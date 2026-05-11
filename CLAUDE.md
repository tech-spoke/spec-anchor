# spec-grag Agent Guide

このファイルは spec-grag リポジトリで作業する Agent 共通の不変ルールを記録する。Claude / Codex / その他 Agent は同じルールに従う。

## 必読ドキュメント

新しいセッションでは、まず次をこの順序で読む。

1. `doc/EXTERNAL_DESIGN.ja.md` - 軽量版 SPEC-grag の外部契約
2. `doc/DESIGN.ja.md` - 軽量版 SPEC-grag の内部設計
3. 本ファイル `CLAUDE.md` - Agent 共通の不変ルール
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

`doc/EXTERNAL_DESIGN.ja.md` と `doc/DESIGN.ja.md` は仕様書であり、作業メモではない。

README は外部利用者向けの概要、最短導入、主要コマンド、正本文書への入口に限定する。README を RUNBOOK として扱ってはいけない。

README に置くもの:

- プロジェクトの概要
- 前提となる標準構成の短い説明
- インストールとプロジェクト導入の最短手順
- 主要コマンド一覧
- Agent 入口の概要
- `doc/RUNBOOK.ja.md` や設計文書へのリンク

README に置かないもの:

- 本運用 Readiness の詳細手順
- restart / troubleshoot の詳細
- Diagnostics プライバシーの詳細設定
- Production Readiness Report Template
- test profile / smoke profile の詳細説明

これらの詳細は `doc/RUNBOOK.ja.md` に置く。README に運用詳細を要求する test / plan が失敗した場合は、README へ追記せず、先に `doc/TEST_SPEC.ja.md` と該当 test の契約を RUNBOOK 対象へ直す。

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
失敗検出 -> 計画 / テスト仕様の状態更新 -> 実装修正 -> 再テスト -> 報告
```

必須事項:

- 失敗や未検証が、既存の `doc/IMPLEMENTATION_PLAN.ja.md` / `doc/TEST_SPEC.ja.md` の項目で表現できるか確認する
- 表現できる場合は、該当する Gate / T 項目 / 検証行を `[ ]`、`[~]`、`[!]`、残 TODO、または証跡更新として先に反映する
- 表現できない場合は、新しい Gate / T 項目 / 検証行 / TODO を追加し、完了条件を明確にする
- 失敗原因が実装 bug、test expectation のズレ、fixture 不足、環境設定不足、外部 provider の仕様差分のどれかを切り分ける
- fake / smoke / default profile の passing で、失敗した real / production 経路を完了扱いしない
- 修正後は、失敗を再現した test または同等の targeted test を再実行し、必要なら default profile と real / local-service profile を分けて再実行する
- 再テストできない場合は、その理由を未完了 TODO として計画と報告の両方に残す

禁止事項:

- 「これは環境問題」「後で確認」「TODO に残す」だけで、計画やテスト仕様を更新せずに進む
- 失敗した検証行を `[x]` のままにする
- full suite や real provider の失敗を、関係ない default passing で相殺して報告する
- flaky を 1 回の単独 passing だけで解消扱いにする
- 人間判断不要な修正を、確認待ちにして止める

### ルール 9: 監査指摘は全件 disposition を残す

Agent は、人間または別 Agent から監査結果、レビュー結果、懸念点、修正候補、過大申告の疑いを受け取った場合、指摘をまとめて消化した扱いにしてはいけない。各指摘に ID を付け、少なくとも次の disposition を残す。

- 指摘 ID
- 指摘要約
- 判定: `採用` / `部分採用` / `不採用` / `保留` / `既対応`
- 理由: 設計根拠、実装根拠、または不採用理由
- 対応: 修正したファイル、追加した test、更新した計画 / テスト仕様
- 証跡: 実行した command、test 結果、または確認した file / line
- 残 TODO: 未解決の場合の完了条件と次アクション

必須事項:

- 重大度が高い指摘、実動作検証、provider boundary、fake / smoke 混入、テスト過大申告、flaky は、口頭だけで処理せず `doc/IMPLEMENTATION_PLAN.ja.md` または `doc/TEST_SPEC.ja.md` に状態を反映する
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
- 契約変更が必要: `doc/EXTERNAL_DESIGN.ja.md` または `doc/DESIGN.ja.md` の方針変更を伴う
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

### ルール 13: 外部設計書のチェックボックスは evidence 付きでのみ `[x]` にする

`doc/EXTERNAL_DESIGN.ja.md` の assertion 行には `- [ ]` または `- [x]` のチェックボックスを付ける。これは「外部契約のうち実装と検証が完了している項目」を仕様書自身が網羅状態として記録するためのダッシュボードである。

#### `[x]` を付けてよい条件

次のすべてを満たす場合だけ `[x]` を付ける。

- 実装している file path と行番号を 1 箇所以上明示できる
- 検証したテスト名 (テストファイル + テスト関数名) を 1 つ以上明示できる。テストで検証できない項目は、手動検証手順または運用検証ログを明示する
- 該当 evidence をチェックボックス直下に短い箇条書きで併記する

evidence を併記しない `[x]` は禁止する。`[x]` を付けたが evidence を書けない場合は `[ ]` に戻す。

例:

```markdown
- [x] relation_hint は `depends_on / impacts / prerequisite / same_policy / see_also` のみ
  - 実装: spec_grag/related_sections.py:59-65 (ALLOWED_RELATION_HINTS)
  - 検証: tests/test_related_sections.py::test_relation_hint_excludes_conflicts_with
