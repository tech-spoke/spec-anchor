# SPEC-grag 詳細設計書

本書は SPEC-grag の **詳細設計** を定義する。外部契約は [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md)（source of truth）で定義され、本書はその実装側を扱う：

- 技術選定の経緯と判断
- 確定したノード型・エッジ型のスキーマ
- アーキテクチャ（三層分業）
- 整合性チェック方針
- 採らない案とその理由

外部契約（コマンド体系、設定ファイル、出力契約、エラー契約）は EXTERNAL_DESIGN.ja.md に従い、本書では繰り返さない。

---

## 1. 議論の流れ

### Phase 1: 当初構成（Rust + graphrag-rs）

最初の方針は次だった。

```text
language    : Rust
backend     : graphrag-rs（vendor 同梱、--depth 1 clone）
LLM 要約    : Claude CLI（subprocess 経由、AsyncLanguageModel trait 実装）
embedding   : Ollama nomic-embed-text
storage     : .spec-grag/graph/ にローカル永続化
配布        : バイナリ 1 個
```

`vendor/graphrag-rs/graphrag-core/src/generation/claude_cli.rs`（240 行、新規）と `AsyncGraphRAG::with_async_claude_cli()` の vendor 拡張、`spec-grag` CLI スケルトン（main.rs / config.rs / commands/ / excitation.rs）まで作った。約 700 行の Rust 実装。

詳細は `BAK/HANDOFF.md` §1.3〜§1.7 に保管。

### Phase 2: graphrag-rs の限界が判明

Phase 2 の深掘り調査（4 並列 Agent + raw 4 ファイル合計 1784 行）で次が判明した。

**プレースホルダ実装が多数**:

- `AsyncGraphRAG::extract_entities_async`（async_graphrag.rs:222-245）は `["tom", "huck", "polly", "sid", "mary", "jim"]` の名前マッチで Entity を作る Tom Sawyer デモ実装
- `AsyncGraphRAG::async_retrieval`（line 284-308）は最初 3 chunks を `chunk.content.contains(query)` で文字列マッチするだけの naive スタブ
- `Lazy Propagation::apply_update`（lazy_propagation.rs:470-477）は本体が空、`Ok(())` を返すだけ
- `Async Batching::process_single_operation`（async_batch.rs:536-564）は全 OperationType が `Ok(())` を返すだけ
- `AdaptiveRetriever`（adaptive.rs）の呼び出し先（vector_search / graph_search / bm25_search / public_hierarchical_search）は **全部スタブ**、ハードコード文字列を返すだけ
- `query/{advanced_pipeline, analysis, expansion, multi_query, ranking_policies}.rs` は **全て 1 行のスタブ**
- `DocumentTree::query`（summarization/mod.rs:914-939）は **フラット線形スキャン**、parent/child を辿らない

**英語ハードコード多数**:

- `query/intelligence.rs::QueryIntelligence` は QueryType 判定を `query.contains("who is")` 等の英語キーワードで実装
- `query/adaptive_routing.rs::QueryComplexityAnalyzer` は `query.matches(" and ")` 等の英語前提
- `Symbolic Anchoring`（retrieval/symbolic_anchoring.rs）の `is_likely_concept` は `["love", "virtue", "justice", "truth", "beauty", ...]` というプラトン哲学的概念をハードコード

**examples が API バージョン違い**:

- `04_with_ollama.rs` の `with_text_config(600, 150)`、`05_batch_processing.rs` の `with_parallel_processing(true, Some(4))` / `auto_detect_llm()` / `add_document_from_text(...)` は `builder/mod.rs` に**存在しない**
- `multi_document_pipeline.rs` は **graphrag-rs を一切使わない standalone 実装**（rayon のみ依存）

**章境界の消失**:

- `KnowledgeGraph::to_leiden_graph` は entity name のみのグラフを作るため、章境界（DocumentId）が cluster 出力に**一切含まれない**
- `LeidenCommunityDetector::hierarchical_leiden` は `let level = 0;` でハードコード、**flat clustering のみ**。`max_levels` config フィールドは dead code

