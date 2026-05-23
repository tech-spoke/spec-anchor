#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-131632-codex-e2e-conflict-review-generation
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
BASE=/tmp/${RUN_ID}.projects

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

mkdir -p "$EVID/stdout" "$EVID/stderr" "$EVID/artifacts"
rm -rf "$BASE"
mkdir -p "$BASE"

{
  echo "run_id=$RUN_ID"
  echo "repo=$REPO"
  echo "base=$BASE"
  echo "date=$(date -Is)"
  echo "SPEC_ANCHOR_FAKE_LLM=${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  echo "SPEC_ANCHOR_FAKE_RETRIEVAL=${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
} > "$EVID/artifacts/environment.txt"

prepare_project() {
  local mode="$1"
  local collection="$2"
  local project="$BASE/$mode"
  local log="$EVID/artifacts/${mode}-provider-invocations.jsonl"

  rm -rf "$project"
  mkdir -p "$project"
  (
    cd "$project"
    spec-anchor-setup-project --target "$project" --agent both --force
  ) > "$EVID/stdout/${mode}-setup.stdout" 2> "$EVID/stderr/${mode}-setup.stderr"

  mkdir -p "$project/docs/core" "$project/docs/spec" "$project/tools"
  cat > "$project/docs/core/purpose.md" <<'DOC'
# Purpose

この隔離 project は Conflict Review 生成の外部入出力契約を確認する。
DOC
  cat > "$project/docs/core/concept.md" <<'DOC'
# Core Concept

矛盾兆候は Related Sections だけで確定せず、Conflict Review Item に委ねる。
DOC
  cat > "$project/docs/spec/conflict.md" <<'DOC'
# Conflict Specification

## Alpha Requirement

source id: alpha-requirement

FEATURE_GATE must be enabled for login processing.
ALPHA_REQUIREMENT_FLAG defines the enabled side.

## Beta Prohibition

source id: beta-prohibition

FEATURE_GATE must not be enabled for logout processing.
BETA_PROHIBITION_FLAG defines the disabled side.

## Gamma Optional

source id: gamma-optional

FEATURE_GATE is optional for audit logging.
GAMMA_OPTIONAL_FLAG defines the optional side.
DOC

  cat > "$project/tools/conflict-provider.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

mode = sys.argv[1]
log_path = Path(sys.argv[2])
payload = json.loads(sys.stdin.read() or "{}")
stage = payload.get("stage") or payload.get("task")
record = {
    "stage": stage,
    "task": payload.get("task"),
    "section_hashes": sorted((payload.get("section_hashes") or {}).keys()),
}
if stage == "conflict_review":
    try:
        record["request"] = json.loads(payload.get("prompt") or "{}")
    except Exception:
        record["request"] = payload.get("prompt")
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

section_ids = list((payload.get("section_hashes") or {}).keys())

if stage == "section_metadata":
    sections = []
    for section_id in section_ids:
        if "alpha-requirement" in section_id:
            summary = "FEATURE_GATE must be enabled for login processing."
            keys = ["FEATURE_GATE", "must enabled login", "alpha requirement"]
        elif "beta-prohibition" in section_id:
            summary = "FEATURE_GATE must not be enabled for logout processing."
            keys = ["FEATURE_GATE", "must not enabled logout", "beta prohibition"]
        elif "gamma-optional" in section_id:
            summary = "FEATURE_GATE is optional for audit logging."
            keys = ["FEATURE_GATE", "optional audit", "gamma optional"]
        else:
            summary = f"summary for {section_id}"
            keys = ["FEATURE_GATE"]
        sections.append({"section_id": section_id, "summary": summary, "search_keys": keys})
    print(json.dumps({"sections": sections}, ensure_ascii=False))
elif stage == "chapter_key_anchor":
    print(
        json.dumps(
            {
                "summary": "conflict chapter",
                "key_topics": ["FEATURE_GATE", "conflict review"],
                "important_sections": section_ids[:3],
                "notes": [],
            },
            ensure_ascii=False,
        )
    )
elif stage == "related_section_selection":
    if mode in {"pending", "warning"}:
        print(
            json.dumps(
                {
                    "sections": [
                        {
                            "source_section_id": "docs/spec/conflict.md#0002-alpha-requirement",
                            "related_sections": [
                                {
                                    "target_section_id": "docs/spec/conflict.md#0003-beta-prohibition",
                                    "relation_hint": "same_policy",
                                    "confidence": "high",
                                    "reason": "Both sections mention FEATURE_GATE and opposing enabled requirements.",
                                    "evidence_terms": ["FEATURE_GATE", "must", "must not"],
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
        print(json.dumps({"sections": []}, ensure_ascii=False))
elif stage == "conflict_review":
    if mode == "warning":
        print(
            json.dumps(
                {
                    "outcome": "not_conflict",
                    "warning": "Conflict candidate was reviewed and retained only as a warning.",
                    "why_not_pending": "The provider judged the two statements as task-separated.",
                },
                ensure_ascii=False,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "outcome": "needs_human_review",
                    "severity": "high",
                    "claims": [
                        "FEATURE_GATE must be enabled.",
                        "FEATURE_GATE must not be enabled.",
                    ],
                    "why_conflicting": "The current Source Specs contain opposing requirements for FEATURE_GATE.",
                    "why_llm_cannot_decide": "Both Source Specs are authoritative and require a human priority decision.",
                    "recommended_next_action": "Ask a human to decide this conflict.",
                },
                ensure_ascii=False,
            )
        )
else:
    print(json.dumps({"summary": "ok", "search_keys": ["ok"], "sections": []}, ensure_ascii=False))
PY
  chmod +x "$project/tools/conflict-provider.py"

  python3 - "$project/.spec-anchor/config.toml" "$collection" "$project/tools/conflict-provider.py" "$mode" "$log" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
collection = sys.argv[2]
provider = sys.argv[3]
mode = sys.argv[4]
log = sys.argv[5]
command = f"{provider} {mode} {log}"
text = path.read_text(encoding="utf-8")
for key in ("section_collection", "collection"):
    text = text.replace(f'{key} = "spec_anchor_sections"', f'{key} = "{collection}"')
    text = text.replace(f'{key} = "spec_anchor_section"', f'{key} = "{collection}"')
text = text.replace(
    '[llm.providers.codex]\ncommand = "codex"',
    f'[llm.providers.conflict_e2e]\ncommand = "{command}"\nmodel = "conflict-provider-{mode}"\neffort = "low"\ntimeout_sec = 30\nmax_retries = 0\n\n[llm.providers.codex]\ncommand = "codex"',
)
text = text.replace('section_metadata   = "codex"', 'section_metadata   = "conflict_e2e"')
text = text.replace('related_sections   = "claude_typing"', 'related_sections   = "conflict_e2e"')
text = text.replace('conflict_review    = "claude_judge"', 'conflict_review    = "conflict_e2e"')
text = text.replace('chapter_key_anchor = "codex"', 'chapter_key_anchor = "conflict_e2e"')
path.write_text(text, encoding="utf-8")
PY

  printf '%s\n' "$project" > "$EVID/artifacts/${mode}-project-path.txt"
  cp "$project/.spec-anchor/config.toml" "$EVID/artifacts/${mode}-config.toml"
}

run_core() {
  local mode="$1"
  local project="$BASE/$mode"
  set +e
  (
    cd "$project"
    spec-anchor core --rebuild
  ) > "$EVID/stdout/${mode}-core-rebuild.stdout" 2> "$EVID/stderr/${mode}-core-rebuild.stderr"
  local code=$?
  set -e
  printf '%s\n' "$code" > "$EVID/stdout/${mode}-core-rebuild.exitcode"
  cp "$project/.spec-anchor/context/conflict_review_items.json" "$EVID/artifacts/${mode}-conflict-review-items.json"
  cp "$project/.spec-anchor/state/core_progress.json" "$EVID/artifacts/${mode}-core-progress.json"
}

prepare_project pending spec_anchor_sections_20260523_131632_conflict_pending
prepare_project warning spec_anchor_sections_20260523_131632_conflict_warning
prepare_project highrisk spec_anchor_sections_20260523_131632_conflict_highrisk

run_core pending
run_core warning
run_core highrisk

python3 "$EVID/scripts/assert-conflict-review-generation.py"
