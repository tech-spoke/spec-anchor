"""Lightweight Conflict Review Item helpers.

This module keeps the G-09 conflict review contract intentionally plain:
dict-shaped items in, dict-shaped items out, with small helpers for judging,
human decisions, freshness, and evidence filtering.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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

_CONFLICT_WORDS = {
    "must",
    "must not",
    "required",
    "forbidden",
    "prohibited",
    "optional",
    "cannot",
    "should not",
    "禁止",
    "必須",
    "任意",
    "例外",
}


@dataclass
class ConflictReviewResult:
    conflict_review_items: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    freshness_report: dict[str, Any]
    pending_conflict_count: int = 0
    selection_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    # Token usage collected from each _call_judge invocation.
    # Each entry is the __spec_anchor_usage dict returned by the LLM provider.
    usage_list: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_review_items": self.conflict_review_items,
            "diagnostics": self.diagnostics,
            "potential_conflicts": self.diagnostics,
            "selection_diagnostics": self.selection_diagnostics,
            "freshness_report": self.freshness_report,
            "pending_conflict_count": self.pending_conflict_count,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str | None = None) -> str:
    return value or _now_iso()


def _copy_items(items: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in (items or [])]


def _coerce_candidate_items(candidates: Any) -> list[dict[str, Any]]:
    if candidates is None:
        return []
    if hasattr(candidates, "to_dict"):
        return _coerce_candidate_items(candidates.to_dict())
    if hasattr(candidates, "related_section_candidates"):
        value = getattr(candidates, "related_section_candidates")
        if value is not candidates:
            return _coerce_candidate_items(value)
    if hasattr(candidates, "candidates"):
        value = getattr(candidates, "candidates")
        if value is not candidates:
            return _coerce_candidate_items(value)
    if isinstance(candidates, Mapping):
        if "source_section_id" in candidates and "target_section_id" in candidates:
            return [deepcopy(dict(candidates))]
        items: list[dict[str, Any]] = []
        for key in ("related_section_candidates", "candidates"):
            items.extend(_coerce_candidate_items(candidates.get(key)))
        return items
    if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
        items = []
        for item in candidates:
            items.extend(_coerce_candidate_items(item))
        return items
    return []


def _metadata_value(metadata: Any, key: str) -> Any:
    if metadata is None:
        return None
    if hasattr(metadata, "to_dict"):
        return _metadata_value(metadata.to_dict(), key)
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return getattr(metadata, key, None)


def _candidate_items_from_metadata(metadata: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in ("related_section_candidates", "candidates"):
        items.extend(_coerce_candidate_items(_metadata_value(metadata, key)))
    return items


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


def _get_limit(config: Any = None, limits: Any = None, default: int = 8) -> int:
    if limits is not None:
        limit_source = limits
    elif isinstance(config, Mapping):
        limit_source = config.get("limits")
    else:
        limit_source = getattr(config, "limits", None)

    if isinstance(limit_source, Mapping):
        value = limit_source.get("conflict_pair_max_per_section", default)
    elif limit_source is not None:
        value = getattr(limit_source, "conflict_pair_max_per_section", default)
    elif isinstance(config, Mapping):
        value = config.get("conflict_pair_max_per_section", default)
    else:
        value = getattr(config, "conflict_pair_max_per_section", default)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _looks_high_risk(candidate: dict[str, Any]) -> bool:
    channels = {str(channel) for channel in candidate.get("channels", [])}
    terms = " ".join(str(term).lower() for term in candidate.get("evidence_terms", []))
    text = " ".join(
        str(candidate.get(key, "")).lower()
        for key in ("reason", "relation_hint", "summary", "text")
    )
    score = candidate.get("candidate_score", candidate.get("score", 0))
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        numeric_score = 0.0

    has_conflict_terms = any(word in terms or word in text for word in _CONFLICT_WORDS)
    return (
        candidate.get("relation_hint") == "conflicts_with"
        or ("shared_identifier" in channels and has_conflict_terms)
        or (numeric_score >= 50 and has_conflict_terms)
    )


class _ConflictPairSelection(list[dict[str, Any]]):
    selection_diagnostics: list[dict[str, Any]]


def select_conflict_judging_pairs(
    sections: list[dict[str, Any]] | None = None,
    related_sections: dict[str, list[dict[str, Any]]] | list[dict[str, Any]] | None = None,
    candidates: Any = None,
    *,
    related_section_candidates: Any = None,
    config: Any = None,
    limits: Any = None,
) -> list[dict[str, Any]]:
    """Select explicit conflicts plus bounded high-risk candidate pairs."""

    del sections  # Selection is id-based; section details are used by the judge stage.
    max_per_section = _get_limit(config=config, limits=limits)
    selected: _ConflictPairSelection = _ConflictPairSelection()
    skipped_pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}

    def add_pair(pair: dict[str, Any], *, explicit: bool) -> None:
        source_id = str(pair.get("source_section_id") or pair.get("section_a_id") or pair.get("a") or "")
        target_id = str(pair.get("target_section_id") or pair.get("section_b_id") or pair.get("b") or "")
        if not source_id or not target_id or source_id == target_id:
            return
        key = _pair_key(source_id, target_id)
        if key in seen:
            return
        if not explicit and max_per_section <= 0:
            skipped_pairs.append(
                {
                    "source_section_id": source_id,
                    "target_section_id": target_id,
                    "reason_code": "conflict_pair_max_per_section",
                    "reason": "conflict_pair_max_per_section is 0; high-risk candidate was not sent to conflict review",
                }
            )
            return
        if not explicit:
            if counts.get(source_id, 0) >= max_per_section or counts.get(target_id, 0) >= max_per_section:
                skipped_pairs.append(
                    {
                        "source_section_id": source_id,
                        "target_section_id": target_id,
                        "reason_code": "conflict_pair_max_per_section",
                        "reason": "per-section conflict pair cap reached; high-risk candidate was not sent to conflict review",
                    }
                )
                return

        normalized = deepcopy(pair)
        normalized["source_section_id"] = source_id
        normalized["target_section_id"] = target_id
        normalized.setdefault("relation_hint", "conflicts_with" if explicit else "potential_conflict")
        normalized.setdefault("channels", [])
        normalized.setdefault("evidence_terms", [])
        selected.append(normalized)
        seen.add(key)
        if not explicit:
            counts[source_id] = counts.get(source_id, 0) + 1
            counts[target_id] = counts.get(target_id, 0) + 1

    if isinstance(related_sections, dict):
        related_iter = [
            relation
            for relations in related_sections.values()
            for relation in (relations or [])
            if isinstance(relation, dict)
        ]
    elif isinstance(related_sections, list):
        related_iter = [relation for relation in related_sections if isinstance(relation, dict)]
    else:
        related_iter = []

    # relation_hint values that do not indicate incompatible requirements even when
    # possible_conflict=True. These are filtered before evaluation to avoid wasting
    # LLM calls on dependency/association relations that the related_sections LLM
    # may over-flag (e.g. "do not directly interact" + possible_conflict=True).
    _NON_CONFLICT_HINTS: frozenset[str] = frozenset({"see_also", "related", "background"})
    filtered_possible_conflicts: list[dict[str, Any]] = []

    for relation in related_iter:
        # Phase E: Related Sections no longer finalizes conflicts_with. The
        # LLM typing stage now emits possible_conflict=True as a referral
        # signal, and the Conflict Review pipeline below re-judges with full
        # Purpose / Core Concept / Source Specs grounding. The legacy
        # relation_hint=conflicts_with path is kept for backward compat.
        hint = relation.get("relation_hint")
        if hint == "conflicts_with":
            add_pair(relation, explicit=True)
        elif bool(relation.get("possible_conflict", False)):
            if hint in _NON_CONFLICT_HINTS:
                # Deterministic pre-filter: non-conflict-bearing relation_hint
                # makes possible_conflict semantically void. Record for diagnostics.
                filtered_possible_conflicts.append(
                    {
                        "source_section_id": str(
                            relation.get("source_section_id") or relation.get("a") or ""
                        ),
                        "target_section_id": str(
                            relation.get("target_section_id") or relation.get("b") or ""
                        ),
                        "relation_hint": hint,
                        "reason_code": "non_conflict_bearing_relation_hint",
                        "reason": (
                            f"relation_hint={hint!r} is not conflict-bearing; "
                            "possible_conflict=True was ignored"
                        ),
                    }
                )
            else:
                add_pair(relation, explicit=True)

    candidate_items = _coerce_candidate_items(candidates) + _coerce_candidate_items(related_section_candidates)
    for candidate in candidate_items:
        if isinstance(candidate, dict) and _looks_high_risk(candidate):
            add_pair(candidate, explicit=False)

    diagnostics_entries: list[dict[str, Any]] = []
    if filtered_possible_conflicts:
        diagnostics_entries.append(
            {
                "kind": "conflict_pair_selection",
                "level": "info",
                "stage": "conflict_review",
                "reason_code": "filtered_possible_conflicts",
                "filtered_count": len(filtered_possible_conflicts),
                "filtered_pairs": filtered_possible_conflicts,
                "message": (
                    "possible_conflict pairs with non-conflict-bearing relation_hint "
                    "(see_also/related/background) were excluded before conflict evaluation."
                ),
            }
        )
    if skipped_pairs:
        diagnostics_entries.append(
            {
                "kind": "conflict_pair_selection",
                "level": "info",
                "stage": "conflict_review",
                "reason_code": "conflict_pair_max_per_section_skipped",
                "conflict_pair_max_per_section": max_per_section,
                "skipped_pair_count": len(skipped_pairs),
                "skipped_pairs_sample": skipped_pairs[:20],
                "message": "Some high-risk conflict candidate pairs were not sent to Conflict Review because conflict_pair_max_per_section was reached.",
            }
        )
    if diagnostics_entries:
        setattr(selected, "selection_diagnostics", diagnostics_entries)

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
    source_id = str(pair.get("source_section_id", "")).replace("/", "-").replace("#", "-")
    target_id = str(pair.get("target_section_id", "")).replace("/", "-").replace("#", "-")
    return f"conflict-{source_id}--{target_id}".strip("-")


def _build_conflict_item(
    pair: dict[str, Any],
    sections_by_id: dict[str, dict[str, Any]],
    judge_payload: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> ConflictReviewResult:
    source_id = str(pair.get("source_section_id"))
    target_id = str(pair.get("target_section_id"))
    source = sections_by_id.get(source_id, {"source_section_id": source_id})
    target = sections_by_id.get(target_id, {"source_section_id": target_id})
    source_refs = [_source_ref(source, source_id), _source_ref(target, target_id)]
    now = _timestamp(generated_at)

    item = {
        "conflict_id": str(judge_payload.get("conflict_id") or _conflict_id_for_pair(pair)),
        "status": "pending",
        "severity": str(judge_payload.get("severity") or "medium"),
        "source_refs": source_refs,
        "claims": deepcopy(judge_payload.get("claims") or []),
        "why_conflicting": str(judge_payload.get("why_conflicting") or pair.get("reason") or "Potential source specifications conflict."),
        "why_llm_cannot_decide": str(
            judge_payload.get("why_llm_cannot_decide")
            or judge_payload.get("why_unresolved")
            or "Existing evidence does not establish a safe priority."
        ),
        "related_sections": [deepcopy(pair)],
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


def evaluate_conflicts(
    sections: list[dict[str, Any]] | None = None,
    related_sections: dict[str, list[dict[str, Any]]] | list[dict[str, Any]] | None = None,
    conflict_judge: Any = None,
    *,
    section_metadata: dict[str, Any] | None = None,
    candidates: Any = None,
    related_section_candidates: Any = None,
    provider: Any = None,
    judge: Any = None,
    config: Any = None,
    limits: Any = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Judge conflict candidates and return pending review items plus diagnostics."""

    if related_sections is None and section_metadata:
        related_sections = _metadata_value(section_metadata, "related_sections")
    candidate_items = (
        _coerce_candidate_items(candidates)
        + _coerce_candidate_items(related_section_candidates)
        + _candidate_items_from_metadata(section_metadata)
    )
    active_judge = conflict_judge or judge or provider
    _llm_cfg = getattr(config, "llm", None)
    if _llm_cfg is None and isinstance(config, dict):
        _llm_cfg = config.get("llm") or {}
    timeout_sec = int(getattr(_llm_cfg, "timeout_sec", None) or (
        _llm_cfg.get("timeout_sec") if isinstance(_llm_cfg, dict) else None
    ) or 120)
    sections_by_id = _section_map(sections)
    pairs = select_conflict_judging_pairs(
        sections=sections,
        related_sections=related_sections,
        candidates=candidate_items,
        config=config,
        limits=limits,
    )
    selection_diagnostics = list(getattr(pairs, "selection_diagnostics", []) or [])

    items: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    call_usages: list[dict[str, Any]] = []
    for pair in pairs:
        request = {
            "pair": deepcopy(pair),
            "section_a": deepcopy(sections_by_id.get(str(pair.get("source_section_id")), {})),
            "section_b": deepcopy(sections_by_id.get(str(pair.get("target_section_id")), {})),
        }
        payload = _call_judge(active_judge, request, timeout_sec=timeout_sec)
        # Collect per-call token usage injected by SubprocessLlmProvider.
        call_usage = dict(payload.pop("__spec_anchor_usage", None) or {})
        if call_usage:
            call_usages.append(call_usage)
        outcome = str(payload.get("outcome", "")).lower()
        if outcome in {"needs_human_review", "unresolved", "pending"}:
            items.append(_build_conflict_item(pair, sections_by_id, payload, generated_at=generated_at))
        else:
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
        selection_diagnostics=selection_diagnostics,
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
