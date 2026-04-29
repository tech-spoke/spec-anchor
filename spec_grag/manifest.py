"""Source manifest and deterministic Markdown section reconciliation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from spec_grag.protocol import StrictModel


MANIFEST_VERSION = "1"


class ManifestUpdateStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILED = "failed"


class SourceManifestEntry(StrictModel):
    document_id: str
    chapter_id: str
    section_id: str
    heading_path: str
    heading_start_line: int
    source_hash: str
    scanned_at: str | None = None
    extract_run_id: str | None = None
    extractor_versions: dict[str, str] = Field(default_factory=dict)


class SourceManifest(StrictModel):
    version: str = MANIFEST_VERSION
    generated_at: str | None = None
    entries: list[SourceManifestEntry] = Field(default_factory=list)

    def by_section_id(self) -> dict[str, SourceManifestEntry]:
        return {entry.section_id: entry for entry in self.entries}


class ManifestReconciliation(StrictModel):
    unchanged_section_ids: list[str] = Field(default_factory=list)
    changed_section_ids: list[str] = Field(default_factory=list)
    added_section_ids: list[str] = Field(default_factory=list)
    removed_section_ids: list[str] = Field(default_factory=list)
    structure_changed_chapter_ids: list[str] = Field(default_factory=list)
    affected_chapter_ids: list[str] = Field(default_factory=list)


class _Heading:
    def __init__(self, level: int, title: str, line_no: int, content_start: int) -> None:
        self.level = level
        self.title = title
        self.line_no = line_no
        self.content_start = content_start


_ATX_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]*(```+|~~~+)")
_SLUG_CHARS_RE = re.compile(r"[^a-z0-9._-]+")


def build_current_section_manifest(
    project_root: Path,
    source_paths: Iterable[Path],
    *,
    generated_at: str | None = None,
) -> SourceManifest:
    entries: list[SourceManifestEntry] = []
    root = project_root.resolve()
    for source_path in sorted(Path(path) for path in source_paths):
        entries.extend(_entries_for_markdown_file(root, source_path))
    return SourceManifest(
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        entries=entries,
    )


def reconcile_manifests(
    previous: SourceManifest, current: SourceManifest
) -> ManifestReconciliation:
    previous_by_id = previous.by_section_id()
    current_by_id = current.by_section_id()
    previous_ids = set(previous_by_id)
    current_ids = set(current_by_id)

    unchanged = sorted(
        section_id
        for section_id in previous_ids & current_ids
        if previous_by_id[section_id].source_hash == current_by_id[section_id].source_hash
    )
    changed = sorted(
        section_id
        for section_id in previous_ids & current_ids
        if previous_by_id[section_id].source_hash != current_by_id[section_id].source_hash
    )
    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)

    affected_chapters = {
        current_by_id[section_id].chapter_id for section_id in added + changed
    } | {previous_by_id[section_id].chapter_id for section_id in removed}
    structure_changed_chapters = {
        current_by_id[section_id].chapter_id for section_id in added
    } | {previous_by_id[section_id].chapter_id for section_id in removed}

    return ManifestReconciliation(
        unchanged_section_ids=unchanged,
        changed_section_ids=changed,
        added_section_ids=added,
        removed_section_ids=removed,
        structure_changed_chapter_ids=sorted(structure_changed_chapters),
        affected_chapter_ids=sorted(affected_chapters),
    )


def load_source_manifest(path: Path) -> SourceManifest:
    if not path.exists():
        return SourceManifest(generated_at=None, entries=[])
    return SourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def write_source_manifest_atomic(path: Path, manifest: SourceManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump_json(indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def next_source_manifest(
    previous: SourceManifest,
    current: SourceManifest,
    *,
    status: ManifestUpdateStatus,
    scanned_at: str,
    extract_run_id: str,
    extractor_versions: dict[str, str] | None = None,
    successful_section_ids: set[str] | None = None,
    failed_section_ids: set[str] | None = None,
    failed_removed_section_ids: set[str] | None = None,
) -> SourceManifest:
    if status in {ManifestUpdateStatus.FAILED, ManifestUpdateStatus.BLOCKED}:
        return previous

    versions = extractor_versions or {}
    if status == ManifestUpdateStatus.OK:
        return SourceManifest(
            generated_at=scanned_at,
            entries=[
                _with_run_metadata(entry, scanned_at, extract_run_id, versions)
                for entry in current.entries
            ],
        )

    previous_by_id = previous.by_section_id()
    current_by_id = current.by_section_id()
    failed = failed_section_ids or set()
    successful = successful_section_ids
    if successful is None:
        successful = set(current_by_id) - failed
    failed_removed = failed_removed_section_ids or set()

    next_by_id = dict(previous_by_id)
    for section_id, entry in current_by_id.items():
        if section_id in successful:
            next_by_id[section_id] = _with_run_metadata(
                entry, scanned_at, extract_run_id, versions
            )
        elif section_id not in previous_by_id:
            next_by_id.pop(section_id, None)

    for section_id in set(previous_by_id) - set(current_by_id):
        if section_id not in failed_removed:
            next_by_id.pop(section_id, None)

    return SourceManifest(
        generated_at=scanned_at,
        entries=sorted(
            next_by_id.values(), key=lambda e: (e.document_id, e.heading_start_line, e.section_id)
        ),
    )


def _entries_for_markdown_file(project_root: Path, source_path: Path) -> list[SourceManifestEntry]:
    resolved = source_path.resolve()
    document_id = _document_id(project_root, resolved)
    text = resolved.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    headings = _extract_headings(lines)

    if not headings:
        body = _normalize_line_endings(text)
        return [
            SourceManifestEntry(
                document_id=document_id,
                chapter_id=f"{document_id}#root",
                section_id=f"{document_id}#root",
                heading_path=Path(document_id).stem,
                heading_start_line=1,
                source_hash=_sha256_text(body),
            )
        ]

    entries: list[SourceManifestEntry] = []
    used_section_ids: dict[str, int] = {}

    first_heading = headings[0]
    if "".join(lines[: first_heading.content_start - 1]).strip():
        preamble = "".join(lines[: first_heading.content_start - 1])
        entries.append(
            SourceManifestEntry(
                document_id=document_id,
                chapter_id=f"{document_id}#root",
                section_id=f"{document_id}#preamble",
                heading_path=f"{Path(document_id).stem} / preamble",
                heading_start_line=1,
                source_hash=_sha256_text(_normalize_line_endings(preamble)),
            )
        )

    heading_stack: list[_Heading] = []
    chapter_slug = "root"
    chapter_id = f"{document_id}#{chapter_slug}"
    for index, heading in enumerate(headings):
        while heading_stack and heading_stack[-1].level >= heading.level:
            heading_stack.pop()
        heading_stack.append(heading)

        if heading.level == 1:
            chapter_slug = _slugify(heading.title)
            chapter_id = f"{document_id}#{chapter_slug}"

        next_start = headings[index + 1].content_start - 1 if index + 1 < len(headings) else len(lines)
        section_text = "".join(lines[heading.content_start - 1 : next_start])
        heading_path = " / ".join(item.title for item in heading_stack)
        base_section_id = f"{document_id}#{_slugify(heading_path)}"
        section_id = _dedupe_section_id(base_section_id, used_section_ids)

        entries.append(
            SourceManifestEntry(
                document_id=document_id,
                chapter_id=chapter_id,
                section_id=section_id,
                heading_path=heading_path,
                heading_start_line=heading.line_no,
                source_hash=_sha256_text(_normalize_line_endings(section_text)),
            )
        )

    return entries


def _extract_headings(lines: list[str]) -> list[_Heading]:
    headings: list[_Heading] = []
    in_fence = False
    fence_marker = ""
    for index, line in enumerate(lines, start=1):
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker[:3]
            elif marker.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue

        match = _ATX_HEADING_RE.match(line.rstrip("\n\r"))
        if not match:
            continue
        title = match.group(2).strip()
        if title:
            headings.append(
                _Heading(
                    level=len(match.group(1)),
                    title=title,
                    line_no=index,
                    content_start=index,
                )
            )
    return headings


def _document_id(project_root: Path, source_path: Path) -> str:
    try:
        return source_path.relative_to(project_root).as_posix()
    except ValueError:
        return source_path.as_posix()


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slugify(text: str) -> str:
    lowered = text.strip().lower()
    normalized = _SLUG_CHARS_RE.sub("-", lowered).strip("-")
    return normalized or "section"


def _dedupe_section_id(base_section_id: str, used: dict[str, int]) -> str:
    count = used.get(base_section_id, 0) + 1
    used[base_section_id] = count
    if count == 1:
        return base_section_id
    return f"{base_section_id}-{count}"


def _with_run_metadata(
    entry: SourceManifestEntry,
    scanned_at: str,
    extract_run_id: str,
    extractor_versions: dict[str, str],
) -> SourceManifestEntry:
    return entry.model_copy(
        update={
            "scanned_at": scanned_at,
            "extract_run_id": extract_run_id,
            "extractor_versions": dict(extractor_versions),
        }
    )


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
