# SPEC-grag 詳細設計書（2026-04-29）

> **位置付け**: 本書は [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md)（不変、source of truth）の全要件を **維持した上で**、それを **Native LlamaIndex GraphRAG Flow + 軽量 graph schema + Orchestrator 実装** で実現する内部設計を記述する。
>
> **大原則**:
>
> - EXTERNAL_DESIGN.ja.md の要件（Purpose / Concept / Source specs / ChapterAnchor / Entity Relationship Graph / Hierarchical Cluster / ConstraintContext / TargetContext / ConflictNotes / ReviewNotes / 4 軸評価 / Conflict 二段階 / Concept 承認制 / Answer 生成 4 区分）は **すべて実現する**
> - 軽量化されるのは **graph schema レベル**（4 entity / 6 relation）と **実装手段**のみ
> - graph 上に持たない概念は **Orchestrator 側で実装**して外部契約を満たす
>
本書は SPEC-grag の **現時点での実装方針** を記録する。外部契約は [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md)（source of truth、不変）で定義され、本書はその実装側の方針を扱う。

---

## 1. アーキテクチャ

### 1.1 責務マトリクス

SPEC-grag は判断契約を **GRAG / GraphRAG ライブラリに委譲しない**。GRAG は構造化された候補生成・検索基盤であり、最終判断は CLI / Orchestrator / LLM（用途別）/ Human が分担する。

| 領域 | 持ち主 | やること |
|---|---|---|
| Purpose 確定 | **Human** | 書く・確定する。LLM は更新しない |
| Concept 承認 | **Human** | accept / reject / 修正指示。LLM は自動承認しない |
| Concept 更新候補生成 | LLM (Extraction) + GRAG | 章本文の ANCHOR と現 Concept から更新候補を unified diff として提示。最終確定はしない |
| Concept diff pending 管理 | **CLI** | diff_id / hunk_id / base_concept_hash を `.spec-grag/pending/` に保存し、accept / reject / revise / apply を状態遷移として扱う（§3.4）|
| 変更検出 | **CLI** | section 単位 SHA-256 差分（決定的、LLM 不要）|
| Document / Section 構造 | **CLI / Parser** | Markdown AST から決定的に取得 |
| ChapterAnchor の文書構造部分 | **CLI / Parser** | document_id / section_id / heading_path / source_hash |
| ChapterAnchor の意味要素部分 | LLM (Extraction) + **Orchestrator** | ANCHOR / 章間 relation に加えて summary / key_entities / key_concepts を ChapterAnchor artifact として生成する（§2.5）|
| Entity / Relation 抽出 | LLM (Extraction) | 軽量 schema（4 entity / 6 relation）で抽出し、全 LLM 抽出 artifact に provenance を付与する（§2.6）|
| LLM 抽出 artifact の stale 除去 | **CLI / Orchestrator** | `source_section_id` / `source_chunk_id` / `extract_run_id` に基づいて section 由来 artifact を削除し、deterministic 構造とは分離する（§2.6）|
| Section grounding / normalization | **Orchestrator** | LLM が出した自由文字列の CHAPTER / SECTION 名を deterministic section_id に正規化（§2.4）|
| Slash command JSON protocol | **Agent + CLI** | Agent が ConversationContext を JSON/stdin で渡し、CLI が CoreResult / InjectionContext / RealignResult / blocked result を JSON で返す（§1.3.1）|
| Graph store / 検索 / 探索 | **GRAG subsystem** | LlamaIndex Property Graph 標準フロー。判断はしない |
| 軽量 Graph Schema | **spec-grag Core** | 4 entity / 6 relation（§2.1）|
| EXTERNAL_DESIGN.ja.md 概念の実現 | **Orchestrator** | Concept / ChapterAnchor / Hierarchical Cluster / ConstraintContext / TargetContext / ConflictNotes / ReviewNotes を Orchestrator 側 wrapper で実現（§3 参照）|
| 4 軸評価の付与 | LLM (Classification) + **Orchestrator** | §1.6 の 4 軸を retrieval 候補に付与（graph 不汚染、transient annotation）|
| 未承認 Concept 遮断 | **Orchestrator** | 絶対に通さない（InjectionContext / Answer 生成を停止）|
| Conflict 候補 → 確定の昇格 | Validator + **Human** | LLM 単独では `conflict=true` 不可（§1.5 二段階）|
| Hierarchical Cluster | **Orchestrator** | /spec-core 時に cluster snapshot を sidecar 生成・更新、retrieval 時に補完（§3.5）|
| InjectionContext 構築 | **Orchestrator** | ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes / ReviewNotes に構造化（§3.1）|
| Answer 生成 | LLM (Answer) | InjectionContext / RealignResult に拘束された 4 区分回答（§3.6）|

LLM は **用途別に分離**して扱う:

- **Extraction LLM**: SchemaLLMPathExtractor の LLM backend、Concept 更新候補生成
- **Classification LLM**: 4 軸付与（review_required / semantic_conflict_candidate）、Validator の deterministic 検査を経る
- **Answer LLM**: InjectionContext を前提に回答生成、ConstraintContext を守る、ConflictNotes / ReviewNotes を隠さない

### 1.2 GRAG / GraphRAG ライブラリがしてはいけないこと

- Purpose を更新する
- Concept diff を自動承認する
- 課題に対して何を最終制約にするかを確定する
- 何を修正対象にするかを最終確定する
- 未承認 Concept を勝手に検索対象に混ぜる
- Answer を生成する
- `conflict=true` を単独で確定する

GRAG / GraphRAG ライブラリ（LlamaIndex / Neo4j 等）は **GRAG subsystem の内部実装**に過ぎず、SPEC-grag の判断契約を代替しない。

### 1.3 三層分業（実装パッケージ）

```text
┌────────────────────────────────────────────────────────┐
│  Agent (Claude / Codex CLI) — slash command 実行層     │
│  - ConversationContext + 課題プロンプト解釈            │
│  - Agentic search で章本文を読む                        │
│  - 章アンカー欠損章を動的補完                           │
│  - Concept 更新候補の unified diff 生成                 │
│  - InjectionContext / RealignResult を読み Answer 生成 │
│  - raw source spec の Read は §1.7 で制限される        │
└──────────────────┬─────────────────────────────────────┘
                   │ Bash 呼び出し
                   ↓
┌────────────────────────────────────────────────────────┐
│  spec-grag CLI / Orchestrator（Python）                 │
│  - .spec-grag/config.toml 読み込み                      │
│  - 変更検出（section 単位 SHA-256）                      │
│  - GRAG Builder / Retriever / Validator 呼び出し制御   │
│  - 未承認 Concept 遮断                                  │
│  - 2 系統 pipeline（制約探索 / 修正対象探索）            │
│    retrieval source は 3 系統:                            │
│    Core Concept / Graph constraint / Graph target        │
│  - 4 軸評価のオーケストレーション                       │
│  - Conflict 二段階の Validator + 昇格制御               │
│  - Hierarchical Cluster の sidecar 生成・更新 + 補完    │
│  - InjectionContext / RealignResult 構造化出力          │
│  - safe_delete_by_section wrapper（R1）                 │
│  - Section grounding / normalization                    │
└──────────────────┬─────────────────────────────────────┘
                   │ Python API（LlamaIndex 標準フロー）
                   ↓
┌────────────────────────────────────────────────────────┐
│  GRAG（LlamaIndex Property Graph、軽量 schema）          │
│  - PropertyGraphIndex.from_documents / from_existing    │
│  - SchemaLLMPathExtractor + ImplicitPathExtractor       │
│  - 軽量 schema: DOCUMENT / CHAPTER / SECTION /          │
│                ANCHOR（§2.1）                           │
│  - SimplePropertyGraphStore（JSON 永続化）              │
│  - SimpleVectorStore + OllamaEmbedding                  │
│    default: bge-m3（dim=1024）                          │
│  - PGRetriever / VectorContextRetriever                 │
│  - LLM backend = CodexCLIAdapter（spec-grag が実装）   │
│  → 候補を返すのみ。判断はしない                         │
└────────────────────────────────────────────────────────┘
```

#### 1.3.1 Slash command wrapper と CLI の JSON 入出力契約

`/spec-inject` / `/spec-realign` が外部設計の ConversationContext を扱うため、Agent は会話区間を推測的に CLI 外へ閉じ込めず、次の `SlashCommandRequest` を JSON として spec-grag CLI の stdin に渡す。CLI / Orchestrator はこの JSON を唯一の ConversationContext 入力として扱う。

```text
SlashCommandRequest:
  command: spec-core | spec-inject | spec-realign
  project_root: string
  task_prompt?: string
  conversation_context:
    current_user_message: string
    recent_messages[]:
      role: user | assistant | system | tool
      content: string
    working_target?: string
    explicit_files?: string[]
  agentic_search_candidates[]?: AgenticSearchCandidate
  agent_capabilities:
    can_read_source: boolean
    can_answer: boolean
  options:
    all?: boolean
    output_format: json
```

呼び出し規約:

```text
Agent / slash command wrapper
  -> SlashCommandRequest を JSON で作る
  -> spec-grag CLI に stdin で渡す
  -> CLI / Orchestrator が処理する
  -> JSON result を stdout に返す
  -> Agent は返却された InjectionContext / RealignResult / blocked result だけを次の応答に使う
```

CLI の JSON transport は `ResultEnvelope` として返す。`status` は envelope に置き、`payload` の InjectionContext / RealignResult / CoreResult は EXTERNAL_DESIGN.ja.md §8 の構造を保つ（InjectionContext のトップレベルに独自フィールドを足さない）。

```text
ResultEnvelope:
  status: ok | degraded | blocked | failed
  result_type: CoreResult | InjectionContext | RealignResult | ConceptApprovalRequiredResult | ConflictApprovalRequiredResult | NeedMoreContextResult | ErrorResult
  payload: object
  execution:
    context_ready?: boolean
    pending_concept_diff_id?: string
    pending_conflict_review_id?: string
    pending_conflict_candidate_ids[]?: string
    failed_sources[]?: string
    degraded_components[]?: string
    runtime_policy?: object
    timing_summary?: object
    stage_timings[]?: object
  warnings[]: string
```

承認フローは外部 slash command を増やさず、`RequestOptions.approval` で内部 transport として渡す。`ConceptApprovalRequiredResult` / `ConflictApprovalRequiredResult` は `approval_prompt.items[].transport.approval` に、エージェントが次リクエストへ戻すための機械 payload を含める。ユーザーにはこの JSON を直接読ませず、エージェントがチャット上で要約と選択肢を提示する。

Phase 10 以降、`execution.runtime_policy` には解決済み runtime policy を保存する。`[runtime].mode` は `local_daily` / `ci` / `production`（smoke 実行時は `smoke`）を取り、`watcher_required`、`foreground_incremental`、`fail_fast_on_dirty`、`fail_fast_on_pending`、`fail_fast_on_stale` を mode 既定値と明示上書きから解決する。production mode では dirty / pending / stale を自動修復しないよう、明示上書きより fail-fast guard を優先する。

`FreshnessReport.readiness_report` には GRAG readiness gate の判定結果を保存する。InjectionContext のトップレベル構造は増やさず、CoreResult / InjectionContext / RealignResult から辿れる FreshnessReport 内に機械判定情報を置く。

Phase 11 以降、`execution.timing_summary` と `execution.stage_timings`
には performance observability 用の診断情報を保存する。`stage_timings`
は `time.perf_counter_ns()` ベースの duration と count / provider identity
だけを持ち、Source specs 本文、LLM prompt 本文、LLM 応答本文は保存しない。
run artifact では同じ情報を top-level にも複写する。

Phase 12 以降、run artifact には `trace_id`、`graph_revision`、
`artifact_revision` も保存する。`[run].include_request` の既定値は false
であり、request / response payload を保存する場合も `[run].redact_payload`
で本文系 field を redaction できる。

```text
readiness_report:
  status: fresh | dirty | pending | stale
  runtime_policy: object
  current_semantic_hash?: string
  last_processed_semantic_hash?: string
  dirty_section_ids[]: string
  format_only_section_ids[]: string
  pending_concept_diff_id?: string
  pending_conflict_candidate_ids[]: string
  stale_reason_codes[]: string
  artifact_diagnostics:
    active_revision?: object
    staging_revisions[]: object
    failed_revisions[]: object
  reasons[]:
    code: string
    message: string
    details: object
```

watcher は `.spec-grag/state/` 配下に状態を保存する。`watch_state.json` は readiness と watcher run state の監査用であり、`watch_lock.json` は二重 watcher 起動を防ぐ一時 lock である。lock は heartbeat を持ち、stale_after_sec を超えたものは stale lock として置き換え可能にする。

