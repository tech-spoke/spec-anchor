"""LLM triage helpers for SpecClaim conflict candidate pairs.

This module owns the prompt, response validation, cache key, cache files,
JSONL filtering, and the triage section of the conflict candidate state file.
Wiring into `/spec-core` is intentionally left for a later integration part.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spec_anchor import claim_retrieval


CONFLICT_CANDIDATE_SCHEMA_VERSION = "conflict-candidate-v1"
CONFLICT_TRIAGE_PROMPT_VERSION = "conflict-triage-prompt-v1"

CONFLICT_CANDIDATE_TRIAGE_STAGE = "conflict_candidate_triage"
CONFLICT_CANDIDATE_TRIAGE_CACHE_DIRNAME = "conflict_candidate_triage"

_ALLOWED_TRIAGE_RESPONSE_FIELDS = frozenset(
    {"send_to_review", "reason", "confidence"}
)
_REQUIRED_TRIAGE_RESPONSE_FIELDS = {
    "send_to_review": bool,
    "reason": str,
    "confidence": str,
}
_DISALLOWED_TRIAGE_RESPONSE_FIELDS = frozenset(
    {"conflict_confirmed", "human_review_required", "resolution"}
)
_ALLOWED_CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})
_EMPTY_SOURCE_HASH = "sha256:" + ("0" * 64)


@dataclass(frozen=True)
class ConflictTriageLlmRequest:
    task: str
    stage: str
    prompt: str
    prompt_version: str
    model: str
    effort: str | None
    source_hash: str
    candidate_uid: str
    left_claim_uid: str
    right_claim_uid: str
    input_hashes: Mapping[str, str]

    def to_provider_payload(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "stage": self.stage,
            "prompt": self.prompt,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "effort": self.effort,
            "source_hash": self.source_hash,
            "candidate_uid": self.candidate_uid,
            "left_claim_uid": self.left_claim_uid,
            "right_claim_uid": self.right_claim_uid,
            "input_hashes": dict(self.input_hashes),
        }


@dataclass(frozen=True)
class ConflictTriageValidation:
    triage: dict[str, Any] | None
    diagnostics: list[dict[str, Any]]
    status: str


@dataclass(frozen=True)
class ConflictCandidateTriageResult:
    candidates: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    state: dict[str, Any]
    status: str
    generated_at: str
    llm_calls: int
    cache_hits: int
    send_to_review_count: int
    send_to_review_false_count: int
    triage_truncated_pairs: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONFLICT_CANDIDATE_SCHEMA_VERSION,
            "prompt_version": CONFLICT_TRIAGE_PROMPT_VERSION,
            "status": self.status,
            "generated_at": self.generated_at,
            "candidates": [dict(candidate) for candidate in self.candidates],
            "diagnostics": dict(self.diagnostics),
            "state": dict(self.state),
            "llm_calls": self.llm_calls,
            "cache_hits": self.cache_hits,
            "send_to_review_count": self.send_to_review_count,
            "send_to_review_false_count": self.send_to_review_false_count,
            "triage_truncated_pairs": self.triage_truncated_pairs,
        }


class ConflictTriageCache:
    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)

    def path_for_key(self, cache_key: str) -> Path:
        return (
            self.cache_dir
            / CONFLICT_CANDIDATE_TRIAGE_CACHE_DIRNAME
            / f"{cache_key}.json"
        )

    def load(self, cache_key: str) -> dict[str, Any] | None:
        path = self.path_for_key(cache_key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, Mapping):
            return None
        if payload.get("cache_key") != cache_key:
            return None
        triage = payload.get("triage")
        if not isinstance(triage, Mapping):
            return None
        validation = validate_conflict_triage_response(triage)
        if validation.status != "success" or validation.triage is None:
            return None
        cached = dict(payload)
        cached["triage"] = validation.triage
        return cached

    def store(self, entry: Mapping[str, Any], cache_key: str) -> Path:
        payload = dict(entry)
        payload["cache_key"] = cache_key
        path = self.path_for_key(cache_key)
        _atomic_write_json(path, payload)
        return path


def build_conflict_triage_prompt(
    left_claim: Mapping[str, Any],
    right_claim: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any] | None = None,
    triage_prompt_version: str = CONFLICT_TRIAGE_PROMPT_VERSION,
    triage_schema_version: str = CONFLICT_CANDIDATE_SCHEMA_VERSION,
) -> str:
    payload = {
        "task": CONFLICT_CANDIDATE_TRIAGE_STAGE,
        "instructions": [
            "Decide only whether this SpecClaim pair is worth sending to Conflict Review.",
            "Use the two claim records and their evidence_span values.",
            "Ask whether the claims handle the same or nearby target, whether their scope can overlap, and whether review is worthwhile.",
            "Do not decide that a conflict is confirmed.",
            "Do not decide that human review is required.",
            "Do not choose a resolution or source priority.",
            "Return strict JSON with exactly send_to_review, reason, and confidence.",
        ],
        "prompt_version": triage_prompt_version,
        "schema_version": triage_schema_version,
        "candidate": _candidate_prompt_record(candidate or {}),
        "claims": [
            _claim_prompt_record(left_claim),
            _claim_prompt_record(right_claim),
        ],
        "output_shape": {
            "send_to_review": True,
            "reason": "short explanation",
            "confidence": "high|medium|low",
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def validate_conflict_triage_response(response: Any) -> ConflictTriageValidation:
    diagnostics: list[dict[str, Any]] = []
    parsed = _parse_response_object(response, diagnostics)
    if parsed is None:
        return ConflictTriageValidation(None, diagnostics, "failed")

    schema_errors = _validate_triage_response_schema(parsed)
    if schema_errors:
        diagnostics.append(
            _diagnostic(
                "schema_validation_failure",
                "Conflict candidate triage response schema validation failed",
                severity="error",
                errors=schema_errors,
            )
        )
        return ConflictTriageValidation(None, diagnostics, "failed")

    return ConflictTriageValidation(
        triage={
            "send_to_review": bool(parsed["send_to_review"]),
            "reason": str(parsed["reason"]),
            "confidence": str(parsed["confidence"]),
        },
        diagnostics=diagnostics,
        status="success",
    )


def compute_conflict_triage_cache_key(
    *,
    left_claim_uid: str,
    left_claim_hash: str,
    left_retrieval_hash: str,
    left_source_hash: str,
    right_claim_uid: str,
    right_claim_hash: str,
    right_retrieval_hash: str,
    right_source_hash: str,
    triage_prompt_version: str = CONFLICT_TRIAGE_PROMPT_VERSION,
    triage_schema_version: str = CONFLICT_CANDIDATE_SCHEMA_VERSION,
    triage_model: str,
    triage_effort: str | None,
) -> str:
    claims = [
        {
            "claim_uid": str(left_claim_uid),
            "claim_hash": str(left_claim_hash),
            "retrieval_hash": str(left_retrieval_hash),
            "source_hash": str(left_source_hash),
        },
        {
            "claim_uid": str(right_claim_uid),
            "claim_hash": str(right_claim_hash),
            "retrieval_hash": str(right_retrieval_hash),
            "source_hash": str(right_source_hash),
        },
    ]
    claims.sort(key=lambda item: item["claim_uid"])
    payload = {
        "claims": claims,
        "triage_prompt_version": triage_prompt_version,
        "triage_schema_version": triage_schema_version,
        "triage_model": triage_model,
        "triage_effort": triage_effort,
    }
    return "sha256:" + _sha256_text(_stable_json(payload))


def generate_conflict_candidate_triage_result(
    candidates: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    *,
    provider: Any,
    model: str = "fake",
    effort: str | None = None,
    triage_max_pairs: int = 30,
    cache_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    state_path: str | Path | None = None,
    previous_state: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
    timeout_sec: int = 120,
    triage_prompt_version: str = CONFLICT_TRIAGE_PROMPT_VERSION,
    triage_schema_version: str = CONFLICT_CANDIDATE_SCHEMA_VERSION,
) -> ConflictCandidateTriageResult:
    generated_at = generated_at or _now()
    claims_by_uid = _claims_by_uid(claims)
    limit = max(0, int(triage_max_pairs))
    cache = ConflictTriageCache(cache_dir) if cache_dir is not None else None
    loaded_state = (
        claim_retrieval.read_conflict_candidate_pairs_state(state_path)
        if previous_state is None and state_path is not None
        else dict(previous_state or {})
    )

    output_candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    cache_key_by_candidate_uid: dict[str, str] = {}
    evaluated_candidate_uids: list[str] = []
    false_candidate_uids: list[str] = []
    failed_candidate_uids: list[str] = []
    llm_calls = 0
    cache_hits = 0

    for index, raw_candidate in enumerate(candidates):
        candidate = dict(raw_candidate)
        candidate_uid = str(candidate.get("candidate_uid") or "")
        if index >= limit:
            continue
        pair = _candidate_claims(candidate, claims_by_uid)
        if pair is None:
            failed_candidate_uids.append(candidate_uid)
            diagnostics.append(
                _diagnostic(
                    "missing_candidate_claim",
                    "Conflict candidate references a claim that is not available",
                    severity="error",
                    candidate_uid=candidate_uid,
                )
            )
            continue
        left_claim, right_claim = pair
        cache_key = _cache_key_for_candidate(
            left_claim,
            right_claim,
            model=model,
            effort=effort,
            triage_prompt_version=triage_prompt_version,
            triage_schema_version=triage_schema_version,
        )
        cache_key_by_candidate_uid[candidate_uid] = cache_key
        cached = cache.load(cache_key) if cache is not None else None
        if cached is not None:
            validation = validate_conflict_triage_response(cached["triage"])
            cache_hits += 1
        else:
            request = _build_llm_request(
                candidate,
                left_claim,
                right_claim,
                cache_key=cache_key,
                model=model,
                effort=effort,
                triage_prompt_version=triage_prompt_version,
                triage_schema_version=triage_schema_version,
            )
            try:
                response = provider.generate(request, timeout_sec=timeout_sec)
            except Exception as exc:
                llm_calls += 1
                failed_candidate_uids.append(candidate_uid)
                diagnostics.append(
                    _diagnostic(
                        "llm_call_failure",
                        "Conflict candidate triage LLM call failed",
                        severity="error",
                        candidate_uid=candidate_uid,
                        exception_type=exc.__class__.__name__,
                        exception_message=str(exc),
                        model=model,
                        effort=effort,
                        prompt_version=triage_prompt_version,
                    )
                )
                continue
            llm_calls += 1
            validation = validate_conflict_triage_response(response)
            if validation.status == "success" and validation.triage is not None and cache is not None:
                cache.store(
                    {
                        "schema_version": triage_schema_version,
                        "prompt_version": triage_prompt_version,
                        "model": model,
                        "effort": effort,
                        "generated_at": generated_at,
                        "candidate_uid": candidate_uid,
                        "left_claim_uid": str(left_claim["claim_uid"]),
                        "right_claim_uid": str(right_claim["claim_uid"]),
                        "triage": validation.triage,
                    },
                    cache_key,
                )
        diagnostics.extend(
            _candidate_diagnostic(candidate_uid, item)
            for item in validation.diagnostics
        )
        if validation.status != "success" or validation.triage is None:
            failed_candidate_uids.append(candidate_uid)
            continue
        evaluated_candidate_uids.append(candidate_uid)
        if validation.triage["send_to_review"] is True:
            output_candidates.append(_candidate_with_triage(candidate, validation.triage))
        else:
            false_candidate_uids.append(candidate_uid)

    triage_truncated_pairs = max(0, len(candidates) - limit)
    status = _triage_status(
        candidate_count=len(candidates),
        failed_count=len(failed_candidate_uids),
        processed_count=len(evaluated_candidate_uids),
        truncated_count=triage_truncated_pairs,
    )
    diagnostics_map = {
        "status": status,
        "schema_version": triage_schema_version,
        "prompt_version": triage_prompt_version,
        "candidate_count": len(candidates),
        "processed_candidate_count": len(evaluated_candidate_uids),
        "send_to_review_count": len(output_candidates),
        "send_to_review_false_count": len(false_candidate_uids),
        "triage_truncated_pairs": triage_truncated_pairs,
        "failed_candidate_count": len(failed_candidate_uids),
        "failed_candidate_uids": failed_candidate_uids,
        "cache_hits": cache_hits,
        "llm_calls": llm_calls,
        "diagnostics": diagnostics,
    }
    state = _merge_triage_state(
        loaded_state,
        triage_state=build_conflict_candidate_triage_state(
            output_candidates,
            model=model,
            effort=effort,
            triage_max_pairs=limit,
            cache_key_by_candidate_uid=cache_key_by_candidate_uid,
            evaluated_candidate_uids=evaluated_candidate_uids,
            false_candidate_uids=false_candidate_uids,
            failed_candidate_uids=failed_candidate_uids,
            diagnostics=diagnostics_map,
            generated_at=generated_at,
            triage_prompt_version=triage_prompt_version,
            triage_schema_version=triage_schema_version,
        ),
        generated_at=generated_at,
        triage_schema_version=triage_schema_version,
    )

    if output_path is not None:
        write_conflict_candidate_pairs_jsonl(output_path, output_candidates)
    if state_path is not None:
        claim_retrieval.write_conflict_candidate_pairs_state(state_path, state)

    return ConflictCandidateTriageResult(
        candidates=output_candidates,
        diagnostics=diagnostics_map,
        state=state,
        status=status,
        generated_at=generated_at,
        llm_calls=llm_calls,
        cache_hits=cache_hits,
        send_to_review_count=len(output_candidates),
        send_to_review_false_count=len(false_candidate_uids),
        triage_truncated_pairs=triage_truncated_pairs,
    )


def generate_conflict_candidate_triage(
    candidates: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    *,
    provider: Any,
    model: str = "fake",
    effort: str | None = None,
    triage_max_pairs: int = 30,
    cache_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    state_path: str | Path | None = None,
    previous_state: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    return generate_conflict_candidate_triage_result(
        candidates,
        claims,
        provider=provider,
        model=model,
        effort=effort,
        triage_max_pairs=triage_max_pairs,
        cache_dir=cache_dir,
        output_path=output_path,
        state_path=state_path,
        previous_state=previous_state,
        generated_at=generated_at,
        timeout_sec=timeout_sec,
    ).to_dict()


def build_conflict_candidate_triage_state(
    candidates: Sequence[Mapping[str, Any]],
    *,
    model: str,
    effort: str | None,
    triage_max_pairs: int,
    cache_key_by_candidate_uid: Mapping[str, str],
    evaluated_candidate_uids: Sequence[str],
    false_candidate_uids: Sequence[str],
    failed_candidate_uids: Sequence[str],
    diagnostics: Mapping[str, Any],
    generated_at: str | None = None,
    triage_prompt_version: str = CONFLICT_TRIAGE_PROMPT_VERSION,
    triage_schema_version: str = CONFLICT_CANDIDATE_SCHEMA_VERSION,
) -> dict[str, Any]:
    send_to_review_candidate_uids = sorted(
        str(candidate.get("candidate_uid") or "")
        for candidate in candidates
        if str(candidate.get("candidate_uid") or "")
    )
    settings = {
        "prompt_version": triage_prompt_version,
        "schema_version": triage_schema_version,
        "model": model,
        "effort": effort,
        "triage_max_pairs": max(0, int(triage_max_pairs)),
    }
    return {
        "schema_version": triage_schema_version,
        "prompt_version": triage_prompt_version,
        "model": model,
        "effort": effort,
        "triage_max_pairs": max(0, int(triage_max_pairs)),
        "triage_settings_fingerprint": "sha256:" + _sha256_text(_stable_json(settings)),
        "candidate_uids": sorted(set(evaluated_candidate_uids)),
        "send_to_review_candidate_uids": send_to_review_candidate_uids,
        "send_to_review_false_candidate_uids": sorted(set(false_candidate_uids)),
        "failed_candidate_uids": sorted(set(failed_candidate_uids)),
        "cache_key_by_candidate_uid": dict(sorted(cache_key_by_candidate_uid.items())),
        "send_to_review_count": int(diagnostics.get("send_to_review_count") or 0),
        "send_to_review_false_count": int(
            diagnostics.get("send_to_review_false_count") or 0
        ),
        "triage_truncated_pairs": int(diagnostics.get("triage_truncated_pairs") or 0),
        "llm_calls": int(diagnostics.get("llm_calls") or 0),
        "cache_hits": int(diagnostics.get("cache_hits") or 0),
        "generated_at": generated_at,
    }


def read_conflict_candidate_pairs_state(path: str | Path) -> dict[str, Any]:
    return claim_retrieval.read_conflict_candidate_pairs_state(path)


def write_conflict_candidate_pairs_state(
    path: str | Path,
    state: Mapping[str, Any],
) -> Path:
    return claim_retrieval.write_conflict_candidate_pairs_state(path, state)


def write_conflict_candidate_pairs_jsonl(
    path: str | Path,
    candidates: Sequence[Mapping[str, Any]],
    *,
    active_claim_uids: Sequence[str] | None = None,
) -> Path:
    jsonl_path = _jsonl_path(path)
    active = set(active_claim_uids or [])
    records = [
        dict(candidate)
        for candidate in candidates
        if _candidate_has_send_to_review_triage(candidate)
        and (
            active_claim_uids is None
            or (
                str(candidate.get("left_claim_uid") or "") in active
                and str(candidate.get("right_claim_uid") or "") in active
            )
        )
    ]
    records.sort(key=lambda item: str(item.get("candidate_uid") or ""))
    _atomic_write_jsonl(jsonl_path, records)
    return jsonl_path


def read_conflict_candidate_pairs_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return claim_retrieval.read_conflict_candidate_pairs_jsonl(path)


def _validate_triage_response_schema(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for field_name in sorted(str(key) for key in response):
        if field_name in _DISALLOWED_TRIAGE_RESPONSE_FIELDS:
            errors.append({"path": f"$.{field_name}", "error": "forbidden_field"})
        elif field_name not in _ALLOWED_TRIAGE_RESPONSE_FIELDS:
            errors.append({"path": f"$.{field_name}", "error": "unexpected_field"})
    for field_name, expected_type in _REQUIRED_TRIAGE_RESPONSE_FIELDS.items():
        if field_name not in response:
            errors.append({"path": f"$.{field_name}", "error": "missing_required_field"})
            continue
        value = response[field_name]
        if expected_type is bool:
            if type(value) is not bool:
                errors.append(
                    {
                        "path": f"$.{field_name}",
                        "error": "invalid_type",
                        "expected": "bool",
                        "actual": type(value).__name__,
                    }
                )
            continue
        if not isinstance(value, expected_type):
            errors.append(
                {
                    "path": f"$.{field_name}",
                    "error": "invalid_type",
                    "expected": expected_type.__name__,
                    "actual": type(value).__name__,
                }
            )
    confidence = response.get("confidence")
    if isinstance(confidence, str) and confidence not in _ALLOWED_CONFIDENCE_VALUES:
        errors.append(
            {
                "path": "$.confidence",
                "error": "invalid_enum",
                "allowed": sorted(_ALLOWED_CONFIDENCE_VALUES),
                "actual": confidence,
            }
        )
    return errors


def _parse_response_object(
    response: Any,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if isinstance(response, (str, bytes, bytearray)):
        try:
            parsed = json.loads(
                response.decode("utf-8")
                if isinstance(response, (bytes, bytearray))
                else response
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            diagnostics.append(
                _diagnostic(
                    "json_parse_failure",
                    "Conflict candidate triage response is not valid JSON",
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
                "Conflict candidate triage response root must be an object",
                severity="error",
                actual_type=type(response).__name__,
            )
        )
        return None
    return dict(response)


def _build_llm_request(
    candidate: Mapping[str, Any],
    left_claim: Mapping[str, Any],
    right_claim: Mapping[str, Any],
    *,
    cache_key: str,
    model: str,
    effort: str | None,
    triage_prompt_version: str,
    triage_schema_version: str,
) -> ConflictTriageLlmRequest:
    left_source_hash = str(left_claim.get("source_hash") or _EMPTY_SOURCE_HASH)
    right_source_hash = str(right_claim.get("source_hash") or _EMPTY_SOURCE_HASH)
    combined_source_hash = "sha256:" + _sha256_text(
        _stable_json([left_source_hash, right_source_hash])
    )
    return ConflictTriageLlmRequest(
        task=CONFLICT_CANDIDATE_TRIAGE_STAGE,
        stage=CONFLICT_CANDIDATE_TRIAGE_STAGE,
        prompt=build_conflict_triage_prompt(
            left_claim,
            right_claim,
            candidate=candidate,
            triage_prompt_version=triage_prompt_version,
            triage_schema_version=triage_schema_version,
        ),
        prompt_version=triage_prompt_version,
        model=model,
        effort=effort,
        source_hash=combined_source_hash,
        candidate_uid=str(candidate.get("candidate_uid") or ""),
        left_claim_uid=str(left_claim["claim_uid"]),
        right_claim_uid=str(right_claim["claim_uid"]),
        input_hashes={
            "cache_key": cache_key,
            "left_claim_hash": str(left_claim.get("claim_hash") or ""),
            "left_retrieval_hash": str(left_claim.get("retrieval_hash") or ""),
            "left_source_hash": left_source_hash,
            "right_claim_hash": str(right_claim.get("claim_hash") or ""),
            "right_retrieval_hash": str(right_claim.get("retrieval_hash") or ""),
            "right_source_hash": right_source_hash,
        },
    )


def _cache_key_for_candidate(
    left_claim: Mapping[str, Any],
    right_claim: Mapping[str, Any],
    *,
    model: str,
    effort: str | None,
    triage_prompt_version: str,
    triage_schema_version: str,
) -> str:
    return compute_conflict_triage_cache_key(
        left_claim_uid=str(left_claim["claim_uid"]),
        left_claim_hash=str(left_claim.get("claim_hash") or ""),
        left_retrieval_hash=str(left_claim.get("retrieval_hash") or ""),
        left_source_hash=str(left_claim.get("source_hash") or _EMPTY_SOURCE_HASH),
        right_claim_uid=str(right_claim["claim_uid"]),
        right_claim_hash=str(right_claim.get("claim_hash") or ""),
        right_retrieval_hash=str(right_claim.get("retrieval_hash") or ""),
        right_source_hash=str(right_claim.get("source_hash") or _EMPTY_SOURCE_HASH),
        triage_prompt_version=triage_prompt_version,
        triage_schema_version=triage_schema_version,
        triage_model=model,
        triage_effort=effort,
    )


def _candidate_claims(
    candidate: Mapping[str, Any],
    claims_by_uid: Mapping[str, Mapping[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    left_uid = str(candidate.get("left_claim_uid") or "")
    right_uid = str(candidate.get("right_claim_uid") or "")
    left_claim = claims_by_uid.get(left_uid)
    right_claim = claims_by_uid.get(right_uid)
    if left_claim is None or right_claim is None:
        return None
    return left_claim, right_claim


def _candidate_with_triage(
    candidate: Mapping[str, Any],
    triage: Mapping[str, Any],
) -> dict[str, Any]:
    record = dict(candidate)
    record["triage"] = {
        "send_to_review": bool(triage["send_to_review"]),
        "reason": str(triage["reason"]),
        "confidence": str(triage["confidence"]),
    }
    signals = [str(value) for value in record.get("signals") or []]
    if "llm_triage_send_to_review" not in signals:
        signals.append("llm_triage_send_to_review")
    record["signals"] = signals
    return record


def _candidate_has_send_to_review_triage(candidate: Mapping[str, Any]) -> bool:
    triage = candidate.get("triage")
    return isinstance(triage, Mapping) and triage.get("send_to_review") is True


def _claim_prompt_record(claim: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "claim_uid": str(claim["claim_uid"]),
        "claim_hash": str(claim.get("claim_hash") or ""),
        "retrieval_hash": str(claim.get("retrieval_hash") or ""),
        "source_section_id": str(claim.get("source_section_id") or ""),
        "source_hash": str(claim.get("source_hash") or ""),
        "claim_text": str(claim.get("claim_text") or ""),
        "target": str(claim.get("target") or ""),
        "target_aliases": [str(value) for value in claim.get("target_aliases") or []],
        "scope": str(claim.get("scope") or ""),
        "condition": str(claim.get("condition") or ""),
        "value": str(claim.get("value") or ""),
        "claim_kind": str(claim.get("claim_kind") or ""),
        "confidence": str(claim.get("confidence") or ""),
        "evidence_span": str(claim.get("evidence_span") or ""),
        "evidence_start": _int_or_none(claim.get("evidence_start")),
        "evidence_end": _int_or_none(claim.get("evidence_end")),
        "evidence_hash": str(claim.get("evidence_hash") or ""),
    }


def _candidate_prompt_record(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_uid": str(candidate.get("candidate_uid") or ""),
        "left_claim_uid": str(candidate.get("left_claim_uid") or ""),
        "right_claim_uid": str(candidate.get("right_claim_uid") or ""),
        "shared_target": str(candidate.get("shared_target") or ""),
        "retrieval_sources": [
            str(value) for value in candidate.get("retrieval_sources") or []
        ],
        "signals": [str(value) for value in candidate.get("signals") or []],
    }


def _claims_by_uid(claims: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for claim in claims:
        uid = str(claim.get("claim_uid") or "")
        if uid:
            result[uid] = dict(claim)
    return dict(sorted(result.items()))


def _candidate_diagnostic(
    candidate_uid: str,
    diagnostic: Mapping[str, Any],
) -> dict[str, Any]:
    item = dict(diagnostic)
    if candidate_uid:
        item["candidate_uid"] = candidate_uid
    return item


def _merge_triage_state(
    previous_state: Mapping[str, Any],
    *,
    triage_state: Mapping[str, Any],
    generated_at: str,
    triage_schema_version: str,
) -> dict[str, Any]:
    state = dict(previous_state)
    state["schema_version"] = triage_schema_version
    state["generated_at"] = generated_at
    state["triage"] = dict(triage_state)
    return state


def _triage_status(
    *,
    candidate_count: int,
    failed_count: int,
    processed_count: int,
    truncated_count: int,
) -> str:
    if candidate_count == 0:
        return "success"
    if failed_count and failed_count >= min(candidate_count, processed_count + failed_count):
        return "failed"
    if failed_count:
        return "partial_success"
    if truncated_count:
        return "partial_success"
    return "success"


def _diagnostic(
    reason_code: str,
    message: str,
    *,
    severity: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "reason_code": reason_code,
        "message": message,
        "severity": severity,
        **extra,
    }


def _jsonl_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.name == claim_retrieval.CONFLICT_CANDIDATE_PAIRS_JSONL_FILENAME:
        return candidate
    return candidate / claim_retrieval.CONFLICT_CANDIDATE_PAIRS_JSONL_FILENAME


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
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
