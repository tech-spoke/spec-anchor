# Agent 4 Phase 2 raw findings — Config / Examples / Embedding / Symbolic Anchoring

調査日: 2026-04-27
対象 vendor: `/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/`（commit 状態は親が把握）
対応する設計判断: D9（Embedding 注入）, D10（設定統合）, D5（Symbolic Anchoring 自前実装の要否）

ライセンス・出典: graphrag-rs（vendor 配下、Cargo.toml 参照）。本文書中の引用コードはすべて graphrag-rs 由来。

---

## 0. エグゼクティブサマリ（先に結論）

| 項目 | 結論 |
| --- | --- |
| Symbolic Anchoring | **実装済み**（`retrieval/symbolic_anchoring.rs` 600 行）。設定は `AdvancedFeaturesConfig.symbolic_anchoring`。`AsyncGraphRAG` 本体への配線は確認できず（`AsyncGraphRAG.async_retrieval` は単純な部分文字列マッチのデモ実装）。 |
| Dynamic Edge Weighting | **実装済み**（`KnowledgeGraph::dynamic_weight()` が `core/mod.rs:1006`、`pagerank_retrieval.rs::search_with_dynamic_weights` 経由で実利用）。設定は `AdvancedFeaturesConfig.dynamic_weighting`。 |
| Embedding 注入経路 (HANDOFF.md §4.11) | **AsyncGraphRAGBuilder には未着手**（builder fn は `language_model` のみ。`embedder` setter なし）。**ただし** `OllamaEmbedderAdapter`（AsyncEmbedder 実装）と `ServiceConfig::build_registry()` 経由の DI 登録は実装済み。spec-grag は registry 経由か、既存 builder を拡張する必要がある。 |
| HierarchicalConfig (`Config`) | 巨大な構造体（~2434 行の `config/mod.rs` 全体に分散）。spec-grag の `[sources]/[core]/[graph]/[llm]` 4 セクションは **直接マップ不可**。spec-grag 側で変換層を書く必要がある。 |
| 5 層 figment | `[Default → ~/.graphrag/config.toml → ./graphrag.toml → GRAPHRAG_* env]` の 4 層（README で「5 sources」と書かれているが builder override を 5 層目と数えている）。実装は `config/mod.rs:1616-1651`。 |
| Sectoral templates | 5 種（general / legal / medical / financial / technical）が `graphrag-core/templates/` に存在。中身は通常の TOML（structure は `Config`）。 |

---

## M9. HierarchicalConfig / Config 構造体定義

### 入力
- TOML / JSON / YAML ファイル（`Config::from_toml_file`, `load_config(path)`）
- 環境変数（`GRAPHRAG_OLLAMA_HOST` 等、prefix `GRAPHRAG_`）
- builder メソッド（`GraphRAGBuilder::with_*`, `TypedBuilder::with_*`）
- 直接構造体構築（`Config { ... }` または `Config::default()`）

### 出力
- `Config` 構造体（`graphrag-core/src/config/mod.rs:46-115`）
- これが `GraphRAG::new(config)`, `AsyncGraphRAG::new(config)`, `RetrievalSystem::new(&config)` 等に渡される

### 内部処理（要点、実装行レベル）

#### `Config` トップレベル（mod.rs:46-115）
- 出現順のフィールド一覧（網羅）：
  ```rust
  pub output_dir: String,
  pub chunk_size: usize,
  pub chunk_overlap: usize,
  pub max_entities_per_chunk: Option<usize>,
  pub top_k_results: Option<usize>,
  pub similarity_threshold: Option<f32>,
  pub approach: String,                         // "semantic" | "algorithmic" | "hybrid"
  pub embeddings: EmbeddingConfig,
  pub graph: GraphConfig,
  pub text: TextConfig,
  pub entities: EntityConfig,
  pub retrieval: RetrievalConfig,
  pub parallel: ParallelConfig,
  pub ollama: crate::ollama::OllamaConfig,
  pub gliner: GlinerConfig,
  pub enhancements: enhancements::EnhancementsConfig,
  pub auto_save: AutoSaveConfig,
  pub summarization: crate::summarization::HierarchicalConfig,  // ← 別物の HierarchicalConfig
  pub zero_cost_approach: ZeroCostApproachConfig,
  pub advanced_features: AdvancedFeaturesConfig,                 // ← Phase 2-3 の機能 OFF/ON
  pub suppress_progress_bars: bool,
  ```

#### サブ構造体の主要フィールド（mod.rs 全体から抜粋）

