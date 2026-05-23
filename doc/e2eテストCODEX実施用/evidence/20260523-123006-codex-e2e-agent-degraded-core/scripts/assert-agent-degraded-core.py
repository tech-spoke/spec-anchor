#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-123006-codex-e2e-agent-degraded-core"
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


def ran_spec_core_no_flags(commands: list[str], trace: str) -> bool:
    if commands:
        return any(
            "spec-anchor core" in command
            and "--all" not in command
            and "--rebuild" not in command
            for command in commands
        )
    return "spec-anchor core" in trace


def degraded_contract(text: str, trace: str, commands: list[str]) -> dict[str, object]:
    return {
        "ran_spec_core_no_flags": ran_spec_core_no_flags(commands, trace),
        "reports_degraded_status": "degraded" in text.lower(),
        "reports_failed_section": has_any(
            text,
            ["docs/spec/flow.md#0003-broken-metadata-section", "broken-metadata-section"],
        ),
        "reports_warning": has_any(
            text,
            ["warning", "warnings", "警告", "LLM generation failed", "生成に失敗"],
        ),
        "reports_required_artifacts_available": has_any(
            text,
            ["必須 artifact は揃", "required artifacts", "継続可能", "can continue"],
        ),
        "reports_inject_realign_continue": has_any(
            text,
            ["/spec-inject", "/spec-realign", "spec-inject", "spec-realign"],
        ),
        "reports_retry_action": has_any(text, ["/spec-core --all", "spec-anchor core --all"]),
        "no_setup_autorun": not ran_setup_command(commands, trace),
    }


claude_trace_path = EVID / "stdout" / "claude-spec-core-degraded.stdout"
codex_trace_path = EVID / "stdout" / "codex-spec-core-degraded.stdout.jsonl"
claude_trace = read(claude_trace_path)
codex_trace = read(codex_trace_path)
claude_text = extract_claude_final(claude_trace_path)
codex_text = read(EVID / "artifacts" / "codex-spec-core-degraded.last-message.txt")

(EVID / "artifacts" / "claude-spec-core-degraded.final.txt").write_text(
    claude_text,
    encoding="utf-8",
)

checks = {
    "run_id": RUN_ID,
    "exitcodes": {
        "claude_degraded": exitcode("claude-spec-core-degraded.exitcode"),
        "codex_degraded": exitcode("codex-spec-core-degraded.exitcode"),
    },
    "claude_degraded": degraded_contract(
        claude_text,
        claude_trace,
        command_execution_commands(claude_trace_path),
    ),
    "codex_degraded": degraded_contract(
        codex_text,
        codex_trace,
        command_execution_commands(codex_trace_path),
    ),
}
checks["passed_claude_degraded_agent_layer"] = (
    checks["exitcodes"]["claude_degraded"] == 0
    and all(checks["claude_degraded"].values())
)
checks["passed_codex_degraded_agent_layer"] = (
    checks["exitcodes"]["codex_degraded"] == 0
    and all(checks["codex_degraded"].values())
)
checks["passed_all"] = (
    checks["passed_claude_degraded_agent_layer"]
    and checks["passed_codex_degraded_agent_layer"]
)

(EVID / "artifacts/agent-degraded-core-assertions.json").write_text(
    json.dumps(checks, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(checks, ensure_ascii=False, indent=2))
raise SystemExit(0 if checks["passed_all"] else 1)
