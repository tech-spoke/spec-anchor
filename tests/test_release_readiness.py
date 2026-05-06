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
DEFAULT_CONFIG = REPO_ROOT / "spec_grag" / "templates" / ".spec-grag" / "config.toml"
REAL_SMOKE_ENV = {"1", "true", "yes"}


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _project_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) if not pythonpath else f"{REPO_ROOT}{os.pathsep}{pythonpath}"
    )
    env.setdefault("SPEC_GRAG_REAL_SMOKE", "")
    env.setdefault("SPEC_GRAG_LOCAL_SERVICE", "")
    return env


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
    assert "pytest" in lowered
    assert "local" in lowered
    assert "diagnostics" in lowered
    assert "privacy" in lowered
    for phrase in (
        "request",
        "response",
        "source",
    ):
        assert phrase in lowered
    assert "full text" in lowered or "full source specs text" in lowered
    assert "core concept" in lowered
    assert "never updates" in lowered or "does not update" in lowered
    assert "automatically" in lowered


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

    result = setup_project(tmp_path, agent="codex")

    assert result["status"] == "ok"
    generated_config = tomllib.loads((tmp_path / ".spec-grag" / "config.toml").read_text(encoding="utf-8"))
    excludes = generated_config["sources"]["exclude"]
    assert "archive/**" in excludes


def test_t_r03_default_ci_skips_local_service_and_real_smoke_without_opt_in() -> None:
    real_enabled = os.environ.get("SPEC_GRAG_REAL_SMOKE", "").lower() in REAL_SMOKE_ENV
    local_enabled = os.environ.get("SPEC_GRAG_LOCAL_SERVICE", "").lower() in REAL_SMOKE_ENV

    if real_enabled or local_enabled:
        pytest.skip("real/local-service smoke profile is explicitly enabled")

    project_skeleton = (REPO_ROOT / "tests" / "test_project_skeleton.py").read_text(encoding="utf-8")
    llm_provider = (REPO_ROOT / "tests" / "test_llm_provider.py").read_text(encoding="utf-8")
    retrieval_index = (REPO_ROOT / "tests" / "test_retrieval_index.py").read_text(encoding="utf-8")

    assert "pytest.mark.skipif" in project_skeleton
    assert "SPEC_GRAG_REAL_SMOKE" in project_skeleton
    assert "real provider smoke tests require SPEC_GRAG_REAL_SMOKE=1" in project_skeleton
    assert "pytest.mark.skipif" in llm_provider
    assert "real provider smoke requires SPEC_GRAG_REAL_SMOKE=1" in llm_provider
    assert "pytest.mark.skipif" in retrieval_index
    assert "SPEC_GRAG_LOCAL_SERVICE=1" in retrieval_index


def test_t_r04_release_smoke_uses_temp_project_and_fake_inputs(tmp_path: Path) -> None:
    from spec_grag.project_setup import setup_project

    executable = shutil.which("spec-grag")
    assert executable is not None, "spec-grag console script must be installed for release smoke"

    help_result = _run([executable, "--help"], cwd=REPO_ROOT)
    assert help_result.returncode == 0, help_result.stderr or help_result.stdout
    assert "usage" in help_result.stdout.lower()

    setup_result = setup_project(tmp_path, agent="codex")
    assert setup_result["status"] == "ok"
    config_path = tmp_path / ".spec-grag" / "config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace(
            'provider = "codex_cli"\ncommand = "codex"\nmodel = "gpt-5.4-mini"\neffort = "low"\ntimeout_sec = 120\nmax_retries = 1',
            'provider = "fake"\nmodel = "fake-release-smoke"\ntimeout_sec = 5\nmax_retries = 0',
        )
        .replace(
            'provider = "flagembedding"\nmodel = "BAAI/bge-m3"\ndense_enabled = true\nsparse_enabled = true',
            'provider = "fake"\nmodel = "fake-embedding"\ndense_enabled = false\nsparse_enabled = false',
        )
        .replace(
            'provider = "qdrant"\nurl = "http://localhost:6333"\ncollection = "spec_grag_source"',
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


def test_t_r05_default_run_artifact_privacy_is_documented_and_configured() -> None:
    config = tomllib.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    run_config = config["run"]

    assert run_config["save_artifacts"] is False
    assert run_config["include_request"] is False
    assert run_config["include_response"] is False
    assert run_config["redact_payload"] is True

    readme = _readme().lower()
    assert "diagnostics" in readme
    assert "privacy" in readme
    assert "request" in readme
    assert "response" in readme
    assert "source" in readme
    assert "full text" in readme or "full source specs text" in readme
    assert "default" in readme
