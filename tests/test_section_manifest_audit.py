"""Tests for `section_manifest.json` audit fields.

The LLM-generation audit metadata (provider / status / last_prompt_version /
generated_at) is hosted in `section_manifest.json`. The audit data is
sourced from the freshly built `metadata_entries` and merged into each
`_section_manifest_entry` via the `_section_manifest_audit_by_id` helper.

These tests verify both helpers directly because they live inside
`spec_grag/core.py` as module-private functions; covering them here
avoids relying on a full `spec-grag core` run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spec_grag.core import (  # noqa: E402
    _section_manifest_audit_by_id,
    _section_manifest_entry,
)


def _section(section_id: str) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "source_section_id": section_id,
        "source_document_id": "docs/spec/main.md",
        "source_hash": f"hash-{section_id}",
        "semantic_hash": f"hash-{section_id}",
        "chapter_id": "chapter-1",
        "heading_path": ["Chapter", section_id],
        "source_span": {"start": 0, "end": 10},
    }


def test_audit_by_id_collects_provider_status_prompt_version_and_generated_at() -> None:
    """Phase R-4: audit fields land in section_manifest by section_id."""

    metadata_entries = [
        {
            "section_id": "alpha",
            "llm_provider": "codex_cli",
            "llm_generation_status": "success",
            "prompt_version": "section-metadata-v2",
            "generated_at": "2026-05-11T03:00:00Z",
        },
        {
            "section_id": "beta",
            "llm_provider": "claude_cli",
            "llm_generation_status": "failed",
            "prompt_version": "section-metadata-v2",
            "generated_at": None,
        },
    ]

    audit_by_id = _section_manifest_audit_by_id(
        metadata_entries,
        generated_at="2026-05-11T03:00:00Z",
    )

    assert set(audit_by_id.keys()) == {"alpha", "beta"}
    assert audit_by_id["alpha"]["llm_provider"] == "codex_cli"
    assert audit_by_id["alpha"]["llm_generation_status"] == "success"
    assert audit_by_id["alpha"]["last_prompt_version"] == "section-metadata-v2"
    assert audit_by_id["alpha"]["generated_at"] == "2026-05-11T03:00:00Z"
    # Falls back to run-level generated_at when entry-level is None.
    assert audit_by_id["beta"]["generated_at"] == "2026-05-11T03:00:00Z"
    assert audit_by_id["beta"]["llm_generation_status"] == "failed"


def test_audit_by_id_skips_entries_without_section_id() -> None:
    metadata_entries = [
        {"llm_provider": "codex_cli"},  # missing section_id
        {"section_id": "", "llm_provider": "codex_cli"},  # empty section_id
        {"section_id": "alpha", "llm_provider": "codex_cli"},
    ]

    audit_by_id = _section_manifest_audit_by_id(
        metadata_entries,
        generated_at="2026-05-11T03:00:00Z",
    )

    assert set(audit_by_id.keys()) == {"alpha"}


def test_audit_by_id_accepts_source_section_id_as_fallback() -> None:
    metadata_entries = [
        {
            "source_section_id": "gamma",
            "llm_provider": "codex_cli",
            "llm_generation_status": "success",
        }
    ]

    audit_by_id = _section_manifest_audit_by_id(
        metadata_entries,
        generated_at="2026-05-11T03:00:00Z",
    )

    assert "gamma" in audit_by_id


def test_section_manifest_entry_includes_audit_when_provided() -> None:
    section = _section("alpha")
    audit = {
        "llm_provider": "codex_cli",
        "llm_generation_status": "success",
        "last_prompt_version": "section-metadata-v2",
        "generated_at": "2026-05-11T03:00:00Z",
    }

    entry = _section_manifest_entry(section, audit=audit)

    for key in (
        "section_id",
        "source_section_id",
        "source_document_id",
        "source_hash",
        "semantic_hash",
        "chapter_id",
        "heading_path",
        "source_span",
        "llm_provider",
        "llm_generation_status",
        "last_prompt_version",
        "generated_at",
    ):
        assert key in entry, f"section_manifest entry must include {key}"
    assert entry["last_prompt_version"] == "section-metadata-v2"


def test_section_manifest_entry_includes_retrieval_fingerprints_when_provided() -> None:
    section = _section("alpha")

    entry = _section_manifest_entry(
        section,
        fingerprints={
            "vector_input_fingerprint": "v" * 64,
            "payload_fingerprint": "p" * 64,
        },
    )

    assert entry["vector_input_fingerprint"] == "v" * 64
    assert entry["payload_fingerprint"] == "p" * 64


def test_section_manifest_entry_without_audit_is_unchanged() -> None:
    section = _section("alpha")

    entry = _section_manifest_entry(section)

    for key in (
        "section_id",
        "source_section_id",
        "source_document_id",
        "source_hash",
        "semantic_hash",
        "chapter_id",
        "heading_path",
        "source_span",
    ):
        assert key in entry
    for audit_key in (
        "llm_provider",
        "llm_generation_status",
        "last_prompt_version",
    ):
        assert audit_key not in entry


def test_section_manifest_entry_drops_missing_audit_keys() -> None:
    """Partial audit dicts must not introduce None values for unknown keys."""

    section = _section("alpha")
    entry = _section_manifest_entry(
        section,
        audit={"llm_provider": "codex_cli"},  # other audit fields missing
    )

    assert entry["llm_provider"] == "codex_cli"
    assert "llm_generation_status" not in entry
    assert "last_prompt_version" not in entry
    assert "generated_at" not in entry
