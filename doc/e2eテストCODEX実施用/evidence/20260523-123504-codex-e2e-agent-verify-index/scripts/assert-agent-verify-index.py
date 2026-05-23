#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-123504-codex-e2e-agent-verify-index"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def exitcode(name: str) -> int:
    return int(read(EVID / "stdout" / name).strip())


def extract_claude_final(path: Path) -> str:
    parts: list[str] = []
    last_result = ""
    for line in read(path).splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "result" and isinstance(obj.get("result"), str):
            last_result = obj["result"]
        event = obj.get("event")
        if not isinstance(event, dict):
            continue
        delta = event.get("delta")
        if isinstance(delta, dict) and isinstance(delta.get("text"), str):
            parts.append(delta["text"])
    return last_result or "".join(parts)


def has_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def command_execution_commands(path: Path) -> list[str]:
    commands: list[str] = []
    for line in read(path).splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = obj.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            command = item.get("command")
            if isinstance(command, str):
                commands.append(command)
        event = obj.get("event")
        if isinstance(event, dict):
            tool_input = event.get("input")
            if isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str):
                commands.append(tool_input["command"])
    return commands


def ran_setup_command(commands: list[str], trace: str) -> bool:
    if commands:
        return any("spec-anchor-setup-project" in command for command in commands)
    return "spec-anchor-setup-project --target" in trace


def ran_verify_command(commands: list[str], trace: str) -> bool:
    if commands:
        return any("spec-anchor core --verify-index" in command for command in commands)
    return "spec-anchor core --verify-index" in trace


def verify_contract(text: str, trace: str, commands: list[str]) -> dict[str, object]:
    return {
        "ran_spec_core_verify": ran_verify_command(commands, trace),
        "reports_failed_status": "failed" in text.lower() or "失敗" in text,
        "reports_retrieval_index_failed": has_any(
            text,
            ["retrieval_index_status", "Source Retrieval Index", "retrieval index", "Source Retrieval"],
        ),
        "reports_verify_inconsistency": has_any(
            text,
            ["verification detected inconsistency", "verify", "検証", "不整合", "inconsistency"],
        ),
        "reports_rebuild_action": has_any(text, ["/spec-core --rebuild", "spec-anchor core --rebuild"]),
        "reports_collection_not_dropped": has_any(
            text,
            ["drop", "dropped", "削除されてい", "保持", "維持", "not dropped"],
        ),
        "no_setup_autorun": not ran_setup_command(commands, trace),
    }


claude_trace_path = EVID / "stdout" / "claude-spec-core-verify.stdout"
codex_trace_path = EVID / "stdout" / "codex-spec-core-verify.stdout.jsonl"
claude_trace = read(claude_trace_path)
codex_trace = read(codex_trace_path)
claude_text = extract_claude_final(claude_trace_path)
codex_text = read(EVID / "artifacts" / "codex-spec-core-verify.last-message.txt")

(EVID / "artifacts" / "claude-spec-core-verify.final.txt").write_text(
    claude_text,
    encoding="utf-8",
)

checks = {
    "run_id": RUN_ID,
    "exitcodes": {
        "initial_core_rebuild": exitcode("initial-core-rebuild.exitcode"),
        "claude_verify": exitcode("claude-spec-core-verify.exitcode"),
        "codex_verify": exitcode("codex-spec-core-verify.exitcode"),
    },
    "deleted_point": json.loads(read(EVID / "artifacts/deleted-point.json")),
    "claude_verify": verify_contract(
        claude_text,
        claude_trace,
        command_execution_commands(claude_trace_path),
    ),
    "codex_verify": verify_contract(
        codex_text,
        codex_trace,
        command_execution_commands(codex_trace_path),
    ),
}
checks["passed_claude_verify_agent_layer"] = (
    checks["exitcodes"]["initial_core_rebuild"] == 0
    and checks["exitcodes"]["claude_verify"] == 0
    and all(checks["claude_verify"].values())
)
checks["passed_codex_verify_agent_layer"] = (
    checks["exitcodes"]["initial_core_rebuild"] == 0
    and checks["exitcodes"]["codex_verify"] == 0
    and all(checks["codex_verify"].values())
)
checks["passed_all"] = (
    checks["passed_claude_verify_agent_layer"]
    and checks["passed_codex_verify_agent_layer"]
)

(EVID / "artifacts/agent-verify-index-assertions.json").write_text(
    json.dumps(checks, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(checks, ensure_ascii=False, indent=2))
raise SystemExit(0 if checks["passed_all"] else 1)