| 構造体 | 主要フィールド |
| --- | --- |
| `EmbeddingConfig` (mod.rs:951) | `dimension: usize`, `backend: String`（`"hash"\|"ollama"\|"huggingface"\|"openai"\|"voyage"\|"cohere"\|"jina"\|"mistral"\|"together"\|"onnx"\|"candle"`）, `model: Option<String>`, `fallback_to_hash: bool`, `api_endpoint`, `api_key`, `cache_dir`, `batch_size` |
| `GraphConfig` (mod.rs:994) | `max_connections`, `similarity_threshold`, `extract_relationships`, `relationship_confidence_threshold`, `traversal: TraversalConfigParams` |
| `TraversalConfigParams` (mod.rs:1017) | `max_depth`, `max_paths`, `use_edge_weights: bool`, `min_relationship_strength: f32` |
| `TextConfig` (mod.rs:1047) | `chunk_size`, `chunk_overlap`, `languages: Vec<String>` |
| `EntityConfig` (mod.rs:1060) | `min_confidence`, `entity_types: Vec<String>`, `use_gleaning`, `max_gleaning_rounds`, `enable_triple_reflection`, `validation_min_confidence`, `use_atomic_facts`, `max_fact_tokens` |
| `RetrievalConfig` (mod.rs:1248) | `top_k`, `search_algorithm: String` |
| `ParallelConfig` (mod.rs:1258) | `num_threads`, `enabled`, `min_batch_size`, `chunk_batch_size`, `parallel_embeddings`, `parallel_graph_ops`, `parallel_vector_ops` |
| `OllamaConfig` (ollama/mod.rs:163) | `enabled`, `host: String`, `port: u16`, `embedding_model: String` (default `"nomic-embed-text"`), `chat_model: String` (default `"llama3.2:3b"`), `timeout_seconds`, `max_retries`, `fallback_to_hash`, `max_tokens`, `temperature`, `enable_caching`, `keep_alive: Option<String>`, `num_ctx: Option<u32>` |
| `GlinerConfig` (mod.rs:118) | ONNX GLiNER 用。`enabled`, `model_path`, `tokenizer_path`, `mode`, `entity_labels`, `relation_labels`, `entity_threshold`, `relation_threshold`, `use_gpu` |
| `AutoSaveConfig` (mod.rs:163) | `enabled: bool`, `base_dir: Option<String>`, `interval_seconds: u64`, `workspace_name: Option<String>`, `max_versions: usize` |
| `HierarchicalConfig`（summarization/mod.rs:76、`Config.summarization` の型） | `merge_size: usize`, `max_summary_length: usize`, `min_node_size: usize`, `overlap_sentences: usize`, `llm_config: LLMConfig` |
| `LLMConfig` (summarization/mod.rs:91) | `enabled: bool`, `model_name: String` (default `"llama3.1:8b"`), `temperature: f32`, `max_tokens: usize`, `strategy: LLMStrategy` (`Uniform`\|`Adaptive`\|`Progressive`), `level_configs: HashMap<usize, LevelConfig>` |
| `AdvancedFeaturesConfig` (mod.rs:1098) | `symbolic_anchoring: SymbolicAnchoringConfig`, `dynamic_weighting: DynamicWeightingConfig`, `causal_analysis: CausalAnalysisConfig`, `hierarchical_clustering: HierarchicalClusteringConfig`, `weight_optimization: WeightOptimizationConfig` |
| `SymbolicAnchoringConfig` (mod.rs:1127) | `min_relevance: f32` (default 0.3), `max_anchors: usize` (default 5), `max_entities_per_anchor: usize` (default 10) |
| `DynamicWeightingConfig` (mod.rs:1143) | `enable_semantic_boost: bool`, `enable_temporal_boost: bool`, `enable_concept_boost: bool`, `enable_causal_boost: bool`（全 default true） |
| `CausalAnalysisConfig` (mod.rs:1163) | `min_confidence`, `min_causal_strength`, `max_chain_depth`, `require_temporal_consistency` |
| `HierarchicalClusteringConfig` (mod.rs:1183) | `num_levels`, `resolutions: Vec<f32>`, `min_cluster_size`, `generate_summaries` |
| `WeightOptimizationConfig` (mod.rs:1204) | `learning_rate`, `max_iterations`, `slope_window`, `stagnation_threshold`, `use_llm_eval`, `objective_weights: ObjectiveWeightsConfig` |

#### 3 つの設定方法

1. **TypedBuilder**（`builder/mod.rs:79-271`、type-state パターン）
   - `NoOutput/HasOutput`、`NoLlm/HasLlm` の状態を PhantomData で持ち、`build()` は `<HasOutput, HasLlm>` でのみ呼べる（コンパイル時検査）
   - 必須遷移：`with_output_dir(&str)`（NoOutput→HasOutput）
   - 必須遷移：`with_ollama() | with_ollama_custom(host,port,chat_model) | with_hash_embeddings() | with_candle_embeddings()`（NoLlm→HasLlm）
   - オプション：`with_chunk_size`, `with_chunk_overlap`, `with_top_k`, `with_similarity_threshold`, `with_approach`, `with_parallel`, `with_gleaning`, `config()`
   - 注意：埋め込みモデル名／次元の細かい指定は TypedBuilder には fn が **ない**（GraphRAGBuilder 側のみ）

2. **figment 階層 config** (`Config::load()`、mod.rs:1616-1651, feature `hierarchical-config`)
   - 公式 README は「5 sources」と書いているが、実装は 4 層 merge：
     1. `Serialized::defaults(Config::default())` （コード default）
     2. `~/.graphrag/config.toml` (`dirs::home_dir()` で取得、存在チェックあり)
     3. `./graphrag.toml` (cwd 直下、存在チェックあり)
     4. `Env::prefixed("GRAPHRAG_").split("_")` （`GRAPHRAG_OLLAMA_HOST` → `ollama.host` にマップ）
   - 5 層目はビルダーオーバーライド（README 記載、コード上は呼び出し側の責任）
   - 実装は `feature = "hierarchical-config"` 必須。Cargo.toml:182 で `hierarchical-config = ["figment", "dirs"]`。

3. **TOML 直接ロード** (`Config::from_toml_file<P>(path)`, mod.rs:1673)
   - `serde::Deserialize` で `Config` に直接デシリアライズ。templates の TOML はこの形式。

   それと別に `config/loader.rs::load_config(path)` がある（mod.rs ではなく loader.rs）。これは **完全に別系統** で、`RawConfig` → `Config::default()` ベースに一部だけマップする変換実装。コメントにも「config.text.chunk_size = chunk_size;」が **コメントアウト** されており、ほぼ未完成。spec-grag は使うべきでない（mod.rs:1673 の `from_toml_file` 一択）。

#### テンプレートの中身

`graphrag-core/templates/`（5 種）：

| ファイル | 主要差分 |
| --- | --- |
| `general.toml` | `approach="hybrid"`, `chunk_size=1000`, `embeddings.backend="hash"`, `entity_types=["PERSON","ORGANIZATION","LOCATION","DATE","EVENT"]`, `ollama.enabled=false` |
| `technical.toml` | `approach="algorithmic"`, `chunk_size=600`, `entity_types=["FUNCTION","CLASS","MODULE","API_ENDPOINT","PARAMETER","RETURN_TYPE","ERROR_TYPE","VERSION","DEPENDENCY","CONFIG_KEY","ENVIRONMENT_VAR","FILE_PATH","URL"]`, `graph.max_connections=20`, `traversal.max_depth=5` |
| `legal.toml` / `medical.toml` / `financial.toml` | （未実読、構造は同一と推測。entity_types とドメイン特化の閾値が中心） |

