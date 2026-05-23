#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-130037-codex-e2e-inject-all-gates"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID

CASES = {
    "inject-search": {"must_not_have": ["hits", "collection", "query"]},
    "inject-section": {"must_not_have": ["sections", "found_section_ids", "missing_section_ids"]},
    "inject-chapters": {"must_not_have": ["chapter_anchors_path"]},
    "inject-purpose": {"must_not_have": ["purpose", "core_concept_path"]},
    "inject-conflicts": {"must_not_have": ["resolved_conflict_review_items", "excluded_conflict_review_items"]},
}


def read_json(label: str) -> dict[str, Any]:
    text = (EVID / "stdout" / f"{label}.stdout").read_text(encoding="utf-8")
    return json.loads(text)


def read_exit(label: str) -> int:
    return int((EVID / "stdout" / f"{label}.exitcode").read_text(encoding="utf-8").strip())


def main() -> int:
    initial = read_json("initial-core-rebuild")
    initial_exit = read_exit("initial-core-rebuild")
    case_results: dict[str, Any] = {}
    for label, expectation in CASES.items():
        payload = read_json(label)
        missing_success_fields = all(key not in payload for key in expectation["must_not_have"])
        case_results[label] = {
            "exit_code": read_exit(label),
            "status": payload.get("status"),
            "should_stop": payload.get("should_stop"),
            "blocking_reasons": payload.get("blocking_reasons"),
            "recommended_next_action": payload.get("recommended_next_action"),
            "has_success_specific_fields": not missing_success_fields,
            "passed": (
                read_exit(label) == 0
                and payload.get("status") == "blocked"
                and payload.get("should_stop") is True
                and list(payload.get("blocking_reasons") or []) == ["dirty_or_stale_source"]
                and payload.get("recommended_next_action") == "run /spec-core before /spec-inject"
                and missing_success_fields
            ),
        }

    result = {
        "run_id": RUN_ID,
        "initial_core": {
            "exit_code": initial_exit,
            "status": initial.get("status"),
            "freshness_status": (initial.get("freshness_report") or {}).get("status"),
            "passed": initial_exit == 0
            and initial.get("status") in {"updated", "degraded"}
            and (initial.get("freshness_report") or {}).get("status") in {"fresh", "degraded"},
        },
        "cases": case_results,
        "passed_all": all(item["passed"] for item in case_results.values()),
    }
    result["passed_all"] = bool(result["initial_core"]["passed"] and result["passed_all"])
    out = EVID / "artifacts" / "inject-all-gates-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
