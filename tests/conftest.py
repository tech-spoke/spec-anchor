from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from spec_anchor.testing.evidence import EvidenceCollector


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_STATE_DIR = REPO_ROOT / ".spec-anchor"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--skip-external",
        action="store_true",
        default=False,
        help=(
            "skip tests that require external dependencies such as Codex/Claude CLI, "
            "Qdrant, FlagEmbedding BGE-M3, or native service readiness checks"
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "external: test requires external dependencies such as Agent CLI, Qdrant, "
        "FlagEmbedding BGE-M3, or native service readiness checks",
    )
    config.addinivalue_line(
        "markers",
        "spec_ref(section, line, profile=None, method=None): attach a "
        "per-parametrize-row SPEC_REF used by the evidence collector when "
        "docstring-level SPEC_REF is too coarse",
    )
    _prepend_venv_to_path()
    _stash_runtime_state_for_session(config)


def pytest_unconfigure(config: pytest.Config) -> None:
    _restore_runtime_state(config)


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.config.getoption("--skip-external") and item.get_closest_marker("external"):
        pytest.skip("--skip-external was specified; external dependency test not run")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Capture test outcome for the evidence map.

    SPEC_REF / PROFILE / METHOD parsing happens inside ``EvidenceCollector``
    so this hook can stay terse and side-effect free in the failure path.
    """

    outcome = yield
    report = outcome.get_result()
    EvidenceCollector.instance().record(item, report)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Persist ``evidence_map.jsonl`` once the session ends."""

    EvidenceCollector.instance().flush()


@pytest.fixture(autouse=True)
def _default_fake_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests default to in-process fake LLM + fake retrieval so that fixtures
    do not spawn real `codex` / `claude` subprocesses or download FlagEmbedding
    BGE-M3 weights. Real-mode integration tests opt out per concern via
    ``monkeypatch.delenv("SPEC_ANCHOR_FAKE_LLM", raising=False)`` and / or
    ``monkeypatch.delenv("SPEC_ANCHOR_FAKE_RETRIEVAL", raising=False)``.
    """

    monkeypatch.setenv("SPEC_ANCHOR_FAKE_LLM", "1")
    monkeypatch.setenv("SPEC_ANCHOR_FAKE_RETRIEVAL", "1")


def _prepend_venv_to_path() -> None:
    """Make `spec-anchor` console scripts visible to `shutil.which` during tests.

    The repo's `.venv/bin` is the install site for the project's console
    scripts (`spec-anchor`, `spec-anchor-watch`, etc.). Without this, T-P02 / T-R04
    fail with "spec-anchor is not installed on PATH" when pytest is invoked from
    a shell that has not activated the venv.
    """

    venv_bin = REPO_ROOT / ".venv" / "bin"
    if not venv_bin.is_dir():
        return
    current_path = os.environ.get("PATH", "")
    parts = current_path.split(os.pathsep) if current_path else []
    if str(venv_bin) in parts:
        return
    os.environ["PATH"] = os.pathsep.join([str(venv_bin), *parts])


def _stash_runtime_state_for_session(config: pytest.Config) -> None:
    """Move repo-root `.spec-anchor/` aside while the test session runs.

    This matches the manual workflow already used during development
    (`.spec-anchor.backup-before-full-suite-*` directories): when the user
    self-uses `spec-anchor` against `テスト用ドキュメント/` from the repo root,
    runtime artifacts accumulate at `.spec-anchor/`. Tests like T-P06 require
    a clean root, so we move the directory aside and restore it at session
    end, even if pytest is interrupted.
    """

    if not RUNTIME_STATE_DIR.exists():
        return
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    stash = REPO_ROOT / f".spec-anchor.pytest-stash-{timestamp}"
    while stash.exists():
        timestamp = time.strftime("%Y%m%d-%H%M%S-%f")
        stash = REPO_ROOT / f".spec-anchor.pytest-stash-{timestamp}"
    shutil.move(str(RUNTIME_STATE_DIR), str(stash))
    config.stash[_STASH_KEY] = stash


def _restore_runtime_state(config: pytest.Config) -> None:
    stash = config.stash.get(_STASH_KEY, None)
    if stash is None or not Path(stash).exists():
        return
    if RUNTIME_STATE_DIR.exists():
        # The test run created a fresh `.spec-anchor/` (e.g. project_setup tests
        # working in tmp_path that leaked, or a watcher-leak). Keep both.
        leak_dir = REPO_ROOT / f".spec-anchor.test-leak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.move(str(RUNTIME_STATE_DIR), str(leak_dir))
    shutil.move(str(stash), str(RUNTIME_STATE_DIR))


_STASH_KEY = pytest.StashKey[Path]()
