"""Source manifest and deterministic Markdown section reconciliation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
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
    stable_section_uid: str | None = None
    section_aliases: list[str] = Field(default_factory=list)
    heading_path: str
    heading_start_line: int
    source_hash: str
    raw_hash: str | None = None
    semantic_hash: str | None = None
    body_semantic_hash: str | None = None
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

    def by_stable_section_uid(self) -> dict[str, SourceManifestEntry]:
        return {
            entry.stable_section_uid: entry
            for entry in self.entries
            if entry.stable_section_uid
        }


class ManifestSectionRename(StrictModel):
    stable_section_uid: str
    previous_section_id: str
    current_section_id: str


class ManifestReconciliation(StrictModel):
    unchanged_section_ids: list[str] = Field(default_factory=list)
    format_only_section_ids: list[str] = Field(default_factory=list)
    changed_section_ids: list[str] = Field(default_factory=list)
    added_section_ids: list[str] = Field(default_factory=list)
    removed_section_ids: list[str] = Field(default_factory=list)
    renamed_sections: list[ManifestSectionRename] = Field(default_factory=list)
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
    document_texts: Mapping[str, str] | None = None,
) -> SourceManifest:
    entries: list[SourceManifestEntry] = []
    root = project_root.resolve()
    for source_path in sorted(Path(path) for path in source_paths):
        resolved = source_path.resolve()
        document_id = _document_id(root, resolved)
        text = None
        if document_texts is not None:
            text = document_texts.get(document_id)
        entries.extend(
            _entries_for_markdown_file(
                root,
                resolved,
                section_max_heading_level=section_max_heading_level,
                text=text,
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
    current = inherit_stable_section_identities(previous, current)
    previous_entries = [_ensure_stable_identity(entry) for entry in previous.entries]
    current_entries = [_ensure_stable_identity(entry) for entry in current.entries]
    previous_by_stable, previous_ambiguous = _unique_entries_by_stable_section_uid(
        previous_entries
    )
    current_by_stable, current_ambiguous = _unique_entries_by_stable_section_uid(
        current_entries
    )
    previous_stable_ids = set(previous_by_stable)
    current_stable_ids = set(current_by_stable)
    parser_changed = bool(previous.entries) and (
        previous.parser_name != current.parser_name
        or previous.parser_version != current.parser_version
    )

    unchanged: list[str] = []
    format_only: list[str] = []
    changed: list[str] = []
    renamed: list[ManifestSectionRename] = []
    for stable_section_uid in sorted(previous_stable_ids & current_stable_ids):
        previous_entry = previous_by_stable[stable_section_uid]
        current_entry = current_by_stable[stable_section_uid]
        if parser_changed:
            changed.append(current_entry.section_id)
            continue
        if previous_entry.section_id != current_entry.section_id:
            renamed.append(
                ManifestSectionRename(
                    stable_section_uid=stable_section_uid,
                    previous_section_id=previous_entry.section_id,
                    current_section_id=current_entry.section_id,
                )
            )
            if _entry_body_semantic_hash(previous_entry) == _entry_body_semantic_hash(
                current_entry
            ):
                continue
            changed.append(current_entry.section_id)
            continue
        previous_raw_hash = _entry_raw_hash(previous_entry)
        current_raw_hash = _entry_raw_hash(current_entry)
        previous_semantic_hash = _entry_semantic_hash(previous_entry)
        current_semantic_hash = _entry_semantic_hash(current_entry)
        if previous_raw_hash == current_raw_hash:
            unchanged.append(current_entry.section_id)
        elif previous_semantic_hash == current_semantic_hash:
            format_only.append(current_entry.section_id)
        else:
            changed.append(current_entry.section_id)
    added = sorted(
        [
            *(
                current_by_stable[stable_id].section_id
                for stable_id in current_stable_ids - previous_stable_ids
            ),
            *(entry.section_id for entry in current_ambiguous),
        ]
    )
    removed = sorted(
        [
            *(
                previous_by_stable[stable_id].section_id
                for stable_id in previous_stable_ids - current_stable_ids
            ),
            *(entry.section_id for entry in previous_ambiguous),
        ]
    )

    current_by_id = {entry.section_id: entry for entry in current_entries}
    previous_by_id = {entry.section_id: entry for entry in previous_entries}

    affected_chapters = {
        current_by_id[section_id].chapter_id for section_id in added + changed
    } | {previous_by_id[section_id].chapter_id for section_id in removed} | {
        current_by_id[item.current_section_id].chapter_id for item in renamed
    } | {previous_by_id[item.previous_section_id].chapter_id for item in renamed}
    structure_changed_chapters = {
        current_by_id[section_id].chapter_id for section_id in added
    } | {previous_by_id[section_id].chapter_id for section_id in removed} | {
        current_by_id[item.current_section_id].chapter_id for item in renamed
    } | {previous_by_id[item.previous_section_id].chapter_id for item in renamed}

    return ManifestReconciliation(
        unchanged_section_ids=unchanged,
        format_only_section_ids=format_only,
        changed_section_ids=changed,
        added_section_ids=added,
        removed_section_ids=removed,
        renamed_sections=sorted(
            renamed,
            key=lambda item: (item.previous_section_id, item.current_section_id),
        ),
        structure_changed_chapter_ids=sorted(structure_changed_chapters),
        affected_chapter_ids=sorted(affected_chapters),
    )


def inherit_stable_section_identities(
    previous: SourceManifest, current: SourceManifest
) -> SourceManifest:
    if not current.entries:
        return current

    previous_by_id = previous.by_section_id()
    previous_by_alias = _unique_previous_entries_by_alias(previous.entries)
    previous_by_body = _unique_previous_entries_by_body_semantic_hash(previous.entries)
    duplicated_previous_stable_uids = _duplicated_stable_section_uids(previous.entries)
    current_body_counts = Counter(
        key
        for entry in current.entries
        if (key := _body_semantic_match_key(entry)) is not None
    )
    consumed_previous_keys: set[str] = set()
    inherited_entries: list[SourceManifestEntry] = []

    for entry in current.entries:
        previous_entry = previous_by_id.get(entry.section_id)
        if previous_entry is None:
            previous_entry = previous_by_alias.get(entry.section_id)
        if previous_entry is None:
            body_key = _body_semantic_match_key(entry)
            if body_key is not None and current_body_counts[body_key] == 1:
                candidate = previous_by_body.get(body_key)
                candidate_key = _previous_identity_key(candidate)
                if candidate is not None and candidate_key not in consumed_previous_keys:
                    previous_entry = candidate

        if previous_entry is None:
            inherited_entries.append(_ensure_stable_identity(entry))
            continue

        consumed_previous_keys.add(_previous_identity_key(previous_entry))
        previous_stable_uid = previous_entry.stable_section_uid
        if previous_stable_uid in duplicated_previous_stable_uids:
            previous_stable_uid = None
        inherited_entries.append(
            entry.model_copy(
                update={
                    "stable_section_uid": previous_stable_uid
                    or entry.stable_section_uid
                    or stable_section_uid_for(entry.document_id, entry.section_id),
                    "section_aliases": _merged_section_aliases(previous_entry, entry),
                }
            )
        )

    return current.model_copy(update={"entries": inherited_entries})


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

    current = inherit_stable_section_identities(previous, current)

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
    text: str | None = None,
) -> list[SourceManifestEntry]:
    resolved = source_path.resolve()
    document_id = _document_id(project_root, resolved)
    if text is None:
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
    body_semantic_hash = _sha256_text(
        _semantic_normalize_markdown(_section_body_without_heading(raw_text))
    )
    return SourceManifestEntry(
        document_id=document_id,
        chapter_id=chapter_id,
        section_id=section_id,
        stable_section_uid=stable_section_uid_for(document_id, section_id),
        section_aliases=[section_id],
        heading_path=heading_path,
        heading_start_line=heading_start_line,
        source_hash=raw_hash,
        raw_hash=raw_hash,
        semantic_hash=semantic_hash,
        body_semantic_hash=body_semantic_hash,
    )


def stable_section_uid_for(document_id: str, section_id: str) -> str:
    digest = _sha256_text(f"stable-section-v2\n{document_id}\n{section_id}")[:24]
    return f"stable-section:{digest}"


def _section_body_without_heading(section_text: str) -> str:
    lines = _normalize_line_endings(section_text).splitlines(keepends=True)
    if lines and lines[0].lstrip().startswith("#"):
        return "".join(lines[1:])
    if len(lines) >= 2 and re.match(r"^[ \t]*(=+|-+)[ \t]*$", lines[1]):
        return "".join(lines[2:])
    return "".join(lines)


def _ensure_stable_identity(entry: SourceManifestEntry) -> SourceManifestEntry:
    updates: dict[str, object] = {}
    if not entry.stable_section_uid:
        updates["stable_section_uid"] = stable_section_uid_for(
            entry.document_id, entry.section_id
        )
    aliases = _normalized_aliases([*entry.section_aliases, entry.section_id])
    if aliases != entry.section_aliases:
        updates["section_aliases"] = aliases
    if not updates:
        return entry
    return entry.model_copy(update=updates)


def _unique_previous_entries_by_alias(
    entries: Iterable[SourceManifestEntry],
) -> dict[str, SourceManifestEntry]:
    by_alias: dict[str, SourceManifestEntry] = {}
    ambiguous: set[str] = set()
    for entry in entries:
        for alias in _normalized_aliases([entry.section_id, *entry.section_aliases]):
            if alias in by_alias and by_alias[alias] != entry:
                ambiguous.add(alias)
                continue
            by_alias[alias] = entry
    for alias in ambiguous:
        by_alias.pop(alias, None)
    return by_alias


def _unique_entries_by_stable_section_uid(
    entries: Iterable[SourceManifestEntry],
) -> tuple[dict[str, SourceManifestEntry], list[SourceManifestEntry]]:
    by_uid: dict[str, SourceManifestEntry] = {}
    ambiguous_uids = _duplicated_stable_section_uids(entries)
    ambiguous_entries: list[SourceManifestEntry] = []
    for entry in entries:
        uid = entry.stable_section_uid
        if not uid:
            ambiguous_entries.append(entry)
            continue
        if uid in ambiguous_uids:
            ambiguous_entries.append(entry)
            continue
        by_uid[uid] = entry
    return by_uid, ambiguous_entries


def _duplicated_stable_section_uids(
    entries: Iterable[SourceManifestEntry],
) -> set[str]:
    counts = Counter(
        entry.stable_section_uid for entry in entries if entry.stable_section_uid
    )
    return {uid for uid, count in counts.items() if count > 1}


def _unique_previous_entries_by_body_semantic_hash(
    entries: Iterable[SourceManifestEntry],
) -> dict[tuple[str, str], SourceManifestEntry]:
    by_hash: dict[tuple[str, str], SourceManifestEntry] = {}
    ambiguous: set[tuple[str, str]] = set()
    for entry in entries:
        key = _body_semantic_match_key(entry)
        if key is None:
            continue
        if key in by_hash and by_hash[key] != entry:
            ambiguous.add(key)
            continue
        by_hash[key] = entry
    for key in ambiguous:
        by_hash.pop(key, None)
    return by_hash


def _body_semantic_match_key(entry: SourceManifestEntry) -> tuple[str, str] | None:
    body_hash = entry.body_semantic_hash
    if not body_hash:
        return None
    return (entry.document_id, body_hash)


def _entry_body_semantic_hash(entry: SourceManifestEntry) -> str:
    return entry.body_semantic_hash or entry.semantic_hash or entry.source_hash


def _previous_identity_key(entry: SourceManifestEntry | None) -> str:
    if entry is None:
        return ""
    return entry.stable_section_uid or entry.section_id


def _merged_section_aliases(
    previous_entry: SourceManifestEntry, current_entry: SourceManifestEntry
) -> list[str]:
    return _normalized_aliases(
        [
            previous_entry.section_id,
            *previous_entry.section_aliases,
            current_entry.section_id,
            *current_entry.section_aliases,
        ]
    )


def _normalized_aliases(values: Iterable[str]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        alias = str(value).strip()
        if not alias or alias in seen:
            continue
        aliases.append(alias)
        seen.add(alias)
    return aliases


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
