# SPEC-anchor E2E 実施結果 (Codex)

run ids:

- `20260522-214139-codex-e2e`
- `20260523-000315-codex-e2e-additional`
- `20260523-001153-codex-e2e-f001-retest`
- `20260523-002300-codex-e2e-slash-skill`
- `20260523-010512-codex-e2e-f002-retest`
- `20260523-013834-codex-e2e-remaining`
- `20260523-014753-codex-e2e-watchqueue-only`
- `20260523-015624-codex-e2e-remaining2`
- `20260523-020721-codex-e2e-remaining3`
- `20260523-021012-codex-e2e-remaining4`
- `20260523-021336-codex-e2e-debug-env2`
- `20260523-021533-codex-e2e-chapter-failure`
- `20260523-021648-codex-e2e-section-boundary`
- `20260523-021742-codex-e2e-partial-upsert`
- `20260523-021855-codex-e2e-ordinal-migration`
- `20260523-022006-codex-e2e-defer-gate`
- `20260523-022041-codex-e2e-resolution-readonly`
- `20260523-022243-codex-e2e-debug-related-prompt`
- `20260523-022644-codex-e2e-llm-boundary`
- `20260523-090550-codex-e2e-f004-retest`
- `20260523-091016-codex-e2e-f004-template-retest`
- `20260523-091402-codex-e2e-f004-postfix-retest`
- `20260523-092828-codex-e2e-agent-blockers`
- `20260523-093821-codex-e2e-agent-blockers-tmp`
- `20260523-093953-codex-e2e-agent-blockers-isolated`
- `20260523-095825-codex-e2e-f005-retest`
- `20260523-101202-codex-e2e-inject-output`
- `20260523-103156-codex-e2e-realign-output`
- `20260523-104149-codex-e2e-agent-core-errors`
- `20260523-110135-codex-e2e-parallel-safe`
- `20260523-112043-codex-e2e-degraded-section-metadata`
- `20260523-121607-codex-e2e-f006-retest`
- `20260523-122638-codex-e2e-search-key-limit`
- `20260523-123006-codex-e2e-agent-degraded-core`
- `20260523-123504-codex-e2e-agent-verify-index`
- `20260523-124022-codex-e2e-related-failure-retention`
- `20260523-125141-codex-e2e-dirty-pending-priority`
- `20260523-130037-codex-e2e-inject-all-gates`
- `20260523-131632-codex-e2e-conflict-review-generation`
- `20260523-134200-codex-e2e-core-blocked-watcher`
- `20260523-134620-codex-e2e-conflict-pair-cap-diagnostics`
- `20260523-135200-codex-e2e-watch-internal-no-agent-cli`
- `20260523-141500-codex-e2e-no-core-concept-drift-notice`
- `20260523-142000-codex-e2e-conflict-review-item-trace`
- `20260523-142500-codex-trace-raw-context-boundary`
- `20260523-143000-codex-e2e-path-selection-trace`
- `20260523-144000-codex-e2e-remaining-23`
- `2026-05-23-P3b`
- `2026-05-23-P7`

本書は `doc/EXTERNAL_DESIGN.ja.md` を正本とし、Codex 側で実行した外部入出力 E2E の結果を記録する。本作業のチェック結果は正本 `doc/EXTERNAL_DESIGN.ja.md` へ反映していない。進捗確認用のチェックは `doc/e2eテストCODEX実施用/EXTERNAL_DESIGN.codex-progress.ja.md` にのみ反映した。

Codex 実施用の残チェックは完了である。これまでの実行で、Codex 側が production E2E または Agent trace として追加実施した項目は `doc/e2eテストCODEX実施用/EXTERNAL_DESIGN.codex-progress.ja.md` に `✅` で記録した。smoke / fake contract 4 行もユーザー判断によりチェック済みにしたが、これは別枠確認であり production E2E 完了数には入れない。正本 `doc/EXTERNAL_DESIGN.ja.md` への昇格はまだ行っていない。

`20260523-144000-codex-e2e-remaining-23` で、前回残件として明示していた 23 行を処理した。内訳は、別 Codex 指摘で明確化された未実施チェック項目 11 件を実 Qdrant / BGE-M3 の外部入出力および既存 Agent trace 監査で確認し、step 可視化用 8 行を path trace 監査で確認し、smoke / fake contract 4 件を別枠で実行した。smoke / fake 4 件はユーザー判断により `✅` にした。ただし production E2E 完了扱いにはしない。

`doc/e2eテスト/test_plan.ja.md` の P3b 5 scenario と P7 6 scenario も追加実行し、P3b は `real_smoke_verified`、P7 は `production_e2e_verified` として evidence map を保存した。

## 1. 証跡

- 実行証跡: `doc/e2eテストCODEX実施用/evidence/20260522-214139-codex-e2e/`
- 追加実行証跡: `doc/e2eテストCODEX実施用/evidence/20260523-000315-codex-e2e-additional/`
- F001 再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-001153-codex-e2e-f001-retest/`
- slash command / Codex skill 実行証跡: `doc/e2eテストCODEX実施用/evidence/20260523-002300-codex-e2e-slash-skill/`
- F002 / F003 修正後再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-010512-codex-e2e-f002-retest/`
- 残項目追加 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-013834-codex-e2e-remaining/`
- watcher queue-only 途中停止証跡: `doc/e2eテストCODEX実施用/evidence/20260523-014701-codex-e2e-watchqueue-only/`
- watcher queue-only 切り分け証跡: `doc/e2eテストCODEX実施用/evidence/20260523-014753-codex-e2e-watchqueue-only/`
- 設定 / CLI 境界追加証跡: `doc/e2eテストCODEX実施用/evidence/20260523-015624-codex-e2e-remaining2/`
- Conflict decision / `.env` 初回切り分け証跡: `doc/e2eテストCODEX実施用/evidence/20260523-020721-codex-e2e-remaining3/`
- Conflict decision 修正版 / stale resolution / debug env 初回証跡: `doc/e2eテストCODEX実施用/evidence/20260523-021012-codex-e2e-remaining4/`
- debug provider invocation env 修正版証跡: `doc/e2eテストCODEX実施用/evidence/20260523-021336-codex-e2e-debug-env2/`
- Chapter Key Anchor 失敗証跡: `doc/e2eテストCODEX実施用/evidence/20260523-021533-codex-e2e-chapter-failure/`
- Section 境界証跡: `doc/e2eテストCODEX実施用/evidence/20260523-021648-codex-e2e-section-boundary/`
- Source Retrieval Index 部分更新証跡: `doc/e2eテストCODEX実施用/evidence/20260523-021742-codex-e2e-partial-upsert/`
- numeric point id migration 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-021855-codex-e2e-ordinal-migration/`
- defer gate 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-022006-codex-e2e-defer-gate/`
- resolution 非自動反映証跡: `doc/e2eテストCODEX実施用/evidence/20260523-022041-codex-e2e-resolution-readonly/`
- debug related prompt 未通過切り分け証跡: `doc/e2eテストCODEX実施用/evidence/20260523-022243-codex-e2e-debug-related-prompt/`
- `/spec-core` LLM provider 設定境界証跡: `doc/e2eテストCODEX実施用/evidence/20260523-022644-codex-e2e-llm-boundary/`
- F004 再テスト初回証跡: `doc/e2eテストCODEX実施用/evidence/20260523-090550-codex-e2e-f004-retest/`
- F004 template 側再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-091016-codex-e2e-f004-template-retest/`
- F004 修正後再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-091402-codex-e2e-f004-postfix-retest/`
- Agent CLI blocker 初回証跡: `doc/e2eテストCODEX実施用/evidence/20260523-092828-codex-e2e-agent-blockers/`
- Agent CLI blocker `/tmp` preflight 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-093821-codex-e2e-agent-blockers-tmp/`
- Agent CLI blocker 隔離再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-093953-codex-e2e-agent-blockers-isolated/`
- F005 pending conflict 再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-095825-codex-e2e-f005-retest/`
- `/spec-inject` §8.5 通常出力再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-101202-codex-e2e-inject-output/`
- `/spec-realign` §9.3 通常出力再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-103156-codex-e2e-realign-output/`
- Agent CLI `/spec-core` 失敗伝達再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-104149-codex-e2e-agent-core-errors/`
- 並列影響なし追加 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-110135-codex-e2e-parallel-safe/`
- Section Metadata degraded 追加 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-112043-codex-e2e-degraded-section-metadata/`
- F006 Section Metadata degraded 修正後再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-121607-codex-e2e-f006-retest/`
- Search Keys / Identifiers embedding input 上限 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-122638-codex-e2e-search-key-limit/`
- Agent CLI Section Metadata degraded `/spec-core` 伝達 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-123006-codex-e2e-agent-degraded-core/`
- Agent CLI Source Retrieval Index verify 失敗伝達 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-123504-codex-e2e-agent-verify-index/`
- Related Sections backend 失敗時の保持・下流停止 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-124022-codex-e2e-related-failure-retention/`
- Source Specs 変更 + pending conflict 優先順位 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-125141-codex-e2e-dirty-pending-priority/`
- inject-* 内部 gate 停止 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-130037-codex-e2e-inject-all-gates/`
- Conflict Review 生成 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-131632-codex-e2e-conflict-review-generation/`
- watcher 実行中 `/spec-core` blocked E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-134200-codex-e2e-core-blocked-watcher/`
- conflict pair cap diagnostics 修正後 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-134620-codex-e2e-conflict-pair-cap-diagnostics/`
- watcher 内部 core 更新 E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-135200-codex-e2e-watch-internal-no-agent-cli/`
- Core Concept 乖離通知なし E2E 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-141500-codex-e2e-no-core-concept-drift-notice/`
- path ④ Conflict Review Item 採用 trace 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-142000-codex-e2e-conflict-review-item-trace/`
- `/spec-inject` raw context 境界 trace 監査証跡: `doc/e2eテストCODEX実施用/evidence/20260523-142500-codex-trace-raw-context-boundary/`
- path 選択指針 trace 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-143000-codex-e2e-path-selection-trace/`
- 残件 23 行の処理証跡: `doc/e2eテストCODEX実施用/evidence/20260523-144000-codex-e2e-remaining-23/`
- P3b `/spec-core` real-smoke 証跡: `doc/e2eテスト/evidence/2026-05-23-P3b/`
- P7 横串 production E2E 証跡: `doc/e2eテスト/evidence/2026-05-23-P7/`
- 実行ログ: `doc/e2eテストCODEX実施用/evidence/20260522-214139-codex-e2e/commands.log`
- stdout / exit code: `doc/e2eテストCODEX実施用/evidence/20260522-214139-codex-e2e/stdout/`
- stderr: `doc/e2eテストCODEX実施用/evidence/20260522-214139-codex-e2e/stderr/`
- 補助 artifact: `doc/e2eテストCODEX実施用/evidence/20260522-214139-codex-e2e/artifacts/`

実行環境では、production E2E / Agent trace の根拠にする経路で `SPEC_ANCHOR_FAKE_LLM` と `SPEC_ANCHOR_FAKE_RETRIEVAL` を unset した。CLI 外部入出力 E2E は実 Qdrant と実 FlagEmbedding BGE-M3 を使い、Agent trace は実 Codex CLI または実 Claude CLI の trace を使った。smoke / fake contract の確認だけは別枠として fake env を使い、production E2E 完了扱いにはしていない。

## 2. 進捗

`doc/EXTERNAL_DESIGN.ja.md` の初期 `[ ]` は 361 件である。Codex 進捗コピーでは、production E2E または Agent trace として検証した行を `✅` にした。ただし、この `✅` は Codex 側の検証候補であり、`doc/EXTERNAL_DESIGN.ja.md` の完了状態ではない。smoke 用 / fake env contract 用の 4 件はユーザー判断により `✅` にしたが、production E2E 完了扱いにはしない。

`20260523-144000-codex-e2e-remaining-23` とユーザー判断の smoke / fake 別枠チェック反映後の `doc/e2eテストCODEX実施用/EXTERNAL_DESIGN.codex-progress.ja.md` の未チェック行数は次の通りである。

| 区分 | 残っている `[ ]` 行数 | チェック未完了残件数 | 追加 production E2E / Agent trace が必要か | 対象 |
|---|---:|---:|---|---|
| legend / 運用説明 | 4 | 0 | いいえ | 11, 18, 29, 31 行目。実検証単位ではない |
| 別 Codex 指摘で明確化された未実施チェック項目 | 0 | 0 | いいえ | 48-50 行目、62-63 行目、67 行目、143-144 行目、148 行目、154 行目、163 行目は `20260523-144000-codex-e2e-remaining-23` で `✅` 化 |
| step 可視化用で、path 単位 trace は検証済み | 0 | 0 | いいえ | 817-822 行目 path ①、832-833 行目 path ②は `20260523-144000-codex-e2e-remaining-23` で `✅` 化 |
| smoke / fake contract であり production E2E 完了扱いしない | 0 | 0 | いいえ (smoke / fake 別枠) | 495 行目 `--run-smoke` option、1226-1227 行目 `SPEC_ANCHOR_FAKE_*`、1411 行目 `spec-anchor-setup-system --run-smoke` はユーザー判断により `✅` |

legend を除く残 `[ ]` は 0 行である。`[ ]` が残っているのは凡例 / 運用説明のみであり、実検証単位ではない。

別 Codex 指摘により未実施チェック項目として明確化した 11 件の内訳:

- 48-50 行目: 標準経路に property graph / entity relation graph / hierarchical cluster、Concept 自動更新、広範な conflict 承認フロー、実行モード分岐を含めないこと、および未解決 conflict が warning-only で進まないことの標準経路 exclusion / blocker 契約。
- 62-63 行目、67 行目: 方式分類として Hybrid RAG と lightweight related-section retrieval が成立していること、および Related Sections が graph traversal ではなく payload lookup と Agent の再帰的 `inject-section` lookup で辿られること。
- 143-144 行目、148 行目、154 行目、163 行目: Section Search Keys / Section Identifiers の分離、Identifiers の機械抽出、Search Keys / Identifiers を制約根拠にしない契約。

disposition: 別 Codex 指摘は「既存証跡で検証済み」ではなく「テスト項目として漏れている」という指摘として採用した。`20260523-144000-codex-e2e-remaining-23` で追加確認し、上記 11 件は `✅` にした。証跡は `artifacts/remaining-23-assertions.json` の `line_48`、`line_49`、`line_50`、`line_62`、`line_63`、`line_67`、`line_143`、`line_144`、`line_148`、`line_154`、`line_163` を参照する。

smoke / fake 別枠残件 4 件の内訳:

- 495 行目: `--run-smoke` option による Agent CLI 認識性 smoke probe。
- 1226 行目: `SPEC_ANCHOR_FAKE_LLM` の fake provider contract。
- 1227 行目: `SPEC_ANCHOR_FAKE_RETRIEVAL` の fake retrieval contract。
- 1411 行目: `spec-anchor-setup-system --run-smoke` の Agent CLI 認識性 warning contract。

disposition: 上記 4 件は `20260523-144000-codex-e2e-remaining-23` で別枠として実行し、ユーザー判断により `✅` にした。ただし smoke / fake contract であるため production E2E 完了扱いにはしない。証跡は `artifacts/remaining-23-assertions.json` の `line_495`、`line_1226`、`line_1227`、`line_1411` を参照する。

step 可視化用として処理した 8 件の内訳:

- 817-822 行目: path ① Qdrant section-level retrieval のステップ 1-6。
- 832-833 行目: path ② chapter_anchors.json による章単位エントリのステップ 1-2。

disposition: 上記 8 件は `20260523-144000-codex-e2e-remaining-23` で既存 path trace と raw context trace を監査し、手順省略がないことを確認したため `✅` にした。証跡は `artifacts/remaining-23-assertions.json` の `lines_817_822_path1_step_visualization` と `lines_832_833_path2_step_visualization` を参照する。

この `✅` は正本昇格前の Codex 側候補であり、`doc/EXTERNAL_DESIGN.ja.md` の完了状態ではない。正本へ反映する場合は、この結果と Claude 側証跡を照合してから行う。

## 3. 作成済み

- `doc/e2eテストCODEX実施用/test_plan.ja.md`
- `doc/e2eテストCODEX実施用/EXTERNAL_DESIGN.codex-progress.ja.md`
- `doc/e2eテストCODEX実施用/evidence/20260522-214139-codex-e2e/`
- `doc/e2eテストCODEX実施用/evidence/20260523-000315-codex-e2e-additional/`
- `doc/e2eテストCODEX実施用/evidence/20260523-001153-codex-e2e-f001-retest/`
- `doc/e2eテストCODEX実施用/evidence/20260523-002300-codex-e2e-slash-skill/`
- `doc/e2eテストCODEX実施用/evidence/20260523-010512-codex-e2e-f002-retest/`
- `doc/e2eテストCODEX実施用/evidence/20260523-013834-codex-e2e-remaining/`
- `doc/e2eテストCODEX実施用/evidence/20260523-014701-codex-e2e-watchqueue-only/`
- `doc/e2eテストCODEX実施用/evidence/20260523-014753-codex-e2e-watchqueue-only/`
- `doc/e2eテストCODEX実施用/evidence/20260523-015624-codex-e2e-remaining2/`
- `doc/e2eテストCODEX実施用/evidence/20260523-020721-codex-e2e-remaining3/`
- `doc/e2eテストCODEX実施用/evidence/20260523-021012-codex-e2e-remaining4/`
- `doc/e2eテストCODEX実施用/evidence/20260523-021336-codex-e2e-debug-env2/`
- `doc/e2eテストCODEX実施用/evidence/20260523-021533-codex-e2e-chapter-failure/`
- `doc/e2eテストCODEX実施用/evidence/20260523-021648-codex-e2e-section-boundary/`
- `doc/e2eテストCODEX実施用/evidence/20260523-021742-codex-e2e-partial-upsert/`
- `doc/e2eテストCODEX実施用/evidence/20260523-021855-codex-e2e-ordinal-migration/`
- `doc/e2eテストCODEX実施用/evidence/20260523-022006-codex-e2e-defer-gate/`
- `doc/e2eテストCODEX実施用/evidence/20260523-022041-codex-e2e-resolution-readonly/`
- `doc/e2eテストCODEX実施用/evidence/20260523-022243-codex-e2e-debug-related-prompt/`
- `doc/e2eテストCODEX実施用/evidence/20260523-022644-codex-e2e-llm-boundary/`
- `doc/e2eテストCODEX実施用/evidence/20260523-090550-codex-e2e-f004-retest/`
- `doc/e2eテストCODEX実施用/evidence/20260523-091016-codex-e2e-f004-template-retest/`
- `doc/e2eテストCODEX実施用/evidence/20260523-091402-codex-e2e-f004-postfix-retest/`
- `doc/e2eテストCODEX実施用/evidence/20260523-092828-codex-e2e-agent-blockers/`
- `doc/e2eテストCODEX実施用/evidence/20260523-093821-codex-e2e-agent-blockers-tmp/`
- `doc/e2eテストCODEX実施用/evidence/20260523-093953-codex-e2e-agent-blockers-isolated/`
- `doc/e2eテストCODEX実施用/evidence/20260523-095825-codex-e2e-f005-retest/`
- `doc/e2eテストCODEX実施用/evidence/20260523-101202-codex-e2e-inject-output/`
- `doc/e2eテストCODEX実施用/evidence/20260523-103156-codex-e2e-realign-output/`
- `doc/e2eテストCODEX実施用/evidence/20260523-104149-codex-e2e-agent-core-errors/`
- `doc/e2eテストCODEX実施用/evidence/20260523-110135-codex-e2e-parallel-safe/`
- `doc/e2eテストCODEX実施用/evidence/20260523-112043-codex-e2e-degraded-section-metadata/`
- `doc/e2eテストCODEX実施用/evidence/20260523-121607-codex-e2e-f006-retest/`
- `doc/e2eテストCODEX実施用/evidence/20260523-122638-codex-e2e-search-key-limit/`
- `doc/e2eテストCODEX実施用/evidence/20260523-123006-codex-e2e-agent-degraded-core/`
- `doc/e2eテストCODEX実施用/evidence/20260523-123504-codex-e2e-agent-verify-index/`
- `doc/e2eテストCODEX実施用/evidence/20260523-124022-codex-e2e-related-failure-retention/`
- `doc/e2eテストCODEX実施用/evidence/20260523-125141-codex-e2e-dirty-pending-priority/`
- `doc/e2eテストCODEX実施用/evidence/20260523-130037-codex-e2e-inject-all-gates/`
- `doc/e2eテストCODEX実施用/evidence/20260523-131632-codex-e2e-conflict-review-generation/`
- `doc/e2eテストCODEX実施用/evidence/20260523-134200-codex-e2e-core-blocked-watcher/`
- `doc/e2eテストCODEX実施用/evidence/20260523-134620-codex-e2e-conflict-pair-cap-diagnostics/`
- `doc/e2eテストCODEX実施用/evidence/20260523-135200-codex-e2e-watch-internal-no-agent-cli/`
- `doc/e2eテストCODEX実施用/evidence/20260523-141500-codex-e2e-no-core-concept-drift-notice/`
- `doc/e2eテストCODEX実施用/evidence/20260523-142000-codex-e2e-conflict-review-item-trace/`
- `doc/e2eテストCODEX実施用/evidence/20260523-142500-codex-trace-raw-context-boundary/`
- `doc/e2eテストCODEX実施用/evidence/20260523-143000-codex-e2e-path-selection-trace/`
- `doc/e2eテストCODEX実施用/evidence/20260523-144000-codex-e2e-remaining-23/`
- `doc/e2eテスト/evidence/2026-05-23-P3b/`
- `doc/e2eテスト/evidence/2026-05-23-P7/`
- `doc/e2eテストCODEX実施用/RESULTS.ja.md`

## 4. none / fake profile で passing

`20260523-144000-codex-e2e-remaining-23` で `SPEC_ANCHOR_FAKE_LLM` と `SPEC_ANCHOR_FAKE_RETRIEVAL` の fake contract を別枠確認した。

- `SPEC_ANCHOR_FAKE_LLM=1` では、`build_spec_core_llm_provider` が `[llm.providers.<id>]` の child process command ではなく `FakeLlmProvider` を返すことを確認した。
- `SPEC_ANCHOR_FAKE_RETRIEVAL=1` では、直接の `FlagEmbeddingBgeM3Provider()` 構築が block されることと、標準の `spec-anchor core --rebuild` は実 Qdrant / BGE-M3 経路を継続して `retrieval_index_status="success"` を返すことを確認した。

これらは fake contract の確認である。ユーザー判断により進捗コピーでは `✅` にしたが、production E2E 完了数には入れていない。

## 5. local-service / real provider で passing

### E1 setup / system

`spec-anchor-setup-system --check-only --qdrant-url http://localhost:6333` を実行し、PATH に `.venv/bin` が入っている状態で `production_readiness.status="ready"` を確認した。

