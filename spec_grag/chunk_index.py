"""Raw document chunk indexing and hybrid retrieval for SPEC-grag."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError

from spec_grag.embedding import (
    EmbeddingMetadata,
    embedding_identity_matches,
    embedding_for_text,
)
from spec_grag.llm_adapters import CLIAdapterError, ClaudeCLIAdapter, CodexCLIAdapter
from spec_grag.manifest import SourceManifest, SourceManifestEntry
from spec_grag.protocol import ConversationContext, StrictModel


CHUNK_INDEX_VERSION = "1"
DOCUMENT_CHUNKS_FILENAME = "document_chunks.json"
CHUNK_VECTOR_INDEX_FILENAME = "chunk_vector_index.json"
BM25_INDEX_FILENAME = "bm25_index.json"

DEFAULT_CHUNK_SIZE = 1600
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_VECTOR_TOP_K = 8
DEFAULT_BM25_TOP_K = 12
DEFAULT_MAX_SOURCE_CHUNKS = 12
DEFAULT_RRF_K = 60.0
BM25_ANALYZER = "char2_3+identifier-v1"

_IDENTIFIER_RE = re.compile(
    r"[@#]?[A-Za-z_][A-Za-z0-9_./:@#-]*|[A-Za-z0-9_]+(?:[./:@#-][A-Za-z0-9_]+)+"
)
_WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class DocumentChunk(StrictModel):
    chunk_id: str
    document_id: str
    chapter_id: str
    section_id: str
    heading_path: str
    source_span: str
    source_hash: str
    text: str
    chunk_hash: str
    generated_at: str


class DocumentChunksSidecar(StrictModel):
    version: str = CHUNK_INDEX_VERSION
    graph_revision: str | None = None
    generated_at: str | None = None
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    chunks: list[DocumentChunk] = Field(default_factory=list)

    def by_chunk_id(self) -> dict[str, DocumentChunk]:
        return {chunk.chunk_id: chunk for chunk in self.chunks}


class ChunkEmbedding(StrictModel):
    chunk_id: str
    chunk_hash: str
    embedding: list[float] = Field(default_factory=list)


class ChunkVectorIndex(StrictModel):
    version: str = CHUNK_INDEX_VERSION
    graph_revision: str | None = None
    generated_at: str | None = None
    embedding_metadata: EmbeddingMetadata
    embeddings: list[ChunkEmbedding] = Field(default_factory=list)

    def by_chunk_id(self) -> dict[str, ChunkEmbedding]:
        return {item.chunk_id: item for item in self.embeddings}


class BM25Document(StrictModel):
    chunk_id: str
    chunk_hash: str
    length: int
    term_frequencies: dict[str, int] = Field(default_factory=dict)


class BM25Index(StrictModel):
    version: str = CHUNK_INDEX_VERSION
    graph_revision: str | None = None
    generated_at: str | None = None
    analyzer: str = BM25_ANALYZER
    document_count: int = 0
    average_doc_length: float = 0.0
    document_frequencies: dict[str, int] = Field(default_factory=dict)
    documents: list[BM25Document] = Field(default_factory=list)

    def by_chunk_id(self) -> dict[str, BM25Document]:
        return {item.chunk_id: item for item in self.documents}


class QueryPlan(StrictModel):
    intent: str
    high_level_concepts: list[str]
    low_level_entities: list[str]
    expected_source_areas: list[str]
    disambiguation_hints: list[str]
    must_include_identifiers: list[str]
    question_type: str


@dataclass(frozen=True)
class ChunkSearchHit:
    chunk: DocumentChunk
    score: float
    retrieval_methods: tuple[str, ...]
    method_scores: dict[str, float] = field(default_factory=dict)


def document_chunks_path(graph_storage: Path) -> Path:
    return graph_storage / DOCUMENT_CHUNKS_FILENAME


def chunk_vector_index_path(graph_storage: Path) -> Path:
    return graph_storage / CHUNK_VECTOR_INDEX_FILENAME


def bm25_index_path(graph_storage: Path) -> Path:
    return graph_storage / BM25_INDEX_FILENAME


def build_document_chunks(
    project_root: Path,
    manifest: SourceManifest,
    *,
    config: Mapping[str, Any],
    graph_revision: str,
    generated_at: str,
) -> DocumentChunksSidecar:
    chunk_size = retrieval_int(config, "chunk_size", DEFAULT_CHUNK_SIZE)
    chunk_overlap = retrieval_int(config, "chunk_overlap", DEFAULT_CHUNK_OVERLAP)
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(chunk_size // 4, 0)

    chunks: list[DocumentChunk] = []
    entries_by_document: dict[str, list[SourceManifestEntry]] = defaultdict(list)
    for entry in manifest.entries:
        entries_by_document[entry.document_id].append(entry)

    for document_id, entries in sorted(entries_by_document.items()):
        path = Path(document_id)
        if not path.is_absolute():
            path = project_root / path
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        ordered = sorted(entries, key=lambda item: (item.heading_start_line, item.section_id))
        for index, entry in enumerate(ordered):
            start = max(entry.heading_start_line, 1)
            next_start = (
                ordered[index + 1].heading_start_line
                if index + 1 < len(ordered)
                else len(lines) + 1
            )
            end = max(start, next_start - 1)
            section_lines = lines[start - 1 : end]
            chunks.extend(
                split_entry_into_chunks(
                    entry,
                    section_lines,
                    section_start_line=start,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    generated_at=generated_at,
                )
            )

    return DocumentChunksSidecar(
        graph_revision=graph_revision,
        generated_at=generated_at,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        chunks=chunks,
    )


def split_entry_into_chunks(
    entry: SourceManifestEntry,
    section_lines: Sequence[str],
    *,
    section_start_line: int,
    chunk_size: int,
    chunk_overlap: int,
    generated_at: str,
) -> list[DocumentChunk]:
    if not section_lines:
        return []

    chunks: list[DocumentChunk] = []
    current: list[tuple[int, str]] = []
    current_size = 0

    def flush() -> None:
        nonlocal current, current_size
        if not current:
            return
        chunk_index = len(chunks)
        start_line = current[0][0]
        end_line = current[-1][0]
        text = "".join(line for _, line in current)
        normalized = normalize_line_endings(text)
        chunk_hash = sha256_text(normalized)
        if chunk_has_body_text(normalized):
            chunks.append(
                DocumentChunk(
                    chunk_id=f"chunk:{entry.section_id}:{chunk_index}",
                    document_id=entry.document_id,
                    chapter_id=entry.chapter_id,
                    section_id=entry.section_id,
                    heading_path=entry.heading_path,
                    source_span=f"{start_line}-{end_line}",
                    source_hash=entry.source_hash,
                    text=normalized.strip(),
                    chunk_hash=chunk_hash,
                    generated_at=generated_at,
                )
            )
        overlap: list[tuple[int, str]] = []
        overlap_size = 0
        if chunk_overlap > 0:
            for line_no, line in reversed(current):
                if overlap and overlap_size >= chunk_overlap:
                    break
                overlap.append((line_no, line))
                overlap_size += len(line)
        current = list(reversed(overlap))
        current_size = sum(len(line) for _, line in current)

    for line_no, line in enumerate(section_lines, start=section_start_line):
        if current and current_size + len(line) > chunk_size:
            flush()
        current.append((line_no, line))
        current_size += len(line)
        if current_size >= chunk_size:
            flush()
    flush()
    return [chunk for chunk in chunks if chunk.text]


def chunk_has_body_text(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        return True
    return False


def build_chunk_vector_index(
    chunks: DocumentChunksSidecar,
    *,
    embedding_metadata: EmbeddingMetadata,
    embedding_config: Mapping[str, Any] | None = None,
    previous_index: ChunkVectorIndex | None = None,
) -> ChunkVectorIndex:
    reusable_embeddings = _reusable_chunk_embeddings(
        previous_index,
        embedding_metadata=embedding_metadata,
    )
    return ChunkVectorIndex(
        graph_revision=chunks.graph_revision,
        generated_at=chunks.generated_at,
        embedding_metadata=embedding_metadata,
        embeddings=[
            ChunkEmbedding(
                chunk_id=chunk.chunk_id,
                chunk_hash=chunk.chunk_hash,
                embedding=_chunk_embedding(
                    chunk,
                    reusable_embeddings=reusable_embeddings,
                    embedding_metadata=embedding_metadata,
                    embedding_config=embedding_config,
                ),
            )
            for chunk in chunks.chunks
        ],
    )


def _reusable_chunk_embeddings(
    previous_index: ChunkVectorIndex | None,
    *,
    embedding_metadata: EmbeddingMetadata,
) -> dict[str, ChunkEmbedding]:
    if previous_index is None:
        return {}
    if not embedding_identity_matches(previous_index.embedding_metadata, embedding_metadata):
        return {}
    return previous_index.by_chunk_id()


def _chunk_embedding(
    chunk: DocumentChunk,
    *,
    reusable_embeddings: Mapping[str, ChunkEmbedding],
    embedding_metadata: EmbeddingMetadata,
    embedding_config: Mapping[str, Any] | None,
) -> list[float]:
    previous = reusable_embeddings.get(chunk.chunk_id)
    if (
        previous is not None
        and previous.chunk_hash == chunk.chunk_hash
        and previous.embedding
    ):
        return list(previous.embedding)
    return embedding_for_text(
        chunk.text,
        embedding_metadata,
        config=embedding_config,
    )


def build_bm25_index(chunks: DocumentChunksSidecar) -> BM25Index:
    documents: list[BM25Document] = []
    document_frequencies: Counter[str] = Counter()
    total_length = 0
    for chunk in chunks.chunks:
        frequencies = Counter(analyze_text(chunk.text))
        length = sum(frequencies.values())
        total_length += length
        document_frequencies.update(frequencies.keys())
        documents.append(
            BM25Document(
                chunk_id=chunk.chunk_id,
                chunk_hash=chunk.chunk_hash,
                length=length,
                term_frequencies=dict(sorted(frequencies.items())),
            )
        )
    document_count = len(documents)
    average_doc_length = total_length / document_count if document_count else 0.0
    return BM25Index(
        graph_revision=chunks.graph_revision,
        generated_at=chunks.generated_at,
        document_count=document_count,
        average_doc_length=average_doc_length,
        document_frequencies=dict(sorted(document_frequencies.items())),
        documents=documents,
    )


def retrieve_hybrid_chunks(
    *,
    project_root: Path,
    graph_storage: Path,
    query: str,
    context: ConversationContext,
    config: Mapping[str, Any],
) -> tuple[list[ChunkSearchHit], QueryPlan, list[str]]:
    warnings: list[str] = []
    chunks = load_document_chunks(document_chunks_path(graph_storage))
    if not chunks.chunks:
        return [], template_query_plan(query), ["document_chunks_missing_or_empty"]

    query_plan, planner_warnings = query_plan_from_config(query=query, config=config)
    warnings.extend(planner_warnings)
    retrieval_query = query_text_for_plan(query, query_plan)
    max_chunks = retrieval_int(config, "max_source_chunks", DEFAULT_MAX_SOURCE_CHUNKS)

    bm25 = load_bm25_index(bm25_index_path(graph_storage))
    if not bm25.documents:
        bm25_hits: list[tuple[str, float]] = []
        warnings.append("bm25_index_missing_or_empty")
    else:
        bm25_hits = bm25_search(
            bm25,
            retrieval_query,
            limit=retrieval_int(config, "bm25_top_k", DEFAULT_BM25_TOP_K),
        )

    vector = load_chunk_vector_index(chunk_vector_index_path(graph_storage))
    if vector is None or not vector.embeddings:
        dense_hits: list[tuple[str, float]] = []
        warnings.append("chunk_vector_index_missing_or_empty")
    else:
        dense_hits = dense_search(
            vector,
            retrieval_query,
            limit=retrieval_int(config, "vector_top_k", DEFAULT_VECTOR_TOP_K),
            embedding_config=_mapping(config.get("embedding")),
        )

    explicit_hits = explicit_chunk_hits(chunks, context)
    hits = fuse_chunk_hits(
        chunks,
        bm25_hits=bm25_hits,
        dense_hits=dense_hits,
        explicit_hits=explicit_hits,
        dense_enabled=vector is not None
        and vector.embedding_metadata.provider != "stable_hash",
        limit=max_chunks,
    )
    return hits, query_plan, warnings


def query_plan_from_config(
    *,
    query: str,
    config: Mapping[str, Any],
) -> tuple[QueryPlan, list[str]]:
    planner_config = _mapping(config.get("query_planner"))
    provider = str(planner_config.get("provider", "template")).strip().lower()
    if provider in {"template", "deterministic", "none", "disabled", ""}:
        return template_query_plan(query), []
    try:
        llm = make_query_planner_llm_from_config(config)
        return generate_query_plan_with_llm(query, llm=llm), []
    except (CLIAdapterError, ValidationError, ValueError, RuntimeError) as exc:
        if bool(planner_config.get("fallback_on_error", True)):
            return template_query_plan(query), [f"query_planner_fallback_template:{exc}"]
        raise


def make_query_planner_llm_from_config(config: Mapping[str, Any]) -> Any:
    planner_config = _mapping(config.get("query_planner"))
    provider = str(planner_config.get("provider", "template")).strip().lower()
    if provider == "codex":
        return CodexCLIAdapter(
            command=str(planner_config.get("command") or "codex"),
            model=str(planner_config.get("model") or "gpt-5.4"),
            effort=str(planner_config.get("effort") or "low"),
            timeout_sec=int(planner_config.get("timeout_sec", 120)),
            sandbox=str(planner_config.get("sandbox", "read-only")),
            max_retries=int(planner_config.get("max_retries", 0)),
            retry_backoff_sec=float(planner_config.get("retry_backoff_sec", 0.0)),
            repair_on_schema_failure=bool(
                planner_config.get("repair_on_schema_failure", True)
            ),
        )
    if provider == "claude":
        return ClaudeCLIAdapter(
            command=str(planner_config.get("command") or "claude"),
            model=str(planner_config.get("model") or ""),
            effort=str(planner_config.get("effort") or "low"),
            timeout_sec=int(planner_config.get("timeout_sec", 120)),
            tools=str(planner_config.get("tools", "")),
            max_retries=int(planner_config.get("max_retries", 0)),
            retry_backoff_sec=float(planner_config.get("retry_backoff_sec", 0.0)),
            repair_on_schema_failure=bool(
                planner_config.get("repair_on_schema_failure", True)
            ),
        )
    raise ValueError(f"unsupported query_planner.provider: {provider}")


def generate_query_plan_with_llm(query: str, *, llm: Any) -> QueryPlan:
    prompt = "\n".join(
        [
            "You are the SPEC-grag Query Planner phase.",
            "Return JSON that matches the supplied schema.",
            "Plan retrieval only. Do not assert source facts.",
            "Prefer source-grounded terms, identifiers, expected source areas, and disambiguation hints.",
            "Return every array field, even when it is empty, and set question_type.",
            "",
            "INPUT_JSON:",
            json.dumps({"query": query}, ensure_ascii=False, indent=2, sort_keys=True),
        ]
    )
    response = llm.complete(prompt, output_schema=QueryPlan)
    return QueryPlan.model_validate_json(response.text)


def template_query_plan(query: str) -> QueryPlan:
    identifiers = sorted(identifier_terms(query))
    return QueryPlan(
        intent=query.strip() or "related source specification",
        high_level_concepts=[query.strip()] if query.strip() else [],
        low_level_entities=identifiers,
        expected_source_areas=[],
        disambiguation_hints=[],
        must_include_identifiers=identifiers,
        question_type="search",
    )


def query_text_for_plan(query: str, plan: QueryPlan) -> str:
    parts = [
        query,
        plan.intent,
        *plan.high_level_concepts,
        *plan.low_level_entities,
        *plan.expected_source_areas,
        *plan.disambiguation_hints,
        *plan.must_include_identifiers,
        plan.question_type,
    ]
    return " ".join(part for part in parts if part)


def bm25_search(index: BM25Index, query: str, *, limit: int) -> list[tuple[str, float]]:
    query_terms = Counter(analyze_text(query))
    if not query_terms or not index.documents or index.average_doc_length <= 0:
        return []
    scores: list[tuple[str, float]] = []
    k1 = 1.5
    b = 0.75
    for document in index.documents:
        score = 0.0
        matched_terms: list[str] = []
        for term, query_frequency in query_terms.items():
            term_frequency = document.term_frequencies.get(term, 0)
            if term_frequency <= 0:
                continue
            matched_terms.append(term)
            document_frequency = index.document_frequencies.get(term, 0)
            idf = math.log(
                1.0
                + (index.document_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            denominator = term_frequency + k1 * (
                1.0 - b + b * document.length / index.average_doc_length
            )
            score += query_frequency * idf * (
                term_frequency * (k1 + 1.0) / denominator
            )
        if score > 0 and bm25_match_is_meaningful(matched_terms):
            scores.append((document.chunk_id, round(score, 6)))
    return sorted(scores, key=lambda item: (-item[1], item[0]))[:limit]


def bm25_match_is_meaningful(matched_terms: Sequence[str]) -> bool:
    if any(term.startswith(("id:", "word:")) for term in matched_terms):
        return True
    char_matches = sum(1 for term in matched_terms if term.startswith("char"))
    return char_matches >= 3


def dense_search(
    index: ChunkVectorIndex,
    query: str,
    *,
    limit: int,
    embedding_config: Mapping[str, Any] | None = None,
) -> list[tuple[str, float]]:
    if not query.strip():
        return []
    query_embedding = embedding_for_text(
        query,
        index.embedding_metadata,
        config=embedding_config,
    )
    scores = [
        (item.chunk_id, round(cosine_similarity(query_embedding, item.embedding), 6))
        for item in index.embeddings
        if item.embedding
    ]
    return sorted(scores, key=lambda item: (-item[1], item[0]))[:limit]


def explicit_chunk_hits(
    chunks: DocumentChunksSidecar,
    context: ConversationContext,
) -> list[tuple[str, float]]:
    explicit_files = set(context.explicit_files)
    working_target = context.working_target
    hits = []
    for chunk in chunks.chunks:
        if chunk.document_id in explicit_files or chunk.document_id == working_target:
            hits.append((chunk.chunk_id, 1.0))
    return hits


def fuse_chunk_hits(
    chunks: DocumentChunksSidecar,
    *,
    bm25_hits: Sequence[tuple[str, float]],
    dense_hits: Sequence[tuple[str, float]],
    explicit_hits: Sequence[tuple[str, float]],
    dense_enabled: bool,
    limit: int,
) -> list[ChunkSearchHit]:
    chunk_by_id = chunks.by_chunk_id()
    scores: dict[str, float] = defaultdict(float)
    methods: dict[str, set[str]] = defaultdict(set)
    method_scores: dict[str, dict[str, float]] = defaultdict(dict)

    add_ranked_hits(
        bm25_hits,
        scores=scores,
        methods=methods,
        method_scores=method_scores,
        method="bm25",
    )
    if dense_enabled:
        add_ranked_hits(
            dense_hits,
            scores=scores,
            methods=methods,
            method_scores=method_scores,
            method="dense_vector",
        )
    for chunk_id, score in explicit_hits:
        if chunk_id in chunk_by_id:
            scores[chunk_id] += 1.0 + score
            methods[chunk_id].add("explicit_target")
            method_scores[chunk_id]["explicit_target"] = score

    hits = [
        ChunkSearchHit(
            chunk=chunk_by_id[chunk_id],
            score=round(score, 6),
            retrieval_methods=tuple(sorted(methods[chunk_id] | {"rank_fusion"})),
            method_scores=dict(sorted(method_scores[chunk_id].items())),
        )
        for chunk_id, score in scores.items()
        if chunk_id in chunk_by_id and score > 0
    ]
    return sorted(
        hits,
        key=lambda hit: (-hit.score, hit.chunk.document_id, hit.chunk.source_span, hit.chunk.chunk_id),
    )[:limit]


def add_ranked_hits(
    hits: Sequence[tuple[str, float]],
    *,
    scores: dict[str, float],
    methods: dict[str, set[str]],
    method_scores: dict[str, dict[str, float]],
    method: str,
) -> None:
    for rank, (chunk_id, raw_score) in enumerate(hits, start=1):
        scores[chunk_id] += 1.0 / (DEFAULT_RRF_K + rank)
        methods[chunk_id].add(method)
        method_scores[chunk_id][method] = raw_score


def analyze_text(text: str) -> list[str]:
    tokens: list[str] = []
    lowered = text.casefold()
    compact = "".join(char for char in lowered if not char.isspace())
    for n in (2, 3):
        if len(compact) < n:
            continue
        tokens.extend(f"char{n}:{compact[index:index + n]}" for index in range(len(compact) - n + 1))
    for word in _WORD_RE.findall(lowered):
        tokens.append(f"word:{word}")
    for term in identifier_terms(text):
        tokens.append(f"id:{term.casefold()}")
    return tokens


def identifier_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for match in _IDENTIFIER_RE.finditer(text):
        raw = match.group(0).strip(".,;()[]{}<>\"'")
        if not raw:
            continue
        terms.add(raw)
        for part in re.split(r"[./:@#-]+", raw):
            if len(part) >= 2:
                terms.add(part)
            for camel in _CAMEL_BOUNDARY_RE.split(part):
                if len(camel) >= 2:
                    terms.add(camel)
    return {term.casefold() for term in terms if term.strip()}


def validate_chunk_source(project_root: Path, chunk: DocumentChunk) -> str | None:
    path = Path(chunk.document_id)
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        return "chunk_source_document_missing"
    span = parse_line_span(chunk.source_span)
    if span is None:
        return "chunk_source_span_invalid"
    lines = path.read_text(encoding="utf-8").splitlines()
    start, end = span
    if start < 1 or end > len(lines) or start > end:
        return "chunk_source_span_out_of_range"
    span_text = "\n".join(lines[start - 1 : end])
    if normalize_excerpt(chunk.text) not in normalize_excerpt(span_text):
        return "chunk_text_not_found_in_source_span"
    return None


def parse_line_span(value: str) -> tuple[int, int] | None:
    numbers = [int(item) for item in re.findall(r"\d+", value)]
    if not numbers:
        return None
    start = numbers[0]
    end = numbers[1] if len(numbers) > 1 else start
    if start <= 0 or end < start:
        return None
    return start, end


def load_document_chunks(path: Path) -> DocumentChunksSidecar:
    if not path.exists():
        return DocumentChunksSidecar()
    return DocumentChunksSidecar.model_validate_json(path.read_text(encoding="utf-8"))


def load_chunk_vector_index(path: Path) -> ChunkVectorIndex | None:
    if not path.exists():
        return None
    return ChunkVectorIndex.model_validate_json(path.read_text(encoding="utf-8"))


def load_bm25_index(path: Path) -> BM25Index:
    if not path.exists():
        return BM25Index()
    return BM25Index.model_validate_json(path.read_text(encoding="utf-8"))


def write_document_chunks_atomic(path: Path, chunks: DocumentChunksSidecar) -> None:
    write_model_atomic(path, chunks)


def write_chunk_vector_index_atomic(path: Path, index: ChunkVectorIndex) -> None:
    write_model_atomic(path, index)


def write_bm25_index_atomic(path: Path, index: BM25Index) -> None:
    write_model_atomic(path, index)


def write_model_atomic(path: Path, model: StrictModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump_json(indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        fsync_directory(path.parent)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def cosine_similarity(left: list[float], right: list[float]) -> float:
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


def retrieval_int(config: Mapping[str, Any], key: str, default: int) -> int:
    retrieval_config = _mapping(config.get("retrieval"))
    return int(retrieval_config.get(key, default))


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_excerpt(text: str) -> str:
    return " ".join(normalize_line_endings(text).split())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
