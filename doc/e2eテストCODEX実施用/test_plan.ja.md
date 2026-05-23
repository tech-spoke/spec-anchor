# SPEC-anchor E2E テスト計画書 (Codex 実施用)

本書は、`doc/EXTERNAL_DESIGN.ja.md` を正本として、Codex が外部から入力し、外部へ出る結果を観測する E2E テストを進めるための計画である。

既存の `doc/e2eテスト/test_plan.ja.md` は参考資料として扱う。現在の正本は `doc/EXTERNAL_DESIGN.ja.md` であり、本書作成時点での検証単位は `[ ]` 361 件、production E2E 検証済みの `✅` は 0 件である。

## 0. 用語の範囲

本書で使う新しい整理語は、この節でだけ先に範囲を固定する。

**仮称: 実機 E2E 検証**

- 意味: 利用者が実行する console script、Agent CLI、設定ファイル、Source Specs、Purpose / Core Concept、Qdrant HTTP endpoint などを外部入力として与え、実 Codex / Claude、実 Qdrant、実 FlagEmbedding BGE-M3、実ファイル入出力を通した結果を、exit code、stdout / stderr、生成ファイル、Qdrant payload、Agent の利用者向け出力として確認する検証。
- 含むもの: `spec-anchor` / `spec-anchor-watch` / `spec-anchor-setup-project` / `spec-anchor-setup-system` の subprocess 実行、実 Qdrant、実 FlagEmbedding BGE-M3、実 Codex / Claude CLI、tmp project に作った実ファイル、生成された `.spec-anchor/context/` と `.spec-anchor/state/` 配下の内容確認、`/spec-core` で生成した保持物を後続の `/spec-inject` / `/spec-realign` が実際に読む一連の流れ。
- 含まないもの: Python 関数の直接呼び出しだけで完結する単体テスト、`SPEC_ANCHOR_FAKE_LLM=1` / `SPEC_ANCHOR_FAKE_RETRIEVAL=1` に依存した通過、pytest fixture だけで成立する状態、固定値や fake provider の成功を本番経路の成功として扱うこと、起動確認だけの smoke test。
- 既存概念との差分: 既存の pytest marker や test profile 名ではなく、今回の完了判定に使う検証姿勢を表す。`unit_verified` / `hybrid_verified` は進捗として記録できるが、`doc/EXTERNAL_DESIGN.ja.md` の `✅` 付与根拠にはしない。
- 未決事項: Codex CLI と Claude Code の tool call trace の保存形式は、外部 I/O だけでは確認できない項目を扱う Phase で実測して確定する。

**既存用語: smoke / real-smoke**

- 意味: コマンド、外部サービス、Agent CLI、実 LLM 実行系が起動できるかを短時間で確認する補助検証。
- 含むもの: version 取得、Qdrant 接続確認、Agent CLI の認識確認、代表 command 1 回の到達確認。
- 含まないもの: `doc/EXTERNAL_DESIGN.ja.md` の `[ ]` を `✅` にする完了根拠、`/spec-core` → `/spec-inject` → `/spec-realign` の保持物受け渡し確認、利用者視点の入出力全体の確認。
- 既存概念との差分: `real-smoke` は実 Codex / Claude や実 Qdrant を使っていても、目的が「起動できるか / 到達できるか」の確認に限られるため、本書では E2E と呼ばない。
- 未決事項: なし。smoke / real-smoke の結果は証跡に残せるが、実機 E2E 検証の完了数には数えない。

**仮称: trace 補助検証**

- 意味: 外部出力だけでは「Agent がどの手順を辿ったか」を判定できない項目について、Agent CLI の session log や tool call log を追加で監査する検証。
- 含むもの: `spec-anchor inject-search` の後に `spec-anchor inject-section` を呼んだか、`inject-chapters` の返却 path を Agent が読んだか、Agentic Search の 4 path を省略していないかの確認。
- 含まないもの: CLI の stdout JSON だけで判定できる契約の代替。trace は外部 I/O E2E 検証の不足分を補うために使う。
- 既存概念との差分: `doc/EXTERNAL_DESIGN.ja.md` の凡例にある `tool call trace 監査` を、今回の作業単位として呼びやすくした仮称である。
- 未決事項: Codex CLI の log 形式、Claude Code の print mode で tool call が残るか、trace 取得を pytest fixture 化するか。

