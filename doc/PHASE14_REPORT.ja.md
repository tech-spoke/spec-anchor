# Phase 14 classification priority / budget policy 実行報告

## 概要

Phase 14 では、GraphRAG retrieval 後の分類候補を一度 `ClassificationCandidate` として収集し、`classification_key` で dedup したうえで priority sort と type budget を適用してから LLM classification を実行するように変更した。

目的は、`classification.max_items` を増やすだけでなく、Purpose / raw source / target 近傍 / approved Concept を graph entity / chapter anchor / cluster より先に分類すること。production で budget 超過した場合の `classification_incomplete` 契約は維持した。

## 実装

- `[classification] max_items = 20` に拡大
- type 別 budget を追加
  - `max_source_chunks = 12`
  - `max_concepts = 4`
  - `max_graph_entities = 4`
  - `max_chapter_anchors = 2`
  - `max_clusters = 2`
  - `batch_size = 5`
  - `cache_enabled = true`
  - `cache_path = ".spec-grag/cache/classification_cache.json"`
  - `fail_on_high_priority_incomplete = true`
- inline classification を削減し、候補収集 -> dedup -> priority sort -> budget 適用 -> classification の順に変更
- LLM classification は最大 `batch_size` 件ずつ structured output で実行する
- persistent classification cache を追加し、`classification_key`、content fingerprint、provider/model/prompt policy が一致する場合は budget 消費前に cache hit とする
- `classification_source = "classification_incomplete"`、`classification_llm_skipped = "max_items_exhausted"`、`review_required = true` の production 契約を維持
- classification stage metrics に以下を追加
  - `candidate_count_by_type`
  - `classified_count_by_type`
  - `skipped_count_by_type`
  - `deprioritized_count_by_type`
  - `high_priority_skipped_count`
  - `medium_priority_skipped_count`
  - `low_priority_skipped_count`
  - `cache_hit_count`
  - `priority_selected_summary`
  - `priority_skipped_summary`

## 検証

- `uv run --with pytest python -m pytest tests/test_phase9_production_policy.py tests/test_phase12_hardening.py tests/test_injection_realign.py tests/test_phase7_packaging.py::test_template_resources_are_packaged_for_wheel_install -q`
  - `51 passed in 25.53s`
- `uv run --with pytest python -m pytest -q`
  - `228 passed in 197.40s`

## production self E2E

### spec-inject

- command: `spec-inject --message 'Scoped Store と Action runtime の設計上の制約を確認したい'`
- result: exit 0、`status=degraded`、`context_ready=true`
- timing: total `108,385ms`、retrieval `15,664ms`、classification `92,464ms`
- llm calls: 21
- classification: candidate 38、classified 20、skipped 18
- classified: Purpose 1、source chunk 12、Concept 2、graph entity 4、chapter anchor 1
- skipped: graph entity 8、chapter anchor 4、cluster 6
- `high_priority_skipped_count = 0`
- warning: `classification_incomplete` / `classification_medium_priority_incomplete`
- artifact: `.spec-grag/runs/20260502T075818.783343Z-spec-inject-7e81989e392a.json`

### spec-inject batch / cache 後

- command: `spec-inject --message 'Scoped Store と Action runtime の設計上の制約を確認したい'`
- first batch result: exit 0、`status=degraded`、total `72,489ms`、retrieval `19,104ms`、classification `53,085ms`
- first batch classification: candidate 38、selected 20、classified 20、skipped 18、classification LLM calls 4、cache hit 0、`high_priority_skipped_count = 0`
- persistent cache rerun: exit 0、`status=degraded`、total `44,670ms`、retrieval `14,124ms`、classification `30,277ms`
- persistent cache classification: candidate 42、selected 26、classified 11、skipped 16、classification LLM calls 3、cache hit 15、`classification_budget_remaining = 9`、`high_priority_skipped_count = 0`
- warning: `classification_incomplete` / `classification_medium_priority_incomplete`
- artifacts:
  - `.spec-grag/runs/20260502T081601.899646Z-spec-inject-7b71d453395a.json`
  - `.spec-grag/runs/20260502T081700.397111Z-spec-inject-925565b62f5d.json`

### spec-realign

- command: `spec-realign --task-prompt 'Scoped Store と Action runtime の設計上の制約を、根拠付きで簡潔に整理して'`
- result: exit 0、`status=degraded`、`context_ready=true`、answer 生成完了
- timing: total `160,713ms`、retrieval `19,290ms`、classification `99,452ms`、answer `41,728ms`
- llm calls: 22
- classification: candidate 40、classified 20、skipped 20
- classified: Purpose 1、source chunk 12、Concept 2、graph entity 4、chapter anchor 1
- skipped: graph entity 8、chapter anchor 5、cluster 7
- `high_priority_skipped_count = 0`
- warning: `classification_incomplete` / `classification_medium_priority_incomplete`
- artifact: `.spec-grag/runs/20260502T080058.085853Z-spec-realign-32aa47a12a59.json`

### spec-realign batch / cache 後

- command: `spec-realign --task-prompt 'Scoped Store と Action runtime の設計上の制約を、根拠付きで簡潔に整理して'`
- result: exit 0、`status=degraded`、`context_ready=true`、answer 生成完了
- timing: total `89,423ms`、retrieval `17,615ms`、classification `28,672ms`、answer `42,844ms`
- llm calls: 4
- classification: candidate 38、selected 29、classified 10、skipped 9、classification LLM calls 2、cache hit 19
- `high_priority_skipped_count = 0`
- warning: `classification_incomplete` / `classification_medium_priority_incomplete`
- artifact: `.spec-grag/runs/20260502T082150.417804Z-spec-realign-fd72d9ad2316.json`

