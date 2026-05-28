from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import spec_anchor.conflict_candidates as conflict_candidates
from spec_anchor import claim_retrieval


@dataclass
class RecordingTriageProvider:
    responses: dict[str, Any]

    def __post_init__(self) -> None:
        self.calls: list[Any] = []

    @property
    def provider_id(self) -> str:
        return "recording-conflict-triage-fake"

    def generate(self, request: Any, *, timeout_sec: int) -> Any:
        self.calls.append(request)
        response = self.responses.get(request.candidate_uid)
        if isinstance(response, BaseException):
            raise response
        return response


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _claim(
    suffix: str,
    *,
    section: str = "docs/spec/main.md#0001-alpha",
    target: str = "active session retention",
    value: str | None = None,
    claim_hash_extra: str = "",
    retrieval_hash_extra: str = "",
) -> dict[str, Any]:
    claim_uid = f"claim:sha256:{suffix}"
    claim_value = value or suffix
    evidence = f"{target} must be {claim_value}."
    return {
        "claim_uid": claim_uid,
        "display_id": f"{section}:C{suffix}",
        "claim_hash": _hash(f"claim:{suffix}:{claim_hash_extra}"),
        "section_uid": section,
        "source_section_id": section,
        "source_document_id": "docs/spec/main.md",
        "source_hash": _hash(f"source:{section}"),
        "semantic_hash": _hash(f"semantic:{section}"),
        "claim_text": evidence,
        "target": target,
        "target_aliases": [target],
        "scope": "normal operation",
        "condition": "active session",
        "value": claim_value,
        "claim_kind": "requirement",
        "claim_kind_confidence": "high",
        "evidence_span": evidence,
        "evidence_start": 0,
        "evidence_end": len(evidence),
        "evidence_hash": _hash(evidence),
        "confidence": "high",
        "retrieval": {
            "embedding_text": f"{target} {claim_value}",
            "sparse_keys": [target, claim_value],
            "conflict_probes": [f"{target} not {claim_value}"],
        },
        "retrieval_hash": _hash(f"retrieval:{suffix}:{retrieval_hash_extra}"),
        "schema_version": "spec-claim-v1",
        "claim_identity_version": "claim-identity-v1",
        "retrieval_schema_version": "spec-claim-retrieval-v1",
        "generated_at": "2026-05-29T00:00:00Z",
    }


