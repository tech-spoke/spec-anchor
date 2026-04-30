"""Sidecar artifact schemas and update helpers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from spec_grag.manifest import SourceManifest, SourceManifestEntry
from spec_grag.protocol import StrictModel


SIDECAR_VERSION = "1"

ChapterRelationType = Literal["RELATED_TO", "DEPENDS_ON", "REFINES", "CONTRASTS_WITH"]
SourceOrigin = Literal["GRAG", "AgenticSearch", "both"]
ClusterLevel = Literal["chapter", "concept", "relation"]


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UnresolvedRelationReason(StrEnum):
    AMBIGUOUS_TARGET = "ambiguous_target"
    MISSING_TARGET = "missing_target"
    LOW_CONFIDENCE = "low_confidence"
    SCHEMA_REJECTED = "schema_rejected"


class UnresolvedRelationEntry(StrictModel):
    unresolved_relation_id: str
    source_document_id: str
    source_chapter_id: str
    source_section_id: str
    source_chunk_id: str
    source_hash: str
    extract_run_id: str
    source_id: str
    relation_type: ChapterRelationType
    target_hint: str
    reason: UnresolvedRelationReason
    evidence_excerpt: str | None = None
    review_required: Literal[True] = True


class UnresolvedRelationsSidecar(StrictModel):
    version: str = SIDECAR_VERSION
    graph_revision: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    entries: list[UnresolvedRelationEntry] = Field(default_factory=list)


class ChapterAnchorKeyEntity(StrictModel):
    name: str
    kind: str | None = None
    evidence_excerpt: str | None = None


class ChapterAnchorKeyConcept(StrictModel):
    name: str
    related_anchor_ids: list[str] = Field(default_factory=list)
    evidence_excerpt: str | None = None


class ChapterAnchorRelatedSection(StrictModel):
    section_id: str
    relation_type: ChapterRelationType | None = None
    confidence: Confidence


class ChapterAnchorEvidence(StrictModel):
    section_id: str
    source_span: str | None = None
    excerpt: str


class ChapterAnchorQuality(StrictModel):
    extraction_confidence: Confidence
    coverage: Confidence
    stale: bool


class ChapterAnchorArtifact(StrictModel):
    chapter_anchor_id: str
    document_id: str
    chapter_id: str
    source_section_ids: list[str]
    source_hashes: list[str]
    generated_at: str
    source_origin: SourceOrigin
    summary: str
    key_entities: list[ChapterAnchorKeyEntity] = Field(default_factory=list)
    key_concepts: list[ChapterAnchorKeyConcept] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)
    related_sections: list[ChapterAnchorRelatedSection] = Field(default_factory=list)
    evidence: list[ChapterAnchorEvidence] = Field(default_factory=list)
    quality: ChapterAnchorQuality


class ChapterAnchorsSidecar(StrictModel):
    version: str = SIDECAR_VERSION
    graph_revision: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    anchors: list[ChapterAnchorArtifact] = Field(default_factory=list)

    def by_chapter_id(self) -> dict[str, ChapterAnchorArtifact]:
        return {anchor.chapter_id: anchor for anchor in self.anchors}


class ChapterAnchorRefreshResult(StrictModel):
    chapter_anchors: ChapterAnchorsSidecar
    warnings: list[str] = Field(default_factory=list)


class ClusterRelationPath(StrictModel):
    source_id: str
    relation_type: ChapterRelationType
    target_id: str
    source_section_id: str
    confidence: Confidence


class ClusterArtifact(StrictModel):
    cluster_id: str
    level: ClusterLevel
    seed_ids: list[str] = Field(default_factory=list)
    member_chapter_ids: list[str] = Field(default_factory=list)
    member_anchor_ids: list[str] = Field(default_factory=list)
    member_concept_chunk_ids: list[str] = Field(default_factory=list)
    relation_paths: list[ClusterRelationPath] = Field(default_factory=list)
    dominant_relation_types: list[str] = Field(default_factory=list)
    source_section_ids: list[str] = Field(default_factory=list)
    confidence: Confidence
    stale: bool


class ClusterSnapshot(StrictModel):
    version: str = SIDECAR_VERSION
    graph_revision: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    clusters: list[ClusterArtifact] = Field(default_factory=list)


class ClusterSnapshotRefreshResult(StrictModel):
    cluster_snapshot: ClusterSnapshot
    warnings: list[str] = Field(default_factory=list)


class CoreConceptIndexEntry(StrictModel):
    concept_chunk_id: str
    related_anchor_ids: list[str] = Field(default_factory=list)
    related_chapter_ids: list[str] = Field(default_factory=list)


def load_unresolved_relations(path: Path) -> UnresolvedRelationsSidecar:
    return _load_sidecar(path, UnresolvedRelationsSidecar)


def write_unresolved_relations_atomic(
    path: Path, sidecar: UnresolvedRelationsSidecar
) -> None:
    _write_model_atomic(path, sidecar)


def upsert_unresolved_relations(
    sidecar: UnresolvedRelationsSidecar,
    entries: Iterable[UnresolvedRelationEntry],
    *,
    graph_revision: str | None = None,
    generated_at: str | None = None,
) -> UnresolvedRelationsSidecar:
    by_id = {entry.unresolved_relation_id: entry for entry in sidecar.entries}
    for entry in entries:
        by_id[entry.unresolved_relation_id] = entry
    return UnresolvedRelationsSidecar(
        graph_revision=graph_revision if graph_revision is not None else sidecar.graph_revision,
        generated_at=generated_at or sidecar.generated_at,
        entries=sorted(by_id.values(), key=lambda e: e.unresolved_relation_id),
    )


def drop_unresolved_relations_by_sections(
    sidecar: UnresolvedRelationsSidecar,
    section_ids: Iterable[str],
    *,
    graph_revision: str | None = None,
    generated_at: str | None = None,
) -> UnresolvedRelationsSidecar:
    section_id_set = set(section_ids)
    return UnresolvedRelationsSidecar(
        graph_revision=graph_revision if graph_revision is not None else sidecar.graph_revision,
        generated_at=generated_at or sidecar.generated_at,
        entries=[
            entry
            for entry in sidecar.entries
            if entry.source_section_id not in section_id_set
        ],
    )


def unresolved_relation_id_for(
    *,
    source_id: str,
    relation_type: str,
    target_hint: str,
    source_section_id: str,
    extract_run_id: str,
) -> str:
    payload = json.dumps(
        {
            "source_id": source_id,
            "relation_type": relation_type,
            "target_hint": target_hint,
            "source_section_id": source_section_id,
            "extract_run_id": extract_run_id,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"unresolved:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def load_chapter_anchors(path: Path) -> ChapterAnchorsSidecar:
    return _load_sidecar(path, ChapterAnchorsSidecar)


def write_chapter_anchors_atomic(path: Path, sidecar: ChapterAnchorsSidecar) -> None:
    _write_model_atomic(path, sidecar)


def mark_chapter_anchors_dirty(
    sidecar: ChapterAnchorsSidecar,
    chapter_ids: Iterable[str],
    *,
    graph_revision: str | None = None,
    generated_at: str | None = None,
) -> ChapterAnchorsSidecar:
    chapter_id_set = set(chapter_ids)
    updated = [
        _anchor_with_stale(anchor, stale=True)
        if anchor.chapter_id in chapter_id_set
        else anchor
        for anchor in sidecar.anchors
    ]
    return ChapterAnchorsSidecar(
        graph_revision=graph_revision if graph_revision is not None else sidecar.graph_revision,
        generated_at=generated_at or sidecar.generated_at,
        anchors=updated,
    )


def replace_chapter_anchor(
    sidecar: ChapterAnchorsSidecar,
    anchor: ChapterAnchorArtifact,
    *,
    graph_revision: str | None = None,
    generated_at: str | None = None,
) -> ChapterAnchorsSidecar:
    anchors = [
        existing
        for existing in sidecar.anchors
        if existing.chapter_id != anchor.chapter_id
    ]
    anchors.append(anchor)
    return ChapterAnchorsSidecar(
        graph_revision=graph_revision if graph_revision is not None else sidecar.graph_revision,
        generated_at=generated_at or sidecar.generated_at,
        anchors=sorted(anchors, key=lambda item: item.chapter_id),
    )


def replace_chapter_anchor_atomic(
    path: Path,
    anchor: ChapterAnchorArtifact,
    *,
    graph_revision: str | None = None,
    generated_at: str | None = None,
) -> None:
    sidecar = load_chapter_anchors(path)
    updated = replace_chapter_anchor(
        sidecar,
        anchor,
        graph_revision=graph_revision,
        generated_at=generated_at,
    )
    write_chapter_anchors_atomic(path, updated)


def aggregate_chapter_anchor(
    graph_store: Any,
    manifest: SourceManifest,
    chapter_id: str,
    *,
    generated_at: str | None = None,
    source_origin: SourceOrigin = "GRAG",
) -> ChapterAnchorArtifact:
    entries = sorted(
        (entry for entry in manifest.entries if entry.chapter_id == chapter_id),
        key=lambda entry: (entry.document_id, entry.heading_start_line, entry.section_id),
    )
    if not entries:
        raise ValueError(f"chapter has no current manifest entries: {chapter_id}")

    generated = generated_at or datetime.now(UTC).isoformat()
    section_ids = {entry.section_id for entry in entries}
    source_hashes = [entry.source_hash for entry in entries]
    graph_data = _graph_dump(graph_store)
    anchors = _anchor_nodes_for_chapter(graph_data, chapter_id, section_ids)
    related_sections = _related_sections_for_chapter(graph_data, chapter_id, section_ids)
    evidence = _evidence_for_chapter(graph_data, anchors, related_sections, section_ids)
    key_terms = _unique_sorted(_node_display_name(node_id, node) for node_id, node in anchors)

    return ChapterAnchorArtifact(
        chapter_anchor_id=f"{chapter_id}#chapter-anchor",
        document_id=entries[0].document_id,
        chapter_id=chapter_id,
        source_section_ids=[entry.section_id for entry in entries],
        source_hashes=source_hashes,
        generated_at=generated,
        source_origin=source_origin,
        summary=_chapter_summary(entries, key_terms),
        key_entities=[
            ChapterAnchorKeyEntity(
                name=_node_display_name(node_id, node),
                kind=_node_label(node),
                evidence_excerpt=_node_properties(node).get("evidence_excerpt"),
            )
            for node_id, node in anchors
        ],
        key_concepts=[
            ChapterAnchorKeyConcept(
                name=_node_display_name(node_id, node),
                related_anchor_ids=[node_id],
                evidence_excerpt=_node_properties(node).get("evidence_excerpt"),
            )
            for node_id, node in anchors
        ],
        key_terms=key_terms,
        related_sections=related_sections,
        evidence=evidence,
        quality=ChapterAnchorQuality(
            extraction_confidence=_confidence_for_count(len(anchors)),
            coverage=_coverage_for_anchors(anchors, section_ids),
            stale=False,
        ),
    )


def refresh_chapter_anchors(
    sidecar: ChapterAnchorsSidecar,
    graph_store: Any,
    manifest: SourceManifest,
    affected_chapter_ids: Iterable[str],
    *,
    graph_revision: str | None = None,
    generated_at: str | None = None,
) -> ChapterAnchorRefreshResult:
    generated = generated_at or datetime.now(UTC).isoformat()
    updated = mark_chapter_anchors_dirty(
        sidecar,
        affected_chapter_ids,
        graph_revision=graph_revision,
        generated_at=generated,
    )
    warnings: list[str] = []

    for chapter_id in sorted(set(affected_chapter_ids)):
        try:
            anchor = aggregate_chapter_anchor(
                graph_store,
                manifest,
                chapter_id,
                generated_at=generated,
            )
        except Exception as exc:
            warnings.append(f"chapter_anchor_reaggregation_failed:{chapter_id}:{exc}")
            continue
        updated = replace_chapter_anchor(
            updated,
            anchor,
            graph_revision=graph_revision,
            generated_at=generated,
        )

    return ChapterAnchorRefreshResult(chapter_anchors=updated, warnings=warnings)


def load_cluster_snapshot(path: Path) -> ClusterSnapshot:
    return _load_sidecar(path, ClusterSnapshot)


def write_cluster_snapshot_atomic(path: Path, snapshot: ClusterSnapshot) -> None:
    _write_model_atomic(path, snapshot)


def mark_clusters_dirty_by_sections(
    snapshot: ClusterSnapshot,
    section_ids: Iterable[str],
    *,
    graph_revision: str | None = None,
    generated_at: str | None = None,
) -> ClusterSnapshot:
    section_id_set = set(section_ids)
    updated = [
        cluster.model_copy(update={"stale": True})
        if section_id_set.intersection(cluster.source_section_ids)
        else cluster
        for cluster in snapshot.clusters
    ]
    return ClusterSnapshot(
        graph_revision=graph_revision if graph_revision is not None else snapshot.graph_revision,
        generated_at=generated_at or snapshot.generated_at,
        clusters=updated,
    )


def build_cluster_snapshot(
    graph_store: Any,
    *,
    graph_revision: str,
    generated_at: str | None = None,
    seed_chapter_ids: Iterable[str] | None = None,
    concept_index: Iterable[CoreConceptIndexEntry | Mapping[str, Any]] | None = None,
) -> ClusterSnapshot:
    graph_data = _graph_dump(graph_store)
    generated = generated_at or datetime.now(UTC).isoformat()
    seed_set = set(seed_chapter_ids or [])
    chapter_clusters = _chapter_clusters_from_graph(graph_data, seed_set)
    concept_clusters = _concept_clusters(concept_index or [])

    return ClusterSnapshot(
        graph_revision=graph_revision,
        generated_at=generated,
        clusters=sorted(
            [*chapter_clusters, *concept_clusters],
            key=lambda cluster: (cluster.level, cluster.cluster_id),
        ),
    )


def refresh_cluster_snapshot(
    previous: ClusterSnapshot,
    graph_store: Any,
    *,
    changed_section_ids: Iterable[str],
    graph_revision: str,
    generated_at: str | None = None,
    seed_chapter_ids: Iterable[str] | None = None,
    concept_index: Iterable[CoreConceptIndexEntry | Mapping[str, Any]] | None = None,
) -> ClusterSnapshotRefreshResult:
    generated = generated_at or datetime.now(UTC).isoformat()
    dirty_previous = mark_clusters_dirty_by_sections(
        previous,
        changed_section_ids,
        graph_revision=graph_revision,
        generated_at=generated,
    )
    try:
        refreshed = build_cluster_snapshot(
            graph_store,
            graph_revision=graph_revision,
            generated_at=generated,
            seed_chapter_ids=seed_chapter_ids,
            concept_index=concept_index,
        )
    except Exception as exc:
        return ClusterSnapshotRefreshResult(
            cluster_snapshot=dirty_previous,
            warnings=[f"cluster_snapshot_refresh_failed:{exc}"],
        )
    return ClusterSnapshotRefreshResult(cluster_snapshot=refreshed, warnings=[])


def _load_sidecar(path: Path, model_type: type[Any]) -> Any:
    if not path.exists():
        return model_type()
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def _write_model_atomic(path: Path, model: StrictModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump_json(indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _anchor_with_stale(anchor: ChapterAnchorArtifact, *, stale: bool) -> ChapterAnchorArtifact:
    return anchor.model_copy(
        update={
            "quality": anchor.quality.model_copy(update={"stale": stale}),
        }
    )


def _graph_dump(graph_store: Any) -> dict[str, Any]:
    if hasattr(graph_store, "graph") and hasattr(graph_store.graph, "model_dump"):
        return graph_store.graph.model_dump()
    if isinstance(graph_store, Mapping):
        return dict(graph_store)
    return {"nodes": {}, "relations": {}, "triplets": set()}


def _node_properties(node: Mapping[str, Any]) -> dict[str, Any]:
    return dict(node.get("properties") or {})


def _relation_properties(relation: Mapping[str, Any]) -> dict[str, Any]:
    return dict(relation.get("properties") or {})


def _node_label(node: Mapping[str, Any]) -> str:
    return str(node.get("label") or "")


def _node_display_name(node_id: str, node: Mapping[str, Any]) -> str:
    props = _node_properties(node)
    return str(props.get("display_name") or node.get("name") or node_id)


def _anchor_nodes_for_chapter(
    graph_data: Mapping[str, Any], chapter_id: str, section_ids: set[str]
) -> list[tuple[str, Mapping[str, Any]]]:
    nodes = graph_data.get("nodes") or {}
    anchors = []
    for node_id, node in nodes.items():
        if _node_label(node) != "ANCHOR":
            continue
        props = _node_properties(node)
        if (
            props.get("source_chapter_id") == chapter_id
            or props.get("chapter_id") == chapter_id
            or props.get("source_section_id") in section_ids
            or props.get("section_id") in section_ids
        ):
            anchors.append((node_id, node))
    return sorted(anchors, key=lambda item: _node_display_name(item[0], item[1]))


def _related_sections_for_chapter(
    graph_data: Mapping[str, Any], chapter_id: str, section_ids: set[str]
) -> list[ChapterAnchorRelatedSection]:
    relations = graph_data.get("relations") or {}
    seen: set[tuple[str, str | None]] = set()
    related: list[ChapterAnchorRelatedSection] = []
    for relation in relations.values():
        label = relation.get("label")
        if label not in _cluster_relation_types():
            continue
        props = _relation_properties(relation)
        source_section_id = props.get("source_section_id")
        if not (
            props.get("source_chapter_id") == chapter_id
            or source_section_id in section_ids
        ):
            continue
        target_id = str(props.get("target_section_id") or relation.get("target_id"))
        key = (target_id, label)
        if key in seen:
            continue
        seen.add(key)
        related.append(
            ChapterAnchorRelatedSection(
                section_id=target_id,
                relation_type=label,
                confidence=_confidence(props.get("confidence")),
            )
        )
    return sorted(related, key=lambda item: (item.section_id, item.relation_type or ""))


def _evidence_for_chapter(
    graph_data: Mapping[str, Any],
    anchors: Sequence[tuple[str, Mapping[str, Any]]],
    related_sections: Sequence[ChapterAnchorRelatedSection],
    section_ids: set[str],
) -> list[ChapterAnchorEvidence]:
    evidence: list[ChapterAnchorEvidence] = []
    for _, node in anchors:
        props = _node_properties(node)
        excerpt = props.get("evidence_excerpt") or props.get("description")
        section_id = props.get("source_section_id") or props.get("section_id")
        if excerpt and section_id:
            evidence.append(
                ChapterAnchorEvidence(
                    section_id=str(section_id),
                    source_span=props.get("source_span"),
                    excerpt=str(excerpt),
                )
            )

    relations = graph_data.get("relations") or {}
    for relation in relations.values():
        props = _relation_properties(relation)
        source_section_id = props.get("source_section_id")
        excerpt = props.get("evidence_excerpt")
        if source_section_id in section_ids and excerpt:
            evidence.append(
                ChapterAnchorEvidence(
                    section_id=str(source_section_id),
                    source_span=props.get("source_span"),
                    excerpt=str(excerpt),
                )
            )

    seen: set[tuple[str, str]] = set()
    deduped = []
    for item in evidence:
        key = (item.section_id, item.excerpt)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    if deduped:
        return deduped
    return [
        ChapterAnchorEvidence(
            section_id=related.section_id,
            excerpt=f"Related through {related.relation_type or 'relation'}",
        )
        for related in related_sections[:3]
    ]


def _chapter_summary(entries: Sequence[SourceManifestEntry], key_terms: Sequence[str]) -> str:
    chapter_heading = entries[0].heading_path.split(" / ")[0]
    if key_terms:
        return f"{chapter_heading}: {', '.join(key_terms[:7])}"
    return f"{chapter_heading}: no extracted anchors available"


def _confidence(value: Any) -> Confidence:
    if value == Confidence.HIGH or value == "high":
        return Confidence.HIGH
    if value == Confidence.LOW or value == "low":
        return Confidence.LOW
    return Confidence.MEDIUM


def _confidence_for_count(count: int) -> Confidence:
    if count >= 3:
        return Confidence.HIGH
    if count >= 1:
        return Confidence.MEDIUM
    return Confidence.LOW


def _coverage_for_anchors(
    anchors: Sequence[tuple[str, Mapping[str, Any]]], section_ids: set[str]
) -> Confidence:
    if not section_ids:
        return Confidence.LOW
    covered = {
        str(
            _node_properties(node).get("source_section_id")
            or _node_properties(node).get("section_id")
        )
        for _, node in anchors
        if _node_properties(node).get("source_section_id")
        or _node_properties(node).get("section_id")
    }
    ratio = len(covered.intersection(section_ids)) / len(section_ids)
    if ratio >= 0.75:
        return Confidence.HIGH
    if ratio > 0:
        return Confidence.MEDIUM
    return Confidence.LOW


def _chapter_clusters_from_graph(
    graph_data: Mapping[str, Any], seed_chapter_ids: set[str]
) -> list[ClusterArtifact]:
    nodes = graph_data.get("nodes") or {}
    relations = [
        relation
        for relation in (graph_data.get("relations") or {}).values()
        if _relation_is_cluster_input(relation)
    ]
    chapter_ids = _chapter_ids_from_graph(nodes)
    chapter_ids.update(seed_chapter_ids)
    for relation in relations:
        source_id = str(relation.get("source_id") or "")
        target_id = str(relation.get("target_id") or "")
        if _is_chapter_ref(source_id, nodes, seed_chapter_ids) and _is_chapter_ref(
            target_id, nodes, seed_chapter_ids
        ):
            chapter_ids.update([source_id, target_id])

    adjacency: dict[str, set[str]] = defaultdict(set)
    relation_paths_by_pair: dict[tuple[str, str], list[ClusterRelationPath]] = defaultdict(list)
    for relation in relations:
        source_id = str(relation.get("source_id") or "")
        target_id = str(relation.get("target_id") or "")
        if not source_id or not target_id:
            continue
        if source_id not in chapter_ids or target_id not in chapter_ids:
            continue
        adjacency[source_id].add(target_id)
        adjacency[target_id].add(source_id)
        path = _cluster_relation_path(relation)
        relation_paths_by_pair[tuple(sorted((source_id, target_id)))].append(path)

    clusters: list[ClusterArtifact] = []
    visited: set[str] = set()
    for chapter_id in sorted(chapter_ids):
        if chapter_id in visited:
            continue
        component = _walk_component(chapter_id, adjacency)
        visited.update(component)
        if seed_chapter_ids and not component.intersection(seed_chapter_ids):
            continue
        paths = [
            path
            for pair, pair_paths in relation_paths_by_pair.items()
            if set(pair).issubset(component)
            for path in pair_paths
        ]
        if len(component) == 1 and not paths:
            seed_ids = [chapter_id]
        else:
            seed_ids = sorted(component.intersection(seed_chapter_ids) or component)
        clusters.append(
            ClusterArtifact(
                cluster_id=_stable_cluster_id("chapter", sorted(component)),
                level="chapter",
                seed_ids=seed_ids,
                member_chapter_ids=sorted(component),
                member_anchor_ids=_anchor_ids_for_chapters(nodes, component),
                member_concept_chunk_ids=[],
                relation_paths=sorted(
                    paths,
                    key=lambda path: (
                        path.source_id,
                        path.relation_type,
                        path.target_id,
                        path.source_section_id,
                    ),
                ),
                dominant_relation_types=_dominant_relation_types(paths),
                source_section_ids=_unique_sorted(path.source_section_id for path in paths),
                confidence=_cluster_confidence(paths),
                stale=False,
            )
        )
    return clusters


def _concept_clusters(
    concept_index: Iterable[CoreConceptIndexEntry | Mapping[str, Any]]
) -> list[ClusterArtifact]:
    clusters: list[ClusterArtifact] = []
    for raw_entry in concept_index:
        entry = (
            raw_entry
            if isinstance(raw_entry, CoreConceptIndexEntry)
            else CoreConceptIndexEntry.model_validate(raw_entry)
        )
        clusters.append(
            ClusterArtifact(
                cluster_id=_stable_cluster_id("concept", [entry.concept_chunk_id]),
                level="concept",
                seed_ids=[entry.concept_chunk_id],
                member_chapter_ids=sorted(entry.related_chapter_ids),
                member_anchor_ids=sorted(entry.related_anchor_ids),
                member_concept_chunk_ids=[entry.concept_chunk_id],
                relation_paths=[],
                dominant_relation_types=[],
                source_section_ids=[],
                confidence=Confidence.MEDIUM,
                stale=False,
            )
        )
    return clusters


def _relation_is_cluster_input(relation: Mapping[str, Any]) -> bool:
    label = relation.get("label")
    if label not in _cluster_relation_types():
        return False
    props = _relation_properties(relation)
    if props.get("review_required") is True:
        return False
    if _confidence(props.get("confidence")) == Confidence.LOW:
        return False
    return True


def _cluster_relation_path(relation: Mapping[str, Any]) -> ClusterRelationPath:
    props = _relation_properties(relation)
    return ClusterRelationPath(
        source_id=str(relation.get("source_id")),
        relation_type=relation.get("label"),
        target_id=str(relation.get("target_id")),
        source_section_id=str(props.get("source_section_id") or ""),
        confidence=_confidence(props.get("confidence")),
    )


def _chapter_ids_from_graph(nodes: Mapping[str, Mapping[str, Any]]) -> set[str]:
    return {
        str(node_id)
        for node_id, node in nodes.items()
        if _node_label(node) == "CHAPTER"
    }


def _is_chapter_ref(
    node_id: str,
    nodes: Mapping[str, Mapping[str, Any]],
    seed_chapter_ids: set[str],
) -> bool:
    node = nodes.get(node_id)
    if node is None:
        return node_id in seed_chapter_ids
    return _node_label(node) == "CHAPTER" or node_id in seed_chapter_ids


def _anchor_ids_for_chapters(
    nodes: Mapping[str, Mapping[str, Any]], chapter_ids: set[str]
) -> list[str]:
    anchor_ids = []
    for node_id, node in nodes.items():
        if _node_label(node) != "ANCHOR":
            continue
        props = _node_properties(node)
        if props.get("source_chapter_id") in chapter_ids or props.get("chapter_id") in chapter_ids:
            anchor_ids.append(str(node_id))
    return sorted(anchor_ids)


def _walk_component(start: str, adjacency: Mapping[str, set[str]]) -> set[str]:
    seen = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, set()):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            queue.append(neighbor)
    return seen


def _dominant_relation_types(paths: Sequence[ClusterRelationPath]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for path in paths:
        counts[path.relation_type] += 1
    return [
        relation_type
        for relation_type, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _cluster_confidence(paths: Sequence[ClusterRelationPath]) -> Confidence:
    if not paths:
        return Confidence.LOW
    if all(path.confidence == Confidence.HIGH for path in paths):
        return Confidence.HIGH
    return Confidence.MEDIUM


def _stable_cluster_id(level: str, parts: Sequence[str]) -> str:
    payload = json.dumps([level, *parts], ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{level}:{digest}"


def _cluster_relation_types() -> set[str]:
    return {"RELATED_TO", "DEPENDS_ON", "REFINES", "CONTRASTS_WITH"}


def _unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})
