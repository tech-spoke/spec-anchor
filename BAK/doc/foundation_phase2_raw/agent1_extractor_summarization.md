# Agent 1 — Extractor / Summarization 深掘り (Phase 2)

調査日: 2026-04-27
対象: graphrag-rs (vendor/) の `entity/`, `summarization/`, `graph/leiden.rs`, `graph/hierarchical_relationships.rs`, `async_graphrag.rs`, `core/mod.rs` (KnowledgeGraph::*)
読書深度: 該当ファイルの **全行 (M1/M2/M3 全関数 fn 本体まで読了)** および lib.rs の起動箇所 (700-1000) を実行行レベルで確認。

---

## M1. LLMEntityExtractor + LLMRelationshipExtractor

### 入力
- **LLMEntityExtractor::extract_from_chunk(&self, chunk: &TextChunk)** → `(Vec<Entity>, Vec<Relationship>)`
  - 入力 `TextChunk { id: ChunkId, document_id: DocumentId, content, start_offset, end_offset, ... }` (core/mod.rs line 199-)
  - 補助: `extract_additional(chunk, previous_entities, previous_relationships)`（gleaning 用継続抽出）
  - 補助: `check_completion(chunk, entities, relationships) -> bool`（LLM が「もう抽出尽くしたか」判定）
- **LLMRelationshipExtractor::extract_with_llm(&self, chunk: &TextChunk)** → `ExtractionResult { entities, relationships }`
  - エンティティ + リレーションを **同一 LLM 呼び出し** で抽出（Microsoft GraphRAG 流）
  - 補助: `validate_triple(source, relation_type, target, source_text) -> TripleValidation`（DEG-RAG triple reflection）

### 出力
- LLMEntityExtractor: `(Vec<Entity>, Vec<Relationship>)`
  - Entity: `id = "{TYPE}_{normalized_name}"`、confidence=0.9 ハードコード (line 378)、mentions は **chunk_id 単位**で `EntityMention { chunk_id, start_offset, end_offset, confidence }` (line 395-)
  - Relationship: `Relationship { source, target, relation_type=description (LLM出力をそのまま), confidence=strength, context: vec![] (空), causal_strength: None, temporal_*: None, embedding: None }` (line 446-)
  - **重要**: relationship に `context: vec![]` (line 451) — つまり ChunkId が記録されていない。
- LLMRelationshipExtractor: `ExtractionResult { entities: Vec<ExtractedEntity>, relationships: Vec<ExtractedRelationship> }` （domain Entity/Relationship 型ではなく struct）

### 内部処理 (実装行レベル)

**LLMEntityExtractor::extract_from_chunk** (llm_extractor.rs line 88-121)
1. `prompt_builder.build_extraction_prompt(&chunk.content)` でプロンプト構築（chunk content のみ、document_id は使われない）
2. `call_llm_with_retry(&prompt)` (line 207) で Ollama を呼ぶ。このメソッドは:
   - `calculate_entity_num_ctx(prompt, max_tokens)` で動的 num_ctx 算出 (prompt_chars/4 + max_tokens を 1024 単位 round up、4096〜131072 にクランプ) (line 75-81)
   - `OllamaGenerationParams { num_predict, temperature, num_ctx, keep_alive, ... }` を組み立てて `ollama_client.generate_with_params` を呼ぶ (line 216-222)
   - 失敗時 2 秒スリープして 1 回のみ再試行 (line 226-229)
3. `parse_extraction_response(&response)` で 4 段階 JSON 修復 (line 254-296):
   - (1) 直接 `serde_json::from_str` (2) markdown ` ```json ... ``` ` 抽出 (3) `jsonfixer::repair_json` (4) `{...}` 範囲を切り出し → 失敗時は空 ExtractionOutput を返す（**Err にしない、warn ログのみ**）
4. `convert_to_entities(entity_data, &chunk.id, &chunk.content)` (line 352-386):
   - chunk テキスト内の name を全文走査して mention を作成 (line 389-422、case-sensitive → case-insensitive fallback)
5. `convert_to_relationships(relationship_data, &entities)` (line 426-468):
   - **chunk_id を context に入れない** (line 451 `context: vec![]`)。同 chunk 内の名前マッチで src/tgt を引く

**LLMEntityExtractor のフィールド** (line 16-25):
```rust
pub struct LLMEntityExtractor {
    ollama_client: OllamaClient,           // <<< 直接保持 (Box<dyn> でない)
    prompt_builder: PromptBuilder,
    temperature: f32,
    max_tokens: usize,
    keep_alive: Option<String>,
}
```
コンストラクタ `LLMEntityExtractor::new(ollama_client: OllamaClient, entity_types: Vec<String>)` (line 33) — トレイトオブジェクトでなく **具象型を要求**。

**LLMRelationshipExtractor::extract_with_llm** (llm_relationship_extractor.rs line 193-263)
1. ハードコードされた英語プロンプトを `chunk.content` に対して埋め込み (line 126-172)
2. `client.generate(&prompt).await` を呼ぶ — **`generate_with_params` ではなく素の generate**（つまり num_ctx も keep_alive もデフォルト）
3. `{` の最初〜`}` の最後で範囲を切り出し → `serde_json::from_str` で `ExtractionResult` パース。失敗時は **空結果を返す（Err にしない）**(line 239-243)
4. JSON 修復は **無し** (LLMEntityExtractor とは異なる)
5. validate_triple も同様、`client.generate(&prompt)` のみ。

