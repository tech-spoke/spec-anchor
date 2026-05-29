---
description: SPEC-anchor の保持コンテキスト artifact を更新する
argument-hint: "[--all]"
allowed-tools: Bash(spec-anchor core:*)
---

# /spec-core

正本は SPEC-anchor の外部 command contract と SPEC-anchor CLI の入出力である。この Claude command template は、Agent がその契約をどう呼び出すかだけを示す。

すべての `spec-anchor` CLI 呼び出しは現在の作業ディレクトリ (cwd) を project root として実行する。親ディレクトリ、別プロジェクト、記憶にある他のパスを探索してはならない。`.spec-anchor/config.toml` の有無を事前確認して CLI 実行を省略してはならない。CLI を実行し、CLI が返すエラー JSON を利用者に伝達する。

project root で `spec-anchor core` を実行する。`--all` または `-a` は、ユーザーが full rebuild を明示した場合だけ追加する。`.spec-anchor/config.toml` の `[llm.stage_routing]` が H-4 calibration で確定した stage 別最適 model / effort (`section_metadata` / `related_sections` / `conflict_review` / `chapter_key_anchor`) を適用する。`--llm-provider` を明示すると stage_routing が上書きされるので、特別な事情がない限り指定しない。

`/spec-core` は SPEC-anchor の保持 artifact を生成または更新する: Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor、Source Retrieval Index、Conflict Review Items。

実行後は、CLI が返す CoreResult JSON を読み、後述「正常完了時のユーザー向け出力フォーマット」に従って整形して報告する。CoreResult の内部 field 名 (`updated_sources` / `failed_sources` / `retrieval_index_status` / `pending_conflict_count` / `stale_resolution_count` / `freshness_report` 等) はそのまま本文に貼らない。

pending Conflict Review Items が残る場合、件数だけでなく後述「pending conflict の本文展開フォーマット」で各衝突を本文展開する。pending conflict を Agent が決めない。

Purpose と Core Concept は人間が維持する read-only input である。この command から `/spec-inject` や `/spec-realign` を自動実行しない。CLI result と、人間判断が必要な pending Conflict Review Items を返す。

## 停止時のユーザー向け出力フォーマット

CLI が失敗を返したとき (返却 JSON の `status` が `failed` / `error`)、その JSON を次の **利用者視点カテゴリ** へ写像し、該当カテゴリの固定フォーマットだけを出力する。利用者は CLI の内部構造を知らない前提なので、内部 field 名・enum 値・パイプライン段階名は本文に出さない (後述「ユーザー向け本文に貼ってはいけない内部用語」)。`/spec-core` は保持物の更新コマンドなので ③ (保持物の更新が必要) ④ (更新中) ✕ (答案待ち) は通常発生せず、主に ① ② ⑤ ⑥ が該当する。

### 停止カテゴリ写像 (6 + ◇ + ✕)

左 2 列は判定のための内部状態であり **本文には出さない**。

| | 利用者向けの状況 | 内部状態 (本文に出さない) | 利用者が取る行動 |
|---|---|---|---|
| ① | 初期設定が完了していない | config.toml 不在 / `docs/core/purpose.md`・`core_concept.md` 不在 / `sources.include` 不一致 | `spec-anchor-setup-project` 実行、purpose / concept 作成、`[sources].include` 修正 |
| ② | 外部サービスへの接続が必要 | Qdrant 接続失敗 / Chapter Anchors の LLM 生成失敗 / Related Sections の retrieval backend 失敗 | サービス起動 / 接続情報の確認、`/spec-core --all` または `/spec-core --rebuild` で再試行 |
| ⑤ | 人間判断が必要な仕様の衝突 | pending conflict | 衝突を読んで採用案を決定 |
| ⑥ | ツール側のエラー | 想定外例外 / ①②⑤ に当てはまらない error (例: Source Retrieval Index の更新・検証失敗) | `/spec-core --rebuild` を試し、解消しなければ開発元へ報告 |
| ◇ | 情報通知 (続行可能) | 補助的保持物のみ劣化 (単独) | 認知のみ、無視可 |

### カテゴリ別フォーマット

該当カテゴリの固定見出しで出す。略称や存在しない command (`spec-anchor init` 等) は提案しない。

