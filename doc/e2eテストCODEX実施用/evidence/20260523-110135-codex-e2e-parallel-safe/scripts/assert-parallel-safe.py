#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-110135-codex-e2e-parallel-safe"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def exitcode(name: str) -> int:
    return int(read(EVID / "stdout" / name).strip())


def stdout_json(name: str) -> dict:
    return json.loads(read(EVID / "stdout" / name))


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in read(path).splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def status_shape(obj: dict) -> dict:
    freshness = obj.get("freshness_report") or {}
    return {
        "status": obj.get("status"),
        "mode": obj.get("mode"),
        "retrieval_index_status": obj.get("retrieval_index_status"),
        "related_sections_status": obj.get("related_sections_status"),
        "freshness_status": freshness.get("status"),
        "blocking_reasons": freshness.get("blocking_reasons") or [],
        "pending_conflict_count": obj.get("pending_conflict_count"),
        "failed_sections_count": len(obj.get("failed_sections") or []),
        "failed_sources_count": len(obj.get("failed_sources") or []),
    }


def collect_payloads(project: Path) -> list[dict]:
    state = json.loads((project / ".spec-anchor/state/retrieval_index_state.json").read_text(encoding="utf-8"))
    collection = state["collection_name"]
    # Use qdrant client as an external retrieval client; this reads the actual
    # Qdrant payload, not local implementation objects.
    from qdrant_client import QdrantClient

    client = QdrantClient(url="http://localhost:6333")
    records, _ = client.scroll(collection_name=collection, with_payload=True, limit=100)
    return [dict(point.payload or {}) for point in records]


nodebug = stdout_json("nodebug-core.stdout")
debug = stdout_json("debug-default-core.stdout")
override = stdout_json("debug-override-core.stdout")
fallback = stdout_json("stage-fallback-core.stdout")

debug_project = Path(read(EVID / "artifacts/debug-project-path.txt").strip())
nodebug_project = Path(read(EVID / "artifacts/nodebug-project-path.txt").strip())

debug_default_path = debug_project / ".spec-anchor/state/_debug_related_prompts.jsonl"
nodebug_default_path = nodebug_project / ".spec-anchor/state/_debug_related_prompts.jsonl"
override_path = EVID / "artifacts/related-prompt-override.jsonl"
fallback_invocations = EVID / "artifacts/stage-fallback-provider-invocations.jsonl"

debug_default_records = jsonl(debug_default_path)
override_records = jsonl(override_path)
provider_records = jsonl(fallback_invocations)

payloads = collect_payloads(debug_project)
login_payload = next(
    payload for payload in payloads
    if payload.get("source_section_id") == "docs/spec/auth.md#0002-login-boundary"
)

heading = " / ".join(login_payload.get("heading_path") or [])
summary = login_payload.get("summary") or ""
search_keys = list(login_payload.get("search_keys") or [])
identifiers = list(login_payload.get("identifiers") or [])
expected_parts = [part for part in [
    heading,
    summary,
    " ".join(str(key) for key in search_keys[:8]) if search_keys else "",
    " ".join(str(item) for item in identifiers[:8]) if identifiers else "",
] if part]
expected_text = " | ".join(expected_parts)
actual_text = login_payload.get("text") or ""

raw_sentinel = "raw-body-sentinel-do-not-embed-login-boundary"
late_identifiers = identifiers[8:]

stage_fallback_commands = [record.get("command") for record in provider_records]
stage_fallback_command_models = []
for command in stage_fallback_commands:
    if not command or "--model" not in command:
        stage_fallback_command_models.append(None)
        continue
    index = command.index("--model")
    stage_fallback_command_models.append(command[index + 1] if index + 1 < len(command) else None)

checks = {
    "run_id": RUN_ID,
    "exitcodes": {
        "nodebug": exitcode("nodebug-core.exitcode"),
        "debug_default": exitcode("debug-default-core.exitcode"),
        "debug_override": exitcode("debug-override-core.exitcode"),
        "stage_fallback": exitcode("stage-fallback-core.exitcode"),
    },
    "debug_related_prompt": {
        "nodebug_no_default_log": not nodebug_default_path.exists(),
        "default_log_written": len(debug_default_records) > 0,
        "override_log_written": len(override_records) > 0,
        "override_path_used": override_path.exists(),
        "record_shape_ok": all(
            record.get("prompt_full_sha256")
            and record.get("prompt_len", 0) > 0
            and record.get("primary_section_id")
            and isinstance(record.get("batch_source_ids"), list)
            and isinstance(record.get("involved_section_ids"), list)
            for record in debug_default_records + override_records
        ),
        "result_shape_unchanged": status_shape(nodebug) == status_shape(debug) == status_shape(override),
    },
    "stage_routing_fallback": {
        "stage_routing_removed": "[llm.stage_routing]" not in read(Path(read(EVID / "artifacts/fallback-project-path.txt").strip()) / ".spec-anchor/config.toml"),
        "provider_invocations_written": len(provider_records) > 0,
        "all_invocations_use_first_provider_command": bool(stage_fallback_commands)
        and all(command and command[0] == "codex" for command in stage_fallback_commands),
        "all_invocations_use_first_provider_model": bool(stage_fallback_command_models)
        and all(model == "gpt-5.4-mini" for model in stage_fallback_command_models),
        "core_succeeded": status_shape(fallback)["status"] == "updated",
    },
    "embedding_payload": {
        "payload_found": bool(login_payload),
        "text_matches_formula": actual_text == expected_text,
        "raw_body_sentinel_absent": raw_sentinel not in actual_text,
        "has_more_than_8_identifiers": len(identifiers) > 8,
        "late_identifiers_absent_from_text": bool(late_identifiers)
        and all(identifier not in actual_text for identifier in late_identifiers),
        "search_key_count": len(search_keys),
        "identifier_count": len(identifiers),
        "actual_text": actual_text,
        "expected_text": expected_text,
        "late_identifiers": late_identifiers,
    },
}

checks["passed_debug_related_prompt"] = all(checks["debug_related_prompt"].values())
checks["passed_stage_routing_fallback"] = all(checks["stage_routing_fallback"].values())
checks["passed_embedding_payload_formula"] = (
    checks["embedding_payload"]["payload_found"]
    and checks["embedding_payload"]["text_matches_formula"]
    and checks["embedding_payload"]["raw_body_sentinel_absent"]
)
checks["passed_identifier_limit"] = (
    checks["embedding_payload"]["has_more_than_8_identifiers"]
    and checks["embedding_payload"]["late_identifiers_absent_from_text"]
)
checks["passed_all"] = (
    all(code == 0 for code in checks["exitcodes"].values())
    and checks["passed_debug_related_prompt"]
    and checks["passed_stage_routing_fallback"]
    and checks["passed_embedding_payload_formula"]
    and checks["passed_identifier_limit"]
)

(EVID / "artifacts/parallel-safe-assertions.json").write_text(
    json.dumps(checks, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(checks, ensure_ascii=False, indent=2))
raise SystemExit(0 if checks["passed_all"] else 1)
