"""Setup script and command template contract tests for G-15.

The setup implementation is still allowed to choose its public helper shape.
These tests therefore try common helper names first and fall back to the public
CLI entrypoints, while pinning the observable project files and diagnostics.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import tomllib
from pathlib import Path
from typing import Any

import pytest


COMMAND_NAMES = ("spec-core.md", "spec-inject.md", "spec-realign.md")


@pytest.fixture(autouse=True)
def isolated_codex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CODEX_HOME",
        str(tmp_path.parent / f"{tmp_path.name}-codex-home"),
    )


def _call_flexible(func: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    supported = {
        name: value for name, value in kwargs.items() if name in signature.parameters
    }
    try:
        return func(**supported)
    except TypeError:
        return func(*kwargs.get("_positional", ()), **supported)


def _maybe_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _result_code(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, int):
        return result
    if isinstance(result, dict):
        value = result.get("returncode", result.get("exit_code", result.get("code", 0)))
        return int(value or 0)
    value = getattr(result, "returncode", getattr(result, "exit_code", 0))
    return int(value or 0)


def _run_project_setup(
    target: Path,
    *,
    agent: str = "both",
    dry_run: bool = False,
    force: bool = False,
    no_init_core_files: bool = False,
    codex_install: str = "user",
) -> Any:
    for module_name in ("spec_grag.setup", "spec_grag.cli"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        for name in (
            "run_setup_project",
            "setup_project",
            "setup_project_main",
            "project_setup_main",
        ):
            func = getattr(module, name, None)
            if not callable(func):
                continue
            if name.endswith("_main"):
                argv = [
                    "--target",
                    str(target),
                    "--agent",
                    agent,
                    "--codex-install",
                    codex_install,
                ]
                if dry_run:
                    argv.append("--dry-run")
                if force:
                    argv.append("--force")
                if no_init_core_files:
                    argv.append("--no-init-core-files")
                return func(argv)
            return _call_flexible(
                func,
                _positional=(target,),
                target=target,
                project_root=target,
                root=target,
                agent=agent,
                dry_run=dry_run,
                force=force,
                no_init_core_files=no_init_core_files,
                init_core_files=not no_init_core_files,
                codex_install=codex_install,
            )
    pytest.fail("Project setup public API is required")


def _run_system_setup(
    *,
    check_only: bool = False,
    run_smoke: bool = False,
    mode: str = "editable",
    qdrant_url: str | None = None,
) -> Any:
    for module_name in ("spec_grag.setup", "spec_grag.cli"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        for name in (
            "run_setup_system",
            "setup_system",
            "setup_system_main",
            "system_setup_main",
        ):
            func = getattr(module, name, None)
            if not callable(func):
                continue
            if name.endswith("_main"):
                argv = ["--mode", mode]
                if check_only:
                    argv.append("--check-only")
                if run_smoke:
                    argv.append("--run-smoke")
                if qdrant_url:
                    argv.extend(["--qdrant-url", qdrant_url])
                return func(argv)
            return _call_flexible(
                func,
                check_only=check_only,
                run_smoke=run_smoke,
                mode=mode,
                qdrant_url=qdrant_url,
            )
    pytest.fail("System setup public API is required")


def _assert_success(result: Any) -> None:
    assert _result_code(result) == 0, result


def _project_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def _config_core_paths(root: Path) -> tuple[Path, Path]:
    config_path = root / ".spec-grag" / "config.toml"
    assert config_path.is_file()
    config = tomllib.loads(config_path.read_text())
    core = config["core"]
    return root / core["purpose_file"], root / core["concept_file"]


def _codex_user_skill_path() -> Path:
    return Path(os.environ["CODEX_HOME"]) / "skills" / "spec-grag" / "SKILL.md"


def _codex_project_skill_path(root: Path) -> Path:
    return root / ".codex" / "skills" / "spec-grag" / "SKILL.md"


@pytest.mark.parametrize(
    ("agent", "codex_install", "expect_claude", "expect_user_skill", "expect_project_skill"),
    (
        ("codex", "user", False, True, False),
        ("codex", "project", False, False, True),
        ("claude", "user", True, False, False),
        ("both", "user", True, True, False),
        ("both", "project", True, False, True),
    ),
)
def test_t_s01_project_setup_creates_agent_specific_files(
    tmp_path: Path,
    agent: str,
    codex_install: str,
    expect_claude: bool,
    expect_user_skill: bool,
    expect_project_skill: bool,
) -> None:
    result = _run_project_setup(tmp_path, agent=agent, codex_install=codex_install)

    _assert_success(result)
    assert (tmp_path / ".spec-grag" / "config.toml").is_file()
    assert (tmp_path / ".spec-grag" / ".gitignore").is_file()
    for command_name in COMMAND_NAMES:
        assert (tmp_path / ".claude" / "commands" / command_name).is_file() is expect_claude

    assert _codex_user_skill_path().is_file() is expect_user_skill
    assert _codex_project_skill_path(tmp_path).is_file() is expect_project_skill
    assert not (tmp_path / ".codex" / "commands").exists()


def test_t_s01_project_setup_initializes_purpose_and_core_concept_placeholders(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both"))

    purpose_file, concept_file = _config_core_paths(tmp_path)
    assert purpose_file.is_file()
    assert concept_file.is_file()
    assert "Purpose" in purpose_file.read_text()
    assert "Core Concept" in concept_file.read_text()


def test_t_s01_no_init_core_files_leaves_spec_core_clearly_blocked(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, no_init_core_files=True))

    purpose_file, concept_file = _config_core_paths(tmp_path)
    assert not purpose_file.exists()
    assert not concept_file.exists()
    (tmp_path / "docs/spec").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs/spec/main.md").write_text("# Main\nA source spec exists.\n")

    from spec_grag.core import run_spec_core

    result = run_spec_core(tmp_path, all_mode=True)
    message = json.dumps(result, ensure_ascii=False).lower()
    assert result["status"] == "failed"
    assert result["freshness_report"]["status"] == "failed"
    assert "failed_required_artifact" in result["freshness_report"]["blocking_reasons"]
    assert "purpose" in message or "concept" in message


def test_t_s01_setup_does_not_run_spec_core_automatically(tmp_path: Path) -> None:
    _assert_success(_run_project_setup(tmp_path))

    context_dir = tmp_path / ".spec-grag" / "context"
    if context_dir.exists():
        generated = {path.name for path in context_dir.rglob("*") if path.is_file()}
        assert generated.isdisjoint(
            {
                "section_metadata.json",
                "section_search_keys.json",
                "related_sections.json",
                "retrieval_index.json",
                "conflict_review_items.json",
            }
        )


def test_t_s01_dry_run_does_not_modify_target(tmp_path: Path) -> None:
    before = _project_files(tmp_path)

    result = _run_project_setup(tmp_path, dry_run=True)

    _assert_success(result)
    assert _project_files(tmp_path) == before
    assert "$CODEX_HOME/skills/spec-grag/SKILL.md" in set(result.get("created", ()))
    assert result.get("codex_install_path") == "$CODEX_HOME"


def test_t_s01_project_setup_rejects_missing_target(tmp_path: Path) -> None:
    missing = tmp_path / "missing-project"

    result = _run_project_setup(missing)

    assert _result_code(result) != 0
    assert result["status"] == "error"
    assert not missing.exists()
    assert "target_not_found" in json.dumps(result)


def test_t_s01_existing_files_are_not_silently_overwritten_without_force(
    tmp_path: Path,
) -> None:
    existing = tmp_path / ".spec-grag" / "config.toml"
    existing.parent.mkdir(parents=True)
    existing.write_text("# human-owned config\nsentinel = true\n")

    try:
        result = _run_project_setup(tmp_path, force=False)
    except Exception:
        result = 1

    assert _result_code(result) != 0
    assert existing.read_text() == "# human-owned config\nsentinel = true\n"


def test_t_s01_force_does_not_overwrite_human_owned_core_files(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both"))
    purpose_file, concept_file = _config_core_paths(tmp_path)
    human_purpose = "# Purpose\n\nHuman maintained purpose.\n"
    human_concept = "# Core Concept\n\nHuman maintained invariant.\n"
    purpose_file.write_text(human_purpose)
    concept_file.write_text(human_concept)

    result = _run_project_setup(tmp_path, agent="both", force=True)

    _assert_success(result)
    assert purpose_file.read_text() == human_purpose
    assert concept_file.read_text() == human_concept

    protected_paths = {
        purpose_file.relative_to(tmp_path).as_posix(),
        concept_file.relative_to(tmp_path).as_posix(),
    }
    result_text = json.dumps(result, ensure_ascii=False).lower()
    assert protected_paths.isdisjoint(set(result.get("updated", ())))
    assert (
        protected_paths.issubset(set(result.get("skipped", ())))
        or "protected" in result_text
    )


def test_t_s01_force_does_not_overwrite_absolute_configured_core_files(
    tmp_path: Path,
) -> None:
    external_core_dir = tmp_path / "outside-configured-core"
    external_core_dir.mkdir()
    absolute_purpose_file = external_core_dir / "purpose.md"
    absolute_concept_file = external_core_dir / "concept.md"
    absolute_purpose = "# Purpose\n\nAbsolute human purpose.\n"
    absolute_concept = "# Core Concept\n\nAbsolute human invariant.\n"
    absolute_purpose_file.write_text(absolute_purpose)
    absolute_concept_file.write_text(absolute_concept)

    default_purpose_file = tmp_path / "docs" / "core" / "purpose.md"
    default_concept_file = tmp_path / "docs" / "core" / "concept.md"
    default_purpose_file.parent.mkdir(parents=True)
    default_purpose = "# Purpose\n\nDefault path human purpose.\n"
    default_concept = "# Core Concept\n\nDefault path human invariant.\n"
    default_purpose_file.write_text(default_purpose)
    default_concept_file.write_text(default_concept)

    config_path = tmp_path / ".spec-grag" / "config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        "\n".join(
            (
                "[core]",
                f'purpose_file = "{absolute_purpose_file.as_posix()}"',
                f'concept_file = "{absolute_concept_file.as_posix()}"',
                "",
            )
        )
    )

    result = _run_project_setup(tmp_path, agent="both", force=True)

    _assert_success(result)
    assert absolute_purpose_file.read_text() == absolute_purpose
    assert absolute_concept_file.read_text() == absolute_concept
    assert default_purpose_file.read_text() == default_purpose
    assert default_concept_file.read_text() == default_concept
    assert "docs/core/purpose.md" not in set(result.get("updated", ()))
    assert "docs/core/concept.md" not in set(result.get("updated", ()))


def test_t_s01_project_gitignore_contains_runtime_state_paths(tmp_path: Path) -> None:
    _assert_success(_run_project_setup(tmp_path))

    ignore_text = (tmp_path / ".spec-grag" / ".gitignore").read_text()
    for ignored in ("context/", "pending/", "cache/", "state/", "tmp/", "runs/"):
        assert ignored in ignore_text


def test_t_c01_spec_inject_template_matches_agent_cli_boundary(tmp_path: Path) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both", codex_install="project"))

    for text in (
        (tmp_path / ".claude" / "commands" / "spec-inject.md").read_text(),
        _codex_project_skill_path(tmp_path).read_text(),
    ):
        lower = text.lower()
        assert "agentic search" in lower
        assert "agent / llm" in lower
        assert "pending conflict" in lower or "pending_conflict" in lower
        assert "`/spec-core` は自動実行しない" in lower
        assert "会話区間" in lower
        assert "search keys" in lower
        assert "section summary" in lower
        assert "related sections" in lower
        assert "sole evidence" in lower
        assert "purpose" in lower and "core concept" in lower
        assert "update purpose" not in lower
        assert "update core concept" not in lower
        assert "automatically update" not in lower


def _assert_agentic_constraint_workflow_text(text: str) -> None:
    lower = text.lower()
    for expected in (
        "gate probe",
        "needs_agent_constraints",
        "会話区間",
        "search keys",
        "source specs snippet",
        "related sections",
        "chapter key anchor",
        "agentic search",
        "statement",
        "evidence_origin",
        "evidence_ref",
        "support_refs",
        "applicability",
        "uncertainty",
        "spec-grag inject",
        "--constraints",
        "constraints json の作り方",
        "最小 schema",
        "良い例",
        "禁止例",
    ):
        assert expected in lower
    assert "cli" in lower and "検証" in lower
    assert "fallback constraints" in lower and "生成しない" in lower
    assert "section summary" in lower
    assert "sole evidence" in lower
    for expected in (
        '"statement"',
        '"evidence_origin"',
        '"evidence_ref"',
        '"support_refs"',
        '"applicability"',
        '"uncertainty"',
        "path + section id",
        "cli validation failed",
        "再生成",
    ):
        assert expected in lower


def _assert_realign_answer_workflow_text(text: str) -> None:
    lower = text.lower()
    for expected in (
        "spec-grag realign",
        "--answer-json",
        "今回守る制約",
        "今回扱う修正候補または検討対象",
        "競合 / 不確実性 / 人間レビューが必要な点",
        "課題プロンプトへの回答または修正案",
        "answer candidate",
        "constraint-checked",
    ):
        assert expected in lower


def _assert_japanese_agent_template_text(text: str) -> None:
    lower = text.lower()
    for expected in (
        "正本",
        "会話区間",
        "自動実行しない",
        "人間",
        "検証",
        "生成しない",
    ):
        assert expected in lower


def _constraints_json_block(text: str) -> str:
    marker = "### constraints JSON の作り方"
    start = text.index(marker)
    next_heading = text.find("\n## ", start + len(marker))
    if next_heading == -1:
        return text[start:].strip()
    return text[start:next_heading].strip()


def test_t_c01_inject_templates_define_agent_generated_constraints_workflow(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both", codex_install="project"))

    for text in (
        (tmp_path / ".claude" / "commands" / "spec-inject.md").read_text(),
        _codex_project_skill_path(tmp_path).read_text(),
    ):
        _assert_agentic_constraint_workflow_text(text)
        _assert_japanese_agent_template_text(text)


def test_t_c01_realign_templates_define_answer_generation_and_validation_workflow(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both", codex_install="project"))

    for text in (
        (tmp_path / ".claude" / "commands" / "spec-realign.md").read_text(),
        _codex_project_skill_path(tmp_path).read_text(),
    ):
        _assert_agentic_constraint_workflow_text(text)
        _assert_realign_answer_workflow_text(text)
        _assert_japanese_agent_template_text(text)


def test_t_c01_command_and_skill_templates_are_japanese_prose(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both", codex_install="project"))

    paths = [
        tmp_path / ".claude" / "commands" / "spec-core.md",
        tmp_path / ".claude" / "commands" / "spec-inject.md",
        tmp_path / ".claude" / "commands" / "spec-realign.md",
        _codex_project_skill_path(tmp_path),
    ]
    for path in paths:
        text = path.read_text()
        lower = text.lower()
        assert "spec-grag" in lower
        assert "人間" in lower
        assert "自動" in lower or "検証" in lower
        assert "purpose" in lower
        assert "core concept" in lower


def test_t_c01_agent_core_entrypoints_select_their_own_llm_provider(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both", codex_install="project"))

    claude_core = (tmp_path / ".claude" / "commands" / "spec-core.md").read_text()
    codex_skill = _codex_project_skill_path(tmp_path).read_text()

    assert "spec-grag core" in claude_core
    assert "stage_routing" in claude_core
    assert "spec-grag core" in codex_skill
    assert "stage_routing" in codex_skill


def test_t_c01_constraints_json_block_is_shared_across_agent_templates(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both", codex_install="project"))

    skill_block = _constraints_json_block(_codex_project_skill_path(tmp_path).read_text())
    inject_block = _constraints_json_block(
        (tmp_path / ".claude" / "commands" / "spec-inject.md").read_text()
    )
    realign_block = _constraints_json_block(
        (tmp_path / ".claude" / "commands" / "spec-realign.md").read_text()
    )

    assert inject_block == skill_block
    assert realign_block == skill_block


def test_t_c01_claude_command_templates_have_command_frontmatter(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="claude"))

    for command_name in COMMAND_NAMES:
        text = (tmp_path / ".claude" / "commands" / command_name).read_text()
        metadata = _front_matter(text)
        assert "description:" in metadata
        assert "allowed-tools:" in metadata
        assert "spec-grag" in metadata


@pytest.mark.parametrize("command_name", ("spec-inject.md", "spec-realign.md"))
def test_t_c01_inject_and_realign_templates_allow_agentic_search_tools_without_core(
    tmp_path: Path,
    command_name: str,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="claude"))

    text = (tmp_path / ".claude" / "commands" / command_name).read_text()
    metadata = _front_matter(text)
    lower = metadata.lower()
    for tool in ("read", "grep", "glob"):
        assert tool in lower
    assert "bash(spec-grag inject" in lower
    if command_name == "spec-realign.md":
        assert "bash(spec-grag realign" in lower
    assert "bash(spec-grag core" not in lower


@pytest.mark.parametrize("command_name", ("spec-inject.md", "spec-realign.md"))
def test_t_c01_inject_and_realign_metadata_do_not_allow_spec_core(
    tmp_path: Path,
    command_name: str,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both", codex_install="project"))

    text = (tmp_path / ".claude" / "commands" / command_name).read_text()
    metadata = _front_matter(text)
    lower_metadata = metadata.lower()
    assert "spec-grag core" not in lower_metadata
    assert "bash(spec-grag core" not in lower_metadata

    lower_text = text.lower()
    assert "`/spec-core` は自動実行しない" in lower_text


def test_t_c01_codex_skill_has_required_frontmatter_and_no_command_dir(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="codex", codex_install="project"))

    skill_path = _codex_project_skill_path(tmp_path)
    text = skill_path.read_text()
    metadata = _front_matter(text)
    lower = text.lower()

    assert "name: spec-grag" in metadata
    assert "description:" in metadata
    assert "short-description:" in metadata
    assert "仕様に基づくコンテキスト" in text
    assert "spec-grag core" in lower
    assert "spec-grag inject" in lower
    assert "spec-grag realign" in lower
    assert "pending conflict" in lower or "pending_conflict" in lower
    assert "section summary" in lower
    assert "related sections" in lower
    assert "sole evidence" in lower
    assert not (tmp_path / ".codex" / "commands").exists()


def test_t_s01_codex_user_install_requires_force_for_existing_skill(
    tmp_path: Path,
) -> None:
    skill_path = _codex_user_skill_path()
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("human-owned skill\n")

    result = _run_project_setup(
        tmp_path,
        agent="codex",
        codex_install="user",
        force=False,
    )

    assert _result_code(result) != 0
    assert result["status"] == "conflict"
    assert skill_path.read_text() == "human-owned skill\n"
    assert "would_overwrite_existing_codex_user_skill" in json.dumps(result)


def test_t_s01_codex_user_install_force_updates_existing_skill(
    tmp_path: Path,
) -> None:
    skill_path = _codex_user_skill_path()
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("human-owned skill\n")

    result = _run_project_setup(
        tmp_path,
        agent="codex",
        codex_install="user",
        force=True,
    )

    _assert_success(result)
    assert "name: spec-grag" in skill_path.read_text()
    diagnostics = json.dumps(result.get("diagnostics", []))
    assert "codex_user_skill_overwrite" in diagnostics
    assert "$CODEX_HOME/skills/spec-grag/SKILL.md" in diagnostics


def test_t_s01_no_init_core_files_with_existing_core_files_has_no_misleading_warning(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both"))

    result = _run_project_setup(tmp_path, agent="both", no_init_core_files=True)

    _assert_success(result)
    assert result.get("missing_core_files") == []
    messages = " ".join(
        str(item.get("message", ""))
        for item in result.get("diagnostics", ())
        if isinstance(item, dict)
    ).lower()
    assert "/spec-core fails until" not in messages
    assert "fails until a human creates" not in messages


def test_t_s01_force_no_init_reports_missing_core_files_after_config_update(
    tmp_path: Path,
) -> None:
    external_core_dir = tmp_path / "outside-configured-core"
    external_core_dir.mkdir()
    absolute_purpose_file = external_core_dir / "purpose.md"
    absolute_concept_file = external_core_dir / "concept.md"
    absolute_purpose_file.write_text("# Purpose\n\nExternal custom purpose.\n")
    absolute_concept_file.write_text("# Core Concept\n\nExternal custom invariant.\n")

    config_path = tmp_path / ".spec-grag" / "config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        "\n".join(
            (
                "[core]",
                f'purpose_file = "{absolute_purpose_file.as_posix()}"',
                f'concept_file = "{absolute_concept_file.as_posix()}"',
                "",
            )
        )
    )

    result = _run_project_setup(
        tmp_path,
        agent="both",
        force=True,
        no_init_core_files=True,
    )

    _assert_success(result)
    purpose_file, concept_file = _config_core_paths(tmp_path)
    assert purpose_file == tmp_path / "docs" / "core" / "purpose.md"
    assert concept_file == tmp_path / "docs" / "core" / "concept.md"
    assert not purpose_file.exists()
    assert not concept_file.exists()
    assert set(result.get("missing_core_files", ())) == {
        "docs/core/purpose.md",
        "docs/core/concept.md",
    }
    messages = " ".join(
        str(item.get("message", ""))
        for item in result.get("diagnostics", ())
        if isinstance(item, dict)
    ).lower()
    assert "/spec-core fails until" in messages


def _front_matter(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    _, metadata, _body = text.split("---", 2)
    return metadata


def test_t_s02_check_only_returns_diagnostics_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    before = _project_files(tmp_path)

    result = _run_system_setup(check_only=True, run_smoke=False)
    captured = capsys.readouterr()
    payload = result if isinstance(result, dict) else _maybe_json(captured.out)

    _assert_success(result)
    assert _project_files(tmp_path) == before
    assert isinstance(payload, dict), "system setup must return or print diagnostics"
    assert "diagnostics" in payload or "checks" in payload or "status" in payload


def test_t_s02_non_check_only_returns_preparation_actions_and_availability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    before = _project_files(tmp_path)

    check_result = _run_system_setup(check_only=True, run_smoke=False, mode="editable")
    check_output = capsys.readouterr()
    check_payload = (
        check_result if isinstance(check_result, dict) else _maybe_json(check_output.out)
    )

    result = _run_system_setup(check_only=False, run_smoke=False, mode="editable")
    captured = capsys.readouterr()
    payload = result if isinstance(result, dict) else _maybe_json(captured.out)

    _assert_success(check_result)
    _assert_success(result)
    assert _project_files(tmp_path) == before
    assert isinstance(check_payload, dict)
    assert isinstance(payload, dict), "system setup must return or print diagnostics"
    assert payload["check_only"] is False
    assert payload["mode"] == "editable"
    assert payload != check_payload

    comparable_check_payload = dict(check_payload)
    comparable_payload = dict(payload)
    comparable_check_payload.pop("check_only", None)
    comparable_payload.pop("check_only", None)
    assert comparable_payload != comparable_check_payload

    actions = payload.get("actions")
    assert isinstance(actions, list)
    assert actions, "non-check-only setup must report concrete preparation actions"
    action_statuses = {
        action.get("status") for action in actions if isinstance(action, dict)
    }
    assert {"prepared", "checked", "skipped"}.issubset(action_statuses)
    assert any(
        isinstance(action, dict)
        and action.get("mode") == "editable"
        and action.get("status") == "prepared"
        for action in actions
    )
    assert isinstance(payload.get("diagnostics"), list)
    assert isinstance(payload.get("console_scripts"), list)
    assert payload["console_scripts"]
    assert all("available" in item for item in payload["console_scripts"])
    assert isinstance(payload.get("templates"), list)
    assert payload["templates"]
    assert all("available" in item for item in payload["templates"])
    template_paths = {item["path"] for item in payload["templates"]}
    assert "templates/.codex/skills/spec-grag/SKILL.md" in template_paths
    assert not any("templates/.codex/commands/" in path for path in template_paths)
    assert isinstance(payload.get("agent_cli_entries"), dict)
    diagnostic_codes = {item["code"] for item in payload.get("diagnostics", [])}
    assert "codex_skill_entrypoint" in diagnostic_codes
    assert "claude_command_entrypoint" in diagnostic_codes


def test_t_s02_smoke_runs_only_when_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    no_smoke = _run_system_setup(check_only=True, run_smoke=False)
    no_smoke_output = capsys.readouterr().out.lower()
    with_smoke = _run_system_setup(check_only=True, run_smoke=True)
    with_smoke_output = capsys.readouterr().out.lower()

    _assert_success(no_smoke)
    _assert_success(with_smoke)
    no_smoke_payload = no_smoke if isinstance(no_smoke, dict) else _maybe_json(no_smoke_output)
    with_smoke_payload = (
        with_smoke if isinstance(with_smoke, dict) else _maybe_json(with_smoke_output)
    )

    assert "smoke" not in no_smoke_output or "skipped" in no_smoke_output
    assert (
        "smoke" in with_smoke_output
        or (isinstance(with_smoke_payload, dict) and "smoke" in str(with_smoke_payload).lower())
    )
    assert no_smoke_payload != with_smoke_payload or "smoke" in with_smoke_output


def test_t_r11_setup_system_reports_production_readiness_dependencies_without_env_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPEC_GRAG_REAL_PROVIDER", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_RETRIEVAL", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_SMOKE", raising=False)
    monkeypatch.delenv("SPEC_GRAG_LOCAL_SERVICE", raising=False)

    payload = _run_system_setup(check_only=True, run_smoke=False)

    _assert_success(payload)
    readiness = payload.get("production_readiness")
    assert isinstance(readiness, dict)
    assert readiness["status"] in {"ready", "blocked"}
    checks = {
        item["name"]: item
        for item in readiness.get("checks", [])
        if isinstance(item, dict)
    }
    for required in (
        "qdrant_service",
        "flagembedding_package",
        "qdrant_client_package",
        "agent_cli",
    ):
        assert required in checks
    assert "real_provider_gate" not in checks
    assert "real_retrieval_gate" not in checks
    assert "real_provider_gate_disabled" not in readiness["blocking_reasons"]
    assert "real_retrieval_gate_disabled" not in readiness["blocking_reasons"]
    assert "model_cache_dir" in readiness


def test_t_r11_setup_system_qdrant_url_is_explicit_probe_input_not_project_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SPEC_GRAG_QDRANT_URL", "http://env-qdrant.example:6333")

    payload = _run_system_setup(
        check_only=True,
        run_smoke=False,
        qdrant_url="http://cli-qdrant.example:6333",
    )

    _assert_success(payload)
    providers = {
        item["name"]: item
        for item in payload.get("providers", [])
        if isinstance(item, dict)
    }
    assert providers["qdrant"]["url"] == "http://cli-qdrant.example:6333"


def test_t_r11_setup_system_does_not_require_real_operation_gate_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPEC_GRAG_REAL_PROVIDER", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_RETRIEVAL", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_SMOKE", raising=False)

    payload = _run_system_setup(check_only=True, run_smoke=False)

    _assert_success(payload)
    readiness = payload["production_readiness"]
    checks = {
        item["name"]: item
        for item in readiness.get("checks", [])
        if isinstance(item, dict)
    }
    assert "real_provider_gate" not in checks
    assert "real_retrieval_gate" not in checks
    assert "real_provider_gate_disabled" not in readiness["blocking_reasons"]
    assert "real_retrieval_gate_disabled" not in readiness["blocking_reasons"]


def test_t_r12_setup_project_config_is_production_stack_ready(
    tmp_path: Path,
) -> None:
    _assert_success(_run_project_setup(tmp_path, agent="both"))
    config_path = tmp_path / ".spec-grag" / "config.toml"
    parsed = tomllib.loads(config_path.read_text())

    # default_provider / fallback_order / providers.claude (haiku-4-5) は dead settings として削除済み
    # (stage_routing が 4 stage 全てを明示指定しているのでフォールバック先は不要)
    assert "default_provider" not in parsed["llm"]
    assert "fallback_order" not in parsed["llm"]
    assert "claude" not in parsed["llm"]["providers"]
    # Base provider entries
    assert parsed["llm"]["providers"]["codex"]["provider"] == "codex_cli"
    assert parsed["llm"]["providers"]["codex"]["model"] == "gpt-5.4-mini"
    assert parsed["llm"]["providers"]["codex"]["effort"] == "low"
    # H-4 calibration (doc/CALIBRATION_MODEL_EFFORT.ja.md) で確定した stage 別 provider
    # related_sections と conflict_review は claude-sonnet-4-6 × low (recall 重視)
    assert parsed["llm"]["providers"]["claude_typing"]["provider"] == "claude_cli"
    assert parsed["llm"]["providers"]["claude_typing"]["model"] == "claude-sonnet-4-6"
    assert parsed["llm"]["providers"]["claude_typing"]["effort"] == "low"
    assert parsed["llm"]["providers"]["claude_judge"]["provider"] == "claude_cli"
    assert parsed["llm"]["providers"]["claude_judge"]["model"] == "claude-sonnet-4-6"
    assert parsed["llm"]["providers"]["claude_judge"]["effort"] == "low"
    # stage_routing は H-4 確定値で template に組み込み済み
    assert parsed["llm"]["stage_routing"] == {
        "section_metadata": "codex",
        "related_sections": "claude_typing",
        "conflict_review": "claude_judge",
        "chapter_key_anchor": "codex",
    }
    # Phase H follow-up: llm_batch_concurrency must be present and >= 1
    assert parsed["limits"]["llm_batch_concurrency"] >= 1
    assert parsed["embedding"]["provider"] == "flagembedding"
    assert parsed["embedding"]["model"] == "BAAI/bge-m3"
    assert parsed["vector_store"]["provider"] == "qdrant"
    assert parsed["vector_store"]["url"] == "http://localhost:6333"
