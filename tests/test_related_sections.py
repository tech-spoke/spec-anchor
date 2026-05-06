"""Related Sections contract tests for G-08.

Related Sections are retrieval auxiliaries / reference helpers. They may help
an Agent decide which Source Specs to inspect next, but they are not evidence
for final constraints by themselves.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spec_grag.llm_provider import LlmRequest


ALLOWED_RELATION_HINTS = {
    "depends_on",
    "impacts",
    "conflicts_with",
    "same_policy",
    "prerequisite",
    "see_also",
}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}


@dataclass
class RelatedSelectionProvider:
    output: dict[str, Any]

    def __post_init__(self) -> None:
        self.calls: list[LlmRequest] = []

    @property
    def provider_id(self) -> str:
        return "related-section-selection-fake"

    def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
        self.calls.append(request)
        return self.output


def _related_module() -> Any:
    module = importlib.import_module("spec_grag.section_metadata")
    return module


def _required_function(module: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail(
        "Related Sections API is required; expected one of: " + ", ".join(names)
    )


def _call(func: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    supported = {
        name: value for name, value in kwargs.items() if name in signature.parameters
    }
    try:
        return func(**supported)
    except TypeError:
        return func(*kwargs.get("_positional", ()), **supported)


def _section(
    section_id: str,
    *,
    chapter_id: str,
    heading: str,
    text: str,
    ordinal: int,
    identifiers: list[str] | None = None,
    summary: str = "",
    search_keys: list[str] | None = None,
) -> dict[str, Any]:
    source_hash = f"hash-{section_id}"
    return {
        "section_id": section_id,
        "source_section_id": section_id,
        "stable_section_uid": f"uid-{section_id}",
        "source_document_id": "docs/spec/main.md",
        "heading_path": [chapter_id.rsplit("#", 1)[-1], heading],
        "heading_level": 2,
        "chapter_id": chapter_id,
        "source_hash": source_hash,
        "semantic_hash": source_hash,
        "source_span": {"start_line": ordinal * 10, "end_line": ordinal * 10 + 5},
        "text": text,
        "identifiers": identifiers or [],
        "summary": summary,
        "search_keys": search_keys or [],
    }


def _fixture_sections() -> list[dict[str, Any]]:
    chapter_one = "docs/spec/main.md#chapter-one"
    chapter_two = "docs/spec/main.md#chapter-two"
    return [
        _section(
            "docs/spec/main.md#alpha",
            chapter_id=chapter_one,
            heading="Alpha",
            ordinal=1,
            identifiers=["AUTH_TOKEN"],
            search_keys=["freshness gate", "auth token"],
            summary="Alpha config depends on freshness gate.",
            text=(
                "Alpha uses `AUTH_TOKEN` and links to "
                "[Beta](docs/spec/main.md#beta). "
                "It also links to [Missing](docs/spec/main.md#missing)."
            ),
        ),
        _section(
            "docs/spec/main.md#beta",
            chapter_id=chapter_one,
            heading="Beta",
            ordinal=2,
            identifiers=["AUTH_TOKEN"],
            search_keys=["freshness gate", "beta policy"],
            summary="Beta defines the freshness gate for auth token.",
            text="Beta defines `AUTH_TOKEN` freshness gate behavior.",
        ),
        _section(
            "docs/spec/main.md#gamma",
            chapter_id=chapter_one,
            heading="Gamma",
            ordinal=3,
            identifiers=["GAMMA_ONLY"],
            search_keys=["summary only"],
            summary="Gamma mentions retry budget and freshness in prose.",
            text="Gamma is the next neighboring section after Beta.",
        ),
        _section(
            "docs/spec/other.md#delta",
            chapter_id=chapter_two,
            heading="Delta",
            ordinal=4,
            identifiers=["DELTA_ONLY"],
            search_keys=["freshness gate"],
            summary="Delta shares search wording but not chapter.",
            text="Delta is in another chapter and is useful for search_key_match.",
        ),
        _section(
            "docs/spec/other.md#epsilon",
            chapter_id=chapter_two,
            heading="Epsilon",
            ordinal=5,
            identifiers=["EPSILON_ONLY"],
            search_keys=["epsilon"],
            summary="This summary repeats Alpha config depends on freshness gate.",
            text="Epsilon is found through summary search only.",
        ),
    ]


def _metadata_for(sections: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifact_role": "retrieval_aid_not_evidence",
        "summary_search_keys_are_evidence": False,
        "sections": [
            {
                "section_id": section["section_id"],
                "heading_path": section["heading_path"],
                "summary": section["summary"],
                "search_keys": section["search_keys"],
                "identifiers": section["identifiers"],
                "related_sections": [],
                "source_hash": section["source_hash"],
                "semantic_hash": section["semantic_hash"],
            }
            for section in sections
        ],
    }


def _config(*, candidate_max: int = 32, selected_max: int = 8) -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(model="fake-model", effort="low", timeout_sec=5, max_retries=0),
        limits=SimpleNamespace(
            section_summary_max_chars=480,
            search_keys_max=32,
            related_candidate_max_per_section=candidate_max,
            related_selected_max_per_section=selected_max,
            conflict_pair_max_per_section=8,
            llm_batch_max_sections=8,
            llm_batch_max_chars=12000,
        ),
        section_metadata=SimpleNamespace(
            summary_enabled=True,
            search_keys_enabled=True,
            related_sections_enabled=True,
        ),
    )


def _candidates(payload: Any, source_section_id: str) -> list[dict[str, Any]]:
    if hasattr(payload, "candidates"):
        payload = payload.candidates
    if isinstance(payload, dict):
        payload = payload.get("related_section_candidates", payload.get("candidates", payload))
        if isinstance(payload, dict):
            payload = payload.get(source_section_id, [])
    assert isinstance(payload, list), "candidate generation must return candidate list data"
    return [dict(item) for item in payload if item.get("source_section_id") == source_section_id]


def _diagnostics(payload: Any) -> list[dict[str, Any]]:
    if hasattr(payload, "diagnostics"):
        payload = payload.diagnostics
    elif isinstance(payload, dict):
        payload = payload.get("diagnostics", [])
    else:
        payload = []
    return [dict(item) for item in payload]


def _related_sections(payload: Any, source_section_id: str | None = None) -> list[dict[str, Any]]:
    if hasattr(payload, "related_sections"):
        payload = payload.related_sections
    if isinstance(payload, dict):
        payload = payload.get("related_sections", payload.get("sections", payload))
        if isinstance(payload, dict) and source_section_id is not None:
            payload = payload.get(source_section_id, [])
    assert isinstance(payload, list), "selection/validation must return related_sections list data"
    if source_section_id is None:
        return [dict(item) for item in payload]
    return [
        dict(item)
        for item in payload
        if item.get("source_section_id", source_section_id) == source_section_id
    ]


def test_t_u09_related_section_candidate_generation_channels_merge_schema_and_limit() -> None:
    module = _related_module()
    build_candidates = _required_function(
        module,
        (
            "build_related_section_candidates",
            "generate_related_section_candidates",
            "build_related_sections_candidates",
        ),
    )
    sections = _fixture_sections()
    metadata = _metadata_for(sections)
    source_id = "docs/spec/main.md#alpha"

    full_payload = _call(
        build_candidates,
        _positional=(sections,),
        sections=sections,
        section_metadata=metadata,
        metadata=metadata,
        config=_config(candidate_max=32),
        limits=_config(candidate_max=32).limits,
        generated_at="2026-05-06T00:00:00Z",
    )
    candidates = _candidates(full_payload, source_id)
    by_target = {candidate["target_section_id"]: candidate for candidate in candidates}

    beta = by_target["docs/spec/main.md#beta"]
    assert {"same_chapter", "neighbor_section", "markdown_link"}.issubset(beta["channels"])
    assert {"shared_identifier", "search_key_match"}.issubset(beta["channels"])
    assert "docs/spec/main.md#missing" not in by_target
    assert source_id not in by_target

    assert "same_chapter" in by_target["docs/spec/main.md#gamma"]["channels"]
    assert "search_key_match" in by_target["docs/spec/other.md#delta"]["channels"]
    assert "summary_search" in by_target["docs/spec/other.md#epsilon"]["channels"]

    required_fields = {
        "source_section_id",
        "target_section_id",
        "channels",
        "candidate_score",
        "evidence_terms",
        "evidence_snippets",
        "source",
        "generated_at",
    }
    for candidate in candidates:
        assert required_fields.issubset(candidate)
        assert isinstance(candidate["channels"], list)
        assert isinstance(candidate["evidence_terms"], list)
        assert isinstance(candidate["evidence_snippets"], list)

    limited_payload = _call(
        build_candidates,
        _positional=(sections,),
        sections=sections,
        section_metadata=metadata,
        metadata=metadata,
        config=_config(candidate_max=1),
        limits=_config(candidate_max=1).limits,
        generated_at="2026-05-06T00:00:00Z",
    )
    limited_candidates = _candidates(limited_payload, source_id)
    assert len(limited_candidates) == 1
    assert limited_candidates[0]["target_section_id"] == "docs/spec/main.md#beta"
    assert "markdown_link" in limited_candidates[0]["channels"]
    assert any(
        diagnostic.get("reason_code") in {"candidate_limit_exceeded", "related_candidate_limit"}
        for diagnostic in _diagnostics(limited_payload)
    )


def test_t_u10_related_sections_validation_filters_invalid_items_and_applies_limit() -> None:
    module = _related_module()
    validate = _required_function(
        module,
        (
            "validate_related_sections",
            "validate_related_section_selection",
            "filter_valid_related_sections",
        ),
    )
    sections = _fixture_sections()
    candidates = [
        {
            "source_section_id": "docs/spec/main.md#alpha",
            "target_section_id": "docs/spec/main.md#beta",
            "channels": ["shared_identifier"],
            "candidate_score": 10,
            "evidence_terms": ["AUTH_TOKEN"],
            "evidence_snippets": ["Alpha and Beta mention AUTH_TOKEN."],
            "source": "candidate_generation",
            "generated_at": "2026-05-06T00:00:00Z",
        },
        {
            "source_section_id": "docs/spec/main.md#alpha",
            "target_section_id": "docs/spec/main.md#gamma",
            "channels": ["same_chapter"],
            "candidate_score": 6,
            "evidence_terms": ["neighboring"],
            "evidence_snippets": ["neighboring section"],
            "source": "candidate_generation",
            "generated_at": "2026-05-06T00:00:00Z",
        },
    ]
    llm_output = {
        "related_sections": [
            {
                "target_section_id": "docs/spec/main.md#beta",
                "relation_hint": "depends_on",
                "confidence": "high",
                "reason": "Alpha depends on Beta's auth policy.",
                "evidence_terms": ["AUTH_TOKEN"],
                "channels": ["shared_identifier"],
            },
            {
                "target_section_id": "docs/spec/main.md#gamma",
                "relation_hint": "see_also",
                "confidence": "medium",
                "reason": "Neighboring section.",
                "evidence_terms": ["neighboring"],
                "channels": ["same_chapter"],
            },
            {"target_section_id": "docs/spec/main.md#missing", "relation_hint": "see_also", "confidence": "low", "reason": "missing", "evidence_terms": ["AUTH_TOKEN"], "channels": ["shared_identifier"]},
            {"target_section_id": "docs/spec/main.md#alpha", "relation_hint": "see_also", "confidence": "low", "reason": "self", "evidence_terms": ["AUTH_TOKEN"], "channels": ["shared_identifier"]},
            {"target_section_id": "docs/spec/main.md#beta", "relation_hint": "invalid", "confidence": "low", "reason": "bad relation", "evidence_terms": ["AUTH_TOKEN"], "channels": ["shared_identifier"]},
            {"target_section_id": "docs/spec/main.md#beta", "relation_hint": "see_also", "confidence": "certain", "reason": "bad confidence", "evidence_terms": ["AUTH_TOKEN"], "channels": ["shared_identifier"]},
            {"target_section_id": "docs/spec/main.md#beta", "relation_hint": "see_also", "confidence": "low", "reason": "bad evidence", "evidence_terms": ["NOT_IN_CANDIDATE_OR_TEXT"], "channels": ["shared_identifier"]},
        ],
    }

    payload = _call(
        validate,
        _positional=("docs/spec/main.md#alpha", llm_output, candidates),
        source_section_id="docs/spec/main.md#alpha",
        llm_output=llm_output,
        output=llm_output,
        candidates=candidates,
        related_section_candidates=candidates,
        sections=sections,
        section_by_id={section["section_id"]: section for section in sections},
        config=_config(selected_max=1),
        limits=_config(selected_max=1).limits,
        related_selected_max_per_section=1,
        generated_at="2026-05-06T00:00:00Z",
    )
    selected = _related_sections(payload, "docs/spec/main.md#alpha")

    assert [item["target_section_id"] for item in selected] == ["docs/spec/main.md#beta"]
    item = selected[0]
    for field in (
        "target_section_id",
        "relation_hint",
        "confidence",
        "reason",
        "evidence_terms",
        "channels",
        "generated_at",
    ):
        assert field in item
    assert item["relation_hint"] in ALLOWED_RELATION_HINTS
    assert item["confidence"] in ALLOWED_CONFIDENCE
    assert "evidence" not in item
    assert "evidence_origin" not in item


def test_t_i06_fake_llm_selection_uses_only_candidates_and_builds_related_sections() -> None:
    module = _related_module()
    select = _required_function(
        module,
        (
            "select_related_sections",
            "select_related_sections_for_section",
            "generate_related_sections",
        ),
    )
    sections = _fixture_sections()
    candidates = [
        {
            "source_section_id": "docs/spec/main.md#alpha",
            "target_section_id": "docs/spec/main.md#beta",
            "heading_path": ["Chapter One", "Beta"],
            "summary": "Beta defines the freshness gate for auth token.",
            "search_keys": ["freshness gate"],
            "channels": ["markdown_link", "shared_identifier"],
            "candidate_score": 10,
            "evidence_terms": ["AUTH_TOKEN"],
            "evidence_snippets": ["Alpha links to Beta and shares AUTH_TOKEN."],
            "source": "candidate_generation",
            "generated_at": "2026-05-06T00:00:00Z",
        }
    ]
    provider = RelatedSelectionProvider(
        {
            "related_sections": [
                {
                    "target_section_id": "docs/spec/main.md#beta",
                    "relation_hint": "depends_on",
                    "confidence": "high",
                    "reason": "Alpha depends on the target auth policy.",
                    "evidence_terms": ["AUTH_TOKEN"],
                    "channels": ["markdown_link", "shared_identifier"],
                },
                {
                    "target_section_id": "docs/spec/other.md#delta",
                    "relation_hint": "see_also",
                    "confidence": "medium",
                    "reason": "Not a supplied candidate and must be dropped.",
                    "evidence_terms": ["freshness gate"],
                    "channels": ["search_key_match"],
                },
            ]
        }
    )

    payload = _call(
        select,
        _positional=("docs/spec/main.md#alpha", candidates, provider),
        source_section_id="docs/spec/main.md#alpha",
        source_section=sections[0],
        candidates=candidates,
        related_section_candidates=candidates,
        sections=sections,
        section_by_id={section["section_id"]: section for section in sections},
        provider=provider,
        llm_provider=provider,
        config=_config(),
        generated_at="2026-05-06T00:00:00Z",
    )
    selected = _related_sections(payload, "docs/spec/main.md#alpha")

    assert provider.calls, "Related Sections selection must call the fake LLM provider"
    prompt = provider.calls[0].prompt
    assert "docs/spec/main.md#beta" in prompt
    assert "docs/spec/other.md#delta" not in prompt
    assert "free discover" not in prompt.lower()

    assert [item["target_section_id"] for item in selected] == ["docs/spec/main.md#beta"]
    assert selected[0]["relation_hint"] in ALLOWED_RELATION_HINTS
    assert selected[0]["confidence"] in ALLOWED_CONFIDENCE


def test_related_sections_configured_provider_requires_real_provider_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("spec_grag.related_sections")
    monkeypatch.delenv("SPEC_GRAG_REAL_PROVIDER", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_SMOKE", raising=False)
    sections = _fixture_sections()
    candidates = [
        {
            "source_section_id": "docs/spec/main.md#alpha",
            "target_section_id": "docs/spec/main.md#beta",
            "relation_hint": "see_also",
            "confidence": "medium",
            "reason": "candidate",
            "evidence_terms": ["AUTH_TOKEN"],
            "channels": ["shared_identifier"],
        }
    ]
    config = _config()
    config.llm = SimpleNamespace(
        provider="codex_cli",
        command="codex",
        model="real-smoke",
        effort="low",
        timeout_sec=5,
        max_retries=0,
    )

    result = module.select_related_sections_result(
        sections,
        candidates=candidates,
        config=config,
        source_section_ids=["docs/spec/main.md#alpha"],
        generated_at="2026-05-06T00:00:00Z",
    )

    assert result.related_sections["docs/spec/main.md#alpha"] == []
    assert result.llm_results
    assert result.llm_results[0].status == "failed"
    assert "real_provider_required" in json.dumps(result.diagnostics)


def test_t_i12_incremental_reevaluation_includes_required_related_section_scope() -> None:
    module = _related_module()
    targets_for_change = _required_function(
        module,
        (
            "related_section_reevaluation_targets",
            "incremental_related_section_reevaluation_targets",
            "find_related_section_reevaluation_targets",
        ),
    )
    sections = _fixture_sections()
    previous_metadata = _metadata_for(sections)
    previous_metadata["sections"][0]["related_sections"] = [
        {
            "target_section_id": "docs/spec/main.md#beta",
            "relation_hint": "depends_on",
            "confidence": "high",
            "reason": "Existing inbound relation.",
            "evidence_terms": ["AUTH_TOKEN"],
            "channels": ["shared_identifier"],
            "generated_at": "2026-05-06T00:00:00Z",
        }
    ]
    changed = "docs/spec/main.md#beta"

    payload = _call(
        targets_for_change,
        _positional=({changed}, sections, previous_metadata),
        changed_section_ids={changed},
        changed_sections={changed},
        sections=sections,
        section_metadata=previous_metadata,
        previous_metadata=previous_metadata,
    )
    target_ids = set(payload if isinstance(payload, list | set | tuple) else payload["section_ids"])

    assert changed in target_ids
    assert "docs/spec/main.md#alpha" in target_ids
    assert "docs/spec/main.md#gamma" in target_ids
    assert "docs/spec/other.md#delta" in target_ids


def test_related_sections_are_reference_helpers_not_evidence() -> None:
    module = _related_module()
    build_candidates = _required_function(
        module,
        (
            "build_related_section_candidates",
            "generate_related_section_candidates",
            "build_related_sections_candidates",
        ),
    )
    sections = _fixture_sections()
    metadata = _metadata_for(sections)

    payload = _call(
        build_candidates,
        _positional=(sections,),
        sections=sections,
        section_metadata=metadata,
        metadata=metadata,
        config=_config(),
        limits=_config().limits,
        generated_at="2026-05-06T00:00:00Z",
    )
    candidates = _candidates(payload, "docs/spec/main.md#alpha")

    assert metadata["artifact_role"] == "retrieval_aid_not_evidence"
    assert metadata["summary_search_keys_are_evidence"] is False
    assert candidates
    for candidate in candidates:
        assert "evidence_origin" not in candidate
        assert "evidence_ref" not in candidate
        assert candidate["source"] in {"candidate_generation", "retrieval_auxiliary", "reference_helper"}
