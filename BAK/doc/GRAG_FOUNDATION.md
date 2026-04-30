# GRAG_FOUNDATION — graphrag-rs の機能カタログと spec-grag からの利用方法

本書は [FOUNDATION_PLAN.md](FOUNDATION_PLAN.md) Phase 2 の成果物。Phase 1 の生データ [GRAG_FOUNDATION_RAW.md](GRAG_FOUNDATION_RAW.md) と Phase 2 の追加調査 [foundation_phase2_raw/](foundation_phase2_raw/) を **設計判断に使える形に集約** する。

> **読み方**：
> - 「graphrag-rs にどんな機能があるか」を知りたい → §2（4 分類カタログ）
> - 「spec-grag は graphrag-rs をどう使うか」を知りたい → §3（典型利用シーケンス）
> - 「設計判断はどこで何を決めるか」を知りたい → §4（D1〜D11 ごとの利用方法）
> - 「まだ分からないことは何か」を知りたい → §5（不確定項目）

---

## 0. 序章

### 0.1 Phase 2 の最重要結論

**graphrag-rs は「上位ファサード API（AsyncGraphRAG）が未完成、下位コンポーネントは実装済み」というライブラリである**。Phase 2 の調査で以下が確定：

| 経路 | 状態 |
|---|---|
| `AsyncGraphRAG.add_document → build_graph → answer_question` | ❌ 不可（中核がスタブ／ハードコード） |
| `GraphRAG::builder().with_ollama().build()` | ⚠ examples が API バージョン違い、信頼できない |
| `examples/multi_document_pipeline.rs` | ⚠ graphrag-rs を一切使わない standalone 実装（rayon のみ） |
| **下位コンポーネント直叩き（KnowledgeGraph + LLMEntityExtractor + RetrievalSystem + LeidenCommunityDetector + WorkspaceManager + Lance）** | ✅ **これが現実解** |

→ spec-grag は **AsyncGraphRAG / AsyncGraphRAGBuilder を使わず**、graphrag-rs を「プリミティブの集合」として使う。

### 0.2 三層分業（spec-grag のアーキテクチャ）

EXTERNAL_DESIGN.ja.md §3.5 / §5.3 から逆引き：

```
┌────────────────────────────────────────────────────────┐
│  Agent (Claude / Codex CLI) — slash command 実行層     │
│  - ConversationContext + 課題プロンプト解釈            │
│  - Agentic search（章ファイルを Read tool で読む）     │
│  - 動的キーワード／エンティティ／章候補抽出            │
│  - synonym 展開・意図解釈                              │
│  - InjectionContext を読み 5 分類（制約／修正対象／    │
│    無関係／競合／要レビュー）                          │
│  - Answer 生成（spec-realign）                          │
└──────────────────┬─────────────────────────────────────┘
                   │ Bash 呼び出し（CLI 引数で動的キーワード渡し）
                   ↓
┌────────────────────────────────────────────────────────┐
│  spec-grag CLI（独立バイナリ）                         │
│  - 設定読み込み（.spec-grag/config.toml）              │
│  - GRAG オーケストレーション                           │
│  - 2 系統 pipeline（制約探索 / 修正対象探索）           │
│  - 階層 ranking（Purpose > Concept > Source spec）     │
│  - 永続化（章 index、Lance、WorkspaceManager）          │
│  - InjectionContext を Markdown / JSON で出力          │
└──────────────────┬─────────────────────────────────────┘
                   │ Rust API
                   ↓
┌────────────────────────────────────────────────────────┐
│  graphrag-rs（プリミティブとしてのライブラリ）          │
│  - KnowledgeGraph / LLMEntityExtractor /                │
│    LeidenCommunityDetector / RetrievalSystem /          │
│    HybridRetriever / WorkspaceManager / Lance / etc.    │
└────────────────────────────────────────────────────────┘
```

責務の境界が重要：
- **クエリ生成は Agent (LLM) の責務**（Agentic search で動的抽出）
- **2 系統 pipeline は CLI の責務**（受け取った動的キーワードでオーケストレーション）
- **graphrag-rs は「プリミティブ」のみ**（ファサード API は使わない）

### 0.3 把握度凡例

| 段階 | 意味 |
|---|---|
| ✅ 高 | 実装行レベルまで読了、API シグネチャと挙動を確認済 |
| ✅ 中 | doc コメントと主要関数本体を読了、論点把握済 |
| ⚠ 浅い | doc コメントまたは概要のみ、行レベル未確認 |
| ❌ 表面的 | 名称のみ、実装未確認 |
| ⏳ 未確認 | 調査未着手、§5 で追加調査が必要 |

---

## 1. 設計判断軸 D1〜D11（EXTERNAL_DESIGN.ja.md からの逆引き）

