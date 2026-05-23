#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-131632-codex-e2e-conflict-review-generation"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID
REQUIRED_ITEM_FIELDS = [
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
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_stdout(mode: str) -> dict[str, Any]:
    return read_json(EVID / "stdout" / f"{mode}-core-rebuild.stdout")


def read_exit(mode: str) -> int:
    return int((EVID / "stdout" / f"{mode}-core-rebuild.exitcode").read_text(encoding="utf-8").strip())


def invocations(mode: str) -> list[dict[str, Any]]:
    path = EVID / "artifacts" / f"{mode}-provider-invocations.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stages(mode: str) -> list[str]:
    return [str(item.get("stage")) for item in invocations(mode)]


def conflict_requests(mode: str) -> list[dict[str, Any]]:
    return [
        item.get("request") or {}
        for item in invocations(mode)
        if item.get("stage") == "conflict_review"
    ]


def has_item_shape(item: dict[str, Any]) -> bool:
    if not all(field in item for field in REQUIRED_ITEM_FIELDS):
        return False
    if item.get("status") != "pending":
        return False
    if not item.get("source_refs") or not item.get("claims"):
        return False
    if not item.get("why_conflicting") or not item.get("why_llm_cannot_decide"):
        return False
    if not item.get("related_sections") or not item.get("decision_options"):
        return False
    if not item.get("recommended_next_action"):
        return False
    if not item.get("base_source_hashes") or not item.get("valid_scope"):
        return False
    option_ids = {
        option.get("id")
        for option in item.get("decision_options", [])
        if isinstance(option, dict)
    }
    return {
        "prefer_a",
        "prefer_b",
        "conditional",
        "dismiss",
        "needs_source_update",
        "defer",
        "task_scope_resolution",
    }.issubset(option_ids)


def request_pair(request: dict[str, Any]) -> dict[str, Any]:
    pair = request.get("pair") if isinstance(request.get("pair"), dict) else {}
    return {
        "source_section_id": pair.get("source_section_id"),
        "target_section_id": pair.get("target_section_id"),
        "relation_hint": pair.get("relation_hint"),
        "possible_conflict": pair.get("possible_conflict"),
        "conflict_route": pair.get("conflict_route"),
        "channels": pair.get("channels"),
        "evidence_terms": pair.get("evidence_terms"),
    }


def main() -> int:
    pending = read_stdout("pending")
    warning = read_stdout("warning")
    highrisk = read_stdout("highrisk")
    pending_items = pending.get("conflict_review_items") or []
    warning_items = warning.get("conflict_review_items") or []
    highrisk_items = highrisk.get("conflict_review_items") or []
    pending_item = pending_items[0] if pending_items else {}
    highrisk_item = highrisk_items[0] if highrisk_items else {}
    pending_requests = conflict_requests("pending")
    warning_requests = conflict_requests("warning")
    highrisk_requests = conflict_requests("highrisk")
    pending_pair = request_pair(pending_requests[0]) if pending_requests else {}
    highrisk_pair = request_pair(highrisk_requests[0]) if highrisk_requests else {}

    checks = {
        "pending_exit_zero": read_exit("pending") == 0,
        "warning_exit_zero": read_exit("warning") == 0,
        "highrisk_exit_zero": read_exit("highrisk") == 0,
        "possible_conflict_referred_to_conflict_review": (
            pending_pair.get("possible_conflict") is True
            and pending_pair.get("relation_hint") == "conflicts_with"
            and pending_pair.get("conflict_route") == "possible_conflict_flag"
        ),
        "pending_conflict_created_and_blocks": (
            int(pending.get("pending_conflict_count") or 0) >= 1
            and (pending.get("freshness_report") or {}).get("status") == "blocked"
            and (pending.get("freshness_report") or {}).get("blocking_reasons") == ["pending_conflict"]
            and len(pending_items) >= 1
            and has_item_shape(pending_item)
        ),
        "no_auto_resolved_item": (
            all(item.get("status") != "resolved" for item in pending_items)
            and warning_items == []
            and warning.get("pending_conflict_count") == 0
        ),
        "warning_potential_conflict_when_judge_resolves": (
            warning_items == []
            and len(warning.get("potential_conflicts") or []) >= 1
            and (warning.get("freshness_report") or {}).get("status") in {"fresh", "degraded"}
        ),
        "stage_order_related_before_conflict": (
            "related_section_selection" in stages("pending")
            and "conflict_review" in stages("pending")
            and stages("pending").index("related_section_selection")
            < stages("pending").index("conflict_review")
        ),
        "highrisk_unselected_candidate_sent_to_conflict_review": (
            len(highrisk_requests) >= 1
            and highrisk_pair.get("relation_hint") == "conflicts_with"
            and "shared_identifier" in set(highrisk_pair.get("channels") or [])
            and "feature_gate" in {str(term).lower() for term in highrisk_pair.get("evidence_terms") or []}
            and len(highrisk_items) >= 1
            and has_item_shape(highrisk_item)
        ),
    }

    result = {
        "run_id": RUN_ID,
        "exitcodes": {
            "pending_core_rebuild": read_exit("pending"),
            "warning_core_rebuild": read_exit("warning"),
            "highrisk_core_rebuild": read_exit("highrisk"),
        },
        "checks": checks,
        "pending_pair": pending_pair,
        "highrisk_pair": highrisk_pair,
        "pending_item_fields": sorted(pending_item.keys()) if pending_item else [],
        "warning_potential_conflicts": warning.get("potential_conflicts") or [],
        "passed_all": all(checks.values()),
    }
    out = EVID / "artifacts" / "conflict-review-generation-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
