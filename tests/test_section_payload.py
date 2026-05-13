"""Tests for the Qdrant section-payload read helpers.

Cover the helpers in `spec_grag/section_payload.py`. Verify that:

* `fetch_section_payloads` issues a single scroll per batch with a
  `MatchAny(any=section_ids)` filter on the `source_section_id` field, and
  returns a `{section_id: payload}` dict that follows insertion order.
* `section_payload_to_metadata_entry` reproduces the section metadata entry
  shape (section_id, summary, search_keys, identifiers, related_sections,
  heading_path, source_hash, semantic_hash, ...).
* Empty input returns an empty dict without touching the client.

These tests use a `FakeQdrantClient` that captures scroll arguments and
returns canned points, so the contract is verified without a running
Qdrant service.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spec_grag.section_payload import (  # noqa: E402
    SECTION_PAYLOAD_LOOKUP_BATCH,
    fetch_section_payloads,
    metadata_entries_from_payloads,
    section_payload_to_metadata_entry,
)


@dataclass
class _FakePoint:
    payload: dict[str, Any]
    id: int


@dataclass
class _FakeQdrantClient:
    points_by_section_id: dict[str, dict[str, Any]]
    scroll_calls: list[dict[str, Any]] = field(default_factory=list)

    def scroll(
        self,
        *,
        collection_name: str,
        scroll_filter: Any,
        with_payload: bool,
        with_vectors: bool,
        limit: int,
        offset: Any,
    ) -> tuple[list[_FakePoint], Any]:
        # Inspect the filter to discover which section_ids were requested.
        section_ids = _extract_match_any_section_ids(scroll_filter)
        self.scroll_calls.append(
            {
                "collection_name": collection_name,
                "section_ids": section_ids,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
                "limit": limit,
                "offset": offset,
            }
        )
        points = [
            _FakePoint(payload=dict(self.points_by_section_id[sid]), id=index)
            for index, sid in enumerate(section_ids)
            if sid in self.points_by_section_id
        ]
        return points, None


def _extract_match_any_section_ids(scroll_filter: Any) -> list[str]:
    must = getattr(scroll_filter, "must", None) or []
    for condition in must:
        if getattr(condition, "key", None) == "source_section_id":
            match = getattr(condition, "match", None)
            any_values = getattr(match, "any", None)
            if any_values is not None:
                return [str(value) for value in any_values]
    return []


def _payload(section_id: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "source_document_id": "docs/spec/main.md",
        "source_section_id": section_id,
        "stable_section_uid": f"uid-{section_id}",
        "stable_chunk_uid": f"uid-{section_id}",
        "heading_path": ["Chapter", section_id],
        "source_span": {
            "start_line": 10,
            "end_line": 12,
            "start_offset": 100,
            "end_offset": 180,
        },
        "source_hash": f"hash-{section_id}",
        "semantic_hash": f"hash-{section_id}",
        "summary": f"summary for {section_id}",
        "search_keys": [f"key-{section_id}", "shared key"],
        "identifiers": [f"Sym{section_id}", "sharedIdent"],
        "text": f"heading | summary | keys | identifiers ({section_id})",
    }
    base.update(overrides)
    return base


def test_fetch_section_payloads_returns_section_id_indexed_dict() -> None:
    payload_alpha = _payload("alpha")
    payload_beta = _payload("beta")
    client = _FakeQdrantClient(points_by_section_id={"alpha": payload_alpha, "beta": payload_beta})

    result = fetch_section_payloads(client, ["alpha", "beta"], collection="spec_grag_section")

    assert set(result.keys()) == {"alpha", "beta"}
    assert result["alpha"] == payload_alpha
    assert result["beta"] == payload_beta
    assert len(client.scroll_calls) == 1
    call = client.scroll_calls[0]
    assert call["collection_name"] == "spec_grag_section"
    assert call["section_ids"] == ["alpha", "beta"]
    assert call["with_payload"] is True
    assert call["with_vectors"] is False


def test_fetch_section_payloads_skips_missing_section_ids_silently() -> None:
    client = _FakeQdrantClient(points_by_section_id={"alpha": _payload("alpha")})

    result = fetch_section_payloads(client, ["alpha", "ghost"])

    assert set(result.keys()) == {"alpha"}


def test_fetch_section_payloads_empty_input_skips_qdrant_call() -> None:
    client = _FakeQdrantClient(points_by_section_id={"alpha": _payload("alpha")})

    result = fetch_section_payloads(client, [])

    assert result == {}
    assert client.scroll_calls == []


def test_fetch_section_payloads_batches_large_id_lists() -> None:
    section_ids = [f"sec-{index:03d}" for index in range(SECTION_PAYLOAD_LOOKUP_BATCH + 3)]
    points = {sid: _payload(sid) for sid in section_ids}
    client = _FakeQdrantClient(points_by_section_id=points)

    result = fetch_section_payloads(
        client,
        section_ids,
        batch=SECTION_PAYLOAD_LOOKUP_BATCH,
    )

    assert set(result.keys()) == set(section_ids)
    assert len(client.scroll_calls) == 2  # one full batch + remainder
    first, second = client.scroll_calls
    assert first["section_ids"] == section_ids[:SECTION_PAYLOAD_LOOKUP_BATCH]
    assert second["section_ids"] == section_ids[SECTION_PAYLOAD_LOOKUP_BATCH:]


def test_section_payload_to_metadata_entry_matches_legacy_shape() -> None:
    payload = _payload(
        "alpha",
        related_sections=[
            {"target_section_id": "beta", "relation_hint": "depends_on", "confidence": "high"}
        ],
    )

    entry = section_payload_to_metadata_entry(payload)

    expected_keys = {
        "section_id",
        "source_section_id",
        "stable_section_uid",
        "source_document_id",
        "heading_path",
        "source_span",
        "summary",
        "search_keys",
        "identifiers",
        "related_sections",
        "source_hash",
        "semantic_hash",
    }
    assert expected_keys.issubset(entry.keys())
    assert entry["section_id"] == "alpha"
    assert entry["heading_path"] == ["Chapter", "alpha"]
    assert entry["source_span"]["start_line"] == 10
    assert entry["related_sections"][0]["target_section_id"] == "beta"
    # search_keys / identifiers must be copied as lists (not the payload reference).
    assert entry["search_keys"] is not payload["search_keys"]
    assert entry["identifiers"] is not payload["identifiers"]


def test_section_payload_to_metadata_entry_fills_empty_defaults() -> None:
    payload = {"source_section_id": "lonely"}

    entry = section_payload_to_metadata_entry(payload)

    assert entry["section_id"] == "lonely"
    assert entry["summary"] == ""
    assert entry["search_keys"] == []
    assert entry["identifiers"] == []
    assert entry["related_sections"] == []
    assert entry["heading_path"] == []
    assert entry["source_span"] == {}


def test_section_payload_to_metadata_entry_supports_extras() -> None:
    payload = _payload("alpha")

    entry = section_payload_to_metadata_entry(
        payload,
        extra={"llm_generation_status": "success", "summary": "must-not-override"},
    )

    # `extra` uses setdefault, so existing keys are preserved.
    assert entry["summary"] == "summary for alpha"
    assert entry["llm_generation_status"] == "success"


def test_metadata_entries_from_payloads_preserves_order() -> None:
    payloads = [_payload("a"), _payload("b"), _payload("c")]

    entries = metadata_entries_from_payloads(payloads)

    assert [entry["section_id"] for entry in entries] == ["a", "b", "c"]


def test_fetch_section_payloads_normalizes_string_section_ids() -> None:
    client = _FakeQdrantClient(points_by_section_id={"alpha": _payload("alpha")})

    result = fetch_section_payloads(client, ["alpha", "", None])  # type: ignore[list-item]

    assert set(result.keys()) == {"alpha"}
    call = client.scroll_calls[0]
    assert call["section_ids"] == ["alpha"]


def test_section_payload_lookup_error_is_runtime_error_subclass() -> None:
    """SectionPayloadLookupError must be a RuntimeError so callers can catch broadly."""

    from spec_grag.section_payload import SectionPayloadLookupError

    assert issubclass(SectionPayloadLookupError, RuntimeError)
