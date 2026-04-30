# spec-grag 実装引き継ぎ

> 最終更新: 2026-04-30
> 位置づけ: 実装・調査結果の現在地メモ。外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md`、作業順は `doc/TODO.md` を正とする。

このファイルは、次の作業者が「どこまで実装・検証済みか」「何を前提に進めてよいか」を短時間で把握するための引き継ぎである。設計判断そのものを変更する場所ではない。

Phase 1 の詳細な結果・気づき・問題点・残リスクは `doc/PHASE1_REPORT.ja.md` を参照する。Phase 2 の結果は `doc/PHASE2_REPORT.ja.md`、Phase 3 の結果は `doc/PHASE3_REPORT.ja.md`、Phase 4 の結果は `doc/PHASE4_REPORT.ja.md`、Phase 5 の結果は `doc/PHASE5_REPORT.ja.md` を参照する。Phase 6 は未完了であり、現時点の中間記録は `doc/PHASE6_REPORT.ja.md` を参照する。

## 現在地

- フェーズ: Phase 6 設定・運用・品質基盤 着手中
- 方針: MVP 縮小ではなく、外部設計を満たす方向で内部契約を実装する
- 実装済み: JSON protocol / CLI transport / manifest reconciliation / Codex CLI adapter / Claude CLI adapter / extraction schema / provenance-based stale delete / vector retrieval pattern / 4 軸 transient annotation / CLI 出力の local schema validation / sidecar artifacts / Concept diff pending-apply protocol / Core Concept index / Concept diff 候補生成 / `/spec-core` E2E / `/spec-inject` / `/spec-realign` / 外部契約 E2E / schema LLM extraction path の `/spec-core` 接続 / Codex・Claude 実機 smoke / Core Concept index retrieval / graph+vector+keyword retrieval merge / ChapterAnchor・cluster retrieval 統合 / Conflict validator deterministic checks / Agentic search 複数 request・excerpt validation / AgenticSearchCandidate source_span strict validation / Answer LLM provider config / Answer prompt + structured schema / Answer phase NeedMoreContext block / ConflictNotes・ReviewNotes 可視化
- 未実装の大きな塊: slash command wrapper、strict config validation、実 embedding provider 接続、実ドキュメント規模 smoke、Classification LLM provider の実呼び出し、Answer LLM 実機 smoke

## 実装済みファイル

| ファイル | 内容 |
|---|---|
| `pyproject.toml` | Python package 定義、`spec-grag = spec_grag.cli:main` |
| `spec_grag/protocol.py` | `SlashCommandRequest` / `ResultEnvelope` / `NeedMoreContextResult` / `AgenticSearchCandidate` / `CoreResult` / `InjectionContext` / `RealignResult` 等 |
| `spec_grag/cli.py` | stdin JSON -> stdout JSON の CLI entrypoint。`/spec-core` / `/spec-inject` / `/spec-realign` を dispatch |
| `spec_grag/manifest.py` | Markdown heading manifest、section hash、atomic write、ok/degraded/blocked/failed 時の更新規則、構造変更 reconciliation |
| `spec_grag/llm_adapters.py` | `CodexCLIAdapter(CustomLLM)` / `ClaudeCLIAdapter(CustomLLM)`。`complete` / `stream_complete` / `metadata` 実装、structured output 対応 |
| `spec_grag/extraction.py` | 4 entity / 6 relation schema、日本語 extraction prompt、`SchemaLLMPathExtractor` factory、抽出 provenance |
| `spec_grag/graph_ops.py` | `source_section_id` 等に基づく provenance-based `safe_delete_by_section` |
| `spec_grag/retrieval.py` | vector TextNode 正規パターン、keyword fallback、4 軸 transient annotation |
| `spec_grag/sidecars.py` | `unresolved_relations` / `chapter_anchors` / `cluster_snapshot` の sidecar schema、atomic write、dirty/stale 更新 |
| `spec_grag/concept_diff.py` | pending Concept diff、hunk accept/reject/revise/apply、hash 衝突検出 |
| `spec_grag/concept_index.py` | Core Concept index。concept_file chunking、concept_index.json、hash-based refresh、Source-derived Concept diff 候補生成 |
| `spec_grag/core.py` | Phase 1 deterministic `/spec-core` E2E update。manifest / graph / vector / sidecar を更新 |
| `spec_grag/core_extraction.py` | Phase 2 schema LLM extraction path。config 切替、Codex / Claude provider、provenance 付与、target grounding、unresolved sidecar、低信頼 relation 除外、incremental carry-forward |
| `spec_grag/injection.py` | `/spec-inject` context build。Core Concept index / graph+vector+keyword / ChapterAnchor / cluster / Agentic search 候補を統合し、4 軸 annotation と Validator を経て InjectionContext を構築 |
| `spec_grag/realign.py` | Answer phase isolation 境界。`task_prompt + InjectionContext` だけを入力に、template fallback または Codex / Claude Answer LLM provider で 4 区分回答を生成 |
| `tests/` | protocol / CLI / manifest / adapter / extraction / graph ops / retrieval / sidecar / concept index / concept diff / core E2E / schema extraction / inject-realign / external contract E2E |

## 検証結果

2026-04-30 時点:

```text
uv run --isolated --with pytest pytest -q
97 passed in 57.02s
```

確認済みバージョン:

```text
codex-cli 0.125.0
Claude Code 2.1.122
jsonschema 4.26.0
llama-index-core 0.14.21
pydantic 2.13.3
pytest 9.0.3
```

## CLI 実認証 smoke

Codex:

- `codex login status` で ChatGPT ログイン済みを確認
- `codex --ask-for-approval never exec ... --output-schema ...` で schema 準拠 JSON 出力を確認
- 注意: `--ask-for-approval` は `exec` ではなく Codex 本体のトップレベルオプション。正しい順序は `codex --ask-for-approval never exec ...`
- adapter のデフォルトは `--ask-for-approval never` / `--sandbox read-only` / `--ephemeral` / `--ignore-rules` / `--skip-git-repo-check` / `--json`

Claude:

- `claude auth status` で `authMethod: claude.ai` / サブスクログイン済みを確認
- `claude --print --no-session-persistence --disable-slash-commands --tools "" --output-format json --json-schema ...` で schema 準拠 JSON 出力を確認
- 注意: `--bare` は OAuth/keychain を読まない可能性があるため、サブスク認証利用では使わない
- Claude の schema 準拠値は `result` ではなく `structured_output` に入る

schema 違反時挙動:

- 矛盾プロンプト（例: schema enum にない `Policy` を強制）では、Codex / Claude とも schema 内の値に寄せて返す傾向を確認
- ただし満たせない schema（例: `enum: []`）では、Codex / Claude とも exit 0 で schema 外の値を返し得る
- 結論: CLI-level structured output は補助。spec-grag の契約境界は adapter 側の local JSON Schema validation とする
- 実装: `spec_grag/llm_adapters.py` で `jsonschema.Draft202012Validator` による検証を追加。違反時は `CLIAdapterError`

## 重要な実装知見

### SimpleVectorStore と KG node id

`SimpleVectorStore` は query 結果で `TextNode` 本体ではなく id 中心に返すことがある。そのため `metadata[VECTOR_SOURCE_KEY]` だけでは KG node へ戻れず、`VectorContextRetriever` が 0 件になる可能性がある。

正規パターン:

```python
TextNode(
    id_=entity.id,
    metadata={
        VECTOR_SOURCE_KEY: entity.id,
        **entity.properties,
    },
    embedding=entity.embedding,
)
```

`spec_grag/retrieval.py::entity_to_vector_text_node()` はこの形にしている。`TextNode.id_` と `EntityNode.id` を一致させること。

### Retrieval metadata

`NodeWithScore.node.metadata` は自動では entity properties を持たない場合がある。retrieval 結果に provenance / source section / heading 等を伝播するため、vector store 投入時に `TextNode.metadata` へ entity properties をコピーする。

### Phase 4 retrieval merge

`/spec-inject` は Concept file を直接読んで単一 summary を入れる形から、`.spec-grag/graph/concept_index.json` の chunk retrieval に切り替えた。未承認 Concept diff は従来どおり blocked で止まるため、Concept index には承認済み内容だけが入る。

Graph retrieval は manifest seed / keyword match / deterministic embedding similarity / relation traversal を merge し、候補を `target_context.related_entities` に入れる。Phase 4 時点の embedding は stable hash なので、意味検索の品質評価は Phase 6 の実 provider 接続後に行う。

ChapterAnchor と cluster snapshot は retrieval 候補として InjectionContext に統合済み。cluster は外部契約に専用 top-level field を増やさず、`related_entities` の `entity_type=CLUSTER` として保持する。

### 4 軸 annotation と Validator

Phase 4 の 4 軸分類は Orchestrator rule-based classifier で実装した。各 item は `constraint_relevance` / `target_relevance` / `semantic_conflict_candidate` / `review_required` / `classification_source` を持つ。`classification_source` 等は InjectionContext 上だけに付与し、graph store には永続化しない regression test を追加済み。

Conflict validator は段階 1/2 の deterministic checks を実装した。`REFINES` cycle と required/optional・必ず/任意・全て/一部を `conflict=true` にできる一方、semantic conflict candidate だけでは `conflict=true` に昇格せず review note に落とす。

### AgenticSearchCandidate source_span validation

Phase 6 着手として `AgenticSearchCandidate.source_span` の strict validation を追加した。明示 span は 1-based line range として parse し、実ファイル範囲、section 範囲、span 本文内の excerpt containment を検証する。明示 span が valid なら、同じ excerpt が別箇所にあっても invalid にしない。

`source_span` がない場合は excerpt から section 内の位置を逆引きし、0 件なら `excerpt_not_found_in_source_section`、複数件なら `ambiguous_excerpt_in_source_section` として候補を reject し `ReviewNotes` に落とす。

### Embedding provider 方針

日本語仕様文書の retrieval 品質を優先し、実 embedding provider の標準は Ollama `bge-m3`（dim=1024）とする。dim=768 互換が必要な既存 index / storage では `nomic-embed-text-v2-moe` を代替候補にし、`nomic-embed-text` / `nomic-embed-text:v1.5` は legacy / English-oriented として日本語仕様書 RAG の標準にしない。

Phase 6 で embedding provider / model / dimension を config 化し、graph / vector / concept index metadata に保存する。metadata と config が不一致の場合は混在させず、index rebuild を要求する。

### Answer phase isolation

Answer 生成 phase では追加 Agentic search / raw source read / tool 利用を許可しない。情報不足は `NeedMoreContextResult` / `blocked` として context build loop に戻す。CLI の read-only sandbox は補助であり、phase contract の代替ではない。

Phase 5 では `AnswerSections` schema と固定 prompt を追加し、`[answer] provider = "codex" | "claude" | "template"` で Answer provider を選択可能にした。デフォルトは `template` fallback で、実 LLM 呼び出し時も `generate_realign_answer(task_prompt, injection_context, llm=...)` は project_root / path / raw source handle を受け取らない。

Answer LLM が `needs_more_context=true` を返した場合、`/spec-realign` は `RealignResult` を生成せず `NeedMoreContextResult` / `blocked` に戻す。LLM が ConflictNotes / ReviewNotes を省略しても、renderer 側で必ず回答の「競合 / 不確実性 / 人間レビュー」区分に差し戻す。

### Claude structured_output

Claude の `--json-schema` 成功時は、schema 準拠値が top-level `structured_output` に入り、`result` には説明文が入ることがある。`extract_cli_text()` は `structured_output` を優先して JSON 文字列へ変換する。

### Concept diff blocked

Concept diff 未承認時は現状どおり一回止める。チャット上でコアコンセプトを修正し、その後に再コマンド実行する運用で進める。`--ignore-pending` のような回避オプションは今は入れない。

### Markdown parser

manifest parser は `markdown-it-py` の CommonMark preset に切り替え済み。ATX / Setext heading、fenced code、HTML block は parser の構文解釈に従う。blockquote / list item 内の heading は source spec の section 境界として扱わない。

`source_manifest.json` には `parser_name` / `parser_version` を記録する。前回 manifest と parser metadata が異なる場合は、同一 `section_id` でも changed section として扱い、stale artifact を再生成対象にする。

## 次の作業

優先順は `doc/TODO.md` の「Phase 2 以降の計画」を参照する。直近は Phase 6 として、運用設定だけでなく Graph / InjectionContext / Answer の根拠性を固める。

1. Codex / Claude CLI adapter の retry / backoff / timeout / schema failure handling を実装する
   - Answer phase では失敗時も raw source read / 追加 Agentic search に逃げない
2. `.spec-grag/config.toml` strict schema validation と provider / model / timeout / retry / storage path / source include の config validation を固める
3. embedding provider / model / dimension metadata と index rebuild 判定を実装する
4. conservative grounding scoring を実装し、曖昧候補を `unresolved_relations` / `ReviewNotes` に落とす
5. LLM Concept diff proposal を structured proposal -> CLI unified diff 変換として実装する
   - pending Concept diff JSON / hunk accept / reject / revise / apply / 未承認遮断は既存実装を維持する
6. Conflict validator の deterministic rule pack を段階的に拡張する
   - LLM 単独で `conflict=true` に昇格させず、Validator rule または human approval を経る
7. slash command wrapper と CLI fixture / run artifact を整備する
8. 実 `テスト用ドキュメント/` と large source set の smoke を実行する

詳細なチェックリストは `doc/TODO.md` を参照。

## 作業時の注意

- `doc/EXTERNAL_DESIGN.ja.md` は外部契約。ユーザーの明示指示なしに縮小・変更しない
- `doc/DESIGN.ja.md` は内部設計。議論ログや作業メモを混ぜない
- 各 Phase の完了時には、Phase 1 と同様に `doc/PHASE<N>_REPORT.ja.md` を作成または最終化し、実装結果・検証結果・気づき・問題点・簡易実装・残リスク・次 Phase への申し送りを記録する
- このリポジトリは未コミット変更が多い。自分が触っていない変更を revert しない
- `テスト用ドキュメント/` は未追跡だが、現時点ではこちらでは触っていない
- `doc/CLAUDE_NOTES.md` には古いセッション引き継ぎも含まれる。最新の現在地は本ファイルと `doc/TODO.md` を優先する
