# 10: /spec-core incremental stale 除去整合（最重要）

> 状態: WebFetch ✓ / GitHub ✓ / **Spike ✓**（spike/01_property_graph_basic.py）— 判定 **usable_with_wrapper**（safe delete wrapper 必須、設計確定）
> 最終更新: 2026-04-28

DESIGN.ja.md §1.9 経路 1 の核心。**項目 04 / 07 / 08 の結果と組み合わせて評価**する。

## 調査対象

- component: `PropertyGraphIndex` + `SimplePropertyGraphStore` の partial update + stale removal path
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: _pending fetch_
  - 実行確認: _pending spike/（最重要シナリオを実装予定）_

## 確認した API（WebFetch レベル）

- 章単位 stale 除去:
  - `graph_store.delete(properties={"section_id": "<changed_section>"})` ← node のプロパティで filter 削除（**章単位 stale 除去の鍵**）
  - `graph_store.delete(ids=[...])` ← spec-grag 側で section_id → node id の mapping を持っていれば使える
- 章単位再投入:
  - `graph_store.upsert_nodes(entities)` / `graph_store.upsert_relations(relations)`
- ID 衝突時の挙動: 未確認（upsert なので新値で上書き想定だが要 spike 確認）

## 最重要シナリオ（spike/01_property_graph_basic.py で実証済）

シナリオ:

```
1. 章 A / 章 B を初期投入 → persist (4 nodes / 3 triplets / 1741 bytes JSON)
2. reload で properties 完全保持（日本語 OK）
3. 【NG】 store.delete(properties={"section_id": "section_b"}) を呼ぶ
   → 章 A の user_authentication が DEPENDS_ON triplet で巻き込まれて削除される
   → triplets set に dangling reference が残り get_triplets() で KeyError
4. 【OK】 safe_delete_by_section(store, "section_b") を呼ぶ
   → 章 A 完全保存、章 B 完全消去、triplets 整合
5. user_session_v2 を upsert で正常投入
6. get_rel_map(depth=2) で traversal 動作確認
```

詳細は項目 [04 incremental_update](04_incremental_update.md) を参照。

## spec-grag への影響

- DESIGN §1.9 経路 1 Step 4-5 の「変更 Section の ChapterAnchor / Entity / Relation 更新」は **API 上は成立見込み**
- spec-grag 側で必要な制御:
  - 章 → section_id mapping（恒久プロパティ、項目 07）
  - 章間 relation の管理（CONFLICTS_WITH 等が章をまたぐ）
  - sidecar manifest（章別 entity ID 一覧）の必要性は spike 結果次第
- 未解決事項:
  - delete(properties=) で edge も削除されるか（**最重要**）
  - upsert_nodes が同 ID で来た場合の merge 挙動
  - section_id をまたぐ entity（同名 Concept が章 A / B 両方で言及される）の dedup

## 判定

**usable_with_wrapper** — safe_delete_by_section wrapper 必須、spike 01 で動作確認済、設計確定
