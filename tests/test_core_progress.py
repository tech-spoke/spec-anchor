"""Unit and integration tests for `spec_anchor.core_progress`.

These pin the contract for `.spec-anchor/state/core_progress.json` so that a
crashed `/spec-core --all` run still leaves a useful diagnostic trail.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spec_anchor.core_progress import (
    CoreProgressTracker,
    progress_file_path,
    read_progress,
)


def test_tracker_records_stage_transitions(tmp_path: Path) -> None:
    tracker = CoreProgressTracker(tmp_path, run_id="run-1", mode="full")

    tracker.emit("core_start")
    tracker.emit("core_section_metadata_start")
    tracker.emit("core_section_metadata_done")
    tracker.emit("core_artifact_write_start")
    tracker.emit("core_artifact_write_done")
    tracker.finalize(status="completed")

    payload = read_progress(tmp_path)
    assert payload is not None
    assert payload["run_id"] == "run-1"
    assert payload["mode"] == "full"
    assert payload["final_status"] == "completed"
    assert payload["finalized_at"] is not None
    assert payload["stage_order"][0] == "start"
    assert payload["stage_order"][-1] == "artifact_write"
    metadata_stage = payload["stages"]["section_metadata"]
    assert metadata_stage["finished_at"] is not None
    assert metadata_stage["elapsed_sec"] >= 0


def test_tracker_persists_after_each_emit(tmp_path: Path) -> None:
    tracker = CoreProgressTracker(tmp_path, run_id="run-2", mode="incremental")
    tracker.emit("core_start")

    snapshot = read_progress(tmp_path)
    assert snapshot is not None
    assert snapshot["current_stage"] == "start"

    tracker.emit("core_section_metadata_start")
    snapshot = read_progress(tmp_path)
    assert snapshot is not None
    assert snapshot["current_stage"] == "section_metadata"
    assert snapshot["stages"]["start"]["finished_at"] is not None


def test_tracker_increment_aggregates_counts(tmp_path: Path) -> None:
    tracker = CoreProgressTracker(tmp_path, run_id="run-3", mode="full")
    tracker.emit("core_section_metadata_start")
    tracker.increment("section_metadata", llm_calls=8, token_count=12000)
    tracker.increment("section_metadata", llm_calls=5, token_count=8000, retry_count=1)
    tracker.increment(
        "section_metadata",
        failed_batch_ids=["batch-3", "batch-3", "batch-7"],
    )

    payload = read_progress(tmp_path)
    assert payload is not None
    metadata_stage = payload["stages"]["section_metadata"]
    assert metadata_stage["llm_calls"] == 13
    assert metadata_stage["token_count"] == 20000
    assert metadata_stage["retry_count"] == 1
    assert metadata_stage["failed_batch_ids"] == ["batch-3", "batch-7"]


def test_tracker_writes_under_spec_anchor_state(tmp_path: Path) -> None:
    CoreProgressTracker(tmp_path, run_id="run-4", mode="full")
    expected = tmp_path / ".spec-anchor" / "state" / "core_progress.json"
    assert expected.is_file()
    assert progress_file_path(tmp_path) == expected


def test_read_progress_returns_none_when_missing(tmp_path: Path) -> None:
    assert read_progress(tmp_path) is None


def test_run_spec_core_writes_progress_artifact(tmp_path: Path) -> None:
    from tests.test_spec_core import (
        FakeSpecCoreProvider,
        _run_spec_core,
        _write_project,
    )

    _write_project(tmp_path)
    _run_spec_core(tmp_path, all_mode=True, provider=FakeSpecCoreProvider())

    payload = read_progress(tmp_path)
    assert payload is not None
    assert payload["mode"] == "full"
    assert payload["final_status"] == "completed"
    assert "section_metadata" in payload["stages"]
    assert "artifact_write" in payload["stages"]
    artifact_stage = payload["stages"]["artifact_write"]
    assert artifact_stage["finished_at"] is not None


def test_record_llm_call_stats_aggregates_codex_usage(tmp_path) -> None:
    """Phase B follow-up (token capture): usage from codex stdout flows
    through LlmGenerationResult.usage into core_progress.json."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from spec_anchor.core import _record_llm_call_stats
    from spec_anchor.core_progress import CoreProgressTracker
    from spec_anchor.llm_provider import LlmGenerationResult

    tracker = CoreProgressTracker(tmp_path, run_id="run-usage", mode="full")
    tracker.emit("core_section_metadata_start")
    results = [
        LlmGenerationResult(
            status="success",
            attempts=1,
            usage={
                "provider": "codex",
                "input_tokens": 1200,
                "cached_input_tokens": 800,
                "output_tokens": 150,
                "reasoning_output_tokens": 50,
            },
        ),
        LlmGenerationResult(
            status="success",
            attempts=1,
            usage={
                "provider": "codex",
                "input_tokens": 1500,
                "cached_input_tokens": 900,
                "output_tokens": 200,
                "reasoning_output_tokens": 70,
            },
        ),
    ]
    _record_llm_call_stats(tracker, "section_metadata", results)
    payload = read_progress(tmp_path)
    assert payload is not None
    stage = payload["stages"]["section_metadata"]
    assert stage["llm_calls"] == 2
    assert stage["retry_count"] == 0
    assert stage["token_count"] == (1200 + 1500) + (150 + 200)
    usage = stage["usage"]
    assert usage["input_tokens"] == 2700
    assert usage["output_tokens"] == 350
    assert usage["cached_input_tokens"] == 1700
    assert usage["reasoning_output_tokens"] == 120
    assert "codex" in usage["providers_seen"]


def test_extract_cli_usage_handles_codex_stream() -> None:
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from spec_anchor.llm_provider import _extract_cli_usage

    stdout = (
        '{"type":"thread.started","thread_id":"abc"}\n'
        '{"type":"turn.started"}\n'
        '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"x\\":1}"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":1199,"cached_input_tokens":2432,"output_tokens":77,"reasoning_output_tokens":50}}'
    )
    usage = _extract_cli_usage(stdout)
    assert usage["provider"] == "codex"
    assert usage["input_tokens"] == 1199
    assert usage["cached_input_tokens"] == 2432
    assert usage["output_tokens"] == 77
    assert usage["reasoning_output_tokens"] == 50


def test_extract_cli_usage_handles_claude_json() -> None:
    import json as _json
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from spec_anchor.llm_provider import _extract_cli_usage

    stdout = _json.dumps(
        {
            "type": "result",
            "result": "ok",
            "total_cost_usd": 0.0235,
            "usage": {
                "input_tokens": 9,
                "output_tokens": 147,
                "cache_creation_input_tokens": 18283,
                "cache_read_input_tokens": 0,
            },
        }
    )
    usage = _extract_cli_usage(stdout)
    assert usage["provider"] == "claude"
    assert usage["input_tokens"] == 9
    assert usage["output_tokens"] == 147
    assert usage["cache_creation_input_tokens"] == 18283
    assert usage["total_cost_usd"] == 0.0235
