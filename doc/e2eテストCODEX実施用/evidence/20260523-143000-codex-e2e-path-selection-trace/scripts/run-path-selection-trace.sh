#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-143000-codex-e2e-path-selection-trace
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
SOURCE_PROJECT=/tmp/20260523-101202-codex-e2e-inject-output.project
PROJECT=/tmp/${RUN_ID}.project

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

rm -rf "$EVID/stdout" "$EVID/stderr" "$EVID/artifacts"
mkdir -p "$EVID/stdout" "$EVID/stderr" "$EVID/artifacts"
rm -rf "$PROJECT"
cp -a "$SOURCE_PROJECT" "$PROJECT"

{
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'repo=%s\n' "$REPO"
  printf 'source_project=%s\n' "$SOURCE_PROJECT"
  printf 'project=%s\n' "$PROJECT"
  printf 'date=%s\n' "$(date -Is)"
  printf 'SPEC_ANCHOR_FAKE_LLM=%s\n' "${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  printf 'SPEC_ANCHOR_FAKE_RETRIEVAL=%s\n' "${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
} > "$EVID/artifacts/environment.txt"

cat > "$PROJECT/.spec-anchor/context/conflict_review_items.json" <<'JSON'
{
  "schema_version": 1,
  "conflict_review_items": [
    {
      "conflict_id": "conflict-login-audit-human-resolution",
      "status": "resolved",
      "severity": "medium",
      "source_refs": [
        "docs/spec/login.md#0002-admin-login-mfa",
        "docs/spec/audit.md#0002-audit-storage-boundary"
      ],
      "claims": [
        {
          "source_ref": "docs/spec/login.md#0002-admin-login-mfa",
          "claim": "管理者ログインでは MFA 成功まで管理画面セッションを発行しない"
        }
      ],
      "why_conflicting": "監査制約とセッション発行境界の優先順位を人間が判断済み。",
      "why_llm_cannot_decide": "人間判断済みの優先順位を根拠にする必要がある。",
      "decision_options": [
        {"id": "adopt_a", "label": "MFA 境界を優先する"},
        {"id": "adopt_b", "label": "別案を採用する"},
        {"id": "needs_source_update", "label": "Source Specs を更新する"},
        {"id": "dismiss", "label": "閉じる"},
        {"id": "defer", "label": "保留する"},
        {"id": "task_scope_resolution", "label": "今回だけ採用する"}
      ],
      "recommended_next_action": "Use this resolved decision only while non-stale.",
      "valid_scope": "global",
      "reflection_status": "unreflected",
      "stale_resolution": false,
      "base_source_hashes": [
        {"source_ref": "docs/spec/login.md#0002-admin-login-mfa", "hash": "hash-login-mfa-v1"}
      ],
      "resolution": {
        "decision": "adopt_a",
        "reason": "人間は MFA 成功前に管理画面セッションを発行しない制約を優先する判断を採用した。",
        "selected_option": "adopt_a",
        "valid_scope": "global",
        "referenced_source_refs": [
          "docs/spec/login.md#0002-admin-login-mfa",
          "docs/spec/audit.md#0002-audit-storage-boundary"
        ]
      }
    }
  ]
}
JSON

printf '%s\n' "$PROJECT" > "$EVID/artifacts/project-path.txt"

write_prompt() {
  local case_id="$1"
  local task_type="$2"
  local task="$3"
  cat > "$EVID/artifacts/${case_id}.prompt.txt" <<PROMPT
Use the spec-anchor skill in the current project.

Run one /spec-inject style workflow for the following task type:
${task_type}

Task:
${task}

Follow the path selection guidance in the skill for this task type. Do not run /spec-core. Do not run setup.
Do not answer the implementation task. Output only the five §8.5 sections, and keep each section present even when empty.
Do not output raw JSON.
PROMPT
}

write_prompt api_identifier "具体的 API / 識別子" "MFA_REQUIRED_ON_ADMIN_LOGIN と AUDIT_EVENT_REQUIRED を使う管理者ログイン監査制約を準備して。"
write_prompt abstract_policy "全体方針 / 抽象的" "ログイン監査と認証ログ保持の全体方針を整理するための制約を準備して。"
write_prompt purpose_direct "Purpose / Core Concept 直接質問" "このプロジェクトの Purpose と Core Concept から、ログイン監査で守るべき判断軸だけを制約として準備して。"
write_prompt past_decision "過去判断の継続" "過去に人間が解決済みにしたログイン監査 conflict の判断を、今回の制約として継続利用して。"

run_case() {
  local case_id="$1"
  set +e
  (
    cd "$PROJECT"
    codex exec \
      --json \
      --skip-git-repo-check \
      --dangerously-bypass-approvals-and-sandbox \
      -s danger-full-access \
      -o "$EVID/artifacts/${case_id}.last-message.txt" \
      - < "$EVID/artifacts/${case_id}.prompt.txt"
  ) > "$EVID/stdout/${case_id}.stdout.jsonl" 2> "$EVID/stderr/${case_id}.stderr"
  local code=$?
  set -e
  printf '%s\n' "$code" > "$EVID/stdout/${case_id}.exitcode"
}

run_case api_identifier
run_case abstract_policy
run_case purpose_direct
run_case past_decision

set +e
python3 "$EVID/scripts/assert-path-selection-trace.py"
assert_exit=$?
set -e
printf '%s\n' "$assert_exit" > "$EVID/artifacts/assert.exitcode"
exit "$assert_exit"
