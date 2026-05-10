"""Minimal `/spec-inject` public API.

This module keeps the Agent/CLI boundary intentionally small: the Agent
supplies task interpretation and candidate constraints; `/spec-inject`
validates freshness plus evidence shape and returns injectable context.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from spec_grag.conflict_review import SCOPES as CONFLICT_REVIEW_SCOPES
from spec_grag.freshness import build_freshness_gate_decision, pending_conflict_items


FINAL_EVIDENCE_ORIGINS = {
    "Purpose",
    "Core Concept",
    "Source Specs",
    "Conflict Review Item",
}
SUPPORT_ONLY_ORIGINS = {
    "Section Summary",
    "Search Keys",
    "Related Sections",
    "Chapter Key Anchor",
}
REQUIRED_CONSTRAINT_FIELDS = (
    "statement",
    "evidence_origin",
    "evidence_ref",
    "support_refs",
    "applicability",
)
REQUIRED_STRING_CONSTRAINT_FIELDS = (
    "statement",
    "evidence_origin",
    "evidence_ref",
    "applicability",
)
CONFLICT_REVIEW_INVALID_STATUSES = {
    "pending",
    "dismissed",
    "unresolved",
    "deferred",
    "needs_human_review",
    "needs_source_update",
    "stale",
    "stale_resolution",
}
CONFLICT_REVIEW_STALE_STATUSES = {"stale", "stale_resolution"}
UNREFLECTED_CONFLICT_WARNING_CODE = "unreflected_conflict_resolution"
TASK_SCOPE_CONFLICT_WARNING_CODE = "task_scope_conflict_resolution"


class SpecInjectError(ValueError):
    """Raised when `/spec-inject` inputs are invalid."""


def run_spec_inject(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
    task_prompt: str | None = None,
    prompt: str | None = None,
    conversation_context: str | None = None,
    agent_constraints: Sequence[Mapping[str, Any]] | None = None,
    constraints: Sequence[Mapping[str, Any]] | None = None,
    generated_constraints: Sequence[Mapping[str, Any]] | None = None,
    freshness_report: Mapping[str, Any] | Any | None = None,
    freshness: Mapping[str, Any] | Any | None = None,
    provider: Any = None,
    llm_provider: Any = None,
    generated_at: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Return a validated, injectable constraint context for `/spec-inject`.

    `provider` and `llm_provider` are accepted for API compatibility only.
    They are deliberately unused because `/spec-inject` must not call an
    autonomous LLM provider or rerun `/spec-core`.
    """

    del task_prompt, prompt, conversation_context, provider, llm_provider

    project = _project_root(project_root, root=root, cwd=cwd)
    report = (
        freshness_report
        if freshness_report is not None
        else freshness
        if freshness is not None
        else _read_freshness_artifact(project)
    )
    decision = build_freshness_gate_decision(report, command="inject")

    base_result = _base_result(
        decision,
        project_root=project,
        generated_at=generated_at,
    )
    if decision.get("should_stop"):
        decision = _hydrate_pending_conflict_items(decision, project)
        return _stopped_result(base_result, decision)

    candidate_constraints = _first_constraints(
        agent_constraints,
        constraints,
        generated_constraints,
    )
    if candidate_constraints is None:
        raise SpecInjectError(
            "Agent constraints are required for /spec-inject; "
            "the CLI validates supplied constraints but does not generate fallback constraints."
        )

    validated = validate_constraints(
        candidate_constraints,
        conflict_review_items=_read_conflict_review_items(project),
    )
    summary = _injectable_summary(validated)
    constraint_warnings = _constraint_warnings(validated)
    if constraint_warnings:
        summary["制約警告"] = constraint_warnings
    result = {
        **base_result,
        "should_stop": False,
        "stops": False,
        "blocked": False,
        "can_continue": True,
        "constraints": validated,
        "injectable_context": summary,
        "labels": {
            "constraints": "今回守る制約",
            "targets": "今回見るべき対象",
            "related": "関連先として確認したもの",
        },
    }
    if decision.get("warnings"):
        result["warnings"] = list(decision.get("warnings") or [])
        result["continues_with_warnings"] = bool(decision.get("continues_with_warnings"))
    if constraint_warnings:
        result["warnings"] = list(result.get("warnings") or []) + constraint_warnings
        result["continues_with_warnings"] = True
    return result


