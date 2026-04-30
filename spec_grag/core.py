"""Core update orchestration for /spec-core."""

from __future__ import annotations

import hashlib
import glob
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode, Relation
from llama_index.core.vector_stores.simple import SimpleVectorStore

from spec_grag.concept_index import (
    generate_concept_diff_candidate,
    refresh_concept_index,
)
from spec_grag.core_extraction import (
    EXTRACTION_MODE_SCHEMA_LLM,
    SCHEMA_LLM_EXTRACTOR_VERSION,
    SchemaExtractor,
    carry_forward_schema_llm_artifacts,
    extract_schema_llm_artifacts,
    extraction_mode,
    make_schema_extractor_from_config,
)
from spec_grag.embedding import (
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
from spec_grag.manifest import (
    ManifestReconciliation,
    ManifestUpdateStatus,
    SourceManifest,
    SourceManifestEntry,
    build_current_section_manifest,
    load_source_manifest,
    next_source_manifest,
    reconcile_manifests,
    write_source_manifest_atomic,
)
from spec_grag.protocol import FreshnessReport, ResultStatus
from spec_grag.retrieval import add_entities_to_vector_store
from spec_grag.sidecars import (
    ChapterAnchorsSidecar,
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


EXTRACTOR_VERSION = "deterministic-core-v1"
GRAPH_STORE_FILENAME = "property_graph_store.json"
VECTOR_STORE_FILENAME = "vector_store.json"


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


def run_core_update(
    project_root: Path,
    config: dict[str, Any],
    *,
    all_sources: bool,
    schema_extractor: SchemaExtractor | None = None,
) -> CoreUpdate:
    graph_storage = _graph_storage_path(project_root, config)
    scanned_at = datetime.now(UTC).isoformat()
    extract_run_id = f"core-{hashlib.sha256(scanned_at.encode('utf-8')).hexdigest()[:12]}"
    embedding_metadata = embedding_metadata_from_config(config, generated_at=scanned_at)
    embedding_metadata_file = embedding_metadata_path(graph_storage)
    previous_embedding_metadata = load_embedding_metadata(embedding_metadata_file)
    existing_embedding_artifacts = (
        (graph_storage / GRAPH_STORE_FILENAME).exists()
        or (graph_storage / VECTOR_STORE_FILENAME).exists()
    )
    if (
        not all_sources
        and existing_embedding_artifacts
        and not embedding_identity_matches(previous_embedding_metadata, embedding_metadata)
    ):
        warnings = [embedding_mismatch_warning(previous_embedding_metadata, embedding_metadata)]
        freshness = FreshnessReport(
            last_core_run=scanned_at,
            graph_revision=None,
            graph_storage_path=str(graph_storage),
            source_manifest_path=str(graph_storage / "source_manifest.json"),
            warnings=warnings,
        )
        return CoreUpdate(
            status=ResultStatus.FAILED,
            mode="incremental",
            updated_sources=[],
            skipped_sources=[],
            failed_sources=["embedding_metadata"],
            graph_storage=str(graph_storage),
            freshness_report=freshness,
            warnings=warnings,
        )
    try:
        mode = extraction_mode(config)
        if mode == EXTRACTION_MODE_SCHEMA_LLM and schema_extractor is None:
            schema_extractor = make_schema_extractor_from_config(config)
    except ValueError as exc:
        freshness = FreshnessReport(
            last_core_run=scanned_at,
            graph_revision=None,
            graph_storage_path=str(graph_storage),
            source_manifest_path=str(graph_storage / "source_manifest.json"),
            warnings=[f"config_invalid:{exc}"],
        )
        return CoreUpdate(
            status=ResultStatus.FAILED,
            mode="full" if all_sources else "incremental",
            updated_sources=[],
            skipped_sources=[],
            failed_sources=["config"],
            graph_storage=str(graph_storage),
            freshness_report=freshness,
            warnings=freshness.warnings,
        )

    source_paths = resolve_source_paths(project_root, config)

    if not source_paths:
        freshness = FreshnessReport(
            last_core_run=scanned_at,
            graph_revision=None,
            graph_storage_path=str(graph_storage),
            source_manifest_path=str(graph_storage / "source_manifest.json"),
            warnings=["sources.include did not match any files"],
        )
        return CoreUpdate(
            status=ResultStatus.FAILED,
            mode="full" if all_sources else "incremental",
            updated_sources=[],
            skipped_sources=[],
            failed_sources=["sources.include"],
            graph_storage=str(graph_storage),
            freshness_report=freshness,
            warnings=freshness.warnings,
        )

    current_manifest = build_current_section_manifest(
        project_root,
        source_paths,
        generated_at=scanned_at,
    )
    manifest_path = graph_storage / "source_manifest.json"
    previous_manifest = SourceManifest(entries=[]) if all_sources else load_source_manifest(manifest_path)
    reconciliation = reconcile_manifests(previous_manifest, current_manifest)
    graph_revision = graph_revision_for_manifest(
        current_manifest,
        embedding_metadata=embedding_metadata,
    )

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
            for section_id in [
                *reconciliation.changed_section_ids,
                *reconciliation.removed_section_ids,
            ]:
                previous_graph_store = safe_delete_by_section(
                    previous_graph_store,
                    section_id=section_id,
                )
            graph_store = carry_forward_schema_llm_artifacts(
                graph_store,
                previous_graph_store,
                keep_section_ids=reconciliation.unchanged_section_ids,
            )
        extraction_result = extract_schema_llm_artifacts(
            project_root=project_root,
            manifest=current_manifest,
            graph_store=graph_store,
            config=config,
            extract_run_id=extract_run_id,
            extracted_at=scanned_at,
            section_ids_to_extract=section_ids_to_extract,
            schema_extractor=schema_extractor,
        )
        graph_store = extraction_result.graph_store
        extraction_warnings.extend(extraction_result.warnings)
        extraction_failed_section_ids = set(extraction_result.failed_section_ids)
        extracted_unresolved_entries = extraction_result.unresolved_entries

    unresolved_path = graph_storage / "unresolved_relations.json"
    unresolved = (
        UnresolvedRelationsSidecar(graph_revision=graph_revision, generated_at=scanned_at)
        if all_sources
        else drop_unresolved_relations_by_sections(
            load_unresolved_relations(unresolved_path),
            [*reconciliation.changed_section_ids, *reconciliation.removed_section_ids],
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
    write_unresolved_relations_atomic(unresolved_path, unresolved)

    vector_store = build_vector_store(
        graph_store,
        embedding_metadata=embedding_metadata,
        embedding_config=_mapping(config.get("embedding")),
    )

    graph_storage.mkdir(parents=True, exist_ok=True)
    graph_store.persist(str(graph_storage / GRAPH_STORE_FILENAME))
    vector_store.persist(str(graph_storage / VECTOR_STORE_FILENAME))
    write_embedding_metadata_atomic(embedding_metadata_file, embedding_metadata)

    chapter_anchors_path = graph_storage / "chapter_anchors.json"
    affected_chapters = (
        sorted({entry.chapter_id for entry in current_manifest.entries})
        if all_sources
        else reconciliation.affected_chapter_ids
    )
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
    write_chapter_anchors_atomic(chapter_anchors_path, chapter_refresh.chapter_anchors)

    cluster_path = graph_storage / "cluster_snapshot.json"
    if all_sources:
        cluster_snapshot = build_cluster_snapshot(
            graph_store,
            graph_revision=graph_revision,
            generated_at=scanned_at,
        )
        cluster_warnings: list[str] = []
    else:
        cluster_refresh = refresh_cluster_snapshot(
            load_cluster_snapshot(cluster_path),
            graph_store,
            changed_section_ids=[
                *reconciliation.changed_section_ids,
                *reconciliation.removed_section_ids,
            ],
            graph_revision=graph_revision,
            generated_at=scanned_at,
            seed_chapter_ids=affected_chapters,
        )
        cluster_snapshot = cluster_refresh.cluster_snapshot
        cluster_warnings = cluster_refresh.warnings
    write_cluster_snapshot_atomic(cluster_path, cluster_snapshot)

    concept_index, concept_index_warnings = refresh_concept_index(
        project_root,
        config,
        graph_storage,
        generated_at=scanned_at,
    )
    changed_for_concept = _changed_section_ids_for_concept_diff(
        current_manifest,
        reconciliation,
        all_sources=all_sources,
        failed_section_ids=extraction_failed_section_ids,
    )
    concept_diff_result = generate_concept_diff_candidate(
        project_root=project_root,
        config=config,
        graph_storage=graph_storage,
        graph_data=graph_store.graph.model_dump(),
        concept_index=concept_index,
        changed_source_section_ids=changed_for_concept,
        extract_run_id=extract_run_id,
        generated_at=scanned_at,
    )

    manifest_status = (
        ManifestUpdateStatus.DEGRADED
        if extraction_failed_section_ids
        else ManifestUpdateStatus.OK
    )
    extractor_versions = {"core": EXTRACTOR_VERSION}
    if mode == EXTRACTION_MODE_SCHEMA_LLM:
        extractor_versions["schema_llm_path_extractor"] = SCHEMA_LLM_EXTRACTOR_VERSION
    next_manifest = next_source_manifest(
        previous_manifest,
        current_manifest,
        status=manifest_status,
        scanned_at=scanned_at,
        extract_run_id=extract_run_id,
        extractor_versions=extractor_versions,
        failed_section_ids=extraction_failed_section_ids,
    )
    write_source_manifest_atomic(manifest_path, next_manifest)

    warnings = [
        *extraction_warnings,
        *chapter_refresh.warnings,
        *cluster_warnings,
        *concept_index_warnings,
        *concept_diff_result.warnings,
    ]
    freshness = FreshnessReport(
        last_core_run=scanned_at,
        graph_revision=graph_revision,
        graph_storage_path=str(graph_storage),
        source_manifest_path=str(manifest_path),
        warnings=warnings,
    )
    return CoreUpdate(
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
    )


def resolve_source_paths(project_root: Path, config: dict[str, Any]) -> list[Path]:
    includes = config.get("sources", {}).get("include", [])
    if isinstance(includes, str):
        includes = [includes]
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
    return sorted(resolved)


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
                        "source_chunk_id": entry.section_id,
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
) -> SimpleVectorStore:
    vector_store = SimpleVectorStore()
    metadata = embedding_metadata or embedding_metadata_from_config({})
    entities = []
    text_by_entity_id = {}
    for node in graph_store.get():
        if node.label not in {"ANCHOR", "SECTION"}:
            continue
        node.embedding = embedding_for_text(
            node.name,
            metadata,
            config=embedding_config,
        )
        node.properties = {
            **(node.properties or {}),
            **embedding_properties(metadata),
        }
        entities.append(node)
        props = node.properties or {}
        text_by_entity_id[node.id] = " ".join(
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
    add_entities_to_vector_store(vector_store, entities, text_by_entity_id=text_by_entity_id)
    return vector_store


def updated_sources_for(
    reconciliation: ManifestReconciliation,
    *,
    all_sources: bool,
    current: SourceManifest,
) -> list[str]:
    if all_sources:
        return sorted({entry.document_id for entry in current.entries})
    section_ids = [
        *reconciliation.changed_section_ids,
        *reconciliation.added_section_ids,
        *reconciliation.removed_section_ids,
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
            "source_document_id": entry.document_id,
            "source_chapter_id": entry.chapter_id,
            "source_section_id": entry.section_id,
            "source_chunk_id": entry.section_id,
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


def _dedupe_relations(relations: list[Relation]) -> list[Relation]:
    by_key: dict[tuple[str, str, str], Relation] = {}
    for relation in relations:
        by_key[(relation.source_id, relation.label, relation.target_id)] = relation
    return list(by_key.values())


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
