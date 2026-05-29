# #13-s01 pending conflict 系 snapshot で `recommended_next_action` が日本語訳されている

CLI 側 `spec_anchor/conflict_review.py:480, 635` で `recommended_next_action` の default 値が英語固定文 `Ask a human to decide this conflict.` のとき、テンプレ「pending conflict の必須出力フォーマット」 と「ユーザー向け本文に貼ってはいけない内部用語」の契約に従い、Agent は利用者向け本文で **日本語訳に置き換える**。CLI 側 raw 文字列はそのまま (将来の i18n 対応を見据える) が、利用者には常に日本語で見せる。

## 翻訳マッピング

| CLI raw 値 (英語) | Agent 翻訳 (日本語) |
|---|---|
| `Ask a human to decide this conflict.` | 人間判断で衝突を解消してください。 |

新たな英語 default 値が CLI に追加された場合、この対応表に行を追加し、`tests/e2e/forbidden_terms.py` の `_NON_JAPANESE_NATURAL_SENTENCES` にも追加する。

## 翻訳契約の所在

| 場所 | 該当節 |
|---|---|
| `.claude/commands/spec-inject.md` | 「pending conflict の必須出力フォーマット」+「ユーザー向け本文に貼ってはいけない内部用語」(許可される文字列を含む) |
| `.claude/commands/spec-realign.md` | 同上 |
| `.claude/commands/spec-core.md` | 同上 |

## 翻訳が適用される対象 snapshot

人間レビュー差し戻し対応として、次の 6 snapshot を翻訳済みで再生成:

- `tests/e2e/snapshots/#3-s01_pending_conflict_single_pair.md`
- `tests/e2e/snapshots/#3-s02_pending_conflict_three_claims.md`
- `tests/e2e/snapshots/#3-s03_pending_conflict_multiple.md` (2 件分の置換)
- `tests/e2e/snapshots/#3-s04_pending_conflict_with_dirty_source.md`
- `tests/e2e/snapshots/#3-s05_pending_conflict_three_commands.md`
- `tests/e2e/snapshots/#8-s04_core_complete_with_pending_conflict.md`

## 観測される結果

```text
$ grep -E "^\s+次の操作: " tests/e2e/snapshots/#3-*.md tests/e2e/snapshots/#8-s04_*.md | sort -u

tests/e2e/snapshots/#3-s01_*.md:     次の操作: 人間判断で衝突を解消してください。
tests/e2e/snapshots/#3-s02_*.md:     次の操作: 人間判断で衝突を解消してください。
tests/e2e/snapshots/#3-s03_*.md:     次の操作: 人間判断で衝突を解消してください。
tests/e2e/snapshots/#3-s04_*.md:     次の操作: 人間判断で衝突を解消してください。
tests/e2e/snapshots/#3-s05_*.md:     次の操作: 人間判断で衝突を解消してください。
tests/e2e/snapshots/#8-s04_*.md:       次の操作: 人間判断で衝突を解消してください。
```

`Ask a human to decide this conflict.` は対象 snapshot から完全に除去された。

## 自動検証

`tests/e2e/forbidden_terms.py` の `_NON_JAPANESE_NATURAL_SENTENCES = ("Ask a human to decide this conflict.",)` が `FORBIDDEN_TERMS` に組み込まれており、`test_snapshot_has_no_forbidden_terms` が全 user_facing snapshot で英語自然文の不在を強制する。

## 翻訳対象外 (そのまま使うべきもの)

- コマンド名 (例: `run /spec-core before /spec-inject`、`spec-anchor-setup-project --target /path/to/project`)
- URL
- file path (例: `docs/spec/auth.md#0002-session-management`)
- 識別子 (例: `conflict-candidate-sha256-...`、`CONF-0007`)
