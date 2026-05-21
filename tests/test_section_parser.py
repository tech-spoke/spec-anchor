"""Section Parser contract tests.

These tests pin the Source Specs sectioning contract before the builder
implementation exists.  Section objects may be dictionaries or dataclasses;
the assertions focus on the public fields promised by the design docs.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parse_sections(
    markdown: str,
    *,
    max_heading_level: int = 4,
    source_document_id: str = "docs/spec/sample.md",
) -> list[Any]:
    module = importlib.import_module("spec_anchor.section_parser")
    parse_markdown_sections = getattr(module, "parse_markdown_sections", None)
    assert callable(
        parse_markdown_sections
    ), "spec_anchor.section_parser.parse_markdown_sections(...) is required"
    signature = inspect.signature(parse_markdown_sections)
    if "source_document_id" in signature.parameters:
        sections = parse_markdown_sections(
            markdown,
            source_document_id=source_document_id,
            max_heading_level=max_heading_level,
        )
    else:
        sections = parse_markdown_sections(
            markdown,
            source_path=source_document_id,
            max_heading_level=max_heading_level,
        )
    assert isinstance(sections, list)
    return sections


def _get(section: Any, field: str) -> Any:
    if isinstance(section, dict):
        return section[field]
    return getattr(section, field)


def _optional(section: Any, *fields: str) -> Any:
    for field in fields:
        if isinstance(section, dict) and field in section:
            return section[field]
        if not isinstance(section, dict) and hasattr(section, field):
            return getattr(section, field)
    pytest.fail(f"section must expose one of: {', '.join(fields)}")


def _body(section: Any) -> str:
    value = _optional(section, "body", "content", "text", "source_text")
    assert isinstance(value, str)
    return value


def _heading_path(section: Any) -> list[str]:
    value = _get(section, "heading_path")
    assert isinstance(value, list)
    return value


def _span_value(source_span: Any, field: str) -> Any:
    if isinstance(source_span, dict):
        return source_span[field]
    return getattr(source_span, field)


def _section_ids(sections: list[Any]) -> list[str]:
    return [_get(section, "section_id") for section in sections]


def test_t_u01_max_heading_level_4_sections_headings_through_level_4() -> None:
    sections = _parse_sections(
        """\
# Chapter
chapter body
## Feature
feature body
### Field group
field body
#### Image upload
image body
##### Internal helper
helper body
"""
    )

    assert len(sections) == 4
    assert [_heading_path(section) for section in sections] == [
        ["Chapter"],
        ["Chapter", "Feature"],
        ["Chapter", "Feature", "Field group"],
        ["Chapter", "Feature", "Field group", "Image upload"],
    ]
    assert "##### Internal helper" in _body(sections[-1])
    assert "helper body" in _body(sections[-1])


def test_t_u01_max_heading_level_2_merges_deeper_headings_into_parent() -> None:
    sections = _parse_sections(
        """\
# Chapter
chapter body
## Feature
feature body
### Field group
field body
#### Image upload
image body
""",
        max_heading_level=2,
    )

    assert len(sections) == 2
    assert _heading_path(sections[-1]) == ["Chapter", "Feature"]
    assert "### Field group" in _body(sections[-1])
    assert "#### Image upload" in _body(sections[-1])


def test_t_u01_max_heading_level_1_merges_lower_headings_into_chapter() -> None:
    sections = _parse_sections(
        """\
# Chapter
chapter body
## Feature
feature body
### Field group
field body
""",
        max_heading_level=1,
    )

    assert len(sections) == 1
    assert _heading_path(sections[0]) == ["Chapter"]
    assert "## Feature" in _body(sections[0])
    assert "### Field group" in _body(sections[0])


def test_t_u01_document_without_heading_becomes_single_root_section() -> None:
    sections = _parse_sections("intro line\nsecond line\n")

    assert len(sections) == 1
    assert _heading_path(sections[0]) == []
    assert _body(sections[0]) == "intro line\nsecond line\n"


def test_t_u01_heading_only_section_has_empty_body() -> None:
    sections = _parse_sections("# Empty section\n")

    assert len(sections) == 1
    assert _heading_path(sections[0]) == ["Empty section"]
    assert _body(sections[0]) == ""


def test_t_u01_duplicate_heading_text_gets_distinct_section_ids() -> None:
    sections = _parse_sections(
        """\
