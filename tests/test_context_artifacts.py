from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec_grag.artifacts import (
    CORE_ARTIFACT_ORDER,
    ARTIFACT_FILENAMES,
    ArtifactError,
    ContextArtifactStore,
    build_empty_chapter_anchors,
    build_section_manifest,
)
from spec_grag.section_parser import parse_markdown_sections


def _sections() -> list[object]:
    return parse_markdown_sections(
        "# Chapter\nchapter body\n## Feature\nfeature body\n",
        source_path="docs/spec/main.md",
        max_heading_level=4,
    )


def test_t_u22_chapter_anchor_structure_round_trips(tmp_path: Path) -> None:
    store = ContextArtifactStore(tmp_path / ".spec-grag/context")
    payload = build_empty_chapter_anchors(_sections())

    store.write("chapter_anchors", payload)
    loaded = store.read("chapter_anchors")
    entry = loaded["chapters"][0]

    for field in (
        "chapter_id",
        "summary",
        "key_topics",
        "important_sections",
        "search_keys",
        "notes",
        "source_section_ids",
        "generated_at",
    ):
        assert field in entry
    assert len(entry["source_section_ids"]) == 2
    assert loaded["schema_version"] == 1


def test_t_i15_context_update_writes_freshness_last(tmp_path: Path) -> None:
    store = ContextArtifactStore(tmp_path / ".spec-grag/context")
    sections = _sections()
    artifacts = {
        "section_manifest": build_section_manifest(sections),
        "chapter_anchors": build_empty_chapter_anchors(sections),
        "conflict_review_items": {"items": []},
        "freshness": {"status": "fresh", "blocking_reasons": [], "warnings": []},
    }

    written = store.write_context_update(artifacts)

    assert [path.name for path in written] == [
        ARTIFACT_FILENAMES[name]
        for name in CORE_ARTIFACT_ORDER
        if name in artifacts
    ]
    assert written[-1].name == "freshness.json"
    assert store.read("freshness")["status"] == "fresh"


def test_t_i15_atomic_write_keeps_previous_payload_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ContextArtifactStore(tmp_path / ".spec-grag/context")
    store.write("freshness", {"status": "fresh"})
    target = store.path_for("freshness")
    before = target.read_text()

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("spec_grag.artifacts.os.replace", fail_replace)
    with pytest.raises(OSError):
        store.write("freshness", {"status": "failed"})

    assert target.read_text() == before
    assert json.loads(before)["status"] == "fresh"


def test_context_artifact_missing_artifacts_diagnostic(tmp_path: Path) -> None:
    store = ContextArtifactStore(tmp_path / ".spec-grag/context")
    store.write("section_manifest", {"sections": []})

    assert store.missing_artifacts(("section_manifest", "chapter_anchors")) == [
        "chapter_anchors"
    ]


def test_context_artifact_unknown_name_fails(tmp_path: Path) -> None:
    store = ContextArtifactStore(tmp_path / ".spec-grag/context")
    with pytest.raises(ArtifactError):
        store.write("unknown", {})
