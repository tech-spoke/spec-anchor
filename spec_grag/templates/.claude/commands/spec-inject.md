---
description: 課題用 SPEC-grag constraints を準備する。回答は出さない
argument-hint: "[課題]"
allowed-tools: Read, Grep, Glob, Bash(spec-grag inject*), Bash(spec-grag realign*)
---

# /spec-inject

正本は SPEC-grag の外部 command contract と SPEC-grag CLI の入出力である。この Claude command template は独立した仕様ではない。

ユーザーが課題固有 constraints を必要としており、まだ最終回答や実装を求めていない場合に `/spec-inject` を使う。

## 必須手順

1. 明示された argument と現在の会話区間から task を定義する。会話区間は search と constraint generation の補助に使うが、final evidence ではない。
2. task と会話区間から search keys を生成する。
3. 4 path の Agentic Search を行う。各 `spec-grag inject-*` コマンドは freshness が blocked / failed のとき、または `spec-grag-watch` 実行中のとき、または pending Conflict Review Item があるとき自動的に停止指示 (`should_stop=true`) を返す。返却 JSON の `blocking_reasons` に dirty / stale / watcher 系の理由がある場合、`/spec-core` または watcher を実行・待機するようユーザーに伝える。`/spec-core` は自動実行しない。唯一の blocker が pending conflict の場合、Conflict Review Items と decision choices を人間に提示する。path は必須ではなく許可。課題の性質に応じて組み合わせる。

### path ① Qdrant section-level retrieval (Source Specs 探索の主経路)

a. search keys で hybrid retrieval を呼ぶ: `spec-grag inject-search "<query>"`
b. 返ってきた hits の payload (heading_path / summary / search_keys / identifiers / related_sections) を読み、制約に関連しそうな候補を選ぶ
c. 候補 section の related_sections 配列から target_section_id を取得し、payload lookup する: `spec-grag inject-section "<target_id>" [<target_id>...]`
d. 必要なら Source Specs ファイル本文を Read で確認し、制約根拠を抽出する
e. c-d を再帰的に適用する (最大数 hop)。制約に関係しないと判断できた時点で打ち切る

### path ② chapter_anchors.json による章単位エントリ

a. 章 anchor の path を取得する: `spec-grag inject-chapters`
b. 返ってきた `chapter_anchors_path` を `Read` で読む。章数が多い場合は必要な範囲だけ部分取得する
c. 各 chapter の summary / key_topics / important_sections を見て、今回の課題に関連しそうな章を特定する
d. 特定された章配下の section を path ① と同様に Agentic Search で読み、制約を抽出する

### path ③ Purpose / Core Concept からの制約抽出

a. Purpose 全文と Core Concept path を取得する: `spec-grag inject-purpose`
b. 返ってきた `purpose` (全文) から課題に該当する制約根拠を抽出する
c. 返ってきた `core_concept_path` を `Read` で読み、課題に関連する箇所だけを部分取得して制約根拠を抽出する。Core Concept は大きくなる可能性があるため一括投入しない

### path ④ resolved Conflict Review Items の確認

a. resolved + stale でない items を取得する: `spec-grag inject-conflicts`
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
5. constraints の構造を自己点検する: 各 constraint で `statement` / `evidence_origin` / `evidence_ref` / `applicability` が非空文字列であること、`evidence_origin` が `Purpose` / `Core Concept` / `Source Specs` / `Conflict Review Item` のいずれかであること、`Section Summary` / `Search Keys` / `Related Sections` / `Chapter Key Anchor` を `evidence_origin` に置かないこと、`support_refs` が list であること。`evidence_origin = "Conflict Review Item"` の場合、`spec-grag inject-conflicts` の返却に含まれる items (resolved + stale でない) だけを参照する。CLI は構造検証を行わないため、Agent 自身が確認する。
6. constraint set、evidence list、Agentic Search summary だけを出力する。`/spec-inject` では task への回答や最終案を出さない。

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

Purpose と Core Concept は人間が維持する read-only input である。両ファイルは変更しない。`.spec-grag/config.toml` の `[llm]` provider は使わない。`/spec-inject` はこの command を実行している Agent / LLM が担当する。
