# #8-s07 正常完了系の禁止用語チェック

検証: `tests/e2e/test_user_facing_output.py::test_snapshot_has_no_forbidden_terms`

意味: #8-s01〜#8-s06 を含む全 user_facing スナップショットに対し、正常完了系の内部 field 名
(updated_sources / failed_sources / retrieval_index_status / stale_resolution_count /
unreflected_conflict_resolutions 等) と enum 値 (status="dismissed" / severity 生表示) が
含まれないことを pytest が横断的に保証する。これらは `tests/e2e/forbidden_terms.py` の
禁止用語に含まれており、3 コマンドテンプレの「ユーザー向け本文に貼ってはいけない内部用語」節と一致する。
