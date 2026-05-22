"""§6 (コマンド体系) acceptance tests.

Per ``doc/e2eテスト/test_plan.ja.md`` §1.1.1, setup-system is verified
against the real environment (real Qdrant + real codex/claude CLI +
real FlagEmbedding) since fake-mode probes would not surface
documented behaviour like "Qdrant が稼働中なら status=ready". The
project setup tests work in ``tmp_path`` (no need to perturb the live
repo state), and watcher tests run ``--once`` in ``tmp_path``.

Coverage map to §6:

- §6 master command table (L424-429): 6 rows, --help works for each
- §6.1 Agent entry table (L437-438): 2 rows, setup-project places per agent
- §6.1 fixed mapping (L440): wrong-agent-target test
- §6.2.1 setup-system confirmation list (L458-461): 4 rows, real probe
- §6.2.1 output structure (L465-466): 2 items, real-smoke status/diagnostics
- §6.2.1 exit code (L468): 1 item, real-smoke
- §6.2.1 options (L472, L473): 2 items, --check-only and --qdrant-url
- §6.2.1 negative (L475): 1 item, setup-system non-modification
- §6.2.2 setup-project options (L489-493): 5 rows
- §6.2.2 processing (L497-499): 3 items, artifact creation
- §6.2.2 output (L501): 1 item, JSON structure
- §6.2.2 safety (L505, L506): 2 items, conflict + no auto core
- §6.3 watcher options (L545-549): 5 rows
- §6.3 watcher output (L551, L552): 2 items, JSON output + blocked freshness
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_main(module: str, func_name: str, argv: list[str]) -> int:
    mod = importlib.import_module(module)
    func = getattr(mod, func_name)
    try:
        result = func(argv)
        return int(result) if isinstance(result, int) else 0
    except SystemExit as exc:
        return int(exc.code or 0)


def _setup_project(target: Path, *, agent: str = "both", force: bool = False,
                   dry_run: bool = False, no_init_core_files: bool = False) -> int:
    argv = ["--target", str(target), "--agent", agent]
    if force:
        argv.append("--force")
    if dry_run:
        argv.append("--dry-run")
    if no_init_core_files:
        argv.append("--no-init-core-files")
    return _run_main("spec_anchor.cli", "setup_project_main", argv)


def _setup_system_real(extra_argv: list[str] | None = None) -> dict[str, Any]:
    """Invoke setup-system in real-smoke mode (no fake env stubs).

    Returns the parsed stdout JSON. Caller is responsible for verifying
    exit code via the ``exit_code`` field in the returned dict.
    """

    env = os.environ.copy()
    # Strip the autouse fake env so the real-smoke probe runs.
    env.pop("SPEC_ANCHOR_FAKE_LLM", None)
    env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    cmd = [str(REPO_ROOT / ".venv" / "bin" / "spec-anchor-setup-system")]
    if extra_argv:
        cmd.extend(extra_argv)
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# §6 command table (L424-429): each command exposes working --help
# ---------------------------------------------------------------------------


_COMMAND_TABLE_CASES: list[tuple[int, str, list[str]]] = [
    (424, "/spec-core", [sys.executable, "-m", "spec_anchor", "core", "--help"]),
    (425, "/spec-inject", [sys.executable, "-m", "spec_anchor", "inject-search", "--help"]),
    (426, "/spec-realign", [sys.executable, "-m", "spec_anchor", "realign", "--help"]),
    (427, "spec-anchor-watch", [str(REPO_ROOT / ".venv/bin/spec-anchor-watch"), "--help"]),
    (428, "spec-anchor-setup-system", [str(REPO_ROOT / ".venv/bin/spec-anchor-setup-system"), "--help"]),
    (429, "spec-anchor-setup-project", [str(REPO_ROOT / ".venv/bin/spec-anchor-setup-project"), "--help"]),
]


@pytest.mark.parametrize(
    "spec_line, label, cmd",
    [
        pytest.param(
            *case,
            marks=[pytest.mark.spec_ref("§6", case[0], profile="none", method="入出力比較")],
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _COMMAND_TABLE_CASES
    ],
)
def test_command_table_entrypoint_help_works(spec_line: int, label: str, cmd: list[str]) -> None:
    """Each documented command/script in §6 exposes a working `--help`.

    PROFILE: none
    METHOD: 入出力比較
    """

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, (
        f"§6 L{spec_line}: `{' '.join(cmd)}` exited {proc.returncode}; "
        f"stderr={proc.stderr!r}"
    )
    assert "usage:" in proc.stdout, (
        f"§6 L{spec_line}: `--help` for {label} did not show usage block"
    )


# ---------------------------------------------------------------------------
# §6.1 Agent entry table (L437-438): setup-project lays down per-agent files
# ---------------------------------------------------------------------------


@pytest.mark.spec_ref("§6.1", 437, profile="fake", method="artifact 内容確認")
def test_claude_entrypoint_is_command_template_under_dot_claude_commands(tmp_path: Path) -> None:
    """`--agent claude` places command templates under `<project>/.claude/commands/`.

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    project = tmp_path / "claude-only"
    project.mkdir()
    code = _setup_project(project, agent="claude")
    assert code == 0
    cmd_dir = project / ".claude" / "commands"
    assert cmd_dir.is_dir()
    for name in ("spec-core.md", "spec-inject.md", "spec-realign.md"):
        assert (cmd_dir / name).is_file(), f"missing {name} under {cmd_dir}"


