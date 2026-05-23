#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-142000-codex-e2e-conflict-review-item-trace
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

rm -rf "$EVID/stdout" "$EVID/stderr" "$EVID/artifacts"
mkdir -p "$EVID/stdout" "$EVID/stderr" "$EVID/artifacts"
rm -rf "$PROJECT"
mkdir -p "$PROJECT"

{
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'repo=%s\n' "$REPO"
  printf 'project=%s\n' "$PROJECT"
  printf 'date=%s\n' "$(date -Is)"
  printf 'SPEC_ANCHOR_FAKE_LLM=%s\n' "${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  printf 'SPEC_ANCHOR_FAKE_RETRIEVAL=%s\n' "${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
  printf 'codex=%s\n' "$(command -v codex || true)"
  printf 'spec-anchor=%s\n' "$(command -v spec-anchor || true)"
} > "$EVID/artifacts/environment.txt"

(
  cd "$PROJECT"
  spec-anchor-setup-project --target "$PROJECT" --agent both --force
) > "$EVID/stdout/setup.stdout" 2> "$EVID/stderr/setup.stderr"

mkdir -p "$PROJECT/docs/core" "$PROJECT/docs/spec" "$PROJECT/.spec-anchor/context" "$PROJECT/.spec-anchor/state"
cat > "$PROJECT/docs/core/purpose.md" <<'DOC'
# Purpose

過去に人間が判断した Conflict Review Item を、Agent が今回の制約根拠として使えることを確認する。
DOC

cat > "$PROJECT/docs/core/concept.md" <<'DOC'
# Core Concept

## Human Decision Priority

人間が resolved にした Conflict Review Item は、stale でない場合だけ今回の制約根拠にできる。
DOC

cat > "$PROJECT/docs/spec/payment.md" <<'DOC'
# Payment Timeout Spec

## Default Timeout

PAYMENT_TIMEOUT_SECONDS は通常の決済確認 timeout を表す。

## Retry Policy

人間判断済みの conflict がある場合、Agent はその判断を無視して timeout を推測してはならない。
DOC

cat > "$PROJECT/.spec-anchor/state/freshness.json" <<'JSON'
{
  "schema_version": 1,
  "status": "fresh",
  "blocking_reasons": [],
  "warnings": [],
  "pending_conflict_count": 0,
  "stale_resolution_count": 0
}
JSON

cat > "$PROJECT/.spec-anchor/context/conflict_review_items.json" <<'JSON'
{
  "schema_version": 1,
  "conflict_review_items": [
    {
      "conflict_id": "conflict-payment-timeout-human-resolution",
      "status": "resolved",
      "severity": "high",
      "source_refs": [
        "docs/spec/payment.md#0001-payment-timeout-spec",
        "docs/spec/payment.md#0002-default-timeout"
      ],
      "claims": [
        {
          "source_ref": "docs/spec/payment.md#0002-default-timeout",
          "claim": "決済 timeout は人間判断済みの値を使う"
        },
        {
          "source_ref": "docs/spec/payment.md#0003-retry-policy",
          "claim": "Agent は timeout を推測しない"
        }
      ],
      "why_conflicting": "timeout value を Agent が推測する案と、人間判断済み値を使う案が衝突する。",
      "why_llm_cannot_decide": "値の採否は仕様判断であり、人間の決定を根拠にする必要がある。",
      "decision_options": [
        {"id": "adopt_a", "label": "人間判断済み値を採用する"},
        {"id": "adopt_b", "label": "Agent 推測値を採用する"},
        {"id": "needs_source_update", "label": "Source Specs を更新する"},
        {"id": "dismiss", "label": "競合ではないとして閉じる"},
        {"id": "defer", "label": "判断を保留する"},
        {"id": "task_scope_resolution", "label": "今回の課題内だけの判断にする"}
      ],
      "recommended_next_action": "Use this resolved human decision as a constraint only while it is non-stale.",
      "valid_scope": "global",
      "reflection_status": "unreflected",
      "reflected_refs": [],
      "stale_resolution": false,
      "base_source_hashes": [
        {"source_ref": "docs/spec/payment.md#0002-default-timeout", "hash": "hash-default-timeout-v1"}
      ],
      "resolution": {
        "decision": "adopt_a",
        "reason": "人間は PAYMENT_TIMEOUT_SECONDS を 45 秒として扱い、Agent が独自値を推測しない方針を採用した。",
        "selected_option": "adopt_a",
        "valid_scope": "global",
        "referenced_source_refs": [
          "docs/spec/payment.md#0002-default-timeout",
          "docs/spec/payment.md#0003-retry-policy"
        ]
      },
      "created_at": "2026-05-23T14:20:00+09:00",
      "updated_at": "2026-05-23T14:20:00+09:00"
    },
    {
      "conflict_id": "conflict-payment-timeout-stale-resolution",
      "status": "resolved",
      "severity": "medium",
      "source_refs": ["docs/spec/payment.md#0002-default-timeout"],
      "claims": [],
      "why_conflicting": "stale fixture",
      "why_llm_cannot_decide": "stale fixture",
      "decision_options": [
        {"id": "adopt_a", "label": "A"},
        {"id": "adopt_b", "label": "B"},
        {"id": "needs_source_update", "label": "Update"},
        {"id": "dismiss", "label": "Dismiss"},
        {"id": "defer", "label": "Defer"},
        {"id": "task_scope_resolution", "label": "Task scope"}
      ],
      "recommended_next_action": "Do not cite stale resolution.",
      "valid_scope": "global",
      "reflection_status": "unreflected",
      "stale_resolution": true,
      "resolution": {
        "decision": "adopt_b",
        "reason": "stale resolution must be excluded",
        "selected_option": "adopt_b",
        "valid_scope": "global",
        "referenced_source_refs": ["docs/spec/payment.md#0002-default-timeout"]
      }
    }
  ]
}
JSON

printf '%s\n' "$PROJECT" > "$EVID/artifacts/project-path.txt"
cp "$PROJECT/.spec-anchor/context/conflict_review_items.json" "$EVID/artifacts/conflict_review_items.seed.json"
cp "$PROJECT/.spec-anchor/state/freshness.json" "$EVID/artifacts/freshness.seed.json"

set +e
(
  cd "$PROJECT"
  spec-anchor inject-conflicts
) > "$EVID/stdout/preflight-inject-conflicts.stdout" 2> "$EVID/stderr/preflight-inject-conflicts.stderr"
preflight_exit=$?
set -e
printf '%s\n' "$preflight_exit" > "$EVID/stdout/preflight-inject-conflicts.exitcode"

cat > "$EVID/artifacts/codex-prompt.txt" <<'PROMPT'
Use the spec-anchor skill in the current project.

Run the /spec-inject style workflow for this task:

過去に人間が解決済みにした PAYMENT_TIMEOUT_SECONDS の Conflict Review Item を、今回守る制約として注入して。

Do not run /spec-core. Do not run setup. Do not answer the implementation task.
Use spec-anchor inject-conflicts and cite only resolved, non-stale Conflict Review Items returned by that command.

Output only the five §8.5 sections:
今回守る制約
今回見るべき対象
関連先として確認したもの
採用しなかったもの
不確実性 / 人間確認

For each constraint, include statement, evidence_origin, evidence_ref, support_refs, applicability, and uncertainty.
The Conflict Review Item constraint must use evidence_origin: Conflict Review Item and evidence_ref: conflict-payment-timeout-human-resolution if it is returned by inject-conflicts.
Do not output raw JSON.
PROMPT

set +e
(
  cd "$PROJECT"
  codex exec \
    --json \
    --skip-git-repo-check \
    --dangerously-bypass-approvals-and-sandbox \
    -s danger-full-access \
    -o "$EVID/artifacts/codex-conflict-trace.last-message.txt" \
    - < "$EVID/artifacts/codex-prompt.txt"
) > "$EVID/stdout/codex-conflict-trace.stdout.jsonl" 2> "$EVID/stderr/codex-conflict-trace.stderr"
codex_exit=$?
set -e
printf '%s\n' "$codex_exit" > "$EVID/stdout/codex-conflict-trace.exitcode"

set +e
python3 "$EVID/scripts/assert-conflict-review-item-trace.py"
assert_exit=$?
set -e
printf '%s\n' "$assert_exit" > "$EVID/artifacts/assert.exitcode"
exit "$assert_exit"
