# spec-grag Agent Guide

このファイルは spec-grag リポジトリで作業する Agent 共通の不変ルールを記録する。Claude / Codex / その他 Agent は同じルールに従う。

## 必読ドキュメント

新しいセッションでは、まず次をこの順序で読む。

1. `doc/EXTERNAL_DESIGN.ja.md` - 軽量版 SPEC-grag の外部契約
2. 本ファイル `CLAUDE.md` - Agent 共通の不変ルール
3. `AGENTS.md` - 報告ルール、設計書の記述ルール (`agent_doc/` 配下の記述ルールへの入口)
4. 必要な場合のみ `archive/full-grag-2026-05-05/` - 旧 full GRAG 版の退避資料

root の `BAK/` は削除済みであり、参照先にしない。

## 現在の正本

現在の正本は軽量版 SPEC-grag である。

- property graph / entity relation graph / hierarchical cluster は標準経路にしない
- Purpose と Core Concept は人間更新対象
- `/spec-core` は Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor、Source Retrieval Index、Conflict Review Items を扱う
- `/spec-inject` / `/spec-realign` では Agent / LLM が Agentic Search と制約生成の主体になる
- CLI は保持物と検索 API を提供する。探索方針と今回必要な制約の最終生成は Agent / LLM が担う
- Core Concept 自動更新と Core Concept 乖離通知は標準契約に入れない

旧 full GRAG 版の資料と実装は `archive/full-grag-2026-05-05/` に退避されている。参照は比較・復旧・背景確認に限り、現在の設計判断の正本にしてはいけない。

## 不変ルール

### ルール 1: 土台がない状態で設計を議論しない

実装方式、外部依存、LLM provider、embedding provider、Qdrant / FlagEmbedding の API など、設計に影響する事実は一次資料または最小実行スパイクで確認してから採用する。

未確認の内容は「未確認」と明示し、推測で仕様を埋めない。特に推論カット後に変わり得る API / package version / CLI 挙動は、現在の資料や実行結果で確認する。

### ルール 2: 資料には決定内容と TODO のみを書く

`doc/EXTERNAL_DESIGN.ja.md` は仕様書であり、作業メモではない。

README は外部利用者向けの概要、最短導入、主要コマンド、正本文書への入口に限定する。

README に置くもの:

- プロジェクトの概要
- 前提となる標準構成の短い説明
- インストールとプロジェクト導入の最短手順
- 主要コマンド一覧
- Agent 入口の概要
- 設計文書へのリンク

書くもの:

- 決定された契約
- 現時点での方針
- 実装前に解くべき未決事項

書かないもの:

- 議論の時系列
- 過去案の長い経緯
- Agent の作業メモ
- 最初のユースケース固有の事情

旧設計の履歴は archive に置く。新しい `doc/` へ戻さない。

### ルール 3: 実装より先に責務境界を考える

設計判断・実装判断では、先に「誰が何を持つか」を整理する。

- Human: Purpose / Core Concept の更新、Conflict Review Item の判断、最終仕様判断
- Agent / LLM: 会話区間の解釈、検索キー生成、Agentic Search、今回必要な制約生成、回答生成
- CLI / SPEC-grag: 設定読込、section hash / freshness 管理、保持物生成、検索 API、参照 API、Conflict Review Item の保存
- Retrieval / vector store: 候補検索の基盤。判断主体ではない

CLI は Agentic Search の探索方針を自律的に決めない。Agent / LLM は CLI が返す保持物と検索結果を使って探索する。

### ルール 4: Source Specs の生テキストを無制限に混ぜない

Agent / LLM は Agentic Search、検索キー生成、根拠確認のために必要な Source Specs snippet を読んでよい。

ただし、読んだ本文を未整理のまま最終回答の前提へ混ぜてはいけない。最終的に使う制約は、今回の課題に必要なものとして生成し、Purpose / Core Concept / Source Specs / stale でない resolved Conflict Review Item の根拠を示す。

