"""Documentation and release-readiness contract tests for G-16."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
RUNBOOK = REPO_ROOT / "doc" / "RUNBOOK.ja.md"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _project_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) if not pythonpath else f"{REPO_ROOT}{os.pathsep}{pythonpath}"
    )
    return env


def _has_any(text: str, *terms: str) -> bool:
    return any(term in text for term in terms)


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=_project_env(),
        text=True,
        capture_output=True,
        check=False,
    )


def _json_output(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def _base_constraint() -> list[dict[str, object]]:
    return [
        {
            "statement": "Keep the lightweight release smoke path deterministic.",
            "evidence_origin": "Source Specs",
            "evidence_ref": "docs/spec/release.md#rules",
            "support_refs": [
                {
                    "origin": "Section Summary",
                    "ref": "docs/spec/release.md#rules",
                }
            ],
            "applicability": "release smoke",
        }
    ]


def test_t_d01_readme_explains_lightweight_setup_smoke_usage_dev_and_privacy() -> None:
    text = _readme()
    lowered = text.lower()
    runbook = _runbook().lower()

    assert "lightweight" in lowered
    assert "spec-grag" in lowered
    assert "setup" in lowered
    assert "smoke" in lowered
    for command in (
        "spec-grag core",
        "spec-grag inject",
        "spec-grag realign",
        "spec-grag-setup-project",
    ):
        assert command in text
    assert "doc/runbook.ja.md" in lowered
    assert "pytest" in runbook
    assert "local" in runbook
    assert "core concept" in lowered
    assert "never updates" in lowered or "does not update" in lowered
    assert "automatically" in lowered


def test_t_d01_readme_is_not_a_runbook() -> None:
    text = _readme()
    lowered = text.lower()

    assert "doc/runbook.ja.md" in lowered
    for forbidden in (
        "Production Readiness Report Template",
        "本運用 Readiness 報告テンプレート",
        "Do not report",
        "qdrant_schema_mismatch",
        "agent_cli_unauthenticated",
    ):
        assert forbidden not in text


def test_t_d01_readme_does_not_present_full_grag_terms_as_standard_path() -> None:
    lowered = _readme().lower()
    forbidden_standard_path_phrases = (
        "standard path is property graph",
        "standard path: property graph",
        "standard route is property graph",
        "uses property graph as the standard",
        "entity relation graph as the standard",
        "hierarchical cluster as the standard",
    )

    for phrase in forbidden_standard_path_phrases:
        assert phrase not in lowered

    for term in ("property graph", "entity relation graph", "hierarchical cluster"):
        if term in lowered:
            paragraphs = [paragraph for paragraph in lowered.split("\n\n") if term in paragraph]
            assert paragraphs
            assert any(
                (
                    "not part of the standard path" in paragraph
                    or "not the standard" in paragraph
                    or "does not use" in paragraph
                    or "not use" in paragraph
                )
                for paragraph in paragraphs
            )


def test_t_r01_root_source_tests_and_docs_do_not_depend_on_archive_or_doc_new() -> None:
    for source_file in (REPO_ROOT / "spec_grag").glob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            assert not any(name == "archive" or name.startswith("archive.") for name in imported), source_file

    for test_file in (REPO_ROOT / "tests").glob("test_*.py"):
        if test_file == Path(__file__):
            continue
        text = test_file.read_text(encoding="utf-8").lower()
        assert "tests/fixtures/archive" not in text
        assert "tests\\fixtures\\archive" not in text
    assert not (REPO_ROOT / "tests" / "fixtures" / "archive").exists()

    source_of_truth_docs = (
        REPO_ROOT / "doc" / "EXTERNAL_DESIGN.ja.md",
        REPO_ROOT / "doc" / "DESIGN.ja.md",
        REPO_ROOT / "doc" / "IMPLEMENTATION_PLAN.ja.md",
    )
    for doc_file in source_of_truth_docs:
        assert "doc-new" not in doc_file.read_text(encoding="utf-8").lower()


def test_t_r02_setup_generated_config_excludes_archive(tmp_path: Path) -> None:
    from spec_grag.project_setup import setup_project

    result = setup_project(tmp_path, agent="codex", codex_install="project")

    assert result["status"] == "ok"
    generated_config = tomllib.loads((tmp_path / ".spec-grag" / "config.toml").read_text(encoding="utf-8"))
    excludes = generated_config["sources"]["exclude"]
    assert "archive/**" in excludes


def test_t_r03_external_dependency_tests_are_skipped_only_by_pytest_option() -> None:
    conftest = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "--skip-external" in conftest
    assert "pytest_runtest_setup" in conftest
    assert "external dependency test not run" in conftest
    assert "external:" in pyproject

    external_test_files = (
        "test_agent_cli_smoke.py",
        "test_llm_provider.py",
        "test_production_readiness.py",
        "test_project_skeleton.py",
        "test_retrieval_index.py",
        "test_spec_core.py",
        "test_watcher.py",
    )
    for filename in external_test_files:
        text = (REPO_ROOT / "tests" / filename).read_text(encoding="utf-8")
        assert "@pytest.mark.external" in text, filename
        assert "pytest.mark.skipif" not in text, filename


def test_t_r04_release_smoke_uses_temp_project_and_fake_inputs(tmp_path: Path) -> None:
    from spec_grag.project_setup import setup_project

    executable = shutil.which("spec-grag")
    assert executable is not None, "spec-grag console script must be installed for release smoke"

    help_result = _run([executable, "--help"], cwd=REPO_ROOT)
    assert help_result.returncode == 0, help_result.stderr or help_result.stdout
    assert "usage" in help_result.stdout.lower()

    setup_result = setup_project(tmp_path, agent="codex", codex_install="project")
    assert setup_result["status"] == "ok"
    config_path = tmp_path / ".spec-grag" / "config.toml"
    real_llm_block = """\
