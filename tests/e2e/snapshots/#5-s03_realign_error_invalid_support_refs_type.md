# #5-s03 realign CLI error 詳細 (support_refs 型違反)

意味: #5 は `spec-anchor realign` が回答候補の形式不備を **field 単位** で返すことを確認する。
CLI は run_spec_realign の dict をそのまま stdout へ出すので、ここでは inject_result を
省いた CLI 出力 (status + error block) を示す。error block の code / field / expected /
actual を Agent が読み、該当 field だけ直して再実行できる (#6 リトライの前提)。

実 CLI 出力 (inject_result 省略):

```json
{
  "blocked": true,
  "blocking_reasons": [],
  "can_continue": false,
  "command": "/spec-realign",
  "constraints": [],
  "error": {
    "actual": "str",
    "code": "invalid_support_refs_type",
    "expected": "list",
    "field": "constraints[0].support_refs",
    "message": "constraint support_refs must be a list"
  },
  "freshness_report": {
    "blocking_reasons": [],
    "status": "fresh",
    "warnings": []
  },
  "generated_at": "2026-05-29T00:00:00Z",
  "project_root": "/tmp/claude-1001/tmp6wr4xkyu/project",
  "recommended_next_action": "repair the reported answer field and re-run spec-anchor realign",
  "should_stop": true,
  "status": "error",
  "stops": true,
  "warnings": []
}
```
