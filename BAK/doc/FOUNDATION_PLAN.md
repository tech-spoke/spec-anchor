# spec-grag 土台作り計画

本書は spec-grag が graphrag-rs を活用するための **土台作り** の計画。設計議論の前に、graphrag-rs の機能体系を俯瞰した土台を整備する。

## 1. 目的

ユーザーから明確に指摘された問題（2026-04-27）：

> どちらも正しいとは言えないのかもしれないが、そもそも、GRAG にどういう機能があり、どう利用できるのかが不明なままでは設計も何も無いと言う事なのだと思う。その土台がないから設計が進まない。

これを受け、設計議論に戻る前に **graphrag-rs の機能体系を俯瞰した土台** を整備する。

## 2. 進め方の原則（memory に従う）

- ボトムアップ：「何ができるか」を確認してから、「どう設計するか」を議論する（[feedback_no_design_without_foundation.md](../../../.claude/projects/-home-kazuki-public-html-spec-grag/memory/feedback_no_design_without_foundation.md)）
- 全項目列挙：最初に網羅的に列挙し、各項目の現状把握度を正直に明示する（[feedback_full_scope_enumeration.md](../../../.claude/projects/-home-kazuki-public-html-spec-grag/memory/feedback_full_scope_enumeration.md)）
- 未確認は明示する（[feedback_verify_before_recommend.md](../../../.claude/projects/-home-kazuki-public-html-spec-grag/memory/feedback_verify_before_recommend.md)）
- 軸を立てる、判断を出す（[feedback_structural_analysis.md](../../../.claude/projects/-home-kazuki-public-html-spec-grag/memory/feedback_structural_analysis.md)）
- 最小コストで逃げない（[feedback_no_minimum_cost_escape.md](../../../.claude/projects/-home-kazuki-public-html-spec-grag/memory/feedback_no_minimum_cost_escape.md)）

## 3. 調査範囲（網羅的列挙、全 59 項目）

graphrag-rs に含まれる機能を以下に列挙する。各項目の **現状把握度** は正直に明示する。

**把握度の段階（Phase 1 後に 6 段階へ拡張）**：
未確認 → 表面的（名称のみ） → 浅い（doc コメント / 概要） → 中（一次資料の主要部を読了、論点把握） → 高（実装行レベルまで読了） → 確認済（自分で書いた / 完全把握）

### 3.1 README に挙がる research papers / advanced techniques

| # | 機能 | 出典 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|---|
| 1 | LightRAG Dual-Level Retrieval | EMNLP 2025 | 表面的 | 中 | RAW §A-1（arXiv:2410.05779、ACL Anthology 2025）, §D-1.10（LIGHTRAG_INTEGRATION.md：4 マージ戦略・6000x token 削減） |
| 2 | Leiden Community Detection | Sci Reports 2019 | 表面的 | 中 | RAW §A-2（Nature 2019、arXiv:1810.08473、3 段階アルゴ）, §D-1.9（LeidenConfig フィールド全 6 個・HierarchicalCommunities） |
| 3 | Cross-Encoder Reranking | EMNLP 2019 | 未確認 | 中 | RAW §A-3（arXiv:1901.04085、MS MARCO SOTA）, §D-1.11（2 段階パイプライン Bi-Encoder→Cross-Encoder、CrossEncoderConfig） |
| 4 | HippoRAG Personalized PageRank | NeurIPS 2024 | 未確認 | 中 | RAW §A-4（arXiv:2405.14831、20% multi-hop 向上、10-30x 低コスト）, §D-1.12（HippoRAGConfig：damping_factor=0.5、デュアルシグナル PPR） |
| 5 | Semantic Chunking | LangChain 2024 | 未確認 | 中 | RAW §A-5（embedding 差分閾値ベースの分割、複数 strategy） |
| 6 | Symbolic Anchoring (CatRAG) | Phase 2 | 表面的 | 未確認のまま | RAW §A-6（学術論文出典が発見できず確認度 30%）, §D-6.2（実装ファイル特定不可） |
| 7 | Dynamic Edge Weighting | Phase 2 | 未確認 | 未確認のまま | RAW §A-7（学術論文出典が発見できず確認度 20%）, §D-6.2 |
| 8 | Causal Chain Analysis | Phase 2 | 未確認 | 中 | RAW §A-8（CausalRAG / CC-RAG / arXiv:2503.19878 確認、graphrag-rs 内実装の詳細アルゴは未確認） |
| 9 | Hierarchical Relationship Clustering | Phase 3 | 表面的 | 中 | RAW §A-9（HiRAG arXiv:2503.10150、Leiden + LLM summary）, §D-1.9（HierarchicalCommunities 自動サマリー） |
| 10 | Graph Weight Optimization (DW-GRPO) | Phase 3 | 未確認 | 中 | RAW §A-10（arXiv:2601.11144、Qwen2.5 1.5B が 72B の 94% 性能、3 reward 動的重み） |

