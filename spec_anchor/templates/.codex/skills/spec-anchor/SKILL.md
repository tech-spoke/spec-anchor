---
name: spec-anchor
description: 実装や回答の前に、仕様に基づくコンテキスト、freshness 確認、Source Specs に対する Agentic Search、Conflict Review Item、spec-anchor core/inject/realign/watch CLI workflow が必要なときに使う。
metadata:
  short-description: 仕様に基づくコンテキスト workflow
---

# SPEC-anchor

SPEC-anchor は、Agent 作業中に軽量な仕様コンテキストを保持する。保持 artifact と freshness の正本は CLI である。会話区間の解釈、Agentic Search の探索方針、今回必要な constraints 生成、realign での answer 生成は Agent / LLM が担当する。

## 作業場所

すべての `spec-anchor` CLI 呼び出しは現在の作業ディレクトリ (cwd) を project root として実行する。親ディレクトリ、別プロジェクト、記憶にある他のパスを探索してはならない。`.spec-anchor/config.toml` の有無を事前確認して CLI 実行を省略してはならない。CLI を実行し、CLI が返すエラー JSON を利用者に伝達する。Source Specs を捏造せず、setup を自動実行しない。

## Core 更新

保持 artifact を更新する必要があるときは `spec-anchor core` を実行する。`--all` は、ユーザーが full rebuild を明示した場合だけ追加する。`.spec-anchor/config.toml` の `[llm.stage_routing]` が stage 別の最適 model / effort を適用する。`--llm-provider` を明示すると stage_routing を上書きしてしまうので、特別な事情 (provider 障害時の fallback など) がない限り指定しない。

`spec-anchor core` は Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor、Source Retrieval Index、Conflict Review Items を更新する。Purpose と Core Concept は人間が維持する read-only input である。

core 実行後は、後続作業に必要な CoreResult field を報告する: `updated_sources`, `failed_sources`, `failed_sections`, `retrieval_index_status`, `freshness_report`, `pending_conflict_count`, `conflict_review_items`, `unreflected_conflict_resolutions`, `stale_resolution_count`。ユーザーが workflow として依頼していない限り、core の一部として inject / realign を実行しない。

## Inject 手順

inject は、ユーザーが課題用 constraints を必要としており、まだ回答や実装案を求めていない場合に使う。

1. 明示された prompt と現在の会話区間から task を定義する。
2. task と会話区間から search keys を生成する。
3. 4 path の Agentic Search を行う。各 `spec-anchor inject-*` コマンドは freshness blocked / failed / watcher 実行中 / pending conflict のとき自動的に停止指示 (`should_stop=true`) を返す。返却 JSON の `blocking_reasons` に dirty / stale / watcher 系の理由がある場合、core/watch を実行または待機するようユーザーに伝える。`/spec-core` は自動実行しない。唯一の blocker が pending conflict の場合、Conflict Review Items と decision options を人間に提示する。path は必須ではなく許可。課題の性質に応じて組み合わせる。
   - いずれか 1 つの `spec-anchor inject-*` が `should_stop=true`、`status="blocked"`、`status="failed"`、または `status="error"` を返した時点で、他の inject path、Source Specs の Read、constraints 生成へ進まず即停止する。停止後に追加の `spec-anchor inject-*` を試してはならない。
   - **path ① Qdrant section-level retrieval** (主経路): `spec-anchor inject-search "<query>"` で hybrid retrieval → hits の payload (heading_path / summary / search_keys / identifiers / related_sections) を読む → related_sections の target を `spec-anchor inject-section "<id>"` で payload lookup → Source Specs 本文を Read で確認 → 再帰的に辿り、制約に無関係と判断できた時点で打ち切り
   - **path ② chapter anchor** (章単位エントリ): `spec-anchor inject-chapters` で `chapter_anchors_path` を取得 → `Read` で読む (大きい場合は部分取得) → summary / key_topics / important_sections で関係しそうな章を特定 → path ① と同様に Agentic Search
   - **path ③ Purpose / Core Concept**: `spec-anchor inject-purpose` で `purpose` (全文) と `core_concept_path` を取得 → Purpose 全文から制約根拠を抽出 → `core_concept_path` は `Read` で課題に関連する部分だけを部分取得して制約根拠を抽出 (Core Concept は大きくなる可能性があるため一括投入しない)
   - **path ④ Conflict Review Items**: `spec-anchor inject-conflicts` → resolved + stale でない items を取得 → valid_scope と referenced_source_refs を確認 → 制約に組み込む
   - path 選択の指針: 具体的 API / 識別子 → ①主 + ③④補強、全体方針 / 抽象的 → ②主 + ①③④補強、Purpose / Core Concept 直接質問 → ③主 + ①②補強、過去判断の継続 → ④主 + ①③補強
   - ユーザーが全文レビューを明示しない限り、Source Specs full text を最終 context に丸ごと貼らない。