## 1. 正本と検証単位

正本は `doc/EXTERNAL_DESIGN.ja.md` の `[ ]` 行である。マークがない説明文は検証単位にしない。`✅` は `production_e2e_verified` の evidence がある場合だけ付与する。

本書作成時点の章別件数:

| 章 | 対象 | `[ ]` 件数 | 主な確認方法 |
|---|---|---:|---|
| §2 | 用語と範囲 | 23 | 実機 E2E 検証 + 生成ファイル確認 |
| §3 | 動作モデル | 23 | 実機 E2E 検証 + freshness 状態確認 |
| §4 | 保持物 | 36 | 実機 E2E 検証 + `.spec-anchor/context/` / `.spec-anchor/state/` 確認 |
| §5 | 責務境界 | 15 | 実機 E2E 検証 + negative check |
| §6 | コマンド体系 | 38 | 外部入出力確認 + 必要箇所は実機 E2E 検証 |
| §7 | `/spec-core` | 60 | 実機 E2E 検証 + Qdrant payload 確認 |
| §8 | `/spec-inject` | 46 | 実機 E2E 検証 + trace 補助検証 |
| §9 | `/spec-realign` | 9 | 実機 E2E 検証 + trace 補助検証 |
| §10 | 設定ファイル | 69 | 外部入出力確認 + config JSON / TOML 確認 |
| §11 | エラー契約 | 42 | 実機 E2E 検証 + Agent 出力確認 |
| 合計 |  | 361 |  |

## 2. 完了判定

`doc/EXTERNAL_DESIGN.ja.md` の `[ ]` を `✅` にできる条件:

- 対応する検証が実機 E2E 検証として実行されている。
- `SPEC_ANCHOR_FAKE_LLM` と `SPEC_ANCHOR_FAKE_RETRIEVAL` は、その検証の完了根拠として使われていない。
- 実行結果の証跡が `doc/e2eテストCODEX実施用/evidence/<run-id>/` に残っている。
- `pytest` を使う場合、`evidence_map.jsonl` に `result: "passed"` と `verification_level: "production_e2e_verified"` が記録されている。
- `pytest` を使わない手動 E2E の場合、実行 command、exit code、stdout / stderr、確認した出力ファイル、判定結果を `RESULTS.ja.md` に残し、後で pytest 化する TODO を明示する。

完了扱いにしないもの:

- fake provider、固定 fixture、最小確認だけの実行で通っただけの項目。
- `pytest -q --skip-external` だけの通過。
- smoke / real-smoke の通過。
- Qdrant、BGE-M3、Codex / Claude CLI を使うべき契約で、それらを使っていない実行。
- Agent の利用者向け出力や tool call trace が必要な契約で、CLI の raw JSON だけを見て済ませた項目。

### 2.1 Agent 別実行と正本への反映

Codex と Claude が並行して検証する場合、各 Agent は実行中に `doc/EXTERNAL_DESIGN.ja.md` の `[ ]` を直接 `✅` に変更しない。

理由: `doc/EXTERNAL_DESIGN.ja.md` の `✅` は Agent 別の作業済み印ではなく、正本上の production E2E 検証済み状態を示す。Codex と Claude が同じ行を別々に編集すると、どの証跡で昇格したのか、片方で失敗した項目をもう片方が誤って完了にしたのかを追跡しづらくなる。

Codex は進捗確認用のコピーとして `doc/e2eテストCODEX実施用/EXTERNAL_DESIGN.codex-progress.ja.md` を使う。この file は `doc/EXTERNAL_DESIGN.ja.md` の正本コピーであり、Codex 実行中のチェック状態を人間が確認するためだけに使う。Codex が検証済みにした項目は、このコピーの `[ ]` を `✅` に変更してよい。ただし、この変更は正本の検証済み状態ではなく、Codex 側の候補状態である。

Agent 別の証跡は次に分ける。

- Codex: `doc/e2eテストCODEX実施用/evidence/<run-id>/`
- Claude: `doc/e2eテストCLAUDE実施用/evidence/<run-id>/`

`doc/EXTERNAL_DESIGN.ja.md` に `✅` を付けるのは、Codex / Claude の証跡を照合した後の昇格レビューで行う。昇格レビューでは、対象行ごとに次を確認する。