### 3.2 Entity Extractor 群

| # | extractor | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 11 | LLMEntityExtractor | 浅い | 中 | RAW §B-1（line:22 keep_alive、99-120 prompt_builder、207-231 OllamaClient generate、jsonfixer による JSON 修復） |
| 12 | LLMRelationshipExtractor | 浅い | 中 | RAW §B-1, §B-2（line:193-263 extract_with_llm、281-409 validate_triple、428-462 fallback co-occurrence、DEG-RAG triple reflection 制御フロー把握） |
| 13 | GleaningEntityExtractor | 表面的 | 中 | RAW §B-1, §B-2（line:113-226 round1/Rn/completion check、228-275 length-based merge、LLMEntityExtractor へ delegate） |
| 14 | AtomicFactExtractor | 浅い | 中 | RAW §B-1（line:122-227 5-tuple 抽出、287-316 atomics_to_graph_elements、causal_strength 取得）, §D-1.5（ATOM Phase 1 完了） |
| 15 | GLiNERExtractor | 表面的 | 中 | RAW §B-1（line:88-95 CUDA、117-235 NER+RE 単一フォワードパス、span/token mode、entity offsets が zero の TODO line:182-186） |

### 3.3 Summarization / Clustering

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 16 | summarization module 全体 | 表面的 | 中 | RAW §B-3（mod.rs:1-260, 421-454、LLMClient trait シグネチャ把握、Progressive strategy） |
| 17 | DocumentTree | 表面的 | 中 | RAW §B-3（line:202-260, 284-304, 421-454、Leaf nodes → 階層マージ merge_size=5、abstractive/extractive 切替） |
| 18 | hierarchical_query | 浅い | 浅い | RAW §B-3（QueryResult 構造把握、内部 traversal アルゴは未読） |
| 19 | cluster generation | 未確認 | 未確認のまま | RAW §B-8（Agent2 自己申告：summarization/mod.rs での「cluster generation」言及は確認、該当コード未読） |
| 20 | LLM cluster summaries | 表面的 | 中 | RAW §D-1.9（LEIDEN_INTEGRATION.md：HierarchicalCommunities の自動サマリー、抽出的＋LLM 対応、bottom-up 生成） |

### 3.4 Retrieval / Reranking

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 21 | retrieval module 全体 | 未確認 | 中 | RAW §B-4（retrieval/mod.rs:1-111、RetrievalSystem / RetrievalConfig / SearchResult / EnrichedRetriever entity:0.4/chunk:0.4/graph:0.2、HybridRetriever RRF/CombMNZ/Linear） |
| 22 | reranking module（Cross-Encoder 等） | 未確認 | 中 | RAW §B-4（reranking/mod.rs:1-14、cross_encoder.rs:1-150、CandleCrossEncoder / ONNX、Confidence normalization）, §D-1.11（CrossEncoderConfig） |
| 23 | lightrag retrieval | 未確認 | 中 | RAW §B-4（lightrag/mod.rs:1-68、keyword_extraction.rs:44-129 high/low level extraction、concept_graph.rs:1-150）, §D-1.10（DualLevelRetriever、4 マージ戦略） |
| 24 | answer_question パイプライン | 表面的 | 浅い | RAW §B-4（query/mod.rs:1-29 QueryIntelligence / adaptive routing、ExplainedAnswer 構造、advanced_pipeline / analysis 等の実装未読） |

