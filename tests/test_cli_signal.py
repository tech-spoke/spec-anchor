"""Tests for SIGTERM → SystemExit conversion in CLI entry points.

`/spec-core` runs hold a `.spec-grag/state/core_update.lock.json` lock that
must be released via `try/finally`. Python's default SIGTERM handler kills
the process without unwinding the stack, so the lock would leak after a
``kill PID``. The CLI installs a SIGTERM handler that calls ``sys.exit``,
which raises ``SystemExit`` and lets ``release_core_update_lock`` run.
"""

from __future__ import annotations

import signal
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spec_grag.cli import _install_termination_handler


def test_install_termination_handler_replaces_default(monkeypatch):
    """After install, SIGTERM handler must call sys.exit (raises SystemExit)."""
    captured = []

    def fake_signal(sig, handler):
        captured.append((sig, handler))
        return signal.SIG_DFL

    monkeypatch.setattr(signal, "signal", fake_signal)
    _install_termination_handler()
    assert any(sig == signal.SIGTERM for sig, _ in captured)

    # The installed handler must call sys.exit, which raises SystemExit
    handler = next(h for sig, h in captured if sig == signal.SIGTERM)
    with pytest.raises(SystemExit) as exc_info:
        handler(signal.SIGTERM, None)
    assert exc_info.value.code == 128 + signal.SIGTERM


def test_install_termination_handler_silently_skips_when_unsupported(monkeypatch):
    """Calling outside the main thread (signal.signal raises ValueError)
    must not propagate — caller can install their own handling."""

    def fake_signal(sig, handler):
        raise ValueError("signal only works in main thread of the main interpreter")

    monkeypatch.setattr(signal, "signal", fake_signal)
    # Should not raise
    _install_termination_handler()
