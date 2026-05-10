"""Source Retrieval Index primitives for lightweight SPEC-grag.

The standard retrieval stack is Qdrant + BGE-M3 dense/sparse vectors + RRF.
This module keeps provider and service imports lazy so unit tests can exercise
chunking, sparse normalization, schema metadata, and fusion without starting
FlagEmbedding or Qdrant.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import math
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


STANDARD_VECTOR_STORE_PROVIDER = "qdrant"
STANDARD_EMBEDDING_PROVIDER = "flagembedding"
STANDARD_EMBEDDING_MODEL = "BAAI/bge-m3"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
BGE_M3_DENSE_SIZE = 1024
DENSE_DISTANCE = "cosine"
SPARSE_VECTOR_KIND = "bge-m3 lexical weights"
FUSION_METHOD = "rrf"
DEFAULT_RRF_K = 60
QDRANT_COLLECTION_SCHEMA_VERSION = "qdrant-bge-m3-hybrid-v2-stable-ids"
# Bumped from v1 in 2026-05-10: point ids are now derived from stable_chunk_uid
# (UUID5) instead of sequential ints, enabling incremental upsert. Existing
# collections with int ids will be recreated on next run (schema mismatch).
QDRANT_POINT_ID_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-5e1c61a9da41")
PAYLOAD_SCHEMA_VERSION = 1
SOURCE_CHUNKS_ARTIFACT_VERSION = 1
RETRIEVAL_INDEX_REVISION_ARTIFACT_VERSION = 1
SECTION_EMBEDDINGS_ARTIFACT_VERSION = 1
DEFAULT_SECTION_COLLECTION = "spec_grag_section"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_TOKEN_RE = re.compile(
    r"@[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"|[A-Za-z_][A-Za-z0-9_.-]*"
    r"|[0-9]+"
    r"|[一-龯ぁ-んァ-ンー]{2,}"
)


@dataclass(frozen=True)
class SparseVector:
    """Qdrant-compatible sparse vector data."""

    indices: list[int] = field(default_factory=list)
    values: list[float] = field(default_factory=list)

    def to_payload(self) -> dict[str, list[int] | list[float]]:
        return {"indices": list(self.indices), "values": list(self.values)}


@dataclass(frozen=True)
class BgeM3Embedding:
    """One BGE-M3 embedding result."""

    dense: list[float] | None = None
    sparse: SparseVector | None = None


@dataclass(frozen=True)
class BgeM3EmbeddingBatch:
    """Batch BGE-M3 embedding result."""

    embeddings: list[BgeM3Embedding]
    provider: str = STANDARD_EMBEDDING_PROVIDER
    model: str = STANDARD_EMBEDDING_MODEL


@runtime_checkable
class BgeM3EmbeddingProvider(Protocol):
    """Interface expected from a BGE-M3 dense/sparse embedding provider."""

    provider_id: str
    model: str
    dense_enabled: bool
    sparse_enabled: bool

    def embed_documents(self, texts: Sequence[str]) -> BgeM3EmbeddingBatch:
        """Embed source chunks."""

    def embed_query(self, text: str) -> BgeM3Embedding:
        """Embed a query string."""


@dataclass(frozen=True)
class SourceChunk:
    source_document_id: str
    source_section_id: str
    stable_section_uid: str
    stable_chunk_uid: str
    heading_path: list[str]
    source_span: dict[str, int]
    source_hash: str
    chunk_hash: str
    text: str
    artifact_revision: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_document_id": self.source_document_id,
            "source_section_id": self.source_section_id,
            "stable_section_uid": self.stable_section_uid,
            "stable_chunk_uid": self.stable_chunk_uid,
            "heading_path": list(self.heading_path),
            "source_span": dict(self.source_span),
            "source_hash": self.source_hash,
            "chunk_hash": self.chunk_hash,
            "text": self.text,
            "artifact_revision": self.artifact_revision,
        }


@dataclass(frozen=True)
class RetrievalHit:
    stable_chunk_uid: str
    score: float
    payload: dict[str, Any]
    point_id: str | int | None = None

    @property
    def source_section_id(self) -> str:
        return str(self.payload.get("source_section_id", ""))

    @property
    def text(self) -> str:
        return str(self.payload.get("text", ""))


@dataclass(frozen=True)
class FusedRetrievalHit:
    stable_chunk_uid: str
    score: float
    payload: dict[str, Any]
    rank: int
    dense_rank: int | None = None
    dense_score: float | None = None
    sparse_rank: int | None = None
    sparse_score: float | None = None

    @property
    def source_section_id(self) -> str:
        return str(self.payload.get("source_section_id", ""))

    @property
    def text(self) -> str:
        return str(self.payload.get("text", ""))


@dataclass(frozen=True)
class RetrievalFusionResult:
    hits: list[FusedRetrievalHit]
    diagnostics: dict[str, Any]

    @property
    def results(self) -> list[FusedRetrievalHit]:
        return self.hits


@dataclass(frozen=True)
class HybridRetrievalResult:
    hits: list[FusedRetrievalHit]
    diagnostics: dict[str, Any]

    @property
    def results(self) -> list[FusedRetrievalHit]:
        return self.hits


class FlagEmbeddingBgeM3Provider:
    """Real BGE-M3 provider backed by FlagEmbedding.

    Real provider initialization can be expensive and may download model
    weights. Direct construction is guarded unless ``allow_real_provider=True``
    is passed, ``SPEC_GRAG_REAL_RETRIEVAL`` is set for a test probe, or an
    explicit real-smoke test is enabled. The standard `/spec-core` Qdrant /
    BGE-M3 path passes ``allow_real_provider=True`` when project config selects
    the production retrieval stack.
    """

    provider_id = STANDARD_EMBEDDING_PROVIDER

    def __init__(
        self,
        *,
        model: str = STANDARD_EMBEDDING_MODEL,
        dense_enabled: bool = True,
        sparse_enabled: bool = True,
        allow_real_provider: bool = False,
        **model_kwargs: Any,
    ) -> None:
        if not allow_real_provider and not _real_retrieval_provider_enabled():
            raise RuntimeError(
                "FlagEmbedding BGE-M3 direct construction is guarded. "
                "Pass allow_real_provider=True for the standard /spec-core path, "
                "or set SPEC_GRAG_REAL_RETRIEVAL=1 / SPEC_GRAG_REAL_SMOKE=1 "
                "for explicit tests."
            )
        from FlagEmbedding import BGEM3FlagModel  # type: ignore[import-not-found]

        self.model = model
        self.dense_enabled = dense_enabled
        self.sparse_enabled = sparse_enabled
        self.model_cache_dir = _model_cache_dir()
        self.model_kwargs = dict(model_kwargs)
        self._model = BGEM3FlagModel(model, **model_kwargs)

    def embed_documents(self, texts: Sequence[str]) -> BgeM3EmbeddingBatch:
        encoded = self._encode(texts)
        return BgeM3EmbeddingBatch(
            embeddings=_embeddings_from_bge_m3_output(
                encoded,
                len(texts),
                dense_enabled=self.dense_enabled,
                sparse_enabled=self.sparse_enabled,
            ),
            provider=self.provider_id,
            model=self.model,
        )

    def embed_query(self, text: str) -> BgeM3Embedding:
        return self.embed_documents([text]).embeddings[0]

    def _encode(self, texts: Sequence[str]) -> Mapping[str, Any]:
        return self._model.encode(
            list(texts),
            return_dense=self.dense_enabled,
            return_sparse=self.sparse_enabled,
            return_colbert_vecs=False,
        )


class FakeBgeM3EmbeddingProvider:
    """Deterministic in-process provider for tests and offline development."""

    provider_id = "fake-bge-m3"

    def __init__(
        self,
        *,
        model: str = STANDARD_EMBEDDING_MODEL,
        dense_enabled: bool = True,
        sparse_enabled: bool = True,
        dense_size: int = BGE_M3_DENSE_SIZE,
    ) -> None:
        self.model = model
        self.dense_enabled = dense_enabled
        self.sparse_enabled = sparse_enabled
        self.dense_size = dense_size

    def embed_documents(self, texts: Sequence[str]) -> BgeM3EmbeddingBatch:
        embeddings = [self._embed_one(text) for text in texts]
        return BgeM3EmbeddingBatch(
            embeddings=embeddings,
            provider=self.provider_id,
            model=self.model,
        )

    def embed_query(self, text: str) -> BgeM3Embedding:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> BgeM3Embedding:
        dense = _fake_dense_vector(text, self.dense_size) if self.dense_enabled else None
        sparse = _fake_sparse_vector(text) if self.sparse_enabled else None
        return BgeM3Embedding(dense=dense, sparse=sparse)


class InMemoryHybridRetriever:
    """Provider-free hybrid retrieval for unit tests.

    It uses deterministic fake BGE-M3-shaped vectors and the same RRF fusion
    path as the Qdrant-backed standard flow.
    """

    def __init__(
        self,
        chunks: Sequence[SourceChunk | Mapping[str, Any]],
        *,
        embedding_provider: BgeM3EmbeddingProvider | None = None,
        dense_enabled: bool = True,
        sparse_enabled: bool = True,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self.chunks = [_coerce_chunk_payload(chunk) for chunk in chunks]
        self.provider = embedding_provider or FakeBgeM3EmbeddingProvider(
            dense_enabled=dense_enabled,
            sparse_enabled=sparse_enabled,
        )
        self.dense_enabled = dense_enabled
        self.sparse_enabled = sparse_enabled
        self.rrf_k = rrf_k
        self._document_embeddings = self.provider.embed_documents(
            [chunk.get("text", "") for chunk in self.chunks]
        ).embeddings

    def search(
        self,
        query: str,
        *,
        dense_top_k: int = 12,
        sparse_top_k: int = 20,
        limit: int | None = None,
        fusion_owner: str = "cli",
    ) -> HybridRetrievalResult:
        if not query.strip():
            diagnostics = _empty_fusion_diagnostics(fusion_owner=fusion_owner)
            diagnostics.update(
                {
                    "dense_hit_count": 0,
                    "sparse_hit_count": 0,
                    "embedding_provider": self.provider.provider_id,
                    "embedding_model": self.provider.model,
                }
            )
            return HybridRetrievalResult(hits=[], diagnostics=diagnostics)

        query_embedding = self.provider.embed_query(query)
        dense_hits: list[RetrievalHit] = []
        sparse_hits: list[RetrievalHit] = []
        if self.dense_enabled and query_embedding.dense is not None:
            dense_hits = self._dense_search(query_embedding.dense, dense_top_k)
        if self.sparse_enabled and query_embedding.sparse is not None:
            sparse_hits = self._sparse_search(query_embedding.sparse, sparse_top_k)

        fused = rrf_fusion(
            dense_hits,
            sparse_hits,
            rrf_k=self.rrf_k,
            fusion_owner=fusion_owner,
            limit=limit,
        )
        diagnostics = dict(fused.diagnostics)
        diagnostics.update(
            {
                "dense_hit_count": len(dense_hits),
                "sparse_hit_count": len(sparse_hits),
                "embedding_provider": self.provider.provider_id,
                "embedding_model": self.provider.model,
            }
        )
        return HybridRetrievalResult(hits=fused.hits, diagnostics=diagnostics)

    def _dense_search(self, query_dense: Sequence[float], limit: int) -> list[RetrievalHit]:
        scored: list[RetrievalHit] = []
        for payload, embedding in zip(self.chunks, self._document_embeddings, strict=False):
            if embedding.dense is None:
                continue
            score = _cosine_similarity(query_dense, embedding.dense)
            if score <= 0:
                continue
            scored.append(_hit_from_payload(payload, score=score))
        return _top_hits(scored, limit)

    def _sparse_search(self, query_sparse: SparseVector, limit: int) -> list[RetrievalHit]:
        scored: list[RetrievalHit] = []
        for payload, embedding in zip(self.chunks, self._document_embeddings, strict=False):
            if embedding.sparse is None:
                continue
            score = _sparse_dot(query_sparse, embedding.sparse)
            if score <= 0:
                continue
            scored.append(_hit_from_payload(payload, score=score))
        return _top_hits(scored, limit)


class QdrantHybridRetriever:
    """Real Qdrant + BGE-M3 dense/sparse retriever for normal operation."""

    def __init__(
        self,
        *,
        url: str = "http://localhost:6333",
        collection: str = "spec_grag_source",
        embedding_provider: BgeM3EmbeddingProvider | None = None,
        dense_enabled: bool = True,
        sparse_enabled: bool = True,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        from qdrant_client import QdrantClient  # type: ignore[import-not-found]

        self.url = url
        self.collection = collection
        self.client = QdrantClient(url)
        self.provider = embedding_provider or FlagEmbeddingBgeM3Provider(
            allow_real_provider=True,
            use_fp16=False,
        )
        self.dense_enabled = dense_enabled
        self.sparse_enabled = sparse_enabled
        self.rrf_k = rrf_k

    def search(
        self,
        query: str,
        *,
        dense_top_k: int = 12,
        sparse_top_k: int = 20,
        limit: int | None = None,
        fusion_owner: str = "qdrant",
    ) -> HybridRetrievalResult:
        if not query.strip():
            diagnostics = self._diagnostics(
                _empty_fusion_diagnostics(fusion_owner=fusion_owner),
                dense_hit_count=0,
                sparse_hit_count=0,
            )
            return HybridRetrievalResult(hits=[], diagnostics=diagnostics)

        query_embedding = self.provider.embed_query(query)
        dense_hits: list[RetrievalHit] = []
        sparse_hits: list[RetrievalHit] = []
        if self.dense_enabled and query_embedding.dense is not None:
            dense_hits = self._dense_search(query_embedding.dense, dense_top_k)
        if self.sparse_enabled and query_embedding.sparse is not None:
            sparse_hits = self._sparse_search(query_embedding.sparse, sparse_top_k)

        fused = rrf_fusion(
            dense_hits,
            sparse_hits,
            rrf_k=self.rrf_k,
            fusion_owner=fusion_owner,
            limit=limit,
        )
        diagnostics = self._diagnostics(
            fused.diagnostics,
            dense_hit_count=len(dense_hits),
            sparse_hit_count=len(sparse_hits),
        )
        return HybridRetrievalResult(hits=fused.hits, diagnostics=diagnostics)

    def _dense_search(self, query_dense: Sequence[float], limit: int) -> list[RetrievalHit]:
        points = self.client.query_points(
            collection_name=self.collection,
            query=[float(value) for value in query_dense],
            using=DENSE_VECTOR_NAME,
            limit=limit,
        ).points
        return [_hit_from_qdrant_point(point) for point in points]

    def _sparse_search(self, query_sparse: SparseVector, limit: int) -> list[RetrievalHit]:
        if not query_sparse.indices:
            return []
        from qdrant_client import models as qdrant_models  # type: ignore[import-not-found]

        points = self.client.query_points(
            collection_name=self.collection,
            query=qdrant_models.SparseVector(
                indices=list(query_sparse.indices),
                values=[float(value) for value in query_sparse.values],
            ),
            using=SPARSE_VECTOR_NAME,
            limit=limit,
        ).points
        return [_hit_from_qdrant_point(point) for point in points]

    def _diagnostics(
        self,
        diagnostics: Mapping[str, Any],
        *,
        dense_hit_count: int,
        sparse_hit_count: int,
    ) -> dict[str, Any]:
        payload = dict(diagnostics)
        payload.update(
            {
                "real_retrieval_index": True,
                "qdrant_url": self.url,
                "collection": self.collection,
                "dense_vector": DENSE_VECTOR_NAME,
                "sparse_vector": SPARSE_VECTOR_NAME,
                "dense_hit_count": dense_hit_count,
                "sparse_hit_count": sparse_hit_count,
                "embedding_provider": self.provider.provider_id,
                "embedding_model": self.provider.model,
                "fusion_method": FUSION_METHOD,
                "rrf_k": self.rrf_k,
            }
        )
        return payload


def build_source_chunks(
    sections: Sequence[Any],
    *,
    retrieval_config: Any | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    artifact_revision: str | None = None,
) -> list[SourceChunk]:
    """Split Source Spec sections into stable payload chunks."""

    size = int(_config_value(retrieval_config, "chunk_size", chunk_size or 1200))
    overlap = int(_config_value(retrieval_config, "chunk_overlap", chunk_overlap or 160))
    if size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("chunk_overlap must be non-negative")
    if overlap >= size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    normalized_sections = [_normalize_section(section) for section in sections]
    revision = artifact_revision or _artifact_revision_from_sections(normalized_sections)
    chunks: list[SourceChunk] = []
    for section in normalized_sections:
        for ordinal, (start, end) in enumerate(
            _chunk_ranges(section["text"], chunk_size=size, chunk_overlap=overlap),
            start=1,
        ):
            text = section["text"][start:end]
            stable_chunk_uid = _stable_chunk_uid(section["stable_section_uid"], ordinal)
            chunks.append(
                SourceChunk(
                    source_document_id=section["source_document_id"],
                    source_section_id=section["source_section_id"],
                    stable_section_uid=section["stable_section_uid"],
                    stable_chunk_uid=stable_chunk_uid,
                    heading_path=list(section["heading_path"]),
                    source_span=_chunk_source_span(section["source_span"], section["text"], start, end),
                    source_hash=section["source_hash"],
                    chunk_hash=_hash_text(text),
                    text=text,
                    artifact_revision=revision,
                )
            )
    return chunks


def build_source_chunks_artifact(
    chunks: Sequence[SourceChunk | Mapping[str, Any]],
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    artifact_revision: str | None = None,
) -> dict[str, Any]:
    payloads = [_coerce_chunk_payload(chunk) for chunk in chunks]
    revision = artifact_revision or _artifact_revision_from_chunks(payloads)
    return {
        "artifact_version": SOURCE_CHUNKS_ARTIFACT_VERSION,
        "artifact_revision": revision,
        "chunking": {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        },
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
        "chunks": payloads,
    }


def normalize_bge_m3_sparse_output(output: Any, *, row: int = 0) -> SparseVector:
    """Normalize BGE-M3 sparse output for one row.

    Accepted forms include FlagEmbedding-style ``sparse_vecs`` matrix output
    and ``lexical_weights`` token-id dictionaries.
    """

    if output is None:
        return SparseVector()
    if isinstance(output, SparseVector):
        return output
    if isinstance(output, Mapping):
        if "lexical_weights" in output:
            return normalize_lexical_weights(output.get("lexical_weights"), row=row)
        if "sparse_vecs" in output:
            return normalize_sparse_vecs(output.get("sparse_vecs"), row=row)
        if _looks_like_lexical_weight_dict(output):
            return normalize_lexical_weights(output, row=row)
    return normalize_sparse_vecs(output, row=row)


def normalize_bge_m3_sparse_batch(
    output: Any,
    *,
    expected_count: int | None = None,
) -> list[SparseVector]:
    if expected_count is None:
        expected_count = _sparse_batch_length(output)
    return [normalize_bge_m3_sparse_output(output, row=row) for row in range(expected_count)]


def normalize_sparse_vectors(output: Any) -> list[SparseVector]:
    return normalize_bge_m3_sparse_batch(output)


def normalize_bge_m3_sparse_vectors(output: Any) -> list[SparseVector]:
    return normalize_bge_m3_sparse_batch(output)


def normalize_lexical_weights(value: Any, *, row: int = 0) -> SparseVector:
    if value is None:
        return SparseVector()
    if isinstance(value, SparseVector):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return SparseVector()
        if row >= len(value):
            return SparseVector()
        return normalize_lexical_weights(value[row], row=0)
    if not isinstance(value, Mapping):
        return SparseVector()

    pairs: dict[int, float] = {}
    for token_id, weight in value.items():
        index = _int_or_none(token_id)
        numeric_weight = _float_or_none(weight)
        if index is None or numeric_weight is None or numeric_weight == 0:
            continue
        pairs[index] = pairs.get(index, 0.0) + numeric_weight
    return _sparse_from_pairs(pairs.items())


def normalize_sparse_vecs(value: Any, *, row: int = 0) -> SparseVector:
    if value is None:
        return SparseVector()
    if isinstance(value, SparseVector):
        return value
    if isinstance(value, Mapping):
        if _looks_like_lexical_weight_dict(value):
            return normalize_lexical_weights(value, row=row)
        indices = value.get("indices")
        values = value.get("values", value.get("data"))
        if indices is not None and values is not None:
            return _sparse_from_parallel(indices, values)
    if hasattr(value, "getrow"):
        try:
            return normalize_sparse_vecs(value.getrow(row), row=0)
        except Exception:
            return SparseVector()
    if hasattr(value, "tocoo"):
        try:
            coo = value.tocoo()
            if hasattr(coo, "col") and hasattr(coo, "row"):
                pairs = {
                    int(col): float(data)
                    for matrix_row, col, data in zip(coo.row, coo.col, coo.data, strict=False)
                    if int(matrix_row) == row
                }
                return _sparse_from_pairs(pairs.items())
            if hasattr(coo, "col") and hasattr(coo, "data"):
                return _sparse_from_parallel(coo.col, coo.data)
        except Exception:
            return SparseVector()
    if hasattr(value, "indices") and hasattr(value, "data"):
        return _sparse_from_parallel(getattr(value, "indices"), getattr(value, "data"))
    if isinstance(value, tuple) and len(value) == 2:
        return _sparse_from_parallel(value[0], value[1])
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return SparseVector()
        first = value[0]
        if all(_looks_like_pair(item) for item in value):
            pairs = []
            for item in value:
                index, sparse_value = item
                pairs.append((index, sparse_value))
            return _sparse_from_pairs(pairs)
        if isinstance(first, Mapping) or _looks_like_pair(first):
            if row >= len(value):
                return SparseVector()
            return normalize_sparse_vecs(value[row], row=0)
    return SparseVector()


def qdrant_named_vector_schema_metadata(
    *,
    collection: str | None = None,
    qdrant_server_version: str | None = None,
    flagembedding_package_version: str | None = None,
    embedding_model_revision: str | None = None,
) -> dict[str, Any]:
    """Return the pinned Qdrant dense/sparse named vector schema metadata."""

    return {
        "provider": STANDARD_VECTOR_STORE_PROVIDER,
        "collection": collection,
        "collection_schema_version": QDRANT_COLLECTION_SCHEMA_VERSION,
        "qdrant_server_version": qdrant_server_version or "unknown",
        "flagembedding_package_version": flagembedding_package_version
        or _package_version("FlagEmbedding"),
        "embedding_provider": STANDARD_EMBEDDING_PROVIDER,
        "embedding_model": STANDARD_EMBEDDING_MODEL,
        "embedding_model_revision": embedding_model_revision or "unknown",
        "dense": {
            "name": DENSE_VECTOR_NAME,
            "size": BGE_M3_DENSE_SIZE,
            "distance": DENSE_DISTANCE,
            "model": STANDARD_EMBEDDING_MODEL,
        },
        "sparse": {
            "name": SPARSE_VECTOR_NAME,
            "kind": SPARSE_VECTOR_KIND,
        },
        "named_vectors": {
            "dense": DENSE_VECTOR_NAME,
            "sparse": SPARSE_VECTOR_NAME,
        },
    }


def build_qdrant_collection_schema_metadata(**kwargs: Any) -> dict[str, Any]:
    return qdrant_named_vector_schema_metadata(**kwargs)


def qdrant_collection_config_metadata() -> dict[str, Any]:
    """Qdrant create-collection config shape without importing qdrant_client."""

    return {
        "vectors_config": {
            DENSE_VECTOR_NAME: {
                "size": BGE_M3_DENSE_SIZE,
                "distance": DENSE_DISTANCE,
            }
        },
        "sparse_vectors_config": {
            SPARSE_VECTOR_NAME: {
                "kind": SPARSE_VECTOR_KIND,
            }
        },
    }


def build_qdrant_point(
    chunk: SourceChunk | Mapping[str, Any],
    *,
    dense: Sequence[float] | None = None,
    sparse: SparseVector | Mapping[str, Any] | None = None,
    point_id: str | int | None = None,
) -> dict[str, Any]:
    payload = _coerce_chunk_payload(chunk)
    sparse_vector = normalize_bge_m3_sparse_output(sparse) if sparse is not None else SparseVector()
    vector: dict[str, Any] = {}
    if dense is not None:
        vector[DENSE_VECTOR_NAME] = [float(value) for value in dense]
    if sparse is not None:
        vector[SPARSE_VECTOR_NAME] = sparse_vector.to_payload()
    return {
        "id": point_id or payload["stable_chunk_uid"],
        "vector": vector,
        "payload": payload,
    }


def upsert_qdrant_bge_m3_index(
    chunks: Sequence[SourceChunk | Mapping[str, Any]],
    *,
    url: str = "http://localhost:6333",
    collection: str = "spec_grag_source",
    embedding_provider: BgeM3EmbeddingProvider | None = None,
    recreate: bool = True,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Create the standard Qdrant dense/sparse collection and upsert chunks."""

    from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    from qdrant_client import models as qdrant_models  # type: ignore[import-not-found]

    payloads = [_coerce_chunk_payload(chunk) for chunk in chunks]
    client = QdrantClient(url)
    server_version = _qdrant_server_version(client)
    provider = embedding_provider or FlagEmbeddingBgeM3Provider(
        allow_real_provider=True,
        use_fp16=False,
    )
    batch = provider.embed_documents([payload["text"] for payload in payloads])

    if recreate:
        client.recreate_collection(
            collection_name=collection,
            vectors_config={
                DENSE_VECTOR_NAME: qdrant_models.VectorParams(
                    size=BGE_M3_DENSE_SIZE,
                    distance=qdrant_models.Distance.COSINE,
                )
            },
            sparse_vectors_config={SPARSE_VECTOR_NAME: qdrant_models.SparseVectorParams()},
        )

    points = []
    for payload, embedding in zip(payloads, batch.embeddings, strict=True):
        sparse = embedding.sparse or SparseVector()
        points.append(
            qdrant_models.PointStruct(
                id=stable_chunk_uid_to_point_id(payload["stable_chunk_uid"]),
                vector={
                    DENSE_VECTOR_NAME: [float(value) for value in (embedding.dense or [])],
                    SPARSE_VECTOR_NAME: qdrant_models.SparseVector(
                        indices=list(sparse.indices),
                        values=[float(value) for value in sparse.values],
                    ),
                },
                payload=payload,
            )
        )
    if points:
        client.upsert(collection_name=collection, points=points)

    revision = _artifact_revision_from_chunks(
        payloads,
        schema=qdrant_named_vector_schema_metadata(
            collection=collection,
            qdrant_server_version=server_version,
        ),
    )
    artifact = build_retrieval_index_revision_artifact(
        chunks=payloads,
        artifact_revision=revision,
        collection=collection,
        qdrant_server_version=server_version,
        qdrant_collection_revision=revision,
        generated_at=generated_at,
    )
    artifact["status"] = "success"
    artifact["diagnostics"] = {
        "real_retrieval_index": True,
        "qdrant_url": url,
        "collection": collection,
        "qdrant_server_version": server_version,
        "embedding_model": STANDARD_EMBEDDING_MODEL,
        "embedding_provider": STANDARD_EMBEDDING_PROVIDER,
        "flagembedding_package_version": _package_version("FlagEmbedding"),
        "embedding_device": _provider_device(provider),
        "embedding_model_cache_dir": _provider_model_cache_dir(provider),
        "embedding_model_revision": "unknown",
        "dense_vector": DENSE_VECTOR_NAME,
        "sparse_vector": SPARSE_VECTOR_NAME,
        "fusion_method": FUSION_METHOD,
        "rrf_k": DEFAULT_RRF_K,
        "chunk_count": len(payloads),
        "upsert_mode": "full_recreate" if recreate else "full_overwrite",
    }
    return artifact


