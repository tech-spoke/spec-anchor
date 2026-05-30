"""Tests for `spec-anchor core --dismiss-conflict` (TODO #3 T-dismiss-cli).

These cover the single human-facing dismissal write path: a pending Conflict
Review Item becomes ``dismissed`` with ``referenced_source_refs`` recorded and a
mandatory ``--reason``; non-existent ids, non-pending ids, and empty reasons are
surfaced as structured errors.
"""

from __future__ import annotations

import json
from pathlib import Path

from spec_anchor import cli
from spec_anchor.core import run_dismiss_conflict


def _write_config(project_root: Path) -> None:
    (project_root / ".spec-anchor").mkdir(parents=True, exist_ok=True)
    (project_root / ".spec-anchor" / "config.toml").write_text(
        '[context]\nstorage = ".spec-anchor/context"\n',
        encoding="utf-8",
    )


def _context_dir(project_root: Path) -> Path:
    return project_root / ".spec-anchor" / "context"


def _pending_item(conflict_id: str = "cnf-1") -> dict:
    return {
        "conflict_id": conflict_id,
        "status": "pending",
        "severity": "medium",
        "source_refs": [
            {"source_section_id": "sec-1", "source_hash": "h1"},
            {"source_section_id": "sec-2", "source_hash": "h2"},
        ],
        "claims": [],
        "why_conflicting": "two sections disagree",
        "why_llm_cannot_decide": "no safe priority",
        "decision_options": [{"id": "dismiss", "label": "Dismiss as not a conflict"}],
        "base_source_hashes": [
            {"source_ref": "sec-1", "hash": "h1"},
            {"source_ref": "sec-2", "hash": "h2"},
        ],
        "valid_scope": "global",
        "reflection_status": "unreflected",
        "created_at": "2026-05-30T00:00:00Z",
        "updated_at": "2026-05-30T00:00:00Z",
    }


def _write_items(project_root: Path, items: list[dict]) -> None:
    context_dir = _context_dir(project_root)
    context_dir.mkdir(parents=True, exist_ok=True)
    (context_dir / "conflict_review_items.json").write_text(
        json.dumps({"conflict_review_items": items}), encoding="utf-8"
    )


def _read_items(project_root: Path) -> list[dict]:
    payload = json.loads(
        (_context_dir(project_root) / "conflict_review_items.json").read_text()
    )
    return payload["conflict_review_items"]


def test_dismiss_marks_item_dismissed_and_records_evidence(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_items(tmp_path, [_pending_item("cnf-1")])

    result = run_dismiss_conflict(
        tmp_path, conflict_id="cnf-1", reason="not actually a conflict"
    )

    assert result["status"] == "dismissed"
    assert result["conflict_id"] == "cnf-1"
    item = _read_items(tmp_path)[0]
    assert item["status"] == "dismissed"
    resolution = item["resolution"]
    assert resolution["decision"] == "dismiss"
    assert resolution["decision_origin"] == "human"
    assert resolution["referenced_source_refs"]
    assert item["base_source_hashes"]


def test_dismiss_unknown_conflict_id_is_error(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_items(tmp_path, [_pending_item("cnf-1")])

    result = run_dismiss_conflict(tmp_path, conflict_id="missing", reason="x")

    assert result["status"] == "error"
    assert result["error"]["code"] == "conflict_not_found"


def test_dismiss_non_pending_conflict_is_error(tmp_path: Path) -> None:
    _write_config(tmp_path)
    item = _pending_item("cnf-1")
    item["status"] = "dismissed"
    _write_items(tmp_path, [item])

    result = run_dismiss_conflict(tmp_path, conflict_id="cnf-1", reason="x")

    assert result["status"] == "error"
    assert result["error"]["code"] == "conflict_not_pending"


def test_dismiss_empty_reason_is_error(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_items(tmp_path, [_pending_item("cnf-1")])

    result = run_dismiss_conflict(tmp_path, conflict_id="cnf-1", reason="   ")

    assert result["status"] == "error"
    assert result["error"]["code"] == "missing_reason"
    assert _read_items(tmp_path)[0]["status"] == "pending"


def test_dismiss_via_cli_emits_json_and_exit_zero(tmp_path, capsys, monkeypatch) -> None:
    _write_config(tmp_path)
    _write_items(tmp_path, [_pending_item("cnf-1")])
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(
        ["core", "--dismiss-conflict", "cnf-1", "--reason", "not a conflict"]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "dismissed"
    assert _read_items(tmp_path)[0]["status"] == "dismissed"


def test_dismiss_via_cli_missing_reason_exit_one(tmp_path, capsys, monkeypatch) -> None:
    _write_config(tmp_path)
    _write_items(tmp_path, [_pending_item("cnf-1")])
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["core", "--dismiss-conflict", "cnf-1"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "missing_reason"
