from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spec_anchor import spec_claims


SECTION_ID = "docs/spec/main.md#0001-alpha"


@dataclass
class RecordingSpecClaimProvider:
    responses: dict[str, Any]

    def __post_init__(self) -> None:
        self.calls: list[Any] = []

    @property
    def provider_id(self) -> str:
        return "recording-spec-claim-fake"

    def generate(self, request: Any, *, timeout_sec: int) -> Any:
        self.calls.append(request)
        response = self.responses.get(request.section_id)
        if isinstance(response, BaseException):
            raise response
        return response


def _section(
    text: str,
    *,
    section_id: str = SECTION_ID,
    source_hash: str | None = None,
) -> dict[str, Any]:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "section_id": section_id,
        "source_section_id": section_id,
        "source_document_id": "docs/spec/main.md",
        "heading_path": ["Spec", "Alpha"],
        "source_hash": source_hash or digest,
        "semantic_hash": digest,
        "text": text,
    }


def _claim(
    text: str,
    evidence: str,
    *,
    start: int | None = None,
    claim_text: str | None = None,
    target: str = "active session retention",
    target_aliases: list[str] | None = None,
    scope: str = "normal operation",
    condition: str = "active session",
    value: str = "30 days",
    claim_kind: str = "requirement",
) -> dict[str, Any]:
    start_value = text.index(evidence) if start is None else start
    return {
        "claim_text": claim_text or f"{target} is {value}",
        "target": target,
        "target_aliases": target_aliases or ["session retention"],
        "scope": scope,
        "condition": condition,
        "value": value,
        "claim_kind": claim_kind,
        "claim_kind_confidence": "high",
        "evidence_span": evidence,
        "evidence_start": start_value,
        "evidence_end": start_value + len(evidence),
        "evidence_hash": _evidence_hash(evidence),
        "confidence": "high",
        "retrieval": {
            "sparse_keys": [target, value],
            "embedding_text": f"{target} {condition} {value}",
            "conflict_probes": [f"{target} is not {value}"],
        },
    }


def _evidence_hash(value: str) -> str:
    normalized = " ".join(value.strip().split())
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _validate(response: Any, text: str, **kwargs: Any) -> spec_claims.SpecClaimValidation:
    section = _section(text)
    return spec_claims.validate_spec_claim_response(
        response,
        source_section_id=section["source_section_id"],
        section_text=section["text"],
        source_hash=section["source_hash"],
        semantic_hash=section["semantic_hash"],
        generated_at="2026-05-28T00:00:00Z",
        **kwargs,
    )


def _reason_codes(diagnostics: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("reason_code")) for item in diagnostics}


def test_schema_validation_accepts_valid_response_and_rejects_unknown_or_missing_fields() -> None:
    text = "Active sessions must be retained for 30 days."
    valid = _validate({"claims": [_claim(text, text)]}, text)

    assert valid.status == spec_claims.SUCCESS_WITH_CLAIMS
    assert len(valid.claims) == 1
    assert valid.claims[0]["claim_uid"].startswith("claim:sha256:")

    with_unknown = _claim(text, text)
    with_unknown["unexpected"] = "not allowed"
    invalid_field = _validate({"claims": [with_unknown]}, text)
    assert invalid_field.status == spec_claims.FAILED_SPEC_CLAIM_SECTIONS
    assert "schema_validation_failure" in _reason_codes(invalid_field.diagnostics)
    assert any(
        error["error"] == "unexpected_field"
        for item in invalid_field.diagnostics
        for error in item.get("errors", [])
    )

    missing = _claim(text, text)
    del missing["target"]
    missing_required = _validate({"claims": [missing]}, text)
    assert missing_required.status == spec_claims.FAILED_SPEC_CLAIM_SECTIONS
    assert any(
        error["error"] == "missing_required_field"
        for item in missing_required.diagnostics
        for error in item.get("errors", [])
    )


