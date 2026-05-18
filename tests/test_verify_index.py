from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _core_module() -> Any:
    return importlib.import_module("spec_grag.core")


def _retrieval_module() -> Any:
    return importlib.import_module("spec_grag.retrieval_index")


class _Point:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = dict(payload)


class _FakeQdrantClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = [dict(payload) for payload in payloads]
        self.scroll_calls: list[dict[str, Any]] = []

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
    ) -> tuple[list[_Point], int | None]:
        self.scroll_calls.append(
            {
                "collection_name": collection_name,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
                "limit": limit,
                "offset": offset,
            }
        )
        start = int(offset or 0)
        end = start + int(limit)
        next_offset = end if end < len(self.payloads) else None
        return [_Point(payload) for payload in self.payloads[start:end]], next_offset


class _ExplodingQdrantClient:
    scroll_calls: list[dict[str, Any]] = []

    def collection_exists(self, *, collection_name: str) -> bool:
        raise AssertionError("verify-index should not query Qdrant in this test")


def _install_fake_qdrant(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    fake_qdrant_client = types.SimpleNamespace(QdrantClient=lambda _url: client)
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_qdrant_client)


def _config(
    *,
    embedding_provider: str = "flagembedding",
    vector_store_provider: str = "qdrant",
) -> dict[str, Any]:
    return {
        "embedding": {
            "provider": embedding_provider,
            "model": "BAAI/bge-m3",
            "dense_enabled": True,
            "sparse_enabled": True,
        },
        "vector_store": {
            "provider": vector_store_provider,
            "url": "http://fake-qdrant:6333",
        },
        "retrieval": {
            "section_collection": "verify_index_collection",
        },
    }


def _payload(
    section_id: str = "docs/spec/main.md#alpha",
    *,
    source_hash: str = "source-alpha",
    semantic_hash: str = "semantic-alpha",
    text: str = "Alpha | summary | key",
) -> dict[str, Any]:
    return {
        "source_document_id": section_id.split("#", 1)[0],
        "source_section_id": section_id,
        "stable_section_uid": section_id,
        "stable_chunk_uid": section_id,
        "heading_path": ["Main", "Alpha"],
        "source_span": {"start_line": 1, "end_line": 3},
        "source_hash": source_hash,
        "semantic_hash": semantic_hash,
        "summary": "summary",
        "search_keys": ["key"],
        "identifiers": ["IDENT"],
        "related_sections": [],
        "text": text,
    }


