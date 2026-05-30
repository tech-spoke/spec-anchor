"""Conflict Review Item contract tests for G-09.

Conflict Review Items surface unresolved Source Spec conflicts to humans.
Resolvable conflicts stay diagnostics / warnings. The only persistent human
write path is dismissing an item as not a real conflict.
"""

from __future__ import annotations

import importlib
import inspect
import json
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


def test_t_u14_pending_item_required_schema_fields() -> None:
    module = _module()
    validate = _required_function(
        module,
        (
            "validate_conflict_review_item",
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
        "why_conflicting",
        "why_llm_cannot_decide",
        "related_sections",
        "recommended_next_action",
        "base_source_hashes",
        "valid_scope",
        "created_at",
        "updated_at",
    }
    assert required_fields.issubset(item)
    assert set(item).issubset(module.CONFLICT_REVIEW_ITEM_FIELDS)
    assert item["status"] == "pending"
    assert item["source_refs"]
    assert item["recommended_next_action"]


def test_conflict_review_item_rejects_unknown_fields() -> None:
    module = _module()
    validate = _required_function(
        module,
        (
            "validate_conflict_review_item",
            "build_conflict_review_item",
        ),
    )
    item = _pending_item()
    item["unexpected_contract_field"] = True

    with pytest.raises(ValueError, match="unknown conflict review item field"):
        _call(validate, item=item, generated_at="2026-05-06T00:00:00Z")


@dataclass
class FakeSectionPairJudge:
    """Judge that judges two whole sections directly (no claim extraction)."""

    outcome: str

    def __post_init__(self) -> None:
        self.calls: list[Any] = []

    def judge_conflict(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
        del timeout_sec
        self.calls.append(request)
        if self.outcome == "unresolved":
            return {
                "outcome": "needs_human_review",
                "severity": "high",
                "conflict_points": [
                    {
                        "left_excerpt": "FEATURE_X is required for all requests.",
                        "right_excerpt": "FEATURE_X is forbidden for guest requests.",
                        "why_conflicting": "Required and forbidden cannot both hold.",
                        "severity": "high",
                    }
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


def test_section_pair_id_is_order_independent_and_handles_self_pair() -> None:
    module = _module()
    section_pair_id = module.section_pair_id

    assert section_pair_id("a", "b") == section_pair_id("b", "a")
    assert section_pair_id("a", "b").startswith("section_pair:sha256:v1:")
    # different unordered pairs must not collide
    assert section_pair_id("a", "b") != section_pair_id("a", "c")
    # self-pair is stable and distinct from a cross-pair
    assert section_pair_id("a", "a") == section_pair_id("a", "a")
    assert section_pair_id("a", "a") != section_pair_id("a", "b")


def test_build_section_pair_conflict_item_matches_schema_and_validates() -> None:
    module = _module()
    builder = module._build_section_pair_conflict_item
    sections = _sections()
    # pass sections in non-sorted order to verify canonical left/right ordering
    section_a = sections[1]  # ...#beta
    section_b = sections[0]  # ...#alpha
    judge_payload = {
        "outcome": "needs_human_review",
        "severity": "high",
        "conflict_points": [
            {
                "left_excerpt": "alpha excerpt",
                "right_excerpt": "beta excerpt",
                "why_conflicting": "they disagree",
                "severity": "high",
            }
        ],
        "why_conflicting": "summary level",
        "why_llm_cannot_decide": "no priority",
    }

    item = builder(
        section_a,
        section_b,
        judge_payload,
        candidate_origin="section_pair_retrieval",
        generated_at="2026-05-06T00:00:00Z",
    )

    expected_id = module.section_pair_id(
        section_a["source_section_id"], section_b["source_section_id"]
    )
    assert item["conflict_id"] == expected_id
    assert item["valid_scope"] == "section_pair"
    assert item["status"] == "pending"
    # The section_pair item only carries fields in the current schema; the
    # claim-era fields are no longer allowed. related_sections is a general
    # field the validator setdefaults to empty.
    assert set(item).issubset(module.CONFLICT_REVIEW_ITEM_FIELDS)
    assert item.get("related_sections", []) == []
    section_pair = item["section_pair"]
    assert section_pair["section_pair_id"] == expected_id
    # canonical sorted order: alpha < beta lexicographically
    assert section_pair["left_section_id"] == "docs/spec/conflict.md#alpha"
    assert section_pair["right_section_id"] == "docs/spec/conflict.md#beta"
    assert section_pair["candidate_origin"] == "section_pair_retrieval"
    assert len(item["source_refs"]) == 2
    assert item["conflict_points"] == judge_payload["conflict_points"]
    assert item["base_source_hashes"]
    # validates without raising and round-trips through the validator
    revalidated = module.validate_conflict_review_item(
        item=item, generated_at="2026-05-06T00:00:00Z"
    )
    assert revalidated["conflict_id"] == expected_id


def test_build_section_pair_conflict_item_self_pair_single_ref() -> None:
    module = _module()
    builder = module._build_section_pair_conflict_item
    section = _sections()[0]

    item = builder(section, section, {"outcome": "needs_human_review"})

    pair = item["section_pair"]
    assert pair["left_section_id"] == pair["right_section_id"]
    assert pair["candidate_origin"] == "all_pairs"
    assert len(item["source_refs"]) == 1


def test_evaluate_section_pair_conflicts_pending_item_with_conflict_points() -> None:
    module = _module()
    evaluate = module.evaluate_section_pair_conflicts
    judge = FakeSectionPairJudge("unresolved")
    section_pairs = [
        {
            "left_section_id": "docs/spec/conflict.md#alpha",
            "right_section_id": "docs/spec/conflict.md#beta",
            "candidate_origin": "all_pairs",
        }
    ]

    result = evaluate(
        section_pairs,
        judge,
        sections=_sections(),
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
    )
    items = _items(result)

    assert judge.calls, "section pair must be judged"
    # request carries section_a/section_b/source_refs (grounding added by wrapper)
    request = judge.calls[0]
    assert set(request) == {"section_a", "section_b", "source_refs"}
    assert len(items) == 1
    assert items[0]["status"] == "pending"
    assert items[0]["valid_scope"] == "section_pair"
    assert items[0]["conflict_points"] == [
        {
            "left_excerpt": "FEATURE_X is required for all requests.",
            "right_excerpt": "FEATURE_X is forbidden for guest requests.",
            "why_conflicting": "Required and forbidden cannot both hold.",
            "severity": "high",
        }
    ]
    assert items[0]["why_conflicting"] == "FEATURE_X is simultaneously required and forbidden."
    assert items[0]["why_conflicting"] != "Potential source specifications conflict."
    assert (
        items[0]["why_llm_cannot_decide"]
        == "No Purpose or Core Concept priority exists."
    )
    assert (
        items[0]["recommended_next_action"]
        == "Ask a human to choose the applicable rule."
    )
    assert items[0]["section_pair"]["candidate_origin"] == "all_pairs"
    assert result.pending_conflict_count == 1


def test_evaluate_section_pair_conflicts_reports_call_budget_counts() -> None:
    module = _module()
    evaluate = module.evaluate_section_pair_conflicts
    section_pairs = [
        {
            "left_section_id": "docs/spec/conflict.md#alpha",
            "right_section_id": "docs/spec/conflict.md#beta",
            "candidate_origin": "all_pairs",
        },
        {
            "left_section_id": "docs/spec/conflict.md#beta",
            "right_section_id": "docs/spec/conflict.md#gamma",
            "candidate_origin": "section_pair_retrieval",
        },
        {
            "left_section_id": "docs/spec/conflict.md#alpha",
            "right_section_id": "docs/spec/conflict.md#gamma",
            "candidate_origin": "existing_conflict_recheck",
        },
        {"left_section_id": "docs/spec/conflict.md#alpha"},
    ]

    class CountingJudge:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def judge_conflict(
            self,
            request: dict[str, Any],
            *,
            timeout_sec: int = 5,
        ) -> dict[str, Any]:
            del timeout_sec
            self.calls.append(request)
            return {
                "outcome": "resolved_by_existing_evidence",
                "warning": "Existing evidence resolves this pair.",
            }

    judge = CountingJudge()
    result = evaluate(
        section_pairs,
        judge,
        sections=_sections(),
        config=_config(llm_batch_concurrency=1),
        generated_at="2026-05-06T00:00:00Z",
    )

    assert len(judge.calls) == 3
    assert result.judge_pair_count == 3
    assert result.llm_call_count == 3
    assert result.to_dict()["judge_pair_count"] == 3
    assert result.to_dict()["llm_call_count"] == 3


def test_build_conflict_review_llm_request_preserves_section_text_for_quotes() -> None:
    core = importlib.import_module("spec_anchor.core")
    build_request = core._build_conflict_review_llm_request

    llm_request = build_request(
        {
            "section_a": {
                "source_section_id": "docs/spec/conflict.md#alpha",
                "text": "Alpha requires FEATURE_X for all requests.",
            },
            "section_b": {
                "source_section_id": "docs/spec/conflict.md#beta",
                "text": "Beta forbids FEATURE_X for guest requests.",
            },
            "source_refs": [
                {
                    "source_section_id": "docs/spec/conflict.md#alpha",
                    "source_hash": "hash-alpha",
                },
                {
                    "source_section_id": "docs/spec/conflict.md#beta",
                    "source_hash": "hash-beta",
                },
            ],
        },
        {"model": "fake-model", "effort": "low"},
    )

    payload = json.loads(llm_request.prompt)
    assert payload["section_a"]["text"] == "Alpha requires FEATURE_X for all requests."
    assert payload["section_b"]["text"] == "Beta forbids FEATURE_X for guest requests."
    assert llm_request.section_hashes == {
        "docs/spec/conflict.md#alpha": "hash-alpha",
        "docs/spec/conflict.md#beta": "hash-beta",
    }


def test_evaluate_section_pair_conflicts_resolved_is_non_pending_signal() -> None:
    module = _module()
    evaluate = module.evaluate_section_pair_conflicts
    judge = FakeSectionPairJudge("resolved")
    section_pairs = [
        {
            "left_section_id": "docs/spec/conflict.md#alpha",
            "right_section_id": "docs/spec/conflict.md#beta",
            "candidate_origin": "existing_conflict_recheck",
        }
    ]

    result = evaluate(
        section_pairs,
        judge,
        sections=_sections(),
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
    )

    assert judge.calls, "section pair must still be judged"
    assert _items(result) == []
    assert result.non_pending_conflict_signals
    signal = result.non_pending_conflict_signals[0]
    assert signal["conflict_id"] == module.section_pair_id(
        "docs/spec/conflict.md#alpha", "docs/spec/conflict.md#beta"
    )
    assert signal["outcome"] == "resolved_by_existing_evidence"
    diagnostics = _diagnostics(result)
    assert any(item.get("kind") == "potential_conflict" for item in diagnostics)


def test_evaluate_section_pair_conflicts_uses_configured_concurrency_and_preserves_order() -> None:
    module = _module()
    evaluate = module.evaluate_section_pair_conflicts
    section_pairs = [
        {
            "left_section_id": "docs/spec/conflict.md#alpha",
            "right_section_id": "docs/spec/conflict.md#beta",
            "candidate_origin": "all_pairs",
        },
        {
            "left_section_id": "docs/spec/conflict.md#beta",
            "right_section_id": "docs/spec/conflict.md#gamma",
            "candidate_origin": "section_pair_retrieval",
        },
        {
            "left_section_id": "docs/spec/conflict.md#alpha",
            "right_section_id": "docs/spec/conflict.md#gamma",
            "candidate_origin": "existing_conflict_recheck",
        },
    ]

    class ConcurrentJudge:
        def __init__(self) -> None:
            self.lock = threading.Lock()
            self.in_flight = 0
            self.max_in_flight = 0
            self.two_in_flight = threading.Event()

        def judge_conflict(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
            del timeout_sec
            left_id = request["section_a"]["source_section_id"]
            right_id = request["section_b"]["source_section_id"]
            with self.lock:
                self.in_flight += 1
                self.max_in_flight = max(self.max_in_flight, self.in_flight)
                if self.in_flight >= 2:
                    self.two_in_flight.set()
            try:
                self.two_in_flight.wait(timeout=1.0)
                if left_id.endswith("#alpha") and right_id.endswith("#beta"):
                    time.sleep(0.12)
                elif left_id.endswith("#beta") and right_id.endswith("#gamma"):
                    time.sleep(0.01)
                else:
                    time.sleep(0.04)
                return {
                    "outcome": "needs_human_review",
                    "severity": "high",
                    "conflict_points": [
                        {
                            "left_excerpt": left_id,
                            "right_excerpt": right_id,
                            "why_conflicting": f"{left_id} conflicts with {right_id}",
                            "severity": "high",
                        }
                    ],
                    "why_conflicting": f"{left_id} conflicts with {right_id}",
                    "why_llm_cannot_decide": "No priority source is present.",
                    "__spec_anchor_usage": {"pair": f"{left_id}|{right_id}"},
                }
            finally:
                with self.lock:
                    self.in_flight -= 1

    judge = ConcurrentJudge()
    result = evaluate(
        section_pairs,
        judge,
        sections=_sections(),
        config={"limits": {"llm_batch_concurrency": 3}},
        generated_at="2026-05-06T00:00:00Z",
    )

    expected_pair_ids = [
        module.section_pair_id(pair["left_section_id"], pair["right_section_id"])
        for pair in section_pairs
    ]
    items = _items(result)
    assert judge.max_in_flight > 1
    assert [item["section_pair"]["section_pair_id"] for item in items] == expected_pair_ids
    assert [usage["pair"] for usage in result.usage_list] == [
        f"{pair['left_section_id']}|{pair['right_section_id']}" for pair in section_pairs
    ]


def test_core_does_not_route_related_sections_to_conflict_review() -> None:
    core = importlib.import_module("spec_anchor.core")
    source = inspect.getsource(core._run_spec_core_unlocked)

    assert "related_sections=selected_related_sections" not in source
    # The section_pair conflict path judges generator-produced candidates, not
    # related_sections. evaluate_section_pair_conflicts receives cand.candidates.
    assert "evaluate_section_pair_conflicts(" in source
    assert "cand.candidates" in source
