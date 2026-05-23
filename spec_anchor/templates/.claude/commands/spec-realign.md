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
2. task と会話区間から search keys を生成する。
3. `/spec-inject` と同じ 4 path の Agentic Search を行う (path ① inject-search + inject-section、path ② inject-chapters、path ③ inject-purpose、path ④ inject-conflicts)。各 path の手順は `/spec-inject` template を参照。各 `spec-anchor inject-*` コマンドは freshness blocked / failed / watcher 実行中 / pending conflict のとき自動的に停止指示を返す。停止理由に応じて `/spec-core` または watcher を実行・待機するようユーザーに伝える。`/spec-core` は自動実行しない。
4. constraints JSON array を作る。各 constraint は `statement`, `evidence_origin`, `evidence_ref`, `support_refs`, `applicability`, `uncertainty` を持つ。
5. constraints の構造を自己点検する (spec-inject template §5 と同じ手順)。CLI は構造検証を行わないため、Agent 自身が確認する。
6. constraints に従う answer candidate を作る。answer が constraint と衝突する場合、隠さず human review として明示する。
7. answer candidate は次の 4 区分を区別する: `今回守る制約`, `今回扱う修正候補または検討対象`, `競合 / 不確実性 / 人間レビューが必要な点`, `課題プロンプトへの回答または修正案`。constraints は `今回守る制約` セクションに直接書く。
8. CLI で答案を整形する: `spec-anchor realign --answer-json '<json-object>'`。CLI は freshness gate を通したうえで answer を 4 区分の RealignResult に整形して返す。`/spec-realign` も freshness blocked / failed / watcher 実行中 / pending conflict のとき自動的に停止指示を返す。CLI は constraints の真偽は検証しない (Agent の責務)。
9. CLI の戻り値は **stdout に出る内部 JSON** (RealignResult) であり、CLI 自身は人間向け整形を持たない (外部設計書 §8.5)。Agent は JSON 内の `answer.今回守る制約` / `今回扱う修正候補または検討対象` / `競合 / 不確実性 / 人間レビューが必要な点` / `課題プロンプトへの回答または修正案` の 4 セクションを読み、ユーザー宛の会話に対して 4 区分の見出し付きで整形して出す。CLI の JSON を生のまま会話に貼らない。ユーザーが意図して raw JSON を求めた場合のみ JSON を出す。

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

Purpose と Core Concept は人間が維持する read-only input である。両ファイルは変更しない。`.spec-anchor/config.toml` の `[llm]` provider は使わない。`/spec-realign` はこの command を実行している Agent / LLM が担当する。

## エラー時の復旧手順を明示する規約

CLI が `should_stop=true` または `status="error"` を返した場合、ユーザー向けの復旧手順は具体的な command 名で提示する。

### recommended_next_action は top-level を引用する

`spec-anchor realign` の戻り値には CLI top-level `recommended_next_action` field と、参考情報として埋め込まれた `inject_result.recommended_next_action` field の 2 つが存在する。

ユーザーへの伝達には **top-level `recommended_next_action`** を引用する。これは `/spec-realign` 用に文言が正規化されており、例えば `"run /spec-core before /spec-realign"` のように realign 文脈の command 名を含む。

埋め込まれた `inject_result.recommended_next_action` は CLI 内部の inject 経路由来の文字列で、`"...before /spec-inject"` のように inject 文脈の command 名を含む。これは参考情報であり、利用者向け文言には使わない。

### CLI が返すエラー条件と対応

- `.spec-anchor/config.toml not found under {root}` のとき → `spec-anchor-setup-project --target <project_root>` で project skeleton を初期化することを提案する (例: `spec-anchor-setup-project --target /path/to/project`)。`spec-anchor init` のような存在しない command を提案しない。answer の整形は実行しない旨を明示する。
- `blocking_reasons` に `dirty_or_stale_source` / `stale_config_or_schema` / `watcher_running` / `watcher_queue_pending` が含まれるとき → top-level `recommended_next_action` (例: `"run /spec-core before /spec-realign"`) をそのまま提示し、人間判断を促す。`/spec-core` は自動実行しない。
- `blocking_reasons=["pending_conflict"]` のとき → CLI 出力の `pending_conflict_items` の各 item の `conflict_id` / `severity` / `claims` / `why_conflicting` / `why_llm_cannot_decide` / `decision_options` / `source_refs` / `recommended_next_action` を人間判断用に提示する。Agent は conflict を決めない。answer の整形は実行しない。
- `blocking_reasons=["failed_required_artifact"]` のとき → top-level `recommended_next_action` (`"run /spec-core or /spec-core --all before /spec-realign"`) と `warnings` の失敗詳細を提示し、`/spec-core --all` の実行を提案する。
- `stop_reason="needs_agent_answer"` のとき (CLI top-level `recommended_next_action="provide an Agent-generated answer candidate for /spec-realign"`) → 4 区分 (今回守る制約 / 今回扱う修正候補 / 競合・不確実性 / 課題プロンプトへの回答) で answer candidate を構成して再実行することを提案する。または利用者へ追加情報を要求する。

CLI の `recommended_next_action` field (top-level) は CLI 自身が出力する文字列をそのまま使う。Agent が再構成して別 command を提案しない。
