from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from spec_grag.config import validate_project_config
from spec_grag.protocol import ResultEnvelope, ResultType, SlashCommandRequest
from spec_grag.slash import build_payload, parse_args
from spec_grag.template_resources import packaged_template_files, project_template_root


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        args,
        cwd=cwd or REPO_ROOT,
        env=command_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_template_config_matches_current_schema() -> None:
    config_path = REPO_ROOT / "templates/.spec-grag/config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    validated = validate_project_config(config)

    assert validated["sources"]["include"] == ["docs/spec/**/*.md"]
    assert "profile" not in validated
    assert validated["core"]["extraction_mode"] == "schema_llm"
    assert validated["llm"]["provider"] == "codex_cli"
    assert validated["llm"]["codex_cli"]["command"] == "codex"
    assert validated["llm"]["codex_cli"]["model"] == "gpt-5.4"
    assert validated["llm"]["codex_cli"]["effort"] == "low"
    assert validated["llm"]["claude_cli"]["model"] == "claude-sonnet-4-6"
    assert validated["llm"]["claude_cli"]["effort"] == "low"
    assert validated["extraction"]["mode"] == "schema_llm"
    assert validated["extraction"]["provider"] == "codex"
    assert validated["extraction"]["command"] == "codex"
    assert validated["extraction"]["model"] == "gpt-5.4-mini"
    assert validated["extraction"]["effort"] == "low"
    assert validated["extraction"]["batch_size"] == 6
    assert validated["extraction"]["batch_max_chars"] == 4000
    assert validated["extraction"]["section_max_heading_level"] == 4
    assert validated["extraction"]["claude"]["model"] == "claude-haiku-4-5"
    assert validated["answer"]["provider"] == "codex"
    assert validated["answer"]["command"] == "codex"
    assert validated["answer"]["model"] == "gpt-5.4"
    assert validated["answer"]["effort"] == "low"
    assert validated["answer"]["failure_fallback"] == "failed"
    assert validated["classification"]["provider"] == "codex"
    assert validated["classification"]["command"] == "codex"
    assert validated["classification"]["model"] == "gpt-5.4"
    assert validated["classification"]["effort"] == "low"
    assert validated["classification"]["fallback_on_error"] is False
    assert validated["concept_diff"]["provider"] == "codex"
    assert validated["concept_diff"]["command"] == "codex"
    assert validated["concept_diff"]["model"] == "gpt-5.4"
    assert validated["concept_diff"]["effort"] == "low"
    assert validated["concept_diff"]["fallback_on_error"] is False
    assert validated["community_report"]["provider"] == "codex"
    assert validated["community_report"]["command"] == "codex"
    assert validated["community_report"]["model"] == "gpt-5.4"
    assert validated["community_report"]["effort"] == "low"
    assert validated["community_report"]["fallback_on_error"] is False
    assert validated["query_planner"]["provider"] == "codex"
    assert validated["query_planner"]["command"] == "codex"
    assert validated["query_planner"]["model"] == "gpt-5.4"
    assert validated["query_planner"]["effort"] == "low"
    assert validated["query_planner"]["fallback_on_error"] is False
    assert validated["embedding"]["provider"] == "ollama"


def test_codex_command_templates_are_present_and_not_git_ignored() -> None:
    commands = {
        "spec-core": REPO_ROOT / "templates/.codex/commands/spec-core.md",
        "spec-inject": REPO_ROOT / "templates/.codex/commands/spec-inject.md",
        "spec-realign": REPO_ROOT / "templates/.codex/commands/spec-realign.md",
    }

    for command, path in commands.items():
        text = path.read_text(encoding="utf-8")
        assert command in text
        assert "spec-grag-slash" in text
        assert "python3 -m spec_grag.slash" in text
        ignored = run_command(["git", "check-ignore", "-q", str(path.relative_to(REPO_ROOT))])
        assert ignored.returncode == 1


