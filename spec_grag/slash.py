"""Slash-command friendly wrapper for SPEC-grag JSON transport."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


COMMANDS = ("spec-core", "spec-inject", "spec-realign")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spec-grag-slash")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--task-prompt")
    parser.add_argument("--message", default="")
    parser.add_argument("--working-target")
    parser.add_argument("--explicit-file", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--accept")
    parser.add_argument("--reject")
    parser.add_argument("--revise")
    parser.add_argument("--revision-instruction")
    parser.add_argument("--apply")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--print-request", action="store_true")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args, prompt = parser.parse_known_args(argv)
    if any(part.startswith("-") for part in prompt):
        parser.error(f"unrecognized arguments: {' '.join(prompt)}")
    args.prompt = prompt
    operation_count = sum(
        value is not None
        for value in (args.accept, args.reject, args.revise, args.apply)
    )
    if operation_count > 1:
        parser.error("only one of --accept, --reject, --revise, or --apply may be set")
    if args.revise and not args.revision_instruction and not args.prompt:
        parser.error("--revise requires --revision-instruction or trailing instruction text")
    if args.command == "spec-realign" and not _task_text(args):
        parser.error("spec-realign requires a task prompt")
    return args


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    task_text = _task_text(args)
    revision_instruction = args.revision_instruction
    if args.revise and revision_instruction is None:
        revision_instruction = " ".join(args.prompt).strip()

    options: dict[str, Any] = {
        "output_format": "json",
        "all": bool(args.all),
    }
    for key in ("accept", "reject", "revise", "apply"):
        value = getattr(args, key)
        if value is not None:
            options[key] = value
    if revision_instruction:
        options["revision_instruction"] = revision_instruction

    current_message = args.message or task_text or ""
    return {
        "command": args.command,
        "project_root": str(Path(args.project_root).expanduser().resolve()),
        "task_prompt": task_text,
        "conversation_context": {
            "current_user_message": current_message,
            "recent_messages": [],
            "working_target": args.working_target,
            "explicit_files": args.explicit_file,
        },
        "agentic_search_candidates": [],
        "agent_capabilities": {
            "can_read_source": True,
            "can_answer": args.command == "spec-realign",
        },
        "options": options,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_payload(args)
    request_json = json.dumps(payload, ensure_ascii=False)
    if args.print_request:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    command = [sys.executable, "-m", "spec_grag.cli"]
    if args.pretty:
        command.append("--pretty")
    completed = subprocess.run(
        command,
        input=request_json,
        text=True,
        check=False,
    )
    return completed.returncode


def _task_text(args: argparse.Namespace) -> str | None:
    if args.task_prompt:
        return args.task_prompt
    if args.command == "spec-core" and args.revise:
        return None
    prompt = " ".join(args.prompt).strip()
    return prompt or None


if __name__ == "__main__":
    raise SystemExit(main())
