"""Lightweight `/spec-realign` public API.

`/spec-realign` deliberately keeps Answer generation outside this package.
The caller supplies Agent-generated constraints and an Agent-generated answer
candidate; this module validates the gate via `/spec-inject` and structures the
answer into the externally defined sections.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from spec_grag.inject import SpecInjectError, run_spec_inject


ANSWER_CONSTRAINTS_LABEL = "今回守る制約"
ANSWER_TARGETS_LABEL = "今回扱う修正候補または検討対象"
ANSWER_REVIEW_LABEL = "競合 / 不確実性 / 人間レビューが必要な点"
ANSWER_FINAL_LABEL = "課題プロンプトへの回答または修正案"

ANSWER_LABELS = (
    ANSWER_CONSTRAINTS_LABEL,
    ANSWER_TARGETS_LABEL,
    ANSWER_REVIEW_LABEL,
    ANSWER_FINAL_LABEL,
)

CONFLICT_DECLARATION_KEYS = (
    "conflicts",
    "conflict",
    "declared_conflicts",
    "uncertainty",
    "uncertainties",
    "human_review",
    "human_review_items",
    "human_review_required",
    "review_items",
    "violations",
    "violation",
    "constraint_violations",
    "violates_constraints",
)
class SpecRealignError(ValueError):
    """Raised when `/spec-realign` inputs are invalid."""


def run_spec_realign(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
    agent_answer: Any | None = None,
    answer: Any | None = None,
    generated_answer: Any | None = None,
    answer_candidate: Any | None = None,
    freshness_report: Mapping[str, Any] | Any | None = None,
    freshness: Mapping[str, Any] | Any | None = None,
    provider: Any = None,
    llm_provider: Any = None,
    generated_at: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Return a RealignResult that structures the Agent-supplied answer.

    `provider` and `llm_provider` are accepted for API compatibility only.
    They are passed through to `/spec-inject`, which deliberately ignores them;
    `/spec-realign` never calls a `[llm]` provider or synthesizes an answer.
    Per §5.3 / §8.5 / §9.1 / §9.2 the constraint generation, task prompt and
    conversation context interpretation, and clarification judgement are
    Agent / LLM responsibilities and are not consumed by the CLI. The CLI
    only enforces the freshness gate and structures the Agent answer into
    the RealignResult layout.
    """

    project = _project_root(project_root, root=root, cwd=cwd)

    try:
        inject_result = run_spec_inject(
            project_root=project,
            root=root,
            cwd=cwd,
            freshness_report=freshness_report,
            freshness=freshness,
            provider=provider,
            llm_provider=llm_provider,
            generated_at=generated_at,
            **extra,
        )
    except SpecInjectError as exc:
        raise SpecRealignError(str(exc)) from exc

    inject_payload = _jsonable(inject_result)
    if not isinstance(inject_payload, Mapping):
        raise SpecRealignError("run_spec_inject must return a mapping-like result")
    inject_payload = dict(inject_payload)

    if _is_stopped(inject_payload):
        return _stopped_from_inject(inject_payload, project_root=project, generated_at=generated_at)

    selected_answer = _first_answer(agent_answer, answer, generated_answer, answer_candidate)
    if selected_answer is None:
        return _needs_answer_result(
            project_root=project,
            generated_at=generated_at,
            inject_result=inject_payload,
        )

    structured_answer = structure_realign_answer(
        selected_answer,
        inject_result=inject_payload,
    )

    return {
        "command": "/spec-realign",
        "project_root": project.as_posix(),
        "status": inject_payload.get("status"),
        "freshness_report": deepcopy(inject_payload.get("freshness_report") or {}),
        "blocking_reasons": list(inject_payload.get("blocking_reasons") or []),
        "warnings": list(inject_payload.get("warnings") or []),
        "recommended_next_action": inject_payload.get("recommended_next_action"),
        "generated_at": generated_at,
        "should_stop": False,
        "stops": False,
        "blocked": False,
        "can_continue": True,
        "answer": structured_answer,
        "realign_answer": structured_answer,
        "inject_result": inject_payload,
        "labels": {
            "constraints": ANSWER_CONSTRAINTS_LABEL,
            "targets": ANSWER_TARGETS_LABEL,
            "review": ANSWER_REVIEW_LABEL,
            "answer": ANSWER_FINAL_LABEL,
        },
    }


