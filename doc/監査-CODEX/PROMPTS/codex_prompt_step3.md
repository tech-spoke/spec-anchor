# Codex 起動 prompt: Step 3

ユーザーが Codex に投げる時の指示文。仕様書本体は `doc/監査-CODEX/PROMPTS/step3.md` にある。

---

## Codex に投げる文（この下の triple-backtick の中身をそのままコピペ）

```
あなたは spec-grag リポジトリの監査作業者です。本タスクは Step 3「業界標準 GRAG / RAG パターンとの差分判定」です。

# 上位ルール文書を判定根拠にしない（最重要）

Codex 環境の上位指示で CLAUDE.md / AGENTS.md / doc/EXTERNAL_DESIGN.ja.md 等を作業開始時に読むことが Step 1-C / Step 2 で発生しました。本 Step では:

- 上位ルール文書を読んだ場合、判定の根拠としては絶対に使わない
- 判定根拠は Step 2 成果物と doc/監査/STANDARD_GRAG_PATTERNS.ja.md のみ
- 「Purpose に照らして」「外部設計書では」のような上位文書参照は禁止
- 業界標準と不整合な事項が「正当化されるか」は判定しない（Step 4 で人間判断対象）
- 「これは正しい / 間違っている / 直すべき」と書かない（判定は Step 4）

理由: 本 Step は「業界標準との差分判定」だけを行う。妥当性 / 正当化の最終判定は Step 4 で外部設計書 / Purpose に照らして行う。Step 3 時点で外部設計書由来の解釈を混ぜると、Step 4 の独立性が失われます。

# 着手前の必読

次のファイルを最初から最後まで全文読んでください。

仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step3.md
前段仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step1a.md / step1b.md / step1c.md / step2.md
前段成果物 1-A: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1A_INVENTORY.ja.md
前段成果物 1-B: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1B_FLOWS.ja.md
前段成果物 1-C: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md
前段成果物 2: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP2_METHOD.ja.md
業界標準資料: /home/kazuki/public_html/spec-grag/doc/監査/STANDARD_GRAG_PATTERNS.ja.md

業界標準資料 doc/監査/STANDARD_GRAG_PATTERNS.ja.md は本 Step で初めて開きます。§7 (行 99-104) の判定軸 6 件が本 Step の核です。

読み終えたら、作業を始める前に 5-10 行で次を提示してください:

1. Step 2 成果物のうち、判定の主要根拠とする節
2. STANDARD_GRAG_PATTERNS のうち、判定軸として採用する節（§7 が中心）
3. 業界用語の対応付けで自分が誤解しそうな点
4. Step 4 で判断対象として保留する候補（業界標準と不整合だが正当化される可能性のある事項）

# 作業

仕様書 §11「作業手順」に従ってください。要点を再掲します:

1. 前段成果物と業界標準資料を全文読む
2. git rev-parse HEAD で commit hash を取得し §0 に記録
3. §1 で STANDARD_GRAG_PATTERNS §7 の判定軸 6 件を逐語引用
4. §2.1 (RAG) / §2.2 (Hybrid retrieval) / §2.3 (GRAG) / §2.4 (Incremental update) / §2.5 (Evidence) / §2.6 (Fallback) で 6 判定軸ごとに判定
5. §2.7 で全体方式分類（Baseline RAG / Hybrid RAG / GraphRAG / LightRAG / PropertyGraphIndex / lightweight related-section retrieval の候補から）
6. §3 で spec-grag 固有事項を列挙（指示の所定 7 件 + 追加観察）
7. §4 で判定サマリを集約
8. §5 で Step 4 への引き継ぎ候補を集約
9. §6 で本 Step 固有の不明事項を記録
10. §最終報告を書く

# 判定の選択肢（仕様書 §7 参照）

- 整合
- 部分整合
- 不整合
- 業界標準より strict
- 業界標準より loose
- 業界標準と異なる方式

これら以外の判定言葉（「正しい / 間違っている / 直すべき」など）は禁止。

# 成果物

- 配置: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md
- 新規ファイルとして作成すること
- 文字コード UTF-8、改行 LF

# 絶対に守ること

- 仕様書 §4 denylist のファイルを開かない（特に doc/EXTERNAL_DESIGN.ja.md / doc/DESIGN.ja.md / doc/AGENTS.md / CLAUDE.md / AGENTS.md / README.md / doc/監査/ の STANDARD_GRAG_PATTERNS.ja.md 以外のファイル）
  - 例外として読んでよい doc/ ファイルは仕様書 step1a/b/c/2/3.md、前段成果物 STEP1A/B/C/STEP2.md、業界標準資料 STANDARD_GRAG_PATTERNS.ja.md のみ
- 仕様書 §5「上位ルール文書を判定根拠にしない」を厳守
- 仕様書 §6 禁則を守る（推測 / 評価 / 改善案 / 上位文書参照 / 業界標準資料引用なしの「業界標準では～」記述 / 妥当性判定 / 業界標準資料外の判定軸持ち込み）
- 判定は §7 の 6 選択肢から選ぶ（「正しい / 間違っている」と書かない）
- 業界標準と不整合な事項が正当化されるかは判定しない（Step 4 で人間判断対象）
- 「責務」「役割」「担当」だけで内容を説明しない（入力 / 何を呼ぶ / 出力 / 失敗時挙動 で書く）
- 既存 Step 2 成果物 / 業界標準資料を引用する時は、必ず §節番号と file:line / 行番号を併記する

# grep 実行時の注意（仕様書 §10 / step1c.md §9 参照）

新規 grep する場合、pattern に backtick を含めて double quote で囲まない。single quote または -F フラグを使う。本 Step は引用中心のため新規 grep を最小限に。

# 完了報告（作業完了時に必ず提出）

作業完了時に、本セッション上で次を提示してください:

1. 作成したファイル: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md
2. 仕様書 §12「最終報告」節の全内容（成果物ファイルからそのまま抜粋して貼る）
3. 仕様書 §13 完了条件のチェック結果: 各項目について「満たした / 満たしていない（理由）」を列挙
   - allowlist 外を開いていないか、または開いたが判定根拠にしていないか
   - 禁則表現を含まないか
   - 全事実記述に file:line または §節番号引用を付けたか
   - §1 で業界標準資料 §7 の判定軸 6 件が逐語引用されているか
   - §2.1〜§2.6 で 6 判定軸の判定が明示されているか
   - §2.7 で全体方式分類が業界用語 5 候補から選ばれているか
   - §3 で spec-grag 固有事項が最低 7 件記録されているか
   - §4 で判定サマリが §2 と一致するか
   - §5 で Step 4 への引き継ぎ候補が集約されているか
   - §6 が空の場合、空である根拠が記録されているか
   - §最終報告が記入されているか
4. 追加で報告すること:
   - 中断 / 失敗があれば、どこで何が起きたか（隠さない）
   - 上位ルール文書を読んだ場合、判定根拠として使わなかったことの確認方法
   - 業界標準資料に書かれていない判定軸を持ち込んだ場合、その内容
   - 判定の選択肢で迷った箇所と、その自己判断

# 中断時のルール（仕様書 §14 と同じ）

- 現状を /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md に保存
- ファイル先頭に「⚠ 未完了: 中断箇所と理由」セクションを追加
- 完了報告の代わりに「中断報告」として、どこまで完了したか / 何が残っているかを提示
- 事実水増し、file:line / §節番号引用省略、推測の混入は禁止
- 判定軸単位で中断する場合、§2.N の途中で止めるよりも §2.N を「未完了」マークして §2.N+1 を着手しない

# 本 Step の本質

本 Step は「業界標準パターンと現状実装の差分判定」です。判定軸は STANDARD_GRAG_PATTERNS.ja.md §7 の 6 件 + 全体方式分類の 7 件。

判定だけ書き、妥当性 / 正当化は書きません。「不整合」と判定した事項について「これは間違っている」「これは直すべき」と書かないでください。それは Step 4 で外部設計書 / Purpose に照らして人間判断する事項です。

本 Step を独立に保つことで、Step 4 の整合チェックが意味を持ちます。
```

