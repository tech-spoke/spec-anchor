"""Lightweight reverse indexes for query-time retrieval."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import Field

from spec_grag.chunk_index import DocumentChunksSidecar
from spec_grag.protocol import StrictModel


RETRIEVAL_INDEX_VERSION = "1"
RETRIEVAL_INDEX_FILENAME = "retrieval_index.json"


class RetrievalRelationRef(StrictModel):
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    source_section_id: str | None = None
    source_chunk_id: str | None = None
    confidence: str | float | int | None = None


class RetrievalIndex(StrictModel):
    version: str = RETRIEVAL_INDEX_VERSION
    graph_revision: str | None = None
    generated_at: str | None = None
    section_chunks: dict[str, list[str]] = Field(default_factory=dict)
    section_graph_nodes: dict[str, list[str]] = Field(default_factory=dict)
    section_relations: dict[str, list[str]] = Field(default_factory=dict)
    node_outgoing_relations: dict[str, list[str]] = Field(default_factory=dict)
    node_incoming_relations: dict[str, list[str]] = Field(default_factory=dict)
    relations: dict[str, RetrievalRelationRef] = Field(default_factory=dict)


def retrieval_index_path(graph_storage: Path) -> Path:
    return graph_storage / RETRIEVAL_INDEX_FILENAME


def load_retrieval_index(path: Path) -> RetrievalIndex | None:
    if not path.exists():
        return None
    return RetrievalIndex.model_validate_json(path.read_text(encoding="utf-8"))


def write_retrieval_index_atomic(path: Path, index: RetrievalIndex) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = index.model_dump_json(indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            tmp_path.unlink()


def build_retrieval_index(
    *,
    graph_data: dict[str, Any],
    document_chunks: DocumentChunksSidecar,
    graph_revision: str | None,
    generated_at: str | None,
) -> RetrievalIndex:
    section_chunks: dict[str, list[str]] = {}
    for chunk in document_chunks.chunks:
        section_chunks.setdefault(chunk.section_id, []).append(chunk.chunk_id)

    section_graph_nodes: dict[str, list[str]] = {}
    for node_id, node in (graph_data.get("nodes") or {}).items():
        label = str(node.get("label") or "")
        if label not in {"SECTION", "ANCHOR"}:
            continue
        props = _properties(node)
        section_id = props.get("section_id") or props.get("source_section_id")
        if section_id:
            section_graph_nodes.setdefault(str(section_id), []).append(str(node_id))

    section_relations: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {}
    incoming: dict[str, list[str]] = {}
    relations: dict[str, RetrievalRelationRef] = {}
    for relation_id, relation in (graph_data.get("relations") or {}).items():
        source_id = str(relation.get("source_id") or "")
        target_id = str(relation.get("target_id") or "")
        if not source_id or not target_id:
            continue
        relation_key = str(relation_id)
        props = _properties(relation)
        source_section_id = props.get("section_id") or props.get("source_section_id")
        source_chunk_id = props.get("source_chunk_id")
        relations[relation_key] = RetrievalRelationRef(
            relation_id=relation_key,
            source_id=source_id,
            target_id=target_id,
            relation_type=str(relation.get("label") or ""),
            source_section_id=str(source_section_id) if source_section_id else None,
            source_chunk_id=str(source_chunk_id) if source_chunk_id else None,
            confidence=props.get("confidence"),
        )
        outgoing.setdefault(source_id, []).append(relation_key)
        incoming.setdefault(target_id, []).append(relation_key)
        if source_section_id:
            section_relations.setdefault(str(source_section_id), []).append(relation_key)

    return RetrievalIndex(
        graph_revision=graph_revision,
        generated_at=generated_at,
        section_chunks={key: sorted(set(value)) for key, value in sorted(section_chunks.items())},
        section_graph_nodes={
            key: sorted(set(value)) for key, value in sorted(section_graph_nodes.items())
        },
        section_relations={
            key: sorted(set(value)) for key, value in sorted(section_relations.items())
        },
        node_outgoing_relations={key: sorted(set(value)) for key, value in sorted(outgoing.items())},
        node_incoming_relations={key: sorted(set(value)) for key, value in sorted(incoming.items())},
        relations=dict(sorted(relations.items())),
    )


def _properties(item: dict[str, Any]) -> dict[str, Any]:
    props = item.get("properties")
    return props if isinstance(props, dict) else {}
