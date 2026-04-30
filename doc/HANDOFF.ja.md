# spec-grag 実装引き継ぎ

> 最終更新: 2026-04-30
> 位置づけ: 実装・調査結果の現在地メモ。外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md`、作業順は `doc/TODO.md` を正とする。

このファイルは、次の作業者が「どこまで実装・検証済みか」「何を前提に進めてよいか」を短時間で把握するための引き継ぎである。設計判断そのものを変更する場所ではない。

Phase 1 の詳細な結果・気づき・問題点・残リスクは `doc/PHASE1_REPORT.ja.md` を参照する。Phase 2 の結果は `doc/PHASE2_REPORT.ja.md`、Phase 3 の結果は `doc/PHASE3_REPORT.ja.md`、Phase 4 の結果は `doc/PHASE4_REPORT.ja.md`、Phase 5 の結果は `doc/PHASE5_REPORT.ja.md`、Phase 6 の結果は `doc/PHASE6_REPORT.ja.md` を参照する。

## 現在地

- フェーズ: Phase 6 設定・運用・品質基盤 完了
- 方針: MVP 縮小ではなく、外部設計を満たす方向で内部契約を実装する
- 実装済み: JSON protocol / CLI transport / manifest reconciliation / strict config validation / embedding metadata + rebuild guard / Ollama embedding provider 接続 / conservative grounding scoring / Classification LLM mode + fallback / Codex CLI adapter / Claude CLI adapter / adapter retry・backoff・timeout・schema repair / extraction schema / provenance-based stale delete / vector retrieval pattern / 4 軸 transient annotation / CLI 出力の local schema validation / sidecar artifacts / sidecar corruption recovery / Concept diff pending-apply protocol / LLM Concept diff proposal / Core Concept index / Concept diff 候補生成 / `/spec-core` E2E / `/spec-inject` / `/spec-realign` / 外部契約 E2E / schema LLM extraction path の `/spec-core` 接続 / Codex・Claude 実機 smoke / Core Concept index retrieval / graph+vector+keyword retrieval merge / ChapterAnchor・cluster retrieval 統合 / Conflict validator deterministic rule pack / Agentic search 複数 request・excerpt validation / AgenticSearchCandidate source_span strict validation / Answer LLM provider config / Answer prompt + structured schema / Answer partial recovery / Answer phase NeedMoreContext block / ConflictNotes・ReviewNotes 可視化 / slash wrapper / CLI fixture / run artifact / smoke scripts
- 未実装の大きな塊: Answer LLM 実機 smoke、実運用ログに基づく retrieval / prompt 品質調整

## 実装済みファイル

| ファイル | 内容 |
|---|---|
| `pyproject.toml` | Python package 定義、`spec-grag = spec_grag.cli:main` |
| `spec_grag/config.py` | `.spec-grag/config.toml` の strict schema validation。source include / storage path / provider / model / timeout / retry 設定を正規化 |
| `spec_grag/embedding.py` | embedding provider / model / dimension metadata、stable hash fallback embedding、Ollama embedding API 接続、metadata mismatch 判定 |
| `spec_grag/protocol.py` | `SlashCommandRequest` / `ResultEnvelope` / `NeedMoreContextResult` / `AgenticSearchCandidate` / `CoreResult` / `InjectionContext` / `RealignResult` 等 |
| `spec_grag/cli.py` | stdin JSON -> stdout JSON の CLI entrypoint。`/spec-core` / `/spec-inject` / `/spec-realign` を dispatch |
| `spec_grag/manifest.py` | Markdown heading manifest、section hash、atomic write、ok/degraded/blocked/failed 時の更新規則、構造変更 reconciliation |
| `spec_grag/llm_adapters.py` | `CodexCLIAdapter(CustomLLM)` / `ClaudeCLIAdapter(CustomLLM)`。`complete` / `stream_complete` / `metadata` 実装、structured output 対応 |
| `spec_grag/extraction.py` | 4 entity / 6 relation schema、日本語 extraction prompt、`SchemaLLMPathExtractor` factory、抽出 provenance |
| `spec_grag/graph_ops.py` | `source_section_id` 等に基づく provenance-based `safe_delete_by_section` |
| `spec_grag/retrieval.py` | vector TextNode 正規パターン、keyword fallback、4 軸 transient annotation |
| `spec_grag/sidecars.py` | `unresolved_relations` / `chapter_anchors` / `cluster_snapshot` の sidecar schema、atomic write、dirty/stale 更新、corrupt/version mismatch quarantine |
| `spec_grag/concept_diff.py` | pending Concept diff、hunk accept/reject/revise/apply、hash 衝突検出 |
| `spec_grag/concept_index.py` | Core Concept index。concept_file chunking、concept_index.json、hash-based refresh、Source-derived / LLM structured Concept diff proposal |
| `spec_grag/core.py` | Phase 1 deterministic `/spec-core` E2E update。manifest / graph / vector / sidecar を更新 |
| `spec_grag/core_extraction.py` | Phase 2 schema LLM extraction path。config 切替、Codex / Claude provider、provenance 付与、conservative target grounding scoring、unresolved sidecar、低信頼 relation 除外、incremental carry-forward |
| `spec_grag/injection.py` | `/spec-inject` context build。Core Concept index / graph+vector+keyword / ChapterAnchor / cluster / Agentic search 候補を統合し、4 軸 annotation と Validator を経て InjectionContext を構築。Classification LLM mode と deterministic rule pack を含む |
| `spec_grag/realign.py` | Answer phase isolation 境界。`task_prompt + InjectionContext` だけを入力に、template fallback または Codex / Claude Answer LLM provider で 4 区分回答を生成 |
| `spec_grag/run_artifacts.py` | `[run] save_artifacts` 有効時に request / response / execution metadata を保存 |
| `scripts/` | slash wrapper、CI smoke、large source smoke、実 `テスト用ドキュメント/` smoke |
| `tests/` | protocol / CLI / fixture / manifest / adapter / extraction / graph ops / retrieval / sidecar / concept index / concept diff / core E2E / schema extraction / inject-realign / external contract E2E / Phase 6 operations |

## 検証結果

2026-04-30 時点:

```text
uv run --isolated --with pytest pytest -q
115 passed in 79.62s
```

追加 smoke:

```text
scripts/ci-smoke.sh
115 passed in 79.62s
{"status": "ok", "updated_sources": 12}
{"command": "spec-core", "status": "ok"}
{"command": "spec-inject", "status": "ok"}
{"command": "spec-realign", "status": "ok"}

