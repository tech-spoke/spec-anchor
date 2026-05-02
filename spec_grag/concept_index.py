"""Core Concept index and Concept diff candidate generation."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llama_index.core.graph_stores import SimplePropertyGraphStore
from pydantic import Field, ValidationError

from spec_grag.concept_diff import (
    ConceptDiffTaskContext,
    PendingConceptDiff,
    PendingConceptHunk,
    concept_file_hash,
    create_pending_concept_diff,
    first_unresolved_pending_concept_diff,
)
from spec_grag.embedding import (
    EmbeddingMetadata,
    default_embedding_metadata,
    embedding_for_text,
    embedding_identity_matches,
    embedding_metadata_from_config,
    stable_embedding as make_stable_embedding,
)
from spec_grag.io import write_model_atomic as _write_model_atomic
from spec_grag.llm_adapters import CLIAdapterError
from spec_grag.llm_factory import make_stage_llm_from_config
from spec_grag.protocol import Command, StrictModel
from spec_grag.watch_state import (
    enqueue_source_changes,
    load_watch_queue,
    remove_watch_queue_changes,
    update_provisional_concept_cache,
    watch_queue_path,
)


CONCEPT_INDEX_VERSION = "2"
CONCEPT_INDEX_FILENAME = "concept_index.json"
SOURCE_DERIVED_HEADING = "Source-derived concepts"
LOGGER = logging.getLogger(__name__)


class ConceptIndexChunk(StrictModel):
    concept_chunk_id: str
    heading_path: str
    paragraph_index: int
    text_hash: str
    text: str
    embedding: list[float] = Field(default_factory=list)


class ConceptIndex(StrictModel):
    version: str = CONCEPT_INDEX_VERSION
    concept_file: str
    concept_file_hash: str
    embedding_metadata: EmbeddingMetadata = Field(default_factory=default_embedding_metadata)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    chunks: list[ConceptIndexChunk] = Field(default_factory=list)

    def chunk_text(self) -> str:
        return "\n".join(chunk.text for chunk in self.chunks)


class ConceptDiffCandidateResult(StrictModel):
    pending_diff: PendingConceptDiff | None = None
    created_path: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ConceptDiffProposalItem(StrictModel):
    term: str
    source_section_id: str
    evidence_excerpt: str
    source_span: str
    proposed_text: str


class ConceptDiffProposal(StrictModel):
    items: list[ConceptDiffProposalItem]
    warnings: list[str]


class ConceptDiffProposalError(RuntimeError):
    """Raised when the configured Concept diff proposal provider cannot run."""


class _ConceptParagraph:
    def __init__(self, heading_path: str, paragraph_index: int, text: str) -> None:
        self.heading_path = heading_path
        self.paragraph_index = paragraph_index
        self.text = text


def concept_index_path(graph_storage: Path) -> Path:
    return graph_storage / CONCEPT_INDEX_FILENAME


def configured_concept_file(project_root: Path, config: Mapping[str, Any]) -> Path | None:
    core_config = config.get("core")
    if not isinstance(core_config, Mapping):
        return None
    configured = core_config.get("concept_file")
    if not configured:
        return None
    path = Path(str(configured))
    if not path.is_absolute():
        path = project_root / path
    return path


def load_concept_index(path: Path) -> ConceptIndex | None:
    if not path.exists():
        return None
    return ConceptIndex.model_validate_json(path.read_text(encoding="utf-8"))


def write_concept_index_atomic(path: Path, index: ConceptIndex) -> None:
    _write_model_atomic(path, index)


def refresh_concept_index(
    project_root: Path,
    config: Mapping[str, Any],
    graph_storage: Path,
    *,
    generated_at: str | None = None,
) -> tuple[ConceptIndex | None, list[str]]:
    concept_file = configured_concept_file(project_root, config)
    if concept_file is None or not concept_file.exists():
        return None, []

    path = concept_index_path(graph_storage)
    current_hash = concept_file_hash(concept_file)
    embedding_metadata = embedding_metadata_from_config(config, generated_at=generated_at)
    existing = load_concept_index(path)
    existing_has_embedding_metadata = _json_file_has_key(path, "embedding_metadata")
    existing_has_current_version = (
        _json_file_has_key(path, "version")
        and existing is not None
        and existing.version == CONCEPT_INDEX_VERSION
    )
    if (
        existing is not None
        and existing_has_current_version
        and existing_has_embedding_metadata
        and existing.concept_file_hash == current_hash
        and embedding_identity_matches(existing.embedding_metadata, embedding_metadata)
    ):
        return existing, []

    index = build_concept_index(
        project_root,
        concept_file,
        embedding_metadata=embedding_metadata,
        embedding_config=_mapping(config.get("embedding")),
        generated_at=generated_at,
        previous_index=existing
        if existing is not None
        and existing_has_current_version
        and existing_has_embedding_metadata
        and embedding_identity_matches(existing.embedding_metadata, embedding_metadata)
        else None,
    )
    write_concept_index_atomic(path, index)
    warnings = []
    if existing is not None and not existing_has_current_version:
        warnings.append("concept_index_version_mismatch_rebuilt")
    if existing is not None and (
        not existing_has_embedding_metadata
        or not embedding_identity_matches(existing.embedding_metadata, embedding_metadata)
    ):
        warnings.append("concept_index_embedding_metadata_mismatch_rebuilt")
    return index, warnings


def build_concept_index(
    project_root: Path,
    concept_file: Path,
    *,
    embedding_metadata: EmbeddingMetadata | None = None,
    embedding_config: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
    previous_index: ConceptIndex | None = None,
) -> ConceptIndex:
    text = concept_file.read_text(encoding="utf-8")
    rel_path = _relative_path(project_root, concept_file)
    metadata = embedding_metadata or default_embedding_metadata(generated_at=generated_at)
    reusable_embeddings = reusable_concept_embeddings(previous_index, metadata)
    chunks = [
        ConceptIndexChunk(
            concept_chunk_id=concept_chunk_id_for(
                rel_path,
                paragraph.heading_path,
                paragraph.paragraph_index,
                paragraph.text,
            ),
            heading_path=paragraph.heading_path,
            paragraph_index=paragraph.paragraph_index,
            text_hash=_sha256_text(paragraph.text),
            text=paragraph.text,
            embedding=embedding_for_concept_text(
                paragraph.text,
                metadata=metadata,
                reusable_embeddings=reusable_embeddings,
                embedding_config=embedding_config,
            ),
        )
        for paragraph in split_concept_paragraphs(text)
    ]
    return ConceptIndex(
        concept_file=rel_path,
        concept_file_hash=concept_file_hash(concept_file),
        embedding_metadata=metadata,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        chunks=chunks,
    )


def reusable_concept_embeddings(
    previous_index: ConceptIndex | None,
    metadata: EmbeddingMetadata,
) -> dict[str, list[float]]:
    if previous_index is None:
        return {}
    if not embedding_identity_matches(previous_index.embedding_metadata, metadata):
        return {}
    reusable: dict[str, list[float]] = {}
    for chunk in previous_index.chunks:
        if chunk.text_hash and chunk.embedding:
            reusable.setdefault(chunk.text_hash, chunk.embedding)
    return reusable


def embedding_for_concept_text(
    text: str,
    *,
    metadata: EmbeddingMetadata,
    reusable_embeddings: Mapping[str, list[float]],
    embedding_config: Mapping[str, Any] | None,
) -> list[float]:
    text_hash = _sha256_text(text)
    reusable = reusable_embeddings.get(text_hash)
    if reusable is not None:
        return list(reusable)
    return embedding_for_text(text, metadata, config=embedding_config)


def split_concept_paragraphs(text: str) -> list[_ConceptParagraph]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    heading_stack: list[tuple[int, str]] = []
    paragraphs: list[_ConceptParagraph] = []
    current: list[str] = []
    current_kind: str | None = None
    paragraph_index_by_heading: dict[str, int] = {}

    def current_heading_path() -> str:
        return " / ".join(title for _, title in heading_stack) or "root"

    def flush() -> None:
        nonlocal current_kind
        body = "\n".join(line for line in current).strip()
        current.clear()
        current_kind = None
        if not body:
            return
        heading_path = current_heading_path()
        paragraph_index = paragraph_index_by_heading.get(heading_path, 0)
        paragraph_index_by_heading[heading_path] = paragraph_index + 1
        paragraphs.append(_ConceptParagraph(heading_path, paragraph_index, body))

    for line in lines:
        heading = _parse_atx_heading(line)
        if heading is not None:
            flush()
            level, title = heading
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue
        if not line.strip():
            flush()
            continue
        if is_markdown_list_item(line):
            flush()
            current.append(line)
            current_kind = "list_item"
            continue
        if current_kind == "list_item" and is_markdown_list_continuation(line):
            current.append(line)
            continue
        if current_kind == "list_item":
            flush()
        current.append(line)
        current_kind = "paragraph"
    flush()
    return paragraphs


def is_markdown_list_item(line: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith(("- ", "* ", "+ ")):
        return True
    marker_end = 0
    while marker_end < len(stripped) and stripped[marker_end].isdigit():
        marker_end += 1
    return (
        marker_end > 0
        and marker_end + 1 < len(stripped)
        and stripped[marker_end] in {".", ")"}
        and stripped[marker_end + 1].isspace()
    )


def is_markdown_list_continuation(line: str) -> bool:
    return line.startswith((" ", "\t"))


def generate_concept_diff_candidate(
    *,
    project_root: Path,
    config: Mapping[str, Any],
    graph_storage: Path,
    graph_data: Mapping[str, Any],
    concept_index: ConceptIndex | None,
    changed_source_section_ids: Sequence[str],
    changed_source_section_hashes: Mapping[str, str] | None = None,
    extract_run_id: str,
    generated_at: str,
) -> ConceptDiffCandidateResult:
    concept_file = configured_concept_file(project_root, config)
    if concept_file is None or not concept_file.exists() or concept_index is None:
        return ConceptDiffCandidateResult()
    if not changed_source_section_ids:
        return ConceptDiffCandidateResult()

    pending_diff = first_unresolved_pending_concept_diff(
        project_root / ".spec-grag" / "pending"
    )
    semantic_hashes = changed_source_section_hashes or {}

    terms = source_derived_terms(
        graph_data,
        changed_source_section_ids=changed_source_section_ids,
        concept_text=concept_file.read_text(encoding="utf-8"),
    )
    proposal_warnings: list[str] = []
    if pending_diff is not None:
        enqueue_source_changes(
            project_root,
            config=config,
            source_section_ids=list(changed_source_section_ids),
            semantic_hashes=semantic_hashes,
            reason="pending_concept_diff_unresolved",
            pending_concept_diff_id=pending_diff.diff_id,
            detected_at=generated_at,
        )
        update_provisional_concept_cache(
            project_root,
            terms=terms,
            semantic_hashes=semantic_hashes,
            provider=str(_mapping(config.get("concept_diff")).get("provider", "")),
            model=str(_mapping(config.get("concept_diff")).get("model", "")),
            prompt_version="concept_diff_proposal_v1",
            seen_at=generated_at,
        )
        return ConceptDiffCandidateResult(
            warnings=[
                *proposal_warnings,
                f"concept_diff_pending_queue_updated:{pending_diff.diff_id}",
            ]
        )
    terms, proposal_warnings = concept_diff_terms_from_config(
        config=config,
        concept_text=concept_file.read_text(encoding="utf-8"),
        source_terms=terms,
        changed_source_section_ids=changed_source_section_ids,
    )
    if not terms:
        return ConceptDiffCandidateResult(warnings=proposal_warnings)

    diff = build_pending_concept_diff(
        project_root=project_root,
        concept_file=concept_file,
        terms=terms,
        changed_source_section_ids=changed_source_section_ids,
        extract_run_id=extract_run_id,
        generated_at=generated_at,
    )
    update_provisional_concept_cache(
        project_root,
        terms=terms,
        semantic_hashes=semantic_hashes,
        provider=str(_mapping(config.get("concept_diff")).get("provider", "")),
        model=str(_mapping(config.get("concept_diff")).get("model", "")),
        prompt_version="concept_diff_proposal_v1",
        seen_at=generated_at,
    )
    pending_dir = project_root / ".spec-grag" / "pending"
    path = pending_dir / f"concept_diff_{diff.diff_id}.json"
    if path.exists():
        return ConceptDiffCandidateResult(
            warnings=[
                *proposal_warnings,
                f"concept_diff_candidate_already_exists:{diff.diff_id}",
            ]
        )
    created = create_pending_concept_diff(pending_dir, diff)
    return ConceptDiffCandidateResult(
        pending_diff=diff,
        created_path=str(created),
        warnings=proposal_warnings,
    )


def generate_queued_concept_diff_candidate(
    *,
    project_root: Path,
    config: Mapping[str, Any],
    graph_storage: Path,
    extract_run_id: str,
    generated_at: str,
) -> ConceptDiffCandidateResult:
    queue = load_watch_queue(watch_queue_path(project_root, config))
    concept_changes = [
        change
        for change in queue.changes
        if change.reason == "pending_concept_diff_unresolved"
    ]
    changed_source_section_ids = [
        change.source_section_id for change in concept_changes
    ]
    if not changed_source_section_ids:
        return ConceptDiffCandidateResult()

    if first_unresolved_pending_concept_diff(project_root / ".spec-grag" / "pending") is not None:
        return ConceptDiffCandidateResult(
            warnings=["queued_concept_diff_waiting_for_existing_pending"]
        )

    concept_index = load_concept_index(concept_index_path(graph_storage))
    if concept_index is None:
        try:
            concept_index, concept_index_warnings = refresh_concept_index(
                project_root,
                config,
                graph_storage,
                generated_at=generated_at,
            )
        except Exception as exc:
            return ConceptDiffCandidateResult(
                warnings=[f"queued_concept_index_refresh_failed:{exc}"]
            )
    else:
        concept_index_warnings = []

    try:
        graph_store = SimplePropertyGraphStore.from_persist_dir(str(graph_storage))
        graph_data = graph_store.graph.model_dump()
    except Exception as exc:
        return ConceptDiffCandidateResult(
            warnings=[*concept_index_warnings, f"queued_concept_graph_load_failed:{exc}"]
        )

    semantic_hashes = {
        change.source_section_id: change.semantic_hash for change in concept_changes
    }
    result = generate_concept_diff_candidate(
        project_root=project_root,
        config=config,
        graph_storage=graph_storage,
        graph_data=graph_data,
        concept_index=concept_index,
        changed_source_section_ids=changed_source_section_ids,
        changed_source_section_hashes=semantic_hashes,
        extract_run_id=extract_run_id,
        generated_at=generated_at,
    )
    if result.pending_diff is not None or not result.warnings:
        remove_watch_queue_changes(
            project_root,
            config=config,
            reasons={"pending_concept_diff_unresolved"},
        )
    elif all(
        not warning.startswith("queued_concept_diff_waiting")
        and not warning.startswith("concept_diff_pending_queue_updated")
        for warning in result.warnings
    ):
        remove_watch_queue_changes(
            project_root,
            config=config,
            reasons={"pending_concept_diff_unresolved"},
        )
    return result.model_copy(
        update={"warnings": [*concept_index_warnings, *result.warnings]}
    )


def source_derived_terms(
    graph_data: Mapping[str, Any],
    *,
    changed_source_section_ids: Sequence[str],
    concept_text: str,
) -> list[dict[str, str]]:
    changed = set(changed_source_section_ids)
    concept_norm = _normalize_for_match(concept_text)
    terms: dict[str, dict[str, str]] = {}
    nodes = graph_data.get("nodes") or {}
    for node_id, node in nodes.items():
        if node.get("label") != "ANCHOR":
            continue
        props = node.get("properties") or {}
        if props.get("extractor_name") != "SchemaLLMPathExtractor":
            continue
        section_id = str(props.get("source_section_id") or "")
        if changed and section_id not in changed:
            continue
        term = str(
            props.get("display_name")
            or props.get("description")
            or node.get("name")
            or node_id
        ).strip()
        if not term:
            continue
        if _normalize_for_match(term) in concept_norm:
            continue
        terms.setdefault(
            _normalize_for_match(term),
            {
                "term": term,
                "source_section_id": section_id,
                "evidence_excerpt": str(props.get("evidence_excerpt") or term),
                "source_span": str(props.get("source_span") or ""),
            },
        )
    return sorted(terms.values(), key=lambda item: (item["source_section_id"], item["term"]))


def concept_diff_terms_from_config(
    *,
    config: Mapping[str, Any],
    concept_text: str,
    source_terms: Sequence[Mapping[str, str]],
    changed_source_section_ids: Sequence[str],
) -> tuple[list[dict[str, str]], list[str]]:
    concept_diff_config = _mapping(config.get("concept_diff"))
    provider = str(
        concept_diff_config.get("provider", "source_derived")
    ).strip().lower()
    if provider in {"none", "disabled"}:
        return [], ["concept_diff_proposal_disabled"]
    if provider in {"source_derived", "template", ""}:
        return [dict(term) for term in source_terms], []

    try:
        llm = make_concept_diff_llm_from_config(config)
        proposal = generate_concept_diff_proposal_with_llm(
            concept_text=concept_text,
            source_terms=source_terms,
            changed_source_section_ids=changed_source_section_ids,
            llm=llm,
        )
        terms = concept_proposal_to_terms(
            proposal,
            changed_source_section_ids=changed_source_section_ids,
        )
        return terms, proposal.warnings
    except (CLIAdapterError, ValidationError, ValueError, RuntimeError) as exc:
        if bool(concept_diff_config.get("fallback_on_error", True)):
            return [dict(term) for term in source_terms], [
                f"concept_diff_llm_proposal_fallback:{exc}"
            ]
        raise ConceptDiffProposalError(
            f"Concept diff LLM proposal failed: {exc}"
        ) from exc


def make_concept_diff_llm_from_config(config: Mapping[str, Any]) -> Any:
    llm = make_stage_llm_from_config(
        config,
        "concept_diff",
        default_provider="source_derived",
        disabled_providers={"source_derived", "template", "none", "disabled", ""},
    )
    if llm is None:
        raise ValueError("unsupported concept_diff.provider: disabled")
    return llm


def generate_concept_diff_proposal_with_llm(
    *,
    concept_text: str,
    source_terms: Sequence[Mapping[str, str]],
    changed_source_section_ids: Sequence[str],
    llm: Any,
) -> ConceptDiffProposal:
    prompt = "\n".join(
        [
            "You are proposing updates to SPEC-grag Core Concept.",
            "Do not edit the Concept file directly.",
            "Return a structured proposal using only the supplied source-derived candidates.",
            "Each proposal item must keep source_section_id and evidence_excerpt.",
            "Include warnings as an array. Use an empty string for source_span or proposed_text when absent.",
            "",
            "INPUT_JSON:",
            json.dumps(
                {
                    "concept_text": concept_text,
                    "changed_source_section_ids": list(changed_source_section_ids),
                    "source_terms": list(source_terms),
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
        ]
    )
    response = llm.complete(prompt, output_schema=ConceptDiffProposal)
    return ConceptDiffProposal.model_validate_json(response.text)


def concept_proposal_to_terms(
    proposal: ConceptDiffProposal,
    *,
    changed_source_section_ids: Sequence[str],
) -> list[dict[str, str]]:
    allowed_sections = set(changed_source_section_ids)
    terms: dict[str, dict[str, str]] = {}
    for item in proposal.items:
        term = item.term.strip()
        if not term:
            continue
        if allowed_sections and item.source_section_id not in allowed_sections:
            continue
        if not item.evidence_excerpt.strip():
            continue
        normalized = _normalize_for_match(term)
        terms.setdefault(
            normalized,
            {
                "term": term,
                "source_section_id": item.source_section_id,
                "evidence_excerpt": item.evidence_excerpt,
                "source_span": item.source_span or "",
                "proposed_text": item.proposed_text or term,
            },
        )
    return sorted(terms.values(), key=lambda item: (item["source_section_id"], item["term"]))


def build_pending_concept_diff(
    *,
    project_root: Path,
    concept_file: Path,
    terms: Sequence[Mapping[str, str]],
    changed_source_section_ids: Sequence[str],
    extract_run_id: str,
    generated_at: str,
) -> PendingConceptDiff:
    base_hash = concept_file_hash(concept_file)
    rel_file = _relative_path(project_root, concept_file)
    diff_id = concept_diff_id_for(base_hash, terms)
    hunk = build_append_hunk(concept_file, rel_file, terms)
    return PendingConceptDiff(
        diff_id=diff_id,
        base_concept_hash=base_hash,
        generated_at=generated_at,
        task_context=ConceptDiffTaskContext(
            command=Command.SPEC_CORE,
            changed_source_section_ids=sorted(set(changed_source_section_ids)),
            extract_run_id=extract_run_id,
        ),
        hunks=[hunk],
    )


def build_append_hunk(
    concept_file: Path,
    rel_file: str,
    terms: Sequence[Mapping[str, str]],
) -> PendingConceptHunk:
    text = concept_file.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    old_start = len(lines) + 1
    prefix = [] if text.endswith("\n") or not text else ["\n"]
    new_lines = [
        *prefix,
        f"## {SOURCE_DERIVED_HEADING}\n",
        "\n",
        *[
            concept_diff_term_line(term)
            for term in terms
        ],
    ]
    diff_lines = [
        f"--- a/{rel_file}\n",
        f"+++ b/{rel_file}\n",
        f"@@ -{old_start},0 +{old_start},{len(new_lines)} @@\n",
        *[f"+{line}" for line in new_lines],
    ]
    return PendingConceptHunk(
        hunk_id="hunk-1",
        file=rel_file,
        old_range=f"-{old_start},0",
        new_range=f"+{old_start},{len(new_lines)}",
        diff_text="".join(diff_lines),
    )


def concept_diff_term_line(term: Mapping[str, str]) -> str:
    proposed = str(term.get("proposed_text") or term["term"]).strip()
    span = str(term.get("source_span") or "").strip()
    span_suffix = f", span: {span}" if span else ""
    return f"- {proposed} (source: {term['source_section_id']}{span_suffix})\n"


def concept_chunk_id_for(
    concept_file: str,
    heading_path: str,
    paragraph_index: int,
    text: str,
) -> str:
    payload = json.dumps(
        {
            "concept_file": concept_file,
            "heading_path": heading_path,
            "paragraph_index": paragraph_index,
            "text_hash": _sha256_text(text),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"concept:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def concept_diff_id_for(base_concept_hash: str, terms: Sequence[Mapping[str, str]]) -> str:
    payload = json.dumps(
        {
            "base_concept_hash": base_concept_hash,
            "terms": [
                {
                    "term": term["term"],
                    "source_section_id": term["source_section_id"],
                }
                for term in terms
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"diff-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def stable_embedding(text: str, *, dimensions: int = 8) -> list[float]:
    return make_stable_embedding(text, dimensions=dimensions)


def _parse_atx_heading(line: str) -> tuple[int, str] | None:
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None
    hashes = len(stripped) - len(stripped.lstrip("#"))
    if hashes < 1 or hashes > 6:
        return None
    if len(stripped) <= hashes or stripped[hashes] not in {" ", "\t"}:
        return None
    title = stripped[hashes:].strip().strip("#").strip()
    return (hashes, title) if title else None


def _normalize_for_match(text: str) -> str:
    return "".join(char.lower() for char in text if char.isalnum())


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relative_path(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _json_file_has_key(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and key in data


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
