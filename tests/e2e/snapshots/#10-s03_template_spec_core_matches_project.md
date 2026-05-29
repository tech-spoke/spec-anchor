# #10-s03 setup-project 直後の .claude/commands/spec-core.md がテンプレ版と一致

検証: `tests/e2e/test_user_facing_output.py::test_template_command_matches_project[spec-core.md]`

意味: `spec_anchor/templates/.claude/commands/spec-core.md` (install skeleton) と
プロジェクト直下 `.claude/commands/spec-core.md` がバイト一致することを pytest が保証する。
これにより、新規プロジェクトで `spec-anchor-setup-project` を実行した直後の
`.claude/commands/spec-core.md` に、#2〜#8 で更新した停止時・正常完了フォーマットと
禁止用語リストがそのまま配布される。