### 3.5 Incremental Update

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 25 | IncrementalGraphManager | 表面的 | 中 | RAW §C-3.5（mod.rs:46-63 struct 構成、85-156 IncrementalConfig 全フィールド） |
| 26 | Delta Computation (Bloom filter) | 表面的 | 中 | RAW §C-3.5（delta_computation.rs:122-571、compute_delta / compute_node_delta / 並列処理オプション、property_changes 追跡） |
| 27 | Lazy Propagation | 表面的 | 中 | RAW §C-3.5（lazy_propagation.rs:281-468、queue_node_update / should_propagate / propagate_pending_updates、apply_update が未実装プレースホルダと判明） |
| 28 | Async Batching | 表面的 | 中 | RAW §C-3.5（async_batch.rs:26-437、Tokio mpsc + Rayon、back-pressure 269-288） |
| 29 | ChangeDetector | 浅い | 中 | RAW §C-3.5（mod.rs:431-438, 841-860 SHA-256 ハッシュベース、document_hashes HashMap） |
| 30 | auto_detect_changes フラグ | 浅い | 中 | RAW §C-3.5（IncrementalConfig 全フィールド確認：lazy_propagation_threshold=100、delta_use_bloom_filter=true 等） |

### 3.6 Storage / Persistence

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 31 | save_state_async | 浅い | 中 | RAW §C-3.6（persistence/mod.rs:68-83 Persistence trait、workspace.rs:79-200 WorkspaceManager メソッド一覧） |
| 32 | load_state_async | 浅い | 中 | 同上（load + exists + size メソッド） |
| 33 | graph storage format（JSON / JSONL / バイナリ） | 未確認 | 中 | RAW §C-3.6（parquet.rs:9-140 ParquetPersistence / ParquetCompression {Snappy/Gzip/Lz4/Zstd}、JSON/JSONL は別実装で未読と申告） |
| 34 | indexes（vector / anchors / clusters / risk） | 未確認 | 浅い | RAW §C-3.6（vector/mod.rs:65-522 VectorIndex + HNSW、anchors/clusters/risk のインデックスは未確認） |
| 35 | vector store integration（Qdrant / LanceDB / in-memory） | 表面的 | 中 | RAW §C-3.6（store.rs:1-42 VectorStore trait、memory_store.rs:10-81 MemoryVectorStore、Qdrant/LanceDB は feature gate のみ確認）, §D-1.14（graphrag-server で Qdrant/LanceDB/in-memory のグレースフルフォールバック） |

### 3.7 Embedding

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 36 | OllamaEmbedderAdapter | 浅い | 中 | RAW §C-3.7（ollama.rs:9-85 OllamaEmbeddings、ollama_adapters.rs:14-70 OllamaEmbedderAdapter、初期化 list_local_models / embed / embed_batch シーケンシャル） |
| 37 | ONNX Runtime（GLiNER 経由） | 未確認 | 浅い | RAW §B-1（gline-rs / ONNX Runtime / CUDA / span/token mode 言及、実装内部未読）, §D-1.1（特性フラグ：cuda / metal / webgpu） |
| 38 | Hash-based fallback embedding（README 言及） | 未確認 | 中 | RAW §C-3.7（vector/mod.rs:568-732 EmbeddingGenerator、FNV-1a ハッシュベース、決定的、モデル依存なし） |

### 3.8 LLM 統合

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 39 | AsyncLanguageModel trait | 確認済 | 確認済 | RAW §C-3.8（traits.rs:547-624、GenerationParams / ModelInfo / ModelUsageStats 確認） |
| 40 | LLMClient trait | 浅い | 中 | RAW §B-5（summarization/mod.rs:14-43、generate_summary + batch メソッド）, §C-3.8 |
| 41 | AsyncLanguageModelAdapter | 浅い | 中 | RAW §C-3.8（ollama_adapters.rs:72-152 全メソッド確認、complete_with_params の OllamaGenerationParams 変換、model_info の context_length=4096） |
| 42 | OllamaLanguageModelAdapter | 浅い | 中 | 同上（ollama_adapters.rs:72-152、get_usage_stats:136-151、average_response_time_ms 未実装と判明） |
| 43 | AsyncMockLLM | 表面的 | 中 | RAW §C-3.8（async_mock_llm.rs:35-79 with_templates / set_simulate_delay、361-458 AsyncLanguageModel 実装） |
| 44 | ClaudeCliLanguageModel（自前追加） | 確認済 | 確認済 | RAW §C-3.8（claude_cli.rs:15-275 全コード把握、build_args の `--bare` 不使用、extract_result の JSON パース、120s timeout） |
| 45 | CodexCliLanguageModel（未実装） | 未確認 | 未確認のまま（範囲外） | — |

