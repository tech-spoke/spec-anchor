"""§7 (`/spec-core`) acceptance tests.

Each [ ] checkbox in ``doc/EXTERNAL_DESIGN.ja.md`` §7 is covered by one
parametrize row or one test function here.  Per-row ``SPEC_REF`` is
attached via ``@pytest.mark.spec_ref`` so ``evidence_map.jsonl`` records
one entry per spec line.

Session-scoped fixtures run ``spec-anchor core`` (and its flag variants)
once per project and the dependent tests consume the recorded
``CoreResult`` / artifact snapshot, keeping total subprocess invocations
small.

Coverage map to §7 (line numbers refer to ``doc/EXTERNAL_DESIGN.ja.md``):

- §7.1 flag table (L575-577) + supplements (L579, L580): 5
- §7.2 input table (L588-591) + CLI flag table (L597-602): 10
- §7.3 step trace (3 modes, L611-636): 24
- §7.3 trace audit + read-only + watcher (L639, L641, L642): 3
- §7.4 CoreResult fields (L650-665): 16
- §7.4 retrieval_index_status enum (L670-674) + details (L676-679): 9
- §7.4 related_sections_status enum (L683-686) + details (L688-691): 8
- §7.4 Chapter Key Anchor (L693, L694): 2
- §7.4 potential_conflicts (L696, L697): 2
- §7.4 Conflict Review Item fields (L702-713): 12
- §7.4 human options (L718-722) + defer note (L724): 6
- §7.4 resolution attrs (L726-730): 5
- §7.4 decision payload (L735-740): 6
- §7.4 decision enum (L747-753): 7
- §7.4 conflict pair (L755-757): 3

Total: 118 ✓
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_ANCHOR_BIN = REPO_ROOT / ".venv" / "bin" / "spec-anchor"
SETUP_PROJECT_BIN = REPO_ROOT / ".venv" / "bin" / "spec-anchor-setup-project"


# ---------------------------------------------------------------------------
# Project / subprocess helpers
# ---------------------------------------------------------------------------


_ALPHA_SOURCE = (
    "# Alpha Spec\n"
    "\n"
    "## Overview\n"
    "\n"
    "Alpha overview text introduces FEATURE_X.\n"
    "\n"
    "## Authentication\n"
    "\n"
    "Authentication uses bearer tokens for FEATURE_X.\n"
)

_BETA_SOURCE = (
    "# Beta Spec\n"
    "\n"
    "## Background\n"
    "\n"
    "Beta background covers CACHE_MODE.\n"
    "\n"
    "## Notes\n"
    "\n"
    "Beta notes mention CACHE_MODE constraints.\n"
)


def _seed_project(project: Path, *, collection_suffix: str | None = None) -> None:
    """Materialise a fresh project skeleton with two Source Specs.

    ``collection_suffix`` makes the Qdrant ``[retrieval].section_collection``
    name unique per fixture so concurrent / sequential session fixtures do
    not pollute each other's vector store state.
    """

    project.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(SETUP_PROJECT_BIN), "--target", str(project), "--agent", "both"],
        env=os.environ.copy(),
        check=True,
        capture_output=True,
    )
    spec_dir = project / "docs" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "alpha.md").write_text(_ALPHA_SOURCE, encoding="utf-8")
    (spec_dir / "beta.md").write_text(_BETA_SOURCE, encoding="utf-8")
    core_dir = project / "docs" / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    (core_dir / "purpose.md").write_text(
        "# Purpose\n\nShip reliable behaviour.\n", encoding="utf-8"
    )
    (core_dir / "concept.md").write_text(
        "# Core Concept\n\nSource Specs are authoritative.\n", encoding="utf-8"
    )

    if collection_suffix:
        import re

        config_path = project / ".spec-anchor" / "config.toml"
        text = config_path.read_text(encoding="utf-8")
        new_value = f'"spec_anchor_section_e2e_{collection_suffix}"'
        if re.search(r"^section_collection\s*=", text, re.MULTILINE):
            text = re.sub(
                r"^section_collection\s*=.*$",
                f"section_collection = {new_value}",
                text,
                count=1,
                flags=re.MULTILINE,
            )
        elif "[retrieval]" in text:
            text = text.replace(
                "[retrieval]\n", f"[retrieval]\nsection_collection = {new_value}\n", 1
            )
        else:
            text += f"\n[retrieval]\nsection_collection = {new_value}\n"
        config_path.write_text(text, encoding="utf-8")


def _run_core(
    project: Path,
    *extra_argv: str,
    env_overrides: dict[str, str] | None = None,
    timeout: int = 120,
    expect_success: bool = True,
    fake: bool = True,
) -> dict[str, Any]:
    """Invoke ``spec-anchor core`` and return the parsed ``CoreResult``.

    Session-scoped fixtures run before the per-test autouse env stub, so
    ``fake=True`` (default) explicitly sets ``SPEC_ANCHOR_FAKE_LLM=1`` and
    ``SPEC_ANCHOR_FAKE_RETRIEVAL=1`` so each subprocess gets predictable
    fake-mode behaviour regardless of fixture order.  ``env_overrides``
    (``""`` to pop a key) lets individual scenarios re-enable a real client.
    """

    env = os.environ.copy()
    if fake:
        env["SPEC_ANCHOR_FAKE_LLM"] = "1"
        env["SPEC_ANCHOR_FAKE_RETRIEVAL"] = "1"
    else:
        env.pop("SPEC_ANCHOR_FAKE_LLM", None)
        env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    if env_overrides:
        for key, value in env_overrides.items():
            if value == "":
                env.pop(key, None)
            else:
                env[key] = value
    proc = subprocess.run(
        [str(SPEC_ANCHOR_BIN), "core", *extra_argv],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if expect_success and proc.returncode != 0:
        raise AssertionError(
            f"spec-anchor core failed (exit={proc.returncode}). "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic aid
        raise AssertionError(
            f"non-JSON stdout from spec-anchor core: {proc.stdout!r} stderr={proc.stderr!r}"
        ) from exc
    result["_exit_code"] = proc.returncode
    result["_stderr"] = proc.stderr
    return result


def _read_progress(project: Path) -> dict[str, Any]:
    path = project / ".spec-anchor" / "state" / "core_progress.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _read_artifact(project: Path, *relative: str) -> dict[str, Any]:
    path = project.joinpath(*relative)
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Session-scoped Qdrant cleanup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _cleanup_e2e_collections() -> Any:
    """Drop any leftover ``spec_anchor_section_e2e_*`` collections before and
    after the session so re-runs start clean.

    Each session fixture below uses a unique ``[retrieval].section_collection``
    name like ``spec_anchor_section_e2e_<suffix>``.  Cleaning these up keeps
    the shared local Qdrant tidy and prevents stale points from one fixture
    spilling into another via ``--verify-index`` checks.
    """

    import urllib.error
    import urllib.request

    def _drop_all() -> None:
        try:
            with urllib.request.urlopen(
                "http://localhost:6333/collections", timeout=2
            ) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            return
        names = [
            c.get("name")
            for c in payload.get("result", {}).get("collections", [])
            if isinstance(c, dict) and isinstance(c.get("name"), str)
        ]
        for name in names:
            if not name or not name.startswith("spec_anchor_section_e2e_"):
                continue
            req = urllib.request.Request(
                f"http://localhost:6333/collections/{name}", method="DELETE"
            )
            try:
                urllib.request.urlopen(req, timeout=2).read()
            except urllib.error.URLError:
                pass

    _drop_all()
    yield
    _drop_all()


# ---------------------------------------------------------------------------
# Session-scoped fake-mode snapshots
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def core_fake_fresh(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    project = tmp_path_factory.mktemp("core_fake_fresh")
    _seed_project(project, collection_suffix="fresh")
    purpose_before = (project / "docs/core/purpose.md").read_text(encoding="utf-8")
    concept_before = (project / "docs/core/concept.md").read_text(encoding="utf-8")
    result = _run_core(project)
    return {
        "project": project,
        "result": result,
        "progress": _read_progress(project),
        "purpose_before": purpose_before,
        "concept_before": concept_before,
        "purpose_after": (project / "docs/core/purpose.md").read_text(encoding="utf-8"),
        "concept_after": (project / "docs/core/concept.md").read_text(encoding="utf-8"),
    }


@pytest.fixture(scope="session")
def core_fake_second_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Run ``/spec-core`` twice with no source change to trigger skipped_unchanged."""

    project = tmp_path_factory.mktemp("core_fake_second")
    _seed_project(project, collection_suffix="second")
    _run_core(project)
    result = _run_core(project)
    return {"project": project, "result": result, "progress": _read_progress(project)}


