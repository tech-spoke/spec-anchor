from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from spec_grag.concept_index import ConceptDiffProposalError
from spec_grag.core import run_core_update
from spec_grag.injection import (
    build_injection,
    classify_context_item,
    merge_graph_traversal_matches,
)
from spec_grag.manifest import load_source_manifest
from spec_grag.protocol import Command, ResultStatus, ResultType, SlashCommandRequest


def request(project_root: Path) -> SlashCommandRequest:
    return SlashCommandRequest.model_validate(
        {
            "command": Command.SPEC_INJECT,
            "project_root": str(project_root),
            "task_prompt": "Auth Login を見直す",
            "conversation_context": {
                "current_user_message": "Auth Login を見直す",
                "recent_messages": [],
                "working_target": None,
                "explicit_files": [],
            },
            "agent_capabilities": {
                "can_read_source": True,
                "can_answer": False,
            },
            "options": {"output_format": "json"},
        }
    )


def config() -> dict[str, Any]:
    return {
        "sources": {"include": ["docs/spec/**/*.md"]},
        "graph": {"storage": ".spec-grag/graph/"},
        "embedding": {"provider": "stable_hash", "dimension": 8},
    }


def write_auth_source(project_root: Path, text: str) -> None:
    path = project_root / "docs/spec/auth.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_injection_is_read_only_by_default(tmp_path: Path) -> None:
    build = build_injection(tmp_path, config(), request(tmp_path))

    assert build.status == ResultStatus.BLOCKED
    assert build.result_type == ResultType.NEED_MORE_CONTEXT_RESULT
    assert not (tmp_path / ".spec-grag/graph/source_manifest.json").exists()


def test_graph_expansion_obeys_hop_limit() -> None:
    graph_data = {
        "nodes": {
            "a": {"label": "ANCHOR", "properties": {"source_section_id": "s-a"}},
            "b": {"label": "ANCHOR", "properties": {"source_section_id": "s-b"}},
            "c": {"label": "ANCHOR", "properties": {"source_section_id": "s-c"}},
        },
        "relations": {
            "r1": {
                "label": "DEPENDS_ON",
                "source_id": "a",
                "target_id": "b",
                "properties": {"source_section_id": "s-a", "confidence": 0.9},
            },
            "r2": {
                "label": "USES",
                "source_id": "b",
                "target_id": "c",
                "properties": {"source_section_id": "s-b", "confidence": 0.8},
            },
        },
    }
    seed = [
        {
            "entity_id": "a",
            "entity_type": "ANCHOR",
            "source_section_id": "s-a",
            "retrieval_methods": ["raw_chunk_hybrid"],
            "ranking_score": 1.0,
        }
    ]

    one_hop = merge_graph_traversal_matches(
        graph_data,
        seed,
        selected_section_ids={"s-a"},
        max_hops=1,
    )
    two_hop = merge_graph_traversal_matches(
        graph_data,
        seed,
        selected_section_ids={"s-a"},
        max_hops=2,
    )

    assert {item["entity_id"] for item in one_hop} == {"a", "b"}
    assert {item["entity_id"] for item in two_hop} == {"a", "b", "c"}
    c_item = next(item for item in two_hop if item["entity_id"] == "c")
    assert c_item["graph_hop"] == 2
    assert c_item["graph_paths"][0][-1]["relation_id"] == "r2"


def test_classification_cache_deduplicates_llm_calls() -> None:
    calls: list[str] = []

    class CountingLLM:
        def complete(self, prompt: str, **_kwargs: Any) -> SimpleNamespace:
            calls.append(prompt)
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "constraint_relevance": "medium",
                        "target_relevance": "high",
                        "semantic_conflict_candidate": False,
                        "review_required": False,
                        "reason_for_current_task": "same evidence",
                    }
                )
            )

    cache: dict[str, dict[str, Any]] = {}
    item = {
        "source_section_id": "docs/spec/auth.md#auth-login",
        "source_hash": "hash-auth",
        "source_span": "1-3",
        "excerpt": "OAuth is required.",
    }

    first = classify_context_item(
        item,
        item_type="source_section",
        query="Auth Login を見直す",
        llm=CountingLLM(),
        llm_budget={"remaining": 2},
        fallback_on_error=False,
        classification_cache=cache,
    )
    second = classify_context_item(
        {**item, "target_relevance": "high"},
        item_type="source_section",
        query="Auth Login を見直す",
        llm=CountingLLM(),
        llm_budget={"remaining": 2},
        fallback_on_error=False,
        classification_cache=cache,
    )

    assert first["classification_source"] == "classification_llm"
    assert second["classification_cache_hit"] is True
    assert len(calls) == 1


def test_core_update_failure_keeps_active_artifacts(tmp_path: Path, monkeypatch) -> None:
    write_auth_source(tmp_path, "# Auth\n\n## Login\n\nOAuth is required.\n")
    first = run_core_update(tmp_path, config(), all_sources=True)
    graph_dir = tmp_path / ".spec-grag/graph"
    before = load_source_manifest(graph_dir / "source_manifest.json")
    before_hash = before.by_section_id()["docs/spec/auth.md#auth-login"].source_hash

    write_auth_source(tmp_path, "# Auth\n\n## Login\n\nOAuth and MFA are required.\n")

    def fail_concept_diff(**_kwargs: Any) -> None:
        raise ConceptDiffProposalError("concept diff unavailable")

    monkeypatch.setattr(
        "spec_grag.core.generate_concept_diff_candidate",
        fail_concept_diff,
    )

    failed = run_core_update(tmp_path, config(), all_sources=False)
    after = load_source_manifest(graph_dir / "source_manifest.json")

    assert first.status == ResultStatus.OK
    assert failed.status == ResultStatus.FAILED
    assert failed.failed_sources == ["concept_diff"]
    assert after.by_section_id()["docs/spec/auth.md#auth-login"].source_hash == before_hash