- 対応する証跡の file path。
- 実行 command と exit code。
- 外部入力と外部出力で確認した内容。
- fake / smoke / real-smoke ではないこと。
- trace 補助検証が必要な項目なら、外部入出力だけでは判定できない残範囲と trace 証跡。

Codex 側の本書では、`doc/EXTERNAL_DESIGN.ja.md` の正本更新は実施対象外とし、実行結果と証跡を残すところまでを担当する。

昇格レビューで `doc/EXTERNAL_DESIGN.ja.md` に `✅` を反映するときは、Codex 進捗コピーの `✅` をそのまま転記しない。対象行ごとに Codex / Claude の証跡を確認し、production E2E 検証済み条件を満たす行だけを正本へ反映する。

## 3. 実行フェーズ

### E0: 棚卸し

目的: `doc/EXTERNAL_DESIGN.ja.md` の現在の `[ ]` 件数、既存 pytest evidence 基盤、実行可能な CLI を確認する。

合格条件:

- 章別件数を本書に記録する。
- `spec-anchor` console script、`codex`、`claude`、`qdrant` の所在を確認する。
- 既存の `doc/e2eテスト/test_plan.ja.md` と矛盾する件数があれば、本書側に現在値を明示する。

### E1: setup / system の外部 I/O

対象: §6.1、§6.2、§10、§11.1.3、§11.1.4。

入力:

- 新規 tmp project directory。
- `spec-anchor-setup-project --target <tmp> --agent both`。
- `spec-anchor-setup-system --check-only --qdrant-url http://localhost:6333`。

出力確認:

- setup-project の stdout JSON、exit code、作成ファイル。
- `--dry-run` でファイルが変化しないこと。
- `--force` 有無による conflict / update の違い。
- setup-system の readiness JSON、Qdrant / FlagEmbedding / Codex / Claude / console script の検出結果。

### E2: `/spec-core` の実機 E2E 経路

対象: §2.4、§2.7、§2.8、§2.9、§3.1、§3.2、§4、§5.3、§7。

入力:

- tmp project の実 Source Specs、Purpose、Core Concept。
- `SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` を unset した環境。
- 実 Qdrant、実 FlagEmbedding BGE-M3、実 Codex / Claude CLI。
- `spec-anchor core --rebuild`、続けて `spec-anchor core`、必要に応じて `spec-anchor core --all`。

出力確認:

- stdout JSON の `status`、`freshness_report`、`retrieval_index_status`、`related_sections_status`。
- `.spec-anchor/context/chapter_anchors.json` と `.spec-anchor/context/conflict_review_items.json`。
- `.spec-anchor/state/section_manifest.json`、`.spec-anchor/state/freshness.json`、`.spec-anchor/state/core_progress.json`。
- `.spec-anchor/state/retrieval_index_state.json` に保存された Source Retrieval Index の前回状態 (section 集合 hash 指紋 + embedding / retrieval 設定指紋) と現在状態が一致する場合、section collection upsert が再実行されないこと。不一致または Qdrant collection 不在では通常 upsert 経路に戻ること。
- `.spec-anchor/state/related_sections_state.json` に保存された Related Sections の前回状態 (section 集合 hash + candidate generation / LLM selection 設定指紋) と現在状態が一致する場合、Related Sections 再生成が抑止されること。不一致では通常生成経路に戻ること。

### E3: freshness / watcher の外部 I/O

対象: §3.3、§6.3、§11.1.5 の watcher 系。

入力:

- Source Specs を変更した tmp project。
- `spec-anchor-watch --once`、`spec-anchor watch`。
- watcher lock / queue file がある状態。

出力確認:

- stdout JSON の `cycles[]`、`cycle_count`、停止理由。
- `.spec-anchor/state/freshness.json` の blocking reasons。
- `/spec-inject` / `/spec-realign` が freshness gate で停止すること。

### E4: `/spec-inject` の実機 E2E 経路

対象: §3.4、§5.3 の retrieval API、§8、§11.1.2、§11.2。

入力:

- E2 で生成した保持物。
- `spec-anchor inject-search "<query>"`。
- `spec-anchor inject-section <source_section_id>`。
- `spec-anchor inject-chapters`。
- `spec-anchor inject-purpose`。
- `spec-anchor inject-conflicts`。

