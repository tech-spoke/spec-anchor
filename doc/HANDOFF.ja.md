# spec-grag 実装引き継ぎ

> 最終更新: 2026-05-02
> 位置づけ: 実装・調査結果の現在地メモ。外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md`、作業順は `doc/TODO.md`、Phase 9 後の監査作業は `doc/AUDIT_TODO.ja.md` を正とする。

このファイルは、次の作業者が「どこまで実装・検証済みか」「何を前提に進めてよいか」を短時間で把握するための引き継ぎである。設計判断そのものを変更する場所ではない。

各 Phase の詳細な結果・気づき・問題点・残リスクは `doc/PHASE<N>_REPORT.ja.md` を参照する。直近は `doc/PHASE14_REPORT.ja.md`。

## 最新引き継ぎ（2026-05-02 / Phase 14 後）

この監査再開前の先頭 commit は `c45c8d9 docs: hand off remaining audit scope`。Phase 14 実装 commit は `9bafb82 feat: add classification priority budgets`、Phase 14 着手前の退避 commit は `a305dd3 chore: checkpoint before phase 14 policy`。再開時の `git status --short` は clean。

Phase 14 は実装・検証済み。`ClassificationCandidate` 収集、`classification_key` dedup、priority sort、type budget、batch classification、persistent classification cache、priority-aware incomplete policy、stage metrics 拡張を入れた。詳細は `doc/PHASE14_REPORT.ja.md`。

検証:

- `uv run --with pytest python -m pytest tests/test_phase9_production_policy.py tests/test_phase12_hardening.py tests/test_injection_realign.py tests/test_phase7_packaging.py::test_template_resources_are_packaged_for_wheel_install -q` -> `51 passed in 25.53s`
- `uv run --with pytest python -m pytest -q` -> `228 passed in 197.40s`

Phase 14 後の production self E2E:

- `spec-inject` batch 初回: total `72,489ms`、retrieval `19,104ms`、classification `53,085ms`、classification LLM calls 4、cache hit 0、`high_priority_skipped_count=0`
- `spec-inject` persistent cache 再実行: total `44,670ms`、retrieval `14,124ms`、classification `30,277ms`、classification LLM calls 3、cache hit 15、`high_priority_skipped_count=0`
- `spec-realign` batch/cache 後: total `89,423ms`、retrieval `17,615ms`、classification `28,672ms`、answer `42,844ms`、classification LLM calls 2、cache hit 19、`high_priority_skipped_count=0`
- artifact: `.spec-grag/runs/20260502T081601.899646Z-spec-inject-7b71d453395a.json`、`.spec-grag/runs/20260502T081700.397111Z-spec-inject-925565b62f5d.json`、`.spec-grag/runs/20260502T082150.417804Z-spec-realign-fd72d9ad2316.json`

classification は high priority skip なしまで改善したが、`classification_medium_priority_incomplete` は残る。これは Purpose / raw source / approved Concept を落としている状態ではなく、主に graph entity / chapter anchor / cluster 側の未分類で degraded になっている。

2026-05-02 監査追補:

- `doc/AUDIT_TODO.ja.md` の古い `classification.max_items=8` 起因 RISK は stale として Phase 14 後の PARTIAL 判定へ更新した
- medium / low priority incomplete の production policy は degraded 維持に決定。warning-only は採用しない。deferred classification は別タスクとして残す
- retrieval query set 5本を実測。Source evidence は概ね妥当だが、Concept 巨大 chunk 混入、query planner 語過多、answer 40秒台が残る
- `Concept にないが Source specs にある制約の扱い` で、type budget が tier 0 graph entity を落として `classification_high_priority_incomplete` / failed になる不具合を発見し修正した
- 修正後 artifact `.spec-grag/runs/20260502T084927.386804Z-spec-inject-2bf9dae9cfe6.json`: `status=degraded`、`high_priority_skipped_count=0`、`medium_priority_skipped_count=4`、`degraded_components=['classification']`
- 検証: `uv run --with pytest python -m pytest -q` -> `229 passed in 187.76s`

2026-05-03 監査実装追補:

- query planner: QueryPlan persistent cache を追加し、BM25 query を raw query + identifiers/entities/expected areas に分離。expanded QueryPlan は dense query 用に限定し、BM25 query terms は cap 80
- Concept retrieval: Concept index を v2 に更新し、Markdown list item を 1 concept chunk とする。readiness は旧 concept index version を stale として検出する。テンプレート導入文 chunk は query-side filter で除外
- answer: Answer prompt 用 InjectionContext compaction と Answer persistent cache を追加。cache key は freshness timestamp / classification cache-hit metadata を除外して安定化
- classification: primary budget 後の deferred classification を追加。medium / low skipped を最大 6 件追加分類し、production の silent rule-based fallback 不可は維持
- config: `[query_planner] cache_enabled/cache_path/bm25_term_limit/dense_query_max_chars`、`[answer] cache_enabled/cache_path/context_*`、`[classification] deferred_enabled/deferred_max_items` を repo / template / setup に追加

2026-05-03 実測:

- `spec-core` concept index v2 再生成: `.spec-grag/runs/20260502T153505.476508Z-spec-core-f9f636203d11.json`、`concept_index` input chunks 17、warning `concept_index_version_mismatch_rebuilt`
- retrieval query set: q1〜q4 は `classification_low_priority_incomplete` で degraded、q5 は ok。全 query で `high_priority_skipped_count=0` / `medium_priority_skipped_count=0`
- QueryPlan cache: q5 repeat `.spec-grag/runs/20260502T154138.492288Z-spec-inject-c57b13ce9e8a.json` は retrieval `4,722ms`、planner LLM calls 0、`query_plan_cache_hit=true`
- Answer cache: miss `.spec-grag/runs/20260502T154645.565178Z-spec-realign-d0c0cfd9dbbf.json` は answer `38,386ms` / LLM 1 call。hit `.spec-grag/runs/20260502T154702.759380Z-spec-realign-5aaef0f12cff.json` は answer `2.886ms` / LLM 0 call / `answer_cache_hit=true`
- 検証: focused regression `58 passed in 15.68s`、full regression `240 passed in 211.84s`

次セッションの残監査キュー:

1. Retrieval 品質の残りを見る。BM25 terms は 80 に抑えたが、candidate documents はまだ 314〜404/407 と広い。特に `section_max_heading_level` query は Source specs 側の直接語が薄く、dense の周辺 section 依存が残る。
2. cold answer latency を見る。Answer cache hit は効くが、cache miss の answer LLM はまだ 38秒台。
3. low priority incomplete の扱いを見る。medium は deferred で消えたが、q1〜q4 は low priority cluster incomplete で degraded が残る。
4. Contract / design drift 監査を進める。`EXTERNAL_DESIGN` / `DESIGN` / implementation / test / artifact matrix を埋め、`PARTIAL` を `OK` / `DRIFT` へ確定する。
5. Failure / recovery と artifact lifecycle を確認する。failed staging diagnostics、old smoke artifact から production artifact への再生成手順、stable ID 導入後の incremental alias 混入を重点に見る。
6. Security / privacy / production reachability を再確認する。mock / fake provider 到達性、query path read-only 全 entrypoint、run artifact request/response opt-in、prompt untrusted boundary を静的 trace と artifact で見る。

次セッション開始時の推奨:

```bash
git status --short
sed -n '1,140p' doc/AUDIT_TODO.ja.md
sed -n '1,180p' doc/PHASE14_REPORT.ja.md
```

`.spec-grag/cache/classification_cache.json` は ignored artifact で、warm cache の E2E 時間に効く。cold cache を測る時だけ明示的に退避または削除する。

## 現在地（Phase 9 時点の旧メモ）

- フェーズ: Phase 9 production policy gate 実装済み。Phase 9 残件は community report / semantic conflict fixture 拡充 / 実 provider 評価
- 方針: MVP 縮小ではなく、外部設計を満たす方向で内部契約を実装する
- 実装済み: JSON protocol / CLI transport / manifest reconciliation / strict config validation / production policy validation / smoke explicit mode / embedding metadata + rebuild guard / Ollama embedding provider 接続 / embedding provider fail-fast / conservative grounding scoring / Classification LLM mode + fail-fast / Codex CLI adapter / Claude CLI adapter / adapter retry・backoff・timeout・schema repair / extraction schema / provenance-based stale delete / vector retrieval pattern / 4 軸 transient annotation / CLI 出力の local schema validation / sidecar artifacts / sidecar corruption recovery / Concept diff pending-apply protocol / LLM Concept diff proposal + fail-fast / Core Concept index / Concept diff 候補生成 / `/spec-core` E2E / `/spec-inject` / `/spec-realign` / 外部契約 E2E / schema LLM extraction path の `/spec-core` 接続 / Codex・Claude 実機 smoke / Core Concept index retrieval / raw document chunk sidecar / raw chunk dense vector index / BM25 sparse lexical index / QueryPlan / hybrid chunk retrieval + RRF / raw chunk evidence InjectionContext / ChapterAnchor・cluster retrieval 統合 / Conflict validator deterministic rule pack / Agentic search 複数 request・excerpt validation / AgenticSearchCandidate source_span strict validation / Answer LLM provider config / Answer prompt + structured schema / Answer partial recovery / Answer phase NeedMoreContext block / ConflictNotes・ReviewNotes 可視化 / slash wrapper / CLI fixture / run artifact provider summary / smoke scripts / active templates / Codex command templates / project setup / system setup / fresh project smoke
- repo root の `.spec-grag/config.toml` は production policy を通る self project 設定。旧 smoke 設定は `.spec-grag/config.smoke.toml` に退避済み
- 未実装の大きな塊: community report / chapter report の本格化、semantic conflict candidate の日本語 fixture 拡充、production provider での self project 大規模評価

## 実装済みファイル

| ファイル | 内容 |
|---|---|
| `pyproject.toml` | Python package 定義、`spec-grag = spec_grag.cli:main`、`spec-grag-slash = spec_grag.slash:main` |
| `spec_grag/config.py` | `.spec-grag/config.toml` の strict schema validation と production policy。source include / storage path / provider / model / timeout / retry 設定を正規化し、smoke fallback 混入を通常実行前に止める |
| `spec_grag/embedding.py` | embedding provider / model / dimension metadata、stable hash fallback embedding、Ollama embedding API 接続、metadata mismatch 判定 |
| `spec_grag/chunk_index.py` | raw document chunks、chunk vector index、BM25 sparse index、QueryPlan、hybrid retrieval + RRF、source span validation |
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
| `spec_grag/core.py` | `/spec-core` E2E update。manifest / graph / vector / sidecar / raw chunk / BM25 / chunk vector index を更新 |
| `spec_grag/core_extraction.py` | Phase 2 schema LLM extraction path。config 切替、Codex / Claude provider、provenance 付与、conservative target grounding scoring、unresolved sidecar、低信頼 relation 除外、incremental carry-forward |
| `spec_grag/injection.py` | `/spec-inject` context build。Core Concept index / raw chunk hybrid retrieval / graph expansion / ChapterAnchor / cluster / Agentic search 候補を統合し、4 軸 annotation と Validator を経て InjectionContext を構築。Classification LLM mode と deterministic rule pack を含む |
| `spec_grag/realign.py` | Answer phase isolation 境界。`task_prompt + InjectionContext` だけを入力に、template fallback または Codex / Claude Answer LLM provider で 4 区分回答を生成 |
| `spec_grag/run_artifacts.py` | `[run] save_artifacts` 有効時に request / response / execution metadata を保存 |
| `spec_grag/slash.py` | `spec-grag-slash` / `python3 -m spec_grag.slash` 用 wrapper。Codex command 引数を JSON transport に変換 |
| `templates/` | 対象 project へ配布する `.spec-grag/config.toml`、`.spec-grag/README.md`、`.codex/commands/spec-*.md` |
| `scripts/` | slash wrapper、project setup、system setup、CI smoke、large source smoke、実 `テスト用ドキュメント/` smoke |
| `README.md` | system setup / project setup / command usage quickstart |
| `tests/` | protocol / CLI / fixture / manifest / adapter / extraction / graph ops / retrieval / sidecar / concept index / concept diff / core E2E / schema extraction / inject-realign / external contract E2E / Phase 6 operations / Phase 7 packaging / Phase 8 hybrid retrieval |

## 検証結果

2026-05-01 時点:

```text
uv run --isolated --with pytest --with pydantic --with llama-index-core --with markdown-it-py pytest -q
145 passed in 118.90s (0:01:58)
```

追加 smoke:

```text
scripts/ci-smoke.sh
142 passed in 119.87s (0:01:59)
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
- adapter のデフォルトは `--ask-for-approval never` / `exec --disable plugins --config analytics.enabled=false --config model_reasoning_effort="low"` / `--sandbox read-only` / `--ephemeral` / `--ignore-rules` / `--skip-git-repo-check` / `--json`