### 3.9 Configuration

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 46 | Config 構造体（graphrag-core 全体） | 未確認 | 浅い | RAW §D-1.3（graphrag-core/README.md 行 64-141：3 つの設定方法 TypedBuilder / figment / TOML、5 層 Hierarchical Config の存在、構造体定義は未読） |
| 47 | HierarchicalConfig | 浅い | 浅い | 同上（figment ベース、~/.graphrag → ./graphrag.toml → 環境変数の 5 層、フィールド詳細は未読） |
| 48 | OllamaConfig | 表面的 | 中 | RAW §D-1.8（ServiceConfig：ollama_base_url / embedding_model / language_model / vector_dimension）, §C-3.7（OllamaEmbeddings 構造体）, §C-3.8（OllamaLanguageModelAdapter） |
| 49 | Cargo features（lightrag, leiden, cross-encoder, pagerank, async, gliner 等） | 表面的 | 中 | RAW §E（4 bundles：starter / full / wasm-bundle / research、30+ individual features 完全列挙、persistent-storage と neural-embeddings の排他確認）, §D-1.1（特性フラグ全体） |

### 3.10 バイナリ / API

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 50 | graphrag-cli バイナリ | 未確認 | 表面的 | RAW §E（Cargo.toml の name="graphrag-cli", description="Modern Terminal User Interface (TUI) for GraphRAG operations"、内部未読）, §D-6.1（専用ドキュメントが見当たらないと申告） |
| 51 | graphrag-server バイナリ（REST API） | 浅い | 中 | RAW §D-1.14（graphrag-server/README.md：Actix-web 4.9 + Apistos、Qdrant/LanceDB/in-memory フォールバック、`GET /` `GET /health` 等のエンドポイント概要） |
| 52 | graphrag-wasm | 未確認 | 浅い | RAW §D-1.1（README.md 行 1029-1040：Phase 2 進行中 60% 完了、ONNX Runtime Web GPU、WebLLM、IndexedDB、Burn+wgpu 70% 完了） |

### 3.11 Examples / Documentation

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 53 | examples ディレクトリ全体 | 未確認 | 浅い | RAW §D-2（01-05 構造把握、API 複雑度ピラミッド Simple → Easy → Builder → Advanced、04 と 05 の内部は未読、advanced 例の存在を確認） |
| 54 | ADVANCED_FEATURES.md | 浅い | 中 | RAW §D-1.5（行 1-200 で Triple Reflection / Temporal Fields / ATOM、Phase 1-4 概要 ✅ 完了表記） |
| 55 | ENTITY_EXTRACTION.md | 浅い | 中 | RAW §D-1.4（行 1-170 で アーキテクチャ図 / GleaningConfig 全 7 フィールド / Microsoft GraphRAG スタイルの真の LLM 抽出） |
| 56 | README.md | 表面的 | 中 | RAW §D-1.1（行 1-1085 で 11 セクション通読、3 つのデプロイ・5 つの最新技術・Phase 1-4 ロードマップ・特性フラグ・モジュール構成 5 件） |
| 57 | MULTI_DOCUMENT_PIPELINE.md | 未確認 | 中 | RAW §D-1.7（行 1-90、Symposium + Tom Sawyer 例の 3 フェーズ、RRF k=60） |
| 57b | （新規）HOW_IT_WORKS.md | — | 中 | RAW §D-1.2（7 段階パイプライン詳細、3 つのアプローチ semantic/algorithmic/hybrid、TOML 設定駆動） |
| 57c | （新規）PIPELINE_ARCHITECTURE.md | — | 中 | RAW §D-1.6（行 1-168、フェーズ詳細と科学的基礎の対応表） |
| 57d | （新規）OLLAMA_INTEGRATION.md | — | 中 | RAW §D-1.8（ServiceConfig / モデル表 llama3.2:3b・nomic-embed-text:latest 等） |
| 57e | （新規）LEIDEN_INTEGRATION.md | — | 中 | RAW §D-1.9 |
| 57f | （新規）LIGHTRAG_INTEGRATION.md | — | 中 | RAW §D-1.10 |
| 57g | （新規）CROSS_ENCODER_INTEGRATION.md | — | 中 | RAW §D-1.11 |
| 57h | （新規）HIPPORAG_INTEGRATION.md | — | 中 | RAW §D-1.12 |
| 57i | （新規）ENRICHMENT_IMPLEMENTATION.md | — | 中 | RAW §D-1.13（7 層 bottom-up、ChunkMetadata 15 フィールド、Markdown/HTML/PlainText パーサー） |
| 57j | （新規）graphrag-core/README.md | — | 中 | RAW §D-1.3（3 つの設定方法、テンプレート general/legal/medical/financial/technical） |
| 57k | （新規）graphrag-server/README.md | — | 中 | RAW §D-1.14 |
| 57l | （新規）report.md | — | 中 | RAW §D-1.15（Dec 5 2025 比較、Phase 2-3 技術追加、cAST/Dynamic Edge Weighting/Causal Chain Analysis 等） |