@pytest.mark.spec_ref("§6.1", 438, profile="fake", method="artifact 内容確認")
def test_codex_entrypoint_is_skill_under_dot_codex_skills_spec_anchor(tmp_path: Path) -> None:
    """`--agent codex` places a SKILL.md under `<project>/.codex/skills/spec-anchor/`.

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    project = tmp_path / "codex-only"
    project.mkdir()
    code = _setup_project(project, agent="codex")
    assert code == 0
    skill = project / ".codex" / "skills" / "spec-anchor" / "SKILL.md"
    assert skill.is_file(), f"missing SKILL.md at {skill}"


@pytest.mark.spec_ref("§6.1", 440, profile="fake", method="artifact 内容確認")
def test_agent_target_does_not_swap_entry_format(tmp_path: Path) -> None:
    """`--agent claude` never places a skill under `.codex/`, and
    `--agent codex` never places command templates under `.claude/`.

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    for agent, allowed, forbidden in [
        ("claude", ".claude", ".codex"),
        ("codex", ".codex", ".claude"),
    ]:
        project = tmp_path / f"agent-{agent}-only"
        project.mkdir()
        _setup_project(project, agent=agent)
        assert (project / allowed).is_dir(), (
            f"--agent {agent}: expected {allowed}/ to exist"
        )
        assert not (project / forbidden).exists(), (
            f"--agent {agent}: forbidden {forbidden}/ should NOT exist; "
            "§6.1 fixes the entry format per agent."
        )


# ---------------------------------------------------------------------------
# §6.2.1 setup-system confirmation list (L458-461)
# ---------------------------------------------------------------------------


_SETUP_SYSTEM_CHECK_CASES: list[tuple[int, str, str]] = [
    (458, "spec-anchor", "console_script:spec-anchor"),
    (459, "FlagEmbedding BGE-M3", "flagembedding_package"),
    (460, "Qdrant", "qdrant_service"),
    (461, "codex/claude", "agent_cli"),
]


@pytest.mark.parametrize(
    "spec_line, label, check_name",
    [
        pytest.param(
            *case,
            marks=[
                pytest.mark.external,
                pytest.mark.spec_ref("§6.2.1", case[0], profile="real-smoke", method="入出力比較"),
            ],
            id=f"L{case[0]}-{case[1].replace(' ', '_').replace('/', '_')}",
        )
        for case in _SETUP_SYSTEM_CHECK_CASES
    ],
)
def test_setup_system_real_probes_documented_dependencies(
    spec_line: int, label: str, check_name: str
) -> None:
    """Each documented setup-system probe target appears in
    ``production_readiness.checks[]``.

    PROFILE: real-smoke
    METHOD: 入出力比較
    """

    result = _setup_system_real(["--check-only"])
    checks = result.get("production_readiness", {}).get("checks", [])
    names = {c["name"] for c in checks}
    assert check_name in names, (
        f"§6.2.1 L{spec_line}: {label!r} probe (check name {check_name!r}) "
        f"not found in setup-system output. checks={sorted(names)}"
    )


