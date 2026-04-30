from __future__ import annotations

import json
import subprocess
from typing import Sequence

import pytest
from pydantic import BaseModel

from spec_grag.llm_adapters import (
    CLIAdapterError,
    ClaudeCLIAdapter,
    CodexCLIAdapter,
    extract_cli_text,
)


class StructuredAnswer(BaseModel):
    name: str


def test_codex_cli_adapter_complete_uses_runner_and_schema() -> None:
    calls: list[Sequence[str]] = []

    def runner(
        cmd: Sequence[str], stdin_text: str | None, timeout_sec: int
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        assert stdin_text is None
        assert timeout_sec == 30
        schema_index = list(cmd).index("--output-schema")
        assert list(cmd)[schema_index + 1].endswith(".json")
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=0,
            stdout=json.dumps({"result": '{"name": "auth"}'}),
            stderr="",
        )

    llm = CodexCLIAdapter(model="test-model", timeout_sec=30, runner=runner)
    response = llm.complete("extract", output_schema=StructuredAnswer)

    assert response.text == '{"name": "auth"}'
    assert calls
    assert list(calls[0])[:6] == [
        "codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--model",
        "test-model",
    ]
    assert "--sandbox" in calls[0]
    assert list(calls[0])[list(calls[0]).index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in calls[0]
    assert "--ignore-rules" in calls[0]
    assert "--json" in calls[0]


def test_codex_cli_adapter_stream_complete_yields_single_response() -> None:
    def runner(
        cmd: Sequence[str], stdin_text: str | None, timeout_sec: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout='{"result": "done"}', stderr=""
        )

    llm = CodexCLIAdapter(runner=runner)
    responses = list(llm.stream_complete("prompt"))

    assert len(responses) == 1
    assert responses[0].text == "done"
    assert responses[0].delta == "done"


def test_codex_cli_adapter_nonzero_exit_raises() -> None:
    def runner(
        cmd: Sequence[str], stdin_text: str | None, timeout_sec: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=2, stdout="", stderr="bad schema"
        )

    llm = CodexCLIAdapter(runner=runner)

    with pytest.raises(CLIAdapterError):
        llm.complete("prompt")


def test_codex_cli_adapter_validates_structured_output_locally() -> None:
    impossible_schema = {
        "type": "object",
        "properties": {"x": {"type": "string", "enum": []}},
        "required": ["x"],
        "additionalProperties": False,
    }

    def runner(
        cmd: Sequence[str], stdin_text: str | None, timeout_sec: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout='{"result": "{\\"x\\": \\"x\\"}"}', stderr=""
        )

    llm = CodexCLIAdapter(runner=runner)

    with pytest.raises(CLIAdapterError, match="violates schema"):
        llm.complete("prompt", output_schema=impossible_schema)


def test_claude_cli_adapter_complete_uses_runner_and_schema() -> None:
    calls: list[Sequence[str]] = []

    def runner(
        cmd: Sequence[str], stdin_text: str | None, timeout_sec: int
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        assert stdin_text is None
        assert timeout_sec == 45
        schema_index = list(cmd).index("--json-schema")
        assert json.loads(list(cmd)[schema_index + 1])["required"] == ["name"]
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=0,
            stdout=json.dumps({"structured_output": {"name": "auth"}}),
            stderr="",
        )

    llm = ClaudeCLIAdapter(model="sonnet", timeout_sec=45, runner=runner)
    response = llm.complete("extract", output_schema=StructuredAnswer)

    assert response.text == '{"name": "auth"}'
    assert calls
    assert list(calls[0])[:4] == ["claude", "--print", "--model", "sonnet"]
    assert "--no-session-persistence" in calls[0]
    assert "--disable-slash-commands" in calls[0]
    assert "--tools" in calls[0]
    assert list(calls[0])[list(calls[0]).index("--tools") + 1] == ""
    assert list(calls[0])[-1] == "extract"


def test_claude_cli_adapter_nonzero_exit_raises() -> None:
    def runner(
        cmd: Sequence[str], stdin_text: str | None, timeout_sec: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=1, stdout="", stderr="not logged in"
        )

    llm = ClaudeCLIAdapter(runner=runner)

    with pytest.raises(CLIAdapterError):
        llm.complete("prompt")


def test_claude_cli_adapter_validates_structured_output_locally() -> None:
    impossible_schema = {
        "type": "object",
        "properties": {"x": {"type": "string", "enum": []}},
        "required": ["x"],
        "additionalProperties": False,
    }

    def runner(
        cmd: Sequence[str], stdin_text: str | None, timeout_sec: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=0,
            stdout=json.dumps({"structured_output": {"x": "x"}}),
            stderr="",
        )

    llm = ClaudeCLIAdapter(runner=runner)

    with pytest.raises(CLIAdapterError, match="violates schema"):
        llm.complete("prompt", output_schema=impossible_schema)


def test_extract_cli_text_handles_jsonl_events() -> None:
    stdout = "\n".join(
        [
            json.dumps({"type": "start"}),
            json.dumps({"type": "message", "delta": "hello"}),
            json.dumps({"type": "done", "result": "final"}),
        ]
    )

    assert extract_cli_text(stdout) == "final"


def test_extract_cli_text_prefers_claude_structured_output() -> None:
    stdout = json.dumps(
        {
            "type": "result",
            "result": "schema 外の説明文",
            "structured_output": {
                "name": "oauth2_auth_constraint",
                "label": "Constraint",
                "description": "OAuth 2.0 必須",
            },
        },
        ensure_ascii=False,
    )

    assert json.loads(extract_cli_text(stdout)) == {
        "name": "oauth2_auth_constraint",
        "label": "Constraint",
        "description": "OAuth 2.0 必須",
    }