Phase 10 の watcher は single worker の常駐 polling watcher である。Source specs の semantic manifest を debounce し、開始時点の snapshot manifest と document text を core update に渡す。watcher 実行中に追加変更が入った場合、現在の incremental には混ぜず、`watch_queue.json` に `running_change` または `post_run_change` として保存する。run 完了後に queue と最新 manifest を再確認し、残変更があれば次サイクルの background incremental を起動する。

watcher の挙動は `.spec-grag/config.toml` の `[watcher]` で設定できる。`enabled=false` の場合、`spec-grag-watch` は core 更新を行わず終了する。`interval_ms` は常駐 polling 間隔、`debounce_ms` は変更検知後に snapshot が安定するまで待つ時間、`stale_lock_ms` は heartbeat lock を stale とみなすまでの時間である。`state_file` と `queue_file` は relative path の場合 project root から解決する。

foreground context generation は watcher state を readiness gate で確認する。local daily では `run_state=running` または queue 非空の間、`/spec-inject` / `/spec-realign` は InjectionContext / Answer を生成せず blocked になる。production では同じ状態を fail-fast として扱う。CI / watcherなし mode では foreground incremental が許可され、watcher state に依存しない。

Phase 12 以降、低レベル API の `build_injection()` は read-only default とする。CLI は必要な `core_update` / `freshness_report` を readiness gate で解決してから渡し、`build_injection()` 自身は `allow_core_update=True` が明示された test / helper 経路を除いて `run_core_update()` を起動しない。query-time の build side effect は production path では禁止し、foreground incremental / watcher / `spec-core` に閉じ込める。

```text
watch_state（.spec-grag/state/watch_state.json）:
  version: string
  readiness_status: fresh | dirty | pending | stale
  run_state: idle | running | failed
  last_run_id?: string
  last_started_at?: ISO8601 timestamp
  last_completed_at?: ISO8601 timestamp
  last_error?: string
  last_processed_semantic_hash?: string
  running_semantic_hash?: string
  queued_change_count: number
  heartbeat_at?: ISO8601 timestamp
  updated_at?: ISO8601 timestamp
  readiness_report?: object

watch_queue（.spec-grag/state/watch_queue.json）:
  version: string
  updated_at?: ISO8601 timestamp
  pending_concept_diff_id?: string
  changes[]:
    source_section_id: string
    semantic_hash: string
    reason: pending_concept_diff_unresolved | running_change | post_run_change | string
    detected_at: ISO8601 timestamp

watch_lock（.spec-grag/state/watch_lock.json）:
  version: string
  pid: number
  heartbeat_at: ISO8601 timestamp
  stale_after_sec: number
```

Agentic search が必要な場合も、Agent は raw source spec を直接 Answer の根拠に使わない。Orchestrator が追加検索を必要とする場合は `NeedMoreContextResult` を返し、Agent はその `search_requests[]` に対応する候補だけを `agentic_search_candidates[]` として次の `SlashCommandRequest` に含める。Orchestrator が ConstraintContext / TargetContext / ReviewNotes に分類した後だけ InjectionContext に入る。

```text
NeedMoreContextResult:
  task_prompt: string
  search_requests[]:
    request_id: string
    reason: string
    target:
      document_id?: string
      chapter_id?: string
      section_id?: string
      query?: string
    expected_use: constraint | target | review
  current_partial_context_summary: string

AgenticSearchCandidate:
  request_id: string
  source_document_id: string
  source_section_id?: string
  heading_path?: string
  excerpt: string
  source_span?: string
  reason: string
  source_hash?: string
```

`SlashCommandRequest` に `agentic_search_candidates[]` が含まれる場合、CLI は `request_id` が未発行の候補、`source_hash` が現行 section hash と一致しない候補、`excerpt` の出典を解決できない候補を採用しない。

`AgenticSearchCandidate.source_span` は 1-based line range として扱う。標準形式は `start-end` または `line` だが、`L12-L18`、`lines 12-18`、`[12:1-40]` のような表記も同じ line range に正規化する。明示 `source_span` がある場合は、実ファイル範囲内、該当 `source_section_id` の section 範囲内、かつ span 本文に `excerpt` が含まれることを検証する。明示 span が valid であれば、同一 excerpt が他箇所に存在しても invalid にはしない。

`source_span` がない場合は、`excerpt` から section 内の位置を逆引きする。該当箇所が 0 件なら `excerpt_not_found_in_source_section`、複数件なら `ambiguous_excerpt_in_source_section` として候補を採用せず `ReviewNotes` に落とす。

### 1.4 採用方針（pivot 後 + Phase 0 結果）

**確定方針（pivot 後 commit b45d95f / 2026-04-27）**:

- 言語: **Python**
- GRAG エンジン: **LlamaIndex** Property Graph（標準フローに乗る、Native LlamaIndex GraphRAG Flow）
- graph store: ローカル・ファイルベース `.spec-grag/graph/`
- **生成系 LLM**（用途別: Extraction / Classification / Answer）: **Claude CLI / Codex CLI**
  - サブスク認証前提（API key 前提にしない）
  - subprocess 呼び出しで JSON 入出力契約（structured output: `--json-schema` / `--output-schema`）
  - 統合方式: **Native LlamaIndex GraphRAG Flow**
    - `CodexCLIAdapter(CustomLLM)` を LlamaIndex の LLM backend として実装（必須実装は `complete` / `stream_complete` の 2 method + `metadata` property のみ、SURVEY 13 §1.2 で Phase 0 評価「10+ method」を訂正）
    - `SchemaLLMPathExtractor` に渡す
    - `PropertyGraphIndex` / `SimplePropertyGraphStore` / Retriever は LlamaIndex 標準フローに乗る
    - 旧調査資料上の「案 B」に相当する（[doc/SURVEY/SUMMARY.md §3.9](SURVEY/SUMMARY.md) / [13_path_b_design_options.md](SURVEY/13_path_b_design_options.md)）
- **ベクトル化 model（embedding）**: **Ollama bge-m3**（ローカル、日本語 / 多言語仕様文書向け標準、dim=1024）
  - dim=768 互換が必要な既存 index / storage では、代替候補として `nomic-embed-text-v2-moe` を使う
  - `nomic-embed-text` / `nomic-embed-text:v1.5` は legacy / English-oriented と扱い、日本語仕様書 RAG の標準にはしない
  - embedding provider / model / dimension は graph / vector / concept index の metadata に保存し、不一致時は index rebuild を要求する
  - dimension や embedding 空間の異なる index は混在させない

**Phase 0 で確定した運用ルール R1〜R5**:

| ルール | 内容 |
|---|---|
| R1 | `safe_delete_by_section` wrapper を spec-grag 側で実装する（LlamaIndex 標準 `delete()` は cascade で対岸 entity を消すため使えない、spike 01 で実証）|
| R2 | **`kg_extractors` は空配列 `[]` にしない**（falsy で default の `[SimpleLLMPathExtractor, ImplicitPathExtractor]` が呼ばれて `Settings.llm` 解決が走る）。Native LlamaIndex GraphRAG Flow では必ず `kg_extractors=[ImplicitPathExtractor(), schema_llm_path_extractor]` のように **ImplicitPathExtractor + SchemaLLMPathExtractor を明示**する。LLM 抽出を無効化する特殊ケースのみ `[ImplicitPathExtractor()]` 単独を許可する |
| R3 | `load_index_from_storage` を使わず、graph_store を `from_persist_dir` で reload + 毎セッション `from_existing` で再構築 |
| R4 | PGRetriever の rank fusion / 4 軸付与 / vector_store 連結はすべて spec-grag Orchestrator 側責務 |
| R5 | Claude / Codex CLI subprocess は `--bare` 不使用（OAuth/keychain を読まないため）。代わりに `--no-session-persistence` + `--disable-slash-commands` + `--allowedTools ""` 等の組合せ |

### 1.5 整合性チェック方針（3 段階パイプライン + Conflict 二段階）

LLM 抽出を完全信用しない。EXTERNAL_DESIGN.ja.md §5.4 の ConflictNotes（制約 vs 修正対象 / Source spec 同士 / Concept vs Source spec）の検出は 3 段階で行う:

1. **グラフ構造ベース**（決定論的、優先）
   - graph 上の章間 `REFINES` チェーンに循環がある
   - 同一 ID への異なる属性が並存する
   - 同一 ANCHOR が複数 section に MENTIONS されている場合は conflict ではなく **review_required 候補**として扱う（同一概念の複数言及は正常、矛盾の判定は段階 3 の LLM 推論に委ねる）
2. **ルールベース**（決定論的、補助）
   - Purpose の制約条項と Source spec の対立量化詞（「必ず」⇔「任意」、「全て」⇔「一部」）
   - FreshnessReport.source_manifest の scanned_at より新しい修正と古い section の食い違い（§4.7 で定義）
   - Required と Optional の同時指定
   - MUST と MUST NOT、禁止と必須、上限値 / 下限値、状態遷移不能、権限条件の食い違い、Concept と Source spec の明示的な逆転
3. **LLM 推論**（補助、最後）
   - 上記 1, 2 で疑わしい候補のみ LLM (Classification) で意味的妥当性確認
   - LLM 単独では `conflict=true` を発火させない、必ず構造的根拠とセット

**Conflict の確定権限（二段階）**:

| 状態 | LLM 単独で出してよいか | 説明 |
|---|---|---|
| `review_required = true` | 可 | 怪しい・確認が必要 |
| `semantic_conflict_candidate = true` | 可 | 意味的に衝突の疑い |
| `conflict = true` | 不可 | 構造的根拠（段階 1 or 2）または Human approval を必須とする |

LLM (Classification) は **候補**を出してよいが、**確定**は Validator または Human approval を経る。実装は Orchestrator 側（§3.3）。

Conflict は source 全体に対する恒久候補と、task 依存の一時候補に分ける。Source specs 全体の矛盾候補は `/spec-core` 相当で `pending_conflict_review` として保持し、人間が candidate 単位に accept / reject / defer / revise する。task 依存の衝突は InjectionContext 上の transient annotation として扱い、承認済み Conflict だけを `ConflictNotes`、未承認候補を `ReviewNotes` に反映する。Answer phase では Conflict の承認・追加検索・raw source read を行わない。

### 1.6 4 軸評価（transient annotation、graph 不汚染）

EXTERNAL_DESIGN.ja.md §5.4 で「同じ Concept / Source spec が制約側と修正対象側の両方に現れる場合もある」と定義されているとおり、課題に対する評価は**排他的 5 分類ではなく、4 軸の独立評価**として実装する。

**4 軸は課題依存の transient annotation**。同一概念が課題ごとに違う評価を持つため、graph store の **恒久プロパティとしては保持しない**（spike 03 で実証）。retrieval result / InjectionContext / RealignResult 上にのみ保持する。

| 種別 | 例 | 保持先 |
|---|---|---|
| 恒久プロパティ | document_id / section_id / heading_path / source_hash / created_at / updated_at（任意）/ source_span（任意）/ evidence_excerpt（任意） | graph store（LlamaIndex SimplePropertyGraphStore の properties）|
| transient annotation | constraint_relevance / target_relevance / semantic_conflict_candidate / review_required / ranking_score / source_origin | retrieval result の NodeWithScore.metadata / InjectionContext / RealignResult |

**4 軸評価（transient）**:

```text
constraint_relevance: none | low | medium | high
target_relevance:     none | low | medium | high
conflict:             true | false  <- LLM 単独では false まで（候補は §1.5 参照）
review_required:      true | false
```

**派生状態**:

```text
irrelevant = (constraint_relevance == none)
          && (target_relevance == none)
          && (conflict == false)
          && (review_required == false)
```

**InjectionContext のフィールド対応**（EXTERNAL_DESIGN §5.4 の構造、Orchestrator が振り分ける）:

| 4 軸の状態 | InjectionContext の所属フィールド |
|---|---|
| `constraint_relevance != none` | `constraint_context.{purpose,concept,source_spec,chapter_anchor}_constraints` |
| `target_relevance != none` | `target_context.{candidate_targets,related_concepts,related_source_sections,related_chapter_anchors,related_entities}` |
| `conflict == true` | `conflict_notes` |
| `review_required == true` | `review_notes` |
| すべて none/false（派生 irrelevant） | `excluded_as_irrelevant` |

同一項目が複数フィールドに同時所属しうる。実装は Orchestrator 側（§3.1 / §3.2）。

各 item の metadata に `source_origin`（GRAG / Agentic search / 両方）を持たせ、由来を追跡する。InjectionContext のトップレベルに独自フィールドは追加しない（EXTERNAL_DESIGN.ja.md §8.1 の構造を厳守）。

