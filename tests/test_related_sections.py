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

from spec_anchor.llm_provider import LlmRequest


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
    module = importlib.import_module("spec_anchor.section_metadata")
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
    # Phase C: candidate channels are now markdown_link / shared_identifier /
    # search_key_match / qdrant_section_hybrid. The old structural channels
    # (same_chapter / neighbor_section) and summary_search are removed.
    assert {"markdown_link", "shared_identifier", "search_key_match"}.issubset(beta["channels"])
    assert "docs/spec/main.md#missing" not in by_target
    assert source_id not in by_target

    assert "search_key_match" in by_target["docs/spec/other.md#delta"]["channels"]

    legacy_channels = {"same_chapter", "neighbor_section", "summary_search"}
    for candidate in candidates:
        assert not (set(candidate["channels"]) & legacy_channels), (
            f"legacy channels must not appear in candidates: {candidate['channels']}"
        )

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
        "evidence_terms",
        "channels",
        "generated_at",
    ):
        assert field in item
    assert "reason" not in item
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


def test_related_sections_configured_provider_runs_without_env_gate_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("spec_anchor.related_sections")
    monkeypatch.delenv("SPEC_ANCHOR_FAKE_LLM", raising=False)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=1, stderr="codex denied", stdout="")

    monkeypatch.setattr("spec_anchor.llm_provider.subprocess.run", fake_run)
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
        providers={
            "codex": SimpleNamespace(
                name="codex",
                command="codex",
                model="real-smoke",
                effort="low",
                timeout_sec=5,
                max_retries=0,
            ),
        },
        stage_routing={},
    )

    result = module.select_related_sections_result(
        sections,
        candidates=candidates,
        config=config,
        source_section_ids=["docs/spec/main.md#alpha"],
        generated_at="2026-05-06T00:00:00Z",
    )

    assert result.related_sections["docs/spec/main.md#alpha"] == []
    assert calls, "configured real provider must be called without env opt-in"
    assert result.llm_results
    assert result.llm_results[0].status == "failed"
    assert "codex denied" in json.dumps(result.diagnostics).lower()


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
    # alpha previously had beta as a selected related target → must re-evaluate
    assert "docs/spec/main.md#alpha" in target_ids
    # delta shares the specific search_key "freshness gate" with beta → must re-evaluate
    assert "docs/spec/other.md#delta" in target_ids
    # Phase F: gamma is NOT a target. The previous design used a chapter
    # neighbor heuristic that caught gamma simply because it was positionally
    # after beta in the same file; that channel was removed in Phase C, and
    # gamma shares no specific identifier / search_key with beta.


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


def test_specificity_filter_drops_generic_identifiers() -> None:
    module = importlib.import_module("spec_anchor.related_sections")
    # generic English & Japanese terms must be filtered out
    assert not module._is_specific_term("user")
    assert not module._is_specific_term("API")  # 3 chars
    assert not module._is_specific_term("ユーザー")
    assert not module._is_specific_term("123")
    assert not module._is_specific_term("a")
    # specific identifiers must pass
    assert module._is_specific_term("AUTH_TOKEN")
    assert module._is_specific_term("FreshnessGate")
    assert module._is_specific_term("auth.token.expiry")
    assert module._is_specific_term("freshness gate")


def test_qdrant_section_hybrid_channel_is_present_in_candidate_set() -> None:
    module = importlib.import_module("spec_anchor.related_sections")
    assert "qdrant_section_hybrid" in module.MVP_CANDIDATE_CHANNELS
    assert module.QDRANT_SECTION_HYBRID == "qdrant_section_hybrid"