def test_template_resources_are_packaged_for_wheel_install() -> None:
    expected = {
        ".spec-grag/.gitignore",
        ".spec-grag/README.md",
        ".spec-grag/config.toml",
        ".codex/commands/spec-core.md",
        ".codex/commands/spec-inject.md",
        ".codex/commands/spec-realign.md",
    }

    assert set(packaged_template_files()) == expected
    with project_template_root(None) as resource_root:
        for relative in expected:
            packaged = resource_root / relative
            active = REPO_ROOT / "templates" / relative
            assert packaged.read_text(encoding="utf-8") == active.read_text(encoding="utf-8")


def test_packaged_project_setup_module_installs_templates(tmp_path: Path) -> None:
    result = run_command(
        [
            sys.executable,
            "-m",
            "spec_grag.project_setup",
            "--target",
            str(tmp_path),
            "--create-example-spec",
            "--json",
        ]
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["ok"] is True
    assert (tmp_path / ".spec-grag/config.toml").exists()
    assert (tmp_path / ".codex/commands/spec-core.md").exists()


def test_slash_wrapper_builds_concept_diff_revision_payload() -> None:
    args = parse_args(["spec-core", "--revise", "diff-1:hunk-1", "make it narrower"])

    payload = build_payload(args)
    request = SlashCommandRequest.model_validate(payload)

    assert request.command == "spec-core"
    assert request.options.revise == "diff-1:hunk-1"
    assert request.options.revision_instruction == "make it narrower"
    assert request.task_prompt is None


def test_slash_wrapper_builds_structured_approval_payload() -> None:
    approval = json.dumps(
        {
            "subject": "concept_diff",
            "action": "accept",
            "diff_id": "diff-1",
            "hunk_id": "hunk-1",
            "apply": True,
        }
    )
    args = parse_args(["spec-core", "--approval-json", approval])

    payload = build_payload(args)
    request = SlashCommandRequest.model_validate(payload)

    assert request.options.approval is not None
    assert request.options.approval.subject == "concept_diff"
    assert request.options.approval.apply is True


def test_slash_script_print_request_uses_current_transport_schema(tmp_path: Path) -> None:
    result = run_command(
        [
            sys.executable,
            "scripts/spec-grag-slash.py",
            "spec-realign",
            "review auth",
            "--project-root",
            str(tmp_path),
            "--print-request",
        ]
    )

    assert result.returncode == 0, result.stderr
    request = SlashCommandRequest.model_validate_json(result.stdout)
    assert request.command == "spec-realign"
    assert request.task_prompt == "review auth"


def test_project_setup_dry_run_does_not_write_files(tmp_path: Path) -> None:
    result = run_command(
        [
            sys.executable,
            "scripts/setup_project.py",
            "--target",
            str(tmp_path),
            "--dry-run",
            "--json",
        ]
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert not (tmp_path / ".spec-grag").exists()
    assert any(action["action"] == "would-create" for action in summary["actions"])


def test_project_setup_installs_templates_and_protects_existing_files(tmp_path: Path) -> None:
    result = run_command(
        [
            sys.executable,
            "scripts/setup_project.py",
            "--target",
            str(tmp_path),
            "--create-example-spec",
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr

    required = [
        ".spec-grag/config.toml",
        ".spec-grag/.gitignore",
        ".codex/commands/spec-core.md",
        ".codex/commands/spec-inject.md",
        ".codex/commands/spec-realign.md",
        "docs/core/purpose.md",
        "docs/core/concept.md",
        "docs/spec/example.md",
    ]
    for relative in required:
        assert (tmp_path / relative).exists()

    config_path = tmp_path / ".spec-grag/config.toml"
    config = validate_project_config(tomllib.loads(config_path.read_text(encoding="utf-8")))
    assert "profile" not in config
    assert config["llm"]["provider"] == "codex_cli"
    assert config["llm"]["codex_cli"]["effort"] == "low"
    assert config["llm"]["claude_cli"]["effort"] == "low"
    assert config["embedding"]["provider"] == "ollama"
    assert config["answer"]["provider"] == "codex"
    assert config["answer"]["effort"] == "low"
    assert config["watcher"]["enabled"] is True
    assert config["watcher"]["debounce_ms"] == 500
    assert config["watcher"]["state_file"] == ".spec-grag/state/watch_state.json"

    config_path.write_text("[sources]\ninclude = [\"changed.md\"]\n", encoding="utf-8")
    conflict = run_command(
        [
            sys.executable,
            "scripts/setup_project.py",
            "--target",
            str(tmp_path),
            "--json",
        ]
    )
    assert conflict.returncode == 1
    conflict_summary = json.loads(conflict.stdout)
    assert conflict_summary["conflicts"][0]["path"] == ".spec-grag/config.toml"

    backup = run_command(
        [
            sys.executable,
            "scripts/setup_project.py",
            "--target",
            str(tmp_path),
            "--backup",
            "--json",
        ]
    )
    assert backup.returncode == 0, backup.stderr
    assert (tmp_path / ".spec-grag/config.toml.bak").exists()
    validate_project_config(tomllib.loads(config_path.read_text(encoding="utf-8")))


def test_system_setup_check_only_returns_stable_json() -> None:
    result = run_command(
        [
            sys.executable,
            "scripts/setup_system.py",
            "--check-only",
            "--json",
        ]
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["ok"] is True
    assert summary["check_only"] is True
    assert summary["checks"]["python"]["ok"] is True
    assert summary["checks"]["python_module_cli"] is True
    assert summary["checks"]["python_module_slash"] is True


def test_system_setup_archive_dry_run_does_not_write(tmp_path: Path) -> None:
    archive_path = tmp_path / "bundle.tar.gz"

    result = run_command(
        [
            sys.executable,
            "scripts/setup_system.py",
            "--mode",
            "archive",
            "--archive-path",
            str(archive_path),
            "--dry-run",
            "--json",
        ]
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["actions"][0]["label"] == "archive"
    assert summary["actions"][0]["dry_run"] is True
    assert not archive_path.exists()


def test_fresh_project_setup_smoke_runs_core_inject_and_realign(tmp_path: Path) -> None:
    setup = run_command(
        [
            sys.executable,
            "scripts/setup_project.py",
            "--target",
            str(tmp_path),
            "--create-example-spec",
            "--smoke",
            "--json",
        ]
    )
    assert setup.returncode == 0, setup.stderr
    setup_summary = json.loads(setup.stdout)
    assert setup_summary["smoke"] is True
    config = validate_project_config(
        tomllib.loads((tmp_path / ".spec-grag/config.toml").read_text(encoding="utf-8")),
        smoke=True,
    )
    assert "profile" not in config
    assert "llm" not in config
    assert config["embedding"]["provider"] == "stable_hash"
    assert config["answer"]["provider"] == "template"

    core = run_command(
        [
            sys.executable,
            "-m",
            "spec_grag.slash",
            "spec-core",
            "--project-root",
            str(tmp_path),
            "--all",
        ],
        env={"SPEC_GRAG_SMOKE": "1"},
    )
    assert core.returncode == 0, core.stderr
    core_envelope = ResultEnvelope.from_json(core.stdout)
    assert core_envelope.result_type == ResultType.CORE_RESULT

    inject = run_command(
        [
            sys.executable,
            "-m",
            "spec_grag.slash",
            "spec-inject",
            "keep specs aligned",
            "--project-root",
            str(tmp_path),
        ],
        env={"SPEC_GRAG_SMOKE": "1"},
    )
    assert inject.returncode == 0, inject.stderr
    inject_envelope = ResultEnvelope.from_json(inject.stdout)
    assert inject_envelope.result_type == ResultType.INJECTION_CONTEXT

    realign = run_command(
        [
            sys.executable,
            "-m",
            "spec_grag.slash",
            "spec-realign",
            "How should we keep specs aligned?",
            "--project-root",
            str(tmp_path),
        ],
        env={"SPEC_GRAG_SMOKE": "1"},
    )
    assert realign.returncode == 0, realign.stderr
    realign_envelope = ResultEnvelope.from_json(realign.stdout)
    assert realign_envelope.result_type == ResultType.REALIGN_RESULT
