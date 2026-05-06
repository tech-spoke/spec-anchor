"""LLM adapters for LlamaIndex integration."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata
from pydantic import PrivateAttr


class CLIAdapterError(RuntimeError):
    """Raised when a CLI-backed LLM call fails."""


class _CLIOutputValidationError(CLIAdapterError):
    def __init__(self, message: str, output_text: str) -> None:
        self.output_text = output_text
        super().__init__(message)


CLIRunner = Callable[[Sequence[str], str | None, int], subprocess.CompletedProcess[str]]


class _RunnerWrapper:
    def __init__(self, runner: CLIRunner) -> None:
        self.runner = runner

    def __call__(
        self, cmd: Sequence[str], stdin_text: str | None, timeout_sec: int
    ) -> subprocess.CompletedProcess[str]:
        return self.runner(cmd, stdin_text, timeout_sec)


def subprocess_runner(
    cmd: Sequence[str], stdin_text: str | None, timeout_sec: int
) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = (
        {"input": stdin_text}
        if stdin_text is not None
        else {"stdin": subprocess.DEVNULL}
    )
    return subprocess.run(
        list(cmd),
        **kwargs,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )


class CodexCLIAdapter(CustomLLM):
    """LlamaIndex CustomLLM backed by the Codex CLI subprocess."""

    command: str = "codex"
    model: str = "gpt-5.4"
    timeout_sec: int = 120
    context_window: int = 200_000
    num_output: int = 4096
    approval_policy: str = "never"
    sandbox: str = "read-only"
    ephemeral: bool = True
    ignore_rules: bool = True
    use_json_events: bool = True
    skip_git_repo_check: bool = True
    disable_features: tuple[str, ...] = ("plugins",)
    disable_analytics: bool = True
    effort: str | None = "low"
    prompt_via_stdin: bool = True
    max_retries: int = 0
    retry_backoff_sec: float = 0.0
    repair_on_schema_failure: bool = True
    _runner: _RunnerWrapper = PrivateAttr(default_factory=lambda: _RunnerWrapper(subprocess_runner))

    def __init__(self, *, runner: CLIRunner | None = None, **kwargs: Any) -> None:
        if "model_reasoning_effort" in kwargs:
            kwargs.setdefault("effort", kwargs.pop("model_reasoning_effort"))
        super().__init__(**kwargs)
        if runner is not None:
            self._runner = _RunnerWrapper(runner)

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.num_output,
            model_name=self.model,
            is_chat_model=False,
            is_function_calling_model=False,
        )

    def complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        output_schema = kwargs.pop("output_schema", None)
        schema = _schema_to_dict(output_schema) if output_schema is not None else None
        return complete_with_retries(
            adapter_name="Codex CLI",
            prompt=prompt,
            schema=schema,
            max_retries=self.max_retries,
            retry_backoff_sec=self.retry_backoff_sec,
            repair_on_schema_failure=self.repair_on_schema_failure,
            complete_once=lambda attempt_prompt: self._complete_once(
                attempt_prompt,
                schema=schema,
            ),
        )

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> Iterator[CompletionResponse]:
        response = self.complete(prompt, formatted=formatted, **kwargs)
        yield CompletionResponse(text=response.text, delta=response.text, raw=response.raw)

    def _build_command(
        self, prompt: str, *, output_schema: dict[str, Any] | type[Any] | None = None
    ) -> tuple[list[str], list[Path]]:
        cmd = [self.command]
        if self.approval_policy:
            # --ask-for-approval is a top-level Codex option, before `exec`.
            cmd.extend(["--ask-for-approval", self.approval_policy])
        cmd.append("exec")
        for feature in self.disable_features:
            feature_name = str(feature).strip()
            if feature_name:
                cmd.extend(["--disable", feature_name])
        if self.disable_analytics:
            cmd.extend(["--config", "analytics.enabled=false"])
        if self.effort:
            cmd.extend(
                [
                    "--config",
                    f"model_reasoning_effort={json.dumps(self.effort)}",
                ]
            )
        cmd.extend(["--model", self.model, "--sandbox", self.sandbox])
        cleanup_paths: list[Path] = []
        if self.ephemeral:
            cmd.append("--ephemeral")
        if self.ignore_rules:
            cmd.append("--ignore-rules")
        if self.skip_git_repo_check:
            cmd.append("--skip-git-repo-check")
        if self.use_json_events:
            cmd.append("--json")

        if output_schema is not None:
            schema = _schema_to_dict(output_schema)
            fd, schema_path = tempfile.mkstemp(
                prefix="spec-grag-output-schema-", suffix=".json"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(schema, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            path = Path(schema_path)
            cleanup_paths.append(path)
            cmd.extend(["--output-schema", str(path)])

        if self.prompt_via_stdin:
            cmd.append("-")
        else:
            cmd.append(prompt)
        return cmd, cleanup_paths

    def _complete_once(
        self, prompt: str, *, schema: dict[str, Any] | None
    ) -> CompletionResponse:
        cmd, cleanup_paths = self._build_command(prompt, output_schema=schema)
        try:
            result = run_cli_command(
                self._runner,
                cmd,
                stdin_text=prompt if self.prompt_via_stdin else None,
                timeout_sec=self.timeout_sec,
                adapter_name="Codex CLI",
            )
            if result.returncode != 0:
                raise CLIAdapterError(
                    f"Codex CLI exited with {result.returncode}: {result.stderr.strip()}"
                )
            text = extract_cli_text(result.stdout)
            if not text:
                raise CLIAdapterError("Codex CLI returned empty output")
            if schema is not None:
                validate_cli_json_text(text, schema)
            return CompletionResponse(
                text=text,
                raw={
                    "command": cmd,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                },
            )
        finally:
            for path in cleanup_paths:
                path.unlink(missing_ok=True)


class ClaudeCLIAdapter(CustomLLM):
    """LlamaIndex CustomLLM backed by the Claude Code CLI subprocess."""

    command: str = "claude"
    model: str = ""
    timeout_sec: int = 120
    context_window: int = 200_000
    num_output: int = 4096
    no_session_persistence: bool = True
    disable_slash_commands: bool = True
    tools: str = ""
    output_format: str = "json"
    effort: str | None = "low"
    max_retries: int = 0
    retry_backoff_sec: float = 0.0
    repair_on_schema_failure: bool = True
    _runner: _RunnerWrapper = PrivateAttr(default_factory=lambda: _RunnerWrapper(subprocess_runner))

    def __init__(self, *, runner: CLIRunner | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if runner is not None:
            self._runner = _RunnerWrapper(runner)

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.num_output,
            model_name=self.model or "claude-default",
            is_chat_model=False,
            is_function_calling_model=False,
        )

    def complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        output_schema = kwargs.pop("output_schema", None)
        schema = _schema_to_dict(output_schema) if output_schema is not None else None
        return complete_with_retries(
            adapter_name="Claude CLI",
            prompt=prompt,
            schema=schema,
            max_retries=self.max_retries,
            retry_backoff_sec=self.retry_backoff_sec,
            repair_on_schema_failure=self.repair_on_schema_failure,
            complete_once=lambda attempt_prompt: self._complete_once(
                attempt_prompt,
                schema=schema,
            ),
        )

    def _complete_once(
        self, prompt: str, *, schema: dict[str, Any] | None
    ) -> CompletionResponse:
        cmd = self._build_command(prompt, output_schema=schema)
        result = run_cli_command(
            self._runner,
            cmd,
            stdin_text=None,
            timeout_sec=self.timeout_sec,
            adapter_name="Claude CLI",
        )
        if result.returncode != 0:
            raise CLIAdapterError(
                f"Claude CLI exited with {result.returncode}: {result.stderr.strip()}"
            )
        text = extract_cli_text(result.stdout)
        if not text:
            raise CLIAdapterError("Claude CLI returned empty output")
        if schema is not None:
            validate_cli_json_text(text, schema)
        return CompletionResponse(
            text=text,
            raw={
                "command": cmd,
                "stderr": result.stderr,
                "returncode": result.returncode,
            },
        )

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> Iterator[CompletionResponse]:
        response = self.complete(prompt, formatted=formatted, **kwargs)
        yield CompletionResponse(text=response.text, delta=response.text, raw=response.raw)

    def _build_command(
        self, prompt: str, *, output_schema: dict[str, Any] | type[Any] | None = None
    ) -> list[str]:
        cmd = [self.command, "--print"]
        if self.model:
            cmd.extend(["--model", self.model])
        if self.effort:
            cmd.extend(["--effort", self.effort])
        if self.no_session_persistence:
            cmd.append("--no-session-persistence")
        if self.disable_slash_commands:
            cmd.append("--disable-slash-commands")
        cmd.extend(["--tools", self.tools])
        cmd.extend(["--output-format", self.output_format])
        if output_schema is not None:
            schema = _schema_to_dict(output_schema)
            cmd.extend(["--json-schema", json.dumps(schema, ensure_ascii=False)])
        cmd.append(prompt)
        return cmd


CompleteOnce = Callable[[str], CompletionResponse]


def complete_with_retries(
    *,
    adapter_name: str,
    prompt: str,
    schema: dict[str, Any] | None,
    max_retries: int,
    retry_backoff_sec: float,
    repair_on_schema_failure: bool,
    complete_once: CompleteOnce,
) -> CompletionResponse:
    attempt_prompt = prompt
    attempt_errors: list[str] = []
    attempts = max(1, max_retries + 1)
    last_error: CLIAdapterError | None = None

    for attempt_index in range(attempts):
        try:
            response = complete_once(attempt_prompt)
            raw = dict(response.raw or {})
            raw["attempt_count"] = attempt_index + 1
            if attempt_errors:
                raw["attempt_errors"] = attempt_errors
            return CompletionResponse(text=response.text, raw=raw)
        except _CLIOutputValidationError as exc:
            last_error = exc
            if attempt_index >= attempts - 1:
                break
            attempt_errors.append(str(exc))
            attempt_prompt = (
                build_schema_repair_prompt(
                    original_prompt=prompt,
                    schema=schema,
                    invalid_output=exc.output_text,
                    validation_error=str(exc),
                )
                if schema is not None and repair_on_schema_failure
                else prompt
            )
            sleep_for_retry(retry_backoff_sec)
        except CLIAdapterError as exc:
            last_error = exc
            if attempt_index >= attempts - 1:
                break
            attempt_errors.append(str(exc))
            attempt_prompt = prompt
            sleep_for_retry(retry_backoff_sec)

    assert last_error is not None
    raise CLIAdapterError(
        f"{adapter_name} failed after {attempts} attempt(s): {last_error}"
    ) from last_error


def run_cli_command(
    runner: _RunnerWrapper,
    cmd: Sequence[str],
    *,
    stdin_text: str | None,
    timeout_sec: int,
    adapter_name: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(cmd, stdin_text, timeout_sec)
    except subprocess.TimeoutExpired as exc:
        raise CLIAdapterError(
            f"{adapter_name} timed out after {timeout_sec}s"
        ) from exc


def sleep_for_retry(retry_backoff_sec: float) -> None:
    if retry_backoff_sec > 0:
        time.sleep(retry_backoff_sec)


def build_schema_repair_prompt(
    *,
    original_prompt: str,
    schema: dict[str, Any] | None,
    invalid_output: str,
    validation_error: str,
) -> str:
    return "\n".join(
        [
            original_prompt,
            "",
            "Previous output failed local schema validation.",
            f"Validation error: {validation_error}",
            "Return only JSON that satisfies the supplied schema.",
            "Do not include markdown fences or explanatory prose.",
            "",
            "SUPPLIED_SCHEMA:",
            json.dumps(schema or {}, ensure_ascii=False, sort_keys=True),
            "",
            "INVALID_OUTPUT:",
            invalid_output,
        ]
    )


def _schema_to_dict(output_schema: dict[str, Any] | type[Any]) -> dict[str, Any]:
    if isinstance(output_schema, dict):
        return output_schema
    if hasattr(output_schema, "model_json_schema"):
        return output_schema.model_json_schema()
    raise TypeError("output_schema must be a JSON schema dict or pydantic model class")


def extract_cli_text(stdout: str) -> str:
    """Extract assistant text from Codex/Claude style JSON or JSONL output."""

    text = stdout.strip()
    if not text:
        return ""

    parsed_json = _try_json_loads(text)
    if parsed_json is not None:
        extracted = _extract_text_from_json(parsed_json)
        if extracted is not None:
            return extracted
        if isinstance(parsed_json, (dict, list)):
            return json.dumps(parsed_json, ensure_ascii=False)
        return str(parsed_json)

    events: list[Any] = []
    for line in text.splitlines():
        parsed_line = _try_json_loads(line.strip())
        if parsed_line is not None:
            events.append(parsed_line)
    for event in reversed(events):
        extracted = _extract_text_from_json(event)
        if extracted:
            return extracted

    return text


def _try_json_loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_text_from_json(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_extract_text_from_json(item) for item in value]
        joined = "".join(part for part in parts if part)
        return joined or None
    if not isinstance(value, dict):
        return None

    for key in ("structured_output",):
        if key not in value:
            continue
        nested = value[key]
        if isinstance(nested, (dict, list)):
            return json.dumps(nested, ensure_ascii=False)
        extracted = _extract_text_from_json(nested)
        if extracted:
            return extracted

    for key in ("result", "output_text", "text", "content", "message"):
        if key not in value:
            continue
        extracted = _extract_text_from_json(value[key])
        if extracted:
            return extracted

    for key in ("delta", "item", "data"):
        if key in value:
            extracted = _extract_text_from_json(value[key])
            if extracted:
                return extracted

    return None


def validate_cli_json_text(text: str, schema: dict[str, Any]) -> None:
    """Validate CLI structured output locally.

    CLI-level structured output is useful, but real CLI smoke tests showed that
    impossible schemas may still exit 0 with non-conforming text. The adapter
    therefore treats local validation as the contract boundary.
    """

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _CLIOutputValidationError(
            f"CLI output is not valid JSON: {exc.msg}",
            text,
        ) from exc

    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(parsed)
    except SchemaError as exc:
        raise CLIAdapterError(f"Invalid output schema: {exc.message}") from exc
    except ValidationError as exc:
        raise _CLIOutputValidationError(
            f"CLI output violates schema: {exc.message}",
            text,
        ) from exc