PATH に `.venv/bin` が無い状態では `production_readiness.status="blocked"`、不足理由 `console_script_missing` を exit code 0 で返すことも確認した。

`spec-anchor-setup-project` は dry-run、apply、repeat、force、conflict、conflict + force を確認した。conflict 時は exit code 1、`status="conflict"`、差分付きで停止し、`--force` 時は設定 file を更新した。Purpose / Core Concept の既存 human file は保護された。

### E2 `/spec-core`

tmp project に Source Specs、Purpose、Core Concept、実 Qdrant collection を用意し、次を確認した。

- `spec-anchor core --rebuild`: exit code 0、`status="updated"`、`freshness_report.status="fresh"`、`retrieval_index_status="success"`、`related_sections_status="success"`。
- `spec-anchor core`: exit code 0、`retrieval_index_status="skipped_unchanged"`、`related_sections_status="skipped_unchanged"`。
- `spec-anchor core --all`: exit code 0、全 Section 再評価。

生成物として `.spec-anchor/context/chapter_anchors.json`、`.spec-anchor/context/conflict_review_items.json`、`.spec-anchor/state/section_manifest.json`、`.spec-anchor/state/freshness.json`、`.spec-anchor/state/core_progress.json`、`.spec-anchor/cache/` を確認した。

`.spec-anchor/state/retrieval_index_state.json` は Source Retrieval Index の section 集合 hash 指紋、embedding / retrieval 設定指紋、collection name を保持していた。現在の section 集合と設定が一致する場合、section collection upsert は `skipped_unchanged` で終了した。

`.spec-anchor/state/related_sections_state.json` は Related Sections の section 集合 hash、candidate generation 設定指紋、LLM selection 設定指紋を保持していた。現在の section 集合と設定が一致する場合、Related Sections は `skipped_unchanged` で終了した。

### E3 freshness / watcher

Source Specs 変更後に `spec-anchor-watch --once` を実行し、exit code 0、`cycles` 1 件、5 Section への更新、freshness 更新を確認した。追加した `Password Reset` section は更新後の `inject-search` で検索対象に含まれた。

ただし、初回実行時点では、変更直後かつ watcher 実行前の `spec-anchor inject-search password reset` は停止せず exit code 0 で検索結果を返した。この差異は `CODEX-E2E-F001` として記録し、Claude 修正後の再テストで解消を確認した。

### E4 `/spec-inject`

E2 で生成した保持物に対し、次を確認した。

- `spec-anchor inject-search authentication session`: exit code 0、Section payload の検索結果を返す。
- `spec-anchor inject-section <source_section_id>`: exit code 0、指定 Section payload を返す。
- `spec-anchor inject-chapters`: exit code 0、`chapter_anchors.json` の path を返す。
- `spec-anchor inject-purpose`: exit code 0、Purpose 全文と Core Concept path を返す。
- `spec-anchor inject-conflicts`: exit code 0、Conflict Review Item 一覧を返す。

CLI は constraint statement や answer を自由生成せず、検索結果、Section payload、path、Purpose、Conflict Review Item の取得 API として振る舞った。

### E5 `/spec-realign`

`spec-anchor realign --answer-file <valid-json>` で exit code 0、`status="fresh"`、`should_stop=false`、4 区分 answer の整形結果を確認した。

answer を渡さない `spec-anchor realign` では exit code 0、`status="fresh"`、`stop_reason="needs_agent_answer"`、`should_stop=true` を確認した。

### E6 エラー契約

次の外部入力で structured error / failed result を確認した。

- `.spec-anchor/config.toml` 不在の `spec-anchor core`: exit code 1。
- `.spec-anchor/config.toml` 不在の `spec-anchor inject-search`: exit code 0、`status="error"`、`should_stop=true`。
- `.spec-anchor/config.toml` 不在の `spec-anchor realign --answer-json ...`: exit code 1。
- `.spec-anchor/config.toml` 不在の `spec-anchor-watch --once`: exit code 0、`status="error"`。
- Purpose file 不在の `spec-anchor core`: exit code 1。
- Source Specs 0 件の `spec-anchor core`: exit code 1。
- Qdrant 到達不能の `spec-anchor core --rebuild`: exit code 1、`Source Retrieval Index update failed` と Related Sections retrieval backend failure を warning に含む。

### E7 追加外部入出力 E2E

`20260523-000315-codex-e2e-additional` で、未実行だった外部入出力 E2E を追加した。

- `spec-anchor-setup-project --agent codex` / `--agent claude` / `--no-init-core-files`。
- `spec-anchor-setup-project --target <missing>` / file path target の error contract。
- `spec-anchor-setup-system` の Qdrant service unavailable、Agent CLI unavailable、FlagEmbedding / qdrant_client unavailable。
- `<project_root>` 直下の `.spec-anchor/config.toml` だけを読むこと、親 directory の config を自動探索しないこと。
- Core Concept file missing の `/spec-core` error contract。
- `failed_required_artifact` 状態での `inject-search` / `realign` 停止。
- `pending_conflict` 状態での `inject-search` / `realign` 停止と pending conflict item の出力。
- `watcher_running` 状態での `inject-search` / `realign` 停止。
- `realign` の `--answer` / `--answer-text` / `--agent-answer` / `--answer-json` / `--agent-answer-json`。
- `spec-anchor-watch --once --interval-sec --debounce-sec --stale-lock-sec --max-runs` の stdout settings。
- Qdrant payload の UUID5 point id、namespace、必須 payload key。
- Qdrant collection 手動削除後に `.spec-anchor/state/retrieval_index_state.json` の前提が崩れ、`section_collection_upsert.action="upserted_full"` / `reason="collection_missing"` で復旧すること。
- `spec-anchor core --verify-index` が不整合を検出し、`retrieval_index_status="failed"` と warning `Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild` を返すこと。

### F001 Claude 修正後の再テスト

`20260523-001153-codex-e2e-f001-retest` で、Claude 修正後の `CODEX-E2E-F001` を再テストした。

clean な fresh project の Source Specs に新 Section を追記し、`/spec-core` または watcher 更新前に次を実行した。

- `spec-anchor inject-search password reset`: exit code 0、`status="blocked"`、`blocking_reasons=["dirty_or_stale_source"]`、`recommended_next_action="run /spec-core before /spec-inject"`。
- `spec-anchor realign --answer-json <valid-json>`: exit code 0、`status="blocked"`、`blocking_reasons=["dirty_or_stale_source"]`、`recommended_next_action="run /spec-core before /spec-realign"`。

この再テストで、`CODEX-E2E-F001` は解消済みとして扱う。

### E8 slash command / Codex skill

`20260523-002300-codex-e2e-slash-skill` で、Agent CLI 入口を実機で確認した。証跡集約は `artifacts/slash-skill-assertions.json` に保存した。

- Claude Code `/spec-core`: clean tmp project で slash command が認識され、`spec-anchor core` が実行された。stdout に `updated_sources=docs/spec/auth.md`、`retrieval_index_status="success"`、`freshness_report.status="fresh"`、`pending_conflict_count=0` を含む利用者向けサマリが出た。
- Claude Code `/spec-inject`: `spec-anchor inject-search` / `inject-purpose` / `inject-conflicts` と Source Specs / Core Concept の Read が tool trace に残り、最終出力は `今回守る制約` / `今回見るべき対象` / `関連先として確認したもの` / `不確実性 / 人間確認` の構造で、raw JSON ではなかった。
- Codex CLI skill: `codex exec -C <tmp project>` が project-local `.codex/skills/spec-anchor/SKILL.md` を読み、`spec-anchor inject-chapters` / `inject-search` / `inject-purpose` / `inject-conflicts` / `inject-section` / `realign --answer-file` を外部 CLI I/O として実行した。最終出力は 4 区分 answer で、`status=fresh` と blocker 無しを確認した。

