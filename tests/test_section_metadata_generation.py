"""Section Metadata generation contract tests for G-06.

The generator is expected to batch `/spec-core` LLM calls, apply configured
limits, and reuse unchanged section metadata during incremental updates.
"""

from __future__ import annotations

import importlib
import inspect
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
from spec_grag.section_parser import Section, parse_markdown_sections


@dataclass
class RecordingSectionMetadataProvider:
    epoch: str = "v1"
    long_summary_chars: int = 96
    key_count: int = 8

    def __post_init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def provider_id(self) -> str:
        return "recording-section-metadata-fake"

    def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
        section_ids = list(request.section_hashes)
        if not section_ids and request.section_id is not None:
            section_ids = [request.section_id]
        self.calls.append(
            {
                "section_ids": section_ids,
                "prompt_chars": len(request.prompt),
                "timeout_sec": timeout_sec,
                "stage": request.stage,
            }
        )
        return {
            "sections": [
                {
                    "section_id": section_id,
                    "summary": (
                        f"{self.epoch}:{section_id}:"
                        + "S" * max(0, self.long_summary_chars)
                    ),
                    "search_keys": [
                        f"{self.epoch}:{section_id}:key-{index}"
                        for index in range(self.key_count)
                    ],
                    "identifiers": [f"id:{section_id}"],
                    "related_sections": [
                        {"target_section_id": "outside-slice", "relation_hint": "see_also"}
                    ],
                }
                for section_id in section_ids
            ],
        }


def _sections(markdown: str | None = None) -> list[Section]:
    return parse_markdown_sections(
        markdown
        or """\
# Chapter
chapter intro
## Alpha
Alpha requirement body.
## Beta
Beta requirement body.
## Gamma
Gamma requirement body.
## Delta
Delta requirement body.
""",
        source_path="docs/spec/main.md",
        max_heading_level=4,
    )


def _config(
    *,
    summary_max: int = 48,
    search_keys_max: int = 3,
    batch_max_sections: int = 3,
    batch_max_chars: int = 1200,
) -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(model="fake-model", effort="low", timeout_sec=5, max_retries=0),
        limits=SimpleNamespace(
            section_summary_max_chars=summary_max,
            search_keys_max=search_keys_max,
            related_candidate_max_per_section=32,
            related_selected_max_per_section=8,
            conflict_pair_max_per_section=8,
            llm_batch_max_sections=batch_max_sections,
            llm_batch_max_chars=batch_max_chars,
        ),
        section_metadata=SimpleNamespace(
            summary_enabled=True,
            search_keys_enabled=True,
            related_sections_enabled=True,
        ),
    )


def _generate(
    sections: list[Section],
    *,
    provider: Any,
    config: Any,
    previous_metadata: Any | None = None,
    rebuild_all: bool = True,
) -> Any:
    try:
        module = importlib.import_module("spec_grag.section_metadata")
    except ModuleNotFoundError as exc:
        if exc.name == "spec_grag.section_metadata":
            pytest.fail(
                "spec_grag.section_metadata module is required for G-06 "
                "Section Metadata generation"
            )
        raise
    generate = getattr(module, "generate_section_metadata", None)
    assert callable(
        generate
    ), "spec_grag.section_metadata.generate_section_metadata(...) is required"

    signature = inspect.signature(generate)
    kwargs: dict[str, Any] = {}
    for name in signature.parameters:
        if name == "sections":
            kwargs[name] = sections
        elif name in {"config", "project_config"}:
            kwargs[name] = config
        elif name in {"provider", "llm_provider"}:
            kwargs[name] = provider
        elif name in {"previous_metadata", "existing_metadata", "current_metadata"}:
            kwargs[name] = previous_metadata
        elif name in {"rebuild_all", "all_sections"}:
            kwargs[name] = rebuild_all
        elif name in {"force_all", "run_all"}:
            kwargs[name] = rebuild_all

    try:
        return generate(**kwargs)
    except TypeError:
        return generate(
            sections,
            config=config,
            provider=provider,
            previous_metadata=previous_metadata,
            rebuild_all=rebuild_all,
        )


def _metadata_sections(payload: Any) -> list[dict[str, Any]]:
    if hasattr(payload, "section_metadata"):
        payload = payload.section_metadata
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = payload["sections"]
    else:
        entries = getattr(payload, "sections")
    return [entry if isinstance(entry, dict) else vars(entry) for entry in entries]


def _by_section_id(payload: Any) -> dict[str, dict[str, Any]]:
    return {entry["section_id"]: entry for entry in _metadata_sections(payload)}