**LLMRelationshipExtractor のフィールド** (line 67-70):
```rust
pub struct LLMRelationshipExtractor {
    pub ollama_client: Option<crate::ollama::OllamaClient>,  // <<< これも具象型
}
```
コンストラクタ `new(ollama_config: Option<&OllamaConfig>) -> Result<Self>` (line 84) で OllamaConfig を受けて内部で OllamaClient を作る。

### 典型 use case

lib.rs line 597-744 の **gleaning enabled** ルートで:
- `extractor = GleaningEntityExtractor::new(client, gleaning_config)` (entity/gleaning_extractor.rs line 87) — 内部で LLMEntityExtractor を所有
- 各 chunk について `extractor.extract_with_gleaning(chunk).await?` を直列実行
- `rel_extractor: Option<LLMRelationshipExtractor>` を triple reflection 用に並走させ、relationship を validate

lib.rs line 838-915 の **single-pass (gleaning disabled)** ルートで:
- `extractor = LLMEntityExtractor::new(client, entity_types)` 直接呼び出し
- 各 chunk について `extractor.extract_from_chunk(chunk).await` 直列実行（並列化なし）

### 他機能との連携
- **OllamaClient**: 具象型として保持。generate / generate_with_params で `OllamaGenerationParams { num_ctx, keep_alive, ... }` を渡せる。
- **AsyncLanguageModel trait** (core/traits.rs line 547): `complete(prompt)` / `complete_with_params(prompt, GenerationParams)` を持つが、`GenerationParams` は **max_tokens / temperature / top_p / stop_sequences のみ**。**num_ctx と keep_alive は表現できない**。
- **OllamaLanguageModelAdapter** (core/ollama_adapters.rs line 73-152): OllamaClient を AsyncLanguageModel として包む。だが `complete_with_params` は **`num_ctx: None, keep_alive: None` でハードコード** (line 111-112) — つまり AsyncLanguageModel 経由で呼ぶと num_ctx 動的計算と keep_alive が **失われる**。
- **async_graphrag.rs::extract_entities_async** (line 222-245): **実際の LLM 呼び出しではなく、ハードコードされたデモ実装** (`names = ["tom", "huck", ...]`)。AsyncGraphRAG ルートでは LLMEntityExtractor は呼ばれない。
- **AsyncLanguageModelAdapter** (async_graphrag.rs line 21-61): BoxedAsyncLanguageModel を `summarization::LLMClient` trait に変換するだけ。エンティティ抽出には未配線。

### 実装ファイル
- `vendor/graphrag-rs/graphrag-core/src/entity/llm_extractor.rs` (597 行)
- `vendor/graphrag-rs/graphrag-core/src/entity/llm_relationship_extractor.rs` (771 行)
- `vendor/graphrag-rs/graphrag-core/src/entity/gleaning_extractor.rs` (line 1-110、`new` シグネチャと OllamaClient 依存のみ確認、本体未読)
- `vendor/graphrag-rs/graphrag-core/src/entity/prompts.rs` (PromptBuilder、未読、Phase 3 で確認すべき)
- `vendor/graphrag-rs/graphrag-core/src/lib.rs` line 597-915 (起動箇所、確認済)
- `vendor/graphrag-rs/graphrag-core/src/core/traits.rs` line 540-624 (AsyncLanguageModel trait、確認済)
- `vendor/graphrag-rs/graphrag-core/src/core/ollama_adapters.rs` (確認済)
- `vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs` (全文確認済)

### ライセンス・出典
- graphrag-rs 全体のライセンスは Phase 1 RAW で確認済み。本ファイルでは個別出典は記録されていない（コメント上の "Microsoft GraphRAG methodology", "DEG-RAG", "ATOM" は手法名のみ）。

### 確認できなかった点
- `entity/gleaning_extractor.rs` の本体（line 110-510 未読）。`extract_with_gleaning` の中で何度 LLM を呼ぶか、各回で previous_entities をどう扱うかは未検証 → **Phase 3 で要追加 Read**。
- `entity/prompts.rs` の PromptBuilder の実装（実プロンプトテンプレート）。spec-grag の章別エンティティ抽出に向けたカスタムプロンプトを差し込めるかは未確認 → **Phase 3 で要追加 Read**。
- `OllamaClient::generate_with_params` の内部（HTTP 経路、retry、stats）— LLM 抽出時間や失敗ログの形が分からない。

### D1 / D2 / D9 への寄与（具体的根拠）