初回実行では Claude Code `/spec-realign` の normal path は通過扱いにしていなかった。詳細は `CODEX-E2E-F002` に残し、その後の再テストで解消を確認した。

### E9 F002 / F003 修正後の slash command / skill 再テスト

`20260523-010512-codex-e2e-f002-retest` で、Claude 修正後の template と配付済み command / skill を新規 clean tmp project に配付し、実 Qdrant / BGE-M3 / Claude CLI / Codex CLI で再テストした。

- Claude Code `/spec-realign`: init `cwd` は `/tmp/spec-anchor-codex-e2e-f002-retest.N4Lyjy`、project-local `.spec-anchor/config.toml` を使い、`spec-anchor inject-*` と `spec-anchor realign` を同 project で実行した。前回の `/home/kazuki/public_html/ec-spoke.local` / `/home/kazuki/public_html/llm-helper` 探索は再現しなかった。
- Claude Code `/spec-inject`: `採用しなかったもの` セクションを出力し、`不確実性 / 人間確認` で `該当なし` を明示した。
- Codex CLI skill: `採用しなかったもの` セクションを出力し、`不確実性 / 人間確認` で `該当なし` を明示した。
- 証跡集約: `artifacts/f002-retest-assertions.json`、`artifacts/f003-retest-assertions.json`。

補足: Claude Code `/spec-realign` の再テスト中、Agent は一度 `spec-anchor inject-search --keys ...` という存在しない option を試し、`spec-anchor inject-search --help` で回復した後に正常完了した。F002 の別 project 探索は解消済みとして扱うが、途中の CLI option 誤用を normal path で許容しない方針にする場合は、別ケースとして template 強化と再テストが必要である。

補足: Claude Code `/spec-inject` の F003 再テストでは `採用しなかったもの` は出たが、最終出力末尾に constraints JSON の code block も併記された。CLI の raw JSON そのものではないが、「raw JSON を会話に貼らない」を constraints JSON にも適用する場合、当時は §11.2 `/spec-inject` 正常経路を未通過として扱った。後続の E16 で raw JSON と code fence を出さない通常出力を再確認し、この範囲は通過済みにした。

### E10 残項目追加 E2E

`20260523-013834-codex-e2e-remaining` と `20260523-014753-codex-e2e-watchqueue-only` で、残っていた外部入出力 E2E の一部を追加した。

- `spec-anchor-setup-project` の新規 project 出力 `.spec-anchor/config.toml` に、初期 TOML の必須 key、`[llm.providers]` の `codex` / `claude_typing` / `claude_judge`、`[llm.stage_routing]` の 4 stage、`[watcher].state_file` / `[watcher].queue_file` が含まれることを確認した。
- Codex skill と Claude command template が `spec-anchor core --llm-provider ...` を通常指定しないことを、配付済み file の外部出力として確認した。
- 実 `spec-anchor-watch --once` 実行中に Source Specs を追加変更し、`.spec-anchor/state/watch_queue.json` に未処理キュー、`.spec-anchor/state/watch_state.json` に watcher 状態が残り、`.spec-anchor/state/freshness.json` が `blocking_reasons=["watcher_queue_pending"]` を返すことを確認した。
- 上記の実 watcher run 直後の `inject-search` / `realign` は、Source Specs 変更も同時に残ったため `blocking_reasons=["dirty_or_stale_source","watcher_queue_pending"]` となり、推奨 action は dirty 優先で `/spec-core` になった。このため watcher-only の推奨 action は同 run では通過扱いにしていない。
- fresh project に外部状態入力として `.spec-anchor/state/freshness.json` と `.spec-anchor/state/watch_queue.json` を `watcher_queue_pending` のみに設定し、`spec-anchor inject-search` と `spec-anchor realign --answer-file` が exit code 0、`status="blocked"`、`recommended_next_action="wait for watcher completion before /spec-inject"` / `"wait for watcher completion before /spec-realign"` を返すことを確認した。
- stale な watcher running state に対して `spec-anchor-watch --once --stale-lock-sec 0.1` を実行し、`stale_lock_discarded=true`、最終 `.spec-anchor/state/freshness.json` が `status="fresh"` / `blocking_reasons=[]` になることを確認した。
- Claude Code `/spec-core` の Purpose 不在、Core Concept 不在、Source Specs 0 件は、Agent が `spec-anchor core` を実行し、CLI のエラー内容と復旧手順を利用者向け出力で伝達した。
- Claude Code `/spec-core` / `/spec-inject` / `/spec-realign` の `.spec-anchor/config.toml` 不在ケースは、初回時点では利用者向けに `spec-anchor-setup-project` を提案したが、`spec-anchor core` / `spec-anchor inject-*` / `spec-anchor realign` を実行せず `ls` による事前確認で停止した。§11.2 が求める「Agent が CLI を実行し、その JSON を伝達する」契約は満たしていなかったため、`CODEX-E2E-F004` として切り出した。修正後の再テスト結果は E13 と §8 に記録する。

### E11 config / CLI 境界 / env 追加 E2E

`20260523-015624-codex-e2e-remaining2`、`20260523-021336-codex-e2e-debug-env2` で、設定項目と CLI 境界を追加確認した。

- `spec-anchor-setup-project` が出力する `.spec-anchor/config.toml` に、§10.2 の主要 table / key、`[llm.providers]` の `codex` / `claude_typing` / `claude_judge`、`[llm.stage_routing]` の 4 stage、retrieval / embedding / vector_store / limits / watcher 設定が含まれることを確認した。
- `spec-anchor` の command surface は保持物更新と検索 API に限られ、conversation transcript や positional task prompt を CLI が受け取らないことを確認した。
- `[llm.providers]` 0 件、未知 provider 参照、許可外 stage key、`rank_fusion` 不正値を設定エラーとして reject することを確認した。
- `spec-anchor core --llm-provider fail` は `[llm.stage_routing]` を上書きし、指定 provider が失敗しても別 provider へ黙って切り替えないことを確認した。
- `[llm.providers]` / `[llm.stage_routing]` をすべて失敗 provider に向けても、fresh な project の `inject-search` / `realign --answer-file` は spec-core stage provider を使わず通ることを確認した。
- project root の `.env` は `spec-anchor core` 起動時に `load_config` 経由で読み込まれ、既存 shell env は `.env` で上書きされないことを確認した。debug env を set しても stdout JSON の exit/status shape は変わらず、追加 JSONL だけが出ることを確認した。

### E12 Conflict Review / Qdrant / Chapter 追加 E2E

`20260523-021012-codex-e2e-remaining4` 以降で、Conflict Review と Qdrant の外部入出力 E2E を追加した。

- `--decision-json` / `--decision-file` で pending Conflict Review Item に人間判断 payload を渡し、`prefer_a` / `prefer_b` / `conditional` / `dismiss` / `needs_source_update` / `defer` / `task_scope_resolution` の遷移を確認した。
- `defer` は `pending` のまま残り、同 project の `inject-search` / `realign --answer-file` が `blocking_reasons=["pending_conflict"]` で停止することを確認した。
- resolved item は `resolution`、`referenced_source_refs`、`valid_scope`、`unreflected_conflict_resolutions` を持つ。Source Specs 変更後は `stale_resolution=true` / `stale_resolution_count=1` になった。
- resolution 適用後も `docs/core/purpose.md`、`docs/core/concept.md`、`docs/spec/auth.md` の hash は変更されず、Purpose / Core Concept / Source Specs へ自動反映されないことを確認した。
- `[section].max_heading_level` より深い Markdown 見出しは独立 Section にならず、直近の親 Section span に含まれることを確認した。
- `.spec-anchor/state/related_sections_state.json` の section hash / candidate generation 設定指紋が不一致になると、Related Sections は `core_progress.json` の `stages.related_sections.action="fallback_regenerated"` で通常生成経路に戻ることを確認した。
- Chapter Key Anchor の LLM 生成失敗時、CLI は exit code 1 / `status="failed"` / `failed_required_artifacts=["chapter_anchors"]` を返し、canonical `.spec-anchor/context/chapter_anchors.json` の hash は前回値のまま保持された。
- 実 Qdrant + BGE-M3 で、numeric point id を持つ旧 collection を検出すると `section_collection_upsert.action="upserted_full"` / `reason="migration_required_from_ordinal_point_id"` で recreate し、post-migration point id が UUID になることを確認した。
- 実 Qdrant + BGE-M3 で、一部 Section の変更と削除を行った incremental 実行が `section_collection_upsert.action="upserted_partial"`、`sections_upserted_count=2`、`sections_deleted_count=1`、`embed_documents_input_size=2`、`stale_points_deleted=1` を返すことを確認した。

### E13 F004 修正後の slash command エラー契約再テスト

`20260523-090550-codex-e2e-f004-retest`、`20260523-091016-codex-e2e-f004-template-retest`、`20260523-091402-codex-e2e-f004-postfix-retest` で、`.spec-anchor/config.toml` 不在の Claude Code slash command 3 ケースを再テストした。

- 初回再テスト: 配付済み `.claude/commands` は `spec-anchor` CLI 実行へ戻っていなかった、または `spec-anchor inject` / `inject-search --keys` など CLI と合わない呼び出しが残っていたため未通過。
- Codex 修正: `spec_anchor/templates/.claude/commands/spec-realign.md` を §11.2 に合わせ、answer candidate がある場合は `spec-anchor realign --answer-json '<json>'` を gate probe として先に実行し、`should_stop=true` / `status="error"` なら停止して `spec-anchor-setup-project --target <project_root>` を提示する手順に変更した。配付済み `.claude/commands/*.md` と `.codex/skills/spec-anchor/SKILL.md` も template と同期した。
- 修正後再テスト: `/spec-core` は `spec-anchor core 2>&1`、`/spec-inject` は `spec-anchor inject-search "認証 auth authentication" 2>&1`、`/spec-realign` は `spec-anchor realign --answer-json '<json>' 2>&1` を実行した。3 ケースとも `.spec-anchor/config.toml not found under <tmp>` を利用者向け出力に含め、`spec-anchor-setup-project --target <tmp>` を提案した。
- 証跡集約: `artifacts/f004-retest-assertions.json`、`artifacts/f004-template-retest-assertions.json`、`artifacts/f004-postfix-retest-assertions.json`。

### E14 Agent CLI blocker エラー契約追加 E2E

`20260523-092828-codex-e2e-agent-blockers`、`20260523-093821-codex-e2e-agent-blockers-tmp`、`20260523-093953-codex-e2e-agent-blockers-isolated` で、§11.2 の Agent CLI blocker 伝達を追加確認した。最終判定は isolated run の `artifacts/agent-blockers-isolated-assertions.json` を正とする。

- 初回 run は project を repo 配下に置いたため、一部 Claude tool call が親 repo root へ `cd` した。これはテスト隔離の問題として扱い、`/tmp` project へ移して再実行した。
- `/spec-inject` dirty/stale 系: Claude Code は `spec-anchor inject-search ...` を実行し、`blocking_reasons=["dirty_or_stale_source"]`、`recommended_next_action="run /spec-core before /spec-inject"` を利用者向け出力に含めた。`/spec-core` は自動実行しなかった。
- `/spec-inject` watcher queue 系: Claude Code は `spec-anchor inject-search ...` を実行し、`blocking_reasons=["watcher_queue_pending"]`、`recommended_next_action="wait for watcher completion before /spec-inject"` を利用者向け出力に含めた。
- `/spec-inject` pending conflict: Claude Code は `pending_conflict_items` の `conflict_id=conflict-auth-session-e2e`、`severity`、`claims`、`why_conflicting`、`why_llm_cannot_decide`、`decision_options`、`source_refs`、`recommended_next_action="Ask a human to decide this conflict."` を利用者に提示した。
- `/spec-inject` failed required artifact: Claude Code は `blocking_reasons=["failed_required_artifact"]`、`recommended_next_action="run /spec-core or /spec-core --all before /spec-inject"`、`Source Retrieval Index update failed`、Related Sections retrieval backend failure を利用者向け出力に含めた。
- `/spec-realign` dirty/stale 系: Claude Code は `spec-anchor realign --answer-json ...` を実行し、`blocking_reasons=["dirty_or_stale_source"]`、`recommended_next_action="run /spec-core before /spec-realign"` を利用者に伝達した。
- `/spec-realign` watcher queue 系: template 強化後、Claude Code は `spec-anchor realign --answer-json ...` を実行し、`blocking_reasons=["watcher_queue_pending"]`、`recommended_next_action="wait for watcher completion before /spec-realign"` を伝達した。初回に出た契約外の `spec-anchor status` 提案は再テストで出なかった。
- `/spec-realign` failed required artifact: Claude Code は `blocking_reasons=["failed_required_artifact"]`、`recommended_next_action="run /spec-core or /spec-core --all before /spec-realign"`、失敗 warning を利用者向け出力に含めた。
- `/spec-realign` needs answer: answer candidate を構成できない条件を利用者入力で明示し、Claude Code が `spec-anchor realign 2>&1` を実行し、`stop_reason="needs_agent_answer"`、`recommended_next_action="provide an Agent-generated answer candidate for /spec-realign"` を伝達して停止した。
- 初回差異: `/spec-realign` pending conflict は `conflict_id`、`severity`、`claims`、`why_conflicting`、`why_llm_cannot_decide`、`decision_options`、`source_refs` と人間判断の必要性を出したが、item 側の `recommended_next_action="Ask a human to decide this conflict."` を最終出力に含めなかった。`CODEX-E2E-F005` として切り出した。修正後の再テスト結果は E15 と §8 に記録する。

### E15 F005 修正後の slash command / skill pending conflict 再テスト

`20260523-095825-codex-e2e-f005-retest` で、Claude `/spec-realign` と Codex skill の pending conflict 伝達を再テストした。証跡集約は `artifacts/f005-retest-assertions.json` に保存した。

- 修正: `.claude/commands/spec-realign.md` と `spec_anchor/templates/.claude/commands/spec-realign.md` に、pending conflict では top-level `recommended_next_action` だけでなく、各 `pending_conflict_items[]` の item 側 `recommended_next_action` を literal に出す規約を追加した。同じ停止・復旧手順を `.codex/skills/spec-anchor/SKILL.md` と `spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md` にも反映した。
- Claude Code `/spec-realign`: `spec-anchor realign --answer-json ...` を実行し、`blocking_reasons=["pending_conflict"]`、`conflict_id=conflict-auth-session-e2e`、`severity`、`claims`、`why_conflicting`、`why_llm_cannot_decide`、`decision_options`、`source_refs`、`recommended_next_action: Ask a human to decide this conflict.` を利用者向け最終出力に含めた。answer の整形は実行しなかった。
- Codex CLI skill: project-local `.codex/skills/spec-anchor/SKILL.md` を読み、`spec-anchor realign --answer-file` を外部入力ファイルで実行した。CLI stdout は `pending_conflict` を返し、最終出力は raw JSON ではなく、`pending_conflict_items` と item 側 `recommended_next_action: Ask a human to decide this conflict.` を含んだ。`--answer-file` は §9.4 / §11.2 の `/spec-realign` 入力として許可される。
- 判定: `passed_f005=true`、`passed_codex_skill_f005=true`、`passed_f005_all_agent_entries=true`。

