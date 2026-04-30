"""Answer generation boundary for /spec-realign."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import Field, ValidationError, model_validator

from spec_grag.llm_adapters import CLIAdapterError, ClaudeCLIAdapter, CodexCLIAdapter
from spec_grag.protocol import InjectionContext, StrictModel


ANSWER_PROVIDER_TEMPLATE = "template"
ANSWER_PROVIDER_CODEX = "codex"
ANSWER_PROVIDER_CLAUDE = "claude"


class AnswerGenerationError(RuntimeError):
    """Raised when the Answer LLM cannot produce a valid structured answer."""


class AnswerNeedsMoreContext(RuntimeError):
    """Raised when Answer LLM says InjectionContext is insufficient."""

    def __init__(self, missing_context: list[str]) -> None:
        self.missing_context = missing_context
        super().__init__("Answer generation needs more context")


class AnswerSections(StrictModel):
    constraints: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    conflicts_and_review: list[str] = Field(default_factory=list)
    answer: str = ""
    needs_more_context: bool = False
    missing_context: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_answer_or_missing_context(self) -> AnswerSections:
        if self.needs_more_context:
            if not self.missing_context:
                raise ValueError("missing_context is required when needs_more_context=true")
            return self
        if not self.answer.strip():
            raise ValueError("answer is required when needs_more_context=false")
        return self


def make_answer_llm_from_config(config: Mapping[str, Any]) -> Any | None:
    answer_config = _mapping(config.get("answer"))
    provider = str(answer_config.get("provider", ANSWER_PROVIDER_TEMPLATE)).strip().lower()
    if provider in {ANSWER_PROVIDER_TEMPLATE, "deterministic", "none", "disabled", ""}:
        return None
    if provider == ANSWER_PROVIDER_CODEX:
        return CodexCLIAdapter(
            command=str(answer_config.get("command") or "codex"),
            model=str(answer_config.get("model") or "gpt-5.4"),
            timeout_sec=int(answer_config.get("timeout_sec", 120)),
            sandbox=str(answer_config.get("sandbox", "read-only")),
            max_retries=int(answer_config.get("max_retries", 0)),
            retry_backoff_sec=float(answer_config.get("retry_backoff_sec", 0.0)),
            repair_on_schema_failure=bool(
                answer_config.get("repair_on_schema_failure", True)
            ),
        )
    if provider == ANSWER_PROVIDER_CLAUDE:
        return ClaudeCLIAdapter(
            command=str(answer_config.get("command") or "claude"),
            model=str(answer_config.get("model") or ""),
            timeout_sec=int(answer_config.get("timeout_sec", 120)),
            tools=str(answer_config.get("tools", "")),
            max_retries=int(answer_config.get("max_retries", 0)),
            retry_backoff_sec=float(answer_config.get("retry_backoff_sec", 0.0)),
            repair_on_schema_failure=bool(
                answer_config.get("repair_on_schema_failure", True)
            ),
        )
    raise ValueError(f"unsupported answer.provider: {provider}")


def answer_failure_fallback_from_config(config: Mapping[str, Any]) -> str:
    answer_config = _mapping(config.get("answer"))
    return str(answer_config.get("failure_fallback", "failed")).strip().lower()


def generate_realign_answer(
    task_prompt: str,
    injection_context: InjectionContext,
    *,
    llm: Any | None = None,
) -> str:
    """Generate an answer from task_prompt + InjectionContext only.

    This function intentionally accepts no project_root, config, paths, tools, or
    raw source handles. Raw source reading belongs to context build, never here.
    """

    if llm is None:
        sections = deterministic_answer_sections(task_prompt, injection_context)
    else:
        sections = generate_answer_sections_with_llm(task_prompt, injection_context, llm)
    sections = ensure_conflict_and_review_visible(sections, injection_context)
    return render_answer_sections(sections)


def generate_answer_sections_with_llm(
    task_prompt: str,
    injection_context: InjectionContext,
    llm: Any,
) -> AnswerSections:
    prompt = build_answer_prompt(task_prompt, injection_context)
    try:
        response = llm.complete(prompt, output_schema=AnswerSections)
        sections = AnswerSections.model_validate_json(response.text)
    except CLIAdapterError as exc:
        raise AnswerGenerationError(f"Answer LLM adapter failed: {exc}") from exc
    except ValidationError as exc:
        raise AnswerGenerationError(f"Answer LLM output is invalid: {exc}") from exc
    except Exception as exc:
        raise AnswerGenerationError(f"Answer LLM failed: {exc}") from exc
    if sections.needs_more_context:
        raise AnswerNeedsMoreContext(sections.missing_context)
    return sections


def deterministic_answer_sections(
    task_prompt: str,
    injection_context: InjectionContext,
) -> AnswerSections:
    constraints = summarize_items(
        [
            *injection_context.constraint_context.purpose_constraints,
            *injection_context.constraint_context.concept_constraints,
            *injection_context.constraint_context.source_spec_constraints,
            *injection_context.constraint_context.chapter_anchor_constraints,
        ]
    )
    targets = summarize_items(
        [
            *injection_context.target_context.candidate_targets,
            *injection_context.target_context.related_concepts,
            *injection_context.target_context.related_source_sections,
            *injection_context.target_context.related_chapter_anchors,
            *injection_context.target_context.related_entities,
        ]
    )
    conflicts = summarize_items(injection_context.conflict_notes)
    reviews = summarize_items(
        [*injection_context.review_notes, *warning_items(injection_context.warnings)]
    )

    return AnswerSections(
        constraints=constraints or ["InjectionContext に明示された制約はありません。"],
        targets=targets or ["InjectionContext に明示された修正対象候補はありません。"],
        conflicts_and_review=conflicts
        or reviews
        or ["明示された競合・レビュー項目はありません。"],
        answer=f"{task_prompt} は、上記の制約と対象候補に限定して検討してください。",
    )


def build_answer_prompt(task_prompt: str, injection_context: InjectionContext) -> str:
    payload = {
        "task_prompt": task_prompt,
        "injection_context": injection_context.model_dump(mode="json"),
    }
    return "\n".join(
        [
            "You are the SPEC-grag Answer phase.",
            "Use only the task_prompt and InjectionContext JSON below.",
            "Do not read raw source files. Do not use tools. Do not run Agentic search.",
            "Do not treat graph relations as confirmed facts unless the InjectionContext item gives evidence.",
            "Return JSON that matches the supplied schema.",
            "The answer must have four sections: constraints, targets, conflicts_and_review, answer.",
            "Do not hide ConflictNotes or ReviewNotes; include them in conflicts_and_review.",
            "If the InjectionContext is insufficient, set needs_more_context=true and fill missing_context instead of answering.",
            "",
            "INPUT_JSON:",
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        ]
    )


def render_answer_sections(sections: AnswerSections) -> str:
    return "\n".join(
        [
            "今回の回答で守る制約:",
            render_lines(sections.constraints, "InjectionContext に明示された制約はありません。"),
            "",
            "今回の回答で扱う修正候補または検討対象:",
            render_lines(sections.targets, "InjectionContext に明示された修正対象候補はありません。"),
            "",
            "競合 / 不確実性 / 人間レビューが必要な点:",
            render_lines(
                sections.conflicts_and_review,
                "明示された競合・レビュー項目はありません。",
            ),
            "",
            "課題プロンプトへの回答または修正案:",
            sections.answer.strip(),
        ]
    )


def ensure_conflict_and_review_visible(
    sections: AnswerSections,
    injection_context: InjectionContext,
) -> AnswerSections:
    required = [
        *summarize_item_lines(injection_context.conflict_notes),
        *summarize_item_lines(injection_context.review_notes),
        *summarize_item_lines(warning_items(injection_context.warnings)),
    ]
    if not required:
        return sections
    existing = set(sections.conflicts_and_review)
    merged = list(sections.conflicts_and_review)
    for line in required:
        if line not in existing:
            merged.append(line)
            existing.add(line)
    return sections.model_copy(update={"conflicts_and_review": merged})


def summarize_items(items: list[dict[str, Any]]) -> list[str]:
    return summarize_item_lines(items)


def summarize_item_lines(items: list[dict[str, Any]]) -> list[str]:
    lines = []
    for index, item in enumerate(items[:6], start=1):
        text = (
            item.get("summary")
            or item.get("heading_path")
            or item.get("excerpt")
            or item.get("reason")
            or item.get("section_id")
            or item.get("chapter_anchor_id")
            or item.get("entity_id")
            or str(item)
        )
        lines.append(f"{index}. {text}")
    return lines


def render_lines(lines: list[str], fallback: str) -> str:
    if not lines:
        return fallback
    return "\n".join(lines)


def warning_items(warnings: list[str]) -> list[dict[str, Any]]:
    return [{"reason": warning, "review_required": True} for warning in warnings]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