def _manifest(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval = _retrieval_module()
    entries = []
    for payload in payloads:
        fingerprints = retrieval.section_payload_fingerprints(payload)
        entries.append(
            {
                "section_id": payload["source_section_id"],
                "source_section_id": payload["source_section_id"],
                "source_hash": payload["source_hash"],
                "semantic_hash": payload["semantic_hash"],
                "vector_input_fingerprint": fingerprints["vector_input_fingerprint"],
                "payload_fingerprint": fingerprints["payload_fingerprint"],
            }
        )
    return {"sections": entries}


def _verify(
    *,
    config: dict[str, Any],
    manifest: dict[str, Any],
    retrieval_index_status: str = "skipped_unchanged",
    verify_index: bool = True,
    force_full_recreate: bool = False,
    upsert_info: dict[str, Any] | None = None,
    progress_root: Path | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    core = _core_module()
    tracker = None
    if progress_root is not None:
        tracker = core.CoreProgressTracker(
            progress_root,
            run_id="verify-index-test",
            mode="incremental",
            generated_at="2026-05-14T00:00:00Z",
        )
    status, diagnostics = core._verify_section_collection_if_requested(
        config=config,
        section_manifest=manifest,
        retrieval_index_status=retrieval_index_status,
        verify_index=verify_index,
        force_full_recreate=force_full_recreate,
        section_collection_upsert_info=upsert_info or {},
        progress_tracker=tracker,
    )
    progress = None
    if progress_root is not None:
        progress = importlib.import_module("spec_grag.core_progress").read_progress(progress_root)
    return status, diagnostics, progress


def test_verify_index_clean_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload()
    client = _FakeQdrantClient([payload])
    _install_fake_qdrant(monkeypatch, client)

    status, diagnostics, progress = _verify(
        config=_config(),
        manifest=_manifest([payload]),
        retrieval_index_status="skipped_unchanged",
        progress_root=tmp_path,
    )

    assert status == "skipped_unchanged"
    assert diagnostics == {
        "executed": True,
        "checked_count": 1,
        "stale_point_count": 0,
        "missing_point_count": 0,
        "hash_mismatch_count": 0,
        "issues": [],
    }
    assert client.scroll_calls == [
        {
            "collection_name": "verify_index_collection",
            "with_payload": True,
            "with_vectors": False,
            "limit": 256,
            "offset": None,
        }
    ]
    assert progress is not None
    assert progress["stages"]["verify_index"]["action"] == "verified_clean"


def test_verify_index_detects_stale_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _payload()
    stale = _payload("docs/spec/main.md#stale")
    client = _FakeQdrantClient([expected, stale])
    _install_fake_qdrant(monkeypatch, client)

    status, diagnostics, progress = _verify(
        config=_config(),
        manifest=_manifest([expected]),
        retrieval_index_status="success",
        progress_root=tmp_path,
    )

    assert status == "failed"
    assert diagnostics["stale_point_count"] == 1
    assert diagnostics["issues"][0]["reason_code"] == "stale_point"
    assert progress is not None
    assert progress["stages"]["verify_index"]["action"] == "verified_inconsistent"


def test_verify_index_detects_missing_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _payload()
    client = _FakeQdrantClient([])
    _install_fake_qdrant(monkeypatch, client)

    status, diagnostics, progress = _verify(
        config=_config(),
        manifest=_manifest([expected]),
        retrieval_index_status="success",
        progress_root=tmp_path,
    )

    assert status == "failed"
    assert diagnostics["missing_point_count"] == 1
    assert diagnostics["issues"] == [
        {
            "section_id": "docs/spec/main.md#alpha",
            "reason_code": "missing_point",
            "fields": [],
        }
    ]
    assert progress is not None
    assert progress["stages"]["verify_index"]["action"] == "verified_inconsistent"


def test_verify_index_detects_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _payload()
    actual = dict(expected)
    actual["source_hash"] = "source-broken"
    client = _FakeQdrantClient([actual])
    _install_fake_qdrant(monkeypatch, client)

    status, diagnostics, progress = _verify(
        config=_config(),
        manifest=_manifest([expected]),
        retrieval_index_status="success",
        progress_root=tmp_path,
    )

    assert status == "failed"
    assert diagnostics["hash_mismatch_count"] == 1
    assert diagnostics["issues"] == [
        {
            "section_id": "docs/spec/main.md#alpha",
            "reason_code": "hash_mismatch",
            "fields": ["source_hash"],
        }
    ]
    assert progress is not None
    assert progress["stages"]["verify_index"]["reason"] == "hash_mismatch"


def test_verify_index_disabled_for_fake_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _ExplodingQdrantClient()
    _install_fake_qdrant(monkeypatch, client)

    status, diagnostics, progress = _verify(
        config=_config(embedding_provider="fake", vector_store_provider="memory"),
        manifest=_manifest([_payload()]),
        retrieval_index_status="skipped",
        progress_root=tmp_path,
    )

    assert status == "skipped"
    assert diagnostics == {"executed": False, "reason": "disabled"}
    assert progress is not None
    assert progress["stages"]["verify_index"]["action"] == "disabled"


def test_verify_index_skipped_after_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _ExplodingQdrantClient()
    _install_fake_qdrant(monkeypatch, client)

    status, diagnostics, progress = _verify(
        config=_config(),
        manifest=_manifest([_payload()]),
        retrieval_index_status="success",
        force_full_recreate=True,
        upsert_info={"action": "upserted_full", "recreate": True},
        progress_root=tmp_path,
    )

    assert status == "success"
    assert diagnostics == {"executed": False, "reason": "already_recreated"}
    assert progress is not None
    assert progress["stages"]["verify_index"]["action"] == "skipped"


def test_verify_index_skipped_when_flag_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _ExplodingQdrantClient()
    _install_fake_qdrant(monkeypatch, client)

    status, diagnostics, progress = _verify(
        config=_config(),
        manifest=_manifest([_payload()]),
        retrieval_index_status="success",
        verify_index=False,
        progress_root=tmp_path,
    )

    assert status == "success"
    assert diagnostics == {"executed": False, "reason": "not_requested"}
    assert progress is not None
    assert progress["stages"]["verify_index"]["action"] == "disabled"