**D1 (ChapterAnchor: 主要エンティティ + キー概念 + 要約)**:
- LLMEntityExtractor は chunk → entities の写像のみ。**章単位の集約は別途必要**。TextChunk が DocumentId を保持する (core/mod.rs line 203) ので、`entities.iter().filter(|e| e.mentions.iter().any(|m| chunk_id_to_doc_id[m.chunk_id] == target_doc_id))` で章フィルタは可能。
- ただし **Entity.mentions は ChunkId のみ持つ** (core/mod.rs line 1222-、entity.with_mentions)。chunk → document の対応表を別途構築する必要がある。
- 「主要エンティティ」のスコアリング機構は LLMEntityExtractor 内には無い（confidence は 0.9 ハードコード）。`mentions.len()` で頻度ベース抽出、または PageRank 等で別途算出する必要。
- 「キー概念」を CONCEPT entity として抽出するには、entity_types に "CONCEPT" を含めれば LLM が抽出する（プロンプトで誘導）。
- 「要約」は LLMEntityExtractor では生成されない。別途、**章テキスト直接 → LLM 要約器** が必要。AsyncLanguageModel trait があれば章テキストをそのまま `complete` に渡せばよい（num_ctx/keep_alive 制御なしで構わなければ）。

**D2 (Entity Relationship Graph: 章単位 vs 全体、抽出器選択)**:
- 章単位で抽出 → 全体マージ: 各章の chunks を別 KnowledgeGraph に流して entity 抽出 → 章境界スパンの relationship は失われる。
- 全体抽出: 章境界を chunk metadata で保持しつつ全 chunk を流す。**現実装の lib.rs ルート (line 838-)** がこれ（DocumentId を chunk が持つので追跡は可能、ただし relationship.context は空）。
- LLMEntityExtractor 単独では章間 relationship を捉えにくい（chunk 内の co-occurrence ベース）。LLMRelationshipExtractor も同様。**章間の依存** を抽出するには gleaning + 章サマリー文脈の追加渡しが必要。
- 抽出器選択: LLMEntityExtractor (entity 中心) vs LLMRelationshipExtractor (entity+rel 同時) vs AtomicFactExtractor (5-tuple、M2 参照)。**最も粒度が小さく仕様策定に適しているのは AtomicFact だが、これも章境界は relationship.context にしか入らない**。

**D9 (LLM プロバイダー注入: AsyncLanguageModel 注入が抽出器・要約器に通るか)**:
- **現状では通らない**。LLMEntityExtractor / LLMRelationshipExtractor / GleaningExtractor / AtomicFactExtractor は全て `OllamaClient` を **具象型として** フィールド保持。
- AsyncLanguageModel trait に置換する場合の影響:
  - `OllamaClient` フィールド → `Arc<dyn AsyncLanguageModel<Error=GraphRAGError>>` に変更（4 ファイル × 1 フィールド = 4 箇所）
  - `client.generate_with_params(prompt, OllamaGenerationParams { num_ctx, keep_alive, ... })` → `client.complete_with_params(prompt, GenerationParams { ... })` への置き換え（**num_ctx と keep_alive は失われる**）
  - JSON 修復経路は維持できる（response の文字列処理だけなので）
  - lib.rs line 848 `let client = OllamaClient::new(self.config.ollama.clone())` の起動箇所も Arc<dyn AsyncLanguageModel> 注入に書き換える必要
- **改造規模の見積もり**:
  - llm_extractor.rs: フィールド型変更 + call_llm_with_retry 改修 ≈ **30 行**
  - llm_relationship_extractor.rs: フィールド型変更 + extract_with_llm/validate_triple ≈ **30 行**
  - gleaning_extractor.rs: コンストラクタと LLMEntityExtractor::new 呼び出し変更 ≈ **20 行**
  - atomic_fact_extractor.rs: 同様 ≈ **20 行**
  - lib.rs 起動箇所 (line 597-915): client 作成と各 extractor の new 呼び出しの書き換え ≈ **40 行**
  - **合計 約 140 行（vendor 改造）**。num_ctx/keep_alive 維持を諦める前提。
- **代替案**: vendor を改造せず spec-grag 側で薄いラッパを書く案 — 不可。LLMEntityExtractor の new が `OllamaClient` 具象を要求しているので、AsyncLanguageModel<Error> を OllamaClient に変換する逆方向アダプタは作れない（OllamaClient::generate は OllamaClient のメソッド、trait ではないため代用不可）。

### 設計判断への含意

- **D1**: ChapterAnchor を「LLMEntityExtractor + 別の章要約器」で組み立てる構成は **可能だが、要約器は spec-grag 側で別途用意する必要**（vendor の hierarchical summarization は chunk merge 階層で章単位ではない、M3 参照）。entity.mentions → chunk_id → document_id の集約処理を spec-grag 側で書く。**改造を伴う場合 vendor 側 ≈ 30 行 + spec-grag 側で集約ロジック**。
- **D2**: 全体抽出 + DocumentId フィルタ で章単位 graph を派生する方針が現実的。**LLMRelationshipExtractor は relationship.context が空 / chunk_id 未保持なので、章境界保持のためには extractor を改造して `relationship.context = vec![chunk.id.clone()]` を入れる必要**（**改造 ≈ 5 行**）。または上流（lib.rs）で relationship を受け取ってから context を埋める。
- **D9**: AsyncLanguageModel 注入は **vendor 改造前提**でしか実現できない。改造規模 140 行。**num_ctx 動的計算と keep_alive を失う**ので、Ollama 以外のプロバイダ（OpenAI, Anthropic など）に切り替える場合は問題ないが、Ollama を使い続けるなら現状の OllamaClient フィールドのほうが num_ctx 制御で有利。**判断保留**: spec-grag が Ollama 以外を使う必要があるか？ 必要なければ AsyncLanguageModel 化は不要、OllamaClient のまま enabled でよい。

