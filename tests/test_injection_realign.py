from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spec_grag.concept_diff import (
    ConceptDiffTaskContext,
    PendingConceptDiff,
    PendingConceptHunk,
    concept_file_hash,
    create_pending_concept_diff,
)
from spec_grag.manifest import build_current_section_manifest, load_source_manifest
from spec_grag.protocol import (
    AgenticSearchCandidate,
    Command,
    ExpectedUse,
    ResultEnvelope,
    ResultStatus,
    ResultType,
    SearchRequest,
    SearchTarget,
)
from spec_grag.injection import (
    conflict_notes_for,
    invalid_agentic_reason,
    review_notes_for_semantic_candidates,
)
from spec_grag.realign import generate_realign_answer


def write_config(project_root: Path) -> None:
    config_dir = project_root / ".spec-grag"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        """
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[graph]
storage = ".spec-grag/graph/"
""".strip(),
        encoding="utf-8",
    )


def write_docs(project_root: Path) -> None:
    spec = project_root / "docs/spec/auth.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# Auth\n\nIntro.\n\n## Login\n\nOAuth is required.\n", encoding="utf-8")
    core = project_root / "docs/core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "purpose.md").write_text("# Purpose\nKeep users secure.\n", encoding="utf-8")
    (core / "concept.md").write_text("# Concept\nAuth protects sessions.\n", encoding="utf-8")


def request_payload(
    project_root: Path,
    command: str,
    *,
    task_prompt: str | None = None,
    explicit_files: list[str] | None = None,
    candidates: list[dict] | None = None,
) -> dict:
    return {
        "command": command,
        "project_root": str(project_root),
        "task_prompt": task_prompt,
        "conversation_context": {
            "current_user_message": task_prompt or "Auth Login を見直す",
            "recent_messages": [],
            "working_target": explicit_files[0] if explicit_files else None,
            "explicit_files": explicit_files or [],
        },
        "agentic_search_candidates": candidates or [],
        "agent_capabilities": {
            "can_read_source": True,
            "can_answer": command == "spec-realign",
        },
        "options": {"output_format": "json"},
    }


def run_cli(payload: dict) -> ResultEnvelope:
    env = os.environ.copy()
    env["SPEC_GRAG_SMOKE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=json.dumps(payload),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return ResultEnvelope.from_json(result.stdout)


def write_duplicate_excerpt_spec(project_root: Path) -> None:
    spec = project_root / "docs/spec/auth.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(
        "# Auth\n\n## Login\n\nOAuth is required.\n\nOAuth is required.\n",
        encoding="utf-8",
    )


def agentic_reason_for(
    project_root: Path,
    *,
    excerpt: str,
    source_span: str | None,
    source_hash: str | None = None,
) -> str | None:
    spec = project_root / "docs/spec/auth.md"
    manifest = build_current_section_manifest(project_root, [spec])
    section = manifest.by_section_id()["docs/spec/auth.md#auth-login"]
    request = SearchRequest(
        request_id="search:test",
        reason="test",
        target=SearchTarget(section_id=section.section_id),
        expected_use=ExpectedUse.TARGET,
    )
    candidate = AgenticSearchCandidate(
        request_id=request.request_id,
        source_document_id=section.document_id,
        source_section_id=section.section_id,
        excerpt=excerpt,
        source_span=source_span,
        reason="test",
        source_hash=source_hash if source_hash is not None else section.source_hash,
    )
    return invalid_agentic_reason(
        candidate, {request.request_id: request}, manifest, project_root
    )


