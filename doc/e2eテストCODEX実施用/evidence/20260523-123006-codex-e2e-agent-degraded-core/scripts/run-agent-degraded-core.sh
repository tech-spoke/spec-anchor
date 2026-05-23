#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-123006-codex-e2e-agent-degraded-core
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

bash "$EVID/scripts/prepare-agent-degraded-project.sh"
PROJECT=$(cat "$EVID/artifacts/project-path.txt")

PROMPT_CLAUDE='利用者が /spec-core を引数なしで発火した状況として扱ってください。現在の project root だけで spec-anchor core を実行し、CLI stdout JSON の status、failed_sections、warnings、diagnostics.section_metadata_generation、freshness_report を読んで利用者向けに伝達してください。status=degraded の場合、必須 artifact は揃っているため /spec-inject / /spec-realign は継続可能であること、失敗 section を再生成する場合は /spec-core --all を実行できることを伝えてください。自動修正、別 project 探索、setup の自動実行はしないでください。'
PROMPT_CODEX='Use the spec-anchor skill. Treat this as the user triggering /spec-core with no arguments. In the current project root only, run spec-anchor core, read the CLI stdout JSON, and report status, failed_sections, warnings, diagnostics.section_metadata_generation, and freshness_report to the user. If status=degraded, tell the user required artifacts are available so /spec-inject and /spec-realign can continue, and failed sections can be regenerated with /spec-core --all. Do not edit files, do not run setup automatically, and do not search another project.'

printf '%s\n' "$PROMPT_CLAUDE" > "$EVID/artifacts/claude-degraded-prompt.txt"
printf '%s\n' "$PROMPT_CODEX" > "$EVID/artifacts/codex-degraded-prompt.txt"

set +e
(
  cd "$PROJECT"
  printf '%s\n' "/spec-core $PROMPT_CLAUDE" | claude -p --verbose --output-format stream-json --include-partial-messages \
    --permission-mode bypassPermissions \
    --allowedTools 'Read,Grep,Glob,Bash(spec-anchor core*)'
) > "$EVID/stdout/claude-spec-core-degraded.stdout" 2> "$EVID/stderr/claude-spec-core-degraded.stderr"
claude_exit=$?
set -e
printf '%s\n' "$claude_exit" > "$EVID/stdout/claude-spec-core-degraded.exitcode"

bash "$EVID/scripts/prepare-agent-degraded-project.sh"
PROJECT=$(cat "$EVID/artifacts/project-path.txt")

set +e
(
  cd "$PROJECT"
  codex exec --json \
    -o "$EVID/artifacts/codex-spec-core-degraded.last-message.txt" \
    -C "$PROJECT" \
    --skip-git-repo-check \
    --dangerously-bypass-approvals-and-sandbox \
    -s danger-full-access \
    "$PROMPT_CODEX"
) > "$EVID/stdout/codex-spec-core-degraded.stdout.jsonl" 2> "$EVID/stderr/codex-spec-core-degraded.stderr"
codex_exit=$?
set -e
printf '%s\n' "$codex_exit" > "$EVID/stdout/codex-spec-core-degraded.exitcode"

find "$PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files-after-agent.txt"
python3 "$EVID/scripts/assert-agent-degraded-core.py"
