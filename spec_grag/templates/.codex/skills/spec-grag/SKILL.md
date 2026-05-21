---
name: spec-grag
description: 実装や回答の前に、仕様に基づくコンテキスト、freshness 確認、Source Specs に対する Agentic Search、Conflict Review Item、spec-grag core/inject/realign/watch CLI workflow が必要なときに使う。
metadata:
  short-description: 仕様に基づくコンテキスト workflow
---

# SPEC-grag

SPEC-grag は、Agent 作業中に軽量な仕様コンテキストを保持する。保持 artifact と freshness の正本は CLI である。会話区間の解釈、Agentic Search の探索方針、今回必要な constraints 生成、realign での answer 生成は Agent / LLM が担当する。

## 作業場所

`.spec-grag/config.toml` がある project root で作業する。存在しない場合、Source Specs を捏造せず、setup を自動実行しない。ユーザーに確認するか、ユーザーが setup を依頼した場合だけ `spec-grag-setup-project` を実行する。

## Core 更新

保持 artifact を更新する必要があるときは `spec-grag core` を実行する。`--all` は、ユーザーが full rebuild を明示した場合だけ追加する。`.spec-grag/config.toml` の `[llm.stage_routing]` が stage 別の最適 model / effort を適用する。`--llm-provider` を明示すると stage_routing を上書きしてしまうので、特別な事情 (provider 障害時の fallback など) がない限り指定しない。

`spec-grag core` は Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor、Source Retrieval Index、Conflict Review Items を更新する。Purpose と Core Concept は人間が維持する read-only input である。

core 実行後は、後続作業に必要な CoreResult field を報告する: `updated_sources`, `failed_sources`, `failed_sections`, `retrieval_index_status`, `freshness_report`, `pending_conflict_count`, `conflict_review_items`, `unreflected_conflict_resolutions`, `stale_resolution_count`。ユーザーが workflow として依頼していない限り、core の一部として inject / realign を実行しない。

## Inject 手順

inject は、ユーザーが課題用 constraints を必要としており、まだ回答や実装案を求めていない場合に使う。

1. 明示された prompt と現在の会話区間から task を定義する。
2. task と会話区間から search keys を生成する。
3. 4 path の Agentic Search を行う。各 `spec-grag inject-*` コマンドは freshness blocked / failed / watcher 実行中 / pending conflict のとき自動的に停止指示 (`should_stop=true`) を返す。返却 JSON の `blocking_reasons` に dirty / stale / watcher 系の理由がある場合、core/watch を実行または待機するようユーザーに伝える。`/spec-core` は自動実行しない。唯一の blocker が pending conflict の場合、Conflict Review Items と decision options を人間に提示する。path は必須ではなく許可。課題の性質に応じて組み合わせる。
   - **path ① Qdrant section-level retrieval** (主経路): `spec-grag inject-search "<query>"` で hybrid retrieval → hits の payload (heading_path / summary / search_keys / identifiers / related_sections) を読む → related_sections の target を `spec-grag inject-section "<id>"` で payload lookup → Source Specs 本文を Read で確認 → 再帰的に辿り、制約に無関係と判断できた時点で打ち切り
   - **path ② chapter anchor** (章単位エントリ): `spec-grag inject-chapters` で `chapter_anchors_path` を取得 → `Read` で読む (大きい場合は部分取得) → summary / key_topics / important_sections で関係しそうな章を特定 → path ① と同様に Agentic Search
   - **path ③ Purpose / Core Concept**: `spec-grag inject-purpose` で `purpose` (全文) と `core_concept_path` を取得 → Purpose 全文から制約根拠を抽出 → `core_concept_path` は `Read` で課題に関連する部分だけを部分取得して制約根拠を抽出 (Core Concept は大きくなる可能性があるため一括投入しない)
   - **path ④ Conflict Review Items**: `spec-grag inject-conflicts` → resolved + stale でない items を取得 → valid_scope と referenced_source_refs を確認 → 制約に組み込む
   - path 選択の指針: 具体的 API / 識別子 → ①主 + ③④補強、全体方針 / 抽象的 → ②主 + ①③④補強、Purpose / Core Concept 直接質問 → ③主 + ①②補強、過去判断の継続 → ④主 + ①③補強
   - ユーザーが全文レビューを明示しない限り、Source Specs full text を最終 context に丸ごと貼らない。
4. constraints JSON array を作る。各 constraint は `statement`, `evidence_origin`, `evidence_ref`, `support_refs`, `applicability`, `uncertainty` を持つ。`evidence_origin` は Purpose、Core Concept、Source Specs、Conflict Review Item のいずれかに限る。Section Summary、Search Keys、Related Sections、Chapter Key Anchor は `support_refs` にだけ置ける。これらを sole evidence にしない。
5. constraints の構造を自己点検する: 各 constraint で `statement` / `evidence_origin` / `evidence_ref` / `applicability` が非空、`evidence_origin` は Purpose / Core Concept / Source Specs / Conflict Review Item のいずれか、`support_refs` は list。CLI は構造検証を行わないため、Agent 自身が確認する。Conflict Review Item を根拠にする場合は `spec-grag inject-conflicts` の返却 (resolved + stale でない) だけを使う。
6. constraints、evidence、search summary だけを出力する。inject では task への回答を出さない。
7. `spec-grag inject-*` および `spec-grag realign` の戻り値は **stdout の内部 JSON** であり、CLI は人間向け整形を持たない (外部設計書 §8.5)。Agent は JSON を読んで、ユーザー宛の会話に対して `今回守る制約` / `今回見るべき対象` / `関連先として確認したもの` / `不確実性 / 人間確認` (realign は加えて 4 区分の answer) を見出し付きで整形して出す。raw JSON を会話に貼らない (ユーザーが明示的に raw を要求した場合のみ例外)。

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
4. CLI で答案を整形する: `spec-grag realign --answer-json '<json-object>'`。constraints は answer の `今回守る制約` セクション内に書く (CLI は constraints の真偽を検証しない、Agent の責務)。返却 payload を constraint-checked answer として扱う。freshness gate が blocked / failed なら停止指示が返るので、ユーザーに伝える。

Purpose と Core Concept は人間が維持する。自動更新しない。
