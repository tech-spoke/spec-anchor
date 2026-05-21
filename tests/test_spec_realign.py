"""`/spec-realign` public API contract tests (post F-9 / F-2).

Post-2026-05-19 contract: `/spec-realign` applies the same freshness gate
as `/spec-inject` and structures the Agent-supplied answer into four
labeled sections. Constraint generation / validation, task prompt and
conversation context interpretation, clarification judgement, and
Conflict Review Item eligibility checks are all Agent / LLM
responsibilities (see EXTERNAL_DESIGN.ja.md §5.3 / §8.5 / §9). The CLI
must not call an autonomous LLM provider or rerun `/spec-core`.
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
storage = ".spec-anchor/context"

[section]
max_heading_level = 4

[llm.providers.fake]
command = "fake-noop"
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
    return importlib.import_module("spec_anchor.realign")


def _run_spec_realign(project_root: Path, **kwargs: Any) -> Any:
    func = _realign_module().run_spec_realign
    signature = inspect.signature(func)
    base: dict[str, Any] = {
        "project_root": project_root,
        "root": project_root,
        "cwd": project_root,
        "agent_answer": kwargs.pop("agent_answer", _valid_answer()),
        "answer": kwargs.pop("answer", None),
        "answer_candidate": kwargs.pop("answer_candidate", None),
        "freshness_report": kwargs.pop("freshness_report", _fresh_report()),
        "freshness": kwargs.pop("freshness", None),
        "provider": kwargs.pop("provider", None),
        "llm_provider": kwargs.pop("llm_provider", None),
        "generated_at": "2026-05-06T00:00:00Z",
    }
    base.update(kwargs)
    supported = {
        name: value
        for name, value in base.items()
        if name in signature.parameters and value is not None
    }
    return func(**supported)


def _write_project(project_root: Path) -> None:
    (project_root / ".spec-anchor").mkdir(parents=True)
    (project_root / ".spec-anchor" / "config.toml").write_text(CONFIG)
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
    return status in {"blocked", "failed"}


# --- tests ---


def test_t_e04_realign_returns_agent_answer_in_four_section_layout(tmp_path: Path) -> None:
    """Happy path: fresh gate + valid agent_answer -> structured 4-section answer."""

    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _result_dict(_run_spec_realign(project_root))
    text = _text_blob(result)

    assert _stopped(result) is False
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
    for expected in ANSWER_SECTION_LABELS:
        assert expected in _text_blob(_answer(result))


def test_t_u18_blocked_freshness_stops_before_answer_provider_and_spec_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    provider = ExplodingProvider()
    import spec_anchor.core as core_module

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
    assert "dirty_or_stale_source" in text
    assert "/spec-core" in text
    assert "課題プロンプトへの回答または修正案" not in text


def test_t_e04_answer_conflict_is_surfaced_for_human_review(tmp_path: Path) -> None:
    """Agent supplies an answer flagging its own conflict; the conflict is surfaced
    in the human-review section unchanged. The CLI does not validate constraints."""

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
