"""Optional run artifact persistence for CLI diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_grag.protocol import ResultEnvelope, SlashCommandRequest


def maybe_write_run_artifact(
    *,
    project_root: Path,
    config: dict[str, Any],
    request: SlashCommandRequest,
    envelope: ResultEnvelope,
) -> str | None:
    run_config = config.get("run", {})
    if not bool(run_config.get("save_artifacts", False)):
        return None
    artifact_dir = Path(str(run_config.get("artifact_dir", ".spec-grag/runs")))
    if not artifact_dir.is_absolute():
        artifact_dir = project_root / artifact_dir
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    digest = hashlib.sha256(envelope.to_json().encode("utf-8")).hexdigest()[:12]
    response_json = json.loads(envelope.to_json())
    trace_id = hashlib.sha256(
        f"{timestamp}:{request.command.value}:{digest}".encode("utf-8")
    ).hexdigest()[:16]
    path = artifact_dir / f"{timestamp}-{request.command.value}-{digest}.json"
    payload: dict[str, Any] = {
        "version": "1",
        "trace_id": trace_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "command": request.command.value,
        "status": envelope.status.value,
        "result_type": envelope.result_type.value,
        "runtime_mode": str(config.get("_runtime_mode", "production")),
        "runtime_policy": envelope.execution.runtime_policy,
        "providers": provider_summary(config),
        "warnings": envelope.warnings,
        "degraded_components": envelope.execution.degraded_components,
        "fallback_events": fallback_events(config, envelope),
        "retrieval_summary": retrieval_summary(envelope),
        "graph_revision": _graph_revision(response_json),
        "artifact_revision": _artifact_revision(project_root, response_json),
        "timing_summary": envelope.execution.timing_summary,
        "stage_timings": envelope.execution.stage_timings,
        "execution": envelope.execution.model_dump(mode="json"),
    }
    if bool(run_config.get("include_request", False)):
        payload["request"] = _artifact_payload(request.model_dump(mode="json"), run_config)
    if bool(run_config.get("include_response", False)):
        payload["response"] = _artifact_payload(response_json, run_config)
    _write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return str(path)


def _graph_revision(response_json: dict[str, Any]) -> str | None:
    freshness = _freshness_payload(response_json)
    value = freshness.get("graph_revision")
    return str(value) if value else None


def _artifact_revision(project_root: Path, response_json: dict[str, Any]) -> dict[str, Any] | None:
    freshness = _freshness_payload(response_json)
    graph_storage_path = freshness.get("graph_storage_path")
    if not graph_storage_path:
        return None
    path = Path(str(graph_storage_path))
    if not path.is_absolute():
        path = project_root / path
    revision_path = path / "artifact_revision.json"
    if not revision_path.exists():
        return None
    try:
        return json.loads(revision_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _freshness_payload(response_json: dict[str, Any]) -> dict[str, Any]:
    payload = response_json.get("payload")
    if not isinstance(payload, dict):
        return {}
    freshness = payload.get("freshness_report")
    return freshness if isinstance(freshness, dict) else {}


def _artifact_payload(value: Any, run_config: dict[str, Any]) -> Any:
    if not bool(run_config.get("redact_payload", False)):
        return value
    return _redact_value(value)


def _redact_value(value: Any) -> Any:
    sensitive_keys = {
        "task_prompt",
        "current_user_message",
        "recent_messages",
        "excerpt",
        "text",
        "response",
        "answer",
        "injection_context",
        "context_item",
    }
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) in sensitive_keys:
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = _redact_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def provider_summary(config: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for section in (
        "extraction",
        "embedding",
        "query_planner",
        "classification",
        "answer",
        "concept_diff",
        "community_report",
    ):
        section_config = config.get(section)
        if not isinstance(section_config, dict):
            continue
        summary[section] = {
            key: section_config[key]
            for key in ("mode", "provider", "model", "dimension", "fallback_on_error", "failure_fallback")
            if key in section_config
        }
    if "embedding" not in summary:
        summary["embedding"] = {
            "provider": "stable_hash",
            "model": "sha256-v1",
            "dimension": 8,
        }
    return summary


def fallback_events(config: dict[str, Any], envelope: ResultEnvelope) -> list[dict[str, str]]:
    """Extract stable fallback/degrade event records from providers and warnings."""

    events: list[dict[str, str]] = []
    runtime_mode = str(config.get("_runtime_mode", "production"))
    providers = provider_summary(config)
    smoke_only_providers = {
        "embedding": {"stable_hash"},
        "answer": {"template", "deterministic", "none", "disabled"},
        "classification": {"orchestrator_rule_based", "rule_based"},
        "concept_diff": {"source_derived", "template", "none", "disabled"},
        "community_report": {"deterministic", "template", "none", "disabled"},
        "query_planner": {"template", "deterministic", "none", "disabled"},
    }
    for component, smoke_values in smoke_only_providers.items():
        section = providers.get(component, {})
        provider = str(section.get("provider", section.get("mode", ""))).strip()
        if provider in smoke_values:
            events.append(
                {
                    "component": component,
                    "code": f"{runtime_mode}_provider:{provider}",
                    "source": "provider_config",
                }
            )

    for warning in envelope.warnings:
        lowered = warning.lower()
        if "fallback" not in lowered and "degraded" not in lowered:
            continue
        events.append(
            {
                "component": component_from_warning(warning),
                "code": stable_warning_code(warning),
                "source": "warning",
            }
        )
    return events


def component_from_warning(warning: str) -> str:
    prefix = stable_warning_code(warning)
    if prefix.startswith("answer_"):
        return "answer"
    if prefix.startswith("classification_"):
        return "classification"
    if prefix.startswith("concept_diff_"):
        return "concept_diff"
    if prefix.startswith("community_report_"):
        return "retrieval"
    if prefix.startswith("query_planner_"):
        return "query_planner"
    if prefix.startswith("embedding_"):
        return "embedding"
    if prefix.startswith("retrieval_") or prefix.startswith("chunk_"):
        return "retrieval"
    if prefix.startswith("schema_llm_") or prefix.startswith("extraction_"):
        return "extraction"
    return "unknown"


def stable_warning_code(warning: str) -> str:
    return warning.split(":", 1)[0]


def retrieval_summary(envelope: ResultEnvelope) -> dict[str, Any]:
    payload = envelope.payload
    result_type = envelope.result_type.value
    summary: dict[str, Any] = {"result_type": result_type}
    if result_type == "CoreResult" and hasattr(payload, "updated_sources"):
        summary.update(
            {
                "updated_sources": len(payload.updated_sources),
                "skipped_sources": len(payload.skipped_sources),
                "failed_sources": len(payload.failed_sources),
            }
        )
        return summary
    if result_type in {"InjectionContext", "RealignResult"}:
        context = payload.injection_context if result_type == "RealignResult" else payload
        summary.update(
            {
                "source_spec_constraints": len(
                    context.constraint_context.source_spec_constraints
                ),
                "related_source_sections": len(
                    context.target_context.related_source_sections
                ),
                "related_entities": len(context.target_context.related_entities),
                "related_concepts": len(context.target_context.related_concepts),
                "review_notes": len(context.review_notes),
                "conflict_notes": len(context.conflict_notes),
            }
        )
    return summary


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
