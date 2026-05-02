from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from spec_grag.chunk_index import (
    BM25_INDEX_FILENAME,
    CHUNK_VECTOR_INDEX_FILENAME,
    DOCUMENT_CHUNKS_FILENAME,
    BM25Document,
    BM25Index,
    ChunkEmbedding,
    ChunkVectorIndex,
    DocumentChunk,
    DocumentChunksSidecar,
    QueryPlan,
    analyze_text,
    bm25_query_text_for_plan,
    bm25_search,
    build_bm25_index,
    dense_query_text_for_plan,
    document_chunks_path,
    load_bm25_index,
    load_document_chunks,
    query_plan_from_config,
    validate_chunk_source,
)
from spec_grag.protocol import ResultEnvelope, ResultStatus, ResultType
from spec_grag.retrieval_index import RETRIEVAL_INDEX_FILENAME, load_retrieval_index


def write_config(project_root: Path) -> None:
    config_dir = project_root / ".spec-grag"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        """
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[graph]
storage = ".spec-grag/graph/"

[retrieval]
chunk_size = 500
chunk_overlap = 80
vector_top_k = 4
bm25_top_k = 8
max_source_chunks = 6
""".strip(),
        encoding="utf-8",
    )


def write_core_docs(project_root: Path) -> None:
    core = project_root / "docs/core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "purpose.md").write_text("# Purpose\n仕様判断を根拠付きで行う。\n", encoding="utf-8")
    (core / "concept.md").write_text("# Concept\nStoreGroup は状態所有権を明確にする。\n", encoding="utf-8")


def request_payload(project_root: Path, task_prompt: str) -> dict:
    return {
        "command": "spec-inject",
        "project_root": str(project_root),
        "task_prompt": task_prompt,
        "conversation_context": {
            "current_user_message": task_prompt,
            "recent_messages": [],
            "explicit_files": [],
        },
        "agent_capabilities": {
            "can_read_source": True,
            "can_answer": False,
        },
        "options": {"output_format": "json"},
    }


