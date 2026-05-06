from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from llama_index.core.graph_stores import SimplePropertyGraphStore

from spec_grag.concept_diff import (
    ConceptDiffTaskContext,
    PendingConceptDiff,
    PendingConceptHunk,
    concept_file_hash,
    create_pending_concept_diff,
)
from spec_grag.protocol import Command, ResultEnvelope, ResultStatus, ResultType
from spec_grag.sidecars import (
    UnresolvedRelationEntry,
    UnresolvedRelationReason,
    UnresolvedRelationsSidecar,
    unresolved_relation_id_for,
    write_unresolved_relations_atomic,
)


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
""".strip(),
        encoding="utf-8",
    )


def write_docs(project_root: Path, *, include_core: bool = True) -> Path:
    source = project_root / "docs/spec/auth.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth is required.\n",
        encoding="utf-8",
    )
    if include_core:
        core = project_root / "docs/core"
        core.mkdir(parents=True, exist_ok=True)
        (core / "purpose.md").write_text("# Purpose\nKeep users secure.\n", encoding="utf-8")
        (core / "concept.md").write_text("# Concept\nAuth protects sessions.\n", encoding="utf-8")
    return source


def request_payload(
    project_root: Path,
    command: str,
    *,
    all_sources: bool = False,
    task_prompt: str | None = None,
    explicit_files: list[str] | None = None,
) -> dict:
    return {
        "command": command,
        "project_root": str(project_root),
        "task_prompt": task_prompt,
        "conversation_context": {
            "current_user_message": task_prompt or "Auth Login を見直す",
            "recent_messages": [],
            "working_target": explicit_files[0] if explicit_files else None,
            "explicit_files": explicit_files or [],
        },
        "agent_capabilities": {
            "can_read_source": True,
            "can_answer": command == "spec-realign",
        },
        "options": {
            "all": all_sources,
            "output_format": "json",
        },
    }


def run_cli(payload: dict) -> tuple[int, ResultEnvelope]:
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
    return result.returncode, ResultEnvelope.from_json(result.stdout)


def create_pending_diff(project_root: Path) -> None:
    concept_file = project_root / "docs/core/concept.md"
    diff = PendingConceptDiff(
        diff_id="diff-1",
        base_concept_hash=concept_file_hash(concept_file),
        task_context=ConceptDiffTaskContext(
            command=Command.SPEC_CORE,
            changed_source_section_ids=["docs/spec/auth.md#auth"],
            extract_run_id="run-1",
        ),
        hunks=[
            PendingConceptHunk(
                hunk_id="hunk-1",
                file="docs/core/concept.md",
                old_range="-1,2",
                new_range="+1,2",
                diff_text="@@ -1,2 +1,2 @@\n # Concept\n-Auth protects sessions.\n+Auth protects all sessions.\n",
            )
        ],
    )
    create_pending_concept_diff(project_root / ".spec-grag/pending", diff)


def load_graph(project_root: Path) -> dict:
    store = SimplePropertyGraphStore.from_persist_dir(
        str(project_root / ".spec-grag/graph")
    )
    return store.graph.model_dump()


def test_external_contract_four_main_paths(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = write_docs(tmp_path)

    code, full = run_cli(request_payload(tmp_path, "spec-core", all_sources=True))
    assert code == 0
    assert full.status == ResultStatus.OK
    assert full.result_type == ResultType.CORE_RESULT
    assert full.payload.mode == "full"

    source.write_text(
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth is required and audited.\n",
        encoding="utf-8",
    )
    code, incremental = run_cli(request_payload(tmp_path, "spec-core"))
    assert code == 0
    assert incremental.status == ResultStatus.OK
    assert incremental.result_type == ResultType.CORE_RESULT
    assert incremental.payload.mode == "incremental"
    assert incremental.payload.updated_sources == ["docs/spec/auth.md#auth-login"]

    code, inject = run_cli(
        request_payload(
            tmp_path,
            "spec-inject",
            task_prompt="Auth Login を見直す",
            explicit_files=["docs/spec/auth.md"],
        )
    )
    assert code == 0
    assert inject.status == ResultStatus.OK
    assert inject.result_type == ResultType.INJECTION_CONTEXT
    assert inject.execution.context_ready is True
    assert inject.payload.constraint_context.purpose_constraints
    assert inject.payload.target_context.related_source_sections

    code, realign = run_cli(
        request_payload(
            tmp_path,
            "spec-realign",
            task_prompt="Auth Login を安全に見直す",
            explicit_files=["docs/spec/auth.md"],
        )
    )
    assert code == 0
    assert realign.status == ResultStatus.OK
    assert realign.result_type == ResultType.REALIGN_RESULT
    assert realign.execution.context_ready is True
    assert realign.payload.task_prompt == "Auth Login を安全に見直す"
    assert realign.payload.injection_context.target_context.related_source_sections
    assert "今回の回答で守る制約" in realign.payload.answer


def test_external_contract_degraded_blocked_and_failed_cases(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_docs(tmp_path, include_core=False)

    code, degraded = run_cli(
        request_payload(
            tmp_path,
            "spec-inject",
            task_prompt="Auth Login を見直す",
            explicit_files=["docs/spec/auth.md"],
        )
    )
    assert code == 0
    assert degraded.status == ResultStatus.DEGRADED
    assert degraded.result_type == ResultType.INJECTION_CONTEXT
    assert "purpose_file_missing" in degraded.warnings
    assert "concept_file_missing" in degraded.warnings

    core = tmp_path / "docs/core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "purpose.md").write_text("# Purpose\nKeep users secure.\n", encoding="utf-8")
    (core / "concept.md").write_text("# Concept\nAuth protects sessions.\n", encoding="utf-8")
    create_pending_diff(tmp_path)
    code, blocked = run_cli(request_payload(tmp_path, "spec-realign", task_prompt="Auth"))
    assert code == 0
    assert blocked.status == ResultStatus.BLOCKED
    assert blocked.result_type == ResultType.CONCEPT_APPROVAL_REQUIRED_RESULT
    assert blocked.execution.context_ready is False

    missing_project = tmp_path / "missing-config"
    missing_project.mkdir()
    code, failed = run_cli(request_payload(missing_project, "spec-core"))
    assert code == 1
    assert failed.status == ResultStatus.FAILED
    assert failed.result_type == ResultType.ERROR_RESULT


def test_external_contract_stale_relations_are_removed_after_section_delete(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    source = write_docs(tmp_path)
    run_cli(request_payload(tmp_path, "spec-core", all_sources=True))
    before = load_graph(tmp_path)
    assert "anchor:docs/spec/auth.md#auth-login:login" in before["nodes"]

    source.write_text("# Auth\n\nIntro.\n", encoding="utf-8")
    code, envelope = run_cli(request_payload(tmp_path, "spec-core"))
    assert code == 0
    assert envelope.status == ResultStatus.OK

    after = load_graph(tmp_path)
    assert "anchor:docs/spec/auth.md#auth-login:login" not in after["nodes"]
    assert all(
        "docs/spec/auth.md#auth-login" not in json.dumps(relation, ensure_ascii=False)
        for relation in after["relations"].values()
    )


def test_external_contract_unresolved_relation_stays_sidecar_only(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    run_cli(request_payload(tmp_path, "spec-core", all_sources=True))
    graph_dir = tmp_path / ".spec-grag/graph"
    relation_id = unresolved_relation_id_for(
        source_id="section:docs/spec/auth.md#auth-login",
        relation_type="DEPENDS_ON",
        target_hint="Billing",
        source_section_id="docs/spec/auth.md#auth-login",
        extract_run_id="run-1",
    )
    unresolved = UnresolvedRelationsSidecar(
        graph_revision="test",
        generated_at="t1",
        entries=[
            UnresolvedRelationEntry(
                unresolved_relation_id=relation_id,
                source_document_id="docs/spec/auth.md",
                source_chapter_id="docs/spec/auth.md#auth",
                source_section_id="docs/spec/auth.md#auth-login",
                source_chunk_id="docs/spec/auth.md#auth-login",
                source_hash="hash",
                extract_run_id="run-1",
                source_id="section:docs/spec/auth.md#auth-login",
                relation_type="DEPENDS_ON",
                target_hint="Billing",
                reason=UnresolvedRelationReason.MISSING_TARGET,
            )
        ],
    )
    write_unresolved_relations_atomic(graph_dir / "unresolved_relations.json", unresolved)

    code, inject = run_cli(
        request_payload(
            tmp_path,
            "spec-inject",
            task_prompt="Auth Login を見直す",
            explicit_files=["docs/spec/auth.md"],
        )
    )
    assert code == 0
    graph = load_graph(tmp_path)
    assert all(
        "Billing" not in json.dumps(relation, ensure_ascii=False)
        for relation in graph["relations"].values()
    )
    assert any(
        note.get("unresolved_relation_id") == relation_id
        for note in inject.payload.review_notes
    )


def test_external_contract_pending_concept_diff_blocks_context_and_answer(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    create_pending_diff(tmp_path)

    code, inject = run_cli(request_payload(tmp_path, "spec-inject", task_prompt="Auth"))
    assert code == 0
    assert inject.status == ResultStatus.BLOCKED
    assert inject.result_type != ResultType.INJECTION_CONTEXT

    code, realign = run_cli(request_payload(tmp_path, "spec-realign", task_prompt="Auth"))
    assert code == 0
    assert realign.status == ResultStatus.BLOCKED
    assert realign.result_type != ResultType.REALIGN_RESULT
