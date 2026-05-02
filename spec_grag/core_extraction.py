"""Schema LLM extraction helpers for /spec-core."""

from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode, Relation
from llama_index.core.indices.property_graph.transformations.schema_llm import (
    KG_NODES_KEY,
    KG_RELATIONS_KEY,
)
from llama_index.core.schema import TextNode

from spec_grag.extraction import (
    BatchExtractionResponse,
    ExtractionProvenance,
    SPEC_GRAG_BATCH_EXTRACT_PROMPT,
    make_schema_llm_path_extractor,
)
from spec_grag.chunk_index import stable_chunk_uid_for
from spec_grag.embedding import stable_embedding
from spec_grag.llm_adapters import ClaudeCLIAdapter, CodexCLIAdapter
from spec_grag.manifest import SourceManifest, SourceManifestEntry
from spec_grag.sidecars import (
    UnresolvedRelationEntry,
    UnresolvedRelationReason,
    unresolved_relation_id_for,
)


SCHEMA_LLM_EXTRACTOR_NAME = "SchemaLLMPathExtractor"
SCHEMA_LLM_EXTRACTOR_VERSION = "schema-llm-path-v1"

EXTRACTION_MODE_DETERMINISTIC = "deterministic"
EXTRACTION_MODE_SCHEMA_LLM = "schema_llm"

GROUNDING_SCORE_THRESHOLD = 0.9
GROUNDING_SCORE_MARGIN = 0.15

CHAPTER_RELATION_TYPES = {
    "RELATED_TO",
    "DEPENDS_ON",
    "REFINES",
    "CONTRASTS_WITH",
}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


class SchemaExtractor(Protocol):
    def __call__(
        self, nodes: Sequence[TextNode], show_progress: bool = False, **kwargs: Any
    ) -> list[TextNode]:
        ...


class ExtractionLLM(Protocol):
    def complete(self, prompt: str, **kwargs: Any) -> Any:
        ...


@dataclass(frozen=True)
class SchemaLLMExtractionResult:
    graph_store: SimplePropertyGraphStore
    unresolved_entries: list[UnresolvedRelationEntry] = field(default_factory=list)
    failed_section_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ExtractionJob:
    section_id: str
    entry: SourceManifestEntry
    source_node: TextNode
    provenance: ExtractionProvenance


@dataclass(frozen=True)
class _ExtractionOutcome:
    section_id: str
    nodes: list[EntityNode] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    unresolved_entries: list[UnresolvedRelationEntry] = field(default_factory=list)
    warning: str | None = None


@dataclass(frozen=True)
class _ResolvedEndpoint:
    node_id: str | None
    label: str
    hint: str
    reason: UnresolvedRelationReason | None = None
    score: float = 0.0
    second_score: float = 0.0
    methods: tuple[str, ...] = ()


@dataclass(frozen=True)
class _NormalizationResult:
    nodes: list[EntityNode] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    unresolved_entries: list[UnresolvedRelationEntry] = field(default_factory=list)


@dataclass(frozen=True)
class _GroundingCandidate:
    node_id: str
    document_id: str
    chapter_id: str
    section_id: str | None
    heading_path: str
    heading_title: str
    heading_start_line: int
    text: str


@dataclass(frozen=True)
class _GroundingScore:
    candidate: _GroundingCandidate
    score: float
    methods: tuple[str, ...]


@dataclass(frozen=True)
class _GroundingDecision:
    node_id: str | None
    reason: UnresolvedRelationReason | None
    score: float = 0.0
    second_score: float = 0.0
    methods: tuple[str, ...] = ()


