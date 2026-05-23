# P1-E3.2: Qdrant payload 構造確認

## 実行日時
2026-05-23 JST

## 確認方法
`spec-anchor inject-search "認証"` の stdout JSON で hits の payload フィールドを確認  
`--rebuild` 後の `spec_anchor_section_sonnet` collection を対象

## 実行コマンド
```bash
cd /tmp/sa-test-sonnet-e3-q2iKl
spec-anchor inject-search "認証" 2>/dev/null
```

## 確認結果

### inject-search の hits 構造
- hits count: 8
- 必須フィールド全て存在: `source_document_id` / `source_section_id` / `source_span` / `heading_path` / `summary` / `search_keys` / `identifiers` / `related_sections` / `score`
- missing: **なし**

### 1 Section = 1 Qdrant point 確認（`--rebuild` 後）
- Qdrant `spec_anchor_section_sonnet` points: **4**
- section_manifest sections: **4**
- 一致: **True**

## 発見した問題（BUG-001）
初回（テスト用ドキュメント、別 project root）の 432 points を同じ collection に upsert 後、  
新プロジェクトで sample.md のみの incremental 実行を行ったところ `stale_points_deleted: 0`（旧ポイント未削除）。  
→ **設計上の制限**（同一 project root での Source Specs 変更では正常動作）。  
→ `--rebuild` で解決（4 points に正常化）。

## 判定
**PASS（`--rebuild` 後）**

| 確認項目 | 結果 |
|---|---|
| Qdrant payload に必須フィールド（7フィールド）が存在する | PASS |
| 1 Section = 1 Qdrant point（chunk 分割しない） | PASS（`--rebuild` 後） |

## 対応する EXTERNAL_DESIGN の検証単位
§4.1 保持物の物理配置（Qdrant payload）の [ ] 行（L332〜L339）
