"""Watcher contract tests for G-14.

These tests pin the external watcher contract while giving the implementation
some room on exact return objects.  They intentionally use a tiny fake project
and injected runners so no Qdrant, FlagEmbedding, or real LLM service is used.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


CONFIG = """\
[sources]
include = ["docs/spec/**/*.md"]
exclude = []

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[context]
storage = ".spec-grag/context"

[llm]
provider = "fake"
model = "fake-watcher"
timeout_sec = 5
max_retries = 0

[embedding]
provider = "fake"
model = "fake-embedding"

[vector_store]
provider = "memory"

[watcher]
enabled = true
interval_ms = 2000
debounce_ms = 1000
stale_lock_ms = 300000
state_file = ".spec-grag/state/watch_state.json"
queue_file = ".spec-grag/state/watch_queue.json"
"""

TRUE_VALUES = {"1", "true", "yes", "on"}


def _has_section_id(ids: list[str] | set[str], expected: str) -> bool:
    return any(
        value == expected
        or re.sub(r"#\d{4}-", "#", str(value)) == expected
        for value in ids
    )


def _real_smoke_enabled() -> bool:
    return (
        os.environ.get("SPEC_GRAG_REAL_SMOKE", "").lower() in TRUE_VALUES
        and os.environ.get("SPEC_GRAG_LOCAL_SERVICE", "").lower() in TRUE_VALUES
    )


@pytest.fixture()
def fake_project(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "project"
    (root / ".spec-grag/state").mkdir(parents=True)
    (root / "docs/core").mkdir(parents=True)
    (root / "docs/spec").mkdir(parents=True)
    (root / ".spec-grag/config.toml").write_text(CONFIG)
    (root / "docs/core/purpose.md").write_text("# Purpose\nShip reliable behavior.\n")
    (root / "docs/core/concept.md").write_text("# Concept\nSource Specs are authoritative.\n")
    source = root / "docs/spec/main.md"
    source.write_text("# Main\n\n## Alpha\nInitial source text.\n")
    return {
        "root": root,
        "source": source,
        "state": root / ".spec-grag/state/watch_state.json",
        "queue": root / ".spec-grag/state/watch_queue.json",
    }


def _write_real_watcher_project(root: Path, *, collection: str, qdrant_url: str) -> None:
    (root / ".spec-grag/state").mkdir(parents=True)
    (root / "docs/core").mkdir(parents=True)
    (root / "docs/spec").mkdir(parents=True)
    (root / ".spec-grag/config.toml").write_text(
        f"""\
[sources]
include = ["docs/spec/**/*.md"]
exclude = []

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[context]
storage = ".spec-grag/context"

[section]
max_heading_level = 4

[llm]
provider = "fake"
model = "fake-real-watcher"
timeout_sec = 5
max_retries = 0

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"
dense_enabled = true
sparse_enabled = true

[vector_store]
provider = "qdrant"
url = "{qdrant_url}"
collection = "{collection}"