```

#### `[ ]` のままにしてよい条件

次のいずれかに該当する項目は `[ ]` のままにしてよい。

- 実装が未完了
- テスト・手動検証が未実施
- 検証経路が外部 service / 人間判断に依存し、未検証
- 仕様書の該当行が assertion ではなく説明文 / 経緯記述である (この場合はチェックボックスを付けない)

#### 禁止事項

- evidence を確認せずに `[x]` に変更する (CLAUDE.md ルール 7「実装完了ガード」の延長)
- 自動化したい都合で「assertion ではない説明文」にチェックボックスを付ける
- evidence の file:line を架空のものにする、または「らしい」だけで実在を確認しない (ルール 1)
- `[x]` 化と同時に対応する `doc/IMPLEMENTATION_PLAN.ja.md` / `doc/TEST_SPEC.ja.md` を更新しない
- 仕様書全体の `[ ]` を一括で `[x]` に変える運用 (差分が追えなくなる)

#### 運用フロー

1. 仕様書を書いた / 改訂したら、新規 assertion 行に `- [ ]` を付ける
2. 実装完了したら、該当行を `- [x]` + evidence に書き換え
3. PR レビュー時に、変更された `[x]` の evidence を audit する。架空・不一致なら `[ ]` に戻す
4. 完了率は `git grep -c "^- \[ \]" doc/EXTERNAL_DESIGN.ja.md` で機械的に追跡

#### 仕様書の前提

`doc/EXTERNAL_DESIGN.ja.md` には外部契約として書くべき内容のみを置く。テスト fixture、過去の議論、内部設計、運用 RUNBOOK などは外部契約ではないため checkbox 化対象から外す。これらは `doc/TEST_SPEC.ja.md` / `doc/DESIGN.ja.md` / `doc/RUNBOOK.ja.md` 等に分離する (ルール 2)。`EXTERNAL_DESIGN.ja.md` 内に外部契約以外の混入が見つかった場合は、別ファイルへ移してから checkbox を振る。

### ルール 14: 仕様書には読者が自力で導けない情報だけを書く

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

## 退避資料

旧 full GRAG 版は次に退避している。

```text
archive/full-grag-2026-05-05/
```

この退避資料は歴史的バックアップであり、現在の正本ではない。現在の仕様判断は `doc/EXTERNAL_DESIGN.ja.md` と `doc/DESIGN.ja.md` を優先する。
