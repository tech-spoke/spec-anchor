from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from spec_grag.chunk_index import QueryPlan
from spec_grag.concept_index import (
    ConceptDiffProposal,
    ConceptDiffProposalError,
    concept_diff_terms_from_config,
)
from spec_grag.config import ConfigPolicyError, smoke_mode_enabled, validate_project_config
from spec_grag.core import run_core_update
from spec_grag.embedding import EmbeddingProviderError
from spec_grag.extraction import BatchExtractionResponse
from spec_grag.injection import (
    ClassificationBatchResponse,
    ClassificationDecision,
    ClassificationError,
    classify_context_item,
)
from spec_grag.protocol import ResultEnvelope, ResultStatus, ResultType
from spec_grag.realign import AnswerSections
from spec_grag.run_artifacts import fallback_events
from spec_grag.sidecars import CommunityReportLLMBatch


def smoke_config() -> dict:
    return {
        "sources": {"include": ["docs/spec/**/*.md"]},
        "core": {
            "purpose_file": "docs/core/purpose.md",
            "concept_file": "docs/core/concept.md",
            "extraction_mode": "deterministic",
        },
        "extraction": {"mode": "deterministic", "provider": "codex"},
        "answer": {"provider": "template", "failure_fallback": "template"},
        "classification": {
            "provider": "orchestrator_rule_based",
            "fallback_on_error": True,
        },
        "concept_diff": {"provider": "source_derived", "fallback_on_error": True},
        "query_planner": {"provider": "template", "fallback_on_error": True},
        "embedding": {"provider": "stable_hash", "model": "sha256-v1", "dimension": 8},
    }


def assert_object_properties_are_required(schema: dict[str, Any]) -> None:
    if schema.get("type") == "object":
        properties = schema.get("properties") or {}
        assert set(schema.get("required") or []) == set(properties)
    for value in (schema.get("$defs") or {}).values():
        assert_object_properties_are_required(value)
    for key in ("properties",):
        for value in (schema.get(key) or {}).values():
            assert_object_properties_are_required(value)
    if "items" in schema:
        assert_object_properties_are_required(schema["items"])
    for key in ("anyOf", "oneOf", "allOf"):
        for value in schema.get(key) or []:
            assert_object_properties_are_required(value)


def test_llm_output_schemas_are_codex_structured_output_compatible() -> None:
    for model in (
        QueryPlan,
        ClassificationBatchResponse,
        ClassificationDecision,
        AnswerSections,
        ConceptDiffProposal,
        CommunityReportLLMBatch,
        BatchExtractionResponse,
    ):
        assert_object_properties_are_required(model.model_json_schema())


def production_config() -> dict:
    return {
        "sources": {"include": ["docs/spec/**/*.md"]},
        "llm": {
            "provider": "codex_cli",
            "codex_cli": {"command": "codex", "model": "gpt-5.4", "effort": "low"},
            "claude_cli": {
                "command": "claude",
                "model": "claude-sonnet-4-6",
                "effort": "low",
            },
        },
        "core": {
            "purpose_file": "docs/core/purpose.md",
            "concept_file": "docs/core/concept.md",
            "extraction_mode": "schema_llm",
        },
        "extraction": {"mode": "schema_llm"},
        "answer": {"failure_fallback": "failed"},
        "classification": {"fallback_on_error": False},
        "concept_diff": {"fallback_on_error": False},
        "community_report": {"fallback_on_error": False},
        "query_planner": {"fallback_on_error": False},
        "embedding": {"provider": "ollama", "model": "bge-m3", "dimension": 1024},
    }


def test_production_policy_rejects_smoke_fallback_config() -> None:
    with pytest.raises(ConfigPolicyError) as exc_info:
        validate_project_config(smoke_config(), smoke=False)

    message = str(exc_info.value)
    assert "production policy violation" in message
    assert "llm section is required" in message
    assert "embedding.provider=stable_hash" in message
    assert "answer.provider must be codex or claude" in message
    assert "classification.provider must be codex or claude" in message
    assert "concept_diff.provider must be codex or claude" in message
    assert "community_report.provider must be codex or claude" in message
    assert "query_planner.provider must be codex or claude" in message


