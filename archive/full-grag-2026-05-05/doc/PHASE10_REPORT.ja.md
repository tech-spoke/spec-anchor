# Phase 10 実行報告: watcher / GRAG readiness gate / Concept diff queue

日付: 2026-05-02

## 実装概要

- `[runtime]` config と runtime policy resolver を追加した。`local_daily` は watcher required / foreground incremental 無効、`ci` は watcher なし foreground incremental 許可、`production` は dirty / pending / stale fail-fast を強制する。
- `[watcher]` config を追加した。`enabled`、`interval_ms`、`debounce_ms`、`stale_lock_ms`、`state_file`、`queue_file` を strict schema で検証し、`spec-grag-watch` は CLI 引数未指定時に project config の値を使う。
- GRAG readiness gate を追加し、source manifest、semantic hash、必須 artifact、embedding metadata、extractor version、Concept index、pending Concept diff、pending Conflict candidate を横断して `fresh` / `dirty` / `pending` / `stale` を判定する。
- `FreshnessReport.readiness_report` と `ResultEnvelope.execution.runtime_policy` を追加し、CoreResult / InjectionContext / RealignResult / run artifact から readiness と policy を追跡できるようにした。
- `.spec-grag/state/watch_state.json`、`watch_queue.json`、`provisional_concept_cache.json`、`watch_lock.json` を追加した。
- `spec-grag-watch` watcher を追加した。Source specs の semantic manifest を継続 polling 監視し、debounce 後に background incremental を実行する。
- watcher は single worker とし、開始時 snapshot を `run_core_update` に渡す。実行中に追加変更が入った場合は現 run に混ぜず、`watch_queue` に `running_change` / `post_run_change` として保存し、run 完了後の次サイクルで drain する。
- watcher 実行中は heartbeat を更新し、watch_state に `running_semantic_hash` と `queued_change_count` を残す。
- `/spec-inject` / `/spec-realign` は readiness gate 経由になり、fresh artifact では同期 core 更新を行わない。local daily の dirty/stale/watcher running/queued は blocked、CI/smoke は foreground incremental、production は fail-fast。
- pending Concept diff は単一 pending に制限した。pending 中の追加 semantic change は新しい diff を作らず watch_queue / provisional cache に積み、pending apply 後に queued change を最新 Concept base hash で再評価する。
- Concept diff の非承認は suppression ではなく未解決扱いにした。pending / provisional cache を残し、次回コマンドで同じ承認を求める。
- Concept diff の修正指示は `revision_instruction` を元に revised hunk を再生成し、再度 pending approval に戻す。修正版を承認すると apply され、provisional cache をクリアする。
- `options.approval` と `approval_prompt` を追加し、チャット上の承認 / 修正指示 / 非承認を外部 slash command 追加なしで内部 transport に渡せるようにした。Concept の承認は chat approval transport では accept + apply まで行う。
- `/spec-core` が Source specs 全体を横断して deterministic source-level Conflict candidate を検出し、`pending_conflict_review` を自動生成する経路を追加した。
- Conflict review artifact / approved_conflicts sidecar を追加し、candidate の accept / reject / defer / revise、承認済み Conflict sidecar 適用、reject fingerprint 保存を実装した。
- provisional concept cache は downstream context から切り離し、InjectionContext / Answer / ConflictNotes に混入しない regression を追加した。

## 主要ファイル

- `spec_grag/config.py`
- `spec_grag/readiness.py`
- `spec_grag/watch_state.py`
- `spec_grag/watcher.py`
- `spec_grag/conflict_review.py`
- `spec_grag/cli.py`
- `spec_grag/injection.py`
- `spec_grag/concept_index.py`
- `tests/test_phase10_readiness.py`

## 検証

- `uv run --with pytest python -m pytest tests/test_phase10_readiness.py -q`
  - 16 passed
- `uv run --with pytest python -m pytest tests/test_cli.py tests/test_injection_realign.py tests/test_core_e2e.py tests/test_external_contract_e2e.py -q`
  - 59 passed
- `uv run --with pytest python -m pytest -q`
  - 200 passed

## Phase 10 範囲外の後続改善

Phase 10 の完了条件は満たした。依存追加なしの常駐 polling watcher で Source specs 変更検知、single worker、snapshot 実行、queue drain、readiness gate blocking、`[watcher]` config 読み込みまで実装済みである。

後続改善として、OS native file event backend、daemon manager、OS 自動起動設定は別フェーズで扱う。これらは Phase 10 の未完了項目ではない。
