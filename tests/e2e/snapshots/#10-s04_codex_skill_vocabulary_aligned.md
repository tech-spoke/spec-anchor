# #10-s04 .codex/skills/spec-anchor/SKILL.md の語彙整理が最新と一致

検証: `tests/e2e/test_user_facing_output.py::test_codex_skill_has_user_facing_output_contract`

意味: Codex skill (`spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md`) に、Claude 版と
同じ語彙整理 — 停止カテゴリ写像 (6 + ◇ + ✕) / pending conflict の本文展開 /
答案なし呼び出しの自動再実行 / 構造化失敗時のリトライ / 正常完了フォーマット /
禁止用語リスト — が含まれることを pytest が確認する。Codex 不使用のため実行検証はせず、
記述の存在確認 (file 内容) のみ。