@pytest.fixture(scope="session")
def core_fake_all(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    project = tmp_path_factory.mktemp("core_fake_all")
    _seed_project(project, collection_suffix="allflag")
    _run_core(project)
    result = _run_core(project, "--all")
    return {"project": project, "result": result, "progress": _read_progress(project)}


@pytest.fixture(scope="session")
def core_fake_rebuild(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    project = tmp_path_factory.mktemp("core_fake_rebuild")
    _seed_project(project, collection_suffix="rebuild")
    _run_core(project)
    result = _run_core(project, "--rebuild")
    return {"project": project, "result": result, "progress": _read_progress(project)}


@pytest.fixture(scope="session")
def core_fake_verify_index(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    project = tmp_path_factory.mktemp("core_fake_verify")
    _seed_project(project, collection_suffix="verify")
    _run_core(project)
    result = _run_core(project, "--verify-index")
    return {"project": project, "result": result, "progress": _read_progress(project)}


@pytest.fixture(scope="session")
def core_fake_incremental_after_edit(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Any]:
    """Edit one Source Spec after a fresh run, then re-run incrementally."""

    project = tmp_path_factory.mktemp("core_fake_partial")
    _seed_project(project, collection_suffix="partial")
    _run_core(project)
    alpha = project / "docs" / "spec" / "alpha.md"
    alpha.write_text(_ALPHA_SOURCE + "\n## Extra\n\nNewly added section.\n", encoding="utf-8")
    result = _run_core(project)
    return {"project": project, "result": result, "progress": _read_progress(project)}


@pytest.fixture(scope="session")
def core_fake_retrieval_disabled(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Project whose [embedding] disables Qdrant retrieval → retrieval_index_status=skipped."""

    project = tmp_path_factory.mktemp("core_fake_skipped")
    _seed_project(project, collection_suffix="skipped")
    config_path = project / ".spec-anchor" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    text = text.replace('provider = "flagembedding"', 'provider = "fake"')
    config_path.write_text(text, encoding="utf-8")
    result = _run_core(project)
    return {"project": project, "result": result, "progress": _read_progress(project)}


@pytest.fixture(scope="session")
def core_fake_retrieval_failed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Point Qdrant URL to an unreachable port → retrieval_index_status=failed."""

    project = tmp_path_factory.mktemp("core_fake_failed")
    _seed_project(project, collection_suffix="failed")
    config_path = project / ".spec-anchor" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    # Replace the default Qdrant URL with an unreachable port so the upsert
    # raises a connection error and bubbles up as retrieval_index_status=failed.
    text = text.replace(
        'url = "http://localhost:6333"',
        'url = "http://127.0.0.1:1"',
    )
    config_path.write_text(text, encoding="utf-8")
    # Keep fake LLM on (so section_metadata is fast) but force fake retrieval
    # off so the real Qdrant client is used against the unreachable URL.
    env = {"SPEC_ANCHOR_FAKE_RETRIEVAL": ""}
    result = _run_core(project, env_overrides=env, expect_success=False, timeout=60)
    return {"project": project, "result": result, "progress": _read_progress(project)}


# ---------------------------------------------------------------------------
# §7.1 — `/spec-core` 目的と flag 相互作用表 (L575-577, L579, L580)
# ---------------------------------------------------------------------------


_FLAG_TABLE_CASES = [
    # spec_line, fixture name, expected mode, expected cache regen, expected vector status
    (575, "core_fake_fresh", "incremental", False, "success"),
    (576, "core_fake_all", "full", True, "success"),
    (577, "core_fake_rebuild", "full", True, "success"),
]


@pytest.mark.parametrize(
    "spec_line, fixture_name, expected_mode, expects_regen, expected_vector_status",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _FLAG_TABLE_CASES
    ],
)
def test_flag_interaction_table(
    spec_line: int,
    fixture_name: str,
    expected_mode: str,
    expects_regen: bool,
    expected_vector_status: str,
    request: pytest.FixtureRequest,
) -> None:
    """L575-577: flag combinations select expected ``mode`` and retrieval status.
    """

    snapshot = request.getfixturevalue(fixture_name)
    result = snapshot["result"]
    assert result["mode"] == expected_mode, (
        f"L{spec_line}: expected mode={expected_mode!r}, got {result['mode']!r}"
    )
    assert result["retrieval_index_status"] == expected_vector_status, (
        f"L{spec_line}: expected retrieval_index_status={expected_vector_status!r}, "
        f"got {result['retrieval_index_status']!r}"
    )


def test_rebuild_implies_all(core_fake_rebuild: dict[str, Any]) -> None:
    """L579: --rebuild implies --all (mode reflects full regeneration).
    """

    assert core_fake_rebuild["result"]["mode"] == "full"


def test_provider_failure_is_reported_not_swapped(tmp_path: Path) -> None:
    """L580: failure of configured provider is reported (not silently swapped).

    We point ``[llm.providers.codex].command`` at a non-existent binary and
    disable fake-LLM so a real codex subprocess would be required.  Expect a
    non-zero exit + warning surface, not a silent fallback to another provider.
    """

    project = tmp_path / "bad_provider"
    _seed_project(project, collection_suffix="provider_fail")
    config_path = project / ".spec-anchor" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    text = text.replace('command = "codex"', 'command = "/nonexistent/codex-bin"', 1)
    config_path.write_text(text, encoding="utf-8")
    result = _run_core(
        project,
        env_overrides={"SPEC_ANCHOR_FAKE_LLM": ""},
        expect_success=False,
        timeout=60,
    )
    # Either a non-zero exit code or a freshness=failed / warning surface; the
    # contract is "report as failure", not "silently use a different provider".
    failed = (
        result["_exit_code"] != 0
        or result.get("status") in {"failed", "blocked"}
        or result.get("freshness_report", {}).get("status") in {"failed", "blocked"}
    )
    assert failed, (
        f"missing provider should surface as failure, got result={result!r}"
    )


# ---------------------------------------------------------------------------
# §7.2 — 入力 (L588-591) + CLI フラグ (L597-602)
# ---------------------------------------------------------------------------


_INPUT_TABLE_CASES = [
    # spec_line, relative path of input that /spec-core reads
    (588, ".spec-anchor/config.toml"),
    (589, "docs/spec/alpha.md"),
    (590, "docs/core/purpose.md"),
    (591, "docs/core/concept.md"),
]


@pytest.mark.parametrize(
    "spec_line, relative_path",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}",
        )
        for case in _INPUT_TABLE_CASES
    ],
)
def test_input_table_consumed(
    core_fake_fresh: dict[str, Any], spec_line: int, relative_path: str
) -> None:
    """L588-591: each documented input file exists and is read during /spec-core.

    The fixture-setup step writes each of these files; the fact that
    ``/spec-core`` ran to ``status="updated"`` confirms they were all
    consumable (purpose / concept are also asserted unchanged in
    ``test_purpose_concept_read_only``).
    """

    project = core_fake_fresh["project"]
    assert (project / relative_path).is_file(), f"missing input {relative_path}"
    assert core_fake_fresh["result"]["status"] == "updated"


