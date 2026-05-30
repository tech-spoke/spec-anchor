# #12-s01 「能動的追加探索」「探索の十分性は Agent が判断」「3 path は起点 (上限ではない)」の明文化 (doc lint)

`.claude/commands/spec-inject.md` / `.claude/commands/spec-realign.md` / `doc/EXTERNAL_DESIGN.ja.md` §8.3 / §8.3.1 に、Agent の能動的追加探索を奨励する文言が追加されている。

## doc lint コマンド

```text
$ grep -cE "3 path は探索の起点であり上限ではない|探索の十分性は Agent が判断|自らの気づきに基づく追加探索" \
      .claude/commands/spec-inject.md \
      .claude/commands/spec-realign.md \
      doc/EXTERNAL_DESIGN.ja.md
```

期待結果: 3 ファイルそれぞれで 1 件以上ヒット。

## 追加された文言 (代表抜粋)

### `.claude/commands/spec-inject.md` 「path 選択の指針」セクション

> **3 path は探索の起点であり上限ではない**。Agent は 3 path を通過した後でも、課題への根拠が不十分と判断した場合、自らの気づきに基づく追加探索を能動的に行う:
>
> - 別の search key を生成して `spec-anchor inject-search` を再実行する
> - 別 path へ切り替える (例: ① で根拠不足なら ② 章単位エントリへ)
> - 上位章や横断 section へ hop する
> - 関連 Conflict Review Item を再確認する
>
> **探索の十分性は Agent が判断**し、制約に必要な根拠が揃うまで継続する。CLI は path 数や hop 数の上限を強制しない。

### `.claude/commands/spec-realign.md` §5

> **3 path は探索の起点であり上限ではない**。Agent は 3 path 通過後でも、課題への根拠が不十分と判断した場合、自らの気づきに基づく追加探索 (別 search key の生成、別 path への切り替え、上位章 hop) を能動的に行う。探索の十分性は Agent が判断し、制約に必要な根拠が揃うまで継続する。

### `doc/EXTERNAL_DESIGN.ja.md` §8.3

> **3 path は探索の起点であり上限ではない**。Agent は 3 path 通過後でも、課題への根拠が不十分と判断した場合、自らの気づきに基づく追加探索 (...) を能動的に行う。探索の十分性は Agent が判断し、制約に必要な根拠が揃うまで継続する。CLI は path 数や hop 数の上限を強制しない。

### `doc/EXTERNAL_DESIGN.ja.md` §8.3.1

> **探索の十分性** (= Agent が「もう追加探索は不要、答案構成に進める」と判断するタイミング) は Agent / LLM が判断する。CLI は path 数や hop 数の上限を強制しない。Agent は課題への根拠が揃うまで、3 path 内での追加探索 (別 search key 生成、別 path 切り替え、上位章 hop) を能動的に継続できる。「3 path 通過 = 終了」を機械的に解釈してはいけない。

## 設計意図

Agent (LLM) は instruction-follower の性質から「3 path 通過 → 即終了」と機械的に解釈する余地がある。これを排除するため、能動的追加探索を **明示的に奨励** する文言を 3 ファイルに同時に入れる。ドリフト防止 (CLI 道具縛り + evidence_origin 縛り) は維持する。

## 関連 sub task

- #2 / #3 / #4 / #5 / #6 (利用者向け出力テンプレ): Agent の探索責務を強化するが、出力フォーマット自体は変えない
- #7 (外部設計書 §8.7 表示契約): §8.3 改訂を伴う本 #12 と並行
- #10 (templates mirror): プロジェクト直下の修正を `spec_anchor/templates/.claude/commands/` に同期 (本 commit で実施)