**LLM プロバイダー注入の制約**:

- `LLMEntityExtractor` / `LLMRelationshipExtractor` / `GleaningEntityExtractor` / `AtomicFactExtractor` はすべて `OllamaClient` を**具象型として直接保持**。trait 化されていない
- `OllamaLanguageModelAdapter::complete_with_params`（ollama_adapters.rs:111-112）は `num_ctx: None, keep_alive: None` でハードコード。AsyncLanguageModel 経由で Ollama を呼ぶと、LLMEntityExtractor の動的 num_ctx 計算と keep_alive 制御が**失われる**
- AsyncLanguageModel 化の vendor 改造規模 ≈ 140 行、しかも num_ctx / keep_alive を犠牲にする

**Phase 2 の結論**:

graphrag-rs は **「上位ファサード API（AsyncGraphRAG）が未完成、下位コンポーネントは実装済み」** というライブラリで、spec-grag が使うには：

- AsyncGraphRAG / AsyncGraphRAGBuilder は **使えない**
- 下位コンポーネント（KnowledgeGraph, LLMEntityExtractor, RetrievalSystem, LeidenCommunityDetector, WorkspaceManager）を**直接組み合わせる**プレーン pipeline を spec-grag が自前で書く必要がある
- 章境界保持・3 階層 cluster・意味的 ConflictNotes 検出・Concept 更新案 unified diff・章別永続化・日本語向け QueryAnalyzer などは **spec-grag 独自実装**（推定 14 件）
- vendor 改造（Hierarchical Leiden 200 行、AsyncLanguageModel 化 140 行）も条件付きで必要

詳細は `BAK/doc/GRAG_FOUNDATION.md`（827 行）と `BAK/doc/foundation_phase2_raw/`（4 ファイル）に保管。

### Phase 3: GPT 合議で代替候補を評価

graphrag-rs を続けるか切り替えるかの判断のため、GPT との合議で次の候補を評価した。

| 候補 | ライセンス | 安定性 | 仕様書解析向き |
|---|---|---|---|
| Microsoft GraphRAG | MIT | 中 | 中〜高（ただし demonstration 扱い）|
| LlamaIndex PropertyGraphIndex | MIT | 高 | 高 |
| LightRAG | MIT | 中 | 中（POC 向け、本番は要検証）|
| Fast GraphRAG | MIT | 中 | 中（マネージド誘導色）|
| nano-graphrag | MIT | 低〜中 | 低〜中（教材向け）|
| Neo4j GraphRAG | Apache 2.0 | 高 | 高（情報量最大）|
| graphrag-rs | MIT | 低（プレースホルダ多数）| Phase 2 で限界判明 |

**情報量の観点**（公式 docs + サンプル + 記事 + コミュニティ + 既存パターン）では Neo4j エコシステム圧勝：

- neo4j-graphrag-python（first-party）は KG Builder / Pipeline / API Documentation を公式に持つ、長期メンテナンス保証
- LlamaIndex PropertyGraphIndex は Neo4j を Property Graph Store として使う公式 notebook あり
- 日本語情報も Neo4j + LangChain で豊富（Qiita 記事多数）

ただし、**spec-grag の運用要件は別問題**：

- 1 開発者が複数プロジェクトを並行管理する想定
- 各プロジェクトに `.spec-grag/graph/` がある
- ローカル開発環境前提（仕様書の機密性のためクラウド非推奨）

Neo4j Community Edition は **standard database を 1 個しか持てない**（Enterprise でないと自由に複数 DB 切れない）。複数プロジェクトを並行管理する spec-grag のモデルとは噛み合わない。

→ **Neo4j を default にしない、optional adapter にする**判断。

### Phase 4: 何を保持するかのスキーマ議論

ノード型・エッジ型を実例（`/home/kazuki/public_html/ec-spoke.local/docs/React+NestJS+Astro/`）から逆引きしながら確定した。