def test_cache_key_reuse_skips_llm_when_section_fingerprint_matches(tmp_path: Path) -> None:
    text = "Active sessions must be retained for 30 days."
    section = _section(text)
    state_path = tmp_path / ".spec-anchor" / "state" / "spec_claims_state.json"
    context_path = tmp_path / ".spec-anchor" / "context" / "spec_claims.jsonl"
    first_provider = RecordingSpecClaimProvider(
        {SECTION_ID: {"claims": [_claim(text, text)]}}
    )

    first = spec_claims.generate_spec_claims_result(
        [section],
        provider=first_provider,
        model="fake-model",
        effort="low",
        state_path=state_path,
        context_path=context_path,
        generated_at="2026-05-28T00:00:00Z",
    )

    assert first.llm_calls == 1
    assert len(first_provider.calls) == 1
    assert state_path.is_file()
    assert context_path.is_file()

    second_provider = RecordingSpecClaimProvider(
        {SECTION_ID: RuntimeError("must not be called")}
    )
    second = spec_claims.generate_spec_claims_result(
        [section],
        provider=second_provider,
        model="fake-model",
        effort="low",
        state_path=state_path,
        context_path=context_path,
        generated_at="2026-05-28T00:01:00Z",
    )

    assert second.status == "skipped_unchanged"
    assert second.llm_calls == 0
    assert second.cache_hits == 1
    assert second_provider.calls == []
    assert second.claims[0]["claim_uid"] == first.claims[0]["claim_uid"]


def test_failed_section_diagnostics_cover_llm_json_and_schema_failures() -> None:
    valid_text = "Active sessions must be retained for 30 days."
    sections = [
        _section(valid_text, section_id="docs/spec/main.md#llm-failure"),
        _section(valid_text, section_id="docs/spec/main.md#json-failure"),
        _section(valid_text, section_id="docs/spec/main.md#schema-failure"),
    ]
    bad_schema = _claim(valid_text, valid_text)
    del bad_schema["claim_kind"]
    provider = RecordingSpecClaimProvider(
        {
            "docs/spec/main.md#llm-failure": RuntimeError("provider down"),
            "docs/spec/main.md#json-failure": "{not-json",
            "docs/spec/main.md#schema-failure": {"claims": [bad_schema]},
        }
    )

    result = spec_claims.generate_spec_claims_result(
        sections,
        provider=provider,
        model="fake-model",
        effort="low",
        generated_at="2026-05-28T00:00:00Z",
    )

    assert result.status == "failed"
    assert set(result.failed_spec_claim_sections) == {
        "docs/spec/main.md#llm-failure",
        "docs/spec/main.md#json-failure",
        "docs/spec/main.md#schema-failure",
    }
    assert {
        "llm_call_failure",
        "json_parse_failure",
        "schema_validation_failure",
    }.issubset(_reason_codes(result.diagnostics))


def test_evidence_offsets_exact_corrected_ambiguous_and_invalid_cases() -> None:
    exact_text = "Active sessions must be retained for 30 days."
    exact = _validate({"claims": [_claim(exact_text, exact_text)]}, exact_text)
    assert exact.status == spec_claims.SUCCESS_WITH_CLAIMS
    assert exact.claims[0]["evidence_start"] == 0
    assert "corrected_evidence_offsets" not in _reason_codes(exact.diagnostics)

    normalized_text = "Active sessions must be retained\n   for 30 days."
    normalized_claim = _claim(
        normalized_text,
        "Active sessions must be retained for 30 days.",
        start=999,
    )
    corrected = _validate({"claims": [normalized_claim]}, normalized_text)
    assert corrected.status == spec_claims.SUCCESS_WITH_CLAIMS
    assert corrected.claims[0]["evidence_start"] == 0
    assert corrected.claims[0]["evidence_end"] == len(normalized_text)
    assert "corrected_evidence_offsets" in _reason_codes(corrected.diagnostics)

    ambiguous_text = (
        "Active sessions must be retained for 30 days. "
        "Active sessions must be retained for 30 days."
    )
    ambiguous_claim = _claim(
        ambiguous_text,
        "Active sessions must be retained for 30 days.",
        start=10,
    )
    ambiguous = _validate({"claims": [ambiguous_claim]}, ambiguous_text)
    assert ambiguous.status == spec_claims.FAILED_SPEC_CLAIM_SECTIONS
    assert "ambiguous_evidence_span" in _reason_codes(ambiguous.diagnostics)
    assert ambiguous.claims == []

    invalid_claim = _claim(exact_text, exact_text)
    invalid_claim["evidence_span"] = "Inactive sessions are deleted immediately."
    invalid_claim["evidence_hash"] = _evidence_hash(invalid_claim["evidence_span"])
    invalid = _validate({"claims": [invalid_claim]}, exact_text)
    assert invalid.status == spec_claims.FAILED_SPEC_CLAIM_SECTIONS
    assert "invalid_evidence_span" in _reason_codes(invalid.diagnostics)
    assert invalid.claims == []


