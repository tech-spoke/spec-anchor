# #5-s04 realign CLI error 詳細 (正常答案)

意味: #5 は `spec-anchor realign` が回答候補の形式不備を **field 単位** で返すことを確認する。
CLI は run_spec_realign の dict をそのまま stdout へ出すので、ここでは inject_result を
省いた CLI 出力 (status + error block) を示す。error block の code / field / expected /
actual を Agent が読み、該当 field だけ直して再実行できる (#6 リトライの前提)。

実 CLI 出力 (inject_result 省略):

```json
{
  "answer": {
    "今回守る制約": [
      {
        "applicability": "guard 実装",
        "evidence_origin": "Source Specs",
        "evidence_ref": "docs/spec/security.md#authentication",
        "statement": "validate session",
        "support_refs": [],
        "uncertainty": []
      }
    ],
    "今回扱う修正候補または検討対象": [
      "guard 追加"
    ],
    "競合 / 不確実性 / 人間レビューが必要な点": [],
    "課題プロンプトへの回答または修正案": "active session を検証する。"
  },
  "blocked": false,
  "blocking_reasons": [],
  "can_continue": true,
  "command": "/spec-realign",
  "freshness_report": {
    "blocking_reasons": [],
    "status": "fresh",
    "warnings": []
  },
  "generated_at": "2026-05-29T00:00:00Z",
  "labels": {
    "answer": "課題プロンプトへの回答または修正案",
    "constraints": "今回守る制約",
    "review": "競合 / 不確実性 / 人間レビューが必要な点",
    "targets": "今回扱う修正候補または検討対象"
  },
  "project_root": "/tmp/claude-1001/tmp2dg42kpl/project",
  "realign_answer": {
    "今回守る制約": [
      {
        "applicability": "guard 実装",
        "evidence_origin": "Source Specs",
        "evidence_ref": "docs/spec/security.md#authentication",
        "statement": "validate session",
        "support_refs": [],
        "uncertainty": []
      }
    ],
    "今回扱う修正候補または検討対象": [
      "guard 追加"
    ],
    "競合 / 不確実性 / 人間レビューが必要な点": [],
    "課題プロンプトへの回答または修正案": "active session を検証する。"
  },
  "recommended_next_action": "continue /spec-inject",
  "should_stop": false,
  "status": "fresh",
  "stops": false,
  "warnings": []
}
```