def test_qdrant_section_hybrid_uses_retrieval_section_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-F-1: candidate generation reads only `[retrieval].section_collection`.
    The legacy `[vector_store].section_collection` / `[vector_store].collection`
    fallback chain was removed; the single key path is the only contract."""

    module = importlib.import_module("spec_anchor.related_sections")
    retrieval_module = importlib.import_module("spec_anchor.retrieval_index")
    sections = _fixture_sections()
    metadata = _metadata_for(sections)
    captured: dict[str, str] = {}

    class _Retriever:
        def __init__(self, *, url: str, collection: str) -> None:
            captured["url"] = url
            captured["collection"] = collection

        def search(self, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(hits=[])

    monkeypatch.setattr(retrieval_module, "QdrantHybridRetriever", _Retriever)

    module.generate_related_section_candidates(
        sections,
        section_metadata=metadata,
        config={
            "vector_store": {
                "provider": "qdrant",
                "url": "http://localhost:6333",
            },
            "embedding": {"provider": "flagembedding"},
            "retrieval": {
                "section_collection": "custom_section_collection",
                "section_candidate_top_k": 1,
            },
        },
        generated_at="2026-05-06T00:00:00Z",
    )

    assert captured["collection"] == "custom_section_collection"


def test_legacy_channels_are_removed_from_module() -> None:
    """T-Phase-C: regression guard for the deleted pattern-matching channels."""
    module = importlib.import_module("spec_anchor.related_sections")
    legacy_constants = {"SAME_CHAPTER", "NEIGHBOR_SECTION", "SUMMARY_SEARCH"}
    for name in legacy_constants:
        assert not hasattr(module, name), f"{name} must be removed from related_sections"
    legacy_helpers = {
        "_add_same_chapter_candidates",
        "_add_neighbor_candidates",
        "_add_summary_search_candidates",
    }
    for name in legacy_helpers:
        assert not hasattr(module, name), f"{name} must be removed from related_sections"
    assert "same_chapter" not in module.MVP_CANDIDATE_CHANNELS
    assert "neighbor_section" not in module.MVP_CANDIDATE_CHANNELS
    assert "summary_search" not in module.MVP_CANDIDATE_CHANNELS


def test_qdrant_section_hybrid_candidate_generation_produces_candidates() -> None:
    module = importlib.import_module("spec_anchor.related_sections")
    sections = _fixture_sections()
    metadata = _metadata_for(sections)
    payload = module.generate_related_section_candidates(
        sections,
        section_metadata=metadata,
        config=_config(candidate_max=32),
        generated_at="2026-05-06T00:00:00Z",
    )
    candidates = payload["related_section_candidates"]
    qdrant_candidates = [
        candidate
        for candidate in candidates
        if "qdrant_section_hybrid" in candidate["channels"]
    ]
    # The deterministic fake BGE-M3 vectors should produce at least one
    # qdrant_section_hybrid candidate across the 5-section fixture (Alpha and
    # Epsilon share repeated phrases in their summaries).
    assert qdrant_candidates, "qdrant_section_hybrid must contribute candidates"
    for candidate in qdrant_candidates:
        terms = candidate["evidence_terms"]
        assert any("section_similarity" in term for term in terms), terms


def test_aud007_qdrant_unconfigured_uses_inmemory_success() -> None:
    """AUD-007: Qdrant 未設定 (`vector_store.provider != "qdrant"`) では
    InMemoryHybridRetriever を最初から使い、`qdrant_backend_failure` は出ない。
    """
    module = importlib.import_module("spec_anchor.related_sections")
    sections = _fixture_sections()
    metadata = _metadata_for(sections)

    # vector_store.provider != "qdrant" の構成 (dev / test 用)
    result = module.generate_related_section_candidates_result(
        sections,
        section_metadata=metadata,
        config={
            "vector_store": {"provider": "", "url": ""},
            "embedding": {"provider": "flagembedding"},
            "retrieval": {"section_candidate_top_k": 4},
        },
        generated_at="2026-05-06T00:00:00Z",
    )
    assert result.qdrant_backend_failure is None
    payload = result.to_dict()
    assert "qdrant_backend_failure" not in payload
    # 旧 fallback 経路の握り潰し痕跡 (related_sections_qdrant_backend_failure
    # diagnostic) も出ない
    for diagnostic in payload["diagnostics"]:
        assert diagnostic.get("reason_code") != "related_sections_qdrant_backend_failure"


def test_aud007_qdrant_backend_initialization_failure_returns_failure_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUD-007: Qdrant 設定済みで `QdrantHybridRetriever` の `__init__` が
    例外を投げた場合、InMemory fallback には落ちず `qdrant_backend_failure`
    descriptor が candidate generation result に乗る (旧 silent fallback 削除)。
    """
    module = importlib.import_module("spec_anchor.related_sections")
    retrieval_module = importlib.import_module("spec_anchor.retrieval_index")
    sections = _fixture_sections()
    metadata = _metadata_for(sections)

    class _BrokenRetriever:
        def __init__(self, *, url: str, collection: str) -> None:
            raise RuntimeError("simulated qdrant connection refused")

    monkeypatch.setattr(retrieval_module, "QdrantHybridRetriever", _BrokenRetriever)

    result = module.generate_related_section_candidates_result(
        sections,
        section_metadata=metadata,
        config={
            "vector_store": {
                "provider": "qdrant",
                "url": "http://localhost:6333",
                "collection": "aud007_failed_collection",
            },
            "embedding": {"provider": "flagembedding"},
            "retrieval": {"section_candidate_top_k": 4},
        },
        generated_at="2026-05-06T00:00:00Z",
    )

    assert result.qdrant_backend_failure is not None
    failure = result.qdrant_backend_failure
    assert failure["expected_retrieval_backend"] == "qdrant"
    assert failure["actual_retrieval_backend"] == "unavailable"
    assert failure["fallback_attempted"] is False
    assert failure["qdrant_url_configured"] is True
    assert failure["embedding_provider"] == "flagembedding"
    assert "simulated qdrant connection refused" in failure["failure_reason"]

    # Qdrant 失敗時、Qdrant 由来の候補は 0 件 (InMemory fallback が走らない)
    qdrant_candidates = [
        candidate
        for candidate in result.related_section_candidates
        if "qdrant_section_hybrid" in candidate["channels"]
    ]
    assert qdrant_candidates == [], "no qdrant_section_hybrid candidate must be added on failure"

    # diagnostic が候補一覧に出ている
    diagnostic_codes = [str(item.get("reason_code") or "") for item in result.diagnostics]
    assert "related_sections_qdrant_backend_failure" in diagnostic_codes

    payload = result.to_dict()
    assert isinstance(payload["qdrant_backend_failure"], dict)
    assert payload["qdrant_backend_failure"]["expected_retrieval_backend"] == "qdrant"