| # | 決めること | graphrag-rs での根拠 | 不足／独自実装が必要な部分 |
|---|---|---|---|
| **D1** | **ChapterAnchor の作り方**（章別「主要エンティティ＋キー概念＋要約」） | `LLMEntityExtractor` で chunk → entities 抽出（chunk が DocumentId 保持）／要約は Agent 側 LLM | entity → 章帰属の集約処理（entity.mentions[].chunk_id → DocumentId）／Concept entity_type のプロンプト誘導 |
| **D2** | **Entity Relationship Graph の作り方**（粒度・抽出器選択） | `LLMEntityExtractor` + `LLMRelationshipExtractor` + `AtomicFactExtractor`（5-tuple + causal_strength） | LLMEntityExtractor の relationship.context = vec![] 問題（chunk_id 記録なし）／日本語化 AtomicFact の entity_type 推論 |
| **D3** | **Hierarchical Cluster の作り方**（章境界整合） | `LeidenCommunityDetector` で flat clustering 実装あり／`prepare_community_context` あり | Leiden の hierarchical_leiden は flat（level 0 only）。3 階層は spec-grag 自前 or vendor 改造 200 行／entity name のみのグラフのため章境界復元が必須 |
| **D4** | **検索 / 探索の API 組み合わせ**（制約／修正対象の 2 系統） | `RetrievalSystem.hybrid_query` ／ `HybridRetriever`（RRF/Weighted/CombSum/MaxScore）／ `LightRAG DualLevel`（4 マージ戦略）／ `HippoRAG PPR`（feature gate）／ `CrossEncoder`（Candle BERT）| analyze_query 内部の英語ハードコード bypass 必要／HippoRAG は fact 抽出 glue が必要／CrossEncoder は日本語モデルへ差し替え必要 |
| **D5** | **分類・矛盾検出メカニズム**（ConflictNotes） | `IncrementalGraphManager::ConflictResolution`（4 戦略）／ `graph/incremental.rs::ConflictResolver`（5 矛盾種別） | 既存実装は「構造的衝突」のみ。spec-grag が要求する「制約 vs 修正対象 / Source spec 同士 / Concept vs Source spec」の **意味的矛盾** は独自実装必須 |
| **D6** | **インクリメント更新の章単位制御** | `ChangeDetector`（SHA-256、document_id 単位、機能） | Lazy Propagation::apply_update プレースホルダ／Async Batching::process_single_operation プレースホルダ／章単位再構築のオーケストレーションは spec-grag 自前 |
| **D7** | **永続化 / ロード粒度** | `WorkspaceManager`（graph.json + entities/relationships/chunks/documents.parquet）／`LanceVectorStore`（embedding 専用）／`save_state_async`（async_knowledge_graph.json + doc 別 tree.json） | 全体一括が標準、章別保存は graphrag-rs に存在せず／VectorIndex (HNSW) は永続化メソッドなし／load_state_async が graphrag-rs に存在しない（HANDOFF §1.7 と矛盾、§5 で要確認）／spec-grag は章 index を別ファイル管理 |
| **D8** | **Concept 更新案 unified diff** | `prepare_community_context` を起点に独自プロンプト | cluster summary → Concept 文書の橋渡しは graphrag-rs に存在せず、spec-grag 独自実装必須／既存 `generate_community_summary` は LLM 呼び出しなし（決定論的サマリー） |
| **D9** | **LLM プロバイダー注入方式** | `AsyncLanguageModel` trait あり（GenerationParams は max_tokens/temperature/top_p/stop_sequences のみ）／ `OllamaLanguageModelAdapter` で Ollama を AsyncLanguageModel 化（num_ctx/keep_alive はハードコード None）／`ClaudeCliLanguageModel`（spec-grag 独自実装、HANDOFF.md §1.2） | 抽出器（LLMEntityExtractor / Gleaning / AtomicFact / LLMRelationship）が **OllamaClient 具象型を要求**、AsyncLanguageModel 化は vendor 改造 ~140 行（num_ctx 動的計算と keep_alive を犠牲） |
| **D10** | **設定ファイル統合** | `Config`（mod.rs 2434 行、9 サブセクション）／`figment` で 4 層 merge（feature `hierarchical-config`）／ templates 5 種 | spec-grag の `[sources][core][graph][llm]` 4 セクションは Config と直接マップ不可。SpecGragConfig → Config 変換層が必須 |
| **D11** | **ConversationContext → 検索クエリ変換** | （存在せず） | spec-grag 独自実装、ただし **クエリ生成は Agent (LLM) の責務**。CLI は受け取った動的キーワード（`--high` `--low`）で 2 系統検索を実行するのみ |

---

## 2. graphrag-rs 機能カタログ（4 分類）

各機能の **使い方**・**実装ファイル**・**spec-grag からの想定経路** を集約。詳細は [foundation_phase2_raw/](foundation_phase2_raw/) を参照。

### 2.1 そのまま使える（A 分類）

| 機能 | 把握度 | 実装ファイル | spec-grag からの想定利用 |
|---|---|---|---|
| **HybridRetriever** | ✅ 高 | `retrieval/hybrid.rs` 545 行 | 制約探索 / 修正対象探索の **基本検索層**。RRF / Weighted / CombSum / MaxScore の 4 fusion。`initialize_with_graph(&kg)` でセットアップ後 `search(query, top_k)` を呼ぶ |
| **BM25Retriever** | ✅ 中 | `retrieval/bm25.rs` 371 行 | HybridRetriever 内部で使用。直接呼び出しは不要 |
| **EnrichedRetriever** | ✅ 中 | `retrieval/enriched.rs` 530 行 | `boost_with_metadata`（章 metadata でブースト）と `filter_by_structure`（章フィルタ）。RetrievalSystem の hybrid_query_with_trees 末尾で適用される |
| **CrossEncoder（Candle BERT）** | ✅ 中 | `reranking/cross_encoder.rs` 473 行 | 後段精度向上。**日本語向けモデル（`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` 等）への差し替え必要**。`CrossEncoderConfig.model_name` で変更可 |
| **LightRAG DualLevelRetriever** | ✅ 中 | `lightrag/dual_retrieval.rs` 357 行 | high_level（Concept / 章サマリ）と low_level（具体エンティティ）の 2 階層検索。4 マージ戦略（Interleave/HighFirst/LowFirst/Weighted）。**high-level index を spec-grag 側で別途構築する必要** |
| **HippoRAG PPR** | ✅ 中 | `retrieval/hipporag_ppr.rs` 441 行（`feature="pagerank"`） | fact ベース検索。**`Fact` リスト・`entity_to_passages` map・`passage_scores` map を spec-grag 側で組み立てる glue が必要**。RetrievalSystem からは自動で呼ばれない |
| **ChangeDetector（SHA-256）** | ✅ 中 | `incremental/mod.rs:430-438, 841-860` | 章単位変更検出。`DocumentContent::id = chapter_path` にすれば章単位 SHA-256 ハッシュで動く |
| **Delta Computation** | ✅ 中 | `incremental/delta_computation.rs` 700+ 行 | 2 つの GraphSnapshot 比較。Bloom filter + rayon 並列。プレースホルダではなく実装済み |
| **Dynamic Edge Weighting** | ✅ 中 | `core/mod.rs:989-1051` ／ `retrieval/pagerank_retrieval.rs:411-548` | `KnowledgeGraph::dynamic_weight(rel, query_emb, query_concepts)` で base_weight × (1 + semantic + temporal + concept + causal)。**言語非依存**、relation_type 文字列マッチの concept_boost のみ日本語化注意 |
| **WorkspaceManager** | ✅ 中 | `persistence/workspace.rs` 369 行 | `save_graph(&kg, "main")` / `load_graph("main")` で graph.json + 4 parquet ファイル + metadata.toml |
| **ParquetPersistence** | ✅ 中 | `persistence/parquet.rs` 1100+ 行 | feature `persistent-storage` 時に entities/relationships/chunks/documents の 4 ファイル分割保存。Snappy 圧縮、row_group_size=10000 |
| **LanceVectorStore** | ✅ 中 | `persistence/lance.rs` 530+ 行 | embedding の永続化（HNSW / IVF / Flat）。**HNSW VectorIndex は永続化メソッドなしのため、Lance 必須** |
| **KnowledgeGraph** | ⚠ 浅い（API 全体は §5.3 で要追加 Read） | `core/mod.rs` | entity / relationship 集約の中心型。`add_entity` / `add_relationship` / `get_neighbors` / `to_leiden_graph` 等 |
| **LeidenCommunityDetector** | ✅ 高 | `graph/leiden.rs` 842 行 | community 検出（**flat、level 0 only**）。`detect_communities(graph)` → `HierarchicalCommunities`。spec-grag は **これに自前 hierarchical を被せる** |
| **HierarchicalCommunities::prepare_community_context** | ✅ 中 | `graph/leiden.rs:254-306` | community 内 entity + relationship を context 文字列化。spec-grag が独自プロンプトで包んで LLM 要約に渡す起点 |
| **OllamaEmbedderAdapter** | ✅ 中 | `core/ollama_adapters.rs:14-70` | `AsyncEmbedder` trait 実装。`new(model, dimension)` で作成、`embed(text)` / `embed_batch(texts)` |
| **AsyncLanguageModel trait** | ✅ 高 | `core/traits.rs:541-624` | LLM プロバイダーの抽象。`complete(prompt)` / `complete_with_params(prompt, GenerationParams)` ／ `BoxedAsyncLanguageModel` 型消去版あり |
| **ClaudeCliLanguageModel** | ✅ 確認済 | `vendor/graphrag-rs/graphrag-core/src/generation/claude_cli.rs`（spec-grag 拡張） | `AsyncLanguageModel` 実装。`claude -p` subprocess 呼び出し（HANDOFF.md §1.2）。spec-grag が直接保持して使う |
| **TextChunker** | ⚠ 浅い | `text/` | 章本文 → TextChunk 群（chunk が DocumentId を保持）。chunk_size / chunk_overlap で制御 |
| **Symbolic Anchoring（構造のみ）** | ✅ 中 | `retrieval/symbolic_anchoring.rs` 600 行 | `SymbolicAnchor` struct と `boost_with_anchors` は再利用可能。**concept extraction は英語ハードコードのため日本語化必須** |
| **CausalAnalysis（temporal_range / causal_strength）** | ⚠ 浅い | `graph/temporal.rs`（要追加 Read） | AtomicFact の causal_strength / temporal_range を計算する基盤 |