## 残課題

Phase 14 の priority / budget policy は効いた。batch classification と persistent cache により、classification は 90-100 秒台から 28-53 秒台まで改善した。

残る改善候補は以下。

- query planner cache / deterministic fast path: no-change inject でも retrieval stage の query planner LLM が残る
- answer generation latency: `spec-realign` では answer LLM が 40 秒台を占める
- graph/chapter/cluster の deferred classification: medium/low priority は answer に使う必要がある時だけ分類する

## 2026-05-02 監査追補

残監査 query set で、`Concept にないが Source specs にある制約の扱い` が `classification_high_priority_incomplete` / failed になった。原因は type budget が tier 0 graph entity にも適用され、`fail_on_high_priority_incomplete=true` と衝突したため。

修正:

- `select_classification_candidates()` で type budget は tier > 0 にのみ適用する
- high priority candidate は global `max_items` だけで制限し、type budget では落とさない
- classification warning だけの場合、`degraded_components` が `retrieval` を含まないよう attribution を修正

検証:

- `uv run --with pytest python -m pytest tests/test_phase12_hardening.py::test_high_priority_classification_candidates_bypass_type_budget tests/test_phase12_hardening.py::test_classification_priority_selects_purpose_and_raw_source_before_graph_cluster tests/test_cli.py::test_cli_answer_failure_can_fallback_to_template -q` -> `3 passed in 2.83s`
- `uv run --with pytest python -m pytest -q` -> `229 passed in 187.76s`
- 再実行 artifact `.spec-grag/runs/20260502T084927.386804Z-spec-inject-2bf9dae9cfe6.json`: `status=degraded`、`high_priority_skipped_count=0`、`medium_priority_skipped_count=4`、`degraded_components=['classification']`

production policy は、medium / low priority incomplete でも warning-only にはせず degraded 維持とする。silent rule-based fallback は引き続き不可。deferred classification は別タスクとして残す。

## 2026-05-03 監査実装追補

Phase 14 後の残監査で見つかった retrieval / latency 課題に対して、以下を追加した。

- QueryPlan cache: `[query_planner] cache_enabled/cache_path` を追加し、graph revision / provider / model / prompt policy / query が一致する場合は planner LLM を省略する
- BM25 query 分離: BM25 は raw query + identifiers/entities/expected areas のみにし、expanded QueryPlan は dense query に限定。BM25 query terms は `bm25_term_limit = 80`
- Concept index v2: Markdown list item を 1 chunk にし、旧 version artifact は readiness で stale として検出。テンプレート導入文 chunk は query-side filter で除外
- Answer context compaction/cache: Answer prompt に渡す InjectionContext を件数・excerpt 長で圧縮し、Answer cache を追加。cache key から freshness timestamp / classification cache-hit metadata を除外
- Deferred classification: primary budget 後に medium / low priority skipped を最大 6 件追加分類する。production の silent rule-based fallback 不可は維持

検証:

- `uv run --with pytest python -m pytest tests/test_concept_index.py tests/test_phase8_hybrid_retrieval.py tests/test_phase10_readiness.py::test_readiness_marks_old_concept_index_version_stale tests/test_phase12_hardening.py tests/test_realign_answer.py tests/test_phase9_production_policy.py tests/test_cli.py::test_cli_answer_failure_can_fallback_to_template -q` -> `58 passed in 15.68s`
- `uv run --with pytest python -m pytest tests/test_realign_answer.py::test_answer_cache_key_ignores_volatile_runtime_metadata tests/test_realign_answer.py::test_answer_cache_round_trips_by_task_and_context -q` -> `2 passed in 2.32s`
- `uv run --with pytest python -m pytest tests/test_concept_index.py::test_retrieve_concept_chunks_filters_template_intro_and_prefers_term_match -q` -> `1 passed in 1.69s`
- `uv run --with pytest python -m pytest -q` -> `240 passed in 211.84s`

production self 実測:

- `spec-core`: `.spec-grag/runs/20260502T153505.476508Z-spec-core-f9f636203d11.json`、Concept index v2 chunks 17、warning `concept_index_version_mismatch_rebuilt`
- query set q1〜q4: `status=degraded`、`high_priority_skipped_count=0`、`medium_priority_skipped_count=0`、残りは `classification_low_priority_incomplete`
- q5: `.spec-grag/runs/20260502T154122.527438Z-spec-inject-c4b65b04c98d.json` は `status=ok`
- QueryPlan cache hit: `.spec-grag/runs/20260502T154138.492288Z-spec-inject-c57b13ce9e8a.json`、retrieval `4,722ms`、planner LLM calls 0
- Answer cache hit: `.spec-grag/runs/20260502T154702.759380Z-spec-realign-5aaef0f12cff.json`、answer `2.886ms`、answer LLM calls 0

残る課題:

- BM25 candidate documents は 314〜404/407 とまだ広く、postings / term priority / field weighting の追加監査が必要
- Answer cache miss はまだ 38秒台
- low priority cluster incomplete による degraded は q1〜q4 で残る