def validate_constraints(
    constraints: Sequence[Mapping[str, Any]],
    conflict_review_items: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Validate and normalize Agent-supplied constraints."""

    if not _is_sequence(constraints):
        raise SpecInjectError("constraints must be a list of objects")

    conflict_items = _coerce_conflict_review_items(conflict_review_items)
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(constraints):
        if not isinstance(raw, Mapping):
            raise SpecInjectError(f"constraint[{index}] must be an object")
        item = deepcopy(dict(raw))
        missing = [field for field in REQUIRED_CONSTRAINT_FIELDS if field not in item]
        if missing:
            raise SpecInjectError(
                f"constraint[{index}] missing required field(s): {', '.join(missing)}"
            )

        invalid_strings = [
            field
            for field in REQUIRED_STRING_CONSTRAINT_FIELDS
            if not _non_empty_string(item.get(field))
        ]
        if invalid_strings:
            raise SpecInjectError(
                f"constraint[{index}] field(s) must be non-empty strings: "
                + ", ".join(invalid_strings)
            )

        origin = item["evidence_origin"]
        if origin in SUPPORT_ONLY_ORIGINS:
            raise SpecInjectError(
                f"{origin} cannot be used as final evidence_origin; "
                "evidence_origin must be one of: "
                + ", ".join(sorted(FINAL_EVIDENCE_ORIGINS))
            )
        if origin not in FINAL_EVIDENCE_ORIGINS:
            raise SpecInjectError(
                f"unsupported evidence_origin {origin}; evidence_origin must be one of: "
                + ", ".join(sorted(FINAL_EVIDENCE_ORIGINS))
            )

        support_refs = item.get("support_refs")
        if not isinstance(support_refs, list):
            raise SpecInjectError(f"constraint[{index}] support_refs must be a list")

        item["evidence_origin"] = origin
        item["support_refs"] = [_normalize_support_ref(ref) for ref in support_refs]
        if origin == "Conflict Review Item":
            _validate_conflict_review_constraint(
                item,
                index=index,
                conflict_review_items=conflict_items,
            )
        normalized.append(_jsonable(item))

    return normalized


def _validate_conflict_review_constraint(
    item: dict[str, Any],
    *,
    index: int,
    conflict_review_items: Sequence[Mapping[str, Any]],
) -> None:
    evidence_ref = str(item.get("evidence_ref") or "").strip()
    sources = _conflict_review_metadata_sources(
        item,
        evidence_ref=evidence_ref,
        conflict_review_items=conflict_review_items,
    )
    validation_sources = [
        (label, source)
        for label, source in sources
        if _has_conflict_review_validation_metadata(source)
    ]
    if not validation_sources:
        raise SpecInjectError(
            f"constraint[{index}] Conflict Review Item evidence requires structured "
            "metadata or an artifact match with status=resolved, stale_resolution=false "
            "or resolution_status not stale_resolution, and valid_scope"
        )

    statuses = _metadata_values(validation_sources, "status", "conflict_status")
    resolution_statuses = _metadata_values(validation_sources, "resolution_status")
    stale_values = _metadata_values(validation_sources, "stale_resolution")
    scopes = _metadata_values(validation_sources, "valid_scope")
    reflection_statuses = _metadata_values(validation_sources, "reflection_status")

    invalid_status = _first_invalid_conflict_review_status(statuses + resolution_statuses)
    if invalid_status is not None:
        raise SpecInjectError(
            f"constraint[{index}] Conflict Review Item evidence must be resolved; "
            f"got {invalid_status}"
        )

    if not any(_normalize_metadata_value(value) == "resolved" for value in statuses + resolution_statuses):
        raise SpecInjectError(
            f"constraint[{index}] Conflict Review Item evidence must include status=resolved"
        )

    stale_value = next((value for value in stale_values if _is_stale_resolution(value)), None)
    if stale_value is not None:
        raise SpecInjectError(
            f"constraint[{index}] Conflict Review Item evidence is stale_resolution"
        )

    has_non_stale_signal = any(_is_non_stale_resolution(value) for value in stale_values) or any(
        _normalize_metadata_value(value) not in CONFLICT_REVIEW_STALE_STATUSES
        for value in resolution_statuses
    )
    if not has_non_stale_signal:
        raise SpecInjectError(
            f"constraint[{index}] Conflict Review Item evidence must include "
            "stale_resolution=false or resolution_status not stale_resolution"
        )

    if not scopes or any(not _non_empty_metadata_value(scope) for scope in scopes):
        raise SpecInjectError(
            f"constraint[{index}] Conflict Review Item evidence must include "
            "non-empty valid_scope"
        )

    invalid_scope = next(
        (
            str(scope)
            for scope in scopes
            if _normalize_metadata_value(scope) not in CONFLICT_REVIEW_SCOPES
        ),
        None,
    )
    if invalid_scope is not None:
        raise SpecInjectError(
            f"constraint[{index}] Conflict Review Item evidence has invalid valid_scope: "
            f"{invalid_scope}"
        )

    if any(_normalize_metadata_value(status) == "unreflected" for status in reflection_statuses):
        _append_constraint_warning(
            item,
            {
                "code": UNREFLECTED_CONFLICT_WARNING_CODE,
                "evidence_ref": evidence_ref,
                "note": (
                    "resolved Conflict Review Item resolution is a human decision "
                    "that is not yet reflected in Purpose, Core Concept, or Source Specs"
                ),
            },
        )

    if any(_normalize_metadata_value(scope) == "task_scope" for scope in scopes):
        _append_constraint_warning(
            item,
            {
                "code": TASK_SCOPE_CONFLICT_WARNING_CODE,
                "evidence_ref": evidence_ref,
                "note": (
                    "valid_scope=task_scope means this Conflict Review Item resolution "
                    "is only a temporary decision for the current task"
                ),
            },
        )


def _conflict_review_metadata_sources(
    item: Mapping[str, Any],
    *,
    evidence_ref: str,
    conflict_review_items: Sequence[Mapping[str, Any]],
) -> list[tuple[str, Mapping[str, Any]]]:
    sources: list[tuple[str, Mapping[str, Any]]] = []
    _append_metadata_source(sources, "constraint", item)
    for key in ("conflict_review_item", "evidence", "resolution"):
        _append_metadata_source(sources, key, item.get(key))

    if evidence_ref:
        for conflict_item in conflict_review_items:
            if _conflict_review_item_matches(conflict_item, evidence_ref):
                _append_metadata_source(sources, "artifact", conflict_item)
    return sources


def _append_metadata_source(
    sources: list[tuple[str, Mapping[str, Any]]],
    label: str,
    value: Any,
) -> None:
    if not isinstance(value, Mapping):
        return
    sources.append((label, value))
    nested_resolution = value.get("resolution")
    if isinstance(nested_resolution, Mapping):
        sources.append((f"{label}.resolution", nested_resolution))
    nested_evidence = value.get("evidence")
    if isinstance(nested_evidence, Mapping):
        sources.append((f"{label}.evidence", nested_evidence))


def _has_conflict_review_validation_metadata(value: Mapping[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "status",
            "conflict_status",
            "resolution_status",
            "stale_resolution",
            "valid_scope",
            "reflection_status",
        )
    )


def _metadata_values(
    sources: Sequence[tuple[str, Mapping[str, Any]]],
    *keys: str,
) -> list[Any]:
    values: list[Any] = []
    for _, source in sources:
        for key in keys:
            if key in source:
                values.append(source.get(key))
    return values


def _first_invalid_conflict_review_status(values: Sequence[Any]) -> str | None:
    for value in values:
        normalized = _normalize_metadata_value(value)
        if normalized in CONFLICT_REVIEW_INVALID_STATUSES:
            return normalized
    return None


def _normalize_metadata_value(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _non_empty_metadata_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_stale_resolution(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalize_metadata_value(value)
    return normalized in {"true", "1", "yes", "y", "stale", "stale_resolution"}


def _is_non_stale_resolution(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    normalized = _normalize_metadata_value(value)
    return normalized in {"false", "0", "no", "n", "fresh", "current", "resolved"}


def _append_constraint_warning(item: dict[str, Any], warning: Mapping[str, Any]) -> None:
    raw_warnings = item.get("warnings")
    if raw_warnings is None:
        warnings: list[Any] = []
    elif isinstance(raw_warnings, list):
        warnings = list(raw_warnings)
    else:
        warnings = [raw_warnings]

    code = warning.get("code")
    if code is not None and any(
        isinstance(existing, Mapping) and existing.get("code") == code for existing in warnings
    ):
        item["warnings"] = warnings
        return

    warnings.append(dict(warning))
    item["warnings"] = warnings


def _constraint_warnings(constraints: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for constraint in constraints:
        evidence_ref = str(constraint.get("evidence_ref") or "")
        for warning in _as_list(constraint.get("warnings")):
            if isinstance(warning, Mapping):
                item = dict(warning)
            else:
                item = {"note": str(warning)}
            item.setdefault("evidence_ref", evidence_ref)
            key = repr(_jsonable(item))
            if key in seen:
                continue
            warnings.append(_jsonable(item))
            seen.add(key)
    return warnings


def _read_conflict_review_items(project_root: Path) -> list[dict[str, Any]]:
    return _coerce_conflict_review_items(
        _read_json_file(_context_dir(project_root) / "conflict_review_items.json")
    )


def _coerce_conflict_review_items(
    value: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("conflict_review_items", "items"):
            nested = value.get(key)
            if nested is not None:
                return _coerce_conflict_review_items(nested)
        return [deepcopy(dict(value))] if value.get("conflict_id") else []
    if not _is_sequence(value):
        return []
    return [deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]


def _conflict_review_item_matches(item: Mapping[str, Any], evidence_ref: str) -> bool:
    candidates = (
        item.get("conflict_id"),
        item.get("id"),
        item.get("evidence_ref"),
    )
    return any(str(candidate or "").strip() == evidence_ref for candidate in candidates)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def _base_result(
    decision: Mapping[str, Any],
    *,
    project_root: Path,
    generated_at: str | None,
) -> dict[str, Any]:
    return {
        "command": "/spec-inject",
        "project_root": project_root.as_posix(),
        "status": decision.get("status"),
        "freshness_report": deepcopy(decision.get("freshness_report") or {}),
        "blocking_reasons": list(decision.get("blocking_reasons") or []),
        "warnings": list(decision.get("warnings") or []),
        "recommended_next_action": decision.get("recommended_next_action"),
        "generated_at": generated_at,
    }


def _stopped_result(base_result: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        **dict(base_result),
        "should_stop": True,
        "stops": True,
        "blocked": True,
        "can_continue": False,
        "constraints": [],
        "stop_reason": decision.get("stop_reason"),
        "reasons": list(decision.get("blocking_reasons") or []),
    }
    if "pending_conflict_items" in decision:
        pending = deepcopy(list(decision.get("pending_conflict_items") or []))
        result["pending_conflict_items"] = pending
        result["pending_conflict_count"] = decision.get("pending_conflict_count", len(pending))
    return result


def _hydrate_pending_conflict_items(
    decision: Mapping[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    result = dict(decision)
    if not _pending_only_stop(result):
        return result
    if result.get("pending_conflict_items"):
        return result

    pending = pending_conflict_items(_read_json_file(_context_dir(project_root) / "conflict_review_items.json"))
    if not pending:
        return result

    result["pending_conflict_items"] = pending
    result["pending_conflict_count"] = len(pending)
    return result


def _pending_only_stop(decision: Mapping[str, Any]) -> bool:
    return (
        bool(decision.get("should_stop"))
        and decision.get("status") == "blocked"
        and list(decision.get("blocking_reasons") or []) == ["pending_conflict"]
    )


def _injectable_summary(constraints: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    targets: list[dict[str, str]] = []
    related: list[dict[str, str]] = []
    seen_related: set[tuple[str, str]] = set()

    for constraint in constraints:
        targets.append(
            {
                "origin": str(constraint.get("evidence_origin")),
                "ref": str(constraint.get("evidence_ref")),
                "applicability": str(constraint.get("applicability")),
            }
        )
        for support in constraint.get("support_refs", []):
            if not isinstance(support, Mapping):
                continue
            origin = str(support.get("origin") or "")
            ref = str(support.get("ref") or "")
            key = (origin, ref)
            if not origin and not ref:
                continue
            if key in seen_related:
                continue
            related.append({"origin": origin, "ref": ref})
            seen_related.add(key)

    return {
        "今回守る制約": [str(item.get("statement")) for item in constraints],
        "今回見るべき対象": targets,
        "関連先として確認したもの": related,
    }


def _first_constraints(*values: Any) -> Any | None:
    for value in values:
        if value is None:
            continue
        if _is_sequence(value) and not value:
            continue
        return value
    return None


def _read_freshness_artifact(project_root: Path) -> dict[str, Any]:
    path = _context_dir(project_root) / "freshness.json"
    payload = _read_json_file(path)
    if payload:
        return payload
    return {
        "status": "failed",
        "blocking_reasons": ["failed_required_artifact"],
        "warnings": [f"freshness artifact missing or unreadable: {path.as_posix()}"],
        "diagnostics": {"missing_required_artifacts": ["freshness"]},
    }


def _context_dir(project_root: Path) -> Path:
    config = _read_project_config(project_root)
    context = config.get("context") if isinstance(config.get("context"), Mapping) else {}
    storage = context.get("storage") if isinstance(context, Mapping) else None
    relative = str(storage or ".spec-grag/context")
    path = Path(relative)
    if path.is_absolute():
        return path
    return project_root / path


def _read_project_config(project_root: Path) -> dict[str, Any]:
    path = project_root / ".spec-grag" / "config.toml"
    if not path.is_file():
        return {}
    try:
        payload = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _project_root(
    project_root: str | Path = ".",
    *,
    root: str | Path | None,
    cwd: str | Path | None,
) -> Path:
    selected = project_root if project_root != "." else root or cwd or project_root
    return Path(selected).expanduser().resolve()


def _normalize_support_ref(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        item = deepcopy(dict(value))
        if "origin" in item:
            item["origin"] = str(item["origin"])
        if "ref" in item:
            item["ref"] = str(item["ref"])
        return _jsonable(item)
    return {"ref": str(value)}


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if _is_sequence(value):
        return [_jsonable(item) for item in value]
    return value


def run_inject_section(
    project_root: str | Path = ".",
    *,
    section_ids: Sequence[str],
    root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Phase R-6: id-indexed section payload lookup against Qdrant.

    Returns `{section_id: payload}` for sections that exist in the
    `spec_grag_section` Qdrant collection. Missing ids are simply absent
    from the result (consistent with `fetch_section_payloads` in
    `spec_grag/section_payload.py`).

    `doc/EXTERNAL_DESIGN.ja.md` §8.4 (inject-section): used by the Agent
    to follow Related Sections without issuing a new vector search.
    """

    from spec_grag.section_payload import (
        SectionPayloadLookupError,
        fetch_section_payloads,
    )

    project = _project_root(project_root, root=root, cwd=cwd)
    requested_ids = [str(value) for value in section_ids if value]
    qdrant_config = _qdrant_section_config(project)
    base_result = {
        "command": "/spec-inject inject-section",
        "project_root": project.as_posix(),
        "requested_section_ids": list(requested_ids),
        "collection": qdrant_config["section_collection"],
        "sections": {},
        "found_section_ids": [],
        "missing_section_ids": requested_ids,
        "warnings": [],
    }
    if not requested_ids:
        return base_result
    try:
        client = _build_qdrant_client(qdrant_config["url"])
    except SpecInjectError as exc:
        base_result["warnings"].append({"reason_code": "qdrant_unavailable", "message": str(exc)})
        return base_result
    try:
        payloads = fetch_section_payloads(
            client,
            requested_ids,
            collection=qdrant_config["section_collection"],
        )
    except SectionPayloadLookupError as exc:
        base_result["warnings"].append(
            {"reason_code": "qdrant_lookup_failed", "message": str(exc)}
        )
        return base_result
    base_result["sections"] = {
        section_id: _jsonable(dict(payload)) for section_id, payload in payloads.items()
    }
    base_result["found_section_ids"] = list(payloads.keys())
    base_result["missing_section_ids"] = [
        section_id for section_id in requested_ids if section_id not in payloads
    ]
    return base_result


def run_inject_chapters(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Phase R-6: return `chapter_anchors.json` for the project.

    `doc/EXTERNAL_DESIGN.ja.md` §8.4 (inject-chapters). Bodies as written
    by `/spec-core` (Phase R-7 will replace the mechanical builder with
    an LLM-generated artifact). The CLI returns the raw artifact so the
    Agent can pick chapters / key_topics / important_sections to follow.
    """

    project = _project_root(project_root, root=root, cwd=cwd)
    artifact = _read_json_file(_context_dir(project) / "chapter_anchors.json")
    return {
        "command": "/spec-inject inject-chapters",
        "project_root": project.as_posix(),
        "status": artifact.get("status", "missing" if not artifact else "success"),
        "chapter_anchors": artifact or {"chapters": [], "status": "missing"},
        "warnings": [] if artifact else [
            {"reason_code": "chapter_anchors_missing", "message": "chapter_anchors.json not found"}
        ],
    }


def run_inject_purpose(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Phase R-6: return Purpose + Core Concept file contents.

    `doc/EXTERNAL_DESIGN.ja.md` §8.4 (inject-purpose). Both files are
    short by design, so the full text is returned (per §8.3 path ③ the
    Agent reads the full file rather than grepping a substring).
    """

    project = _project_root(project_root, root=root, cwd=cwd)
    config = _read_project_config(project)
    core_section = config.get("core") if isinstance(config.get("core"), Mapping) else {}
    purpose_path = _resolve_optional_path(
        project,
        str(core_section.get("purpose_file") or "") if isinstance(core_section, Mapping) else "",
    )
    concept_path = _resolve_optional_path(
        project,
        str(core_section.get("concept_file") or "") if isinstance(core_section, Mapping) else "",
    )
    purpose_text, purpose_warning = _read_text_or_warning(purpose_path, "purpose_file")
    concept_text, concept_warning = _read_text_or_warning(concept_path, "concept_file")
    warnings: list[dict[str, Any]] = []
    if purpose_warning is not None:
        warnings.append(purpose_warning)
    if concept_warning is not None:
        warnings.append(concept_warning)
    return {
        "command": "/spec-inject inject-purpose",
        "project_root": project.as_posix(),
        "purpose_file": purpose_path.as_posix() if purpose_path is not None else None,
        "concept_file": concept_path.as_posix() if concept_path is not None else None,
        "purpose_text": purpose_text,
        "concept_text": concept_text,
        "warnings": warnings,
    }


def run_inject_conflicts(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Phase R-6: return resolved + non-stale Conflict Review Items.

    `doc/EXTERNAL_DESIGN.ja.md` §8.4 (inject-conflicts). The Agent uses
    these as `evidence_origin = Conflict Review Item` candidates for
    constraints. Pending / dismissed / stale items are filtered out so
    callers see only safe-to-cite resolutions.
    """

    project = _project_root(project_root, root=root, cwd=cwd)
    raw_items = _read_conflict_review_items(project)
    resolved_items: list[dict[str, Any]] = []
    excluded_items: list[dict[str, Any]] = []
    for item in raw_items:
        status = str(item.get("status") or "").strip().lower()
        if status == "resolved" and status not in CONFLICT_REVIEW_STALE_STATUSES:
            # Apply the same stale check `/spec-inject` uses for its
            # primary constraint validation path.
            stale_marker = item.get("stale_resolution") or item.get("stale")
            if stale_marker:
                excluded_items.append(
                    {
                        "conflict_id": item.get("conflict_id"),
                        "reason_code": "stale_resolution",
                    }
                )
                continue
            resolved_items.append(deepcopy(item))
        else:
            excluded_items.append(
                {
                    "conflict_id": item.get("conflict_id"),
                    "reason_code": f"status_{status or 'missing'}",
                }
            )
    return {
        "command": "/spec-inject inject-conflicts",
        "project_root": project.as_posix(),
        "resolved_conflict_review_items": resolved_items,
        "excluded_conflict_review_items": excluded_items,
        "count": len(resolved_items),
    }


def run_inject_search(
    project_root: str | Path = ".",
    *,
    query: str,
    top_k: int = 8,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Phase R-6: section-level hybrid retrieval against the Qdrant section collection.

    `doc/EXTERNAL_DESIGN.ja.md` §8.4 (inject-search). Returns the top-K
    section payloads (heading / summary / search_keys / identifiers /
    related_sections / source_section_id / score) ranked by RRF over
    BGE-M3 dense + sparse vectors. When Qdrant or FlagEmbedding is
    unavailable, the call returns a structured warning instead of
    raising so the Agent can fall back to other paths (§8.3 path ②/③/④).
    """

    project = _project_root(project_root, root=root, cwd=cwd)
    qdrant_config = _qdrant_section_config(project)
    base_result: dict[str, Any] = {
        "command": "/spec-inject inject-search",
        "project_root": project.as_posix(),
        "query": query,
        "top_k": int(top_k),
        "collection": qdrant_config["section_collection"],
        "hits": [],
        "warnings": [],
    }
    if not query or not str(query).strip():
        base_result["warnings"].append(
            {"reason_code": "empty_query", "message": "query must be a non-empty string"}
        )
        return base_result
    try:
        from spec_grag.retrieval_index import (
            QdrantHybridRetriever,  # type: ignore[attr-defined]
        )
    except ImportError:
        try:
            from spec_grag.retrieval_index import (  # type: ignore[attr-defined]
                _hit_from_qdrant_point as _hit,  # noqa: F401
            )
            from spec_grag.retrieval_index import (
                HybridRetrievalIndex,
            )
            QdrantHybridRetriever = None  # type: ignore[assignment]
        except ImportError:
            base_result["warnings"].append(
                {"reason_code": "retriever_unavailable", "message": "QdrantHybridRetriever import failed"}
            )
            return base_result
    try:
        from spec_grag.retrieval_index import FlagEmbeddingBgeM3Provider
    except ImportError as exc:
        base_result["warnings"].append(
            {"reason_code": "embedding_unavailable", "message": str(exc)}
        )
        return base_result
    try:
        provider = FlagEmbeddingBgeM3Provider(
            allow_real_provider=True,
            use_fp16=False,
        )
        retriever = _build_hybrid_retriever(
            qdrant_config["url"],
            qdrant_config["section_collection"],
            provider,
        )
    except Exception as exc:  # pragma: no cover - integration boundary
        base_result["warnings"].append(
            {"reason_code": "retriever_init_failed", "message": str(exc)}
        )
        return base_result
    try:
        result = retriever.search(query, top_k=int(top_k))
    except Exception as exc:  # pragma: no cover - integration boundary
        base_result["warnings"].append(
            {"reason_code": "retrieval_failed", "message": str(exc)}
        )
        return base_result
    hits_payload: list[dict[str, Any]] = []
    for hit in getattr(result, "hits", []) or []:
        payload = dict(getattr(hit, "payload", None) or {})
        hits_payload.append(
            {
                "source_section_id": payload.get("source_section_id"),
                "heading_path": payload.get("heading_path") or [],
                "summary": payload.get("summary") or "",
                "search_keys": payload.get("search_keys") or [],
                "identifiers": payload.get("identifiers") or [],
                "related_sections": payload.get("related_sections") or [],
                "score": float(getattr(hit, "score", 0.0) or 0.0),
            }
        )
    base_result["hits"] = hits_payload
    return base_result


def _qdrant_section_config(project: Path) -> dict[str, str]:
    config = _read_project_config(project)
    vector_store = config.get("vector_store") if isinstance(config.get("vector_store"), Mapping) else {}
    return {
        "url": str(vector_store.get("url") or "http://localhost:6333"),
        "section_collection": str(
            vector_store.get("section_collection") or "spec_grag_section"
        ),
    }


def _build_qdrant_client(url: str) -> Any:
    try:
        from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SpecInjectError(f"qdrant_client is unavailable: {exc}") from exc
    return QdrantClient(url)


def _build_hybrid_retriever(url: str, collection: str, provider: Any) -> Any:
    from spec_grag.retrieval_index import HybridRetrievalIndex

    return HybridRetrievalIndex(
        url=url,
        collection=collection,
        provider=provider,
    )


def _resolve_optional_path(project_root: Path, relative: str) -> Path | None:
    relative = (relative or "").strip()
    if not relative:
        return None
    path = Path(relative)
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


def _read_text_or_warning(
    path: Path | None,
    label: str,
) -> tuple[str | None, dict[str, Any] | None]:
    if path is None:
        return None, {"reason_code": f"{label}_unset", "message": f"{label} is not set in config"}
    if not path.is_file():
        return None, {
            "reason_code": f"{label}_missing",
            "message": f"{label} file not found at {path.as_posix()}",
        }
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, {"reason_code": f"{label}_read_error", "message": str(exc)}


spec_inject = run_spec_inject
run_inject = run_spec_inject
inject = run_spec_inject
execute_spec_inject = run_spec_inject


__all__ = [
    "SpecInjectError",
    "run_spec_inject",
    "run_inject_chapters",
    "run_inject_conflicts",
    "run_inject_purpose",
    "run_inject_search",
    "run_inject_section",
    "spec_inject",
    "run_inject",
    "inject",
    "execute_spec_inject",
    "validate_constraints",
]