[llm.providers.codex]
provider = "codex_cli"
command = "codex"
model = "gpt-5.4-mini"
effort = "low"
timeout_sec = 120
max_retries = 1

[llm.providers.claude_typing]
provider = "claude_cli"
command = "claude"
model = "claude-sonnet-4-6"
effort = "low"
timeout_sec = 360
max_retries = 1

[llm.providers.claude_judge]
provider = "claude_cli"
command = "claude"
model = "claude-sonnet-4-6"
effort = "low"
timeout_sec = 360
max_retries = 1

# 各 stage がどの provider を使うかを指定する。
[llm.stage_routing]
section_metadata   = "codex"
related_sections   = "claude_typing"
conflict_review    = "claude_judge"
chapter_key_anchor = "codex"
"""
    fake_llm_block = """\
[llm]
provider = "fake"
model = "fake-release-smoke"
timeout_sec = 5
max_retries = 0
"""
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace(
            real_llm_block,
            fake_llm_block,
        )
        .replace(
            'provider = "flagembedding"\nmodel = "BAAI/bge-m3"\ndense_enabled = true\nsparse_enabled = true',
            'provider = "fake"\nmodel = "fake-embedding"\ndense_enabled = false\nsparse_enabled = false',
        )
        .replace(
            'provider = "qdrant"\nurl = "http://localhost:6333"',
            'provider = "memory"\ncollection = "spec_grag_release_smoke"',
        ),
        encoding="utf-8",
    )

    spec_dir = tmp_path / "docs" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "release.md").write_text(
        "# Release\n\n"
        "## Rules\n"
        "Release smoke must run without real Qdrant, FlagEmbedding, or Agent service calls.\n",
        encoding="utf-8",
    )

    core_payload = _json_output(
        _run([executable, "core", "--all", "--project-root", str(tmp_path)], cwd=REPO_ROOT)
    )
    assert core_payload["status"] == "updated"

    constraints_json = json.dumps(_base_constraint())
    inject_payload = _json_output(
        _run(
            [
                executable,
                "inject",
                "--project-root",
                str(tmp_path),
                "--constraints",
                constraints_json,
                "release smoke",
            ],
            cwd=REPO_ROOT,
        )
    )
    assert inject_payload["status"] in {"fresh", "success"}
    assert inject_payload["can_continue"] is True

    answer_json = json.dumps({"answer": "The release smoke path is ready."})
    realign_payload = _json_output(
        _run(
            [
                executable,
                "realign",
                "--project-root",
                str(tmp_path),
                "--constraints",
                constraints_json,
                "--answer-json",
                answer_json,
                "release smoke",
            ],
            cwd=REPO_ROOT,
        )
    )
    assert realign_payload["status"] in {"fresh", "success"}
    assert realign_payload["can_continue"] is True


