# #13-s03 snapshot 全件横断: Agent 整形済み snapshot に日本語以外の自然文が含まれない

`tests/e2e/snapshots/` 配下の Agent 整形済み snapshot (`kind="user_facing"` のもの) に、`Ask a human to decide this conflict.` のような日本語以外の自然文が含まれていない。

## 検証手順 (自動)

```text
$ .venv/bin/python3 -m pytest tests/e2e/test_user_facing_output.py -q
```

期待結果: `test_snapshot_has_no_forbidden_terms` が全 user_facing snapshot で pass。

## 禁止用語 SOT への追加

`tests/e2e/forbidden_terms.py` に新規 tuple を追加:

```python
_NON_JAPANESE_NATURAL_SENTENCES = (
    "Ask a human to decide this conflict.",
)

FORBIDDEN_TERMS: tuple[str, ...] = (
    _CONTROL_FLAGS
    + _ENUM_VALUES
    + _PIPELINE_STAGE_NAMES
    + _NORMAL_COMPLETION_FIELDS
    + _RESULT_PATH_FIELDS
    + _CONFLICT_FIELD_NAMES
    + _NON_JAPANESE_NATURAL_SENTENCES
)
```

これにより、新たな snapshot に英語自然文が混入した場合、pytest が即座に検出する。

## 除外対象 (kind="cli_json")

CLI raw JSON snapshot (#5 系 / #9-s01〜s07) は除外。これらはシナリオ責務として **CLI 内部 JSON 構造の assert** を行うため、内部 field 名・enum 値・英語 default 値が出るのは意図通り。

- `#5-s01` 〜 `#5-s04`: CLI error block の構造を assert
- `#9-s01` 〜 `#9-s07`: CLI raw stdout が valid JSON 単体であることを assert

## 全件横断 grep の補助確認

`Ask a human` を全 snapshot ファイルで grep し、`kind="user_facing"` の snapshot に該当ヒットがゼロであることを確認:

```text
$ grep -lE "Ask a human" tests/e2e/snapshots/*.md
```

期待結果: 何もヒットしない (`kind="cli_json"` snapshot にも当該文字列が含まれないこと、もし含まれた場合はその snapshot が `kind="cli_json"` であることを scenarios.py で確認)。

## 拡張 protocol

将来、CLI が新たな英語 default 文字列を導入した場合:

1. `_NON_JAPANESE_NATURAL_SENTENCES` に固定文字列を追加
2. 3 コマンドテンプレの翻訳マッピング表 (#13-s01) に翻訳対応を追記
3. 既存 snapshot を再生成 (もし既存 snapshot に新文字列が漏出していれば差し戻し)

`Ask a human to decide this conflict.` のような完全一致の固定文字列を列挙する形で運用。文法・文体ベースの「自然文か否か」判定は採用しない (false positive を避ける)。

## SCENARIO 登録

`tests/e2e/scenarios.py` に `#13-s01` / `#13-s02` / `#13-s03` を `kind="note"` で登録。
