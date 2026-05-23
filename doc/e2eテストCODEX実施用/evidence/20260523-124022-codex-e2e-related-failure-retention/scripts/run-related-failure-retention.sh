#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-124022-codex-e2e-related-failure-retention
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project
COLLECTION=spec_anchor_sections_20260523_124022_related_failure

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

この隔離 project は、Related Sections backend failure 時の前回値保持と下流停止を確認する。
DOC
cat > "$PROJECT/docs/core/concept.md" <<'DOC'
# Core Concept

Related Sections の canonical 更新に失敗した場合、前回の関連先を保持し、freshness gate で下流を停止する。
DOC
cat > "$PROJECT/docs/spec/flow.md" <<'DOC'
# Flow Specification

## Login Boundary

source id: login-boundary

LOGIN_BOUNDARY は SESSION_BOUNDARY に依存する。
See [Session Boundary](docs/spec/flow.md#0003-session-boundary).

## Session Boundary

source id: session-boundary

SESSION_BOUNDARY は active session の範囲を定義する。
DOC

cat > "$PROJECT/tools/related-provider.py" <<'PY'
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
                        "search_keys": ["login boundary", "session boundary"],
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
                "summary": "flow chapter",
                "key_topics": ["login", "session"],
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
                        "source_section_id": "docs/spec/flow.md#0002-login-boundary",
                        "related_sections": [
                            {
                                "target_section_id": "docs/spec/flow.md#0003-session-boundary",
                                "relation_hint": "depends_on",
                                "confidence": "high",
                                "reason": "Login Boundary explicitly links to Session Boundary.",
                                "evidence_terms": ["SESSION_BOUNDARY"],
                                "channels": ["markdown_link"],
                                "possible_conflict": False,
                            }
                        ],
                    },
                    {
                        "source_section_id": "docs/spec/flow.md#0003-session-boundary",
                        "related_sections": [
                            {
                                "target_section_id": "docs/spec/flow.md#0002-login-boundary",
                                "relation_hint": "see_also",
                                "confidence": "medium",
                                "reason": "Session Boundary is referenced by Login Boundary.",
                                "evidence_terms": ["LOGIN_BOUNDARY"],
                                "channels": ["shared_identifier"],
                                "possible_conflict": False,
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        )
    )
else:
    print(json.dumps({"summary": "ok", "search_keys": ["ok"], "sections": []}, ensure_ascii=False))
PY
chmod +x "$PROJECT/tools/related-provider.py"

python3 - "$PROJECT/.spec-anchor/config.toml" "$COLLECTION" "$PROJECT/tools/related-provider.py" <<'PY'
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
    f'[llm.providers.related]\ncommand = "{provider}"\nmodel = "related-provider"\neffort = "low"\ntimeout_sec = 30\nmax_retries = 0\n\n[llm.providers.codex]\ncommand = "codex"',
)
text = text.replace('section_metadata   = "codex"', 'section_metadata   = "related"')
text = text.replace('related_sections   = "claude_typing"', 'related_sections   = "related"')
text = text.replace('conflict_review    = "claude_judge"', 'conflict_review    = "related"')
text = text.replace('chapter_key_anchor = "codex"', 'chapter_key_anchor = "related"')
path.write_text(text, encoding="utf-8")
PY

printf '%s\n' "$PROJECT" > "$EVID/artifacts/project-path.txt"
cp "$PROJECT/.spec-anchor/config.toml" "$EVID/artifacts/config.initial.toml"

set +e
(
  cd "$PROJECT"
  spec-anchor core --rebuild
) > "$EVID/stdout/initial-core-rebuild.stdout" 2> "$EVID/stderr/initial-core-rebuild.stderr"
initial_exit=$?
set -e
printf '%s\n' "$initial_exit" > "$EVID/stdout/initial-core-rebuild.exitcode"

python3 "$EVID/scripts/collect-related-payload.py" "$PROJECT" "$EVID/artifacts/before-failure-payloads.json"

python3 - "$PROJECT/.spec-anchor/config.toml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace('url = "http://localhost:6333"', 'url = "http://127.0.0.1:65531"')
path.write_text(text, encoding="utf-8")
PY
cp "$PROJECT/.spec-anchor/config.toml" "$EVID/artifacts/config.broken-qdrant.toml"

set +e
(
  cd "$PROJECT"
  spec-anchor core --all
) > "$EVID/stdout/broken-qdrant-core.stdout" 2> "$EVID/stderr/broken-qdrant-core.stderr"
broken_exit=$?
set -e
printf '%s\n' "$broken_exit" > "$EVID/stdout/broken-qdrant-core.exitcode"

python3 "$EVID/scripts/collect-related-payload.py" "$PROJECT" "$EVID/artifacts/after-failure-payloads.json" "$COLLECTION"

set +e
(
  cd "$PROJECT"
  spec-anchor inject-search "login boundary"
) > "$EVID/stdout/inject-after-failure.stdout" 2> "$EVID/stderr/inject-after-failure.stderr"
inject_exit=$?
set -e
printf '%s\n' "$inject_exit" > "$EVID/stdout/inject-after-failure.exitcode"

set +e
(
  cd "$PROJECT"
  spec-anchor realign --answer-json '{"answer":"確認"}'
) > "$EVID/stdout/realign-after-failure.stdout" 2> "$EVID/stderr/realign-after-failure.stderr"
realign_exit=$?
set -e
printf '%s\n' "$realign_exit" > "$EVID/stdout/realign-after-failure.exitcode"

find "$PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files.txt"
python3 "$EVID/scripts/assert-related-failure-retention.py"
