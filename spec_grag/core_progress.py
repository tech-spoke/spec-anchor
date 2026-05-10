"""Persist `/spec-core` stage progress to `.spec-grag/state/core_progress.json`.

This module makes `spec-grag core` runs observable when they take long or
timeout. Stage transitions, LLM call counts, token usage, retries, and any
failed batch ids are written atomically each time the tracker is updated, so
even a killed process leaves a usable diagnostic trail at the file path
returned by :func:`progress_file_path`.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROGRESS_FILENAME = "core_progress.json"


def progress_file_path(root: Path | str) -> Path:
    return Path(root) / ".spec-grag" / "state" / PROGRESS_FILENAME


def _stage_label(raw: str) -> str:
    label = raw.removeprefix("core_")
    if label.endswith("_start"):
        label = label[: -len("_start")]
    elif label.endswith("_done"):
        label = label[: -len("_done")]
    return label or raw


def _stage_phase(raw: str) -> str:
    if raw.endswith("_start"):
        return "start"
    if raw.endswith("_done"):
        return "done"
    return "checkpoint"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class CoreProgressTracker:
    """File-backed tracker for `/spec-core` stage progress.

    The same tracker is used across all stages of a single run. Each public
    method persists the full state to disk, so a crash leaves a recoverable
    snapshot.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        run_id: str,
        mode: str,
        generated_at: str | None = None,
    ) -> None:
        self.path = progress_file_path(root)
        self.run_id = run_id
        self.mode = mode
        self.generated_at = generated_at
        self._started_at = _now_iso()
        self._started_epoch = time.time()
        self._stages: dict[str, dict[str, Any]] = {}
        self._stage_order: list[str] = []
        self._current_stage: str | None = None
        self._finalized_at: str | None = None
        self._persist()

    def emit(self, raw_stage: str) -> None:
        """Handle a heartbeat-style stage marker (e.g. ``core_section_metadata_start``)."""

        label = _stage_label(raw_stage)
        phase = _stage_phase(raw_stage)
        if phase == "start":
            self._begin(label, raw_stage)
        elif phase == "done":
            self._finish(label, raw_stage)
        else:
            self._checkpoint(label, raw_stage)
        self._persist()

    def increment(
        self,
        stage: str,
        *,
        llm_calls: int = 0,
        token_count: int = 0,
        retry_count: int = 0,
        failed_batch_ids: list[str] | None = None,
    ) -> None:
        entry = self._stage_entry(stage)
        if llm_calls:
            entry["llm_calls"] = int(entry.get("llm_calls", 0)) + int(llm_calls)
        if token_count:
            entry["token_count"] = int(entry.get("token_count", 0)) + int(token_count)
        if retry_count:
            entry["retry_count"] = int(entry.get("retry_count", 0)) + int(retry_count)
        if failed_batch_ids:
            existing = list(entry.get("failed_batch_ids", []))
            for batch_id in failed_batch_ids:
                if batch_id not in existing:
                    existing.append(batch_id)
            entry["failed_batch_ids"] = existing
        self._persist()

    def update(self, stage: str, **fields: Any) -> None:
        entry = self._stage_entry(stage)
        entry.update(fields)
        self._persist()

    def finalize(self, *, status: str = "completed") -> None:
        if self._current_stage and self._stages.get(self._current_stage, {}).get("finished_at") is None:
            self._finish(self._current_stage, raw=f"core_{self._current_stage}_done")
        self._finalized_at = _now_iso()
        self._final_status = status
        self._persist()

    def _begin(self, label: str, raw: str) -> None:
        if self._current_stage and self._current_stage != label:
            previous = self._stages.get(self._current_stage)
            if previous and previous.get("finished_at") is None:
                self._finish(self._current_stage, raw=f"core_{self._current_stage}_done")
        entry = self._stages.get(label)
        if entry is None:
            entry = {
                "stage": label,
                "raw": raw,
                "started_at": _now_iso(),
                "started_at_epoch": time.time(),
                "llm_calls": 0,
                "token_count": 0,
                "retry_count": 0,
                "failed_batch_ids": [],
            }
            self._stages[label] = entry
            self._stage_order.append(label)
        else:
            entry.setdefault("started_at", _now_iso())
            entry.setdefault("started_at_epoch", time.time())
        self._current_stage = label

    def _finish(self, label: str, raw: str) -> None:
        entry = self._stages.get(label)
        if entry is None:
            entry = {
                "stage": label,
                "raw": raw,
                "started_at": _now_iso(),
                "started_at_epoch": time.time(),
                "llm_calls": 0,
                "token_count": 0,
                "retry_count": 0,
                "failed_batch_ids": [],
            }
            self._stages[label] = entry
            self._stage_order.append(label)
        now_epoch = time.time()
        entry["finished_at"] = _now_iso()
        entry["elapsed_sec"] = round(now_epoch - float(entry.get("started_at_epoch", now_epoch)), 3)
        if self._current_stage == label:
            self._current_stage = None

    def _checkpoint(self, label: str, raw: str) -> None:
        entry = self._stage_entry(label, raw=raw)
        checkpoints = list(entry.get("checkpoints", []))
        checkpoints.append({"raw": raw, "at": _now_iso()})
        entry["checkpoints"] = checkpoints

    def _stage_entry(self, label: str, *, raw: str | None = None) -> dict[str, Any]:
        entry = self._stages.get(label)
        if entry is None:
            entry = {
                "stage": label,
                "raw": raw or f"core_{label}",
                "started_at": _now_iso(),
                "started_at_epoch": time.time(),
                "llm_calls": 0,
                "token_count": 0,
                "retry_count": 0,
                "failed_batch_ids": [],
            }
            self._stages[label] = entry
            self._stage_order.append(label)
        return entry

    def _persist(self) -> None:
        payload = {
            "run_id": self.run_id,
            "mode": self.mode,
            "generated_at": self.generated_at,
            "started_at": self._started_at,
            "started_at_epoch": self._started_epoch,
            "updated_at": _now_iso(),
            "current_stage": self._current_stage,
            "finalized_at": getattr(self, "_finalized_at", None),
            "final_status": getattr(self, "_final_status", None),
            "stage_order": list(self._stage_order),
            "stages": {label: dict(entry) for label, entry in self._stages.items()},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        os.replace(tmp, self.path)


def read_progress(root: Path | str) -> Mapping[str, Any] | None:
    path = progress_file_path(root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


__all__ = [
    "CoreProgressTracker",
    "PROGRESS_FILENAME",
    "progress_file_path",
    "read_progress",
]
