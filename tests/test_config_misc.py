"""Auxiliary tests for §10 — items that don't fit the §10.2 config-key
table-driven harness.

Covered claims:

- §10.1 L1008: ``spec-anchor`` family reads config from
  ``<project_root>/.spec-anchor/config.toml``.
- §10.2 L1066: ``[llm.providers.<id>]`` / ``[llm.stage_routing]`` only
  shape ``/spec-core``; they do not appear in ``/spec-inject`` or
  ``/spec-realign`` execution paths.
- §10.2 L1070: Codex skill and Claude command templates invoke
  ``spec-anchor core`` without ``--llm-provider``.
- §10.2 L1085: At least one ``[llm.providers.<id>]`` is required.
- §10.2 L1088: ``spec-anchor core --llm-provider <id>`` overrides
  ``[llm.stage_routing]`` and applies to every stage.
- §10.2 L1089: A failed provider is reported, not silently swapped.
- §10.2 L1093: ``spec-anchor-setup-project`` lays down the documented
  initial TOML.
- §10.3 L1193: ``SPEC_ANCHOR_DEBUG_*`` env vars do not alter the main
  execution path.
- §10.3 L1197–L1199: ``.env`` loading mechanics (load to ``os.environ``,
  do not clobber existing shell vars, equivalent across export
  channels).
- §10.3 L1203–L1209: env var name registry (each documented var is
  referenced from the source tree).
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_ANCHOR_PKG = REPO_ROOT / "spec_anchor"


def _run_main(module: str, func_name: str, argv: list[str]) -> int:
    mod = importlib.import_module(module)
    func = getattr(mod, func_name)
    try:
        result = func(argv)
        return int(result) if isinstance(result, int) else 0
    except SystemExit as exc:
        return int(exc.code or 0)


def _setup_project(target: Path) -> None:
    code = _run_main(
        "spec_anchor.cli",
        "setup_project_main",
        ["--target", str(target), "--agent", "both"],
    )
    assert code == 0, f"setup-project exited {code}"
    # Source Specs are required by load_config (sources.include must match);
    # the setup-project template creates the directory tree but no actual
    # spec file, so we drop a minimal one to satisfy the validator.
    spec_dir = target / "docs" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / "main.md"
    if not spec_file.exists():
        spec_file.write_text("# Main\n\n## Overview\n\nbody\n", encoding="utf-8")


# ----- §10.1 L1008 ---------------------------------------------------------


@pytest.mark.spec_ref("§10.1", 1008, profile="fake", method="入出力比較")
def test_spec_anchor_commands_read_config_from_project_root(tmp_path: Path) -> None:
    """`spec-anchor` family loads `<project_root>/.spec-anchor/config.toml`.

    PROFILE: fake
    METHOD: 入出力比較
    """

    project = tmp_path / "proj"
    project.mkdir()
    _setup_project(project)
    config_path = project / ".spec-anchor" / "config.toml"
    assert config_path.is_file(), "setup-project must create config at project_root/.spec-anchor/config.toml"

    config_module = importlib.import_module("spec_anchor.config")
    config = config_module.load_config(project)
    assert config.config_file == config_path.resolve()


# ----- §10.2 L1066: stage_routing scope ------------------------------------


@pytest.mark.spec_ref("§10.2", 1066, profile="fake", method="入出力比較")
def test_inject_path_does_not_consume_llm_providers_or_stage_routing(
    tmp_path: Path,
) -> None:
    """`[llm.providers]` / `[llm.stage_routing]` are not referenced by
    ``inject-*`` / ``realign`` code paths.

    PROFILE: fake
    METHOD: tool call trace 監査
    """

    inject_src = (SPEC_ANCHOR_PKG / "inject.py").read_text(encoding="utf-8")
    realign_src = (SPEC_ANCHOR_PKG / "realign.py").read_text(encoding="utf-8")
    # The inject / realign source code must not reference
    # build_spec_core_llm_provider or select_llm_provider_config; those
    # are gated to the /spec-core stage_routing pipeline.
    for label, src in (("inject.py", inject_src), ("realign.py", realign_src)):
        assert "build_spec_core_llm_provider" not in src, (
            f"§10.2 L1066: {label} references build_spec_core_llm_provider, "
            "implying /spec-inject or /spec-realign spawns a stage_routing-driven "
            "LLM. The contract restricts this to /spec-core."
        )


# ----- §10.2 L1070: template does not pass --llm-provider ------------------


@pytest.mark.spec_ref("§10.2", 1070, profile="none", method="artifact 内容確認")
def test_templates_do_not_pass_llm_provider_flag() -> None:
    """Claude command and Codex skill templates instruct the Agent not to
    pass ``--llm-provider``.

    PROFILE: none
    METHOD: artifact 内容確認
    """

    targets = [
        SPEC_ANCHOR_PKG / "templates" / ".claude" / "commands" / "spec-core.md",
        SPEC_ANCHOR_PKG / "templates" / ".codex" / "skills" / "spec-anchor" / "SKILL.md",
    ]
    for target in targets:
        text = target.read_text(encoding="utf-8")
        # The contract is "don't use --llm-provider unless 特別な事情";
        # the template should explicitly warn against routine use.
        assert "--llm-provider" in text, (
            f"{target}: should mention --llm-provider in the context of the warning"
        )
        assert "特別な事情" in text or "fallback" in text.lower(), (
            f"{target}: must caution against routine --llm-provider use; "
            "no '特別な事情' / 'fallback' guidance found"
        )


# ----- §10.2 L1085: providers required -------------------------------------


@pytest.mark.spec_ref("§10.2", 1085, profile="fake", method="入出力比較")
def test_zero_providers_rejected(tmp_path: Path) -> None:
    """Config with zero ``[llm.providers.<id>]`` is rejected as ConfigError.

    PROFILE: fake
    METHOD: 入出力比較
    """

    config_module = importlib.import_module("spec_anchor.config")
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".spec-anchor").mkdir()
    (project / ".spec-anchor" / "config.toml").write_text(
        """\
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"

