"""Registry of E2E user-facing-output scenarios.

Each scenario ties a ``scenario_id`` (``#<subtask>-s<NN>``) to the evidence
snapshot under ``snapshots/`` and the human-facing content that snapshot must
contain. The pytest module :mod:`tests.e2e.test_user_facing_output` is driven
entirely by this registry, so adding a scenario means adding one entry here plus
its snapshot file.

Fields per :class:`Scenario`:

* ``snapshot`` — filename under ``snapshots/`` (the Agent-formatted final reply).
* ``required`` — substrings that must be present (human-facing content the
  scenario is meant to prove is shown).
* ``allow`` — forbidden substrings tolerated for this scenario, each justified.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    subtask: str
    summary: str
    snapshot: str
    required: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()
    # "user_facing": Agent-formatted reply — forbidden-term + required-content
    #   checked. "cli_json": raw CLI stdout JSON evidence — validated as a single
    #   JSON object, NOT forbidden-term checked (internal field names are the
    #   CLI's by design; the Agent translates them in the user_facing snapshots).
    kind: str = "user_facing"


SCENARIOS: tuple[Scenario, ...] = (
    # Scenarios are registered per-Phase as their evidence snapshots are
    # authored. #1〜#8 / #10 scenarios join this tuple when their sub task is
    # implemented (keeps the suite green at every phase commit).

    # --- #9 CLI stdout = single JSON object (raw CLI evidence) ----------------
    Scenario(
        "#9-s01", "#9", "spec-anchor core stdout が valid JSON 単体",
        "#9-s01_core_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s02", "#9", "spec-anchor inject-search stdout が valid JSON 単体",
        "#9-s02_inject_search_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s03", "#9", "spec-anchor inject-section stdout が valid JSON 単体",
        "#9-s03_inject_section_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s04", "#9", "spec-anchor inject-chapters stdout が valid JSON 単体",
        "#9-s04_inject_chapters_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s05", "#9", "spec-anchor inject-purpose stdout が valid JSON 単体",
        "#9-s05_inject_purpose_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s06", "#9", "spec-anchor inject-conflicts stdout が valid JSON 単体",
        "#9-s06_inject_conflicts_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s07", "#9", "spec-anchor realign stdout が valid JSON 単体",
        "#9-s07_realign_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s08", "#9", "stdout に HF / FlagEmbedding / progress bar 由来文字列が含まれない",
        "#9-s08_stdout_no_progress_noise.md", kind="note",
        required=("test_library_stdout_noise_is_redirected", "stderr"),
    ),
    Scenario(
        "#9-s09", "#9", "stderr 側に warning / progress 等が出ている (副作用確認)",
        "#9-s09_stderr_carries_noise.md", kind="note",
        required=("stderr", "Fetching 30 files"),
    ),
)


SCENARIOS_BY_ID = {scenario.scenario_id: scenario for scenario in SCENARIOS}
