"""Polling watcher for lightweight SPEC-grag projects."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import spec_grag.config as config_api
from spec_grag.artifacts import ContextArtifactStore
from spec_grag.core import run_spec_core_for_watcher
from spec_grag.core_lock import (
    acquire_core_update_lock,
    cleanup_stale_core_update_lock,
    core_update_lock_path,
    heartbeat_core_update_lock,
    lock_diagnostics,
    lock_is_stale,
    read_core_update_lock,
    release_core_update_lock,
)
from spec_grag.freshness import (
    WATCHER_QUEUE_PENDING,
    WATCHER_RUNNING,
    build_freshness_report,
    classify_freshness_status,
    normalize_freshness_report,
    order_blocking_reasons,
)


DEFAULT_INTERVAL_MS = 2000
DEFAULT_DEBOUNCE_MS = 1000
DEFAULT_STALE_LOCK_MS = 300000
DEFAULT_STATE_FILE = ".spec-grag/state/watch_state.json"
DEFAULT_QUEUE_FILE = ".spec-grag/state/watch_queue.json"
SCHEMA_VERSION = 1
WATCHER_ACTIVITY_REASONS = {WATCHER_RUNNING, WATCHER_QUEUE_PENDING}
ACTIVE_STATE_MARKER_KEYS = (
    "current_snapshot",
    "lock",
    "lock_file",
    "owner",
    "run_id",
    "started_at",
    "started_at_epoch_ms",
    "started_at_ms",
    "locked_at",
    "locked_at_epoch_ms",
    "locked_at_ms",
    "queue_count_at_start",
)


class WatcherError(Exception):
    """Raised when the watcher cannot load or update project state."""


@dataclass(frozen=True)
class WatcherSettings:
    project_root: Path
    config_file: Path
    context_dir: Path
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    source_files: tuple[Path, ...]
    enabled: bool
    interval_sec: float
    debounce_sec: float
    stale_lock_sec: float
    state_file: Path
    queue_file: Path
    raw_config: Mapping[str, Any]


def run_spec_grag_watch(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
    once: bool = False,
    interval_sec: float | None = None,
    debounce_sec: float | None = None,
    stale_lock_sec: float | None = None,
    interval_ms: int | None = None,
    debounce_ms: int | None = None,
    stale_lock_ms: int | None = None,
    max_runs: int | None = None,
    core_runner: Callable[..., Mapping[str, Any]] | None = None,
    runner: Callable[..., Mapping[str, Any]] | None = None,
    sleep: Callable[[float], Any] | None = None,
    generated_at: str | None = None,
    now_ms: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run the polling watcher loop and return a JSON-friendly summary."""

    project = _project_root(project_root, root=root, cwd=cwd)
    settings = load_watcher_settings(
        project,
        interval_sec=interval_sec,
        debounce_sec=debounce_sec,
        stale_lock_sec=stale_lock_sec,
        interval_ms=interval_ms,
        debounce_ms=debounce_ms,
        stale_lock_ms=stale_lock_ms,
    )
    sleep_func = sleep or time.sleep
    active_runner = core_runner or runner
    cycles: list[dict[str, Any]] = []
    update_run_limit = None if once else max_runs
    cycle_count = 0
    update_runs = 0

    while True:
        if update_run_limit is not None and update_runs >= max(0, update_run_limit):
            break

        result = run_watcher_cycle(
            settings.project_root,
            settings=settings,
            core_runner=active_runner,
            sleep=sleep_func,
            generated_at=generated_at,
            now_ms=now_ms,
            **kwargs,
        )
        cycles.append(result)
        cycle_count += 1
        if result.get("ran_core"):
            update_runs += 1

        if once:
            break
        if update_run_limit is not None and update_runs >= update_run_limit:
            break
        sleep_func(settings.interval_sec)

    last = cycles[-1] if cycles else _idle_result(settings, generated_at=generated_at)
    return {
        **last,
        "cycles": cycles,
        "cycle_count": cycle_count,
        "runs": update_runs,
        "run_count": update_runs,
        "settings": _settings_summary(settings),
    }


