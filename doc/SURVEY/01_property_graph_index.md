# 01: PropertyGraphIndex の API 安定度

> 状態: WebFetch ✓ / GitHub ☐ / Spike ☐ — 判定 **usable_with_wrapper**（暫定、spike で昇格予定）
> 最終更新: 2026-04-28

## 調査対象

- component: `llama_index.core.indices.property_graph.PropertyGraphIndex`
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: _pending fetch（`llama_index/core/indices/property_graph/`）_
  - 実行確認: _pending spike/_

## 確認した API（WebFetch レベル）

- import path:
  - `from llama_index.core.indices.property_graph import PropertyGraphIndex` (推定。`from llama_index.core import PropertyGraphIndex` も spike で確認)
- constructor / factory:
  - `PropertyGraphIndex.from_documents(documents, kg_extractors=[...], property_graph_store=..., vector_store=..., embed_kg_nodes=True)`
  - `PropertyGraphIndex.from_existing(property_graph_store=..., vector_store=..., ...)`
- main methods:
  - `index.insert(document)` — 文書追加
  - `index.insert_nodes(nodes)` — ノード追加
- persist / reload:
  - `index.storage_context.persist(persist_dir="./storage")`
  - `StorageContext.from_defaults(persist_dir="./storage")` + `load_index_from_storage(storage_context)`
- delete / update（graph_store 経由、項目 03 / 04 と関連）:
  - `graph_store.delete(ids=[...])` / `graph_store.delete(properties={...})`
  - `graph_store.upsert_nodes(...)` / `graph_store.upsert_relations(...)`

## 実測・検証結果

- 最小コードで動いたこと: _pending spike/_
- 動かなかったこと: _pending_
- エラー: _pending_

## spec-grag への影響

- DESIGN §1.9 経路 1（incremental）/ 経路 2（--all）の API 上の前提は揃っている（WebFetch レベル）
- v0.14 系（0.14.21）が最新。breaking change 頻度は GitHub release notes で要確認
- 未解決事項:
  - PropertyGraphIndex.from_existing の永続化粒度（項目 03 / 04 と関連）
  - kg_extractors=[] (空 list) の挙動（**案 A: 外部抽出のみで extractor を使わない構成にできるか**）
  - vector_store=None の挙動（embed_kg_nodes=False で vector index を作らない構成）

## 判定

**usable_with_wrapper**（spike で実証後 usable に昇格予定）
