# spec-anchor Agent Guide

このリポジトリで作業する Agent は、まず [CLAUDE.md](CLAUDE.md) を読むこと。

`CLAUDE.md` は Claude Code 用という名前だが、このリポジトリでは Agent 共通の不変ルールを置く正のファイルとして扱う。Codex / Claude / その他 Agent も同じルールに従う。

特に設計相談では、`CLAUDE.md` の「ルール 6: 新しい用語・仮称を出す時は範囲を先に明示する」を守ること。新しい用語を出す場合は、仮称か既存用語か、意味、含むもの、含まないもの、既存概念との差分、未決事項を先に明示し、範囲が曖昧なまま設計判断へ進まない。

実装完了の判定では、`CLAUDE.md` の「ルール 7: 実装完了ガードを守る」に従うこと。smoke / fake / fixture / placeholder による通過を、production 経路または通常実行経路の完了として扱ってはいけない。

TODO / 設計書 / 依頼文に「廃止」「削除」「根絶」「完全削除」「旧経路を残さない」と書かれている対象を扱う場合は、`CLAUDE.md` の「ルール 15: 機能を廃止する場合は根絶する」に従うこと。後方互換 shim、legacy fold、deprecated alias、旧入力の読み替え、旧 enum / 旧 reason の受理、旧 CLI flag の no-op 化を残したまま完了扱いしてはいけない。廃止対象名や禁止語を文字列連結・動的生成・別名で残して `git grep` をすり抜けることも禁止する。

失敗、skip、未実行、過大申告、flaky、環境差分、設計との不整合を見つけた場合は、`CLAUDE.md` の「ルール 8: 失敗を計画へ反映してから修正する」に従うこと。口頭説明だけで進めず、実装修正と再テストへ戻る。

人間または別 Agent から監査結果、レビュー結果、懸念点、修正候補、過大申告の疑いを受け取った場合は、`CLAUDE.md` の「ルール 9: 監査指摘は全件 disposition を残す」に従うこと。指摘をまとめて消化せず、指摘 ID ごとに `採用` / `部分採用` / `不採用` / `保留` / `既対応`、理由、対応、証跡、残 TODO を残す。

作業終了時の最終報告では、`CLAUDE.md` の「ルール 10: 最終報告では完了範囲と残範囲を必ず分ける」に従うこと。作業が小さい場合でも、完了したこと、残したこと、未検証のこと、判定できないこと、証跡を必要に応じて分けて書く。

指摘や残 TODO を残す場合は、`CLAUDE.md` の「ルール 11: 合理的理由のない保留を禁止する」に従うこと。既存契約の範囲内で、人間判断も外部ブロッカーも不要な修正・検証は、その場で実施する。残す場合は、理由分類、今進められない理由、完了条件、次に実行すべき作業を明示する。

## 設計書の記述ルール

`doc/EXTERNAL_DESIGN.ja.md` を記述・レビューする際は、[agent_doc/EXTERNAL_DESIGN_RULES.ja.md](agent_doc/EXTERNAL_DESIGN_RULES.ja.md) に従うこと。外部設計書にソースコードの知識がないと読めない文を書いてはいけない。

### `sidecar` を単独で使わない

`sidecar` という語は、技術用語としては成立するが、このリポジトリでは単独で使ってはいけない。現時点で `sidecar` と呼びうる状態記録ファイルは少なくとも次の 2 種類があり、`sidecar` だけでは読者がどちらを指すか判別できないためである。

この禁止は、設計書、報告書、TODO、最終報告、進捗報告のすべてに適用する。`.spec-anchor/state/retrieval_index_state.json` または `.spec-anchor/state/related_sections_state.json` を参照する場合は、毎回 file path、保存する fingerprint の内容、参照する stage / 経路、一致時の挙動、不一致時の fallback 条件を明示する。

- `.spec-anchor/state/retrieval_index_state.json` (Source Retrieval Index の冪等判定用)
- `.spec-anchor/state/related_sections_state.json` (Related Sections の冪等判定用)

設計書・報告書・TODO に書く場合は、原則として「状態記録ファイル」と表現したうえで、対象を具体的に書く。

書くべき要素:

- 具体的な file path (`.spec-anchor/state/<name>.json`)
- そのファイルに保存される内容 (何の指紋か)
- 参照する stage / 経路 (例: `section_collection_upsert`)
- 一致時の挙動 / 不一致時の fallback 条件

悪い例:

```text
sidecar が一致したら fast path に入る。
B-2 fast path は state sidecar のみ参照。
state sidecar の責務拡大。
```