### 3.12 Tests / Benchmarks

| # | 機能 | Phase 0 | Phase 1 後 | 根拠 |
|---|---|---|---|---|
| 58 | integration tests | 未確認 | 表面的 | RAW §D-1.15（report.md：tests/e2e/ ディレクトリ追加の事実）, §D-7.1（README 主張：「214 passing tests, zero warnings」） |
| 59 | ベンチマーク | 未確認 | 表面的 | RAW §E（benches/ ディレクトリの存在を確認）, §D-1.5（パフォーマンス指標 30-50% ハルシネーション削減等の数値あり） |

## 4. 現状把握度サマリ

### 4.1 Phase 0（土台作り計画策定時）

- **確認済**：3 項目（traits.rs:547 の AsyncLanguageModel trait、AsyncLanguageModelAdapter line 21-61、自前 ClaudeCliLanguageModel）
- **浅い / 表面的**：23 項目
- **未確認**：33 項目

つまり **全 59 項目中 56 項目（95%）が表面的または未確認**。設計議論に入れる土台はない。

### 4.2 Phase 1 完了後（2026-04-27）

把握度の段階を 6 段階に拡張し、Phase 1 の Agent 4 並列調査結果を反映：

| 段階 | 件数 | 主な対象 |
|---|---|---|
| 確認済 | 3 | AsyncLanguageModel trait / OllamaEmbedderAdapter（部分） / ClaudeCliLanguageModel |
| 高 | 0 | （該当なし） |
| 中 | 47 | 5 extractor 全件 / Incremental 全件 / Storage 主要件 / Embedding 主要件 / LLM 統合 / Retrieval 全件 / 公式 docs 大半 / Cargo features |
| 浅い | 9 | hierarchical_query / cluster generation の名前のみ / examples ディレクトリ詳細 / Config 構造体 / HierarchicalConfig / indexes（vector 以外）/ ONNX / answer_question / graphrag-wasm |
| 表面的 | 4 | graphrag-cli / integration tests / ベンチマーク / 一部の TODO |
| 未確認のまま | 4 | Symbolic Anchoring（CatRAG）/ Dynamic Edge Weighting / cluster generation の実装 / CodexCliLanguageModel（範囲外） |

**Phase 0 → Phase 1 後の変化**：

- 全 59 項目中 47 項目（80%）が「中」以上に到達
- 「未確認のまま」が 33 → 4 件に減少
- 新たに **公式 docs 11+ ファイルの内容**（HOW_IT_WORKS.md / PIPELINE_ARCHITECTURE.md / OLLAMA_INTEGRATION.md / LEIDEN_INTEGRATION.md / LIGHTRAG_INTEGRATION.md / CROSS_ENCODER_INTEGRATION.md / HIPPORAG_INTEGRATION.md / ENRICHMENT_IMPLEMENTATION.md / report.md 等）が把握できた（FOUNDATION_PLAN §3.11 の項目 57b〜57l に追加）