Claude:

- `claude auth status` で `authMethod: claude.ai` / サブスクログイン済みを確認
- `claude --print --effort low --no-session-persistence --disable-slash-commands --tools "" --output-format json --json-schema ...` で schema 準拠 JSON 出力を確認
- 注意: `--bare` は OAuth/keychain を読まない可能性があるため、サブスク認証利用では使わない
- Claude の schema 準拠値は `result` ではなく `structured_output` に入る

schema 違反時挙動:

- 矛盾プロンプト（例: schema enum にない `Policy` を強制）では、Codex / Claude とも schema 内の値に寄せて返す傾向を確認
- ただし満たせない schema（例: `enum: []`）では、Codex / Claude とも exit 0 で schema 外の値を返し得る
- 結論: CLI-level structured output は補助。spec-grag の契約境界は adapter 側の local JSON Schema validation とする
- 実装: `spec_grag/llm_adapters.py` で `jsonschema.Draft202012Validator` による検証を追加。違反時は `CLIAdapterError`
- Phase 6 で `max_retries` / `retry_backoff_sec` / `repair_on_schema_failure` を Codex / Claude adapter に追加。subprocess timeout は `CLIAdapterError` に変換し、schema 違反時は repair prompt で再試行できる

### Config validation

`.spec-grag/config.toml` は `spec_grag/config.py` の strict schema と production policy を通してから各 command に渡す。未知の top-level table / section key、型不一致、空文字 path、unsupported provider、timeout / retry 範囲外、production policy 違反は `config_invalid` の `ErrorResult` として command 実行前に止める。生成系 LLM は `[llm].provider = "codex_cli" | "claude_cli"` を外部契約の切替点とし、production では `[llm]` と選択 provider の `model` を必須にする。schema extraction / classification / answer / concept diff / query planner の各 stage は選択 provider の `command` / `model` / `effort` を継承する。`[extraction.codex]` / `[extraction.claude]` がある場合は、抽出だけ provider 別の軽量 model / effort に上書きできる。

