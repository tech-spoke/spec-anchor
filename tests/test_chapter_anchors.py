"""Tests for LLM-driven Chapter Key Anchor generation.

Chapter Key Anchor is LLM-generated per chapter with fields:
`chapter_id` / `summary` / `key_topics` / `important_sections` / `notes`
/ `source_section_ids` / `generated_at`. These tests cover the
`spec_grag.chapter_anchors.generate_chapter_anchors` entry point and its
cache.
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

from spec_grag.chapter_anchors import (  # noqa: E402
    CHAPTER_ANCHORS_PROMPT_VERSION,
    ChapterAnchorsCache,
    generate_chapter_anchors,
)
from spec_grag.llm_provider import LlmRequest  # noqa: E402


@dataclass
class RecordingChapterAnchorsProvider:
    """Stub LLM that returns a deterministic anchor per chapter."""

    summary_prefix: str = "chapter"
    key_topics: tuple[str, ...] = ("auth", "session", "policy")
    notes: tuple[str, ...] = ("watch CACHE_MODE",)
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return "recording-chapter-anchors-fake"

    def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
        self.calls.append(
            {
                "chapter_id": request.section_id,
                "prompt_chars": len(request.prompt),
                "timeout_sec": timeout_sec,
                "stage": request.stage,
            }
        )
        assert request.stage == "chapter_key_anchor"
        section_ids = list(request.section_hashes.keys())
        return {
            "summary": f"{self.summary_prefix} {request.section_id} summary",
            "key_topics": list(self.key_topics),
            "important_sections": section_ids[:2],
            "notes": list(self.notes),
        }


def _sections() -> list[dict[str, Any]]:
    return [
        {
            "section_id": "docs/spec/main.md#alpha",
            "source_section_id": "docs/spec/main.md#alpha",
            "chapter_id": "docs/spec/main.md",
            "heading_path": ["Main", "Alpha"],
        },
        {
            "section_id": "docs/spec/main.md#beta",
            "source_section_id": "docs/spec/main.md#beta",
            "chapter_id": "docs/spec/main.md",
            "heading_path": ["Main", "Beta"],
        },
        {
            "section_id": "docs/spec/other.md#gamma",
            "source_section_id": "docs/spec/other.md#gamma",
            "chapter_id": "docs/spec/other.md",
            "heading_path": ["Other", "Gamma"],
        },
    ]


def _metadata_entries() -> list[dict[str, Any]]:
    return [
        {
            "section_id": "docs/spec/main.md#alpha",
            "summary": "Alpha covers authentication.",
            "search_keys": ["authentication", "login"],
            "identifiers": ["AuthService"],
            "related_sections": [],
            "source_hash": "hash-alpha",
        },
        {
            "section_id": "docs/spec/main.md#beta",
            "summary": "Beta defines session policy.",
            "search_keys": ["session", "policy"],
            "identifiers": ["SessionPolicy"],
            "related_sections": [],
            "source_hash": "hash-beta",
        },
        {
            "section_id": "docs/spec/other.md#gamma",
            "summary": "Gamma handles caching.",
            "search_keys": ["caching", "cache"],
            "identifiers": ["CACHE_MODE"],
            "related_sections": [],
            "source_hash": "hash-gamma",
        },
    ]


def test_generate_chapter_anchors_returns_one_anchor_per_chapter() -> None:
    provider = RecordingChapterAnchorsProvider()

    result = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=provider,
        generated_at="2026-05-11T03:00:00Z",
    )

    assert result.llm_calls == 2  # two chapters
    chapter_ids = [chapter["chapter_id"] for chapter in result.chapters]
    assert chapter_ids == ["docs/spec/main.md", "docs/spec/other.md"]
    for chapter in result.chapters:
        for field in (
            "chapter_id",
            "summary",
            "key_topics",
            "important_sections",
            "notes",
            "source_section_ids",
            "generated_at",
        ):
            assert field in chapter, f"{field} missing from chapter anchor"
        assert chapter["generated_at"] == "2026-05-11T03:00:00Z"


def test_generate_chapter_anchors_summary_and_topics_come_from_llm() -> None:
    provider = RecordingChapterAnchorsProvider(
        summary_prefix="custom-summary",
        key_topics=("k1", "k2", "k3"),
    )

    result = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=provider,
        generated_at="2026-05-11T03:00:00Z",
    )

    main_chapter = next(
        chapter for chapter in result.chapters if chapter["chapter_id"] == "docs/spec/main.md"
    )
    assert main_chapter["summary"].startswith("custom-summary ")
    assert main_chapter["key_topics"] == ["k1", "k2", "k3"]
    assert main_chapter["notes"] == ["watch CACHE_MODE"]
    assert main_chapter["important_sections"] == [
        "docs/spec/main.md#alpha",
        "docs/spec/main.md#beta",
    ]


def test_generate_chapter_anchors_filters_invalid_important_sections() -> None:
    """LLM-emitted important_sections must be drawn from the chapter's own section_ids."""

    @dataclass
    class _BadProvider:
        @property
        def provider_id(self) -> str:
            return "bad-fake"

        def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
            return {
                "summary": "summary",
                "key_topics": ["k"],
                "important_sections": ["unknown-section-id", "docs/spec/main.md#alpha"],
                "notes": [],
            }

    result = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=_BadProvider(),
        generated_at="2026-05-11T03:00:00Z",
    )

    main_chapter = next(
        chapter for chapter in result.chapters if chapter["chapter_id"] == "docs/spec/main.md"
    )
    assert main_chapter["important_sections"] == ["docs/spec/main.md#alpha"]


