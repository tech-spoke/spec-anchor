---
description: 課題用 SPEC-anchor constraints を準備する。回答は出さない
argument-hint: "[課題]"
allowed-tools: Read, Grep, Glob, Bash(spec-anchor inject*), Bash(spec-anchor realign*)
---

# /spec-inject

正本は SPEC-anchor の外部 command contract と SPEC-anchor CLI の入出力である。この Claude command template は独立した仕様ではない。

すべての `spec-anchor` CLI 呼び出しは現在の作業ディレクトリ (cwd) を project root として実行する。親ディレクトリ、別プロジェクト、記憶にある他のパスを探索してはならない。`.spec-anchor/config.toml` の有無を事前確認して CLI 実行を省略してはならない。CLI を実行し、CLI が返すエラー JSON を利用者に伝達する。

ユーザーが課題固有 constraints を必要としており、まだ最終回答や実装を求めていない場合に `/spec-inject` を使う。

## 必須手順

1. 明示された argument と現在の会話区間から task を定義する。会話区間は search と constraint generation の補助に使うが、final evidence ではない。
2. task と会話区間から search keys を生成する。
3. 4 path の Agentic Search を行う。各 `spec-anchor inject-*` コマンドは freshness が blocked / failed のとき、または `spec-anchor-watch` 実行中のとき、または pending Conflict Review Item があるとき自動的に停止指示 (`should_stop=true`) を返す。返却 JSON の `blocking_reasons` に dirty / stale / watcher 系の理由がある場合、`/spec-core` または watcher を実行・待機するようユーザーに伝える。`/spec-core` は自動実行しない。唯一の blocker が pending conflict の場合、Conflict Review Items と decision choices を人間に提示する。path は必須ではなく許可。課題の性質に応じて組み合わせる。

   重要: いずれか 1 つの `spec-anchor inject-*` が `should_stop=true`、`status="blocked"`、`status="failed"`、または `status="error"` を返した時点で、他の inject path、Source Specs の Read、constraints 生成へ進まず即停止する。停止後に追加の `spec-anchor inject-*` を試してはならない。

### path ① Qdrant section-level retrieval (Source Specs 探索の主経路)

a. search keys で hybrid retrieval を呼ぶ: `spec-anchor inject-search "<query>"`
b. 返ってきた hits の payload (heading_path / summary / search_keys / identifiers / related_sections) を読み、制約に関連しそうな候補を選ぶ
c. 候補 section の related_sections 配列から target_section_id を取得し、payload lookup する: `spec-anchor inject-section "<target_id>" [<target_id>...]`
d. 必要なら Source Specs ファイル本文を Read で確認し、制約根拠を抽出する
e. c-d を再帰的に適用する (最大数 hop)。制約に関係しないと判断できた時点で打ち切る

### path ② chapter_anchors.json による章単位エントリ

a. 章 anchor の path を取得する: `spec-anchor inject-chapters`
b. 返ってきた `chapter_anchors_path` を `Read` で読む。章数が多い場合は必要な範囲だけ部分取得する
c. 各 chapter の summary / key_topics / important_sections を見て、今回の課題に関連しそうな章を特定する
d. 特定された章配下の section を path ① と同様に Agentic Search で読み、制約を抽出する

### path ③ Purpose / Core Concept からの制約抽出

a. Purpose 全文と Core Concept path を取得する: `spec-anchor inject-purpose`
b. 返ってきた `purpose` (全文) から課題に該当する制約根拠を抽出する
c. 返ってきた `core_concept_path` を `Read` で読み、課題に関連する箇所だけを部分取得して制約根拠を抽出する。Core Concept は大きくなる可能性があるため一括投入しない

### path ④ resolved Conflict Review Items の確認

a. resolved + stale でない items を取得する: `spec-anchor inject-conflicts`
b. valid_scope (global / task_scope) と resolution.referenced_source_refs を確認する
c. 制約に関係する場合、evidence_origin = "Conflict Review Item" として制約に組み込む

### path 選択の指針

| 課題タイプ | 主 path | 補強 |
|---|---|---|
| 具体的 API / 識別子 | ① | ③、④ |
| 全体方針 / 抽象的 | ② | ①、③、④ |
| Purpose / Core Concept 直接質問 | ③ | ①、② |
| 過去判断の継続 | ④ | ①、③ |

4. constraints JSON array を作る。各 constraint は `statement`, `evidence_origin`, `evidence_ref`, `support_refs`, `applicability`, `uncertainty` を持つ。
5. constraints の構造を自己点検する: 各 constraint で `statement` / `evidence_origin` / `evidence_ref` / `applicability` が非空文字列であること、`evidence_origin` が `Purpose` / `Core Concept` / `Source Specs` / `Conflict Review Item` のいずれかであること、`Section Summary` / `Search Keys` / `Related Sections` / `Chapter Key Anchor` を `evidence_origin` に置かないこと、`support_refs` が list であること。`evidence_origin = "Conflict Review Item"` の場合、`spec-anchor inject-conflicts` の返却に含まれる items (resolved + stale でない) だけを参照する。CLI は構造検証を行わないため、Agent 自身が確認する。
6. constraint set、evidence list、Agentic Search summary だけを出力する。`/spec-inject` では task への回答や最終案を出さない。

## CLI 出力と人間向け整形

`spec-anchor inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` の戻り値は **stdout に出る内部 JSON** であり、CLI 自身は人間向け整形を持たない (外部設計書 §8.5)。Agent はこの JSON を読んで、ユーザー宛の会話に対して次の構造で整形する:

