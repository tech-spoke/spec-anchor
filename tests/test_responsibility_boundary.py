"""Tests for §5.3 CLI / SPEC-anchor responsibility boundary (negative side).

Each test verifies a "CLI does NOT do X" claim from
``doc/EXTERNAL_DESIGN.ja.md`` §5.3. Positive responsibilities ("CLI DOES
generate Section Metadata", etc.) are checked by component-level tests
elsewhere (``test_section_metadata_generation.py``,
``test_conflict_review.py`` …); their SPEC_REF backfill happens in
those files.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_main(module: str, func_name: str, argv: list[str]) -> int:
    """Invoke a top-level ``_main`` function in-process with the given argv.

    Returns the exit code. ``SystemExit`` from ``argparse`` / ``sys.exit`` is
    captured and returned as an int.
    """

    import importlib

    mod = importlib.import_module(module)
    func = getattr(mod, func_name)
    saved = sys.argv
    sys.argv = [func_name.replace("_main", ""), *argv]
    try:
        result = func(argv)
        if isinstance(result, int):
            return result
        return 0
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        sys.argv = saved


def _setup_project(target: Path) -> None:
    code = _run_main(
        "spec_anchor.cli",
        "setup_project_main",
        ["--target", str(target), "--agent", "both"],
    )
    assert code == 0, f"setup-project exited {code}"


def _run_spec_anchor(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run ``spec-anchor`` (the main CLI) as a subprocess."""

    return subprocess.run(
        [sys.executable, "-m", "spec_anchor", *args],
        cwd=cwd if cwd is not None else REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _cli_help_text(*args: str) -> str:
    result = _run_spec_anchor(*args, "--help")
    assert result.returncode == 0, (
        f"`spec-anchor {' '.join(args)} --help` exited {result.returncode}: "
        f"stderr={result.stderr!r}"
    )
    return result.stdout


def test_cli_does_not_accept_conversation_transcript_argument() -> None:
    """CLI does not consume conversation transcript / prompt as input.

    Verifies that none of the ``spec-anchor`` subcommands declare a flag
    that takes a free-form conversation transcript or full task prompt as
    a single argument. The contract is that the Agent interprets the
    conversation and feeds structured inputs (a search query, a section
    id, or a constructed answer JSON) to the CLI.

    SPEC_REF: §5.3 L411
    PROFILE: none
    METHOD: 入出力比較
    """

    forbidden_flags = {
        "--conversation",
        "--transcript",
        "--prompt-full",
        "--task-prompt",
        "--user-message",
    }
    for sub in (
        "inject-search",
        "inject-section",
        "inject-chapters",
        "inject-purpose",
        "inject-conflicts",
        "realign",
        "core",
    ):
        help_text = _cli_help_text(sub)
        for flag in forbidden_flags:
            assert flag not in help_text, (
                f"`spec-anchor {sub}` exposes forbidden conversation flag {flag!r}; "
                f"§5.3 requires CLI not to consume the conversation transcript."
            )


def test_cli_does_not_expose_auto_exploration_command() -> None:
    """CLI exposes no command that runs Agentic Search autonomously.

    Verifies that ``spec-anchor --help`` lists only single-shot retrieval
    primitives (``inject-search`` / ``inject-section`` / ``inject-chapters``
    / ``inject-purpose`` / ``inject-conflicts``) plus ``core`` / ``realign``
    / ``watch``, and exposes no ``auto-explore`` / ``walk`` / ``traverse``
    style subcommand. Recursive related-section lookup is the Agent's job.

    SPEC_REF: §5.3 L412
    PROFILE: none
    METHOD: 入出力比較
    """

    help_text = _cli_help_text()
    forbidden_subcommands = {
        "auto-explore",
        "agentic-search",
        "walk",
        "traverse",
        "explore",
    }
    for sub in forbidden_subcommands:
        # The argparse listing shows subcommands as their own help row.
        assert sub not in help_text.split(), (
            f"`spec-anchor --help` lists forbidden subcommand {sub!r}"
        )


def test_inject_search_output_does_not_contain_fabricated_constraints(tmp_path: Path) -> None:
    """`spec-anchor inject-search` returns raw retrieval payload, not
    fabricated constraint statements.

    The contract per §5.3 L413 is that the CLI provides retrieval data
    (heading_path / summary / search_keys / identifiers / related_sections /
    score) and the Agent composes constraint statements. The CLI's output
    must therefore contain no ``"statement":`` / ``"constraints":`` field
    populated with synthesised text.

    SPEC_REF: §5.3 L413
    PROFILE: fake
    METHOD: 入出力比較
    """

    project = tmp_path / "no-fallback-probe"
    project.mkdir()
    _setup_project(project)
    # Provide minimal Source Specs so freshness gate has something to evaluate.
    (project / "docs" / "spec").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "spec" / "main.md").write_text(
        "# Main\n\n## Overview\n\nThis is the overview section.\n",
        encoding="utf-8",
    )

    result = _run_spec_anchor("inject-search", "overview", cwd=project)
    # Output may be a freshness-gate stop (no /spec-core yet) or a payload
    # response. Either way, no synthesised constraint statements should
    # appear in stdout.
    if result.stdout.strip():
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            pytest.fail(f"inject-search stdout was not JSON: {result.stdout!r}")
        # `payload` must not contain a top-level non-empty `constraints`
        # array (that would mean the CLI fabricated constraints).
        constraints = payload.get("constraints")
        assert constraints in (None, []), (
            f"inject-search returned `constraints` field with content: {constraints!r}; "
            "§5.3 forbids CLI from generating constraints."
        )
        # `statement` field anywhere in top-level output would also be a
        # fabrication signal.
        flattened = json.dumps(payload, ensure_ascii=False)
        assert '"statement":' not in flattened, (
            "inject-search output contains a `statement` field, suggesting "
            "a fabricated constraint."
        )


