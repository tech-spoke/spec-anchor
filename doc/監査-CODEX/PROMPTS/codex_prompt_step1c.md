# Codex 起動 prompt: Step 1-C

ユーザーが Codex に投げる時の指示文。仕様書本体は `doc/監査-CODEX/PROMPTS/step1c.md` にある。

---

## Codex に投げる文（この下の triple-backtick の中身をそのままコピペ）

```
あなたは spec-grag リポジトリの監査作業者です。本タスクは Step 1-C「横断観点表」です。

# 着手前の必読

次の 4 ファイルを最初から最後まで全文読んでから着手してください。

仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step1c.md
前段仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step1a.md
前段仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step1b.md
前段成果物 1-A: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1A_INVENTORY.ja.md
前段成果物 1-B: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1B_FLOWS.ja.md

読み終えたら、作業を始める前に 5-10 行で次を提示してください:

1. 1-A / 1-B 成果物のうち、本 Step で必ず引用する節
2. 1-A / 1-B の事実だけで埋まる節と、新規 grep が必要な節の見分け
3. 本 Step で新規 grep する範囲（あれば）
4. 自分が誤解しそうな点と、その回避方法

提示してから作業を始めてください。

# 作業

仕様書 §10「作業手順」に従ってください。要点を再掲します:

1. Step 1-A / 1-B 成果物を全文読む
2. git rev-parse HEAD で commit hash を取得し §0 に記録
3. §1 外部接続点マトリクスを Step 1-B §1〜§9 の「外部接続点」表から転記し横断統合
4. §2 artifact ライフサイクルを 1-A §4 / §5 と 1-B 各 CLI フローから構築
5. §3 失敗時挙動を 1-B §1〜§9 から転記しカテゴリ分類
6. §4 判断ロジックを 1-B 「分岐」記述から横断統合
7. §5 設定 key 重複を 1-B §C から全 CLI 影響範囲に展開
8. §6.1 (target 9 CLI 範囲の dead) / §6.2 (リポジトリ全体の dead) で二重区分
9. §7 本 Step 固有の不明事項を記録 (1-B §D の 2 件は対象外)
10. §最終報告を書く

本 Step は「新規 grep を最小限に抑え、1-A / 1-B 事実の再構造化を中心に行う」のが原則です。新規 grep が必要な場合のみ、その理由と探索コマンドを §0 に明示してください。

# 成果物

- 配置: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md
- 新規ファイルとして作成すること
- 文字コード UTF-8、改行 LF

# 絶対に守ること

- 仕様書 §4 denylist のファイルを開かない / 引用しない（特に doc/EXTERNAL_DESIGN.ja.md / doc/DESIGN.ja.md / doc/AGENTS.md / CLAUDE.md / AGENTS.md / README.md）
  - 例外として読んでよい doc/ ファイルは仕様書 step1a.md, step1b.md, step1c.md と前段成果物 STEP1A_INVENTORY.ja.md, STEP1B_FLOWS.ja.md のみ
- 仕様書 §5 禁則を守る（推測・評価・改善案・業界標準比較・「責務」だけの記述・file:line 無し記述）
- 既存 1-A / 1-B 事実を引用する時は、必ず引用元の節番号と file:line を併記する
- §6 の二重区分を混ぜない: slash_main / watch_main / setup_project_main / setup_system_main は §6.1 (target 9 CLI 範囲では呼ばれないが、pyproject.toml の別 entry として実在) に分類する
- §1 マトリクスは 9 CLI 全列を空欄なく埋める。各セルに「呼ぶ (file:line + Step 1-B §節番号)」「呼ばない (根拠)」「条件付き (条件 + file:line)」のいずれかを書く
- 「dead」「不要」「冗長」と書く時、観測範囲（target 9 CLI 範囲か / repo 全体か）を必ず明示する
- 「失敗時に止まる」「continue する」と書く時、判定箇所の file:line を必ず書く

# grep 実行時の注意（仕様書 §9 参照）

Step 1-B 実行時に shell quoting エラーがありました。本 Step で新規 grep する場合:

- pattern に backtick を含めて double quote で囲まない（shell が backtick 内を command として展開する）
- 安全な書き方: single quote で囲む or `-F` (fixed string) フラグを使う
  - 例: grep -nF 'watch' spec_grag
  - 例: grep -n 'watch' spec_grag
- backslash escape の double quote 内使用も注意

# 完了報告（作業完了時に必ず提出）

作業完了時に、本セッション上で次を提示してください:

1. 作成したファイル: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md
2. 仕様書 §11「最終報告」節の全内容（成果物ファイルからそのまま抜粋して貼る）
3. 仕様書 §12 完了条件のチェック結果: 各項目について「満たした / 満たしていない（理由）」を列挙
   - allowlist 外を開いていないか
   - 禁則表現を含まないか
   - 全事実記述に file:line または Step 1-B 節番号引用を付けたか
   - §0 に commit hash と前提成果物が明示されているか
   - §1 マトリクスが 9 CLI 全列で空欄なく埋まっているか
   - §2 artifact ライフサイクルが対象 artifact 全件で埋まっているか
   - §3 失敗時挙動が Step 1-B §1〜§9 の全外部接続点失敗を網羅しているか
   - §4 判断ロジックが Step 1-B 「分岐」記述を網羅しているか
   - §5 設定 key 重複が Step 1-B §C を全 CLI 影響範囲に展開しているか
   - §6.1 / §6.2 が分けて記録されているか
   - §7 が空の場合、空である根拠が記録されているか
   - §最終報告が記入されているか
4. 追加で報告すること:
   - 中断 / 失敗があれば、どこで何が起きたか（隠さない）
   - 仕様書の指示で曖昧だった箇所、自己判断で解釈した箇所
   - 想定より時間がかかった節とその理由
   - 1-A / 1-B 事実だけで埋まらず、新規 grep を要した節とその理由
   - 1-A / 1-B 事実に齟齬や矛盾を見つけた場合、その内容と所在

# 中断時のルール（仕様書 §13 と同じ）

- 現状を /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md に保存
- ファイル先頭に「⚠ 未完了: 中断箇所と理由」セクションを追加
- 完了報告の代わりに「中断報告」として、どこまで完了したか / 何が残っているかを提示
- 事実水増し、file:line 省略、推測の混入は禁止
- 節単位で中断する場合、§N の途中で止めるよりも §N を「未完了」マークして §N+1 を着手しない

# 本 Step の特徴

- Step 1-A は新規事実抽出、Step 1-B は CLI 単位フロー追跡、Step 1-C は**観点単位の横断統合**です
- 新規 grep を最小限に抑え、1-A / 1-B 事実を再構造化することで、観点ごとに 9 CLI を見渡せるマトリクスを作るのが目的です
- §1 マトリクスが本 Step の核です。9 CLI × 11 外部接続点 = 99 セルを空欄なく埋めることが、後段 Step 2 で方式仕様書を再構成する起点になります
```

---

## 補足（Codex に投げる文には含めない、ユーザー向けメモ）

- Step 1-C は新規 grep が少ないため Step 1-B より短時間で完了する見込み
- 完了後の点検観点:
  - §1 マトリクスで「LLM 呼ぶ」が core / watch のみであることが横断的に見えるか
  - §1 マトリクスで「Qdrant 呼ぶ」が core / inject-search / inject-section / watch のみであることが見えるか
  - §2 artifact ライフサイクルで「生成されているが読まれない artifact」が表面化するか
  - §3 失敗時挙動で degraded / warning / failed / blocked の分類が CLI ごとに整理されるか
  - §5 設定 key 重複の影響範囲が Step 1-B §C より広がるか
  - §6.1 と §6.2 が混ざらず分類されているか
- Codex から完了報告が来たら共有してもらえれば点検する
- Step 1-C 完了で Step 1 シリーズ（1-A / 1-B / 1-C）が完了。次は Step 2（方式仕様書再構成）に進む