def run_cli(payload: dict) -> ResultEnvelope:
    env = os.environ.copy()
    env["SPEC_GRAG_SMOKE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=json.dumps(payload),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return ResultEnvelope.from_json(result.stdout)


def test_spec_core_writes_raw_chunk_dense_and_bm25_indexes(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_core_docs(tmp_path)
    source = tmp_path / "docs/spec/store.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "# Store\n\n## State Ownership\n\nStoreGroup設計原則を本文に保持する。\n",
        encoding="utf-8",
    )

    envelope = run_cli(request_payload(tmp_path, "StoreGroup設計原則を確認する"))

    graph_dir = tmp_path / ".spec-grag/graph"
    chunks = load_document_chunks(document_chunks_path(graph_dir))
    assert envelope.status == ResultStatus.OK
    assert envelope.result_type == ResultType.INJECTION_CONTEXT
    assert (graph_dir / DOCUMENT_CHUNKS_FILENAME).exists()
    assert (graph_dir / CHUNK_VECTOR_INDEX_FILENAME).exists()
    assert (graph_dir / BM25_INDEX_FILENAME).exists()
    assert (graph_dir / RETRIEVAL_INDEX_FILENAME).exists()
    assert chunks.chunks
    bm25 = load_bm25_index(graph_dir / BM25_INDEX_FILENAME)
    assert bm25.postings
    assert chunks.chunks[0].stable_section_uid
    assert chunks.chunks[0].stable_chunk_uid
    assert any(
        chunks.chunks[0].stable_chunk_uid in chunk_ids
        for chunk_ids in bm25.postings.values()
    )
    retrieval_index = load_retrieval_index(graph_dir / RETRIEVAL_INDEX_FILENAME)
    assert retrieval_index is not None
    assert chunks.chunks[0].section_id in retrieval_index.section_chunks
    assert chunks.chunks[0].stable_section_uid in retrieval_index.stable_section_chunks
    assert (
        chunks.chunks[0].stable_chunk_uid
        in retrieval_index.stable_section_chunks[chunks.chunks[0].stable_section_uid]
    )
    assert validate_chunk_source(tmp_path, chunks.chunks[0]) is None


def test_japanese_no_space_query_retrieves_body_chunk_with_source_span(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_core_docs(tmp_path)
    source = tmp_path / "docs/spec/admin.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "# 管理画面\n\n"
        "## 状態管理\n\n"
        "管理画面仕様ではStoreGroup設計原則を守る。"
        "State Ownership は UI state と domain state を分離する。\n",
        encoding="utf-8",
    )

    envelope = run_cli(
        request_payload(
            tmp_path,
            "StoreGroup設計原則を確認して管理画面仕様で守るべき制約を教えて",
        )
    )

    related = envelope.payload.target_context.related_source_sections
    assert related
    assert any("StoreGroup設計原則" in item["excerpt"] for item in related)
    assert all(item.get("source_span") for item in related)
    assert any("bm25" in item.get("retrieval_methods", []) for item in related)


def test_stable_chunk_uid_survives_body_edit_at_same_chunk_ordinal(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    write_core_docs(tmp_path)
    source = tmp_path / "docs/spec/store.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "# Store\n\n## State Ownership\n\nStoreGroup設計原則を本文に保持する。\n",
        encoding="utf-8",
    )
    run_cli(request_payload(tmp_path, "StoreGroup設計原則を確認する"))
    graph_dir = tmp_path / ".spec-grag/graph"
    before = load_document_chunks(document_chunks_path(graph_dir)).chunks[0]

    source.write_text(
        "# Store\n\n## State Ownership\n\nStoreGroup設計原則を本文に保持し、境界を明確にする。\n",
        encoding="utf-8",
    )
    run_cli(request_payload(tmp_path, "StoreGroup設計原則の境界を確認する"))
    after = load_document_chunks(document_chunks_path(graph_dir)).chunks[0]

    assert before.chunk_hash != after.chunk_hash
    assert before.stable_section_uid == after.stable_section_uid
    assert before.stable_chunk_uid == after.stable_chunk_uid


def test_identifier_query_retrieves_terms_that_only_exist_in_body(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_core_docs(tmp_path)
    source = tmp_path / "docs/spec/runtime.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "# Runtime\n\n"
        "## Notes\n\n"
        "The orchestration layer must pass ActionContext to defineStoreGroup "
        "and call flattenRefs before persistence.\n",
        encoding="utf-8",
    )

    envelope = run_cli(
        request_payload(tmp_path, "defineStoreGroup flattenRefs ActionContext")
    )

    related = envelope.payload.target_context.related_source_sections
    assert any("flattenRefs" in item["excerpt"] for item in related)
    assert any("ActionContext" in item["excerpt"] for item in related)
    assert any(item["heading_path"] == "Runtime / Notes" for item in related)


def test_bm25_analyzer_keeps_identifiers_and_char_ngrams() -> None:
    tokens = analyze_text("StoreGroup設計 defineStoreGroup flattenRefs @core/ui")

    assert "id:storegroup" in tokens
    assert "id:definestoregroup" in tokens
    assert "id:flattenrefs" in tokens
    assert "id:@core/ui" in tokens
    assert "char2:設計" in tokens


def test_chunk_lookup_indexes_are_cached() -> None:
    chunk = DocumentChunk(
        chunk_id="chunk:auth:0",
        stable_chunk_uid="stable:auth:0",
        document_id="docs/spec/auth.md",
        chapter_id="docs/spec/auth.md#auth",
        section_id="docs/spec/auth.md#auth-login",
        stable_section_uid="stable:section:auth",
        heading_path="Auth / Login",
        source_span="1-3",
        source_hash="hash-source",
        text="OAuth is required.",
        chunk_hash="hash-chunk",
        generated_at="t1",
    )
    chunks = DocumentChunksSidecar(chunks=[chunk])
    vector = ChunkVectorIndex(
        embedding_metadata={"provider": "stable_hash", "model": "sha256-v1", "dimension": 1},
        embeddings=[
            ChunkEmbedding(
                chunk_id=chunk.chunk_id,
                stable_chunk_uid=chunk.stable_chunk_uid,
                chunk_hash=chunk.chunk_hash,
                embedding=[1.0],
            )
        ],
    )
    bm25 = BM25Index(
        documents=[
            BM25Document(
                chunk_id=chunk.chunk_id,
                stable_chunk_uid=chunk.stable_chunk_uid,
                chunk_hash=chunk.chunk_hash,
                length=3,
            )
        ]
    )

    assert chunks.by_retrieval_key() is chunks.by_retrieval_key()
    assert vector.by_retrieval_key() is vector.by_retrieval_key()
    assert bm25.by_retrieval_key() is bm25.by_retrieval_key()
    assert "_by_retrieval_key" not in chunks.model_dump()


def test_bm25_query_uses_raw_query_and_identifier_plan_parts_only() -> None:
    plan = QueryPlan(
        intent="Expanded intent with many broad words",
        high_level_concepts=["very broad concept"],
        low_level_entities=["ActionContext", "flattenRefs"],
        expected_source_areas=["Framework internals"],
        disambiguation_hints=["ignore unrelated"],
        must_include_identifiers=["defineStoreGroup"],
        question_type="search",
    )

    bm25_query = bm25_query_text_for_plan("defineStoreGroup を確認", plan)
    dense_query = dense_query_text_for_plan(
        "defineStoreGroup を確認",
        plan,
        max_chars=500,
    )

    assert "defineStoreGroup" in bm25_query
    assert "ActionContext" in bm25_query
    assert "Expanded intent" not in bm25_query
    assert "very broad concept" not in bm25_query
    assert "Expanded intent" in dense_query


def test_bm25_search_caps_query_terms(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_core_docs(tmp_path)
    source = tmp_path / "docs/spec/runtime.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "# Runtime\n\n"
        "## Notes\n\n"
        "The orchestration layer must pass ActionContext and flattenRefs.\n",
        encoding="utf-8",
    )
    run_cli(request_payload(tmp_path, "ActionContext flattenRefs"))
    bm25 = load_bm25_index(tmp_path / ".spec-grag/graph" / BM25_INDEX_FILENAME)
    metrics: dict[str, object] = {}

    hits = bm25_search(
        bm25,
        " ".join([f"common{index}" for index in range(100)] + ["ActionContext"]),
        limit=4,
        term_limit=8,
        metrics=metrics,
    )

    assert hits
    assert metrics["bm25_query_terms_before_cap"] > metrics["bm25_query_terms"]
    assert metrics["bm25_query_terms"] == 8


def test_bm25_search_prunes_broad_char_candidates_when_identifier_matches() -> None:
    chunks = DocumentChunksSidecar(
        chunks=[
            DocumentChunk(
                chunk_id=f"chunk:{index}",
                document_id="docs/spec/runtime.md",
                chapter_id="docs/spec/runtime.md#runtime",
                section_id=f"docs/spec/runtime.md#section-{index}",
                heading_path=f"Runtime / {index}",
                source_span="1-2",
                source_hash=f"hash:{index}",
                text="設計 詳細 共通 メモ"
                if index
                else "設計 詳細 共通 ActionContext handles signals",
                chunk_hash=f"chunk-hash:{index}",
                generated_at="t1",
            )
            for index in range(4)
        ]
    )
    bm25 = build_bm25_index(chunks)
    metrics: dict[str, object] = {}

    hits = bm25_search(
        bm25,
        "設計 詳細 ActionContext",
        limit=1,
        metrics=metrics,
    )

    assert hits == [("chunk:0", hits[0][1])]
    assert metrics["bm25_candidate_documents_before_strong_prune"] == 4
    assert metrics["bm25_candidate_documents"] == 1
    assert metrics["bm25_candidate_strong_term_pruned"] is True


def test_query_plan_cache_reuses_llm_result(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    class CountingLLM:
        def complete(self, prompt: str, **_kwargs: object) -> object:
            nonlocal calls
            calls += 1

            class Response:
                text = json.dumps(
                    {
                        "intent": "Find source constraints",
                        "high_level_concepts": [],
                        "low_level_entities": ["ActionContext"],
                        "expected_source_areas": [],
                        "disambiguation_hints": [],
                        "must_include_identifiers": ["ActionContext"],
                        "question_type": "search",
                    }
                )

            return Response()

    monkeypatch.setattr(
        "spec_grag.chunk_index.make_query_planner_llm_from_config",
        lambda _config: CountingLLM(),
    )
    config = {
        "query_planner": {
            "provider": "codex",
            "model": "gpt-test",
            "fallback_on_error": False,
            "cache_enabled": True,
            "cache_path": ".spec-grag/cache/query_plan_cache.json",
        }
    }

    first_metrics: dict[str, object] = {}
    second_metrics: dict[str, object] = {}
    first, first_warnings = query_plan_from_config(
        query="ActionContext",
        config=config,
        project_root=tmp_path,
        graph_revision="graph:1",
        metrics=first_metrics,
    )
    second, second_warnings = query_plan_from_config(
        query="ActionContext",
        config=config,
        project_root=tmp_path,
        graph_revision="graph:1",
        metrics=second_metrics,
    )

    assert first == second
    assert first_warnings == []
    assert second_warnings == []
    assert calls == 1
    assert first_metrics["llm_calls"] == 1
    assert second_metrics["llm_calls"] == 0
    assert second_metrics["query_plan_cache_hit"] is True
