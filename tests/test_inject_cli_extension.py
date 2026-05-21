"""Tests for the inject CLI extensions.

The `spec-anchor` CLI ships five helper subcommands:

* `inject-search "<query>"`
* `inject-section "<id>" [<id>...]`
* `inject-chapters`
* `inject-purpose`
* `inject-conflicts`

The tests below exercise the Python entry points
(`spec_anchor.inject.run_inject_*`) directly so the assertions stay
hermetic; the corresponding CLI dispatchers in `spec_anchor.cli` are
trivial wrappers that just print the JSON.

Each test sets up a small project under `tmp_path` with a
`.spec-anchor/config.toml` and the relevant artifacts in
`.spec-anchor/context/`. Qdrant-backed paths (inject-section,
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

from spec_anchor.inject import (  # noqa: E402
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
    (project / ".spec-anchor" / "context").mkdir(parents=True)
    (project / ".spec-anchor" / "state").mkdir(parents=True)
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
        storage = ".spec-anchor/context"

        [vector_store]
        provider = "qdrant"
        url = "http://localhost:6333"
        section_collection = "spec_anchor_section"
        {config_overrides}
        """
    )
    (project / ".spec-anchor/config.toml").write_text(config)
    # Each inject-* command now runs an internal freshness gate (F-C).
    # Tests that focus on inject-* behavior assume a `fresh` baseline; tests
    # that exercise the gate itself overwrite this file explicitly.
    (project / ".spec-anchor/state/freshness.json").write_text(
        json.dumps({"status": "fresh", "blocking_reasons": [], "warnings": []})
    )
    if chapter_anchors is not None:
        (project / ".spec-anchor/context/chapter_anchors.json").write_text(
            json.dumps(chapter_anchors)
        )
    if conflict_review_items is not None:
        (project / ".spec-anchor/context/conflict_review_items.json").write_text(
            json.dumps({"conflict_review_items": conflict_review_items})
        )
    return project


def test_inject_chapters_returns_artifact_path(tmp_path: Path) -> None:
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
    expected_path = (project / ".spec-anchor/context/chapter_anchors.json").as_posix()
    assert result["chapter_anchors_path"] == expected_path
    assert "chapter_anchors" not in result
    assert result["warnings"] == []


def test_inject_chapters_warns_when_artifact_missing(tmp_path: Path) -> None:
    project = _write_project(tmp_path)

    result = run_inject_chapters(project_root=project)

    assert result["status"] == "missing"
    assert result["chapter_anchors_path"].endswith("chapter_anchors.json")
    assert result["warnings"][0]["reason_code"] == "chapter_anchors_missing"


def test_inject_purpose_returns_purpose_full_text_and_concept_path(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        purpose_text="# Purpose\nLine 1.\nLine 2.\n",
        concept_text="# Concept\nPrinciple A.\n",
    )

    result = run_inject_purpose(project_root=project)

    assert result["command"] == "/spec-inject inject-purpose"
    assert "Line 1." in (result["purpose"] or "")
    expected_concept_path = (project / "docs/core/concept.md").as_posix()
    assert result["core_concept_path"] == expected_concept_path
    assert "concept_text" not in result
    assert "purpose_text" not in result
    assert result["warnings"] == []


def test_inject_purpose_warns_when_purpose_file_unset(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".spec-anchor" / "context").mkdir(parents=True)
    (project / ".spec-anchor" / "state").mkdir(parents=True)
    (project / ".spec-anchor" / "config.toml").write_text(
        '[core]\nconcept_file = ""\npurpose_file = ""\n'
    )
    (project / ".spec-anchor/state/freshness.json").write_text(
        json.dumps({"status": "fresh", "blocking_reasons": [], "warnings": []})
    )

    result = run_inject_purpose(project_root=project)

    assert result["purpose"] is None
    assert result["core_concept_path"] is None
    reason_codes = {w["reason_code"] for w in result["warnings"]}
    assert "purpose_file_unset" in reason_codes
    assert "concept_file_unset" in reason_codes


