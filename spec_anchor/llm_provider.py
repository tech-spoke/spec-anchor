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


FAKE_LLM_ENV = "SPEC_ANCHOR_FAKE_LLM"
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
    "spec_claims",
    "conflict_candidate_triage",
    "related_sections",
    "related_section_selection",
    "chapter_key_anchor",
    "conflict_review",
}


class LlmProviderError(Exception):
    """Base error for `/spec-core` LLM generation."""


class LlmValidationError(LlmProviderError):
    """Raised when provider output does not match the expected structure."""


class LlmTimeoutError(LlmProviderError):
    """Raised when provider generation times out."""


class RealLlmProviderDisabledError(LlmProviderError):
    """Raised when a test explicitly disables a subprocess-backed provider."""


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
    # Per-call token usage / cost captured from the underlying CLI's JSON
    # output (codex `turn.completed.usage`, claude `usage` + `total_cost_usd`).
    # Empty dict for FakeLlmProvider or when stdout doesn't expose usage info.
    # Aggregated by core.py:_record_llm_call_stats into core_progress.json.
    usage: dict[str, Any] | None = None


class LlmProvider(Protocol):
    @property
    def provider_id(self) -> str:
        """Stable provider identity for diagnostics and cache metadata."""

    def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
        """Return structured output for one `/spec-core` generation request."""