4. constraints JSON array を作る。各 constraint は `statement`, `evidence_origin`, `evidence_ref`, `support_refs`, `applicability`, `uncertainty` を持つ。`evidence_origin` は Purpose、Core Concept、Source Specs、Conflict Review Item のいずれかに限る。Section Summary、Search Keys、Related Sections、Chapter Key Anchor は `support_refs` にだけ置ける。これらを sole evidence にしない。
5. constraints の構造を自己点検する: 各 constraint で `statement` / `evidence_origin` / `evidence_ref` / `applicability` が非空、`evidence_origin` は Purpose / Core Concept / Source Specs / Conflict Review Item のいずれか、`support_refs` は list。CLI は構造検証を行わないため、Agent 自身が確認する。Conflict Review Item を根拠にする場合は `spec-anchor inject-conflicts` の返却 (resolved + stale でない) だけを使う。
6. constraints、evidence、search summary だけを出力する。inject では task への回答を出さない。
7. `spec-anchor inject-*` および `spec-anchor realign` の戻り値は **stdout の内部 JSON** であり、CLI は人間向け整形を持たない (外部設計書 §8.5)。Agent は JSON を読んで、ユーザー宛の会話に対して `今回守る制約` / `今回見るべき対象` / `関連先として確認したもの` / `採用しなかったもの` / `不確実性 / 人間確認` (realign は加えて 4 区分の answer) の 5 セクションを見出し付きで整形して出す。各セクションは、該当 0 件のときも「該当なし」を明示する。セクション自体の省略は許可しない。raw JSON を会話に貼らない (ユーザーが明示的に raw を要求した場合のみ例外)。

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

## Realign 手順

realign は、ユーザーが constraints と回答または実装方針を必要としている場合に使う。

1. Inject Workflow を実行し、validated constraints まで進める。
2. validated constraints に従う answer candidate を作る。answer が constraint と衝突する場合、隠さず human review として明示する。
3. answer candidate は次の 4 区分を区別する: `今回守る制約`, `今回扱う修正候補または検討対象`, `競合 / 不確実性 / 人間レビューが必要な点`, `課題プロンプトへの回答または修正案`。
4. CLI で答案を整形する: `spec-anchor realign --answer-json '<json-object>'`。constraints は answer の `今回守る制約` セクション内に書く (CLI は constraints の真偽を検証しない、Agent の責務)。返却 payload を constraint-checked answer として扱う。freshness gate が blocked / failed なら停止指示が返るので、ユーザーに伝える。この場合、停止後に追加の `spec-anchor inject-*`、Source Specs の Read、answer 整形へ進まない。

## 停止時のユーザー向け出力フォーマット

CLI が停止 (返却 JSON の `should_stop` が真、または `status` が `blocked` / `failed` / `error`) を返したとき、利用者は CLI の内部構造を知らない前提で読む。CLI の内部 field 名・enum 値・パイプライン段階名は本文に出さず、次の利用者視点カテゴリへ写像して固定見出しで出す (Claude 版 `.claude/commands/spec-*.md` と完全に同じ契約)。

| | 利用者向けの状況 | 内部状態 (本文に出さない) | 利用者向け見出し / 行動 |
|---|---|---|---|
| ① | 初期設定が完了していない | config.toml / purpose / concept 不在、`sources.include` 不一致 | ■ 初期設定が完了していません → `spec-anchor-setup-project` |
| ② | 外部サービスへの接続が必要 | Qdrant / LLM provider 失敗 | ■ 外部サービスへの接続が必要です → サービス起動 / 接続確認 |
| ③ | 保持物の更新が必要 | dirty / stale source / 設定 schema 不整合 / 必須保持物失敗 | ■ 保持物の更新が必要です → `/spec-core` |
| ④ | 保持物の更新中・待機 | watcher 実行中 / 更新キュー待ち | ■ 保持物の更新中です → 完了を待つ |
| ⑤ | 人間判断が必要な仕様の衝突 | pending conflict | ■ 人間判断が必要な仕様の衝突があります → 本文展開 (下記) |
| ⑥ | ツール側のエラー | 想定外例外 / ①〜⑤ 外の error | ■ ツール側でエラーが発生しました → 開発元へ報告 |
| ◇ | 情報通知 (続行可能) | 補助保持物のみ劣化 (単独) | 末尾に「参考情報: …続行できます」(停止しない) |
| ✕ | 非表示 | Agent 答案待ちの内部信号 | 表示せず Agent が答案を組み立てて自動再実行 |

