"""LLM provider boundary for `/spec-core` generation stages."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol


REAL_PROVIDER_ENV = "SPEC_GRAG_REAL_PROVIDER"
REAL_SMOKE_ENV = "SPEC_GRAG_REAL_SMOKE"
SPEC_CORE_SCOPE = "/spec-core"
TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_METADATA_VERSION = 1
SUCCESS = "success"
FAILED = "failed"
FRESH = "fresh"
DEGRADED = "degraded"
SPEC_CORE_GENERATION_STAGES = {
    "section_metadata",
    "section_summary",
    "section_search_keys",
    "related_sections",
    "related_section_selection",
    "chapter_key_anchor",
    "conflict_review",
    "conflict_detection",
    "conflict_judgement",
}


class LlmProviderError(Exception):
    """Base error for `/spec-core` LLM generation."""


class LlmValidationError(LlmProviderError):
    """Raised when provider output does not match the expected structure."""


class LlmTimeoutError(LlmProviderError):
    """Raised when provider generation times out."""


class RealLlmProviderDisabledError(LlmProviderError):
    """Raised when a real provider is requested without explicit opt-in."""


class LlmStageError(LlmProviderError, ValueError):
    """Raised when `[llm]` is asked to handle a non `/spec-core` stage."""


@dataclass(frozen=True)
class LlmDiagnostic:
    reason_code: str
    message: str
    attempt: int
    stage: str
    model: str
    timeout_sec: int
    provider: str
    prompt_version: str
    source_hash: str
    section_id: str | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "reason_code": self.reason_code,
            "message": self.message,
            "attempt": self.attempt,
            "stage": self.stage,
            "model": self.model,
            "timeout_sec": self.timeout_sec,
            "provider": self.provider,
            "prompt_version": self.prompt_version,
            "source_hash": self.source_hash,
            "severity": self.severity,
        }
        if self.section_id is not None:
            data["section_id"] = self.section_id
        return data

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def __contains__(self, value: object) -> bool:
        if not isinstance(value, str):
            return False
        data = self.to_dict()
        return value in data or value in self.message or value in self.reason_code

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class LlmRequest:
    """Structured request passed to a `/spec-core` LLM provider.

    The `[llm]` config is intentionally scoped to `/spec-core` artifact
    generation and is not used for `/spec-inject` or `/spec-realign` Agent work.
    """

    task: str
    prompt: str
    prompt_version: str
    model: str
    source_hash: str
    semantic_hash: str | None = None
    section_id: str | None = None
    stage: str | None = None
    metadata_version: int = DEFAULT_METADATA_VERSION
    effort: str | None = None
    input_hashes: Mapping[str, str] = field(default_factory=dict)
    context_hashes: Mapping[str, str] = field(default_factory=dict)
    section_hashes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        stage = self.stage or self.task
        if stage not in SPEC_CORE_GENERATION_STAGES:
            allowed = ", ".join(sorted(SPEC_CORE_GENERATION_STAGES))
            raise LlmStageError(
                f"[llm] is only available for /spec-core generation stages; "
                f"got {stage!r}. Agent-side LLM work for /spec-inject and "
                f"/spec-realign is outside this provider. allowed: {allowed}"
            )
        if self.stage is None:
            object.__setattr__(self, "stage", stage)

    def to_provider_payload(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "stage": self.stage,
            "prompt": self.prompt,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "source_hash": self.source_hash,
            "semantic_hash": self.semantic_hash,
            "section_id": self.section_id,
            "metadata_version": self.metadata_version,
            "effort": self.effort,
            "input_hashes": dict(self.input_hashes),
            "context_hashes": dict(self.context_hashes),
            "section_hashes": dict(self.section_hashes),
        }


@dataclass(frozen=True)
class LlmGenerationArtifact:
    prompt_version: str
    model: str
    source_hash: str
    semantic_hash: str | None
    output: dict[str, Any]
    metadata_version: int = DEFAULT_METADATA_VERSION
    task: str | None = None
    stage: str | None = None
    section_id: str | None = None
    provider: str | None = None
    cache_key: str | None = None
    context_hashes: Mapping[str, str] = field(default_factory=dict)
    section_hashes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LlmGenerationResult:
    status: str
    artifact: LlmGenerationArtifact | None = None
    diagnostics: list[LlmDiagnostic] | None = None
    attempts: int = 1
    diagnostic_items: list[dict[str, Any]] | None = None
    cache_hit: bool = False
    duration_ms: int | None = None


class LlmProvider(Protocol):
    @property
    def provider_id(self) -> str:
        """Stable provider identity for diagnostics and cache metadata."""

    def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
        """Return structured output for one `/spec-core` generation request."""


class FakeLlmProvider:
    """Deterministic provider for unit tests and default non-real-smoke runs."""

    provider_id = "fake"

    def __init__(
        self,
        response: Mapping[str, Any] | None = None,
        *,
        mode: str = "ok",
    ) -> None:
        self.response = dict(response) if response is not None else None
        self.mode = mode
        self.calls = 0

    def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
        self.calls += 1
        if self.mode == "timeout":
            raise LlmTimeoutError(f"generation timed out after {timeout_sec}s")
        if self.mode == "invalid":
            return {"unexpected": request.task}
        if self.response is not None:
            return dict(self.response)
        return _fake_response_for(request)


class SubprocessLlmProvider:
    """Subprocess-backed real provider, guarded by explicit real-provider opt-in.

    Interface:
    - stdin: JSON object matching `LlmRequest.to_provider_payload()`
    - stdout: JSON object containing the structured generation result
    - stderr/non-zero exit: treated as provider failure diagnostics
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        real_smoke_enabled: bool | None = None,
        provider_id: str = "subprocess",
    ) -> None:
        self.command = list(command)
        self.real_provider_enabled = (
            real_provider_enabled() if real_smoke_enabled is None else real_smoke_enabled
        )
        self.real_smoke_enabled = self.real_provider_enabled
        self.provider_id = provider_id

    def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
        if not self.real_provider_enabled:
            raise RealLlmProviderDisabledError(
                "real LLM provider requires SPEC_GRAG_REAL_PROVIDER=1 for normal "
                "operation, or SPEC_GRAG_REAL_SMOKE=1 for explicit smoke tests"
            )
        cleanup_paths: list[Path] = []
        try:
            command, stdin, cleanup_paths = _subprocess_invocation(self.command, request)
            completed = subprocess.run(
                command,
                input=stdin,
                text=True,
                capture_output=True,
                timeout=timeout_sec,
                check=False,
                env=_subprocess_env(command),
            )
            if completed.returncode != 0:
                raise LlmProviderError(completed.stderr.strip() or "LLM command failed")
            output = _extract_provider_output(completed.stdout)
            if not isinstance(output, dict):
                raise LlmValidationError("LLM command output must be an object")
            return output
        except subprocess.TimeoutExpired as exc:
            raise LlmTimeoutError(f"generation timed out after {timeout_sec}s") from exc
        finally:
            for path in cleanup_paths:
                path.unlink(missing_ok=True)