### 1.7 Agent の Read tool 使用制限

Agent (Claude / Codex CLI) は spec-grag CLI の外側で動く実行制御層であり、raw source spec の直接読み取りは **用途を限定**する。Orchestrator の **未承認 Concept 遮断**を Agent が迂回しないための制約。

**許可される Agent の Read**:

- Agentic search（GRAG 候補補正、章アンカー欠損章の動的補完、§2.5）
- evidence inspection（debug / 人間レビュー用）
- 章ファイルの軽量サンプリング（章数の確認等）

**禁止される Agent の Read**:

- Answer 生成時に raw source spec を **直接 Answer の根拠として組み込む**
- InjectionContext を経由せず source spec の内容を Answer に引用する
- 未承認 Concept を含む章ファイルを Answer の根拠として使う
- ConstraintContext / TargetContext / ConflictNotes / ReviewNotes に **存在しない情報**を Answer 制約として持ち込む

Answer 生成時の制約・修正対象・競合候補は **InjectionContext / RealignResult 経由のみ**使用する。raw source の Read は InjectionContext 構築 loop または evidence inspection の補助に限定し、Answer 生成 phase では tool / raw source read / 追加 Agentic search を禁止する。

### 1.8 LlamaIndex 部品契約（candidate_only）

LlamaIndex 部品はすべて **candidate_only** として扱う。承認状態、制約確定、Concept 更新、Conflict 確定の権限は持たせない。

| 部品 | role | authority | 許可される用途 | 禁止される用途 |
|---|---|---|---|---|
| `PropertyGraphIndex` | graph_index_builder_and_query_surface | candidate_store_only | graph_build / retrieval / relation_candidate_storage | concept_approval / conflict_resolution / answer_generation / 制約確定 |
| `SchemaLLMPathExtractor` | schema_constrained_path_candidate_extraction | candidate_only | entity_candidate_extraction / relation_candidate_extraction | concept 承認 / 最終 relation 決定 / Purpose 更新 / Conflict 確定 |
| `SimplePropertyGraphStore` | local_graph_persistence_candidate | storage_only | local_persist / local_reload | source_of_truth_for_approval / Concept レジストリ代替 |
| `Retriever` | evidence_backed_candidate_retrieval | retrieval_only | candidate_search / evidence_collection | final_classification / Orchestrator なしの answer_generation |
| `CodexCLIAdapter` (spec-grag 実装) | llm_backend_for_extraction | structured_output_only | SchemaLLMPathExtractor の LLM、subprocess経由 JSON | 判断 / 承認 / 制約確定 |

### 1.9 内部処理フロー（3 コマンド × 4 経路）

EXTERNAL_DESIGN.ja.md §4 / §5 / §6 の 3 コマンドを、§1.1 の責務境界と §1.5〜§1.8 の制約に従って実行する。`/spec-core` は incremental / --all の 2 経路、計 4 経路すべてが一気通貫で動作する。

```text
経路 1: /spec-core incremental（変更分のみ）
  1. CLI: .spec-grag/config.toml 読み込み
  2. CLI / Parser: Markdown AST から current_section_manifest を生成し、
     前回の source_manifest と比較する（§2.6）
     - changed_section_ids: section_id は同じだが source_hash が変わった section
     - added_section_ids: 新規 section
     - removed_section_ids: 削除 / rename / split / merge で消えた section
     - structure_changed_chapter_ids: chapter heading / 階層が変わった chapter
  3. CLI: deterministic structure reconciliation を実行
     - removed_section_ids の SECTION node / CONTAINS relation を削除
     - removed_section_ids の source_section_id 由来 LLM artifact / vector /
       unresolved_relation を削除
     - removed_section_ids を含む affected chapter の ChapterAnchor artifact を dirty にする
     - renamed section は removed + added として扱う
     - split / merge は removed + added の集合として扱う
     - chapter heading / 階層変更は chapter_id レベルで再構築対象にする
  4. CLI: 変更 section（changed + added）と affected chapter を特定
  5. spec-grag が safe_delete_by_section(graph_store, section_id) で
     変更 section 由来の旧 LLM extraction artifact を provenance ベースで除去（R1、§2.6）
     - source_section_id == section_id の ANCHOR / LLM 抽出 relation を削除
     - source_section_id == section_id の vector embedding を削除
     - source_section_id == section_id を含む affected chapter の ChapterAnchor artifact を dirty にする
       （章単位 artifact のため、この段階では物理削除しない）
     - deterministic DOCUMENT / CHAPTER / SECTION / CONTAINS はここでは削除しない
  6. CLI / Parser: 変更 section の Markdown heading から
     DOCUMENT / CHAPTER / SECTION 構造（CONTAINS）を deterministic に生成
     - heading_path / source_hash 等の恒久プロパティを付与
  7. ChapterAnchor 生成（共同責務、変更 section のみ）
     - SchemaLLMPathExtractor が変更 section から ANCHOR / 章間 relation を抽出
     - LLM backend = CodexCLIAdapter（Native LlamaIndex GraphRAG Flow）
     - schema = §2.1 軽量 schema（4 entity / 6 relation）
     - Orchestrator が Section grounding / normalization で正規化（§2.4）
     - 全 LLM 抽出 artifact に source_document_id / source_chapter_id /
       source_section_id / source_chunk_id / source_hash / extract_run_id を付与
  8. graph_store.upsert_nodes / upsert_relations で投入
     vector_store: 変更 section の stale embedding を provenance ベースで削除し、
     新規 ANCHOR / section text の embedding を upsert
  9. Orchestrator: affected chapter の ChapterAnchor artifact を章単位で再集約（§2.5）
     - affected_chapter_id を dirty にする
     - affected chapter 配下の最新 ANCHOR / relation / evidence を集約
     - source_section_ids[] / source_hashes[] を更新
     - 再生成成功時に chapter_anchor artifact を atomically replace し、
       stale=false に戻す
 10. Orchestrator: Hierarchical Cluster の cluster snapshot を更新（§3.5）
     - 変更 section に関連する章間 relation を traversal
     - 変更 / 削除 section の source_section_id を持つ cluster を dirty にする
     - 影響を受けた cluster を再算出し sidecar に書き出す
 11. Orchestrator: source-level Conflict 候補を検出（§3.3）
     - source_span / source_hash / evidence_excerpt を持つ候補だけ pending_conflict_review に入れる
     - accepted 済み候補は approved_conflicts sidecar に保持し、rejected fingerprint は再通知抑制に使う
 12. Concept 更新候補生成（§3.4）
     - GRAG の ANCHOR + relation から「Core 書き換え候補」を検出
     - LLM (Extraction) が Agentic search で章本文確認 + unified diff 生成
 13. CLI: Concept diff がある場合は pending_concept_diff を作成し、
     CoreResult.concept_diff / ResultEnvelope.execution.pending_concept_diff_id として出力
     Conflict 候補がある場合は pending_conflict_review を作成し、
     CoreResult.conflict_review / ResultEnvelope.execution.pending_conflict_review_id として出力
 14. CLI: CoreResult を返して正常終了
 15. Human: Concept は hunk 単位で accept / reject / 修正指示、Conflict は candidate 単位で accept / reject / defer / 修正指示（チャット上の確認）
 16. CLI: apply 時に base_concept_hash を検証し、
     accept された hunk のみ Concept に反映、未承認 hunk は反映しない
     approved conflict のみ approved_conflicts sidecar に反映し、未承認 candidate は確定 Conflict にしない
 17. CLI: Concept が更新された場合、Core Concept index を再生成（§3.7）

経路 2: /spec-core --all（全再構築）
  1. CLI: .spec-grag/config.toml 読み込み
  2. 既存 graph store / vector store / cluster sidecar をバックアップ後に破棄
  3. CLI / Parser: sources.include の全 section を Markdown AST で解析
     DOCUMENT / CHAPTER / SECTION 構造（CONTAINS）を deterministic に生成
     - heading_path / source_hash 等の恒久プロパティを付与
  4. SchemaLLMPathExtractor で全 section から ANCHOR / 章間 relation を抽出
     - Section grounding / normalization を適用（§2.4）
  5. graph_store.upsert_nodes / upsert_relations で投入
     vector_store: 全 ANCHOR / section text の embedding を計算し upsert
  6. PropertyGraphIndex.from_existing で graph_store + vector_store を接続、persist
  7. Orchestrator: 全 chapter の ChapterAnchor artifact を全再生成（§2.5）
     - chapter_anchors.json を atomically replace する
  8. Orchestrator: Hierarchical Cluster の cluster snapshot を全再生成（§3.5）
  9. source-level Conflict 候補検出（経路 1 の Step 11 と同じプロセス）
 10. Concept 再生成候補（経路 1 の Step 12 と同じプロセス）
 11. CLI: Concept diff がある場合は pending_concept_diff を作成し、
     CoreResult.concept_diff / ResultEnvelope.execution.pending_concept_diff_id として出力
     Conflict 候補がある場合は pending_conflict_review を作成し、
     CoreResult.conflict_review / ResultEnvelope.execution.pending_conflict_review_id として出力
 12. CLI: CoreResult を返して正常終了
 13. Human: Concept は hunk 単位で accept / reject / 修正指示、Conflict は candidate 単位で accept / reject / defer / 修正指示（チャット上の確認）
 14. CLI: apply 時に base_concept_hash を検証し、
     accept された hunk のみ Concept に反映、未承認 hunk は反映しない
     approved conflict のみ approved_conflicts sidecar に反映し、未承認 candidate は確定 Conflict にしない
 15. CLI: Concept が更新された場合、Core Concept index を再生成（§3.7）

経路 3: /spec-inject（GRAG を信じすぎず、Agentic search 併用）
  1. CLI: GRAG readiness gate を実行する
     - fresh: 既存 artifact だけを使って InjectionContext 構築へ進む
     - dirty / stale: runtime policy に従い、local_daily では watcher waiting で blocked、
       ci / smoke では foreground incremental を許可、production では failed にする
     - pending: foreground human では Concept / Conflict の確認要求、production では failed
  2. Orchestrator: Concept diff または Conflict review が未解決なら InjectionContext を生成せず、
     ConceptApprovalRequiredResult / ConflictApprovalRequiredResult を返して停止:
       task_prompt / concept_diff or conflict_review / approval_prompt / required_actions / warnings
     （EXTERNAL_DESIGN.ja.md §5.3: 未承認時は確認要求だけを出力する）
     - これはデッドロックではなく安全停止点である。ユーザーはチャット上で
       Concept を手動修正するか、承認 / 非承認 / 修正指示 / 保留相当の判断を行い、
       `options.approval` を通して内部状態遷移を行う
     - 未承認 diff を無視して現在の Concept のまま進める `--ignore-pending`
       相当の迂回オプションは設けない。進める場合は reject / revise / 手動修正で
       pending 状態を解消してから再実行する
  3. CLI: ConversationContext + Purpose + 承認済 Concept + approved_conflicts / pending_conflict_review を取得
     課題プロンプトが明示されていれば中心クエリとして使用、
     省略時は ConversationContext から中心クエリを推定（EXTERNAL_DESIGN.ja.md §3.3）
  4. Orchestrator: Purpose を必ず ConstraintContext 候補に追加（自動）
  5. 関連候補を 3 系統で取得:
     a. Core Concept retrieval（graph 外）:
        - 承認済み Concept 文書（concept_file）を読み込む
        - heading / paragraph 単位に分割し、keyword + embedding で課題関連 Concept を取得
        - 未承認 Concept diff は絶対に含めない
     b. Graph retrieval（制約探索）:
        - PGRetriever で Source specs / ANCHOR / 章間 relation から制約候補を取得
     c. Graph retrieval（修正対象探索）:
        - VectorContextRetriever + 章間 relation 探索で修正対象候補を取得
     - 各 graph 候補は (node, relation, source span, evidence, confidence, score) を持つ
     - graph の relation は「読むべき場所のヒント」、確定事実ではない
     - `retrieval.graph_expansion_hops` は seed section / chunk / explicit target からの bounded traversal 上限であり、結果には hop / path / relation_type / confidence / source_section_id / evidence_excerpt を保持する
     - 既定の traversal policy は `DEPENDS_ON` / `REFINES` / `RELATED_TO` / `CONTRASTS_WITH` かつ confidence `medium` 以上、最大 12 graph entities とする。`CONTRASTS_WITH` は矛盾候補を拾うために含める
     - `retrieval_index.json` は query-time の section / chunk / node / relation 逆引き artifact であり、Graph RAG traversal の主要な全件走査を避けるために使う
  6. GRAG: 該当章 / 関連章の chapter_anchors（ANCHOR）を取得
  7. Orchestrator: cluster snapshot から Hierarchical Cluster を読み込み、
     関連 cluster を InjectionContext に反映（§3.5）
  8. InjectionContext 構築 loop（Answer 生成前に完了させる）:
     - LLM が Agentic search を併用して GRAG 候補を章本文ベースで補正
       （関連が薄い候補は除外、見落とし候補を追加）
     - 章アンカー欠損章を Agentic search で動的補完（§2.5）
     - graph の relation type を章本文確認後に確信度付きで context に反映
     - 不足が残る場合は NeedMoreContext を出し、追加検索候補を取得
     - Orchestrator が追加候補を分類し、context_ready になるまで loop する
  9. LLM (Classification) + Orchestrator: 4 軸評価を付与（transient annotation）
     - constraint_relevance / target_relevance / conflict / review_required
     - LLM が出すのは候補（review_required, semantic_conflict_candidate）まで
     - 各 item に source_origin（GRAG / Agentic search / 両方）を付与
 10. Validator: schema / source / Concept approval / Conflict 昇格を deterministic に検査（§1.5）
     - approved_conflicts のうち task に関連するものだけ ConflictNotes に入れる
     - 未承認 Conflict candidate / semantic_conflict_candidate は ReviewNotes に落とす
     - Answer phase で Conflict 承認を行わせない
 11. Orchestrator: InjectionContext を構造化出力（EXTERNAL_DESIGN.ja.md §8.1 の構造を厳守）
     - ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes / ReviewNotes
     - chapter_anchors は constraint_context.chapter_anchor_constraints / target_context.related_chapter_anchors に振り分け
     - source_origin は各 item の metadata として保持（トップレベルフィールドにしない）
     - GRAG Freshness Report

経路 4: /spec-realign（InjectionContext 経由を厳守）
  1. 経路 3（/spec-inject 相当）で readiness gate を通し、InjectionContext を作成
  2. ResultEnvelope.status が ok / degraded で、execution.context_ready == true であることを確認
  3. LLM (Answer): task_prompt + InjectionContext のみに拘束された 4 区分回答を生成（§3.6）
     - 守る制約（ConstraintContext）
     - 修正候補（TargetContext）
     - 競合 / 不確実性 / 人間レビュー（ConflictNotes / ReviewNotes）
     - 課題への回答または修正案
     - graph の relation を「確定事実」として引用しない、章本文を根拠に明示する
     - raw source spec を直接根拠に使わない（§1.7、InjectionContext 経由のみ）
     - Answer 生成 phase では tool / raw source read / 追加 Agentic search を禁止する
     - 追加情報が必要な場合は Answer を生成せず blocked または review_required として返す
  4. Orchestrator: RealignResult を構造化出力（task_prompt + InjectionContext + answer）
```

