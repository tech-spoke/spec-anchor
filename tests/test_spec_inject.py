"""`/spec-inject` public API contract tests (post F-9 / F-2 / F-D).

Post-2026-05-19 contract: `/spec-inject` is a freshness gate probe + pending
conflict surfacing only. Constraint generation, validation, evidence_origin
checks, and Conflict Review Item eligibility checks are all Agent / LLM
responsibilities (see EXTERNAL_DESIGN.ja.md §5.3 / §8.5). The CLI must not
call an autonomous LLM provider or rerun `/spec-core`.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


CONFIG = """\
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[context]
storage = ".spec-anchor/context"

[section]
max_heading_level = 4

[llm.providers.fake]
command = "fake-noop"
model = "fake-spec-core"
timeout_sec = 5
max_retries = 0

[embedding]
provider = "fake"
model = "fake-embedding"

[vector_store]
provider = "memory"
"""


@dataclass
class FakeSpecCoreProvider:
    def __post_init__(self) -> None:
        self.calls: list[Any] = []

    @property
    def provider_id(self) -> str:
        return "fake-spec-inject-core"

    def generate(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
        self.calls.append(request)
        section_hashes = getattr(request, "section_hashes", None)
        if (
            str(getattr(request, "stage", "")) == "section_metadata"
            and isinstance(section_hashes, dict)
            and section_hashes
        ):
            return {
                "sections": [
                    {
                        "section_id": str(section_id),
                        "summary": f"summary for {section_id}",
                        "search_keys": ["authentication", "session", "policy"],
                        "related_sections": [],
                    }
                    for section_id in section_hashes
                ]
            }
        section_id = _request_section_id(request)
        return {
            "summary": f"summary for {section_id}",
            "search_keys": ["authentication", "session", "policy"],
            "related_sections": [
                {
                    "target_section_id": "docs/spec/security.md#session",
                    "relation_hint": "depends_on",
                    "reason": "Authentication depends on session expiry rules.",
                    "evidence_terms": ["session"],
                }
            ],
            "chapter_summary": "security chapter anchor",
            "key_topics": ["authentication"],
            "important_sections": [section_id] if section_id else [],
            "notes": [],
        }

    def judge_conflict(self, request: Any, **_: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "outcome": "resolved_by_existing_evidence",
            "severity": "low",
            "warning": "No pending conflict in the fixture.",
        }


class PendingConflictSpecCoreProvider(FakeSpecCoreProvider):
    @property
    def provider_id(self) -> str:
        return "fake-spec-core-pending-conflict"

    def judge_conflict(self, request: Any, **_: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "outcome": "needs_human_review",
            "conflict_id": "conflict-from-spec-core-artifact",
            "severity": "high",
            "why_conflicting": "One source requires session validation while the other makes it optional.",
            "why_llm_cannot_decide": "No higher-priority source resolves the priority.",
            "recommended_next_action": "Ask a human to choose the session validation rule.",
        }


def _inject_module() -> Any:
    return importlib.import_module("spec_anchor.inject")


def _run_spec_inject(project_root: Path, **kwargs: Any) -> Any:
    func = _inject_module().run_spec_inject
    signature = inspect.signature(func)
    supported = {
        name: value
        for name, value in kwargs.items()
        if name in signature.parameters and value is not None
    }
    return func(
        project_root=project_root,
        generated_at="2026-05-06T00:00:00Z",
        **supported,
    )


def _run_spec_core(project_root: Path) -> dict[str, Any]:
    from spec_anchor.core import run_spec_core

    result = run_spec_core(
        project_root=project_root,
        all=True,
        all_mode=True,
        force=True,
        mode="full",
        provider=FakeSpecCoreProvider(),
        generated_at="2026-05-06T00:00:00Z",
    )
    assert _value(result, "freshness_report", "status") == "fresh"
    return result


def _write_project(project_root: Path) -> dict[str, Path]:
    (project_root / ".spec-anchor").mkdir(parents=True)
    (project_root / ".spec-anchor" / "config.toml").write_text(CONFIG)
    (project_root / "docs/core").mkdir(parents=True)
    (project_root / "docs/spec").mkdir(parents=True)
    purpose = project_root / "docs/core/purpose.md"
    concept = project_root / "docs/core/concept.md"
    spec = project_root / "docs/spec/security.md"
    purpose.write_text("# Purpose\nShip reliable authentication behavior.\n")
    concept.write_text("# Core Concept\nSource Specs are the final authority.\n")
    spec.write_text(
        "# Security\n"
        "Intro.\n\n"
        "## Authentication\n"
        "Authentication must validate sessions before privileged actions.\n\n"
        "## Session\n"
        "Sessions expire after inactivity and must be refreshed explicitly.\n"
    )
    return {"purpose": purpose, "concept": concept, "spec": spec}


def _write_conflicting_project(project_root: Path) -> dict[str, Path]:
    paths = _write_project(project_root)
    paths["spec"].write_text(
        "# Security\n"
        "Intro.\n\n"
        "## Authentication\n"
        "Authentication must validate active sessions before privileged actions.\n\n"
        "## Session\n"
        "For the same privileged actions, session validation is optional during migration.\n"
    )
    return paths


def _pending_conflict(conflict_id: str = "conflict-auth-session") -> dict[str, Any]:
    return {
        "conflict_id": conflict_id,
        "status": "pending",
        "severity": "high",
        "source_refs": [
            {"source_section_id": "docs/spec/security.md#authentication"},
            {"source_section_id": "docs/spec/security.md#session"},
        ],
        "why_conflicting": "The active-session requirement cannot be applied safely.",
        "why_llm_cannot_decide": "No higher-priority source defines the exception.",
        "recommended_next_action": "Ask a human to resolve the session rule.",
    }


def _auto_dismissed_conflict(conflict_id: str = "auto-dismissed-conflict") -> dict[str, Any]:
    item = _pending_conflict(conflict_id)
    item["status"] = "dismissed"
    item["resolution"] = {
        "decision": "dismiss",
        "reason": "Source update recheck no longer requires human conflict review.",
        "valid_scope": "global",
        "referenced_source_refs": list(item["source_refs"]),
        "decision_origin": "auto_source_update",
        "previous_status": "pending",
        "applied_at": "2026-05-06T00:00:00Z",
        "auto_dismiss_reason": "source_update_recheck_pair_absent",
    }
    return item


def _write_conflict_review_state(project_root: Path, items: list[dict[str, Any]]) -> None:
    from spec_anchor.freshness import build_freshness_report

    context_dir = project_root / ".spec-anchor" / "context"
    state_dir = project_root / ".spec-anchor" / "state"
    context_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    (context_dir / "conflict_review_items.json").write_text(
        json.dumps({"conflict_review_items": items})
    )
    (state_dir / "freshness.json").write_text(
        json.dumps(build_freshness_report(conflict_review_items=items))
    )


def _value(value: Any, *path: str, default: Any = None) -> Any:
    current = value
    for key in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            current = getattr(current, key, default)
    return current


def _result_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        result = result.to_dict()
    if hasattr(result, "__dict__") and not isinstance(result, dict):
        result = vars(result)
    assert isinstance(result, dict), "InjectResult must be dict-like or dataclass-like"
    return dict(result)


def _text_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {_text_blob(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text_blob(item) for item in value)
    return "" if value is None else str(value)


def _stopped(result: Any) -> bool:
    data = _result_dict(result)
    for key in ("should_stop", "stops", "blocked", "stop"):
        value = data.get(key)
        if isinstance(value, bool):
            return value
    can_continue = data.get("can_continue") or data.get("should_continue")
    if isinstance(can_continue, bool):
        return not can_continue
    status = str(data.get("status") or _value(data, "freshness_report", "status") or "")
    return status in {"blocked", "failed"}


def _request_section_id(request: Any) -> str:
    if isinstance(request, dict):
        return str(request.get("section_id") or request.get("source_section_id") or "unknown")
    return str(getattr(request, "section_id", None) or getattr(request, "source_section_id", None) or "unknown")


# --- gate probe behavior tests ---


def test_t_e01_fresh_core_then_inject_returns_gate_probe_shape(tmp_path: Path) -> None:
    """Fresh state: gate probe returns can_continue True with no answer/constraint fields."""

    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)

    result = _result_dict(_run_spec_inject(project_root))

    assert _stopped(result) is False
    assert result.get("status") == "fresh"
    assert result.get("can_continue") is True
    assert "constraints" not in result
    assert "injectable_context" not in result
    assert "answer" not in result


def test_t_u17_inject_output_has_no_answer_or_constraint_field(tmp_path: Path) -> None:
    """`/spec-inject` must never include answer / final_answer / constraints in output."""

    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)

    result = _result_dict(_run_spec_inject(project_root))
    text = _text_blob(result).lower()

    assert "answer" not in result
    assert "final_answer" not in result
    assert "constraints" not in result
    assert "課題プロンプトへの回答" not in _text_blob(result)
    assert "answer section" not in text


def test_t_i09_pending_conflict_fresh_output_surfaces_items_without_stopping(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    pending = _pending_conflict()

    result = _result_dict(
        _run_spec_inject(
            project_root,
            freshness_report={
                "status": "fresh",
                "blocking_reasons": [],
                "warnings": [],
                "pending_conflict_items": [pending],
            },
        )
    )
    text = _text_blob(result)

    assert _stopped(result) is False
    for expected in (
        "conflict-auth-session",
        "severity",
        "source_refs",
        "why_conflicting",
        "why_llm_cannot_decide",
        "recommended_next_action",
    ):
        assert expected in text
    assert "pending_conflict" not in result.get("blocking_reasons", [])


def test_review_dirty_plus_pending_conflict_does_not_surface_stale_conflict_targets(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    stale_pending = _pending_conflict("stale-conflict-auth-session")

    result = _result_dict(
        _run_spec_inject(
            project_root,
            freshness_report={
                "status": "blocked",
                "blocking_reasons": ["dirty_or_stale_source", "pending_conflict"],
                "warnings": [],
                "pending_conflict_items": [stale_pending],
                "pending_conflict_count": 1,
            },
        )
    )
    text = _text_blob(result)

    assert _stopped(result) is True
    assert "dirty_or_stale_source" in text
    assert "/spec-core" in text
    assert "pending_conflict" not in result.get("blocking_reasons", [])
    assert _value(result, "pending_conflict_items", default=[]) == []
    assert _value(result, "pending_conflict_count", default=0) == 0
    assert "stale-conflict-auth-session" not in text
    assert "why_llm_cannot_decide" not in text


def test_review_pending_conflict_items_are_loaded_from_real_context_artifact(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_conflicting_project(project_root)

    from spec_anchor.core import run_spec_core

    core_result = run_spec_core(
        project_root=project_root,
        all=True,
        all_mode=True,
        force=True,
        mode="full",
        provider=PendingConflictSpecCoreProvider(),
        generated_at="2026-05-06T00:00:00Z",
    )
    assert _value(core_result, "failed_sections", default=[]) == []
    assert _value(core_result, "failed_sources", default=[]) == []
    assert _value(core_result, "pending_conflict_count") >= 1
    freshness = _value(core_result, "freshness_report")
    assert _value(freshness, "status") == "fresh"
    assert _value(freshness, "blocking_reasons") == []

    artifact_path = project_root / ".spec-anchor/context/conflict_review_items.json"
    artifact = json.loads(artifact_path.read_text())
    pending_items = [
        item
        for item in artifact.get("conflict_review_items", [])
        if item.get("status") == "pending"
    ]
    assert pending_items

    result = _result_dict(
        _run_spec_inject(
            project_root,
            freshness_report={
                "status": "fresh",
                "blocking_reasons": [],
                "pending_conflict_count": len(pending_items),
                "warnings": [],
            },
        )
    )

    assert _stopped(result) is False
    assert _value(result, "pending_conflict_items") == pending_items
    text = _text_blob(result)
    # Under the section_pair conflict contract the conflict_id is a derived
    # section_pair id (the judge payload's conflict_id is ignored by the item
    # builder). Assert the loaded item's real id round-trips into the reply.
    pending_conflict_id = str(pending_items[0]["conflict_id"])
    assert pending_conflict_id.startswith("section_pair:")
    assert pending_conflict_id in text
    assert "why_llm_cannot_decide" in text


@pytest.mark.parametrize(
    ("status", "reasons", "recommended"),
    (
        ("blocked", ["dirty_or_stale_source"], "/spec-core"),
        ("blocked", ["stale_config_or_schema"], "/spec-core --all"),
        ("blocked", ["watcher_running"], "watcher"),
        ("blocked", ["watcher_queue_pending"], "watcher"),
        ("failed", ["failed_required_artifact"], "/spec-core"),
    ),
)
def test_t_u18_blocked_or_failed_inject_stops_without_running_spec_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    reasons: list[str],
    recommended: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    import spec_anchor.core as core_module

    calls: list[Any] = []

    def spy_run_spec_core(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append((args, kwargs))
        raise AssertionError("/spec-inject must not run /spec-core automatically")

    monkeypatch.setattr(core_module, "run_spec_core", spy_run_spec_core)
    inject_module = _inject_module()
    if hasattr(inject_module, "run_spec_core"):
        monkeypatch.setattr(inject_module, "run_spec_core", spy_run_spec_core)

    result = _result_dict(
        _run_spec_inject(
            project_root,
            freshness_report={"status": status, "blocking_reasons": reasons, "warnings": []},
        )
    )
    text = _text_blob(result)

    assert calls == []
    assert _stopped(result) is True
    for reason in reasons:
        assert reason in text
    assert recommended in text
    assert "recommended_next_action" in text


def test_spec_inject_reads_freshness_artifact_without_recomputing_core(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)
    freshness_path = project_root / ".spec-anchor/state/freshness.json"
    freshness = json.loads(freshness_path.read_text())
    assert freshness["status"] == "fresh"

    result = _run_spec_inject(project_root)

    assert _stopped(result) is False
    assert _result_dict(result).get("status") == "fresh"


def test_t_i08_inject_does_not_call_agentic_llm_provider(tmp_path: Path) -> None:
    """/spec-inject must never call an autonomous LLM provider, even if one is passed."""

    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)

    class ExplodingAgentProvider:
        provider_id = "must-not-be-used-by-spec-inject"

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, *_: Any, **__: Any) -> dict[str, Any]:
            self.calls += 1
            raise AssertionError("/spec-inject must not call an autonomous LLM provider")

        def judge_conflict(self, *_: Any, **__: Any) -> dict[str, Any]:
            self.calls += 1
            raise AssertionError("/spec-inject must not run /spec-core conflict judging")

    provider = ExplodingAgentProvider()
    result = _run_spec_inject(project_root, provider=provider, llm_provider=provider)

    assert provider.calls == 0
    assert _stopped(result) is False


def test_live_source_dirty_detects_edited_source_after_core(tmp_path: Path) -> None:
    """§3.3: inject gate stops when Source Specs changed after /spec-core."""
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    _run_spec_core(project_root)

    result_before = _result_dict(_run_spec_inject(project_root))
    assert result_before.get("status") == "fresh"
    assert _stopped(result_before) is False

    paths["spec"].write_text(
        "# Security\n"
        "Intro.\n\n"
        "## Authentication\n"
        "Authentication must validate sessions before privileged actions.\n\n"
        "## Session\n"
        "Sessions expire after inactivity and must be refreshed explicitly.\n\n"
        "## Password Reset\n"
        "Password reset tokens expire in 30 minutes.\n"
    )

    result_after = _result_dict(_run_spec_inject(project_root))
    assert result_after.get("status") == "blocked"
    assert "dirty_or_stale_source" in (result_after.get("blocking_reasons") or [])
    assert _stopped(result_after) is True


def test_live_source_dirty_detects_removed_section_after_core(tmp_path: Path) -> None:
    """§3.3: inject gate stops when a section is removed from Source Specs."""
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)

    (project_root / "docs/spec/security.md").write_text(
        "# Security\nIntro.\n\n## Authentication\nValidate sessions.\n"
    )

    result = _result_dict(_run_spec_inject(project_root))
    assert result.get("status") == "blocked"
    assert "dirty_or_stale_source" in (result.get("blocking_reasons") or [])


def test_live_source_dirty_unchanged_source_stays_fresh(tmp_path: Path) -> None:
    """§3.3: inject gate passes when Source Specs are unchanged after /spec-core."""
    project_root = tmp_path / "project"
    _write_project(project_root)
    _run_spec_core(project_root)

    result = _result_dict(_run_spec_inject(project_root))
    assert result.get("status") == "fresh"
    assert _stopped(result) is False