**最初の提案の誤り（私の現状維持バイアス）**:

私は最初に GPT 提案 9 ノード型（Chapter / Section / Requirement / Constraint / Concept / Decision / OpenQuestion / Conflict / ImplementationTarget）に加え、ec-spoke.local 由来の Layer / Component / API / DataStructure / Action / Hook / Pattern / TechStack / Feature / Persona を spec-grag 標準に組み込もうと提案した。

ユーザーの指摘により次が判明：

1. **抽象度の混在**: Chapter / Section は文書の物理構造、Requirement / Constraint / Concept / Decision / Conflict は意味的内容。同レベルで並べるのは構造的に間違い。LlamaIndex の ChunkNode / EntityNode 分離と整合させるべき
2. **B-3 システム実装タイプは ec-spoke.local 専用**: Layer / Component / API / DataStructure / Action / Hook / Pattern / TechStack / Feature / Persona は EC / Web フロントエンド系の語彙であり、spec-grag 標準に入れると別ドメイン（金融、医療、ゲーム、研究、契約等）で使えなくなる
3. **標準スキーマだけで EXTERNAL_DESIGN の本来目的は満たせる**: Tier 2 / 3 / ユーザー拡張を最初から積むのは「最適化欲」で本来目的を超える

GPT の整理を全面採用：

- **2 層構造**（文書構造ノード + 意味要素ノード）の分離
- **SourceSpan を文書構造に追加**（行範囲、`[26:1263-1289]` のような行参照付き根拠の表現）
- **Rationale / Alternative を意味要素標準に昇格**（Decision のプロパティではなく独立ノード型、graph 探索で柔軟）
- **HAS_EVIDENCE を grounding 系標準 Relation に追加**
- **SUPPORTS / ALTERNATIVE_TO / RELATED_TO を semantic 系標準 Relation に追加**
- **IMPLEMENTS は project custom に降格**（技術寄りすぎ、研究計画書や業務企画書には合わない）
- **Phase / RejectedItem / SupersededItem は decision_process 拡張に分離**（議論ログ寄り、汎用必須ではない）
- **TakeDown を SupersededItem / RejectedItem に汎用名化**
- **「Section は必ず 1 つ以上の意味要素を参照」を 0 個以上に緩和**（前置き / 目次的節 / 補足節は意味要素を持たないことが正常）

---

## 2. 最終方針

### 2.1 採用スタック

```text
language     : Python
backend      : LlamaIndex PropertyGraphIndex
graph store  : SimplePropertyGraphStore（ローカル、ファイルベース）
extractor    : SchemaLLMPathExtractor（ノード型・関係型を制約）
embedding    : Ollama nomic-embed-text（または OpenAI 互換、設定で切替）
LLM 要約・生成: Claude CLI / Codex CLI（spec-grag が直接保持、subprocess 呼び出し）
storage      : .spec-grag/graph/ にローカル永続化
optional     : Neo4jPropertyGraphStore adapter（拡張として将来追加可）
```

### 2.2 Core Schema（spec-grag 標準、ドメイン非依存、増やさない）

```toml
[schema.core.entities]
document_structure = [
  "Document",
  "Section",
  "SourceSpan",     # 行範囲（[26:1263-1289] 等）の根拠粒度
]
semantic = [
  "Concept",
  "Requirement",
  "Constraint",
  "Decision",
  "OpenQuestion",
  "Conflict",
  "Rationale",      # 独立ノード型、複数 Decision で共有可
  "Alternative",    # 独立ノード型、ALTERNATIVE_TO で Decision に紐付け
]

[schema.core.relations]
structure = [
  "CONTAINS",       # Document → Section、Section → Section
]
grounding = [
  "MENTIONS",       # Section → 意味要素（弱参照）
  "DEFINES",        # Section → 意味要素（その節が定義主体）
  "HAS_EVIDENCE",   # 意味要素 → SourceSpan（行参照付き根拠）
]
semantic = [
  "DEPENDS_ON",
  "CONSTRAINS",
  "REFINES",
  "SUPERSEDES",
  "CONFLICTS_WITH",
  "SUPPORTS",       # 意味要素 → 意味要素（弱依存、根拠としての支持）
  "ALTERNATIVE_TO", # Alternative → Decision
  "RELATED_TO",     # 弱関連（型が定まらない参照）
]
```

