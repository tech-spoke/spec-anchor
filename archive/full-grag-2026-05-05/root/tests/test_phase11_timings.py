from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from llama_index.core.schema import TextNode

from spec_grag.core import run_core_update
from spec_grag.protocol import ResultEnvelope, ResultStatus, ResultType


def write_config(project_root: Path, *, runtime_mode: str | None = None) -> None:
    config_dir = project_root / ".spec-grag"
    config_dir.mkdir(parents=True, exist_ok=True)
    runtime = f'\n\n[runtime]\nmode = "{runtime_mode}"\n' if runtime_mode else ""
    (config_dir / "config.toml").write_text(
        (
            """
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[graph]
storage = ".spec-grag/graph/"

[embedding]
provider = "stable_hash"
model = "sha256-v1"
dimension = 8

[run]
save_artifacts = true
artifact_dir = ".spec-grag/runs"
""".strip()
            + runtime
        ),
        encoding="utf-8",
    )


def write_docs(project_root: Path, source_text: str = "OAuth is optional.") -> Path:
    source = project_root / "docs/spec/auth.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(f"# Auth\n\n## Login\n\n{source_text}\n", encoding="utf-8")
    core = project_root / "docs/core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "purpose.md").write_text("# Purpose\nKeep sessions secure.\n", encoding="utf-8")
    (core / "concept.md").write_text("# Concept\nAuth protects sessions.\n", encoding="utf-8")
    return source


def request_payload(project_root: Path, command: str, *, all_sources: bool = False) -> dict[str, Any]:
    return {
        "command": command,
        "project_root": str(project_root),
        "task_prompt": "Auth Login を見直す" if command == "spec-realign" else None,
        "conversation_context": {
            "current_user_message": "Auth Login を見直す",
            "recent_messages": [],
            "working_target": "docs/spec/auth.md",
            "explicit_files": ["docs/spec/auth.md"],
        },
        "agentic_search_candidates": [],
        "agent_capabilities": {
            "can_read_source": True,
            "can_answer": command == "spec-realign",
        },
        "options": {"all": all_sources, "output_format": "json"},
    }


def run_cli(payload: dict[str, Any], *, smoke: bool = True) -> tuple[int, ResultEnvelope]:
    env = os.environ.copy()
    if smoke:
        env["SPEC_GRAG_SMOKE"] = "1"
    else:
        env.pop("SPEC_GRAG_SMOKE", None)
        env.pop("SPEC_GRAG_RUNTIME_MODE", None)
    result = subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=json.dumps(payload),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode, ResultEnvelope.from_json(result.stdout)


def latest_artifact(project_root: Path, command: str) -> dict[str, Any]:
    paths = sorted((project_root / ".spec-grag/runs").glob(f"*-{command}-*.json"))
    assert paths
    return json.loads(paths[-1].read_text(encoding="utf-8"))


def stage_names(data: dict[str, Any]) -> set[str]:
    return {stage["stage"] for stage in data["stage_timings"]}