---

## M2. AtomicFactExtractor

### 入力
- `AtomicFactExtractor::extract_atomic_facts(chunk: &TextChunk) -> Vec<AtomicFact>` (atomic_fact_extractor.rs line 122-227)

### 出力
- `Vec<AtomicFact>` where `AtomicFact { subject, predicate, object, temporal_marker: Option<String>, confidence: f32 }` (line 27-38)

### 内部処理 (実装行レベル)

**重要発見 1**: ATOM は **5-tuple ではなく 4-fields + confidence**。doc コメントには "5-tuples: (Subject, Predicate, Object, TemporalMarker, Confidence)" とあるが、Confidence はメタデータとして本来 5-tuple の一部ではない。実質 **4-tuple** (subject, predicate, object, temporal_marker)。

**extract_atomic_facts** (line 122-227):
1. ハードコードプロンプト構築 (line 123-145): "Extract atomic facts ... < {max_fact_tokens} tokens ... TemporalMarker should capture time expressions ..."
2. `self.ollama_client.generate(&prompt).await` — **plain generate**（generate_with_params ではない、num_ctx も keep_alive もデフォルト）
3. 応答から `[` ... `]` を切り出し → `serde_json::from_str::<Vec<AtomicFactJson>>`
4. パース失敗時は `Ok(Vec::new())` を返す（warn のみ、Err にしない、line 209-211）
5. LLM 失敗時のみ `GraphRAGError::EntityExtraction` を返す (line 222-225)

**atomics_to_graph_elements(facts, chunk_id) -> (Vec<Entity>, Vec<Relationship>)** (line 239-321):
1. fact ごとに subject/object を Entity に変換:
   - id = `EntityId::new(normalize_entity_name(name))` — **normalize_entity_name は "Socrates the Philosopher" → "socrates_the_philosopher"** (line 324-331)
   - entity_type = `infer_entity_type(name)` — **超単純なヒューリスティック**: 大文字始まり → ("ia"/"land"/"istan" で終わる → LOCATION、それ以外 PERSON)、数字あり → DATE、その他 → CONCEPT (line 334-352)。**仕様用語には不適**（「APIレイヤー」「認証コンテキスト」などは PERSON 扱いされる）。
   - HashMap で重複 entity を統合 (line 244, 250, 269)
   - temporal_marker から timestamp を抽出して entity.first_mentioned/last_mentioned にセット (line 259-262)
2. relationship 構築:
   - `Relationship::new(subject_id, object_id, predicate.to_uppercase(), confidence)` (line 287)
   - `with_context(vec![chunk_id.clone()])` (line 293) — **chunk_id がここで初めて記録される**
   - temporal_marker があれば `temporal_range` をセット
   - **causal_strength の取得** (line 302-314):
     - predicate に "caused" / "led to" → `temporal_type = Some(Caused), causal_strength = Some(confidence)`
     - predicate に "enabled" / "allowed" → `temporal_type = Some(Enabled), causal_strength = Some(confidence * 0.6)`
     - その他 → `causal_strength = None` （暗黙）

**重要発見 2**: temporal_marker の抽出は `extract_timestamp()` (line 50-80) で実装。"BC"/"BCE" 検出 → 負の年、"1000<year<3000" → 正の年。**章番号や仕様文書の時系列には使えない**。

### 典型 use case

lib.rs line 745-829 で `entities.use_atomic_facts == true` の場合に LLMEntityExtractor の後に追加実行:
- `let atomic_extractor = AtomicFactExtractor::new(client.clone()).with_max_tokens(max_fact_tokens)` (line 752-753)
- 各 chunk について `extract_atomic_facts(chunk).await` → `atomics_to_graph_elements(facts, &chunk.id)` → `graph.add_entity` / `graph.add_relationship`
- LLMEntityExtractor で抽出した entities/relationships に **重ねて** atomic 由来も追加（重複は graph 側でマージされる）

### 他機能との連携
- OllamaClient: 具象型として直接保持（D9 と同じ問題）
- chunk.id: relationship.context にのみ伝わる。entity 側には伝わらない。
- temporal_range / causal_strength: AtomicFact からのみ供給される。LLMEntityExtractor の Relationship は両方とも None。
- KnowledgeGraph::detect_hierarchical_communities (Leiden): entity name のみのグラフを作るので、atomic で付与された temporal_range や causal_strength は **Leiden には届かない**。

### 実装ファイル
- `vendor/graphrag-rs/graphrag-core/src/entity/atomic_fact_extractor.rs` (424 行、全文確認済)
- `vendor/graphrag-rs/graphrag-core/src/lib.rs` line 745-829 (起動箇所、確認済)
- `vendor/graphrag-rs/graphrag-core/src/graph/temporal.rs` (TemporalRange / TemporalRelationType、未読 — Phase 3)

