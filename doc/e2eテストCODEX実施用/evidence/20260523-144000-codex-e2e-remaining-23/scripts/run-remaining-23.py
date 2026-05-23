#!/home/kazuki/public_html/spec-anchor/.venv/bin/python
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any


REPO = Path("/home/kazuki/public_html/spec-anchor")
RUN_ID = "20260523-144000-codex-e2e-remaining-23"
EVID = REPO / "doc/e2eテストCODEX実施用/evidence" / RUN_ID
BASE = Path("/tmp") / RUN_ID
PYTHON = REPO / ".venv/bin/python"
SPEC_ANCHOR = REPO / ".venv/bin/spec-anchor"
SETUP_PROJECT = REPO / ".venv/bin/spec-anchor-setup-project"
SETUP_SYSTEM = REPO / ".venv/bin/spec-anchor-setup-system"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def env_without_fakes() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{REPO / '.venv/bin'}:{env.get('PATH', '')}"
    env.pop("SPEC_ANCHOR_FAKE_LLM", None)
    env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    return env


def run(
    label: str,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    (EVID / "stdout").mkdir(parents=True, exist_ok=True)
    (EVID / "stderr").mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env or env_without_fakes(),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    write(EVID / f"stdout/{label}.stdout", completed.stdout)
    write(EVID / f"stderr/{label}.stderr", completed.stderr)
    write(EVID / f"stdout/{label}.exitcode", f"{completed.returncode}\n")
    with (EVID / "commands.log").open("a", encoding="utf-8") as handle:
        handle.write(f"[{label}] cwd={cwd} cmd={json.dumps(args, ensure_ascii=False)} exit={completed.returncode}\n")
    return completed


def configure_project(project: Path, *, collection: str, provider_mode: str) -> None:
    provider = project / "tools/remaining-provider.py"
    provider_log = EVID / f"artifacts/{provider_mode}-provider-invocations.jsonl"
    command = f"{provider} {provider_mode} {provider_log}"
    config = project / ".spec-anchor/config.toml"
    text = config.read_text(encoding="utf-8")
    for key in ("section_collection", "collection"):
        text = text.replace(f'{key} = "spec_anchor_sections"', f'{key} = "{collection}"')
        text = text.replace(f'{key} = "spec_anchor_section"', f'{key} = "{collection}"')
    text = text.replace(
        '[llm.providers.codex]\ncommand = "codex"',
        (
            '[llm.providers.remaining]\n'
            f'command = "{command}"\n'
            f'model = "remaining-{provider_mode}"\n'
            'effort = "low"\n'
            'timeout_sec = 30\n'
            'max_retries = 0\n\n'
            '[llm.providers.codex]\ncommand = "codex"'
        ),
    )
    text = text.replace('section_metadata   = "codex"', 'section_metadata   = "remaining"')
    text = text.replace('related_sections   = "claude_typing"', 'related_sections   = "remaining"')
    text = text.replace('conflict_review    = "claude_judge"', 'conflict_review    = "remaining"')
    text = text.replace('chapter_key_anchor = "codex"', 'chapter_key_anchor = "remaining"')
    config.write_text(text, encoding="utf-8")


def prepare_project(name: str, *, collection: str, provider_mode: str) -> Path:
    project = BASE / f"{name}.project"
    shutil.rmtree(project, ignore_errors=True)
    project.mkdir(parents=True)
    run(f"{name}-setup", [str(SETUP_PROJECT), "--target", str(project), "--agent", "both", "--force"], cwd=project)

    write(
        project / "docs/core/purpose.md",
        """
        # Purpose

        この隔離 project は、残っていた Codex 進捗チェックを外部入出力で確認する。
        """,
    )
    write(
        project / "docs/core/concept.md",
        """
        # Core Concept

        ## Evidence Boundary

        Section Search Keys と Section Identifiers は検索補助であり、制約根拠ではない。

        ## Human Ownership

        Purpose と Core Concept は人間が管理し、`/spec-core` は自動更新しない。
        """,
    )
    write(
        project / "docs/spec/runtime.md",
        """
        # Runtime Specification

        ## Session Runtime Contract

        source id: session-runtime

        The session runtime uses `AUTH_TOKEN` and `bindContext` to attach a user session.
        Operators may run `spec-anchor core --rebuild` when retrieval payloads are stale.
        The config file `.spec-anchor/config.toml` stores the section collection name.
        ProductStore and productStoreGroup.replace are implementation identifiers, not natural-language search keys.

        Related: docs/spec/runtime.md#search-evidence-boundary

        ## Search Evidence Boundary

        source id: search-evidence-boundary

        Natural language search phrases help discovery, but they do not become constraints.
        `EVIDENCE_SOURCE_REQUIRED` means the Agent must confirm Source Specs, Purpose, Core Concept,
        or a resolved non-stale Conflict Review Item before writing a constraint.
        """,
    )
    write(
        project / "docs/spec/conflict.md",
        """
        # Conflict Specification

        ## Feature Gate Required

        source id: feature-gate-required

        FEATURE_GATE must be enabled for login processing.

        ## Feature Gate Forbidden

        source id: feature-gate-forbidden

        FEATURE_GATE must not be enabled for login processing.
        """,
    )
    write(
        project / "tools/remaining-provider.py",
        r"""
        #!/usr/bin/env python3
        from __future__ import annotations

        import json
        import sys
        from pathlib import Path

        mode = sys.argv[1]
        log_path = Path(sys.argv[2])
        payload = json.loads(sys.stdin.read() or "{}")
        stage = payload.get("stage") or payload.get("task")
        section_ids = list((payload.get("section_hashes") or {}).keys())
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"stage": stage, "section_ids": section_ids}, ensure_ascii=False) + "\n")

        if stage == "section_metadata":
            sections = []
            for section_id in section_ids:
                if "session-runtime-contract" in section_id:
                    sections.append({
                        "section_id": section_id,
                        "summary": "Session runtime contract with operator retrieval maintenance.",
                        "search_keys": [
                            "session runtime retrieval",
                            "operator maintenance",
                            "AUTH_TOKEN",
                            "bindContext",
                            "spec-anchor core",
                            "--rebuild",
                            ".spec-anchor/config.toml",
                            "ProductStore",
                            "productStoreGroup.replace",
                            "natural language discovery",
                        ],
                    })
                elif "search-evidence-boundary" in section_id:
                    sections.append({
                        "section_id": section_id,
                        "summary": "Search aids must be confirmed against authoritative evidence before constraints.",
                        "search_keys": ["search aid boundary", "constraint evidence", "source spec confirmation"],
                    })
                elif "feature-gate-required" in section_id:
                    sections.append({
                        "section_id": section_id,
                        "summary": "FEATURE_GATE must be enabled for login processing.",
                        "search_keys": ["feature gate required", "login processing"],
                    })
                elif "feature-gate-forbidden" in section_id:
                    sections.append({
                        "section_id": section_id,
                        "summary": "FEATURE_GATE must not be enabled for login processing.",
                        "search_keys": ["feature gate forbidden", "login processing"],
                    })
                else:
                    sections.append({"section_id": section_id, "summary": f"summary for {section_id}", "search_keys": ["runtime"]})
            print(json.dumps({"sections": sections}, ensure_ascii=False))
        elif stage == "related_section_selection":
            if mode == "pending":
                print(json.dumps({
                    "sections": [{
                        "source_section_id": "docs/spec/conflict.md#0002-feature-gate-required",
                        "related_sections": [{
                            "target_section_id": "docs/spec/conflict.md#0003-feature-gate-forbidden",
                            "relation_hint": "same_policy",
                            "confidence": "high",
                            "reason": "Both sections mention FEATURE_GATE with opposing requirements.",
                            "evidence_terms": ["FEATURE_GATE", "must", "must not"],
                            "channels": ["shared_identifier"],
                            "possible_conflict": True,
                        }],
                    }]
                }, ensure_ascii=False))
            else:
                print(json.dumps({
                    "sections": [{
                        "source_section_id": "docs/spec/runtime.md#0002-session-runtime-contract",
                        "related_sections": [{
                            "target_section_id": "docs/spec/runtime.md#0003-search-evidence-boundary",
                            "relation_hint": "depends_on",
                            "confidence": "high",
                            "reason": "The runtime section points to the evidence boundary.",
                            "evidence_terms": ["EVIDENCE_SOURCE_REQUIRED"],
                            "channels": ["markdown_link", "shared_identifier"],
                        }],
                    }]
                }, ensure_ascii=False))
        elif stage == "conflict_review":
            if mode == "pending":
                print(json.dumps({
                    "outcome": "needs_human_review",
                    "severity": "high",
                    "claims": ["FEATURE_GATE must be enabled.", "FEATURE_GATE must not be enabled."],
                    "why_conflicting": "Both Source Specs are authoritative and cannot both be satisfied.",
                    "why_llm_cannot_decide": "A human must choose which requirement has priority.",
                    "recommended_next_action": "Ask a human to decide this conflict.",
                }, ensure_ascii=False))
            else:
                print(json.dumps({
                    "outcome": "not_conflict",
                    "warning": "Reviewed as non-conflict for the standard project.",
                    "why_not_pending": "The candidate does not require human review in this mode.",
                }, ensure_ascii=False))
        elif stage == "chapter_key_anchor":
            print(json.dumps({
                "summary": "Runtime and conflict chapter",
                "key_topics": ["session runtime", "search evidence", "feature gate"],
                "important_sections": section_ids[:3],
                "notes": ["Search helpers are not evidence."],
            }, ensure_ascii=False))
        else:
            print(json.dumps({"summary": "ok", "search_keys": ["ok"], "sections": []}, ensure_ascii=False))
        """,
    )
    (project / "tools/remaining-provider.py").chmod(0o755)
    configure_project(project, collection=collection, provider_mode=provider_mode)
    write(EVID / f"artifacts/{name}-project-path.txt", f"{project}\n")
    shutil.copy2(project / ".spec-anchor/config.toml", EVID / f"artifacts/{name}-config.toml")
    return project


def stdout_json(label: str) -> dict[str, Any]:
    try:
        return json.loads(read(EVID / f"stdout/{label}.stdout"))
    except json.JSONDecodeError:
        return {}


def find_value(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        if key in payload:
            return payload[key]
        for value in payload.values():
            found = find_value(value, key)
            if found is not None:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = find_value(value, key)
            if found is not None:
                return found
    return None


def qdrant_payloads(project: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from qdrant_client import QdrantClient

    state = json.loads((project / ".spec-anchor/state/retrieval_index_state.json").read_text(encoding="utf-8"))
    collection = state["collection_name"]
    client = QdrantClient(url="http://localhost:6333")
    info = client.get_collection(collection)
    records, _ = client.scroll(collection_name=collection, with_payload=True, limit=100)
    try:
        info_payload = info.model_dump(mode="json")
    except AttributeError:
        info_payload = json.loads(info.json())
    return info_payload, [dict(point.payload or {}) for point in records]


def main() -> int:
    shutil.rmtree(EVID / "stdout", ignore_errors=True)
    shutil.rmtree(EVID / "stderr", ignore_errors=True)
    shutil.rmtree(EVID / "artifacts", ignore_errors=True)
    shutil.rmtree(BASE, ignore_errors=True)
    (EVID / "artifacts").mkdir(parents=True, exist_ok=True)
    (EVID / "commands.log").write_text("", encoding="utf-8")

    write(
        EVID / "artifacts/environment.txt",
        f"""
        run_id={RUN_ID}
        repo={REPO}
        base={BASE}
        date_command={subprocess.run(["date", "-Is"], text=True, capture_output=True).stdout.strip()}
        SPEC_ANCHOR_FAKE_LLM={os.environ.get("SPEC_ANCHOR_FAKE_LLM", "<unset>")}
        SPEC_ANCHOR_FAKE_RETRIEVAL={os.environ.get("SPEC_ANCHOR_FAKE_RETRIEVAL", "<unset>")}
        """,
    )

    standard = prepare_project(
        "standard",
        collection="spec_anchor_sections_20260523_144000_remaining_standard",
        provider_mode="standard",
    )
    pending = prepare_project(
        "pending",
        collection="spec_anchor_sections_20260523_144000_remaining_pending",
        provider_mode="pending",
    )

    purpose_hash_before = sha256(standard / "docs/core/purpose.md")
    concept_hash_before = sha256(standard / "docs/core/concept.md")
    run("standard-core-rebuild", [str(SPEC_ANCHOR), "core", "--rebuild"], cwd=standard, timeout=420)
    purpose_hash_after = sha256(standard / "docs/core/purpose.md")
    concept_hash_after = sha256(standard / "docs/core/concept.md")

    run("standard-help", [str(SPEC_ANCHOR), "--help"], cwd=standard)
    run("standard-core-help", [str(SPEC_ANCHOR), "core", "--help"], cwd=standard)
    run("standard-inject-search", [str(SPEC_ANCHOR), "inject-search", "session", "runtime", "retrieval"], cwd=standard)
    run(
        "standard-inject-section-runtime",
        [str(SPEC_ANCHOR), "inject-section", "docs/spec/runtime.md#0002-session-runtime-contract"],
        cwd=standard,
    )
    run("standard-inject-chapters", [str(SPEC_ANCHOR), "inject-chapters"], cwd=standard)

    run("pending-core-rebuild", [str(SPEC_ANCHOR), "core", "--rebuild"], cwd=pending, timeout=420)
    answer = {
        "今回守る制約": ["FEATURE_GATE の扱いを決める。"],
        "今回扱う修正候補または検討対象": ["ログイン処理"],
        "競合 / 不確実性 / 人間レビューが必要な点": [],
        "課題プロンプトへの回答または修正案": "候補回答",
    }
    write(EVID / "artifacts/answer.json", json.dumps(answer, ensure_ascii=False, indent=2) + "\n")
    run("pending-inject-search", [str(SPEC_ANCHOR), "inject-search", "feature", "gate"], cwd=pending)
    run("pending-realign", [str(SPEC_ANCHOR), "realign", "--answer-file", str(EVID / "artifacts/answer.json")], cwd=pending)

    smoke_env = env_without_fakes()
    run(
        "smoke-setup-system-run-smoke",
        [str(SETUP_SYSTEM), "--check-only", "--run-smoke", "--qdrant-url", "http://localhost:6333"],
        cwd=REPO,
        env=smoke_env,
        timeout=180,
    )

    fake_llm_env = env_without_fakes()
    fake_llm_env["SPEC_ANCHOR_FAKE_LLM"] = "1"
    run(
        "fake-llm-provider-direct",
        [
            str(PYTHON),
            "-c",
            (
                "from spec_anchor.config import load_config;"
                "from spec_anchor.llm_provider import build_spec_core_llm_provider, FakeLlmProvider;"
                "cfg=load_config('.');"
                "provider=build_spec_core_llm_provider(cfg.llm, stage='section_metadata');"
                "print(type(provider).__name__);"
                "raise SystemExit(0 if isinstance(provider, FakeLlmProvider) else 1)"
            ),
        ],
        cwd=standard,
        env=fake_llm_env,
    )

    fake_retrieval_env = env_without_fakes()
    fake_retrieval_env["SPEC_ANCHOR_FAKE_RETRIEVAL"] = "1"
    run(
        "fake-retrieval-direct-block",
        [
            str(PYTHON),
            "-c",
            (
                "from spec_anchor.retrieval_index import FlagEmbeddingBgeM3Provider\n"
                "try:\n"
                "    FlagEmbeddingBgeM3Provider()\n"
                "except RuntimeError as exc:\n"
                "    print(str(exc))\n"
                "    raise SystemExit(0)\n"
                "raise SystemExit(1)"
            ),
        ],
        cwd=standard,
        env=fake_retrieval_env,
        timeout=180,
    )
    run("fake-retrieval-standard-core", [str(SPEC_ANCHOR), "core", "--rebuild"], cwd=standard, env=fake_retrieval_env, timeout=420)

    std_core = stdout_json("standard-core-rebuild")
    pending_core = stdout_json("pending-core-rebuild")
    std_search = stdout_json("standard-inject-search")
    std_section = stdout_json("standard-inject-section-runtime")
    pending_inject = stdout_json("pending-inject-search")
    pending_realign = stdout_json("pending-realign")
    smoke = stdout_json("smoke-setup-system-run-smoke")
    fake_retrieval_core = stdout_json("fake-retrieval-standard-core")
    collection_info, payloads = qdrant_payloads(standard)
    runtime_payload = next(
        (payload for payload in payloads if payload.get("source_section_id") == "docs/spec/runtime.md#0002-session-runtime-contract"),
        {},
    )

    files = sorted(str(path.relative_to(standard)) for path in (standard / ".spec-anchor").rglob("*") if path.is_file())
    write(EVID / "artifacts/standard-spec-anchor-files.txt", "\n".join(files) + "\n")
    write(EVID / "artifacts/standard-qdrant-collection.json", json.dumps(collection_info, ensure_ascii=False, indent=2) + "\n")
    write(EVID / "artifacts/standard-runtime-payload.json", json.dumps(runtime_payload, ensure_ascii=False, indent=2) + "\n")

    bad_search_key_terms = {
        "AUTH_TOKEN",
        "bindContext",
        "spec-anchor core",
        "--rebuild",
        ".spec-anchor/config.toml",
        "ProductStore",
        "productStoreGroup.replace",
    }
    search_keys = set(str(item) for item in runtime_payload.get("search_keys") or [])
    identifiers = set(str(item) for item in runtime_payload.get("identifiers") or [])
    collection_text = json.dumps(collection_info, ensure_ascii=False)
    section_metadata_diag = std_core.get("diagnostics", {}).get("section_metadata", {})
    metadata_not_evidence = (
        section_metadata_diag.get("artifact_role") == "retrieval_aid_not_evidence"
        or find_value(std_core, "summary_search_keys_are_evidence") is False
    )
    identifier_extractor_version = (
        section_metadata_diag.get("generation", {}).get("identifier_extractor_version")
        or find_value(std_core, "identifier_extractor_version")
    )

    prior_agent_trace = read(REPO / "doc/e2eテストCODEX実施用/evidence/20260523-101202-codex-e2e-inject-output/artifacts/codex-skill-inject-8-5.last-message.txt")
    conflict_agent_trace = read(REPO / "doc/e2eテストCODEX実施用/evidence/20260523-142000-codex-e2e-conflict-review-item-trace/artifacts/codex-conflict-trace.last-message.txt")
    path_trace = json.loads(read(REPO / "doc/e2eテストCODEX実施用/evidence/20260523-143000-codex-e2e-path-selection-trace/artifacts/path-selection-trace-assertions.json") or "{}")
    raw_trace = json.loads(read(REPO / "doc/e2eテストCODEX実施用/evidence/20260523-142500-codex-trace-raw-context-boundary/artifacts/raw-context-boundary-assertions.json") or "{}")

    checks: dict[str, Any] = {
        "run_id": RUN_ID,
        "line_48_no_graph_standard_path": {
            "passed": (
                std_core.get("retrieval_index_status") == "success"
                and not any(token in file_name for file_name in files for token in ("property_graph", "entity_relation_graph", "hierarchical_cluster"))
                and "graph" not in read(EVID / "stdout/standard-help.stdout").lower()
            ),
            "evidence": ["stdout/standard-core-rebuild.stdout", "stdout/standard-help.stdout", "artifacts/standard-spec-anchor-files.txt"],
        },
        "line_49_no_concept_auto_update_or_execution_mode_branch": {
            "passed": (
                purpose_hash_before == purpose_hash_after
                and concept_hash_before == concept_hash_after
                and "--mode" not in read(EVID / "stdout/standard-core-help.stdout")
                and "execution_mode" not in read(EVID / "artifacts/standard-config.toml")
            ),
            "purpose_hash_before": purpose_hash_before,
            "purpose_hash_after": purpose_hash_after,
            "concept_hash_before": concept_hash_before,
            "concept_hash_after": concept_hash_after,
            "evidence": ["stdout/standard-core-rebuild.stdout", "stdout/standard-core-help.stdout"],
        },
        "line_50_pending_conflict_blocks_inject_and_realign": {
            "passed": (
                pending_core.get("pending_conflict_count", 0) >= 1
                and pending_inject.get("status") == "blocked"
                and "pending_conflict" in (pending_inject.get("blocking_reasons") or [])
                and pending_realign.get("status") == "blocked"
                and "pending_conflict" in (pending_realign.get("blocking_reasons") or [])
            ),
            "evidence": ["stdout/pending-core-rebuild.stdout", "stdout/pending-inject-search.stdout", "stdout/pending-realign.stdout"],
        },
        "line_62_hybrid_rag_qdrant_dense_sparse_rrf_search": {
            "passed": (
                std_core.get("retrieval_index_status") == "success"
                and "vectors" in collection_text
                and "sparse_vectors" in collection_text
                and bool(std_search.get("hits"))
            ),
            "evidence": ["artifacts/standard-qdrant-collection.json", "stdout/standard-inject-search.stdout"],
        },
        "line_63_lightweight_related_section_payload_lookup": {
            "passed": (
                isinstance(runtime_payload.get("related_sections"), list)
                and any(item.get("target_section_id") == "docs/spec/runtime.md#0003-search-evidence-boundary" for item in runtime_payload.get("related_sections") or [])
                and bool(std_section.get("sections") or std_section.get("section"))
            ),
            "evidence": ["artifacts/standard-runtime-payload.json", "stdout/standard-inject-section-runtime.stdout"],
        },
        "line_67_related_sections_are_payload_field_not_graph_traversal": {
            "passed": (
                isinstance(runtime_payload.get("related_sections"), list)
                and "graph" not in read(EVID / "stdout/standard-help.stdout").lower()
            ),
            "evidence": ["artifacts/standard-runtime-payload.json", "stdout/standard-help.stdout"],
        },
        "line_143_search_keys_are_natural_language_only": {
            "passed": bad_search_key_terms.isdisjoint(search_keys),
            "search_keys": sorted(search_keys),
            "filtered_bad_terms": sorted(bad_search_key_terms & search_keys),
            "evidence": ["artifacts/standard-runtime-payload.json"],
        },
        "line_144_identifiers_are_separated": {
            "passed": bool({"AUTH_TOKEN", "bindContext", "--rebuild", ".spec-anchor/config.toml"} & identifiers) and bad_search_key_terms.isdisjoint(search_keys),
            "identifiers_sample": sorted(identifiers)[:20],
            "evidence": ["artifacts/standard-runtime-payload.json"],
        },
        "line_148_search_keys_not_constraint_evidence": {
            "passed": (
                metadata_not_evidence
                and "evidence_origin: Section Search Keys" not in prior_agent_trace
            ),
            "evidence": [
                "stdout/standard-core-rebuild.stdout",
                "../20260523-101202-codex-e2e-inject-output/artifacts/codex-skill-inject-8-5.last-message.txt",
            ],
        },
        "line_154_identifiers_are_machine_extracted": {
            "passed": bool(identifiers) and identifier_extractor_version == "identifier-extractor-v1",
            "evidence": ["stdout/standard-core-rebuild.stdout", "artifacts/standard-runtime-payload.json"],
        },
        "line_163_identifiers_not_constraint_evidence": {
            "passed": (
                metadata_not_evidence
                and "evidence_origin: Section Identifiers" not in prior_agent_trace
                and "evidence_origin: Conflict Review Item" in conflict_agent_trace
            ),
            "evidence": [
                "stdout/standard-core-rebuild.stdout",
                "../20260523-101202-codex-e2e-inject-output/artifacts/codex-skill-inject-8-5.last-message.txt",
                "../20260523-142000-codex-e2e-conflict-review-item-trace/artifacts/codex-conflict-trace.last-message.txt",
            ],
        },
        "lines_817_822_path1_step_visualization": {
            "passed": (
                bool(path_trace.get("checks", {}).get("api_identifier_uses_path_1"))
                and bool(raw_trace.get("checks", {}).get("inject_search_before_source_reads"))
                and bool(raw_trace.get("checks", {}).get("inject_section_before_source_reads"))
            ),
            "evidence": [
                "../20260523-143000-codex-e2e-path-selection-trace/artifacts/path-selection-trace-assertions.json",
                "../20260523-142500-codex-trace-raw-context-boundary/artifacts/raw-context-boundary-assertions.json",
            ],
        },
        "lines_832_833_path2_step_visualization": {
            "passed": (
                bool(path_trace.get("checks", {}).get("abstract_policy_uses_path_2"))
                and bool(path_trace.get("checks", {}).get("abstract_policy_uses_supplement_1_3_4"))
            ),
            "evidence": ["../20260523-143000-codex-e2e-path-selection-trace/artifacts/path-selection-trace-assertions.json"],
        },
        "line_495_run_smoke_separate_contract": {
            "production_e2e_verified": False,
            "passed_smoke_contract": (
                smoke.get("smoke", {}).get("executed") is True
                and isinstance(smoke.get("agent_cli_entries"), dict)
                and "production_readiness" in smoke
            ),
            "reason": "Agent CLI recognition smoke is an opt-in smoke check and is not counted as production E2E.",
            "evidence": ["stdout/smoke-setup-system-run-smoke.stdout"],
        },
        "line_1226_fake_llm_separate_contract": {
            "production_e2e_verified": False,
            "passed_fake_contract": read(EVID / "stdout/fake-llm-provider-direct.stdout").strip() == "FakeLlmProvider",
            "reason": "SPEC_ANCHOR_FAKE_LLM selects the in-process FakeLlmProvider and is not counted as production E2E.",
            "evidence": ["stdout/fake-llm-provider-direct.stdout"],
        },
        "line_1227_fake_retrieval_separate_contract": {
            "production_e2e_verified": False,
            "passed_fake_contract": (
                "SPEC_ANCHOR_FAKE_RETRIEVAL is set" in read(EVID / "stdout/fake-retrieval-direct-block.stdout")
                and fake_retrieval_core.get("retrieval_index_status") == "success"
            ),
            "reason": "Direct fake retrieval guard and standard /spec-core allowance were checked, but fake env checks are not counted as production E2E.",
            "evidence": ["stdout/fake-retrieval-direct-block.stdout", "stdout/fake-retrieval-standard-core.stdout"],
        },
        "line_1411_run_smoke_agent_cli_warning_separate_contract": {
            "production_e2e_verified": False,
            "passed_smoke_contract": (
                smoke.get("smoke", {}).get("executed") is True
                and "project_skill_path" in json.dumps(smoke.get("agent_cli_entries", {}).get("codex", {}), ensure_ascii=False)
                and "project_command_path" in json.dumps(smoke.get("agent_cli_entries", {}).get("claude", {}), ensure_ascii=False)
            ),
            "reason": "The --run-smoke output includes Agent CLI entrypoint paths and remains a smoke/warning-level contract, not production E2E.",
            "evidence": ["stdout/smoke-setup-system-run-smoke.stdout"],
        },
    }
    production_checks = [value for key, value in checks.items() if key.startswith("line_") or key.startswith("lines_")]
    production_done = [
        value
        for key, value in checks.items()
        if key not in {"run_id"}
        and not key.startswith("line_495")
        and not key.startswith("line_1226")
        and not key.startswith("line_1227")
        and not key.startswith("line_1411")
    ]
    smoke_done = [
        checks["line_495_run_smoke_separate_contract"],
        checks["line_1226_fake_llm_separate_contract"],
        checks["line_1227_fake_retrieval_separate_contract"],
        checks["line_1411_run_smoke_agent_cli_warning_separate_contract"],
    ]
    summary = {
        "run_id": RUN_ID,
        "production_or_agent_trace_checks_passed": all(item.get("passed") for item in production_done),
        "smoke_fake_separate_checks_passed": all(item.get("passed_smoke_contract", item.get("passed_fake_contract")) for item in smoke_done),
        "production_or_agent_trace_check_count": len(production_done),
        "smoke_fake_separate_check_count": len(smoke_done),
        "all_processed": all(item.get("passed") for item in production_done)
        and all(item.get("passed_smoke_contract", item.get("passed_fake_contract")) for item in smoke_done),
    }
    output = {"summary": summary, "checks": checks}
    write(EVID / "artifacts/remaining-23-assertions.json", json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["all_processed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
