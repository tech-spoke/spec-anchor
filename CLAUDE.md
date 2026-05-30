# spec-anchor Agent Guide

このファイルは spec-anchor リポジトリで作業する Agent 共通の不変ルールを記録する。Claude / Codex / その他 Agent は同じルールに従う。

## 必読ドキュメント

新しいセッションでは、まず次をこの順序で読む。

1. `doc/EXTERNAL_DESIGN.ja.md` - 軽量版 SPEC-anchor の外部契約
2. 本ファイル `CLAUDE.md` - Agent 共通の不変ルール
3. `AGENTS.md` - 報告ルール、設計書の記述ルール (`agent_doc/` 配下の記述ルールへの入口)
4. `doc/TODO/*.ja.md` - 進行中の課題 TODO ファイル群 (各課題は「全体目的 + sub task」の構造)。新規課題は `doc/TODO/TODO_template.ja.md` を雛形として `doc/TODO/<topic>.ja.md` を作成する。実装着手前に該当 sub task の検証条件・scope・依存を確認する。完了済み課題 TODO は `doc/TODO/完了済みTODO/<YYYY-MM-DD>_<topic>.ja.md` を参照
5. 必要な場合のみ `archive/full-grag-2026-05-05/` - 旧 full GRAG 版の退避資料

root の `BAK/` は削除済みであり、参照先にしない。

## 現在の正本

現在の正本は軽量版 SPEC-anchor である。

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
- CLI / SPEC-anchor: 設定読込、section hash / freshness 管理、保持物生成、検索 API、参照 API、Conflict Review Item の保存
- Retrieval / vector store: 候補検索の基盤。判断主体ではない

CLI は Agentic Search の探索方針を自律的に決めない。Agent / LLM は CLI が返す保持物と検索結果を使って探索する。

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
通常の `spec-anchor core` 実行で、`.spec-anchor/config.toml` の
`[llm]` から Codex / Claude provider を構築する経路を確認した。
補足: これは provider boundary の確認に相当する。
```

```text
プロジェクト直下に、以前の実行で作られた `.spec-anchor/`
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
以前の実行で生成された .spec-anchor/ が既に存在しており、
テスト結果に影響する可能性があるためです。
次の対応: mv .spec-anchor .spec-anchor.bak で退避してから、
pytest -q を実行してください。
```

```text
Qdrant に依存するテストはスキップされました。
理由: これらのテストを実行するには、ローカルで Qdrant サービスが
起動している必要があるためです。
これは最終完了を妨げます。なぜなら、vector-store 連携が
まだ検証されていないためです。
次の対応: Qdrant を起動し、
SPEC_ANCHOR_LOCAL_SERVICE=1 pytest -q ... を実行してください。
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

TODO / 設計書 / 依頼文に「廃止」「削除」「根絶」「完全削除」「旧経路を残さない」と書かれている対象について、後方互換 shim、legacy fold、deprecated alias、旧入力の読み替え、旧 enum / 旧 reason の受理、旧 CLI flag の no-op 化を残してはいけない。これらは fallback の一種であり、根絶漏れとして扱う。

廃止対象の外部互換を本当に残す必要がある場合は、実装してから完了扱いにしてはいけない。先に人間へ「根絶条件に反する互換経路を残す契約変更が必要」と明示し、TODO / 設計書の scope を変更する。人間承認がない限り、互換 shim を残した状態は未完了である。

grep 検証をすり抜けるために、廃止対象名や禁止語を文字列連結、部分文字列、動的生成、別名化で残してはいけない。例: `"degraded" + "_optional_artifact"` のように `git grep degraded_optional_artifact` を 0 件に見せる書き方は禁止する。test でも production code でも同じく禁止する。

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
- 旧入力・旧 status・旧 reason を受け付ける後方互換 shim を、TODO の根絶条件に反して残す
- 廃止対象名を文字列連結や動的生成で隠し、grep 0 件を装う

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

例: `doc/EXTERNAL_DESIGN.ja.md` §4.1「保持物の物理配置」が SPEC-anchor の artifact マッピング表。これに無い artifact を実装が生成している場合、ルール 15 (廃止 = 根絶) を適用する。

### ルール 18: Agent は git worktree を作らない

Agent (Claude / Codex / その他) は `git worktree add` や Agent 起動オプションの `isolation: "worktree"` を含む、**新しい git worktree を作成する一切の操作を行わない**。worktree が必要な場合は、user が手動で作成・管理する。

#### 禁止する具体的操作

