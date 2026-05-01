from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode

import spec_grag.watcher as watcher_module
from spec_grag.concept_diff import (
    ConceptDiffTaskContext,
    PendingConceptDiff,
    PendingConceptHunk,
    accept_hunk,
    apply_pending_concept_diff,
    concept_file_hash,
    create_pending_concept_diff,
    load_pending_concept_diff,
)
from spec_grag.concept_index import (
    build_concept_index,
    generate_concept_diff_candidate,
    generate_queued_concept_diff_candidate,
    write_concept_index_atomic,
)
from spec_grag.config import ExecutionRole
from spec_grag.core import GRAPH_STORE_FILENAME
from spec_grag.manifest import load_source_manifest
from spec_grag.protocol import Command, ResultEnvelope, ResultStatus, ResultType
from spec_grag.readiness import evaluate_grag_readiness
from spec_grag.watch_state import (
    WatchRunState,
    WatchState,
    enqueue_source_changes,
    load_watch_state,
    load_provisional_concept_cache,
    load_watch_queue,
    provisional_concept_cache_path,
    semantic_digest_for_manifest,
    update_provisional_concept_cache,
    watch_queue_path,
    watch_state_path,
    write_watch_state_atomic,
)
from spec_grag.watcher import (
    capture_source_snapshot,
    run_watch_once,
    watcher_settings_from_config,
)


def write_config(project_root: Path, *, runtime_mode: str | None = None) -> None:
    config_dir = project_root / ".spec-grag"
    config_dir.mkdir(parents=True, exist_ok=True)
    runtime = (
        f'\n\n[runtime]\nmode = "{runtime_mode}"\n'
        if runtime_mode is not None
        else ""
    )
    (config_dir / "config.toml").write_text(
        (
            """
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[graph]
storage = ".spec-grag/graph/"

[embedding]
provider = "stable_hash"
model = "sha256-v1"
dimension = 8
""".strip()
            + runtime
        ),
        encoding="utf-8",
    )


def disable_concept_file(project_root: Path) -> None:
    config_path = project_root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            'concept_file = "docs/core/concept.md"\n',
            "",
        ),
        encoding="utf-8",
    )


def write_production_config(project_root: Path, *, runtime_mode: str = "production") -> None:
    config_dir = project_root / ".spec-grag"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        f"""
[sources]
include = ["docs/spec/**/*.md"]

[llm]
provider = "codex_cli"

[llm.codex_cli]
command = "codex"
model = "gpt-5.4"
effort = "low"

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"
extraction_mode = "schema_llm"

[extraction]
mode = "schema_llm"

[answer]
failure_fallback = "failed"

[classification]
fallback_on_error = false

[concept_diff]
fallback_on_error = false

[community_report]
fallback_on_error = false

[query_planner]
fallback_on_error = false

[embedding]
provider = "ollama"
model = "bge-m3"
dimension = 1024

[runtime]
mode = "{runtime_mode}"
""".strip(),
        encoding="utf-8",
    )


def write_docs(project_root: Path, *, auth_text: str = "OAuth is required.") -> None:
    spec = project_root / "docs/spec/auth.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(f"# Auth\n\n## Login\n\n{auth_text}\n", encoding="utf-8")
    core = project_root / "docs/core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "purpose.md").write_text("# Purpose\nKeep users secure.\n", encoding="utf-8")
    (core / "concept.md").write_text("# Concept\nAuth protects sessions.\n", encoding="utf-8")


def request_payload(project_root: Path, command: str) -> dict:
    return {
        "command": command,
        "project_root": str(project_root),
        "task_prompt": "Auth Login を見直す" if command == "spec-realign" else None,
        "conversation_context": {
            "current_user_message": "Auth Login を見直す",
            "recent_messages": [],
            "working_target": "docs/spec/auth.md",
            "explicit_files": ["docs/spec/auth.md"],
        },
        "agentic_search_candidates": [],
        "agent_capabilities": {
            "can_read_source": True,
            "can_answer": command == "spec-realign",
        },
        "options": {"output_format": "json"},
    }