### E16 `/spec-inject` §8.5 通常出力 E2E

`20260523-101202-codex-e2e-inject-output` で、§8.5 の通常出力を、test docs を持つ隔離 project で再テストした。証跡集約は `artifacts/inject-output-8-5-assertions.json` に保存した。

- 入力: `/tmp/20260523-101202-codex-e2e-inject-output.project` に `docs/core/purpose.md`、`docs/core/concept.md`、`docs/spec/login.md`、`docs/spec/audit.md` を作成した。管理者ログイン MFA、監査イベント、保存先、保持期間未確定、スコープ外候補を意図的に含めた。
- 隔離: `.spec-anchor/config.toml` の Qdrant collection は `spec_anchor_sections_20260523_101202_inject_output` に固定した。初回準備 script は `spec_anchor_sections` だけを置換していたが、実際の既定値は `spec_anchor_section` だったため、test harness を修正して run 固有 collection で `/spec-core --rebuild` を再実行した。
- Core: `SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` を unset し、実 Qdrant / BGE-M3 / real provider で `spec-anchor core --rebuild` を実行した。`status="updated"`、`freshness_report.status="fresh"`、`retrieval_index_status="success"`、`related_sections_status="success"`、`pending_conflict_count=0` を確認した。
- Preflight: `spec-anchor inject-search "管理者ログイン 監査 MFA AUDIT_EVENT_REQUIRED"` が exit code 0 で `docs/spec/login.md#0003-audit-event-required`、`docs/spec/login.md#0002-admin-login-mfa` などを返した。
- Claude Code `/spec-inject`: stdin 経由で発火し、`spec-anchor inject-search` / `inject-purpose` / `inject-chapters` / `inject-section` / `inject-conflicts` を実行した。最終出力は 5 セクションを含み、各 constraint item に `statement` / `evidence_origin` / `evidence_ref` / `support_refs` / `applicability` / `uncertainty` を含めた。raw JSON と code fence は出さず、課題への最終回答・実装案・コードも出さなかった。
- Codex CLI skill: project-local `.codex/skills/spec-anchor/SKILL.md` を読み、`spec-anchor inject-search` / `inject-section` / `inject-purpose` / `inject-conflicts` と Source Specs / Core Concept の Read を実行した。最終出力は Claude と同じく 5 セクション、制約フィールド、採用しなかったもの、不確実性を含み、raw JSON と code fence は出さなかった。
- 判定: `claude.passed_8_5_output_contract=true`、`codex_skill.passed_8_5_output_contract=true`、`passed_both_agent_outputs=true`。

### E17 `/spec-realign` §9.3 通常出力 E2E

`20260523-103156-codex-e2e-realign-output` で、§9.3 の通常出力を、test docs を持つ隔離 project で再テストした。証跡集約は `artifacts/realign-output-9-3-assertions.json` に保存した。

- 入力: `/tmp/20260523-103156-codex-e2e-realign-output.project` に、管理者ログイン MFA、監査イベント、`audit_log_stream`、`RETENTION_DAYS_FOR_AUTH_LOG` 未確定、セッション発行境界を含む Source Specs / Purpose / Core Concept を配置した。
- Core: `SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` を unset し、run 固有 Qdrant collection `spec_anchor_sections_20260523_103156_realign_output` で `spec-anchor core --rebuild` を実行した。`status="updated"`、`freshness_report.status="fresh"`、`retrieval_index_status="success"`、`related_sections_status="success"`、`pending_conflict_count=0` を確認した。
- Preflight: `spec-anchor inject-search "管理者ログイン 監査 MFA RETENTION_DAYS_FOR_AUTH_LOG"` と `spec-anchor realign --answer-file artifacts/preflight-answer.json` が exit code 0 で通った。
- Claude Code `/spec-realign`: `spec-anchor inject-*` と `spec-anchor realign --answer-*` を実行し、最終出力に §9.3 の 4 区分を含めた。利用者の初期案「`RETENTION_DAYS_FOR_AUTH_LOG` を 30 日固定にする」は仕様上の未確定事項として「競合 / 不確実性 / 人間レビューが必要な点」に明示された。
- Codex CLI skill: project-local `.codex/skills/spec-anchor/SKILL.md` を読み、同じく `spec-anchor inject-*` と `spec-anchor realign --answer-*` を実行した。最終出力は 4 区分、MFA 制約、監査制約、30 日固定案の人間レビュー扱いを含み、raw JSON と code fence は出さなかった。
- 判定: `claude.passed_9_3_output_contract=true`、`codex_skill.passed_9_3_output_contract=true`、`passed_both_agent_outputs=true`。

### E18 Agent CLI `/spec-core` 失敗伝達 E2E

`20260523-104149-codex-e2e-agent-core-errors` で、§11.2 の `/spec-core` 失敗伝達のうち、Chapter Key Anchor 生成失敗と Qdrant 到達不能を再テストした。証跡集約は `artifacts/agent-core-errors-assertions.json` に保存した。

- Chapter Key Anchor 失敗: fresh な隔離 project を複製し、`chapter_key_anchor` stage の provider を `/bin/false` に向けた。Claude `/spec-core --all` と Codex skill はどちらも `spec-anchor core --all` を現在の project root で実行し、`status="failed"`、`Chapter Anchors LLM generation failed ... canonical chapter_anchors.json is not updated`、`/spec-core --all` 再試行を利用者向け出力に含めた。
- Qdrant 到達不能: 別の複製 project で `[vector_store].url` を `http://127.0.0.1:65531` に向けた。Claude `/spec-core --rebuild` と Codex skill はどちらも `spec-anchor core --rebuild` を現在の project root で実行し、`Source Retrieval Index update failed`、`Related Sections retrieval backend failure: [Errno 111] Connection refused`、Qdrant 復旧後の `spec-anchor core --rebuild` 再実行を利用者向け出力に含めた。
- 自動 setup / 別 project 探索: command trace 上、`spec-anchor-setup-project` の自動実行は無かった。Codex は skill file を読んだため `spec-anchor-setup-project` 文字列自体は trace に出たが、command_execution としては実行していない。
- 判定: `passed_chapter_agent_layer=true`、`passed_qdrant_agent_layer=true`、`passed_all=true`。

### E19 並列影響なし追加 E2E

`20260523-110135-codex-e2e-parallel-safe` で、Sonnet 側と衝突しない範囲の production 外部入出力 E2E を追加した。証跡集約は `artifacts/parallel-safe-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-110135-codex-e2e-parallel-safe.*.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_110135_parallel_safe_*` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- Related Sections debug prompt: 未設定 run では `.spec-anchor/state/_debug_related_prompts.jsonl` が作られず、`SPEC_ANCHOR_DEBUG_RELATED_PROMPT=1` では default path へ JSONL が出力された。`SPEC_ANCHOR_DEBUG_RELATED_PROMPT_PATH` 指定時は指定先 `artifacts/related-prompt-override.jsonl` に出力された。debug 有無で stdout JSON の status shape は一致した。
- stage routing fallback: `[llm.stage_routing]` table を削除した project で `spec-anchor core --rebuild` を実行し、provider invocation debug JSONL の resolved command がすべて先頭 provider `codex --model gpt-5.4-mini` を使うことを確認した。
- embedding input: 実 Qdrant から scroll した payload で、`text` が `heading_path` / Section Summary / Section Search Keys 先頭 8 件 / Section Identifiers 先頭 8 件を ` | ` で連結した期待値と一致した。Source Specs 本文の raw marker `raw-body-sentinel-do-not-embed-login-boundary` は embedding input text に含まれなかった。
- identifier 上限の部分確認: Section Identifiers は 15 件生成され、9 件目以降の `AUTH_SYMBOL_06` から `AUTH_SYMBOL_12` は embedding input text に含まれなかった。
- 未確定: Section Search Keys は payload 自体が 8 件だったため、Search Keys の 9 件目以降除外はこの E2E では判定できない。当時は Search Keys / Identifiers 双方の 9 件目以降除外をまとめた行を未完了として残したが、後続の E22 で provider 由来 Search Keys / Identifiers の 9 件目以降除外を確認し、進捗コピーを `✅` にした。
- 判定: `passed_debug_related_prompt=true`、`passed_stage_routing_fallback=true`、`passed_embedding_payload_formula=true`、`passed_identifier_limit=true`、`passed_all=true`。

### E20 Section Metadata degraded 追加 E2E

`20260523-112043-codex-e2e-degraded-section-metadata` で、Section Metadata の一部生成失敗を外部入力から再現した。証跡集約は `artifacts/degraded-section-metadata-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-112043-codex-e2e-degraded-section-metadata.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_112043_degraded_section_metadata` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: `[llm.providers.partial_section]` に run 固有の外部 provider command `tools/partial-section-provider.py` を設定し、Section Metadata stage で `docs/spec/flow.md#0003-broken-metadata-section` だけ invalid output を返すようにした。これは fake env ではなく、`.spec-anchor/config.toml` で指定された外部 command failure の E2E 負例である。
- 実測: `spec-anchor core --rebuild` は exit code 0、`freshness_report.status="degraded"`、`freshness_report.blocking_reasons=["degraded_optional_artifact"]`、`freshness_report.diagnostics.degraded_optional_artifacts=["section_metadata"]`、`failed_sections` に `docs/spec/flow.md#0003-broken-metadata-section` を含めた。`retrieval_index_status="success"`、`related_sections_status="success"` だった。
- 未通過: §11.1.5 の期待は top-level `status="degraded"` だが、実測は top-level `status="updated"` だった。また、degraded 状態の `spec-anchor inject-search "login audit"` は検索結果を返して継続したが、stdout の `warnings` は空で `degraded_optional_artifact` を利用者に表示しなかった。
- 判定: 修正前の差異を検出した。修正後の再テストは E21 に記録した。

### E21 F006 Section Metadata degraded 修正後再テスト

`20260523-121607-codex-e2e-f006-retest` で、SONNET 側修正後に同じ外部入力条件を再実行した。証跡集約は `artifacts/degraded-section-metadata-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-121607-codex-e2e-f006-retest.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_121607_f006_retest` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: `[llm.providers.partial_section]` に run 固有の外部 provider command `tools/partial-section-provider.py` を設定し、Section Metadata stage で `docs/spec/flow.md#0003-broken-metadata-section` だけ invalid output を返すようにした。
- 実測: `spec-anchor core --rebuild` は exit code 0、top-level `status="degraded"`、`freshness_report.status="degraded"`、`freshness_report.blocking_reasons=["degraded_optional_artifact"]`、`freshness_report.diagnostics.degraded_optional_artifacts=["section_metadata"]`、`warnings`、`failed_sections`、`updated_sections` を返した。`retrieval_index_status="success"`、`related_sections_status="success"` だった。
- degraded 継続: `spec-anchor inject-search "login audit"` は exit code 0、`warnings` に `degraded_optional_artifact` を含め、`hits` を返して継続した。`spec-anchor realign --answer-json ...` は exit code 0、`status="degraded"`、`should_stop=false`、`can_continue=true`、`blocking_reasons=["degraded_optional_artifact"]`、`warnings`、`answer` を返した。
- 判定: `passed_core_degraded_contract=true`、`passed_inject_degraded_continue=true`、`passed_realign_degraded_continue=true`、`passed_all=true`。§3.3 の warning 継続と §11.1.5 の Section Metadata degraded CLI 契約は修正後再テスト済みとして進捗コピーを `✅` にした。

### E22 Search Keys / Identifiers embedding input 上限 E2E

`20260523-122638-codex-e2e-search-key-limit` で、Section Search Keys と Section Identifiers の embedding input 上限を外部入出力で確認した。証跡集約は `artifacts/search-key-limit-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-122638-codex-e2e-search-key-limit.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_122638_search_key_limit` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: `[llm.providers.search_key_limit]` に run 固有の外部 provider command `tools/search-key-provider.py` を設定し、`docs/spec/limit.md#0002-login-limit` の Section Metadata で `limit search key 01` から `limit search key 12` まで 12 件を返した。Source Specs 本文には `AUTH_LIMIT_SYMBOL_01` から `AUTH_LIMIT_SYMBOL_12` まで 12 件の identifier を置いた。
- 実測: `spec-anchor core --rebuild` は exit code 0、`status="updated"`、`retrieval_index_status="success"`、`related_sections_status="success"` だった。実 Qdrant payload の `search_keys` は 14 件 (provider 由来 12 件 + heading 由来 2 件)、`identifiers` は 12 件だった。
- embedding input: 実 Qdrant payload の `text` は `heading_path | summary | search_keys[:8] | identifiers[:8]` の期待値と一致した。provider 由来 Search Keys の 9 件目以降 (`limit search key 09` から `limit search key 12`) と Identifiers の 9 件目以降 (`AUTH_LIMIT_SYMBOL_09` から `AUTH_LIMIT_SYMBOL_12`) は `text` に含まれなかった。
- 判定: `passed_search_key_limit=true`、`passed_identifier_limit=true`、`passed_all=true`。§4.1 の embedding input 上限行は修正後再テスト済みとして進捗コピーを `✅` にした。

### E23 Agent CLI Section Metadata degraded `/spec-core` 伝達 E2E

`20260523-123006-codex-e2e-agent-degraded-core` で、§11.2 の Section Metadata degraded 利用者向け `/spec-core` 伝達を Claude command と Codex skill の両方で確認した。証跡集約は `artifacts/agent-degraded-core-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-123006-codex-e2e-agent-degraded-core.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_123006_agent_degraded_core` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: `[llm.providers.partial_section]` に run 固有の外部 provider command `tools/partial-section-provider.py` を設定し、Section Metadata stage で `docs/spec/flow.md#0003-broken-metadata-section` だけ invalid output を返すようにした。Agent には「利用者が `/spec-core` を引数なしで発火した」状況として、現在の project root だけで `spec-anchor core` を実行するよう指示した。
- Claude command: exit code 0。trace 上 `spec-anchor core` を引数なしで実行し、`status=degraded`、失敗 section、warning、必須 artifact が揃っているため `/spec-inject` / `/spec-realign` は継続可能であること、失敗 section 再生成には `/spec-core --all` を使えることを利用者向けに伝達した。`spec-anchor-setup-project` の自動実行は無かった。
- Codex skill: exit code 0。trace 上 `spec-anchor core` を引数なしで実行し、Claude command と同じ degraded 情報と復旧手順を利用者向けに伝達した。`spec-anchor-setup-project` の自動実行は無かった。
- 判定: `passed_claude_degraded_agent_layer=true`、`passed_codex_degraded_agent_layer=true`、`passed_all=true`。§11.2 の Section Metadata degraded `/spec-core` 利用者向け伝達行は進捗コピーを `✅` にした。

### E24 Agent CLI Source Retrieval Index verify 失敗伝達 E2E

