"""Freshness report and gate helpers.

The helpers in this module are intentionally deterministic and dict-shaped:
callers provide the current freshness inputs, receive a JSON-friendly report,
and can then ask whether `/spec-inject` or `/spec-realign` should continue.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from spec_grag.conflict_review import summarize_conflict_review_state


FRESH = "fresh"
BLOCKED = "blocked"
DEGRADED = "degraded"
FAILED = "failed"

STATUSES = {FRESH, BLOCKED, DEGRADED, FAILED}

DIRTY_OR_STALE_SOURCE = "dirty_or_stale_source"
WATCHER_RUNNING = "watcher_running"
WATCHER_QUEUE_PENDING = "watcher_queue_pending"
STALE_CONFIG_OR_SCHEMA = "stale_config_or_schema"
FAILED_REQUIRED_ARTIFACT = "failed_required_artifact"
PENDING_CONFLICT = "pending_conflict"
DEGRADED_OPTIONAL_ARTIFACT = "degraded_optional_artifact"

REASON_PRIORITY = (
    DIRTY_OR_STALE_SOURCE,
    WATCHER_RUNNING,
    WATCHER_QUEUE_PENDING,
    STALE_CONFIG_OR_SCHEMA,
    FAILED_REQUIRED_ARTIFACT,
    PENDING_CONFLICT,
    DEGRADED_OPTIONAL_ARTIFACT,
)
REASON_PRIORITIES = REASON_PRIORITY
BLOCKING_REASON_PRIORITY = REASON_PRIORITY

KNOWN_REASONS = set(REASON_PRIORITY)
BLOCKED_REASONS = {
    DIRTY_OR_STALE_SOURCE,
    WATCHER_RUNNING,
    WATCHER_QUEUE_PENDING,
    STALE_CONFIG_OR_SCHEMA,
    PENDING_CONFLICT,
}
DIRTY_WATCHER_OR_STALE_REASONS = {
    DIRTY_OR_STALE_SOURCE,
    WATCHER_RUNNING,
    WATCHER_QUEUE_PENDING,
    STALE_CONFIG_OR_SCHEMA,
}
PENDING_CONFLICT_DETAIL_KEYS = ("pending_conflict_items", "conflict_review_items")

SUPPORTED_GATE_COMMANDS = {"inject", "realign", "/spec-inject", "/spec-realign"}


def build_freshness_report(
    state: Mapping[str, Any] | None = None,
    *,
    inputs: Mapping[str, Any] | None = None,
    freshness_inputs: Mapping[str, Any] | None = None,
    project_state: Mapping[str, Any] | None = None,
    context_state: Mapping[str, Any] | None = None,
    source_sections: Sequence[Mapping[str, Any]] | None = None,
    current_sections: Sequence[Mapping[str, Any]] | None = None,
    manifest: Mapping[str, Any] | None = None,
    section_manifest: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
    artifact_statuses: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
    artifact_config: Mapping[str, Any] | None = None,
    watcher: Mapping[str, Any] | Any | None = None,
    watcher_state: Mapping[str, Any] | Any | None = None,
    items: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    dirty_or_stale_source: bool = False,
    dirty_source: bool = False,
    stale_source: bool = False,
    source_dirty: bool = False,
    source_stale: bool = False,
    watcher_running: bool = False,
    watcher_queue_pending: bool = False,
    watcher_queue: Any = None,
    watcher_queue_count: int | None = None,
    queue_pending: bool = False,
    stale_config_or_schema: bool = False,
    config_mismatch: bool = False,
    schema_mismatch: bool = False,
    config_or_schema_mismatch: bool = False,
    failed_required_artifact: bool = False,
    required_artifact_failed: bool = False,
    required_artifact_missing: bool = False,
    missing_required_artifact: bool = False,
    failed_required_artifacts: Sequence[Any] | None = None,
    missing_required_artifacts: Sequence[Any] | None = None,
    required_artifacts_missing: Sequence[Any] | None = None,
    degraded_optional_artifact: bool = False,
    optional_artifact_degraded: bool = False,
    degraded_optional_artifacts: Sequence[Any] | None = None,
    conflict_review_items: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    pending_conflict_count: int | None = None,
    pending_conflicts: int | Sequence[Mapping[str, Any]] | None = None,
    blocking_reasons: Sequence[str] | None = None,
    existing_blocking_reasons: Sequence[str] | None = None,
    warnings: Sequence[Any] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    counts: Mapping[str, Any] | None = None,
    **extra_inputs: Any,
) -> dict[str, Any]:
    """Build a freshness report from explicit booleans and small inputs."""

    state_payload = _first_mapping(state, inputs, freshness_inputs, project_state, context_state)
    source_sections = _coalesce(
        source_sections,
        current_sections,
        _mapping_get(state_payload, "source_sections"),
        _mapping_get(state_payload, "current_sections"),
    )
    manifest = _coalesce(
        manifest,
        section_manifest,
        _mapping_get(state_payload, "manifest"),
        _mapping_get(state_payload, "section_manifest"),
    )
    artifacts = _coalesce(artifacts, _mapping_get(state_payload, "artifacts"))
    artifact_statuses = _coalesce(
        artifact_statuses,
        _mapping_get(state_payload, "artifact_statuses"),
    )
    config = _coalesce(config, _mapping_get(state_payload, "config"))
    artifact_config = _coalesce(artifact_config, _mapping_get(state_payload, "artifact_config"))
    watcher = _coalesce(watcher, watcher_state, _mapping_get(state_payload, "watcher"))
    conflict_review_items = _coalesce(
        conflict_review_items,
        items,
        _mapping_get(state_payload, "conflict_review_items"),
        _mapping_get(state_payload, "items"),
    )

    reasons: list[str] = []
    diagnostics_payload = dict(diagnostics or {})
    counts_payload: dict[str, Any] = dict(counts or {})

    for reason in blocking_reasons or ():
        _add_reason(reasons, reason)
    for reason in existing_blocking_reasons or ():
        _add_reason(reasons, reason)

    if _any_true(
        dirty_or_stale_source,
        dirty_source,
        stale_source,
        source_dirty,
        source_stale,
        extra_inputs.get("source_changed"),
        extra_inputs.get("semantic_source_changed"),
        extra_inputs.get("semantic_change"),
        _state_source_dirty(
            source_sections,
            manifest,
            artifacts,
            current_source_hashes=_current_source_hash_inputs(state_payload, extra_inputs),
        ),
    ):
        _add_reason(reasons, DIRTY_OR_STALE_SOURCE)

    if _any_true(watcher_running, _watcher_value(watcher, "running"), _watcher_value(watcher, "is_running")):
        _add_reason(reasons, WATCHER_RUNNING)

    queue_count = _optional_count(
        _coalesce(watcher_queue_count, _watcher_value(watcher, "queue_count"))
    )
    if queue_count:
        counts_payload["watcher_queue_count"] = queue_count
    if _any_true(
        watcher_queue_pending,
        queue_pending,
        (queue_count or 0) > 0,
        _has_items(watcher_queue),
        _watcher_value(watcher, "queue_pending"),
        _has_items(_watcher_value(watcher, "queue")),
        extra_inputs.get("watcher_queue_non_empty"),
        extra_inputs.get("queued_changes"),
    ):
        _add_reason(reasons, WATCHER_QUEUE_PENDING)

    if _any_true(
        stale_config_or_schema,
        config_mismatch,
        schema_mismatch,
        config_or_schema_mismatch,
        extra_inputs.get("config_changed"),
        extra_inputs.get("schema_changed"),
        extra_inputs.get("model_mismatch"),
        extra_inputs.get("prompt_version_mismatch"),
        extra_inputs.get("embedding_model_mismatch"),
        extra_inputs.get("metadata_version_mismatch"),
        _state_config_or_schema_stale(config, artifact_config, artifacts),
    ):
        _add_reason(reasons, STALE_CONFIG_OR_SCHEMA)

    failed_required = _as_list(failed_required_artifacts)
    missing_required = _as_list(missing_required_artifacts) + _as_list(required_artifacts_missing)
    state_required, state_degraded = _artifact_problem_names(artifacts, artifact_statuses)
    _extend_unique(failed_required, state_required)
    required_problem_count = len(failed_required) + len(missing_required)
    if required_problem_count:
        counts_payload["required_artifact_problem_count"] = required_problem_count
        diagnostics_payload.setdefault("failed_required_artifacts", failed_required)
        diagnostics_payload.setdefault("missing_required_artifacts", missing_required)
    if _any_true(
        failed_required_artifact,
        required_artifact_failed,
        required_artifact_missing,
        missing_required_artifact,
        required_problem_count > 0,
        extra_inputs.get("retrieval_index_failed"),
        extra_inputs.get("retrieval_index_missing"),
        extra_inputs.get("required_artifact_unavailable"),
    ):
        _add_reason(reasons, FAILED_REQUIRED_ARTIFACT)

    degraded_optional = _as_list(degraded_optional_artifacts)
    _extend_unique(degraded_optional, state_degraded)
    if degraded_optional:
        counts_payload["degraded_optional_artifact_count"] = len(degraded_optional)
        diagnostics_payload.setdefault("degraded_optional_artifacts", degraded_optional)
    if _any_true(
        degraded_optional_artifact,
        optional_artifact_degraded,
        bool(degraded_optional),
        extra_inputs.get("optional_artifact_failed"),
        extra_inputs.get("optional_artifact_missing"),
    ):
        _add_reason(reasons, DEGRADED_OPTIONAL_ARTIFACT)

    pending_items = pending_conflict_items(conflict_review_items)
    explicit_pending_count = _pending_count_from_inputs(pending_conflict_count, pending_conflicts)
    pending_count = max(len(pending_items), explicit_pending_count)
    if conflict_review_items is not None:
        summary = summarize_conflict_review_state(conflict_review_items=list(_coerce_items(conflict_review_items)))
        pending_count = max(pending_count, _optional_count(summary.get("pending_conflict_count")) or 0)
    if pending_count:
        _add_reason(reasons, PENDING_CONFLICT)
        counts_payload["pending_conflict_count"] = pending_count

    ordered_reasons = order_blocking_reasons(reasons)
    status = classify_freshness_status(ordered_reasons)
    warning_items = _ordered_warnings(warnings)
    if status == DEGRADED and DEGRADED_OPTIONAL_ARTIFACT not in warning_items:
        warning_items.append(DEGRADED_OPTIONAL_ARTIFACT)

    report: dict[str, Any] = {
        "status": status,
        "blocking_reasons": ordered_reasons,
        "warnings": warning_items,
    }
    if counts_payload:
        report["counts"] = counts_payload
        for key, value in counts_payload.items():
            if key.endswith("_count"):
                report.setdefault(key, value)
    if diagnostics_payload:
        report["diagnostics"] = diagnostics_payload
    return report


def normalize_freshness_report(report: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Return a copy of an existing report with ordered known reasons."""

    payload = _extract_report(report)
    reasons = order_blocking_reasons(_as_list(payload.get("blocking_reasons")))
    status = str(payload.get("status") or "")
    if reasons:
        status = classify_freshness_status(reasons)
    elif status not in STATUSES:
        status = FRESH

    normalized: dict[str, Any] = {
        "status": status,
        "blocking_reasons": reasons,
        "warnings": _ordered_warnings(payload.get("warnings")),
    }
    for key, value in payload.items():
        if key not in normalized:
            normalized[key] = deepcopy(value)
    normalized["status"] = status
    normalized["blocking_reasons"] = reasons
    normalized["warnings"] = _ordered_warnings(normalized.get("warnings"))
    return normalized