def run_watcher_once(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
    interval_sec: float | None = None,
    debounce_sec: float | None = None,
    stale_lock_sec: float | None = None,
    interval_ms: int | None = None,
    debounce_ms: int | None = None,
    stale_lock_ms: int | None = None,
    core_runner: Callable[..., Mapping[str, Any]] | None = None,
    runner: Callable[..., Mapping[str, Any]] | None = None,
    sleep: Callable[[float], Any] | None = None,
    generated_at: str | None = None,
    now_ms: int | None = None,
    once: bool | None = None,
    max_runs: int | None = None,
    wait: bool | None = None,
    blocking: bool | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run one deterministic watcher cycle."""

    del once, max_runs, wait, blocking
    return run_spec_grag_watch(
        project_root,
        root=root,
        cwd=cwd,
        once=True,
        interval_sec=interval_sec,
        debounce_sec=debounce_sec,
        stale_lock_sec=stale_lock_sec,
        interval_ms=interval_ms,
        debounce_ms=debounce_ms,
        stale_lock_ms=stale_lock_ms,
        core_runner=core_runner,
        runner=runner,
        sleep=sleep,
        generated_at=generated_at,
        now_ms=now_ms,
        **kwargs,
    )


def run_watcher_cycle(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
    settings: WatcherSettings | None = None,
    interval_sec: float | None = None,
    debounce_sec: float | None = None,
    stale_lock_sec: float | None = None,
    interval_ms: int | None = None,
    debounce_ms: int | None = None,
    stale_lock_ms: int | None = None,
    core_runner: Callable[..., Mapping[str, Any]] | None = None,
    runner: Callable[..., Mapping[str, Any]] | None = None,
    sleep: Callable[[float], Any] | None = None,
    generated_at: str | None = None,
    now_ms: int | None = None,
    wait: bool | None = None,
    blocking: bool | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Scan once and run at most one internal SPEC-grag core update."""

    del wait, blocking
    project = _project_root(project_root, root=root, cwd=cwd)
    settings = settings or load_watcher_settings(
        project,
        interval_sec=interval_sec,
        debounce_sec=debounce_sec,
        stale_lock_sec=stale_lock_sec,
        interval_ms=interval_ms,
        debounce_ms=debounce_ms,
        stale_lock_ms=stale_lock_ms,
    )
    sleep_func = sleep or time.sleep
    now_ms = _now_ms() if now_ms is None else int(now_ms)
    run_id = str(uuid.uuid4())
    original_state = _read_state(settings.state_file)
    state = _discard_stale_lock_if_needed(
        original_state,
        stale_lock_ms=int(settings.stale_lock_sec * 1000),
        now_ms=now_ms,
    )
    if state != original_state:
        _write_state(settings.state_file, state)
    queue = _read_queue(settings.queue_file)
    current_snapshot = collect_source_snapshot(settings)

    previous_snapshot = _snapshot_from_state(state)
    detected = _diff_snapshots(previous_snapshot, current_snapshot)
    if detected:
        queue = _merge_queue(queue, detected, generated_at=generated_at)
        _write_queue(settings.queue_file, queue)
        _write_freshness_artifact(
            settings,
            build_freshness_report(watcher_queue_pending=True, watcher_queue_count=len(queue["queue"])),
        )

    if _state_running(state):
        report = build_freshness_report(watcher_running=True)
        _write_freshness_artifact(settings, report)
        return _result(
            settings,
            status="locked",
            ran_core=False,
            run_id=run_id,
            snapshot=current_snapshot,
            queue=queue,
            state=state,
            freshness_report=report,
            generated_at=generated_at,
            lock_reused=True,
        )

    if not queue["queue"]:
        cleaned_lock = cleanup_stale_core_update_lock(
            settings.project_root,
            stale_lock_ms=int(settings.stale_lock_sec * 1000),
            now_ms=now_ms,
        )
        if cleaned_lock:
            state = _record_stale_lock_cleanup(state, cleaned_lock)
        next_state = {
            **_inactive_state(state),
            "schema_version": SCHEMA_VERSION,
            "project_root": settings.project_root.as_posix(),
            "running": False,
            "last_snapshot": _snapshot_summary(current_snapshot),
            "last_scan_at": _timestamp(generated_at),
            "last_scan_epoch_ms": now_ms,
            "updated_at": _timestamp(generated_at),
            "updated_at_epoch_ms": now_ms,
        }
        _write_state(settings.state_file, next_state)
        report = _idle_freshness_report(settings, state=next_state)
        return _result(
            settings,
            status="idle",
            ran_core=False,
            run_id=run_id,
            snapshot=current_snapshot,
            queue=queue,
            state=next_state,
            freshness_report=report,
            generated_at=generated_at,
        )

    if settings.debounce_sec > 0:
        sleep_func(settings.debounce_sec)

    run_snapshot = collect_source_snapshot(settings)
    queued_changes = list(queue["queue"])
    lock_attempt = acquire_core_update_lock(
        settings.project_root,
        owner="watcher",
        run_id=run_id,
        stale_lock_ms=int(settings.stale_lock_sec * 1000),
        now_ms=now_ms,
        metadata={"entrypoint": "spec-grag-watch"},
    )
    if not lock_attempt.acquired:
        lock_state = {
            **state,
            "schema_version": SCHEMA_VERSION,
            "project_root": settings.project_root.as_posix(),
            "running": True,
            "is_running": True,
            "owner": lock_attempt.reason,
            "updated_at": _timestamp(generated_at),
            "updated_at_epoch_ms": now_ms,
            "lock": lock_diagnostics(lock_attempt.existing_lock, path=lock_attempt.path),
            "lock_file": lock_attempt.path.as_posix(),
            "last_lock_contention": {
                "owner": lock_attempt.reason,
                "lock": lock_diagnostics(lock_attempt.existing_lock, path=lock_attempt.path),
                "queue_count": len(queue["queue"]),
                "run_id": run_id,
            },
        }
        _write_state(settings.state_file, lock_state)
        report = build_freshness_report(watcher_running=True)
        _write_freshness_artifact(settings, report)
        return _result(
            settings,
            status="locked",
            ran_core=False,
            run_id=run_id,
            snapshot=run_snapshot,
            queue=queue,
            state=lock_state,
            freshness_report=report,
            generated_at=generated_at,
            lock_reused=True,
        )

    update_lock = lock_attempt.lock
    lock_payload = lock_diagnostics(
        update_lock.payload if update_lock else None,
        path=lock_attempt.path,
    )
    stale_locks = (
        list(state.get("stale_locks", []))
        if isinstance(state.get("stale_locks"), list)
        else []
    )
    if lock_attempt.stale_lock_discarded and lock_attempt.stale_lock:
        stale_locks.append(_inactive_history_item(lock_attempt.stale_lock))
    running_state = {
        **state,
        "schema_version": SCHEMA_VERSION,
        "project_root": settings.project_root.as_posix(),
        "running": True,
        "is_running": True,
        "run_id": run_id,
        "owner": "watcher",
        "started_at": _timestamp(generated_at),
        "started_at_epoch_ms": now_ms,
        "updated_at": _timestamp(generated_at),
        "updated_at_epoch_ms": now_ms,
        "current_snapshot": _snapshot_summary(run_snapshot),
        "queue_count_at_start": len(queued_changes),
        "lock": lock_payload,
        "lock_file": lock_attempt.path.as_posix(),
    }
    if stale_locks:
        running_state["stale_locks"] = stale_locks
    if state.get("stale_lock_discarded") or lock_attempt.stale_lock_discarded:
        running_state["stale_lock_discarded"] = True
    _write_state(settings.state_file, running_state)
    running_report = build_freshness_report(watcher_running=True)
    _write_freshness_artifact(settings, running_report)

    runner = core_runner or runner or run_spec_core_for_watcher

    def heartbeat(
        *args: Any,
        now_ms: int | None = None,
        timestamp_ms: int | None = None,
        metadata: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        nonlocal running_state

        heartbeat_now_ms = _heartbeat_now_ms(
            args,
            now_ms=now_ms,
            timestamp_ms=timestamp_ms,
        )
        heartbeat_metadata = dict(metadata or {})
        if fields:
            heartbeat_metadata.update(fields)
        lock_updated = heartbeat_core_update_lock(
            update_lock,
            now_ms=heartbeat_now_ms,
            metadata=heartbeat_metadata or None,
        )
        current_lock = read_core_update_lock(lock_attempt.path)
        current_state = _read_state(settings.state_file)
        if current_state.get("run_id") != run_id or not _state_running(current_state):
            current_state = dict(running_state)
        next_state = {
            **current_state,
            "schema_version": SCHEMA_VERSION,
            "project_root": settings.project_root.as_posix(),
            "running": True,
            "is_running": True,
            "owner": "watcher",
            "run_id": run_id,
            "updated_at": _timestamp_from_ms(heartbeat_now_ms),
            "updated_at_epoch_ms": heartbeat_now_ms,
            "lock": (
                lock_diagnostics(current_lock, path=lock_attempt.path)
                if current_lock
                else None
            ),
            "lock_file": lock_attempt.path.as_posix(),
        }
        _write_state(settings.state_file, next_state)
        running_state = next_state
        return {
            "updated": True,
            "lock_updated": lock_updated,
            "updated_at_epoch_ms": heartbeat_now_ms,
        }

    try:
        core_result = _call_core_runner(
            runner,
            settings=settings,
            run_id=run_id,
            snapshot=run_snapshot,
            queued_changes=queued_changes,
            generated_at=generated_at,
            heartbeat=heartbeat,
            extra_kwargs=kwargs,
        )
        core_report = _freshness_from_core_result(core_result)
        if _core_result_failed(core_result, core_report):
            failed_ms = _now_ms()
            failed_state = {
                **_inactive_state(running_state),
                "running": False,
                "is_running": False,
                "failed_at": _timestamp(generated_at),
                "failed_at_epoch_ms": failed_ms,
                "updated_at": _timestamp(generated_at),
                "updated_at_epoch_ms": failed_ms,
                "last_failure_reason": _core_failure_reason(
                    core_result,
                    core_report,
                    run_id=run_id,
                    queue_count=len(queue["queue"]),
                ),
                "last_result": _core_result_summary(core_result),
                "queue_count": len(queue["queue"]),
            }
            _write_state(settings.state_file, failed_state)
            _write_queue(settings.queue_file, queue)
            _write_freshness_artifact(settings, core_report)
            return _result(
                settings,
                status="failed",
                ran_core=True,
                run_id=run_id,
                snapshot=run_snapshot,
                queue=queue,
                state=failed_state,
                freshness_report=core_report,
                generated_at=generated_at,
                core_result=core_result,
            )
        post_snapshot = collect_source_snapshot(settings)
        new_changes = _diff_snapshots(run_snapshot, post_snapshot)
        queue = _merge_queue({"schema_version": SCHEMA_VERSION, "queue": []}, new_changes, generated_at=generated_at)
        _write_queue(settings.queue_file, queue)

        finished_ms = _now_ms()
        final_state = {
            **_inactive_state(running_state),
            "running": False,
            "is_running": False,
            "finished_at": _timestamp(generated_at),
            "finished_at_epoch_ms": finished_ms,
            "updated_at": _timestamp(generated_at),
            "updated_at_epoch_ms": finished_ms,
            "last_snapshot": _snapshot_summary(run_snapshot if queue["queue"] else post_snapshot),
            "last_result": _core_result_summary(core_result),
            "last_error": None,
            "last_success_at": _timestamp(generated_at),
            "last_success_at_epoch_ms": finished_ms,
            "last_success_result": _core_result_summary(core_result),
            "last_success_artifact_revision": _artifact_revision_from_core_result(core_result),
            "queue_count": len(queue["queue"]),
        }
        _write_state(settings.state_file, final_state)

        if queue["queue"]:
            final_report = build_freshness_report(
                blocking_reasons=list(core_report.get("blocking_reasons") or ()),
                warnings=list(core_report.get("warnings") or ()),
                watcher_queue_pending=True,
                watcher_queue_count=len(queue["queue"]),
            )
        else:
            final_report = core_report
        _write_freshness_artifact(settings, final_report)
        return _result(
            settings,
            status="updated" if not queue["queue"] else "queued",
            ran_core=True,
            run_id=run_id,
            snapshot=run_snapshot,
            queue=queue,
            state=final_state,
            freshness_report=final_report,
            generated_at=generated_at,
            core_result=core_result,
        )
    except Exception as exc:
        failed_ms = _now_ms()
        failed_state = {
            **_inactive_state(running_state),
            "running": False,
            "is_running": False,
            "failed_at": _timestamp(generated_at),
            "failed_at_epoch_ms": failed_ms,
            "updated_at": _timestamp(generated_at),
            "updated_at_epoch_ms": failed_ms,
            "last_error": {"type": type(exc).__name__, "message": str(exc)},
            "last_failure_reason": {
                "type": type(exc).__name__,
                "message": str(exc),
                "run_id": run_id,
                "queue_count": len(queue["queue"]),
            },
            "queue_count": len(queue["queue"]),
        }
        _write_state(settings.state_file, failed_state)
        _write_queue(settings.queue_file, queue)
        report = build_freshness_report(
            failed_required_artifact=True,
            warnings=[f"watcher core update failed: {exc}"],
        )
        _write_freshness_artifact(settings, report)
        raise
    finally:
        release_core_update_lock(update_lock)


def get_watcher_status(
    project_root: str | Path = ".",
    *,
    stale_lock_sec: float | None = None,
) -> dict[str, Any]:
    """Return watcher state in the shape accepted by the freshness helpers."""

    settings = load_watcher_settings(project_root, stale_lock_sec=stale_lock_sec)
    state = _read_state(settings.state_file)
    queue = _read_queue(settings.queue_file)
    now_ms = _now_ms()
    active_state = _discard_stale_lock_if_needed(
        state,
        stale_lock_ms=int(settings.stale_lock_sec * 1000),
        now_ms=now_ms,
    )
    if active_state != state:
        _write_state(settings.state_file, active_state)
    lock_file = core_update_lock_path(settings.project_root)
    shared_lock = read_core_update_lock(lock_file)
    shared_lock_running = bool(
        shared_lock
        and not lock_is_stale(
            shared_lock,
            stale_lock_ms=int(settings.stale_lock_sec * 1000),
            now_ms=now_ms,
        )
    )
    running = _state_running(active_state) or shared_lock_running
    freshness_report = _read_freshness_artifact(settings)
    diagnostics = {
        "last_success_at_epoch_ms": active_state.get("last_success_at_epoch_ms"),
        "last_success_result": _jsonable(active_state.get("last_success_result")),
        "last_success_artifact_revision": active_state.get("last_success_artifact_revision"),
        "last_failure_reason": _jsonable(active_state.get("last_failure_reason")),
        "last_lock": _jsonable(active_state.get("last_lock")),
        "stale_lock_discarded": bool(active_state.get("stale_lock_discarded")),
        "stale_locks": _jsonable(active_state.get("stale_locks", [])),
    }
    return {
        "running": running,
        "is_running": running,
        "queue_pending": bool(queue["queue"]),
        "queue_count": len(queue["queue"]),
        "state_file": settings.state_file.as_posix(),
        "queue_file": settings.queue_file.as_posix(),
        "lock_file": lock_file.as_posix(),
        "lock": lock_diagnostics(shared_lock, path=lock_file) if shared_lock else None,
        "state": active_state,
        "queue": list(queue["queue"]),
        "freshness_report": freshness_report,
        "diagnostics": diagnostics,
    }


def load_watcher_settings(
    project_root: str | Path = ".",
    *,
    interval_sec: float | None = None,
    debounce_sec: float | None = None,
    stale_lock_sec: float | None = None,
    interval_ms: int | None = None,
    debounce_ms: int | None = None,
    stale_lock_ms: int | None = None,
) -> WatcherSettings:
    """Load watcher settings from the project-root local config only."""

    root = Path(project_root).expanduser().resolve()
    try:
        project_config = config_api.load_config(
            root,
            allow_non_standard_providers=True,
        )
    except config_api.ConfigError as exc:
        raise WatcherError(str(exc)) from exc

    raw = dict(project_config.raw)
    include = list(project_config.sources.include)
    exclude = list(project_config.sources.exclude)
    watcher = _optional_table(raw.get("watcher"), "watcher")
    context = _optional_table(raw.get("context"), "context")

    interval_config_ms = interval_ms if interval_ms is not None else _int(watcher, "watcher", "interval_ms", DEFAULT_INTERVAL_MS)
    debounce_config_ms = debounce_ms if debounce_ms is not None else _int(watcher, "watcher", "debounce_ms", DEFAULT_DEBOUNCE_MS)
    stale_lock_config_ms = stale_lock_ms if stale_lock_ms is not None else _int(watcher, "watcher", "stale_lock_ms", DEFAULT_STALE_LOCK_MS)
    interval = _seconds_override(interval_sec, interval_config_ms)
    debounce = _seconds_override(debounce_sec, debounce_config_ms)
    stale_lock = _seconds_override(stale_lock_sec, stale_lock_config_ms)
    state_value = _optional_str(watcher, "watcher", "state_file") or DEFAULT_STATE_FILE
    queue_value = _optional_str(watcher, "watcher", "queue_file") or DEFAULT_QUEUE_FILE
    context_value = _optional_str(context, "context", "storage") or ".spec-grag/context"

    return WatcherSettings(
        project_root=root,
        config_file=project_config.config_file,
        context_dir=_relative_path(root, "context", "storage", context_value),
        include=tuple(include),
        exclude=tuple(exclude),
        source_files=tuple(project_config.sources.files),
        enabled=_bool(watcher, "watcher", "enabled", False),
        interval_sec=interval,
        debounce_sec=debounce,
        stale_lock_sec=stale_lock,
        state_file=_relative_path(root, "watcher", "state_file", state_value),
        queue_file=_relative_path(root, "watcher", "queue_file", queue_value),
        raw_config=raw,
    )


def collect_source_snapshot(settings: WatcherSettings | str | Path) -> dict[str, Any]:
    """Collect a deterministic Source Specs snapshot with file text."""

    if not isinstance(settings, WatcherSettings):
        settings = load_watcher_settings(settings)
    files: list[dict[str, Any]] = []
    for path in _matched_source_files(settings):
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        stat = path.stat()
        relative_path = path.relative_to(settings.project_root).as_posix()
        files.append(
            {
                "relative_path": relative_path,
                "path": relative_path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "text": text,
            }
        )
    summary_files = [_file_summary(item) for item in files]
    return {
        "schema_version": SCHEMA_VERSION,
        "files": files,
        "file_count": len(files),
        "fingerprint": _fingerprint_files(summary_files),
    }


def _matched_source_files(settings: WatcherSettings) -> list[Path]:
    return sorted(settings.source_files)


def _call_core_runner(
    runner: Callable[..., Mapping[str, Any]],
    *,
    settings: WatcherSettings,
    run_id: str,
    snapshot: Mapping[str, Any],
    queued_changes: Sequence[Mapping[str, Any]],
    generated_at: str | None,
    heartbeat: Callable[..., Any],
    extra_kwargs: Mapping[str, Any],
) -> Mapping[str, Any]:
    kwargs: dict[str, Any] = {
        "project_root": settings.project_root,
        "root": settings.project_root,
        "cwd": settings.project_root,
        "source_snapshot": snapshot,
        "snapshot": snapshot,
        "watcher_snapshot": snapshot,
        "queued_changes": list(queued_changes),
        "changed_files": list(queued_changes),
        "run_id": run_id,
        "generated_at": generated_at,
        "role": "watcher",
        "runner_role": "watcher",
        "internal": True,
        "internal_watcher": True,
        "called_by_watcher": True,
        "execution_role": "watcher",
        "bypass_update_lock": True,
        "heartbeat": heartbeat,
        "watcher_heartbeat": heartbeat,
        "heartbeat_callback": heartbeat,
        "touch_lock": heartbeat,
        "touch_core_update_lock": heartbeat,
    }
    kwargs.update(extra_kwargs)
    supported = _supported_call_kwargs(runner, kwargs)
    try:
        return runner(**supported)
    except TypeError as first_exc:
        if "project_root" in supported:
            positional_kwargs = dict(supported)
            positional_root = positional_kwargs.pop("project_root")
            try:
                return runner(positional_root, **positional_kwargs)
            except TypeError:
                pass
        raise first_exc


def _supported_call_kwargs(runner: Callable[..., Any], kwargs: Mapping[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(runner)
    except (TypeError, ValueError):
        return dict(kwargs)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return dict(kwargs)
    return {key: value for key, value in kwargs.items() if key in signature.parameters}


def _freshness_from_core_result(core_result: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(core_result, Mapping):
        for key in ("freshness_report", "freshness", "report"):
            value = core_result.get(key)
            if isinstance(value, Mapping):
                return normalize_freshness_report(value)
    return build_freshness_report()


def _core_result_failed(
    core_result: Mapping[str, Any] | Any,
    core_report: Mapping[str, Any],
) -> bool:
    status = ""
    if isinstance(core_result, Mapping):
        status = str(core_result.get("status") or "").lower()
    report_status = str(core_report.get("status") or "").lower()
    return status in {"failed", "error"} or report_status == "failed"


def _core_failure_reason(
    core_result: Mapping[str, Any] | Any,
    core_report: Mapping[str, Any],
    *,
    run_id: str,
    queue_count: int,
) -> dict[str, Any]:
    warnings = list(core_report.get("warnings") or [])
    reasons = list(core_report.get("blocking_reasons") or [])
    status = str(core_report.get("status") or "")
    if isinstance(core_result, Mapping):
        warnings.extend(str(item) for item in core_result.get("warnings", []) or [])
        status = str(core_result.get("status") or status)
    return {
        "type": "core_result_failed",
        "status": status,
        "blocking_reasons": reasons,
        "warnings": _dedupe_strings(warnings),
        "run_id": run_id,
        "queue_count": queue_count,
    }


def _core_result_summary(core_result: Mapping[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(core_result, Mapping):
        return {}
    summary: dict[str, Any] = {}
    for key in (
        "mode",
        "updated_sources",
        "skipped_sources",
        "failed_sources",
        "updated_sections",
        "failed_sections",
        "retrieval_index_status",
        "retrieval_index_artifact_revision",
        "source_update_diff",
        "pending_conflict_count",
        "stale_resolution_count",
    ):
        if key in core_result:
            summary[key] = _jsonable(core_result[key])
    return summary


def _artifact_revision_from_core_result(core_result: Mapping[str, Any] | Any) -> str | None:
    if not isinstance(core_result, Mapping):
        return None
    value = core_result.get("retrieval_index_artifact_revision")
    return str(value) if value is not None else None


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _diff_snapshots(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not previous:
        return [
            {
                **_file_summary(file_item),
                "change_type": "added",
            }
            for file_item in current.get("files", [])
            if isinstance(file_item, Mapping)
        ]

    previous_files = _files_by_path(previous)
    current_files = _files_by_path(current)
    changes: list[dict[str, Any]] = []
    for path, current_item in current_files.items():
        previous_item = previous_files.get(path)
        if previous_item is None:
            change_type = "added"
        elif previous_item.get("sha256") != current_item.get("sha256"):
            change_type = "modified"
        else:
            continue
        changes.append({**_file_summary(current_item), "change_type": change_type})
    for path, previous_item in previous_files.items():
        if path not in current_files:
            changes.append(
                {
                    "relative_path": path,
                    "path": path,
                    "sha256": None,
                    "previous_sha256": previous_item.get("sha256"),
                    "exists": False,
                    "change_type": "deleted",
                }
            )
    return sorted(changes, key=lambda item: str(item.get("relative_path") or item.get("path") or ""))


def _merge_queue(
    queue: Mapping[str, Any],
    changes: Sequence[Mapping[str, Any]],
    *,
    generated_at: str | None,
) -> dict[str, Any]:
    items = [
        dict(item)
        for item in queue.get("queue", [])
        if isinstance(item, Mapping)
    ]
    by_path = {
        str(item.get("relative_path") or item.get("path")): item
        for item in items
        if item.get("relative_path") or item.get("path")
    }
    for change in changes:
        path = str(change.get("relative_path") or change.get("path") or "")
        if not path:
            continue
        by_path[path] = {
            **dict(change),
            "relative_path": path,
            "path": path,
            "queued_at": _timestamp(generated_at),
        }
    merged = sorted(by_path.values(), key=lambda item: str(item.get("relative_path") or item.get("path") or ""))
    return {
        "schema_version": SCHEMA_VERSION,
        "queue": merged,
        "queue_count": len(merged),
        "updated_at": _timestamp(generated_at),
    }


def _read_state(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if isinstance(payload, Mapping):
        return dict(payload)
    return {"schema_version": SCHEMA_VERSION, "running": False}


def _write_state(path: Path, state: Mapping[str, Any]) -> None:
    _atomic_write_json(path, _jsonable(dict(state)))


def _read_queue(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if isinstance(payload, Mapping):
        items = payload.get("queue", payload.get("items", []))
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
            queue = [dict(item) for item in items if isinstance(item, Mapping)]
            return {
                "schema_version": int(payload.get("schema_version", SCHEMA_VERSION) or SCHEMA_VERSION),
                "queue": queue,
                "queue_count": len(queue),
                "updated_at": payload.get("updated_at"),
            }
    return {"schema_version": SCHEMA_VERSION, "queue": [], "queue_count": 0}


def _write_queue(path: Path, queue: Mapping[str, Any]) -> None:
    items = [
        dict(item)
        for item in queue.get("queue", [])
        if isinstance(item, Mapping)
    ]
    _atomic_write_json(
        path,
        {
            "schema_version": SCHEMA_VERSION,
            "queue": _jsonable(items),
            "queue_count": len(items),
            "updated_at": queue.get("updated_at") or _timestamp(None),
        },
    )


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _inactive_state(state: Mapping[str, Any]) -> dict[str, Any]:
    current = dict(state)
    _preserve_inactive_run_history(current)
    for key in ACTIVE_STATE_MARKER_KEYS:
        current.pop(key, None)
    if isinstance(current.get("stale_locks"), list):
        current["stale_locks"] = [
            _inactive_history_item(item)
            for item in current["stale_locks"]
        ]
    current["running"] = False
    current["is_running"] = False
    return current


def _preserve_inactive_run_history(state: dict[str, Any]) -> None:
    mappings = (
        ("run_id", "last_run_id"),
        ("owner", "last_owner"),
        ("started_at", "last_started_at"),
        ("started_at_epoch_ms", "last_started_at_epoch_ms"),
        ("started_at_ms", "last_started_at_ms"),
        ("updated_at", "last_heartbeat_at"),
        ("updated_at_epoch_ms", "last_heartbeat_at_epoch_ms"),
        ("updated_at_ms", "last_heartbeat_at_ms"),
        ("lock_file", "last_lock_file"),
        ("queue_count_at_start", "last_queue_count_at_start"),
    )
    for source, target in mappings:
        value = state.get(source)
        if value is not None:
            state[target] = value
    lock = state.get("lock")
    if isinstance(lock, Mapping):
        state["last_lock"] = _jsonable(lock)
        lock_mappings = (
            ("updated_at", "last_lock_updated_at"),
            ("updated_at_epoch_ms", "last_lock_updated_at_epoch_ms"),
            ("acquired_at", "last_lock_acquired_at"),
            ("acquired_at_epoch_ms", "last_lock_acquired_at_epoch_ms"),
        )
        for source, target in lock_mappings:
            value = lock.get(source)
            if value is not None:
                state[target] = value


def _stale_run_summary(state: Mapping[str, Any], *, stale_age_ms: int) -> dict[str, Any]:
    summary = {
        "last_run_id": state.get("run_id"),
        "last_owner": state.get("owner"),
        "last_started_at": state.get("started_at"),
        "last_started_at_epoch_ms": state.get("started_at_epoch_ms"),
        "last_updated_at": state.get("updated_at"),
        "last_updated_at_epoch_ms": state.get("updated_at_epoch_ms"),
        "stale_age_ms": stale_age_ms,
    }
    return {key: value for key, value in summary.items() if value is not None}


def _inactive_history_item(item: Any) -> Any:
    if not isinstance(item, Mapping):
        return item
    payload = dict(item)
    summary: dict[str, Any] = {}
    mappings = (
        ("owner", "last_owner"),
        ("run_id", "last_run_id"),
        ("started_at", "last_started_at"),
        ("started_at_epoch_ms", "last_started_at_epoch_ms"),
        ("started_at_ms", "last_started_at_ms"),
        ("acquired_at", "last_acquired_at"),
        ("acquired_at_epoch_ms", "last_acquired_at_epoch_ms"),
        ("updated_at", "last_updated_at"),
        ("updated_at_epoch_ms", "last_updated_at_epoch_ms"),
    )
    for source, target in mappings:
        value = payload.get(source)
        if value is not None:
            summary[target] = value
    for key, value in payload.items():
        if key.startswith("last_") or key in {"stale_age_ms", "lock_kind", "reason", "unreadable"}:
            summary[key] = value
    return summary


def _record_stale_lock_cleanup(
    state: Mapping[str, Any],
    stale_lock: Mapping[str, Any],
) -> dict[str, Any]:
    current = _inactive_state(state)
    stale_locks = (
        list(current.get("stale_locks", []))
        if isinstance(current.get("stale_locks"), list)
        else []
    )
    stale_locks.append(_inactive_history_item(stale_lock))
    current["stale_lock_discarded"] = True
    current["stale_locks"] = stale_locks
    return current


def _discard_stale_lock_if_needed(
    state: Mapping[str, Any],
    *,
    stale_lock_ms: int,
    now_ms: int,
) -> dict[str, Any]:
    current = dict(state)
    if not _state_running(current):
        return current
    age_ms = now_ms - _lock_epoch_ms(current)
    if age_ms <= stale_lock_ms:
        return current
    stale_locks = (
        list(current.get("stale_locks", []))
        if isinstance(current.get("stale_locks"), list)
        else []
    )
    stale_locks.append(_stale_run_summary(current, stale_age_ms=age_ms))
    current = _inactive_state(current)
    current["stale_lock_discarded"] = True
    current["stale_locks"] = stale_locks
    return current


def _state_running(state: Mapping[str, Any]) -> bool:
    return bool(state.get("running") or state.get("is_running"))


def _lock_epoch_ms(state: Mapping[str, Any]) -> int:
    for key in (
        "updated_at_epoch_ms",
        "started_at_epoch_ms",
        "locked_at_epoch_ms",
        "updated_at_ms",
        "started_at_ms",
        "locked_at_ms",
    ):
        value = state.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    lock = state.get("lock")
    if isinstance(lock, Mapping):
        for key in (
            "updated_at_epoch_ms",
            "acquired_at_epoch_ms",
            "started_at_epoch_ms",
            "updated_at_ms",
            "acquired_at_ms",
            "started_at_ms",
        ):
            value = lock.get(key)
            if isinstance(value, (int, float)):
                return int(value)
    for key in ("started_at", "updated_at", "locked_at"):
        parsed = _parse_timestamp_ms(state.get(key))
        if parsed is not None:
            return parsed
    if isinstance(lock, Mapping):
        for key in ("acquired_at", "updated_at", "started_at"):
            parsed = _parse_timestamp_ms(lock.get(key))
            if parsed is not None:
                return parsed
    return 0


def _heartbeat_now_ms(
    args: Sequence[Any],
    *,
    now_ms: int | None,
    timestamp_ms: int | None,
) -> int:
    if now_ms is not None:
        return int(now_ms)
    if timestamp_ms is not None:
        return int(timestamp_ms)
    if args:
        return int(args[0])
    return _now_ms()


def _parse_timestamp_ms(value: Any) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _snapshot_from_state(state: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = state.get("last_snapshot")
    return value if isinstance(value, Mapping) else None


def _snapshot_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    files = [
        _file_summary(item)
        for item in snapshot.get("files", [])
        if isinstance(item, Mapping)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "files": files,
        "file_count": len(files),
        "fingerprint": _fingerprint_files(files),
    }


def _file_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    path = str(item.get("relative_path") or item.get("path") or "")
    return {
        "relative_path": path,
        "path": path,
        "sha256": item.get("sha256"),
        "size": item.get("size"),
        "mtime_ns": item.get("mtime_ns"),
        "exists": item.get("exists", True),
    }


def _files_by_path(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    files = snapshot.get("files", [])
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        return result
    for item in files:
        if not isinstance(item, Mapping):
            continue
        path = str(item.get("relative_path") or item.get("path") or "")
        if path:
            result[path] = dict(item)
    return result


def _fingerprint_files(files: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {
            "relative_path": str(file_item.get("relative_path") or file_item.get("path") or ""),
            "sha256": file_item.get("sha256"),
            "exists": file_item.get("exists", True),
        }
        for file_item in files
    ]
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def _write_freshness_artifact(settings: WatcherSettings, report: Mapping[str, Any]) -> None:
    store = ContextArtifactStore(settings.context_dir)
    store.write("freshness", normalize_freshness_report(report))


def _read_freshness_artifact(settings: WatcherSettings) -> dict[str, Any] | None:
    path = settings.context_dir / "freshness.json"
    payload = _read_json(path)
    if isinstance(payload, Mapping):
        return normalize_freshness_report(payload)
    return None


def _idle_freshness_report(
    settings: WatcherSettings,
    *,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    existing = _read_freshness_artifact(settings)
    if existing is None:
        report = build_freshness_report()
        if state.get("stale_lock_discarded"):
            _write_freshness_artifact(settings, report)
        return report

    report = _without_watcher_activity_reasons(existing)
    if state.get("stale_lock_discarded") or report != existing:
        _write_freshness_artifact(settings, report)
    return report


def _without_watcher_activity_reasons(report: Mapping[str, Any]) -> dict[str, Any]:
    payload = normalize_freshness_report(report)
    reasons = order_blocking_reasons(
        [
            reason
            for reason in payload.get("blocking_reasons", [])
            if reason not in WATCHER_ACTIVITY_REASONS
        ]
    )
    next_report = dict(payload)
    next_report["blocking_reasons"] = reasons
    next_report["status"] = classify_freshness_status(reasons)

    counts = next_report.get("counts")
    if isinstance(counts, Mapping):
        next_counts = dict(counts)
        next_counts.pop("watcher_queue_count", None)
        if next_counts:
            next_report["counts"] = next_counts
        else:
            next_report.pop("counts", None)
    next_report.pop("watcher_queue_count", None)
    return normalize_freshness_report(next_report)


def _result(
    settings: WatcherSettings,
    *,
    status: str,
    ran_core: bool,
    run_id: str,
    snapshot: Mapping[str, Any],
    queue: Mapping[str, Any],
    state: Mapping[str, Any],
    freshness_report: Mapping[str, Any],
    generated_at: str | None,
    core_result: Mapping[str, Any] | Any | None = None,
    lock_reused: bool = False,
) -> dict[str, Any]:
    queue_items = [
        dict(item)
        for item in queue.get("queue", [])
        if isinstance(item, Mapping)
    ]
    running = _state_running(state)
    watcher_payload = {
        "running": running,
        "is_running": running,
        "queue_pending": bool(queue_items),
        "queue_count": len(queue_items),
        "state_file": settings.state_file.as_posix(),
        "queue_file": settings.queue_file.as_posix(),
        "lock_file": core_update_lock_path(settings.project_root).as_posix(),
    }
    result = {
        "status": status,
        "project_root": settings.project_root.as_posix(),
        "run_id": run_id,
        "ran_core": ran_core,
        "updated": ran_core,
        "lock_reused": lock_reused,
        "source_snapshot": _snapshot_summary(snapshot),
        "snapshot": _snapshot_summary(snapshot),
        "queued_changes": queue_items,
        "queue_count": len(queue_items),
        "queue_pending": bool(queue_items),
        "watcher": watcher_payload,
        "freshness_report": normalize_freshness_report(freshness_report),
        "generated_at": generated_at,
    }
    if state.get("stale_lock_discarded"):
        result["stale_lock_discarded"] = True
        result["stale_locks"] = _jsonable(state.get("stale_locks", []))
    if state.get("lock") is not None:
        result["lock"] = _jsonable(state.get("lock"))
    if state.get("lock_file") is not None:
        result["lock_file"] = str(state.get("lock_file"))
    if state.get("last_lock") is not None:
        result["last_lock"] = _jsonable(state.get("last_lock"))
    if state.get("last_lock_file") is not None:
        result["last_lock_file"] = str(state.get("last_lock_file"))
    if state.get("last_heartbeat_at") is not None:
        result["last_heartbeat_at"] = state.get("last_heartbeat_at")
    if state.get("last_heartbeat_at_epoch_ms") is not None:
        result["last_heartbeat_at_epoch_ms"] = state.get("last_heartbeat_at_epoch_ms")
    if core_result is not None:
        result["core_result"] = _jsonable(core_result)
    return result


def _idle_result(settings: WatcherSettings, *, generated_at: str | None) -> dict[str, Any]:
    queue = _read_queue(settings.queue_file)
    state = _read_state(settings.state_file)
    report = _read_freshness_artifact(settings) or build_freshness_report(
        watcher_running=_state_running(state),
        watcher_queue_pending=bool(queue["queue"]),
        watcher_queue_count=len(queue["queue"]),
    )
    return _result(
        settings,
        status="idle",
        ran_core=False,
        run_id="",
        snapshot={"files": []},
        queue=queue,
        state=state,
        freshness_report=report,
        generated_at=generated_at,
    )


def _settings_summary(settings: WatcherSettings) -> dict[str, Any]:
    return {
        "project_root": settings.project_root.as_posix(),
        "config_file": settings.config_file.as_posix(),
        "enabled": settings.enabled,
        "interval_sec": settings.interval_sec,
        "debounce_sec": settings.debounce_sec,
        "stale_lock_sec": settings.stale_lock_sec,
        "state_file": settings.state_file.as_posix(),
        "queue_file": settings.queue_file.as_posix(),
        "lock_file": core_update_lock_path(settings.project_root).as_posix(),
    }


def _table(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = raw.get(name)
    if not isinstance(value, Mapping):
        raise WatcherError(f"[{name}] table is required")
    return value


def _optional_table(value: Any, name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise WatcherError(f"[{name}] must be a table")
    return value


def _string_list(
    table: Mapping[str, Any],
    table_name: str,
    key: str,
    *,
    required: bool,
) -> list[str]:
    if key not in table:
        if required:
            raise WatcherError(f"{table_name}.{key} is required")
        return []
    value = table[key]
    if not isinstance(value, list):
        raise WatcherError(f"{table_name}.{key} must be a list")
    if not all(isinstance(item, str) and item for item in value):
        raise WatcherError(f"{table_name}.{key} must contain non-empty strings")
    return list(value)


def _optional_str(table: Mapping[str, Any], table_name: str, key: str) -> str | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str) or not value:
        raise WatcherError(f"{table_name}.{key} must be a non-empty string")
    return value


def _int(table: Mapping[str, Any], table_name: str, key: str, default: int) -> int:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise WatcherError(f"{table_name}.{key} must be an integer")
    return value


def _bool(table: Mapping[str, Any], table_name: str, key: str, default: bool) -> bool:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, bool):
        raise WatcherError(f"{table_name}.{key} must be a boolean")
    return value


def _seconds_override(value: float | None, millis: int) -> float:
    result = float(millis) / 1000.0 if value is None else float(value)
    if result < 0:
        raise WatcherError("watcher timing options must be non-negative")
    return result


def _relative_path(root: Path, table_name: str, key: str, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    if ".." in path.parts:
        raise WatcherError(f"{table_name}.{key} must not escape project root")
    return root / path


def _validate_project_pattern(pattern: str, label: str) -> None:
    path = Path(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise WatcherError(f"{label} must be project-root relative")


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _project_root(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> Path:
    return Path(root or cwd or project_root).expanduser().resolve()


def _timestamp(generated_at: str | None) -> str:
    return generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_from_ms(value: int) -> str:
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


run_watch = run_spec_grag_watch
watch = run_spec_grag_watch
spec_grag_watch = run_spec_grag_watch
run_watch_once = run_watcher_once
watch_once = run_watcher_once
run_watcher = run_spec_grag_watch
watcher_status = get_watcher_status
read_watcher_status = get_watcher_status
