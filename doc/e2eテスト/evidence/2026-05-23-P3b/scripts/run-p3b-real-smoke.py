#!/home/kazuki/public_html/spec-anchor/.venv/bin/python
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_ID = "2026-05-23-P3b"
COLLECTION = "spec_anchor_section_p3b_20260523"
TMP_ROOT = Path("/tmp/spec-anchor-e2e-2026-05-23-P3b")


def find_repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "pyproject.toml").is_file() and (path / "spec_anchor").is_dir():
            return path
    raise RuntimeError("repo root not found")


SCRIPT_PATH = Path(__file__).resolve()
EVIDENCE_DIR = SCRIPT_PATH.parents[1]
REPO_ROOT = find_repo_root(SCRIPT_PATH)
ARTIFACTS = EVIDENCE_DIR / "artifacts"
STDOUT = EVIDENCE_DIR / "stdout"
STDERR = EVIDENCE_DIR / "stderr"
COMMANDS_LOG = EVIDENCE_DIR / "commands.log"
EVIDENCE_MAP = EVIDENCE_DIR / "evidence_map.jsonl"
SPEC_ANCHOR = REPO_ROOT / ".venv" / "bin" / "spec-anchor"
SETUP_PROJECT = REPO_ROOT / ".venv" / "bin" / "spec-anchor-setup-project"
SETUP_SYSTEM = REPO_ROOT / ".venv" / "bin" / "spec-anchor-setup-system"
PROVIDER_BIN = TMP_ROOT / "provider-bin"
PROVIDER_LOGS = ARTIFACTS / "provider-logs"


SOURCE_RUNTIME = """# Runtime Source Spec

## Product Catalog Runtime

The product catalog keeps product identifiers stable across search and checkout.
Catalog updates preserve the `ProductStore` identifier and the
`productStoreGroup.replace` migration hook.

## Session Runtime Contract

Authenticated sessions use bearer token renewal. The session guard reports
missing or stale `AUTH_TOKEN` values, and the operator recovers by running
`spec-anchor core --rebuild` after fixing the source state.

## Checkout Integration

Checkout consumes validated catalog entries. Retrieval aids support navigation;
Source Specs, Purpose, Core Concept, and resolved Conflict Review Items remain
the constraint evidence.
"""

SOURCE_OPERATIONS = """# Operations Source Spec

## Maintenance Workflow

Operators run `spec-anchor core` incrementally after Source Specs change. Full
refreshes use `spec-anchor core --all`; collection rebuilds use
`spec-anchor core --rebuild`.

## Agent Output Boundary

Agent-facing output summarizes constraints, targets, related sections,
discarded paths, and uncertainty. Raw internal JSON is saved as evidence, not
pasted to users unless explicitly requested.
"""

PURPOSE = """# Purpose

Keep implementation work grounded in Source Specs while preserving a short,
auditable context path for Agents.
"""

CONCEPT = """# Core Concept

SPEC-anchor treats Purpose, Core Concept, Source Specs, and resolved Conflict
Review Items as evidence. Section Metadata, Search Keys, Related Sections, and
Chapter Key Anchors are retrieval aids for navigation and triage.

The normal chain is `/spec-core` first, then `/spec-inject`, then
`/spec-realign`. Fake providers are only for tests and smoke checks.
"""


def ensure_dirs() -> None:
    for path in (ARTIFACTS, STDOUT, STDERR):
        path.mkdir(parents=True, exist_ok=True)
    COMMANDS_LOG.write_text("", encoding="utf-8")
    EVIDENCE_MAP.write_text("", encoding="utf-8")
    (ARTIFACTS / "provider-invocations.jsonl").write_text("", encoding="utf-8")


def create_provider_wrappers() -> None:
    PROVIDER_BIN.mkdir(parents=True, exist_ok=True)
    PROVIDER_LOGS.mkdir(parents=True, exist_ok=True)
    real_codex = shutil.which("codex")
    real_claude = shutil.which("claude")
    if not real_codex or not real_claude:
        raise AssertionError(f"codex/claude not found: codex={real_codex}, claude={real_claude}")
    wrapper = f"""#!/usr/bin/env bash
set -u
name="$(basename "$0")"
case "$name" in
  codex) real={real_codex!r} ;;
  claude) real={real_claude!r} ;;
  *) echo "unknown wrapper: $name" >&2; exit 127 ;;
esac
logdir={str(PROVIDER_LOGS)!r}
mkdir -p "$logdir"
base="$logdir/${{name}}-$(date +%Y%m%dT%H%M%S)-$$"
printf '%s\\n' "$real $*" > "${{base}}.command.txt"
cat > "${{base}}.stdin"
"$real" "$@" < "${{base}}.stdin" > "${{base}}.stdout" 2> "${{base}}.stderr"
rc=$?
printf '%s\\n' "$rc" > "${{base}}.exitcode"
cat "${{base}}.stdout"
cat "${{base}}.stderr" >&2
exit "$rc"
"""
    for name in ("codex", "claude"):
        path = PROVIDER_BIN / name
        path.write_text(wrapper, encoding="utf-8")
        path.chmod(0o755)


