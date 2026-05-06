"""Lightweight `/spec-core` orchestration helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import spec_grag.config as config_api
import spec_grag.related_sections as related_sections_api
import spec_grag.retrieval_index as retrieval_index_api
import spec_grag.section_metadata as section_metadata_api
import spec_grag.section_parser as section_parser_api
import spec_grag.llm_provider as llm_provider_api
from spec_grag.artifacts import ContextArtifactStore, build_empty_chapter_anchors
from spec_grag.conflict_review import (
    apply_conflict_decision,
    evaluate_conflicts,
    refresh_conflict_resolution_staleness,
    summarize_conflict_review_state,
)
from spec_grag.core_lock import (
    DEFAULT_STALE_LOCK_MS,
    acquire_core_update_lock,
    core_update_lock_path,
    lock_diagnostics,
    lock_is_stale,
    release_core_update_lock,
)
from spec_grag.freshness import build_freshness_report


MUST_RE = re.compile(r"\bmust\b(?!\s+not\b)")
REQUIRE_TERMS = ("requires", "required", "requirement", "必須")
FORBID_TERMS = ("forbids", "forbidden", "must not", "cannot", "prohibited", "should not", "禁止")
OPTIONAL_TERMS = ("optional", "任意")
CONFLICT_CANDIDATE_CHANNELS = {"markdown_link", "shared_identifier", "search_key_match"}


def run_spec_core(
    project_root: str | Path = ".",
    *,
    all: bool = False,
    all_mode: bool = False,
    full: bool = False,
    force: bool = False,
    mode: str | None = None,
    decision_payload: Mapping[str, Any] | None = None,
    decision: Mapping[str, Any] | None = None,
    conflict_decision: Mapping[str, Any] | None = None,
    provider: Any = None,
    llm_provider: Any = None,
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
            decision_payload=decision_payload,
            decision=decision,
            conflict_decision=conflict_decision,
            provider=provider,
            llm_provider=llm_provider,
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
    decision_payload: Mapping[str, Any] | None = None,
    decision: Mapping[str, Any] | None = None,
    conflict_decision: Mapping[str, Any] | None = None,
    provider: Any = None,
    llm_provider: Any = None,
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
    **_: Any,
) -> dict[str, Any]:
    """Run a small, deterministic `/spec-core` update after external locking."""

    _emit_heartbeat(heartbeat, stage="core_start")
    root = Path(project_root)
    generated_at = generated_at or _nowish()
    config = dict(config) if config is not None else _load_project_config(root)
    purpose_path = root / _config_get(config, ("core", "purpose_file"), "docs/core/purpose.md")
    concept_path = root / _config_get(config, ("core", "concept_file"), "docs/core/concept.md")
    purpose_text = _read_required(purpose_path)
    concept_text = _read_required(concept_path)
    _emit_heartbeat(heartbeat, stage="core_inputs_loaded")
    purpose_hash = _hash_text(purpose_text)
    concept_hash = _hash_text(concept_text)
    purpose_ref = _project_ref(root, purpose_path)
    concept_ref = _project_ref(root, concept_path)

    context_dir = root / _config_get(config, ("context", "storage"), ".spec-grag/context")
    store = ContextArtifactStore(context_dir)
    previous_metadata = _read_artifact(store, "section_metadata")
    previous_conflicts = _read_artifact(store, "conflict_review_items")
    previous_source_chunks = _read_artifact(store, "source_chunks")
    previous_retrieval_index_revision = _read_artifact(store, "retrieval_index_revision")

    run_full = bool(all or all_mode or full or force or mode == "full")
    mode_name = "full" if run_full else "incremental"
    active_provider = _resolve_spec_core_llm_provider(
        config,
        provider=provider,
        llm_provider=llm_provider,
    )
    active_judge = conflict_judge or judge or active_provider

    sections = _load_sections_from_snapshot(
        root,
        config,
        source_snapshot or snapshot or watcher_snapshot,
    ) if source_snapshot or snapshot or watcher_snapshot else _load_sections(root, config)
    _emit_heartbeat(heartbeat, stage="core_sections_loaded")
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
        or old_entries[section["section_id"]].get("source_hash") != section["source_hash"]
    }

    _emit_heartbeat(heartbeat, stage="core_section_metadata_start")
    metadata_generation = section_metadata_api.generate_section_metadata_result(
        sections,
        config=config,
        provider=active_provider,
        previous_metadata=previous_metadata,
        rebuild_all=False,
        cache_dir=context_dir / "cache",
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
    section_metadata["prompt_version"] = "section-metadata-v1"
    section_metadata["sections"] = metadata_entries
    section_metadata["generated_at"] = generated_at
    _emit_heartbeat(heartbeat, stage="core_section_metadata_done")
    _emit_heartbeat(heartbeat, stage="core_related_sections_start")
    related_generation = _generate_related_sections(
        sections=sections,
        section_metadata=section_metadata,
        provider=active_provider,
        config=config,
        generated_at=generated_at,
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
    section_metadata = related_sections_api.apply_related_sections_to_metadata(
        section_metadata,
        {"related_sections": selected_related_sections},
    )
    _emit_heartbeat(heartbeat, stage="core_related_sections_done")
    metadata_entries = [
        dict(entry)
        for entry in section_metadata.get("sections", [])
        if isinstance(entry, Mapping)
    ]

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
        _emit_heartbeat(heartbeat, stage="core_conflict_decision_start")
        existing_conflict_items = apply_conflict_decision(
            conflict_review_items=existing_conflict_items,
            decision_payload=dict(payload),
            generated_at=generated_at,
        )
        _emit_heartbeat(heartbeat, stage="core_conflict_decision_done")

    conflict_candidates = _conflict_candidates_from_related_output(
        related_section_candidates,
        sections=sections,
    )
    _emit_heartbeat(heartbeat, stage="core_conflict_evaluation_start")
    conflict_result = evaluate_conflicts(
        sections=sections,
        related_sections=selected_related_sections,
        related_section_candidates=conflict_candidates,
        conflict_judge=_EvidenceGroundedConflictJudge(
            active_judge,
            purpose_ref=purpose_ref,
            purpose_text=purpose_text,
            purpose_hash=purpose_hash,
            concept_ref=concept_ref,
            concept_text=concept_text,
            concept_hash=concept_hash,
        ),
        config=None,
        generated_at=generated_at,
    )
    _emit_heartbeat(heartbeat, stage="core_conflict_evaluation_done")
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
    failed_required_artifacts = (
        ["section_metadata"] if generation_status == "failed" else []
    )
    degraded_optional_artifacts = (
        ["section_metadata"] if generation_status == "degraded" else []
    )
    generation_warnings = list(metadata_generation_summary.get("warnings") or [])
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
        }
    }

    section_manifest = {
        "sections": [_section_manifest_entry(section) for section in sections],
        "purpose_hash": purpose_hash,
        "concept_hash": concept_hash,
        "generated_at": generated_at,
    }
    chapter_anchors = _chapter_anchors(sections, metadata_entries, generated_at)
    retrieval_chunks = retrieval_index_api.build_source_chunks(
        sections,
        retrieval_config=_config_get(config, ("retrieval",), {}),
    )
    source_chunks = retrieval_index_api.build_source_chunks_artifact(
        retrieval_chunks,
        chunk_size=_config_get(config, ("retrieval", "chunk_size"), 1200),
        chunk_overlap=_config_get(config, ("retrieval", "chunk_overlap"), 160),
    )
    source_chunks["status"] = "success"
    source_chunks["generated_at"] = generated_at
    retrieval_index_revision = _build_retrieval_index_revision(
        config,
        retrieval_chunks,
        generated_at=generated_at,
        previous_source_chunks=previous_source_chunks,
        previous_revision=previous_retrieval_index_revision,
    )
    if str(retrieval_index_revision.get("status", "")).lower() in {
        "failed",
        "missing",
        "error",
        "unavailable",
        "skipped",
    }:
        failed_required_artifacts.append("retrieval_index_revision")
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
        "section_metadata": section_metadata,
        "conflict_review_items": {
            "conflict_review_items": conflict_review_items,
            "generated_at": generated_at,
        },
        "chapter_anchors": chapter_anchors,
        "source_chunks": source_chunks,
        "retrieval_index_revision": retrieval_index_revision,
    }
    if not watcher_internal_update:
        artifacts["freshness"] = freshness_report
    _emit_heartbeat(heartbeat, stage="core_artifact_write_start")
    store.write_context_update(artifacts)
    _emit_heartbeat(heartbeat, stage="core_artifact_write_done")

    result_warnings = _dedupe_strings(
        [
            *generation_warnings,
            *list(freshness_report.get("warnings") or []),
        ]
    )
    return {
        "status": "failed" if freshness_report["status"] == "failed" else "updated",
        "mode": mode_name,
        "updated_sources": updated_sources,
        "skipped_sources": skipped_sources,
        "failed_sources": _source_refs_for_sections(failed_sections),
        "failed_sections": failed_sections,
        "updated_sections": updated_sections,
        "skipped_sections": skipped_sections,
        "regenerated_chapter_anchors": sorted({section["chapter_id"] for section in sections if section["section_id"] in changed_ids}),
        "retrieval_index_status": retrieval_index_revision["status"],
        "retrieval_index_artifact_revision": retrieval_index_revision.get("artifact_revision"),
        "source_update_diff": (retrieval_index_revision.get("diagnostics") or {}).get("source_update_diff"),
        "potential_conflicts": potential_conflicts,
        "conflict_review_items": conflict_review_items,
        "pending_conflict_count": pending_conflict_count,
        "unreflected_conflict_resolutions": unreflected_conflicts,
        "stale_resolution_count": stale_resolution_count,
        "freshness_report": freshness_report,
        "warnings": result_warnings,
        "diagnostics": generation_diagnostics,
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
    value = _config_get(config, ("watcher", "state_file"), ".spec-grag/state/watch_state.json")
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


def _build_retrieval_index_revision(
    config: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
    previous_source_chunks: Mapping[str, Any] | None = None,
    previous_revision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    collection = str(_config_get(config, ("vector_store", "collection"), "spec_grag_source"))
    embedding_provider = str(_config_get(config, ("embedding", "provider"), ""))
    vector_store_provider = str(_config_get(config, ("vector_store", "provider"), ""))
    reusable = _reusable_retrieval_index_revision(
        previous_source_chunks,
        previous_revision,
        chunks,
        generated_at=generated_at,
    )
    if reusable is not None:
        return reusable
    if embedding_provider != "flagembedding" or vector_store_provider != "qdrant":
        artifact = retrieval_index_api.build_retrieval_index_revision_artifact(
            chunks=chunks,
            collection=collection,
            generated_at=generated_at,
        )
        artifact["status"] = "success"
        artifact["diagnostics"] = {
            "real_retrieval_index": False,
            "provider_mode": "offline",
            "reason": (
                "non-standard retrieval providers are treated as offline/fake "
                "profile and do not create a Qdrant index"
            ),
            "embedding_provider": embedding_provider,
            "vector_store_provider": vector_store_provider,
            "fusion_method": "rrf",
        }
        return artifact
    if _real_retrieval_enabled():
        url = str(_config_get(config, ("vector_store", "url"), "http://localhost:6333"))
        try:
            artifact = retrieval_index_api.upsert_qdrant_bge_m3_index(
                chunks,
                url=url,
                collection=collection,
                generated_at=generated_at,
            )
            _attach_retrieval_source_update_diff(
                artifact,
                previous_source_chunks=previous_source_chunks,
                previous_revision=previous_revision,
                chunks=chunks,
            )
            return artifact
        except Exception as exc:
            artifact = _failed_retrieval_index_revision_artifact(
                chunks,
                collection=collection,
                url=url,
                generated_at=generated_at,
                exc=exc,
            )
            _attach_retrieval_source_update_diff(
                artifact,
                previous_source_chunks=previous_source_chunks,
                previous_revision=previous_revision,
                chunks=chunks,
            )
            return artifact

    artifact = retrieval_index_api.build_retrieval_index_revision_artifact(
        chunks=chunks,
        collection=collection,
        generated_at=generated_at,
    )
    artifact["status"] = "skipped"
    artifact["diagnostics"] = {
        "real_retrieval_index": False,
        "reason": (
            "real Qdrant/BGE-M3 indexing requires SPEC_GRAG_REAL_RETRIEVAL=1 "
            "for normal operation, or SPEC_GRAG_REAL_SMOKE=1 and "
            "SPEC_GRAG_LOCAL_SERVICE=1 for explicit smoke tests"
        ),
        "fusion_method": "rrf",
    }
    return artifact


def _attach_retrieval_source_update_diff(
    artifact: dict[str, Any],
    *,
    previous_source_chunks: Mapping[str, Any] | None,
    previous_revision: Mapping[str, Any] | None,
    chunks: Sequence[Mapping[str, Any]],
) -> None:
    if not previous_revision and not previous_source_chunks:
        return
    old_revision = (
        str(previous_revision.get("artifact_revision"))
        if isinstance(previous_revision, Mapping) and previous_revision.get("artifact_revision")
        else None
    )
    new_revision = str(artifact.get("artifact_revision") or "")
    previous_chunks = (
        previous_source_chunks.get("chunks", [])
        if isinstance(previous_source_chunks, Mapping)
        else []
    )
    diff = _source_update_diff(
        previous_chunks if isinstance(previous_chunks, Sequence) else [],
        chunks,
        old_revision=old_revision,
        new_revision=new_revision,
    )
    if diff["changed"]:
        diagnostics = dict(artifact.get("diagnostics") or {})
        diagnostics["source_update_diff"] = diff
        artifact["diagnostics"] = diagnostics


def _source_update_diff(
    previous_chunks: Sequence[Any],
    chunks: Sequence[Any],
    *,
    old_revision: str | None,
    new_revision: str,
) -> dict[str, Any]:
    old_by_uid = {
        str(chunk.get("stable_chunk_uid")): dict(chunk)
        for raw_chunk in previous_chunks
        for chunk in (_chunk_payload(raw_chunk),)
        if chunk.get("stable_chunk_uid")
    }
    new_by_uid = {
        str(chunk.get("stable_chunk_uid")): dict(chunk)
        for raw_chunk in chunks
        for chunk in (_chunk_payload(raw_chunk),)
        if chunk.get("stable_chunk_uid")
    }
    changed_uids = {
        uid
        for uid, chunk in new_by_uid.items()
        if uid not in old_by_uid
        or old_by_uid[uid].get("chunk_hash") != chunk.get("chunk_hash")
    }
    removed_uids = set(old_by_uid) - set(new_by_uid)
    changed_sections = sorted(
        {
            str(new_by_uid[uid].get("source_section_id"))
            for uid in changed_uids
            if new_by_uid[uid].get("source_section_id")
        }
    )
    removed_sections = sorted(
        {
            str(old_by_uid[uid].get("source_section_id"))
            for uid in removed_uids
            if old_by_uid[uid].get("source_section_id")
        }
    )
    changed_sources = sorted(
        {
            str(chunk.get("source_document_id"))
            for uid in changed_uids
            for chunk in (new_by_uid[uid],)
            if chunk.get("source_document_id")
        }
        | {
            str(chunk.get("source_document_id"))
            for uid in removed_uids
            for chunk in (old_by_uid[uid],)
            if chunk.get("source_document_id")
        }
    )
    return {
        "changed": bool(changed_uids or removed_uids or (old_revision and old_revision != new_revision)),
        "trigger": "source_specs_update",
        "old_revision": old_revision,
        "new_revision": new_revision,
        "changed_sources": changed_sources,
        "changed_sections": changed_sections,
        "removed_sections": removed_sections,
        "changed_chunk_count": len(changed_uids),
        "removed_chunk_count": len(removed_uids),
    }


def _chunk_payload(chunk: Any) -> dict[str, Any]:
    if isinstance(chunk, Mapping):
        return dict(chunk)
    to_payload = getattr(chunk, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, Mapping):
            return dict(payload)
    return {}


def _failed_retrieval_index_revision_artifact(
    chunks: Sequence[Mapping[str, Any]],
    *,
    collection: str,
    url: str,
    generated_at: str,
    exc: Exception,
) -> dict[str, Any]:
    artifact = retrieval_index_api.build_retrieval_index_revision_artifact(
        chunks=chunks,
        collection=collection,
        generated_at=generated_at,
    )
    artifact["status"] = "failed"
    artifact["diagnostics"] = {
        "real_retrieval_index": False,
        "reason_code": _classify_retrieval_failure(exc),
        "message": str(exc),
        "exception_type": type(exc).__name__,
        "qdrant_url": url,
        "collection": collection,
        "embedding_model": "BAAI/bge-m3",
        "fusion_method": "rrf",
    }
    return artifact


def _classify_retrieval_failure(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    module = getattr(exc.__class__, "__module__", "")
    if "unauthor" in text or "not logged in" in text or "authentication" in text:
        return "agent_cli_unauthenticated"
    if "timeout" in text or "timed out" in text:
        return "provider_timeout"
    if (
        "schema" in text
        or "vector params" in text
        or "dimension" in text
        or ("dense" in text and "size" in text)
    ):
        return "qdrant_schema_mismatch"
    if _is_model_load_failure(exc, module=module, text=text):
        return "embedding_model_load_failure"
    if (
        "qdrant" in module
        or "connection" in text
        or "connect" in text
        or "refused" in text
        or "service unavailable" in text
        or "http" in text
    ):
        return "qdrant_service_unavailable"
    return "retrieval_index_failure"


def _is_model_load_failure(exc: Exception, *, module: str, text: str) -> bool:
    if "flagembedding" in module.lower():
        return True
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return True
    return any(
        term in text
        for term in (
            "flagembedding",
            "bge-m3",
            "huggingface",
            "model",
            "safetensors",
            "torch",
        )
    )


def _reusable_retrieval_index_revision(
    previous_source_chunks: Mapping[str, Any] | None,
    previous_revision: Mapping[str, Any] | None,
    chunks: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any] | None:
    if not previous_source_chunks or not previous_revision:
        return None
    if str(previous_revision.get("status", "")).lower() != "success":
        return None
    previous_chunks = previous_source_chunks.get("chunks")
    if not isinstance(previous_chunks, Sequence) or isinstance(previous_chunks, (str, bytes)):
        return None
    current_fingerprint = _retrieval_chunk_fingerprint(chunks)
    previous_fingerprint = _retrieval_chunk_fingerprint(
        [item for item in previous_chunks if isinstance(item, Mapping)]
    )
    if current_fingerprint != previous_fingerprint:
        return None
    artifact = dict(previous_revision)
    artifact["generated_at"] = generated_at
    diagnostics = dict(artifact.get("diagnostics") or {})
    diagnostics["embedding_generation_skipped"] = True
    diagnostics["skip_reason"] = "source_hash_unchanged"
    artifact["diagnostics"] = diagnostics
    return artifact


def _retrieval_chunk_fingerprint(chunks: Sequence[Any]) -> list[tuple[str, str, str]]:
    return sorted(
        (
            str(_chunk_field(chunk, "stable_chunk_uid")),
            str(_chunk_field(chunk, "source_hash")),
            str(_chunk_field(chunk, "chunk_hash")),
        )
        for chunk in chunks
    )


def _chunk_field(chunk: Any, field: str) -> Any:
    if isinstance(chunk, Mapping):
        return chunk.get(field, "")
    return getattr(chunk, field, "")


def _real_retrieval_enabled() -> bool:
    true_values = {"1", "true", "yes", "on"}
    normal_operation_enabled = (
        os.environ.get("SPEC_GRAG_REAL_RETRIEVAL", "").lower() in true_values
    )
    smoke_enabled = (
        os.environ.get("SPEC_GRAG_REAL_SMOKE", "").lower() in true_values
        and os.environ.get("SPEC_GRAG_LOCAL_SERVICE", "").lower() in true_values
    )
    return normal_operation_enabled or smoke_enabled


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
) -> Any:
    explicit = provider if provider is not None else llm_provider
    if explicit is not None:
        return explicit
    return llm_provider_api.build_spec_core_llm_provider(
        _config_get(config, ("llm",), {}),
    )


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
            entry.setdefault("heading_level", section.get("heading_level"))
            entry.setdefault("source_hash", section.get("source_hash"))
            entry.setdefault("semantic_hash", section.get("semantic_hash"))
        else:
            entry.setdefault("source_section_id", section_id)
        entry.setdefault("metadata_version", 1)
        entry["prompt_version"] = "section-metadata-v1"
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
) -> Any:
    try:
        return related_sections_api.generate_related_sections_result(
            sections,
            section_metadata=section_metadata,
            provider=provider,
            config=config,
            generated_at=generated_at,
        )
    except Exception as exc:
        return {
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
            "generated_at": generated_at,
        }


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


def _conflict_candidates_from_related_output(
    candidates: Sequence[Mapping[str, Any]],
    *,
    sections: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    sections_by_id = {
        str(section.get("source_section_id") or section.get("section_id")): section
        for section in sections
    }
    conflict_candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        source_id = str(candidate.get("source_section_id") or "")
        target_id = str(candidate.get("target_section_id") or "")
        if not source_id or not target_id or source_id == target_id:
            continue
        key = tuple(sorted((source_id, target_id)))
        if key in seen:
            continue
        source = sections_by_id.get(source_id)
        target = sections_by_id.get(target_id)
        if source is None or target is None:
            continue
        channels = set(_list_of_strings(candidate.get("channels")))
        if (
            candidate.get("relation_hint") != "conflicts_with"
            and not (channels & CONFLICT_CANDIDATE_CHANNELS)
        ):
            continue
        source_signal = _conflict_signal(str(source.get("text", "")))
        target_signal = _conflict_signal(str(target.get("text", "")))
        if not _has_conflict_tension(source_signal, target_signal):
            continue
        item = dict(candidate)
        item["source_section_id"] = source_id
        item["target_section_id"] = target_id
        item["relation_hint"] = "conflicts_with"
        item["reason"] = (
            "Related Sections candidate has conflicting requirement, prohibition, "
            "or optionality language in the linked Source Specs."
        )
        item["evidence_terms"] = _dedupe_strings(
            [
                *_list_of_strings(candidate.get("evidence_terms")),
                *source_signal["terms"],
                *target_signal["terms"],
            ]
        )
        item["channels"] = _list_of_strings(candidate.get("channels"))
        conflict_candidates.append(item)
        seen.add(key)
    return conflict_candidates


def _conflict_signal(text: str) -> dict[str, Any]:
    lowered = text.lower()
    categories: set[str] = set()
    terms: list[str] = []
    for term in FORBID_TERMS:
        if term in lowered:
            categories.add("forbid")
            terms.append(term)
    for term in REQUIRE_TERMS:
        if term in lowered:
            categories.add("require")
            terms.append(term)
    if MUST_RE.search(lowered):
        categories.add("require")
        terms.append("must")
    for term in OPTIONAL_TERMS:
        if term in lowered:
            categories.add("optional")
            terms.append(term)
    return {"categories": categories, "terms": _dedupe_strings(terms)}


def _has_conflict_tension(source: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    source_categories = set(source.get("categories", set()))
    target_categories = set(target.get("categories", set()))
    if "require" in source_categories and "forbid" in target_categories:
        return True
    if "forbid" in source_categories and "require" in target_categories:
        return True
    if "require" in source_categories and "optional" in target_categories:
        return True
    return "optional" in source_categories and "require" in target_categories


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
    ) -> None:
        self.delegate = delegate
        self.purpose_ref = purpose_ref
        self.purpose_text = purpose_text
        self.purpose_hash = purpose_hash
        self.concept_ref = concept_ref
        self.concept_text = concept_text
        self.concept_hash = concept_hash

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
        return _call_conflict_judge(self.delegate, grounded_request, timeout_sec=timeout_sec)


def _call_conflict_judge(delegate: Any, request: dict[str, Any], *, timeout_sec: int) -> dict[str, Any]:
    if delegate is None:
        return {"outcome": "needs_human_review", "severity": "medium"}
    for method_name in ("judge_conflict", "judge", "generate"):
        method = getattr(delegate, method_name, None)
        if not callable(method):
            continue
        try:
            return dict(method(request, timeout_sec=timeout_sec))
        except TypeError:
            return dict(method(request))
    if callable(delegate):
        return dict(delegate(request))
    raise TypeError("conflict_judge must expose judge_conflict, judge, generate, or be callable")


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


def _chapter_anchors(sections: Sequence[Mapping[str, Any]], metadata: Sequence[Mapping[str, Any]], generated_at: str) -> dict[str, Any]:
    by_id = {entry["section_id"]: entry for entry in metadata}
    chapters = build_empty_chapter_anchors(list(sections))["chapters"]
    for chapter in chapters:
        section_ids = chapter["source_section_ids"]
        chapter["summary"] = " / ".join(by_id.get(section_id, {}).get("summary", "") for section_id in section_ids).strip(" /")
        chapter["key_topics"] = [key for section_id in section_ids for key in by_id.get(section_id, {}).get("search_keys", [])[:1]]
        chapter["important_sections"] = section_ids[:3]
        chapter["generated_at"] = generated_at
    return {"status": "success", "chapters": chapters, "generated_at": generated_at}


def _section_manifest_entry(section: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: section[key]
        for key in (
            "section_id",
            "source_section_id",
            "source_document_id",
            "source_hash",
            "semantic_hash",
            "chapter_id",
            "heading_path",
            "heading_level",
            "source_span",
        )
    }


def _source_chunk(section: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": f"{section['section_id']}::chunk-1",
        "source_section_id": section["section_id"],
        "text": section.get("text", ""),
        "source_hash": section["source_hash"],
    }


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
