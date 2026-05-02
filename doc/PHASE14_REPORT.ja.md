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
