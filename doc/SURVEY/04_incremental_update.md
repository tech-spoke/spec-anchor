# 04: incremental update 方式

> 状態: WebFetch ✓ / GitHub ✓（simple_labelled.py 確認）/ Spike ☐ — 判定 **usable_with_wrapper**（要 spike 実証）
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

## 実測・検証結果

- 章単位 SHA-256 変更検出 → 影響範囲のみ再構築:
  - **API 上の path 確定**: spec-grag 側で `section_id` を node property として持たせ、変更章は `graph_store.delete(properties={"section_id": "<changed>"})` → 新規 entity を `upsert_nodes(...)` で再投入
  - 実測: pending（spike で実証必須）
- stale edge 除去:
  - `delete(properties={"section_id": "<changed>"})` で **node を消した時に紐付 edge も連動して消えるか**は要 spike 確認（最重要）
  - もし edge が残るなら、spec-grag 側で section_id を edge の properties にも書いて二重削除する必要あり
- 全体再構築のみが標準だった場合の workaround: 上記 API 構成で章単位 incremental が成立すれば不要

## spec-grag への影響

- DESIGN §1.9 経路 1（/spec-core incremental）の API 上の前提は **GitHub source レベルで成立**
- spec-grag 側の責務:
  - 章単位 SHA-256 計算
  - section_id 採番（恒久プロパティ、項目 07 と整合）
  - 章間 relation の整合性管理（変更章 → 他章へ MENTIONS された entity の取り扱い）
  - **node + edge 両方に section_id を property として書く**（edge 側も連動削除のため）
- 未解決事項:
  - `delete(properties={"section_id": ...})` で edge も連動削除されるか（**最重要、項目 10 と連携、spike 必須**）
  - upsert_nodes が同 ID で来た場合の merge 挙動（フィールド全置換か partial merge か）
  - SUPERSEDES / CONFLICTS_WITH 等の章をまたぐ edge の保持
  - dedup（同名 entity が複数章で登場する場合）

## 判定

**usable_with_wrapper** — API path は完全に揃っている、stale edge 連動削除の正確な挙動を spike で実証してから usable に昇格判定