**経路間の依存関係**:

- 経路 3 / 4 は経路 1（incremental）を内部で呼ぶ -> Concept diff 未承認時は停止
- 経路 2（--all）は単独実行のみ
- 経路 1 / 2 で生成された ANCHOR / 関連 relation / cluster snapshot が経路 3 の Retriever / Cluster 読み込みで取得できることを保証する

ChapterAnchor は **retrieval artifact** であり、判断主体ではない。`/spec-core`（経路 1 / 2 両方）で生成・更新するが、「課題に対して制約か修正対象か」は確定しない。その評価は `/spec-inject` または `/spec-realign` で課題に応じて 4 軸評価（transient annotation）を付与する。

---

## 2. スキーマ

### 2.1 軽量 Graph Schema（4 entity / 6 relation）

**実装方針**: EXTERNAL_DESIGN.ja.md §1 の概念（Purpose / Concept / Source specs / ChapterAnchor / Entity Relationship Graph / Hierarchical Cluster）と §5.4 の構造化 context（ConstraintContext / TargetContext / ConflictNotes / ReviewNotes）を実現するため、graph schema は **4 entity / 6 relation の軽量版**を採用する。Orchestrator 側（§3）でこれらの概念を構造化して提供する。

**Entity（4 種）**:

| Entity | 抽出方式 | 説明 |
|---|---|---|
| `DOCUMENT` | deterministic（CLI / Parser）| ファイル単位（`docs/spec/foo.md`）|
| `CHAPTER` | deterministic（Markdown heading から）| 上位章（H1 / H2）|
| `SECTION` | deterministic（Markdown heading から）| 下位節（H2 / H3）|
| `ANCHOR` | LLM 抽出（SchemaLLMPathExtractor）| 章のキーアンカー（主要キーワード / 概念 / トピック、3〜7 個）。EXTERNAL_DESIGN.ja.md §1 の ChapterAnchor の意味要素に対応する。「どの ANCHOR が Core 文書（Concept）の概念に対応するか」は graph entity 型では区別せず、Orchestrator が retrieval 時に Core 文書と比較して判定する（transient annotation）|

**Relation（6 種）**:

| Relation | 抽出方式 | 説明 |
|---|---|---|
| `CONTAINS` | deterministic | DOCUMENT -> CHAPTER、CHAPTER -> SECTION |
| `MENTIONS` | LLM 抽出 | CHAPTER / SECTION -> ANCHOR（弱参照、grounding）|
| `RELATED_TO` | LLM 抽出 | 弱関連（章同士 / ANCHOR 同士、SUPPORTS / ALTERNATIVE_TO の抽象化）|
| `DEPENDS_ON` | LLM 抽出 | 依存関係（章同士、CONSTRAINS の抽象化を含む）|
| `REFINES` | LLM 抽出 | 精緻化 / 詳細化（SUPERSEDES の抽象化を含む）|
| `CONTRASTS_WITH` | LLM 抽出 | 対比 / 異なる視点（CONFLICTS_WITH より緩い、graph 上の Conflict 確定は §1.5 二段階を経る）|

**deterministic 部分（DOCUMENT / CHAPTER / SECTION / CONTAINS）は spec-grag CLI が Markdown AST から直接生成し、graph_store.upsert_nodes / upsert_relations で投入する**。LLM 抽出に任せない（精度・速度・冪等性の都合）。

### 2.2 EXTERNAL_DESIGN.ja.md 概念と graph schema の対応表

EXTERNAL_DESIGN.ja.md の各概念を、軽量 graph schema + Orchestrator 実装でどう実現するかの対応:

| EXTERNAL_DESIGN.ja.md 概念 | graph schema での表現 | 実装場所 |
|---|---|---|
| Purpose（人手書き、不変）| graph に持たない | spec-grag CLI が常に ConstraintContext に追加（経路 3 Step 4）|
| Concept（コアコンセプト、人承認） | Core 文書（user-managed、graph 外）。graph の ANCHOR が Core 文書の個別概念への参照候補として機能する | spec-grag CLI が Core 文書管理。Orchestrator が ANCHOR と Core 文書を比較し、更新候補を検出（§3.4）|
| Source specs | DOCUMENT / CHAPTER / SECTION（heading から deterministic）| spec-grag CLI が Markdown AST 解析 |
| ChapterAnchor | ANCHOR entity + ChapterAnchor artifact（summary / key_entities / key_concepts / evidence）+ Agentic search（§2.5 フォールバック）| ANCHOR は graph に乗せ、章別要約・主要エンティティ等は sidecar として保持する |
| Entity Relationship Graph | 4 entity / 6 relation の graph 全体 | LlamaIndex Property Graph 標準フロー |
| Hierarchical Cluster | graph に持たない。/spec-core 時に cluster snapshot を sidecar 生成・更新 | Orchestrator が章間 relation traversal で算出し sidecar に永続化、retrieval 時に読み込み + 補完（§3.5）|
| ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes / ReviewNotes | graph に持たない | Orchestrator が InjectionContext のフィールドに振り分け（§3.1）|
| 4 軸評価 | graph に持たない（transient annotation）| Orchestrator が NodeWithScore.metadata に後付け（§3.2、spike 03 で実証）|
| Conflict 二段階確定 | graph 上の CONTRASTS_WITH は Conflict 候補のヒントのみ、Orchestrator 側 Validator が確定 | グラフ構造ベース + ルールベース + LLM Classification 候補（§1.5 / §3.3）|
| Concept 承認制 | graph と無関係 | spec-grag CLI が unified diff を hunk 単位で人承認 UX 提供（§3.4）|
| Answer 生成 4 区分 | graph と無関係 | LLM (Answer) への prompt 制約として実装（§3.6）|

### 2.3 SchemaLLMPathExtractor へのスキーマ受理形式（Phase 0 確認済）

```python
from typing import Literal

Entities = Literal["DOCUMENT", "CHAPTER", "SECTION", "ANCHOR"]
Relations = Literal["CONTAINS", "MENTIONS", "RELATED_TO", "DEPENDS_ON", "REFINES", "CONTRASTS_WITH"]

# 関係型整合 schema（接続可能な triple）
kg_validation_schema = [
    ("DOCUMENT", "CONTAINS", "CHAPTER"),
    ("CHAPTER", "CONTAINS", "SECTION"),
    ("CHAPTER", "MENTIONS", "ANCHOR"),
    ("SECTION", "MENTIONS", "ANCHOR"),
    ("CHAPTER", "RELATED_TO", "CHAPTER"),
    ("CHAPTER", "DEPENDS_ON", "CHAPTER"),
    ("CHAPTER", "REFINES", "CHAPTER"),
    ("CHAPTER", "CONTRASTS_WITH", "CHAPTER"),
    ("ANCHOR", "RELATED_TO", "ANCHOR"),
    ("ANCHOR", "DEPENDS_ON", "ANCHOR"),
    ("ANCHOR", "REFINES", "ANCHOR"),
    ("ANCHOR", "CONTRASTS_WITH", "ANCHOR"),
]

extractor = SchemaLLMPathExtractor(
    llm=codex_cli_adapter,                  # CodexCLIAdapter (CustomLLM)
    possible_entities=Entities,
    possible_relations=Relations,
    kg_validation_schema=kg_validation_schema,
    strict=True,
    extract_prompt="<日本語プロンプト>",  # spec-grag が用意
    max_triplets_per_chunk=20,
)

# R2: kg_extractors=[ImplicitPathExtractor(), schema_extractor] と明示
```

運用最適化として、複数 section を 1 prompt にまとめる batch extraction を許可する。
batch 経路でも各 triplet は `source_section_id` を必ず持ち、正規化後の
ANCHOR / relation / unresolved_relation には section 起点の provenance を保持する。
これにより初回 rebuild の LLM call 数を減らしつつ、incremental 更新と
`safe_delete_by_section` の粒度は section 単位のまま維持する。
section 化する heading depth は `section_max_heading_level` で制御できる。
`4` の場合は `####` までを section とし、`#####` 以下は直近の親 section の本文に含める。

### 2.4 Section grounding / normalization（LLM 出力の正規化）【方針案、spike 06 で検証予定】

> **検証状態**: 本節の正規化ルールは **どの SURVEY・spike でも未検証**。spike 06 で SchemaLLMPathExtractor + 軽量 schema の動作を確認する中で詰める。LLM が生成する自由文字列の分布・解決候補の曖昧性・embedding 類似の閾値設定は実装着手後に変わり得る。

SchemaLLMPathExtractor の出力をそのまま graph に確定投入してはいけない。LLM が章名 / 節名から派生して生成した CHAPTER / SECTION ノードと、deterministic に作った CHAPTER / SECTION ノードの **ID を正規化して接続**する責務は spec-grag CLI が持つ。

理由: SchemaLLMPathExtractor は LLM に「この章 X が章 Y に DEPENDS_ON している」と推論させると、LLM が `"章 Y"` 等の自由文字列で新規 CHAPTER / SECTION ノードを生成する。一方で spec-grag は heading から `docs/foo.md#section-y` のような deterministic な section_id を持つ CHAPTER / SECTION ノードを既に作っている。両者を結ばないと、graph 上で **同名・別 ID の孤立ノード** が増える。

**正規化ルール**:

| ルール | 内容 |
|---|---|
| 入力 chunk metadata | LlamaIndex の `Document` / `TextNode` に `current_section_id` / `heading_path` / `doc_path` を metadata として渡す |
| 抽出範囲の限定 | LLM には原則として **current section を source とする relation のみ抽出**させる（自由文字列の CHAPTER / SECTION ノードを大量生成しないよう prompt で制約） |
| target の解決 | LLM が relation の target として出した CHAPTER / SECTION の自由文字列は、`target_hint` として一旦保持し、spec-grag CLI が **既存 deterministic section_id に解決**する（heading text / heading_path の文字列マッチ + embedding 類似で）|
| 解決できない target の扱い | 通常 relation として graph に投入しない。`unresolved_relations` sidecar に保存し、InjectionContext では ReviewNotes に落とす |
| 低信頼 relation の扱い | confidence が閾値未満の relation は traversal / cluster の入力に使わない。`RELATED_TO` の低信頼候補として graph を汚染しない |
| 重複ノード生成の禁止 | deterministic node と同名でない CHAPTER / SECTION ノードを LLM が新規作成することは **graph 投入時に拒否**する |
| ANCHOR は対象外 | この正規化は CHAPTER / SECTION のみに適用。ANCHOR は LLM が自由に生成して良い |

Section grounding は保守的に扱う。文字列一致・heading_path 類似・embedding 類似のいずれでも十分な確信が得られない target は、デフォルトで `unresolved_relations` に落とし、通常 relation として graph に投入しない。閾値の具体値は spike 06 で実測して決めるが、閾値未満を `RELATED_TO` の低信頼候補として graph に残す fallback は採用しない。

実装は Phase 1 verification の spike 06（軽量 schema + 章アンカー抽出）で検証する。

`unresolved_relations` sidecar の最小 schema:

```text
unresolved_relations（.spec-grag/graph/unresolved_relations.json）:
  version: string
  graph_revision: string
  generated_at: ISO8601 timestamp
  entries[]:
    unresolved_relation_id: string
    source_document_id: string
    source_chapter_id: string
    source_section_id: string
    source_chunk_id: string
    source_hash: string
    extract_run_id: string
    source_id: string
    relation_type: RELATED_TO | DEPENDS_ON | REFINES | CONTRASTS_WITH
    target_hint: string
    reason: ambiguous_target | missing_target | low_confidence | schema_rejected
    evidence_excerpt?: string
    review_required: true
```

### 2.5 ChapterAnchor artifact と欠損時の Agentic search フォールバック

EXTERNAL_DESIGN.ja.md §1 の ChapterAnchor は「章別キーアンカー。各章の主要エンティティ、キー概念、要約」であるため、graph 上の `ANCHOR` entity だけでは表現しない。`/spec-core` 時に章単位の `ChapterAnchor artifact` を sidecar として生成・更新し、`/spec-inject` / `/spec-realign` では graph の ANCHOR と sidecar を統合して InjectionContext に反映する。

```text
ChapterAnchor artifact（.spec-grag/graph/chapter_anchors.json）:
  version: string
  graph_revision: string
  generated_at: ISO8601 timestamp
  anchors[]:
    chapter_anchor_id: string
    document_id: string
    chapter_id: string
    source_section_ids[]: string
    source_hashes[]: string
    generated_at: ISO8601 timestamp
    source_origin: GRAG | AgenticSearch | both
    summary: string
    key_entities[]:
      name: string
      kind?: string
      evidence_excerpt?: string
    key_concepts[]:
      name: string
      related_anchor_ids[]?: string
      evidence_excerpt?: string
    key_terms[]: string
    related_sections[]:
      section_id: string
      relation_type?: RELATED_TO | DEPENDS_ON | REFINES | CONTRASTS_WITH
      confidence: low | medium | high
    evidence[]:
      section_id: string
      source_span?: string
      excerpt: string
    quality:
      extraction_confidence: low | medium | high
      coverage: low | medium | high
      stale: boolean
```

`ANCHOR` entity は ChapterAnchor artifact の key_concepts / key_terms の graph 検索入口である。ChapterAnchor artifact 自体は判断主体ではなく、課題ごとの 4 軸評価で `constraint_context.chapter_anchor_constraints` または `target_context.related_chapter_anchors` に振り分ける。

ChapterAnchor artifact は章単位の artifact であるため、section が 1 つだけ変わった場合でも、該当章の artifact は章全体から再集約する。

```text
ChapterAnchor artifact update:
  1. changed / added / removed section から affected_chapter_id を特定
  2. affected chapter の ChapterAnchor artifact を dirty にする
  3. affected chapter 配下の最新 ANCHOR / relation / evidence を取得
  4. summary / key_entities / key_concepts / key_terms / related_sections を再集約
  5. source_section_ids[] / source_hashes[] を current_section_manifest に合わせて更新
  6. 再生成が成功したら chapter_anchor artifact を atomically replace し、
     quality.stale = false に戻す
  7. 再生成に失敗した場合は quality.stale = true のまま warnings / ReviewNotes に出す
```

ChapterAnchor artifact は章単位 artifact なので、`safe_delete_by_section` では物理削除しない。section 変更・削除・rename・split・merge では affected chapter を `quality.stale = true` にし、再集約成功時に chapter 単位で atomic replace する。これにより、再集約に失敗しても前回の章アンカーを stale として保持できる。

GRAG が章アンカーを持っていない章（抽出失敗 / 質が低い / 新規追加章で未抽出）は、`/spec-inject` / `/spec-realign` 実行時に LLM が章本文を Agentic search で読んで動的に章アンカーを作成する。spec-grag CLI は GRAG 由来と Agentic search 由来をマージして、InjectionContext の `constraint_context.chapter_anchor_constraints` / `target_context.related_chapter_anchors` に振り分ける（各 item の `source_origin` metadata で由来を区別）。実装は Phase 1 spike 08。

### 2.6 ノード / リレーションのプロパティ

**必須プロパティ**:

| プロパティ | 対象 | 用途 |
|---|---|---|
| `document_id` | 全 entity / 全 relation | 所属 document の id |
| `chapter_id` | CHAPTER / SECTION / ANCHOR / 全 relation | 所属 chapter の id。cluster snapshot の更新範囲判定に使用 |
| `section_id` | SECTION / ANCHOR / section 起点 relation | section 単位 stale 除去（safe_delete_by_section、R1）および変更検出の基準 |
| `heading_path` | CHAPTER / SECTION | 「1 / 認証」のような可読 path |
| `source_hash` | SECTION | section 単位 SHA-256（変更検出の基準）|

**LLM extraction artifact 必須 provenance**:

LLM 抽出由来の node / relation / vector embedding / ChapterAnchor artifact / unresolved_relation には、section 起点の stale 除去と監査のため、次を必ず付与する。章間 relation が graph 上で `CHAPTER -> CHAPTER` として保存される場合でも、抽出元 section は `source_section_id` として保持する。

| プロパティ | 対象 | 用途 |
|---|---|---|
| `source_document_id` | LLM 抽出 artifact 全て | 抽出元 document |
| `source_chapter_id` | LLM 抽出 artifact 全て | 抽出元 chapter、cluster dirty 判定 |
| `source_section_id` | LLM 抽出 artifact 全て | section 単位 stale 除去の主キー |
| `source_chunk_id` | LLM 抽出 artifact 全て | LlamaIndex chunk / TextNode 単位の追跡 |
| `source_hash` | LLM 抽出 artifact 全て | 抽出時の section hash |
| `extract_run_id` | LLM 抽出 artifact 全て | 同一 core run の抽出結果の追跡 |
| `extractor_name` | LLM 抽出 artifact 全て | SchemaLLMPathExtractor / AgenticSearch 等 |
| `extractor_version` | LLM 抽出 artifact 全て | prompt / schema / adapter version |
| `extracted_at` | LLM 抽出 artifact 全て | ISO8601 timestamp |

**変更検出・再抽出の粒度**: section 単位で統一する。変更検出は section 単位の `source_hash` 比較で行い、変更があった section のみ `safe_delete_by_section` + 再抽出する。`safe_delete_by_section` は `source_section_id == section_id` の LLM 抽出 artifact（ANCHOR、LLM 抽出 relation、vector embedding、unresolved_relation）を削除する。ChapterAnchor artifact は章単位 artifact のため物理削除せず、affected chapter を dirty にする。親 CHAPTER ノード、SECTION ノード、deterministic CONTAINS relation は削除しない。CHAPTER の再構築は章名変更時のみ chapter_id レベルで行う。cluster snapshot の更新は `source_section_id` をもとに影響を受けた chapter / cluster を dirty にして再算出する。

**deterministic structure reconciliation**:

section の本文変更だけでなく、削除・rename・分割・統合・chapter 構造変更を扱うため、`/spec-core incremental` は毎回 Markdown heading 構造から `current_section_manifest` を作り、前回の `source_manifest` と比較する。Markdown heading 構造の解析は CommonMark preset の `markdown-it-py` を標準とし、ATX / Setext heading、fenced code、HTML block を parser の構文解釈に従って扱う。blockquote / list item 内の heading は source spec の section 境界としては扱わない。

```text
current_section_manifest:
  entries[]:
    document_id: string
    chapter_id: string
    section_id: string
    heading_path: string
    heading_start_line: integer
    source_hash: string
```

比較結果:

```text
changed_section_ids:
  - section_id は同じだが source_hash が変わった section
added_section_ids:
  - current_section_manifest にだけ存在する section
removed_section_ids:
  - 前回 source_manifest にだけ存在する section
structure_changed_chapter_ids:
  - chapter heading / heading_path / 階層が変わった chapter
```

処理規則:

```text
removed_section_ids:
  - SECTION node を削除
  - SECTION に接続する deterministic CONTAINS relation を削除
  - source_section_id 由来の LLM extraction artifact を削除
  - vector embedding を削除
  - ChapterAnchor artifact を dirty / 再集約対象にする
  - unresolved_relation を削除
  - affected cluster を dirty にする

renamed section:
  - removed + added として扱う

split / merge:
  - removed + added の集合として扱う

chapter heading / 階層変更:
  - chapter_id レベルで deterministic CHAPTER / SECTION / CONTAINS を再構築する
  - affected chapter の ChapterAnchor artifact と cluster を dirty にする
```

**任意プロパティ**（debug / evidence / 拡張用、取得できたら graph に乗せる）:

| プロパティ | 対象 | 用途 |
|---|---|---|
| `embedding` | ANCHOR | vector retrieval 用（spec-grag CLI が事前計算してセット）|
| `description` | ANCHOR | LLM 抽出時の付加情報 |
| `source_span` | 章間 relation / ANCHOR | 行範囲（[26:1263-1289] 等）。debug / 根拠提示用 |
| `evidence_excerpt` | 章間 relation / ANCHOR | LLM 抽出 relation の短い根拠テキスト |
| `heading_start_line` | CHAPTER / SECTION | section の Markdown 内開始行番号 |
| `created_at` / `updated_at` | 全 entity | ISO8601 timestamp |

**transient annotation**（4 軸評価）は graph には書かない（§1.6 / §3.2）。

---

## 3. Orchestrator 側で EXTERNAL_DESIGN.ja.md 概念を実現する

軽量 graph schema には乗せず、Orchestrator が EXTERNAL_DESIGN.ja.md の概念を実現する責務:

### 3.1 InjectionContext の構造化（ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes / ReviewNotes）

EXTERNAL_DESIGN.ja.md §5.4 / §8.1 の構造を Orchestrator が組み立てる。InjectionContext のトップレベル構造は EXTERNAL_DESIGN.ja.md §8.1 を厳守し、独自フィールドを追加しない。

```text
Orchestrator が経路 3 で行う:
  retrieval 候補（NodeWithScore のリスト、graph + Agentic search 由来）
    |
  4 軸評価付与（§3.2）
    |
  各候補を 4 軸の値で振り分け（§1.6 のフィールド対応表）:
    constraint_relevance != none -> constraint_context.{...}_constraints
    target_relevance != none     -> target_context.{...}
    conflict == true            -> conflict_notes（Validator 確定後のみ）
    review_required == true     -> review_notes
    すべて none/false (派生 irrelevant) -> excluded_as_irrelevant
    |
  各 item の metadata に source_origin（GRAG / Agentic search / 両方）を付与
    |
  LLM (Classification) が各候補に classification_notes を生成:
    constraint_context.classification_notes[]: 制約側に分類した理由
    target_context.classification_notes[]: 修正対象側に分類した理由
    |
  approved_concept_update を構築:
    経路 1 で Concept diff が accept された場合 -> 承認内容を approved_concept_update に格納
    Concept diff がなかった / reject された場合 -> approved_concept_update = null
    |
  approved_conflicts / pending_conflict_review を反映:
    承認済み source-level Conflict -> conflict_notes
    未承認 source-level Conflict 候補 -> review_notes
    task 依存の semantic_conflict_candidate -> review_notes
    |
  InjectionContext として構造化出力（EXTERNAL_DESIGN.ja.md §8.1）
```

同一項目が複数フィールドに同時所属しうる（例: Constraint としても Target としても関連、かつ Conflict 候補で review 必要）。