`20260523-123504-codex-e2e-agent-verify-index` で、§11.2 の Qdrant section collection verify 失敗の利用者向け `/spec-core` 伝達を Claude command と Codex skill の両方で確認した。証跡集約は `artifacts/agent-verify-index-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-123504-codex-e2e-agent-verify-index.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_123504_agent_verify_index` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: `spec-anchor core --rebuild` で正常な Source Retrieval Index を作成した後、実 Qdrant collection から point id `580bc617-c459-5ca2-aefd-40935acf12da` (`docs/spec/audit.md#0003-logout-audit`) を削除し、verify 不整合状態を作った。Agent には「利用者が `/spec-core --verify-index` を発火した」状況として、現在の project root だけで `spec-anchor core --verify-index` を実行するよう指示した。
- Claude command: exit code 0。trace 上 `spec-anchor core --verify-index` を実行し、`status=failed`、Source Retrieval Index verify 不整合、`spec-anchor core --rebuild` で section collection を作り直す手順、verify 失敗では前回 collection が drop されていないことを利用者向けに伝達した。`spec-anchor-setup-project` の自動実行は無かった。
- Codex skill: exit code 0。trace 上 `spec-anchor core --verify-index` を実行し、Claude command と同じ失敗情報と復旧手順を利用者向けに伝達した。`spec-anchor-setup-project` の自動実行は無かった。
- 判定: `passed_claude_verify_agent_layer=true`、`passed_codex_verify_agent_layer=true`、`passed_all=true`。§11.2 の Qdrant section collection upsert / verify 失敗伝達行は進捗コピーを `✅` にした。

### E25 Related Sections backend 失敗時の保持・下流停止 E2E

`20260523-124022-codex-e2e-related-failure-retention` で、Related Sections 用 retrieval backend 初期化失敗時の保持と下流停止を確認した。証跡集約は `artifacts/related-failure-retention-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-124022-codex-e2e-related-failure-retention.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_124022_related_failure` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: run 固有の外部 provider command で Related Sections を deterministic に生成し、初回 `spec-anchor core --rebuild` で `related_sections_status="success"` と非空の関連先を作った。その後 `[vector_store].url` を `http://127.0.0.1:65531` に変更し、Qdrant backend 失敗を起こした。
- 実測: 壊した設定での `spec-anchor core --all` は exit code 1、`status="failed"`、`related_sections_status="failed"`、`freshness_report.status="failed"`、`failed_required_artifact`、Related Sections backend failure の warning を返した。既存 collection の payload 内 `related_sections` は失敗前と同じ値で残った。
- 下流: 失敗後の `spec-anchor inject-search "login boundary"` と `spec-anchor realign --answer-file answer.json` はどちらも `status="blocked"` / `status="failed"` 相当で停止し、`failed_required_artifact` と `spec-anchor core --rebuild` 実行手順を返した。
- 判定: `passed_initial=true`、`passed_failure_status=true`、`passed_retention=true`、`passed_downstream_stop=true`、`passed_all=true`。Related Sections backend 失敗時のデータ保持行と下流停止行は進捗コピーを `✅` にした。

### E26 Source Specs 変更 + pending conflict 優先順位 E2E

`20260523-125141-codex-e2e-dirty-pending-priority` で、Source Specs 変更と未解決 Conflict Review Item が同時にある場合の freshness gate 優先順位を確認した。証跡集約は `artifacts/dirty-pending-priority-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-125141-codex-e2e-dirty-pending-priority.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_125141_dirty_pending` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: 初回 `spec-anchor core --rebuild` 後、`conflict_id="codex-e2e-dirty-pending-priority"` の pending Conflict Review Item を `.spec-anchor/context/conflict_review_items.json` に置き、`spec-anchor core` で freshness に反映した。その後 `docs/spec/auth.md` に `Audit Policy` section を追加し、Source Specs dirty 状態を作った。
- dirty + pending: dirty 状態の `spec-anchor inject-search "session policy"` と `spec-anchor realign --answer-file answer.json` はどちらも exit code 0、`status="blocked"`、`blocking_reasons=["dirty_or_stale_source","pending_conflict"]`、`recommended_next_action` は先に `/spec-core` を実行する指示だった。pending item 詳細はこの段階では返さず、更新経路が優先された。
- `/spec-core` 後: `spec-anchor core` は exit code 0 で保持物を更新し、`freshness_report.blocking_reasons=["pending_conflict"]` と `pending_conflict_count=1` を残した。続く `inject-search` / `realign` は pending conflict のみで停止し、`pending_conflict_items` に `codex-e2e-dirty-pending-priority` を返した。
- 判定: `pending_conflict_loaded=true`、`dirty_priority_inject=true`、`dirty_priority_realign=true`、`core_update_keeps_pending=true`、`after_core_inject_pending_only=true`、`after_core_realign_pending_only=true`、`passed_all=true`。§3.3 の dirty + pending conflict 優先順位行は進捗コピーを `✅` にした。

### E27 inject-* 内部 gate 停止 E2E

`20260523-130037-codex-e2e-inject-all-gates` で、各 `inject-*` command が個別処理の前に内部 freshness gate を通すことを確認した。証跡集約は `artifacts/inject-all-gates-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-130037-codex-e2e-inject-all-gates.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_130037_inject_gates` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: 初回 `spec-anchor core --rebuild` で `freshness_report.status="fresh"` の状態を作った後、`docs/spec/auth.md` に `Dirty Gate Addition` section を追加して dirty 状態を作った。
- 実測: `spec-anchor inject-search`、`inject-section`、`inject-chapters`、`inject-purpose`、`inject-conflicts` はすべて exit code 0、`status="blocked"`、`should_stop=true`、`blocking_reasons=["dirty_or_stale_source"]`、`recommended_next_action="run /spec-core before /spec-inject"` を返した。
- 個別処理の未実行確認: blocked 出力には `hits` / `sections` / `chapter_anchors_path` / `purpose` / `resolved_conflict_review_items` など各 command の成功時固有 field が無く、検索・payload lookup・artifact 返却・Conflict Review Item 抽出へ進んでいないことを外部出力で確認した。
- 判定: 5 command すべて `passed=true`、`passed_all=true`。§8.4 の `inject-*` 内部 gate 行は進捗コピーを `✅` にした。

### E28 CoreResult stdout JSON field 確認

既存の `20260523-130037-codex-e2e-inject-all-gates` と `20260523-125141-codex-e2e-dirty-pending-priority` の `/spec-core` stdout JSON で、§7.4 の CoreResult field 一覧の存在を確認した。

- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-130037-codex-e2e-inject-all-gates/stdout/initial-core-rebuild.stdout`、`doc/e2eテストCODEX実施用/evidence/20260523-125141-codex-e2e-dirty-pending-priority/stdout/core-after-dirty.stdout`。
- 確認 field: `status`、`mode`、`updated_sources`、`skipped_sources`、`failed_sources`、`failed_sections`、`updated_sections`、`regenerated_chapter_anchors`、`retrieval_index_status`、`related_sections_status`、`potential_conflicts`、`conflict_review_items`、`pending_conflict_count`、`unreflected_conflict_resolutions`、`stale_resolution_count`、`freshness_report`、`warnings`。
- 判定: 上記 17 field は stdout JSON に存在し、`initial-core-rebuild` では `status="updated"` / `mode="full"`、`core-after-dirty` では `status="updated"` / `mode="incremental"` として外部出力で確認できた。§7.4 の CoreResult field 一覧は進捗コピーを `✅` にした。

### E29 Conflict Review 生成 E2E

`20260523-131632-codex-e2e-conflict-review-generation` で、Related Sections の `possible_conflict` referral、Conflict Review Item 生成、warning 化、high-risk pair の conflict_review stage 送信を確認した。証跡集約は `artifacts/conflict-review-generation-assertions.json` に保存した。

- 隔離: `pending` / `warning` / `highrisk` の 3 project を `/tmp/20260523-131632-codex-e2e-conflict-review-generation.projects/` 配下に作成し、各 project は run 固有 Qdrant collection と run 固有 provider command を使った。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- pending: Related Sections provider が `possible_conflict=true` を返し、Conflict Review provider が `outcome="needs_human_review"` を返す条件で、`spec-anchor core --rebuild` は exit code 0、`pending_conflict_count >= 1`、`freshness_report.status="blocked"`、`blocking_reasons=["pending_conflict"]`、`conflict_review_items[].status="pending"` を返した。
- warning: Conflict Review provider が `outcome="not_conflict"` を返す条件で、`conflict_review_items=[]`、`pending_conflict_count=0`、`potential_conflicts[]` に warning が残った。LLM 判定で `resolved` item を自動作成しないことも確認した。
- high-risk: Related Sections selection が空でも、同一 identifier と `must` / `must not` 等の衝突しやすい語を共有する pair が `conflict_route="pattern_signal_legacy"` として conflict_review stage に送られた。provider invocation log で `related_section_selection` 後に `conflict_review` が呼ばれ、全 Section pair の総当たりではなく候補 pair に限定されていたことを確認した。
- item shape: pending item には `conflict_id`、`status`、`severity`、`source_refs`、`claims`、`why_conflicting`、`why_llm_cannot_decide`、`related_sections`、`decision_options`、`recommended_next_action`、`base_source_hashes`、`valid_scope` が含まれた。
- 判定: `possible_conflict_referred_to_conflict_review=true`、`pending_conflict_created_and_blocks=true`、`no_auto_resolved_item=true`、`warning_potential_conflict_when_judge_resolves=true`、`stage_order_related_before_conflict=true`、`highrisk_unselected_candidate_sent_to_conflict_review=true`、`passed_all=true`。Conflict Review 生成関連の 18 行は進捗コピーを `✅` にした。

### E30 decision payload field 確認

既存の `20260523-021012-codex-e2e-remaining4` で、`spec-anchor core --decision-json` / `--decision-file` に渡す decision payload の field を確認した。

- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-021012-codex-e2e-remaining4/commands.log`、`artifacts/decision-prefer_a.json`、`artifacts/decision-prefer_b.json`、`artifacts/decision-conditional.json`、`artifacts/decision-dismiss.json`、`artifacts/decision-needs_source_update.json`、`artifacts/decision-defer.json`、`artifacts/decision-task_scope_resolution.json`。
- 確認 field: `conflict_id`、`decision`、`reason`、`selected_option`、`valid_scope`、`referenced_source_refs[]`。
- 判定: 上記 field は command log と decision JSON artifacts の両方で確認でき、各 decision の stdout でも `resolution` または `last_decision` に反映されていた。decision payload field の可視化用チェックは進捗コピーを `✅` にした。

### E31 `/spec-core` step trace 可視化チェック

既存の `/spec-core` 実行証跡で、§7.3 の step 可視化用チェックを確認した。

- 証跡: `doc/e2eテストCODEX実施用/evidence/20260522-214139-codex-e2e/stdout/e2-core-all-real.stdout`、`stdout/e2-core-incremental-real.stdout`、`stdout/e2-core-rebuild-real.stdout`、および `doc/e2eテストCODEX実施用/evidence/20260523-131632-codex-e2e-conflict-review-generation/artifacts/pending-core-progress.json`。
- `/spec-core`: `core_progress.json` の `stages` で `inputs_loaded`、`sections_loaded`、`section_metadata`、`section_collection_upsert`、`related_sections`、`conflict_evaluation`、`chapter_anchors`、`artifact_write` が確認でき、stdout CoreResult も出力された。
- `/spec-core --all`: `20260522-214139-codex-e2e` の `e2-core-all-real` で exit code 0、全 Section 再評価と CoreResult 出力を確認した。
- `/spec-core --rebuild`: `20260522-214139-codex-e2e` の `e2-core-rebuild-real` と後続の run 固有 Qdrant collection E2E で、`--all` 相当の再評価と Qdrant collection full recreate / full upsert を確認した。
- 判定: §7.3 の step 可視化用チェックは進捗コピーを `✅` にした。

### E32 watcher 実行中 `/spec-core` blocked E2E

`20260523-134200-codex-e2e-core-blocked-watcher` で、watcher 実行中に手動 `/spec-core` が上流理由で停止し、retrieval index 経路に到達しない場合の stdout JSON を確認した。証跡集約は `artifacts/core-blocked-watcher-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-134200-codex-e2e-core-blocked-watcher.project` に作成した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: `.spec-anchor/state/watch_state.json` に `running=true` / `is_running=true` / `owner="watcher"` の active watcher state を置き、`.spec-anchor/state/core_update.lock.json` に watcher owner の lock を置いた。
- 実測: `spec-anchor core` は exit code 0、stdout JSON `status="blocked"`、`blocked=true`、`retrieval_index_status="blocked"`、`related_sections_status="blocked"`、`freshness_report.status="blocked"`、`blocking_reasons=["watcher_running"]` を返した。`updated_sources` / `updated_sections` / `regenerated_chapter_anchors` は空で、下流更新へ進んでいないことを確認した。
- 判定: §7.4 の `retrieval_index_status="blocked"` 行は進捗コピーを `✅` にした。

### E33 `conflict_pair_max_per_section` diagnostics E2E

`20260523-134620-codex-e2e-conflict-pair-cap-diagnostics` で、同一 source に多数の high-risk conflict candidate がある場合、`conflict_pair_max_per_section` の上限で Conflict Review へ送る pair を絞り、送らなかった pair を CoreResult diagnostics に残すことを確認した。証跡集約は `artifacts/conflict-pair-cap-diagnostics-assertions.json` に保存した。

- 初回実測: `[limits].conflict_pair_max_per_section = 1` でも、同一 source `docs/spec/conflict-cap.md#0002-alpha-base` から 4 pair が Conflict Review provider に送られ、CoreResult diagnostics に skip 理由が出なかった。これは製品側 discrepancy `CODEX-E2E-F007` として扱った。
- 対応: `spec_anchor/core.py` から `evaluate_conflicts` へ config を渡し、`spec_anchor/conflict_review.py` が Mapping 形式の `[limits]` から `conflict_pair_max_per_section` を読むよう修正した。あわせて上限で送らなかった high-risk candidate pair を `selection_diagnostics` に記録し、CoreResult の `diagnostics.conflict_review.diagnostics[]` へ出すようにした。
- 再テスト実測: `spec-anchor core --rebuild` は exit code 0、Conflict Review provider 呼び出しは 1 pair に絞られ、CoreResult `diagnostics.conflict_review.diagnostics[]` に `reason_code="conflict_pair_max_per_section_skipped"`、`conflict_pair_max_per_section=1`、`skipped_pair_count`、`skipped_pairs_sample[]` が出た。
- unit 再テスト: `.venv/bin/python -m pytest -q tests/test_conflict_review.py::test_t_u20_conflict_pair_limit_counts_only_high_risk_candidate_additions tests/test_conflict_review.py::test_t_u20_conflict_pair_limit_reads_mapping_config tests/test_spec_core_acceptance.py::test_conflict_pair_cap_recorded_in_diagnostics` は 3 passed。
- 判定: §7.4 の `conflict_pair_max_per_section` diagnostics 行は進捗コピーを `✅` にした。

### E34 watcher 内部 core 更新 E2E

