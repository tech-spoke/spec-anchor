# Phase 2 Agent 2 — Retrieval / Query API 深掘り

調査対象 vendor: `vendor/graphrag-rs/graphrag-core`（spec-grag が `Cargo.toml` で path 依存している実体）。
別ツリー `vendor/graphrag-rs-claude-spike` は **現在ビルドされない**（spec-grag は使っていない）が、参考のため確認した範囲を別途記す。

---

## 重要な事実（最初に提示）

1. **HippoRAG PPR の実装有無 = あり**
   `vendor/graphrag-rs/graphrag-core/src/retrieval/hipporag_ppr.rs`（441 行）に `HippoRAGRetriever` / `HippoRAGConfig` / `Fact` が実装済み。`#[cfg(feature = "pagerank")]` で feature gate されているが、コード本体は揃っている。
   ただし **`RetrievalSystem` から自動で呼ばれることは無い**。利用者が `Fact` リスト・`entity_to_passages` map・`passage_scores` map を自前で組み立てて `retrieve()` を呼ぶ。

2. **LightRAG DualLevelRetriever の実装有無 = あり**
   `lightrag/dual_retrieval.rs`（357 行）。`MergeStrategy` は **4 種**（`Interleave` / `HighFirst` / `LowFirst` / `Weighted`）。`#[cfg(feature = "lightrag")]` ではなく **モジュール自体は常時ビルド**（`lightrag = []` は空 feature。lightrag は keyword_extraction / dual_retrieval / graph_indexer の 3 ファイルが常時 `pub mod`、`lazygraphrag` のみ feature gate）。

3. **HybridRetriever の FusionMethod = 4 種**
   `RRF` / `Weighted` / `CombSum` / `MaxScore`。**CombMNZ や Linear は無い**。ただし Weighted がそれに近い。`hybrid.rs:38-47`。

4. **Cross-Encoder の実装状況**
   - `reranking/cross_encoder.rs` (473 行) に trait `CrossEncoder` と 2 つの実装：
     - `CandleCrossEncoder` （`#[cfg(feature = "neural-embeddings")]`、Candle + BERT、HF Hub からモデル DL、本格実装）
     - `ConfidenceCrossEncoder` （**passthrough のフォールバック実装**、relevance_score = original_score でスコアを変えない）
   - `reranking/confidence.rs` は **1 行（空）**。
   - feature `cross-encoder = []` も別途あるが、現状の `cross_encoder.rs` は `cross-encoder` feature ではなく `neural-embeddings` で本実装が gate されている点が紛らわしい。

5. **AdaptiveRetriever は使い物にならない可能性大**
   `retrieval/adaptive.rs` の `AdaptiveRetriever::retrieve()` は `RetrievalSystem` の `vector_search` / `graph_search` / `bm25_search` / `public_hierarchical_search` を呼ぶが、**これらは全部スタブ実装**（`mod.rs:1751-1801`）。
   - 例：`graph_search()` は `format!("Graph-based result for: {query}")` をハードコードで返す。
   - `bm25_search()` は `format!("BM25 result for: {query}")` を返すだけ。

6. **`RetrievalConfig` のデフォルト 0.4/0.4/0.2 weight は変更可能**
   `RetrievalConfig` は struct で `pub` フィールド。`RetrievalSystem::new()` 内でハードコードされて構築されるが、`pub` のため後から差し替え可能（ただし `RetrievalSystem` の `config` フィールドが pub でないので公式の setter は無い）。`mod.rs:91-128`。

7. **`hierarchical_query_grouped` は spec-grag が使っている vendor には存在しない**
   `vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs:311` には通常の `hierarchical_query` のみ。`hierarchical_query_grouped` は `vendor/graphrag-rs-claude-spike/graphrag-core/src/async_graphrag.rs:336` にしか無い。spec-grag の HANDOFF.md は spike vendor を前提に書かれているが、現在の `Cargo.toml` は通常 vendor を参照。**設計判断時に矛盾を解消する必要あり**。

8. **`hierarchical_query` の "traversal" は traversal ではない**
   `DocumentTree::query`（`summarization/mod.rs:914-939`）は **全ノード線形スキャン**してキーワード重複でスコアリング。木構造の depth-first / breadth-first 走査ではない。レベルごとのフィルタは `level_score = 1.0 / (level + 1)` でレベル番号を分母にした弱いペナルティのみ。

