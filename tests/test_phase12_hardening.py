from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from spec_grag.config import validate_project_config
from spec_grag.concept_index import ConceptDiffProposalError
from spec_grag.core import ARTIFACT_REVISION_FILENAME, run_core_update
from spec_grag.injection import (
    build_injection,
    classification_candidate_for_item,
    classify_candidates_by_priority,
    classify_context_item,
    load_persistent_classification_cache,
    merge_graph_traversal_matches,
    save_persistent_classification_cache,
)
from spec_grag.manifest import load_source_manifest
from spec_grag.protocol import Command, ResultStatus, ResultType, SlashCommandRequest
from spec_grag.readiness import evaluate_grag_readiness


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


def test_graph_traversal_policy_filters_relation_type_confidence_and_caps() -> None:
    graph_data = {
        "nodes": {
            "a": {"label": "ANCHOR", "properties": {"source_section_id": "s-a"}},
            "b": {"label": "ANCHOR", "properties": {"source_section_id": "s-b"}},
            "c": {"label": "ANCHOR", "properties": {"source_section_id": "s-c"}},
            "d": {"label": "ANCHOR", "properties": {"source_section_id": "s-d"}},
            "e": {"label": "ANCHOR", "properties": {"source_section_id": "s-e"}},
        },
        "relations": {
            "r-depends": {
                "label": "DEPENDS_ON",
                "source_id": "a",
                "target_id": "b",
                "properties": {"source_section_id": "s-a", "confidence": "high"},
            },
            "r-low": {
                "label": "RELATED_TO",
                "source_id": "a",
                "target_id": "c",
                "properties": {"source_section_id": "s-a", "confidence": "low"},
            },
            "r-mentions": {
                "label": "MENTIONS",
                "source_id": "a",
                "target_id": "d",
                "properties": {"source_section_id": "s-a", "confidence": "high"},
            },
            "r-contrast": {
                "label": "CONTRASTS_WITH",
                "source_id": "a",
                "target_id": "e",
                "properties": {"source_section_id": "s-a", "confidence": "medium"},
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

    matches = merge_graph_traversal_matches(
        graph_data,
        seed,
        selected_section_ids={"s-a"},
        max_hops=1,
        relation_allowlist=["DEPENDS_ON", "REFINES", "RELATED_TO", "CONTRASTS_WITH"],
        min_relation_confidence="medium",
        max_graph_entities=10,
    )

    assert {item["entity_id"] for item in matches} == {"a", "b", "e"}
    contrast = next(item for item in matches if item["entity_id"] == "e")
    assert contrast["relation_types"] == ["CONTRASTS_WITH"]

    capped = merge_graph_traversal_matches(
        graph_data,
        seed,
        selected_section_ids={"s-a"},
        max_hops=1,
        relation_allowlist=["DEPENDS_ON", "REFINES", "RELATED_TO", "CONTRASTS_WITH"],
        min_relation_confidence="medium",
        max_graph_entities=2,
    )

    assert [item["entity_id"] for item in capped] == ["a", "b"]


def test_retrieval_policy_config_defaults_include_contrast_for_conflicts() -> None:
    validated = validate_project_config(
        {"sources": {"include": ["docs/spec/**/*.md"]}},
        smoke=True,
    )

    assert validated["retrieval"]["graph_expansion_hops"] == 1
    assert validated["retrieval"]["graph_relation_allowlist"] == [
        "DEPENDS_ON",
        "REFINES",
        "RELATED_TO",
        "CONTRASTS_WITH",
    ]
    assert validated["retrieval"]["graph_min_relation_confidence"] == "medium"
    assert validated["retrieval"]["max_graph_entities"] == 12


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


def test_classification_priority_selects_purpose_and_raw_source_before_graph_cluster() -> None:
    calls: list[list[str]] = []

    class RecordingLLM:
        def complete(self, prompt: str, **_kwargs: Any) -> SimpleNamespace:
            payload = json.loads(prompt.split("INPUT_JSON:\n", 1)[1])
            keys = [item["classification_key"] for item in payload["context_items"]]
            calls.append([item["item_type"] for item in payload["context_items"]])
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "decisions": [
                            {
                                "classification_key": key,
                                "constraint_relevance": "medium",
                                "target_relevance": "medium",
                                "semantic_conflict_candidate": False,
                                "review_required": False,
                                "reason_for_current_task": f"{key} selected",
                            }
                            for key in keys
                        ]
                    }
                )
            )

    query = "Auth Login を見直す"
    items = [
        (
            "cluster",
            {
                "entity_id": "cluster:auth",
                "cluster_id": "cluster:auth",
                "entity_type": "CLUSTER",
                "summary": "Auth related summary.",
                "ranking_score": 0.9,
            },
        ),
        (
            "graph_entity",
            {
                "entity_id": "section:auth",
                "entity_type": "SECTION",
                "summary": "Auth graph section.",
                "ranking_score": 0.95,
            },
        ),
        (
            "source_section",
            {
                "source_section_id": "docs/spec/auth.md#auth-login",
                "stable_chunk_uid": "chunk:auth-login",
                "source_hash": "hash-auth",
                "source_span": "4-8",
                "excerpt": "OAuth is required for Auth Login.",
                "retrieval_unit": "raw_document_chunk",
                "retrieval_methods": ["raw_chunk_hybrid"],
                "constraint_relevance": "medium",
                "target_relevance": "high",
                "ranking_score": 0.7,
            },
        ),
        (
            "purpose",
            {
                "source_origin": "Purpose",
                "summary": "Keep users secure.",
                "constraint_relevance": "high",
            },
        ),
    ]
    candidates = [
        classification_candidate_for_item(item, item_type=item_type, query=query)
        for item_type, item in items
    ]

    run = classify_candidates_by_priority(
        candidates,
        query=query,
        llm=RecordingLLM(),
        classification_budget={"remaining": 2, "skipped": 0},
        fallback_on_error=False,
        classification_cache={},
        classification_config={
            "max_items": 2,
            "max_source_chunks": 1,
            "max_graph_entities": 1,
            "max_clusters": 1,
            "batch_size": 5,
        },
    )

    assert calls == [["purpose", "source_section"]]
    assert run.metrics["llm_calls"] == 1
    assert run.metrics["candidate_count_by_type"] == {
        "cluster": 1,
        "graph_entity": 1,
        "source_chunk": 1,
        "purpose": 1,
    }
    assert run.metrics["skipped_count_by_type"] == {
        "graph_entity": 1,
        "cluster": 1,
    }
    assert run.metrics["high_priority_skipped_count"] == 0
    assert all(
        item["classification_source"] == "classification_incomplete"
        and item["classification_llm_skipped"] == "max_items_exhausted"
        and item["review_required"] is True
        for item in run.items_by_key.values()
        if item.get("classification_budget_skip_reason")
    )


