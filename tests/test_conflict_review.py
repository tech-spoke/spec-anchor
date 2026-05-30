"""Conflict Review Item contract tests for G-09.

Conflict Review Items surface unresolved Source Spec conflicts to humans.
Resolvable conflicts stay diagnostics / warnings. The only persistent human
write path is dismissing an item as not a real conflict.
"""

from __future__ import annotations

import importlib
import inspect
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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


def _config(
    *,
    llm_batch_concurrency: int = 4,
) -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(model="fake-model", effort="low", timeout_sec=5, max_retries=0),
        limits=SimpleNamespace(
            section_summary_max_chars=480,
            search_keys_max=32,
            related_candidate_max_per_section=32,
            related_selected_max_per_section=8,
            llm_batch_max_sections=8,
            llm_batch_max_chars=12000,
            llm_batch_concurrency=llm_batch_concurrency,
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


def _claim(
    suffix: str,
    *,
    source_section_id: str,
    claim_text: str,
    target: str = "FEATURE_X",
) -> dict[str, Any]:
    return {
        "claim_uid": f"claim:sha256:{suffix}",
        "display_id": f"{source_section_id}:C{suffix}",
        "claim_hash": f"claim-hash-{suffix}",
        "retrieval_hash": f"retrieval-hash-{suffix}",
        "source_section_id": source_section_id,
        "source_document_id": "docs/spec/conflict.md",
        "source_hash": f"hash-{source_section_id}",
        "claim_text": claim_text,
        "target": target,
        "target_aliases": [target],
        "claim_kind": "requirement",
        "scope": "normal operation",
        "condition": "",
        "value": claim_text,
        "confidence": "high",
        "evidence_span": claim_text,
        "evidence_start": 0,
        "evidence_end": len(claim_text),
        "evidence_hash": f"evidence-hash-{suffix}",
    }


def _candidate_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    send_to_review: bool = True,
) -> dict[str, Any]:
    left_uid, right_uid = sorted([left["claim_uid"], right["claim_uid"]])
    claims = {left["claim_uid"]: left, right["claim_uid"]: right}
    left_claim = claims[left_uid]
    right_claim = claims[right_uid]
    return {
        "candidate_uid": f"candidate:sha256:{left_uid.rsplit(':', 1)[-1]}-{right_uid.rsplit(':', 1)[-1]}",
        "display_id": "CC-00001",
        "left_claim_uid": left_uid,
        "right_claim_uid": right_uid,
        "left_claim_hash": left_claim["claim_hash"],
        "right_claim_hash": right_claim["claim_hash"],
        "left_retrieval_hash": left_claim["retrieval_hash"],
        "right_retrieval_hash": right_claim["retrieval_hash"],
        "left_section_uid": left_claim["source_section_id"],
        "right_section_uid": right_claim["source_section_id"],
        "shared_target": left_claim["target"],
        "retrieval_sources": ["dense_claim_retrieval"],
        "signals": ["semantic_same_target"],
        "triage": {
            "send_to_review": send_to_review,
            "reason": "Claims share a target and require Conflict Review evaluation.",
            "confidence": "medium",
        },
        "evidence": [
            {
                "claim_uid": left_claim["claim_uid"],
                "section_uid": left_claim["source_section_id"],
                "evidence_span": left_claim["evidence_span"],
                "evidence_start": left_claim["evidence_start"],
                "evidence_end": left_claim["evidence_end"],
                "evidence_hash": left_claim["evidence_hash"],
            },
            {
                "claim_uid": right_claim["claim_uid"],
                "section_uid": right_claim["source_section_id"],
                "evidence_span": right_claim["evidence_span"],
                "evidence_start": right_claim["evidence_start"],
                "evidence_end": right_claim["evidence_end"],
                "evidence_hash": right_claim["evidence_hash"],
            },
        ],
    }


def _spec_claim_fixture() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    left = _claim(
        "alpha",
        source_section_id="docs/spec/conflict.md#alpha",
        claim_text="FEATURE_X is required for all requests.",
    )
    right = _claim(
        "beta",
        source_section_id="docs/spec/conflict.md#beta",
        claim_text="FEATURE_X is forbidden for guest requests.",
    )
    return [left, right], [_candidate_pair(left, right)]


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


def _pending_item(conflict_id: str = "conflict-feature-x") -> dict[str, Any]:
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
        "recommended_next_action": "Ask a human for a decision.",
        "base_source_hashes": [
            {"source_ref": "docs/spec/conflict.md#alpha", "hash": "hash-a"},
            {"source_ref": "docs/spec/conflict.md#beta", "hash": "hash-b"},
        ],
        "valid_scope": "global",
        "reflection_status": "unreflected",
        "reflected_refs": [],
        "stale_dismissal": False,
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


