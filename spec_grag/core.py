"""Core update orchestration for /spec-core."""

from __future__ import annotations

import hashlib
import glob
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode, Relation
from llama_index.core.vector_stores.simple import SimpleVectorStore

from spec_grag.concept_index import (
    ConceptDiffProposalError,
    concept_index_path,
    configured_concept_file,
    generate_concept_diff_candidate,
    load_concept_index,
    refresh_concept_index,
)
from spec_grag.config import ExecutionRole
from spec_grag.concept_diff import concept_file_hash
from spec_grag.conflict_review import generate_source_conflict_review
from spec_grag.chunk_index import (
    BM25_INDEX_FILENAME,
    CHUNK_VECTOR_INDEX_FILENAME,
    DOCUMENT_CHUNKS_FILENAME,
    build_bm25_index,
    build_chunk_vector_index,
    build_document_chunks,
    load_chunk_vector_index,
    stable_chunk_uid_for,
    write_bm25_index_atomic,
    write_chunk_vector_index_atomic,
    write_document_chunks_atomic,
)
from spec_grag.core_extraction import (
    EXTRACTION_MODE_SCHEMA_LLM,
    SCHEMA_LLM_EXTRACTOR_VERSION,
    SchemaExtractor,
    carry_forward_schema_llm_artifacts,
    extract_schema_llm_artifacts,
    extraction_mode,
    make_extraction_llm_from_config,
    make_schema_extractor_from_config,
    schema_llm_batch_enabled,
)
from spec_grag.embedding import (
    EmbeddingProviderError,
    EmbeddingMetadata,
    embedding_for_text,
    embedding_identity_matches,
    embedding_metadata_from_config,
    embedding_metadata_path,
    embedding_mismatch_warning,
    load_embedding_metadata,
    stable_embedding,
    write_embedding_metadata_atomic,
)
from spec_grag.graph_ops import safe_delete_by_section
from spec_grag.llm_adapters import ClaudeCLIAdapter, CodexCLIAdapter
from spec_grag.manifest import (
    ManifestReconciliation,
    ManifestUpdateStatus,
    SourceManifest,
    SourceManifestEntry,
    build_current_section_manifest,
    inherit_stable_section_identities,
    load_source_manifest,
    next_source_manifest,
    reconcile_manifests,
    write_source_manifest_atomic,
)
from spec_grag.protocol import FreshnessReport, ResultStatus
from spec_grag.retrieval import add_entities_to_vector_store
from spec_grag.retrieval_index import (
    RETRIEVAL_INDEX_FILENAME,
    build_retrieval_index,
    write_retrieval_index_atomic,
)
from spec_grag.sidecars import (
    ChapterAnchorsSidecar,
    CommunityReportGenerationError,
    UnresolvedRelationsSidecar,
    build_cluster_snapshot,
    drop_unresolved_relations_by_sections,
    load_chapter_anchors,
    load_cluster_snapshot,
    load_unresolved_relations,
    refresh_chapter_anchors,
    refresh_cluster_snapshot,
    upsert_unresolved_relations,
    write_chapter_anchors_atomic,
    write_cluster_snapshot_atomic,
    write_unresolved_relations_atomic,
)
from spec_grag.timing import (
    TimingRecorder,
    embedding_config_metrics,
    llm_config_metrics,
)


EXTRACTOR_VERSION = "deterministic-core-v1"
GRAPH_STORE_FILENAME = "property_graph_store.json"
VECTOR_STORE_FILENAME = "vector_store.json"
ARTIFACT_REVISION_FILENAME = "artifact_revision.json"
FAILED_ARTIFACT_REVISIONS_FILENAME = "failed_revisions.json"
MAX_FAILED_ARTIFACT_REVISIONS = 10


@dataclass(frozen=True)
class CoreUpdate:
    status: ResultStatus
    mode: str
    updated_sources: list[str]
    skipped_sources: list[str]
    failed_sources: list[str]
    graph_storage: str
    freshness_report: FreshnessReport
    warnings: list[str] = field(default_factory=list)
    reconciliation: ManifestReconciliation | None = None
    concept_diff: dict[str, Any] | None = None
    pending_concept_diff_id: str | None = None
    conflict_review: dict[str, Any] | None = None
    pending_conflict_review_id: str | None = None
    execution_role: str = ExecutionRole.FOREGROUND_HUMAN.value
    timing_summary: dict[str, Any] = field(default_factory=dict)
    stage_timings: list[dict[str, Any]] = field(default_factory=list)