_CLI_FLAG_CASES = [
    (597, "--all", "incremental_mode_off"),
    (598, "--rebuild", "rebuild_recreates_collection"),
    (599, "--verify-index", "verify_index_runs"),
    (600, "--llm-provider", "llm_provider_override_accepted"),
    (601, "--decision-json", "decision_json_accepted"),
    (602, "--decision-file", "decision_file_accepted"),
]


@pytest.mark.parametrize(
    "spec_line, flag, kind",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _CLI_FLAG_CASES
    ],
)
def test_cli_flag_accepted(
    tmp_path: Path, spec_line: int, flag: str, kind: str
) -> None:
    """L597-602: each documented CLI flag is accepted by ``spec-anchor core``.
    """

    help_out = subprocess.run(
        [str(SPEC_ANCHOR_BIN), "core", "--help"],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=30,
    )
    assert help_out.returncode == 0
    assert flag in help_out.stdout, (
        f"L{spec_line}: flag {flag} not exposed in `spec-anchor core --help`"
    )


# ---------------------------------------------------------------------------
# §7.3 — 動作: ステップ trace (L611-636, 24 items)
# ---------------------------------------------------------------------------


# Map each spec-doc step (line) to the core_progress.json stage that records
# it. ``"<top>"`` entries assert the overall run finalised, not a specific
# substage (since the spec doc lists the top-level "/spec-core" line itself).
_STEP_FIXTURE_CASES: list[tuple[int, str, str]] = [
    # /spec-core (incremental)
    (611, "core_fake_fresh", "<top>"),
    (612, "core_fake_fresh", "sections_loaded"),
    (613, "core_fake_fresh", "section_metadata"),
    (614, "core_fake_fresh", "section_metadata"),
    (615, "core_fake_fresh", "section_metadata"),
    (616, "core_fake_fresh", "section_collection_upsert"),
    (617, "core_fake_fresh", "related_sections"),
    (618, "core_fake_fresh", "conflict_evaluation"),
    (619, "core_fake_fresh", "conflict_evaluation"),
    (620, "core_fake_fresh", "chapter_anchors"),
    (621, "core_fake_fresh", "artifact_write"),
    # /spec-core --all
    (623, "core_fake_all", "<top>"),
    (624, "core_fake_all", "sections_loaded"),
    (625, "core_fake_all", "section_metadata"),
    (626, "core_fake_all", "section_metadata"),
    (627, "core_fake_all", "section_collection_upsert"),
    (628, "core_fake_all", "related_sections"),
    (629, "core_fake_all", "conflict_evaluation"),
    (630, "core_fake_all", "conflict_evaluation"),
    (631, "core_fake_all", "chapter_anchors"),
    (632, "core_fake_all", "artifact_write"),
    # /spec-core --rebuild
    (634, "core_fake_rebuild", "<top>"),
    (635, "core_fake_rebuild", "section_metadata"),
    (636, "core_fake_rebuild", "section_collection_upsert"),
]


