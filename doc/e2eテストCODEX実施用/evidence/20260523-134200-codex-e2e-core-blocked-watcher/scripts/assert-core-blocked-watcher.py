#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-134200-codex-e2e-core-blocked-watcher"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID


def read_json(name: str) -> dict[str, Any]:
    return json.loads((EVID / "stdout" / f"{name}.stdout").read_text(encoding="utf-8"))


def read_exit(name: str) -> int:
    return int((EVID / "stdout" / f"{name}.exitcode").read_text(encoding="utf-8").strip())


def main() -> int:
    payload = read_json("core-while-watcher-running")
    freshness = payload.get("freshness_report") or {}
    diagnostics = payload.get("diagnostics") or {}
    checks = {
        "exit_zero": read_exit("core-while-watcher-running") == 0,
        "status_blocked": payload.get("status") == "blocked" and payload.get("blocked") is True,
        "retrieval_index_status_blocked": payload.get("retrieval_index_status") == "blocked",
        "related_sections_status_blocked": payload.get("related_sections_status") == "blocked",
        "freshness_watcher_running": (
            freshness.get("status") == "blocked"
            and freshness.get("blocking_reasons") == ["watcher_running"]
        ),
        "no_downstream_updates": (
            payload.get("updated_sources") == []
            and payload.get("updated_sections") == []
            and payload.get("regenerated_chapter_anchors") == []
        ),
        "diagnostics_identify_watcher_state": (
            diagnostics.get("blocked_by") == "watcher_running"
            and str(diagnostics.get("watcher_state_file") or "").endswith(
                ".spec-anchor/state/watch_state.json"
            )
            and str(diagnostics.get("lock_file") or "").endswith(
                ".spec-anchor/state/core_update.lock.json"
            )
        ),
    }
    result = {
        "run_id": RUN_ID,
        "checks": checks,
        "core_summary": {
            "status": payload.get("status"),
            "retrieval_index_status": payload.get("retrieval_index_status"),
            "related_sections_status": payload.get("related_sections_status"),
            "freshness_report": freshness,
            "diagnostics": diagnostics,
        },
        "passed_all": all(checks.values()),
    }
    out = EVID / "artifacts" / "core-blocked-watcher-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
