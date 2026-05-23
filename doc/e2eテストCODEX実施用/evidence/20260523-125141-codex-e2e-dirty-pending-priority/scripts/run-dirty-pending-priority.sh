#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-125141-codex-e2e-dirty-pending-priority
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project
COLLECTION=spec_anchor_sections_20260523_125141_dirty_pending

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

mkdir -p "$EVID/stdout" "$EVID/stderr" "$EVID/artifacts"

{
  echo "run_id=$RUN_ID"
  echo "repo=$REPO"
  echo "project=$PROJECT"
  echo "collection=$COLLECTION"
  echo "date=$(date -Is)"
  echo "SPEC_ANCHOR_FAKE_LLM=${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  echo "SPEC_ANCHOR_FAKE_RETRIEVAL=${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
} > "$EVID/artifacts/environment.txt"

rm -rf "$PROJECT"
mkdir -p "$PROJECT"
(
  cd "$PROJECT"
  spec-anchor-setup-project --target "$PROJECT" --agent both --force
) > "$EVID/stdout/setup.stdout" 2> "$EVID/stderr/setup.stderr"

mkdir -p "$PROJECT/docs/core" "$PROJECT/docs/spec" "$PROJECT/tools"
cat > "$PROJECT/docs/core/purpose.md" <<'DOC'
# Purpose

この隔離 project は、Source Specs 変更と pending Conflict Review Item が同時にある時の freshness gate 優先順位を確認する。
DOC
cat > "$PROJECT/docs/core/concept.md" <<'DOC'
# Core Concept

Source Specs が dirty の場合は、pending conflict の人間判断より先に `/spec-core` で保持物を更新する。
DOC
cat > "$PROJECT/docs/spec/auth.md" <<'DOC'
# Authentication Specification

## Session Policy

source id: session-policy

ログイン後は SESSION_POLICY_ACTIVE を満たす active session を生成する。

## Logout Policy

source id: logout-policy

ログアウト時は SESSION_POLICY_TERMINATED を満たすよう active session を無効化する。
DOC

cat > "$PROJECT/tools/deterministic-provider.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

payload = json.loads(sys.stdin.read() or "{}")
stage = payload.get("stage") or payload.get("task")
section_ids = list((payload.get("section_hashes") or {}).keys())

if stage == "section_metadata":
    print(
        json.dumps(
            {
                "sections": [
                    {
                        "section_id": section_id,
                        "summary": f"summary for {section_id}",
                        "search_keys": ["session policy", "logout policy", "dirty pending priority"],
                    }
                    for section_id in section_ids
                ]
            },
            ensure_ascii=False,
        )
    )
elif stage == "chapter_key_anchor":
    print(
        json.dumps(
            {
                "summary": "authentication chapter",
                "key_topics": ["session", "logout"],
                "important_sections": section_ids[:3],
                "notes": [],
            },
            ensure_ascii=False,
        )
    )
elif stage == "related_section_selection":
    print(
        json.dumps(
            {
                "sections": [
                    {
                        "source_section_id": "docs/spec/auth.md#0002-session-policy",
                        "related_sections": [
                            {
                                "target_section_id": "docs/spec/auth.md#0003-logout-policy",
                                "relation_hint": "conflicts_with",
                                "confidence": "medium",
                                "reason": "Both sections define active session lifecycle.",
                                "evidence_terms": ["SESSION_POLICY_ACTIVE", "SESSION_POLICY_TERMINATED"],
                                "channels": ["shared_identifier"],
                                "possible_conflict": True,
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )
    )
else:
    print(json.dumps({"summary": "ok", "search_keys": ["ok"], "sections": []}, ensure_ascii=False))
PY
chmod +x "$PROJECT/tools/deterministic-provider.py"

python3 - "$PROJECT/.spec-anchor/config.toml" "$COLLECTION" "$PROJECT/tools/deterministic-provider.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
collection = sys.argv[2]
provider = sys.argv[3]
text = path.read_text(encoding="utf-8")
for key in ("section_collection", "collection"):
    text = text.replace(f'{key} = "spec_anchor_sections"', f'{key} = "{collection}"')
    text = text.replace(f'{key} = "spec_anchor_section"', f'{key} = "{collection}"')
text = text.replace(
    '[llm.providers.codex]\ncommand = "codex"',
    f'[llm.providers.deterministic]\ncommand = "{provider}"\nmodel = "deterministic-provider"\neffort = "low"\ntimeout_sec = 30\nmax_retries = 0\n\n[llm.providers.codex]\ncommand = "codex"',
)
text = text.replace('section_metadata   = "codex"', 'section_metadata   = "deterministic"')
text = text.replace('related_sections   = "claude_typing"', 'related_sections   = "deterministic"')
text = text.replace('conflict_review    = "claude_judge"', 'conflict_review    = "deterministic"')
text = text.replace('chapter_key_anchor = "codex"', 'chapter_key_anchor = "deterministic"')
path.write_text(text, encoding="utf-8")
PY

printf '%s\n' "$PROJECT" > "$EVID/artifacts/project-path.txt"
cp "$PROJECT/.spec-anchor/config.toml" "$EVID/artifacts/config.toml"

set +e
(
  cd "$PROJECT"
  spec-anchor core --rebuild
) > "$EVID/stdout/initial-core-rebuild.stdout" 2> "$EVID/stderr/initial-core-rebuild.stderr"
initial_exit=$?
set -e
printf '%s\n' "$initial_exit" > "$EVID/stdout/initial-core-rebuild.exitcode"
cp "$PROJECT/.spec-anchor/state/section_manifest.json" "$EVID/artifacts/section-manifest.before-conflict.json"

python3 - "$PROJECT" <<'PY'
from __future__ import annotations

import json
from pathlib import Path

project = Path(__import__("sys").argv[1])
manifest = json.loads((project / ".spec-anchor/state/section_manifest.json").read_text(encoding="utf-8"))
sections = {section["source_section_id"]: section for section in manifest["sections"]}
item = {
    "conflict_id": "codex-e2e-dirty-pending-priority",
    "status": "pending",
    "severity": "high",
    "source_refs": [
        {
            "source_section_id": "docs/spec/auth.md#0002-session-policy",
            "source_hash": sections["docs/spec/auth.md#0002-session-policy"]["source_hash"],
        },
        {
            "source_section_id": "docs/spec/auth.md#0003-logout-policy",
            "source_hash": sections["docs/spec/auth.md#0003-logout-policy"]["source_hash"],
        },
    ],
    "claims": [
        "Session Policy requires an active session after login.",
        "Logout Policy requires the active session to be invalidated.",
    ],
    "why_conflicting": "The fixture keeps this lifecycle boundary as a human-review conflict.",
    "why_llm_cannot_decide": "Both current Source Specs are authoritative and require a human decision.",
    "related_sections": [
        {
            "source_section_id": "docs/spec/auth.md#0002-session-policy",
            "target_section_id": "docs/spec/auth.md#0003-logout-policy",
            "relation_hint": "conflicts_with",
        }
    ],
    "decision_options": [
        {"id": "prefer_session_policy", "label": "Prefer Session Policy"},
        {"id": "prefer_logout_policy", "label": "Prefer Logout Policy"},
        {"id": "defer", "label": "Defer"},
    ],
    "recommended_next_action": "Ask a human to decide this conflict.",
    "base_source_hashes": [
        {
            "source_ref": "docs/spec/auth.md#0002-session-policy",
            "hash": sections["docs/spec/auth.md#0002-session-policy"]["source_hash"],
        },
        {
            "source_ref": "docs/spec/auth.md#0003-logout-policy",
            "hash": sections["docs/spec/auth.md#0003-logout-policy"]["source_hash"],
        },
    ],
    "valid_scope": "global",
    "created_at": "2026-05-23T00:00:00Z",
    "updated_at": "2026-05-23T00:00:00Z",
}
payload = {"schema_version": 1, "generated_at": "2026-05-23T00:00:00Z", "conflict_review_items": [item]}
path = project / ".spec-anchor/context/conflict_review_items.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
cp "$PROJECT/.spec-anchor/context/conflict_review_items.json" "$EVID/artifacts/injected-pending-conflict.json"

set +e
(
  cd "$PROJECT"
  spec-anchor core
) > "$EVID/stdout/core-with-pending-conflict.stdout" 2> "$EVID/stderr/core-with-pending-conflict.stderr"
pending_core_exit=$?
set -e
printf '%s\n' "$pending_core_exit" > "$EVID/stdout/core-with-pending-conflict.exitcode"

set +e
(
  cd "$PROJECT"
  spec-anchor inject-search "session policy"
) > "$EVID/stdout/inject-pending-only.stdout" 2> "$EVID/stderr/inject-pending-only.stderr"
inject_pending_exit=$?
set -e
printf '%s\n' "$inject_pending_exit" > "$EVID/stdout/inject-pending-only.exitcode"

cat > "$PROJECT/answer.json" <<'JSON'
{
  "今回守る制約": ["Session Policy と Logout Policy の両方を確認する"],
  "今回扱う修正候補または検討対象": ["session lifecycle"],
  "競合 / 不確実性 / 人間レビューが必要な点": ["pending conflict があるため人間判断が必要"],
  "課題プロンプトへの回答または修正案": ["session lifecycle は pending conflict 解決後に確定する"]
}
JSON

cat >> "$PROJECT/docs/spec/auth.md" <<'DOC'

## Audit Policy

source id: audit-policy

AUDIT_POLICY_DIRTY_CHANGE は session lifecycle の監査記録を要求する。
DOC
cp "$PROJECT/docs/spec/auth.md" "$EVID/artifacts/auth-after-dirty.md"

set +e
(
  cd "$PROJECT"
  spec-anchor inject-search "session policy"
) > "$EVID/stdout/inject-dirty-and-pending.stdout" 2> "$EVID/stderr/inject-dirty-and-pending.stderr"
inject_dirty_exit=$?
set -e
printf '%s\n' "$inject_dirty_exit" > "$EVID/stdout/inject-dirty-and-pending.exitcode"

set +e
(
  cd "$PROJECT"
  spec-anchor realign --answer-file answer.json
) > "$EVID/stdout/realign-dirty-and-pending.stdout" 2> "$EVID/stderr/realign-dirty-and-pending.stderr"
realign_dirty_exit=$?
set -e
printf '%s\n' "$realign_dirty_exit" > "$EVID/stdout/realign-dirty-and-pending.exitcode"

set +e
(
  cd "$PROJECT"
  spec-anchor core
) > "$EVID/stdout/core-after-dirty.stdout" 2> "$EVID/stderr/core-after-dirty.stderr"
core_after_dirty_exit=$?
set -e
printf '%s\n' "$core_after_dirty_exit" > "$EVID/stdout/core-after-dirty.exitcode"
cp "$PROJECT/.spec-anchor/state/section_manifest.json" "$EVID/artifacts/section-manifest.after-dirty.json"
cp "$PROJECT/.spec-anchor/context/conflict_review_items.json" "$EVID/artifacts/conflict-review-after-dirty-core.json"

set +e
(
  cd "$PROJECT"
  spec-anchor inject-search "session policy"
) > "$EVID/stdout/inject-after-core-pending-only.stdout" 2> "$EVID/stderr/inject-after-core-pending-only.stderr"
inject_after_core_exit=$?
set -e
printf '%s\n' "$inject_after_core_exit" > "$EVID/stdout/inject-after-core-pending-only.exitcode"

set +e
(
  cd "$PROJECT"
  spec-anchor realign --answer-file answer.json
) > "$EVID/stdout/realign-after-core-pending-only.stdout" 2> "$EVID/stderr/realign-after-core-pending-only.stderr"
realign_after_core_exit=$?
set -e
printf '%s\n' "$realign_after_core_exit" > "$EVID/stdout/realign-after-core-pending-only.exitcode"

find "$PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files.txt"
python3 "$EVID/scripts/assert-dirty-pending-priority.py"