def test_generate_chapter_anchors_marks_failed_when_llm_returns_invalid_shape() -> None:
    @dataclass
    class _BrokenProvider:
        @property
        def provider_id(self) -> str:
            return "broken-fake"

        def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
            return {"unexpected": "field"}

    result = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=_BrokenProvider(),
        generated_at="2026-05-11T03:00:00Z",
    )

    failed_ids = {"docs/spec/main.md", "docs/spec/other.md"}
    assert set(result.failed_chapter_ids) == failed_ids
    assert result.artifact["status"] == "failed"
    assert set(result.artifact["generation"]["failed_chapter_ids"]) == failed_ids
    reasons = result.artifact["generation"]["failure_reasons_by_chapter"]
    assert set(reasons) == failed_ids
    assert all(reason.startswith("llm_generation_failed: ") for reason in reasons.values())
    assert len(result.chapters) == 0


def test_generate_chapter_anchors_marks_failed_when_provider_raises() -> None:
    @dataclass
    class _RaisingProvider:
        @property
        def provider_id(self) -> str:
            return "raising-fake"

        def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
            raise RuntimeError(f"boom for {request.section_id}")

    result = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=_RaisingProvider(),
        generated_at="2026-05-11T03:00:00Z",
    )

    failed_ids = {"docs/spec/main.md", "docs/spec/other.md"}
    assert set(result.failed_chapter_ids) == failed_ids
    assert result.artifact["status"] == "failed"
    assert set(result.artifact["generation"]["failed_chapter_ids"]) == failed_ids
    reasons = result.artifact["generation"]["failure_reasons_by_chapter"]
    assert set(reasons) == failed_ids
    assert all(reason.startswith("llm_generation_failed: boom for ") for reason in reasons.values())
    assert result.chapters == []


def test_generate_chapter_anchors_marks_failed_when_llm_output_missing_summary() -> None:
    @dataclass
    class _MissingSummaryProvider:
        @property
        def provider_id(self) -> str:
            return "missing-summary-fake"

        def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
            summary: str | None = ""
            if request.section_id == "docs/spec/other.md":
                summary = None
            return {
                "summary": summary,
                "key_topics": ["topic"],
                "important_sections": list(request.section_hashes.keys())[:1],
                "notes": [],
            }

    result = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=_MissingSummaryProvider(),
        generated_at="2026-05-11T03:00:00Z",
    )

    failed_ids = {"docs/spec/main.md", "docs/spec/other.md"}
    assert set(result.failed_chapter_ids) == failed_ids
    assert result.artifact["status"] == "failed"
    assert set(result.artifact["generation"]["failed_chapter_ids"]) == failed_ids
    assert result.artifact["generation"]["failure_reasons_by_chapter"] == {
        chapter_id: "llm_output_unparseable_or_missing_summary"
        for chapter_id in failed_ids
    }
    assert result.chapters == []


def test_chapter_anchors_cache_reuses_unchanged_chapter(tmp_path: Path) -> None:
    provider = RecordingChapterAnchorsProvider()
    cache_dir = tmp_path / "cache"

    first = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=provider,
        cache_dir=cache_dir,
        generated_at="2026-05-11T03:00:00Z",
    )

    assert first.llm_calls == 2
    assert first.cache_hits == 0

    cached_provider = RecordingChapterAnchorsProvider()
    second = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=cached_provider,
        cache_dir=cache_dir,
        generated_at="2026-05-11T04:00:00Z",
    )

    assert cached_provider.calls == []
    assert second.cache_hits == 2
    assert second.llm_calls == 0
    # Cached chapters carry over the prior LLM output (summary etc.) but
    # the run-level generated_at is refreshed.
    main = next(
        chapter for chapter in second.chapters if chapter["chapter_id"] == "docs/spec/main.md"
    )
    assert main["generated_at"] == "2026-05-11T04:00:00Z"


