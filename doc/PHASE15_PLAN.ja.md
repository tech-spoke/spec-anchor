# Phase 15 architecture audit hardening 計画

> 作成: 2026-05-03
> 位置づけ: Claude architecture audit 指摘のうち、current HEAD で正当かつ未対応のものを Phase 15 の実装計画へ落とす。外部契約の変更提案ではない。

## 判定方針

Phase 15 は監査指摘をそのまま採用するフェーズではない。`doc/EXTERNAL_DESIGN.ja.md`、`doc/DESIGN.ja.md`、現 HEAD の実装、実測 artifact に照らして、次の条件を満たすものだけを対象にする。

- current HEAD でまだ残っている
- 外部契約と矛盾しない
- production readiness、保守性、診断性、性能のいずれかを実質的に改善する
- 既存 JSON protocol を壊さず段階移行できる

対象外:

- Concept diff の reject を「解決済み」とみなす変更はしない。外部設計上、reject は pending と provisional cache を残し、次回も確認を求めるのが正しい。
- pending Concept / Conflict を apply 前に消す状態遷移変更は Phase 15 では扱わない。承認結果が approved sidecar / rejected fingerprint / Concept file に反映されるまでは gate の対象にする。
- Qdrant 移行、InjectionContext の protocol-breaking 型変更、native filesystem watcher 化は将来検討に留める。

## Phase 15 の目的

1. 中核モジュールの肥大化と重複 utility を減らし、変更範囲を読みやすくする。
2. production 障害時の原因追跡に必要な logging / diagnostics を入れる。
3. retrieval / artifact hot path の低リスクな性能改善を進める。
4. テスト追加の摩擦を下げ、refactor を小さく検証できる形にする。

## 実装ワークストリーム

### P15-A. 低リスク構造整理

- [x] `spec_grag/io.py` を追加し、atomic write / fsync helper を集約する
  - 対象候補: `core.py`、`chunk_index.py`、`concept_index.py`、`conflict_review.py`、`concept_diff.py`、`sidecars.py`、`watch_state.py`、`watcher.py`、`manifest.py`、`run_artifacts.py`、`realign.py`、`embedding.py`、`retrieval_index.py`
  - 受け入れ条件: 既存 artifact 書き込み挙動を変えず、focused tests と full regression が通る
- [x] `spec_grag/llm_factory.py` を追加し、用途別 LLM factory の重複を減らす
  - 対象候補: `core.py`、`injection.py`、`chunk_index.py`、`concept_index.py`、必要に応じて `realign.py`
  - 受け入れ条件: provider / model / retry / fallback policy の解決結果が既存と一致する
- [x] `injection.py` の classification priority magic numbers を named constants に移す
  - 受け入れ条件: priority order と Phase 14 budget policy の挙動が変わらない
- [x] `tests/conftest.py` を導入し、共有 fixture / CLI helper / integration marker を段階的に集約する
  - 受け入れ条件: 既存 test 名と呼び出し方式を壊さず、以後の追加 test が共通 helper を使える

### P15-B. 中核モジュール分割

- [ ] `injection_classification.py` を抽出する
  - 所有範囲: `ClassificationCandidate`、priority scoring、budget / deferred classification、batch LLM classification、persistent classification cache
- [ ] `injection_conflict.py` を抽出する
  - 所有範囲: deterministic conflict note helpers、required/optional などの rule-based validators
- [ ] `injection_retrieval.py` を抽出する
  - 所有範囲: graph traversal、hybrid chunk retrieval 連携、agentic candidate validation、retrieval item assembly
- [ ] `injection.py` は `build_injection` orchestration と InjectionContext assembly に寄せる
  - 受け入れ条件: public API と JSON output を維持し、既存 tests が無変更で通る
- [ ] `core.py` の `run_core_update` を stage 関数へ分ける
  - 候補 stage: manifest reconciliation、graph build、extraction、embedding、indexing、chapter anchors、concept index、cluster snapshot、concept diff、conflict review、staging commit
  - 受け入れ条件: no-change fast path と heavy staging path の artifact 結果が変わらない
- [x] `cli.py` の `run_spec_inject` / `run_spec_realign` の共通前処理を抽出する
  - 受け入れ条件: readiness gate、dirty/stale 時の挙動、answer 生成前 gate が既存どおり

### P15-C. Logging / diagnostics

- [x] `[logging]` config を追加する
  - 最小項目: `level`、必要なら watcher 用 `file_path` / `max_bytes` / `backup_count`
  - 既定: WARNING 相当。production で prompt / source body / LLM response body を不用意にログへ出さない
- [x] 主要 module に `logging.getLogger(__name__)` を導入する
  - 優先対象: `core.py`、`injection.py`、`chunk_index.py`、`concept_index.py`、`realign.py`、`watcher.py`
  - ログ対象: stage 開始/終了、cache hit/miss、provider call count、artifact path、diagnostic reason code
- [x] watcher の長期運用ログを整備する
  - 受け入れ条件: stderr だけに依存せず、stale / failed / queued / pending の理由を追える
- [x] foreground command と watcher の lock 方針を監査する
  - 受け入れ条件: background core update と foreground `/spec-core` / query command の同時実行時に active artifact を壊さないことを test または設計メモで示す

### P15-D. Retrieval / artifact performance

