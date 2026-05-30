# TODO: 1 回の /spec-core 内で BGE-M3 を 1 回だけ load する (provider 共有)

**起票日**: 2026-05-31
**起票者**: Claude main (実機計測で発見)
**最終更新**: 2026-05-31
**ステータス**: 完了（案 A 実装、commit `dee9550`。実機 instrument で BGEM3FlagModel 構築 2→1 を確認、total wall 123→118 s。targeted 112 passed。人間レビュー待ち）
**関連設計書**: `tests/e2e/snapshots/#9-s10_flagembedding_load_count_real_run.md` (計測エビデンス)、`doc/性能測定/METRICS.md` 第12回

## 全体目的

1 回の `spec-anchor core` 実行中に FlagEmbedding BGE-M3 model weights が **2 回 load** されている。これを **1 回** に減らし、無駄な ~5-10 s (warm cache 時) / 数十秒 (cold 時) を削る。

### 背景 (実機計測で判明)

2026-05-31 の instrument 計測 (`FlagEmbedding.BGEM3FlagModel` と `FlagEmbeddingBgeM3Provider.__init__` を wrap して `spec-anchor core --rebuild` を 1 回実行) で、BGEM3FlagModel が **2 回構築** されていることが判明した。call site:

```
# load #1: section collection の embedding upsert
spec_anchor/core.py:428 (_run_spec_core_unlocked → section_collection_upsert)
  -> retrieval_index.py:211  BGEM3FlagModel(model, **model_kwargs)

# load #2: related_sections 候補生成の retrieval
spec_anchor/core.py:471 (_run_spec_core_unlocked → _generate_related_sections)
  -> related_sections.py:1128 → :427 → retrieval_index.py:211  BGEM3FlagModel(...)
```

`FlagEmbeddingBgeM3Provider` は `__init__` で `self._model = BGEM3FlagModel(...)` を直接構築し、class-level cache を持たない (旧 #9-s10 の「1 回 load・instance 共有」主張は `id(.model)` 文字列比較に依る誤りだった。`._model` 実オブジェクトは別物)。section_collection_upsert と related_sections がそれぞれ独立に retriever / provider を構築するため、同一 `/spec-core` 内で 2 回 load する。

> 注: section 数 > 12 の retrieval_cap mode では section_pair candidate generation も独自に retriever を構築するため、その場合は **3 回 load** になりうる。

## 対応方針 (案)

1 回の `/spec-core` 内で `FlagEmbeddingBgeM3Provider` (または `BGEM3FlagModel`) を **1 つ構築して共有**する。候補:

- **案 A (provider を core で 1 回構築して各経路へ注入)**: `_run_spec_core_unlocked` の先頭で provider を 1 回作り、section_collection_upsert / related_sections / (retrieval_cap 時) section_pair candidate generation の retriever 構築へ `embedding_provider=` 引数で渡す。`QdrantHybridRetriever.__init__` は既に `embedding_provider` 引数を受ける (retrieval_index.py:390)。related_sections と section_pair_candidates の retriever 構築点にも provider 注入経路を通す。
- **案 B (BGEM3FlagModel に process-level cache を持たせる)**: `FlagEmbeddingBgeM3Provider` で `(model, model_kwargs)` をキーにした module-level / class-level cache を実装し、同一設定なら同一 `_model` を返す。影響範囲が広い (全 construction 点に効く) が、test での mock/差し替えに注意。

案 A が影響範囲が局所的で安全。案 B は cold start を含む全経路に効くが、cache 不変条件 (model_kwargs 同一性) とテスト隔離の検証が要る。実装着手前に A/B を確定する (人間判断点)。

## 検証条件

- 本 TODO の instrument 手順 (BGEM3FlagModel 構築 wrap) で `spec-anchor core --rebuild` を実行し、構築回数が **1** になることを確認する。
- `pytest --skip-external` 回帰なし。
- METRICS で section_collection_upsert + related_sections の wall が短縮 (2 回目 load 分) されることを確認。

## 完了条件

1 回の `/spec-core` (all_pairs / retrieval_cap 両 mode) で BGE-M3 load が 1 回になり、`#9-s10` エビデンスを 1 回 load で更新、回帰なし。

## 依存 / scope 外

- 矛盾検出 section_pair 切り直し課題 (`TODO_conflict_detection_pipeline_simplify.ja.md`) とは独立。あちらは完了済み。
- `/spec-inject` 経路 (inject.py:586) の provider 構築は本 TODO の scope 外 (別コマンド)。