### 2.2 改造が必要（B 分類、条件付き）

| 機能 | 改造規模 | 条件 | 詳細 |
|---|---|---|---|
| **LLMEntityExtractor / GleaningEntityExtractor / AtomicFactExtractor / LLMRelationshipExtractor の AsyncLanguageModel 化** | ~140 行 | **抽出に Ollama 以外（Claude CLI / Codex CLI）を使う場合のみ**。Ollama に固定するなら不要 | `OllamaClient` 具象フィールド → `Arc<dyn AsyncLanguageModel<Error=GraphRAGError>>` 置換。num_ctx 動的計算と keep_alive 制御を犠牲（OllamaLanguageModelAdapter::complete_with_params が両者 None ハードコード）|
| **3 階層 Hierarchical Leiden** | ~200 行（vendor 改造の場合） | spec-grag 自前で擬似階層化する選択肢あり | `LeidenCommunityDetector::hierarchical_leiden` の `let level = 0;` 固定（leiden.rs:511）を contraction + 再 Leiden で本物の hierarchical に拡張 |
| **AtomicFact の日本語化** | ~30 行 | spec-grag が AtomicFact を採用する場合 | `infer_entity_type` ヒューリスティック（"APIレイヤー" → PERSON 誤判定）／ causal キーワード（"caused"/"led to"/"enabled"/"allowed"）／ extract_timestamp（西暦専用） |
| **LLMRelationshipExtractor の chunk_id 保持** | ~5 行 | 章境界保持を完全にしたい場合 | relationship.context = vec![] を chunk.id を入れるよう修正（line 451）|

### 2.3 独自実装が必要（C 分類、14 件）

spec-grag が graphrag-rs にない機能を自前で実装する必要がある領域。

| # | 項目 | 担当層 | 主要根拠 |
|---|---|---|---|
| 1 | **意味的 Conflict 検出**（ConflictNotes 3 種：制約 vs 修正対象 / Source spec 同士 / Concept vs Source spec） | CLI 内部（推論ロジック）+ Agent（LLM 判断） | EXTERNAL_DESIGN §5.4。graphrag-rs の Conflict は構造的衝突のみ |
| 2 | **3 階層 Hierarchical Cluster**（Leiden flat の上に擬似階層化） | CLI 内部 | Leiden は flat、parent_cluster 未配線。spec-grag 自前 or vendor 200 行改造 |
| 3 | **章境界の伝播・復元**（entity.mentions[].chunk_id → DocumentId 集約） | CLI 内部 | `to_leiden_graph` が entity name のみ、章境界完全消失 |
| 4 | **`hierarchical_query_grouped` 相当**（章単位グルーピング検索） | CLI 内部（~15 行） | spike vendor のみ存在、通常 vendor に無い |
| 5 | **章別 ChapterAnchor / ERG / Hierarchical Cluster の更新オーケストレーション** | CLI 内部 | graphrag-rs の incremental は ChapterAnchor 概念を持たない |
| 6 | **Concept 更新案 unified diff 生成**（cluster summary → Concept 文書） | CLI 内部 + LLM (Claude/Codex CLI) | graphrag-rs に橋渡しなし、`similar` クレートで diff 生成 |
| 7 | **ConversationContext → 検索クエリ変換**（動的キーワード抽出） | **Agent (LLM)** が動的生成、CLI は受け取るのみ | EXTERNAL_DESIGN §5.3 Agentic search |
| 8 | **日本語化 Symbolic Anchoring**（concept extraction） | CLI 内部 | `is_likely_concept` 英語ハードコード代替 |
| 9 | **日本語化 AtomicFact**（entity_type 推論 / causal キーワード / extract_timestamp） | CLI 内部（vendor 改造でも可） | "APIレイヤー" → PERSON 誤判定問題 |
| 10 | **日本語向け QueryAnalyzer**（`hybrid_query` 内部の英語 QueryType 判定 bypass） | CLI 内部 | `query/intelligence.rs` / `query/adaptive_routing.rs` 英語ハードコード代替 |
| 11 | **章別永続化**（`chapter_index.json` / `concept_index.json`、章 ID → entity_ids / concept_name → source spec ids） | CLI 内部 | graphrag-rs は全体一括のみ |
| 12 | **AsyncGraphRAGBuilder への embedder 注入 thin wrapper**（または vendor 改造） | CLI 内部 | `AsyncGraphRAGBuilder.embedder()` setter なし |
| 13 | **2 系統 pipeline オーケストレーション**（制約探索 / 修正対象探索の orchestration） | CLI 内部 | EXTERNAL_DESIGN §5.3 / §6.3 |
| 14 | **Purpose > Concept > Source specs 階層 ranking** + diversity + recency | CLI 内部 | EXTERNAL_DESIGN §5.4 / §5.5 |

### 2.4 致命的に使えない（D 分類、依存禁止）

graphrag-rs に「仕様としては存在するが実装が未完成」な機能。spec-grag は **これらに依存しない設計** を取る。

