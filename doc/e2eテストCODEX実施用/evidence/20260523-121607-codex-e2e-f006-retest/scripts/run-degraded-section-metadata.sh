#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-121607-codex-e2e-f006-retest
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project
COLLECTION=spec_anchor_sections_20260523_121607_f006_retest

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

この隔離 project は、Section Metadata の一部生成失敗が degraded として外部出力されることを確認する。
DOC
cat > "$PROJECT/docs/core/concept.md" <<'DOC'
# Core Concept

必須 artifact が揃っている場合、一部 section の retrieval aid 生成失敗は利用者に warning として伝達し、検索 API は継続可能にする。
DOC
cat > "$PROJECT/docs/spec/flow.md" <<'DOC'
# Login Flow

## Successful Login

source id: successful-login

LOGIN_SUCCESS_AUDIT を記録し、利用者を認証済みとして扱う。

## Broken Metadata Section

source id: broken-metadata-section

この section は Section Metadata provider の一部失敗を再現するための入力である。
BROKEN_METADATA_SENTINEL はこの section にだけ存在する。

## Logout

source id: logout

LOGOUT_AUDIT を記録し、active session を無効化する。
DOC

cat > "$PROJECT/tools/partial-section-provider.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

payload = json.loads(sys.stdin.read() or "{}")
stage = payload.get("stage") or payload.get("task")
section_ids = list((payload.get("section_hashes") or {}).keys())
section_id = section_ids[0] if section_ids else str(payload.get("section_id") or "unknown")

if stage == "section_metadata":
    if "broken-metadata-section" in section_id:
        print(json.dumps({"invalid": "missing sections"}, ensure_ascii=False))
    else:
        print(
            json.dumps(
                {
                    "sections": [
                        {
                            "section_id": section_id,
                            "summary": f"summary for {section_id}",
                            "search_keys": ["login audit", "session boundary"],
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )
elif stage == "chapter_key_anchor":
    print(
        json.dumps(
            {
                "summary": "chapter anchor summary",
                "key_topics": ["login", "audit"],
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
chmod +x "$PROJECT/tools/partial-section-provider.py"

python3 - "$PROJECT/.spec-anchor/config.toml" "$COLLECTION" "$PROJECT/tools/partial-section-provider.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
collection = sys.argv[2]
provider = sys.argv[3]
text = path.read_text(encoding="utf-8")
for key in ("section_collection", "collection"):
    text = text.replace(f'{key} = "spec_anchor_sections"', f'{key} = "{collection}"')
    text = text.replace(f'{key} = "spec_anchor_section"', f'{key} = "{collection}"')
text = text.replace("llm_batch_max_sections = 8", "llm_batch_max_sections = 1")
text = text.replace("llm_batch_concurrency = 1", "llm_batch_concurrency = 1")
text = text.replace("[chapter_anchor]\nenabled = true", "[chapter_anchor]\nenabled = false")
text = text.replace(
    '[llm.providers.codex]\ncommand = "codex"',
    f'[llm.providers.partial_section]\ncommand = "{provider}"\nmodel = "partial-section-provider"\neffort = "low"\ntimeout_sec = 30\nmax_retries = 0\n\n[llm.providers.codex]\ncommand = "codex"',
)
text = text.replace('section_metadata   = "codex"', 'section_metadata   = "partial_section"')
text = text.replace('related_sections   = "claude_typing"', 'related_sections   = "partial_section"')
text = text.replace('conflict_review    = "claude_judge"', 'conflict_review    = "partial_section"')
text = text.replace('chapter_key_anchor = "codex"', 'chapter_key_anchor = "partial_section"')
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

set +e
(
  cd "$PROJECT"
  spec-anchor inject-search "login audit"
) > "$EVID/stdout/inject-search.stdout" 2> "$EVID/stderr/inject-search.stderr"
inject_exit=$?
set -e
printf '%s\n' "$inject_exit" > "$EVID/stdout/inject-search.exitcode"

set +e
(
  cd "$PROJECT"
  spec-anchor realign --answer-json '{"constraints":["degraded optional artifact can continue with warnings"],"targets":["F006 retest"],"human_review":[],"answer":"Check degraded warning propagation."}'
) > "$EVID/stdout/realign.stdout" 2> "$EVID/stderr/realign.stderr"
realign_exit=$?
set -e
printf '%s\n' "$realign_exit" > "$EVID/stdout/realign.exitcode"

find "$PROJECT" -maxdepth 4 -type f | sort > "$EVID/artifacts/project-files.txt"
python3 "$EVID/scripts/assert-degraded-section-metadata.py"