class FakeLlmProvider:
    """Deterministic provider for tests and explicit fake/offline configs.

    Normal `/spec-core` operation does not select this provider because a smoke
    environment variable is missing. It is selected only when the caller injects
    it directly or the project config explicitly sets `[llm].provider = "fake"`.
    """

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
    """Subprocess-backed real provider for `/spec-core`.

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
        self.real_provider_enabled = True if real_smoke_enabled is None else real_smoke_enabled
        self.real_smoke_enabled = self.real_provider_enabled
        self.provider_id = provider_id

    def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
        if not self.real_provider_enabled:
            raise RealLlmProviderDisabledError(
                "real LLM provider was explicitly disabled by the caller"
            )
        cleanup_paths: list[Path] = []
        try:
            command, stdin, cleanup_paths = _subprocess_invocation(self.command, request)
            if (
                os.environ.get("SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION", "").strip().lower()
                in {"1", "true", "yes", "on"}
                and request.stage == "related_section_selection"
            ):
                _dump_provider_invocation(command, stdin)
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
    provider_id: str | None = None,
    stage: str | None = None,
    env: Mapping[str, str] | None = None,
    real_smoke_enabled: bool | None = None,
    usage_scope: str = SPEC_CORE_SCOPE,
) -> LlmProvider:
    """Build the provider described by `[llm]` for `/spec-core` only.

    When `stage` is supplied (e.g. ``"section_metadata"``), the per-stage
    routing in `[llm.stage_routing]` selects the model / effort tuned for that
    stage. Explicit `provider_id` overrides the routing.

    If the env var `SPEC_ANCHOR_FAKE_LLM` is truthy (1 / true / yes / on),
    return the in-process FakeLlmProvider regardless of `[llm.providers]`
    contents. Used for tests / smoke runs that must not spawn real CLIs.
    """

    validate_llm_usage_scope(usage_scope)
    source = os.environ if env is None else env
    if source.get(FAKE_LLM_ENV, "").lower() in TRUE_VALUES:
        return FakeLlmProvider()

    selected_config = select_llm_provider_config(
        llm_config,
        provider_id=provider_id,
        stage=stage,
        env=env,
    )
    command = _config_value(selected_config, "command")
    command_args = _command_args(command)
    if not command_args:
        raise LlmProviderError("[llm.providers.<id>].command is required")
    enabled = True if real_smoke_enabled is None else real_smoke_enabled
    return SubprocessLlmProvider(
        command_args,
        real_smoke_enabled=enabled,
        provider_id=str(command_args[0]),
    )


def select_llm_provider_config(
    llm_config: Any,
    *,
    provider_id: str | None = None,
    stage: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Any:
    """Select one configured `/spec-core` LLM provider.

    Resolution priority: explicit `provider_id` (CLI `--llm-provider`) >
    `[llm.stage_routing].<stage>` > first entry of `[llm.providers]`.

    If `llm_config` has no `providers` key (already a single-provider mapping,
    e.g. a downstream caller pre-selected one with `_config_with_selected_llm`),
    it is returned as-is.
    """

    del env  # env-based provider id override removed; CLI --llm-provider is the only override
    requested = provider_id
    providers = _config_value(llm_config, "providers")
    if not isinstance(providers, Mapping) or not providers:
        return llm_config
    stage_routing = _config_value(llm_config, "stage_routing")
    stage_provider = None
    if (
        stage
        and isinstance(stage_routing, Mapping)
        and isinstance(stage_routing.get(stage), str)
    ):
        stage_provider = stage_routing.get(stage)
    selected_name = requested or stage_provider
    if not selected_name:
        selected_name = next(iter(providers))
    selected = providers.get(str(selected_name))
    if selected is None:
        known = ", ".join(sorted(str(name) for name in providers))
        raise LlmProviderError(
            f"unknown [llm] provider id {selected_name!r}; configured providers: {known}"
        )
    return selected


def validate_llm_usage_scope(scope: str) -> str:
    if scope == SPEC_CORE_SCOPE:
        return scope
    raise LlmStageError(
        f"[llm] is only for {SPEC_CORE_SCOPE}; Agent-side LLM work for "
        f"/spec-inject and /spec-realign must use the external Agent environment, "
        f"not the /spec-core provider. got: {scope}"
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
        fd, schema_path = tempfile.mkstemp(prefix="spec-anchor-llm-schema-", suffix=".json")
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
        # `--exclude-dynamic-system-prompt-sections` moves per-machine sections
        # (cwd, env info, memory paths, git status) out of the cached system
        # prompt. Without this flag, every spec-anchor core --rebuild rewrites
        # those sections (especially `git status`) so the Claude prompt cache
        # entry is invalidated each run, billing the full system prompt as
        # `cache_creation_input_tokens`. B-1 criterion A (90% cache reuse on
        # the second run) cannot be met without this flag because spec-anchor's
        # catalog determinism alone does not stabilize Claude Code's own
        # dynamic system prompt.
        claude_command = [
            command_args[0],
            "--print",
            "--effort",
            request.effort or "low",
            "--no-session-persistence",
            "--disable-slash-commands",
            "--exclude-dynamic-system-prompt-sections",
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


def _dump_provider_invocation(command: Sequence[str], stdin: str | None) -> None:
    """Append the resolved subprocess command + stdin to a debug file.

    Gate: `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION=1`. Used to verify byte-level
    stability of the actual command Claude / Codex sees across consecutive
    runs. Writes are best-effort; never raise.
    """

    path = os.environ.get("SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION_PATH", "").strip()
    target = Path(path) if path else Path(".spec-anchor/state/_debug_provider_invocations.jsonl")
    record = {
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "command": list(command),
        "stdin": stdin,
        "command_sha256": hashlib.sha256(
            json.dumps(list(command), ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "stdin_sha256": (
            hashlib.sha256((stdin or "").encode("utf-8")).hexdigest()
            if stdin is not None
            else None
        ),
        "stdin_len": len(stdin) if stdin else 0,
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
    except OSError:
        return


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
            "The JSON object must include array field \"sections\". "
            "Each section item must include \"source_section_id\" and array field "
            "\"related_sections\". Each related_sections item must include "
            "\"target_section_id\", \"relation_hint\", \"confidence\", "
            "and \"evidence_terms\"."
        )
    elif stage == "conflict_review":
        output_contract = (
            "You are reviewing a potential conflict between two specification sections. "
            "The JSON object must include string field \"outcome\" and string field \"severity\". "
            "\"outcome\" must be one of: \"needs_human_review\" (a real conflict requiring human decision), "
            "\"not_a_conflict\" (sections are compatible), or \"false_positive\" (no actual conflict). "
            "\"severity\" must be one of: \"low\", \"medium\", \"high\". "
            "Optional: string field \"why_not_pending\" (reason when outcome is not needs_human_review), "
            "string field \"summary\" (brief description of the conflict)."
        )
    elif stage == "chapter_key_anchor":
        output_contract = (
            "The JSON object must include string field \"summary\" (2-3 sentence description of the "
            "chapter's intent, must not be empty), array field \"key_topics\" (3-6 natural-language "
            "phrases describing the chapter's themes), array field \"important_sections\" (section_ids "
            "to read first, max 5), and array field \"notes\" (0-3 cautions for the Agent)."
        )
    elif stage == "spec_claims":
        output_contract = (
            "The JSON object must include exactly one top-level array field \"claims\". "
            "Each item must include claim_text, target, target_aliases, claim_kind, "
            "evidence_span, evidence_start, evidence_end, evidence_hash, confidence, "
            "and retrieval. The retrieval object must include sparse_keys, "
            "embedding_text, and conflict_probes. Use an empty claims array when "
            "the section contains no grounded specification claim."
        )
    elif stage == "conflict_candidate_triage":
        output_contract = (
            "The JSON object must include exactly boolean field \"send_to_review\", "
            "string field \"reason\", and string field \"confidence\". "
            "\"confidence\" must be one of: \"high\", \"medium\", \"low\". "
            "Do not include conflict_confirmed, human_review_required, resolution, "
            "or any other fields."
        )
    elif is_batch:
        output_contract = (
            "The JSON object must include array field \"sections\". "
            "Each item must include string field \"section_id\", string field "
            "\"summary\", and array field \"search_keys\". "
            "Return exactly one item in \"sections\" for every section in the input \"sections\" array. "
            "Use the exact \"section_id\" value from the input. "
            "Do not omit, add, rename, or merge sections. "
            "If a section is unclear, return an empty \"summary\" and empty \"search_keys\" "
            "for that item but keep the item in the output."
        )
    else:
        output_contract = (
            "The JSON object must include at least string field \"summary\" and "
            "array field \"search_keys\"."
        )
    return (
        "You are the SPEC-anchor /spec-core generation provider. "
        "Return only one JSON object. No markdown, no prose. "
        f"{output_contract}\n\n"
        # `sort_keys=True` is load-bearing: the payload contains dict fields
        # (notably `section_hashes`) populated from set-based iteration in the
        # caller, so dict insertion order can differ between processes due to
        # Python hash randomization. Without sorting, the resulting prompt
        # bytes differ between consecutive `spec-anchor core --rebuild` runs and
        # the Claude prompt cache is invalidated (B-1 criterion A).
        f"Request JSON:\n{json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True)}"
    )


def _spec_core_output_schema(request: LlmRequest) -> dict[str, Any]:
    if request.stage == "related_section_selection":
        return _related_section_selection_output_schema()
    if request.stage == "chapter_key_anchor":
        return _chapter_key_anchor_output_schema()
    if request.stage == "conflict_review":
        return _conflict_review_output_schema()
    if request.stage == "spec_claims":
        return _spec_claims_output_schema()
    if request.stage == "conflict_candidate_triage":
        return _conflict_candidate_triage_output_schema()
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


def _chapter_key_anchor_output_schema() -> dict[str, Any]:
    """JSON schema for the chapter_key_anchor LLM stage (Phase R-7).

    The chapter anchor structure differs from the section_metadata
    schema: the LLM emits a chapter-level `summary` plus `key_topics`,
    `important_sections`, and `notes` aligned with
    `doc/EXTERNAL_DESIGN.ja.md` §2.9. Without this dedicated schema the
    codex provider would receive the section_metadata schema (with
    `search_keys`) and produce output that
    `spec_anchor.chapter_anchors._anchor_from_llm_output` rejects, marking
    every chapter as failed in the Chapter Key Anchor artifact (since
    AUD-006 the failed chapters are no longer replaced by any fallback).
    """

    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "key_topics": {"type": "array", "items": {"type": "string"}},
            "important_sections": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "key_topics", "important_sections", "notes"],
        "additionalProperties": False,
    }


def _conflict_review_output_schema() -> dict[str, Any]:
    """JSON schema for the conflict_review LLM stage."""

    return {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "string",
                "enum": ["needs_human_review", "not_a_conflict", "false_positive"],
            },
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "summary": {"type": "string"},
            "why_not_pending": {"type": "string"},
        },
        "required": ["outcome", "severity"],
        "additionalProperties": False,
    }


def _spec_claims_output_schema() -> dict[str, Any]:
    claim_schema = {
        "type": "object",
        "properties": {
            "claim_text": {"type": "string"},
            "target": {"type": "string"},
            "target_aliases": {"type": "array", "items": {"type": "string"}},
            "scope": {"type": "string"},
            "condition": {"type": "string"},
            "value": {"type": "string"},
            "claim_kind": {"type": "string"},
            "claim_kind_confidence": {"type": "string"},
            "evidence_span": {"type": "string"},
            "evidence_start": {"type": "integer"},
            "evidence_end": {"type": "integer"},
            "evidence_hash": {"type": "string"},
            "confidence": {"type": "string"},
            "retrieval": {
                "type": "object",
                "properties": {
                    "sparse_keys": {"type": "array", "items": {"type": "string"}},
                    "embedding_text": {"type": "string"},
                    "conflict_probes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["sparse_keys", "embedding_text", "conflict_probes"],
                "additionalProperties": False,
            },
        },
        "required": [
            "claim_text",
            "target",
            "target_aliases",
            "scope",
            "condition",
            "value",
            "claim_kind",
            "claim_kind_confidence",
            "evidence_span",
            "evidence_start",
            "evidence_end",
            "evidence_hash",
            "confidence",
            "retrieval",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "claims": {"type": "array", "items": claim_schema},
        },
        "required": ["claims"],
        "additionalProperties": False,
    }


def _conflict_candidate_triage_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "send_to_review": {"type": "boolean"},
            "reason": {"type": "string"},
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
        },
        "required": ["send_to_review", "reason", "confidence"],
        "additionalProperties": False,
    }


def _related_section_selection_output_schema() -> dict[str, Any]:
    """JSON schema for the related_section_selection batch output (Phase D)."""

    related_item_schema = {
        "type": "object",
        "properties": {
            "target_section_id": {"type": "string"},
            "relation_hint": {
                "type": "string",
                "enum": [
                    "depends_on",
                    "impacts",
                    "prerequisite",
                    "same_policy",
                    "see_also",
                ],
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "evidence_terms": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "target_section_id",
            "relation_hint",
            "confidence",
            "evidence_terms",
        ],
        "additionalProperties": False,
    }
    section_envelope_schema = {
        "type": "object",
        "properties": {
            "source_section_id": {"type": "string"},
            "related_sections": {
                "type": "array",
                "items": related_item_schema,
            },
        },
        "required": ["source_section_id", "related_sections"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": section_envelope_schema,
            },
        },
        "required": ["sections"],
        "additionalProperties": False,
    }


USAGE_META_KEY = "__spec_anchor_usage"


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
    output_dict = dict(output)
    usage = _extract_cli_usage(stdout)
    if usage:
        # Carry usage through generate's return so generate_with_retries can
        # pop it into LlmGenerationResult.usage. The agent message is unchanged
        # for downstream consumers; the meta key is stripped before validation.
        output_dict[USAGE_META_KEY] = usage
    return output_dict


def _extract_cli_usage(stdout: str) -> dict[str, Any]:
    """Pull token / cost usage from codex `turn.completed` events or claude JSON.

    Returns an empty dict if the CLI didn't surface usage info.
    """

    text = stdout.strip()
    if not text:
        return {}

    # Claude `--output-format json` emits a single object containing usage and
    # total_cost_usd at the top level.
    parsed = _try_json_loads(text)
    if isinstance(parsed, Mapping):
        usage = _normalize_claude_usage(parsed)
        if usage:
            return usage

    # Codex `--json` streams events, each on its own line. Look for the
    # final turn.completed event which carries the aggregated usage.
    last_codex_usage: dict[str, Any] = {}
    for line in text.splitlines():
        line_parsed = _try_json_loads(line.strip())
        if not isinstance(line_parsed, Mapping):
            continue
        if line_parsed.get("type") == "turn.completed":
            usage_payload = line_parsed.get("usage")
            if isinstance(usage_payload, Mapping):
                last_codex_usage = _normalize_codex_usage(usage_payload)
    return last_codex_usage


def _normalize_codex_usage(usage: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "provider": "codex",
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cached_input_tokens": int(usage.get("cached_input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "reasoning_output_tokens": int(usage.get("reasoning_output_tokens") or 0),
    }


def _normalize_claude_usage(payload: Mapping[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return {}
    cost = payload.get("total_cost_usd")
    return {
        "provider": "claude",
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens") or 0),
        "cache_read_input_tokens": int(usage.get("cache_read_input_tokens") or 0),
        "total_cost_usd": float(cost) if cost is not None else 0.0,
    }


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
            usage: dict[str, Any] = {}
            if isinstance(output, dict):
                # Strip usage meta before validation so the agent message
                # written to artifact.output (and cache) stays clean.
                usage = output.pop(USAGE_META_KEY, {}) or {}
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
                usage=usage if usage else None,
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
                code="real_provider_disabled",
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
    if request.stage == "spec_claims":
        return {"claims": []}
    if request.stage == "conflict_candidate_triage":
        return {
            "send_to_review": False,
            "reason": "Fake provider does not send this pair to Conflict Review.",
            "confidence": "low",
        }
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
        elif expected == "list|object":
            if not isinstance(value, (list, Mapping)):
                errors.append(f"{field_name} must be a list or object")
        elif expected == "non_empty_str":
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{field_name} must be a non-empty string")
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
