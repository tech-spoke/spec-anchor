"""Shared core-update lock regression tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_stale_lock_eviction_does_not_remove_new_lock_created_after_read(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    from spec_grag import core_lock

    project_root = tmp_path / "project"
    lock_path = core_lock.core_update_lock_path(project_root)
    lock_path.parent.mkdir(parents=True)
    stale_payload = {
        "schema_version": 1,
        "lock_kind": "core_update",
        "owner": "watcher",
        "run_id": "stale-reader-saw-this",
        "token": "old-token",
        "acquired_at_epoch_ms": 1_000,
        "updated_at_epoch_ms": 1_000,
    }
    new_payload = {
        "schema_version": 1,
        "lock_kind": "core_update",
        "owner": "watcher",
        "run_id": "new-lock-must-survive",
        "token": "new-token",
        "acquired_at_epoch_ms": 10_000,
        "updated_at_epoch_ms": 10_000,
    }
    lock_path.write_text(json.dumps(stale_payload))

    original_read = core_lock.read_core_update_lock
    first_read = True

    def racing_read(path: str | Path) -> dict[str, Any] | None:
        nonlocal first_read
        payload = original_read(path)
        if first_read:
            first_read = False
            lock_path.write_text(json.dumps(new_payload))
            return stale_payload
        return payload

    monkeypatch.setattr(core_lock, "read_core_update_lock", racing_read)

    result = core_lock.acquire_core_update_lock(
        project_root,
        owner="spec_core",
        run_id="manual-core-run",
        stale_lock_ms=100,
        now_ms=10_000,
    )

    assert result.acquired is False
    assert json.loads(lock_path.read_text())["run_id"] == "new-lock-must-survive"


def test_lock_payload_records_pid_and_hostname(tmp_path):
    """Lock file must record holder_pid + holder_hostname for liveness check."""
    import os, socket
    from spec_grag.core_lock import (
        acquire_core_update_lock,
        read_core_update_lock,
        release_core_update_lock,
    )

    attempt = acquire_core_update_lock(tmp_path, owner="test", stale_lock_ms=60_000)
    try:
        assert attempt.acquired
        payload = read_core_update_lock(attempt.path)
        assert payload is not None
        assert payload["holder_pid"] == os.getpid()
        assert payload["holder_hostname"] == socket.gethostname()
    finally:
        release_core_update_lock(attempt.lock)


def test_lock_is_stale_detects_dead_pid(tmp_path):
    """If the lock holder's pid no longer exists on the same host, treat as stale
    even when within the stale_lock_ms TTL window."""
    import socket
    from spec_grag.core_lock import lock_is_stale, _now_ms

    # Build a lock payload as if a recent-but-dead process owns it
    now = _now_ms()
    payload = {
        "schema_version": 1,
        "lock_kind": "core_update",
        "owner": "spec_core",
        "run_id": "abc",
        "token": "tok",
        "acquired_at_epoch_ms": now - 1_000,  # 1 second ago, well within TTL
        "updated_at_epoch_ms": now - 1_000,
        "stale_lock_ms": 300_000,
        "holder_pid": 1,  # init, exists, so liveness is alive — should NOT be stale
        "holder_hostname": socket.gethostname(),
    }
    assert lock_is_stale(payload, stale_lock_ms=300_000, now_ms=now) is False

    # Use a pid that's almost certainly dead (very large number, unlikely to be in use)
    payload["holder_pid"] = 2_000_000  # PID_MAX on Linux is typically 4_194_304
    payload["holder_hostname"] = socket.gethostname()
    # Within TTL but dead pid → stale
    assert lock_is_stale(payload, stale_lock_ms=300_000, now_ms=now) is True


def test_lock_is_stale_ignores_pid_on_different_host(tmp_path):
    """Cross-host locks should not be auto-cleared by pid check."""
    from spec_grag.core_lock import lock_is_stale, _now_ms

    now = _now_ms()
    payload = {
        "schema_version": 1,
        "owner": "spec_core",
        "run_id": "abc",
        "token": "tok",
        "acquired_at_epoch_ms": now - 1_000,
        "updated_at_epoch_ms": now - 1_000,
        "stale_lock_ms": 300_000,
        "holder_pid": 2_000_000,
        "holder_hostname": "different-host-that-does-not-match",
    }
    # pid would otherwise be marked dead but host doesn't match → not stale
    assert lock_is_stale(payload, stale_lock_ms=300_000, now_ms=now) is False
