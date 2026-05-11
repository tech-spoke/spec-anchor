---
description: SPEC-grag constraints を準備し、課題へ回答する
argument-hint: "[課題]"
allowed-tools: Read, Grep, Glob, Bash(spec-grag inject*), Bash(spec-grag realign*)
---

# /spec-realign

正本は SPEC-grag の外部 command contract と SPEC-grag CLI の入出力である。この Claude command template は独立した仕様ではない。

ユーザーが課題固有 constraints と answer candidate または実装方針を必要としている場合に `/spec-realign` を使う。

## 必須手順

1. 明示された argument と現在の会話区間から task を定義する。会話区間は search、constraint generation、answer drafting の補助に使うが、final evidence ではない。
2. project root で gate probe を実行する: `spec-grag inject "$TASK"`。command が non-zero exit でも JSON を読む。freshness が blocked / failed の場合は停止する。`blocking_reasons` に dirty / stale / watcher 系の理由がある場合、`/spec-core` または watcher を実行・待機するようユーザーに伝える。`/spec-core` は自動実行しない。唯一の blocker が pending conflict の場合、Conflict Review Items と decision choices を人間に提示する。probe が `needs_agent_constraints` を返した場合は続行する。
3. task と会話区間から search keys を生成する。
4. `/spec-inject` と同じ 4 path の Agentic Search を行う (path ① inject-search + inject-section、path ② inject-chapters、path ③ inject-purpose、path ④ inject-conflicts)。各 path の手順は `/spec-inject` template を参照。
5. constraints JSON array を作る。各 constraint は `statement`, `evidence_origin`, `evidence_ref`, `support_refs`, `applicability`, `uncertainty` を持つ。
6. Agent-generated constraints を CLI で検証する: `spec-grag inject "$TASK" --constraints '<json-array>'`。CLI は supplied constraints を検証し、fallback constraints を生成しない。検証に失敗した場合、constraints を直すか blocker として報告する。
7. validated constraints に従う answer candidate を作る。answer が constraint と衝突する場合、隠さず human review として明示する。
8. answer candidate は次の 4 区分を区別する: `今回守る制約`, `今回扱う修正候補または検討対象`, `競合 / 不確実性 / 人間レビューが必要な点`, `課題プロンプトへの回答または修正案`。
9. CLI で検証する: `spec-grag realign "$TASK" --constraints '<json-array>' --answer-json '<json-object>'`。返却 payload を constraint-checked answer として扱う。検証に失敗した場合、answer を直すか blocker として報告する。

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

Purpose と Core Concept は人間が維持する read-only input である。両ファイルは変更しない。`.spec-grag/config.toml` の `[llm]` provider は使わない。`/spec-realign` はこの command を実行している Agent / LLM が担当する。
