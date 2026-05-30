---
name: spec-anchor
description: 実装や回答の前に、仕様に基づくコンテキスト、freshness 確認、Source Specs に対する Agentic Search、矛盾 (Conflict Review Item) の提示、spec-anchor core/inject/realign/watch CLI workflow が必要なときに使う。
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

core 実行後は、後続作業に必要な CoreResult field を報告する: `updated_sources`, `failed_sources`, `failed_sections`, `retrieval_index_status`, `freshness_report`, `pending_conflict_count`, `conflict_review_items`, `stale_dismissal_count`, `reopened_dismissal_count`。ユーザーが workflow として依頼していない限り、core の一部として inject / realign を実行しない。

## Inject 手順

inject は、ユーザーが課題用 constraints を必要としており、まだ回答や実装案を求めていない場合に使う。

1. 明示された prompt と現在の会話区間から task を定義する。
2. task と会話区間から search keys を生成する。
3. 3 path の Agentic Search を行う。各 `spec-anchor inject-*` コマンドは freshness blocked / failed / watcher 実行中のとき自動的に停止指示 (`should_stop=true`) を返す。返却 JSON の `blocking_reasons` に dirty / stale / watcher 系の理由がある場合、core/watch を実行または待機するようユーザーに伝える。`/spec-core` は自動実行しない。pending な矛盾 (`pending_conflict_items`) は停止理由ではなく注入情報なので、search は実行でき、課題に関係する矛盾は制約とともに人間へ提示する (却下を強制しない)。path は必須ではなく許可。課題の性質に応じて組み合わせる。
   - いずれか 1 つの `spec-anchor inject-*` が `should_stop=true`、`status="blocked"`、`status="failed"`、または `status="error"` を返した時点で、他の inject path、Source Specs の Read、constraints 生成へ進まず即停止する。停止後に追加の `spec-anchor inject-*` を試してはならない。
   - **path ① Qdrant section-level retrieval** (主経路): `spec-anchor inject-search "<query>"` で hybrid retrieval → hits の payload (heading_path / summary / search_keys / identifiers / related_sections) を読む → related_sections の target を `spec-anchor inject-section "<id>"` で payload lookup → Source Specs 本文を Read で確認 → 再帰的に辿り、制約に無関係と判断できた時点で打ち切り
   - **path ② chapter anchor** (章単位エントリ): `spec-anchor inject-chapters` で `chapter_anchors_path` を取得 → `Read` で読む (大きい場合は部分取得) → summary / key_topics / important_sections で関係しそうな章を特定 → path ① と同様に Agentic Search
   - **path ③ Purpose / Core Concept**: `spec-anchor inject-purpose` で `purpose` (全文) と `core_concept_path` を取得 → Purpose 全文から制約根拠を抽出 → `core_concept_path` は `Read` で課題に関連する部分だけを部分取得して制約根拠を抽出 (Core Concept は大きくなる可能性があるため一括投入しない)
   - path 選択の指針: 具体的 API / 識別子 → ①主 + ③補強、全体方針 / 抽象的 → ②主 + ①③補強、Purpose / Core Concept 直接質問 → ③主 + ①②補強
   - ユーザーが全文レビューを明示しない限り、Source Specs full text を最終 context に丸ごと貼らない。
4. constraints JSON array を作る。各 constraint は `statement`, `evidence_origin`, `evidence_ref`, `support_refs`, `applicability`, `uncertainty` を持つ。`evidence_origin` は Purpose、Core Concept、Source Specs のいずれかに限る。Section Summary、Search Keys、Related Sections、Chapter Key Anchor は `support_refs` にだけ置ける。これらを sole evidence にしない。
5. constraints の構造を自己点検する: 各 constraint で `statement` / `evidence_origin` / `evidence_ref` / `applicability` が非空、`evidence_origin` は Purpose / Core Concept / Source Specs のいずれか、`support_refs` は list。CLI は構造検証を行わないため、Agent 自身が確認する。
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

良い例: `evidence_ref` は実在する Purpose / Core Concept / Source Specs の path + section id を指す。`statement` は evidence から直接言える内容だけにする。迷いがある場合は `uncertainty` に短く書き、断定しない。

禁止例: `evidence_origin` に Section Summary / Related Sections / Chapter Key Anchor を入れない。`evidence_ref` を「たぶん関連」「上の要約」など曖昧にしない。`support_refs` だけを根拠にした constraint を作らない。CLI validation failed の場合、field を削って通そうとせず、引用元 snippet を読み直して constraints JSON を再生成する。

