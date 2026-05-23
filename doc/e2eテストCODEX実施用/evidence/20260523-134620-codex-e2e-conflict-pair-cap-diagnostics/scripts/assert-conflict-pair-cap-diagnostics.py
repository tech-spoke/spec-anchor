#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-134620-codex-e2e-conflict-pair-cap-diagnostics"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_stdout() -> dict[str, Any]:
    return read_json(EVID / "stdout/core-rebuild.stdout")


def read_exit() -> int:
    return int((EVID / "stdout/core-rebuild.exitcode").read_text(encoding="utf-8").strip())


def provider_invocations() -> list[dict[str, Any]]:
    path = EVID / "artifacts/provider-invocations.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def walk_json(value: Any) -> list[Any]:
    found = [value]
    if isinstance(value, dict):
        for child in value.values():
            found.extend(walk_json(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(walk_json(child))
    return found


def has_cap_skip_diagnostic(payload: dict[str, Any]) -> bool:
    for item in walk_json(payload.get("diagnostics")):
        if not isinstance(item, dict):
            continue
        joined = json.dumps(item, ensure_ascii=False, sort_keys=True).lower()
        if "conflict_pair_max_per_section" in joined and (
            "skip" in joined or "dropped" in joined or "filtered" in joined
        ):
            return True
    return False


def main() -> int:
    payload = read_stdout()
    invocations = provider_invocations()
    conflict_requests = [item for item in invocations if item.get("stage") == "conflict_review"]
    observed_pairs = [
        ((item.get("request") or {}).get("pair") or {})
        for item in conflict_requests
    ]
    checks = {
        "core_exit_zero": read_exit() == 0,
        "core_completed": payload.get("status") in {"updated", "degraded"},
        "limit_was_one": "conflict_pair_max_per_section = 1"
        in (EVID / "artifacts/config.toml").read_text(encoding="utf-8"),
        "conflict_review_was_bounded": 1 <= len(conflict_requests) < 10,
        "core_result_has_cap_skip_diagnostic": has_cap_skip_diagnostic(payload),
    }
    result = {
        "run_id": RUN_ID,
        "checks": checks,
        "conflict_review_call_count": len(conflict_requests),
        "observed_pairs": observed_pairs,
        "diagnostics_keys": sorted((payload.get("diagnostics") or {}).keys()),
        "passed_all": all(checks.values()),
    }
    out = EVID / "artifacts/conflict-pair-cap-diagnostics-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
