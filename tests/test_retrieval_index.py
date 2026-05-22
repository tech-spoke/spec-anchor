"""Retrieval Index contract tests.

The fake tests in this module must not require Qdrant or FlagEmbedding.  The
real provider roundtrip is marked external and can be skipped with
`pytest --skip-external`.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _retrieval_module() -> Any:
    return importlib.import_module("spec_anchor.retrieval_index")


def _callable(module: Any, *names: str) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail(f"spec_anchor.retrieval_index must expose one of: {', '.join(names)}")


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


class _FakePoint:
    def __init__(self, point_id: Any) -> None:
        self.id = point_id


class _FakePointStruct:
    def __init__(self, *, id: Any, vector: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        self.id = id
        self.vector = dict(vector)
        self.payload = dict(payload)


class _FakePointIdsList:
    def __init__(self, *, points: Iterable[Any]) -> None:
        self.points = list(points)


class _FakeVectorParams:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = dict(kwargs)


class _FakeSparseVectorParams:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = dict(kwargs)


class _FakeSparseVectorPayload:
    def __init__(self, *, indices: Iterable[int], values: Iterable[float]) -> None:
        self.indices = list(indices)
        self.values = list(values)


class _FakeQdrantModels(types.SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(
            PointStruct=_FakePointStruct,
            PointIdsList=_FakePointIdsList,
            VectorParams=_FakeVectorParams,
            SparseVectorParams=_FakeSparseVectorParams,
            SparseVector=_FakeSparseVectorPayload,
            Distance=types.SimpleNamespace(COSINE="cosine"),
        )


class _FakeQdrantClient:
    def __init__(self, point_ids: Iterable[Any]) -> None:
        self.point_ids = list(point_ids)
        self.deleted_point_ids: list[Any] = []
        self.upserted_points: list[Any] = []
        self.recreate_calls: list[Mapping[str, Any]] = []
        self.scroll_calls: list[Mapping[str, Any]] = []
        self.delete_calls: list[Mapping[str, Any]] = []

    def info(self) -> Mapping[str, str]:
        return {"version": "fake-qdrant"}

    def collection_exists(self, *, collection_name: str) -> bool:
        return True

    def scroll(
        self,
        *,
        collection_name: str,
        with_payload: bool,
        with_vectors: bool,
        limit: int,
        offset: int | None = None,
    ) -> tuple[list[_FakePoint], int | None]:
        start = int(offset or 0)
        end = start + int(limit)
        self.scroll_calls.append(
            {
                "collection_name": collection_name,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
                "limit": limit,
                "offset": offset,
            }
        )
        points = [_FakePoint(point_id) for point_id in self.point_ids[start:end]]
        next_offset = end if end < len(self.point_ids) else None
        return points, next_offset

    def recreate_collection(self, **kwargs: Any) -> None:
        self.recreate_calls.append(dict(kwargs))
        self.point_ids = []

    def delete(self, *, collection_name: str, points_selector: Any) -> None:
        points = list(points_selector.points)
        self.delete_calls.append(
            {"collection_name": collection_name, "points_selector": points_selector}
        )
        self.deleted_point_ids.extend(points)
        self.point_ids = [point_id for point_id in self.point_ids if point_id not in points]

    def upsert(self, *, collection_name: str, points: Iterable[Any]) -> None:
        self.upserted_points = list(points)
        by_id = {str(point_id): point_id for point_id in self.point_ids}
        for point in self.upserted_points:
            by_id[str(point.id)] = point.id
        self.point_ids = list(by_id.values())


def _install_fake_qdrant(
    monkeypatch: pytest.MonkeyPatch,
    client: _FakeQdrantClient,
) -> None:
    fake_models = _FakeQdrantModels()
    fake_qdrant_client = types.SimpleNamespace(
        QdrantClient=lambda _url: client,
        models=fake_models,
    )
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_qdrant_client)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", fake_models)


class _FakeEmbeddingProvider:
    provider_id = "fake-embedding"
    model = "fake-model"
    dense_enabled = True
    sparse_enabled = True

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: Iterable[str]) -> Any:
        texts = list(texts)
        self.calls.append(texts)
        module = _retrieval_module()
        embeddings = [
            module.BgeM3Embedding(
                dense=[float(index + 1)],
                sparse=module.SparseVector(indices=[index + 1], values=[1.0]),
            )
            for index, _text in enumerate(texts)
        ]
        return module.BgeM3EmbeddingBatch(embeddings=embeddings)

    def embed_query(self, text: str) -> Any:
        module = _retrieval_module()
        return module.BgeM3Embedding(dense=[1.0], sparse=module.SparseVector())


def _b3a_sections(section_ids: Iterable[str]) -> list[dict[str, Any]]:
    return [
        {
            "source_section_id": section_id,
            "source_document_id": section_id.split("#", 1)[0],
            "stable_section_uid": f"uid-{index}",
            "heading_path": ["Doc", section_id],
            "source_hash": f"h{index}",
            "semantic_hash": f"s{index}",
        }
        for index, section_id in enumerate(section_ids)
    ]


def test_stable_section_point_id_deterministic() -> None:
    """`/spec-core` generates Source Retrieval Index entries with stable UUID5 ids.

    SPEC_REF: §5.3 L404
    PROFILE: fake
    METHOD: artifact 内容確認
    """

    module = _retrieval_module()
    source_section_id = "docs/spec/sample.md#0001-sample-specification"

    first = module.stable_section_point_id(source_section_id)
    second = module.stable_section_point_id(source_section_id)

    assert first == second
    assert first == "dcfbeee8-791f-5fdb-8726-d81c4063f255"


def test_stable_section_point_id_no_collision() -> None:
    module = _retrieval_module()
    point_ids = {
        module.stable_section_point_id(f"docs/spec/{index:02d}.md#section-{index:02d}")
        for index in range(50)
    }

    assert len(point_ids) == 50
    for point_id in point_ids:
        uuid.UUID(point_id)


def test_upsert_stale_delete_recreate_false(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _retrieval_module()
    section_ids = ["doc.md#a", "doc.md#b", "doc.md#c"]
    stale_point_id = module.stable_section_point_id("doc.md#deleted")
    existing_point_ids = [
        *(module.stable_section_point_id(section_id) for section_id in section_ids),
        stale_point_id,
    ]
    fake_client = _FakeQdrantClient(existing_point_ids)
    _install_fake_qdrant(monkeypatch, fake_client)

    artifact = module.upsert_qdrant_section_collection(
        _b3a_sections(section_ids),
        {},
        url="http://fake-qdrant:6333",
        collection="spec_anchor_section",
        embedding_provider=_FakeEmbeddingProvider(),
        recreate=False,
    )

    assert fake_client.recreate_calls == []
    assert fake_client.deleted_point_ids == [stale_point_id]
    assert stale_point_id not in fake_client.point_ids
    assert artifact["diagnostics"]["stale_points_deleted"] == 1
    assert artifact["diagnostics"]["recreate"] is False
    assert {point.id for point in fake_client.upserted_points} == {
        module.stable_section_point_id(section_id)
        for section_id in section_ids
    }
    assert fake_client.scroll_calls[0]["limit"] == 1
    assert fake_client.scroll_calls[0]["with_payload"] is False
    assert fake_client.scroll_calls[0]["with_vectors"] is False


def test_stable_section_point_id_reorder_invariance() -> None:
    module = _retrieval_module()
    sections = _b3a_sections(["doc.md#a", "doc.md#b", "doc.md#c", "doc.md#d"])
    original = {
        section["source_section_id"]: module.stable_section_point_id(section["source_section_id"])
        for section in sections
    }
    reordered = {
        section["source_section_id"]: module.stable_section_point_id(section["source_section_id"])
        for section in reversed(sections)
    }

    assert reordered == original


def test_upsert_migration_from_ordinal(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    module = _retrieval_module()
    section_ids = ["doc.md#a", "doc.md#b", "doc.md#c"]
    fake_client = _FakeQdrantClient([0, 1, 2, 3])
    _install_fake_qdrant(monkeypatch, fake_client)
    caplog.set_level("WARNING", logger="spec_anchor.retrieval_index")

    artifact = module.upsert_qdrant_section_collection(
        _b3a_sections(section_ids),
        {},
        url="http://fake-qdrant:6333",
        collection="spec_anchor_section",
        embedding_provider=_FakeEmbeddingProvider(),
        recreate=False,
    )

    assert fake_client.recreate_calls
    assert fake_client.deleted_point_ids == []
    assert {point.id for point in fake_client.upserted_points} == {
        module.stable_section_point_id(section_id)
        for section_id in section_ids
    }
    assert artifact["diagnostics"]["recreate"] is True
    assert artifact["diagnostics"]["reason"] == "migration_required_from_ordinal_point_id"
    assert artifact["diagnostics"]["migration_required_from_ordinal_point_id"] is True
    assert "migration_required_from_ordinal_point_id" in caplog.text


def test_b3b_axis_a_embed_input_size_matches_sections_to_upsert_and_zero_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _retrieval_module()
    section_ids = ["doc.md#a", "doc.md#b", "doc.md#c"]
    sections = _b3a_sections(section_ids)
    metadata = {
        section_id: {
            "summary": f"Summary for {section_id}",
            "search_keys": [f"key-{index}"],
            "identifiers": [f"Identifier{index}"],
        }
        for index, section_id in enumerate(section_ids)
    }
    fake_client = _FakeQdrantClient(
        [module.stable_section_point_id(section_id) for section_id in section_ids]
    )
    _install_fake_qdrant(monkeypatch, fake_client)
    provider = _FakeEmbeddingProvider()

    artifact = module.upsert_qdrant_section_collection(
        sections,
        metadata,
        url="http://fake-qdrant:6333",
        collection="spec_anchor_section",
        embedding_provider=provider,
        recreate=False,
        sections_to_upsert=[sections[1], sections[2]],
        sections_to_delete=[],
    )

    assert [len(call) for call in provider.calls] == [2]
    assert artifact["diagnostics"]["embed_documents_input_size"] == 2
    assert artifact["diagnostics"]["sections_upserted_count"] == 2

    zero_client = _FakeQdrantClient(
        [module.stable_section_point_id(section_id) for section_id in section_ids]
    )
    _install_fake_qdrant(monkeypatch, zero_client)
    zero_provider = _FakeEmbeddingProvider()

    zero_artifact = module.upsert_qdrant_section_collection(
        sections,
        metadata,
        url="http://fake-qdrant:6333",
        collection="spec_anchor_section",
        embedding_provider=zero_provider,
        recreate=False,
        sections_to_upsert=[],
        sections_to_delete=[],
    )

    assert zero_provider.calls == []
    assert zero_client.upserted_points == []
    assert zero_artifact["diagnostics"]["embed_documents_input_size"] == 0
    assert zero_artifact["diagnostics"]["sections_upserted_count"] == 0


def test_b3b_axis_b_added_changed_removed_upserts_only_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _retrieval_module()
    from spec_anchor import core as core_module

    existing_ids = ["doc.md#a", "doc.md#b", "doc.md#c", "doc.md#d"]
    current_ids = ["doc.md#a", "doc.md#b", "doc.md#c", "doc.md#e"]
    previous_sections = _b3a_sections(existing_ids)
    sections = _b3a_sections(current_ids)
    sections_by_id = {section["source_section_id"]: section for section in sections}
    sections_by_id["doc.md#b"]["source_hash"] = "changed-source-b"
    sections_by_id["doc.md#b"]["semantic_hash"] = "changed-semantic-b"
    metadata = {
        section_id: {
            "summary": f"Summary for {section_id}",
            "search_keys": [f"search-{section_id[-1]}"],
            "identifiers": [f"Identifier{section_id[-1].upper()}"],
        }
        for section_id in current_ids
    }
    previous_metadata = {
        section_id: dict(
            metadata.get(
                section_id,
                {
                    "summary": f"Summary for {section_id}",
                    "search_keys": [f"search-{section_id[-1]}"],
                    "identifiers": [f"Identifier{section_id[-1].upper()}"],
                },
            )
        )
        for section_id in existing_ids
    }
    previous_fingerprints = module.build_section_payload_fingerprints(
        previous_sections,
        previous_metadata,
    )
    current_fingerprints = module.build_section_payload_fingerprints(
        sections,
        metadata,
    )
    previous_manifest = {
        "sections": [
            {
                "source_section_id": section["source_section_id"],
                "source_hash": section["source_hash"],
                "semantic_hash": section["semantic_hash"],
                **previous_fingerprints[section["source_section_id"]],
            }
            for section in previous_sections
        ]
    }
    diff = core_module._section_collection_diff_sets(
        sections,
        previous_manifest,
        current_fingerprints,
    )
    assert diff["added_section_ids"] == ["doc.md#e"]
    assert diff["changed_section_ids"] == ["doc.md#b"]
    assert diff["removed_section_ids"] == ["doc.md#d"]

    fake_client = _FakeQdrantClient(
        [module.stable_section_point_id(section_id) for section_id in existing_ids]
    )
    _install_fake_qdrant(monkeypatch, fake_client)
    provider = _FakeEmbeddingProvider()
    upsert_ids = set(diff["added_section_ids"]) | set(diff["changed_section_ids"])

    artifact = module.upsert_qdrant_section_collection(
        sections,
        metadata,
        url="http://fake-qdrant:6333",
        collection="spec_anchor_section",
        embedding_provider=provider,
        recreate=False,
        sections_to_upsert=[sections_by_id[section_id] for section_id in sorted(upsert_ids)],
        sections_to_delete=diff["removed_section_ids"],
    )

    assert len(provider.calls) == 1
    embedded_text = "\n".join(provider.calls[0])
    assert "Summary for doc.md#b" in embedded_text
    assert "Summary for doc.md#e" in embedded_text
    assert "Summary for doc.md#a" not in embedded_text
    assert "Summary for doc.md#c" not in embedded_text
    assert {point.id for point in fake_client.upserted_points} == {
        module.stable_section_point_id("doc.md#b"),
        module.stable_section_point_id("doc.md#e"),
    }
    assert fake_client.deleted_point_ids == [
        module.stable_section_point_id("doc.md#d")
    ]
    assert module.stable_section_point_id("doc.md#a") in fake_client.point_ids
    assert artifact["diagnostics"]["sections_upserted_count"] == 2
    assert artifact["diagnostics"]["sections_deleted_count"] == 1
    assert artifact["diagnostics"]["stale_points_deleted"] == 1


def test_b3b_axis_c_vector_input_fingerprint_detects_summary_change() -> None:
    module = _retrieval_module()
    from spec_anchor import core as core_module

    section = _b3a_sections(["doc.md#a"])[0]
    previous_fingerprints = module.build_section_payload_fingerprints(
        [section],
        {"doc.md#a": {"summary": "Old summary", "search_keys": [], "identifiers": []}},
    )
    current_fingerprints = module.build_section_payload_fingerprints(
        [section],
        {"doc.md#a": {"summary": "New summary", "search_keys": [], "identifiers": []}},
    )
    previous_manifest = {
        "sections": [
            {
                "source_section_id": "doc.md#a",
                "source_hash": section["source_hash"],
                "semantic_hash": section["semantic_hash"],
                **previous_fingerprints["doc.md#a"],
            }
        ]
    }

    diff = core_module._section_collection_diff_sets(
        [section],
        previous_manifest,
        current_fingerprints,
    )

    assert diff["added_section_ids"] == []
    assert diff["changed_section_ids"] == ["doc.md#a"]
    assert diff["removed_section_ids"] == []
    assert diff["changed_reasons"]["doc.md#a"] == "vector_input_fingerprint"


def test_b3b_axis_d_related_sections_only_change_does_not_invalidate_payload_fingerprint() -> None:
    # CDX-002 修正: payload_fingerprint は related_sections を除外する。
    # related_sections は update_section_collection_related_sections の
    # set_payload で別経路 patch され BGE-M3 embedding を変えない。
    # apply-before タイミング ([]) と apply-after タイミング ([{...}]) で
    # fingerprint が乖離すると partial 化が real LLM で破綻するため、
    # この test は related_sections だけの変更が diff に上がらないことを固定する。
    module = _retrieval_module()
    from spec_anchor import core as core_module

    section = _b3a_sections(["doc.md#a"])[0]
    metadata_without_related = {
        "doc.md#a": {
            "summary": "Stable summary",
            "search_keys": ["stable"],
            "identifiers": ["StableIdentifier"],
            "related_sections": [],
        }
    }
    metadata_with_related = {
        "doc.md#a": {
            "summary": "Stable summary",
            "search_keys": ["stable"],
            "identifiers": ["StableIdentifier"],
            "related_sections": [
                {"target_section_id": "doc.md#b", "relation_hint": "see_also"}
            ],
        }
    }
    previous_fingerprints = module.build_section_payload_fingerprints(
        [section],
        metadata_without_related,
    )
    current_fingerprints = module.build_section_payload_fingerprints(
        [section],
        metadata_with_related,
    )
    assert (
        previous_fingerprints["doc.md#a"]["vector_input_fingerprint"]
        == current_fingerprints["doc.md#a"]["vector_input_fingerprint"]
    )
    assert (
        previous_fingerprints["doc.md#a"]["payload_fingerprint"]
        == current_fingerprints["doc.md#a"]["payload_fingerprint"]
    )
    previous_manifest = {
        "sections": [
            {
                "source_section_id": "doc.md#a",
                "source_hash": section["source_hash"],
                "semantic_hash": section["semantic_hash"],
                **previous_fingerprints["doc.md#a"],
            }
        ]
    }

    diff = core_module._section_collection_diff_sets(
        [section],
        previous_manifest,
        current_fingerprints,
    )

    assert diff["changed_section_ids"] == []
    assert diff["unchanged"] is True


def test_b3b_axis_e_recreate_ignores_partial_arguments_and_rebuilds_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _retrieval_module()
    section_ids = ["doc.md#a", "doc.md#b", "doc.md#c"]
    sections = _b3a_sections(section_ids)
    fake_client = _FakeQdrantClient(
        [module.stable_section_point_id(section_id) for section_id in section_ids]
    )
    _install_fake_qdrant(monkeypatch, fake_client)
    provider = _FakeEmbeddingProvider()

    artifact = module.upsert_qdrant_section_collection(
        sections,
        {},
        url="http://fake-qdrant:6333",
        collection="spec_anchor_section",
        embedding_provider=provider,
        recreate=True,
        sections_to_upsert=[sections[1]],
        sections_to_delete=["doc.md#c"],
    )

    assert fake_client.recreate_calls
    assert fake_client.deleted_point_ids == []
    assert len(provider.calls) == 1
    assert len(provider.calls[0]) == 3
    assert {point.id for point in fake_client.upserted_points} == {
        module.stable_section_point_id(section_id)
        for section_id in section_ids
    }
    assert artifact["diagnostics"]["sections_upserted_count"] == 3
    assert artifact["diagnostics"]["sections_deleted_count"] == 0


def test_b3b_axis_f_new_args_none_preserves_full_upsert_migration_and_stale_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _retrieval_module()
    section_ids = ["doc.md#a", "doc.md#b"]
    sections = _b3a_sections(section_ids)
    stale_point_id = module.stable_section_point_id("doc.md#stale")
    stale_client = _FakeQdrantClient(
        [
            module.stable_section_point_id("doc.md#a"),
            stale_point_id,
        ]
    )
    _install_fake_qdrant(monkeypatch, stale_client)
    stale_provider = _FakeEmbeddingProvider()

    stale_artifact = module.upsert_qdrant_section_collection(
        sections,
        {},
        url="http://fake-qdrant:6333",
        collection="spec_anchor_section",
        embedding_provider=stale_provider,
        recreate=False,
    )

    assert [len(call) for call in stale_provider.calls] == [2]
    assert stale_client.deleted_point_ids == [stale_point_id]
    assert stale_artifact["diagnostics"]["stale_points_deleted"] == 1

    migration_client = _FakeQdrantClient([0, 1])
    _install_fake_qdrant(monkeypatch, migration_client)
    migration_provider = _FakeEmbeddingProvider()

    migration_artifact = module.upsert_qdrant_section_collection(
        sections,
        {},
        url="http://fake-qdrant:6333",
        collection="spec_anchor_section",
        embedding_provider=migration_provider,
        recreate=False,
    )

    assert [len(call) for call in migration_provider.calls] == [2]
    assert migration_client.recreate_calls
    assert migration_artifact["diagnostics"]["reason"] == "migration_required_from_ordinal_point_id"
    assert migration_artifact["diagnostics"]["migration_required_from_ordinal_point_id"] is True


def test_fast_path_consistency_with_new_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_anchor.artifacts import ContextArtifactStore
    from spec_anchor import core as core_module

    sections = _b3a_sections(["doc.md#a", "doc.md#b"])
    config = {
        "embedding": {
            "provider": "flagembedding",
            "model": "BAAI/bge-m3",
            "dense_enabled": True,
            "sparse_enabled": True,
        }
    }
    store = ContextArtifactStore(tmp_path / ".spec-anchor" / "context")
    expected = core_module._build_retrieval_index_state(
        sections,
        config=config,
        collection="spec_anchor_section",
        generated_at="2026-05-13T00:00:00Z",
    )
    monkeypatch.setattr(core_module, "_section_collection_exists", lambda *_args: True)
    unchanged_sections = {
        "unchanged": True,
        "reason": core_module.UNCHANGED_SECTION_REASON,
    }

    store.write("retrieval_index_state", expected)
    assert store.path_for("retrieval_index_state").is_file()
    decision = core_module._retrieval_index_fast_path_decision(
        expected,
        store=store,
        url="http://localhost:6333",
        collection="spec_anchor_section",
        run_full=False,
        force_full_recreate=False,
        unchanged_sections=unchanged_sections,
    )
    assert decision == {"can_skip": True, "reason": core_module.UNCHANGED_SECTION_REASON}

    old_state = dict(expected)
    old_state["retrieval_schema_pin_fingerprint"] = "old-fingerprint-before-b3a"
    store.write("retrieval_index_state", old_state)
    decision = core_module._retrieval_index_fast_path_decision(
        expected,
        store=store,
        url="http://localhost:6333",
        collection="spec_anchor_section",
        run_full=False,
        force_full_recreate=False,
        unchanged_sections=unchanged_sections,
    )
    assert decision == {
        "can_skip": False,
        "reason": "fingerprint_mismatch",
        "field": "retrieval_schema_pin_fingerprint",
    }


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
    module = _retrieval_module()

    model = flagembedding.BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
    texts = ["refund policy source chunk", "invoice due date source chunk"]
    encoded = model.encode(texts, return_dense=True, return_sparse=True)
    dense_vectors = list(encoded["dense_vecs"])
    sparse_vectors = _normalize_sparse(encoded)

    client = qdrant_client.QdrantClient(os.environ.get("SPEC_ANCHOR_QDRANT_URL", "http://localhost:6333"))
    collection = f"spec_anchor_t_i05_{uuid.uuid4().hex}"
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
        points = []
        for index in range(len(texts)):
            source_section_id = f"S-0{index + 1}"
            points.append(
                qdrant_models.PointStruct(
                    id=module.stable_section_point_id(source_section_id),
                    vector={
                        "dense": list(map(float, dense_vectors[index])),
                        "sparse": qdrant_models.SparseVector(
                            indices=_indices(sparse_vectors[index]),
                            values=_values(sparse_vectors[index]),
                        ),
                    },
                    payload=_hit(f"chunk-{index}", source_section_id, 1.0, texts[index])[
                        "payload"
                    ],
                )
            )
        client.upsert(collection_name=collection, points=points)

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
            "source_span": {
                "start_line": 3,
                "end_line": 5,
                "start_offset": 20,
                "end_offset": 90,
            },
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
    assert by_id["spec.md#alpha"]["source_span"]["start_line"] == 3
    assert by_id["spec.md#alpha"]["source_span"]["end_line"] == 5
    assert "Alpha" in by_id["spec.md#alpha"]["text"]
    assert "auth" in by_id["spec.md#alpha"]["text"].lower()
    assert by_id["spec.md#beta"]["summary"] == ""


def test_section_payloads_use_empty_source_span_for_incomplete_or_invalid_fields() -> None:
    module = _retrieval_module()
    sections = [
        {
            "source_section_id": "spec.md#missing",
            "source_document_id": "spec.md",
            "source_span": {"start_line": 3, "end_line": 5},
            "source_hash": "hm",
        },
        {
            "source_section_id": "spec.md#invalid",
            "source_document_id": "spec.md",
            "source_span": {
                "start_line": 3,
                "end_line": "not-int",
                "start_offset": 20,
                "end_offset": 90,
            },
            "source_hash": "hi",
        },
    ]

    payloads = module.build_section_payloads(sections, {})

    by_id = {p["source_section_id"]: p for p in payloads}
    assert by_id["spec.md#missing"]["source_span"] == {}
    assert by_id["spec.md#invalid"]["source_span"] == {}


def test_section_payloads_include_related_sections_when_metadata_has_it() -> None:
    """Phase R-3: related_sections must round-trip through build_section_payloads."""

    module = _retrieval_module()
    sections = [
        {
            "source_section_id": "spec.md#alpha",
            "source_document_id": "spec.md",
            "stable_section_uid": "uid-alpha",
            "heading_path": ["Spec", "Alpha"],
            "source_hash": "ha",
        },
    ]
    related = [
        {
            "target_section_id": "spec.md#beta",
            "relation_hint": "depends_on",
            "confidence": "high",
            "reason": "alpha depends on beta",
            "evidence_terms": ["auth"],
            "channels": ["shared_identifier"],
        }
    ]
    metadata = {
        "spec.md#alpha": {
            "summary": "Alpha summary.",
            "search_keys": ["auth"],
            "identifiers": ["AuthService"],
            "related_sections": related,
        },
    }
    payloads = module.build_section_payloads(sections, metadata)

    assert payloads[0]["related_sections"] == related
    # The list must be a copy, not the same reference (so later mutation
    # of metadata does not leak into the payload).
    assert payloads[0]["related_sections"] is not related


def test_section_payloads_default_related_sections_to_empty_list() -> None:
    """Phase R-3: when metadata has no related_sections, payload defaults to []."""

    module = _retrieval_module()
    sections = [
        {
            "source_section_id": "spec.md#alpha",
            "source_document_id": "spec.md",
            "stable_section_uid": "uid-alpha",
            "heading_path": ["Spec", "Alpha"],
            "source_hash": "ha",
        }
    ]
    metadata = {"spec.md#alpha": {"summary": "Alpha summary."}}

    payloads = module.build_section_payloads(sections, metadata)

    assert payloads[0]["related_sections"] == []


def test_update_section_collection_related_sections_issues_set_payload_per_section() -> None:
    """Phase R-3: related_sections is patched via set_payload, not re-embedded."""

    module = _retrieval_module()
    captured: list[dict[str, Any]] = []

    class _FakeQdrantClient:
        def set_payload(
            self,
            *,
            collection_name: str,
            payload: dict[str, Any],
            points: Any,
        ) -> None:
            captured.append(
                {
                    "collection_name": collection_name,
                    "payload": payload,
                    "points": points,
                }
            )

    fake = _FakeQdrantClient()
    related_by_id = {
        "spec.md#alpha": [
            {
                "target_section_id": "spec.md#beta",
                "relation_hint": "depends_on",
                "confidence": "high",
            }
        ],
        "spec.md#beta": [],
    }

    diagnostics = module.update_section_collection_related_sections(
        related_by_id,
        collection="spec_anchor_section",
        client=fake,
    )

    assert diagnostics["status"] == "success"
    assert diagnostics["section_count"] == 2
    assert diagnostics["errors"] == []
    assert len(captured) == 2
    seen_section_ids: list[str] = []
    for call in captured:
        assert call["collection_name"] == "spec_anchor_section"
        assert set(call["payload"].keys()) == {"related_sections"}
        must = getattr(call["points"], "must", []) or []
        section_id = ""
        for cond in must:
            if getattr(cond, "key", None) == "source_section_id":
                section_id = getattr(getattr(cond, "match", None), "value", "")
        seen_section_ids.append(str(section_id))
    assert sorted(seen_section_ids) == ["spec.md#alpha", "spec.md#beta"]


def test_update_section_collection_related_sections_empty_input_skips_client() -> None:
    """Phase R-3: empty input must not contact Qdrant."""

    module = _retrieval_module()

    class _AssertNoCallClient:
        def set_payload(self, **kwargs: Any) -> None:  # pragma: no cover
            raise AssertionError("set_payload must not be called for empty input")

    diagnostics = module.update_section_collection_related_sections(
        {},
        client=_AssertNoCallClient(),
    )

    assert diagnostics == {
        "status": "success",
        "section_count": 0,
        "errors": [],
        "collection": module.DEFAULT_SECTION_COLLECTION,
    }


def test_update_section_collection_related_sections_records_per_section_error() -> None:
    """Phase R-3: a failing set_payload must be reported, not raised."""

    module = _retrieval_module()

    class _PartiallyFailingClient:
        def __init__(self) -> None:
            self.calls = 0

        def set_payload(
            self,
            *,
            collection_name: str,
            payload: dict[str, Any],
            points: Any,
        ) -> None:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("simulated Qdrant outage")

    fake = _PartiallyFailingClient()
    diagnostics = module.update_section_collection_related_sections(
        {"alpha": [], "beta": []},
        client=fake,
    )

    assert diagnostics["status"] == "degraded"
    assert diagnostics["section_count"] == 1
    assert len(diagnostics["errors"]) == 1
    assert diagnostics["errors"][0]["reason_code"] == "set_payload_failed"


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
    assert artifact["collection"] == "spec_anchor_section"
    assert artifact["section_count"] == 1
    assert artifact["embedding"]["model"] == "BAAI/bge-m3"
    assert artifact["sections"][0]["source_section_id"] == "doc.md#a"
    assert artifact["generated_at"] == "2026-05-08T00:00:00Z"
    assert artifact["artifact_revision"]


def test_section_collection_default_name() -> None:
    module = _retrieval_module()
    assert module.DEFAULT_SECTION_COLLECTION == "spec_anchor_section"


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


def test_qdrant_collection_schema_version_bumped_for_stable_ids() -> None:
    """Schema version must reflect the new stable point id format so existing
    collections are recreated on first run after upgrade."""
    module = _retrieval_module()
    assert module.QDRANT_COLLECTION_SCHEMA_VERSION == "qdrant-bge-m3-hybrid-v2-stable-ids"
