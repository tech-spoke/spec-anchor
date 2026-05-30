"""Project Skeleton contract tests.

These tests intentionally exercise only the public package and CLI surface.
They should be useful even while the builder slice is still catching up.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.resources
import json
import os
import shutil
import subprocess
import sys
import tomllib
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_MODULE_NAMES = (
    "FlagEmbedding",
    "qdrant_client",
    "qdrant_client.models",
    "qdrant_client.http",
    "qdrant_client.http.models",
)


class _ProviderSentinel(types.ModuleType):
    def __init__(self, name: str, calls: list[str]) -> None:
        super().__init__(name)
        self._calls = calls

    def __getattr__(self, name: str) -> object:
        if name.startswith("__"):
            raise AttributeError(name)

        def _factory(*_args: object, **_kwargs: object) -> None:
            self._calls.append(f"{self.__name__}.{name}")
            raise AssertionError(
                f"provider initializer {self.__name__}.{name} was called during import"
            )

        return _factory


def _project_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) if not pythonpath else f"{REPO_ROOT}{os.pathsep}{pythonpath}"
    )
    return env


def _run_help(command: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which(command)
    assert executable is not None, f"{command} is not installed on PATH"
    return subprocess.run(
        [executable, "--help"],
        cwd=REPO_ROOT,
        env=_project_env(),
        text=True,
        capture_output=True,
        check=False,
    )


def _json_stdout(text: str) -> dict[str, object]:
    payload = json.loads(text)
    assert isinstance(payload, dict)
    return payload


def test_t_p01_package_import_exposes_version_without_provider_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for module_name in list(sys.modules):
        if module_name == "spec_anchor" or module_name.startswith("spec_anchor."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    provider_calls: list[str] = []
    for module_name in PROVIDER_MODULE_NAMES:
        monkeypatch.setitem(
            sys.modules,
            module_name,
            _ProviderSentinel(module_name, provider_calls),
        )

    package = importlib.import_module("spec_anchor")

    version = getattr(package, "__version__", None)
    if version is None:
        version = importlib.metadata.version("spec-anchor")

    assert isinstance(version, str)
    assert version
    assert provider_calls == []


@pytest.mark.parametrize(
    "command",
    (
        "spec-anchor",
        "spec-anchor-slash",
        "spec-anchor-watch",
        "spec-anchor-setup-project",
        "spec-anchor-setup-system",
    ),
)
def test_t_p02_cli_help_exits_zero(command: str) -> None:
    result = _run_help(command)

    assert result.returncode == 0, result.stderr or result.stdout
    assert "usage" in result.stdout.lower() or "help" in result.stdout.lower()


@pytest.mark.parametrize(
    ("command", "runner_module", "runner_name", "extra_args"),
    (
        ("core", "spec_anchor.core", "run_spec_core", ("--all",)),
        ("inject-purpose", "spec_anchor.inject", "run_inject_purpose", ()),
        ("realign", "spec_anchor.realign", "run_spec_realign", ()),
    ),
)
def test_t_p02_main_cli_dispatches_primary_commands_as_json(
    command: str,
    runner_module: str,
    runner_name: str,
    extra_args: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module(runner_module)
    calls: list[dict[str, object]] = []

    def fake_runner(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append({"args": args, "kwargs": kwargs})
        return {
            "command": f"/spec-{command}",
            "status": "ok",
            "returncode": 0,
        }

    monkeypatch.setattr(module, runner_name, fake_runner)
    from spec_anchor import cli

    try:
        exit_code = cli.main((command, *extra_args))
    except SystemExit as exc:
        if exc.code is None:
            exit_code = 0
        elif isinstance(exc.code, int):
            exit_code = exc.code
        else:
            exit_code = exc.code

    captured = capsys.readouterr()
    combined_output = f"{captured.out}\n{captured.err}".lower()
    assert "not implemented yet" not in combined_output
    assert exit_code == 0
    assert calls, f"{command} must dispatch to {runner_module}.{runner_name}"

    payload = _json_stdout(captured.out)
    assert command.split("-")[0] in payload["command"]
    assert payload["status"] == "ok"


def test_t_p02_core_cli_passes_explicit_llm_provider_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("spec_anchor.core")
    calls: list[dict[str, object]] = []

    def fake_runner(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append({"args": args, "kwargs": kwargs})
        return {"command": "/spec-core", "status": "ok", "returncode": 0}

    monkeypatch.setattr(module, "run_spec_core", fake_runner)
    from spec_anchor import cli

    exit_code = cli.main(("core", "--llm-provider", "claude", "--all"))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls[0]["kwargs"]["llm_provider_id"] == "claude"
    payload = _json_stdout(captured.out)
    assert payload["command"] == "/spec-core"


def test_t_p03_pytest_runner_smoke() -> None:
    assert "pytest" in sys.modules


@pytest.mark.external
def test_t_p03_external_dependency_tests_can_be_marked_for_optional_skip() -> None:
    assert True


def test_t_p04_packaging_metadata_defines_scripts_and_package_data() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    project = pyproject["project"]
    scripts = project["scripts"]
    dependencies = project.get("dependencies", [])

    assert project["name"] == "spec-anchor"
    assert any(str(item).startswith("markdown-it-py") for item in dependencies)
    for script_name in (
        "spec-anchor",
        "spec-anchor-slash",
        "spec-anchor-watch",
        "spec-anchor-setup-project",
        "spec-anchor-setup-system",
    ):
        assert script_name in scripts

    package_root = importlib.resources.files("spec_anchor")
    for resource in (
        "templates/.codex/skills/spec-anchor/SKILL.md",
        "templates/.claude/commands/spec-core.md",
        "templates/.claude/commands/spec-inject.md",
        "templates/.claude/commands/spec-realign.md",
        "templates/.spec-anchor/config.toml",
        "templates/.spec-anchor/.gitignore",
    ):
        assert package_root.joinpath(resource).is_file()


def test_t_p05_runtime_package_does_not_import_archive_modules() -> None:
    package = importlib.import_module("spec_anchor")
    package_path = Path(package.__file__).resolve()

    assert "archive" not in package_path.parts

    for module_name, module in sys.modules.items():
        if not (module_name == "spec_anchor" or module_name.startswith("spec_anchor.")):
            continue
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            continue
        assert "archive" not in Path(module_file).resolve().parts


def test_t_p05_tests_do_not_use_archive_fixtures() -> None:
    tests_root = Path(__file__).resolve().parent
    assert "archive" not in tests_root.parts
    assert not (tests_root / "archive").exists()


def test_t_p06_root_has_no_generated_runtime_state() -> None:
    runtime_root = REPO_ROOT / ".spec-anchor"
    assert not runtime_root.exists()


def test_t_p06_new_skeleton_does_not_reference_old_full_grag_modules() -> None:
    old_module_names = (
        "graph_ops",
        "concept_diff",
        "concept_index",
        "sidecars",
        "chunk_index",
    )
    source_text = "\n".join(
        path.read_text()
        for path in (REPO_ROOT / "spec_anchor").glob("*.py")
        if path.name != "__pycache__"
    )
    for old_module_name in old_module_names:
        assert old_module_name not in source_text