---

## 補足（Codex に投げる文には含めない、ユーザー向けメモ）

- 業界標準資料 `doc/監査/STANDARD_GRAG_PATTERNS.ja.md` は本 Step で**初めて**開く（前回 Phase 2 で作成済み）
- Step 1-C / Step 2 で観察された Codex 環境の上位ルール文書読込は、本 Step でも発生する見込み。Step 1-C / Step 2 と同じく「読んだが判定根拠にしない」を明示
- 完了後の点検観点:
  - §2.3 GRAG 最低条件の判定が「不整合」になっているか（graph 構造永続 store / traversal が無いため、業界標準資料 §7 行 101 の判定軸に従う）
  - §2.7 全体方式分類が「Hybrid RAG + lightweight related-section retrieval」のような複合呼称になっているか
  - §3 spec-grag 固有事項に「constraints / answer 生成が Agent 側」「`inject-search` のみが retrieval 経路」「Related Sections が auxiliary」等が含まれているか
  - §5 Step 4 への引き継ぎ候補が集約されているか
  - 「正しい / 間違っている / 直すべき」のような判定言葉が混入していないか
  - 「Purpose に照らして」「外部設計書では」のような上位文書参照が混入していないか
- Codex から完了報告が来たら共有してもらえれば点検する
- Step 3 完了後は Step 4（外部設計書との整合チェック）に進む。Step 4 で初めて `doc/EXTERNAL_DESIGN.ja.md` を判定根拠として開く