def build_spec_core_llm_provider(
    llm_config: Any,
    *,
    real_smoke_enabled: bool | None = None,
    usage_scope: str = SPEC_CORE_SCOPE,
) -> LlmProvider:
    """Build the provider described by `[llm]` for `/spec-core` only."""

    validate_llm_usage_scope(usage_scope)
    provider_name = _config_value(llm_config, "provider")
    if not isinstance(provider_name, str) or not provider_name:
        raise LlmProviderError("[llm].provider must be a non-empty string")
    normalized = provider_name.lower()

    if normalized == "fake":
        return FakeLlmProvider()

    enabled = real_provider_enabled() if real_smoke_enabled is None else real_smoke_enabled
    if normalized in {"subprocess", "codex_cli", "claude_cli"}:
        command = _config_value(llm_config, "command")
        if command is None:
            if normalized == "codex_cli":
                command = "codex"
            elif normalized == "claude_cli":
                command = "claude"
        command_args = _command_args(command)
        if not command_args:
            raise LlmProviderError("[llm].command is required for subprocess provider")
        return SubprocessLlmProvider(
            command_args,
            real_smoke_enabled=enabled,
            provider_id=normalized,
        )

    raise LlmProviderError(f"unsupported /spec-core LLM provider: {provider_name}")


def validate_llm_usage_scope(scope: str) -> str:
    if scope == SPEC_CORE_SCOPE:
        return scope
    raise LlmStageError(
        f"[llm] is only for {SPEC_CORE_SCOPE}; Agent-side LLM work for "
        f"/spec-inject and /spec-realign must use the external Agent environment, "
        f"not the /spec-core provider. got: {scope}"
    )