Search Keys、Section Summary、Related Sections、Chapter Key Anchor は参照補助であり、単独で制約根拠にしてはいけない。

### ルール 5: pending conflict を無視して進まない

status が `pending` の Conflict Review Item が残っている場合、`/spec-inject` と `/spec-realign` は通常の制約生成や回答生成へ進まない。

dirty / stale と pending conflict が同時にある場合、先に `/spec-core` または watcher で保持物を更新し、更新後も残る pending conflict だけを人間判断対象にする。

resolved だが未反映の Conflict Review Item は、`base_source_hashes` と `valid_scope` に従う。`stale_resolution` になったものを制約根拠にしてはいけない。

### ルール 6: 新しい用語・仮称を出す時は範囲を先に明示する

設計相談や監査中に、Agent が新しい用語・仮称・整理ラベルを突然導入してはいけない。新しい用語が必要な場合は、先に次を明示する。

- 仮称か既存用語か
- 意味
- 含むもの
- 含まないもの
- 既存概念との差分
- 未決事項

範囲が曖昧なまま、その用語を前提に設計判断・実装判断へ進まない。

例:

```text
仮称: Section Context JSON
意味: section ごとの目的・要約・重要制約・関連先を JSON sidecar として持つ軽量案
含む: purpose, summary, key_constraints, related_sections, source span
含まない: property graph, 多段 traversal, cluster snapshot
既存概念との差分: Core Concept は人間更新の原則本文、これは retrieval / injection 用 metadata
未決: related_sections の生成上限と検証方法
```

### ルール 7: 実装完了ガードを守る

Agent は、形だけの実装や smoke / fake provider の通過だけを根拠に「完了」と報告してはいけない。

production 経路または通常実行経路に入るコードでは、次を未完了として扱う。

- `TODO`、`NotImplementedError`、`pass`、`...`、空の戻り値だけで成立する関数・メソッド
- 入力を実際に処理せず、固定値・mock data・fixture 相当の値だけを返す実装
- 実 provider / 実 storage / 実 artifact を扱うべき箇所で fake provider 相当の処理に逃げる実装
- `try/except pass`、広すぎる `except Exception`、失敗を diagnostics なしに握りつぶす実装
- 期待される validation、異常系、境界条件を省略したまま正常系だけを通す実装

ただし、明示的な test fixture、fake provider、smoke 専用経路、仕様書に未決事項として記録された TODO は禁止対象ではない。その場合も、報告では production / 通常実行経路の未完了範囲を明示する。

完了報告前に、Agent は次を自己確認する。

- 実装した関数が入力・設定・状態・artifact を実際に読んで処理しているか
- fake / smoke 専用処理が通常実行経路へ混入していないか
- 異常系が silent failure になっていないか
- 未実装・仮実装・未検証の範囲を報告に分けて書いているか

### ルール 8: 失敗を計画へ反映してから修正する

Agent は、実装・検証・監査で失敗、skip、未実行、過大申告、flaky、環境差分、設計との不整合を見つけた場合、単に口頭で説明して進めてはいけない。外部契約変更や人間判断が不要な範囲では、次の loop を止めずに回す。

```text
失敗検出 -> 実装修正 -> 再テスト -> 報告
```

必須事項:

- 失敗原因が実装 bug、test expectation のズレ、fixture 不足、環境設定不足、外部 provider の仕様差分のどれかを切り分ける
- fake / smoke / default profile の passing で、失敗した real / production 経路を完了扱いしない
- 修正後は、失敗を再現した test または同等の targeted test を再実行し、必要なら default profile と real / local-service profile を分けて再実行する
- 再テストできない場合は、その理由を未完了 TODO として報告に残す

禁止事項:

- 「これは環境問題」「後で確認」「TODO に残す」だけで進む
- full suite や real provider の失敗を、関係ない default passing で相殺して報告する
- flaky を 1 回の単独 passing だけで解消扱いにする
- 人間判断不要な修正を、確認待ちにして止める

