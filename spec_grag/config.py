"""Strict project config validation for .spec-grag/config.toml."""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from spec_grag.protocol import StrictModel


SMOKE_ENV_VAR = "SPEC_GRAG_SMOKE"
RUNTIME_MODE_ENV_VAR = "SPEC_GRAG_RUNTIME_MODE"
SMOKE_TRUE_VALUES = {"1", "true", "yes", "on", "smoke"}
RUNTIME_MODES = {"smoke", "local_daily", "ci", "production"}
LLM_PROVIDERS = {"codex", "claude"}
LLM_PROVIDER_TO_STAGE_PROVIDER = {
    "codex_cli": "codex",
    "claude_cli": "claude",
}
STAGE_PROVIDER_TO_LLM_PROVIDER = {
    "codex": "codex_cli",
    "claude": "claude_cli",
}
CODEX_EFFORT_VALUES = ("minimal", "low", "medium", "high", "xhigh")
CLAUDE_EFFORT_VALUES = ("low", "medium", "high", "xhigh", "max")
LLM_EFFORT_VALUES_BY_PROVIDER = {
    "codex_cli": CODEX_EFFORT_VALUES,
    "codex": CODEX_EFFORT_VALUES,
    "claude_cli": CLAUDE_EFFORT_VALUES,
    "claude": CLAUDE_EFFORT_VALUES,
}
LLM_STAGE_SECTIONS = (
    "extraction",
    "answer",
    "classification",
    "concept_diff",
    "community_report",
    "query_planner",
)
GraphRelationType = Literal["DEPENDS_ON", "REFINES", "RELATED_TO", "CONTRASTS_WITH"]
GraphConfidenceThreshold = Literal["low", "medium", "high"]
DEFAULT_GRAPH_RELATION_ALLOWLIST: tuple[GraphRelationType, ...] = (
    "DEPENDS_ON",
    "REFINES",
    "RELATED_TO",
    "CONTRASTS_WITH",
)
DEFAULT_GRAPH_MIN_RELATION_CONFIDENCE: GraphConfidenceThreshold = "medium"
DEFAULT_MAX_GRAPH_ENTITIES = 12
LLM_INHERITED_KEYS = (
    "command",
    "model",
    "effort",
    "timeout_sec",
    "max_retries",
    "retry_backoff_sec",
)


class ConfigPolicyError(ValueError):
    """Raised when a valid config schema violates runtime policy."""


class RuntimeMode(StrEnum):
    SMOKE = "smoke"
    LOCAL_DAILY = "local_daily"
    CI = "ci"
    PRODUCTION = "production"


class ExecutionRole(StrEnum):
    FOREGROUND_HUMAN = "foreground_human"
    BACKGROUND_WATCHER = "background_watcher"
    CI_NO_WATCHER = "ci_no_watcher"
    PRODUCTION = "production"


def smoke_mode_enabled(env: Mapping[str, str] | None = None) -> bool:
    values = env if env is not None else os.environ
    smoke_value = str(values.get(SMOKE_ENV_VAR, "")).strip().lower()
    runtime_value = str(values.get(RUNTIME_MODE_ENV_VAR, "")).strip().lower()
    return smoke_value in SMOKE_TRUE_VALUES or runtime_value == "smoke"