def test_classification_candidate_dedup_runs_llm_once_per_classification_key() -> None:
    calls: list[str] = []

    class CountingLLM:
        def complete(self, prompt: str, **_kwargs: Any) -> SimpleNamespace:
            calls.append(prompt)
            payload = json.loads(prompt.split("INPUT_JSON:\n", 1)[1])
            key = payload["context_items"][0]["classification_key"]
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "decisions": [
                            {
                                "classification_key": key,
                                "constraint_relevance": "medium",
                                "target_relevance": "high",
                                "semantic_conflict_candidate": False,
                                "review_required": False,
                                "reason_for_current_task": "deduped source",
                            }
                        ]
                    }
                )
            )

    query = "Auth Login を見直す"
    source = {
        "source_section_id": "docs/spec/auth.md#auth-login",
        "source_hash": "hash-auth",
        "source_span": "4-8",
        "excerpt": "OAuth is required.",
        "constraint_relevance": "medium",
    }
    candidates = [
        classification_candidate_for_item(source, item_type="source_section", query=query),
        classification_candidate_for_item(
            {**source, "target_relevance": "high"},
            item_type="source_section",
            query=query,
        ),
    ]

    run = classify_candidates_by_priority(
        candidates,
        query=query,
        llm=CountingLLM(),
        classification_budget={"remaining": 1, "skipped": 0},
        fallback_on_error=False,
        classification_cache={},
        classification_config={"max_items": 1, "max_source_chunks": 1},
    )

    assert len(calls) == 1
    assert run.metrics["candidate_count"] == 1
    assert run.metrics["selected_count"] == 1
    assert run.metrics["llm_calls"] == 1
    assert run.skipped_count == 0


def test_classification_batch_size_controls_llm_call_count() -> None:
    batch_lengths: list[int] = []

    class BatchLLM:
        def complete(self, prompt: str, **_kwargs: Any) -> SimpleNamespace:
            payload = json.loads(prompt.split("INPUT_JSON:\n", 1)[1])
            keys = [item["classification_key"] for item in payload["context_items"]]
            batch_lengths.append(len(keys))
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "decisions": [
                            {
                                "classification_key": key,
                                "constraint_relevance": "medium",
                                "target_relevance": "high",
                                "semantic_conflict_candidate": False,
                                "review_required": False,
                                "reason_for_current_task": "batched",
                            }
                            for key in keys
                        ]
                    }
                )
            )

    query = "Auth Login を見直す"
    candidates = [
        classification_candidate_for_item(
            {
                "source_section_id": f"docs/spec/auth.md#auth-login-{index}",
                "source_hash": f"hash-{index}",
                "source_span": f"{index + 1}-{index + 2}",
                "excerpt": f"OAuth is required {index}.",
                "constraint_relevance": "medium",
                "target_relevance": "high",
            },
            item_type="source_section",
            query=query,
        )
        for index in range(5)
    ]

    run = classify_candidates_by_priority(
        candidates,
        query=query,
        llm=BatchLLM(),
        classification_budget={"remaining": 5, "skipped": 0, "llm_calls": 0},
        fallback_on_error=False,
        classification_cache={},
        classification_config={
            "max_items": 5,
            "max_source_chunks": 5,
            "batch_size": 2,
        },
    )

    assert batch_lengths == [2, 2, 1]
    assert run.metrics["llm_calls"] == 3
    assert run.metrics["selected_count"] == 5


