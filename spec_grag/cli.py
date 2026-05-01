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

from spec_grag.config import ConfigPolicyError, validate_project_config
from spec_grag.concept_index import refresh_concept_index
from spec_grag.concept_diff import (
    ConceptApplyStatus,
    ConceptDiffError,
    ConceptPatchApplyError,
    HunkStatus,
    accept_hunk,
    apply_pending_concept_diff,
    load_pending_concept_diff,
    parse_hunk_ref,
    pending_concept_diff_path,
    reject_hunk,
    revise_hunk,
    write_pending_concept_diff_atomic,
)
from spec_grag.core import run_core_update
from spec_grag.injection import ClassificationError, InjectionBuild, build_injection
from spec_grag.protocol import (
    Command,
    ConceptApprovalRequiredResult,
    CoreResult,
    ErrorResult,
    ExecutionMetadata,
    FreshnessReport,
    InjectionContext,
    NeedMoreContextResult,
    RealignResult,
    ResultEnvelope,
    ResultStatus,
    ResultType,
    SlashCommandRequest,
    validation_error_to_details,
)
from spec_grag.realign import (
    AnswerGenerationError,
    AnswerNeedsMoreContext,
    answer_failure_fallback_from_config,
    generate_realign_answer,
    make_answer_llm_from_config,
)
from spec_grag.run_artifacts import maybe_write_run_artifact


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
        envelope = run_spec_core(request, project_root, config, graph_storage, freshness)
        return with_run_artifact(project_root, config, request, envelope)
    if request.command == Command.SPEC_INJECT:
        envelope = run_spec_inject(request, project_root, config, freshness)
        return with_run_artifact(project_root, config, request, envelope)
    if request.command == Command.SPEC_REALIGN:
        envelope = run_spec_realign(request, project_root, config, freshness)
        return with_run_artifact(project_root, config, request, envelope)

    return error_envelope(
        "unsupported_command",
        f"Unsupported command: {request.command}",
        {"command": request.command},
    )


def with_run_artifact(
    project_root: Path,
    config: dict[str, Any],
    request: SlashCommandRequest,
    envelope: ResultEnvelope,
) -> ResultEnvelope:
    try:
        artifact_path = maybe_write_run_artifact(
            project_root=project_root,
            config=config,
            request=request,
            envelope=envelope,
        )
    except Exception as exc:
        warnings = [*envelope.warnings, f"run_artifact_write_failed:{exc}"]
        return envelope.model_copy(update={"warnings": warnings})
    if artifact_path is None:
        return envelope
    warnings = [*envelope.warnings, f"run_artifact:{artifact_path}"]
    return envelope.model_copy(update={"warnings": warnings})


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
            config = tomllib.load(f)
        return validate_project_config(config)
    except tomllib.TOMLDecodeError as exc:
        return error_envelope(
            "config_invalid",
            ".spec-grag/config.toml is not valid TOML",
            {"config_path": str(config_path), "message": str(exc)},
        )
    except ValidationError as exc:
        return error_envelope(
            "config_invalid",
            ".spec-grag/config.toml does not match the SPEC-grag config schema",
            {
                "config_path": str(config_path),
                **validation_error_to_details(exc),
            },
        )
    except ConfigPolicyError as exc:
        return error_envelope(
            "config_invalid",
            ".spec-grag/config.toml violates the SPEC-grag production policy",
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
    request: SlashCommandRequest,
    project_root: Path,
    config: dict[str, Any],
    graph_storage: str,
    freshness: FreshnessReport,
) -> ResultEnvelope:
    concept_operation = run_concept_diff_operation(
        request,
        project_root,
        config,
        graph_storage,
        freshness,
    )
    if concept_operation is not None:
        return concept_operation

    pending_diff = first_unresolved_pending_concept_diff(project_root / ".spec-grag" / "pending")
    if pending_diff is not None:
        return concept_diff_blocked_envelope(
            pending_diff,
            freshness,
            "pending_concept_diff_unresolved",
        )

    update = run_core_update(project_root, config, all_sources=request.options.all)
    if update.status == ResultStatus.FAILED:
        return error_envelope(
            "spec_core_failed",
            "SPEC-grag core update failed",
            {
                "failed_sources": update.failed_sources,
                "warnings": update.warnings,
            },
        )

    payload = CoreResult(
        mode=update.mode,
        updated_sources=update.updated_sources,
        skipped_sources=update.skipped_sources,
        failed_sources=update.failed_sources,
        graph_storage=update.graph_storage,
        freshness_report=update.freshness_report,
        concept_diff=update.concept_diff,
        warnings=update.warnings,
    )
    return ResultEnvelope(
        status=update.status,
        result_type=ResultType.CORE_RESULT,
        payload=payload,
        execution=ExecutionMetadata(
            context_ready=False,
            pending_concept_diff_id=update.pending_concept_diff_id,
            failed_sources=update.failed_sources,
            degraded_components=["extraction"]
            if update.status == ResultStatus.DEGRADED
            else [],
        ),
        warnings=update.warnings,
    )