### ルール 9: 監査指摘は全件 disposition を残す

Agent は、人間または別 Agent から監査結果、レビュー結果、懸念点、修正候補、過大申告の疑いを受け取った場合、指摘をまとめて消化した扱いにしてはいけない。各指摘に ID を付け、少なくとも次の disposition を残す。

- 指摘 ID
- 指摘要約
- 判定: `採用` / `部分採用` / `不採用` / `保留` / `既対応`
- 理由: 設計根拠、実装根拠、または不採用理由
- 対応: 修正したファイル、追加した test
- 証跡: 実行した command、test 結果、または確認した file / line
- 残 TODO: 未解決の場合の完了条件と次アクション

必須事項:

- 不採用または既対応と判断する場合も、根拠となる実装箇所または test を明示する
- 複数指摘のうち一部だけ修正した場合は、修正済みと未修正を分けて報告する
- 未検証の指摘は `不採用` にしない。`保留` または残 TODO として扱う
- 最終報告では「何を直したか」「何を直していないか」「何が未検証か」を指摘 ID 単位で読める形にする

禁止事項:

- 「主なものは対応済み」「大きな問題は解消」など、指摘単位の対応が追えない報告をする
- 採用しなかった指摘を理由なしに省略する
- 未検証のまま「問題なし」と報告する
- test passing の総数だけを示し、どの指摘の再テストになっているかを示さない

### ルール 10: 最終報告では完了範囲と残範囲を必ず分ける

Agent は、作業終了時の最終報告で「何が終わったか」と「何が残っているか」を必ず分けて書く。作業が小さい場合でも、未実行・未検証・対象外・次 TODO があるなら省略してはいけない。

最終報告には、少なくとも次を含める。

- 完了したこと: 変更した仕様、実装、test、docs
- 残したこと: 未修正、未実装、未解決、次に必要な作業
- 未検証のこと: 実行していない test、skip、環境未確認、real provider / local-service 未確認
- 判定できないこと: 人間判断待ち、外部環境待ち、再現待ち
- 証跡: 実行した command、test 結果、確認した file / line

報告では、次の区分を崩さない。

- 実装済み
- `none` / `fake` profile で passing
- `local-service` / `real-smoke` で passing
- skipped / 未実行
- 残 TODO

禁止事項:

- 「完了」「対応済み」「大丈夫」とだけ書き、残範囲を省略する
- 未実行の test や skip を、関係ない passing の後ろに隠す
- 実装済みと検証済みを同じ意味で扱う
- 本運用 readiness 未完了のまま「本運用可能」と報告する

### ルール 11: 合理的理由のない保留を禁止する

Agent は、指摘や残 TODO を、合理的な理由なしに残してはいけない。既存契約の範囲内で、人間判断も外部ブロッカーも不要な修正・検証は、その場で実施する。

残してよい理由は次に限る。

- 人間判断が必要: Purpose / Core Concept、Conflict Review Item の決定、仕様方針の選択など
- 外部ブロッカーがある: 認証、service 権限、network、provider 障害、hardware / model cache、長時間運用待ちなど
- 契約変更が必要: `doc/EXTERNAL_DESIGN.ja.md` の方針変更を伴う
- 既存差分を壊す危険がある: user 変更、archive 退避、generated 差分と衝突し、独断で編集すると巻き戻しになる
- 再現性が不足している: flaky / sporadic failure で、追加の再現条件整理が必要
- スコープ外である: ユーザーの今回依頼から外れる。ただし、本運用完了判定や安全性に関わる場合は残 TODO に記録する

残す場合は、最終報告で次を明示する。

- 残す項目
- 残す理由の分類
- なぜ今この場で進められないか
- 完了条件
- 次に実行すべき command または作業

禁止事項:

