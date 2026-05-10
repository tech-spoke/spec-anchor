"""Qdrant section-level payload read helpers.

Phase R-2 (`doc/STORAGE_REDESIGN.ja.md` §7.4) consolidates section content
read paths onto the `spec_grag_section` Qdrant collection payload. This
module hosts the lookup helpers downstream callers (Phase R-6 inject CLI,
watcher snapshot consumers, future agents) use to read section data
without opening `.spec-grag/context/section_metadata.json`.

The Qdrant payload schema written by `build_section_payloads` in
`spec_grag/retrieval_index.py:1043` is the contract. This module
normalizes payload dicts back into the `section_metadata.json["sections"]`
entry shape so legacy consumers can switch over without restructuring.
The legacy JSON artifact remains the write-time fallback until Phase R-3
attaches Related Sections to the payload via `set_payload` and Phase R-5
removes the JSON entirely.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from spec_grag.retrieval_index import DEFAULT_SECTION_COLLECTION


SECTION_PAYLOAD_LOOKUP_BATCH = 256


class SectionPayloadLookupError(RuntimeError):
    """Raised when the Qdrant section collection cannot serve a payload read."""


def fetch_section_payloads(
    client: Any,
    section_ids: Sequence[str],
    *,
    collection: str = DEFAULT_SECTION_COLLECTION,
    batch: int = SECTION_PAYLOAD_LOOKUP_BATCH,
) -> dict[str, dict[str, Any]]:
    """Return `{section_id: payload}` for the given section ids.

    Uses `client.scroll` with a `source_section_id` filter so callers can
    look up section content without a vector search. Missing section_ids
    are simply absent from the result dict; callers decide whether that
    is an error.

    `client` is a `qdrant_client.QdrantClient` instance. The collection
    must be the section-level collection (default `spec_grag_section`).
    """

    section_ids = [str(value) for value in section_ids if value]
    if not section_ids:
        return {}

    try:
        from qdrant_client import models as qdrant_models  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - import guard
        raise SectionPayloadLookupError(
            "qdrant_client is required for section payload lookup"
        ) from exc

    result: dict[str, dict[str, Any]] = {}
    for start in range(0, len(section_ids), max(1, int(batch))):
        slice_ids = section_ids[start : start + batch]
        scroll_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="source_section_id",
                    match=qdrant_models.MatchAny(any=slice_ids),
                )
            ]
        )
        offset: Any = None
        while True:
            points, next_offset = client.scroll(
                collection_name=collection,
                scroll_filter=scroll_filter,
                with_payload=True,
                with_vectors=False,
                limit=len(slice_ids),
                offset=offset,
            )
            for point in points:
                payload = dict(getattr(point, "payload", None) or {})
                section_id = payload.get("source_section_id") or payload.get("section_id")
                if not isinstance(section_id, str) or not section_id:
                    continue
                if section_id not in result:
                    result[section_id] = payload
            if not next_offset:
                break
            offset = next_offset
    return result


def section_payload_to_metadata_entry(
    payload: Mapping[str, Any],
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate a Qdrant section payload into a section_metadata entry shape.

    The shape matches `.spec-grag/context/section_metadata.json["sections"][i]`
    so consumers that historically read the JSON can pass a Qdrant payload
    through this normalizer instead. Fields absent from the payload are
    filled with empty defaults.
    """

    section_id = str(payload.get("source_section_id") or payload.get("section_id") or "")
    entry: dict[str, Any] = {
        "section_id": section_id,
        "source_section_id": section_id,
        "stable_section_uid": str(payload.get("stable_section_uid") or section_id),
        "source_document_id": str(payload.get("source_document_id") or ""),
        "heading_path": list(payload.get("heading_path") or []),
        "summary": str(payload.get("summary") or ""),
        "search_keys": list(payload.get("search_keys") or []),
        "identifiers": list(payload.get("identifiers") or []),
        "related_sections": list(payload.get("related_sections") or []),
        "source_hash": str(payload.get("source_hash") or ""),
        "semantic_hash": str(payload.get("semantic_hash") or payload.get("source_hash") or ""),
    }
    if extra:
        for key, value in extra.items():
            entry.setdefault(key, value)
    return entry


def metadata_entries_from_payloads(
    payloads: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Translate a batch of Qdrant payloads into metadata entries."""

    return [section_payload_to_metadata_entry(payload) for payload in payloads]


__all__ = [
    "SECTION_PAYLOAD_LOOKUP_BATCH",
    "SectionPayloadLookupError",
    "fetch_section_payloads",
    "metadata_entries_from_payloads",
    "section_payload_to_metadata_entry",
]