uv run --isolated --with pytest --with pydantic --with llama-index-core --with markdown-it-py python scripts/performance_smoke.py
{"status": "ok", "updated_sources": 12}

uv run --isolated --with pytest --with pydantic --with llama-index-core --with markdown-it-py python scripts/real_docs_smoke.py
{"command": "spec-core", "status": "ok"}
{"command": "spec-inject", "status": "ok"}
{"command": "spec-realign", "status": "ok"}
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
- Phase 6 で `max_retries` / `retry_backoff_sec` / `repair_on_schema_failure` を Codex / Claude adapter に追加。subprocess timeout は `CLIAdapterError` に変換し、schema 違反時は repair prompt で再試行できる

### Config validation

`.spec-grag/config.toml` は `spec_grag/config.py` の strict schema を通してから各 command に渡す。未知の top-level table / section key、型不一致、空文字 path、unsupported provider、timeout / retry 範囲外は `config_invalid` の `ErrorResult` として command 実行前に止める。

現在 validate する主要項目:

- `[sources] include / exclude`
- `[core] purpose_file / concept_file / extraction_mode`
- `[graph] storage`
- `[extraction] mode / provider / command / model / timeout_sec / max_retries / retry_backoff_sec / repair_on_schema_failure / max_triplets_per_chunk / num_workers / grounding_score_threshold / grounding_score_margin`
- `[answer] provider / command / model / timeout_sec / max_retries / retry_backoff_sec / repair_on_schema_failure / sandbox / tools`
- `[classification] provider / command / model / timeout_sec / retry / fallback`
- `[concept_diff] provider / command / model / timeout_sec / retry / fallback`
- `[embedding] provider / model / dimension / timeout_sec / retry`
- `[run] save_artifacts / artifact_dir / include_request`
- 互換用 `[llm]`

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

Graph retrieval は manifest seed / keyword match / embedding similarity / relation traversal を merge し、候補を `target_context.related_entities` に入れる。embedding 未指定時は stable hash fallback、`[embedding] provider = "ollama"` 指定時は Ollama `/api/embeddings` を使う。

ChapterAnchor と cluster snapshot は retrieval 候補として InjectionContext に統合済み。cluster は外部契約に専用 top-level field を増やさず、`related_entities` の `entity_type=CLUSTER` として保持する。

### 4 軸 annotation と Validator

4 軸分類は Orchestrator rule-based classifier を fallback とし、`[classification] provider = "codex" | "claude"` で Classification LLM mode を使える。各 item は `constraint_relevance` / `target_relevance` / `semantic_conflict_candidate` / `review_required` / `classification_source` を持つ。壊れた LLM output は採用せず、rule-based fallback に戻して `review_required=true` とする。

Conflict validator は deterministic rule pack を実装済み。`REFINES` cycle、required/optional、必ず/任意、全て/一部、MUST vs MUST NOT、禁止 vs 必須、上限値 / 下限値、権限条件、状態遷移、Concept vs Source spec の候補を扱う。一方、semantic conflict candidate だけでは `conflict=true` に昇格せず review note に落とす。

### AgenticSearchCandidate source_span validation

Phase 6 着手として `AgenticSearchCandidate.source_span` の strict validation を追加した。明示 span は 1-based line range として parse し、実ファイル範囲、section 範囲、span 本文内の excerpt containment を検証する。明示 span が valid なら、同じ excerpt が別箇所にあっても invalid にしない。

