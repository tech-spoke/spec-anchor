"""Freshness Gate contract tests for G-10.

The Freshness Gate is the shared public decision point for `/spec-inject` and
`/spec-realign`.  These tests intentionally accept dictionaries or dataclasses
so the builder can choose the concrete API shape while preserving the public
contract from the design docs.
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


def _module() -> Any:
    try:
        return importlib.import_module("spec_anchor.freshness")
    except ModuleNotFoundError as exc:
        if exc.name == "spec_anchor.freshness":
            pytest.fail("spec_anchor.freshness module is required for G-10")
        raise


def _required_function(module: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail("Freshness API is required; expected one of: " + ", ".join(names))


def _call(func: Any, state: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    state = state or {}
    candidates = {
        "_positional": (state,),
        "state": state,
        "inputs": state,
        "freshness_inputs": state,
        "project_state": state,
        "context_state": state,
        "source_sections": state.get("source_sections"),
        "current_sections": state.get("source_sections"),
        "manifest": state.get("manifest"),
        "section_manifest": state.get("manifest"),
        "artifacts": state.get("artifacts"),
        "artifact_statuses": state.get("artifact_statuses"),
        "config": state.get("config"),
        "artifact_config": state.get("artifact_config"),
        "watcher": state.get("watcher"),
        "watcher_state": state.get("watcher"),
        "conflict_review_items": state.get("conflict_review_items"),
        "items": state.get("conflict_review_items"),
        **kwargs,
    }
    supported = {
        name: value
        for name, value in candidates.items()
        if name in signature.parameters and value is not None
    }
    try:
        return func(**supported)
    except TypeError:
        return func(*candidates.get("_positional", ()), **supported)


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


def _report(payload: Any) -> Any:
    for key in ("freshness_report", "report", "freshness"):
        nested = _value(payload, key)
        if nested is not None:
            return nested
    return payload


def _status(payload: Any) -> str:
    status = _value(_report(payload), "status")
    assert isinstance(status, str), "freshness report must expose status"
    return status


def _reasons(payload: Any) -> list[str]:
    report = _report(payload)
    reasons = (
        _value(report, "blocking_reasons")
        or _value(report, "reasons")
        or _value(report, "reason_codes")
        or []
    )
    assert isinstance(reasons, list), "freshness report must expose reason list"
    return reasons


def _warnings(payload: Any) -> list[Any]:
    warnings = _value(_report(payload), "warnings", default=[])
    assert isinstance(warnings, list), "freshness report warnings must be list-like"
    return warnings


def _string_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {_string_blob(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_string_blob(item) for item in value)
    return "" if value is None else str(value)


def _continue_allowed(decision: Any) -> bool:
    for key in ("should_continue", "continue", "allowed", "ok", "can_continue"):
        value = _value(decision, key)
        if isinstance(value, bool):
            return value
    action = str(_value(decision, "action", default="")).lower()
    if action in {"continue", "allow", "proceed"}:
        return True
    if action in {"stop", "block", "fail"}:
        return False
    pytest.fail("command gate decision must expose continue/stop as a boolean or action")


def _freshness_function() -> Any:
    return _required_function(
        _module(),
        (
            "build_freshness_report",
            "evaluate_freshness",
            "check_freshness",
            "freshness_report",
            "get_freshness_report",
        ),
    )


def _gate_function() -> Any:
    return _required_function(
        _module(),
        (
            "apply_freshness_gate",
            "evaluate_command_gate",
            "check_command_gate",
            "check_freshness_gate",
            "gate_command",
        ),
    )


def _base_state(**overrides: Any) -> dict[str, Any]:
    section = {
        "section_id": "docs/spec/main.md#freshness-gate",
        "source_hash": "source-hash-a",
        "semantic_hash": "semantic-hash-a",
    }
    state: dict[str, Any] = {
        "source_sections": [section],
        "manifest": {
            "sections": [section],
            "purpose_hash": "purpose-hash-a",
            "concept_hash": "concept-hash-a",
        },
        "config": {
            "embedding": {"provider": "flagembedding", "model": "BAAI/bge-m3"},
            "llm": {"provider": "codex_cli", "model": "gpt-5.4-mini"},
            "prompt_versions": {"section_metadata": "section-metadata-v1"},
            "section_metadata_version": 1,
        },
        "artifact_config": {
            "embedding": {"provider": "flagembedding", "model": "BAAI/bge-m3"},
            "llm": {"provider": "codex_cli", "model": "gpt-5.4-mini"},
            "prompt_versions": {"section_metadata": "section-metadata-v1"},
            "section_metadata_version": 1,
        },
        "artifacts": {
            "section_manifest": {
                "sections": [section],
                "purpose_hash": "purpose-hash-a",
                "concept_hash": "concept-hash-a",
            },
            "section_metadata": {
                "metadata_version": 1,
                "prompt_version": "section-metadata-v1",
                "sections": [
                    {
                        "section_id": section["section_id"],
                        "source_hash": section["source_hash"],
                        "semantic_hash": section["semantic_hash"],
                        "metadata_version": 1,
                        "prompt_version": "section-metadata-v1",
                    }
                ],
            },
            "chapter_anchors": {"status": "success", "chapters": []},
        },
        "artifact_statuses": {
            "section_manifest": "success",
            "section_metadata": "success",
            "chapter_anchors": "success",
        },
        "watcher": {"running": False, "queue_pending": False},
        "conflict_review_items": [],
    }
    state.update(overrides)
    return state


def _pending_conflict(conflict_id: str = "conflict-1") -> dict[str, Any]:
    return {
        "conflict_id": conflict_id,
        "status": "pending",
        "severity": "medium",
        "source_refs": [
            {
                "source_section_id": "docs/spec/main.md#freshness-gate",
                "source_hash": "source-hash-a",
            }
        ],
        "why_conflicting": "two sections disagree",
        "why_llm_cannot_decide": "no safe priority",
        "recommended_next_action": "Ask a human to decide this conflict.",
    }


def _freshness(state: dict[str, Any]) -> Any:
    return _call(_freshness_function(), state)


def _gate(command: str, freshness_report: Any) -> Any:
    return _call(
        _gate_function(),
        {"freshness_report": _report(freshness_report)},
        command=command,
        freshness_report=_report(freshness_report),
        report=_report(freshness_report),
    )


def test_t_u03_fresh_report_has_no_reasons() -> None:
    """CLI determines freshness and writes the report to `freshness.json`.
    """

    report = _freshness(_base_state())

    assert _status(report) == "fresh"
    assert _reasons(report) == []
    assert _warnings(report) == []


def test_t_u03_dirty_or_stale_source_blocks() -> None:
    state = _base_state(
        source_sections=[
            {
                "section_id": "docs/spec/main.md#freshness-gate",
                "source_hash": "source-hash-b",
                "semantic_hash": "semantic-hash-b",
            }
        ]
    )

    report = _freshness(state)

    assert _status(report) == "blocked"
    assert "dirty_or_stale_source" in _reasons(report)


def test_t_u03_deleted_stored_source_section_blocks() -> None:
    deleted_section = {
        "section_id": "docs/spec/main.md#deleted",
        "source_hash": "source-hash-deleted",
        "semantic_hash": "semantic-hash-deleted",
    }
    state = _base_state()
    state["artifacts"]["section_manifest"]["sections"] = [
        *state["artifacts"]["section_manifest"]["sections"],
        deleted_section,
    ]

    report = _freshness(state)

    assert _status(report) == "blocked"
    assert "dirty_or_stale_source" in _reasons(report)


@pytest.mark.parametrize("hash_key", ("purpose_hash", "concept_hash"))
def test_t_u03_purpose_or_concept_hash_drift_blocks(hash_key: str) -> None:
    state = _base_state()
    state["manifest"][hash_key] = f"{hash_key}-current"

    report = _freshness(state)

    assert _status(report) == "blocked"
    assert "dirty_or_stale_source" in _reasons(report)


@pytest.mark.parametrize(
    ("watcher", "reason"),
    (
        ({"running": True, "queue_pending": False}, "watcher_running"),
        ({"running": False, "queue_pending": True}, "watcher_queue_pending"),
    ),
)
def test_t_u03_watcher_running_or_queue_pending_blocks(
    watcher: dict[str, bool], reason: str
) -> None:
    report = _freshness(_base_state(watcher=watcher))

    assert _status(report) == "blocked"
    assert reason in _reasons(report)


@pytest.mark.parametrize(
    "state",
    (
        _base_state(
            config={
                "embedding": {"provider": "flagembedding", "model": "BAAI/bge-m3-new"},
                "llm": {"provider": "codex_cli", "model": "gpt-5.4-mini"},
                "prompt_versions": {"section_metadata": "section-metadata-v1"},
                "section_metadata_version": 1,
            }
        ),
        _base_state(
            config={
                "embedding": {"provider": "flagembedding", "model": "BAAI/bge-m3"},
                "llm": {"provider": "codex_cli", "model": "gpt-5.4-mini"},
                "prompt_versions": {"section_metadata": "section-metadata-v2"},
                "section_metadata_version": 1,
            }
        ),
        _base_state(
            config={
                "embedding": {"provider": "flagembedding", "model": "BAAI/bge-m3"},
                "llm": {"provider": "codex_cli", "model": "gpt-5.4-mini"},
                "prompt_versions": {"section_metadata": "section-metadata-v1"},
                "section_metadata_version": 2,
            }
        ),
    ),
)
def test_t_u03_stale_config_or_schema_blocks(state: dict[str, Any]) -> None:
    report = _freshness(state)

    assert _status(report) == "blocked"
    assert "stale_config_or_schema" in _reasons(report)


def test_t_u03_pending_conflict_does_not_block() -> None:
    # TODO #1: pending Conflict Review Items are surfaced as information, not a
    # freshness blocking reason. A project whose only signal is pending
    # conflicts is still `fresh`.
    report = _freshness(_base_state(conflict_review_items=[_pending_conflict()]))

    assert _status(report) == "fresh"
    assert "pending_conflict" not in _reasons(report)


def test_t_u03_legacy_blocked_without_reasons_normalizes_to_fresh() -> None:
    decision = _gate(
        "/spec-inject",
        {"status": "blocked", "blocking_reasons": [], "warnings": []},
    )

    assert _continue_allowed(decision) is True
    assert _value(decision, "freshness_report", "status") == "fresh"


def test_t_u07_artifact_failure_status_blocks_as_failed() -> None:
    # TODO #7: there is no `degraded` status. Any non-success artifact status
    # (including the historical `degraded`) is a required-artifact failure that
    # stops the gate with status="failed".
    report = _freshness(
        _base_state(
            artifact_statuses={
                "section_manifest": "success",
                "section_metadata": "degraded",
                "chapter_anchors": "success",
            }
        )
    )

    assert _status(report) == "failed"
    assert "failed_required_artifact" in _reasons(report)

    decision = _gate("/spec-inject", report)
    assert _continue_allowed(decision) is False


def test_t_u03_required_artifact_failure_fails_and_stops() -> None:
    report = _freshness(
        _base_state(
            artifact_statuses={
                "section_manifest": "failed",
                "section_metadata": "success",
                "chapter_anchors": "success",
            }
        )
    )

    assert _status(report) == "failed"
    assert "failed_required_artifact" in _reasons(report)

    decision = _gate("/spec-realign", report)
    assert _continue_allowed(decision) is False


def test_t_u03_required_artifact_failure_wins_with_blocked_reasons() -> None:
    report = _freshness(
        _base_state(
            source_sections=[
                {
                    "section_id": "docs/spec/main.md#freshness-gate",
                    "source_hash": "source-hash-b",
                    "semantic_hash": "semantic-hash-b",
                }
            ],
            artifact_statuses={
                "section_manifest": "failed",
                "section_metadata": "success",
                "chapter_anchors": "success",
            },
        )
    )

    assert _status(report) == "failed"
    assert _reasons(report) == ["dirty_or_stale_source", "failed_required_artifact"]


def test_t_u03_dirty_plus_pending_reasons_are_priority_sorted_and_core_first() -> None:
    state = _base_state(
        source_sections=[
            {
                "section_id": "docs/spec/main.md#freshness-gate",
                "source_hash": "source-hash-b",
                "semantic_hash": "semantic-hash-b",
            }
        ],
        conflict_review_items=[_pending_conflict()],
    )

    report = _freshness(state)

    # TODO #1: with both a dirty source and pending conflicts, the gate blocks
    # on the dirty source only; pending is not a blocking reason.
    assert _status(report) == "blocked"
    assert _reasons(report) == ["dirty_or_stale_source"]
    assert "pending_conflict" not in _reasons(report)

    decision = _gate("/spec-inject", report)
    text = _string_blob(decision)
    assert _continue_allowed(decision) is False
    assert "/spec-core" in text


@pytest.mark.parametrize("command", ("/spec-inject", "/spec-realign"))
@pytest.mark.parametrize(
    ("report", "should_continue"),
    (
        ({"status": "fresh", "blocking_reasons": [], "warnings": []}, True),
        (
            {
                "status": "blocked",
                "blocking_reasons": ["dirty_or_stale_source"],
                "warnings": [],
            },
            False,
        ),
        (
            {
                "status": "failed",
                "blocking_reasons": ["failed_required_artifact"],
                "warnings": [],
            },
            False,
        ),
    ),
)
def test_t_u04_command_gate_continue_or_stop(
    command: str, report: dict[str, Any], should_continue: bool
) -> None:
    decision = _gate(command, report)

    assert _continue_allowed(decision) is should_continue


def test_t_u04_pending_only_gate_continues_and_surfaces_items() -> None:
    # TODO #1: a pending-only gate does not stop; it continues (fresh) while
    # still surfacing the pending conflict items for the Agent to present.
    pending = _pending_conflict("conflict-pending-only")
    report = {
        "status": "fresh",
        "blocking_reasons": [],
        "warnings": [],
        "pending_conflict_items": [pending],
        "conflict_review_items": [pending],
    }

    decision = _gate("/spec-inject", report)
    text = _string_blob(decision)

    assert _continue_allowed(decision) is True
    for expected in (
        "conflict-pending-only",
        "severity",
        "source_refs",
        "why_conflicting",
        "why_llm_cannot_decide",
        "recommended_next_action",
    ):
        assert expected in text


@pytest.mark.parametrize("item_key", ("pending_conflict_items", "conflict_review_items"))
def test_t_u04_pending_gate_copies_report_conflicts_to_top_level(item_key: str) -> None:
    pending = _pending_conflict(f"conflict-from-{item_key}")
    report = {
        "status": "fresh",
        "blocking_reasons": [],
        "warnings": [],
        item_key: [pending],
    }

    decision = _gate("/spec-inject", report)

    assert _continue_allowed(decision) is True
    assert _value(decision, "pending_conflict_items") == [pending]
    assert _value(decision, "pending_conflict_count") == 1