class RuntimePolicy(StrictModel):
    mode: RuntimeMode
    execution_role: ExecutionRole
    watcher_required: bool
    foreground_incremental: bool
    fail_fast_on_dirty: bool
    fail_fast_on_pending: bool
    fail_fast_on_stale: bool

    def as_artifact(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SourcesConfig(StrictModel):
    include: list[str]
    exclude: list[str] = Field(default_factory=list)

    @field_validator("include", "exclude", mode="before")
    @classmethod
    def normalize_patterns(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return value
        raise ValueError("must be a string or list of strings")

    @field_validator("include")
    @classmethod
    def include_must_not_be_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("sources.include must contain at least one pattern")
        return value

    @field_validator("include", "exclude")
    @classmethod
    def patterns_must_be_non_empty_strings(cls, value: list[str]) -> list[str]:
        for pattern in value:
            if not isinstance(pattern, str) or not pattern.strip():
                raise ValueError("source patterns must be non-empty strings")
        return value


class CoreConfig(StrictModel):
    purpose_file: str | None = None
    concept_file: str | None = None
    extraction_mode: Literal["deterministic", "schema_llm", "schema", "llm"] | None = None

    @field_validator("purpose_file", "concept_file")
    @classmethod
    def optional_path_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("path must be a non-empty string")
        return value


class GraphConfig(StrictModel):
    storage: str = ".spec-grag/graph/"

    @field_validator("storage")
    @classmethod
    def storage_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("graph.storage must be a non-empty string")
        return value


class RetryConfig(StrictModel):
    timeout_sec: int = Field(default=120, ge=1, le=3600)
    max_retries: int = Field(default=0, ge=0, le=10)
    retry_backoff_sec: float = Field(default=0.0, ge=0.0, le=60.0)
    repair_on_schema_failure: bool = True
    effort: str | None = None

    @field_validator("effort")
    @classmethod
    def optional_effort_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("effort must be a non-empty string")
        return value.strip() if value is not None else None


class LLMStageProviderOverride(StrictModel):
    command: str | None = None
    model: str | None = None
    effort: str | None = None
    timeout_sec: int | None = Field(default=None, ge=1, le=3600)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    retry_backoff_sec: float | None = Field(default=None, ge=0.0, le=60.0)

    @field_validator("command", "model")
    @classmethod
    def optional_text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("effort")
    @classmethod
    def optional_effort_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("effort must be a non-empty string")
        return value.strip() if value is not None else None


class ExtractionConfig(RetryConfig):
    mode: Literal["deterministic", "schema_llm", "schema", "llm"] = "deterministic"
    provider: Literal["codex", "claude"] = "codex"
    command: str | None = None
    model: str | None = None
    codex: LLMStageProviderOverride | None = None
    claude: LLMStageProviderOverride | None = None
    max_triplets_per_chunk: int = Field(default=20, ge=1, le=100)
    num_workers: int = Field(default=4, ge=1, le=64)
    batch_size: int = Field(default=1, ge=1, le=64)
    batch_max_chars: int = Field(default=4000, ge=100, le=200000)
    section_max_heading_level: int = Field(default=6, ge=1, le=6)
    grounding_score_threshold: float = Field(default=0.9, ge=0.0, le=10.0)
    grounding_score_margin: float = Field(default=0.15, ge=0.0, le=10.0)

    @field_validator("command", "model")
    @classmethod
    def optional_text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @model_validator(mode="after")
    def provider_specific_effort_must_match_provider(self) -> ExtractionConfig:
        if self.codex is not None:
            _validate_effort(
                "extraction.codex.effort",
                provider="codex",
                effort=self.codex.effort,
            )
        if self.claude is not None:
            _validate_effort(
                "extraction.claude.effort",
                provider="claude",
                effort=self.claude.effort,
            )
        return self


class AnswerConfig(RetryConfig):
    provider: Literal["template", "deterministic", "none", "disabled", "codex", "claude"] = "template"
    command: str | None = None
    model: str | None = None
    sandbox: str = "read-only"
    tools: str = ""
    failure_fallback: Literal["failed", "template"] = "failed"
    cache_enabled: bool = True
    cache_path: str = ".spec-grag/cache/answer_cache.json"
    context_max_source_constraints: int = Field(default=8, ge=1, le=100)
    context_max_related_sources: int = Field(default=8, ge=1, le=100)
    context_max_entities: int = Field(default=8, ge=1, le=100)
    context_max_review_notes: int = Field(default=12, ge=1, le=200)
    context_max_conflict_notes: int = Field(default=8, ge=1, le=100)
    context_max_classification_notes: int = Field(default=6, ge=1, le=100)
    context_excerpt_chars: int = Field(default=700, ge=80, le=5000)

    @field_validator("command", "model", "sandbox", "cache_path")
    @classmethod
    def optional_text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class ClassificationConfig(RetryConfig):
    provider: Literal["orchestrator_rule_based", "rule_based", "codex", "claude"] = (
        "orchestrator_rule_based"
    )
    command: str | None = None
    model: str | None = None
    sandbox: str = "read-only"
    tools: str = ""
    max_items: int = Field(default=20, ge=1, le=200)
    max_source_chunks: int = Field(default=12, ge=0, le=200)
    max_concepts: int = Field(default=4, ge=0, le=200)
    max_graph_entities: int = Field(default=4, ge=0, le=200)
    max_chapter_anchors: int = Field(default=2, ge=0, le=200)
    max_clusters: int = Field(default=2, ge=0, le=200)
    batch_size: int = Field(default=5, ge=1, le=50)
    cache_enabled: bool = True
    cache_path: str = ".spec-grag/cache/classification_cache.json"
    fail_on_high_priority_incomplete: bool = True
    deferred_enabled: bool = True
    deferred_max_items: int = Field(default=6, ge=0, le=100)
    fallback_on_error: bool = True

    @field_validator("command", "model", "sandbox", "cache_path")
    @classmethod
    def optional_text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class ConceptDiffConfig(RetryConfig):
    provider: Literal["source_derived", "template", "none", "disabled", "codex", "claude"] = (
        "source_derived"
    )
    command: str | None = None
    model: str | None = None
    sandbox: str = "read-only"
    tools: str = ""
    fallback_on_error: bool = True

    @field_validator("command", "model", "sandbox")
    @classmethod
    def optional_text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class CommunityReportConfig(RetryConfig):
    provider: Literal["deterministic", "template", "none", "disabled", "codex", "claude"] = (
        "deterministic"
    )
    command: str | None = None
    model: str | None = None
    sandbox: str = "read-only"
    tools: str = ""
    fallback_on_error: bool = False

    @field_validator("command", "model", "sandbox")
    @classmethod
    def optional_text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class RetrievalConfig(StrictModel):
    chunk_size: int = Field(default=1600, ge=100, le=100000)
    chunk_overlap: int = Field(default=200, ge=0, le=50000)
    vector_top_k: int = Field(default=8, ge=0, le=200)
    bm25_top_k: int = Field(default=12, ge=0, le=200)
    graph_expansion_hops: int = Field(default=1, ge=0, le=3)
    graph_relation_allowlist: list[GraphRelationType] = Field(
        default_factory=lambda: list(DEFAULT_GRAPH_RELATION_ALLOWLIST)
    )
    graph_min_relation_confidence: GraphConfidenceThreshold = (
        DEFAULT_GRAPH_MIN_RELATION_CONFIDENCE
    )
    max_graph_entities: int = Field(default=DEFAULT_MAX_GRAPH_ENTITIES, ge=1, le=200)
    rank_fusion: Literal["rrf"] = "rrf"
    max_source_chunks: int = Field(default=12, ge=1, le=100)

    @field_validator("graph_relation_allowlist")
    @classmethod
    def graph_relation_allowlist_must_not_be_empty(
        cls, value: list[GraphRelationType]
    ) -> list[GraphRelationType]:
        if not value:
            raise ValueError("retrieval.graph_relation_allowlist must not be empty")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def overlap_must_be_smaller_than_chunk_size(self) -> RetrievalConfig:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("retrieval.chunk_overlap must be smaller than chunk_size")
        return self


class QueryPlannerConfig(RetryConfig):
    provider: Literal["template", "deterministic", "none", "disabled", "codex", "claude"] = (
        "template"
    )
    command: str | None = None
    model: str | None = None
    sandbox: str = "read-only"
    tools: str = ""
    cache_enabled: bool = True
    cache_path: str = ".spec-grag/cache/query_plan_cache.json"
    bm25_term_limit: int = Field(default=80, ge=1, le=1000)
    dense_query_max_chars: int = Field(default=2000, ge=100, le=20000)
    fallback_on_error: bool = True

    @field_validator("command", "model", "sandbox", "cache_path")
    @classmethod
    def optional_text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class LLMProviderConfig(StrictModel):
    command: str
    model: str | None = None
    effort: str | None = None
    timeout_sec: int = Field(default=120, ge=1, le=3600)
    max_retries: int = Field(default=0, ge=0, le=10)
    retry_backoff_sec: float = Field(default=0.0, ge=0.0, le=60.0)

    @field_validator("command", "model")
    @classmethod
    def text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("effort")
    @classmethod
    def effort_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("effort must be a non-empty string")
        return value.strip() if value is not None else None


class ProjectLLMConfig(StrictModel):
    provider: Literal["codex_cli", "claude_cli", "mock"] | None = None
    codex_cli: LLMProviderConfig | None = None
    claude_cli: LLMProviderConfig | None = None

    @model_validator(mode="after")
    def effort_must_match_provider(self) -> ProjectLLMConfig:
        if self.codex_cli is not None:
            _validate_effort(
                "llm.codex_cli.effort",
                provider="codex_cli",
                effort=self.codex_cli.effort,
            )
        if self.claude_cli is not None:
            _validate_effort(
                "llm.claude_cli.effort",
                provider="claude_cli",
                effort=self.claude_cli.effort,
            )
        return self


class EmbeddingConfig(StrictModel):
    provider: Literal["ollama", "stable_hash"] = "ollama"
    model: str = "bge-m3"
    dimension: int = Field(default=1024, ge=1, le=65536)
    timeout_sec: int = Field(default=120, ge=1, le=3600)
    max_retries: int = Field(default=0, ge=0, le=10)
    retry_backoff_sec: float = Field(default=0.0, ge=0.0, le=60.0)

    @field_validator("model")
    @classmethod
    def model_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("embedding.model must be a non-empty string")
        return value


class RunConfig(StrictModel):
    save_artifacts: bool = False
    artifact_dir: str = ".spec-grag/runs"
    include_request: bool = False
    include_response: bool = False
    redact_payload: bool = False

    @field_validator("artifact_dir")
    @classmethod
    def artifact_dir_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run.artifact_dir must be a non-empty string")
        return value


class RuntimeConfig(StrictModel):
    mode: Literal["smoke", "local_daily", "ci", "production"] | None = None
    watcher_required: bool | None = None
    foreground_incremental: bool | None = None
    fail_fast_on_dirty: bool | None = None
    fail_fast_on_pending: bool | None = None
    fail_fast_on_stale: bool | None = None


class WatcherConfig(StrictModel):
    enabled: bool = True
    interval_ms: int = Field(default=2000, ge=50, le=3_600_000)
    debounce_ms: int = Field(default=500, ge=0, le=600_000)
    stale_lock_ms: int = Field(default=300_000, ge=1000, le=86_400_000)
    state_file: str = ".spec-grag/state/watch_state.json"
    queue_file: str = ".spec-grag/state/watch_queue.json"

    @field_validator("state_file", "queue_file")
    @classmethod
    def path_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("watcher path must be a non-empty string")
        return value


class ProjectConfig(StrictModel):
    sources: SourcesConfig
    core: CoreConfig = Field(default_factory=CoreConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    answer: AnswerConfig = Field(default_factory=AnswerConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)
    concept_diff: ConceptDiffConfig = Field(default_factory=ConceptDiffConfig)
    community_report: CommunityReportConfig = Field(default_factory=CommunityReportConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    query_planner: QueryPlannerConfig = Field(default_factory=QueryPlannerConfig)
    llm: ProjectLLMConfig | None = None
    embedding: EmbeddingConfig | None = None
    run: RunConfig = Field(default_factory=RunConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)

    @model_validator(mode="after")
    def stage_effort_must_match_provider(self) -> ProjectConfig:
        for section_name in LLM_STAGE_SECTIONS:
            section = getattr(self, section_name)
            _validate_effort(
                f"{section_name}.effort",
                provider=getattr(section, "provider", None),
                effort=getattr(section, "effort", None),
            )
        return self


def validate_project_config(
    config: Mapping[str, Any],
    *,
    smoke: bool | None = None,
) -> dict[str, Any]:
    """Validate and normalize config TOML data into plain Python dictionaries."""

    smoke_mode = smoke_mode_enabled() if smoke is None else smoke
    validated = ProjectConfig.model_validate(apply_llm_provider_defaults(config))
    normalized = validated.model_dump(mode="python", exclude_none=True)
    runtime_mode = resolve_runtime_mode(normalized, smoke_mode=smoke_mode)
    if smoke_mode:
        normalized["_runtime_mode"] = runtime_mode
        normalized["_smoke_mode"] = True
        return normalized
    enforce_production_policy(normalized)
    normalized["_runtime_mode"] = runtime_mode
    normalized["_smoke_mode"] = False
    return normalized


def resolve_runtime_mode(
    config: Mapping[str, Any],
    *,
    smoke_mode: bool | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    values = env if env is not None else os.environ
    runtime_config = _mapping(config.get("runtime"))
    configured = _normalized_text(runtime_config.get("mode"))
    env_mode = _normalized_text(values.get(RUNTIME_MODE_ENV_VAR))
    if configured in RUNTIME_MODES:
        return configured
    if env_mode in RUNTIME_MODES:
        return env_mode
    if smoke_mode is None:
        smoke_mode = smoke_mode_enabled(values)
    return RuntimeMode.SMOKE.value if smoke_mode else RuntimeMode.PRODUCTION.value


def resolve_runtime_policy(
    config: Mapping[str, Any],
    *,
    execution_role: ExecutionRole | str | None = None,
) -> RuntimePolicy:
    mode_value = _normalized_text(config.get("_runtime_mode")) or resolve_runtime_mode(config)
    if mode_value not in RUNTIME_MODES:
        mode_value = RuntimeMode.PRODUCTION.value
    mode = RuntimeMode(mode_value)
    role = (
        ExecutionRole(execution_role)
        if execution_role is not None
        else default_execution_role_for_mode(mode)
    )

    defaults = _runtime_policy_defaults(mode)
    runtime_config = _mapping(config.get("runtime"))
    values = {
        key: bool(runtime_config.get(key, defaults[key]))
        for key in (
            "watcher_required",
            "foreground_incremental",
            "fail_fast_on_dirty",
            "fail_fast_on_pending",
            "fail_fast_on_stale",
        )
    }

    if mode == RuntimeMode.PRODUCTION:
        values["foreground_incremental"] = False
        values["fail_fast_on_dirty"] = True
        values["fail_fast_on_pending"] = True
        values["fail_fast_on_stale"] = True

    if role == ExecutionRole.BACKGROUND_WATCHER:
        values["foreground_incremental"] = False

    return RuntimePolicy(mode=mode, execution_role=role, **values)


def default_execution_role_for_mode(mode: RuntimeMode) -> ExecutionRole:
    if mode == RuntimeMode.CI:
        return ExecutionRole.CI_NO_WATCHER
    if mode == RuntimeMode.PRODUCTION:
        return ExecutionRole.PRODUCTION
    return ExecutionRole.FOREGROUND_HUMAN


def _runtime_policy_defaults(mode: RuntimeMode) -> dict[str, bool]:
    if mode == RuntimeMode.LOCAL_DAILY:
        return {
            "watcher_required": True,
            "foreground_incremental": False,
            "fail_fast_on_dirty": False,
            "fail_fast_on_pending": False,
            "fail_fast_on_stale": False,
        }
    if mode == RuntimeMode.CI:
        return {
            "watcher_required": False,
            "foreground_incremental": True,
            "fail_fast_on_dirty": False,
            "fail_fast_on_pending": False,
            "fail_fast_on_stale": False,
        }
    if mode == RuntimeMode.SMOKE:
        return {
            "watcher_required": False,
            "foreground_incremental": True,
            "fail_fast_on_dirty": False,
            "fail_fast_on_pending": False,
            "fail_fast_on_stale": False,
        }
    return {
        "watcher_required": False,
        "foreground_incremental": False,
        "fail_fast_on_dirty": True,
        "fail_fast_on_pending": True,
        "fail_fast_on_stale": True,
    }


def apply_llm_provider_defaults(config: Mapping[str, Any]) -> dict[str, Any]:
    """Apply external-contract ``[llm]`` defaults to all LLM-backed stages.

    ``[llm]`` is the project-level switch. Detailed stage tables can still add
    phase-specific settings such as fallback policy, sandbox, tools, and retry
    behavior, while command/model/provider default to the selected LLM provider.
    """

    normalized = _copy_config(config)
    llm_config = _mapping(normalized.get("llm"))
    llm_provider = _normalized_text(llm_config.get("provider"))
    default_stage_provider = LLM_PROVIDER_TO_STAGE_PROVIDER.get(llm_provider)
    if default_stage_provider is None:
        return normalized

    for section_name in LLM_STAGE_SECTIONS:
        section = dict(_mapping(normalized.get(section_name)))
        configured_provider = _normalized_text(section.get("provider"))
        stage_provider = (
            configured_provider
            if configured_provider in LLM_PROVIDERS
            else default_stage_provider
        )
        section["provider"] = stage_provider
        stage_llm_provider = STAGE_PROVIDER_TO_LLM_PROVIDER.get(stage_provider, llm_provider)
        provider_config = _mapping(llm_config.get(stage_llm_provider))
        for key in LLM_INHERITED_KEYS:
            value = provider_config.get(key)
            if value is not None and key not in section:
                section[key] = value
        if section_name == "extraction":
            stage_override = _mapping(section.get(stage_provider))
            for key in LLM_INHERITED_KEYS:
                value = stage_override.get(key)
                if value is not None:
                    section[key] = value
        normalized[section_name] = section
    return normalized


def enforce_production_policy(config: Mapping[str, Any]) -> None:
    """Reject smoke/fallback settings from the normal production runtime path."""

    errors: list[str] = []

    llm_config = _mapping(config.get("llm"))
    if not llm_config:
        errors.append("llm section is required in production")
    else:
        llm_provider = _normalized_text(llm_config.get("provider"))
        if llm_provider not in LLM_PROVIDER_TO_STAGE_PROVIDER:
            errors.append("llm.provider must be codex_cli or claude_cli in production")
        else:
            llm_provider_config = _mapping(llm_config.get(llm_provider))
            if not llm_provider_config:
                errors.append(f"llm.{llm_provider} table is required in production")
            elif not _normalized_text(llm_provider_config.get("model")):
                errors.append(f"llm.{llm_provider}.model is required in production")
        required_cli_providers = {
            STAGE_PROVIDER_TO_LLM_PROVIDER[stage_provider]
            for section_name in LLM_STAGE_SECTIONS
            for stage_provider in [_normalized_text(_mapping(config.get(section_name)).get("provider"))]
            if stage_provider in STAGE_PROVIDER_TO_LLM_PROVIDER
        }
        for required_provider in sorted(required_cli_providers):
            required_config = _mapping(llm_config.get(required_provider))
            if not required_config:
                errors.append(f"llm.{required_provider} table is required in production")
            elif not _normalized_text(required_config.get("model")):
                errors.append(f"llm.{required_provider}.model is required in production")

    core_config = _mapping(config.get("core"))
    extraction_config = _mapping(config.get("extraction"))
    core_mode = _normalized_text(core_config.get("extraction_mode"))
    extraction_mode = _normalized_text(extraction_config.get("mode"))
    effective_extraction_mode = extraction_mode or core_mode
    if effective_extraction_mode in {"schema", "llm"}:
        effective_extraction_mode = "schema_llm"
    if effective_extraction_mode != "schema_llm":
        errors.append(
            "extraction.mode must be schema_llm in production "
            f"(got {effective_extraction_mode or 'missing'})"
        )
    if core_mode == "deterministic":
        errors.append("core.extraction_mode must not be deterministic in production")

    embedding_config = _mapping(config.get("embedding"))
    if not embedding_config:
        errors.append("embedding section is required in production")
    elif _normalized_text(embedding_config.get("provider")) == "stable_hash":
        errors.append("embedding.provider=stable_hash is smoke-only")

    answer_config = _mapping(config.get("answer"))
    if _normalized_text(answer_config.get("provider")) not in LLM_PROVIDERS:
        errors.append("answer.provider must be codex or claude in production")
    if _normalized_text(answer_config.get("failure_fallback")) == "template":
        errors.append("answer.failure_fallback=template is smoke-only")

    classification_config = _mapping(config.get("classification"))
    if _normalized_text(classification_config.get("provider")) not in LLM_PROVIDERS:
        errors.append("classification.provider must be codex or claude in production")
    if bool(classification_config.get("fallback_on_error", False)):
        errors.append("classification.fallback_on_error must be false in production")

    concept_diff_config = _mapping(config.get("concept_diff"))
    if _normalized_text(concept_diff_config.get("provider")) not in LLM_PROVIDERS:
        errors.append("concept_diff.provider must be codex or claude in production")
    if bool(concept_diff_config.get("fallback_on_error", False)):
        errors.append("concept_diff.fallback_on_error must be false in production")

    community_report_config = _mapping(config.get("community_report"))
    if _normalized_text(community_report_config.get("provider")) not in LLM_PROVIDERS:
        errors.append("community_report.provider must be codex or claude in production")
    if bool(community_report_config.get("fallback_on_error", False)):
        errors.append("community_report.fallback_on_error must be false in production")

    query_planner_config = _mapping(config.get("query_planner"))
    if _normalized_text(query_planner_config.get("provider")) not in LLM_PROVIDERS:
        errors.append("query_planner.provider must be codex or claude in production")
    if bool(query_planner_config.get("fallback_on_error", False)):
        errors.append("query_planner.fallback_on_error must be false in production")

    if errors:
        raise ConfigPolicyError("production policy violation: " + "; ".join(errors))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _validate_effort(path: str, *, provider: Any, effort: Any) -> None:
    if effort is None:
        return
    provider_key = _normalized_text(provider)
    allowed = LLM_EFFORT_VALUES_BY_PROVIDER.get(provider_key)
    if allowed is None:
        return
    effort_key = str(effort).strip()
    if effort_key not in allowed:
        raise ValueError(f"{path} must be one of {', '.join(allowed)}")


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _copy_config(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _copy_config(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_copy_config(child) for child in value]
    return value
