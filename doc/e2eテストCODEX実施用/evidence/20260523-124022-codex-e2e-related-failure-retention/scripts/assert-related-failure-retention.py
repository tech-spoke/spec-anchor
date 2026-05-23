#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-124022-codex-e2e-related-failure-retention"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def exitcode(name: str) -> int:
    return int(read(EVID / "stdout" / name).strip())


def stdout_json(name: str) -> dict:
    return json.loads(read(EVID / "stdout" / name))


def payload_for(path: Path, section_id: str) -> dict:
    data = json.loads(read(path))
    for payload in data.get("payloads") or []:
        if payload.get("source_section_id") == section_id:
            return payload
    return {}


section_id = "docs/spec/flow.md#0002-login-boundary"
initial = stdout_json("initial-core-rebuild.stdout")
broken = stdout_json("broken-qdrant-core.stdout")
inject = stdout_json("inject-after-failure.stdout")
realign = stdout_json("realign-after-failure.stdout")
before_payload = payload_for(EVID / "artifacts/before-failure-payloads.json", section_id)
after_payload = payload_for(EVID / "artifacts/after-failure-payloads.json", section_id)
before_related = before_payload.get("related_sections") or []
after_related = after_payload.get("related_sections") or []

checks = {
    "run_id": RUN_ID,
    "exitcodes": {
        "initial_core_rebuild": exitcode("initial-core-rebuild.exitcode"),
        "broken_qdrant_core": exitcode("broken-qdrant-core.exitcode"),
        "inject_after_failure": exitcode("inject-after-failure.exitcode"),
        "realign_after_failure": exitcode("realign-after-failure.exitcode"),
    },
    "initial_success": {
        "status_updated": initial.get("status") == "updated",
        "related_sections_success": initial.get("related_sections_status") == "success",
        "retrieval_index_success": initial.get("retrieval_index_status") == "success",
        "before_related_nonempty": bool(before_related),
    },
    "failure_status": {
        "status_failed": broken.get("status") == "failed",
        "related_sections_failed": broken.get("related_sections_status") == "failed",
        "freshness_failed": (broken.get("freshness_report") or {}).get("status") == "failed",
        "failed_required_artifact": "failed_required_artifact"
        in ((broken.get("freshness_report") or {}).get("blocking_reasons") or []),
        "warning_mentions_related_backend": "Related Sections retrieval backend failure"
        in json.dumps(broken.get("warnings") or [], ensure_ascii=False),
    },
    "retention": {
        "after_payload_found": bool(after_payload),
        "after_related_nonempty": bool(after_related),
        "related_sections_unchanged": before_related == after_related,
    },
    "downstream_stop": {
        "inject_status_failed": inject.get("status") == "failed",
        "inject_should_stop": inject.get("should_stop") is True,
        "inject_failed_required_artifact": "failed_required_artifact"
        in (inject.get("blocking_reasons") or []),
        "inject_recommends_core": "spec-core" in str(inject.get("recommended_next_action")),
        "realign_status_failed": realign.get("status") == "failed",
        "realign_should_stop": realign.get("should_stop") is True,
        "realign_failed_required_artifact": "failed_required_artifact"
        in (realign.get("blocking_reasons") or []),
        "realign_recommends_core": "spec-core" in str(realign.get("recommended_next_action")),
    },
}
checks["passed_initial"] = all(checks["initial_success"].values())
checks["passed_failure_status"] = all(checks["failure_status"].values())
checks["passed_retention"] = all(checks["retention"].values())
checks["passed_downstream_stop"] = all(checks["downstream_stop"].values())
checks["passed_all"] = (
    checks["exitcodes"]["initial_core_rebuild"] == 0
    and checks["exitcodes"]["broken_qdrant_core"] == 1
    and checks["exitcodes"]["inject_after_failure"] == 0
    and checks["exitcodes"]["realign_after_failure"] == 0
    and checks["passed_initial"]
    and checks["passed_failure_status"]
    and checks["passed_retention"]
    and checks["passed_downstream_stop"]
)

(EVID / "artifacts/related-failure-retention-assertions.json").write_text(
    json.dumps(checks, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(checks, ensure_ascii=False, indent=2))
raise SystemExit(0 if checks["passed_all"] else 1)
