---
description: SPEC-anchor constraints を準備し、課題へ回答する
argument-hint: "[課題]"
allowed-tools: Read, Grep, Glob, Bash(spec-anchor inject*), Bash(spec-anchor realign*)
---

# /spec-realign

正本は SPEC-anchor の外部 command contract と SPEC-anchor CLI の入出力である。この Claude command template は独立した仕様ではない。

すべての `spec-anchor` CLI 呼び出しは現在の作業ディレクトリ (cwd) を project root として実行する。親ディレクトリ、別プロジェクト、記憶にある他のパスを探索してはならない。`.spec-anchor/config.toml` の有無を事前確認して CLI 実行を省略してはならない。CLI を実行し、CLI が返すエラー JSON を利用者に伝達する。

ユーザーが課題固有 constraints と answer candidate または実装方針を必要としている場合に `/spec-realign` を使う。

## 必須手順

1. 明示された argument と現在の会話区間から task を定義する。会話区間は search、constraint generation、answer drafting の補助に使うが、final evidence ではない。
2. answer candidate が会話または argument にある場合、4 区分 JSON の暫定形を作り、project root で gate probe として `spec-anchor realign --answer-json '<json-object>'` を実行する。`.spec-anchor/config.toml` の有無を事前確認しない。CLI が `should_stop=true`、`status="blocked"`、`status="failed"`、または `status="error"` を返した場合、その JSON を読んで利用者に伝達し、ここで即停止する。停止後に `spec-anchor inject-*`、Source Specs の Read、answer 整形へ進まない。CLI が `should_stop=false` を返した場合、この最初の戻り値だけで完了扱いにせず、以降の Agentic Search と最終 realign へ進む。
3. answer candidate が会話にも argument にも無い場合、project root で `spec-anchor realign` を実行して CLI の `stop_reason="needs_agent_answer"` / `recommended_next_action` を確認する。`.spec-anchor/config.toml` 不在や freshness blocker など `should_stop=true` の場合は、その JSON を利用者に伝達して停止する。
4. task と会話区間から search keys を生成する。
5. `/spec-inject` と同じ 3 path の Agentic Search を行う (path ① inject-search + inject-section、path ② inject-chapters、path ③ inject-purpose)。各 path の手順は `/spec-inject` template を参照。各 `spec-anchor inject-*` コマンドは freshness blocked / failed / watcher 実行中のとき自動的に停止指示を返す。`should_stop=true` または `status="error"` を返した時点で他 path へ進まず停止する。`/spec-core` は自動実行しない。pending conflict は CLI の停止理由ではなく情報として返るので、pending のみのときは停止せず提示へ進む。`inject-search` は positional query を使い、存在しない `--keys` option を使わない。

   **3 path は探索の起点であり上限ではない**。Agent は 3 path 通過後でも、課題への根拠が不十分と判断した場合、自らの気づきに基づく追加探索 (別 search key の生成、別 path への切り替え、上位章 hop) を能動的に行う。探索の十分性は Agent が判断し、制約に必要な根拠が揃うまで継続する。ただし `evidence_origin` 縛りと「CLI 道具経由でしか Source Specs に到達しない」制約は維持する (ドリフト防止)。詳細は `/spec-inject` template の「path 選択の指針」と外部設計書 §8.3 を参照。
6. constraints JSON array を作る。各 constraint は `statement`, `evidence_origin`, `evidence_ref`, `support_refs`, `applicability`, `uncertainty` を持つ。
7. constraints の構造を自己点検する (spec-inject template §5 と同じ手順)。CLI は構造検証を行わないため、Agent 自身が確認する。
8. constraints に従う answer candidate を作る。answer が constraint と衝突する場合、隠さず human review として明示する。
9. answer candidate は次の 4 区分を区別する: `今回守る制約`, `今回扱う修正候補または検討対象`, `競合 / 不確実性 / 人間レビューが必要な点`, `課題プロンプトへの回答または修正案`。constraints は `今回守る制約` セクションに直接書く。
10. CLI で答案を整形する: `spec-anchor realign --answer-json '<json-object>'`。CLI は freshness gate を通したうえで answer を 4 区分の RealignResult に整形して返す。`/spec-realign` も freshness blocked / failed / watcher 実行中のとき自動的に停止指示を返す。pending conflict は CLI の停止理由ではない (CLI は答案抑止のゲートを持たない)。**課題に関連する pending conflict があるときは、このテンプレの指示として答案を生成せず、答案つきの `spec-anchor realign` を呼ばない**。提示で停止する。CLI は constraints の真偽は検証しない (Agent の責務)。
11. CLI の戻り値は **stdout に出る内部 JSON** (RealignResult) であり、CLI 自身は人間向け整形を持たない (外部設計書 §8.5)。Agent は JSON 内の `answer.今回守る制約` / `今回扱う修正候補または検討対象` / `競合 / 不確実性 / 人間レビューが必要な点` / `課題プロンプトへの回答または修正案` の 4 セクションを読み、ユーザー宛の会話に対して 4 区分の見出し付きで整形して出す。`今回守る制約` セクション内の各制約は `/spec-inject` と同じ label 翻訳を適用する (内部 field 名 `evidence_origin` / `support_refs` / `applicability` を「根拠の種類」/「参照補助」/「適用範囲」へ置換する)。CLI の JSON を生のまま会話に貼らない。ユーザーが意図して raw JSON を求めた場合のみ JSON を出す。