良い例:

```text
`.spec-anchor/state/retrieval_index_state.json` に保存された
Source Retrieval Index の前回状態 (section hash 指紋 + 設定指紋) と、
現在の section hash / retrieval 設定が一致した場合、
section_collection_upsert stage は `skipped_unchanged` で終了する。
```

どうしても短縮表現が必要な節 (同一段落内で何度も参照する等) では、初出で次の形式で定義したうえで、その節の中だけで使う。節を跨ぐ参照では再び具体名に戻す。

```text
状態記録ファイル (以下この節では sidecar と呼ぶ):
- `.spec-anchor/state/retrieval_index_state.json`
- `.spec-anchor/state/related_sections_state.json`
```

このルールは `CLAUDE.md` の「ルール 12: 報告・設計文書は人間のプロジェクトオーナー向けに書く」の `artifact` / `generated state` を単独で使ってはいけないという要求と整合する。`sidecar` も同じ理由で単独使用禁止対象に含める。

## 報告ルール

smoke 実装、fake provider での通過、`none` / `fake` profile の test passing を、全体の完了や実動作完了として報告してはいけない。

実 Qdrant、BGE-M3、real provider、`local-service`、`real-smoke` を含む検証が未実行または skip されている場合は、その範囲を未完了 TODO として明示すること。

### 人間向け報告文ガード

Agent は、報告、TODO 更新、状況サマリー、Completion Ledger、最終報告を、人間のプロジェクトオーナーがそのまま判断に使える文として書く。内部実装名、test 名、英語の skip reason、略語、分類ラベルを説明なしに置いてはいけない。

報告文では、各項目について少なくとも次が分かるように書く。

- 何の機能・経路についての話か
- 今回の完了条件に含むのか、含まないのか
- 含まない場合、なぜ今回の判断から外せるのか
- 未完了なら、次に何をすれば完了するのか
- PASS / SKIP / NOT-RUN が、利用者にとって何を意味するのか

禁止する書き方:

- 内部ラベルだけを書く: `model/effort calibration scaffold`, `grep disposition`, `component-local status`, `legacy fixture`, `measurement loop not implemented`
- test 名や skip reason だけを書く: `tests/test_x.py 9 skipped`, `calibration measurement loop not implemented`
- profile 名だけで説明する: `fake は PASS`, `local-service は SKIP`, `real-smoke 未実行`
- 「対象外」「既存」「別タスク」だけを書き、今回の完了判定から外せる理由を書かない

必要な書き方:

- まず人間向けの意味を書く。内部名は必要な場合だけ括弧で補足する
- 例: 「`tests/test_model_effort_calibration.py` は Claude の stage/model/effort 組み合わせを実測評価する別用途の既存外部テストで、今回 TODO の完了条件には含まれていない。9 件は測定ループ未実装のため skip された」
- 例: 「`--skip-external` により外部サービスを使う検証は実行していない。したがって実 Qdrant / BGE-M3 経路の完了判定には使えない」

Agent は、人間向けの一文に言い換えられない項目を、Completion Ledger や状況サマリーに載せてはいけない。言い換えられない場合は、先に対象 test / 実装 / TODO を読み直し、意味を確認してから報告する。

TODO に存在しない検証や unrelated な skipped test を、勝手に残 TODO、次アクション、別タスク候補へ昇格してはいけない。unrelated な skip は、件数の説明に必要な範囲でだけ触れる。今回の TODO が求めているのは、TODO に書かれた修正と検証を正しく完了させることであり、TODO 外の既存 test を実装することではない。

ただし、unrelated な skip を「今回 TODO 外」と分類しても、今回 TODO が要求する実環境検証・production E2E・通常実行経路の未実行を正当化してはいけない。skip の分類は「その skipped test を今回直さない」という意味でしかなく、「今回必要な実環境検証をしなくてよい」という意味ではない。Completion Ledger では、unrelated skip の説明と、今回 TODO の production / real / local-service 検証の PASS / NOT-RUN / BLOCKED を必ず別 scope として分ける。

### smoke / fake で止めない実環境検証ガード

Agent は、smoke / fake / fixture / `--skip-external` の通過を、作業を止める理由にしてはいけない。これらは「初期確認」または「狭い回帰確認」であり、実環境・通常実行経路・production E2E が必要な TODO では完了判定の代替にならない。