def test_t_i04_unresolved_spec_claim_pair_creates_pending_item() -> None:
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
    claims, pairs = _spec_claim_fixture()

    result = _call(
        evaluate,
        _positional=(pairs, judge),
        conflict_candidate_pairs=pairs,
        spec_claims=claims,
        sections=_sections(),
        provider=judge,
        judge=judge,
        conflict_judge=judge,
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
    )
    items = _items(result)

    assert judge.calls, "triaged SpecClaim pair must be sent to the injected fake judge"
    assert len(items) == 1
    assert items[0]["status"] == "pending"
    assert items[0]["source_refs"]
    assert items[0]["why_llm_cannot_decide"]


def test_t_i04_resolvable_spec_claim_pair_is_warning_not_pending() -> None:
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
    claims, pairs = _spec_claim_fixture()

    result = _call(
        evaluate,
        _positional=(pairs, judge),
        conflict_candidate_pairs=pairs,
        spec_claims=claims,
        sections=_sections(),
        provider=judge,
        judge=judge,
        conflict_judge=judge,
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
    )

    assert judge.calls, "triaged SpecClaim pair must still be judged"
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
    assert ("decision" + "_options") not in item
    assert item["recommended_next_action"]


def test_t_u20_conflict_pair_selection_uses_triaged_spec_claim_pairs() -> None:
    module = _module()
    select_pairs = _required_function(
        module,
        (
            "select_conflict_judging_pairs",
            "build_conflict_judging_pairs",
            "candidate_conflict_pairs",
        ),
    )
    claims, pairs = _spec_claim_fixture()
    skipped_pair = _candidate_pair(claims[0], claims[1], send_to_review=False)
    duplicate_pair = dict(pairs[0])

    result = _call(
        select_pairs,
        _positional=([pairs[0], skipped_pair, duplicate_pair],),
        conflict_candidate_pairs=[pairs[0], skipped_pair, duplicate_pair],
        spec_claims=claims,
    )
    pairs = result.get("pairs", result.get("conflict_pairs", result)) if isinstance(result, dict) else result
    assert isinstance(pairs, list), "conflict pair selection must return list-like pairs"

    assert len(pairs) == 1
    assert pairs[0]["left_claim_uid"] == claims[0]["claim_uid"]
    assert pairs[0]["right_claim_uid"] == claims[1]["claim_uid"]
    assert pairs[0]["source_section_id"] == "docs/spec/conflict.md#alpha"
    assert pairs[0]["target_section_id"] == "docs/spec/conflict.md#beta"
    assert [claim["claim_uid"] for claim in pairs[0]["claims"]] == [
        claims[0]["claim_uid"],
        claims[1]["claim_uid"],
    ]


def test_conflict_review_accepts_only_spec_claim_pair_input() -> None:
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
    claims, pairs = _spec_claim_fixture()
    retired_flag = "possible" + "_conflict"
    previous_shape = {
        "docs/spec/conflict.md#alpha": [
            {
                "source_section_id": "docs/spec/conflict.md#alpha",
                "target_section_id": "docs/spec/conflict.md#beta",
                "relation_hint": "depends_on",
                retired_flag: True,
            }
        ]
    }

    with pytest.raises(TypeError):
        evaluate(related_sections=previous_shape, conflict_judge=judge)

    result = _call(
        evaluate,
        conflict_candidate_pairs=pairs,
        spec_claims=claims,
        sections=_sections(),
        conflict_judge=judge,
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
    )
    items = _items(result)

    assert judge.calls, "triaged SpecClaim pair input must be judged"
    assert len(items) == 1
    assert items[0]["spec_claim_pair"]["triage"]["send_to_review"] is True


def test_conflict_review_concurrency_uses_config_limits() -> None:
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
    active = 0
    max_active = 0
    lock = threading.Lock()

    class TrackingJudge:
        def judge_conflict(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
            nonlocal active, max_active
            del request, timeout_sec
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            return {"outcome": "not_a_conflict", "severity": "low"}

    claims = [
        _claim(
            f"s{index}",
            source_section_id=f"docs/spec/conflict.md#s{index}",
            claim_text=f"FEATURE_X rule {index}.",
        )
        for index in range(5)
    ]
    pairs = [_candidate_pair(claims[0], claims[index]) for index in range(1, 5)]

    _call(
        evaluate,
        conflict_candidate_pairs=pairs,
        spec_claims=claims,
        sections=[
            _section(
                f"docs/spec/conflict.md#s{index}",
                text=f"FEATURE_X rule {index}.",
                ordinal=index + 1,
            )
            for index in range(5)
        ],
        conflict_judge=TrackingJudge(),
        config=_config(llm_batch_concurrency=1),
    )

    assert max_active == 1


def test_conflict_review_concurrency_uses_mapping_config_limits() -> None:
    module = _module()
    get_concurrency = getattr(module, "_get_llm_batch_concurrency")

    assert get_concurrency(config={"limits": {"llm_batch_concurrency": 2}}) == 2
    assert get_concurrency(limits={"llm_batch_concurrency": 3}) == 3


def test_core_does_not_route_related_sections_to_conflict_review() -> None:
    core = importlib.import_module("spec_anchor.core")
    source = inspect.getsource(core._run_spec_core_unlocked)

    assert "related_sections=selected_related_sections" not in source
    assert "conflict_candidate_pairs=" in source
