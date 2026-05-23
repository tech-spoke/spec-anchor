#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-130037-codex-e2e-inject-all-gates
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project
COLLECTION=spec_anchor_sections_20260523_130037_inject_gates

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

この隔離 project は、各 inject-* command が内部 gate で停止することを確認する。
DOC
cat > "$PROJECT/docs/core/concept.md" <<'DOC'
# Core Concept

Source Specs が dirty の場合、inject-* command は個別操作に入る前に停止する。
DOC
cat > "$PROJECT/docs/spec/auth.md" <<'DOC'
# Authentication Specification

## Session Policy

source id: session-policy

SESSION_POLICY_ACTIVE は login 後の session 境界を定義する。

## Logout Policy

source id: logout-policy

SESSION_POLICY_TERMINATED は logout 後の session 境界を定義する。
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
                        "search_keys": ["session policy", "logout policy", "inject gate"],
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
    print(json.dumps({"sections": []}, ensure_ascii=False))
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

cat >> "$PROJECT/docs/spec/auth.md" <<'DOC'

## Dirty Gate Addition

source id: dirty-gate-addition

DIRTY_GATE_ADDITION は各 inject command が内部 gate で止まることを確認するための変更である。
DOC
cp "$PROJECT/docs/spec/auth.md" "$EVID/artifacts/auth-after-dirty.md"

run_case() {
  local label="$1"
  shift
  set +e
  (
    cd "$PROJECT"
    "$@"
  ) > "$EVID/stdout/${label}.stdout" 2> "$EVID/stderr/${label}.stderr"
  local code=$?
  set -e
  printf '%s\n' "$code" > "$EVID/stdout/${label}.exitcode"
}

run_case inject-search spec-anchor inject-search "session policy"
run_case inject-section spec-anchor inject-section "docs/spec/auth.md#0002-session-policy"
run_case inject-chapters spec-anchor inject-chapters
run_case inject-purpose spec-anchor inject-purpose
run_case inject-conflicts spec-anchor inject-conflicts

find "$PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files.txt"
python3 "$EVID/scripts/assert-inject-all-gates.py"