別途 `config/templates/` には `algorithmic_pipeline.toml`, `hybrid_pipeline.toml`, `semantic_pipeline.toml`, `narrative_fiction.toml`, `web_blog_content.toml`, `academic_research.toml`, `dynamic_universal.toml`, `enrichment_example.toml`, `legal_documents.toml`, `technical_documentation.toml` の 10 種があるが、これは `SetConfig`（config/setconfig.rs）系で別 schema。混乱しやすい。

### 典型 use case
- アプリ起動時: `let cfg = Config::load()?` で 4 層 merge → `let g = GraphRAG::new(cfg)?`
- spec-grag のように独自 TOML を持つ場合: `Config::default()` ベースでフィールドを上書きするか、自前 TOML → `serde_json::Value` → 必要部分だけ `Config` のフィールドに代入

### 他機能との連携
- `Config` は `RetrievalSystem::new(&config)`, `AsyncGraphRAG::new(config)`, `KnowledgeGraph::*`, `summarization::DocumentTree::new(.., config.summarization, ..)` 等に渡される根幹データ
- `OllamaConfig` は `OllamaClient::new(config)` および `OllamaLanguageModelAdapter::new(config)` でクライアント化される

### 実装ファイル
- `graphrag-core/src/config/mod.rs`（2434 行、構造体定義の中心）
- `graphrag-core/src/config/loader.rs`（旧式 RawConfig 経由 loader、ほぼ未完成）
- `graphrag-core/src/config/setconfig.rs`（別 schema の SetConfig）
- `graphrag-core/src/config/enhancements.rs`, `validation.rs`, `json5_loader.rs`, `schema_validator.rs`
- `graphrag-core/src/summarization/mod.rs:76-153`（`HierarchicalConfig`, `LLMConfig`）
- `graphrag-core/src/ollama/mod.rs:163-221`（`OllamaConfig`）
- `graphrag-core/templates/{general,legal,medical,financial,technical}.toml`
- `graphrag-core/Cargo.toml:180-238`（features: `hierarchical-config = ["figment", "dirs"]`）

### ライセンス・出典
- graphrag-rs（vendor 配下、ライセンスは vendor の LICENSE 参照）。

### 確認できなかった点
- legal / medical / financial.toml の中身（general / technical のみ実読）
- `setconfig.rs` の SetConfig vs `mod.rs` の Config の関係性（API として両立しているのか、片方が deprecated なのか）
- `from_toml_file` で **未知のキーがあるとエラーか黙殺か** —`serde` の default 動作だと黙殺（`#[serde(default)]` 多用）。spec-grag は spec-grag 独自セクションを持つので、ここは慎重に検証が必要

### D9/D10/D5 への寄与
- **D10 への直接的根拠**：
  - spec-grag の `[sources] [core] [graph] [llm]` は graphrag-rs の `Config` のセクション名と **一致しない**（graphrag-rs 側は `[embeddings] [graph] [text] [entities] [retrieval] [parallel] [ollama] [auto_save] [summarization] [advanced_features]` 等）。
  - spec-grag の `[llm]` は要約を Claude CLI / Codex CLI、埋め込みを Ollama に分離する想定だが、graphrag-rs は要約 LLM (`Config.summarization.llm_config`) と Ollama (`Config.ollama`) と embedding backend (`Config.embeddings.backend`) が **別フィールドに分散**。spec-grag は変換層が必要。
  - figment は `merge` ベースなので「spec-grag config + graphrag-rs config を別ファイルに」分けるのは可能だが、spec-grag 独自セクションをそのまま `Config` に流し込もうとすると serde の挙動次第（`#[serde(deny_unknown_fields)]` は付いていない）。

### 設計判断への含意
- spec-grag は `.spec-grag/config.toml` を **直接 `Config` にマップしない**で、SpecGragConfig（独自構造体）→ `Config` 変換関数を持つのが安全。
- TypedBuilder は埋め込みモデル名・次元を細かく指定できないため、要約 = Claude CLI、埋め込み = Ollama nomic-embed-text のような構成では **GraphRAGBuilder（runtime validation 版）か `Config` 直接構築** のほうが向く。
- 4 層 figment は spec-grag が `~/.graphrag/config.toml` を直接サポートしたいなら有用、不要なら独自 TOML loader で十分。

---

## M10. examples（multi_document_pipeline / 04_with_ollama / 05_batch_processing）

### 入力
- `multi_document_pipeline.rs`: `docs-example/Symposium.txt` と `docs-example/The Adventures of Tom Sawyer.txt`（テキストファイル）
- `04_with_ollama.rs`: ハードコードされた科学論文サンプル文字列、Ollama (`llama3.1:8b` + `nomic-embed-text`) ローカル起動前提
- `05_batch_processing.rs`: 4 つのハードコード文書（company_overview / product_lineup / financial_report / future_plans）

### 出力
- 各 example は標準出力にクエリ結果と統計を表示。`05_batch_processing.rs` は `./output/techvision_graph` に save_pipeline_state。

### 内部処理（要点、実装行レベル）

#### `multi_document_pipeline.rs`（735 行）
- **重要：これは graphrag-rs の API を一切使っていない `standalone` 実装**。ファイル冒頭にも graphrag-rs の use 文がない（`rayon` のみ依存）。
- 自前で `Document`, `Chunk`, `KnowledgeGraph`, `Entity`, `Relationship`, `QueryResult` を定義（35-101 行）
- 自前 hash_embedding（FNV-1a 442-491 行、384 次元 hash-TF + sublinear log + L2 norm）
- 自前 chunk_document（408-439 行、word-based、chunk_size=200, overlap=50）
- 自前 cosine_similarity（493-508 行）
- 自前 RRF（apply_rrf, 610-646 行、K=60）
- 大文字始まりの単語を頻度 2 以上で entity 化する単純実装（510-543 行）
- **示唆**：spec-grag の章ファイル群を「multi-doc」として処理するパターンは **graphrag-rs の AsyncGraphRAG.add_document を回す** 方が筋（このファイルの自前実装は参考にすべきでない）。

