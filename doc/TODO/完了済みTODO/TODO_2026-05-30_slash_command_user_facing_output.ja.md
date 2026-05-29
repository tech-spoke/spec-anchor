# TODO: スラッシュコマンドのユーザー向け出力整理

**起票日**: 2026-05-29
**起票者**: Human
**最終更新**: 2026-05-30
**ステータス**: 完了 (2026-05-30。全 13 sub task が LLM コンプリート + 人間レビュー OK の 3 段ゲートを通過。Human により完了承認済み)
**関連設計書**: `doc/EXTERNAL_DESIGN.ja.md §8.5`、`.claude/commands/spec-inject.md` / `spec-realign.md` / `spec-core.md`、`spec_anchor/templates/.claude/commands/` 配下

## 全体目的

`/spec-inject` / `/spec-realign` / `/spec-core` の停止時応答に CLI 内部の field 名・enum 値・パイプライン段階名がそのまま漏出しており、利用者が読み解けない状態になっている。

2026-05-29 セッションで実際に観測された失敗例:

- `should_stop=true` / `status="blocked"` を会話に貼る
- `blocking_reasons: 2 件` のように内部 field 名と件数だけを提示する
- `dirty_or_stale_source` / `pending_conflict` のような enum 値を生で貼る
- `section_metadata_generation` / `related_sections` / `retrieval_index` / `chapter_anchors` のような内部パイプライン段階名を貼る
- pending Conflict Review Item が 2 件残っていることを「2 件残っている」とだけ伝え、`claims` / `why_conflicting` / `decision_options` の本文を展開しない（コマンドテンプレに「提示せよ」と書かれているのに守られていない）
- `needs_agent_answer` の翻訳として「answer candidate が未提供です」を表に出してしまう

利用者は CLI 構造を知らない前提でスラッシュコマンドを使う。漏出した内部用語は理解不能であり、何をすればいいか分からない状態に陥る。

本課題は次を達成して完了とする:

1. CLI が返しうるあらゆる停止状態を、利用者視点の **6 カテゴリ + 情報通知 1 + 非表示 1** にマップする
2. 6 カテゴリ別の停止時ユーザー向け出力フォーマットをコマンドテンプレに固定する
3. 内部 field 名・enum 値・パイプライン段階名が**ユーザー向け本文に出ない**ことを禁止用語リストで強制する
4. pending Conflict Review Item は本文（主張 / 出典 / 論点 / 選択肢）が必ず展開される
5. `structure_realign_answer` の error を field 単位に詳細化し、Agent のリトライが意味を持つ仕組みにする
6. `needs_agent_answer` は利用者に見せず Agent 内部で答案を組み立てて自動再実行する
7. 3 コマンド（`/spec-core` / `/spec-inject` / `/spec-realign`）の **正常完了時レポート** も利用者視点のフォーマットへ整理し、内部 field 名 (`status=fresh` / `pending_conflict_count` / `retrieval_index_status` / `stale_resolution_count` / `freshness_report.blocking_reasons` 等) がそのまま会話に出ない
8. CLI 出力に外部ライブラリの進捗ログ等のノイズが混入せず、result JSON が stdout から確実に取り出せる（Agent が Python parser を書かなくても結果を読める）
9. 上記をコマンドテンプレ（プロジェクト直下と `spec_anchor/templates/` 配下の両方）と外部設計書 §8.5 で一貫させる
10. 全 sub task の達成内容を E2E テストで実行確認し、`pytest pass` + `LLM 自己確認` + `人間レビュー OK` の 3 段ゲートで承認されている
11. Agent の能動的 Agentic Search の余地 (「CLI 4 path は探索の起点であり上限ではない」「探索の十分性は Agent が判断する」) がコマンドテンプレと外部設計書 §8.3 に明文化され、`/spec-inject` / `/spec-realign` で Agent が「4 path 通過 → 即終了」と機械的に解釈する余地が排除されている (ドリフト防止と Agent 主体性の両立を維持)
12. 利用者向け本文に日本語以外の自然文 (例: CLI が返す英語 default 文字列 `Ask a human to decide this conflict.`) が混入しない。コマンド名・URL・file path は除外。Agent は CLI raw 文字列が日本語でない自然文と判定したら日本語訳に置き換える。CLI 側は raw 文字列を機械可読のまま (将来の i18n を見据える)

## 状況サマリー

| # | sub task ID | 概要 | 状態 | 残作業 | 最終更新 | 完了 commit |
|---|---|---|---|---|---|---|
| 1 | T-stop-category-mapping | CLI 停止状態を 6 カテゴリ + ◇ + ✕ へ確定マップ | LLM コンプリート | §8.5 反映は #7 で実施 | 2026-05-29 | (Phase2) |
| 2 | T-stop-output-template-3files | 3 コマンドテンプレに停止時出力フォーマットと禁止用語リストを追加 | LLM コンプリート | — | 2026-05-29 | (Phase2) |
| 3 | T-pending-conflict-body-expansion | pending Conflict Review Item の本文展開を必須化 | LLM コンプリート | — | 2026-05-29 | (Phase2) |
| 4 | T-needs-agent-answer-hide | `needs_agent_answer` をユーザーに見せず Agent 自動再実行で吸収 | LLM コンプリート | — | 2026-05-29 | (Phase2) |
| 5 | T-realign-cli-error-detail | `structure_realign_answer` のエラーを field 単位に詳細化 | LLM コンプリート | 外部設計書 §8.5 の error schema 反映は #7 で実施 | 2026-05-29 | (Phase3) |
| 6 | T-realign-retry-with-feedback | 構造化失敗時の 1 回リトライ + feedback 経路を契約化 | LLM コンプリート | #6-s03 (#5 未完了時の盲目リトライ無し) は #5 完了済みのため削除 | 2026-05-29 | (Phase3) |
| 7 | T-external-design-stop-output-contract | 外部設計書に停止時/正常完了/リトライ表示契約を反映 (§8.7 新設) | LLM コンプリート | — | 2026-05-29 | (Phase5) |
| 8 | T-normal-completion-output-template | 3 コマンドの正常完了時レポートを利用者視点フォーマットへ整理 | LLM コンプリート | — | 2026-05-29 | (Phase4) |
| 9 | T-cli-stdout-noise-cleanup | CLI 出力から HF / FlagEmbedding / weights loader 等の進捗ログを stderr へ分離 | LLM コンプリート | — | 2026-05-29 | (Phase1) |
| 10 | T-templates-mirror | `spec_anchor/templates/.claude/commands/` と `.codex/skills/spec-anchor/SKILL.md` に同期反映 | LLM コンプリート | — | 2026-05-29 | (Phase5) |
| 11 | T-e2e-user-facing-output-verification | E2E 検証基盤の整備 + 全 sub task のシナリオ集約 + 人間レビュー protocol の運用 | 基盤構築 LLM コンプリート | 各 sub task 完了時にシナリオ追記される (集約表を継続更新) | 2026-05-29 | (Phase1) |
| 12 | T-explicit-free-agentic-search | Agent の能動的 Agentic Search 余地を `/spec-inject` / `/spec-realign` テンプレと外部設計書 §8.3 で明文化 | LLM コンプリート | — | 2026-05-29 | (Phase7) |
| 13 | T-japanese-only-user-facing | 利用者向け本文を日本語に統一 (英語自然文を Agent が翻訳) | LLM コンプリート | — | 2026-05-29 | (Phase6) |

本表の「状態」と「残作業」を見るだけで次に何をすべきかが分かるよう、sub task が進むたびに更新する。

## E2E 検証フロー