def test_inject_conflicts_does_not_auto_resolve_pending_status(tmp_path: Path) -> None:
    """CLI never flips a `pending` Conflict Review Item to `resolved`
    automatically.

    Seeds ``conflict_review_items.json`` with a ``status: pending`` entry,
    runs ``spec-anchor inject-conflicts``, and verifies the on-disk
    artifact is unchanged afterwards.

    SPEC_REF: §5.3 L414
    PROFILE: fake
    METHOD: artifact 内容確認
    """

    project = tmp_path / "conflict-autoresolve-probe"
    project.mkdir()
    _setup_project(project)

    conflict_path = project / ".spec-anchor" / "context" / "conflict_review_items.json"
    conflict_path.parent.mkdir(parents=True, exist_ok=True)
    pending_item = {
        "items": [
            {
                "conflict_id": "cnf_test_pending",
                "status": "pending",
                "severity": "medium",
                "source_refs": ["docs/spec/main.md#0001-overview"],
                "claims": ["claim a", "claim b"],
                "why_conflicting": "test fixture",
                "why_llm_cannot_decide": "test fixture",
                "decision_options": ["option_a", "option_b"],
                "recommended_next_action": "Ask a human to decide this conflict.",
            }
        ]
    }
    conflict_path.write_text(json.dumps(pending_item), encoding="utf-8")
    before = conflict_path.read_bytes()

    _run_spec_anchor("inject-conflicts", cwd=project)

    after = conflict_path.read_bytes()
    assert before == after, (
        "CLI mutated `conflict_review_items.json` during `inject-conflicts`; "
        "§5.3 forbids CLI from auto-resolving a pending conflict."
    )


def test_realign_without_answer_does_not_generate_free_form_answer(tmp_path: Path) -> None:
    """`spec-anchor realign` only formats Agent-supplied answers; it never
    composes one from scratch.

    Invokes ``spec-anchor realign`` without any ``--answer*`` flag. The CLI
    must report a needs-answer signal rather than emit a populated
    ``answer`` field in the output JSON.

    SPEC_REF: §5.3 L415
    PROFILE: fake
    METHOD: 入出力比較
    """

    project = tmp_path / "realign-noanswer"
    project.mkdir()
    _setup_project(project)

    result = _run_spec_anchor("realign", cwd=project)
    combined = result.stdout + result.stderr
    assert (
        "needs_agent_answer" in combined
        or "agent_answer is required" in combined
        or "should_stop" in combined
        or "blocking_reasons" in combined
    ), (
        f"`spec-anchor realign` produced output without a stop signal: {combined!r}"
    )
    # Stronger: stdout must not contain a populated `answer` body. A null
    # / empty answer is allowed (it's the absence-of-output signal).
    if result.stdout.strip():
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {}
        answer = payload.get("answer")
        assert answer in (None, "", {}, []), (
            f"`spec-anchor realign` returned populated `answer` field {answer!r} "
            "without Agent-supplied --answer-* input."
        )


def test_spec_core_does_not_modify_purpose_or_concept_files(tmp_path: Path) -> None:
    """`/spec-core` must never write to ``purpose_file`` / ``concept_file``.

    Captures the pre-run bytes of Purpose and Core Concept files, runs
    ``spec-anchor core`` against a setup project, and asserts byte-for-byte
    equality afterwards. ``/spec-core`` should only generate state /
    context artifacts under ``.spec-anchor/``.

    SPEC_REF: §5.3 L416
    PROFILE: fake
    METHOD: artifact 内容確認
    """

    project = tmp_path / "core-readonly-probe"
    project.mkdir()
    _setup_project(project)
    # Provide minimal Source Specs so /spec-core has work to do.
    (project / "docs" / "spec").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "spec" / "main.md").write_text(
        "# Main\n\n## Overview\n\nOverview body.\n",
        encoding="utf-8",
    )

    config_text = (project / ".spec-anchor" / "config.toml").read_text(encoding="utf-8")
    config = tomllib.loads(config_text)
    purpose = project / config["core"]["purpose_file"]
    concept = project / config["core"]["concept_file"]

    assert purpose.exists(), f"Purpose file should be initialised: {purpose}"
    assert concept.exists(), f"Core Concept file should be initialised: {concept}"
    purpose_before = purpose.read_bytes()
    concept_before = concept.read_bytes()

    _run_spec_anchor("core", cwd=project)

    assert purpose.read_bytes() == purpose_before, (
        f"`spec-anchor core` mutated Purpose file {purpose}; §5.3 L416 forbids this."
    )
    assert concept.read_bytes() == concept_before, (
        f"`spec-anchor core` mutated Core Concept file {concept}; §5.3 L416 forbids this."
    )
