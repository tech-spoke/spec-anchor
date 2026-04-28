# 01: PropertyGraphIndex の API 安定度

> 状態: WebFetch ✓ / GitHub ✓ / **Spike ✓**（spike/02_property_graph_index.py）— 判定 **usable_with_caveat**
> 最終更新: 2026-04-28

## 調査対象

- component: `llama_index.core.indices.property_graph.PropertyGraphIndex`
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: `llama-index-core/llama_index/core/indices/property_graph/base.py`
  - 実行確認: [`spike/02_property_graph_index.py`](../../spike/02_property_graph_index.py)

## 確認した API（GitHub source レベル）

- import path: `from llama_index.core import PropertyGraphIndex`
- factory:
  - `PropertyGraphIndex.from_documents(documents, kg_extractors=[...], property_graph_store=..., vector_store=..., embed_kg_nodes=True)`
  - `PropertyGraphIndex.from_existing(property_graph_store=..., vector_store=..., kg_extractors=..., embed_kg_nodes=True, ...)`
- main methods:
  - `index.insert(document)` — 文書追加
  - `index.insert_nodes(nodes)` — ノード追加
- persist / reload:
  - persist: `index.storage_context.persist(persist_dir="./storage")`
  - reload (graph_store 単独): `SimplePropertyGraphStore.from_persist_dir(persist_dir)`
  - reload (index 全体): `StorageContext.from_defaults(persist_dir=...)` + `load_index_from_storage(storage_ctx)` ← **LLM 解決を要求するため spec-grag 運用では使わない**

## ⚠️ 重要な落とし穴（spike 02 で実証）

### 落とし穴 1: `kg_extractors=None` または `kg_extractors=[]` で LLM 解決が走る

`PropertyGraphIndex.__init__` は以下のコードで extractor を初期化（base.py 124-127 行）:

```python
self._kg_extractors = kg_extractors or [
    SimpleLLMPathExtractor(llm=llm or Settings.llm),
    ImplicitPathExtractor(),
]
```

**`kg_extractors or [...]` の `or` で空 list `[]` も falsy 扱い**され、default の `[SimpleLLMPathExtractor, ImplicitPathExtractor]` が代入される。`SimpleLLMPathExtractor(llm=llm or Settings.llm)` で `Settings.llm` が解決されるが、`llama-index-llms-openai` 未インストールの場合 `ImportError`。

**spec-grag の対処**: `kg_extractors=[ImplicitPathExtractor()]` を渡す（LLM 不要、truthy なので default 生成を回避、案 A の精神とも整合）。

```python
from llama_index.core.indices.property_graph import ImplicitPathExtractor

index = PropertyGraphIndex.from_existing(
    property_graph_store=graph_store,
    vector_store=vector_store,
    embed_kg_nodes=False,
    kg_extractors=[ImplicitPathExtractor()],  # ★ 案 A、LLM 解決回避
)
```

### 落とし穴 2: `load_index_from_storage` は LLM を要求

`load_index_from_storage(storage_ctx)` は内部で `PropertyGraphIndex.__init__` を再度呼ぶため、上記と同じ理由で LLM 解決が走り、未インストールなら `ImportError`。

**spec-grag の対処**: PropertyGraphIndex オブジェクトを永続化された塊として再ロードしない。代わりに毎セッションで:

1. `graph_store = SimplePropertyGraphStore.from_persist_dir(persist_dir)` で graph_store のみ単独 reload
2. `PropertyGraphIndex.from_existing(property_graph_store=graph_store, ..., kg_extractors=[ImplicitPathExtractor()])` で再構築

PropertyGraphIndex は薄いラッパなので、毎回作り直しても問題ない（永続化される本体は graph_store / vector_store / docstore のみ）。

## persist で生成されるファイル（spike 02 観察）

```
spike_storage/02/
├── property_graph_store.json   1117 bytes  ← spec-grag が使う本体
├── default__vector_store.json    72 bytes  ← VectorStore（embedding なしなら空）
├── image__vector_store.json      72 bytes
├── graph_store.json              18 bytes  ← 旧 KG store（property_graph と別）
├── docstore.json                  2 bytes
├── index_store.json             181 bytes
```

spec-grag は `property_graph_store.json` を主体にし、他はサイドカーとして扱う。

## 実測・検証結果（spike 02）

- ✅ `Settings.embed_model = OllamaEmbedding(...)` 注入 OK
- ✅ `PropertyGraphIndex.from_existing(kg_extractors=[ImplicitPathExtractor()])` 構築 OK
- ✅ `index.storage_context.persist(persist_dir=...)` 動作、6 ファイル生成
- ✅ `SimplePropertyGraphStore.from_persist_dir(...)` で graph_store 単独 reload OK
- ❌ `load_index_from_storage(storage_ctx)` は `Settings.llm` 解決で ImportError（spec-grag 運用では使わない）
- ✅ `shutil.rmtree(persist_dir)` + 新 store + 新 index 構築 + persist の全再構築シナリオ動作

## spec-grag への影響

- DESIGN §1.9 経路 1 / 経路 2 / 経路 3 / 経路 4 すべて、PropertyGraphIndex は **runtime に毎回 `from_existing` で再構築する** 設計が必要
- spec-grag CLI の責務:
  - 起動時: `SimplePropertyGraphStore.from_persist_dir` で reload → `PropertyGraphIndex.from_existing(graph_store, vector_store, kg_extractors=[ImplicitPathExtractor()])` で構築
  - 終了時: `index.storage_context.persist(persist_dir)`
- DESIGN §1.4 採用候補スタックに以下を追記する想定:
  - 「`PropertyGraphIndex` は永続化される塊ではなく、graph_store / vector_store の薄いラッパとして毎回構築する」
  - 「`kg_extractors=[ImplicitPathExtractor()]` を必須引数として渡す（案 A の運用上の前提）」
- 未解決事項:
  - v0.14 系の breaking change 頻度（GitHub release notes 未確認）

## 判定

**usable_with_caveat** — 動作確認 OK、ただし spec-grag は次の運用ルールを守る必要あり：

1. `kg_extractors=[ImplicitPathExtractor()]` を必ず渡す（空 list NG）
2. `load_index_from_storage` を使わない（graph_store 単独 reload + 毎回再構築）