def classify_freshness_status(blocking_reasons: Sequence[str] | None = None) -> str:
    """Classify status from ordered or unordered freshness reasons."""

    reasons = set(order_blocking_reasons(blocking_reasons or ()))
    if not reasons:
        return FRESH
    if FAILED_REQUIRED_ARTIFACT in reasons:
        return FAILED
    if reasons & BLOCKED_REASONS:
        return BLOCKED
    if reasons == {DEGRADED_OPTIONAL_ARTIFACT}:
        return DEGRADED
    return BLOCKED


def order_blocking_reasons(reasons: Sequence[str] | None = None) -> list[str]:
    """Return known reasons once, in the required display priority."""

    seen = {str(reason) for reason in (reasons or ()) if str(reason) in KNOWN_REASONS}
    return [reason for reason in REASON_PRIORITY if reason in seen]


def pending_conflict_items(
    conflict_review_items: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return pending Conflict Review Items as JSON-friendly copies."""

    return [
        deepcopy(dict(item))
        for item in _coerce_items(conflict_review_items)
        if item.get("status") == "pending"
    ]


def _pending_payload_for_decision(
    report: Mapping[str, Any],
    *,
    pending_items: Sequence[Mapping[str, Any]] | None,
    conflict_review_items: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    pending_payload = _as_item_list(pending_items)
    if pending_payload:
        return pending_payload
    for source in (
        report.get("pending_conflict_items"),
        report.get("conflict_review_items"),
        conflict_review_items,
    ):
        pending_payload = pending_conflict_items(source)
        if pending_payload:
            return pending_payload
    return []


def _without_pending_conflict_details(report: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = deepcopy(dict(report))
    for key in PENDING_CONFLICT_DETAIL_KEYS:
        sanitized.pop(key, None)
    return sanitized


def build_freshness_gate_decision(
    freshness_report: Mapping[str, Any] | Any | None = None,
    *,
    report: Mapping[str, Any] | Any | None = None,
    command: str = "inject",
    conflict_review_items: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    pending_items: Sequence[Mapping[str, Any]] | None = None,
    **freshness_inputs: Any,
) -> dict[str, Any]:
    """Decide whether `/spec-inject` or `/spec-realign` may continue."""

    source_report = freshness_report if freshness_report is not None else report
    current_report = (
        build_freshness_report(conflict_review_items=conflict_review_items, **freshness_inputs)
        if source_report is None
        else normalize_freshness_report(source_report)
    )
    command_name = normalize_gate_command(command)
    status = str(current_report["status"])
    reasons = list(current_report.get("blocking_reasons", []))
    warnings = list(current_report.get("warnings", []))
    can_continue = status in {FRESH, DEGRADED}
    should_stop = not can_continue
    pending_only = status == BLOCKED and reasons == [PENDING_CONFLICT]
    decision_report = (
        current_report
        if pending_only
        else _without_pending_conflict_details(current_report)
    )

    decision = {
        "command": command_name,
        "status": status,
        "recommended_next_action": recommend_next_action(current_report, command=command_name),
        "blocking_reasons": reasons,
        "warnings": warnings,
        "can_continue": can_continue,
        "should_stop": should_stop,
        "stops": should_stop,
        "freshness_report": decision_report,
    }
    if pending_only:
        pending_payload = _pending_payload_for_decision(
            current_report,
            pending_items=pending_items,
            conflict_review_items=conflict_review_items,
        )
        pending_count = (
            len(pending_payload)
            or _optional_count(current_report.get("pending_conflict_count"))
            or 0
        )
        decision["stop_reason"] = PENDING_CONFLICT
        decision["pending_conflict_items"] = pending_payload
        decision["pending_conflict_count"] = pending_count
    elif should_stop:
        decision["stop_reason"] = reasons[0] if reasons else status
    if status == DEGRADED:
        decision["continues_with_warnings"] = True
    return decision


def normalize_gate_command(command: str | None) -> str:
    """Normalize supported command names to `inject` or `realign`."""

    value = str(command or "inject").strip()
    if value.startswith("/spec-"):
        value = value.removeprefix("/spec-")
    elif value.startswith("spec-"):
        value = value.removeprefix("spec-")
    return value


def recommend_next_action(
    freshness_report: Mapping[str, Any] | Any,
    *,
    command: str = "inject",
) -> str:
    """Return the first recommended action implied by the report priority."""

    report = normalize_freshness_report(freshness_report)
    status = report["status"]
    reasons = report["blocking_reasons"]
    command_label = _command_label(command)

    if status == FRESH:
        return f"continue {command_label}"
    if status == DEGRADED:
        return f"continue {command_label} with warnings"
    if DIRTY_OR_STALE_SOURCE in reasons:
        return f"run /spec-core before {command_label}"
    if WATCHER_RUNNING in reasons or WATCHER_QUEUE_PENDING in reasons:
        return f"wait for watcher completion before {command_label}"
    if STALE_CONFIG_OR_SCHEMA in reasons:
        return f"run /spec-core --all before {command_label}"
    if FAILED_REQUIRED_ARTIFACT in reasons:
        return f"run /spec-core or /spec-core --all before {command_label}"
    if reasons == [PENDING_CONFLICT] or PENDING_CONFLICT in reasons:
        return "resolve pending Conflict Review Items"
    return f"stop before {command_label}"


def can_continue_with_freshness(
    freshness_report: Mapping[str, Any] | Any,
    *,
    command: str = "inject",
) -> bool:
    """Return true when the gate permits command execution."""

    return bool(build_freshness_gate_decision(freshness_report, command=command)["can_continue"])


def _extract_report(report: Mapping[str, Any] | Any) -> dict[str, Any]:
    if hasattr(report, "freshness_report"):
        return _extract_report(getattr(report, "freshness_report"))
    if hasattr(report, "to_dict"):
        return _extract_report(report.to_dict())
    if isinstance(report, Mapping) and "freshness_report" in report:
        return _extract_report(report["freshness_report"])
    if isinstance(report, Mapping):
        return deepcopy(dict(report))
    return {}


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _mapping_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _watcher_value(watcher: Any, key: str) -> Any:
    return _mapping_get(watcher, key)


def _state_source_dirty(
    source_sections: Sequence[Mapping[str, Any]] | None,
    manifest: Mapping[str, Any] | None,
    artifacts: Mapping[str, Any] | None,
    *,
    current_source_hashes: Mapping[str, Any] | None = None,
) -> bool:
    artifact_manifest = _mapping_get(artifacts, "section_manifest")
    manifest_sections = _mapping_get(manifest, "sections")
    artifact_sections = _mapping_get(artifact_manifest, "sections")

    source_sections_known = _is_section_sequence(source_sections)
    manifest_sections_known = _is_section_sequence(manifest_sections)
    artifact_sections_known = _is_section_sequence(artifact_sections)

    current: dict[str, dict[str, Any]] = {}
    current_known = False
    if source_sections_known:
        current = _section_hash_map(source_sections)
        current_known = True
    elif manifest_sections_known:
        current = _section_hash_map(manifest_sections)
        current_known = True

    stored: dict[str, dict[str, Any]] = {}
    stored_known = False
    manifest_as_stored = False
    if artifact_sections_known:
        stored = _section_hash_map(artifact_sections)
        stored_known = True
    elif source_sections_known and manifest_sections_known:
        stored = _section_hash_map(manifest_sections)
        stored_known = True
        manifest_as_stored = True

    if current_known and stored_known:
        if set(current) != set(stored):
            return True
        for section_id, hashes in current.items():
            stored_hashes = stored[section_id]
            if _hash_changed(hashes, stored_hashes, "semantic_hash"):
                return True
            if _hash_changed(hashes, stored_hashes, "source_hash"):
                return True
    if _source_manifest_hash_drift(
        manifest,
        artifact_manifest,
        current_source_hashes=current_source_hashes,
        manifest_as_stored=manifest_as_stored,
    ):
        return True
    return False


def _is_section_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _section_hash_map(sections: Any) -> dict[str, dict[str, Any]]:
    section_map: dict[str, dict[str, Any]] = {}
    if not _is_section_sequence(sections):
        return section_map
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        section_id = section.get("source_section_id") or section.get("section_id") or section.get("id")
        if section_id:
            section_map[str(section_id)] = {
                "source_hash": section.get("source_hash") or section.get("hash"),
                "semantic_hash": section.get("semantic_hash"),
            }
    return section_map


def _hash_changed(current: Mapping[str, Any], stored: Mapping[str, Any], key: str) -> bool:
    current_value = current.get(key)
    stored_value = stored.get(key)
    return current_value is not None and stored_value is not None and current_value != stored_value


def _current_source_hash_inputs(
    state_payload: Mapping[str, Any],
    extra_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "purpose_hash": _coalesce_hash(
            extra_inputs.get("current_purpose_hash"),
            extra_inputs.get("purpose_file_hash"),
            extra_inputs.get("purpose_hash"),
            _mapping_get(state_payload, "current_purpose_hash"),
            _mapping_get(state_payload, "purpose_file_hash"),
            _mapping_get(state_payload, "purpose_hash"),
        ),
        "core_concept_hash": _coalesce_hash(
            extra_inputs.get("current_core_concept_hash"),
            extra_inputs.get("core_concept_file_hash"),
            extra_inputs.get("concept_file_hash"),
            extra_inputs.get("core_concept_hash"),
            extra_inputs.get("concept_hash"),
            _mapping_get(state_payload, "current_core_concept_hash"),
            _mapping_get(state_payload, "core_concept_file_hash"),
            _mapping_get(state_payload, "concept_file_hash"),
            _mapping_get(state_payload, "core_concept_hash"),
            _mapping_get(state_payload, "concept_hash"),
        ),
    }


def _source_manifest_hash_drift(
    manifest: Mapping[str, Any] | None,
    artifact_manifest: Mapping[str, Any] | None,
    *,
    current_source_hashes: Mapping[str, Any] | None,
    manifest_as_stored: bool,
) -> bool:
    current_hashes = current_source_hashes or {}
    for current_keys, stored_keys in (
        (
            ("purpose_hash", "purpose_file_hash"),
            ("purpose_hash", "purpose_file_hash"),
        ),
        (
            ("core_concept_hash", "concept_hash", "core_concept_file_hash", "concept_file_hash"),
            ("core_concept_hash", "concept_hash", "core_concept_file_hash", "concept_file_hash"),
        ),
    ):
        current_hash = _coalesce_hash(
            *(_mapping_get(current_hashes, key) for key in current_keys),
            *_manifest_hash_values(manifest, current_keys),
        )
        stored_hash = _coalesce_hash(
            *_manifest_hash_values(artifact_manifest, stored_keys),
            *(_manifest_hash_values(manifest, stored_keys) if manifest_as_stored else ()),
        )
        if current_hash is not None and stored_hash is not None and current_hash != stored_hash:
            return True
    return False


def _manifest_hash_values(manifest: Mapping[str, Any] | None, keys: Sequence[str]) -> tuple[Any, ...]:
    return tuple(_mapping_get(manifest, key) for key in keys)


def _coalesce_hash(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return str(value)
    return None


def _state_config_or_schema_stale(
    config: Mapping[str, Any] | None,
    artifact_config: Mapping[str, Any] | None,
    artifacts: Mapping[str, Any] | None,
) -> bool:
    if _known_config_changed(config, artifact_config):
        return True

    section_metadata = _mapping_get(artifacts, "section_metadata")

    expected_prompt = _nested_get(config, "prompt_versions", "section_metadata")
    artifact_prompt = _mapping_get(section_metadata, "prompt_version")
    if expected_prompt is not None and artifact_prompt is not None and expected_prompt != artifact_prompt:
        return True

    expected_version = _mapping_get(config, "section_metadata_version")
    artifact_version = _mapping_get(section_metadata, "metadata_version")
    return expected_version is not None and artifact_version is not None and expected_version != artifact_version


def _known_config_changed(config: Mapping[str, Any] | None, artifact_config: Mapping[str, Any] | None) -> bool:
    if config is None or artifact_config is None:
        return False
    keys = (
        ("embedding", "provider"),
        ("embedding", "model"),
        ("llm", "provider"),
        ("llm", "model"),
        ("prompt_versions", "section_metadata"),
        ("section_metadata_version",),
    )
    for path in keys:
        current = _nested_get(config, *path)
        stored = _nested_get(artifact_config, *path)
        if current is not None and stored is not None and current != stored:
            return True
    return False


def _nested_get(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        current = _mapping_get(current, key)
        if current is None:
            return None
    return current


def _artifact_problem_names(
    artifacts: Mapping[str, Any] | None,
    artifact_statuses: Mapping[str, Any] | None,
) -> tuple[list[str], list[str]]:
    required: list[str] = []
    degraded: list[str] = []
    statuses: dict[str, Any] = {}
    if isinstance(artifact_statuses, Mapping):
        statuses.update(artifact_statuses)
    if isinstance(artifacts, Mapping):
        for artifact_name, payload in artifacts.items():
            status = _mapping_get(payload, "status")
            if status is not None:
                statuses.setdefault(str(artifact_name), status)

    for artifact_name, status in statuses.items():
        normalized = str(status).strip().lower()
        if normalized in {"failed", "missing", "error", "unavailable"}:
            if _is_required_artifact(str(artifact_name)):
                required.append(str(artifact_name))
            else:
                degraded.append(str(artifact_name))
        elif normalized == "degraded":
            degraded.append(str(artifact_name))
    return required, degraded


def _is_required_artifact(artifact_name: str) -> bool:
    return artifact_name in {
        "section_manifest",
    }


def _extend_unique(target: list[Any], values: Sequence[Any]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _coerce_items(items: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if items is None:
        return []
    if hasattr(items, "to_dict"):
        return _coerce_items(items.to_dict())
    if isinstance(items, Mapping):
        if "conflict_id" in items:
            return [deepcopy(dict(items))]
        for key in ("conflict_review_items", "items"):
            if key in items:
                return _coerce_items(items[key])
        return []
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        return [deepcopy(dict(item)) for item in items if isinstance(item, Mapping)]
    return []


def _as_item_list(items: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if items is None:
        return []
    return [deepcopy(dict(item)) for item in items if isinstance(item, Mapping)]


def _pending_count_from_inputs(
    pending_conflict_count: int | None,
    pending_conflicts: int | Sequence[Mapping[str, Any]] | None,
) -> int:
    count = _optional_count(pending_conflict_count) or 0
    if isinstance(pending_conflicts, int):
        count = max(count, max(0, pending_conflicts))
    elif pending_conflicts is not None:
        count = max(count, len(_coerce_items(pending_conflicts)))
    return count


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason in KNOWN_REASONS and reason not in reasons:
        reasons.append(reason)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    return bool(value)


def _any_true(*values: Any) -> bool:
    return any(_truthy(value) for value in values)


def _has_items(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return bool(value)
    return _truthy(value)


def _optional_count(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [deepcopy(item) for item in value]
    if isinstance(value, tuple):
        return [deepcopy(item) for item in value]
    if isinstance(value, set):
        return sorted(deepcopy(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [deepcopy(item) for item in value]
    return [deepcopy(value)]


def _ordered_warnings(warnings: Any) -> list[str]:
    ordered: list[str] = []
    for warning in _as_list(warnings):
        text = str(warning)
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def _command_label(command: str) -> str:
    command_name = normalize_gate_command(command)
    if command_name in {"inject", "realign"}:
        return f"/spec-{command_name}"
    return command_name


evaluate_freshness = build_freshness_report
freshness_report = build_freshness_report
assess_freshness = build_freshness_report

evaluate_freshness_gate = build_freshness_gate_decision
decide_freshness_gate = build_freshness_gate_decision
freshness_gate_decision = build_freshness_gate_decision
apply_freshness_gate = build_freshness_gate_decision
evaluate_command_gate = build_freshness_gate_decision
check_command_gate = build_freshness_gate_decision
check_freshness_gate = build_freshness_gate_decision
gate_command = build_freshness_gate_decision

__all__ = [
    "FRESH",
    "BLOCKED",
    "DEGRADED",
    "FAILED",
    "STATUSES",
    "REASON_PRIORITY",
    "REASON_PRIORITIES",
    "BLOCKING_REASON_PRIORITY",
    "DIRTY_OR_STALE_SOURCE",
    "WATCHER_RUNNING",
    "WATCHER_QUEUE_PENDING",
    "STALE_CONFIG_OR_SCHEMA",
    "FAILED_REQUIRED_ARTIFACT",
    "PENDING_CONFLICT",
    "DEGRADED_OPTIONAL_ARTIFACT",
    "build_freshness_report",
    "evaluate_freshness",
    "freshness_report",
    "assess_freshness",
    "normalize_freshness_report",
    "classify_freshness_status",
    "order_blocking_reasons",
    "pending_conflict_items",
    "build_freshness_gate_decision",
    "evaluate_freshness_gate",
    "decide_freshness_gate",
    "freshness_gate_decision",
    "apply_freshness_gate",
    "evaluate_command_gate",
    "check_command_gate",
    "check_freshness_gate",
    "gate_command",
    "normalize_gate_command",
    "recommend_next_action",
    "can_continue_with_freshness",
]