| 機能 | 状態 | 詳細 |
|---|---|---|
| **AsyncGraphRAG** | ❌ 不可 | `extract_entities_async` は Tom Sawyer ハードコード（async_graphrag.rs:222-245）／ `async_retrieval` は naive スタブ（最初 3 chunks の `contains(query)`）／ `answer_question` の prompt template が英語固定／ `query()` は `sleep(10ms)` してダミー文字列返却 |
| **AsyncGraphRAG::with_async_claude_cli()** | ❌ 経由不要 | 当初は AsyncGraphRAG 内部でクラスタ要約と Q&A 生成に使う想定だったが、AsyncGraphRAG 自体が使えないので呼ぶ意味なし。`ClaudeCliLanguageModel` 自体は spec-grag が直接保持して使う |
| **Lazy Propagation::apply_update** | ❌ プレースホルダ | `lazy_propagation.rs:470-477` メソッド本体が空。`enable_lazy_propagation: false` 必須 |
| **Async Batching::process_single_operation** | ❌ プレースホルダ | `async_batch.rs:536-564` 全 OperationType が `Ok(())` 返却。spec-grag は rayon 直接 or 自前 async loop |
| **AdaptiveRetriever** | ❌ 呼び出し先がスタブ | `adaptive.rs` は `vector_search` / `graph_search` / `bm25_search` / `public_hierarchical_search` を呼ぶが、これらが全部ハードコード文字列返却（mod.rs:1751-1801） |
| **DocumentTree::query** | ❌ フラット線形スキャン | `summarization/mod.rs:914-939` 全ノードを線形 scan、parent/child を辿らない |
| **query/* の 5 ファイル** | ❌ 1 行スタブ | `advanced_pipeline.rs` / `analysis.rs` / `expansion.rs` / `multi_query.rs` / `ranking_policies.rs` すべて空 |
| **query/intelligence.rs** | ❌ 英語ハードコード | QueryType 判定が `query.contains("who is")` 等。日本語不可 |
| **query/adaptive_routing.rs** | ❌ 英語ハードコード | 複雑度判定が `query.matches(" and ")` 等。日本語不可 |
| **examples/multi_document_pipeline.rs** | ❌ graphrag-rs 非依存の standalone 実装 | rayon のみ依存。spec-grag のリファレンスにすべきでない |
| **examples/04_with_ollama.rs / 05_batch_processing.rs** | ⚠ API バージョン違い | `with_text_config` / `with_parallel_processing` / `auto_detect_llm` / `add_document_from_text` が builder/mod.rs に存在せず |
| **GraphRAG::ask_explained の query_analysis** | ⚠ 常に None | `from_results` 内部で固定 None。`ExplainedAnswer` を spec-grag 用に再構築すべき |

---

## 3. 典型利用シーケンス（spec-grag 視点）

EXTERNAL_DESIGN.ja.md §4 / §5 / §6 の 3 コマンドそれぞれの利用シーケンスを、graphrag-rs の API 呼び出しレベルで示す。

### 3.1 `/spec-core [--all|-a]` 経路（章ファイル → 6 要素生成）

EXTERNAL_DESIGN §4.3。GRAG インクリメント or 全再構築 + Concept 更新案。

```
入力: .spec-grag/config.toml
        - sources.include = ["docs/spec/**/*.md"]
        - core.purpose_file / core.concept_file
        - graph.storage = ".spec-grag/graph/"
        - llm.provider, llm.claude_cli/codex_cli

【Phase A: 章ファイル変更検出】
1. spec-grag が config.toml.sources.include を glob 展開 → 章ファイル群
2. 各章ファイルを DocumentContent { id: chapter_path, text, metadata }
   に変換
3. ChangeDetector::has_content_changed(&content) で SHA-256 比較
   - --all 指定なら全章を更新対象に
   - incremental なら変更ありの章のみ

【Phase B: 章ファイル → entity / relationship 抽出】
4. 各変更章について:
   a. TextChunker::chunk_document(text) → Vec<TextChunk>
      （chunk が DocumentId を保持）
   b. LLMEntityExtractor::extract_from_chunk(chunk).await
      → (Vec<Entity>, Vec<Relationship>)
      ※ OllamaClient 直結（要約は Ollama 一択）
      ※ Claude CLI で抽出するなら vendor 改造 ~140 行が必要
   c. （オプション）AtomicFactExtractor::extract_atomic_facts(chunk)
      → Vec<AtomicFact>
      ※ 日本語化改造 ~30 行が必要
   d. KnowledgeGraph::add_entity / add_relationship に流し込み

【Phase C: 章境界の復元】
5. spec-grag 自前で entity.mentions[].chunk_id → DocumentId の集約マップを作る
   chapter_index: HashMap<DocumentId, Vec<EntityId>>

【Phase D: ChapterAnchor 生成】
6. 各章について:
   a. chapter_index[doc_id] でその章に属する entities を取得
   b. mentions.len() / PageRank で「主要エンティティ」抽出
   c. entity_type == "CONCEPT" のものを「キー概念」として抽出
   d. 章本文 + 主要エンティティ + キー概念を ClaudeCliLanguageModel.complete()
      に渡して章要約生成 → ChapterAnchor

【Phase E: Embedding 計算】
7. OllamaEmbedderAdapter::embed_batch(entity_descriptions)
   → entity / chunk の embedding
   spec-grag 側で thin wrapper を作って batch 並列化

【Phase F: Hierarchical Cluster 生成】
8. KnowledgeGraph::to_leiden_graph()
   → petgraph::Graph<String, f32, Undirected>
   ※ 章境界は entity name のみのグラフに集約され消失
9. LeidenCommunityDetector::detect_communities(graph)
   → HierarchicalCommunities（flat、level 0 only）
10. spec-grag 自前で 3 階層擬似階層化:
    - level 0: Leiden 出力をそのまま
    - level 1: level 0 cluster を resolution=0.5 で再 Leiden
    - level 2: level 1 cluster を resolution=0.2 で再 Leiden
11. HierarchicalCommunities::prepare_community_context(cluster)
    → context 文字列
12. spec-grag 独自プロンプト + ClaudeCliLanguageModel.complete()
    → cluster summary
13. cluster と章の m:n 対応を chapter_index 経由で復元

【Phase G: 永続化】
14. KnowledgeGraph::save_to_json or ParquetPersistence::save_graph
    → .spec-grag/graph/workspace/main/{graph.json or *.parquet}
15. LanceVectorStore::store_embedding for entity in entities
    → .spec-grag/graph/vectors.lance/
16. spec-grag 独自 chapter_index.json / concept_index.json を別保存

【Phase H: Concept 更新案生成】
17. cluster summary → 既存 concept.md と比較 → unified diff 生成
    ※ similar クレートで context_radius 10
18. diff があれば CoreResult.concept_diff に詰める

出力: CoreResult { mode, updated_sources[], skipped_sources[], failed_sources[],
                   graph_storage, freshness_report, concept_diff?, warnings[] }
```

### 3.2 `/spec-inject [<課題プロンプト>]` 経路（InjectionContext 注入）

EXTERNAL_DESIGN §5.3。先に core incremental を実行 → InjectionContext 生成。

```
入力: ConversationContext (Agent から渡る)
       + <課題プロンプト>（任意）
       + .spec-grag/config.toml

