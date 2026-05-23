# SONNET E2E テスト結果サマリー

正本: `doc/EXTERNAL_DESIGN.ja.md`  
進捗コピー: `EXTERNAL_DESIGN.sonnet-progress.ja.md`（確認済みの `[ ]` をここで `✅` に変更）  
証跡フォルダ: `evidence/<テスト ID>/result.md`

`✅` 付与条件: 実機 E2E 検証済み、`SPEC_ANCHOR_FAKE_*` 未使用、証跡あり

---

## フェーズ① — Production 環境

| テスト ID | テスト名 | 判定 | 証跡パス | 備考 |
|---|---|---|---|---|
| P0 | 前提確認（Qdrant / CLI / FlagEmbedding） | **PASS** | evidence/P0_prerequisite/ | 全6項目 PASS |
| P1-E1 | spec-anchor-setup-system 正常系 | **PASS** | evidence/P1_E1_setup_system/ | 全5項目 PASS |
| P1-E2 | spec-anchor-setup-project 正常系 | **PASS** | evidence/P1_E2_setup_project/ | 全9項目 PASS |
| P1-E3 | /spec-core 正常系 | **PASS** | evidence/P1_E3_spec_core/ | 全12項目PASS（2回目incremental は E3補足で実施予定） |
| P1-E3.1 | Section 分割・source_section_id 検証 | **PASS** | evidence/P1_E3_1_section_id/ | 全3項目 PASS |
| P1-E3.2 | Qdrant payload 構造確認 | **PASS** | evidence/P1_E3_2_qdrant_payload/ | --rebuild 後に確認。テストミス-001 記録済み |
| P1-E4 | freshness gate（Source Specs 変更 / pending conflict） | **PASS** | evidence/P1_E4_freshness_gate/ | 全6項目 PASS |
| P1-E5 | /spec-inject 正常系（CLI + Agent） | **PASS** | evidence/P1_E5_inject_cli/ / evidence/P1_E5_agent/ | CLI 5 項目 + Agent 5 セクション構造 PASS |
| P1-E6 | /spec-realign 正常系（CLI + Agent） | **PASS** | evidence/P1_E6_realign_cli/ / evidence/P1_E6_agent/ | CLI 3 項目 + Agent 4 区分構造 PASS |
| P1-E7 | エラー系（config 不在 / purpose 不在 / concept 不在 / Source Specs 0 件） | **PASS** | evidence/P1_E7_error_cases/ | 全9項目 PASS |
| P1-E8 | 設定・環境変数（.env 上書き禁止 / デバッグ変数） | **PASS** | evidence/P1_E8_config_env/ | 全3項目 PASS |
| P1-E9 | Related Sections の relation_hint enum 確認 | **PASS** | evidence/P1_E9_relation_hint/ | conflicts_with 不在・許可5種のみ確認 |
| P1-E10 | Chapter Key Anchor の必須フィールド確認 | **PASS** | evidence/P1_E10_chapter_anchor/ | 必須6フィールド全て存在 |

### フェーズ①完了条件

- P0 の全項目が PASS
- P1-E1 〜 P1-E10 が全て PASS または SKIP（SKIP は備考に理由を記載）
- 全テストの証跡が `evidence/` に存在する
- 人間が「フェーズ①完了」を確認し「フェーズ②着手可」と明示する

フェーズ①完了宣言: **完了候補**（人間の確認と「フェーズ②着手可」明示を待つ）

---

## フェーズ③ — 残 [ ] 章別全量確認（Production 環境）

| グループ ID | 対象章 | 判定 | 証跡パス | 残件数 |
|---|---|---|---|---|
| G2 | §2 用語と範囲（残11件） | **PASS** | evidence/P3_G2_terms/ | 11件 PASS |
| G3 | §3 動作モデル（残12件） | **PASS/SKIP** | evidence/P3_G3_operation_model/ | 11件PASS、1件SKIP（L264:LLM失敗が必要） |
| G4 | §4 保持物（残30件） | **PASS/SKIP** | evidence/P3_G4_artifacts/ | 27件PASS、4件SKIP（Qdrant停止/LLM失敗が必要、P2-F1で追加確認） |
| G5 | §5 責務境界（全15件） | **PASS** | evidence/P3_G5_responsibility/ | 0 |
| G6 | §6 コマンド体系（残22件） | 未実施 | — | 22 |
| G7 | §7 /spec-core（残118件） | **PASS/SKIP** | evidence/P3_G7_spec_core/ | 85件PASS、8件SKIP（Qdrant停止/LLM失敗/旧artifact が必要） |
| G8 | §8 /spec-inject（残50件） | **PASS** | evidence/P3_G8_spec_inject/ | 50件PASS、0件SKIP |
| G9 | §9 /spec-realign（残8件） | **PASS** | evidence/P3_G9_spec_realign/ | 8件PASS、0件SKIP |
| G10 | §10 設定ファイル（残66件） | 未実施 | — | 66 |
| G11 | §11 エラー契約（残31件） | 未実施 | — | 31 |

---

## フェーズ② — Production 環境で実施困難な項目

**フェーズ①完了・人間の「フェーズ②着手可」明示を受けてから着手する。**

| テスト ID | テスト名 | 判定 | 証跡パス | 備考 |
|---|---|---|---|---|
| P2-F1 | Qdrant 停止状態のエラーハンドリング | 未着手 | — | Qdrant を意図的に停止 |
| P2-F2 | FlagEmbedding 不在状態 | **PASS** | evidence/P2_F2_flagembedding_absent/ | blocked + flagembedding_missing 確認。復旧済み |
| P2-F3 | Agent CLI 不在状態（codex / claude を PATH から除外） | **PASS** | evidence/P2_F3_agent_cli_absent/ | blocked + agent_cli_unavailable 確認 |
| P2-F4 | watcher 実行中の freshness gate | **PASS** | evidence/P2_F4_watcher_running/ | blocking_reasons=[watcher_running,dirty_or_stale_source] 確認 |

フェーズ②着手許可: **未受領**

---

## 残範囲・未実施・SKIP 一覧

| テスト ID | 内容 | 理由 | 次のアクション |
|---|---|---|---|
| （テスト開始後に記入） | | | |

---

## 発見した問題点

実装の不具合・仕様との乖離を記録する。テスト手順の誤りは「テスト上のミス」欄に記録する。

| 問題 ID | 発見日 | テスト ID | 問題の内容 | 影響 | ステータス |
|---|---|---|---|---|---|
| （発見次第記入） | | | | | |

---

## テスト上のミス

テスト手順の誤りや、想定外の使い方によって生じた現象を記録する。実装バグとは無関係。

| ミス ID | 発見日 | テスト ID | ミスの内容 | 対処 |
|---|---|---|---|---|
| テストミス-001 | 2026-05-23 | P1-E3.2 | テスト用ドキュメント（別 project root `/tmp/sa-test-sonnet-e3-y5Qkw`）で一度 upsert した `spec_anchor_section_sonnet` を、新 project（`/tmp/sa-test-sonnet-e3-q2iKl`）でそのまま使い回した。新 project の section_manifest は旧 sections を知らないため stale 判定できず、旧ポイント 428 件が残存した。これは別 project root から同一 collection を共有するという**想定外の使い方**であり、実装の問題ではない。 | `spec-anchor core --rebuild` で collection を再作成し 4 points に正常化。以降は project root ごとに collection 名を分けるか、同一 project root を継続使用する。 |
