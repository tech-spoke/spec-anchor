# P1-E6: /spec-realign CLI 部分

## 実行日時
2026-05-23 JST

## 注記
E6 の「Agent CLI が 4 区分構造を提示するか」は Agent CLI 出力の確認が必要なため別途実施。  
本証跡は CLI コマンドの戻り値構造を確認する部分のみ。

---

## realign --answer-json（4区分形式）

```bash
spec-anchor realign --answer-json '{
  "constraints": ["セッションは24時間で失効", "管理者はMFAが必須"],
  "targets": ["認証エンドポイント"],
  "uncertainty": [],
  "answer": "認証エンドポイントでセッションタイムアウトを24時間に設定し、管理者アカウントにはMFAを強制する。"
}'
```

```
status: fresh
answer フィールド存在: True
stop_reason: なし
answer keys: ['今回守る制約', '今回扱う修正候補または検討対象', '競合 / 不確実性 / 人間レビューが必要な点', '課題プロンプトへの回答または修正案']
exit: 0
```

4 区分の RealignResult に整形されて返る。CLI は回答本文を独自生成しない。

### 注意: answer JSON の必須フィールド
`--answer-json` に渡す JSON には `answer` / `final_answer` / `proposal` のいずれかが必須。  
これらが欠けると `structure_realign_answer` が `SpecRealignError` を throw し、`needs_agent_answer` が返る。  
（`{"summary":"...","constraints":[...]}` だけでは不十分）

---

## realign なし（needs_agent_answer）

```bash
spec-anchor realign
```

```
status: fresh
stop_reason: needs_agent_answer
should_stop: True
answer フィールド存在: False
error フィールド存在: False
exit: 0
```

`--answer-json` なしの場合、`stop_reason="needs_agent_answer"`, `should_stop=True` を返す（例外として raise しない）。

---

## 判定
**PASS（CLI 部分 3 項目）**

| 確認項目 | 結果 |
|---|---|
| realign --answer-json（4区分形式）で `answer` フィールドに 4 区分が返る | PASS |
| CLI は回答本文を独自生成しない（Agent 渡しの JSON を整形するのみ） | PASS |
| realign なしで `stop_reason="needs_agent_answer"`, `should_stop=True` | PASS |

Agent CLI 側の 4 区分構造確認: 未実施（E6-Agent として別途実施予定）

## 対応する EXTERNAL_DESIGN の検証単位
§9.4 CLI フラグ / §9.1 `needs_agent_answer` 経路