# API
first
# API
second
"""
    )

    assert [_heading_path(section) for section in sections] == [["API"], ["API"]]
    assert len(set(_section_ids(sections))) == 2


def test_t_u01_fenced_code_heading_text_is_not_a_section_boundary() -> None:
    sections = _parse_sections(
        """\
# API
before
```markdown
# Not a heading
```
## Details
after
"""
    )

    assert [_heading_path(section) for section in sections] == [
        ["API"],
        ["API", "Details"],
    ]
    assert "# Not a heading" in _body(sections[0])


def test_t_u01_setext_headings_are_section_boundaries() -> None:
    sections = _parse_sections(
        """\
認証設計
====
overview

セッション管理
----
details
"""
    )

    assert len(sections) == 2
    assert [_heading_path(section) for section in sections] == [
        ["認証設計"],
        ["認証設計", "セッション管理"],
    ]
    assert _body(sections[0]) == "overview\n\n"
    assert _body(sections[1]) == "details\n"


def test_t_u02_section_manifest_contains_required_fields_and_id_alias() -> None:
    section = _parse_sections(
        """\
# Chapter
chapter body
## Feature
feature body
""",
        source_document_id="docs/spec/core.md",
    )[1]

    for field in (
        "section_id",
        "source_section_id",
        "stable_section_uid",
        "source_document_id",
        "heading_path",
        "source_span",
        "source_hash",
        "semantic_hash",
        "chapter_id",
    ):
        value = _get(section, field)
        assert value is not None
        if isinstance(value, str):
            assert value

    assert _get(section, "section_id") == _get(section, "source_section_id")
    assert _get(section, "source_document_id") == "docs/spec/core.md"
    assert _get(section, "heading_path") == ["Chapter", "Feature"]

    source_span = _get(section, "source_span")
    assert _span_value(source_span, "start_line") <= _span_value(source_span, "end_line")


def test_t_u02_stable_section_uid_survives_heading_rename() -> None:
    before = _parse_sections(
        """\
# Chapter
chapter body
## Feature
same body
""",
        source_document_id="docs/spec/core.md",
    )
    after = _parse_sections(
        """\
# Chapter
chapter body
## Renamed Feature
same body
""",
        source_document_id="docs/spec/core.md",
    )

    assert _get(before[1], "section_id") != _get(after[1], "section_id")
    assert _get(before[1], "stable_section_uid") == _get(
        after[1],
        "stable_section_uid",
    )


def test_t_u02_japanese_and_mixed_headings_keep_unique_non_empty_ids() -> None:
    sections = _parse_sections(
        """\
# 認証設計
本文
## セッション管理 2
詳細
## 認証設計
重複
""",
        source_document_id="docs/spec/日本語.md",
    )

    ids = _section_ids(sections)

    assert ids == [
        "docs/spec/日本語.md#0001-認証設計",
        "docs/spec/日本語.md#0002-セッション管理-2",
        "docs/spec/日本語.md#0003-認証設計",
    ]
    assert len(set(ids)) == len(ids)
    assert all(_get(section, "source_hash") for section in sections)


def test_t_u02_hashes_distinguish_format_only_and_semantic_changes() -> None:
    base = _parse_sections("# Chapter\nAlpha beta\nGamma\n")[0]
    whitespace_only = _parse_sections("# Chapter\nAlpha   beta\n\nGamma\n")[0]
    semantic_change = _parse_sections("# Chapter\nAlpha beta\nDelta\n")[0]

    assert _get(base, "source_hash") != _get(whitespace_only, "source_hash")
    assert _get(base, "semantic_hash") == _get(whitespace_only, "semantic_hash")

    assert _get(base, "source_hash") != _get(semantic_change, "source_hash")
    assert _get(base, "semantic_hash") != _get(semantic_change, "semantic_hash")
