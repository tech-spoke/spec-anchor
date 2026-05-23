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
2. project root で gate probe を実行する: `spec-anchor inject "$TASK"`。command が non-zero exit でも JSON を読む。freshness が blocked / failed の場合は停止する。`blocking_reasons` に dirty / stale / watcher 系の理由がある場合、`/spec-core` または watcher を実行・待機するようユーザーに伝える。`/spec-core` は自動実行しない。唯一の blocker が pending conflict の場合、Conflict Review Items と decision choices を人間に提示する。probe が `needs_agent_constraints` を返した場合は続行する。
3. task と会話区間から search keys を生成する。
4. 4 path の Agentic Search を行う。path は必須ではなく許可。課題の性質に応じて組み合わせる。

### path ① Qdrant section-level retrieval (Source Specs 探索の主経路)

a. search keys で hybrid retrieval を呼ぶ: `spec-anchor inject-search "<query>" --top-k 8`
b. 返ってきた hits の payload (heading_path / summary / search_keys / identifiers / related_sections) を読み、制約に関連しそうな候補を選ぶ
c. 候補 section の related_sections 配列から target_section_id を取得し、payload lookup する: `spec-anchor inject-section "<target_id>" [<target_id>...]`
d. 必要なら Source Specs ファイル本文を Read で確認し、制約根拠を抽出する
e. c-d を再帰的に適用する (最大数 hop)。制約に関係しないと判断できた時点で打ち切る

### path ② chapter_anchors.json による章単位エントリ

a. 章 anchor を取得する: `spec-anchor inject-chapters`
b. 返ってきた chapters の summary / key_topics / important_sections を読み、関係しそうな章を特定する
c. 特定された章配下の section を path ① と同様に Agentic Search で読み、制約を抽出する

### path ③ Purpose / Core Concept からの制約抽出

a. Purpose + Core Concept の全文を取得する: `spec-anchor inject-purpose`
b. 課題に該当する制約根拠を抽出する

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

5. constraints JSON array を作る。各 constraint は `statement`, `evidence_origin`, `evidence_ref`, `support_refs`, `applicability`, `uncertainty` を持つ。
6. Agent-generated constraints を CLI で検証する: `spec-anchor inject "$TASK" --constraints '<json-array>'`。CLI は supplied constraints を検証し、fallback constraints を生成しない。検証に失敗した場合、constraints を直すか blocker として報告する。
7. validated constraint set、evidence list、Agentic Search summary だけを出力する。`/spec-inject` では task への回答や最終案を出さない。

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

## CLI 出力と人間向け整形

`spec-anchor inject-*` の戻り値は **stdout に出る内部 JSON** であり、CLI 自身は人間向け整形を持たない (外部設計書 §8.5)。Agent はこの JSON を読んで、ユーザー宛の会話に対して次の 5 セクション構造で整形する。各セクションは、該当 0 件のときも「該当なし」を明示する。セクション自体の省略は許可しない。

```text
今回守る制約
  - <statement>
    根拠: <evidence_origin> / <evidence_ref>
    参照補助: <support_refs (origin/ref) の要約>

今回見るべき対象
  - <Section または topic>
    理由: <なぜ今回関係するか>

関連先として確認したもの
  - <related Section>
    理由: <depends / impacts / related / conflicts など>

採用しなかったもの
  - <候補>
    理由: <今回の課題には遠い / 根拠不足 / 別論点>

不確実性 / 人間確認
  - <確認すべき点>
```

CLI の JSON を生のまま会話に貼らない。ユーザーが意図して raw JSON を求めた場合のみ JSON を出す。
