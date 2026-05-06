"""Persistent Concept diff approval protocol."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from spec_grag.io import write_text_atomic as _write_text_atomic
from spec_grag.protocol import Command, StrictModel


class HunkStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVISED = "revised"


class ConceptDiffTaskContext(StrictModel):
    command: Command
    task_prompt: str | None = None
    changed_source_section_ids: list[str] = Field(default_factory=list)
    extract_run_id: str


class PendingConceptHunk(StrictModel):
    hunk_id: str
    file: str
    old_range: str
    new_range: str
    diff_text: str
    status: HunkStatus = HunkStatus.PENDING
    revision_instruction: str | None = None
    revision_history: list[str] = Field(default_factory=list)


class PendingConceptDiff(StrictModel):
    diff_id: str
    base_concept_hash: str
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    task_context: ConceptDiffTaskContext
    hunks: list[PendingConceptHunk]
    expires_at: str | None = None

    def by_hunk_id(self) -> dict[str, PendingConceptHunk]:
        return {hunk.hunk_id: hunk for hunk in self.hunks}


class ConceptApplyStatus(StrEnum):
    APPLIED = "applied"
    BLOCKED = "blocked"


class ConceptApplyResult(StrictModel):
    status: ConceptApplyStatus
    diff_id: str
    applied_hunk_ids: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    current_concept_hash: str | None = None


class ConceptDiffError(Exception):
    """Base error for Concept diff protocol failures."""


class ConceptDiffNotFoundError(ConceptDiffError):
    pass


class ConceptHunkNotFoundError(ConceptDiffError):
    pass


class ConceptPatchApplyError(ConceptDiffError):
    pass


_HUNK_HEADER_RE = re.compile(r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? ")
_SOURCE_MARKER_RE = re.compile(r"\(source:\s*(?P<source>[^)]+)\)")
_SOURCE_DERIVED_HEADING = "Source-derived concepts"


def concept_file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pending_concept_diff_path(pending_dir: Path, diff_id: str) -> Path:
    return pending_dir / f"concept_diff_{diff_id}.json"


def load_pending_concept_diff(path: Path) -> PendingConceptDiff:
    if not path.exists():
        raise ConceptDiffNotFoundError(f"pending Concept diff not found: {path}")
    return PendingConceptDiff.model_validate_json(path.read_text(encoding="utf-8"))


def first_unresolved_pending_concept_diff(pending_dir: Path) -> PendingConceptDiff | None:
    if not pending_dir.exists():
        return None
    for path in sorted(pending_dir.glob("concept_diff_*.json")):
        try:
            diff = load_pending_concept_diff(path)
        except ConceptDiffError:
            continue
        if pending_concept_diff_is_unresolved(diff):
            return diff
    return None


def pending_concept_diff_is_unresolved(diff: PendingConceptDiff) -> bool:
    return any(
        hunk.status
        in {HunkStatus.PENDING, HunkStatus.ACCEPTED, HunkStatus.REJECTED, HunkStatus.REVISED}
        for hunk in diff.hunks
    )


def write_pending_concept_diff_atomic(path: Path, diff: PendingConceptDiff) -> None:
    _write_text_atomic(path, diff.model_dump_json(indent=2) + "\n")


def create_pending_concept_diff(
    pending_dir: Path,
    diff: PendingConceptDiff,
) -> Path:
    path = pending_concept_diff_path(pending_dir, diff.diff_id)
    write_pending_concept_diff_atomic(path, diff)
    return path


def parse_hunk_ref(value: str) -> tuple[str, str]:
    diff_id, sep, hunk_id = value.partition(":")
    if not sep or not diff_id or not hunk_id:
        raise ValueError("hunk reference must be '<diff_id>:<hunk_id>'")
    return diff_id, hunk_id


def accept_hunk(diff: PendingConceptDiff, hunk_id: str) -> PendingConceptDiff:
    return update_hunk_status(diff, hunk_id, HunkStatus.ACCEPTED)


def reject_hunk(diff: PendingConceptDiff, hunk_id: str) -> PendingConceptDiff:
    return update_hunk_status(diff, hunk_id, HunkStatus.REJECTED)


def revise_hunk(
    diff: PendingConceptDiff, hunk_id: str, revision_instruction: str
) -> PendingConceptDiff:
    if not revision_instruction.strip():
        raise ValueError("revision_instruction is required")
    return update_hunk_status(
        diff,
        hunk_id,
        HunkStatus.REVISED,
        revision_instruction=revision_instruction,
    )


def regenerate_revised_hunks(
    diff: PendingConceptDiff,
    concept_file: Path,
    *,
    generated_at: str | None = None,
) -> PendingConceptDiff:
    updated_hunks: list[PendingConceptHunk] = []
    changed = False
    for hunk in diff.hunks:
        if hunk.status != HunkStatus.REVISED:
            updated_hunks.append(hunk)
            continue
        instruction = (hunk.revision_instruction or "").strip()
        if not instruction:
            updated_hunks.append(hunk)
            continue
        updated_hunks.append(
            build_revised_append_hunk(
                concept_file,
                hunk,
                revision_instruction=instruction,
                source_ref=_source_ref_for_revised_hunk(diff, hunk),
            )
        )
        changed = True
    if not changed:
        return diff
    return diff.model_copy(
        update={
            "generated_at": generated_at or datetime.now(UTC).isoformat(),
            "hunks": updated_hunks,
        }
    )


def build_revised_append_hunk(
    concept_file: Path,
    hunk: PendingConceptHunk,
    *,
    revision_instruction: str,
    source_ref: str,
) -> PendingConceptHunk:
    text = concept_file.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    old_start = len(lines) + 1
    prefix = [] if text.endswith("\n") or not text else ["\n"]
    new_lines = [
        *prefix,
        f"## {_SOURCE_DERIVED_HEADING}\n",
        "\n",
        f"- {revision_instruction} (source: {source_ref})\n",
    ]
    diff_lines = [
        f"--- a/{hunk.file}\n",
        f"+++ b/{hunk.file}\n",
        f"@@ -{old_start},0 +{old_start},{len(new_lines)} @@\n",
        *[f"+{line}" for line in new_lines],
    ]
    return hunk.model_copy(
        update={
            "old_range": f"-{old_start},0",
            "new_range": f"+{old_start},{len(new_lines)}",
            "diff_text": "".join(diff_lines),
            "status": HunkStatus.PENDING,
            "revision_instruction": None,
            "revision_history": [*hunk.revision_history, revision_instruction],
        }
    )


def _source_ref_for_revised_hunk(
    diff: PendingConceptDiff,
    hunk: PendingConceptHunk,
) -> str:
    match = _SOURCE_MARKER_RE.search(hunk.diff_text)
    if match:
        return match.group("source").strip()
    if diff.task_context.changed_source_section_ids:
        return ",".join(diff.task_context.changed_source_section_ids)
    return f"revision:{hunk.hunk_id}"


def update_hunk_status(
    diff: PendingConceptDiff,
    hunk_id: str,
    status: HunkStatus,
    *,
    revision_instruction: str | None = None,
) -> PendingConceptDiff:
    updated_hunks: list[PendingConceptHunk] = []
    found = False
    for hunk in diff.hunks:
        if hunk.hunk_id != hunk_id:
            updated_hunks.append(hunk)
            continue
        found = True
        updated_hunks.append(
            hunk.model_copy(
                update={
                    "status": status,
                    "revision_instruction": revision_instruction
                    if status == HunkStatus.REVISED
                    else None,
                }
            )
        )

    if not found:
        raise ConceptHunkNotFoundError(f"hunk not found: {hunk_id}")
    return diff.model_copy(update={"hunks": updated_hunks})


def apply_pending_concept_diff(
    diff: PendingConceptDiff,
    concept_file: Path,
    *,
    remove_pending_path: Path | None = None,
) -> ConceptApplyResult:
    current_hash = concept_file_hash(concept_file)
    if current_hash != diff.base_concept_hash:
        return ConceptApplyResult(
            status=ConceptApplyStatus.BLOCKED,
            diff_id=diff.diff_id,
            blocked_reason="base_concept_hash_mismatch",
            current_concept_hash=current_hash,
        )

    unresolved = [
        hunk.hunk_id
        for hunk in diff.hunks
        if hunk.status in {HunkStatus.PENDING, HunkStatus.REJECTED, HunkStatus.REVISED}
    ]
    if unresolved:
        return ConceptApplyResult(
            status=ConceptApplyStatus.BLOCKED,
            diff_id=diff.diff_id,
            blocked_reason=f"unresolved_hunks:{','.join(unresolved)}",
            current_concept_hash=current_hash,
        )

    accepted_hunks = [hunk for hunk in diff.hunks if hunk.status == HunkStatus.ACCEPTED]
    current_text = concept_file.read_text(encoding="utf-8")
    try:
        updated_text = apply_unified_hunks(current_text, accepted_hunks)
    except ConceptPatchApplyError:
        raise

    _write_text_atomic(concept_file, updated_text)
    if remove_pending_path is not None:
        remove_pending_path.unlink(missing_ok=True)
    return ConceptApplyResult(
        status=ConceptApplyStatus.APPLIED,
        diff_id=diff.diff_id,
        applied_hunk_ids=[hunk.hunk_id for hunk in accepted_hunks],
        current_concept_hash=concept_file_hash(concept_file),
    )


def apply_unified_hunks(text: str, hunks: list[PendingConceptHunk]) -> str:
    lines = text.splitlines(keepends=True)
    parsed = sorted(
        (_parse_unified_hunk(hunk) for hunk in hunks),
        key=lambda item: item[0],
        reverse=True,
    )
    for old_start, old_lines, new_lines, hunk_id in parsed:
        index = old_start - 1
        if index < 0:
            raise ConceptPatchApplyError(f"invalid hunk start: {hunk_id}")
        current = lines[index : index + len(old_lines)]
        if current != old_lines:
            raise ConceptPatchApplyError(f"hunk does not match current Concept: {hunk_id}")
        lines[index : index + len(old_lines)] = new_lines
    return "".join(lines)


def _parse_unified_hunk(hunk: PendingConceptHunk) -> tuple[int, list[str], list[str], str]:
    old_start: int | None = None
    old_lines: list[str] = []
    new_lines: list[str] = []
    in_hunk = False

    for line in hunk.diff_text.splitlines(keepends=True):
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        if line.startswith("@@ "):
            match = _HUNK_HEADER_RE.match(line)
            if not match:
                raise ConceptPatchApplyError(f"invalid hunk header: {hunk.hunk_id}")
            old_start = int(match.group("old_start"))
            in_hunk = True
            continue
        if line.startswith("\\ No newline at end of file"):
            continue
        if not in_hunk:
            continue
        if not line:
            continue

        marker = line[0]
        content = line[1:]
        if marker == " ":
            old_lines.append(content)
            new_lines.append(content)
        elif marker == "-":
            old_lines.append(content)
        elif marker == "+":
            new_lines.append(content)
        else:
            raise ConceptPatchApplyError(f"unsupported diff line: {hunk.hunk_id}")

    if old_start is None:
        raise ConceptPatchApplyError(f"hunk header is required: {hunk.hunk_id}")
    return old_start, old_lines, new_lines, hunk.hunk_id