def run_core_update(
    project_root: Path,
    config: dict[str, Any],
    *,
    all_sources: bool,
    schema_extractor: SchemaExtractor | None = None,
    execution_role: ExecutionRole | str = ExecutionRole.FOREGROUND_HUMAN,
    source_manifest: SourceManifest | None = None,
    source_document_texts: Mapping[str, str] | None = None,
    timer: TimingRecorder | None = None,
) -> CoreUpdate:
    timer = timer or TimingRecorder()
    graph_storage = _graph_storage_path(project_root, config)
    scanned_at = datetime.now(UTC).isoformat()
    extract_run_id = f"core-{hashlib.sha256(scanned_at.encode('utf-8')).hexdigest()[:12]}"
    embedding_metadata = embedding_metadata_from_config(config, generated_at=scanned_at)
    embedding_metadata_file = embedding_metadata_path(graph_storage)
    previous_embedding_metadata = load_embedding_metadata(embedding_metadata_file)
    existing_embedding_artifacts = (
        (graph_storage / GRAPH_STORE_FILENAME).exists()
        or (graph_storage / VECTOR_STORE_FILENAME).exists()
        or (graph_storage / CHUNK_VECTOR_INDEX_FILENAME).exists()
    )
    if (
        not all_sources
        and existing_embedding_artifacts
        and not embedding_identity_matches(previous_embedding_metadata, embedding_metadata)
    ):
        warnings = [embedding_mismatch_warning(previous_embedding_metadata, embedding_metadata)]
        with timer.stage(
            "embedding_update",
            metrics={**embedding_config_metrics(config), "operation": "metadata_check"},
            status="failed",
        ):
            pass
        freshness = FreshnessReport(
            last_core_run=scanned_at,
            graph_revision=None,
            graph_storage_path=str(graph_storage),
            source_manifest_path=str(graph_storage / "source_manifest.json"),
            warnings=warnings,
        )
        return _with_core_timing(CoreUpdate(
            status=ResultStatus.FAILED,
            mode="incremental",
            updated_sources=[],
            skipped_sources=[],
            failed_sources=["embedding_metadata"],
            graph_storage=str(graph_storage),
            freshness_report=freshness,
            warnings=warnings,
        ), timer)
    try:
        mode = extraction_mode(config)
        if mode == EXTRACTION_MODE_SCHEMA_LLM and schema_extractor is None:
            if schema_llm_batch_enabled(config):
                make_extraction_llm_from_config(config)
            else:
                schema_extractor = make_schema_extractor_from_config(config)
    except ValueError as exc:
        freshness = FreshnessReport(
            last_core_run=scanned_at,
            graph_revision=None,
            graph_storage_path=str(graph_storage),
            source_manifest_path=str(graph_storage / "source_manifest.json"),
            warnings=[f"config_invalid:{exc}"],
        )
        return _with_core_timing(CoreUpdate(
            status=ResultStatus.FAILED,
            mode="full" if all_sources else "incremental",
            updated_sources=[],
            skipped_sources=[],
            failed_sources=["config"],
            graph_storage=str(graph_storage),
            freshness_report=freshness,
            warnings=freshness.warnings,
        ), timer)

    with timer.stage("manifest_reconcile") as stage:
        source_paths = resolve_source_paths(project_root, config)
        stage.metrics["source_files"] = len(source_paths)

        if not source_paths and source_manifest is None:
            stage.set_status("failed")
            freshness = FreshnessReport(
                last_core_run=scanned_at,
                graph_revision=None,
                graph_storage_path=str(graph_storage),
                source_manifest_path=str(graph_storage / "source_manifest.json"),
                warnings=["sources.include did not match any files"],
            )
            return _with_core_timing(CoreUpdate(
                status=ResultStatus.FAILED,
                mode="full" if all_sources else "incremental",
                updated_sources=[],
                skipped_sources=[],
                failed_sources=["sources.include"],
                graph_storage=str(graph_storage),
                freshness_report=freshness,
                warnings=freshness.warnings,
            ), timer)

        manifest_path = graph_storage / "source_manifest.json"
        stored_manifest = load_source_manifest(manifest_path)
        previous_manifest = SourceManifest(entries=[]) if all_sources else stored_manifest
        current_manifest = source_manifest or build_current_section_manifest(
            project_root,
            source_paths,
            generated_at=scanned_at,
            section_max_heading_level=int(
                _mapping(config.get("extraction")).get("section_max_heading_level", 6)
            ),
            document_texts=source_document_texts,
        )
        current_manifest = inherit_stable_section_identities(
            stored_manifest,
            current_manifest,
        )
        reconciliation = reconcile_manifests(previous_manifest, current_manifest)
        graph_revision = graph_revision_for_manifest(
            current_manifest,
            embedding_metadata=embedding_metadata,
        )
        stage.metrics.update(
            {
                "current_sections": len(current_manifest.entries),
                "previous_sections": len(previous_manifest.entries),
                "changed_sections": len(reconciliation.changed_section_ids),
                "added_sections": len(reconciliation.added_section_ids),
                "removed_sections": len(reconciliation.removed_section_ids),
                "renamed_sections": len(reconciliation.renamed_sections),
                "format_only_sections": len(reconciliation.format_only_section_ids),
            }
        )
    with timer.stage("semantic_noop_filter") as stage:
        semantic_noop = not (
            reconciliation.changed_section_ids
            or reconciliation.added_section_ids
            or reconciliation.removed_section_ids
        )
        stage.metrics.update(
            {
                "semantic_noop": semantic_noop,
                "format_only": bool(reconciliation.format_only_section_ids),
            }
        )
        can_return_no_change_incremental = _can_return_no_change_incremental(
            project_root,
            config,
            graph_storage,
            reconciliation,
            previous_manifest,
            embedding_metadata,
            graph_revision=graph_revision,
            all_sources=all_sources,
        )
        stage.metrics["fast_path"] = can_return_no_change_incremental
    timer.set_flag("semantic_noop", semantic_noop)
    timer.set_flag("heavy_path", not can_return_no_change_incremental)
    if can_return_no_change_incremental:
        should_write_manifest = (
            reconciliation.format_only_section_ids
            or _manifest_needs_hash_migration(previous_manifest)
        )
        with timer.stage(
            "artifact_write",
            metrics={
                "artifact_count": 1 if should_write_manifest else 0,
                "artifact_kind": "source_manifest",
            },
        ):
            if should_write_manifest:
                next_manifest = next_source_manifest(
                    previous_manifest,
                    current_manifest,
                    status=ManifestUpdateStatus.OK,
                    scanned_at=scanned_at,
                    extract_run_id=extract_run_id,
                    extractor_versions=_extractor_versions_for_mode(mode),
                )
                write_source_manifest_atomic(manifest_path, next_manifest)
        reported_graph_revision = (
            _existing_graph_revision(graph_storage)
            if reconciliation.format_only_section_ids
            else None
        ) or graph_revision
        with timer.stage(
            "conflict_review",
            metrics={"input_sections": len(current_manifest.entries)},
        ):
            conflict_review_result = generate_source_conflict_review(
                project_root=project_root,
                graph_storage=graph_storage,
                manifest=current_manifest,
                graph_revision=reported_graph_revision,
                generated_at=scanned_at,
                document_texts=source_document_texts,
            )
        warnings = [*conflict_review_result.warnings]
        freshness = FreshnessReport(
            last_core_run=scanned_at,
            graph_revision=reported_graph_revision,
            graph_storage_path=str(graph_storage),
            source_manifest_path=str(manifest_path),
            warnings=warnings,
        )
        return _with_core_timing(CoreUpdate(
            status=ResultStatus.OK if not warnings else ResultStatus.DEGRADED,
            mode="incremental",
            updated_sources=updated_sources_for(
                reconciliation,
                all_sources=False,
                current=current_manifest,
            ),
            skipped_sources=skipped_sources_for(reconciliation, all_sources=False),
            failed_sources=[],
            graph_storage=str(graph_storage),
            freshness_report=freshness,
            warnings=warnings,
            reconciliation=reconciliation,
            conflict_review=conflict_review_result.pending_review.model_dump(mode="json")
            if conflict_review_result.pending_review is not None
            else None,
            pending_conflict_review_id=conflict_review_result.pending_review.review_id
            if conflict_review_result.pending_review is not None
            else None,
        ), timer)

    with timer.stage(
        "artifact_write",
        metrics={"artifact_kind": "artifact_staging", "operation": "prepare"},
    ) as stage:
        artifact_graph_storage = _prepare_artifact_staging(graph_storage, graph_revision)
        stage.metrics["staging_path"] = str(artifact_graph_storage)
    artifact_manifest_path = artifact_graph_storage / "source_manifest.json"
    artifact_embedding_metadata_file = embedding_metadata_path(artifact_graph_storage)

    with timer.stage(
        "graph_sidecar_update",
        metrics={"input_sections": len(current_manifest.entries), "operation": "build_graph"},
    ):
        graph_store = build_deterministic_graph(
            current_manifest,
            embedding_metadata=embedding_metadata,
            include_heading_anchors=mode != EXTRACTION_MODE_SCHEMA_LLM,
        )

    extraction_warnings: list[str] = []
    extraction_failed_section_ids: set[str] = set()
    extracted_unresolved_entries = []
    if mode == EXTRACTION_MODE_SCHEMA_LLM:
        previous_graph_store, load_warnings = _load_previous_graph_store(graph_storage)
        extraction_warnings.extend(load_warnings)
        section_ids_to_extract = _section_ids_for_schema_extraction(
            current_manifest,
            reconciliation,
            all_sources=all_sources,
            previous_graph_available=previous_graph_store is not None,
            previous_manifest_has_entries=bool(previous_manifest.entries),
        )
        if previous_graph_store is not None and not all_sources:
            with timer.stage(
                "stale_carry_forward",
                metrics={
                    "kept_sections": len(_keep_section_ids_for_incremental(reconciliation)),
                    "removed_sections": len(reconciliation.removed_section_ids),
                    "changed_sections": len(reconciliation.changed_section_ids),
                    "renamed_sections": len(reconciliation.renamed_sections),
                },
            ):
                for section_id in [
                    *reconciliation.changed_section_ids,
                    *reconciliation.removed_section_ids,
                    *_renamed_previous_section_ids(reconciliation),
                ]:
                    previous_graph_store = safe_delete_by_section(
                        previous_graph_store,
                        section_id=section_id,
                        stable_section_uid=_stable_section_uid_for_cleanup(
                            section_id,
                            previous_manifest=previous_manifest,
                            current_manifest=current_manifest,
                        ),
                    )
                graph_store = carry_forward_schema_llm_artifacts(
                    graph_store,
                    previous_graph_store,
                    keep_section_ids=_keep_section_ids_for_incremental(reconciliation),
                )
        extraction_metrics = llm_config_metrics(
            config,
            "extraction",
            default_provider="codex",
            disabled_providers={"none", "disabled", "deterministic", ""},
        )
        extraction_metrics["input_sections"] = len(section_ids_to_extract)
        extraction_metrics["llm_calls"] = _schema_llm_call_count(
            config,
            section_ids_to_extract,
            schema_extractor=schema_extractor,
        )
        with timer.stage("schema_llm_extraction", metrics=extraction_metrics) as stage:
            extraction_result = extract_schema_llm_artifacts(
                project_root=project_root,
                manifest=current_manifest,
                graph_store=graph_store,
                config=config,
                extract_run_id=extract_run_id,
                extracted_at=scanned_at,
                section_ids_to_extract=section_ids_to_extract,
                schema_extractor=schema_extractor,
                document_texts=source_document_texts,
            )
            stage.metrics["failed_sections"] = len(extraction_result.failed_section_ids)
            if extraction_result.failed_section_ids:
                stage.set_status("degraded")
        graph_store = extraction_result.graph_store
        extraction_warnings.extend(extraction_result.warnings)
        extraction_failed_section_ids = set(extraction_result.failed_section_ids)
        extracted_unresolved_entries = extraction_result.unresolved_entries

    unresolved_path = artifact_graph_storage / "unresolved_relations.json"
    with timer.stage(
        "graph_sidecar_update",
        metrics={
            "operation": "unresolved_relations",
            "input_sections": len(current_manifest.entries),
        },
    ) as stage:
        unresolved = (
            UnresolvedRelationsSidecar(graph_revision=graph_revision, generated_at=scanned_at)
            if all_sources
            else drop_unresolved_relations_by_sections(
                load_unresolved_relations(unresolved_path),
                [
                    *reconciliation.changed_section_ids,
                    *reconciliation.removed_section_ids,
                    *_renamed_previous_section_ids(reconciliation),
                ],
                graph_revision=graph_revision,
                generated_at=scanned_at,
            )
        )
        if extracted_unresolved_entries:
            unresolved = upsert_unresolved_relations(
                unresolved,
                extracted_unresolved_entries,
                graph_revision=graph_revision,
                generated_at=scanned_at,
            )
        stage.metrics["unresolved_entries"] = len(unresolved.entries)
    with timer.stage(
        "artifact_write",
        metrics={"artifact_count": 1, "artifact_kind": "unresolved_relations"},
    ):
        write_unresolved_relations_atomic(unresolved_path, unresolved)

    try:
        embedding_metrics = embedding_config_metrics(config)
        embedding_metrics["input_nodes"] = _embedding_input_node_count(graph_store)
        with timer.stage("embedding_update", metrics=embedding_metrics) as stage:
            previous_vector_store = (
                None if all_sources else _load_previous_vector_store(graph_storage)
            )
            vector_store = build_vector_store(
                graph_store,
                embedding_metadata=embedding_metadata,
                embedding_config=_mapping(config.get("embedding")),
                previous_vector_store=previous_vector_store,
            )
            document_chunks = build_document_chunks(
                project_root,
                current_manifest,
                config=config,
                graph_revision=graph_revision,
                generated_at=scanned_at,
                document_texts=source_document_texts,
            )
            previous_chunk_vector_index = (
                None
                if all_sources
                else load_chunk_vector_index(graph_storage / CHUNK_VECTOR_INDEX_FILENAME)
            )
            chunk_vector_index = build_chunk_vector_index(
                document_chunks,
                embedding_metadata=embedding_metadata,
                embedding_config=_mapping(config.get("embedding")),
                previous_index=previous_chunk_vector_index,
            )
            stage.metrics["input_chunks"] = len(document_chunks.chunks)
    except EmbeddingProviderError as exc:
        _discard_artifact_staging(artifact_graph_storage)
        warnings = [f"embedding_provider_failed:{exc}"]
        return _failed_core_update(
            scanned_at=scanned_at,
            graph_storage=graph_storage,
            mode="full" if all_sources else "incremental",
            failed_sources=["embedding"],
            warnings=warnings,
            reconciliation=reconciliation,
            timer=timer,
            attempted_graph_revision=graph_revision,
            extract_run_id=extract_run_id,
            failed_stage="embedding_update",
            staging_path=artifact_graph_storage,
        )
    with timer.stage(
        "chunk_index_update",
        metrics={"input_chunks": len(document_chunks.chunks)},
    ) as stage:
        bm25_index = build_bm25_index(document_chunks)
        retrieval_index = build_retrieval_index(
            graph_data=graph_store.graph.model_dump(),
            document_chunks=document_chunks,
            graph_revision=graph_revision,
            generated_at=scanned_at,
        )
        stage.metrics["bm25_posting_terms"] = len(bm25_index.postings)
        stage.metrics["retrieval_index_relations"] = len(retrieval_index.relations)

    artifact_graph_storage.mkdir(parents=True, exist_ok=True)
    with timer.stage(
        "artifact_write",
        metrics={"artifact_count": 7, "artifact_kind": "core_graph"},
    ):
        graph_store.persist(str(artifact_graph_storage / GRAPH_STORE_FILENAME))
        vector_store.persist(str(artifact_graph_storage / VECTOR_STORE_FILENAME))
        write_document_chunks_atomic(
            artifact_graph_storage / DOCUMENT_CHUNKS_FILENAME,
            document_chunks,
        )
        write_chunk_vector_index_atomic(
            artifact_graph_storage / CHUNK_VECTOR_INDEX_FILENAME,
            chunk_vector_index,
        )
        write_bm25_index_atomic(artifact_graph_storage / BM25_INDEX_FILENAME, bm25_index)
        write_retrieval_index_atomic(
            artifact_graph_storage / RETRIEVAL_INDEX_FILENAME,
            retrieval_index,
        )
        write_embedding_metadata_atomic(artifact_embedding_metadata_file, embedding_metadata)

    chapter_anchors_path = artifact_graph_storage / "chapter_anchors.json"
    affected_chapters = (
        sorted({entry.chapter_id for entry in current_manifest.entries})
        if all_sources
        else reconciliation.affected_chapter_ids
    )
    with timer.stage(
        "graph_sidecar_update",
        metrics={
            "operation": "chapter_anchors",
            "affected_chapters": len(affected_chapters),
        },
    ) as stage:
        if all_sources:
            chapter_anchors = ChapterAnchorsSidecar(
                graph_revision=graph_revision,
                generated_at=scanned_at,
            )
        else:
            chapter_anchors = load_chapter_anchors(chapter_anchors_path)
        chapter_refresh = refresh_chapter_anchors(
            chapter_anchors,
            graph_store,
            current_manifest,
            affected_chapters,
            graph_revision=graph_revision,
            generated_at=scanned_at,
        )
        stage.metrics["anchor_count"] = len(chapter_refresh.chapter_anchors.anchors)
    with timer.stage(
        "artifact_write",
        metrics={"artifact_count": 1, "artifact_kind": "chapter_anchors"},
    ):
        write_chapter_anchors_atomic(chapter_anchors_path, chapter_refresh.chapter_anchors)

    try:
        with timer.stage(
            "embedding_update",
            metrics={**embedding_config_metrics(config), "operation": "concept_index"},
        ) as stage:
            concept_index, concept_index_warnings = refresh_concept_index(
                project_root,
                config,
                artifact_graph_storage,
                generated_at=scanned_at,
            )
            stage.metrics["input_chunks"] = len(concept_index.chunks) if concept_index else 0
    except EmbeddingProviderError as exc:
        _discard_artifact_staging(artifact_graph_storage)
        warnings = [f"embedding_provider_failed:{exc}"]
        return _failed_core_update(
            scanned_at=scanned_at,
            graph_storage=graph_storage,
            mode="full" if all_sources else "incremental",
            failed_sources=["embedding"],
            warnings=warnings,
            reconciliation=reconciliation,
            timer=timer,
            attempted_graph_revision=graph_revision,
            extract_run_id=extract_run_id,
            failed_stage="concept_index_update",
            staging_path=artifact_graph_storage,
        )
    concept_index_cluster_entries = (
        [
            {
                "concept_chunk_id": chunk.concept_chunk_id,
                "related_anchor_ids": [],
                "related_chapter_ids": [],
            }
            for chunk in concept_index.chunks
        ]
        if concept_index is not None
        else []
    )
    cluster_path = artifact_graph_storage / "cluster_snapshot.json"
    changed_cluster_section_ids = [
        *reconciliation.changed_section_ids,
        *reconciliation.added_section_ids,
        *reconciliation.removed_section_ids,
        *_renamed_current_section_ids(reconciliation),
        *_renamed_previous_section_ids(reconciliation),
    ]
    try:
        community_metrics = llm_config_metrics(
            config,
            "community_report",
            default_provider="deterministic",
            disabled_providers={"deterministic", "template", "none", "disabled", ""},
        )
        community_metrics.update(
            {
                "input_sections": len(changed_cluster_section_ids)
                if not all_sources
                else len(current_manifest.entries),
                "input_chunks": len(document_chunks.chunks),
            }
        )
        with timer.stage("community_report", metrics=community_metrics) as stage:
            if all_sources:
                community_report_llm = make_community_report_llm_from_config(config)
                stage.metrics["llm_calls"] = 0 if community_report_llm is None else 1
                cluster_snapshot = build_cluster_snapshot(
                    graph_store,
                    graph_revision=graph_revision,
                    generated_at=scanned_at,
                    concept_index=concept_index_cluster_entries,
                    document_chunks=document_chunks.chunks,
                    community_report_llm=community_report_llm,
                )
                cluster_warnings: list[str] = []
            else:
                previous_cluster_snapshot = load_cluster_snapshot(cluster_path)
                if _can_reuse_cluster_snapshot(
                    previous_cluster_snapshot,
                    graph_revision=graph_revision,
                    changed_section_ids=changed_cluster_section_ids,
                    concept_index=concept_index_cluster_entries,
                ):
                    stage.metrics["cache_hit"] = True
                    stage.metrics["llm_calls"] = 0
                    cluster_snapshot = previous_cluster_snapshot
                    cluster_warnings = []
                else:
                    community_report_llm = make_community_report_llm_from_config(config)
                    stage.metrics["llm_calls"] = 0 if community_report_llm is None else 1
                    cluster_refresh = refresh_cluster_snapshot(
                        previous_cluster_snapshot,
                        graph_store,
                        changed_section_ids=changed_cluster_section_ids,
                        graph_revision=graph_revision,
                        generated_at=scanned_at,
                        seed_chapter_ids=affected_chapters,
                        concept_index=concept_index_cluster_entries,
                        document_chunks=document_chunks.chunks,
                        community_report_llm=community_report_llm,
                    )
                    cluster_snapshot = cluster_refresh.cluster_snapshot
                    cluster_warnings = cluster_refresh.warnings
            stage.metrics["cluster_count"] = len(cluster_snapshot.clusters)
    except CommunityReportGenerationError as exc:
        _discard_artifact_staging(artifact_graph_storage)
        warnings = [
            *extraction_warnings,
            *chapter_refresh.warnings,
            *concept_index_warnings,
            f"community_report_provider_failed:{exc}",
        ]
        return _failed_core_update(
            scanned_at=scanned_at,
            graph_storage=graph_storage,
            mode="full" if all_sources else "incremental",
            failed_sources=["community_report"],
            warnings=warnings,
            reconciliation=reconciliation,
            timer=timer,
            attempted_graph_revision=graph_revision,
            extract_run_id=extract_run_id,
            failed_stage="community_report",
            staging_path=artifact_graph_storage,
        )
    with timer.stage(
        "artifact_write",
        metrics={"artifact_count": 1, "artifact_kind": "cluster_snapshot"},
    ):
        write_cluster_snapshot_atomic(cluster_path, cluster_snapshot)
    changed_for_concept = _changed_section_ids_for_concept_diff(
        current_manifest,
        reconciliation,
        all_sources=all_sources,
        failed_section_ids=extraction_failed_section_ids,
    )
    current_by_section_id = current_manifest.by_section_id()
    changed_concept_hashes = {
        section_id: (
            current_by_section_id[section_id].semantic_hash
            or current_by_section_id[section_id].source_hash
        )
        for section_id in changed_for_concept
        if section_id in current_by_section_id
    }
    try:
        concept_diff_metrics = llm_config_metrics(
            config,
            "concept_diff",
            default_provider="source_derived",
            disabled_providers={"source_derived", "template", "none", "disabled", ""},
        )
        concept_diff_metrics["input_sections"] = len(changed_for_concept)
        if not changed_for_concept:
            concept_diff_metrics["llm_calls"] = 0
        with timer.stage("concept_diff", metrics=concept_diff_metrics) as stage:
            concept_diff_result = generate_concept_diff_candidate(
                project_root=project_root,
                config=config,
                graph_storage=graph_storage,
                graph_data=graph_store.graph.model_dump(),
                concept_index=concept_index,
                changed_source_section_ids=changed_for_concept,
                changed_source_section_hashes=changed_concept_hashes,
                extract_run_id=extract_run_id,
                generated_at=scanned_at,
            )
            stage.metrics["pending_created"] = (
                concept_diff_result.pending_diff is not None
            )
            stage.metrics["warnings"] = len(concept_diff_result.warnings)
    except ConceptDiffProposalError as exc:
        _discard_artifact_staging(artifact_graph_storage)
        warnings = [
            *extraction_warnings,
            *chapter_refresh.warnings,
            *cluster_warnings,
            *concept_index_warnings,
            f"concept_diff_provider_failed:{exc}",
        ]
        return _failed_core_update(
            scanned_at=scanned_at,
            graph_storage=graph_storage,
            mode="full" if all_sources else "incremental",
            failed_sources=["concept_diff"],
            warnings=warnings,
            reconciliation=reconciliation,
            timer=timer,
            attempted_graph_revision=graph_revision,
            extract_run_id=extract_run_id,
            failed_stage="concept_diff",
            staging_path=artifact_graph_storage,
        )

    manifest_status = (
        ManifestUpdateStatus.DEGRADED
        if extraction_failed_section_ids
        else ManifestUpdateStatus.OK
    )
    extractor_versions = _extractor_versions_for_mode(mode)
    next_manifest = next_source_manifest(
        previous_manifest,
        current_manifest,
        status=manifest_status,
        scanned_at=scanned_at,
        extract_run_id=extract_run_id,
        extractor_versions=extractor_versions,
        failed_section_ids=extraction_failed_section_ids,
    )
    with timer.stage(
        "artifact_write",
        metrics={"artifact_count": 1, "artifact_kind": "source_manifest"},
    ):
        write_source_manifest_atomic(artifact_manifest_path, next_manifest)
    with timer.stage(
        "conflict_review",
        metrics={"input_sections": len(next_manifest.entries)},
    ) as stage:
        conflict_review_result = generate_source_conflict_review(
            project_root=project_root,
            graph_storage=artifact_graph_storage,
            manifest=next_manifest,
            graph_revision=graph_revision,
            generated_at=scanned_at,
            document_texts=source_document_texts,
        )
        stage.metrics["pending_created"] = (
            conflict_review_result.pending_review is not None
        )
        stage.metrics["warnings"] = len(conflict_review_result.warnings)

    with timer.stage(
        "artifact_write",
        metrics={"artifact_kind": "artifact_commit", "operation": "commit"},
    ) as stage:
        try:
            _write_artifact_revision(
                artifact_graph_storage,
                graph_revision=graph_revision,
                extract_run_id=extract_run_id,
                generated_at=scanned_at,
            )
            _commit_artifact_staging(graph_storage, artifact_graph_storage)
        except OSError as exc:
            stage.set_status("failed")
            return _failed_core_update(
                scanned_at=scanned_at,
                graph_storage=graph_storage,
                mode="full" if all_sources else "incremental",
                failed_sources=["artifact_commit"],
                warnings=[
                    *extraction_warnings,
                    *chapter_refresh.warnings,
                    *cluster_warnings,
                    *concept_index_warnings,
                    *concept_diff_result.warnings,
                    *conflict_review_result.warnings,
                    f"artifact_commit_failed:{exc}",
                ],
                reconciliation=reconciliation,
                timer=timer,
                attempted_graph_revision=graph_revision,
                extract_run_id=extract_run_id,
                failed_stage="artifact_commit",
                staging_path=artifact_graph_storage,
            )

    warnings = [
        *extraction_warnings,
        *chapter_refresh.warnings,
        *cluster_warnings,
        *concept_index_warnings,
        *concept_diff_result.warnings,
        *conflict_review_result.warnings,
    ]
    freshness = FreshnessReport(
        last_core_run=scanned_at,
        graph_revision=graph_revision,
        graph_storage_path=str(graph_storage),
        source_manifest_path=str(manifest_path),
        warnings=warnings,
    )
    return _with_core_timing(CoreUpdate(
        status=ResultStatus.OK if not warnings else ResultStatus.DEGRADED,
        mode="full" if all_sources else "incremental",
        updated_sources=updated_sources_for(reconciliation, all_sources=all_sources, current=current_manifest),
        skipped_sources=skipped_sources_for(reconciliation, all_sources=all_sources),
        failed_sources=sorted(extraction_failed_section_ids),
        graph_storage=str(graph_storage),
        freshness_report=freshness,
        warnings=warnings,
        reconciliation=reconciliation,
        concept_diff=concept_diff_result.pending_diff.model_dump(mode="json")
        if concept_diff_result.pending_diff is not None
        else None,
        pending_concept_diff_id=concept_diff_result.pending_diff.diff_id
        if concept_diff_result.pending_diff is not None
        else None,
        conflict_review=conflict_review_result.pending_review.model_dump(mode="json")
        if conflict_review_result.pending_review is not None
        else None,
        pending_conflict_review_id=conflict_review_result.pending_review.review_id
        if conflict_review_result.pending_review is not None
        else None,
        execution_role=str(execution_role),
    ), timer)


