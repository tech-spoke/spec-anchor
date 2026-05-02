"""GRAG readiness gate for foreground commands and watcher diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from spec_grag.chunk_index import (
    BM25_INDEX_FILENAME,
    CHUNK_VECTOR_INDEX_FILENAME,
    DOCUMENT_CHUNKS_FILENAME,
)
from spec_grag.retrieval_index import RETRIEVAL_INDEX_FILENAME
from spec_grag.conflict_review import pending_conflict_candidate_ids
from spec_grag.concept_diff import first_unresolved_pending_concept_diff
from spec_grag.concept_index import concept_index_path, configured_concept_file, load_concept_index
from spec_grag.config import ExecutionRole, RuntimePolicy, resolve_runtime_policy
from spec_grag.core import (
    EXTRACTOR_VERSION,
    GRAPH_STORE_FILENAME,
    VECTOR_STORE_FILENAME,
    artifact_revision_diagnostics,
    graph_revision_for_manifest,
    resolve_source_paths,
)
from spec_grag.core_extraction import (
    EXTRACTION_MODE_SCHEMA_LLM,
    SCHEMA_LLM_EXTRACTOR_VERSION,
    extraction_mode,
)
from spec_grag.embedding import (
    embedding_identity_matches,
    embedding_metadata_from_config,
    embedding_metadata_path,
    load_embedding_metadata,
)
from spec_grag.manifest import (
    SourceManifest,
    build_current_section_manifest,
    load_source_manifest,
    reconcile_manifests,
)
from spec_grag.protocol import FreshnessReport, StrictModel
from spec_grag.watch_state import (
    WatchReadinessStatus,
    WatchRunState,
    load_watch_queue,
    load_watch_state,
    semantic_digest_for_manifest,
    watch_queue_path,
    watch_state_path,
)


class ReadinessReason(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ReadinessReport(StrictModel):
    status: WatchReadinessStatus
    generated_at: str
    graph_storage_path: str
    source_manifest_path: str
    watch_state_path: str
    watch_queue_path: str
    runtime_policy: dict[str, Any]
    current_semantic_hash: str | None = None
    last_processed_semantic_hash: str | None = None
    dirty_section_ids: list[str] = Field(default_factory=list)
    format_only_section_ids: list[str] = Field(default_factory=list)
    pending_concept_diff_id: str | None = None
    pending_conflict_candidate_ids: list[str] = Field(default_factory=list)
    watcher_run_state: str = WatchRunState.IDLE.value
    queued_section_ids: list[str] = Field(default_factory=list)
    stale_reason_codes: list[str] = Field(default_factory=list)
    reasons: list[ReadinessReason] = Field(default_factory=list)
    artifact_diagnostics: dict[str, Any] = Field(default_factory=dict)
    foreground_incremental_allowed: bool = False
    watcher_required: bool = False

    def as_freshness_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def evaluate_grag_readiness(
    project_root: Path,
    config: Mapping[str, Any],
    *,
    runtime_policy: RuntimePolicy | None = None,
) -> ReadinessReport:
    policy = runtime_policy or resolve_runtime_policy(config)
    graph_storage = _graph_storage_path(project_root, config)
    manifest_path = graph_storage / "source_manifest.json"
    now = datetime.now(UTC).isoformat()
    reasons: list[ReadinessReason] = []
    stale_codes: list[str] = []

    source_paths = resolve_source_paths(project_root, dict(config))
    current_manifest = build_current_section_manifest(
        project_root,
        source_paths,
        generated_at=now,
        section_max_heading_level=int(
            _mapping(config.get("extraction")).get("section_max_heading_level", 6)
        ),
    )
    previous_manifest = load_source_manifest(manifest_path)
    reconciliation = reconcile_manifests(previous_manifest, current_manifest)
    dirty_section_ids = sorted(
        {
            *reconciliation.changed_section_ids,
            *reconciliation.added_section_ids,
            *reconciliation.removed_section_ids,
            *(
                item.current_section_id
                for item in reconciliation.renamed_sections
            ),
            *(
                item.previous_section_id
                for item in reconciliation.renamed_sections
            ),
        }
    )
    if not previous_manifest.entries and current_manifest.entries:
        dirty_section_ids = sorted(entry.section_id for entry in current_manifest.entries)
        reasons.append(
            ReadinessReason(
                code="initial_graph_build_required",
                message="No processed source manifest exists for current Source specs.",
            )
        )

    if not source_paths:
        stale_codes.append("sources_missing")
        reasons.append(
            ReadinessReason(
                code="sources_missing",
                message="sources.include did not match any files.",
            )
        )

    missing_artifacts = _missing_required_artifacts(graph_storage)
    if missing_artifacts and previous_manifest.entries:
        stale_codes.append("artifact_missing")
        reasons.append(
            ReadinessReason(
                code="artifact_missing",
                message="One or more required GRAG artifacts are missing.",
                details={"artifacts": missing_artifacts},
            )
        )
    elif missing_artifacts and current_manifest.entries:
        reasons.append(
            ReadinessReason(
                code="artifact_missing_initial_build",
                message="GRAG artifacts are missing and can be built incrementally.",
                details={"artifacts": missing_artifacts},
            )
        )

    embedding_metadata = embedding_metadata_from_config(config, generated_at=now)
    existing_embedding_metadata = load_embedding_metadata(
        embedding_metadata_path(graph_storage)
    )
    if _has_embedding_artifacts(graph_storage) and not embedding_identity_matches(
        existing_embedding_metadata, embedding_metadata
    ):
        stale_codes.append("embedding_metadata_mismatch")
        reasons.append(
            ReadinessReason(
                code="embedding_metadata_mismatch",
                message="Embedding metadata does not match the current config.",
                details={
                    "previous": existing_embedding_metadata.identity()
                    if existing_embedding_metadata
                    else None,
                    "current": embedding_metadata.identity(),
                },
            )
        )

    if previous_manifest.entries and (
        previous_manifest.parser_name != current_manifest.parser_name
        or previous_manifest.parser_version != current_manifest.parser_version
    ):
        stale_codes.append("markdown_parser_version_mismatch")
        reasons.append(
            ReadinessReason(
                code="markdown_parser_version_mismatch",
                message="Markdown parser identity changed since the last manifest.",
                details={
                    "previous": {
                        "name": previous_manifest.parser_name,
                        "version": previous_manifest.parser_version,
                    },
                    "current": {
                        "name": current_manifest.parser_name,
                        "version": current_manifest.parser_version,
                    },
                },
            )
        )

    extractor_stale = _extractor_version_stale(previous_manifest, config)
    if extractor_stale:
        stale_codes.append("extractor_version_mismatch")
        reasons.append(
            ReadinessReason(
                code="extractor_version_mismatch",
                message="Extractor version metadata does not match the current config.",
                details={"sections": extractor_stale[:20]},
            )
        )

    if not dirty_section_ids and previous_manifest.entries and not missing_artifacts:
        expected_revision = graph_revision_for_manifest(
            current_manifest,
            embedding_metadata=embedding_metadata,
        )
        revision_mismatches = _graph_revision_mismatches(graph_storage, expected_revision)
        if revision_mismatches:
            stale_codes.append("graph_revision_mismatch")
            reasons.append(
                ReadinessReason(
                    code="graph_revision_mismatch",
                    message="Graph-side artifacts do not match the current manifest revision.",
                    details={"artifacts": revision_mismatches},
                )
            )

    concept_stale = _concept_index_stale(project_root, config, graph_storage)
    if concept_stale is not None:
        stale_codes.append(concept_stale)
        reasons.append(
            ReadinessReason(
                code=concept_stale,
                message="Approved Concept index is not aligned with the Concept file.",
            )
        )

    pending_diff = first_unresolved_pending_concept_diff(
        project_root / ".spec-grag" / "pending"
    )
    pending_conflicts = pending_conflict_candidate_ids(project_root)
    if pending_diff is not None:
        reasons.append(
            ReadinessReason(
                code="pending_concept_diff_unresolved",
                message="A Concept diff is waiting for human approval.",
                details={"diff_id": pending_diff.diff_id},
            )
        )
    for conflict_id in pending_conflicts:
        reasons.append(
            ReadinessReason(
                code="pending_conflict_candidate_unresolved",
                message="A Conflict candidate is waiting for human approval.",
                details={"candidate_id": conflict_id},
            )
        )

    state = load_watch_state(watch_state_path(project_root, config))
    queue = load_watch_queue(watch_queue_path(project_root, config))
    queued_section_ids = sorted({change.source_section_id for change in queue.changes})
    watcher_running_blocks = (
        state.run_state == WatchRunState.RUNNING
        and policy.execution_role != ExecutionRole.BACKGROUND_WATCHER
        and not policy.foreground_incremental
    )
    queue_blocks = bool(queued_section_ids) and not policy.foreground_incremental
    if state.run_state == WatchRunState.FAILED:
        stale_codes.append("watcher_failed")
        reasons.append(
            ReadinessReason(
                code="watcher_failed",
                message="The last watcher run failed.",
                details={"last_error": state.last_error},
            )
        )
    if watcher_running_blocks:
        reasons.append(
            ReadinessReason(
                code="watcher_running",
                message="The background watcher is currently processing Source specs.",
                details={"last_run_id": state.last_run_id},
            )
        )
    if queue_blocks:
        reasons.append(
            ReadinessReason(
                code="watch_queue_pending",
                message="Source spec changes are queued for the watcher.",
                details={"source_section_ids": queued_section_ids},
            )
        )

    if pending_diff is not None or pending_conflicts:
        status = WatchReadinessStatus.PENDING
    elif stale_codes:
        status = WatchReadinessStatus.STALE
    elif dirty_section_ids or watcher_running_blocks or queue_blocks:
        status = WatchReadinessStatus.DIRTY
    else:
        status = WatchReadinessStatus.FRESH

    current_semantic_hash = (
        semantic_digest_for_manifest(current_manifest) if current_manifest.entries else None
    )
    return ReadinessReport(
        status=status,
        generated_at=now,
        graph_storage_path=str(graph_storage),
        source_manifest_path=str(manifest_path),
        watch_state_path=str(watch_state_path(project_root, config)),
        watch_queue_path=str(watch_queue_path(project_root, config)),
        runtime_policy=policy.as_artifact(),
        current_semantic_hash=current_semantic_hash,
        last_processed_semantic_hash=state.last_processed_semantic_hash,
        dirty_section_ids=dirty_section_ids,
        format_only_section_ids=reconciliation.format_only_section_ids,
        pending_concept_diff_id=pending_diff.diff_id if pending_diff is not None else None,
        pending_conflict_candidate_ids=pending_conflicts,
        watcher_run_state=state.run_state.value,
        queued_section_ids=queued_section_ids,
        stale_reason_codes=sorted(set(stale_codes)),
        reasons=reasons,
        artifact_diagnostics=artifact_revision_diagnostics(graph_storage),
        foreground_incremental_allowed=policy.foreground_incremental,
        watcher_required=policy.watcher_required,
    )


def freshness_with_readiness(
    freshness: FreshnessReport,
    readiness: ReadinessReport,
) -> FreshnessReport:
    warnings = list(freshness.warnings)
    if readiness.status != WatchReadinessStatus.FRESH:
        warnings.append(f"readiness:{readiness.status.value}")
    return freshness.model_copy(
        update={
            "readiness_report": readiness.as_freshness_payload(),
            "warnings": warnings,
        }
    )


def _graph_storage_path(project_root: Path, config: Mapping[str, Any]) -> Path:
    configured = _mapping(config.get("graph")).get("storage", ".spec-grag/graph/")
    path = Path(str(configured))
    if not path.is_absolute():
        path = project_root / path
    return path


def _missing_required_artifacts(graph_storage: Path) -> list[str]:
    required = [
        GRAPH_STORE_FILENAME,
        VECTOR_STORE_FILENAME,
        DOCUMENT_CHUNKS_FILENAME,
        CHUNK_VECTOR_INDEX_FILENAME,
        BM25_INDEX_FILENAME,
        RETRIEVAL_INDEX_FILENAME,
        "embedding_metadata.json",
        "source_manifest.json",
        "unresolved_relations.json",
        "chapter_anchors.json",
        "cluster_snapshot.json",
    ]
    return [filename for filename in required if not (graph_storage / filename).exists()]


def _has_embedding_artifacts(graph_storage: Path) -> bool:
    return any(
        (graph_storage / filename).exists()
        for filename in (
            GRAPH_STORE_FILENAME,
            VECTOR_STORE_FILENAME,
            CHUNK_VECTOR_INDEX_FILENAME,
        )
    )


def _extractor_version_stale(
    manifest: SourceManifest,
    config: Mapping[str, Any],
) -> list[str]:
    if not manifest.entries:
        return []
    try:
        mode = extraction_mode(dict(config))
    except ValueError:
        return [entry.section_id for entry in manifest.entries]
    expected = {"core": EXTRACTOR_VERSION}
    if mode == EXTRACTION_MODE_SCHEMA_LLM:
        expected["schema_llm_path_extractor"] = SCHEMA_LLM_EXTRACTOR_VERSION
    stale = []
    for entry in manifest.entries:
        versions = entry.extractor_versions or {}
        for key, value in expected.items():
            if versions.get(key) != value:
                stale.append(entry.section_id)
                break
    return stale


def _graph_revision_mismatches(graph_storage: Path, expected_revision: str) -> list[str]:
    mismatches = []
    for filename in ("cluster_snapshot.json", DOCUMENT_CHUNKS_FILENAME):
        path = graph_storage / filename
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            mismatches.append(filename)
            continue
        revision = data.get("graph_revision")
        if revision and revision != expected_revision:
            mismatches.append(filename)
    return mismatches


def _concept_index_stale(
    project_root: Path,
    config: Mapping[str, Any],
    graph_storage: Path,
) -> str | None:
    concept_file = configured_concept_file(project_root, config)
    index_path = concept_index_path(graph_storage)
    if concept_file is None or not concept_file.exists():
        return None if not index_path.exists() else "concept_index_orphaned"
    if not index_path.exists():
        return "concept_index_missing"
    try:
        index = load_concept_index(index_path)
    except Exception:
        return "concept_index_invalid"
    if index is None:
        return "concept_index_missing"
    current_hash = _file_sha256(concept_file)
    if index.concept_file_hash != current_hash:
        return "concept_index_hash_mismatch"
    embedding_metadata = embedding_metadata_from_config(config)
    if not embedding_identity_matches(index.embedding_metadata, embedding_metadata):
        return "concept_index_embedding_metadata_mismatch"
    return None


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