def real_smoke_opt_in_enabled(env: Mapping[str, str] | None = None) -> bool:
    return real_provider_enabled(env)


def real_provider_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return any(
        source.get(name, "").strip().lower() in TRUE_VALUES
        for name in (REAL_PROVIDER_ENV, REAL_SMOKE_ENV)
    )


def _subprocess_invocation(
    command: Sequence[str],
    request: LlmRequest,
) -> tuple[list[str], str | None, list[Path]]:
    command_args = list(command)
    payload = request.to_provider_payload()
    payload_json = json.dumps(payload, ensure_ascii=False)
    if not command_args:
        return command_args, payload_json, []

    executable = Path(command_args[0]).name
    if executable == "codex" and len(command_args) == 1:
        fd, schema_path = tempfile.mkstemp(prefix="spec-grag-llm-schema-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(_spec_core_output_schema(request), handle, ensure_ascii=False)
        codex_command = [
            command_args[0],
            "--ask-for-approval",
            "never",
            "exec",
            "--disable",
            "plugins",
            "--config",
            "analytics.enabled=false",
            "--config",
            f"model_reasoning_effort={json.dumps(request.effort or 'low')}",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-rules",
            "--sandbox",
            "read-only",
            "--json",
            "--output-schema",
            schema_path,
        ]
        if request.model and request.model != "real-smoke":
            codex_command.extend(["--model", request.model])
        codex_command.append("-")
        return codex_command, _provider_prompt(payload), [Path(schema_path)]
    if executable == "claude" and len(command_args) == 1:
        claude_command = [
            command_args[0],
            "--print",
            "--effort",
            request.effort or "low",
            "--no-session-persistence",
            "--disable-slash-commands",
            "--tools",
            "",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(_spec_core_output_schema(request), ensure_ascii=False),
        ]
        if request.model and request.model != "real-smoke":
            claude_command.extend(["--model", request.model])
        claude_command.append(_provider_prompt(payload))
        return claude_command, None, []
    return command_args, payload_json, []


def _subprocess_env(command: Sequence[str]) -> dict[str, str]:
    env = os.environ.copy()
    if command and Path(command[0]).name == "codex":
        env.pop("CODEX_HOME", None)
        env.pop("CODEX_THREAD_ID", None)
        env.pop("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", None)
    return env


def _provider_prompt(payload: Mapping[str, Any]) -> str:
    stage = str(payload.get("stage") or payload.get("task") or "")
    section_hashes = payload.get("section_hashes")
    is_batch = isinstance(section_hashes, Mapping) and len(section_hashes) > 1
    if stage == "related_section_selection":
        output_contract = (
            "The JSON object must include array field \"related_sections\". "
            "Each item must include \"target_section_id\", \"relation_hint\", "
            "\"confidence\", \"reason\", \"evidence_terms\", and \"channels\"."
        )
    elif is_batch:
        output_contract = (
            "The JSON object must include array field \"sections\". "
            "Each item must include string field \"section_id\", string field "
            "\"summary\", and array field \"search_keys\"."
        )
    else:
        output_contract = (
            "The JSON object must include at least string field \"summary\" and "
            "array field \"search_keys\"."
        )
    return (
        "You are the SPEC-grag /spec-core generation provider. "
        "Return only one JSON object. No markdown, no prose. "
        f"{output_contract}\n\n"
        f"Request JSON:\n{json.dumps(dict(payload), ensure_ascii=False, indent=2)}"
    )


def _spec_core_output_schema(request: LlmRequest) -> dict[str, Any]:
    if request.stage == "related_section_selection":
        return _related_section_selection_output_schema()
    section_hashes = request.section_hashes
    is_batch = len(section_hashes) > 1
    section_item_schema = {
        "type": "object",
        "properties": {
            "section_id": {"type": "string"},
            "summary": {"type": "string"},
            "search_keys": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["section_id", "summary", "search_keys"],
        "additionalProperties": False,
    }
    if is_batch:
        return {
            "type": "object",
            "properties": {
                "sections": {"type": "array", "items": section_item_schema},
            },
            "required": ["sections"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "search_keys": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "search_keys"],
        "additionalProperties": False,
    }


def _related_section_selection_output_schema() -> dict[str, Any]:
    related_item_schema = {
        "type": "object",
        "properties": {
            "target_section_id": {"type": "string"},
            "relation_hint": {
                "type": "string",
                "enum": [
                    "depends_on",
                    "refines",
                    "overlaps",
                    "conflicts_with",
                    "same_concept",
                    "see_also",
                ],
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "reason": {"type": "string"},
            "evidence_terms": {"type": "array", "items": {"type": "string"}},
            "channels": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "target_section_id",
            "relation_hint",
            "confidence",
            "reason",
            "evidence_terms",
            "channels",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "related_sections": {"type": "array", "items": related_item_schema},
        },
        "required": ["related_sections"],
        "additionalProperties": False,
    }


def _extract_provider_output(stdout: str) -> dict[str, Any]:
    text = _extract_cli_text(stdout)
    if not text:
        raise LlmValidationError("LLM command returned empty output")
    try:
        output = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmValidationError("LLM command did not return JSON") from exc
    if not isinstance(output, Mapping):
        raise LlmValidationError("LLM command output must be an object")
    return dict(output)


def _extract_cli_text(stdout: str) -> str:
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
    if not isinstance(value, Mapping):
        return None

    for key in ("structured_output",):
        if key not in value:
            continue
        nested = value[key]
        if isinstance(nested, (Mapping, list)):
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


def validate_structured_output(
    output: Any,
    *,
    required_fields: Sequence[str],
    field_schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(output, Mapping):
        raise LlmValidationError("LLM output must be an object")
    missing = [field for field in required_fields if field not in output]
    if missing:
        raise LlmValidationError(f"missing required fields: {', '.join(missing)}")
    errors = _validate_field_types(output, field_schema or {})
    if errors:
        raise LlmValidationError("; ".join(errors))
    return dict(output)


def generate_with_retries(
    provider: LlmProvider,
    request: LlmRequest,
    *,
    required_fields: Sequence[str],
    field_schema: Mapping[str, Any] | None = None,
    timeout_sec: int = 120,
    max_retries: int = 1,
) -> LlmGenerationResult:
    diagnostics: list[LlmDiagnostic] = []
    diagnostic_items: list[dict[str, Any]] = []
    attempts = max(0, max_retries) + 1
    provider_id = getattr(provider, "provider_id", provider.__class__.__name__)
    started = time.monotonic()
    for attempt in range(1, attempts + 1):
        try:
            output = provider.generate(request, timeout_sec=timeout_sec)
            validated = validate_structured_output(
                output,
                required_fields=required_fields,
                field_schema=field_schema,
            )
            duration_ms = _elapsed_ms(started)
            return LlmGenerationResult(
                status=SUCCESS,
                artifact=LlmGenerationArtifact(
                    prompt_version=request.prompt_version,
                    model=request.model,
                    source_hash=request.source_hash,
                    semantic_hash=request.semantic_hash,
                    output=validated,
                    metadata_version=request.metadata_version,
                    task=request.task,
                    stage=request.stage,
                    section_id=request.section_id,
                    provider=provider_id,
                    context_hashes=dict(request.context_hashes),
                    section_hashes=dict(request.section_hashes),
                ),
                diagnostics=diagnostics,
                attempts=attempt,
                diagnostic_items=diagnostic_items,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as exc:
            _append_diagnostic(
                diagnostics,
                diagnostic_items,
                code="timeout",
                message=f"timeout: {exc}",
                attempt=attempt,
                timeout_sec=timeout_sec,
                provider_id=provider_id,
                request=request,
            )
        except LlmTimeoutError as exc:
            _append_diagnostic(
                diagnostics,
                diagnostic_items,
                code="timeout",
                message=f"timeout: {exc}",
                attempt=attempt,
                timeout_sec=timeout_sec,
                provider_id=provider_id,
                request=request,
            )
        except LlmValidationError as exc:
            _append_diagnostic(
                diagnostics,
                diagnostic_items,
                code="validation_error",
                message=str(exc),
                attempt=attempt,
                timeout_sec=timeout_sec,
                provider_id=provider_id,
                request=request,
            )
        except RealLlmProviderDisabledError as exc:
            _append_diagnostic(
                diagnostics,
                diagnostic_items,
                code="real_provider_required",
                message=str(exc),
                attempt=attempt,
                timeout_sec=timeout_sec,
                provider_id=provider_id,
                request=request,
            )
            break
        except LlmProviderError as exc:
            _append_diagnostic(
                diagnostics,
                diagnostic_items,
                code="provider_error",
                message=str(exc),
                attempt=attempt,
                timeout_sec=timeout_sec,
                provider_id=provider_id,
                request=request,
            )
        except Exception as exc:
            _append_diagnostic(
                diagnostics,
                diagnostic_items,
                code="provider_exception",
                message=str(exc),
                attempt=attempt,
                timeout_sec=timeout_sec,
                provider_id=provider_id,
                request=request,
            )
    return LlmGenerationResult(
        status=FAILED,
        diagnostics=diagnostics,
        attempts=len(diagnostic_items) or attempts,
        diagnostic_items=diagnostic_items,
        duration_ms=_elapsed_ms(started),
    )


class GenerationCache:
    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)

    def cache_key(self, request: LlmRequest) -> str:
        # semantic_hash is deliberately excluded: if the source bytes, prompt
        # version, model, and explicit context hashes are unchanged, generation
        # may be reused even when semantic hashing logic changes.
        raw = _stable_json(
            {
                "prompt_version": request.prompt_version,
                "model": request.model,
                "source_hash": request.source_hash,
                "stage": request.stage,
                "task": request.task,
                "metadata_version": request.metadata_version,
                "effort": request.effort,
                "input_hashes": dict(request.input_hashes),
                "context_hashes": dict(request.context_hashes),
                "section_hashes": dict(request.section_hashes),
            }
        )
        return _sha256_text(raw)

    def path_for(self, request: LlmRequest) -> Path:
        return self.cache_dir / f"{self.cache_key(request)}.json"

    def load(self, request: LlmRequest) -> LlmGenerationArtifact | None:
        path = self.path_for(request)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return LlmGenerationArtifact(
            prompt_version=payload["prompt_version"],
            model=payload["model"],
            source_hash=payload["source_hash"],
            semantic_hash=request.semantic_hash,
            output=payload["output"],
            metadata_version=payload.get("metadata_version", DEFAULT_METADATA_VERSION),
            task=payload.get("task"),
            stage=payload.get("stage"),
            section_id=payload.get("section_id"),
            provider=payload.get("provider"),
            cache_key=payload.get("cache_key"),
            context_hashes=payload.get("context_hashes", {}),
            section_hashes=payload.get("section_hashes", {}),
        )

    def store(self, artifact: LlmGenerationArtifact, request: LlmRequest) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.path_for(request)
        data = asdict(artifact)
        data["cache_key"] = self.cache_key(request)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path


def generate_with_cache(
    provider: LlmProvider,
    request: LlmRequest,
    *,
    cache: GenerationCache,
    required_fields: Sequence[str],
    field_schema: Mapping[str, Any] | None = None,
    timeout_sec: int = 120,
    max_retries: int = 1,
) -> tuple[LlmGenerationResult, bool]:
    cached = cache.load(request)
    if cached is not None:
        try:
            validate_structured_output(
                cached.output,
                required_fields=required_fields,
                field_schema=field_schema,
            )
        except LlmValidationError:
            cached = None
        else:
            return (
                LlmGenerationResult(
                    status=SUCCESS,
                    artifact=cached,
                    attempts=0,
                    diagnostics=[],
                    diagnostic_items=[],
                    cache_hit=True,
                    duration_ms=0,
                ),
                True,
            )

    result = generate_with_retries(
        provider,
        request,
        required_fields=required_fields,
        field_schema=field_schema,
        timeout_sec=timeout_sec,
        max_retries=max_retries,
    )
    if result.artifact is not None:
        cache.store(result.artifact, request)
    return result, False


def summarize_generation_results(results: Mapping[str, LlmGenerationResult]) -> dict[str, Any]:
    failed_sections = [
        section_id for section_id, result in results.items() if result.status != SUCCESS
    ]
    freshness_status = classify_generation_status(results)
    blocking_reasons: list[str] = []
    if freshness_status == FAILED:
        blocking_reasons.append("failed_required_artifact")
    elif freshness_status == DEGRADED:
        blocking_reasons.append("degraded_optional_artifact")
    return {
        "failed_sections": failed_sections,
        "warnings": [f"LLM generation failed for {section_id}" for section_id in failed_sections],
        "freshness_status": freshness_status,
        "blocking_reasons": blocking_reasons,
    }


def classify_generation_status(results: Mapping[str, LlmGenerationResult]) -> str:
    if not results:
        return FRESH
    failed_count = sum(1 for result in results.values() if result.status != SUCCESS)
    if failed_count == 0:
        return FRESH
    if failed_count == len(results):
        return FAILED
    return DEGRADED


def _fake_response_for(request: LlmRequest) -> dict[str, Any]:
    seed = request.section_id or request.task
    search_key = seed.replace("/", " ").replace("_", " ").strip() or "fake"
    section_ids = list(request.section_hashes) or ([request.section_id] if request.section_id else [])
    section_outputs = [
        {
            "section_id": section_id,
            "summary": f"fake summary for {section_id}",
            "search_keys": [
                section_id.replace("/", " ").replace("_", " ").strip() or "fake",
            ],
            "identifiers": [],
            "related_sections": [],
        }
        for section_id in section_ids
    ]
    return {
        "summary": f"fake summary for {seed}",
        "search_keys": [search_key],
        "sections": section_outputs,
        "identifiers": [],
        "related_sections": [],
        "key_topics": [],
        "important_sections": [],
        "notes": [],
        "conflicts": [],
        "conflict_review_items": [],
    }


def _validate_field_types(
    output: Mapping[str, Any],
    field_schema: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    schema = dict(_default_field_schema())
    schema.update(field_schema)
    for field_name, expected in schema.items():
        if field_name not in output:
            continue
        value = output[field_name]
        if expected == "list[str]":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                errors.append(f"{field_name} must be a list of strings")
        elif expected == "list[object]":
            if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
                errors.append(f"{field_name} must be a list of objects")
        elif expected == "list":
            if not isinstance(value, list):
                errors.append(f"{field_name} must be a list")
        elif expected == "object":
            if not isinstance(value, Mapping):
                errors.append(f"{field_name} must be an object")
        elif isinstance(expected, type):
            if not isinstance(value, expected):
                errors.append(f"{field_name} must be {expected.__name__}")
        elif isinstance(expected, tuple) and all(isinstance(item, type) for item in expected):
            if not isinstance(value, expected):
                type_names = " or ".join(item.__name__ for item in expected)
                errors.append(f"{field_name} must be {type_names}")
    return errors


def _default_field_schema() -> dict[str, Any]:
    return {
        "summary": str,
        "search_keys": "list[str]",
        "identifiers": "list[str]",
        "related_sections": "list",
        "key_topics": "list[str]",
        "important_sections": "list[str]",
        "notes": "list[str]",
        "conflicts": "list",
        "conflict_review_items": "list",
    }


def _append_diagnostic(
    diagnostics: list[LlmDiagnostic],
    diagnostic_items: list[dict[str, Any]],
    *,
    code: str,
    message: str,
    attempt: int,
    timeout_sec: int,
    provider_id: str,
    request: LlmRequest,
) -> None:
    diagnostic = LlmDiagnostic(
        reason_code=code,
        message=message,
        attempt=attempt,
        stage=request.stage or request.task,
        model=request.model,
        timeout_sec=timeout_sec,
        provider=provider_id,
        prompt_version=request.prompt_version,
        source_hash=request.source_hash,
        section_id=request.section_id,
    )
    diagnostics.append(diagnostic)
    diagnostic_items.append(diagnostic.to_dict())


def _config_value(config: Any, key: str) -> Any:
    if isinstance(config, Mapping):
        return config.get(key)
    return getattr(config, key, None)


def _command_args(command: Any) -> list[str]:
    if command is None:
        return []
    if isinstance(command, str):
        return shlex.split(command)
    if isinstance(command, Sequence):
        return [str(part) for part in command]
    raise LlmProviderError("[llm].command must be a string or sequence")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
