# 03: SimplePropertyGraphStore 永続化粒度

> 状態: WebFetch ✓ / GitHub ☐ / Spike ☐ — 判定 **usable_with_wrapper**
> 最終更新: 2026-04-28

## 調査対象

- component: `llama_index.core.graph_stores.SimplePropertyGraphStore`
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: _pending fetch（`llama_index/core/graph_stores/simple_lpg.py` を後で確認）_
  - 実行確認: _pending spike/_

## 確認した API（WebFetch レベル）

- import path: `from llama_index.core.graph_stores import SimplePropertyGraphStore`
- delete:
  - `graph_store.delete(ids=['id1'])` — ID 指定
  - `graph_store.delete(properties={"key": "val"})` — **プロパティ指定削除**（章単位 stale 除去の鍵、項目 04 / 10）
- upsert:
  - `graph_store.upsert_nodes(entities)`
  - `graph_store.upsert_relations(relations)`
- persist: `index.storage_context.persist(persist_dir="./storage")`（StorageContext 経由）
- reload: `StorageContext.from_defaults(persist_dir="./storage")` + `load_index_from_storage`
- 永続化形式: **未確認**（pickle / JSON / parquet どれか、要 GitHub source 確認）

## 実測・検証結果

- 最小コードで動いたこと: _pending spike/_
- 動かなかったこと: _pending_

## spec-grag への影響

- 章別 vs 全体一括: **未確認**（永続化形式と関連）
  - 単一 store + section_id プロパティでフィルタする方式が現実的（`delete(properties={"section_id": "..."})` が動けば）
  - 章別 store 分割は spec-grag 側 orchestrator で対応する方式（複数 SimplePropertyGraphStore を CLI 側でマップ）も選択肢
- 永続化形式が human-readable（JSON）なら review 用途に有利、pickle なら debug 性が下がる
- 未解決事項:
  - 永続化ファイルが human-readable か（review / debug 用途、pickle vs JSON）
  - `delete(properties=...)` の正規挙動（unindexed property での全走査でも動くか / edge は連動して消えるか）
  - 並行アクセス（spec-grag は基本シングルプロセス想定なので問題は薄い）

## 判定

**usable_with_wrapper**（API 概要は確認、永続化形式と粒度は spike + GitHub source で実証）
