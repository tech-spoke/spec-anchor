#!/usr/bin/env bash
set -euo pipefail

REPO=/home/kazuki/public_html/spec-anchor
RUN_ID=20260523-134200-codex-e2e-core-blocked-watcher
EVID="$REPO/doc/e2eテストCODEX実施用/evidence/$RUN_ID"
PROJECT=/tmp/${RUN_ID}.project

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
  printf 'date=%s\n' "$(date -Is)"
  printf 'SPEC_ANCHOR_FAKE_LLM=%s\n' "${SPEC_ANCHOR_FAKE_LLM-<unset>}"
  printf 'SPEC_ANCHOR_FAKE_RETRIEVAL=%s\n' "${SPEC_ANCHOR_FAKE_RETRIEVAL-<unset>}"
} > "$EVID/artifacts/environment.txt"

(
  cd "$PROJECT"
  spec-anchor-setup-project --target "$PROJECT" --agent both --force
) > "$EVID/stdout/setup.stdout" 2> "$EVID/stderr/setup.stderr"

python3 - "$PROJECT" <<'PY'
from __future__ import annotations

import json
import time
from pathlib import Path
import sys

project = Path(sys.argv[1])
(project / "docs/core").mkdir(parents=True, exist_ok=True)
(project / "docs/spec").mkdir(parents=True, exist_ok=True)
(project / "docs/core/purpose.md").write_text(
    "# Purpose\n\nwatcher 実行中の `/spec-core` blocked 出力を確認する。\n",
    encoding="utf-8",
)
(project / "docs/core/concept.md").write_text(
    "# Core Concept\n\nwatcher が Source Specs 更新を処理中の場合、手動 `/spec-core` は停止する。\n",
    encoding="utf-8",
)
(project / "docs/spec/main.md").write_text(
    "# Watcher Blocking Spec\n\n"
    "## Session Policy\n\n"
    "WATCHER_BLOCK_SENTINEL は watcher 更新中の停止確認に使う。\n",
    encoding="utf-8",
)

state_dir = project / ".spec-anchor/state"
state_dir.mkdir(parents=True, exist_ok=True)
now_ms = int(time.time() * 1000)
state_payload = {
    "schema_version": 1,
    "running": True,
    "is_running": True,
    "owner": "watcher",
    "run_id": "codex-e2e-active-watcher",
    "started_at": "2026-05-23T04:42:00Z",
    "started_at_epoch_ms": now_ms - 1000,
    "updated_at": "2026-05-23T04:42:01Z",
    "updated_at_epoch_ms": now_ms,
    "lock_file": (state_dir / "core_update.lock.json").as_posix(),
    "queue_count_at_start": 1,
}
lock_payload = {
    "schema_version": 1,
    "lock_kind": "core_update",
    "owner": "watcher",
    "reason": "watcher_running",
    "run_id": "codex-e2e-active-watcher",
    "acquired_at": "2026-05-23T04:42:00Z",
    "acquired_at_epoch_ms": now_ms - 1000,
    "updated_at": "2026-05-23T04:42:01Z",
    "updated_at_epoch_ms": now_ms,
}
(state_dir / "watch_state.json").write_text(
    json.dumps(state_payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
(state_dir / "core_update.lock.json").write_text(
    json.dumps(lock_payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

printf '%s\n' "$PROJECT" > "$EVID/artifacts/project-path.txt"
cp "$PROJECT/.spec-anchor/config.toml" "$EVID/artifacts/config.toml"
cp "$PROJECT/.spec-anchor/state/watch_state.json" "$EVID/artifacts/watch_state.before-core.json"
cp "$PROJECT/.spec-anchor/state/core_update.lock.json" "$EVID/artifacts/core_update.lock.before-core.json"

set +e
(
  cd "$PROJECT"
  spec-anchor core
) > "$EVID/stdout/core-while-watcher-running.stdout" 2> "$EVID/stderr/core-while-watcher-running.stderr"
core_exit=$?
set -e
printf '%s\n' "$core_exit" > "$EVID/stdout/core-while-watcher-running.exitcode"

python3 "$EVID/scripts/assert-core-blocked-watcher.py"
