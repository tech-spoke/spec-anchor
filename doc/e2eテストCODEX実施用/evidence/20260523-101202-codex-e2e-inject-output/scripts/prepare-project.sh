#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-101202-codex-e2e-inject-output
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project

rm -rf "$PROJECT"
mkdir -p "$PROJECT" "$EVID/stdout" "$EVID/stderr" "$EVID/artifacts"

{
  echo "run_id=$RUN_ID"
  echo "repo=$REPO"
  echo "project=$PROJECT"
  echo "date=$(date -Is)"
  echo "SPEC_ANCHOR_FAKE_LLM=${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  echo "SPEC_ANCHOR_FAKE_RETRIEVAL=${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
} > "$EVID/artifacts/environment.txt"
printf '%s\n' "$PROJECT" > "$EVID/artifacts/project-path.txt"
printf '%s\n' "$RUN_ID" > "$EVID/artifacts/run-id.txt"

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

set +e
(
  cd "$PROJECT"
  spec-anchor-setup-project --target "$PROJECT" --agent both --force
) > "$EVID/stdout/setup-project.stdout" 2> "$EVID/stderr/setup-project.stderr"
setup_exit=$?
set -e
printf '%s\n' "$setup_exit" > "$EVID/stdout/setup-project.exitcode"
if [ "$setup_exit" -ne 0 ]; then
  exit "$setup_exit"
fi

rm -rf "$PROJECT/.claude/commands" "$PROJECT/.codex/skills/spec-anchor"
mkdir -p "$PROJECT/.claude/commands" "$PROJECT/.codex/skills/spec-anchor"
cp "$REPO/.claude/commands/spec-core.md" "$PROJECT/.claude/commands/spec-core.md"
cp "$REPO/.claude/commands/spec-inject.md" "$PROJECT/.claude/commands/spec-inject.md"
cp "$REPO/.claude/commands/spec-realign.md" "$PROJECT/.claude/commands/spec-realign.md"
cp "$REPO/.codex/skills/spec-anchor/SKILL.md" "$PROJECT/.codex/skills/spec-anchor/SKILL.md"

mkdir -p "$PROJECT/docs/core" "$PROJECT/docs/spec"

cat > "$PROJECT/docs/core/purpose.md" <<'DOC'
# Purpose

このテストプロジェクトは、ログイン監査フローの仕様制約を Agent が §8.5 の通常出力として利用者へ注入できることを確認するためのもの。

ログイン監査では、MFA_REQUIRED_ON_ADMIN_LOGIN を最優先の目的制約として扱う。
ユーザー向け回答や実装コードではなく、今回守る制約と根拠だけを提示する。
DOC

cat > "$PROJECT/docs/core/concept.md" <<'DOC'
# Core Concept

## Audit First

管理者ログインは audit-first の対象である。Agent はログイン監査に関する検討では、監査証跡と人間確認が必要な点を明示する。

## Data Boundary

認証ログの保持期間や保管先が未確定の場合は、推測で決めず、不確実性として提示する。
DOC

cat > "$PROJECT/docs/spec/login.md" <<'DOC'
# Login Audit Specification

## Admin Login MFA

source id: login-audit-admin-mfa

管理者ログインでは MFA_REQUIRED_ON_ADMIN_LOGIN を必須とする。
MFA チャレンジはパスワード認証の直後に実行し、成功するまで管理画面セッションを発行してはならない。

Related: docs/spec/audit.md#audit-event-required

## Audit Event Required

source id: login-audit-event-required

管理者ログインの成功時と失敗時には AUDIT_EVENT_REQUIRED を記録する。
記録する項目は actor_id、source_ip、result、mfa_result、occurred_at である。
保持期間 RETENTION_DAYS_FOR_AUTH_LOG は未確定であり、人間確認が必要である。

Related: docs/spec/audit.md#audit-storage-boundary

## Password Reset Out Of Scope

source id: password-reset-out-of-scope

パスワードリセットでは EMAIL_TOKEN_RESET_FLOW を使用する。
この section はログイン監査 task の検索候補にはなり得るが、管理者ログイン MFA の制約としては採用しない。
DOC

cat > "$PROJECT/docs/spec/audit.md" <<'DOC'
# Audit Storage Specification

## Audit Storage Boundary

source id: audit-storage-boundary

AUDIT_EVENT_REQUIRED の保存先は audit_log_stream である。
ただし RETENTION_DAYS_FOR_AUTH_LOG は法務確認待ちであり、Agent は日数を決めてはならない。

## Marketing Tracking Irrelevant

source id: marketing-tracking-irrelevant

MARKETING_PIXEL_LOGIN_PAGE はマーケティング分析用であり、管理者ログインの認証制約や監査制約には採用しない。
DOC

python3 - "$PROJECT/.spec-anchor/config.toml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace('section_collection = "spec_anchor_sections"', 'section_collection = "spec_anchor_sections_20260523_101202_inject_output"')
text = text.replace('section_collection = "spec_anchor_section"', 'section_collection = "spec_anchor_sections_20260523_101202_inject_output"')
text = text.replace('collection = "spec_anchor_sections"', 'collection = "spec_anchor_sections_20260523_101202_inject_output"')
text = text.replace('collection = "spec_anchor_section"', 'collection = "spec_anchor_sections_20260523_101202_inject_output"')
path.write_text(text, encoding="utf-8")
PY

find "$PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files-before-core.txt"

set +e
(
  cd "$PROJECT"
  spec-anchor core --rebuild
) > "$EVID/stdout/core-rebuild.stdout" 2> "$EVID/stderr/core-rebuild.stderr"
core_exit=$?
set -e
printf '%s\n' "$core_exit" > "$EVID/stdout/core-rebuild.exitcode"

find "$PROJECT/.spec-anchor" -maxdepth 4 -type f | sort > "$EVID/artifacts/spec-anchor-files-after-core.txt"
exit "$core_exit"