#### `04_with_ollama.rs`（147 行）
- 実コード抜粋（69-72 行）：
  ```rust
  let mut graphrag = GraphRAG::builder()
      .with_ollama()                         // Enable Ollama with defaults
      .with_text_config(600, 150)            // chunk_size: 600, chunk_overlap: 150
      .build()?;
  ```
- `add_document_from_text(scientific_text)` でテキストを 1 引数で投入
- `graphrag.ask(question)` で同期呼び出し
- **`with_text_config(600, 150)` は GraphRAGBuilder に存在するメソッドのはずだが、`builder/mod.rs` で grep した範囲では見当たらない**（`with_chunk_size` / `with_chunk_overlap` 別々のはず）。要確認。
- Ollama 統合の典型コード：`with_ollama()` を呼ぶだけで `OllamaConfig::default()` の `embedding_model="nomic-embed-text"` と `chat_model="llama3.2:3b"` が使われる。**ただし example の冒頭で「llama3.1:8b と nomic-embed-text」を pull しろと書いてあり、デフォルトとずれている**。

#### `05_batch_processing.rs`（216 行）
- 実コード抜粋（110-114 行）：
  ```rust
  let mut graphrag = GraphRAG::builder()
      .with_text_config(600, 100)
      .with_parallel_processing(true, Some(4))  // ← 引数 2 個だが builder/mod.rs は 1 個
      .auto_detect_llm()                         // ← builder/mod.rs に未定義
      .build()?;
  ```
- ループで各文書を `Document::new(DocumentId::new(...), name, content).with_metadata(...)` を作って `graphrag.add_document(document)?`
- `graphrag.ask(query)` で同期 Q&A
- `graphrag.save_pipeline_state("./output/techvision_graph")?` で永続化
- **`with_parallel_processing(bool, Option<usize>)` と `auto_detect_llm()` は `builder/mod.rs` で確認した API と一致しない**。examples は古い API を使っているか、別の builder impl がある可能性が高い。

#### `MULTI_DOCUMENT_PIPELINE.md`（example のドキュメント）
- 322 行付近に `let mut graph = AsyncGraphRAG::new(Config::default()).await?;` と書かれており、**ドキュメント上は AsyncGraphRAG が multi-doc の正解形**。

### 典型 use case
- spec-grag が章ファイル群を multi-doc として扱う：
  ```rust
  let mut graphrag = AsyncGraphRAGBuilder::new()
      .config(my_config)
      .with_async_ollama(ollama_config).await?
      .build().await?;
  for chapter_doc in chapters {
      graphrag.add_document(chapter_doc).await?;  // または add_documents_batch(vec)
  }
  graphrag.build_graph().await?;
  let answer = graphrag.answer_question(query).await?;
  ```
- ただし `AsyncGraphRAG.add_documents_batch` は内部で **逐次** 処理（async_graphrag.rs:412-426 のコメント「Process documents sequentially for now to avoid borrowing issues」）。並列度は出ない。

### 他機能との連携
- batch 処理は `answer_questions_batch(&[&str])` で `FuturesUnordered` 経由で並列クエリ可（async_graphrag.rs:429-443）。
- save 経由は `GraphRAG::save_pipeline_state(path)`（同期 API、05 example で使用）。AsyncGraphRAG は `save_state_async(path)`（async_graphrag.rs:481-503）。

### 実装ファイル
- `examples/multi_document_pipeline.rs`（735 行、standalone）
- `examples/04_with_ollama.rs`（147 行、`GraphRAG::builder().with_ollama()`）
- `examples/05_batch_processing.rs`（216 行、`with_parallel_processing(true, Some(4))` / `auto_detect_llm()`）
- `examples/MULTI_DOCUMENT_PIPELINE.md`（AsyncGraphRAG ベースの正解形を示すドキュメント）
- `examples/real_ollama_pipeline.rs`（OllamaClient + OllamaConfig + OllamaEmbeddings 直接利用、参考）
- `graphrag-core/src/builder/mod.rs:281-598`（`GraphRAGBuilder`）
- `graphrag-core/src/async_graphrag.rs:531-602`（`AsyncGraphRAGBuilder`）

### ライセンス・出典
- graphrag-rs `examples/`（vendor 配下）。Symposium / Tom Sawyer はパブリックドメイン。

### 確認できなかった点
- `with_text_config`, `with_parallel_processing(bool, Option<usize>)`, `auto_detect_llm()` の実体（`builder/mod.rs` には存在せず、別ファイルに定義されている可能性）
- `add_document_from_text(text)` の実体（`lib.rs` 確認すれば見つかると思われる）
- `multi_document_pipeline.rs` が **なぜ graphrag-rs を使わない自前実装** になっているのか（README とのギャップ。実装が unfinished の証拠かも）
- `AsyncGraphRAGBuilder.with_async_ollama(config)` の使用例（コード上は存在するが examples で使われていない）

### D9/D10/D5 への寄与
- **D9 へ**：04_with_ollama は `with_ollama()` 一発で「embedding+generation 両方を Ollama」というパターンを示唆。spec-grag のように「embedding=Ollama nomic-embed-text、generation=Claude CLI/Codex CLI」のように分離するパターンは **examples に存在しない**。spec-grag は独自に組まないとならない。
- **multi-doc へ**：MULTI_DOCUMENT_PIPELINE.md ドキュメントは `AsyncGraphRAG::new(Config::default())` を使うべきと示しているが、`multi_document_pipeline.rs` 本体は別実装。**正解形は AsyncGraphRAG**。

