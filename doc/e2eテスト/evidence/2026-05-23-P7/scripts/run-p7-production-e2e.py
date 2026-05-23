#!/home/kazuki/public_html/spec-anchor/.venv/bin/python
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_ID = "2026-05-23-P7"
P3B_RUN_ID = "2026-05-23-P3b"
SECTION_ID = "docs/spec/runtime.md#0002-product-catalog-runtime"


def find_repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "pyproject.toml").is_file() and (path / "spec_anchor").is_dir():
            return path
    raise RuntimeError("repo root not found")


SCRIPT_PATH = Path(__file__).resolve()
EVIDENCE_DIR = SCRIPT_PATH.parents[1]
REPO_ROOT = find_repo_root(SCRIPT_PATH)
P3B_DIR = REPO_ROOT / "doc/e2eテスト/evidence" / P3B_RUN_ID
ARTIFACTS = EVIDENCE_DIR / "artifacts"
STDOUT = EVIDENCE_DIR / "stdout"
STDERR = EVIDENCE_DIR / "stderr"
COMMANDS_LOG = EVIDENCE_DIR / "commands.log"
EVIDENCE_MAP = EVIDENCE_DIR / "evidence_map.jsonl"
SPEC_ANCHOR = REPO_ROOT / ".venv/bin/spec-anchor"
TMP_ROOT = Path("/tmp/spec-anchor-e2e-2026-05-23-P7")


def ensure_dirs() -> None:
    for path in (ARTIFACTS, STDOUT, STDERR):
        path.mkdir(parents=True, exist_ok=True)
    COMMANDS_LOG.write_text("", encoding="utf-8")
    EVIDENCE_MAP.write_text("", encoding="utf-8")


def env_real() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{REPO_ROOT / '.venv' / 'bin'}:{env.get('PATH', '')}"
    env.pop("SPEC_ANCHOR_FAKE_LLM", None)
    env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    return env


def run(
    name: str,
    args: list[str | Path],
    *,
    cwd: Path,
    timeout: int = 900,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    proc = subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        env=env_real(),
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    duration = time.monotonic() - started
    (STDOUT / f"{name}.stdout").write_text(proc.stdout, encoding="utf-8")
    (STDERR / f"{name}.stderr").write_text(proc.stderr, encoding="utf-8")
    (STDOUT / f"{name}.exitcode").write_text(str(proc.returncode), encoding="utf-8")
    with COMMANDS_LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "name": name,
                    "cwd": str(cwd),
                    "command": [str(arg) for arg in args],
                    "returncode": proc.returncode,
                    "duration_sec": round(duration, 3),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return proc


def parse_json_stdout(name: str) -> dict[str, Any]:
    text = (STDOUT / f"{name}.stdout").read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{name}: stdout is not JSON: {text[:500]!r}") from exc


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def artifact_hashes(project: Path) -> dict[str, str]:
    rels = [
        ".spec-anchor/context/section_manifest.json",
        ".spec-anchor/context/section_metadata.json",
        ".spec-anchor/context/related_sections.json",
        ".spec-anchor/context/chapter_anchors.json",
        ".spec-anchor/context/conflict_review_items.json",
        ".spec-anchor/state/retrieval_index_state.json",
        ".spec-anchor/state/related_sections_state.json",
    ]
    return {
        rel: hashlib.sha256((project / rel).read_bytes()).hexdigest()
        for rel in rels
        if (project / rel).is_file()
    }


def evidence_row(
    *,
    scenario: str,
    line: int,
    checkbox_text: str,
    duration_sec: float,
    evidence: list[str],
) -> None:
    row = {
        "spec_section": "P7",
        "spec_line": line,
        "checkbox_text": checkbox_text,
        "test_id": f"manual:{RUN_ID}:{scenario}",
        "profile": "real-smoke",
        "method": "manual production chain scenario",
        "verification_level": "production_e2e_verified",
        "result": "passed",
        "duration_sec": round(duration_sec, 3),
        "executed_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "evidence": evidence,
    }
    with EVIDENCE_MAP.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def assert_fresh(payload: dict[str, Any], label: str) -> None:
    freshness = payload.get("freshness_report") or payload.get("inject_result", {}).get("freshness_report") or {}
    if freshness.get("status") not in {"fresh", "degraded"}:
        raise AssertionError(f"{label}: freshness must be fresh/degraded, got {freshness}")
    diagnostics = freshness.get("diagnostics") or {}
    retrieval = diagnostics.get("retrieval_index", {})
    related = diagnostics.get("related_sections", {})
    if retrieval.get("status") not in {"success", "skipped_unchanged"}:
        raise AssertionError(f"{label}: retrieval status bad: {retrieval}")
    if related.get("status") not in {"success", "skipped_unchanged"}:
        raise AssertionError(f"{label}: related status bad: {related}")
    if related.get("qdrant_backend_failure") is not None:
        raise AssertionError(f"{label}: qdrant backend failure: {related}")


def assert_headings(text: str, headings: list[str], label: str) -> None:
    missing = [heading for heading in headings if heading not in text]
    if missing:
        raise AssertionError(f"{label}: missing headings {missing}; text={text[:1000]!r}")


def assert_trace_contains(path: Path, needles: list[str], label: str) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{label}: trace missing {missing}")


def run_codex(
    name: str,
    project: Path,
    prompt: str,
    *,
    output_name: str,
    timeout: int = 1200,
) -> subprocess.CompletedProcess[str]:
    output_path = ARTIFACTS / output_name
    (ARTIFACTS / f"{name}.prompt.txt").write_text(prompt, encoding="utf-8")
    proc = run(
        name,
        [
            "codex",
            "exec",
            "--json",
            "-o",
            output_path,
            "-C",
            project,
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "-s",
            "danger-full-access",
            prompt,
        ],
        cwd=project,
        timeout=timeout,
    )
    jsonl_path = STDOUT / f"{name}.stdout"
    jsonl_path.rename(STDOUT / f"{name}.stdout.jsonl")
    return proc


def prepare_failure_project() -> Path:
    failure = TMP_ROOT / "config-missing"
    shutil.rmtree(failure, ignore_errors=True)
    failure.mkdir(parents=True, exist_ok=True)
    skill_src = P3B_PROJECT / ".codex/skills/spec-anchor/SKILL.md"
    skill_dst = failure / ".codex/skills/spec-anchor/SKILL.md"
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_src, skill_dst)
    return failure