def _failed_core_update(
    *,
    scanned_at: str,
    graph_storage: Path,
    mode: str,
    failed_sources: list[str],
    warnings: list[str],
    reconciliation: ManifestReconciliation | None = None,
    timer: TimingRecorder | None = None,
    attempted_graph_revision: str | None = None,
    extract_run_id: str | None = None,
    failed_stage: str | None = None,
    staging_path: Path | None = None,
) -> CoreUpdate:
    failure_warnings = list(warnings)
    if attempted_graph_revision and extract_run_id and failed_stage:
        try:
            _record_failed_artifact_revision(
                graph_storage,
                graph_revision=attempted_graph_revision,
                extract_run_id=extract_run_id,
                failed_at=scanned_at,
                failed_stage=failed_stage,
                warnings=warnings,
                staging_path=staging_path,
            )
        except OSError as exc:
            failure_warnings.append(f"failed_revision_record_failed:{exc}")

    freshness = FreshnessReport(
        last_core_run=scanned_at,
        graph_revision=None,
        graph_storage_path=str(graph_storage),
        source_manifest_path=str(graph_storage / "source_manifest.json"),
        warnings=failure_warnings,
    )
    update = CoreUpdate(
        status=ResultStatus.FAILED,
        mode=mode,
        updated_sources=[],
        skipped_sources=[],
        failed_sources=failed_sources,
        graph_storage=str(graph_storage),
        freshness_report=freshness,
        warnings=failure_warnings,
        reconciliation=reconciliation,
    )
    return _with_core_timing(update, timer) if timer is not None else update