class _GroundingIndex:
    def __init__(
        self,
        manifest: SourceManifest,
        *,
        section_texts: Mapping[str, str] | None = None,
        score_threshold: float = GROUNDING_SCORE_THRESHOLD,
        score_margin: float = GROUNDING_SCORE_MARGIN,
    ) -> None:
        self.score_threshold = score_threshold
        self.score_margin = score_margin
        self.section_texts = dict(section_texts or {})
        self.chapter_hints: dict[str, set[str]] = defaultdict(set)
        self.section_hints: dict[str, set[str]] = defaultdict(set)
        self.chapter_candidates: list[_GroundingCandidate] = []
        self.section_candidates: list[_GroundingCandidate] = []
        chapter_seen: set[str] = set()
        chapter_texts: dict[str, str] = defaultdict(str)
        for entry in manifest.entries:
            chapter_texts[entry.chapter_id] += "\n" + self.section_texts.get(
                entry.section_id, ""
            )

        for entry in manifest.entries:
            chapter_title = entry.heading_path.split(" / ")[0]
            self._add_chapter_hint(entry.chapter_id, entry.chapter_id)
            self._add_chapter_hint(chapter_title, entry.chapter_id)
            self._add_chapter_hint(_slugify(chapter_title), entry.chapter_id)
            if entry.chapter_id not in chapter_seen:
                self.chapter_candidates.append(
                    _GroundingCandidate(
                        node_id=entry.chapter_id,
                        document_id=entry.document_id,
                        chapter_id=entry.chapter_id,
                        section_id=None,
                        heading_path=chapter_title,
                        heading_title=chapter_title,
                        heading_start_line=entry.heading_start_line,
                        text=chapter_texts[entry.chapter_id],
                    )
                )
                chapter_seen.add(entry.chapter_id)

            section_title = entry.heading_path.split(" / ")[-1]
            self._add_section_hint(entry.section_id, entry.section_id)
            self._add_section_hint(section_node_id_for(entry.section_id), entry.section_id)
            self._add_section_hint(entry.heading_path, entry.section_id)
            self._add_section_hint(section_title, entry.section_id)
            self._add_section_hint(_slugify(section_title), entry.section_id)
            self.section_candidates.append(
                _GroundingCandidate(
                    node_id=entry.section_id,
                    document_id=entry.document_id,
                    chapter_id=entry.chapter_id,
                    section_id=entry.section_id,
                    heading_path=entry.heading_path,
                    heading_title=section_title,
                    heading_start_line=entry.heading_start_line,
                    text=self.section_texts.get(entry.section_id, ""),
                )
            )

    def resolve_chapter(
        self,
        hint: str,
        *,
        current_entry: SourceManifestEntry | None = None,
        evidence_excerpt: str | None = None,
        source_span: str | None = None,
    ) -> _GroundingDecision:
        return self._resolve_scored(
            self.chapter_candidates,
            self.chapter_hints,
            hint,
            current_entry=current_entry,
            evidence_excerpt=evidence_excerpt,
            source_span=source_span,
        )

    def resolve_section(
        self,
        hint: str,
        *,
        current_entry: SourceManifestEntry | None = None,
        evidence_excerpt: str | None = None,
        source_span: str | None = None,
    ) -> _GroundingDecision:
        decision = self._resolve_scored(
            self.section_candidates,
            self.section_hints,
            hint,
            current_entry=current_entry,
            evidence_excerpt=evidence_excerpt,
            source_span=source_span,
        )
        if decision.node_id is None:
            return decision
        return _GroundingDecision(
            node_id=section_node_id_for(decision.node_id),
            reason=None,
            score=decision.score,
            second_score=decision.second_score,
            methods=decision.methods,
        )

    def _add_chapter_hint(self, hint: str, chapter_id: str) -> None:
        normalized = _normalize_hint(hint)
        if normalized:
            self.chapter_hints[normalized].add(chapter_id)
        compact = _compact_hint(normalized)
        if compact and compact != normalized:
            self.chapter_hints[compact].add(chapter_id)

    def _add_section_hint(self, hint: str, section_id: str) -> None:
        normalized = _normalize_hint(hint)
        if normalized:
            self.section_hints[normalized].add(section_id)
        compact = _compact_hint(normalized)
        if compact and compact != normalized:
            self.section_hints[compact].add(section_id)

    def _resolve_scored(
        self,
        candidates: Sequence[_GroundingCandidate],
        index: Mapping[str, set[str]],
        hint: str,
        *,
        current_entry: SourceManifestEntry | None,
        evidence_excerpt: str | None,
        source_span: str | None,
    ) -> _GroundingDecision:
        normalized = _normalize_hint(hint)
        matches = index.get(normalized, set())
        if not matches:
            compact = _compact_hint(normalized)
            matches = index.get(compact, set()) if compact else set()

        scored = [
            self._score_candidate(
                candidate,
                hint,
                current_entry=current_entry,
                evidence_excerpt=evidence_excerpt,
                source_span=source_span,
                exact_match=candidate.node_id in matches,
            )
            for candidate in candidates
        ]
        scored = [item for item in scored if item.score > 0.0]
        scored.sort(key=lambda item: (-item.score, item.candidate.node_id))
        if not scored:
            return _GroundingDecision(None, UnresolvedRelationReason.MISSING_TARGET)

        best = scored[0]
        second_score = scored[1].score if len(scored) > 1 else 0.0
        if best.score < self.score_threshold:
            return _GroundingDecision(
                None,
                UnresolvedRelationReason.AMBIGUOUS_TARGET,
                score=best.score,
                second_score=second_score,
                methods=best.methods,
            )
        if len(scored) > 1 and best.score - second_score < self.score_margin:
            return _GroundingDecision(
                None,
                UnresolvedRelationReason.AMBIGUOUS_TARGET,
                score=best.score,
                second_score=second_score,
                methods=best.methods,
            )
        return _GroundingDecision(
            best.candidate.node_id,
            None,
            score=best.score,
            second_score=second_score,
            methods=best.methods,
        )

    def _score_candidate(
        self,
        candidate: _GroundingCandidate,
        hint: str,
        *,
        current_entry: SourceManifestEntry | None,
        evidence_excerpt: str | None,
        source_span: str | None,
        exact_match: bool,
    ) -> _GroundingScore:
        score = 0.0
        methods: list[str] = []
        normalized_hint = _normalize_hint(hint)
        compact_hint = _compact_hint(normalized_hint)

        id_key = _normalize_hint(candidate.node_id)
        path_key = _normalize_hint(candidate.heading_path)
        title_key = _normalize_hint(candidate.heading_title)
        compact_id = _compact_hint(id_key)
        compact_path = _compact_hint(path_key)
        compact_title = _compact_hint(title_key)

        if exact_match and normalized_hint == id_key:
            score += 1.5
            methods.append("exact_id")
        elif exact_match and compact_hint == compact_id:
            score += 1.35
            methods.append("compact_id")
        elif normalized_hint == path_key:
            score += 1.3
            methods.append("exact_heading_path")
        elif compact_hint and compact_hint == compact_path:
            score += 1.2
            methods.append("compact_heading_path")
        elif normalized_hint == title_key:
            score += 0.9
            methods.append("exact_heading")
        elif compact_hint and compact_hint == compact_title:
            score += 0.85
            methods.append("compact_heading")
        elif normalized_hint and (
            normalized_hint in path_key or title_key in normalized_hint
        ):
            score += 0.35
            methods.append("partial_heading")

        token_score = _token_overlap_score(normalized_hint, path_key)
        if token_score:
            score += token_score * 0.25
            methods.append("heading_token_overlap")

        similarity = _embedding_similarity(
            stable_embedding(hint, dimensions=16),
            stable_embedding(candidate.heading_path, dimensions=16),
        )
        if similarity >= 0.97:
            score += 0.05
            methods.append("embedding_similarity")

        if evidence_excerpt and _contains_excerpt(candidate.text, evidence_excerpt):
            score += 0.12
            methods.append("evidence_excerpt_containment")

        span = _parse_line_span(source_span)
        if span is not None and span[0] - 5 <= candidate.heading_start_line <= span[1] + 5:
            score += 0.05
            if "span_proximity" not in methods:
                methods.append("span_proximity")

        if current_entry is not None and methods:
            if candidate.document_id == current_entry.document_id:
                score += 0.08
                methods.append("same_document")
            if candidate.chapter_id == current_entry.chapter_id:
                score += 0.18
                methods.append("same_chapter")
            if candidate.section_id == current_entry.section_id:
                score += 0.05
                methods.append("anchor_proximity")
            if _nearby_lines(candidate.heading_start_line, current_entry.heading_start_line):
                score += 0.05
                methods.append("span_proximity")

        return _GroundingScore(candidate, round(score, 6), tuple(sorted(set(methods))))


