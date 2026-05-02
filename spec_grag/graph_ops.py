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

    return safe_delete_by_sections(
        store,
        section_ids=(section_id,),
        stable_section_uids=(stable_section_uid,) if stable_section_uid else (),
        provenance_keys=provenance_keys,
        stable_provenance_keys=stable_provenance_keys,
    )


def safe_delete_by_sections(
    store: Any,
    *,
    section_ids: tuple[str, ...],
    stable_section_uids: tuple[str, ...] = (),
    provenance_keys: tuple[str, ...] = ("source_section_id",),
    stable_provenance_keys: tuple[str, ...] = (
        "stable_source_section_uid",
        "stable_section_uid",
    ),
) -> Any:
    """Delete LLM-extracted graph artifacts for multiple source sections."""

    data = store.graph.model_dump()
    raw_nodes: dict[str, Any] = data.get("nodes", {})
    raw_relations: dict[str, Any] = data.get("relations", {})
    raw_triplets = data.get("triplets", set())
    section_id_set = set(section_ids)
    stable_section_uid_set = {uid for uid in stable_section_uids if uid}

    kept_nodes = {
        node_id: node
        for node_id, node in raw_nodes.items()
        if not _has_any_section_provenance(
            node,
            section_ids=section_id_set,
            stable_section_uids=stable_section_uid_set,
            provenance_keys=provenance_keys,
            stable_provenance_keys=stable_provenance_keys,
        )
    }
    kept_node_ids = set(kept_nodes)
    kept_relations = {
        rel_key: rel
        for rel_key, rel in raw_relations.items()
        if not _has_any_section_provenance(
            rel,
            section_ids=section_id_set,
            stable_section_uids=stable_section_uid_set,
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


def _has_any_section_provenance(
    artifact: dict[str, Any],
    *,
    section_ids: set[str],
    stable_section_uids: set[str],
    provenance_keys: tuple[str, ...],
    stable_provenance_keys: tuple[str, ...],
) -> bool:
    props = artifact.get("properties") or {}
    if stable_section_uids and any(
        props.get(key) in stable_section_uids for key in stable_provenance_keys
    ):
        return True
    return any(props.get(key) in section_ids for key in provenance_keys)


def _iter_triplets(raw_triplets: Any) -> set[tuple[str, str, str]]:
    if isinstance(raw_triplets, set):
        return {tuple(triplet) for triplet in raw_triplets}
    return {tuple(triplet) for triplet in raw_triplets or []}