def test_smoke_mode_allows_smoke_fallback_config() -> None:
    validated = validate_project_config(smoke_config(), smoke=True)

    assert validated["_runtime_mode"] == "smoke"
    assert validated["embedding"]["provider"] == "stable_hash"
    assert validated["answer"]["provider"] == "template"


def test_production_policy_accepts_real_provider_config() -> None:
    validated = validate_project_config(production_config(), smoke=False)

    assert validated["_runtime_mode"] == "production"
    assert validated["extraction"]["mode"] == "schema_llm"
    assert validated["embedding"]["provider"] == "ollama"
    assert validated["classification"]["fallback_on_error"] is False
    assert validated["classification"]["max_items"] == 20
    assert validated["classification"]["max_source_chunks"] == 12
    assert validated["classification"]["max_concepts"] == 4
    assert validated["classification"]["max_graph_entities"] == 4
    assert validated["classification"]["max_chapter_anchors"] == 2
    assert validated["classification"]["max_clusters"] == 2
    assert validated["classification"]["batch_size"] == 5
    assert validated["classification"]["cache_enabled"] is True
    assert validated["classification"]["cache_path"] == ".spec-grag/cache/classification_cache.json"
    assert validated["classification"]["fail_on_high_priority_incomplete"] is True


def test_llm_provider_switch_applies_to_all_production_stages() -> None:
    config = production_config()
    config["llm"]["provider"] = "claude_cli"
    config["llm"]["claude_cli"] = {
        "command": "claude-dev",
        "model": "claude-sonnet-4-6",
        "effort": "max",
        "timeout_sec": 33,
        "max_retries": 2,
        "retry_backoff_sec": 1.5,
    }
    config["answer"]["model"] = "stage-specific-answer-model"

    validated = validate_project_config(config, smoke=False)

    for section in (
        "extraction",
        "classification",
        "concept_diff",
        "community_report",
        "query_planner",
    ):
        assert validated[section]["provider"] == "claude"
        assert validated[section]["command"] == "claude-dev"
        assert validated[section]["model"] == "claude-sonnet-4-6"
        assert validated[section]["effort"] == "max"
        assert validated[section]["timeout_sec"] == 33
        assert validated[section]["max_retries"] == 2
        assert validated[section]["retry_backoff_sec"] == 1.5
    assert validated["answer"]["provider"] == "claude"
    assert validated["answer"]["command"] == "claude-dev"
    assert validated["answer"]["model"] == "stage-specific-answer-model"
    assert validated["answer"]["effort"] == "max"
    assert validated["answer"]["timeout_sec"] == 33


def test_extraction_can_override_provider_with_provider_specific_light_model() -> None:
    config = production_config()
    config["llm"]["provider"] = "claude_cli"
    config["extraction"] = {
        "mode": "schema_llm",
        "provider": "codex",
        "codex": {"model": "gpt-5.4-mini", "effort": "low"},
        "claude": {"model": "claude-haiku-4-5", "effort": "low"},
    }

    validated = validate_project_config(config, smoke=False)

    assert validated["extraction"]["provider"] == "codex"
    assert validated["extraction"]["command"] == "codex"
    assert validated["extraction"]["model"] == "gpt-5.4-mini"
    assert validated["extraction"]["effort"] == "low"
    assert validated["answer"]["provider"] == "claude"
    assert validated["answer"]["model"] == "claude-sonnet-4-6"


def test_llm_provider_effort_is_validated_by_cli_provider() -> None:
    config = production_config()
    config["llm"]["codex_cli"]["effort"] = "max"

    with pytest.raises(ValueError) as exc_info:
        validate_project_config(config, smoke=False)

    assert "llm.codex_cli.effort must be one of minimal, low, medium, high, xhigh" in str(
        exc_info.value
    )

    config = production_config()
    config["llm"]["claude_cli"]["effort"] = "minimal"

    with pytest.raises(ValueError) as exc_info:
        validate_project_config(config, smoke=False)

    assert "llm.claude_cli.effort must be one of low, medium, high, xhigh, max" in str(
        exc_info.value
    )