def test_persistent_classification_cache_hits_before_budget_consumption(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class CountingLLM:
        def complete(self, prompt: str, **_kwargs: Any) -> SimpleNamespace:
            calls.append(prompt)
            payload = json.loads(prompt.split("INPUT_JSON:\n", 1)[1])
            key = payload["context_items"][0]["classification_key"]
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "decisions": [
                            {
                                "classification_key": key,
                                "constraint_relevance": "medium",
                                "target_relevance": "high",
                                "semantic_conflict_candidate": False,
                                "review_required": False,
                                "reason_for_current_task": "cached source",
                            }
                        ]
                    }
                )
            )

    config = {
        "classification": {
            "provider": "codex",
            "model": "gpt-test",
            "cache_enabled": True,
            "cache_path": ".spec-grag/cache/classification_cache.json",
        }
    }
    query = "Auth Login を見直す"
    candidate = classification_candidate_for_item(
        {
            "source_section_id": "docs/spec/auth.md#auth-login",
            "source_hash": "hash-auth",
            "source_span": "4-8",
            "excerpt": "OAuth is required.",
            "constraint_relevance": "medium",
            "target_relevance": "high",
        },
        item_type="source_section",
        query=query,
    )
    first_cache = load_persistent_classification_cache(tmp_path, config)

    first = classify_candidates_by_priority(
        [candidate],
        query=query,
        llm=CountingLLM(),
        classification_budget={"remaining": 1, "skipped": 0, "llm_calls": 0},
        fallback_on_error=False,
        classification_cache={},
        classification_config={**config["classification"], "max_source_chunks": 1},
        persistent_cache=first_cache,
    )
    save_persistent_classification_cache(first_cache)

    second_cache = load_persistent_classification_cache(tmp_path, config)
    second_budget = {"remaining": 1, "skipped": 0, "llm_calls": 0}
    second = classify_candidates_by_priority(
        [candidate],
        query=query,
        llm=CountingLLM(),
        classification_budget=second_budget,
        fallback_on_error=False,
        classification_cache={},
        classification_config={**config["classification"], "max_source_chunks": 1},
        persistent_cache=second_cache,
    )

    assert first.metrics["llm_calls"] == 1
    assert first.metrics["cache_hit_count"] == 0
    assert second.metrics["llm_calls"] == 0
    assert second.metrics["cache_hit_count"] == 1
    assert second_budget["remaining"] == 1
    assert len(calls) == 1
    cached_item = next(iter(second.items_by_key.values()))
    assert cached_item["classification_cache_hit"] is True
    assert cached_item["classification_cache_scope"] == "persistent"


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

    readiness = evaluate_grag_readiness(tmp_path, config())
    diagnostics = readiness.artifact_diagnostics

    assert diagnostics["active_revision"]["graph_revision"] == (
        first.freshness_report.graph_revision
    )
    assert diagnostics["staging_revisions"] == []
    assert diagnostics["failed_revisions"][0]["failed_stage"] == "concept_diff"
    assert diagnostics["failed_revisions"][0]["graph_revision"] != (
        first.freshness_report.graph_revision
    )
    assert diagnostics["failed_revisions"][0]["staging_path_exists"] is False


def test_artifact_revision_is_required_for_freshness(tmp_path: Path) -> None:
    write_auth_source(tmp_path, "# Auth\n\n## Login\n\nOAuth is required.\n")
    first = run_core_update(tmp_path, config(), all_sources=True)
    graph_dir = tmp_path / ".spec-grag/graph"
    revision_path = graph_dir / ARTIFACT_REVISION_FILENAME

    assert first.status == ResultStatus.OK
    assert revision_path.exists()

    revision_path.unlink()
    stale = evaluate_grag_readiness(tmp_path, config())

    assert stale.status.value == "stale"
    assert "artifact_missing" in stale.stale_reason_codes
    assert any(
        reason.code == "artifact_missing"
        and ARTIFACT_REVISION_FILENAME in reason.details["artifacts"]
        for reason in stale.reasons
    )

    repaired = run_core_update(tmp_path, config(), all_sources=False)

    assert repaired.status == ResultStatus.OK
    assert revision_path.exists()
