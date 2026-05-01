from __future__ import annotations

from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode
from llama_index.core.schema import TextNode
from llama_index.core.vector_stores.simple import SimpleVectorStore

from spec_grag.chunk_index import (
    ChunkEmbedding,
    ChunkVectorIndex,
    DocumentChunk,
    DocumentChunksSidecar,
    build_chunk_vector_index,
)
from spec_grag.core import build_vector_store
from spec_grag.embedding import EmbeddingMetadata


def embedding_metadata() -> EmbeddingMetadata:
    return EmbeddingMetadata(provider="ollama", model="bge-m3", dimension=2)


def document_chunk(chunk_id: str, *, chunk_hash: str, text: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id="docs/spec/auth.md",
        chapter_id="docs/spec/auth.md#auth",
        section_id="docs/spec/auth.md#auth",
        heading_path="Auth",
        source_span="1-3",
        source_hash="source-hash",
        text=text,
        chunk_hash=chunk_hash,
        generated_at="now",
    )


def test_chunk_vector_index_reuses_unchanged_embeddings(monkeypatch) -> None:
    metadata = embedding_metadata()
    chunks = DocumentChunksSidecar(
        graph_revision="graph:new",
        generated_at="new",
        chunks=[
            document_chunk("chunk:auth:0", chunk_hash="hash-same", text="same"),
            document_chunk("chunk:auth:1", chunk_hash="hash-new", text="changed"),
        ],
    )
    previous = ChunkVectorIndex(
        graph_revision="graph:old",
        generated_at="old",
        embedding_metadata=metadata,
        embeddings=[
            ChunkEmbedding(
                chunk_id="chunk:auth:0",
                chunk_hash="hash-same",
                embedding=[0.1, 0.2],
            ),
            ChunkEmbedding(
                chunk_id="chunk:auth:1",
                chunk_hash="hash-old",
                embedding=[9.0, 9.0],
            ),
        ],
    )
    calls: list[str] = []

    def fake_embedding(text: str, *_args, **_kwargs) -> list[float]:
        calls.append(text)
        return [1.0, 2.0]

    monkeypatch.setattr("spec_grag.chunk_index.embedding_for_text", fake_embedding)

    index = build_chunk_vector_index(
        chunks,
        embedding_metadata=metadata,
        previous_index=previous,
    )

    by_chunk = index.by_chunk_id()
    assert by_chunk["chunk:auth:0"].embedding == [0.1, 0.2]
    assert by_chunk["chunk:auth:1"].embedding == [1.0, 2.0]
    assert calls == ["changed"]


def test_vector_store_reuses_unchanged_entity_embeddings(monkeypatch) -> None:
    metadata = embedding_metadata()
    graph_store = SimplePropertyGraphStore()
    graph_store.upsert_nodes(
        [
            EntityNode(
                label="ANCHOR",
                name="auth_anchor",
                properties={"source_hash": "hash-same"},
            ),
            EntityNode(
                label="ANCHOR",
                name="session_anchor",
                properties={"source_hash": "hash-new"},
            ),
        ]
    )
    previous = SimpleVectorStore()
    previous.add(
        [
            TextNode(
                id_="auth_anchor",
                text="auth_anchor",
                embedding=[0.1, 0.2],
                metadata={
                    "source_hash": "hash-same",
                    "embedding_provider": "ollama",
                    "embedding_model": "bge-m3",
                    "embedding_dimension": 2,
                },
            ),
            TextNode(
                id_="session_anchor",
                text="session_anchor",
                embedding=[9.0, 9.0],
                metadata={
                    "source_hash": "hash-old",
                    "embedding_provider": "ollama",
                    "embedding_model": "bge-m3",
                    "embedding_dimension": 2,
                },
            ),
        ]
    )
    calls: list[str] = []

    def fake_embedding(text: str, *_args, **_kwargs) -> list[float]:
        calls.append(text)
        return [1.0, 2.0]

    monkeypatch.setattr("spec_grag.core.embedding_for_text", fake_embedding)

    vector_store = build_vector_store(
        graph_store,
        embedding_metadata=metadata,
        previous_vector_store=previous,
    )

    assert vector_store.data.embedding_dict["auth_anchor"] == [0.1, 0.2]
    assert vector_store.data.embedding_dict["session_anchor"] == [1.0, 2.0]
    assert calls == ["session_anchor"]