def test_spec_inject_runs_core_incremental_and_returns_structured_context(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    payload = request_payload(
        tmp_path,
        "spec-inject",
        task_prompt="Auth Login を見直す",
        explicit_files=["docs/spec/auth.md"],
    )

    envelope = run_cli(payload)

    assert envelope.status == ResultStatus.OK
    assert envelope.result_type == ResultType.INJECTION_CONTEXT
    assert envelope.execution.context_ready is True
    assert envelope.payload.constraint_context.purpose_constraints
    assert envelope.payload.constraint_context.concept_constraints
    assert envelope.payload.constraint_context.chapter_anchor_constraints
    assert envelope.payload.target_context.related_source_sections
    assert (tmp_path / ".spec-grag/graph/source_manifest.json").exists()


def test_spec_inject_merges_concept_index_graph_vector_and_cluster_candidates(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)

    envelope = run_cli(
        request_payload(
            tmp_path,
            "spec-inject",
            task_prompt="Auth Login を安全に見直す",
            explicit_files=["docs/spec/auth.md"],
        )
    )

    concept = envelope.payload.constraint_context.concept_constraints[0]
    assert concept["source_origin"] == "CoreConceptIndex"
    assert concept["concept_chunk_id"].startswith("concept:")
    assert concept["classification_source"] == "orchestrator_rule_based"

    related_entities = envelope.payload.target_context.related_entities
    assert any(item["entity_type"] == "ANCHOR" for item in related_entities)
    assert any(item["entity_type"] == "CLUSTER" for item in related_entities)
    cluster = next(item for item in related_entities if item["entity_type"] == "CLUSTER")
    assert "community_report" in cluster["retrieval_methods"]
    assert cluster["community_report"]["summary"]
    assert cluster["community_report"]["source_evidence"]
    assert any("raw_chunk_hybrid" in item.get("retrieval_methods", []) for item in related_entities)
    assert envelope.payload.target_context.related_source_sections[0]["excerpt"]
    assert envelope.payload.target_context.related_source_sections[0]["source_span"]
    assert envelope.payload.target_context.classification_notes

    graph_text = (tmp_path / ".spec-grag/graph/property_graph_store.json").read_text(
        encoding="utf-8"
    )
    assert "classification_source" not in graph_text
    assert "constraint_relevance" not in graph_text


def test_spec_inject_blocks_on_unapproved_concept_diff(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    concept_file = tmp_path / "docs/core/concept.md"
    diff = PendingConceptDiff(
        diff_id="diff-1",
        base_concept_hash=concept_file_hash(concept_file),
        task_context=ConceptDiffTaskContext(
            command=Command.SPEC_CORE,
            changed_source_section_ids=["docs/spec/auth.md#auth"],
            extract_run_id="run-1",
        ),
        hunks=[
            PendingConceptHunk(
                hunk_id="hunk-1",
                file="docs/core/concept.md",
                old_range="-1,2",
                new_range="+1,2",
                diff_text="@@ -1,2 +1,2 @@\n # Concept\n-Auth protects sessions.\n+Auth protects all sessions.\n",
            )
        ],
    )
    create_pending_concept_diff(tmp_path / ".spec-grag/pending", diff)

    envelope = run_cli(request_payload(tmp_path, "spec-inject"))

    assert envelope.status == ResultStatus.BLOCKED
    assert envelope.result_type == ResultType.CONCEPT_APPROVAL_REQUIRED_RESULT
    assert envelope.execution.pending_concept_diff_id == "diff-1"


def test_spec_inject_need_more_context_loop_and_agentic_validation(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    spec = tmp_path / "docs/spec/auth.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# Auth\n\n## Login\n\nOAuth is required.\n", encoding="utf-8")
    first = run_cli(
        request_payload(
            tmp_path,
            "spec-inject",
            task_prompt="Billing flow を確認する",
        )
    )
    assert first.status == ResultStatus.BLOCKED
    assert first.result_type == ResultType.NEED_MORE_CONTEXT_RESULT
    assert len(first.payload.search_requests) >= 3
    request_id = first.payload.search_requests[0].request_id
    manifest = load_source_manifest(tmp_path / ".spec-grag/graph/source_manifest.json")
    section = manifest.by_section_id()["docs/spec/auth.md#auth-login"]

    bad = run_cli(
        request_payload(
            tmp_path,
            "spec-inject",
            task_prompt="Billing flow を確認する",
            candidates=[
                {
                    "request_id": request_id,
                    "source_document_id": section.document_id,
                    "source_section_id": section.section_id,
                    "excerpt": "OAuth is required.",
                    "reason": "test",
                    "source_hash": "stale",
                }
            ],
        )
    )
    assert bad.status == ResultStatus.BLOCKED

    good = run_cli(
        request_payload(
            tmp_path,
            "spec-inject",
            task_prompt="Billing flow を確認する",
            candidates=[
                {
                    "request_id": request_id,
                    "source_document_id": section.document_id,
                    "source_section_id": section.section_id,
                    "excerpt": "OAuth is required.",
                    "reason": "test",
                    "source_hash": section.source_hash,
                }
            ],
        )
    )
    assert good.status == ResultStatus.DEGRADED
    assert good.result_type == ResultType.INJECTION_CONTEXT
    assert good.payload.target_context.candidate_targets[0]["source_origin"] == "AgenticSearch"


def test_spec_inject_rejects_agentic_excerpt_that_does_not_resolve(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    spec = tmp_path / "docs/spec/auth.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# Auth\n\n## Login\n\nOAuth is required.\n", encoding="utf-8")
    first = run_cli(
        request_payload(tmp_path, "spec-inject", task_prompt="Billing flow を確認する")
    )
    request_id = first.payload.search_requests[0].request_id
    manifest = load_source_manifest(tmp_path / ".spec-grag/graph/source_manifest.json")
    section = manifest.by_section_id()["docs/spec/auth.md#auth-login"]

    core = tmp_path / "docs/core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "purpose.md").write_text("# Purpose\nKeep users secure.\n", encoding="utf-8")
    (core / "concept.md").write_text("# Concept\nBilling review.\n", encoding="utf-8")

    envelope = run_cli(
        request_payload(
            tmp_path,
            "spec-inject",
            task_prompt="Billing flow を確認する",
            candidates=[
                {
                    "request_id": request_id,
                    "source_document_id": section.document_id,
                    "source_section_id": section.section_id,
                    "excerpt": "This excerpt is not in the source.",
                    "reason": "test",
                    "source_hash": section.source_hash,
                }
            ],
        )
    )

    assert envelope.result_type == ResultType.INJECTION_CONTEXT
    assert any(
        note["reason"] == "excerpt_not_found_in_source_section"
        for note in envelope.payload.review_notes
    )


def test_agentic_source_span_accepts_duplicate_excerpt_when_span_is_valid(
    tmp_path: Path,
) -> None:
    write_duplicate_excerpt_spec(tmp_path)

    assert (
        agentic_reason_for(
            tmp_path,
            excerpt="OAuth is required.",
            source_span="5-5",
        )
        is None
    )


def test_agentic_source_span_accepts_single_line_char_range_format(
    tmp_path: Path,
) -> None:
    write_duplicate_excerpt_spec(tmp_path)

    assert (
        agentic_reason_for(
            tmp_path,
            excerpt="OAuth is required.",
            source_span="[5:1-18]",
        )
        is None
    )


def test_agentic_excerpt_without_span_is_ambiguous_when_duplicate(
    tmp_path: Path,
) -> None:
    write_duplicate_excerpt_spec(tmp_path)

    assert (
        agentic_reason_for(
            tmp_path,
            excerpt="OAuth is required.",
            source_span=None,
        )
        == "ambiguous_excerpt_in_source_section"
    )


def test_agentic_source_span_must_stay_inside_section(tmp_path: Path) -> None:
    write_duplicate_excerpt_spec(tmp_path)

    assert (
        agentic_reason_for(
            tmp_path,
            excerpt="OAuth is required.",
            source_span="1-1",
        )
        == "source_span_out_of_section_range"
    )


def test_agentic_source_span_must_contain_excerpt(tmp_path: Path) -> None:
    write_duplicate_excerpt_spec(tmp_path)

    assert (
        agentic_reason_for(
            tmp_path,
            excerpt="OAuth is required.",
            source_span="6-6",
        )
        == "excerpt_not_found_in_source_span"
    )


def test_agentic_source_span_rejects_invalid_range(tmp_path: Path) -> None:
    write_duplicate_excerpt_spec(tmp_path)

    assert (
        agentic_reason_for(
            tmp_path,
            excerpt="OAuth is required.",
            source_span="7-5",
        )
        == "invalid_source_span_range"
    )


def test_conflict_validator_does_not_promote_semantic_candidate_alone() -> None:
    conflicts = conflict_notes_for(
        [],
        [],
        classified_items=[
            {"excerpt": "OAuth is required."},
            {"excerpt": "OAuth is optional."},
        ],
    )
    assert conflicts[0]["conflict"] is True
    assert conflicts[0]["validator_stage"] == "rule_based"

    review_notes = review_notes_for_semantic_candidates(
        [
            {
                "entity_id": "anchor:auth",
                "source_origin": "ClassificationLLM",
                "semantic_conflict_candidate": True,
            }
        ]
    )
    assert review_notes
    assert "requires_validator" in review_notes[0]["reason"]


def test_llm_semantic_candidate_requires_review_without_hard_conflict() -> None:
    item = {
        "entity_id": "anchor:policy",
        "source_origin": "classification_llm",
        "excerpt": "This may need business review for edge-case access.",
        "semantic_conflict_candidate": True,
        "classification_source": "classification_llm",
    }

    conflicts = conflict_notes_for([], [], classified_items=[item])
    review_notes = review_notes_for_semantic_candidates([item])

    assert conflicts == []
    assert review_notes == [
        {
            "source_origin": "classification_llm",
            "reason": "semantic_conflict_candidate_requires_validator_or_human_approval",
            "item_id": "anchor:policy",
            "review_required": True,
        }
    ]


@pytest.mark.parametrize(
    ("excerpt", "rule_id"),
    [
        ("管理者のみが承認できる。全ユーザーが承認できる。", "permission_scope"),
        ("必要 状態 draft -> approved。禁止 状態 draft -> approved。", "state_transition"),
        ("下限は10。上限は5。", "numeric_bounds"),
    ],
)
def test_conflict_validator_detects_japanese_rule_pack_cases(
    excerpt: str,
    rule_id: str,
) -> None:
    conflicts = conflict_notes_for([], [], classified_items=[{"excerpt": excerpt}])

    assert rule_id in {item.get("rule_id") for item in conflicts}


def test_conflict_validator_detects_japanese_quantifier_conflict() -> None:
    conflicts = conflict_notes_for(
        [],
        [],
        classified_items=[{"excerpt": "全ての申請を承認する。一部の申請だけ承認する。"}],
    )

    assert any(
        item.get("reason") == "Japanese opposing quantifiers appeared in selected evidence."
        for item in conflicts
    )


def test_spec_realign_builds_context_then_structured_answer(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    envelope = run_cli(
        request_payload(
            tmp_path,
            "spec-realign",
            task_prompt="Auth Login を安全に見直す",
            explicit_files=["docs/spec/auth.md"],
        )
    )

    assert envelope.status == ResultStatus.OK
    assert envelope.result_type == ResultType.REALIGN_RESULT
    assert envelope.execution.context_ready is True
    assert envelope.payload.injection_context.target_context.related_source_sections
    assert "今回の回答で守る制約" in envelope.payload.answer
    assert "課題プロンプトへの回答または修正案" in envelope.payload.answer


def test_answer_generation_does_not_read_raw_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    from spec_grag.protocol import FreshnessReport, InjectionContext

    def forbidden(*args, **kwargs):
        raise AssertionError("raw source read in answer phase")

    monkeypatch.setattr(Path, "read_text", forbidden)
    context = InjectionContext(
        conversation_context_summary="summary",
        freshness_report=FreshnessReport(graph_storage_path=".spec-grag/graph"),
    )

    answer = generate_realign_answer("task", context)

    assert "今回の回答で守る制約" in answer