def artifact_revision_diagnostics(graph_storage: Path) -> dict[str, Any]:
    """Return lightweight artifact revision state for readiness diagnostics."""

    return {
        "active_revision": _active_artifact_revision(graph_storage),
        "staging_revisions": _staging_artifact_revisions(graph_storage),
        "failed_revisions": _failed_artifact_revisions(graph_storage),
    }


def _prepare_artifact_staging(graph_storage: Path, graph_revision: str) -> Path:
    safe_revision = _safe_path_component(graph_revision)
    staging = artifact_staging_root(graph_storage) / safe_revision
    if staging.exists():
        shutil.rmtree(staging)
    staging.parent.mkdir(parents=True, exist_ok=True)
    if graph_storage.exists():
        shutil.copytree(
            graph_storage,
            staging,
            ignore=shutil.ignore_patterns(".staging", "*.tmp"),
        )
    else:
        staging.mkdir(parents=True, exist_ok=True)
    return staging


def artifact_staging_root(graph_storage: Path) -> Path:
    return graph_storage.parent / ".staging" / graph_storage.name


def _commit_artifact_staging(graph_storage: Path, staging: Path) -> None:
    if not staging.exists():
        raise OSError(f"staging artifact directory missing: {staging}")
    backup = (
        graph_storage.parent
        / ".staging"
        / "backups"
        / f"{graph_storage.name}-{hashlib.sha256(str(staging).encode('utf-8')).hexdigest()[:12]}"
    )
    if backup.exists():
        shutil.rmtree(backup)
    backup.parent.mkdir(parents=True, exist_ok=True)
    moved_active = False
    try:
        if graph_storage.exists():
            os.replace(graph_storage, backup)
            moved_active = True
        os.replace(staging, graph_storage)
    except OSError:
        if moved_active and backup.exists() and not graph_storage.exists():
            os.replace(backup, graph_storage)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)
        _cleanup_empty_staging_parents(staging.parent)


