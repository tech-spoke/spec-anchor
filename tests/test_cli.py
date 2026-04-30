from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from spec_grag.concept_index import load_concept_index
from spec_grag.concept_diff import (
    ConceptDiffTaskContext,
    HunkStatus,
    PendingConceptDiff,
    PendingConceptHunk,
    concept_file_hash,
    create_pending_concept_diff,
    load_pending_concept_diff,
    pending_concept_diff_path,
)
from spec_grag.protocol import Command
from spec_grag.protocol import ResultEnvelope, ResultStatus, ResultType


def write_config(project_root: Path) -> None:
    config_dir = project_root / ".spec-grag"
    config_dir.mkdir()
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


def write_source_specs(project_root: Path) -> None:
    source_dir = project_root / "docs/spec"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "auth.md").write_text(
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth is optional.\n",
        encoding="utf-8",
    )


def request_json(project_root: Path, command: str = "spec-inject") -> str:
    payload = {
        "command": command,
        "project_root": str(project_root),
        "task_prompt": "認証仕様を見直す" if command == "spec-realign" else None,
        "conversation_context": {
            "current_user_message": "認証仕様を見直したい",
            "recent_messages": [],
            "working_target": "docs/spec/auth.md",
            "explicit_files": ["docs/spec/auth.md"],
        },
        "agent_capabilities": {
            "can_read_source": True,
            "can_answer": True,
        },
        "options": {
            "output_format": "json",
        },
    }
    return json.dumps(payload)


