"""Context artifact read/write helpers."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ARTIFACT_FILENAMES = {
    "section_manifest": "section_manifest.json",
    "section_metadata": "section_metadata.json",
    "conflict_review_items": "conflict_review_items.json",
    "chapter_anchors": "chapter_anchors.json",
    "source_chunks": "source_chunks.json",
    "retrieval_index_revision": "retrieval_index_revision.json",
    "freshness": "freshness.json",
}
CORE_ARTIFACT_ORDER = (
    "section_manifest",
    "section_metadata",
    "conflict_review_items",
    "chapter_anchors",
    "source_chunks",
    "retrieval_index_revision",
    "freshness",
)


class ArtifactError(Exception):
    """Raised when a context artifact cannot be read or written."""


class ContextArtifactStore:
    def __init__(self, context_dir: str | Path) -> None:
        self.context_dir = Path(context_dir)

    def path_for(self, artifact_name: str) -> Path:
        try:
            filename = ARTIFACT_FILENAMES[artifact_name]
        except KeyError as exc:
            raise ArtifactError(f"unknown artifact: {artifact_name}") from exc
        return self.context_dir / filename

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
    return {
        "sections": [_jsonable(section) for section in sections],
    }


def build_empty_section_metadata(sections: list[Any]) -> dict[str, Any]:
    entries = []
    for section in sections:
        value = _jsonable(section)
        entries.append(
            {
                "section_id": value["section_id"],
                "stable_section_uid": value["stable_section_uid"],
                "source_document_id": value["source_document_id"],
                "heading_path": value["heading_path"],
                "summary": "",
                "search_keys": [],
                "identifiers": [],
                "related_sections": [],
                "metadata_version": 1,
                "source_hash": value["source_hash"],
                "semantic_hash": value["semantic_hash"],
                "generated_at": None,
            }
        )
    return {"sections": entries}


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
