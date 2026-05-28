"""SpecClaim extraction stage helpers.

SpecClaims are conflict-candidate inputs extracted from Source Specs sections.
This module owns the prompt, response validation, deterministic claim identity,
state file handling, and JSONL persistence for the extraction stage. Wiring into
`/spec-core` is intentionally handled outside this Part A module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SPEC_CLAIM_SCHEMA_VERSION = "spec-claim-schema-v1"
SPEC_CLAIM_PROMPT_VERSION = "spec-claim-prompt-v1"
SPEC_CLAIM_IDENTITY_VERSION = "spec-claim-identity-v1"
SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION = "spec-claim-retrieval-v1"

SPEC_CLAIMS_STAGE = "spec_claims"
SPEC_CLAIMS_STATE_FILENAME = "spec_claims_state.json"
SPEC_CLAIMS_JSONL_FILENAME = "spec_claims.jsonl"

SUCCESS_WITH_CLAIMS = "success_with_claims"
SUCCESS_NO_CLAIMS = "success_no_claims"
FAILED_SPEC_CLAIM_SECTIONS = "failed_spec_claim_sections"
CLAIM_LIMIT_REACHED_SECTIONS = "claim_limit_reached_sections"

_SPACE_RE = re.compile(r"\s+")
_REQUIRED_RESPONSE_FIELDS = {"claims": list}
_ALLOWED_RESPONSE_FIELDS = frozenset({"claims"})
_REQUIRED_CLAIM_FIELDS = {
    "claim_text": str,
    "target": str,
    "target_aliases": list,
    "claim_kind": str,
    "evidence_span": str,
    "evidence_start": int,
    "evidence_end": int,
    "evidence_hash": str,
    "confidence": str,
    "retrieval": dict,
}
_OPTIONAL_CLAIM_FIELDS = frozenset(
    {
        "scope",
        "condition",
        "value",
        "claim_kind_confidence",
    }
)
_ALLOWED_CLAIM_FIELDS = frozenset(_REQUIRED_CLAIM_FIELDS) | _OPTIONAL_CLAIM_FIELDS
_REQUIRED_RETRIEVAL_FIELDS = {
    "sparse_keys": list,
    "embedding_text": str,
    "conflict_probes": list,
}
_ALLOWED_RETRIEVAL_FIELDS = frozenset(_REQUIRED_RETRIEVAL_FIELDS)


@dataclass(frozen=True)
class SpecClaimLlmRequest:
    task: str
    prompt: str
    prompt_version: str
    model: str
    source_hash: str
    semantic_hash: str | None = None
    section_id: str | None = None
    stage: str = SPEC_CLAIMS_STAGE
    effort: str | None = None
    input_hashes: Mapping[str, str] | None = None
    context_hashes: Mapping[str, str] | None = None
    section_hashes: Mapping[str, str] | None = None
    metadata_version: int = 1

    def to_provider_payload(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "stage": self.stage,
            "prompt": self.prompt,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "source_hash": self.source_hash,
            "semantic_hash": self.semantic_hash,
            "section_id": self.section_id,
            "effort": self.effort,
            "input_hashes": dict(self.input_hashes or {}),
            "context_hashes": dict(self.context_hashes or {}),
            "section_hashes": dict(self.section_hashes or {}),
            "metadata_version": self.metadata_version,
        }


@dataclass(frozen=True)
class SpecClaimValidation:
    claims: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    status: str
    limit_reached: bool = False


@dataclass(frozen=True)
class SpecClaimSectionResult:
    source_section_id: str
    status: str
    claims: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    generated_at: str
    cache_key: str
    llm_called: bool
    cache_hit: bool
    limit_reached: bool = False

    def to_state_entry(self, section: "_SectionRecord") -> dict[str, Any]:
        return {
            "source_hash": section.source_hash,
            "semantic_hash": section.semantic_hash,
            "prompt_version": SPEC_CLAIM_PROMPT_VERSION,
            "model": _jsonable_value(section.model),
            "effort": _jsonable_value(section.effort),
            "schema_version": SPEC_CLAIM_SCHEMA_VERSION,
            "cache_key": self.cache_key,
            "claims": [dict(claim) for claim in self.claims],
            "status": self.status,
            "diagnostics": [dict(item) for item in self.diagnostics],
            "generated_at": self.generated_at,
            "claim_count": len(self.claims),
            "claim_uids": [str(claim.get("claim_uid")) for claim in self.claims],
            "claim_hashes": [str(claim.get("claim_hash")) for claim in self.claims],
            "retrieval_hashes": [
                str(claim.get("retrieval_hash")) for claim in self.claims
            ],
            "max_claims_per_section": section.max_claims_per_section,
            "limit_reached": self.limit_reached,
        }


@dataclass(frozen=True)
class SpecClaimGenerationResult:
    claims: list[dict[str, Any]]
    section_results: dict[str, SpecClaimSectionResult]
    diagnostics: list[dict[str, Any]]
    state: dict[str, Any]
    status: str
    generated_at: str
    llm_calls: int
    cache_hits: int
    success_with_claims: list[str]
    success_no_claims: list[str]
    failed_spec_claim_sections: list[str]
    claim_limit_reached_sections: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SPEC_CLAIM_SCHEMA_VERSION,
            "prompt_version": SPEC_CLAIM_PROMPT_VERSION,
            "identity_version": SPEC_CLAIM_IDENTITY_VERSION,
            "retrieval_schema_version": SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION,
            "status": self.status,
            "generated_at": self.generated_at,
            "claims": [dict(claim) for claim in self.claims],
            "sections": {
                section_id: {
                    "status": result.status,
                    "claims": [dict(claim) for claim in result.claims],
                    "diagnostics": [dict(item) for item in result.diagnostics],
                    "generated_at": result.generated_at,
                    "cache_key": result.cache_key,
                    "llm_called": result.llm_called,
                    "cache_hit": result.cache_hit,
                    "limit_reached": result.limit_reached,
                }
                for section_id, result in self.section_results.items()
            },
            "diagnostics": [dict(item) for item in self.diagnostics],
            "llm_calls": self.llm_calls,
            "cache_hits": self.cache_hits,
            SUCCESS_WITH_CLAIMS: list(self.success_with_claims),
            SUCCESS_NO_CLAIMS: list(self.success_no_claims),
            FAILED_SPEC_CLAIM_SECTIONS: list(self.failed_spec_claim_sections),
            CLAIM_LIMIT_REACHED_SECTIONS: list(self.claim_limit_reached_sections),
        }


@dataclass(frozen=True)
class _SectionRecord:
    source_section_id: str
    section_id: str
    source_hash: str
    semantic_hash: str
    text: str
    heading_path: list[str]
    source_document_id: str
    model: str
    effort: str | None
    max_claims_per_section: int


def build_spec_claim_prompt(
    section_text: str,
    *,
    source_section_id: str,
    source_hash: str | None = None,
    semantic_hash: str | None = None,
    max_claims_per_section: int = 20,
) -> str:
    """Build the LLM prompt for one Source Specs section."""

    payload = {
        "task": "extract_spec_claims",
        "instructions": [
            "Extract only specification claims explicitly supported by the section.",
            "Return strict JSON with exactly one top-level key: claims.",
            "Each claim must contain claim_text, target, target_aliases, claim_kind, evidence_span, evidence_start, evidence_end, evidence_hash, confidence, and retrieval.",
            "Each claim may also contain scope, condition, value, and claim_kind_confidence.",
            "retrieval must contain sparse_keys, embedding_text, and conflict_probes.",
            "Do not infer conflicts; only extract grounded claims.",
            "Use an empty claims array when the section contains no specification claim.",
        ],
        "schema_version": SPEC_CLAIM_SCHEMA_VERSION,
        "prompt_version": SPEC_CLAIM_PROMPT_VERSION,
        "retrieval_schema_version": SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION,
        "max_claims_per_section": max(0, int(max_claims_per_section)),
        "source_section": {
            "source_section_id": source_section_id,
            "source_hash": source_hash,
            "semantic_hash": semantic_hash,
            "text": section_text,
        },
        "output_shape": {
            "claims": [
                {
                    "claim_text": "string",
                    "target": "string",
                    "target_aliases": ["string"],
                    "scope": "string",
                    "condition": "string",
                    "value": "string",
                    "claim_kind": "requirement|constraint|behavior|status|fallback|deprecation|source_of_truth|scope_rule|freshness_rule|cache_rule|unknown|other",
                    "claim_kind_confidence": "high|medium|low",
                    "evidence_span": "exact source excerpt or whitespace-normalized excerpt",
                    "evidence_start": 0,
                    "evidence_end": 0,
                    "evidence_hash": "sha256:<normalized evidence hash>",
                    "confidence": "high|medium|low",
                    "retrieval": {
                        "sparse_keys": ["string"],
                        "embedding_text": "string",
                        "conflict_probes": ["string"],
                    },
                }
            ]
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def validate_spec_claim_response(
    response: Any,
    *,
    source_section_id: str,
    section_text: str,
    source_hash: str,
    semantic_hash: str,
    generated_at: str | None = None,
    max_claims_per_section: int = 20,
    schema_version: str = SPEC_CLAIM_SCHEMA_VERSION,
    claim_identity_version: str = SPEC_CLAIM_IDENTITY_VERSION,
    retrieval_schema_version: str = SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION,
) -> SpecClaimValidation:
    """Validate one LLM response and return canonical SpecClaim records."""

    generated_at = generated_at or _now()
    diagnostics: list[dict[str, Any]] = []
    parsed = _parse_response_object(response, source_section_id, diagnostics)
    if parsed is None:
        return SpecClaimValidation(
            claims=[],
            diagnostics=diagnostics,
            status=FAILED_SPEC_CLAIM_SECTIONS,
        )

    schema_errors = _validate_response_schema(parsed)
    if schema_errors:
        diagnostics.append(
            _diagnostic(
                "schema_validation_failure",
                "SpecClaim response schema validation failed",
                source_section_id=source_section_id,
                severity="error",
                errors=schema_errors,
            )
        )
        return SpecClaimValidation(
            claims=[],
            diagnostics=diagnostics,
            status=FAILED_SPEC_CLAIM_SECTIONS,
        )

    raw_claims = list(parsed["claims"])
    if not raw_claims:
        diagnostics.append(
            _diagnostic(
                "sections_with_no_claims",
                "LLM returned an empty claims array for this section",
                source_section_id=source_section_id,
                severity="info",
            )
        )
        return SpecClaimValidation(
            claims=[],
            diagnostics=diagnostics,
            status=SUCCESS_NO_CLAIMS,
        )

    max_claims = max(0, int(max_claims_per_section))
    limit_reached = max_claims == 0 or len(raw_claims) >= max_claims
    if limit_reached:
        diagnostics.append(
            _diagnostic(
                CLAIM_LIMIT_REACHED_SECTIONS,
                "SpecClaim extraction reached max_claims_per_section",
                source_section_id=source_section_id,
                severity="warning",
                raw_claim_count=len(raw_claims),
                max_claims_per_section=max_claims,
            )
        )
    raw_claims = raw_claims[:max_claims] if max_claims > 0 else []

    claims: list[dict[str, Any]] = []
    seen_claim_uids: set[str] = set()
    skipped_for_offsets = 0
    valid_raw_claims: list[tuple[int, Mapping[str, Any], dict[str, Any]]] = []
    for index, raw_claim in enumerate(raw_claims):
        offset_result = _resolve_evidence_offsets(
            raw_claim,
            section_text=section_text,
            source_section_id=source_section_id,
            item_index=index,
        )
        diagnostics.extend(offset_result["diagnostics"])
        if offset_result["status"] != "valid":
            skipped_for_offsets += 1
            continue
        valid_raw_claims.append((index, raw_claim, offset_result))

    base_uid_counts: dict[str, int] = {}
    for _, raw_claim, offset_result in valid_raw_claims:
        base_uid = compute_claim_uid(
            source_section_id=source_section_id,
            evidence_hash=_hash_normalized_text(str(offset_result["evidence_span"])),
            evidence_span=str(offset_result["evidence_span"]),
            claim_text=str(raw_claim.get("claim_text") or ""),
            target=str(raw_claim.get("target") or ""),
            claim_identity_version=claim_identity_version,
        )
        base_uid_counts[base_uid] = base_uid_counts.get(base_uid, 0) + 1

    for index, raw_claim, offset_result in valid_raw_claims:
        base_uid = compute_claim_uid(
            source_section_id=source_section_id,
            evidence_hash=_hash_normalized_text(str(offset_result["evidence_span"])),
            evidence_span=str(offset_result["evidence_span"]),
            claim_text=str(raw_claim.get("claim_text") or ""),
            target=str(raw_claim.get("target") or ""),
            claim_identity_version=claim_identity_version,
        )
        claim = _build_claim_record(
            raw_claim,
            source_section_id=source_section_id,
            source_hash=source_hash,
            semantic_hash=semantic_hash,
            generated_at=generated_at,
            evidence_start=offset_result["evidence_start"],
            evidence_end=offset_result["evidence_end"],
            evidence_span=offset_result["evidence_span"],
            schema_version=schema_version,
            claim_identity_version=claim_identity_version,
            retrieval_schema_version=retrieval_schema_version,
            use_evidence_start_in_identity=base_uid_counts[base_uid] > 1,
        )
        claim_uid = str(claim["claim_uid"])
        if claim_uid in seen_claim_uids:
            diagnostics.append(
                _diagnostic(
                    "duplicate_spec_claim_collapsed",
                    "Duplicate SpecClaim was collapsed by claim_uid",
                    source_section_id=source_section_id,
                    severity="warning",
                    item_index=index,
                    claim_uid=claim_uid,
                )
            )
            continue
        seen_claim_uids.add(claim_uid)
        claims.append(claim)

    if claims:
        return SpecClaimValidation(
            claims=claims,
            diagnostics=diagnostics,
            status=SUCCESS_WITH_CLAIMS,
            limit_reached=limit_reached,
        )
    if skipped_for_offsets:
        return SpecClaimValidation(
            claims=[],
            diagnostics=diagnostics,
            status=FAILED_SPEC_CLAIM_SECTIONS,
            limit_reached=limit_reached,
        )
    return SpecClaimValidation(
        claims=[],
        diagnostics=diagnostics,
        status=SUCCESS_NO_CLAIMS,
        limit_reached=limit_reached,
    )


def compute_claim_uid(
    *,
    source_section_id: str | None = None,
    section_uid: str | None = None,
    evidence_hash: str,
    evidence_span: str,
    claim_text: str,
    target: str,
    claim_identity_version: str = SPEC_CLAIM_IDENTITY_VERSION,
    evidence_start: int | None = None,
) -> str:
    """Return a deterministic stable SpecClaim identity."""

    materials: list[Any] = [
        str(source_section_id or section_uid or ""),
        str(evidence_hash),
        _identity_text(evidence_span),
        _identity_text(claim_text),
        _target_identity_text(target),
        str(claim_identity_version),
    ]
    if evidence_start is not None:
        materials.append({"evidence_start": int(evidence_start)})
    return "claim:sha256:" + _sha256_text(_stable_json(materials))


def compute_spec_claim_cache_key(
    *,
    source_section_id: str,
    source_hash: str,
    semantic_hash: str,
    spec_claim_prompt_version: str = SPEC_CLAIM_PROMPT_VERSION,
    model: str,
    effort: str | None,
    schema_version: str = SPEC_CLAIM_SCHEMA_VERSION,
) -> str:
    payload = {
        "source_section_id": source_section_id,
        "source_hash": source_hash,
        "semantic_hash": semantic_hash,
        "spec_claim_prompt_version": spec_claim_prompt_version,
        "model": model,
        "effort": effort,
        "schema_version": schema_version,
    }
    return "sha256:" + _sha256_text(_stable_json(payload))


def read_spec_claims_state(path: str | Path) -> dict[str, Any]:
    state_path = _state_path(path)
    if not state_path.is_file():
        return {
            "schema_version": SPEC_CLAIM_SCHEMA_VERSION,
            "generated_at": None,
            "sections": {},
        }
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema_version": SPEC_CLAIM_SCHEMA_VERSION,
            "generated_at": None,
            "sections": {},
        }
    if not isinstance(payload, Mapping):
        return {
            "schema_version": SPEC_CLAIM_SCHEMA_VERSION,
            "generated_at": None,
            "sections": {},
        }
    sections = payload.get("sections")
    return {
        "schema_version": str(payload.get("schema_version") or SPEC_CLAIM_SCHEMA_VERSION),
        "generated_at": payload.get("generated_at"),
        "sections": dict(sections) if isinstance(sections, Mapping) else {},
    }


def write_spec_claims_state(path: str | Path, state: Mapping[str, Any]) -> Path:
    state_path = _state_path(path)
    payload = {
        "schema_version": str(state.get("schema_version") or SPEC_CLAIM_SCHEMA_VERSION),
        "generated_at": state.get("generated_at") or _now(),
        "sections": dict(state.get("sections") or {}),
    }
    _atomic_write_json(state_path, payload)
    return state_path


def write_spec_claims_jsonl(
    path: str | Path,
    claims: Sequence[Mapping[str, Any]],
    *,
    active_source_section_ids: Sequence[str] | None = None,
) -> Path:
    jsonl_path = _jsonl_path(path)
    active = set(active_source_section_ids or [])
    records = [
        dict(claim)
        for claim in claims
        if active_source_section_ids is None
        or str(claim.get("source_section_id") or "") in active
    ]
    records.sort(
        key=lambda item: (
            str(item.get("source_section_id") or ""),
            str(item.get("claim_uid") or ""),
        )
    )
    _atomic_write_jsonl(jsonl_path, records)
    return jsonl_path


def generate_spec_claims_result(
    sections: Sequence[Any],
    *,
    provider: Any,
    model: str = "fake",
    effort: str | None = None,
    max_claims_per_section: int = 20,
    state_path: str | Path | None = None,
    context_path: str | Path | None = None,
    previous_state: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
    timeout_sec: int = 120,
) -> SpecClaimGenerationResult:
    """Generate or reuse SpecClaims for a set of Source Specs sections."""

    generated_at = generated_at or _now()
    records = [
        _normalize_section(
            section,
            model=model,
            effort=effort,
            max_claims_per_section=max_claims_per_section,
        )
        for section in sections
    ]
    loaded_state = (
        read_spec_claims_state(state_path)
        if previous_state is None and state_path is not None
        else _normalize_state(previous_state)
    )
    previous_sections = loaded_state.get("sections", {})
    if not isinstance(previous_sections, Mapping):
        previous_sections = {}

    section_results: dict[str, SpecClaimSectionResult] = {}
    state_sections: dict[str, Any] = {}
    all_claims: list[dict[str, Any]] = []
    all_diagnostics: list[dict[str, Any]] = []
    llm_calls = 0
    cache_hits = 0

    for section in records:
        cache_key = compute_spec_claim_cache_key(
            source_section_id=section.source_section_id,
            source_hash=section.source_hash,
            semantic_hash=section.semantic_hash,
            model=model,
            effort=effort,
        )
        cached = _usable_cached_section(
            previous_sections.get(section.source_section_id),
            section=section,
            cache_key=cache_key,
        )
        if cached is not None:
            result = SpecClaimSectionResult(
                source_section_id=section.source_section_id,
                status=str(cached.get("status") or SUCCESS_NO_CLAIMS),
                claims=[
                    dict(claim)
                    for claim in cached.get("claims", [])
                    if isinstance(claim, Mapping)
                ],
                diagnostics=[
                    dict(item)
                    for item in cached.get("diagnostics", [])
                    if isinstance(item, Mapping)
                ],
                generated_at=str(cached.get("generated_at") or generated_at),
                cache_key=cache_key,
                llm_called=False,
                cache_hit=True,
                limit_reached=bool(cached.get("limit_reached")),
            )
            cache_hits += 1
        else:
            result = _extract_section_claims(
                section,
                provider=provider,
                cache_key=cache_key,
                generated_at=generated_at,
                timeout_sec=timeout_sec,
            )
            llm_calls += 1 if result.llm_called else 0

        section_results[section.source_section_id] = result
        state_sections[section.source_section_id] = result.to_state_entry(section)
        all_claims.extend(result.claims)
        all_diagnostics.extend(result.diagnostics)

    state = {
        "schema_version": SPEC_CLAIM_SCHEMA_VERSION,
        "generated_at": generated_at,
        "sections": state_sections,
    }
    if state_path is not None:
        write_spec_claims_state(state_path, state)
    if context_path is not None:
        write_spec_claims_jsonl(
            context_path,
            all_claims,
            active_source_section_ids=[record.source_section_id for record in records],
        )

    success_with_claims = [
        section_id
        for section_id, result in section_results.items()
        if result.status == SUCCESS_WITH_CLAIMS
    ]
    success_no_claims = [
        section_id
        for section_id, result in section_results.items()
        if result.status == SUCCESS_NO_CLAIMS
    ]
    failed_sections = [
        section_id
        for section_id, result in section_results.items()
        if result.status == FAILED_SPEC_CLAIM_SECTIONS
    ]
    limit_sections = [
        section_id
        for section_id, result in section_results.items()
        if result.limit_reached
    ]
    status = _stage_status(
        section_results.values(),
        cache_hits=cache_hits,
        section_count=len(records),
    )
    return SpecClaimGenerationResult(
        claims=all_claims,
        section_results=section_results,
        diagnostics=all_diagnostics,
        state=state,
        status=status,
        generated_at=generated_at,
        llm_calls=llm_calls,
        cache_hits=cache_hits,
        success_with_claims=success_with_claims,
        success_no_claims=success_no_claims,
        failed_spec_claim_sections=failed_sections,
        claim_limit_reached_sections=limit_sections,
    )


def generate_spec_claims(
    sections: Sequence[Any],
    *,
    provider: Any,
    model: str = "fake",
    effort: str | None = None,
    max_claims_per_section: int = 20,
    state_path: str | Path | None = None,
    context_path: str | Path | None = None,
    previous_state: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    return generate_spec_claims_result(
        sections,
        provider=provider,
        model=model,
        effort=effort,
        max_claims_per_section=max_claims_per_section,
        state_path=state_path,
        context_path=context_path,
        previous_state=previous_state,
        generated_at=generated_at,
        timeout_sec=timeout_sec,
    ).to_dict()


def _extract_section_claims(
    section: _SectionRecord,
    *,
    provider: Any,
    cache_key: str,
    generated_at: str,
    timeout_sec: int,
) -> SpecClaimSectionResult:
    request = SpecClaimLlmRequest(
        task=SPEC_CLAIMS_STAGE,
        stage=SPEC_CLAIMS_STAGE,
        prompt=build_spec_claim_prompt(
            section.text,
            source_section_id=section.source_section_id,
            source_hash=section.source_hash,
            semantic_hash=section.semantic_hash,
            max_claims_per_section=section.max_claims_per_section,
        ),
        prompt_version=SPEC_CLAIM_PROMPT_VERSION,
        model=section.model,
        effort=section.effort,
        source_hash=section.source_hash,
        semantic_hash=section.semantic_hash,
        section_id=section.source_section_id,
        input_hashes={
            "source_hash": section.source_hash,
            "semantic_hash": section.semantic_hash,
        },
        section_hashes={section.source_section_id: section.source_hash},
    )
    try:
        response = provider.generate(request, timeout_sec=timeout_sec)
    except Exception as exc:
        diagnostics = [
            _diagnostic(
                "llm_call_failure",
                "SpecClaim LLM call failed",
                source_section_id=section.source_section_id,
                severity="error",
                exception_type=exc.__class__.__name__,
                exception_message=str(exc),
                model=section.model,
                effort=section.effort,
                prompt_version=SPEC_CLAIM_PROMPT_VERSION,
            )
        ]
        return SpecClaimSectionResult(
            source_section_id=section.source_section_id,
            status=FAILED_SPEC_CLAIM_SECTIONS,
            claims=[],
            diagnostics=diagnostics,
            generated_at=generated_at,
            cache_key=cache_key,
            llm_called=True,
            cache_hit=False,
        )

    validation = validate_spec_claim_response(
        response,
        source_section_id=section.source_section_id,
        section_text=section.text,
        source_hash=section.source_hash,
        semantic_hash=section.semantic_hash,
        generated_at=generated_at,
        max_claims_per_section=section.max_claims_per_section,
    )
    return SpecClaimSectionResult(
        source_section_id=section.source_section_id,
        status=validation.status,
        claims=validation.claims,
        diagnostics=validation.diagnostics,
        generated_at=generated_at,
        cache_key=cache_key,
        llm_called=True,
        cache_hit=False,
        limit_reached=validation.limit_reached,
    )


def _parse_response_object(
    response: Any,
    source_section_id: str,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if isinstance(response, (str, bytes, bytearray)):
        try:
            parsed = json.loads(
                response.decode("utf-8") if isinstance(response, (bytes, bytearray)) else response
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            diagnostics.append(
                _diagnostic(
                    "json_parse_failure",
                    "SpecClaim LLM response is not valid JSON",
                    source_section_id=source_section_id,
                    severity="error",
                    exception_type=exc.__class__.__name__,
                    exception_message=str(exc),
                )
            )
            return None
        response = parsed
    if not isinstance(response, Mapping):
        diagnostics.append(
            _diagnostic(
                "schema_validation_failure",
                "SpecClaim LLM response root must be an object",
                source_section_id=source_section_id,
                severity="error",
                actual_type=type(response).__name__,
            )
        )
        return None
    return dict(response)


def _validate_response_schema(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    errors.extend(_unexpected_fields(response, _ALLOWED_RESPONSE_FIELDS, path="$"))
    for field_name, expected_type in _REQUIRED_RESPONSE_FIELDS.items():
        if field_name not in response:
            errors.append({"path": f"$.{field_name}", "error": "missing_required_field"})
            continue
        if not _is_expected_type(response[field_name], expected_type):
            errors.append(
                {
                    "path": f"$.{field_name}",
                    "error": "invalid_type",
                    "expected": expected_type.__name__,
                    "actual": type(response[field_name]).__name__,
                }
            )
    claims = response.get("claims")
    if isinstance(claims, list):
        for index, claim in enumerate(claims):
            if not isinstance(claim, Mapping):
                errors.append(
                    {
                        "path": f"$.claims[{index}]",
                        "error": "invalid_type",
                        "expected": "object",
                        "actual": type(claim).__name__,
                    }
                )
                continue
            errors.extend(_validate_claim_schema(claim, index))
    return errors


def _validate_claim_schema(claim: Mapping[str, Any], index: int) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    claim_path = f"$.claims[{index}]"
    errors.extend(_unexpected_fields(claim, _ALLOWED_CLAIM_FIELDS, path=claim_path))
    for field_name, expected_type in _REQUIRED_CLAIM_FIELDS.items():
        path = f"{claim_path}.{field_name}"
        if field_name not in claim:
            errors.append({"path": path, "error": "missing_required_field"})
            continue
        value = claim[field_name]
        if not _is_expected_type(value, expected_type):
            errors.append(
                {
                    "path": path,
                    "error": "invalid_type",
                    "expected": _type_name(expected_type),
                    "actual": type(value).__name__,
                }
            )
            continue
        if expected_type is list and not all(isinstance(item, str) for item in value):
            errors.append(
                {
                    "path": path,
                    "error": "invalid_list_item_type",
                    "expected": "list[str]",
                }
            )
    retrieval = claim.get("retrieval")
    if isinstance(retrieval, Mapping):
        retrieval_path = f"{claim_path}.retrieval"
        errors.extend(
            _unexpected_fields(
                retrieval,
                _ALLOWED_RETRIEVAL_FIELDS,
                path=retrieval_path,
            )
        )
        for field_name, expected_type in _REQUIRED_RETRIEVAL_FIELDS.items():
            path = f"{retrieval_path}.{field_name}"
            if field_name not in retrieval:
                errors.append({"path": path, "error": "missing_required_field"})
                continue
            value = retrieval[field_name]
            if not _is_expected_type(value, expected_type):
                errors.append(
                    {
                        "path": path,
                        "error": "invalid_type",
                        "expected": _type_name(expected_type),
                        "actual": type(value).__name__,
                    }
                )
                continue
            if expected_type is list and not all(isinstance(item, str) for item in value):
                errors.append(
                    {
                        "path": path,
                        "error": "invalid_list_item_type",
                        "expected": "list[str]",
                    }
                )
    return errors


def _unexpected_fields(
    value: Mapping[str, Any],
    allowed_fields: frozenset[str],
    *,
    path: str,
) -> list[dict[str, Any]]:
    return [
        {
            "path": f"{path}.{field_name}",
            "error": "unexpected_field",
        }
        for field_name in sorted(str(key) for key in value)
        if field_name not in allowed_fields
    ]


def _resolve_evidence_offsets(
    raw_claim: Mapping[str, Any],
    *,
    section_text: str,
    source_section_id: str,
    item_index: int,
) -> dict[str, Any]:
    evidence_span = str(raw_claim.get("evidence_span") or "")
    start = raw_claim.get("evidence_start")
    end = raw_claim.get("evidence_end")
    diagnostics: list[dict[str, Any]] = []
    if (
        _is_exact_int(start)
        and _is_exact_int(end)
        and 0 <= int(start) <= int(end) <= len(section_text)
        and section_text[int(start):int(end)] == evidence_span
    ):
        diagnostics.extend(
            _evidence_hash_diagnostics(
                raw_claim,
                evidence_span=evidence_span,
                source_section_id=source_section_id,
                item_index=item_index,
            )
        )
        return {
            "status": "valid",
            "evidence_start": int(start),
            "evidence_end": int(end),
            "evidence_span": evidence_span,
            "diagnostics": diagnostics,
        }

    matches = _normalized_evidence_matches(section_text, evidence_span)
    if len(matches) == 1:
        corrected_start, corrected_end = matches[0]
        corrected_span = section_text[corrected_start:corrected_end]
        diagnostics.append(
            _diagnostic(
                "corrected_evidence_offsets",
                "evidence_start/evidence_end were corrected by normalized unique match",
                source_section_id=source_section_id,
                severity="warning",
                item_index=item_index,
                original_start=start,
                original_end=end,
                corrected_start=corrected_start,
                corrected_end=corrected_end,
            )
        )
        diagnostics.extend(
            _evidence_hash_diagnostics(
                raw_claim,
                evidence_span=corrected_span,
                source_section_id=source_section_id,
                item_index=item_index,
            )
        )
        return {
            "status": "valid",
            "evidence_start": corrected_start,
            "evidence_end": corrected_end,
            "evidence_span": corrected_span,
            "diagnostics": diagnostics,
        }
    if len(matches) > 1:
        diagnostics.append(
            _diagnostic(
                "ambiguous_evidence_span",
                "evidence_span matched multiple ranges after whitespace normalization",
                source_section_id=source_section_id,
                severity="error",
                item_index=item_index,
                match_count=len(matches),
                ranges=[
                    {"evidence_start": match_start, "evidence_end": match_end}
                    for match_start, match_end in matches
                ],
            )
        )
        return {"status": "invalid", "diagnostics": diagnostics}
    diagnostics.append(
        _diagnostic(
            "invalid_evidence_span",
            "evidence_span could not be found in the Source Specs section text",
            source_section_id=source_section_id,
            severity="error",
            item_index=item_index,
        )
    )
    return {"status": "invalid", "diagnostics": diagnostics}


def _evidence_hash_diagnostics(
    raw_claim: Mapping[str, Any],
    *,
    evidence_span: str,
    source_section_id: str,
    item_index: int,
) -> list[dict[str, Any]]:
    expected = _hash_normalized_text(evidence_span)
    observed = str(raw_claim.get("evidence_hash") or "")
    if observed == expected:
        return []
    return [
        _diagnostic(
            "evidence_hash_corrected",
            "LLM evidence_hash differed from locally recomputed evidence_hash",
            source_section_id=source_section_id,
            severity="warning",
            item_index=item_index,
            llm_evidence_hash=observed,
            recomputed_evidence_hash=expected,
        )
    ]


def _build_claim_record(
    raw_claim: Mapping[str, Any],
    *,
    source_section_id: str,
    source_hash: str,
    semantic_hash: str,
    generated_at: str,
    evidence_start: int,
    evidence_end: int,
    evidence_span: str,
    schema_version: str,
    claim_identity_version: str,
    retrieval_schema_version: str,
    use_evidence_start_in_identity: bool = False,
) -> dict[str, Any]:
    claim_text = str(raw_claim.get("claim_text") or "")
    target = str(raw_claim.get("target") or "")
    claim_kind = str(raw_claim.get("claim_kind") or "")
    if not claim_text or not target or not claim_kind:
        raise ValueError("SpecClaim record requires claim_text, target, and claim_kind")
    retrieval = dict(raw_claim.get("retrieval") or {})
    target_aliases = list(raw_claim.get("target_aliases") or [])
    scope = str(raw_claim.get("scope") or "")
    condition = str(raw_claim.get("condition") or "")
    value = str(raw_claim.get("value") or "")
    evidence_hash = _hash_normalized_text(evidence_span)
    claim_uid = compute_claim_uid(
        source_section_id=source_section_id,
        evidence_hash=evidence_hash,
        evidence_span=evidence_span,
        claim_text=claim_text,
        target=target,
        claim_identity_version=claim_identity_version,
        evidence_start=evidence_start if use_evidence_start_in_identity else None,
    )
    claim_hash = _hash_mapping(
        {
            "schema_version": schema_version,
            "claim_text": claim_text,
            "target": target,
            "target_aliases": target_aliases,
            "scope": scope,
            "condition": condition,
            "value": value,
            "claim_kind": claim_kind,
            "evidence_hash": evidence_hash,
        }
    )
    retrieval_hash = _hash_mapping(
        {
            "retrieval_schema_version": retrieval_schema_version,
            "sparse_keys": list(retrieval.get("sparse_keys") or []),
            "embedding_text": str(retrieval.get("embedding_text") or ""),
            "conflict_probes": list(retrieval.get("conflict_probes") or []),
        }
    )
    return {
        "claim_uid": claim_uid,
        "display_id": f"{source_section_id}:C{claim_uid.rsplit(':', 1)[-1][:8]}",
        "claim_hash": claim_hash,
        "section_uid": source_section_id,
        "source_section_id": source_section_id,
        "source_hash": source_hash,
        "semantic_hash": semantic_hash,
        "claim_text": claim_text,
        "target": target,
        "target_aliases": target_aliases,
        "scope": scope,
        "condition": condition,
        "value": value,
        "claim_kind": claim_kind,
        "claim_kind_confidence": str(raw_claim.get("claim_kind_confidence") or ""),
        "evidence_span": evidence_span,
        "evidence_start": evidence_start,
        "evidence_end": evidence_end,
        "evidence_hash": evidence_hash,
        "confidence": str(raw_claim.get("confidence") or ""),
        "retrieval": retrieval,
        "retrieval_hash": retrieval_hash,
        "schema_version": schema_version,
        "claim_identity_version": claim_identity_version,
        "retrieval_schema_version": retrieval_schema_version,
        "generated_at": generated_at,
    }


def _usable_cached_section(
    entry: Any,
    *,
    section: _SectionRecord,
    cache_key: str,
) -> Mapping[str, Any] | None:
    if not isinstance(entry, Mapping):
        return None
    if entry.get("source_hash") != section.source_hash:
        return None
    if entry.get("semantic_hash") != section.semantic_hash:
        return None
    if entry.get("prompt_version") != SPEC_CLAIM_PROMPT_VERSION:
        return None
    if entry.get("model") != section.model:
        return None
    if entry.get("effort") != section.effort:
        return None
    if entry.get("schema_version") != SPEC_CLAIM_SCHEMA_VERSION:
        return None
    if entry.get("cache_key") != cache_key:
        return None
    if entry.get("max_claims_per_section") != section.max_claims_per_section:
        return None
    claims = entry.get("claims")
    if not isinstance(claims, list):
        return None
    status = entry.get("status")
    if status not in {SUCCESS_WITH_CLAIMS, SUCCESS_NO_CLAIMS}:
        return None
    return entry


def _stage_status(
    results: Sequence[SpecClaimSectionResult],
    *,
    cache_hits: int,
    section_count: int,
) -> str:
    result_list = list(results)
    if not result_list:
        return "success"
    failed_count = sum(
        1 for result in result_list if result.status == FAILED_SPEC_CLAIM_SECTIONS
    )
    if failed_count == len(result_list):
        return "failed"
    if failed_count:
        return "partial_success"
    if cache_hits == section_count:
        return "skipped_unchanged"
    return "success"


def _normalize_section(
    section: Any,
    *,
    model: str,
    effort: str | None,
    max_claims_per_section: int,
) -> _SectionRecord:
    text = str(_section_value(section, "text", ""))
    source_section_id = str(
        _section_value(
            section,
            "source_section_id",
            _section_value(section, "section_id", ""),
        )
    )
    source_hash = str(_section_value(section, "source_hash", _sha256_text(text)))
    semantic_hash = str(_section_value(section, "semantic_hash", source_hash))
    heading_path_raw = _section_value(section, "heading_path", [])
    heading_path = (
        [str(item) for item in heading_path_raw]
        if isinstance(heading_path_raw, Sequence)
        and not isinstance(heading_path_raw, (str, bytes))
        else []
    )
    return _SectionRecord(
        source_section_id=source_section_id,
        section_id=str(_section_value(section, "section_id", source_section_id)),
        source_hash=source_hash,
        semantic_hash=semantic_hash,
        text=text,
        heading_path=heading_path,
        source_document_id=str(_section_value(section, "source_document_id", "")),
        model=model,
        effort=effort,
        max_claims_per_section=max(0, int(max_claims_per_section)),
    )


def _section_value(section: Any, key: str, default: Any = None) -> Any:
    if isinstance(section, Mapping):
        return section.get(key, default)
    return getattr(section, key, default)


def _normalize_state(state: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, Mapping):
        return {
            "schema_version": SPEC_CLAIM_SCHEMA_VERSION,
            "generated_at": None,
            "sections": {},
        }
    sections = state.get("sections")
    return {
        "schema_version": str(state.get("schema_version") or SPEC_CLAIM_SCHEMA_VERSION),
        "generated_at": state.get("generated_at"),
        "sections": dict(sections) if isinstance(sections, Mapping) else {},
    }


def _normalized_evidence_matches(section_text: str, evidence_span: str) -> list[tuple[int, int]]:
    normalized_section, index_map = _normalize_with_index_map(section_text)
    normalized_evidence = _normalize_text(evidence_span)
    if not normalized_evidence:
        return []
    matches: list[tuple[int, int]] = []
    start_at = 0
    while True:
        found = normalized_section.find(normalized_evidence, start_at)
        if found < 0:
            break
        end = found + len(normalized_evidence)
        if found < len(index_map) and end - 1 < len(index_map):
            matches.append((index_map[found], index_map[end - 1] + 1))
        start_at = found + 1
    return matches


def _normalize_with_index_map(value: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    index_map: list[int] = []
    pending_space_index: int | None = None
    for index, char in enumerate(value):
        if char.isspace():
            if chars:
                pending_space_index = index
            continue
        if pending_space_index is not None and chars:
            chars.append(" ")
            index_map.append(pending_space_index)
        pending_space_index = None
        chars.append(char)
        index_map.append(index)
    return "".join(chars), index_map


def _hash_mapping(payload: Mapping[str, Any]) -> str:
    return "sha256:" + _sha256_text(_stable_json(_jsonable_value(payload)))


def _hash_normalized_text(value: str) -> str:
    return "sha256:" + _sha256_text(_normalize_text(value))


def _normalize_text(value: str) -> str:
    return _SPACE_RE.sub(" ", str(value).strip())


def _identity_text(value: str) -> str:
    return _normalize_text(value).lower()


def _target_identity_text(value: str) -> str:
    return str(value).strip().lower()


def _diagnostic(
    reason_code: str,
    message: str,
    *,
    source_section_id: str | None = None,
    severity: str = "warning",
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "reason_code": reason_code,
        "message": message,
        "stage": SPEC_CLAIMS_STAGE,
        "severity": severity,
    }
    if source_section_id is not None:
        item["source_section_id"] = source_section_id
    item.update(extra)
    return item


def _is_expected_type(value: Any, expected_type: type) -> bool:
    if expected_type is int:
        return _is_exact_int(value)
    if expected_type is list:
        return isinstance(value, list)
    if expected_type is dict:
        return isinstance(value, Mapping)
    return isinstance(value, expected_type)


def _is_exact_int(value: Any) -> bool:
    return type(value) is int


def _type_name(value: type) -> str:
    if value is dict:
        return "object"
    return value.__name__


def _state_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.name == SPEC_CLAIMS_STATE_FILENAME:
        return candidate
    return candidate / SPEC_CLAIMS_STATE_FILENAME


def _jsonl_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.name == SPEC_CLAIMS_JSONL_FILENAME:
        return candidate
    return candidate / SPEC_CLAIMS_JSONL_FILENAME


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True)
                )
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _jsonable_value(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _jsonable_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable_value(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable_value(item) for item in value]
    return value


def _stable_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