def test_inject_purpose_warns_when_purpose_file_missing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".spec-anchor" / "context").mkdir(parents=True)
    (project / ".spec-anchor" / "state").mkdir(parents=True)
    (project / ".spec-anchor" / "config.toml").write_text(
        '[core]\npurpose_file = "docs/core/purpose.md"\n'
        'concept_file = "docs/core/concept.md"\n'
    )
    (project / ".spec-anchor/state/freshness.json").write_text(
        json.dumps({"status": "fresh", "blocking_reasons": [], "warnings": []})
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
    assert result["collection"] == "spec_anchor_section"


def test_inject_section_warns_when_qdrant_lookup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the Qdrant client raises, the result includes a structured warning."""

    project = _write_project(tmp_path)

    import spec_anchor.inject as inject_module

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


def test_inject_search_returns_source_provenance_for_agentic_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _write_project(tmp_path)

    import spec_anchor.inject as inject_module
    import spec_anchor.retrieval_index as retrieval_module

    class _Provider:
        pass

    class _Hit:
        score = 0.75
        payload = {
            "source_document_id": "docs/spec/main.md",
            "source_section_id": "docs/spec/main.md#0002-alpha",
            "source_span": {
                "start_line": 3,
                "end_line": 5,
                "start_offset": 20,
                "end_offset": 90,
            },
            "heading_path": ["Main", "Alpha"],
            "summary": "Alpha summary",
            "search_keys": ["alpha key"],
            "identifiers": ["AlphaId"],
            "related_sections": [],
        }

    class _Result:
        hits = [_Hit()]

    class _Retriever:
        def search(self, query: str, *, limit: int) -> _Result:
            assert query == "alpha"
            assert limit == 1
            return _Result()

    monkeypatch.setattr(
        retrieval_module,
        "FlagEmbeddingBgeM3Provider",
        lambda **_kwargs: _Provider(),
    )
    monkeypatch.setattr(
        inject_module,
        "_build_hybrid_retriever",
        lambda *_args, **_kwargs: _Retriever(),
    )

    result = run_inject_search(project_root=project, query="alpha", top_k=1)

    assert result["warnings"] == []
    assert result["hits"][0]["source_document_id"] == "docs/spec/main.md"
    assert result["hits"][0]["source_section_id"] == "docs/spec/main.md#0002-alpha"
    assert result["hits"][0]["source_span"]["start_line"] == 3


def test_inject_search_reads_retrieval_section_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _write_project(
        tmp_path,
        config_overrides=dedent(
            """\
            [retrieval]
            section_collection = "custom_collection"
            """
        ),
    )

    import spec_anchor.inject as inject_module
    import spec_anchor.retrieval_index as retrieval_module

    class _Provider:
        pass

    class _Result:
        hits: list[Any] = []

    class _Retriever:
        def search(self, query: str, *, limit: int) -> _Result:
            assert query == "alpha"
            assert limit == 1
            return _Result()

    captured: dict[str, str] = {}

    def _build(url: str, collection: str, provider: Any) -> _Retriever:
        captured["url"] = url
        captured["collection"] = collection
        captured["provider"] = type(provider).__name__
        return _Retriever()

    monkeypatch.setattr(
        retrieval_module,
        "FlagEmbeddingBgeM3Provider",
        lambda **_kwargs: _Provider(),
    )
    monkeypatch.setattr(inject_module, "_build_hybrid_retriever", _build)

    result = run_inject_search(project_root=project, query="alpha", top_k=1)

    assert result["warnings"] == []
    assert result["collection"] == "custom_collection"
    assert captured["collection"] == "custom_collection"


def test_build_hybrid_retriever_constructs_qdrant_hybrid_retriever() -> None:
    """Regression guard: `_build_hybrid_retriever` must construct the
    real `QdrantHybridRetriever` class, not the non-existent
    `HybridRetrievalIndex`. The first real-codex `inject-search` run
    after Phase R-6 surfaced this import-name bug; without this test
    the dormant bug returns silently because every other test stubs the
    constructor.
    """

    from spec_anchor.retrieval_index import (
        FakeBgeM3EmbeddingProvider,
        QdrantHybridRetriever,
    )
    from spec_anchor.inject import _build_hybrid_retriever

    retriever = _build_hybrid_retriever(
        "http://localhost:6333",
        "spec_anchor_section",
        FakeBgeM3EmbeddingProvider(),
    )

    assert isinstance(retriever, QdrantHybridRetriever)
    assert retriever.collection == "spec_anchor_section"


def test_inject_search_warns_when_embedding_provider_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When FlagEmbedding cannot be initialized, the call returns a structured warning."""

    project = _write_project(tmp_path)

    import spec_anchor.inject as inject_module

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