現在 validate する主要項目:

- `[sources] include / exclude`
- `[core] purpose_file / concept_file / extraction_mode`
- `[graph] storage`
- `[llm] provider` と `[llm.codex_cli]` / `[llm.claude_cli] command / model / effort / timeout_sec / retry`
- `[extraction] mode / provider / command / model / timeout_sec / max_retries / retry_backoff_sec / repair_on_schema_failure / max_triplets_per_chunk / num_workers / batch_size / batch_max_chars / section_max_heading_level / grounding_score_threshold / grounding_score_margin` と `[extraction.codex]` / `[extraction.claude]`
- `[answer] provider / command / model / timeout_sec / max_retries / retry_backoff_sec / repair_on_schema_failure / sandbox / tools`
- `[classification] provider / command / model / timeout_sec / retry / fallback`
- `[concept_diff] provider / command / model / timeout_sec / retry / fallback`
- `[retrieval] chunk_size / chunk_overlap / vector_top_k / bm25_top_k / graph_expansion_hops / rank_fusion / max_source_chunks`
- `[query_planner] provider / command / model / timeout_sec / retry / fallback`
- `[embedding] provider / model / dimension / timeout_sec / retry`
- `[run] save_artifacts / artifact_dir / include_request`

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

### Phase 8 raw chunk hybrid retrieval

