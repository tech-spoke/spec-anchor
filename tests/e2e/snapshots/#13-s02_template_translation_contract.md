# #13-s02 3 コマンドテンプレに「日本語訳契約」が明記されている (doc lint)

3 コマンドテンプレ (`.claude/commands/spec-inject.md` / `spec-realign.md` / `spec-core.md`) の「pending conflict の必須出力フォーマット」セクションと「ユーザー向け本文に貼ってはいけない内部用語」セクションに、CLI が返す日本語以外の自然文を **Agent が日本語訳に置き換える契約** が明文化されている。

## doc lint コマンド

```text
$ grep -nE "日本語以外の自然文|日本語訳|人間判断で衝突を解消してください" \
      .claude/commands/spec-inject.md \
      .claude/commands/spec-realign.md \
      .claude/commands/spec-core.md
```

## 期待される文言 (代表抜粋)

### pending conflict 本文展開フォーマット 行

> 次の操作: <Agent が日本語訳した item recommended_next_action 値。CLI が日本語以外の自然文を返した場合は日本語に置き換える。例: `Ask a human to decide this conflict.` → 「人間判断で衝突を解消してください。」>

### 禁止用語リスト 追加項目

> **日本語以外の自然文** (例: CLI の `recommended_next_action` default 値 `Ask a human to decide this conflict.`、LLM judge の英語返答)。本文は日本語で統一する。**翻訳対象外**: コマンド名 / URL / file path / 識別子

### 許可される文字列セクション 追加項目

> CLI が出力する `recommended_next_action` の値が **日本語以外の自然文** (例: `Ask a human to decide this conflict.`) の場合、Agent は **利用者向け本文で日本語訳に置き換える** (例: `人間判断で衝突を解消してください。`)。翻訳対象外: コマンド名・URL・file path・識別子

## 翻訳対象外の例外 (そのまま使うべきもの)

| カテゴリ | 例 |
|---|---|
| コマンド名指示 | `run /spec-core before /spec-inject` / `run /spec-core --all` / `spec-anchor-setup-project --target /path/to/project` |
| URL | `http://localhost:6333/` 等 |
| file path | `docs/spec/auth.md#0002-session-management` 等 |
| 識別子 | `conflict-candidate-sha256-...` / `CONF-0007` 等 |

## 単一の真実

禁止用語の機械検証は `tests/e2e/forbidden_terms.py` が SOT (Single Source of Truth)。テンプレ側の文言は Agent への教育目的、`forbidden_terms.py` 側が pytest による強制。両者は同じ対象 (例: `Ask a human to decide this conflict.`) を扱うため、片方を更新したら他方も更新する。
