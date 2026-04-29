from __future__ import annotations

import pytest
from pydantic import ValidationError

from spec_grag.protocol import (
    AgentCapabilities,
    Command,
    ConversationContext,
    CoreResult,
    ErrorResult,
    ExecutionMetadata,
    FreshnessReport,
    InjectionContext,
    RealignResult,
    RequestOptions,
    ResultEnvelope,
    ResultStatus,
    ResultType,
    SlashCommandRequest,
)


def sample_freshness() -> FreshnessReport:
    return FreshnessReport(
        last_core_run="2026-04-29T00:00:00+00:00",
        graph_revision="test-revision",
        graph_storage_path=".spec-grag/graph",
        source_manifest_path=".spec-grag/graph/source_manifest.json",
    )


def sample_request(command: Command = Command.SPEC_INJECT) -> SlashCommandRequest:
    return SlashCommandRequest(
        command=command,
        project_root="/tmp/project",
        task_prompt="認証仕様を見直す" if command == Command.SPEC_REALIGN else None,
        conversation_context=ConversationContext(
            current_user_message="認証仕様を見直したい",
            recent_messages=[],
            working_target="docs/spec/auth.md",
            explicit_files=["docs/spec/auth.md"],
        ),
        agent_capabilities=AgentCapabilities(can_read_source=True, can_answer=True),
        options=RequestOptions(output_format="json"),
    )


def test_slash_command_request_roundtrip() -> None:
    request = sample_request()

    encoded = request.model_dump_json()
    decoded = SlashCommandRequest.model_validate_json(encoded)

    assert decoded == request
    assert decoded.command == Command.SPEC_INJECT


def test_spec_realign_requires_task_prompt() -> None:
    with pytest.raises(ValidationError):
        SlashCommandRequest(
            command=Command.SPEC_REALIGN,
            project_root="/tmp/project",
            conversation_context=ConversationContext(current_user_message="相談"),
            agent_capabilities=AgentCapabilities(can_read_source=True, can_answer=True),
        )


def test_result_envelope_roundtrip_core_result() -> None:
    freshness = sample_freshness()
    payload = CoreResult(
        mode="incremental",
        graph_storage=".spec-grag/graph",
        freshness_report=freshness,
    )
    envelope = ResultEnvelope(
        status=ResultStatus.OK,
        result_type=ResultType.CORE_RESULT,
        payload=payload,
        execution=ExecutionMetadata(context_ready=False),
    )

    decoded = ResultEnvelope.from_json(envelope.to_json())

    assert decoded == envelope
    assert isinstance(decoded.payload, CoreResult)


def test_result_envelope_rejects_mismatched_payload_type() -> None:
    with pytest.raises(ValidationError):
        ResultEnvelope(
            status=ResultStatus.FAILED,
            result_type=ResultType.CORE_RESULT,
            payload=ErrorResult(error_code="x", message="wrong payload"),
        )


def test_injection_context_top_level_matches_external_contract() -> None:
    context = InjectionContext(
        conversation_context_summary="summary",
        freshness_report=sample_freshness(),
    )

    assert set(context.model_dump(mode="json").keys()) == {
        "conversation_context_summary",
        "constraint_context",
        "target_context",
        "excluded_as_irrelevant",
        "conflict_notes",
        "review_notes",
        "freshness_report",
        "approved_concept_update",
        "warnings",
    }


def test_realign_result_reuses_injection_context() -> None:
    injection_context = InjectionContext(
        conversation_context_summary="summary",
        freshness_report=sample_freshness(),
    )
    result = RealignResult(
        task_prompt="認証仕様を見直す",
        injection_context=injection_context,
        answer="answer",
    )

    assert result.injection_context == injection_context
    assert set(result.model_dump(mode="json").keys()) == {
        "task_prompt",
        "injection_context",
        "answer",
    }


def test_json_schema_can_be_exported() -> None:
    request_schema = SlashCommandRequest.model_json_schema()
    envelope_schema = ResultEnvelope.model_json_schema()

    assert request_schema["title"] == "SlashCommandRequest"
    assert envelope_schema["title"] == "ResultEnvelope"