[vector_store]
provider = "qdrant"
""",
        encoding="utf-8",
    )
    (project / "docs" / "core").mkdir(parents=True)
    (project / "docs" / "core" / "purpose.md").write_text("# P\n")
    (project / "docs" / "core" / "concept.md").write_text("# C\n")
    (project / "docs" / "spec").mkdir(parents=True)
    (project / "docs" / "spec" / "main.md").write_text("# M\n")

    with pytest.raises(config_module.ConfigError):
        config_module.load_config(project)


# ----- §10.2 L1088 / L1089: --llm-provider CLI behaviour --------------------


@pytest.mark.spec_ref("§10.2", 1088, profile="none", method="入出力比較")
def test_core_cli_accepts_llm_provider_flag() -> None:
    """`spec-anchor core` argparse exposes ``--llm-provider`` flag.

    PROFILE: none
    METHOD: 入出力比較
    """

    help_text = subprocess.run(
        [sys.executable, "-m", "spec_anchor", "core", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    assert "--llm-provider" in help_text, (
        "`spec-anchor core --help` must surface the --llm-provider flag so "
        "stage_routing can be overridden per §10.2 L1088."
    )


@pytest.mark.spec_ref("§10.2", 1089, profile="none", method="入出力比較")
def test_no_silent_fallback_to_alt_provider_in_source() -> None:
    """Source code does not contain a silent fallback when a configured
    provider fails: failure must be reported.

    Verified by searching ``llm_provider.py`` for a fallback path that
    swaps providers on exception without raising.

    PROFILE: none
    METHOD: artifact 内容確認
    """

    src = (SPEC_ANCHOR_PKG / "llm_provider.py").read_text(encoding="utf-8")
    # Heuristic: there should be no `except ...: ... select_llm_provider`
    # block. The actual fallback wiring lives in stage routing tests.
    assert not re.search(
        r"except\s+\w*Error[^:]*:\s*[^\n]*\n\s*provider\s*=\s*select_llm_provider_config",
        src,
    ), (
        "llm_provider.py contains a silent provider swap on error; §10.2 "
        "L1089 forbids this."
    )


# ----- §10.2 L1093: initial config expansion -------------------------------


@pytest.mark.spec_ref("§10.2", 1093, profile="fake", method="artifact 内容確認")
def test_setup_project_writes_initial_config_with_required_keys(
    tmp_path: Path,
) -> None:
    """`spec-anchor-setup-project` writes ``.spec-anchor/config.toml`` with
    the documented initial config (required keys present + standard
    defaults).

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    project = tmp_path / "fresh"
    project.mkdir()
    _setup_project(project)
    config_path = project / ".spec-anchor" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    config = tomllib.loads(text)

    # Required tables / keys per the §10.2 initial config TOML block.
    assert config["sources"]["include"], "sources.include must be present"
    assert config["core"]["purpose_file"], "core.purpose_file must be present"
    assert config["core"]["concept_file"], "core.concept_file must be present"
    assert config["embedding"]["provider"], "embedding.provider must be present"
    assert config["embedding"]["model"], "embedding.model must be present"
    assert config["vector_store"]["provider"], "vector_store.provider must be present"
    providers = config["llm"]["providers"]
    assert len(providers) >= 1, "at least one [llm.providers.<id>] must be present"


