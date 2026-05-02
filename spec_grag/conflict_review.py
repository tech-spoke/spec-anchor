"""Persistent Conflict candidate review protocol."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from spec_grag.io import write_model_atomic as _write_model_atomic
from spec_grag.protocol import StrictModel
from spec_grag.manifest import SourceManifest, SourceManifestEntry


APPROVED_CONFLICTS_VERSION = "1"


class ConflictCandidateStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    REVISED = "revised"


class PendingConflictCandidate(StrictModel):
    candidate_id: str
    conflict_type: str
    severity: str = "medium"
    rule_id: str | None = None
    summary: str
    reason: str
    evidence_spans: list[dict[str, Any]] = Field(default_factory=list)
    status: ConflictCandidateStatus = ConflictCandidateStatus.PENDING
    revision_instruction: str | None = None


class PendingConflictReview(StrictModel):
    review_id: str
    base_graph_revision: str | None = None
    base_source_manifest_hash: str | None = None
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    candidates: list[PendingConflictCandidate] = Field(default_factory=list)

    def by_candidate_id(self) -> dict[str, PendingConflictCandidate]:
        return {candidate.candidate_id: candidate for candidate in self.candidates}


class ApprovedConflict(StrictModel):
    conflict_id: str
    source_candidate_id: str
    conflict_type: str
    severity: str
    summary: str
    reason: str
    evidence_spans: list[dict[str, Any]] = Field(default_factory=list)
    approved_at: str
    approved_by: str = "human"


class RejectedConflictFingerprint(StrictModel):
    fingerprint: str
    source_candidate_id: str
    rejected_at: str


class ApprovedConflictsSidecar(StrictModel):
    version: str = APPROVED_CONFLICTS_VERSION
    graph_revision: str | None = None
    source_manifest_hash: str | None = None
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    conflicts: list[ApprovedConflict] = Field(default_factory=list)
    rejected_fingerprints: list[RejectedConflictFingerprint] = Field(default_factory=list)


class ConflictApplyStatus(StrEnum):
    APPLIED = "applied"
    BLOCKED = "blocked"


class ConflictApplyResult(StrictModel):
    status: ConflictApplyStatus
    review_id: str
    approved_candidate_ids: list[str] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)
    pending_candidate_ids: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None


class ConflictReviewGenerationResult(StrictModel):
    pending_review: PendingConflictReview | None = None
    created_path: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ConflictReviewError(Exception):
    """Base error for Conflict review protocol failures."""


class ConflictReviewNotFoundError(ConflictReviewError):
    pass


class ConflictCandidateNotFoundError(ConflictReviewError):
    pass


def pending_conflict_review_path(pending_dir: Path, review_id: str) -> Path:
    return pending_dir / f"conflict_review_{review_id}.json"


def approved_conflicts_path(graph_storage: Path) -> Path:
    return graph_storage / "approved_conflicts.json"


def load_pending_conflict_review(path: Path) -> PendingConflictReview:
    if not path.exists():
        raise ConflictReviewNotFoundError(f"pending Conflict review not found: {path}")
    return PendingConflictReview.model_validate_json(path.read_text(encoding="utf-8"))


def write_pending_conflict_review_atomic(
    path: Path,
    review: PendingConflictReview,
) -> None:
    _write_model_atomic(path, review)


def create_pending_conflict_review(
    pending_dir: Path,
    review: PendingConflictReview,
) -> Path:
    path = pending_conflict_review_path(pending_dir, review.review_id)
    write_pending_conflict_review_atomic(path, review)
    return path


def generate_source_conflict_review(
    *,
    project_root: Path,
    graph_storage: Path,
    manifest: SourceManifest,
    graph_revision: str | None,
    generated_at: str,
    document_texts: dict[str, str] | None = None,
) -> ConflictReviewGenerationResult:
    pending_dir = project_root / ".spec-grag" / "pending"
    if first_unresolved_pending_conflict_review(pending_dir) is not None:
        return ConflictReviewGenerationResult()

    candidates = source_conflict_candidates(
        project_root,
        manifest,
        document_texts=document_texts,
    )
    if not candidates:
        return ConflictReviewGenerationResult()

    sidecar = load_approved_conflicts(approved_conflicts_path(graph_storage))
    rejected = {item.fingerprint for item in sidecar.rejected_fingerprints}
    approved_ids = {item.conflict_id for item in sidecar.conflicts}
    filtered = [
        candidate
        for candidate in candidates
        if conflict_fingerprint(candidate) not in rejected
        and conflict_id_for_candidate(candidate) not in approved_ids
    ]
    if not filtered:
        return ConflictReviewGenerationResult()

    review = PendingConflictReview(
        review_id=review_id_for_candidates(filtered, manifest),
        base_graph_revision=graph_revision,
        base_source_manifest_hash=source_manifest_hash(manifest),
        generated_at=generated_at,
        candidates=filtered,
    )
    path = create_pending_conflict_review(pending_dir, review)
    return ConflictReviewGenerationResult(
        pending_review=review,
        created_path=str(path),
    )


def source_conflict_candidates(
    project_root: Path,
    manifest: SourceManifest,
    *,
    document_texts: dict[str, str] | None = None,
) -> list[PendingConflictCandidate]:
    sections = _section_texts(project_root, manifest, document_texts=document_texts)
    if not sections:
        return []

    candidates: list[PendingConflictCandidate] = []
    candidates.extend(_paired_token_candidate(
        sections,
        rule_id="required_optional",
        conflict_type="source_rule",
        severity="medium",
        left_tokens=("required",),
        right_tokens=("optional",),
        summary="Required and optional language both appear in Source specs.",
        reason="A source-level rule appears to be both required and optional.",
    ))
    candidates.extend(_must_vs_must_not_candidates(sections))
    candidates.extend(_paired_token_candidate(
        sections,
        rule_id="required_vs_prohibited_japanese",
        conflict_type="source_rule",
        severity="high",
        left_tokens=("必須", "必ず", "必要"),
        right_tokens=("禁止", "不可", "してはならない", "できない"),
        summary="必須系と禁止系の表現が Source specs 内で並存している。",
        reason="同じ source-level rule が必須と禁止の両方として書かれている可能性がある。",
    ))
    candidates.extend(_paired_token_candidate(
        sections,
        rule_id="japanese_quantifier",
        conflict_type="source_rule",
        severity="medium",
        left_tokens=("必ず", "全て", "すべて"),
        right_tokens=("任意", "一部"),
        summary="日本語の量化表現が Source specs 内で衝突している。",
        reason="全称または必須の表現と、任意または一部の表現が同時に現れている。",
    ))
    candidates.extend(_permission_scope_candidates(sections))
    candidates.extend(_numeric_bound_candidates(sections))
    candidates.extend(_state_transition_candidates(sections))

    deduped: dict[str, PendingConflictCandidate] = {}
    for candidate in candidates:
        deduped.setdefault(conflict_fingerprint(candidate), candidate)
    return sorted(deduped.values(), key=lambda item: item.candidate_id)


def load_approved_conflicts(path: Path) -> ApprovedConflictsSidecar:
    if not path.exists():
        return ApprovedConflictsSidecar()
    return ApprovedConflictsSidecar.model_validate_json(path.read_text(encoding="utf-8"))


def write_approved_conflicts_atomic(
    path: Path,
    sidecar: ApprovedConflictsSidecar,
) -> None:
    _write_model_atomic(path, sidecar)


def iter_pending_conflict_reviews(pending_dir: Path) -> list[PendingConflictReview]:
    if not pending_dir.exists():
        return []
    reviews = []
    for path in sorted(pending_dir.glob("conflict_review_*.json")):
        try:
            reviews.append(load_pending_conflict_review(path))
        except (ConflictReviewError, ValueError):
            continue
    return reviews


def first_unresolved_pending_conflict_review(
    pending_dir: Path,
) -> PendingConflictReview | None:
    for review in iter_pending_conflict_reviews(pending_dir):
        if pending_conflict_review_is_unresolved(review):
            return review
    return None


def pending_conflict_review_is_unresolved(review: PendingConflictReview) -> bool:
    return any(
        candidate.status
        in {
            ConflictCandidateStatus.PENDING,
            ConflictCandidateStatus.ACCEPTED,
            ConflictCandidateStatus.REJECTED,
            ConflictCandidateStatus.DEFERRED,
            ConflictCandidateStatus.REVISED,
        }
        for candidate in review.candidates
    )


def pending_conflict_candidate_ids(project_root: Path) -> list[str]:
    ids: list[str] = []
    for review in iter_pending_conflict_reviews(project_root / ".spec-grag" / "pending"):
        for candidate in review.candidates:
            if candidate.status in {
                ConflictCandidateStatus.PENDING,
                ConflictCandidateStatus.ACCEPTED,
                ConflictCandidateStatus.REJECTED,
                ConflictCandidateStatus.DEFERRED,
                ConflictCandidateStatus.REVISED,
            }:
                ids.append(candidate.candidate_id)
    return ids


def update_conflict_candidate_status(
    review: PendingConflictReview,
    candidate_id: str,
    status: ConflictCandidateStatus,
    *,
    revision_instruction: str | None = None,
) -> PendingConflictReview:
    updated_candidates: list[PendingConflictCandidate] = []
    found = False
    for candidate in review.candidates:
        if candidate.candidate_id != candidate_id:
            updated_candidates.append(candidate)
            continue
        found = True
        updated_candidates.append(
            candidate.model_copy(
                update={
                    "status": status,
                    "revision_instruction": revision_instruction
                    if status == ConflictCandidateStatus.REVISED
                    else None,
                }
            )
        )
    if not found:
        raise ConflictCandidateNotFoundError(f"candidate not found: {candidate_id}")
    return review.model_copy(update={"candidates": updated_candidates})


def apply_pending_conflict_review(
    review: PendingConflictReview,
    graph_storage: Path,
    *,
    remove_pending_path: Path | None = None,
) -> ConflictApplyResult:
    unresolved = [
        candidate
        for candidate in review.candidates
        if candidate.status
        in {
            ConflictCandidateStatus.PENDING,
            ConflictCandidateStatus.DEFERRED,
            ConflictCandidateStatus.REVISED,
        }
    ]
    accepted = [
        candidate
        for candidate in review.candidates
        if candidate.status == ConflictCandidateStatus.ACCEPTED
    ]
    rejected = [
        candidate
        for candidate in review.candidates
        if candidate.status == ConflictCandidateStatus.REJECTED
    ]

    now = datetime.now(UTC).isoformat()
    path = approved_conflicts_path(graph_storage)
    sidecar = load_approved_conflicts(path)
    existing_conflict_ids = {conflict.conflict_id for conflict in sidecar.conflicts}
    existing_fingerprints = {
        fingerprint.fingerprint for fingerprint in sidecar.rejected_fingerprints
    }
    conflicts = list(sidecar.conflicts)
    rejected_fingerprints = list(sidecar.rejected_fingerprints)

    for candidate in accepted:
        conflict = approved_conflict_from_candidate(candidate, approved_at=now)
        if conflict.conflict_id not in existing_conflict_ids:
            conflicts.append(conflict)
            existing_conflict_ids.add(conflict.conflict_id)

    for candidate in rejected:
        fingerprint = rejected_fingerprint_from_candidate(candidate, rejected_at=now)
        if fingerprint.fingerprint not in existing_fingerprints:
            rejected_fingerprints.append(fingerprint)
            existing_fingerprints.add(fingerprint.fingerprint)

    if accepted or rejected:
        write_approved_conflicts_atomic(
            path,
            sidecar.model_copy(
                update={
                    "graph_revision": review.base_graph_revision,
                    "source_manifest_hash": review.base_source_manifest_hash,
                    "generated_at": now,
                    "conflicts": conflicts,
                    "rejected_fingerprints": rejected_fingerprints,
                }
            ),
        )

    if remove_pending_path is not None:
        if unresolved:
            write_pending_conflict_review_atomic(
                remove_pending_path,
                review.model_copy(update={"candidates": unresolved}),
            )
        else:
            remove_pending_path.unlink(missing_ok=True)

    return ConflictApplyResult(
        status=ConflictApplyStatus.APPLIED,
        review_id=review.review_id,
        approved_candidate_ids=[candidate.candidate_id for candidate in accepted],
        rejected_candidate_ids=[candidate.candidate_id for candidate in rejected],
        pending_candidate_ids=[candidate.candidate_id for candidate in unresolved],
    )


def approved_conflict_from_candidate(
    candidate: PendingConflictCandidate,
    *,
    approved_at: str,
) -> ApprovedConflict:
    return ApprovedConflict(
        conflict_id=conflict_id_for_candidate(candidate),
        source_candidate_id=candidate.candidate_id,
        conflict_type=candidate.conflict_type,
        severity=candidate.severity,
        summary=candidate.summary,
        reason=candidate.reason,
        evidence_spans=candidate.evidence_spans,
        approved_at=approved_at,
    )


def rejected_fingerprint_from_candidate(
    candidate: PendingConflictCandidate,
    *,
    rejected_at: str,
) -> RejectedConflictFingerprint:
    return RejectedConflictFingerprint(
        fingerprint=conflict_fingerprint(candidate),
        source_candidate_id=candidate.candidate_id,
        rejected_at=rejected_at,
    )


def conflict_id_for_candidate(candidate: PendingConflictCandidate) -> str:
    return f"conflict-{conflict_fingerprint(candidate)[:16]}"


def conflict_fingerprint(candidate: PendingConflictCandidate) -> str:
    payload = {
        "candidate_id": candidate.candidate_id,
        "conflict_type": candidate.conflict_type,
        "summary": candidate.summary,
        "reason": candidate.reason,
        "evidence_spans": candidate.evidence_spans,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def review_id_for_candidates(
    candidates: list[PendingConflictCandidate],
    manifest: SourceManifest,
) -> str:
    payload = {
        "source_manifest_hash": source_manifest_hash(manifest),
        "candidate_ids": [candidate.candidate_id for candidate in candidates],
    }
    return "review-" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def source_manifest_hash(manifest: SourceManifest) -> str:
    payload = [
        {
            "document_id": entry.document_id,
            "section_id": entry.section_id,
            "source_hash": entry.source_hash,
            "semantic_hash": entry.semantic_hash,
        }
        for entry in sorted(manifest.entries, key=lambda item: item.section_id)
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


class _SectionText:
    def __init__(
        self,
        entry: SourceManifestEntry,
        text: str,
        start_line: int,
        end_line: int,
    ) -> None:
        self.entry = entry
        self.text = text
        self.lowered = text.lower()
        self.start_line = start_line
        self.end_line = end_line


def _section_texts(
    project_root: Path,
    manifest: SourceManifest,
    *,
    document_texts: dict[str, str] | None = None,
) -> list[_SectionText]:
    by_document: dict[str, list[SourceManifestEntry]] = {}
    for entry in manifest.entries:
        by_document.setdefault(entry.document_id, []).append(entry)

    sections: list[_SectionText] = []
    for document_id, entries in by_document.items():
        path = project_root / document_id
        try:
            text = (
                document_texts.get(document_id)
                if document_texts is not None
                else None
            )
            if text is None:
                text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
        except OSError:
            continue
        ordered = sorted(entries, key=lambda item: item.heading_start_line)
        for index, entry in enumerate(ordered):
            start = max(entry.heading_start_line, 1)
            next_start = (
                ordered[index + 1].heading_start_line
                if index + 1 < len(ordered)
                else len(lines) + 1
            )
            end = max(start, next_start - 1)
            text = "\n".join(lines[start - 1 : end]).strip()
            if text:
                sections.append(_SectionText(entry, text, start, end))
    return sections


def _paired_token_candidate(
    sections: list[_SectionText],
    *,
    rule_id: str,
    conflict_type: str,
    severity: str,
    left_tokens: tuple[str, ...],
    right_tokens: tuple[str, ...],
    summary: str,
    reason: str,
) -> list[PendingConflictCandidate]:
    left = _first_section_with_any(sections, left_tokens)
    right = _first_section_with_any(sections, right_tokens)
    if left is None or right is None:
        return []
    return [
        _candidate(
            rule_id=rule_id,
            conflict_type=conflict_type,
            severity=severity,
            summary=summary,
            reason=reason,
            evidence_sections=[left, right] if left is not right else [left],
        )
    ]


def _permission_scope_candidates(
    sections: list[_SectionText],
) -> list[PendingConflictCandidate]:
    admin = _first_section_matching(
        sections,
        lambda section: (
            "admin only" in section.lowered
            or "administrator only" in section.lowered
            or "管理者のみ" in section.text
            or "管理者だけ" in section.text
        ),
    )
    all_users = _first_section_matching(
        sections,
        lambda section: (
            "all users" in section.lowered
            or "any user" in section.lowered
            or "全ユーザー" in section.text
            or "全てのユーザー" in section.text
            or "すべてのユーザー" in section.text
        ),
    )
    if admin is None or all_users is None:
        return []
    return [
        _candidate(
            rule_id="permission_scope",
            conflict_type="source_rule",
            severity="high",
            summary="Exclusive administrator scope and all-user scope both appear.",
            reason="A source-level permission rule may allow both administrators only and all users.",
            evidence_sections=[admin, all_users] if admin is not all_users else [admin],
        )
    ]


def _must_vs_must_not_candidates(
    sections: list[_SectionText],
) -> list[PendingConflictCandidate]:
    required = _first_section_matching(
        sections,
        lambda section: bool(
            re.search(r"\bmust\b(?!\s+not)|\brequired\b|\bshall\b(?!\s+not)", section.lowered)
        ),
    )
    prohibited = _first_section_matching(
        sections,
        lambda section: bool(
            re.search(r"\bmust not\b|\bshall not\b|\bprohibited\b|\bforbidden\b", section.lowered)
        ),
    )
    if required is None or prohibited is None:
        return []
    return [
        _candidate(
            rule_id="must_vs_must_not",
            conflict_type="source_rule",
            severity="high",
            summary="Required and prohibited language both appear in Source specs.",
            reason="A source-level rule appears to be both required and prohibited.",
            evidence_sections=[required, prohibited]
            if required is not prohibited
            else [required],
        )
    ]


def _numeric_bound_candidates(
    sections: list[_SectionText],
) -> list[PendingConflictCandidate]:
    minimums: list[tuple[int, _SectionText]] = []
    maximums: list[tuple[int, _SectionText]] = []
    for section in sections:
        for match in re.finditer(
            r"(?:min(?:imum)?|at least|下限|最低)\D{0,8}(?P<value>\d+)",
            section.lowered,
        ):
            minimums.append((int(match.group("value")), section))
        for match in re.finditer(
            r"(?:max(?:imum)?|at most|上限|最大)\D{0,8}(?P<value>\d+)",
            section.lowered,
        ):
            maximums.append((int(match.group("value")), section))
    if not minimums or not maximums:
        return []
    lower, lower_section = max(minimums, key=lambda item: item[0])
    upper, upper_section = min(maximums, key=lambda item: item[0])
    if lower <= upper:
        return []
    return [
        _candidate(
            rule_id="numeric_bounds",
            conflict_type="source_rule",
            severity="high",
            summary=f"Lower bound {lower} exceeds upper bound {upper}.",
            reason="Numeric lower and upper bounds in Source specs are inconsistent.",
            evidence_sections=[lower_section, upper_section]
            if lower_section is not upper_section
            else [lower_section],
        )
    ]


def _state_transition_candidates(
    sections: list[_SectionText],
) -> list[PendingConflictCandidate]:
    state_word = r"(?:state|状態)"
    transition = r"(?P<from>[^\s,.;。、]+)\s*->\s*(?P<to>[^\s,.;。、]+)"
    required: dict[tuple[str, str], _SectionText] = {}
    prohibited: dict[tuple[str, str], _SectionText] = {}
    for section in sections:
        for match in re.finditer(
            rf"(?:must|required|必須|必要).{{0,24}}{state_word}\s+{transition}",
            section.lowered,
        ):
            required.setdefault((match.group("from"), match.group("to")), section)
        for match in re.finditer(
            rf"(?:must not|shall not|prohibited|forbidden|禁止|不可).{{0,24}}{state_word}\s+{transition}",
            section.lowered,
        ):
            prohibited.setdefault((match.group("from"), match.group("to")), section)
    overlap = sorted(set(required) & set(prohibited))
    if not overlap:
        return []
    source, target = overlap[0]
    required_section = required[(source, target)]
    prohibited_section = prohibited[(source, target)]
    return [
        _candidate(
            rule_id="state_transition",
            conflict_type="source_rule",
            severity="high",
            summary=f"State transition {source} -> {target} is both required and prohibited.",
            reason="The same state transition appears as both required and prohibited.",
            evidence_sections=[required_section, prohibited_section]
            if required_section is not prohibited_section
            else [required_section],
        )
    ]


def _candidate(
    *,
    rule_id: str,
    conflict_type: str,
    severity: str,
    summary: str,
    reason: str,
    evidence_sections: list[_SectionText],
) -> PendingConflictCandidate:
    evidence = [_evidence_span(section) for section in evidence_sections]
    candidate_id = "candidate-" + hashlib.sha256(
        json.dumps(
            {
                "rule_id": rule_id,
                "evidence": [
                    {
                        "source_section_id": item["source_section_id"],
                        "source_hash": item["source_hash"],
                    }
                    for item in evidence
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return PendingConflictCandidate(
        candidate_id=candidate_id,
        conflict_type=conflict_type,
        severity=severity,
        rule_id=rule_id,
        summary=summary,
        reason=reason,
        evidence_spans=evidence,
    )


def _evidence_span(section: _SectionText) -> dict[str, Any]:
    excerpt = " ".join(section.text.split())
    if len(excerpt) > 240:
        excerpt = excerpt[:237].rstrip() + "..."
    return {
        "source_document_id": section.entry.document_id,
        "source_section_id": section.entry.section_id,
        "source_span": f"{section.start_line}-{section.end_line}",
        "source_hash": section.entry.source_hash,
        "excerpt": excerpt,
    }


def _first_section_with_any(
    sections: list[_SectionText],
    tokens: tuple[str, ...],
) -> _SectionText | None:
    lowered_tokens = tuple(token.lower() for token in tokens)
    return _first_section_matching(
        sections,
        lambda section: any(
            token in section.lowered or token in section.text for token in lowered_tokens
        ),
    )


def _first_section_matching(
    sections: list[_SectionText],
    predicate: Any,
) -> _SectionText | None:
    for section in sections:
        if predicate(section):
            return section
    return None


def approved_conflict_notes(graph_storage: Path) -> list[dict[str, Any]]:
    sidecar = load_approved_conflicts(approved_conflicts_path(graph_storage))
    return [
        {
            "conflict": True,
            "source_origin": "approved_conflicts",
            "conflict_id": conflict.conflict_id,
            "source_candidate_id": conflict.source_candidate_id,
            "conflict_type": conflict.conflict_type,
            "severity": conflict.severity,
            "summary": conflict.summary,
            "reason": conflict.reason,
            "evidence_spans": conflict.evidence_spans,
            "approved_by": conflict.approved_by,
            "approved_at": conflict.approved_at,
        }
        for conflict in sidecar.conflicts
    ]


def pending_conflict_review_notes(project_root: Path) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for review in iter_pending_conflict_reviews(project_root / ".spec-grag" / "pending"):
        for candidate in review.candidates:
            notes.append(
                {
                    "source_origin": "pending_conflict_review",
                    "review_id": review.review_id,
                    "candidate_id": candidate.candidate_id,
                    "status": candidate.status.value,
                    "conflict_type": candidate.conflict_type,
                    "severity": candidate.severity,
                    "summary": candidate.summary,
                    "reason": candidate.reason,
                    "evidence_spans": candidate.evidence_spans,
                    "review_required": candidate.status
                    in {
                        ConflictCandidateStatus.PENDING,
                        ConflictCandidateStatus.DEFERRED,
                        ConflictCandidateStatus.REVISED,
                    },
                }
            )
    return notes