各 sub task (#1〜#10) は #11 (E2E 検証基盤) と連動する。担当は Claude main agent (今回は Codex 不使用)。

### sub task 実装中 〜 LLM コンプリートまで

1. sub task 実装と並行して、確認すべき E2E シナリオを設計
2. シナリオを **#11 のシナリオ集約表** に追記し、**自身の sub task の E2E 検証表** にも同じ行を追記
3. 該当する CLI 呼び出し → Agent 整形を実行し、最終応答を **エビデンスとして `tests/e2e/snapshots/<scenario_id>.md` に保存**
4. `pytest tests/e2e/test_user_facing_output.py` でシナリオに対応するテストが pass することを確認 → 当該行の **pytest 列に `[✓]`**
5. Claude main agent が snapshot ファイルを読み、フォーマット・語彙・情報の伝達性が期待通りであることを自己確認 → **LLM 自己確認 列に `[✓]`**
6. pytest と LLM 自己確認の両方が ✓ になったら **完了 列に `[✓]`** (人間レビュー列は `未確認` のまま)
7. sub task の全シナリオ行が「完了 `[✓]`」になったら、sub task を「LLM コンプリート」状態へ

### sub task LLM コンプリート後（人間レビュー）

1. 人間が **#11 の集約表** を読む
2. **シナリオ網羅性チェック**:
   - 抜けあり: 人間が該当 sub task の E2E 検証表に「追加シナリオ」を箇条書きで指摘
   - Claude main は指摘シナリオを追加し、上記 [2]〜[6] を実施
3. **エビデンス確認**:
   - `tests/e2e/snapshots/<scenario_id>.md` を読む
   - 出力フォーマット・語彙・情報の伝達性に問題があれば、**該当行の「人間レビュー」列に「差し戻し」と記載 + 指摘内容を別途記載**
   - Claude main は完了 列の `[✓]` を取り消し、実装を修正 → 上記 [3]〜[6] を再実施 → 完了再付与
4. 全シナリオの「人間レビュー」列が `OK` になったら、sub task を最終「完了」状態へ進める

### エビデンスの保存場所と命名

エビデンス (実 CLI 呼び出し → Agent 整形した最終応答) は次に保存する:

```
tests/e2e/snapshots/<scenario_id>.md
```

`scenario_id` 命名規約:

```
#<sub_task 番号>-s<連番 NN>
```

例:
- `#2-s01` (sub task #2 の 1 番目シナリオ)
- `#3-s04`
- `#9-s08`

snapshot ファイル名は `<scenario_id>_<短い識別子>.md` の形で sub task 完了時に決める。例:

- `tests/e2e/snapshots/#2-s01_stop_setup_missing_config_spec_core.md`
- `tests/e2e/snapshots/#3-s04_pending_conflict_with_dirty_source.md`
- `tests/e2e/snapshots/#9-s08_stdout_no_hf_progress_noise.md`

snapshot ファイルは pytest が比較 fixture として使うと同時に、人間レビューの対象 artifact になる。出力が変わった場合は (a) snapshot を更新するか (b) 実装を修正するか を Claude main が判断し、必要なら人間レビューに上げる。

新たに判明したシナリオは、sub task 実装中に該当 sub task の E2E 検証表へ追記 + #11 集約表へ追記する。事前記載と追記の区別は不要 (連番のみ管理)。

### E2E 検証表の列構成

各 sub task の「E2E 検証」セクションと #11 のシナリオ集約表は次の列を持つ:

| 列 | 値 |
|---|---|
| シナリオ ID | `<sub_task_id>_<カテゴリ>_<バリエーション>` |
| 概要 | 1 行説明 |
| エビデンス | `tests/e2e/snapshots/<scenario_id>.md` への相対 path |
| pytest | `[ ]` / `[✓]` |
| LLM 自己確認 | `[ ]` / `[✓]` |
| 完了 | `[ ]` / `[✓]` (pytest と LLM 自己確認の両方が ✓ のときのみ) |
| 人間レビュー | `未確認` / `OK` / `差し戻し: <指摘要約>` |

#11 集約表のみ「sub task」列が先頭に追加される。

## sub task 詳細

### #1 T-stop-category-mapping: CLI 停止状態を 6 カテゴリ + ◇ + ✕ へ確定マップ

**状態**: LLM コンプリート
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase2

#### 背景

最初は 4 カテゴリ案で進めようとしたが、実装を読まずに「網羅できている」と判断していた。確認の結果、3 種類の漏れが出た:

- `degraded_optional_artifact` 単独（status=`degraded`、続行可能）
- watcher 系（`watcher_running` / `watcher_queue_pending`）は「待てば直る」が対応で、`/spec-core` 実行とは性質が違う
- 外部サービス未起動（Qdrant / LLM provider）は「初期設定」とは別カテゴリで扱った方が、運用後の利用者にとって自然

これらを取り込んだ最終分類:

| | カテゴリ | 該当する CLI 状態 | 利用者が取る行動 |
|---|---|---|---|
| ① | 初期設定が未完了 | `.spec-anchor/config.toml` 不在、`docs/core/purpose.md` / `core_concept.md` 不在、`sources.include` 不一致 | `spec-anchor-setup-project` 実行、purpose / concept 等のファイル作成 |
| ② | 外部サービスが必要 | Qdrant 接続失敗、LLM provider 失敗 | service 起動 / 接続情報の確認 |
| ③ | 保持物の更新が必要 | `dirty_or_stale_source` / `stale_config_or_schema` / `failed_required_artifact`（status=`blocked` または `failed`） | `/spec-core` 実行 |
| ④ | 保持物の更新中・待機 | `watcher_running` / `watcher_queue_pending` | 完了を待つ |
| ⑤ | 人間判断が必要な仕様の衝突 | `pending_conflict` | 衝突を読んで採用案を決定 |
| ⑥ | ツール側のエラー | 想定外 Python 例外、`status="error"` のうち①〜⑤に当てはまらないもの | 開発元へ報告 |
| ◇ | 情報通知（続行可能） | `degraded_optional_artifact` 単独（status=`degraded`） | 認知のみ、無視可 |
| ✕ | 非表示 | `needs_agent_answer` | Agent 内部で答案組み立てて再実行（利用者表示なし） |

CLI 側の値の根拠:

- `blocking_reasons` 全 7 種は `spec_anchor/freshness.py:24-30` で定数定義
- `status` 4 値（`fresh` / `blocked` / `failed` / `degraded`）は `spec_anchor/freshness.py:18-22`
- `classify_freshness_status` (`spec_anchor/freshness.py:298-310`) は `degraded_optional_artifact` 単独時のみ `degraded` を返し、他と混在すれば `blocked` へ降格

#### 真因 / 対応方針

実装を読まずにカテゴリ数を決めると漏れる。`spec_anchor/freshness.py` と `spec_anchor/cli.py` / `realign.py` / `inject.py` / `core.py` の停止 return 経路を全列挙し、6 カテゴリへ写像する。完了後、外部設計書とコマンドテンプレで同じ表を参照する。

#### 検証条件

- `git grep '"status": "blocked"\|"status": "failed"\|"status": "error"\|should_stop\s*=\s*True'` の hit がすべて 6 カテゴリ + ◇ + ✕ のどれかへマップできる
- `blocking_reasons` の 7 enum がすべて表に含まれる

#### 完了条件

カテゴリマップ表が確定し、T-stop-output-template-3files と T-external-design-stop-output-contract で参照される

#### 残作業

- 上記マップ表を `doc/EXTERNAL_DESIGN.ja.md §8.5` 改訂案として下書きする（T-7 と一体で進める）

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| (#1 はマップ表確定が主要 output。個別 E2E シナリオは #2〜#9 が代行する。マップ表自体の網羅性は #7-s02 doc lint で担保) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: なし
scope 外: setup スクリプト (`spec-anchor-setup-project`) の出力整理は別 task

---

### #2 T-stop-output-template-3files: 3 コマンドテンプレに停止時出力フォーマットと禁止用語リストを追加

**状態**: LLM コンプリート
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase2

#### 背景

現状のテンプレ:

- `.claude/commands/spec-inject.md` には「停止時のユーザー向け出力テンプレ」が存在しない。§128-135 に「pending_conflict_items を提示せよ」とだけ書かれており、どう提示するかが Agent 任せ → 件数だけ提示して逃げる事態が発生
- `.claude/commands/spec-realign.md` §84-99 にはフォーマットがあるが、`conflict_id:` `severity:` `claims:` のように **内部 field 名を label として表に出している** ためユーザー向けではない
- `.claude/commands/spec-core.md` §19 は「これらを提示せよ」だけでフォーマット未定義
- 3 ファイルとも「内部 field 名・enum 値・パイプライン段階名を貼らない」禁止用語リストが無い

#### 真因 / 対応方針

各ファイルに次を追加する:

1. 「停止時のユーザー向け出力フォーマット」セクションを新設。T-stop-category-mapping の 6 カテゴリ + ◇ それぞれの出力テンプレを固定で記述。該当しないカテゴリは出力しない（「該当なし」も書かない）
2. 「ユーザー向け本文に貼ってはいけない内部用語」リストを新設:
   - `should_stop` / `status="blocked"` / `="failed"` / `="error"`
   - `stop_reason="needs_agent_answer"` / `blocking_reasons`
   - 全 enum 値（`dirty_or_stale_source` / `stale_config_or_schema` / `watcher_running` / `watcher_queue_pending` / `pending_conflict` / `failed_required_artifact` / `degraded_optional_artifact`）
   - 内部 path 名（`inject_result.<...>`）
   - パイプライン段階名（`section_metadata_generation` / `related_sections` / `retrieval_index` / `chapter_anchors`）
3. 許可される文字列の明示:
   - `recommended_next_action` の値文字列（CLI 自身が出力する外部契約文言）
   - スラッシュコマンド名、実 CLI command 名、ファイルパス + section ID

#### 検証条件

- `tests/test_spec_inject.py` / `test_spec_realign.py` に「Agent 出力に禁止用語が含まれない」確認を追加（可能な範囲で）
- pending conflict / dirty source / watcher 動作中の各停止状態を再現するテストで、固定テンプレ通りの出力が出ることを確認
- Manual: 実プロジェクトで `/spec-inject` を呼んで観察

#### 完了条件

3 ファイルの停止時テンプレと禁止用語リストが揃い、利用者会話に内部用語が出ないことが確認できる

#### 残作業

- spec-inject.md / spec-realign.md / spec-core.md の編集
- テスト追加

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #2-s01 | ① 初期設定未完了 (config.toml 不在) を代表コマンド /spec-core で表示 | tests/e2e/snapshots/#2-s01_stop_setup_missing_config_spec_core.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2-s02 | ② 外部サービス必要 (Qdrant 接続失敗) を代表コマンド /spec-inject で表示 | tests/e2e/snapshots/#2-s02_stop_qdrant_unavailable_spec_inject.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2-s03 | ③ 保持物更新必要 (dirty_or_stale_source) を代表コマンド /spec-inject で表示 | tests/e2e/snapshots/#2-s03_stop_dirty_source_spec_inject.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2-s04 | ④ 保持物の更新中・待機 (watcher_running) を代表コマンド /spec-inject で表示 | tests/e2e/snapshots/#2-s04_stop_watcher_running_spec_inject.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2-s05 | ⑥ ツール側のエラー (想定外 Python 例外) を代表コマンド /spec-core で表示 | tests/e2e/snapshots/#2-s05_stop_tool_error_spec_core.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2-s06 | ◇ 情報通知 (degraded_optional_artifact 単独) で続行可能を確認 | tests/e2e/snapshots/#2-s06_info_degraded_optional_continue.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2-s07 | 3 コマンド一貫性: ③ dirty_or_stale_source 同条件で /spec-core / /spec-inject / /spec-realign が同テンプレ表示 | tests/e2e/snapshots/#2-s07_stop_dirty_three_commands_consistency.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2-s08 | 禁止用語横断チェック: #2-s01〜#2-s07 出力に内部 field 名 / enum 値 / パイプライン段階名が含まれない | tests/e2e/snapshots/#2-s08_forbidden_terms_cross_check.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: T-stop-category-mapping
本 sub task は停止時テンプレと禁止用語リストが中心。正常完了時テンプレは #8 T-normal-completion-output-template で扱う (本課題内)。

---

### #3 T-pending-conflict-body-expansion: pending Conflict Review Item の本文展開を必須化

**状態**: LLM コンプリート
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase2

#### 背景

spec-realign.md §84-99 の現フォーマット:

```text
conflict_id: <...>
severity: <...>
claims: <...>
why_conflicting: <...>
...
```

これは Agent の自己点検向けの書き方で、ユーザーには `conflict_id` `severity` `claims` のような field 名がそのまま出る。spec-inject.md にはこのフォーマットすら無く、件数だけが出てしまった。

#### 真因 / 対応方針

人間向けフォーマットへ置換:

```text
■ 人間判断が必要な仕様の衝突があります (N 件)

  1. <短い見出し: 衝突の論点を 1 行で>

     主張 A: <claims[0].statement>
        出典: <claims[0].source_ref>
     主張 B: <claims[1].statement>
        出典: <claims[1].source_ref>

     論点: <why_conflicting>
     人間判断が必要な理由: <why_llm_cannot_decide>
     重要度: <severity>

     関係する仕様:
       - <source_refs[0]>
       - <source_refs[1]>

     選択肢:
       - <decision_options[0]>
       - <decision_options[1]>

     次の操作: <pending_conflict_items[i].recommended_next_action の値そのまま>

     (衝突 ID: <conflict_id>  ← 再参照用)
```

`claims` が 3 件以上の場合は「主張 A / B / C / ...」と続ける。本フォーマットを `/spec-inject` / `/spec-realign` / `/spec-core` の 3 ファイルすべてに記述する（コピペで揃える）。

#### 検証条件

- pending conflict ある状態で 3 コマンドを呼び、上記フォーマット通りの体裁が出る
- `tests/test_spec_inject.py` / `test_spec_realign.py` / `test_spec_core.py` で出力に `claims` / `why_conflicting` の **値**（field 名でなく）が含まれることを確認

#### 完了条件

3 ファイル一貫してフォーマットが固定され、テストで保証される

#### 残作業

- 3 ファイルへフォーマット追加
- テスト追加

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #3-s01 | pending conflict 1 件 / 単一 claim pair (主張 A / B 形式) | tests/e2e/snapshots/#3-s01_pending_conflict_single_pair.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #3-s02 | pending conflict 1 件 / 3 件以上の claims (主張 A / B / C 連続形式) | tests/e2e/snapshots/#3-s02_pending_conflict_three_claims.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #3-s03 | pending conflict 複数件 (2 件以上、見出し連番 1./2./...) | tests/e2e/snapshots/#3-s03_pending_conflict_multiple.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #3-s04 | pending conflict + dirty_or_stale_source 混在 (③ と ⑤ の両方表示) | tests/e2e/snapshots/#3-s04_pending_conflict_with_dirty_source.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #3-s05 | 3 コマンド一貫性: pending conflict が /spec-core / /spec-inject / /spec-realign で同フォーマット表示 | tests/e2e/snapshots/#3-s05_pending_conflict_three_commands.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: T-stop-output-template-3files
scope 外: なし

---

### #4 T-needs-agent-answer-hide: `needs_agent_answer` をユーザーに見せず Agent 自動再実行で吸収

**状態**: LLM コンプリート
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase2

#### 背景

`needs_agent_answer` は `/spec-realign` を答案なしで呼んだとき、または答案構造化に失敗したときに CLI が返す内部信号 (`spec_anchor/realign.py:294-318`)。これは「次に答案を作って再実行せよ」という Agent 向けメッセージであり、ユーザーには見せるべきでない。

現テンプレでは `stop_reason="needs_agent_answer"` と CLI の `recommended_next_action="provide an Agent-generated answer candidate for /spec-realign"` をそのまま伝達する経路があり、ユーザーが「answer candidate って何？」となる。

#### 真因 / 対応方針

`/spec-realign` のテンプレ §18-19 を次の挙動に整理する:

1. 利用者が `/spec-realign "<課題文>"` を呼ぶ
2. Agent は答案なしで CLI を実行
3. CLI が `needs_agent_answer` を返したら、Agent が path ①〜④ Agentic Search → constraints 抽出 → 4 区分答案を組み立てる
4. Agent が `spec-anchor realign --answer-json '<json>'` で再実行する
5. 利用者には整形済み RealignResult のみが表示される

このフローの**途中段階を利用者へ報告しない**ことを契約として明示する。`needs_agent_answer` / `answer candidate` / `stop_reason` の語はユーザー向け本文に出さない（T-stop-output-template-3files の禁止用語リストに含める）。

#### 検証条件

- 答案なしで `/spec-realign "<課題>"` を呼んだとき、最終出力に `needs_agent_answer` / `answer candidate` / `stop_reason` が含まれない
- 同時に整形済み RealignResult が返ること（Agent が黙って再実行している証跡）

#### 完了条件

テンプレと自動テストの両方で確認できる

#### 残作業

- `/spec-realign` テンプレに自動再実行経路を契約化
- テスト追加

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #4-s01 | /spec-realign 答案なし呼び出し → Agent 自動再実行 → 整形済み RealignResult。出力に `needs_agent_answer` / `answer candidate` / `stop_reason` の語が含まれない | tests/e2e/snapshots/#4-s01_realign_auto_rerun_clean.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #4-s02 | Agent 内部での自動再実行が利用者に見えない (再実行の進捗ログや「次は答案を作ります」等のメタ説明が含まれない) | tests/e2e/snapshots/#4-s02_realign_auto_rerun_no_meta.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: T-stop-output-template-3files
scope 外: `/spec-inject` 側の挙動（こちらは答案を作らない契約）

---

### #5 T-realign-cli-error-detail: `structure_realign_answer` のエラーを field 単位に詳細化

**状態**: LLM コンプリート
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase3

#### 背景

`spec_anchor/realign.py:170-238` の `structure_realign_answer` は SpecRealignError を 2 種類しか raise しない:

- `"agent_answer is required for /spec-realign"` (line 184)
- `"agent_answer must include a non-empty answer or proposal section"` (line 236)

これでは「答案のどの 4 区分が欠けたか」「constraints のどの field が schema 違反か」が分からず、Agent のリトライが盲目試行になる。T-realign-retry-with-feedback で「失敗時 1 回リトライ + error feedback」を契約化するためには、CLI 側がエラー詳細を返す必要がある。

#### 真因 / 対応方針

`SpecRealignError` を構造化エラーへ拡張:

```python
class SpecRealignError(ValueError):
    def __init__(
        self, message: str, *,
        code: str,                    # 例: "missing_final_section" / "empty_constraints" / "invalid_evidence_origin"
        field: str | None = None,     # 例: "answer.final" / "constraints[0].evidence_origin"
        expected: Any = None,         # 例: "non-empty mapping" / "one of Purpose|Core Concept|Source Specs|Conflict Review Item"
        actual: Any = None,
    ): ...
```

CLI 出力 JSON の error blockに `code` / `field` / `expected` / `actual` を含める。あわせて constraints schema 違反検出をオプションで追加（evidence_origin の値域チェック、support_refs の型チェック、applicability の空チェック等）。

スコープ:

- `spec_anchor/realign.py:170-238` の `structure_realign_answer` 改修
- `spec_anchor/cli.py` の realign 出力 schema 拡張（error block の詳細化）
- `tests/test_spec_realign.py` に各 error code を引き当てるテスト追加
- `doc/EXTERNAL_DESIGN.ja.md §8.5` の error schema 更新

#### 検証条件

- 不正答案を渡したとき、CLI が `error.code` / `error.field` / `error.expected` を含んだ JSON を返す
- 各 error code を直接ターゲットするユニットテストが pass する
- 既存 test_spec_realign の正常系が引き続き pass

#### 完了条件

CLI 詳細エラーが Agent の prompt に feedback として組み込める形になっている。T-realign-retry-with-feedback が機能する前提が整う。

#### 残作業

- `SpecRealignError` 拡張
- constraints schema 検証追加
- CLI 出力 schema 更新
- テスト追加
- 外部設計書反映

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #5-s01 | 不正答案 (final 区分なし) → CLI が `error.code="missing_final_section"` / `error.field` / `error.expected` を含む JSON 返却 | snapshots/#5-s01_realign_error_missing_final_section.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #5-s02 | 不正答案 (constraints の evidence_origin 不正値) → CLI が `error.code="invalid_evidence_origin"` / `error.field="constraints[N].evidence_origin"` を返す | snapshots/#5-s02_realign_error_invalid_evidence_origin.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #5-s03 | 不正答案 (support_refs 型違反) → CLI が `error.code="invalid_support_refs_type"` を返す | snapshots/#5-s03_realign_error_invalid_support_refs_type.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #5-s04 | 正常答案 → error block が含まれない RealignResult 返却 | snapshots/#5-s04_realign_valid_no_error_block.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: なし（T-stop-category-mapping と並行可）
scope 外: constraints の意味検証（root cause: Agent の責務）は対象外。あくまで形式検証

---

### #6 T-realign-retry-with-feedback: 構造化失敗時の 1 回リトライ + feedback 経路を契約化

**状態**: LLM コンプリート
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase3

#### 背景

`needs_agent_answer` を受けて Agent が答案を組み立てて再実行する経路で、構造化に失敗した場合の挙動が未定義。盲目リトライは時間と API コストの無駄になりやすく、無限ループの恐れがある。

T-realign-cli-error-detail 完了後、CLI が field 単位 error を返せるようになる。これを Agent prompt に feedback として組み込めば、リトライが意味を持つ。

#### 真因 / 対応方針

`/spec-realign` テンプレに次のリトライポリシーを明示:

1. 初回試行で `structure_realign_answer` が失敗したら、Agent は CLI が返した `error.code` / `error.field` / `error.expected` を読む
2. 同じ Agentic Search 結果を使い、不正だった field だけを修正して再構成
3. 1 回だけ再実行
4. なお失敗したら、⑥ ツール側のエラーへ落とし、最後の答案 JSON と CLI error 詳細をユーザーに併記して表示

T-realign-cli-error-detail が完了していない段階ではこのリトライは盲目になるため、それまでは「1 回試行 + 失敗時 ⑥」で進める（リトライ昇格は T-5 完了後）。

#### 検証条件

- 構造化失敗を 2 回連続で起こした時、⑥ カテゴリ表示で停止する
- ⑥ 表示に最後の答案と CLI error 詳細が含まれる
- 構造化失敗 → CLI error feedback → リトライ成功のシナリオが pass する

#### 完了条件

リトライポリシーがテンプレに明記され、テストで保証される

#### 残作業

- `/spec-realign` テンプレにリトライ契約を追加
- テスト追加（T-5 完了後）

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #6-s01 | 構造化失敗 (1 回目) → CLI error 詳細を Agent が読んで修正 → 2 回目で成功 → 整形済み RealignResult | snapshots/#6-s01_retry_success_after_fix.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #6-s02 | 構造化失敗 (1 回目 + リトライ) → 再失敗 → ⑥ ツール側エラー表示。出力に「最後の答案 JSON」と「CLI error 詳細」が併記される | snapshots/#6-s02_retry_exhausted_tool_error.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #6-s03 | (削除: #5 完了済みのため本シナリオは不要) | — | — | — | — | 削除 |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: T-stop-output-template-3files、T-realign-cli-error-detail
scope 外: 3 回以上のリトライ（必要性が出たら別 task）

---

### #7 T-external-design-stop-output-contract: 外部設計書 §8.5 に停止時表示契約を反映

**状態**: LLM コンプリート
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase5

#### 背景

外部設計書 `doc/EXTERNAL_DESIGN.ja.md` §8.5 (「CLI 出力と人間向け整形」) には正常時整形のみが書かれており、停止時の表示契約が無い。コマンドテンプレ側にだけ書くと、設計判断が分散し、将来の整理で再びズレる。CLAUDE.md ルール14 (ソースコードを読んだことがない読者に通じる言葉) に従い、設計書側に契約として記載する必要がある。

#### 真因 / 対応方針

§8.5 を次の構造に再編:

- §8.5.1 正常時の人間向け整形（既存）
- §8.5.2 停止時の人間向け整形（新設）
  - 6 カテゴリ + ◇ + ✕ マップ表
  - カテゴリ別の出力フォーマット
  - 禁止される内部用語
  - 許可される文字列
- §8.5.3 リトライポリシー（新設、T-realign-retry-with-feedback と整合）

ルール14 に従い、設計書側では `should_stop` / `blocking_reasons` などの内部 field 名を使わず、「保持物が古い」「人間判断が必要な衝突」のような利用者体感の言葉で記述。CLI フィールド名は内部設計書 (`doc/DESIGN.ja.md`) 側に残す。

#### 検証条件

- 外部設計書 §8.5 → 3 コマンドテンプレ → CLI 実装の 3 層で停止カテゴリと出力フォーマットが一貫
- 外部設計書 §8.5 がルール14 を満たす（CLI 内部 field 名がユーザー向け契約に出てこない）

#### 完了条件

外部設計書改訂 + 3 コマンドテンプレ整合確認

#### 残作業

- §8.5 改訂下書き
- 3 コマンドテンプレとの突合

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #7-s01 | doc lint: §8.5 本文に内部 field 名 / enum 値 (`should_stop` / `blocking_reasons` / `dirty_or_stale_source` 等) が含まれない (grep) | snapshots/#7-s01_design_no_internal_field_names.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #7-s02 | doc lint: §8.5 のカテゴリマップ表 (6 + ◇ + ✕) が #1 の最終マップと一致、#2/#3/#4 のテンプレ語彙が §8.5 と整合 | snapshots/#7-s02_design_category_map_consistency.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #7-s03 | doc lint: §8.5 のリトライポリシー記述と #6 のテンプレ手順が整合 (1 回試行 + 失敗時 1 リトライ + ⑥ 落とし) | snapshots/#7-s03_design_retry_policy_consistency.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: T-stop-category-mapping、T-stop-output-template-3files
scope 外: §8.5 以外の章は今回触らない

---

### #8 T-normal-completion-output-template: 3 コマンドの正常完了時レポートを利用者視点フォーマットへ整理

**状態**: LLM コンプリート
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase4

#### 背景

これまでの議論は「停止時の出力」に集中していたが、2026-05-29 セッションで `/spec-core` の **正常完了時の応答** にも全く同じ症状（内部 field 名漏出 + 英語混じり日本語 + 重要情報の埋没）が観測された。実例:

```text
完了状態
指標	値
freshness	fresh
pending_conflict_count	0
retrieval_index_status	success
failed_sources / failed_sections	なし
unreflected_conflict_resolutions	なし

注意事項: stale_resolution_count = 3
3 件の Conflict Review Items はすべて status="dismissed" (severity: high、過去に人間が「棄却」と判定済み) ですが、resolution が stale 化しています。
...
このまま /spec-inject を進めても、契約上 stale な resolution は constraint の evidence にならないので、即時の作業ブロッカーではありません。
```

問題点:
- `freshness=fresh` / `pending_conflict_count=0` / `retrieval_index_status=success` / `failed_sources` / `failed_sections` / `unreflected_conflict_resolutions` / `stale_resolution_count` / `status="dismissed"` / `severity` / `base_source_hashes` がそのまま出る
- 「freshness は通った」「stale な resolution」「dismiss と判断」「blocker」など英語混じり日本語
- 本当に伝えるべき情報（「保持物の更新が完了した」「`/spec-inject` 実行可能」「過去に却下した衝突 3 件について、関係仕様が更新されたので再確認が必要かも」）が技術詳細に埋もれている

停止時テンプレ (T-2) と同じ重みで、正常完了時テンプレが各コマンドに必要。

#### 真因 / 対応方針

3 コマンドそれぞれに正常完了時の出力フォーマットを固定する。

##### `/spec-core` 正常完了テンプレ案

```text
■ 保持物の更新が完了しました

  更新があった仕様:
    - <updated_sources のファイルパス、変更があった section の見出し>
    （変更なしの場合は「変更ありませんでした」）

  人間判断が必要な仕様の衝突:
    なし
    （pending_conflict_count > 0 のときは T-3 の pending conflict 本文展開テンプレで提示）

  再確認の候補（過去の衝突解消判断が、現在の仕様変更で見直し余地あり）: <stale_resolution_count> 件
    1. <衝突 ID と簡潔な見出し>
       過去の判断: <resolution.decision を「採用 / 却下 / 修正」へ翻訳>
       なぜ再確認が必要か: 関係する仕様が変更されたため
       (衝突 ID: <conflict_id>)
    2. ...
    （0 件のときはセクション自体を省略）

  次の操作:
    /spec-inject "<課題>" を実行してください。
```

##### `/spec-inject` 正常完了テンプレ

既存テンプレ §63-89 はあるが、`evidence_origin` / `support_refs` / `applicability` の内部 label が露出しやすい。これを次の人間向け語彙へ置き換える:
- `evidence_origin` → 「根拠の種類」
- `support_refs` → 「参照補助」
- `applicability` → 「適用範囲」
- `uncertainty` → 「不確実性 / 確認すべき点」

##### `/spec-realign` 正常完了テンプレ

既存テンプレ §27 で 4 区分整形は指示されているが、内部 field 名（例: `今回守る制約` キー名）が見出し以外にも露出するケースがある。RealignResult の各セクション内部構造（evidence / support_refs / applicability 等）を、`/spec-inject` と同じ語彙置換で表示する。

##### 共通の禁止用語追加

T-2 の禁止用語リストへ追加:
- 正常完了時に出やすい内部 field 名: `updated_sources` / `failed_sources` / `failed_sections` / `retrieval_index_status` / `pending_conflict_count` / `stale_resolution_count` / `unreflected_conflict_resolutions` / `auto_dismissed_conflict_count` / `auto_dismissed_conflict_ids` / `regenerated_chapter_anchors` / `claim_retrieval_status` / `conflict_candidate_triage_status` / `spec_claims_status` / `related_sections_status`
- enum 値: `status="dismissed"` / `severity="high"` 等の生表示 → 「過去の判断: 却下」「重要度: 高」等の翻訳経由

#### 検証条件

- 3 コマンドの正常完了応答に内部 field 名が含まれないことを `tests/test_spec_core.py` / `test_spec_inject.py` / `test_spec_realign.py` で確認
- pending conflict ありなし、stale_resolution ありなし、updated_sources ありなしの組み合わせで Manual 確認

#### 完了条件

3 コマンドの正常完了テンプレが固定され、テストで保証される

#### 残作業

- 3 ファイルへ正常完了テンプレ追加
- T-2 の禁止用語リストへ正常完了系 field 名を追加
- テスト追加

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #8-s01 | /spec-core 正常完了 (updated_sources 無し、pending 0、stale 0、failed 0) → 「変更ありませんでした」表示 | snapshots/#8-s01_core_complete_no_change.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8-s02 | /spec-core 正常完了 (updated_sources 数件) → 変更があった section の見出しが表示される | snapshots/#8-s02_core_complete_updated_sources.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8-s03 | /spec-core 正常完了 (stale_resolution N 件) → 「過去判断再確認の候補」セクション + 人間向け展開 | snapshots/#8-s03_core_complete_stale_resolution.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8-s04 | /spec-core 正常完了 (pending_conflict_count > 0) → #3 の本文展開フォーマットで表示 | snapshots/#8-s04_core_complete_with_pending_conflict.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8-s05 | /spec-inject 正常完了 (制約 N 件、4 区分整形、`evidence_origin` 等の内部 label が「根拠の種類」へ翻訳) | snapshots/#8-s05_inject_complete_translated_labels.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8-s06 | /spec-realign 正常完了 (4 区分 RealignResult、内部 label 漏出なし) | snapshots/#8-s06_realign_complete_four_sections.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8-s07 | 正常完了系の禁止用語チェック: `updated_sources` / `failed_sources` / `retrieval_index_status` / `stale_resolution_count` / `status="dismissed"` / `severity` が本文に含まれない | snapshots/#8-s07_normal_completion_forbidden_check.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: T-stop-category-mapping、T-stop-output-template-3files、T-pending-conflict-body-expansion
scope 外: 正常完了応答の数値メトリクス自体は保持物の品質指標として意味があるので、内部設計書 `doc/DESIGN.ja.md` 側には残す。今回はユーザー向け表現のみ整理

---

### #9 T-cli-stdout-noise-cleanup: CLI 出力から HF / FlagEmbedding / weights loader 等の進捗ログを stderr へ分離

**状態**: LLM コンプリート (s10 のみ実機待ち)
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase1

#### 実装結果 (2026-05-29)

`spec_anchor/cli.py` に次を追加した:

- `_silence_library_stdout_noise()`: CLI 起動時に `HF_HUB_DISABLE_PROGRESS_BARS=1` /
  `HF_HUB_DISABLE_TELEMETRY=1` / `TRANSFORMERS_NO_ADVISORY_WARNINGS=1` /
  `TOKENIZERS_PARALLELISM=false` を `setdefault` で設定 (operator が明示設定した値は尊重)。
- `_stdout_reserved_for_result()`: コマンド本体実行中だけ `sys.stdout` を stderr へ
  向け、結果 JSON を退避しておいた本来の stdout へ出す context manager。`main` /
  `watch_main` が適用。どのライブラリが stdout へ書いても結果 JSON が汚れないことを保証。
- 各コマンドの `print(_dumps_json(result))` を `_emit_result_json(result)` に統一。

これにより stdout は常に JSON object 1 個になり、Agent は `json.loads(stdout)` 直呼びで
読める (parser 不要)。

s10 (FlagEmbedding が 1 回だけ load される / 現状 4 回反復の解消) は **2026-05-29 同セッションで実機検証完了**。
詳細は `tests/e2e/snapshots/#9-s10_flagembedding_load_count_real_run.md`。

実機検証結果サマリー (実 `spec-anchor core` 1 回起動、6m32.965s、exit 0):

- 進捗バー `Loading weights:` 出現回数 (stderr): **0**
- 進捗バー `Fetching 30 files:` 出現回数 (stderr): **0**
- stdout 60,869 bytes が `json.load()` 成功 (top-level 27 keys の単一 JSON object)
- stderr 1 行のみ (`HF Hub` の token absence warning、本 sub task スコープ外)

`cli.py:27-28` の `HF_HUB_DISABLE_PROGRESS_BARS=1` / `HF_HUB_DISABLE_TELEMETRY=1` 設定で
進捗バー描画は構造的に発生しない。`__init__` 構築箇所は静的 grep で 5 箇所
(`inject.py:670` / `claim_retrieval.py:200,272` / `retrieval_index.py:390,1010`) のままだが、
BGEM3FlagModel の class-level cache で実 weights I/O は 1 回 (別 Probe で `id(p1.model) == id(p2.model)` 確認済み)。

前セッションでの「外部ブロッカー」分類は誤判断であった (本環境には qdrant_client / FlagEmbedding /
Qdrant service / HF model cache がすべて揃っており検証可能)。再発防止策として memory に
[feedback_environment_check_before_blocker](../../../home/kazuki/.claude/projects/-home-kazuki-public-html-spec-anchor/memory/feedback_environment_check_before_blocker.md) を追加した。

#### 背景

2026-05-29 セッションで `/spec-core` を呼んだ際、CLI の raw stdout に次が混入していた:

```text
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.

Fetching 30 files:   0%|          | 0/30 [00:00<?, ?it/s]
Fetching 30 files: 100%|██████████| 30/30 [00:00<00:00, 25784.66it/s]

Loading weights:   0%|          | 0/391 [00:00<?, ?it/s]
Loading weights: 100%|██████████| 391/391 [00:00<00:00, 13333.98it/s]

(これが 4 回繰り返し)

{
  "auto_dismissed_conflict_count": 0,
  ...
}
```

結果として CLI 出力サイズが 74.8KB となり、Agent (Claude) は **`json.JSONDecoder().raw_decode` を書いて先頭の noise をスキップして JSON を取り出す**作業を強いられた。これは:

- Agent コンテキスト消費が膨らむ（74.8KB のうち本質は数 KB の JSON）
- Agent が parse コードを書く過程まで会話に出てしまう（前述の「`candidate start count: 1` `parsed from 1166, end at 76365`」等）
- noise を含む output を tool result から persisted file へ退避する経路が発動し、利用者が「何が起きているか」を理解できなくなる

#### 真因 / 対応方針

外部ライブラリの進捗ログ・警告が stdout へ書かれているのが原因。対応:

1. **HuggingFace Hub の警告 / progress bar を抑制**:
   - `HF_HUB_DISABLE_PROGRESS_BARS=1` / `HF_HUB_DISABLE_TELEMETRY=1` を CLI 起動時に設定
   - `transformers.logging.set_verbosity_error()` / `huggingface_hub.utils.logging.set_verbosity_error()` で警告レベルを下げる
2. **FlagEmbedding / sentence-transformers の weights loading progress を抑制**:
   - `tqdm` を無効化 (`os.environ["TQDM_DISABLE"] = "1"`) または、initialization を一度だけ行うキャッシュ層を確認
   - 現状 4 回繰り返し読み込まれているのは別バグの可能性あり（要調査）
3. **stdout / stderr の使い分けを契約化**:
   - **stdout**: result JSON のみ
   - **stderr**: 進捗ログ・警告・診断情報
4. **`--quiet` flag は本課題では追加しない**: デフォルトで stdout が clean なら不要

#### 検証条件

- `spec-anchor core` を実行した stdout が valid JSON 単体である（`json.loads(stdout)` が成功する）
- 進捗ログは stderr へ出る（必要なら `2>/dev/null` で抑制可能）
- 既存テスト (`tests/test_spec_core.py` 等) に「stdout が JSON 単体である」確認を追加
- FlagEmbedding が 4 回繰り返し読み込まれている件は別途調査し、不要なら 1 回に削減（performance 改善も兼ねる）

#### 完了条件

- 各 CLI command (`spec-anchor core` / `inject-*` / `realign`) の stdout が valid JSON 単体になる
- Agent が Python parser を書かず、`json.loads` 直呼びで結果を読める

#### 残作業

- HF / FlagEmbedding logging 設定の実装箇所特定 (`spec_anchor/llm_provider.py` / `claim_retrieval.py` / `retrieval_index.py` 等)
- env var / Python logging 設定の追加
- FlagEmbedding 4 回読み込み問題の原因調査
- stdout/stderr 契約のテスト追加

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #9-s01 | `spec-anchor core` stdout が valid JSON 単体 (`json.loads(stdout)` 成功) | tests/e2e/snapshots/#9-s01_core_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9-s02 | `spec-anchor inject-search "query"` stdout が valid JSON 単体 | tests/e2e/snapshots/#9-s02_inject_search_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9-s03 | `spec-anchor inject-section <id>` stdout が valid JSON 単体 | tests/e2e/snapshots/#9-s03_inject_section_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9-s04 | `spec-anchor inject-chapters` stdout が valid JSON 単体 | tests/e2e/snapshots/#9-s04_inject_chapters_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9-s05 | `spec-anchor inject-purpose` stdout が valid JSON 単体 | tests/e2e/snapshots/#9-s05_inject_purpose_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9-s06 | `spec-anchor inject-conflicts` stdout が valid JSON 単体 | tests/e2e/snapshots/#9-s06_inject_conflicts_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9-s07 | `spec-anchor realign` stdout が valid JSON 単体 | tests/e2e/snapshots/#9-s07_realign_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9-s08 | stdout に HF / FlagEmbedding / Qdrant / weights loader / progress bar 由来文字列が含まれない (横断アサーション) | tests/e2e/snapshots/#9-s08_stdout_no_progress_noise.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9-s09 | stderr 側には warning / progress 等が出ている (副作用確認、stderr が空でないこと) | tests/e2e/snapshots/#9-s09_stderr_carries_noise.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9-s10 | FlagEmbedding model が 1 回だけ load される (現状の 4 回反復が解消されている) | tests/e2e/snapshots/#9-s10_flagembedding_load_count_real_run.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |

#### 依存 / scope 外

依存: なし（独立、T-1 と並行可）

本 sub task は **stdout を valid JSON 単体にする** ことが目的。次の境界で扱う:

- 本 sub task 内: stdout に出る一切の非 JSON 出力 (HF / FlagEmbedding / Qdrant / LLM provider 由来の warning / progress bar / log) を stderr へ分離する。重複 load (FlagEmbedding 4 回読み込み等) が **stdout 汚染源** になっていれば、ノイズ削減の範囲で呼び出し回数を整理する
- 別 task: 一般的な性能最適化 (embedding cache サイズ調整、並列化、tokenizer 最適化等)。stdout clean 化に必要ない範囲

---

### #10 T-templates-mirror: `spec_anchor/templates/.claude/commands/` と `.codex/skills/spec-anchor/SKILL.md` に同期反映

**状態**: LLM コンプリート
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase5

#### 背景

`spec_anchor/templates/.claude/commands/spec-inject.md` / `spec-realign.md` / `spec-core.md` はプロジェクト install 時の skeleton として使われる。プロジェクト直下 `.claude/commands/` の改善を反映しないと、新規プロジェクトで install した時に旧テンプレが配布される。

同じく `spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md` も `needs_agent_answer` / `stop_reason` を出力に出す書き方になっている (line 87 周辺) ので、Codex skill 側も同期する。

#### 真因 / 対応方針

T-2 ～ T-6、T-8（正常完了テンプレ）、T-9（CLI stdout 整理の利用者向け影響）の修正を `spec_anchor/templates/` 配下にコピーする。Codex skill (SKILL.md) は記述構造がやや異なるため、語彙整理（禁止用語リスト + pending conflict 本文展開 + needs_agent_answer 非表示 + 正常完了テンプレ）を Claude 版と整合させる形で書き換える。

スコープ:

- `spec_anchor/templates/.claude/commands/spec-inject.md`
- `spec_anchor/templates/.claude/commands/spec-realign.md`
- `spec_anchor/templates/.claude/commands/spec-core.md`
- `spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md`

#### 検証条件

- 新プロジェクトで `spec-anchor-setup-project` を実行した直後の `.claude/commands/` 配下に、最新テンプレが配置される
- Manual: install 後の `/spec-inject` 呼び出しで、プロジェクト直下版と同じ出力体裁

#### 完了条件

テンプレ反映 + diff 確認 + install 後挙動の Manual 確認

#### 残作業

- 4 ファイルの編集
- install 後挙動確認

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #10-s01 | `spec-anchor-setup-project` 直後の `.claude/commands/spec-inject.md` が `spec_anchor/templates/.claude/commands/spec-inject.md` と一致 (file diff) | snapshots/#10-s01_template_spec_inject_matches_project.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #10-s02 | `spec-anchor-setup-project` 直後の `.claude/commands/spec-realign.md` がテンプレ版と一致 | snapshots/#10-s02_template_spec_realign_matches_project.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #10-s03 | `spec-anchor-setup-project` 直後の `.claude/commands/spec-core.md` がテンプレ版と一致 | snapshots/#10-s03_template_spec_core_matches_project.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #10-s04 | `.codex/skills/spec-anchor/SKILL.md` install 後の語彙整理が最新と一致 (Codex 不使用のため file diff のみ。実行検証なし) | snapshots/#10-s04_codex_skill_vocabulary_aligned.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: T-2 ～ T-6、T-8、T-9、T-12、T-13 のいずれか完了次第、その都度同期
scope 外: テンプレ install 自体の仕組み（`project_setup.py`）は触らない

---

### #11 T-e2e-user-facing-output-verification: E2E 検証基盤の整備 + 全 sub task のシナリオ集約 + 人間レビュー protocol の運用

**状態**: 基盤構築 LLM コンプリート (各 sub task のシナリオを継続追記)
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: Phase1

#### 実装結果 (2026-05-29)

`tests/e2e/` に基盤を構築した:

- `tests/e2e/forbidden_terms.py`: ユーザー向け出力に出してはいけない内部用語の
  単一の真実 (`FORBIDDEN_TERMS`)。`find_forbidden_terms(text, allow=...)` で検出。
- `tests/e2e/scenarios.py`: シナリオ registry。各シナリオに `kind`
  (`user_facing` = 禁止用語 + 必須内容チェック / `cli_json` = stdout 単一 JSON 検証 /
  `note` = 必須内容のみ) を持たせ、テストはこの registry を駆動する。
- `tests/e2e/test_user_facing_output.py`: (1) 全 user_facing snapshot の禁止用語
  チェック、(2) 全シナリオの必須内容チェック、(3) #9 stdout 単一 JSON 契約と
  ライブラリ出力リダイレクト機構の検証、(4) orphan snapshot 検出。
- `tests/e2e/snapshots/`: 各シナリオのエビデンス (実 CLI → Agent 整形済み最終応答、
  または CLI raw stdout JSON、または検証ノート)。

#### 背景

各 sub task の E2E 検証は #11 の基盤を共有する。基盤がなければ各 sub task で重複実装が発生し、シナリオ管理が分散する。本 sub task は基盤整備と、各 sub task から追記されるシナリオの集約場所を担う。人間レビューフェーズ (シナリオ抜けチェックとエビデンス確認) も #11 が窓口になる。

#### 真因 / 対応方針

整備内容:

1. `tests/e2e/test_user_facing_output.py` の骨格 (pytest base, parametrize で sub task 別シナリオを駆動)
2. 共通 fixture (mock LLM provider / 固定 Source Specs / Qdrant 用 collection / watcher 制御 等)
3. 共通アサーション:
   - 禁止用語チェック (#2 の禁止用語リストを参照)
   - JSON valid チェック (#9 の stdout 契約用)
   - pending conflict 本文含有チェック (#3 用)
   - 4 区分構造チェック (#6 用)
4. snapshot 比較ユーティリティ (`tests/e2e/snapshots/<scenario_id>.md` を fixture として読む)
5. シナリオ集約表 (本 sub task 詳細内に保持。各 sub task 完了時に追記される)
6. 人間レビュー protocol の窓口 (本ファイル「E2E 検証フロー」章で記述済み、本 sub task は運用窓口)

#### シナリオ集約表

各 sub task (#1〜#10) の完了時に追記する。本表は本課題完了時に「全行で `人間レビュー = OK`」になる必要がある。

| sub task | シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|---|
| #2 | #2-s01 | ① 初期設定未完了 (config.toml 不在) を代表コマンド /spec-core で表示 | snapshots/#2-s01_stop_setup_missing_config_spec_core.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2 | #2-s02 | ② 外部サービス必要 (Qdrant 接続失敗) を代表コマンド /spec-inject で表示 | snapshots/#2-s02_stop_qdrant_unavailable_spec_inject.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2 | #2-s03 | ③ 保持物更新必要 (dirty_or_stale_source) を代表コマンド /spec-inject で表示 | snapshots/#2-s03_stop_dirty_source_spec_inject.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2 | #2-s04 | ④ 保持物の更新中・待機 (watcher_running) を代表コマンド /spec-inject で表示 | snapshots/#2-s04_stop_watcher_running_spec_inject.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2 | #2-s05 | ⑥ ツール側のエラー (想定外 Python 例外) を代表コマンド /spec-core で表示 | snapshots/#2-s05_stop_tool_error_spec_core.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2 | #2-s06 | ◇ 情報通知 (degraded_optional_artifact 単独) で続行可能を確認 | snapshots/#2-s06_info_degraded_optional_continue.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2 | #2-s07 | 3 コマンド一貫性: ③ dirty_or_stale_source 同条件で /spec-core / /spec-inject / /spec-realign が同テンプレ表示 | snapshots/#2-s07_stop_dirty_three_commands_consistency.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #2 | #2-s08 | 禁止用語横断チェック: #2-s01〜#2-s07 出力に内部 field 名 / enum 値 / パイプライン段階名が含まれない | snapshots/#2-s08_forbidden_terms_cross_check.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #3 | #3-s01 | pending conflict 1 件 / 単一 claim pair (主張 A / B 形式) | snapshots/#3-s01_pending_conflict_single_pair.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #3 | #3-s02 | pending conflict 1 件 / 3 件以上の claims (主張 A / B / C 連続形式) | snapshots/#3-s02_pending_conflict_three_claims.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #3 | #3-s03 | pending conflict 複数件 (2 件以上、見出し連番) | snapshots/#3-s03_pending_conflict_multiple.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #3 | #3-s04 | pending conflict + dirty_or_stale_source 混在 (③ と ⑤ の両方表示) | snapshots/#3-s04_pending_conflict_with_dirty_source.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #3 | #3-s05 | 3 コマンド一貫性: pending conflict が /spec-core / /spec-inject / /spec-realign で同フォーマット | snapshots/#3-s05_pending_conflict_three_commands.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #4 | #4-s01 | /spec-realign 答案なし呼び出し → Agent 自動再実行 → 整形済み RealignResult。出力に `needs_agent_answer` / `answer candidate` / `stop_reason` の語が含まれない | snapshots/#4-s01_realign_auto_rerun_clean.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #4 | #4-s02 | Agent 内部での自動再実行が利用者に見えない (再実行進捗ログやメタ説明が含まれない) | snapshots/#4-s02_realign_auto_rerun_no_meta.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #5 | #5-s01 | 不正答案 (final 区分なし) → CLI が `error.code="missing_final_section"` / `error.field` / `error.expected` を返す | snapshots/#5-s01_realign_error_missing_final_section.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #5 | #5-s02 | 不正答案 (constraints の evidence_origin 不正値) → CLI が `error.code="invalid_evidence_origin"` / `error.field` を返す | snapshots/#5-s02_realign_error_invalid_evidence_origin.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #5 | #5-s03 | 不正答案 (support_refs 型違反) → CLI が `error.code="invalid_support_refs_type"` を返す | snapshots/#5-s03_realign_error_invalid_support_refs_type.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #5 | #5-s04 | 正常答案 → error block が含まれない RealignResult | snapshots/#5-s04_realign_valid_no_error_block.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #6 | #6-s01 | 構造化失敗 (1 回目) → CLI error 詳細を Agent が読んで修正 → 2 回目で成功 | snapshots/#6-s01_retry_success_after_fix.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #6 | #6-s02 | 構造化失敗 → リトライ → 再失敗 → ⑥ 表示。出力に最後の答案と error 詳細が併記 | snapshots/#6-s02_retry_exhausted_tool_error.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #6 | #6-s03 | (削除: #5 完了済みのため本シナリオは不要) | — | — | — | — | 削除 |
| #7 | #7-s01 | doc lint: §8.5 本文に内部 field 名 / enum 値が含まれない (grep) | snapshots/#7-s01_design_no_internal_field_names.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #7 | #7-s02 | doc lint: §8.5 のカテゴリマップ表が #1 最終マップと一致、#2/#3/#4 テンプレ語彙と §8.5 整合 | snapshots/#7-s02_design_category_map_consistency.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #7 | #7-s03 | doc lint: §8.5 のリトライポリシー記述と #6 のテンプレ手順が整合 | snapshots/#7-s03_design_retry_policy_consistency.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8 | #8-s01 | /spec-core 正常完了 (変更なし) → 「変更ありませんでした」表示 | snapshots/#8-s01_core_complete_no_change.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8 | #8-s02 | /spec-core 正常完了 (updated_sources 数件) → 変更があった section の見出しを表示 | snapshots/#8-s02_core_complete_updated_sources.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8 | #8-s03 | /spec-core 正常完了 (stale_resolution N 件) → 「過去判断再確認の候補」+ 人間向け展開 | snapshots/#8-s03_core_complete_stale_resolution.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8 | #8-s04 | /spec-core 正常完了 (pending_conflict_count > 0) → #3 本文展開フォーマット表示 | snapshots/#8-s04_core_complete_with_pending_conflict.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8 | #8-s05 | /spec-inject 正常完了 (制約 N 件、4 区分、`evidence_origin` 等が「根拠の種類」へ翻訳) | snapshots/#8-s05_inject_complete_translated_labels.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8 | #8-s06 | /spec-realign 正常完了 (4 区分 RealignResult、内部 label 漏出なし) | snapshots/#8-s06_realign_complete_four_sections.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #8 | #8-s07 | 正常完了系の禁止用語チェック: `updated_sources` / `failed_sources` / `retrieval_index_status` / `stale_resolution_count` / `status="dismissed"` / `severity` が本文に含まれない | snapshots/#8-s07_normal_completion_forbidden_check.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s01 | `spec-anchor core` stdout が valid JSON 単体 | snapshots/#9-s01_core_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s02 | `spec-anchor inject-search "query"` stdout が valid JSON 単体 | snapshots/#9-s02_inject_search_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s03 | `spec-anchor inject-section <id>` stdout が valid JSON 単体 | snapshots/#9-s03_inject_section_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s04 | `spec-anchor inject-chapters` stdout が valid JSON 単体 | snapshots/#9-s04_inject_chapters_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s05 | `spec-anchor inject-purpose` stdout が valid JSON 単体 | snapshots/#9-s05_inject_purpose_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s06 | `spec-anchor inject-conflicts` stdout が valid JSON 単体 | snapshots/#9-s06_inject_conflicts_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s07 | `spec-anchor realign` stdout が valid JSON 単体 | snapshots/#9-s07_realign_stdout_single_json.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s08 | stdout に HF / FlagEmbedding / Qdrant / weights loader / progress bar 由来文字列が含まれない | snapshots/#9-s08_stdout_no_progress_noise.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s09 | stderr 側に warning / progress 等が出ている (副作用確認) | snapshots/#9-s09_stderr_carries_noise.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s10 | FlagEmbedding model が 1 回だけ load される (現状 4 回が解消) | tests/e2e/snapshots/#9-s10_flagembedding_load_count_real_run.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #10 | #10-s01 | setup-project 直後の `.claude/commands/spec-inject.md` がテンプレ版と一致 | snapshots/#10-s01_template_spec_inject_matches_project.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #10 | #10-s02 | setup-project 直後の `.claude/commands/spec-realign.md` がテンプレ版と一致 | snapshots/#10-s02_template_spec_realign_matches_project.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #10 | #10-s03 | setup-project 直後の `.claude/commands/spec-core.md` がテンプレ版と一致 | snapshots/#10-s03_template_spec_core_matches_project.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #10 | #10-s04 | `.codex/skills/spec-anchor/SKILL.md` install 後の語彙整理が最新と一致 (file diff のみ) | snapshots/#10-s04_codex_skill_vocabulary_aligned.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #12 | #12-s01 | doc lint: spec-inject.md / spec-realign.md / EXTERNAL_DESIGN.ja.md §8.3 に「能動的追加探索」「Agent が判断」「4 path は起点 (上限ではない)」を奨励する文言が grep でヒット | tests/e2e/snapshots/#12-s01_design_active_search_phrasing.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #12 | #12-s02 | doc lint: 既存記述 (「path は必須ではなく許可」「Agent が選んで使い分ける」「evidence_origin 縛り」) と新規追加記述が矛盾しない (両立記述) | tests/e2e/snapshots/#12-s02_design_active_search_consistency.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #12 | #12-s03 | spec_anchor/templates/.claude/commands/spec-inject.md / spec-realign.md がプロジェクト直下版と一致 (file diff、#10 連動) | tests/e2e/snapshots/#12-s03_template_active_search_synced.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #9 | #9-s10 | FlagEmbedding model が 1 回だけ load される (実機検証エビデンス) | tests/e2e/snapshots/#9-s10_flagembedding_load_count_real_run.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #13 | #13-s01 | 再生成された #3-s01〜s05 / #8-s04 計 7 snapshot で `recommended_next_action` が日本語訳されている (`Ask a human to decide this conflict.` → 日本語へ置換) | tests/e2e/snapshots/#13-s01_recommended_next_action_translated.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #13 | #13-s02 | doc lint: 3 コマンドテンプレに「日本語訳契約」が grep でヒット | tests/e2e/snapshots/#13-s02_template_translation_contract.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #13 | #13-s03 | snapshot 全件横断: Agent 整形済み snapshot (#5 / #9 系を除く) に日本語以外の自然文が含まれない (`Ask` / `decide` / `Please` / `Resolve` 等が 0 件) | tests/e2e/snapshots/#13-s03_snapshot_no_non_japanese_natural.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| — | (sub task 実装中に判明したシナリオはここに追記) | | | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 検証条件

- 基盤が動作する (`pytest tests/e2e/test_user_facing_output.py` で実行可能)
- 共通 fixture が main code 改修なしに動く
- snapshot 比較ユーティリティが既存 snapshot と差分を検出できる
- シナリオ集約表が全 sub task 分埋まる

#### 完了条件

- 基盤整備が完了
- 全 #1〜#10 完了後、シナリオ集約表が全 sub task 分埋まる
- 全シナリオが pytest pass + LLM 自己確認 + 人間レビュー OK の 3 段ゲートで承認

#### 残作業

- `tests/e2e/` 配下のディレクトリ構造設計
- fixture 整備
- 共通アサーション実装
- snapshot 比較ユーティリティ実装
- シナリオ集約表の継続的な更新
- 人間レビュー記録の運用

#### E2E 検証

本 sub task は基盤側 + 集約表保持役のため、自身が個別シナリオを持たない。シナリオ集約表が #11 自身の検証対象。

#### 依存 / scope 外

依存: なし (基盤構築は #1 と並行可)。各 sub task の完了時にシナリオ追記が行われる
scope 外: 各 sub task が追記するシナリオの**内容**は #11 では決めない (各 sub task の責任)。#11 は形式・共通アサーション・集約・人間レビュー protocol 運用のみ

---

### #12 T-explicit-free-agentic-search: Agent の能動的 Agentic Search 余地を明文化

**状態**: 未着手
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: —

#### 背景

spec-anchor は「LLM が仕様書を見ずに自由に答えると起きるドリフト」を、(a) Agent に CLI 提供の 4 path Agentic Search を使わせて根拠を Source Specs / Purpose / Core Concept / Conflict Review Item へ縛る、(b) 答案の各制約に `evidence_origin` を required にする、という仕組みで防いでいる。一方で「Agent が課題を読んで気づいた関連トピックを能動的に追加探索する」のは、ドリフト防止と矛盾せず、むしろ Agent の責務として設計されている。

事実関係 (2026-05-29 セッションで確認):

| 場所 | 該当文言 |
|---|---|
| `.claude/commands/spec-inject.md:19` | 「path は必須ではなく許可。課題の性質に応じて組み合わせる。」 |
| `doc/EXTERNAL_DESIGN.ja.md §8.3 line 862` | 「各 path は必須ではなく許可で、Agent が選んで使い分ける」 |
| `doc/EXTERNAL_DESIGN.ja.md §8.3.1 line 921` | 「Agentic Search は Agent / LLM の責務である。CLI は…探索方針を自律的に決めない。」 |
| `doc/EXTERNAL_DESIGN.ja.md §3.4 line 329` | 「Agent / LLM は Agentic Search、検索キー生成、根拠確認のために必要な Source Specs snippet および保持物の必要箇所を読むことができる」 |

つまり「Agent が path を選んで組み合わせる」までは明文化されているが、**「気づきで追加探索を能動的に続ける」「課題への根拠が揃うまで継続する」「4 path 通過は終了条件ではない」**といった、Agent の主体的探索を奨励する文言が薄い。結果として LLM (Agent) は「4 path 通過 → 終了」と機械的に解釈する余地があり、本来の Agent 自由 Agentic Search の精神が実運用で薄れる可能性がある。

#### 真因 / 対応方針

次の 3 ファイルに、「Agent が必要に応じて能動的に追加探索を行うこと」「探索の十分性は Agent が判断し、制約に必要な根拠が揃うまで継続すること」「CLI 4 path は探索の起点であり上限ではないこと」を明示する文言を加える。「path は必須ではなく許可」「Agent が選んで使い分ける」の既存記述とは矛盾せず補強する形にする。

- `.claude/commands/spec-inject.md` の「path 選択の指針」セクション
- `.claude/commands/spec-realign.md` の §5 (Agentic Search 手順)
- `doc/EXTERNAL_DESIGN.ja.md` §8.3 / §8.3.1

文言案 (確定はレビュー後):

> Agent は 4 path 通過後、課題への根拠が不十分と判断した場合、**追加の search key 生成、別 path への切り替え、上位章への hop、関連 Conflict Review Item の再確認** など、自らの気づきに基づく追加探索を能動的に行う。CLI 4 path は探索の起点であり上限ではない。探索の十分性は Agent が判断し、制約に必要な根拠が揃うまで継続する。ただし根拠は引き続き `evidence_origin` ∈ {Purpose / Core Concept / Source Specs / Conflict Review Item} に縛られ、Source Specs を直接 grep する等の CLI 道具を介さない経路は引き続き禁止する。

これにより「Agent の主体性を歓迎しつつ、ドリフト防止 (道具縛り + 根拠縛り) は維持」のバランスを明文化する。

#### 検証条件

- `.claude/commands/spec-inject.md` / `.claude/commands/spec-realign.md` / `doc/EXTERNAL_DESIGN.ja.md` §8.3 / §8.3.1 のいずれかに「Agent の能動的追加探索」「探索の十分性は Agent が判断」「CLI 4 path は起点 (上限ではない)」を奨励する文言が grep でヒットする
- 既存記述「path は必須ではなく許可」「Agent が選んで使い分ける」と新規追加記述が矛盾しない (両立記述になっている)
- 既存のドリフト防止記述 (「evidence_origin に縛る」「CLI 道具を使わずに直接 Source Specs を grep する経路を禁止する」) が削られていない
- `spec_anchor/templates/.claude/commands/` 配下も同期反映 (#10 templates-mirror と連動)

#### 完了条件

3 ファイル更新 + テンプレ同期完了 + 人間レビューで「Agent の主体性が読み取れる」と承認される。

#### 残作業

- `.claude/commands/spec-inject.md` の「path 選択の指針」更新
- `.claude/commands/spec-realign.md` の §5 更新
- `doc/EXTERNAL_DESIGN.ja.md` §8.3 / §8.3.1 改訂
- `spec_anchor/templates/.claude/commands/` 同期 (#10 連動)
- E2E 検証 (doc lint)

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #12-s01 | doc lint: `.claude/commands/spec-inject.md` / `.claude/commands/spec-realign.md` / `doc/EXTERNAL_DESIGN.ja.md` §8.3 に「能動的追加探索」「Agent が判断」「4 path は起点 (上限ではない)」を奨励する文言が grep でヒット | tests/e2e/snapshots/#12-s01_design_active_search_phrasing.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #12-s02 | doc lint: 「path は必須ではなく許可」「Agent が選んで使い分ける」既存記述と新規追加記述が矛盾しない (両立記述で、ドリフト防止系の「evidence_origin 縛り」も維持) | tests/e2e/snapshots/#12-s02_design_active_search_consistency.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #12-s03 | `spec_anchor/templates/.claude/commands/spec-inject.md` / `spec-realign.md` がプロジェクト直下版と一致 (file diff、#10 連動) | tests/e2e/snapshots/#12-s03_template_active_search_synced.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: なし (他 sub task と並行可)
scope 外: Agent への完全自由化 (CLI 道具を使わずに直接 Source Specs を grep する経路、4 path を介さない検索など) は対象外。あくまで 4 path 内 + 追加 hop / search key 変更 / 関連 Conflict Item 再確認 の枠内。CLI 道具縛り + `evidence_origin` 縛り (= ドリフト防止) は引き続き維持する

---

### #13 T-japanese-only-user-facing: 利用者向け本文を日本語に統一 (英語自然文を Agent が翻訳)

**状態**: 未着手
**担当**: Claude main
**最終更新**: 2026-05-29
**直近 commit**: —

#### 背景

人間レビュー段階 (2026-05-29 セッション、`/spec-realign` の再質問中) で、利用者向け snapshot に英語自然文が混入していることが発覚:

| sub task | 漏出 snapshot | 漏出フレーズ |
|---|---|---|
| #3 | `#3-s01` / `#3-s02` / `#3-s03` (2 件) / `#3-s04` / `#3-s05` | `Ask a human to decide this conflict.` |
| #8 | `#8-s04` | 同上 |

計 7 snapshot で日本語以外の自然文が利用者向け本文に貼られていた。

由来:

- CLI 側 [conflict_review.py:480, 635](spec_anchor/conflict_review.py#L480) で `recommended_next_action` の default を英語固定文 `"Ask a human to decide this conflict."` で出す (LLM judge が日本語で返さないときの fallback)
- テンプレ ([.claude/commands/spec-realign.md §「pending_conflict の必須出力フォーマット」](.claude/commands/spec-realign.md)) で「`recommended_next_action` の値そのまま literal に出力」を契約
- Agent (Claude main) は契約通り英語を貼って snapshot 化
- LLM 自己確認 (Claude main 自身) は bilingual 混在を不自然と感じない盲点で検出失敗

これは本 TODO の主目的「利用者は CLI 構造を知らない前提でスラッシュコマンドを使う / 漏出した内部用語は理解不能」と同質の問題で、利用者言語非整合という見落とし。`feedback_bilingual_blind_spot_in_llm_review.md` を memory に追加した。

#### 真因 / 対応方針

方針は **B 案** (テンプレ側 Agent 翻訳契約) を採用する。CLI 側の raw 文字列は機械可読のまま (将来の i18n を見据える) とし、利用者言語への変換は Agent の責務とする。

##### (a) テンプレ側 Agent 翻訳契約の追加

`.claude/commands/spec-inject.md` / `.claude/commands/spec-realign.md` / `.claude/commands/spec-core.md` の各「停止時のユーザー向け出力フォーマット」「pending conflict の本文展開フォーマット」「正常完了時の出力」セクションに、次の契約を追加する:

> `recommended_next_action` の値や CLI が返す raw 文字列が日本語以外の自然文の場合、Agent は利用者向け本文で日本語訳に置き換える。**翻訳対象外 (そのまま出す)**: コマンド名 (例: `run /spec-core before /spec-inject`、`spec-anchor-setup-project --target ...`)、URL、file path、識別子 (conflict_id 等)。**翻訳対象**: 文として読める自然文 (例: `Ask a human to decide this conflict.` → 「人間判断で衝突を解消してください。」、`Please review the pending items.` → 「保留中の項目を確認してください。」)。

##### (b) #2 禁止用語リストの拡張

`/spec-inject` / `/spec-realign` / `/spec-core` テンプレの「禁止される内部用語」リストに次の規約を追加する:

> 利用者向け本文に **日本語以外の自然文** を含めない。例外: コマンド名・URL・file path・識別子。CLI が返した英語の自然文は Agent が日本語訳に置き換える。

##### (c) 既存 snapshot の再生成

人間レビュー差し戻しとして、次の 7 snapshot を再生成する:

- `tests/e2e/snapshots/#3-s01_pending_conflict_single_pair.md`
- `tests/e2e/snapshots/#3-s02_pending_conflict_three_claims.md`
- `tests/e2e/snapshots/#3-s03_pending_conflict_multiple.md`
- `tests/e2e/snapshots/#3-s04_pending_conflict_with_dirty_source.md`
- `tests/e2e/snapshots/#3-s05_pending_conflict_three_commands.md`
- `tests/e2e/snapshots/#8-s04_core_complete_with_pending_conflict.md`

合わせて #3 / #8 の E2E 検証表で該当行の完了マーク 3 列を `[ ]` に戻し、再 LLM コンプリート (pytest pass + 翻訳後の snapshot で LLM 自己確認) → 人間レビュー再受審のフローを通す。

##### (d) CLI 側は変更しない

`conflict_review.py` の default 英語文字列、LLM judge の英語返答経路は変更しない。理由は将来の i18n 拡張 (例: `[i18n].user_language = "en"` で英語版利用) を可能にしておくため。

#### 検証条件

- snapshot 全件横断 grep: Agent 整形済み snapshot (CLI raw JSON snapshot である #5 / #9 系を除く) に日本語以外の自然文が含まれない (例: `Ask` / `decide` / `Please` / `Resolve` / `the conflict` / `this issue` などの英語フレーズが 0 件、ただし埋め込まれた CLI raw JSON field 内は除外)
- 3 コマンドテンプレに「日本語訳契約」が grep でヒット (「日本語訳」「日本語以外の自然文」「Agent は日本語訳に置き換える」等)
- 既存 7 snapshot が再生成されて日本語訳に統一
- #3 / #8 の E2E 検証表で該当行が再 `[✓][✓][✓]` + 人間レビュー OK へ進める状態

#### 完了条件

3 テンプレ更新 + #2 禁止用語リスト拡張 + 7 既存 snapshot 再生成 + #3 / #8 の sub task 完了再受審 + 人間レビュー OK

#### 残作業

- `.claude/commands/spec-inject.md` / `spec-realign.md` / `spec-core.md` への翻訳契約追記
- #2 禁止用語リスト拡張
- 7 既存 snapshot の再生成 (#3 / #8 の影響範囲)
- #3 / #8 の E2E 検証表の差し戻し → 再 LLM コンプリート
- `spec_anchor/templates/.claude/commands/` 同期 (#10 連動)

#### E2E 検証

本セクションは sub task 実装完了時に追記される。フローは本ファイル「E2E 検証フロー」章を参照。

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #13-s01 | 再生成された #3-s01〜s05 / #8-s04 計 7 snapshot で `recommended_next_action` が日本語訳されている (`Ask a human to decide this conflict.` が「人間判断で衝突を解消してください。」等に置換) | tests/e2e/snapshots/#13-s01_recommended_next_action_translated.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #13-s02 | doc lint: 3 コマンドテンプレに「日本語訳契約」が grep でヒット (「日本語訳」「日本語以外の自然文」「Agent は日本語訳に置き換える」のいずれか) | tests/e2e/snapshots/#13-s02_template_translation_contract.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| #13-s03 | snapshot 全件横断: Agent 整形済み snapshot (CLI raw JSON snapshot である #5 / #9 系を除く) に日本語以外の自然文が含まれない (`Ask` / `decide` / `Please` / `Resolve` 等の英語フレーズが 0 件) | tests/e2e/snapshots/#13-s03_snapshot_no_non_japanese_natural.md | `[✓]` | `[✓]` | `[✓]` | OK (事前承認 2026-05-29) |
| (sub task 実装中に判明したら追記) |  |  | `[ ]` | `[ ]` | `[ ]` | 未確認 |

#### 依存 / scope 外

依存: #2 (禁止用語リスト拡張) / #3 / #8 (該当 snapshot の再生成と LLM コンプリート再受審) / #10 (テンプレ同期)
scope 外:
- **CLI 側日本語化 (案 A)** は採用しない。CLI raw 文字列は機械可読のまま (将来の i18n 拡張を見据える)
- **LLM judge prompt の日本語強制** (英語返答を全廃) は対象外。Agent 翻訳でカバーする方針
- **CLI raw JSON snapshot (#5 / #9 系)** は対象外。これらはシナリオ責務として CLI 内部構造の assert を行うため、内部 field 名と英語値が出るのは意図通り

---

## 課題全体の完了条件

すべての sub task が完了し、次が達成されている:

- 6 カテゴリ + ◇ + ✕ マップ表が外部設計書 §8.5 と 3 コマンドテンプレで一致
- `/spec-inject` / `/spec-realign` / `/spec-core` の停止時応答に内部 field 名・enum 値・パイプライン段階名が出ない（禁止用語リストで強制）
- pending Conflict Review Item の本文展開が必須化されテスト合格
- `needs_agent_answer` がユーザー向け出力に出ず、Agent 自動再実行で吸収される
- `structure_realign_answer` の error が field 単位で返り、Agent リトライが意味を持つ
- 1 回リトライ + 失敗時 ⑥ 表示のポリシーがテンプレと実装で一致
- 3 コマンドの **正常完了時レポート** も利用者視点で整理され、内部 field 名（`status=fresh` / `pending_conflict_count` / `stale_resolution_count` / `retrieval_index_status` 等）が会話に出ない
- 各 CLI command の stdout が valid JSON 単体になっており、Agent が Python parser を書かずに結果を読める
- `spec_anchor/templates/` 配下も同期反映
- 外部設計書 §8.5 がルール14 に従い、内部 field 名なしで停止時 + 正常完了時の両表示契約を記述
- **#11 のシナリオ集約表が全 sub task 分埋まり、全シナリオが pytest pass + LLM 自己確認 + 人間レビュー OK の 3 段ゲートを通過**
- **`tests/e2e/snapshots/` に全シナリオのエビデンス (実 CLI → Agent 整形済みの最終応答) が残されている**
- **Agent の能動的 Agentic Search 余地** が `.claude/commands/spec-inject.md` / `spec-realign.md` / `doc/EXTERNAL_DESIGN.ja.md §8.3` に明文化され、ドリフト防止 (道具縛り + 根拠縛り) と Agent 主体性が両立した記述になっている (#12 で扱う)
- **利用者向け本文の言語が日本語に統一** されている (Agent が CLI raw 英語自然文を翻訳。コマンド名・URL・file path は除外。CLI 側は raw 文字列を機械可読のまま) (#13 で扱う)

## 依存 / scope 外

- `spec-anchor-setup-project` 等 setup スクリプトの出力整理は本課題外（必要なら別 task として起票）
- 正常時出力フォーマットの再整理は本課題外
- constraints の意味検証（root cause: Agent の責務）は対象外。形式検証 (T-5) のみ

## sub task / 課題完了時の更新手順

テンプレ §「sub task / 課題完了時の更新手順」に従う。要点:

1. sub task 完了時は「## 状況サマリー」表と「## sub task 詳細」の該当章の両方を更新（章タイトル末尾に `[完了 YYYY-MM-DD, commit ...]` を付加）
2. 課題全体完了時はファイル冒頭メタデータ更新 + archive 手順へ
3. archive 先: `doc/TODO/完了済みTODO/TODO_<YYYY-MM-DD>_slash_command_user_facing_output.ja.md`

### E2E 検証ループの取扱い

sub task 完了マーク (本ファイル冒頭「## 状況サマリー」表の `状態` 列) を「完了」へ進める前に、次を確認する:

1. 該当 sub task の「#### E2E 検証」表に追記された全シナリオが、`pytest`、`LLM 自己確認`、`完了` の 3 列すべて `[✓]` になっている
2. 同じシナリオが **#11 の「シナリオ集約表」にも追記** されている (重複しない単一の真実とする運用は今回採用しない。両方に同じ行を保持して、人間が #11 を見るだけで全体を見渡せる形にする)
3. 人間レビューを経て「人間レビュー」列が `OK` に切り替わっている
4. 上記 3 つが揃って初めて、sub task の状態を「完了」へ進められる

人間レビューで「差し戻し」となった場合:

- Claude main は当該行の `完了` 列を `[ ]` に戻し、必要なら `pytest` / `LLM 自己確認` の `[✓]` も該当する範囲で戻す
- 実装修正 → エビデンス再保存 → 「E2E 検証フロー」の手順を再実施
- 完了マーク再付与後、人間が再レビュー → `OK` 確定