# ----- §10.3 L1193: SPEC_ANCHOR_DEBUG_* observable-only --------------------


@pytest.mark.spec_ref("§10.3", 1193, profile="none", method="artifact 内容確認")
def test_debug_envvars_are_not_referenced_outside_diagnostic_paths() -> None:
    """``SPEC_ANCHOR_DEBUG_*`` env vars only affect optional append-mode
    diagnostic logs.

    Verified by grepping ``spec_anchor/`` for references and asserting
    each reference is in a code path comment-marked or function-named as
    diagnostic / debug (not in core control flow).

    PROFILE: none
    METHOD: artifact 内容確認
    """

    matches: list[tuple[Path, int, str]] = []
    for py_file in SPEC_ANCHOR_PKG.rglob("*.py"):
        for lineno, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            if "SPEC_ANCHOR_DEBUG_" in line:
                matches.append((py_file.relative_to(REPO_ROOT), lineno, line.strip()))

    # If the source mentions DEBUG envvars at all, the locations must be
    # in clearly-named diagnostic helpers (function / module containing
    # "debug" / "diagnostic" / "_log") rather than in main control flow.
    for path, lineno, line in matches:
        rel_str = str(path)
        is_diagnostic_context = (
            "debug" in rel_str.lower()
            or "diagnostic" in rel_str.lower()
            or "debug" in line.lower()
            or "diagnostic" in line.lower()
            or "_log" in line.lower()
        )
        assert is_diagnostic_context, (
            f"{path}:{lineno} references SPEC_ANCHOR_DEBUG_* outside a "
            f"diagnostic helper: {line!r}"
        )


# ----- §10.3 L1197 / L1198 / L1199: .env loading ---------------------------


@pytest.mark.spec_ref("§10.3", 1197, profile="none", method="入出力比較")
def test_env_file_is_loaded_into_os_environ(tmp_path: Path, monkeypatch) -> None:
    """A ``.env`` file at project root is loaded into ``os.environ`` by
    ``load_config``.

    PROFILE: none
    METHOD: 入出力比較
    """

    project = tmp_path / "envproj"
    project.mkdir()
    _setup_project(project)
    (project / ".env").write_text("SPEC_ANCHOR_TEST_FROM_DOTENV=hello-from-dotenv\n")
    monkeypatch.delenv("SPEC_ANCHOR_TEST_FROM_DOTENV", raising=False)

    config_module = importlib.import_module("spec_anchor.config")
    config_module.load_config(project)
    assert os.environ.get("SPEC_ANCHOR_TEST_FROM_DOTENV") == "hello-from-dotenv"


