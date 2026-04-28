# 04: incremental update 方式

> 状態: WebFetch ✓ / GitHub ✓ / **Spike ✓** — 判定 **usable_with_wrapper**（safe delete wrapper 必須、設計確定）
> 最終更新: 2026-04-28

## 調査対象

- component: `PropertyGraphIndex` + `SimplePropertyGraphStore` の incremental update path
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: `llama-index-core/llama_index/core/graph_stores/simple_labelled.py`
  - 実行確認: _pending spike/_

## 確認した API（GitHub source レベル）

- 既存 index への追加:
  - `index.insert(document)` / `index.insert_nodes(nodes)`
- 既存ノード / リレーション更新:
  - `graph_store.upsert_nodes(nodes: Sequence[LabelledNode])` ← 同 ID で上書きする想定（add_node の挙動次第、要 spike）
  - `graph_store.upsert_relations(relations: List[Relation])`
- 削除（**多軸 filter**）:
  ```python
  graph_store.delete(
      entity_names=None,    # entity 名（id）でフィルタ
      relation_names=None,  # relation 名（id）でフィルタ
      properties=None,      # ★ section_id 等のプロパティでフィルタ
      ids=None,             # node id でフィルタ
  )
  ```
- ID 衝突 / dedupe の挙動: 未確認（要 spike）

## 実測・検証結果（spike/01_property_graph_basic.py で実証）

### 【NG】 LlamaIndex 標準 `store.delete(properties={...})` は破綻する

`SimplePropertyGraphStore.delete` の実装（simple_labelled.py）:

```python
def delete(self, ..., properties=None, ids=None):
    triplets = self.get_triplets(properties=properties, ids=ids, ...)
    for triplet in triplets:
        self.graph.delete_triplet(triplet)  # ← subj/obj まで消す
    nodes = self.get(properties=properties, ids=ids)
    for node in nodes:
        self.graph.delete_node(node)
```

`delete_triplet` の中身（types.py）:

```python
def delete_triplet(self, triplet):
    subj, rel, obj = triplet
    self.triplets.remove((subj.id, rel.id, obj.id))
    if subj.id in self.nodes: del self.nodes[subj.id]   # subj 削除
    if obj.id in self.nodes:  del self.nodes[obj.id]    # ★ obj まで削除
```

**spike 結果**: 章 B 削除時に、章 B の `user_session` が章 A の `user_authentication` と DEPENDS_ON edge を持っていたため、**章 A の `user_authentication` が巻き込まれて削除された**。さらに triplets set に dangling reference が残り、`get_triplets()` で KeyError。

### 【OK】 spec-grag 推奨: safe_delete_by_section（to_dict → filter → from_dict）

```python
def safe_delete_by_section(store, section_id):
    data = store.graph.model_dump()
    raw_nodes, raw_relations, raw_triplets = data["nodes"], data["relations"], data["triplets"]

    kept_nodes = {nid: nd for nid, nd in raw_nodes.items()
                  if (nd.get("properties") or {}).get("section_id") != section_id}
    kept_node_ids = set(kept_nodes.keys())
    kept_relations = {rk: rd for rk, rd in raw_relations.items()
                      if (rd.get("properties") or {}).get("section_id") != section_id}
    kept_triplets = set()
    for subj_id, rel_id, obj_id in raw_triplets:
        if subj_id not in kept_node_ids: continue
        if obj_id not in kept_node_ids: continue
        if f"{subj_id}_{rel_id}_{obj_id}" not in kept_relations: continue
        kept_triplets.add((subj_id, rel_id, obj_id))

    return SimplePropertyGraphStore.from_dict({
        "nodes": kept_nodes,
        "relations": kept_relations,
        "triplets": kept_triplets,
    })
```

**spike 結果**: 章 A 完全保存（user_authentication / oauth2_required 残存）、章 B 完全消去、triplets 整合（残存 1 個 = 章 A 由来 CONSTRAINS）、その後 user_session_v2 を upsert で正常追加可能。

### 全体再構築のみが標準だった場合の workaround

不要。safe_delete_by_section + upsert で章単位 incremental が成立。

## spec-grag への影響（spike 01 後の確定版）

- DESIGN §1.9 経路 1（/spec-core incremental）は **safe_delete_by_section wrapper 経由で成立**（spike 01 で実証）
- spec-grag 側の責務:
  - 章単位 SHA-256 計算
  - section_id 採番（恒久プロパティ、項目 07 と整合）
  - **node + edge 両方の properties に section_id を書く**（safe_delete が edge も section_id でフィルタするため）
  - **safe_delete_by_section wrapper の実装**（spike 01 で動作確認済）
  - 章をまたぐ relation（DEPENDS_ON / CONSTRAINS / SUPERSEDES / CONFLICTS_WITH）の整合性管理
- DESIGN.ja.md §1.9 経路 1 / §1.4 採用候補スタックへの追記:
  - 「LlamaIndex 標準 `store.delete()` は破綻するため、spec-grag 側で safe_delete_by_section を実装する」
- 未解決事項:
  - upsert_nodes が同 ID で来た場合の merge 挙動（フィールド全置換と推定、別 spike で実証）
  - dedup（同名 entity が複数章で登場する場合）— spec-grag は name に section_id prefix を付けない素朴設計だと entity_id 衝突の可能性

## 判定

**usable_with_wrapper** — safe_delete_by_section wrapper 必須、wrapper は spike 01 で動作実証済、設計確定
