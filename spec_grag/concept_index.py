"""Core Concept index and Concept diff candidate generation."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from spec_grag.concept_diff import (
    ConceptDiffTaskContext,
    PendingConceptDiff,
    PendingConceptHunk,
    concept_file_hash,
    create_pending_concept_diff,
)
from spec_grag.protocol import Command, StrictModel


CONCEPT_INDEX_VERSION = "1"
CONCEPT_INDEX_FILENAME = "concept_index.json"
SOURCE_DERIVED_HEADING = "Source-derived concepts"


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
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    chunks: list[ConceptIndexChunk] = Field(default_factory=list)

    def chunk_text(self) -> str:
        return "\n".join(chunk.text for chunk in self.chunks)


class ConceptDiffCandidateResult(StrictModel):
    pending_diff: PendingConceptDiff | None = None
    created_path: str | None = None
    warnings: list[str] = Field(default_factory=list)


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
    existing = load_concept_index(path)
    if existing is not None and existing.concept_file_hash == current_hash:
        return existing, []

    index = build_concept_index(
        project_root,
        concept_file,
        generated_at=generated_at,
    )
    write_concept_index_atomic(path, index)
    return index, []


def build_concept_index(
    project_root: Path,
    concept_file: Path,
    *,
    generated_at: str | None = None,
) -> ConceptIndex:
    text = concept_file.read_text(encoding="utf-8")
    rel_path = _relative_path(project_root, concept_file)
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
            embedding=stable_embedding(paragraph.text),
        )
        for paragraph in split_concept_paragraphs(text)
    ]
    return ConceptIndex(
        concept_file=rel_path,
        concept_file_hash=concept_file_hash(concept_file),
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        chunks=chunks,
    )


def split_concept_paragraphs(text: str) -> list[_ConceptParagraph]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    heading_stack: list[tuple[int, str]] = []
    paragraphs: list[_ConceptParagraph] = []
    current: list[str] = []
    paragraph_index_by_heading: dict[str, int] = {}

    def current_heading_path() -> str:
        return " / ".join(title for _, title in heading_stack) or "root"

    def flush() -> None:
        body = "\n".join(line for line in current).strip()
        current.clear()
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
        current.append(line)
    flush()
    return paragraphs


def generate_concept_diff_candidate(
    *,
    project_root: Path,
    config: Mapping[str, Any],
    graph_storage: Path,
    graph_data: Mapping[str, Any],
    concept_index: ConceptIndex | None,
    changed_source_section_ids: Sequence[str],
    extract_run_id: str,
    generated_at: str,
) -> ConceptDiffCandidateResult:
    concept_file = configured_concept_file(project_root, config)
    if concept_file is None or not concept_file.exists() or concept_index is None:
        return ConceptDiffCandidateResult()
    if not changed_source_section_ids:
        return ConceptDiffCandidateResult()

    terms = source_derived_terms(
        graph_data,
        changed_source_section_ids=changed_source_section_ids,
        concept_text=concept_file.read_text(encoding="utf-8"),
    )
    if not terms:
        return ConceptDiffCandidateResult()

    diff = build_pending_concept_diff(
        project_root=project_root,
        concept_file=concept_file,
        terms=terms,
        changed_source_section_ids=changed_source_section_ids,
        extract_run_id=extract_run_id,
        generated_at=generated_at,
    )
    pending_dir = project_root / ".spec-grag" / "pending"
    path = pending_dir / f"concept_diff_{diff.diff_id}.json"
    if path.exists():
        return ConceptDiffCandidateResult(
            warnings=[f"concept_diff_candidate_already_exists:{diff.diff_id}"]
        )
    created = create_pending_concept_diff(pending_dir, diff)
    return ConceptDiffCandidateResult(
        pending_diff=diff,
        created_path=str(created),
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
            f"- {term['term']} (source: {term['source_section_id']})\n"
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
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [round(digest[index] / 255.0, 6) for index in range(dimensions)]


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


def _write_model_atomic(path: Path, model: StrictModel) -> None:
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
        _fsync_directory(path.parent)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
