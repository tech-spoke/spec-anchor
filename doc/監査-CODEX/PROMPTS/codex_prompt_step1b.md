# Codex 起動 prompt: Step 1-B

ユーザーが Codex に投げる時の指示文。仕様書本体は `doc/監査-CODEX/PROMPTS/step1b.md` にある。

---

## Codex に投げる文（この下の triple-backtick の中身をそのままコピペ）

```
あなたは spec-grag リポジトリの監査作業者です。本タスクは Step 1-B「主要 CLI フローの深掘り」です。

# 着手前の必読

次の 2 ファイルを最初から最後まで全文読んでから着手してください。途中で読むのをやめないでください。

仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/step1b.md
前段成果物: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1A_INVENTORY.ja.md

仕様書 §2 に「着手前に提示するもの」のリストがあります。これに従って、作業を始める前に 5-10 行で次を提示してください:

1. Step 1-A 成果物のうち、本 Step で必ず引用する節（§1 / §2 / §3 / §7 のいずれか）
2. 本 Step で深掘りする CLI 一覧
3. 本 Step で深掘りしない CLI 一覧と、その理由
4. Step 1-A §7（動的 env var resolution）のうち本 Step で解消する候補
5. 自分が誤解しそうな点と、その回避方法

提示してから作業を始めてください。

# 作業

仕様書 §10「作業手順」に従ってください。要点を再掲します:

1. Step 1-A 成果物を全文読む
2. git rev-parse HEAD で commit hash を取得し §0 に記録
3. §0 で対象 CLI と対象外 CLI を確定
4. §1 (core) → §2 (inject) → §3 (inject-search) → §4 (inject-section) → §5 (inject-chapters) → §6 (inject-purpose) → §7 (inject-conflicts) → §8 (realign) → §9 (watch) の順で各 CLI のフローを書く
5. §A で動的 env var を解消、§B で dead 引数 / dead import / dead 関数、§C で設定 key の重複 / 乖離、§D で不明事項
6. §最終報告を書く

# 成果物

- 配置: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1B_FLOWS.ja.md
- 新規ファイルとして作成すること
- 文字コード UTF-8、改行 LF

# 絶対に守ること

- 仕様書 §4 denylist のファイルを開かない / 引用しない（特に doc/EXTERNAL_DESIGN.ja.md / doc/DESIGN.ja.md / doc/AGENTS.md / CLAUDE.md / AGENTS.md / README.md）
  - 例外として読んでよい doc/ ファイルは仕様書 step1b.md と前段成果物 STEP1A_INVENTORY.ja.md のみ
- 仕様書 §5 禁則を守る（推測・評価・改善案・業界標準比較・「責務」だけの記述・file:line 無し記述）
- 各 CLI のフローを「省略」「以下同様」と書かない。同一パターン連続時は §5 のルールに従う
- 各ステップに必ず「入力 / 処理 / 出力 / 外部接続 / 分岐」を書く。「処理: 適切に処理する」のような抽象表現は禁止
- 外部接続点は「ある」とだけ書かず、接続先・接続条件・失敗時挙動を file:line で明示する
- 「呼ばれている」とだけ書かず、「どの条件で呼ばれるか」を書く
- 仕様書 §B の dead 引数 / dead import / dead 関数は探索コマンド付きで全件列挙

# 完了報告（作業完了時に必ず提出）

作業完了時に、本セッション上で次を提示してください:

1. 作成したファイル: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1B_FLOWS.ja.md
2. 仕様書 §11「最終報告」節の全内容（成果物ファイルからそのまま抜粋して貼る）
3. 仕様書 §12 完了条件のチェック結果: 各項目について「満たした / 満たしていない（理由）」を列挙
   - allowlist 外を開いていないか
   - 禁則表現を含まないか
   - 全事実記述に file:line を付けたか
   - §0 に対象 CLI と対象外 CLI が明示されているか
   - §1〜§9 の各 CLI フローが入口から出口まで揃っているか
   - 各 CLI フロー末尾に「呼ばれない引数 / 経路」と「外部接続点」の節があるか
   - §A で動的 env var が解消可能な範囲で解消されているか
   - §B で dead 引数 / dead import / dead 関数が全件列挙されているか（探索コマンド併記）
   - §C で設定 key の重複 / 乖離が全件列挙されているか
   - §D が空の場合、空である根拠が記録されているか
   - §最終報告が記入されているか
4. 追加で報告すること:
   - 中断 / 失敗があれば、どこで何が起きたか（隠さない）
   - 仕様書の指示で曖昧だった箇所、自己判断で解釈した箇所
   - 想定より時間がかかった CLI とその理由
   - 各 CLI のフローステップ数（参考情報）

# 中断時のルール（仕様書 §13 と同じ）

タスクの途中で中断する場合（タイムアウト / ユーザー指示 / 自己判断停止のいずれでも）:

- 現状を /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP1B_FLOWS.ja.md に保存する
- ファイル先頭に「⚠ 未完了: 中断箇所と理由」セクションを追加する
- 完了報告の代わりに「中断報告」として、どこまで完了したか / 何が残っているかを提示する
- 「完了したように見せる」ための事実水増し、file:line 省略、推測の混入は禁止
- CLI 単位で中断する場合、§N の途中で止めるよりも §N を「未完了」マークして §N+1 を着手しないでください

中途半端でも正直に中断報告してください。

# 量に関する注意

本 Step は Step 1-A より深掘りなため、各 CLI のフローステップ数が増えます。core のような深い経路で 20-50 ステップ、inject-chapters のような浅い artifact lookup 経路で 3-5 ステップを目安にしてください。

浅い経路で水増し（無理にステップを増やす）してはいけません。深い経路で省略（「以下同様」「同じパターン」だけで済ませる）してはいけません。コードの実態に従ってください。
```

---

## 補足（Codex に投げる文には含めない、ユーザー向けメモ）

- Step 1-A 成果物 `STEP1A_INVENTORY.ja.md` が allowlist に入っている。Step 1-A の §1 (公開関数シグネチャ) と §3 (設定キー) を引用しないとフロー追跡ができないため
- Step 1-A の §7 で残った動的 env var resolution 6 件を、Step 1-B §A で解消対象としている。完全に解消できなくても良い（フロー追跡で確定できる範囲のみ）。残ったものは Step 1-C で扱う
- Step 1-B 完了後、Claude 側で点検する観点:
  - 各 CLI フローが入口から出口まで欠けなく追跡されているか
  - 「LLM 呼び出しの有無」「Qdrant 呼び出しの有無」「FlagEmbedding 呼び出しの有無」が CLI ごとに事実として書かれているか（前回見つけた「ベクター DB を使わない制約生成」がフロー上で表面化するか）
  - §B の dead 引数 / dead import が、実装と契約の乖離を示唆する箇所として列挙されているか
  - §C の設定 key 重複が、Step 1-A §3 で観測した `section_collection` 等を含むか
- Codex から完了報告が来たら、私（Claude）に次を共有してもらえれば点検する:
  - 完了報告の全文
  - 生成された STEP1B_FLOWS.ja.md のパス（私が読む）