def _discard_artifact_staging(staging: Path) -> None:
    if staging.exists():
        shutil.rmtree(staging)


def _write_artifact_revision(
    graph_storage: Path,
    *,
    graph_revision: str,
    extract_run_id: str,
    generated_at: str,
) -> None:
    _write_json_atomic(
        graph_storage / ARTIFACT_REVISION_FILENAME,
        {
            "graph_revision": graph_revision,
            "extract_run_id": extract_run_id,
            "generated_at": generated_at,
            "commit_protocol": "staging-directory-v1",
        },
    )


def _active_artifact_revision(graph_storage: Path) -> dict[str, Any] | None:
    payload = _read_json_object(graph_storage / ARTIFACT_REVISION_FILENAME)
    if payload is None:
        return None
    return {**payload, "path": str(graph_storage)}


def _staging_artifact_revisions(graph_storage: Path) -> list[dict[str, Any]]:
    root = artifact_staging_root(graph_storage)
    if not root.exists():
        return []

    revisions: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        payload = _read_json_object(child / ARTIFACT_REVISION_FILENAME) or {}
        revisions.append(
            {
                **payload,
                "staging_name": child.name,
                "path": str(child),
            }
        )
    return revisions


def _failed_artifact_revisions(graph_storage: Path) -> list[dict[str, Any]]:
    payload = _read_json_object(_failed_artifact_revisions_path(graph_storage)) or {}
    raw_revisions = payload.get("failed_revisions", [])
    if not isinstance(raw_revisions, list):
        return []

    revisions: list[dict[str, Any]] = []
    for raw_revision in raw_revisions:
        if not isinstance(raw_revision, dict):
            continue
        revision = dict(raw_revision)
        staging_path = revision.get("staging_path")
        if isinstance(staging_path, str):
            revision["staging_path_exists"] = Path(staging_path).exists()
        revisions.append(revision)
    return revisions


