#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-142000-codex-e2e-conflict-review-item-trace"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID
ELIGIBLE_ID = "conflict-payment-timeout-human-resolution"
STALE_ID = "conflict-payment-timeout-stale-resolution"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def exit_code(name: str) -> int:
    return int(read_text(EVID / f"stdout/{name}.exitcode").strip())


def jsonl_items() -> list[dict[str, Any]]:
    path = EVID / "stdout/codex-conflict-trace.stdout.jsonl"
    items: list[dict[str, Any]] = []
    if not path.is_file():
        return items
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


def command_items() -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for event in jsonl_items():
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            commands.append(item)
    return commands


def commands_seen() -> list[str]:
    return [str(item.get("command") or "") for item in command_items()]


def completed_command_outputs(command_substring: str) -> list[str]:
    outputs: list[str] = []
    for event in jsonl_items():
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        command = str(item.get("command") or "")
        if command_substring in command:
            outputs.append(str(item.get("aggregated_output") or ""))
    return outputs


def extract_json_objects(texts: list[str]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for text in texts:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def final_uses_eligible_conflict(final_message: str) -> bool:
    lowered = final_message.lower()
    return (
        "evidence_origin" in lowered
        and "conflict review item" in lowered
        and ELIGIBLE_ID in final_message
    )


def final_cites_stale_as_evidence(final_message: str) -> bool:
    if STALE_ID not in final_message:
        return False
    stale_index = final_message.find(STALE_ID)
    window = final_message[max(0, stale_index - 120) : stale_index + 160].lower()
    return "evidence_ref" in window or "evidence_origin" in window


def main() -> int:
    preflight = read_json(EVID / "stdout/preflight-inject-conflicts.stdout")
    final_message = read_text(EVID / "artifacts/codex-conflict-trace.last-message.txt")
    inject_outputs = extract_json_objects(completed_command_outputs("spec-anchor inject-conflicts"))
    returned_ids = [
        item.get("conflict_id")
        for payload in inject_outputs
        for item in payload.get("resolved_conflict_review_items", [])
        if isinstance(item, dict)
    ]
    preflight_ids = [
        item.get("conflict_id")
        for item in preflight.get("resolved_conflict_review_items", [])
        if isinstance(item, dict)
    ]
    eligible_items = [
        item for item in preflight.get("resolved_conflict_review_items", [])
        if isinstance(item, dict) and item.get("conflict_id") == ELIGIBLE_ID
    ]
    eligible = eligible_items[0] if eligible_items else {}
    referenced_refs = ((eligible.get("resolution") or {}).get("referenced_source_refs") or [])
    checks = {
        "preflight_exit_zero": exit_code("preflight-inject-conflicts") == 0,
        "preflight_returns_eligible_only": preflight_ids == [ELIGIBLE_ID],
        "preflight_item_is_resolved_non_stale": eligible.get("status") == "resolved"
        and eligible.get("stale_resolution") is False,
        "preflight_item_has_valid_scope_and_referenced_refs": eligible.get("valid_scope") == "global"
        and "docs/spec/payment.md#0002-default-timeout" in referenced_refs
        and "docs/spec/payment.md#0003-retry-policy" in referenced_refs,
        "codex_exit_zero": exit_code("codex-conflict-trace") == 0,
        "codex_called_inject_conflicts": any("spec-anchor inject-conflicts" in command for command in commands_seen()),
        "trace_returned_eligible_conflict": ELIGIBLE_ID in returned_ids,
        "trace_did_not_return_stale_conflict": STALE_ID not in returned_ids,
        "final_uses_conflict_review_item_evidence": final_uses_eligible_conflict(final_message),
        "final_does_not_cite_stale_conflict_as_evidence": not final_cites_stale_as_evidence(final_message),
    }
    result = {
        "run_id": RUN_ID,
        "checks": checks,
        "commands_seen": commands_seen(),
        "preflight_resolved_ids": preflight_ids,
        "trace_resolved_ids": returned_ids,
        "final_excerpt": final_message[:3000],
        "passed_all": all(checks.values()),
    }
    out = EVID / "artifacts/conflict-review-item-trace-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
