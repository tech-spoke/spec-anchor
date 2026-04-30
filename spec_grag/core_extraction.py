"""Schema LLM extraction helpers for /spec-core."""

from __future__ import annotations

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
    ExtractionProvenance,
    make_schema_llm_path_extractor,
)
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


@dataclass(frozen=True)
class SchemaLLMExtractionResult:
    graph_store: SimplePropertyGraphStore
    unresolved_entries: list[UnresolvedRelationEntry] = field(default_factory=list)
    failed_section_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ResolvedEndpoint:
    node_id: str | None
    label: str
    hint: str
    reason: UnresolvedRelationReason | None = None


@dataclass(frozen=True)
class _NormalizationResult:
    nodes: list[EntityNode] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    unresolved_entries: list[UnresolvedRelationEntry] = field(default_factory=list)


class _GroundingIndex:
    def __init__(self, manifest: SourceManifest) -> None:
        self.chapter_hints: dict[str, set[str]] = defaultdict(set)
        self.section_hints: dict[str, set[str]] = defaultdict(set)
        for entry in manifest.entries:
            chapter_title = entry.heading_path.split(" / ")[0]
            self._add_chapter_hint(entry.chapter_id, entry.chapter_id)
            self._add_chapter_hint(chapter_title, entry.chapter_id)
            self._add_chapter_hint(_slugify(chapter_title), entry.chapter_id)

            section_title = entry.heading_path.split(" / ")[-1]
            self._add_section_hint(entry.section_id, entry.section_id)
            self._add_section_hint(section_node_id_for(entry.section_id), entry.section_id)
            self._add_section_hint(entry.heading_path, entry.section_id)
            self._add_section_hint(section_title, entry.section_id)
            self._add_section_hint(_slugify(section_title), entry.section_id)

    def resolve_chapter(self, hint: str) -> tuple[str | None, UnresolvedRelationReason | None]:
        return self._resolve(self.chapter_hints, hint)

    def resolve_section(self, hint: str) -> tuple[str | None, UnresolvedRelationReason | None]:
        section_id, reason = self._resolve(self.section_hints, hint)
        if section_id is None:
            return None, reason
        return section_node_id_for(section_id), None

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

    @staticmethod
    def _resolve(
        index: Mapping[str, set[str]], hint: str
    ) -> tuple[str | None, UnresolvedRelationReason | None]:
        normalized = _normalize_hint(hint)
        matches = index.get(normalized, set())
        if not matches:
            compact = _compact_hint(normalized)
            matches = index.get(compact, set()) if compact else set()
        if len(matches) == 1:
            return next(iter(matches)), None
        if len(matches) > 1:
            return None, UnresolvedRelationReason.AMBIGUOUS_TARGET
        return None, UnresolvedRelationReason.MISSING_TARGET


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


def make_schema_extractor_from_config(config: Mapping[str, Any]) -> SchemaExtractor:
    extraction_config = _mapping(config.get("extraction"))
    provider = str(extraction_config.get("provider", "codex")).strip().lower()
    if provider == "codex":
        llm = CodexCLIAdapter(
            command=str(extraction_config.get("command", "codex")),
            model=str(extraction_config.get("model", "gpt-5.4")),
            timeout_sec=int(extraction_config.get("timeout_sec", 120)),
        )
    elif provider == "claude":
        llm = ClaudeCLIAdapter(
            command=str(extraction_config.get("command", "claude")),
            model=str(extraction_config.get("model", "")),
            timeout_sec=int(extraction_config.get("timeout_sec", 120)),
        )
    else:
        raise ValueError(f"unsupported extraction.provider: {provider}")
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
) -> SchemaLLMExtractionResult:
    extractor = schema_extractor or make_schema_extractor_from_config(config)
    entries_by_id = manifest.by_section_id()
    grounding = _GroundingIndex(manifest)
    section_texts = read_section_texts(project_root, manifest)

    all_nodes: list[EntityNode] = []
    all_relations: list[Relation] = []
    unresolved_entries: list[UnresolvedRelationEntry] = []
    failed_section_ids: list[str] = []
    warnings: list[str] = []

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

        try:
            extracted_nodes = extractor([source_node], show_progress=False)
        except Exception as exc:
            failed_section_ids.append(section_id)
            warnings.append(f"schema_llm_extraction_failed:{section_id}:{exc}")
            continue

        for extracted_node in extracted_nodes:
            normalized = normalize_extracted_artifacts(
                entry=entry,
                extracted_nodes=extracted_node.metadata.get(KG_NODES_KEY, []),
                extracted_relations=extracted_node.metadata.get(KG_RELATIONS_KEY, []),
                provenance=provenance,
                grounding=grounding,
            )
            all_nodes.extend(normalized.nodes)
            all_relations.extend(normalized.relations)
            unresolved_entries.extend(normalized.unresolved_entries)

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
            default_chapter_id=entry.chapter_id,
        )
        target = _resolve_endpoint(
            relation.target_id,
            raw_nodes,
            anchor_nodes,
            grounding,
            endpoint_cache,
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


def read_section_texts(project_root: Path, manifest: SourceManifest) -> dict[str, str]:
    texts: dict[str, str] = {}
    by_document: dict[str, list[SourceManifestEntry]] = defaultdict(list)
    for entry in manifest.entries:
        by_document[entry.document_id].append(entry)

    for document_id, entries in by_document.items():
        path = Path(document_id)
        if not path.is_absolute():
            path = project_root / path
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
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

    if label == "CHAPTER":
        resolved, reason = grounding.resolve_chapter(hint)
        if resolved is None and default_chapter_id is not None:
            resolved = default_chapter_id
            reason = None
        endpoint = _ResolvedEndpoint(resolved, label, hint, reason)
    elif label == "SECTION":
        resolved, reason = grounding.resolve_section(hint)
        endpoint = _ResolvedEndpoint(resolved, label, hint, reason)
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


def _display_name(node: EntityNode | None, fallback: str) -> str:
    if node is None:
        return fallback
    props = node.properties or {}
    return str(props.get("display_name") or props.get("name") or node.name or fallback)


def _evidence_excerpt(props: Mapping[str, Any]) -> str | None:
    value = props.get("evidence_excerpt") or props.get("excerpt") or props.get("evidence")
    return str(value) if value else None


def _confidence(props: Mapping[str, Any]) -> str:
    confidence = str(props.get("confidence", "medium")).strip().lower()
    return confidence if confidence in ALLOWED_CONFIDENCE else "medium"


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
