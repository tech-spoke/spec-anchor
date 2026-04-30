from __future__ import annotations

from pathlib import Path

import pytest

from spec_grag.concept_diff import (
    ConceptApplyStatus,
    ConceptDiffTaskContext,
    ConceptPatchApplyError,
    HunkStatus,
    PendingConceptDiff,
    PendingConceptHunk,
    accept_hunk,
    apply_pending_concept_diff,
    concept_file_hash,
    create_pending_concept_diff,
    load_pending_concept_diff,
    parse_hunk_ref,
    pending_concept_diff_path,
    reject_hunk,
    revise_hunk,
)
from spec_grag.protocol import Command


def make_pending_diff(concept_file: Path, *, diff_id: str = "diff-1") -> PendingConceptDiff:
    return PendingConceptDiff(
        diff_id=diff_id,
        base_concept_hash=concept_file_hash(concept_file),
        generated_at="2026-04-29T00:00:00+00:00",
        task_context=ConceptDiffTaskContext(
            command=Command.SPEC_CORE,
            changed_source_section_ids=["docs/spec/auth.md#auth"],
            extract_run_id="run-1",
        ),
        hunks=[
            PendingConceptHunk(
                hunk_id="hunk-1",
                file=str(concept_file),
                old_range="-1,3",
                new_range="+1,3",
                diff_text=(
                    "--- a/concept.md\n"
                    "+++ b/concept.md\n"
                    "@@ -1,3 +1,3 @@\n"
                    " # Concept\n"
                    "-Auth is optional.\n"
                    "+Auth is required.\n"
                    " Keep sessions short.\n"
                ),
            )
        ],
    )


def test_pending_concept_diff_roundtrip_and_hunk_statuses(tmp_path: Path) -> None:
    concept_file = tmp_path / "docs/core/concept.md"
    concept_file.parent.mkdir(parents=True)
    concept_file.write_text(
        "# Concept\nAuth is optional.\nKeep sessions short.\n",
        encoding="utf-8",
    )
    pending_dir = tmp_path / ".spec-grag/pending"
    diff = make_pending_diff(concept_file)

    path = create_pending_concept_diff(pending_dir, diff)
    loaded = load_pending_concept_diff(path)
    accepted = accept_hunk(loaded, "hunk-1")
    rejected = reject_hunk(accepted, "hunk-1")
    revised = revise_hunk(rejected, "hunk-1", "認証必須の根拠を短くする")

    assert path == pending_concept_diff_path(pending_dir, "diff-1")
    assert revised.hunks[0].status == HunkStatus.REVISED
    assert revised.hunks[0].revision_instruction == "認証必須の根拠を短くする"


def test_apply_pending_concept_diff_applies_only_accepted_hunks_and_removes_pending(
    tmp_path: Path,
) -> None:
    concept_file = tmp_path / "docs/core/concept.md"
    concept_file.parent.mkdir(parents=True)
    concept_file.write_text(
        "# Concept\nAuth is optional.\nKeep sessions short.\n",
        encoding="utf-8",
    )
    pending_path = tmp_path / ".spec-grag/pending/concept_diff_diff-1.json"
    diff = accept_hunk(make_pending_diff(concept_file), "hunk-1")

    result = apply_pending_concept_diff(
        diff,
        concept_file,
        remove_pending_path=pending_path,
    )

    assert result.status == ConceptApplyStatus.APPLIED
    assert result.applied_hunk_ids == ["hunk-1"]
    assert "Auth is required." in concept_file.read_text(encoding="utf-8")
    assert not pending_path.exists()


def test_apply_pending_concept_diff_blocks_on_hash_mismatch(tmp_path: Path) -> None:
    concept_file = tmp_path / "docs/core/concept.md"
    concept_file.parent.mkdir(parents=True)
    concept_file.write_text(
        "# Concept\nAuth is optional.\nKeep sessions short.\n",
        encoding="utf-8",
    )
    diff = accept_hunk(make_pending_diff(concept_file), "hunk-1")
    concept_file.write_text(
        "# Concept\nAuth was manually changed.\nKeep sessions short.\n",
        encoding="utf-8",
    )

    result = apply_pending_concept_diff(diff, concept_file)

    assert result.status == ConceptApplyStatus.BLOCKED
    assert result.blocked_reason == "base_concept_hash_mismatch"


def test_apply_pending_concept_diff_blocks_on_unresolved_hunks(tmp_path: Path) -> None:
    concept_file = tmp_path / "docs/core/concept.md"
    concept_file.parent.mkdir(parents=True)
    concept_file.write_text(
        "# Concept\nAuth is optional.\nKeep sessions short.\n",
        encoding="utf-8",
    )
    diff = make_pending_diff(concept_file)

    result = apply_pending_concept_diff(diff, concept_file)

    assert result.status == ConceptApplyStatus.BLOCKED
    assert result.blocked_reason == "unresolved_hunks:hunk-1"


def test_apply_pending_concept_diff_detects_hunk_mismatch(tmp_path: Path) -> None:
    concept_file = tmp_path / "docs/core/concept.md"
    concept_file.parent.mkdir(parents=True)
    concept_file.write_text(
        "# Concept\nAuth is optional.\nKeep sessions short.\n",
        encoding="utf-8",
    )
    diff = accept_hunk(make_pending_diff(concept_file), "hunk-1")
    broken = diff.model_copy(
        update={
            "hunks": [
                diff.hunks[0].model_copy(
                    update={
                        "diff_text": (
                            "@@ -1,3 +1,3 @@\n"
                            " # Concept\n"
                            "-Auth is forbidden.\n"
                            "+Auth is required.\n"
                            " Keep sessions short.\n"
                        )
                    }
                )
            ]
        }
    )

    with pytest.raises(ConceptPatchApplyError):
        apply_pending_concept_diff(broken, concept_file)


def test_parse_hunk_ref_requires_diff_and_hunk() -> None:
    assert parse_hunk_ref("diff-1:hunk-1") == ("diff-1", "hunk-1")
    with pytest.raises(ValueError):
        parse_hunk_ref("diff-1")