def run_concept_diff_operation(
    request: SlashCommandRequest,
    project_root: Path,
    config: dict[str, Any],
    graph_storage: str,
    freshness: FreshnessReport,
) -> ResultEnvelope | None:
    options = request.options
    pending_dir = project_root / ".spec-grag" / "pending"

    try:
        if options.accept is not None:
            diff_id, hunk_id = parse_hunk_ref(options.accept)
            path = pending_concept_diff_path(pending_dir, diff_id)
            diff = accept_hunk(load_pending_concept_diff(path), hunk_id)
            write_pending_concept_diff_atomic(path, diff)
            return concept_diff_updated_envelope(diff, graph_storage, freshness, "accepted")

        if options.reject is not None:
            diff_id, hunk_id = parse_hunk_ref(options.reject)
            path = pending_concept_diff_path(pending_dir, diff_id)
            diff = reject_hunk(load_pending_concept_diff(path), hunk_id)
            write_pending_concept_diff_atomic(path, diff)
            return concept_diff_updated_envelope(diff, graph_storage, freshness, "rejected")

        if options.revise is not None:
            diff_id, hunk_id = parse_hunk_ref(options.revise)
            path = pending_concept_diff_path(pending_dir, diff_id)
            diff = revise_hunk(
                load_pending_concept_diff(path),
                hunk_id,
                options.revision_instruction or "",
            )
            write_pending_concept_diff_atomic(path, diff)
            return concept_diff_updated_envelope(diff, graph_storage, freshness, "revised")

        if options.apply is not None:
            diff_id = options.apply
            path = pending_concept_diff_path(pending_dir, diff_id)
            diff = load_pending_concept_diff(path)
            concept_path = concept_file_path(project_root, config)
            if concept_path is None:
                return error_envelope(
                    "concept_file_missing",
                    "core.concept_file is required to apply Concept diff",
                    {"project_root": str(project_root)},
                )
            if not concept_path.exists():
                return error_envelope(
                    "concept_file_missing",
                    "Configured Concept file does not exist",
                    {"concept_file": str(concept_path)},
                )
            apply_result = apply_pending_concept_diff(
                diff,
                concept_path,
                remove_pending_path=path,
            )
            if apply_result.status == ConceptApplyStatus.BLOCKED:
                return concept_diff_blocked_envelope(
                    diff,
                    freshness,
                    apply_result.blocked_reason or "concept_diff_apply_blocked",
                )
            concept_index, concept_index_warnings = refresh_concept_index(
                project_root,
                config,
                Path(graph_storage),
            )
            payload = CoreResult(
                mode="incremental",
                updated_sources=[str(concept_path)],
                skipped_sources=[],
                failed_sources=[],
                graph_storage=graph_storage,
                freshness_report=freshness,
                concept_diff=apply_result.model_dump(mode="json"),
                warnings=concept_index_warnings,
            )
            return ResultEnvelope(
                status=ResultStatus.OK,
                result_type=ResultType.CORE_RESULT,
                payload=payload,
                execution=ExecutionMetadata(
                    context_ready=False,
                    pending_concept_diff_id=None,
                ),
                warnings=concept_index_warnings,
            )
    except (ValueError, ConceptDiffError, ConceptPatchApplyError) as exc:
        return error_envelope(
            "concept_diff_operation_failed",
            str(exc),
            {"project_root": str(project_root)},
        )

    return None


def concept_diff_updated_envelope(
    diff: Any,
    graph_storage: str,
    freshness: FreshnessReport,
    action: str,
) -> ResultEnvelope:
    payload = CoreResult(
        mode="incremental",
        updated_sources=[],
        skipped_sources=[],
        failed_sources=[],
        graph_storage=graph_storage,
        freshness_report=freshness,
        concept_diff=diff.model_dump(mode="json"),
        warnings=[f"Concept diff hunk {action}; apply is still required."],
    )
    return ResultEnvelope(
        status=ResultStatus.OK,
        result_type=ResultType.CORE_RESULT,
        payload=payload,
        execution=ExecutionMetadata(
            context_ready=False,
            pending_concept_diff_id=diff.diff_id,
        ),
        warnings=payload.warnings,
    )


def concept_diff_blocked_envelope(
    diff: Any,
    freshness: FreshnessReport,
    warning: str,
) -> ResultEnvelope:
    payload = ConceptApprovalRequiredResult(
        task_prompt=diff.task_context.task_prompt,
        concept_diff=diff.model_dump(mode="json"),
        warnings=[warning],
    )
    return ResultEnvelope(
        status=ResultStatus.BLOCKED,
        result_type=ResultType.CONCEPT_APPROVAL_REQUIRED_RESULT,
        payload=payload,
        execution=ExecutionMetadata(
            context_ready=False,
            pending_concept_diff_id=diff.diff_id,
        ),
        warnings=[warning],
    )


