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

実行後は、CLI が返す CoreResult JSON を読み、後述「正常完了時のユーザー向け出力フォーマット」に従って整形して報告する。CoreResult の内部 field 名 (`updated_sources` / `failed_sources` / `retrieval_index_status` / `pending_conflict_count` / `stale_dismissal_count` / `freshness_report` 等) はそのまま本文に貼らない。

pending Conflict Review Items が残る場合、件数だけでなく後述「pending conflict の本文展開フォーマット」で各衝突を本文展開する。pending conflict を Agent が決めない。

Purpose と Core Concept は人間が維持する read-only input である。この command から `/spec-inject` や `/spec-realign` を自動実行しない。CLI result と、人間判断が必要な pending Conflict Review Items を返す。

## 正常完了時のユーザー向け出力フォーマット

CLI が正常完了 (`status` が `updated`) を返したとき、CoreResult JSON の内部 field 名 (`updated_sources` / `failed_sources` / `retrieval_index_status` / `pending_conflict_count` / `stale_dismissal_count` 等) や enum 値 (`status="dismissed"` 等) をそのまま貼らず、次の固定フォーマットへ整形する。英語混じり日本語 (「freshness は通った」「失効した dismissal」等) を使わない。

```text
■ 保持物の更新が完了しました

  更新があった仕様:
    - <変更があった仕様ファイルのパスと section の見出し>
    (変更が無かった場合は「変更ありませんでした」とだけ書く)

  人間判断が必要な仕様の衝突:
    なし
    (1 件以上ある場合は「pending conflict の本文展開フォーマット」で各衝突を展開する)

  再確認の候補 (過去に却下した衝突が、現在の仕様変更で見直し余地あり): <件数> 件
    1. <衝突 ID と簡潔な見出し>
       過去の判断: <採用 / 却下 / 修正 のいずれかへ翻訳>
       なぜ再確認が必要か: 関係する仕様が変更されたため
       (衝突 ID: <値>)
    (0 件のときはこのセクション自体を省略する)

  次の操作:
    /spec-inject "<課題>" を実行してください。
```

「過去の判断」は内部値を人間語へ翻訳する (採用 = 過去に採択、却下 = 過去に棄却、修正 = 過去に修正採択)。`status="dismissed"` / `severity="high"` などの生の enum 値は出さず、「却下」「重要度: 高」へ翻訳する。「再確認の候補」は、過去に解消した衝突判断が、その後の仕様変更で根拠が古くなった (= 制約の根拠には使えない) ものを、人間が再確認できるよう提示するもの。即時の作業ブロッカーではない。

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

pending conflict があるとき、件数だけを伝えてはいけない。各衝突を次の人間向けフォーマットで本文展開する。`conflict_id` / `conflict_points` / `why_conflicting` などの内部 field 名は **見出しに使わず、値だけ** を出す。

```text
■ 人間判断が必要な仕様の衝突があります (N 件)

  1. <短い見出し: 衝突の論点を 1 行で>

     衝突箇所:
       - 左の抜粋: <conflict_points[0].left_excerpt>
         右の抜粋: <conflict_points[0].right_excerpt>
         なぜ衝突するか: <conflict_points[0].why_conflicting>
         重要度: <conflict_points[0].severity を high → 高 / medium → 中 / low → 低 へ翻訳>

     論点: <なぜ衝突しているか>
     人間判断が必要な理由: <なぜ LLM が決められないか>
     重要度: <high → 高 / medium → 中 / low → 低 へ翻訳>

     関係する仕様:
       - <関係する仕様の参照>

     次の操作: <Agent が日本語訳した item recommended_next_action 値。CLI が日本語以外の自然文を返した場合は日本語に置き換える。例: `Ask a human to decide this conflict.` → 「人間判断で衝突を解消してください。」>

     (衝突 ID: <conflict_id の値>  ← 再参照用)
```

`conflict_points` が 2 件以上なら「衝突箇所」に箇条書きを追加する。複数衝突なら見出しを `1.` `2.` と連番にする。各 item の `recommended_next_action` の **値** は省略せず必ず本文に含める (日本語以外の自然文は Agent が翻訳して反映)。Agent は衝突を決めない。

## ユーザー向け本文に貼ってはいけない内部用語

次の内部 field 名・enum 値・パイプライン段階名は、利用者宛の本文に出さない (`tests/e2e/forbidden_terms.py` が単一の真実)。利用者は CLI の内部構造を知らない前提で読む。

- 制御 flag: `should_stop` / `stop_reason` / `blocking_reasons` / `can_continue` / `status="blocked"` / `="failed"` / `="error"` / `="fresh"`
- freshness の理由 (enum): `dirty_or_stale_source` / `stale_config_or_schema` / `watcher_running` / `watcher_queue_pending` / `failed_required_artifact`
- 正常完了系の field 名: `updated_sources` / `failed_sources` / `failed_sections` / `retrieval_index_status` / `pending_conflict_count` / `stale_dismissal_count` / `auto_dismissed_conflict_count` / `auto_dismissed_conflict_ids` / `regenerated_chapter_anchors`
- パイプライン段階名: `section_metadata_generation` / `related_sections` / `retrieval_index` / `chapter_anchors` / `section_pair_candidate_generation_status`
- 内部 path / 答案 field 名: `inject_result.<...>` / `freshness_report` / `evidence_origin` / `support_refs`
- conflict の raw field 名: `conflict_id` / `why_conflicting` / `why_llm_cannot_decide` / `source_refs` (= 上記の人間向け見出しへ置換する)
- **日本語以外の自然文** (例: CLI の `recommended_next_action` default 値 `Ask a human to decide this conflict.`、LLM judge の英語返答)。本文は日本語で統一する。**翻訳対象外**: コマンド名 / URL / file path / 識別子

許可される文字列:

- CLI が出力する `recommended_next_action` の値が **コマンド名指示** (例: `run /spec-core --all`、`spec-anchor-setup-project --target /path/to/project`) の場合は、そのまま使う
- CLI が出力する `recommended_next_action` の値が **日本語以外の自然文** (例: `Ask a human to decide this conflict.`) の場合、Agent は **利用者向け本文で日本語訳に置き換える** (例: `人間判断で衝突を解消してください。`)。翻訳対象外: コマンド名・URL・file path・識別子
- スラッシュコマンド名 (`/spec-core` / `/spec-core --all` / `/spec-core --rebuild` 等)、実 CLI command 名 (`spec-anchor-setup-project` 等)、ファイルパス + section ID

CLI が出力する `recommended_next_action` の値 (コマンド名指示) は CLI 自身が出力する文字列をそのまま使う。日本語以外の自然文は Agent が日本語訳に置き換える。Agent が再構成して別 command を提案しない。CLI 出力に無い復旧 command を追加提案しない。特に `spec-anchor status` は本 contract の command ではないため提案しない。