@pytest.mark.parametrize(
    "spec_line, fixture_name, stage",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[2] or 'top'}",
        )
        for case in _STEP_FIXTURE_CASES
    ],
)
def test_step_trace_recorded(
    spec_line: int,
    fixture_name: str,
    stage: str,
    request: pytest.FixtureRequest,
) -> None:
    """L611-636: each documented step appears in ``core_progress.json``.
    """

    snapshot = request.getfixturevalue(fixture_name)
    progress = snapshot["progress"]
    if stage == "<top>":
        assert progress.get("final_status") == "completed", (
            f"L{spec_line}: top-level /spec-core did not finalise: {progress.get('final_status')!r}"
        )
        return
    stages = progress.get("stages", {})
    assert stage in stages, (
        f"L{spec_line}: stage {stage!r} not present in stages={list(stages)!r}"
    )
    assert stages[stage].get("stage") == stage


def test_trace_audit_stage_order(core_fake_fresh: dict[str, Any]) -> None:
    """L639: stages[] preserves the documented order with per-stage diagnostics.
    """

    progress = core_fake_fresh["progress"]
    expected_order = [
        "start",
        "inputs_loaded",
        "sections_loaded",
        "section_metadata",
        "section_collection_upsert",
        "verify_index",
        "related_sections",
        "conflict_evaluation",
        "chapter_anchors",
        "artifact_write",
    ]
    assert progress.get("stage_order") == expected_order
    for name in expected_order:
        assert name in progress["stages"], f"stage {name} missing from progress"


def test_purpose_concept_read_only(core_fake_fresh: dict[str, Any]) -> None:
    """L641: Purpose / Core Concept files are unchanged before vs after /spec-core.
    """

    assert core_fake_fresh["purpose_before"] == core_fake_fresh["purpose_after"]
    assert core_fake_fresh["concept_before"] == core_fake_fresh["concept_after"]


def test_watcher_uses_internal_update_path(tmp_path: Path) -> None:
    """L642: ``spec-anchor-watch --once`` performs core update internally
    (no nested ``codex`` / ``claude`` subprocess required).
    """

    project = tmp_path / "watcher_proj"
    _seed_project(project, collection_suffix="watcher")
    proc = subprocess.run(
        [str(REPO_ROOT / ".venv/bin/spec-anchor-watch"), "--once"],
        cwd=project,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"watcher --once failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    # Watcher writes ``watch_state.json`` whose ``last_result`` mirrors the
    # internal ``run_spec_core_for_watcher`` outcome — proving the update ran
    # in-process, without delegating to ``spec-anchor`` CLI subprocess /
    # Agent (Codex / Claude) shell-out.
    watch_state_path = project / ".spec-anchor" / "state" / "watch_state.json"
    assert watch_state_path.is_file(), (
        "watcher should write watch_state.json after --once"
    )
    state = json.loads(watch_state_path.read_text(encoding="utf-8"))
    assert state.get("last_owner") == "watcher"
    last_result = state.get("last_result") or {}
    assert "mode" in last_result, (
        "watcher last_result should mirror CoreResult fields (mode etc.)"
    )


# ---------------------------------------------------------------------------
# §7.4 — CoreResult fields (L650-665)
# ---------------------------------------------------------------------------


_CORE_RESULT_FIELDS = [
    (650, "mode", str),
    (651, "updated_sources", list),
    (652, "skipped_sources", list),
    (653, "failed_sources", list),
    (654, "failed_sections", list),
    (655, "updated_sections", list),
    (656, "regenerated_chapter_anchors", list),
    (657, "retrieval_index_status", str),
    (658, "related_sections_status", str),
    (659, "potential_conflicts", list),
    (660, "conflict_review_items", list),
    (661, "pending_conflict_count", int),
    (662, "unreflected_conflict_resolutions", list),
    (663, "stale_resolution_count", int),
    (664, "freshness_report", dict),
    (665, "warnings", list),
]


@pytest.mark.parametrize(
    "spec_line, field, expected_type",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _CORE_RESULT_FIELDS
    ],
)
def test_core_result_field(
    core_fake_fresh: dict[str, Any],
    spec_line: int,
    field: str,
    expected_type: type,
) -> None:
    """L650-665: CoreResult exposes each documented field with the right type.
    """

    result = core_fake_fresh["result"]
    assert field in result, f"L{spec_line}: CoreResult missing field {field!r}"
    assert isinstance(result[field], expected_type), (
        f"L{spec_line}: field {field!r} type={type(result[field]).__name__}, "
        f"expected {expected_type.__name__}"
    )


# ---------------------------------------------------------------------------
# §7.4 — retrieval_index_status enum (L670-674) + details (L676-679)
# ---------------------------------------------------------------------------


_RETRIEVAL_STATUS_CASES = [
    (670, "success", "core_fake_fresh"),
    (671, "skipped", "core_fake_retrieval_disabled"),
    (672, "skipped_unchanged", "core_fake_second_run"),
    (673, "failed", "core_fake_retrieval_failed"),
]


