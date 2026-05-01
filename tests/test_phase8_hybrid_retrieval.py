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
    analyze_text,
    document_chunks_path,
    load_document_chunks,
    validate_chunk_source,
)
from spec_grag.protocol import ResultEnvelope, ResultStatus, ResultType


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
    assert chunks.chunks
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
