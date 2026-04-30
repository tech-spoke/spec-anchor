from __future__ import annotations

from pathlib import Path

from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode, Relation

from spec_grag.manifest import build_current_section_manifest
from spec_grag.sidecars import (
    ChapterAnchorArtifact,
    ChapterAnchorKeyConcept,
    ChapterAnchorQuality,
    ChapterAnchorsSidecar,
    ClusterSnapshot,
    Confidence,
    CoreConceptIndexEntry,
    UnresolvedRelationEntry,
    UnresolvedRelationReason,
    UnresolvedRelationsSidecar,
    aggregate_chapter_anchor,
    build_cluster_snapshot,
    drop_unresolved_relations_by_sections,
    load_chapter_anchors,
    load_cluster_snapshot,
    load_unresolved_relations,
    mark_chapter_anchors_dirty,
    mark_clusters_dirty_by_sections,
    refresh_chapter_anchors,
    refresh_cluster_snapshot,
    replace_chapter_anchor_atomic,
    unresolved_relation_id_for,
    upsert_unresolved_relations,
    write_chapter_anchors_atomic,
    write_cluster_snapshot_atomic,
    write_unresolved_relations_atomic,
)


def write_markdown(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_unresolved_relations_sidecar_upserts_deletes_and_writes_atomic(
    tmp_path: Path,
) -> None:
    relation_id = unresolved_relation_id_for(
        source_id="docs/spec/auth.md#auth",
        relation_type="DEPENDS_ON",
        target_hint="Session",
        source_section_id="docs/spec/auth.md#auth",
        extract_run_id="run-1",
    )
    entry = UnresolvedRelationEntry(
        unresolved_relation_id=relation_id,
        source_document_id="docs/spec/auth.md",
        source_chapter_id="docs/spec/auth.md#auth",
        source_section_id="docs/spec/auth.md#auth",
        source_chunk_id="chunk-1",
        source_hash="hash-auth",
        extract_run_id="run-1",
        source_id="docs/spec/auth.md#auth",
        relation_type="DEPENDS_ON",
        target_hint="Session",
        reason=UnresolvedRelationReason.MISSING_TARGET,
        evidence_excerpt="Session is referenced but not found.",
    )

    sidecar = upsert_unresolved_relations(
        UnresolvedRelationsSidecar(graph_revision="g1", generated_at="t1"),
        [entry],
    )
    path = tmp_path / ".spec-grag/graph/unresolved_relations.json"
    write_unresolved_relations_atomic(path, sidecar)

    loaded = load_unresolved_relations(path)
    assert loaded.entries[0].review_required is True
    assert loaded.entries[0].unresolved_relation_id == relation_id
    assert not list(path.parent.glob("*.tmp"))

    dropped = drop_unresolved_relations_by_sections(
        loaded,
        ["docs/spec/auth.md#auth"],
        graph_revision="g2",
        generated_at="t2",
    )
    assert dropped.graph_revision == "g2"
    assert dropped.entries == []


def test_chapter_anchor_dirty_and_reaggregate_replaces_only_on_success(
    tmp_path: Path,
) -> None:
    source = write_markdown(
        tmp_path / "docs/spec/auth.md",
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth.\n",
    )
    manifest = build_current_section_manifest(tmp_path, [source], generated_at="m1")
    chapter_id = "docs/spec/auth.md#auth"
    old_anchor = ChapterAnchorArtifact(
        chapter_anchor_id=f"{chapter_id}#chapter-anchor",
        document_id="docs/spec/auth.md",
        chapter_id=chapter_id,
        source_section_ids=["docs/spec/auth.md#auth"],
        source_hashes=["old-hash"],
        generated_at="old",
        source_origin="GRAG",
        summary="old summary",
        key_concepts=[ChapterAnchorKeyConcept(name="old")],
        key_terms=["old"],
        quality=ChapterAnchorQuality(
            extraction_confidence=Confidence.MEDIUM,
            coverage=Confidence.MEDIUM,
            stale=False,
        ),
    )
    sidecar = ChapterAnchorsSidecar(
        graph_revision="g1",
        generated_at="old",
        anchors=[old_anchor],
    )
    store = SimplePropertyGraphStore()
    store.upsert_nodes(
        [
            EntityNode(
                label="ANCHOR",
                name="oauth",
                properties={
                    "source_chapter_id": chapter_id,
                    "source_section_id": "docs/spec/auth.md#auth-login",
                    "source_hash": "hash-login",
                    "description": "OAuth login",
                    "evidence_excerpt": "OAuth.",
                },
            )
        ]
    )

    dirty = mark_chapter_anchors_dirty(
        sidecar,
        [chapter_id],
        graph_revision="g2",
        generated_at="dirty",
    )
    assert dirty.anchors[0].quality.stale is True

    refreshed = refresh_chapter_anchors(
        dirty,
        store,
        manifest,
        [chapter_id],
        graph_revision="g3",
        generated_at="new",
    )
    new_anchor = refreshed.chapter_anchors.by_chapter_id()[chapter_id]
    assert refreshed.warnings == []
    assert new_anchor.quality.stale is False
    assert new_anchor.key_terms == ["oauth"]
    assert "docs/spec/auth.md#auth-login" in new_anchor.source_section_ids

    failed = refresh_chapter_anchors(
        dirty,
        store,
        manifest,
        ["docs/spec/missing.md#missing"],
        graph_revision="g4",
        generated_at="failed",
    )
    assert failed.chapter_anchors.by_chapter_id()[chapter_id].quality.stale is True
    assert failed.warnings


def test_chapter_anchor_atomic_replace_roundtrip(tmp_path: Path) -> None:
    chapter_id = "docs/spec/auth.md#auth"
    anchor = ChapterAnchorArtifact(
        chapter_anchor_id=f"{chapter_id}#chapter-anchor",
        document_id="docs/spec/auth.md",
        chapter_id=chapter_id,
        source_section_ids=["docs/spec/auth.md#auth"],
        source_hashes=["hash-auth"],
        generated_at="t1",
        source_origin="GRAG",
        summary="Auth: oauth",
        key_terms=["oauth"],
        quality=ChapterAnchorQuality(
            extraction_confidence=Confidence.MEDIUM,
            coverage=Confidence.HIGH,
            stale=False,
        ),
    )
    path = tmp_path / ".spec-grag/graph/chapter_anchors.json"

    replace_chapter_anchor_atomic(path, anchor, graph_revision="g1", generated_at="t1")
    loaded = load_chapter_anchors(path)

    assert loaded.graph_revision == "g1"
    assert loaded.anchors[0] == anchor
    assert not list(path.parent.glob("*.tmp"))


def test_aggregate_chapter_anchor_uses_whole_chapter_manifest(tmp_path: Path) -> None:
    source = write_markdown(
        tmp_path / "docs/spec/auth.md",
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth.\n\n## Logout\n\nClear session.\n",
    )
    manifest = build_current_section_manifest(tmp_path, [source])
    chapter_id = "docs/spec/auth.md#auth"
    store = SimplePropertyGraphStore()
    store.upsert_nodes(
        [
            EntityNode(
                label="ANCHOR",
                name="oauth",
                properties={
                    "source_chapter_id": chapter_id,
                    "source_section_id": "docs/spec/auth.md#auth-login",
                    "evidence_excerpt": "OAuth.",
                },
            ),
            EntityNode(
                label="ANCHOR",
                name="session",
                properties={
                    "source_chapter_id": chapter_id,
                    "source_section_id": "docs/spec/auth.md#auth-logout",
                    "evidence_excerpt": "Clear session.",
                },
            ),
        ]
    )
    store.upsert_relations(
        [
            Relation(
                label="DEPENDS_ON",
                source_id=chapter_id,
                target_id="docs/spec/session.md#session",
                properties={
                    "source_section_id": "docs/spec/auth.md#auth-login",
                    "confidence": "high",
                },
            )
        ]
    )

    anchor = aggregate_chapter_anchor(
        store,
        manifest,
        chapter_id,
        generated_at="t1",
    )

    assert anchor.source_section_ids == [
        "docs/spec/auth.md#auth",
        "docs/spec/auth.md#auth-login",
        "docs/spec/auth.md#auth-logout",
    ]
    assert anchor.key_terms == ["oauth", "session"]
    assert anchor.related_sections[0].section_id == "docs/spec/session.md#session"
    assert anchor.quality.coverage == Confidence.MEDIUM


def test_cluster_snapshot_dirty_refresh_and_concept_index_reference(
    tmp_path: Path,
) -> None:
    store = SimplePropertyGraphStore()
    auth = "docs/spec/auth.md#auth"
    session = "docs/spec/session.md#session"
    store.upsert_nodes(
        [
            EntityNode(label="CHAPTER", name=auth),
            EntityNode(label="CHAPTER", name=session),
            EntityNode(
                label="ANCHOR",
                name="oauth",
                properties={"source_chapter_id": auth},
            ),
        ]
    )
    store.upsert_relations(
        [
            Relation(
                label="DEPENDS_ON",
                source_id=auth,
                target_id=session,
                properties={
                    "source_section_id": "docs/spec/auth.md#auth-login",
                    "confidence": "high",
                },
            ),
            Relation(
                label="RELATED_TO",
                source_id=auth,
                target_id="docs/spec/low.md#low",
                properties={
                    "source_section_id": "docs/spec/auth.md#auth",
                    "confidence": "low",
                },
            ),
        ]
    )

    snapshot = build_cluster_snapshot(
        store,
        graph_revision="g1",
        generated_at="t1",
        concept_index=[
            CoreConceptIndexEntry(
                concept_chunk_id="concept:auth-boundary",
                related_anchor_ids=["oauth"],
                related_chapter_ids=[auth],
            )
        ],
    )
    chapter_cluster = next(
        cluster for cluster in snapshot.clusters if cluster.level == "chapter"
    )
    concept_cluster = next(
        cluster for cluster in snapshot.clusters if cluster.level == "concept"
    )
    assert chapter_cluster.member_chapter_ids == [auth, session]
    assert chapter_cluster.member_anchor_ids == ["oauth"]
    assert chapter_cluster.source_section_ids == ["docs/spec/auth.md#auth-login"]
    assert concept_cluster.member_concept_chunk_ids == ["concept:auth-boundary"]

    dirty = mark_clusters_dirty_by_sections(
        snapshot,
        ["docs/spec/auth.md#auth-login"],
        graph_revision="g2",
        generated_at="t2",
    )
    assert next(cluster for cluster in dirty.clusters if cluster.level == "chapter").stale is True

    refreshed = refresh_cluster_snapshot(
        dirty,
        store,
        changed_section_ids=["docs/spec/auth.md#auth-login"],
        graph_revision="g3",
        generated_at="t3",
        concept_index=[{"concept_chunk_id": "concept:auth-boundary"}],
    )
    assert refreshed.warnings == []
    assert all(cluster.stale is False for cluster in refreshed.cluster_snapshot.clusters)

    path = tmp_path / ".spec-grag/graph/cluster_snapshot.json"
    write_cluster_snapshot_atomic(path, refreshed.cluster_snapshot)
    loaded = load_cluster_snapshot(path)
    assert loaded.graph_revision == "g3"
    assert not list(path.parent.glob("*.tmp"))


def test_sidecar_empty_loads_have_schema_defaults(tmp_path: Path) -> None:
    assert load_unresolved_relations(tmp_path / "missing-unresolved.json").version == "1"
    assert load_chapter_anchors(tmp_path / "missing-anchors.json").anchors == []
    assert load_cluster_snapshot(tmp_path / "missing-clusters.json").clusters == []

    path = tmp_path / ".spec-grag/graph/chapter_anchors.json"
    write_chapter_anchors_atomic(path, ChapterAnchorsSidecar(graph_revision="g1"))
    assert load_chapter_anchors(path).graph_revision == "g1"