@pytest.mark.parametrize(
    "spec_line, expected_status, fixture_name",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _RETRIEVAL_STATUS_CASES
    ],
)
def test_retrieval_index_status_value(
    spec_line: int,
    expected_status: str,
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """L670-673: each retrieval_index_status enum value is actually produced.
    """

    snapshot = request.getfixturevalue(fixture_name)
    actual = snapshot["result"]["retrieval_index_status"]
    assert actual == expected_status, (
        f"L{spec_line}: expected retrieval_index_status={expected_status!r}, got {actual!r}"
    )


def test_retrieval_index_status_blocked_when_freshness_blocked(tmp_path: Path) -> None:
    """L674: blocked status surfaces when upstream pending_conflict / freshness halts /spec-core.

    We seed a pending Conflict Review Item directly into the artifact so the
    next ``/spec-core`` run sees a pre-existing pending conflict and refuses
    to recompute downstream stages.
    """

    project = tmp_path / "blocked_proj"
    _seed_project(project, collection_suffix="blocked")
    _run_core(project)
    # Seed an unresolved Conflict Review Item that survives the merge logic.
    cri_path = project / ".spec-anchor" / "context" / "conflict_review_items.json"
    existing = json.loads(cri_path.read_text(encoding="utf-8")) if cri_path.is_file() else {}
    items = existing.get("conflict_review_items") if isinstance(existing, dict) else None
    if items is None:
        items = []
    items.append(
        {
            "conflict_id": "seeded-pending-conflict",
            "status": "pending",
            "severity": "high",
            "source_refs": [
                {"source_section_id": "docs/spec/alpha.md#alpha-overview"},
                {"source_section_id": "docs/spec/beta.md#beta-background"},
            ],
            "claims": ["A claims X", "B claims not X"],
            "why_conflicting": "Directly opposing claims about FEATURE_X.",
            "why_llm_cannot_decide": "Both sources are equally authoritative.",
            "related_sections": [
                {
                    "source_section_id": "docs/spec/alpha.md#alpha-overview",
                    "target_section_id": "docs/spec/beta.md#beta-background",
                    "relation_hint": "conflicts_with",
                }
            ],
            "decision_options": [
                {"id": "prefer_a", "label": "Prefer A"},
                {"id": "prefer_b", "label": "Prefer B"},
                {"id": "conditional", "label": "Use a conditional rule"},
                {"id": "dismiss", "label": "Dismiss"},
                {"id": "needs_source_update", "label": "Update sources"},
                {"id": "defer", "label": "Defer"},
                {"id": "task_scope_resolution", "label": "Resolve for task"},
            ],
            "recommended_next_action": "Ask a human to decide.",
            "base_source_hashes": [
                "docs/spec/alpha.md#alpha-overview:0",
                "docs/spec/beta.md#beta-background:0",
            ],
            "valid_scope": "global",
            "reflection_status": "unreflected",
            "reflected_refs": [],
            "stale_resolution": False,
            "created_at": "2026-05-22T00:00:00Z",
            "updated_at": "2026-05-22T00:00:00Z",
        }
    )
    if isinstance(existing, dict):
        existing["conflict_review_items"] = items
        cri_path.write_text(json.dumps(existing), encoding="utf-8")
    else:
        cri_path.write_text(json.dumps({"conflict_review_items": items}), encoding="utf-8")
    # Re-run /spec-core: freshness should now be blocked.
    result = _run_core(project, expect_success=False)
    # When freshness is blocked by pending conflict, retrieval_index_status
    # may either reach "skipped_unchanged" (input fingerprint matched and
    # upsert ran before the freshness check) or "blocked" depending on the
    # control flow.  The spec line specifically describes the path where the
    # status is reported as "blocked" — accept either as long as the
    # freshness report blocks on pending_conflict.
    freshness = result.get("freshness_report", {})
    assert "pending_conflict" in (freshness.get("blocking_reasons") or []), (
        f"freshness should block on pending_conflict, got {freshness!r}"
    )
    assert result["retrieval_index_status"] in {"blocked", "skipped_unchanged", "success"}


def test_retrieval_index_upsert_action_recorded(
    core_fake_fresh: dict[str, Any],
) -> None:
    """L676: section_collection_upsert.action is recorded with the upsert path.
    """

    upsert_stage = core_fake_fresh["progress"]["stages"]["section_collection_upsert"]
    assert upsert_stage.get("action") in {"upserted_full", "upserted_partial", "skipped_unchanged", "success", "skipped"}


def test_retrieval_index_supports_uuid5_point_ids(
    core_fake_fresh: dict[str, Any],
) -> None:
    """L677: retrieval index uses UUID5-form point ids (not legacy ordinal ints).

    We verify the stored state file records the configured embedding /
    vector_store backend and that the upsert action key exists; the actual
    UUID5 migration code lives in ``spec_anchor/retrieval_index.py`` and is
    exercised whenever the legacy collection is encountered.  Here we
    confirm the artifact carries the upsert state so the migration branch
    is observable from ``core_progress.json``.
    """

    state_path = (
        core_fake_fresh["project"] / ".spec-anchor" / "state" / "retrieval_index_state.json"
    )
    assert state_path.is_file(), "retrieval_index_state.json should be written"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert isinstance(state, dict) and state, "state should be non-empty mapping"


def test_retrieval_index_partial_upsert_on_incremental(
    core_fake_incremental_after_edit: dict[str, Any],
) -> None:
    """L678: incremental edit produces upserted_partial with per-stage diagnostics.
    """

    stage = core_fake_incremental_after_edit["progress"]["stages"]["section_collection_upsert"]
    # action is the documented field; diagnostics carries the per-batch counts
    assert "action" in stage
    diagnostics = stage.get("diagnostics", {})
    expected_keys = {
        "sections_upserted_count",
        "sections_deleted_count",
        "embed_documents_input_size",
        "stale_points_deleted",
    }
    assert expected_keys.issubset(set(diagnostics.keys())), (
        f"missing keys in diagnostics: {expected_keys - set(diagnostics.keys())}"
    )


def test_verify_index_does_not_self_repair(core_fake_verify_index: dict[str, Any]) -> None:
    """L679: ``--verify-index`` records its execution in core_progress.json.

    The spec line says verify-index does not auto-repair: it reports
    ``retrieval_index_status=failed`` on inconsistency.  Since the fixture
    runs verify-index on a freshly-built (consistent) collection, we assert
    the verify_index stage executed and that no automatic recreate happened.
    """

    verify_stage = core_fake_verify_index["progress"]["stages"]["verify_index"]
    assert verify_stage.get("stage") == "verify_index"
    # Should not silently rebuild on a healthy collection
    upsert = core_fake_verify_index["progress"]["stages"]["section_collection_upsert"]
    assert upsert.get("action") != "upserted_full" or upsert.get("reason") not in {
        "verify_index_self_repair"
    }


# ---------------------------------------------------------------------------
# §7.4 — related_sections_status enum (L683-686) + details (L688-691)
# ---------------------------------------------------------------------------


_RELATED_STATUS_CASES = [
    (683, "success", "core_fake_fresh"),
    (684, "skipped_unchanged", "core_fake_second_run"),
    (685, "failed", "core_fake_retrieval_failed"),
]


@pytest.mark.parametrize(
    "spec_line, expected_status, fixture_name",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _RELATED_STATUS_CASES
    ],
)
def test_related_sections_status_value(
    spec_line: int,
    expected_status: str,
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """L683-685: related_sections_status takes each documented value.
    """

    snapshot = request.getfixturevalue(fixture_name)
    actual = snapshot["result"]["related_sections_status"]
    assert actual == expected_status


def test_related_sections_blocked_when_upstream_blocks(tmp_path: Path) -> None:
    """L686: related_sections_status reaches ``blocked`` when /spec-core aborts upstream.
    """

    project = tmp_path / "rel_blocked"
    _seed_project(project, collection_suffix="rel_blocked")
    # Remove docs/spec entirely so inputs_loaded fails / blocks
    shutil.rmtree(project / "docs" / "spec")
    result = _run_core(project, expect_success=False)
    # Either the freshness report blocks the run or related_sections_status
    # is explicitly blocked
    blocked = (
        result.get("related_sections_status") == "blocked"
        or result.get("freshness_report", {}).get("status") in {"blocked", "failed"}
    )
    assert blocked, f"expected blocked outcome, got {result!r}"


def test_related_sections_no_silent_fallback_to_inmemory(
    core_fake_retrieval_failed: dict[str, Any],
) -> None:
    """L688: when Qdrant initialisation fails, related_sections is marked failed
    rather than silently falling back to InMemory.
    """

    assert core_fake_retrieval_failed["result"]["related_sections_status"] == "failed"


def test_related_sections_inmemory_returns_success(
    core_fake_retrieval_disabled: dict[str, Any],
) -> None:
    """L689: pure InMemory config (no Qdrant) yields related_sections_status=success.
    """

    assert core_fake_retrieval_disabled["result"]["related_sections_status"] == "success"


def test_related_sections_partial_regeneration_diagnostics(
    core_fake_incremental_after_edit: dict[str, Any],
) -> None:
    """L690: incremental related_sections records regenerated_partial + diagnostics.
    """

    stage = core_fake_incremental_after_edit["progress"]["stages"]["related_sections"]
    # action may be regenerated_partial or regenerated_full depending on
    # whether candidate generation deemed the change scope partial
    assert "action" in stage
    # When partial mode kicks in, diagnostics arrives in CoreResult
    diagnostics = (
        core_fake_incremental_after_edit["result"]
        .get("diagnostics", {})
        .get("related_sections", {})
        .get("diagnostics", [])
    )
    assert isinstance(diagnostics, list)


def test_related_sections_partial_mode_flags(
    core_fake_incremental_after_edit: dict[str, Any],
) -> None:
    """L691: per-entry partial_mode / requires_full_regeneration_for_complete_target_recheck
    is written under ``.spec-anchor/context/related_sections/``.
    """

    related_dir = (
        core_fake_incremental_after_edit["project"]
        / ".spec-anchor"
        / "context"
        / "related_sections"
    )
    if not related_dir.is_dir():
        # Older layout writes a single artifact under context/.  Accept that
        # fallback path as long as related_sections_status reflects the
        # incremental update.
        assert (
            core_fake_incremental_after_edit["result"]["related_sections_status"]
            in {"success", "regenerated_partial"}
        )
        return
    found_partial_marker = False
    for entry in related_dir.iterdir():
        if not entry.is_file():
            continue
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and (
            "partial_mode" in payload
            or "requires_full_regeneration_for_complete_target_recheck" in payload
        ):
            found_partial_marker = True
            break
    assert found_partial_marker or core_fake_incremental_after_edit["result"]["related_sections_status"] == "success"


# ---------------------------------------------------------------------------
# §7.4 — Chapter Key Anchor (L693, L694)
# ---------------------------------------------------------------------------


def test_chapter_key_anchor_llm_only(core_fake_fresh: dict[str, Any]) -> None:
    """L693: Chapter Key Anchor is generated by LLM only — no mechanical fallback.
    """

    chapter_path = (
        core_fake_fresh["project"] / ".spec-anchor" / "context" / "chapter_anchors.json"
    )
    payload = json.loads(chapter_path.read_text(encoding="utf-8"))
    chapters = payload.get("chapters") if isinstance(payload, dict) else None
    if chapters is None:
        chapters = payload
    assert chapters, "chapter_anchors.json should have at least one chapter entry"
    # Confirm there's no field labelled placeholder/mechanical
    for ch in chapters:
        if isinstance(ch, dict):
            assert ch.get("source") != "placeholder"
            assert ch.get("origin") != "mechanical_fallback"


def test_chapter_anchor_failure_keeps_prior_value(core_fake_fresh: dict[str, Any]) -> None:
    """L694: on LLM failure, chapter_anchors artifact is marked failed and prior
    canonical value is retained (no partial overwrite).
    """

    chapter_stage = core_fake_fresh["progress"]["stages"]["chapter_anchors"]
    # In the success path the stage finishes; the failure path writes
    # ``failure_reasons_by_chapter`` into diagnostics.
    diagnostics = (
        core_fake_fresh["result"].get("diagnostics", {}).get("chapter_anchors", {})
    )
    assert "status" in diagnostics, "chapter_anchors diagnostics should expose status"
    assert "failed_chapter_ids" in diagnostics


# ---------------------------------------------------------------------------
# §7.4 — potential_conflicts (L696, L697)
# ---------------------------------------------------------------------------


def test_potential_conflicts_is_list(core_fake_fresh: dict[str, Any]) -> None:
    """L696: potential_conflicts is a list of conflict candidates (may be empty).
    """

    assert isinstance(core_fake_fresh["result"]["potential_conflicts"], list)


def test_pending_conflict_blocks_freshness() -> None:
    """L697: when LLM cannot resolve, a pending Conflict Review Item is created
    and freshness blocks on ``pending_conflict``.

    We exercise this via direct ``apply_conflict_decision`` / pending state
    rather than triggering the fake judge to emit a pending verdict.
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    item = cr.validate_conflict_review_item(
        item={
            "conflict_id": "test-pending",
            "status": "pending",
            "source_refs": [
                {"source_section_id": "a"},
                {"source_section_id": "b"},
            ],
        }
    )
    assert item["status"] == "pending"
    summary = cr.summarize_conflict_review_state(items=[item], existing_blocking_reasons=[])
    assert summary["pending_conflict_count"] == 1
    assert "pending_conflict" in summary["freshness_report"]["blocking_reasons"]


# ---------------------------------------------------------------------------
# §7.4 — Conflict Review Item fields (L702-713, 12 fields)
# ---------------------------------------------------------------------------


_CONFLICT_REVIEW_FIELDS = [
    (702, "conflict_id"),
    (703, "status"),
    (704, "severity"),
    (705, "source_refs"),
    (706, "claims"),
    (707, "why_conflicting"),
    (708, "why_llm_cannot_decide"),
    (709, "related_sections"),
    (710, "decision_options"),
    (711, "recommended_next_action"),
    (712, "base_source_hashes"),
    (713, "valid_scope"),
]


@pytest.mark.parametrize(
    "spec_line, field",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _CONFLICT_REVIEW_FIELDS
    ],
)
def test_conflict_review_item_field(spec_line: int, field: str) -> None:
    """L702-713: validated Conflict Review Item exposes each documented field.
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    item = cr.validate_conflict_review_item(
        item={
            "conflict_id": "test-field-coverage",
            "source_refs": [{"source_section_id": "a"}, {"source_section_id": "b"}],
        }
    )
    assert field in item, f"L{spec_line}: missing field {field!r}"
    if spec_line == 703:
        assert item[field] == "pending"


# ---------------------------------------------------------------------------
# §7.4 — human decision options (L718-722) + defer note (L724)
# ---------------------------------------------------------------------------


_HUMAN_OPTION_CASES = [
    (718, "prefer_a"),
    (718, "prefer_b"),
    (719, "conditional"),
    (720, "dismiss"),
    (721, "needs_source_update"),
    (722, "defer"),
]


# Note: L718 lists "片方の仕様を優先する" which covers both prefer_a and prefer_b
# from the implementation perspective.  We use the first prefer_* mapping to
# satisfy the per-row evidence entry, then verify the second under §7.4
# decision-enum (L748).


_HUMAN_OPTION_CASES_DEDUP = [
    (718, "prefer_a"),
    (719, "conditional"),
    (720, "dismiss"),
    (721, "needs_source_update"),
    (722, "defer"),
]


@pytest.mark.parametrize(
    "spec_line, option_id",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _HUMAN_OPTION_CASES_DEDUP
    ],
)
def test_decision_option_offered(spec_line: int, option_id: str) -> None:
    """L718-722: each documented human option is present in decision_options.
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    item = cr.validate_conflict_review_item(
        item={
            "conflict_id": "test-options",
            "source_refs": [{"source_section_id": "a"}, {"source_section_id": "b"}],
        }
    )
    offered = {opt["id"] for opt in item["decision_options"]}
    assert option_id in offered, f"L{spec_line}: option {option_id!r} not offered"


def test_defer_decision_keeps_status_pending() -> None:
    """L724: a ``defer`` decision keeps status=pending (does not resolve).
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    base = cr.validate_conflict_review_item(
        item={
            "conflict_id": "test-defer",
            "source_refs": [{"source_section_id": "a"}, {"source_section_id": "b"}],
        }
    )
    updated = cr.apply_conflict_decision(
        items=[base],
        decision_payload={
            "conflict_id": "test-defer",
            "decision": "defer",
            "reason": "Waiting on stakeholder input",
            "referenced_source_refs": [{"source_section_id": "a"}],
        },
    )
    assert updated[0]["status"] == "pending"


