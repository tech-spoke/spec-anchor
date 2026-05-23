#!/usr/bin/env python3
"""F006 retest assertions after fix.

Corrected field expectations vs. original:
- inject-search does NOT return should_stop / blocking_reasons / results.
  Use hits (search hits) and warnings instead.
- core top-level status must now be "degraded" (Issue 1 fix).
- inject-search warnings must contain "degraded_optional_artifact" (Issue 2 fix).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-f006-retest-after-fix"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def exitcode(name: str) -> int:
    return int(read(EVID / "stdout" / name).strip())


def stdout_json(name: str) -> dict:
    return json.loads(read(EVID / "stdout" / name))


core = stdout_json("core-rebuild.stdout")
inject = stdout_json("inject-search.stdout")
freshness = core.get("freshness_report") or {}
diagnostics = core.get("diagnostics") or {}
metadata_diag = diagnostics.get("section_metadata_generation") or {}

failed_sections = list(core.get("failed_sections") or [])
failed_section_text = json.dumps(failed_sections, ensure_ascii=False)
updated_sections = list(core.get("updated_sections") or [])
core_warnings = list(core.get("warnings") or [])
inject_warnings = list(inject.get("warnings") or [])
degraded_optional = list((freshness.get("diagnostics") or {}).get("degraded_optional_artifacts") or [])

checks = {
    "run_id": RUN_ID,
    "exitcodes": {
        "core_rebuild": exitcode("core-rebuild.exitcode"),
        "inject_search": exitcode("inject-search.exitcode"),
    },
    # Issue 1: core top-level status must be "degraded" (was "updated" before fix)
    "core_degraded_contract": {
        "top_level_status_degraded": core.get("status") == "degraded",
        "freshness_status_degraded": freshness.get("status") == "degraded",
        "blocking_reason_degraded_optional": freshness.get("blocking_reasons") == ["degraded_optional_artifact"],
        "degraded_optional_section_metadata": "section_metadata" in degraded_optional,
        "failed_sections_nonempty": bool(failed_sections),
        "failed_section_is_broken": "broken-metadata-section" in failed_section_text,
        "updated_sections_nonempty": bool(updated_sections),
        "retrieval_index_success": core.get("retrieval_index_status") == "success",
        "related_sections_success": core.get("related_sections_status") == "success",
    },
    # Issue 2: inject-search must propagate degraded warning (was empty before fix)
    # inject-search returns: command / project_root / query / top_k / collection / hits / warnings
    # It does NOT return: should_stop / blocking_reasons / results
    "inject_degraded_continue_contract": {
        "not_stopped": inject.get("should_stop") is not True,
        "hits_field_present": "hits" in inject,
        "warnings_contains_degraded_optional_artifact": any(
            "degraded_optional_artifact" in str(w) for w in inject_warnings
        ),
    },
    "raw": {
        "core_status": core.get("status"),
        "freshness_status": freshness.get("status"),
        "failed_sections": failed_sections,
        "updated_sections": updated_sections[:3],
        "inject_warnings": inject_warnings,
        "inject_hits_count": len(inject.get("hits") or []),
    },
}
checks["passed_core_degraded_contract"] = all(checks["core_degraded_contract"].values())
checks["passed_inject_degraded_continue"] = all(checks["inject_degraded_continue_contract"].values())
checks["passed_all"] = (
    all(code == 0 for code in checks["exitcodes"].values())
    and checks["passed_core_degraded_contract"]
    and checks["passed_inject_degraded_continue"]
)

out = EVID / "artifacts/f006-retest-assertions.json"
out.write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(checks, ensure_ascii=False, indent=2))
raise SystemExit(0 if checks["passed_all"] else 1)