### constraints JSON の作り方

最小 schema:

```json
[
  {
    "statement": "今回の作業で守る制約を 1 文で書く。",
    "evidence_origin": "Source Specs",
    "evidence_ref": "docs/spec/auth.md#0002-session-management",
    "support_refs": [
      {
        "origin": "Section Summary",
        "ref": "docs/spec/auth.md#0002-session-management",
        "note": "該当 Source Specs snippet へ到達するための探索補助"
      }
    ],
    "applicability": "この制約が適用される作業範囲を書く。",
    "uncertainty": []
  }
]
```

良い例: `evidence_ref` は実在する Purpose / Core Concept / Source Specs の path + section id を指す。`statement` は evidence から直接言える内容だけにする。迷いがある場合は `uncertainty` に短く書き、断定しない。

禁止例: `evidence_origin` に Section Summary / Related Sections / Chapter Key Anchor を入れない。`evidence_ref` を「たぶん関連」「上の要約」など曖昧にしない。`support_refs` だけを根拠にした constraint を作らない。CLI validation failed の場合、field を削って通そうとせず、引用元 snippet を読み直して constraints JSON を再生成する。

## 根拠ルール

`evidence_origin` は Purpose、Core Concept、Source Specs のいずれかでなければならない。

Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor は navigation / support 専用である。`support_refs` には入れられるが、constraint の sole evidence にはしない。

Purpose と Core Concept は人間が維持する read-only input である。両ファイルは変更しない。`.spec-anchor/config.toml` の `[llm]` provider は使わない。`/spec-realign` はこの command を実行している Agent / LLM が担当する。

## 矛盾 (Conflict Review Item) の扱い

`/spec-realign` の矛盾時挙動は `/spec-inject` と同じで、矛盾は pending (提示対象) / dismissed (却下済み・抑制中) の 2 状態しかない。

- 課題に関連する pending conflict があれば、制約情報と併せて提示して**停止する**
- 矛盾ありのときは回答 (答案・修正案) を生成しない。答案つきの `spec-anchor realign` を呼ばない (CLI は答案抑止のゲートを持たないため、停止はこのテンプレ指示で保証する)
- 矛盾なしのときだけ回答まで進む
- 課題と無関係な pending は関連性で絞ってよい
- dismissed の矛盾は提示されない。却下根拠のセクションが変わると `/spec-core` 再生成で却下が自動失効し、矛盾は再び pending に戻る

人間が明示的に「これは矛盾ではない」と却下したときだけ、却下を永続化する。却下フロー (実行前確認 → `spec-anchor core --dismiss-conflict <conflict_id> --reason "<理由>"` 実行 → 証跡表示) は `/spec-inject` template の「却下フロー」と同じ。Agent が矛盾を勝手に却下・解決しない。

## 停止時のユーザー向け出力フォーマット

CLI が停止を返したとき (返却 JSON の `should_stop` が真、または `status` が `blocked` / `failed` / `error`)、その JSON を次の **利用者視点カテゴリ** へ写像し、該当カテゴリの固定フォーマットだけを出力する。利用者は CLI の内部構造を知らない前提なので、内部 field 名・enum 値・パイプライン段階名は本文に出さない (後述「ユーザー向け本文に貼ってはいけない内部用語」)。該当しないカテゴリは出力しない (「該当なし」も書かない)。

### 停止カテゴリ写像 (6 + ◇ + ✕)

左 2 列は判定のための内部状態であり **本文には出さない**。利用者へ出すのは「利用者向けの状況」以降だけ。