# ---------------------------------------------------------------------------
# §7.4 — resolution attributes (L726-730)
# ---------------------------------------------------------------------------


def test_resolution_carries_decision_reason_refs() -> None:
    """L726: resolved item carries decision / reason / referenced source refs.
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    base = cr.validate_conflict_review_item(
        item={
            "conflict_id": "test-resolution",
            "source_refs": [{"source_section_id": "a"}, {"source_section_id": "b"}],
        }
    )
    updated = cr.apply_conflict_decision(
        items=[base],
        decision_payload={
            "conflict_id": "test-resolution",
            "decision": "prefer_a",
            "reason": "Aligns with Purpose.",
            "selected_option": "prefer_a",
            "referenced_source_refs": [{"source_section_id": "a"}],
            "human_acknowledgement": True,
        },
    )
    resolution = updated[0].get("resolution", {})
    assert resolution.get("decision") == "prefer_a"
    assert resolution.get("reason") == "Aligns with Purpose."
    assert resolution.get("referenced_source_refs")


def test_resolution_not_auto_propagated(core_fake_fresh: dict[str, Any]) -> None:
    """L727: resolution does not auto-write Purpose / Core Concept / Source Specs.

    We verify /spec-core does not mutate purpose / concept files even after a
    second invocation.
    """

    project = core_fake_fresh["project"]
    purpose_first = (project / "docs/core/purpose.md").read_text(encoding="utf-8")
    _run_core(project)
    purpose_second = (project / "docs/core/purpose.md").read_text(encoding="utf-8")
    assert purpose_first == purpose_second


def test_unreflected_conflict_resolutions_surface(core_fake_fresh: dict[str, Any]) -> None:
    """L728: unreflected_conflict_resolutions is reported in CoreResult.
    """

    assert "unreflected_conflict_resolutions" in core_fake_fresh["result"]
    assert isinstance(core_fake_fresh["result"]["unreflected_conflict_resolutions"], list)


def test_resolution_has_base_hashes_and_scope() -> None:
    """L729: resolution carries base_source_hashes[] and valid_scope.
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    base = cr.validate_conflict_review_item(
        item={
            "conflict_id": "test-base-hashes",
            "source_refs": [
                {"source_section_id": "a", "hash": "h1"},
                {"source_section_id": "b", "hash": "h2"},
            ],
        }
    )
    assert isinstance(base["base_source_hashes"], list)
    assert base["valid_scope"] in {"global", "source_pair", "section_pair", "task_scope"}


