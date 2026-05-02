"""Shared construction of CLI-backed LLM adapters for pipeline stages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from spec_grag.llm_adapters import ClaudeCLIAdapter, CodexCLIAdapter


def make_stage_llm_from_config(
    config: Mapping[str, Any],
    section_name: str,
    *,
    default_provider: str,
    disabled_providers: set[str] | frozenset[str] = frozenset(),
    default_model: str = "gpt-5.4",
    default_effort: str = "low",
    codex_sandbox: bool = True,
    claude_tools: bool = True,
) -> Any | None:
    """Build the configured Codex/Claude adapter for one LLM-backed stage."""

    stage_config = _mapping(config.get(section_name))
    provider = str(stage_config.get("provider", default_provider)).strip().lower()
    if provider in disabled_providers:
        return None
    if provider == "codex":
        kwargs: dict[str, Any] = {
            "command": str(stage_config.get("command") or "codex"),
            "model": str(stage_config.get("model") or default_model),
            "effort": str(stage_config.get("effort") or default_effort),
            "timeout_sec": int(stage_config.get("timeout_sec", 120)),
            "max_retries": int(stage_config.get("max_retries", 0)),
            "retry_backoff_sec": float(stage_config.get("retry_backoff_sec", 0.0)),
            "repair_on_schema_failure": bool(
                stage_config.get("repair_on_schema_failure", True)
            ),
        }
        if codex_sandbox:
            kwargs["sandbox"] = str(stage_config.get("sandbox", "read-only"))
        return CodexCLIAdapter(**kwargs)
    if provider == "claude":
        kwargs = {
            "command": str(stage_config.get("command") or "claude"),
            "model": str(stage_config.get("model") or ""),
            "effort": str(stage_config.get("effort") or default_effort),
            "timeout_sec": int(stage_config.get("timeout_sec", 120)),
            "max_retries": int(stage_config.get("max_retries", 0)),
            "retry_backoff_sec": float(stage_config.get("retry_backoff_sec", 0.0)),
            "repair_on_schema_failure": bool(
                stage_config.get("repair_on_schema_failure", True)
            ),
        }
        if claude_tools:
            kwargs["tools"] = str(stage_config.get("tools", ""))
        return ClaudeCLIAdapter(**kwargs)
    raise ValueError(f"unsupported {section_name}.provider: {provider}")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
