"""Tests for the inject CLI extensions.

The `spec-grag` CLI ships five helper subcommands:

* `inject-search "<query>"`
* `inject-section "<id>" [<id>...]`
* `inject-chapters`
* `inject-purpose`
* `inject-conflicts`

The tests below exercise the Python entry points
(`spec_grag.inject.run_inject_*`) directly so the assertions stay
hermetic; the corresponding CLI dispatchers in `spec_grag.cli` are
trivial wrappers that just print the JSON.

Each test sets up a small project under `tmp_path` with a
`.spec-grag/config.toml` and the relevant artifacts in
`.spec-grag/context/`. Qdrant-backed paths (inject-section,
inject-search) are not exercised here because they require a live
service; instead we verify the disabled / fallback behavior
(structured warnings, no exception).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spec_grag.inject import (  # noqa: E402
    run_inject_chapters,
    run_inject_conflicts,
    run_inject_purpose,
    run_inject_search,
    run_inject_section,
)


def _write_project(
    tmp_path: Path,
    *,
    purpose_text: str = "# Purpose\nKeep specs honest.\n",
    concept_text: str = "# Core Concept\nSource Specs are the authority.\n",
    chapter_anchors: dict[str, Any] | None = None,
    conflict_review_items: list[dict[str, Any]] | None = None,
    config_overrides: str = "",
) -> Path:
    project = tmp_path / "project"
    (project / ".spec-grag" / "context").mkdir(parents=True)
    (project / "docs/core").mkdir(parents=True)
    (project / "docs/core/purpose.md").write_text(purpose_text)
    (project / "docs/core/concept.md").write_text(concept_text)
    config = dedent(
        f"""\
        [sources]
        include = ["docs/spec/**/*.md"]

        [core]
        purpose_file = "docs/core/purpose.md"
        concept_file = "docs/core/concept.md"

        [context]
        storage = ".spec-grag/context"

        [vector_store]
        provider = "qdrant"
        url = "http://localhost:6333"
        section_collection = "spec_grag_section"
        {config_overrides}
        """
    )
    (project / ".spec-grag/config.toml").write_text(config)
    if chapter_anchors is not None:
        (project / ".spec-grag/context/chapter_anchors.json").write_text(
            json.dumps(chapter_anchors)
        )
    if conflict_review_items is not None:
        (project / ".spec-grag/context/conflict_review_items.json").write_text(
            json.dumps({"conflict_review_items": conflict_review_items})
        )
    return project


def test_inject_chapters_returns_artifact(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        chapter_anchors={
            "status": "success",
            "chapters": [
                {
                    "chapter_id": "ch-1",
                    "summary": "Chapter 1 summary",
                    "key_topics": ["auth"],
                    "important_sections": ["s1"],
                }
            ],
            "generated_at": "2026-05-11T03:00:00Z",
        },
    )

    result = run_inject_chapters(project_root=project)

    assert result["command"] == "/spec-inject inject-chapters"
    assert result["status"] == "success"
    chapters = result["chapter_anchors"]["chapters"]
    assert chapters[0]["chapter_id"] == "ch-1"
    assert result["warnings"] == []


def test_inject_chapters_warns_when_artifact_missing(tmp_path: Path) -> None:
    project = _write_project(tmp_path)

    result = run_inject_chapters(project_root=project)

    assert result["status"] == "missing"
    assert result["chapter_anchors"]["status"] == "missing"
    assert result["warnings"][0]["reason_code"] == "chapter_anchors_missing"


def test_inject_purpose_returns_full_text(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        purpose_text="# Purpose\nLine 1.\nLine 2.\n",
        concept_text="# Concept\nPrinciple A.\n",
    )

    result = run_inject_purpose(project_root=project)

    assert result["command"] == "/spec-inject inject-purpose"
    assert "Line 1." in (result["purpose_text"] or "")
    assert "Principle A." in (result["concept_text"] or "")
    assert result["warnings"] == []


def test_inject_purpose_warns_when_purpose_file_unset(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".spec-grag" / "context").mkdir(parents=True)
    (project / ".spec-grag" / "config.toml").write_text(
        '[core]\nconcept_file = ""\npurpose_file = ""\n'
    )

    result = run_inject_purpose(project_root=project)

    assert result["purpose_text"] is None
    assert result["concept_text"] is None
    reason_codes = {w["reason_code"] for w in result["warnings"]}
    assert "purpose_file_unset" in reason_codes
    assert "concept_file_unset" in reason_codes


def test_inject_purpose_warns_when_purpose_file_missing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".spec-grag" / "context").mkdir(parents=True)
    (project / ".spec-grag" / "config.toml").write_text(
        '[core]\npurpose_file = "docs/core/purpose.md"\n'
        'concept_file = "docs/core/concept.md"\n'
    )

    result = run_inject_purpose(project_root=project)

    reason_codes = {w["reason_code"] for w in result["warnings"]}
    assert "purpose_file_missing" in reason_codes
    assert "concept_file_missing" in reason_codes


def test_inject_conflicts_returns_only_resolved_non_stale(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        conflict_review_items=[
            {"conflict_id": "c-resolved", "status": "resolved"},
            {"conflict_id": "c-pending", "status": "pending"},
            {"conflict_id": "c-dismissed", "status": "dismissed"},
            {"conflict_id": "c-stale", "status": "resolved", "stale_resolution": True},
        ],
    )

    result = run_inject_conflicts(project_root=project)

    resolved_ids = [item["conflict_id"] for item in result["resolved_conflict_review_items"]]
    excluded_ids = [item["conflict_id"] for item in result["excluded_conflict_review_items"]]
    assert resolved_ids == ["c-resolved"]
    assert "c-pending" in excluded_ids
    assert "c-dismissed" in excluded_ids
    assert "c-stale" in excluded_ids
    assert result["count"] == 1


def test_inject_conflicts_returns_empty_for_missing_artifact(tmp_path: Path) -> None:
    project = _write_project(tmp_path)

    result = run_inject_conflicts(project_root=project)

    assert result["resolved_conflict_review_items"] == []
    assert result["excluded_conflict_review_items"] == []
    assert result["count"] == 0


def test_inject_section_returns_empty_for_no_ids(tmp_path: Path) -> None:
    project = _write_project(tmp_path)

    result = run_inject_section(project_root=project, section_ids=[])

    assert result["sections"] == {}
    assert result["found_section_ids"] == []
    assert result["missing_section_ids"] == []
    assert result["collection"] == "spec_grag_section"


def test_inject_section_warns_when_qdrant_lookup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the Qdrant client raises, the result includes a structured warning."""

    project = _write_project(tmp_path)

    import spec_grag.inject as inject_module

    def _raise_inject_error(url: str) -> Any:
        raise inject_module.SpecInjectError("qdrant unavailable in test")

    monkeypatch.setattr(inject_module, "_build_qdrant_client", _raise_inject_error)

    result = run_inject_section(
        project_root=project,
        section_ids=["docs/spec/main.md#alpha"],
    )

    assert result["sections"] == {}
    reasons = {w["reason_code"] for w in result["warnings"]}
    assert "qdrant_unavailable" in reasons


