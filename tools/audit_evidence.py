#!/usr/bin/env python3
"""Audit spec doc ✅ marks against evidence_map.jsonl entries.

Exit 0 if consistent, exit 1 if mismatches found.

Usage:
    python tools/audit_evidence.py
    python tools/audit_evidence.py --fix   # rewrite spec doc ✅/[ ] from evidence
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_DOC = REPO_ROOT / "doc" / "EXTERNAL_DESIGN.ja.md"
EVIDENCE_ROOT = REPO_ROOT / "doc" / "e2eテスト" / "evidence"

_CHAPTER_RE = re.compile(r"^## (\d+)\. ")
_CHECK_ROW_RE = re.compile(r"^(\| ✅ \||\| \[ \] \||- ✅ |- \[ \] )")


def _parse_spec_doc() -> dict[int, str]:
    """Return {line_number: 'checked' | 'unchecked'} for every verification row."""
    rows: dict[int, str] = {}
    for i, line in enumerate(SPEC_DOC.read_text(encoding="utf-8").splitlines(), 1):
        m = _CHECK_ROW_RE.match(line)
        if not m:
            continue
        mark = m.group(0)
        if "✅" in mark:
            rows[i] = "checked"
        else:
            rows[i] = "unchecked"
    return rows


def _parse_evidence() -> dict[tuple[str, int], dict]:
    """Return {(spec_section, spec_line): best_entry} from all evidence files.

    'best' = highest verification_level among passed entries.
    """
    level_rank = {
        "production_e2e_verified": 4,
        "real_smoke_verified": 3,
        "hybrid_verified": 2,
        "unit_verified": 1,
    }
    best: dict[tuple[str, int], dict] = {}
    for f in sorted(EVIDENCE_ROOT.rglob("evidence_map.jsonl")):
        for raw in f.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if entry.get("result") != "passed":
                continue
            vl = entry.get("verification_level")
            if vl is None:
                continue
            key = (entry.get("spec_section", ""), entry.get("spec_line", 0))
            rank = level_rank.get(vl, 0)
            existing = best.get(key)
            if existing is None or rank > level_rank.get(existing.get("verification_level", ""), 0):
                best[key] = entry
    return best


def _line_to_section_line(spec_lines: list[str], line_no: int) -> tuple[str, int]:
    """Derive (§X, line_no) from spec doc context."""
    current_chapter = "?"
    for i, line in enumerate(spec_lines[:line_no], 1):
        m = _CHAPTER_RE.match(line)
        if m:
            current_chapter = f"§{m.group(1)}"
    return current_chapter, line_no


def audit() -> list[str]:
    """Return list of mismatch descriptions. Empty = consistent."""
    spec_rows = _parse_spec_doc()
    evidence = _parse_evidence()
    spec_lines = SPEC_DOC.read_text(encoding="utf-8").splitlines()
    issues: list[str] = []

    evidence_by_line: dict[int, dict] = {}
    for (sec, line), entry in evidence.items():
        evidence_by_line[line] = entry

    for line_no, status in sorted(spec_rows.items()):
        entry = evidence_by_line.get(line_no)
        has_prod_e2e = (
            entry is not None
            and entry.get("verification_level") == "production_e2e_verified"
        )

        if status == "checked" and not has_prod_e2e:
            sec, _ = _line_to_section_line(spec_lines, line_no)
            vl = entry.get("verification_level", "none") if entry else "no evidence"
            issues.append(
                f"L{line_no} ({sec}): spec doc has ✅ but evidence is {vl} "
                f"(need production_e2e_verified)"
            )
        elif status == "unchecked" and has_prod_e2e:
            sec, _ = _line_to_section_line(spec_lines, line_no)
            issues.append(
                f"L{line_no} ({sec}): evidence has production_e2e_verified but "
                f"spec doc still shows [ ]"
            )

    checked_count = sum(1 for s in spec_rows.values() if s == "checked")
    prod_e2e_count = sum(
        1 for e in evidence.values()
        if e.get("verification_level") == "production_e2e_verified"
    )
    uncovered_lines = set(spec_rows.keys()) - set(evidence_by_line.keys())

    return issues, {
        "spec_checked": checked_count,
        "spec_unchecked": sum(1 for s in spec_rows.values() if s == "unchecked"),
        "evidence_prod_e2e": prod_e2e_count,
        "evidence_total_field_tracked": len(evidence),
        "spec_lines_without_any_evidence": len(uncovered_lines),
    }


def main() -> int:
    issues, stats = audit()

    print("=== Evidence Audit ===")
    print(f"spec doc verification rows: {stats['spec_checked']} ✅ + {stats['spec_unchecked']} [ ] = {stats['spec_checked'] + stats['spec_unchecked']}")
    print(f"evidence (field-tracked, passed): {stats['evidence_total_field_tracked']} unique (section, line)")
    print(f"evidence production_e2e_verified: {stats['evidence_prod_e2e']}")
    print(f"spec lines with no evidence at all: {stats['spec_lines_without_any_evidence']}")
    print()

    if not issues:
        print("OK: spec doc ✅ marks are consistent with evidence_map.jsonl")
        return 0

    print(f"MISMATCH: {len(issues)} issue(s) found:")
    for issue in issues:
        print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
