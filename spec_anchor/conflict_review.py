"""Lightweight Conflict Review Item helpers.

This module keeps the G-09 conflict review contract intentionally plain:
dict-shaped items in, dict-shaped items out, with small helpers for judging,
human dismissals, freshness counts, and diagnostics.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


STATUSES = {"pending", "dismissed"}
SCOPES = {"global", "source_pair", "section_pair", "task_scope"}
CONFLICT_REVIEW_ITEM_FIELDS = {
    "base_source_hashes",
    "conflict_id",
    "conflict_points",
    "created_at",
    "recommended_next_action",
    "related_sections",
    "resolution",
    "section_pair",
    "severity",
    "source_refs",
    "stale_dismissal",
    "status",
    "updated_at",
    "valid_scope",
    "why_conflicting",
    "why_llm_cannot_decide",
}

# candidate_origin values produced by the section_pair candidate generator
# (built in a later task) and accepted by the section_pair conflict path.
SECTION_PAIR_CANDIDATE_ORIGINS = {
    "all_pairs",
    "section_pair_retrieval",
    "existing_conflict_recheck",
}

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


def _section_id(section: dict[str, Any]) -> str:
    return str(section.get("source_section_id") or section.get("section_id") or section.get("id") or "")


def _section_map(sections: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {_section_id(section): section for section in (sections or []) if _section_id(section)}


def _hash_for_section(section: dict[str, Any]) -> str | None:
    value = section.get("source_hash") or section.get("hash") or section.get("semantic_hash")
    return str(value) if value is not None else None


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


def _config_get(config: Any, path: tuple[str, ...], default: Any = None) -> Any:
    current: Any = config
    for key in path:
        if current is None:
            return default
        if isinstance(current, Mapping):
            if key not in current:
                return default
            current = current[key]
        else:
            if not hasattr(current, key):
                return default
            current = getattr(current, key)
    if current is None:
        return default
    return current


def _llm_batch_concurrency_from_config(config: Any) -> int:
    value = _config_get(config, ("limits", "llm_batch_concurrency"), 4)
    try:
        return max(1, int(value or 4))
    except (TypeError, ValueError):
        return 4


def section_pair_id(left_section_id: str, right_section_id: str) -> str:
    """Return a canonical, order-independent id for a pair of sections.

    The canonical pair is the two section ids sorted lexicographically when
    they differ, or ``[left, left]`` for a self-pair. The hash input is
    ``json.dumps(["v1", canonical_pair], sort_keys=True)`` (identity_version
    "v1" followed by the canonical pair list).
    """

    left = str(left_section_id)
    right = str(right_section_id)
    if left == right:
        canonical_pair = [left, left]
    else:
        canonical_pair = sorted([left, right])
    payload = json.dumps(["v1", canonical_pair], sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return "section_pair:sha256:v1:" + digest


def _section_pair_source_refs(
    section_a: dict[str, Any],
    section_b: dict[str, Any],
    left_section_id: str,
    right_section_id: str,
) -> list[dict[str, Any]]:
    """Build one source_ref per section (a and b; one entry when a == b).

    Reuses the existing ``_source_ref`` helper. Adds ``heading_path`` when the
    section dict carries it (``_source_ref`` does not include it by default).
    """

    sections = (
        [(section_a, left_section_id)]
        if left_section_id == right_section_id
        else [(section_a, left_section_id), (section_b, right_section_id)]
    )
    refs: list[dict[str, Any]] = []
    for section, fallback_id in sections:
        ref = _source_ref(section, fallback_id)
        ref.setdefault("source_ref", ref.get("source_section_id", fallback_id))
        heading_path = section.get("heading_path")
        if heading_path:
            ref["heading_path"] = deepcopy(heading_path)
        refs.append(ref)
    return refs


def _build_section_pair_conflict_item(
    section_a: dict[str, Any],
    section_b: dict[str, Any],
    judge_payload: dict[str, Any],
    *,
    candidate_origin: str = "all_pairs",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a section_pair Conflict Review Item (claim-free schema)."""

    a_id = _section_id(section_a)
    b_id = _section_id(section_b)
    pair_id = section_pair_id(a_id, b_id)
    # Use the SORTED canonical order so left/right match the id derivation.
    if a_id == b_id:
        left_section_id, right_section_id = a_id, a_id
        left_section, right_section = section_a, section_a
    else:
        if a_id <= b_id:
            left_section_id, right_section_id = a_id, b_id
            left_section, right_section = section_a, section_b
        else:
            left_section_id, right_section_id = b_id, a_id
            left_section, right_section = section_b, section_a

    source_refs = _section_pair_source_refs(
        left_section, right_section, left_section_id, right_section_id
    )
    origin = str(judge_payload.get("candidate_origin") or candidate_origin or "all_pairs")
    conflict_points = deepcopy(judge_payload.get("conflict_points") or [])
    now = _timestamp(generated_at)

    item = {
        "conflict_id": pair_id,
        "status": "pending",
        "severity": str(judge_payload.get("severity") or "medium"),
        "source_refs": source_refs,
        "section_pair": {
            "section_pair_id": pair_id,
            "left_section_id": left_section_id,
            "right_section_id": right_section_id,
            "candidate_origin": origin,
        },
        "conflict_points": conflict_points,
        "why_conflicting": str(
            judge_payload.get("why_conflicting")
            or "Potential source specifications conflict."
        ),
        "why_llm_cannot_decide": str(
            judge_payload.get("why_llm_cannot_decide")
            or judge_payload.get("why_unresolved")
            or "Existing evidence does not establish a safe priority."
        ),
        "recommended_next_action": str(
            judge_payload.get("recommended_next_action")
            or "Ask a human to decide this conflict."
        ),
        "base_source_hashes": _base_source_hash(source_refs),
        "valid_scope": "section_pair",
        "stale_dismissal": False,
        "created_at": now,
        "updated_at": now,
    }
    return validate_conflict_review_item(item=item, generated_at=generated_at)


