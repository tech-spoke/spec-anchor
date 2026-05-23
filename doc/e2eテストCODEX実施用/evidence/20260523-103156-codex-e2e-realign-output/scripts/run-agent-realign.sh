#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-103156-codex-e2e-realign-output
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=$(cat "$EVID/artifacts/project-path.txt")

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

PROMPT_JA='管理者ログイン監査の修正案を /spec-realign で作成して。私の初期案には「RETENTION_DAYS_FOR_AUTH_LOG を 30 日固定にする」が含まれるが、仕様と矛盾するなら隠さず「競合 / 不確実性 / 人間レビューが必要な点」に明示すること。最終出力は §9.3 の 4 区分「今回守る制約」「今回扱う修正候補または検討対象」「競合 / 不確実性 / 人間レビューが必要な点」「課題プロンプトへの回答または修正案」だけにする。raw JSON と実装コードは出さない。'
PROMPT_CODEX='Use the spec-anchor skill. Run the /spec-realign style workflow in the current project for this task: 管理者ログイン監査の修正案を作成して。The user draft says RETENTION_DAYS_FOR_AUTH_LOG should be fixed to 30 days; if that conflicts with the specs, explicitly put it in 競合 / 不確実性 / 人間レビューが必要な点. Final output must contain only the four §9.3 sections: 今回守る制約, 今回扱う修正候補または検討対象, 競合 / 不確実性 / 人間レビューが必要な点, 課題プロンプトへの回答または修正案. Do not output raw JSON or implementation code.'

printf '%s\n' "$PROMPT_JA" > "$EVID/artifacts/claude-prompt.txt"
printf '%s\n' "$PROMPT_CODEX" > "$EVID/artifacts/codex-prompt.txt"

cat > "$EVID/artifacts/preflight-answer.json" <<'JSON'
{
  "constraints": [
    "管理者ログインでは MFA_REQUIRED_ON_ADMIN_LOGIN を必須とする",
    "管理者ログインの成功時と失敗時に AUDIT_EVENT_REQUIRED を記録する",
    "RETENTION_DAYS_FOR_AUTH_LOG は未確定であり人間確認が必要"
  ],
  "candidate": "管理者ログイン監査を実装する。MFA 成功後に管理画面セッションを発行し、成功時と失敗時に audit_log_stream へ AUDIT_EVENT_REQUIRED を記録する。初期案では RETENTION_DAYS_FOR_AUTH_LOG を 30 日固定にする。",
  "risks": [
    "RETENTION_DAYS_FOR_AUTH_LOG を 30 日固定にする案は仕様上の未確定事項と衝突する可能性がある"
  ]
}
JSON

set +e
(
  cd "$PROJECT"
  spec-anchor inject-search "管理者ログイン 監査 MFA RETENTION_DAYS_FOR_AUTH_LOG"
) > "$EVID/stdout/preflight-inject-search.stdout" 2> "$EVID/stderr/preflight-inject-search.stderr"
preflight_inject_exit=$?
set -e
printf '%s\n' "$preflight_inject_exit" > "$EVID/stdout/preflight-inject-search.exitcode"

set +e
(
  cd "$PROJECT"
  spec-anchor realign --answer-file "$EVID/artifacts/preflight-answer.json"
) > "$EVID/stdout/preflight-realign-answer.stdout" 2> "$EVID/stderr/preflight-realign-answer.stderr"
preflight_realign_exit=$?
set -e
printf '%s\n' "$preflight_realign_exit" > "$EVID/stdout/preflight-realign-answer.exitcode"

set +e
(
  cd "$PROJECT"
  printf '%s\n' "/spec-realign $PROMPT_JA" | claude -p --verbose --output-format stream-json --include-partial-messages \
    --permission-mode bypassPermissions \
    --allowedTools 'Read,Grep,Glob,Bash(spec-anchor inject*),Bash(spec-anchor realign*)'
) > "$EVID/stdout/claude-spec-realign-9-3.stdout" 2> "$EVID/stderr/claude-spec-realign-9-3.stderr"
claude_exit=$?
set -e
printf '%s\n' "$claude_exit" > "$EVID/stdout/claude-spec-realign-9-3.exitcode"

set +e
(
  cd "$PROJECT"
  codex exec --json \
    -o "$EVID/artifacts/codex-skill-realign-9-3.last-message.txt" \
    -C "$PROJECT" \
    --skip-git-repo-check \
    --dangerously-bypass-approvals-and-sandbox \
    -s danger-full-access \
    "$PROMPT_CODEX"
) > "$EVID/stdout/codex-skill-realign-9-3.stdout.jsonl" 2> "$EVID/stderr/codex-skill-realign-9-3.stderr"
codex_exit=$?
set -e
printf '%s\n' "$codex_exit" > "$EVID/stdout/codex-skill-realign-9-3.exitcode"

exit 0