復旧手順は CLI の `recommended_next_action` の **値** をそのまま使い、存在しない command (`spec-anchor status` 等) を追加提案しない。`.spec-anchor/config.toml not found under {root}` のときは `spec-anchor-setup-project --target <project_root>` を提案する。

### pending conflict の本文展開フォーマット (⑤)

件数だけを伝えてはいけない。各衝突を次の人間向けフォーマットで本文展開する (`conflict_id` / `claims` / `why_conflicting` などの内部 field 名は見出しに使わず、値だけを出す)。

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

     次の操作: <item recommended_next_action の値そのまま (例: Ask a human to decide this conflict.)>

     (衝突 ID: <conflict_id の値>  ← 再参照用)
```

`claims` が 3 件以上なら主張 A / B / C と続け、複数衝突なら見出しを `1.` `2.` と連番にする。各 item の `recommended_next_action` の **値** は省略せず必ず本文に含める。

### 答案なし呼び出しの自動再実行 (✕ カテゴリ)

利用者が答案なしで `/spec-realign` を呼び、CLI が Agent 答案待ちの内部信号で停止した場合、その停止を利用者へ見せない。Agent は黙って Agentic Search → 4 区分答案の組み立て → `spec-anchor realign --answer-json '<json>'` 再実行を行い、整形済み RealignResult だけを表示する。`needs_agent_answer` / `answer candidate` / `stop_reason` の語は本文に出さない。

### 構造化失敗時のリトライ (1 回まで)

答案を渡した結果 CLI が形式不備を `error` block (`code` / `field` / `expected` / `actual`) で返したら、`error.field` が指す箇所だけを直して 1 回だけ再実行する。なお失敗したら ⑥ へ落とし、最後に送った答案と「期待された形式との差分」を人間語で併記する (内部 `code` 名は出さない)。

## 正常完了時のユーザー向け出力フォーマット

正常完了でも、CoreResult / RealignResult の内部 field 名 (`updated_sources` / `failed_sources` / `retrieval_index_status` / `pending_conflict_count` / `stale_resolution_count` / `unreflected_conflict_resolutions` 等) や enum 値 (`status="dismissed"` / `severity`) を貼らない。

- `/spec-core` 正常完了: 「■ 保持物の更新が完了しました」+「更新があった仕様」(変更なしなら「変更ありませんでした」) +「人間判断が必要な仕様の衝突」(あれば本文展開) +「再確認の候補」(過去判断を 採用 / 却下 / 修正 へ翻訳、0 件なら省略) +「次の操作」。
- `/spec-inject` 正常完了: 5 セクション (今回守る制約 / 今回見るべき対象 / 関連先として確認したもの / 採用しなかったもの / 不確実性) で出す。制約の内部 field 名 `evidence_origin` / `support_refs` / `applicability` / `uncertainty` を「根拠の種類」/「参照補助」/「適用範囲」/「確認すべき点」へ翻訳。
- `/spec-realign` 正常完了: 4 区分 (今回守る制約 / 今回扱う修正候補または検討対象 / 競合・不確実性・人間レビュー / 課題プロンプトへの回答または修正案) で出し、制約は inject と同じ label 翻訳を適用。

## ユーザー向け本文に貼ってはいけない内部用語

`tests/e2e/forbidden_terms.py` が単一の真実。`should_stop` / `stop_reason` / `blocking_reasons` / `status="blocked"` 等の制御 flag、`dirty_or_stale_source` / `pending_conflict` / `needs_agent_answer` 等の enum・内部信号、`section_metadata_generation` / `related_sections` / `retrieval_index` / `chapter_anchors` 等のパイプライン段階名、`updated_sources` / `retrieval_index_status` / `stale_resolution_count` 等の正常完了系 field 名、`evidence_origin` / `support_refs` / `conflict_id` / `why_conflicting` / `decision_options` / `source_refs` などは本文に出さない。許可されるのは `recommended_next_action` の値文字列、スラッシュコマンド名、実 CLI command 名、ファイルパス + section ID。

Purpose と Core Concept は人間が維持する。自動更新しない。
