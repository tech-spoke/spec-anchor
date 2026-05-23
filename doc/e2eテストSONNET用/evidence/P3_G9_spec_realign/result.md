# P3-G9: §9 /spec-realign 詳細確認

## 実行日時
2026-05-23 JST

---

## 残 [ ] 4件（sub-step code block）の確認

G9 範囲（L951-L1003）のほとんどは E6_cli / E6_agent で既に ✅ 済み。
残りは `/spec-realign` の手順 code block 内の 4 sub-items。

### freshness gate (§3.3 と同じ判定で blocked / failed なら停止)

実機確認:
```python
# freshness を status=blocked, blocking_reasons=["dirty_or_stale_source"] に書き換え
spec-anchor realign --answer-json '{"constraints":[],...,"answer":"test"}'
→ status=blocked, should_stop=True, blocking_reasons=["dirty_or_stale_source"]
```
**PASS** — realign が freshness gate で停止する

### 8.3 と同じ手順で制約を生成する
E6_agent で確認: inject-search → inject-section の呼び出しと constraints 生成（4 path Agentic Search）  
**PASS**

### 生成した制約に従って回答または修正案を作る
E6_agent で確認: 4 件の constraints（Source Specs 根拠付き）を生成した後、制約に従った回答を提示。制約と回答の整合を確認。  
**PASS**

### RealignResult を出力する
E6_cli で確認: RealignResult の `answer` フィールドに 4 区分が存在:
```
'今回守る制約', '今回扱う修正候補または検討対象', '競合 / 不確実性 / 人間レビューが必要な点', '課題プロンプトへの回答または修正案'
```
**PASS**

---

## 判定
**PASS 8件 / SKIP 0件**

| 残 [ ] 項目 | 判定 | 確認方法 |
|---|---|---|
| freshness gate | PASS | 実機: freshness=blocked で realign が should_stop=True を返す |
| 8.3 と同じ手順で制約を生成する | PASS | E6_agent: 4 path Agentic Search + constraints 生成 |
| 生成した制約に従って回答を作る | PASS | E6_agent: 制約根拠と回答の整合確認 |
| RealignResult を出力する | PASS | E6_cli: 4 区分 RealignResult |
| /spec-realign の出力は「制約セット + 回答/修正案」 | PASS | E6_agent（既 ✅） |
| 中心課題を特定できない場合は停止 | PASS | E6_cli（既 ✅、needs_agent_answer） |
| realign CLI は会話区間を受け取らない | PASS | E6_cli（既 ✅） |
| /spec-realign 実行の trace 監査 | PASS | E6_agent（既 ✅） |

対応 EXTERNAL_DESIGN: §9 全体 L951〜L1003