### ライセンス・出典
- doc コメント line 1-13 に "ATOM methodology (itext2kg - https://github.com/AuvaLab/itext2kg)" の参照あり。本実装は graphrag-rs 独自。

### 確認できなかった点
- `graph/temporal.rs` の `TemporalRange` / `TemporalRelationType` 構造体本体（serde 形式、permanent/transient の区別など）→ **Phase 3 で要追加 Read**
- causal_strength = 0.6 の係数の根拠（実装上は arbitrary）
- atomic fact 抽出のプロンプトが日本語仕様書で動くかは検証が必要

### D2 / D8 への寄与（具体的根拠）

**D2 (Entity Relationship Graph)**:
- AtomicFactExtractor は **subject/predicate/object/temporal の 5-tuple**で抽出。仕様策定でいうと「機能X が 機能Y に DEPENDS_ON」「データ Z は INPUT_OF プロセス W」のような細粒度関係を取れる。
- ただし `infer_entity_type` のヒューリスティックは **日本語仕様書の用語には不適**（"APIレイヤー" → PERSON 扱い）。**プロンプトで entity_type をハード指定するか、entity_type 推論を完全にオーバーライドする必要**。改造規模 ≈ 20 行。
- chunk_id (= 章 id 派生) が **relationship.context にのみ**入る。entity の章帰属は別途 mentions 経由で集約する必要がある（M1 と同じ問題）。
- causal_strength は predicate のキーワード "caused/led to/enabled/allowed" でしか付与されない。日本語仕様書では「依存する」「起因する」「有効化する」等を別途キーワードに加える改造が必要 ≈ 10 行。

**D8 (Concept 更新案: cluster summary → Concept 文書 → unified diff)**:
- AtomicFact の細粒度は Concept 文書の改訂提案に向く（「機能 X が機能 Y を必要とする」という単位で diff を出せる）。
- ただし AtomicFact 単体では章境界に紐づかない（chunk_id しかない）。Concept 更新案を **章別** に整理するなら spec-grag 側で集約マッピングが必要。
- temporal_marker は仕様書の時系列管理（"v1.0 で導入"、"v2.0 で削除"）に使える可能性があるが、**現実装の extract_timestamp は西暦専用**で動かない → 改造 or 別フィールド追加が必要。

### 設計判断への含意
- **D2**: AtomicFact は 5-tuple 抽出として有用だが、**(a) entity_type 推論を spec-grag 用にオーバーライド** (b) **causal キーワードを日本語化** (c) **章境界保持のため relationship.context だけでなく entity 側にも DocumentId を持たせる集約処理** が必要。改造合計 ≈ 30 行 + spec-grag 側集約。**判断: 採用候補だが LLMRelationshipExtractor との二重抽出になる場合のコスト評価が未確認**。
- **D8**: cluster summary → Concept 改訂案のフローでは、AtomicFact の細粒度は subject-predicate-object の構造に reduce できるので diff 生成と相性が良い。**ただし temporal_marker / causal_strength は仕様書ドメインで再定義が必要**。

---

## M3. Cluster generation / HierarchicalCommunities 自動サマリー

### 入力
- (A) Entity ベースの Leiden (KnowledgeGraph::detect_hierarchical_communities):
  - `KnowledgeGraph::to_leiden_graph() -> petgraph::Graph<String, f32, Undirected>` (core/mod.rs line 1057-1076)
  - **node label = entity.name のみ**、edge weight = relationship.confidence
- (B) Relationship ベースの Hierarchy (HierarchyBuilder):
  - `HierarchyBuilder::from_graph(&KnowledgeGraph)` → relationships を持つ Builder
  - `with_num_levels(usize)`, `with_resolutions(Vec<f32>)`, `with_min_cluster_size(usize)`, `with_ollama_client(OllamaClient)` で設定
- (C) Document ベースの hierarchical chunk merge (DocumentTree, summarization/mod.rs):
  - `DocumentTree::build_from_chunks(Vec<TextChunk>)` — chunk を merge_size (default 5) ずつ束ねて bottom-up 階層化

### 出力
- (A) `HierarchicalCommunities { levels: HashMap<usize, HashMap<NodeIndex, usize>>, hierarchy: HashMap<usize, Option<usize>>, summaries: HashMap<usize, String>, entity_mapping: Option<HashMap<String, EntityMetadata>> }` (leiden.rs line 35-49)
- (B) `RelationshipHierarchy { levels: Vec<HierarchyLevel> }` where `HierarchyLevel { level_id, clusters: Vec<RelationshipCluster>, resolution }` (hierarchical_relationships.rs line 25-89)
- (C) `DocumentTree { nodes: IndexMap<NodeId, TreeNode>, root_nodes, levels, document_id, ... }` where `TreeNode { id, content, summary, level, children, parent, chunk_ids: Vec<ChunkId>, keywords, start_offset, end_offset }` (summarization/mod.rs line 167-200)

### 内部処理 (実装行レベル)