REQUIRED_SECTION_METADATA_FIELDS = (
    "section_id",
    "stable_section_uid",
    "source_document_id",
    "heading_path",
    "summary",
    "search_keys",
    "identifiers",
    "related_sections",
    "metadata_version",
    "source_hash",
    "semantic_hash",
    "generated_at",
)


def test_t_u19_limits_are_applied_to_metadata_and_llm_batches() -> None:
    sections = _sections()
    config = _config(
        summary_max=24,
        search_keys_max=2,
        batch_max_sections=2,
        batch_max_chars=1200,
    )
    provider = RecordingSectionMetadataProvider(long_summary_chars=120, key_count=6)

    payload = _generate(
        sections,
        provider=provider,
        config=config,
        rebuild_all=True,
    )
    entries = _metadata_sections(payload)

    assert len(entries) == len(sections)
    for entry in entries:
        assert len(entry["summary"]) <= config.limits.section_summary_max_chars
        assert len(entry["search_keys"]) <= config.limits.search_keys_max
        assert entry["related_sections"] == []
        assert "evidence" not in entry
        assert "source_references" not in entry

    assert 1 < len(provider.calls) < len(sections)
    for call in provider.calls:
        assert 1 <= len(call["section_ids"]) <= config.limits.llm_batch_max_sections
        assert call["prompt_chars"] <= config.limits.llm_batch_max_chars


def test_t_u21_generated_section_metadata_entries_have_required_fields() -> None:
    sections = _sections()
    provider = RecordingSectionMetadataProvider(epoch="full")

    payload = _generate(
        sections,
        provider=provider,
        config=_config(),
        rebuild_all=True,
    )

    for entry in _metadata_sections(payload):
        for field in REQUIRED_SECTION_METADATA_FIELDS:
            assert field in entry
        assert isinstance(entry["search_keys"], list)
        assert isinstance(entry["identifiers"], list)
        assert isinstance(entry["related_sections"], list)


def test_section_metadata_configured_provider_runs_without_env_gate_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("spec_grag.section_metadata")
    monkeypatch.delenv("SPEC_GRAG_FAKE_LLM", raising=False)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=1, stderr="codex denied", stdout="")

    monkeypatch.setattr("spec_grag.llm_provider.subprocess.run", fake_run)

    result = module.generate_section_metadata_result(
        _sections()[:1],
        config=SimpleNamespace(
            llm=SimpleNamespace(
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
            ),
            limits=_config().limits,
            section_metadata=_config().section_metadata,
        ),
        rebuild_all=True,
    )

    entry = result.entries[0]
    assert calls, "configured real provider must be called without env opt-in"
    assert entry["summary"] == ""
    assert result.llm_results[0].status == "failed"
    assert "codex denied" in str(result.diagnostics).lower()


def test_t_i01_incremental_regenerates_only_changed_source_hash_section() -> None:
    initial_sections = _sections()
    initial_provider = RecordingSectionMetadataProvider(epoch="initial")
    config = _config(batch_max_sections=3)

    initial_payload = _generate(
        initial_sections,
        provider=initial_provider,
        config=config,
        rebuild_all=True,
    )

    changed_sections = _sections(
        """\
# Chapter
chapter intro
## Alpha
Alpha requirement body.
## Beta
Beta requirement body changed.
## Gamma
Gamma requirement body.
## Delta
Delta requirement body.
"""
    )
    changed_section = next(
        section for section in changed_sections if section.heading_path[-1] == "Beta"
    )
    incremental_provider = RecordingSectionMetadataProvider(epoch="incremental")

    incremental_payload = _generate(
        changed_sections,
        provider=incremental_provider,
        config=config,
        previous_metadata=initial_payload,
        rebuild_all=False,
    )

    before = _by_section_id(initial_payload)
    after = _by_section_id(incremental_payload)
    regenerated_ids = [
        section_id
        for call in incremental_provider.calls
        for section_id in call["section_ids"]
    ]

    assert regenerated_ids == [changed_section.section_id]
    for section in changed_sections:
        entry = after[section.section_id]
        if section.section_id == changed_section.section_id:
            assert entry["summary"].startswith("incremental:")
            assert entry["source_hash"] == section.source_hash
            assert entry["summary"] != before[section.section_id]["summary"]
        else:
            assert entry["summary"] == before[section.section_id]["summary"]
            assert entry["search_keys"] == before[section.section_id]["search_keys"]


