# spec-grag Agent Guide

このリポジトリで作業する Agent は、まず [CLAUDE.md](CLAUDE.md) を読むこと。

`CLAUDE.md` は Claude Code 用という名前だが、このリポジトリでは Agent 共通の不変ルールを置く正のファイルとして扱う。Codex / Claude / その他 Agent も同じルールに従う。

特に設計相談では、`CLAUDE.md` の「ルール 6: 新しい用語・仮称を出す時は範囲を先に明示する」を守ること。新しい用語を出す場合は、仮称か既存用語か、意味、含むもの、含まないもの、既存概念との差分、未決事項を先に明示し、範囲が曖昧なまま設計判断へ進まない。

実装完了の判定では、`CLAUDE.md` の「ルール 7: 実装完了ガードを守る」に従うこと。smoke / fake / fixture / placeholder による通過を、production 経路または通常実行経路の完了として扱ってはいけない。

失敗、skip、未実行、過大申告、flaky、環境差分、設計との不整合を見つけた場合は、`CLAUDE.md` の「ルール 8: 失敗を計画へ反映してから修正する」に従うこと。口頭説明だけで進めず、実装修正と再テストへ戻る。

人間または別 Agent から監査結果、レビュー結果、懸念点、修正候補、過大申告の疑いを受け取った場合は、`CLAUDE.md` の「ルール 9: 監査指摘は全件 disposition を残す」に従うこと。指摘をまとめて消化せず、指摘 ID ごとに `採用` / `部分採用` / `不採用` / `保留` / `既対応`、理由、対応、証跡、残 TODO を残す。

作業終了時の最終報告では、`CLAUDE.md` の「ルール 10: 最終報告では完了範囲と残範囲を必ず分ける」に従うこと。作業が小さい場合でも、完了したこと、残したこと、未検証のこと、判定できないこと、証跡を必要に応じて分けて書く。

指摘や残 TODO を残す場合は、`CLAUDE.md` の「ルール 11: 合理的理由のない保留を禁止する」に従うこと。既存契約の範囲内で、人間判断も外部ブロッカーも不要な修正・検証は、その場で実施する。残す場合は、理由分類、今進められない理由、完了条件、次に実行すべき作業を明示する。

## 設計書の記述ルール

`doc/EXTERNAL_DESIGN.ja.md` を記述・レビューする際は、[agent_doc/EXTERNAL_DESIGN_RULES.ja.md](agent_doc/EXTERNAL_DESIGN_RULES.ja.md) に従うこと。外部設計書にソースコードの知識がないと読めない文を書いてはいけない。

### `sidecar` を単独で使わない

`sidecar` という語は、技術用語としては成立するが、このリポジトリでは単独で使ってはいけない。現時点で `sidecar` と呼びうる状態記録ファイルは少なくとも次の 2 種類があり、`sidecar` だけでは読者がどちらを指すか判別できないためである。

この禁止は、設計書、報告書、TODO、最終報告、進捗報告のすべてに適用する。`.spec-grag/state/retrieval_index_state.json` または `.spec-grag/state/related_sections_state.json` を参照する場合は、毎回 file path、保存する fingerprint の内容、参照する stage / 経路、一致時の挙動、不一致時の fallback 条件を明示する。

- `.spec-grag/state/retrieval_index_state.json` (Source Retrieval Index の冪等判定用)
- `.spec-grag/state/related_sections_state.json` (Related Sections の冪等判定用)

設計書・報告書・TODO に書く場合は、原則として「状態記録ファイル」と表現したうえで、対象を具体的に書く。

書くべき要素:

- 具体的な file path (`.spec-grag/state/<name>.json`)
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
`.spec-grag/state/retrieval_index_state.json` に保存された
Source Retrieval Index の前回状態 (section hash 指紋 + 設定指紋) と、
現在の section hash / retrieval 設定が一致した場合、
section_collection_upsert stage は `skipped_unchanged` で終了する。
```

どうしても短縮表現が必要な節 (同一段落内で何度も参照する等) では、初出で次の形式で定義したうえで、その節の中だけで使う。節を跨ぐ参照では再び具体名に戻す。

```text
状態記録ファイル (以下この節では sidecar と呼ぶ):
- `.spec-grag/state/retrieval_index_state.json`
- `.spec-grag/state/related_sections_state.json`
```

このルールは `CLAUDE.md` の「ルール 12: 報告・設計文書は人間のプロジェクトオーナー向けに書く」の `artifact` / `generated state` を単独で使ってはいけないという要求と整合する。`sidecar` も同じ理由で単独使用禁止対象に含める。

## 報告ルール

smoke 実装、fake provider での通過、`none` / `fake` profile の test passing を、全体の完了や実動作完了として報告してはいけない。

実 Qdrant、BGE-M3、real provider、`local-service`、`real-smoke` を含む検証が未実行または skip されている場合は、その範囲を未完了 TODO として明示すること。

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