### 設計判断への含意
- spec-grag は **04_with_ollama を直接コピペ** しても「LLM 分離」ができない。`AsyncGraphRAGBuilder.language_model(...)` で **独自 BoxedAsyncLanguageModel（Claude CLI ラッパー）を渡す** 戦略が必要。
- multi-doc 投入は逐次 + 自前並列化が必要。`AsyncGraphRAG.add_documents_batch` を信用しない。
- examples 自体が古い API を引きずっているので、API 安定性に懸念あり。spec-grag は **AsyncGraphRAG（async） + Config 直接構築** を主軸に据えるのが安全。

---

## M11. Embedding 注入経路（HANDOFF.md §4.11 の地雷検証）

### 入力
- 埋め込みモデル名（例：`"nomic-embed-text"`）と次元（例：768）
- テキスト文字列または文字列バッチ

### 出力
- `Vec<f32>`（単一埋め込み）または `Vec<Vec<f32>>`（バッチ）
- AsyncEmbedder トレイトを通じて型消去された Service として登録

### 内部処理（要点、実装行レベル）

#### `EmbeddingProvider` trait（embeddings/mod.rs:27-45）
```rust
#[async_trait::async_trait]
pub trait EmbeddingProvider: Send + Sync {
    async fn initialize(&mut self) -> Result<()>;
    async fn embed(&self, text: &str) -> Result<Vec<f32>>;
    async fn embed_batch(&self, texts: &[&str]) -> Result<Vec<Vec<f32>>>;
    fn dimensions(&self) -> usize;
    fn is_available(&self) -> bool;
    fn provider_name(&self) -> &str;
}
```
- 実装：
  - `embeddings/ollama.rs`: `OllamaEmbeddings` (feature `ollama`)
  - `embeddings/api_providers.rs`: `HttpEmbeddingProvider`（OpenAI/Voyage/Cohere/Jina/Mistral/Together、feature `ureq`）
  - `embeddings/huggingface.rs`: HuggingFace Hub（feature `huggingface-hub`）
  - そのほか hash / candle / onnx / fastembed は別 crate / モジュール

#### `OllamaEmbeddings`（embeddings/ollama.rs:1-99）
- フィールド：`model: String`, `client: ollama_rs::Ollama`（default localhost:11434）, `dimensions: usize`（default 1024）
- `initialize`: `client.list_local_models()` で Ollama 接続確認
- `embed`: `ollama_rs::generation::embeddings::request::GenerateEmbeddingsRequest` を `EmbeddingsInput::Single(text)` で発行
- `embed_batch`: `embed` をループ呼び出し（**真のバッチ API ではない**、コメントで「Ollama currently processes one by one in the API wrapper usually」）
- 戻り値の `Vec<Vec<f64>>` を `Vec<f32>` に変換

#### `OllamaEmbedderAdapter`（core/ollama_adapters.rs:14-70）
- `EmbeddingProvider` 実装の `OllamaEmbeddings` を、より汎用な `AsyncEmbedder` trait（core/traits.rs:144）に変換するアダプタ
- フィールド：`embeddings: OllamaEmbeddings`, `dimension: usize`
- `OllamaEmbedderAdapter::new(model, dimension)` または `from_embeddings(OllamaEmbeddings, dimension)`
- 同じく `embed/embed_batch/dimension/is_ready` を実装（AsyncEmbedder trait 経由）

#### `AsyncEmbedder` trait（core/traits.rs:144）
- 型消去版：`BoxedAsyncEmbedder = Box<dyn AsyncEmbedder<Error = GraphRAGError> + Send + Sync>`（traits.rs:1447-1448）
- spec-grag が独自実装を渡すならこの trait を実装する。

#### AsyncGraphRAGBuilder の wiring（async_graphrag.rs:531-595）
**重要な事実**：
```rust
pub struct AsyncGraphRAGBuilder {
    config: Config,
    language_model: Option<Arc<BoxedAsyncLanguageModel>>,
    hierarchical_config: Option<HierarchicalConfig>,
}
```
- フィールドに `embedder: Option<Arc<BoxedAsyncEmbedder>>` が **ない**。
- メソッド一覧：
  - `new()`, `default()`
  - `config(Config)`
  - `language_model(BoxedAsyncLanguageModel)`
  - `hierarchical_config(HierarchicalConfig)`
  - `with_async_mock_llm()` (feature `async-traits`)
  - `with_async_ollama(OllamaConfig)` (feature `ollama`+`async-traits`)
  - `build() -> Result<AsyncGraphRAG>`
- → **AsyncGraphRAGBuilder には embedder を直接注入する API がない**。

#### AsyncGraphRAG 本体の embedder 利用
- `async_graphrag.rs:248-253` の `query()` は **embedder を呼ばない**：
  ```rust
  pub async fn query(&self, query: &str) -> Result<Vec<String>> {
      tokio::time::sleep(std::time::Duration::from_millis(10)).await;
      Ok(vec![format!("Async result for: {}", query)])
  }
  ```
- `async_retrieval()`（284-308 行）も embedder 不使用、単純な `chunk.content.contains(query)` の文字列検索。
- `extract_entities_async()`（222-245 行）はハードコードした名前（`["tom", "huck", "polly", "sid", "mary", "jim"]`）を返すデモ実装。
- → **AsyncGraphRAG は async_graphrag.rs 単体ではあくまで「async 版のスケルトン」で、embedder 経路はそもそも実装されていない**。HANDOFF.md §4.11 の指摘は **正しい**。

#### 代替経路：ServiceConfig::build_registry()（core/registry.rs:303-562）
**HANDOFF.md §4.11 の指摘の反証材料はここ**にある：
```rust
// 3. Embedding Provider
#[cfg(feature = "ollama")]
{
    if let Some(model) = &self.embedding_model {
        if let Some(dimension) = self.vector_dimension {
            use crate::core::ollama_adapters::OllamaEmbedderAdapter;
            let embedder = OllamaEmbedderAdapter::new(model.clone(), dimension);
            builder = builder.with_service(embedder);
        }
    }
}
```
- `ServiceConfig` フィールド（registry.rs:305-336）：
  ```rust
  pub ollama_base_url: Option<String>,
  pub embedding_model: Option<String>,        // ← embedder 用
  pub language_model: Option<String>,
  pub vector_dimension: Option<usize>,
  pub entity_confidence_threshold: Option<f32>,
  pub enable_parallel_processing: bool,
  pub enable_function_calling: bool,
  pub enable_monitoring: bool,
  ```
