"""Lightweight `/spec-core` orchestration helpers."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import spec_anchor.config as config_api
import spec_anchor.claim_retrieval as claim_retrieval_api
import spec_anchor.conflict_candidates as conflict_candidates_api
import spec_anchor.related_sections as related_sections_api
import spec_anchor.retrieval_index as retrieval_index_api
import spec_anchor.section_metadata as section_metadata_api
import spec_anchor.section_parser as section_parser_api
import spec_anchor.spec_claims as spec_claims_api
import spec_anchor.llm_provider as llm_provider_api
from spec_anchor.artifacts import ArtifactError, ContextArtifactStore, build_empty_chapter_anchors
from spec_anchor.conflict_review import (
    apply_conflict_decision,
    evaluate_conflicts,
    refresh_conflict_resolution_staleness,
    summarize_conflict_review_state,
)
from spec_anchor.core_lock import (
    DEFAULT_STALE_LOCK_MS,
    acquire_core_update_lock,
    core_update_lock_path,
    lock_diagnostics,
    lock_is_stale,
    release_core_update_lock,
)
from spec_anchor.core_progress import CoreProgressTracker
from spec_anchor.freshness import build_freshness_report


RETRIEVAL_INDEX_STATE_SCHEMA_VERSION = 1
RELATED_SECTIONS_STATE_SCHEMA_VERSION = 1
RELATED_SECTIONS_ARTIFACT_SCHEMA_VERSION = 1
UNCHANGED_SECTION_REASON = "section_hashes_match"


def run_spec_core(
    project_root: str | Path = ".",
    *,
    all: bool = False,
    all_mode: bool = False,
    full: bool = False,
    force: bool = False,
    mode: str | None = None,
    rebuild_embeddings: bool = False,
    verify_index: bool = False,
    decision_payload: Mapping[str, Any] | None = None,
    decision: Mapping[str, Any] | None = None,
    conflict_decision: Mapping[str, Any] | None = None,
    provider: Any = None,
    llm_provider: Any = None,
    llm_provider_id: str | None = None,
    conflict_judge: Any = None,
    judge: Any = None,
    generated_at: str | None = None,
    source_snapshot: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    snapshot: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    watcher_snapshot: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    run_id: str | None = None,
    stale_lock_ms: int | None = None,
    now_ms: int | None = None,
    role: str | None = None,
    runner_role: str | None = None,
    internal: bool = False,
    internal_watcher: bool = False,
    called_by_watcher: bool = False,
    execution_role: str | None = None,
    bypass_update_lock: bool = False,
    heartbeat: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a small, deterministic `/spec-core` update and return CoreResult."""

    root = Path(project_root).expanduser().resolve()
    generated_at = generated_at or _nowish()
    run_full = bool(all or all_mode or full or force or mode == "full")
    mode_name = "full" if run_full else "incremental"
    update_lock = None
    run_id = run_id or str(uuid.uuid4())

    try:
        config = _load_project_config(root)
    except config_api.ConfigError as exc:
        return _config_error_core_result(
            root,
            mode_name=mode_name,
            generated_at=generated_at,
            exc=exc,
        )

    if not _bypasses_update_lock(
        internal=internal,
        internal_watcher=internal_watcher,
        called_by_watcher=called_by_watcher,
        role=role,
        runner_role=runner_role,
        execution_role=execution_role,
        bypass_update_lock=bypass_update_lock,
    ):
        lock_now_ms = _now_ms() if now_ms is None else int(now_ms)
        blocked = _watcher_state_blocked_result(
            root,
            config,
            mode_name=mode_name,
            generated_at=generated_at,
            stale_lock_ms=stale_lock_ms,
            now_ms=lock_now_ms,
            check_staleness=_checks_watcher_state_staleness(
                config,
                stale_lock_ms=stale_lock_ms,
                now_ms=now_ms,
            ),
        )
        if blocked is not None:
            return blocked
        lock_attempt = acquire_core_update_lock(
            root,
            owner="spec_core",
            run_id=run_id,
            stale_lock_ms=_stale_lock_ms(config, stale_lock_ms),
            now_ms=lock_now_ms,
            metadata={"entrypoint": "/spec-core", "mode": mode_name},
        )
        if not lock_attempt.acquired:
            return _blocked_core_result(
                root,
                mode_name=mode_name,
                freshness_report=build_freshness_report(watcher_running=True),
                generated_at=generated_at,
                diagnostics={
                    "blocked_by": lock_attempt.reason,
                    "lock": lock_diagnostics(
                        lock_attempt.existing_lock,
                        path=lock_attempt.path,
                    ),
                },
            )
        update_lock = lock_attempt.lock

    try:
        return _run_spec_core_unlocked(
            root,
            config=config,
            all=all,
            all_mode=all_mode,
            full=full,
            force=force,
            mode=mode,
            rebuild_embeddings=rebuild_embeddings,
            verify_index=verify_index,
            decision_payload=decision_payload,
            decision=decision,
            conflict_decision=conflict_decision,
            provider=provider,
            llm_provider=llm_provider,
            llm_provider_id=llm_provider_id,
            conflict_judge=conflict_judge,
            judge=judge,
            generated_at=generated_at,
            source_snapshot=source_snapshot,
            snapshot=snapshot,
            watcher_snapshot=watcher_snapshot,
            role=role,
            runner_role=runner_role,
            internal_watcher=internal_watcher,
            called_by_watcher=called_by_watcher,
            execution_role=execution_role,
            heartbeat=heartbeat,
            run_id=run_id,
            **kwargs,
        )
    finally:
        release_core_update_lock(update_lock)


