#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-104149-codex-e2e-agent-core-errors
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
CHAPTER_PROJECT=$(cat "$EVID/artifacts/chapter-project-path.txt")
QDRANT_PROJECT=$(cat "$EVID/artifacts/qdrant-project-path.txt")

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

PROMPT_CHAPTER_JA='利用者が /spec-core --all を発火した状況として扱ってください。現在の project root だけで spec-anchor core --all を実行し、CLI stdout JSON の status、warnings、diagnostics.chapter_anchors、freshness_report を読んで利用者向けに伝達してください。自動修正、別 project 探索、setup の自動実行はしないでください。'
PROMPT_QDRANT_JA='利用者が /spec-core --rebuild を発火した状況として扱ってください。現在の project root だけで spec-anchor core --rebuild を実行し、CLI stdout JSON の status、warnings、diagnostics.related_sections、freshness_report を読んで利用者向けに伝達してください。Qdrant 復旧後に spec-anchor core --rebuild を再実行する手順を示してください。自動修正、別 project 探索、setup の自動実行はしないでください。'
PROMPT_CHAPTER_CODEX='Use the spec-anchor skill. Treat this as the user triggering /spec-core --all. In the current project root only, run spec-anchor core --all, read the CLI stdout JSON, and report status, warnings, diagnostics.chapter_anchors, and freshness_report to the user. Do not edit files, do not run setup automatically, and do not search another project.'
PROMPT_QDRANT_CODEX='Use the spec-anchor skill. Treat this as the user triggering /spec-core --rebuild. In the current project root only, run spec-anchor core --rebuild, read the CLI stdout JSON, and report status, warnings, diagnostics.related_sections, and freshness_report to the user. Tell the user to restore Qdrant connectivity and rerun spec-anchor core --rebuild. Do not edit files, do not run setup automatically, and do not search another project.'

printf '%s\n' "$PROMPT_CHAPTER_JA" > "$EVID/artifacts/claude-chapter-prompt.txt"
printf '%s\n' "$PROMPT_QDRANT_JA" > "$EVID/artifacts/claude-qdrant-prompt.txt"
printf '%s\n' "$PROMPT_CHAPTER_CODEX" > "$EVID/artifacts/codex-chapter-prompt.txt"
printf '%s\n' "$PROMPT_QDRANT_CODEX" > "$EVID/artifacts/codex-qdrant-prompt.txt"

set +e
(
  cd "$CHAPTER_PROJECT"
  printf '%s\n' "/spec-core --all $PROMPT_CHAPTER_JA" | claude -p --verbose --output-format stream-json --include-partial-messages \
    --permission-mode bypassPermissions \
    --allowedTools 'Read,Grep,Glob,Bash(spec-anchor core*)'
) > "$EVID/stdout/claude-spec-core-chapter-failure.stdout" 2> "$EVID/stderr/claude-spec-core-chapter-failure.stderr"
claude_chapter_exit=$?
set -e
printf '%s\n' "$claude_chapter_exit" > "$EVID/stdout/claude-spec-core-chapter-failure.exitcode"

set +e
(
  cd "$CHAPTER_PROJECT"
  codex exec --json \
    -o "$EVID/artifacts/codex-spec-core-chapter-failure.last-message.txt" \
    -C "$CHAPTER_PROJECT" \
    --skip-git-repo-check \
    --dangerously-bypass-approvals-and-sandbox \
    -s danger-full-access \
    "$PROMPT_CHAPTER_CODEX"
) > "$EVID/stdout/codex-spec-core-chapter-failure.stdout.jsonl" 2> "$EVID/stderr/codex-spec-core-chapter-failure.stderr"
codex_chapter_exit=$?
set -e
printf '%s\n' "$codex_chapter_exit" > "$EVID/stdout/codex-spec-core-chapter-failure.exitcode"

set +e
(
  cd "$QDRANT_PROJECT"
  printf '%s\n' "/spec-core --rebuild $PROMPT_QDRANT_JA" | claude -p --verbose --output-format stream-json --include-partial-messages \
    --permission-mode bypassPermissions \
    --allowedTools 'Read,Grep,Glob,Bash(spec-anchor core*)'
) > "$EVID/stdout/claude-spec-core-qdrant-failure.stdout" 2> "$EVID/stderr/claude-spec-core-qdrant-failure.stderr"
claude_qdrant_exit=$?
set -e
printf '%s\n' "$claude_qdrant_exit" > "$EVID/stdout/claude-spec-core-qdrant-failure.exitcode"

set +e
(
  cd "$QDRANT_PROJECT"
  codex exec --json \
    -o "$EVID/artifacts/codex-spec-core-qdrant-failure.last-message.txt" \
    -C "$QDRANT_PROJECT" \
    --skip-git-repo-check \
    --dangerously-bypass-approvals-and-sandbox \
    -s danger-full-access \
    "$PROMPT_QDRANT_CODEX"
) > "$EVID/stdout/codex-spec-core-qdrant-failure.stdout.jsonl" 2> "$EVID/stderr/codex-spec-core-qdrant-failure.stderr"
codex_qdrant_exit=$?
set -e
printf '%s\n' "$codex_qdrant_exit" > "$EVID/stdout/codex-spec-core-qdrant-failure.exitcode"

exit 0