[watcher]
enabled = true
interval_ms = 0
debounce_ms = 1
stale_lock_ms = 300000
state_file = ".spec-grag/state/watch_state.json"
queue_file = ".spec-grag/state/watch_queue.json"
"""
    )
    (root / "docs/core/purpose.md").write_text("# Purpose\nVerify real watcher operation.\n")
    (root / "docs/core/concept.md").write_text("# Concept\nSource Specs are authoritative.\n")
    (root / "docs/spec/main.md").write_text(
        "# Main\n\n## Real Watcher Baseline\nThe real watcher baseline is indexed.\n"
    )


def _watcher_module() -> Any:
    try:
        return importlib.import_module("spec_grag.watcher")
    except ModuleNotFoundError as exc:
        if exc.name == "spec_grag.watcher":
            pytest.fail("spec_grag.watcher module is required for G-14 Watcher")
        raise


def _required_function(module: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail("Watcher API is required; expected one of: " + ", ".join(names))


def _watch_once_function() -> Any:
    return _required_function(
        _watcher_module(),
        (
            "run_watcher_once",
            "run_watcher_cycle",
            "run_spec_grag_watch_once",
            "run_spec_grag_watch",
            "watch",
        ),
    )


def _call_adaptive(func: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    supported = {
        name: value for name, value in kwargs.items() if name in signature.parameters
    }
    if "project_root" in signature.parameters:
        return func(**supported)
    try:
        return func(kwargs["project_root"], **supported)
    except TypeError:
        return func(**supported)


def _run_once(project_root: Path, **kwargs: Any) -> Any:
    func = _watch_once_function()
    return _call_adaptive(
        func,
        project_root=project_root,
        root=project_root,
        cwd=project_root,
        once=True,
        max_runs=1,
        interval_ms=0,
        debounce_ms=0,
        stale_lock_ms=kwargs.pop("stale_lock_ms", 300_000),
        now_ms=kwargs.pop("now_ms", 1_000_000),
        wait=False,
        blocking=False,
        **kwargs,
    )


def test_watcher_snapshot_respects_config_loader_sources_exclude(
    fake_project: dict[str, Path],
) -> None:
    watcher = _watcher_module()
    root = fake_project["root"]
    config_path = root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text().replace(
            "exclude = []",
            'exclude = ["docs/spec/drafts/**"]',
        )
    )
    draft = root / "docs/spec/drafts/ignored.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("# Draft\nWatcher must not snapshot this draft.\n")

    snapshot = watcher.collect_source_snapshot(root)
    paths = {str(item["relative_path"]) for item in snapshot["files"]}

    assert "docs/spec/main.md" in paths
    assert "docs/spec/drafts/ignored.md" not in paths


def test_watcher_settings_fail_when_sources_include_matches_no_files(
    fake_project: dict[str, Path],
) -> None:
    watcher = _watcher_module()
    root = fake_project["root"]
    config_path = root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text().replace(
            'include = ["docs/spec/**/*.md"]',
            'include = ["docs/spec/missing/**/*.md"]',
        )
    )

    with pytest.raises(Exception) as exc_info:
        watcher.load_watcher_settings(root)

    assert "sources.include" in str(exc_info.value)


def _value(value: Any, *path: str, default: Any = None) -> Any:
    current = value
    for key in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            current = getattr(current, key, default)
    return current


def _freshness(result: Any) -> dict[str, Any]:
    for key in ("freshness_report", "freshness", "report"):
        nested = _value(result, key)
        if isinstance(nested, dict) and "status" in nested:
            return nested
    if isinstance(result, dict) and "status" in result and "blocking_reasons" in result:
        return result
    return {}


def _reasons(result: Any) -> list[str]:
    reasons = _value(_freshness(result), "blocking_reasons", default=[])
    assert isinstance(reasons, list), "watcher result must expose freshness blocking_reasons"
    return reasons


def _status(result: Any) -> str:
    status = _value(_freshness(result), "status")
    assert isinstance(status, str), "watcher result must expose freshness status"
    return status


def _maybe_status(result: Any) -> str | None:
    try:
        return _status(result)
    except AssertionError:
        value = _value(result, "status")
        return value if isinstance(value, str) else None


def _maybe_reasons(result: Any) -> list[str]:
    try:
        return _reasons(result)
    except AssertionError:
        value = _value(result, "blocking_reasons", default=[])
        return value if isinstance(value, list) else []


def _queue_items(result: Any, queue_file: Path) -> list[Any]:
    for key in ("queued_changes", "queue", "pending_changes"):
        value = _value(result, key)
        if isinstance(value, list):
            return value
    if not queue_file.exists():
        return []
    payload = json.loads(queue_file.read_text())
    if isinstance(payload, list):
        return payload
    for key in ("changes", "queued_changes", "queue", "items"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, list):
            return value
    return []


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _assert_exclusive_block_result(result: Any, *expected_terms: str) -> None:
    status = _maybe_status(result) or _value(result, "status")
    reasons = _maybe_reasons(result)
    text = _json_text({"status": status, "reasons": reasons, "result": result}).lower()

    assert status in {"blocked", "locked", "idle"} or any(
        term in text for term in ("locked", "blocked", "running")
    ), "watcher must expose that the run was blocked by an active exclusive owner"
    assert any(term in text for term in expected_terms), (
        "watcher block result must identify the active owner or lock condition"
    )


def _heartbeat_callable(kwargs: dict[str, Any]) -> Any:
    for name in (
        "heartbeat",
        "watcher_heartbeat",
        "heartbeat_callback",
        "touch_lock",
        "touch_core_update_lock",
    ):
        value = kwargs.get(name)
        if callable(value):
            return value
    pytest.fail(
        "watcher must pass a heartbeat callable to its internal core runner "
        "so long runs can refresh watch_state and the shared update lock"
    )


def _call_heartbeat(heartbeat: Any, *, now_ms: int) -> Any:
    signature = inspect.signature(heartbeat)
    if "now_ms" in signature.parameters:
        return heartbeat(now_ms=now_ms)
    if "timestamp_ms" in signature.parameters:
        return heartbeat(timestamp_ms=now_ms)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return heartbeat(now_ms=now_ms)
    if len(signature.parameters) == 1:
        return heartbeat(now_ms)
    return heartbeat()


def _lock_updated_at(project_root: Path) -> int:
    lock_path = project_root / ".spec-grag/state/core_update.lock.json"
    assert lock_path.is_file(), "watcher must hold the shared core-update lock while internal core runs"
    payload = json.loads(lock_path.read_text())
    return int(payload["updated_at_epoch_ms"])


def _core_update_lock_path(project_root: Path) -> Path:
    return project_root / ".spec-grag/state/core_update.lock.json"


def _active_marker_payload(payload: dict[str, Any]) -> dict[str, Any]:
    active_keys = (
        "owner",
        "run_id",
        "started_at",
        "started_at_epoch_ms",
        "lock_file",
        "queue_count_at_start",
        "current_snapshot",
        "lock",
    )
    return {key: payload[key] for key in active_keys if key in payload}


def _state_updated_at(state_file: Path) -> int:
    assert state_file.is_file(), "watcher must publish watch_state while internal core runs"
    payload = json.loads(state_file.read_text())
    return int(payload["updated_at_epoch_ms"])


def _snapshot_text(snapshot: Any, project_root: Path, source: Path) -> str:
    if isinstance(snapshot, dict):
        for key in ("files", "sources", "source_specs"):
            value = snapshot.get(key)
            if isinstance(value, dict):
                text = value.get("docs/spec/main.md") or value.get(str(source))
                if isinstance(text, str):
                    return text
            if isinstance(value, list):
                for item in value:
                    path = _value(item, "path") or _value(item, "source_path")
                    text = _value(item, "text") or _value(item, "content")
                    if str(path).endswith("docs/spec/main.md") and isinstance(text, str):
                        return text
        text = snapshot.get("docs/spec/main.md") or snapshot.get(str(source))
        if isinstance(text, str):
            return text
    candidate = Path(project_root) / "docs/spec/main.md"
    return candidate.read_text()


def test_snapshot_isolation_queue_and_next_run(fake_project: dict[str, Path]) -> None:
    root = fake_project["root"]
    source = fake_project["source"]
    queue = fake_project["queue"]
    processed_texts: list[str] = []

    def core_runner(project_root: Path = root, **kwargs: Any) -> dict[str, Any]:
        if not processed_texts:
            source.write_text(source.read_text() + "\n## Beta\nChanged after run start.\n")
        snapshot = (
            kwargs.get("source_snapshot")
            or kwargs.get("snapshot")
            or kwargs.get("snapshot_sources")
            or kwargs.get("sources")
        )
        processed_texts.append(_snapshot_text(snapshot, Path(project_root), source))
        return {"freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []}}

    first = _run_once(root, core_runner=core_runner, runner=core_runner)

    assert processed_texts, "watcher must invoke an internal core runner"
    assert "Changed after run start" not in processed_texts[0], (
        "Source Specs modified after run start must not be included in that run's snapshot"
    )
    assert _queue_items(first, queue), "changes observed during a run must remain queued"
    assert _status(first) == "blocked"
    assert "watcher_queue_pending" in _reasons(first)

    second = _run_once(root, core_runner=core_runner, runner=core_runner, now_ms=1_001_000)

    assert any("Changed after run start" in text for text in processed_texts[1:])
    assert _queue_items(second, queue) == []
    assert _status(second) == "fresh"
    assert "watcher_queue_pending" not in _reasons(second)


def test_watcher_does_not_enter_internal_runner_while_spec_core_running(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    state = fake_project["state"]
    calls: list[str] = []

    state.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": True,
                "owner": "spec-core",
                "run_id": "manual-core-run",
                "started_at_epoch_ms": 1_000_000,
                "updated_at_epoch_ms": 1_000_000,
            }
        )
    )

    def core_runner(**_: Any) -> dict[str, Any]:
        calls.append("called")
        return {"freshness_report": {"status": "fresh", "blocking_reasons": []}}

    result = _run_once(root, core_runner=core_runner, runner=core_runner, now_ms=1_000_100)

    assert calls == [], "watcher must not enter the internal core runner while `/spec-core` owns the lock"
    assert _value(result, "ran_core") is False
    _assert_exclusive_block_result(result, "watcher_running", "spec-core", "core", "locked")


def test_watcher_lock_acquisition_is_atomic_when_lock_already_held(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    state = fake_project["state"]
    queue = fake_project["queue"]
    calls: list[str] = []

    state.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": True,
                "owner": "watcher",
                "run_id": "first-watcher-run",
                "started_at_epoch_ms": 1_000_000,
                "updated_at_epoch_ms": 1_000_000,
            }
        )
    )
    queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "queue": [
                    {
                        "relative_path": "docs/spec/main.md",
                        "path": "docs/spec/main.md",
                        "change_type": "modified",
                    }
                ],
            }
        )
    )

    def core_runner(**_: Any) -> dict[str, Any]:
        calls.append("called")
        return {"freshness_report": {"status": "fresh", "blocking_reasons": []}}

    result = _run_once(root, core_runner=core_runner, runner=core_runner, now_ms=1_000_100)

    assert calls == [], "a second watcher must not enter the core runner when lock state is already held"
    assert _value(result, "ran_core") is False
    _assert_exclusive_block_result(result, "watcher_running", "watcher", "locked")


def test_running_watcher_blocks_second_start(fake_project: dict[str, Path]) -> None:
    root = fake_project["root"]
    nested_results: list[Any] = []

    def inner_runner(**_: Any) -> dict[str, Any]:
        nested_results.append(_run_once(root, core_runner=lambda **__: {}, runner=lambda **__: {}))
        return {"freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []}}

    _run_once(root, core_runner=inner_runner, runner=inner_runner)

    assert nested_results, "second watcher start was not attempted during the running lock"
    nested = nested_results[0]
    blob = json.dumps(nested, sort_keys=True, default=str).lower()
    assert (
        _maybe_status(nested) in {"blocked", "locked"}
        or "watcher_running" in _maybe_reasons(nested)
        or "locked" in blob
        or "blocked" in blob
    ), "a second watcher must not proceed while another watcher run is active"


def test_stale_lock_allows_new_run(fake_project: dict[str, Path]) -> None:
    state = fake_project["state"]
    state.write_text(
        json.dumps(
            {
                "running": True,
                "updated_at_ms": 1_000,
                "lock": {"owner": "dead-process", "acquired_at_ms": 1_000},
            }
        )
    )
    calls: list[str] = []

    result = _run_once(
        fake_project["root"],
        stale_lock_ms=100,
        now_ms=1_500,
        core_runner=lambda **_: calls.append("ran") or {},
        runner=lambda **_: calls.append("ran") or {},
    )

    assert calls == ["ran"]
    assert "stale" in json.dumps(result, sort_keys=True, default=str).lower()
    assert _status(result) == "fresh"


def test_stale_lock_with_legacy_is_running_allows_new_run(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    state = fake_project["state"]
    calls: list[str] = []

    state.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": True,
                "is_running": True,
                "owner": "watcher",
                "run_id": "stale-watcher-run",
                "started_at_epoch_ms": 1_000,
                "updated_at_epoch_ms": 1_000,
            }
        )
    )

    def core_runner(**_: Any) -> dict[str, Any]:
        calls.append("ran")
        return {"freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []}}

    result = _run_once(
        root,
        stale_lock_ms=100,
        now_ms=1_500,
        core_runner=core_runner,
        runner=core_runner,
    )

    assert calls == ["ran"], "stale is_running must not become a permanent watcher lock"
    assert _value(result, "ran_core") is True
    assert _status(result) == "fresh"
    assert "watcher_running" not in _reasons(result)

    payload = json.loads(state.read_text())
    assert payload["running"] is False
    assert payload["is_running"] is False


def test_stale_watcher_recovery_success_drops_active_state_markers(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    state = fake_project["state"]
    queue = fake_project["queue"]
    watcher = _watcher_module()
    snapshot = watcher.collect_source_snapshot(root)
    calls: list[str] = []

    state.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": True,
                "is_running": True,
                "owner": "watcher",
                "run_id": "stale-watcher-run",
                "started_at": "1970-01-01T00:00:01Z",
                "started_at_epoch_ms": 1_000,
                "updated_at_epoch_ms": 1_000,
                "lock_file": _core_update_lock_path(root).as_posix(),
                "queue_count_at_start": 1,
                "current_snapshot": snapshot,
                "last_snapshot": snapshot,
                "lock": {
                    "owner": "watcher",
                    "run_id": "stale-watcher-run",
                    "updated_at_epoch_ms": 1_000,
                },
            }
        )
    )
    queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "queue": [
                    {
                        "relative_path": "docs/spec/main.md",
                        "path": "docs/spec/main.md",
                        "change_type": "modified",
                    }
                ],
            }
        )
    )

    def core_runner(**_: Any) -> dict[str, Any]:
        calls.append("ran")
        return {"freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []}}

    result = _run_once(
        root,
        stale_lock_ms=100,
        now_ms=1_500,
        core_runner=core_runner,
        runner=core_runner,
    )

    assert calls == ["ran"], "stale watcher state with a queue must recover by running core"
    assert _value(result, "ran_core") is True
    assert _queue_items(result, queue) == []
    assert _status(result) == "fresh"

    payload = json.loads(state.read_text())
    assert payload["running"] is False
    assert payload["is_running"] is False
    assert _active_marker_payload(payload) == {}


def test_stale_watcher_recovery_idle_removes_stale_core_update_lock(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    state = fake_project["state"]
    lock_path = _core_update_lock_path(root)
    watcher = _watcher_module()
    snapshot = watcher.collect_source_snapshot(root)

    state.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": True,
                "is_running": True,
                "owner": "watcher",
                "run_id": "stale-idle-watcher-run",
                "started_at_epoch_ms": 1_000,
                "updated_at_epoch_ms": 1_000,
                "last_snapshot": snapshot,
            }
        )
    )
    lock_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "lock_kind": "core_update",
                "owner": "watcher",
                "run_id": "stale-idle-watcher-run",
                "token": "stale-token",
                "acquired_at_epoch_ms": 1_000,
                "updated_at_epoch_ms": 1_000,
            }
        )
    )

    result = _run_once(root, stale_lock_ms=100, now_ms=1_500)

    assert _value(result, "ran_core") is False
    assert _queue_items(result, fake_project["queue"]) == []
    assert _status(result) in {"fresh", "idle"}
    assert not lock_path.exists(), "idle stale watcher recovery must clean up stale shared core-update locks"


def test_stale_watcher_recovery_clears_old_running_freshness_when_idle(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    state = fake_project["state"]
    freshness_path = root / ".spec-grag/context/freshness.json"
    watcher = _watcher_module()
    snapshot = watcher.collect_source_snapshot(root)

    freshness_path.parent.mkdir(parents=True, exist_ok=True)
    freshness_path.write_text(
        json.dumps(
            {
                "status": "blocked",
                "blocking_reasons": ["watcher_running"],
                "warnings": [],
            }
        )
    )
    state.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": True,
                "is_running": True,
                "owner": "watcher",
                "run_id": "stale-idle-watcher-run",
                "started_at_epoch_ms": 1_000,
                "updated_at_epoch_ms": 1_000,
                "last_snapshot": snapshot,
            }
        )
    )

    result = _run_once(root, stale_lock_ms=100, now_ms=1_500)

    assert _value(result, "ran_core") is False
    assert _queue_items(result, fake_project["queue"]) == []
    assert "watcher_running" not in _reasons(result)
    assert _status(result) in {"fresh", "idle"}

    freshness = json.loads(freshness_path.read_text())
    assert "watcher_running" not in freshness.get("blocking_reasons", [])
    assert freshness.get("status") in {"fresh", "idle"}


def test_cli_options_override_config_for_one_watch_run(
    fake_project: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = importlib.import_module("spec_grag.cli")
    watcher = _watcher_module()
    calls: list[dict[str, Any]] = []

    def fake_watch(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []}}

    monkeypatch.setattr(watcher, "run_spec_grag_watch", fake_watch, raising=False)
    monkeypatch.setattr(watcher, "run_watcher_once", fake_watch, raising=False)

    exit_code = cli.watch_main(
        [
            "--once",
            "--interval-sec",
            "1.25",
            "--debounce-sec",
            "0.3",
            "--stale-lock-sec",
            "60",
            "--max-runs",
            "3",
            str(fake_project["root"]),
        ]
    )

    assert exit_code == 0
    assert calls, "watch_main must dispatch to the watcher API"
    call = calls[0]
    assert Path(call.get("project_root") or call.get("root")) == fake_project["root"]
    assert call.get("once") is True
    assert call.get("max_runs") == 3
    assert call.get("interval_ms") == 1250 or call.get("interval_sec") == 1.25
    assert call.get("debounce_ms") == 300 or call.get("debounce_sec") == 0.3
    assert call.get("stale_lock_ms") == 60_000 or call.get("stale_lock_sec") == 60


def test_watcher_calls_internal_core_runner_not_slash_command(
    fake_project: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watcher = _watcher_module()
    core = importlib.import_module("spec_grag.core")
    calls: list[str] = []

    def internal_runner(**_: Any) -> dict[str, Any]:
        calls.append("internal")
        return {"freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []}}

    def slash_runner(**_: Any) -> None:
        raise AssertionError("watcher must not dispatch `/spec-core` as an external slash command")

    monkeypatch.setattr(core, "run_spec_core_for_watcher", internal_runner, raising=False)
    monkeypatch.setattr(core, "run_spec_core", slash_runner, raising=False)
    monkeypatch.setattr(watcher, "run_spec_core_for_watcher", internal_runner, raising=False)
    monkeypatch.setattr(watcher, "run_spec_core", slash_runner, raising=False)

    _run_once(fake_project["root"])

    assert calls == ["internal"]


def test_watcher_internal_core_runner_sees_watcher_running_freshness_artifact(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    freshness_path = root / ".spec-grag/context/freshness.json"
    observed: list[dict[str, Any]] = []

    def core_runner(**_: Any) -> dict[str, Any]:
        assert freshness_path.is_file(), (
            "watcher must publish a running freshness artifact before internal core starts"
        )
        payload = json.loads(freshness_path.read_text())
        observed.append(payload)
        return {"freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []}}

    result = _run_once(root, core_runner=core_runner, runner=core_runner)

    assert observed, "watcher must invoke the internal core runner"
    assert observed[0]["status"] == "blocked"
    assert "watcher_running" in observed[0]["blocking_reasons"]
    assert _status(result) == "fresh"


def test_watcher_heartbeat_keeps_long_internal_core_from_looking_stale(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    state = fake_project["state"]
    manual_results: list[Any] = []

    def core_runner(**kwargs: Any) -> dict[str, Any]:
        heartbeat = _heartbeat_callable(kwargs)
        _call_heartbeat(heartbeat, now_ms=1_000_500)

        assert _lock_updated_at(root) == 1_000_500
        assert _state_updated_at(state) == 1_000_500

        manual_result = _call_adaptive(
            importlib.import_module("spec_grag.core").run_spec_core,
            project_root=root,
            provider=None,
            llm_provider=None,
            stale_lock_ms=100,
            now_ms=1_000_550,
        )
        manual_results.append(manual_result)

        assert _value(manual_result, "status") == "blocked"
        assert _value(manual_result, "freshness_report", "status") == "blocked"
        assert "watcher_running" in _value(
            manual_result,
            "freshness_report",
            "blocking_reasons",
            default=[],
        )
        return {"freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []}}

    _run_once(
        root,
        core_runner=core_runner,
        runner=core_runner,
        stale_lock_ms=100,
        now_ms=1_000_000,
    )

    assert manual_results, "test must attempt manual `/spec-core` during the long watcher run"
    final_state = json.loads(state.read_text())
    assert final_state["last_heartbeat_at_epoch_ms"] == 1_000_500
    assert final_state["last_lock"]["updated_at_epoch_ms"] == 1_000_500
    assert final_state["last_lock_file"].endswith(".spec-grag/state/core_update.lock.json")


def test_t_r13_continuous_mode_processes_multiple_source_changes(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    source = fake_project["source"]
    watcher = _watcher_module()
    fake_project["state"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": False,
                "is_running": False,
                "last_snapshot": watcher.collect_source_snapshot(root),
            }
        )
    )
    source.write_text("# Main\n\n## Alpha\nFirst continuous update.\n")
    observed_texts: list[str] = []
    interval_sleeps = 0

    def runner(**kwargs: Any) -> dict[str, Any]:
        observed_texts.append(_snapshot_text(kwargs["source_snapshot"], root, source))
        return {
            "status": "updated",
            "retrieval_index_artifact_revision": f"rev-{len(observed_texts)}",
            "freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []},
        }

    def sleep(_: float) -> None:
        nonlocal interval_sleeps
        interval_sleeps += 1
        if interval_sleeps == 1:
            source.write_text("# Main\n\n## Alpha\nSecond continuous update.\n")

    result = watcher.run_spec_grag_watch(
        root,
        once=False,
        max_runs=2,
        interval_ms=0,
        debounce_ms=0,
        sleep=sleep,
        core_runner=runner,
    )

    assert result["run_count"] == 2
    assert len(observed_texts) == 2
    assert "First continuous update" in observed_texts[0]
    assert "Second continuous update" in observed_texts[1]
    assert json.loads(fake_project["queue"].read_text())["queue_count"] == 0


def test_t_r13_status_survives_restart_with_freshness_and_diagnostics(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    source = fake_project["source"]
    watcher = _watcher_module()
    fake_project["state"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": False,
                "is_running": False,
                "last_snapshot": watcher.collect_source_snapshot(root),
            }
        )
    )
    source.write_text("# Main\n\n## Alpha\nRestart-visible watcher update.\n")

    result = _run_once(
        root,
        core_runner=lambda **_: {
            "status": "updated",
            "retrieval_index_artifact_revision": "restart-rev-1",
            "freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []},
        },
    )
    assert result["freshness_report"]["status"] == "fresh"

    restarted_watcher = importlib.reload(watcher)
    status = restarted_watcher.get_watcher_status(root)

    assert status["freshness_report"]["status"] == "fresh"
    assert status["diagnostics"]["last_success_artifact_revision"] == "restart-rev-1"
    assert status["diagnostics"]["last_success_result"]["retrieval_index_artifact_revision"] == "restart-rev-1"
    assert status["queue_count"] == 0


def test_t_r13_failed_core_result_keeps_last_success_and_failure_reason(
    fake_project: dict[str, Path],
) -> None:
    root = fake_project["root"]
    source = fake_project["source"]
    watcher = _watcher_module()
    fake_project["state"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": False,
                "is_running": False,
                "last_snapshot": watcher.collect_source_snapshot(root),
            }
        )
    )
    source.write_text("# Main\n\n## Alpha\nSuccessful baseline update.\n")
    _run_once(
        root,
        core_runner=lambda **_: {
            "status": "updated",
            "retrieval_index_artifact_revision": "success-rev-1",
            "freshness_report": {"status": "fresh", "blocking_reasons": [], "warnings": []},
        },
    )

    source.write_text("# Main\n\n## Alpha\nFailing follow-up update.\n")
    result = _run_once(
        root,
        core_runner=lambda **_: {
            "status": "failed",
            "retrieval_index_artifact_revision": "failed-rev-2",
            "warnings": ["retrieval failed"],
            "freshness_report": {
                "status": "failed",
                "blocking_reasons": ["failed_required_artifact"],
                "warnings": ["retrieval failed"],
            },
        },
    )
    state = json.loads(fake_project["state"].read_text())

    assert result["status"] == "failed"
    assert result["queue_count"] == 1
    assert state["last_success_artifact_revision"] == "success-rev-1"
    assert state["last_failure_reason"]["type"] == "core_result_failed"
    assert state["last_failure_reason"]["blocking_reasons"] == ["failed_required_artifact"]
    assert json.loads(fake_project["queue"].read_text())["queue_count"] == 1


@pytest.mark.skipif(
    not _real_smoke_enabled(),
    reason=(
        "T-R09 real watcher operation requires SPEC_GRAG_REAL_SMOKE=1 "
        "and SPEC_GRAG_LOCAL_SERVICE=1"
    ),
)
def test_t_r09_real_watcher_reports_running_queue_lock_heartbeat_and_stale_recovery(
    tmp_path: Path,
) -> None:
    pytest.importorskip("FlagEmbedding")
    qdrant_client = pytest.importorskip("qdrant_client")

    watcher = _watcher_module()
    from spec_grag.core import run_spec_core, run_spec_core_for_watcher

    root = tmp_path / "real-watcher"
    collection = f"spec_grag_t_r09_{uuid.uuid4().hex}"
    qdrant_url = os.environ.get("SPEC_GRAG_QDRANT_URL", "http://localhost:6333")
    _write_real_watcher_project(root, collection=collection, qdrant_url=qdrant_url)
    state_path = root / ".spec-grag/state/watch_state.json"
    queue_path = root / ".spec-grag/state/watch_queue.json"
    lock_path = root / ".spec-grag/state/core_update.lock.json"
    freshness_path = root / ".spec-grag/context/freshness.json"
    source_path = root / "docs/spec/main.md"

    client = qdrant_client.QdrantClient(qdrant_url)
    try:
        initial = run_spec_core(root, all=True)
        assert initial["freshness_report"]["status"] == "fresh"
        initial_revision = json.loads(
            (root / ".spec-grag/context/retrieval_index_revision.json").read_text()
        )["artifact_revision"]
        initial_snapshot = watcher.collect_source_snapshot(root)
        state_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "running": False,
                    "is_running": False,
                    "last_snapshot": initial_snapshot,
                }
            )
        )

        source_path.write_text(
            source_path.read_text()
            + "\n## Real Watcher Update\nThe watcher must rebuild the real index.\n"
        )
        queue_observations: list[dict[str, Any]] = []
        running_observations: list[dict[str, Any]] = []
        lock_observations: list[dict[str, Any]] = []
        heartbeat_results: list[dict[str, Any]] = []

        def observe_debounce(_: float) -> None:
            queue_observations.append(json.loads(freshness_path.read_text()))

        def observing_core_runner(**kwargs: Any) -> dict[str, Any]:
            running_observations.append(json.loads(freshness_path.read_text()))
            status = watcher.get_watcher_status(root)
            lock_observations.append(status)
            heartbeat = kwargs["heartbeat"]
            heartbeat_results.append(dict(heartbeat(metadata={"test_stage": "t-r09"})))
            assert lock_path.is_file()
            return run_spec_core_for_watcher(**kwargs)

        result = watcher.run_spec_grag_watch(
            root,
            once=True,
            interval_ms=0,
            debounce_ms=1,
            sleep=observe_debounce,
            core_runner=observing_core_runner,
        )

        assert queue_observations
        assert queue_observations[0]["status"] == "blocked"
        assert "watcher_queue_pending" in queue_observations[0]["blocking_reasons"]
        assert running_observations
        assert running_observations[0]["status"] == "blocked"
        assert "watcher_running" in running_observations[0]["blocking_reasons"]
        assert lock_observations[0]["running"] is True
        assert lock_observations[0]["lock"]["owner"] == "watcher"
        assert heartbeat_results[0]["lock_updated"] is True
        assert result["freshness_report"]["status"] == "fresh"
        assert result["queue_count"] == 0
        assert json.loads(queue_path.read_text())["queue_count"] == 0
        assert not lock_path.exists()
        updated_revision = json.loads(
            (root / ".spec-grag/context/retrieval_index_revision.json").read_text()
        )
        source_update_diff = updated_revision["diagnostics"]["source_update_diff"]
        assert source_update_diff["old_revision"] == initial_revision
        assert source_update_diff["new_revision"] == updated_revision["artifact_revision"]
        assert _has_section_id(
            source_update_diff["changed_sections"],
            "docs/spec/main.md#real-watcher-update",
        )

        final_state = json.loads(state_path.read_text())
        assert final_state["last_lock"]["owner"] == "watcher"
        assert final_state["last_lock_file"].endswith(".spec-grag/state/core_update.lock.json")
        assert isinstance(final_state["last_heartbeat_at_epoch_ms"], int)
        assert isinstance(final_state["last_lock_updated_at_epoch_ms"], int)
        assert final_state["last_success_artifact_revision"] == updated_revision["artifact_revision"]
        assert final_state["last_success_result"]["source_update_diff"]["old_revision"] == initial_revision

        current_snapshot = watcher.collect_source_snapshot(root)
        state_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "running": True,
                    "is_running": True,
                    "owner": "watcher",
                    "run_id": "stale-real-watcher",
                    "started_at_epoch_ms": 1_000,
                    "updated_at_epoch_ms": 1_000,
                    "last_snapshot": current_snapshot,
                }
            )
        )
        lock_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "lock_kind": "core_update",
                    "owner": "watcher",
                    "run_id": "stale-real-watcher",
                    "token": "stale-real-token",
                    "acquired_at_epoch_ms": 1_000,
                    "updated_at_epoch_ms": 1_000,
                }
            )
        )

        stale_result = watcher.run_spec_grag_watch(
            root,
            once=True,
            interval_ms=0,
            debounce_ms=0,
            stale_lock_ms=100,
            now_ms=1_500,
        )

        assert stale_result["freshness_report"]["status"] == "fresh"
        assert stale_result["stale_lock_discarded"] is True
        assert stale_result["stale_locks"]
        assert stale_result["stale_locks"][0]["stale_age_ms"] >= 500
        assert not lock_path.exists()
        recovered_state = json.loads(state_path.read_text())
        assert recovered_state["stale_lock_discarded"] is True
        assert recovered_state["stale_locks"]
    finally:
        try:
            client.delete_collection(collection)
        except Exception:
            pass