特に Codex は、skip を `SKIP-OUT-OF-SCOPE` と分類しただけで安心して作業を止めてはいけない。skip 分類は説明であって、実環境検証の代替ではない。実 Qdrant、BGE-M3、real provider、`local-service`、`real-smoke`、`production-e2e` が使える状態なら、合理的理由なく未実行のまま残してはいけない。

作業中に次のいずれかを満たす場合、Agent は最終報告前に実環境または通常実行経路の検証へ進む。

- TODO / handoff / task file の完了条件に production E2E、実 Qdrant、BGE-M3、real provider、`local-service`、`real-smoke`、人間レビュー前の実動作確認が含まれる
- ユーザーが「完走」「引き継いで」「実環境」「本当に動くか」「ProductionE2E」などを求めている
- 実装が CLI、provider、storage、Qdrant、embedding、watcher、filesystem、state file、外部 process をまたぐ
- smoke / fake では通るが、実依存・状態更新・永続化・再実行時の挙動を検証していない

実環境検証を残してよい理由は、CLAUDE.md ルール 11 の合理的理由に限る。単に「時間がかかる」「別範囲に見える」「unit は通った」「skip は今回 scope 外に見える」は、実環境検証を残す理由にならない。

実環境検証を実行できない場合は、必ず `NOT-RUN` または `BLOCKED` として TODO の状況サマリーに残し、次を明記する。

- どの production / real / local-service 経路が未実行か
- なぜ今この場で実行できないか
- 実行可能にする条件
- 次に実行する具体的 command
- smoke / fake / unit passing では何が未保証のままか

スモーク実装放置も禁止する。production 経路または通常実行経路に、固定値、fake provider 前提、fixture 前提、未実装分岐、`TODO` / `NotImplementedError` / `pass` / `...` / silent fallback が残る場合、Agent は完了報告前に修正する。修正できない場合は、未完了の実装 TODO として状況サマリーに残す。

### Codex 向け完了報告ガード

Codex / ChatGPT 系 Agent は、最終報告または「完了したか」と聞かれた時の回答で、曖昧な完了表現を使ってはいけない。特に Codex は、smoke / fake / fixture / `--skip-external` / real Qdrant / BGE-M3 / real provider / production E2E / 人間レビューを混同しやすいため、必ず次の Completion Ledger を出す。

| scope | 判定 | profile | command / evidence | skip / 未実行理由 | 次アクション |
|---|---|---|---|---|---|

`判定` は次の語だけを使う。

- `PASS`: 今回 scope 内で実行済み、成功した。
- `FAIL`: 今回 scope 内で実行済み、失敗した。
- `SKIP-IN-SCOPE`: 今回 scope 内だが skip された。
- `SKIP-OUT-OF-SCOPE`: 今回 scope 外の既存の将来用 test、未実装機能向け test、または今回の acceptance criteria と無関係な skip。
- `NOT-RUN`: 今回 scope 内だが実行していない。
- `BLOCKED`: 外部要因で実行できない。

Codex は `skipped` を見つけたら、必ず `SKIP-IN-SCOPE` と `SKIP-OUT-OF-SCOPE` に分類する。分類できない skip は `SKIP-IN-SCOPE` として扱い、完了扱いしない。skip 理由を報告するときは、test 名・内部ラベル・英語の skip reason だけをそのまま出してはいけない。人間のプロジェクトオーナーが判断できるように、何の機能の検証か、今回の acceptance criteria に含むのか、含まないならなぜ含まないのかを日本語で書く。TODO に存在しない検証名を作ってはいけない。例: `model/effort calibration` や `measurement loop not implemented` は、「`tests/test_model_effort_calibration.py` は Claude の stage/model/effort 組み合わせを実測評価する別用途の既存外部テストで、今回 TODO の完了条件には含まれていない。9 件は測定ループ未実装のため skip された」のように言い換える。

profile は次の意味で固定する。

- `none` / `fake`: 実依存なし。実運用完了ではない。
- `local-service`: 実 Qdrant / 実 BGE-M3 など local service を使った確認。
- `real-smoke`: 実 Agent CLI / 実 provider を使う代表経路確認。production E2E の代替ではない。
- `production-e2e`: 実運用に近い chain を通した確認。完了判定の最上位。

Codex は次の報告を禁止する。

