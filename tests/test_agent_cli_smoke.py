"""Agent CLI recognition and setup roundtrip tests for G-19.

These tests call local Agent CLI binaries and, for T-A02, the configured
production provider/retrieval stack. Use `pytest --skip-external` to skip them
on machines without Codex/Claude CLI, Qdrant, or FlagEmbedding BGE-M3.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE_DIR = REPO_ROOT / "テスト用ドキュメント"
SOURCE_FIXTURE_FILES = (
    "01_システム目標.md",
)


def _command_from_env(env_name: str, default: str) -> str:
    value = os.environ.get(env_name, default)
    if os.sep in value:
        path = Path(value).expanduser()
        if path.is_file():
            return path.as_posix()
        pytest.skip(f"{env_name} points to a missing executable: {path}")
    resolved = shutil.which(value)
    if not resolved:
        pytest.skip(f"{value} CLI is not installed or not on PATH")
    return resolved


def _project_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) if not pythonpath else f"{REPO_ROOT}{os.pathsep}{pythonpath}"
    )
    if extra:
        env.update(extra)
    return env


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env or _project_env(),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _json_output(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def _has_spec_grag_skill_description(prompt_input: str) -> bool:
    lower = prompt_input.lower()
    return (
        "specification-grounded context" in lower
        or "仕様に基づくコンテキスト" in prompt_input
    )


def _setup_project(
    project_root: Path,
    *,
    agent: str,
    codex_install: str = "project",
) -> dict[str, Any]:
    from spec_grag.project_setup import setup_project

    result = setup_project(
        project_root,
        agent=agent,
        codex_install=codex_install,
        force=True,
        no_init_core_files=False,
    )
    assert result["status"] == "ok", result
    return result


def _codex_prompt_input(
    *,
    codex: str,
    cwd: Path,
    env: dict[str, str],
    prompt: str = "Use spec-grag for this repository task.",
) -> str:
    result = _run(
        [codex, "debug", "prompt-input", prompt],
        cwd=cwd,
        env=env,
        timeout=30,
    )
    if result.returncode != 0:
        output = f"{result.stdout}\n{result.stderr}".lower()
        if "unknown command" in output or "unrecognized" in output:
            pytest.skip("Codex CLI does not support `codex debug prompt-input`")
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout


def _copy_source_fixture(project_root: Path) -> None:
    target = project_root / "docs" / "spec"
    target.mkdir(parents=True, exist_ok=True)
    for filename in SOURCE_FIXTURE_FILES:
        source = SOURCE_FIXTURE_DIR / filename
        assert source.is_file(), f"missing Source Specs fixture: {source}"
        shutil.copy2(source, target / source.name)


def _patch_collection(project_root: Path) -> str:
    config_path = project_root / ".spec-grag" / "config.toml"
    collection = f"spec_grag_t_a02_{uuid.uuid4().hex}"
    qdrant_url = os.environ.get("SPEC_GRAG_QDRANT_URL", "http://localhost:6333")
    text = config_path.read_text(encoding="utf-8")
    text = text.replace('url = "http://localhost:6333"', f'url = "{qdrant_url}"')
    text = text.replace('collection = "spec_grag_source"', f'collection = "{collection}"')
    # Phase R-5: production default disables chunk-level retrieval. This
    # smoke test runs in a subprocess, so the conftest constant override
    # does not reach it. Opt back in via the config flag so the
    # `client.count(collection)` assertion still has chunk-level data.
    if "chunk_level_enabled" not in text:
        text = text.replace(
            f'collection = "{collection}"',
            f'collection = "{collection}"\nchunk_level_enabled = true',
        )
    config_path.write_text(text, encoding="utf-8")
    return collection


def _first_section_id(project_root: Path) -> str:
    metadata_path = project_root / ".spec-grag" / "context" / "section_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    sections = metadata.get("sections")
    assert isinstance(sections, list) and sections
    section_id = sections[0].get("section_id")
    assert isinstance(section_id, str) and section_id
    return section_id


@pytest.mark.external
def test_t_a01_codex_user_skill_is_visible_in_prompt_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex = _command_from_env("SPEC_GRAG_AGENT_CLI_CODEX_COMMAND", "codex")
    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())
    _setup_project(project_root, agent="codex", codex_install="user")

    skill_path = codex_home / "skills" / "spec-grag" / "SKILL.md"
    assert skill_path.is_file()
    env = _project_env({"CODEX_HOME": codex_home.as_posix()})
    prompt_input = _codex_prompt_input(codex=codex, cwd=project_root, env=env)

    assert "- spec-grag:" in prompt_input
    assert _has_spec_grag_skill_description(prompt_input)
    assert skill_path.as_posix() in prompt_input


@pytest.mark.external
def test_t_a01_codex_project_skill_is_visible_in_prompt_input(
    tmp_path: Path,
) -> None:
    codex = _command_from_env("SPEC_GRAG_AGENT_CLI_CODEX_COMMAND", "codex")
    codex_home = tmp_path / "empty-codex-home"
    project_root = tmp_path / "project"
    project_root.mkdir()
    _setup_project(project_root, agent="codex", codex_install="project")

    skill_path = project_root / ".codex" / "skills" / "spec-grag" / "SKILL.md"
    assert skill_path.is_file()
    codex_home.mkdir(parents=True)
    env = _project_env({"CODEX_HOME": codex_home.as_posix()})
    prompt_input = _codex_prompt_input(codex=codex, cwd=project_root, env=env)

    assert "- spec-grag:" in prompt_input
    assert _has_spec_grag_skill_description(prompt_input)
    assert skill_path.as_posix() in prompt_input


@pytest.mark.external
def test_t_a01_claude_project_command_files_are_available_to_claude_cli(
    tmp_path: Path,
) -> None:
    claude = _command_from_env("SPEC_GRAG_AGENT_CLI_CLAUDE_COMMAND", "claude")
    project_root = tmp_path / "project"
    project_root.mkdir()
    _setup_project(project_root, agent="claude")

    version = _run([claude, "--version"], cwd=project_root, timeout=20)
    assert version.returncode == 0, version.stderr or version.stdout
    for name in ("spec-core.md", "spec-inject.md", "spec-realign.md"):
        command_path = project_root / ".claude" / "commands" / name
        assert command_path.is_file()
        text = command_path.read_text(encoding="utf-8")
        assert "description:" in text
        assert "spec-grag" in text


@pytest.mark.external
def test_t_a02_real_setup_core_inject_realign_watch_roundtrip_with_agent_entrypoints(
    tmp_path: Path,
) -> None:
    codex = _command_from_env("SPEC_GRAG_AGENT_CLI_CODEX_COMMAND", "codex")
    _command_from_env("SPEC_GRAG_AGENT_CLI_CLAUDE_COMMAND", "claude")
    pytest.importorskip("FlagEmbedding")
    qdrant_client = pytest.importorskip("qdrant_client")

    codex_home = tmp_path / "codex-home"
    project_root = tmp_path / "project"
    project_root.mkdir()
    _copy_source_fixture(project_root)
    _setup_project(project_root, agent="both", codex_install="project")
    collection = _patch_collection(project_root)
    codex_home.mkdir(parents=True)

    env = _project_env({"CODEX_HOME": codex_home.as_posix()})
    qdrant_url = os.environ.get("SPEC_GRAG_QDRANT_URL", "http://localhost:6333")
    client = qdrant_client.QdrantClient(qdrant_url)
    try:
        prompt_input = _codex_prompt_input(codex=codex, cwd=project_root, env=env)
        assert "- spec-grag:" in prompt_input
        assert (project_root / ".claude" / "commands" / "spec-core.md").is_file()

        core = _json_output(
            _run(
                [
                    sys.executable,
                    "-m",
                    "spec_grag",
                    "core",
                    "--llm-provider",
                    "codex",
                    "--all",
                    "--project-root",
                    project_root.as_posix(),
                ],
                cwd=REPO_ROOT,
                env=env,
                timeout=600,
            )
        )
        assert core["status"] == "updated"
        assert core["freshness_report"]["status"] == "fresh"
        assert client.count(collection).count >= 1

        section_id = _first_section_id(project_root)
        constraints = [
            {
                "statement": "テスト用ドキュメントの Source Specs を最終根拠にする。",
                "evidence_origin": "Source Specs",
                "evidence_ref": section_id,
                "support_refs": [{"origin": "Section Summary", "ref": section_id}],
                "applicability": "Agent CLI smoke roundtrip.",
                "uncertainty": [],
            }
        ]
        constraints_json = json.dumps(constraints, ensure_ascii=False)

        inject = _json_output(
            _run(
                [
                    sys.executable,
                    "-m",
                    "spec_grag",
                    "inject",
                    "--project-root",
                    project_root.as_posix(),
                    "--constraints",
                    constraints_json,
                    "管理画面の基本設計の制約を確認したい",
                ],
                cwd=REPO_ROOT,
                env=env,
                timeout=120,
            )
        )
        assert inject["status"] in {"fresh", "success", "ready", "ok"}
        assert inject["can_continue"] is True

        answer = {
            "今回守る制約": ["テスト用ドキュメントの Source Specs を最終根拠にする。"],
            "今回扱う修正候補または検討対象": ["管理画面仕様の確認手順。"],
            "競合 / 不確実性 / 人間レビューが必要な点": [],
            "課題プロンプトへの回答または修正案": "Source Specs を根拠に制約を確認する。",
        }
        realign = _json_output(
            _run(
                [
                    sys.executable,
                    "-m",
                    "spec_grag",
                    "realign",
                    "--project-root",
                    project_root.as_posix(),
                    "--constraints",
                    constraints_json,
                    "--answer-json",
                    json.dumps(answer, ensure_ascii=False),
                    "問題点一覧の優先順位案",
                ],
                cwd=REPO_ROOT,
                env=env,
                timeout=120,
            )
        )
        assert realign["status"] in {"fresh", "success", "ready", "ok"}
        assert realign["can_continue"] is True

        watched_source = sorted((project_root / "docs" / "spec").glob("*.md"))[0]
        watched_source.write_text(
            watched_source.read_text(encoding="utf-8")
            + "\n\n## Agent CLI Smoke Watch\n\nWatcher should index this change.\n",
            encoding="utf-8",
        )
        watch = _json_output(
            _run(
                [
                    sys.executable,
                    "-m",
                    "spec_grag",
                    "watch",
                    project_root.as_posix(),
                    "--once",
                    "--interval-sec",
                    "0",
                    "--debounce-sec",
                    "0",
                ],
                cwd=REPO_ROOT,
                env=env,
                timeout=600,
            )
        )
        assert watch["ran_core"] is True
        assert watch["freshness_report"]["status"] == "fresh"
        revision = json.loads(
            (project_root / ".spec-grag" / "context" / "retrieval_index_revision.json").read_text(
                encoding="utf-8"
            )
        )
        diff = revision["diagnostics"]["source_update_diff"]
        assert diff["changed_sections"]
    finally:
        try:
            client.delete_collection(collection)
        except Exception:
            pass
