#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-135200-codex-e2e-watch-internal-no-agent-cli
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project
COLLECTION=spec_anchor_sections_20260523_135200_watch_internal
RUN_PATH="$REPO/.venv/bin:/usr/bin:/bin"

export PATH="$RUN_PATH"
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
  printf 'PATH=%s\n' "$PATH"
  printf 'date=%s\n' "$(date -Is)"
  printf 'codex_path=%s\n' "$(command -v codex || true)"
  printf 'claude_path=%s\n' "$(command -v claude || true)"
  printf 'SPEC_ANCHOR_FAKE_LLM=%s\n' "${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  printf 'SPEC_ANCHOR_FAKE_RETRIEVAL=%s\n' "${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
} > "$EVID/artifacts/environment.txt"

(
  cd "$PROJECT"
  spec-anchor-setup-project --target "$PROJECT" --agent both --force
) > "$EVID/stdout/setup.stdout" 2> "$EVID/stderr/setup.stderr"

python3 - "$PROJECT" "$COLLECTION" "$EVID/artifacts/provider-invocations.jsonl" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

project = Path(sys.argv[1])
collection = sys.argv[2]
log_path = Path(sys.argv[3])
(project / "docs/core").mkdir(parents=True, exist_ok=True)
(project / "docs/spec").mkdir(parents=True, exist_ok=True)
(project / "tools").mkdir(parents=True, exist_ok=True)
(project / "docs/core/purpose.md").write_text(
    "# Purpose\n\nwatcher が Agent CLI なしで内部 core 更新を行うことを確認する。\n",
    encoding="utf-8",
)
(project / "docs/core/concept.md").write_text(
    "# Core Concept\n\nwatcher は slash command を外部起動せず、内部 runner で保持物を更新する。\n",
    encoding="utf-8",
)
(project / "docs/spec/watch.md").write_text(
    "# Watch Internal Spec\n\n"
    "## Initial Policy\n\n"
    "WATCH_INTERNAL_INITIAL controls initial state.\n",
    encoding="utf-8",
)

provider = project / "tools/watch-provider.py"
provider.write_text(
    """#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
payload = json.loads(sys.stdin.read() or "{}")
stage = payload.get("stage") or payload.get("task")
record = {
    "stage": stage,
    "section_hashes": sorted((payload.get("section_hashes") or {}).keys()),
}
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\\n")

section_ids = list((payload.get("section_hashes") or {}).keys())
if stage == "section_metadata":
    print(json.dumps({
        "sections": [
            {
                "section_id": section_id,
                "summary": f"summary for {section_id}",
                "search_keys": ["watch internal", "no agent cli", section_id],
            }
            for section_id in section_ids
        ]
    }, ensure_ascii=False))
elif stage == "chapter_key_anchor":
    print(json.dumps({
        "summary": "watch internal chapter",
        "key_topics": ["watch internal", "background update"],
        "important_sections": section_ids[:5],
        "notes": []
    }, ensure_ascii=False))
elif stage == "related_section_selection":
    print(json.dumps({"sections": []}, ensure_ascii=False))
elif stage == "conflict_review":
    print(json.dumps({"outcome": "not_conflict", "warning": "no conflict"}, ensure_ascii=False))
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
    f'[llm.providers.watch_e2e]\ncommand = "{command}"\nmodel = "watch-provider"\neffort = "low"\ntimeout_sec = 30\nmax_retries = 0\n\n[llm.providers.codex]\ncommand = "codex"',
)
text = text.replace('section_metadata  = "codex"', 'section_metadata  = "watch_e2e"')
text = text.replace('section_metadata   = "codex"', 'section_metadata   = "watch_e2e"')
text = text.replace('related_sections  = "claude_typing"', 'related_sections  = "watch_e2e"')
text = text.replace('related_sections   = "claude_typing"', 'related_sections   = "watch_e2e"')
text = text.replace('conflict_review   = "claude_judge"', 'conflict_review   = "watch_e2e"')
text = text.replace('conflict_review    = "claude_judge"', 'conflict_review    = "watch_e2e"')
text = text.replace('chapter_key_anchor = "codex"', 'chapter_key_anchor = "watch_e2e"')
config_path.write_text(text, encoding="utf-8")
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

python3 - "$PROJECT" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1]) / "docs/spec/watch.md"
text = path.read_text(encoding="utf-8")
text += "\n## Watch Added Policy\n\nWATCH_INTERNAL_ADDED is added after initial core.\n"
path.write_text(text, encoding="utf-8")
PY
cp "$PROJECT/docs/spec/watch.md" "$EVID/artifacts/watch-after-change.md"

set +e
(
  cd "$PROJECT"
  spec-anchor-watch --once
) > "$EVID/stdout/watch-once.stdout" 2> "$EVID/stderr/watch-once.stderr"
watch_exit=$?
set -e
printf '%s\n' "$watch_exit" > "$EVID/stdout/watch-once.exitcode"

if [ -f "$PROJECT/.spec-anchor/state/watch_state.json" ]; then
  cp "$PROJECT/.spec-anchor/state/watch_state.json" "$EVID/artifacts/watch_state.after-watch.json"
fi
if [ -f "$PROJECT/.spec-anchor/state/core_progress.json" ]; then
  cp "$PROJECT/.spec-anchor/state/core_progress.json" "$EVID/artifacts/core_progress.after-watch.json"
fi

python3 "$EVID/scripts/assert-watch-internal-no-agent-cli.py"
