"""Persistent watcher state, queue, lock, and provisional Concept cache."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from spec_grag.io import fsync_directory as _fsync_directory
from spec_grag.io import write_json_atomic as _write_json_atomic
from spec_grag.manifest import SourceManifest
from spec_grag.protocol import StrictModel


WATCH_STATE_VERSION = "1"
WATCH_QUEUE_VERSION = "1"
PROVISIONAL_CONCEPT_CACHE_VERSION = "1"
DEFAULT_STALE_LOCK_SEC = 300
RUNNING_CHANGE_REASONS = frozenset({"running_change", "post_run_change"})


class WatchReadinessStatus(StrEnum):
    FRESH = "fresh"
    DIRTY = "dirty"
    PENDING = "pending"
    STALE = "stale"


class WatchRunState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"


class QueuedSourceChange(StrictModel):
    source_section_id: str
    semantic_hash: str
    reason: str
    detected_at: str


class WatchQueue(StrictModel):
    version: str = WATCH_QUEUE_VERSION
    updated_at: str | None = None
    pending_concept_diff_id: str | None = None
    changes: list[QueuedSourceChange] = Field(default_factory=list)


class WatchState(StrictModel):
    version: str = WATCH_STATE_VERSION
    readiness_status: WatchReadinessStatus = WatchReadinessStatus.FRESH
    run_state: WatchRunState = WatchRunState.IDLE
    last_run_id: str | None = None
    last_started_at: str | None = None
    last_completed_at: str | None = None
    last_error: str | None = None
    last_processed_semantic_hash: str | None = None
    running_semantic_hash: str | None = None
    queued_change_count: int = 0
    heartbeat_at: str | None = None
    updated_at: str | None = None
    readiness_report: dict[str, Any] | None = None


class ProvisionalConceptCandidate(StrictModel):
    label: str
    normalized_label: str
    aliases: list[str] = Field(default_factory=list)
    supporting_sections: list[str] = Field(default_factory=list)
    semantic_hashes: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    first_seen: str
    last_seen: str
    status: str = "provisional"


class ProvisionalConceptCache(StrictModel):
    version: str = PROVISIONAL_CONCEPT_CACHE_VERSION
    updated_at: str | None = None
    candidates: list[ProvisionalConceptCandidate] = Field(default_factory=list)


class WatchLockError(RuntimeError):
    """Raised when another non-stale watcher lock already exists."""


class WatchLock:
    def __init__(
        self,
        project_root: Path,
        *,
        config: Mapping[str, Any] | None = None,
        stale_after_sec: int = DEFAULT_STALE_LOCK_SEC,
    ) -> None:
        self.path = watch_lock_path(project_root, config)
        self.stale_after_sec = stale_after_sec
        self.acquired = False

    def __enter__(self) -> WatchLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._payload()
        try:
            fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            if not self._lock_is_stale():
                raise WatchLockError(f"watcher lock already exists: {self.path}")
            self.path.unlink(missing_ok=True)
            fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        self.acquired = True

    def heartbeat(self) -> None:
        if not self.acquired:
            return
        _write_json_atomic(self.path, self._payload())

    def release(self) -> None:
        if not self.acquired:
            return
        self.path.unlink(missing_ok=True)
        self.acquired = False

    def _payload(self) -> dict[str, Any]:
        now = _now()
        return {
            "version": "1",
            "pid": os.getpid(),
            "heartbeat_at": now,
            "stale_after_sec": self.stale_after_sec,
        }

    def _lock_is_stale(self) -> bool:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True
        heartbeat = _parse_datetime(str(data.get("heartbeat_at") or ""))
        if heartbeat is None:
            return True
        stale_after = int(data.get("stale_after_sec") or self.stale_after_sec)
        age = (datetime.now(UTC) - heartbeat).total_seconds()
        return age > stale_after


def state_dir(
    project_root: Path,
    config: Mapping[str, Any] | None = None,
) -> Path:
    if config is not None:
        return watch_state_path(project_root, config).parent
    return project_root / ".spec-grag" / "state"


def watch_state_path(
    project_root: Path,
    config: Mapping[str, Any] | None = None,
) -> Path:
    return _configured_watcher_path(
        project_root,
        config,
        key="state_file",
        default=".spec-grag/state/watch_state.json",
    )


def watch_queue_path(
    project_root: Path,
    config: Mapping[str, Any] | None = None,
) -> Path:
    return _configured_watcher_path(
        project_root,
        config,
        key="queue_file",
        default=".spec-grag/state/watch_queue.json",
    )


def provisional_concept_cache_path(project_root: Path) -> Path:
    return state_dir(project_root) / "provisional_concept_cache.json"


def watch_lock_path(
    project_root: Path,
    config: Mapping[str, Any] | None = None,
) -> Path:
    return state_dir(project_root, config) / "watch_lock.json"


def load_watch_state(path: Path) -> WatchState:
    if not path.exists():
        return WatchState()
    return WatchState.model_validate_json(path.read_text(encoding="utf-8"))


def write_watch_state_atomic(path: Path, state: WatchState) -> None:
    _write_json_atomic(path, state.model_dump(mode="json"))


def load_watch_queue(path: Path) -> WatchQueue:
    if not path.exists():
        return WatchQueue()
    return WatchQueue.model_validate_json(path.read_text(encoding="utf-8"))


def write_watch_queue_atomic(path: Path, queue: WatchQueue) -> None:
    _write_json_atomic(path, queue.model_dump(mode="json"))


def clear_watch_queue(
    project_root: Path,
    config: Mapping[str, Any] | None = None,
) -> None:
    path = watch_queue_path(project_root, config)
    if path.exists():
        write_watch_queue_atomic(path, WatchQueue(updated_at=_now()))


def clear_provisional_concept_cache(project_root: Path) -> None:
    path = provisional_concept_cache_path(project_root)
    if path.exists():
        write_provisional_concept_cache_atomic(
            path,
            ProvisionalConceptCache(updated_at=_now()),
        )


def queued_section_ids(
    project_root: Path,
    config: Mapping[str, Any] | None = None,
) -> list[str]:
    queue = load_watch_queue(watch_queue_path(project_root, config))
    return sorted({change.source_section_id for change in queue.changes})


def watch_queue_has_changes(
    project_root: Path,
    config: Mapping[str, Any] | None = None,
) -> bool:
    return bool(load_watch_queue(watch_queue_path(project_root, config)).changes)


def enqueue_source_changes(
    project_root: Path,
    *,
    config: Mapping[str, Any] | None = None,
    source_section_ids: Sequence[str],
    semantic_hashes: Mapping[str, str] | None = None,
    reason: str,
    pending_concept_diff_id: str | None = None,
    detected_at: str | None = None,
) -> WatchQueue:
    if not source_section_ids:
        return load_watch_queue(watch_queue_path(project_root, config))
    detected = detected_at or _now()
    path = watch_queue_path(project_root, config)
    queue = load_watch_queue(path)
    by_section = {change.source_section_id: change for change in queue.changes}
    hashes = semantic_hashes or {}
    for section_id in source_section_ids:
        by_section[section_id] = QueuedSourceChange(
            source_section_id=section_id,
            semantic_hash=str(hashes.get(section_id) or ""),
            reason=reason,
            detected_at=detected,
        )
    updated = WatchQueue(
        updated_at=detected,
        pending_concept_diff_id=pending_concept_diff_id or queue.pending_concept_diff_id,
        changes=sorted(by_section.values(), key=lambda item: item.source_section_id),
    )
    write_watch_queue_atomic(path, updated)
    return updated


def remove_watch_queue_changes(
    project_root: Path,
    *,
    config: Mapping[str, Any] | None = None,
    reasons: set[str] | frozenset[str] | None = None,
    matching_semantic_hashes: Mapping[str, str] | None = None,
) -> WatchQueue:
    path = watch_queue_path(project_root, config)
    queue = load_watch_queue(path)
    if not queue.changes:
        return queue

    kept: list[QueuedSourceChange] = []
    for change in queue.changes:
        if reasons is not None and change.reason not in reasons:
            kept.append(change)
            continue
        if matching_semantic_hashes is not None:
            current_hash = matching_semantic_hashes.get(change.source_section_id, "")
            if current_hash != change.semantic_hash:
                kept.append(change)
                continue
        # Otherwise this change was processed by the latest watcher run.

    pending_concept_diff_id = (
        queue.pending_concept_diff_id
        if any(change.reason == "pending_concept_diff_unresolved" for change in kept)
        else None
    )
    updated = WatchQueue(
        updated_at=_now(),
        pending_concept_diff_id=pending_concept_diff_id,
        changes=sorted(kept, key=lambda item: item.source_section_id),
    )
    write_watch_queue_atomic(path, updated)
    return updated


def semantic_hashes_for_manifest(manifest: SourceManifest) -> dict[str, str]:
    return {
        entry.section_id: entry.semantic_hash or entry.source_hash
        for entry in manifest.entries
    }


def load_provisional_concept_cache(path: Path) -> ProvisionalConceptCache:
    if not path.exists():
        return ProvisionalConceptCache()
    return ProvisionalConceptCache.model_validate_json(path.read_text(encoding="utf-8"))


def write_provisional_concept_cache_atomic(
    path: Path, cache: ProvisionalConceptCache
) -> None:
    _write_json_atomic(path, cache.model_dump(mode="json"))


def update_provisional_concept_cache(
    project_root: Path,
    *,
    terms: Sequence[Mapping[str, str]],
    semantic_hashes: Mapping[str, str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    seen_at: str | None = None,
) -> ProvisionalConceptCache:
    if not terms:
        return load_provisional_concept_cache(provisional_concept_cache_path(project_root))
    now = seen_at or _now()
    hashes = semantic_hashes or {}
    path = provisional_concept_cache_path(project_root)
    cache = load_provisional_concept_cache(path)
    by_label = {candidate.normalized_label: candidate for candidate in cache.candidates}
    for term in terms:
        label = str(term.get("proposed_text") or term.get("term") or "").strip()
        if not label:
            continue
        normalized = normalize_label(label)
        section_id = str(term.get("source_section_id") or "")
        previous = by_label.get(normalized)
        supporting_sections = sorted(
            {
                *(previous.supporting_sections if previous else []),
                *([section_id] if section_id else []),
            }
        )
        semantic_values = sorted(
            {
                *(previous.semantic_hashes if previous else []),
                *([hashes[section_id]] if section_id and hashes.get(section_id) else []),
            }
        )
        by_label[normalized] = ProvisionalConceptCandidate(
            label=previous.label if previous else label,
            normalized_label=normalized,
            aliases=previous.aliases if previous else [],
            supporting_sections=supporting_sections,
            semantic_hashes=semantic_values,
            confidence=previous.confidence if previous else 0.5,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            first_seen=previous.first_seen if previous else now,
            last_seen=now,
            status=previous.status if previous else "provisional",
        )
    updated = ProvisionalConceptCache(
        updated_at=now,
        candidates=sorted(by_label.values(), key=lambda item: item.normalized_label),
    )
    write_provisional_concept_cache_atomic(path, updated)
    return updated


def semantic_digest_for_manifest(manifest: SourceManifest) -> str:
    payload = [
        {
            "section_id": entry.section_id,
            "semantic_hash": entry.semantic_hash or entry.source_hash,
        }
        for entry in sorted(manifest.entries, key=lambda item: item.section_id)
    ]
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"semantic:{digest[:24]}"


def normalize_label(text: str) -> str:
    return "".join(char.lower() for char in text if char.isalnum())


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _configured_watcher_path(
    project_root: Path,
    config: Mapping[str, Any] | None,
    *,
    key: str,
    default: str,
) -> Path:
    watcher = config.get("watcher") if isinstance(config, Mapping) else None
    configured = (
        watcher.get(key)
        if isinstance(watcher, Mapping) and watcher.get(key) is not None
        else default
    )
    path = Path(str(configured))
    if not path.is_absolute():
        path = project_root / path
    return path
