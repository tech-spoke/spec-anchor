#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-123504-codex-e2e-agent-verify-index
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project
COLLECTION=spec_anchor_sections_20260523_123504_agent_verify_index

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

この隔離 project は、Agent が Source Retrieval Index verify 失敗を利用者へ伝達することを確認する。
DOC
cat > "$PROJECT/docs/core/concept.md" <<'DOC'
# Core Concept

Source Retrieval Index の verify 失敗は自動修復せず、利用者に /spec-core --rebuild を促す。
DOC
cat > "$PROJECT/docs/spec/audit.md" <<'DOC'
# Audit Specification

## Login Audit

source id: login-audit

LOGIN_AUDIT_REQUIRED を満たすイベントを保存する。

## Logout Audit

source id: logout-audit

LOGOUT_AUDIT_REQUIRED を満たすイベントを保存する。
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
                        "search_keys": ["audit event", "login logout"],
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
                "summary": "audit chapter",
                "key_topics": ["audit", "login", "logout"],
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

python3 - "$PROJECT" "$EVID/artifacts/deleted-point.json" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

from qdrant_client import QdrantClient
from qdrant_client.models import PointIdsList

project = Path(sys.argv[1])
out = Path(sys.argv[2])
state = json.loads((project / ".spec-anchor/state/retrieval_index_state.json").read_text(encoding="utf-8"))
collection = state["collection_name"]
client = QdrantClient(url="http://localhost:6333")
records, _ = client.scroll(collection_name=collection, with_payload=True, limit=10)
if not records:
    raise SystemExit("no qdrant records to delete")
point = records[0]
client.delete(collection_name=collection, points_selector=PointIdsList(points=[point.id]))
out.write_text(
    json.dumps(
        {
            "collection": collection,
            "deleted_point_id": str(point.id),
            "source_section_id": (point.payload or {}).get("source_section_id"),
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

find "$PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files-before-agent.txt"
