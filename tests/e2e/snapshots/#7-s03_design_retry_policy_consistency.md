# #7-s03 §8.7 のリトライポリシーが #6 と整合

検証: `tests/e2e/test_user_facing_output.py::test_external_design_8_7_describes_retry_policy`

意味: §8.7.4 が #6 のテンプレ手順 (項目単位の不備指摘 → 該当項目だけ修正 → 1 回だけ再実行 →
再失敗で ⑥ として最後の答案と差分を併記) と整合する記述になっていることを確認する。