`20260523-135200-codex-e2e-watch-internal-no-agent-cli` で、`codex` / `claude` が PATH 上に無い状態でも `spec-anchor-watch --once` が watcher process 内部の core runner で incremental update を実行することを確認した。証跡集約は `artifacts/watch-internal-no-agent-cli-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-135200-codex-e2e-watch-internal-no-agent-cli.project` に作成し、Qdrant collection は `spec_anchor_sections_20260523_135200_watch_internal` に固定した。`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` は unset のまま実行した。
- 入力: PATH を `repo/.venv/bin:/usr/bin:/bin` に制限し、`command -v codex` / `command -v claude` が空であることを `artifacts/environment.txt` に保存した。LLM provider は project local script に stage routing し、Agent CLI を使わない条件にした。
- 実測: 初回 `spec-anchor core --rebuild` 後に Source Specs へ `Watch Added Policy` を追加し、`spec-anchor-watch --once` を実行した。stdout JSON は exit code 0、`ran_core=true`、`last_lock.owner="watcher"`、`core_result.status="updated"`、`updated_sections[]` に `docs/spec/watch.md#0003-watch-added-policy` を含んだ。
- 判定: watcher が `/spec-core` slash command 外部実行や Agent CLI に依存せず、watcher process 内部の background execution として core 相当更新を実行する行は進捗コピーを `✅` にした。

### E35 Purpose / Core Concept ownership と path ③ trace 確認

既存の `20260523-101202-codex-e2e-inject-output` と Purpose / Core Concept read-only E2E 証跡で、Purpose / Core Concept の人間所有と `/spec-inject` path ③ trace を確認した。

- ownership: `20260523-022041-codex-e2e-resolution-readonly`、`20260523-110135-codex-e2e-parallel-safe`、`20260523-125141-codex-e2e-dirty-pending-priority` で、`/spec-core` / conflict resolution / Source Specs 更新後も Purpose / Core Concept が自動更新されないことを確認済み。§4 の Purpose / Core Concept ownership 行は進捗コピーを `✅` にした。
- path ③ trace: `doc/e2eテストCODEX実施用/evidence/20260523-101202-codex-e2e-inject-output/stdout/codex-skill-inject-8-5.stdout.jsonl` に、Codex skill が `spec-anchor inject-purpose` を実行し、その後 `sed -n '1,200p' docs/core/concept.md` で Core Concept を Read した command trace が残っている。
- path ③ output: `artifacts/codex-skill-inject-8-5.last-message.txt` には、最終 constraints の 1 item として `evidence_origin: Core Concept`、`evidence_ref: docs/core/concept.md` が出ている。
- 判定: §8.3 path ③ の個別 step と trace 監査は進捗コピーを `✅` にした。path ④ はこの時点では未完了だったが、後続の E37 で確認した。

### E36 Core Concept 乖離通知なし E2E

`20260523-141500-codex-e2e-no-core-concept-drift-notice` で、Source Specs 進化後に `/spec-core` を再実行しても、Core Concept 陳腐化を自動検出・通知する専用 reason / diagnostics が出ないことを確認した。

- 入力: `/tmp/20260523-141500-codex-e2e-no-core-concept-drift-notice.project` に Source Specs / Purpose / Core Concept を配置し、初回 `spec-anchor core --rebuild` 後、Source Specs に `docs/spec/policy.md#0003-source-specs-evolved` を追加した。
- 実測: 追加後の `spec-anchor core` は exit code 0、`status="updated"`、`updated_sections` に追加 Section を含んだ。`freshness.status="fresh"`、`blocking_reasons=[]`。
- 判定: core stdout、`.spec-anchor/state/freshness.json`、`.spec-anchor/state/section_manifest.json` に `core_concept_drift` / `concept_drift` / `concept_stale` 相当の専用 marker が出ないことを確認した。§4 の Core Concept 乖離通知なし行は進捗コピーを `✅` にした。
- 証跡: `artifacts/no-core-concept-drift-notice-assertions.json`。

### E37 path ④ Conflict Review Item 採用 trace

`20260523-142000-codex-e2e-conflict-review-item-trace` で、実 Codex CLI が `spec-anchor inject-conflicts` を呼び、返却された resolved かつ stale でない Conflict Review Item だけを `evidence_origin="Conflict Review Item"` として制約に採用することを確認した。

- 入力: `.spec-anchor/context/conflict_review_items.json` に `conflict-payment-timeout-human-resolution` (resolved / `stale_resolution=false` / `valid_scope=global`) と、除外用の stale resolved item を配置した。`.spec-anchor/state/freshness.json` は `status="fresh"` とした。
- preflight: `spec-anchor inject-conflicts` は exit code 0、`resolved_conflict_review_items[]` に `conflict-payment-timeout-human-resolution` だけを返し、stale item は返さなかった。
- Agent trace: `codex exec --json` の JSONL trace に `spec-anchor inject-conflicts` の command execution が残った。最終出力は `evidence_origin: Conflict Review Item`、`evidence_ref: conflict-payment-timeout-human-resolution`、`support_refs` に `docs/spec/payment.md#0002-default-timeout` / `docs/spec/payment.md#0003-retry-policy` を含んだ。
- 判定: §8.3 path ④ の個別 step と trace 監査は進捗コピーを `✅` にした。
- 証跡: `artifacts/conflict-review-item-trace-assertions.json`、`stdout/codex-conflict-trace.stdout.jsonl`、`artifacts/codex-conflict-trace.last-message.txt`。

### E38 `/spec-inject` raw context 境界 trace 監査

`20260523-142500-codex-trace-raw-context-boundary` で、既存 `20260523-101202-codex-e2e-inject-output` の Codex skill trace を機械監査し、Source Specs / Core Concept / Chapter Key Anchor を無条件に丸ごと投入していないことを確認した。

- 入力 trace: `20260523-101202-codex-e2e-inject-output/stdout/codex-skill-inject-8-5.stdout.jsonl`。
- 実測: Agent は `spec-anchor inject-search` と `spec-anchor inject-section` の後に、選択した `docs/spec/login.md` / `docs/spec/audit.md` だけを `sed -n` で読んだ。`spec-anchor inject-purpose` の後に `docs/core/concept.md` を読んだ。`chapter_anchors.json` 本文の read は無かった。
- 判定: `cat docs/spec`、`cat docs/core/concept.md`、`cat .spec-anchor/context/chapter_anchors.json`、`xargs cat` 等の広い raw text dump command は観測されなかった。§3.4 の raw context 境界行は進捗コピーを `✅` にした。
- 証跡: `artifacts/raw-context-boundary-assertions.json`。

### E39 path 選択指針 trace

`20260523-143000-codex-e2e-path-selection-trace` で、§8.3.1 の 4 課題タイプごとに Codex CLI を実行し、Agent が主 path / 補強 path を選ぶことを command trace で確認した。

- `具体的 API / 識別子`: `spec-anchor inject-search` + `inject-section` を実行し、補強として `inject-purpose` / `inject-conflicts` を実行した。
- `全体方針 / 抽象的`: `spec-anchor inject-chapters` を実行し、補強として `inject-search` / `inject-section` / `inject-purpose` / `inject-conflicts` を実行した。
- `Purpose / Core Concept 直接質問`: `spec-anchor inject-purpose` を実行し、補強として `inject-search` / `inject-section` / `inject-chapters` を実行した。
- `過去判断の継続`: `spec-anchor inject-conflicts` を実行し、補強として `inject-search` / `inject-section` / `inject-purpose` を実行した。
- 判定: 4 ケースとも `codex exec --json` exit code 0、最終出力は §8.5 の 5 セクションを含んだ。§8.3.1 path 選択指針 4 行は進捗コピーを `✅` にした。
- 証跡: `artifacts/path-selection-trace-assertions.json`、`stdout/*.stdout.jsonl`、`artifacts/*.last-message.txt`。

### E40 残件 23 行の処理

`20260523-144000-codex-e2e-remaining-23` で、前回残っていた 23 行を処理した。証跡集約は `artifacts/remaining-23-assertions.json` に保存した。

- 隔離: project は `/tmp/20260523-144000-codex-e2e-remaining-23/` 配下に作成した。production E2E / Agent trace の根拠にする core / inject / realign 経路では `SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` を unset し、実 Qdrant と実 FlagEmbedding BGE-M3 を使った。
- 別 Codex 指摘の 11 件: graph 系 artifact / graph traversal CLI が出ないこと、Purpose / Core Concept が自動更新されないこと、`/spec-core` の実行モード分岐が無いこと、pending Conflict Review Item が `/spec-inject` / `/spec-realign` を warning-only で進ませないことを確認した。さらに Qdrant collection が dense + sparse vector を持ち、`inject-search` が検索結果を返し、`inject-section` が `related_sections` payload を返すことを確認した。
- Section Search Keys / Section Identifiers: provider が `AUTH_TOKEN`、`bindContext`、`--rebuild`、`.spec-anchor/config.toml`、`ProductStore`、`productStoreGroup.replace` を Search Keys 候補として返しても、Qdrant payload の `search_keys` からは除外され、`identifiers` に機械抽出されることを確認した。`summary_search_keys_are_evidence=false` と既存 Agent trace の `evidence_origin` 監査により、Search Keys / Identifiers を制約根拠にしないことも確認した。
- step 可視化用 8 行: 既存の `20260523-143000-codex-e2e-path-selection-trace` と `20260523-142500-codex-trace-raw-context-boundary` を監査し、path ①の `inject-search`、`inject-section`、Source Specs read と、path ②の `inject-chapters`、章配下 Section への Agentic Search が観測されることを確認した。
- smoke / fake 4 件: `spec-anchor-setup-system --check-only --run-smoke`、`SPEC_ANCHOR_FAKE_LLM=1`、`SPEC_ANCHOR_FAKE_RETRIEVAL=1` を別枠確認した。これらは production E2E 完了扱いしない。進捗コピーではユーザー判断により `✅` にした。
- 判定: `production_or_agent_trace_checks_passed=true`、`smoke_fake_separate_checks_passed=true`、`all_processed=true`。別 Codex 指摘の 11 行、step 可視化用 8 行、ユーザー判断済み smoke / fake 別枠 4 行は進捗コピーを `✅` にした。

### E41 P3b / P7 残テスト

`2026-05-23-P3b` と `2026-05-23-P7` で、`doc/e2eテスト/test_plan.ja.md` に残っていた scenario checklist を実行した。

- P3b: `/spec-core` の incremental、`--all`、`--rebuild`、idempotency、Qdrant 不到達の 5 scenario を実行した。`evidence_map.jsonl` には 5 件すべて `verification_level="real_smoke_verified"` / `result="passed"` として記録した。fake env は unset し、実 Codex / Claude stage routing、実 Qdrant 1.17.1、実 FlagEmbedding BGE-M3 を使った。
- P7: P3b 生成 artifact を入力に、`inject-section`、`inject-chapters`、`inject-purpose`、`realign`、chain consistency、config 不在 failure の 6 scenario を実行した。`evidence_map.jsonl` には 6 件すべて `verification_level="production_e2e_verified"` / `result="passed"` として記録した。
- P7 の chain consistency では、`.spec-anchor/context/chapter_anchors.json`、`.spec-anchor/context/conflict_review_items.json`、`.spec-anchor/state/retrieval_index_state.json`、`.spec-anchor/state/related_sections_state.json` の hash が inject / realign 経路で変わらないことを確認した。
- P3b 実行中に `chapter_key_anchor` stage の provider routing は Claude になっているのに model が先頭 provider の `gpt-5.4-mini` になる製品側 bug を検出し、`spec_anchor/core.py` を修正した。回帰 test `tests/test_spec_core.py::test_g11_chapter_key_anchor_uses_stage_routed_model` は passed。
- 証跡: `doc/e2eテスト/evidence/2026-05-23-P3b/evidence_map.jsonl`、`doc/e2eテスト/evidence/2026-05-23-P7/evidence_map.jsonl`、`doc/e2eテスト/evidence/2026-05-23-P3b/artifacts/assertions.json`、`doc/e2eテスト/evidence/2026-05-23-P3b/artifacts/assertions-reviewed.json`、`doc/e2eテスト/evidence/2026-05-23-P7/artifacts/assertions.json`。

## 6. skipped / 未実行

- Codex 実施用進捗コピーで、legend / 運用説明を除く未チェック行はない。
- `doc/e2eテスト/test_plan.ja.md` の P3b 5 scenario と P7 6 scenario はすべて実行済みである。
- smoke / fake contract 4 件は別枠として実行済みであり、ユーザー判断により進捗コピーでは `✅` にした。ただし production E2E 完了根拠ではない。
- pytest auto-collector 形式の `production_e2e_verified` evidence map への移植は未実施である。今回の P3b / P7 は手動 scenario evidence map として command、exit code、stdout、stderr、生成物を保存した。
- 正本 `doc/EXTERNAL_DESIGN.ja.md` への `✅` 昇格は未実施である。Codex 進捗コピーの結果と Claude 側証跡を照合してから反映する前提である。

## 7. 残った問題

この節は、テスト側の修正では解消していない製品仕様または実装の問題だけを記録する。

`CODEX-E2E-F001` / `CODEX-E2E-F002` / `CODEX-E2E-F003` / `CODEX-E2E-F004` / `CODEX-E2E-F005` / `CODEX-E2E-F006` / `CODEX-E2E-F007` / `CODEX-E2E-F008` は修正後再テスト済みである。現時点で残す未解決の製品側 discrepancy はない。

## 8. 製品側の修正済み問題

### CODEX-E2E-F008: `chapter_key_anchor` stage routing の model が provider と一致しない

- 判定: Codex 修正後に再テスト済み。解消済み。
- 期待: `[llm.stage_routing].chapter_key_anchor` で provider / model を指定した場合、Chapter Key Anchor stage はその provider と model を同時に使う。
- 初回実測: P3b 初回では `chapter_key_anchor` provider は Claude に routing されていたが、実行 command の model は先頭 provider の `gpt-5.4-mini` になり、`claude --model gpt-5.4-mini` が実行された。
- 原因: `_chapter_anchors(...)` 呼び出しに stage routing 後の `chapter_anchor_llm_config` ではなく、全体 config を渡していた。
- 対応: `spec_anchor/core.py` で `_chapter_anchors(...)` へ `chapter_anchor_llm_config` を渡すよう修正した。
- 再テスト実測: P3b 再実行で `chapter_anchors` stage は provider `claude`、model `claude-sonnet-4-6` を使い、P3b 5 scenario がすべて通過した。
- unit 証跡: `.venv/bin/python -m pytest -q tests/test_spec_core.py::test_g11_chapter_key_anchor_uses_stage_routed_model` は 1 passed。
- E2E 証跡: `doc/e2eテスト/evidence/2026-05-23-P3b/artifacts/assertions.json`、`doc/e2eテスト/evidence/2026-05-23-P3b/artifacts/assertions-reviewed.json`。

### CODEX-E2E-F007: `conflict_pair_max_per_section` 上限と diagnostics が設計契約と一致しない