`/spec-core` は従来の graph / vector / sidecar に加え、`.spec-grag/graph/document_chunks.json`、`chunk_vector_index.json`、`bm25_index.json` を生成する。chunk は raw markdown 本文を保持し、`source_span` / `source_hash` / `chunk_hash` を持つ。heading-only chunk は evidence から除外する。

`/spec-inject` / `/spec-realign` は BM25 sparse search、raw chunk dense vector search、explicit target hint を RRF で fuse し、hit chunk を `source_spec_constraints` / `related_source_sections` の evidence に入れる。各 item は `excerpt` / `source_span` / `source_hash` / `retrieval_methods` / `ranking_score` を持つ。

BM25 analyzer は char 2/3-gram + identifier/code/path token。`query_tokens()` / `token in haystack` は source / graph retrieval 主経路から外した。remaining use は smoke / debug fallback と deterministic validator に残る。production classification は LLM structured output を主経路とし、fallback 無効時は固定語彙判定を先に混ぜない。

ChapterAnchor と cluster snapshot は retrieval 候補として InjectionContext に統合済み。cluster は外部契約に専用 top-level field を増やさず、`related_entities` の `entity_type=CLUSTER` として保持する。

### 4 軸 annotation と Validator

4 軸分類は `production` では `[llm].provider` から解決された `[classification] provider = "codex" | "claude"` と `fallback_on_error = false` が必須。各 item は `constraint_relevance` / `target_relevance` / `semantic_conflict_candidate` / `review_required` / `classification_source` を持つ。壊れた LLM output は採用せず、production では `ClassificationError` で fail-fast し、smoke / fallback 明示時だけ rule-based fallback に戻して `review_required=true` とする。