def _run_spec_core_unlocked(
    project_root: str | Path = ".",
    *,
    config: Mapping[str, Any] | None = None,
    all: bool = False,
    all_mode: bool = False,
    full: bool = False,
    force: bool = False,
    mode: str | None = None,
    rebuild_embeddings: bool = False,
    verify_index: bool = False,
    decision_payload: Mapping[str, Any] | None = None,
    decision: Mapping[str, Any] | None = None,
    conflict_decision: Mapping[str, Any] | None = None,
    provider: Any = None,
    llm_provider: Any = None,
    llm_provider_id: str | None = None,
    conflict_judge: Any = None,
    judge: Any = None,
    generated_at: str | None = None,
    source_snapshot: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    snapshot: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    watcher_snapshot: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    role: str | None = None,
    runner_role: str | None = None,
    internal_watcher: bool = False,
    called_by_watcher: bool = False,
    execution_role: str | None = None,
    heartbeat: Callable[..., Any] | None = None,
    run_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Run a small, deterministic `/spec-core` update after external locking."""

    root = Path(project_root)
    generated_at = generated_at or _nowish()
    config = dict(config) if config is not None else _load_project_config(root)
    run_full_for_progress = bool(all or all_mode or full or force or mode == "full")
    progress_mode = "full" if run_full_for_progress else "incremental"
    progress_tracker = (
        CoreProgressTracker(
            root,
            run_id=run_id or "unknown",
            mode=progress_mode,
            generated_at=generated_at,
        )
        if not _is_watcher_internal_update(
            internal_watcher=internal_watcher,
            called_by_watcher=called_by_watcher,
            role=role,
            runner_role=runner_role,
            execution_role=execution_role,
        )
        else None
    )

    def emit(stage: str) -> Any:
        if progress_tracker is not None:
            progress_tracker.emit(stage)
        return _emit_heartbeat(heartbeat, stage=stage)

    emit("core_start")
    purpose_path = root / _config_get(config, ("core", "purpose_file"), "docs/core/purpose.md")
    concept_path = root / _config_get(config, ("core", "concept_file"), "docs/core/concept.md")
    purpose_text = _read_required(purpose_path)
    concept_text = _read_required(concept_path)
    emit("core_inputs_loaded")
    purpose_hash = _hash_text(purpose_text)
    concept_hash = _hash_text(concept_text)
    purpose_ref = _project_ref(root, purpose_path)
    concept_ref = _project_ref(root, concept_path)

    context_dir = root / _config_get(config, ("context", "storage"), ".spec-anchor/context")
    cache_dir = root / ".spec-anchor/cache"
    store = ContextArtifactStore(context_dir)
    previous_section_manifest = _read_artifact(store, "section_manifest")
    previous_conflicts = _read_artifact(store, "conflict_review_items")
    previous_metadata = _read_previous_section_metadata(config, store)

    run_full = bool(all or all_mode or full or force or mode == "full")
    mode_name = "full" if run_full else "incremental"

    # `--all` clears the LLM-derived caches BEFORE the stages run, so the new
    # run's `cache.store()` writes become the post-run cache state
    # (EXTERNAL_DESIGN §7.4 「クリアして再評価」).
    # - section_metadata / chapter_anchors caches are content-addressed
    #   per-section / per-chapter; the clear removes orphans from earlier
    #   prompt_version / model / cache_key changes.
    # - related_typing_cache.json is flat JSON keyed by section pair
    #   signatures with no content-addressed naming, so the physical
    #   removal is the only way to force re-typing under `--all`.
    if run_full:
        related_pair_cache_file = cache_dir / "related_typing_cache.json"
        try:
            related_pair_cache_file.unlink()
        except FileNotFoundError:
            pass
        for subdir_name in (
            "section_metadata",
            "chapter_anchors",
            conflict_candidates_api.CONFLICT_CANDIDATE_TRIAGE_CACHE_DIRNAME,
        ):
            subdir = cache_dir / subdir_name
            if subdir.is_dir():
                for cache_file in subdir.glob("*.json"):
                    try:
                        cache_file.unlink()
                    except FileNotFoundError:
                        pass
    # Phase H-3: resolve a provider per stage so [llm.stage_routing] can target
    # different model/effort tuples for extraction (section_metadata),
    # classification (related_sections), judgment (conflict_review), and
    # chapter anchor synthesis (chapter_key_anchor).
    metadata_llm_config = _config_with_selected_llm(
        config,
        provider_id=llm_provider_id,
        stage="section_metadata",
    )
    related_llm_config = _config_with_selected_llm(
        config,
        provider_id=llm_provider_id,
        stage="related_sections",
    )
    conflict_llm_config = _config_with_selected_llm(
        config,
        provider_id=llm_provider_id,
        stage="conflict_review",
    )
    chapter_anchor_llm_config = _config_with_selected_llm(
        config,
        provider_id=llm_provider_id,
        stage="chapter_key_anchor",
    )
    spec_claims_llm_config = _config_with_selected_llm(
        config,
        provider_id=llm_provider_id,
        stage="spec_claims",
    )
    conflict_candidate_triage_llm_config = _config_with_selected_llm(
        config,
        provider_id=llm_provider_id,
        stage="conflict_candidate_triage",
    )
    metadata_provider = _resolve_spec_core_llm_provider(
        metadata_llm_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_provider_id=llm_provider_id,
        stage="section_metadata",
    )
    related_provider = _resolve_spec_core_llm_provider(
        related_llm_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_provider_id=llm_provider_id,
        stage="related_sections",
    )
    conflict_provider = _resolve_spec_core_llm_provider(
        conflict_llm_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_provider_id=llm_provider_id,
        stage="conflict_review",
    )
    chapter_anchor_provider = _resolve_spec_core_llm_provider(
        chapter_anchor_llm_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_provider_id=llm_provider_id,
        stage="chapter_key_anchor",
    )
    spec_claims_provider = _resolve_spec_core_llm_provider(
        spec_claims_llm_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_provider_id=llm_provider_id,
        stage="spec_claims",
    )
    conflict_candidate_triage_provider = _resolve_spec_core_llm_provider(
        conflict_candidate_triage_llm_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_provider_id=llm_provider_id,
        stage="conflict_candidate_triage",
    )
    # Backward-compat aliases for code paths that read these names.
    llm_generation_config = metadata_llm_config
    active_provider = metadata_provider
    active_judge = conflict_judge or judge or conflict_provider

    sections = _load_sections_from_snapshot(
        root,
        config,
        source_snapshot or snapshot or watcher_snapshot,
    ) if source_snapshot or snapshot or watcher_snapshot else _load_sections(root, config)
    emit("core_sections_loaded")
    unchanged_sections = _section_unchanged_decision(
        sections,
        previous_section_manifest,
        run_full=run_full,
    )
    old_entries = {
        str(entry.get("section_id") or entry.get("source_section_id")): entry
        for entry in previous_metadata.get("sections", [])
        if isinstance(entry, Mapping)
    }
    changed_ids = {
        section["section_id"]
        for section in sections
        if run_full
        or section["section_id"] not in old_entries
        or old_entries[section["section_id"]].get("semantic_hash") != section["semantic_hash"]
    }

    emit("core_section_metadata_start")
    metadata_generation = section_metadata_api.generate_section_metadata_result(
        sections,
        config=llm_generation_config,
        provider=active_provider,
        previous_metadata=previous_metadata,
        rebuild_all=run_full,
        cache_dir=cache_dir,
        generated_at=generated_at,
    )
    metadata_generation_results = _metadata_generation_results_by_section(
        metadata_generation
    )
    metadata_diagnostics_by_section = _metadata_diagnostics_by_section(
        metadata_generation
    )
    failed_section_ids = {
        section_id
        for section_id, result in metadata_generation_results.items()
        if result.status != "success"
    } | set(metadata_diagnostics_by_section)
    reused_section_ids = set(metadata_generation.reused_section_ids)
    generated_section_ids = set(metadata_generation.generated_section_ids)
    updated_sections = [
        _section_ref(section)
        for section in sections
        if section["section_id"] in generated_section_ids
        and section["section_id"] not in failed_section_ids
    ]
    skipped_sections = [
        _section_ref(section)
        for section in sections
        if section["section_id"] in reused_section_ids
    ]
    failed_sections = [
        _section_ref(section)
        for section in sections
        if section["section_id"] in failed_section_ids
    ]
    metadata_entries = _core_metadata_entries(
        metadata_generation,
        sections=sections,
        provider=active_provider,
        failed_section_ids=failed_section_ids,
    )
    section_metadata = dict(metadata_generation.artifact)
    section_metadata["metadata_version"] = 1
    section_metadata["prompt_version"] = section_metadata_api.SECTION_METADATA_PROMPT_VERSION
    section_metadata["sections"] = metadata_entries
    section_metadata["generated_at"] = generated_at
    if progress_tracker is not None:
        _record_llm_call_stats(
            progress_tracker,
            "section_metadata",
            metadata_generation.llm_results,
        )
    emit("core_section_metadata_done")
    section_collection_fingerprints_by_id: dict[str, Mapping[str, str]] = {}
    section_collection_upsert_info: dict[str, Any] = {}
    emit("core_section_collection_upsert_start")
    retrieval_index_status = _upsert_section_collection_if_enabled(
        config=config,
        sections=sections,
        section_metadata=section_metadata,
        force_full_recreate=rebuild_embeddings,
        emit=emit,
        store=store,
        run_full=run_full,
        unchanged_sections=unchanged_sections,
        generated_at=generated_at,
        progress_tracker=progress_tracker,
        previous_section_manifest=previous_section_manifest,
        section_payload_fingerprints_out=section_collection_fingerprints_by_id,
        section_collection_upsert_info_out=section_collection_upsert_info,
    )
    emit("core_section_collection_upsert_done")
    verify_section_manifest = {
        "sections": [
            _section_manifest_entry(
                section,
                fingerprints=section_collection_fingerprints_by_id.get(
                    str(section.get("section_id") or section.get("source_section_id") or ""),
                ),
            )
            for section in sections
        ]
    }
    retrieval_index_status, verify_index_diagnostics = _verify_section_collection_if_requested(
        config=config,
        section_manifest=verify_section_manifest,
        retrieval_index_status=retrieval_index_status,
        verify_index=verify_index,
        force_full_recreate=rebuild_embeddings,
        section_collection_upsert_info=section_collection_upsert_info,
        progress_tracker=progress_tracker,
    )
    section_diff_sets = _section_collection_diff_sets(
        sections,
        previous_section_manifest,
        section_collection_fingerprints_by_id,
    )
    emit("core_related_sections_start")
    related_pair_cache_dir = cache_dir
    related_generation = _generate_related_sections(
        sections=sections,
        section_metadata=section_metadata,
        provider=related_provider,
        config=related_llm_config,
        generated_at=generated_at,
        cache_dir=related_pair_cache_dir,
        store=store,
        run_full=run_full,
        unchanged_sections=unchanged_sections,
        section_diff_sets=section_diff_sets,
        previous_related_sections=previous_metadata,
        retrieval_index_status=retrieval_index_status,
        progress_tracker=progress_tracker,
    )
    related_sections_status = _related_sections_status(related_generation)
    related_sections_qdrant_backend_failure = _related_sections_qdrant_backend_failure(
        related_generation
    )
    related_section_candidates = _related_section_candidates(related_generation)
    selected_related_sections = _merge_related_sections_by_source(
        _related_sections_by_source(related_generation),
        _metadata_related_sections_by_source(
            section_metadata,
            candidates=related_section_candidates,
            sections=sections,
            generated_at=generated_at,
        ),
    )
    # AUD-007: Qdrant backend が初期化に失敗して related_sections が failed の場合、
    # canonical artifact (section_manifest の related_sections field + Qdrant
    # section payload の related_sections) を更新せず前回値を残す。
    if related_sections_status != "failed":
        section_metadata = related_sections_api.apply_related_sections_to_metadata(
            section_metadata,
            {"related_sections": selected_related_sections},
        )
    if related_sections_status not in {"skipped_unchanged", "failed"}:
        _update_section_collection_related_sections_if_enabled(
            config=config,
            section_metadata=section_metadata,
            emit=emit,
        )
    if progress_tracker is not None:
        related_llm_results = getattr(
            getattr(related_generation, "selection", None), "llm_results", []
        ) or []
        _record_llm_call_stats(
            progress_tracker,
            "related_sections",
            related_llm_results,
        )
    emit("core_related_sections_done")
    emit("core_spec_claims_start")
    spec_claims_generation = _generate_spec_claims_if_enabled(
        root=root,
        config=spec_claims_llm_config,
        sections=sections,
        provider=spec_claims_provider,
        generated_at=generated_at,
        context_dir=context_dir,
        run_full=run_full,
        progress_tracker=progress_tracker,
    )
    emit("core_spec_claims_done")
    spec_claims_status = str(spec_claims_generation.get("status") or "failed")
    spec_claims_diagnostics = dict(spec_claims_generation.get("diagnostics") or {})
    emit("core_claim_retrieval_start")
    claim_retrieval_generation = _generate_claim_retrieval_if_enabled(
        root=root,
        config=config,
        spec_claims_status=spec_claims_status,
        spec_claims_diagnostics=spec_claims_diagnostics,
        generated_at=generated_at,
        context_dir=context_dir,
        run_full=run_full,
        progress_tracker=progress_tracker,
    )
    emit("core_claim_retrieval_done")
    claim_retrieval_status = str(
        claim_retrieval_generation.get("status") or "failed"
    )
    claim_retrieval_diagnostics = dict(
        claim_retrieval_generation.get("diagnostics") or {}
    )
    emit("core_conflict_candidate_triage_start")
    conflict_candidate_triage_generation = (
        _generate_conflict_candidate_triage_if_enabled(
            root=root,
            config=conflict_candidate_triage_llm_config,
            spec_claims_status=spec_claims_status,
            claim_retrieval_status=claim_retrieval_status,
            generated_at=generated_at,
            context_dir=context_dir,
            cache_dir=cache_dir,
            provider=conflict_candidate_triage_provider,
            run_full=run_full,
            progress_tracker=progress_tracker,
        )
    )
    emit("core_conflict_candidate_triage_done")
    conflict_candidate_triage_status = str(
        conflict_candidate_triage_generation.get("status") or "failed"
    )
    conflict_candidate_triage_diagnostics = dict(
        conflict_candidate_triage_generation.get("diagnostics") or {}
    )
    metadata_entries = [
        dict(entry)
        for entry in section_metadata.get("sections", [])
        if isinstance(entry, Mapping)
    ]
    # payload_fingerprint must be stable across the related_sections apply
    # boundary so the manifest value matches the value computed on the next
    # run's diff. retrieval_index._payload_fingerprint_input excludes
    # `related_sections` for this reason; recomputing here is unnecessary.

    updated_sources = _source_refs_for_sections(updated_sections)
    skipped_sources = [
        source
        for source in _source_refs_for_sections(skipped_sections)
        if source not in updated_sources
    ]

    existing_conflict_items = [
        dict(item)
        for item in previous_conflicts.get("conflict_review_items", previous_conflicts.get("items", []))
        if isinstance(item, Mapping)
    ]
    payload = decision_payload or decision or conflict_decision
    if payload:
        emit("core_conflict_decision_start")
        existing_conflict_items = apply_conflict_decision(
            conflict_review_items=existing_conflict_items,
            decision_payload=dict(payload),
            generated_at=generated_at,
        )
        emit("core_conflict_decision_done")

    conflict_candidate_pairs = conflict_candidates_api.read_conflict_candidate_pairs_jsonl(
        context_dir / claim_retrieval_api.CONFLICT_CANDIDATE_PAIRS_JSONL_FILENAME
    )
    spec_claim_records = _read_jsonl_records(
        context_dir / spec_claims_api.SPEC_CLAIMS_JSONL_FILENAME
    )
    emit("core_conflict_evaluation_start")
    conflict_result = evaluate_conflicts(
        conflict_candidate_pairs=conflict_candidate_pairs,
        spec_claims=spec_claim_records,
        sections=sections,
        conflict_judge=_EvidenceGroundedConflictJudge(
            active_judge,
            purpose_ref=purpose_ref,
            purpose_text=purpose_text,
            purpose_hash=purpose_hash,
            concept_ref=concept_ref,
            concept_text=concept_text,
            concept_hash=concept_hash,
            llm_config=_config_get(conflict_llm_config, ("llm",), {}),
        ),
        config=config,
        generated_at=generated_at,
    )
    emit("core_conflict_evaluation_done")
    if progress_tracker is not None:
        from types import SimpleNamespace
        _record_llm_call_stats(
            progress_tracker,
            "conflict_evaluation",
            [
                SimpleNamespace(attempts=1, status="success", artifact=None, usage=u)
                for u in getattr(conflict_result, "usage_list", [])
                if u
            ],
        )
    conflict_payload = conflict_result.to_dict() if hasattr(conflict_result, "to_dict") else dict(conflict_result)
    new_items = [
        dict(item)
        for item in conflict_payload.get("conflict_review_items", [])
        if isinstance(item, Mapping)
    ]
    conflict_review_items = _merge_conflict_items(existing_conflict_items, new_items)
    conflict_review_items = _ensure_context_base_hashes(
        conflict_review_items,
        purpose_ref=purpose_ref,
        purpose_hash=purpose_hash,
        concept_ref=concept_ref,
        concept_hash=concept_hash,
    )
    current_hashes = {section["section_id"]: section["source_hash"] for section in sections}
    current_hashes[purpose_ref] = purpose_hash
    current_hashes[concept_ref] = concept_hash
    conflict_review_items = refresh_conflict_resolution_staleness(
        conflict_review_items=conflict_review_items,
        current_source_hashes=current_hashes,
    )
    conflict_summary = summarize_conflict_review_state(conflict_review_items=conflict_review_items)
    potential_conflicts = list(conflict_payload.get("potential_conflicts") or conflict_payload.get("diagnostics") or [])
    conflict_selection_diagnostics = list(conflict_payload.get("selection_diagnostics") or [])
    pending_conflict_count = int(conflict_summary.get("pending_conflict_count", 0))
    stale_resolution_count = int(conflict_summary.get("stale_resolution_count", 0))
    unreflected_conflicts = [
        item
        for item in conflict_review_items
        if item.get("status") == "resolved" and item.get("reflection_status", "unreflected") == "unreflected"
    ]
    metadata_generation_summary = llm_provider_api.summarize_generation_results(
        metadata_generation_results
    )
    if failed_section_ids:
        metadata_generation_summary = _summarize_metadata_generation(
            metadata_generation,
            failed_section_ids=failed_section_ids,
        )
    generation_status = str(metadata_generation_summary.get("freshness_status") or "fresh")
    failed_required_artifacts = []
    if generation_status == "failed":
        failed_required_artifacts.append("section_metadata")
    if retrieval_index_status == "failed":
        failed_required_artifacts.append("retrieval_index")
    if related_sections_status == "failed":
        # AUD-007: Qdrant 設定済みなのに retriever 初期化失敗時、Related Sections は
        # required artifact failure として扱う (degraded ではない)。
        failed_required_artifacts.append("related_sections")
    degraded_optional_artifacts = []
    if generation_status == "degraded":
        degraded_optional_artifacts.append("section_metadata")
    generation_warnings = list(metadata_generation_summary.get("warnings") or [])
    if retrieval_index_status == "failed":
        if _verify_index_has_issues(verify_index_diagnostics):
            generation_warnings.append(
                "Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild"
            )
        else:
            generation_warnings.append("Source Retrieval Index update failed")
    if related_sections_status == "failed":
        if related_sections_qdrant_backend_failure is not None:
            failure_reason = str(
                related_sections_qdrant_backend_failure.get("failure_reason") or ""
            )
            generation_warnings.append(
                "Related Sections retrieval backend failure: "
                f"{failure_reason}; canonical related_sections artifact is not updated. "
                "Restore Qdrant connectivity and run /spec-core --rebuild."
            )
        else:
            generation_warnings.append("Related Sections generation failed")
    generation_diagnostics = {
        "section_metadata_generation": {
            **metadata_generation_summary,
            "llm_calls": metadata_generation.llm_calls,
            "batch_sizes": list(metadata_generation.batch_sizes),
            "cache_hits": metadata_generation.cache_hits,
            "reused_section_ids": list(metadata_generation.reused_section_ids),
            "generated_section_ids": list(metadata_generation.generated_section_ids),
            "diagnostics": {
                section_id: list(metadata_diagnostics_by_section.get(section_id) or [])
                for section_id in sorted(failed_section_ids)
            },
        },
        "retrieval_index": {
            "status": retrieval_index_status,
        },
        "verify_index": verify_index_diagnostics,
        "related_sections": {
            "status": related_sections_status,
            "diagnostics": _related_generation_diagnostics(related_generation),
            "qdrant_backend_failure": related_sections_qdrant_backend_failure,
        },
        "spec_claims": {
            "status": spec_claims_status,
            "diagnostics": spec_claims_diagnostics,
        },
        "claim_retrieval": {
            "status": claim_retrieval_status,
            "diagnostics": claim_retrieval_diagnostics,
        },
        "conflict_candidate_triage": {
            "status": conflict_candidate_triage_status,
            "diagnostics": conflict_candidate_triage_diagnostics,
        },
    }
    if conflict_selection_diagnostics:
        generation_diagnostics["conflict_review"] = {
            "status": "success",
            "diagnostics": conflict_selection_diagnostics,
        }

    section_manifest_audit_by_id = _section_manifest_audit_by_id(
        metadata_entries,
        generated_at=generated_at,
    )
    section_manifest_payload: dict[str, Any] = {
        "sections": [
            _section_manifest_entry(
                section,
                audit=section_manifest_audit_by_id.get(
                    str(section.get("section_id") or section.get("source_section_id") or ""),
                ),
                fingerprints=section_collection_fingerprints_by_id.get(
                    str(section.get("section_id") or section.get("source_section_id") or ""),
                ),
            )
            for section in sections
        ],
        "purpose_hash": purpose_hash,
        "concept_hash": concept_hash,
        "generated_at": generated_at,
    }
    # The `generation` audit block is the prompt / model / provider /
    # metadata_version / enabled_fields / limits used to produce the section
    # metadata in this run. Persisting it at the section_manifest top level
    # lets the next run validate prior Qdrant payload entries with
    # `_reusable_existing_entry` after `--all` has wiped the on-disk LLM
    # cache. Without it, the post-`--all` incremental run cannot reuse any
    # unchanged section and re-runs every LLM call.
    metadata_generation_block = section_metadata.get("generation")
    if isinstance(metadata_generation_block, Mapping):
        section_manifest_payload["generation"] = dict(metadata_generation_block)
    section_manifest = section_manifest_payload
    emit("core_chapter_anchors_start")
    chapter_anchors, chapter_anchors_llm_results, chapter_anchors_failed_ids = _chapter_anchors(
        sections,
        metadata_entries,
        generated_at,
        config=chapter_anchor_llm_config,
        provider=chapter_anchor_provider,
        cache_dir=cache_dir,
        concept_text=concept_text,
        rebuild_all=run_full,
    )
    if progress_tracker is not None:
        _record_llm_call_stats(
            progress_tracker,
            "chapter_anchors",
            chapter_anchors_llm_results,
        )
    emit("core_chapter_anchors_done")
    if chapter_anchors.get("status") == "failed":
        failed_required_artifacts.append("chapter_anchors")
        generation_warnings.append(
            f"Chapter Anchors LLM generation failed for {len(chapter_anchors_failed_ids)} chapter(s); "
            f"canonical chapter_anchors.json is not updated. Run /spec-core --all to retry."
        )
    generation_diagnostics["chapter_anchors"] = {
        "status": chapter_anchors.get("status"),
        "failed_chapter_ids": chapter_anchors_failed_ids,
        "failure_reasons_by_chapter": chapter_anchors.get("generation", {}).get(
            "failure_reasons_by_chapter",
            {},
        ),
    }
    freshness_report = build_freshness_report(
        conflict_review_items=conflict_review_items,
        failed_required_artifacts=failed_required_artifacts,
        degraded_optional_artifacts=degraded_optional_artifacts,
        warnings=generation_warnings,
        diagnostics=generation_diagnostics,
    )
    watcher_internal_update = _is_watcher_internal_update(
        internal_watcher=internal_watcher,
        called_by_watcher=called_by_watcher,
        role=role,
        runner_role=runner_role,
        execution_role=execution_role,
    )
    artifacts = {
        "section_manifest": section_manifest,
        "conflict_review_items": {
            "conflict_review_items": conflict_review_items,
            "generated_at": generated_at,
        },
    }
    if chapter_anchors.get("status") == "success":
        artifacts["chapter_anchors"] = chapter_anchors
    if not watcher_internal_update:
        artifacts["freshness"] = freshness_report
    emit("core_artifact_write_start")
    store.write_context_update(artifacts)
    emit("core_artifact_write_done")
    if progress_tracker is not None:
        progress_tracker.finalize(status="completed")

    result_warnings = _dedupe_strings(
        [
            *generation_warnings,
            *list(freshness_report.get("warnings") or []),
        ]
    )
    diagnostics_payload = dict(generation_diagnostics)
    diagnostics_payload["section_metadata"] = section_metadata
    return {
        "status": (
            "failed" if freshness_report["status"] == "failed"
            else "degraded" if freshness_report["status"] == "degraded"
            else "updated"
        ),
        "mode": mode_name,
        "updated_sources": updated_sources,
        "skipped_sources": skipped_sources,
        "failed_sources": _source_refs_for_sections(failed_sections),
        "failed_sections": failed_sections,
        "updated_sections": updated_sections,
        "skipped_sections": skipped_sections,
        "regenerated_chapter_anchors": sorted({section["chapter_id"] for section in sections if section["section_id"] in changed_ids}),
        "retrieval_index_status": retrieval_index_status,
        "related_sections_status": related_sections_status,
        "spec_claims_status": spec_claims_status,
        "spec_claims_diagnostics": spec_claims_diagnostics,
        "claim_retrieval_status": claim_retrieval_status,
        "claim_retrieval_diagnostics": claim_retrieval_diagnostics,
        "conflict_candidate_triage_status": conflict_candidate_triage_status,
        "conflict_candidate_triage_diagnostics": conflict_candidate_triage_diagnostics,
        "potential_conflicts": potential_conflicts,
        "conflict_review_items": conflict_review_items,
        "pending_conflict_count": pending_conflict_count,
        "unreflected_conflict_resolutions": unreflected_conflicts,
        "stale_resolution_count": stale_resolution_count,
        "freshness_report": freshness_report,
        "warnings": result_warnings,
        "diagnostics": diagnostics_payload,
    }


def run_spec_core_for_watcher(project_root: str | Path = ".", **kwargs: Any) -> dict[str, Any]:
    """Internal watcher entry point, intentionally distinct from slash command API."""

    kwargs.setdefault("role", "watcher")
    kwargs.setdefault("runner_role", "watcher")
    kwargs.setdefault("internal", True)
    kwargs.setdefault("internal_watcher", True)
    kwargs.setdefault("called_by_watcher", True)
    kwargs.setdefault("execution_role", "watcher")
    kwargs.setdefault("bypass_update_lock", True)
    return run_spec_core(project_root, **kwargs)


def _record_llm_call_stats(
    tracker: CoreProgressTracker,
    stage: str,
    llm_results: Sequence[Any],
) -> None:
    """Aggregate LLM call counts from a stage's `LlmGenerationResult` list and
    persist them to the progress tracker.

    `LlmGenerationResult.attempts` records the actual number of subprocess
    invocations (initial + retries). Together with the result count we report:
    - `llm_calls`: subprocess invocations across the stage (sum of attempts)
    - `retry_count`: how many of those calls were retries (attempts - 1 each)
    - `failed_batch_ids`: section_id of any batch whose final status != success
    """

    if not llm_results:
        return
    total_calls = 0
    total_retries = 0
    failed_batch_ids: list[str] = []
    usage_totals: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "total_cost_usd": 0.0,
        "providers_seen": [],
        "models_seen": [],
    }
    for index, result in enumerate(llm_results):
        attempts = int(getattr(result, "attempts", 1) or 1)
        total_calls += attempts
        total_retries += max(0, attempts - 1)
        status = getattr(result, "status", "")
        artifact = getattr(result, "artifact", None)
        if status != "success":
            section_id = (
                getattr(artifact, "section_id", None)
                if artifact is not None
                else None
            )
            failed_batch_ids.append(str(section_id or f"{stage}-batch-{index}"))
        model_name = str(getattr(artifact, "model", None) or "")
        if model_name and model_name not in usage_totals["models_seen"]:
            usage_totals["models_seen"].append(model_name)
        usage = getattr(result, "usage", None) or {}
        if usage:
            provider_name = str(usage.get("provider") or "")
            if provider_name and provider_name not in usage_totals["providers_seen"]:
                usage_totals["providers_seen"].append(provider_name)
            for token_field in (
                "input_tokens",
                "output_tokens",
                "cached_input_tokens",
                "reasoning_output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            ):
                if token_field in usage:
                    usage_totals[token_field] += int(usage.get(token_field) or 0)
            cost = usage.get("total_cost_usd")
            if cost is not None:
                usage_totals["total_cost_usd"] += float(cost or 0.0)
    tracker.increment(
        stage,
        llm_calls=total_calls,
        retry_count=total_retries,
        failed_batch_ids=failed_batch_ids,
        token_count=usage_totals["input_tokens"] + usage_totals["output_tokens"],
    )
    tracker.update(
        stage,
        batch_count=len(llm_results),
        actual_call_count=total_calls,
        usage=usage_totals,
    )


def _bypasses_update_lock(
    *,
    internal: bool,
    internal_watcher: bool,
    called_by_watcher: bool,
    role: str | None,
    runner_role: str | None,
    execution_role: str | None,
    bypass_update_lock: bool,
) -> bool:
    roles = {str(value).lower() for value in (role, runner_role, execution_role) if value}
    return bool(
        bypass_update_lock
        or internal
        or internal_watcher
        or called_by_watcher
        or roles & {"watcher", "watcher_internal", "internal_watcher"}
    )


def _is_watcher_internal_update(
    *,
    internal_watcher: bool,
    called_by_watcher: bool,
    role: str | None,
    runner_role: str | None,
    execution_role: str | None,
) -> bool:
    roles = {str(value).lower() for value in (role, runner_role, execution_role) if value}
    return bool(
        internal_watcher
        or called_by_watcher
        or roles & {"watcher", "watcher_internal", "internal_watcher"}
    )


def _emit_heartbeat(heartbeat: Callable[..., Any] | None, *, stage: str) -> Any:
    if heartbeat is None:
        return None
    try:
        return heartbeat(stage=stage)
    except TypeError as exc:
        try:
            return heartbeat()
        except TypeError:
            raise exc


def _watcher_state_blocked_result(
    root: Path,
    config: Mapping[str, Any],
    *,
    mode_name: str,
    generated_at: str,
    stale_lock_ms: int | None,
    now_ms: int | None,
    check_staleness: bool = True,
) -> dict[str, Any] | None:
    state_path = _watcher_state_path(root, config)
    state = _read_json_mapping(state_path)
    if not state or not _state_running(state):
        return None
    effective_now_ms = _now_ms() if now_ms is None else int(now_ms)
    if check_staleness and lock_is_stale(
        state,
        stale_lock_ms=_stale_lock_ms(config, stale_lock_ms),
        now_ms=effective_now_ms,
    ):
        return None
    return _blocked_core_result(
        root,
        mode_name=mode_name,
        freshness_report=build_freshness_report(watcher_running=True),
        generated_at=generated_at,
        diagnostics={
            "blocked_by": "watcher_running",
            "watcher_state_file": state_path.as_posix(),
            "watcher_state": {
                "owner": state.get("owner"),
                "run_id": state.get("run_id"),
                "started_at": state.get("started_at"),
                "started_at_epoch_ms": state.get("started_at_epoch_ms"),
                "updated_at": state.get("updated_at"),
                "updated_at_epoch_ms": state.get("updated_at_epoch_ms"),
            },
        },
    )


def _checks_watcher_state_staleness(
    config: Mapping[str, Any],
    *,
    stale_lock_ms: int | None,
    now_ms: int | None,
) -> bool:
    return bool(now_ms is not None or stale_lock_ms is not None or isinstance(config.get("watcher"), Mapping))


def _blocked_core_result(
    root: Path,
    *,
    mode_name: str,
    freshness_report: Mapping[str, Any],
    generated_at: str,
    diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    report = build_freshness_report(
        blocking_reasons=list(freshness_report.get("blocking_reasons") or ()),
        warnings=list(freshness_report.get("warnings") or ()),
    )
    return {
        "status": "blocked",
        "blocked": True,
        "mode": mode_name,
        "project_root": root.as_posix(),
        "updated_sources": [],
        "skipped_sources": [],
        "failed_sources": [],
        "failed_sections": [],
        "updated_sections": [],
        "skipped_sections": [],
        "regenerated_chapter_anchors": [],
        "retrieval_index_status": "blocked",
        "related_sections_status": "blocked",
        "spec_claims_status": "blocked",
        "spec_claims_diagnostics": _empty_spec_claims_diagnostics(),
        "claim_retrieval_status": "blocked",
        "claim_retrieval_diagnostics": _empty_claim_retrieval_diagnostics(),
        "conflict_candidate_triage_status": "blocked",
        "conflict_candidate_triage_diagnostics": _empty_conflict_candidate_triage_diagnostics(),
        "potential_conflicts": [],
        "conflict_review_items": [],
        "pending_conflict_count": 0,
        "unreflected_conflict_resolutions": [],
        "stale_resolution_count": 0,
        "freshness_report": report,
        "warnings": list(report.get("warnings") or []),
        "diagnostics": {
            **dict(diagnostics),
            "lock_file": core_update_lock_path(root).as_posix(),
        },
        "generated_at": generated_at,
    }


def _config_error_core_result(
    root: Path,
    *,
    mode_name: str,
    generated_at: str,
    exc: Exception,
) -> dict[str, Any]:
    report = build_freshness_report(
        failed_required_artifacts=["source_specs"],
        warnings=[str(exc)],
        diagnostics={
            "config_error": {
                "reason_code": "config_error",
                "message": str(exc),
                "exception_type": type(exc).__name__,
            }
        },
    )
    return {
        "status": "failed",
        "mode": mode_name,
        "project_root": root.as_posix(),
        "updated_sources": [],
        "skipped_sources": [],
        "failed_sources": [],
        "failed_sections": [],
        "updated_sections": [],
        "skipped_sections": [],
        "regenerated_chapter_anchors": [],
        "retrieval_index_status": "failed",
        "related_sections_status": "blocked",
        "spec_claims_status": "failed",
        "spec_claims_diagnostics": _empty_spec_claims_diagnostics(),
        "claim_retrieval_status": "failed",
        "claim_retrieval_diagnostics": _empty_claim_retrieval_diagnostics(),
        "conflict_candidate_triage_status": "failed",
        "conflict_candidate_triage_diagnostics": _empty_conflict_candidate_triage_diagnostics(),
        "potential_conflicts": [],
        "conflict_review_items": [],
        "pending_conflict_count": 0,
        "unreflected_conflict_resolutions": [],
        "stale_resolution_count": 0,
        "freshness_report": report,
        "warnings": list(report.get("warnings") or []),
        "diagnostics": {
            "config_error": {
                "reason_code": "config_error",
                "message": str(exc),
                "exception_type": type(exc).__name__,
            }
        },
        "generated_at": generated_at,
    }


def _stale_lock_ms(config: Mapping[str, Any], override: int | None) -> int:
    value = override if override is not None else _config_get(
        config,
        ("watcher", "stale_lock_ms"),
        DEFAULT_STALE_LOCK_MS,
    )
    try:
        result = int(value)
    except (TypeError, ValueError):
        return DEFAULT_STALE_LOCK_MS
    return max(0, result)


def _watcher_state_path(root: Path, config: Mapping[str, Any]) -> Path:
    value = _config_get(config, ("watcher", "state_file"), ".spec-anchor/state/watch_state.json")
    return _project_path(root, value)


def _project_path(root: Path, value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else root / path


def _read_json_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def _state_running(state: Mapping[str, Any]) -> bool:
    return bool(state.get("running") or state.get("is_running"))


def _load_project_config(root: Path) -> dict[str, Any]:
    project_config = config_api.load_config(
        root,
        allow_non_standard_providers=True,
    )
    raw = dict(project_config.raw)
    raw["__project_config"] = project_config
    raw["__config_file"] = project_config.config_file.as_posix()
    return raw


def _config_get(config: Mapping[str, Any], path: tuple[str, ...], default: Any = None) -> Any:
    current: Any = config
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _read_previous_section_metadata(
    config: Mapping[str, Any],
    store: ContextArtifactStore,
) -> dict[str, Any]:
    """Reconstruct the prior section metadata payload for `previous_metadata`.

    Combines:
    - per-section content (summary / search_keys / identifiers / related_sections)
      from the Qdrant section collection payload, and
    - the `generation` audit block (prompt_version / model / provider /
      metadata_version / enabled_fields / limits) from `section_manifest.json`.

    `generate_section_metadata_result` uses the returned dict via
    `_existing_entries` to attach `_artifact_generation` to each per-section
    entry, which lets `_reusable_existing_entry` reuse unchanged sections
    after `--all` has wiped the on-disk LLM cache.

    Returns `{"sections": [...], "generation": {...}}`. Either field can be
    empty / missing — `_existing_entries` simply skips reuse when the
    metadata is incomplete, and the LLM generator regenerates the section.
    """

    entries = _read_section_payloads_from_qdrant(config)
    generation = _read_section_manifest_generation(store)
    if generation is not None:
        metadata_version = generation.get("metadata_version")
        if isinstance(metadata_version, int):
            for entry in entries:
                entry.setdefault("metadata_version", metadata_version)
    payload: dict[str, Any] = {"sections": entries}
    if generation is not None:
        payload["generation"] = generation
    return payload


def _read_section_payloads_from_qdrant(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Scroll the Qdrant section collection and return one entry per section.

    Returns an empty list when the section collection is unavailable (fake
    embedding, Qdrant down, collection not yet created). Callers fall back to
    full regeneration in that case.
    """

    embedding_provider = str(_config_get(config, ("embedding", "provider"), ""))
    vector_store_provider = str(_config_get(config, ("vector_store", "provider"), ""))
    if embedding_provider != "flagembedding" or vector_store_provider != "qdrant":
        return []
    from spec_anchor.section_payload import section_payload_to_metadata_entry

    entries: list[dict[str, Any]] = []
    try:
        payloads = _scroll_section_payloads_from_qdrant(config)
    except _SectionPayloadScrollError:
        return []
    for payload in payloads:
        if not payload.get("source_section_id"):
            continue
        entries.append(section_payload_to_metadata_entry(payload))
    return entries


def _read_section_manifest_generation(
    store: ContextArtifactStore,
) -> dict[str, Any] | None:
    """Return the `generation` audit block from the existing section_manifest.

    `generation` was last written by the previous `/spec-core` run. It records
    the prompt / model / provider / metadata_version / enabled_fields / limits
    used at that time. Returns None when the manifest is missing or the block
    is absent (first run).
    """

    try:
        manifest = store.read("section_manifest")
    except ArtifactError:
        return None
    except Exception:
        return None
    if not isinstance(manifest, Mapping):
        return None
    generation = manifest.get("generation")
    if not isinstance(generation, Mapping):
        return None
    return dict(generation)


def _section_collection_name(config: Mapping[str, Any]) -> str:
    value = (
        _config_get(config, ("retrieval", "section_collection"))
        or "spec_anchor_section"
    )
    return str(value)


def _section_unchanged_decision(
    sections: Sequence[Mapping[str, Any]],
    previous_manifest: Mapping[str, Any] | None,
    *,
    run_full: bool,
) -> dict[str, Any]:
    if run_full:
        return {"unchanged": False, "reason": "full_rebuild"}
    if not isinstance(previous_manifest, Mapping) or not previous_manifest.get("sections"):
        return {"unchanged": False, "reason": "manifest_missing"}
    previous_entries = {
        str(entry.get("source_section_id") or entry.get("section_id") or ""): entry
        for entry in previous_manifest.get("sections", [])
        if isinstance(entry, Mapping)
    }
    previous_entries.pop("", None)
    current_ids = {
        str(section.get("source_section_id") or section.get("section_id") or "")
        for section in sections
    }
    current_ids.discard("")
    previous_ids = set(previous_entries)
    added = sorted(current_ids - previous_ids)
    deleted = sorted(previous_ids - current_ids)
    if added:
        return {"unchanged": False, "reason": "section_added", "section_ids": added}
    if deleted:
        return {"unchanged": False, "reason": "section_deleted", "section_ids": deleted}
    for section in sections:
        section_id = str(section.get("source_section_id") or section.get("section_id") or "")
        previous = previous_entries.get(section_id)
        if previous is None:
            return {"unchanged": False, "reason": "section_added", "section_ids": [section_id]}
        if previous.get("source_hash") != section.get("source_hash"):
            return {"unchanged": False, "reason": "source_hash_changed", "section_ids": [section_id]}
        if previous.get("semantic_hash") != section.get("semantic_hash"):
            return {"unchanged": False, "reason": "semantic_hash_changed", "section_ids": [section_id]}
    return {"unchanged": True, "reason": UNCHANGED_SECTION_REASON}


_SECTION_COLLECTION_DIFF_KEYS = (
    "source_hash",
    "semantic_hash",
    "vector_input_fingerprint",
    "payload_fingerprint",
)


def _section_collection_diff_sets(
    sections: Sequence[Mapping[str, Any]],
    previous_manifest: Mapping[str, Any] | None,
    current_payload_fingerprints: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    manifest_sections = (
        previous_manifest.get("sections", [])
        if isinstance(previous_manifest, Mapping)
        else []
    )
    previous_entries = {
        str(entry.get("source_section_id") or entry.get("section_id") or ""): entry
        for entry in manifest_sections
        if isinstance(entry, Mapping)
    }
    previous_entries.pop("", None)
    current_entries: dict[str, dict[str, str]] = {}
    for section in sections:
        section_id = str(section.get("source_section_id") or section.get("section_id") or "")
        if not section_id:
            continue
        fingerprints = current_payload_fingerprints.get(section_id, {})
        current_entries[section_id] = {
            "source_hash": str(section.get("source_hash") or ""),
            "semantic_hash": str(section.get("semantic_hash") or ""),
            "vector_input_fingerprint": str(fingerprints.get("vector_input_fingerprint") or ""),
            "payload_fingerprint": str(fingerprints.get("payload_fingerprint") or ""),
        }

    current_ids = set(current_entries)
    previous_ids = set(previous_entries)
    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)
    changed: list[str] = []
    changed_reasons: dict[str, str] = {}
    for section_id in sorted(current_ids & previous_ids):
        previous = previous_entries[section_id]
        current = current_entries[section_id]
        for key in _SECTION_COLLECTION_DIFF_KEYS:
            if str(previous.get(key) or "") != str(current.get(key) or ""):
                changed.append(section_id)
                changed_reasons[section_id] = key
                break
    unchanged = not added and not changed and not removed
    reason = UNCHANGED_SECTION_REASON
    if added:
        reason = "section_added"
    elif removed:
        reason = "section_deleted"
    elif changed:
        reason = str(changed_reasons.get(changed[0]) or "section_changed")
    return {
        "unchanged": unchanged,
        "reason": reason,
        "added_section_ids": added,
        "changed_section_ids": changed,
        "removed_section_ids": removed,
        "changed_reasons": changed_reasons,
    }


def _build_retrieval_index_state(
    sections: Sequence[Mapping[str, Any]],
    *,
    config: Mapping[str, Any],
    collection: str,
    generated_at: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": RETRIEVAL_INDEX_STATE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "collection_name": collection,
        "section_count": len(sections),
        "section_hash_fingerprint": _section_hash_fingerprint(sections),
        "embedding_provider": str(_config_get(config, ("embedding", "provider"), "")),
        "embedding_model": str(_config_get(config, ("embedding", "model"), "")),
        "dense_enabled": _config_bool(config, ("embedding", "dense_enabled"), True),
        "sparse_enabled": _config_bool(config, ("embedding", "sparse_enabled"), True),
        "retrieval_schema_pin_fingerprint": _retrieval_schema_pin_fingerprint(),
        "artifact_schema_version": retrieval_index_api.SECTION_EMBEDDINGS_ARTIFACT_VERSION,
    }


def _build_related_sections_state(
    sections: Sequence[Mapping[str, Any]],
    *,
    config: Mapping[str, Any],
    provider: Any,
    generated_at: str | None,
) -> dict[str, Any]:
    llm_config = _config_get(config, ("llm",), {})
    provider_id = str(getattr(provider, "provider_id", "") or _config_get(llm_config, ("command",), ""))
    model = str(_config_get(llm_config, ("model",), "") or provider_id or "fake")
    effort = str(_config_get(llm_config, ("effort",), "") or "")
    return {
        "schema_version": RELATED_SECTIONS_STATE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "section_list_fingerprint": _section_list_fingerprint(sections),
        "section_hash_fingerprint": _section_hash_fingerprint(sections),
        "candidate_generation_config_fingerprint": _related_candidate_generation_config_fingerprint(config),
        "selection_prompt_version": related_sections_api.RELATED_SECTIONS_PROMPT_VERSION,
        "selection_model": model,
        "selection_provider": provider_id,
        "selection_effort": effort,
        "artifact_schema_version": RELATED_SECTIONS_ARTIFACT_SCHEMA_VERSION,
    }


def _retrieval_index_fast_path_decision(
    expected_state: Mapping[str, Any],
    *,
    store: ContextArtifactStore | None,
    url: str,
    collection: str,
    run_full: bool,
    force_full_recreate: bool,
    unchanged_sections: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if run_full or force_full_recreate:
        return {"can_skip": False, "reason": "full_rebuild"}
    if not unchanged_sections or not unchanged_sections.get("unchanged"):
        return {"can_skip": False, "reason": str((unchanged_sections or {}).get("reason") or "section_changed")}
    actual_state = _read_optional_artifact(store, "retrieval_index_state")
    if actual_state is None:
        return {"can_skip": False, "reason": "sidecar_missing"}
    mismatch = _state_mismatch(
        actual_state,
        expected_state,
        keys=(
            "schema_version",
            "collection_name",
            "section_count",
            "section_hash_fingerprint",
            "embedding_provider",
            "embedding_model",
            "dense_enabled",
            "sparse_enabled",
            "retrieval_schema_pin_fingerprint",
            "artifact_schema_version",
        ),
    )
    if mismatch:
        return {"can_skip": False, "reason": "fingerprint_mismatch", "field": mismatch}
    if not _section_collection_exists(url, collection):
        return {"can_skip": False, "reason": "collection_missing"}
    return {"can_skip": True, "reason": UNCHANGED_SECTION_REASON}


def _related_sections_fast_path_decision(
    expected_state: Mapping[str, Any],
    *,
    store: ContextArtifactStore | None,
    run_full: bool,
    unchanged_sections: Mapping[str, Any] | None,
    section_diff_sets: Mapping[str, Any] | None = None,
    retrieval_index_status: str,
) -> dict[str, Any]:
    del unchanged_sections  # section diff sets drive both no-change and partial paths.
    if run_full:
        return {"can_skip": False, "can_partial": False, "reason": "full_rebuild"}
    if retrieval_index_status not in {"success", "skipped_unchanged"}:
        return {"can_skip": False, "can_partial": False, "reason": f"retrieval_index_{retrieval_index_status or 'unknown'}"}
    actual_state = _read_optional_artifact(store, "related_sections_state")
    if actual_state is None:
        return {"can_skip": False, "can_partial": False, "reason": "sidecar_missing"}
    mismatch = _state_mismatch(
        actual_state,
        expected_state,
        keys=(
            "schema_version",
            "candidate_generation_config_fingerprint",
            "selection_prompt_version",
            "selection_model",
            "selection_provider",
            "selection_effort",
            "artifact_schema_version",
        ),
    )
    if mismatch:
        return {"can_skip": False, "can_partial": False, "reason": "fingerprint_mismatch", "field": mismatch}
    section_mismatch = _state_mismatch(
        actual_state,
        expected_state,
        keys=(
            "section_list_fingerprint",
            "section_hash_fingerprint",
        ),
    )
    if section_mismatch is None:
        return {
            "can_skip": True,
            "can_partial": False,
            "reason": UNCHANGED_SECTION_REASON,
        }
    if _has_section_diff(section_diff_sets):
        return {
            "can_skip": False,
            "can_partial": True,
            "reason": str((section_diff_sets or {}).get("reason") or section_mismatch),
            "field": section_mismatch,
        }
    return {
        "can_skip": False,
        "can_partial": False,
        "reason": "section_fingerprint_mismatch",
        "field": section_mismatch,
    }


def _has_section_diff(section_diff_sets: Mapping[str, Any] | None) -> bool:
    if not isinstance(section_diff_sets, Mapping):
        return False
    return any(
        section_diff_sets.get(key)
        for key in (
            "added_section_ids",
            "changed_section_ids",
            "removed_section_ids",
        )
    )


def _changed_or_added_section_ids(
    section_diff_sets: Mapping[str, Any] | None,
) -> list[str]:
    if not isinstance(section_diff_sets, Mapping):
        return []
    section_ids: list[str] = []
    for key in ("added_section_ids", "changed_section_ids"):
        values = section_diff_sets.get(key) or []
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            continue
        for section_id in values:
            value = str(section_id)
            if value and value not in section_ids:
                section_ids.append(value)
    return sorted(section_ids)


def _read_optional_artifact(
    store: ContextArtifactStore | None,
    artifact_name: str,
) -> dict[str, Any] | None:
    if store is None:
        return None
    try:
        return store.read(artifact_name)
    except Exception:
        return None


def _state_mismatch(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    keys: Sequence[str],
) -> str | None:
    for key in keys:
        if actual.get(key) != expected.get(key):
            return key
    return None


def _section_hash_fingerprint(sections: Sequence[Mapping[str, Any]]) -> str:
    parts = [
        "|".join(
            (
                str(section.get("source_section_id") or section.get("section_id") or ""),
                str(section.get("source_hash") or ""),
                str(section.get("semantic_hash") or ""),
            )
        )
        for section in sections
    ]
    return _hash_text("\n".join(sorted(parts)))


def _section_list_fingerprint(sections: Sequence[Mapping[str, Any]]) -> str:
    values = [
        str(section.get("source_section_id") or section.get("section_id") or "")
        for section in sections
    ]
    return _hash_text("\n".join(sorted(value for value in values if value)))


def _retrieval_schema_pin_fingerprint() -> str:
    payload = {
        "collection_schema_version": retrieval_index_api.QDRANT_COLLECTION_SCHEMA_VERSION,
        "collection_config": retrieval_index_api.qdrant_collection_config_metadata(),
        "dense_size": retrieval_index_api.BGE_M3_DENSE_SIZE,
        "dense_vector_name": retrieval_index_api.DENSE_VECTOR_NAME,
        "sparse_vector_name": retrieval_index_api.SPARSE_VECTOR_NAME,
        "fusion_method": retrieval_index_api.FUSION_METHOD,
        "point_id_scheme": "point_id_v1_uuid5_source_section_id",
    }
    return _hash_text(_stable_json(payload))


def _related_candidate_generation_config_fingerprint(config: Mapping[str, Any]) -> str:
    payload = {
        "candidate_channels": list(related_sections_api.MVP_CANDIDATE_CHANNELS),
        "retrieval": {
            "section_candidate_top_k": _config_get(config, ("retrieval", "section_candidate_top_k"), 16),
            "section_final_top_n": _config_get(config, ("retrieval", "section_final_top_n"), 8),
            "section_dense_threshold": _config_get(config, ("retrieval", "section_dense_threshold"), 0.55),
        },
        "limits": {
            "related_candidate_max_per_section": _config_get(config, ("limits", "related_candidate_max_per_section"), 32),
            "related_selected_max_per_section": _config_get(config, ("limits", "related_selected_max_per_section"), 8),
            "llm_batch_max_sections": _config_get(config, ("limits", "llm_batch_max_sections"), 8),
            "llm_batch_max_chars": _config_get(config, ("limits", "llm_batch_max_chars"), 12000),
        },
    }
    return _hash_text(_stable_json(payload))


def _config_bool(config: Mapping[str, Any], path: tuple[str, ...], default: bool) -> bool:
    value = _config_get(config, path, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _progress_action(
    progress_tracker: CoreProgressTracker | None,
    stage: str,
    *,
    action: str,
    reason: str,
    **fields: Any,
) -> None:
    if progress_tracker is None:
        return
    progress_tracker.update(stage, action=action, reason=reason, **fields)


def _generate_spec_claims_if_enabled(
    *,
    root: Path,
    config: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
    provider: Any,
    generated_at: str,
    context_dir: Path,
    run_full: bool,
    progress_tracker: CoreProgressTracker | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    diagnostics = _empty_spec_claims_diagnostics()
    if not _spec_claims_enabled(config):
        status = "success_no_claims"
        _record_spec_claims_progress(
            progress_tracker,
            status=status,
            diagnostics=diagnostics,
            calls=0,
            input_tokens=0,
            output_tokens=0,
            started=started,
            action="skipped_disabled",
            reason="spec_claims_disabled_by_config",
        )
        return {"status": status, "diagnostics": diagnostics}

    state_path = root / ".spec-anchor" / "state" / spec_claims_api.SPEC_CLAIMS_STATE_FILENAME
    jsonl_path = context_dir / spec_claims_api.SPEC_CLAIMS_JSONL_FILENAME
    model = str(_config_get(config, ("llm", "model"), "fake"))
    effort_value = _config_get(config, ("llm", "effort"), None)
    effort = str(effort_value) if effort_value is not None else None
    timeout_sec = _spec_claims_timeout_sec(config)
    max_claims_per_section = _spec_claims_max_claims_per_section(config)
    active_ids = [_spec_claim_section_id(section) for section in sections]
    active_id_set = set(active_ids)

    try:
        previous_state = spec_claims_api.read_spec_claims_state(state_path)
        previous_sections = previous_state.get("sections")
        if not isinstance(previous_sections, Mapping):
            previous_sections = {}
        changed_sections = [
            section
            for section in sections
            if run_full
            or not _spec_claim_state_entry_matches(
                previous_sections.get(_spec_claim_section_id(section)),
                section=section,
                model=model,
                effort=effort,
                max_claims_per_section=max_claims_per_section,
            )
        ]
        previous_active_ids = {
            str(section_id)
            for section_id in previous_sections
            if isinstance(section_id, str) and section_id
        }
        if not run_full and not changed_sections and previous_active_ids == active_id_set:
            diagnostics = _spec_claims_diagnostics_from_state(
                previous_sections,
                active_ids=active_ids,
            )
            status = "skipped_unchanged"
            _record_spec_claims_progress(
                progress_tracker,
                status=status,
                diagnostics=diagnostics,
                calls=0,
                input_tokens=0,
                output_tokens=0,
                started=started,
                action="skipped_unchanged",
                reason="input_and_config_fingerprint_match",
            )
            return {"status": status, "diagnostics": diagnostics}

        usage_provider = _SpecClaimUsageTrackingProvider(provider)
        generation = spec_claims_api.generate_spec_claims_result(
            changed_sections,
            provider=usage_provider,
            model=model,
            effort=effort,
            max_claims_per_section=max_claims_per_section,
            previous_state=previous_state,
            generated_at=generated_at,
            timeout_sec=timeout_sec,
        )
        generated_state_sections = generation.state.get("sections")
        if not isinstance(generated_state_sections, Mapping):
            generated_state_sections = {}
        merged_sections: dict[str, Any] = {}
        changed_ids = {_spec_claim_section_id(section) for section in changed_sections}
        for section in sections:
            section_id = _spec_claim_section_id(section)
            if section_id in changed_ids:
                entry = generated_state_sections.get(section_id)
            else:
                entry = previous_sections.get(section_id)
            if isinstance(entry, Mapping):
                merged_sections[section_id] = dict(entry)

        merged_state = {
            "schema_version": spec_claims_api.SPEC_CLAIM_SCHEMA_VERSION,
            "generated_at": generated_at,
            "sections": merged_sections,
        }
        all_claims = _spec_claims_from_state_sections(merged_sections, active_ids=active_ids)
        spec_claims_api.write_spec_claims_state(state_path, merged_state)
        spec_claims_api.write_spec_claims_jsonl(
            jsonl_path,
            all_claims,
            active_source_section_ids=active_ids,
        )
        diagnostics = _spec_claims_diagnostics_from_state(
            merged_sections,
            active_ids=active_ids,
        )
        status = _spec_claims_status_from_diagnostics(diagnostics, active_ids=active_ids)
        usage = usage_provider.usage_totals
        _record_spec_claims_progress(
            progress_tracker,
            status=status,
            diagnostics=diagnostics,
            calls=generation.llm_calls,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            started=started,
            action="generated" if run_full else "regenerated_partial",
            reason="full_rebuild" if run_full else "section_changed",
            changed_source_section_ids=sorted(changed_ids),
        )
        return {"status": status, "diagnostics": diagnostics}
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        diagnostics = {
            **diagnostics,
            "failed_spec_claim_sections": sorted(active_id_set),
            "failure": {
                "reason_code": "spec_claims_generation_failed",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            },
        }
        _record_spec_claims_progress(
            progress_tracker,
            status=status,
            diagnostics=diagnostics,
            calls=0,
            input_tokens=0,
            output_tokens=0,
            started=started,
            action="failed",
            reason="spec_claims_generation_failed",
        )
        return {"status": status, "diagnostics": diagnostics}


class _CountingClaimRetrievalBackend:
    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.search_count = 0

    def dense_search(self, query: str, top_k: int) -> Sequence[Any]:
        self.search_count += 1
        return self.delegate.dense_search(query, top_k)

    def sparse_search(self, query: str, top_k: int) -> Sequence[Any]:
        self.search_count += 1
        return self.delegate.sparse_search(query, top_k)


class _NoopClaimRetrievalBackend:
    def dense_search(self, query: str, top_k: int) -> Sequence[Any]:
        return []

    def sparse_search(self, query: str, top_k: int) -> Sequence[Any]:
        return []


def _generate_claim_retrieval_if_enabled(
    *,
    root: Path,
    config: Mapping[str, Any],
    spec_claims_status: str,
    spec_claims_diagnostics: Mapping[str, Any],
    generated_at: str,
    context_dir: Path,
    run_full: bool,
    progress_tracker: CoreProgressTracker | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    diagnostics = _empty_claim_retrieval_diagnostics()
    if not _claim_retrieval_enabled(config):
        status = "success_no_candidates"
        _record_claim_retrieval_progress(
            progress_tracker,
            status=status,
            diagnostics=diagnostics,
            started=started,
            action="skipped_disabled",
            reason="conflict_candidate_detection_disabled_by_config",
            qdrant_upsert_count=0,
            qdrant_search_count=0,
        )
        return {"status": status, "diagnostics": diagnostics}

    state_path = (
        root
        / ".spec-anchor"
        / "state"
        / claim_retrieval_api.CONFLICT_CANDIDATE_PAIRS_STATE_FILENAME
    )
    candidate_path = context_dir / claim_retrieval_api.CONFLICT_CANDIDATE_PAIRS_JSONL_FILENAME
    spec_claims_path = context_dir / spec_claims_api.SPEC_CLAIMS_JSONL_FILENAME
    retrieval_config = _claim_retrieval_config(config)

    try:
        claims = _read_jsonl_records(spec_claims_path)
        previous_state = claim_retrieval_api.read_conflict_candidate_pairs_state(
            state_path
        )
        previous_retrieval_state = _claim_retrieval_state(previous_state)
        if _claim_retrieval_state_matches(
            previous_retrieval_state,
            claims=claims,
            config=retrieval_config,
            run_full=run_full,
            candidate_path=candidate_path,
        ):
            previous_candidates = claim_retrieval_api.read_conflict_candidate_pairs_jsonl(
                candidate_path
            )
            diagnostics = _claim_retrieval_diagnostics(
                {
                    "candidate_count": len(
                        previous_retrieval_state.get("candidate_uids") or []
                    ),
                    "truncated_candidate_sources": previous_retrieval_state.get(
                        "truncated_candidate_sources"
                    )
                    or [],
                    "truncated_pair_count": previous_retrieval_state.get(
                        "truncated_pair_count"
                    )
                    or 0,
                },
                previous_candidates,
            )
            status = "skipped_unchanged"
            _record_claim_retrieval_progress(
                progress_tracker,
                status=status,
                diagnostics=diagnostics,
                started=started,
                action="skipped_unchanged",
                reason="input_and_config_fingerprint_match",
                qdrant_upsert_count=0,
                qdrant_search_count=0,
            )
            return {"status": status, "diagnostics": diagnostics}

        plan = _claim_retrieval_incremental_plan(
            claims,
            previous_retrieval_state=previous_retrieval_state,
            config=retrieval_config,
            run_full=run_full,
        )
        qdrant_upsert_count = 0
        qdrant_delete_count = 0
        qdrant_search_count = 0
        qdrant_enabled = _claim_retrieval_qdrant_enabled(config)
        backend: Any
        if qdrant_enabled and (
            claims or plan["deleted_claim_uids"] or plan["claims_to_upsert"]
        ):
            upsert_info = claim_retrieval_api.upsert_qdrant_claim_collection(
                claims,
                url=str(
                    _config_get(
                        config,
                        ("vector_store", "url"),
                        "http://localhost:6333",
                    )
                    or "http://localhost:6333"
                ),
                collection=retrieval_config.claim_collection,
                recreate=bool(plan["recreate"]),
                claims_to_upsert=plan["claims_to_upsert"],
                claims_to_delete=plan["deleted_claim_uids"],
            )
            qdrant_upsert_count = int(upsert_info.get("claims_upserted_count") or 0)
            qdrant_delete_count = int(upsert_info.get("claims_deleted_count") or 0)
        if qdrant_enabled and plan["seed_claim_uids"]:
            backend = _CountingClaimRetrievalBackend(
                claim_retrieval_api.QdrantClaimRetriever(
                    url=str(
                        _config_get(
                            config,
                            ("vector_store", "url"),
                            "http://localhost:6333",
                        )
                        or "http://localhost:6333"
                    ),
                    collection=retrieval_config.claim_collection,
                )
            )
        elif qdrant_enabled:
            backend = _CountingClaimRetrievalBackend(_NoopClaimRetrievalBackend())
        else:
            backend = claim_retrieval_api.InMemoryClaimRetrievalBackend(
                claims,
                dense_enabled=_config_bool(config, ("embedding", "dense_enabled"), True),
                sparse_enabled=_config_bool(config, ("embedding", "sparse_enabled"), True),
            )
        result = claim_retrieval_api.generate_claim_retrieval_result(
            claims,
            seed_claim_uids=plan["seed_claim_uids"],
            backend=backend,
            config=retrieval_config,
            previous_state=previous_state,
            output_path=candidate_path,
            state_path=state_path,
            generated_at=generated_at,
        )
        if isinstance(backend, _CountingClaimRetrievalBackend):
            qdrant_search_count = backend.search_count
        diagnostics = _claim_retrieval_diagnostics(
            result.diagnostics,
            result.candidates,
        )
        diagnostics["qdrant_delete_count"] = qdrant_delete_count
        diagnostics["changed_or_added_claim_count"] = len(plan["seed_claim_uids"])
        diagnostics["deleted_claim_count"] = len(plan["deleted_claim_uids"])
        status = _claim_retrieval_status_from_diagnostics(
            diagnostics,
            spec_claims_status=spec_claims_status,
            spec_claims_diagnostics=spec_claims_diagnostics,
        )
        _record_claim_retrieval_progress(
            progress_tracker,
            status=status,
            diagnostics=diagnostics,
            started=started,
            action="generated" if run_full else "regenerated_partial",
            reason="full_rebuild" if run_full else str(plan["reason"]),
            qdrant_upsert_count=qdrant_upsert_count,
            qdrant_search_count=qdrant_search_count,
            qdrant_delete_count=qdrant_delete_count,
        )
        return {"status": status, "diagnostics": diagnostics}
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        diagnostics = {
            **diagnostics,
            "failure": {
                "reason_code": "claim_retrieval_generation_failed",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            },
        }
        _record_claim_retrieval_progress(
            progress_tracker,
            status=status,
            diagnostics=diagnostics,
            started=started,
            action="failed",
            reason="claim_retrieval_generation_failed",
            qdrant_upsert_count=0,
            qdrant_search_count=0,
        )
        return {"status": status, "diagnostics": diagnostics}


def _generate_conflict_candidate_triage_if_enabled(
    *,
    root: Path,
    config: Mapping[str, Any],
    spec_claims_status: str,
    claim_retrieval_status: str,
    generated_at: str,
    context_dir: Path,
    cache_dir: Path,
    provider: Any,
    run_full: bool,
    progress_tracker: CoreProgressTracker | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    diagnostics = _empty_conflict_candidate_triage_diagnostics()
    if not _claim_retrieval_enabled(config):
        status = "success_no_triage"
        _record_conflict_candidate_triage_progress(
            progress_tracker,
            status=status,
            diagnostics=diagnostics,
            started=started,
            action="skipped_disabled",
            reason="conflict_candidate_detection_disabled_by_config",
            llm_calls=0,
            cache_hits=0,
            input_tokens=0,
            output_tokens=0,
        )
        return {"status": status, "diagnostics": diagnostics}

    state_path = (
        root
        / ".spec-anchor"
        / "state"
        / claim_retrieval_api.CONFLICT_CANDIDATE_PAIRS_STATE_FILENAME
    )
    candidate_path = context_dir / claim_retrieval_api.CONFLICT_CANDIDATE_PAIRS_JSONL_FILENAME
    spec_claims_path = context_dir / spec_claims_api.SPEC_CLAIMS_JSONL_FILENAME
    model = str(_config_get(config, ("llm", "model"), "fake"))
    effort_value = _config_get(config, ("llm", "effort"), None)
    effort = str(effort_value) if effort_value is not None else None
    timeout_sec = _spec_claims_timeout_sec(config)
    triage_max_pairs = _conflict_candidate_triage_max_pairs(config)

    try:
        previous_state = conflict_candidates_api.read_conflict_candidate_pairs_state(
            state_path
        )
        triage_state = _conflict_candidate_triage_state(previous_state)
        if claim_retrieval_status == "failed":
            status = "failed"
            diagnostics = {
                **diagnostics,
                "failure": {
                    "reason_code": "claim_retrieval_failed",
                    "message": "Claim Retrieval failed; conflict candidate triage was not run.",
                },
            }
            _record_conflict_candidate_triage_progress(
                progress_tracker,
                status=status,
                diagnostics=diagnostics,
                started=started,
                action="blocked_by_claim_retrieval",
                reason="claim_retrieval_failed",
                llm_calls=0,
                cache_hits=0,
                input_tokens=0,
                output_tokens=0,
            )
            return {"status": status, "diagnostics": diagnostics}

        if _conflict_candidate_triage_state_matches(
            triage_state,
            spec_claims_status=spec_claims_status,
            claim_retrieval_status=claim_retrieval_status,
            model=model,
            effort=effort,
            triage_max_pairs=triage_max_pairs,
            run_full=run_full,
            candidate_path=candidate_path,
        ):
            diagnostics = _conflict_candidate_triage_diagnostics_from_state(
                triage_state
            )
            status = "skipped_unchanged"
            _record_conflict_candidate_triage_progress(
                progress_tracker,
                status=status,
                diagnostics=diagnostics,
                started=started,
                action="skipped_unchanged",
                reason="input_and_config_fingerprint_match",
                llm_calls=0,
                cache_hits=int(triage_state.get("cache_hits") or 0),
                input_tokens=0,
                output_tokens=0,
            )
            return {"status": status, "diagnostics": diagnostics}

        candidates = conflict_candidates_api.read_conflict_candidate_pairs_jsonl(
            candidate_path
        )
        claims = _read_jsonl_records(spec_claims_path)
        usage_provider = _SpecClaimUsageTrackingProvider(provider)
        result = conflict_candidates_api.generate_conflict_candidate_triage_result(
            candidates,
            claims,
            provider=usage_provider,
            model=model,
            effort=effort,
            triage_max_pairs=triage_max_pairs,
            cache_dir=cache_dir,
            output_path=candidate_path,
            state_path=state_path,
            previous_state=previous_state,
            generated_at=generated_at,
            timeout_sec=timeout_sec,
        )
        diagnostics = _conflict_candidate_triage_diagnostics(result.diagnostics)
        status = (
            "success_no_triage"
            if not candidates and result.status == "success"
            else str(result.status)
        )
        usage = usage_provider.usage_totals
        _record_conflict_candidate_triage_progress(
            progress_tracker,
            status=status,
            diagnostics=diagnostics,
            started=started,
            action="skipped_no_candidates" if not candidates else "generated",
            reason="no_candidate_pairs" if not candidates else "candidate_pairs_available",
            llm_calls=result.llm_calls,
            cache_hits=result.cache_hits,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
        )
        return {"status": status, "diagnostics": diagnostics}
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        diagnostics = {
            **diagnostics,
            "failure": {
                "reason_code": "conflict_candidate_triage_generation_failed",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            },
        }
        _record_conflict_candidate_triage_progress(
            progress_tracker,
            status=status,
            diagnostics=diagnostics,
            started=started,
            action="failed",
            reason="conflict_candidate_triage_generation_failed",
            llm_calls=0,
            cache_hits=0,
            input_tokens=0,
            output_tokens=0,
        )
        return {"status": status, "diagnostics": diagnostics}


def _claim_retrieval_config(
    config: Mapping[str, Any],
) -> claim_retrieval_api.ClaimRetrievalConfig:
    return claim_retrieval_api.ClaimRetrievalConfig(
        claim_collection=str(
            _config_get(
                config,
                ("retrieval", "claim_collection"),
                claim_retrieval_api.DEFAULT_CLAIM_COLLECTION,
            )
            or claim_retrieval_api.DEFAULT_CLAIM_COLLECTION
        ),
        dense_top_k=_config_int(config, ("retrieval", "dense_top_k"), 12),
        sparse_top_k=_config_int(config, ("retrieval", "sparse_top_k"), 20),
        per_claim_top_k=_config_int(
            config,
            ("conflict_candidate_detection", "per_claim_top_k"),
            10,
        ),
        per_section_top_k=_config_int(
            config,
            ("conflict_candidate_detection", "per_section_top_k"),
            20,
        ),
        per_target_top_k=_config_int(
            config,
            ("conflict_candidate_detection", "per_target_top_k"),
            20,
        ),
        global_candidate_top_k=_config_int(
            config,
            ("conflict_candidate_detection", "global_candidate_top_k"),
            100,
        ),
        min_dense_score=_config_float(
            config,
            ("conflict_candidate_detection", "min_dense_score"),
            0.55,
        ),
        min_sparse_score=_config_float(
            config,
            ("conflict_candidate_detection", "min_sparse_score"),
            0.0,
        ),
        rank_fusion=str(
            _config_get(
                config,
                ("conflict_candidate_detection", "rank_fusion"),
                "rrf",
            )
            or "rrf"
        ),
        allow_same_section_claim_pair=_config_bool(
            config,
            ("conflict_candidate_detection", "allow_same_section_claim_pair"),
            True,
        ),
        allow_same_source_file_claim_pair=_config_bool(
            config,
            ("conflict_candidate_detection", "allow_same_source_file_claim_pair"),
            True,
        ),
    )


def _claim_retrieval_enabled(config: Mapping[str, Any]) -> bool:
    return _config_bool(config, ("conflict_candidate_detection", "enabled"), True)


def _claim_retrieval_qdrant_enabled(config: Mapping[str, Any]) -> bool:
    return (
        str(_config_get(config, ("embedding", "provider"), "")) == "flagembedding"
        and str(_config_get(config, ("vector_store", "provider"), "")) == "qdrant"
    )


def _claim_retrieval_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    retrieval = state.get("retrieval") if isinstance(state, Mapping) else None
    return dict(retrieval or {})


def _claim_retrieval_state_matches(
    retrieval_state: Mapping[str, Any],
    *,
    claims: Sequence[Mapping[str, Any]],
    config: claim_retrieval_api.ClaimRetrievalConfig,
    run_full: bool,
    candidate_path: Path,
) -> bool:
    if run_full or not candidate_path.is_file():
        return False
    return (
        str(retrieval_state.get("schema_version") or "")
        == claim_retrieval_api.CLAIM_RETRIEVAL_SCHEMA_VERSION
        and str(retrieval_state.get("spec_claims_fingerprint") or "")
        == claim_retrieval_api.spec_claims_fingerprint(claims)
        and str(retrieval_state.get("claim_retrieval_config_fingerprint") or "")
        == config.fingerprint()
    )


def _claim_retrieval_incremental_plan(
    claims: Sequence[Mapping[str, Any]],
    *,
    previous_retrieval_state: Mapping[str, Any],
    config: claim_retrieval_api.ClaimRetrievalConfig,
    run_full: bool,
) -> dict[str, Any]:
    current_by_uid = {
        str(claim.get("claim_uid") or ""): dict(claim)
        for claim in claims
        if str(claim.get("claim_uid") or "")
    }
    previous_claim_hash_by_uid = dict(
        previous_retrieval_state.get("claim_hash_by_uid") or {}
    )
    previous_retrieval_hash_by_uid = dict(
        previous_retrieval_state.get("retrieval_hash_by_uid") or {}
    )
    previous_uids = set(previous_claim_hash_by_uid) | set(previous_retrieval_hash_by_uid)
    current_uids = set(current_by_uid)
    deleted_uids = sorted(previous_uids - current_uids)
    config_mismatch = (
        str(previous_retrieval_state.get("schema_version") or "")
        != claim_retrieval_api.CLAIM_RETRIEVAL_SCHEMA_VERSION
        or str(previous_retrieval_state.get("claim_retrieval_config_fingerprint") or "")
        != config.fingerprint()
    )
    force_all = run_full or not previous_retrieval_state or config_mismatch
    if force_all:
        seed_uids = sorted(current_uids)
        claims_to_upsert = [current_by_uid[uid] for uid in seed_uids]
        reason = "full_rebuild" if run_full else "fingerprint_mismatch"
    else:
        seed_uids = sorted(
            uid
            for uid, claim in current_by_uid.items()
            if previous_claim_hash_by_uid.get(uid) != str(claim.get("claim_hash") or "")
            or previous_retrieval_hash_by_uid.get(uid)
            != str(claim.get("retrieval_hash") or "")
        )
        claims_to_upsert = [current_by_uid[uid] for uid in seed_uids]
        reason = "claim_changed" if seed_uids else "claim_deleted"
    return {
        "seed_claim_uids": seed_uids,
        "claims_to_upsert": claims_to_upsert,
        "deleted_claim_uids": deleted_uids,
        "recreate": bool(force_all and current_uids),
        "reason": reason,
    }


def _empty_claim_retrieval_diagnostics() -> dict[str, Any]:
    return {
        "candidate_count": 0,
        "truncated_candidate_sources": [],
        "truncated_pair_count": 0,
        "same_section_pair_count": 0,
    }


def _claim_retrieval_diagnostics(
    raw_diagnostics: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    diagnostics = _empty_claim_retrieval_diagnostics()
    diagnostics["candidate_count"] = int(raw_diagnostics.get("candidate_count") or 0)
    diagnostics["truncated_candidate_sources"] = _list_of_strings(
        raw_diagnostics.get("truncated_candidate_sources")
    )
    diagnostics["truncated_pair_count"] = int(
        raw_diagnostics.get("truncated_pair_count") or 0
    )
    diagnostics["same_section_pair_count"] = sum(
        1
        for candidate in candidates
        if str(candidate.get("left_section_uid") or "")
        and str(candidate.get("left_section_uid") or "")
        == str(candidate.get("right_section_uid") or "")
    )
    return diagnostics


def _claim_retrieval_status_from_diagnostics(
    diagnostics: Mapping[str, Any],
    *,
    spec_claims_status: str,
    spec_claims_diagnostics: Mapping[str, Any],
) -> str:
    failed_sections = list(
        spec_claims_diagnostics.get("failed_spec_claim_sections") or []
    )
    if spec_claims_status == "failed" and failed_sections:
        return "failed"
    if failed_sections:
        return "partial_success"
    if int(diagnostics.get("candidate_count") or 0) > 0:
        return "success"
    return "success_no_candidates"


def _record_claim_retrieval_progress(
    progress_tracker: CoreProgressTracker | None,
    *,
    status: str,
    diagnostics: Mapping[str, Any],
    started: float,
    action: str,
    reason: str,
    qdrant_upsert_count: int,
    qdrant_search_count: int,
    qdrant_delete_count: int = 0,
) -> None:
    if progress_tracker is None:
        return
    progress_tracker.update(
        "claim_retrieval",
        action=action,
        reason=reason,
        status=status,
        diagnostics=dict(diagnostics),
        wall=round(time.monotonic() - started, 3),
        qdrant_upsert_count=int(qdrant_upsert_count),
        qdrant_search_count=int(qdrant_search_count),
        qdrant_delete_count=int(qdrant_delete_count),
    )


def _conflict_candidate_triage_max_pairs(config: Mapping[str, Any]) -> int:
    return _config_int(config, ("conflict_candidate_detection", "triage_max_pairs"), 30)


def _conflict_candidate_triage_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    triage = state.get("triage") if isinstance(state, Mapping) else None
    return dict(triage or {})


def _conflict_candidate_triage_state_matches(
    triage_state: Mapping[str, Any],
    *,
    spec_claims_status: str,
    claim_retrieval_status: str,
    model: str,
    effort: str | None,
    triage_max_pairs: int,
    run_full: bool,
    candidate_path: Path,
) -> bool:
    if (
        run_full
        or not candidate_path.is_file()
        or spec_claims_status != "skipped_unchanged"
        or claim_retrieval_status != "skipped_unchanged"
    ):
        return False
    settings = {
        "prompt_version": conflict_candidates_api.CONFLICT_TRIAGE_PROMPT_VERSION,
        "schema_version": conflict_candidates_api.CONFLICT_CANDIDATE_SCHEMA_VERSION,
        "model": model,
        "effort": effort,
        "triage_max_pairs": max(0, int(triage_max_pairs)),
    }
    expected_fingerprint = "sha256:" + hashlib.sha256(
        json.dumps(settings, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return (
        str(triage_state.get("schema_version") or "")
        == conflict_candidates_api.CONFLICT_CANDIDATE_SCHEMA_VERSION
        and str(triage_state.get("prompt_version") or "")
        == conflict_candidates_api.CONFLICT_TRIAGE_PROMPT_VERSION
        and str(triage_state.get("model") or "") == model
        and triage_state.get("effort") == effort
        and int(triage_state.get("triage_max_pairs") or 0)
        == max(0, int(triage_max_pairs))
        and str(triage_state.get("triage_settings_fingerprint") or "")
        == expected_fingerprint
    )


def _empty_conflict_candidate_triage_diagnostics() -> dict[str, Any]:
    return {
        "send_to_review_count": 0,
        "send_to_review_false_count": 0,
        "triage_truncated_pairs": 0,
    }


def _conflict_candidate_triage_diagnostics(
    raw_diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    diagnostics = _empty_conflict_candidate_triage_diagnostics()
    diagnostics["send_to_review_count"] = int(
        raw_diagnostics.get("send_to_review_count") or 0
    )
    diagnostics["send_to_review_false_count"] = int(
        raw_diagnostics.get("send_to_review_false_count") or 0
    )
    diagnostics["triage_truncated_pairs"] = int(
        raw_diagnostics.get("triage_truncated_pairs") or 0
    )
    for key in (
        "candidate_count",
        "processed_candidate_count",
        "failed_candidate_count",
        "failed_candidate_uids",
        "cache_hits",
        "llm_calls",
        "diagnostics",
        "failure",
    ):
        if key in raw_diagnostics:
            diagnostics[key] = raw_diagnostics[key]
    return diagnostics


def _conflict_candidate_triage_diagnostics_from_state(
    triage_state: Mapping[str, Any],
) -> dict[str, Any]:
    diagnostics = _empty_conflict_candidate_triage_diagnostics()
    diagnostics["send_to_review_count"] = int(
        triage_state.get("send_to_review_count") or 0
    )
    diagnostics["send_to_review_false_count"] = int(
        triage_state.get("send_to_review_false_count") or 0
    )
    diagnostics["triage_truncated_pairs"] = int(
        triage_state.get("triage_truncated_pairs") or 0
    )
    diagnostics["cache_hits"] = int(triage_state.get("cache_hits") or 0)
    diagnostics["llm_calls"] = 0
    return diagnostics


def _record_conflict_candidate_triage_progress(
    progress_tracker: CoreProgressTracker | None,
    *,
    status: str,
    diagnostics: Mapping[str, Any],
    started: float,
    action: str,
    reason: str,
    llm_calls: int,
    cache_hits: int,
    input_tokens: int,
    output_tokens: int,
) -> None:
    if progress_tracker is None:
        return
    progress_tracker.update(
        "conflict_candidate_triage",
        action=action,
        reason=reason,
        status=status,
        diagnostics=dict(diagnostics),
        wall=round(time.monotonic() - started, 3),
        llm_calls=int(llm_calls),
        cache_hits=int(cache_hits),
        token_count=int(input_tokens) + int(output_tokens),
        usage={
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
        },
    )


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, Mapping):
            records.append(dict(value))
    return records


def _config_int(config: Mapping[str, Any], path: tuple[str, ...], default: int) -> int:
    value = _config_get(config, path, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _config_float(
    config: Mapping[str, Any],
    path: tuple[str, ...],
    default: float,
) -> float:
    value = _config_get(config, path, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class _SpecClaimUsageTrackingProvider:
    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.usage_totals: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    @property
    def provider_id(self) -> str:
        return str(getattr(self.delegate, "provider_id", "spec-claim-provider"))

    def generate(self, request: Any, *, timeout_sec: int) -> Any:
        output = self.delegate.generate(request, timeout_sec=timeout_sec)
        if isinstance(output, dict):
            clean = dict(output)
            usage = clean.pop(llm_provider_api.USAGE_META_KEY, {}) or {}
            if isinstance(usage, Mapping):
                self.usage_totals["input_tokens"] += int(usage.get("input_tokens") or 0)
                self.usage_totals["output_tokens"] += int(usage.get("output_tokens") or 0)
            return clean
        return output


def _spec_claims_enabled(config: Mapping[str, Any]) -> bool:
    return bool(
        _config_bool(config, ("section_metadata", "enabled"), True)
        or _config_bool(config, ("conflict_candidate_detection", "enabled"), True)
    )


def _spec_claims_timeout_sec(config: Mapping[str, Any]) -> int:
    value = _config_get(config, ("llm", "timeout_sec"), 120)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 120


def _spec_claims_max_claims_per_section(config: Mapping[str, Any]) -> int:
    value = _config_get(
        config,
        ("spec_claims", "max_claims_per_section"),
        _config_get(config, ("limits", "spec_claims_max_per_section"), 20),
    )
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 20


def _spec_claim_section_id(section: Mapping[str, Any]) -> str:
    return str(section.get("source_section_id") or section.get("section_id") or "")


def _spec_claim_state_entry_matches(
    entry: Any,
    *,
    section: Mapping[str, Any],
    model: str,
    effort: str | None,
    max_claims_per_section: int,
) -> bool:
    if not isinstance(entry, Mapping):
        return False
    section_id = _spec_claim_section_id(section)
    source_hash = str(section.get("source_hash") or "")
    semantic_hash = str(section.get("semantic_hash") or source_hash)
    expected_cache_key = spec_claims_api.compute_spec_claim_cache_key(
        source_section_id=section_id,
        source_hash=source_hash,
        semantic_hash=semantic_hash,
        model=model,
        effort=effort,
    )
    return (
        entry.get("source_hash") == source_hash
        and entry.get("semantic_hash") == semantic_hash
        and entry.get("prompt_version") == spec_claims_api.SPEC_CLAIM_PROMPT_VERSION
        and entry.get("schema_version") == spec_claims_api.SPEC_CLAIM_SCHEMA_VERSION
        and entry.get("cache_key") == expected_cache_key
        and entry.get("model") == model
        and entry.get("effort") == effort
        and entry.get("max_claims_per_section") == max_claims_per_section
        and isinstance(entry.get("claims"), list)
        and entry.get("status")
        in {spec_claims_api.SUCCESS_WITH_CLAIMS, spec_claims_api.SUCCESS_NO_CLAIMS}
    )


def _empty_spec_claims_diagnostics() -> dict[str, Any]:
    return {
        "success_with_claims_count": 0,
        "success_no_claims_count": 0,
        "failed_spec_claim_sections": [],
        "claim_limit_reached_sections": [],
    }


def _spec_claims_diagnostics_from_state(
    state_sections: Mapping[str, Any],
    *,
    active_ids: Sequence[str],
) -> dict[str, Any]:
    diagnostics = _empty_spec_claims_diagnostics()
    failed: list[str] = []
    limited: list[str] = []
    for section_id in active_ids:
        entry = state_sections.get(section_id)
        if not isinstance(entry, Mapping):
            failed.append(section_id)
            continue
        status = str(entry.get("status") or "")
        if status == spec_claims_api.SUCCESS_WITH_CLAIMS:
            diagnostics["success_with_claims_count"] += 1
        elif status == spec_claims_api.SUCCESS_NO_CLAIMS:
            diagnostics["success_no_claims_count"] += 1
        else:
            failed.append(section_id)
        if entry.get("limit_reached"):
            limited.append(section_id)
    diagnostics["failed_spec_claim_sections"] = sorted(failed)
    diagnostics["claim_limit_reached_sections"] = sorted(limited)
    return diagnostics


def _spec_claims_status_from_diagnostics(
    diagnostics: Mapping[str, Any],
    *,
    active_ids: Sequence[str],
) -> str:
    failed = list(diagnostics.get("failed_spec_claim_sections") or [])
    if active_ids and len(failed) == len(active_ids):
        return "failed"
    if failed:
        return "partial_success"
    if int(diagnostics.get("success_with_claims_count") or 0) > 0:
        return "success"
    return "success_no_claims"


def _spec_claims_from_state_sections(
    state_sections: Mapping[str, Any],
    *,
    active_ids: Sequence[str],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for section_id in active_ids:
        entry = state_sections.get(section_id)
        if not isinstance(entry, Mapping):
            continue
        entry_claims = entry.get("claims")
        if not isinstance(entry_claims, Sequence) or isinstance(entry_claims, (str, bytes)):
            continue
        claims.extend(dict(claim) for claim in entry_claims if isinstance(claim, Mapping))
    return claims


def _record_spec_claims_progress(
    progress_tracker: CoreProgressTracker | None,
    *,
    status: str,
    diagnostics: Mapping[str, Any],
    calls: int,
    input_tokens: int,
    output_tokens: int,
    started: float,
    action: str,
    reason: str,
    changed_source_section_ids: Sequence[str] | None = None,
) -> None:
    if progress_tracker is None:
        return
    progress_tracker.increment(
        "spec_claims",
        llm_calls=calls,
        token_count=input_tokens + output_tokens,
    )
    fields: dict[str, Any] = {
        "action": action,
        "reason": reason,
        "status": status,
        "diagnostics": dict(diagnostics),
        "calls": int(calls),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "wall_sec": round(time.monotonic() - started, 3),
    }
    if changed_source_section_ids is not None:
        fields["changed_source_section_ids"] = list(changed_source_section_ids)
    progress_tracker.update("spec_claims", **fields)


_VERIFY_INDEX_FIELDS = (
    "source_hash",
    "semantic_hash",
    "vector_input_fingerprint",
    "payload_fingerprint",
)


class _SectionPayloadScrollError(RuntimeError):
    """Raised when Qdrant payload scroll cannot complete for explicit verify."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _verify_section_collection_if_requested(
    *,
    config: Mapping[str, Any],
    section_manifest: Mapping[str, Any],
    retrieval_index_status: str,
    verify_index: bool,
    force_full_recreate: bool = False,
    section_collection_upsert_info: Mapping[str, Any] | None = None,
    progress_tracker: CoreProgressTracker | None = None,
) -> tuple[str, dict[str, Any]]:
    """Verify Qdrant section payloads against the current manifest contract."""

    if not verify_index:
        diagnostics = {"executed": False, "reason": "not_requested"}
        _progress_action(
            progress_tracker,
            "verify_index",
            action="disabled",
            reason="not_requested",
            diagnostics=diagnostics,
        )
        return retrieval_index_status, diagnostics

    embedding_provider = str(_config_get(config, ("embedding", "provider"), ""))
    vector_store_provider = str(_config_get(config, ("vector_store", "provider"), ""))
    if embedding_provider != "flagembedding" or vector_store_provider != "qdrant":
        diagnostics = {"executed": False, "reason": "disabled"}
        _progress_action(
            progress_tracker,
            "verify_index",
            action="disabled",
            reason="disabled",
            diagnostics=diagnostics,
        )
        return retrieval_index_status, diagnostics

    if retrieval_index_status in {"failed", "blocked", "skipped"}:
        diagnostics = {
            "executed": False,
            "reason": "skipped",
            "retrieval_index_status": retrieval_index_status,
        }
        _progress_action(
            progress_tracker,
            "verify_index",
            action="skipped",
            reason=f"retrieval_index_{retrieval_index_status}",
            diagnostics=diagnostics,
        )
        return retrieval_index_status, diagnostics

    upsert_info = dict(section_collection_upsert_info or {})
    already_recreated = bool(
        force_full_recreate
        or upsert_info.get("action") == "upserted_full"
        or upsert_info.get("recreate") is True
    )
    if already_recreated:
        diagnostics = {"executed": False, "reason": "already_recreated"}
        _progress_action(
            progress_tracker,
            "verify_index",
            action="skipped",
            reason="already_recreated",
            diagnostics=diagnostics,
        )
        return retrieval_index_status, diagnostics

    try:
        payloads = _scroll_section_payloads_from_qdrant(config)
        diagnostics = _verify_index_payloads(section_manifest, payloads)
    except _SectionPayloadScrollError as exc:
        diagnostics = {
            "executed": True,
            "checked_count": 0,
            "stale_point_count": 0,
            "missing_point_count": 0,
            "hash_mismatch_count": 0,
            "issues": [
                {
                    "section_id": "<collection>",
                    "reason_code": exc.reason_code,
                    "fields": [],
                    "message": str(exc),
                }
            ],
        }

    if _verify_index_has_issues(diagnostics):
        reason = _dominant_verify_index_reason(diagnostics)
        _progress_action(
            progress_tracker,
            "verify_index",
            action="verified_inconsistent",
            reason=reason,
            diagnostics=diagnostics,
        )
        return "failed", diagnostics

    _progress_action(
        progress_tracker,
        "verify_index",
        action="verified_clean",
        reason="clean",
        diagnostics=diagnostics,
    )
    return retrieval_index_status, diagnostics


def _verify_index_payloads(
    section_manifest: Mapping[str, Any],
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected = _verify_index_expected_map(section_manifest)
    actual_ids: set[str] = set()
    issues: list[dict[str, Any]] = []
    stale_point_count = 0
    hash_mismatch_count = 0

    for payload in payloads:
        section_id = str(payload.get("source_section_id") or "")
        if not section_id:
            stale_point_count += 1
            issues.append(
                {
                    "section_id": "<missing>",
                    "reason_code": "stale_point",
                    "fields": [],
                }
            )
            continue
        actual_ids.add(section_id)
        expected_entry = expected.get(section_id)
        if expected_entry is None:
            stale_point_count += 1
            issues.append(
                {
                    "section_id": section_id,
                    "reason_code": "stale_point",
                    "fields": [],
                }
            )
            continue
        payload_fingerprints = retrieval_index_api.section_payload_fingerprints(payload)
        actual_entry = {
            "source_hash": str(payload.get("source_hash") or ""),
            "semantic_hash": str(payload.get("semantic_hash") or ""),
            "vector_input_fingerprint": str(payload_fingerprints.get("vector_input_fingerprint") or ""),
            "payload_fingerprint": str(payload_fingerprints.get("payload_fingerprint") or ""),
        }
        mismatched_fields = [
            field
            for field in _VERIFY_INDEX_FIELDS[:-1]
            if actual_entry.get(field) != expected_entry.get(field)
        ]
        if (
            not mismatched_fields
            and actual_entry.get("payload_fingerprint")
            != expected_entry.get("payload_fingerprint")
        ):
            mismatched_fields.append("payload_fingerprint")
        if mismatched_fields:
            hash_mismatch_count += 1
            issues.append(
                {
                    "section_id": section_id,
                    "reason_code": "hash_mismatch",
                    "fields": mismatched_fields,
                }
            )

    missing_ids = sorted(set(expected) - actual_ids)
    for section_id in missing_ids:
        issues.append(
            {
                "section_id": section_id,
                "reason_code": "missing_point",
                "fields": [],
            }
        )

    return {
        "executed": True,
        "checked_count": len(payloads),
        "stale_point_count": stale_point_count,
        "missing_point_count": len(missing_ids),
        "hash_mismatch_count": hash_mismatch_count,
        "issues": issues,
    }


def _verify_index_expected_map(
    section_manifest: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    expected: dict[str, dict[str, str]] = {}
    for entry in section_manifest.get("sections") or ():
        if not isinstance(entry, Mapping):
            continue
        section_id = str(entry.get("source_section_id") or entry.get("section_id") or "")
        if not section_id:
            continue
        expected[section_id] = {
            field: str(entry.get(field) or "")
            for field in _VERIFY_INDEX_FIELDS
        }
    return expected


def _verify_index_has_issues(diagnostics: Mapping[str, Any]) -> bool:
    return bool(diagnostics.get("issues"))


def _dominant_verify_index_reason(diagnostics: Mapping[str, Any]) -> str:
    counts = {
        "hash_mismatch": int(diagnostics.get("hash_mismatch_count") or 0),
        "stale_point": int(diagnostics.get("stale_point_count") or 0),
        "missing_point": int(diagnostics.get("missing_point_count") or 0),
    }
    max_count = max(counts.values(), default=0)
    if max_count <= 0:
        return "mixed"
    winners = [reason for reason, count in counts.items() if count == max_count]
    if len(winners) == 1:
        return winners[0]
    if "hash_mismatch" in winners:
        return "hash_mismatch"
    return "mixed"


def _scroll_section_payloads_from_qdrant(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    url = str(_config_get(config, ("vector_store", "url"), "http://localhost:6333"))
    section_collection = _section_collection_name(config)
    try:
        from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    except ImportError as exc:
        raise _SectionPayloadScrollError(
            "qdrant_client_unavailable",
            "qdrant_client is required to verify the Source Retrieval Index",
        ) from exc
    try:
        client = QdrantClient(url)
    except Exception as exc:  # pragma: no cover - client constructor is library-defined
        raise _SectionPayloadScrollError(
            "qdrant_client_init_failed",
            str(exc),
        ) from exc
    try:
        collection_exists = bool(client.collection_exists(collection_name=section_collection))
    except Exception as exc:
        raise _SectionPayloadScrollError(
            "collection_exists_failed",
            str(exc),
        ) from exc
    if not collection_exists:
        raise _SectionPayloadScrollError(
            "collection_missing",
            f"Qdrant collection does not exist: {section_collection}",
        )

    payloads: list[dict[str, Any]] = []
    offset: Any = None
    try:
        while True:
            points, next_offset = client.scroll(
                collection_name=section_collection,
                with_payload=True,
                with_vectors=False,
                limit=256,
                offset=offset,
            )
            for point in points:
                payloads.append(dict(getattr(point, "payload", None) or {}))
            if next_offset is None:
                break
            offset = next_offset
    except Exception as exc:
        raise _SectionPayloadScrollError("scroll_failed", str(exc)) from exc
    return payloads


def _section_collection_exists(url: str, collection: str) -> bool:
    """Return True when the Qdrant section-level collection already exists.

    Used to decide whether the section-level upsert needs `recreate=True`.
    A failure to query Qdrant (network error, 404 service down) returns
    False so the caller falls back to creating the collection.
    """

    try:
        from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        client = QdrantClient(url)
        return bool(client.collection_exists(collection_name=collection))
    except Exception:
        return False


def _section_metadata_by_id(
    section_metadata: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    metadata_by_id: dict[str, Mapping[str, Any]] = {}
    for entry in section_metadata.get("sections") or ():
        if not isinstance(entry, Mapping):
            continue
        section_id = str(
            entry.get("source_section_id") or entry.get("section_id") or ""
        )
        if not section_id:
            continue
        metadata_by_id[section_id] = {
            "summary": entry.get("summary"),
            "search_keys": entry.get("search_keys") or [],
            "identifiers": entry.get("identifiers") or [],
            "related_sections": entry.get("related_sections") or [],
        }
    return metadata_by_id


def _upsert_section_collection_if_enabled(
    *,
    config: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
    section_metadata: Mapping[str, Any],
    force_full_recreate: bool,
    emit: Any,
    store: ContextArtifactStore | None = None,
    run_full: bool = False,
    unchanged_sections: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
    progress_tracker: CoreProgressTracker | None = None,
    previous_section_manifest: Mapping[str, Any] | None = None,
    section_payload_fingerprints_out: MutableMapping[str, Mapping[str, str]] | None = None,
    section_collection_upsert_info_out: MutableMapping[str, Any] | None = None,
) -> str:
    """Build / refresh the section-level Qdrant collection.

    Returns the section collection status used for `CoreResult.retrieval_index_status`:

    * ``"success"``     — section collection upsert completed against Qdrant.
    * ``"skipped"``     — fake / offline retrieval (e.g. `embedding.provider != flagembedding`).
    * ``"skipped_unchanged"`` — prior Qdrant collection state is still valid.
    * ``"failed"``      — Qdrant exception swallowed so `/spec-core` is not blocked,
      but the section collection is unreliable. The candidate generator falls
      back to in-memory retrieval; surface this via the result diagnostics.
    """

    del emit  # kept for backward-compatible call sites and tests
    embedding_provider = str(_config_get(config, ("embedding", "provider"), ""))
    vector_store_provider = str(_config_get(config, ("vector_store", "provider"), ""))
    if embedding_provider != "flagembedding" or vector_store_provider != "qdrant":
        if section_collection_upsert_info_out is not None:
            section_collection_upsert_info_out.clear()
            section_collection_upsert_info_out.update(
                {"action": "skipped", "reason": "retrieval_disabled", "recreate": False}
            )
        _progress_action(
            progress_tracker,
            "section_collection_upsert",
            action="skipped",
            reason="retrieval_disabled",
        )
        return "skipped"
    url = str(_config_get(config, ("vector_store", "url"), "http://localhost:6333"))
    section_collection = _section_collection_name(config)
    expected_state = _build_retrieval_index_state(
        sections,
        config=config,
        collection=section_collection,
        generated_at=generated_at,
    )
    metadata_by_id = _section_metadata_by_id(section_metadata)
    current_payload_fingerprints = retrieval_index_api.build_section_payload_fingerprints(
        sections,
        metadata_by_id,
    )
    if section_payload_fingerprints_out is not None:
        section_payload_fingerprints_out.clear()
        section_payload_fingerprints_out.update(current_payload_fingerprints)
    section_diff = _section_collection_diff_sets(
        sections,
        previous_section_manifest,
        current_payload_fingerprints,
    )
    fast_path = _retrieval_index_fast_path_decision(
        expected_state,
        store=store,
        url=url,
        collection=section_collection,
        run_full=run_full,
        force_full_recreate=force_full_recreate,
        unchanged_sections=section_diff,
    )
    if fast_path["can_skip"]:
        if section_collection_upsert_info_out is not None:
            section_collection_upsert_info_out.clear()
            section_collection_upsert_info_out.update(
                {
                    "action": "skipped_unchanged",
                    "reason": "input_and_config_fingerprint_match_and_collection_exists",
                    "recreate": False,
                }
            )
        _progress_action(
            progress_tracker,
            "section_collection_upsert",
            action="skipped_unchanged",
            reason="input_and_config_fingerprint_match_and_collection_exists",
            diagnostics={
                "sections_upserted_count": 0,
                "sections_deleted_count": 0,
                "embed_documents_input_size": 0,
                "stale_points_deleted": 0,
            },
        )
        return "skipped_unchanged"

    # When the section collection has not been created yet (first run that
    # exercises section-level retrieval, or the operator deleted it
    # manually), the incremental upsert path would fail silently. Force
    # `recreate=True` in that case so the collection is materialized on
    # first encounter and downstream `set_payload` (related_sections) can
    # land successfully. Existing collections still respect the explicit
    # `force_full_recreate` flag.
    recreate = bool(force_full_recreate) or not _section_collection_exists(
        url, section_collection
    )
    sections_by_id = {
        str(section.get("source_section_id") or section.get("section_id") or ""): section
        for section in sections
    }
    sections_by_id.pop("", None)
    upsert_section_ids = set(section_diff["added_section_ids"]) | set(
        section_diff["changed_section_ids"]
    )
    partial_sections_to_upsert = [
        sections_by_id[section_id]
        for section_id in sorted(upsert_section_ids)
        if section_id in sections_by_id
    ]
    partial_sections_to_delete = list(section_diff["removed_section_ids"])
    use_partial_args = not run_full and not force_full_recreate
    use_explicit_delete_set = use_partial_args and isinstance(previous_section_manifest, Mapping)
    try:
        artifact = retrieval_index_api.upsert_qdrant_section_collection(
            sections,
            metadata_by_id,
            url=url,
            collection=section_collection,
            recreate=recreate,
            generated_at=str(section_metadata.get("generated_at") or ""),
            sections_to_upsert=partial_sections_to_upsert if use_partial_args else None,
            sections_to_delete=partial_sections_to_delete if use_explicit_delete_set else None,
        )
        diagnostics = artifact.get("diagnostics", {}) if isinstance(artifact, Mapping) else {}
        state_write_error: str | None = None
        if store is not None:
            try:
                store.write("retrieval_index_state", expected_state)
            except Exception as exc:
                state_write_error = str(exc)
        actual_recreate = bool(diagnostics.get("recreate", recreate))
        action = (
            "upserted_full"
            if run_full or force_full_recreate or actual_recreate or not use_partial_args
            else "upserted_partial"
        )
        reason = str(
            diagnostics.get("reason")
            or fast_path.get("reason")
            or "normal_upsert"
        )
        progress_diagnostics = dict(diagnostics)
        if state_write_error is not None:
            progress_diagnostics["state_write_error"] = state_write_error
        _progress_action(
            progress_tracker,
            "section_collection_upsert",
            action=action,
            reason=reason,
            recreate=actual_recreate,
            diagnostics=progress_diagnostics,
        )
        if section_collection_upsert_info_out is not None:
            section_collection_upsert_info_out.clear()
            section_collection_upsert_info_out.update(
                {
                    "action": action,
                    "reason": reason,
                    "recreate": actual_recreate,
                    "diagnostics": progress_diagnostics,
                }
            )
        return "success"
    except Exception:
        # Section collection upsert failures must not block /spec-core.
        # The candidate generator will fall back to in-memory retrieval and
        # surface the failure via diagnostics in the next aggregation step.
        _progress_action(
            progress_tracker,
            "section_collection_upsert",
            action="failed",
            reason=str(fast_path.get("reason") or "upsert_failed"),
        )
        if section_collection_upsert_info_out is not None:
            section_collection_upsert_info_out.clear()
            section_collection_upsert_info_out.update(
                {
                    "action": "failed",
                    "reason": str(fast_path.get("reason") or "upsert_failed"),
                    "recreate": recreate,
                }
            )
        return "failed"


def _update_section_collection_related_sections_if_enabled(
    *,
    config: Mapping[str, Any],
    section_metadata: Mapping[str, Any],
    emit: Any,
) -> None:
    """Push the `related_sections` field into the Qdrant section payload.

    Routes the related_sections LLM typing output back to the section
    collection so the inject CLI can return Related Sections in the same
    call as the section content. Skipped when the project is configured for
    fake / offline retrieval (the same gate as
    `_upsert_section_collection_if_enabled`).
    """

    embedding_provider = str(_config_get(config, ("embedding", "provider"), ""))
    vector_store_provider = str(_config_get(config, ("vector_store", "provider"), ""))
    if embedding_provider != "flagembedding" or vector_store_provider != "qdrant":
        return
    url = str(_config_get(config, ("vector_store", "url"), "http://localhost:6333"))
    section_collection = _section_collection_name(config)
    related_sections_by_id: dict[str, list[Mapping[str, Any]]] = {}
    for entry in section_metadata.get("sections") or ():
        if not isinstance(entry, Mapping):
            continue
        section_id = str(
            entry.get("source_section_id") or entry.get("section_id") or ""
        )
        if not section_id:
            continue
        related = entry.get("related_sections") or []
        if not isinstance(related, Sequence) or isinstance(related, (str, bytes)):
            continue
        related_sections_by_id[section_id] = [
            dict(item) for item in related if isinstance(item, Mapping)
        ]
    if not related_sections_by_id:
        return
    try:
        retrieval_index_api.update_section_collection_related_sections(
            related_sections_by_id,
            url=url,
            collection=section_collection,
        )
    except Exception:
        # set_payload failures must not block /spec-core. The inject CLI
        # can still resolve related_sections from the in-process metadata
        # payload until the next successful upsert lands.
        try:
            emit("core_related_sections_payload_patch_failed")
        except Exception:
            pass
        return


def _read_required(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"required core file not found: {path}")
    return path.read_text()


def _read_artifact(store: ContextArtifactStore, name: str) -> dict[str, Any]:
    try:
        return store.read(name)
    except Exception:
        return {}


def _load_sections(root: Path, config: Mapping[str, Any]) -> list[dict[str, Any]]:
    project_config = _project_config(config)
    max_level = int(_config_get(config, ("section", "max_heading_level"), 4))
    if project_config is not None:
        max_level = int(project_config.section.max_heading_level)
        files = list(project_config.sources.files)
    else:
        files = []
    sections: list[dict[str, Any]] = []
    for path in files:
        sections.extend(_parse_markdown_file(root, path, max_level=max_level))
    return sections


def _load_sections_from_snapshot(
    root: Path,
    config: Mapping[str, Any],
    snapshot: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    max_level = int(_config_get(config, ("section", "max_heading_level"), 4))
    project_config = _project_config(config)
    allowed_files = (
        {path.resolve() for path in project_config.sources.files}
        if project_config is not None
        else None
    )
    if project_config is not None:
        max_level = int(project_config.section.max_heading_level)
    files = _snapshot_files(snapshot)
    if files:
        sections: list[dict[str, Any]] = []
        for item in files:
            path_value = str(item.get("relative_path") or item.get("path") or "")
            if not path_value or item.get("exists") is False:
                continue
            path = root / path_value
            if allowed_files is not None and path.resolve() not in allowed_files:
                continue
            text = item.get("text")
            if not isinstance(text, str):
                text = path.read_text() if path.is_file() else ""
            sections.extend(_parse_markdown_text(root, path, text, max_level=max_level))
        return sections

    section_items = _snapshot_sections(snapshot)
    if section_items:
        return [dict(item) for item in section_items]
    return _load_sections(root, config)


def _snapshot_files(
    snapshot: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(snapshot, Mapping):
        files = snapshot.get("files", [])
    else:
        files = snapshot
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        return []
    return [dict(item) for item in files if isinstance(item, Mapping)]


def _snapshot_sections(
    snapshot: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(snapshot, Mapping):
        return []
    sections = snapshot.get("sections", [])
    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
        return []
    return [dict(item) for item in sections if isinstance(item, Mapping)]


def _parse_markdown_file(root: Path, path: Path, *, max_level: int) -> list[dict[str, Any]]:
    return _parse_markdown_text(root, path, path.read_text(), max_level=max_level)


def _parse_markdown_text(root: Path, path: Path, text: str, *, max_level: int) -> list[dict[str, Any]]:
    source_path = path.relative_to(root) if path.is_absolute() else path
    return [
        _section_to_dict(section)
        for section in section_parser_api.parse_markdown_sections(
            text,
            source_path=source_path.as_posix(),
            max_heading_level=max_level,
        )
    ]


def _project_config(config: Mapping[str, Any]) -> config_api.ProjectConfig | None:
    value = config.get("__project_config")
    return value if isinstance(value, config_api.ProjectConfig) else None


def _section_to_dict(section: Any) -> dict[str, Any]:
    if is_dataclass(section):
        data = asdict(section)
    elif isinstance(section, Mapping):
        data = dict(section)
    else:
        data = dict(getattr(section, "__dict__", {}))
    span = data.get("source_span")
    if is_dataclass(span):
        data["source_span"] = asdict(span)
    elif isinstance(span, Mapping):
        data["source_span"] = dict(span)
    return data


def _resolve_spec_core_llm_provider(
    config: Mapping[str, Any],
    *,
    provider: Any,
    llm_provider: Any,
    llm_provider_id: str | None = None,
    stage: str | None = None,
) -> Any:
    explicit = provider if provider is not None else llm_provider
    if explicit is not None:
        return explicit
    return llm_provider_api.build_spec_core_llm_provider(
        _config_get(config, ("llm",), {}),
        provider_id=llm_provider_id,
        stage=stage,
    )


def _config_with_selected_llm(
    config: Mapping[str, Any],
    *,
    provider_id: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    selected = llm_provider_api.select_llm_provider_config(
        _config_get(config, ("llm",), {}),
        provider_id=provider_id,
        stage=stage,
    )
    updated = dict(config)
    updated["llm"] = _llm_config_to_mapping(selected)
    return updated


def _llm_config_to_mapping(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        data = asdict(value)
    elif isinstance(value, Mapping):
        data = dict(value)
    else:
        data = dict(getattr(value, "__dict__", {}))
    return {
        key: item
        for key, item in data.items()
        if key in {"provider", "command", "model", "effort", "timeout_sec", "max_retries"}
        and item is not None
    }


def _metadata_generation_results_by_section(
    generation: section_metadata_api.SectionMetadataGeneration,
) -> dict[str, llm_provider_api.LlmGenerationResult]:
    results: dict[str, llm_provider_api.LlmGenerationResult] = {}
    generated_ids = list(generation.generated_section_ids)
    cursor = 0
    for result, batch_size in zip(generation.llm_results, generation.batch_sizes, strict=False):
        section_ids = generated_ids[cursor : cursor + batch_size]
        cursor += batch_size
        for section_id in section_ids:
            results[str(section_id)] = result
    return results


def _core_metadata_entries(
    generation: section_metadata_api.SectionMetadataGeneration,
    *,
    sections: Sequence[Mapping[str, Any]],
    provider: Any,
    failed_section_ids: set[str],
) -> list[dict[str, Any]]:
    section_by_id = {str(section["section_id"]): section for section in sections}
    diagnostics_by_section = _metadata_diagnostics_by_section(generation)
    provider_id = str(getattr(provider, "provider_id", provider.__class__.__name__))
    entries: list[dict[str, Any]] = []
    for raw_entry in generation.entries:
        entry = dict(raw_entry)
        section_id = str(entry.get("section_id") or "")
        section = section_by_id.get(section_id)
        if section is not None:
            entry.setdefault("source_section_id", section.get("source_section_id", section_id))
            entry.setdefault("stable_section_uid", section.get("stable_section_uid"))
            entry.setdefault("source_document_id", section.get("source_document_id"))
            entry.setdefault("heading_path", list(section.get("heading_path", [])))
            entry["source_hash"] = section.get("source_hash")
            entry["semantic_hash"] = section.get("semantic_hash")
        else:
            entry.setdefault("source_section_id", section_id)
        entry.setdefault("metadata_version", 1)
        entry["prompt_version"] = section_metadata_api.SECTION_METADATA_PROMPT_VERSION
        entry["llm_provider"] = provider_id
        if section_id in failed_section_ids:
            entry["llm_generation_status"] = "failed"
            entry["llm_diagnostics"] = diagnostics_by_section.get(section_id, [])
        else:
            entry["llm_generation_status"] = "success"
            entry.pop("llm_diagnostics", None)
        entries.append(entry)
    return entries


def _metadata_diagnostics_by_section(
    generation: section_metadata_api.SectionMetadataGeneration,
) -> dict[str, list[dict[str, Any]]]:
    by_section: dict[str, list[dict[str, Any]]] = {}
    generated_ids = list(generation.generated_section_ids)
    cursor = 0
    for result, batch_size in zip(generation.llm_results, generation.batch_sizes, strict=False):
        section_ids = [str(section_id) for section_id in generated_ids[cursor : cursor + batch_size]]
        cursor += batch_size
        if result.status == "success":
            continue
        diagnostics = [dict(item) for item in result.diagnostic_items or []]
        for section_id in section_ids:
            by_section[section_id] = diagnostics
    for diagnostic in generation.diagnostics:
        section_ids = diagnostic.get("section_ids")
        if isinstance(section_ids, Sequence) and not isinstance(section_ids, (str, bytes)):
            for section_id in section_ids:
                by_section.setdefault(str(section_id), []).append(dict(diagnostic))
            continue
        section_id = diagnostic.get("section_id")
        if isinstance(section_id, str) and section_id:
            by_section.setdefault(section_id, []).append(dict(diagnostic))
    return by_section


def _summarize_metadata_generation(
    generation: section_metadata_api.SectionMetadataGeneration,
    *,
    failed_section_ids: set[str],
) -> dict[str, Any]:
    generated_ids = {str(section_id) for section_id in generation.generated_section_ids}
    failed = sorted(failed_section_ids)
    if generated_ids and failed_section_ids >= generated_ids:
        freshness_status = "failed"
        blocking_reasons = ["failed_required_artifact"]
    else:
        freshness_status = "degraded"
        blocking_reasons = ["degraded_optional_artifact"]
    return {
        "failed_sections": failed,
        "warnings": [f"LLM generation failed for {section_id}" for section_id in failed],
        "freshness_status": freshness_status,
        "blocking_reasons": blocking_reasons,
    }


def _generate_related_sections(
    *,
    sections: Sequence[Mapping[str, Any]],
    section_metadata: Mapping[str, Any],
    provider: Any,
    config: Mapping[str, Any],
    generated_at: str,
    cache_dir: Any | None = None,
    store: ContextArtifactStore | None = None,
    run_full: bool = False,
    unchanged_sections: Mapping[str, Any] | None = None,
    section_diff_sets: Mapping[str, Any] | None = None,
    previous_related_sections: Mapping[str, Any] | None = None,
    retrieval_index_status: str = "",
    progress_tracker: CoreProgressTracker | None = None,
) -> Any:
    expected_state = _build_related_sections_state(
        sections,
        config=config,
        provider=provider,
        generated_at=generated_at,
    )
    fast_path = _related_sections_fast_path_decision(
        expected_state,
        store=store,
        run_full=run_full,
        unchanged_sections=unchanged_sections,
        section_diff_sets=section_diff_sets,
        retrieval_index_status=retrieval_index_status,
    )
    if fast_path["can_skip"]:
        _progress_action(
            progress_tracker,
            "related_sections",
            action="skipped_unchanged",
            reason="input_and_config_fingerprint_match",
        )
        return {
            "status": "skipped_unchanged",
            "related_section_candidates": [],
            "related_sections": _related_sections_from_metadata(section_metadata),
            "sections": _related_section_payloads_from_metadata(section_metadata),
            "diagnostics": [],
            "generated_at": generated_at,
        }

    if fast_path.get("can_partial"):
        changed_source_section_ids = _changed_or_added_section_ids(section_diff_sets)
        result = related_sections_api.generate_related_sections_partial_result(
            sections,
            section_metadata=section_metadata,
            previous_related_sections=previous_related_sections,
            changed_source_section_ids=changed_source_section_ids,
            provider=provider,
            config=config,
            generated_at=generated_at,
            cache_dir=cache_dir,
        )
        candidate_generation = getattr(result, "candidate_generation", None)
        selection = getattr(result, "selection", None)
        candidate_generation_elapsed_sec = float(
            getattr(candidate_generation, "elapsed_sec", 0.0) or 0.0
        )
        selection_elapsed_sec = float(getattr(selection, "elapsed_sec", 0.0) or 0.0)
        if store is not None and retrieval_index_status in {"success", "skipped_unchanged"}:
            store.write("related_sections_state", expected_state)
        _progress_action(
            progress_tracker,
            "related_sections",
            action="regenerated_partial",
            reason=str(fast_path.get("reason") or "section_changed"),
            diagnostics=_related_generation_diagnostics(result),
            batch_count=getattr(getattr(result, "selection", None), "llm_calls", 0),
            changed_source_section_ids=changed_source_section_ids,
            candidate_generation_elapsed_sec=candidate_generation_elapsed_sec,
            selection_elapsed_sec=selection_elapsed_sec,
            candidate_generation_source_count=len(changed_source_section_ids),
            candidate_generation_partial_mode="source_changed_only",
        )
        return result

    try:
        result = related_sections_api.generate_related_sections_result(
            sections,
            section_metadata=section_metadata,
            provider=provider,
            config=config,
            generated_at=generated_at,
            cache_dir=cache_dir,
        )
        candidate_generation = getattr(result, "candidate_generation", None)
        selection = getattr(result, "selection", None)
        candidate_generation_elapsed_sec = float(
            getattr(candidate_generation, "elapsed_sec", 0.0) or 0.0
        )
        selection_elapsed_sec = float(getattr(selection, "elapsed_sec", 0.0) or 0.0)
        if store is not None and retrieval_index_status in {"success", "skipped_unchanged"}:
            try:
                store.write("related_sections_state", expected_state)
            except Exception:
                pass
        _progress_action(
            progress_tracker,
            "related_sections",
            action="generated" if run_full else "fallback_regenerated",
            reason=str(fast_path.get("reason") or "normal_generation"),
            candidate_generation_elapsed_sec=candidate_generation_elapsed_sec,
            selection_elapsed_sec=selection_elapsed_sec,
            candidate_generation_source_count=len(sections),
            candidate_generation_partial_mode="full",
        )
        return result
    except Exception as exc:
        _progress_action(
            progress_tracker,
            "related_sections",
            action="failed",
            reason=str(fast_path.get("reason") or "generation_failed"),
        )
        qdrant_backend_failure = _detect_qdrant_backend_failure(exc, config=config)
        return {
            "status": "failed",
            "related_section_candidates": [],
            "related_sections": {},
            "sections": [],
            "diagnostics": [
                {
                    "kind": "related_sections_generation_failed",
                    "level": "warning",
                    "message": str(exc),
                }
            ],
            "qdrant_backend_failure": qdrant_backend_failure,
            "generated_at": generated_at,
        }


def _detect_qdrant_backend_failure(exc: Exception, *, config: Any) -> dict[str, Any] | None:
    """Classify whether `exc` looks like a Qdrant connection failure.

    Per EXTERNAL_DESIGN.ja.md §11.1.5 行 10, when `[vector_store].provider="qdrant"`
    and the service is unreachable, the result should expose
    `diagnostics.related_sections.qdrant_backend_failure={"failure_reason":<具体>, ...}`
    so the Agent can present recovery hints to the user.
    """

    vector_store = config.get("vector_store") if isinstance(config, Mapping) else None
    provider = (vector_store or {}).get("provider") if isinstance(vector_store, Mapping) else None
    url = (vector_store or {}).get("url") if isinstance(vector_store, Mapping) else None
    if provider != "qdrant":
        return None
    text = f"{type(exc).__name__}: {exc}"
    # Common connection failure signatures from httpx/urllib3/socket.
    markers = (
        "Connection refused",
        "Errno 111",
        "Errno 61",
        "Failed to establish a new connection",
        "Max retries exceeded",
        "Name or service not known",
        "Temporary failure in name resolution",
        "Connection reset by peer",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
    )
    if not any(marker in text for marker in markers):
        return None
    return {
        "failure_reason": str(exc),
        "exception_type": type(exc).__name__,
        "provider": "qdrant",
        "url": url,
    }


def _related_sections_status(payload: Any) -> str:
    if isinstance(payload, Mapping):
        status = payload.get("status")
        if isinstance(status, str) and status:
            return status
        diagnostics = payload.get("diagnostics")
        if diagnostics:
            return "failed"
        return "success"
    artifact = getattr(payload, "artifact", None)
    if isinstance(artifact, Mapping):
        status = artifact.get("status")
        if isinstance(status, str) and status:
            return status
    return "success"


def _related_sections_qdrant_backend_failure(payload: Any) -> dict[str, Any] | None:
    """Return the Qdrant backend failure descriptor when AUD-007 marks failed."""

    if isinstance(payload, Mapping):
        failure = payload.get("qdrant_backend_failure")
        if isinstance(failure, Mapping):
            return dict(failure)
        return None
    candidate_generation = getattr(payload, "candidate_generation", None)
    if candidate_generation is not None:
        failure = getattr(candidate_generation, "qdrant_backend_failure", None)
        if isinstance(failure, Mapping):
            return dict(failure)
    artifact = getattr(payload, "artifact", None)
    if isinstance(artifact, Mapping):
        failure = artifact.get("qdrant_backend_failure")
        if isinstance(failure, Mapping):
            return dict(failure)
    return None


def _related_generation_diagnostics(payload: Any) -> list[dict[str, Any]]:
    value: Any = None
    if hasattr(payload, "diagnostics"):
        value = getattr(payload, "diagnostics")
    elif hasattr(payload, "to_dict"):
        return _related_generation_diagnostics(payload.to_dict())
    elif isinstance(payload, Mapping):
        value = payload.get("diagnostics")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _related_sections_from_metadata(
    section_metadata: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    related_by_source: dict[str, list[dict[str, Any]]] = {}
    for entry in section_metadata.get("sections", []):
        if not isinstance(entry, Mapping):
            continue
        section_id = str(entry.get("source_section_id") or entry.get("section_id") or "")
        if not section_id:
            continue
        related_by_source[section_id] = _mapping_list(entry.get("related_sections"))
    return related_by_source


def _related_section_payloads_from_metadata(
    section_metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "source_section_id": source_id,
            "section_id": source_id,
            "related_sections": related,
        }
        for source_id, related in _related_sections_from_metadata(section_metadata).items()
    ]


def _related_sections_by_source(payload: Any) -> dict[str, list[dict[str, Any]]]:
    if hasattr(payload, "related_sections"):
        value = getattr(payload, "related_sections")
        if isinstance(value, Mapping):
            return {
                str(source_id): _mapping_list(items)
                for source_id, items in value.items()
            }
    if hasattr(payload, "to_dict"):
        return _related_sections_by_source(payload.to_dict())
    if not isinstance(payload, Mapping):
        return {}
    related = payload.get("related_sections")
    if isinstance(related, Mapping):
        return {
            str(source_id): _mapping_list(items)
            for source_id, items in related.items()
        }
    by_source: dict[str, list[dict[str, Any]]] = {}
    sections = payload.get("sections", [])
    if isinstance(sections, Sequence) and not isinstance(sections, (str, bytes)):
        for item in sections:
            if not isinstance(item, Mapping):
                continue
            source_id = item.get("source_section_id") or item.get("section_id")
            if source_id:
                by_source[str(source_id)] = _mapping_list(item.get("related_sections"))
    return by_source


def _related_section_candidates(payload: Any) -> list[dict[str, Any]]:
    if hasattr(payload, "related_section_candidates"):
        value = getattr(payload, "related_section_candidates")
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return _mapping_list(value)
    if hasattr(payload, "to_dict"):
        return _related_section_candidates(payload.to_dict())
    if isinstance(payload, Mapping):
        return _mapping_list(payload.get("related_section_candidates") or payload.get("candidates"))
    return []


def _metadata_related_sections_by_source(
    section_metadata: Mapping[str, Any],
    *,
    candidates: Sequence[Mapping[str, Any]],
    sections: Sequence[Mapping[str, Any]],
    generated_at: str,
) -> dict[str, list[dict[str, Any]]]:
    related_by_source: dict[str, list[dict[str, Any]]] = {}
    for entry in section_metadata.get("sections", []):
        if not isinstance(entry, Mapping):
            continue
        source_id = str(entry.get("source_section_id") or entry.get("section_id") or "")
        raw_items = _mapping_list(entry.get("related_sections"))
        if not source_id or not raw_items:
            continue
        enriched_items = _enrich_related_items_from_candidates(
            source_id,
            raw_items,
            candidates,
        )
        try:
            validation = related_sections_api.validate_related_sections_result(
                source_id,
                enriched_items,
                candidates=candidates,
                sections=sections,
                section_metadata=section_metadata,
                generated_at=generated_at,
            )
        except Exception:
            continue
        payload = validation.to_dict() if hasattr(validation, "to_dict") else dict(validation)
        validated = _mapping_list(payload.get("related_sections"))
        if validated:
            related_by_source[source_id] = validated
    return related_by_source


def _enrich_related_items_from_candidates(
    source_id: str,
    raw_items: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidate_by_target = {
        str(candidate.get("target_section_id")): candidate
        for candidate in candidates
        if str(candidate.get("source_section_id") or "") == source_id
    }
    enriched_items: list[dict[str, Any]] = []
    for item in raw_items:
        enriched = dict(item)
        target_id = str(enriched.get("target_section_id") or "")
        candidate = candidate_by_target.get(target_id, {})
        enriched.setdefault("relation_hint", "see_also")
        enriched.setdefault("confidence", "medium")
        enriched.setdefault("reason", candidate.get("reason") or "Related by generated candidate evidence.")
        if not enriched.get("evidence_terms"):
            enriched["evidence_terms"] = _list_of_strings(candidate.get("evidence_terms"))
        if not enriched.get("channels"):
            enriched["channels"] = _list_of_strings(candidate.get("channels"))
        enriched_items.append(enriched)
    return enriched_items


def _merge_related_sections_by_source(
    selected: Mapping[str, Sequence[Mapping[str, Any]]],
    fallback: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    merged = {
        str(source_id): _mapping_list(items)
        for source_id, items in selected.items()
    }
    for source_id, items in fallback.items():
        if items and not merged.get(str(source_id)):
            merged[str(source_id)] = _mapping_list(items)
    return merged


CONFLICT_REVIEW_PROMPT_VERSION = "conflict-review-v1"


class _EvidenceGroundedConflictJudge:
    def __init__(
        self,
        delegate: Any,
        *,
        purpose_ref: str,
        purpose_text: str,
        purpose_hash: str,
        concept_ref: str,
        concept_text: str,
        concept_hash: str,
        llm_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.delegate = delegate
        self.purpose_ref = purpose_ref
        self.purpose_text = purpose_text
        self.purpose_hash = purpose_hash
        self.concept_ref = concept_ref
        self.concept_text = concept_text
        self.concept_hash = concept_hash
        # Capture model / effort from the conflict_review stage's resolved llm
        # config so we can build a proper LlmRequest when delegate is an
        # LlmProvider (e.g. SubprocessLlmProvider). Without this the delegate's
        # `generate(LlmRequest)` contract crashes because conflict_review used
        # to pass plain dicts before stage_routing existed.
        self._llm_config = dict(llm_config) if isinstance(llm_config, Mapping) else {}

    @property
    def provider_id(self) -> str:
        return str(getattr(self.delegate, "provider_id", "evidence-grounded-conflict-judge"))

    def judge_conflict(self, request: Mapping[str, Any], *, timeout_sec: int = 5) -> dict[str, Any]:
        grounded_request = {
            **dict(request),
            "purpose": {
                "source_ref": self.purpose_ref,
                "hash": self.purpose_hash,
                "text": self.purpose_text,
            },
            "core_concept": {
                "source_ref": self.concept_ref,
                "hash": self.concept_hash,
                "text": self.concept_text,
            },
        }
        return _call_conflict_judge(
            self.delegate,
            grounded_request,
            timeout_sec=timeout_sec,
            llm_config=self._llm_config,
        )


def _call_conflict_judge(
    delegate: Any,
    request: dict[str, Any],
    *,
    timeout_sec: int,
    llm_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if delegate is None:
        return {"outcome": "needs_human_review", "severity": "medium"}
    # Fake / test judges expose dict-shaped judge_conflict / judge methods.
    for method_name in ("judge_conflict", "judge"):
        method = getattr(delegate, method_name, None)
        if not callable(method):
            continue
        try:
            return dict(method(request, timeout_sec=timeout_sec))
        except TypeError:
            return dict(method(request))
    # LlmProvider exposes generate(LlmRequest, timeout_sec=...) and refuses
    # plain dicts. Wrap the conflict review request as a stage-tagged
    # LlmRequest so SubprocessLlmProvider / FakeLlmProvider can both consume it.
    generate = getattr(delegate, "generate", None)
    if callable(generate):
        try:
            llm_request = _build_conflict_review_llm_request(request, llm_config or {})
            raw_output = generate(llm_request, timeout_sec=timeout_sec)
            return _coerce_conflict_judge_output(raw_output)
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": "needs_human_review",
                "severity": "medium",
                "reason": (
                    "conflict_review LlmProvider call failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            }
    if callable(delegate):
        return dict(delegate(request))
    raise TypeError("conflict_judge must expose judge_conflict, judge, generate, or be callable")


def _build_conflict_review_llm_request(
    request: Mapping[str, Any],
    llm_config: Mapping[str, Any],
) -> llm_provider_api.LlmRequest:
    """Wrap a conflict-review dict request as a stage='conflict_review' LlmRequest."""

    serialized = json.dumps(dict(request), ensure_ascii=False, sort_keys=True, default=str)
    source_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    section_hashes: dict[str, str] = {}
    for ref in request.get("source_refs", []) or []:
        if isinstance(ref, Mapping):
            sid = ref.get("source_section_id") or ref.get("source_ref") or ref.get("ref")
            shash = ref.get("source_hash") or ref.get("hash")
            if isinstance(sid, str) and isinstance(shash, str):
                section_hashes[sid] = shash
    purpose = request.get("purpose")
    if isinstance(purpose, Mapping):
        ref = str(purpose.get("source_ref") or "")
        h = str(purpose.get("hash") or "")
        if ref and h:
            section_hashes[ref] = h
    concept = request.get("core_concept")
    if isinstance(concept, Mapping):
        ref = str(concept.get("source_ref") or "")
        h = str(concept.get("hash") or "")
        if ref and h:
            section_hashes[ref] = h
    return llm_provider_api.LlmRequest(
        task="conflict_review",
        stage="conflict_review",
        prompt=serialized,
        prompt_version=CONFLICT_REVIEW_PROMPT_VERSION,
        model=str(llm_config.get("model") or "fake"),
        source_hash=source_hash,
        section_hashes=section_hashes,
        effort=llm_config.get("effort"),
    )


def _coerce_conflict_judge_output(output: Any) -> dict[str, Any]:
    if isinstance(output, Mapping):
        result = dict(output)
        usage = result.get("__spec_anchor_usage")
        # If the LLM returned a top-level conflict outcome, pass through.
        if "outcome" in result:
            return result
        # Some providers nest the actual response under "result" / "output" /
        # "judgement"; fall back to reading those.
        for key in ("result", "output", "judgement", "judgment"):
            value = result.get(key)
            if isinstance(value, Mapping) and "outcome" in value:
                coerced = dict(value)
                if usage is not None:
                    coerced["__spec_anchor_usage"] = usage
                return coerced
        # No outcome found in structured output → mark as needing human review
        # and preserve any reason/text present for diagnostics.
        fallback: dict[str, Any] = {
            "outcome": "needs_human_review",
            "severity": "medium",
            "reason": "conflict_review LlmProvider output missing outcome field",
            "raw": result,
        }
        if usage is not None:
            fallback["__spec_anchor_usage"] = usage
        return fallback
    return {
        "outcome": "needs_human_review",
        "severity": "medium",
        "reason": f"conflict_review LlmProvider returned non-mapping: {type(output).__name__}",
    }


def _ensure_context_base_hashes(
    items: Sequence[Mapping[str, Any]],
    *,
    purpose_ref: str,
    purpose_hash: str,
    concept_ref: str,
    concept_hash: str,
) -> list[dict[str, Any]]:
    context_hashes = {
        purpose_ref: purpose_hash,
        concept_ref: concept_hash,
    }
    updated_items: list[dict[str, Any]] = []
    for item in items:
        updated = dict(item)
        base_hashes = [
            dict(base)
            for base in updated.get("base_source_hashes", [])
            if isinstance(base, Mapping)
        ]
        by_ref = {
            str(base.get("source_ref") or base.get("source_section_id") or base.get("ref")): base
            for base in base_hashes
        }
        for source_ref, source_hash in context_hashes.items():
            by_ref.setdefault(source_ref, {"source_ref": source_ref, "hash": source_hash})
        updated["base_source_hashes"] = list(by_ref.values())
        updated_items.append(updated)
    return updated_items


def _merge_conflict_items(existing: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    resolved_pair_keys: set[tuple[str, str]] = set()
    for item in existing:
        current = dict(item)
        merged[str(item.get("conflict_id"))] = current
        if current.get("status") in {"resolved", "dismissed"}:
            pair_key = _conflict_pair_key_from_item(current)
            if pair_key is not None:
                resolved_pair_keys.add(pair_key)
    for item in new:
        conflict_id = str(item.get("conflict_id"))
        pair_key = _conflict_pair_key_from_item(item)
        if pair_key in resolved_pair_keys:
            continue
        if merged.get(conflict_id, {}).get("status") in {"resolved", "dismissed"}:
            continue
        merged[conflict_id] = dict(item)
    return list(merged.values())


def _conflict_pair_key_from_item(item: Mapping[str, Any]) -> tuple[str, str] | None:
    for related in item.get("related_sections", []):
        if not isinstance(related, Mapping):
            continue
        source_id = related.get("source_section_id")
        target_id = related.get("target_section_id")
        if source_id and target_id:
            return tuple(sorted((str(source_id), str(target_id))))
    refs = [
        str(ref.get("source_section_id") or ref.get("source_ref") or ref.get("ref") or "")
        for ref in item.get("source_refs", [])
        if isinstance(ref, Mapping)
    ]
    refs = [ref for ref in refs if ref]
    if len(refs) >= 2:
        return tuple(sorted(refs[:2]))
    return None


def _chapter_anchors(
    sections: Sequence[Mapping[str, Any]],
    metadata: Sequence[Mapping[str, Any]],
    generated_at: str,
    *,
    config: Mapping[str, Any] | None = None,
    provider: Any = None,
    cache_dir: str | Path | None = None,
    concept_text: str | None = None,
    rebuild_all: bool = False,
) -> tuple[dict[str, Any], list[Any], list[str]]:
    """Phase R-7: LLM-generated Chapter Key Anchor.

    Delegates to `spec_anchor.chapter_anchors.generate_chapter_anchors`
    which issues one LLM call per chapter and reports chapter ids whose
    LLM output could not produce a usable anchor.

    `rebuild_all=True` propagates the `--all` / `--rebuild` CLI contract
    into chapter_anchors so its on-disk cache is bypassed for the load
    step (every chapter is recomputed via LLM). This parallels the
    section_metadata cache bypass and the related_typing_cache.json
    deletion that `_run_spec_core_unlocked` already performs for `--all`.
    """

    import spec_anchor.chapter_anchors as chapter_anchors_api

    llm_config = _config_get(config, ("llm",), {}) if config is not None else {}
    generation = chapter_anchors_api.generate_chapter_anchors(
        sections,
        metadata,
        config=config,
        llm_config=llm_config,
        provider=provider,
        cache_dir=cache_dir,
        concept_text=concept_text or "",
        generated_at=generated_at,
        rebuild_all=rebuild_all,
    )
    return generation.artifact, list(generation.llm_results), list(generation.failed_chapter_ids)


def _section_manifest_audit_by_id(
    metadata_entries: Sequence[Mapping[str, Any]],
    *,
    generated_at: str | None,
) -> dict[str, dict[str, Any]]:
    """Collect per-section audit fields for `section_manifest.json`.

    Sources the audit data (`llm_provider`, `llm_generation_status`,
    `last_prompt_version`, `generated_at`) from the freshly built
    `metadata_entries`. The values are written into the manifest shape
    without rewriting the metadata entries themselves.
    """

    audit_by_id: dict[str, dict[str, Any]] = {}
    for entry in metadata_entries:
        if not isinstance(entry, Mapping):
            continue
        section_id = str(
            entry.get("section_id") or entry.get("source_section_id") or ""
        )
        if not section_id:
            continue
        audit_by_id[section_id] = {
            "llm_provider": entry.get("llm_provider"),
            "llm_generation_status": entry.get("llm_generation_status"),
            "last_prompt_version": entry.get("prompt_version"),
            "generated_at": entry.get("generated_at") or generated_at,
        }
    return audit_by_id


def _section_manifest_entry(
    section: Mapping[str, Any],
    *,
    audit: Mapping[str, Any] | None = None,
    fingerprints: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return one ``section_manifest.json`` entry.

    Schema (``doc/STORAGE_REDESIGN.ja.md`` §4.3)::

        source_section_id   — 一次 key
        source_hash         — raw body の SHA-256 (file integrity)
        semantic_hash       — whitespace 正規化後の SHA-256 (LLM cache key)
        heading_path        — 見出し親子チェーン list[str]
        chapter_id          — 章 ID
        source_span         — {start_line, end_line, start_offset, end_offset}
        vector_input_fingerprint — BGE-M3 入力 text の SHA-256
        payload_fingerprint — Qdrant payload dict の canonical JSON SHA-256
        llm_provider        — 監査用 (audit, optional)
        llm_generation_status — success / failed / skipped (audit, optional)
        last_prompt_version — cache 整合確認用 (audit, optional)
        generated_at        — 監査用 (audit, optional)

    ``audit`` dict が渡された場合のみ下 4 行が追加される。
    """

    entry: dict[str, Any] = {
        key: section[key]
        for key in (
            "section_id",
            "source_section_id",
            "source_document_id",
            "source_hash",
            "semantic_hash",
            "chapter_id",
            "heading_path",
            "source_span",
        )
    }
    if fingerprints:
        for key in ("vector_input_fingerprint", "payload_fingerprint"):
            value = fingerprints.get(key)
            if value:
                entry[key] = str(value)
    if audit:
        for key in (
            "llm_provider",
            "llm_generation_status",
            "last_prompt_version",
            "generated_at",
        ):
            if key in audit:
                entry[key] = audit[key]
    return entry


def _section_ref(section: Mapping[str, Any]) -> dict[str, str]:
    return {"section_id": str(section["section_id"]), "source_section_id": str(section["section_id"])}


def _source_refs_for_sections(sections: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(section.get("source_document_id") or str(section.get("section_id", "")).split("#", 1)[0]) for section in sections})


def _project_ref(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value]


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_一-龯ぁ-んァ-ンー]+", "-", value.strip()).strip("-")
    return slug.lower() or "section"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _nowish() -> str:
    return "1970-01-01T00:00:00Z"


def _now_ms() -> int:
    return int(time.time() * 1000)


spec_core = run_spec_core
run_core = run_spec_core
core = run_spec_core
execute_spec_core = run_spec_core
update_spec_core_from_watcher = run_spec_core_for_watcher
run_watcher_core_update = run_spec_core_for_watcher
apply_watcher_update = run_spec_core_for_watcher