- `git worktree add` を Bash で直接実行する
- Agent ツール起動時に `isolation: "worktree"` パラメータを指定する
- general-purpose subagent / 任意の subagent を worktree 隔離で立ち上げる
- 既存 worktree の `git worktree lock` / `unlock` / 設定変更

#### なぜ禁止するか

複数 worktree が並存すると Agent は確実に次の失敗を起こす:

- **bash cwd が session 中に reset される** ことを忘れ、worktree のつもりが main repo を編集する (またはその逆)。grep / pytest / git status の結果が「どちらの worktree で取得したか」を見失う
- **「削除した / 修正した」報告の主語の scope (どの worktree か / どの branch か) を省く**。user が main を見ている時に Agent が worktree 側の grep 結果で「除去済み」と報告し、矛盾が発生する
- **post-merge 後の追加 commit が merge 元 branch / worktree directory に伝播しない** ことを失念する。user が worktree directory を IDE で開いていれば、merge 後に main へ commit した削除が worktree の file には反映されず、「言った通りになっていない」と user が気づく
- **worktree 内での `.venv` が main repo を指す symlink** であることを失念し、worktree のリファクタコードを実行したつもりが main の editable install を実行する。テスト結果が嘘になる
- **worktree 内で setup-project / spec-anchor core などを試運転すると、副作用 (`.spec-anchor/` / `docs/spec/` / `.claude/commands/` の生成) が worktree と main の両方を汚す**。後片付けが必ず漏れる

これらは過去 session で実際に複合発生した。`feedback_report_scope_branch.md` に詳細あり。

#### 例外

user が明示的に「worktree を作って」と指示した場合のみ、Agent は worktree を作ってよい。ただしその場合も:

- 作成した worktree path と branch 名を即座に user へ報告する
- 作業中に「いま自分はどの worktree で動いているか」を Bash 出力 (`pwd`) で毎回確認する
- merge 完了後は **即座に** `git worktree remove` + `git branch -D` で削除する

#### 代替策

worktree を使う動機の多くは「main を汚さずに作業したい」「コンテキストを隔離したい」だが、これは次で代替できる:

- topic branch (`git switch -c topic`) を main repo 上で切り、commit して merge / rebase する
- Agent 内では Phase / step 単位で **そのまま main repo に commit する** (ルール 8「失敗を計画へ反映」+ コミット境界を切る)
- subagent をコンテキスト消費削減目的で使う場合、`isolation` 未指定 (= main repo 上で動作) で起動する

### ルール 19: Codex subagent 呼び出しの完了判定と粒度

Claude main agent が `codex:codex-rescue` subagent 経由で Codex CLI に作業を委譲する場合、forwarder の `completed` 通知を Codex 本体の実装完了と取り違えてはいけない。完了判定は output file の Final report を確認するまで行わない。

#### 完了ステータスは 4 区分で扱う

Codex 呼び出し後の状態は次の 4 つに分けて報告する。3 つ以下に丸めない。

- **Forwarded**: `Agent` tool で `codex:codex-rescue` に依頼を投げた段階。forwarder subagent が起動した直後。Codex 本体はまだ動いていない可能性がある
- **Running**: Codex 子 process が残っている、または output file (`/tmp/claude-1001/.../tasks/<bg-id>.output`) が更新中
- **Completed**: 子 process が終了し、output file に Final report が存在し、依頼した checklist 全項目と `pytest -q --skip-external` 結果と `git grep` 検証が揃った状態
- **Interrupted / Incomplete**: output file が途中で終わっている、Final report が不在、checklist の一部が未実行。working tree が静止していてもこの状態でありうる

#### Codex 呼び出し後の必須確認手順

forwarder subagent の `task-notification status=completed` を受け取った直後に、次を順に実施する。

1. forwarder transcript (`/home/kazuki/.claude/projects/.../subagents/agent-<id>.jsonl`) を `python -c "import json; ..."` で解析し、最後の `assistant` text content と最後の `tool_result` を確認する。`Codex Task started in the background as task-...` / `Command running in background with ID: ...` は **完了通知ではない**。前者は Codex 起動通知、後者は Claude Code Bash tool の自動 background 切替通知である
2. forwarder が起動した Bash bg ID の output file (`/tmp/claude-1001/.../tasks/<bg-id>.output`) を最後まで読む。行数だけでなく末尾内容を確認する
3. Codex / `codex-companion.mjs` の running process を `ps -eo pid,etime,cmd | grep -iE 'codex|companion' | grep -v grep` で確認する。残っていれば Running、消えていれば output file の Final report 有無を確認する
4. Final report 10 項目 (依頼 prompt の Final report structure 節) が output に揃っているか、checklist と `git grep` / `pytest -q --skip-external` 結果でクロス確認する
5. 上記が揃わない場合、status は Interrupted / Incomplete。**working tree 監査へ進まず**、未完了範囲を報告する

