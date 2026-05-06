"""`/spec-inject` public API contract tests for G-12.

These tests pin the Agent/CLI responsibility boundary from the external
contract.  The Agent supplies the task interpretation, Agentic Search, and
candidate constraints; the public API validates freshness and evidence shape,
then returns an injectable constraint summary without producing an answer.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from dataclasses import dataclass
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


FINAL_EVIDENCE_ORIGINS = {
    "Purpose",
    "Core Concept",
    "Source Specs",
    "Conflict Review Item",
}
SUPPORT_ONLY_ORIGINS = {
    "Section Summary",
    "Search Keys",
    "Related Sections",
    "Chapter Key Anchor",
}


@dataclass
class FakeSpecCoreProvider:
    def __post_init__(self) -> None:
        self.calls: list[Any] = []

    @property
    def provider_id(self) -> str:
        return "fake-spec-inject-core"

    def generate(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
        self.calls.append(request)
        section_hashes = getattr(request, "section_hashes", None)
        if (
            str(getattr(request, "stage", "")) == "section_metadata"
            and isinstance(section_hashes, dict)
            and section_hashes
        ):
            return {
                "sections": [
                    {
                        "section_id": str(section_id),
                        "summary": f"summary for {section_id}",
                        "search_keys": ["authentication", "session", "policy"],
                        "related_sections": [],
                    }
                    for section_id in section_hashes
                ]
            }
        section_id = _request_section_id(request)
        return {
            "summary": f"summary for {section_id}",
            "search_keys": ["authentication", "session", "policy"],
            "related_sections": [
                {
                    "target_section_id": "docs/spec/security.md#session",
                    "relation_hint": "depends_on",
                    "reason": "Authentication depends on session expiry rules.",
                    "evidence_terms": ["session"],
                }
            ],
            "chapter_summary": "security chapter anchor",
            "key_topics": ["authentication"],
            "important_sections": [section_id] if section_id else [],
        }

    def judge_conflict(self, request: Any, **_: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "outcome": "resolved_by_existing_evidence",
            "severity": "low",
            "warning": "No pending conflict in the fixture.",
        }


class ExplodingAgentProvider:
    provider_id = "must-not-be-used-by-spec-inject"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.calls += 1
        raise AssertionError("/spec-inject must not call an autonomous LLM provider")

    def judge_conflict(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.calls += 1
        raise AssertionError("/spec-inject must not run /spec-core conflict judging")


class PendingConflictSpecCoreProvider(FakeSpecCoreProvider):
    @property
    def provider_id(self) -> str:
        return "fake-spec-core-pending-conflict"

    def generate(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
        self.calls.append(request)
        if (
            not isinstance(request, dict)
            and getattr(request, "stage", "") == "related_section_selection"
        ):
            target = (
                "docs/spec/security.md#session"
                if getattr(request, "section_id", "") == "docs/spec/security.md#authentication"
                else "docs/spec/security.md#authentication"
            )
            return {
                "related_sections": [
                    {
                        "target_section_id": target,
                        "relation_hint": "conflicts_with",
                        "confidence": "high",
                        "reason": "The sections disagree on whether session validation is mandatory.",
                        "evidence_terms": ["session", "must", "optional"],
                    }
                ],
                "sections": [],
            }
        return super().generate(request, timeout_sec=timeout_sec)

    def judge_conflict(self, request: Any, **_: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "outcome": "needs_human_review",
            "conflict_id": "conflict-from-spec-core-artifact",
            "severity": "high",
            "claims": [
                {"side": "a", "summary": "Authentication must validate active sessions."},
                {"side": "b", "summary": "Session validation is optional in this flow."},
            ],
            "why_conflicting": "One source requires session validation while the other makes it optional.",
            "why_llm_cannot_decide": "No higher-priority source resolves the priority.",
            "recommended_next_action": "Ask a human to choose the session validation rule.",
        }


def _inject_module() -> Any:
    try:
        return importlib.import_module("spec_grag.inject")
    except ModuleNotFoundError as exc:
        if exc.name == "spec_grag.inject":
            pytest.fail("spec_grag.inject module is required for G-12 `/spec-inject`")
        raise


def _required_function(module: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail("`/spec-inject` public API is required; expected one of: " + ", ".join(names))


def _run_function() -> Any:
    return _required_function(
        _inject_module(),
        (
            "run_spec_inject",
            "spec_inject",
            "run_inject",
            "inject",
            "execute_spec_inject",
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


def _run_spec_core(project_root: Path) -> dict[str, Any]:
    from spec_grag.core import run_spec_core

    result = run_spec_core(
        project_root=project_root,
        all=True,
        all_mode=True,
        force=True,
        mode="full",
        provider=FakeSpecCoreProvider(),
        generated_at="2026-05-06T00:00:00Z",
    )
    assert _value(result, "freshness_report", "status") == "fresh"
    return result


def _run_spec_inject(project_root: Path, **kwargs: Any) -> Any:
    return _call(
        _run_function(),
        _positional=(project_root,),
        project_root=project_root,
        root=project_root,
        cwd=project_root,
        task_prompt=kwargs.pop("task_prompt", "認証の設計方針を確認したい"),
        prompt=kwargs.pop("prompt", None),
        conversation_context=kwargs.pop("conversation_context", "Review auth behavior."),
        agent_constraints=kwargs.pop("agent_constraints", _valid_constraints()),
        constraints=kwargs.pop("constraints", None),
        generated_constraints=kwargs.pop("generated_constraints", None),
        freshness_report=kwargs.pop("freshness_report", None),
        freshness=kwargs.pop("freshness", None),
        provider=kwargs.pop("provider", None),
        llm_provider=kwargs.pop("llm_provider", None),
        generated_at="2026-05-06T00:00:00Z",
        **kwargs,
    )


def _write_project(project_root: Path) -> dict[str, Path]:
    (project_root / ".spec-grag").mkdir(parents=True)
    (project_root / ".spec-grag" / "config.toml").write_text(CONFIG)
    (project_root / "docs/core").mkdir(parents=True)
    (project_root / "docs/spec").mkdir(parents=True)
    purpose = project_root / "docs/core/purpose.md"
    concept = project_root / "docs/core/concept.md"
    spec = project_root / "docs/spec/security.md"
    purpose.write_text("# Purpose\nShip reliable authentication behavior.\n")
    concept.write_text("# Core Concept\nSource Specs are the final authority.\n")
    spec.write_text(
        "# Security\n"
        "Intro.\n\n"
        "## Authentication\n"
        "Authentication must validate sessions before privileged actions.\n\n"
        "## Session\n"
        "Sessions expire after inactivity and must be refreshed explicitly.\n"
    )
    return {"purpose": purpose, "concept": concept, "spec": spec}


def _write_conflicting_project(project_root: Path) -> dict[str, Path]:
    paths = _write_project(project_root)
    paths["spec"].write_text(
        "# Security\n"
        "Intro.\n\n"
        "## Authentication\n"
        "Authentication must validate active sessions before privileged actions.\n\n"
        "## Session\n"
        "For the same privileged actions, session validation is optional during migration.\n"
    )
    return paths


def _valid_constraints() -> list[dict[str, Any]]:
    return [
        {
            "statement": "Privileged actions must validate an active session first.",
            "evidence_origin": "Source Specs",
            "evidence_ref": "docs/spec/security.md#authentication",
            "support_refs": [
                {
                    "origin": "Section Summary",
                    "ref": "docs/spec/security.md#authentication",
                },
                {
                    "origin": "Related Sections",
                    "ref": "docs/spec/security.md#session",
                },
                {
                    "origin": "Chapter Key Anchor",
                    "ref": "Security",
                },
            ],
            "applicability": "Authentication design and authorization checks.",
            "uncertainty": [],
        }
    ]


def _pending_conflict(conflict_id: str = "conflict-auth-session") -> dict[str, Any]:
    return {
        "conflict_id": conflict_id,
        "status": "pending",
        "severity": "high",
        "source_refs": [
            {"source_section_id": "docs/spec/security.md#authentication"},
            {"source_section_id": "docs/spec/security.md#session"},
        ],
        "claims": [
            {"side": "a", "summary": "Authentication requires active sessions."},
            {"side": "b", "summary": "Session validity is undecided."},
        ],
        "why_conflicting": "The active-session requirement cannot be applied safely.",
        "why_llm_cannot_decide": "No higher-priority source defines the exception.",
        "decision_options": [{"id": "prefer_a"}, {"id": "prefer_b"}, {"id": "defer"}],
        "recommended_next_action": "Ask a human to resolve the session rule.",
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
    assert isinstance(result, dict), "InjectResult must be dict-like or dataclass-like"
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
    assert isinstance(raw, list), "InjectResult constraints must be list-like"
    return [dict(item) for item in raw]


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


def _assert_needs_agent_constraints_failure(value: Any) -> None:
    text = _text_blob(value)
    lowered = text.lower()
    assert (
        "needs_agent_constraints" in lowered
        or "agent_constraints" in lowered
        or "no constraints" in lowered
        or "constraints" in lowered
    )
    assert "今回守る制約" not in text


def _assert_constraint_validation_rejected(value: Any, *expected_fragments: str) -> None:
    text = _text_blob(value)
    lowered = text.lower()
    assert "validation" in lowered or "invalid" in lowered or "reject" in lowered or _stopped(value)
    assert _constraints(value) == []
    for expected in expected_fragments:
        assert expected in text
    assert "今回守る制約" not in text


def _request_section_id(request: Any) -> str:
    if isinstance(request, dict):
        return str(request.get("section_id") or request.get("source_section_id") or "unknown")
    return str(getattr(request, "section_id", None) or getattr(request, "source_section_id", None) or "unknown")


def test_t_e01_fresh_core_then_inject_returns_minimal_constraint_shape(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)

    result = _result_dict(_run_spec_inject(project_root))
    constraints = _constraints(result)

    assert constraints, "`/spec-inject` must return the Agent-generated constraint set"
    for constraint in constraints:
        assert {"statement", "evidence_origin", "evidence_ref", "support_refs", "applicability"}.issubset(constraint)
        assert constraint["evidence_origin"] in FINAL_EVIDENCE_ORIGINS
        assert constraint["evidence_ref"]
        assert isinstance(constraint["support_refs"], list)
        assert constraint["applicability"]

    text = _text_blob(result)
    for expected in ("今回守る制約", "今回見るべき対象", "関連先として確認したもの"):
        assert expected in text


def test_review_no_agent_constraints_does_not_synthesize_fallback_constraints(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)

    try:
        result = _result_dict(
            _run_spec_inject(
                project_root,
                agent_constraints=None,
                constraints=None,
                generated_constraints=None,
            )
        )
    except Exception as exc:
        _assert_needs_agent_constraints_failure(exc)
        return

    assert _stopped(result) is True
    assert _constraints(result) == []
    _assert_needs_agent_constraints_failure(result)


def test_t_u17_inject_output_has_no_answer_section_or_answer_field(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)

    result = _result_dict(_run_spec_inject(project_root))
    text = _text_blob(result).lower()

    assert "answer" not in result
    assert "final_answer" not in result
    assert "課題プロンプトへの回答" not in text
    assert "answer section" not in text
    assert "今回守る制約" in _text_blob(result)


@pytest.mark.parametrize("origin", sorted(SUPPORT_ONLY_ORIGINS))
def test_t_e06_support_only_origins_are_rejected_as_final_evidence(
    tmp_path: Path,
    origin: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)
    invalid = _valid_constraints()
    invalid[0]["evidence_origin"] = origin
    invalid[0]["evidence_ref"] = "docs/spec/security.md#authentication"

    with pytest.raises(Exception) as exc_info:
        _run_spec_inject(project_root, agent_constraints=invalid)

    message = str(exc_info.value)
    assert origin in message
    assert "evidence_origin" in message


def test_t_e06_support_refs_may_include_search_helper_artifacts(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)
    constraints = _valid_constraints()
    constraints[0]["support_refs"].append({"origin": "Search Keys", "ref": "authentication"})

    result = _run_spec_inject(project_root, agent_constraints=constraints)
    support_origins = {
        str(ref.get("origin"))
        for constraint in _constraints(result)
        for ref in constraint.get("support_refs", [])
        if isinstance(ref, dict)
    }

    assert SUPPORT_ONLY_ORIGINS.issubset(support_origins)


def test_t_i09_pending_conflict_stop_output_has_items_and_no_constraints(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    pending = _pending_conflict()

    result = _result_dict(
        _run_spec_inject(
            project_root,
            freshness_report={
                "status": "blocked",
                "blocking_reasons": ["pending_conflict"],
                "warnings": [],
                "pending_conflict_items": [pending],
            },
        )
    )
    text = _text_blob(result)

    assert _stopped(result) is True
    assert _constraints(result) == []
    for expected in (
        "pending_conflict",
        "conflict-auth-session",
        "severity",
        "source_refs",
        "claims",
        "why_conflicting",
        "why_llm_cannot_decide",
        "decision_options",
        "recommended_next_action",
    ):
        assert expected in text


def test_review_dirty_plus_pending_conflict_does_not_surface_stale_conflict_targets(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    stale_pending = _pending_conflict("stale-conflict-auth-session")

    result = _result_dict(
        _run_spec_inject(
            project_root,
            freshness_report={
                "status": "blocked",
                "blocking_reasons": ["dirty_or_stale_source", "pending_conflict"],
                "warnings": [],
                "pending_conflict_items": [stale_pending],
                "pending_conflict_count": 1,
            },
        )
    )
    text = _text_blob(result)

    assert _stopped(result) is True
    assert _constraints(result) == []
    assert "dirty_or_stale_source" in text
    assert "pending_conflict" in text
    assert "/spec-core" in text
    assert _value(result, "pending_conflict_items", default=[]) == []
    assert _value(result, "pending_conflict_count", default=0) == 0
    assert "stale-conflict-auth-session" not in text
    assert "decision_options" not in text
    assert "why_llm_cannot_decide" not in text


def test_review_pending_conflict_items_are_loaded_from_real_context_artifact(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_conflicting_project(project_root)

    from spec_grag.core import run_spec_core

    core_result = run_spec_core(
        project_root=project_root,
        all=True,
        all_mode=True,
        force=True,
        mode="full",
        provider=PendingConflictSpecCoreProvider(),
        generated_at="2026-05-06T00:00:00Z",
    )
    assert _value(core_result, "failed_sections", default=[]) == []
    assert _value(core_result, "failed_sources", default=[]) == []
    assert _value(core_result, "pending_conflict_count") >= 1
    freshness = _value(core_result, "freshness_report")
    assert _value(freshness, "status") == "blocked"
    assert _value(freshness, "blocking_reasons") == ["pending_conflict"]

    artifact_path = project_root / ".spec-grag/context/conflict_review_items.json"
    artifact = json.loads(artifact_path.read_text())
    pending_items = [
        item
        for item in artifact.get("conflict_review_items", [])
        if item.get("status") == "pending"
    ]
    assert pending_items

    result = _result_dict(
        _run_spec_inject(
            project_root,
            freshness_report={
                "status": "blocked",
                "blocking_reasons": ["pending_conflict"],
                "pending_conflict_count": len(pending_items),
                "warnings": [],
            },
        )
    )

    assert _stopped(result) is True
    assert _constraints(result) == []
    assert _value(result, "pending_conflict_items") == pending_items
    text = _text_blob(result)
    assert "conflict-from-spec-core-artifact" in text
    assert "why_llm_cannot_decide" in text


@pytest.mark.parametrize(
    ("status", "reasons", "recommended"),
    (
        ("blocked", ["dirty_or_stale_source"], "/spec-core"),
        ("blocked", ["stale_config_or_schema"], "/spec-core --all"),
        ("blocked", ["watcher_running"], "watcher"),
        ("blocked", ["watcher_queue_pending"], "watcher"),
        ("failed", ["failed_required_artifact"], "/spec-core"),
    ),
)
def test_t_u18_blocked_or_failed_inject_stops_without_running_spec_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    reasons: list[str],
    recommended: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    import spec_grag.core as core_module

    calls: list[Any] = []

    def spy_run_spec_core(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append((args, kwargs))
        raise AssertionError("/spec-inject must not run /spec-core automatically")

    monkeypatch.setattr(core_module, "run_spec_core", spy_run_spec_core)
    inject_module = _inject_module()
    if hasattr(inject_module, "run_spec_core"):
        monkeypatch.setattr(inject_module, "run_spec_core", spy_run_spec_core)

    result = _result_dict(
        _run_spec_inject(
            project_root,
            freshness_report={"status": status, "blocking_reasons": reasons, "warnings": []},
        )
    )
    text = _text_blob(result)

    assert calls == []
    assert _stopped(result) is True
    assert _constraints(result) == []
    for reason in reasons:
        assert reason in text
    assert recommended in text
    assert "recommended_next_action" in text


def test_t_u03_degraded_optional_artifact_continues_with_warnings(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _result_dict(
        _run_spec_inject(
            project_root,
            freshness_report={
                "status": "degraded",
                "blocking_reasons": ["degraded_optional_artifact"],
                "warnings": [{"reason_code": "degraded_optional_artifact", "artifact": "section_metadata"}],
            },
        )
    )
    text = _text_blob(result)

    assert _stopped(result) is False
    assert _constraints(result)
    assert "degraded_optional_artifact" in text
    assert "warnings" in text


def test_t_i08_inject_does_not_call_agentic_llm_provider_and_validates_constraints(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)
    provider = ExplodingAgentProvider()

    result = _run_spec_inject(project_root, provider=provider, llm_provider=provider)

    assert provider.calls == 0
    assert _constraints(result)

    invalid = _valid_constraints()
    invalid[0].pop("applicability")
    with pytest.raises(Exception) as exc_info:
        _run_spec_inject(project_root, agent_constraints=invalid, provider=provider)
    assert "applicability" in str(exc_info.value)
    assert provider.calls == 0


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("statement", []),
        ("statement", ""),
        ("statement", "   "),
        ("evidence_ref", {}),
        ("evidence_ref", ""),
        ("evidence_ref", "   "),
        ("evidence_origin", []),
        ("evidence_origin", ""),
        ("evidence_origin", "   "),
        ("applicability", []),
        ("applicability", ""),
        ("applicability", "   "),
    ),
)
def test_review_required_constraint_fields_reject_non_scalar_or_empty_values(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)
    invalid = _valid_constraints()
    invalid[0][field] = value

    with pytest.raises(Exception) as exc_info:
        _run_spec_inject(project_root, agent_constraints=invalid)

    assert field in str(exc_info.value)


def test_spec_inject_reads_freshness_artifact_without_recomputing_core(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)
    freshness_path = project_root / ".spec-grag/context/freshness.json"
    freshness = json.loads(freshness_path.read_text())
    assert freshness["status"] == "fresh"

    result = _run_spec_inject(project_root)

    assert _stopped(result) is False
    assert _constraints(result)


@pytest.mark.parametrize(
    ("constraint_patch", "expected_fragment"),
    (
        ({"status": "pending"}, "pending"),
        ({"status": "resolved", "stale_resolution": True}, "stale_resolution"),
    ),
)
def test_review_inject_rejects_unusable_conflict_review_item_evidence(
    tmp_path: Path,
    constraint_patch: dict[str, Any],
    expected_fragment: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)
    constraint = _conflict_review_constraint()
    constraint.update(constraint_patch)

    try:
        result = _result_dict(_run_spec_inject(project_root, agent_constraints=[constraint]))
    except Exception as exc:
        message = str(exc)
        assert "Conflict Review Item" in message
        assert expected_fragment in message
        return

    _assert_constraint_validation_rejected(result, "Conflict Review Item", expected_fragment)


def test_review_inject_rejects_resolved_conflict_review_item_without_valid_scope(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)
    constraint = _conflict_review_constraint(
        status="resolved",
        stale_resolution=False,
    )
    constraint.pop("valid_scope")

    try:
        result = _result_dict(_run_spec_inject(project_root, agent_constraints=[constraint]))
    except Exception as exc:
        message = str(exc)
        assert "Conflict Review Item" in message
        assert "valid_scope" in message
        return

    _assert_constraint_validation_rejected(result, "Conflict Review Item", "valid_scope")


def test_review_inject_marks_unreflected_human_conflict_decision(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)
    constraint = _conflict_review_constraint(
        status="resolved",
        stale_resolution=False,
        reflection_status="unreflected",
    )

    result = _result_dict(_run_spec_inject(project_root, agent_constraints=[constraint]))
    text = _text_blob(result)

    assert _stopped(result) is False
    assert _constraints(result)
    assert "Conflict Review Item" in text
    assert "unreflected" in text or "未反映" in text
    assert "human" in text.lower() or "人間" in text
