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

from spec_anchor.freshness import build_freshness_gate_decision, pending_conflict_items


class SpecInjectError(ValueError):
    """Raised when `/spec-inject` inputs are invalid."""


def run_spec_inject(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
    freshness_report: Mapping[str, Any] | Any | None = None,
    freshness: Mapping[str, Any] | Any | None = None,
    provider: Any = None,
    llm_provider: Any = None,
    generated_at: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Return the freshness gate + pending conflict result for `/spec-inject`.

    `provider` and `llm_provider` are accepted for API compatibility only.
    They are deliberately unused because `/spec-inject` must not call an
    autonomous LLM provider or rerun `/spec-core`. Per §5.3 / §8.5 the
    constraint structure (statement / evidence_origin / evidence_ref /
    support_refs / applicability / uncertainty) is the responsibility of
    the Agent / LLM and is not validated by the CLI.
    """

    del provider, llm_provider

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

    result = {
        **base_result,
        "should_stop": False,
        "stops": False,
        "blocked": False,
        "can_continue": True,
    }
    if decision.get("warnings"):
        result["warnings"] = list(decision.get("warnings") or [])
        result["continues_with_warnings"] = bool(decision.get("continues_with_warnings"))
    return result


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


def _read_freshness_artifact(project_root: Path) -> dict[str, Any]:
    from spec_anchor.artifacts import ContextArtifactStore

    store = ContextArtifactStore(_context_dir(project_root))
    path = store.path_for("freshness")
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
    relative = str(storage or ".spec-anchor/context")
    path = Path(relative)
    if path.is_absolute():
        return path
    return project_root / path


def _read_project_config(project_root: Path) -> dict[str, Any]:
    path = project_root / ".spec-anchor" / "config.toml"
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


def _gate_stop_for_command(project: Path, command: str) -> dict[str, Any] | None:
    """Return a stopped result if the freshness gate or pending conflict blocks.

    Each `/spec-inject inject-*` and `/spec-realign` command enforces the
    freshness gate (§3.3), pending conflict gate (§2.8 / §3.4), and watcher
    gate (§6.3) before doing its specific work. The Agent only sees the
    stopped payload — there is no separate `spec-anchor inject` probe to call
    in advance.
    """

    gate = run_spec_inject(project_root=project)
    if not gate.get("should_stop"):
        return None
    result = dict(gate)
    result["command"] = command
    return result


def _config_missing_error_result(
    project: Path, command: str
) -> dict[str, Any] | None:
    """Return §11.1.2 B error shape when `.spec-anchor/config.toml` is missing.

    Per EXTERNAL_DESIGN.ja.md §11.1.5 行 2-3, `spec-anchor inject-*` and
    `spec-anchor realign` must surface config absence as a structured
    `command_error` (status="error") so the Agent can present the recovery
    path (`spec-anchor-setup-project`) to the user. The freshness gate is
    not entered when the config is absent.
    """

    config_path = project / ".spec-anchor" / "config.toml"
    if config_path.is_file():
        return None
    from spec_anchor.config import ConfigError

    message = f".spec-anchor/config.toml not found under {project.as_posix()}"
    return {
        "command": command,
        "project_root": project.as_posix(),
        "status": "error",
        "should_stop": True,
        "stops": True,
        "blocked": True,
        "can_continue": False,
        "constraints": [],
        "error": {
            "code": "command_error",
            "type": ConfigError.__name__,
            "message": message,
        },
    }


def run_inject_section(
    project_root: str | Path = ".",
    *,
    section_ids: Sequence[str],
    root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Phase R-6: id-indexed section payload lookup against Qdrant.

    Returns `{section_id: payload}` for sections that exist in the
    `spec_anchor_section` Qdrant collection. Missing ids are simply absent
    from the result (consistent with `fetch_section_payloads` in
    `spec_anchor/section_payload.py`).

    `doc/EXTERNAL_DESIGN.ja.md` §8.4 (inject-section): used by the Agent
    to follow Related Sections without issuing a new vector search.
    """

    from spec_anchor.section_payload import (
        SectionPayloadLookupError,
        fetch_section_payloads,
    )

    project = _project_root(project_root, root=root, cwd=cwd)
    config_missing = _config_missing_error_result(project, "/spec-inject inject-section")
    if config_missing is not None:
        return config_missing
    gate = _gate_stop_for_command(project, "/spec-inject inject-section")
    if gate is not None:
        return gate
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
    """Phase R-6: return the path to `chapter_anchors.json` for the project.

    `doc/EXTERNAL_DESIGN.ja.md` §8.4 (inject-chapters). Bodies are
    LLM-generated by `/spec-core`. The CLI returns the artifact path so the
    Agent can `Read` it and extract chapters / key_topics / important_sections
    relevant to the current task. Per §3.4 the artifact body is not injected
    wholesale into the response to avoid context bloat.
    """

    project = _project_root(project_root, root=root, cwd=cwd)
    config_missing = _config_missing_error_result(project, "/spec-inject inject-chapters")
    if config_missing is not None:
        return config_missing
    gate = _gate_stop_for_command(project, "/spec-inject inject-chapters")
    if gate is not None:
        return gate
    artifact_path = _context_dir(project) / "chapter_anchors.json"
    warnings: list[dict[str, Any]] = []
    if not artifact_path.is_file():
        warnings.append(
            {
                "reason_code": "chapter_anchors_missing",
                "message": "chapter_anchors.json not found",
            }
        )
    return {
        "command": "/spec-inject inject-chapters",
        "project_root": project.as_posix(),
        "status": "missing" if warnings else "success",
        "chapter_anchors_path": artifact_path.as_posix(),
        "warnings": warnings,
    }


def run_inject_purpose(
    project_root: str | Path = ".",
    *,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Phase R-6: return Purpose full text + Core Concept file path.

    `doc/EXTERNAL_DESIGN.ja.md` §8.4 (inject-purpose). Purpose is short by
    design so its full text is returned. Core Concept can grow large, so
    only the path is returned and the Agent uses `Read` to extract the
    portion relevant to the current task (per §3.4 the artifact body is
    not injected wholesale to avoid context bloat).
    """

    project = _project_root(project_root, root=root, cwd=cwd)
    config_missing = _config_missing_error_result(project, "/spec-inject inject-purpose")
    if config_missing is not None:
        return config_missing
    gate = _gate_stop_for_command(project, "/spec-inject inject-purpose")
    if gate is not None:
        return gate
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
    warnings: list[dict[str, Any]] = []
    if purpose_warning is not None:
        warnings.append(purpose_warning)
    if concept_path is None:
        warnings.append(
            {
                "reason_code": "concept_file_unset",
                "message": "core.concept_file is not configured",
            }
        )
    elif not concept_path.is_file():
        warnings.append(
            {
                "reason_code": "concept_file_missing",
                "message": f"concept_file not found: {concept_path.as_posix()}",
            }
        )
    return {
        "command": "/spec-inject inject-purpose",
        "project_root": project.as_posix(),
        "purpose": purpose_text,
        "core_concept_path": concept_path.as_posix() if concept_path is not None else None,
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
    config_missing = _config_missing_error_result(project, "/spec-inject inject-conflicts")
    if config_missing is not None:
        return config_missing
    gate = _gate_stop_for_command(project, "/spec-inject inject-conflicts")
    if gate is not None:
        return gate
    raw_items = _read_conflict_review_items(project)
    resolved_items: list[dict[str, Any]] = []
    excluded_items: list[dict[str, Any]] = []
    for item in raw_items:
        status = str(item.get("status") or "").strip().lower()
        if status == "resolved":
            # Filter out stale resolutions; the Agent must only cite
            # non-stale resolved items as `evidence_origin = "Conflict
            # Review Item"`.
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
    top_k: int | None = None,
    root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Phase R-6: section-level hybrid retrieval against the Qdrant section collection.

    `doc/EXTERNAL_DESIGN.ja.md` §8.4 (inject-search). Returns the top-K
    section payloads (source_document_id / source_section_id / source_span /
    heading / summary / search_keys / identifiers / related_sections / score)
    ranked by RRF over BGE-M3 dense + sparse vectors. `top_k` defaults to
    `[retrieval].section_final_top_n` from project config (default 8 when
    omitted). When Qdrant or FlagEmbedding is unavailable, the call returns
    a structured warning instead of raising so the Agent can fall back to
    other paths (§8.3 path ②/③/④).
    """

    project = _project_root(project_root, root=root, cwd=cwd)
    config_missing = _config_missing_error_result(project, "/spec-inject inject-search")
    if config_missing is not None:
        return config_missing
    gate = _gate_stop_for_command(project, "/spec-inject inject-search")
    if gate is not None:
        return gate
    qdrant_config = _qdrant_section_config(project)
    if top_k is None:
        project_config = _read_project_config(project)
        retrieval = (
            project_config.get("retrieval")
            if isinstance(project_config.get("retrieval"), Mapping)
            else {}
        )
        top_k = int(retrieval.get("section_final_top_n", 8))
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
        from spec_anchor.retrieval_index import (
            FlagEmbeddingBgeM3Provider,
            QdrantHybridRetriever,
        )
    except ImportError as exc:
        base_result["warnings"].append(
            {"reason_code": "retriever_unavailable", "message": str(exc)}
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
        result = retriever.search(query, limit=int(top_k))
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
                "source_document_id": payload.get("source_document_id"),
                "source_section_id": payload.get("source_section_id"),
                "source_span": payload.get("source_span") or {},
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
    retrieval = config.get("retrieval") if isinstance(config.get("retrieval"), Mapping) else {}
    return {
        "url": str(vector_store.get("url") or "http://localhost:6333"),
        "section_collection": str(
            retrieval.get("section_collection") or "spec_anchor_section"
        ),
    }


def _build_qdrant_client(url: str) -> Any:
    try:
        from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SpecInjectError(f"qdrant_client is unavailable: {exc}") from exc
    return QdrantClient(url)


def _build_hybrid_retriever(url: str, collection: str, provider: Any) -> Any:
    """Build the live BGE-M3 + Qdrant section-level retriever.

    Uses `QdrantHybridRetriever` (real Qdrant + BGE-M3 dense/sparse + RRF)
    against the section-level collection (`[retrieval].section_collection`).
    """

    from spec_anchor.retrieval_index import QdrantHybridRetriever

    return QdrantHybridRetriever(
        url=url,
        collection=collection,
        embedding_provider=provider,
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
]
