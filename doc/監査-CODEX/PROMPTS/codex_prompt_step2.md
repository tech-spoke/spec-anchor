# Codex 起動 prompt: Step 2

ユーザーが Codex に投げる時の指示文。仕様書本体は `doc/監査-CODEX/PROMPTS/step2.md` にある。

---

## Codex に投げる文（この下の triple-backtick の中身をそのままコピペ）

```
あなたは spec-grag リポジトリの監査作業者です。本タスクは Step 2「方式仕様書の逆生成（C4 / arc42 / ADR 混合形式）」です。

# 上位ルール確認の禁止（最重要）

CLAUDE.md / AGENTS.md / README.md / doc/EXTERNAL_DESIGN.ja.md / doc/DESIGN.ja.md / doc/TODO.ja.md / doc/AGENTS.md などの「上位ルール文書 / 設計書 / 作業ガイド」を、いかなる目的でも開かないでください。「上位ルールの確認のために読む」のも禁止です。

本 Step の作業に必要な情報は、§2 必読仕様書と前段成果物 (STEP1A_INVENTORY.ja.md / STEP1B_FLOWS.ja.md / STEP1C_CROSS_VIEWS.ja.md) に全て含まれています。

仕様書に書かれていない方針が必要だと感じた場合、上位ルール文書を読まずに、仕様書 §12 不明事項に「仕様書に方針記述が無い」と記録して自己判断で進めず保留してください。

理由: 本 Step は「コードから方式を逆生成する」作業です。設計書バイアスや作業ガイドのバイアスが入ると、後段 Step 3 (業界標準差分) / Step 4 (外部設計書整合チェック) の独立性が失われます。特に doc/EXTERNAL_DESIGN.ja.md は Step 4 で初めて開く設計書です。Step 2 時点で見ると Step 4 の整合チェックが意味を失います。

前回 Step 1-C で「上位ルール確認」として doc/EXTERNAL_DESIGN.ja.md などを開いた経緯がありますが、本 Step では同じことを行わないでください。

# 着手前の必読

次の 6 ファイルを最初から最後まで全文読んでから着手してください。

仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step2.md
前段仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step1a.md
前段仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step1b.md
前段仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step1c.md
前段成果物 1-A: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1A_INVENTORY.ja.md
前段成果物 1-B: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1B_FLOWS.ja.md
前段成果物 1-C: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md

読み終えたら、作業を始める前に 5-10 行で次を提示してください:

1. 1-A / 1-B / 1-C 成果物のうち、本 Step で必ず引用する節
2. 本 Step で新規 grep / line read が必要だと判断した範囲（あれば、その理由）
3. 上位ルール確認の禁止について、自分の理解を 1-2 行で要約
4. 自分が誤解しそうな点と、その回避方法

# 作業

仕様書 §11「作業手順」に従ってください。要点を再掲します:

1. Step 1-A / 1-B / 1-C 成果物を全文読む
2. git rev-parse HEAD で commit hash を取得し §0 に記録
3. §1 Executive Summary（事実のみ、業界用語比較なし、評価表現なし）
4. §2 方式分類（事実ベース、Step 1-C §1 マトリクスから）
5. §3 正本/派生/cache/index/runtime state/debug の 6 カテゴリで artifact 分類（14 件）
6. §4 C4 ビュー Container / Component
7. §5 主要データフロー（CLI 9 件、Container 間移動が見える粒度に圧縮）
8. §6 更新時整合性 case 別
9. §7 検索結果から本文戻り経路（inject-search 中心）
10. §8 失敗時ポリシー（34 件、Step 1-C §3 から CLI ごとに再構造化）
11. §9 ADR 候補（所定の方式判断 8 件 + 追加観測、「コードから不明」を恐れない）
12. §10 アーキテクチャリスク
13. §11 方式の構造的要約（10-15 行）
14. §12 不明事項
15. §最終報告

# 成果物

- 配置: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP2_METHOD.ja.md
- 新規ファイルとして作成すること
- 文字コード UTF-8、改行 LF

# 絶対に守ること

- 仕様書 §4 denylist のファイルを開かない（特に CLAUDE.md / AGENTS.md / doc/EXTERNAL_DESIGN.ja.md / doc/TODO.ja.md / doc/AGENTS.md / 上位 README.md）
- 仕様書 §5「上位ルール確認の禁止」を厳守する
- 仕様書 §6 禁則を守る（推測 / 評価 / 改善案 / 業界標準比較 / 上位文書参照 / 「責務」だけの記述 / file:line 無し記述）
- 業界標準（RAG / GraphRAG / LlamaIndex / Microsoft / LightRAG 等）との比較・対応付けは Step 3 で行うため、本 Step では書かない
- 「Purpose に照らして」「外部設計書では」のような上位文書参照は禁止
- C4 / arc42 / ADR のテンプレートを埋めるためだけに、コードから読めない内容を記述しない。読めない欄は「コードから不明」と書く
- 「責務」「役割」「担当」だけで内容を説明しない。**入力 / 何を呼ぶ / 出力 / 失敗時挙動** で書く
- 既存 1-A / 1-B / 1-C 事実を引用する時は、必ず引用元の節番号と file:line を併記する

# grep 実行時の注意（仕様書 §10 / step1c.md §9 参照）

新規 grep する場合、pattern に backtick を含めて double quote で囲まない（shell が backtick 内を command として展開する）。single quote または -F (fixed string) フラグを使う:

- 例: grep -nF 'inject-search' spec_grag
- 例: grep -n 'inject-search' spec_grag

# 完了報告（作業完了時に必ず提出）

作業完了時に、本セッション上で次を提示してください:

1. 作成したファイル: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP2_METHOD.ja.md
2. 仕様書 §12「最終報告」節の全内容（成果物ファイルからそのまま抜粋して貼る）
3. 仕様書 §13 完了条件のチェック結果: 各項目について「満たした / 満たしていない（理由）」を列挙
   - allowlist 外を開いていないか（特に CLAUDE.md / AGENTS.md / doc/EXTERNAL_DESIGN.ja.md 等）
   - 禁則表現を含まないか
   - 全事実記述に file:line または §節番号引用を付けたか
   - §0〜§12 が全て埋まっているか
   - §3 artifact 件数 14 が Step 1-C §2 と一致するか
   - §8 失敗時ポリシー件数 34 が Step 1-C §3 と一致するか
   - §6 / §9 で「コードから観測なし / 不明」を恐れずに明記しているか
   - §11 方式構造的要約が 10-15 行に収まっているか
   - §最終報告が記入されているか
4. 追加で報告すること:
   - 中断 / 失敗があれば、どこで何が起きたか（隠さない）
   - 仕様書の指示で曖昧だった箇所、自己判断で解釈した箇所
   - 想定より時間がかかった節とその理由
   - 1-A / 1-B / 1-C 事実だけで埋まらず、新規 grep を要した節とその理由（0 件が望ましい）
   - 1-A / 1-B / 1-C 事実に齟齬や矛盾を見つけた場合、その内容と所在
   - 上位ルール文書を開かなかったことの確認方法

# 中断時のルール（仕様書 §14 と同じ）

- 現状を /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP2_METHOD.ja.md に保存
- ファイル先頭に「⚠ 未完了: 中断箇所と理由」セクションを追加
- 完了報告の代わりに「中断報告」として、どこまで完了したか / 何が残っているかを提示
- 事実水増し、file:line 省略、推測の混入は禁止
- 節単位で中断する場合、§N の途中で止めるよりも §N を「未完了」マークして §N+1 を着手しない

# 本 Step の本質

本 Step は「コードから方式を逆生成する」作業です。設計書を見ないでコードだけから方式仕様書を書くことが、後段 Step 4 で外部設計書との整合チェックを意味のあるものにします。

「読まないと書けない」と感じる節があれば、それは「コードから不明」と明記して保留してください。コードから読めない箇所を埋めるために設計書を開くと、Step 2 の独立性が失われます。
```

---

## 補足（Codex に投げる文には含めない、ユーザー向けメモ）

- Step 1-C で発生した上位ルール文書読込（CLAUDE.md / AGENTS.md / doc/EXTERNAL_DESIGN.ja.md / doc/TODO.ja.md）を防ぐため、本 prompt 冒頭に明示的な禁止を書いた
- 「上位ルール確認の禁止」の理由を Codex に理解させることが核心。理解しないまま遵守すると、判断を要する局面で抜け穴を作る
- 完了後の点検観点:
  - §1 Executive Summary に業界用語（RAG / GraphRAG 等）が混入していないか
  - §2 方式分類が事実ベースで書かれ、判定言葉が混入していないか
  - §6 更新時整合性で「コードから観測なし」が適切に使われているか（無理に埋めていないか）
  - §9 ADR で「採用理由がコードから不明」が適切に使われているか
  - §11 構造的要約に評価表現が混入していないか
  - 最終報告で「上位ルール文書を開かなかった確認方法」が誠実に記録されているか
- Codex から完了報告が来たら共有してもらえれば点検する
- Step 2 完了後は Step 3 (業界標準との差分) → Step 4 (外部設計書との整合チェック) に進む
