"""Lightweight Conflict Review Item helpers.

This module keeps the G-09 conflict review contract intentionally plain:
dict-shaped items in, dict-shaped items out, with small helpers for judging,
human decisions, freshness, and evidence filtering.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


DECISIONS = {
    "prefer_a",
    "prefer_b",
    "conditional",
    "dismiss",
    "needs_source_update",
    "defer",
    "task_scope_resolution",
}
RESOLVED_DECISIONS = {"prefer_a", "prefer_b", "conditional", "task_scope_resolution"}
PENDING_DECISIONS = {"needs_source_update", "defer"}
STATUSES = {"pending", "resolved", "dismissed"}
SCOPES = {"global", "source_pair", "section_pair", "task_scope"}
REFLECTION_STATUSES = {"unreflected", "reflected", "not_required"}

_DEFAULT_DECISION_OPTIONS = [
    {"id": "prefer_a", "label": "Prefer source A"},
    {"id": "prefer_b", "label": "Prefer source B"},
    {"id": "conditional", "label": "Use a conditional rule"},
    {"id": "dismiss", "label": "Dismiss as not a conflict"},
    {"id": "needs_source_update", "label": "Update source specs"},
    {"id": "defer", "label": "Defer decision"},
    {"id": "task_scope_resolution", "label": "Resolve for this task only"},
]

@dataclass
class ConflictReviewResult:
    conflict_review_items: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    freshness_report: dict[str, Any]
    pending_conflict_count: int = 0
    selection_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    non_pending_conflict_signals: list[dict[str, Any]] = field(default_factory=list)
    # Token usage collected from each _call_judge invocation.
    # Each entry is the __spec_anchor_usage dict returned by the LLM provider.
    usage_list: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_review_items": self.conflict_review_items,
            "diagnostics": self.diagnostics,
            "potential_conflicts": self.diagnostics,
            "selection_diagnostics": self.selection_diagnostics,
            "non_pending_conflict_signals": self.non_pending_conflict_signals,
            "freshness_report": self.freshness_report,
            "pending_conflict_count": self.pending_conflict_count,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str | None = None) -> str:
    return value or _now_iso()


def _copy_items(items: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in (items or [])]


def _coerce_conflict_candidate_pairs(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        return _coerce_conflict_candidate_pairs(value.to_dict())
    if hasattr(value, "conflict_candidate_pairs"):
        nested = getattr(value, "conflict_candidate_pairs")
        if nested is not value:
            return _coerce_conflict_candidate_pairs(nested)
    if isinstance(value, Mapping):
        if "left_claim_uid" in value and "right_claim_uid" in value:
            return [deepcopy(dict(value))]
        items: list[dict[str, Any]] = []
        for key in ("conflict_candidate_pairs", "candidate_pairs", "pairs"):
            items.extend(_coerce_conflict_candidate_pairs(value.get(key)))
        return items
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = []
        for item in value:
            items.extend(_coerce_conflict_candidate_pairs(item))
        return items
    return []


def _section_id(section: dict[str, Any]) -> str:
    return str(section.get("source_section_id") or section.get("section_id") or section.get("id") or "")


def _section_map(sections: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {_section_id(section): section for section in (sections or []) if _section_id(section)}


def _hash_for_section(section: dict[str, Any]) -> str | None:
    value = section.get("source_hash") or section.get("hash") or section.get("semantic_hash")
    return str(value) if value is not None else None


def _decision_option_ids(item: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for option in item.get("decision_options", []):
        if isinstance(option, str):
            ids.add(option)
        elif isinstance(option, dict):
            option_id = option.get("id", option.get("decision", option.get("value")))
            if option_id:
                ids.add(str(option_id))
    return ids


def _normalize_decision_options(options: Any = None) -> list[dict[str, str]]:
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []

    raw_options = options if isinstance(options, list) else []
    for option in raw_options:
        if isinstance(option, str):
            option_id = option
            label = option.replace("_", " ")
        elif isinstance(option, dict):
            option_id = str(option.get("id", option.get("decision", option.get("value", ""))))
            label = str(option.get("label") or option_id.replace("_", " "))
        else:
            continue
        if option_id in DECISIONS and option_id not in seen:
            normalized.append({"id": option_id, "label": label})
            seen.add(option_id)

    for option in _DEFAULT_DECISION_OPTIONS:
        if option["id"] not in seen:
            normalized.append(dict(option))
            seen.add(option["id"])
    return normalized


def _source_ref(section: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    section_id = _section_id(section) or fallback_id
    ref = {
        "source_section_id": section_id,
        "source_hash": _hash_for_section(section),
    }
    if section.get("source_document_id"):
        ref["source_document_id"] = section["source_document_id"]
    if section.get("source_span"):
        ref["source_span"] = deepcopy(section["source_span"])
    return {key: value for key, value in ref.items() if value is not None}


def _base_source_hash(refs: list[dict[str, Any]]) -> list[dict[str, str]]:
    hashes: list[dict[str, str]] = []
    for ref in refs:
        source_ref = ref.get("source_section_id") or ref.get("source_ref") or ref.get("ref")
        source_hash = ref.get("source_hash") or ref.get("hash")
        if source_ref and source_hash:
            hashes.append({"source_ref": str(source_ref), "hash": str(source_hash)})
    return hashes


def _pair_key(source_id: str, target_id: str) -> tuple[str, str]:
    return tuple(sorted((source_id, target_id)))


def _get_llm_batch_concurrency(
    config: Any = None,
    limits: Any = None,
    default: int = 4,
) -> int:
    sentinel = object()
    value: Any = sentinel
    if limits is not None:
        if isinstance(limits, Mapping):
            value = limits.get("llm_batch_concurrency", sentinel)
        else:
            value = getattr(limits, "llm_batch_concurrency", sentinel)
    if value is sentinel:
        if isinstance(config, Mapping):
            limit_source = config.get("limits")
        else:
            limit_source = getattr(config, "limits", None)
        if isinstance(limit_source, Mapping):
            value = limit_source.get("llm_batch_concurrency", sentinel)
        elif limit_source is not None:
            value = getattr(limit_source, "llm_batch_concurrency", sentinel)
    if value is sentinel:
        if isinstance(config, Mapping):
            value = config.get("llm_batch_concurrency", default)
        else:
            value = getattr(config, "llm_batch_concurrency", default)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _claims_by_uid(claims: Any) -> dict[str, dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if claims is None:
        return {}
    if hasattr(claims, "to_dict"):
        return _claims_by_uid(claims.to_dict())
    if isinstance(claims, Mapping):
        if "claim_uid" in claims:
            records = [dict(claims)]
        else:
            for key in ("claims", "spec_claims"):
                nested = claims.get(key)
                if nested is not None:
                    return _claims_by_uid(nested)
    elif isinstance(claims, Sequence) and not isinstance(claims, (str, bytes)):
        records = [dict(item) for item in claims if isinstance(item, Mapping)]
    return {
        str(record.get("claim_uid")): record
        for record in records
        if str(record.get("claim_uid") or "")
    }


def _triage_sends_to_review(pair: Mapping[str, Any]) -> bool:
    triage = pair.get("triage")
    return isinstance(triage, Mapping) and triage.get("send_to_review") is True


def _pair_evidence_by_claim_uid(pair: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    evidence = pair.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        return result
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        claim_uid = str(item.get("claim_uid") or "")
        if claim_uid:
            result[claim_uid] = dict(item)
    return result


def _claim_source_section_id(
    *,
    claim_uid: str,
    claim: Mapping[str, Any] | None,
    evidence: Mapping[str, Any] | None,
    pair: Mapping[str, Any],
    side: str,
) -> str:
    if claim is not None:
        source_id = str(claim.get("source_section_id") or "")
        if source_id:
            return source_id
    if evidence is not None:
        section_id = str(
            evidence.get("source_section_id")
            or evidence.get("section_uid")
            or evidence.get("section_id")
            or ""
        )
        if section_id:
            return section_id
    for key in (
        f"{side}_source_section_id",
        f"{side}_section_id",
        f"{side}_section_uid",
    ):
        section_id = str(pair.get(key) or "")
        if section_id:
            return section_id
    return claim_uid


def _claim_review_record(
    *,
    claim_uid: str,
    claim: Mapping[str, Any] | None,
    evidence: Mapping[str, Any] | None,
    source_section_id: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "claim_uid": claim_uid,
        "source_section_id": source_section_id,
    }
    if claim is not None:
        for key in (
            "display_id",
            "claim_text",
            "target",
            "target_aliases",
            "scope",
            "condition",
            "value",
            "claim_kind",
            "confidence",
            "evidence_span",
            "evidence_start",
            "evidence_end",
            "evidence_hash",
            "claim_hash",
            "source_hash",
        ):
            if key in claim:
                record[key] = deepcopy(claim[key])
    if evidence is not None:
        for key in ("evidence_span", "evidence_start", "evidence_end", "evidence_hash"):
            if key in evidence and key not in record:
                record[key] = deepcopy(evidence[key])
    return record


def _normalize_spec_claim_pair(
    pair: Mapping[str, Any],
    *,
    claims_by_uid: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    left_uid = str(pair.get("left_claim_uid") or "")
    right_uid = str(pair.get("right_claim_uid") or "")
    if not left_uid or not right_uid or left_uid == right_uid:
        return None
    if not _triage_sends_to_review(pair):
        return None

    evidence_by_uid = _pair_evidence_by_claim_uid(pair)
    left_claim = claims_by_uid.get(left_uid)
    right_claim = claims_by_uid.get(right_uid)
    left_evidence = evidence_by_uid.get(left_uid)
    right_evidence = evidence_by_uid.get(right_uid)
    left_section_id = _claim_source_section_id(
        claim_uid=left_uid,
        claim=left_claim,
        evidence=left_evidence,
        pair=pair,
        side="left",
    )
    right_section_id = _claim_source_section_id(
        claim_uid=right_uid,
        claim=right_claim,
        evidence=right_evidence,
        pair=pair,
        side="right",
    )
    normalized = deepcopy(dict(pair))
    normalized["left_claim_uid"] = left_uid
    normalized["right_claim_uid"] = right_uid
    normalized["source_section_id"] = left_section_id
    normalized["target_section_id"] = right_section_id
    normalized["claims"] = [
        _claim_review_record(
            claim_uid=left_uid,
            claim=left_claim,
            evidence=left_evidence,
            source_section_id=left_section_id,
        ),
        _claim_review_record(
            claim_uid=right_uid,
            claim=right_claim,
            evidence=right_evidence,
            source_section_id=right_section_id,
        ),
    ]
    return normalized


def select_conflict_judging_pairs(
    conflict_candidate_pairs: Any = None,
    *,
    spec_claims: Any = None,
    claims: Any = None,
) -> list[dict[str, Any]]:
    """Select triaged SpecClaim candidate pairs for Conflict Review."""

    claim_index = _claims_by_uid(claims if claims is not None else spec_claims)
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for pair in _coerce_conflict_candidate_pairs(conflict_candidate_pairs):
        normalized = _normalize_spec_claim_pair(pair, claims_by_uid=claim_index)
        if normalized is None:
            continue
        key = tuple(sorted((normalized["left_claim_uid"], normalized["right_claim_uid"])))
        if key in seen:
            continue
        selected.append(normalized)
        seen.add(key)
    return selected


def _call_judge(conflict_judge: Any, request: dict[str, Any], timeout_sec: int = 5) -> dict[str, Any]:
    if conflict_judge is None:
        return {"outcome": "needs_human_review", "severity": "medium"}

    for method_name in ("judge_conflict", "judge", "generate"):
        method = getattr(conflict_judge, method_name, None)
        if callable(method):
            try:
                return dict(method(request, timeout_sec=timeout_sec))
            except TypeError:
                return dict(method(request))
    if callable(conflict_judge):
        return dict(conflict_judge(request))
    raise TypeError("conflict_judge must expose judge_conflict, judge, generate, or be callable")


def _conflict_id_for_pair(pair: dict[str, Any]) -> str:
    candidate_uid = str(pair.get("candidate_uid") or "")
    if candidate_uid:
        return "conflict-" + candidate_uid.replace(":", "-").replace("/", "-").replace("#", "-")
    left_uid = str(pair.get("left_claim_uid", "")).replace(":", "-").replace("/", "-").replace("#", "-")
    right_uid = str(pair.get("right_claim_uid", "")).replace(":", "-").replace("/", "-").replace("#", "-")
    return f"conflict-{left_uid}--{right_uid}".strip("-")


def _source_refs_for_pair(
    pair: Mapping[str, Any],
    sections_by_id: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for claim in pair.get("claims") or []:
        if not isinstance(claim, Mapping):
            continue
        section_id = str(claim.get("source_section_id") or "")
        if not section_id:
            continue
        section = sections_by_id.get(section_id, {"source_section_id": section_id})
        ref = _source_ref(section, section_id)
        source_hash = claim.get("source_hash")
        if source_hash and "source_hash" not in ref:
            ref["source_hash"] = str(source_hash)
        refs.append(ref)
    if refs:
        return refs
    return [
        _source_ref(
            sections_by_id.get(str(pair.get(key)), {"source_section_id": str(pair.get(key) or "")}),
            str(pair.get(key) or ""),
        )
        for key in ("source_section_id", "target_section_id")
        if str(pair.get(key) or "")
    ]


def _build_conflict_item(
    pair: dict[str, Any],
    sections_by_id: dict[str, dict[str, Any]],
    judge_payload: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> ConflictReviewResult:
    source_refs = _source_refs_for_pair(pair, sections_by_id)
    now = _timestamp(generated_at)

    item = {
        "conflict_id": str(judge_payload.get("conflict_id") or _conflict_id_for_pair(pair)),
        "status": "pending",
        "severity": str(judge_payload.get("severity") or "medium"),
        "source_refs": source_refs,
        "claims": deepcopy(judge_payload.get("claims") or pair.get("claims") or []),
        "why_conflicting": str(judge_payload.get("why_conflicting") or pair.get("reason") or "Potential source specifications conflict."),
        "why_llm_cannot_decide": str(
            judge_payload.get("why_llm_cannot_decide")
            or judge_payload.get("why_unresolved")
            or "Existing evidence does not establish a safe priority."
        ),
        "related_sections": [],
        "spec_claim_pair": deepcopy(pair),
        "decision_options": _normalize_decision_options(judge_payload.get("decision_options")),
        "recommended_next_action": str(
            judge_payload.get("recommended_next_action") or "Ask a human to decide this conflict."
        ),
        "base_source_hashes": _base_source_hash(source_refs),
        "valid_scope": "global",
        "reflection_status": "unreflected",
        "reflected_refs": [],
        "stale_resolution": False,
        "created_at": now,
        "updated_at": now,
    }
    return validate_conflict_review_item(item=item, generated_at=generated_at)


def _build_non_pending_signal(
    pair: Mapping[str, Any],
    sections_by_id: Mapping[str, dict[str, Any]],
    judge_payload: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    source_refs = _source_refs_for_pair(pair, sections_by_id)
    return {
        "conflict_id": str(judge_payload.get("conflict_id") or _conflict_id_for_pair(dict(pair))),
        "source_section_id": pair.get("source_section_id"),
        "target_section_id": pair.get("target_section_id"),
        "source_refs": source_refs,
        "base_source_hashes": _base_source_hash(source_refs),
        "outcome": str(judge_payload.get("outcome") or ""),
        "reason": str(
            judge_payload.get("why_not_pending")
            or judge_payload.get("warning")
            or "Potential conflict resolved by existing evidence."
        ),
        "spec_claim_pair": deepcopy(dict(pair)),
        "generated_at": _timestamp(generated_at),
    }


def evaluate_conflicts(
    conflict_candidate_pairs: Any = None,
    conflict_judge: Any = None,
    *,
    sections: list[dict[str, Any]] | None = None,
    spec_claims: Any = None,
    claims: Any = None,
    provider: Any = None,
    judge: Any = None,
    config: Any = None,
    limits: Any = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Judge conflict candidates and return pending review items plus diagnostics."""

    active_judge = conflict_judge or judge or provider
    _llm_cfg = getattr(config, "llm", None)
    if _llm_cfg is None and isinstance(config, dict):
        _llm_cfg = config.get("llm") or {}
    timeout_sec = int(getattr(_llm_cfg, "timeout_sec", None) or (
        _llm_cfg.get("timeout_sec") if isinstance(_llm_cfg, dict) else None
    ) or 120)
    sections_by_id = _section_map(sections)
    pairs = select_conflict_judging_pairs(
        conflict_candidate_pairs=conflict_candidate_pairs,
        spec_claims=spec_claims,
        claims=claims,
    )

    items: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    non_pending_signals: list[dict[str, Any]] = []
    call_usages: list[dict[str, Any]] = []

    def _judge_one(pair: Mapping[str, Any]) -> tuple[Mapping[str, Any], dict[str, Any]]:
        request = {
            "spec_claim_pair": deepcopy(pair),
            "claims": deepcopy(pair.get("claims") or []),
            "source_refs": _source_refs_for_pair(pair, sections_by_id),
            "section_a": deepcopy(sections_by_id.get(str(pair.get("source_section_id")), {})),
            "section_b": deepcopy(sections_by_id.get(str(pair.get("target_section_id")), {})),
        }
        return pair, _call_judge(active_judge, request, timeout_sec=timeout_sec)

    concurrency = _get_llm_batch_concurrency(config=config, limits=limits)

    pair_payloads: list[tuple[Mapping[str, Any], dict[str, Any]]]
    if concurrency > 1 and len(pairs) > 1:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            pair_payloads = list(ex.map(_judge_one, pairs))
    else:
        pair_payloads = [_judge_one(pair) for pair in pairs]

    for pair, payload in pair_payloads:
        # Collect per-call token usage injected by SubprocessLlmProvider.
        call_usage = dict(payload.pop("__spec_anchor_usage", None) or {})
        if call_usage:
            call_usages.append(call_usage)
        outcome = str(payload.get("outcome", "")).lower()
        if outcome in {"needs_human_review", "unresolved", "pending"}:
            items.append(_build_conflict_item(pair, sections_by_id, payload, generated_at=generated_at))
        else:
            non_pending_signals.append(
                _build_non_pending_signal(
                    pair,
                    sections_by_id,
                    payload,
                    generated_at=generated_at,
                )
            )
            diagnostics.append(
                {
                    "kind": "potential_conflict",
                    "level": "warning",
                    "source_section_id": pair.get("source_section_id"),
                    "target_section_id": pair.get("target_section_id"),
                    "warning": payload.get("warning") or payload.get("why_not_pending") or "Potential conflict resolved by existing evidence.",
                    "outcome": payload.get("outcome"),
                }
            )

    summary = summarize_conflict_review_state(items=items, existing_blocking_reasons=[])
    return ConflictReviewResult(
        conflict_review_items=items,
        diagnostics=diagnostics,
        freshness_report=summary["freshness_report"],
        pending_conflict_count=summary["pending_conflict_count"],
        selection_diagnostics=[],
        non_pending_conflict_signals=non_pending_signals,
        usage_list=call_usages,
    )