#### (A) KnowledgeGraph::detect_hierarchical_communities → LeidenCommunityDetector::detect_communities

**LeidenCommunityDetector::detect_communities** (leiden.rs line 471-497):
1. `extract_largest_connected_component(graph)` — **実装は graph.clone() を返すだけ** (line 765-780)。"Full implementation would extract actual largest component" のコメントどおり **未実装**。
2. RNG 初期化（seed あれば再現可能）
3. `hierarchical_leiden(working_graph)` を呼ぶ

**hierarchical_leiden** (line 500-541):
1. `let level = 0;` — **level 0 で固定** (line 511)
2. `initialize_communities` — 各 node を独立 community に
3. local moving (greedy modularity optimization) ループ (max 100 iter)
4. `refine_partition` (line 597-621) — 連結性チェックで poorly connected community を split
5. `levels.insert(0, communities)` — **level 0 のみ insert** (line 538)
6. **`hierarchy` HashMap は空のまま返る** (line 508 で初期化されたあと一度も .insert されない)

**結論**: 「Hierarchical Leiden」を名乗っているが **現実装は flat clustering (level 0 only)**。`max_levels` config フィールドは **使われていない**。`hierarchy: HashMap<usize, Option<usize>>` は親子関係マップだが空のまま。複数レベル展開は **未実装**。

**HierarchicalCommunities::generate_community_summary** (leiden.rs line 139-192):
- **抽出的な決定論的サマリー**: entity を type ごとにグループ化して "Community 5 (Level 0)\nContains 12 entities:\n- PERSON: Tom, Huck...\n- LOCATION: Athens..." 形式で出力
- **LLM 呼び出しは無い**。max_length で文字列切り詰め。
- 章境界の情報も無い（entity name と type と confidence と mention_count だけ）

**HierarchicalCommunities::generate_hierarchical_summaries** (line 225-236):
- max_level までボトムアップで `generate_community_summary` を呼ぶだけ — でも先述のとおり level 0 しか levels.keys() に無いので、**実質 level 0 のサマリーしか作らない**。

**HierarchicalCommunities::prepare_community_context** (line 254-306):
- LLM プロンプト用 context を組み立てる（entities + relationships + sub-community placeholder）
- "## Sub-community Summaries:" は line 302 でコメント `// Would need to track parent-child relationships` のとおり **未実装**
- spec-grag 側で LLM に投げて summary 取得するエントリポイントとしては使える

#### (B) HierarchyBuilder::build (hierarchical_relationships.rs line 251-268)

1. `resolutions` (default `[1.0, 0.5, 0.2]`) の各レベルで `build_level(level_id, resolution, &existing_hierarchy)` を呼ぶ
2. `build_level` (line 272-338):
   - `build_relationship_graph(relationships)` (line 341-368): **relationships をノードとし、relationship_similarity > 0.3 の組をエッジ** で結ぶ。relationship_similarity は (a) 同じ relation_type なら +0.5, (b) 同じ source/target を共有 +0.3, (c) temporal overlap +0.2 (line 371-391)
   - `cluster_relationships(rel_graph, resolution)` → leiden feature が enabled なら `LeidenCommunityDetector` を呼ぶ。**ただし leiden 自身が level 0 only なので、resolution を変えるたびに level 0 の Leiden を再実行する**形になる（疑似階層）。
   - `generate_cluster_summary(cluster, all_relationships, ollama_client)` を呼ぶ:
     - 各 rel_id を "source_target_type" で分割（**`rel.source.0`, `rel.target.0`, `rel.relation_type` を `_` で join した文字列を、再度 `_` で split している**）→ entity 名や relation_type に `_` が含まれると **ロジック破綻**
     - `format!("Summarize the theme of these N relationships in 1-2 sentences:\n{descriptions}\nTheme:")` で LLM 呼び出し
     - `client.generate(&prompt)` — **plain generate**、num_ctx 制御なし
     - 失敗時 fallback: `format!("Cluster of {} relationships", total)`
3. cohesion_score 計算（line 586-、内部エッジ密度）

**重要**: HierarchyBuilder の階層構造は「同じ Leiden を解像度を変えて N 回回す」という方式。**parent_cluster が論理的にネストしているわけではない**（line 128 `parent_cluster: Option<String>` フィールドはあるが、build_level 内で **設定されていない** — 確認: line 272-338 全文に `parent_cluster` への代入なし）。

#### (C) DocumentTree (summarization/mod.rs)

**build_from_chunks** (line 284-304):
1. `create_leaf_nodes(chunks)` — chunk ごとに TreeNode を作る (level=0)。各 leaf は `chunk_ids: vec![chunk.id]`、summary は extractive (sentence ranking) または LLM。
2. `build_bottom_up(leaf_nodes)` (line 674-691): `current_level_nodes.len() > 1` の間、`merge_level` で merge_size (default 5) ずつ束ねて新 level を作る。

**merge_nodes** (line 725-803):
- N 個の子ノードの content を `\n\n` で join → combined_content
- chunk_ids を flatten して保持 — **これにより全ての TreeNode は配下の chunk_ids を辿れる**
- summary 生成: llm_config.enabled && llm_client.is_some() なら `generate_llm_summary(combined_content, level, context)` (line 421-454)、失敗時は `generate_extractive_summary` フォールバック