def test_chapter_anchors_rebuild_all_bypasses_cache(tmp_path: Path) -> None:
    """Phase R-7 follow-up: rebuild_all=True honors the `--all` CLI contract.

    The first run populates the chapter_anchors cache. A second run with
    `rebuild_all=True` MUST call the LLM again for every chapter even
    though `section_hashes` + `concept_hash` + `prompt_version` +
    `model` + `provider` are unchanged. Without this, the `--all` /
    `--rebuild` flag fails to invalidate Phase R-7's LLM-derived cache,
    contradicting its documented "clear LLM-derived caches" contract.
    """

    provider = RecordingChapterAnchorsProvider()
    cache_dir = tmp_path / "cache"

    first = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=provider,
        cache_dir=cache_dir,
        generated_at="2026-05-11T03:00:00Z",
    )
    assert first.llm_calls == 2
    assert first.cache_hits == 0

    # Re-run with rebuild_all=True. The on-disk cache files still exist
    # (this test does not physically delete them; the CLI dispatcher
    # does that in addition for safety). The chapter_anchors module
    # itself must bypass the cache.load step via the rebuild_all flag.
    rebuilt_provider = RecordingChapterAnchorsProvider(summary_prefix="rebuilt")
    second = generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=rebuilt_provider,
        cache_dir=cache_dir,
        generated_at="2026-05-11T04:00:00Z",
        rebuild_all=True,
    )

    assert second.cache_hits == 0, (
        "rebuild_all=True must bypass the cache.load step entirely. "
        "Phase R-7 cache hits would mask the --all contract."
    )
    assert second.llm_calls == 2
    assert len(rebuilt_provider.calls) == 2
    # The new summary text comes from the fresh LLM, not the cached
    # entry, proving the bypass.
    main = next(
        chapter for chapter in second.chapters if chapter["chapter_id"] == "docs/spec/main.md"
    )
    assert main["summary"].startswith("rebuilt "), main["summary"]


def test_chapter_anchors_cache_invalidates_on_section_hash_change(tmp_path: Path) -> None:
    provider = RecordingChapterAnchorsProvider()
    cache_dir = tmp_path / "cache"

    generate_chapter_anchors(
        _sections(),
        _metadata_entries(),
        provider=provider,
        cache_dir=cache_dir,
        generated_at="2026-05-11T03:00:00Z",
    )

    bumped = [dict(entry) for entry in _metadata_entries()]
    bumped[0]["source_hash"] = "hash-alpha-bumped"

    fresh_provider = RecordingChapterAnchorsProvider()
    result = generate_chapter_anchors(
        _sections(),
        bumped,
        provider=fresh_provider,
        cache_dir=cache_dir,
        generated_at="2026-05-11T04:00:00Z",
    )

    # The "main" chapter contains the bumped section, so it re-runs.
    # The "other" chapter is unchanged and stays cached.
    chapter_ids_recomputed = {call["chapter_id"] for call in fresh_provider.calls}
    assert chapter_ids_recomputed == {"docs/spec/main.md"}
    assert result.cache_hits == 1


def test_chapter_anchors_prompt_version_constant_matches_module() -> None:
    assert CHAPTER_ANCHORS_PROMPT_VERSION == "chapter-anchors-v1"


def test_chapter_anchors_cache_path_matches_phase_r7_layout(tmp_path: Path) -> None:
    cache = ChapterAnchorsCache(tmp_path / "cache")

    key = cache.key_for("docs/spec/main.md", ["hash-a", "hash-b"])
    path = cache.path_for_key(key)

    assert path == tmp_path / "cache" / "chapter_anchors" / f"{key}.json"


def test_chapter_key_anchor_output_schema_includes_required_fields() -> None:
    """Phase R-7 followup: codex receives the chapter-shaped schema, not the
    section_metadata one.

    The bug found during real-codex verification was: codex was given the
    default `_spec_core_output_schema` (which requires `summary` +
    `search_keys`) for the `chapter_key_anchor` stage. Verify the schema
    now reflects Phase R-7 contract.
    """

    from spec_grag.llm_provider import _chapter_key_anchor_output_schema

    schema = _chapter_key_anchor_output_schema()

    assert set(schema["required"]) == {
        "summary",
        "key_topics",
        "important_sections",
        "notes",
    }
    assert schema["additionalProperties"] is False
    assert schema["properties"]["summary"] == {"type": "string"}
    assert schema["properties"]["key_topics"]["items"] == {"type": "string"}


def test_generate_chapter_anchors_handles_empty_input() -> None:
    result = generate_chapter_anchors(
        [],
        [],
        generated_at="2026-05-11T03:00:00Z",
    )

    assert result.chapters == []
    assert result.llm_calls == 0
    assert result.artifact["status"] == "success"