def test_section_result_buckets_distinguish_claims_empty_and_failed() -> None:
    claim_text = "Active sessions must be retained for 30 days."
    claim_section = _section(claim_text, section_id="docs/spec/main.md#with-claim")
    empty_section = _section(
        "This paragraph is introductory background.",
        section_id="docs/spec/main.md#no-claim",
    )
    failed_section = _section(claim_text, section_id="docs/spec/main.md#failed")
    bad_claim = _claim(claim_text, claim_text)
    del bad_claim["target"]
    provider = RecordingSpecClaimProvider(
        {
            "docs/spec/main.md#with-claim": {"claims": [_claim(claim_text, claim_text)]},
            "docs/spec/main.md#no-claim": {"claims": []},
            "docs/spec/main.md#failed": {"claims": [bad_claim]},
        }
    )

    result = spec_claims.generate_spec_claims_result(
        [claim_section, empty_section, failed_section],
        provider=provider,
        model="fake-model",
        effort="low",
        generated_at="2026-05-28T00:00:00Z",
    )

    assert result.status == "partial_success"
    assert result.success_with_claims == ["docs/spec/main.md#with-claim"]
    assert result.success_no_claims == ["docs/spec/main.md#no-claim"]
    assert result.failed_spec_claim_sections == ["docs/spec/main.md#failed"]
    assert "sections_with_no_claims" in _reason_codes(result.diagnostics)


def test_max_claims_per_section_records_limit_reached_section() -> None:
    first_evidence = "Active sessions must be retained for 30 days."
    second_evidence = "Expired sessions must be deleted after retention."
    text = first_evidence + "\n" + second_evidence
    section = _section(text)
    provider = RecordingSpecClaimProvider(
        {
            SECTION_ID: {
                "claims": [
                    _claim(text, first_evidence, target="active session retention"),
                    _claim(
                        text,
                        second_evidence,
                        target="expired session deletion",
                        condition="expired session",
                        value="after retention",
                        claim_text="Expired sessions must be deleted after retention.",
                    ),
                ]
            }
        }
    )

    result = spec_claims.generate_spec_claims_result(
        [section],
        provider=provider,
        model="fake-model",
        max_claims_per_section=1,
        generated_at="2026-05-28T00:00:00Z",
    )

    assert result.status == "success"
    assert result.claim_limit_reached_sections == [SECTION_ID]
    assert len(result.claims) == 1
    assert spec_claims.CLAIM_LIMIT_REACHED_SECTIONS in _reason_codes(result.diagnostics)