**Section の意味要素参照ポリシー**:

「Section は 0 個以上の意味要素を参照する。ただし主要節は最低 1 つの Anchor または Summary を持つ」。前置き / 目次的節 / 補足節は意味要素を持たないことが正常。

### 2.3 Optional Extensions（spec-grag 標準で提供、`.spec-grag/config.toml` で有効化）

```toml
[schema.extensions]
enabled = ["decision_process"]

[schema.extensions.decision_process.entities]
items = [
  "Phase",          # 議論段階
  "RejectedItem",   # 採用しなかった案（Alternative より明確に「却下された」もの）
  "SupersededItem", # 旧版（_old.md など、SUPERSEDES の対象）
]
```

議論プロセスを記録する文書（技術選定経緯、ADR、設計判断記録）でのみ有効化する。一般的な業務要件定義書では不要。

### 2.4 Project Custom Schema（spec-grag 標準には含めない、各プロジェクトが定義）

各プロジェクトが自分のドメイン語彙を `.spec-grag/schema.toml` で定義する。spec-grag 本体には含めない。

ec-spoke.local の例（参考、§4 で詳述）:

```toml
[schema.custom.entities]
items = [
  "Layer",
  "Component",
  "API",
  "DataStructure",
  "Action",
  "Hook",
  "Pattern",
  "TechStack",
  "Feature",
  "Persona",
]

[schema.custom.relations]
items = [
  "IMPLEMENTS",
  "USES_TECH",
  "COMPOSED_OF",
  "CALLS",
  "EXPOSES",
  "TARGETS_PERSONA",
]
```

別プロジェクトでは別の語彙：

- 金融システム → `BusinessRule` / `Account` / `Transaction` / `RegulatoryRequirement` / `RiskClassification`
- 医療システム → `ClinicalProtocol` / `Diagnosis` / `Medication` / `PatientPathway`
- 論文執筆 → `Hypothesis` / `Experiment` / `Result` / `RelatedWork` / `Limitation`
- ゲーム企画 → `GameMechanic` / `Character` / `Level` / `Progression` / `Monetization`
- 契約仕様 → `Party` / `Obligation` / `Right` / `Term` / `Condition` / `Penalty`

spec-grag 本体は **ドメイン非依存**を保つ。

### 2.5 アーキテクチャ（三層分業）

```text
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
│  spec-grag CLI（Python、独立スクリプト）               │
│  - .spec-grag/config.toml + schema.toml 読み込み       │
│  - GRAG オーケストレーション                           │
│  - 2 系統 pipeline（制約探索 / 修正対象探索）           │
│  - 階層 ranking（Purpose > Concept > Source spec）     │
│  - 章別永続化（chapter_index、concept_index）          │
│  - InjectionContext を Markdown / JSON で出力          │
└──────────────────┬─────────────────────────────────────┘
                   │ Python API
                   ↓
┌────────────────────────────────────────────────────────┐
│  LlamaIndex（プリミティブ）                            │
│  - PropertyGraphIndex / SimplePropertyGraphStore        │
│  - SchemaLLMPathExtractor / VectorStoreIndex            │
│  - HybridRetriever / Cross-Encoder                     │
└────────────────────────────────────────────────────────┘
```

責務の境界が重要：

- **クエリ生成は Agent (LLM) の責務**（Agentic search で動的抽出）。spec-grag CLI は受け取った動的キーワードで GRAG 検索を**実行する**側
- **2 系統 pipeline は CLI の責務**（受け取った動的キーワードでオーケストレーション）
- **LlamaIndex は「プリミティブ」のみ**（ファサード API を信用しすぎない、Phase 2 で graphrag-rs に同じ罠があった教訓）