def test_stage_effort_override_is_validated_against_selected_provider() -> None:
    config = production_config()
    config["llm"]["provider"] = "claude_cli"
    config["answer"]["effort"] = "minimal"

    with pytest.raises(ValueError) as exc_info:
        validate_project_config(config, smoke=False)

    assert "answer.effort must be one of low, medium, high, xhigh, max" in str(
        exc_info.value
    )


def test_llm_provider_table_is_required_when_declared() -> None:
    config = production_config()
    config["llm"] = {
        "provider": "claude_cli",
        "codex_cli": {"command": "codex", "model": "gpt-5.4", "effort": "low"},
    }

    with pytest.raises(ConfigPolicyError) as exc_info:
        validate_project_config(config, smoke=False)

    assert "llm.claude_cli table is required" in str(exc_info.value)


def test_llm_provider_model_is_required_when_declared() -> None:
    config = production_config()
    config["llm"]["codex_cli"].pop("model")

    with pytest.raises(ConfigPolicyError) as exc_info:
        validate_project_config(config, smoke=False)

    assert "llm.codex_cli.model is required" in str(exc_info.value)


def test_smoke_mode_env_detection() -> None:
    assert smoke_mode_enabled({"SPEC_GRAG_SMOKE": "1"}) is True
    assert smoke_mode_enabled({"SPEC_GRAG_RUNTIME_MODE": "smoke"}) is True
    assert smoke_mode_enabled({}) is False


def test_production_templates_do_not_emit_smoke_provider_events() -> None:
    for path in (
        Path(".spec-grag/config.toml"),
        Path("templates/.spec-grag/config.toml"),
        Path("spec_grag/templates/.spec-grag/config.toml"),
    ):
        config = tomllib.loads(path.read_text(encoding="utf-8"))
        validated = validate_project_config(config, smoke=False)

        assert validated["_runtime_mode"] == "production"
        assert [
            event
            for event in fallback_events(validated, SimpleNamespace(warnings=[]))
            if event["source"] == "provider_config"
        ] == []


def test_cli_rejects_smoke_config_without_smoke_env(tmp_path: Path) -> None:
    write_smoke_project(tmp_path)
    result = run_cli(tmp_path, smoke=False)

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT
    assert envelope.payload.error_code == "config_invalid"
    assert "production policy violation" in envelope.payload.details["message"]


def test_classification_llm_failure_is_fail_fast_when_fallback_disabled() -> None:
    class BrokenLLM:
        def complete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            raise RuntimeError("boom")

    with pytest.raises(ClassificationError):
        classify_context_item(
            {"summary": "Auth protects sessions."},
            item_type="concept",
            query="Auth Login を見直す",
            llm=BrokenLLM(),
            fallback_on_error=False,
        )


def test_classification_budget_exhaustion_is_policy_skip_not_provider_fallback() -> None:
    item = classify_context_item(
        {"summary": "Auth protects sessions."},
        item_type="concept",
        query="Auth Login を見直す",
        llm=SimpleNamespace(),
        llm_budget={"remaining": 0},
        fallback_on_error=False,
    )

    assert item["classification_source"] == "classification_incomplete"
    assert item["classification_llm_skipped"] == "max_items_exhausted"
    assert item["review_required"] is True


def test_classification_llm_path_does_not_preapply_fixed_intent_words() -> None:
    class CapturingLLM:
        def complete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "constraint_relevance": "low",
                        "target_relevance": "none",
                        "semantic_conflict_candidate": False,
                        "review_required": False,
                        "reason_for_current_task": "LLM-only decision",
                    }
                )
            )

    item = classify_context_item(
        {"summary": "Auth protects sessions."},
        item_type="concept",
        query="Auth Login target update 見直す",
        llm=CapturingLLM(),
        fallback_on_error=False,
    )

    assert item["classification_source"] == "classification_llm"
    assert item["target_relevance"] == "none"
    assert item["reason_for_current_task"] == "LLM-only decision"


