"""E2E gate for slash-command user-facing output (課題 #11 infra).

Three families of checks:

1. ``test_snapshot_has_no_forbidden_terms`` — every evidence snapshot under
   ``snapshots/`` is free of CLI-internal vocabulary (field names, enum values,
   pipeline stage names). This is the cross-cutting禁止用語 contract (#2-s08 /
   #8-s07 / #7-s01) applied to every snapshot at once.
2. ``test_scenario_snapshot_has_required_content`` — each registered scenario's
   snapshot exists and contains the human-facing content the scenario proves.
3. ``test_cli_stdout_is_single_json_object`` and
   ``test_library_stdout_noise_is_redirected`` — the #9 stdout contract: a
   ``spec-anchor`` command prints exactly one JSON object to stdout, and any
   library output produced while the command runs is routed to stderr.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec_anchor import cli
from tests.e2e.forbidden_terms import find_forbidden_terms
from tests.e2e.scenarios import SCENARIOS, SCENARIOS_BY_ID

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"

_USER_FACING = [s for s in SCENARIOS if s.kind == "user_facing"]
_CLI_JSON = [s for s in SCENARIOS if s.kind == "cli_json"]


def test_every_snapshot_file_is_registered() -> None:
    """No orphan evidence: every ``snapshots/*.md`` belongs to a scenario."""

    registered = {s.snapshot for s in SCENARIOS}
    on_disk = {p.name for p in SNAPSHOTS_DIR.glob("*.md")}
    orphans = sorted(on_disk - registered)
    assert not orphans, f"unregistered snapshot files: {orphans}"


def _reply_body(text: str) -> str:
    """Return the user-facing reply portion of a snapshot.

    A user_facing snapshot starts with a meta header (what the scenario proves)
    followed by a ``---`` separator and then the actual Agent reply. The header
    may legitimately name internal vocabulary while *describing* the contract
    (e.g. "evidence_origin を「根拠の種類」へ翻訳"); only the reply below ``---``
    is the user-facing text the forbidden-term contract applies to. If there is
    no separator, the whole file is treated as the reply.
    """

    for sep in ("\n---\n", "\n---"):
        idx = text.find(sep)
        if idx != -1:
            return text[idx + len(sep):]
    return text


@pytest.mark.parametrize("scenario", _USER_FACING, ids=lambda s: s.scenario_id)
def test_snapshot_has_no_forbidden_terms(scenario) -> None:
    text = _reply_body((SNAPSHOTS_DIR / scenario.snapshot).read_text(encoding="utf-8"))
    hits = find_forbidden_terms(text, allow=scenario.allow)
    assert not hits, (
        f"{scenario.scenario_id} ({scenario.snapshot}) leaks CLI-internal "
        f"vocabulary into user-facing output: {hits}"
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.scenario_id)
def test_scenario_snapshot_has_required_content(scenario) -> None:
    snapshot_path = SNAPSHOTS_DIR / scenario.snapshot
    assert snapshot_path.is_file(), (
        f"scenario {scenario.scenario_id} is missing its evidence snapshot "
        f"{scenario.snapshot}"
    )
    text = snapshot_path.read_text(encoding="utf-8")
    missing = [needle for needle in scenario.required if needle not in text]
    assert not missing, (
        f"scenario {scenario.scenario_id} snapshot is missing required "
        f"human-facing content: {missing}"
    )


@pytest.mark.parametrize("scenario", _CLI_JSON, ids=lambda s: s.scenario_id)
def test_cli_json_snapshot_is_single_json_object(scenario) -> None:
    """A #9 evidence snapshot embeds the captured CLI stdout as a single JSON object.

    The snapshot stores the real ``spec-anchor`` stdout inside a fenced ```json
    block; the contract under test (#9) is that the captured stdout parses as
    exactly one JSON object with no surrounding library noise.
    """

    text = (SNAPSHOTS_DIR / scenario.snapshot).read_text(encoding="utf-8")
    payload = _extract_json_block(text)
    parsed = json.loads(payload)
    assert isinstance(parsed, dict) and parsed, (
        f"{scenario.scenario_id} stdout is not a single non-empty JSON object"
    )


def _extract_json_block(text: str) -> str:
    marker = "```json"
    start = text.index(marker) + len(marker)
    end = text.index("```", start)
    return text[start:end].strip()


# --- #9 stdout contract ------------------------------------------------------

# Commands whose error path needs no external service: an absent
# `.spec-anchor/config.toml` makes them return a structured error JSON. They are
# enough to prove "stdout holds exactly one JSON object" without Qdrant / a model.
_NO_SERVICE_COMMANDS = (
    ["inject-purpose"],
    ["inject-conflicts"],
    ["inject-chapters"],
    ["inject-section", "0001-some-section"],
    ["inject-search", "example", "query"],
    ["realign", "--answer-text", "hello"],
)


@pytest.mark.parametrize(
    "argv",
    _NO_SERVICE_COMMANDS,
    ids=lambda a: a[0],
)
def test_cli_stdout_is_single_json_object(argv, tmp_path, monkeypatch, capsys) -> None:
    """`spec-anchor <cmd>` prints exactly one JSON object to stdout (#9-s01..s07).

    Run in an empty project dir so the command takes its config-absent error
    path; the contract under test is the stdout shape, not the command success.
    """

    monkeypatch.chdir(tmp_path)
    cli.main(argv)
    out = capsys.readouterr().out
    parsed = json.loads(out)  # raises if stdout is not a single JSON object
    assert isinstance(parsed, dict)
    assert parsed.get("command")


def test_library_stdout_noise_is_redirected(tmp_path, monkeypatch, capsys) -> None:
    """Library stdout writes during a command body never reach the result stdout.

    `inject-purpose`'s real runner is monkeypatched so its body prints the kind
    of progress noise FlagEmbedding / HuggingFace emit. After ``main`` returns,
    stdout must still parse as a single JSON object and contain none of the
    noise lines (they were redirected to stderr).
    """

    monkeypatch.chdir(tmp_path)
    noise = (
        "Warning: You are sending unauthenticated requests to the HF Hub.\n"
        "Fetching 30 files: 100%|##########| 30/30 [00:00<00:00, 25784it/s]\n"
        "Loading weights: 100%|##########| 391/391 [00:00<00:00, 13333it/s]\n"
    )

    def _noisy_runner(args):
        import sys as _sys

        print(noise, file=_sys.stdout)  # library-style stdout write
        cli._emit_result_json({"command": "/spec-inject inject-purpose", "status": "fresh"})
        return 0

    monkeypatch.setattr(cli, "_run_inject_purpose_from_args", _noisy_runner)
    cli.main(["inject-purpose"])
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["command"] == "/spec-inject inject-purpose"
    assert "Fetching 30 files" not in captured.out
    assert "Loading weights" not in captured.out
    assert "unauthenticated requests" not in captured.out
    # The noise was redirected to stderr, proving the channel separation.
    assert "Fetching 30 files" in captured.err


# --- #10 templates mirror ----------------------------------------------------

import pytest as _pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIRRORED_COMMANDS = ("spec-inject.md", "spec-realign.md", "spec-core.md")


@_pytest.mark.parametrize("name", _MIRRORED_COMMANDS)
def test_template_command_matches_project(name: str) -> None:
    """#10-s01..s03: the install skeleton template equals the project command file."""

    project = (_REPO_ROOT / ".claude" / "commands" / name).read_text(encoding="utf-8")
    template = (
        _REPO_ROOT / "spec_anchor" / "templates" / ".claude" / "commands" / name
    ).read_text(encoding="utf-8")
    assert project == template, (
        f"{name} differs between .claude/commands/ and spec_anchor/templates/"
    )


def test_codex_skill_has_user_facing_output_contract() -> None:
    """#10-s04: the Codex SKILL.md mirrors the user-facing output vocabulary."""

    skill = (
        _REPO_ROOT
        / "spec_anchor" / "templates" / ".codex" / "skills" / "spec-anchor" / "SKILL.md"
    ).read_text(encoding="utf-8")
    for needle in (
        "停止時のユーザー向け出力フォーマット",
        "pending conflict の本文展開フォーマット",
        "答案なし呼び出しの自動再実行",
        "ユーザー向け本文に貼ってはいけない内部用語",
        "正常完了時のユーザー向け出力フォーマット",
    ):
        assert needle in skill, f"SKILL.md is missing the section: {needle}"


# --- #7 external design §8.7 human-facing display contract -------------------

_EXTERNAL_DESIGN = _REPO_ROOT / "doc" / "EXTERNAL_DESIGN.ja.md"


def _section_8_7() -> str:
    text = _EXTERNAL_DESIGN.read_text(encoding="utf-8")
    start = text.index("### 8.7 人間向け表示契約")
    end = text.index("## 9. `/spec-realign`", start)
    return text[start:end]


def test_external_design_8_7_has_no_internal_field_names() -> None:
    """#7-s01: the §8.7 display contract uses user-experience language only.

    Per CLAUDE.md ルール 14 the external design must read for someone who never
    saw the source; the §8.7 contract text must not contain CLI-internal field
    names / enum values.
    """

    hits = find_forbidden_terms(_section_8_7())
    assert not hits, f"§8.7 leaks CLI-internal vocabulary: {hits}"


def test_external_design_8_7_covers_all_stop_categories() -> None:
    """#7-s02: §8.7 enumerates the same 6 + ◇ + ✕ categories as the templates (#1)."""

    body = _section_8_7()
    for marker in ("①", "②", "③", "④", "⑤", "⑥", "◇", "✕"):
        assert marker in body, f"§8.7 is missing stop category {marker}"


def test_external_design_8_7_describes_retry_policy() -> None:
    """#7-s03: §8.7 states the 1-retry-then-⑥ policy consistent with #6."""

    body = _section_8_7()
    assert "1 回だけ再実行" in body
    assert "差分" in body
