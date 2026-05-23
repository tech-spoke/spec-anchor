# P1-E3.1: Section 分割・source_section_id 形式検証

## 実行日時
2026-05-23 JST

## 確認方法
`/tmp/sa-test-sonnet-e3-q2iKl/.spec-anchor/state/section_manifest.json` を読んで全 section_id を検証

## 確認結果

### 全 section_id 一覧
```
docs/spec/sample.md#0001-sample-specification
docs/spec/sample.md#0002-authentication
docs/spec/sample.md#0003-authorization
docs/spec/sample.md#0004-session-termination
```

### 形式検証
- パターン `^.+#(\d{4})-[a-z0-9_ぁ-ん一-鿿]+$` への一致: **全4件 PASS**
- 形式違反: なし
- ordinal 4桁 zero-padded: True
- 最小 ordinal: `0001`（1始まり PASS）
- `max_heading_level=4` のデフォルト動作: sample.md に H5 以下の見出しなし（確認）

## 判定
**PASS — 全3項目**

| 確認項目 | 結果 |
|---|---|
| source_section_id の形式が `<file_path>#<ordinal>-<heading_slug>` | PASS |
| ordinal は1始まり 4桁 zero-padded | PASS |
| heading_slug の正規化ルール（英数字/アンダースコア保持、他を `-` に置換） | PASS（`sample-specification`, `authentication`, `authorization`, `session-termination`）|

## 対応する EXTERNAL_DESIGN の検証単位
§2.4 Section の source_section_id 形式定義の [ ] 行（L123〜L126）