def test_aud007_qdrant_normal_no_fallback_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUD-007: 正常に Qdrant が動く場合、`qdrant_backend_failure` は None。"""
    module = importlib.import_module("spec_anchor.related_sections")
    retrieval_module = importlib.import_module("spec_anchor.retrieval_index")
    sections = _fixture_sections()
    metadata = _metadata_for(sections)

    class _Retriever:
        def __init__(self, *, url: str, collection: str) -> None:
            self.url = url
            self.collection = collection

        def search(self, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(hits=[])

    monkeypatch.setattr(retrieval_module, "QdrantHybridRetriever", _Retriever)

    result = module.generate_related_section_candidates_result(
        sections,
        section_metadata=metadata,
        config={
            "vector_store": {
                "provider": "qdrant",
                "url": "http://localhost:6333",
                "collection": "aud007_normal_collection",
            },
            "embedding": {"provider": "flagembedding"},
            "retrieval": {"section_candidate_top_k": 4},
        },
        generated_at="2026-05-06T00:00:00Z",
    )

    assert result.qdrant_backend_failure is None
    payload = result.to_dict()
    assert "qdrant_backend_failure" not in payload
    diagnostic_codes = [str(item.get("reason_code") or "") for item in result.diagnostics]
    assert "related_sections_qdrant_backend_failure" not in diagnostic_codes


def test_llm_batch_concurrency_runs_batches_in_parallel() -> None:
    """Phase H follow-up: when llm_batch_concurrency > 1, batch loop submits
    multiple LLM calls concurrently. Verify by making provider sleep and
    asserting wall time < (sequential * concurrency) / concurrency.
    """
    import threading
    import time
    import importlib

    rs_module = importlib.import_module("spec_anchor.related_sections")

    sections_in = [
        {
            "section_id": f"doc#sec{i:03d}",
            "source_section_id": f"doc#sec{i:03d}",
            "stable_section_uid": f"uid-{i}",
            "source_document_id": "doc",
            "heading_path": ["Doc", f"Sec{i}"],
            "chapter_id": "doc#ch1",
            "source_hash": f"h{i}",
            "semantic_hash": f"h{i}",
            "source_span": {"start_line": i * 10, "end_line": i * 10 + 5},
            "text": f"Section {i} body referencing AUTH_TOKEN_{i % 4}.",
            "identifiers": [f"AUTH_TOKEN_{i % 4}"],
            "summary": f"Section {i} summary covering authentication scenario {i}.",
            "search_keys": [f"auth scenario {i % 4}", f"sec{i % 4} policy"],
        }
        for i in range(16)  # 2 batches of 8
    ]

    metadata = {
        "sections": [
            {
                "section_id": s["section_id"],
                "source_section_id": s["section_id"],
                "summary": s["summary"],
                "search_keys": s["search_keys"],
                "identifiers": s["identifiers"],
                "related_sections": [],
                "source_hash": s["source_hash"],
                "semantic_hash": s["semantic_hash"],
            }
            for s in sections_in
        ]
    }

    call_started_at: list[float] = []
    lock = threading.Lock()

    class SlowProvider:
        provider_id = "slow-fake"

        def generate(self, request, *, timeout_sec):
            with lock:
                call_started_at.append(time.monotonic())
            time.sleep(0.5)
            # Return valid empty batch output keyed by source_section_id
            return {"sections": []}

    cfg = SimpleNamespace(
        llm=SimpleNamespace(model="fake", effort="low", timeout_sec=5, max_retries=0),
        limits=SimpleNamespace(
            section_summary_max_chars=480,
            search_keys_max=32,
            related_candidate_max_per_section=32,
            related_selected_max_per_section=8,
            conflict_pair_max_per_section=8,
            llm_batch_max_sections=8,
            llm_batch_max_chars=12000,
            llm_batch_concurrency=4,
        ),
    )

    # Generate one candidate per source so all 16 sources are evaluable → 2 batches of 8.
    candidates = [
        {
            "source_section_id": f"doc#sec{i:03d}",
            "target_section_id": f"doc#sec{(i + 1) % 16:03d}",
            "channels": ["shared_identifier"],
            "candidate_score": 50.0,
            "evidence_terms": [f"AUTH_TOKEN_{i % 4}"],
            "evidence_snippets": [],
            "source": "candidate_generation",
            "generated_at": "2026-05-09T00:00:00Z",
        }
        for i in range(16)
    ]
    start = time.monotonic()
    result = rs_module.select_related_sections_result(
        sections_in,
        section_metadata=metadata,
        config=cfg,
        provider=SlowProvider(),
        candidates=candidates,
        generated_at="2026-05-09T00:00:00Z",
    )
    elapsed = time.monotonic() - start

    # 2 batches, each sleeping 0.5s. Sequential would take >= 1.0s.
    # Parallel (concurrency=4) should overlap → wall time < 0.9s.
    assert result.llm_calls == 2, f"expected 2 batches, got {result.llm_calls}"
    assert len(call_started_at) == 2
    # Both calls must start within ~0.1s of each other (parallel)
    delta = abs(call_started_at[0] - call_started_at[1])
    assert delta < 0.1, f"calls must be concurrent (delta={delta:.3f}s)"
    assert elapsed < 0.9, f"parallel batches must finish under 0.9s (got {elapsed:.3f}s)"


def test_llm_batch_concurrency_default_is_parallel() -> None:
    """Default concurrency=4 enables the parallel code path. Smoke test with
    empty inputs verifies the default-fallback path still terminates cleanly."""
    import importlib

    rs_module = importlib.import_module("spec_anchor.related_sections")
    cfg = SimpleNamespace(
        llm=SimpleNamespace(model="fake", effort="low", timeout_sec=5, max_retries=0),
        limits=SimpleNamespace(
            section_summary_max_chars=480,
            search_keys_max=32,
            related_candidate_max_per_section=32,
            related_selected_max_per_section=8,
            conflict_pair_max_per_section=8,
            llm_batch_max_sections=8,
            llm_batch_max_chars=12000,
            # No llm_batch_concurrency override: getattr default = 4
        ),
    )
    result = rs_module.select_related_sections_result(
        [],
        section_metadata={"sections": []},
        config=cfg,
        candidates=[],
        generated_at="2026-05-09T00:00:00Z",
    )
    assert result.llm_calls == 0


def test_pair_level_typing_cache_skips_unchanged_pairs(tmp_path: Path) -> None:
    """Pair cache should skip the LLM when source_hash + target_hash and other
    cache key components are unchanged from the previous run.
    """
    import importlib

    rs_module = importlib.import_module("spec_anchor.related_sections")
    cache_module = importlib.import_module("spec_anchor.related_typing_cache")

    sections_in = [
        {
            "section_id": "doc#a",
            "source_section_id": "doc#a",
            "stable_section_uid": "uid-a",
            "source_document_id": "doc",
            "heading_path": ["Doc", "A"],
            "chapter_id": "doc#ch1",
            "source_hash": "ha",
            "semantic_hash": "ha",
            "source_span": {"start_line": 0, "end_line": 5},
            "text": "A references TOKEN.",
            "identifiers": ["TOKEN"],
            "summary": "A summary",
            "search_keys": ["alpha key"],
        },
        {
            "section_id": "doc#b",
            "source_section_id": "doc#b",
            "stable_section_uid": "uid-b",
            "source_document_id": "doc",
            "heading_path": ["Doc", "B"],
            "chapter_id": "doc#ch1",
            "source_hash": "hb",
            "semantic_hash": "hb",
            "source_span": {"start_line": 10, "end_line": 15},
            "text": "B references TOKEN.",
            "identifiers": ["TOKEN"],
            "summary": "B summary",
            "search_keys": ["beta key"],
        },
    ]
    metadata = {
        "sections": [
            {
                "section_id": s["section_id"],
                "source_section_id": s["section_id"],
                "summary": s["summary"],
                "search_keys": s["search_keys"],
                "identifiers": s["identifiers"],
                "related_sections": [],
                "source_hash": s["source_hash"],
                "semantic_hash": s["semantic_hash"],
            }
            for s in sections_in
        ]
    }
    candidates = [
        {
            "source_section_id": "doc#a",
            "target_section_id": "doc#b",
            "channels": ["shared_identifier"],
            "candidate_score": 50.0,
            "evidence_terms": ["TOKEN"],
            "evidence_snippets": [],
            "source": "candidate_generation",
            "generated_at": "2026-05-10T00:00:00Z",
        }
    ]

    class CountingProvider:
        provider_id = "counting-fake"

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request, *, timeout_sec):
            self.calls += 1
            return {
                "sections": [
                    {
                        "source_section_id": "doc#a",
                        "related_sections": [
                            {
                                "target_section_id": "doc#b",
                                "relation_hint": "depends_on",
                                "confidence": "high",
                                "reason": "A depends on B for TOKEN policy.",
                                "evidence_terms": ["TOKEN"],
                                "channels": ["shared_identifier"],
                                "possible_conflict": False,
                            }
                        ],
                    }
                ]
            }

    cfg = SimpleNamespace(
        llm=SimpleNamespace(model="fake", effort="low", timeout_sec=5, max_retries=0),
        limits=SimpleNamespace(
            section_summary_max_chars=480,
            search_keys_max=32,
            related_candidate_max_per_section=32,
            related_selected_max_per_section=8,
            conflict_pair_max_per_section=8,
            llm_batch_max_sections=8,
            llm_batch_max_chars=12000,
        ),
    )

    cache_dir = tmp_path / "cache"
    provider = CountingProvider()
    result_first = rs_module.select_related_sections_result(
        sections_in,
        section_metadata=metadata,
        config=cfg,
        provider=provider,
        candidates=candidates,
        cache_dir=cache_dir,
        generated_at="2026-05-10T00:00:00Z",
    )
    assert provider.calls == 1, "first run must call LLM once"
    assert result_first.related_sections["doc#a"], "first run must produce edges"
    cache_file = cache_dir / cache_module.CACHE_FILE_NAME
    assert cache_file.exists(), "cache file must be persisted"

    # Second run: no source/target hash change → all candidates served from cache.
    provider2 = CountingProvider()
    result_second = rs_module.select_related_sections_result(
        sections_in,
        section_metadata=metadata,
        config=cfg,
        provider=provider2,
        candidates=candidates,
        cache_dir=cache_dir,
        generated_at="2026-05-10T00:00:00Z",
    )
    assert provider2.calls == 0, "second run must NOT call LLM (pair cache hit)"
    assert (
        result_second.related_sections["doc#a"][0]["target_section_id"] == "doc#b"
    ), "cached entries must populate related_sections"

    # Third run: change target hash → cache miss → LLM is called again.
    sections_in[1]["source_hash"] = "hb-v2"
    sections_in[1]["semantic_hash"] = "hb-v2"
    metadata["sections"][1]["source_hash"] = "hb-v2"
    metadata["sections"][1]["semantic_hash"] = "hb-v2"
    provider3 = CountingProvider()
    rs_module.select_related_sections_result(
        sections_in,
        section_metadata=metadata,
        config=cfg,
        provider=provider3,
        candidates=candidates,
        cache_dir=cache_dir,
        generated_at="2026-05-10T00:00:00Z",
    )
    assert provider3.calls == 1, "target hash change must invalidate the pair cache"