- `build_registry()` は `RegistryBuilder` を返し、その中に `Storage / VectorStore / EmbedderAdapter / EntityExtractor / Retriever / LanguageModel / MetricsCollector / FunctionRegistry` が DI される。
- → **embedder の DI 経路は ServiceRegistry 経由で存在する**。ただし `AsyncGraphRAG` がこの ServiceRegistry を使うかどうかは不明（async_graphrag.rs は ServiceRegistry を import していない）。両者は **別系統** の可能性が高い。

#### 同期 GraphRAG 側（lib.rs）
- `GraphRAG::initialize()`（lib.rs:344-360）は `RetrievalSystem::new(&config)` を呼ぶだけで、embedder の明示的な注入を見ていない。`Config.embeddings.backend` で内部分岐していると思われるが、`EmbeddingProvider` trait の dyn 注入は確認できず。
- spec-grag が `with_ollama()` で起動した場合、内部的に `Config.ollama.embedding_model` を読んで `OllamaEmbeddings` を作る経路は **register/RetrievalSystem の中** にあるはずだが、`async_graphrag` 直経路ではない。

### 典型 use case
- ServiceConfig 経由：
  ```rust
  let registry = ServiceConfig {
      ollama_base_url: Some("http://localhost:11434".into()),
      embedding_model: Some("nomic-embed-text".into()),
      vector_dimension: Some(768),
      ..Default::default()
  }.build_registry().build();
  let embedder = registry.get::<OllamaEmbedderAdapter>().unwrap();
  // 自前で AsyncGraphRAG にこの embedder を渡す経路は… 現状ない
  ```

### 他機能との連携
- AsyncEmbedder の利用先：retrieval / vector store / entity extractor で本来は使われるはずだが、AsyncGraphRAG 本体は呼ばない。

### 実装ファイル
- `graphrag-core/src/embeddings/mod.rs:27-45`（`EmbeddingProvider` trait）
- `graphrag-core/src/embeddings/ollama.rs`（`OllamaEmbeddings`、99 行）
- `graphrag-core/src/core/ollama_adapters.rs:14-70`（`OllamaEmbedderAdapter`）
- `graphrag-core/src/core/traits.rs:144, 1447-1448`（`AsyncEmbedder` trait + Boxed alias）
- `graphrag-core/src/core/registry.rs:303-562`（`ServiceConfig` + `build_registry`）
- `graphrag-core/src/async_graphrag.rs:531-595`（`AsyncGraphRAGBuilder` — embedder setter なし）
- `graphrag-core/src/embeddings/api_providers.rs`（OpenAI/Voyage/Cohere 等）

### ライセンス・出典
- graphrag-rs（vendor 配下）。

### 確認できなかった点
- `GraphRAG`（同期版）の中で `Config.embeddings.backend = "ollama"` を指定したとき、**実際にどこで** `OllamaEmbeddings` がインスタンス化されているか（lib.rs の initialize は明示していない）
- `RetrievalSystem::new(&config)` の内部で embedder factory がいるかどうか
- ServiceRegistry が AsyncGraphRAG とどう連携するか（あるいは独立しているか）
- spec-grag が AsyncGraphRAGBuilder に `embedder()` メソッドを追加する PR を出すか、自前で `BoxedAsyncEmbedder` を持つラッパーを書くか

### D9/D10 への寄与（特に D9）
- **HANDOFF.md §4.11「埋め込み経路が現状未着手」は AsyncGraphRAGBuilder レベルでは事実**。`AsyncGraphRAGBuilder` には `embedder` setter が **ない**。
- ただし反証材料として、`OllamaEmbedderAdapter` および `ServiceRegistry` 経由の DI 経路は **下回りのレイヤーには実装されている**。AsyncGraphRAG 本体がそれを使っていない。
- spec-grag が embedding を Ollama に固定するなら、選択肢は 3 つ：
  1. AsyncGraphRAGBuilder に `embedder(BoxedAsyncEmbedder)` を **vendor 修正** で追加
  2. ServiceRegistry を spec-grag 側でラップし、`KnowledgeGraph` を直接操作する自前パイプラインを書く（async_graphrag を使わない）
  3. 同期 `GraphRAG`（lib.rs）の `with_ollama()` 経路を使う（generation も Ollama になり、Claude CLI と分離できない欠点）
- **D9 結論**：「AsyncGraphRAG + 独自 BoxedAsyncEmbedder 注入」は vendor 修正が必要。一旦は spec-grag 側で thin wrapper を書いて、内部で `OllamaEmbedderAdapter` をフィールド保持する自前 GraphRAG ラッパーを作るのが現実的。

### 設計判断への含意
- HANDOFF.md §4.11 の警告通り、**AsyncGraphRAGBuilder にそのまま `with_ollama_embeddings()` のような fn を期待するのは誤り**。
- spec-grag のアーキテクチャは：
  - 埋め込み層：`OllamaEmbedderAdapter` を spec-grag 側で直接インスタンス化
  - 要約／生成層：`BoxedAsyncLanguageModel` を実装した「Claude CLI ラッパー」「Codex CLI ラッパー」を `AsyncGraphRAGBuilder.language_model(..)` に注入
  - 両者は AsyncGraphRAG の中で「並べて」使う必要があるが、現状の AsyncGraphRAG はそれを統合する API を持たない → spec-grag は AsyncGraphRAG を **直接使わず**、graphrag-core の下位コンポーネント（KnowledgeGraph, RetrievalSystem, OllamaEmbedderAdapter, summarization::DocumentTree）を **自前で組み合わせる** プレーンな pipeline を書くのが堅牢。

---