def _candidate(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_uid, right_uid = sorted([left["claim_uid"], right["claim_uid"]])
    claims = {left["claim_uid"]: left, right["claim_uid"]: right}
    left_claim = claims[left_uid]
    right_claim = claims[right_uid]
    return {
        "candidate_uid": claim_retrieval.candidate_uid_for_claim_pair(
            left_uid,
            right_uid,
        ),
        "display_id": "CC-00001",
        "left_claim_uid": left_uid,
        "right_claim_uid": right_uid,
        "left_claim_hash": left_claim["claim_hash"],
        "right_claim_hash": right_claim["claim_hash"],
        "left_retrieval_hash": left_claim["retrieval_hash"],
        "right_retrieval_hash": right_claim["retrieval_hash"],
        "left_section_uid": left_claim["source_section_id"],
        "right_section_uid": right_claim["source_section_id"],
        "shared_target": left_claim["target"],
        "primary_route": claim_retrieval.CLAIM_RETRIEVAL_ROUTE,
        "routes": [
            {
                "route": claim_retrieval.CLAIM_RETRIEVAL_ROUTE,
                "is_primary_route": True,
            }
        ],
        "retrieval_sources": [claim_retrieval.DENSE_CLAIM_RETRIEVAL],
        "signals": ["semantic_same_target"],
        "triage": None,
        "evidence": [
            {
                "claim_uid": left_claim["claim_uid"],
                "section_uid": left_claim["source_section_id"],
                "evidence_span": left_claim["evidence_span"],
                "evidence_start": left_claim["evidence_start"],
                "evidence_end": left_claim["evidence_end"],
                "evidence_hash": left_claim["evidence_hash"],
            },
            {
                "claim_uid": right_claim["claim_uid"],
                "section_uid": right_claim["source_section_id"],
                "evidence_span": right_claim["evidence_span"],
                "evidence_start": right_claim["evidence_start"],
                "evidence_end": right_claim["evidence_end"],
                "evidence_hash": right_claim["evidence_hash"],
            },
        ],
    }


def _valid_response(send_to_review: bool = True) -> dict[str, Any]:
    return {
        "send_to_review": send_to_review,
        "reason": "The claims govern the same target and may be incompatible.",
        "confidence": "medium",
    }


def _error_codes(validation: conflict_candidates.ConflictTriageValidation) -> set[str]:
    return {
        error["error"]
        for item in validation.diagnostics
        for error in item.get("errors", [])
    }


def _run_triage(
    tmp_path: Path,
    candidates: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    provider: RecordingTriageProvider,
    **kwargs: Any,
) -> conflict_candidates.ConflictCandidateTriageResult:
    return conflict_candidates.generate_conflict_candidate_triage_result(
        candidates,
        claims,
        provider=provider,
        model=kwargs.pop("model", "fake-model"),
        effort=kwargs.pop("effort", "low"),
        cache_dir=tmp_path / ".spec-anchor" / "cache",
        output_path=tmp_path / ".spec-anchor" / "context",
        state_path=tmp_path / ".spec-anchor" / "state",
        generated_at=kwargs.pop("generated_at", "2026-05-29T00:00:00Z"),
        **kwargs,
    )


def test_response_with_conflict_confirmed_field_is_rejected() -> None:
    response = _valid_response()
    response["conflict_confirmed"] = True

    validation = conflict_candidates.validate_conflict_triage_response(response)

    assert validation.status == "failed"
    assert "forbidden_field" in _error_codes(validation)


def test_response_with_human_review_required_field_is_rejected() -> None:
    response = _valid_response()
    response["human_review_required"] = True

    validation = conflict_candidates.validate_conflict_triage_response(response)

    assert validation.status == "failed"
    assert "forbidden_field" in _error_codes(validation)


def test_response_with_resolution_field_is_rejected() -> None:
    response = _valid_response()
    response["resolution"] = "prefer the newer source"

    validation = conflict_candidates.validate_conflict_triage_response(response)

    assert validation.status == "failed"
    assert "forbidden_field" in _error_codes(validation)


def test_response_with_unrecognized_extra_field_is_rejected() -> None:
    response = _valid_response()
    response["notes"] = "not allowed"

    validation = conflict_candidates.validate_conflict_triage_response(response)

    assert validation.status == "failed"
    assert "unexpected_field" in _error_codes(validation)


def test_response_with_unknown_confidence_is_rejected() -> None:
    response = _valid_response()
    response["confidence"] = "unknown"

    validation = conflict_candidates.validate_conflict_triage_response(response)

    assert validation.status == "failed"
    assert "invalid_enum" in _error_codes(validation)


def test_null_triage_record_is_excluded_from_conflict_candidate_jsonl(
    tmp_path: Path,
) -> None:
    left = _claim("a")
    right = _claim("b", section="docs/spec/main.md#0002-beta")
    null_record = _candidate(left, right)
    triaged_record = dict(null_record)
    triaged_record["candidate_uid"] = "candidate:sha256:kept"
    triaged_record["triage"] = _valid_response()

    output = conflict_candidates.write_conflict_candidate_pairs_jsonl(
        tmp_path / ".spec-anchor" / "context",
        [null_record, triaged_record],
    )

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [line["candidate_uid"] for line in lines] == ["candidate:sha256:kept"]
    assert all(line["triage"] is not None for line in lines)


def test_cache_is_reused_when_claim_hash_retrieval_hash_and_settings_match(
    tmp_path: Path,
) -> None:
    left = _claim("a")
    right = _claim("b", section="docs/spec/main.md#0002-beta")
    candidate = _candidate(left, right)
    first_provider = RecordingTriageProvider(
        {candidate["candidate_uid"]: _valid_response()}
    )

    first = _run_triage(tmp_path, [candidate], [left, right], first_provider)

    second_provider = RecordingTriageProvider(
        {candidate["candidate_uid"]: RuntimeError("must not be called")}
    )
    second = _run_triage(tmp_path, [candidate], [left, right], second_provider)

    assert first.llm_calls == 1
    assert second.llm_calls == 0
    assert second.cache_hits == 1
    assert second_provider.calls == []
    assert second.candidates[0]["triage"] == _valid_response()


def test_cache_is_not_reused_when_triage_prompt_version_changes(
    tmp_path: Path,
) -> None:
    left = _claim("a")
    right = _claim("b", section="docs/spec/main.md#0002-beta")
    candidate = _candidate(left, right)
    first_provider = RecordingTriageProvider(
        {candidate["candidate_uid"]: _valid_response()}
    )
    second_provider = RecordingTriageProvider(
        {
            candidate["candidate_uid"]: {
                "send_to_review": True,
                "reason": "Prompt version changed, so this was regenerated.",
                "confidence": "high",
            }
        }
    )

    _run_triage(
        tmp_path,
        [candidate],
        [left, right],
        first_provider,
        triage_prompt_version="conflict-triage-prompt-test-v1",
    )
    second = _run_triage(
        tmp_path,
        [candidate],
        [left, right],
        second_provider,
        triage_prompt_version="conflict-triage-prompt-test-v2",
    )

    assert len(second_provider.calls) == 1
    assert second.llm_calls == 1
    assert second.cache_hits == 0
    assert second.candidates[0]["triage"]["confidence"] == "high"


def test_triage_max_pairs_skips_pairs_beyond_limit_without_llm_call(
    tmp_path: Path,
) -> None:
    first = _claim("a")
    second = _claim("b", section="docs/spec/main.md#0002-beta")
    third = _claim("c", section="docs/spec/main.md#0003-gamma")
    first_candidate = _candidate(first, second)
    second_candidate = _candidate(first, third)
    provider = RecordingTriageProvider(
        {first_candidate["candidate_uid"]: _valid_response()}
    )

    result = _run_triage(
        tmp_path,
        [first_candidate, second_candidate],
        [first, second, third],
        provider,
        triage_max_pairs=1,
    )

    assert len(provider.calls) == 1
    assert provider.calls[0].candidate_uid == first_candidate["candidate_uid"]
    assert result.triage_truncated_pairs == 1
    assert [item["candidate_uid"] for item in result.candidates] == [
        first_candidate["candidate_uid"]
    ]


def test_valid_send_to_review_response_is_accepted_and_written(
    tmp_path: Path,
) -> None:
    left = _claim("a", value="30 days")
    right = _claim("b", section="docs/spec/main.md#0002-beta", value="7 days")
    candidate = _candidate(left, right)
    provider = RecordingTriageProvider(
        {candidate["candidate_uid"]: _valid_response()}
    )

    result = _run_triage(tmp_path, [candidate], [left, right], provider)

    assert result.status == "success"
    assert result.send_to_review_count == 1
    assert result.candidates[0]["triage"] == _valid_response()
    assert "llm_triage_send_to_review" in result.candidates[0]["signals"]

    written = conflict_candidates.read_conflict_candidate_pairs_jsonl(
        tmp_path / ".spec-anchor" / "context"
    )
    assert [item["candidate_uid"] for item in written] == [candidate["candidate_uid"]]
    assert written[0]["triage"] == _valid_response()
