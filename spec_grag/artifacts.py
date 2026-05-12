"""Context and state artifact read/write helpers.

Two on-disk locations host the persistent artifacts:

* `.spec-grag/context/`  — human-facing read API (chapter_anchors,
  conflict_review_items)
* `.spec-grag/state/`    — `/spec-core` execution state (section_manifest,
  freshness, watch_state, watch_queue, core_update.lock)

`ContextArtifactStore` resolves the on-disk path per artifact name and
keeps the atomic-write / rollback behavior for the union of artifacts
written together by `/spec-core`.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1

# Artifact filename map. The dict is the single source of truth for the
# physical filenames; the directory each artifact lives in is recorded in
# `STATE_ARTIFACTS` below (state) vs the remaining keys (context).
ARTIFACT_FILENAMES = {
    "section_manifest": "section_manifest.json",
    "conflict_review_items": "conflict_review_items.json",
    "chapter_anchors": "chapter_anchors.json",
    "freshness": "freshness.json",
}

# Artifact names that live in `.spec-grag/state/` rather than
# `.spec-grag/context/`.
STATE_ARTIFACTS = frozenset({"section_manifest", "freshness"})

CORE_ARTIFACT_ORDER = (
    "section_manifest",
    "conflict_review_items",
    "chapter_anchors",
    "freshness",
)


class ArtifactError(Exception):
    """Raised when an artifact cannot be read or written."""


class ContextArtifactStore:
    """Resolve and atomically write the `.spec-grag/context/` and
    `.spec-grag/state/` artifacts produced by `/spec-core`.

    `state_dir` defaults to the sibling `.spec-grag/state/` directory of the
    given `context_dir` (i.e. `context_dir.parent / "state"`).
    """

    def __init__(
        self,
        context_dir: str | Path,
        *,
        state_dir: str | Path | None = None,
    ) -> None:
        self.context_dir = Path(context_dir)
        self.state_dir = (
            Path(state_dir) if state_dir is not None else self.context_dir.parent / "state"
        )

    def path_for(self, artifact_name: str) -> Path:
        try:
            filename = ARTIFACT_FILENAMES[artifact_name]
        except KeyError as exc:
            raise ArtifactError(f"unknown artifact: {artifact_name}") from exc
        base_dir = self.state_dir if artifact_name in STATE_ARTIFACTS else self.context_dir
        return base_dir / filename

    def read(self, artifact_name: str) -> dict[str, Any]:
        path = self.path_for(artifact_name)
        if not path.is_file():
            raise ArtifactError(f"artifact missing: {path}")
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ArtifactError(f"artifact is not valid JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ArtifactError(f"artifact root must be object: {path}")
        return payload

    def write(self, artifact_name: str, payload: Mapping[str, Any]) -> Path:
        path = self.path_for(artifact_name)
        data = _with_schema(payload)
        _atomic_write_json(path, data)
        return path

    def write_context_update(self, artifacts: Mapping[str, Mapping[str, Any]]) -> list[Path]:
        updates = [
            (artifact_name, self.path_for(artifact_name), artifacts[artifact_name])
            for artifact_name in CORE_ARTIFACT_ORDER
            if artifact_name in artifacts
        ]
        snapshots = {
            path: path.read_bytes() if path.is_file() else None
            for _, path, _ in updates
        }
        written: list[Path] = []
        try:
            for artifact_name, _, payload in updates:
                written.append(self.write(artifact_name, payload))
            return written
        except Exception:
            for path in reversed(written):
                snapshot = snapshots[path]
                if snapshot is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(path, snapshot)
            raise

    def missing_artifacts(self, required: list[str] | tuple[str, ...]) -> list[str]:
        return [name for name in required if not self.path_for(name).is_file()]


def build_section_manifest(sections: list[Any]) -> dict[str, Any]:
    """Build a minimal ``section_manifest.json`` payload.

    Used by tests and initial setup paths. The production entry builder
    is ``spec_grag.core._section_manifest_entry`` which adds audit
    fields. Schema per section::

        source_section_id   — 一次 key
        source_hash         — raw body の SHA-256 (file integrity)
        semantic_hash       — whitespace 正規化後の SHA-256 (LLM cache key)
        heading_path        — 見出し親子チェーン list[str]
        chapter_id          — 章 ID
        source_span         — {start_line, end_line, start_offset, end_offset}
        llm_provider        — 監査用 (audit)
        llm_generation_status — success / failed / skipped (audit)
        last_prompt_version — cache 整合確認用 (audit)
        generated_at        — 監査用 (audit)
    """

    return {
        "sections": [_jsonable(section) for section in sections],
    }


def build_empty_chapter_anchors(sections: list[Any]) -> dict[str, Any]:
    chapters: dict[str, dict[str, Any]] = {}
    for section in sections:
        value = _jsonable(section)
        chapter_id = value["chapter_id"]
        entry = chapters.setdefault(
            chapter_id,
            {
                "chapter_id": chapter_id,
                "summary": "",
                "key_topics": [],
                "important_sections": [],
                "search_keys": [],
                "notes": [],
                "source_section_ids": [],
                "generated_at": None,
            },
        )
        entry["source_section_ids"].append(value["source_section_id"])
    return {"chapters": list(chapters.values())}


def _with_schema(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data.setdefault("schema_version", SCHEMA_VERSION)
    return _jsonable(data)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".rollback.tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
