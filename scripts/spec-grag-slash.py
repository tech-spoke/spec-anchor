#!/usr/bin/env python3
"""Small slash-command wrapper for SPEC-grag JSON transport."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="spec-grag-slash")
    parser.add_argument("command", choices=["spec-core", "spec-inject", "spec-realign"])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--task-prompt")
    parser.add_argument("--message", default="")
    parser.add_argument("--working-target")
    parser.add_argument("--explicit-file", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--print-request", action="store_true")
    args = parser.parse_args()

    payload = {
        "command": args.command,
        "project_root": str(Path(args.project_root).resolve()),
        "task_prompt": args.task_prompt,
        "conversation_context": {
            "current_user_message": args.message or args.task_prompt or "",
            "recent_messages": [],
            "working_target": args.working_target,
            "explicit_files": args.explicit_file,
        },
        "agentic_search_candidates": [],
        "agent_capabilities": {
            "can_read_source": True,
            "can_answer": args.command == "spec-realign",
        },
        "options": {
            "output_format": "json",
            "all": args.all,
        },
    }
    request_json = json.dumps(payload, ensure_ascii=False)
    if args.print_request:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    completed = subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=request_json,
        text=True,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