### 3.2 4 軸 transient annotation（graph 不汚染、spike 03 で実証）

- LLM (Classification) が retrieval 候補 each に 4 軸の **候補値**を出す
  - `review_required = true / false`
  - `semantic_conflict_candidate = true / false`
  - `constraint_relevance = none | low | medium | high`
  - `target_relevance = none | low | medium | high`
- Orchestrator が NodeWithScore.metadata に後付け（spike 03 で実証）
- graph_store / persist パスには 4 軸を書き込まない（spike 03 で graph 不汚染を確認）
- LLM 単独では `conflict = true` を発火させない（§1.5 二段階）

### 3.3 Conflict 二段階確定（Orchestrator 側 Validator）

§1.5 の 3 段階パイプラインを Orchestrator が実装する。

```text
段階 1（グラフ構造ベース、決定論的）:
  - 章間 REFINES の循環検出
  - 同一 ID への異なる属性並存検出
  - 同一 ANCHOR の複数 section MENTIONS は review_required 候補（conflict ではない）
  -> 循環 / 属性並存に該当した候補を「conflict 候補」として retrieval result に印を付ける
  -> 複数 MENTIONS は review_required として印を付ける（段階 3 で矛盾判定）

段階 2（ルールベース、決定論的）:
  - Purpose の制約条項と Source spec の対立量化詞検出
  - FreshnessReport.source_manifest の scanned_at と section の updated_at の食い違い検出（§4.7）
  - Required と Optional の同時指定検出
  - MUST と MUST NOT、禁止と必須、上限値 / 下限値、状態遷移不能、権限条件、Concept と Source spec の逆転を検出
  -> 段階 1 と合わせて「conflict 候補」を絞り込む

段階 3（LLM 推論、補助）:
  - 段階 1 / 2 で疑わしい候補のみ LLM (Classification) で意味的妥当性を確認
  - LLM が semantic_conflict_candidate = true / review_required = true を出してよい
  - LLM 単独で conflict = true は不可

確定:
  conflict = true は構造的根拠（段階 1 or 2）または Human approval を必須とする
```

Conflict approval workflow は実装対象とする。検出 rule の網羅率は versioned rule pack として増やすが、候補検出 -> 人間確認 -> approved conflict -> InjectionContext 反映の縦切りは最初から持つ。

Phase 10 では `/spec-core` の core 更新後に Source specs 全体を deterministic scan し、source-level Conflict candidate を `pending_conflict_review` として自動生成する。初期 rule pack は required/optional、must vs must not、必須/禁止、permission scope、numeric bounds、state transition、日本語量化詞を扱う。candidate には `source_document_id`、`source_section_id`、`source_span`、`source_hash`、`excerpt` を持たせ、既存 `approved_conflicts` と rejected fingerprint に一致する候補は再生成しない。

**source-level Conflict review artifact**:

```text
pending_conflict_review（.spec-grag/pending/conflict_review_<review_id>.json）:
  review_id: string
  base_graph_revision: string
  base_source_manifest_hash: string
  generated_at: ISO8601 timestamp
  candidates[]:
    candidate_id: string
    conflict_type: string
    severity: low | medium | high
    rule_id?: string
    summary: string
    reason: string
    evidence_spans[]:
      source_document_id: string
      source_section_id: string
      source_span: string
      source_hash: string
      excerpt: string
    status: pending | accepted | rejected | deferred | revised
    revision_instruction?: string
```

`pending_conflict_review` はユーザーに直接読ませる UI ではない。Agent がチャット上で candidate 単位に要約、根拠 source span、conflict_type、severity、選択肢を提示し、ユーザーの accept / reject / defer / 修正指示をエージェント内部の状態遷移操作に変換する。これは外部 CLI 契約ではない。内部 JSON は再開・hash mismatch 検査・再通知抑制のための状態である。

```text
/spec-core
  -> CoreResult.conflict_review
  -> ResultEnvelope.execution.pending_conflict_review_id
  -> .spec-grag/pending/conflict_review_<review_id>.json を作成

approve_conflict_candidate(review_id, candidate_id)
reject_conflict_candidate(review_id, candidate_id)
defer_conflict_candidate(review_id, candidate_id)
revise_conflict_candidate(review_id, candidate_id, instruction)
apply_accepted_conflict_candidates(review_id)
chat_approval_transport(options.approval)
```

`apply_accepted_conflict_candidates` 時の必須検査:

```text
1. base_graph_revision / base_source_manifest_hash が現在値と一致することを確認
2. 不一致なら apply せず blocked とし、再検出または人間レビューを要求
3. accepted candidate のみ approved_conflicts sidecar に反映
4. rejected candidate は false positive として fingerprint を保存し、同一根拠での再通知を抑制
5. deferred candidate は未確定として pending review に保持し、関連 task では ReviewNotes に落とす
6. revised candidate は revision_instruction を保存し、再検出または再分類後に再度 candidate 承認に戻す
```

**approved_conflicts sidecar**:

```text
approved_conflicts（.spec-grag/graph/approved_conflicts.json）:
  version: string
  graph_revision: string
  source_manifest_hash: string
  conflicts[]:
    conflict_id: string
    source_candidate_id: string
    conflict_type: string
    severity: low | medium | high
    summary: string
    reason: string
    evidence_spans[]
    approved_at: ISO8601 timestamp
    approved_by: human
  rejected_fingerprints[]:
    fingerprint: string
    rejected_at: ISO8601 timestamp
```

Graph store 本体に `conflict=true` を恒久 property として書き込まない。承認済み Conflict は sidecar として保持し、`/spec-inject` / `/spec-realign` が task に関連するものだけ `ConflictNotes` へ昇格する。未承認 candidate は `ReviewNotes` に出すが、確定 Conflict として Answer に使わせない。

### 3.4 Concept (Core) 承認制【方針案、spike 06 + 09 で検証予定】

> **検証状態**: ANCHOR 抽出自体が未検証（spike 06 で初検証予定）。ANCHOR と Core 文書の比較ロジック、候補検出ロジックは一切検証されていない。ANCHOR 抽出の品質次第で候補生成方式が変わり得る。

EXTERNAL_DESIGN.ja.md §3.4 / §4.5 の Concept 更新候補生成プロセス:

```text
1. GRAG の ANCHOR + relation から「Core 書き換え候補」を検出
   - SchemaLLMPathExtractor が章から ANCHOR entity を抽出
   - Orchestrator が ANCHOR と現 Core 文書の概念を比較
   - 新規概念の出現、既存概念の変化、関連 relation の変動を候補とする
2. LLM が Agentic search で章本文・現 Core を確認、unified diff を生成
3. SPEC-grag CLI がユーザーに hunk 単位で提示
4. ユーザーが accept / reject / 修正指示
5. SPEC-grag CLI が accept された hunk を Core 文書に反映
```

Concept diff は CLI プロセスをまたいで hunk 単位に承認されるため、生成時に pending state を永続化する。未承認 diff は Concept retrieval / InjectionContext / Answer 生成に絶対に混ぜない。

Concept diff により `/spec-inject` / `/spec-realign` が `blocked` になった場合、ユーザーはチャット上で Concept を手動修正するか、`accept` / `reject` / `revise` 相当の判断を行い、その後同じコマンドを再実行する。SPEC-grag は blocked 状態のまま InjectionContext / Answer を生成しない。

`pending_concept_diff` はユーザーに直接読ませる UI ではない。Agent がチャット上で hunk 単位に要約、根拠 source span、差分、選択肢を提示し、ユーザーの承認 / 非承認 / 修正指示をエージェント内部の状態遷移操作に変換する。これは外部 CLI 契約ではない。内部 JSON は再開・hash mismatch 検査・hunk 状態管理のための状態である。

```text
pending_concept_diff（.spec-grag/pending/concept_diff_<diff_id>.json）:
  diff_id: string
  base_concept_hash: string
  generated_at: ISO8601 timestamp
  task_context:
    command: spec-core | spec-inject | spec-realign
    task_prompt?: string
    changed_source_section_ids[]: string
    extract_run_id: string
  hunks[]:
    hunk_id: string
    file: string
    old_range: string
    new_range: string
    diff_text: string
    status: pending | accepted | rejected | revised
    revision_instruction?: string
    revision_history[]?: string
  expires_at?: ISO8601 timestamp
```

内部状態遷移操作（外部 CLI 契約ではない）:

```text
/spec-core
  -> CoreResult.concept_diff
  -> ResultEnvelope.execution.pending_concept_diff_id
  -> .spec-grag/pending/concept_diff_<diff_id>.json を作成

accept_concept_hunk(diff_id, hunk_id)
reject_concept_hunk(diff_id, hunk_id)
revise_concept_hunk(diff_id, hunk_id, instruction)
apply_accepted_concept_diff(diff_id)
chat_approval_transport(options.approval)
```

`apply_accepted_concept_diff` 時の必須検査:

```text
1. base_concept_hash == 現在の concept_file hash を確認
2. 不一致なら apply せず blocked とし、再生成または人間レビューを要求
3. accepted hunk のみ適用
4. rejected / pending hunk は適用せず、pending_concept_diff を未解決のまま残す
5. revised hunk は revision_instruction に基づき diff_text を再生成し、status=pending として再度 hunk 承認に戻す
6. 適用後に Core Concept index（§3.7）を再生成
7. watch_queue に queued change があれば、最新 Concept base hash と最新 Source specs / graph artifact で再評価し、必要な場合だけ次の pending_concept_diff を 1 件作成する
```

Phase 10 以降、Concept diff は **単一 pending** とする。`.spec-grag/pending/concept_diff_<diff_id>.json` に未解決 hunk がある間は、新しい Concept diff JSON を作らない。background watcher または core incremental が pending 中の Source specs 意味変更を検出した場合は、変更 section を `.spec-grag/state/watch_queue.json` に保存し、Concept 候補ラベルを `.spec-grag/state/provisional_concept_cache.json` に保存して停止する。

Concept diff の確認は 3 択として扱う。

| 選択 | 内部状態 | 次回コマンド |
|---|---|---|
| そのまま承認 | hunk を accepted にし、内部 apply で Concept へ反映する。反映後に provisional cache をクリアする | queued change があれば次 diff、なければ fresh |
| 修正指示 | hunk を revised にし、修正案を再生成した後、同じ hunk を pending approval に戻す。承認 apply 後に provisional cache をクリアする | 修正版が承認されるまで pending |
| 非承認 | hunk を rejected にするが、pending は未解決として残し、provisional cache も残す | 同じ diff を再度承認フローに出す |

```text
watch_queue（.spec-grag/state/watch_queue.json）:
  version: string
  updated_at?: ISO8601 timestamp
  pending_concept_diff_id?: string
  changes[]:
    source_section_id: string
    semantic_hash: string
    reason: string
    detected_at: ISO8601 timestamp

provisional_concept_cache（.spec-grag/state/provisional_concept_cache.json）:
  version: string
  updated_at?: ISO8601 timestamp
  candidates[]:
    label: string
    normalized_label: string
    aliases[]: string
    supporting_sections[]: string
    semantic_hashes[]: string
    confidence: number
    provider?: string
    model?: string
    prompt_version?: string
    first_seen: ISO8601 timestamp
    last_seen: ISO8601 timestamp
    status: provisional
```

provisional concept cache は未承認候補の観測・重複抑制・再評価効率化専用である。Core Concept index、InjectionContext、Answer、ConflictNotes、production readiness の authoritative input には使わない。

候補生成方式 (P) GRAG 経由 vs (Q) LLM 直接 の比較は Phase 1 spike 09 で行う。

### 3.5 Hierarchical Cluster（/spec-core 時に sidecar 生成 + retrieval 時に補完）【方針案、spike 12 で検証予定】

> **検証状態**: `get_rel_map(depth=2)` は spike 01/03 で動作確認済だが、**cluster 算出ロジック（何をもって「クラスタ」とするか）・sidecar 形式・incremental 再算出**は一切検証されていない。永続化パスや形式は spike 12 の結果で変わり得る。

EXTERNAL_DESIGN.ja.md §1 の Hierarchical Cluster は「GRAG 更新時に生成・更新する」と定義されている。graph schema には乗せないが、**`/spec-core` の完了時に cluster snapshot を sidecar として生成・永続化する**:

```text
/spec-core 時（経路 1 / 経路 2）:
  - graph_store の章間 relation（DEPENDS_ON / REFINES / RELATED_TO）を traversal
  - get_rel_map(seed_chapters, depth=2-3) で関連章群を取得
  - 章群をクラスタとしてグルーピング
  - cluster snapshot を .spec-grag/graph/cluster_snapshot.json に永続化
  - 経路 1（incremental）: 変更 section に関連する cluster のみ再算出
  - 経路 2（--all）: 全 cluster を再生成

/spec-inject・/spec-realign 時（経路 3 / 経路 4）:
  - cluster snapshot を読み込み、retrieval 候補と合わせて InjectionContext に反映
  - graph 更新後に cluster snapshot が古くなっている場合は relation traversal で補完
```

