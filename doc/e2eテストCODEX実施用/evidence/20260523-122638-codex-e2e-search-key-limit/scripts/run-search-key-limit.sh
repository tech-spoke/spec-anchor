#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-122638-codex-e2e-search-key-limit
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project
COLLECTION=spec_anchor_sections_20260523_122638_search_key_limit

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

この隔離 project は、Search Keys と Identifiers の embedding input 上限を外部入出力で確認する。
DOC
cat > "$PROJECT/docs/core/concept.md" <<'DOC'
# Core Concept

Section Search Keys と Section Identifiers は検索補助であり、embedding input には先頭 8 件までを入れる。
DOC
cat > "$PROJECT/docs/spec/limit.md" <<'DOC'
# Search Limit Specification

## Login Limit

source id: login-limit

ログイン境界では検索補助語を多数生成させ、embedding input の上限を確認する。
AUTH_LIMIT_SYMBOL_01 AUTH_LIMIT_SYMBOL_02 AUTH_LIMIT_SYMBOL_03 AUTH_LIMIT_SYMBOL_04 AUTH_LIMIT_SYMBOL_05 AUTH_LIMIT_SYMBOL_06 AUTH_LIMIT_SYMBOL_07 AUTH_LIMIT_SYMBOL_08 AUTH_LIMIT_SYMBOL_09 AUTH_LIMIT_SYMBOL_10 AUTH_LIMIT_SYMBOL_11 AUTH_LIMIT_SYMBOL_12

## Logout Limit

source id: logout-limit

ログアウト境界では LOGOUT_LIMIT_MARKER を記録する。
DOC

cat > "$PROJECT/tools/search-key-provider.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

payload = json.loads(sys.stdin.read() or "{}")
stage = payload.get("stage") or payload.get("task")
section_ids = list((payload.get("section_hashes") or {}).keys())

if stage == "section_metadata":
    sections = []
    for section_id in section_ids:
        if "login-limit" in section_id:
            search_keys = [f"limit search key {index:02d}" for index in range(1, 13)]
            summary = "login limit summary with many search keys"
        else:
            search_keys = ["logout limit key", "session boundary"]
            summary = f"summary for {section_id}"
        sections.append(
            {
                "section_id": section_id,
                "summary": summary,
                "search_keys": search_keys,
            }
        )
    print(json.dumps({"sections": sections}, ensure_ascii=False))
elif stage == "chapter_key_anchor":
    print(
        json.dumps(
            {
                "summary": "search limit chapter",
                "key_topics": ["search key limit", "identifier limit"],
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
chmod +x "$PROJECT/tools/search-key-provider.py"

python3 - "$PROJECT/.spec-anchor/config.toml" "$COLLECTION" "$PROJECT/tools/search-key-provider.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
collection = sys.argv[2]
provider = sys.argv[3]
text = path.read_text(encoding="utf-8")
for key in ("section_collection", "collection"):
    text = text.replace(f'{key} = "spec_anchor_sections"', f'{key} = "{collection}"')
    text = text.replace(f'{key} = "spec_anchor_section"', f'{key} = "{collection}"')
text = text.replace("llm_batch_max_sections = 8", "llm_batch_max_sections = 8")
text = text.replace(
    '[llm.providers.codex]\ncommand = "codex"',
    f'[llm.providers.search_key_limit]\ncommand = "{provider}"\nmodel = "search-key-provider"\neffort = "low"\ntimeout_sec = 30\nmax_retries = 0\n\n[llm.providers.codex]\ncommand = "codex"',
)
text = text.replace('section_metadata   = "codex"', 'section_metadata   = "search_key_limit"')
text = text.replace('related_sections   = "claude_typing"', 'related_sections   = "search_key_limit"')
text = text.replace('conflict_review    = "claude_judge"', 'conflict_review    = "search_key_limit"')
text = text.replace('chapter_key_anchor = "codex"', 'chapter_key_anchor = "search_key_limit"')
path.write_text(text, encoding="utf-8")
PY

printf '%s\n' "$PROJECT" > "$EVID/artifacts/project-path.txt"
cp "$PROJECT/.spec-anchor/config.toml" "$EVID/artifacts/config.toml"

set +e
(
  cd "$PROJECT"
  spec-anchor core --rebuild
) > "$EVID/stdout/core-rebuild.stdout" 2> "$EVID/stderr/core-rebuild.stderr"
core_exit=$?
set -e
printf '%s\n' "$core_exit" > "$EVID/stdout/core-rebuild.exitcode"

find "$PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files.txt"
python3 "$EVID/scripts/assert-search-key-limit.py"
