# 04: incremental update 方式

> 状態: WebFetch ✓ / GitHub ☐ / Spike ☐ — 判定 **usable_with_wrapper**（暫定、要 spike 実証）
> 最終更新: 2026-04-28

## 調査対象

- component: `PropertyGraphIndex` + `SimplePropertyGraphStore` の incremental update path
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: _pending fetch_
  - 実行確認: _pending spike/_

## 確認した API（WebFetch レベル）

- 既存 index への追加: `index.insert(document)` / `index.insert_nodes(nodes)`
- 既存ノード更新: `graph_store.upsert_nodes(entities)`（同 ID で上書きする想定だが要 spike 実測）
- 既存ノード削除:
  - `graph_store.delete(ids=[...])`
  - `graph_store.delete(properties={...})` ← **章単位 stale 除去の中核**
- 既存リレーション更新: `graph_store.upsert_relations(relations)`
- ID 衝突 / dedupe の挙動: **未確認**（spike で実測）

## 実測・検証結果

- 章単位 SHA-256 変更検出 → 影響範囲のみ再構築:
  - **API 上の path 候補**: spec-grag 側で section_id を node property として持たせ、変更章は `graph_store.delete(properties={"section_id": "<changed>"})` → 新規 entity を `upsert_nodes(...)` で再投入
  - 実測: pending
- stale edge 除去:
  - `delete(properties={"section_id": "<changed>"})` で section_id 紐付の edge も削除されるか、それとも node のみで edge は残るか → spike で確認必須
- 全体再構築のみが標準だった場合の workaround: 上記 API 構成で章単位 incremental が成立すれば不要

## spec-grag への影響

- DESIGN §1.9 経路 1（/spec-core incremental）の前提が API 上は成立する見込み（WebFetch レベル）
- spec-grag 側の責務:
  - 章単位 SHA-256 計算
  - section_id 採番（恒久プロパティ、項目 07 と整合）
  - 章間 relation の整合性管理（変更章 → 他章へ MENTIONS された entity の取り扱い）
- 未解決事項:
  - delete(properties=) で edge 側もカスケード削除されるか（**最重要、項目 10 と連携**）
  - SUPERSEDES / CONFLICTS_WITH 等の章をまたぐ edge の保持
  - dedup（同名 entity が複数章で登場する場合）

## 判定

**usable_with_wrapper**（API path は揃っているが、stale edge 削除の正確な挙動は spike で実証必須）