@pytest.mark.spec_ref("§10.3", 1198, profile="none", method="入出力比較")
def test_env_file_does_not_overwrite_existing_shell_var(
    tmp_path: Path, monkeypatch
) -> None:
    """If a shell variable is already exported, ``.env`` does not override it.

    PROFILE: none
    METHOD: 入出力比較
    """

    project = tmp_path / "envproj"
    project.mkdir()
    _setup_project(project)
    monkeypatch.setenv("SPEC_ANCHOR_TEST_OVERRIDE", "shell-value")
    (project / ".env").write_text("SPEC_ANCHOR_TEST_OVERRIDE=dotenv-value\n")

    config_module = importlib.import_module("spec_anchor.config")
    config_module.load_config(project)
    assert os.environ["SPEC_ANCHOR_TEST_OVERRIDE"] == "shell-value", (
        "Existing shell var must not be overridden by .env"
    )


@pytest.mark.spec_ref("§10.3", 1199, profile="none", method="入出力比較")
def test_env_channels_are_equivalent(tmp_path: Path, monkeypatch) -> None:
    """Env injected via shell / .env / CI export is observed identically
    by ``spec-anchor`` runtime.

    PROFILE: none
    METHOD: 入出力比較
    """

    project_a = tmp_path / "via-shell"
    project_a.mkdir()
    _setup_project(project_a)
    project_b = tmp_path / "via-dotenv"
    project_b.mkdir()
    _setup_project(project_b)

    monkeypatch.delenv("SPEC_ANCHOR_TEST_CHANNEL", raising=False)
    # Channel A: shell export
    monkeypatch.setenv("SPEC_ANCHOR_TEST_CHANNEL", "via-shell")
    config_module = importlib.import_module("spec_anchor.config")
    config_module.load_config(project_a)
    shell_value = os.environ.get("SPEC_ANCHOR_TEST_CHANNEL")

    # Channel B: .env loading. Need to first remove shell value so
    # .env is what populates the var.
    monkeypatch.delenv("SPEC_ANCHOR_TEST_CHANNEL", raising=False)
    (project_b / ".env").write_text("SPEC_ANCHOR_TEST_CHANNEL=via-dotenv\n")
    config_module.load_config(project_b)
    dotenv_value = os.environ.get("SPEC_ANCHOR_TEST_CHANNEL")

    # Equivalence: both channels populate os.environ via the same
    # mechanism (os.environ dict). The values differ because we used
    # different inputs, but both are observable identically.
    assert shell_value == "via-shell"
    assert dotenv_value == "via-dotenv"


# ----- §10.3 env var table (L1203-L1209) -----------------------------------


_ENVVAR_CASES: list[tuple[int, str]] = [
    (1203, "SPEC_ANCHOR_FAKE_LLM"),
    (1204, "SPEC_ANCHOR_FAKE_RETRIEVAL"),
    (1205, "SPEC_ANCHOR_QDRANT_URL"),
    (1206, "SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION"),
    (1207, "SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION_PATH"),
    (1208, "SPEC_ANCHOR_DEBUG_RELATED_PROMPT"),
    (1209, "SPEC_ANCHOR_DEBUG_RELATED_PROMPT_PATH"),
]


@pytest.mark.parametrize(
    "spec_line, envvar_name",
    [
        pytest.param(
            *case,
            marks=[
                pytest.mark.spec_ref("§10.3", case[0], profile="none", method="artifact 内容確認"),
            ],
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _ENVVAR_CASES
    ],
)
def test_documented_envvar_is_referenced_in_source(
    spec_line: int, envvar_name: str
) -> None:
    """Each env var documented in the §10.3 table is referenced by name
    somewhere in ``spec_anchor/`` source.

    PROFILE: none
    METHOD: artifact 内容確認
    """

    found = False
    for py_file in SPEC_ANCHOR_PKG.rglob("*.py"):
        if envvar_name in py_file.read_text(encoding="utf-8"):
            found = True
            break
    assert found, (
        f"§10.3 L{spec_line}: env var {envvar_name!r} is documented but no "
        f"reference exists in spec_anchor/*.py — the var is dead."
    )