| | 利用者向けの状況 | 内部状態 (本文に出さない) | 利用者が取る行動 |
|---|---|---|---|
| ① | 初期設定が完了していない | config.toml 不在 / `docs/core/purpose.md`・`core_concept.md` 不在 / `sources.include` 不一致 | `spec-anchor-setup-project` 実行、purpose / concept 作成 |
| ② | 外部サービスへの接続が必要 | Qdrant 接続失敗 / LLM provider 失敗 | サービス起動 / 接続情報の確認 |
| ③ | 保持物の更新が必要 | dirty / stale source / 設定 schema の不整合 / 必須保持物の生成失敗 | `/spec-core` 実行 |
| ④ | 保持物の更新中・待機 | watcher 実行中 / 更新キュー待ち | 完了を待つ |
| ⑤ | 人間判断が必要な仕様の衝突 | pending conflict | 衝突を読んで採用案を決定 |
| ⑥ | ツール側のエラー | 想定外例外 / ①〜⑤ に当てはまらない error | 開発元へ報告 |
| ◇ | 情報通知 (続行可能) | 補助的保持物のみ劣化 (単独) | 認知のみ、無視可 (停止しない) |
| ✕ | 非表示 | Agent 答案待ちの内部信号 | Agent 内部で答案を組み立てて再実行 (利用者表示なし) |

✕ (Agent 答案待ち) の扱いは後述「答案なし呼び出しの自動再実行」を参照。利用者には停止を見せず、Agent が答案を組み立てて自動再実行する。

### カテゴリ別フォーマット

該当したカテゴリ 1 つ (③ と ⑤ のように複数該当時は両方) を、次の固定見出しで出す。`/spec-realign` では復旧手順の文言は CLI top-level の `recommended_next_action` の値 (realign 文脈に正規化済み) を使い、内部に埋め込まれた inject 経路の文言は使わない。

