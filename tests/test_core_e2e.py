from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from spec_grag.concept_diff import (
    ConceptDiffTaskContext,
    PendingConceptDiff,
    PendingConceptHunk,
    concept_file_hash,
    create_pending_concept_diff,
)
from spec_grag.embedding import load_embedding_metadata
from spec_grag.manifest import load_source_manifest
from spec_grag.protocol import Command, ResultEnvelope, ResultStatus, ResultType
from spec_grag.sidecars import load_chapter_anchors, load_cluster_snapshot


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


def request_json(project_root: Path, *, all_sources: bool = False) -> str:
    return json.dumps(
        {
            "command": "spec-core",
            "project_root": str(project_root),
            "conversation_context": {
                "current_user_message": "core update",
                "recent_messages": [],
                "explicit_files": [],
            },
            "agent_capabilities": {
                "can_read_source": True,
                "can_answer": False,
            },
            "options": {
                "all": all_sources,
                "output_format": "json",
            },
        }
    )


def run_cli(stdin_json: str) -> ResultEnvelope:
    result = subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=stdin_json,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return ResultEnvelope.from_json(result.stdout)


def write_auth_source(project_root: Path, text: str) -> Path:
    path = project_root / "docs/spec/auth.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_spec_core_all_generates_manifest_graph_vector_and_sidecars(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_auth_source(
        tmp_path,
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth is optional.\n\n## Logout\n\nClear session.\n",
    )

    envelope = run_cli(request_json(tmp_path, all_sources=True))

    graph_dir = tmp_path / ".spec-grag/graph"
    manifest = load_source_manifest(graph_dir / "source_manifest.json")
    anchors = load_chapter_anchors(graph_dir / "chapter_anchors.json")
    clusters = load_cluster_snapshot(graph_dir / "cluster_snapshot.json")

    assert envelope.status == ResultStatus.OK
    assert envelope.result_type == ResultType.CORE_RESULT
    assert envelope.payload.mode == "full"
    assert envelope.payload.updated_sources == ["docs/spec/auth.md"]
    assert {entry.section_id for entry in manifest.entries} == {
        "docs/spec/auth.md#auth",
        "docs/spec/auth.md#auth-login",
        "docs/spec/auth.md#auth-logout",
    }
    assert (graph_dir / "property_graph_store.json").exists()
    assert (graph_dir / "vector_store.json").exists()
    assert (graph_dir / "embedding_metadata.json").exists()
    embedding_metadata = load_embedding_metadata(graph_dir / "embedding_metadata.json")
    assert embedding_metadata is not None
    assert embedding_metadata.provider == "stable_hash"
    assert embedding_metadata.dimension == 8
    assert anchors.anchors[0].quality.stale is False
    assert clusters.graph_revision == envelope.payload.freshness_report.graph_revision


def test_spec_core_incremental_body_change_updates_only_changed_section(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    source = write_auth_source(
        tmp_path,
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth is optional.\n",
    )
    run_cli(request_json(tmp_path, all_sources=True))
    before = load_source_manifest(tmp_path / ".spec-grag/graph/source_manifest.json")

    source.write_text(
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth is required.\n",
        encoding="utf-8",
    )
    envelope = run_cli(request_json(tmp_path))
    after = load_source_manifest(tmp_path / ".spec-grag/graph/source_manifest.json")

    assert envelope.status == ResultStatus.OK
    assert envelope.payload.mode == "incremental"
    assert envelope.payload.updated_sources == ["docs/spec/auth.md#auth-login"]
    assert (
        before.by_section_id()["docs/spec/auth.md#auth-login"].source_hash
        != after.by_section_id()["docs/spec/auth.md#auth-login"].source_hash
    )
    assert (
        before.by_section_id()["docs/spec/auth.md#auth"].source_hash
        == after.by_section_id()["docs/spec/auth.md#auth"].source_hash
    )


def test_spec_core_incremental_section_delete_and_rename(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = write_auth_source(
        tmp_path,
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth.\n\n## Logout\n\nClear session.\n",
    )
    run_cli(request_json(tmp_path, all_sources=True))

    source.write_text(
        "# Auth\n\nIntro.\n\n## Authentication\n\nOAuth.\n",
        encoding="utf-8",
    )
    envelope = run_cli(request_json(tmp_path))
    manifest = load_source_manifest(tmp_path / ".spec-grag/graph/source_manifest.json")

    assert envelope.status == ResultStatus.OK
    assert envelope.payload.updated_sources == [
        "docs/spec/auth.md#auth-authentication",
        "docs/spec/auth.md#auth-login",
        "docs/spec/auth.md#auth-logout",
    ]
    assert "docs/spec/auth.md#auth-authentication" in manifest.by_section_id()
    assert "docs/spec/auth.md#auth-login" not in manifest.by_section_id()
    assert "docs/spec/auth.md#auth-logout" not in manifest.by_section_id()


def test_spec_core_incremental_requires_rebuild_when_embedding_metadata_changes(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    source = write_auth_source(tmp_path, "# Auth\n\nIntro.\n")
    run_cli(request_json(tmp_path, all_sources=True))
    config_path = tmp_path / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + """

[embedding]
provider = "stable_hash"
model = "sha256-v2"
dimension = 12
""",
        encoding="utf-8",
    )
    source.write_text("# Auth\n\nChanged intro.\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=request_json(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT
    assert "embedding_metadata_mismatch" in envelope.payload.details["warnings"][0]


def test_spec_core_incremental_split_and_merge(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = write_auth_source(
        tmp_path,
        "# Auth\n\n## Session\n\nOAuth and cleanup.\n",
    )
    run_cli(request_json(tmp_path, all_sources=True))

    source.write_text(
        "# Auth\n\n## Login\n\nOAuth.\n\n## Logout\n\nClear session.\n",
        encoding="utf-8",
    )
    split = run_cli(request_json(tmp_path))
    assert split.status == ResultStatus.OK
    assert split.payload.updated_sources == [
        "docs/spec/auth.md#auth-login",
        "docs/spec/auth.md#auth-logout",
        "docs/spec/auth.md#auth-session",
    ]

    source.write_text(
        "# Auth\n\n## Session\n\nOAuth and cleanup.\n",
        encoding="utf-8",
    )
    merged = run_cli(request_json(tmp_path))
    assert merged.status == ResultStatus.OK
    assert merged.payload.updated_sources == [
        "docs/spec/auth.md#auth-login",
        "docs/spec/auth.md#auth-logout",
        "docs/spec/auth.md#auth-session",
    ]


def test_spec_core_blocks_when_pending_concept_diff_exists(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_auth_source(tmp_path, "# Auth\n\nIntro.\n")
    concept_file = tmp_path / "docs/core/concept.md"
    concept_file.parent.mkdir(parents=True, exist_ok=True)
    concept_file.write_text("# Concept\nAuth is optional.\n", encoding="utf-8")
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
                diff_text="@@ -1,2 +1,2 @@\n # Concept\n-Auth is optional.\n+Auth is required.\n",
            )
        ],
    )
    create_pending_concept_diff(tmp_path / ".spec-grag/pending", diff)

    envelope = run_cli(request_json(tmp_path))

    assert envelope.status == ResultStatus.BLOCKED
    assert envelope.result_type == ResultType.CONCEPT_APPROVAL_REQUIRED_RESULT
    assert envelope.execution.pending_concept_diff_id == "diff-1"