【Phase A: GRAG Freshness】
1. /spec-core 相当の incremental（§3.1 Phase A〜G）を内部実行
   → CoreResult を取得
2. concept_diff があれば停止 → Agent に accept/reject/修正指示を要求
3. 承認済み Concept を確定

【Phase B: Agentic search（Agent 側、CLI 外）】
※ 以下は Agent (Claude / Codex) が slash command プロンプトで実行
   spec-grag CLI は呼ばれない
4. Agent が Purpose / Concept を Read tool で取得
5. Agent が課題プロンプト + ConversationContext を解釈
6. Agent が config.toml.sources.include の章ファイル群を Glob
7. Agent が関連しそうな章ファイルを Read tool で読む
8. Agent が動的に抽出:
   - high_level keywords: 上位概念（Purpose / Concept 由来の制約候補）
   - low_level keywords: 具体エンティティ（修正対象候補）
   - 関連章候補

【Phase C: 制約探索（CLI 内部）】
9. Agent が呼ぶ: spec-grag inject "<prompt>" --high "k1,k2,..." --low "e1,e2,..."
10. CLI が制約探索を実行:
    a. RetrievalSystem.hybrid_query(constraint_query)
       ※ 内部の analyze_query は英語ハードコードのため bypass する
       薄いラッパを spec-grag 側に置く（独自実装 #10）
    b. EnrichedRetriever.filter_by_structure（章フィルタ）で章別に絞り込み
    c. ChapterAnchor を chapter_index.json から取得
    d. Purpose / Concept から守るべき制約を抽出
       （Agent が事前に Read 済みの Purpose を CLI に渡す or
        CLI が purpose_file を直接読む）
11. CLI が修正対象探索を実行:
    a. RetrievalSystem.hybrid_query(target_query)
       または LightRAG DualLevelRetriever.retrieve（high/low keyword 渡し）
       ※ high-level index = community summary 群、
         low-level index = chunks の 2 つを準備
    b. KnowledgeGraph.get_neighbors(entity) で隣接エンティティ拡張
    c. Hierarchical Cluster traversal:
       - get_ancestors / get_descendants で depth-aware 探索
       - DocumentTree.query は使わない（フラットスキャン）
    d. 関連 ChapterAnchor / 章・節・エンティティを取得

【Phase D: 階層 ranking（CLI 内部、独自実装 #14）】
12. ConstraintContext の rerank:
    1) Purpose 由来 (最高優先)
    2) Concept 由来 (人間承認済み)
    3) Source spec 由来
    4) ChapterAnchor 由来
13. TargetContext の rerank:
    1) HybridRetriever.score
    2) Cross-Encoder rerank（日本語モデル）
    3) diversity penalty
    4) recency（sources_scanned_through 比較）

【Phase E: InjectionContext 出力】
14. spec-grag CLI が InjectionContext を Markdown / JSON で出力:
    - conversation_context_summary
    - constraint_context.{purpose, concept, source_spec, chapter_anchor}_constraints
    - target_context.{candidate_targets, related_concepts, related_source_sections,
                      related_chapter_anchors, related_entities}
    - excluded_as_irrelevant
    - conflict_notes ← 独自実装 #1（意味的矛盾検出）
    - review_notes
    - freshness_report
    - approved_concept_update?
    - warnings

【Phase F: 分類（Agent 側）】
15. Agent が InjectionContext を読み:
    - ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes /
      ReviewNotes に応じて KV へ取り込み
    - 章本文と Concept は丸ごと注入しない（§3.5 制限）

出力: 構造化された InjectionContext（CLI が出力）
       + Agent の KV 状態（slash command の効果）
```

### 3.3 `/spec-realign <課題プロンプト>` 経路（Answer 生成まで）

EXTERNAL_DESIGN §6.3 / §6.5。`/spec-inject` の発展形、Answer まで生成。

```
入力: <課題プロンプト> + ConversationContext + .spec-grag/config.toml

1. /spec-inject 相当（§3.2 Phase A〜E）を実行
   → InjectionContext 取得

2. Agent (Claude / Codex) が Answer 生成（§6.5 Answer 生成契約）:
   - InjectionContext.ConstraintContext を制約として扱う
   - InjectionContext.TargetContext を修正候補として扱う
   - InjectionContext.ExclusionNotes は採用しない
   - InjectionContext.ConflictNotes は Answer 内で明示
   - InjectionContext.ReviewNotes は Answer 内で明示
   - 制約と矛盾する案を出す場合は Answer 内で明示

3. RealignResult { task_prompt, injection_context, answer } を出力

出力: RealignResult
```

### 3.4 三層分業の責任マトリクス

| ステップ | Agent (LLM) | spec-grag CLI | graphrag-rs |
|---|---|---|---|
| ConversationContext 解釈 | ✓ | | |
| 課題プロンプト → 動的キーワード抽出 | ✓（Agentic search）| | |
| synonym 展開 / 意図解釈 | ✓ | | |
| GRAG 検索実行 | | ✓（CLI 内部） | ✓（RetrievalSystem.hybrid_query） |
| 章単位変更検出 | | ✓ | ✓（ChangeDetector）|
| entity 抽出 | | ✓（呼び出し） | ✓（LLMEntityExtractor）|
| 階層 cluster 生成 | | ✓（疑似階層化） | ✓（LeidenCommunityDetector flat）|
| 章境界復元 | | ✓（独自実装 #3）| |
| 2 系統 pipeline orchestration | | ✓（独自実装 #13） | |
| 階層 ranking | | ✓（独自実装 #14） | |
| 意味的 ConflictNotes 検出 | ✓（LLM 判断） | ✓（推論ロジック） | |
| 永続化 | | ✓ | ✓（WorkspaceManager / Lance）|
| InjectionContext 構造化出力 | | ✓ | |
| 5 分類（制約 / 修正対象 / 無関係 / 競合 / 要レビュー） | ✓ | | |
| Answer 生成（spec-realign）| ✓ | | |

---

## 4. 設計判断軸ごとの利用方法

### D1. ChapterAnchor の作り方

**EXTERNAL_DESIGN §1**：章別「主要エンティティ＋キー概念＋要約」。GRAG 更新時に生成・更新。

**graphrag-rs の素材**：
- `LLMEntityExtractor` で chunk → entities 抽出（chunk は DocumentId を保持）
- entity.mentions[].chunk_id で entity と chunk の対応
- 「キー概念」は entity_type = "CONCEPT" としてプロンプトで誘導
- 「主要エンティティ」は mentions.len() による頻度ベース or PageRank
- 「要約」は graphrag-rs にはなし → spec-grag が ClaudeCliLanguageModel で生成

**spec-grag の利用パターン**：

```rust
// Phase B〜D の擬似コード
for chapter_doc in changed_chapters {
    let chunks = TextChunker::chunk_document(&chapter_doc);
    for chunk in chunks {
        let (entities, rels) = llm_extractor
            .extract_from_chunk(&chunk).await?;
        kg.add_entities(entities);
        kg.add_relationships(rels);
    }
}

