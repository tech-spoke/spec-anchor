"""Minimal SPEC-grag CLI transport skeleton."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from spec_grag.config import (
    ConfigPolicyError,
    ExecutionRole,
    RuntimePolicy,
    resolve_runtime_policy,
    validate_project_config,
)
from spec_grag.concept_index import (
    generate_queued_concept_diff_candidate,
    refresh_concept_index,
)
from spec_grag.concept_diff import (
    ConceptApplyStatus,
    ConceptDiffError,
    ConceptPatchApplyError,
    accept_hunk,
    apply_pending_concept_diff,
    first_unresolved_pending_concept_diff,
    load_pending_concept_diff,
    parse_hunk_ref,
    pending_concept_diff_path,
    regenerate_revised_hunks,
    reject_hunk,
    revise_hunk,
    write_pending_concept_diff_atomic,
)
from spec_grag.conflict_review import (
    ConflictCandidateStatus,
    ConflictReviewError,
    apply_pending_conflict_review,
    first_unresolved_pending_conflict_review,
    load_pending_conflict_review,
    pending_conflict_review_path,
    update_conflict_candidate_status,
    write_pending_conflict_review_atomic,
)
from spec_grag.core import run_core_update
from spec_grag.injection import ClassificationError, InjectionBuild, build_injection
from spec_grag.protocol import (
    ApprovalDecision,
    Command,
    ConceptApprovalRequiredResult,
    ConflictApprovalRequiredResult,
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
from spec_grag.readiness import (
    ReadinessReport,
    evaluate_grag_readiness,
    freshness_with_readiness,
)
from spec_grag.realign import (
    AnswerGenerationError,
    AnswerNeedsMoreContext,
    answer_failure_fallback_from_config,
    generate_realign_answer,
    make_answer_llm_from_config,
)
from spec_grag.run_artifacts import maybe_write_run_artifact
from spec_grag.timing import (
    TimingRecorder,
    llm_config_metrics,
)
from spec_grag.watch_state import clear_provisional_concept_cache


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
    timer = TimingRecorder()
    project_root = Path(request.project_root).expanduser().resolve()
    with timer.stage("config_load") as stage:
        config_result = load_project_config(project_root)
        if isinstance(config_result, ResultEnvelope):
            stage.set_status("failed")
    if isinstance(config_result, ResultEnvelope):
        return with_timing_diagnostics(config_result, timer)

    config = config_result
    graph_storage = graph_storage_path(project_root, config)
    freshness = freshness_report(graph_storage)
    runtime_policy = resolve_runtime_policy(
        config,
        execution_role=ExecutionRole.FOREGROUND_HUMAN,
    )

    approval_envelope = run_approval_transport_operation(
        request,
        project_root,
        config,
        graph_storage,
        freshness,
    )
    if approval_envelope is not None:
        approval_envelope = with_runtime_policy(approval_envelope, runtime_policy)
        approval_envelope = with_timing_diagnostics(approval_envelope, timer)
        return with_run_artifact(
            project_root,
            config,
            request,
            approval_envelope,
        )

    if request.command == Command.SPEC_CORE:
        envelope = run_spec_core(
            request,
            project_root,
            config,
            graph_storage,
            freshness,
            runtime_policy,
            timer=timer,
        )
        envelope = with_runtime_policy(envelope, runtime_policy)
        envelope = with_timing_diagnostics(envelope, timer)
        return with_run_artifact(
            project_root,
            config,
            request,
            envelope,
        )
    if request.command == Command.SPEC_INJECT:
        envelope = run_spec_inject(
            request,
            project_root,
            config,
            freshness,
            runtime_policy,
            timer=timer,
        )
        envelope = with_runtime_policy(envelope, runtime_policy)
        envelope = with_timing_diagnostics(envelope, timer)
        return with_run_artifact(
            project_root,
            config,
            request,
            envelope,
        )
    if request.command == Command.SPEC_REALIGN:
        envelope = run_spec_realign(
            request,
            project_root,
            config,
            freshness,
            runtime_policy,
            timer=timer,
        )
        envelope = with_runtime_policy(envelope, runtime_policy)
        envelope = with_timing_diagnostics(envelope, timer)
        return with_run_artifact(
            project_root,
            config,
            request,
            envelope,
        )

    return with_timing_diagnostics(
        error_envelope(
            "unsupported_command",
            f"Unsupported command: {request.command}",
            {"command": request.command},
        ),
        timer,
    )


def run_approval_transport_operation(
    request: SlashCommandRequest,
    project_root: Path,
    config: dict[str, Any],
    graph_storage: str,
    freshness: FreshnessReport,
) -> ResultEnvelope | None:
    approval = request.options.approval
    if approval is None:
        return None
    if approval.subject == "concept_diff":
        return run_concept_diff_operation(
            request,
            project_root,
            config,
            graph_storage,
            freshness,
        )
    if approval.subject == "conflict_candidate":
        return run_conflict_review_operation(
            request,
            graph_storage,
            freshness,
        )
    return None


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


def with_runtime_policy(
    envelope: ResultEnvelope,
    runtime_policy: RuntimePolicy,
) -> ResultEnvelope:
    execution = envelope.execution.model_copy(
        update={"runtime_policy": runtime_policy.as_artifact()}
    )
    return envelope.model_copy(update={"execution": execution})


def with_timing_diagnostics(
    envelope: ResultEnvelope,
    timer: TimingRecorder,
) -> ResultEnvelope:
    execution = envelope.execution.model_copy(
        update={
            "timing_summary": timer.summary(status=envelope.status.value),
            "stage_timings": timer.stage_timings(),
        }
    )
    return envelope.model_copy(update={"execution": execution})


def record_readiness_metrics(
    metrics: dict[str, Any],
    readiness: ReadinessReport,
) -> None:
    metrics.update(
        {
            "readiness_status": readiness.status.value
            if hasattr(readiness.status, "value")
            else str(readiness.status),
            "dirty_sections": len(readiness.dirty_section_ids),
            "format_only_sections": len(readiness.format_only_section_ids),
            "queued_sections": len(readiness.queued_section_ids),
            "pending_conflict_candidates": len(readiness.pending_conflict_candidate_ids),
            "pending_concept_diff": readiness.pending_concept_diff_id is not None,
            "watcher_run_state": readiness.watcher_run_state,
        }
    )


def _gate_stage_status(envelope: ResultEnvelope) -> str:
    if envelope.status == ResultStatus.FAILED:
        return "failed"
    if envelope.status == ResultStatus.BLOCKED:
        return "blocked"
    if envelope.status == ResultStatus.DEGRADED:
        return "degraded"
    return "ok"


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


@dataclass(frozen=True)
class ConceptApprovalOperation:
    action: str
    diff_id: str
    hunk_id: str | None = None
    revision_instruction: str | None = None
    auto_apply: bool = False
    from_chat_approval: bool = False


def run_spec_core(
    request: SlashCommandRequest,
    project_root: Path,
    config: dict[str, Any],
    graph_storage: str,
    freshness: FreshnessReport,
    runtime_policy: RuntimePolicy,
    *,
    timer: TimingRecorder | None = None,
) -> ResultEnvelope:
    timer = timer or TimingRecorder()
    with timer.stage("readiness_gate") as stage:
        readiness = evaluate_grag_readiness(
            project_root,
            config,
            runtime_policy=runtime_policy,
        )
        record_readiness_metrics(stage.metrics, readiness)
    freshness = freshness_with_readiness(freshness, readiness)
    conflict_operation = run_conflict_review_operation(
        request,
        graph_storage,
        freshness,
    )
    if conflict_operation is not None:
        return conflict_operation

    concept_operation = run_concept_diff_operation(
        request,
        project_root,
        config,
        graph_storage,
        freshness,
    )
    if concept_operation is not None:
        return concept_operation

    pending_diff = first_unresolved_pending_concept_diff(
        project_root / ".spec-grag" / "pending"
    )
    if pending_diff is not None:
        if runtime_policy.fail_fast_on_pending:
            return readiness_failed_envelope(readiness, "pending_concept_diff_unresolved")
        return concept_diff_blocked_envelope(
            pending_diff,
            freshness,
            "pending_concept_diff_unresolved",
        )
    pending_conflict = first_unresolved_pending_conflict_review(
        project_root / ".spec-grag" / "pending"
    )
    if pending_conflict is not None:
        if runtime_policy.fail_fast_on_pending:
            return readiness_failed_envelope(readiness, "pending_conflict_candidate_unresolved")
        return conflict_review_blocked_envelope(
            pending_conflict,
            freshness,
            "pending_conflict_candidate_unresolved",
        )

    update = run_core_update(
        project_root,
        config,
        all_sources=request.options.all,
        execution_role=runtime_policy.execution_role,
        timer=timer,
    )
    if update.status == ResultStatus.FAILED:
        return error_envelope(
            "spec_core_failed",
            "SPEC-grag core update failed",
            {
                "failed_sources": update.failed_sources,
                "warnings": update.warnings,
            },
        )
    post_readiness = evaluate_grag_readiness(
        project_root,
        config,
        runtime_policy=runtime_policy,
    )
    update_freshness = freshness_with_readiness(
        update.freshness_report,
        post_readiness,
    )
    if update.pending_conflict_review_id and update.pending_concept_diff_id is None:
        pending_conflict = first_unresolved_pending_conflict_review(
            project_root / ".spec-grag" / "pending"
        )
        if pending_conflict is not None:
            return conflict_review_blocked_envelope(
                pending_conflict,
                update_freshness,
                "pending_conflict_candidate_unresolved",
            )

    payload = CoreResult(
        mode=update.mode,
        updated_sources=update.updated_sources,
        skipped_sources=update.skipped_sources,
        failed_sources=update.failed_sources,
        graph_storage=update.graph_storage,
        freshness_report=update_freshness,
        concept_diff=update.concept_diff,
        conflict_review=update.conflict_review,
        warnings=update_freshness.warnings,
    )
    return ResultEnvelope(
        status=update.status,
        result_type=ResultType.CORE_RESULT,
        payload=payload,
        execution=ExecutionMetadata(
            context_ready=False,
            pending_concept_diff_id=update.pending_concept_diff_id,
            pending_conflict_review_id=update.pending_conflict_review_id,
            failed_sources=update.failed_sources,
            degraded_components=["extraction"]
            if update.status == ResultStatus.DEGRADED
            else [],
        ),
        warnings=update_freshness.warnings,
    )


def run_concept_diff_operation(
    request: SlashCommandRequest,
    project_root: Path,
    config: dict[str, Any],
    graph_storage: str,
    freshness: FreshnessReport,
) -> ResultEnvelope | None:
    operation = concept_approval_operation_from_request(request)
    if operation is None:
        return None
    pending_dir = project_root / ".spec-grag" / "pending"

    try:
        if operation.action == "accept":
            path = pending_concept_diff_path(pending_dir, operation.diff_id)
            diff = accept_hunk(
                load_pending_concept_diff(path),
                operation.hunk_id or "",
            )
            write_pending_concept_diff_atomic(path, diff)
            if operation.auto_apply:
                return apply_concept_diff_envelope(
                    diff,
                    path,
                    project_root,
                    config,
                    graph_storage,
                    freshness,
                )
            return concept_diff_updated_envelope(diff, graph_storage, freshness, "accepted")

        if operation.action == "reject":
            path = pending_concept_diff_path(pending_dir, operation.diff_id)
            diff = reject_hunk(
                load_pending_concept_diff(path),
                operation.hunk_id or "",
            )
            write_pending_concept_diff_atomic(path, diff)
            if operation.from_chat_approval:
                return concept_diff_blocked_envelope(
                    diff,
                    freshness,
                    "pending_concept_diff_unresolved",
                )
            return concept_diff_updated_envelope(diff, graph_storage, freshness, "rejected")

        if operation.action == "revise":
            path = pending_concept_diff_path(pending_dir, operation.diff_id)
            diff = revise_hunk(
                load_pending_concept_diff(path),
                operation.hunk_id or "",
                operation.revision_instruction or "",
            )
            concept_path = concept_file_path(project_root, config)
            if concept_path is not None and concept_path.exists():
                diff = regenerate_revised_hunks(diff, concept_path)
            write_pending_concept_diff_atomic(path, diff)
            if operation.from_chat_approval:
                return concept_diff_blocked_envelope(
                    diff,
                    freshness,
                    "concept_diff_revised_requires_approval",
                )
            return concept_diff_updated_envelope(diff, graph_storage, freshness, "revised")

        if operation.action == "apply":
            path = pending_concept_diff_path(pending_dir, operation.diff_id)
            diff = load_pending_concept_diff(path)
            return apply_concept_diff_envelope(
                diff,
                path,
                project_root,
                config,
                graph_storage,
                freshness,
            )
    except (ValueError, ConceptDiffError, ConceptPatchApplyError) as exc:
        return error_envelope(
            "concept_diff_operation_failed",
            str(exc),
            {"project_root": str(project_root)},
        )

    return None


def concept_approval_operation_from_request(
    request: SlashCommandRequest,
) -> ConceptApprovalOperation | None:
    approval = request.options.approval
    if approval is not None:
        if approval.subject != "concept_diff":
            return None
        return ConceptApprovalOperation(
            action=approval.action,
            diff_id=approval.diff_id or "",
            hunk_id=approval.hunk_id,
            revision_instruction=approval.revision_instruction,
            auto_apply=approval.apply and approval.action == "accept",
            from_chat_approval=True,
        )
    options = request.options
    if options.accept is not None:
        diff_id, hunk_id = parse_hunk_ref(options.accept)
        return ConceptApprovalOperation("accept", diff_id, hunk_id)
    if options.reject is not None:
        diff_id, hunk_id = parse_hunk_ref(options.reject)
        return ConceptApprovalOperation("reject", diff_id, hunk_id)
    if options.revise is not None:
        diff_id, hunk_id = parse_hunk_ref(options.revise)
        return ConceptApprovalOperation(
            "revise",
            diff_id,
            hunk_id,
            revision_instruction=options.revision_instruction,
        )
    if options.apply is not None:
        return ConceptApprovalOperation("apply", options.apply)
    return None


def apply_concept_diff_envelope(
    diff: Any,
    path: Path,
    project_root: Path,
    config: dict[str, Any],
    graph_storage: str,
    freshness: FreshnessReport,
) -> ResultEnvelope:
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
    clear_provisional_concept_cache(project_root)
    queued_result = generate_queued_concept_diff_candidate(
        project_root=project_root,
        config=config,
        graph_storage=Path(graph_storage),
        extract_run_id=f"queued-{diff.diff_id}",
        generated_at=datetime.now(UTC).isoformat(),
    )
    concept_payload: dict[str, Any] = apply_result.model_dump(mode="json")
    pending_concept_diff_id = None
    if queued_result.pending_diff is not None:
        concept_payload = queued_result.pending_diff.model_dump(mode="json")
        pending_concept_diff_id = queued_result.pending_diff.diff_id
    warnings = [
        *concept_index_warnings,
        *queued_result.warnings,
    ]
    if queued_result.pending_diff is not None:
        warnings.append("queued_concept_diff_created")
    payload = CoreResult(
        mode="incremental",
        updated_sources=[str(concept_path)],
        skipped_sources=[],
        failed_sources=[],
        graph_storage=graph_storage,
        freshness_report=freshness,
        concept_diff=concept_payload,
        warnings=warnings,
    )
    return ResultEnvelope(
        status=ResultStatus.OK,
        result_type=ResultType.CORE_RESULT,
        payload=payload,
        execution=ExecutionMetadata(
            context_ready=False,
            pending_concept_diff_id=pending_concept_diff_id,
        ),
        warnings=warnings,
    )


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
        approval_prompt=concept_approval_prompt(diff),
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


def concept_approval_prompt(diff: Any) -> dict[str, Any]:
    return {
        "kind": "concept_diff",
        "title": "Concept diff approval required",
        "summary": "Review each Concept hunk before SPEC-grag can use it downstream.",
        "choices": [
            {"action": "accept", "label": "承認"},
            {"action": "revise", "label": "修正指示"},
            {"action": "reject", "label": "非承認"},
        ],
        "items": [
            {
                "diff_id": diff.diff_id,
                "hunk_id": hunk.hunk_id,
                "file": hunk.file,
                "status": hunk.status.value
                if hasattr(hunk.status, "value")
                else str(hunk.status),
                "diff_text": hunk.diff_text,
                "revision_history": list(getattr(hunk, "revision_history", [])),
                "transport": {
                    "accept": {
                        "approval": {
                            "subject": "concept_diff",
                            "action": "accept",
                            "diff_id": diff.diff_id,
                            "hunk_id": hunk.hunk_id,
                            "apply": True,
                        }
                    },
                    "reject": {
                        "approval": {
                            "subject": "concept_diff",
                            "action": "reject",
                            "diff_id": diff.diff_id,
                            "hunk_id": hunk.hunk_id,
                        }
                    },
                    "revise": {
                        "approval": {
                            "subject": "concept_diff",
                            "action": "revise",
                            "diff_id": diff.diff_id,
                            "hunk_id": hunk.hunk_id,
                            "revision_instruction": "<instruction>",
                        }
                    },
                },
            }
            for hunk in diff.hunks
        ],
    }


def run_conflict_review_operation(
    request: SlashCommandRequest,
    graph_storage: str,
    freshness: FreshnessReport,
) -> ResultEnvelope | None:
    approval = request.options.approval
    if approval is None or approval.subject != "conflict_candidate":
        return None
    pending_dir = Path(request.project_root).expanduser().resolve() / ".spec-grag" / "pending"

    try:
        path = pending_conflict_review_path(pending_dir, approval.review_id or "")
        review = load_pending_conflict_review(path)
        if approval.action == "apply":
            return apply_conflict_review_envelope(review, path, graph_storage, freshness)

        status_by_action = {
            "accept": ConflictCandidateStatus.ACCEPTED,
            "reject": ConflictCandidateStatus.REJECTED,
            "defer": ConflictCandidateStatus.DEFERRED,
            "revise": ConflictCandidateStatus.REVISED,
        }
        status = status_by_action.get(approval.action)
        if status is None:
            return error_envelope(
                "conflict_review_operation_failed",
                f"Unsupported Conflict approval action: {approval.action}",
                {"review_id": approval.review_id},
            )
        review = update_conflict_candidate_status(
            review,
            approval.candidate_id or "",
            status,
            revision_instruction=approval.revision_instruction,
        )
        write_pending_conflict_review_atomic(path, review)
        if approval.apply and status in {
            ConflictCandidateStatus.ACCEPTED,
            ConflictCandidateStatus.REJECTED,
        }:
            return apply_conflict_review_envelope(review, path, graph_storage, freshness)
        return conflict_review_blocked_envelope(
            review,
            freshness,
            "pending_conflict_candidate_unresolved",
        )
    except (ValueError, ConflictReviewError) as exc:
        return error_envelope(
            "conflict_review_operation_failed",
            str(exc),
            {"project_root": request.project_root},
        )


def apply_conflict_review_envelope(
    review: Any,
    path: Path,
    graph_storage: str,
    freshness: FreshnessReport,
) -> ResultEnvelope:
    apply_result = apply_pending_conflict_review(
        review,
        Path(graph_storage),
        remove_pending_path=path,
    )
    warnings = []
    if apply_result.pending_candidate_ids:
        warnings.append("pending_conflict_candidate_unresolved")
    payload = CoreResult(
        mode="incremental",
        updated_sources=[],
        skipped_sources=[],
        failed_sources=[],
        graph_storage=graph_storage,
        freshness_report=freshness,
        conflict_review=apply_result.model_dump(mode="json"),
        warnings=warnings,
    )
    return ResultEnvelope(
        status=ResultStatus.OK if not apply_result.pending_candidate_ids else ResultStatus.BLOCKED,
        result_type=ResultType.CORE_RESULT
        if not apply_result.pending_candidate_ids
        else ResultType.CONFLICT_APPROVAL_REQUIRED_RESULT,
        payload=payload
        if not apply_result.pending_candidate_ids
        else ConflictApprovalRequiredResult(
            task_prompt=None,
            conflict_review=review.model_dump(mode="json"),
            approval_prompt=conflict_approval_prompt(review),
            warnings=warnings,
        ),
        execution=ExecutionMetadata(
            context_ready=False,
            pending_conflict_review_id=review.review_id
            if apply_result.pending_candidate_ids
            else None,
            pending_conflict_candidate_ids=apply_result.pending_candidate_ids,
        ),
        warnings=warnings,
    )


def conflict_review_blocked_envelope(
    review: Any,
    freshness: FreshnessReport,
    warning: str,
) -> ResultEnvelope:
    pending_ids = [
        candidate.candidate_id
        for candidate in review.candidates
        if str(candidate.status) in {
            "pending",
            "accepted",
            "rejected",
            "deferred",
            "revised",
        }
    ]
    payload = ConflictApprovalRequiredResult(
        task_prompt=None,
        conflict_review=review.model_dump(mode="json"),
        approval_prompt=conflict_approval_prompt(review),
        warnings=[warning],
    )
    return ResultEnvelope(
        status=ResultStatus.BLOCKED,
        result_type=ResultType.CONFLICT_APPROVAL_REQUIRED_RESULT,
        payload=payload,
        execution=ExecutionMetadata(
            context_ready=False,
            pending_conflict_review_id=review.review_id,
            pending_conflict_candidate_ids=pending_ids,
        ),
        warnings=[warning],
    )


def conflict_approval_prompt(review: Any) -> dict[str, Any]:
    return {
        "kind": "conflict_review",
        "title": "Conflict candidate approval required",
        "summary": "Review each Conflict candidate before it can become a ConflictNote.",
        "choices": [
            {"action": "accept", "label": "承認"},
            {"action": "revise", "label": "修正指示"},
            {"action": "reject", "label": "非承認"},
            {"action": "defer", "label": "保留"},
        ],
        "items": [
            {
                "review_id": review.review_id,
                "candidate_id": candidate.candidate_id,
                "status": candidate.status.value
                if hasattr(candidate.status, "value")
                else str(candidate.status),
                "conflict_type": candidate.conflict_type,
                "severity": candidate.severity,
                "summary": candidate.summary,
                "reason": candidate.reason,
                "evidence_spans": candidate.evidence_spans,
                "transport": {
                    "accept": {
                        "approval": {
                            "subject": "conflict_candidate",
                            "action": "accept",
                            "review_id": review.review_id,
                            "candidate_id": candidate.candidate_id,
                            "apply": True,
                        }
                    },
                    "reject": {
                        "approval": {
                            "subject": "conflict_candidate",
                            "action": "reject",
                            "review_id": review.review_id,
                            "candidate_id": candidate.candidate_id,
                            "apply": True,
                        }
                    },
                    "defer": {
                        "approval": {
                            "subject": "conflict_candidate",
                            "action": "defer",
                            "review_id": review.review_id,
                            "candidate_id": candidate.candidate_id,
                            "apply": False,
                        }
                    },
                    "revise": {
                        "approval": {
                            "subject": "conflict_candidate",
                            "action": "revise",
                            "review_id": review.review_id,
                            "candidate_id": candidate.candidate_id,
                            "revision_instruction": "<instruction>",
                            "apply": False,
                        }
                    },
                },
            }
            for candidate in review.candidates
        ],
    }


def pending_readiness_envelope(
    project_root: Path,
    freshness: FreshnessReport,
    readiness: ReadinessReport,
    runtime_policy: RuntimePolicy,
) -> ResultEnvelope | None:
    if readiness.status != "pending":
        return None
    if runtime_policy.fail_fast_on_pending:
        return readiness_failed_envelope(readiness, "readiness_pending")
    pending_diff = first_unresolved_pending_concept_diff(
        project_root / ".spec-grag" / "pending"
    )
    if pending_diff is not None:
        return concept_diff_blocked_envelope(
            pending_diff,
            freshness,
            "pending_concept_diff_unresolved",
        )
    pending_conflict = first_unresolved_pending_conflict_review(
        project_root / ".spec-grag" / "pending"
    )
    if pending_conflict is not None:
        return conflict_review_blocked_envelope(
            pending_conflict,
            freshness,
            "pending_conflict_candidate_unresolved",
        )
    return readiness_blocked_envelope(readiness, "pending_conflict_candidate_unresolved")


def dirty_or_stale_readiness_envelope(
    readiness: ReadinessReport,
    runtime_policy: RuntimePolicy,
) -> ResultEnvelope | None:
    if readiness.status == "dirty":
        if runtime_policy.fail_fast_on_dirty:
            return readiness_failed_envelope(readiness, "readiness_dirty")
        if runtime_policy.foreground_incremental:
            return None
        reason_codes = {reason.code for reason in readiness.reasons}
        if "watcher_running" in reason_codes:
            return readiness_blocked_envelope(readiness, "watcher_processing")
        if "watch_queue_pending" in reason_codes:
            return readiness_blocked_envelope(readiness, "watcher_queue_pending")
        return readiness_blocked_envelope(readiness, "watcher_waiting_for_dirty_grag")
    if readiness.status == "stale":
        if runtime_policy.fail_fast_on_stale:
            return readiness_failed_envelope(readiness, "readiness_stale")
        if runtime_policy.foreground_incremental:
            return None
        return readiness_blocked_envelope(readiness, "watcher_waiting_for_stale_grag")
    return None


def readiness_failed_envelope(
    readiness: ReadinessReport,
    error_code: str,
) -> ResultEnvelope:
    return error_envelope(
        error_code,
        "GRAG readiness gate failed",
        readiness.as_freshness_payload(),
    )


def readiness_blocked_envelope(
    readiness: ReadinessReport,
    warning: str,
) -> ResultEnvelope:
    payload = ErrorResult(
        error_code=warning,
        message="GRAG is not ready for context generation",
        details=readiness.as_freshness_payload(),
    )
    return ResultEnvelope(
        status=ResultStatus.BLOCKED,
        result_type=ResultType.ERROR_RESULT,
        payload=payload,
        execution=ExecutionMetadata(context_ready=False),
        warnings=[warning],
    )


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
    runtime_policy: RuntimePolicy,
    *,
    timer: TimingRecorder | None = None,
) -> ResultEnvelope:
    timer = timer or TimingRecorder()
    with timer.stage("readiness_gate") as stage:
        readiness = evaluate_grag_readiness(
            project_root,
            config,
            runtime_policy=runtime_policy,
        )
        record_readiness_metrics(stage.metrics, readiness)
        freshness = freshness_with_readiness(freshness, readiness)
        pending_gate = pending_readiness_envelope(project_root, freshness, readiness, runtime_policy)
        if pending_gate is not None:
            stage.set_status(_gate_stage_status(pending_gate))
            return pending_gate

    core_update = None
    if readiness.status in {"dirty", "stale"}:
        with timer.stage("readiness_gate", metrics={"recheck": "dirty_or_stale"}) as stage:
            gate = dirty_or_stale_readiness_envelope(readiness, runtime_policy)
            if gate is not None:
                stage.set_status(_gate_stage_status(gate))
                return gate
        core_update = run_core_update(
            project_root,
            config,
            all_sources=False,
            execution_role=runtime_policy.execution_role,
            timer=timer,
        )
        if core_update.status == ResultStatus.FAILED:
            return error_envelope(
                "spec_core_failed",
                "SPEC-grag core update failed before injection",
                {
                    "failed_sources": core_update.failed_sources,
                    "warnings": core_update.warnings,
                },
            )
        post_readiness = evaluate_grag_readiness(
            project_root,
            config,
            runtime_policy=runtime_policy,
        )
        core_update = replace(
            core_update,
            freshness_report=freshness_with_readiness(
                core_update.freshness_report,
                post_readiness,
            ),
        )

    try:
        build = build_injection(
            project_root,
            config,
            request,
            core_update=core_update,
            freshness_report=None if core_update is not None else freshness,
            timer=timer,
        )
    except (ClassificationError, ValidationError, ValueError, RuntimeError) as exc:
        return context_build_failed_envelope(exc)
    return injection_build_envelope(build)


def run_spec_realign(
    request: SlashCommandRequest,
    project_root: Path,
    config: dict[str, Any],
    freshness: FreshnessReport,
    runtime_policy: RuntimePolicy,
    *,
    timer: TimingRecorder | None = None,
) -> ResultEnvelope:
    timer = timer or TimingRecorder()
    with timer.stage("readiness_gate") as stage:
        readiness = evaluate_grag_readiness(
            project_root,
            config,
            runtime_policy=runtime_policy,
        )
        record_readiness_metrics(stage.metrics, readiness)
        freshness = freshness_with_readiness(freshness, readiness)
        pending_gate = pending_readiness_envelope(project_root, freshness, readiness, runtime_policy)
        if pending_gate is not None:
            stage.set_status(_gate_stage_status(pending_gate))
            return pending_gate

    core_update = None
    if readiness.status in {"dirty", "stale"}:
        with timer.stage("readiness_gate", metrics={"recheck": "dirty_or_stale"}) as stage:
            gate = dirty_or_stale_readiness_envelope(readiness, runtime_policy)
            if gate is not None:
                stage.set_status(_gate_stage_status(gate))
                return gate
        core_update = run_core_update(
            project_root,
            config,
            all_sources=False,
            execution_role=runtime_policy.execution_role,
            timer=timer,
        )
        if core_update.status == ResultStatus.FAILED:
            return error_envelope(
                "spec_core_failed",
                "SPEC-grag core update failed before realign",
                {
                    "failed_sources": core_update.failed_sources,
                    "warnings": core_update.warnings,
                },
            )
        post_readiness = evaluate_grag_readiness(
            project_root,
            config,
            runtime_policy=runtime_policy,
        )
        core_update = replace(
            core_update,
            freshness_report=freshness_with_readiness(
                core_update.freshness_report,
                post_readiness,
            ),
        )

    try:
        build = build_injection(
            project_root,
            config,
            request,
            core_update=core_update,
            freshness_report=None if core_update is not None else freshness,
            timer=timer,
        )
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
        answer_metrics = llm_config_metrics(
            config,
            "answer",
            default_provider="template",
            disabled_providers={"template", "deterministic", "none", "disabled", ""},
        )
        with timer.stage("answer_generation", metrics=answer_metrics) as stage:
            answer_llm = make_answer_llm_from_config(config)
            stage.metrics["llm_calls"] = 0 if answer_llm is None else 1
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
            with timer.stage(
                "answer_generation",
                metrics={"provider": "template", "llm_calls": 0, "fallback": True},
                status="degraded",
            ):
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
