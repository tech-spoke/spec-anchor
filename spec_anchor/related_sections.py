"""Related Sections candidate generation and LLM selection.

Related Sections are retrieval aids for Agentic Search. They are not final
evidence; callers must verify Purpose, Core Concept, Source Specs, or resolved
Conflict Review Items before turning a related link into a constraint.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from spec_anchor.config import LimitsConfig
from spec_anchor.llm_provider import (
    DEFAULT_METADATA_VERSION,
    FakeLlmProvider,
    LlmGenerationResult,
    LlmProvider,
    LlmRequest,
    build_spec_core_llm_provider,
    generate_with_retries,
    select_llm_provider_config,
)
from spec_anchor.related_typing_cache import (
    CACHE_FILE_NAME as RELATED_TYPING_CACHE_FILE_NAME,
    RelatedTypingCache,
    make_related_typing_cache_key,
)
from spec_anchor.section_metadata import extract_identifiers


RELATED_SECTIONS_PROMPT_VERSION = "related-sections-v1"
RELATED_SECTIONS_ROLE = "related_sections_retrieval_aid_not_evidence"
RELATED_SECTIONS_STAGE = "related_section_selection"
RELATED_SECTIONS_SOURCE = "candidate_generation"

MARKDOWN_LINK = "markdown_link"
SHARED_IDENTIFIER = "shared_identifier"
SEARCH_KEY_MATCH = "search_key_match"
QDRANT_SECTION_HYBRID = "qdrant_section_hybrid"

MVP_CANDIDATE_CHANNELS = (
    MARKDOWN_LINK,
    SHARED_IDENTIFIER,
    SEARCH_KEY_MATCH,
    QDRANT_SECTION_HYBRID,
)
EXACT_CHANNELS = {MARKDOWN_LINK, SHARED_IDENTIFIER, SEARCH_KEY_MATCH}
SEMANTIC_CHANNELS = {QDRANT_SECTION_HYBRID}

ALLOWED_RELATION_HINTS = {
    "depends_on",
    "impacts",
    "same_policy",
    "prerequisite",
    "see_also",
}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}

CHANNEL_WEIGHTS = {
    MARKDOWN_LINK: 100.0,
    SHARED_IDENTIFIER: 90.0,
    SEARCH_KEY_MATCH: 80.0,
    QDRANT_SECTION_HYBRID: 60.0,
}
CHANNEL_ORDER = {channel: index for index, channel in enumerate(MVP_CANDIDATE_CHANNELS)}

_GENERIC_TERMS = frozenset(
    {
        "user",
        "users",
        "data",
        "info",
        "config",
        "configuration",
        "test",
        "tests",
        "section",
        "sections",
        "summary",
        "spec",
        "specs",
        "source",
        "value",
        "values",
        "input",
        "output",
        "field",
        "fields",
        "name",
        "names",
        "type",
        "types",
        "auth",
        "api",
        "url",
        "key",
        "keys",
        "id",
        "ids",
        "ユーザー",
        "データ",
        "設定",
        "認証",
        "テスト",
    }
)


def _is_specific_term(value: Any) -> bool:
    cleaned = str(value).strip()
    if len(cleaned) < 4:
        return False
    if cleaned.isdigit():
        return False
    if _normalize_key(cleaned) in _GENERIC_TERMS:
        return False
    return True


def _filter_specific_terms(values: Sequence[Any]) -> list[str]:
    return [str(value) for value in values if _is_specific_term(value)]

_LINK_RE = re.compile(
    r"(?<!!)\[([^\]\n]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)",
)
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class RelatedSectionCandidateGeneration:
    related_section_candidates: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    candidate_count_by_source: dict[str, int]
    dropped_candidate_count_by_source: dict[str, int]
    generated_at: str
    elapsed_sec: float
    qdrant_backend_failure: dict[str, Any] | None = None

    @property
    def candidates(self) -> list[dict[str, Any]]:
        return self.related_section_candidates

    def to_dict(self) -> dict[str, Any]:
        limit_events = _related_candidate_limit_events(self.diagnostics)
        payload: dict[str, Any] = {
            "artifact_role": RELATED_SECTIONS_ROLE,
            "artifact_kind": "retrieval_auxiliary",
            "retrieval_auxiliary": True,
            "retrieval_aid_not_evidence": True,
            "reference_helper": True,
            "evidence": False,
            "related_sections_are_evidence": False,
            "metadata": _retrieval_auxiliary_metadata(),
            "related_section_candidates": list(self.related_section_candidates),
            "related_candidate_limit_events": limit_events,
            "diagnostics": list(self.diagnostics),
            "candidate_count_by_source": dict(self.candidate_count_by_source),
            "dropped_candidate_count_by_source": dict(
                self.dropped_candidate_count_by_source,
            ),
            "generated_at": self.generated_at,
            "elapsed_sec": self.elapsed_sec,
        }
        if self.qdrant_backend_failure is not None:
            payload["qdrant_backend_failure"] = dict(self.qdrant_backend_failure)
        return payload


@dataclass(frozen=True)
class RelatedSectionValidation:
    related_sections: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_role": RELATED_SECTIONS_ROLE,
            "artifact_kind": "retrieval_auxiliary",
            "retrieval_auxiliary": True,
            "retrieval_aid_not_evidence": True,
            "reference_helper": True,
            "evidence": False,
            "related_sections_are_evidence": False,
            "metadata": _retrieval_auxiliary_metadata(),
            "related_sections": list(self.related_sections),
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class RelatedSectionSelection:
    related_sections: dict[str, list[dict[str, Any]]]
    sections: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    llm_results: list[LlmGenerationResult]
    llm_calls: int
    generated_at: str
    elapsed_sec: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_role": RELATED_SECTIONS_ROLE,
            "artifact_kind": "retrieval_auxiliary",
            "retrieval_auxiliary": True,
            "retrieval_aid_not_evidence": True,
            "reference_helper": True,
            "evidence": False,
            "related_sections_are_evidence": False,
            "metadata": _retrieval_auxiliary_metadata(),
            "related_sections": {
                source_id: list(items)
                for source_id, items in self.related_sections.items()
            },
            "sections": list(self.sections),
            "diagnostics": list(self.diagnostics),
            "llm_calls": self.llm_calls,
            "generated_at": self.generated_at,
            "elapsed_sec": self.elapsed_sec,
        }


@dataclass(frozen=True)
class RelatedSectionsGeneration:
    artifact: dict[str, Any]
    candidate_generation: RelatedSectionCandidateGeneration
    selection: RelatedSectionSelection
    diagnostics: list[dict[str, Any]]

    @property
    def related_section_candidates(self) -> list[dict[str, Any]]:
        return self.candidate_generation.related_section_candidates

    @property
    def related_sections(self) -> dict[str, list[dict[str, Any]]]:
        return self.selection.related_sections

    def to_dict(self) -> dict[str, Any]:
        return dict(self.artifact)


@dataclass(frozen=True)
class _SectionRecord:
    section_id: str
    source_section_id: str
    stable_section_uid: str
    source_document_id: str
    heading_path: list[str]
    chapter_id: str
    source_hash: str
    semantic_hash: str
    text: str


@dataclass(frozen=True)
class _MetadataRecord:
    section_id: str
    summary: str
    search_keys: list[str]
    identifiers: list[str]
    related_sections: list[dict[str, Any]]


@dataclass
class _CandidateBuilder:
    source_section_id: str
    target_section_id: str
    channels: set[str]
    evidence_terms: list[str]
    evidence_snippets: list[str]
    generated_at: str
    source: str = RELATED_SECTIONS_SOURCE

    def add(
        self,
        *,
        channel: str,
        evidence_terms: Sequence[str] = (),
        evidence_snippets: Sequence[str] = (),
    ) -> None:
        self.channels.add(channel)
        for term in evidence_terms:
            _append_unique(self.evidence_terms, _normalize_public_text(term))
        for snippet in evidence_snippets:
            _append_unique(self.evidence_snippets, _short_text(snippet, 240))

    def to_candidate(self) -> dict[str, Any]:
        channels = sorted(self.channels, key=lambda item: CHANNEL_ORDER.get(item, 999))
        base_score = max(CHANNEL_WEIGHTS.get(channel, 0.0) for channel in channels)
        channel_bonus = min(5.0, max(0, len(channels) - 1) * 1.0)
        evidence_bonus = min(3.0, len(self.evidence_terms) * 0.25)
        return {
            "source_section_id": self.source_section_id,
            "target_section_id": self.target_section_id,
            "channels": channels,
            "candidate_score": round(base_score + channel_bonus + evidence_bonus, 6),
            "evidence_terms": list(self.evidence_terms),
            "evidence_snippets": list(self.evidence_snippets),
            "source": self.source,
            "generated_at": self.generated_at,
        }


def generate_related_section_candidates_result(
    sections: Sequence[Any],
    *,
    section_metadata: Any | None = None,
    metadata: Any | None = None,
    config: Any | None = None,
    project_config: Any | None = None,
    limits: Any | None = None,
    source_section_ids: Sequence[str] | None = None,
    generated_at: str | None = None,
) -> RelatedSectionCandidateGeneration:
    """Build high-recall Related Section candidates from deterministic channels."""

    start = time.perf_counter()
    generated_at = generated_at or _now()
    records = [_normalize_section(section) for section in sections]
    records_by_id = {record.source_section_id: record for record in records}
    source_section_id_set = (
        {str(section_id) for section_id in source_section_ids if str(section_id)}
        if source_section_ids is not None
        else None
    )
    if source_section_id_set is None:
        source_records = records
        candidate_generation_partial_mode = "full"
    else:
        source_records = [
            record
            for record in records
            if record.source_section_id in source_section_id_set
        ]
        candidate_generation_partial_mode = "source_changed_only"
    metadata_by_id = _metadata_records(
        _first_not_none(section_metadata, metadata),
        records,
    )
    limits_config = _limits(_first_not_none(limits, _config_value(config, "limits", None), _config_value(project_config, "limits", None)))
    retrieval_config = _first_not_none(
        _config_value(config, "retrieval", None),
        _config_value(project_config, "retrieval", None),
    )
    section_top_k = int(
        _config_value(retrieval_config, "section_candidate_top_k", 16)
        if retrieval_config is not None
        else 16
    )
    section_dense_threshold = float(
        _config_value(retrieval_config, "section_dense_threshold", 0.55)
        if retrieval_config is not None
        else 0.55
    )
    section_final_top_n = int(
        _config_value(retrieval_config, "section_final_top_n", 8)
        if retrieval_config is not None
        else 8
    )
    vector_store_config = _first_not_none(
        _config_value(config, "vector_store", None),
        _config_value(project_config, "vector_store", None),
    )
    embedding_config = _first_not_none(
        _config_value(config, "embedding", None),
        _config_value(project_config, "embedding", None),
    )
    qdrant_url = (
        str(_config_value(vector_store_config, "url", "") or "")
        if vector_store_config is not None
        else ""
    )
    qdrant_provider = (
        str(_config_value(vector_store_config, "provider", "") or "")
        if vector_store_config is not None
        else ""
    )
    section_collection = str(
        _config_value(retrieval_config, "section_collection", "spec_anchor_section")
        or "spec_anchor_section"
    )
    embedding_provider_id = (
        str(_config_value(embedding_config, "provider", "") or "")
        if embedding_config is not None
        else ""
    )
    use_real_qdrant_section = (
        qdrant_provider == "qdrant"
        and bool(qdrant_url)
        and embedding_provider_id == "flagembedding"
    )

    builders: dict[tuple[str, str], _CandidateBuilder] = {}

    _add_markdown_link_candidates(
        builders,
        source_records,
        records_by_id,
        metadata_by_id,
        generated_at,
    )
    _add_shared_identifier_candidates(
        builders,
        source_records,
        metadata_by_id,
        generated_at,
        full_records=records,
        source_section_ids=source_section_id_set,
    )
    _add_search_key_candidates(
        builders,
        source_records,
        metadata_by_id,
        generated_at,
        full_records=records,
        source_section_ids=source_section_id_set,
    )
    qdrant_backend_failure = _add_qdrant_section_hybrid_candidates(
        builders,
        source_records,
        records_by_id,
        metadata_by_id,
        generated_at,
        full_records=records,
        top_k=section_top_k,
        dense_threshold=section_dense_threshold,
        final_top_n=section_final_top_n,
        use_real_qdrant=use_real_qdrant_section,
        qdrant_url=qdrant_url,
        qdrant_collection=section_collection,
        embedding_provider_id=embedding_provider_id,
    )

    all_candidates = [builder.to_candidate() for builder in builders.values()]
    candidates, diagnostics, counts, dropped_counts = _limit_candidates_by_source(
        all_candidates,
        source_records,
        limits_config,
    )
    elapsed_sec = time.perf_counter() - start
    diagnostics.append(
        _diagnostic(
            "related_section_candidate_generation_scope",
            "Related Section candidates were generated for the selected source scope.",
            stage=RELATED_SECTIONS_SOURCE,
            severity="info",
            candidate_generation_partial_mode=candidate_generation_partial_mode,
            candidate_generation_source_count=len(source_records),
            candidate_generation_elapsed_sec=elapsed_sec,
        ),
    )
    if qdrant_backend_failure is not None:
        diagnostics.append(
            _diagnostic(
                "related_sections_qdrant_backend_failure",
                "Qdrant retrieval backend was configured but could not be initialized; "
                "no Qdrant-driven candidates were added and Related Sections must be "
                "marked failed by the caller.",
                stage=RELATED_SECTIONS_SOURCE,
                severity="error",
                **qdrant_backend_failure,
            ),
        )
    return RelatedSectionCandidateGeneration(
        related_section_candidates=candidates,
        diagnostics=diagnostics,
        candidate_count_by_source=counts,
        dropped_candidate_count_by_source=dropped_counts,
        generated_at=generated_at,
        elapsed_sec=elapsed_sec,
        qdrant_backend_failure=dict(qdrant_backend_failure)
        if qdrant_backend_failure is not None
        else None,
    )


def generate_related_section_candidates(
    sections: Sequence[Any],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Return a related_section_candidates artifact payload."""

    _apply_positional_kwargs(
        kwargs,
        args,
        ("section_metadata", "config", "limits"),
        "generate_related_section_candidates",
    )
    return generate_related_section_candidates_result(sections, **kwargs).to_dict()


