"""`/spec-realign` public API contract tests for G-13.

These tests pin the external contract for `/spec-realign`: it first applies
the same freshness and Agent-supplied constraint boundary as `/spec-inject`,
then returns an Agent-supplied answer shaped into the four required sections.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


CONFIG = """\
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[context]
storage = ".spec-grag/context"

[section]
max_heading_level = 4

[llm]
provider = "fake"
model = "fake-spec-core"
timeout_sec = 5
max_retries = 0

[embedding]
provider = "fake"
model = "fake-embedding"

[vector_store]
provider = "memory"
"""


ANSWER_SECTION_LABELS = (
    "今回守る制約",
    "今回扱う修正候補または検討対象",
    "競合 / 不確実性 / 人間レビューが必要な点",
    "課題プロンプトへの回答または修正案",
)


class ExplodingProvider:
    provider_id = "must-not-be-used-by-spec-realign"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.calls += 1
        raise AssertionError("/spec-realign must not call the configured [llm] provider")

    def judge_conflict(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.calls += 1
        raise AssertionError("/spec-realign must not run /spec-core conflict judging")


def _realign_module() -> Any:
    try:
        return importlib.import_module("spec_grag.realign")
    except ModuleNotFoundError as exc:
        if exc.name == "spec_grag.realign":
            pytest.fail("spec_grag.realign module is required for G-13 `/spec-realign`")
        raise


def _required_function(module: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail("`/spec-realign` public API is required; expected one of: " + ", ".join(names))


def _run_function() -> Any:
    return _required_function(
        _realign_module(),
        (
            "run_spec_realign",
            "spec_realign",
            "run_realign",
            "realign",
            "execute_spec_realign",
        ),
    )


def _call(func: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    supported = {
        name: value
        for name, value in kwargs.items()
        if name in signature.parameters and value is not None
    }
    try:
        return func(**supported)
    except TypeError:
        return func(*kwargs.get("_positional", ()), **supported)


def _run_spec_realign(project_root: Path, **kwargs: Any) -> Any:
    return _call(
        _run_function(),
        _positional=(project_root,),
        project_root=project_root,
        root=project_root,
        cwd=project_root,
        task_prompt=kwargs.pop("task_prompt", "認証修正案を作ってください"),
        prompt=kwargs.pop("prompt", None),
        conversation_context=kwargs.pop(
            "conversation_context",
            "認証チェックの修正案を作るという中心課題が明確な会話区間。",
        ),
        agent_constraints=kwargs.pop("agent_constraints", _valid_constraints()),
        constraints=kwargs.pop("constraints", None),
        generated_constraints=kwargs.pop("generated_constraints", None),
        agent_answer=kwargs.pop("agent_answer", _valid_answer()),
        answer=kwargs.pop("answer", None),
        answer_candidate=kwargs.pop("answer_candidate", None),
        freshness_report=kwargs.pop("freshness_report", _fresh_report()),
        freshness=kwargs.pop("freshness", None),
        provider=kwargs.pop("provider", None),
        llm_provider=kwargs.pop("llm_provider", None),
        generated_at="2026-05-06T00:00:00Z",
        **kwargs,
    )


def _write_project(project_root: Path) -> None:
    (project_root / ".spec-grag").mkdir(parents=True)
    (project_root / ".spec-grag" / "config.toml").write_text(CONFIG)
    (project_root / "docs/core").mkdir(parents=True)
    (project_root / "docs/spec").mkdir(parents=True)
    (project_root / "docs/core/purpose.md").write_text(
        "# Purpose\nShip reliable authentication behavior.\n"
    )
    (project_root / "docs/core/concept.md").write_text(
        "# Core Concept\nSource Specs are the final authority.\n"
    )
    (project_root / "docs/spec/security.md").write_text(
        "# Security\n"
        "Intro.\n\n"
        "## Authentication\n"
        "Authentication must validate sessions before privileged actions.\n\n"
        "## Session\n"
        "Sessions expire after inactivity and must be refreshed explicitly.\n"
    )


def _fresh_report() -> dict[str, Any]:
    return {"status": "fresh", "blocking_reasons": [], "warnings": []}


def _valid_constraints() -> list[dict[str, Any]]:
    return [
        {
            "statement": "Privileged actions must validate an active session first.",
            "evidence_origin": "Source Specs",
            "evidence_ref": "docs/spec/security.md#authentication",
            "support_refs": [
                {"origin": "Section Summary", "ref": "docs/spec/security.md#authentication"},
                {"origin": "Related Sections", "ref": "docs/spec/security.md#session"},
            ],
            "applicability": "Authentication design and authorization checks.",
            "uncertainty": [],
        },
        {
            "statement": "Expired sessions must be refreshed explicitly.",
            "evidence_origin": "Source Specs",
            "evidence_ref": "docs/spec/security.md#session",
            "support_refs": [{"origin": "Chapter Key Anchor", "ref": "Security"}],
            "applicability": "Session refresh behavior.",
            "uncertainty": [],
        },
    ]


def _valid_answer() -> dict[str, Any]:
    return {
        "今回守る制約": [
            "Privileged actions must validate an active session first.",
            "Expired sessions must be refreshed explicitly.",
        ],
        "今回扱う修正候補または検討対象": [
            "Add an active-session guard before privileged actions.",
            "Require explicit refresh for expired sessions.",
        ],
        "競合 / 不確実性 / 人間レビューが必要な点": [],
        "課題プロンプトへの回答または修正案": (
            "認証処理の先頭で active session を検証し、期限切れなら明示 refresh を要求する。"
        ),
    }


def _conflicting_answer() -> dict[str, Any]:
    return {
        "今回守る制約": ["Privileged actions must validate an active session first."],
        "今回扱う修正候補または検討対象": [
            "During migration, allow privileged actions without active-session validation."
        ],
        "競合 / 不確実性 / 人間レビューが必要な点": [
            "The migration shortcut conflicts with the Source Specs session-validation constraint."
        ],
        "課題プロンプトへの回答または修正案": (
            "移行中だけ検証を省略する案は制約と矛盾するため、人間レビュー対象として扱う。"
        ),
    }


def _conflict_review_constraint(
    *,
    status: str = "resolved",
    stale_resolution: bool = False,
    reflection_status: str = "reflected",
    valid_scope: str = "global",
) -> dict[str, Any]:
    return {
        "statement": "Use the human-approved active-session rule from conflict-auth-session.",
        "evidence_origin": "Conflict Review Item",
        "evidence_ref": "conflict-auth-session",
        "support_refs": [
            {"origin": "Source Specs", "ref": "docs/spec/security.md#authentication"}
        ],
        "applicability": "Authentication migration behavior.",
        "uncertainty": [],
        "status": status,
        "stale_resolution": stale_resolution,
        "reflection_status": reflection_status,
        "valid_scope": valid_scope,
        "human_decision": "Prefer mandatory active-session validation.",
    }


def _value(value: Any, *path: str, default: Any = None) -> Any:
    current = value
    for key in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            current = getattr(current, key, default)
    return current


def _result_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        result = result.to_dict()
    if hasattr(result, "__dict__") and not isinstance(result, dict):
        result = vars(result)
    assert isinstance(result, dict), "RealignResult must be dict-like or dataclass-like"
    return dict(result)


def _constraints(result: Any) -> list[dict[str, Any]]:
    data = _result_dict(result)
    raw = (
        data.get("constraints")
        or data.get("constraint_set")
        or data.get("agent_constraints")
        or data.get("injected_constraints")
        or []
    )
    assert isinstance(raw, list), "RealignResult constraints must be list-like"
    return [dict(item) for item in raw]


def _answer(result: Any) -> Any:
    data = _result_dict(result)
    return (
        data.get("answer")
        or data.get("agent_answer")
        or data.get("answer_candidate")
        or data.get("final_answer")
        or data.get("realign_answer")
        or {}
    )


def _answer_section(result: Any, label: str) -> Any:
    answer = _answer(result)
    if isinstance(answer, dict):
        return answer.get(label, "")
    return getattr(answer, label, "")


def _text_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {_text_blob(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text_blob(item) for item in value)
    return "" if value is None else str(value)


def _stopped(result: Any) -> bool:
    data = _result_dict(result)
    for key in ("should_stop", "stops", "blocked", "stop"):
        value = data.get(key)
        if isinstance(value, bool):
            return value
    can_continue = data.get("can_continue") or data.get("should_continue")
    if isinstance(can_continue, bool):
        return not can_continue
    status = str(data.get("status") or _value(data, "freshness_report", "status") or "")
    return status in {"blocked", "failed", "needs_clarification"}


def _assert_constraint_validation_rejected(value: Any, *expected_fragments: str) -> None:
    text = _text_blob(value)
    lowered = text.lower()
    assert "validation" in lowered or "invalid" in lowered or "reject" in lowered or _stopped(value)
    assert _constraints(value) == []
    for expected in expected_fragments:
        assert expected in text
    assert "課題プロンプトへの回答または修正案" not in text


def test_t_e04_realign_reuses_inject_constraints_before_returning_answer(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _result_dict(_run_spec_realign(project_root))
    constraints = _constraints(result)
    text = _text_blob(result)

    assert _stopped(result) is False
    assert [item["statement"] for item in constraints] == [
        item["statement"] for item in _valid_constraints()
    ]
    for expected in ANSWER_SECTION_LABELS:
        assert expected in text


@pytest.mark.parametrize("answer_key", ("agent_answer", "answer"))
def test_t_i08_realign_accepts_agent_supplied_answer_and_does_not_call_llm_provider(
    tmp_path: Path,
    answer_key: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    provider = ExplodingProvider()

    result = _run_spec_realign(
        project_root,
        provider=provider,
        llm_provider=provider,
        agent_answer=_valid_answer() if answer_key == "agent_answer" else None,
        answer=_valid_answer() if answer_key == "answer" else None,
    )

    assert provider.calls == 0
    assert _stopped(result) is False
    assert _constraints(result)
    for expected in ANSWER_SECTION_LABELS:
        assert expected in _text_blob(_answer(result))


def test_t_u18_blocked_freshness_stops_before_answer_provider_and_spec_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    provider = ExplodingProvider()
    import spec_grag.core as core_module

    calls: list[Any] = []

    def spy_run_spec_core(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append((args, kwargs))
        raise AssertionError("/spec-realign must not run /spec-core automatically")

    monkeypatch.setattr(core_module, "run_spec_core", spy_run_spec_core)
    realign_module = _realign_module()
    if hasattr(realign_module, "run_spec_core"):
        monkeypatch.setattr(realign_module, "run_spec_core", spy_run_spec_core)

    result = _result_dict(
        _run_spec_realign(
            project_root,
            provider=provider,
            llm_provider=provider,
            freshness_report={
                "status": "blocked",
                "blocking_reasons": ["dirty_or_stale_source"],
                "warnings": [],
            },
        )
    )
    text = _text_blob(result)

    assert calls == []
    assert provider.calls == 0
    assert _stopped(result) is True
    assert _constraints(result) == []
    assert "dirty_or_stale_source" in text
    assert "/spec-core" in text
    assert "課題プロンプトへの回答または修正案" not in text


def test_t_e05_no_task_prompt_with_clear_conversation_context_can_proceed(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _result_dict(
        _run_spec_realign(
            project_root,
            task_prompt=None,
            prompt=None,
            conversation_context=(
                "直近の会話では、認証チェックの修正案を作ることが中心課題として明確。"
            ),
        )
    )

    assert _stopped(result) is False
    assert "認証処理の先頭で active session を検証" in _text_blob(_answer(result))


@pytest.mark.parametrize("conversation_context", ("", "   "))
def test_t_e05_no_task_prompt_with_blank_context_asks_clarification(
    tmp_path: Path,
    conversation_context: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _result_dict(
        _run_spec_realign(
            project_root,
            task_prompt=None,
            prompt=None,
            conversation_context=conversation_context,
        )
    )
    text = _text_blob(result)

    assert _stopped(result) is True
    assert _constraints(result) == []
    assert (
        "clarification" in text.lower()
        or "確認" in text
        or "中心課題" in text
        or "曖昧" in text
    )
    assert "課題プロンプトへの回答または修正案" not in text


def test_t_e05_agent_supplied_clarification_flag_asks_clarification(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _result_dict(
        _run_spec_realign(
            project_root,
            task_prompt=None,
            prompt=None,
            conversation_context="それ、どうしますか。",
            clarification_required=True,
        )
    )
    text = _text_blob(result)

    assert _stopped(result) is True
    assert _constraints(result) == []
    assert "clarification" in text.lower() or "確認" in text
    assert "課題プロンプトへの回答または修正案" not in text


def test_t_e05_non_empty_ambiguous_words_do_not_trigger_cli_heuristic(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _result_dict(
        _run_spec_realign(
            project_root,
            task_prompt="これを直す",
            prompt="これを直す",
            conversation_context="Agent が会話区間を解釈し、認証仕様の修正対象を特定済み。",
        )
    )

    assert _stopped(result) is False
    assert "課題プロンプトへの回答または修正案" in _text_blob(result)


def test_t_e04_answer_conflict_with_constraints_is_surfaced_for_human_review(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _result_dict(
        _run_spec_realign(project_root, agent_answer=_conflicting_answer())
    )
    text = _text_blob(result)

    assert _stopped(result) is False
    assert "conflict" in text.lower() or "矛盾" in text or "競合" in text
    assert "human" in text.lower() or "人間レビュー" in text
    assert "active-session" in text or "session-validation" in text or "session" in text


def test_review_constraint_uncertainty_is_surfaced_in_realign_human_review_section(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    constraints = _valid_constraints()
    constraints[0]["uncertainty"] = [
        "Migration exception for service-to-service calls is unresolved."
    ]

    result = _result_dict(_run_spec_realign(project_root, agent_constraints=constraints))
    review_section = _text_blob(
        _answer_section(result, "競合 / 不確実性 / 人間レビューが必要な点")
    )

    assert _stopped(result) is False
    assert "Migration exception for service-to-service calls is unresolved." in review_section


@pytest.mark.parametrize(
    ("constraint_patch", "expected_fragment"),
    (
        ({"status": "pending"}, "pending"),
        ({"status": "resolved", "stale_resolution": True}, "stale_resolution"),
    ),
)
def test_review_realign_rejects_unusable_conflict_review_item_evidence(
    tmp_path: Path,
    constraint_patch: dict[str, Any],
    expected_fragment: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    constraint = _conflict_review_constraint()
    constraint.update(constraint_patch)

    try:
        result = _result_dict(_run_spec_realign(project_root, agent_constraints=[constraint]))
    except Exception as exc:
        message = str(exc)
        assert "Conflict Review Item" in message
        assert expected_fragment in message
        return

    _assert_constraint_validation_rejected(result, "Conflict Review Item", expected_fragment)


def test_review_realign_rejects_resolved_conflict_review_item_without_valid_scope(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    constraint = _conflict_review_constraint(
        status="resolved",
        stale_resolution=False,
    )
    constraint.pop("valid_scope")

    try:
        result = _result_dict(_run_spec_realign(project_root, agent_constraints=[constraint]))
    except Exception as exc:
        message = str(exc)
        assert "Conflict Review Item" in message
        assert "valid_scope" in message
        return

    _assert_constraint_validation_rejected(result, "Conflict Review Item", "valid_scope")


def test_review_realign_marks_unreflected_human_conflict_decision(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    constraint = _conflict_review_constraint(
        status="resolved",
        stale_resolution=False,
        reflection_status="unreflected",
    )

    result = _result_dict(_run_spec_realign(project_root, agent_constraints=[constraint]))
    text = _text_blob(result)

    assert _stopped(result) is False
    assert _constraints(result)
    assert "Conflict Review Item" in text
    assert "unreflected" in text or "未反映" in text
    assert "human" in text.lower() or "人間" in text