def _build_section_pair_non_pending_signal(
    left_section_id: str,
    right_section_id: str,
    source_refs: list[dict[str, Any]],
    judge_payload: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "conflict_id": section_pair_id(left_section_id, right_section_id),
        "left_section_id": left_section_id,
        "right_section_id": right_section_id,
        "source_refs": source_refs,
        "base_source_hashes": _base_source_hash(source_refs),
        "outcome": str(judge_payload.get("outcome") or ""),
        "reason": str(
            judge_payload.get("why_not_pending")
            or judge_payload.get("warning")
            or "Potential conflict resolved by existing evidence."
        ),
        "generated_at": _timestamp(generated_at),
    }


def evaluate_section_pair_conflicts(
    section_pairs: Any = None,
    conflict_judge: Any = None,
    *,
    sections: list[dict[str, Any]] | None = None,
    config: Any = None,
    limits: Any = None,
    generated_at: str | None = None,
) -> ConflictReviewResult:
    """Judge whole section pairs directly and return pending review items.

    Each entry of ``section_pairs`` is a dict shaped like
    ``{"left_section_id", "right_section_id", "candidate_origin"}``. The judge
    request carries ``section_a`` / ``section_b`` / ``source_refs`` only; the
    injected judge wrapper adds Purpose / Core Concept grounding itself, so this
    function must not strip grounding. Judge calls can run concurrently, but
    result processing remains in section_pairs order.
    """

    active_judge = conflict_judge
    _llm_cfg = getattr(config, "llm", None)
    if _llm_cfg is None and isinstance(config, dict):
        _llm_cfg = config.get("llm") or {}
    timeout_sec = int(getattr(_llm_cfg, "timeout_sec", None) or (
        _llm_cfg.get("timeout_sec") if isinstance(_llm_cfg, dict) else None
    ) or 120)
    sections_by_id = _section_map(sections)
    concurrency = _llm_batch_concurrency_from_config(config)

    items: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    non_pending_signals: list[dict[str, Any]] = []
    call_usages: list[dict[str, Any]] = []

    valid_pairs: list[Mapping[str, Any]] = []
    for pair in section_pairs or []:
        if not isinstance(pair, Mapping):
            continue
        a_id = str(pair.get("left_section_id") or "")
        b_id = str(pair.get("right_section_id") or "")
        if not a_id or not b_id:
            continue
        valid_pairs.append(pair)

    def _judge_pair(pair: Mapping[str, Any]) -> tuple[
        str,
        str,
        str,
        dict[str, Any],
        dict[str, Any],
        list[dict[str, Any]],
        dict[str, Any],
    ]:
        a_id = str(pair.get("left_section_id") or "")
        b_id = str(pair.get("right_section_id") or "")
        candidate_origin = str(pair.get("candidate_origin") or "all_pairs")
        section_a = deepcopy(sections_by_id.get(a_id, {"source_section_id": a_id}))
        section_b = deepcopy(sections_by_id.get(b_id, {"source_section_id": b_id}))
        source_refs = _section_pair_source_refs(section_a, section_b, a_id, b_id)
        request = {
            "section_a": section_a,
            "section_b": section_b,
            "source_refs": source_refs,
        }
        payload = _call_judge(active_judge, request, timeout_sec=timeout_sec)
        return a_id, b_id, candidate_origin, section_a, section_b, source_refs, payload

    if concurrency > 1 and len(valid_pairs) > 1:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            judge_outputs = list(ex.map(_judge_pair, valid_pairs))
    else:
        judge_outputs = [_judge_pair(pair) for pair in valid_pairs]

    for (
        a_id,
        b_id,
        candidate_origin,
        section_a,
        section_b,
        source_refs,
        payload,
    ) in judge_outputs:
        call_usage = dict(payload.pop("__spec_anchor_usage", None) or {})
        if call_usage:
            call_usages.append(call_usage)

        outcome = str(payload.get("outcome", "")).lower()
        if outcome in {"needs_human_review", "unresolved", "pending"}:
            items.append(
                _build_section_pair_conflict_item(
                    section_a,
                    section_b,
                    payload,
                    candidate_origin=candidate_origin,
                    generated_at=generated_at,
                )
            )
        else:
            non_pending_signals.append(
                _build_section_pair_non_pending_signal(
                    a_id,
                    b_id,
                    source_refs,
                    payload,
                    generated_at=generated_at,
                )
            )
            diagnostics.append(
                {
                    "kind": "potential_conflict",
                    "level": "warning",
                    "left_section_id": a_id,
                    "right_section_id": b_id,
                    "warning": payload.get("warning")
                    or payload.get("why_not_pending")
                    or "Potential conflict resolved by existing evidence.",
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
    normalized.setdefault("conflict_points", [])
    normalized.setdefault("why_conflicting", "")
    normalized.setdefault("why_llm_cannot_decide", "")
    normalized.setdefault("related_sections", [])
    normalized.setdefault("recommended_next_action", "Ask a human to decide this conflict.")
    normalized.setdefault("base_source_hashes", _base_source_hash(normalized.get("source_refs", [])))
    normalized.setdefault("valid_scope", "global")
    normalized.setdefault("stale_dismissal", False)
    normalized.setdefault("created_at", now)
    normalized.setdefault("updated_at", now)

    unknown_fields = sorted(set(normalized) - CONFLICT_REVIEW_ITEM_FIELDS)
    if unknown_fields:
        raise ValueError(f"unknown conflict review item field: {unknown_fields[0]}")
    if normalized["status"] not in STATUSES:
        raise ValueError(f"invalid conflict review status: {normalized['status']}")
    if normalized["valid_scope"] not in SCOPES:
        raise ValueError(f"invalid conflict review scope: {normalized['valid_scope']}")
    return normalized


def apply_conflict_dismissal(
    items: list[dict[str, Any]] | None = None,
    dismissal_payload: dict[str, Any] | None = None,
    *,
    conflict_review_items: list[dict[str, Any]] | None = None,
    payload: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Apply one human dismissal request to a pending conflict item.

    Only ``dismiss`` is supported: a human marks a surfaced conflict as not a
    real conflict. The payload must attest ``human_acknowledgement=true`` and
    supply ``referenced_source_refs``.
    """

    current_items = _copy_items(items if items is not None else conflict_review_items)
    dismissal_payload = dismissal_payload or payload
    if not dismissal_payload:
        raise ValueError("dismissal payload is required")

    conflict_id = str(dismissal_payload.get("conflict_id") or "")
    selected_action = str(dismissal_payload.get("decision") or dismissal_payload.get("action") or "")
    if selected_action != "dismiss":
        raise ValueError(f"invalid conflict dismissal: {selected_action}")
    # A pending Conflict Review Item is dismissed by a human who has judged it
    # is not a real conflict, never by the LLM/agent autonomously. The caller
    # must attest a human authorization; CLI tools that proxy a human decision
    # (`spec-anchor core --dismiss-conflict`) include the field.
    if not bool(dismissal_payload.get("human_acknowledgement")):
        raise ValueError(
            "human_acknowledgement=true is required to dismiss a conflict; "
            "agent-only callers must surface this to a human operator before "
            "invoking apply_conflict_dismissal"
        )

    for index, item in enumerate(current_items):
        if item.get("conflict_id") != conflict_id:
            continue
        if item.get("status") == "dismissed":
            raise ValueError("dismissed conflict decisions cannot be overwritten")

        updated = validate_conflict_review_item(item=item, generated_at=generated_at)
        now = _timestamp(generated_at)
        updated["status"] = "dismissed"
        updated["valid_scope"] = str(
            dismissal_payload.get("valid_scope") or updated.get("valid_scope") or "global"
        )
        if updated["valid_scope"] not in SCOPES:
            raise ValueError(f"invalid conflict review scope: {updated['valid_scope']}")
        updated["resolution"] = _resolution_from_payload(dismissal_payload)
        updated["updated_at"] = now
        current_items[index] = updated
        return current_items

    raise ValueError(f"conflict item not found: {conflict_id}")


def _resolution_from_payload(dismissal_payload: dict[str, Any]) -> dict[str, Any]:
    referenced_source_refs = dismissal_payload.get("referenced_source_refs") or []
    if not referenced_source_refs:
        raise ValueError("referenced_source_refs is required for dismissed conflicts")
    return {
        "decision": str(dismissal_payload.get("decision") or dismissal_payload.get("action")),
        "reason": str(dismissal_payload.get("reason") or ""),
        "valid_scope": str(dismissal_payload.get("valid_scope") or "global"),
        "referenced_source_refs": list(referenced_source_refs),
        "decision_origin": str(dismissal_payload.get("decision_origin") or "human"),
    }


def summarize_conflict_review_state(
    items: list[dict[str, Any]] | None = None,
    *,
    conflict_review_items: list[dict[str, Any]] | None = None,
    existing_blocking_reasons: list[str] | None = None,
) -> dict[str, Any]:
    """Summarize pending conflicts and stale dismissals for `/spec-core`."""

    current_items = items if items is not None else conflict_review_items or []
    pending_count = sum(1 for item in current_items if item.get("status") == "pending")
    stale_count = sum(1 for item in current_items if item.get("stale_dismissal") is True)
    blocking_reasons = list(existing_blocking_reasons or [])

    return {
        "pending_conflict_count": pending_count,
        "stale_dismissal_count": stale_count,
        "freshness_report": {
            "status": "blocked" if blocking_reasons else "fresh",
            "blocking_reasons": blocking_reasons,
            "pending_conflict_count": pending_count,
            "stale_dismissal_count": stale_count,
        },
    }


def refresh_conflict_dismissal_staleness(
    items: list[dict[str, Any]] | None = None,
    *,
    conflict_review_items: list[dict[str, Any]] | None = None,
    current_source_hashes: dict[str, str] | None = None,
    source_hashes: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Refresh stale_dismissal by comparing base_source_hashes to current hashes."""

    current_items = _copy_items(items if items is not None else conflict_review_items)
    hashes = current_source_hashes or source_hashes or {}
    for item in current_items:
        if item.get("status") != "dismissed":
            item["stale_dismissal"] = False
            continue
        stale = False
        for base in item.get("base_source_hashes", []):
            source_ref = base.get("source_ref") or base.get("source_section_id") or base.get("ref")
            expected_hash = base.get("hash") or base.get("source_hash")
            if source_ref in hashes and expected_hash is not None and str(hashes[source_ref]) != str(expected_hash):
                stale = True
                break
        item["stale_dismissal"] = stale
    return current_items