`cluster_snapshot.json` の最小 schema:

```text
cluster_snapshot（.spec-grag/graph/cluster_snapshot.json）:
  version: string
  graph_revision: string
  generated_at: ISO8601 timestamp
  clusters[]:
    cluster_id: string
    level: chapter | concept | relation
    seed_ids[]: string
    member_chapter_ids[]: string
    member_anchor_ids[]: string
    member_concept_chunk_ids[]: string
    relation_paths[]:
      source_id: string
      relation_type: RELATED_TO | DEPENDS_ON | REFINES | CONTRASTS_WITH
      target_id: string
      source_section_id: string
      confidence: low | medium | high
    dominant_relation_types[]: string
    source_section_ids[]: string
    confidence: low | medium | high
    stale: boolean
```

`level=concept` の cluster は graph 上の CONCEPT node を指さない。`member_concept_chunk_ids[]` は §3.7 の Core Concept index に含まれる `concept_chunk_id` を参照する。graph の ANCHOR と Core Concept index の chunk は Orchestrator が retrieval 時に対応付ける。

`unresolved_relations`、confidence が閾値未満の relation、`review_required` のみで確定していない relation は cluster 算出の入力に使わない。incremental 更新では、変更 section の `source_section_id` を含む cluster を `stale=true` にし、再算出が完了してから `stale=false` に戻す。

実装は Phase 1 spike 12。

### 3.6 Answer 生成 4 区分（LLM への prompt 制約）

EXTERNAL_DESIGN.ja.md §6.5 の Answer 生成契約。LLM (Answer) への prompt 制約として実装:

```text
前提:
  - Answer 生成 phase に入る前に InjectionContext 構築 loop が context_ready で完了している
  - LLM (Answer) の入力は task_prompt + InjectionContext のみ
  - Answer 生成 phase では tool / raw source read / 追加 Agentic search を禁止する
  - 追加情報が必要な場合は Answer を生成せず、
    ReviewNotes または blocked status として Orchestrator に返す
  - InjectionContext に存在しない事実を推測で補わない。必要情報が不足している場合は、
    不足している情報を明示し、Answer ではなく NeedMoreContextResult / blocked に戻す

LLM へ渡す prompt template（spec-grag が固定）:
  - InjectionContext.ConstraintContext を「今回の回答で守る制約」として扱う
  - InjectionContext.TargetContext を「今回の修正候補または検討対象」として扱う
  - InjectionContext.ExclusionNotes は「回答の前提情報として採用しない」
  - InjectionContext.ConflictNotes は Answer 内で明示する
  - InjectionContext.ReviewNotes は Answer 内で「人間レビューが必要な点」として明示する
  - InjectionContext.approved_concept_update / warnings は「不確実性または人間レビュー項目」として Answer 内で明示する

Answer は次を区別して記述:
  1. 今回の回答で守る制約
  2. 今回の回答で扱う修正候補または検討対象
  3. 競合 / 不確実性 / 人間レビューが必要な点
  4. 課題プロンプトへの回答または修正案

制約と矛盾する案を出す場合は、その矛盾を Answer 内で明示し、人間レビューが必要な点として扱う。
```

### 3.7 Core Concept index（graph 外の Concept retrieval 基盤）

Concept を graph entity から外したため（§2.1）、経路 3 step 5a の Core Concept retrieval には graph とは別の index が必要:

```text
Core Concept index（.spec-grag/graph/concept_index.json または vector_store namespace=core_concept）:
  - metadata: embedding_provider / embedding_model / embedding_dimension
  - concept_file を heading / paragraph 単位に分割
  - 各 chunk: concept_chunk_id / heading_path / text_hash / embedding
  - 未承認 Concept diff は index に入れない
  - metadata と現行 config の embedding provider / model / dimension が一致しない場合は rebuild 対象にする

更新タイミング:
  - /spec-core 経路 1 / 2 で Concept hunk が accept され concept_file が更新された直後（経路 1 step 16 / 経路 2 step 14）
  - concept_file の text_hash が変化していない場合は再生成しない（冪等）

鮮度確認（concept_file の直接編集対応）:
  - /spec-inject / /spec-realign の Core Concept retrieval（経路 3 step 5a）の前に
    concept_file の text_hash と concept_index に記録された concept_file_hash を比較する
  - 不一致の場合は Core Concept index を再生成してから retrieval に進む
  - 再生成できない場合は warnings に concept_index_stale を出す
  - 未承認 Concept diff は再生成後も index に入れない
```

経路 3 step 5a はこの index を使って keyword + embedding 検索を行い、課題に関連する Concept を取得する。

### 3.8 ResultEnvelope status（外部出力 payload を壊さない実行状態）

外部設計の出力構造（CoreResult / InjectionContext / RealignResult）は payload として維持し、CLI transport の envelope に実行状態を載せる。これにより、EXTERNAL_DESIGN.ja.md §8.1 の InjectionContext トップレベル構造を汚さず、§9 の degraded / blocked / failed を機械判定できる。

```text
ResultEnvelope:
  status: ok | degraded | blocked | failed
  result_type: CoreResult | InjectionContext | RealignResult | ConceptApprovalRequiredResult | ConflictApprovalRequiredResult | NeedMoreContextResult | ErrorResult
  payload: object
  execution:
    context_ready?: boolean
    pending_concept_diff_id?: string
    pending_conflict_review_id?: string
    pending_conflict_candidate_ids[]?: string
    failed_sources[]?: string
    degraded_components[]?: string
    runtime_policy?: object
    timing_summary?: object
    stage_timings[]?: object
  warnings[]: string
```

`status` の意味:

| status | 意味 |
|---|---|
| `ok` | 全処理が成功し、payload を通常利用できる |
| `degraded` | 一部 source / extractor / vector_store / cluster 更新に失敗したが、payload は利用可能。warnings と failed_sources を必ず出す |
| `blocked` | Concept diff 未承認、追加 context 不足など、ユーザー操作なしでは次工程へ進めない |
| `failed` | config 不正、source 不在、graph 読み込み不能などで実行不可 |

Phase 10 以降、source-level の未解決 Conflict review が pending state として残る場合、foreground command は `ConflictApprovalRequiredResult` を返して承認フローに入る。確定済み Conflict だけを `ConflictNotes` に反映し、未解決 candidate を確定 Conflict として Answer に使わせない。

`/spec-inject` は `status=blocked` の場合、payload を InjectionContext にせず `ConceptApprovalRequiredResult` / `ConflictApprovalRequiredResult` / `NeedMoreContextResult` / `ErrorResult` のいずれかにする。`/spec-realign` は Answer 生成前に `ResultEnvelope.status in {ok, degraded}` かつ `execution.context_ready == true` を必須条件にする。Purpose 欠落や config 不正など、必須入力の欠落はユーザー操作で補える場合でも `failed` として扱う。

---

## 4. 実装前検証項目（Phase 1 verification）

本章は「仕様を後で決めるための未確定リスト」ではない。§1-§3 で定義した内部契約を、実装方式・ライブラリ挙動・CLI 境界の観点で検証するゲートである。

Phase 1 verification では、外部契約（EXTERNAL_DESIGN.ja.md）と本設計の JSON / sidecar / status 契約を維持したまま、未実証の実装方式を小さく確認する。検証で不成立が分かった場合は、§4.9 の fallback に従って実装方式を差し替える。外部出力構造を縮小したり、Answer 生成 phase に raw source read を戻したりしない。

### 4.1 Phase 1 verification 計画

| spike | 実証内容 |
|---|---|
| **spike 13** | SlashCommandRequest / ResultEnvelope / NeedMoreContextResult / AgenticSearchCandidate JSON protocol + InjectionContext 構造化出力（§1.3.1 / §3.1 / §3.8、EXTERNAL_DESIGN.ja.md §8.1 厳守、source_origin metadata 付与）|
| **spike 05** | `CodexCLIAdapter(CustomLLM)` 実装（`complete` / `stream_complete` / `metadata` の最小実装、subprocess `claude --print --output-format json --json-schema ...` 経由）。**追加検証**: `--json-schema` の schema 違反時挙動（エラー型 / partial output / retry 可否）を含む |
| **spike 06** | SchemaLLMPathExtractor 軽量 schema（4 entity / 6 relation）+ 日本語 prompt + 章アンカー抽出 + Section grounding / normalization（§2.4）+ unresolved_relations sidecar + deterministic structure reconciliation。**追加検証**: (a) pydantic ValidationError 時の LlamaIndex 内蔵 retry 挙動（伝播するか吸収されるか）、(b) `upsert_nodes` の同一 ID merge 挙動（フィールド全置換か部分更新か、incremental update の安全性に直結、SURVEY 04 残課題）、(c) LLM 抽出 artifact への provenance 付与 |
| **spike 07** | vector_store の VECTOR_SOURCE_KEY 連結正規パターン（spike 03 の 0 件問題を解消）。**追加検証**: vector_store 投入時の TextNode.metadata への entity properties コピーパターン（SURVEY 07 残課題、retrieval result に properties を伝播するため必須）|
| **spike 08** | ChapterAnchor artifact schema + affected chapter 単位の再集約 + 章アンカー欠損章の LLM Agentic search フォールバック実装（§2.5）|
| **spike 09** | Concept (Core) 更新提案の (P) GRAG ANCHOR 経由 vs (Q) LLM 直接 の比較 + pending_concept_diff / hunk apply protocol（§3.4）|
| **spike 10** | Classification LLM の 4 軸付与 prompt template + Orchestrator 側 NodeWithScore.metadata 後付けパイプライン（§3.2）|
| **spike 11** | Conflict 二段階 Validator 実装（段階 1 グラフ構造 + 段階 2 ルール + 段階 3 LLM 候補、§3.3）|
| **spike 12** | Hierarchical Cluster の /spec-core 時 sidecar 生成 + retrieval 時読み込み・補完 + dirty/stale 再算出 + Core Concept index 参照（§3.5）|

spike 番号は検証 ID として維持する。実行順は、全コマンドの入口契約になる **spike 13 相当の JSON protocol を最初に固定**し、その後に spike 05-09（経路 1 / 2 の GRAG build / Concept diff）と spike 10-12（経路 3 / 4 の retrieval / validation / cluster）を進める。

### 4.2 LLM プロバイダー実装

- `CodexCLIAdapter(CustomLLM)` の実装（spike 05 で確定）。必須実装は `complete` / `stream_complete` の 2 method + `metadata` property のみ（Phase 0 評価「10+ method」は SURVEY 13 §1.2 で訂正済、`chat` / `acomplete` 等は default 実装あり）
- 並列実行（`asyncio.gather` + `asyncio.Semaphore`）の設計
- timeout / 認証切れ / rate limit / 出力揺れの error handling
- LLM 用途別（Extraction / Classification / Answer）の設定切替
- Ollama generative LLM（B-1）と CodexCLIAdapter（B-2）のハイブリッド可能性（[SURVEY/13](SURVEY/13_path_b_design_options.md) §4 参照）

### 4.3 Concept (Core) 更新承認制 unified diff 生成

EXTERNAL_DESIGN.ja.md §3.4 の Core 更新候補生成プロセスを実装する。

- 候補生成方式: (P) GRAG ANCHOR 経由 vs (Q) LLM 直接（spike 09 で比較）
- diff ライブラリ選定（`difflib` 標準 / サードパーティ）
- diff の context_radius / unified format の出力規約
- ユーザー hunk 単位 accept / reject UX

### 4.4 spec-grag CLI 実装

- フレームワーク選定（Click / Typer / Fire 等）
- パッケージング（`pyproject.toml`、`uv` / `pdm` / `poetry` 等）
- 配布方式（PyPI / git clone / Docker）
- 設定ファイル schema（`.spec-grag/config.toml`）の strict validation

### 4.5 Cross-Encoder rerank（内部設計、必要時に追加）

retriever（PGRetriever / VectorContextRetriever）のスコアで retrieval 候補の関連度が正しく序列化できるかを spike 06 / 07 / 08 の retrieval 動作で評価する。不足が顕在化したら、日本語対応の cross-encoder reranker（例: BAAI/bge-reranker-v2-m3）を spike 14 として PGRetriever の後段に組み込む（R4「fusion / rerank は Orchestrator 側責務」と整合）。

