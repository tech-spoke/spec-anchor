"""Pair-level cache for Related Sections relation typing.

Each cache entry corresponds to a single (source_section, target_section)
pair classified by the LLM. The key includes both section content hashes,
the prompt version, model and effort so any change invalidates the entry
automatically.

Rejected pairs (sent to the LLM but not returned in the output) are also
recorded so they are not re-evaluated on the next run.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

CACHE_SCHEMA_VERSION = 1
CACHE_FILE_NAME = "related_typing_cache.json"


def make_related_typing_cache_key(
    *,
    source_section_id: str,
    target_section_id: str,
    source_hash: str,
    target_hash: str,
    prompt_version: str,
    model: str,
    effort: str | None,
) -> str:
    payload = "|".join(
        [
            source_section_id,
            target_section_id,
            source_hash,
            target_hash,
            prompt_version,
            model or "",
            str(effort or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class RelatedTypingCache:
    """File-backed pair cache. Empty / missing path → no-op cache."""

    def __init__(self, cache_path: Path | None) -> None:
        self.path: Path | None = Path(cache_path) if cache_path else None
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._loaded_schema = CACHE_SCHEMA_VERSION
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        if data.get("schema_version") != CACHE_SCHEMA_VERSION:
            return
        entries = data.get("entries")
        if isinstance(entries, dict):
            self._entries = {
                str(k): dict(v) for k, v in entries.items() if isinstance(v, dict)
            }

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._entries.get(key)
        return dict(entry) if entry is not None else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        existing = self._entries.get(key)
        if existing == value:
            return
        self._entries[key] = dict(value)
        self._dirty = True

    def save(self) -> None:
        if not self._dirty or self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "entries": self._entries,
        }
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, self.path)
        self._dirty = False

    @property
    def size(self) -> int:
        return len(self._entries)


__all__ = [
    "CACHE_FILE_NAME",
    "CACHE_SCHEMA_VERSION",
    "RelatedTypingCache",
    "make_related_typing_cache_key",
]
