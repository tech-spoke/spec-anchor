#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-123504-codex-e2e-agent-verify-index
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

bash "$EVID/scripts/prepare-agent-verify-project.sh"
PROJECT=$(cat "$EVID/artifacts/project-path.txt")

PROMPT_CLAUDE='利用者が /spec-core --verify-index を発火した状況として扱ってください。現在の project root だけで spec-anchor core --verify-index を実行し、CLI stdout JSON の status、warnings、retrieval_index_status、diagnostics.retrieval_index、freshness_report を読んで利用者向けに伝達してください。verify 不整合または Source Retrieval Index 失敗の場合は、spec-anchor core --rebuild で section collection を作り直す手順を提案し、前回 collection はこの verify 失敗では drop されていないことを伝えてください。自動修正、別 project 探索、setup の自動実行はしないでください。'
PROMPT_CODEX='Use the spec-anchor skill. Treat this as the user triggering /spec-core --verify-index. In the current project root only, run spec-anchor core --verify-index, read the CLI stdout JSON, and report status, warnings, retrieval_index_status, diagnostics.retrieval_index, and freshness_report to the user. If verification inconsistency or Source Retrieval Index failure is reported, tell the user to run spec-anchor core --rebuild to recreate the section collection, and note that the previous collection was not dropped by this verify failure. Do not edit files, do not run setup automatically, and do not search another project.'

printf '%s\n' "$PROMPT_CLAUDE" > "$EVID/artifacts/claude-verify-prompt.txt"
printf '%s\n' "$PROMPT_CODEX" > "$EVID/artifacts/codex-verify-prompt.txt"

set +e
(
  cd "$PROJECT"
  printf '%s\n' "/spec-core --verify-index $PROMPT_CLAUDE" | claude -p --verbose --output-format stream-json --include-partial-messages \
    --permission-mode bypassPermissions \
    --allowedTools 'Read,Grep,Glob,Bash(spec-anchor core*)'
) > "$EVID/stdout/claude-spec-core-verify.stdout" 2> "$EVID/stderr/claude-spec-core-verify.stderr"
claude_exit=$?
set -e
printf '%s\n' "$claude_exit" > "$EVID/stdout/claude-spec-core-verify.exitcode"

bash "$EVID/scripts/prepare-agent-verify-project.sh"
PROJECT=$(cat "$EVID/artifacts/project-path.txt")

set +e
(
  cd "$PROJECT"
  codex exec --json \
    -o "$EVID/artifacts/codex-spec-core-verify.last-message.txt" \
    -C "$PROJECT" \
    --skip-git-repo-check \
    --dangerously-bypass-approvals-and-sandbox \
    -s danger-full-access \
    "$PROMPT_CODEX"
) > "$EVID/stdout/codex-spec-core-verify.stdout.jsonl" 2> "$EVID/stderr/codex-spec-core-verify.stderr"
codex_exit=$?
set -e
printf '%s\n' "$codex_exit" > "$EVID/stdout/codex-spec-core-verify.exitcode"

find "$PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files-after-agent.txt"
python3 "$EVID/scripts/assert-agent-verify-index.py"
