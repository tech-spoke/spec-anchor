from __future__ import annotations

from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode, Relation

from spec_grag.graph_ops import safe_delete_by_section


def test_safe_delete_by_section_removes_only_matching_provenance() -> None:
    store = SimplePropertyGraphStore()
    store.upsert_nodes(
        [
            EntityNode(label="ANCHOR", name="auth", properties={"source_section_id": "s1"}),
            EntityNode(label="ANCHOR", name="session", properties={"source_section_id": "s2"}),
            EntityNode(label="CHAPTER", name="chapter", properties={"section_id": "s1"}),
        ]
    )
    store.upsert_relations(
        [
            Relation(
                label="RELATED_TO",
                source_id="auth",
                target_id="session",
                properties={"source_section_id": "s1"},
            ),
            Relation(
                label="MENTIONS",
                source_id="chapter",
                target_id="session",
                properties={},
            ),
        ]
    )

    updated = safe_delete_by_section(store, section_id="s1")
    data = updated.graph.model_dump()

    assert "auth" not in data["nodes"]
    assert "session" in data["nodes"]
    assert "chapter" in data["nodes"]
    assert all(
        (rel.get("properties") or {}).get("source_section_id") != "s1"
        for rel in data["relations"].values()
    )


def test_safe_delete_by_section_prefers_stable_provenance() -> None:
    store = SimplePropertyGraphStore()
    store.upsert_nodes(
        [
            EntityNode(
                label="ANCHOR",
                name="auth",
                properties={"stable_source_section_uid": "stable:s1"},
            ),
            EntityNode(
                label="ANCHOR",
                name="session",
                properties={"stable_source_section_uid": "stable:s2"},
            ),
        ]
    )
    store.upsert_relations(
        [
            Relation(
                label="RELATED_TO",
                source_id="auth",
                target_id="session",
                properties={"stable_source_section_uid": "stable:s1"},
            ),
        ]
    )

    updated = safe_delete_by_section(
        store,
        section_id="renamed-section",
        stable_section_uid="stable:s1",
    )
    data = updated.graph.model_dump()

    assert "auth" not in data["nodes"]
    assert "session" in data["nodes"]
    assert not data["relations"]
