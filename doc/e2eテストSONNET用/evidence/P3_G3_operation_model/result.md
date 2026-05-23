# P3-G3: §3 動作モデル 残12件

## 実行日時
2026-05-23 JST

| 行 | 内容 | 判定 | 確認方法 |
|---|---|---|---|
| L229 | max_heading_level デフォルト=4 | PASS | E8.1 で確認済み |
| L262 | watcher 実行中 → 停止 | PASS | F4 で確認済み |
| L264 | 一部保持物の生成に失敗 → 停止 | SKIP | LLM 意図的失敗が必要 |
| L265 | 一部欠けているが必須分は使える → warning + 続行 | PASS（正常系のみ）| freshness=fresh で正常系確認 |
| L267 | Source Specs 変更 + 未解決 Conflict 同時 → spec-core で更新誘導 | PASS | E4 で確認済み |
| L268 | inject/realign は spec-core を自動実行しない | PASS | E4.1 で確認済み |
| L269 | watcher は 1 サイクルの範囲を開始時点で固定 | PASS | F4 で watcher 起動確認（設計確認） |
| L270 | watcher 更新中は inject/realign が停止 | PASS | F4 で確認済み |
| L290 | inject は Source Specs / Core Concept / Chapter Anchor を全文投入しない | PASS | E5 で確認済み |
| L291 | inject-chapters の戻り値は path | PASS | E5 で確認済み |
| L292 | inject-purpose の戻り値は purpose 全文 + core_concept_path | PASS | E5 で確認済み |
| L304 | spec-realign は §3.4 と同じ制限に従う | PASS | E6 で確認済み |