def run_cli(payload: dict, *, smoke: bool = True) -> tuple[int, ResultEnvelope]:
    env = os.environ.copy()
    if smoke:
        env["SPEC_GRAG_SMOKE"] = "1"
    else:
        env.pop("SPEC_GRAG_SMOKE", None)
        env.pop("SPEC_GRAG_RUNTIME_MODE", None)
    result = subprocess.run(
        [sys.executable, "-m", "spec_grag.cli"],
        input=json.dumps(payload),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode, ResultEnvelope.from_json(result.stdout)


def run_core_cli(project_root: Path, *, all_sources: bool = False) -> ResultEnvelope:
    payload = request_payload(project_root, "spec-core")
    payload["options"]["all"] = all_sources
    code, envelope = run_cli(payload)
    assert code == 0
    return envelope


def test_local_daily_dirty_inject_does_not_run_foreground_core(tmp_path: Path) -> None:
    write_config(tmp_path, runtime_mode="local_daily")
    write_docs(tmp_path)
    run_core_cli(tmp_path, all_sources=True)
    manifest_before = load_source_manifest(tmp_path / ".spec-grag/graph/source_manifest.json")

    write_docs(tmp_path, auth_text="OAuth is required and audited.")
    code, envelope = run_cli(request_payload(tmp_path, "spec-inject"))
    manifest_after = load_source_manifest(tmp_path / ".spec-grag/graph/source_manifest.json")

    assert code == 0
    assert envelope.status == ResultStatus.BLOCKED
    assert envelope.result_type == ResultType.ERROR_RESULT
    assert envelope.payload.error_code == "watcher_waiting_for_dirty_grag"
    assert manifest_after == manifest_before


def test_local_daily_inject_blocks_while_watcher_is_running(tmp_path: Path) -> None:
    write_config(tmp_path, runtime_mode="local_daily")
    write_docs(tmp_path)
    run_core_cli(tmp_path, all_sources=True)
    write_watch_state_atomic(
        watch_state_path(tmp_path),
        WatchState(run_state=WatchRunState.RUNNING, last_run_id="watch-running"),
    )

    code, envelope = run_cli(request_payload(tmp_path, "spec-inject"))

    assert code == 0
    assert envelope.status == ResultStatus.BLOCKED
    assert envelope.payload.error_code == "watcher_processing"
    assert any(
        reason["code"] == "watcher_running"
        for reason in envelope.payload.details["reasons"]
    )


def test_local_daily_inject_blocks_when_watch_queue_has_changes(tmp_path: Path) -> None:
    write_config(tmp_path, runtime_mode="local_daily")
    write_docs(tmp_path)
    run_core_cli(tmp_path, all_sources=True)
    enqueue_source_changes(
        tmp_path,
        source_section_ids=["docs/spec/auth.md#auth-login"],
        semantic_hashes={"docs/spec/auth.md#auth-login": "semantic-next"},
        reason="running_change",
        detected_at="2026-05-01T00:00:00+00:00",
    )

    code, envelope = run_cli(request_payload(tmp_path, "spec-inject"))

    assert code == 0
    assert envelope.status == ResultStatus.BLOCKED
    assert envelope.payload.error_code == "watcher_queue_pending"
    assert envelope.payload.details["queued_section_ids"] == [
        "docs/spec/auth.md#auth-login"
    ]


def test_ci_mode_allows_foreground_incremental_without_watcher(tmp_path: Path) -> None:
    write_config(tmp_path, runtime_mode="ci")
    write_docs(tmp_path)

    code, envelope = run_cli(request_payload(tmp_path, "spec-inject"))

    assert code == 0
    assert envelope.status == ResultStatus.OK
    assert envelope.result_type == ResultType.INJECTION_CONTEXT
    assert (tmp_path / ".spec-grag/graph/source_manifest.json").exists()
    report = envelope.payload.freshness_report.readiness_report
    assert report is not None
    assert report["runtime_policy"]["mode"] == "ci"


def test_production_pending_fails_fast(tmp_path: Path) -> None:
    write_production_config(tmp_path)
    write_docs(tmp_path)
    concept_file = tmp_path / "docs/core/concept.md"
    diff = make_pending_diff(concept_file)
    create_pending_concept_diff(tmp_path / ".spec-grag/pending", diff)

    code, envelope = run_cli(request_payload(tmp_path, "spec-inject"), smoke=False)

    assert code == 1
    assert envelope.status == ResultStatus.FAILED
    assert envelope.result_type == ResultType.ERROR_RESULT
    assert envelope.payload.error_code == "readiness_pending"


def test_production_watcher_running_fails_fast(tmp_path: Path) -> None:
    write_production_config(tmp_path)
    write_docs(tmp_path)
    write_watch_state_atomic(
        watch_state_path(tmp_path),
        WatchState(run_state=WatchRunState.RUNNING, last_run_id="watch-running"),
    )

    code, envelope = run_cli(request_payload(tmp_path, "spec-inject"), smoke=False)

    assert code == 1
    assert envelope.status == ResultStatus.FAILED
    assert envelope.payload.error_code in {"readiness_dirty", "readiness_stale"}
    assert any(
        reason["code"] == "watcher_running"
        for reason in envelope.payload.details["reasons"]
    )


def test_production_watch_queue_fails_fast(tmp_path: Path) -> None:
    write_production_config(tmp_path)
    write_docs(tmp_path)
    enqueue_source_changes(
        tmp_path,
        source_section_ids=["docs/spec/auth.md#auth-login"],
        semantic_hashes={"docs/spec/auth.md#auth-login": "semantic-next"},
        reason="running_change",
        detected_at="2026-05-01T00:00:00+00:00",
    )

    code, envelope = run_cli(request_payload(tmp_path, "spec-inject"), smoke=False)

    assert code == 1
    assert envelope.status == ResultStatus.FAILED
    assert envelope.payload.error_code in {"readiness_dirty", "readiness_stale"}
    assert any(
        reason["code"] == "watch_queue_pending"
        for reason in envelope.payload.details["reasons"]
    )


def test_pending_concept_diff_queues_changed_sections_without_second_diff(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    graph_dir = tmp_path / ".spec-grag/graph"
    graph_dir.mkdir(parents=True)
    concept_file = tmp_path / "docs/core/concept.md"
    concept_index = build_concept_index(
        tmp_path,
        concept_file,
        embedding_config={"provider": "stable_hash", "dimension": 8},
    )
    existing = make_pending_diff(concept_file)
    create_pending_concept_diff(tmp_path / ".spec-grag/pending", existing)

    result = generate_concept_diff_candidate(
        project_root=tmp_path,
        config={
            "core": {"concept_file": "docs/core/concept.md"},
            "concept_diff": {"provider": "source_derived"},
            "embedding": {"provider": "stable_hash", "dimension": 8},
        },
        graph_storage=graph_dir,
        graph_data=fake_graph_data("docs/spec/auth.md#auth-login", "Session Boundary"),
        concept_index=concept_index,
        changed_source_section_ids=["docs/spec/auth.md#auth-login"],
        changed_source_section_hashes={"docs/spec/auth.md#auth-login": "semantic-1"},
        extract_run_id="run-1",
        generated_at="2026-05-01T00:00:00+00:00",
    )

    pending_files = sorted((tmp_path / ".spec-grag/pending").glob("concept_diff_*.json"))
    queue = load_watch_queue(watch_queue_path(tmp_path))
    cache = load_provisional_concept_cache(provisional_concept_cache_path(tmp_path))

    assert result.pending_diff is None
    assert [path.name for path in pending_files] == ["concept_diff_diff-1.json"]
    assert [change.source_section_id for change in queue.changes] == [
        "docs/spec/auth.md#auth-login"
    ]
    assert any(candidate.label == "Session Boundary" for candidate in cache.candidates)


def test_queued_concept_change_is_reevaluated_after_pending_apply(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    graph_dir = tmp_path / ".spec-grag/graph"
    graph_dir.mkdir(parents=True)
    concept_file = tmp_path / "docs/core/concept.md"
    index = build_concept_index(
        tmp_path,
        concept_file,
        embedding_config={"provider": "stable_hash", "dimension": 8},
    )
    write_concept_index_atomic(graph_dir / "concept_index.json", index)
    write_fake_graph_store(graph_dir, "docs/spec/auth.md#auth-login", "Session Boundary")
    pending_path = create_pending_concept_diff(
        tmp_path / ".spec-grag/pending",
        make_pending_diff(concept_file),
    )
    generate_concept_diff_candidate(
        project_root=tmp_path,
        config={
            "core": {"concept_file": "docs/core/concept.md"},
            "concept_diff": {"provider": "source_derived"},
            "embedding": {"provider": "stable_hash", "dimension": 8},
        },
        graph_storage=graph_dir,
        graph_data=fake_graph_data("docs/spec/auth.md#auth-login", "Session Boundary"),
        concept_index=index,
        changed_source_section_ids=["docs/spec/auth.md#auth-login"],
        changed_source_section_hashes={"docs/spec/auth.md#auth-login": "semantic-1"},
        extract_run_id="run-1",
        generated_at="2026-05-01T00:00:00+00:00",
    )
    accepted = accept_hunk(load_pending_concept_diff(pending_path), "hunk-1")
    apply_pending_concept_diff(
        accepted,
        concept_file,
        remove_pending_path=pending_path,
    )

    queued = generate_queued_concept_diff_candidate(
        project_root=tmp_path,
        config={
            "core": {"concept_file": "docs/core/concept.md"},
            "concept_diff": {"provider": "source_derived"},
            "embedding": {"provider": "stable_hash", "dimension": 8},
        },
        graph_storage=graph_dir,
        extract_run_id="queued-run",
        generated_at="2026-05-01T00:01:00+00:00",
    )

    assert queued.pending_diff is not None
    assert queued.pending_diff.diff_id != "diff-1"
    assert load_watch_queue(watch_queue_path(tmp_path)).changes == []


def test_provisional_cache_is_not_mixed_into_injection_context(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    run_core_cli(tmp_path, all_sources=True)
    update_provisional_concept_cache(
        tmp_path,
        terms=[
            {
                "term": "UnapprovedMagic",
                "source_section_id": "docs/spec/auth.md#auth-login",
            }
        ],
        seen_at="2026-05-01T00:00:00+00:00",
    )

    code, envelope = run_cli(request_payload(tmp_path, "spec-inject"))

    assert code == 0
    assert envelope.status == ResultStatus.OK
    assert "UnapprovedMagic" not in envelope.payload.model_dump_json()


def test_approval_apply_clears_provisional_concept_cache(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    concept_file = tmp_path / "docs/core/concept.md"
    create_pending_concept_diff(
        tmp_path / ".spec-grag/pending",
        make_pending_diff(concept_file),
    )
    update_provisional_concept_cache(
        tmp_path,
        terms=[
            {
                "term": "UnapprovedMagic",
                "source_section_id": "docs/spec/auth.md#auth-login",
            }
        ],
        seen_at="2026-05-01T00:00:00+00:00",
    )
    payload = request_payload(tmp_path, "spec-core")
    payload["options"]["accept"] = "diff-1:hunk-1"
    code, accepted = run_cli(payload)
    assert code == 0
    assert accepted.status == ResultStatus.OK

    payload["options"] = {"output_format": "json", "apply": "diff-1"}
    code, applied = run_cli(payload)

    assert code == 0
    assert applied.status == ResultStatus.OK
    cache = load_provisional_concept_cache(provisional_concept_cache_path(tmp_path))
    assert cache.candidates == []


def test_nonapproval_keeps_provisional_concept_cache(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    concept_file = tmp_path / "docs/core/concept.md"
    create_pending_concept_diff(
        tmp_path / ".spec-grag/pending",
        make_pending_diff(concept_file),
    )
    update_provisional_concept_cache(
        tmp_path,
        terms=[
            {
                "term": "UnapprovedMagic",
                "source_section_id": "docs/spec/auth.md#auth-login",
            }
        ],
        seen_at="2026-05-01T00:00:00+00:00",
    )
    payload = request_payload(tmp_path, "spec-core")
    payload["options"]["reject"] = "diff-1:hunk-1"
    code, rejected = run_cli(payload)
    assert code == 0
    assert rejected.status == ResultStatus.OK

    payload["options"] = {"output_format": "json", "apply": "diff-1"}
    code, blocked = run_cli(payload)

    assert code == 0
    assert blocked.status == ResultStatus.BLOCKED
    cache = load_provisional_concept_cache(provisional_concept_cache_path(tmp_path))
    assert [candidate.label for candidate in cache.candidates] == ["UnapprovedMagic"]


def test_background_watcher_queues_pending_changes_without_approval_prompt(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    write_docs(tmp_path)
    run_core_cli(tmp_path, all_sources=True)
    concept_file = tmp_path / "docs/core/concept.md"
    create_pending_concept_diff(
        tmp_path / ".spec-grag/pending",
        make_pending_diff(concept_file),
    )
    write_docs(tmp_path, auth_text="OAuth is required and audited.")

    code = run_watch_once(tmp_path, load_smoke_config(tmp_path), debounce_sec=0)
    queue = load_watch_queue(watch_queue_path(tmp_path))

    assert code == 0
    assert [path.name for path in (tmp_path / ".spec-grag/pending").glob("concept_diff_*.json")] == [
        "concept_diff_diff-1.json"
    ]
    assert [change.source_section_id for change in queue.changes] == [
        "docs/spec/auth.md#auth-login"
    ]


def test_watcher_config_custom_paths_and_timing_are_used(tmp_path: Path) -> None:
    write_config(tmp_path)
    disable_concept_file(tmp_path)
    config_path = tmp_path / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + """

[watcher]
enabled = true
interval_ms = 50
debounce_ms = 0
stale_lock_ms = 1000
state_file = ".custom-grag/watch_state.json"
queue_file = ".custom-grag/watch_queue.json"
""",
        encoding="utf-8",
    )
    write_docs(tmp_path)
    config = load_smoke_config(tmp_path)

    settings = watcher_settings_from_config(config)
    assert settings.enabled is True
    assert settings.interval_sec == 0.05
    assert settings.debounce_sec == 0.0
    assert settings.stale_lock_sec == 1

    code = run_watch_once(tmp_path, config)
    enqueue_source_changes(
        tmp_path,
        config=config,
        source_section_ids=["docs/spec/auth.md#auth-login"],
        semantic_hashes={"docs/spec/auth.md#auth-login": "semantic-custom"},
        reason="running_change",
        detected_at="2026-05-01T00:00:00+00:00",
    )
    readiness = evaluate_grag_readiness(tmp_path, config)

    assert code == 0
    assert load_watch_state(tmp_path / ".custom-grag/watch_state.json").run_state == "idle"
    assert not watch_state_path(tmp_path).exists()
    assert readiness.watch_state_path.endswith(".custom-grag/watch_state.json")
    assert readiness.watch_queue_path.endswith(".custom-grag/watch_queue.json")
    assert readiness.queued_section_ids == ["docs/spec/auth.md#auth-login"]


def test_watcher_config_enabled_false_skips_run(tmp_path: Path) -> None:
    write_config(tmp_path)
    disable_concept_file(tmp_path)
    config_path = tmp_path / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + """

[watcher]
enabled = false
""",
        encoding="utf-8",
    )
    write_docs(tmp_path)
    config = load_smoke_config(tmp_path)

    code = run_watch_once(tmp_path, config)

    assert code == 0
    assert not watch_state_path(tmp_path).exists()
    assert watcher_settings_from_config(config).enabled is False


def test_watcher_queues_change_that_arrives_during_run_and_drains_next_cycle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    write_config(tmp_path)
    disable_concept_file(tmp_path)
    write_docs(tmp_path)
    config = load_smoke_config(tmp_path)
    run_core_cli(tmp_path, all_sources=True)

    write_docs(tmp_path, auth_text="OAuth is required and audited.")
    snapshot_a = capture_source_snapshot(tmp_path, config)
    original_run_core_update = watcher_module.run_core_update
    changed_during_run = False

    def run_core_update_with_concurrent_change(*args, **kwargs):
        nonlocal changed_during_run
        if not changed_during_run:
            changed_during_run = True
            write_docs(
                tmp_path,
                auth_text="OAuth is required, audited, and rotated.",
            )
            time.sleep(0.25)
        return original_run_core_update(*args, **kwargs)

    monkeypatch.setattr(
        watcher_module,
        "run_core_update",
        run_core_update_with_concurrent_change,
    )

    code = run_watch_once(tmp_path, config, debounce_sec=0.05)
    manifest_after_a = load_source_manifest(
        tmp_path / ".spec-grag/graph/source_manifest.json"
    )
    queue_after_a = load_watch_queue(watch_queue_path(tmp_path))

    assert code == 0
    assert changed_during_run
    assert semantic_digest_for_manifest(manifest_after_a) == snapshot_a.semantic_hash
    assert [change.source_section_id for change in queue_after_a.changes] == [
        "docs/spec/auth.md#auth-login"
    ]
    assert queue_after_a.changes[0].reason in {"running_change", "post_run_change"}

    monkeypatch.setattr(watcher_module, "run_core_update", original_run_core_update)
    code = run_watch_once(tmp_path, config, debounce_sec=0)
    manifest_after_b = load_source_manifest(
        tmp_path / ".spec-grag/graph/source_manifest.json"
    )
    queue_after_b = load_watch_queue(watch_queue_path(tmp_path))
    snapshot_b = capture_source_snapshot(tmp_path, config)

    assert code == 0
    assert semantic_digest_for_manifest(manifest_after_b) == snapshot_b.semantic_hash
    assert queue_after_b.changes == []


def make_pending_diff(concept_file: Path) -> PendingConceptDiff:
    return PendingConceptDiff(
        diff_id="diff-1",
        base_concept_hash=concept_file_hash(concept_file),
        task_context=ConceptDiffTaskContext(
            command=Command.SPEC_CORE,
            changed_source_section_ids=["docs/spec/auth.md#auth-login"],
            extract_run_id="run-0",
        ),
        hunks=[
            PendingConceptHunk(
                hunk_id="hunk-1",
                file="docs/core/concept.md",
                old_range="-1,2",
                new_range="+1,2",
                diff_text=(
                    "@@ -1,2 +1,2 @@\n"
                    " # Concept\n"
                    "-Auth protects sessions.\n"
                    "+Auth protects all sessions.\n"
                ),
            )
        ],
    )


def fake_graph_data(section_id: str, label: str) -> dict:
    return {
        "nodes": {
            f"anchor:{section_id}:session-boundary": {
                "label": "ANCHOR",
                "name": label,
                "properties": {
                    "extractor_name": "SchemaLLMPathExtractor",
                    "source_section_id": section_id,
                    "display_name": label,
                    "evidence_excerpt": label,
                    "source_span": "1-1",
                },
            }
        }
    }


def write_fake_graph_store(graph_dir: Path, section_id: str, label: str) -> None:
    store = SimplePropertyGraphStore()
    store.upsert_nodes(
        [
            EntityNode(
                label="ANCHOR",
                name=f"anchor:{section_id}:session-boundary",
                properties={
                    "extractor_name": "SchemaLLMPathExtractor",
                    "source_section_id": section_id,
                    "display_name": label,
                    "evidence_excerpt": label,
                    "source_span": "1-1",
                },
            )
        ]
    )
    store.persist(str(graph_dir / GRAPH_STORE_FILENAME))


def load_smoke_config(project_root: Path) -> dict:
    import tomllib

    from spec_grag.config import validate_project_config

    with (project_root / ".spec-grag/config.toml").open("rb") as f:
        return validate_project_config(tomllib.load(f), smoke=True)
