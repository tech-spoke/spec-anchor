# Phase 11 実行報告: stage timings / performance observability

日付: 2026-05-02

## 実装概要

- `spec_grag/timing.py` を追加し、`time.perf_counter_ns()` ベースの `TimingRecorder` / stage context manager を実装した。
- `ResultEnvelope.execution` に `timing_summary` と `stage_timings` を追加した。InjectionContext / RealignResult / CoreResult payload のトップレベル構造は増やしていない。
- run artifact の top-level に `timing_summary` と `stage_timings` を保存し、`execution` 側にも同じ診断情報を保持するようにした。
- `/spec-core` に `manifest_reconcile`、`semantic_noop_filter`、`stale_carry_forward`、`schema_llm_extraction`、`embedding_update`、`chunk_index_update`、`graph_sidecar_update`、`concept_diff`、`conflict_review`、`community_report`、`artifact_write` を追加した。
- `/spec-inject` / `/spec-realign` に `readiness_gate`、`retrieval`、`classification`、`answer_generation` を追加した。
- blocked / failed の早期 return でも、その時点までに完了した timings を `execution` と run artifact に残す。
- watcher の run artifact summary にも `CoreUpdate.timing_summary` / `stage_timings` を含め、background incremental の性能比較に使えるようにした。

## 保存しないもの

- Source specs 本文
- LLM prompt 本文
- LLM 応答本文

stage metrics は duration、status、provider/model、`llm_calls`、`input_sections`、`input_chunks`、`input_nodes` などの軽量な count / identity に限定した。

## 検証

- `uv run --with pytest python -m pytest tests/test_phase11_timings.py -q`
  - 4 passed
- `uv run --with pytest python -m pytest tests/test_cli.py tests/test_core_e2e.py tests/test_injection_realign.py tests/test_phase10_readiness.py -q`
  - 70 passed
- `uv run --with pytest python -m pytest -q`
  - 204 passed

## 実測プロトコル

初期 regression では fixture project で次を確認した。

- no-change `/spec-core`: `manifest_reconcile`、`semantic_noop_filter`、`artifact_write` が残り、`timing_summary.semantic_noop=true`、`heavy_path=false`。
- format-only `/spec-core`: semantic noop fast path に入り、`schema_llm_extraction` は出ない。
- semantic change + schema extraction: `schema_llm_extraction` と `embedding_update` が残り、`heavy_path=true`。
- local daily dirty `/spec-inject`: readiness gate blocked でも `readiness_gate` timing が run artifact に残る。
- embedding metadata mismatch `/spec-core`: failed でも完了済み `embedding_update` timing が run artifact に残る。

実 provider を使う production 相当の stage 比率は、次の監査フェーズで `doc/AUDIT_TODO.ja.md` の performance / production readiness と合わせて記録する。

## 残リスク / 次アクション

- LLM token usage は provider / CLI から安定取得できる場合だけ追加する方針のため、今回は未保存。
- `cache_hits` / `affected_nodes` などは意味が固定できる箇所だけ段階的に追加する。今回入れた cache 系 metric は cluster snapshot reuse の boolean に限定した。
- artifact transaction / rollback 監査、production full build の実測、GRAG quality evaluation は Phase 11 後の監査タスクとして継続する。