def _record_failed_artifact_revision(
    graph_storage: Path,
    *,
    graph_revision: str,
    extract_run_id: str,
    failed_at: str,
    failed_stage: str,
    warnings: list[str],
    staging_path: Path | None,
) -> None:
    existing = _failed_artifact_revisions(graph_storage)
    entry = {
        "graph_revision": graph_revision,
        "extract_run_id": extract_run_id,
        "failed_at": failed_at,
        "failed_stage": failed_stage,
        "warnings": warnings[:10],
        "staging_path": str(staging_path) if staging_path is not None else None,
        "staging_path_exists": bool(staging_path and staging_path.exists()),
        "commit_protocol": "staging-directory-v1",
    }
    _write_json_atomic(
        _failed_artifact_revisions_path(graph_storage),
        {
            "version": 1,
            "updated_at": failed_at,
            "failed_revisions": [entry, *existing][:MAX_FAILED_ARTIFACT_REVISIONS],
        },
    )


def _failed_artifact_revisions_path(graph_storage: Path) -> Path:
    return artifact_staging_root(graph_storage) / FAILED_ARTIFACT_REVISIONS_FILENAME


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            tmp_path.unlink()


def _cleanup_empty_staging_parents(path: Path) -> None:
    current = path
    for _ in range(3):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _safe_path_component(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value)[:96]


def _with_core_timing(update: CoreUpdate, timer: TimingRecorder) -> CoreUpdate:
    return replace(
        update,
        timing_summary=timer.summary(status=update.status.value),
        stage_timings=timer.stage_timings(),
    )


def resolve_source_paths(project_root: Path, config: dict[str, Any]) -> list[Path]:
    includes = config.get("sources", {}).get("include", [])
    if isinstance(includes, str):
        includes = [includes]
    excludes = config.get("sources", {}).get("exclude", [])
    if isinstance(excludes, str):
        excludes = [excludes]
    resolved: set[Path] = set()
    for pattern in includes:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute():
            matches = (Path(match) for match in glob.glob(pattern, recursive=True))
        else:
            matches = project_root.glob(pattern)
        for match in matches:
            if match.is_file():
                resolved.add(match.resolve())
    excluded: set[Path] = set()
    for pattern in excludes:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute():
            matches = (Path(match) for match in glob.glob(pattern, recursive=True))
        else:
            matches = project_root.glob(pattern)
        for match in matches:
            if match.is_file():
                excluded.add(match.resolve())
    return sorted(resolved - excluded)


def build_deterministic_graph(
    manifest: SourceManifest,
    *,
    embedding_metadata: EmbeddingMetadata | None = None,
    include_heading_anchors: bool = True,
) -> SimplePropertyGraphStore:
    store = SimplePropertyGraphStore()
    metadata = embedding_metadata or embedding_metadata_from_config({})
    documents: dict[str, EntityNode] = {}
    chapters: dict[str, EntityNode] = {}
    sections: dict[str, EntityNode] = {}
    anchors: dict[str, EntityNode] = {}
    relations: list[Relation] = []

    for entry in manifest.entries:
        documents.setdefault(
            entry.document_id,
            EntityNode(
                label="DOCUMENT",
                name=entry.document_id,
                properties={"document_id": entry.document_id},
            ),
        )
        chapters.setdefault(
            entry.chapter_id,
            EntityNode(
                label="CHAPTER",
                name=entry.chapter_id,
                properties={
                    "document_id": entry.document_id,
                    "chapter_id": entry.chapter_id,
                    "heading_path": entry.heading_path.split(" / ")[0],
                },
            ),
        )
        section_node_id = section_node_id_for(entry.section_id)
        sections[section_node_id] = EntityNode(
            label="SECTION",
            name=section_node_id,
            properties={
                "document_id": entry.document_id,
                "chapter_id": entry.chapter_id,
                "section_id": entry.section_id,
                "stable_section_uid": entry.stable_section_uid,
                "source_section_id": entry.section_id,
                "stable_source_section_uid": entry.stable_section_uid,
                "heading_path": entry.heading_path,
                "heading_start_line": entry.heading_start_line,
                "source_hash": entry.source_hash,
                **embedding_properties(metadata),
            },
        )

        section_relations = [
            Relation(
                label="CONTAINS",
                source_id=entry.document_id,
                target_id=entry.chapter_id,
                properties={"deterministic": True, "document_id": entry.document_id},
            ),
            Relation(
                label="CONTAINS",
                source_id=entry.chapter_id,
                target_id=section_node_id,
                properties={
                    "deterministic": True,
                    "document_id": entry.document_id,
                    "chapter_id": entry.chapter_id,
                    "section_id": entry.section_id,
                    "stable_section_uid": entry.stable_section_uid,
                },
            ),
        ]
        if include_heading_anchors:
            anchor = anchor_for_entry(entry, embedding_metadata=metadata)
            anchors[anchor.name] = anchor
            section_relations.append(
                Relation(
                    label="MENTIONS",
                    source_id=section_node_id,
                    target_id=anchor.name,
                    properties={
                        "source_document_id": entry.document_id,
                        "source_chapter_id": entry.chapter_id,
                        "source_section_id": entry.section_id,
                        "stable_section_uid": entry.stable_section_uid,
                        "stable_source_section_uid": entry.stable_section_uid,
                        "source_chunk_id": entry.section_id,
                        "stable_source_chunk_uid": _section_level_stable_chunk_uid(entry),
                        "source_hash": entry.source_hash,
                        "extract_run_id": "deterministic",
                        "extractor_name": "spec-grag-core",
                        "extractor_version": EXTRACTOR_VERSION,
                        "confidence": "high",
                    },
                )
            )
        relations.extend(section_relations)

    store.upsert_nodes([*documents.values(), *chapters.values(), *sections.values(), *anchors.values()])
    store.upsert_relations(_dedupe_relations(relations))
    return store


def build_vector_store(
    graph_store: SimplePropertyGraphStore,
    *,
    embedding_metadata: EmbeddingMetadata | None = None,
    embedding_config: Mapping[str, Any] | None = None,
    previous_vector_store: SimpleVectorStore | None = None,
) -> SimpleVectorStore:
    vector_store = SimpleVectorStore()
    metadata = embedding_metadata or embedding_metadata_from_config({})
    previous_embeddings = _reusable_vector_embeddings(previous_vector_store, metadata)
    entities = []
    text_by_entity_id = {}
    for node in graph_store.get():
        if node.label not in {"ANCHOR", "SECTION"}:
            continue
        props = node.properties or {}
        entity_text = " ".join(
            str(value)
            for value in (
                node.label,
                node.name,
                props.get("heading_path"),
                props.get("description"),
                props.get("evidence_excerpt"),
            )
            if value
        )
        node.embedding = _entity_embedding(
            node,
            entity_text=entity_text,
            reusable_embeddings=previous_embeddings,
            embedding_metadata=metadata,
            embedding_config=embedding_config,
        )
        node.properties = {
            **(node.properties or {}),
            **embedding_properties(metadata),
            "entity_text_hash": hashlib.sha256(entity_text.encode("utf-8")).hexdigest(),
        }
        entities.append(node)
        text_by_entity_id[node.id] = entity_text
    add_entities_to_vector_store(vector_store, entities, text_by_entity_id=text_by_entity_id)
    return vector_store


def _load_previous_vector_store(graph_storage: Path) -> SimpleVectorStore | None:
    vector_path = graph_storage / VECTOR_STORE_FILENAME
    if not vector_path.exists():
        return None
    try:
        return SimpleVectorStore.from_persist_path(str(vector_path))
    except Exception:
        return None


