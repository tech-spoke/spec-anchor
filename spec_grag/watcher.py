"""Polling watcher entrypoint for background GRAG incremental updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import tomllib
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any

from pydantic import ValidationError

from spec_grag.config import (
    ConfigPolicyError,
    ExecutionRole,
    resolve_runtime_policy,
    validate_project_config,
)
from spec_grag.core import resolve_source_paths, run_core_update
from spec_grag.manifest import (
    SourceManifest,
    build_current_section_manifest,
    load_source_manifest,
    reconcile_manifests,
)
from spec_grag.readiness import evaluate_grag_readiness
from spec_grag.watch_state import (
    RUNNING_CHANGE_REASONS,
    WatchLock,
    WatchLockError,
    WatchRunState,
    WatchState,
    enqueue_source_changes,
    load_watch_queue,
    load_watch_state,
    remove_watch_queue_changes,
    semantic_digest_for_manifest,
    semantic_hashes_for_manifest,
    watch_queue_path,
    watch_state_path,
    write_watch_state_atomic,
)


@dataclass(frozen=True)
class SourceSnapshot:
    manifest: SourceManifest
    document_texts: dict[str, str]
    semantic_hash: str | None


@dataclass(frozen=True)
class WatcherSettings:
    enabled: bool
    interval_sec: float
    debounce_sec: float
    stale_lock_sec: int


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spec-grag-watch")
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--once", action="store_true", help="run one polling cycle")
    parser.add_argument("--interval-sec", type=float)
    parser.add_argument("--debounce-sec", type=float)
    parser.add_argument("--max-runs", type=int, default=0)
    parser.add_argument("--stale-lock-sec", type=int)
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).expanduser().resolve()
    try:
        config = load_project_config(project_root)
    except Exception as exc:
        sys.stderr.write(f"spec-grag-watch config error: {exc}\n")
        return 1

    settings = watcher_settings_from_config(config)
    if not settings.enabled:
        sys.stderr.write("spec-grag-watch disabled by [watcher].enabled = false\n")
        return 0
    interval_sec = args.interval_sec if args.interval_sec is not None else settings.interval_sec
    debounce_sec = args.debounce_sec if args.debounce_sec is not None else settings.debounce_sec
    stale_lock_sec = (
        args.stale_lock_sec
        if args.stale_lock_sec is not None
        else settings.stale_lock_sec
    )

    runs = 0
    while True:
        if not args.once and not watcher_should_run(project_root, config):
            time.sleep(interval_sec)
            continue
        code = run_watch_once(
            project_root,
            config,
            debounce_sec=debounce_sec,
            stale_lock_sec=stale_lock_sec,
        )
        runs += 1
        if args.once or code != 0:
            return code
        if args.max_runs and runs >= args.max_runs:
            return 0
        if not watcher_should_run(project_root, config):
            time.sleep(interval_sec)


def load_project_config(project_root: Path) -> dict[str, Any]:
    config_path = project_root / ".spec-grag" / "config.toml"
    with config_path.open("rb") as f:
        raw = tomllib.load(f)
    try:
        return validate_project_config(raw)
    except (ValidationError, ConfigPolicyError) as exc:
        raise RuntimeError(f"{config_path}: {exc}") from exc


def run_watch_once(
    project_root: Path,
    config: dict[str, Any],
    *,
    debounce_sec: float | None = None,
    stale_lock_sec: int | None = None,
) -> int:
    settings = watcher_settings_from_config(config)
    if not settings.enabled:
        return 0
    debounce = settings.debounce_sec if debounce_sec is None else debounce_sec
    stale_lock = settings.stale_lock_sec if stale_lock_sec is None else stale_lock_sec
    policy = resolve_runtime_policy(
        config,
        execution_role=ExecutionRole.BACKGROUND_WATCHER,
    )
    try:
        with WatchLock(project_root, config=config, stale_after_sec=stale_lock) as lock:
            snapshot = capture_debounced_source_snapshot(
                project_root,
                config,
                debounce_sec=debounce,
            )
            run_id = new_run_id()
            started_at = datetime.now(UTC).isoformat()
            readiness = evaluate_grag_readiness(
                project_root,
                config,
                runtime_policy=policy,
            )
            queue_before = load_watch_queue(watch_queue_path(project_root, config))
            write_watch_state_atomic(
                watch_state_path(project_root, config),
                WatchState(
                    readiness_status=readiness.status,
                    run_state=WatchRunState.RUNNING,
                    last_run_id=run_id,
                    last_started_at=started_at,
                    heartbeat_at=started_at,
                    updated_at=started_at,
                    last_processed_semantic_hash=readiness.last_processed_semantic_hash,
                    running_semantic_hash=snapshot.semantic_hash,
                    queued_change_count=len(queue_before.changes),
                    readiness_report=readiness.as_freshness_payload(),
                ),
            )
            lock.heartbeat()

            heartbeat = WatchHeartbeat(
                project_root=project_root,
                config=config,
                lock=lock,
                run_id=run_id,
                interval_sec=max(0.2, min(5.0, stale_lock / 4)),
            )
            monitor = RunningChangeMonitor(
                project_root=project_root,
                config=config,
                baseline=snapshot,
                poll_interval_sec=max(0.05, min(0.5, debounce or 0.5)),
            )
            heartbeat.start()
            monitor.start()
            try:
                update = run_core_update(
                    project_root,
                    config,
                    all_sources=False,
                    execution_role=ExecutionRole.BACKGROUND_WATCHER,
                    source_manifest=snapshot.manifest,
                    source_document_texts=snapshot.document_texts,
                )
            finally:
                monitor.stop()
                heartbeat.stop()
            completed_at = datetime.now(UTC).isoformat()
            latest_snapshot = capture_source_snapshot(project_root, config)
            enqueue_changes_since_snapshot(
                project_root,
                config=config,
                before=snapshot.manifest,
                after=latest_snapshot.manifest,
                reason="post_run_change",
                detected_at=completed_at,
            )
            graph_storage = Path(update.graph_storage)
            manifest = load_source_manifest(graph_storage / "source_manifest.json")
            processed_hash = (
                semantic_digest_for_manifest(manifest) if manifest.entries else None
            )
            if update.status != "failed":
                processed_hashes = semantic_hashes_for_manifest(manifest)
                if latest_snapshot.semantic_hash == processed_hash:
                    remove_watch_queue_changes(
                        project_root,
                        config=config,
                        reasons=RUNNING_CHANGE_REASONS,
                    )
                else:
                    remove_watch_queue_changes(
                        project_root,
                        config=config,
                        reasons=RUNNING_CHANGE_REASONS,
                        matching_semantic_hashes=processed_hashes,
                    )
            queue_after = load_watch_queue(watch_queue_path(project_root, config))
            post_readiness = evaluate_grag_readiness(
                project_root,
                config,
                runtime_policy=policy,
            )
            run_state = (
                WatchRunState.FAILED
                if update.status == "failed"
                else WatchRunState.IDLE
            )
            write_watch_state_atomic(
                watch_state_path(project_root, config),
                WatchState(
                    readiness_status=post_readiness.status,
                    run_state=run_state,
                    last_run_id=run_id,
                    last_started_at=started_at,
                    last_completed_at=completed_at,
                    last_error=";".join(update.warnings)
                    if update.status == "failed"
                    else None,
                    last_processed_semantic_hash=processed_hash,
                    running_semantic_hash=None,
                    queued_change_count=len(queue_after.changes),
                    heartbeat_at=completed_at,
                    updated_at=completed_at,
                    readiness_report=post_readiness.as_freshness_payload(),
                ),
            )
            maybe_write_watch_run_artifact(
                project_root=project_root,
                config=config,
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                readiness_before=readiness.as_freshness_payload(),
                readiness_after=post_readiness.as_freshness_payload(),
                update_summary={
                    "status": update.status.value,
                    "mode": update.mode,
                    "updated_sources": update.updated_sources,
                    "skipped_sources": update.skipped_sources,
                    "failed_sources": update.failed_sources,
                    "pending_concept_diff_id": update.pending_concept_diff_id,
                    "warnings": update.warnings,
                },
            )
            return 1 if update.status == "failed" else 0
    except WatchLockError as exc:
        state = load_watch_state(watch_state_path(project_root, config))
        failed = state.model_copy(
            update={
                "run_state": WatchRunState.FAILED,
                "last_error": str(exc),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        write_watch_state_atomic(watch_state_path(project_root, config), failed)
        sys.stderr.write(f"{exc}\n")
        return 1


def new_run_id() -> str:
    timestamp = datetime.now(UTC).isoformat()
    digest = hashlib.sha256(timestamp.encode("utf-8")).hexdigest()[:12]
    return f"watch-{digest}"


def watcher_should_run(project_root: Path, config: dict[str, Any]) -> bool:
    policy = resolve_runtime_policy(
        config,
        execution_role=ExecutionRole.BACKGROUND_WATCHER,
    )
    readiness = evaluate_grag_readiness(
        project_root,
        config,
        runtime_policy=policy,
    )
    if readiness.status in {"dirty", "stale"} or readiness.dirty_section_ids:
        return True
    return bool(load_watch_queue(watch_queue_path(project_root, config)).changes)


def watcher_settings_from_config(config: dict[str, Any]) -> WatcherSettings:
    watcher = _mapping(config.get("watcher"))
    return WatcherSettings(
        enabled=bool(watcher.get("enabled", True)),
        interval_sec=_milliseconds_to_seconds(watcher.get("interval_ms", 2000)),
        debounce_sec=_milliseconds_to_seconds(watcher.get("debounce_ms", 500)),
        stale_lock_sec=max(1, int(_milliseconds_to_seconds(watcher.get("stale_lock_ms", 300_000)))),
    )


def capture_debounced_source_snapshot(
    project_root: Path,
    config: dict[str, Any],
    *,
    debounce_sec: float,
) -> SourceSnapshot:
    snapshot = capture_source_snapshot(project_root, config)
    if debounce_sec <= 0:
        return snapshot

    stable_after = time.monotonic() + debounce_sec
    while True:
        remaining = stable_after - time.monotonic()
        if remaining <= 0:
            return snapshot
        time.sleep(min(remaining, 0.1))
        current = capture_source_snapshot(project_root, config)
        if current.semantic_hash != snapshot.semantic_hash:
            snapshot = current
            stable_after = time.monotonic() + debounce_sec


def capture_source_snapshot(project_root: Path, config: dict[str, Any]) -> SourceSnapshot:
    source_paths = resolve_source_paths(project_root, config)
    document_texts = read_source_document_texts(project_root, source_paths)
    manifest = build_current_section_manifest(
        project_root,
        source_paths,
        generated_at=datetime.now(UTC).isoformat(),
        section_max_heading_level=int(
            _mapping(config.get("extraction")).get("section_max_heading_level", 6)
        ),
        document_texts=document_texts,
    )
    semantic_hash = semantic_digest_for_manifest(manifest) if manifest.entries else None
    return SourceSnapshot(
        manifest=manifest,
        document_texts=document_texts,
        semantic_hash=semantic_hash,
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def read_source_document_texts(
    project_root: Path,
    source_paths: list[Path],
) -> dict[str, str]:
    root = project_root.resolve()
    documents: dict[str, str] = {}
    for source_path in sorted(source_paths):
        resolved = source_path.resolve()
        try:
            document_id = resolved.relative_to(root).as_posix()
        except ValueError:
            document_id = resolved.as_posix()
        documents[document_id] = resolved.read_text(encoding="utf-8")
    return documents


def enqueue_changes_since_snapshot(
    project_root: Path,
    *,
    config: dict[str, Any] | None = None,
    before: SourceManifest,
    after: SourceManifest,
    reason: str,
    detected_at: str | None = None,
) -> None:
    section_ids, semantic_hashes = changed_sections_between(before, after)
    if not section_ids:
        return
    enqueue_source_changes(
        project_root,
        config=config,
        source_section_ids=section_ids,
        semantic_hashes=semantic_hashes,
        reason=reason,
        detected_at=detected_at,
    )


def changed_sections_between(
    before: SourceManifest,
    after: SourceManifest,
) -> tuple[list[str], dict[str, str]]:
    reconciliation = reconcile_manifests(before, after)
    section_ids = sorted(
        {
            *reconciliation.changed_section_ids,
            *reconciliation.added_section_ids,
            *reconciliation.removed_section_ids,
        }
    )
    after_hashes = semantic_hashes_for_manifest(after)
    return section_ids, {section_id: after_hashes.get(section_id, "") for section_id in section_ids}


class WatchHeartbeat:
    def __init__(
        self,
        *,
        project_root: Path,
        config: dict[str, Any],
        lock: WatchLock,
        run_id: str,
        interval_sec: float,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.lock = lock
        self.run_id = run_id
        self.interval_sec = interval_sec
        self._stop = Event()
        self._thread = Thread(target=self._run, name="spec-grag-watch-heartbeat", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(self.interval_sec * 2, 1.0))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_sec):
            self.lock.heartbeat()
            path = watch_state_path(self.project_root, self.config)
            state = load_watch_state(path)
            if state.last_run_id != self.run_id or state.run_state != WatchRunState.RUNNING:
                continue
            now = datetime.now(UTC).isoformat()
            write_watch_state_atomic(
                path,
                state.model_copy(update={"heartbeat_at": now, "updated_at": now}),
            )


class RunningChangeMonitor:
    def __init__(
        self,
        *,
        project_root: Path,
        config: dict[str, Any],
        baseline: SourceSnapshot,
        poll_interval_sec: float,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.baseline = baseline
        self.poll_interval_sec = poll_interval_sec
        self._stop = Event()
        self._thread = Thread(target=self._run, name="spec-grag-watch-monitor", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(self.poll_interval_sec * 2, 1.0))

    def _run(self) -> None:
        while not self._stop.wait(self.poll_interval_sec):
            try:
                current = capture_source_snapshot(self.project_root, self.config)
            except OSError:
                continue
            if current.semantic_hash == self.baseline.semantic_hash:
                continue
            enqueue_changes_since_snapshot(
                self.project_root,
                config=self.config,
                before=self.baseline.manifest,
                after=current.manifest,
                reason="running_change",
                detected_at=datetime.now(UTC).isoformat(),
            )


def maybe_write_watch_run_artifact(
    *,
    project_root: Path,
    config: dict[str, Any],
    run_id: str,
    started_at: str,
    completed_at: str,
    readiness_before: dict[str, Any],
    readiness_after: dict[str, Any],
    update_summary: dict[str, Any],
) -> str | None:
    run_config = config.get("run", {})
    if not bool(run_config.get("save_artifacts", False)):
        return None
    artifact_dir = Path(str(run_config.get("artifact_dir", ".spec-grag/runs")))
    if not artifact_dir.is_absolute():
        artifact_dir = project_root / artifact_dir
    digest = hashlib.sha256(
        json.dumps(update_summary, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    path = artifact_dir / f"{completed_at.replace(':', '').replace('+', 'Z')}-spec-watch-{digest}.json"
    payload = {
        "version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "command": "spec-grag-watch",
        "run_id": run_id,
        "status": update_summary.get("status"),
        "runtime_mode": str(config.get("_runtime_mode", "production")),
        "runtime_policy": readiness_after.get("runtime_policy", {}),
        "started_at": started_at,
        "completed_at": completed_at,
        "readiness_before": readiness_before,
        "readiness_after": readiness_after,
        "core_update": update_summary,
    }
    _write_json_atomic(path, payload)
    return str(path)


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _milliseconds_to_seconds(value: Any) -> float:
    return max(0.0, float(value) / 1000.0)


if __name__ == "__main__":
    raise SystemExit(main())
