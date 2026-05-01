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
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import Field

from spec_grag.protocol import StrictModel

try:
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover - dependency is declared, fallback is defensive.
    MarkdownIt = None  # type: ignore[assignment]


MANIFEST_VERSION = "1"
MARKDOWN_PARSER_NAME = "markdown-it-py:commonmark"
try:
    MARKDOWN_PARSER_VERSION = version("markdown-it-py")
except PackageNotFoundError:  # pragma: no cover - dependency is declared.
    MARKDOWN_PARSER_VERSION = "unknown"


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
    raw_hash: str | None = None
    semantic_hash: str | None = None
    scanned_at: str | None = None
    extract_run_id: str | None = None
    extractor_versions: dict[str, str] = Field(default_factory=dict)


class SourceManifest(StrictModel):
    version: str = MANIFEST_VERSION
    parser_name: str = ""
    parser_version: str = ""
    generated_at: str | None = None
    entries: list[SourceManifestEntry] = Field(default_factory=list)

    def by_section_id(self) -> dict[str, SourceManifestEntry]:
        return {entry.section_id: entry for entry in self.entries}


class ManifestReconciliation(StrictModel):
    unchanged_section_ids: list[str] = Field(default_factory=list)
    format_only_section_ids: list[str] = Field(default_factory=list)
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
    section_max_heading_level: int = 6,
) -> SourceManifest:
    entries: list[SourceManifestEntry] = []
    root = project_root.resolve()
    for source_path in sorted(Path(path) for path in source_paths):
        entries.extend(
            _entries_for_markdown_file(
                root,
                source_path,
                section_max_heading_level=section_max_heading_level,
            )
        )
    return SourceManifest(
        parser_name=MARKDOWN_PARSER_NAME,
        parser_version=MARKDOWN_PARSER_VERSION,
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
    parser_changed = bool(previous.entries) and (
        previous.parser_name != current.parser_name
        or previous.parser_version != current.parser_version
    )

    unchanged: list[str] = []
    format_only: list[str] = []
    changed: list[str] = []
    for section_id in sorted(previous_ids & current_ids):
        previous_entry = previous_by_id[section_id]
        current_entry = current_by_id[section_id]
        if parser_changed:
            changed.append(section_id)
            continue
        previous_raw_hash = _entry_raw_hash(previous_entry)
        current_raw_hash = _entry_raw_hash(current_entry)
        previous_semantic_hash = _entry_semantic_hash(previous_entry)
        current_semantic_hash = _entry_semantic_hash(current_entry)
        if previous_raw_hash == current_raw_hash:
            unchanged.append(section_id)
        elif previous_semantic_hash == current_semantic_hash:
            format_only.append(section_id)
        else:
            changed.append(section_id)
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
        format_only_section_ids=format_only,
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
            parser_name=current.parser_name,
            parser_version=current.parser_version,
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
        parser_name=current.parser_name,
        parser_version=current.parser_version,
        generated_at=scanned_at,
        entries=sorted(
            next_by_id.values(), key=lambda e: (e.document_id, e.heading_start_line, e.section_id)
        ),
    )