`source_span` がない場合は excerpt から section 内の位置を逆引きし、0 件なら `excerpt_not_found_in_source_section`、複数件なら `ambiguous_excerpt_in_source_section` として候補を reject し `ReviewNotes` に落とす。

### Embedding provider 方針

日本語仕様文書の retrieval 品質を優先し、実 embedding provider の標準は Ollama `bge-m3`（dim=1024）とする。dim=768 互換が必要な既存 index / storage では `nomic-embed-text-v2-moe` を代替候補にし、`nomic-embed-text` / `nomic-embed-text:v1.5` は legacy / English-oriented として日本語仕様書 RAG の標準にしない。

Phase 6 で embedding provider / model / dimension を config 化し、graph / vector / concept index metadata に保存済み。metadata と config が不一致の場合は混在させず、incremental run を `failed` にして `--all` rebuild を要求する。Concept index は concept_file hash が同じでも embedding metadata が変われば再生成する。

embedding 未指定時の互換 fallback は stable hash（dim=8）である。`[embedding] provider = "ollama"` 指定時は Ollama `bge-m3` などの provider / model / dimension を受け取り、dimension mismatch は provider error として扱う。

### Answer phase isolation

Answer 生成 phase では追加 Agentic search / raw source read / tool 利用を許可しない。情報不足は `NeedMoreContextResult` / `blocked` として context build loop に戻す。CLI の read-only sandbox は補助であり、phase contract の代替ではない。

Phase 5 では `AnswerSections` schema と固定 prompt を追加し、`[answer] provider = "codex" | "claude" | "template"` で Answer provider を選択可能にした。デフォルトは `template` fallback で、実 LLM 呼び出し時も `generate_realign_answer(task_prompt, injection_context, llm=...)` は project_root / path / raw source handle を受け取らない。

Answer LLM が `needs_more_context=true` を返した場合、`/spec-realign` は `RealignResult` を生成せず `NeedMoreContextResult` / `blocked` に戻す。LLM が ConflictNotes / ReviewNotes を省略しても、renderer 側で必ず回答の「競合 / 不確実性 / 人間レビュー」区分に差し戻す。

`[answer] failure_fallback = "template"` 指定時は、Answer LLM の invalid JSON / schema violation / adapter failure を template answer に degrade recovery する。未指定時は従来どおり `answer_generation_failed`。

### Claude structured_output

Claude の `--json-schema` 成功時は、schema 準拠値が top-level `structured_output` に入り、`result` には説明文が入ることがある。`extract_cli_text()` は `structured_output` を優先して JSON 文字列へ変換する。

### Concept diff blocked

Concept diff 未承認時は現状どおり一回止める。`[concept_diff] provider = "codex" | "claude"` で LLM structured proposal を使えるが、LLM は Concept を直接更新せず、evidence span 付き proposal を返すだけである。CLI が proposal を検証し、既存の pending Concept diff hunk / accept / reject / revise / apply に接続する。`--ignore-pending` のような回避オプションは今は入れない。

### Run artifact / recovery / smoke

`[run] save_artifacts = true` 指定時、request / response / execution metadata を `.spec-grag/runs/*.json` に保存する。壊れた sidecar JSON または version mismatch は `.corrupt-<hash>` に隔離し、空 sidecar から再構築できる。

運用スクリプト:

- `scripts/spec-grag-slash.py`: slash command wrapper
- `scripts/ci-smoke.sh`: CI 用 smoke
- `scripts/performance_smoke.py`: large source set smoke
- `scripts/real_docs_smoke.py`: 実 `テスト用ドキュメント/` smoke

### Markdown parser

manifest parser は `markdown-it-py` の CommonMark preset に切り替え済み。ATX / Setext heading、fenced code、HTML block は parser の構文解釈に従う。blockquote / list item 内の heading は source spec の section 境界として扱わない。

`source_manifest.json` には `parser_name` / `parser_version` を記録する。前回 manifest と parser metadata が異なる場合は、同一 `section_id` でも changed section として扱い、stale artifact を再生成対象にする。

## 次の作業

Phase 6 checklist は完了。次は実運用ログを見ながら、retrieval / grounding threshold / Classification prompt / Answer prompt の品質調整を行う。

## 作業時の注意

- `doc/EXTERNAL_DESIGN.ja.md` は外部契約。ユーザーの明示指示なしに縮小・変更しない
- `doc/DESIGN.ja.md` は内部設計。議論ログや作業メモを混ぜない
- 各 Phase の完了時には、Phase 1 と同様に `doc/PHASE<N>_REPORT.ja.md` を作成または最終化し、実装結果・検証結果・気づき・問題点・簡易実装・残リスク・次 Phase への申し送りを記録する
- このリポジトリは未コミット変更が多い。自分が触っていない変更を revert しない
- 実 `テスト用ドキュメント/` smoke は一時ディレクトリへ copy して実行するため、元ファイルは変更しない
- `doc/CLAUDE_NOTES.md` には古いセッション引き継ぎも含まれる。最新の現在地は本ファイルと `doc/TODO.md` を優先する
