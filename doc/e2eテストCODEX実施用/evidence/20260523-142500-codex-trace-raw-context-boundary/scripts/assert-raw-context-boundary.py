#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-142500-codex-trace-raw-context-boundary"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID
SOURCE_RUN = REPO / "doc/e2eテストCODEX実施用/evidence/20260523-101202-codex-e2e-inject-output"
TRACE = SOURCE_RUN / "stdout/codex-skill-inject-8-5.stdout.jsonl"
FINAL = SOURCE_RUN / "artifacts/codex-skill-inject-8-5.last-message.txt"


def jsonl_items(path: Path) -> list[dict[str, Any]]:
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


def command_items() -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for event in jsonl_items(TRACE):
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            commands.append(item)
    return commands


def commands_seen() -> list[str]:
    return [str(item.get("command") or "") for item in command_items()]


def command_index(needle: str) -> int:
    for index, command in enumerate(commands_seen()):
        if needle in command:
            return index
    return -1


def main() -> int:
    commands = commands_seen()
    source_reads = [
        command for command in commands
        if "docs/spec/" in command and ("sed -n" in command or "cat " in command)
    ]
    concept_reads = [
        command for command in commands
        if "docs/core/concept.md" in command and ("sed -n" in command or "cat " in command)
    ]
    broad_read_patterns = [
        "cat docs/spec",
        "cat docs/core/concept.md",
        "cat .spec-anchor/context/chapter_anchors.json",
        "sed -n '1,$p'",
        "sed -n \"1,$p\"",
        "xargs cat",
    ]
    final_message = FINAL.read_text(encoding="utf-8")
    checks = {
        "source_trace_exists": TRACE.is_file(),
        "inject_search_before_source_reads": command_index("spec-anchor inject-search") >= 0
        and all(command_index("spec-anchor inject-search") < commands.index(command) for command in source_reads),
        "inject_section_before_source_reads": command_index("spec-anchor inject-section") >= 0
        and all(command_index("spec-anchor inject-section") < commands.index(command) for command in source_reads),
        "inject_purpose_before_concept_read": command_index("spec-anchor inject-purpose") >= 0
        and bool(concept_reads)
        and command_index("spec-anchor inject-purpose") < commands.index(concept_reads[0]),
        "source_reads_are_selected_files": set(source_reads) == {
            "/bin/bash -lc \"sed -n '1,120p' docs/spec/login.md\"",
            "/bin/bash -lc \"sed -n '1,120p' docs/spec/audit.md\"",
        },
        "no_chapter_anchor_body_read": not any("chapter_anchors.json" in command and ("sed -n" in command or "cat " in command) for command in commands),
        "no_broad_raw_text_dump_commands": not any(pattern in command for command in commands for pattern in broad_read_patterns),
        "final_has_constraints_not_raw_json": "evidence_origin" in final_message and not final_message.lstrip().startswith("{"),
    }
    result = {
        "run_id": RUN_ID,
        "source_run_id": "20260523-101202-codex-e2e-inject-output",
        "checks": checks,
        "source_reads": source_reads,
        "concept_reads": concept_reads,
        "commands_seen": commands,
        "passed_all": all(checks.values()),
    }
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "artifacts").mkdir(parents=True, exist_ok=True)
    out = EVID / "artifacts/raw-context-boundary-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