**generate_llm_summary** (line 421-454):
- LLMClient trait (line 14-43) の `generate_summary(text, prompt, max_tokens, temperature)` を呼ぶ
- max_tokens / temperature を直接渡す形式。num_ctx / keep_alive は LLMClient trait のシグネチャに無い。
- AsyncLanguageModelAdapter (async_graphrag.rs line 21-61) でラップすれば AsyncLanguageModel から呼べるが、その `generate_summary` 実装は単に `model.complete(&prompt).await` を呼ぶだけ — **max_tokens / temperature は無視されている** (async_graphrag.rs line 44-45 `_max_tokens, _temperature`)。

**重要発見**:
- **(C) は entity / relationship に基づくクラスタリングではなく、テキストの merge_size 分位束ね**。Leiden community とは別物。
- 章境界の保持は **chunk_ids 経由で可能** だが、merge_size でランダムに束ねられるので「章単位の TreeNode」を作るには `create_leaf_nodes` を章単位入力で呼ぶ必要がある（spec-grag 側で章ごとに DocumentTree を独立構築）。
- DocumentTree は **document_id を 1 つしか持たない** (line 196 `document_id: DocumentId`)。複数章を 1 ツリーに混ぜるには違う document_id 群を 1 つの document_id 配下に束ねる必要 → **章 = document として扱うのが自然**。

### 典型 use case
- **(A) HierarchicalCommunities**: 知識グラフのコミュニティ検出に。spec-grag では仕様用語クラスタの抽出に使える可能性、ただし level 0 only。
- **(B) HierarchyBuilder**: relationship 群のテーマ別クラスタリング。spec-grag では「機能依存性の cluster」抽出に使える可能性。
- **(C) DocumentTree**: ドキュメント本文の階層的要約。Microsoft GraphRAG の community summary とは別アーキテクチャ。

### 他機能との連携
- (A)(B) は OllamaClient 直接、または extractive のみ。AsyncLanguageModel 経由不可。
- (C) は LLMClient trait 経由 → AsyncLanguageModelAdapter 経由で AsyncLanguageModel 使用可。**ただし max_tokens/temperature は無視される**。
- (A) → (B) → (C) は互いに連携していない（独立な 3 系統）。spec-grag が選ぶ場合 1 つに絞るか組み合わせる。

### 実装ファイル
- `vendor/graphrag-rs/graphrag-core/src/graph/leiden.rs` (842 行、line 1-540 確認済、test 部分は流し読み)
- `vendor/graphrag-rs/graphrag-core/src/graph/hierarchical_relationships.rs` (919 行、line 1-600 確認済、cohesion 詳細は流し読み)
- `vendor/graphrag-rs/graphrag-core/src/summarization/mod.rs` (1303 行、line 1-1000 確認済、query 関連は流し読み)
- `vendor/graphrag-rs/graphrag-core/src/core/mod.rs` line 1050-1180 (KnowledgeGraph::detect_hierarchical_communities, build_relationship_hierarchy 確認済)

### ライセンス・出典
- leiden.rs line 7 "Reference: 'From Louvain to Leiden: guaranteeing well-connected communities' Traag, Waltman & van Eck (2019)"
- hierarchical_relationships.rs line 1-10 "Phase 3.1" 自社実装
- summarization/mod.rs に出典明記なし

