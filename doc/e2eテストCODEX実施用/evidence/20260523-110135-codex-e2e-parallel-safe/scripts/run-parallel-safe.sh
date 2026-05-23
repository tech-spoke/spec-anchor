#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-110135-codex-e2e-parallel-safe
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT_BASE=/tmp/${RUN_ID}
COLLECTION_BASE=spec_anchor_sections_20260523_110135_parallel_safe

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

mkdir -p "$EVID/stdout" "$EVID/stderr" "$EVID/artifacts"

{
  echo "run_id=$RUN_ID"
  echo "repo=$REPO"
  echo "project_base=$PROJECT_BASE"
  echo "collection_base=$COLLECTION_BASE"
  echo "date=$(date -Is)"
  echo "SPEC_ANCHOR_FAKE_LLM=${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  echo "SPEC_ANCHOR_FAKE_RETRIEVAL=${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
} > "$EVID/artifacts/environment.txt"

prepare_project() {
  local project="$1"
  local collection="$2"
  rm -rf "$project"
  mkdir -p "$project"
  (
    cd "$project"
    spec-anchor-setup-project --target "$project" --agent both --force
  ) > "$EVID/stdout/setup-$(basename "$project").stdout" 2> "$EVID/stderr/setup-$(basename "$project").stderr"

  mkdir -p "$project/docs/core" "$project/docs/spec"
  cat > "$project/docs/core/purpose.md" <<'DOC'
# Purpose

この隔離 project は、並列 E2E で stage routing fallback、Related Sections debug prompt、embedding input を確認するためのもの。
認証仕様では `AUTH_ALPHA_REQUIRED`、`SESSION_COOKIE_HTTP_ONLY`、`ADMIN_ROLE_REQUIRED` を検索補助語として扱う。
DOC
  cat > "$project/docs/core/concept.md" <<'DOC'
# Core Concept

## Retrieval Aid Boundary

検索補助情報は根拠ではない。Source Specs 本文を根拠にする場合だけ制約として採用できる。
DOC
  cat > "$project/docs/spec/auth.md" <<'DOC'
# Authentication Specification

## Login Boundary

source id: login-boundary

ログイン処理では AUTH_ALPHA_REQUIRED を満たした利用者だけを認証済みにする。
raw-body-sentinel-do-not-embed-login-boundary は本文だけに置かれた検証用文字列であり、検索補助語ではない。
AUTH_SYMBOL_01 AUTH_SYMBOL_02 AUTH_SYMBOL_03 AUTH_SYMBOL_04 AUTH_SYMBOL_05 AUTH_SYMBOL_06 AUTH_SYMBOL_07 AUTH_SYMBOL_08 AUTH_SYMBOL_09 AUTH_SYMBOL_10 AUTH_SYMBOL_11 AUTH_SYMBOL_12

Related: docs/spec/session.md#session-cookie

## Admin Authorization

source id: admin-authorization

管理画面は ADMIN_ROLE_REQUIRED を持つ利用者だけが利用できる。
状態変更操作では `POST_ADMIN_CHANGE` を audit trail に残す。
DOC
  cat > "$project/docs/spec/session.md" <<'DOC'
# Session Specification

## Session Cookie

source id: session-cookie

ログイン成功後の session cookie は SESSION_COOKIE_HTTP_ONLY と Secure を必須とする。
SESSION_ROTATION_AFTER_MFA を満たす場合、MFA 成功後に cookie を再発行する。

Related: docs/spec/auth.md#login-boundary

## Logout Boundary

source id: logout-boundary

logout 時には ACTIVE_SESSION_REVOKED を記録し、以後の protected resource access を拒否する。
DOC

  python3 - "$project/.spec-anchor/config.toml" "$collection" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
collection = sys.argv[2]
text = path.read_text(encoding="utf-8")
for key in ("section_collection", "collection"):
    text = text.replace(f'{key} = "spec_anchor_sections"', f'{key} = "{collection}"')
    text = text.replace(f'{key} = "spec_anchor_section"', f'{key} = "{collection}"')
text = text.replace("llm_batch_concurrency = 4", "llm_batch_concurrency = 1")
path.write_text(text, encoding="utf-8")
PY
}

remove_stage_routing() {
  local config="$1"
  python3 - "$config" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
out = []
skip = False
for line in lines:
    if line.strip() == "[llm.stage_routing]":
        skip = True
        continue
    if skip and line.startswith("[") and line.strip().endswith("]"):
        skip = False
    if not skip:
        out.append(line)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

BASE_PROJECT="$PROJECT_BASE.base.project"
prepare_project "$BASE_PROJECT" "${COLLECTION_BASE}_base"
printf '%s\n' "$BASE_PROJECT" > "$EVID/artifacts/base-project-path.txt"

NODEBUG_PROJECT="$PROJECT_BASE.nodebug.project"
DEBUG_PROJECT="$PROJECT_BASE.debug.project"
OVERRIDE_PROJECT="$PROJECT_BASE.override.project"
FALLBACK_PROJECT="$PROJECT_BASE.fallback.project"
cp -a "$BASE_PROJECT" "$NODEBUG_PROJECT"
cp -a "$BASE_PROJECT" "$DEBUG_PROJECT"
cp -a "$BASE_PROJECT" "$OVERRIDE_PROJECT"
cp -a "$BASE_PROJECT" "$FALLBACK_PROJECT"
python3 - "$NODEBUG_PROJECT/.spec-anchor/config.toml" "$DEBUG_PROJECT/.spec-anchor/config.toml" "$OVERRIDE_PROJECT/.spec-anchor/config.toml" "$FALLBACK_PROJECT/.spec-anchor/config.toml" <<'PY'
from pathlib import Path
import sys

for index, config in enumerate(sys.argv[1:], start=1):
    path = Path(config)
    text = path.read_text(encoding="utf-8")
    text = text.replace("spec_anchor_sections_20260523_110135_parallel_safe_base", f"spec_anchor_sections_20260523_110135_parallel_safe_{index}")
    path.write_text(text, encoding="utf-8")
PY
remove_stage_routing "$FALLBACK_PROJECT/.spec-anchor/config.toml"

set +e
(
  cd "$NODEBUG_PROJECT"
  spec-anchor core --rebuild
) > "$EVID/stdout/nodebug-core.stdout" 2> "$EVID/stderr/nodebug-core.stderr"
nodebug_exit=$?
set -e
printf '%s\n' "$nodebug_exit" > "$EVID/stdout/nodebug-core.exitcode"

set +e
(
  cd "$DEBUG_PROJECT"
  SPEC_ANCHOR_DEBUG_RELATED_PROMPT=1 spec-anchor core --rebuild
) > "$EVID/stdout/debug-default-core.stdout" 2> "$EVID/stderr/debug-default-core.stderr"
debug_exit=$?
set -e
printf '%s\n' "$debug_exit" > "$EVID/stdout/debug-default-core.exitcode"

set +e
(
  cd "$OVERRIDE_PROJECT"
  SPEC_ANCHOR_DEBUG_RELATED_PROMPT=1 \
  SPEC_ANCHOR_DEBUG_RELATED_PROMPT_PATH="$EVID/artifacts/related-prompt-override.jsonl" \
  spec-anchor core --rebuild
) > "$EVID/stdout/debug-override-core.stdout" 2> "$EVID/stderr/debug-override-core.stderr"
override_exit=$?
set -e
printf '%s\n' "$override_exit" > "$EVID/stdout/debug-override-core.exitcode"

set +e
(
  cd "$FALLBACK_PROJECT"
  SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION=1 \
  SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION_PATH="$EVID/artifacts/stage-fallback-provider-invocations.jsonl" \
  spec-anchor core --rebuild
) > "$EVID/stdout/stage-fallback-core.stdout" 2> "$EVID/stderr/stage-fallback-core.stderr"
fallback_exit=$?
set -e
printf '%s\n' "$fallback_exit" > "$EVID/stdout/stage-fallback-core.exitcode"

printf '%s\n' "$NODEBUG_PROJECT" > "$EVID/artifacts/nodebug-project-path.txt"
printf '%s\n' "$DEBUG_PROJECT" > "$EVID/artifacts/debug-project-path.txt"
printf '%s\n' "$OVERRIDE_PROJECT" > "$EVID/artifacts/override-project-path.txt"
printf '%s\n' "$FALLBACK_PROJECT" > "$EVID/artifacts/fallback-project-path.txt"
find "$PROJECT_BASE".*.project -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files.txt"

python3 "$EVID/scripts/assert-parallel-safe.py"
