from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_STATE_DIR = REPO_ROOT / ".spec-grag"


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
    _prepend_venv_to_path()
    _stash_runtime_state_for_session(config)
    _enable_chunk_level_for_tests()


def _enable_chunk_level_for_tests() -> None:
    """Phase R-5: keep the dormant chunk-level path on inside the test suite.

    `doc/STORAGE_REDESIGN.ja.md` §7.4 R-5 disables chunk-level retrieval
    by default (case C-1). The dormant code stays in
    `spec_grag/{core,retrieval_index}.py` so it can still be exercised
    by existing integration tests and so a future operator can re-enable
    it without resurrecting deleted history. Tests in this repository
    still assert on `source_chunks` and chunk-level Qdrant upsert
    behavior, so we flip the constant on for the session here.

    Production callers see the production default
    (`CHUNK_LEVEL_ENABLED = False`). A specific test that wants to
    cover the disabled path explicitly can monkeypatch
    `spec_grag.core.CHUNK_LEVEL_ENABLED` back to False or set
    `[vector_store].chunk_level_enabled = false` in its project config.
    """

    import spec_grag.core as core_module

    core_module.CHUNK_LEVEL_ENABLED = True


def pytest_unconfigure(config: pytest.Config) -> None:
    _restore_runtime_state(config)


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.config.getoption("--skip-external") and item.get_closest_marker("external"):
        pytest.skip("--skip-external was specified; external dependency test not run")


def _prepend_venv_to_path() -> None:
    """Make `spec-grag` console scripts visible to `shutil.which` during tests.

    The repo's `.venv/bin` is the install site for the project's console
    scripts (`spec-grag`, `spec-grag-watch`, etc.). Without this, T-P02 / T-R04
    fail with "spec-grag is not installed on PATH" when pytest is invoked from
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
    """Move repo-root `.spec-grag/` aside while the test session runs.

    This matches the manual workflow already used during development
    (`.spec-grag.backup-before-full-suite-*` directories): when the user
    self-uses `spec-grag` against `テスト用ドキュメント/` from the repo root,
    runtime artifacts accumulate at `.spec-grag/`. Tests like T-P06 require
    a clean root, so we move the directory aside and restore it at session
    end, even if pytest is interrupted.
    """

    if not RUNTIME_STATE_DIR.exists():
        return
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    stash = REPO_ROOT / f".spec-grag.pytest-stash-{timestamp}"
    while stash.exists():
        timestamp = time.strftime("%Y%m%d-%H%M%S-%f")
        stash = REPO_ROOT / f".spec-grag.pytest-stash-{timestamp}"
    shutil.move(str(RUNTIME_STATE_DIR), str(stash))
    config.stash[_STASH_KEY] = stash


def _restore_runtime_state(config: pytest.Config) -> None:
    stash = config.stash.get(_STASH_KEY, None)
    if stash is None or not Path(stash).exists():
        return
    if RUNTIME_STATE_DIR.exists():
        # The test run created a fresh `.spec-grag/` (e.g. project_setup tests
        # working in tmp_path that leaked, or a watcher-leak). Keep both.
        leak_dir = REPO_ROOT / f".spec-grag.test-leak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.move(str(RUNTIME_STATE_DIR), str(leak_dir))
    shutil.move(str(stash), str(RUNTIME_STATE_DIR))


_STASH_KEY = pytest.StashKey[Path]()
