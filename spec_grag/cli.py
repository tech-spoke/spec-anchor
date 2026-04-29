"""Minimal SPEC-grag CLI transport skeleton."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from spec_grag.protocol import (
    Command,
    ConversationContext,
    CoreResult,
    ErrorResult,
    ExecutionMetadata,
    FreshnessReport,
    InjectionContext,
    RealignResult,
    ResultEnvelope,
    ResultStatus,
    ResultType,
    SlashCommandRequest,
    validation_error_to_details,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spec-grag")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON output")
    args = parser.parse_args(argv)

    envelope = run_transport(sys.stdin)
    sys.stdout.write(envelope.to_json(indent=2 if args.pretty else None))
    sys.stdout.write("\n")
    return 1 if envelope.status == ResultStatus.FAILED else 0


def run_transport(stdin: TextIO) -> ResultEnvelope:
    try:
        raw = stdin.read()
        request = SlashCommandRequest.model_validate_json(raw)
    except ValidationError as exc:
        return error_envelope(
            "invalid_request",
            "Invalid SlashCommandRequest JSON",
            validation_error_to_details(exc),
        )
    except json.JSONDecodeError as exc:
        return error_envelope(
            "invalid_json",
            "Request body is not valid JSON",
            {"line": exc.lineno, "column": exc.colno, "message": exc.msg},
        )

    return run_request(request)


def run_request(request: SlashCommandRequest) -> ResultEnvelope:
    project_root = Path(request.project_root).expanduser().resolve()
    config_result = load_project_config(project_root)
    if isinstance(config_result, ResultEnvelope):
        return config_result

    config = config_result
    graph_storage = graph_storage_path(project_root, config)
    freshness = freshness_report(graph_storage)

    if request.command == Command.SPEC_CORE:
        return run_spec_core(request, graph_storage, freshness)
    if request.command == Command.SPEC_INJECT:
        return run_spec_inject(request, freshness)
    if request.command == Command.SPEC_REALIGN:
        return run_spec_realign(request, freshness)

    return error_envelope(
        "unsupported_command",
        f"Unsupported command: {request.command}",
        {"command": request.command},
    )


def load_project_config(project_root: Path) -> dict[str, Any] | ResultEnvelope:
    config_path = project_root / ".spec-grag" / "config.toml"
    if not config_path.exists():
        return error_envelope(
            "config_missing",
            ".spec-grag/config.toml is required",
            {"project_root": str(project_root), "config_path": str(config_path)},
        )

    try:
        with config_path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        return error_envelope(
            "config_invalid",
            ".spec-grag/config.toml is not valid TOML",
            {"config_path": str(config_path), "message": str(exc)},
        )


def graph_storage_path(project_root: Path, config: dict[str, Any]) -> str:
    configured = config.get("graph", {}).get("storage", ".spec-grag/graph/")
    path = Path(configured)
    if not path.is_absolute():
        path = project_root / path
    return str(path)


def freshness_report(graph_storage: str) -> FreshnessReport:
    now = datetime.now(UTC).isoformat()
    return FreshnessReport(
        last_core_run=now,
        graph_revision=None,
        graph_storage_path=graph_storage,
        source_manifest_path=str(Path(graph_storage) / "source_manifest.json"),
        warnings=[],
    )


def run_spec_core(
    request: SlashCommandRequest, graph_storage: str, freshness: FreshnessReport
) -> ResultEnvelope:
    warning = "GRAG build is not implemented yet; CLI transport skeleton only."
    payload = CoreResult(
        mode="full" if request.options.all else "incremental",
        updated_sources=[],
        skipped_sources=[],
        failed_sources=[],
        graph_storage=graph_storage,
        freshness_report=freshness,
        concept_diff=None,
        warnings=[warning],
    )
    return ResultEnvelope(
        status=ResultStatus.DEGRADED,
        result_type=ResultType.CORE_RESULT,
        payload=payload,
        execution=ExecutionMetadata(context_ready=False, degraded_components=["grag_builder"]),
        warnings=[warning],
    )


def run_spec_inject(request: SlashCommandRequest, freshness: FreshnessReport) -> ResultEnvelope:
    warning = "InjectionContext classification is not implemented yet; empty context returned."
    payload = make_injection_context(request.conversation_context, freshness, [warning])
    return ResultEnvelope(
        status=ResultStatus.DEGRADED,
        result_type=ResultType.INJECTION_CONTEXT,
        payload=payload,
        execution=ExecutionMetadata(context_ready=True, degraded_components=["retrieval"]),
        warnings=[warning],
    )


def run_spec_realign(request: SlashCommandRequest, freshness: FreshnessReport) -> ResultEnvelope:
    warning = "Answer generation is not implemented yet; placeholder answer returned."
    injection_context = make_injection_context(request.conversation_context, freshness, [warning])
    payload = RealignResult(
        task_prompt=request.task_prompt or "",
        injection_context=injection_context,
        answer=(
            "今回の回答で守る制約: 未実装\n"
            "今回の回答で扱う修正候補または検討対象: 未実装\n"
            "競合 / 不確実性 / 人間レビューが必要な点: Answer generation is not implemented yet.\n"
            "課題プロンプトへの回答または修正案: 未実装"
        ),
    )
    return ResultEnvelope(
        status=ResultStatus.DEGRADED,
        result_type=ResultType.REALIGN_RESULT,
        payload=payload,
        execution=ExecutionMetadata(context_ready=True, degraded_components=["answer_llm"]),
        warnings=[warning],
    )


def make_injection_context(
    conversation_context: ConversationContext,
    freshness: FreshnessReport,
    warnings: list[str],
) -> InjectionContext:
    return InjectionContext(
        conversation_context_summary=conversation_context.current_user_message,
        freshness_report=freshness,
        warnings=warnings,
    )


def error_envelope(
    error_code: str, message: str, details: dict[str, Any] | None = None
) -> ResultEnvelope:
    payload = ErrorResult(error_code=error_code, message=message, details=details or {})
    return ResultEnvelope(
        status=ResultStatus.FAILED,
        result_type=ResultType.ERROR_RESULT,
        payload=payload,
        execution=ExecutionMetadata(context_ready=False),
        warnings=[message],
    )


if __name__ == "__main__":
    raise SystemExit(main())
