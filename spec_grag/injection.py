"""InjectionContext construction for /spec-inject and /spec-realign."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llama_index.core.graph_stores import SimplePropertyGraphStore

from spec_grag.concept_index import (
    ConceptIndex,
    ConceptIndexChunk,
    concept_index_path,
    load_concept_index,
    stable_embedding,
)
from spec_grag.core import run_core_update
from spec_grag.manifest import SourceManifest, SourceManifestEntry, load_source_manifest
from spec_grag.protocol import (
    AgenticSearchCandidate,
    ConceptApprovalRequiredResult,
    ConstraintContext,
    ConversationContext,
    ErrorResult,
    ExpectedUse,
    FreshnessReport,
    InjectionContext,
    NeedMoreContextResult,
    ResultStatus,
    ResultType,
    SearchRequest,
    SearchTarget,
    SlashCommandRequest,
    TargetContext,
)
from spec_grag.sidecars import (
    ChapterAnchorArtifact,
    ClusterArtifact,
    ClusterSnapshot,
    UnresolvedRelationsSidecar,
    load_chapter_anchors,
    load_cluster_snapshot,
    load_unresolved_relations,
)


@dataclass(frozen=True)
class InjectionBuild:
    status: ResultStatus
    result_type: ResultType
    payload: (
        InjectionContext
        | NeedMoreContextResult
        | ErrorResult
        | ConceptApprovalRequiredResult
    )
    freshness_report: FreshnessReport
    warnings: list[str] = field(default_factory=list)
    context_ready: bool = False
    failed_sources: list[str] = field(default_factory=list)
    degraded_components: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphRetrievalResult:
    source_sections: list[SourceManifestEntry]
    related_entities: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    graph_data: dict[str, Any] = field(default_factory=dict)


def build_injection(
    project_root: Path,
    config: dict[str, Any],
    request: SlashCommandRequest,
) -> InjectionBuild:
    core_update = run_core_update(project_root, config, all_sources=False)
    if core_update.status == ResultStatus.FAILED:
        payload = ErrorResult(
            error_code="spec_core_failed",
            message="SPEC-grag core update failed before injection",
            details={
                "failed_sources": core_update.failed_sources,
                "warnings": core_update.warnings,
            },
        )
        return InjectionBuild(
            status=ResultStatus.FAILED,
            result_type=ResultType.ERROR_RESULT,
            payload=payload,
            freshness_report=core_update.freshness_report,
            warnings=core_update.warnings,
            failed_sources=core_update.failed_sources,
        )
    if core_update.concept_diff is not None:
        payload = ConceptApprovalRequiredResult(
            concept_diff=core_update.concept_diff,
            warnings=["pending_concept_diff_created"],
        )
        return InjectionBuild(
            status=ResultStatus.BLOCKED,
            result_type=ResultType.CONCEPT_APPROVAL_REQUIRED_RESULT,
            payload=payload,
            freshness_report=core_update.freshness_report,
            warnings=["pending_concept_diff_created"],
            context_ready=False,
        )

    graph_dir = Path(core_update.graph_storage)
    manifest = load_source_manifest(graph_dir / "source_manifest.json")
    query = central_query(request)
    expected_requests = expected_search_requests(request, manifest, query)
    valid_agentic, invalid_agentic = validate_agentic_candidates(
        request.agentic_search_candidates,
        expected_requests,
        manifest,
        project_root,
    )
    graph_retrieval = retrieve_graph_context(
        graph_dir,
        manifest,
        query,
        request.conversation_context,
        valid_agentic,
    )
    source_sections = graph_retrieval.source_sections
    purpose_item, purpose_warning = read_purpose_constraint(project_root, config)
    concept_items, concept_warning = read_concept_constraints(
        graph_dir,
        project_root,
        config,
        query,
    )
    chapter_anchors = retrieve_chapter_anchors(
        graph_dir,
        source_sections,
        valid_agentic,
    )
    chapter_anchor_items = [
        classify_context_item(
            chapter_anchor_item(anchor, source_origin=anchor.source_origin),
            item_type="chapter_anchor",
            query=query,
        )
        for anchor in chapter_anchors
    ]
    cluster_items = retrieve_cluster_items(
        graph_dir,
        source_sections=source_sections,
        concept_items=concept_items,
        related_entities=graph_retrieval.related_entities,
        query=query,
    )

    warnings = [
        *core_update.warnings,
        *graph_retrieval.warnings,
        *purpose_warning,
        *concept_warning,
    ]
    if invalid_agentic:
        warnings.append("some AgenticSearchCandidate entries were rejected")

    if (
        not source_sections
        and not valid_agentic
        and not concept_items
        and not purpose_item
        and not graph_retrieval.related_entities
        and not cluster_items
    ):
        need_more = NeedMoreContextResult(
            task_prompt=query,
            search_requests=expected_requests,
            current_partial_context_summary=summarize_conversation(
                request.conversation_context
            ),
        )
        return InjectionBuild(
            status=ResultStatus.BLOCKED,
            result_type=ResultType.NEED_MORE_CONTEXT_RESULT,
            payload=need_more,
            freshness_report=core_update.freshness_report,
            warnings=warnings,
            context_ready=False,
            degraded_components=["context_build"],
        )

    context = InjectionContext(
        conversation_context_summary=summarize_conversation(request.conversation_context),
        constraint_context=ConstraintContext(
            purpose_constraints=[
                classify_context_item(purpose_item, item_type="purpose", query=query)
            ]
            if purpose_item
            else [],
            concept_constraints=[
                item
                for item in concept_items
                if item.get("constraint_relevance") != "none"
            ],
            source_spec_constraints=[
                classify_context_item(
                    source_section_item(entry, source_origin="GRAG", relevance="medium"),
                    item_type="source_section",
                    query=query,
                )
                for entry in source_sections
            ],
            chapter_anchor_constraints=[
                item
                for item in chapter_anchor_items
                if item.get("constraint_relevance") != "none"
            ],
            classification_notes=classification_notes(
                purpose_item=purpose_item,
                concept_items=concept_items,
                source_sections=source_sections,
                chapter_anchor_items=chapter_anchor_items,
                related_entities=graph_retrieval.related_entities,
                cluster_items=cluster_items,
                source_origin="GRAG",
            ),
        ),
        target_context=TargetContext(
            candidate_targets=[
                classify_context_item(
                    agentic_candidate_item(candidate, expected_requests),
                    item_type="agentic_candidate",
                    query=query,
                )
                for candidate in valid_agentic
                if expected_use_for_candidate(candidate, expected_requests)
                in {ExpectedUse.TARGET, ExpectedUse.REVIEW}
            ],
            related_concepts=[
                item for item in concept_items if item.get("target_relevance") != "none"
            ],
            related_source_sections=[
                classify_context_item(
                    source_section_item(entry, source_origin="GRAG", relevance="high"),
                    item_type="source_section",
                    query=query,
                )
                for entry in source_sections
            ],
            related_chapter_anchors=[
                item
                for item in chapter_anchor_items
                if item.get("target_relevance") != "none"
            ],
            related_entities=[
                *graph_retrieval.related_entities,
                *cluster_items,
            ],
            classification_notes=target_classification_notes(
                source_sections=source_sections,
                concept_items=concept_items,
                chapter_anchor_items=chapter_anchor_items,
                related_entities=graph_retrieval.related_entities,
                cluster_items=cluster_items,
            ),
        ),
        excluded_as_irrelevant=excluded_irrelevant_items(
            [*concept_items, *graph_retrieval.related_entities, *cluster_items]
        ),
        conflict_notes=conflict_notes_for(
            source_sections,
            valid_agentic,
            graph_data=graph_retrieval.graph_data,
            classified_items=[
                *concept_items,
                *graph_retrieval.related_entities,
                *cluster_items,
                *chapter_anchor_items,
            ],
        ),
        review_notes=[
            *review_notes_for_invalid_agentic(invalid_agentic),
            *review_notes_for_unresolved(graph_dir),
            *review_notes_for_cluster_stale(graph_dir),
            *review_notes_for_graph_structure(graph_retrieval.graph_data),
            *review_notes_for_semantic_candidates(
                [
                    *concept_items,
                    *graph_retrieval.related_entities,
                    *cluster_items,
                    *chapter_anchor_items,
                ]
            ),
        ],
        freshness_report=core_update.freshness_report,
        approved_concept_update=None,
        warnings=warnings,
    )

    status = (
        ResultStatus.DEGRADED
        if warnings and core_update.status == ResultStatus.OK
        else core_update.status
    )
    return InjectionBuild(
        status=status,
        result_type=ResultType.INJECTION_CONTEXT,
        payload=context,
        freshness_report=core_update.freshness_report,
        warnings=warnings,
        context_ready=True,
        degraded_components=warnings and ["context_build"] or [],
    )


def central_query(request: SlashCommandRequest) -> str:
    return (
        request.task_prompt
        or request.conversation_context.current_user_message
        or request.conversation_context.working_target
        or ""
    )


def summarize_conversation(context: ConversationContext) -> str:
    parts = [context.current_user_message]
    if context.working_target:
        parts.append(f"working_target={context.working_target}")
    if context.explicit_files:
        parts.append("explicit_files=" + ",".join(context.explicit_files))
    return " | ".join(part for part in parts if part)


def expected_search_requests(
    request: SlashCommandRequest, manifest: SourceManifest, query: str
) -> list[SearchRequest]:
    target = SearchTarget(query=query or "related source specification")
    explicit_files = set(request.conversation_context.explicit_files)
    working_target = request.conversation_context.working_target
    for entry in manifest.entries:
        if entry.document_id in explicit_files or entry.document_id == working_target:
            target = SearchTarget(
                document_id=entry.document_id,
                chapter_id=entry.chapter_id,
                section_id=entry.section_id,
                query=query or None,
            )
            break

    return [
        SearchRequest(
            request_id=search_request_id(query, target, ExpectedUse.TARGET),
            reason="Round 1: need source-grounded target excerpt before building InjectionContext.",
            target=target,
            expected_use=ExpectedUse.TARGET,
        ),
        SearchRequest(
            request_id=search_request_id(query, target, ExpectedUse.CONSTRAINT),
            reason="Round 1: need constraint evidence that may limit the target change.",
            target=target,
            expected_use=ExpectedUse.CONSTRAINT,
        ),
        SearchRequest(
            request_id=search_request_id(query, target, ExpectedUse.REVIEW),
            reason="Round 2: provide review-only evidence if retrieved context is ambiguous.",
            target=target,
            expected_use=ExpectedUse.REVIEW,
        ),
    ]


def search_request_id(query: str, target: SearchTarget, expected_use: ExpectedUse) -> str:
    payload = target.model_dump(mode="json")
    payload["query_seed"] = query
    payload["expected_use"] = expected_use.value
    digest = hashlib.sha256(
        repr(sorted(payload.items())).encode("utf-8")
    ).hexdigest()[:12]
    return f"search:{digest}"


def validate_agentic_candidates(
    candidates: list[AgenticSearchCandidate],
    expected_requests: list[SearchRequest],
    manifest: SourceManifest,
    project_root: Path,
) -> tuple[list[AgenticSearchCandidate], list[dict[str, Any]]]:
    expected_by_id = {request.request_id: request for request in expected_requests}
    valid: list[AgenticSearchCandidate] = []
    invalid: list[dict[str, Any]] = []

    for candidate in candidates:
        reason = invalid_agentic_reason(candidate, expected_by_id, manifest, project_root)
        if reason:
            invalid.append(
                {
                    "request_id": candidate.request_id,
                    "source_document_id": candidate.source_document_id,
                    "source_section_id": candidate.source_section_id,
                    "source_span": candidate.source_span,
                    "reason": reason,
                    "review_required": True,
                    "source_origin": "AgenticSearch",
                }
            )
            continue
        valid.append(candidate)
    return valid, invalid


def invalid_agentic_reason(
    candidate: AgenticSearchCandidate,
    expected_by_id: dict[str, SearchRequest],
    manifest: SourceManifest,
    project_root: Path,
) -> str | None:
    manifest_by_section = manifest.by_section_id()
    if candidate.request_id not in expected_by_id:
        return "unknown_request_id"
    if not candidate.source_section_id:
        return "missing_source_section_id"
    entry = manifest_by_section.get(candidate.source_section_id)
    if entry is None:
        return "unknown_source_section_id"
    if candidate.source_document_id != entry.document_id:
        return "source_document_mismatch"
    if candidate.source_hash and candidate.source_hash != entry.source_hash:
        return "source_hash_mismatch"
    return candidate_source_grounding_error(candidate, entry, manifest, project_root)


@dataclass(frozen=True)
class _LineRange:
    start: int
    end: int


_SINGLE_LINE_CHAR_SPAN_RE = re.compile(
    r"^\[?\s*(?P<line>\d+)\s*:\s*\d+\s*-\s*\d+\s*\]?\s*$"
)
_LINE_RANGE_SPAN_RE = re.compile(
    r"(?:^|[^\d])(?:L|line(?:s)?\s*)?(?P<start>\d+)"
    r"\s*(?:-|–|~|:|\.\.)\s*(?:L|line\s*)?(?P<end>\d+)(?:[^\d]|$)",
    re.IGNORECASE,
)
_SINGLE_LINE_SPAN_RE = re.compile(
    r"^\s*(?:L|line\s*)?(?P<line>\d+)\s*$", re.IGNORECASE
)


def candidate_source_grounding_error(
    candidate: AgenticSearchCandidate,
    entry: SourceManifestEntry,
    manifest: SourceManifest,
    project_root: Path,
) -> str | None:
    document_lines = source_document_lines(project_root, entry)
    if document_lines is None:
        return "source_document_not_found"

    section_range = source_section_line_range(manifest, entry, len(document_lines))
    if section_range is None:
        return "source_section_line_range_invalid"

    if candidate.source_span:
        parsed_span = parse_source_span(candidate.source_span)
        if parsed_span is None:
            return "invalid_source_span_format"
        if parsed_span.start > parsed_span.end:
            return "invalid_source_span_range"
        if parsed_span.start < 1 or parsed_span.end > len(document_lines):
            return "source_span_out_of_file_range"
        if parsed_span.start < section_range.start or parsed_span.end > section_range.end:
            return "source_span_out_of_section_range"
        span_text = text_for_line_range(document_lines, parsed_span)
        if normalize_excerpt(candidate.excerpt) not in normalize_excerpt(span_text):
            return "excerpt_not_found_in_source_span"
        return None

    section_text = text_for_line_range(document_lines, section_range)
    occurrence_count = normalized_occurrence_count(candidate.excerpt, section_text)
    if occurrence_count == 0:
        return "excerpt_not_found_in_source_section"
    if occurrence_count > 1:
        return "ambiguous_excerpt_in_source_section"
    return None


def retrieve_source_sections(
    manifest: SourceManifest, query: str, context: ConversationContext
) -> list[SourceManifestEntry]:
    explicit_files = set(context.explicit_files)
    working_target = context.working_target
    tokens = query_tokens(query)
    matched = []
    for entry in manifest.entries:
        haystack = " ".join(
            [entry.document_id, entry.chapter_id, entry.section_id, entry.heading_path]
        ).lower()
        if entry.document_id in explicit_files or entry.document_id == working_target:
            matched.append(entry)
            continue
        if tokens and any(token in haystack for token in tokens):
            matched.append(entry)
    return sorted(matched, key=lambda entry: (entry.document_id, entry.heading_start_line))


def retrieve_graph_context(
    graph_dir: Path,
    manifest: SourceManifest,
    query: str,
    context: ConversationContext,
    valid_agentic: list[AgenticSearchCandidate],
) -> GraphRetrievalResult:
    graph_data, warnings = load_graph_data(graph_dir)
    source_sections = retrieve_source_sections(manifest, query, context)
    selected_section_ids = {entry.section_id for entry in source_sections}
    selected_section_ids.update(
        candidate.source_section_id
        for candidate in valid_agentic
        if candidate.source_section_id
    )

    graph_matches = graph_node_matches(
        graph_data,
        query=query,
        context=context,
        selected_section_ids=selected_section_ids,
    )
    selected_section_ids.update(
        item.get("source_section_id")
        for item in graph_matches
        if item.get("source_section_id")
    )
    graph_matches = merge_graph_traversal_matches(
        graph_data,
        graph_matches,
        selected_section_ids=selected_section_ids,
    )
    selected_section_ids.update(
        item.get("source_section_id")
        for item in graph_matches
        if item.get("source_section_id")
    )

    manifest_by_section = manifest.by_section_id()
    merged_sections = {
        entry.section_id: entry
        for entry in source_sections
    }
    for section_id in selected_section_ids:
        if section_id in manifest_by_section:
            merged_sections[section_id] = manifest_by_section[section_id]

    related_entities = [
        classify_context_item(item, item_type="graph_entity", query=query)
        for item in dedupe_items(graph_matches, key="entity_id")
    ]
    return GraphRetrievalResult(
        source_sections=sorted(
            merged_sections.values(),
            key=lambda entry: (entry.document_id, entry.heading_start_line, entry.section_id),
        ),
        related_entities=related_entities,
        warnings=warnings,
        graph_data=graph_data,
    )


def load_graph_data(graph_dir: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        store = SimplePropertyGraphStore.from_persist_dir(str(graph_dir))
    except FileNotFoundError:
        return {"nodes": {}, "relations": {}}, ["graph_store_missing"]
    except Exception as exc:
        return {"nodes": {}, "relations": {}}, [f"graph_store_load_failed:{exc}"]
    return store.graph.model_dump(), []


def graph_node_matches(
    graph_data: dict[str, Any],
    *,
    query: str,
    context: ConversationContext,
    selected_section_ids: set[str],
) -> list[dict[str, Any]]:
    tokens = query_tokens(query)
    explicit_files = set(context.explicit_files)
    working_target = context.working_target
    results: list[dict[str, Any]] = []
    for node_id, node in (graph_data.get("nodes") or {}).items():
        label = node_label(node)
        if label not in {"SECTION", "ANCHOR"}:
            continue
        props = node_properties(node)
        section_id = str(props.get("section_id") or props.get("source_section_id") or "")
        document_id = str(props.get("document_id") or props.get("source_document_id") or "")
        haystack = graph_node_haystack(node_id, node)
        methods: set[str] = set()
        keyword_score = token_match_score(tokens, haystack)
        if keyword_score:
            methods.add("keyword")
        if section_id in selected_section_ids:
            methods.add("manifest_seed")
        if document_id in explicit_files or document_id == working_target:
            methods.add("explicit_target")
        if not methods:
            continue
        vector_score = embedding_similarity(
            stable_embedding(query or node_id),
            node.get("embedding") or stable_embedding(haystack),
        )
        score = keyword_score + (1.0 if "explicit_target" in methods else 0.0) + vector_score
        results.append(
            graph_entity_item(
                node_id,
                node,
                retrieval_methods=sorted(methods | {"vector_similarity"}),
                ranking_score=score,
            )
        )
    return results


def merge_graph_traversal_matches(
    graph_data: dict[str, Any],
    graph_matches: list[dict[str, Any]],
    *,
    selected_section_ids: set[str],
) -> list[dict[str, Any]]:
    nodes = graph_data.get("nodes") or {}
    relations = graph_data.get("relations") or {}
    matched_node_ids = {item["entity_id"] for item in graph_matches}
    merged = {item["entity_id"]: dict(item) for item in graph_matches}

    for relation in relations.values():
        props = node_properties(relation)
        relation_section_id = props.get("section_id") or props.get("source_section_id")
        endpoints = [str(relation.get("source_id") or ""), str(relation.get("target_id") or "")]
        if not (
            relation_section_id in selected_section_ids
            or any(endpoint in matched_node_ids for endpoint in endpoints)
        ):
            continue
        for endpoint in endpoints:
            node = nodes.get(endpoint)
            if not node or node_label(node) not in {"SECTION", "ANCHOR"}:
                continue
            existing = merged.get(endpoint)
            if existing is None:
                merged[endpoint] = graph_entity_item(
                    endpoint,
                    node,
                    retrieval_methods=["graph_traversal"],
                    ranking_score=0.5,
                    relation_type=relation.get("label"),
                )
            else:
                methods = set(existing.get("retrieval_methods") or [])
                methods.add("graph_traversal")
                existing["retrieval_methods"] = sorted(methods)
                existing.setdefault("relation_types", [])
                if relation.get("label") not in existing["relation_types"]:
                    existing["relation_types"].append(relation.get("label"))

    return sorted(
        merged.values(),
        key=lambda item: (-float(item.get("ranking_score") or 0), item.get("entity_id") or ""),
    )


def retrieve_chapter_anchors(
    graph_dir: Path,
    source_sections: list[SourceManifestEntry],
    valid_agentic: list[AgenticSearchCandidate],
) -> list[ChapterAnchorArtifact]:
    chapter_ids = {entry.chapter_id for entry in source_sections}
    section_ids = {
        candidate.source_section_id
        for candidate in valid_agentic
        if candidate.source_section_id
    }
    anchors = load_chapter_anchors(graph_dir / "chapter_anchors.json")
    selected = []
    for anchor in anchors.anchors:
        if anchor.chapter_id in chapter_ids or section_ids.intersection(anchor.source_section_ids):
            selected.append(anchor)
    return selected


def retrieve_cluster_items(
    graph_dir: Path,
    *,
    source_sections: list[SourceManifestEntry],
    concept_items: list[dict[str, Any]],
    related_entities: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    snapshot = load_cluster_snapshot(graph_dir / "cluster_snapshot.json")
    selected_chapter_ids = {entry.chapter_id for entry in source_sections}
    selected_section_ids = {entry.section_id for entry in source_sections}
    selected_anchor_ids = {
        str(item.get("entity_id"))
        for item in related_entities
        if item.get("entity_type") == "ANCHOR"
    }
    selected_concept_chunk_ids = {
        str(item.get("concept_chunk_id")) for item in concept_items if item.get("concept_chunk_id")
    }
    items = []
    for cluster in snapshot.clusters:
        if not cluster_matches(
            cluster,
            chapter_ids=selected_chapter_ids,
            section_ids=selected_section_ids,
            anchor_ids=selected_anchor_ids,
            concept_chunk_ids=selected_concept_chunk_ids,
            query=query,
        ):
            continue
        items.append(
            classify_context_item(
                cluster_item(cluster),
                item_type="cluster",
                query=query,
            )
        )
    return items


def cluster_matches(
    cluster: ClusterArtifact,
    *,
    chapter_ids: set[str],
    section_ids: set[str],
    anchor_ids: set[str],
    concept_chunk_ids: set[str],
    query: str,
) -> bool:
    if set(cluster.member_chapter_ids).intersection(chapter_ids):
        return True
    if set(cluster.source_section_ids).intersection(section_ids):
        return True
    if set(cluster.member_anchor_ids).intersection(anchor_ids):
        return True
    if set(cluster.member_concept_chunk_ids).intersection(concept_chunk_ids):
        return True
    haystack = " ".join(
        [
            cluster.cluster_id,
            *cluster.seed_ids,
            *cluster.member_chapter_ids,
            *cluster.member_anchor_ids,
            *cluster.member_concept_chunk_ids,
            *cluster.dominant_relation_types,
        ]
    ).lower()
    return bool(token_match_score(query_tokens(query), haystack))


def cluster_item(cluster: ClusterArtifact) -> dict[str, Any]:
    return {
        "entity_id": cluster.cluster_id,
        "entity_type": "CLUSTER",
        "cluster_id": cluster.cluster_id,
        "cluster_level": cluster.level,
        "seed_ids": cluster.seed_ids,
        "member_chapter_ids": cluster.member_chapter_ids,
        "member_anchor_ids": cluster.member_anchor_ids,
        "member_concept_chunk_ids": cluster.member_concept_chunk_ids,
        "dominant_relation_types": cluster.dominant_relation_types,
        "source_section_ids": cluster.source_section_ids,
        "source_origin": "cluster_snapshot",
        "confidence": cluster.confidence,
        "stale": cluster.stale,
        "review_required": cluster.stale,
        "ranking_score": 0.25,
    }


def read_purpose_constraint(
    project_root: Path, config: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    path = configured_path(project_root, config, "core", "purpose_file")
    if path is None or not path.exists():
        return None, ["purpose_file_missing"]
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None, ["purpose_file_empty"]
    return (
        {
            "source_origin": "Purpose",
            "file": str(path),
            "constraint_relevance": "high",
            "summary": first_nonempty_line(text),
        },
        [],
    )


def read_concept_constraints(
    graph_dir: Path,
    project_root: Path,
    config: dict[str, Any],
    query: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    path = configured_path(project_root, config, "core", "concept_file")
    if path is None or not path.exists():
        return [], ["concept_file_missing"]
    index = load_concept_index(concept_index_path(graph_dir))
    if index is None:
        return [], ["concept_index_missing"]
    if index.concept_file_hash != _file_sha256(path):
        return [], ["concept_index_stale"]
    chunks = retrieve_concept_chunks(index, query, limit=5)
    return [
        classify_context_item(
            concept_chunk_item(project_root, path, chunk, score=score),
            item_type="concept",
            query=query,
        )
        for chunk, score in chunks
    ], []


def source_section_item(
    entry: SourceManifestEntry, *, source_origin: str, relevance: str
) -> dict[str, Any]:
    return {
        "source_origin": source_origin,
        "document_id": entry.document_id,
        "chapter_id": entry.chapter_id,
        "section_id": entry.section_id,
        "heading_path": entry.heading_path,
        "source_hash": entry.source_hash,
        "constraint_relevance": relevance,
        "target_relevance": relevance,
        "review_required": False,
    }


def concept_chunk_item(
    project_root: Path,
    concept_file: Path,
    chunk: ConceptIndexChunk,
    *,
    score: float,
) -> dict[str, Any]:
    return {
        "source_origin": "CoreConceptIndex",
        "file": relative_path(project_root, concept_file),
        "concept_chunk_id": chunk.concept_chunk_id,
        "heading_path": chunk.heading_path,
        "paragraph_index": chunk.paragraph_index,
        "text_hash": chunk.text_hash,
        "summary": first_nonempty_line(chunk.text),
        "excerpt": chunk.text,
        "ranking_score": round(score, 6),
    }


def retrieve_concept_chunks(
    index: ConceptIndex,
    query: str,
    *,
    limit: int,
) -> list[tuple[ConceptIndexChunk, float]]:
    tokens = query_tokens(query)
    if not index.chunks:
        return []
    scored: list[tuple[ConceptIndexChunk, float]] = []
    query_embedding = stable_embedding(query)
    for chunk in index.chunks:
        haystack = f"{chunk.heading_path} {chunk.text}".lower()
        keyword_score = token_match_score(tokens, haystack)
        if not keyword_score and tokens:
            continue
        score = keyword_score + embedding_similarity(query_embedding, chunk.embedding)
        scored.append((chunk, score))
    if not scored and not tokens:
        scored = [(chunk, 0.0) for chunk in index.chunks[:limit]]
    return sorted(scored, key=lambda item: (-item[1], item[0].concept_chunk_id))[:limit]


def chapter_anchor_item(anchor: ChapterAnchorArtifact, *, source_origin: str) -> dict[str, Any]:
    return {
        "chapter_anchor_id": anchor.chapter_anchor_id,
        "document_id": anchor.document_id,
        "chapter_id": anchor.chapter_id,
        "source_section_ids": anchor.source_section_ids,
        "summary": anchor.summary,
        "key_terms": anchor.key_terms,
        "source_origin": source_origin,
        "constraint_relevance": "medium",
        "target_relevance": "medium",
        "review_required": anchor.quality.stale,
    }


def graph_entity_item(
    entity_id: str,
    node: dict[str, Any],
    *,
    retrieval_methods: list[str],
    ranking_score: float,
    relation_type: str | None = None,
) -> dict[str, Any]:
    props = node_properties(node)
    relation_types = [relation_type] if relation_type else []
    return {
        "entity_id": entity_id,
        "entity_type": node_label(node),
        "heading_path": props.get("heading_path"),
        "document_id": props.get("document_id") or props.get("source_document_id"),
        "chapter_id": props.get("chapter_id") or props.get("source_chapter_id"),
        "section_id": props.get("section_id"),
        "source_section_id": props.get("source_section_id") or props.get("section_id"),
        "source_hash": props.get("source_hash"),
        "description": props.get("description"),
        "evidence_excerpt": props.get("evidence_excerpt"),
        "retrieval_methods": retrieval_methods,
        "relation_types": relation_types,
        "source_origin": "GRAG",
        "ranking_score": round(ranking_score, 6),
    }


def agentic_candidate_item(
    candidate: AgenticSearchCandidate, expected_requests: list[SearchRequest]
) -> dict[str, Any]:
    expected_use = expected_use_for_candidate(candidate, expected_requests)
    return {
        "source_origin": "AgenticSearch",
        "request_id": candidate.request_id,
        "source_document_id": candidate.source_document_id,
        "source_section_id": candidate.source_section_id,
        "heading_path": candidate.heading_path,
        "excerpt": candidate.excerpt,
        "source_span": candidate.source_span,
        "reason": candidate.reason,
        "expected_use": expected_use.value if expected_use else None,
        "review_required": expected_use == ExpectedUse.REVIEW,
    }


def expected_use_for_candidate(
    candidate: AgenticSearchCandidate, expected_requests: list[SearchRequest]
) -> ExpectedUse | None:
    for request in expected_requests:
        if request.request_id == candidate.request_id:
            return request.expected_use
    return None


def classification_notes(
    *,
    purpose_item: dict[str, Any] | None,
    concept_items: list[dict[str, Any]],
    source_sections: list[SourceManifestEntry],
    chapter_anchor_items: list[dict[str, Any]],
    related_entities: list[dict[str, Any]],
    cluster_items: list[dict[str, Any]],
    source_origin: str,
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    if purpose_item:
        notes.append(
            {
                "source_origin": "Purpose",
                "reason": "Purpose is always an upper constraint.",
                "constraint_relevance": "high",
            }
        )
    if concept_items:
        notes.append(
            {
                "source_origin": "CoreConceptIndex",
                "reason": "Approved Concept index chunks matched the current task query.",
                "concept_chunk_ids": [
                    item["concept_chunk_id"]
                    for item in concept_items
                    if item.get("concept_chunk_id")
                ],
                "constraint_relevance": "medium",
            }
        )
    if source_sections:
        notes.append(
            {
                "source_origin": source_origin,
                "reason": "Source sections matched the current task query or explicit files.",
                "section_ids": [entry.section_id for entry in source_sections],
                "constraint_relevance": "medium",
            }
        )
    if chapter_anchor_items:
        notes.append(
            {
                "source_origin": source_origin,
                "reason": "ChapterAnchor artifacts matched selected source sections.",
                "chapter_anchor_ids": [
                    item["chapter_anchor_id"]
                    for item in chapter_anchor_items
                    if item.get("chapter_anchor_id")
                ],
                "constraint_relevance": "medium",
            }
        )
    if related_entities:
        notes.append(
            {
                "source_origin": "GRAG",
                "reason": "Graph/vector retrieval candidates were annotated with 4-axis metadata.",
                "entity_ids": [
                    item["entity_id"] for item in related_entities if item.get("entity_id")
                ],
                "constraint_relevance": "low",
            }
        )
    if cluster_items:
        notes.append(
            {
                "source_origin": "cluster_snapshot",
                "reason": "Hierarchical cluster sidecar matched retrieved chapters, anchors, or concepts.",
                "cluster_ids": [
                    item["cluster_id"] for item in cluster_items if item.get("cluster_id")
                ],
                "constraint_relevance": "low",
            }
        )
    return notes


def target_classification_notes(
    *,
    source_sections: list[SourceManifestEntry],
    concept_items: list[dict[str, Any]],
    chapter_anchor_items: list[dict[str, Any]],
    related_entities: list[dict[str, Any]],
    cluster_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    if source_sections:
        notes.append(
            {
                "source_origin": "GRAG",
                "reason": "Matched current task query or explicit working target.",
                "section_ids": [entry.section_id for entry in source_sections],
                "target_relevance": "medium",
            }
        )
    if concept_items:
        notes.append(
            {
                "source_origin": "CoreConceptIndex",
                "reason": "Concept chunks are relevant to the target when the task asks for a change or review.",
                "concept_chunk_ids": [
                    item["concept_chunk_id"]
                    for item in concept_items
                    if item.get("concept_chunk_id")
                ],
                "target_relevance": "medium",
            }
        )
    if chapter_anchor_items:
        notes.append(
            {
                "source_origin": "GRAG",
                "reason": "ChapterAnchor artifacts describe target-adjacent chapters.",
                "chapter_anchor_ids": [
                    item["chapter_anchor_id"]
                    for item in chapter_anchor_items
                    if item.get("chapter_anchor_id")
                ],
                "target_relevance": "medium",
            }
        )
    if related_entities or cluster_items:
        notes.append(
            {
                "source_origin": "GRAG",
                "reason": "Graph/vector/cluster candidates were merged into TargetContext.related_entities.",
                "entity_ids": [
                    item["entity_id"]
                    for item in [*related_entities, *cluster_items]
                    if item.get("entity_id")
                ],
                "target_relevance": "medium",
            }
        )
    return notes


def conflict_notes_for(
    source_sections: list[SourceManifestEntry],
    valid_agentic: list[AgenticSearchCandidate],
    *,
    graph_data: dict[str, Any] | None = None,
    classified_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    combined = " ".join(
        [
            *(entry.heading_path.lower() for entry in source_sections),
            *(candidate.excerpt.lower() for candidate in valid_agentic),
            *(
                item_text(item).lower()
                for item in (classified_items or [])
            ),
        ]
    )
    if has_required_optional_conflict(combined):
        notes.append(
            {
                "conflict": True,
                "validator_stage": "rule_based",
                "reason": "Required and optional language appeared in selected evidence.",
                "source_origin": "Validator",
            }
        )
    if has_japanese_quantifier_conflict(combined):
        notes.append(
            {
                "conflict": True,
                "validator_stage": "rule_based",
                "reason": "Japanese opposing quantifiers appeared in selected evidence.",
                "source_origin": "Validator",
            }
        )
    notes.extend(refines_cycle_conflicts(graph_data or {}))
    return notes


def has_required_optional_conflict(text: str) -> bool:
    lowered = text.lower()
    return "required" in lowered and "optional" in lowered


def has_japanese_quantifier_conflict(text: str) -> bool:
    return ("必ず" in text and "任意" in text) or ("全て" in text and "一部" in text)


def refines_cycle_conflicts(graph_data: dict[str, Any]) -> list[dict[str, Any]]:
    relations = graph_data.get("relations") or {}
    edges: dict[str, set[str]] = {}
    for relation in relations.values():
        if relation.get("label") != "REFINES":
            continue
        source = str(relation.get("source_id") or "")
        target = str(relation.get("target_id") or "")
        if source and target:
            edges.setdefault(source, set()).add(target)

    conflicts: list[dict[str, Any]] = []
    visited: set[str] = set()
    visiting: list[str] = []

    def visit(node: str) -> None:
        if node in visiting:
            cycle = visiting[visiting.index(node) :] + [node]
            conflicts.append(
                {
                    "conflict": True,
                    "validator_stage": "graph_structure",
                    "reason": "REFINES relation cycle detected.",
                    "cycle": cycle,
                    "source_origin": "Validator",
                }
            )
            return
        if node in visited:
            return
        visiting.append(node)
        for target in sorted(edges.get(node, set())):
            visit(target)
        visiting.pop()
        visited.add(node)

    for node in sorted(edges):
        visit(node)
    return conflicts


def review_notes_for_invalid_agentic(invalid: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return invalid


def review_notes_for_unresolved(graph_dir: Path) -> list[dict[str, Any]]:
    sidecar: UnresolvedRelationsSidecar = load_unresolved_relations(
        graph_dir / "unresolved_relations.json"
    )
    return [
        {
            "source_origin": "unresolved_relations",
            "unresolved_relation_id": entry.unresolved_relation_id,
            "source_section_id": entry.source_section_id,
            "target_hint": entry.target_hint,
            "reason": entry.reason,
            "review_required": True,
        }
        for entry in sidecar.entries
    ]


def review_notes_for_cluster_stale(graph_dir: Path) -> list[dict[str, Any]]:
    snapshot = load_cluster_snapshot(graph_dir / "cluster_snapshot.json")
    return [
        {
            "source_origin": "cluster_snapshot",
            "cluster_id": cluster.cluster_id,
            "reason": "cluster_snapshot_stale",
            "review_required": True,
        }
        for cluster in snapshot.clusters
        if cluster.stale
    ]


def review_notes_for_graph_structure(graph_data: dict[str, Any]) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    mentions_by_anchor: dict[str, set[str]] = {}
    for relation in (graph_data.get("relations") or {}).values():
        if relation.get("label") != "MENTIONS":
            continue
        props = node_properties(relation)
        source_section_id = props.get("source_section_id")
        target_id = relation.get("target_id")
        if source_section_id and target_id:
            mentions_by_anchor.setdefault(str(target_id), set()).add(str(source_section_id))
    for anchor_id, section_ids in sorted(mentions_by_anchor.items()):
        if len(section_ids) <= 1:
            continue
        notes.append(
            {
                "source_origin": "Validator",
                "validator_stage": "graph_structure",
                "reason": "same_anchor_mentioned_by_multiple_sections",
                "anchor_id": anchor_id,
                "source_section_ids": sorted(section_ids),
                "review_required": True,
            }
        )
    return notes


def review_notes_for_semantic_candidates(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "source_origin": item.get("source_origin", "Classification"),
            "reason": "semantic_conflict_candidate_requires_validator_or_human_approval",
            "item_id": item.get("entity_id")
            or item.get("concept_chunk_id")
            or item.get("chapter_anchor_id")
            or item.get("cluster_id"),
            "review_required": True,
        }
        for item in items
        if item.get("semantic_conflict_candidate") is True
        and item.get("conflict") is not True
    ]


def excluded_irrelevant_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    excluded = []
    for item in items:
        if (
            item.get("constraint_relevance") == "none"
            and item.get("target_relevance") == "none"
            and item.get("semantic_conflict_candidate") is not True
            and item.get("review_required") is not True
        ):
            excluded.append(item)
    return excluded


def configured_path(
    project_root: Path, config: dict[str, Any], section: str, key: str
) -> Path | None:
    configured = config.get(section, {}).get(key)
    if not configured:
        return None
    path = Path(configured)
    if not path.is_absolute():
        path = project_root / path
    return path


def candidate_excerpt_resolves(
    candidate: AgenticSearchCandidate,
    entry: SourceManifestEntry,
    manifest: SourceManifest,
    project_root: Path,
) -> bool:
    return candidate_source_grounding_error(candidate, entry, manifest, project_root) is None


def parse_source_span(value: str) -> _LineRange | None:
    text = value.strip()
    if not text:
        return None

    char_span = _SINGLE_LINE_CHAR_SPAN_RE.match(text)
    if char_span:
        line = int(char_span.group("line"))
        return _LineRange(line, line)

    range_span = _LINE_RANGE_SPAN_RE.search(text)
    if range_span:
        return _LineRange(int(range_span.group("start")), int(range_span.group("end")))

    single_line = _SINGLE_LINE_SPAN_RE.match(text)
    if single_line:
        line = int(single_line.group("line"))
        return _LineRange(line, line)

    return None


def source_document_lines(
    project_root: Path,
    entry: SourceManifestEntry,
) -> list[str] | None:
    path = Path(entry.document_id)
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").splitlines()


def source_section_line_range(
    manifest: SourceManifest,
    entry: SourceManifestEntry,
    total_line_count: int,
) -> _LineRange | None:
    if entry.heading_start_line < 1 or entry.heading_start_line > total_line_count:
        return None
    entries_for_doc = sorted(
        (
            candidate
            for candidate in manifest.entries
            if candidate.document_id == entry.document_id
        ),
        key=lambda candidate: (candidate.heading_start_line, candidate.section_id),
    )
    next_start = total_line_count + 1
    for candidate in entries_for_doc:
        if candidate.heading_start_line > entry.heading_start_line:
            next_start = candidate.heading_start_line
            break
    return _LineRange(entry.heading_start_line, next_start - 1)


def source_section_text(
    project_root: Path,
    manifest: SourceManifest,
    entry: SourceManifestEntry,
) -> str:
    lines = source_document_lines(project_root, entry)
    if lines is None:
        return ""
    line_range = source_section_line_range(manifest, entry, len(lines))
    if line_range is None:
        return ""
    return text_for_line_range(lines, line_range)


def text_for_line_range(lines: list[str], line_range: _LineRange) -> str:
    return "\n".join(lines[line_range.start - 1 : line_range.end])


def normalized_occurrence_count(needle: str, haystack: str) -> int:
    normalized_needle = normalize_excerpt(needle)
    normalized_haystack = normalize_excerpt(haystack)
    if not normalized_needle:
        return 0
    return normalized_haystack.count(normalized_needle)


def normalize_excerpt(text: str) -> str:
    return " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())


def classify_context_item(
    item: dict[str, Any],
    *,
    item_type: str,
    query: str,
) -> dict[str, Any]:
    annotated = dict(item)
    existing_review = bool(annotated.get("review_required"))
    text = item_text(annotated)
    tokens = query_tokens(query)
    token_score = token_match_score(tokens, text.lower())
    target_intent = is_target_query(query)

    if item_type == "purpose":
        constraint = "high"
        target = "none"
    elif item_type == "agentic_candidate":
        expected_use = annotated.get("expected_use")
        constraint = "high" if expected_use == ExpectedUse.CONSTRAINT.value else "none"
        target = "high" if expected_use in {ExpectedUse.TARGET.value, ExpectedUse.REVIEW.value} else "none"
    elif item_type == "concept":
        constraint = "high" if token_score else "medium"
        target = "medium" if target_intent and (token_score or annotated.get("ranking_score")) else "none"
    elif item_type == "source_section":
        constraint = "medium" if token_score or annotated.get("constraint_relevance") else "low"
        target = "high" if target_intent else "medium"
    elif item_type == "chapter_anchor":
        constraint = "medium" if token_score else "low"
        target = "medium" if target_intent or token_score else "low"
    elif item_type == "graph_entity":
        constraint = "medium" if token_score else "low"
        target = "medium" if target_intent or token_score else "low"
    elif item_type == "cluster":
        constraint = "low"
        target = "medium" if target_intent or token_score else "low"
    else:
        constraint = "none"
        target = "none"

    semantic_conflict_candidate = (
        annotated.get("semantic_conflict_candidate") is True
        or has_required_optional_conflict(text)
        or has_japanese_quantifier_conflict(text)
        or "contradict" in text.lower()
        or "conflict" in text.lower()
        or "矛盾" in text
    )
    annotated.update(
        {
            "constraint_relevance": annotated.get("constraint_relevance", constraint),
            "target_relevance": annotated.get("target_relevance", target),
            "semantic_conflict_candidate": semantic_conflict_candidate,
            "review_required": existing_review or semantic_conflict_candidate,
            "classification_source": "orchestrator_rule_based",
            "reason_for_current_task": classification_reason(
                item_type,
                constraint=annotated.get("constraint_relevance", constraint),
                target=annotated.get("target_relevance", target),
                token_score=token_score,
            ),
        }
    )
    annotated.setdefault("ranking_score", round(float(token_score), 6))
    return annotated


def classification_reason(
    item_type: str,
    *,
    constraint: str,
    target: str,
    token_score: float,
) -> str:
    return (
        f"{item_type} classified with constraint={constraint}, "
        f"target={target}, token_score={token_score:.3f}."
    )


def item_text(item: dict[str, Any]) -> str:
    parts = []
    for key in (
        "summary",
        "excerpt",
        "heading_path",
        "description",
        "evidence_excerpt",
        "reason",
        "cluster_id",
    ):
        value = item.get(key)
        if value:
            parts.append(str(value))
    for key in ("key_terms", "member_chapter_ids", "member_anchor_ids", "dominant_relation_types"):
        value = item.get(key)
        if isinstance(value, list):
            parts.extend(str(part) for part in value)
    return " ".join(parts)


def node_label(node: dict[str, Any]) -> str:
    return str(node.get("label") or "")


def node_properties(node: dict[str, Any]) -> dict[str, Any]:
    return dict(node.get("properties") or {})


def graph_node_haystack(node_id: str, node: dict[str, Any]) -> str:
    props = node_properties(node)
    values = [
        node_id,
        node_label(node),
        node.get("name"),
        *[props.get(key) for key in (
            "document_id",
            "chapter_id",
            "section_id",
            "source_section_id",
            "heading_path",
            "description",
            "evidence_excerpt",
        )],
    ]
    return " ".join(str(value) for value in values if value).lower()


def token_match_score(tokens: list[str], haystack: str) -> float:
    if not tokens:
        return 0.0
    normalized = haystack.lower()
    hits = sum(1 for token in tokens if token and token in normalized)
    return hits / len(tokens)


def embedding_similarity(left: list[float], right: list[float]) -> float:
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


def dedupe_items(items: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        item_key = str(item.get(key) or "")
        if not item_key:
            continue
        existing = by_key.get(item_key)
        if existing is None or float(item.get("ranking_score") or 0) > float(
            existing.get("ranking_score") or 0
        ):
            by_key[item_key] = item
            continue
        methods = set(existing.get("retrieval_methods") or [])
        methods.update(item.get("retrieval_methods") or [])
        existing["retrieval_methods"] = sorted(methods)
    return sorted(
        by_key.values(),
        key=lambda item: (-float(item.get("ranking_score") or 0), item.get(key) or ""),
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def query_tokens(query: str) -> list[str]:
    return [
        token.lower()
        for token in query.replace("　", " ").replace("/", " ").split()
        if token.strip()
    ]


def is_target_query(query: str) -> bool:
    lowered = query.lower()
    return any(token in lowered for token in ("見直", "修正", "変更", "target", "update"))
