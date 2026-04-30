"""
spike 04: Claude/Codex CLI subprocess + structured output

実証する Phase 0 項目（doc/TODO.md Phase 0.5 spike 計画 #04）:
- 12: Claude/Codex CLI を subprocess external worker として呼び、
      structured output（--json-schema / --output-schema）で JSON を取得できるか

シナリオ:
  STEP 1: spec-grag 想定の最小 JSON Schema を定義
  STEP 2: Claude CLI: claude --print --bare --no-session-persistence
                       --output-format json --json-schema '{...}'
  STEP 3: Codex CLI: codex exec --output-schema schema.json
                      --skip-git-repo-check
  STEP 4: 出力揺れ（同 prompt × 2 回）の観察

注意:
  - サブスク認証前提（API key 不要）。Claude.ai / ChatGPT サブスクログイン済が前提
  - rate limit / 認証切れの可能性があるため最小プロンプト・最小回数で実行
  - Claude CLI は --bare で hooks/LSP/auto-memory を無効化
  - timeout は 90 秒で設定

usage:
  spike/.venv/bin/python spike/04_cli_subprocess.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

PERSIST_DIR = "./spike_storage/04"


def banner(msg: str) -> None:
    print()
    print("=" * 64)
    print(msg)
    print("=" * 64)


# spec-grag 想定の最小 schema: 章テキストから 1 つの Concept を抽出する想定
SPEC_GRAG_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Entity の名前（snake_case 推奨）"
        },
        "label": {
            "type": "string",
            "enum": ["Concept", "Requirement", "Constraint", "Decision"],
            "description": "spec-grag の Core schema label"
        },
        "description": {
            "type": "string",
            "description": "簡潔な説明（30 字以内）"
        }
    },
    "required": ["name", "label", "description"],
    "additionalProperties": False
}

PROMPT = (
    "次の章テキストから、最も中心的な entity を 1 つだけ抽出せよ。"
    "JSON で {name, label, description} を返せ。\n\n"
    "章テキスト：\n"
    "ユーザー認証は OAuth 2.0 を必須とする。"
    "外部 ID プロバイダ（Google / GitHub）からの ID トークンを検証し、"
    "セッションを発行する。"
)


def run_subprocess(cmd: list[str], stdin_text: str | None, timeout: int = 90) -> dict:
    """subprocess を実行し、stdout / stderr / rc / 経過時間を返す."""
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - t0
        return {
            "rc": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed_sec": elapsed,
            "timeout": False,
        }
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - t0
        return {
            "rc": -1,
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
            "elapsed_sec": elapsed,
            "timeout": True,
        }


def try_parse_json(text: str) -> tuple[bool, dict | str]:
    """text を JSON parse、失敗したら markdown code fence を剥がして再試行."""
    text = text.strip()
    try:
        return True, json.loads(text)
    except json.JSONDecodeError:
        pass
    # ```json ... ``` を剥がす
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)
        try:
            return True, json.loads(body)
        except json.JSONDecodeError:
            pass
    return False, text


# =====================================================================
banner("spike 04: Claude/Codex CLI subprocess + structured output")

if os.path.exists(PERSIST_DIR):
    shutil.rmtree(PERSIST_DIR)
os.makedirs(PERSIST_DIR, exist_ok=True)

schema_path = os.path.join(PERSIST_DIR, "schema.json")
with open(schema_path, "w") as f:
    json.dump(SPEC_GRAG_SCHEMA, f, ensure_ascii=False, indent=2)
print(f"  schema.json written: {schema_path}")

# ---------------------------------------------------------------------
banner("STEP 1: Claude CLI で structured output を取る（--json-schema 経由）")

claude_cmd = [
    "claude",
    "--print",
    "--bare",
    "--no-session-persistence",
    "--output-format", "json",
    "--json-schema", json.dumps(SPEC_GRAG_SCHEMA, ensure_ascii=False),
    "--model", "haiku",  # 速度重視で haiku を使う
    PROMPT,
]
print(f"  cmd[:6]: {claude_cmd[:6]}...")
print(f"  prompt = {PROMPT[:50]!r}")

claude_result_1 = run_subprocess(claude_cmd, stdin_text=None, timeout=90)
print(f"  rc = {claude_result_1['rc']}, elapsed = {claude_result_1['elapsed_sec']:.1f}s")
if claude_result_1["timeout"]:
    print(f"  [TIMEOUT]")
else:
    print(f"  stdout (first 300 chars):")
    print(f"    {claude_result_1['stdout'][:300]!r}")
    if claude_result_1["stderr"]:
        print(f"  stderr (first 200 chars):")
        print(f"    {claude_result_1['stderr'][:200]!r}")

    # JSON parse
    ok, parsed = try_parse_json(claude_result_1["stdout"])
    if ok:
        print(f"  [OK] JSON parse")
        print(f"    parsed type: {type(parsed).__name__}")
        if isinstance(parsed, dict):
            # claude の --output-format json は full response object を返す可能性
            # その中の 'result' が schema 適合な JSON のはず
            keys = list(parsed.keys())[:10]
            print(f"    top-level keys: {keys}")
            if "result" in parsed:
                # result フィールドに schema 適合 JSON が入っている想定
                inner = parsed["result"]
                ok2, inner_json = try_parse_json(inner) if isinstance(inner, str) else (True, inner)
                if ok2 and isinstance(inner_json, dict):
                    print(f"    result.name = {inner_json.get('name')!r}")
                    print(f"    result.label = {inner_json.get('label')!r}")
                    print(f"    result.description = {inner_json.get('description')!r}")
                else:
                    print(f"    result is non-JSON string: {inner[:120]!r}")
    else:
        print(f"  [WARN] JSON parse failed, raw text returned")


# ---------------------------------------------------------------------
banner("STEP 2: Codex CLI で structured output を取る（--output-schema 経由）")

codex_cmd = [
    "codex", "exec",
    "--output-schema", schema_path,
    "--skip-git-repo-check",
    "--json",  # JSONL events
    PROMPT,
]
print(f"  cmd: {codex_cmd[:5]}...")

codex_result_1 = run_subprocess(codex_cmd, stdin_text=None, timeout=90)
print(f"  rc = {codex_result_1['rc']}, elapsed = {codex_result_1['elapsed_sec']:.1f}s")
if codex_result_1["timeout"]:
    print(f"  [TIMEOUT]")
else:
    print(f"  stdout (first 500 chars):")
    print(f"    {codex_result_1['stdout'][:500]!r}")
    if codex_result_1["stderr"]:
        print(f"  stderr (first 200 chars):")
        print(f"    {codex_result_1['stderr'][:200]!r}")

    # JSONL なので 1 行ずつ parse
    if codex_result_1["stdout"]:
        events = []
        for line in codex_result_1["stdout"].strip().split("\n"):
            if not line:
                continue
            ok, parsed = try_parse_json(line)
            if ok:
                events.append(parsed)
        print(f"  parsed events: {len(events)}")
        # last event を見る（最終結果が含まれている想定）
        if events:
            last = events[-1]
            print(f"    last event keys: {list(last.keys())[:10] if isinstance(last, dict) else 'non-dict'}")


# ---------------------------------------------------------------------
banner("STEP 3: Claude CLI を 2 回目呼び（出力揺れ観察）")
claude_result_2 = run_subprocess(claude_cmd, stdin_text=None, timeout=90)
print(f"  2nd run rc = {claude_result_2['rc']}, elapsed = {claude_result_2['elapsed_sec']:.1f}s")
if not claude_result_2["timeout"] and claude_result_1.get("stdout"):
    same_byte = claude_result_1["stdout"] == claude_result_2["stdout"]
    print(f"  byte-identical to 1st run: {same_byte}")
    if not same_byte:
        ok1, p1 = try_parse_json(claude_result_1["stdout"])
        ok2, p2 = try_parse_json(claude_result_2["stdout"])
        if ok1 and ok2 and isinstance(p1, dict) and isinstance(p2, dict):
            r1 = p1.get("result")
            r2 = p2.get("result")
            ok1b, j1 = try_parse_json(r1) if isinstance(r1, str) else (True, r1)
            ok2b, j2 = try_parse_json(r2) if isinstance(r2, str) else (True, r2)
            if ok1b and ok2b and isinstance(j1, dict) and isinstance(j2, dict):
                print(f"  parsed result.name 1st = {j1.get('name')!r}")
                print(f"  parsed result.name 2nd = {j2.get('name')!r}")
                print(f"  same name: {j1.get('name') == j2.get('name')}")


banner("DONE")
