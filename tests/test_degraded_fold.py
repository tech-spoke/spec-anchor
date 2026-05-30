"""Tests for the degraded→failed fold (TODO #7 T-freshness-degraded-fold).

`degraded` is removed as a freshness status (status is now fresh / blocked /
failed). A `section_metadata` generation failure — whether every section failed
or only some batches failed — is a required-artifact failure that stops the
gate with `status="failed"`.
"""

from __future__ import annotations

from spec_anchor.core import _summarize_metadata_generation
from spec_anchor.freshness import STATUSES, build_freshness_report
from spec_anchor.section_metadata import SectionMetadataGeneration


def _generation(generated: list[str]) -> SectionMetadataGeneration:
    return SectionMetadataGeneration(
        artifact={},
        entries=[],
        diagnostics=[],
        llm_results=[],
        llm_calls=0,
        cache_hits=0,
        reused_section_ids=[],
        generated_section_ids=generated,
        batch_sizes=[],
    )


def test_no_degraded_status_value() -> None:
    assert "degraded" not in STATUSES
    assert STATUSES == {"fresh", "blocked", "failed"}


def test_full_section_metadata_failure_is_failed() -> None:
    summary = _summarize_metadata_generation(
        _generation(["s1", "s2"]),
        failed_section_ids={"s1", "s2"},
    )
    assert summary["freshness_status"] == "failed"
    assert summary["blocking_reasons"] == ["failed_required_artifact"]


def test_partial_section_metadata_failure_is_failed() -> None:
    # TODO #7: a partial batch failure no longer produces `degraded`; it folds
    # into `failed` like a full failure.
    summary = _summarize_metadata_generation(
        _generation(["s1", "s2"]),
        failed_section_ids={"s1"},
    )
    assert summary["freshness_status"] == "failed"
    assert summary["blocking_reasons"] == ["failed_required_artifact"]


def test_artifact_status_degraded_folds_to_failed_report() -> None:
    report = build_freshness_report(
        artifact_statuses={"section_metadata": "degraded"}
    )
    assert report["status"] == "failed"
    assert "failed_required_artifact" in report["blocking_reasons"]