#### Codex 依頼の粒度ルール

1 回の Codex task は **Claude Code Bash tool の前景タイムアウト以内** に終わる単位に分割する。タイムアウトを超えると Bash tool が自動的に background 切替を行い、その時点で forwarder の Bash 子プロセスが脱落し、Codex 子プロセスが kill / orphan 化されて中断する。

タイムアウト値は `~/.claude/settings.json` の `env.BASH_MAX_TIMEOUT_MS` で変更できる。本リポジトリ作業者の現設定 (2026-05-14 時点) は次の通り。

- `BASH_DEFAULT_TIMEOUT_MS`: 未設定 (= Claude Code default の 120000ms = 2 分)
- `BASH_MAX_TIMEOUT_MS`: `1800000` = 30 分

つまり 1 Codex task の上限はおおよそ **30 分以内に終わる単位** に分割する (codex:codex-rescue 側 Bash が `timeout` を明示指定して `BASH_MAX_TIMEOUT_MS` の上限を使う場合)。codex:codex-rescue が `timeout` を明示指定していない場合は default 2 分が効くので、その場合は実質 2 分以内に収める必要がある。実機で B-5 着手時に挙動を確認し、必要なら本ルール上限値を再調整する。

タイムアウト引き上げは無条件で全 Bash 呼び出しに適用したくないため (誤って hang したコマンドの検出を遅らせる副作用がある)、`BASH_DEFAULT_TIMEOUT_MS` は default のまま、`BASH_MAX_TIMEOUT_MS` だけ伸ばす方針を取っている。

粒度の指針:

- 1 task = 1 修正テーマ + 関連 unit test + 関連 grep 検証 + その task の Final report までを含む粒度に絞る
- 複数 CDX / R6 系の full pytest / R7 系の reversion verification / Final report 10 項目をすべて 1 task に詰め込まない
- R6 final pytest と R7 reversion verification は **Claude main agent が実行する**。Codex には実装と関連 pytest までを任せる。Claude が監督・検収役に回る分業を維持する (これはタイムアウト対策ではなく、検収と実装の分離契約として独立した理由がある)

#### 禁止する具体的操作

- forwarder `completed` を Codex 本体 `completed` と短絡して working tree 監査へ進む
- output file (`/tmp/claude-1001/.../tasks/<bg-id>.output`) を最後まで読まずに完了判定する
- Final report 不在のまま「CODEX が手抜きした」と推論する。中断と手抜きは別物として扱う
- 現設定の `BASH_MAX_TIMEOUT_MS` を超える見込みの bundle を 1 task で投げる (粒度過大)
- `agents.job_max_runtime_seconds` を増やせば打ち切りが防げると仮定する。これは Codex の subagent worker 用設定で、Claude Code Bash tool の前景タイムアウトとは別系統

#### なぜこのルールが必要か

2026-05-14 session で次の事故が 2 回起きた。

**1 回目** (CDX-001/003/004/006/007 bundle): Claude main agent が CDX-001/003/004/006/007 + R6 final pytest + R7 reversion verification + Final report 10 項目を 1 つの bundle prompt で `codex:codex-rescue` に依頼した。forwarder が約 11 分後に `completed` を返し、その時点で working tree は CDX-001/003/004/006 まで実装が入った状態で静止していた。Claude は forwarder completed = Codex completed と判断し、`tests/test_retrieval_index.py` が未編集なのを見て「CODEX が CDX-003 / CDX-007 を手抜きした」と推論した。

実際は forwarder が起動した `codex-companion.mjs task` が当時の Bash tool 前景タイムアウト (10 分 hard cap と思い込んでいた、後述) を超えた結果、Claude Code Bash tool の自動 background 化が発動し、forwarder の Bash 子プロセスが脱落、Codex 子プロセスが kill された。output file (`bb3cnpwvm.output`, 183 行) は Final report 直前の CDX-006 pytest pass 行で終わっており、CDX-007 / R6 / R7 / Final report は実行されていなかった。