// 章境界復元（独自実装 #3）
let chapter_index: HashMap<DocumentId, Vec<EntityId>> =
    build_chapter_index(&kg);

for (doc_id, entity_ids) in chapter_index {
    let chapter_entities: Vec<&Entity> = entity_ids
        .iter().filter_map(|id| kg.get_entity(id)).collect();

    // 主要エンティティ（mentions.len() top N）
    let key_entities: Vec<&Entity> = chapter_entities.iter()
        .sorted_by_key(|e| -(e.mentions.len() as i64))
        .take(N).copied().collect();

    // キー概念（entity_type == "CONCEPT"）
    let key_concepts: Vec<&Entity> = chapter_entities.iter()
        .filter(|e| e.entity_type == "CONCEPT").copied().collect();

    // 章要約（独自実装、spec-grag が ClaudeCliLanguageModel を直接保持）
    let summary = claude_cli.complete(&build_summary_prompt(
        &chapter_doc, &key_entities, &key_concepts
    )).await?;

    let anchor = ChapterAnchor { doc_id, key_entities, key_concepts, summary };
    chapter_anchors.insert(doc_id, anchor);
}
```

**確認できなかった点**：
- entity_type のプロンプト誘導（"CONCEPT" を入れた場合の抽出品質）→ Phase 3 で要検証
- prompts.rs の PromptBuilder のカスタマイズ可否 → Phase 3 で要 Read

### D2. Entity Relationship Graph の作り方

**EXTERNAL_DESIGN §1**：仕様要素間の関係グラフ。

**graphrag-rs の素材**：
- `LLMEntityExtractor` 単独：entity 中心、relationship.context = vec![]（chunk_id 記録なし）
- `LLMRelationshipExtractor`：entity + relationship 同時抽出（Microsoft GraphRAG 流）
- `AtomicFactExtractor`：5-tuple（subject/predicate/object/temporal_marker/confidence）+ causal_strength

**spec-grag の選択**：粒度・章境界保持・causal の必要性で 3 候補から選ぶ。

| 候補 | 粒度 | 章境界 | causal | 日本語化 |
|---|---|---|---|---|
| LLMEntityExtractor のみ | 粗い | mentions[].chunk_id 経由 | なし | OK |
| + LLMRelationshipExtractor | 中 | relationship.context = vec![]（vendor 改造 5 行で chunk_id 入れる） | なし | OK |
| + AtomicFactExtractor | 細 | relationship.context に chunk_id 入る | あり（英語キーワード）| 改造 ~30 行 |

**推奨**：LLMEntityExtractor + AtomicFactExtractor の併用（lib.rs:745-829 の `entities.use_atomic_facts == true` ルートと同じ）。spec-grag が AtomicFact を採用するなら日本語化改造（独自実装 #9）を行う。

### D3. Hierarchical Cluster の作り方

**EXTERNAL_DESIGN §1**：章・概念・関係の階層クラスタ。

**graphrag-rs の素材**：
- `LeidenCommunityDetector`（flat、level 0 only）
- `HierarchyBuilder`（resolutions = [1.0, 0.5, 0.2] で擬似階層、ただし parent_cluster 未配線）
- `DocumentTree`（chunk merge_size 束ね、entity 不在）

**spec-grag の選択**：

```
案 A: vendor 改造（~200 行）で hierarchical_leiden を本物の hierarchical に
案 B: spec-grag 自前で擬似階層化（推奨）
  - level 0: Leiden 出力をそのまま使う
  - level 1: level 0 cluster を resolution=0.5 で再 Leiden
  - level 2: level 1 cluster を resolution=0.2 で再 Leiden
  - 各 cluster の章帰属は chapter_index 経由で復元
```

**LLM cluster summary**：
- `HierarchicalCommunities::generate_community_summary` は LLM 呼び出しなし（決定論的）
- spec-grag は `prepare_community_context` を起点に独自プロンプト + ClaudeCliLanguageModel.complete() で要約生成

### D4. 検索 / 探索の API 組み合わせ

**EXTERNAL_DESIGN §6.3**：制約探索 / 修正対象探索の 2 系統。

**graphrag-rs の素材（採用候補）**：
- **HybridRetriever**（vector + BM25 RRF）：基本検索層
- **LightRAG DualLevelRetriever**（high_level / low_level の 2 階層）：spec-grag の高粒度検索に綺麗にマッチ
- **HippoRAG PPR**（fact ベース）：Concept / Source spec を fact 化できれば強い
- **CrossEncoder rerank**（日本語モデル差し替え）：精度向上の最終段
- **EnrichedRetriever**（章フィルタ）：制約探索で章絞り込み

**spec-grag の利用パターン**：

```rust
// 制約探索（独自実装 #13、CLI 内部）
let constraint_query = build_constraint_query(
    &purpose, &concept, &agent_high_keywords);
let constraint_results = hybrid_retriever
    .search(&constraint_query, top_k * 4).await?;
let constraint_filtered = enriched_retriever
    .filter_by_structure(constraint_results, &chapter_filter);
let constraint_reranked = cross_encoder
    .rerank(&constraint_query, constraint_filtered).await?;
let constraint_ranked = apply_purpose_concept_priority(
    constraint_reranked); // 独自実装 #14

// 修正対象探索（独自実装 #13、CLI 内部）
let dual_results = dual_level_retriever
    .retrieve(
        &agent_low_keywords,    // low_level: 具体エンティティ
        &agent_high_keywords,   // high_level: 上位概念
        MergeStrategy::Weighted,
        top_k
    ).await?;
let target_expanded = expand_with_neighbors(
    &kg, dual_results.merged_chunks);
let target_clusters = hierarchical_cluster_traversal(
    &kg, &target_expanded); // 独自実装 #2 / #3
```

### D5. 分類・矛盾検出メカニズム

**EXTERNAL_DESIGN §5.4**：ConflictNotes（制約 vs 修正対象 / Source spec 同士 / Concept vs Source spec）。

**graphrag-rs の素材**：
- `ConflictResolver`（5 矛盾種別：EntityExists / RelationshipExists / VersionMismatch / DataInconsistency / ConstraintViolation）
- `validate_consistency`（orphan / broken refs のみ）
- → **すべて構造的衝突。意味的矛盾は検出しない**

**spec-grag の独自実装（#1）**：

```rust
// 意味的矛盾検出（CLI 内部 + Agent (LLM) 判断）
struct ConflictNote {
    conflict_type: ConflictType,
    // EXTERNAL_DESIGN §5.4 の 3 種:
    //   ConstraintVsTarget,      // 制約 vs 修正対象
    //   SourceSpecVsSourceSpec,  // Source specs 同士
    //   ConceptVsSourceSpec,     // Concept vs Source spec
    parties: Vec<EvidenceRef>,
    explanation: String,
    severity: Severity, // Block / Review / Info
}