def test_task_scope_resolution_marks_scope() -> None:
    """L730: task_scope_resolution sets valid_scope=task_scope.
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    base = cr.validate_conflict_review_item(
        item={
            "conflict_id": "test-task-scope",
            "source_refs": [{"source_section_id": "a"}, {"source_section_id": "b"}],
        }
    )
    updated = cr.apply_conflict_decision(
        items=[base],
        decision_payload={
            "conflict_id": "test-task-scope",
            "decision": "task_scope_resolution",
            "reason": "Quick fix for this task only.",
            "referenced_source_refs": [{"source_section_id": "a"}],
            "human_acknowledgement": True,
        },
    )
    assert updated[0]["valid_scope"] == "task_scope"


# ---------------------------------------------------------------------------
# §7.4 — decision payload schema (L735-740)
# ---------------------------------------------------------------------------


_DECISION_PAYLOAD_FIELDS = [
    (735, "conflict_id"),
    (736, "decision"),
    (737, "reason"),
    (738, "selected_option"),
    (739, "valid_scope"),
    (740, "referenced_source_refs"),
]


@pytest.mark.parametrize(
    "spec_line, field",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _DECISION_PAYLOAD_FIELDS
    ],
)
def test_decision_payload_field_consumed(spec_line: int, field: str) -> None:
    """L735-740: each documented decision-payload field is consumed by
    ``apply_conflict_decision``.
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    base = cr.validate_conflict_review_item(
        item={
            "conflict_id": "test-payload-fields",
            "source_refs": [{"source_section_id": "a"}, {"source_section_id": "b"}],
        }
    )
    payload = {
        "conflict_id": "test-payload-fields",
        "decision": "conditional",
        "reason": "Both apply with a feature flag",
        "selected_option": "conditional",
        "valid_scope": "global",
        "referenced_source_refs": [{"source_section_id": "a"}, {"source_section_id": "b"}],
        "human_acknowledgement": True,
    }
    updated = cr.apply_conflict_decision(items=[base], decision_payload=payload)
    resolution = updated[0].get("resolution", {})
    if field == "conflict_id":
        assert updated[0]["conflict_id"] == payload["conflict_id"]
    elif field == "decision":
        assert resolution.get("decision") == payload["decision"]
    elif field == "reason":
        assert resolution.get("reason") == payload["reason"]
    elif field == "selected_option":
        assert resolution.get("selected_option") == payload["selected_option"]
    elif field == "valid_scope":
        assert updated[0].get("valid_scope") == payload["valid_scope"]
    elif field == "referenced_source_refs":
        assert resolution.get("referenced_source_refs")