## M12. Symbolic Anchoring / Dynamic Edge Weighting の実装ファイル特定

### 入力（Symbolic Anchoring）
- ユーザクエリ文字列
- `KnowledgeGraph`（`SymbolicAnchoringStrategy::new(graph)`）
- 任意：`HashMap<EntityId, f32>` PageRank scores（`with_pagerank_scores`）
- 任意：min_relevance（default 0.3）, max_anchors（default 5）, max_entities_per_anchor（default 10）

### 入力（Dynamic Edge Weighting）
- `Relationship`（base weight = `relationship.confidence`）
- 任意：`Option<&[f32]>` query_embedding
- `&[String]` query_concepts

### 出力（Symbolic Anchoring）
- `Vec<SymbolicAnchor>` — concept とそれに grounded した entity ID 群、relevance_score 付き
- `boost_with_anchors(results, anchors)` で `Vec<SearchResult>` のスコアを乗法的にブースト

### 出力（Dynamic Edge Weighting）
- `f32` 動的重み（典型 0.0-2.0、強マッチで超過もあり）
- `pagerank_retrieval::search_with_dynamic_weights` ではこれを使って探索

### 内部処理（要点、実装行レベル）

#### Symbolic Anchoring（retrieval/symbolic_anchoring.rs、600 行）
- `SymbolicAnchor` struct（25-37 行）：`concept: String`, `grounded_entities: Vec<EntityId>`, `relevance_score: f32`, `embedding_similarity: Option<f32>`
- `SymbolicAnchoringStrategy::new(graph)` → `extract_anchors(query)`：
  1. `extract_concepts(query)` でクエリから concept 候補を抽出（187-250 行）。`["what is", "nature of", "meaning of", ...]` のようなパターンマッチ + 単純な大文字始まり単語抽出 + ハードコード concept リスト（`["love", "virtue", "justice", "truth", "beauty", "good", "evil", "knowledge", "wisdom", "courage", "philosophy", "ethics", "morality", "freedom", "happiness", "meaning", "purpose", "existence", "reality", "consciousness", "mind", "soul", "spirit", "nature", "essence"]`、255-281 行）。
  2. `ground_concept(concept)`（295-325 行）で `entity.name.contains(concept)` または `entity_type == "concept"` または relationship type マッチで entity を引っ張る。
  3. `calculate_relevance(anchor)`（331-362 行）で `count_score = (n/10).min(1.0)` と PageRank average を 40:60 で線形結合。
  4. min_relevance 以上を残し、relevance 降順 sort、max_anchors で truncate。
- `boost_with_anchors(results, anchors)`（374-440 行）：anchor の grounded_entities を逆引き map にして、SearchResult.entities にマッチした entity 数だけスコアをブースト（`result.score *= 1.0 + avg_boost`）。
- **コンセプトはシンプル**：完全な意味解析ではなく、ハードコード concept list + 文字列 contains での grounding。実用的には spec-grag の仕様文書には適さない可能性が高い（concept list がプラトン哲学的）。
- テストあり（512-600 行付近、`is_likely_concept`, `test_extract_anchors`, `test_boost_with_anchors` 等）。

#### Dynamic Edge Weighting（core/mod.rs:989-1051）
- `KnowledgeGraph::dynamic_weight(relationship, query_embedding, query_concepts)`：
  ```rust
  let base_weight = relationship.confidence;
  let semantic_boost = if let (Some(rel_emb), Some(query_emb)) =
      (relationship.embedding.as_deref(), query_embedding) {
      Self::cosine_similarity(rel_emb, query_emb).max(0.0)
  } else { 0.0 };
  let temporal_boost = relationship.temporal_range.map(|tr| Self::calculate_temporal_relevance(tr)).unwrap_or(0.0);
  let concept_boost = query_concepts.iter()
      .filter(|c| relationship.relation_type.to_lowercase().contains(&c.to_lowercase()))
      .count() as f32 * 0.15;  // 15% per matching concept
  let causal_boost = relationship.causal_strength.map(|s| s * 0.2).unwrap_or(0.0);
  base_weight * (1.0 + semantic_boost + temporal_boost + concept_boost + causal_boost)
  ```
- `calculate_temporal_relevance` は years_ago に応じて 0.05〜減衰の時間ブースト（mod.rs:973-987 周辺）
- 利用先：`retrieval/pagerank_retrieval.rs::search_with_dynamic_weights`（411-548 行）。query_embedding と query_concepts を取って、全 relationship に対して動的重みを計算し、`weighted_edges` map を構築 → PageRank 系の探索に使用 → 動的重みでさらに boost を加算。
- `optimization/graph_weight_optimizer.rs` には DW-GRPO（Dynamic Weighted Group Relative Policy Optimization）ベースの重み最適化が別途実装されている（heuristic）。

#### config 上の扱い
- `AdvancedFeaturesConfig` (mod.rs:1098) に `symbolic_anchoring`, `dynamic_weighting` フィールド：default ON。
- ただし `AsyncGraphRAG` 本体は `AdvancedFeaturesConfig` を **読まない**（async_graphrag.rs を grep しても `advanced_features` 参照なし）。
- 利用するには `RetrievalSystem` レベルで明示的に呼ぶか、`pagerank_retrieval::search_with_dynamic_weights` を直接呼ぶ必要がある。

### 典型 use case
```rust
// Symbolic Anchoring
let strategy = SymbolicAnchoringStrategy::new(&graph)
    .with_pagerank_scores(scores)
    .with_min_relevance(0.3)
    .with_max_anchors(5);
let anchors = strategy.extract_anchors("What is the nature of love?");
let boosted = strategy.boost_with_anchors(initial_results, &anchors);

// Dynamic Edge Weighting
let dyn_w = graph.dynamic_weight(&rel, Some(&query_embedding), &query_concepts);
```

### 他機能との連携
- Symbolic Anchoring は SearchResult スコアの後処理 boost
- Dynamic Edge Weighting は `pagerank_retrieval` と `optimization::graph_weight_optimizer` の中核
- 両者とも AsyncGraphRAG の async_retrieval からは呼ばれていない