### 4.3 Phase 2 で重点的に詰めるべき残課題

1. **cluster generation の実装ロジック**：Phase 2 でのクラスタ自動生成にあたって必読
2. **examples/04_with_ollama.rs / 05_batch_processing.rs / multi_document_pipeline.rs**：実利用パターンの確認
3. **HierarchicalConfig / Config 構造体定義**：spec-grag が TOML を採用する場合の参考
4. **Conflict detection メカニズム**：spec-grag の ConflictNotes 分類に直結
5. **Symbolic Anchoring / Dynamic Edge Weighting**：実装ファイル特定（grep ベースで再調査）

これらは Phase 2（機能カタログ構築）で個別に Read する。

## 5. 調査方法

各カテゴリで以下の手段を組み合わせる：

| 手段 | 適用カテゴリ | 備考 |
|---|---|---|
| 公式論文（arXiv 等）WebFetch | 3.1（research papers） | 各論文の abstract + 該当セクション |
| GitHub README / docs.rs Read | 3.1〜3.12 全般 | 公式説明 |
| `vendor/graphrag-rs/` 実装の Read | 3.2〜3.9（実装本体） | 主要 struct / trait / fn のシグネチャと処理 |
| `vendor/graphrag-rs/examples/` Read | 3.11 | 実利用例 |
| `vendor/graphrag-rs/*.md`（README、ADVANCED_FEATURES、ENTITY_EXTRACTION、MULTI_DOCUMENT_PIPELINE）Read | 3.11 | 公式設計説明 |
| Cargo.toml（features 一覧） | 3.9 | 機能の有効化オプション |

## 6. 進め方

### Phase 1: 一次資料の網羅的取得（並列） ✅ 完了（2026-04-27）

- 3.1：論文 abstract（10 件、WebFetch）→ Agent 1
- 3.2〜3.8 の実装本体（vendor の Read、Agent (Explore) 並列起動）→ Agent 2 + Agent 3
- 3.11：vendor の docs（実際は 11+ ファイル）の Read → Agent 4
- 3.9：Cargo.toml の features 一覧確認 → Bash

**成果物**：[doc/GRAG_FOUNDATION_RAW.md](GRAG_FOUNDATION_RAW.md)（111KB、5 セクション §A〜§E）

**Phase 1 で確認できなかったもの**（Phase 2 で個別に詰める）：

- examples/04_with_ollama.rs / 05_batch_processing.rs / multi_document_pipeline.rs の中身
- Symbolic Anchoring（CatRAG）/ Dynamic Edge Weighting の実装ファイル特定
- cluster generation の実装ロジック
- WEBLLM_INTEGRATION.md / BURN_WASM_STATUS.md
- HierarchicalConfig / Config 構造体定義
- Conflict detection メカニズム
- LanceDB / Qdrant 実装詳細
- TemporalRelationType enum / GraphStatistics 計算ロジック

### Phase 2: 機能カタログの構築（順次）

各機能について以下を埋める：

```
機能名:
  入力:
  出力:
  内部処理（要点）:
  典型 use case:
  他機能との連携:
  実装ファイル:
  ライセンス / 出典:
  確認できなかった点:
```

### Phase 3: 利用パターンの整理

- graphrag-rs 標準の典型フロー（A 用例：知識グラフ構築 + 検索）を図示
- 仕様書 GRAG が必要とする変形フロー（EXTERNAL_DESIGN.ja.md）を図示
- 標準フロー → 仕様書 GRAG への gap を列挙

### Phase 4: spec-grag への適用判断

- どの機能を **そのまま使う**
- どの機能を **改造して使う**
- どの機能を **使わない**
- 何を **独自に追加する**

## 7. アウトプット

