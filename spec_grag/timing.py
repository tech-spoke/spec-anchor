"""Lightweight stage timing diagnostics for run artifacts."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


HEAVY_CORE_STAGES = {
    "schema_llm_extraction",
    "embedding_update",
    "chunk_index_update",
    "graph_sidecar_update",
    "concept_diff",
    "community_report",
}


@dataclass
class StageScope:
    recorder: TimingRecorder
    stage: str
    started_ns: int
    status: str = "ok"
    metrics: dict[str, Any] = field(default_factory=dict)

    def set_status(self, status: str) -> None:
        self.status = status

    def __enter__(self) -> StageScope:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if exc_type is not None and self.status == "ok":
            self.status = "failed"
        finished_ns = time.perf_counter_ns()
        self.recorder.record_stage(
            stage=self.stage,
            duration_ns=finished_ns - self.started_ns,
            status=self.status,
            metrics=self.metrics,
        )
        return False


class TimingRecorder:
    """Collect monotonic stage timings without retaining request/response bodies."""

    def __init__(self) -> None:
        self.started_ns = time.perf_counter_ns()
        self._records: list[dict[str, Any]] = []
        self._flags: dict[str, Any] = {}

    def stage(
        self,
        stage: str,
        *,
        metrics: Mapping[str, Any] | None = None,
        status: str = "ok",
    ) -> StageScope:
        return StageScope(
            recorder=self,
            stage=stage,
            started_ns=time.perf_counter_ns(),
            status=status,
            metrics=dict(metrics or {}),
        )

    def record_stage(
        self,
        *,
        stage: str,
        duration_ns: int,
        status: str,
        metrics: Mapping[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "stage": stage,
            "duration_ms": _duration_ms(duration_ns),
            "status": status,
        }
        safe_metrics = _safe_metrics(metrics or {})
        if safe_metrics:
            record["metrics"] = safe_metrics
        self._records.append(record)

    def set_flag(self, key: str, value: Any) -> None:
        self._flags[key] = value

    def stage_timings(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self._records]

    def summary(self, *, status: str | None = None) -> dict[str, Any]:
        records = self.stage_timings()
        llm_call_count = sum(_metric_int(record, "llm_calls") for record in records)
        llm_total_duration_ms = sum(
            float(record.get("duration_ms", 0.0))
            for record in records
            if _metric_int(record, "llm_calls") > 0
        )
        embedding_total_duration_ms = sum(
            float(record.get("duration_ms", 0.0))
            for record in records
            if record.get("stage") == "embedding_update"
        )
        community_total_duration_ms = sum(
            float(record.get("duration_ms", 0.0))
            for record in records
            if record.get("stage") == "community_report"
        )
        heavy_path = bool(
            self._flags.get(
                "heavy_path",
                any(record.get("stage") in HEAVY_CORE_STAGES for record in records),
            )
        )
        semantic_noop = bool(
            self._flags.get(
                "semantic_noop",
                any(
                    _metric_bool(record, "semantic_noop")
                    for record in records
                    if record.get("stage") == "semantic_noop_filter"
                ),
            )
        )
        summary: dict[str, Any] = {
            "total_duration_ms": _duration_ms(time.perf_counter_ns() - self.started_ns),
            "heavy_path": heavy_path,
            "semantic_noop": semantic_noop,
            "llm_call_count": llm_call_count,
            "llm_total_duration_ms": round(llm_total_duration_ms, 3),
            "embedding_total_duration_ms": round(embedding_total_duration_ms, 3),
            "community_total_duration_ms": round(community_total_duration_ms, 3),
        }
        if status is not None:
            summary["status"] = status
        return summary


def timing_recorder(timer: TimingRecorder | None) -> TimingRecorder:
    return timer if timer is not None else TimingRecorder()


def llm_config_metrics(
    config: Mapping[str, Any],
    section: str,
    *,
    default_provider: str,
    disabled_providers: set[str],
) -> dict[str, Any]:
    section_config = _mapping(config.get(section))
    provider = str(section_config.get("provider", default_provider)).strip().lower()
    metrics: dict[str, Any] = {"provider": provider}
    model = section_config.get("model")
    if model is not None:
        metrics["model"] = str(model)
    metrics["llm_calls"] = 0 if provider in disabled_providers else 1
    return metrics


def embedding_config_metrics(config: Mapping[str, Any]) -> dict[str, Any]:
    section_config = _mapping(config.get("embedding"))
    return {
        "provider": str(section_config.get("provider", "stable_hash")),
        "model": str(section_config.get("model", "sha256-v1")),
        "dimension": int(section_config.get("dimension", 8)),
    }


def _duration_ms(duration_ns: int) -> float:
    return round(max(duration_ns, 0) / 1_000_000, 3)


def _metric_int(record: Mapping[str, Any], key: str) -> int:
    value = _metrics(record).get(key, 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _metric_bool(record: Mapping[str, Any], key: str) -> bool:
    return bool(_metrics(record).get(key, False))


def _metrics(record: Mapping[str, Any]) -> Mapping[str, Any]:
    metrics = record.get("metrics")
    return metrics if isinstance(metrics, Mapping) else {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metrics.items():
        if value is None:
            continue
        safe[str(key)] = _safe_value(value)
    return safe


def _safe_value(value: Any) -> Any:
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple):
        return [_safe_value(item) for item in value[:50]]
    if isinstance(value, Mapping):
        return {str(key): _safe_value(item) for key, item in list(value.items())[:50]}
    return str(value)
