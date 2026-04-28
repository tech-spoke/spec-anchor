# 10: /spec-core incremental stale 除去整合（最重要）

> 状態: WebFetch ✓ / GitHub ☐ / Spike ☐ — 判定 **usable_with_wrapper（暫定）**
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

## 最重要シナリオ（spike で実装予定）

```
1. 章 A / B / C を初期投入 → persist
2. 章 B のみ修正（旧 entity X を削除、新 entity Y を追加）
3. 章 B の旧 entity X / relation が graph から消える
4. 章 A / C の状態は変化しない
5. 章 A から X への MENTIONS edge があった場合の挙動
```

→ Phase 0.5 spike で実証（spike/02_incremental_stale.py 等）

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

**usable_with_wrapper（暫定）** — API path は揃っているが、stale edge 削除の正確な挙動を spike 実装で実証してから昇格判定