def env_real() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{PROVIDER_BIN}:{REPO_ROOT / '.venv' / 'bin'}:{env.get('PATH', '')}"
    env.pop("SPEC_ANCHOR_FAKE_LLM", None)
    env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    env["SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION"] = "1"
    env["SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION_PATH"] = str(
        ARTIFACTS / "provider-invocations.jsonl"
    )
    return env


def run(
    name: str,
    args: list[str | Path],
    *,
    cwd: Path | None = None,
    timeout: int = 900,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = env_real()
    if extra_env:
        for key, value in extra_env.items():
            if value == "":
                env.pop(key, None)
            else:
                env[key] = value
    cmd = [str(arg) for arg in args]
    started = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    duration = time.monotonic() - started
    (STDOUT / f"{name}.stdout").write_text(proc.stdout, encoding="utf-8")
    (STDERR / f"{name}.stderr").write_text(proc.stderr, encoding="utf-8")
    (STDOUT / f"{name}.exitcode").write_text(str(proc.returncode), encoding="utf-8")
    with COMMANDS_LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "name": name,
                    "cwd": str(cwd or REPO_ROOT),
                    "command": cmd,
                    "returncode": proc.returncode,
                    "duration_sec": round(duration, 3),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return proc


def parse_stdout_json(name: str) -> dict[str, Any]:
    text = (STDOUT / f"{name}.stdout").read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{name}: stdout is not JSON: {text[:500]!r}") from exc


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def seed_project(project: Path) -> None:
    shutil.rmtree(project, ignore_errors=True)
    project.mkdir(parents=True, exist_ok=True)
    setup = run("setup-project", [SETUP_PROJECT, "--target", project, "--agent", "both"])
    if setup.returncode != 0:
        raise AssertionError(f"setup-project failed: {setup.stdout} {setup.stderr}")

    (project / "docs/spec").mkdir(parents=True, exist_ok=True)
    (project / "docs/core").mkdir(parents=True, exist_ok=True)
    (project / "docs/spec/runtime.md").write_text(SOURCE_RUNTIME, encoding="utf-8")
    (project / "docs/spec/operations.md").write_text(SOURCE_OPERATIONS, encoding="utf-8")
    (project / "docs/core/purpose.md").write_text(PURPOSE, encoding="utf-8")
    (project / "docs/core/concept.md").write_text(CONCEPT, encoding="utf-8")

    config_path = project / ".spec-anchor/config.toml"
    text = config_path.read_text(encoding="utf-8")
    text = re.sub(
        r'^section_collection\s*=\s*".*"$',
        f'section_collection = "{COLLECTION}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^llm_batch_concurrency\s*=\s*\d+.*$",
        "llm_batch_concurrency = 1",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r'^chapter_key_anchor\s*=\s*"[^"]+"$',
        'chapter_key_anchor = "claude_typing"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    config_path.write_text(text, encoding="utf-8")
    shutil.copy2(config_path, ARTIFACTS / "config.toml")
    (ARTIFACTS / "project-path.txt").write_text(str(project) + "\n", encoding="utf-8")


def artifact_hashes(project: Path) -> dict[str, str]:
    paths = [
        ".spec-anchor/context/section_manifest.json",
        ".spec-anchor/context/section_metadata.json",
        ".spec-anchor/context/related_sections.json",
        ".spec-anchor/context/chapter_anchors.json",
        ".spec-anchor/context/conflict_review_items.json",
        ".spec-anchor/state/retrieval_index_state.json",
        ".spec-anchor/state/related_sections_state.json",
    ]
    hashes: dict[str, str] = {}
    for rel in paths:
        path = project / rel
        if path.is_file():
            hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def read_progress(project: Path) -> dict[str, Any]:
    return json.loads((project / ".spec-anchor/state/core_progress.json").read_text(encoding="utf-8"))


def assert_no_fake_env() -> None:
    if os.environ.get("SPEC_ANCHOR_FAKE_LLM") or os.environ.get("SPEC_ANCHOR_FAKE_RETRIEVAL"):
        raise AssertionError("fake env vars are set in parent process")


def provider_invocation_summary() -> dict[str, Any]:
    path = ARTIFACTS / "provider-invocations.jsonl"
    commands: list[list[str]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                commands.append(json.loads(line)["command"])
    provider_names = sorted({Path(cmd[0]).name for cmd in commands if cmd})
    flattened = "\n".join(" ".join(cmd) for cmd in commands)
    return {
        "count": len(commands),
        "provider_names": provider_names,
        "contains_codex": "codex" in provider_names,
        "contains_claude": "claude" in provider_names,
        "contains_fake_or_stub": any(
            token in flattened.lower()
            for token in ("fake", "stub", "in-memory", "in_memory", "true ")
        ),
    }


def progress_provider_summary(progress: dict[str, Any]) -> dict[str, Any]:
    providers: dict[str, list[str]] = {}
    models: dict[str, list[str]] = {}
    for stage, payload in (progress.get("stages") or {}).items():
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if not isinstance(usage, dict):
            continue
        providers[str(stage)] = [str(value) for value in usage.get("providers_seen") or []]
        models[str(stage)] = [str(value) for value in usage.get("models_seen") or []]
    flattened = json.dumps({"providers": providers, "models": models}, ensure_ascii=False).lower()
    return {
        "providers_by_stage": providers,
        "models_by_stage": models,
        "contains_codex": any("codex" in values for values in providers.values()),
        "contains_claude": any("claude" in values for values in providers.values()),
        "contains_fake_or_stub": any(
            token in flattened
            for token in ("fake", "stub", "in-memory", "in_memory")
        ),
    }


def assert_core_success(name: str, result: dict[str, Any], *, mode: str) -> None:
    freshness = result.get("freshness_report") or {}
    diagnostics = result.get("diagnostics") or {}
    related = diagnostics.get("related_sections") if isinstance(diagnostics, dict) else {}
    if result.get("status") != "updated":
        raise AssertionError(f"{name}: status expected updated, got {result.get('status')!r}")
    if result.get("mode") != mode:
        raise AssertionError(f"{name}: mode expected {mode!r}, got {result.get('mode')!r}")
    if freshness.get("status") != "fresh":
        raise AssertionError(f"{name}: freshness_report.status expected fresh, got {freshness.get('status')!r}")
    if result.get("retrieval_index_status") != "success":
        raise AssertionError(f"{name}: retrieval_index_status expected success, got {result.get('retrieval_index_status')!r}")
    if result.get("related_sections_status") != "success":
        raise AssertionError(f"{name}: related_sections_status expected success, got {result.get('related_sections_status')!r}")
    if isinstance(related, dict) and related.get("qdrant_backend_failure") is not None:
        raise AssertionError(f"{name}: related_sections.qdrant_backend_failure must be null")


def write_evidence_row(
    *,
    scenario: str,
    line: int,
    checkbox_text: str,
    verification_level: str,
    result: str,
    duration_sec: float,
    evidence: list[str],
) -> None:
    row = {
        "spec_section": "P3b",
        "spec_line": line,
        "checkbox_text": checkbox_text,
        "test_id": f"manual:{RUN_ID}:{scenario}",
        "profile": "real-smoke",
        "method": "manual subprocess scenario",
        "verification_level": verification_level,
        "result": result,
        "duration_sec": round(duration_sec, 3),
        "executed_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "evidence": evidence,
    }
    with EVIDENCE_MAP.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def copy_artifact(project: Path, rel: str, name: str) -> None:
    source = project / rel
    if source.is_file():
        shutil.copy2(source, ARTIFACTS / name)


def main() -> int:
    ensure_dirs()
    create_provider_wrappers()
    assert_no_fake_env()
    shutil.rmtree(TMP_ROOT, ignore_errors=True)
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    create_provider_wrappers()

    setup_system = run("setup-system-check-only", [SETUP_SYSTEM, "--check-only"])
    setup_payload = parse_stdout_json("setup-system-check-only")
    write_json(ARTIFACTS / "setup-system-check-only.json", setup_payload)
    readiness = setup_payload.get("production_readiness") or {}
    if setup_system.returncode != 0 or readiness.get("status") != "ready":
        raise AssertionError(f"setup-system readiness is not ready: {readiness}")

    project = TMP_ROOT / "project"
    seed_project(project)

    checks: dict[str, Any] = {"run_id": RUN_ID, "project": str(project), "checks": {}}

    started = time.monotonic()
    proc = run("scenario-1-core", [SPEC_ANCHOR, "core"], cwd=project)
    result = parse_stdout_json("scenario-1-core")
    assert proc.returncode == 0, result
    assert_core_success("scenario-1", result, mode="incremental")
    progress = read_progress(project)
    providers = provider_invocation_summary()
    progress_providers = progress_provider_summary(progress)
    if not progress_providers["contains_codex"] or not progress_providers["contains_claude"]:
        raise AssertionError(
            f"scenario-1: expected codex and claude real-provider stages, got {progress_providers}"
        )
    if progress_providers["contains_fake_or_stub"]:
        raise AssertionError(
            f"scenario-1: fake/stub marker found: invocations={providers}, progress={progress_providers}"
        )
    copy_artifact(project, ".spec-anchor/state/core_progress.json", "scenario-1-core_progress.json")
    checks["checks"]["scenario_1_incremental"] = {
        "passed": True,
        "result_status": result.get("status"),
        "retrieval_index_status": result.get("retrieval_index_status"),
        "related_sections_status": result.get("related_sections_status"),
        "provider_invocations": providers,
        "progress_providers": progress_providers,
        "progress_mode": progress.get("mode"),
    }
    write_evidence_row(
        scenario="scenario-1-incremental",
        line=263,
        checkbox_text="scenario 1: incremental 経路",
        verification_level="real_smoke_verified",
        result="passed",
        duration_sec=time.monotonic() - started,
        evidence=[
            "stdout/scenario-1-core.stdout",
            "artifacts/scenario-1-core_progress.json",
            "artifacts/provider-invocations.jsonl",
        ],
    )

    started = time.monotonic()
    proc = run("scenario-2-core-all", [SPEC_ANCHOR, "core", "--all"], cwd=project)
    result = parse_stdout_json("scenario-2-core-all")
    assert proc.returncode == 0, result
    assert_core_success("scenario-2", result, mode="full")
    progress = read_progress(project)
    if progress.get("mode") != "full":
        raise AssertionError(f"scenario-2: progress mode expected full, got {progress.get('mode')!r}")
    copy_artifact(project, ".spec-anchor/state/core_progress.json", "scenario-2-core_progress.json")
    checks["checks"]["scenario_2_all"] = {
        "passed": True,
        "mode": result.get("mode"),
        "progress_mode": progress.get("mode"),
        "retrieval_index_status": result.get("retrieval_index_status"),
        "related_sections_status": result.get("related_sections_status"),
    }
    write_evidence_row(
        scenario="scenario-2-all",
        line=266,
        checkbox_text="scenario 2: `--all` 経路",
        verification_level="real_smoke_verified",
        result="passed",
        duration_sec=time.monotonic() - started,
        evidence=["stdout/scenario-2-core-all.stdout", "artifacts/scenario-2-core_progress.json"],
    )

    started = time.monotonic()
    proc = run("scenario-3-core-rebuild", [SPEC_ANCHOR, "core", "--rebuild"], cwd=project)
    result = parse_stdout_json("scenario-3-core-rebuild")
    assert proc.returncode == 0, result
    assert_core_success("scenario-3", result, mode="full")
    progress = read_progress(project)
    upsert_stage = progress.get("stages", {}).get("section_collection_upsert", {})
    if upsert_stage.get("action") != "upserted_full":
        raise AssertionError(f"scenario-3: section_collection_upsert.action expected upserted_full, got {upsert_stage}")
    copy_artifact(project, ".spec-anchor/state/core_progress.json", "scenario-3-core_progress.json")
    checks["checks"]["scenario_3_rebuild"] = {
        "passed": True,
        "mode": result.get("mode"),
        "section_collection_upsert": upsert_stage,
    }
    write_evidence_row(
        scenario="scenario-3-rebuild",
        line=269,
        checkbox_text="scenario 3: `--rebuild` 経路",
        verification_level="real_smoke_verified",
        result="passed",
        duration_sec=time.monotonic() - started,
        evidence=["stdout/scenario-3-core-rebuild.stdout", "artifacts/scenario-3-core_progress.json"],
    )

    before_hashes = artifact_hashes(project)
    started = time.monotonic()
    proc = run("scenario-4-core-idempotent", [SPEC_ANCHOR, "core"], cwd=project)
    result = parse_stdout_json("scenario-4-core-idempotent")
    assert proc.returncode == 0, result
    after_hashes = artifact_hashes(project)
    if result.get("freshness_report", {}).get("status") != "fresh":
        raise AssertionError("scenario-4: freshness_report.status must be fresh")
    if result.get("retrieval_index_status") != "skipped_unchanged":
        raise AssertionError(
            f"scenario-4: retrieval_index_status expected skipped_unchanged, got {result.get('retrieval_index_status')!r}"
        )
    if result.get("related_sections_status") != "skipped_unchanged":
        raise AssertionError(
            f"scenario-4: related_sections_status expected skipped_unchanged, got {result.get('related_sections_status')!r}"
        )
    if before_hashes != after_hashes:
        raise AssertionError(
            f"scenario-4: artifact hashes changed: before={before_hashes} after={after_hashes}"
        )
    copy_artifact(project, ".spec-anchor/state/core_progress.json", "scenario-4-core_progress.json")
    write_json(ARTIFACTS / "scenario-4-artifact-hashes.json", after_hashes)
    checks["checks"]["scenario_4_idempotency"] = {
        "passed": True,
        "retrieval_index_status": result.get("retrieval_index_status"),
        "related_sections_status": result.get("related_sections_status"),
        "artifact_hashes": after_hashes,
    }
    write_evidence_row(
        scenario="scenario-4-idempotency",
        line=272,
        checkbox_text="scenario 4: idempotency",
        verification_level="real_smoke_verified",
        result="passed",
        duration_sec=time.monotonic() - started,
        evidence=[
            "stdout/scenario-4-core-idempotent.stdout",
            "artifacts/scenario-4-core_progress.json",
            "artifacts/scenario-4-artifact-hashes.json",
        ],
    )

    failure_project = TMP_ROOT / "qdrant-unavailable"
    shutil.copytree(project, failure_project)
    config_path = failure_project / ".spec-anchor/config.toml"
    text = config_path.read_text(encoding="utf-8")
    text = text.replace('url = "http://localhost:6333"', 'url = "http://127.0.0.1:1"')
    config_path.write_text(text, encoding="utf-8")
    started = time.monotonic()
    proc = run("scenario-5-core-qdrant-unavailable", [SPEC_ANCHOR, "core", "--rebuild"], cwd=failure_project, timeout=600)
    result = parse_stdout_json("scenario-5-core-qdrant-unavailable")
    if result.get("status") != "failed":
        raise AssertionError(f"scenario-5: status expected failed, got {result.get('status')!r}")
    if result.get("retrieval_index_status") != "failed":
        raise AssertionError(
            f"scenario-5: retrieval_index_status expected failed, got {result.get('retrieval_index_status')!r}"
        )
    warnings_text = json.dumps(result.get("warnings") or [], ensure_ascii=False)
    if "/spec-core --rebuild" not in warnings_text:
        raise AssertionError(f"scenario-5: warnings did not include /spec-core --rebuild: {warnings_text}")
    copy_artifact(
        failure_project,
        ".spec-anchor/state/core_progress.json",
        "scenario-5-core_progress.json",
    )
    checks["checks"]["scenario_5_qdrant_unavailable"] = {
        "passed": True,
        "exit_code": proc.returncode,
        "status": result.get("status"),
        "retrieval_index_status": result.get("retrieval_index_status"),
        "warnings": result.get("warnings"),
    }
    write_evidence_row(
        scenario="scenario-5-qdrant-unavailable",
        line=275,
        checkbox_text="scenario 5: 失敗系 (Qdrant 不到達)",
        verification_level="real_smoke_verified",
        result="passed",
        duration_sec=time.monotonic() - started,
        evidence=[
            "stdout/scenario-5-core-qdrant-unavailable.stdout",
            "artifacts/scenario-5-core_progress.json",
        ],
    )

    for rel, name in [
        (".spec-anchor/context/section_manifest.json", "section_manifest.json"),
        (".spec-anchor/context/section_metadata.json", "section_metadata.json"),
        (".spec-anchor/context/related_sections.json", "related_sections.json"),
        (".spec-anchor/context/chapter_anchors.json", "chapter_anchors.json"),
        (".spec-anchor/state/retrieval_index_state.json", "retrieval_index_state.json"),
        (".spec-anchor/state/related_sections_state.json", "related_sections_state.json"),
    ]:
        copy_artifact(project, rel, name)

    rows = [json.loads(line) for line in EVIDENCE_MAP.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 5 or any(row.get("verification_level") != "real_smoke_verified" or row.get("result") != "passed" for row in rows):
        raise AssertionError(f"unexpected evidence_map rows: {rows}")
    checks["summary"] = {
        "run_id": RUN_ID,
        "scenario_count": len(rows),
        "all_passed": all(row.get("result") == "passed" for row in rows),
        "verification_level": "real_smoke_verified",
        "fake_env_unset": True,
        "provider_invocations": provider_invocation_summary(),
        "progress_providers": progress_provider_summary(read_progress(project)),
        "evidence_map": "evidence_map.jsonl",
    }
    write_json(ARTIFACTS / "assertions.json", checks)
    print(json.dumps(checks["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
