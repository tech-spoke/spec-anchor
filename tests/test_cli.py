from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from spec_grag.protocol import ResultEnvelope, ResultStatus, ResultType


def write_config(project_root: Path) -> None:
    config_dir = project_root / ".spec-grag"
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


def request_json(project_root: Path, command: str = "spec-inject") -> str:
    payload = {
        "command": command,
        "project_root": str(project_root),
        "task_prompt": "認証仕様を見直す" if command == "spec-realign" else None,
        "conversation_context": {
            "current_user_message": "認証仕様を見直したい",
            "recent_messages": [],
            "working_target": "docs/spec/auth.md",
            "explicit_files": ["docs/spec/auth.md"],
        },
        "agent_capabilities": {
            "can_read_source": True,
            "can_answer": True,
        },
        "options": {
            "output_format": "json",
        },
    }
    return json.dumps(payload)


def run_cli(stdin_json: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=stdin_json,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_stdin_stdout_roundtrip_for_spec_inject(tmp_path: Path) -> None:
    write_config(tmp_path)

    result = run_cli(request_json(tmp_path, "spec-inject"))

    assert result.returncode == 0
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.DEGRADED
    assert envelope.result_type == ResultType.INJECTION_CONTEXT
    assert envelope.execution.context_ready is True


def test_cli_missing_config_returns_failed_error(tmp_path: Path) -> None:
    result = run_cli(request_json(tmp_path, "spec-core"))

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT


def test_cli_spec_core_all_uses_full_mode(tmp_path: Path) -> None:
    write_config(tmp_path)
    payload = json.loads(request_json(tmp_path, "spec-core"))
    payload["options"]["all"] = True

    result = run_cli(json.dumps(payload))

    assert result.returncode == 0
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.result_type == ResultType.CORE_RESULT
    assert envelope.payload.mode == "full"


def test_cli_spec_realign_requires_task_prompt(tmp_path: Path) -> None:
    write_config(tmp_path)
    payload = json.loads(request_json(tmp_path, "spec-realign"))
    payload["task_prompt"] = None

    result = run_cli(json.dumps(payload))

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT
