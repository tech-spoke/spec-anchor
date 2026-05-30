"""Tests for dismissal staleness + reopen (TODO #4 T-dismiss-staleness-reopen).

A dismissed Conflict Review Item is reopened to ``pending`` when its evidence
sections change (hash drift on `base_source_hashes`); an unchanged dismissal is
kept. The legacy ``stale_resolution`` symbol is renamed to ``stale_dismissal``.
"""

from __future__ import annotations

from spec_anchor.conflict_review import (
    refresh_conflict_dismissal_staleness,
    summarize_conflict_review_state,
)
from spec_anchor.core import _merge_conflict_items, _reopen_dismissed_conflict


def _dismissed_item(conflict_id: str = "cnf-1", base_hash: str = "old") -> dict:
    return {
        "conflict_id": conflict_id,
        "status": "dismissed",
        "source_section_id": "sec-1",
        "target_section_id": "sec-2",
        "source_refs": [
            {"source_section_id": "sec-1", "source_hash": base_hash},
            {"source_section_id": "sec-2", "source_hash": "h2"},
        ],
        "base_source_hashes": [
            {"source_ref": "sec-1", "hash": base_hash},
            {"source_ref": "sec-2", "hash": "h2"},
        ],
        "valid_scope": "global",
        "reflection_status": "not_required",
        "resolution": {"decision": "dismiss", "decision_origin": "human"},
    }


def test_reopen_when_dismissal_evidence_changes() -> None:
    item = _dismissed_item()
    merged, auto = _merge_conflict_items(
        [item],
        [],
        current_source_hashes={"sec-1": "NEW", "sec-2": "h2"},
        allow_pair_absent_auto_dismiss=False,
    )
    result = {i["conflict_id"]: i for i in merged}["cnf-1"]
    assert result["status"] == "pending"
    assert "reopened_at" in result
    assert result.get("stale_dismissal") is False


def test_dismissal_kept_when_sources_unchanged() -> None:
    item = _dismissed_item()
    merged, _ = _merge_conflict_items(
        [item],
        [],
        current_source_hashes={"sec-1": "old", "sec-2": "h2"},
        allow_pair_absent_auto_dismiss=False,
    )
    result = {i["conflict_id"]: i for i in merged}["cnf-1"]
    assert result["status"] == "dismissed"


def test_reopened_pair_lets_fresh_conflict_through() -> None:
    item = _dismissed_item()
    fresh = {
        "conflict_id": "cnf-1",
        "status": "pending",
        "source_section_id": "sec-1",
        "target_section_id": "sec-2",
        "source_refs": [
            {"source_section_id": "sec-1", "source_hash": "NEW"},
            {"source_section_id": "sec-2", "source_hash": "h2"},
        ],
        "base_source_hashes": [
            {"source_ref": "sec-1", "hash": "NEW"},
            {"source_ref": "sec-2", "hash": "h2"},
        ],
    }
    merged, _ = _merge_conflict_items(
        [item],
        [fresh],
        current_source_hashes={"sec-1": "NEW", "sec-2": "h2"},
    )
    result = {i["conflict_id"]: i for i in merged}["cnf-1"]
    assert result["status"] == "pending"


def test_reopen_helper_clears_resolution() -> None:
    reopened = _reopen_dismissed_conflict(_dismissed_item(), generated_at="2026-05-30T00:00:00Z")
    assert reopened["status"] == "pending"
    assert "resolution" not in reopened
    assert reopened["previous_resolution"]["decision"] == "dismiss"


def test_refresh_marks_stale_dismissal_field() -> None:
    changed = refresh_conflict_dismissal_staleness(
        conflict_review_items=[_dismissed_item()],
        current_source_hashes={"sec-1": "NEW", "sec-2": "h2"},
    )
    assert changed[0]["stale_dismissal"] is True
    assert "stale_resolution" not in changed[0]

    unchanged = refresh_conflict_dismissal_staleness(
        conflict_review_items=[_dismissed_item()],
        current_source_hashes={"sec-1": "old", "sec-2": "h2"},
    )
    assert unchanged[0]["stale_dismissal"] is False


def test_summary_uses_stale_dismissal_count() -> None:
    item = _dismissed_item()
    item["stale_dismissal"] = True
    summary = summarize_conflict_review_state(conflict_review_items=[item])
    assert "stale_dismissal_count" in summary
    assert summary["stale_dismissal_count"] == 1