// 検出パイプライン（推奨）:
// 1. ConstraintContext と TargetContext の overlap を取る
// 2. それぞれの根拠 snippet を ClaudeCliLanguageModel に渡し、
//    「これらの記述は両立するか？」を判定（LLM 推論）
// 3. 両立しないとされたら ConflictNote を発火
// 4. graphrag-rs の Conflict struct 構造を借用（再利用）
```

### D6. インクリメント更新の章単位制御

**EXTERNAL_DESIGN §3.2**：GRAG Freshness。/spec-inject / /spec-realign 前に core incremental。

**graphrag-rs の素材**：
- `ChangeDetector`（SHA-256、document_id 単位、機能する）✅
- `IncrementalConfig`（auto_detect_changes / parallel_updates / max_batch_size 等）
- `Lazy Propagation::apply_update` ❌ プレースホルダ
- `Async Batching::process_single_operation` ❌ プレースホルダ
- `Delta Computation`（Bloom filter、機能する）✅

**spec-grag の設定**：

```rust
let inc_config = IncrementalConfig {
    auto_detect_changes: true,            // ChangeDetector 有効
    parallel_updates: false,              // Async Batching プレースホルダのため OFF
    enable_lazy_propagation: false,       // Lazy Propagation プレースホルダのため OFF
    enable_delta_computation: true,       // 機能するので有効
    delta_use_bloom_filter: true,
    conflict_resolution: ConflictResolution::Manual,
    ..Default::default()
};
```

**章単位再構築のオーケストレーション（独自実装 #5）**：

```rust
// spec-grag 自前
let changed_chapters = change_detector.detect_changes(&chapters);
for chapter in changed_chapters {
    rebuild_chapter_anchor(&mut kg, chapter);
    rebuild_erg_for_chapter(&mut kg, chapter);
    rebuild_clusters_affecting_chapter(&mut kg, chapter); // 影響範囲のみ
}
save_state(&kg);
```

### D7. 永続化 / ロード粒度

**EXTERNAL_DESIGN §7.1**：`graph.storage = ".spec-grag/graph/"`。

**graphrag-rs の素材**：
- WorkspaceManager（graph.json / *.parquet / metadata.toml）：全体一括
- LanceVectorStore：embedding 専用
- save_state_async：async 用、対称の load_state_async は **graphrag-rs に存在しない**（HANDOFF.md §1.7 の主張と矛盾、§5 で要確認）

**spec-grag のファイル構成**：

```
.spec-grag/graph/
├── workspace/main/
│   ├── graph.json          # KnowledgeGraph 全体（embedding 抜き）
│   ├── entities.parquet    # feature persistent-storage 時
│   ├── relationships.parquet
│   ├── chunks.parquet
│   ├── documents.parquet
│   └── metadata.toml
├── vectors.lance/          # entity / chunk embedding（HNSW）
├── chapter_index.json      # 独自実装 #11: chapter_id → entity_ids
├── concept_index.json      # 独自実装 #11: concept_name → source spec ids
└── chapter_anchors.json    # 独自実装: ChapterAnchor 集約
```

### D8. Concept 更新案の生成パイプライン

**EXTERNAL_DESIGN §4.4 / §7.3**：cluster summary → Concept 文書 → unified diff。

**graphrag-rs の素材**：
- `prepare_community_context`：cluster の context 生成（起点として使える）
- `similar` クレート：unified diff 生成

**spec-grag の独自実装（#6）**：

```rust
// Phase H: Concept 更新案生成
let cluster_summaries: Vec<String> = top_level_clusters.iter()
    .map(|c| {
        let context = c.prepare_community_context(&kg, max_length);
        claude_cli.complete(&build_concept_prompt(&context)).await
    }).collect().await;

let proposed_concept = aggregate_cluster_summaries_to_concept(
    &cluster_summaries, &existing_concept);

// 既存 Concept との diff
let diff = similar::TextDiff::from_lines(
    &existing_concept, &proposed_concept);
let unified = diff.unified_diff()
    .context_radius(10)
    .header(&concept_path, &concept_path)
    .to_string();

if !diff.ratio_lines().is_empty() {
    core_result.concept_diff = Some(unified);
}
```

### D9. LLM プロバイダー注入方式

**spec-grag の方針**：
- **要約 / 生成 LLM** = Claude CLI / Codex CLI（spec-grag が ClaudeCliLanguageModel を直接保持）
- **埋め込み** = Ollama nomic-embed-text（OllamaEmbedderAdapter）
- **抽出** = Ollama 一択（OllamaClient 直結のため）or vendor 改造 ~140 行で AsyncLanguageModel 化

**ClaudeCliLanguageModel の使い方**：

```rust
// HANDOFF.md §1.2 で実装済み
let claude_cli = ClaudeCliLanguageModel::new(ClaudeCliConfig {
    command: "claude",
    model: "sonnet",
    ..Default::default()
})?;

// AsyncGraphRAG には渡さない（with_async_claude_cli は使わない）
// spec-grag が直接保持
let chapter_summary = claude_cli.complete(&prompt).await?;

// 並列化（HANDOFF.md §2.4 の concurrent batch override）:
let summaries = claude_cli.complete_batch_concurrent(
    &prompts, max_concurrent: 5
).await?;
```

**埋め込みの注入経路（独自実装 #12）**：

`AsyncGraphRAGBuilder.embedder()` setter が無いため、以下のいずれか：

```rust
// 方式 A: spec-grag が thin wrapper を持つ（推奨、vendor 改造なし）
struct SpecGragGraphRAG {
    embedder: OllamaEmbedderAdapter,
    kg: Arc<RwLock<KnowledgeGraph>>,
    retrieval_system: RetrievalSystem,
    // ...
}

// 方式 B: vendor 改造で AsyncGraphRAGBuilder.embedder() を追加（PR 候補）
// ただし AsyncGraphRAG 自体を使わない方針なので、方式 A で十分
```

### D10. 設定ファイル統合

**spec-grag の設計**：SpecGragConfig（独自）→ Config 変換層を通す。

```rust
// spec-grag 独自構造体
#[derive(Deserialize)]
pub struct SpecGragConfig {
    pub sources: SourcesConfig,
    pub core: CoreConfig,
    pub graph: GraphSection,
    pub llm: LlmSection,
}