def test_no_change_spec_core_artifact_records_fast_path_timings(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    code, first = run_cli(request_payload(tmp_path, "spec-core", all_sources=True))
    assert code == 0
    assert first.status == ResultStatus.OK

    code, second = run_cli(request_payload(tmp_path, "spec-core"))
    assert code == 0
    assert second.status == ResultStatus.OK
    data = latest_artifact(tmp_path, "spec-core")

    assert data["timing_summary"]["semantic_noop"] is True
    assert data["timing_summary"]["heavy_path"] is False
    assert data["execution"]["timing_summary"] == data["timing_summary"]
    assert {"manifest_reconcile", "semantic_noop_filter", "artifact_write"} <= stage_names(data)
    timing_json = json.dumps(
        {"timing_summary": data["timing_summary"], "stage_timings": data["stage_timings"]},
        ensure_ascii=False,
    )
    assert "OAuth is optional." not in timing_json
    assert "INPUT_JSON" not in timing_json


def test_format_only_spec_core_artifact_does_not_run_schema_llm(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = write_docs(tmp_path)
    run_cli(request_payload(tmp_path, "spec-core", all_sources=True))
    source.write_text("# Auth\n\n## Login\n\nOAuth is optional.  \n\n\n", encoding="utf-8")

    code, envelope = run_cli(request_payload(tmp_path, "spec-core"))
    assert code == 0
    assert envelope.status == ResultStatus.OK
    data = latest_artifact(tmp_path, "spec-core")

    assert data["timing_summary"]["semantic_noop"] is True
    assert data["timing_summary"]["heavy_path"] is False
    assert "schema_llm_extraction" not in stage_names(data)


def test_semantic_change_and_schema_extraction_timings_are_recorded(tmp_path: Path) -> None:
    source = write_docs(tmp_path)
    config = {
        "sources": {"include": ["docs/spec/**/*.md"]},
        "core": {
            "concept_file": "docs/core/concept.md",
            "extraction_mode": "schema_llm",
        },
        "extraction": {"mode": "schema_llm"},
        "graph": {"storage": ".spec-grag/graph/"},
        "embedding": {"provider": "stable_hash", "model": "sha256-v1", "dimension": 8},
    }

    class EmptySchemaExtractor:
        def __call__(self, nodes: list[TextNode], show_progress: bool = False, **_kwargs: Any) -> list[TextNode]:
            return nodes

    first = run_core_update(tmp_path, config, all_sources=True, schema_extractor=EmptySchemaExtractor())
    assert first.status == ResultStatus.OK
    source.write_text("# Auth\n\n## Login\n\nOAuth is required.\n", encoding="utf-8")

    second = run_core_update(tmp_path, config, all_sources=False, schema_extractor=EmptySchemaExtractor())
    names = {stage["stage"] for stage in second.stage_timings}
    staging_stage = next(
        stage
        for stage in second.stage_timings
        if stage["stage"] == "artifact_write"
        and stage["metrics"].get("operation") == "prepare"
    )

    assert second.timing_summary["semantic_noop"] is False
    assert second.timing_summary["heavy_path"] is True
    assert {"schema_llm_extraction", "embedding_update"} <= names
    assert staging_stage["metrics"]["active_exists"] is True
    assert staging_stage["metrics"]["staging_exists"] is True
    assert staging_stage["metrics"]["staging_file_count"] >= 1


def test_blocked_and_failed_artifacts_keep_completed_timings(tmp_path: Path) -> None:
    write_config(tmp_path, runtime_mode="local_daily")
    source = write_docs(tmp_path)
    code, first = run_cli(request_payload(tmp_path, "spec-core", all_sources=True))
    assert code == 0
    assert first.status == ResultStatus.OK

    source.write_text("# Auth\n\n## Login\n\nOAuth is required.\n", encoding="utf-8")
    code, blocked = run_cli(request_payload(tmp_path, "spec-inject"))
    assert code == 0
    assert blocked.status == ResultStatus.BLOCKED
    blocked_artifact = latest_artifact(tmp_path, "spec-inject")
    assert blocked_artifact["status"] == "blocked"
    assert any(
        stage["stage"] == "readiness_gate" and stage["status"] == "blocked"
        for stage in blocked_artifact["stage_timings"]
    )

    config_path = tmp_path / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("dimension = 8", "dimension = 9"),
        encoding="utf-8",
    )
    code, failed = run_cli(request_payload(tmp_path, "spec-core"))
    assert code == 1
    assert failed.status == ResultStatus.FAILED
    failed_artifact = latest_artifact(tmp_path, "spec-core")
    assert failed_artifact["status"] == "failed"
    assert any(
        stage["stage"] == "embedding_update" and stage["status"] == "failed"
        for stage in failed_artifact["stage_timings"]
    )