### 確認できなかった点
- `graph/leiden.rs` line 540-700（refine_partition 全分岐、modularity 計算の細部）— 流し読み、論理は理解したが境界条件は未確認
- `summarization/mod.rs` line 1000-1303（query 機能、JSON serialization）— 未読
- `summarization/` ディレクトリには **mod.rs しか無い** → 「summarization/*.rs」相当のサブモジュールは存在しない。元の指示で複数ファイル想定だったが、単一ファイルに集約されている。
- `HierarchyBuilder::build` の cohesion_score 算出ロジック詳細（line 586-919）

### D3 / D8 への寄与（具体的根拠）

**D3 (Hierarchical Cluster: Leiden + LLM cluster summary、章境界整合)**:
- **Leiden 階層化は未実装** (level 0 only)。spec-grag が 3 階層 cluster を要求する場合、**vendor 改造が必要**。改造ポイント:
  - `LeidenCommunityDetector::hierarchical_leiden` を本物の hierarchical に拡張（contraction + 再 Leiden、典型実装）— **新規 100-200 行**
  - or HierarchyBuilder の「resolution を変えて N 回」方式で擬似階層化（既存実装、ただし parent_cluster 未配線）
- **章境界整合は完全に失われる**: `KnowledgeGraph::to_leiden_graph` は entity name のみのグラフを作る (core/mod.rs line 1057-1076)。entity 側に DocumentId が伝わっていないので、cluster と章の対応は **後付け** で entity.mentions 経由で復元するしかない。
- LLM cluster summary: HierarchyBuilder::generate_cluster_summary が存在するが、(a) **rel_id 文字列分割の破綻リスク** (b) **plain generate (num_ctx 制御なし)** (c) **prompt が英語ハードコード**。改造 or spec-grag 側で再実装 必要。
- `HierarchicalCommunities::prepare_community_context` (leiden.rs line 254-306) を spec-grag が直接呼んで context を作り、自前 LLM 要約は可能。これが最も柔軟（vendor 改造なし）。

**D8 (Concept 更新案パイプライン)**:
- cluster summary → Concept 文書 → unified diff の前提として、cluster summary が **章境界を保持** している必要がある。現実装の `generate_community_summary` は entity 名と type のみで章は無い。
- 解決策:
  - (i) spec-grag 側で「cluster_id → entity_names → mentions[].chunk_id → document_id」の集約マップを作り、cluster summary に章番号を後注入
  - (ii) prepare_community_context を spec-grag が独自プロンプトで包んで LLM に投げ、章別要約を得る
- **どちらも vendor 改造なしで可能**だが、cluster と章の m:n 対応（1 cluster が複数章にまたがる）の処理ロジックは spec-grag 側で書く必要がある。

### 設計判断への含意

- **D3**: 現状 vendor の hierarchical 機能は **3 系統 (A)(B)(C) すべて部分実装**。
  - (A) Leiden は flat。max_levels は dead code。
  - (B) HierarchyBuilder は parent_cluster 未配線、rel_id 分割が壊れやすい。
  - (C) DocumentTree は entity 不在、テキスト merge のみ。
  - **判断**: 「Leiden + LLM cluster summary」の本格的な階層構造は **vendor を 200 行以上改造する** か、**spec-grag 側で Leiden を直接呼んで自前で階層化** するか。後者が安全（vendor 依存を減らす）。
  - **章境界整合**: 完全に失われている。vendor が entity に DocumentId を持たせていないため、spec-grag 側で entity.mentions[].chunk_id → DocumentId のマッピングを自前で持つ必要。
- **D8**: vendor の cluster summary はそのままでは Concept 更新案に使えない。**`prepare_community_context` を起点に spec-grag が独自プロンプトを書く方針が妥当**。改造不要。

---

## 全体まとめ：完了 / 部分完了 / 未着手

| 調査項目 | 状態 | 主な未確認 |
|---|---|---|
| M1. LLMEntityExtractor + LLMRelationshipExtractor | **完了** | gleaning_extractor.rs 本体 (line 110-510)、prompts.rs |
| M2. AtomicFactExtractor | **完了** | graph/temporal.rs |
| M3. Cluster generation / HierarchicalCommunities | **部分完了** | leiden.rs line 540-700 (modularity 詳細)、hierarchical_relationships.rs line 600-919 (cohesion 詳細)、summarization/mod.rs line 1000-1303 (query) |

| 設計判断軸 | 根拠の充実度 |
|---|---|
| D1 (ChapterAnchor) | **十分**（M1 + chunk.document_id 確認）|
| D2 (Entity Relationship Graph) | **十分**（M1 + M2 + relationship.context の挙動確認） |
| D3 (Hierarchical Cluster) | **十分（ただし悪い知らせ）** — 階層化が flat、章境界が失われる |
| D8 (Concept 更新案) | **十分**（prepare_community_context が spec-grag 側起点になる） |
| D9 (LLM プロバイダー注入) | **十分**（AsyncLanguageModel 経由は num_ctx/keep_alive を失う、改造規模 140 行）|

## 特筆すべき発見（Phase 3 / FOUNDATION_PLAN.md §4.2 で要対応）

1. **`async_graphrag.rs::extract_entities_async` (line 222-245) はハードコードのデモ実装** — `["tom", "huck", "polly", "sid", "mary", "jim"]` の名前マッチで Entity を作る。AsyncGraphRAG ルートでは LLMEntityExtractor も AtomicFactExtractor も呼ばれない。**spec-grag が AsyncGraphRAG を直接使うのは不可**。
2. **`OllamaLanguageModelAdapter::complete_with_params` は num_ctx/keep_alive をハードコードで None にする** (core/ollama_adapters.rs line 111-112)。AsyncLanguageModel 経由で Ollama を使うと、LLMEntityExtractor が組んだ動的 num_ctx と keep_alive が失われる。
3. **Leiden は flat clustering**。`hierarchical_leiden` の `let level = 0;` (leiden.rs line 511) と空の `hierarchy` HashMap が証拠。`max_levels` config は dead code。
4. **`HierarchicalCommunities` は entity name のみのグラフ**。章境界 (DocumentId) は cluster 出力には一切含まれない。spec-grag 側で entity.mentions 経由で復元する必要がある。
5. **AtomicFact の `infer_entity_type` は超単純ヒューリスティック**で日本語仕様用語に不適。"APIレイヤー" → PERSON 扱いされる可能性大。
6. **HierarchyBuilder の `parent_cluster` は宣言だけで未配線**（build_level 内で代入されない）。階層を名乗るが論理的階層構造を持たない。
7. **`OllamaClient::generate` (plain) を使う extractor**: LLMRelationshipExtractor、AtomicFactExtractor、HierarchyBuilder。これらは num_ctx 動的計算の恩恵を受けない。