- [x] `graph_ops.safe_delete_by_sections()` を追加し、複数 section の stale 削除を 1 回の graph rebuild にまとめる
  - 受け入れ条件: single section API 互換を保ち、incremental update の artifact 結果が一致する
- [x] dense cosine search の短期高速化を入れる
  - 方針: numpy が利用できる場合は vectorized dot product、利用できない場合は現行 pure Python fallback
  - 受け入れ条件: ranking の tie 以外の差分を抑え、dependency policy を明示する
- [~] BM25 broad candidate 問題を追加監査する
  - 対象: candidate documents が 314-404/407 に広がる query、identifier 空時の挙動、field weighting、required term gate、`k1` / `b` config 化
  - 受け入れ条件: query set 5本で Source evidence を落とさず candidate 幅を縮める
- [x] Concept index の incremental embedding reuse を検討する
  - 受け入れ条件: concept chunk hash が同じ場合に embedding を再利用し、version mismatch 時は安全に rebuild する
- [ ] staging directory の `copytree` コストを監査する
  - 受け入れ条件: artifact 増加時の wall time と失敗時 diagnostics を記録する

### P15-E. Context item 型付けの段階移行

- [ ] `ContextItem` 相当の `TypedDict` または internal strict model を追加する
  - 初期対象: source chunk、concept chunk、graph entity、chapter anchor、cluster、conflict note、review note
  - 受け入れ条件: external JSON schema は変えない
- [ ] `realign.py` の `compact_item` keep keys を schema/category helper へ寄せる
  - 受け入れ条件: answer cache key と compact context の安定性を維持する
- [ ] protocol-level `ContextItem` model 化は別フェーズ判断に残す

## 推奨実装順

1. P15-A の `io.py` / `llm_factory.py` / priority constants を小 commit で進める。
2. P15-D の `safe_delete_by_sections()` と BM25 追加監査を入れる。
3. P15-C の logging config と watcher diagnostics を最小導入する。
4. P15-B の `injection.py` 分割を 1 concern ずつ進める。
5. P15-B の `core.py` stage 分割と `cli.py` read path 共通化を進める。
6. P15-E の internal typing を入れ、protocol-breaking 変更が必要かを再評価する。

## 検証方針

- behavior preserving refactor は focused tests + `uv run --with pytest python -m pytest -q` を通す。
- retrieval scoring / latency に触る変更は、既存 query set 5本を再実測し、run artifact ID と stage timings を `doc/AUDIT_TODO.ja.md` に残す。
- logging / diagnostics は privacy check を含める。prompt 本文、source 本文、LLM response 本文を既定ログへ出さない。
- watcher / lock 方針は foreground と background の同時実行リスクを test または設計メモで閉じる。

## 2026-05-03 実施メモ

- P15-A: atomic write 共通化、LLM factory 共通化、priority constants、`tests/conftest.py` を実装。
- P15-B: `cli.py` の inject / realign 共通 readiness + injection pipeline を抽出。`injection.py` / `core.py` の大型分割は未着手。
- P15-C: `[logging]` config、entrypoint logging setup、主要 module logger、watcher file logging の最小導入を実装。詳細な stage diagnostics と lock 方針監査は継続。
- P15-C 追補: foreground `/spec-core` と dirty/stale 時の inject / realign core update は watcher と同じ `WatchLock` を取得する。lock が存在する場合は `watcher_processing` blocked にする。
- P15-D: `safe_delete_by_sections()` と optional numpy dense similarity を実装。BM25 broad candidate、Concept index incremental embedding reuse、staging copytree 監査は継続。
- P15-D 追補: Concept index は同一 `text_hash` の embedding reuse を実装。BM25 は broad char candidate が広がり、identifier / word term の candidate がある場合に strong-term candidate へ prune する一次対策を追加。
- focused regression: `uv run --with pytest python -m pytest tests/test_graph_ops.py tests/test_phase9_production_policy.py tests/test_phase7_packaging.py::test_template_resources_are_packaged_for_wheel_install tests/test_phase8_hybrid_retrieval.py -q` -> `32 passed in 15.23s`
- focused regression: `uv run --with pytest python -m pytest tests/test_realign_answer.py tests/test_core_extraction.py tests/test_core_e2e.py tests/test_phase8_hybrid_retrieval.py tests/test_phase9_production_policy.py tests/test_phase7_packaging.py -q` -> `67 passed in 69.05s`
- focused regression: `uv run --with pytest python -m pytest tests/test_concept_index.py tests/test_phase8_hybrid_retrieval.py -q` -> `19 passed in 12.27s`
- focused regression: `uv run --with pytest python -m pytest tests/test_cli.py -q` -> `26 passed in 59.47s`
- full regression: `uv run --with pytest python -m pytest -q` -> `246 passed in 201.81s`

## 完了条件

- Phase 15 対象項目のうち、少なくとも P15-A と P15-C の最小導入が完了している。
- `injection.py` / `core.py` の分割計画が実装 commit 単位で進み、public API と JSON protocol が維持されている。
- `doc/AUDIT_TODO.ja.md` の Claude architecture audit 継続課題が、実装済み / 後続フェーズ / 非対象に分類済み。
- full regression が通り、production policy で silent rule-based fallback 不可、medium / low incomplete degraded 維持、Concept reject 未解決扱いが保たれている。