Conflict validator は deterministic rule pack を実装済み。`REFINES` cycle、required/optional、必ず/任意、全て/一部、MUST vs MUST NOT、禁止 vs 必須、上限値 / 下限値、権限条件、状態遷移、Concept vs Source spec の候補を扱う。一方、semantic conflict candidate だけでは `conflict=true` に昇格せず review note に落とす。

### AgenticSearchCandidate source_span validation

Phase 6 着手として `AgenticSearchCandidate.source_span` の strict validation を追加した。明示 span は 1-based line range として parse し、実ファイル範囲、section 範囲、span 本文内の excerpt containment を検証する。明示 span が valid なら、同じ excerpt が別箇所にあっても invalid にしない。

`source_span` がない場合は excerpt から section 内の位置を逆引きし、0 件なら `excerpt_not_found_in_source_section`、複数件なら `ambiguous_excerpt_in_source_section` として候補を reject し `ReviewNotes` に落とす。

### Embedding provider 方針

日本語仕様文書の retrieval 品質を優先し、実 embedding provider の標準は Ollama `bge-m3`（dim=1024）とする。dim=768 互換が必要な既存 index / storage では `nomic-embed-text-v2-moe` を代替候補にし、`nomic-embed-text` / `nomic-embed-text:v1.5` は legacy / English-oriented として日本語仕様書 RAG の標準にしない。

Phase 6 で embedding provider / model / dimension を config 化し、graph / vector / concept index metadata に保存済み。metadata と config が不一致の場合は混在させず、incremental run を `failed` にして `--all` rebuild を要求する。Concept index は concept_file hash が同じでも embedding metadata が変われば再生成する。

embedding 未指定時の互換 fallback は stable hash（dim=8）である。`[embedding] provider = "ollama"` 指定時は Ollama `bge-m3` などの provider / model / dimension を受け取り、dimension mismatch は provider error として扱う。

Phase 9 以降、通常実行経路では `[embedding] provider = "ollama"` などの実 embedding provider が必須。`stable_hash` は `SPEC_GRAG_SMOKE=1` または `scripts/setup_project.py --smoke` の明示 smoke 経路だけで許可する。provider unavailable / dimension mismatch は `/spec-core` の `failed` として `embedding_provider_failed:*` に記録する。

この checkout の `.spec-grag/config.toml` は、`[llm] provider = "codex_cli"` と Ollama `bge-m3` / `dimension = 1024` を使う。判断系 Codex model は Codex CLI catalog の slug `gpt-5.4`、Claude model は full Claude Code model name `claude-sonnet-4-6`、両 provider の既定 effort は `low` を設定している。抽出は provider 別に `[extraction.codex].model = "gpt-5.4-mini"`、`[extraction.claude].model = "claude-haiku-4-5"` を使い、`batch_size = 6` / `batch_max_chars = 4000` で複数 section を 1 prompt にまとめる。`section_max_heading_level = 4` により `####` までは section 化し、`#####` 以下は親 section 本文に統合する。Claude に切り替える場合は `[llm].provider` を `claude_cli` にする。旧 smoke 設定は `.spec-grag/config.smoke.toml` に退避しており、通常実行経路では使わない。既存 `.spec-grag/graph/` 生成物は過去 smoke の `stable_hash` metadata のため、production self project 評価では token 見積もり後に `spec-core --all` rebuild が必要である。小型一時 project の production probe では `spec-core --all` 56,425 tokens、no-change incremental 12,330 tokens、`spec-inject` 116,520 tokens、`spec-realign` 137,724 tokens を確認済み。repo-local `テスト用ドキュメント/**/*.md` 全体の full run はまだ未実施。

### Answer phase isolation

Answer 生成 phase では追加 Agentic search / raw source read / tool 利用を許可しない。情報不足は `NeedMoreContextResult` / `blocked` として context build loop に戻す。CLI の read-only sandbox は補助であり、phase contract の代替ではない。