def extraction_mode(config: Mapping[str, Any]) -> str:
    extraction_config = _mapping(config.get("extraction"))
    core_config = _mapping(config.get("core"))
    raw_mode = extraction_config.get("mode") or core_config.get("extraction_mode")
    mode = str(raw_mode or EXTRACTION_MODE_DETERMINISTIC).strip().lower().replace("-", "_")
    if mode in {"llm", "schema"}:
        return EXTRACTION_MODE_SCHEMA_LLM
    if mode not in {EXTRACTION_MODE_DETERMINISTIC, EXTRACTION_MODE_SCHEMA_LLM}:
        raise ValueError(f"unsupported extraction.mode: {raw_mode}")
    return mode


def schema_llm_batch_enabled(config: Mapping[str, Any]) -> bool:
    extraction_config = _mapping(config.get("extraction"))
    return int(extraction_config.get("batch_size", 1)) > 1


def make_extraction_llm_from_config(config: Mapping[str, Any]) -> ExtractionLLM:
    extraction_config = _mapping(config.get("extraction"))
    provider = str(extraction_config.get("provider", "codex")).strip().lower()
    if provider == "codex":
        return CodexCLIAdapter(
            command=str(extraction_config.get("command") or "codex"),
            model=str(extraction_config.get("model") or "gpt-5.4"),
            effort=str(extraction_config.get("effort") or "low"),
            timeout_sec=int(extraction_config.get("timeout_sec", 120)),
            max_retries=int(extraction_config.get("max_retries", 0)),
            retry_backoff_sec=float(extraction_config.get("retry_backoff_sec", 0.0)),
            repair_on_schema_failure=bool(
                extraction_config.get("repair_on_schema_failure", True)
            ),
        )
    if provider == "claude":
        return ClaudeCLIAdapter(
            command=str(extraction_config.get("command") or "claude"),
            model=str(extraction_config.get("model") or ""),
            effort=str(extraction_config.get("effort") or "low"),
            timeout_sec=int(extraction_config.get("timeout_sec", 120)),
            max_retries=int(extraction_config.get("max_retries", 0)),
            retry_backoff_sec=float(extraction_config.get("retry_backoff_sec", 0.0)),
            repair_on_schema_failure=bool(
                extraction_config.get("repair_on_schema_failure", True)
            ),
        )
    raise ValueError(f"unsupported extraction.provider: {provider}")