def test_concept_diff_llm_failure_is_fail_fast_when_fallback_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenLLM:
        def complete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            raise RuntimeError("concept diff unavailable")

    monkeypatch.setattr(
        "spec_grag.concept_index.make_concept_diff_llm_from_config",
        lambda config: BrokenLLM(),
    )

    with pytest.raises(ConceptDiffProposalError):
        concept_diff_terms_from_config(
            config={"concept_diff": {"provider": "codex", "fallback_on_error": False}},
            concept_text="# Concept\n\nAuth protects sessions.\n",
            source_terms=[],
            changed_source_section_ids=["docs/spec/auth.md#auth-login"],
        )


def test_core_update_reports_embedding_provider_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_smoke_project(tmp_path)

    def fail_embedding(*args: Any, **kwargs: Any) -> list[float]:
        raise EmbeddingProviderError("embedding unavailable")

    monkeypatch.setattr("spec_grag.core.embedding_for_text", fail_embedding)

    update = run_core_update(tmp_path, smoke_config(), all_sources=True)

    assert update.status == ResultStatus.FAILED
    assert update.failed_sources == ["embedding"]
    assert update.warnings[0].startswith("embedding_provider_failed:")


def test_core_update_reports_concept_diff_provider_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_smoke_project(tmp_path)
    config = smoke_config()
    config["concept_diff"] = {"provider": "codex", "fallback_on_error": False}

    class BrokenLLM:
        def complete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            raise RuntimeError("concept diff unavailable")

    monkeypatch.setattr(
        "spec_grag.concept_index.make_concept_diff_llm_from_config",
        lambda config: BrokenLLM(),
    )

    update = run_core_update(tmp_path, config, all_sources=True)

    assert update.status == ResultStatus.FAILED
    assert update.failed_sources == ["concept_diff"]
    assert any(
        warning.startswith("concept_diff_provider_failed:")
        for warning in update.warnings
    )


def write_smoke_project(project_root: Path) -> None:
    spec_dir = project_root / "docs/spec"
    core_dir = project_root / "docs/core"
    config_dir = project_root / ".spec-grag"
    spec_dir.mkdir(parents=True)
    core_dir.mkdir(parents=True)
    config_dir.mkdir()
    (spec_dir / "sample.md").write_text("# Sample\n\n## Item\n\nKeep a note.\n", encoding="utf-8")
    (core_dir / "purpose.md").write_text("# Purpose\nKeep specs aligned.\n", encoding="utf-8")
    (core_dir / "concept.md").write_text("# Concept\nNotes are stable.\n", encoding="utf-8")
    (config_dir / "config.toml").write_text(
        """
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"
extraction_mode = "deterministic"

[extraction]
mode = "deterministic"
provider = "codex"

[answer]
provider = "template"
failure_fallback = "template"

[classification]
provider = "orchestrator_rule_based"
fallback_on_error = true

[concept_diff]
provider = "source_derived"
fallback_on_error = true

[query_planner]
provider = "template"
fallback_on_error = true

[embedding]
provider = "stable_hash"
model = "sha256-v1"
dimension = 8
""".strip(),
        encoding="utf-8",
    )


def run_cli(project_root: Path, *, smoke: bool) -> subprocess.CompletedProcess[str]:
    payload = {
        "command": "spec-core",
        "project_root": str(project_root),
        "conversation_context": {
            "current_user_message": "check sample",
            "recent_messages": [],
            "working_target": None,
            "explicit_files": [],
        },
        "agent_capabilities": {"can_read_source": True, "can_answer": False},
        "options": {"output_format": "json", "all": True},
    }
    env = os.environ.copy()
    if smoke:
        env["SPEC_GRAG_SMOKE"] = "1"
    else:
        env.pop("SPEC_GRAG_SMOKE", None)
        env.pop("SPEC_GRAG_RUNTIME_MODE", None)
    return subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=json.dumps(payload),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
