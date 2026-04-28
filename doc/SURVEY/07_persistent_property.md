# 07: 恒久プロパティの node/relation metadata

> 状態: 未確認
> 最終更新: 2026-04-28

## 調査対象

DESIGN.ja.md §1.6 / TODO.md「恒久プロパティ vs transient annotation の境界」に従い、以下の **恒久プロパティ**が node / relation に乗るか確認する。

恒久プロパティの一覧:

- `document_id`
- `section_id`
- `heading_path`
- `source_span`
- `source_hash`
- `concept_id`
- `approval_status`
- `evidence`
- `created_at`
- `updated_at`

- component: `PropertyGraphIndex` node / relation の metadata 機構
- version / commit: _pending_
- source:
  - official docs: _pending fetch_
  - GitHub source: _pending fetch_
  - 実行確認: _pending spike/_

## 確認した API

- node metadata の付与 API: _pending_
- relation metadata の付与 API: _pending_
- metadata の retrieval（検索結果に含まれるか）: _pending_
- 永続化での metadata 保持: _pending_

## 実測・検証結果

- 上記 10 個の恒久プロパティを node / relation に書けるか: _pending_
- persist / reload で保持されるか: _pending_
- retrieval result に metadata が含まれるか: _pending_

## spec-grag への影響

- DESIGN §1.6 の恒久プロパティ表が成立するか:
- 表現できないプロパティがあれば代替手段（外部 sidecar JSON 等）の必要性:
- 未解決事項: _pending_

## 判定

unknown