def test_claim_uid_stability_ignores_order_schema_version_and_offsets() -> None:
    first_text = "Active sessions must be retained for 30 days."
    second_text = "Expired sessions must be deleted after retention."
    text = first_text + "\n" + second_text
    first = _claim(text, first_text, target="active session retention")
    second = _claim(
        text,
        second_text,
        target="expired session deletion",
        condition="expired session",
        value="after retention",
        claim_text="Expired sessions must be deleted after retention.",
    )

    original = _validate({"claims": [first, second]}, text)
    reordered = _validate({"claims": [second, first]}, text)
    schema_changed = _validate(
        {"claims": [first]},
        text,
        schema_version="spec-claim-schema-v99",
    )

    offset_changed = dict(first)
    offset_changed["evidence_start"] = first["evidence_start"] + 99
    offset_changed["evidence_end"] = first["evidence_end"] + 99
    offset_validated = _validate({"claims": [offset_changed]}, text)

    assert {claim["claim_uid"] for claim in original.claims} == {
        claim["claim_uid"] for claim in reordered.claims
    }
    assert original.claims[0]["claim_uid"] == schema_changed.claims[0]["claim_uid"]
    assert original.claims[0]["claim_uid"] == offset_validated.claims[0]["claim_uid"]
    assert spec_claims.compute_claim_uid(
        source_section_id=SECTION_ID,
        evidence_hash=offset_changed["evidence_hash"],
        evidence_span=offset_changed["evidence_span"],
        claim_text=offset_changed["claim_text"],
        target=offset_changed["target"],
    ) == original.claims[0]["claim_uid"]

    changed_identity_version_uid = spec_claims.compute_claim_uid(
        source_section_id=SECTION_ID,
        evidence_hash=first["evidence_hash"],
        evidence_span=first["evidence_span"],
        claim_text=first["claim_text"],
        target=first["target"],
        claim_identity_version="spec-claim-identity-v2",
    )
    assert changed_identity_version_uid != original.claims[0]["claim_uid"]


def test_state_schema_and_jsonl_atomic_write_exclude_deleted_sections(tmp_path: Path) -> None:
    kept_text = "Active sessions must be retained for 30 days."
    deleted_text = "Expired sessions must be deleted after retention."
    kept = _section(kept_text, section_id="docs/spec/main.md#kept")
    deleted = _section(deleted_text, section_id="docs/spec/main.md#deleted")
    kept_claim = spec_claims.validate_spec_claim_response(
        {"claims": [_claim(kept_text, kept_text)]},
        source_section_id=kept["source_section_id"],
        section_text=kept["text"],
        source_hash=kept["source_hash"],
        semantic_hash=kept["semantic_hash"],
        generated_at="2026-05-28T00:00:00Z",
    ).claims[0]
    deleted_claim = spec_claims.validate_spec_claim_response(
        {"claims": [_claim(deleted_text, deleted_text)]},
        source_section_id=deleted["source_section_id"],
        section_text=deleted["text"],
        source_hash=deleted["source_hash"],
        semantic_hash=deleted["semantic_hash"],
        generated_at="2026-05-28T00:00:00Z",
    ).claims[0]
    state_path = tmp_path / ".spec-anchor" / "state"
    jsonl_path = tmp_path / ".spec-anchor" / "context"

    written_state = spec_claims.write_spec_claims_state(
        state_path,
        {
            "schema_version": spec_claims.SPEC_CLAIM_SCHEMA_VERSION,
            "generated_at": "2026-05-28T00:00:00Z",
            "sections": {
                kept["source_section_id"]: {
                    "source_hash": kept["source_hash"],
                    "semantic_hash": kept["semantic_hash"],
                    "prompt_version": spec_claims.SPEC_CLAIM_PROMPT_VERSION,
                    "model": "fake-model",
                    "effort": "low",
                    "claims": [kept_claim],
                    "status": spec_claims.SUCCESS_WITH_CLAIMS,
                    "diagnostics": [],
                    "generated_at": "2026-05-28T00:00:00Z",
                }
            },
        },
    )
    written_jsonl = spec_claims.write_spec_claims_jsonl(
        jsonl_path,
        [kept_claim, deleted_claim],
        active_source_section_ids=[kept["source_section_id"]],
    )

    state = json.loads(written_state.read_text(encoding="utf-8"))
    assert set(state) == {"schema_version", "generated_at", "sections"}
    assert kept["source_section_id"] in state["sections"]

    lines = [
        json.loads(line)
        for line in written_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert [line["source_section_id"] for line in lines] == [kept["source_section_id"]]
