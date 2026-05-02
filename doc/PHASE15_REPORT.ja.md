# Phase 15 architecture audit hardening report

> 作成: 2026-05-03
> 対象: Phase 15 first implementation pass。外部契約を変えず、正当で現在も残る architecture audit 指摘のうち低リスクなものを実装した。

## 実装内容

- `spec_grag/io.py` を追加し、atomic text / JSON / model write と directory fsync を共通化した。
- `spec_grag/llm_factory.py` を追加し、用途別 CLI LLM adapter factory の重複を削減した。
- `injection.py` の classification priority score を named constants 化した。
- `tests/conftest.py` を追加し、repo root fixture と `integration` marker 登録を入れた。
- `[logging]` config、`spec_grag/logging_config.py`、CLI / watcher entrypoint の logging setup を追加した。既定は WARNING、file path は `.spec-grag/logs/spec-grag.log`。
- `graph_ops.safe_delete_by_sections()` を追加し、core incremental の stale graph artifact 削除を section ごとの rebuild から batch rebuild へ変更した。
- dense search は numpy が利用できる場合に vectorized cosine similarity を使い、利用できない場合は従来 pure Python に fallback する。
- Concept index refresh は、embedding metadata が一致する既存 index から同一 `text_hash` の chunk embedding を再利用する。
- BM25 search は、broad char term で candidate が大きく広がり、identifier / word term の candidate が存在する場合に strong-term candidate へ prune する。
- `cli.py` の `/spec-inject` / `/spec-realign` 共通 readiness gate + injection build pipeline を `run_injection_pipeline()` に抽出した。
- foreground `/spec-core` と dirty/stale 時の inject / realign core update は watcher と `WatchLock` を共有する。lock 取得不可の場合は `watcher_processing` blocked として active artifact を守る。

## 維持した設計

- Concept reject は未解決として残し、次回も確認を求める。
- apply 前 pending を gate から外さない。
- production の silent rule-based fallback 不可を維持する。
- InjectionContext の外部 JSON protocol は変更しない。
- Qdrant は導入しない。

## 検証

- `uv run python -m compileall -q spec_grag` -> pass
- `uv run --with pytest python -m pytest tests/test_graph_ops.py tests/test_phase9_production_policy.py tests/test_phase7_packaging.py::test_template_resources_are_packaged_for_wheel_install tests/test_phase8_hybrid_retrieval.py -q` -> `32 passed in 15.23s`
- `uv run --with pytest python -m pytest tests/test_realign_answer.py tests/test_core_extraction.py tests/test_core_e2e.py tests/test_phase8_hybrid_retrieval.py tests/test_phase9_production_policy.py tests/test_phase7_packaging.py -q` -> `67 passed in 69.05s`
- `uv run --with pytest python -m pytest tests/test_concept_index.py tests/test_phase8_hybrid_retrieval.py -q` -> `19 passed in 12.27s`
- `uv run --with pytest python -m pytest tests/test_cli.py -q` -> `26 passed in 59.47s`
- `uv run --with pytest python -m pytest -q` -> `246 passed in 201.81s`

## 残り

- `injection.py` を classification / conflict / retrieval concern へ分割する。
- `core.py` の `run_core_update` を stage 関数へ分ける。
- BM25 broad candidate 問題を query set 5本で再実測する。
- staging `copytree` コストと failure diagnostics を監査する。
