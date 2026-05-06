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

## 退避資料

旧 full GRAG 版は次に退避している。

```text
archive/full-grag-2026-05-05/
```

この退避資料は歴史的バックアップであり、現在の正本ではない。現在の仕様判断は `doc/EXTERNAL_DESIGN.ja.md` と `doc/DESIGN.ja.md` を優先する。
