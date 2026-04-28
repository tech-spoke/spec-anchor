# 07: 恒久プロパティの node/relation metadata

> 状態: WebFetch ✓ / GitHub ✓（simple_labelled.py 確認、types.py は要追加 fetch）/ Spike ☐
> 判定 **usable_with_wrapper**（spike で persist 後の保持を実証）
> 最終更新: 2026-04-28

## 調査対象

DESIGN.ja.md §1.6 / TODO.md「恒久プロパティ vs transient annotation の境界」に従い、以下の **恒久プロパティ**が node / relation に乗るか確認する。

恒久プロパティ:

- `document_id` / `section_id` / `heading_path` / `source_span` / `source_hash` / `concept_id` / `approval_status` / `evidence` / `created_at` / `updated_at`

- component: `llama_index.core.graph_stores.types` の `LabelledNode` / `EntityNode` / `Relation`
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: `llama-index-core/llama_index/core/graph_stores/{simple_labelled,types}.py`
  - 実行確認: _pending spike/_

## 確認した API（GitHub source レベル、simple_labelled.py から推定）

- `LabelledNode.properties: dict` ← **free-form dict** として恒久プロパティを書ける
- `EntityNode` / `Relation` も `properties` を持つ（`upsert_nodes(nodes: Sequence[LabelledNode])` の引数型から推定）
- filter 対応:
  - `graph_store.get(properties={"section_id": "..."})` で properties 値で取得
  - `graph_store.delete(properties={"section_id": "..."})` で properties 値で削除
  - `graph_store.get_triplets(properties={...})` で同上

## 想定マッピング

| 恒久プロパティ | 保持先 | 注記 |
|---|---|---|
| `document_id` | node `properties` | spec-grag 側で採番、`Document` ノード id と紐付け |
| `section_id` | node `properties` + edge `properties` | **edge にも書く**（章単位 stale 除去で edge 連動削除のため、項目 04 / 10）|
| `heading_path` | node `properties` | "1 / 2.3 / 概要" のような path 文字列 |
| `source_span` | node `properties` | `[26:1263-1289]` 形式（spec-grag DESIGN §2.1）|
| `source_hash` | node `properties` | SHA-256 of source span（変更検出） |
| `concept_id` | node `properties` | `Concept` ノードの永続 id |
| `approval_status` | node `properties` | "approved" / "pending" / "rejected" |
| `evidence` | node `properties` | source span / SourceSpan ノードへの参照 |
| `created_at` / `updated_at` | node `properties` | ISO8601 timestamp |

## 実測・検証結果

- 上記 10 個の恒久プロパティを node / relation に書けるか: API 構造的には **free-form dict なので可能**（要 spike で実測）
- persist / reload で保持されるか: JSON 永続化（`to_dict()` / `from_dict()`）の対象に properties が含まれるかを spike で実測
- retrieval result（`NodeWithScore`）に metadata が含まれるか: BasePGRetriever の `_get_nodes_with_score` から推定で含まれる、spike で実測

## spec-grag への影響

- DESIGN §1.6 の恒久プロパティ表は API レベルで成立する見込み
- spec-grag 側の運用:
  - すべての node / relation に section_id を書く（edge 連動削除のため、項目 04 と整合）
  - approval_status は CLI / Orchestrator 側で書き換え（Concept 承認時に pending → approved）
  - source_hash は変更検出の核（章 SHA-256）
- 未解決事項:
  - persist で properties dict 全体が JSON にシリアライズされるか（特に nested dict / 日本語）
  - retrieval result に properties がそのまま乗るか、include_text / include_properties オプションで制御するか
  - properties に書ける値の型制約（str / int / list / dict / None）→ types.py 要確認

## 判定

**usable_with_wrapper**（API 構造的に成立、persist 後の properties 保持と retrieval result への伝播は spike で実証）