def first_unresolved_pending_concept_diff(pending_dir: Path) -> Any | None:
    if not pending_dir.exists():
        return None
    for path in sorted(pending_dir.glob("concept_diff_*.json")):
        try:
            diff = load_pending_concept_diff(path)
        except ConceptDiffError:
            continue
        if any(
            hunk.status in {HunkStatus.PENDING, HunkStatus.ACCEPTED, HunkStatus.REVISED}
            for hunk in diff.hunks
        ):
            return diff
    return None


def concept_file_path(project_root: Path, config: dict[str, Any]) -> Path | None:
    configured = config.get("core", {}).get("concept_file")
    if not configured:
        return None
    path = Path(configured)
    if not path.is_absolute():
        path = project_root / path
    return path


def run_spec_inject(
    request: SlashCommandRequest,
    project_root: Path,
    config: dict[str, Any],
    freshness: FreshnessReport,
) -> ResultEnvelope:
    pending_diff = first_unresolved_pending_concept_diff(project_root / ".spec-grag" / "pending")
    if pending_diff is not None:
        return concept_diff_blocked_envelope(
            pending_diff,
            freshness,
            "pending_concept_diff_unresolved",
        )

    try:
        build = build_injection(project_root, config, request)
    except (ClassificationError, ValidationError, ValueError, RuntimeError) as exc:
        return context_build_failed_envelope(exc)
    return injection_build_envelope(build)


def run_spec_realign(
    request: SlashCommandRequest,
    project_root: Path,
    config: dict[str, Any],
    freshness: FreshnessReport,
) -> ResultEnvelope:
    pending_diff = first_unresolved_pending_concept_diff(project_root / ".spec-grag" / "pending")
    if pending_diff is not None:
        return concept_diff_blocked_envelope(
            pending_diff,
            freshness,
            "pending_concept_diff_unresolved",
        )

    try:
        build = build_injection(project_root, config, request)
    except (ClassificationError, ValidationError, ValueError, RuntimeError) as exc:
        return context_build_failed_envelope(exc)
    if (
        build.status not in {ResultStatus.OK, ResultStatus.DEGRADED}
        or not build.context_ready
        or not isinstance(build.payload, InjectionContext)
    ):
        return injection_build_envelope(build)

    task_prompt = request.task_prompt or ""
    try:
        answer_llm = make_answer_llm_from_config(config)
        answer = generate_realign_answer(task_prompt, build.payload, llm=answer_llm)
    except ValueError as exc:
        return error_envelope(
            "answer_config_invalid",
            "Answer provider configuration is invalid",
            {"message": str(exc)},
        )
    except AnswerNeedsMoreContext as exc:
        payload = NeedMoreContextResult(
            task_prompt=task_prompt,
            search_requests=[],
            current_partial_context_summary=(
                "Answer phase reported missing context: "
                + "; ".join(exc.missing_context)
            ),
        )
        warnings = [*build.warnings, "answer_needs_more_context"]
        return ResultEnvelope(
            status=ResultStatus.BLOCKED,
            result_type=ResultType.NEED_MORE_CONTEXT_RESULT,
            payload=payload,
            execution=ExecutionMetadata(
                context_ready=False,
                failed_sources=build.failed_sources,
                degraded_components=[*build.degraded_components, "answer"],
            ),
            warnings=warnings,
        )
    except AnswerGenerationError as exc:
        if answer_failure_fallback_from_config(config) == "template":
            answer = generate_realign_answer(task_prompt, build.payload, llm=None)
            warnings = [
                *build.warnings,
                "answer_generation_fallback_template",
                str(exc),
            ]
            payload = RealignResult(
                task_prompt=task_prompt,
                injection_context=build.payload,
                answer=answer,
            )
            return ResultEnvelope(
                status=ResultStatus.DEGRADED,
                result_type=ResultType.REALIGN_RESULT,
                payload=payload,
                execution=ExecutionMetadata(
                    context_ready=True,
                    failed_sources=build.failed_sources,
                    degraded_components=[
                        *build.degraded_components,
                        "answer",
                    ],
                ),
                warnings=warnings,
            )
        return error_envelope(
            "answer_generation_failed",
            "Answer generation failed",
            {"message": str(exc), "warnings": build.warnings},
        )

    payload = RealignResult(
        task_prompt=task_prompt,
        injection_context=build.payload,
        answer=answer,
    )
    return ResultEnvelope(
        status=build.status,
        result_type=ResultType.REALIGN_RESULT,
        payload=payload,
        execution=ExecutionMetadata(
            context_ready=True,
            failed_sources=build.failed_sources,
            degraded_components=build.degraded_components,
        ),
        warnings=build.warnings,
    )


def context_build_failed_envelope(exc: Exception) -> ResultEnvelope:
    return error_envelope(
        "context_build_failed",
        "Injection context build failed",
        {"message": str(exc)},
    )


def injection_build_envelope(build: InjectionBuild) -> ResultEnvelope:
    return ResultEnvelope(
        status=build.status,
        result_type=build.result_type,
        payload=build.payload,
        execution=ExecutionMetadata(
            context_ready=build.context_ready,
            failed_sources=build.failed_sources,
            degraded_components=build.degraded_components,
        ),
        warnings=build.warnings,
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
