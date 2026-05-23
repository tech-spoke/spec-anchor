#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-104149-codex-e2e-agent-core-errors"
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
    return commands


def ran_setup_command(commands: list[str], trace: str) -> bool:
    if commands:
        return any("spec-anchor-setup-project" in command for command in commands)
    return "spec-anchor-setup-project --target" in trace


def chapter_contract(text: str, trace: str, commands: list[str]) -> dict[str, object]:
    return {
        "ran_spec_core_all": "spec-anchor core --all" in trace,
        "reports_failed_status": "failed" in text.lower() or "失敗" in text,
        "reports_chapter_warning": has_any(
            text,
            [
                "Chapter Anchors LLM generation failed",
                "Chapter Key Anchor",
                "chapter_anchors",
                "chapter_anchors.json",
            ],
        ),
        "reports_canonical_preserved": has_any(text, ["canonical", "前回値", "更新され", "not updated"]),
        "reports_retry_action": has_any(text, ["/spec-core --all", "spec-anchor core --all"]),
        "no_setup_autorun": not ran_setup_command(commands, trace),
    }


def qdrant_contract(text: str, trace: str, commands: list[str]) -> dict[str, object]:
    return {
        "ran_spec_core_rebuild": "spec-anchor core --rebuild" in trace,
        "reports_failed_status": "failed" in text.lower() or "失敗" in text,
        "reports_qdrant_failure": has_any(
            text,
            [
                "Related Sections retrieval backend failure",
                "Qdrant",
                "qdrant",
                "127.0.0.1:65531",
            ],
        ),
        "reports_recovery_action": has_any(text, ["/spec-core --rebuild", "spec-anchor core --rebuild"]),
        "no_setup_autorun": not ran_setup_command(commands, trace),
    }


claude_chapter_trace = read(EVID / "stdout" / "claude-spec-core-chapter-failure.stdout")
claude_qdrant_trace = read(EVID / "stdout" / "claude-spec-core-qdrant-failure.stdout")
codex_chapter_trace = read(EVID / "stdout" / "codex-spec-core-chapter-failure.stdout.jsonl")
codex_qdrant_trace = read(EVID / "stdout" / "codex-spec-core-qdrant-failure.stdout.jsonl")

claude_chapter_text = extract_claude_final(EVID / "stdout" / "claude-spec-core-chapter-failure.stdout")
claude_qdrant_text = extract_claude_final(EVID / "stdout" / "claude-spec-core-qdrant-failure.stdout")
codex_chapter_text = read(EVID / "artifacts" / "codex-spec-core-chapter-failure.last-message.txt")
codex_qdrant_text = read(EVID / "artifacts" / "codex-spec-core-qdrant-failure.last-message.txt")

(EVID / "artifacts" / "claude-spec-core-chapter-failure.final.txt").write_text(claude_chapter_text, encoding="utf-8")
(EVID / "artifacts" / "claude-spec-core-qdrant-failure.final.txt").write_text(claude_qdrant_text, encoding="utf-8")

checks = {
    "run_id": RUN_ID,
    "exitcodes": {
        "claude_chapter": exitcode("claude-spec-core-chapter-failure.exitcode"),
        "codex_chapter": exitcode("codex-spec-core-chapter-failure.exitcode"),
        "claude_qdrant": exitcode("claude-spec-core-qdrant-failure.exitcode"),
        "codex_qdrant": exitcode("codex-spec-core-qdrant-failure.exitcode"),
    },
    "claude_chapter": chapter_contract(
        claude_chapter_text,
        claude_chapter_trace,
        command_execution_commands(EVID / "stdout" / "claude-spec-core-chapter-failure.stdout"),
    ),
    "codex_chapter": chapter_contract(
        codex_chapter_text,
        codex_chapter_trace,
        command_execution_commands(EVID / "stdout" / "codex-spec-core-chapter-failure.stdout.jsonl"),
    ),
    "claude_qdrant": qdrant_contract(
        claude_qdrant_text,
        claude_qdrant_trace,
        command_execution_commands(EVID / "stdout" / "claude-spec-core-qdrant-failure.stdout"),
    ),
    "codex_qdrant": qdrant_contract(
        codex_qdrant_text,
        codex_qdrant_trace,
        command_execution_commands(EVID / "stdout" / "codex-spec-core-qdrant-failure.stdout.jsonl"),
    ),
}

checks["passed_chapter_agent_layer"] = (
    checks["exitcodes"]["claude_chapter"] == 0
    and checks["exitcodes"]["codex_chapter"] == 0
    and all(checks["claude_chapter"].values())
    and all(checks["codex_chapter"].values())
)
checks["passed_qdrant_agent_layer"] = (
    checks["exitcodes"]["claude_qdrant"] == 0
    and checks["exitcodes"]["codex_qdrant"] == 0
    and all(checks["claude_qdrant"].values())
    and all(checks["codex_qdrant"].values())
)
checks["passed_all"] = checks["passed_chapter_agent_layer"] and checks["passed_qdrant_agent_layer"]

out = EVID / "artifacts" / "agent-core-errors-assertions.json"
out.write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(checks, ensure_ascii=False, indent=2))
raise SystemExit(0 if checks["passed_all"] else 1)
