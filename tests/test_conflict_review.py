"""Conflict Review Item contract tests for G-09.

Conflict Review Items are the only standard path where unresolved Source Spec
conflicts become human-blocking state. Resolvable conflicts stay diagnostics /
warnings, and resolved human decisions are usable evidence only while their
source hashes and valid scope allow it.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DECISION_ENUM = {
    "prefer_a",
    "prefer_b",
    "conditional",
    "dismiss",
    "needs_source_update",
    "defer",
    "task_scope_resolution",
}
RESOLVED_DECISIONS = {
    "prefer_a",
    "prefer_b",
    "conditional",
    "task_scope_resolution",
}
PENDING_DECISIONS = {"needs_source_update", "defer"}


@dataclass
class FakeConflictJudge:
    outcome: str

    def __post_init__(self) -> None:
        self.calls: list[Any] = []

    @property
    def provider_id(self) -> str:
        return f"fake-conflict-judge-{self.outcome}"

    def generate(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
        self.calls.append(request)
        return self._payload()

    def judge(self, pair: Any, **_: Any) -> dict[str, Any]:
        self.calls.append(pair)
        return self._payload()

    def judge_conflict(self, pair: Any, **_: Any) -> dict[str, Any]:
        self.calls.append(pair)
        return self._payload()

    def _payload(self) -> dict[str, Any]:
        if self.outcome == "unresolved":
            return {
                "outcome": "needs_human_review",
                "severity": "high",
                "claims": [
                    {"side": "a", "summary": "Alpha says FEATURE_X is required."},
                    {"side": "b", "summary": "Beta says FEATURE_X is forbidden."},
                ],
                "why_conflicting": "FEATURE_X is simultaneously required and forbidden.",
                "why_llm_cannot_decide": "No Purpose or Core Concept priority exists.",
                "decision_options": [
                    {"id": "prefer_a", "label": "Prefer Alpha"},
                    {"id": "prefer_b", "label": "Prefer Beta"},
                    {"id": "conditional", "label": "Use a conditional rule"},
                    {"id": "dismiss", "label": "Not a conflict"},
                    {"id": "needs_source_update", "label": "Update Source Specs"},
                    {"id": "defer", "label": "Defer"},
                    {"id": "task_scope_resolution", "label": "Resolve for this task only"},
                ],
                "recommended_next_action": "Ask a human to choose the applicable rule.",
            }
        return {
            "outcome": "resolved_by_existing_evidence",
            "severity": "medium",
            "warning": "Potential conflict is resolved by explicit Core Concept priority.",
            "why_not_pending": "Core Concept says Beta overrides Alpha.",
        }


def _module() -> Any:
    try:
        return importlib.import_module("spec_anchor.conflict_review")
    except ModuleNotFoundError as exc:
        if exc.name == "spec_anchor.conflict_review":
            pytest.fail("spec_anchor.conflict_review module is required for G-09")
        raise


def _required_function(module: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail("Conflict Review API is required; expected one of: " + ", ".join(names))


def _call(func: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    supported = {
        name: value for name, value in kwargs.items() if name in signature.parameters
    }
    try:
        return func(**supported)
    except TypeError:
        return func(*kwargs.get("_positional", ()), **supported)


def _config(*, conflict_pair_max_per_section: int = 8) -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(model="fake-model", effort="low", timeout_sec=5, max_retries=0),
        limits=SimpleNamespace(
            section_summary_max_chars=480,
            search_keys_max=32,
            related_candidate_max_per_section=32,
            related_selected_max_per_section=8,
            conflict_pair_max_per_section=conflict_pair_max_per_section,
            llm_batch_max_sections=8,
            llm_batch_max_chars=12000,
        ),
    )


def _section(
    section_id: str,
    *,
    text: str,
    identifiers: list[str] | None = None,
    ordinal: int = 1,
) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "source_section_id": section_id,
        "stable_section_uid": f"uid-{section_id}",
        "source_document_id": "docs/spec/conflict.md",
        "heading_path": ["Conflict", section_id.rsplit("#", 1)[-1]],
        "chapter_id": "docs/spec/conflict.md#chapter",
        "source_hash": f"hash-{section_id}",
        "semantic_hash": f"semantic-{section_id}",
        "source_span": {"start_line": ordinal * 10, "end_line": ordinal * 10 + 4},
        "identifiers": identifiers or [],
        "text": text,
        "summary": text,
        "search_keys": identifiers or [],
    }


def _sections() -> list[dict[str, Any]]:
    return [
        _section(
            "docs/spec/conflict.md#alpha",
            text="Alpha: FEATURE_X is required for all requests.",
            identifiers=["FEATURE_X"],
            ordinal=1,
        ),
        _section(
            "docs/spec/conflict.md#beta",
            text="Beta: FEATURE_X is forbidden for guest requests.",
            identifiers=["FEATURE_X"],
            ordinal=2,
        ),
        _section(
            "docs/spec/conflict.md#gamma",
            text="Gamma: CACHE_MODE is optional.",
            identifiers=["CACHE_MODE"],
            ordinal=3,
        ),
    ]


def _conflicts_with_related() -> dict[str, list[dict[str, Any]]]:
    return {
        "docs/spec/conflict.md#alpha": [
            {
                "source_section_id": "docs/spec/conflict.md#alpha",
                "target_section_id": "docs/spec/conflict.md#beta",
                "relation_hint": "conflicts_with",
                "confidence": "high",
                "reason": "Both define FEATURE_X in incompatible language.",
                "evidence_terms": ["FEATURE_X", "required", "forbidden"],
                "channels": ["shared_identifier"],
            }
        ]
    }


def _high_risk_candidate(
    source_section_id: str = "docs/spec/conflict.md#gamma",
    target_section_id: str = "docs/spec/conflict.md#delta",
) -> dict[str, Any]:
    return {
        "source_section_id": source_section_id,
        "target_section_id": target_section_id,
        "channels": ["shared_identifier"],
        "evidence_terms": ["FEATURE_X", "required", "forbidden"],
        "candidate_score": 90,
        "reason": "Shared identifier uses required and forbidden language.",
    }


def _items(payload: Any) -> list[dict[str, Any]]:
    if hasattr(payload, "conflict_review_items"):
        payload = payload.conflict_review_items
    elif hasattr(payload, "items"):
        payload = payload.items
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    if isinstance(payload, dict):
        payload = payload.get("conflict_review_items", payload.get("items", []))
    assert isinstance(payload, list), "result must expose conflict_review_items/items list"
    return [dict(item) for item in payload]


def _diagnostics(payload: Any) -> list[dict[str, Any]]:
    if hasattr(payload, "diagnostics"):
        payload = payload.diagnostics
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    if isinstance(payload, dict):
        payload = payload.get("diagnostics", payload.get("potential_conflicts", []))
    if payload is None:
        return []
    assert isinstance(payload, list), "result diagnostics must be list-like"
    return [dict(item) for item in payload]


def _freshness(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "freshness_report"):
        payload = payload.freshness_report
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    if isinstance(payload, dict) and "freshness_report" in payload:
        payload = payload["freshness_report"]
    assert isinstance(payload, dict), "result must expose a freshness_report dict"
    return dict(payload)


def _option_ids(item: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for option in item.get("decision_options", []):
        if isinstance(option, str):
            ids.add(option)
        elif isinstance(option, dict):
            ids.add(str(option.get("id", option.get("decision", option.get("value", "")))))
    return {option_id for option_id in ids if option_id}


def _pending_item(conflict_id: str = "conflict-feature-x") -> dict[str, Any]:
    options = [
        {"id": decision, "label": decision.replace("_", " ")}
        for decision in sorted(DECISION_ENUM)
    ]
    return {
        "conflict_id": conflict_id,
        "status": "pending",
        "severity": "high",
        "source_refs": [
            {"source_section_id": "docs/spec/conflict.md#alpha", "source_hash": "hash-a"},
            {"source_section_id": "docs/spec/conflict.md#beta", "source_hash": "hash-b"},
        ],
        "claims": [
            {"side": "a", "summary": "FEATURE_X is required."},
            {"side": "b", "summary": "FEATURE_X is forbidden."},
        ],
        "why_conflicting": "Required and forbidden cannot both hold globally.",
        "why_llm_cannot_decide": "No priority source is present.",
        "related_sections": [
            {
                "source_section_id": "docs/spec/conflict.md#alpha",
                "target_section_id": "docs/spec/conflict.md#beta",
                "relation_hint": "conflicts_with",
            }
        ],
        "decision_options": options,
        "recommended_next_action": "Ask a human for a decision.",
        "base_source_hashes": [
            {"source_ref": "docs/spec/conflict.md#alpha", "hash": "hash-a"},
            {"source_ref": "docs/spec/conflict.md#beta", "hash": "hash-b"},
        ],
        "valid_scope": "global",
        "reflection_status": "unreflected",
        "reflected_refs": [],
        "stale_resolution": False,
        "created_at": "2026-05-06T00:00:00Z",
        "updated_at": "2026-05-06T00:00:00Z",
    }


def _item_by_id(payload: Any, conflict_id: str) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("conflict_id") == conflict_id:
        return dict(payload)
    for item in _items(payload):
        if item.get("conflict_id") == conflict_id:
            return item
    pytest.fail(f"conflict item {conflict_id!r} was not returned")


def _decision_payload(
    *,
    conflict_id: str,
    decision: str,
    selected_option: str | None = None,
    valid_scope: str = "global",
) -> dict[str, Any]:
    return {
        "conflict_id": conflict_id,
        "decision": decision,
        "reason": f"Human selected {decision}.",
        "selected_option": selected_option or decision,
        "valid_scope": valid_scope,
        "referenced_source_refs": ["docs/spec/conflict.md#alpha"],
        "human_acknowledgement": True,
    }


def _assert_rejected(func: Any, **kwargs: Any) -> None:
    try:
        result = _call(func, **kwargs)
    except Exception:
        return
    if isinstance(result, dict):
        assert result.get("status") == "error" or result.get("errors") or result.get("ok") is False
        return
    if hasattr(result, "errors") or hasattr(result, "ok"):
        assert getattr(result, "errors", None) or getattr(result, "ok", True) is False
        return
    pytest.fail("invalid conflict decision must be rejected")


def test_t_i04_unresolved_conflicts_with_creates_pending_item() -> None:
    """`/spec-core` generates Conflict Review Items as `conflict_review_items.json`.
    """

    module = _module()
    evaluate = _required_function(
        module,
        (
            "evaluate_conflicts",
            "evaluate_conflict_review_items",
            "run_conflict_review",
            "generate_conflict_review_items",
        ),
    )
    judge = FakeConflictJudge("unresolved")

    result = _call(
        evaluate,
        _positional=(_sections(), _conflicts_with_related(), judge),
        sections=_sections(),
        section_metadata={"related_sections": _conflicts_with_related()},
        related_sections=_conflicts_with_related(),
        provider=judge,
        judge=judge,
        conflict_judge=judge,
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
    )
    items = _items(result)

    assert judge.calls, "conflicts_with pair must be sent to the injected fake judge"
    assert len(items) == 1
    assert items[0]["status"] == "pending"
    assert items[0]["source_refs"]
    assert items[0]["why_llm_cannot_decide"]


def test_t_i04_resolvable_conflict_is_warning_not_pending() -> None:
    module = _module()
    evaluate = _required_function(
        module,
        (
            "evaluate_conflicts",
            "evaluate_conflict_review_items",
            "run_conflict_review",
            "generate_conflict_review_items",
        ),
    )
    judge = FakeConflictJudge("resolved")

    result = _call(
        evaluate,
        _positional=(_sections(), _conflicts_with_related(), judge),
        sections=_sections(),
        section_metadata={"related_sections": _conflicts_with_related()},
        related_sections=_conflicts_with_related(),
        provider=judge,
        judge=judge,
        conflict_judge=judge,
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
    )

    assert judge.calls, "conflicts_with pair must still be judged"
    assert _items(result) == []
    diagnostics = _diagnostics(result)
    assert diagnostics
    assert any(
        item.get("level") in {"warning", "info"} or item.get("kind") == "potential_conflict"
        for item in diagnostics
    )


def test_t_u14_pending_item_required_schema_fields() -> None:
    module = _module()
    validate = _required_function(
        module,
        (
            "validate_conflict_review_item",
            "normalize_conflict_review_item",
            "validate_conflict_review_items",
        ),
    )

    result = _call(
        validate,
        _positional=(_pending_item(),),
        item=_pending_item(),
        items=[_pending_item()],
        generated_at="2026-05-06T00:00:00Z",
    )
    item = _item_by_id(result, "conflict-feature-x") if not isinstance(result, dict) else result

    required_fields = {
        "conflict_id",
        "status",
        "severity",
        "source_refs",
        "claims",
        "why_conflicting",
        "why_llm_cannot_decide",
        "related_sections",
        "decision_options",
        "recommended_next_action",
        "base_source_hashes",
        "valid_scope",
        "reflection_status",
        "created_at",
        "updated_at",
    }
    assert required_fields.issubset(item)
    assert item["status"] == "pending"
    assert item["source_refs"]
    assert item["decision_options"]
    assert _option_ids(item) == DECISION_ENUM


@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_scope"),
    [
        ("prefer_a", "resolved", "global"),
        ("prefer_b", "resolved", "global"),
        ("conditional", "resolved", "global"),
        ("dismiss", "dismissed", "global"),
        ("needs_source_update", "pending", "global"),
        ("defer", "pending", "global"),
        ("task_scope_resolution", "resolved", "task_scope"),
    ],
)
def test_t_u15_decision_payload_transitions(
    decision: str,
    expected_status: str,
    expected_scope: str,
) -> None:
    module = _module()
    apply_decision = _required_function(
        module,
        (
            "apply_conflict_decision",
            "record_conflict_decision",
            "resolve_conflict_review_item",
        ),
    )
    item = _pending_item(f"conflict-{decision}")
    payload = _decision_payload(
        conflict_id=item["conflict_id"],
        decision=decision,
        valid_scope="task_scope" if decision == "task_scope_resolution" else "global",
    )

    result = _call(
        apply_decision,
        _positional=([item], payload),
        items=[item],
        conflict_review_items=[item],
        decision_payload=payload,
        payload=payload,
        decision=payload,
        generated_at="2026-05-06T01:00:00Z",
    )
    updated = _item_by_id(result, item["conflict_id"])

    assert updated["status"] == expected_status
    assert updated["valid_scope"] == expected_scope
    assert updated["reflection_status"] in {"unreflected", "not_required"}
    assert "reflected_refs" in updated
    if expected_status in {"resolved", "dismissed"}:
        assert updated["resolution"]["decision"] == decision
        assert updated["resolution"]["reason"]
        assert updated["resolution"]["referenced_source_refs"]
    else:
        assert updated["status"] == "pending"


def test_t_u15_invalid_decisions_and_overwrites_are_rejected() -> None:
    module = _module()
    apply_decision = _required_function(
        module,
        (
            "apply_conflict_decision",
            "record_conflict_decision",
            "resolve_conflict_review_item",
        ),
    )
    item = _pending_item()

    _assert_rejected(
        apply_decision,
        _positional=([item], _decision_payload(conflict_id=item["conflict_id"], decision="merge")),
        items=[item],
        conflict_review_items=[item],
        decision_payload=_decision_payload(conflict_id=item["conflict_id"], decision="merge"),
        payload=_decision_payload(conflict_id=item["conflict_id"], decision="merge"),
        decision=_decision_payload(conflict_id=item["conflict_id"], decision="merge"),
    )
    _assert_rejected(
        apply_decision,
        _positional=(
            [item],
            _decision_payload(
                conflict_id=item["conflict_id"],
                decision="prefer_a",
                selected_option="not-an-offered-option",
            ),
        ),
        items=[item],
        conflict_review_items=[item],
        decision_payload=_decision_payload(
            conflict_id=item["conflict_id"],
            decision="prefer_a",
            selected_option="not-an-offered-option",
        ),
        payload=_decision_payload(
            conflict_id=item["conflict_id"],
            decision="prefer_a",
            selected_option="not-an-offered-option",
        ),
        decision=_decision_payload(
            conflict_id=item["conflict_id"],
            decision="prefer_a",
            selected_option="not-an-offered-option",
        ),
    )

    resolved = dict(item, status="resolved", resolution={"decision": "prefer_a"})
    dismissed = dict(item, status="dismissed", resolution={"decision": "dismiss"})
    for closed_item in (resolved, dismissed):
        _assert_rejected(
            apply_decision,
            _positional=(
                [closed_item],
                _decision_payload(conflict_id=closed_item["conflict_id"], decision="prefer_b"),
            ),
            items=[closed_item],
            conflict_review_items=[closed_item],
            decision_payload=_decision_payload(
                conflict_id=closed_item["conflict_id"],
                decision="prefer_b",
            ),
            payload=_decision_payload(
                conflict_id=closed_item["conflict_id"],
                decision="prefer_b",
            ),
            decision=_decision_payload(
                conflict_id=closed_item["conflict_id"],
                decision="prefer_b",
            ),
        )


def test_t_u11_pending_count_is_only_pending_conflict_blocking_reason() -> None:
    module = _module()
    summarize = _required_function(
        module,
        (
            "summarize_conflict_review_state",
            "build_conflict_freshness_report",
            "conflict_review_freshness_report",
        ),
    )
    pending = _pending_item("pending-conflict")
    resolved = dict(
        _pending_item("resolved-conflict"),
        status="resolved",
        resolution={"decision": "prefer_a"},
    )
    dismissed = dict(
        _pending_item("dismissed-conflict"),
        status="dismissed",
        resolution={"decision": "dismiss"},
    )

    result = _call(
        summarize,
        _positional=([pending, resolved, dismissed],),
        items=[pending, resolved, dismissed],
        conflict_review_items=[pending, resolved, dismissed],
        existing_blocking_reasons=[],
    )
    freshness = _freshness(result)

    assert freshness["status"] == "blocked"
    assert freshness["blocking_reasons"] == ["pending_conflict"]
    assert result.get("pending_conflict_count", 1) == 1 if isinstance(result, dict) else True

    no_pending = _call(
        summarize,
        _positional=([resolved, dismissed],),
        items=[resolved, dismissed],
        conflict_review_items=[resolved, dismissed],
        existing_blocking_reasons=[],
    )
    no_pending_freshness = _freshness(no_pending)
    assert "pending_conflict" not in no_pending_freshness.get("blocking_reasons", [])


def test_t_u16_stale_resolution_and_scope_control_evidence_use() -> None:
    module = _module()
    mark_stale = _required_function(
        module,
        (
            "refresh_conflict_resolution_staleness",
            "mark_stale_conflict_resolutions",
            "validate_conflict_resolution_freshness",
        ),
    )
    usable_evidence = _required_function(
        module,
        (
            "usable_conflict_resolution_evidence",
            "filter_usable_conflict_evidence",
            "resolved_conflict_evidence",
        ),
    )
    resolved = dict(
        _pending_item("resolved-conflict"),
        status="resolved",
        resolution={"decision": "prefer_a", "reason": "A wins"},
    )
    task_scope = dict(
        _pending_item("task-scope-conflict"),
        status="resolved",
        valid_scope="task_scope",
        resolution={"decision": "task_scope_resolution", "reason": "This task only"},
    )

    refreshed = _call(
        mark_stale,
        _positional=([resolved, task_scope],),
        items=[resolved, task_scope],
        conflict_review_items=[resolved, task_scope],
        current_source_hashes={
            "docs/spec/conflict.md#alpha": "changed-hash-a",
            "docs/spec/conflict.md#beta": "hash-b",
        },
        source_hashes={
            "docs/spec/conflict.md#alpha": "changed-hash-a",
            "docs/spec/conflict.md#beta": "hash-b",
        },
    )
    stale_item = _item_by_id(refreshed, "resolved-conflict")
    assert stale_item["stale_resolution"] is True

    evidence = _call(
        usable_evidence,
        _positional=(_items(refreshed),),
        items=_items(refreshed),
        conflict_review_items=_items(refreshed),
        requested_scope="global",
        scope="global",
        include_task_scope=False,
    )
    evidence_items = _items(evidence) if not isinstance(evidence, list) else evidence
    evidence_ids = {item["conflict_id"] for item in evidence_items}

    assert "resolved-conflict" not in evidence_ids
    assert "task-scope-conflict" not in evidence_ids


def test_t_u20_conflict_pair_selection_uses_conflicts_with_and_bounded_high_risk_pairs() -> None:
    module = _module()
    select_pairs = _required_function(
        module,
        (
            "select_conflict_judging_pairs",
            "build_conflict_judging_pairs",
            "candidate_conflict_pairs",
        ),
    )
    sections = [
        _section("docs/spec/conflict.md#alpha", text="FEATURE_X must be enabled.", identifiers=["FEATURE_X"], ordinal=1),
        _section("docs/spec/conflict.md#beta", text="FEATURE_X must not be enabled.", identifiers=["FEATURE_X"], ordinal=2),
        _section("docs/spec/conflict.md#gamma", text="PAYMENT_STATUS is required.", identifiers=["PAYMENT_STATUS"], ordinal=3),
        _section("docs/spec/conflict.md#delta", text="PAYMENT_STATUS is optional.", identifiers=["PAYMENT_STATUS"], ordinal=4),
        _section("docs/spec/conflict.md#epsilon", text="Unrelated prose.", identifiers=["EPSILON"], ordinal=5),
    ]
    related_sections = {
        "docs/spec/conflict.md#alpha": [
            {
                "source_section_id": "docs/spec/conflict.md#alpha",
                "target_section_id": "docs/spec/conflict.md#beta",
                "relation_hint": "conflicts_with",
                "confidence": "high",
                "reason": "Explicit conflict hint.",
                "evidence_terms": ["FEATURE_X"],
                "channels": ["shared_identifier"],
            }
        ]
    }
    candidates = [
        {
            "source_section_id": "docs/spec/conflict.md#gamma",
            "target_section_id": "docs/spec/conflict.md#delta",
            "channels": ["shared_identifier"],
            "evidence_terms": ["PAYMENT_STATUS", "required", "optional"],
            "candidate_score": 90,
        },
        {
            "source_section_id": "docs/spec/conflict.md#alpha",
            "target_section_id": "docs/spec/conflict.md#epsilon",
            "channels": ["same_chapter"],
            "evidence_terms": ["unrelated"],
            "candidate_score": 1,
        },
    ]

    result = _call(
        select_pairs,
        _positional=(sections, related_sections, candidates),
        sections=sections,
        related_sections=related_sections,
        candidates=candidates,
        related_section_candidates=candidates,
        config=_config(conflict_pair_max_per_section=1),
        limits=_config(conflict_pair_max_per_section=1).limits,
    )
    pairs = result.get("pairs", result.get("conflict_pairs", result)) if isinstance(result, dict) else result
    assert isinstance(pairs, list), "conflict pair selection must return list-like pairs"

    pair_ids = {
        frozenset(
            (
                pair.get("source_section_id", pair.get("section_a_id", pair.get("a"))),
                pair.get("target_section_id", pair.get("section_b_id", pair.get("b"))),
            )
        )
        for pair in pairs
    }
    assert frozenset({"docs/spec/conflict.md#alpha", "docs/spec/conflict.md#beta"}) in pair_ids
    assert frozenset({"docs/spec/conflict.md#gamma", "docs/spec/conflict.md#delta"}) in pair_ids
    assert frozenset({"docs/spec/conflict.md#alpha", "docs/spec/conflict.md#epsilon"}) not in pair_ids
    assert len(pairs) < (len(sections) * (len(sections) - 1) // 2)


@pytest.mark.parametrize("candidate_kw", ("candidates", "related_section_candidates"))
def test_t_u20_evaluate_conflicts_accepts_high_risk_candidate_arguments(candidate_kw: str) -> None:
    module = _module()
    evaluate = _required_function(
        module,
        (
            "evaluate_conflicts",
            "evaluate_conflict_review_items",
            "run_conflict_review",
            "generate_conflict_review_items",
        ),
    )
    judge = FakeConflictJudge("unresolved")
    sections = _sections() + [
        _section(
            "docs/spec/conflict.md#delta",
            text="Delta: FEATURE_X is forbidden for background jobs.",
            identifiers=["FEATURE_X"],
            ordinal=4,
        )
    ]
    candidate = _high_risk_candidate()

    result = _call(
        evaluate,
        sections=sections,
        related_sections={},
        section_metadata={"related_sections": {}},
        conflict_judge=judge,
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
        **{candidate_kw: [candidate]},
    )
    items = _items(result)

    assert judge.calls, "high-risk candidates passed to evaluate_conflicts must be judged"
    assert len(items) == 1
    assert {
        ref["source_section_id"]
        for ref in items[0]["source_refs"]
    } == {"docs/spec/conflict.md#gamma", "docs/spec/conflict.md#delta"}


def test_t_u20_evaluate_conflicts_extracts_related_section_candidates_from_metadata() -> None:
    module = _module()
    evaluate = _required_function(
        module,
        (
            "evaluate_conflicts",
            "evaluate_conflict_review_items",
            "run_conflict_review",
            "generate_conflict_review_items",
        ),
    )
    judge = FakeConflictJudge("unresolved")
    sections = _sections() + [
        _section(
            "docs/spec/conflict.md#delta",
            text="Delta: FEATURE_X is forbidden for background jobs.",
            identifiers=["FEATURE_X"],
            ordinal=4,
        )
    ]

    result = _call(
        evaluate,
        sections=sections,
        section_metadata={
            "related_sections": {},
            "related_section_candidates": [_high_risk_candidate()],
        },
        conflict_judge=judge,
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
    )

    assert judge.calls, "section_metadata related_section_candidates must be judged"
    assert len(_items(result)) == 1


def test_t_u20_conflict_pair_zero_limit_keeps_explicit_and_skips_high_risk_candidates() -> None:
    module = _module()
    select_pairs = _required_function(
        module,
        (
            "select_conflict_judging_pairs",
            "build_conflict_judging_pairs",
            "candidate_conflict_pairs",
        ),
    )

    result = _call(
        select_pairs,
        sections=_sections(),
        related_sections=_conflicts_with_related(),
        candidates=[_high_risk_candidate()],
        config=_config(conflict_pair_max_per_section=0),
    )
    pairs = result.get("pairs", result.get("conflict_pairs", result)) if isinstance(result, dict) else result
    pair_ids = {
        frozenset((pair["source_section_id"], pair["target_section_id"]))
        for pair in pairs
    }

    assert pair_ids == {
        frozenset({"docs/spec/conflict.md#alpha", "docs/spec/conflict.md#beta"})
    }


def test_t_u20_conflict_pair_limit_counts_only_high_risk_candidate_additions() -> None:
    module = _module()
    select_pairs = _required_function(
        module,
        (
            "select_conflict_judging_pairs",
            "build_conflict_judging_pairs",
            "candidate_conflict_pairs",
        ),
    )
    candidates = [
        _high_risk_candidate("docs/spec/conflict.md#alpha", "docs/spec/conflict.md#gamma"),
        _high_risk_candidate("docs/spec/conflict.md#alpha", "docs/spec/conflict.md#delta"),
    ]

    result = _call(
        select_pairs,
        sections=_sections(),
        related_sections=_conflicts_with_related(),
        candidates=candidates,
        config=_config(conflict_pair_max_per_section=1),
    )
    pairs = result.get("pairs", result.get("conflict_pairs", result)) if isinstance(result, dict) else result
    pair_ids = {
        frozenset((pair["source_section_id"], pair["target_section_id"]))
        for pair in pairs
    }

    assert frozenset({"docs/spec/conflict.md#alpha", "docs/spec/conflict.md#beta"}) in pair_ids
    assert frozenset({"docs/spec/conflict.md#alpha", "docs/spec/conflict.md#gamma"}) in pair_ids
    assert frozenset({"docs/spec/conflict.md#alpha", "docs/spec/conflict.md#delta"}) not in pair_ids


def test_phase_e_possible_conflict_flag_routes_to_conflict_review() -> None:
    """Phase E: related_sections with possible_conflict=True must be picked up
    as an explicit pair by select_conflict_judging_pairs, even though
    relation_hint != "conflicts_with".
    """
    import importlib

    module = importlib.import_module("spec_anchor.conflict_review")
    select = module.select_conflict_judging_pairs
    related_sections = {
        "spec.md#alpha": [
            {
                "source_section_id": "spec.md#alpha",
                "target_section_id": "spec.md#beta",
                "relation_hint": "depends_on",
                "confidence": "high",
                "reason": "Alpha depends on beta auth policy.",
                "evidence_terms": ["AUTH_TOKEN"],
                "channels": ["shared_identifier"],
                "possible_conflict": True,
            }
        ]
    }

    pairs = select(related_sections=related_sections)
    assert len(pairs) == 1
    assert pairs[0]["source_section_id"] == "spec.md#alpha"
    assert pairs[0]["target_section_id"] == "spec.md#beta"
    # Either the original relation_hint preserved or normalized to conflicts_with
    # — the key thing is the pair routed to the judge.
    assert pairs[0].get("relation_hint") in {"depends_on", "conflicts_with"}