出力確認:

- CLI が constraint statement を生成せず、検索結果、Section payload、Chapter Key Anchor path、Purpose 本文、Conflict Review Item 一覧だけを返すこと。
- `inject-chapters` は `chapter_anchors.json` の path を返すこと。
- `inject-purpose` は Purpose 全文と Core Concept path を返すこと。
- freshness が blocked / failed の場合は、Agentic Search を進められない形の JSON になること。

trace 補助検証が必要な範囲:

- Agent / LLM が `inject-search` の結果から `inject-section` を辿ること。
- Agent / LLM が `inject-chapters` の path を読んで必要箇所だけを制約根拠に使うこと。
- Agent / LLM が Source Specs 全文や Core Concept 全文を無条件に投入しないこと。

### E5: `/spec-realign` の実機 E2E 経路

対象: §3.5、§5.3 の回答生成境界、§9、§11.1.2、§11.2。

入力:

- E4 で得た代表制約。
- `spec-anchor realign --answer-json '<json>'`。
- answer が無い状態、freshness が blocked / failed の状態、pending conflict がある状態。

出力確認:

- CLI は Agent から渡された answer を整形し、独自に自由生成しないこと。
- answer 不在時は needs-answer の JSON を返すこと。
- blocked / failed / pending conflict の停止理由と次アクションが JSON に出ること。

### E6: エラー契約の外部 I/O

対象: §11.1.5、§11.2。

入力:

- `.spec-anchor/config.toml` 不在。
- Purpose / Core Concept 不在。
- Source Specs 0 件。
- Qdrant 到達不能。
- console script / Agent CLI を PATH から隠した状態。

出力確認:

- exit code と stdout JSON の shape が設計書どおりであること。
- Agent CLI を使う行では、利用者向けの復旧手順が §11.2 の構造で出ること。

### E7: Agent 出力と trace 補助検証

対象: §8.3、§8.5、§8.6、§9.2、§9.3、§11.2。

入力:

- Codex CLI と Claude Code / Claude CLI の非対話実行。
- E2 の tmp project と代表課題。

出力確認:

- Agent の利用者向け出力が raw JSON の貼り付けではなく、設計書で求める区分構造になっていること。
- tool call trace から、Agent が必要な `spec-anchor inject-*` 呼び出しを行ったこと。
- trace が取れない場合は、外部 I/O で判定できない残範囲として本書と結果報告に残す。

## 4. 証跡保存

今回の Codex 実施用証跡は、次に保存する。

```text
doc/e2eテストCODEX実施用/
├── test_plan.ja.md
├── RESULTS.ja.md
└── evidence/
    └── <run-id>/
        ├── environment.txt
        ├── commands.log
        ├── stdout/
        ├── stderr/
        └── artifacts/
```

`RESULTS.ja.md` には、少なくとも次を分けて記録する。

- 実行済みの実機 E2E 検証。
- `none` / `fake` provider 相当の通過がある場合、その範囲。
- 実 Qdrant、実 FlagEmbedding BGE-M3、実 Codex / Claude CLI を使った通過。
- smoke / real-smoke として実行したが、実機 E2E 検証には数えない補助確認。
- skipped / 未実行。
- 残 TODO。

## 5. 最初に実行するテスト

初回は E1 から開始する。理由は、外部 I/O だけで判定でき、実 LLM 呼び出しに進む前に system readiness と project setup の契約を確認できるためである。

初回実行項目:

1. `spec-anchor-setup-system --check-only --qdrant-url http://localhost:6333`
2. tmp project に対する `spec-anchor-setup-project --target <tmp> --agent both --dry-run`
3. tmp project に対する `spec-anchor-setup-project --target <tmp> --agent both`
4. 同じ tmp project に対する再実行 conflict check。
5. `--force` 再実行で conflict が解消されるかの確認。

E1 が通った後、E2 の `/spec-core --rebuild` で実 Codex / Claude / Qdrant / BGE-M3 を使う経路へ進む。E2 が未実行の間は、保持物生成、retrieval index、Related Sections、Chapter Key Anchor、Conflict Review Item に関する項目を完了扱いにしない。`spec-anchor-setup-system --run-smoke` や Agent CLI の起動確認が通っていても、この完了判定は変えない。
