"""Phase H-4: model / effort calibration scaffolding.

These tests exercise the actual `claude` CLI against representative
SPEC-grag prompts to measure schema validation pass rate, required-field
fill rate, and per-call latency for each (stage, model, effort) cell of
the calibration matrix documented in
`doc/CALIBRATION_MODEL_EFFORT.ja.md`.

The tests are gated behind `SPEC_GRAG_LOCAL_SERVICE=1` because they
incur real LLM cost and require the `claude` console script on PATH.
Run them when calibrating; their results feed the doc tables that drive
the production model / effort selection.

The current scaffolding skips by default and only documents the matrix
shape. Implementing the real measurement loop is left to the operator
who runs calibration; the contract pinned here is:

- Each parametrised test asserts that the configured (model, effort)
  combination produces a single JSON object output that satisfies the
  stage's required schema fields.
- Failures should be diagnosed with the per-call latency and raw output
  excerpts captured in the test report.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


pytestmark = pytest.mark.external


def _local_service_enabled() -> bool:
    return os.environ.get("SPEC_GRAG_LOCAL_SERVICE", "").lower() in {"1", "true", "yes", "on"}


def _claude_available() -> bool:
    return shutil.which("claude") is not None


CALIBRATION_MATRIX = [
    # (stage, model, effort)
    ("section_metadata", "claude-haiku-4-5", "low"),
    ("section_metadata", "claude-haiku-4-5", "medium"),
    ("section_metadata", "claude-sonnet-4-6", "low"),
    ("related_sections", "claude-haiku-4-5", "low"),
    ("related_sections", "claude-haiku-4-5", "medium"),
    ("related_sections", "claude-sonnet-4-6", "medium"),
    ("conflict_review", "claude-haiku-4-5", "medium"),
    ("conflict_review", "claude-sonnet-4-6", "medium"),
    ("conflict_review", "claude-opus-4-7", "medium"),
]


@pytest.mark.parametrize("stage,model,effort", CALIBRATION_MATRIX)
def test_calibrate_stage_model_effort(stage: str, model: str, effort: str) -> None:
    """Per-cell calibration. Skipped unless local-service profile is enabled.

    The full measurement implementation is the operator's responsibility
    during calibration runs. This test currently asserts only that the
    matrix cell is reachable (claude CLI on PATH) and skips otherwise so
    the matrix shape stays visible in pytest collection.
    """

    if not _local_service_enabled():
        pytest.skip(
            "SPEC_GRAG_LOCAL_SERVICE=1 not set; calibration matrix is documentation-only "
            "until an operator runs the real-call evaluation"
        )
    if not _claude_available():
        pytest.skip("`claude` CLI not on PATH; calibration cell is unreachable")

    # Operator: implement the measurement loop here. At minimum:
    # 1. Build a representative prompt for `stage` (use existing fixtures
    #    in tests/test_section_metadata_generation.py and
    #    tests/test_related_sections.py).
    # 2. Invoke `claude --print --model <model> --effort <effort> ...`.
    # 3. Validate the resulting JSON against the stage's expected fields.
    # 4. Record the latency / pass-rate in
    #    doc/CALIBRATION_MODEL_EFFORT.ja.md.
    pytest.skip(
        "calibration measurement loop not implemented; see "
        "doc/CALIBRATION_MODEL_EFFORT.ja.md for the procedure"
    )


def test_calibration_matrix_is_complete() -> None:
    """Regression guard: every documented stage has at least one cell."""

    stages = {entry[0] for entry in CALIBRATION_MATRIX}
    assert stages == {"section_metadata", "related_sections", "conflict_review"}
