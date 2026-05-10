"""Retrieval Index contract tests.

The fake tests in this module must not require Qdrant or FlagEmbedding.  The
real provider roundtrip is marked external and can be skipped with
`pytest --skip-external`.
"""

from __future__ import annotations

import importlib
import os
import sys
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _retrieval_module() -> Any:
    return importlib.import_module("spec_grag.retrieval_index")


def _callable(module: Any, *names: str) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail(f"spec_grag.retrieval_index must expose one of: {', '.join(names)}")


def _get(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if isinstance(current, Mapping):
            current = current[key]
        else:
            current = getattr(current, key)
    return current


def _maybe_get(value: Any, *path: str, default: Any = None) -> Any:
    try:
        return _get(value, *path)
    except (AttributeError, KeyError, TypeError):
        return default


def _indices(vector: Any) -> list[int]:
    return list(_get(vector, "indices"))


def _values(vector: Any) -> list[float]:
    return list(_get(vector, "values"))


def _hit_id(hit: Any) -> str:
    for key in ("id", "point_id", "stable_chunk_uid"):
        value = _maybe_get(hit, key)
        if value is not None:
            return str(value)
    payload = _maybe_get(hit, "payload", default={})
    return str(payload["stable_chunk_uid"])


def _hit_score(hit: Any) -> float:
    return float(_get(hit, "score"))


def _hit_payload(hit: Any) -> Mapping[str, Any]:
    payload = _maybe_get(hit, "payload", default=None)
    if payload is None:
        return hit if isinstance(hit, Mapping) else hit.__dict__
    return payload


def _unpack_result(result: Any) -> tuple[list[Any], Mapping[str, Any]]:
    if isinstance(result, tuple):
        hits, diagnostics = result
        return list(hits), diagnostics
    if isinstance(result, Mapping):
        hits = result.get("hits") or result.get("results") or result.get("items")
        assert hits is not None, "retrieval result mapping must include hits/results/items"
        diagnostics = result.get("diagnostics") or {}
        return list(hits), diagnostics
    hits = _get(result, "hits")
    diagnostics = _maybe_get(result, "diagnostics", default={})
    return list(hits), diagnostics


class _FakeCooMatrix:
    row = [0, 0, 1]
    col = [7, 11, 13]
    data = [0.7, 0.11, 0.13]


class _FakeSparseMatrix:
    shape = (2, 32)

    def tocoo(self) -> _FakeCooMatrix:
        return _FakeCooMatrix()


class _FakeSearchBackend:
    def __init__(self, dense_hits: list[Mapping[str, Any]], sparse_hits: list[Mapping[str, Any]]):
        self.dense_hits = dense_hits
        self.sparse_hits = sparse_hits
        self.calls: list[tuple[str, str, int]] = []

    def dense_search(self, query: str, top_k: int) -> list[Mapping[str, Any]]:
        self.calls.append(("dense", query, top_k))
        return self.dense_hits[:top_k]

    def sparse_search(self, query: str, top_k: int) -> list[Mapping[str, Any]]:
        self.calls.append(("sparse", query, top_k))
        return self.sparse_hits[:top_k]


def _hit(
    chunk_uid: str,
    source_section_id: str,
    score: float,
    text: str = "snippet",
) -> dict[str, Any]:
    return {
        "id": chunk_uid,
        "score": score,
        "payload": {
            "source_document_id": "docs/spec/main.md",
            "source_section_id": source_section_id,
            "stable_section_uid": f"sec-{source_section_id}",
            "stable_chunk_uid": chunk_uid,
            "heading_path": ["Spec", source_section_id],
            "source_span": {"start_line": 1, "end_line": 3},
            "source_hash": "sha256:source",
            "chunk_hash": f"sha256:{chunk_uid}",
            "artifact_revision": "rev-1",
            "text": text,
        },
    }


def _normalize_sparse(encoded: Mapping[str, Any]) -> list[Any]:
    module = _retrieval_module()
    normalize = _callable(
        module,
        "normalize_sparse_vectors",
        "normalize_bge_m3_sparse_output",
        "normalize_bge_m3_sparse_vectors",
    )
    vectors = normalize(encoded)
    return list(vectors)


def test_t_u12_sparse_vecs_matrix_like_output_is_normalized() -> None:
    vectors = _normalize_sparse({"sparse_vecs": _FakeSparseMatrix()})

    assert len(vectors) == 2
    assert _indices(vectors[0]) == [7, 11]
    assert _values(vectors[0]) == [0.7, 0.11]
    assert _indices(vectors[1]) == [13]
    assert _values(vectors[1]) == [0.13]


def test_t_u12_lexical_weights_dict_output_is_normalized() -> None:
    vectors = _normalize_sparse({"lexical_weights": [{"42": 0.4, 7: 0.9}]})

    assert len(vectors) == 1
    assert _indices(vectors[0]) == [7, 42]
    assert _values(vectors[0]) == [0.9, 0.4]


@pytest.mark.parametrize(
    "encoded",
    (
        {"sparse_vecs": None},
        {"lexical_weights": {}},
        {"lexical_weights": []},
    ),
)
def test_t_u12_empty_sparse_output_returns_empty_indices_and_values(
    encoded: Mapping[str, Any],
) -> None:
    vectors = _normalize_sparse(encoded)

    assert len(vectors) == 1
    assert _indices(vectors[0]) == []
    assert _values(vectors[0]) == []


def test_t_u13_rrf_fusion_scores_ranking_diagnostics_and_defaults() -> None:
    module = _retrieval_module()
    rrf_fuse = _callable(module, "rrf_fuse", "fuse_rrf")
    dense_hits = [_hit("shared", "S-02", 0.91), _hit("dense-only", "S-01", 0.82)]
    sparse_hits = [_hit("shared", "S-02", 0.65), _hit("sparse-only", "S-03", 0.58)]

    hits, diagnostics = _unpack_result(
        rrf_fuse(dense_hits=dense_hits, sparse_hits=sparse_hits, fusion_owner="CLI")
    )

    assert [_hit_id(hit) for hit in hits] == ["shared", "dense-only", "sparse-only"]
    scores = [_hit_score(hit) for hit in hits]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[1]
    assert {"shared", "dense-only", "sparse-only"} == {_hit_id(hit) for hit in hits}

    assert diagnostics["rrf_k"] == 60
    assert diagnostics["fusion_owner"] == "CLI"
    assert [entry["stable_chunk_uid"] for entry in diagnostics["dense_ranking"]] == [
        "shared",
        "dense-only",
    ]
    assert [entry["stable_chunk_uid"] for entry in diagnostics["sparse_ranking"]] == [
        "shared",
        "sparse-only",
    ]
    assert [entry["stable_chunk_uid"] for entry in diagnostics["fused_ranking"]] == [
        "shared",
        "dense-only",
        "sparse-only",
    ]
    assert diagnostics["dense_ranking"][0]["score"] == 0.91
    assert diagnostics["sparse_ranking"][0]["score"] == 0.65


def test_t_u13_rrf_ties_break_by_source_section_id_then_stable_chunk_uid() -> None:
    module = _retrieval_module()
    rrf_fuse = _callable(module, "rrf_fuse", "fuse_rrf")
    dense_hits = [
        _hit("chunk-b", "S-02", 0.8),
        _hit("chunk-a", "S-01", 0.8),
        _hit("chunk-c", "S-01", 0.8),
    ]

    hits, diagnostics = _unpack_result(rrf_fuse(dense_hits=dense_hits, sparse_hits=[]))

    assert [_hit_id(hit) for hit in hits] == ["chunk-a", "chunk-c", "chunk-b"]
    assert diagnostics["tie_break"] == ["source_section_id", "stable_chunk_uid"]
    assert diagnostics["tie_break_results"][0]["stable_chunk_uid"] == "chunk-a"


def test_t_u23_retrieval_index_revision_payload_pins_schema() -> None:
    module = _retrieval_module()
    build_revision = _callable(
        module,
        "build_retrieval_index_revision",
        "build_retrieval_index_revision_payload",
    )

    payload = build_revision(
        qdrant_collection_schema_version=3,
        qdrant_server_version="1.11.0",
        flagembedding_package_version="1.3.0",
        embedding_model_revision="test-revision",
    )

    assert _get(payload, "embedding", "provider") == "flagembedding"
    assert _get(payload, "embedding", "model") == "BAAI/bge-m3"
    assert _get(payload, "embedding", "model_revision") == "test-revision"
    assert _get(payload, "dense_vector", "name") == "dense"
    assert _get(payload, "dense_vector", "size") == 1024
    assert _get(payload, "dense_vector", "distance") == "cosine"
    assert _get(payload, "sparse_vector", "name") == "sparse"
    assert _get(payload, "sparse_vector", "kind") == "bge-m3 lexical weights"
    assert _get(payload, "fusion", "method") == "rrf"
    assert _get(payload, "fusion", "rrf_k") == 60
    assert _get(payload, "vector_store", "provider") == "qdrant"
    assert _get(payload, "vector_store", "qdrant_collection_schema_version") == 3
    assert _get(payload, "vector_store", "qdrant_server_version") == "1.11.0"
    assert _get(payload, "packages", "FlagEmbedding") == "1.3.0"


def _hybrid_retrieve(
    backend: _FakeSearchBackend,
    query: str,
    *,
    dense_enabled: bool = True,
    sparse_enabled: bool = True,
) -> tuple[list[Any], Mapping[str, Any]]:
    module = _retrieval_module()
    hybrid_retrieve = _callable(module, "hybrid_retrieve", "retrieve_hybrid")
    return _unpack_result(
        hybrid_retrieve(
            query,
            backend=backend,
            dense_top_k=10,
            sparse_top_k=10,
            dense_enabled=dense_enabled,
            sparse_enabled=sparse_enabled,
        )
    )


def test_t_u24_hybrid_retrieval_empty_query_and_empty_hits() -> None:
    backend = _FakeSearchBackend(dense_hits=[], sparse_hits=[])

    empty_query_hits, _diagnostics = _hybrid_retrieve(backend, "")
    no_hit_hits, _diagnostics = _hybrid_retrieve(backend, "missing term")

    assert empty_query_hits == []
    assert no_hit_hits == []


def test_t_u24_hybrid_retrieval_dense_only_sparse_only_and_overlap() -> None:
    dense = [_hit("shared", "S-01", 0.9), _hit("dense-only", "S-02", 0.8)]
    sparse = [_hit("shared", "S-01", 0.7), _hit("sparse-only", "S-03", 0.6)]
    backend = _FakeSearchBackend(dense_hits=dense, sparse_hits=sparse)

    dense_only_hits, dense_only_diagnostics = _hybrid_retrieve(
        backend,
        "payment retry",
        sparse_enabled=False,
    )
    sparse_only_hits, sparse_only_diagnostics = _hybrid_retrieve(
        backend,
        "payment retry",
        dense_enabled=False,
    )
    fused_hits, _fused_diagnostics = _hybrid_retrieve(backend, "payment retry")

    assert [_hit_id(hit) for hit in dense_only_hits] == ["shared", "dense-only"]
    assert dense_only_diagnostics["sparse_ranking"] == []
    assert [_hit_id(hit) for hit in sparse_only_hits] == ["shared", "sparse-only"]
    assert sparse_only_diagnostics["dense_ranking"] == []
    assert [_hit_id(hit) for hit in fused_hits] == ["shared", "dense-only", "sparse-only"]


def test_t_u24_hybrid_retrieval_tie_break_is_stable_with_fake_backend() -> None:
    backend = _FakeSearchBackend(
        dense_hits=[
            _hit("chunk-z", "S-02", 0.4),
            _hit("chunk-a", "S-01", 0.4),
        ],
        sparse_hits=[],
    )

    hits, diagnostics = _hybrid_retrieve(backend, "tie")

    assert [_hit_id(hit) for hit in hits] == ["chunk-a", "chunk-z"]
    assert diagnostics["tie_break"] == ["source_section_id", "stable_chunk_uid"]


@pytest.mark.external
def test_t_i05_embedding_to_qdrant_roundtrip_uses_real_local_service() -> None:
    flagembedding = pytest.importorskip("FlagEmbedding")
    qdrant_client = pytest.importorskip("qdrant_client")
    qdrant_models = pytest.importorskip("qdrant_client.models")

    model = flagembedding.BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
    texts = ["refund policy source chunk", "invoice due date source chunk"]
    encoded = model.encode(texts, return_dense=True, return_sparse=True)
    dense_vectors = list(encoded["dense_vecs"])
    sparse_vectors = _normalize_sparse(encoded)

    client = qdrant_client.QdrantClient(os.environ.get("SPEC_GRAG_QDRANT_URL", "http://localhost:6333"))
    collection = f"spec_grag_t_i05_{uuid.uuid4().hex}"
    client.recreate_collection(
        collection_name=collection,
        vectors_config={
            "dense": qdrant_models.VectorParams(
                size=1024,
                distance=qdrant_models.Distance.COSINE,
            )
        },
        sparse_vectors_config={"sparse": qdrant_models.SparseVectorParams()},
    )

    try:
        client.upsert(
            collection_name=collection,
            points=[
                qdrant_models.PointStruct(
                    id=index,
                    vector={
                        "dense": list(map(float, dense_vectors[index])),
                        "sparse": qdrant_models.SparseVector(
                            indices=_indices(sparse_vectors[index]),
                            values=_values(sparse_vectors[index]),
                        ),
                    },
                    payload=_hit(f"chunk-{index}", f"S-0{index + 1}", 1.0, texts[index])[
                        "payload"
                    ],
                )
                for index in range(len(texts))
            ],
        )

        dense_result = client.query_points(
            collection_name=collection,
            query=list(map(float, dense_vectors[0])),
            using="dense",
            limit=1,
        ).points
        sparse_result = client.query_points(
            collection_name=collection,
            query=qdrant_models.SparseVector(
                indices=_indices(sparse_vectors[0]),
                values=_values(sparse_vectors[0]),
            ),
            using="sparse",
            limit=1,
        ).points

        for point in (dense_result[0], sparse_result[0]):
            payload = point.payload
            for field in (
                "source_document_id",
                "source_section_id",
                "heading_path",
                "source_span",
                "stable_section_uid",
                "stable_chunk_uid",
                "source_hash",
                "chunk_hash",
                "artifact_revision",
            ):
                assert field in payload
            assert "source chunk" in payload["text"]
    finally:
        client.delete_collection(collection)


def test_section_payloads_one_per_section() -> None:
    module = _retrieval_module()
    sections = [
        {
            "source_section_id": "spec.md#alpha",
            "source_document_id": "spec.md",
            "stable_section_uid": "uid-alpha",
            "heading_path": ["Spec", "Alpha"],
            "source_hash": "ha",
            "semantic_hash": "sa",
        },
        {
            "source_section_id": "spec.md#beta",
            "source_document_id": "spec.md",
            "stable_section_uid": "uid-beta",
            "heading_path": ["Spec", "Beta"],
            "source_hash": "hb",
        },
    ]
    metadata = {
        "spec.md#alpha": {
            "summary": "Alpha covers authentication.",
            "search_keys": ["auth", "login"],
            "identifiers": ["AuthService"],
        },
    }
    payloads = module.build_section_payloads(sections, metadata)
    assert len(payloads) == 2
    by_id = {p["source_section_id"]: p for p in payloads}
    assert by_id["spec.md#alpha"]["summary"] == "Alpha covers authentication."
    assert "Alpha" in by_id["spec.md#alpha"]["text"]
    assert "auth" in by_id["spec.md#alpha"]["text"].lower()
    assert by_id["spec.md#beta"]["summary"] == ""


def test_section_embeddings_artifact_uses_section_collection() -> None:
    module = _retrieval_module()
    sections = [
        {
            "source_section_id": "doc.md#a",
            "source_document_id": "doc.md",
            "stable_section_uid": "uid-a",
            "heading_path": ["Doc", "A"],
            "source_hash": "h1",
        },
    ]
    artifact = module.build_section_embeddings_artifact(
        sections,
        {"doc.md#a": {"summary": "Alpha section."}},
        generated_at="2026-05-08T00:00:00Z",
    )
    assert artifact["collection"] == "spec_grag_section"
    assert artifact["section_count"] == 1
    assert artifact["embedding"]["model"] == "BAAI/bge-m3"
    assert artifact["sections"][0]["source_section_id"] == "doc.md#a"
    assert artifact["generated_at"] == "2026-05-08T00:00:00Z"
    assert artifact["artifact_revision"]


def test_section_collection_is_distinct_from_chunk_collection() -> None:
    module = _retrieval_module()
    assert module.DEFAULT_SECTION_COLLECTION == "spec_grag_section"
    # Sanity: chunk-level standard collection name is not equal to section-level.
    chunk_default = "spec_grag_source"
    assert module.DEFAULT_SECTION_COLLECTION != chunk_default


def test_section_hybrid_candidates_excludes_self() -> None:
    module = _retrieval_module()
    sections = [
        {"source_section_id": "doc#auth", "source_document_id": "doc", "source_hash": "h1"},
        {"source_section_id": "doc#session", "source_document_id": "doc", "source_hash": "h2"},
        {"source_section_id": "doc#billing", "source_document_id": "doc", "source_hash": "h3"},
    ]
    metadata = {
        "doc#auth": {
            "summary": "User authentication login JWT tokens session refresh authorization",
            "search_keys": ["auth", "login", "JWT", "session", "tokens"],
        },
        "doc#session": {
            "summary": "Session management JWT tokens authorization refresh login authentication",
            "search_keys": ["session", "JWT", "tokens", "auth", "login"],
        },
        "doc#billing": {
            "summary": "Invoice rendering PDF layout receipt download printing",
            "search_keys": ["invoice", "PDF", "receipt"],
        },
    }
    payloads = module.build_section_payloads(sections, metadata)
    candidates = module.section_hybrid_candidates(
        "doc#auth",
        payloads,
        limit=2,
    )
    target_ids = [hit.source_section_id for hit in candidates]
    assert "doc#auth" not in target_ids
    if target_ids:
        assert target_ids[0] == "doc#session"


def test_stable_chunk_uid_to_point_id_is_deterministic() -> None:
    module = _retrieval_module()
    a1 = module.stable_chunk_uid_to_point_id("chunk-uid-1")
    a2 = module.stable_chunk_uid_to_point_id("chunk-uid-1")
    b = module.stable_chunk_uid_to_point_id("chunk-uid-2")
    assert a1 == a2, "same input must produce same point id"
    assert a1 != b, "different input must produce different point id"
    # Must be a valid UUID string
    import uuid as _uuid
    _uuid.UUID(a1)


def test_compute_chunk_diff_categorizes_added_changed_removed() -> None:
    module = _retrieval_module()
    previous = [
        {"stable_chunk_uid": "u1", "chunk_hash": "h1", "text": "a"},
        {"stable_chunk_uid": "u2", "chunk_hash": "h2", "text": "b"},
        {"stable_chunk_uid": "u3", "chunk_hash": "h3", "text": "c"},
    ]
    current = [
        {"stable_chunk_uid": "u1", "chunk_hash": "h1", "text": "a"},  # unchanged
        {"stable_chunk_uid": "u2", "chunk_hash": "h2-NEW", "text": "b'"},  # changed
        # u3 removed
        {"stable_chunk_uid": "u4", "chunk_hash": "h4", "text": "d"},  # added
    ]
    diff = module.compute_chunk_diff(previous, current)
    assert [c["stable_chunk_uid"] for c in diff["added"]] == ["u4"]
    assert [c["stable_chunk_uid"] for c in diff["changed"]] == ["u2"]
    assert [c["stable_chunk_uid"] for c in diff["unchanged"]] == ["u1"]
    assert sorted(diff["removed_uids"]) == ["u3"]


def test_compute_chunk_diff_handles_empty_previous() -> None:
    module = _retrieval_module()
    current = [
        {"stable_chunk_uid": "u1", "chunk_hash": "h1", "text": "a"},
        {"stable_chunk_uid": "u2", "chunk_hash": "h2", "text": "b"},
    ]
    diff = module.compute_chunk_diff(None, current)
    assert len(diff["added"]) == 2
    assert diff["changed"] == []
    assert diff["removed_uids"] == []


def test_qdrant_collection_schema_version_bumped_for_stable_ids() -> None:
    """Schema version must reflect the new stable point id format so existing
    collections are recreated on first run after upgrade."""
    module = _retrieval_module()
    assert module.QDRANT_COLLECTION_SCHEMA_VERSION == "qdrant-bge-m3-hybrid-v2-stable-ids"