## Realign 手順

realign は、ユーザーが constraints と回答または実装方針を必要としている場合に使う。

1. Inject Workflow を実行し、validated constraints まで進める。
2. validated constraints に従う answer candidate を作る。answer が constraint と衝突する場合、隠さず human review として明示する。
3. answer candidate は次の 4 区分を区別する: `今回守る制約`, `今回扱う修正候補または検討対象`, `競合 / 不確実性 / 人間レビューが必要な点`, `課題プロンプトへの回答または修正案`。
4. CLI で答案を整形する: `spec-anchor realign --answer-json '<json-object>'`。constraints は answer の `今回守る制約` セクション内に書く (CLI は constraints の真偽を検証しない、Agent の責務)。返却 payload を constraint-checked answer として扱う。freshness gate が blocked / failed なら停止指示が返るので、ユーザーに伝える。この場合、停止後に追加の `spec-anchor inject-*`、Source Specs の Read、answer 整形へ進まない。

## エラー時の復旧手順

CLI が `should_stop=true`、`status="blocked"`、`status="failed"`、または `status="error"` を返した場合、CLI の `recommended_next_action` を解釈して日本語で次の操作を示し、存在しない復旧 command を追加提案しない。特に `spec-anchor status` は本 contract の command ではないため提案しない。

- `.spec-anchor/config.toml not found under {root}` のときは `spec-anchor-setup-project --target <project_root>` を提案する。
- `blocking_reasons` に dirty / stale / watcher 系 (`dirty_or_stale_source` / `stale_config_or_schema` / `watcher_running` / `watcher_queue_pending`) があるときは、CLI の `recommended_next_action` を日本語で伝え、`/spec-core` を自動実行しない。
- `pending_conflict_items` がある場合は停止理由ではなく注入情報である。各 item について `conflict_id` / `severity` / `claims` / `why_conflicting` / `why_llm_cannot_decide` / `source_refs` / item 側の `recommended_next_action` を人間向け見出しに翻訳して提示する。item 側が `"Ask a human to decide this conflict."` なら、「人間判断で衝突を解消してください」と訳す。矛盾の省略を contract violation として扱う。矛盾ではないと人間が明示したときだけ `spec-anchor core --dismiss-conflict <conflict_id> --reason "..."` で却下を永続化し、実行した CLI と結果を会話に出す。
- `blocking_reasons=["failed_required_artifact"]` のときは、CLI の `recommended_next_action` を日本語で伝え、`warnings` の失敗詳細を提示する。
- `stop_reason="needs_agent_answer"` のときは、4 区分 answer candidate が必要であることを日本語で伝える。

## 停止時のユーザー向け出力フォーマット

freshness blocker または tool error で停止する場合は、停止した command、理由、次に人間が実行すべき操作を日本語で示す。raw JSON は貼らない。

## pending conflict の本文展開フォーマット

pending conflict がある場合は件数だけで済ませず、各 item の `conflict_id`、`severity`、`claims`、`why_conflicting`、`why_llm_cannot_decide`、`source_refs`、`recommended_next_action` の値を人間向け見出しへ置き換えて提示する。課題に関連する pending conflict がある `/spec-realign` では答案を生成しない。

## 答案なし呼び出しの自動再実行

`spec-anchor realign` が `stop_reason="needs_agent_answer"` を返した場合、Agent は 3 path の Agentic Search で constraints を作り、4 区分 answer candidate を組み立てて `spec-anchor realign --answer-json` を再実行する。利用者には内部停止信号ではなく最終 4 区分を提示する。

## 正常完了時のユーザー向け出力フォーマット

`spec-anchor core` の正常完了時は、更新された仕様、失敗した仕様、Retrieval / Related Sections / Conflict Review Items の状態、pending conflict の有無、stale dismissal の有無を人間語で分けて報告する。`/spec-inject` は constraints だけを提示し、`/spec-realign` は 4 区分 answer を提示する。

## ユーザー向け本文に貼ってはいけない内部用語

`should_stop`、`blocking_reasons`、`freshness_report`、`pending_conflict_count`、`stale_dismissal_count`、`section_metadata_generation`、`recommended_next_action` などの内部 field 名は、利用者向け本文では人間語へ翻訳する。コマンド名、file path、識別子だけ原文を残す。

Purpose と Core Concept は人間が維持する。自動更新しない。