def _reusable_vector_embeddings(
    previous_vector_store: SimpleVectorStore | None,
    embedding_metadata: EmbeddingMetadata,
) -> dict[str, tuple[list[float], Mapping[str, Any]]]:
    if previous_vector_store is None:
        return {}
    reusable: dict[str, tuple[list[float], Mapping[str, Any]]] = {}
    for node_id, embedding in previous_vector_store.data.embedding_dict.items():
        metadata = previous_vector_store.data.metadata_dict.get(node_id, {})
        if not _embedding_metadata_matches(metadata, embedding_metadata):
            continue
        reusable[node_id] = (list(embedding), metadata)
    return reusable


def _entity_embedding(
    node: EntityNode,
    *,
    entity_text: str,
    reusable_embeddings: Mapping[str, tuple[list[float], Mapping[str, Any]]],
    embedding_metadata: EmbeddingMetadata,
    embedding_config: Mapping[str, Any] | None,
) -> list[float]:
    reusable = reusable_embeddings.get(node.id)
    current_source_hash = (node.properties or {}).get("source_hash")
    current_text_hash = hashlib.sha256(entity_text.encode("utf-8")).hexdigest()
    if reusable is not None and current_source_hash:
        embedding, previous_metadata = reusable
        previous_text_hash = previous_metadata.get("entity_text_hash")
        if (
            previous_metadata.get("source_hash") == current_source_hash
            and previous_text_hash == current_text_hash
            and embedding
        ):
            return list(embedding)
    return embedding_for_text(
        entity_text,
        embedding_metadata,
        config=embedding_config,
    )


def _embedding_input_node_count(graph_store: SimplePropertyGraphStore) -> int:
    return sum(1 for node in graph_store.get() if node.label in {"ANCHOR", "SECTION"})


def _schema_llm_call_count(
    config: Mapping[str, Any],
    section_ids_to_extract: list[str],
    *,
    schema_extractor: SchemaExtractor | None,
) -> int:
    if not section_ids_to_extract:
        return 0
    if schema_extractor is not None:
        return len(section_ids_to_extract)
    extraction_config = _mapping(config.get("extraction"))
    batch_size = max(1, int(extraction_config.get("batch_size", 1)))
    if batch_size <= 1:
        return len(section_ids_to_extract)
    return (len(section_ids_to_extract) + batch_size - 1) // batch_size


def _embedding_metadata_matches(
    metadata: Mapping[str, Any],
    embedding_metadata: EmbeddingMetadata,
) -> bool:
    try:
        dimension = int(metadata.get("embedding_dimension", -1))
    except (TypeError, ValueError):
        return False
    return (
        str(metadata.get("embedding_provider", "")) == embedding_metadata.provider
        and str(metadata.get("embedding_model", "")) == embedding_metadata.model
        and dimension == embedding_metadata.dimension
    )


def updated_sources_for(
    reconciliation: ManifestReconciliation,
    *,
    all_sources: bool,
    current: SourceManifest,
) -> list[str]:
    if all_sources:
        return sorted({entry.document_id for entry in current.entries})
    section_ids = [
        *reconciliation.format_only_section_ids,
        *reconciliation.changed_section_ids,
        *reconciliation.added_section_ids,
        *reconciliation.removed_section_ids,
        *_renamed_current_section_ids(reconciliation),
        *_renamed_previous_section_ids(reconciliation),
    ]
    return sorted(section_ids)


def skipped_sources_for(
    reconciliation: ManifestReconciliation,
    *,
    all_sources: bool,
) -> list[str]:
    if all_sources:
        return []
    return reconciliation.unchanged_section_ids


def _renamed_current_section_ids(
    reconciliation: ManifestReconciliation,
) -> list[str]:
    return [item.current_section_id for item in reconciliation.renamed_sections]


def _renamed_previous_section_ids(
    reconciliation: ManifestReconciliation,
) -> list[str]:
    return [item.previous_section_id for item in reconciliation.renamed_sections]


def _stable_section_uid_for_cleanup(
    section_id: str,
    *,
    previous_manifest: SourceManifest,
    current_manifest: SourceManifest,
) -> str | None:
    previous_entry = previous_manifest.by_section_id().get(section_id)
    if previous_entry is not None and previous_entry.stable_section_uid:
        return previous_entry.stable_section_uid
    current_entry = current_manifest.by_section_id().get(section_id)
    if current_entry is not None:
        return current_entry.stable_section_uid
    return None


def graph_revision_for_manifest(
    manifest: SourceManifest,
    *,
    embedding_metadata: EmbeddingMetadata | None = None,
) -> str:
    payload: list[dict[str, Any]] = [
        {
            "document_id": entry.document_id,
            "chapter_id": entry.chapter_id,
            "section_id": entry.section_id,
            "stable_section_uid": entry.stable_section_uid,
            "source_hash": entry.source_hash,
        }
        for entry in sorted(manifest.entries, key=lambda item: item.section_id)
    ]
    if embedding_metadata is not None:
        payload.append({"embedding_metadata": embedding_metadata.identity()})
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"graph:{digest[:24]}"


def section_node_id_for(section_id: str) -> str:
    return f"section:{section_id}"


def _section_level_stable_chunk_uid(entry: SourceManifestEntry) -> str | None:
    if not entry.stable_section_uid:
        return None
    return stable_chunk_uid_for(entry.stable_section_uid, "", 0)


def anchor_for_entry(
    entry: SourceManifestEntry,
    *,
    embedding_metadata: EmbeddingMetadata | None = None,
) -> EntityNode:
    metadata = embedding_metadata or embedding_metadata_from_config({})
    name = entry.heading_path.split(" / ")[-1]
    anchor_id = f"anchor:{entry.section_id}:{_slugify(name)}"
    return EntityNode(
        label="ANCHOR",
        name=anchor_id,
        embedding=stable_embedding(anchor_id, dimensions=metadata.dimension),
        properties={
            "document_id": entry.document_id,
            "chapter_id": entry.chapter_id,
            "section_id": entry.section_id,
            "stable_section_uid": entry.stable_section_uid,
            "source_document_id": entry.document_id,
            "source_chapter_id": entry.chapter_id,
            "source_section_id": entry.section_id,
            "stable_source_section_uid": entry.stable_section_uid,
            "source_chunk_id": entry.section_id,
            "stable_source_chunk_uid": _section_level_stable_chunk_uid(entry),
            "source_hash": entry.source_hash,
            "extract_run_id": "deterministic",
            "extractor_name": "spec-grag-core",
            "extractor_version": EXTRACTOR_VERSION,
            "description": entry.heading_path,
            "evidence_excerpt": entry.heading_path,
            "heading_path": entry.heading_path,
            **embedding_properties(metadata),
        },
    )


def embedding_properties(metadata: EmbeddingMetadata) -> dict[str, Any]:
    return {
        "embedding_provider": metadata.provider,
        "embedding_model": metadata.model,
        "embedding_dimension": metadata.dimension,
    }


def _graph_storage_path(project_root: Path, config: dict[str, Any]) -> Path:
    configured = config.get("graph", {}).get("storage", ".spec-grag/graph/")
    path = Path(configured)
    if not path.is_absolute():
        path = project_root / path
    return path


def _load_previous_graph_store(
    graph_storage: Path,
) -> tuple[SimplePropertyGraphStore | None, list[str]]:
    graph_path = graph_storage / GRAPH_STORE_FILENAME
    if not graph_path.exists():
        return None, []
    try:
        return SimplePropertyGraphStore.from_persist_dir(str(graph_storage)), []
    except Exception as exc:
        return None, [f"previous_graph_load_failed:{exc}"]