| ファイル | 内容 | フェーズ | 状態 |
|---|---|---|---|
| `doc/GRAG_FOUNDATION_RAW.md` | Phase 1 の 5 並列調査の生データ（4 Agent + 1 Bash 結果） | Phase 1 | ✅ 完了（2026-04-27） |
| `doc/GRAG_FOUNDATION.md` | 機能カタログ（59 項目 + 追加項目を §6 Phase 2 のテンプレで整理） | Phase 2 | 未着手 |
| `doc/GRAG_USAGE_PATTERNS.md` | 利用パターン図（標準フロー / spec-grag フロー / gap） | Phase 3 | 未着手 |
| `doc/SPEC_GRAG_APPLICATION.md` | spec-grag への適用判断（使う / 改造 / 使わない / 独自追加） | Phase 4 | 未着手 |

## 8. 完了条件

- 全 59 項目が **「確認済」または「明示的に対象外」** になっている
- Phase 3 で「標準フロー」「仕様書 GRAG フロー」「gap」が図示されている
- Phase 4 で「使う / 改造する / 使わない / 独自追加する」が機能ごとに判断されている

これらが揃うまで **設計の議論には戻らない**。

## 9. 想定時間

- Phase 1：1-2 時間（並列調査）
- Phase 2：2-4 時間（カタログ整理）
- Phase 3：1-2 時間
- Phase 4：1-2 時間（ユーザーと議論）

合計 **5-10 時間**。複数セッションにまたがる可能性あり。

## 10. 進めるための承認待ち

ユーザーに以下を確認したい：

1. 上記 **59 項目で網羅的か**？追加すべき項目があれば（例：私が見落としている graphrag-rs の機能、または graphrag-rs 以外で土台に必要な要素）
2. **進め方（Phase 1〜4）で OK か**、それとも別の順序が良いか
3. **アウトプット 3 ファイル** の構成で OK か
4. **想定時間（5-10 時間）** を許容できるか
5. Phase 1 を Agent (Explore) で **並列実行する** ことに同意するか（Agent もまた表面確認に陥るリスクがあるため、私が検証する役割を担う）

## 11. 関連ドキュメント

- [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md)：外部契約（source of truth、Phase 4 の判断基準）
- [doc/DESIGN.ja.md](DESIGN.ja.md)：Codex 版の詳細設計（Phase 4 で再構築対象、現状の DESIGN は「土台不足のまま書かれている」状態）
- [doc/DESIGN_old.md](DESIGN_old.md)：私の旧設計（GRAG の使い方を誤った設計、Phase 4 で破棄予定）
- [doc/GRAG_FOUNDATION_RAW.md](GRAG_FOUNDATION_RAW.md)：Phase 1 の生データ（**Phase 2 の一次ソース**）
- [HANDOFF.md](../HANDOFF.md)：実装フェーズの進捗（土台作り完了後に再構築）

## 12. 次セッションへの申し送り

Phase 1 完了時点（2026-04-27）の状態：

1. **完了した作業**：
   - 5 並列調査（4 Agent + 1 Bash）の生データ取得
   - [doc/GRAG_FOUNDATION_RAW.md](GRAG_FOUNDATION_RAW.md) への保管
   - 本書 §3 の把握度テーブルを 6 段階で更新

2. **次セッションでの最初の作業**：
   - Phase 2 着手：[doc/GRAG_FOUNDATION.md](GRAG_FOUNDATION.md) の作成（59 項目 + §3.11 追加項目）
   - §6 Phase 2 のテンプレ（入力／出力／内部処理／典型 use case／他機能との連携／実装ファイル／ライセンス・出典／確認できなかった点）に従う
   - **必ず本書 §4.2 の現状把握度表を参照**してから Phase 2 を始める。「中」のままでは Phase 4 判断が出来ない項目は Phase 2 内で追加 Read を行う

3. **絶対に守る原則**（memory に明記済）：
   - 推奨・判断を出す前に一次資料を読み返す（[verify_before_recommend](../../.claude/projects/-home-kazuki-public-html-spec-grag/memory/feedback_verify_before_recommend.md)）
   - 未確認の項目は最初から「未確認」と明示する（[full_scope_enumeration](../../.claude/projects/-home-kazuki-public-html-spec-grag/memory/feedback_full_scope_enumeration.md)）
   - 土台が出来るまで設計議論には戻らない（[no_design_without_foundation](../../.claude/projects/-home-kazuki-public-html-spec-grag/memory/feedback_no_design_without_foundation.md)）