- 「後でやる」「時間切れ」「今回はここまで」だけを理由に、人間判断不要な作業を残す
- 合理的な反対理由がないのに、監査指摘を `保留` や残 TODO にする
- 実装できるが test を回していないだけの状態を、完了扱いまたは既対応扱いにする
- 未検証を、単なる報告の省略で見えなくする

### ルール 12: 報告・設計文書は人間のプロジェクトオーナー向けに書く

Agent は、報告書と設計文書を人間のプロジェクトオーナーが読む文書として書く。別の Agent 向けの内部通信として書いてはいけない。

#### 重要な記述の必須要素

重要な記述には、次の問いへの回答を含めなければならない。

- 主語は何か
- どこに適用される話か（ファイル、コマンド、設定、API、モジュール）
- それを実行すると何が変わるのか
- なぜ重要なのか
- 人間が次にする必要があることは何か（ある場合）

いずれかに答えられない記述を、あたかも明確であるかのように書いてはならない。

#### 内部ラベル・省略表現の展開義務

圧縮された内部ラベル、省略表現、抽象的な分類名を使う場合は、同じ段落内で直ちに次の形式で展開する。

- 人間向けの意味
- なぜ重要か
- 具体的な次の対応（ある場合）

次の語は自明であると仮定してはならない。使う場合は初出で定義する。

`profile`、`root`、`artifact`、`generated state`、`smoke`、`default suite`、`degraded`、`stale`、`provider`、`runtime`、`integration`

特に test の skip を報告する場合は、`default skip 検証` のような短縮表現を使わず、次を明記する。

- どの test file / test function が skip されたか
- その test は何を確認するものか
- なぜ今回の実行では skip されるのか
- skip が完了判定を妨げるか

#### 内部ラベルを主要表現にしない

Agent は、報告の見出し、要約、完了判定、残 TODO の主語に、test profile 名、CI profile 名、内部分類名、略称だけを置いてはいけない。先に人間が対象を理解できる具体的な説明を書き、その補足として内部ラベルを併記する。

禁止例:

- `full local-service / real-smoke suite`
- `default profile passing`
- `provider boundary fixed`
- `runtime path covered`
- `generated state remaining`
- `default skip verification`
- `default skip 検証`

良い例:

```text
pytest 全体を、実 Codex / Claude CLI、起動済み Qdrant、
FlagEmbedding BGE-M3 を使うテストも含めて実行した。
補足: この実行は test profile 名では `real-smoke` と
`local-service` を有効にした状態である。
```

```text
通常の `spec-grag core` 実行で、`.spec-grag/config.toml` の
`[llm]` から Codex / Claude provider を構築する経路を確認した。
補足: これは provider boundary の確認に相当する。
```

```text
プロジェクト直下に、以前の実行で作られた `.spec-grag/`
ディレクトリが残っている。
影響: root skeleton test は、生成済み runtime state が無いことを
期待するため失敗する。
```

#### 禁止される表現と許可条件

次の表現は、報告・設計文書で単独では使えない。

- 「orchestrator によって処理される」
- 「default path でカバーされる」
- 「後で対応する」
- 「profile 固有」
- 「root の状態」
- 「artifact のライフサイクル」
- 「provider 統合」
- 「real smoke 経路」
- 「local service 経路」
- 「full local-service / real-smoke suite」
- 「default profile passing」
- 「provider boundary fixed」
- 「runtime path covered」
- 「generated state remaining」
- 「default skip verification」
- 「default skip 検証」
- 「通常フロー」

ただし、直後に次をすべて展開する場合は使ってよい。

- 責任を持つファイルまたはモジュール
- 実際のコマンドまたは設定
- 通常実行時の挙動
- テスト時の挙動
- 人間による判断が必要な場合は、その判断内容

#### 文の完了判定

人間の読者が次の問いに答えられない文は、出力前に書き直す。

- 具体的に何について述べているのか
- それはどこにあるのか
- それはコード、設定、テスト、通常実行時の挙動、設計意図のどれなのか
- それは完了しているのか、未完了なのか
- 次に必要なコマンド、ファイル、作業は何か
- それは完了判定を妨げるのか