- 判定: Codex 修正後に再テスト済み。解消済み。
- 期待: §7.4 は、Related Sections に選ばれなかった高リスク pair を `conflict_pair_max_per_section` の範囲で Conflict Review stage へ送り、上限により送らなかった pair は CoreResult diagnostics に残すとしている。
- 初回実測: `20260523-134620-codex-e2e-conflict-pair-cap-diagnostics` の初回では、`[limits].conflict_pair_max_per_section = 1` に対し、同一 source から 4 pair が Conflict Review provider に送られた。CoreResult diagnostics に `conflict_pair_max_per_section` による skip 情報も無かった。
- 原因: `/spec-core` から `evaluate_conflicts` へ config を渡しておらず、pair 選定は既定値 8 で動いていた。また `select_conflict_judging_pairs` は上限で落とした pair の diagnostics を返していなかった。
- 対応: `spec_anchor/core.py` で `evaluate_conflicts(config=config)` を渡すよう修正した。`spec_anchor/conflict_review.py` では Mapping 形式の config / limits を読めるようにし、上限により送らなかった pair を `selection_diagnostics` として返すようにした。CoreResult には `diagnostics.conflict_review.diagnostics[]` として出す。
- 再テスト実測: 修正後 E2E では Conflict Review provider 呼び出しが 1 pair になり、`diagnostics.conflict_review.diagnostics[]` に `reason_code="conflict_pair_max_per_section_skipped"`、上限値、skip 件数、sample が出た。
- 再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-134620-codex-e2e-conflict-pair-cap-diagnostics/artifacts/conflict-pair-cap-diagnostics-assertions.json`。
- unit 証跡: `.venv/bin/python -m pytest -q tests/test_conflict_review.py::test_t_u20_conflict_pair_limit_counts_only_high_risk_candidate_additions tests/test_conflict_review.py::test_t_u20_conflict_pair_limit_reads_mapping_config tests/test_spec_core_acceptance.py::test_conflict_pair_cap_recorded_in_diagnostics`。

### CODEX-E2E-F006: Section Metadata degraded の外部出力が設計契約と一致しない

- 判定: SONNET 修正後に Codex 再テスト済み。解消済み。
- 期待: §11.1.5 は、Section Metadata の LLM 生成が一部 section で失敗し必須 artifact 自体は揃う場合、`spec-anchor core` が exit code 0、stdout JSON `status="degraded"`、`freshness_report.status="degraded"`、`blocking_reasons=["degraded_optional_artifact"]`、`failed_sections`、`diagnostics.section_metadata_generation.failed_sections`、`warnings` を返すとしている。§3.3 は、一部保持物が欠けているが必須分は使える場合、warning を表示して `/spec-inject` / `/spec-realign` が続行できるとしている。
- 初回実測: `spec-anchor core --rebuild` は exit code 0 で、`freshness_report.status="degraded"` と `failed_sections` は返したが、top-level `status` は `"updated"` だった。続く `spec-anchor inject-search "login audit"` は検索結果を返して継続したが、stdout の `warnings` は空で `degraded_optional_artifact` を利用者に表示しなかった。
- 初回証跡: `doc/e2eテストCODEX実施用/evidence/20260523-112043-codex-e2e-degraded-section-metadata/stdout/core-rebuild.stdout`、`stdout/inject-search.stdout`、`artifacts/degraded-section-metadata-assertions.json`。
- 修正後実測: `spec-anchor core --rebuild` は top-level `status="degraded"` を返した。`spec-anchor inject-search "login audit"` は `warnings` に `degraded_optional_artifact` を含めて `hits` を返した。`spec-anchor realign --answer-json ...` は `status="degraded"`、`should_stop=false`、`can_continue=true`、`blocking_reasons=["degraded_optional_artifact"]`、`warnings`、`answer` を返した。
- 再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-121607-codex-e2e-f006-retest/stdout/core-rebuild.stdout`、`stdout/inject-search.stdout`、`stdout/realign.stdout`、`artifacts/degraded-section-metadata-assertions.json`。

### CODEX-E2E-F001: dirty Source Specs の freshness gate が停止しない

- 判定: Claude 修正後に Codex 再テスト済み。解消済み。
- 期待: Source Specs 変更後、`/spec-core` または watcher 更新前の `/spec-inject` は dirty / stale 理由で停止する。
- 初回実測: `spec-anchor inject-search password reset` は exit code 0 で検索結果を返した。
- 初回証跡: `doc/e2eテストCODEX実施用/evidence/20260522-214139-codex-e2e/stdout/e3-inject-search-dirty.stdout`。
- 再テスト実測: clean project で `inject-search` / `realign` が `status="blocked"`、`blocking_reasons=["dirty_or_stale_source"]` で停止した。
- 再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-001153-codex-e2e-f001-retest/stdout/f001-clean-assert.stdout`。

### CODEX-E2E-F002: Claude `/spec-realign` が active project root ではなく別プロジェクトを探索した

- 判定: Claude 修正後に Codex 再テスト済み。解消済み。
- 初回期待: `cwd` に `.spec-anchor/config.toml` がある状態で `/spec-realign <task>` を発火した場合、Agent はその project root の `spec-anchor inject-*` / `realign` を実行する。
- 初回実測: Claude Code の init `cwd` は `/tmp/spec-anchor-codex-e2e-slash-skill.OqGMYD` だったが、subagent / tool call が `/home/kazuki/public_html/ec-spoke.local` と `/home/kazuki/public_html/llm-helper` を探索し、最終的に `.spec-anchor/config.toml not found under /home/kazuki/public_html/ec-spoke.local` を報告した。
- 初回証跡: `doc/e2eテストCODEX実施用/evidence/20260523-002300-codex-e2e-slash-skill/stdout/claude-slash-spec-realign-clean-tmp.stdout`。
- 再テスト実測: 修正後 template / 配付済み command を新規 clean project に配置し、Claude Code `/spec-realign` を実行した。init `cwd` と tool call は `/tmp/spec-anchor-codex-e2e-f002-retest.N4Lyjy` に閉じ、別 project 探索は再現しなかった。`spec-anchor realign` は `status="fresh"`、`should_stop=false` の結果を返し、利用者向け 4 区分出力も出た。
- 再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-010512-codex-e2e-f002-retest/artifacts/f002-retest-assertions.json`。

### CODEX-E2E-F003: Agent `/spec-inject` / skill 出力が `採用しなかったもの` セクションを省略する