9. **多くの query/* モジュールが空ファイル**
   `query/advanced_pipeline.rs` / `analysis.rs` / `expansion.rs` / `multi_query.rs` / `ranking_policies.rs` は **全て 1 行**（空または stub）。
   - 公開されているのは `intelligence.rs`（`QueryIntelligence`、英語ハードコード synonym/template）と `adaptive_routing.rs`（`QueryComplexityAnalyzer`、英語キーワードハードコード）と `optimizer.rs`（681 行、別系統）。
   - **日本語クエリでは intelligence / adaptive_routing の効果はほぼ無い**（"who is" / "compare" / "overview" 等を contains 検出している）。

10. **`hybrid_query` 内の adaptive_retrieval は重み計算をクエリタイプから決定**
    `mod.rs:1177-1189` の `calculate_strategy_weights` は `(QueryType, QueryIntent)` 組合せで vector/graph/hierarchical の 3 重みを返す。**英語前提のキーワード検出に依存**（"overview" / "compare" 等）。

---

## M5. Retrieval API の組み合わせ規則

### 入力

`RetrievalSystem`：
- `Config`（`Config::default()` 経由）。`config.retrieval.top_k` のみ参照。
- `KnowledgeGraph` を `index_graph(&self, graph: &KnowledgeGraph)` で投入（async）。
- 後付けで `initialize_pagerank(&mut self, graph)` / `initialize_enriched(config)` を呼ぶことで PageRank（fast-GraphRAG 系列）と enriched metadata 機能を有効化できる。

`HybridRetriever`：
- `HybridConfig`（semantic_weight / keyword_weight / fusion_method / rrf_k / max_candidates / min_score_threshold）。
- `initialize_with_graph(&mut self, graph)` で内部の `VectorIndex` と `BM25Retriever` を構築。

`DualLevelRetriever`（LightRAG）：
- `Arc<KeywordExtractor>`（`AsyncLanguageModel` 必須、LLM コール前提）
- `Arc<dyn SemanticSearcher>` を **2 つ**（high-level / low-level、それぞれ別 index）
- `DualRetrievalConfig`（high_level_weight / low_level_weight / merge_strategy）

`HippoRAGRetriever`：
- `HippoRAGConfig`（damping_factor=0.5、passage_node_weight=0.05 等、HippoRAG 論文に準拠したデフォルト）
- `with_pagerank(PersonalizedPageRank)` で PPR エンジンを注入
- `retrieve(query, top_k_facts: Vec<Fact>, entity_to_passages: HashMap, passage_scores: HashMap)` を呼ぶ際に **これらは全て利用者が用意する**

`CrossEncoder` trait：
- `rerank(&self, query: &str, candidates: Vec<SearchResult>) -> Result<Vec<RankedResult>>`
- `score_pair(&self, query: &str, document: &str) -> Result<f32>`
- `score_batch(&self, pairs: Vec<(String, String)>) -> Result<Vec<f32>>`

### 出力

- `RetrievalSystem::hybrid_query` → `Vec<SearchResult>`
- `HybridRetriever::search` → `Vec<HybridSearchResult>`（semantic_score / keyword_score / fusion_method を保持）
- `DualLevelRetriever::retrieve` → `DualRetrievalResults { high_level_chunks, low_level_chunks, merged_chunks, keywords }`
- `HippoRAGRetriever::retrieve` → `Vec<SearchResult>`（content は空文字、呼び出し側で埋める前提）
- `CrossEncoder::rerank` → `Vec<RankedResult>`（RankedResult { result, relevance_score, original_score, score_delta }）

### 内部処理（要点、実装行レベル）

**`RetrievalSystem::hybrid_query` (mod.rs:650-687)**：
1. `analyze_query(query, graph)` → `QueryAnalysis`（mod.rs:874-959、英語前提のキーワード分類）
2. `embedding_generator.generate_embedding(query)`
3. `execute_adaptive_retrieval` (mod.rs:962-1026)：
   - `calculate_strategy_weights(analysis)` で `(vector_weight, graph_weight, hierarchical_weight)` 決定（mod.rs:1177-1189）
   - vector_similarity_search → entity_centric_search / entity_based_search → hierarchical_search → 複雑度>0.7 で advanced_graph_traversal
   - `cross_strategy_fusion`：複数戦略で同じ content key を持つ結果に boost +0.2/strategy（mod.rs:1316-1363）
   - `adaptive_rank_and_deduplicate`：query_type ごとのスコア調整＋result_type ごとの上限（top_k/3 / top_k/2 等）で多様性確保（mod.rs:1366-1436）
4. `EnrichedRetriever` がセットされていれば metadata boost と structure filter を後段で適用

**`HybridRetriever::search` (hybrid.rs:168-186)**：
1. `semantic_search` → vector_index.search で `Vec<(id, score, content)>`
2. `keyword_search` → bm25_retriever.search で `Vec<BM25Result>`
3. `combine_results` で 4 つの fusion メソッド分岐（hybrid.rs:209-227）
   - **RRF**：`rrf_score = 1.0 / (rrf_k + rank + 1.0)` を semantic / keyword それぞれの順位から計算し、weight をかけて加算（hybrid.rs:230-261）
   - **Weighted**：max スコアで正規化後、weight をかけて加算（hybrid.rs:264-313）
   - **CombSum**：raw スコアをそのまま加算（正規化なし）（hybrid.rs:316-342）
   - **MaxScore**：semantic / keyword で大きい方を採用（hybrid.rs:345-371）

**`DualLevelRetriever::retrieve` (dual_retrieval.rs:103-142)**：
1. `keyword_extractor.extract_with_fallback(query)` → `DualLevelKeywords { high_level, low_level }`（LLM コール、失敗時は単純な単語分割でフォールバック）
2. `tokio::join!` で `retrieve_high_level` / `retrieve_low_level` を並列実行
   - 各々 `keywords.join(" ")` で結合した query を `SemanticSearcher::search` に渡す
3. `merge_results` で 4 戦略分岐：
   - **Interleave** (dual_retrieval.rs:204-242)：高/低を交互に取り、seen_ids で dedup
   - **HighFirst** / **LowFirst** (dual_retrieval.rs:245-275)：片方を先に詰めて、足りない分だけもう片方
   - **Weighted** (dual_retrieval.rs:278-316)：weight × score で全結合してソート → dedup → top_k
4. **重要**：DualLevelRetriever は内部で `SemanticSearcher` trait を 2 つ要求するので、利用者が「topic 用 index（コミュニティサマリ等）」と「entity 用 index（chunks/entities）」を **別々に構築する責任**を持つ。spec-grag では章ごとの community summary index がまだ無い → **DualLevel をそのまま使うには事前準備（高レベル index 構築）が必要**。

**`HippoRAGRetriever::retrieve` (hipporag_ppr.rs:117-140)**：
1. `calculate_entity_weights`：fact_score を passage 数で割り（generic entity 抑制）、出現回数で平均（hipporag_ppr.rs:146-195）
2. `calculate_passage_weights`：passage_scores × passage_node_weight=0.05（hipporag_ppr.rs:198-216）
3. `combine_weights`：合算後に総和で正規化（reset distribution として使うため）（hipporag_ppr.rs:219-240）
4. `run_ppr`：注入された `PersonalizedPageRank::calculate_scores(reset_probabilities)` を呼ぶ（hipporag_ppr.rs:243-256）
5. `rank_passages`：PPR スコアから passage ノードのみ抽出してソート（hipporag_ppr.rs:259-294）

**`CandleCrossEncoder::score_pair` (cross_encoder.rs:198-252)**：
1. tokenizer.encode((query, document)) で 2 セグメント結合
2. `model.forward(token_ids, token_type_ids)` で BERT 通過
3. logits[0] を取り出し、`normalize_scores` なら sigmoid で 0-1 化

**`ConfidenceCrossEncoder::rerank` (cross_encoder.rs:329-345)**：候補をそのまま `RankedResult` にラップして返すだけ（**スコア変えない、score_delta=0**）。事実上のフォールバック。

### 典型 use case

- **シンプル GraphRAG 質疑応答**：`GraphRAG::ask_explained(query)` → 内部で `hybrid_query` → `ExplainedAnswer`。HippoRAG / DualLevel / CrossEncoder は経由しない。
- **構造的・キーワード重視検索**：`HybridRetriever::search`（vector + BM25 を RRF でフュージョン）。
- **トピック × エンティティ二段階検索**：`DualLevelRetriever::retrieve`（要 LLM、要 2 つの SemanticSearcher）。
- **Fact-grounded reranking**：`HippoRAGRetriever::retrieve`（要 Fact 抽出 / PPR エンジン）。
- **後段精度向上**：候補数 top_k×4 程度を用意 →`CrossEncoder::rerank`。

### 他機能との連携

- `RetrievalSystem` が `DocumentTree`（HashMap<DocumentId, DocumentTree>）を `hybrid_query_with_trees` から受け取り、hierarchical_search で利用。
- `EnrichedRetriever` は `boost_with_metadata` と `filter_by_structure` を `hybrid_query_with_trees` 末尾で適用（mod.rs:678-684）。
- `HippoRAGRetriever` は `KnowledgeGraph` を直接見ず、entity_to_passages / passage_scores を **外部から受け取る** → `KnowledgeGraph` から自前で抽出する glue コードが必要。
- `DualLevelRetriever` は `KnowledgeGraph` も `RetrievalSystem` も知らず、`SemanticSearcher` 抽象だけに依存 → 既存 `RetrievalSystem` を `SemanticSearcher` 実装で wrap すれば組み込み可能。

### 実装ファイル

- `vendor/graphrag-rs/graphrag-core/src/retrieval/mod.rs`（2094 行、`RetrievalSystem` / `RetrievalConfig` / `SearchResult` / `ResultType` / `ExplainedAnswer` / `QueryAnalysis` / `QueryResult`(retrieval 版)）
- `vendor/graphrag-rs/graphrag-core/src/retrieval/hybrid.rs`（545 行、`HybridRetriever` / `FusionMethod`）
- `vendor/graphrag-rs/graphrag-core/src/retrieval/hipporag_ppr.rs`（441 行、`HippoRAGRetriever`）
- `vendor/graphrag-rs/graphrag-core/src/retrieval/enriched.rs`（530 行、`EnrichedRetriever`）
- `vendor/graphrag-rs/graphrag-core/src/retrieval/adaptive.rs`（384 行、ただし呼び出す先がスタブ）
- `vendor/graphrag-rs/graphrag-core/src/retrieval/bm25.rs`（371 行、本実装）
- `vendor/graphrag-rs/graphrag-core/src/retrieval/pagerank_retrieval.rs`（902 行、fast-GraphRAG 系の別系統）
- `vendor/graphrag-rs/graphrag-core/src/lightrag/mod.rs` + `dual_retrieval.rs`（357 行）+ `keyword_extraction.rs`（273 行）
- `vendor/graphrag-rs/graphrag-core/src/reranking/mod.rs`（14 行）+ `cross_encoder.rs`（473 行）
- `vendor/graphrag-rs/graphrag-core/Cargo.toml`：features 定義（`pagerank` / `lightrag` / `lazygraphrag` / `cross-encoder` / `neural-embeddings`）

### ライセンス・出典

- HippoRAG：論文 arXiv:2405.14831、ソースコメントに明記（hipporag_ppr.rs:10-11）
- LightRAG：論文 arXiv:2410.05779（EMNLP 2025）、lightrag/mod.rs:11
- Cross-Encoder：Reimers & Gurevych "Sentence-BERT" (2019)、cross_encoder.rs:8-9
- ライセンスは graphrag-rs ルート LICENSE に従う（未確認、別 Agent 範囲）。

### 確認できなかった点

- `lightrag = []` が空 feature でモジュール側で `#[cfg]` が付いていないように見えたが、`lightrag/mod.rs:21-23` を見る限り `dual_retrieval` / `graph_indexer` / `keyword_extraction` は **無条件 pub mod**。再エクスポートも無条件（mod.rs:43-47）。実質「常時ビルド、`lightrag` feature flag は形骸化」と判断。
- `pagerank` feature を有効にした場合の `PersonalizedPageRank::calculate_scores` の挙動詳細（呼び出し方は確認済みだが、収束保証や疎行列実装は未読）。
- `EnrichedRetriever::metadata_search` の `min_node_size` / `summary` 等の依存先 metadata は `chunk.metadata.keywords` 等を使うが、graphrag-rs 側の chunk metadata 抽出ロジック（M2 範囲）の出力品質は未確認。
- `huggingface-hub` feature と `neural-embeddings` feature が分かれているが、`CandleCrossEncoder::new` は両方を `#[cfg]` で要求している（cross_encoder.rs:88-90）。実利用では両 feature を同時有効化する必要あり。
- `cross-encoder = []` feature が定義されているが、`cross_encoder.rs` 内のモジュール gate には使われていない（neural-embeddings / huggingface-hub のみ）。何のための feature か不明。

### D4 への寄与

**制約探索（Purpose / Concept / Source specs から制約を取得）**：
- spec-grag の実装観点で「キーワード一致」「章・節フィルタ」が重要 → **HybridRetriever（RRF, vector+BM25）** が最初の候補。BM25 で語彙一致、vector で意味一致を取る基本構成。
- 章・節情報の取得には **EnrichedRetriever の `filter_by_structure`** が使える（chunk.metadata に chapter/section が乗っている前提）。Phase 1 の調査で metadata がどこまで入っているかを確認する必要あり（M2 範囲）。
- HippoRAG PPR は「fact-based」検索なので、Concept Spec / Purpose Spec を fact triple 化できれば強い候補。ただし **fact 抽出 → entity_to_passages map → passage_scores の glue コードを自前で書く**必要あり。

**修正対象探索（課題プロンプト → Agentic search → ERG → Hierarchical Cluster → 修正対象候補）**：
- 「課題プロンプト → 関連エンティティ → グラフ拡張」のフェーズには **`RetrievalSystem::hybrid_query` の entity_centric_search**（mod.rs:1192-1252）がそのまま使える。`graph.get_neighbors(&entity.id)` でエンティティ中心の隣接拡張あり。
- ERG（Entity Relationship Graph）からのクラスタリング → 階層辿りには **`DocumentTree.query`** が使えるが、**実態はフラット線形スキャン**なので、spec-grag が想定する「Hierarchical Cluster の depth-aware 探索」には不足。改造または別実装が必要。
- LightRAG DualLevelRetriever の「high_level=topic（修正のスコープ）/ low_level=entity（具体的修正対象）」という構造は、修正対象探索の 2 段階フェーズ（広い検索 → 狭い特定）に綺麗にマッチする。**ただし high_level index（topic/community summary）を別途構築する必要あり**。

**Cross-Encoder rerank（2 段階パイプライン）の採否**：
- Bi-Encoder（vector + BM25）→ Cross-Encoder の構成は cross_encoder.rs に実装済み。`CandleCrossEncoder` で `cross-encoder/ms-marco-MiniLM-L-6-v2` を HF Hub から DL（英語向けモデル）。
- 日本語仕様文書では **多言語 cross-encoder モデル**（`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` 等）への差し替えが必要。`CrossEncoderConfig.model_name` で変更可。
- spec-grag の精度要求次第だが、**2 系統探索の最後段に置くと候補数を絞り込みやすい**。コスト（GPU/CPU 時間）と精度のトレードオフ。

**LightRAG dual-level の採否**：
- 採用するなら **high_level index = community summary 群（要 Leiden + summarize）/ low_level index = chunks**。
- LLM で keyword 抽出を毎クエリ実行する点がコスト要因。`extract_with_fallback` でフォールバック可能だが、フォールバックは単純単語分割なので品質劣化大。
- 仕様文書の特性（章立てが明確、固有名詞が定義 → 参照される）と相性は良い。

### 設計判断への含意

- **そのまま使える**：`HybridRetriever` (RRF / Weighted / CombSum / MaxScore) ／ `BM25Retriever` ／ `EnrichedRetriever` の boost_with_metadata と filter_by_structure ／ `ExplainedAnswer::from_results`。
- **改造が必要**：
  - `RetrievalSystem::hybrid_query` 内部の `analyze_query` と `calculate_strategy_weights` は **英語ハードコードのため日本語クエリに使えない**。日本語向けに置き換えるか、上位層で QueryType を直接渡す API を作る必要あり。
  - `DocumentTree::query` の **フラット線形スキャン**は階層的探索を必要とする修正対象探索に不向き → 真の depth-first / level-aware traversal を spec-grag で実装する必要。
  - `hierarchical_query_grouped` は **spike vendor のみ存在** → 通常 vendor にバックポートするか、spec-grag 側で同等関数を 1 ファイル追加（実装は 15 行程度）。
- **使う前に下準備が必要**：
  - `DualLevelRetriever`：high-level index（community summary）が必要。Leiden + summarize の前段が前提条件。
  - `HippoRAGRetriever`：fact 抽出と entity_to_passages map を spec-grag で組み立てる glue が必要。
- **使えない・使うべきでない**：
  - `AdaptiveRetriever`（adaptive.rs）：呼び出す先のメソッド群がスタブ。
  - `query/intelligence.rs::QueryIntelligence`：英語ハードコード synonym/template、日本語不可。
  - `query/adaptive_routing.rs::QueryComplexityAnalyzer`：英語ハードコードキーワード、日本語クエリでは default_level に張り付く。
  - `query/{advanced_pipeline, analysis, expansion, multi_query, ranking_policies}.rs`：**全て 1 行スタブ**。

---

## M6. answer_question / hierarchical_query の内部 traversal

### 入力

- `AsyncGraphRAG::answer_question(question: &str)` → 内部で `knowledge_graph` と `language_model` を要求（async_graphrag.rs:257-281）。
- `AsyncGraphRAG::hierarchical_query(query: &str, max_results: usize)` → `document_trees: Arc<RwLock<HashMap<DocumentId, DocumentTree>>>` を読む（async_graphrag.rs:311-331）。
- `GraphRAG::ask_explained(query: &str)`（lib.rs:1375）→ 内部で `query_internal_with_results(query)` → `retrieval.hybrid_query(query, graph)`。

### 出力

- `answer_question` → `GeneratedAnswer { answer_text, confidence_score, sources, entities_mentioned, mode_used: AnswerMode::Abstractive, context_quality }`（async_graphrag.rs:353-360）。
- `hierarchical_query` → `Vec<QueryResult>`（**summarization 版** `QueryResult`：`{ node_id, score, level, summary, keywords, chunk_ids }`、summarization/mod.rs:1216-1229）。
- `ask_explained` → `ExplainedAnswer { answer, confidence, sources, reasoning_steps, key_entities, query_analysis: Option<QueryAnalysis> }`（retrieval/mod.rs:191-204）。

**注意**：`QueryResult` は **2 つの異なる型**が同名で存在する。
- `retrieval/mod.rs:474` の `QueryResult { query, results: Vec<SearchResult>, summary, metadata }` ← retrieval 全体の wrap
- `summarization/mod.rs:1216` の `QueryResult { node_id, score, level, summary, keywords, chunk_ids }` ← Tree のノード結果
`hierarchical_query` が返すのは **後者**（summarization 版）。spec-grag のコードは `use graphrag_core::summarization::QueryResult` を選ぶべき。

### 内部処理（要点、実装行レベル）

**`AsyncGraphRAG::answer_question` (async_graphrag.rs:257-281)**：
1. `knowledge_graph.read().await` ＋ `language_model` 取得
2. `async_retrieval(question, graph)`（async_graphrag.rs:284-308）→ **ナイーブ実装**：chunks を最初の 3 件だけスキャンして `chunk.content.contains(query)` でフィルタ。BM25 も vector も使っていない（**実質スタブ**）
3. `hierarchical_query(question, 5)` で `Vec<QueryResult>` 取得
4. `generate_answer_async`（async_graphrag.rs:334-361）で context 組立 → prompt 化 → `llm.complete(&prompt).await`

**`AsyncGraphRAG::hierarchical_query` (async_graphrag.rs:311-331)**：
1. `document_trees.read().await` を取得
2. **全 DocumentTree について `tree.query(query, max_results)` を呼ぶ**（async_graphrag.rs:319-324）
3. 全結果を集約 → score 降順 → `truncate(max_results)` で全 doc 合算後に top_k

**`DocumentTree::query` (summarization/mod.rs:914-939)**：
1. `text_processor.extract_keywords(query, 5)` でクエリキーワード抽出
2. **`for (node_id, node) in &self.nodes`：全ノード線形スキャン**
3. `calculate_relevance_score(node, query_keywords, query)`（summarization/mod.rs:942-978）：
   - `node.summary + node.keywords` を含む text に対し query_keywords の出現で +1.0/keyword
   - query 単語の overlap 比率 × 2.0
   - `level_score = 1.0 / (level + 1)` × 0.5（**level が高い = abstract = 弱い分母 → 高 score boost**…とコメントにあるが実装は逆で **level が低い leaf ほど高い**点に注意）
4. score > 0.1 のノードを `QueryResult` に変換して push
5. score 降順 → `truncate(max_results)`

**つまり「hierarchical_query の traversal」は traversal ではない**：
- 親子関係を辿らない
- depth-first / breadth-first 走査ではない
- 各ノード独立にスコアリング → ソート

これは spec-grag の「修正対象探索 → ERG → Hierarchical Cluster」というフローで階層を意識した辿りを期待する場合、**致命的に不足**。

**`GraphRAG::ask_explained` (lib.rs:1375-1403)**：
1. `query_internal_with_results(query)` → `retrieval.hybrid_query(query, graph)` で `Vec<SearchResult>`
2. `config.ollama.enabled` なら `generate_semantic_answer_from_results` で LLM 生成、無効なら top 3 の content を join
3. `ExplainedAnswer::from_results(answer, &search_results, query)` で構造化（retrieval/mod.rs:248-358）：
   - 平均 score → confidence 計算（`(avg_score * 0.7 + 0.3).clamp(0, 1)`）
   - top 5 を SourceReference に詰める（type 判別、200 char 切り詰め）
   - reasoning_steps を 4 段階固定で組み立て：query 解析 → entity 検出 → chunk 検索 → 合成
   - **query_analysis フィールドは `None` で固定**（retrieval/mod.rs:356）

### 典型 use case

- 単発質問応答：`GraphRAG::ask_explained(query)` で `ExplainedAnswer` を取得 → confidence と reasoning_steps を UI 表示。
- 階層検索（コミュニティ要約等）：`AsyncGraphRAG::hierarchical_query(query, max_results)` → 全 doc tree を平等に検索した結果。
- 対話システム：`AsyncGraphRAG::answer_question(question)` → `GeneratedAnswer.answer_text` をユーザに返す（ただし async_retrieval が naive なため精度は出ない）。

### 他機能との連携

- `GraphRAG::ask_explained` → `RetrievalSystem::hybrid_query` → `EnrichedRetriever`（ある場合）→ `ExplainedAnswer::from_results`。
- `AsyncGraphRAG::answer_question` → `async_retrieval`（naive）＋ `hierarchical_query`（DocumentTree 全走査）→ `assemble_context_async`（mod.rs:364-394）→ LLM。
- `ExplainedAnswer.query_analysis` は `Option<retrieval::QueryAnalysis>` だが、`ExplainedAnswer::from_results` 内では **常に None**。`retrieval::QueryAnalysis` は `RetrievalSystem::analyze_query` で作られるが、`ExplainedAnswer` 経路では渡されない。

### 実装ファイル

- `vendor/graphrag-rs/graphrag-core/src/lib.rs`（`GraphRAG::ask` / `ask_explained` / `query_internal` / `query_internal_with_results`、1306-1500 行付近）
- `vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs`（`AsyncGraphRAG`、661 行、`answer_question`/257、`async_retrieval`/284、`hierarchical_query`/311、`generate_answer_async`/334、`assemble_context_async`/364）
- `vendor/graphrag-rs/graphrag-core/src/summarization/mod.rs`（`DocumentTree`/192、`DocumentTree::query`/914、`QueryResult`/1216）
- `vendor/graphrag-rs/graphrag-core/src/retrieval/mod.rs`（`ExplainedAnswer`/191、`from_results`/249、`format_display`/361）
- `vendor/graphrag-rs/graphrag-core/src/query/intelligence.rs`（453 行、`QueryIntelligence`、`QueryType` 7 種）
- `vendor/graphrag-rs/graphrag-core/src/query/adaptive_routing.rs`（365 行、`QueryComplexityAnalyzer`、`QueryComplexity` 5 段階）

### ライセンス・出典

- 内製コード。論文出典は ExplainedAnswer の rustdoc には無し。reasoning_steps の構造は CoT-like だが特定論文の引用無し。

### 確認できなかった点

- `query/optimizer.rs`（681 行）：join ordering / cost estimation 系統。ask_explained / hierarchical_query からは呼ばれていないので未読。
- `query/planner.rs`（59 行）：内容を読んでいないが、行数的に骨組みのみ。
- `AsyncGraphRAG::generate_answer_async` で使う prompt template の実体（async_graphrag.rs:404-409）。spec-grag が日本語仕様で使う場合、このテンプレートは日本語化される必要があるが、現在は英語固定。
- `GraphRAG::ask_explained` の `query_analysis` が常に None で渡されるため、`ExplainedAnswer.query_analysis` を活用する経路が **無い**（外部から手動で詰める必要あり）。
- `confidence` 計算式 `(avg_score * 0.7 + 0.3).clamp(0, 1)` の妥当性。bias +0.3 が固定なので、結果が空の場合だけ 0、それ以外は最低でも 0.3 になる。

### D4 への寄与

**制約探索の応答性**：
- `hybrid_query` 経由なら章・節情報は `EnrichedRetriever::filter_by_structure` で取り出せる。`SearchResult.source_chunks` から chunk → metadata.chapter / metadata.section に辿れる前提。
- ExplainedAnswer は confidence / sources / reasoning_steps を提供 → 制約として「どの spec のどの章から何の制約を引いたか」を UI 表示する用途に流用可能。
- `hierarchical_query` で DocumentTree から summary / keywords / chunk_ids / level を取得可能 → 章単位（DocumentId 単位）の制約を取り出すには、**`hierarchical_query_grouped`（spike vendor のみ存在）か spec-grag 側でラップ追加が必要**。

**修正対象探索の応答性**：
- 課題プロンプト → 候補 chunk / entity を取得するには `hybrid_query`（adaptive_retrieval 経路）が使える。entity_centric_search で「課題に絡むエンティティ → 隣接エンティティ拡張」を 1 hop / 2 hop で行える。
- ただし **「ERG → Hierarchical Cluster」のクラスタ単位での traversal は現状の DocumentTree.query では不可**。Tree のノード親子を辿る `get_ancestors` / `get_descendants`（summarization/mod.rs:980-1000 付近）は存在するので、これを組み合わせて spec-grag 側で「ある leaf ノードから親方向に上る → 兄弟ノードも回収」のような設計をすれば階層対応可能。
- 修正対象の信頼度は `SearchResult.score` または `ExplainedAnswer.confidence` → そのまま使えるが、bias +0.3 の影響に注意。

### 設計判断への含意

- **ask_explained は spec-grag 用に再構築すべき**：confidence の +0.3 bias、reasoning_steps の 4 段階固定構造、query_analysis None 固定など、spec-grag の要件（制約 / 修正対象の根拠提示）に合わせて作り直す方が早い。`ExplainedAnswer` 構造体（retrieval/mod.rs:191-204）はそのまま流用可。
- **hierarchical_query は使えるが、章単位グルーピングが無い**：spec-grag 側で
    ```rust
    pub async fn hierarchical_query_grouped(
        &self, query: &str, max_results_per_doc: usize
    ) -> Result<Vec<(DocumentId, QueryResult)>>
    ```
  を 15 行程度で追加実装するのがコスト最小。spike vendor の実装が参考になる（`vendor/graphrag-rs-claude-spike/graphrag-core/src/async_graphrag.rs:336-353`）。
- **DocumentTree.query は階層的でない** → spec-grag が「Hierarchical Cluster からの絞り込み」を要求するなら、spec-grag 側で `tree.get_ancestors` / `tree.get_descendants` を組み合わせた depth-aware 検索を実装する。または `tree.nodes` に直接アクセスして level filter を行う。
- **answer_question の async_retrieval は naive すぎる** → spec-grag では `AsyncGraphRAG::answer_question` を使わず、自前で `RetrievalSystem::hybrid_query`（または HippoRAG / DualLevel）を呼んでから LLM 生成に渡すのが妥当。
- **ExplainedAnswer.query_analysis を埋める経路を spec-grag で作る** → 制約 / 修正対象の root cause を可視化するために、`ExplainedAnswer` を組み立てる際に `RetrievalSystem::analyze_query` の結果を入れる薄いラッパを spec-grag に置く。

---

## 親への報告に向けた要約（次のコンテキストで使う）

- M5: 完了。HybridRetriever / DualLevelRetriever / HippoRAGRetriever / CrossEncoder 全て実装行レベルで読了。
- M6: 完了。answer_question / hierarchical_query / ask_explained / DocumentTree.query 全て実装行レベルで読了。
- D4 根拠：揃った。
  - HippoRAG PPR：**実装あり**（`hipporag_ppr.rs` 441 行、`#[cfg(feature = "pagerank")]`）。ただし RetrievalSystem からは呼ばれず、利用者が組み立てる。
  - LightRAG DualLevel：**実装あり**、4 マージ戦略 (Interleave/HighFirst/LowFirst/Weighted)。high-level index を別途構築する必要。
  - Cross-Encoder rerank：**実装あり**（Candle BERT、neural-embeddings + huggingface-hub feature 必要）、フォールバックは passthrough。
  - HybridRetriever fusion：**RRF / Weighted / CombSum / MaxScore の 4 種**。CombMNZ / Linear は無し。
- 設計矛盾 1：spec-grag の HANDOFF.md は `hierarchical_query_grouped`（spike vendor のみ）を前提に書かれているが、Cargo.toml は通常 vendor を参照。
- 設計矛盾 2：`AdaptiveRetriever` と `query/intelligence.rs` は英語ハードコードのため日本語仕様文書では使えない。
- 設計矛盾 3：`DocumentTree.query` はフラット線形スキャンであり、Hierarchical Cluster の depth-aware 探索には不足。