#### 報告前チェック

Agent は最終報告、進捗報告、設計文書更新の前に、各見出しと箇条書きについて次を確認する。

- その文の主語は、人間が見て具体物を想像できるか
- `profile`、`smoke`、`runtime`、`provider`、`artifact` などの語だけで意味を成立させていないか
- 実際のファイル名、コマンド、設定名、テスト名のいずれかが書かれているか
- その結果が完了判定に影響するかを書いているか

上記に答えられない場合は、内部ラベルを補足へ下げ、人間向けの具体説明を先に書く。

#### 悪い例と良い例

悪い例:

```text
full default suite was not rerun
root has generated artifacts
handled later
local-service profile is skipped
implementation is mostly done
this is a smoke/test profile setting
graph state may be stale
source retrieval is degraded
```

良い例:

```text
full pytest テストスイートは実行していません。
理由: プロジェクトディレクトリ /absolute/path/to/project に、
以前の実行で生成された .spec-grag/ が既に存在しており、
テスト結果に影響する可能性があるためです。
次の対応: mv .spec-grag .spec-grag.bak で退避してから、
pytest -q を実行してください。
```

```text
Qdrant に依存するテストはスキップされました。
理由: これらのテストを実行するには、ローカルで Qdrant サービスが
起動している必要があるためです。
これは最終完了を妨げます。なぜなら、vector-store 連携が
まだ検証されていないためです。
次の対応: Qdrant を起動し、
SPEC_GRAG_LOCAL_SERVICE=1 pytest -q ... を実行してください。
```

```text
Source retrieval は degraded 状態です。
意味: システムは根拠候補となる source section を見つけましたが、
回答生成前にそのすべてを分類できませんでした。
リスク: 回答が関連する制約を見落とす可能性があります。
次の対応: <exact path> にある未分類項目を確認してください。
```

### ルール 13: 仕様書には読者が自力で導けない情報だけを書く

仕様書の記述は「定義文から読者が自力で導けない情報」だけを書く。定義文で確定している内容を繰り返さない。

判定基準: **定義文を読んだ読者がこの行を自力で導出できるか?**

- 導出できる → 書かない (認知コストだけ上がる悪)
- 導出できない → 書く (もれなく記述すべき独自情報)

具体例:

- Source Specs の定義が「`[sources].include` に一致する Markdown 文書」であるとき、「含むもの: 仕様章ファイル / section 化された本文」は定義から自明なので書かない
- Purpose と Core Concept の境界は名前だけでは分からないので「含むもの / 含まないもの」で境界を明示する意味がある
- Section Search Keys と Section Identifiers の分離は設計判断であり名前から自明でないので、何を入れて何を入れないかを書く意味がある

禁止事項:

- 近隣セクションの形式 (含む / 含まない テンプレート等) を機械的に踏襲して、自明な内容を列挙する
- 「体裁の統一」を理由に情報密度を下げる
- 定義文と同じ内容を表現を変えて繰り返す

### ルール 14: 外部設計書はソースコードを読んだことがない読者に通じる言葉で書く

外部設計書 (`doc/EXTERNAL_DESIGN.ja.md`) の文は、ソースコードを読んだことがない読者に通じなければならない。内部の実装構造名 (関数名、変数名、JSON field 名、enum 値、内部モジュール名) を使っている場合、その文は内部設計の言葉で外部契約を書いてしまっている。

判定基準: **この文は、ソースコードを読んだことがない読者に通じるか?**

- 通じる → 外部設計書に書いてよい
- 通じない → 内部設計書に書く。外部設計書では読者が体験する動作 (何が起きるか、何を見るか、何をすればよいか) で書き直す

悪い例:

