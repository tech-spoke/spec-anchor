#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
BASE_PROJECT=/tmp/20260523-103156-codex-e2e-realign-output.project
RUN_ID=20260523-104149-codex-e2e-agent-core-errors
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
CHAPTER_PROJECT=/tmp/${RUN_ID}.chapter.project
QDRANT_PROJECT=/tmp/${RUN_ID}.qdrant.project

mkdir -p "$EVID/stdout" "$EVID/stderr" "$EVID/artifacts"
rm -rf "$CHAPTER_PROJECT" "$QDRANT_PROJECT"
cp -a "$BASE_PROJECT" "$CHAPTER_PROJECT"
cp -a "$BASE_PROJECT" "$QDRANT_PROJECT"

export PATH="$REPO/.venv/bin:$PATH"
unset SPEC_ANCHOR_FAKE_LLM
unset SPEC_ANCHOR_FAKE_RETRIEVAL

python3 - "$CHAPTER_PROJECT/.spec-anchor/config.toml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    'section_collection = "spec_anchor_sections_20260523_103156_realign_output"',
    'section_collection = "spec_anchor_sections_20260523_104149_chapter_error"',
)
text = text.replace(
    'chapter_key_anchor = "codex"',
    'chapter_key_anchor = "fail_chapter"',
)
text += '''

[llm.providers.fail_chapter]
command = "/bin/false"
model = "intentional-chapter-failure"
effort = "low"
timeout_sec = 5
max_retries = 0
'''
path.write_text(text, encoding="utf-8")
PY

python3 - "$QDRANT_PROJECT/.spec-anchor/config.toml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    'section_collection = "spec_anchor_sections_20260523_103156_realign_output"',
    'section_collection = "spec_anchor_sections_20260523_104149_qdrant_error"',
)
text = text.replace('url = "http://localhost:6333"', 'url = "http://127.0.0.1:65531"')
path.write_text(text, encoding="utf-8")
PY

{
  echo "run_id=$RUN_ID"
  echo "repo=$REPO"
  echo "base_project=$BASE_PROJECT"
  echo "chapter_project=$CHAPTER_PROJECT"
  echo "qdrant_project=$QDRANT_PROJECT"
  echo "date=$(date -Is)"
  echo "SPEC_ANCHOR_FAKE_LLM=${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  echo "SPEC_ANCHOR_FAKE_RETRIEVAL=${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
} > "$EVID/artifacts/environment.txt"

printf '%s\n' "$CHAPTER_PROJECT" > "$EVID/artifacts/chapter-project-path.txt"
printf '%s\n' "$QDRANT_PROJECT" > "$EVID/artifacts/qdrant-project-path.txt"
find "$CHAPTER_PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/chapter-project-files.txt"
find "$QDRANT_PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/qdrant-project-files.txt"

exit 0