def structure_realign_answer(
    answer_candidate: Any,
    *,
    inject_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize an Agent-generated Answer into the RealignResult 4-section layout.

    Per §8.5 / §9.3 the Agent supplies the constraints inside the answer
    candidate (in `ANSWER_CONSTRAINTS_LABEL` or a similarly-named section).
    The CLI does not validate constraint content; it only re-shapes the
    answer into the canonical 4-section layout for downstream consumers.
    """

    if answer_candidate is None:
        raise SpecRealignError("agent_answer is required for /spec-realign")

    raw_candidate = _jsonable(answer_candidate)
    sections = _section_source(raw_candidate)

    if isinstance(sections, Mapping):
        constraints_section = _first_present(
            sections,
            ANSWER_CONSTRAINTS_LABEL,
            "constraints",
            "constraint_set",
            "guardrails",
        )
        targets_section = _first_present(
            sections,
            ANSWER_TARGETS_LABEL,
            "targets",
            "target",
            "scope",
            "change_candidates",
            "candidates",
            "modification_candidates",
        )
        review_section = _first_present(
            sections,
            ANSWER_REVIEW_LABEL,
            "human_review",
            "human_review_items",
            "uncertainty",
            "uncertainties",
            "conflicts",
            "violations",
            "constraint_violations",
        )
        final_section = _first_present(
            sections,
            ANSWER_FINAL_LABEL,
            "answer",
            "final_answer",
            "generated_answer",
            "response",
            "proposal",
            "patch",
            "solution",
        )
    else:
        constraints_section = None
        targets_section = None
        review_section = None
        final_section = raw_candidate

    if _is_blank(final_section):
        raise SpecRealignError(
            "agent_answer must include a non-empty answer or proposal section"
        )

    declared_review = _declared_review_items(raw_candidate)
    inferred_review = (
        []
        if declared_review or not _is_blank(review_section)
        else _conflict_lines(final_section)
    )
    review_items = _merge_review_items(
        review_section,
        declared_review,
        inferred_review,
    )

    return {
        ANSWER_CONSTRAINTS_LABEL: _normalize_section(constraints_section),
        ANSWER_TARGETS_LABEL: (
            _normalize_section(targets_section)
            if not _is_blank(targets_section)
            else _default_targets(inject_result=inject_result)
        ),
        ANSWER_REVIEW_LABEL: _normalize_review_section(review_items),
        ANSWER_FINAL_LABEL: _normalize_section(final_section),
    }


def _stopped_from_inject(
    inject_result: Mapping[str, Any],
    *,
    project_root: Path,
    generated_at: str | None,
) -> dict[str, Any]:
    result = {
        **deepcopy(dict(inject_result)),
        "command": "/spec-realign",
        "project_root": project_root.as_posix(),
        "generated_at": generated_at,
        "should_stop": True,
        "stops": True,
        "blocked": True,
        "can_continue": False,
        "constraints": [],
        "inject_result": deepcopy(dict(inject_result)),
    }
    result.pop("answer", None)
    result.pop("realign_answer", None)
    return result


def _needs_answer_result(
    *,
    project_root: Path,
    generated_at: str | None,
    inject_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "command": "/spec-realign",
        "project_root": project_root.as_posix(),
        "status": inject_result.get("status"),
        "freshness_report": deepcopy(inject_result.get("freshness_report") or {}),
        "blocking_reasons": list(inject_result.get("blocking_reasons") or []),
        "warnings": list(inject_result.get("warnings") or []),
        "recommended_next_action": (
            "provide an Agent-generated answer candidate for /spec-realign"
        ),
        "generated_at": generated_at,
        "should_stop": True,
        "stops": True,
        "blocked": True,
        "can_continue": False,
        "stop_reason": "needs_agent_answer",
        "reasons": ["needs_agent_answer"],
        "inject_result": deepcopy(dict(inject_result)),
    }


def _section_source(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return value
    for key in ("sections", "answer_sections", "realign_answer", "answer"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            return nested
    return value


def _declared_review_items(value: Any) -> list[Any]:
    items: list[Any] = []
    _collect_declared_review_items(value, items)
    return items


def _collect_declared_review_items(value: Any, items: list[Any]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in CONFLICT_DECLARATION_KEYS:
                if item is not False and not _is_blank(item):
                    items.extend(_declared_items_for_key(key_text, item))
                continue
            _collect_declared_review_items(item, items)
    elif _is_sequence(value):
        for item in value:
            _collect_declared_review_items(item, items)


def _declared_items_for_key(key: str, value: Any) -> list[Any]:
    if value is True:
        return [{key: True}]
    if _is_sequence(value):
        return [deepcopy(item) for item in value]
    return [deepcopy(value)]


def _conflict_lines(value: Any) -> list[str]:
    text = _plain_text(value)
    if not text:
        return []
    keywords = (
        "conflict",
        "conflicts",
        "violate",
        "violates",
        "violation",
        "uncertain",
        "uncertainty",
        "human review",
        "矛盾",
        "競合",
        "違反",
        "不確実",
        "人間レビュー",
        "レビューが必要",
    )
    lines: list[str] = []
    for raw_line in text.replace("。", "。\n").splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if line and any(keyword in lowered for keyword in keywords):
            if line not in lines:
                lines.append(line)
    return lines


def _merge_review_items(*values: Any) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for value in values:
        for item in _as_items(value):
            key = _stable_key(item)
            if key in seen:
                continue
            merged.append(item)
            seen.add(key)
    return merged


def _normalize_review_section(value: Any) -> Any:
    items = _as_items(value)
    if not items:
        return []
    return [_jsonable(item) for item in items]


def _default_targets(
    *,
    inject_result: Mapping[str, Any] | None,
) -> list[Any]:
    del inject_result
    return []


def _normalize_section(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return _jsonable(value)


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and not _is_blank(mapping.get(key)):
            return mapping.get(key)
    return None


def _first_answer(*values: Any) -> Any | None:
    for value in values:
        if value is None or _is_blank(value):
            continue
        return value
    return None


def _is_stopped(result: Mapping[str, Any]) -> bool:
    for key in ("should_stop", "stops", "blocked", "stop"):
        value = result.get(key)
        if isinstance(value, bool):
            return value
    for key in ("can_continue", "should_continue"):
        value = result.get(key)
        if isinstance(value, bool):
            return not value
    status = str(result.get("status") or _mapping_get(result, "freshness_report", "status") or "")
    return status in {"blocked", "failed"}


def _project_root(
    project_root: str | Path = ".",
    *,
    root: str | Path | None,
    cwd: str | Path | None,
) -> Path:
    selected = project_root if project_root != "." else root or cwd or project_root
    return Path(selected).expanduser().resolve()


def _mapping_get(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _as_items(value: Any) -> list[Any]:
    if _is_blank(value):
        return []
    if isinstance(value, list):
        return [deepcopy(item) for item in value]
    if isinstance(value, tuple):
        return [deepcopy(item) for item in value]
    if isinstance(value, set):
        return sorted(deepcopy(item) for item in value)
    return [deepcopy(value)]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, Mapping):
        return not value
    return _is_sequence(value) and not value


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(f"{key} {_plain_text(item)}" for key, item in value.items())
    if _is_sequence(value):
        return " ".join(_plain_text(item) for item in value)
    return str(value)


def _stable_key(value: Any) -> str:
    return repr(_jsonable(value))


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _jsonable(vars(value))
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if _is_sequence(value):
        return [_jsonable(item) for item in value]
    return value


spec_realign = run_spec_realign
run_realign = run_spec_realign
realign = run_spec_realign
execute_spec_realign = run_spec_realign


__all__ = [
    "SpecRealignError",
    "ANSWER_CONSTRAINTS_LABEL",
    "ANSWER_TARGETS_LABEL",
    "ANSWER_REVIEW_LABEL",
    "ANSWER_FINAL_LABEL",
    "ANSWER_LABELS",
    "run_spec_realign",
    "spec_realign",
    "run_realign",
    "realign",
    "execute_spec_realign",
    "structure_realign_answer",
]