def _entries_for_markdown_file(
    project_root: Path,
    source_path: Path,
    *,
    section_max_heading_level: int,
) -> list[SourceManifestEntry]:
    resolved = source_path.resolve()
    document_id = _document_id(project_root, resolved)
    text = resolved.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    headings = [
        heading
        for heading in _extract_headings(lines)
        if heading.level <= section_max_heading_level
    ]

    if not headings:
        return [
            _manifest_entry(
                document_id=document_id,
                chapter_id=f"{document_id}#root",
                section_id=f"{document_id}#root",
                heading_path=Path(document_id).stem,
                heading_start_line=1,
                section_text=text,
            )
        ]

    entries: list[SourceManifestEntry] = []
    used_section_ids: dict[str, int] = {}

    first_heading = headings[0]
    if "".join(lines[: first_heading.content_start - 1]).strip():
        preamble = "".join(lines[: first_heading.content_start - 1])
        entries.append(
            _manifest_entry(
                document_id=document_id,
                chapter_id=f"{document_id}#root",
                section_id=f"{document_id}#preamble",
                heading_path=f"{Path(document_id).stem} / preamble",
                heading_start_line=1,
                section_text=preamble,
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
            _manifest_entry(
                document_id=document_id,
                chapter_id=chapter_id,
                section_id=section_id,
                heading_path=heading_path,
                heading_start_line=heading.line_no,
                section_text=section_text,
            )
        )

    return entries


def _extract_headings(lines: list[str]) -> list[_Heading]:
    if MarkdownIt is not None:
        return _extract_headings_commonmark(lines)
    return _extract_headings_fallback(lines)


def _extract_headings_commonmark(lines: list[str]) -> list[_Heading]:
    md = MarkdownIt("commonmark")
    tokens = md.parse("".join(lines))
    headings: list[_Heading] = []
    for token_index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        # SPEC-grag source sections are document-level sections. Headings inside
        # blockquotes/list items are valid Markdown, but should not split the
        # source spec manifest.
        if token.level != 0:
            continue
        if not token.tag.startswith("h") or not token.tag[1:].isdigit():
            continue
        if not token.map:
            continue
        inline = tokens[token_index + 1] if token_index + 1 < len(tokens) else None
        title = inline.content.strip() if inline is not None and inline.type == "inline" else ""
        if not title:
            continue
        headings.append(
            _Heading(
                level=int(token.tag[1:]),
                title=title,
                line_no=token.map[0] + 1,
                content_start=token.map[0] + 1,
            )
        )
    return headings


def _extract_headings_fallback(lines: list[str]) -> list[_Heading]:
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


def _manifest_entry(
    *,
    document_id: str,
    chapter_id: str,
    section_id: str,
    heading_path: str,
    heading_start_line: int,
    section_text: str,
) -> SourceManifestEntry:
    raw_text = _normalize_line_endings(section_text)
    raw_hash = _sha256_text(raw_text)
    semantic_hash = _sha256_text(_semantic_normalize_markdown(raw_text))
    return SourceManifestEntry(
        document_id=document_id,
        chapter_id=chapter_id,
        section_id=section_id,
        heading_path=heading_path,
        heading_start_line=heading_start_line,
        source_hash=raw_hash,
        raw_hash=raw_hash,
        semantic_hash=semantic_hash,
    )


def _entry_raw_hash(entry: SourceManifestEntry) -> str:
    return entry.raw_hash or entry.source_hash


def _entry_semantic_hash(entry: SourceManifestEntry) -> str:
    return entry.semantic_hash or entry.source_hash


def _semantic_normalize_markdown(text: str) -> str:
    lines = _normalize_line_endings(text).split("\n")
    output: list[str] = []
    prose_parts: list[str] = []
    in_fence = False
    fence_marker = ""

    def flush_prose() -> None:
        if prose_parts:
            output.append("TEXT:" + " ".join(prose_parts))
            prose_parts.clear()

    for line in lines:
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            flush_prose()
            marker = fence_match.group(1)
            output.append("FENCE:" + line.strip())
            if not in_fence:
                in_fence = True
                fence_marker = marker[:3]
            elif marker.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            continue

        if in_fence:
            output.append("CODE:" + line.rstrip())
            continue

        if line.startswith("    ") or line.startswith("\t"):
            flush_prose()
            output.append("INDENT_CODE:" + line.rstrip())
            continue

        stripped = line.strip()
        if not stripped:
            continue
        prose_parts.append(re.sub(r"\s+", " ", stripped))

    flush_prose()
    return "\n".join(output).strip()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slugify(text: str) -> str:
    lowered = text.strip().lower()
    normalized = "".join(
        char if char.isalnum() or char in "._-" else "-"
        for char in lowered
    ).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
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
