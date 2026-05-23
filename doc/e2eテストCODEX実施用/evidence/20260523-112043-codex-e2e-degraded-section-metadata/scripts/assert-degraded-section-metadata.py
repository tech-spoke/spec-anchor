#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-112043-codex-e2e-degraded-section-metadata"
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
warnings = list(core.get("warnings") or [])
degraded_optional = list((freshness.get("diagnostics") or {}).get("degraded_optional_artifacts") or [])

checks = {
    "run_id": RUN_ID,
    "exitcodes": {
        "core_rebuild": exitcode("core-rebuild.exitcode"),
        "inject_search": exitcode("inject-search.exitcode"),
    },
    "core_degraded": {
        "status_degraded": core.get("status") == "degraded",
        "freshness_degraded": freshness.get("status") == "degraded",
        "blocking_reason_degraded_optional": freshness.get("blocking_reasons") == ["degraded_optional_artifact"],
        "degraded_optional_section_metadata": "section_metadata" in degraded_optional,
        "failed_sections_nonempty": bool(failed_sections),
        "failed_section_is_broken": "broken-metadata-section" in failed_section_text,
        "updated_sections_nonempty": bool(updated_sections),
        "warning_mentions_failed_section": any("broken-metadata-section" in warning for warning in warnings),
        "metadata_freshness_status_degraded": metadata_diag.get("freshness_status") == "degraded",
        "retrieval_index_success": core.get("retrieval_index_status") == "success",
        "related_sections_success": core.get("related_sections_status") == "success",
    },
    "inject_continues_on_degraded": {
        "status_not_blocked": inject.get("status") != "blocked",
        "should_stop_false": inject.get("should_stop") is False,
        "blocking_reasons_degraded_optional": inject.get("blocking_reasons") == ["degraded_optional_artifact"],
        "warnings_present": bool(inject.get("warnings")),
        "results_present": bool(inject.get("results")),
    },
    "failed_sections": failed_sections,
    "updated_sections": updated_sections,
}
checks["passed_core_degraded_contract"] = all(checks["core_degraded"].values())
checks["passed_inject_degraded_continue"] = all(checks["inject_continues_on_degraded"].values())
checks["passed_all"] = (
    all(code == 0 for code in checks["exitcodes"].values())
    and checks["passed_core_degraded_contract"]
    and checks["passed_inject_degraded_continue"]
)

(EVID / "artifacts/degraded-section-metadata-assertions.json").write_text(
    json.dumps(checks, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(checks, ensure_ascii=False, indent=2))
raise SystemExit(0 if checks["passed_all"] else 1)
