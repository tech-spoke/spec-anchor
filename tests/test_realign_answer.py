from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from spec_grag.protocol import FreshnessReport, InjectionContext
from spec_grag.realign import (
    AnswerNeedsMoreContext,
    AnswerSections,
    build_answer_prompt,
    generate_realign_answer,
    make_answer_llm_from_config,
)
from spec_grag.llm_adapters import ClaudeCLIAdapter, CodexCLIAdapter


class FakeAnswerLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.prompt: str | None = None
        self.output_schema: Any = None

    def complete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        self.prompt = prompt
        self.output_schema = kwargs.get("output_schema")
        return SimpleNamespace(text=json.dumps(self.payload, ensure_ascii=False))


def context_with_review_and_conflict() -> InjectionContext:
    return InjectionContext(
        conversation_context_summary="Auth Login を見直す",
        constraint_context={
            "purpose_constraints": [{"summary": "Keep users secure."}],
            "concept_constraints": [{"summary": "Auth protects sessions."}],
        },
        target_context={
            "related_source_sections": [
                {"heading_path": "Auth / Login", "summary": "OAuth is required."}
            ],
        },
        conflict_notes=[
            {
                "reason": "Required and optional language appeared.",
                "conflict": True,
            }
        ],
        review_notes=[
            {
                "reason": "same_anchor_mentioned_by_multiple_sections",
                "review_required": True,
            }
        ],
        freshness_report=FreshnessReport(graph_storage_path=".spec-grag/graph"),
    )


def test_answer_llm_uses_fixed_prompt_schema_and_renders_four_sections() -> None:
    llm = FakeAnswerLLM(
        {
            "constraints": ["Keep users secure."],
            "targets": ["Auth / Login"],
            "conflicts_and_review": ["Review OAuth wording."],
            "answer": "OAuth login should remain constrained by the context.",
        }
    )
    context = context_with_review_and_conflict()

    answer = generate_realign_answer("Auth Login を安全に見直す", context, llm=llm)

    assert llm.output_schema is AnswerSections
    assert llm.prompt is not None
    assert "Do not read raw source files" in llm.prompt
    assert "Do not use tools" in llm.prompt
    assert "INPUT_JSON" in llm.prompt
    assert "今回の回答で守る制約" in answer
    assert "今回の回答で扱う修正候補または検討対象" in answer
    assert "競合 / 不確実性 / 人間レビューが必要な点" in answer
    assert "課題プロンプトへの回答または修正案" in answer
    assert "OAuth login should remain constrained" in answer


def test_answer_does_not_hide_conflict_or_review_notes() -> None:
    llm = FakeAnswerLLM(
        {
            "constraints": ["Keep users secure."],
            "targets": ["Auth / Login"],
            "conflicts_and_review": [],
            "answer": "Proceed carefully.",
        }
    )

    answer = generate_realign_answer("Auth Login", context_with_review_and_conflict(), llm=llm)

    assert "Required and optional language appeared." in answer
    assert "same_anchor_mentioned_by_multiple_sections" in answer


def test_answer_llm_can_block_for_more_context() -> None:
    llm = FakeAnswerLLM(
        {
            "constraints": [],
            "targets": [],
            "conflicts_and_review": [],
            "answer": "",
            "needs_more_context": True,
            "missing_context": ["Need confirmed billing section."],
        }
    )

    with pytest.raises(AnswerNeedsMoreContext) as exc:
        generate_realign_answer("Billing", context_with_review_and_conflict(), llm=llm)

    assert exc.value.missing_context == ["Need confirmed billing section."]


def test_answer_provider_config_builds_codex_and_claude_adapters() -> None:
    codex = make_answer_llm_from_config(
        {
            "answer": {
                "provider": "codex",
                "command": "codex-dev",
                "model": "gpt-test",
                "timeout_sec": 42,
            }
        }
    )
    claude = make_answer_llm_from_config(
        {
            "answer": {
                "provider": "claude",
                "command": "claude-dev",
                "model": "sonnet",
                "timeout_sec": 33,
            }
        }
    )

    assert isinstance(codex, CodexCLIAdapter)
    assert codex.command == "codex-dev"
    assert codex.model == "gpt-test"
    assert codex.timeout_sec == 42
    assert codex.sandbox == "read-only"
    assert isinstance(claude, ClaudeCLIAdapter)
    assert claude.command == "claude-dev"
    assert claude.model == "sonnet"
    assert claude.timeout_sec == 33
    assert claude.tools == ""


def test_template_provider_keeps_answer_boundary_promptless() -> None:
    assert make_answer_llm_from_config({}) is None
    prompt = build_answer_prompt("task", context_with_review_and_conflict())
    assert "project_root" not in prompt
    assert "raw source" in prompt