### 2.6 整合性チェック方針（3 段階パイプライン）

LLM 抽出を完全信用しない。EXTERNAL_DESIGN.ja.md §5.4 ConflictNotes（制約 vs 修正対象 / Source spec 同士 / Concept vs Source spec）の検出を 3 段階で実装する：

```text
1. グラフ構造ベース（決定論的、優先）:
   - conflicts_with エッジが既に存在するか
   - 同じ概念に対して違う Definition が存在
   - supersedes チェーンに循環があるか
   - 同じ Component に違う DataModel で writes している relationships
   - 同じ API endpoint に違う Schema を持つ

2. ルールベース（決定論的、補助）:
   - Purpose の制約条項と Source spec の対立量化詞
     （「必ず」⇔「任意」、「全て」⇔「一部」）
   - sources_scanned_through より新しい修正と古い章の食い違い
   - Required と Optional の同時指定

3. LLM 推論（補助、最後）:
   - 上記 1, 2 で疑わしい候補のみ LLM で意味的妥当性確認
   - LLM 単独では発火しない、必ず構造的根拠とセット
```

LLM は最後の検証段階で、構造的に検出済みの候補に対する補助としてのみ使う。

---

## 3. 採らない案

### 3.1 graphrag-rs (Rust) を維持し、独自実装で覆い被せる

- 14 件の独自実装と 340 行の vendor 改造が必要
- プレースホルダ実装（apply_update / process_single_operation）に依存できない
- 英語ハードコードを 500 行規模で覆い被せる必要
- examples が信頼できないため学習コスト高
- LlamaIndex に切り替えても独自実装は同程度（14 件）必要だが、ベース安定性が高く改造が不要

### 3.2 Microsoft GraphRAG

- README に「demonstration」と明記、「officially supported Microsoft offering ではない」
- v3.0.0 で monorepo restructure、API/設定がまだ固まっていない
- 業務実装で詰まったときの逃げ道が Neo4j 周辺より少ない
- 概念（community report / global search / local search / hierarchical summary）は参考価値あり

### 3.3 LightRAG（単独採用）

- 研究色が強く、本番設計には POC 後の検証が必要
- ただし dual-level retrieval の概念は LlamaIndex から間接利用できる

### 3.4 Neo4j を default 化

- Community Edition は standard database を 1 個しか持てない（Enterprise でないと自由に複数 DB 切れない）
- spec-grag のモデル（1 開発者 = 複数プロジェクト、各プロジェクトに `.spec-grag/graph/`）と噛み合わない
- プロジェクトごとに Neo4j Docker を立てるのは POC ならよいが、CLI ツールの常用には重い
- 情報量・実装事例では強いが、運用要件の観点で default 不適
- → **optional adapter として将来追加**（spec-grag が成長して大規模・多段探索が必要になったとき）

### 3.5 ノード型を ec-spoke.local 専用に細分化

- Layer / Component / API / DataStructure / Action / Hook / Pattern / TechStack / Feature / Persona を spec-grag 標準に入れると、別ドメイン（金融、医療、ゲーム、研究、契約）で使えなくなる
- 「技術資料を扱うからといって技術ドメイン語彙を spec-grag 標準に入れてはいけない」（GPT 合意）
- これらは ec-spoke.local 側の `.spec-grag/schema.toml` に置く

### 3.6 Tier 2 / Tier 3 を標準スキーマに含める

- Phase / Alternative / Rationale / TakeDown / Layer / Component などを最初から階層的に積む案を私が提案したが、これは「最適化欲」で EXTERNAL_DESIGN の本来目的を超える
- 標準スキーマだけで EXTERNAL_DESIGN の 6 要素（Purpose / Concept / Source specs / ChapterAnchor / ERG / Hierarchical Cluster）と 5 分類（制約 / 修正対象 / 無関係 / 競合 / 要レビュー）は表現可能

