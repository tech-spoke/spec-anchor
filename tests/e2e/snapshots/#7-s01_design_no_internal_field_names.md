# #7-s01 §8.7 本文に内部 field 名 / enum 値が含まれない

検証: `tests/e2e/test_user_facing_output.py::test_external_design_8_7_has_no_internal_field_names`

意味: 外部設計書 `doc/EXTERNAL_DESIGN.ja.md` の新設節 §8.7「人間向け表示契約」が、
CLAUDE.md ルール 14 に従い、`should_stop` / `blocking_reasons` / `dirty_or_stale_source` /
`pending_conflict` などの CLI 内部 field 名・enum 値を使わず、利用者体感の言葉で
停止時・正常完了時・リトライの表示契約を記述していることを `forbidden_terms` で確認する。