GPT (ChatGPT) からの指摘で初めて output file を最後まで読み、Claude が「完了判定誤認」と「手抜き誤推論」の両方を起こしていたことが判明した。

**2 回目** (B-4 task): その後 B-4 task 1 つだけを Codex に投げた時も、約 12 分で同じ症状 (forwarder completed・Codex 本体 kill・Final report 不在) が再発した。Claude main は監査で逸脱 2 ファイル (`spec_anchor/retrieval_index.py` / `spec_anchor/section_payload.py` への scope 外 fallback shim 追加。CODEX が pytest を venv 外で実行して見た幻の 8 件 ImportError を「修正」した) を検出し revert した。同時に、Bash tool のタイムアウトを「仕様上 600000ms = 10 分が hard cap、変更不可」と誤認していたことも user 指摘で発覚した。

実際は `BASH_DEFAULT_TIMEOUT_MS` / `BASH_MAX_TIMEOUT_MS` 環境変数で延長可能であり、現在 `BASH_MAX_TIMEOUT_MS=1800000` (30 分) を設定済 (2026-05-14)。これにより、`codex:codex-rescue` 内部 Bash が timeout 明示指定するなら 30 分まで auto-background されない。明示指定しない場合は default 2 分のままなので、その挙動は B-5 着手時に実機確認する必要がある。

詳細は `feedback_codex_invocation_protocol.md` に保存。

### ルール 20: 実装を他 Agent へ委譲する場合は委譲・監査ガイドに従う

Agent (Claude main / 人間) が他の Agent へ実装を委譲する場合、委譲先に応じて次のガイドの依頼ルールと受け取り後の監査チェックリストに従う。委譲先の自己申告 (「完了しました」「テスト通過」) を完了の根拠にせず、必ず実 diff・実コードで裏取りする。

- `codex:codex-rescue` 経由の CODEX: `agent_doc/CODEX_DELEGATION_GUIDE.ja.md`
- `Agent` tool 経由の CLAUDE サブエージェント: `agent_doc/CLAUDE_SUBAGENT_DELEGATION_GUIDE.ja.md` (CODEX ガイドと共通部分が多く、Claude 特有の傾向 = TODO/placeholder 完了・推論カットによる調査不足・サマリー≠実変更 を追加でカバー)

特に次を必須とする (詳細と理由は同ガイド参照)。

- **外部仕様書 (`doc/EXTERNAL_DESIGN.ja.md` / `doc/EXTERNAL_SPEC_DRAFT.ja.md`) の反映は、実装の監査が終わってから行う。** 実装と仕様反映を同じ CODEX task でやらせない (phantom 仕様の混入を防ぐ)。外部仕様書を更新する task の prompt には「仕様の発明を禁止する / docs に追加してよいのは実装済みかつテストで観測可能な挙動だけ / `code`・`test`・`TODO` に根拠の無い field・status・reason・route・config key を追加してはならない」を必ず入れる。
- 真因不明 / 再現困難の調査を simple prompt で委譲する場合は **root cause exploration に限る**。同じ task で修正・仕様変更・TODO close を許可せず、出力を hypothesis / evidence / reproduction steps / proposed next test に限定する。
- 受け取り後は、phantom フィールド (doc 記載 × コード未 emit)、根絶残骸 (廃止概念の write-only 死蔵フィールド)、grep 回避の文字列連結 hack、早期リターン dead code、smoke / fake の production 混入を機械的に監査する。契約ドキュメントを信頼基準にせず、人間承認の TODO とコードの実挙動を基準にする。

関連: ルール 7 (実装完了ガード)、ルール 15 (廃止 = 根絶)、ルール 19 (Codex subagent 完了判定)。

## 実行環境メモ

Agent が頻繁に使うコマンドの実行系について、本リポジトリ作業時の注意。

### Python は `python3` を使う

本リポジトリのターミナルでは `python` ではなく `python3` を使う。`python` は環境によって存在しないか別バージョンを指す可能性がある。Agent が inline で Python スクリプトを実行する場合も次のように書く:

```bash
python3 -c "..."
python3 << 'EOF'
...
EOF
python3 path/to/script.py
```

pytest も venv 経由で `python3 -m pytest` または `.venv/bin/pytest` を呼ぶ。`python` 直呼びは禁止。

## 退避資料

旧 full GRAG 版は次に退避している。

```text
archive/full-grag-2026-05-05/
```

この退避資料は歴史的バックアップであり、現在の正本ではない。現在の仕様判断は `doc/EXTERNAL_DESIGN.ja.md` を優先する。