```text
① ■ 初期設定が完了していません

     プロジェクトの設定ファイル、Purpose / Core Concept ファイル、または Source Specs が見つかりません。

     次の操作:
       - 設定ファイルが無い場合: spec-anchor-setup-project --target <プロジェクトのパス> を実行してください。
       - Purpose / Core Concept ファイル (docs/core/purpose.md 等) が無い場合: 人間が作成して再実行してください。
         (Agent は Purpose / Core Concept を書きません)
       - Source Specs が見つからない場合: 設定の [sources].include を修正するか、Source Specs を該当パスに置いてください。

② ■ 外部サービスへの接続が必要です

     検索やモデル呼び出しに必要な外部サービスへ接続できませんでした (例: Qdrant / Chapter Anchors 生成 / Related Sections 検索)。

     次の操作:
       必要なサービスが起動しているか、接続情報が正しいかを確認し、/spec-core --all または /spec-core --rebuild で再試行してください。

⑤ ■ 人間判断が必要な仕様の衝突があります (本フォーマットは「pending conflict の本文展開フォーマット」を参照)

⑥ ■ ツール側でエラーが発生しました

     処理中に想定外のエラーが発生しました (例: Source Retrieval Index の更新・検証の失敗)。

     エラー内容: <利用者に見せてよい範囲のエラーメッセージ>

     次の操作:
       /spec-core --rebuild で再構築を試してください。解消しない場合は、本ツールの開発元へ上記エラー内容と実行したコマンドを添えて報告してください。

◇ (停止しない。通常の完了報告を出したうえで、末尾に 1 行)

     参考情報: 一部の補助的な保持物が最新ではありませんが、更新自体は完了しています。
```

### pending conflict の本文展開フォーマット (⑤)

pending conflict があるとき、件数だけを伝えてはいけない。各衝突を次の人間向けフォーマットで本文展開する。`conflict_id` / `claims` / `why_conflicting` などの内部 field 名は **見出しに使わず、値だけ** を出す。

```text
■ 人間判断が必要な仕様の衝突があります (N 件)

  1. <短い見出し: 衝突の論点を 1 行で>

     主張 A: <claims[0] の主張本文>
        出典: <claims[0] の出典>
     主張 B: <claims[1] の主張本文>
        出典: <claims[1] の出典>

     論点: <なぜ衝突しているか>
     人間判断が必要な理由: <なぜ LLM が決められないか>
     重要度: <high → 高 / medium → 中 / low → 低 へ翻訳>

     関係する仕様:
       - <関係する仕様の参照>

     選択肢:
       - <採用候補 1>
       - <採用候補 2>

     次の操作: <CLI の item recommended_next_action の値そのまま (例: Ask a human to decide this conflict.)>

     (衝突 ID: <conflict_id の値>  ← 再参照用)
```

`claims` が 3 件以上なら「主張 A / B / C / ...」と続ける。複数衝突なら見出しを `1.` `2.` と連番にする。各 item の `recommended_next_action` の **値** は省略せず必ず本文に含める。Agent は衝突を決めない。

## ユーザー向け本文に貼ってはいけない内部用語

次の内部 field 名・enum 値・パイプライン段階名は、利用者宛の本文に出さない (`tests/e2e/forbidden_terms.py` が単一の真実)。利用者は CLI の内部構造を知らない前提で読む。

- 制御 flag: `should_stop` / `stop_reason` / `blocking_reasons` / `can_continue` / `status="blocked"` / `="failed"` / `="error"` / `="fresh"` / `="degraded"`
- freshness の理由 (enum): `dirty_or_stale_source` / `stale_config_or_schema` / `watcher_running` / `watcher_queue_pending` / `pending_conflict` / `failed_required_artifact` / `degraded_optional_artifact`
- 正常完了系の field 名: `updated_sources` / `failed_sources` / `failed_sections` / `retrieval_index_status` / `pending_conflict_count` / `stale_resolution_count` / `unreflected_conflict_resolutions` / `auto_dismissed_conflict_count` / `auto_dismissed_conflict_ids` / `regenerated_chapter_anchors`
- パイプライン段階名: `section_metadata_generation` / `related_sections` / `retrieval_index` / `chapter_anchors` / `claim_retrieval_status` / `conflict_candidate_triage_status` / `spec_claims_status`
- 内部 path / 答案 field 名: `inject_result.<...>` / `freshness_report` / `evidence_origin` / `support_refs`
- conflict の raw field 名: `conflict_id` / `why_conflicting` / `why_llm_cannot_decide` / `decision_options` / `source_refs` (= 上記の人間向け見出しへ置換する)

許可される文字列:

- CLI が出力する `recommended_next_action` の **値文字列** (例: `run /spec-core --all` / `Ask a human to decide this conflict.`)
- スラッシュコマンド名 (`/spec-core` / `/spec-core --all` / `/spec-core --rebuild` 等)、実 CLI command 名 (`spec-anchor-setup-project` 等)、ファイルパス + section ID

CLI が出力する `recommended_next_action` の値は CLI 自身が出力する文字列をそのまま使う。Agent が再構成して別 command を提案しない。CLI 出力に無い復旧 command を追加提案しない。特に `spec-anchor status` は本 contract の command ではないため提案しない。
