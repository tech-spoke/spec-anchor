# 09: /spec-core --all 全再構築の API 挙動

> 状態: Spike ✓（spike/02_property_graph_index.py STEP 6）— 判定 **usable**
> 最終更新: 2026-04-28

## 調査対象

DESIGN.ja.md §1.9 経路 2（全再構築）の API レベル動作確認。

- component: `PropertyGraphIndex` + `SimplePropertyGraphStore` + `SimpleVectorStore` の全破棄 / 再構築 path
- version / commit: llama-index-core **0.14.21**
- source:
  - 実行確認: [`spike/02_property_graph_index.py`](../../spike/02_property_graph_index.py) STEP 6

## 確認した API（spike 02 で実証）

```python
import os
import shutil

from llama_index.core import PropertyGraphIndex
from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.indices.property_graph import ImplicitPathExtractor
from llama_index.core.vector_stores.simple import SimpleVectorStore

PERSIST_DIR = "./spike_storage/02"

# 1. 既存 store の破棄
shutil.rmtree(PERSIST_DIR)
os.makedirs(PERSIST_DIR, exist_ok=True)

# 2. 新しい store を作成して案 A 投入（または LLM 抽出）
new_graph_store = SimplePropertyGraphStore()
new_vector_store = SimpleVectorStore()
new_graph_store.upsert_nodes(nodes)
new_graph_store.upsert_relations(rels)

# 3. PropertyGraphIndex.from_existing で再構築
new_index = PropertyGraphIndex.from_existing(
    property_graph_store=new_graph_store,
    vector_store=new_vector_store,
    embed_kg_nodes=False,
    kg_extractors=[ImplicitPathExtractor()],  # 項目 01 の落とし穴対策
)

# 4. persist
new_index.storage_context.persist(persist_dir=PERSIST_DIR)
```

## 実測・検証結果（spike 02 STEP 6）

- ✅ `shutil.rmtree(PERSIST_DIR)` で persist_dir 完全消去（exists=False）
- ✅ `os.makedirs(PERSIST_DIR)` で再作成
- ✅ 新 graph_store + 新 vector_store + 新 index で全再構築
- ✅ persist 後、6 ファイル生成（property_graph_store.json 1117 bytes ほか）
- ✅ nodes / triplets が再投入したデータと一致（nodes=3, triplets=2）

## spec-grag への影響

- DESIGN §1.9 経路 2（/spec-core --all）の Step 2「既存 graph store / chapter_index / concept_index を破棄（または別パスへバックアップ）」は **`shutil.rmtree(persist_dir)` + `os.makedirs` で実現可能**
- spec-grag CLI の責務:
  - --all 指定時: persist_dir のバックアップ作成（オプション）→ `shutil.rmtree(persist_dir)` → 新 graph_store 構築 → 案 A で全 entity/relation を投入 → `PropertyGraphIndex.from_existing` → persist
  - エラー時: バックアップから復元 or persist_dir 再作成して空 store にロールバック
- バックアップは spec-grag 側で `shutil.copytree(persist_dir, backup_dir)` で取れる（標準 Python）

## 判定

**usable**（spike で動作実証、Python 標準の OS 操作 + 案 A 投入で完結）