def run_cli(stdin_json: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=stdin_json,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_stdin_stdout_roundtrip_for_spec_inject(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_source_specs(tmp_path)

    result = run_cli(request_json(tmp_path, "spec-inject"))

    assert result.returncode == 0
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.DEGRADED
    assert envelope.result_type == ResultType.INJECTION_CONTEXT
    assert envelope.execution.context_ready is True


def test_cli_missing_config_returns_failed_error(tmp_path: Path) -> None:
    result = run_cli(request_json(tmp_path, "spec-core"))

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT


def test_cli_spec_core_all_uses_full_mode(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_source_specs(tmp_path)
    payload = json.loads(request_json(tmp_path, "spec-core"))
    payload["options"]["all"] = True

    result = run_cli(json.dumps(payload))

    assert result.returncode == 0
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.OK
    assert envelope.result_type == ResultType.CORE_RESULT
    assert envelope.payload.mode == "full"
    assert (tmp_path / ".spec-grag/graph/source_manifest.json").exists()
    assert (tmp_path / ".spec-grag/graph/property_graph_store.json").exists()
    assert (tmp_path / ".spec-grag/graph/vector_store.json").exists()
    assert (tmp_path / ".spec-grag/graph/chapter_anchors.json").exists()
    assert (tmp_path / ".spec-grag/graph/cluster_snapshot.json").exists()


def test_cli_spec_realign_requires_task_prompt(tmp_path: Path) -> None:
    write_config(tmp_path)
    payload = json.loads(request_json(tmp_path, "spec-realign"))
    payload["task_prompt"] = None

    result = run_cli(json.dumps(payload))

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT


def test_cli_spec_realign_invalid_answer_provider_fails_before_answer(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    write_source_specs(tmp_path)
    config_path = tmp_path / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + '\n\n[answer]\nprovider = "unknown"\n',
        encoding="utf-8",
    )

    result = run_cli(request_json(tmp_path, "spec-realign"))

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT
    assert envelope.payload.error_code == "config_invalid"


def test_cli_config_rejects_unknown_top_level_table(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_source_specs(tmp_path)
    config_path = tmp_path / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n\n[unexpected]\nvalue = true\n",
        encoding="utf-8",
    )

    result = run_cli(request_json(tmp_path, "spec-core"))

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT
    assert envelope.payload.error_code == "config_invalid"
    assert envelope.payload.details["errors"][0]["loc"] == ["unexpected"]


def test_cli_config_rejects_invalid_source_include_type(tmp_path: Path) -> None:
    config_dir = tmp_path / ".spec-grag"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
[sources]
include = 1
""".strip(),
        encoding="utf-8",
    )

    result = run_cli(request_json(tmp_path, "spec-core"))

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT
    assert envelope.payload.error_code == "config_invalid"


def test_cli_config_rejects_invalid_embedding_provider(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_source_specs(tmp_path)
    config_path = tmp_path / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + """

[embedding]
provider = "legacy-english"
model = "nomic-embed-text"
dimension = 768
""",
        encoding="utf-8",
    )

    result = run_cli(request_json(tmp_path, "spec-core"))

    assert result.returncode == 1
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT
    assert envelope.payload.error_code == "config_invalid"


def test_cli_writes_run_artifact_when_enabled(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_source_specs(tmp_path)
    config_path = tmp_path / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + """

[run]
save_artifacts = true
artifact_dir = ".spec-grag/runs"
""",
        encoding="utf-8",
    )

    result = run_cli(request_json(tmp_path, "spec-core"))

    assert result.returncode == 0
    envelope = ResultEnvelope.from_json(result.stdout)
    assert any(warning.startswith("run_artifact:") for warning in envelope.warnings)
    artifacts = list((tmp_path / ".spec-grag/runs").glob("*.json"))
    assert len(artifacts) == 1
    data = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert data["command"] == "spec-core"
    assert data["request"]["project_root"] == str(tmp_path)


def test_cli_answer_failure_can_fallback_to_template(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_source_specs(tmp_path)
    config_path = tmp_path / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + """

[answer]
provider = "codex"
command = "/bin/false"
failure_fallback = "template"
""",
        encoding="utf-8",
    )

    result = run_cli(request_json(tmp_path, "spec-realign"))

    assert result.returncode == 0
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.DEGRADED
    assert envelope.result_type == ResultType.REALIGN_RESULT
    assert "answer_generation_fallback_template" in envelope.warnings
    assert "今回の回答で守る制約" in envelope.payload.answer


def write_concept_and_pending_diff(tmp_path: Path) -> Path:
    concept_file = tmp_path / "docs/core/concept.md"
    concept_file.parent.mkdir(parents=True)
    concept_file.write_text(
        "# Concept\nAuth is optional.\nKeep sessions short.\n",
        encoding="utf-8",
    )
    diff = PendingConceptDiff(
        diff_id="diff-1",
        base_concept_hash=concept_file_hash(concept_file),
        generated_at="2026-04-29T00:00:00+00:00",
        task_context=ConceptDiffTaskContext(
            command=Command.SPEC_CORE,
            changed_source_section_ids=["docs/spec/auth.md#auth"],
            extract_run_id="run-1",
        ),
        hunks=[
            PendingConceptHunk(
                hunk_id="hunk-1",
                file="docs/core/concept.md",
                old_range="-1,3",
                new_range="+1,3",
                diff_text=(
                    "@@ -1,3 +1,3 @@\n"
                    " # Concept\n"
                    "-Auth is optional.\n"
                    "+Auth is required.\n"
                    " Keep sessions short.\n"
                ),
            )
        ],
    )
    return create_pending_concept_diff(tmp_path / ".spec-grag/pending", diff)


def test_cli_spec_core_accept_reject_revise_updates_pending_diff(tmp_path: Path) -> None:
    write_config(tmp_path)
    pending_path = write_concept_and_pending_diff(tmp_path)
    payload = json.loads(request_json(tmp_path, "spec-core"))

    payload["options"]["accept"] = "diff-1:hunk-1"
    accepted = run_cli(json.dumps(payload))
    assert accepted.returncode == 0
    assert load_pending_concept_diff(pending_path).hunks[0].status == HunkStatus.ACCEPTED

    payload["options"] = {"output_format": "json", "reject": "diff-1:hunk-1"}
    rejected = run_cli(json.dumps(payload))
    assert rejected.returncode == 0
    assert load_pending_concept_diff(pending_path).hunks[0].status == HunkStatus.REJECTED

    payload["options"] = {
        "output_format": "json",
        "revise": "diff-1:hunk-1",
        "revision_instruction": "根拠を短くする",
    }
    revised = run_cli(json.dumps(payload))
    assert revised.returncode == 0
    hunk = load_pending_concept_diff(pending_path).hunks[0]
    assert hunk.status == HunkStatus.REVISED
    assert hunk.revision_instruction == "根拠を短くする"


def test_cli_spec_core_apply_updates_concept_and_removes_pending(tmp_path: Path) -> None:
    write_config(tmp_path)
    pending_path = write_concept_and_pending_diff(tmp_path)
    payload = json.loads(request_json(tmp_path, "spec-core"))
    payload["options"]["accept"] = "diff-1:hunk-1"
    run_cli(json.dumps(payload))

    payload["options"] = {"output_format": "json", "apply": "diff-1"}
    result = run_cli(json.dumps(payload))

    assert result.returncode == 0
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.OK
    assert envelope.result_type == ResultType.CORE_RESULT
    assert "Auth is required." in (tmp_path / "docs/core/concept.md").read_text(
        encoding="utf-8"
    )
    concept_index = load_concept_index(tmp_path / ".spec-grag/graph/concept_index.json")
    assert concept_index is not None
    assert "Auth is required." in concept_index.chunk_text()
    assert not pending_path.exists()


def test_cli_spec_core_apply_hash_mismatch_returns_blocked(tmp_path: Path) -> None:
    write_config(tmp_path)
    pending_path = write_concept_and_pending_diff(tmp_path)
    payload = json.loads(request_json(tmp_path, "spec-core"))
    payload["options"]["accept"] = "diff-1:hunk-1"
    run_cli(json.dumps(payload))
    (tmp_path / "docs/core/concept.md").write_text(
        "# Concept\nAuth was manually changed.\nKeep sessions short.\n",
        encoding="utf-8",
    )

    payload["options"] = {"output_format": "json", "apply": "diff-1"}
    result = run_cli(json.dumps(payload))

    assert result.returncode == 0
    envelope = ResultEnvelope.from_json(result.stdout)
    assert envelope.status == ResultStatus.BLOCKED
    assert envelope.result_type == ResultType.CONCEPT_APPROVAL_REQUIRED_RESULT
    assert envelope.execution.pending_concept_diff_id == "diff-1"
    assert pending_path == pending_concept_diff_path(tmp_path / ".spec-grag/pending", "diff-1")
    assert pending_path.exists()
