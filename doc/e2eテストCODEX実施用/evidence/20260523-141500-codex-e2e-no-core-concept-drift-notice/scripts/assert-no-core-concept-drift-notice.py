#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-141500-codex-e2e-no-core-concept-drift-notice"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID

FORBIDDEN_MARKERS = (
    "core_concept_drift",
    "concept_drift",
    "core concept drift",
    "core concept stale",
    "concept_stale",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def exit_code(name: str) -> int:
    return int(read_text(EVID / f"stdout/{name}.exitcode").strip())


def marker_hits(payload: Any) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    return [marker for marker in FORBIDDEN_MARKERS if marker in text]


def section_ids(values: Any) -> list[str]:
    ids: list[str] = []
    if not isinstance(values, list):
        return ids
    for item in values:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            value = item.get("source_section_id") or item.get("section_id")
            if value:
                ids.append(str(value))
    return ids


def main() -> int:
    initial = read_json(EVID / "stdout/core-initial.stdout")
    after = read_json(EVID / "stdout/core-after-source-change.stdout")
    freshness = read_json(EVID / "artifacts/freshness-after-source-change.json")
    manifest = read_json(EVID / "artifacts/section-manifest-after-source-change.json")
    changed_sections = section_ids(after.get("updated_sections"))
    checks = {
        "initial_exit_zero": exit_code("core-initial") == 0,
        "after_change_exit_zero": exit_code("core-after-source-change") == 0,
        "source_change_was_processed": "docs/spec/policy.md#0003-source-specs-evolved" in changed_sections,
        "core_status_not_failed": after.get("status") in {"updated", "degraded"},
        "no_core_concept_drift_marker_in_core_stdout": not marker_hits(after),
        "no_core_concept_drift_marker_in_freshness": not marker_hits(freshness),
        "no_core_concept_drift_marker_in_manifest": not marker_hits(manifest),
    }
    result = {
        "run_id": RUN_ID,
        "checks": checks,
        "initial_status": initial.get("status"),
        "after_change_status": after.get("status"),
        "updated_sections": changed_sections,
        "freshness_status": freshness.get("status"),
        "freshness_blocking_reasons": freshness.get("blocking_reasons"),
        "forbidden_marker_hits": {
            "core_stdout": marker_hits(after),
            "freshness": marker_hits(freshness),
            "section_manifest": marker_hits(manifest),
        },
        "passed_all": all(checks.values()),
    }
    out = EVID / "artifacts/no-core-concept-drift-notice-assertions.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