- 「freshness gate を通す」(gate は内部実装の構造名)
- 「freshness report の `status` が `fresh` の場合だけ続行する」(report というオブジェクトの存在を前提にしている)
- 「`blocking_reasons[]` に `dirty_or_stale_source` が入る」(JSON field 名と enum 値)

良い例:

- 「保持物が古い場合、`/spec-inject` は停止し、理由と対処方法を表示する」
- 「Source Specs が変更されたがまだ `/spec-core` で更新されていない場合、`/spec-inject` は停止する」

動作が外部契約であることと、その記述が外部設計書として適切であることは別の判定である。動作は外部でも、記述が内部用語を使っていれば書き直す必要がある。

外部設計書の書き換えルールの詳細は `agent_doc/EXTERNAL_DESIGN_RULES.ja.md` の「契約内容の保護」を参照。

### ルール 15: 機能を廃止する場合は根絶する

機能を廃止する場合、stub / disabled / コメントアウト / fallback 等の「中身を消して名前を残す」形にしてはいけない。次のすべてを grep で網羅し、削除する。

- artifact 名 / フィールド名 / 設定 key / 環境変数名 / CLI flag 名
- 生成処理 / 書き込み処理 / 読み込み処理
- 参照箇所 (他コードからの import / call / 型注釈)
- テストファイル / テストフィクスチャ / `@pytest.mark.skip(reason="...dormant...")` のような skipped test
- ドキュメント (外部設計 / 内部設計 / README / 設定 template / コメント)

「将来戻すかもしれない」は理由にしない。Git history で戻せる前提で削除する。

廃止後の必須検証:

```text
git grep <廃止した名前>
git grep -nE "stub|dormant|legacy|disabled|deprecated|fallback"
```

`git grep <廃止した名前>` は 0 件であること。`stub|dormant|legacy|disabled|deprecated|fallback` の hit はすべて「目的のある記述か / 削除し漏れたゴミか」を判定する。判断つかなければユーザーに確認する。

禁止事項:

- artifact 名や設定 key を残したまま中身を空にする
- 関数本体を `pass` または「disabled」コメントだけにして残す
- `@pytest.mark.skip(reason="...dormant...")` で test を残す (削除する)
- ドキュメントに「廃止された ○○」を後置きで残す (削除して history に任せる)

### ルール 16: 新規追加時は既存責務との整合を先に確認する

新しい artifact / フィールド / 設定 key / CLI flag / 用語を追加する場合、既存の同種要素を grep して責務重複がないか確認する。重複する場合、新規追加ではなく既存を拡張する。

確認例:

- 新 artifact 追加: `git grep ARTIFACT_FILENAMES` で既存 artifact 一覧確認
- 新 CLI flag 追加: `git grep "parser.add_argument"` で重複確認
- 新 settings key 追加: `git grep "\[<table>\]"` で既存 key 確認
- 新用語追加: 外部設計書 §2 (用語と範囲) を grep で確認

「似て非なる」要素を増やさない。既存と意味が近いなら既存を拡張する。意味が離れているなら、その差を明示してから追加する (CLAUDE.md ルール 6 と併用)。

### ルール 17: 機能 → 配置 のマッピングを doc に保持する

artifact / 設定 / 状態管理の物理配置は、外部設計書または内部設計書に「機能 → 配置」の対応表を必ず持つ。表に無い artifact / フィールドは作らない。新規追加時は表に追記してから実装に入る。

対応表は **唯一の真実** として運用する。表と実装に乖離が生じた場合、どちらが正しいかを先に確定する。

例: `doc/EXTERNAL_DESIGN.ja.md` §4.1「保持物の物理配置」が SPEC-grag の artifact マッピング表。これに無い artifact を実装が生成している場合、ルール 15 (廃止 = 根絶) を適用する。

## 退避資料

旧 full GRAG 版は次に退避している。

```text
archive/full-grag-2026-05-05/
```

この退避資料は歴史的バックアップであり、現在の正本ではない。現在の仕様判断は `doc/EXTERNAL_DESIGN.ja.md` を優先する。