### 3.7 AsyncGraphRAG::with_async_claude_cli() 経由でクラスタ要約と Q&A を生成

- AsyncGraphRAG 自体がスケルトン（query は sleep(10ms) → ダミー文字列、async_retrieval は最初 3 chunks の contains マッチ）
- DocumentTree.merge_nodes::generate_summary は max_tokens / temperature を無視（AsyncLanguageModelAdapter:44-45）
- spec-grag は AsyncGraphRAG ではなく、ClaudeCliLanguageModel を **直接保持**して使う方が制御可能
- pivot により Rust 実装ごと不要

### 3.8 純テンプレートベースの仕様書解析

- spec-grag は「仕様書を読み LLM に渡す」だけのツールではなく、ノード化・グラフ化・分類・矛盾検出を行う
- テンプレート抽出だけでは EXTERNAL_DESIGN §5.4 の InjectionContext 構造を満たせない

---

## 4. ec-spoke.local の独自拡張（リファレンス例）

ec-spoke.local（React + NestJS + Astro 構成の EC パッケージ、ECCUBE 置き換え狙い）は spec-grag の最初のユースケースであり、Project Custom Schema の参考例。**spec-grag 本体には含めない**が、別プロジェクトが拡張を作る際の参考になるため本書に収録する。

### 4.1 仕様書の構造

`/home/kazuki/public_html/ec-spoke.local/docs/React+NestJS+Astro/`

**メインディレクトリ（14 ファイル、合計 ~320KB）**:

- 章番号付き Markdown（`NN_*.md`）
- サブテーマが括弧書き（例: 「コンポーネント層（Core側）」「コンポーネント層（Customize側）」）
- 最大は `31_フレームワーク実装仕様書.md`（78KB）と `26_コンポーネント層（Core側）.md`（64KB）

**drafts/ ディレクトリ（28 ファイル、合計 ~350KB）**:

- ドラフト → メインの二層構造（drafts/ で検討、メインで確定）
- `_old.md` / `_引継ぎ.md` で版管理（SUPERSEDES エッジの典型）
- `04_未決定事項.md`（OpenQuestion 典型、優先度: 高 / 中 / 低）
- `00_技術選定の経緯.md`（Decision + Phase + Alternative 典型、Phase 1〜5 で議論プロセスを記録）
- `10_問題点一覧.md`（Conflict 典型、CR-1 / MJ-7 / mn-3 の ID 付き、行参照付き、状態追跡付き）

### 4.2 `10_問題点一覧.md` は ConflictNotes の手本

このファイルは spec-grag が `InjectionContext.ConflictNotes` で出力したい構造そのもの：

- ID 付き（CR-1, MJ-7, mn-3）
- 該当（行番号付き参照、`[26:1263-1289]` のように `SourceSpan` で表現可能）
- 問題（説明）
- 修正方針 / 修正内容
- 状態（解消済み 2026-04-24 / 取り下げ / 未解消）
- 取り下げ項目セクション（`~~MJ-X（旧）...~~`）

ユーザーが既に手作業でやっている運用を spec-grag が自動化する、という構図。spec-grag の出力は、このファイルが保つ構造（ID / 該当行 / 問題 / 修正方針 / 状態 / 取り下げ）に倣う。

### 4.3 ec-spoke.local の Custom Schema（候補、最終確定は実装時）