```text
今回守る制約
  - <制約の文 (statement の値)>
    根拠の種類: <Purpose / Core Concept / Source Specs / Conflict Review Item>
    参照: <文書 path + section ID など (evidence_ref の値)>
    参照補助: <探索補助に使った Section Summary / Related Sections / Chapter Key Anchor の要約>
    適用範囲: <この制約が効く作業範囲 (applicability の値)>

今回見るべき対象
  - <Section または topic>
    理由: <なぜ今回関係するか>

関連先として確認したもの
  - <related Section>
    理由: <依存 / 影響 / 関連 / 衝突 など>

採用しなかったもの
  - <候補>
    理由: <今回の課題には遠い / 根拠不足 / 別論点>

不確実性 / 確認すべき点
  - <確認すべき点>
```

内部 field 名 (`evidence_origin` / `support_refs` / `applicability` / `uncertainty`) を label として貼らず、上記の人間語見出し (根拠の種類 / 参照 / 参照補助 / 適用範囲 / 確認すべき点) へ翻訳する。各セクションは、該当 0 件のときも「該当なし」を明示する。セクション自体の省略は許可しない。CLI の JSON を生のまま会話に貼らない。ユーザーが意図して raw JSON を求めた場合のみ JSON を出す。

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

良い例: `evidence_ref` は実在する Purpose / Core Concept / Source Specs の path + section id、または stale でない resolved Conflict Review Item id を指す。`statement` は evidence から直接言える内容だけにする。迷いがある場合は `uncertainty` に短く書き、断定しない。

禁止例: `evidence_origin` に Section Summary / Related Sections / Chapter Key Anchor を入れない。`evidence_ref` を「たぶん関連」「上の要約」など曖昧にしない。`support_refs` だけを根拠にした constraint を作らない。CLI validation failed の場合、field を削って通そうとせず、引用元 snippet を読み直して constraints JSON を再生成する。

## 根拠ルール

`evidence_origin` は Purpose、Core Concept、Source Specs、Conflict Review Item のいずれかでなければならない。Conflict Review Item は resolved かつ stale でない場合だけ final evidence にできる。

Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor は navigation / support 専用である。`support_refs` には入れられるが、constraint の sole evidence にはしない。

Purpose と Core Concept は人間が維持する read-only input である。両ファイルは変更しない。`.spec-anchor/config.toml` の `[llm]` provider は使わない。`/spec-inject` はこの command を実行している Agent / LLM が担当する。

## 停止時のユーザー向け出力フォーマット

CLI が停止を返したとき (返却 JSON の `should_stop` が真、または `status` が `blocked` / `failed` / `error`)、その JSON を次の **利用者視点カテゴリ** へ写像し、該当カテゴリの固定フォーマットだけを出力する。利用者は CLI の内部構造を知らない前提なので、内部 field 名・enum 値・パイプライン段階名は本文に出さない (後述「ユーザー向け本文に貼ってはいけない内部用語」)。該当しないカテゴリは出力しない (「該当なし」も書かない)。

### 停止カテゴリ写像 (6 + ◇ + ✕)

左 2 列は判定のための内部状態であり **本文には出さない**。利用者へ出すのは「利用者向け見出し」以降だけ。

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

### カテゴリ別フォーマット

該当したカテゴリ 1 つ (③ と ⑤ のように複数該当時は両方) を、次の固定見出しで出す。

```text
① ■ 初期設定が完了していません

     プロジェクトの設定ファイルまたは Purpose / Core Concept ファイルが見つかりません。

     次の操作:
       spec-anchor-setup-project --target <プロジェクトのパス> を実行して初期化してください。
       Purpose / Core Concept ファイル (docs/core/purpose.md 等) が未作成なら、人間が作成してください。
       (今回の探索・制約生成は行いません)

② ■ 外部サービスへの接続が必要です

     検索やモデル呼び出しに必要な外部サービスへ接続できませんでした (例: Qdrant / LLM provider)。

     次の操作:
       必要なサービスが起動しているか、接続情報 (URL / 認証) が正しいかを確認してから、もう一度実行してください。

③ ■ 保持物の更新が必要です

     Source Specs または設定が変更され、保持している情報が古くなっています。この状態では今回の制約生成へ進みません。

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

◇ (停止しない。通常の出力を出したうえで、末尾に 1 行)

     参考情報: 一部の補助的な保持物が最新ではありませんが、今回の処理は続行できます。
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
- Agent 答案待ちの内部信号: `needs_agent_answer` / `answer candidate`
- パイプライン段階名: `section_metadata_generation` / `related_sections` / `retrieval_index` / `chapter_anchors` / `claim_retrieval_status` / `conflict_candidate_triage_status` / `spec_claims_status`
- 内部 path / 答案 field 名: `inject_result.<...>` / `freshness_report` / `evidence_origin` / `support_refs`
- conflict の raw field 名: `conflict_id` / `why_conflicting` / `why_llm_cannot_decide` / `decision_options` / `source_refs` (= 上記の人間向け見出しへ置換する)

許可される文字列:

- CLI が出力する `recommended_next_action` の **値文字列** (例: `run /spec-core before /spec-inject` / `Ask a human to decide this conflict.`)
- スラッシュコマンド名 (`/spec-core` 等)、実 CLI command 名 (`spec-anchor-setup-project` 等)、ファイルパス + section ID

CLI が出力する `recommended_next_action` の値は CLI 自身が出力する文字列をそのまま使う。Agent が再構成して別 command を提案しない。CLI 出力に無い復旧 command を追加提案しない。特に `spec-anchor status` は本 contract の command ではないため提案しない。