def validate_conflict_review_item(
    item: dict[str, Any] | None = None,
    *,
    items: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Return a normalized Conflict Review Item, or a list when items is given."""

    if item is None and items is not None:
        return [validate_conflict_review_item(item=entry, generated_at=generated_at) for entry in items]
    if item is None:
        raise ValueError("item is required")

    normalized = deepcopy(item)
    now = _timestamp(generated_at)
    normalized.setdefault("conflict_id", f"conflict-{abs(hash(str(normalized))) :x}")
    normalized.setdefault("status", "pending")
    normalized.setdefault("severity", "medium")
    normalized.setdefault("source_refs", [])
    normalized.setdefault("claims", [])
    normalized.setdefault("why_conflicting", "")
    normalized.setdefault("why_llm_cannot_decide", "")
    normalized.setdefault("related_sections", [])
    normalized["decision_options"] = _normalize_decision_options(normalized.get("decision_options"))
    normalized.setdefault("recommended_next_action", "Ask a human to decide this conflict.")
    normalized.setdefault("base_source_hashes", _base_source_hash(normalized.get("source_refs", [])))
    normalized.setdefault("valid_scope", "global")
    normalized.setdefault("reflection_status", "unreflected")
    normalized.setdefault("reflected_refs", [])
    normalized.setdefault("stale_resolution", False)
    normalized.setdefault("created_at", now)
    normalized.setdefault("updated_at", now)

    if normalized["status"] not in STATUSES:
        raise ValueError(f"invalid conflict review status: {normalized['status']}")
    if normalized["valid_scope"] not in SCOPES:
        raise ValueError(f"invalid conflict review scope: {normalized['valid_scope']}")
    if normalized["reflection_status"] not in REFLECTION_STATUSES:
        raise ValueError(f"invalid reflection status: {normalized['reflection_status']}")
    if _decision_option_ids(normalized) != DECISIONS:
        raise ValueError("decision_options must contain the full conflict decision enum")
    return normalized


def apply_conflict_decision(
    items: list[dict[str, Any]] | None = None,
    decision_payload: dict[str, Any] | None = None,
    *,
    conflict_review_items: list[dict[str, Any]] | None = None,
    payload: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Apply one human decision payload to a pending conflict item."""

    current_items = _copy_items(items if items is not None else conflict_review_items)
    decision_payload = decision_payload or payload or decision
    if not decision_payload:
        raise ValueError("decision payload is required")

    conflict_id = str(decision_payload.get("conflict_id") or "")
    selected_decision = str(decision_payload.get("decision") or "")
    selected_option = str(decision_payload.get("selected_option") or selected_decision)
    if selected_decision not in DECISIONS:
        raise ValueError(f"invalid conflict decision: {selected_decision}")
    # CLAUDE.md ルール 5 / EXTERNAL_DESIGN §2.8: pending Conflict Review Items
    # are decided by humans, not by LLM/agent. Resolve / dismiss transitions
    # therefore require the caller to attest a human authorization. Tests and
    # CLI tools that proxy a human decision must include the field.
    final_decisions = set(DECISIONS) - set(PENDING_DECISIONS)
    if selected_decision in final_decisions:
        ack = decision_payload.get("human_acknowledgement")
        if not bool(ack):
            raise ValueError(
                "human_acknowledgement=true is required for resolve/dismiss "
                "decisions; agent-only callers must surface this to a human "
                "operator before invoking apply_conflict_decision"
            )

    for index, item in enumerate(current_items):
        if item.get("conflict_id") != conflict_id:
            continue
        if item.get("status") in {"resolved", "dismissed"}:
            raise ValueError("resolved or dismissed conflict decisions cannot be overwritten")
        if selected_option not in _decision_option_ids(item):
            raise ValueError(f"selected option is not available: {selected_option}")

        updated = validate_conflict_review_item(item=item, generated_at=generated_at)
        now = _timestamp(generated_at)
        if selected_decision in PENDING_DECISIONS:
            updated["status"] = "pending"
            updated["updated_at"] = now
            updated["last_decision"] = {
                "decision": selected_decision,
                "reason": str(decision_payload.get("reason") or ""),
                "selected_option": selected_option,
            }
        elif selected_decision == "dismiss":
            updated["status"] = "dismissed"
            updated["valid_scope"] = str(decision_payload.get("valid_scope") or updated.get("valid_scope") or "global")
            updated["resolution"] = _resolution_from_payload(decision_payload, selected_option=selected_option)
            updated["reflection_status"] = "not_required"
            updated["updated_at"] = now
        else:
            updated["status"] = "resolved"
            updated["valid_scope"] = "task_scope" if selected_decision == "task_scope_resolution" else str(
                decision_payload.get("valid_scope") or updated.get("valid_scope") or "global"
            )
            if updated["valid_scope"] not in SCOPES:
                raise ValueError(f"invalid conflict review scope: {updated['valid_scope']}")
            updated["resolution"] = _resolution_from_payload(decision_payload, selected_option=selected_option)
            updated["reflection_status"] = "unreflected"
            updated["updated_at"] = now
        updated.setdefault("reflected_refs", [])
        current_items[index] = updated
        return current_items

    raise ValueError(f"conflict item not found: {conflict_id}")


def _resolution_from_payload(decision_payload: dict[str, Any], *, selected_option: str) -> dict[str, Any]:
    referenced_source_refs = decision_payload.get("referenced_source_refs") or []
    if not referenced_source_refs:
        raise ValueError("referenced_source_refs is required for resolved or dismissed conflicts")
    return {
        "decision": str(decision_payload.get("decision")),
        "reason": str(decision_payload.get("reason") or ""),
        "selected_option": selected_option,
        "valid_scope": str(decision_payload.get("valid_scope") or "global"),
        "referenced_source_refs": list(referenced_source_refs),
        "decision_origin": str(decision_payload.get("decision_origin") or "human"),
    }


def summarize_conflict_review_state(
    items: list[dict[str, Any]] | None = None,
    *,
    conflict_review_items: list[dict[str, Any]] | None = None,
    existing_blocking_reasons: list[str] | None = None,
) -> dict[str, Any]:
    """Build a freshness summary where pending conflicts are the only blocker here."""

    current_items = items if items is not None else conflict_review_items or []
    pending_count = sum(1 for item in current_items if item.get("status") == "pending")
    stale_count = sum(1 for item in current_items if item.get("stale_resolution") is True)
    unreflected_count = sum(
        1
        for item in current_items
        if item.get("status") == "resolved" and item.get("reflection_status", "unreflected") == "unreflected"
    )
    blocking_reasons = list(existing_blocking_reasons or [])
    if pending_count and "pending_conflict" not in blocking_reasons:
        blocking_reasons.append("pending_conflict")

    return {
        "pending_conflict_count": pending_count,
        "unreflected_conflict_resolution_count": unreflected_count,
        "unreflected_conflict_resolutions": unreflected_count,
        "stale_resolution_count": stale_count,
        "freshness_report": {
            "status": "blocked" if blocking_reasons else "fresh",
            "blocking_reasons": blocking_reasons,
            "pending_conflict_count": pending_count,
            "unreflected_conflict_resolution_count": unreflected_count,
            "stale_resolution_count": stale_count,
        },
    }


def refresh_conflict_resolution_staleness(
    items: list[dict[str, Any]] | None = None,
    *,
    conflict_review_items: list[dict[str, Any]] | None = None,
    current_source_hashes: dict[str, str] | None = None,
    source_hashes: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Refresh stale_resolution by comparing base_source_hashes to current hashes."""

    current_items = _copy_items(items if items is not None else conflict_review_items)
    hashes = current_source_hashes or source_hashes or {}
    for item in current_items:
        if item.get("status") not in {"resolved", "dismissed"}:
            item["stale_resolution"] = False
            continue
        stale = False
        for base in item.get("base_source_hashes", []):
            source_ref = base.get("source_ref") or base.get("source_section_id") or base.get("ref")
            expected_hash = base.get("hash") or base.get("source_hash")
            if source_ref in hashes and expected_hash is not None and str(hashes[source_ref]) != str(expected_hash):
                stale = True
                break
        item["stale_resolution"] = stale
    return current_items


def usable_conflict_resolution_evidence(
    items: list[dict[str, Any]] | None = None,
    *,
    conflict_review_items: list[dict[str, Any]] | None = None,
    requested_scope: str | None = None,
    scope: str | None = None,
    include_task_scope: bool = False,
) -> list[dict[str, Any]]:
    """Return resolved, non-stale conflict decisions usable for the requested scope."""

    requested_scope = requested_scope or scope or "global"
    current_items = items if items is not None else conflict_review_items or []
    evidence: list[dict[str, Any]] = []
    for item in current_items:
        if item.get("status") != "resolved":
            continue
        if item.get("stale_resolution") is True:
            continue
        valid_scope = item.get("valid_scope", "global")
        if valid_scope == "task_scope" and not include_task_scope:
            continue
        if requested_scope == "global" and valid_scope != "global":
            continue
        evidence.append(deepcopy(item))
    return evidence


evaluate_conflict_review_items = evaluate_conflicts
run_conflict_review = evaluate_conflicts
generate_conflict_review_items = evaluate_conflicts
normalize_conflict_review_item = validate_conflict_review_item
validate_conflict_review_items = validate_conflict_review_item
record_conflict_decision = apply_conflict_decision
resolve_conflict_review_item = apply_conflict_decision
build_conflict_freshness_report = summarize_conflict_review_state
conflict_review_freshness_report = summarize_conflict_review_state
mark_stale_conflict_resolutions = refresh_conflict_resolution_staleness
validate_conflict_resolution_freshness = refresh_conflict_resolution_staleness
filter_usable_conflict_evidence = usable_conflict_resolution_evidence
resolved_conflict_evidence = usable_conflict_resolution_evidence
build_conflict_judging_pairs = select_conflict_judging_pairs
candidate_conflict_pairs = select_conflict_judging_pairs
