#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-125141-codex-e2e-dirty-pending-priority"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID


def read_json(name: str) -> dict[str, Any]:
    text = (EVID / "stdout" / f"{name}.stdout").read_text(encoding="utf-8")
    return json.loads(text)


def read_exit(name: str) -> int:
    return int((EVID / "stdout" / f"{name}.exitcode").read_text(encoding="utf-8").strip())


def reasons(payload: dict[str, Any]) -> list[str]:
    return list(payload.get("blocking_reasons") or [])


def recommended(payload: dict[str, Any]) -> str:
    return str(payload.get("recommended_next_action") or "")


def has_pending_item(payload: dict[str, Any]) -> bool:
    items = payload.get("pending_conflict_items") or []
    return any(item.get("conflict_id") == "codex-e2e-dirty-pending-priority" for item in items)


def main() -> int:
    initial_core = read_json("initial-core-rebuild")
    pending_core = read_json("core-with-pending-conflict")
    inject_pending = read_json("inject-pending-only")
    inject_dirty = read_json("inject-dirty-and-pending")
    realign_dirty = read_json("realign-dirty-and-pending")
    core_after_dirty = read_json("core-after-dirty")
    inject_after_core = read_json("inject-after-core-pending-only")
    realign_after_core = read_json("realign-after-core-pending-only")

    exitcodes = {
        "initial_core_rebuild": read_exit("initial-core-rebuild"),
        "core_with_pending_conflict": read_exit("core-with-pending-conflict"),
        "inject_pending_only": read_exit("inject-pending-only"),
        "inject_dirty_and_pending": read_exit("inject-dirty-and-pending"),
        "realign_dirty_and_pending": read_exit("realign-dirty-and-pending"),
        "core_after_dirty": read_exit("core-after-dirty"),
        "inject_after_core_pending_only": read_exit("inject-after-core-pending-only"),
        "realign_after_core_pending_only": read_exit("realign-after-core-pending-only"),
    }

    pending_core_freshness = pending_core.get("freshness_report") or {}
    core_after_dirty_freshness = core_after_dirty.get("freshness_report") or {}

    checks = {
        "initial_core_success": (
            exitcodes["initial_core_rebuild"] == 0
            and initial_core.get("status") in {"updated", "degraded"}
            and (initial_core.get("freshness_report") or {}).get("status") in {"fresh", "degraded"}
        ),
        "pending_conflict_loaded": (
            exitcodes["core_with_pending_conflict"] == 0
            and pending_core_freshness.get("status") == "blocked"
            and reasons(pending_core_freshness) == ["pending_conflict"]
            and int(pending_core_freshness.get("pending_conflict_count") or 0) == 1
        ),
        "pending_only_gate_has_items": (
            exitcodes["inject_pending_only"] == 0
            and inject_pending.get("status") == "blocked"
            and reasons(inject_pending) == ["pending_conflict"]
            and has_pending_item(inject_pending)
            and "resolve pending Conflict Review Items" in recommended(inject_pending)
        ),
        "dirty_priority_inject": (
            exitcodes["inject_dirty_and_pending"] == 0
            and inject_dirty.get("status") == "blocked"
            and reasons(inject_dirty)[:2] == ["dirty_or_stale_source", "pending_conflict"]
            and inject_dirty.get("should_stop") is True
            and "run /spec-core before /spec-inject" in recommended(inject_dirty)
            and "pending_conflict_items" not in inject_dirty
        ),
        "dirty_priority_realign": (
            exitcodes["realign_dirty_and_pending"] == 0
            and realign_dirty.get("status") == "blocked"
            and reasons(realign_dirty)[:2] == ["dirty_or_stale_source", "pending_conflict"]
            and realign_dirty.get("should_stop") is True
            and "run /spec-core before /spec-realign" in recommended(realign_dirty)
            and "pending_conflict_items" not in realign_dirty
        ),
        "core_update_keeps_pending": (
            exitcodes["core_after_dirty"] == 0
            and core_after_dirty_freshness.get("status") == "blocked"
            and reasons(core_after_dirty_freshness) == ["pending_conflict"]
            and int(core_after_dirty.get("pending_conflict_count") or 0) == 1
            and int(core_after_dirty_freshness.get("pending_conflict_count") or 0) == 1
        ),
        "after_core_inject_pending_only": (
            exitcodes["inject_after_core_pending_only"] == 0
            and inject_after_core.get("status") == "blocked"
            and reasons(inject_after_core) == ["pending_conflict"]
            and has_pending_item(inject_after_core)
            and "resolve pending Conflict Review Items" in recommended(inject_after_core)
        ),
        "after_core_realign_pending_only": (
            exitcodes["realign_after_core_pending_only"] == 0
            and realign_after_core.get("status") == "blocked"
            and reasons(realign_after_core) == ["pending_conflict"]
            and has_pending_item(realign_after_core)
            and "resolve pending Conflict Review Items" in recommended(realign_after_core)
        ),
    }

    result = {
        "run_id": RUN_ID,
        "exitcodes": exitcodes,
        "checks": checks,
        "passed_all": all(checks.values()),
    }
    out = EVID / "artifacts" / "dirty-pending-priority-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