def make_schema_extractor_from_config(config: Mapping[str, Any]) -> SchemaExtractor:
    extraction_config = _mapping(config.get("extraction"))
    llm = make_extraction_llm_from_config(config)
    return make_schema_llm_path_extractor(
        llm,
        max_triplets_per_chunk=int(extraction_config.get("max_triplets_per_chunk", 20)),
        num_workers=int(extraction_config.get("num_workers", 4)),
    )


def extract_schema_llm_artifacts(
    *,
    project_root: Path,
    manifest: SourceManifest,
    graph_store: SimplePropertyGraphStore,
    config: Mapping[str, Any],
    extract_run_id: str,
    extracted_at: str,
    section_ids_to_extract: Sequence[str],
    schema_extractor: SchemaExtractor | None = None,
    document_texts: Mapping[str, str] | None = None,
) -> SchemaLLMExtractionResult:
    extraction_config = _mapping(config.get("extraction"))
    entries_by_id = manifest.by_section_id()
    section_texts = read_section_texts(
        project_root,
        manifest,
        document_texts=document_texts,
    )
    grounding = _GroundingIndex(
        manifest,
        section_texts=section_texts,
        score_threshold=float(
            extraction_config.get(
                "grounding_score_threshold",
                GROUNDING_SCORE_THRESHOLD,
            )
        ),
        score_margin=float(
            extraction_config.get("grounding_score_margin", GROUNDING_SCORE_MARGIN)
        ),
    )

    all_nodes: list[EntityNode] = []
    all_relations: list[Relation] = []
    unresolved_entries: list[UnresolvedRelationEntry] = []
    failed_section_ids: list[str] = []
    warnings: list[str] = []
    jobs: list[_ExtractionJob] = []

    for section_id in section_ids_to_extract:
        entry = entries_by_id.get(section_id)
        if entry is None:
            continue

        source_text = section_texts.get(section_id, "")
        provenance = ExtractionProvenance(
            source_document_id=entry.document_id,
            source_chapter_id=entry.chapter_id,
            source_section_id=entry.section_id,
            source_chunk_id=entry.section_id,
            stable_source_section_uid=entry.stable_section_uid,
            stable_source_chunk_uid=_section_level_stable_chunk_uid(entry),
            source_hash=entry.source_hash,
            extract_run_id=extract_run_id,
            extractor_name=SCHEMA_LLM_EXTRACTOR_NAME,
            extractor_version=SCHEMA_LLM_EXTRACTOR_VERSION,
            extracted_at=extracted_at,
        )
        source_node = TextNode(
            id_=f"source-chunk:{entry.section_id}",
            text=source_text,
            metadata={
                **provenance.to_metadata(),
                "current_section_id": entry.section_id,
                "current_chapter_id": entry.chapter_id,
                "heading_path": entry.heading_path,
                "doc_path": entry.document_id,
            },
        )
        jobs.append(
            _ExtractionJob(
                section_id=section_id,
                entry=entry,
                source_node=source_node,
                provenance=provenance,
            )
        )

    worker_count = max(1, int(extraction_config.get("num_workers", 4)))
    batch_size = max(1, int(extraction_config.get("batch_size", 1)))
    if schema_extractor is None and batch_size > 1:
        llm = make_extraction_llm_from_config(config)
        batches = _batch_extraction_jobs(
            jobs,
            batch_size=batch_size,
            batch_max_chars=int(extraction_config.get("batch_max_chars", 4000)),
        )
        max_triplets_per_chunk = int(extraction_config.get("max_triplets_per_chunk", 20))
        if worker_count > 1 and len(batches) > 1:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = [
                    executor.submit(
                        _extract_schema_batch,
                        llm,
                        batch,
                        grounding,
                        max_triplets_per_batch=max_triplets_per_chunk * len(batch),
                    )
                    for batch in batches
                ]
                outcomes = [
                    outcome
                    for future in as_completed(futures)
                    for outcome in future.result()
                ]
        else:
            outcomes = [
                outcome
                for batch in batches
                for outcome in _extract_schema_batch(
                    llm,
                    batch,
                    grounding,
                    max_triplets_per_batch=max_triplets_per_chunk * len(batch),
                )
            ]
    elif worker_count > 1 and len(jobs) > 1:
        extractor = schema_extractor or make_schema_extractor_from_config(config)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_section = {
                executor.submit(_extract_schema_job, extractor, job, grounding): job.section_id
                for job in jobs
            }
            outcomes = [
                future.result()
                for future in as_completed(future_to_section)
            ]
    else:
        extractor = schema_extractor or make_schema_extractor_from_config(config)
        outcomes = [_extract_schema_job(extractor, job, grounding) for job in jobs]

    order = {section_id: index for index, section_id in enumerate(section_ids_to_extract)}
    for outcome in sorted(
        outcomes,
        key=lambda item: order.get(item.section_id, len(order)),
    ):
        if outcome.warning is not None:
            failed_section_ids.append(outcome.section_id)
            warnings.append(outcome.warning)
            continue
        all_nodes.extend(outcome.nodes)
        all_relations.extend(outcome.relations)
        unresolved_entries.extend(outcome.unresolved_entries)

    if all_nodes:
        graph_store.upsert_nodes(_dedupe_nodes(all_nodes))
    if all_relations:
        graph_store.upsert_relations(_dedupe_relations(all_relations))

    return SchemaLLMExtractionResult(
        graph_store=graph_store,
        unresolved_entries=sorted(
            unresolved_entries, key=lambda entry: entry.unresolved_relation_id
        ),
        failed_section_ids=sorted(set(failed_section_ids)),
        warnings=warnings,
    )