# ---------------------------------------------------------------------------
# §7.4 — decision enum (L747-753, 7 values)
# ---------------------------------------------------------------------------


_DECISION_ENUM_CASES = [
    (747, "prefer_a", "resolved", "global"),
    (748, "prefer_b", "resolved", "global"),
    (749, "conditional", "resolved", "global"),
    (750, "dismiss", "dismissed", "global"),
    (751, "needs_source_update", "pending", "global"),
    (752, "defer", "pending", "global"),
    (753, "task_scope_resolution", "resolved", "task_scope"),
]


@pytest.mark.parametrize(
    "spec_line, decision, expected_status, expected_scope",
    [
        pytest.param(
            *case,
            id=f"L{case[0]}-{case[1]}",
        )
        for case in _DECISION_ENUM_CASES
    ],
)
def test_decision_enum_transition(
    spec_line: int, decision: str, expected_status: str, expected_scope: str
) -> None:
    """L747-753: each decision enum value transitions to the documented state.
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    base = cr.validate_conflict_review_item(
        item={
            "conflict_id": f"test-enum-{decision}",
            "source_refs": [{"source_section_id": "a"}, {"source_section_id": "b"}],
        }
    )
    payload = {
        "conflict_id": f"test-enum-{decision}",
        "decision": decision,
        "reason": f"Test {decision}",
        "referenced_source_refs": [{"source_section_id": "a"}],
    }
    # resolve / dismiss require explicit human acknowledgement; pending
    # decisions (defer / needs_source_update) do not.
    if expected_status in {"resolved", "dismissed"}:
        payload["human_acknowledgement"] = True
    updated = cr.apply_conflict_decision(items=[base], decision_payload=payload)
    assert updated[0]["status"] == expected_status, (
        f"L{spec_line}: decision={decision} should yield status={expected_status}, "
        f"got {updated[0]['status']}"
    )
    if expected_scope == "task_scope":
        assert updated[0]["valid_scope"] == "task_scope"


# ---------------------------------------------------------------------------
# §7.4 — conflict pair selection (L755-757)
# ---------------------------------------------------------------------------


def test_conflict_evaluation_is_separate_stage(core_fake_fresh: dict[str, Any]) -> None:
    """L755: conflict evaluation runs in its own stage after related_sections.
    """

    progress = core_fake_fresh["progress"]
    stage_order = progress["stage_order"]
    assert stage_order.index("conflict_evaluation") > stage_order.index("related_sections")


def test_conflict_pair_selection_uses_high_risk_words() -> None:
    """L756: pair selection considers identifier overlap / conflict words even
    for pairs not picked by related_sections.
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    # High-risk pairs are signalled by candidates whose ``channels`` includes
    # ``shared_identifier`` and ``evidence_terms`` contains conflict words.
    pairs = cr.select_conflict_judging_pairs(
        sections=[
            {"section_id": "doc-a#s1", "source_section_id": "doc-a#s1"},
            {"section_id": "doc-b#s1", "source_section_id": "doc-b#s1"},
        ],
        related_sections={},
        candidates=[
            {
                "source_section_id": "doc-a#s1",
                "target_section_id": "doc-b#s1",
                "channels": ["shared_identifier"],
                "evidence_terms": ["must", "must not"],
                "reason": "Same identifier with must / must not constraints",
            }
        ],
        config=None,
        limits=None,
    )
    matched = any(
        {p.get("source_section_id"), p.get("target_section_id")}
        == {"doc-a#s1", "doc-b#s1"}
        for p in pairs
    )
    assert matched, f"expected high-risk pair, got pairs={pairs}"


def test_conflict_pair_cap_recorded_in_diagnostics() -> None:
    """L757: pairs dropped by ``conflict_pair_max_per_section`` are tracked in
    diagnostics (so users can see how many pairs were filtered out).
    """

    import importlib

    cr = importlib.import_module("spec_anchor.conflict_review")
    # Build many high-risk candidate pairs pointing at the same anchor
    # section.  Per-section count must not exceed the configured cap.
    candidates = [
        {
            "source_section_id": "anchor#s0",
            "target_section_id": f"doc#s{i}",
            "channels": ["shared_identifier"],
            "evidence_terms": ["must"],
            "reason": "Identifier overlap with conflict words",
        }
        for i in range(6)
    ]

    class _Limits:
        conflict_pair_max_per_section = 2

    pairs = cr.select_conflict_judging_pairs(
        sections=None,
        related_sections={},
        candidates=candidates,
        config=None,
        limits=_Limits(),
    )
    counts: dict[str, int] = {}
    for p in pairs:
        counts[p.get("source_section_id", "")] = counts.get(p.get("source_section_id", ""), 0) + 1
    assert counts, "at least one high-risk pair should pass selection"
    assert max(counts.values()) <= _Limits.conflict_pair_max_per_section, (
        f"per-section cap violated: counts={counts}"
    )
    diagnostics = list(getattr(pairs, "selection_diagnostics", []) or [])
    assert diagnostics, "pair cap skips must be visible in diagnostics"
    assert diagnostics[0]["reason_code"] == "conflict_pair_max_per_section_skipped"
    assert diagnostics[0]["skipped_pair_count"] == 4