def build_related_section_candidates(
    sections: Sequence[Any],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    _apply_positional_kwargs(
        kwargs,
        args,
        ("section_metadata", "config", "limits"),
        "build_related_section_candidates",
    )
    return generate_related_section_candidates(sections, **kwargs)


def select_related_sections_result(
    sections: Sequence[Any],
    *,
    candidates: Any | None = None,
    related_section_candidates: Any | None = None,
    section_metadata: Any | None = None,
    metadata: Any | None = None,
    config: Any | None = None,
    project_config: Any | None = None,
    provider: LlmProvider | None = None,
    llm_provider: LlmProvider | None = None,
    llm_config: Any | None = None,
    limits: Any | None = None,
    source_section_ids: Sequence[str] | None = None,
    reevaluate_section_ids: Sequence[str] | None = None,
    generated_at: str | None = None,
    prompt_version: str = RELATED_SECTIONS_PROMPT_VERSION,
    metadata_version: int = DEFAULT_METADATA_VERSION,
    cache_dir: Any | None = None,
) -> RelatedSectionSelection:
    """Run LLM selection over CLI-generated candidates only."""

    start = time.perf_counter()
    generated_at = generated_at or _now()
    records = [_normalize_section(section) for section in sections]
    records_by_id = {record.source_section_id: record for record in records}
    metadata_by_id = _metadata_records(
        _first_not_none(section_metadata, metadata),
        records,
    )
    limits_config = _limits(_first_not_none(limits, _config_value(config, "limits", None), _config_value(project_config, "limits", None)))
    llm_config = _first_not_none(
        llm_config,
        _config_value(config, "llm", None),
        _config_value(project_config, "llm", None),
    )
    llm_config = _selected_llm_config(llm_config)
    provider = _resolve_selection_provider(
        _first_not_none(provider, llm_provider),
        llm_config,
    )
    provider_id = str(getattr(provider, "provider_id", provider.__class__.__name__))
    model = _model_name(llm_config, provider_id)
    timeout_sec = int(_config_value(llm_config, "timeout_sec", 120))
    max_retries = int(_config_value(llm_config, "max_retries", 1))
    effort = _config_value(llm_config, "effort", None)

    candidate_input = _first_not_none(candidates, related_section_candidates)
    requested_source_input = _first_not_none(source_section_ids, reevaluate_section_ids)
    if candidate_input is None:
        candidate_input = generate_related_section_candidates_result(
            records,
            section_metadata=metadata_by_id,
            limits=limits_config,
            source_section_ids=requested_source_input,
            generated_at=generated_at,
        )
    candidate_items = _coerce_candidate_items(candidate_input)
    candidates_by_source = _candidates_by_source(candidate_items, records_by_id)

    requested = _requested_source_ids(
        records,
        requested_source_input,
    )
    related_by_source: dict[str, list[dict[str, Any]]] = {}
    diagnostics: list[dict[str, Any]] = []
    llm_results: list[LlmGenerationResult] = []

    cache_path: Any | None = None
    if cache_dir is not None:
        try:
            from pathlib import Path as _Path
            cache_path = _Path(cache_dir) / RELATED_TYPING_CACHE_FILE_NAME
        except Exception:
            cache_path = None
    typing_cache = RelatedTypingCache(cache_path)
    cache_hits = 0
    cache_misses = 0
    cache_rejected_hits = 0
    cached_entries_by_source: dict[str, list[dict[str, Any]]] = {}
    pending_candidates_by_source: dict[str, list[Mapping[str, Any]]] = {}
    pending_keys_by_source: dict[str, dict[str, str]] = {}

    sources_to_evaluate: list[_SectionRecord] = []
    for source_id in requested:
        source = records_by_id.get(source_id)
        if source is None:
            diagnostics.append(
                _diagnostic(
                    "unknown_source_section",
                    f"source_section_id does not exist: {source_id}",
                    source_section_id=source_id,
                ),
            )
            continue
        source_candidates = candidates_by_source.get(source_id, [])
        if not source_candidates or limits_config.related_selected_max_per_section <= 0:
            related_by_source[source_id] = []
            continue

        cached_entries: list[dict[str, Any]] = []
        pending_candidates: list[Mapping[str, Any]] = []
        pending_keys: dict[str, str] = {}
        for candidate in source_candidates:
            target_id = str(candidate.get("target_section_id", ""))
            target_record = records_by_id.get(target_id)
            if not target_id or target_record is None:
                pending_candidates.append(candidate)
                continue
            cache_key = make_related_typing_cache_key(
                source_section_id=source_id,
                target_section_id=target_id,
                source_hash=source.source_hash,
                target_hash=target_record.source_hash,
                prompt_version=prompt_version,
                model=model,
                effort=effort,
            )
            cached = typing_cache.get(cache_key)
            if cached is None:
                pending_candidates.append(candidate)
                pending_keys[target_id] = cache_key
                cache_misses += 1
                continue
            if cached.get("accepted"):
                entry = dict(cached.get("entry") or {})
                if entry.get("target_section_id") == target_id:
                    cached_entries.append(entry)
                    cache_hits += 1
                else:
                    pending_candidates.append(candidate)
                    pending_keys[target_id] = cache_key
                    cache_misses += 1
            else:
                cache_rejected_hits += 1

        cached_entries_by_source[source_id] = cached_entries
        if pending_candidates:
            pending_candidates_by_source[source_id] = pending_candidates
            pending_keys_by_source[source_id] = pending_keys
            sources_to_evaluate.append(source)
        else:
            related_by_source[source_id] = cached_entries

    batch_size = max(1, int(getattr(limits_config, "llm_batch_max_sections", 8) or 8))
    max_chars = max(0, int(getattr(limits_config, "llm_batch_max_chars", 0) or 0))

    def _estimate_source_chars(source: _SectionRecord) -> int:
        # Rough proxy: source section's own text + its candidates' target text.
        # The actual prompt also serializes metadata, but text dominates.
        own = len(source.text or "")
        cands = pending_candidates_by_source.get(source.source_section_id, [])
        cand_chars = 0
        for cand in cands:
            tid = str(cand.get("target_section_id") or "")
            target = records_by_id.get(tid)
            if target is not None:
                cand_chars += len(target.text or "")
        return own + cand_chars

    batches: list[tuple[list[_SectionRecord], dict[str, list[Mapping[str, Any]]]]] = []
    current_batch: list[_SectionRecord] = []
    current_chars = 0
    for source in sources_to_evaluate:
        source_chars = _estimate_source_chars(source)
        would_exceed_size = len(current_batch) >= batch_size
        would_exceed_chars = (
            max_chars > 0 and current_batch and current_chars + source_chars > max_chars
        )
        if would_exceed_size or would_exceed_chars:
            batch_candidates_by_source = {
                s.source_section_id: pending_candidates_by_source.get(
                    s.source_section_id, []
                )
                for s in current_batch
            }
            batches.append((current_batch, batch_candidates_by_source))
            current_batch = []
            current_chars = 0
        current_batch.append(source)
        current_chars += source_chars
    if current_batch:
        batch_candidates_by_source = {
            s.source_section_id: pending_candidates_by_source.get(
                s.source_section_id, []
            )
            for s in current_batch
        }
        batches.append((current_batch, batch_candidates_by_source))

    def _run_related_batch(batch: tuple[list[_SectionRecord], dict[str, list[Mapping[str, Any]]]]):
        batch_sources, batch_candidates_by_source = batch
        request = _build_batch_selection_request(
            batch_sources,
            batch_candidates_by_source,
            records_by_id,
            metadata_by_id,
            prompt_version=prompt_version,
            model=model,
            effort=effort,
            metadata_version=metadata_version,
            limits=limits_config,
        )
        result = generate_with_retries(
            provider,
            request,
            required_fields=(),
            field_schema={
                "related_sections": "list|object",
                "sections": "list[object]",
            },
            timeout_sec=timeout_sec,
            max_retries=max_retries,
        )
        return batch_sources, batch_candidates_by_source, result

    concurrency = max(1, int(getattr(limits_config, "llm_batch_concurrency", 4) or 4))
    if concurrency > 1 and len(batches) > 1:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            batch_outputs = list(ex.map(_run_related_batch, batches))
    else:
        batch_outputs = [_run_related_batch(batch) for batch in batches]

    for batch_sources, batch_candidates_by_source, result in batch_outputs:
        llm_results.append(result)
        for diagnostic in result.diagnostic_items or []:
            diagnostics.append(dict(diagnostic))
        if result.status != "success" or result.artifact is None:
            for source in batch_sources:
                source_id = source.source_section_id
                related_by_source[source_id] = list(
                    cached_entries_by_source.get(source_id, [])
                )
            continue
        batch_output = _batch_related_items_from_output(
            result.artifact.output, batch_sources
        )
        for source in batch_sources:
            source_id = source.source_section_id
            raw_items = batch_output.get(source_id)
            if raw_items is None:
                diagnostics.append(
                    _diagnostic(
                        "validation_error",
                        "related_section_selection batch output missing source",
                        source_section_id=source_id,
                        stage=RELATED_SECTIONS_STAGE,
                        prompt_version=prompt_version,
                        model=model,
                    ),
                )
                related_by_source[source_id] = list(
                    cached_entries_by_source.get(source_id, [])
                )
                continue
            validation = validate_related_sections_result(
                source_id,
                raw_items,
                candidates=batch_candidates_by_source[source_id],
                sections=records,
                section_metadata=metadata_by_id,
                limits=limits_config,
                generated_at=generated_at,
            )
            new_entries = list(validation.related_sections)
            accepted_targets: set[str] = set()
            pending_keys = pending_keys_by_source.get(source_id, {})
            for entry in new_entries:
                target_id = str(entry.get("target_section_id", ""))
                if not target_id:
                    continue
                cache_key = pending_keys.get(target_id)
                if cache_key is None:
                    continue
                typing_cache.put(
                    cache_key,
                    {"accepted": True, "entry": dict(entry)},
                )
                accepted_targets.add(target_id)
            for target_id, cache_key in pending_keys.items():
                if target_id not in accepted_targets:
                    typing_cache.put(cache_key, {"accepted": False})
            cached_entries = cached_entries_by_source.get(source_id, [])
            related_by_source[source_id] = cached_entries + new_entries
            diagnostics.extend(validation.diagnostics)

    typing_cache.save()
    if cache_hits or cache_misses or cache_rejected_hits:
        diagnostics.append(
            _diagnostic(
                "related_typing_cache_stats",
                "pair-level relation typing cache statistics",
                cache_hits=cache_hits,
                cache_misses=cache_misses,
                cache_rejected_hits=cache_rejected_hits,
                cache_size=typing_cache.size,
                stage=RELATED_SECTIONS_STAGE,
            ),
        )

    sections_payload = [
        {
            "source_section_id": record.source_section_id,
            "section_id": record.source_section_id,
            "related_sections": related_by_source.get(record.source_section_id, []),
        }
        for record in records
        if record.source_section_id in requested
    ]
    return RelatedSectionSelection(
        related_sections=related_by_source,
        sections=sections_payload,
        diagnostics=diagnostics,
        llm_results=llm_results,
        llm_calls=len(llm_results),
        generated_at=generated_at,
        elapsed_sec=time.perf_counter() - start,
    )


def _resolve_selection_provider(
    provider: LlmProvider | None,
    llm_config: Any | None,
) -> LlmProvider:
    if provider is not None:
        return provider
    if llm_config is None:
        return FakeLlmProvider()
    return build_spec_core_llm_provider(llm_config)


def _selected_llm_config(llm_config: Any | None) -> Any | None:
    if _config_value(llm_config, "providers"):
        return select_llm_provider_config(llm_config)
    return llm_config


def select_related_sections(
    sections: Sequence[Any],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Return an artifact payload for LLM-selected related_sections."""

    _apply_positional_kwargs(
        kwargs,
        args,
        ("candidates", "section_metadata", "provider", "config"),
        "select_related_sections",
    )
    return select_related_sections_result(sections, **kwargs).to_dict()


def validate_related_sections_result(
    source_section_id: str,
    items: Any,
    *,
    candidates: Sequence[Any],
    sections: Sequence[Any] = (),
    section_metadata: Any | None = None,
    metadata: Any | None = None,
    limits: Any | None = None,
    config: Any | None = None,
    project_config: Any | None = None,
    generated_at: str | None = None,
) -> RelatedSectionValidation:
    """Validate LLM-selected Related Sections for one source section."""

    generated_at = generated_at or _now()
    records = [_normalize_section(section) for section in sections]
    records_by_id = {record.source_section_id: record for record in records}
    metadata_by_id = _metadata_records(
        _first_not_none(section_metadata, metadata),
        records,
    )
    limits_config = _limits(_first_not_none(limits, _config_value(config, "limits", None), _config_value(project_config, "limits", None)))
    raw_items = _raw_related_item_list(items)
    candidate_items = [
        candidate
        for candidate in _coerce_candidate_items(candidates)
        if candidate.get("source_section_id") == source_section_id
    ]
    candidate_by_target = {
        str(candidate.get("target_section_id")): candidate
        for candidate in candidate_items
        if isinstance(candidate.get("target_section_id"), str)
    }
    existing_targets = set(records_by_id)
    if not existing_targets:
        existing_targets = {
            str(candidate.get("target_section_id"))
            for candidate in candidate_items
            if isinstance(candidate.get("target_section_id"), str)
        }
        existing_targets.add(source_section_id)

    diagnostics: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    for index, item in enumerate(raw_items):
        if not isinstance(item, Mapping):
            diagnostics.append(
                _validation_drop(
                    "invalid_item",
                    "related_sections item must be an object",
                    source_section_id,
                    index,
                ),
            )
            continue
        target_id = item.get("target_section_id")
        if not isinstance(target_id, str) or not target_id:
            diagnostics.append(
                _validation_drop(
                    "invalid_target_section_id",
                    "target_section_id is required",
                    source_section_id,
                    index,
                ),
            )
            continue
        if target_id == source_section_id:
            diagnostics.append(
                _validation_drop(
                    "self_reference",
                    "self reference is not allowed",
                    source_section_id,
                    index,
                    target_section_id=target_id,
                ),
            )
            continue
        if target_id not in existing_targets:
            diagnostics.append(
                _validation_drop(
                    "missing_target_section",
                    "target_section_id does not exist",
                    source_section_id,
                    index,
                    target_section_id=target_id,
                ),
            )
            continue
        candidate = candidate_by_target.get(target_id)
        if candidate is None:
            diagnostics.append(
                _validation_drop(
                    "outside_candidate_set",
                    "LLM selected a target outside related_section_candidates",
                    source_section_id,
                    index,
                    target_section_id=target_id,
                ),
            )
            continue
        relation_hint = item.get("relation_hint")
        if relation_hint not in ALLOWED_RELATION_HINTS:
            diagnostics.append(
                _validation_drop(
                    "invalid_relation_hint",
                    "relation_hint is not allowed",
                    source_section_id,
                    index,
                    target_section_id=target_id,
                ),
            )
            continue
        confidence = item.get("confidence")
        if confidence not in ALLOWED_CONFIDENCE:
            diagnostics.append(
                _validation_drop(
                    "invalid_confidence",
                    "confidence is not allowed",
                    source_section_id,
                    index,
                    target_section_id=target_id,
                ),
            )
            continue
        possible_conflict = bool(item.get("possible_conflict", False))
        evidence_terms = item.get("evidence_terms")
        if not isinstance(evidence_terms, Sequence) or isinstance(
            evidence_terms,
            (str, bytes),
        ):
            diagnostics.append(
                _validation_drop(
                    "invalid_evidence_terms",
                    "evidence_terms must be a list",
                    source_section_id,
                    index,
                    target_section_id=target_id,
                ),
            )
            continue
        evidence_terms = _dedupe_public_terms(evidence_terms)
        if not _evidence_terms_are_supported(
            evidence_terms,
            candidate,
            source=records_by_id.get(source_section_id),
            target=records_by_id.get(target_id),
            metadata_by_id=metadata_by_id,
        ):
            diagnostics.append(
                _validation_drop(
                    "unsupported_evidence_terms",
                    "evidence_terms are not present in candidate information or snippets",
                    source_section_id,
                    index,
                    target_section_id=target_id,
                ),
            )
            continue
        channels = _candidate_channels(candidate)
        if not channels:
            diagnostics.append(
                _validation_drop(
                    "invalid_channels",
                    "candidate has no recognized channels to restore",
                    source_section_id,
                    index,
                    target_section_id=target_id,
                ),
            )
            continue
        if target_id in seen_targets:
            continue
        seen_targets.add(target_id)
        entry: dict[str, Any] = {
            "target_section_id": target_id,
            "relation_hint": relation_hint,
            "confidence": confidence,
            "evidence_terms": evidence_terms,
            "channels": sorted(
                channels,
                key=lambda channel: CHANNEL_ORDER.get(channel, 999),
            ),
            "possible_conflict": possible_conflict,
            "generated_at": generated_at,
        }
        valid.append(entry)

    limit = max(0, limits_config.related_selected_max_per_section)
    if len(valid) > limit:
        dropped = valid[limit:]
        valid = valid[:limit]
        diagnostics.append(
            _diagnostic(
                "related_selected_limit_exceeded",
                "related_selected_max_per_section truncated related_sections",
                source_section_id=source_section_id,
                limit=limit,
                dropped_count=len(dropped),
                dropped_target_section_ids=[
                    item["target_section_id"] for item in dropped
                ],
            ),
        )
    raw_count = len(raw_items)
    valid_count = len(valid)
    drop_reasons: dict[str, int] = {}
    for diag in diagnostics:
        if "item_index" not in diag:
            continue
        reason_code = str(diag.get("reason_code") or "unknown")
        drop_reasons[reason_code] = drop_reasons.get(reason_code, 0) + 1
    possible_conflict_count = sum(1 for entry in valid if entry.get("possible_conflict"))
    diagnostics.append(
        _diagnostic(
            "related_selection_counts",
            "Per-source validation counts after LLM selection.",
            source_section_id=source_section_id,
            raw_candidate_count=raw_count,
            valid_candidate_count=valid_count,
            validation_dropped_count=raw_count - valid_count,
            validation_drop_reasons=drop_reasons,
            possible_conflict_true_count=possible_conflict_count,
        ),
    )
    return RelatedSectionValidation(related_sections=valid, diagnostics=diagnostics)


def validate_related_sections(
    source_section_id: str,
    items: Any,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    _apply_positional_kwargs(
        kwargs,
        args,
        ("candidates", "sections", "section_metadata", "limits"),
        "validate_related_sections",
    )
    return validate_related_sections_result(source_section_id, items, **kwargs).to_dict()


def generate_related_sections_result(
    sections: Sequence[Any],
    *,
    section_metadata: Any | None = None,
    metadata: Any | None = None,
    config: Any | None = None,
    project_config: Any | None = None,
    provider: LlmProvider | None = None,
    llm_provider: LlmProvider | None = None,
    llm_config: Any | None = None,
    limits: Any | None = None,
    generated_at: str | None = None,
    prompt_version: str = RELATED_SECTIONS_PROMPT_VERSION,
    metadata_version: int = DEFAULT_METADATA_VERSION,
    cache_dir: Any | None = None,
) -> RelatedSectionsGeneration:
    """Generate candidates, run selection, and return a Related Sections artifact."""

    generated_at = generated_at or _now()
    candidate_generation = generate_related_section_candidates_result(
        sections,
        section_metadata=_first_not_none(section_metadata, metadata),
        config=config,
        project_config=project_config,
        limits=limits,
        generated_at=generated_at,
    )
    selection = select_related_sections_result(
        sections,
        candidates=candidate_generation,
        section_metadata=_first_not_none(section_metadata, metadata),
        config=config,
        project_config=project_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_config=llm_config,
        limits=limits,
        generated_at=generated_at,
        prompt_version=prompt_version,
        metadata_version=metadata_version,
        cache_dir=cache_dir,
    )
    diagnostics = candidate_generation.diagnostics + selection.diagnostics
    qdrant_backend_failure = candidate_generation.qdrant_backend_failure
    artifact_status = "failed" if qdrant_backend_failure is not None else "success"
    artifact = {
        "artifact_role": RELATED_SECTIONS_ROLE,
        "artifact_kind": "retrieval_auxiliary",
        "status": artifact_status,
        "retrieval_auxiliary": True,
        "retrieval_aid_not_evidence": True,
        "reference_helper": True,
        "evidence": False,
        "related_sections_are_evidence": False,
        "metadata": _retrieval_auxiliary_metadata(),
        "generation": {
            "stage": "related_sections",
            "prompt_version": prompt_version,
            "metadata_version": metadata_version,
            "candidate_channels": list(MVP_CANDIDATE_CHANNELS),
            "allowed_relation_hints": sorted(ALLOWED_RELATION_HINTS),
            "allowed_confidence": sorted(ALLOWED_CONFIDENCE),
        },
        "related_section_candidates": candidate_generation.related_section_candidates,
        "related_candidate_limit_events": _related_candidate_limit_events(
            candidate_generation.diagnostics,
        ),
        "candidate_generation_elapsed_sec": candidate_generation.elapsed_sec,
        "selection_elapsed_sec": selection.elapsed_sec,
        "sections": selection.sections,
        "diagnostics": diagnostics,
        "generated_at": generated_at,
    }
    if qdrant_backend_failure is not None:
        artifact["qdrant_backend_failure"] = dict(qdrant_backend_failure)
    return RelatedSectionsGeneration(
        artifact=artifact,
        candidate_generation=candidate_generation,
        selection=selection,
        diagnostics=diagnostics,
    )


def generate_related_sections_partial_result(
    sections: Sequence[Any],
    *,
    changed_source_section_ids: Sequence[str] | None = None,
    changed_section_ids: Sequence[str] | None = None,
    previous_related_sections: Any | None = None,
    section_metadata: Any | None = None,
    metadata: Any | None = None,
    config: Any | None = None,
    project_config: Any | None = None,
    provider: LlmProvider | None = None,
    llm_provider: LlmProvider | None = None,
    llm_config: Any | None = None,
    limits: Any | None = None,
    generated_at: str | None = None,
    prompt_version: str = RELATED_SECTIONS_PROMPT_VERSION,
    metadata_version: int = DEFAULT_METADATA_VERSION,
    cache_dir: Any | None = None,
) -> RelatedSectionsGeneration:
    """Regenerate Related Sections for changed/added sources and inherit the rest."""

    generated_at = generated_at or _now()
    records = [_normalize_section(section) for section in sections]
    current_source_ids = [record.source_section_id for record in records]
    current_source_id_set = set(current_source_ids)
    changed_sources = {
        str(section_id)
        for section_id in _first_not_none(
            changed_source_section_ids,
            changed_section_ids,
            [],
        )
        if str(section_id) in current_source_id_set
    }
    changed_sources_in_order = [
        section_id for section_id in current_source_ids if section_id in changed_sources
    ]

    candidate_generation = generate_related_section_candidates_result(
        sections,
        section_metadata=_first_not_none(section_metadata, metadata),
        config=config,
        project_config=project_config,
        limits=limits,
        source_section_ids=changed_sources_in_order,
        generated_at=generated_at,
    )
    filtered_candidates = [
        dict(candidate)
        for candidate in candidate_generation.related_section_candidates
        if str(candidate.get("source_section_id") or "") in changed_sources
    ]
    selection = select_related_sections_result(
        sections,
        candidates={
            "related_section_candidates": filtered_candidates,
        },
        section_metadata=_first_not_none(section_metadata, metadata),
        config=config,
        project_config=project_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_config=llm_config,
        limits=limits,
        source_section_ids=changed_sources_in_order,
        generated_at=generated_at,
        prompt_version=prompt_version,
        metadata_version=metadata_version,
        cache_dir=cache_dir,
    )

    previous_by_source = _coerce_related_sections_by_source(previous_related_sections)
    selected_by_source = {
        source_id: [dict(item) for item in items]
        for source_id, items in selection.related_sections.items()
    }
    final_related_sections: dict[str, list[dict[str, Any]]] = {}
    inherited_source_ids: list[str] = []
    for source_id in current_source_ids:
        if source_id in changed_sources:
            final_related_sections[source_id] = selected_by_source.get(source_id, [])
            continue
        inherited_source_ids.append(source_id)
        inherited_items: list[dict[str, Any]] = []
        for item in previous_by_source.get(source_id, []):
            target_id = str(item.get("target_section_id") or "")
            if target_id and target_id in current_source_id_set and target_id != source_id:
                inherited_items.append(dict(item))
        final_related_sections[source_id] = inherited_items

    removed_source_ids = sorted(set(previous_by_source) - current_source_id_set)
    final_sections = [
        {
            "source_section_id": source_id,
            "section_id": source_id,
            "related_sections": final_related_sections.get(source_id, []),
        }
        for source_id in current_source_ids
    ]
    partial_diagnostic = _diagnostic(
        "related_sections_partial_regenerated",
        "Related Sections were regenerated for changed/added sources and inherited for unchanged sources. Target-side changes do not trigger re-typing; use --all for complete re-evaluation.",
        stage="related_sections",
        severity="info",
        partial_regeneration=True,
        partial_mode="source_changed_only",
        source_centric_partial=True,
        source_centric_partial_regeneration=True,
        unchanged_source_inheritance=True,
        removed_source_exclusion=True,
        fallback_regenerated=False,
        changed_target_relations_inherited=True,
        requires_full_regeneration_for_complete_target_recheck=True,
        changed_source_section_ids=changed_sources_in_order,
        changed_target_section_ids=changed_sources_in_order,
        added_or_changed_source_section_ids=changed_sources_in_order,
        inherited_source_section_ids=inherited_source_ids,
        removed_source_section_ids=removed_source_ids,
        candidate_count=len(candidate_generation.related_section_candidates),
        candidate_count_for_selection=len(filtered_candidates),
        candidate_generation_elapsed_sec=candidate_generation.elapsed_sec,
        candidate_generation_partial_mode="source_changed_only",
        candidate_generation_source_count=len(changed_sources_in_order),
        selection_elapsed_sec=selection.elapsed_sec,
        selection_source_count=len(changed_sources_in_order),
        inherited_source_count=len(inherited_source_ids),
        removed_source_count=len(removed_source_ids),
        batch_count=selection.llm_calls,
        llm_calls=selection.llm_calls,
    )
    final_selection_diagnostics = list(selection.diagnostics) + [partial_diagnostic]
    final_selection = RelatedSectionSelection(
        related_sections=final_related_sections,
        sections=final_sections,
        diagnostics=final_selection_diagnostics,
        llm_results=selection.llm_results,
        llm_calls=selection.llm_calls,
        generated_at=generated_at,
        elapsed_sec=selection.elapsed_sec,
    )
    diagnostics = candidate_generation.diagnostics + final_selection.diagnostics
    qdrant_backend_failure = candidate_generation.qdrant_backend_failure
    artifact_status = "failed" if qdrant_backend_failure is not None else "success"
    artifact = {
        "artifact_role": RELATED_SECTIONS_ROLE,
        "artifact_kind": "retrieval_auxiliary",
        "status": artifact_status,
        "retrieval_auxiliary": True,
        "retrieval_aid_not_evidence": True,
        "reference_helper": True,
        "evidence": False,
        "related_sections_are_evidence": False,
        "metadata": _retrieval_auxiliary_metadata(),
        "generation": {
            "stage": "related_sections",
            "prompt_version": prompt_version,
            "metadata_version": metadata_version,
            "candidate_channels": list(MVP_CANDIDATE_CHANNELS),
            "allowed_relation_hints": sorted(ALLOWED_RELATION_HINTS),
            "allowed_confidence": sorted(ALLOWED_CONFIDENCE),
        },
        "related_section_candidates": candidate_generation.related_section_candidates,
        "related_candidate_limit_events": _related_candidate_limit_events(
            candidate_generation.diagnostics,
        ),
        "candidate_generation_elapsed_sec": candidate_generation.elapsed_sec,
        "selection_elapsed_sec": selection.elapsed_sec,
        "sections": final_sections,
        "diagnostics": diagnostics,
        "generated_at": generated_at,
    }
    if qdrant_backend_failure is not None:
        artifact["qdrant_backend_failure"] = dict(qdrant_backend_failure)
    return RelatedSectionsGeneration(
        artifact=artifact,
        candidate_generation=candidate_generation,
        selection=final_selection,
        diagnostics=diagnostics,
    )


def generate_related_sections(
    sections: Sequence[Any],
    **kwargs: Any,
) -> dict[str, Any]:
    return generate_related_sections_result(sections, **kwargs).artifact


def generate_related_sections_partial(
    sections: Sequence[Any],
    **kwargs: Any,
) -> dict[str, Any]:
    return generate_related_sections_partial_result(sections, **kwargs).artifact


def apply_related_sections_to_metadata(
    section_metadata: Any,
    related_sections: Any,
) -> dict[str, Any]:
    """Return the section metadata payload with selected related_sections applied."""

    metadata_payload = dict(section_metadata) if isinstance(section_metadata, Mapping) else {}
    entries = _metadata_entries(section_metadata)
    related_by_source = _coerce_related_sections_by_source(related_sections)
    updated_entries: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        section_id = str(item.get("source_section_id") or item.get("section_id") or "")
        item["related_sections"] = related_by_source.get(section_id, item.get("related_sections", []))
        updated_entries.append(item)
    metadata_payload["sections"] = updated_entries
    return metadata_payload


def compute_related_sections_reevaluation_targets(
    changed_section_ids: Sequence[str],
    *,
    sections: Sequence[Any],
    section_metadata: Any | None = None,
    metadata: Any | None = None,
    candidates: Any | None = None,
    related_section_candidates: Any | None = None,
) -> list[str]:
    """Return the minimum incremental Related Sections re-evaluation scope.

    External API exposing the re-evaluation set described in DESIGN.ja.md
    §5.7. The core `/spec-core` path does NOT call this; it uses the pair
    cache (`related_typing_cache.json`) to skip unchanged (source, target)
    pairs at LLM-evaluation time, which catches candidate-set shifts that
    section-level narrowing would miss. Kept available for external
    incremental orchestration tools and for the unit-test contract.
    """

    records = [_normalize_section(section) for section in sections]
    records_by_id = {record.source_section_id: record for record in records}
    metadata_by_id = _metadata_records(
        _first_not_none(section_metadata, metadata),
        records,
    )
    changed = {
        str(section_id)
        for section_id in changed_section_ids
        if str(section_id) in records_by_id
    }
    targets: set[str] = set(changed)
    order = [record.source_section_id for record in records]

    # Phase F: drop the neighbor_section (positional / same-chapter) heuristic
    # since that channel was removed in Phase C. Re-evaluation now follows the
    # actually-used channels: prior selected edges, exact-signal overlap
    # (markdown_link / shared_identifier / search_key_match with specificity
    # filter), and the qdrant_section_hybrid neighborhood (covered by signal
    # overlap below as a conservative heuristic).

    for record in records:
        metadata_record = metadata_by_id.get(record.source_section_id)
        if metadata_record is None:
            continue
        for related in metadata_record.related_sections:
            if related.get("target_section_id") in changed:
                targets.add(record.source_section_id)

    identifiers_by_id = {
        record.source_section_id: {
            _normalize_key(identifier)
            for identifier in _filter_specific_terms(
                _metadata_for(record, metadata_by_id).identifiers
            )
            if _normalize_key(identifier)
        }
        for record in records
    }
    changed_identifiers = set().union(
        *(identifiers_by_id.get(section_id, set()) for section_id in changed),
    )
    if changed_identifiers:
        for section_id, identifiers in identifiers_by_id.items():
            if section_id not in changed and identifiers & changed_identifiers:
                targets.add(section_id)

    search_keys_by_id = {
        record.source_section_id: {
            _normalize_key(search_key)
            for search_key in _filter_specific_terms(
                _metadata_for(record, metadata_by_id).search_keys
            )
            if _normalize_key(search_key)
        }
        for record in records
    }
    changed_search_keys = set().union(
        *(search_keys_by_id.get(section_id, set()) for section_id in changed),
    )
    if changed_search_keys:
        for section_id, search_keys in search_keys_by_id.items():
            if section_id not in changed and search_keys & changed_search_keys:
                targets.add(section_id)

    # Phase F: drop the summary_tokens overlap heuristic. The qdrant_section_hybrid
    # channel covers semantic similarity at section level; on incremental update
    # the conservative scope is captured by exact-signal overlap (above) plus
    # markdown_link edges and prior candidate edges (below).

    link_edges = _markdown_link_edges(records, records_by_id)
    for source_id, target_id in link_edges:
        if source_id in changed or target_id in changed:
            targets.add(source_id)
            targets.add(target_id)

    candidate_items = _coerce_candidate_items(
        _first_not_none(candidates, related_section_candidates, []),
    )
    for candidate in candidate_items:
        source_id = str(candidate.get("source_section_id", ""))
        target_id = str(candidate.get("target_section_id", ""))
        if source_id in changed or target_id in changed:
            if source_id in records_by_id:
                targets.add(source_id)
            if target_id in records_by_id:
                targets.add(target_id)

    return [section_id for section_id in order if section_id in targets]


def related_section_reevaluation_targets(
    changed_section_ids: Sequence[str],
    **kwargs: Any,
) -> list[str]:
    """Compatibility alias used by section_metadata re-export and existing tests."""

    return compute_related_sections_reevaluation_targets(changed_section_ids, **kwargs)


def _add_markdown_link_candidates(
    builders: dict[tuple[str, str], _CandidateBuilder],
    records: Sequence[_SectionRecord],
    records_by_id: Mapping[str, _SectionRecord],
    metadata_by_id: Mapping[str, _MetadataRecord],
    generated_at: str,
) -> None:
    resolver = _MarkdownLinkResolver(list(records_by_id.values()))
    for source in records:
        for link_text, target_text in _markdown_links(source.text):
            target_id = resolver.resolve(source, target_text)
            target = records_by_id.get(target_id or "")
            if target is None:
                continue
            _add_candidate(
                builders,
                source,
                target,
                MARKDOWN_LINK,
                generated_at,
                evidence_terms=[link_text, target_text],
                evidence_snippets=[_candidate_snippet(target, metadata_by_id)],
            )


def _add_shared_identifier_candidates(
    builders: dict[tuple[str, str], _CandidateBuilder],
    records: Sequence[_SectionRecord],
    metadata_by_id: Mapping[str, _MetadataRecord],
    generated_at: str,
    *,
    full_records: Sequence[_SectionRecord] | None = None,
    source_section_ids: set[str] | None = None,
) -> None:
    index_records = full_records if full_records is not None else records
    index = _inverted_terms(
        {
            record.source_section_id: _filter_specific_terms(
                _metadata_for(record, metadata_by_id).identifiers
            )
            for record in index_records
        },
    )
    _add_index_candidates(
        builders,
        index,
        index_records,
        metadata_by_id,
        generated_at,
        channel=SHARED_IDENTIFIER,
        source_section_ids=source_section_ids,
    )


def _add_search_key_candidates(
    builders: dict[tuple[str, str], _CandidateBuilder],
    records: Sequence[_SectionRecord],
    metadata_by_id: Mapping[str, _MetadataRecord],
    generated_at: str,
    *,
    full_records: Sequence[_SectionRecord] | None = None,
    source_section_ids: set[str] | None = None,
) -> None:
    index_records = full_records if full_records is not None else records
    index = _inverted_terms(
        {
            record.source_section_id: _filter_specific_terms(
                _metadata_for(record, metadata_by_id).search_keys
            )
            for record in index_records
        },
    )
    _add_index_candidates(
        builders,
        index,
        index_records,
        metadata_by_id,
        generated_at,
        channel=SEARCH_KEY_MATCH,
        source_section_ids=source_section_ids,
    )


def _add_qdrant_section_hybrid_candidates(
    builders: dict[tuple[str, str], _CandidateBuilder],
    records: Sequence[_SectionRecord],
    records_by_id: Mapping[str, _SectionRecord],
    metadata_by_id: Mapping[str, _MetadataRecord],
    generated_at: str,
    *,
    full_records: Sequence[_SectionRecord] | None = None,
    top_k: int,
    dense_threshold: float = 0.0,
    final_top_n: int = 0,
    use_real_qdrant: bool = False,
    qdrant_url: str = "",
    qdrant_collection: str = "spec_anchor_section",
    embedding_provider_id: str = "",
) -> dict[str, Any] | None:
    """Add candidates from section-level dense+sparse hybrid retrieval (Qdrant).

    Returns a failure descriptor when Qdrant is configured (``use_real_qdrant``
    is true) but the Qdrant-backed retriever cannot be initialized. In that
    case no candidates are added and the caller is expected to mark the
    Related Sections artifact as ``failed``. Returns ``None`` on success and
    in the Qdrant-unconfigured path (which uses :class:`InMemoryHybridRetriever`
    for development / test).
    """

    if not records or top_k <= 0:
        return None
    index_records = full_records if full_records is not None else records
    try:
        from spec_anchor.retrieval_index import (
            InMemoryHybridRetriever,
            build_section_payloads,
        )
    except ImportError:
        return None

    sections_for_payload = [
        {
            "source_section_id": record.source_section_id,
            "source_document_id": record.source_document_id,
            "stable_section_uid": record.stable_section_uid,
            "heading_path": record.heading_path,
            "source_hash": record.source_hash,
            "semantic_hash": record.semantic_hash,
        }
        for record in index_records
    ]
    metadata_for_payload: dict[str, dict[str, Any]] = {}
    for record in index_records:
        metadata = _metadata_for(record, metadata_by_id)
        metadata_for_payload[record.source_section_id] = {
            "summary": metadata.summary,
            "search_keys": list(metadata.search_keys),
            "identifiers": list(metadata.identifiers),
        }
    payloads = build_section_payloads(sections_for_payload, metadata_for_payload)
    payload_by_id = {payload["source_section_id"]: payload for payload in payloads}
    if not payloads:
        return None

    retriever: Any
    if use_real_qdrant and qdrant_url and qdrant_collection:
        try:
            from spec_anchor.retrieval_index import QdrantHybridRetriever

            retriever = QdrantHybridRetriever(
                url=qdrant_url,
                collection=qdrant_collection,
            )
        except Exception as exc:
            # AUD-007: Qdrant が設定済みなのに retriever 初期化に失敗した場合は
            # silently InMemory fallback せず、上位で failed 扱いとして
            # canonical artifact を更新しないようにする。
            return {
                "expected_retrieval_backend": "qdrant",
                "actual_retrieval_backend": "unavailable",
                "fallback_attempted": False,
                "failure_reason": (
                    f"Qdrant retriever initialization failed: {exc}"
                ),
                "qdrant_url_configured": True,
                "embedding_provider": embedding_provider_id,
            }
    else:
        # Qdrant 未設定 (dev / test 用構成、`vector_store.provider != "qdrant"`
        # または `url` 未設定) では InMemory hybrid retriever を最初から使う。
        # これは本 task の削除対象外 (= 正規動作)。
        retriever = InMemoryHybridRetriever(payloads)
    cap = max(0, int(final_top_n)) if final_top_n else 0
    for source in records:
        source_payload = payload_by_id.get(source.source_section_id)
        if source_payload is None:
            continue
        query_text = str(source_payload.get("text") or "")
        if not query_text.strip():
            continue
        result = retriever.search(
            query_text,
            limit=top_k + 1,
            fusion_owner="related_sections_section_hybrid",
        )
        accepted_for_source = 0
        for hit in result.hits:
            target_id = hit.source_section_id
            if not target_id or target_id == source.source_section_id:
                continue
            target_record = records_by_id.get(target_id)
            if target_record is None:
                continue
            score = float(hit.score)
            existing = builders.get((source.source_section_id, target_id))
            has_exact_signal = bool(
                existing
                and existing.channels & {MARKDOWN_LINK, SHARED_IDENTIFIER}
            )
            if (
                dense_threshold > 0.0
                and score < dense_threshold
                and not has_exact_signal
            ):
                continue
            if cap and accepted_for_source >= cap and not has_exact_signal:
                continue
            _add_candidate(
                builders,
                source,
                target_record,
                QDRANT_SECTION_HYBRID,
                generated_at,
                evidence_terms=[f"section_similarity:{round(score, 4)}"],
                evidence_snippets=[_candidate_snippet(target_record, metadata_by_id)],
            )
            accepted_for_source += 1
    return None


def _add_index_candidates(
    builders: dict[tuple[str, str], _CandidateBuilder],
    index: Mapping[str, list[str]],
    records: Sequence[_SectionRecord],
    metadata_by_id: Mapping[str, _MetadataRecord],
    generated_at: str,
    *,
    channel: str,
    source_section_ids: set[str] | None = None,
) -> None:
    records_by_id = {record.source_section_id: record for record in records}
    for term, section_ids in index.items():
        if len(section_ids) <= 1:
            continue
        for source_id in section_ids:
            if source_section_ids is not None and source_id not in source_section_ids:
                continue
            source = records_by_id[source_id]
            for target_id in section_ids:
                if source_id == target_id:
                    continue
                target = records_by_id[target_id]
                _add_candidate(
                    builders,
                    source,
                    target,
                    channel,
                    generated_at,
                    evidence_terms=[term],
                    evidence_snippets=[_candidate_snippet(target, metadata_by_id)],
                )


def _add_candidate(
    builders: dict[tuple[str, str], _CandidateBuilder],
    source: _SectionRecord,
    target: _SectionRecord,
    channel: str,
    generated_at: str,
    *,
    evidence_terms: Sequence[str] = (),
    evidence_snippets: Sequence[str] = (),
) -> None:
    if source.source_section_id == target.source_section_id:
        return
    key = (source.source_section_id, target.source_section_id)
    builder = builders.get(key)
    if builder is None:
        builder = _CandidateBuilder(
            source_section_id=source.source_section_id,
            target_section_id=target.source_section_id,
            channels=set(),
            evidence_terms=[],
            evidence_snippets=[],
            generated_at=generated_at,
        )
        builders[key] = builder
    builder.add(
        channel=channel,
        evidence_terms=evidence_terms,
        evidence_snippets=evidence_snippets,
    )


def _limit_candidates_by_source(
    candidates: Sequence[Mapping[str, Any]],
    records: Sequence[_SectionRecord],
    limits: LimitsConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int], dict[str, int]]:
    limit = max(0, limits.related_candidate_max_per_section)
    by_source: dict[str, list[dict[str, Any]]] = {
        record.source_section_id: [] for record in records
    }
    for candidate in candidates:
        source_id = str(candidate.get("source_section_id", ""))
        target_id = str(candidate.get("target_section_id", ""))
        if not source_id or not target_id or source_id == target_id:
            continue
        if source_id not in by_source:
            continue
        by_source[source_id].append(dict(candidate))

    diagnostics: list[dict[str, Any]] = []
    limited: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    dropped_counts: dict[str, int] = {}
    for record in records:
        source_id = record.source_section_id
        ordered = sorted(by_source[source_id], key=_candidate_sort_key)
        dropped = ordered[limit:]
        kept = ordered[:limit]
        counts[source_id] = len(kept)
        dropped_counts[source_id] = len(dropped)
        limited.extend(kept)
        if dropped:
            diagnostics.append(
                _diagnostic(
                    "related_candidate_limit",
                    "related_candidate_max_per_section truncated candidates",
                    source_section_id=source_id,
                    limit=limit,
                    kept_count=len(kept),
                    dropped_count=len(dropped),
                    dropped_summaries=[
                        _dropped_candidate_summary(item) for item in dropped
                    ],
                    candidate_count_before_limit=len(ordered),
                    dropped_target_section_ids=[
                        str(item.get("target_section_id", "")) for item in dropped
                    ],
                ),
            )
    return limited, diagnostics, counts, dropped_counts


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    channels = set(_candidate_channels(candidate))
    exact_priority = 1 if channels & EXACT_CHANNELS else 0
    semantic_priority = 1 if channels & SEMANTIC_CHANNELS else 0
    best_channel_score = max((CHANNEL_WEIGHTS.get(channel, 0.0) for channel in channels), default=0.0)
    return (
        -exact_priority,
        -best_channel_score,
        -float(candidate.get("candidate_score", 0.0) or 0.0),
        -semantic_priority,
        str(candidate.get("target_section_id", "")),
    )


def _dropped_candidate_summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    channels = _candidate_channels(candidate)
    strongest_channel = max(
        channels,
        key=lambda channel: CHANNEL_WEIGHTS.get(channel, 0.0),
        default="unknown",
    )
    return {
        "target_section_id": str(candidate.get("target_section_id", "")),
        "channels": channels,
        "candidate_score": float(candidate.get("candidate_score", 0.0) or 0.0),
        "reason": (
            "dropped_by_related_candidate_max_per_section; "
            f"strongest_channel={strongest_channel}"
        ),
    }


class _MarkdownLinkResolver:
    def __init__(self, records: Sequence[_SectionRecord]) -> None:
        self.by_section_id = {record.source_section_id: record for record in records}
        self.by_document: dict[str, list[_SectionRecord]] = {}
        self.by_anchor: dict[tuple[str, str], str] = {}
        for record in records:
            self.by_document.setdefault(record.source_document_id, []).append(record)
            suffix = record.source_section_id.split("#", 1)[1] if "#" in record.source_section_id else ""
            for anchor in (
                suffix,
                _slug(record.heading_path[-1] if record.heading_path else ""),
            ):
                if anchor:
                    self.by_anchor.setdefault((record.source_document_id, anchor), record.source_section_id)

    def resolve(self, source: _SectionRecord, target_text: str) -> str | None:
        raw = target_text.strip()
        if raw in self.by_section_id:
            return raw
        parts = urlsplit(raw)
        if parts.scheme or parts.netloc:
            return None
        target_doc = source.source_document_id
        if parts.path:
            target_doc = _normalize_link_path(source.source_document_id, unquote(parts.path))
        fragment = unquote(parts.fragment).strip()
        if not fragment:
            records = self.by_document.get(target_doc, [])
            return records[0].source_section_id if records else None
        direct_id = f"{target_doc}#{fragment}"
        if direct_id in self.by_section_id:
            return direct_id
        return self.by_anchor.get((target_doc, _slug(fragment)))


def _markdown_link_edges(
    records: Sequence[_SectionRecord],
    records_by_id: Mapping[str, _SectionRecord],
) -> list[tuple[str, str]]:
    resolver = _MarkdownLinkResolver(records)
    edges: list[tuple[str, str]] = []
    for source in records:
        for _text, target_text in _markdown_links(source.text):
            target_id = resolver.resolve(source, target_text)
            if target_id in records_by_id and target_id != source.source_section_id:
                edges.append((source.source_section_id, target_id))
    return edges


def _markdown_links(text: str) -> list[tuple[str, str]]:
    return [
        (_normalize_public_text(match.group(1)), _normalize_public_text(match.group(2)))
        for match in _LINK_RE.finditer(text)
    ]


def _build_selection_request(
    source: _SectionRecord,
    candidates: Sequence[Mapping[str, Any]],
    records_by_id: Mapping[str, _SectionRecord],
    metadata_by_id: Mapping[str, _MetadataRecord],
    *,
    prompt_version: str,
    model: str,
    effort: str | None,
    metadata_version: int,
    limits: LimitsConfig,
) -> LlmRequest:
    payload = {
        "task": RELATED_SECTIONS_STAGE,
        "artifact_role": RELATED_SECTIONS_ROLE,
        "related_sections_are_evidence": False,
        "boundary": {
            "must_choose_from_candidate_target_section_ids": [
                str(candidate["target_section_id"]) for candidate in candidates
            ],
            "do_not_search_full_text_outside_candidates": True,
        },
        "instructions": [
            "Classify each candidate's relation_hint, confidence, and possible_conflict.",
            "Set possible_conflict=true ONLY when: (1) both sections address the same "
            "concrete subject (the same resource, lifecycle, action, or policy), AND "
            "(2) their requirements cannot be simultaneously satisfied. "
            "Do NOT set possible_conflict=true for dependency (impacts), implementation "
            "order, see_also, shared vocabulary, or general conceptual relationship.",
        ],
        "return_shape": {
            "related_sections": [
                {
                    "target_section_id": "string",
                    "relation_hint": sorted(ALLOWED_RELATION_HINTS),
                    "confidence": sorted(ALLOWED_CONFIDENCE),
                    "possible_conflict": "boolean — true only if requirements are mutually incompatible",
                    "evidence_terms": ["string"],
                },
            ],
        },
        "limits": {
            "related_selected_max_per_section": limits.related_selected_max_per_section,
        },
        "source_section": _selection_section_payload(source, metadata_by_id),
        "candidates": [
            {
                **dict(candidate),
                "target_section": _selection_section_payload(
                    records_by_id[str(candidate["target_section_id"])],
                    metadata_by_id,
                ),
            }
            for candidate in candidates
            if str(candidate.get("target_section_id", "")) in records_by_id
        ],
    }
    prompt = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    _log_related_prompt_debug(
        request_kind="single_source",
        payload=payload,
        prompt=prompt,
        primary_section_id=source.source_section_id,
        batch_source_ids=[source.source_section_id],
        involved_section_ids=[
            source.source_section_id,
            *(
                str(candidate["target_section_id"])
                for candidate in candidates
                if str(candidate.get("target_section_id", "")) in records_by_id
            ),
        ],
    )
    section_hashes = {
        source.source_section_id: source.source_hash,
        **{
            str(candidate["target_section_id"]): records_by_id[
                str(candidate["target_section_id"])
            ].source_hash
            for candidate in candidates
            if str(candidate.get("target_section_id", "")) in records_by_id
        },
    }
    source_hash = _sha256_text(
        _stable_json(
            {
                "source_section_id": source.source_section_id,
                "source_hash": source.source_hash,
                "candidate_pairs": [
                    [
                        candidate.get("target_section_id"),
                        candidate.get("candidate_score"),
                        candidate.get("channels"),
                    ]
                    for candidate in candidates
                ],
                "prompt_version": prompt_version,
            },
        ),
    )
    semantic_hash = _sha256_text(
        _stable_json(
            {
                "source_section_id": source.source_section_id,
                "semantic_hash": source.semantic_hash,
                "target_semantic_hashes": {
                    target_id: records_by_id[target_id].semantic_hash
                    for target_id in section_hashes
                    if target_id in records_by_id
                },
            },
        ),
    )
    return LlmRequest(
        task=RELATED_SECTIONS_STAGE,
        stage=RELATED_SECTIONS_STAGE,
        prompt=prompt,
        prompt_version=prompt_version,
        model=model,
        source_hash=source_hash,
        semantic_hash=semantic_hash,
        section_id=source.source_section_id,
        metadata_version=metadata_version,
        effort=effort,
        section_hashes=section_hashes,
        context_hashes={
            "artifact_role": _sha256_text(RELATED_SECTIONS_ROLE),
            "candidate_channels": _sha256_text("|".join(MVP_CANDIDATE_CHANNELS)),
        },
    )


_RELATED_SNIPPET_MAX_CHARS = 480
_RELATED_IDENTIFIERS_MAX = 16


def _selection_section_payload(
    record: _SectionRecord,
    metadata_by_id: Mapping[str, _MetadataRecord],
) -> dict[str, Any]:
    """Section descriptor for the single-source LLM selection prompt.

    Composed of fields that are deterministic from Source Specs alone
    (heading path, mechanically extracted identifiers, source document id, and
    the leading N chars of the section body). LLM-generated metadata
    (`section_metadata` stage's summary / search_keys) is intentionally
    excluded: those drift run-to-run and would invalidate the Claude prompt
    cache between consecutive runs (B-1).
    """

    metadata = _metadata_for(record, metadata_by_id)
    return {
        "source_section_id": record.source_section_id,
        "heading_path": record.heading_path,
        "identifiers": metadata.identifiers[:_RELATED_IDENTIFIERS_MAX],
        "source_document_id": record.source_document_id,
        "snippet": _short_text(record.text, _RELATED_SNIPPET_MAX_CHARS),
    }


def _catalog_entry(
    record: _SectionRecord,
    metadata_by_id: Mapping[str, _MetadataRecord],
) -> dict[str, Any]:
    """Compact section descriptor used in batch LLM catalogs.

    Deterministic-by-construction: every field is derived from Source Specs
    parsing (heading path, source document id, body excerpt) or mechanical
    identifier extraction. `section_metadata` LLM output (summary /
    search_keys) is excluded so the catalog SHA-256 stays stable across runs
    and the Claude prompt cache hits on consecutive `--rebuild` invocations
    (B-1).
    """

    metadata = _metadata_for(record, metadata_by_id)
    return {
        "heading_path": record.heading_path,
        "identifiers": metadata.identifiers[:_RELATED_IDENTIFIERS_MAX],
        "short_snippet": _short_text(record.text, _RELATED_SNIPPET_MAX_CHARS),
        "source_document_id": record.source_document_id,
    }


def _build_batch_selection_request(
    sources: Sequence[_SectionRecord],
    candidates_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    records_by_id: Mapping[str, _SectionRecord],
    metadata_by_id: Mapping[str, _MetadataRecord],
    *,
    prompt_version: str,
    model: str,
    effort: str | None,
    metadata_version: int,
    limits: LimitsConfig,
) -> LlmRequest:
    """Build a single LLM request that classifies multiple source sections at once.

    The catalog dedupes section descriptors so each section's heading / summary
    / keys appear at most once per call (Phase D plan eliminates the per-source
    payload duplication that produced ~33x repeats in the previous design).
    """

    involved_ids: set[str] = set()
    evaluations: list[dict[str, Any]] = []
    for source in sources:
        source_id = source.source_section_id
        involved_ids.add(source_id)
        candidate_payload: list[dict[str, Any]] = []
        for candidate in candidates_by_source.get(source_id, []):
            target_id = str(candidate.get("target_section_id", ""))
            if not target_id or target_id not in records_by_id:
                continue
            involved_ids.add(target_id)
            candidate_payload.append(
                {
                    "target_section_id": target_id,
                    "channels": list(candidate.get("channels", [])),
                    "candidate_score": float(candidate.get("candidate_score", 0.0) or 0.0),
                    "evidence_terms": list(candidate.get("evidence_terms", [])),
                }
            )
        evaluations.append(
            {
                "source_section_id": source_id,
                "candidates": candidate_payload,
            }
        )

    catalog = {
        section_id: _catalog_entry(records_by_id[section_id], metadata_by_id)
        for section_id in sorted(involved_ids)
        if section_id in records_by_id
    }

    payload = {
        "task": "related_section_selection_batch",
        "artifact_role": RELATED_SECTIONS_ROLE,
        "related_sections_are_evidence": False,
        "instructions": [
            "Each candidate has been pre-scored by deterministic signals "
            "(markdown_link, shared_identifier, search_key_match, qdrant_section_hybrid).",
            "Your task is to classify each candidate's relation_hint, confidence, "
            "and possible_conflict. Reject only obviously unrelated candidates.",
            "Do not search beyond the supplied candidates. Use only catalog entries.",
            "Set possible_conflict=true ONLY when: (1) both sections address the same "
            "concrete subject (the same resource, lifecycle, action, or policy), AND "
            "(2) their requirements cannot be simultaneously satisfied. "
            "Do NOT set possible_conflict=true for dependency (impacts), implementation "
            "order, see_also, shared vocabulary, or general conceptual relationship. "
            "The Conflict Review pipeline will independently verify before any conflict "
            "is finalized; do not output relation_hint=conflicts_with from this stage.",
        ],
        "boundary": {
            "must_choose_from_candidate_target_section_ids_per_source": True,
            "do_not_search_full_text_outside_candidates": True,
            "use_only_catalog_for_section_descriptors": True,
        },
        "return_shape": {
            "sections": [
                {
                    "source_section_id": "string (one of the evaluation source ids)",
                    "related_sections": [
                        {
                            "target_section_id": "string",
                            "relation_hint": sorted(ALLOWED_RELATION_HINTS),
                            "confidence": sorted(ALLOWED_CONFIDENCE),
                            "possible_conflict": "boolean",
                            "evidence_terms": ["string"],
                        },
                    ],
                },
            ],
        },
        "limits": {
            "related_selected_max_per_section": limits.related_selected_max_per_section,
            "batch_size": len(sources),
        },
        "catalog": catalog,
        "evaluations": evaluations,
    }

    prompt = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    _log_related_prompt_debug(
        request_kind="batch",
        payload=payload,
        prompt=prompt,
        primary_section_id=sources[0].source_section_id if sources else "",
        batch_source_ids=[source.source_section_id for source in sources],
        involved_section_ids=list(involved_ids),
    )

    section_hashes = {
        section_id: records_by_id[section_id].source_hash
        for section_id in sorted(involved_ids)
        if section_id in records_by_id
    }
    source_hash = _sha256_text(
        _stable_json(
            {
                "batch_source_ids": [source.source_section_id for source in sources],
                "candidate_pairs": [
                    [
                        evaluation["source_section_id"],
                        candidate.get("target_section_id"),
                        candidate.get("candidate_score"),
                        candidate.get("channels"),
                    ]
                    for evaluation in evaluations
                    for candidate in evaluation["candidates"]
                ],
                "prompt_version": prompt_version,
            },
        ),
    )
    semantic_hash = _sha256_text(
        _stable_json(
            {
                "section_semantic_hashes": {
                    section_id: records_by_id[section_id].semantic_hash
                    for section_id in sorted(involved_ids)
                    if section_id in records_by_id
                },
            },
        ),
    )
    primary_section_id = sources[0].source_section_id if sources else ""
    return LlmRequest(
        task=RELATED_SECTIONS_STAGE,
        stage=RELATED_SECTIONS_STAGE,
        prompt=prompt,
        prompt_version=prompt_version,
        model=model,
        source_hash=source_hash,
        semantic_hash=semantic_hash,
        section_id=primary_section_id,
        metadata_version=metadata_version,
        effort=effort,
        section_hashes=section_hashes,
        context_hashes={
            "artifact_role": _sha256_text(RELATED_SECTIONS_ROLE),
            "candidate_channels": _sha256_text("|".join(MVP_CANDIDATE_CHANNELS)),
            "batch_format": _sha256_text("related_section_selection_batch"),
        },
    )


def _batch_related_items_from_output(
    output: Mapping[str, Any],
    sources: Sequence[_SectionRecord],
) -> dict[str, list[Any]]:
    """Extract per-source related_sections lists from a batch LLM output."""

    result: dict[str, list[Any]] = {}
    related = output.get("related_sections")
    if isinstance(related, Mapping):
        for source in sources:
            source_id = source.source_section_id
            items = related.get(source_id)
            if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
                result[source_id] = list(items)
            else:
                result[source_id] = []
        return result
    sections = output.get("sections")
    if isinstance(sections, Sequence) and not isinstance(sections, (str, bytes)):
        items_by_source: dict[str, list[Any]] = {}
        for entry in sections:
            if not isinstance(entry, Mapping):
                continue
            source_id = entry.get("source_section_id") or entry.get("section_id")
            entry_items = entry.get("related_sections")
            if isinstance(source_id, str) and isinstance(entry_items, Sequence) and not isinstance(entry_items, (str, bytes)):
                items_by_source[source_id] = list(entry_items)
        for source in sources:
            result[source.source_section_id] = items_by_source.get(source.source_section_id, [])
        return result
    if isinstance(related, Sequence) and not isinstance(related, (str, bytes)):
        if len(sources) == 1:
            result[sources[0].source_section_id] = list(related)
            return result
    for source in sources:
        result.setdefault(source.source_section_id, [])
    return result


def _related_items_from_output(
    output: Mapping[str, Any],
    source_section_id: str,
) -> list[Any] | None:
    related = output.get("related_sections")
    if isinstance(related, Sequence) and not isinstance(related, (str, bytes)):
        return list(related)
    sections = output.get("sections")
    if isinstance(sections, Sequence) and not isinstance(sections, (str, bytes)):
        for item in sections:
            if not isinstance(item, Mapping):
                continue
            item_source_id = item.get("source_section_id") or item.get("section_id")
            if item_source_id == source_section_id:
                related = item.get("related_sections")
                if isinstance(related, Sequence) and not isinstance(related, (str, bytes)):
                    return list(related)
    return None


def _raw_related_item_list(items: Any) -> list[Any]:
    if isinstance(items, Mapping):
        extracted = _related_items_from_output(items, str(items.get("source_section_id", "")))
        if extracted is not None:
            return extracted
        related = items.get("related_sections")
        if isinstance(related, Sequence) and not isinstance(related, (str, bytes)):
            return list(related)
        return [items]
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        return list(items)
    return []


def _evidence_terms_are_supported(
    evidence_terms: Sequence[str],
    candidate: Mapping[str, Any],
    *,
    source: _SectionRecord | None,
    target: _SectionRecord | None,
    metadata_by_id: Mapping[str, _MetadataRecord],
) -> bool:
    if not evidence_terms:
        return True
    corpus_parts: list[str] = []
    for key in ("channels", "evidence_terms", "evidence_snippets"):
        value = candidate.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            corpus_parts.extend(str(item) for item in value)
    for record in (source, target):
        if record is None:
            continue
        metadata = _metadata_for(record, metadata_by_id)
        corpus_parts.extend(record.heading_path)
        corpus_parts.append(metadata.summary)
        corpus_parts.extend(metadata.search_keys)
        corpus_parts.extend(metadata.identifiers)
        corpus_parts.append(_short_text(record.text, 1000))
    corpus = _normalize_key(" ".join(corpus_parts))
    return all(_normalize_key(term) in corpus for term in evidence_terms)


def _coerce_candidate_items(candidates: Any) -> list[dict[str, Any]]:
    if candidates is None:
        return []
    if isinstance(candidates, RelatedSectionCandidateGeneration):
        return [dict(item) for item in candidates.related_section_candidates]
    if hasattr(candidates, "related_section_candidates"):
        value = getattr(candidates, "related_section_candidates")
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    if hasattr(candidates, "to_dict"):
        return _coerce_candidate_items(candidates.to_dict())
    if isinstance(candidates, Mapping):
        for key in ("related_section_candidates", "candidates"):
            value = candidates.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return [dict(item) for item in value if isinstance(item, Mapping)]
        if "source_section_id" in candidates and "target_section_id" in candidates:
            return [dict(candidates)]
        return []
    if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
        return [dict(item) for item in candidates if isinstance(item, Mapping)]
    return []


def _candidates_by_source(
    candidates: Sequence[Mapping[str, Any]],
    records_by_id: Mapping[str, _SectionRecord],
) -> dict[str, list[dict[str, Any]]]:
    by_source: dict[str, list[dict[str, Any]]] = {section_id: [] for section_id in records_by_id}
    for candidate in candidates:
        source_id = str(candidate.get("source_section_id", ""))
        target_id = str(candidate.get("target_section_id", ""))
        if source_id == target_id:
            continue
        if source_id not in records_by_id or target_id not in records_by_id:
            continue
        by_source[source_id].append(dict(candidate))
    for source_id, items in by_source.items():
        by_source[source_id] = sorted(items, key=_candidate_sort_key)
    return by_source


def _coerce_related_sections_by_source(value: Any) -> dict[str, list[dict[str, Any]]]:
    if isinstance(value, RelatedSectionSelection):
        return {
            source_id: [dict(item) for item in items]
            for source_id, items in value.related_sections.items()
        }
    if isinstance(value, RelatedSectionsGeneration):
        return _coerce_related_sections_by_source(value.selection)
    if hasattr(value, "to_dict"):
        return _coerce_related_sections_by_source(value.to_dict())
    if not isinstance(value, Mapping):
        return {}
    related = value.get("related_sections")
    if isinstance(related, Mapping):
        return {
            str(source_id): [dict(item) for item in items if isinstance(item, Mapping)]
            for source_id, items in related.items()
            if isinstance(items, Sequence) and not isinstance(items, (str, bytes))
        }
    sections = value.get("sections")
    result: dict[str, list[dict[str, Any]]] = {}
    if isinstance(sections, Sequence) and not isinstance(sections, (str, bytes)):
        for item in sections:
            if not isinstance(item, Mapping):
                continue
            section_id = item.get("source_section_id") or item.get("section_id")
            section_related = item.get("related_sections", [])
            if isinstance(section_id, str) and isinstance(section_related, Sequence) and not isinstance(section_related, (str, bytes)):
                result[section_id] = [
                    dict(related_item)
                    for related_item in section_related
                    if isinstance(related_item, Mapping)
                ]
    return result


def _requested_source_ids(
    records: Sequence[_SectionRecord],
    requested: Sequence[str] | None,
) -> list[str]:
    order = [record.source_section_id for record in records]
    if requested is None:
        return order
    requested_set = {str(item) for item in requested}
    return [section_id for section_id in order if section_id in requested_set]


def _metadata_records(
    metadata: Any | None,
    records: Sequence[_SectionRecord],
) -> dict[str, _MetadataRecord]:
    by_id: dict[str, _MetadataRecord] = {}
    for entry in _metadata_entries(metadata):
        section_id = str(entry.get("source_section_id") or entry.get("section_id") or "")
        if not section_id:
            continue
        related_sections = entry.get("related_sections", [])
        by_id[section_id] = _MetadataRecord(
            section_id=section_id,
            summary=str(entry.get("summary") or ""),
            search_keys=_list_of_strings(entry.get("search_keys", [])),
            identifiers=_list_of_strings(entry.get("identifiers", [])),
            related_sections=[
                dict(item)
                for item in related_sections
                if isinstance(item, Mapping)
            ]
            if isinstance(related_sections, Sequence)
            and not isinstance(related_sections, (str, bytes))
            else [],
        )
    for record in records:
        by_id.setdefault(record.source_section_id, _fallback_metadata(record))
    return by_id


def _metadata_entries(metadata: Any | None) -> list[dict[str, Any]]:
    if metadata is None:
        return []
    if hasattr(metadata, "to_dict"):
        return _metadata_entries(metadata.to_dict())
    if isinstance(metadata, Mapping):
        value = metadata.get("sections")
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [dict(item) for item in value if isinstance(item, Mapping)]
        if "section_id" in metadata or "source_section_id" in metadata:
            return [dict(metadata)]
        return []
    if isinstance(metadata, Sequence) and not isinstance(metadata, (str, bytes)):
        entries: list[dict[str, Any]] = []
        for item in metadata:
            if isinstance(item, Mapping):
                entries.append(dict(item))
            else:
                section_id = str(
                    _section_value(item, "source_section_id", _section_value(item, "section_id", "")),
                )
                if section_id:
                    entries.append(
                        {
                            "section_id": section_id,
                            "summary": _section_value(item, "summary", ""),
                            "search_keys": _section_value(item, "search_keys", []),
                            "identifiers": _section_value(item, "identifiers", []),
                            "related_sections": _section_value(item, "related_sections", []),
                        },
                    )
        return entries
    return []


def _fallback_metadata(record: _SectionRecord) -> _MetadataRecord:
    identifiers = extract_identifiers(record)
    heading_keys = [item for item in record.heading_path if item]
    return _MetadataRecord(
        section_id=record.source_section_id,
        summary=_fallback_summary(record),
        search_keys=_dedupe_public_terms([*heading_keys, *identifiers]),
        identifiers=identifiers,
        related_sections=[],
    )


def _metadata_for(
    record: _SectionRecord,
    metadata_by_id: Mapping[str, _MetadataRecord],
) -> _MetadataRecord:
    return metadata_by_id.get(record.source_section_id) or _fallback_metadata(record)


def _normalize_section(section: Any) -> _SectionRecord:
    text = str(_section_value(section, "text", ""))
    section_id = str(_section_value(section, "section_id", ""))
    source_section_id = str(_section_value(section, "source_section_id", section_id))
    if not source_section_id:
        source_section_id = section_id or _sha256_text(text)[:16]
    if not section_id:
        section_id = source_section_id
    source_document_id = str(_section_value(section, "source_document_id", ""))
    if not source_document_id and "#" in source_section_id:
        source_document_id = source_section_id.split("#", 1)[0]
    source_hash = str(_section_value(section, "source_hash", _sha256_text(text)))
    semantic_hash = str(_section_value(section, "semantic_hash", source_hash))
    return _SectionRecord(
        section_id=section_id,
        source_section_id=source_section_id,
        stable_section_uid=str(
            _section_value(section, "stable_section_uid", source_section_id),
        ),
        source_document_id=source_document_id,
        heading_path=_list_of_strings(_section_value(section, "heading_path", [])),
        chapter_id=str(_section_value(section, "chapter_id", source_document_id)),
        source_hash=source_hash,
        semantic_hash=semantic_hash,
        text=text,
    )


def _section_value(section: Any, key: str, default: Any) -> Any:
    if isinstance(section, Mapping):
        return section.get(key, default)
    return getattr(section, key, default)


def _candidate_snippet(
    target: _SectionRecord,
    metadata_by_id: Mapping[str, _MetadataRecord],
) -> str:
    metadata = _metadata_for(target, metadata_by_id)
    heading = " / ".join(target.heading_path)
    summary_or_text = metadata.summary or _short_text(target.text, 160)
    return _short_text(f"{target.source_section_id} {heading} {summary_or_text}", 240)


def _fallback_summary(record: _SectionRecord) -> str:
    heading = " / ".join(record.heading_path).strip()
    first_line = next(
        (line.strip() for line in record.text.splitlines() if line.strip()),
        "",
    )
    if heading and first_line:
        return f"{heading}: {first_line}"
    return heading or first_line


def _inverted_terms(values_by_section: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for section_id, values in values_by_section.items():
        seen_for_section: set[str] = set()
        for value in values:
            term = _normalize_key(value)
            if not term or term in seen_for_section:
                continue
            seen_for_section.add(term)
            index.setdefault(term, []).append(section_id)
    return index


def _candidate_channels(candidate: Mapping[str, Any]) -> list[str]:
    value = candidate.get("channels", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(channel) for channel in value if str(channel) in MVP_CANDIDATE_CHANNELS]


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value]


def _dedupe_public_terms(values: Sequence[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        _append_unique(result, _normalize_public_text(value))
    return result


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _normalize_public_text(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value).strip())


def _normalize_key(value: Any) -> str:
    return _normalize_public_text(value).casefold()


def _short_text(value: Any, max_chars: int) -> str:
    text = _normalize_public_text(value)
    if max_chars <= 0:
        return ""
    return text[:max_chars]


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_一-龯ぁ-んァ-ンー]+", "-", value.strip()).strip("-")
    return slug.casefold() or "section"


def _normalize_link_path(source_document_id: str, raw_path: str) -> str:
    path = PurePosixPath(raw_path)
    if path.is_absolute():
        return _normalize_posix_path(path.as_posix())
    base = PurePosixPath(source_document_id).parent
    return _normalize_posix_path((base / path).as_posix())


def _normalize_posix_path(value: str) -> str:
    parts: list[str] = []
    for part in PurePosixPath(value).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _limits(value: Any | None) -> LimitsConfig:
    if isinstance(value, LimitsConfig):
        return value
    if value is None:
        return LimitsConfig()
    return LimitsConfig(
        section_summary_max_chars=max(
            0,
            int(_config_value(value, "section_summary_max_chars", 480)),
        ),
        search_keys_max=max(0, int(_config_value(value, "search_keys_max", 32))),
        related_candidate_max_per_section=max(
            0,
            int(_config_value(value, "related_candidate_max_per_section", 32)),
        ),
        related_selected_max_per_section=max(
            0,
            int(_config_value(value, "related_selected_max_per_section", 8)),
        ),
        conflict_pair_max_per_section=max(
            0,
            int(_config_value(value, "conflict_pair_max_per_section", 8)),
        ),
        llm_batch_max_sections=max(
            1,
            int(_config_value(value, "llm_batch_max_sections", 8)),
        ),
        llm_batch_max_chars=max(
            1,
            int(_config_value(value, "llm_batch_max_chars", 12000)),
        ),
        llm_batch_concurrency=max(
            1,
            int(_config_value(value, "llm_batch_concurrency", 4)),
        ),
    )


def _model_name(llm_config: Any, provider_id: str) -> str:
    model = _config_value(llm_config, "model", None)
    if isinstance(model, str) and model:
        return model
    return provider_id or "fake"


def _config_value(config: Any, key: str, default: Any = None) -> Any:
    if config is None:
        return default
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _apply_positional_kwargs(
    kwargs: dict[str, Any],
    args: Sequence[Any],
    names: Sequence[str],
    function_name: str,
) -> None:
    if len(args) > len(names):
        raise TypeError(
            f"{function_name}() takes at most {len(names)} positional helper "
            f"arguments after the required arguments ({len(args)} given)"
        )
    for name, value in zip(names, args, strict=False):
        if name in kwargs:
            raise TypeError(f"{function_name}() got multiple values for {name!r}")
        kwargs[name] = value


def _diagnostic(
    reason_code: str,
    message: str,
    *,
    source_section_id: str | None = None,
    target_section_id: str | None = None,
    stage: str = "related_sections",
    severity: str = "warning",
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "reason_code": reason_code,
        "message": message,
        "stage": stage,
        "severity": severity,
    }
    if source_section_id is not None:
        item["source_section_id"] = source_section_id
    if target_section_id is not None:
        item["target_section_id"] = target_section_id
    item.update(extra)
    return item


def _validation_drop(
    reason_code: str,
    message: str,
    source_section_id: str,
    index: int,
    *,
    target_section_id: str | None = None,
) -> dict[str, Any]:
    return _diagnostic(
        reason_code,
        message,
        source_section_id=source_section_id,
        target_section_id=target_section_id,
        stage=RELATED_SECTIONS_STAGE,
        severity="warning",
        item_index=index,
        action="dropped",
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_RELATED_PROMPT_DEBUG_ENV = "SPEC_ANCHOR_DEBUG_RELATED_PROMPT"
_RELATED_PROMPT_DEBUG_PATH_ENV = "SPEC_ANCHOR_DEBUG_RELATED_PROMPT_PATH"
_DEFAULT_RELATED_PROMPT_DEBUG_PATH = Path(".spec-anchor/state/_debug_related_prompts.jsonl")


def _related_prompt_debug_path() -> Path | None:
    """Return the JSONL destination for the related_sections prompt debug log.

    Activation rule: writing only happens when `SPEC_ANCHOR_DEBUG_RELATED_PROMPT`
    is set to a truthy value ("1" / "true" / "yes"). The override path env var
    `SPEC_ANCHOR_DEBUG_RELATED_PROMPT_PATH` (if set) wins; otherwise the file is
    placed at `<cwd>/.spec-anchor/state/_debug_related_prompts.jsonl`. The CLI
    always runs `spec-anchor core` from the project root, so cwd-relative is
    consistent with the rest of the state layout (`.spec-anchor/state/`).
    """

    flag = os.environ.get(_RELATED_PROMPT_DEBUG_ENV, "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return None
    override = os.environ.get(_RELATED_PROMPT_DEBUG_PATH_ENV, "").strip()
    if override:
        return Path(override)
    return _DEFAULT_RELATED_PROMPT_DEBUG_PATH


def _log_related_prompt_debug(
    *,
    request_kind: str,
    payload: Mapping[str, Any],
    prompt: str,
    primary_section_id: str,
    batch_source_ids: Sequence[str],
    involved_section_ids: Sequence[str],
) -> None:
    """Append a per-prompt hash record to the related_sections debug JSONL.

    No-op when `SPEC_ANCHOR_DEBUG_RELATED_PROMPT` is unset / falsy. Errors during
    write are swallowed to avoid disturbing the production run that owns the
    LLM call — the debug log is observational only and not on the success path.
    """

    target = _related_prompt_debug_path()
    if target is None:
        return
    catalog_obj = payload.get("catalog")
    evaluations_obj = payload.get("evaluations")
    candidates_obj = payload.get("candidates")
    source_section_obj = payload.get("source_section")
    catalog_keys = (
        sorted({key for entry in catalog_obj.values() if isinstance(entry, Mapping) for key in entry.keys()})
        if isinstance(catalog_obj, Mapping)
        else []
    )
    record = {
        "timestamp": _now(),
        "request_kind": request_kind,
        "prompt_full_sha256": _sha256_text(prompt),
        "prompt_len": len(prompt),
        "primary_section_id": primary_section_id,
        "batch_source_ids": list(batch_source_ids),
        "involved_section_ids": sorted(set(involved_section_ids)),
        "catalog_size": (
            len(catalog_obj) if isinstance(catalog_obj, Mapping) else None
        ),
        "catalog_entry_keys": catalog_keys,
        "catalog_sha256": (
            _sha256_text(_stable_json(catalog_obj))
            if isinstance(catalog_obj, Mapping)
            else None
        ),
        "evaluations_sha256": (
            _sha256_text(
                _stable_json({"evaluations": list(evaluations_obj)})
            )
            if isinstance(evaluations_obj, Sequence)
            and not isinstance(evaluations_obj, (str, bytes))
            else None
        ),
        "candidates_sha256": (
            _sha256_text(
                _stable_json({"candidates": list(candidates_obj)})
            )
            if isinstance(candidates_obj, Sequence)
            and not isinstance(candidates_obj, (str, bytes))
            else None
        ),
        "source_section_sha256": (
            _sha256_text(_stable_json(source_section_obj))
            if isinstance(source_section_obj, Mapping)
            else None
        ),
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    except OSError:
        # Debug instrumentation must never block the run.
        return


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _retrieval_auxiliary_metadata() -> dict[str, Any]:
    return {
        "role": "retrieval_auxiliary",
        "retrieval_aid_not_evidence": True,
        "reference_helper": True,
        "support_refs": True,
        "support_ref_kinds": ["related_sections"],
        "evidence": False,
        "final_constraint_provenance": False,
        "agentic_search_owner": "agent_llm",
        "cli_role": "high_recall_candidates_and_candidate_selection_boundary",
    }


def _related_candidate_limit_events(
    diagnostics: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in diagnostics
        if item.get("reason_code")
        in {"candidate_limit_exceeded", "related_candidate_limit", "related_candidate_limit_exceeded"}
    ]


__all__ = [
    "ALLOWED_CONFIDENCE",
    "ALLOWED_RELATION_HINTS",
    "MVP_CANDIDATE_CHANNELS",
    "RELATED_SECTIONS_PROMPT_VERSION",
    "RELATED_SECTIONS_ROLE",
    "RelatedSectionCandidateGeneration",
    "RelatedSectionSelection",
    "RelatedSectionValidation",
    "RelatedSectionsGeneration",
    "apply_related_sections_to_metadata",
    "build_related_section_candidates",
    "compute_related_sections_reevaluation_targets",
    "generate_related_section_candidates",
    "generate_related_section_candidates_result",
    "generate_related_sections",
    "generate_related_sections_partial",
    "generate_related_sections_partial_result",
    "generate_related_sections_result",
    "related_section_reevaluation_targets",
    "select_related_sections",
    "select_related_sections_result",
    "validate_related_sections",
    "validate_related_sections_result",
]