Phase 5 では `AnswerSections` schema と固定 prompt を追加し、Answer provider を `codex` / `claude` / `template` から選べる境界にした。Phase 9 以降の production config では `[answer]` に stage 個別 provider を書かず、`[llm].provider` から `codex` / `claude` へ解決する。実 LLM 呼び出し時も `generate_realign_answer(task_prompt, injection_context, llm=...)` は project_root / path / raw source handle を受け取らない。

Answer LLM が `needs_more_context=true` を返した場合、`/spec-realign` は `RealignResult` を生成せず `NeedMoreContextResult` / `blocked` に戻す。LLM が ConflictNotes / ReviewNotes を省略しても、renderer 側で必ず回答の「競合 / 不確実性 / 人間レビュー」区分に差し戻す。

`[answer] failure_fallback = "template"` 指定時は、Answer LLM の invalid JSON / schema violation / adapter failure を template answer に degrade recovery する。未指定時は従来どおり `answer_generation_failed`。

### Claude structured_output

Claude の `--json-schema` 成功時は、schema 準拠値が top-level `structured_output` に入り、`result` には説明文が入ることがある。`extract_cli_text()` は `structured_output` を優先して JSON 文字列へ変換する。

### Concept diff blocked

Concept diff 未承認時は現状どおり一回止める。production では `[llm].provider` から解決された LLM structured proposal を使うが、LLM は Concept を直接更新せず、evidence span 付き proposal を返すだけである。CLI が proposal を検証し、既存の pending Concept diff hunk / accept / reject / revise / apply に接続する。`--ignore-pending` のような回避オプションは今は入れない。

### Run artifact / recovery / smoke

`[run] save_artifacts = true` 指定時、request / response / execution metadata を `.spec-grag/runs/*.json` に保存する。artifact には `runtime_mode`、provider summary、`fallback_events`、`degraded_components`、`retrieval_summary` を含める。壊れた sidecar JSON または version mismatch は `.corrupt-<hash>` に隔離し、空 sidecar から再構築できる。

運用スクリプト:

- `scripts/spec-grag-slash.py`: slash command wrapper
- `scripts/setup_project.py`: 通常は production 向け config を生成し、`--smoke` 指定時だけ no-deps の CI / fresh install 確認用 config を生成する
- `spec-grag-setup-project`: wheel / pip install 後に package resource の template から project setup を行う console script
- `scripts/ci-smoke.sh`: CI 用 smoke
- `scripts/performance_smoke.py`: large source set smoke
- `scripts/real_docs_smoke.py`: 実 `テスト用ドキュメント/` smoke

### Markdown parser

manifest parser は `markdown-it-py` の CommonMark preset に切り替え済み。ATX / Setext heading、fenced code、HTML block は parser の構文解釈に従う。blockquote / list item 内の heading は source spec の section 境界として扱わない。

`source_manifest.json` には `parser_name` / `parser_version` を記録する。前回 manifest と parser metadata が異なる場合は、同一 `section_id` でも changed section として扱い、stale artifact を再生成対象にする。

## 次の作業

Phase 9 の production policy gate、repo-local production config 切替、wheel install 後の template resource 導線、run artifact の fallback 可視化は実装済み。次は Phase 9 残件として、full self project 実行の前に小さい source subset の一時 project で token 消費を見積もり、その後に production provider での self project 評価を行う。並行して community detection / LLM community report / report evidence、semantic conflict candidate の日本語 fixture 拡充を進める。`local` profile は作らず、開発者PCで動かす場合も production 実行経路として扱い、実行場所は provider 設定で表現する。smoke は CI / fresh install 確認用の明示モードに限定する。

## 作業時の注意

- `doc/EXTERNAL_DESIGN.ja.md` は外部契約。ユーザーの明示指示なしに縮小・変更しない
- `doc/DESIGN.ja.md` は内部設計。議論ログや作業メモを混ぜない
- 各 Phase の完了時には、Phase 1 と同様に `doc/PHASE<N>_REPORT.ja.md` を作成または最終化し、実装結果・検証結果・気づき・問題点・簡易実装・残リスク・次 Phase への申し送りを記録する
- このリポジトリは未コミット変更が多い。自分が触っていない変更を revert しない
- 実 `テスト用ドキュメント/` smoke は一時ディレクトリへ copy して実行するため、元ファイルは変更しない
- `doc/CLAUDE_NOTES.md` には古いセッション引き継ぎも含まれる。最新の現在地は本ファイルと `doc/TODO.md` を優先する
