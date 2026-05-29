# #2-s08 禁止用語横断チェック

検証: `tests/e2e/test_user_facing_output.py::test_snapshot_has_no_forbidden_terms`

意味: #2-s01〜#2-s07 を含む全 user_facing スナップショットに対し、`tests/e2e/forbidden_terms.py`
の禁止用語 (内部 field 名 / freshness enum 値 / パイプライン段階名 / 制御 flag) が
1 つも含まれないことを pytest が横断的に保証する。これにより、停止時応答に
`should_stop` / `blocking_reasons` / `dirty_or_stale_source` / `pending_conflict` /
`retrieval_index` などの内部用語が漏出しないことが機械的に強制される。

禁止用語リストの単一の真実は `tests/e2e/forbidden_terms.py` であり、3 コマンドテンプレ
(`.claude/commands/spec-*.md`) の「ユーザー向け本文に貼ってはいけない内部用語」節と一致する。
