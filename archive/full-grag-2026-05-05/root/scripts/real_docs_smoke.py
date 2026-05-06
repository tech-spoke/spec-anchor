"""Run an end-to-end smoke against the repository's Japanese test documents."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_docs = repo / "テスト用ドキュメント"
    if not source_docs.exists():
        print("テスト用ドキュメント is missing", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="spec-grag-real-docs-") as tmp:
        root = Path(tmp)
        shutil.copytree(source_docs, root / "docs/spec")
        core_dir = root / "docs/core"
        core_dir.mkdir(parents=True)
        (core_dir / "purpose.md").write_text("# Purpose\n仕様の整合性を保つ。\n", encoding="utf-8")
        (core_dir / "concept.md").write_text("# Concept\n管理画面仕様の主要概念を扱う。\n", encoding="utf-8")
        config_dir = root / ".spec-grag"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            """
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[graph]
storage = ".spec-grag/graph/"
""".strip(),
            encoding="utf-8",
        )
        for payload in (
            request_payload(root, "spec-core", all_sources=True),
            request_payload(root, "spec-inject"),
            request_payload(root, "spec-realign", task_prompt="管理画面仕様を安全に見直す"),
        ):
            result = subprocess.run(
                [sys.executable, "-m", "spec_grag.cli"],
                input=json.dumps(payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                print(result.stdout)
                print(result.stderr, file=sys.stderr)
                return result.returncode
            envelope = json.loads(result.stdout)
            print(json.dumps({"command": payload["command"], "status": envelope["status"]}, ensure_ascii=False))
    return 0


def request_payload(
    root: Path,
    command: str,
    *,
    all_sources: bool = False,
    task_prompt: str | None = None,
) -> dict:
    return {
        "command": command,
        "project_root": str(root),
        "task_prompt": task_prompt,
        "conversation_context": {
            "current_user_message": task_prompt or "管理画面仕様を見直す",
            "recent_messages": [],
            "working_target": None,
            "explicit_files": [],
        },
        "agent_capabilities": {"can_read_source": True, "can_answer": command == "spec-realign"},
        "options": {"output_format": "json", "all": all_sources},
    }


if __name__ == "__main__":
    raise SystemExit(main())
