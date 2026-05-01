"""JSON transport contracts for SPEC-grag slash command integration."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class StrictModel(BaseModel):
    """Base model for transport objects; reject unknown envelope/schema fields."""

    model_config = ConfigDict(extra="forbid")


class Command(StrEnum):
    SPEC_CORE = "spec-core"
    SPEC_INJECT = "spec-inject"
    SPEC_REALIGN = "spec-realign"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ResultStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILED = "failed"


class ResultType(StrEnum):
    CORE_RESULT = "CoreResult"
    INJECTION_CONTEXT = "InjectionContext"
    REALIGN_RESULT = "RealignResult"
    CONCEPT_APPROVAL_REQUIRED_RESULT = "ConceptApprovalRequiredResult"
    CONFLICT_APPROVAL_REQUIRED_RESULT = "ConflictApprovalRequiredResult"
    NEED_MORE_CONTEXT_RESULT = "NeedMoreContextResult"
    ERROR_RESULT = "ErrorResult"


class ExpectedUse(StrEnum):
    CONSTRAINT = "constraint"
    TARGET = "target"
    REVIEW = "review"


class ConversationMessage(StrictModel):
    role: MessageRole
    content: Annotated[str, Field(min_length=1)]


class ConversationContext(StrictModel):
    current_user_message: str
    recent_messages: list[ConversationMessage] = Field(default_factory=list)
    working_target: str | None = None
    explicit_files: list[str] = Field(default_factory=list)


class AgentCapabilities(StrictModel):
    can_read_source: bool
    can_answer: bool


class ApprovalDecision(StrictModel):
    subject: Literal["concept_diff", "conflict_candidate"]
    action: Literal["accept", "reject", "revise", "apply", "defer"]
    diff_id: str | None = None
    hunk_id: str | None = None
    review_id: str | None = None
    candidate_id: str | None = None
    revision_instruction: str | None = None
    apply: bool = True

    @model_validator(mode="after")
    def validate_decision_target(self) -> ApprovalDecision:
        if self.subject == "concept_diff":
            if self.action == "defer":
                raise ValueError("concept_diff approval does not support defer")
            if self.action == "apply":
                if not self.diff_id or self.hunk_id is not None:
                    raise ValueError("concept_diff apply requires diff_id only")
            elif not self.diff_id or not self.hunk_id:
                raise ValueError("concept_diff approval requires diff_id and hunk_id")
            if self.action == "revise" and not self.revision_instruction:
                raise ValueError("revision_instruction is required with revise")
            if self.action != "revise" and self.revision_instruction is not None:
                raise ValueError("revision_instruction requires revise")
            if self.review_id is not None or self.candidate_id is not None:
                raise ValueError("concept_diff approval must not set conflict identifiers")
            return self

        if self.action == "apply":
            if not self.review_id or self.candidate_id is not None:
                raise ValueError("conflict apply requires review_id only")
        elif not self.review_id or not self.candidate_id:
            raise ValueError("conflict approval requires review_id and candidate_id")
        if self.action == "revise" and not self.revision_instruction:
            raise ValueError("revision_instruction is required with revise")
        if self.action != "revise" and self.revision_instruction is not None:
            raise ValueError("revision_instruction requires revise")
        if self.diff_id is not None or self.hunk_id is not None:
            raise ValueError("conflict approval must not set concept identifiers")
        return self


class RequestOptions(StrictModel):
    all: bool = False
    output_format: Literal["json"] = "json"
    accept: str | None = None
    reject: str | None = None
    revise: str | None = None
    revision_instruction: str | None = None
    apply: str | None = None
    approval: ApprovalDecision | None = None

    @model_validator(mode="after")
    def validate_concept_diff_operation(self) -> RequestOptions:
        operations = [
            value
            for value in (self.accept, self.reject, self.revise, self.apply)
            if value is not None
        ]
        if self.approval is not None:
            operations.append(self.approval.subject)
        if len(operations) > 1:
            raise ValueError("only one approval operation may be requested")
        if self.revise is not None and not self.revision_instruction:
            raise ValueError("revision_instruction is required with revise")
        if self.revision_instruction is not None and self.revise is None:
            raise ValueError("revision_instruction requires revise")
        return self


class SearchTarget(StrictModel):
    document_id: str | None = None
    chapter_id: str | None = None
    section_id: str | None = None
    query: str | None = None

    @model_validator(mode="after")
    def require_at_least_one_selector(self) -> SearchTarget:
        if not any((self.document_id, self.chapter_id, self.section_id, self.query)):
            raise ValueError("SearchTarget requires at least one selector")
        return self


class SearchRequest(StrictModel):
    request_id: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)]
    target: SearchTarget
    expected_use: ExpectedUse


class AgenticSearchCandidate(StrictModel):
    request_id: Annotated[str, Field(min_length=1)]
    source_document_id: Annotated[str, Field(min_length=1)]
    source_section_id: str | None = None
    heading_path: str | None = None
    excerpt: Annotated[str, Field(min_length=1)]
    source_span: str | None = None
    reason: Annotated[str, Field(min_length=1)]
    source_hash: str | None = None


class SlashCommandRequest(StrictModel):
    command: Command
    project_root: Annotated[str, Field(min_length=1)]
    task_prompt: str | None = None
    conversation_context: ConversationContext
    agentic_search_candidates: list[AgenticSearchCandidate] = Field(default_factory=list)
    agent_capabilities: AgentCapabilities
    options: RequestOptions = Field(default_factory=RequestOptions)

    @model_validator(mode="after")
    def require_realign_task_prompt(self) -> SlashCommandRequest:
        if self.command == Command.SPEC_REALIGN and not self.task_prompt:
            raise ValueError("spec-realign requires task_prompt")
        return self


class FreshnessReport(StrictModel):
    last_core_run: str | None = None
    graph_revision: str | None = None
    graph_storage_path: str
    source_manifest_path: str | None = None
    readiness_report: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class ConstraintContext(StrictModel):
    purpose_constraints: list[dict[str, Any]] = Field(default_factory=list)
    concept_constraints: list[dict[str, Any]] = Field(default_factory=list)
    source_spec_constraints: list[dict[str, Any]] = Field(default_factory=list)
    chapter_anchor_constraints: list[dict[str, Any]] = Field(default_factory=list)
    classification_notes: list[dict[str, Any]] = Field(default_factory=list)


class TargetContext(StrictModel):
    candidate_targets: list[dict[str, Any]] = Field(default_factory=list)
    related_concepts: list[dict[str, Any]] = Field(default_factory=list)
    related_source_sections: list[dict[str, Any]] = Field(default_factory=list)
    related_chapter_anchors: list[dict[str, Any]] = Field(default_factory=list)
    related_entities: list[dict[str, Any]] = Field(default_factory=list)
    classification_notes: list[dict[str, Any]] = Field(default_factory=list)


class InjectionContext(StrictModel):
    conversation_context_summary: str
    constraint_context: ConstraintContext = Field(default_factory=ConstraintContext)
    target_context: TargetContext = Field(default_factory=TargetContext)
    excluded_as_irrelevant: list[dict[str, Any]] = Field(default_factory=list)
    conflict_notes: list[dict[str, Any]] = Field(default_factory=list)
    review_notes: list[dict[str, Any]] = Field(default_factory=list)
    freshness_report: FreshnessReport
    approved_concept_update: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class RealignResult(StrictModel):
    task_prompt: Annotated[str, Field(min_length=1)]
    injection_context: InjectionContext
    answer: str


class CoreResult(StrictModel):
    mode: Literal["incremental", "full"]
    updated_sources: list[str] = Field(default_factory=list)
    skipped_sources: list[str] = Field(default_factory=list)
    failed_sources: list[str] = Field(default_factory=list)
    graph_storage: str
    freshness_report: FreshnessReport
    concept_diff: dict[str, Any] | None = None
    conflict_review: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class ConceptApprovalRequiredResult(StrictModel):
    task_prompt: str | None = None
    concept_diff: dict[str, Any]
    approval_prompt: dict[str, Any] = Field(default_factory=dict)
    required_actions: list[Literal["accept", "reject", "revise"]] = Field(
        default_factory=lambda: ["accept", "reject", "revise"]
    )
    warnings: list[str] = Field(default_factory=list)


class ConflictApprovalRequiredResult(StrictModel):
    task_prompt: str | None = None
    conflict_review: dict[str, Any]
    approval_prompt: dict[str, Any] = Field(default_factory=dict)
    required_actions: list[Literal["accept", "reject", "defer", "revise"]] = Field(
        default_factory=lambda: ["accept", "reject", "defer", "revise"]
    )
    warnings: list[str] = Field(default_factory=list)


class NeedMoreContextResult(StrictModel):
    task_prompt: str
    search_requests: list[SearchRequest]
    current_partial_context_summary: str


class ErrorResult(StrictModel):
    error_code: Annotated[str, Field(min_length=1)]
    message: Annotated[str, Field(min_length=1)]
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionMetadata(StrictModel):
    context_ready: bool | None = None
    pending_concept_diff_id: str | None = None
    pending_conflict_review_id: str | None = None
    pending_conflict_candidate_ids: list[str] = Field(default_factory=list)
    failed_sources: list[str] = Field(default_factory=list)
    degraded_components: list[str] = Field(default_factory=list)
    runtime_policy: dict[str, Any] = Field(default_factory=dict)


Payload = (
    CoreResult
    | InjectionContext
    | RealignResult
    | ConceptApprovalRequiredResult
    | ConflictApprovalRequiredResult
    | NeedMoreContextResult
    | ErrorResult
)


_PAYLOAD_TYPE_BY_RESULT_TYPE: dict[ResultType, type[BaseModel]] = {
    ResultType.CORE_RESULT: CoreResult,
    ResultType.INJECTION_CONTEXT: InjectionContext,
    ResultType.REALIGN_RESULT: RealignResult,
    ResultType.CONCEPT_APPROVAL_REQUIRED_RESULT: ConceptApprovalRequiredResult,
    ResultType.CONFLICT_APPROVAL_REQUIRED_RESULT: ConflictApprovalRequiredResult,
    ResultType.NEED_MORE_CONTEXT_RESULT: NeedMoreContextResult,
    ResultType.ERROR_RESULT: ErrorResult,
}


class ResultEnvelope(StrictModel):
    status: ResultStatus
    result_type: ResultType
    payload: Payload
    execution: ExecutionMetadata = Field(default_factory=ExecutionMetadata)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def payload_must_match_result_type(self) -> ResultEnvelope:
        expected = _PAYLOAD_TYPE_BY_RESULT_TYPE[self.result_type]
        if not isinstance(self.payload, expected):
            raise ValueError(
                f"payload for {self.result_type.value} must be {expected.__name__}, "
                f"got {type(self.payload).__name__}"
            )
        return self

    def to_json(self, *, indent: int | None = None) -> str:
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, text: str) -> ResultEnvelope:
        return cls.model_validate_json(text)


def validation_error_to_details(exc: ValidationError) -> dict[str, Any]:
    errors = exc.errors(include_url=False)
    return {"errors": json.loads(json.dumps(errors, default=str))}