def stable_chunk_uid_to_point_id(stable_chunk_uid: str) -> str:
    """Map a chunk's stable UID to a deterministic Qdrant point id.

    Using UUIDv5 keyed by ``stable_chunk_uid`` means re-running spec-grag
    produces identical point ids for unchanged chunks → enables incremental
    upsert (overwrite-by-id without recreate_collection). Schema version
    `qdrant-bge-m3-hybrid-v2-stable-ids` reflects this id format.
    """

    return str(uuid.uuid5(QDRANT_POINT_ID_NAMESPACE, str(stable_chunk_uid)))


def compute_chunk_diff(
    previous_chunks: Sequence[Mapping[str, Any]] | None,
    current_chunks: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Diff two chunk lists by stable_chunk_uid + chunk_hash.

    Returns:
        {
            "added":   chunks present in current but not in previous,
            "changed": chunks whose stable_chunk_uid is in previous but
                       chunk_hash differs,
            "unchanged": chunks identical in both,
            "removed_uids": stable_chunk_uids only in previous,
        }
    """

    prev_by_uid: dict[str, dict[str, Any]] = {}
    if previous_chunks:
        for chunk in previous_chunks:
            prev_payload = _coerce_chunk_payload(chunk)
            uid = prev_payload.get("stable_chunk_uid", "")
            if uid:
                prev_by_uid[uid] = prev_payload
    added: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    seen_uids: set[str] = set()
    for chunk in current_chunks:
        payload = _coerce_chunk_payload(chunk)
        uid = payload.get("stable_chunk_uid", "")
        if not uid:
            continue
        seen_uids.add(uid)
        prev = prev_by_uid.get(uid)
        if prev is None:
            added.append(payload)
            continue
        if prev.get("chunk_hash") != payload.get("chunk_hash"):
            changed.append(payload)
        else:
            unchanged.append(payload)
    removed_uids = [uid for uid in prev_by_uid if uid not in seen_uids]
    return {
        "added": added,
        "changed": changed,
        "unchanged": unchanged,
        "removed_uids": removed_uids,
    }


def upsert_qdrant_bge_m3_index_incremental(
    *,
    url: str,
    collection: str,
    chunks_to_embed: Sequence[Mapping[str, Any]],
    point_ids_to_delete: Sequence[str],
    all_chunks: Sequence[Mapping[str, Any]],
    embedding_provider: BgeM3EmbeddingProvider | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Embed only changed/added chunks, delete removed chunks. No recreate.

    `all_chunks` is the full current chunk set (used for artifact_revision /
    chunk_count metadata). `chunks_to_embed` and `point_ids_to_delete` are the
    diff produced by ``compute_chunk_diff``.
    """

    from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    from qdrant_client import models as qdrant_models  # type: ignore[import-not-found]

    client = QdrantClient(url)
    server_version = _qdrant_server_version(client)

    # Delete removed points first (before upsert so id reuse is unambiguous).
    if point_ids_to_delete:
        client.delete(
            collection_name=collection,
            points_selector=qdrant_models.PointIdsList(
                points=[
                    stable_chunk_uid_to_point_id(uid) for uid in point_ids_to_delete
                ],
            ),
        )

    # Embed and upsert only the chunks that actually changed.
    embed_payloads = [_coerce_chunk_payload(chunk) for chunk in chunks_to_embed]
    if embed_payloads:
        provider = embedding_provider or FlagEmbeddingBgeM3Provider(
            allow_real_provider=True,
            use_fp16=False,
        )
        batch = provider.embed_documents([payload["text"] for payload in embed_payloads])
        points = []
        for payload, embedding in zip(embed_payloads, batch.embeddings, strict=True):
            sparse = embedding.sparse or SparseVector()
            points.append(
                qdrant_models.PointStruct(
                    id=stable_chunk_uid_to_point_id(payload["stable_chunk_uid"]),
                    vector={
                        DENSE_VECTOR_NAME: [float(value) for value in (embedding.dense or [])],
                        SPARSE_VECTOR_NAME: qdrant_models.SparseVector(
                            indices=list(sparse.indices),
                            values=[float(value) for value in sparse.values],
                        ),
                    },
                    payload=payload,
                )
            )
        if points:
            client.upsert(collection_name=collection, points=points)
    else:
        provider = embedding_provider  # not used for diagnostics if no embed

    full_payloads = [_coerce_chunk_payload(chunk) for chunk in all_chunks]
    revision = _artifact_revision_from_chunks(
        full_payloads,
        schema=qdrant_named_vector_schema_metadata(
            collection=collection,
            qdrant_server_version=server_version,
        ),
    )
    artifact = build_retrieval_index_revision_artifact(
        chunks=full_payloads,
        artifact_revision=revision,
        collection=collection,
        qdrant_server_version=server_version,
        qdrant_collection_revision=revision,
        generated_at=generated_at,
    )
    artifact["status"] = "success"
    artifact["diagnostics"] = {
        "real_retrieval_index": True,
        "qdrant_url": url,
        "collection": collection,
        "qdrant_server_version": server_version,
        "embedding_model": STANDARD_EMBEDDING_MODEL,
        "embedding_provider": STANDARD_EMBEDDING_PROVIDER,
        "flagembedding_package_version": _package_version("FlagEmbedding"),
        "embedding_device": (
            _provider_device(provider) if provider is not None else "skipped"
        ),
        "embedding_model_revision": "unknown",
        "dense_vector": DENSE_VECTOR_NAME,
        "sparse_vector": SPARSE_VECTOR_NAME,
        "fusion_method": FUSION_METHOD,
        "rrf_k": DEFAULT_RRF_K,
        "chunk_count": len(full_payloads),
        "upsert_mode": "incremental",
        "embedded_chunk_count": len(embed_payloads),
        "deleted_chunk_count": len(point_ids_to_delete),
    }
    return artifact


def build_section_embedding_text(
    section: Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
    *,
    max_search_keys: int = 8,
    max_identifiers: int = 8,
) -> str:
    """Build the embedding text for one section (summary + heading + key terms).

    Used by Phase B (section-level Qdrant collection). The text is intentionally
    short and semantically dense so 1 section = 1 BGE-M3 vector fits the model
    input length.
    """

    metadata = metadata or {}
    heading_path = section.get("heading_path") or []
    heading = " / ".join(str(part) for part in heading_path if part)
    summary = str(metadata.get("summary") or "")
    search_keys = list(metadata.get("search_keys") or [])[:max_search_keys]
    identifiers = list(metadata.get("identifiers") or [])[:max_identifiers]
    parts: list[str] = []
    if heading:
        parts.append(heading)
    if summary:
        parts.append(summary)
    if search_keys:
        parts.append(" ".join(str(key) for key in search_keys))
    if identifiers:
        parts.append(" ".join(str(item) for item in identifiers))
    return " | ".join(parts)


def build_section_payloads(
    sections: Sequence[Mapping[str, Any]],
    metadata_by_section_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return one Qdrant payload per section for the section-level collection.

    Per Phase R-3 (`doc/STORAGE_REDESIGN.ja.md` §7.4) the payload now also
    includes `related_sections`. When the related_sections stage has not
    run yet (e.g. the initial section_metadata upsert), the metadata input
    has no `related_sections` key and the payload defaults to an empty
    list; the related_sections stage then refreshes the field via
    `update_section_collection_related_sections` (`set_payload`) without a
    re-embed.
    """

    metadata_by_section_id = metadata_by_section_id or {}
    payloads: list[dict[str, Any]] = []
    for section in sections:
        section_id = str(section.get("source_section_id") or section.get("section_id") or "")
        if not section_id:
            continue
        metadata = metadata_by_section_id.get(section_id, {})
        text = build_section_embedding_text(section, metadata)
        stable_section_uid = str(section.get("stable_section_uid", section_id))
        payloads.append(
            {
                "source_document_id": str(section.get("source_document_id", "")),
                "source_section_id": section_id,
                "stable_section_uid": stable_section_uid,
                "stable_chunk_uid": stable_section_uid,
                "heading_path": _heading_path_list(section.get("heading_path", [])),
                "source_hash": str(section.get("source_hash", "")),
                "semantic_hash": str(section.get("semantic_hash", section.get("source_hash", ""))),
                "summary": str(metadata.get("summary") or ""),
                "search_keys": list(metadata.get("search_keys") or []),
                "identifiers": list(metadata.get("identifiers") or []),
                "related_sections": list(metadata.get("related_sections") or []),
                "text": text,
            }
        )
    return payloads


def update_section_collection_related_sections(
    related_sections_by_id: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    url: str = "http://localhost:6333",
    collection: str = DEFAULT_SECTION_COLLECTION,
    client: Any | None = None,
) -> dict[str, Any]:
    """Patch the `related_sections` payload field in `spec_grag_section`.

    Phase R-3 (`doc/STORAGE_REDESIGN.ja.md` §7.4) routes the related_sections
    LLM typing output back to the Qdrant section collection via
    `client.set_payload` so the `inject-search` API (Phase R-6) can return
    related_sections in the same call as the section content.

    `related_sections_by_id` maps `source_section_id` to the related-section
    list (the same dicts found in section_metadata.json). The function
    issues one `set_payload` call per section using a
    `source_section_id` filter, so the existing point IDs (assigned by
    `upsert_qdrant_section_collection`) do not need to be tracked by
    callers.

    Returns a small diagnostics dict that includes the number of sections
    successfully patched and the list of section_ids that produced an
    error (each error is logged into `errors` instead of raising).
    """

    from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    from qdrant_client import models as qdrant_models  # type: ignore[import-not-found]

    if not related_sections_by_id:
        return {
            "status": "success",
            "section_count": 0,
            "errors": [],
            "collection": collection,
        }

    qdrant = client if client is not None else QdrantClient(url)
    patched = 0
    errors: list[dict[str, Any]] = []
    for section_id, related in related_sections_by_id.items():
        section_id_str = str(section_id)
        if not section_id_str:
            continue
        payload_patch = {"related_sections": [dict(item) for item in related]}
        selector = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="source_section_id",
                    match=qdrant_models.MatchValue(value=section_id_str),
                )
            ]
        )
        try:
            qdrant.set_payload(
                collection_name=collection,
                payload=payload_patch,
                points=selector,
            )
            patched += 1
        except Exception as exc:  # pragma: no cover - exercised via integration
            errors.append(
                {
                    "section_id": section_id_str,
                    "reason_code": "set_payload_failed",
                    "message": str(exc),
                }
            )
    return {
        "status": "success" if not errors else "degraded",
        "section_count": patched,
        "errors": errors,
        "collection": collection,
    }


def build_section_embeddings_artifact(
    sections: Sequence[Mapping[str, Any]],
    metadata_by_section_id: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    collection: str = DEFAULT_SECTION_COLLECTION,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the section_embeddings artifact (provider-free metadata)."""

    payloads = build_section_payloads(sections, metadata_by_section_id)
    revision = _hash_text(
        "\n".join(
            f"{payload['source_section_id']}:{payload['source_hash']}:{payload.get('semantic_hash', '')}"
            for payload in payloads
        )
    )[:16]
    return {
        "artifact_version": SECTION_EMBEDDINGS_ARTIFACT_VERSION,
        "artifact_revision": revision,
        "collection": collection,
        "embedding": {
            "provider": STANDARD_EMBEDDING_PROVIDER,
            "model": STANDARD_EMBEDDING_MODEL,
            "dense_vector_size": BGE_M3_DENSE_SIZE,
            "dense_distance": DENSE_DISTANCE,
            "sparse_vector_kind": SPARSE_VECTOR_KIND,
        },
        "section_count": len(payloads),
        "sections": payloads,
        "generated_at": generated_at,
    }


def upsert_qdrant_section_collection(
    sections: Sequence[Mapping[str, Any]],
    metadata_by_section_id: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    url: str = "http://localhost:6333",
    collection: str = DEFAULT_SECTION_COLLECTION,
    embedding_provider: BgeM3EmbeddingProvider | None = None,
    recreate: bool = True,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Upsert one BGE-M3 dense+sparse vector per section into a Qdrant collection."""

    from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    from qdrant_client import models as qdrant_models  # type: ignore[import-not-found]

    payloads = build_section_payloads(sections, metadata_by_section_id)
    client = QdrantClient(url)
    server_version = _qdrant_server_version(client)
    provider = embedding_provider or FlagEmbeddingBgeM3Provider(
        allow_real_provider=True,
        use_fp16=False,
    )
    batch = provider.embed_documents([payload["text"] for payload in payloads])

    if recreate:
        client.recreate_collection(
            collection_name=collection,
            vectors_config={
                DENSE_VECTOR_NAME: qdrant_models.VectorParams(
                    size=BGE_M3_DENSE_SIZE,
                    distance=qdrant_models.Distance.COSINE,
                )
            },
            sparse_vectors_config={SPARSE_VECTOR_NAME: qdrant_models.SparseVectorParams()},
        )

    points = []
    for index, (payload, embedding) in enumerate(zip(payloads, batch.embeddings, strict=True)):
        sparse = embedding.sparse or SparseVector()
        points.append(
            qdrant_models.PointStruct(
                id=index,
                vector={
                    DENSE_VECTOR_NAME: [float(value) for value in (embedding.dense or [])],
                    SPARSE_VECTOR_NAME: qdrant_models.SparseVector(
                        indices=list(sparse.indices),
                        values=[float(value) for value in sparse.values],
                    ),
                },
                payload=payload,
            )
        )
    if points:
        client.upsert(collection_name=collection, points=points)

    artifact = build_section_embeddings_artifact(
        sections,
        metadata_by_section_id,
        collection=collection,
        generated_at=generated_at,
    )
    artifact["status"] = "success"
    artifact["diagnostics"] = {
        "real_section_index": True,
        "qdrant_url": url,
        "collection": collection,
        "qdrant_server_version": server_version,
        "section_count": len(payloads),
        "embedding_provider": STANDARD_EMBEDDING_PROVIDER,
        "embedding_model": STANDARD_EMBEDDING_MODEL,
        "embedding_device": _provider_device(provider),
    }
    return artifact


def section_hybrid_candidates(
    source_section_id: str,
    payloads: Sequence[Mapping[str, Any]],
    *,
    embedding_provider: BgeM3EmbeddingProvider | None = None,
    dense_top_k: int = 12,
    sparse_top_k: int = 20,
    limit: int = 16,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[FusedRetrievalHit]:
    """Return top-N section candidates for one source section via in-process RRF.

    Used by Phase C candidate generation when running without a live Qdrant.
    The same provider-free path is exercised by unit tests; the real Qdrant
    backed query lives in :class:`QdrantHybridRetriever` against the section
    collection.
    """

    chunks = list(payloads)
    if not chunks:
        return []
    source_text = ""
    for payload in chunks:
        if str(payload.get("source_section_id", "")) == source_section_id:
            source_text = str(payload.get("text", ""))
            break
    if not source_text.strip():
        return []
    retriever = InMemoryHybridRetriever(
        chunks,
        embedding_provider=embedding_provider,
        rrf_k=rrf_k,
    )
    result = retriever.search(
        source_text,
        dense_top_k=dense_top_k,
        sparse_top_k=sparse_top_k,
        limit=limit + 1,
        fusion_owner="related_sections_section_hybrid",
    )
    return [hit for hit in result.hits if hit.source_section_id != source_section_id][:limit]


def rrf_fusion(
    dense_hits: Sequence[Any],
    sparse_hits: Sequence[Any],
    *,
    rrf_k: int = DEFAULT_RRF_K,
    fusion_owner: str = "cli",
    limit: int | None = None,
) -> RetrievalFusionResult:
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")

    dense = _stable_channel_order([_coerce_hit(hit) for hit in dense_hits])
    sparse = _stable_channel_order([_coerce_hit(hit) for hit in sparse_hits])
    by_chunk: dict[str, dict[str, Any]] = {}

    for rank, hit in enumerate(dense, start=1):
        entry = by_chunk.setdefault(hit.stable_chunk_uid, {"payload": hit.payload})
        entry["payload"] = _prefer_payload(entry.get("payload"), hit.payload)
        entry["dense_rank"] = min(rank, entry.get("dense_rank", rank))
        entry["dense_score"] = hit.score
        entry["rrf_score"] = entry.get("rrf_score", 0.0) + 1.0 / (rrf_k + rank)

    for rank, hit in enumerate(sparse, start=1):
        entry = by_chunk.setdefault(hit.stable_chunk_uid, {"payload": hit.payload})
        entry["payload"] = _prefer_payload(entry.get("payload"), hit.payload)
        entry["sparse_rank"] = min(rank, entry.get("sparse_rank", rank))
        entry["sparse_score"] = hit.score
        entry["rrf_score"] = entry.get("rrf_score", 0.0) + 1.0 / (rrf_k + rank)

    ordered_entries = sorted(
        by_chunk.items(),
        key=lambda item: (
            -float(item[1].get("rrf_score", 0.0)),
            str(item[1].get("payload", {}).get("source_section_id", "")),
            str(item[0]),
        ),
    )
    if limit is not None:
        ordered_entries = ordered_entries[:limit]

    hits = [
        FusedRetrievalHit(
            stable_chunk_uid=stable_chunk_uid,
            score=float(entry.get("rrf_score", 0.0)),
            payload=dict(entry.get("payload", {})),
            rank=rank,
            dense_rank=entry.get("dense_rank"),
            dense_score=entry.get("dense_score"),
            sparse_rank=entry.get("sparse_rank"),
            sparse_score=entry.get("sparse_score"),
        )
        for rank, (stable_chunk_uid, entry) in enumerate(ordered_entries, start=1)
    ]
    diagnostics = _fusion_diagnostics(
        dense,
        sparse,
        hits,
        rrf_k=rrf_k,
        fusion_owner=fusion_owner,
    )
    return RetrievalFusionResult(hits=hits, diagnostics=diagnostics)


def hybrid_retrieve(
    query: str,
    *,
    backend: Any,
    dense_top_k: int = 12,
    sparse_top_k: int = 20,
    dense_enabled: bool = True,
    sparse_enabled: bool = True,
    rrf_k: int = DEFAULT_RRF_K,
    fusion_owner: str = "cli",
    limit: int | None = None,
) -> RetrievalFusionResult:
    """Run one caller-directed hybrid retrieval against an injected backend."""

    if not query.strip():
        return RetrievalFusionResult(
            hits=[],
            diagnostics=_empty_fusion_diagnostics(fusion_owner=fusion_owner),
        )

    dense_hits: Sequence[Any] = []
    sparse_hits: Sequence[Any] = []
    if dense_enabled:
        dense_hits = _call_backend_search(
            backend,
            ("dense_search", "search_dense"),
            query=query,
            top_k=dense_top_k,
        )
    if sparse_enabled:
        sparse_hits = _call_backend_search(
            backend,
            ("sparse_search", "search_sparse"),
            query=query,
            top_k=sparse_top_k,
        )

    return rrf_fusion(
        dense_hits,
        sparse_hits,
        rrf_k=rrf_k,
        fusion_owner=fusion_owner,
        limit=limit,
    )


retrieve_hybrid = hybrid_retrieve


def qdrant_hybrid_retrieve(
    query: str,
    *,
    url: str = "http://localhost:6333",
    collection: str = "spec_grag_source",
    embedding_provider: BgeM3EmbeddingProvider | None = None,
    dense_top_k: int = 12,
    sparse_top_k: int = 20,
    limit: int | None = None,
) -> HybridRetrievalResult:
    retriever = QdrantHybridRetriever(
        url=url,
        collection=collection,
        embedding_provider=embedding_provider,
    )
    return retriever.search(
        query,
        dense_top_k=dense_top_k,
        sparse_top_k=sparse_top_k,
        limit=limit,
    )


retrieve_qdrant_hybrid = qdrant_hybrid_retrieve


def build_retrieval_index_revision_artifact(
    *,
    chunks: Sequence[SourceChunk | Mapping[str, Any]] | None = None,
    artifact_revision: str | None = None,
    collection: str | None = None,
    qdrant_server_version: str | None = None,
    qdrant_collection_revision: str | None = None,
    flagembedding_package_version: str | None = None,
    embedding_model_revision: str | None = None,
    dense_enabled: bool = True,
    sparse_enabled: bool = True,
    generated_at: str | None = None,
    qdrant_collection_schema_version: str | int | None = None,
) -> dict[str, Any]:
    payloads = [_coerce_chunk_payload(chunk) for chunk in chunks or []]
    schema = qdrant_named_vector_schema_metadata(
        collection=collection,
        qdrant_server_version=qdrant_server_version,
        flagembedding_package_version=flagembedding_package_version,
        embedding_model_revision=embedding_model_revision,
    )
    revision = artifact_revision or _artifact_revision_from_chunks(payloads, schema=schema)
    collection_schema_version = (
        qdrant_collection_schema_version or QDRANT_COLLECTION_SCHEMA_VERSION
    )
    return {
        "artifact_version": RETRIEVAL_INDEX_REVISION_ARTIFACT_VERSION,
        "artifact_revision": revision,
        "generated_at": generated_at,
        "retrieval_stack": {
            "vector_store": STANDARD_VECTOR_STORE_PROVIDER,
            "embedding_provider": STANDARD_EMBEDDING_PROVIDER,
            "embedding_model": STANDARD_EMBEDDING_MODEL,
            "fusion_method": FUSION_METHOD,
        },
        "embedding": {
            "provider": STANDARD_EMBEDDING_PROVIDER,
            "model": STANDARD_EMBEDDING_MODEL,
            "model_revision": embedding_model_revision or "unknown",
            "dense_enabled": bool(dense_enabled),
            "sparse_enabled": bool(sparse_enabled),
            "dense_vector_size": BGE_M3_DENSE_SIZE,
            "dense_distance": DENSE_DISTANCE,
            "sparse_vector_kind": SPARSE_VECTOR_KIND,
            "flagembedding_package_version": schema["flagembedding_package_version"],
        },
        "vector_store": {
            "provider": STANDARD_VECTOR_STORE_PROVIDER,
            "collection": collection,
            "collection_revision": qdrant_collection_revision or revision,
            "server_version": schema["qdrant_server_version"],
            "qdrant_server_version": schema["qdrant_server_version"],
            "collection_schema_version": collection_schema_version,
            "qdrant_collection_schema_version": collection_schema_version,
        },
        "qdrant": schema,
        "qdrant_collection_schema_version": collection_schema_version,
        "flagembedding_package_version": schema["flagembedding_package_version"],
        "packages": {
            "FlagEmbedding": schema["flagembedding_package_version"],
        },
        "embedding_model": STANDARD_EMBEDDING_MODEL,
        "dense_vector": {
            "name": DENSE_VECTOR_NAME,
            "size": BGE_M3_DENSE_SIZE,
            "distance": DENSE_DISTANCE,
        },
        "dense_vector_size": BGE_M3_DENSE_SIZE,
        "dense_distance": DENSE_DISTANCE,
        "sparse_vector": {
            "name": SPARSE_VECTOR_NAME,
            "kind": SPARSE_VECTOR_KIND,
        },
        "sparse_vector_kind": SPARSE_VECTOR_KIND,
        "named_vectors": {
            "dense": DENSE_VECTOR_NAME,
            "sparse": SPARSE_VECTOR_NAME,
        },
        "fusion": {
            "method": FUSION_METHOD,
            "rrf_k": DEFAULT_RRF_K,
            "tie_break": ["source_section_id", "stable_chunk_uid"],
        },
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
        "chunk_count": len(payloads),
    }


def build_retrieval_index_revision(**kwargs: Any) -> dict[str, Any]:
    return build_retrieval_index_revision_artifact(**kwargs)


def build_retrieval_index_revision_payload(**kwargs: Any) -> dict[str, Any]:
    return build_retrieval_index_revision_artifact(**kwargs)


def build_retrieval_artifacts(
    sections: Sequence[Any],
    *,
    retrieval_config: Any | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    artifact_revision: str | None = None,
    collection: str | None = None,
    generated_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    chunks = build_source_chunks(
        sections,
        retrieval_config=retrieval_config,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        artifact_revision=artifact_revision,
    )
    revision = artifact_revision or (chunks[0].artifact_revision if chunks else _hash_text(""))
    return {
        "source_chunks": build_source_chunks_artifact(
            chunks,
            chunk_size=_config_value(retrieval_config, "chunk_size", chunk_size),
            chunk_overlap=_config_value(retrieval_config, "chunk_overlap", chunk_overlap),
            artifact_revision=revision,
        ),
        "retrieval_index_revision": build_retrieval_index_revision_artifact(
            chunks=chunks,
            artifact_revision=revision,
            collection=collection,
            generated_at=generated_at,
        ),
    }


def source_snippet_from_payload(payload: Mapping[str, Any]) -> str:
    return str(payload.get("text", ""))


def get_source_snippet(
    chunks: Sequence[SourceChunk | Mapping[str, Any]],
    *,
    stable_chunk_uid: str | None = None,
    source_span: Mapping[str, Any] | None = None,
    source_document_id: str | None = None,
) -> str | None:
    target_span = dict(source_span or {})
    for chunk in chunks:
        payload = _coerce_chunk_payload(chunk)
        if stable_chunk_uid and payload.get("stable_chunk_uid") != stable_chunk_uid:
            continue
        if source_document_id and payload.get("source_document_id") != source_document_id:
            continue
        if target_span and dict(payload.get("source_span") or {}) != target_span:
            continue
        return str(payload.get("text", ""))
    return None


# Friendly aliases for tests and callers using slightly different wording.
normalize_bge_m3_sparse = normalize_bge_m3_sparse_output
normalize_sparse_vector = normalize_bge_m3_sparse_output
build_qdrant_schema_metadata = qdrant_named_vector_schema_metadata
build_qdrant_named_vector_schema_metadata = qdrant_named_vector_schema_metadata
fuse_rrf = rrf_fusion
rrf_fuse = rrf_fusion
FakeRetrievalIndex = InMemoryHybridRetriever


def _embeddings_from_bge_m3_output(
    output: Mapping[str, Any],
    expected_count: int,
    *,
    dense_enabled: bool,
    sparse_enabled: bool,
) -> list[BgeM3Embedding]:
    dense_batch = _dense_batch(output.get("dense_vecs"), expected_count) if dense_enabled else []
    sparse_batch = normalize_bge_m3_sparse_batch(output, expected_count=expected_count) if sparse_enabled else []
    embeddings: list[BgeM3Embedding] = []
    for index in range(expected_count):
        dense = dense_batch[index] if index < len(dense_batch) else None
        sparse = sparse_batch[index] if index < len(sparse_batch) else None
        embeddings.append(BgeM3Embedding(dense=dense, sparse=sparse))
    return embeddings


def _dense_batch(value: Any, expected_count: int) -> list[list[float] | None]:
    if value is None:
        return [None for _ in range(expected_count)]
    rows = value.tolist() if hasattr(value, "tolist") else value
    if expected_count == 1 and rows and all(isinstance(item, (int, float)) for item in rows):
        return [[float(item) for item in rows]]
    dense: list[list[float] | None] = []
    for row in list(rows)[:expected_count]:
        if row is None:
            dense.append(None)
        else:
            items = row.tolist() if hasattr(row, "tolist") else row
            dense.append([float(item) for item in items])
    while len(dense) < expected_count:
        dense.append(None)
    return dense


def _real_smoke_enabled() -> bool:
    return os.environ.get("SPEC_GRAG_REAL_SMOKE", "").lower() in _TRUE_VALUES


def _real_retrieval_provider_enabled() -> bool:
    return (
        os.environ.get("SPEC_GRAG_REAL_RETRIEVAL", "").lower() in _TRUE_VALUES
        or _real_smoke_enabled()
    )


def _coerce_chunk_payload(chunk: SourceChunk | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(chunk, SourceChunk):
        return chunk.to_payload()
    if is_dataclass(chunk):
        return _coerce_chunk_payload(asdict(chunk))
    if isinstance(chunk, Mapping):
        if "payload" in chunk and isinstance(chunk["payload"], Mapping):
            return _coerce_chunk_payload(chunk["payload"])
        return {
            "source_document_id": str(chunk.get("source_document_id", "")),
            "source_section_id": str(
                chunk.get("source_section_id", chunk.get("section_id", ""))
            ),
            "stable_section_uid": str(chunk.get("stable_section_uid", "")),
            "stable_chunk_uid": str(chunk.get("stable_chunk_uid", chunk.get("id", ""))),
            "heading_path": _heading_path_list(chunk.get("heading_path", [])),
            "source_span": _source_span_dict(chunk.get("source_span", {})),
            "source_hash": str(chunk.get("source_hash", "")),
            "chunk_hash": str(chunk.get("chunk_hash", "")),
            "text": str(chunk.get("text", chunk.get("body", ""))),
            "artifact_revision": str(chunk.get("artifact_revision", "")),
        }
    raise TypeError(f"unsupported chunk payload: {type(chunk)!r}")


def _normalize_section(section: Any) -> dict[str, Any]:
    source_section_id = str(
        _field(section, "source_section_id", _field(section, "section_id", ""))
    )
    text = str(_field(section, "text", _field(section, "body", "")))
    return {
        "source_document_id": str(_field(section, "source_document_id", "")),
        "source_section_id": source_section_id,
        "stable_section_uid": str(_field(section, "stable_section_uid", "")),
        "heading_path": _heading_path_list(_field(section, "heading_path", [])),
        "source_span": _source_span_dict(_field(section, "source_span", {})),
        "source_hash": str(_field(section, "source_hash", _hash_text(text))),
        "text": text,
    }


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _heading_path_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split("/") if part.strip()]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    return []


def _source_span_dict(value: Any) -> dict[str, int]:
    if isinstance(value, Mapping):
        return {
            "start_line": int(value.get("start_line", 1)),
            "end_line": int(value.get("end_line", value.get("start_line", 1))),
            "start_offset": int(value.get("start_offset", 0)),
            "end_offset": int(value.get("end_offset", value.get("start_offset", 0))),
        }
    return {
        "start_line": int(getattr(value, "start_line", 1)),
        "end_line": int(getattr(value, "end_line", getattr(value, "start_line", 1))),
        "start_offset": int(getattr(value, "start_offset", 0)),
        "end_offset": int(getattr(value, "end_offset", getattr(value, "start_offset", 0))),
    }


def _chunk_ranges(text: str, *, chunk_size: int, chunk_overlap: int) -> list[tuple[int, int]]:
    if text == "":
        return [(0, 0)]
    ranges: list[tuple[int, int]] = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(text_len, start + chunk_size)
        ranges.append((start, end))
        if end >= text_len:
            break
        start = max(end - chunk_overlap, start + 1)
    return ranges


def _chunk_source_span(
    section_span: Mapping[str, int],
    section_text: str,
    start: int,
    end: int,
) -> dict[str, int]:
    base_line = int(section_span.get("start_line", 1))
    start_line = base_line + section_text.count("\n", 0, start)
    if end <= start:
        end_line = start_line
    else:
        end_line = base_line + section_text.count("\n", 0, max(end - 1, 0))
    start_offset = int(section_span.get("start_offset", 0)) + start
    return {
        "start_line": start_line,
        "end_line": end_line,
        "start_offset": start_offset,
        "end_offset": int(section_span.get("start_offset", 0)) + end,
    }


def _stable_chunk_uid(stable_section_uid: str, ordinal: int) -> str:
    return _hash_text(f"{stable_section_uid}\n{ordinal:04d}")[:16]


def _artifact_revision_from_sections(sections: Sequence[Mapping[str, Any]]) -> str:
    seed = "\n".join(
        f"{section.get('source_section_id')}:{section.get('source_hash')}"
        for section in sections
    )
    return _hash_text(seed)[:16]


def _artifact_revision_from_chunks(
    chunks: Sequence[Mapping[str, Any]],
    *,
    schema: Mapping[str, Any] | None = None,
) -> str:
    parts = [
        f"{chunk.get('stable_chunk_uid')}:{chunk.get('chunk_hash')}"
        for chunk in chunks
    ]
    if schema:
        parts.append(repr(sorted(schema.items())))
    return _hash_text("\n".join(parts))[:16]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sparse_batch_length(output: Any) -> int:
    if isinstance(output, Mapping):
        if "lexical_weights" in output:
            return _sparse_batch_length(output.get("lexical_weights"))
        if "sparse_vecs" in output:
            return _sparse_batch_length(output.get("sparse_vecs"))
        return 1
    shape = getattr(output, "shape", None)
    if shape and len(shape) >= 1:
        return int(shape[0])
    if isinstance(output, Sequence) and not isinstance(output, (str, bytes, bytearray)):
        if not output:
            return 1
        return len(output)
    return 1


def _looks_like_lexical_weight_dict(value: Mapping[Any, Any]) -> bool:
    if not value:
        return True
    return all(_int_or_none(key) is not None for key in value.keys())


def _looks_like_pair(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and len(value) == 2
    )


def _sparse_from_parallel(indices: Any, values: Any) -> SparseVector:
    return _sparse_from_pairs(zip(indices, values, strict=False))


def _sparse_from_pairs(pairs: Any) -> SparseVector:
    summed: dict[int, float] = {}
    for index_value, sparse_value in pairs:
        index = _int_or_none(index_value)
        value = _float_or_none(sparse_value)
        if index is None or value is None or value == 0:
            continue
        summed[index] = summed.get(index, 0.0) + value
    ordered = sorted(
        (index, value)
        for index, value in summed.items()
        if math.isfinite(value) and value != 0
    )
    return SparseVector(
        indices=[index for index, _value in ordered],
        values=[float(value) for _index, value in ordered],
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _fake_dense_vector(text: str, dimension: int) -> list[float]:
    vector = [0.0 for _ in range(dimension)]
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _fake_sparse_vector(text: str) -> SparseVector:
    weights: dict[int, float] = {}
    for token in _tokens(text):
        token_id = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big")
        weights[token_id] = weights.get(token_id, 0.0) + 1.0
    return _sparse_from_pairs(weights.items())


def _tokens(text: str) -> list[str]:
    normalized = text.lower().replace("　", " ")
    tokens = [match.group(0) for match in _TOKEN_RE.finditer(normalized)]
    for match in re.finditer(r"[一-龯ぁ-んァ-ンー]{3,}", normalized):
        value = match.group(0)
        tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
    return tokens


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right, strict=False):
        dot += float(a) * float(b)
        left_norm += float(a) * float(a)
        right_norm += float(b) * float(b)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / math.sqrt(left_norm * right_norm)


def _sparse_dot(left: SparseVector, right: SparseVector) -> float:
    right_by_index = dict(zip(right.indices, right.values, strict=False))
    return sum(
        value * right_by_index.get(index, 0.0)
        for index, value in zip(left.indices, left.values, strict=False)
    )


def _top_hits(hits: Sequence[RetrievalHit], limit: int) -> list[RetrievalHit]:
    if limit <= 0:
        return []
    return sorted(
        hits,
        key=lambda hit: (-hit.score, hit.source_section_id, hit.stable_chunk_uid),
    )[:limit]


def _stable_channel_order(hits: Sequence[RetrievalHit]) -> list[RetrievalHit]:
    return sorted(
        hits,
        key=lambda hit: (-hit.score, hit.source_section_id, hit.stable_chunk_uid),
    )


def _call_backend_search(
    backend: Any,
    method_names: Sequence[str],
    *,
    query: str,
    top_k: int,
) -> Sequence[Any]:
    for method_name in method_names:
        method = getattr(backend, method_name, None)
        if callable(method):
            return method(query, top_k)
    raise TypeError(f"backend must expose one of: {', '.join(method_names)}")


def _hit_from_payload(payload: Mapping[str, Any], *, score: float) -> RetrievalHit:
    stable_chunk_uid = str(payload.get("stable_chunk_uid", payload.get("id", "")))
    return RetrievalHit(
        stable_chunk_uid=stable_chunk_uid,
        score=float(score),
        payload=dict(payload),
        point_id=payload.get("id"),
    )


def _hit_from_qdrant_point(point: Any) -> RetrievalHit:
    payload = dict(getattr(point, "payload", None) or {})
    stable_chunk_uid = str(
        payload.get("stable_chunk_uid")
        or payload.get("chunk_id")
        or getattr(point, "id", "")
    )
    return RetrievalHit(
        stable_chunk_uid=stable_chunk_uid,
        score=float(getattr(point, "score", 0.0) or 0.0),
        payload=payload,
        point_id=getattr(point, "id", None),
    )


def _coerce_hit(hit: Any) -> RetrievalHit:
    if isinstance(hit, RetrievalHit):
        return hit
    if isinstance(hit, FusedRetrievalHit):
        return RetrievalHit(
            stable_chunk_uid=hit.stable_chunk_uid,
            score=hit.score,
            payload=hit.payload,
        )
    if isinstance(hit, SourceChunk):
        return _hit_from_payload(hit.to_payload(), score=0.0)
    if is_dataclass(hit):
        return _coerce_hit(asdict(hit))
    if isinstance(hit, Mapping):
        payload_value = hit.get("payload")
        payload = dict(payload_value) if isinstance(payload_value, Mapping) else dict(hit)
        stable_chunk_uid = str(
            hit.get(
                "stable_chunk_uid",
                payload.get("stable_chunk_uid", hit.get("id", "")),
            )
        )
        return RetrievalHit(
            stable_chunk_uid=stable_chunk_uid,
            score=float(hit.get("score", hit.get("rrf_score", 0.0)) or 0.0),
            payload=payload,
            point_id=hit.get("id"),
        )
    if isinstance(hit, tuple) and len(hit) >= 2:
        key = str(hit[0])
        score = float(hit[1])
        payload = {"stable_chunk_uid": key}
        if len(hit) >= 3 and isinstance(hit[2], Mapping):
            payload.update(hit[2])
        payload.setdefault("stable_chunk_uid", key)
        return RetrievalHit(stable_chunk_uid=key, score=score, payload=payload)
    raise TypeError(f"unsupported retrieval hit: {type(hit)!r}")


def _prefer_payload(current: Any, candidate: Mapping[str, Any]) -> dict[str, Any]:
    current_payload = dict(current or {})
    candidate_payload = dict(candidate or {})
    if len(candidate_payload) > len(current_payload):
        return candidate_payload
    if not current_payload.get("text") and candidate_payload.get("text"):
        return candidate_payload
    return current_payload


def _fusion_diagnostics(
    dense_hits: Sequence[RetrievalHit],
    sparse_hits: Sequence[RetrievalHit],
    fused_hits: Sequence[FusedRetrievalHit],
    *,
    rrf_k: int,
    fusion_owner: str,
) -> dict[str, Any]:
    return {
        "fusion_owner": fusion_owner,
        "fusion_method": FUSION_METHOD,
        "rrf_k": rrf_k,
        "tie_break": ["source_section_id", "stable_chunk_uid"],
        "dense_ranking": [
            _channel_ranking_entry(hit, rank, rrf_k=rrf_k)
            for rank, hit in enumerate(dense_hits, start=1)
        ],
        "sparse_ranking": [
            _channel_ranking_entry(hit, rank, rrf_k=rrf_k)
            for rank, hit in enumerate(sparse_hits, start=1)
        ],
        "fused_ranking": [_fused_ranking_entry(hit) for hit in fused_hits],
        "tie_break_results": [
            {
                "rank": hit.rank,
                "source_section_id": hit.source_section_id,
                "stable_chunk_uid": hit.stable_chunk_uid,
                "tie_break_key": [hit.source_section_id, hit.stable_chunk_uid],
            }
            for hit in fused_hits
        ],
    }


def _empty_fusion_diagnostics(*, fusion_owner: str) -> dict[str, Any]:
    return _fusion_diagnostics([], [], [], rrf_k=DEFAULT_RRF_K, fusion_owner=fusion_owner)


def _channel_ranking_entry(hit: RetrievalHit, rank: int, *, rrf_k: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "stable_chunk_uid": hit.stable_chunk_uid,
        "source_section_id": hit.source_section_id,
        "score": hit.score,
        "rrf_contribution": 1.0 / (rrf_k + rank),
    }


def _fused_ranking_entry(hit: FusedRetrievalHit) -> dict[str, Any]:
    return {
        "rank": hit.rank,
        "stable_chunk_uid": hit.stable_chunk_uid,
        "source_section_id": hit.source_section_id,
        "rrf_score": hit.score,
        "dense_rank": hit.dense_rank,
        "dense_score": hit.dense_score,
        "sparse_rank": hit.sparse_rank,
        "sparse_score": hit.sparse_score,
    }


def _package_version(distribution_name: str) -> str:
    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _model_cache_dir() -> str:
    for name in ("HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE"):
        value = os.environ.get(name)
        if value:
            return value
    return str(Path.home() / ".cache" / "huggingface")


def _provider_device(provider: Any) -> str:
    model = getattr(provider, "_model", None)
    for source in (provider, model):
        value = getattr(source, "device", None)
        if value is not None:
            return str(value)
    return str(getattr(provider, "model_kwargs", {}).get("device") or "unknown")


def _provider_model_cache_dir(provider: Any) -> str:
    return str(getattr(provider, "model_cache_dir", None) or _model_cache_dir())


def _qdrant_server_version(client: Any) -> str:
    try:
        info = client.info()
    except Exception:
        return "unknown"
    if isinstance(info, Mapping):
        return str(info.get("version") or "unknown")
    return str(getattr(info, "version", None) or "unknown")


def _config_value(config: Any, field_name: str, default: Any = None) -> Any:
    if config is None:
        return default
    if isinstance(config, Mapping):
        return config.get(field_name, default)
    return getattr(config, field_name, default)