```toml
[schema.custom.entities]
items = [
  "Layer",          # Core / Customize / Framework / Theme Surface / Internal World
  "Component",      # TextInputField / PriceSection / RepeaterField 等
  "API",            # patchComponent / registerComponents / actionRegistry.register 等
  "DataStructure",  # CommonFieldProps / RepeaterRowProps / AddressValue 等
  "Action",         # updatePrice 等の Action パイプライン
  "Hook",           # usePriceSectionState / useTextInputFieldUI 等
  "Pattern",        # 「処理と見た目の分離」「3 フェーズ実行順序」「ミラー配置 + サフィックス規約」等
  "TechStack",      # NestJS / React / Astro / Drizzle / RHF / Zod / PostgreSQL
  "Feature",        # 検索 / 決済 / 配送 / 在庫 / 会員 / Webhook / Queue
  "Persona",        # テーマ作者 / Customize 開発者 / Core 開発者 / パッケージ利用者
]

[schema.custom.relations]
items = [
  "IMPLEMENTS",       # Component が API を実装、Pattern が Layer に適用
  "USES_TECH",        # Component / Action → TechStack
  "COMPOSED_OF",      # page → section → field、StoreGroup → Store
  "CALLS",            # Action 間呼び出し
  "EXPOSES",          # Component → API
  "TARGETS_PERSONA",  # Concept / Constraint → Persona
]
```

### 4.4 ec-spoke.local 仕様書の運用上の特徴

- **ドラフト → 確定の二層**: drafts/ で議論、メインで確定。spec-grag は両方を Source spec として扱うが、確定版優先（`.spec-grag/config.toml` の `sources.include` で制御）
- **章番号 + 括弧書きサブテーマ**: 「コンポーネント層（Core側）」のように 1 トピックに対し複数視点の章が並ぶ。`Document.metadata.topic_group` でグルーピング可能にする
- **行参照付き根拠**: `[26:1263-1289]` のような行範囲を Conflict / Decision の根拠として明示する慣習が既にある。spec-grag は `SourceSpan` ノード + `HAS_EVIDENCE` エッジでこれを表現する

---

## 5. この構成が狙う差別化

- **graphrag-rs の安定性問題を回避**: LlamaIndex first-party の安定実装を使う
- **日本語仕様書に対応**: 英語ハードコード覆い被せを排除、プロンプト変更だけで日本語対応
- **ローカル配布性**: Neo4j サーバー常駐を強制せず、SimplePropertyGraphStore でファイルベース完結。`.spec-grag/graph/` のみで動作
- **複数プロジェクト並行管理**: Neo4j Community の database 1 個制約を回避、プロジェクトごとに独立した graph を持てる
- **ドメイン非依存の標準スキーマ**: 業務要件 / 技術仕様 / 論文 / 企画書 / 契約 など多様なドメインで使える、各プロジェクトが `.spec-grag/schema.toml` で拡張
- **integrity の保証**: 整合性チェックを LLM 丸投げせず、グラフ構造ベース → ルールベース → LLM 補助の 3 段階で deterministic に検証
- **将来拡張パス**: spec-grag が成長したとき、Neo4jPropertyGraphStore adapter を optional 追加で大規模化可能

---

## 6. 不確定項目（次セッション以降で詰める）

### 6.1 LlamaIndex の表面マップ調査

- PropertyGraphIndex の API 安定度（v0.10 系での変更頻度、Breaking change の頻度）
- SchemaLLMPathExtractor の制約強度（プロンプトレベル止まりか、型システムレベルまで）
- SimplePropertyGraphStore の永続化粒度（章別 vs 全体一括の制御可否、pickle / JSON / parquet どれか）
- incremental update 方式（章単位 SHA-256 変更検出 → 影響範囲のみ再構築できるか）
- HybridRetriever の fusion 戦略（RRF / Weighted / CombSum / MaxScore）
- HippoRAG / LightRAG retrieval との統合可否

### 6.2 章別管理の実装方針

- ChapterAnchor 集約の具体実装（entity.mentions[].chunk_id → DocumentId 集約）
- 章別 chapter_index.json / concept_index.json のスキーマ
- 章単位 incremental の orchestration（変更章のみ再抽出 → ERG 再構築 → cluster 再計算）
- 階層 cluster の実装（LlamaIndex に hierarchical clustering があるか、自前実装か）

### 6.3 LLM プロバイダー実装

