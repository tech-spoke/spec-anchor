#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path


REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-103156-codex-e2e-realign-output"
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
        if event.get("type") not in {"content_block_delta", "message_delta"}:
            continue
        delta = event.get("delta")
        if isinstance(delta, dict) and isinstance(delta.get("text"), str):
            parts.append(delta["text"])
    return last_result or "".join(parts)


def contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def no_raw_json_or_code(text: str) -> bool:
    if "```" in text:
        return False
    if re.search(r'^\s*\{\s*"', text, re.M):
        return False
    return True


def output_contract(text: str) -> dict[str, object]:
    sections = [
        "今回守る制約",
        "今回扱う修正候補または検討対象",
        "競合 / 不確実性 / 人間レビューが必要な点",
        "課題プロンプトへの回答または修正案",
    ]
    contract = {
        "has_four_sections": contains_all(text, sections),
        "has_mfa_constraint": "MFA_REQUIRED_ON_ADMIN_LOGIN" in text,
        "has_audit_constraint": "AUDIT_EVENT_REQUIRED" in text and "audit_log_stream" in text,
        "has_retention_conflict": "RETENTION_DAYS_FOR_AUTH_LOG" in text
        and "30" in text
        and ("人間" in text or "未確定" in text or "法務" in text),
        "no_raw_json_or_code_fence": no_raw_json_or_code(text),
        "does_not_silently_accept_30_days": not re.search(
            r"RETENTION_DAYS_FOR_AUTH_LOG[^\n。]*30\s*日[^\n。]*(固定|決定|確定)",
            text,
        )
        or "矛盾" in text
        or "人間" in text,
    }
    contract["passed_9_3_output_contract"] = all(contract.values())
    return contract


def command_trace(path: Path) -> dict[str, object]:
    text = read(path)
    return {
        "contains_inject_call": "spec-anchor inject-" in text,
        "contains_realign_call": "spec-anchor realign" in text,
        "contains_realign_answer_input": "--answer-json" in text or "--answer-file" in text or "--answer-text" in text,
    }


claude_text = extract_claude_final(EVID / "stdout" / "claude-spec-realign-9-3.stdout")
codex_text = read(EVID / "artifacts" / "codex-skill-realign-9-3.last-message.txt")

(EVID / "artifacts" / "claude-spec-realign-9-3.final.txt").write_text(claude_text, encoding="utf-8")

result = {
    "run_id": RUN_ID,
    "exitcodes": {
        "setup_project": exitcode("setup-project.exitcode"),
        "core_rebuild": exitcode("core-rebuild.exitcode"),
        "preflight_inject_search": exitcode("preflight-inject-search.exitcode"),
        "preflight_realign_answer": exitcode("preflight-realign-answer.exitcode"),
        "claude_spec_realign": exitcode("claude-spec-realign-9-3.exitcode"),
        "codex_skill_realign": exitcode("codex-skill-realign-9-3.exitcode"),
    },
    "claude": {
        **output_contract(claude_text),
        "trace": command_trace(EVID / "stdout" / "claude-spec-realign-9-3.stdout"),
    },
    "codex_skill": {
        **output_contract(codex_text),
        "trace": command_trace(EVID / "stdout" / "codex-skill-realign-9-3.stdout.jsonl"),
    },
}

result["passed_both_agent_outputs"] = (
    all(code == 0 for code in result["exitcodes"].values())
    and result["claude"]["passed_9_3_output_contract"]
    and result["codex_skill"]["passed_9_3_output_contract"]
    and all(result["claude"]["trace"].values())
    and all(result["codex_skill"]["trace"].values())
)

out = EVID / "artifacts" / "realign-output-9-3-assertions.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["passed_both_agent_outputs"] else 1)