def test_inject_search_warns_on_empty_query(tmp_path: Path) -> None:
    project = _write_project(tmp_path)

    result = run_inject_search(project_root=project, query="   ", top_k=4)

    assert result["hits"] == []
    reasons = {w["reason_code"] for w in result["warnings"]}
    assert "empty_query" in reasons


def test_build_hybrid_retriever_constructs_qdrant_hybrid_retriever() -> None:
    """Regression guard: `_build_hybrid_retriever` must construct the
    real `QdrantHybridRetriever` class, not the non-existent
    `HybridRetrievalIndex`. The first real-codex `inject-search` run
    after Phase R-6 surfaced this import-name bug; without this test
    the dormant bug returns silently because every other test stubs the
    constructor.
    """

    from spec_grag.retrieval_index import (
        FakeBgeM3EmbeddingProvider,
        QdrantHybridRetriever,
    )
    from spec_grag.inject import _build_hybrid_retriever

    retriever = _build_hybrid_retriever(
        "http://localhost:6333",
        "spec_grag_section",
        FakeBgeM3EmbeddingProvider(),
    )

    assert isinstance(retriever, QdrantHybridRetriever)
    assert retriever.collection == "spec_grag_section"


def test_inject_search_warns_when_embedding_provider_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When FlagEmbedding cannot be initialized, the call returns a structured warning."""

    project = _write_project(tmp_path)

    import spec_grag.inject as inject_module

    def _raise_init(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated FlagEmbedding load failure")

    monkeypatch.setattr(
        inject_module,
        "_build_hybrid_retriever",
        _raise_init,
    )

    result = run_inject_search(
        project_root=project,
        query="auth",
        top_k=2,
    )

    reasons = {w["reason_code"] for w in result["warnings"]}
    assert "retriever_init_failed" in reasons or "embedding_unavailable" in reasons
    assert result["hits"] == []
