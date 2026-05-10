"""Shared lock helpers for SPEC-grag core artifact updates."""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]


DEFAULT_CORE_LOCK_FILE = ".spec-grag/state/core_update.lock.json"
DEFAULT_STALE_LOCK_MS = 300000
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CoreUpdateLock:
    path: Path
    owner: str
    run_id: str
    token: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class LockAttempt:
    acquired: bool
    path: Path
    lock: CoreUpdateLock | None = None
    existing_lock: dict[str, Any] | None = None
    stale_lock_discarded: bool = False
    stale_lock: dict[str, Any] | None = None
    reason: str = "locked"


def core_update_lock_path(project_root: str | Path) -> Path:
    return Path(project_root).expanduser().resolve() / DEFAULT_CORE_LOCK_FILE


def acquire_core_update_lock(
    project_root: str | Path,
    *,
    owner: str,
    run_id: str | None = None,
    stale_lock_ms: int = DEFAULT_STALE_LOCK_MS,
    now_ms: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> LockAttempt:
    """Create the shared core-update lock atomically or report who holds it."""

    path = core_update_lock_path(project_root)
    now = _now_ms() if now_ms is None else int(now_ms)
    run_id = run_id or str(uuid.uuid4())
    token = str(uuid.uuid4())
    stale_discarded = False
    stale_lock: dict[str, Any] | None = None

    for _ in range(2):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _lock_payload(
            owner=owner,
            run_id=run_id,
            token=token,
            now_ms=now,
            stale_lock_ms=stale_lock_ms,
            metadata=metadata,
        )
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = read_core_update_lock(path)
            if existing and lock_is_stale(existing, stale_lock_ms=stale_lock_ms, now_ms=now):
                stale_lock = _stale_lock_summary(existing, now_ms=now)
                if not _unlink_lock_if_unchanged(
                    path,
                    expected=existing,
                    stale_lock_ms=stale_lock_ms,
                    now_ms=now,
                    require_stale=True,
                ):
                    current = read_core_update_lock(path) or existing
                    return LockAttempt(
                        acquired=False,
                        path=path,
                        existing_lock=current,
                        stale_lock_discarded=stale_discarded,
                        stale_lock=stale_lock,
                        reason=lock_blocking_reason(current),
                    )
                stale_discarded = True
                continue
            return LockAttempt(
                acquired=False,
                path=path,
                existing_lock=existing,
                stale_lock_discarded=stale_discarded,
                stale_lock=stale_lock,
                reason=lock_blocking_reason(existing),
            )
        except OSError:
            raise
        else:
            try:
                with os.fdopen(fd, "w") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                path.unlink(missing_ok=True)
                raise
            lock = CoreUpdateLock(path=path, owner=owner, run_id=run_id, token=token, payload=payload)
            return LockAttempt(
                acquired=True,
                path=path,
                lock=lock,
                stale_lock_discarded=stale_discarded,
                stale_lock=stale_lock,
            )

    existing = read_core_update_lock(path)
    return LockAttempt(
        acquired=False,
        path=path,
        existing_lock=existing,
        stale_lock_discarded=stale_discarded,
        stale_lock=stale_lock,
        reason=lock_blocking_reason(existing),
    )


def release_core_update_lock(lock: CoreUpdateLock | None) -> None:
    """Release a lock only when the lock file still belongs to this process."""

    if lock is None:
        return
    _unlink_lock_if_unchanged(
        lock.path,
        expected=lock.payload,
        stale_lock_ms=None,
        now_ms=None,
        require_stale=False,
    )


def cleanup_stale_core_update_lock(
    project_root: str | Path,
    *,
    stale_lock_ms: int = DEFAULT_STALE_LOCK_MS,
    now_ms: int | None = None,
) -> dict[str, Any] | None:
    """Remove a stale shared lock after re-checking that the same lock remains."""

    path = core_update_lock_path(project_root)
    now = _now_ms() if now_ms is None else int(now_ms)
    existing = read_core_update_lock(path)
    if not existing or not lock_is_stale(existing, stale_lock_ms=stale_lock_ms, now_ms=now):
        return None
    stale_lock = _stale_lock_summary(existing, now_ms=now)
    if _unlink_lock_if_unchanged(
        path,
        expected=existing,
        stale_lock_ms=stale_lock_ms,
        now_ms=now,
        require_stale=True,
    ):
        return stale_lock
    return None


def heartbeat_core_update_lock(
    lock: CoreUpdateLock | None,
    *,
    now_ms: int | None = None,
    timestamp_ms: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> bool:
    """Refresh a held lock's heartbeat after confirming its owner token."""

    if lock is None:
        return False
    if now_ms is not None:
        now = int(now_ms)
    elif timestamp_ms is not None:
        now = int(timestamp_ms)
    else:
        now = _now_ms()
    try:
        with _eviction_guard(lock.path):
            current = read_core_update_lock(lock.path)
            if not _same_lock_identity(lock.payload, current):
                return False
            payload = dict(current or {})
            payload["updated_at"] = _timestamp_ms(now)
            payload["updated_at_epoch_ms"] = now
            if metadata:
                current_metadata = payload.get("metadata")
                merged_metadata = (
                    dict(current_metadata)
                    if isinstance(current_metadata, Mapping)
                    else {}
                )
                merged_metadata.update(dict(metadata))
                payload["metadata"] = _jsonable(merged_metadata)
            _write_lock_payload(lock.path, payload)
            lock.payload.clear()
            lock.payload.update(_jsonable(payload))
            return True
    except OSError:
        return False


def read_core_update_lock(path: str | Path) -> dict[str, Any] | None:
    lock_path = Path(path)
    if not lock_path.is_file():
        return None
    try:
        payload = json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError):
        try:
            mtime_ms = int(lock_path.stat().st_mtime * 1000)
        except OSError:
            return None
        return {
            "schema_version": SCHEMA_VERSION,
            "unreadable": True,
            "updated_at_epoch_ms": mtime_ms,
        }
    if isinstance(payload, Mapping):
        return dict(payload)
    return None


def lock_blocking_reason(lock_payload: Mapping[str, Any] | None) -> str:
    owner = str((lock_payload or {}).get("owner") or "").lower()
    if owner.startswith("watcher"):
        return "watcher_running"
    return "locked"


def lock_diagnostics(lock_payload: Mapping[str, Any] | None, *, path: str | Path) -> dict[str, Any]:
    payload = dict(lock_payload or {})
    return {
        "lock_file": Path(path).as_posix(),
        "owner": payload.get("owner"),
        "run_id": payload.get("run_id"),
        "acquired_at": payload.get("acquired_at"),
        "acquired_at_epoch_ms": payload.get("acquired_at_epoch_ms"),
        "updated_at": payload.get("updated_at"),
        "updated_at_epoch_ms": payload.get("updated_at_epoch_ms"),
        "reason": lock_blocking_reason(payload),
    }


def lock_age_ms(lock_payload: Mapping[str, Any], *, now_ms: int) -> int:
    return _lock_age_ms(lock_payload, now_ms=now_ms)


def lock_is_stale(lock_payload: Mapping[str, Any], *, stale_lock_ms: int, now_ms: int) -> bool:
    # PID liveness fast-path: if the holder process on this host is gone,
    # consider the lock stale regardless of the TTL window. Avoids a
    # multi-minute wait after a SIGKILL or crash.
    if _holder_process_dead(lock_payload):
        return True
    return _lock_epoch_ms(lock_payload) > 0 and lock_age_ms(lock_payload, now_ms=now_ms) > int(stale_lock_ms)


def _lock_payload(
    *,
    owner: str,
    run_id: str,
    token: str,
    now_ms: int,
    stale_lock_ms: int,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "lock_kind": "core_update",
        "owner": owner,
        "run_id": run_id,
        "token": token,
        "acquired_at": _timestamp_ms(now_ms),
        "acquired_at_epoch_ms": now_ms,
        "updated_at": _timestamp_ms(now_ms),
        "updated_at_epoch_ms": now_ms,
        "stale_lock_ms": int(stale_lock_ms),
        # PID + hostname for liveness check (next run can detect a dead
        # holder on the same host even before stale_lock_ms expires).
        "holder_pid": os.getpid(),
        "holder_hostname": _hostname(),
    }
    if metadata:
        payload["metadata"] = _jsonable(dict(metadata))
    return payload


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return ""


def _holder_process_dead(lock_payload: Mapping[str, Any]) -> bool:
    """Return True if the lock holder's PID is no longer alive on this host.

    Used as an early stale-lock signal that doesn't wait for ``stale_lock_ms``
    to expire. Only acts when the lock was acquired on the same machine
    (``holder_hostname`` matches) so cross-host locks (rare for spec-grag) are
    not falsely cleared.
    """

    pid = lock_payload.get("holder_pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    holder_host = lock_payload.get("holder_hostname")
    if not isinstance(holder_host, str) or not holder_host:
        return False
    if holder_host != _hostname():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        # Process exists but we can't signal it; treat as alive to be safe.
        return False
    except OSError:
        return False
    return False


def _stale_lock_summary(lock_payload: Mapping[str, Any], *, now_ms: int) -> dict[str, Any]:
    return {
        "owner": lock_payload.get("owner"),
        "run_id": lock_payload.get("run_id"),
        "token": lock_payload.get("token"),
        "acquired_at": lock_payload.get("acquired_at"),
        "updated_at": lock_payload.get("updated_at"),
        "updated_at_epoch_ms": lock_payload.get("updated_at_epoch_ms"),
        "stale_age_ms": _lock_age_ms(lock_payload, now_ms=now_ms),
    }


def _unlink_lock_if_unchanged(
    path: Path,
    *,
    expected: Mapping[str, Any],
    stale_lock_ms: int | None,
    now_ms: int | None,
    require_stale: bool,
) -> bool:
    """Unlink a lock only after serializing evictors and re-checking identity."""

    try:
        with _eviction_guard(path):
            current = read_core_update_lock(path)
            if not _same_lock_payload(expected, current):
                return False
            if require_stale:
                if stale_lock_ms is None or now_ms is None:
                    return False
                if not lock_is_stale(current, stale_lock_ms=stale_lock_ms, now_ms=now_ms):
                    return False
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            _fsync_parent(path)
            return True
    except OSError:
        return False


@contextmanager
def _eviction_guard(path: Path):
    guard_path = path.with_name(f".{path.name}.evict.lock")
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(guard_path, os.O_RDWR | os.O_CREAT, 0o600)
    locked = False
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        yield
    except BlockingIOError:
        raise OSError(f"lock eviction already in progress: {path}")
    finally:
        if locked and fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _same_lock_payload(expected: Mapping[str, Any], current: Mapping[str, Any] | None) -> bool:
    return _same_lock_identity(expected, current)


def _same_lock_identity(expected: Mapping[str, Any], current: Mapping[str, Any] | None) -> bool:
    if current is None:
        return False
    for key in ("owner", "run_id", "token"):
        if expected.get(key) != current.get(key):
            return False
    return True


def _fsync_parent(path: Path) -> None:
    try:
        fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _write_lock_payload(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(
                _jsonable(dict(payload)),
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_parent(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _lock_age_ms(lock_payload: Mapping[str, Any], *, now_ms: int) -> int:
    return now_ms - _lock_epoch_ms(lock_payload)


def _lock_epoch_ms(lock_payload: Mapping[str, Any]) -> int:
    for key in (
        "updated_at_epoch_ms",
        "acquired_at_epoch_ms",
        "started_at_epoch_ms",
        "updated_at_ms",
        "acquired_at_ms",
        "started_at_ms",
    ):
        value = lock_payload.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    nested = lock_payload.get("lock")
    if isinstance(nested, Mapping):
        for key in (
            "updated_at_epoch_ms",
            "acquired_at_epoch_ms",
            "started_at_epoch_ms",
            "updated_at_ms",
            "acquired_at_ms",
            "started_at_ms",
        ):
            value = nested.get(key)
            if isinstance(value, (int, float)):
                return int(value)
    for key in ("updated_at", "acquired_at", "started_at"):
        parsed = _parse_timestamp_ms(lock_payload.get(key))
        if parsed is not None:
            return parsed
    if isinstance(nested, Mapping):
        for key in ("updated_at", "acquired_at", "started_at"):
            parsed = _parse_timestamp_ms(nested.get(key))
            if parsed is not None:
                return parsed
    return 0


def _parse_timestamp_ms(value: Any) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _timestamp_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value
