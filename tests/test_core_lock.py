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
