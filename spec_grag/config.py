"""Strict project config validation for .spec-grag/config.toml."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, field_validator

from spec_grag.protocol import StrictModel


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


class ExtractionConfig(RetryConfig):
    mode: Literal["deterministic", "schema_llm", "schema", "llm"] = "deterministic"
    provider: Literal["codex", "claude"] = "codex"
    command: str | None = None
    model: str | None = None
    max_triplets_per_chunk: int = Field(default=20, ge=1, le=100)
    num_workers: int = Field(default=4, ge=1, le=64)
    grounding_score_threshold: float = Field(default=0.9, ge=0.0, le=10.0)
    grounding_score_margin: float = Field(default=0.15, ge=0.0, le=10.0)

    @field_validator("command", "model")
    @classmethod
    def optional_text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class AnswerConfig(RetryConfig):
    provider: Literal["template", "deterministic", "none", "disabled", "codex", "claude"] = "template"
    command: str | None = None
    model: str | None = None
    sandbox: str = "read-only"
    tools: str = ""
    failure_fallback: Literal["failed", "template"] = "failed"

    @field_validator("command", "model", "sandbox")
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
    max_items: int = Field(default=24, ge=1, le=200)
    fallback_on_error: bool = True

    @field_validator("command", "model", "sandbox")
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


class LegacyLLMProviderConfig(StrictModel):
    command: str
    model: str | None = None
    timeout_sec: int = Field(default=120, ge=1, le=3600)
    max_retries: int = Field(default=0, ge=0, le=10)
    retry_backoff_sec: float = Field(default=0.0, ge=0.0, le=60.0)

    @field_validator("command", "model")
    @classmethod
    def text_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class LegacyLLMConfig(StrictModel):
    provider: Literal["codex_cli", "claude_cli", "mock"] | None = None
    codex_cli: LegacyLLMProviderConfig | None = None
    claude_cli: LegacyLLMProviderConfig | None = None


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
    include_request: bool = True

    @field_validator("artifact_dir")
    @classmethod
    def artifact_dir_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run.artifact_dir must be a non-empty string")
        return value


class ProjectConfig(StrictModel):
    sources: SourcesConfig
    core: CoreConfig = Field(default_factory=CoreConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    answer: AnswerConfig = Field(default_factory=AnswerConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)
    concept_diff: ConceptDiffConfig = Field(default_factory=ConceptDiffConfig)
    llm: LegacyLLMConfig | None = None
    embedding: EmbeddingConfig | None = None
    run: RunConfig = Field(default_factory=RunConfig)


def validate_project_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize config TOML data into plain Python dictionaries."""

    validated = ProjectConfig.model_validate(config)
    return validated.model_dump(mode="python", exclude_none=True)
