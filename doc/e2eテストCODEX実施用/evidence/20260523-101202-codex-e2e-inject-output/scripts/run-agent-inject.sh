#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-101202-codex-e2e-inject-output
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=$(cat "$EVID/artifacts/project-path.txt")

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

PROMPT_JA='管理者ログイン監査の制約を準備して。課題への最終回答、実装案、コードは出さない。§8.5 の通常出力として「今回守る制約」「今回見るべき対象」「関連先として確認したもの」「採用しなかったもの」「不確実性 / 人間確認」の5セクションだけを出す。今回守る制約の各 item では statement、evidence_origin、evidence_ref、support_refs、applicability、uncertainty を人間が読める形で示す。raw JSON は出さない。'
PROMPT_CODEX='Use the spec-anchor skill. Run the /spec-inject style workflow for this task in the current project: 管理者ログイン監査の制約を準備して。Do not answer the task, do not propose implementation, and do not output code. Produce only the five §8.5 sections: 今回守る制約, 今回見るべき対象, 関連先として確認したもの, 採用しなかったもの, 不確実性 / 人間確認. For each 今回守る制約 item, show statement, evidence_origin, evidence_ref, support_refs, applicability, and uncertainty in a human-readable form. Do not output raw JSON.'

printf '%s\n' "$PROMPT_JA" > "$EVID/artifacts/claude-prompt.txt"
printf '%s\n' "$PROMPT_CODEX" > "$EVID/artifacts/codex-prompt.txt"

set +e
(
  cd "$PROJECT"
  spec-anchor inject-search "管理者ログイン 監査 MFA AUDIT_EVENT_REQUIRED"
) > "$EVID/stdout/preflight-inject-search.stdout" 2> "$EVID/stderr/preflight-inject-search.stderr"
preflight_exit=$?
set -e
printf '%s\n' "$preflight_exit" > "$EVID/stdout/preflight-inject-search.exitcode"

set +e
(
  cd "$PROJECT"
  claude -p --verbose --output-format stream-json --include-partial-messages \
    --permission-mode bypassPermissions \
    --allowedTools 'Read,Grep,Glob,Bash(spec-anchor inject*),Bash(spec-anchor realign*)' \
    "/spec-inject $PROMPT_JA"
) > "$EVID/stdout/claude-spec-inject-8-5.stdout" 2> "$EVID/stderr/claude-spec-inject-8-5.stderr"
claude_exit=$?
set -e
printf '%s\n' "$claude_exit" > "$EVID/stdout/claude-spec-inject-8-5.exitcode"

set +e
(
  cd "$PROJECT"
  codex exec --json \
    -o "$EVID/artifacts/codex-skill-inject-8-5.last-message.txt" \
    -C "$PROJECT" \
    --skip-git-repo-check \
    --dangerously-bypass-approvals-and-sandbox \
    -s danger-full-access \
    "$PROMPT_CODEX"
) > "$EVID/stdout/codex-skill-inject-8-5.stdout.jsonl" 2> "$EVID/stderr/codex-skill-inject-8-5.stderr"
codex_exit=$?
set -e
printf '%s\n' "$codex_exit" > "$EVID/stdout/codex-skill-inject-8-5.exitcode"

exit 0