def main() -> int:
    ensure_dirs()
    if os.environ.get("SPEC_ANCHOR_FAKE_LLM") or os.environ.get("SPEC_ANCHOR_FAKE_RETRIEVAL"):
        raise AssertionError("fake env vars must be unset for P7")

    global P3B_PROJECT
    P3B_PROJECT = Path((P3B_DIR / "artifacts/project-path.txt").read_text(encoding="utf-8").strip())
    if not P3B_PROJECT.is_dir():
        raise AssertionError(f"P3b project not found: {P3B_PROJECT}")
    (ARTIFACTS / "p3b-project-path.txt").write_text(str(P3B_PROJECT) + "\n", encoding="utf-8")
    before_hashes = artifact_hashes(P3B_PROJECT)
    write_json(ARTIFACTS / "chain-before-hashes.json", before_hashes)

    checks: dict[str, Any] = {"run_id": RUN_ID, "p3b_project": str(P3B_PROJECT), "checks": {}}

    started = time.monotonic()
    proc = run("scenario-1-inject-section", [SPEC_ANCHOR, "inject-section", SECTION_ID], cwd=P3B_PROJECT)
    section_payload = parse_json_stdout("scenario-1-inject-section")
    if proc.returncode != 0:
        raise AssertionError(section_payload)
    section = section_payload.get("sections", {}).get(SECTION_ID)
    required = {"summary", "search_keys", "identifiers", "related_sections", "heading_path"}
    if not isinstance(section, dict) or not required.issubset(section):
        raise AssertionError(f"scenario-1 section payload missing fields: {section}")
    checks["checks"]["scenario_1_inject_section"] = {"passed": True, "section_id": SECTION_ID}
    evidence_row(
        scenario="scenario-1-inject-section",
        line=304,
        checkbox_text="scenario 1: `/spec-inject` inject-section 代表経路",
        duration_sec=time.monotonic() - started,
        evidence=["stdout/scenario-1-inject-section.stdout"],
    )

    started = time.monotonic()
    proc = run("scenario-2-inject-chapters", [SPEC_ANCHOR, "inject-chapters"], cwd=P3B_PROJECT)
    chapters_payload = parse_json_stdout("scenario-2-inject-chapters")
    chapter_path = Path(str(chapters_payload.get("chapter_anchors_path") or ""))
    if proc.returncode != 0 or chapters_payload.get("status") != "success" or not chapter_path.is_absolute() or not chapter_path.is_file():
        raise AssertionError(f"scenario-2 bad chapter payload: {chapters_payload}")
    shutil.copy2(chapter_path, ARTIFACTS / "chapter_anchors.json")
    checks["checks"]["scenario_2_inject_chapters"] = {"passed": True, "chapter_anchors_path": str(chapter_path)}
    evidence_row(
        scenario="scenario-2-inject-chapters",
        line=307,
        checkbox_text="scenario 2: `/spec-inject` inject-chapters 代表経路",
        duration_sec=time.monotonic() - started,
        evidence=["stdout/scenario-2-inject-chapters.stdout", "artifacts/chapter_anchors.json"],
    )

    started = time.monotonic()
    proc = run("scenario-3-inject-purpose", [SPEC_ANCHOR, "inject-purpose"], cwd=P3B_PROJECT)
    purpose_payload = parse_json_stdout("scenario-3-inject-purpose")
    concept_path = Path(str(purpose_payload.get("core_concept_path") or ""))
    if proc.returncode != 0 or not purpose_payload.get("purpose") or not concept_path.is_absolute() or not concept_path.is_file():
        raise AssertionError(f"scenario-3 bad purpose payload: {purpose_payload}")
    checks["checks"]["scenario_3_inject_purpose"] = {"passed": True, "core_concept_path": str(concept_path)}
    evidence_row(
        scenario="scenario-3-inject-purpose",
        line=310,
        checkbox_text="scenario 3: `/spec-inject` inject-purpose 代表経路",
        duration_sec=time.monotonic() - started,
        evidence=["stdout/scenario-3-inject-purpose.stdout"],
    )

    inject_prompt = f"""Use the spec-anchor skill. In the current project, run the /spec-inject style workflow for a task about product catalog and checkout constraints.
You must execute these commands: `spec-anchor inject-section {SECTION_ID}`, `spec-anchor inject-chapters`, read the returned chapter_anchors.json, `spec-anchor inject-purpose`, and read the returned Core Concept path.
Do not answer with implementation code. Output only the five §8.5 sections: 今回守る制約, 今回見るべき対象, 関連先として確認したもの, 採用しなかったもの, 不確実性 / 人間確認.
Do not output raw JSON."""
    proc = run_codex(
        "agent-inject-combined",
        P3B_PROJECT,
        inject_prompt,
        output_name="agent-inject-combined.last-message.txt",
    )
    if proc.returncode != 0:
        raise AssertionError("agent inject codex failed")
    inject_text = (ARTIFACTS / "agent-inject-combined.last-message.txt").read_text(encoding="utf-8")
    assert_headings(
        inject_text,
        ["今回守る制約", "今回見るべき対象", "関連先として確認したもの", "採用しなかったもの", "不確実性 / 人間確認"],
        "agent inject",
    )
    assert_trace_contains(
        STDOUT / "agent-inject-combined.stdout.jsonl",
        ["spec-anchor inject-section", "spec-anchor inject-chapters", "spec-anchor inject-purpose"],
        "agent inject trace",
    )

    answer = {
        "今回守る制約": [
            "ProductStore identifier remains stable across search and checkout.",
            "Checkout consumes validated catalog entries.",
        ],
        "今回扱う修正候補または検討対象": [
            "Catalog update and checkout integration handling.",
        ],
        "競合 / 不確実性 / 人間レビューが必要な点": [
            "No pending conflict in the P3b project.",
        ],
        "課題プロンプトへの回答または修正案": [
            "Keep ProductStore stable and route checkout through validated catalog entries.",
        ],
    }
    answer_path = ARTIFACTS / "realign-answer.json"
    write_json(answer_path, answer)
    started = time.monotonic()
    proc = run("scenario-4-realign", [SPEC_ANCHOR, "realign", "--answer-file", answer_path], cwd=P3B_PROJECT)
    realign_payload = parse_json_stdout("scenario-4-realign")
    if proc.returncode != 0 or realign_payload.get("status") != "fresh":
        raise AssertionError(f"scenario-4 bad realign payload: {realign_payload}")
    realign_answer = realign_payload.get("answer") or {}
    if set(answer) - set(realign_answer):
        raise AssertionError(f"scenario-4 answer missing sections: {realign_answer}")
    assert_fresh(realign_payload, "scenario-4")
    checks["checks"]["scenario_4_realign"] = {"passed": True}
    evidence_row(
        scenario="scenario-4-realign",
        line=313,
        checkbox_text="scenario 4: `/spec-realign` 正常経路",
        duration_sec=time.monotonic() - started,
        evidence=["stdout/scenario-4-realign.stdout", "artifacts/realign-answer.json"],
    )

    realign_prompt = f"""Use the spec-anchor skill. Run the /spec-realign style workflow in the current project.
First use `/spec-inject` style constraints for product catalog and checkout. Then call `spec-anchor realign --answer-file` or `spec-anchor realign --answer-json` with a four-section answer candidate.
Final output must contain only these four §9.3 sections: 今回守る制約, 今回扱う修正候補または検討対象, 競合 / 不確実性 / 人間レビューが必要な点, 課題プロンプトへの回答または修正案.
Do not output raw JSON or implementation code."""
    proc = run_codex(
        "agent-realign",
        P3B_PROJECT,
        realign_prompt,
        output_name="agent-realign.last-message.txt",
    )
    if proc.returncode != 0:
        raise AssertionError("agent realign codex failed")
    realign_text = (ARTIFACTS / "agent-realign.last-message.txt").read_text(encoding="utf-8")
    assert_headings(
        realign_text,
        ["今回守る制約", "今回扱う修正候補または検討対象", "競合 / 不確実性 / 人間レビューが必要な点", "課題プロンプトへの回答または修正案"],
        "agent realign",
    )
    assert_trace_contains(STDOUT / "agent-realign.stdout.jsonl", ["spec-anchor realign"], "agent realign trace")

    after_hashes = artifact_hashes(P3B_PROJECT)
    write_json(ARTIFACTS / "chain-after-hashes.json", after_hashes)
    if before_hashes != after_hashes:
        raise AssertionError(f"chain artifacts changed: before={before_hashes} after={after_hashes}")
    checks["checks"]["scenario_5_chain_consistency"] = {"passed": True, "artifact_hashes": after_hashes}
    evidence_row(
        scenario="scenario-5-chain-consistency",
        line=316,
        checkbox_text="scenario 5: chain consistency",
        duration_sec=0.0,
        evidence=[
            "artifacts/chain-before-hashes.json",
            "artifacts/chain-after-hashes.json",
            "stdout/scenario-1-inject-section.stdout",
            "stdout/scenario-2-inject-chapters.stdout",
            "stdout/scenario-3-inject-purpose.stdout",
            "stdout/scenario-4-realign.stdout",
        ],
    )

    failure_project = prepare_failure_project()
    started = time.monotonic()
    proc = run("scenario-6-direct-config-missing", [SPEC_ANCHOR, "inject-purpose"], cwd=failure_project)
    failure_payload = parse_json_stdout("scenario-6-direct-config-missing")
    if failure_payload.get("status") != "error" or not failure_payload.get("should_stop"):
        raise AssertionError(f"scenario-6 direct failure payload bad: {failure_payload}")
    failure_prompt = """Use the spec-anchor skill in this current project. Run `/spec-inject` style workflow by executing `spec-anchor inject-purpose`.
Do not run setup. When the CLI stops, present the stop to the user using the §11.2 stop structure, including the recommended next action from the CLI.
Do not output raw JSON."""
    proc = run_codex(
        "agent-failure-config-missing",
        failure_project,
        failure_prompt,
        output_name="agent-failure-config-missing.last-message.txt",
        timeout=900,
    )
    if proc.returncode != 0:
        raise AssertionError("agent failure codex failed")
    failure_text = (ARTIFACTS / "agent-failure-config-missing.last-message.txt").read_text(encoding="utf-8")
    if "spec-anchor-setup-project" not in failure_text:
        raise AssertionError(f"scenario-6 agent output missing setup action: {failure_text}")
    assert_trace_contains(
        STDOUT / "agent-failure-config-missing.stdout.jsonl",
        ["spec-anchor inject-purpose"],
        "agent failure trace",
    )
    checks["checks"]["scenario_6_failure"] = {"passed": True, "failure_status": failure_payload.get("status")}
    evidence_row(
        scenario="scenario-6-failure",
        line=319,
        checkbox_text="scenario 6: 失敗系 1 経路",
        duration_sec=time.monotonic() - started,
        evidence=[
            "stdout/scenario-6-direct-config-missing.stdout",
            "stdout/agent-failure-config-missing.stdout.jsonl",
            "artifacts/agent-failure-config-missing.last-message.txt",
        ],
    )

    rows = [json.loads(line) for line in EVIDENCE_MAP.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 6 or any(row.get("verification_level") != "production_e2e_verified" or row.get("result") != "passed" for row in rows):
        raise AssertionError(f"unexpected evidence_map rows: {rows}")
    checks["summary"] = {
        "run_id": RUN_ID,
        "scenario_count": len(rows),
        "all_passed": True,
        "verification_level": "production_e2e_verified",
        "fake_env_unset": True,
        "evidence_map": "evidence_map.jsonl",
    }
    write_json(ARTIFACTS / "assertions.json", checks)
    print(json.dumps(checks["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
