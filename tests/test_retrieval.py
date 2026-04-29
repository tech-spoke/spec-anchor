from __future__ import annotations

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode, Relation, VECTOR_SOURCE_KEY
from llama_index.core.indices.property_graph import PGRetriever, VectorContextRetriever
from llama_index.core.schema import QueryBundle
from llama_index.core.vector_stores.simple import SimpleVectorStore

from spec_grag.retrieval import (
    Relevance,
    add_entities_to_vector_store,
    annotate_4axis,
    entity_to_vector_text_node,
    keyword_property_fallback,
)


class FakeEmbedding(BaseEmbedding):
    def _get_query_embedding(self, query: str):
        return self._embed(query)

    async def _aget_query_embedding(self, query: str):
        return self._embed(query)

    def _get_text_embedding(self, text: str):
        return self._embed(text)

    def _embed(self, text: str):
        lowered = text.lower()
        return [
            1.0 if "auth" in lowered or "認証" in lowered else 0.0,
            1.0 if "session" in lowered or "セッション" in lowered else 0.0,
            1.0 if "payment" in lowered or "決済" in lowered else 0.0,
        ]


def auth_entity() -> EntityNode:
    return EntityNode(
        label="ANCHOR",
        name="auth_anchor",
        embedding=[1.0, 0.0, 0.0],
        properties={
            "source_section_id": "docs/spec/auth.md#auth",
            "heading_path": "Auth",
            "source_hash": "hash-auth",
        },
    )


def session_entity() -> EntityNode:
    return EntityNode(
        label="ANCHOR",
        name="session_anchor",
        embedding=[0.0, 1.0, 0.0],
        properties={
            "source_section_id": "docs/spec/session.md#session",
            "heading_path": "Session",
            "source_hash": "hash-session",
        },
    )


def test_entity_to_vector_text_node_copies_vector_source_and_properties() -> None:
    node = entity_to_vector_text_node(auth_entity())

    assert node.metadata[VECTOR_SOURCE_KEY] == "auth_anchor"
    assert node.metadata["source_section_id"] == "docs/spec/auth.md#auth"
    assert node.embedding == [1.0, 0.0, 0.0]


def test_vector_context_retriever_and_pg_retriever_smoke() -> None:
    graph_store = SimplePropertyGraphStore()
    vector_store = SimpleVectorStore()
    entities = [auth_entity(), session_entity()]
    graph_store.upsert_nodes(entities)
    graph_store.upsert_relations(
        [
            Relation(
                label="DEPENDS_ON",
                source_id="auth_anchor",
                target_id="session_anchor",
                properties={"source_section_id": "docs/spec/session.md#session"},
            )
        ]
    )
    add_entities_to_vector_store(
        vector_store,
        entities,
        text_by_entity_id={
            "auth_anchor": "ユーザー認証 auth",
            "session_anchor": "セッション session",
        },
    )

    vector_retriever = VectorContextRetriever(
        graph_store=graph_store,
        vector_store=vector_store,
        embed_model=FakeEmbedding(),
        similarity_top_k=1,
        include_text=True,
    )
    vector_results = vector_retriever.retrieve(QueryBundle(query_str="認証 auth"))
    pg_results = PGRetriever(sub_retrievers=[vector_retriever], use_async=False).retrieve(
        QueryBundle(query_str="認証 auth")
    )

    assert vector_results
    assert pg_results
    assert "auth_anchor" in pg_results[0].node.get_content()


def test_keyword_property_fallback_returns_source_metadata() -> None:
    graph_store = SimplePropertyGraphStore()
    graph_store.upsert_nodes([auth_entity(), session_entity()])

    results = keyword_property_fallback(graph_store, "Auth", limit=5)

    assert len(results) == 1
    assert results[0].node.metadata["source_section_id"] == "docs/spec/auth.md#auth"
    assert results[0].node.metadata["source_origin"] == "graph_keyword_fallback"


def test_annotate_4axis_does_not_write_to_graph_store() -> None:
    graph_store = SimplePropertyGraphStore()
    graph_store.upsert_nodes([auth_entity()])
    result = keyword_property_fallback(graph_store, "Auth")[0]

    annotate_4axis(
        result,
        constraint_relevance=Relevance.HIGH,
        target_relevance=Relevance.LOW,
        semantic_conflict_candidate=False,
        review_required=True,
        reason_for_current_task="認証制約として参照",
        source_origin="GRAG",
    )

    assert result.node.metadata["constraint_relevance"] == "high"
    assert result.node.metadata["review_required"] is True
    graph_data = graph_store.graph.model_dump()
    assert "constraint_relevance" not in str(graph_data)
