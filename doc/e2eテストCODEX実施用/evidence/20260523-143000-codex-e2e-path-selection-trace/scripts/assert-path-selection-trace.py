#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-143000-codex-e2e-path-selection-trace"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID
CASES = ("api_identifier", "abstract_policy", "purpose_direct", "past_decision")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def exit_code(case_id: str) -> int:
    return int(read_text(EVID / f"stdout/{case_id}.exitcode").strip())


def jsonl_items(case_id: str) -> list[dict[str, Any]]:
    path = EVID / f"stdout/{case_id}.stdout.jsonl"
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def commands_seen(case_id: str) -> list[str]:
    commands: list[str] = []
    for event in jsonl_items(case_id):
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            commands.append(str(item.get("command") or ""))
    return commands


def has(case_id: str, command: str) -> bool:
    return any(command in seen for seen in commands_seen(case_id))


def final_has_five_sections(case_id: str) -> bool:
    text = read_text(EVID / f"artifacts/{case_id}.last-message.txt")
    return all(
        label in text
        for label in (
            "今回守る制約",
            "今回見るべき対象",
            "関連先として確認したもの",
            "採用しなかったもの",
            "不確実性 / 人間確認",
        )
    )


def main() -> int:
    checks = {
        "api_identifier_exit_zero": exit_code("api_identifier") == 0,
        "api_identifier_uses_path_1": has("api_identifier", "spec-anchor inject-search")
        and has("api_identifier", "spec-anchor inject-section"),
        "api_identifier_uses_supplement_3_4": has("api_identifier", "spec-anchor inject-purpose")
        and has("api_identifier", "spec-anchor inject-conflicts"),
        "api_identifier_five_sections": final_has_five_sections("api_identifier"),
        "abstract_policy_exit_zero": exit_code("abstract_policy") == 0,
        "abstract_policy_uses_path_2": has("abstract_policy", "spec-anchor inject-chapters"),
        "abstract_policy_uses_supplement_1_3_4": has("abstract_policy", "spec-anchor inject-search")
        and has("abstract_policy", "spec-anchor inject-section")
        and has("abstract_policy", "spec-anchor inject-purpose")
        and has("abstract_policy", "spec-anchor inject-conflicts"),
        "abstract_policy_five_sections": final_has_five_sections("abstract_policy"),
        "purpose_direct_exit_zero": exit_code("purpose_direct") == 0,
        "purpose_direct_uses_path_3": has("purpose_direct", "spec-anchor inject-purpose"),
        "purpose_direct_uses_supplement_1_2": has("purpose_direct", "spec-anchor inject-search")
        and has("purpose_direct", "spec-anchor inject-section")
        and has("purpose_direct", "spec-anchor inject-chapters"),
        "purpose_direct_five_sections": final_has_five_sections("purpose_direct"),
        "past_decision_exit_zero": exit_code("past_decision") == 0,
        "past_decision_uses_path_4": has("past_decision", "spec-anchor inject-conflicts"),
        "past_decision_uses_supplement_1_3": has("past_decision", "spec-anchor inject-search")
        and has("past_decision", "spec-anchor inject-section")
        and has("past_decision", "spec-anchor inject-purpose"),
        "past_decision_five_sections": final_has_five_sections("past_decision"),
    }
    result = {
        "run_id": RUN_ID,
        "checks": checks,
        "commands_by_case": {case_id: commands_seen(case_id) for case_id in CASES},
        "passed_all": all(checks.values()),
    }
    out = EVID / "artifacts/path-selection-trace-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