### 実装ファイル
- `graphrag-core/src/retrieval/symbolic_anchoring.rs`（600 行、CatRAG 由来）
- `graphrag-core/src/retrieval/mod.rs:14-15`（`pub mod symbolic_anchoring`）
- `graphrag-core/src/core/mod.rs:989-1051`（`KnowledgeGraph::dynamic_weight`）
- `graphrag-core/src/retrieval/pagerank_retrieval.rs:411-548`（`search_with_dynamic_weights`）
- `graphrag-core/src/optimization/graph_weight_optimizer.rs`（DW-GRPO 風実装）
- `graphrag-core/src/config/mod.rs:1097-1160`（`AdvancedFeaturesConfig`, `SymbolicAnchoringConfig`, `DynamicWeightingConfig`）

### ライセンス・出典
- graphrag-rs（vendor 配下）。Symbolic Anchoring は CatRAG methodology 由来（symbolic_anchoring.rs:3 に明記）。

### 確認できなかった点
- `pagerank_retrieval::search_with_dynamic_weights` の呼び出し元（誰が `query_concepts` を抽出しているか）
- `AdvancedFeaturesConfig.symbolic_anchoring` を読み取る経路の実装（grep では config への参照しか見えなかった）
- Symbolic Anchoring が **日本語クエリ** で機能するか（`["love", "virtue", ...]` ハードコードリストは英語、日本語スペック仕様文書には不適と推測）

### D5（Symbolic Anchoring 自前実装の要否）への寄与
- **二値結論**：Symbolic Anchoring も Dynamic Edge Weighting も **graphrag-rs に実装済み**。spec-grag が「実装あり / なし」で迷う必要はない（実装あり）。
- ただし **spec-grag の用途では使えない可能性が高い**：
  1. `is_likely_concept` のハードコード concept list が哲学的（love, virtue, justice…）。仕様策定文書には合わない。
  2. concept extraction が英語パターンマッチ（"what is", "nature of"）。日本語仕様文書には機能しない。
  3. AsyncGraphRAG 本体に統合されておらず、spec-grag が下回りで `SymbolicAnchoringStrategy::new(&graph)` を直接呼ぶ必要がある。
- **採否判断**：
  - 「graphrag-rs の実装をそのまま使う」→ 動かない（言語ミスマッチ）
  - 「graphrag-rs の構造（trait, struct）を再利用 + concept extraction を自前で日本語対応」→ 妥当
  - 「完全に独自実装」→ 不要（base struct はそのまま使える）

### 設計判断への含意
- spec-grag は **「Symbolic Anchoring の構造は graphrag-rs から再利用、concept extraction は自前で日本語対応」** が現実解。
- Dynamic Edge Weighting は実装ロジックが言語非依存（cosine similarity, temporal range, causal strength）なので、**そのまま使える**。relationship.relation_type 文字列マッチの `concept_boost` だけ日本語化注意。
- AsyncGraphRAG ではなく `RetrievalSystem` または自前 pipeline で配線する。

---

## 全体まとめ・親への引き継ぎ要約

| ID | 結論 | 詳細セクション |
| --- | --- | --- |
| M9 | Config フィールド網羅完了。3 設定方法（TypedBuilder / figment 4 層 / TOML 直接）と templates 5 種を確認 | §M9 |
| M10 | examples の典型コードは確認したが、4 系統 (`with_text_config`, `with_parallel_processing`, `auto_detect_llm`, `add_document_from_text`) は builder/mod.rs で見当たらず別ファイル定義の可能性。multi_document_pipeline.rs は graphrag-rs 非依存の standalone | §M10 |
| M11 | **AsyncGraphRAGBuilder には embedder setter なし**（HANDOFF.md §4.11 裏付け）。ServiceRegistry には DI 経路あり（反証材料）。spec-grag は thin wrapper か vendor 修正が必要 | §M11 |
| M12 | **Symbolic Anchoring・Dynamic Edge Weighting ともに実装あり**（二値確定）。ただし英語ハードコード concept list で日本語仕様文書には機能しない可能性大 | §M12 |
| D9 | embedder 注入は vendor 修正 or 自前 wrapper の二択。短期は wrapper 推奨 | §M11 |
| D10 | spec-grag config.toml は graphrag-rs Config と直接マップ不可。SpecGragConfig→Config 変換層が必要 | §M9 |
| D5 | Symbolic Anchoring の構造体は再利用可、concept extraction は日本語化が必要 | §M12 |

主要な「設計に効く事実」：

1. `AsyncGraphRAGBuilder` は **embedder を受け取らない**。これは HANDOFF.md §4.11 の指摘通り。
2. Symbolic Anchoring / Dynamic Edge Weighting は **実装済みだが**、AsyncGraphRAG の `async_retrieval` ルートに **配線されていない**。実利用には `RetrievalSystem` 直叩き or 自前 pipeline。
3. `Config` の階層は spec-grag の 4 セクション（`[sources]/[core]/[graph]/[llm]`）と **直接マップしない**。変換層が必須。
4. examples は **API バージョン違い** が混在しており、最新仕様の真の正解は `AsyncGraphRAG` だが本体実装はまだスケルトン段階。

「絶対に守る原則」回答：
1. Symbolic Anchoring / Dynamic Edge Weighting → **実装あり**（grep 確証 + 該当ファイル実読 600+ 行）
2. Embedding 注入経路 → **AsyncGraphRAGBuilder には未実装**（HANDOFF.md 裏付け）／**OllamaEmbedderAdapter / ServiceRegistry 経由なら下回りに実装あり**（部分反証）
3. HierarchicalConfig フィールド → 全フィールド網羅した（§M9 表）
4. examples 要点 → 04 (`with_ollama`) 引用、05 (`with_parallel_processing`+`auto_detect_llm` の API ギャップ指摘）、multi_document_pipeline (standalone 実装の罠) を引用付きで提示