def _section_ids_for_schema_extraction(
    current_manifest: SourceManifest,
    reconciliation: ManifestReconciliation,
    *,
    all_sources: bool,
    previous_graph_available: bool,
    previous_manifest_has_entries: bool,
) -> list[str]:
    if all_sources:
        return sorted(entry.section_id for entry in current_manifest.entries)
    if previous_manifest_has_entries and not previous_graph_available:
        return sorted(entry.section_id for entry in current_manifest.entries)
    return sorted(
        {
            *reconciliation.changed_section_ids,
            *reconciliation.added_section_ids,
            *_renamed_current_section_ids(reconciliation),
        }
    )


def _changed_section_ids_for_concept_diff(
    current_manifest: SourceManifest,
    reconciliation: ManifestReconciliation,
    *,
    all_sources: bool,
    failed_section_ids: set[str],
) -> list[str]:
    if all_sources:
        section_ids = {entry.section_id for entry in current_manifest.entries}
    else:
        section_ids = {
            *reconciliation.changed_section_ids,
            *reconciliation.added_section_ids,
        }
    return sorted(section_ids - failed_section_ids)


def _extractor_versions_for_mode(mode: str) -> dict[str, str]:
    versions = {"core": EXTRACTOR_VERSION}
    if mode == EXTRACTION_MODE_SCHEMA_LLM:
        versions["schema_llm_path_extractor"] = SCHEMA_LLM_EXTRACTOR_VERSION
    return versions


def _keep_section_ids_for_incremental(
    reconciliation: ManifestReconciliation,
) -> list[str]:
    return sorted(
        {
            *reconciliation.unchanged_section_ids,
            *reconciliation.format_only_section_ids,
        }
    )


def _can_return_no_change_incremental(
    project_root: Path,
    config: Mapping[str, Any],
    graph_storage: Path,
    reconciliation: ManifestReconciliation,
    previous_manifest: SourceManifest,
    embedding_metadata: EmbeddingMetadata,
    *,
    graph_revision: str,
    all_sources: bool,
) -> bool:
    if all_sources or not previous_manifest.entries:
        return False
    has_semantic_changes = (
        reconciliation.changed_section_ids
        or reconciliation.added_section_ids
        or reconciliation.removed_section_ids
        or reconciliation.renamed_sections
    )
    if has_semantic_changes:
        return False
    if not _required_incremental_artifacts_exist(graph_storage):
        return False
    if reconciliation.format_only_section_ids:
        if not _artifact_has_graph_revision(graph_storage / "cluster_snapshot.json"):
            return False
    else:
        if not _artifact_graph_revision_matches(
            graph_storage / "cluster_snapshot.json",
            graph_revision,
        ):
            return False
    return _concept_index_is_fresh(
        project_root,
        config,
        graph_storage,
        embedding_metadata,
    )


def _required_incremental_artifacts_exist(graph_storage: Path) -> bool:
    required = [
        GRAPH_STORE_FILENAME,
        VECTOR_STORE_FILENAME,
        DOCUMENT_CHUNKS_FILENAME,
        CHUNK_VECTOR_INDEX_FILENAME,
        BM25_INDEX_FILENAME,
        RETRIEVAL_INDEX_FILENAME,
        ARTIFACT_REVISION_FILENAME,
        "embedding_metadata.json",
        "source_manifest.json",
        "unresolved_relations.json",
        "chapter_anchors.json",
        "cluster_snapshot.json",
    ]
    return all((graph_storage / filename).exists() for filename in required)


def _manifest_needs_hash_migration(manifest: SourceManifest) -> bool:
    return any(
        entry.raw_hash is None
        or entry.semantic_hash is None
        or entry.body_semantic_hash is None
        or entry.stable_section_uid is None
        or not entry.section_aliases
        for entry in manifest.entries
    )


def _artifact_has_graph_revision(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("graph_revision"))


def _existing_graph_revision(graph_storage: Path) -> str | None:
    for filename in ("cluster_snapshot.json", DOCUMENT_CHUNKS_FILENAME):
        path = graph_storage / filename
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        revision = data.get("graph_revision")
        if isinstance(revision, str) and revision:
            return revision
    return None


def _artifact_graph_revision_matches(path: Path, graph_revision: str) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("graph_revision") == graph_revision


def _concept_index_is_fresh(
    project_root: Path,
    config: Mapping[str, Any],
    graph_storage: Path,
    embedding_metadata: EmbeddingMetadata,
) -> bool:
    path = concept_index_path(graph_storage)
    concept_file = configured_concept_file(project_root, config)
    if concept_file is None:
        return not path.exists()
    if not concept_file.exists():
        return not path.exists()

    existing = load_concept_index(path)
    if existing is None:
        return False
    return (
        existing.concept_file_hash == concept_file_hash(concept_file)
        and embedding_identity_matches(existing.embedding_metadata, embedding_metadata)
    )


def _can_reuse_cluster_snapshot(
    snapshot: Any,
    *,
    graph_revision: str,
    changed_section_ids: list[str],
    concept_index: list[Mapping[str, Any]],
) -> bool:
    if changed_section_ids:
        return False
    if snapshot.graph_revision != graph_revision:
        return False
    return _snapshot_concept_chunk_ids(snapshot) == _concept_index_chunk_ids(concept_index)


def _snapshot_concept_chunk_ids(snapshot: Any) -> list[str]:
    return sorted(
        {
            concept_chunk_id
            for cluster in snapshot.clusters
            for concept_chunk_id in cluster.member_concept_chunk_ids
        }
    )


def _concept_index_chunk_ids(concept_index: list[Mapping[str, Any]]) -> list[str]:
    return sorted(
        str(entry.get("concept_chunk_id"))
        for entry in concept_index
        if entry.get("concept_chunk_id")
    )


def _dedupe_relations(relations: list[Relation]) -> list[Relation]:
    by_key: dict[tuple[str, str, str], Relation] = {}
    for relation in relations:
        by_key[(relation.source_id, relation.label, relation.target_id)] = relation
    return list(by_key.values())


def make_community_report_llm_from_config(config: Mapping[str, Any]) -> Any | None:
    report_config = _mapping(config.get("community_report"))
    provider = str(report_config.get("provider", "deterministic")).strip().lower()
    if provider in {"deterministic", "template", "none", "disabled", ""}:
        return None
    if provider == "codex":
        return CodexCLIAdapter(
            command=str(report_config.get("command") or "codex"),
            model=str(report_config.get("model") or "gpt-5.4"),
            effort=str(report_config.get("effort") or "low"),
            timeout_sec=int(report_config.get("timeout_sec", 120)),
            sandbox=str(report_config.get("sandbox", "read-only")),
            max_retries=int(report_config.get("max_retries", 0)),
            retry_backoff_sec=float(report_config.get("retry_backoff_sec", 0.0)),
            repair_on_schema_failure=bool(
                report_config.get("repair_on_schema_failure", True)
            ),
        )
    if provider == "claude":
        return ClaudeCLIAdapter(
            command=str(report_config.get("command") or "claude"),
            model=str(report_config.get("model") or ""),
            effort=str(report_config.get("effort") or "low"),
            timeout_sec=int(report_config.get("timeout_sec", 120)),
            tools=str(report_config.get("tools", "")),
            max_retries=int(report_config.get("max_retries", 0)),
            retry_backoff_sec=float(report_config.get("retry_backoff_sec", 0.0)),
            repair_on_schema_failure=bool(
                report_config.get("repair_on_schema_failure", True)
            ),
        )
    raise ValueError(f"unsupported community_report.provider: {provider}")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _slugify(text: str) -> str:
    normalized = "".join(
        char.lower() if char.isalnum() or char in "._-" else "-"
        for char in text.strip()
    ).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized or "section"
