# 09: /spec-core --all 全再構築の API 挙動

> 状態: 未確認
> 最終更新: 2026-04-28

## 調査対象

DESIGN.ja.md §1.9 経路 2（全再構築）の API レベルでの実現方式を確認する。

- component: `PropertyGraphIndex` + `SimplePropertyGraphStore` の全破棄 / 再構築 path
- version / commit: _pending_
- source:
  - official docs: _pending fetch_
  - GitHub source: _pending fetch_
  - 実行確認: _pending spike/_

## 確認した API

- 既存 graph store の破棄 API: _pending_
- 別パスへのバックアップ / atomic switchover: _pending_
- 上書き挙動（同じ persist path への persist）: _pending_
- 冪等性（同じ入力 → 同じ出力 path / state）: _pending_

## 実測・検証結果

- toy 構成での全再構築シーケンス（破棄 → 再構築 → persist）: _pending_
- バックアップを取ってから再構築する手順の確立: _pending_
- 失敗時のロールバック可否: _pending_

## spec-grag への影響

- DESIGN §1.9 経路 2 の Step 2「既存 graph store / chapter_index / concept_index を破棄（または別パスへバックアップ）」の実装パターン:
- 章別 store 分割（項目 03 と関連）が必要なら、再構築の単位も変わる:
- 未解決事項: _pending_

## 判定

unknown