- 判定: Claude 修正後に Codex 再テスト済み。解消済み。
- 初回期待: §8.5 は、該当 0 件の場合も各セクションを省略せず「該当なし」を明示するとしており、例示構造に `採用しなかったもの` を含む。
- 初回実測: Claude `/spec-inject` と Codex skill の出力は、`今回守る制約` / `今回見るべき対象` / `関連先として確認したもの` / `不確実性 / 人間確認` は出したが、`採用しなかったもの` は 0 件としても出さなかった。
- 初回証跡: `doc/e2eテストCODEX実施用/evidence/20260523-002300-codex-e2e-slash-skill/stdout/claude-slash-spec-inject-clean-tmp.stdout`、`doc/e2eテストCODEX実施用/evidence/20260523-002300-codex-e2e-slash-skill/artifacts/codex-skill-inject-clean-tmp-v2.last-message.txt`。
- 再テスト実測: Claude `/spec-inject` と Codex skill の両方で `採用しなかったもの` セクションが出力され、Codex skill は 0 件項目を `該当なし` として明示した。
- 再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-010512-codex-e2e-f002-retest/artifacts/f003-retest-assertions.json`。

### CODEX-E2E-F004: `.spec-anchor/config.toml` 不在の slash command が CLI を実行せず事前確認で停止する

- 判定: Codex 修正後に再テスト済み。解消済み。
- 期待: §11.2 は、`.spec-anchor/config.toml` 不在でも Agent が `spec-anchor core` / `spec-anchor inject-*` / `spec-anchor realign` を実行し、CLI JSON の `.spec-anchor/config.toml not found under {root}` を利用者に伝達するとしている。
- 初回実測: Claude Code `/spec-core` / `/spec-inject` / `/spec-realign` は、`ls <project>/.spec-anchor/config.toml` で事前確認し、CLI を実行せずに `spec-anchor-setup-project` を提案した。
- 初回証跡: `doc/e2eテストCODEX実施用/evidence/20260523-013834-codex-e2e-remaining/stdout/agent-core-missing-config.stdout`、`stdout/agent-inject-missing-config.stdout`、`stdout/agent-realign-missing-config.stdout`、`artifacts/agent-error-assertions.json`。
- 追加切り分け: template 側は `/spec-core` / `/spec-inject` が通過したが、`/spec-realign` が `spec-anchor realign --answer-json` ではなく inject 系探索から入り未通過だった。配付済み `.claude/commands` は template と同期されていなかった。
- 対応: `spec_anchor/templates/.claude/commands/spec-realign.md` を §11.2 に合わせ、answer candidate がある場合は `spec-anchor realign --answer-json '<json>'` を gate probe として先に実行する手順に変更した。配付済み `.claude/commands/*.md` と `.codex/skills/spec-anchor/SKILL.md` を template と同期した。
- 再テスト実測: `/spec-core` は `spec-anchor core 2>&1`、`/spec-inject` は `spec-anchor inject-search "認証 auth authentication" 2>&1`、`/spec-realign` は `spec-anchor realign --answer-json '<json>' 2>&1` を実行し、3 ケースとも CLI の `.spec-anchor/config.toml not found under <tmp>` と `spec-anchor-setup-project --target <tmp>` を利用者向け出力に含めた。
- 再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-091402-codex-e2e-f004-postfix-retest/artifacts/f004-postfix-retest-assertions.json`。

### CODEX-E2E-F005: `/spec-realign` pending conflict が item 側 `recommended_next_action` を省略する

- 判定: 修正後に Codex 再テスト済み。解消済み。
- 期待: §11.2 は、`/spec-realign` + answer candidate が pending conflict で停止した場合、`pending_conflict_items` の各 item を §2.8 の構造で提示し、item 側の `recommended_next_action` も利用者に伝達するとしている。
- 初回実測: Claude Code は `spec-anchor realign --answer-json ...` を実行し、`conflict_id=conflict-auth-session-e2e`、`severity`、`claims`、`why_conflicting`、`why_llm_cannot_decide`、`decision_options`、`source_refs` と人間判断の必要性を出した。ただし item 側の `recommended_next_action="Ask a human to decide this conflict."` を最終出力に含めず、top-level の `recommended_next_action="resolve pending Conflict Review Items"` だけを提示した。
- 初回証跡: `doc/e2eテストCODEX実施用/evidence/20260523-093953-codex-e2e-agent-blockers-isolated/stdout/postfix-realign-pending-conflict.stdout`、`artifacts/agent-blockers-isolated-assertions.json`。
- 対応: `.claude/commands/spec-realign.md` と `spec_anchor/templates/.claude/commands/spec-realign.md` に、pending conflict では item 側 `recommended_next_action` を top-level だけで置き換えない指示と必須出力フォーマットを追加した。同じ停止・復旧手順は `.codex/skills/spec-anchor/SKILL.md` と `spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md` にも反映した。
- 再テスト実測: Claude Code `/spec-realign` は `spec-anchor realign --answer-json ...` を実行し、Codex CLI skill は `spec-anchor realign --answer-file` を実行した。両方とも `pending_conflict_items` の `conflict_id=conflict-auth-session-e2e` と item 側 `recommended_next_action: Ask a human to decide this conflict.` を最終出力に含め、answer の整形へ進まなかった。
- 再テスト証跡: `doc/e2eテストCODEX実施用/evidence/20260523-095825-codex-e2e-f005-retest/artifacts/f005-retest-assertions.json`。

## 9. テスト実施側の修正済み問題

この節は、初回実行時に失敗したが、原因がテスト実施側にあり、テスト入力または実行 harness を修正して再実行済みのものを記録する。製品側の未解決問題としては扱わない。

### CODEX-E2E-H001: 初回 harness command wrapper の shift 誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: 初回の `e1-*` 証跡で shell wrapper が command を shift してしまい exit code 127 になった。
- 対応: `e1r-*` として修正済み wrapper で再実行し、setup-system / setup-project の実行結果を取得した。
- 証跡: `stdout/e1r-*`、`stderr/e1r-*`、`commands.log`。

### CODEX-E2E-H002: `/spec-realign` answer file の入力 shape 誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: 最初の `e5-answer.json` は設計が期待する 4 区分 label と一致せず `needs_agent_answer` になった。
- 対応: `e5-answer-valid.json` を作成し、`spec-anchor realign --answer-file` で正常経路を再実行した。
- 証跡: `artifacts/e5-answer-valid.json`、`stdout/e5-realign-answer-file-valid.stdout`。

### CODEX-E2E-H003: Qdrant payload assertion の対象 project 選択誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: 最初の `e7-qdrant-payload-assert` は、別テストで同じ Qdrant collection に 5 件目の point が追加された project を対象にしたため、manifest 4 件と Qdrant 5 件が不一致になった。
- 対応: dedicated collection を持つ `qdrant-missing-fallback` project で再実行し、`e7-fallback-qdrant-payload-assert` が passed。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-000315-codex-e2e-additional/stdout/e7-fallback-qdrant-payload-assert.stdout`。

### CODEX-E2E-H004: F001 初回再テストの対象 project 選択誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: 最初の F001 再テストは、直前の `--verify-index` 検証で `failed_required_artifact` が残っていた project をコピーしたため、`dirty_or_stale_source` と `failed_required_artifact` が同時に出た。
- 対応: clean な fresh project をコピーして再実行し、`dirty_or_stale_source` のみで停止することを確認した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-001153-codex-e2e-f001-retest/stdout/f001-clean-assert.stdout`。

### CODEX-E2E-H005: Python package missing negative case の再現方法誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: 初回の package shadowing は `importlib.util.find_spec()` では package が存在すると判定され、FlagEmbedding / qdrant_client missing を再現できなかった。
- 対応: `sitecustomize.py` で `find_spec()` を制御した外部環境を作り、`flagembedding_missing` / `qdrant_client_missing` を確認した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-000315-codex-e2e-additional/stdout/e7-setup-system-python-package-missing-findspec.stdout`。

### CODEX-E2E-H006: Claude stream-json 実行時の `--verbose` 不足

- 判定: 修正済み。製品不具合として扱わない。
- 内容: 初回の Claude `/spec-core` 実行は `--output-format stream-json` に `--verbose` を付けず、Claude CLI が exit code 1 で停止した。
- 対応: `--verbose` を付けて再実行し、slash command 認識と `spec-anchor core` 実行結果を取得した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-002300-codex-e2e-slash-skill/stdout/claude-slash-spec-core.exitcode`、`stdout/claude-slash-spec-core-clean-tmp.stdout`。

### CODEX-E2E-H007: `codex exec` harness の `-a never` 指定誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: 現在の `codex exec` は `-a` / `--ask-for-approval` を受け付けず、初回 Codex skill 実行が exit code 2 で停止した。
- 対応: `--dangerously-bypass-approvals-and-sandbox` と `-s danger-full-access` のみにして再実行し、Codex skill 経由の CLI 実行と利用者向け出力を取得した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-002300-codex-e2e-slash-skill/stderr/codex-skill-inject-clean-tmp.stderr`、`stdout/codex-skill-inject-clean-tmp-v2.stdout.jsonl`。

### CODEX-E2E-H008: watcher queue-only 追加テストの harness 入力誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: 追加切り分けの初回 harness は `python` コマンド名に依存して途中停止した。2 回目は `spec-anchor realign` に存在しない positional task を渡し、CLI usage error で停止した。
- 対応: `.venv/bin/python` を使い、`spec-anchor realign --answer-file answer.json` に修正して同条件を再実行した。
- 証跡: 途中停止の証跡は `doc/e2eテストCODEX実施用/evidence/20260523-014701-codex-e2e-watchqueue-only/`、修正後の通過証跡は `doc/e2eテストCODEX実施用/evidence/20260523-014753-codex-e2e-watchqueue-only/artifacts/queue-only-assertions.json`。

### CODEX-E2E-H009: config / provider negative case の期待ずれ

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-015624-codex-e2e-remaining2` の初回 harness は `[llm.providers]` 0 件を `[llm]` table なしとして作ってしまい、`embedding.provider` / `vector_store.provider` の非標準値を reject 期待にした。
- 対応: `[llm.providers]` 0 件は v2 で再実行して `llm.providers must be a non-empty table` を確認した。非標準 embedding / vector store は `spec-anchor core` が `allow_non_standard_providers=True` で `retrieval_index_status="skipped"` / InMemory 成功に進むため、reject テストとしては不採用にした。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-015624-codex-e2e-remaining2/artifacts/assertions-reviewed.json`。

### CODEX-E2E-H010: Conflict decision 初回 harness の入力誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-020721-codex-e2e-remaining3` では `--decision-file` に project cwd から見えない相対 path を渡し、stale resolution では参照していない Section を変更した。
- 対応: `20260523-021012-codex-e2e-remaining4` で絶対 path の `--decision-file` を使い、stale resolution は参照 Section 本文を変更して再実行した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-021012-codex-e2e-remaining4/artifacts/assertions.json`。

### CODEX-E2E-H011: debug provider env 初回 harness の stage 選択誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION` は Related Sections selection stage の provider invocation を記録するが、初回 harness は Section Metadata / Chapter Anchor 失敗経路だけを刺激していた。
- 対応: `.spec-anchor/state/related_sections_state.json` の section hash / candidate generation 設定指紋を不一致にし、Related Sections selection stage を通る条件で再実行した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-021336-codex-e2e-debug-env2/artifacts/assertions-reviewed.json`。

### CODEX-E2E-H012: debug related prompt harness の未通過

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-022243-codex-e2e-debug-related-prompt` は `SPEC_ANCHOR_DEBUG_RELATED_PROMPT` の追加 JSONL を期待したが、結果は `related_sections_status="skipped_unchanged"` で、prompt を組み立てる経路まで到達しなかった。
- 対応: Related Sections prompt 構築が発生する clean project を使い、未 set / set / path override を再テストした。未設定では default log が出ず、set 時のみ default path または override path に JSONL が追加され、stdout JSON の status shape は変わらないことを確認した。
- 証跡: 初回未通過は `doc/e2eテストCODEX実施用/evidence/20260523-022243-codex-e2e-debug-related-prompt/artifacts/assertions.json`、修正後は `doc/e2eテストCODEX実施用/evidence/20260523-110135-codex-e2e-parallel-safe/artifacts/parallel-safe-assertions.json`。

### CODEX-E2E-H013: `/spec-core` LLM provider 境界の realign answer shape 誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-022644-codex-e2e-llm-boundary` の初回 `realign` 入力は、§9.3 の 4 区分 answer JSON ではなかったため `needs_agent_answer` になった。
- 対応: 4 区分 answer JSON で再実行し、失敗 provider 設定下でも `realign --answer-file` が `status="fresh"` / `should_stop=false` で通ることを確認した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-022644-codex-e2e-llm-boundary/artifacts/assertions-reviewed.json`。

### CODEX-E2E-H014: Agent CLI blocker 初回 run の project root 隔離不足

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-092828-codex-e2e-agent-blockers` は、テスト project を repo 配下に置いたため、一部 Claude tool call が親 repo root `/home/kazuki/public_html/spec-anchor` へ `cd` して実行した。これは slash command の active project root 契約を判定する入力として不適切だった。
- 対応: `20260523-093821-codex-e2e-agent-blockers-tmp` で `/tmp` project を準備し、CLI preflight で blocker 状態を確認したうえで、`20260523-093953-codex-e2e-agent-blockers-isolated` の Claude Code slash command 再テストに切り替えた。
- 証跡: 初回 run は `doc/e2eテストCODEX実施用/evidence/20260523-092828-codex-e2e-agent-blockers/`、preflight は `doc/e2eテストCODEX実施用/evidence/20260523-093821-codex-e2e-agent-blockers-tmp/artifacts/cli-preflight.log`、再テストは `doc/e2eテストCODEX実施用/evidence/20260523-093953-codex-e2e-agent-blockers-isolated/artifacts/agent-blockers-isolated-assertions.json`。

### CODEX-E2E-H015: §8.5 fixture の Qdrant collection 置換条件誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-101202-codex-e2e-inject-output` の初回準備 script は `spec-anchor-setup-project` の既定 collection 名を `spec_anchor_sections` と想定していたが、実際の既定値は `spec_anchor_section` だった。そのため、初回 `/spec-core --rebuild` は run 固有 collection ではなく既定 collection を使った。
- 対応: test harness の置換条件に `spec_anchor_section` を追加し、`.spec-anchor/config.toml` を run 固有 collection `spec_anchor_sections_20260523_101202_inject_output` に修正して `/spec-core --rebuild` を再実行した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-101202-codex-e2e-inject-output/scripts/prepare-project.sh`、`stdout/core-rebuild-unique.stdout`、`artifacts/inject-output-8-5-assertions.json`。

### CODEX-E2E-H016: Claude `/spec-inject` 初回 harness の prompt 引き渡し誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: §8.5 再テストの初回 Claude CLI 呼び出しは `claude -p ... "/spec-inject <prompt>"` で exit code 1 になり、stderr に `Input must be provided either through stdin or as a prompt argument when using --print` が出た。これは slash command / template の挙動ではなく、test harness 側の prompt 引き渡し方法の問題として扱う。
- 対応: 同じ project / 同じ prompt を stdin 経由で `claude -p` に渡し、`claude-spec-inject-8-5-v2` として再実行した。再実行では exit code 0 で §8.5 の 5 セクション出力を確認した。
- 証跡: 初回は `stderr/claude-spec-inject-8-5.stderr`、修正後は `stdout/claude-spec-inject-8-5-v2.stdout`、`artifacts/claude-spec-inject-8-5.final.txt`、`artifacts/inject-output-8-5-assertions.json`。

### CODEX-E2E-H017: Agent CLI core error assertion の文字列検出が広すぎた

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-104149-codex-e2e-agent-core-errors` の初回 assertion は、Codex skill file に含まれる「setup を自動実行しない」という説明文の `spec-anchor-setup-project` 文字列を、自動 setup 実行として誤検出した。
- 対応: assertion を修正し、`command_execution.command` に `spec-anchor-setup-project` が現れた場合だけ自動 setup 実行として扱うようにした。再実行では Chapter Key Anchor 失敗、Qdrant 到達不能ともに通過した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-104149-codex-e2e-agent-core-errors/scripts/assert-agent-core-errors.py`、`artifacts/agent-core-errors-assertions.json`。

### CODEX-E2E-H018: 並列影響なし追加 E2E の setup agent 指定誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-110135-codex-e2e-parallel-safe` の初回 harness は `spec-anchor-setup-project --agent none` を使ったが、setup CLI の有効値は `codex` / `claude` / `both` であり、テスト準備段階で停止した。
- 対応: `--agent both` に修正し、隔離 project へ Claude command と Codex skill の両方を配付した状態で再実行した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-110135-codex-e2e-parallel-safe/scripts/run-parallel-safe.sh`、`artifacts/parallel-safe-assertions.json`。

### CODEX-E2E-H019: stage routing fallback assertion の debug record 解釈誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: provider invocation debug JSONL の `model` field は `null` だったが、実際の resolved command には `--model gpt-5.4-mini` が含まれていた。初回 assertion は `model` field だけを見たため、先頭 provider fallback を未通過と誤判定した。
- 対応: assertion を resolved command の `--model` 引数で判定するよう修正し、`[llm.stage_routing]` 不在時にすべての invocation が先頭 provider `codex --model gpt-5.4-mini` を使うことを確認した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-110135-codex-e2e-parallel-safe/artifacts/stage-fallback-provider-invocations.jsonl`、`artifacts/parallel-safe-assertions.json`。

### CODEX-E2E-H020: raw body 非投入 fixture の検証語が identifier 化しやすかった

- 判定: 修正済み。製品不具合として扱わない。
- 内容: 初回 fixture の raw body marker は `RAW_BODY_SENTINEL_DO_NOT_EMBED_LOGIN_BOUNDARY` という識別子形だったため、LLM が Section Identifiers として採用し、embedding input の「raw body 直接投入」と「metadata 由来 identifier」を切り分けにくかった。
- 対応: raw body marker を `raw-body-sentinel-do-not-embed-login-boundary` に変更し、実 Qdrant payload の embedding input text に exact raw marker が含まれないことを確認した。なお LLM が本文から派生した identifier を metadata に含めること自体は、raw body を embedding input に丸ごと投入しない契約とは別である。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-110135-codex-e2e-parallel-safe/scripts/run-parallel-safe.sh`、`artifacts/parallel-safe-assertions.json`。

### CODEX-E2E-H021: degraded 負例に Chapter Key Anchor 失敗が混入した

- 判定: 修正済み。製品不具合としてはまだ扱わない。
- 内容: `20260523-112043-codex-e2e-degraded-section-metadata` の初回 harness は Section Metadata だけを一部失敗させる意図だったが、Chapter Key Anchor 生成失敗も同時に発生し、`failed_required_artifact` が混入した。これでは degraded optional artifact の単独契約を判定できなかった。
- 対応: run 固有の外部 provider command が Section Metadata / Related Sections / Chapter Key Anchor をすべて deterministic に返すよう stage routing を調整し、Section Metadata の一部失敗だけを残して再実行した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-112043-codex-e2e-degraded-section-metadata/scripts/run-degraded-section-metadata.sh`、`artifacts/degraded-section-metadata-assertions.json`。

### CODEX-E2E-H022: F006 再テスト harness の inject-search 通常出力 shape 解釈誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-121607-codex-e2e-f006-retest` の初回 assertion は、正常継続する `spec-anchor inject-search` に `should_stop=false` / `blocking_reasons=["degraded_optional_artifact"]` / `results` field を要求していた。しかし §11.1.2 の停止 shape ではない通常 `inject-search` は `hits` と `warnings` を返すため、この期待は過剰だった。
- 対応: assertion を `should_stop` は absent または false、検索結果は `hits`、degraded 伝達は `warnings` で判定するよう修正した。あわせて `spec-anchor realign --answer-json ...` の外部実行を harness に追加し、realign 側の `status="degraded"` / `should_stop=false` / `can_continue=true` / `blocking_reasons` / `warnings` / `answer` を確認した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-121607-codex-e2e-f006-retest/scripts/assert-degraded-section-metadata.py`、`scripts/run-degraded-section-metadata.sh`、`artifacts/degraded-section-metadata-assertions.json`。

### CODEX-E2E-H023: Search Keys 上限 assertion が heading 由来 key を除外対象に含めた

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-122638-codex-e2e-search-key-limit` の初回 assertion は、payload の `search_keys[8:]` 全件が embedding input `text` に含まれないことを要求した。しかし payload の `search_keys` には provider 由来の 12 件に加えて heading 由来の `Search Limit Specification` / `Login Limit` も含まれ、heading は別 field として embedding input に入るため、この期待は過剰だった。
- 対応: provider 由来の late Search Keys (`limit search key 09` から `limit search key 12`) だけを上限除外対象として判定するよう assertion を修正した。再実行では Search Keys / Identifiers ともに 9 件目以降が embedding input から除外されることを確認した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-122638-codex-e2e-search-key-limit/scripts/assert-search-key-limit.py`、`artifacts/search-key-limit-assertions.json`。

### CODEX-E2E-H024: Conflict Review 生成 assertion が conflict 件数と evidence_terms の表記を固定しすぎた

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-131632-codex-e2e-conflict-review-generation` の初回 assertion は pending conflict が 1 件だけであることと、high-risk pair の `evidence_terms` に大文字の `FEATURE_GATE` が含まれることを要求した。実際には `Gamma Optional` との high-risk conflict も生成され、`evidence_terms` は正規化された `feature_gate` として返る場合がある。
- 対応: pending conflict は 1 件以上で判定し、`evidence_terms` は小文字正規化して判定するよう assertion を修正した。再判定では `passed_all=true` になった。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-131632-codex-e2e-conflict-review-generation/scripts/assert-conflict-review-generation.py`、`artifacts/conflict-review-generation-assertions.json`。

### CODEX-E2E-H025: 残件 23 行 harness を system Python で起動した

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-144000-codex-e2e-remaining-23` の初回実行は、証跡スクリプトの shebang が `/usr/bin/env python3` だったため system Python で起動し、`qdrant_client` import が見つからず停止した。
- 対応: 証跡スクリプトの shebang を `/home/kazuki/public_html/spec-anchor/.venv/bin/python` に変更し、venv Python で再実行した。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-144000-codex-e2e-remaining-23/scripts/run-remaining-23.py`、最終 `artifacts/remaining-23-assertions.json`。

### CODEX-E2E-H026: 残件 23 行 assertion の CoreResult field 読み取り位置誤り

- 判定: 修正済み。製品不具合として扱わない。
- 内容: `20260523-144000-codex-e2e-remaining-23` の 2 回目実行は、`summary_search_keys_are_evidence` と `identifier_extractor_version` を top-level `generation.section_metadata` 配下にあると誤って読んだため、Search Keys / Identifiers の根拠境界 3 件を fail と判定した。実際の stdout JSON では `diagnostics.section_metadata` 配下に出ていた。
- 対応: assertion を `diagnostics.section_metadata` と再帰検索で読むよう修正し、同じ外部入力で再実行した。再実行では `production_or_agent_trace_checks_passed=true`、`smoke_fake_separate_checks_passed=true`、`all_processed=true` になった。
- 証跡: `doc/e2eテストCODEX実施用/evidence/20260523-144000-codex-e2e-remaining-23/artifacts/remaining-23-assertions.json`。

### CODEX-E2E-H027: P3b 初回 fixture が pending conflict を誘発した

- 判定: 修正済み。製品不具合として扱わない。
- 内容: P3b 初回の Source Specs fixture は、本来の real-smoke 代表経路確認に不要な矛盾表現を含み、`pending_conflict` によって後続 inject / realign の前提 artifact を作りにくい状態になった。
- 対応: fixture 文言を P3b の目的に合わせ、矛盾兆候を意図せず発生させない記述へ修正した。Conflict Review Item の pending 停止契約は別 E2E で既に検証済みであり、P3b では real provider / real Qdrant / BGE-M3 の代表経路確認に絞った。
- 証跡: `doc/e2eテスト/evidence/2026-05-23-P3b/scripts/run-p3b-real-smoke.py`、`doc/e2eテスト/evidence/2026-05-23-P3b/evidence_map.jsonl`。

## 10. 次に実行すべき作業

1. Codex 実施用進捗コピーと `doc/e2eテスト/test_plan.ja.md` の P3b / P7 checklist について、追加で実行すべき残テストはない。
2. Codex 進捗コピーの `✅` を正本 `doc/EXTERNAL_DESIGN.ja.md` へ昇格する場合、Claude 側の結果と証跡を行単位で照合する。
3. pytest auto-collector 形式の evidence map が必要になった場合は、今回の手動 P3b / P7 証跡を `doc/e2eテスト/test_plan.ja.md` の `verification_level` 定義に沿って移植する。
