"""Property graph mutation helpers."""

from __future__ import annotations

from typing import Any


def safe_delete_by_section(
    store: Any,
    *,
    section_id: str,
    stable_section_uid: str | None = None,
    provenance_keys: tuple[str, ...] = ("source_section_id",),
    stable_provenance_keys: tuple[str, ...] = (
        "stable_source_section_uid",
        "stable_section_uid",
    ),
) -> Any:
    """Delete LLM-extracted graph artifacts for one source section.

    The LlamaIndex graph store delete API cascades through connected nodes.
    SPEC-grag therefore filters the serialized graph by provenance and rebuilds
    the store, leaving deterministic DOCUMENT / CHAPTER / SECTION structure to
    the separate structure reconciliation path.
    """

    data = store.graph.model_dump()
    raw_nodes: dict[str, Any] = data.get("nodes", {})
    raw_relations: dict[str, Any] = data.get("relations", {})
    raw_triplets = data.get("triplets", set())

    kept_nodes = {
        node_id: node
        for node_id, node in raw_nodes.items()
        if not _has_section_provenance(
            node,
            section_id=section_id,
            stable_section_uid=stable_section_uid,
            provenance_keys=provenance_keys,
            stable_provenance_keys=stable_provenance_keys,
        )
    }
    kept_node_ids = set(kept_nodes)
    kept_relations = {
        rel_key: rel
        for rel_key, rel in raw_relations.items()
        if not _has_section_provenance(
            rel,
            section_id=section_id,
            stable_section_uid=stable_section_uid,
            provenance_keys=provenance_keys,
            stable_provenance_keys=stable_provenance_keys,
        )
    }

    kept_triplets = set()
    for triplet in _iter_triplets(raw_triplets):
        subj_id, rel_id, obj_id = triplet
        if subj_id not in kept_node_ids or obj_id not in kept_node_ids:
            continue
        if f"{subj_id}_{rel_id}_{obj_id}" not in kept_relations:
            continue
        kept_triplets.add(triplet)

    return store.__class__.from_dict(
        {
            "nodes": kept_nodes,
            "relations": kept_relations,
            "triplets": kept_triplets,
        }
    )


def _has_section_provenance(
    artifact: dict[str, Any],
    *,
    section_id: str,
    stable_section_uid: str | None,
    provenance_keys: tuple[str, ...],
    stable_provenance_keys: tuple[str, ...],
) -> bool:
    props = artifact.get("properties") or {}
    if stable_section_uid and any(
        props.get(key) == stable_section_uid for key in stable_provenance_keys
    ):
        return True
    return any(props.get(key) == section_id for key in provenance_keys)


def _iter_triplets(raw_triplets: Any) -> set[tuple[str, str, str]]:
    if isinstance(raw_triplets, set):
        return {tuple(triplet) for triplet in raw_triplets}
    return {tuple(triplet) for triplet in raw_triplets or []}
