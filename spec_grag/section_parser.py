"""Markdown section parser for Source Specs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SourceSpan:
    start_line: int
    end_line: int
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class Section:
    section_id: str
    source_section_id: str
    stable_section_uid: str
    source_document_id: str
    heading_path: list[str]
    heading_level: int
    source_span: SourceSpan
    source_hash: str
    semantic_hash: str
    chapter_id: str
    text: str


def parse_markdown_sections(
    text: str,
    *,
    source_path: str | Path,
    max_heading_level: int = 4,
) -> list[Section]:
    if max_heading_level < 1 or max_heading_level > 6:
        raise ValueError("max_heading_level must be between 1 and 6")

    document_id = _document_id(source_path)
    lines = text.splitlines(keepends=True)
    line_starts = _line_offsets(lines)
    boundaries = _section_boundaries(lines, max_heading_level)

    if not boundaries:
        return [
            _build_section(
                document_id=document_id,
                ordinal=1,
                heading_path=[],
                heading_level=0,
                lines=lines,
                line_starts=line_starts,
                start_line=1,
                end_line=max(1, len(lines)),
                chapter_id=_chapter_id(document_id, []),
            )
        ]

    sections: list[Section] = []
    active_headings: dict[int, str] = {}
    chapter_id = ""
    for index, (line_index, level, heading) in enumerate(boundaries):
        for old_level in list(active_headings):
            if old_level >= level:
                del active_headings[old_level]
        active_headings[level] = heading
        heading_path = [active_headings[key] for key in sorted(active_headings)]
        if level == 1 or not chapter_id:
            chapter_id = _chapter_id(document_id, heading_path[:1] or [heading])

        next_line_index = (
            boundaries[index + 1][0]
            if index + 1 < len(boundaries)
            else len(lines)
        )
        section_lines = lines[line_index + 1 : next_line_index]
        sections.append(
            _build_section(
                document_id=document_id,
                ordinal=index + 1,
                heading_path=heading_path,
                heading_level=level,
                lines=section_lines,
                line_starts=line_starts,
                start_line=line_index + 1,
                end_line=max(line_index + 1, next_line_index),
                chapter_id=chapter_id,
                heading_line_offset=line_starts[line_index],
                body_start_offset=line_starts[line_index + 1]
                if line_index + 1 < len(line_starts)
                else len("".join(lines)),
            )
        )
    return sections


def parse_markdown_file(
    path: str | Path,
    *,
    max_heading_level: int = 4,
) -> list[Section]:
    source_path = Path(path)
    return parse_markdown_sections(
        source_path.read_text(),
        source_path=source_path,
        max_heading_level=max_heading_level,
    )


def _section_boundaries(lines: list[str], max_heading_level: int) -> list[tuple[int, int, str]]:
    boundaries: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.rstrip("\n\r"))
        if not match:
            continue
        level = len(match.group(1))
        if level <= max_heading_level:
            boundaries.append((index, level, match.group(2).strip()))
    return boundaries


def _build_section(
    *,
    document_id: str,
    ordinal: int,
    heading_path: list[str],
    heading_level: int,
    lines: list[str],
    line_starts: list[int],
    start_line: int,
    end_line: int,
    chapter_id: str,
    heading_line_offset: int | None = None,
    body_start_offset: int | None = None,
) -> Section:
    body = "".join(lines)
    source_hash = _hash(body.encode())
    semantic_hash = _hash(_semantic_normalize(body).encode())
    slug = _slug(heading_path[-1] if heading_path else "document")
    section_id = f"{document_id}#{ordinal:04d}-{slug}"
    stable_seed = f"{document_id}\n{ordinal:04d}"
    stable_section_uid = _hash(stable_seed.encode())[:16]
    if body_start_offset is None:
        start_offset = line_starts[start_line - 1] if line_starts else 0
    else:
        start_offset = body_start_offset
    end_offset = start_offset + len(body)
    if heading_line_offset is not None:
        start_offset = body_start_offset if body_start_offset is not None else heading_line_offset
    return Section(
        section_id=section_id,
        source_section_id=section_id,
        stable_section_uid=stable_section_uid,
        source_document_id=document_id,
        heading_path=heading_path,
        heading_level=heading_level,
        source_span=SourceSpan(
            start_line=start_line,
            end_line=end_line,
            start_offset=start_offset,
            end_offset=end_offset,
        ),
        source_hash=source_hash,
        semantic_hash=semantic_hash,
        chapter_id=chapter_id,
        text=body,
    )


def _line_offsets(lines: list[str]) -> list[int]:
    offsets: list[int] = []
    current = 0
    for line in lines:
        offsets.append(current)
        current += len(line)
    return offsets


def _document_id(path: str | Path) -> str:
    normalized = str(Path(path).as_posix()).strip("/")
    return normalized or "document"


def _chapter_id(document_id: str, heading_path: list[str]) -> str:
    chapter = heading_path[0] if heading_path else "document"
    return f"{document_id}#{_slug(chapter)}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_一-龯ぁ-んァ-ンー]+", "-", value.strip()).strip("-")
    return slug.lower() or "section"


def _semantic_normalize(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