// graphrag-rs の Config に変換
impl SpecGragConfig {
    pub fn to_graphrag_config(&self) -> graphrag_core::Config {
        let mut cfg = graphrag_core::Config::default();
        cfg.output_dir = self.graph.storage.clone();
        cfg.embeddings.backend = "ollama".to_string();
        cfg.embeddings.model = Some("nomic-embed-text".to_string());
        cfg.ollama.embedding_model = "nomic-embed-text".to_string();
        cfg.entities.use_atomic_facts = true;
        cfg.entities.use_gleaning = true;
        // 必要なフィールドだけ上書き、それ以外は default のまま
        cfg
    }
}
```

`figment` の 4 層 merge は使わない（spec-grag は `.spec-grag/config.toml` 単一ソース）。

### D11. ConversationContext → 検索クエリ変換

**Agent (LLM) の責務**。spec-grag CLI は受け取るだけ。

```
Agent (Claude / Codex) の slash command プロンプト:
  1. ConversationContext を解釈
  2. <課題プロンプト> を解釈
  3. config.toml.sources.include の glob を取得
  4. 関連しそうな章ファイルを Read tool で読む（Agentic search）
  5. 動的にキーワード抽出:
     - high_level (Concept / 上位概念候補): 例 ["認証ポリシー", "境界制御"]
     - low_level (具体エンティティ候補): 例 ["LoginHandler", "AuthMiddleware"]
  6. spec-grag CLI を呼ぶ:
     spec-grag inject "<課題>" --high "認証ポリシー,境界制御" \
                                 --low "LoginHandler,AuthMiddleware"

spec-grag CLI 側:
  受け取った --high / --low をそのまま LightRAG DualLevelRetriever に渡す。
  CLI 内部に固定 synonym 辞書を持たない（Agent が動的判断する方が品質高い）。
```

---

## 5. 不確定項目（追加調査が必要）

Phase 2 で確定しきれず、Phase 3 着手時 or 設計判断時に追加 Read が必要な項目。

| # | 項目 | 必要な調査 | 影響する設計判断軸 |
|---|---|---|---|
| 1 | `load_state_async` の実態（HANDOFF.md §1.7 の主張 vs Agent 3 の grep 結果の矛盾） | `vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs` の load 関連 fn を直接 grep | D7 |
| 2 | KnowledgeGraph の API 全体（add_entity / add_relationship / get_neighbors / to_leiden_graph 以外） | `core/mod.rs` の `impl KnowledgeGraph` ブロック全体を Read | D1, D2, D3 |
| 3 | lib.rs:597-915 の同期 GraphRAG ルート（gleaning enabled / single-pass）の wiring 詳細 | `lib.rs` を実コード断片で抽出 | D1, D2, D9 |
| 4 | `IncrementalGraphStore` trait の具体的実装の有無 | `graph/incremental.rs` の `impl IncrementalGraphStore for ...` を grep | D5, D6 |
| 5 | `HierarchicalCluster` の永続化先（KnowledgeGraph フィールドか別か） | `core/mod.rs` のフィールド宣言と `save_to_json` の対象を確認 | D7 |
| 6 | `with_ollama()` 経路で OllamaEmbeddings がインスタンス化される箇所 | `lib.rs::initialize` と `RetrievalSystem::new` を Read | D9 |
| 7 | entity/gleaning_extractor.rs:110-510 の本体（gleaning ループの LLM 呼び出し回数）| 該当ファイルを Read | D1 |
| 8 | entity/prompts.rs の PromptBuilder の実装（カスタムプロンプト差し込み可否） | 該当ファイルを Read | D1（章別 entity 抽出のドメイン誘導） |
| 9 | summarization/mod.rs:1000-1303（query 機能、JSON serialization） | 該当範囲を Read | D3, D7 |
| 10 | graph/temporal.rs の `TemporalRange` / `TemporalRelationType` 構造 | 該当ファイルを Read | D2（AtomicFact temporal_marker 採用判断） |
| 11 | examples の API ギャップ（`with_text_config` / `with_parallel_processing` / `auto_detect_llm` / `add_document_from_text` の実体） | `lib.rs` と `builder/` を grep | D9（spec-grag が GraphRAG::builder 経路を使うか判断） |
| 12 | legal/medical/financial.toml templates の中身 | 3 ファイルを Read | D10（spec-grag のデフォルト config 設計の参考） |

---

## 6. 付録：raw 4 ファイルへの参照表

各機能の詳細・行番号付き引用は raw を参照。

| 機能 | raw ファイル | セクション |
|---|---|---|
| LLMEntityExtractor / LLMRelationshipExtractor | `agent1_extractor_summarization.md` | M1 |
| AtomicFactExtractor | `agent1_extractor_summarization.md` | M2 |
| Cluster generation / HierarchicalCommunities | `agent1_extractor_summarization.md` | M3 |
| Conflict detection | `agent3_incremental_storage_conflict.md` | M4 |
| Retrieval API（HybridRetriever / DualLevel / HippoRAG / CrossEncoder） | `agent2_retrieval_query.md` | M5 |
| answer_question / hierarchical_query | `agent2_retrieval_query.md` | M6 |
| IncrementalGraphManager | `agent3_incremental_storage_conflict.md` | M7 |
| save_state_async / 永続化粒度 | `agent3_incremental_storage_conflict.md` | M8 |
| HierarchicalConfig / Config | `agent4_config_examples_embedding_symbolic.md` | M9 |
| examples（multi_document_pipeline / 04 / 05） | `agent4_config_examples_embedding_symbolic.md` | M10 |
| Embedding 注入経路 | `agent4_config_examples_embedding_symbolic.md` | M11 |
| Symbolic Anchoring / Dynamic Edge Weighting | `agent4_config_examples_embedding_symbolic.md` | M12 |

Phase 1 の生データ（論文・公式 docs・Cargo features）は [GRAG_FOUNDATION_RAW.md](GRAG_FOUNDATION_RAW.md)（§A〜§E）。

---

## 7. 次フェーズへの橋渡し

本書で揃った：

- **graphrag-rs の機能カタログ（4 分類）**：A. そのまま使える（21 件）／ B. 改造が必要（4 件）／ C. 独自実装が必要（14 件）／ D. 致命的に使えない（12 件）
- **典型利用シーケンス**：spec-core / spec-inject / spec-realign の 3 経路をコード断片付きで記述
- **設計判断軸 D1〜D11 ごとの利用方法**：spec-grag が graphrag-rs の何をどう使うか

次のフェーズ：

| Phase | 内容 | アウトプット |
|---|---|---|
| Phase 2.5 | §5 の不確定項目 12 件を追加調査して埋める | 本書 §5 を「中」以上の把握度で完了 |
| Phase 3 | 利用パターンの整理（spec-core / spec-inject / spec-realign のフロー図） | `doc/GRAG_USAGE_PATTERNS.md` |
| Phase 4 | spec-grag への適用判断（使う / 改造 / 使わない / 独自追加 を機能ごとに確定） | `doc/SPEC_GRAG_APPLICATION.md` |
| Phase 5 | DESIGN.ja.md / DESIGN_old.md / EXTERNAL_DESIGN.ja.md の整合再構築 | spec-grag 詳細設計の更新 |
| Phase 6 | HANDOFF.md §2 の実装作業を解凍 | 実装フェーズ再開 |

設計議論は **Phase 4 完了まで本格再開しない**（FOUNDATION_PLAN.md §10 の原則）。