### 4.6 vector retrieval の fallback

> **背景**: spike 03 で vector_store に TextNode を投入しても **0 件返る問題が未解決**（SURVEY 05）。spike 07 で VECTOR_SOURCE_KEY 連結の正規パターンを確立する想定だが、解決できなかった場合の fallback が必要。

PGRetriever / VectorContextRetriever が機能しない / 0 件返す場合の fallback として、graph store の `get` / `get_rel_map` で keyword + property filter を組み合わせた retrieval を spec-grag Orchestrator 側で実装する。spike 07 で実証する。

vector retrieval なしでも、経路 3/4 は graph traversal（PGRetriever + `get_rel_map`）ベースで成立可能。ただし暗黙的な波及先発見（明示 edge にないが意味的に関連する章の発見）の品質は低下する。この場合、Agentic search（§2.5）の補完がより重要になる。

Phase 13 時点では、大多数の project が 5,000 chunks 未満に収まる想定のため、raw chunk dense retrieval は `document_chunks.json` と `chunk_vector_index.json` を正本 / index とする JSON scan を既定として維持する。`dense_scanned_embeddings`、retrieval stage latency、`chunk_vector_index.json` size を観測し、概ね 5,000〜10,000 chunks で Qdrant backend 導入を検討、10,000 chunks 以上または retrieval stage が 500ms〜1s を継続して超える場合は Qdrant backend を推奨する。

Qdrant 導入時も、初期案では `document_chunks.json` を citation / provenance / fallback の正本として残し、Qdrant は ANN index として `chunk_id`、section metadata、hash、graph/artifact revision、短い excerpt、embedding を保持する。query-time は Qdrant search で `chunk_id` top-k を取得し、本文と根拠情報は `document_chunks.json` から引く。これにより Qdrant collection が壊れた場合も `.spec-grag/graph` artifacts から再構築でき、既存の artifact transaction / readiness / offline audit を保てる。

Qdrant backend は local-only 運用を前提に optional backend とする。設定案は `[retrieval].vector_backend = "json" | "qdrant"`、`[retrieval].qdrant_fallback_to_json = true`、`[qdrant].url = "http://localhost:6333"`、`[qdrant].collection = "spec_grag_chunks"` とし、llm-helper とは collection を分離する。Qdrant を chunk 正本へ一元化する案は、CI / local / packaging で Qdrant 必須化、collection schema version、backup/restore、revision rollback を設計できた段階で別途検討する。

### 4.7 FreshnessReport と source_manifest の定義

§1.5 段階 2 および §3.3 段階 2 で参照する「section の鮮度と GRAG の同期状態」を追跡するための定義:

```text
FreshnessReport:
  last_core_run: ISO8601 timestamp（最後に /spec-core が完了した時刻）
  graph_revision: string
  graph_storage_path: string
  source_manifest_path: string（.spec-grag/graph/source_manifest.json）
  warnings: string[]

source_manifest（.spec-grag/graph/source_manifest.json）:
  parser_name: string
  parser_version: string
  entries[]:
    document_id: string
    chapter_id: string
    section_id: string
    stable_section_uid: string（heading rename に強い互換 ID）
    section_aliases[]: string
    heading_path: string
    heading_start_line: integer
    source_hash: string（section 単位 SHA-256）
    extract_run_id: string
    scanned_at: ISO8601 timestamp（最後に GRAG に取り込まれた時刻）
    extractor_versions:
      schema_llm_path_extractor?: string
      codex_cli_adapter?: string
```

`source_manifest` の更新規則:

```text
1. /spec-core は graph / vector_store / ChapterAnchor artifact / cluster snapshot の
   更新が完了するまで source_manifest を書き換えない
2. 更新完了後、source_manifest.json.tmp を生成し、fsync 後に
   source_manifest.json へ atomic replace する
3. status=ok の場合:
   - current_section_manifest の全 entry を反映する
   - scanned_at / extract_run_id / extractor_versions を今回 run の値に更新する
4. status=degraded の場合:
   - 成功 section の entry のみ scanned_at / extract_run_id / extractor_versions を更新する
   - 失敗 section は旧 entry を維持し、failed_sources / warnings に記録する
   - removed section の削除処理に失敗した場合、その旧 entry は維持する
5. status=failed / blocked の場合:
   - source_manifest は更新しない
```

Phase 12 以降の heavy core path は `.spec-grag/.staging/<graph>/<revision>/`
へ graph / vector / raw chunk / BM25 / retrieval index / sidecar を書き出し、
`artifact_revision.json` を生成してから active graph directory へ commit する。
後段 stage が失敗した場合は staging を破棄し、active artifact は旧 revision の
一貫した状態を維持する。no-change / format-only fast path は従来通り
個別 atomic file write を使う。
`readiness_report.artifact_diagnostics` は active revision、残存 staging
revision、直近の failed revision ledger を返す。provider failure などで
staging を破棄した場合も failed revision には `failed_stage`、
`graph_revision`、`extract_run_id`、`staging_path_exists` を残し、commit
失敗のように staging が残るケースは診断から再現できるようにする。

Conflict 段階 2 の「scanned_at より新しい修正との食い違い」は、source_manifest の `scanned_at` と実ファイルの `mtime` / 再計算 hash を比較して検出する。ただし `mtime` は Git checkout や touch で内容変更なしに更新されるため、再スキャンの補助トリガーにとどめる。真の変更判定は section 単位 SHA-256 の `source_hash` 比較を優先する。

### 4.8 エラー契約の内部設計対応（EXTERNAL_DESIGN.ja.md §9）

経路 1-4 の各 step 1（config 読み込み）直後に以下のエラーチェックを実行する:

| エラー状態 | ResultEnvelope.status | 内部処理 |
|---|---|---|
| `.spec-grag/config.toml` が見つからない | `failed` | CLI が ErrorResult を返し、設定ファイル作成を促すメッセージを出力 |
| `core.purpose_file` が見つからない | `failed` | Purpose なしでは制約探索が成立しないため ErrorResult を返す |
| `core.concept_file` が見つからない | `degraded` | 警告を出力し、初期 Concept 作成候補を提示。Concept なしでも経路 1 / 2 は実行可（ChapterAnchor / graph は構築できる）。経路 3 / 4 は concept_constraints が空になる旨を warnings に含める |
| `sources.include` に一致するファイルがない | `failed` | Source specs なしでは GRAG 構築不可のため ErrorResult を返す |
| GRAG 更新に一部失敗（SchemaLLMPathExtractor / vector_store / cluster snapshot 等） | `degraded` | CoreResult.failed_sources / ResultEnvelope.execution.degraded_components / warnings に記録。成功した section の結果は保持する |
| Concept diff が未承認（経路 3 / 4） | `blocked` | Orchestrator が InjectionContext / Answer 生成を行わず、ConceptApprovalRequiredResult を返して停止 |
| Conflict review が未解決 | `blocked` | `ConflictApprovalRequiredResult` を返して承認フローに入り、確定 Conflict には昇格しない |
| Answer 生成前に context 不足が残る | `blocked` | Answer を生成せず、NeedMoreContextResult または ReviewNotes 相当の blocked result として返す |

### 4.9 spike 失敗時の影響範囲（fallback ladder との対応）

本設計は案 B（Native LlamaIndex GraphRAG Flow）前提で書かれている。Phase 1 verification で不成立が実証された場合、[SUMMARY.md §3.9](SURVEY/SUMMARY.md) の fallback ladder（案 B → 案 C → GRAG 撤回）に従って実装方式を差し替える。各 spike の失敗が本設計のどこを崩すかを以下に明示する。

| spike | 失敗した場合に崩れる箇所 | 影響範囲 | 外部契約を維持する代替 |
|---|---|---|---|
| **spike 05**（CodexCLIAdapter） | §1.3 三層分業の GRAG 層全体、§1.4 統合方式、§2.3 SchemaLLMPathExtractor 構成 | **全経路（1-4）の LLM 抽出が動かない** | 案 C に降りる（CustomPGExtractor + subprocess 直接呼び出し）。案 C も不成立なら GRAG 撤回 |
| **spike 06**（SchemaLLMPathExtractor + 軽量 schema + Section grounding） | §2.1 軽量 schema の LLM 抽出部分、§2.3 スキーマ受理、§2.4 正規化ルール、§3.4 Concept 更新候補生成 | **経路 1/2 の ANCHOR 抽出・章間 relation 抽出が動かない** → 経路 3/4 の retrieval 品質も連鎖的に低下 | 日本語 prompt / schema 調整で対応可能な範囲か判定。SchemaLLMPathExtractor 自体が使えない場合は案 C に降りる |
| **spike 07**（VECTOR_SOURCE_KEY 連結） | §1.9 経路 3 Step 5c（VectorContextRetriever）、§2.6 embedding プロパティ | **経路 3/4 の vector retrieval が 0 件**。graph traversal（PGRetriever + get_rel_map）は影響なし | §4.6 の keyword + property filter fallback で代替。vector retrieval なしでも経路 3/4 は graph traversal ベースで成立可能（retrieval 品質は低下） |
| **spike 08**（章アンカー欠損フォールバック） | §2.5 Agentic search フォールバック | 欠損章の補完品質が低下。経路 3/4 の retrieval 網羅性に影響 | 欠損章を raw read せず ReviewNotes に「章アンカー欠損、人間確認推奨」として落とす |
| **spike 09**（Concept 更新候補生成 P vs Q） | §3.4 候補生成方式 | GRAG ANCHOR 経由の候補検出が使えない | (Q) LLM 直接方式（Agentic search + 現 Core 比較）に寄せる。§3.4 step 1 を LLM 直接に書き換え |
| **spike 10**（4 軸付与 prompt + metadata 後付け） | §3.2 transient annotation、§1.6 4 軸評価 | 4 軸の LLM 分類精度が不十分 | rule-based 分類（keyword match + relation type）+ Human review を併用し、4 軸フィールド自体は必ず出力する。低信頼項目は review_required=true に寄せる |
| **spike 11**（Conflict 二段階 Validator） | §1.5 / §3.3 Conflict 確定パイプライン | conflict=true の自動確定ができない | conflict=true を自動確定せず、semantic_conflict_candidate / review_required のみ出力。全 Conflict を Human approval 経由に |
| **spike 12**（Hierarchical Cluster sidecar） | §3.5 cluster snapshot | cluster snapshot の品質が低い / incremental 再算出が難しい | get_rel_map traversal ベースの deterministic cluster generator に切り替え、cluster_snapshot.json は必ず生成する。低信頼 cluster は confidence=low / stale=true / warnings で明示する |
| **spike 13**（JSON protocol + InjectionContext 構造化出力） | §1.3.1 JSON protocol / §3.1 InjectionContext 構築 / §3.8 ResultEnvelope | 構造化振り分けや Agentic search 往復の実装が複雑 / バグが多い | EXTERNAL_DESIGN.ja.md §8.1 のフィールドは維持する。実装を deterministic mapper + LLM classification の段階に分け、分類不能項目は review_notes に落とす。NeedMoreContextResult / AgenticSearchCandidate の schema は崩さない |

spike 05 は LLM 抽出基盤として影響範囲が広い。spike 13 は全コマンドの JSON 境界として先に固定する。spike 05 が不成立の場合は本設計の §1.3 / §1.4 / §2.3 を案 C 前提に書き直す。spike 08-13 は経路 3/4 の品質に影響するが、外部契約の出力構造は維持したまま、低信頼・未解決結果を ReviewNotes / warnings / ResultEnvelope.status で明示する。

---

## 5. 関連ドキュメント

### リポジトリ内（現行）

- [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md): 外部契約（**source of truth、不変**）
- [doc/SURVEY/SUMMARY.md](SURVEY/SUMMARY.md): Phase 0 / 0.5 完了レポート、案 A 破棄根拠、Native LlamaIndex GraphRAG Flow（旧名 案 B）採用
- [doc/SURVEY/13_path_b_design_options.md](SURVEY/13_path_b_design_options.md): 案 B サブパターン（B-1 / B-2 / B-3）+ ハイブリッド可能性
- [doc/SURVEY/01_*.md](SURVEY/) 〜 [12_*.md](SURVEY/): Phase 0 個別調査結果
- [doc/TODO.md](TODO.md): Phase 1 verification / 初期実装の作業計画
- [CLAUDE.md](../CLAUDE.md): リポジトリレベルの不変ルール（EXTERNAL_DESIGN.ja.md は不変、明示の改訂指示なしに変更しない）

### BAK/（pre-pivot のアーカイブ、参考のみ）

`BAK/` 配下に Rust + graphrag-rs 前提の旧実装。pivot 後は使わない。
