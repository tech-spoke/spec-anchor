#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-141500-codex-e2e-no-core-concept-drift-notice
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project
COLLECTION=spec_anchor_sections_20260523_141500_no_concept_drift

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
  printf 'collection=%s\n' "$COLLECTION"
  printf 'date=%s\n' "$(date -Is)"
  printf 'SPEC_ANCHOR_FAKE_LLM=%s\n' "${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  printf 'SPEC_ANCHOR_FAKE_RETRIEVAL=%s\n' "${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
} > "$EVID/artifacts/environment.txt"

(
  cd "$PROJECT"
  spec-anchor-setup-project --target "$PROJECT" --agent both --force
) > "$EVID/stdout/setup.stdout" 2> "$EVID/stderr/setup.stderr"

python3 - "$PROJECT" "$COLLECTION" "$EVID/artifacts/provider-invocations.jsonl" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

project = Path(sys.argv[1])
collection = sys.argv[2]
log_path = Path(sys.argv[3])

(project / "docs/core").mkdir(parents=True, exist_ok=True)
(project / "docs/spec").mkdir(parents=True, exist_ok=True)
(project / "tools").mkdir(parents=True, exist_ok=True)

(project / "docs/core/purpose.md").write_text(
    "# Purpose\n\nCore Concept の乖離通知を標準提供しない契約を確認する。\n",
    encoding="utf-8",
)
(project / "docs/core/concept.md").write_text(
    "# Core Concept\n\n"
    "## Human Owned Principle\n\n"
    "Core Concept は人間が保守する判断軸であり、Source Specs の変化から自動で陳腐化通知を作らない。\n",
    encoding="utf-8",
)
(project / "docs/spec/policy.md").write_text(
    "# Policy Spec\n\n"
    "## Existing Policy\n\n"
    "ALPHA_POLICY は既存処理の通常経路である。\n",
    encoding="utf-8",
)

provider = project / "tools/no-concept-drift-provider.py"
provider.write_text(
    """#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
payload = json.loads(sys.stdin.read() or "{}")
stage = payload.get("stage") or payload.get("task")
section_ids = list((payload.get("section_hashes") or {}).keys())
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"stage": stage, "section_ids": section_ids}, ensure_ascii=False, sort_keys=True) + "\\n")

if stage == "section_metadata":
    print(json.dumps({
        "sections": [
            {
                "section_id": section_id,
                "summary": f"Summary for {section_id}.",
                "search_keys": ["policy", "human-owned concept notice absence", section_id],
                "identifiers": ["ALPHA_POLICY"],
            }
            for section_id in section_ids
        ]
    }, ensure_ascii=False))
elif stage == "chapter_key_anchor":
    print(json.dumps({
        "summary": "Policy chapter for human-owned concept notice absence check.",
        "key_topics": ["policy", "human-owned core concept"],
        "important_sections": section_ids,
        "notes": []
    }, ensure_ascii=False))
elif stage == "related_section_selection":
    print(json.dumps({"sections": []}, ensure_ascii=False))
elif stage == "conflict_review":
    print(json.dumps({
        "outcome": "not_conflict",
        "warning": "No human-review conflict in this fixture.",
        "why_not_pending": "Fixture focuses on absence of Core Concept drift notification."
    }, ensure_ascii=False))
else:
    print(json.dumps({"sections": []}, ensure_ascii=False))
""",
    encoding="utf-8",
)
provider.chmod(0o755)

config_path = project / ".spec-anchor/config.toml"
text = config_path.read_text(encoding="utf-8")
for key in ("section_collection", "collection"):
    text = text.replace(f'{key} = "spec_anchor_sections"', f'{key} = "{collection}"')
    text = text.replace(f'{key} = "spec_anchor_section"', f'{key} = "{collection}"')
command = f"{provider} {log_path}"
text = text.replace(
    '[llm.providers.codex]\ncommand = "codex"',
    f'[llm.providers.no_concept_drift]\ncommand = "{command}"\nmodel = "no-concept-drift-provider"\neffort = "low"\ntimeout_sec = 30\nmax_retries = 0\n\n[llm.providers.codex]\ncommand = "codex"',
)
for old in (
    'section_metadata  = "codex"',
    'section_metadata   = "codex"',
):
    text = text.replace(old, old.split("=")[0] + '= "no_concept_drift"')
for old in (
    'related_sections  = "claude_typing"',
    'related_sections   = "claude_typing"',
    'chapter_key_anchor = "codex"',
    'conflict_review   = "claude_judge"',
    'conflict_review    = "claude_judge"',
):
    text = text.replace(old, old.split("=")[0] + '= "no_concept_drift"')
config_path.write_text(text, encoding="utf-8")
PY

printf '%s\n' "$PROJECT" > "$EVID/artifacts/project-path.txt"
cp "$PROJECT/.spec-anchor/config.toml" "$EVID/artifacts/config.toml"

set +e
(
  cd "$PROJECT"
  spec-anchor core --rebuild
) > "$EVID/stdout/core-initial.stdout" 2> "$EVID/stderr/core-initial.stderr"
initial_exit=$?
set -e
printf '%s\n' "$initial_exit" > "$EVID/stdout/core-initial.exitcode"

cat >> "$PROJECT/docs/spec/policy.md" <<'DOC'

## Source Specs Evolved

BETA_POLICY は Source Specs 側で追加された新しい判断対象である。
この追加は Core Concept を人間が見直す契機になり得るが、SPEC-anchor は Core Concept drift 専用通知を自動生成しない。
DOC

set +e
(
  cd "$PROJECT"
  spec-anchor core
) > "$EVID/stdout/core-after-source-change.stdout" 2> "$EVID/stderr/core-after-source-change.stderr"
second_exit=$?
set -e
printf '%s\n' "$second_exit" > "$EVID/stdout/core-after-source-change.exitcode"

cp "$PROJECT/.spec-anchor/state/freshness.json" "$EVID/artifacts/freshness-after-source-change.json"
cp "$PROJECT/.spec-anchor/state/section_manifest.json" "$EVID/artifacts/section-manifest-after-source-change.json"

set +e
python3 "$EVID/scripts/assert-no-core-concept-drift-notice.py"
assert_exit=$?
set -e
printf '%s\n' "$assert_exit" > "$EVID/artifacts/assert.exitcode"
exit "$assert_exit"