@dataclass
class IdentifierLikeSearchKeyProvider:
    """LLM stub that emits a mix of identifier-shaped and natural-language keys.

    Used to verify that the search_keys post-process filter (search_keys and
    identifiers must remain disjoint) drops code-shaped tokens before the
    entry is materialized.
    """

    def __post_init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.last_prompt: str = ""

    @property
    def provider_id(self) -> str:
        return "identifier-like-search-key-fake"

    def generate(self, request: LlmRequest, *, timeout_sec: int) -> dict[str, Any]:
        self.last_prompt = request.prompt
        section_ids = list(request.section_hashes)
        if not section_ids and request.section_id is not None:
            section_ids = [request.section_id]
        self.calls.append({"section_ids": section_ids})
        return {
            "sections": [
                {
                    "section_id": section_id,
                    "summary": f"summary for {section_id}",
                    "search_keys": [
                        "context registration",
                        "再登録の挙動",
                        "bindContext",
                        "productStoreGroup.replace",
                        "--rebuild",
                        "/spec-core",
                        "BINDING_KEY",
                        "PascalName",
                        "config.toml",
                        "freshness gate",
                    ],
                }
                for section_id in section_ids
            ],
        }


def test_search_keys_and_identifiers_are_disjoint() -> None:
    sections = _sections()
    provider = IdentifierLikeSearchKeyProvider()

    payload = _generate(
        sections,
        provider=provider,
        config=_config(search_keys_max=32, batch_max_sections=4, batch_max_chars=8000),
        rebuild_all=True,
    )

    for entry in _metadata_sections(payload):
        search_keys = list(entry["search_keys"])
        identifiers = list(entry["identifiers"])
        # Role separation: search_keys (natural language) and identifiers
        # (code symbols) must not overlap.
        assert set(search_keys).isdisjoint(set(identifiers)), (
            f"search_keys and identifiers must be disjoint, "
            f"got overlap {set(search_keys) & set(identifiers)} "
            f"for section {entry['section_id']}"
        )
        # Identifier-shaped tokens emitted by the LLM stub must be dropped.
        for forbidden in (
            "bindContext",
            "productStoreGroup.replace",
            "--rebuild",
            "/spec-core",
            "BINDING_KEY",
            "PascalName",
            "config.toml",
        ):
            assert forbidden not in search_keys, (
                f"identifier-like token {forbidden!r} leaked into search_keys "
                f"for section {entry['section_id']}: {search_keys}"
            )
        # Natural-language phrases must survive the filter.
        assert "context registration" in search_keys
        assert "freshness gate" in search_keys


def test_section_metadata_prompt_includes_role_constraint_instructions() -> None:
    module = importlib.import_module("spec_grag.section_metadata")
    sections = _sections()
    provider = IdentifierLikeSearchKeyProvider()

    _generate(
        sections,
        provider=provider,
        config=_config(batch_max_sections=4, batch_max_chars=8000),
        rebuild_all=True,
    )

    assert provider.last_prompt, "prompt must be sent to the LLM provider"
    prompt = provider.last_prompt
    assert "search_keys" in prompt
    assert "identifiers" in prompt
    assert "natural language" in prompt.lower()
    assert "code symbols" in prompt.lower()
    # Confirm the canonical instructions module constant is the source.
    assert module._SEARCH_KEYS_INSTRUCTIONS in prompt


def test_section_metadata_prompt_version_is_v2() -> None:
    module = importlib.import_module("spec_grag.section_metadata")
    assert module.SECTION_METADATA_PROMPT_VERSION == "section-metadata-v2", (
        "Phase R-0 requires the section_metadata prompt_version to be bumped to "
        "section-metadata-v2 so existing caches are invalidated."
    )


def test_t_i02_full_generation_regenerates_all_metadata_with_batching() -> None:
    sections = _sections()
    config = _config(batch_max_sections=3)
    initial_payload = _generate(
        sections,
        provider=RecordingSectionMetadataProvider(epoch="initial"),
        config=config,
        rebuild_all=True,
    )
    provider = RecordingSectionMetadataProvider(epoch="rebuild")

    rebuilt_payload = _generate(
        sections,
        provider=provider,
        config=config,
        previous_metadata=initial_payload,
        rebuild_all=True,
    )

    entries = _metadata_sections(rebuilt_payload)
    regenerated_ids = [
        section_id
        for call in provider.calls
        for section_id in call["section_ids"]
    ]

    assert len(entries) == len(sections)
    assert regenerated_ids == [section.section_id for section in sections]
    assert 1 < len(provider.calls) < len(sections)
    assert all(entry["summary"].startswith("rebuild:") for entry in entries)