- `--skip-external` 付き pytest の PASS を `local-service` / `real-smoke` / `production-e2e` の PASS として報告する。
- smoke / fake / fixture の PASS を「実動作完了」「production 完了」として報告する。
- skip 件数だけを示し、今回 scope 内か scope 外かを分類しない。
- 「ほぼ完了」「大丈夫そう」「完了した感」など、scope が不明な完了表現を使う。
- TODO の acceptance criteria と対応しない passing test だけで、その TODO を完了扱いする。
- TODO / handoff / task file が `production-e2e`、`production E2E`、`prod E2E`、`人間レビュー`、`3 段ゲート`、またはそれに相当する最上位検証を完了条件にしている場合、`none` / `fake` / `local-service` / `real-smoke` の PASS だけで「完了」と報告してはいけない。
- user から監査・不明瞭報告の指摘を受けた後に、指摘 ID 単位の disposition と Completion Ledger を省略する。

Codex は作業開始時と最終報告前に、対象 TODO / handoff / task file の `完了条件`、`検証条件`、`E2E シナリオ`、`残 TODO`、`3 段ゲート` の記述を確認し、Completion Ledger に TODO acceptance criteria を scope として列挙する。TODO が production E2E まで要求している場合は、production E2E が `PASS` になるまで最終判定を `完了` にしてはいけない。production E2E が未実行なら、実装・unit・fake・local-service・real-smoke がすべて PASS でも、最終判定は `条件付き完了` または `未完了` とする。

### Codex 向け TODO 状況サマリー更新ガード

Codex は、`doc/TODO/*.md`、handoff、task file、またはユーザーが明示した TODO ファイルを根拠に作業した場合、会話での報告だけで終わってはいけない。対象ファイルに `状況サマリー`、sub task 一覧、`E2E シナリオ` 表、`完了条件`、`残作業`、`Completion Ledger` のいずれかがある場合、最終報告前に必ずそのファイル自体を更新する。

最終報告前に必ず更新する項目:

- top-level `ステータス`
- `状況サマリー` の各 sub task の `状態` / `残作業` / `最終更新`
- `Completion Ledger` または同等の証跡表
- `E2E シナリオ` 表の `pytest` / `LLM 自己確認` / `人間レビュー` / `完了`
- `課題全体の完了条件` の現在判定
- skip / 未実行 / production E2E 未実施 / 人間レビュー未実施の残 TODO

Codex は、対象 TODO に `状況サマリー` があるのに更新しないまま「完了」「条件付き完了」「未完了」を会話だけで報告してはいけない。これは報告漏れではなく、完了条件未達として扱う。

最終報告前の必須確認:

```text
rg -n "未着手|未確認|計画中|\\[ \\]" <対象TODO>
```

この確認で stale な `未着手` / `未確認` / `計画中` / 未処理 checkbox が見つかった場合は、次のどちらかを必ず実施する。

- 実態に合わせて TODO を更新する
- 意図的に残す場合は、その行がなぜ未完了なのか、完了条件、次アクションを同じ TODO 内に書く

最終報告では、更新した TODO の file / line を証跡として示す。TODO の状況サマリーを更新できない合理的理由がある場合だけ例外とし、その場合も `BLOCKED` または `NOT-RUN` として、理由、完了条件、次アクションを明示する。

TODO の完了条件に含まれる検証を実行しなかった場合、Codex は `NOT-RUN` として次を明記する。

- なぜ実行していないか
- 今この場で実行できない理由が本当にあるか
- 完了条件
- 次に実行すべき command または人間作業

user が「完了したか」「まだテストが残っているか」と聞いた場合、Codex は最初の 1 行で次のいずれかを答える。

- `完了`: 今回 scope の acceptance criteria がすべて `PASS`。
- `条件付き完了`: 実装と一部 profile は `PASS` だが、real / production / human review などが `NOT-RUN` または `SKIP-IN-SCOPE`。
- `未完了`: 今回 scope に `FAIL` / `NOT-RUN` / `SKIP-IN-SCOPE` / `BLOCKED` が残っている。

その後に Completion Ledger を出し、`PASS`、`SKIP-IN-SCOPE`、`SKIP-OUT-OF-SCOPE`、`NOT-RUN`、`BLOCKED` を分けて説明する。

進捗報告では、少なくとも次を分けて書くこと。

- 実装済み
- `none` / `fake` profile で passing
- `local-service` / `real-smoke` で passing
- skipped / 未実行
- 残 TODO

失敗を検出した後の報告では、追加で次を明示すること。

- どの実装を修正したか
- どの再テストで失敗が解消したか
- 解消していない場合、どの TODO として残したか

監査指摘を受けた後の報告では、追加で次を指摘 ID 単位で明示すること。

- 採用して修正した指摘
- 部分採用し、残 TODO がある指摘
- 不採用または既対応と判断した指摘と、その根拠
- 未検証または保留した指摘と、次に必要な検証