def _batch_extraction_jobs(
    jobs: Sequence[_ExtractionJob],
    *,
    batch_size: int,
    batch_max_chars: int,
) -> list[list[_ExtractionJob]]:
    batches: list[list[_ExtractionJob]] = []
    current: list[_ExtractionJob] = []
    current_chars = 0
    for job in jobs:
        text_len = len(job.source_node.text or "")
        if current and (
            len(current) >= batch_size or current_chars + text_len > batch_max_chars
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(job)
        current_chars += text_len
    if current:
        batches.append(current)
    return batches


def _extract_schema_batch(
    llm: ExtractionLLM,
    jobs: Sequence[_ExtractionJob],
    grounding: _GroundingIndex,
    *,
    max_triplets_per_batch: int,
) -> list[_ExtractionOutcome]:
    try:
        sections_json = json.dumps(
            [
                {
                    "source_section_id": job.section_id,
                    "source_document_id": job.entry.document_id,
                    "current_chapter_id": job.entry.chapter_id,
                    "heading_path": job.entry.heading_path,
                    "heading_start_line": job.entry.heading_start_line,
                    "text": job.source_node.text,
                }
                for job in jobs
            ],
            ensure_ascii=False,
            indent=2,
        )
        prompt = SPEC_GRAG_BATCH_EXTRACT_PROMPT.format(
            sections_json=sections_json,
            max_triplets_per_batch=max_triplets_per_batch,
        )
        response = llm.complete(prompt, output_schema=BatchExtractionResponse)
        batch = BatchExtractionResponse.model_validate_json(response.text)
    except Exception as exc:
        return [
            _ExtractionOutcome(
                section_id=job.section_id,
                warning=f"schema_llm_batch_extraction_failed:{job.section_id}:{exc}",
            )
            for job in jobs
        ]

    jobs_by_id = {job.section_id: job for job in jobs}
    nodes_by_section: dict[str, list[EntityNode]] = defaultdict(list)
    relations_by_section: dict[str, list[Relation]] = defaultdict(list)
    for triplet in batch.triplets[:max_triplets_per_batch]:
        job = jobs_by_id.get(triplet.source_section_id)
        if job is None:
            continue
        subject = EntityNode(
            label=triplet.subject.type,
            name=triplet.subject.name,
            properties=triplet.subject.properties.model_dump(mode="json"),
        )
        obj = EntityNode(
            label=triplet.object.type,
            name=triplet.object.name,
            properties=triplet.object.properties.model_dump(mode="json"),
        )
        relation = Relation(
            label=triplet.relation.type,
            source_id=subject.id,
            target_id=obj.id,
            properties=triplet.relation.properties.model_dump(mode="json"),
        )
        nodes_by_section[job.section_id].extend([subject, obj])
        relations_by_section[job.section_id].append(relation)

    outcomes: list[_ExtractionOutcome] = []
    for job in jobs:
        normalized = normalize_extracted_artifacts(
            entry=job.entry,
            extracted_nodes=nodes_by_section.get(job.section_id, []),
            extracted_relations=relations_by_section.get(job.section_id, []),
            provenance=job.provenance,
            grounding=grounding,
        )
        outcomes.append(
            _ExtractionOutcome(
                section_id=job.section_id,
                nodes=normalized.nodes,
                relations=normalized.relations,
                unresolved_entries=normalized.unresolved_entries,
            )
        )
    return outcomes


def _extract_schema_job(
    extractor: SchemaExtractor,
    job: _ExtractionJob,
    grounding: _GroundingIndex,
) -> _ExtractionOutcome:
    try:
        extracted_nodes = extractor([job.source_node], show_progress=False)
    except Exception as exc:
        return _ExtractionOutcome(
            section_id=job.section_id,
            warning=f"schema_llm_extraction_failed:{job.section_id}:{exc}",
        )

    nodes: list[EntityNode] = []
    relations: list[Relation] = []
    unresolved_entries: list[UnresolvedRelationEntry] = []
    for extracted_node in extracted_nodes:
        normalized = normalize_extracted_artifacts(
            entry=job.entry,
            extracted_nodes=extracted_node.metadata.get(KG_NODES_KEY, []),
            extracted_relations=extracted_node.metadata.get(KG_RELATIONS_KEY, []),
            provenance=job.provenance,
            grounding=grounding,
        )
        nodes.extend(normalized.nodes)
        relations.extend(normalized.relations)
        unresolved_entries.extend(normalized.unresolved_entries)
    return _ExtractionOutcome(
        section_id=job.section_id,
        nodes=nodes,
        relations=relations,
        unresolved_entries=unresolved_entries,
    )


def normalize_extracted_artifacts(
    *,
    entry: SourceManifestEntry,
    extracted_nodes: Sequence[EntityNode],
    extracted_relations: Sequence[Relation],
    provenance: ExtractionProvenance,
    grounding: _GroundingIndex,
) -> _NormalizationResult:
    raw_nodes = {node.id: node for node in extracted_nodes}
    endpoint_cache: dict[str, _ResolvedEndpoint] = {}
    anchor_nodes: dict[str, EntityNode] = {}
    relations: list[Relation] = []
    unresolved_entries: list[UnresolvedRelationEntry] = []

    for node in extracted_nodes:
        if node.label == "ANCHOR":
            anchor = _anchor_from_raw(entry, node, provenance)
            anchor_nodes[node.id] = anchor

    for relation in extracted_relations:
        label = str(relation.label)
        props = _clean_properties(relation.properties or {})
        confidence = _confidence(props)

        if label == "MENTIONS":
            anchor = _relation_anchor_target(relation, raw_nodes, anchor_nodes)
            if anchor is None:
                continue
            relations.append(
                Relation(
                    label="MENTIONS",
                    source_id=section_node_id_for(entry.section_id),
                    target_id=anchor.id,
                    properties={
                        **props,
                        **provenance.to_metadata(),
                        "confidence": confidence,
                    },
                )
            )
            continue

        if label not in CHAPTER_RELATION_TYPES:
            continue

        source = _resolve_endpoint(
            relation.source_id,
            raw_nodes,
            anchor_nodes,
            grounding,
            endpoint_cache,
            current_entry=entry,
            relation_properties=props,
            default_chapter_id=entry.chapter_id,
        )
        target = _resolve_endpoint(
            relation.target_id,
            raw_nodes,
            anchor_nodes,
            grounding,
            endpoint_cache,
            current_entry=entry,
            relation_properties=props,
            default_chapter_id=None,
        )

        if confidence == "low":
            unresolved_entries.append(
                _unresolved_entry(
                    entry=entry,
                    source_id=source.node_id or entry.chapter_id,
                    relation_type=label,
                    target_hint=target.hint,
                    reason=UnresolvedRelationReason.LOW_CONFIDENCE,
                    evidence_excerpt=_evidence_excerpt(props),
                    provenance=provenance,
                )
            )
            continue

        if source.node_id is None or target.node_id is None:
            unresolved_entries.append(
                _unresolved_entry(
                    entry=entry,
                    source_id=source.node_id or entry.chapter_id,
                    relation_type=label,
                    target_hint=target.hint,
                    reason=target.reason
                    or source.reason
                    or UnresolvedRelationReason.MISSING_TARGET,
                    evidence_excerpt=_evidence_excerpt(props),
                    provenance=provenance,
                )
            )
            continue

        relations.append(
            Relation(
                label=label,
                source_id=source.node_id,
                target_id=target.node_id,
                properties={
                    **props,
                    **provenance.to_metadata(),
                    "confidence": confidence,
                    **_grounding_properties("source", source),
                    **_grounding_properties("target", target),
                },
            )
        )

    return _NormalizationResult(
        nodes=list(anchor_nodes.values()),
        relations=relations,
        unresolved_entries=unresolved_entries,
    )


def carry_forward_schema_llm_artifacts(
    graph_store: SimplePropertyGraphStore,
    previous_graph_store: SimplePropertyGraphStore,
    *,
    keep_section_ids: Sequence[str],
) -> SimplePropertyGraphStore:
    keep = set(keep_section_ids)
    data = previous_graph_store.graph.model_dump()
    nodes = [
        EntityNode.model_validate(raw_node)
        for raw_node in (data.get("nodes") or {}).values()
        if _is_schema_llm_artifact(raw_node, keep)
    ]
    relations = [
        Relation.model_validate(raw_relation)
        for raw_relation in (data.get("relations") or {}).values()
        if _is_schema_llm_artifact(raw_relation, keep)
    ]
    if nodes:
        graph_store.upsert_nodes(nodes)
    if relations:
        graph_store.upsert_relations(_dedupe_relations(relations))
    return graph_store


def read_section_texts(
    project_root: Path,
    manifest: SourceManifest,
    *,
    document_texts: Mapping[str, str] | None = None,
) -> dict[str, str]:
    texts: dict[str, str] = {}
    by_document: dict[str, list[SourceManifestEntry]] = defaultdict(list)
    for entry in manifest.entries:
        by_document[entry.document_id].append(entry)

    for document_id, entries in by_document.items():
        path = Path(document_id)
        if not path.is_absolute():
            path = project_root / path
        text = (
            document_texts.get(document_id)
            if document_texts is not None
            else None
        )
        if text is None:
            text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        ordered = sorted(entries, key=lambda item: (item.heading_start_line, item.section_id))
        for index, entry in enumerate(ordered):
            start = max(entry.heading_start_line - 1, 0)
            end = (
                max(ordered[index + 1].heading_start_line - 1, start)
                if index + 1 < len(ordered)
                else len(lines)
            )
            texts[entry.section_id] = "".join(lines[start:end])
    return texts


def section_node_id_for(section_id: str) -> str:
    return f"section:{section_id}"


def _relation_anchor_target(
    relation: Relation,
    raw_nodes: Mapping[str, EntityNode],
    anchor_nodes: Mapping[str, EntityNode],
) -> EntityNode | None:
    if relation.target_id in anchor_nodes:
        return anchor_nodes[relation.target_id]
    if relation.source_id in anchor_nodes:
        return anchor_nodes[relation.source_id]

    raw_target = raw_nodes.get(relation.target_id)
    if raw_target is not None and raw_target.label == "ANCHOR":
        return anchor_nodes.get(raw_target.id)
    raw_source = raw_nodes.get(relation.source_id)
    if raw_source is not None and raw_source.label == "ANCHOR":
        return anchor_nodes.get(raw_source.id)
    return None


def _resolve_endpoint(
    raw_id: str,
    raw_nodes: Mapping[str, EntityNode],
    anchor_nodes: Mapping[str, EntityNode],
    grounding: _GroundingIndex,
    endpoint_cache: dict[str, _ResolvedEndpoint],
    *,
    current_entry: SourceManifestEntry,
    relation_properties: Mapping[str, Any],
    default_chapter_id: str | None,
) -> _ResolvedEndpoint:
    if raw_id in endpoint_cache:
        return endpoint_cache[raw_id]
    if raw_id in anchor_nodes:
        endpoint = _ResolvedEndpoint(
            node_id=anchor_nodes[raw_id].id,
            label="ANCHOR",
            hint=_display_name(raw_nodes.get(raw_id), raw_id),
        )
        endpoint_cache[raw_id] = endpoint
        return endpoint

    raw_node = raw_nodes.get(raw_id)
    label = str(raw_node.label if raw_node is not None else "")
    hint = _display_name(raw_node, raw_id)
    evidence_excerpt = _evidence_excerpt(relation_properties)
    source_span = _source_span(relation_properties)

    if label == "CHAPTER":
        decision = grounding.resolve_chapter(
            hint,
            current_entry=current_entry,
            evidence_excerpt=evidence_excerpt,
            source_span=source_span,
        )
        if decision.node_id is None and default_chapter_id is not None:
            endpoint = _ResolvedEndpoint(
                default_chapter_id,
                label,
                hint,
                None,
                score=decision.score,
                second_score=decision.second_score,
                methods=tuple(sorted(set(decision.methods + ("default_current_chapter",)))),
            )
        else:
            endpoint = _ResolvedEndpoint(
                decision.node_id,
                label,
                hint,
                decision.reason,
                score=decision.score,
                second_score=decision.second_score,
                methods=decision.methods,
            )
    elif label == "SECTION":
        decision = grounding.resolve_section(
            hint,
            current_entry=current_entry,
            evidence_excerpt=evidence_excerpt,
            source_span=source_span,
        )
        endpoint = _ResolvedEndpoint(
            decision.node_id,
            label,
            hint,
            decision.reason,
            score=decision.score,
            second_score=decision.second_score,
            methods=decision.methods,
        )
    elif label == "DOCUMENT":
        endpoint = _ResolvedEndpoint(None, label, hint, UnresolvedRelationReason.MISSING_TARGET)
    elif default_chapter_id is not None:
        endpoint = _ResolvedEndpoint(default_chapter_id, "CHAPTER", hint)
    else:
        endpoint = _ResolvedEndpoint(None, label, hint, UnresolvedRelationReason.MISSING_TARGET)

    endpoint_cache[raw_id] = endpoint
    return endpoint


def _anchor_from_raw(
    entry: SourceManifestEntry,
    node: EntityNode,
    provenance: ExtractionProvenance,
) -> EntityNode:
    props = _clean_properties(node.properties or {})
    display_name = str(
        props.get("display_name") or props.get("name") or node.name or "anchor"
    )
    anchor_id = f"anchor:{entry.section_id}:{_slugify(display_name)}"
    return EntityNode(
        label="ANCHOR",
        name=anchor_id,
        properties={
            **props,
            **provenance.to_metadata(),
            "document_id": entry.document_id,
            "chapter_id": entry.chapter_id,
            "section_id": entry.section_id,
            "stable_section_uid": entry.stable_section_uid,
            "display_name": display_name,
            "description": str(props.get("description") or display_name),
            "evidence_excerpt": _evidence_excerpt(props) or display_name,
            "heading_path": entry.heading_path,
            "confidence": _confidence(props),
        },
    )


def _unresolved_entry(
    *,
    entry: SourceManifestEntry,
    source_id: str,
    relation_type: str,
    target_hint: str,
    reason: UnresolvedRelationReason,
    evidence_excerpt: str | None,
    provenance: ExtractionProvenance,
) -> UnresolvedRelationEntry:
    unresolved_id = unresolved_relation_id_for(
        source_id=source_id,
        relation_type=relation_type,
        target_hint=target_hint,
        source_section_id=entry.section_id,
        extract_run_id=provenance.extract_run_id,
    )
    return UnresolvedRelationEntry(
        unresolved_relation_id=unresolved_id,
        source_document_id=entry.document_id,
        source_chapter_id=entry.chapter_id,
        source_section_id=entry.section_id,
        source_chunk_id=provenance.source_chunk_id,
        source_hash=entry.source_hash,
        extract_run_id=provenance.extract_run_id,
        source_id=source_id,
        relation_type=relation_type,  # type: ignore[arg-type]
        target_hint=target_hint,
        reason=reason,
        evidence_excerpt=evidence_excerpt,
    )


def _section_level_stable_chunk_uid(entry: SourceManifestEntry) -> str | None:
    if not entry.stable_section_uid:
        return None
    return stable_chunk_uid_for(entry.stable_section_uid, "", 0)


def _display_name(node: EntityNode | None, fallback: str) -> str:
    if node is None:
        return fallback
    props = node.properties or {}
    return str(props.get("display_name") or props.get("name") or node.name or fallback)


def _evidence_excerpt(props: Mapping[str, Any]) -> str | None:
    value = props.get("evidence_excerpt") or props.get("excerpt") or props.get("evidence")
    return str(value) if value else None


def _source_span(props: Mapping[str, Any]) -> str | None:
    value = props.get("source_span") or props.get("span")
    return str(value) if value else None


def _confidence(props: Mapping[str, Any]) -> str:
    confidence = str(props.get("confidence", "medium")).strip().lower()
    return confidence if confidence in ALLOWED_CONFIDENCE else "medium"


def _grounding_properties(prefix: str, endpoint: _ResolvedEndpoint) -> dict[str, Any]:
    if not endpoint.methods:
        return {}
    return {
        f"{prefix}_grounding_score": endpoint.score,
        f"{prefix}_grounding_second_score": endpoint.second_score,
        f"{prefix}_grounding_methods": list(endpoint.methods),
    }


def _token_overlap_score(left: str, right: str) -> float:
    left_tokens = {token for token in re.split(r"[-_./#\s]+", left) if token}
    right_tokens = {token for token in re.split(r"[-_./#\s]+", right) if token}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def _embedding_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    a = left[:size]
    b = right[:size]
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _nearby_lines(left: int, right: int) -> bool:
    return abs(left - right) <= 20


def _contains_excerpt(text: str, excerpt: str) -> bool:
    normalized_text = " ".join(text.split()).casefold()
    normalized_excerpt = " ".join(excerpt.split()).casefold()
    return bool(normalized_excerpt and normalized_excerpt in normalized_text)


def _parse_line_span(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    numbers = [int(item) for item in re.findall(r"\d+", value)]
    if not numbers:
        return None
    start = numbers[0]
    end = numbers[1] if len(numbers) > 1 else start
    if start <= 0 or end < start:
        return None
    return start, end


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _clean_properties(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe(value) for key, value in value.items()}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _is_schema_llm_artifact(raw: Mapping[str, Any], keep_section_ids: set[str]) -> bool:
    props = raw.get("properties") or {}
    return (
        props.get("extractor_name") == SCHEMA_LLM_EXTRACTOR_NAME
        and props.get("source_section_id") in keep_section_ids
    )


def _dedupe_nodes(nodes: Sequence[EntityNode]) -> list[EntityNode]:
    by_id = {node.id: node for node in nodes}
    return list(by_id.values())


def _dedupe_relations(relations: Sequence[Relation]) -> list[Relation]:
    by_key: dict[tuple[str, str, str], Relation] = {}
    for relation in relations:
        by_key[(relation.source_id, relation.label, relation.target_id)] = relation
    return list(by_key.values())


def _normalize_hint(value: str) -> str:
    text = str(value).strip()
    for prefix in ("section:", "chapter:", "document:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return _slugify(text)


def _compact_hint(value: str) -> str:
    return "".join(char for char in value if char.isalnum())


def _slugify(text: str) -> str:
    normalized = "".join(
        char.lower() if char.isalnum() or char in "._-" else "-"
        for char in text.strip()
    ).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized or "section"