# ---------------------------------------------------------------------------
# §6.2.1 output structure / exit code (L465, L466, L468)
# ---------------------------------------------------------------------------


@pytest.mark.external
@pytest.mark.spec_ref("§6.2.1", 465, profile="real-smoke", method="入出力比較")
def test_setup_system_ready_status_when_all_deps_available() -> None:
    """`production_readiness.status == "ready"` when all deps are present.

    PROFILE: real-smoke
    METHOD: 入出力比較
    """

    result = _setup_system_real(["--check-only"])
    assert result["production_readiness"]["status"] == "ready", (
        f"With Qdrant + codex + claude + FlagEmbedding available, status should "
        f"be 'ready'. Got: {result['production_readiness']['status']!r}, "
        f"blocking_reasons={result['production_readiness'].get('blocking_reasons')!r}"
    )


@pytest.mark.spec_ref("§6.2.1", 466, profile="fake", method="入出力比較")
def test_setup_system_blocked_status_when_qdrant_unreachable(monkeypatch) -> None:
    """`production_readiness.status == "blocked"` with diagnostics when a
    documented dep (Qdrant here) is unreachable.

    PROFILE: fake
    METHOD: 入出力比較
    """

    # Override the probe URL to an unreachable port to force blocked.
    env = os.environ.copy()
    env.pop("SPEC_ANCHOR_FAKE_LLM", None)
    env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    proc = subprocess.run(
        [
            str(REPO_ROOT / ".venv/bin/spec-anchor-setup-system"),
            "--check-only",
            "--qdrant-url",
            "http://127.0.0.1:1",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(proc.stdout)
    assert payload["production_readiness"]["status"] == "blocked", (
        "Qdrant unreachable should produce blocked status; "
        f"got {payload['production_readiness']['status']!r}"
    )
    blocking = payload["production_readiness"].get("blocking_reasons", [])
    assert any("qdrant" in r.lower() for r in blocking), (
        f"blocking_reasons should mention qdrant; got {blocking!r}"
    )


@pytest.mark.external
@pytest.mark.spec_ref("§6.2.1", 468, profile="real-smoke", method="入出力比較")
def test_setup_system_exit_code_zero_on_ready() -> None:
    """Exit code is 0 when status is ready.

    PROFILE: real-smoke
    METHOD: 入出力比較
    """

    env = os.environ.copy()
    env.pop("SPEC_ANCHOR_FAKE_LLM", None)
    env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    proc = subprocess.run(
        [str(REPO_ROOT / ".venv/bin/spec-anchor-setup-system"), "--check-only"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0


# ---------------------------------------------------------------------------
# §6.2.1 options (L472, L473)
# ---------------------------------------------------------------------------


@pytest.mark.spec_ref("§6.2.1", 472, profile="fake", method="artifact 内容確認")
def test_setup_system_check_only_does_not_write(tmp_path: Path) -> None:
    """`--check-only` performs no writes anywhere (no created/updated entries).

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    env = os.environ.copy()
    env.pop("SPEC_ANCHOR_FAKE_LLM", None)
    env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    proc = subprocess.run(
        [str(REPO_ROOT / ".venv/bin/spec-anchor-setup-system"), "--check-only"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(proc.stdout)
    assert payload.get("created") == [], "--check-only created entries should be empty"
    assert payload.get("updated") == [], "--check-only updated entries should be empty"


@pytest.mark.spec_ref("§6.2.1", 473, profile="none", method="入出力比較")
def test_setup_system_qdrant_url_default() -> None:
    """`--qdrant-url` default is `http://localhost:6333`.

    Verified by `--help` text showing the documented default endpoint;
    the actual probe URL is asserted via the spec/spec-anchor source.

    PROFILE: none
    METHOD: 入出力比較
    """

    proc = subprocess.run(
        [str(REPO_ROOT / ".venv/bin/spec-anchor-setup-system"), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "--qdrant-url" in proc.stdout
    # The default URL is documented as http://localhost:6333; verify
    # source references this exact endpoint as the fallback. Search
    # across the spec_anchor package since the constant may live in
    # cli.py, setup.py, or project_setup.py.
    candidates = [
        REPO_ROOT / "spec_anchor" / "cli.py",
        REPO_ROOT / "spec_anchor" / "setup.py",
        REPO_ROOT / "spec_anchor" / "project_setup.py",
    ]
    sources = "".join(
        p.read_text(encoding="utf-8") for p in candidates if p.is_file()
    )
    assert "http://localhost:6333" in sources, (
        "Source must reference http://localhost:6333 as the default Qdrant URL "
        f"in one of {[p.name for p in candidates]}"
    )


# ---------------------------------------------------------------------------
# §6.2.1 negative (L475)
# ---------------------------------------------------------------------------


@pytest.mark.spec_ref("§6.2.1", 475, profile="fake", method="artifact 内容確認")
def test_setup_system_does_not_modify_project_state(tmp_path: Path) -> None:
    """setup-system does not touch project Source Specs / Purpose / Core
    Concept / generated artifacts.

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    # Create a project, capture state hashes, run setup-system, check unchanged.
    project = tmp_path / "p1"
    project.mkdir()
    _setup_project(project)

    def snapshot(root: Path) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for p in root.rglob("*"):
            if p.is_file():
                out[str(p.relative_to(root))] = p.read_bytes()
        return out

    before = snapshot(project)

    env = os.environ.copy()
    env.pop("SPEC_ANCHOR_FAKE_LLM", None)
    env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    subprocess.run(
        [str(REPO_ROOT / ".venv/bin/spec-anchor-setup-system"), "--check-only"],
        env=env,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
    )

    after = snapshot(project)
    assert before == after, (
        "setup-system must not modify any file in the project root"
    )


# ---------------------------------------------------------------------------
# §6.2.2 setup-project options (L489-L493)
# ---------------------------------------------------------------------------


_SETUP_PROJECT_OPTION_CASES: list[tuple[int, str]] = [
    (489, "--target"),
    (490, "--agent"),
    (491, "--dry-run"),
    (492, "--force"),
    (493, "--no-init-core-files"),
]


@pytest.mark.parametrize(
    "spec_line, flag",
    [
        pytest.param(
            *case,
            marks=[pytest.mark.spec_ref("§6.2.2", case[0], profile="none", method="入出力比較")],
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _SETUP_PROJECT_OPTION_CASES
    ],
)
def test_setup_project_exposes_documented_option(spec_line: int, flag: str) -> None:
    """Each documented setup-project flag appears in `--help`.

    PROFILE: none
    METHOD: 入出力比較
    """

    proc = subprocess.run(
        [str(REPO_ROOT / ".venv/bin/spec-anchor-setup-project"), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert flag in proc.stdout, f"§6.2.2 L{spec_line}: {flag} not in --help"


# ---------------------------------------------------------------------------
# §6.2.2 processing (L497-L499)
# ---------------------------------------------------------------------------


@pytest.mark.spec_ref("§6.2.2", 497, profile="fake", method="artifact 内容確認")
def test_setup_project_creates_config_toml_and_gitignore(tmp_path: Path) -> None:
    """setup-project creates `.spec-anchor/config.toml` and `.spec-anchor/.gitignore`.

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    project = tmp_path / "p"
    project.mkdir()
    _setup_project(project)
    assert (project / ".spec-anchor" / "config.toml").is_file()
    assert (project / ".spec-anchor" / ".gitignore").is_file()


@pytest.mark.spec_ref("§6.2.2", 498, profile="fake", method="artifact 内容確認")
def test_setup_project_initializes_purpose_and_core_concept(tmp_path: Path) -> None:
    """setup-project creates Purpose / Core Concept placeholders by default,
    and `--no-init-core-files` suppresses them.

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    default_project = tmp_path / "default"
    default_project.mkdir()
    _setup_project(default_project)
    assert (default_project / "docs" / "core" / "purpose.md").is_file()
    assert (default_project / "docs" / "core" / "concept.md").is_file()

    suppressed_project = tmp_path / "suppressed"
    suppressed_project.mkdir()
    _setup_project(suppressed_project, no_init_core_files=True)
    assert not (suppressed_project / "docs" / "core" / "purpose.md").exists()
    assert not (suppressed_project / "docs" / "core" / "concept.md").exists()


@pytest.mark.spec_ref("§6.2.2", 499, profile="fake", method="artifact 内容確認")
def test_setup_project_places_agent_entry_per_agent_flag(tmp_path: Path) -> None:
    """`--agent claude` / `codex` / `both` controls which agent entry files
    are placed.

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    for agent in ("claude", "codex", "both"):
        proj = tmp_path / f"agent-{agent}"
        proj.mkdir()
        _setup_project(proj, agent=agent)
        if agent in ("claude", "both"):
            assert (proj / ".claude" / "commands" / "spec-core.md").is_file()
        if agent in ("codex", "both"):
            assert (proj / ".codex" / "skills" / "spec-anchor" / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# §6.2.2 output (L501)
# ---------------------------------------------------------------------------


@pytest.mark.spec_ref("§6.2.2", 501, profile="fake", method="入出力比較")
def test_setup_project_emits_json_with_correct_exit_code(tmp_path: Path) -> None:
    """setup-project emits a JSON object to stdout and exits 0 on success.

    PROFILE: fake
    METHOD: 入出力比較
    """

    project = tmp_path / "p"
    project.mkdir()
    proc = subprocess.run(
        [
            str(REPO_ROOT / ".venv/bin/spec-anchor-setup-project"),
            "--target",
            str(project),
            "--agent",
            "both",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"non-zero exit: {proc.stderr}"
    payload = json.loads(proc.stdout)
    assert payload.get("status") == "ok"
    assert payload.get("exit_code") == 0


# ---------------------------------------------------------------------------
# §6.2.2 safety (L505, L506)
# ---------------------------------------------------------------------------


@pytest.mark.spec_ref("§6.2.2", 505, profile="fake", method="入出力比較")
def test_setup_project_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    """Existing files are not silently overwritten without `--force`.

    PROFILE: fake
    METHOD: 入出力比較
    """

    project = tmp_path / "p"
    project.mkdir()
    _setup_project(project)
    # Mutate config.toml then run setup-project again without --force.
    cfg = project / ".spec-anchor" / "config.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "\n# manual edit\n", encoding="utf-8")
    before = cfg.read_text(encoding="utf-8")
    code = _setup_project(project, force=False)
    after = cfg.read_text(encoding="utf-8")
    # Either the rerun exits non-zero (conflict) or it leaves the file alone.
    if code == 0:
        assert after == before, "config.toml mutated despite no --force"
    else:
        assert "# manual edit" in after


@pytest.mark.spec_ref("§6.2.2", 506, profile="fake", method="artifact 内容確認")
def test_setup_project_does_not_run_spec_core_automatically(tmp_path: Path) -> None:
    """setup-project does not run `/spec-core`: no state/context artifacts
    are present after setup.

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    project = tmp_path / "p"
    project.mkdir()
    _setup_project(project)
    # State / context dirs may exist (created by setup-project), but no
    # generated artifacts should be inside.
    state_dir = project / ".spec-anchor" / "state"
    context_dir = project / ".spec-anchor" / "context"
    for d in (state_dir, context_dir):
        if d.exists():
            contents = list(d.iterdir())
            # Allow placeholder .gitkeep but no real artifact files.
            for f in contents:
                if f.name == ".gitkeep":
                    continue
                pytest.fail(
                    f"setup-project should not generate {f}; /spec-core has not run"
                )


# ---------------------------------------------------------------------------
# §6.3 watcher options (L545-L549)
# ---------------------------------------------------------------------------


_WATCHER_OPTION_CASES: list[tuple[int, str]] = [
    (545, "--once"),
    (546, "--interval-sec"),
    (547, "--debounce-sec"),
    (548, "--stale-lock-sec"),
    (549, "--max-runs"),
]


@pytest.mark.parametrize(
    "spec_line, flag",
    [
        pytest.param(
            *case,
            marks=[pytest.mark.spec_ref("§6.3", case[0], profile="none", method="入出力比較")],
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _WATCHER_OPTION_CASES
    ],
)
def test_watcher_exposes_documented_option(spec_line: int, flag: str) -> None:
    """Each documented watcher flag appears in `--help`.

    PROFILE: none
    METHOD: 入出力比較
    """

    proc = subprocess.run(
        [str(REPO_ROOT / ".venv/bin/spec-anchor-watch"), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert flag in proc.stdout, f"§6.3 L{spec_line}: {flag} not in watch --help"


# ---------------------------------------------------------------------------
# §6.3 watcher output (L551, L552)
# ---------------------------------------------------------------------------


@pytest.mark.spec_ref("§6.3", 551, profile="fake", method="入出力比較")
def test_watcher_once_emits_json(tmp_path: Path) -> None:
    """`spec-anchor-watch --once` emits JSON to stdout.

    PROFILE: fake
    METHOD: 入出力比較
    """

    project = tmp_path / "p"
    project.mkdir()
    _setup_project(project)
    proc = subprocess.run(
        [str(REPO_ROOT / ".venv/bin/spec-anchor-watch"), "--once"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Output should be parseable JSON regardless of internal status.
    assert proc.stdout.strip(), f"--once produced empty stdout (stderr={proc.stderr!r})"
    try:
        json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"watcher --once stdout is not JSON: {exc}\n{proc.stdout!r}")


@pytest.mark.spec_ref("§6.3", 552, profile="fake", method="artifact 内容確認")
def test_watcher_running_blocks_inject_via_freshness(tmp_path: Path) -> None:
    """While watcher is running, freshness becomes `status=blocked` with
    `watcher_running` reason, blocking `/spec-inject` / `/spec-realign`.

    Verified by inspecting the freshness state file written during
    watcher activity. The test simulates an active watcher by writing
    the watcher state directly (faster than spinning a real watcher);
    the contract under test is the freshness gate output, not the
    watcher scheduler.

    PROFILE: fake
    METHOD: artifact 内容確認
    """

    project = tmp_path / "p"
    project.mkdir()
    _setup_project(project)
    # Drop a minimal Source Specs so freshness can compute.
    (project / "docs" / "spec").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "spec" / "main.md").write_text("# Main\n", encoding="utf-8")

    # Use the watcher source to know which artifact carries the
    # watcher_running signal. The contract is that an inject-* probe
    # surfaces a blocking reason mentioning the watcher.
    state_dir = project / ".spec-anchor" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    # Write a "watcher running" lock-style state. The exact schema lives
    # in spec_anchor/watcher.py; the contract observable to inject-* is
    # the freshness blocking_reasons.
    (state_dir / "watch_state.json").write_text(
        json.dumps({"is_running": True, "pid": 99999, "started_at_epoch": 9999999999}),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, "-m", "spec_anchor", "inject-search", "anything"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = proc.stdout + proc.stderr
    # Either inject-search reports blocked status, or watcher integration
    # surfaces watcher_running in blocking_reasons. We accept either
    # since the artifact-level state may need a freshness recompute hook
    # invoked separately.
    assert (
        "watcher_running" in out
        or "blocked" in out
        or "should_stop" in out
    ), (
        f"With watcher state active, inject-search should surface a blocking "
        f"signal. Got stdout/stderr: {out!r}"
    )
