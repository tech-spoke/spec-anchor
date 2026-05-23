# P1-E4: freshness gate

## 実行日時
2026-05-23 JST

## 実行環境
- tmp project root: `/tmp/sa-test-sonnet-e3-q2iKl`
- Source Specs: `docs/spec/sample.md`

---

## E4.1: Source Specs 変更後の停止

### 手順
1. `/spec-core` 実行済み（freshness.status=fresh）
2. `docs/spec/sample.md` に空行を追加（変更）
3. `spec-anchor inject-search "認証"` 実行

### 結果
```json
{
  "status": "blocked",
  "should_stop": true,
  "blocked": true,
  "can_continue": false,
  "blocking_reasons": ["dirty_or_stale_source"],
  "recommended_next_action": "run /spec-core before /spec-inject"
}
exit: 0
```

### /spec-core 後に続行することを確認
```
spec-core status: updated, freshness_report.status: fresh
inject-search 再実行: should_stop=False, hits count=4
exit: 0
```

---

## E4.2: pending conflict での停止

### 手順
1. `conflict_review_items.json` に `status=pending` の conflict を 1 件作成
2. `freshness.json` を `status=blocked`, `blocking_reasons=["pending_conflict"]` に書き換え
3. `spec-anchor inject-search "認証"` 実行

### 結果
```json
{
  "status": "blocked",
  "should_stop": true,
  "blocking_reasons": ["pending_conflict"],
  "pending_conflict_items": [
    {
      "conflict_id": "cnf_test_001",
      "severity": "high",
      "decision_options": ["prefer_a", "prefer_b", "dismiss", "defer"],
      "recommended_next_action": "Ask a human to decide this conflict."
    }
  ]
}
exit: 0
```

### テスト後の fixture 復元
- `conflict_review_items.json` を空配列に戻した
- `/spec-core` を再実行し `freshness_report.status=fresh` を確認

---

## 判定
**PASS — 全6項目**

| 確認項目 | 結果 |
|---|---|
| Source Specs 変更後に inject-search が `status=blocked`, `blocking_reasons=["dirty_or_stale_source"]`, `should_stop=true` で停止 | PASS |
| `can_continue=false` | PASS |
| `recommended_next_action` に `"run /spec-core before /spec-inject"` が含まれる | PASS |
| exit code 0 | PASS |
| `/spec-core` 実行後に inject-search が続行する（`should_stop=False`, hits あり） | PASS |
| `blocking_reasons=["pending_conflict"]` で `pending_conflict_items` が提示される | PASS |

## 対応する EXTERNAL_DESIGN の検証単位
§3.3 保持物の鮮度 / §11.1.5 エラー契約（freshness gate 行）
