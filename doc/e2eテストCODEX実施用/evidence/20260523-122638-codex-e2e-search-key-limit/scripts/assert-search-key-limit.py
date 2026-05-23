#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-122638-codex-e2e-search-key-limit"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def exitcode(name: str) -> int:
    return int(read(EVID / "stdout" / name).strip())


def stdout_json(name: str) -> dict:
    return json.loads(read(EVID / "stdout" / name))


def collect_payloads(project: Path) -> list[dict]:
    state = json.loads(
        (project / ".spec-anchor/state/retrieval_index_state.json").read_text(
            encoding="utf-8"
        )
    )
    collection = state["collection_name"]
    from qdrant_client import QdrantClient

    client = QdrantClient(url="http://localhost:6333")
    records, _ = client.scroll(collection_name=collection, with_payload=True, limit=100)
    return [dict(point.payload or {}) for point in records]


project = Path(read(EVID / "artifacts/project-path.txt").strip())
core = stdout_json("core-rebuild.stdout")
payloads = collect_payloads(project)
login_payload = next(
    (
        payload
        for payload in payloads
        if payload.get("source_section_id") == "docs/spec/limit.md#0002-login-limit"
    ),
    {},
)

heading = " / ".join(login_payload.get("heading_path") or [])
summary = login_payload.get("summary") or ""
search_keys = list(login_payload.get("search_keys") or [])
identifiers = list(login_payload.get("identifiers") or [])
expected_parts = [
    part
    for part in [
        heading,
        summary,
        " ".join(str(key) for key in search_keys[:8]) if search_keys else "",
        " ".join(str(item) for item in identifiers[:8]) if identifiers else "",
    ]
    if part
]
expected_text = " | ".join(expected_parts)
actual_text = login_payload.get("text") or ""
late_generated_search_keys = [
    key for key in search_keys[8:] if str(key).startswith("limit search key ")
]
late_identifiers = identifiers[8:]

checks = {
    "run_id": RUN_ID,
    "exitcodes": {
        "core_rebuild": exitcode("core-rebuild.exitcode"),
    },
    "core": {
        "status_updated": core.get("status") == "updated",
        "retrieval_index_success": core.get("retrieval_index_status") == "success",
        "related_sections_success": core.get("related_sections_status") == "success",
    },
    "payload": {
        "payload_found": bool(login_payload),
        "search_key_count_gt_8": len(search_keys) > 8,
        "identifier_count_gt_8": len(identifiers) > 8,
        "text_matches_formula": actual_text == expected_text,
        "late_generated_search_keys_absent_from_text": bool(late_generated_search_keys)
        and all(str(key) not in actual_text for key in late_generated_search_keys),
        "late_identifiers_absent_from_text": bool(late_identifiers)
        and all(str(identifier) not in actual_text for identifier in late_identifiers),
        "search_keys": search_keys,
        "identifiers": identifiers,
        "late_generated_search_keys": late_generated_search_keys,
        "late_identifiers": late_identifiers,
        "actual_text": actual_text,
        "expected_text": expected_text,
    },
}
checks["passed_core"] = all(checks["core"].values())
checks["passed_search_key_limit"] = (
    checks["payload"]["payload_found"]
    and checks["payload"]["search_key_count_gt_8"]
    and checks["payload"]["text_matches_formula"]
    and checks["payload"]["late_generated_search_keys_absent_from_text"]
)
checks["passed_identifier_limit"] = (
    checks["payload"]["payload_found"]
    and checks["payload"]["identifier_count_gt_8"]
    and checks["payload"]["text_matches_formula"]
    and checks["payload"]["late_identifiers_absent_from_text"]
)
checks["passed_all"] = (
    all(code == 0 for code in checks["exitcodes"].values())
    and checks["passed_core"]
    and checks["passed_search_key_limit"]
    and checks["passed_identifier_limit"]
)

(EVID / "artifacts/search-key-limit-assertions.json").write_text(
    json.dumps(checks, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(checks, ensure_ascii=False, indent=2))
raise SystemExit(0 if checks["passed_all"] else 1)
