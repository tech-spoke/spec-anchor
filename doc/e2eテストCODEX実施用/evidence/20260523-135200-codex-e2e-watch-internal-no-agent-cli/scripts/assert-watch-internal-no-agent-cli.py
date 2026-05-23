#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-135200-codex-e2e-watch-internal-no-agent-cli"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID


def read_json(name: str) -> dict[str, Any]:
    return json.loads((EVID / "stdout" / f"{name}.stdout").read_text(encoding="utf-8"))


def read_exit(name: str) -> int:
    return int((EVID / "stdout" / f"{name}.exitcode").read_text(encoding="utf-8").strip())


def provider_invocations() -> list[dict[str, Any]]:
    path = EVID / "artifacts/provider-invocations.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    env_text = (EVID / "artifacts/environment.txt").read_text(encoding="utf-8")
    initial = read_json("initial-core-rebuild")
    watch = read_json("watch-once")
    cycles = watch.get("cycles") or []
    first_cycle = cycles[0] if cycles else {}
    core_result = first_cycle.get("core_result") or watch.get("core_result") or {}
    last_lock = watch.get("last_lock") or first_cycle.get("last_lock") or {}
    stages = [item.get("stage") for item in provider_invocations()]
    checks = {
        "agent_cli_absent_from_path": "codex_path=\n" in env_text and "claude_path=\n" in env_text,
        "initial_core_exit_zero": read_exit("initial-core-rebuild") == 0
        and initial.get("status") in {"updated", "degraded"},
        "watch_exit_zero": read_exit("watch-once") == 0,
        "watch_ran_core_internally": watch.get("ran_core") is True and bool(core_result),
        "watch_lock_owner_is_watcher": last_lock.get("owner") == "watcher",
        "watch_core_updated_added_section": any(
            str(item.get("source_section_id") or item.get("section_id") or "").endswith(
                "#0003-watch-added-policy"
            )
            for item in (core_result.get("updated_sections") or [])
        ),
        "provider_used_project_script_not_agent_cli": (
            "section_metadata" in stages
            and "chapter_key_anchor" in stages
            and "codex_path=\n" in env_text
            and "claude_path=\n" in env_text
        ),
    }
    result = {
        "run_id": RUN_ID,
        "checks": checks,
        "watch_summary": {
            "status": watch.get("status"),
            "ran_core": watch.get("ran_core"),
            "last_lock": last_lock,
            "core_result_status": core_result.get("status"),
            "updated_sections": core_result.get("updated_sections"),
            "retrieval_index_status": core_result.get("retrieval_index_status"),
            "related_sections_status": core_result.get("related_sections_status"),
        },
        "provider_stages": stages,
        "passed_all": all(checks.values()),
    }
    out = EVID / "artifacts/watch-internal-no-agent-cli-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