```text
① ■ 初期設定が完了していません

     プロジェクトの設定ファイルまたは Purpose / Core Concept ファイルが見つかりません。

     次の操作:
       spec-anchor-setup-project --target <プロジェクトのパス> を実行して初期化してください。
       Purpose / Core Concept ファイル (docs/core/purpose.md 等) が未作成なら、人間が作成してください。
       (今回の回答整形は行いません)

② ■ 外部サービスへの接続が必要です

     検索やモデル呼び出しに必要な外部サービスへ接続できませんでした (例: Qdrant / LLM provider)。

     次の操作:
       必要なサービスが起動しているか、接続情報 (URL / 認証) が正しいかを確認してから、もう一度実行してください。

③ ■ 保持物の更新が必要です

     Source Specs または設定が変更され、保持している情報が古くなっています。この状態では回答整形へ進みません。

     次の操作:
       /spec-core を実行して保持物を更新してください。
       (設定や schema の変更が原因の場合は /spec-core --all)

④ ■ 保持物の更新中です

     別プロセスが保持物を更新中、または更新待ちの変更があります。

     次の操作:
       更新の完了を待ってから、もう一度実行してください。

⑤ ■ 人間判断が必要な仕様の衝突があります (本フォーマットは「pending conflict の本文展開フォーマット」を参照)

⑥ ■ ツール側でエラーが発生しました

     処理中に想定外のエラーが発生しました。これは利用者の操作では解消できない可能性があります。

     エラー内容: <利用者に見せてよい範囲のエラーメッセージ>

     次の操作:
       本ツールの開発元へ、上記エラー内容と実行したコマンドを添えて報告してください。

◇ (停止しない。通常の 4 区分出力を出したうえで、末尾に 1 行)

     参考情報: 一部の補助的な保持物が最新ではありませんが、今回の処理は続行できます。
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

`conflict_points` が 2 件以上なら「衝突箇所」に箇条書きを追加する。複数衝突なら見出しを `1.` `2.` と連番にする。各 item の `recommended_next_action` の **値** は省略せず必ず本文に含める (日本語以外の自然文は Agent が翻訳して反映)。Agent は衝突を決めない。回答整形は実行しない。

### 答案なし呼び出しの自動再実行 (✕ カテゴリ)

利用者が答案なしで `/spec-realign "<課題>"` を呼び、CLI が「Agent 答案待ち」の内部信号で停止した場合、その停止を利用者へ見せてはいけない。Agent は黙って次を行う:

1. 3 path の Agentic Search を行い constraints を抽出する。
2. 4 区分 (今回守る制約 / 今回扱う修正候補 / 競合・不確実性 / 課題プロンプトへの回答) の答案を組み立てる。
3. `spec-anchor realign --answer-json '<json>'` で再実行する。
4. 利用者には整形済み RealignResult (4 区分) のみを表示する。

この再実行の途中段階 (「次は答案を作ります」等のメタ説明、内部信号の語) を利用者へ出さない。`needs_agent_answer` / `answer candidate` / `stop_reason` の語は本文に出さない。

### 構造化失敗時のリトライ (1 回まで)

答案を渡して `spec-anchor realign --answer-json '<json>'` を実行した結果、CLI が答案の形式不備を `error` block (`code` / `field` / `expected` / `actual`) で返した場合のリトライポリシー:

1. CLI が返した `error.code` / `error.field` / `error.expected` を読む。代表的な `code`:
   - `missing_final_section`: 回答/修正案セクションが空。`課題プロンプトへの回答または修正案` を埋める。
   - `invalid_evidence_origin`: ある制約の根拠種別が許可外。`field` が指す制約の根拠を Purpose / Core Concept / Source Specs のいずれかへ直す。
   - `invalid_support_refs_type`: ある制約の参照補助がリストでない。`field` が指す制約の参照補助をリストへ直す。
   - `empty_applicability`: ある制約の適用範囲が空。`field` が指す制約の適用範囲を埋める。
2. 同じ Agentic Search 結果を使い、`error.field` が指す箇所だけを修正して答案を再構成する。盲目的に作り直さない。
3. `spec-anchor realign --answer-json '<json>'` を **1 回だけ** 再実行する。
4. それでも形式不備が返る場合は、⑥ ツール側のエラーへ落とし、**最後に送った答案 (4 区分)** と **CLI が返した error 詳細 (どの field が期待とどう違ったか)** を利用者に併記して表示する。

このリトライ過程 (`error.code` 等の内部 field 名、再構成中の独り言) は利用者本文に出さない。利用者に見せるのは、成功時は整形済み RealignResult、2 回失敗時は ⑥ の体裁に整えた「最後の答案」と「期待された形式との差分」だけ。

## ユーザー向け本文に貼ってはいけない内部用語

次の内部 field 名・enum 値・パイプライン段階名は、利用者宛の本文に出さない (`tests/e2e/forbidden_terms.py` が単一の真実)。利用者は CLI の内部構造を知らない前提で読む。

- 制御 flag: `should_stop` / `stop_reason` / `blocking_reasons` / `can_continue` / `status="blocked"` / `="failed"` / `="error"` / `="fresh"`
- freshness の理由 (enum): `dirty_or_stale_source` / `stale_config_or_schema` / `watcher_running` / `watcher_queue_pending` / `pending_conflict` / `failed_required_artifact`
- Agent 答案待ちの内部信号: `needs_agent_answer` / `answer candidate`
- パイプライン段階名: `section_metadata_generation` / `related_sections` / `retrieval_index` / `chapter_anchors` / `section_pair_candidate_generation_status`
- 内部 path / 答案 field 名: `inject_result.<...>` / `freshness_report` / `evidence_origin` / `support_refs`
- conflict の raw field 名: `conflict_id` / `severity` / `why_conflicting` / `why_llm_cannot_decide` / `source_refs` (= 上記の人間向け見出しへ置換する)
- **日本語以外の自然文** (例: CLI の `recommended_next_action` default 値 `Ask a human to decide this conflict.`、LLM judge の英語返答)。本文は日本語で統一する。**翻訳対象外**: コマンド名 / URL / file path / 識別子

許可される文字列:

- CLI が出力する top-level `recommended_next_action` の値が **コマンド名指示** (例: `run /spec-core before /spec-realign`、`spec-anchor-setup-project --target /path/to/project`) の場合は、そのまま使う
- CLI が出力する `recommended_next_action` の値が **日本語以外の自然文** (例: `Ask a human to decide this conflict.`) の場合、Agent は **利用者向け本文で日本語訳に置き換える** (例: `人間判断で衝突を解消してください。`)。翻訳対象外: コマンド名・URL・file path・識別子
- スラッシュコマンド名 (`/spec-core` 等)、実 CLI command 名 (`spec-anchor-setup-project` 等)、ファイルパス + section ID

CLI が出力する top-level `recommended_next_action` の値 (コマンド名指示) は CLI 自身が出力する文字列をそのまま使う。日本語以外の自然文は Agent が日本語訳に置き換える。Agent が再構成して別 command を提案しない。CLI 出力に無い復旧 command を追加提案しない。特に `spec-anchor status` は本 contract の command ではないため提案しない。
