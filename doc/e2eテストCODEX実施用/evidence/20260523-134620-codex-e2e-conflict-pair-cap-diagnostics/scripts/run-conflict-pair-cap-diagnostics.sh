#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-134620-codex-e2e-conflict-pair-cap-diagnostics
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project
COLLECTION=spec_anchor_sections_20260523_134620_conflict_cap

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

from pathlib import Path
import sys

project = Path(sys.argv[1])
collection = sys.argv[2]
log_path = Path(sys.argv[3])
(project / "docs/core").mkdir(parents=True, exist_ok=True)
(project / "docs/spec").mkdir(parents=True, exist_ok=True)
(project / "tools").mkdir(parents=True, exist_ok=True)
(project / "docs/core/purpose.md").write_text(
    "# Purpose\n\nconflict pair cap diagnostics の外部出力契約を確認する。\n",
    encoding="utf-8",
)
(project / "docs/core/concept.md").write_text(
    "# Core Concept\n\n同一 identifier に対する must / must not の高リスク候補は上限で絞る。\n",
    encoding="utf-8",
)
(project / "docs/spec/conflict-cap.md").write_text(
    "# Conflict Pair Cap Spec\n\n"
    "## Alpha Base\n\n"
    "FEATURE_CAP_TOKEN must be enabled for all jobs.\n"
    "ALPHA_CAP_FLAG defines the required side.\n\n"
    "## Beta Block\n\n"
    "FEATURE_CAP_TOKEN must not be enabled for beta jobs.\n"
    "BETA_CAP_FLAG defines the prohibited side.\n\n"
    "## Gamma Block\n\n"
    "FEATURE_CAP_TOKEN must not be enabled for gamma jobs.\n"
    "GAMMA_CAP_FLAG defines the prohibited side.\n\n"
    "## Delta Block\n\n"
    "FEATURE_CAP_TOKEN must not be enabled for delta jobs.\n"
    "DELTA_CAP_FLAG defines the prohibited side.\n\n"
    "## Epsilon Block\n\n"
    "FEATURE_CAP_TOKEN must not be enabled for epsilon jobs.\n"
    "EPSILON_CAP_FLAG defines the prohibited side.\n",
    encoding="utf-8",
)

provider = project / "tools/conflict-cap-provider.py"
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
if stage == "conflict_review":
    try:
        record["request"] = json.loads(payload.get("prompt") or "{}")
    except Exception:
        record["request"] = payload.get("prompt")
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\\n")

section_ids = list((payload.get("section_hashes") or {}).keys())
if stage == "section_metadata":
    sections = []
    for section_id in section_ids:
        if "alpha-base" in section_id:
            summary = "FEATURE_CAP_TOKEN must be enabled for all jobs."
            keys = ["FEATURE_CAP_TOKEN", "must enabled", "alpha base"]
        else:
            summary = f"{section_id} says FEATURE_CAP_TOKEN must not be enabled."
            keys = ["FEATURE_CAP_TOKEN", "must not enabled", "block"]
        sections.append({"section_id": section_id, "summary": summary, "search_keys": keys})
    print(json.dumps({"sections": sections}, ensure_ascii=False))
elif stage == "chapter_key_anchor":
    print(json.dumps({
        "summary": "conflict pair cap chapter",
        "key_topics": ["FEATURE_CAP_TOKEN", "conflict pair cap"],
        "important_sections": section_ids[:5],
        "notes": []
    }, ensure_ascii=False))
elif stage == "related_section_selection":
    print(json.dumps({"sections": []}, ensure_ascii=False))
elif stage == "conflict_review":
    print(json.dumps({
        "outcome": "not_conflict",
        "warning": "Pair was judged and retained only as a warning.",
        "why_not_pending": "The deterministic provider keeps this E2E focused on pair selection diagnostics."
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
    f'[llm.providers.conflict_cap]\ncommand = "{command}"\nmodel = "conflict-cap-provider"\neffort = "low"\ntimeout_sec = 30\nmax_retries = 0\n\n[llm.providers.codex]\ncommand = "codex"',
)
text = text.replace('section_metadata  = "codex"', 'section_metadata  = "conflict_cap"')
text = text.replace('section_metadata   = "codex"', 'section_metadata   = "conflict_cap"')
text = text.replace('related_sections  = "claude_typing"', 'related_sections  = "conflict_cap"')
text = text.replace('related_sections   = "claude_typing"', 'related_sections   = "conflict_cap"')
text = text.replace('conflict_review   = "claude_judge"', 'conflict_review   = "conflict_cap"')
text = text.replace('conflict_review    = "claude_judge"', 'conflict_review    = "conflict_cap"')
text = text.replace('chapter_key_anchor = "codex"', 'chapter_key_anchor = "conflict_cap"')
text = text.replace('conflict_pair_max_per_section = 8', 'conflict_pair_max_per_section = 1')
config_path.write_text(text, encoding="utf-8")
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

if [ -f "$PROJECT/.spec-anchor/state/core_progress.json" ]; then
  cp "$PROJECT/.spec-anchor/state/core_progress.json" "$EVID/artifacts/core_progress.json"
fi
if [ -f "$PROJECT/.spec-anchor/context/conflict_review_items.json" ]; then
  cp "$PROJECT/.spec-anchor/context/conflict_review_items.json" "$EVID/artifacts/conflict_review_items.json"
fi

set +e
python3 "$EVID/scripts/assert-conflict-pair-cap-diagnostics.py"
assert_exit=$?
set -e
printf '%s\n' "$assert_exit" > "$EVID/artifacts/assert.exitcode"
exit "$assert_exit"
