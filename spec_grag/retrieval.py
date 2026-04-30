"""Retrieval helpers owned by the SPEC-grag Orchestrator."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from llama_index.core.graph_stores.types import EntityNode, VECTOR_SOURCE_KEY
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.vector_stores.simple import SimpleVectorStore


class Relevance(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


def entity_to_vector_text_node(entity: EntityNode, *, text: str | None = None) -> TextNode:
    """Create the TextNode pattern VectorContextRetriever expects.

    LlamaIndex maps vector hits back to KG nodes through
    metadata[VECTOR_SOURCE_KEY]. SPEC-grag also copies entity properties into
    TextNode.metadata so retrieval results can carry source provenance.
    """

    metadata = dict(entity.properties or {})
    metadata[VECTOR_SOURCE_KEY] = entity.id
    return TextNode(
        id_=entity.id,
        text=text or _entity_text(entity),
        metadata=metadata,
        embedding=entity.embedding,
    )


def add_entities_to_vector_store(
    vector_store: SimpleVectorStore,
    entities: list[EntityNode],
    *,
    text_by_entity_id: dict[str, str] | None = None,
) -> list[str]:
    text_by_entity_id = text_by_entity_id or {}
    nodes = [
        entity_to_vector_text_node(entity, text=text_by_entity_id.get(entity.id))
        for entity in entities
    ]
    return vector_store.add(nodes)


def annotate_4axis(
    node_with_score: NodeWithScore,
    *,
    constraint_relevance: Relevance,
    target_relevance: Relevance,
    semantic_conflict_candidate: bool = False,
    review_required: bool = False,
    reason_for_current_task: str | None = None,
    source_origin: str | None = None,
) -> NodeWithScore:
    """Attach transient task-specific classification to a retrieval result."""

    metadata = dict(node_with_score.node.metadata or {})
    metadata.update(
        {
            "constraint_relevance": constraint_relevance.value,
            "target_relevance": target_relevance.value,
            "semantic_conflict_candidate": semantic_conflict_candidate,
            "review_required": review_required,
        }
    )
    if reason_for_current_task is not None:
        metadata["reason_for_current_task"] = reason_for_current_task
    if source_origin is not None:
        metadata["source_origin"] = source_origin
    node_with_score.node.metadata = metadata
    return node_with_score


def keyword_property_fallback(
    graph_store: Any,
    query: str,
    *,
    limit: int = 10,
) -> list[NodeWithScore]:
    """Fallback retrieval using graph node name/properties when vector hits are empty."""

    tokens = _tokens(query)
    if not tokens:
        return []

    results: list[NodeWithScore] = []
    for node in graph_store.get():
        haystack = _node_haystack(node)
        if not any(token in haystack for token in tokens):
            continue
        metadata = dict(node.properties or {})
        metadata["source_origin"] = "graph_keyword_fallback"
        results.append(
            NodeWithScore(
                node=TextNode(
                    id_=f"fallback:{node.id}",
                    text=_entity_text(node),
                    metadata=metadata,
                ),
                score=0.0,
            )
        )
        if len(results) >= limit:
            break
    return results


def _entity_text(entity: EntityNode) -> str:
    props = entity.properties or {}
    parts = [entity.label, entity.name]
    for key in ("heading_path", "summary", "description", "evidence_excerpt"):
        value = props.get(key)
        if value:
            parts.append(str(value))
    return " ".join(parts)


def _tokens(query: str) -> list[str]:
    return [token.lower() for token in query.replace("　", " ").split() if token.strip()]


def _node_haystack(node: EntityNode) -> str:
    props = node.properties or {}
    prop_text = " ".join(str(value) for value in props.values())
    return f"{node.id} {node.name} {node.label} {prop_text}".lower()