- ClaudeCliLanguageModel の Python 版 subprocess 設計（`claude -p --model sonnet --output-format json --no-session-persistence --dangerously-skip-permissions`）
- CodexCliLanguageModel の Python 版（同様）
- 並列実行（concurrent batch）の実装（`asyncio.gather` + `asyncio.Semaphore` で max_concurrent 制御）
- LLM 注入の抽象化（LlamaIndex の `LLM` interface を実装するか独自 trait か）

### 6.4 Cross-Encoder rerank

- 日本語向けモデル選定（`hotchpotch/japanese-reranker-cross-encoder-large-v1`、`cl-tohoku/bert-base-japanese-v3`、`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` 等の比較）
- LlamaIndex への統合方法

### 6.5 spec-grag CLI 実装

- フレームワーク選定（Click / Typer / Fire のいずれか、Typer が型ヒント連動で第一候補）
- パッケージング（`pyproject.toml`、`uv` / `pdm` / `poetry` のいずれか）
- 配布方式（pip install から直接、または `pipx` で隔離環境）

### 6.6 整合性チェックの実装

- グラフ構造ベース検出ルールの具体（Cypher 風クエリで書くか、Python 直書きか）
- ルールベース検出の YAML / TOML スキーマ
- LLM 推論の prompt template（日本語）

### 6.7 Concept 更新案 unified diff

- cluster summary → Concept 文書の生成パイプライン
- `difflib`（標準）vs `similar` 系のサードパーティ
- diff の context_radius / unified format の出力規約

### 6.8 Optional Extensions の発動判断

- decision_process 拡張は ec-spoke.local の `00_技術選定の経緯.md` のような議論記録文書で必須。`.spec-grag/config.toml` でどう設定するか
- ec-spoke.local では `enabled = ["decision_process"]` を default にする想定

---

## 7. 関連ドキュメント / コミット

### 現行ドキュメント（リポジトリ内）

- [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md): 外部契約（source of truth、pivot を超えて生き残った唯一のもの）

### Pre-pivot のアーカイブ（BAK/ 配下、参考のみ、戻らない）

- `BAK/HANDOFF.md`: Rust + graphrag-rs 前提の実装引継ぎ（HANDOFF.md §1.3〜§1.7、~700 行の Rust 実装）
- `BAK/Cargo.toml` / `BAK/Cargo.lock` / `BAK/src/`: spec-grag CLI の Rust スケルトン
- `BAK/templates/`: 旧 `.claude/commands/spec-{core,inject,realign}.md` と `.spec-grag/config.toml`
- `BAK/doc/DESIGN.ja.md`: Codex 版詳細設計（旧）
- `BAK/doc/DESIGN.md`: 設計ドキュメント（旧）
- `BAK/doc/DESIGN_old.md`: 旧設計（破棄予定だった）
- `BAK/doc/FOUNDATION_PLAN.md`: graphrag-rs 土台作り計画
- `BAK/doc/GRAG_FOUNDATION.md`: Phase 2 で書いた graphrag-rs 機能カタログ（827 行）— 内容は obsolete だが LlamaIndex 設計の参考になる部分あり
- `BAK/doc/GRAG_FOUNDATION_RAW.md`: Phase 1 生データ（111KB、§A〜§E）
- `BAK/doc/foundation_phase2_raw/`: Phase 2 生データ（4 ファイル、141KB）

### 関連 commit

- b45d95f（2026-04-27）: Pivot from Rust+graphrag-rs to Python+LlamaIndex; archive prior work to BAK/
- 0259cfa + b89ac2f（2026-04-27）: Phase 1 完了（graphrag-rs 機能調査）

### memory（spec-grag リポジトリ管理外、`~/.claude/projects/-home-kazuki-public-html-spec-grag/memory/`）

- `project_engine_pivot.md`: pivot 経緯と確定スキーマの memory
- `project_first_use_case.md`: ec-spoke.local 事例の memory
- `feedback_*.md`（6 件）: 行動原則
