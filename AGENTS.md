# spec-grag Agent Guide

このリポジトリで作業する Agent は、まず [CLAUDE.md](CLAUDE.md) を読むこと。

`CLAUDE.md` は Claude Code 用という名前だが、このリポジトリでは Agent 共通の不変ルールを置く正のファイルとして扱う。Codex / Claude / その他 Agent も同じルールに従う。

特に設計相談では、`CLAUDE.md` の「ルール 6: 新しい用語・仮称を出す時は範囲を先に明示する」を守ること。新しい用語を出す場合は、仮称か既存用語か、意味、含むもの、含まないもの、既存概念との差分、未決事項を先に明示し、範囲が曖昧なまま設計判断へ進まない。

実装完了の判定では、`CLAUDE.md` の「ルール 7: 実装完了ガードを守る」に従うこと。smoke / fake / fixture / placeholder による通過を、production 経路または通常実行経路の完了として扱ってはいけない。

失敗、skip、未実行、過大申告、flaky、環境差分、設計との不整合を見つけた場合は、`CLAUDE.md` の「ルール 8: 失敗を計画へ反映してから修正する」に従うこと。口頭説明だけで進めず、`doc/IMPLEMENTATION_PLAN.ja.md` / `doc/TEST_SPEC.ja.md` の Gate / T 項目 / 検証行 / TODO を更新してから、実装修正と再テストへ戻る。

人間または別 Agent から監査結果、レビュー結果、懸念点、修正候補、過大申告の疑いを受け取った場合は、`CLAUDE.md` の「ルール 9: 監査指摘は全件 disposition を残す」に従うこと。指摘をまとめて消化せず、指摘 ID ごとに `採用` / `部分採用` / `不採用` / `保留` / `既対応`、理由、対応、証跡、残 TODO を残す。

作業終了時の最終報告では、`CLAUDE.md` の「ルール 10: 最終報告では完了範囲と残範囲を必ず分ける」に従うこと。作業が小さい場合でも、完了したこと、残したこと、未検証のこと、判定できないこと、証跡を必要に応じて分けて書く。

指摘や残 TODO を残す場合は、`CLAUDE.md` の「ルール 11: 合理的理由のない保留を禁止する」に従うこと。既存契約の範囲内で、人間判断も外部ブロッカーも不要な修正・検証は、その場で実施する。残す場合は、理由分類、今進められない理由、完了条件、次に実行すべき作業を明示する。

## 設計書の記述ルール

`doc/EXTERNAL_DESIGN.ja.md` を記述・レビューする際は、[doc/EXTERNAL_DESIGN_RULES.ja.md](doc/EXTERNAL_DESIGN_RULES.ja.md) に従うこと。外部設計書にソースコードの知識がないと読めない文を書いてはいけない。

`doc/DESIGN.ja.md` を記述・レビューする際は、[doc/INTERNAL_DESIGN_RULES.ja.md](doc/INTERNAL_DESIGN_RULES.ja.md) に従うこと。内部設計は実装メモではなく、確定した設計判断の記録として書かなければならない。

## 報告ルール

smoke 実装、fake provider での通過、`none` / `fake` profile の test passing を、全体の完了や実動作完了として報告してはいけない。

実 Qdrant、BGE-M3、real provider、`local-service`、`real-smoke` を含む検証が未実行または skip されている場合は、その範囲を未完了 TODO として明示すること。特に `doc/TEST_SPEC.ja.md` の G-17 / T-R06〜T-R10 が未完了の間は、「実動作完了」と報告しない。

進捗報告では、少なくとも次を分けて書くこと。

- 実装済み
- `none` / `fake` profile で passing
- `local-service` / `real-smoke` で passing
- skipped / 未実行
- 残 TODO

失敗を検出した後の報告では、追加で次を明示すること。

- どの計画項目 / テスト仕様項目を更新したか
- どの実装を修正したか
- どの再テストで失敗が解消したか
- 解消していない場合、どの TODO として残したか

監査指摘を受けた後の報告では、追加で次を指摘 ID 単位で明示すること。

- 採用して修正した指摘
- 部分採用し、残 TODO がある指摘
- 不採用または既対応と判断した指摘と、その根拠
- 未検証または保留した指摘と、次に必要な検証
