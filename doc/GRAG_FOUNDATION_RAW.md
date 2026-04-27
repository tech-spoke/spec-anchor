# spec-grag GRAG_FOUNDATION_RAW（Phase 1 一次調査の生データ）

本書は [FOUNDATION_PLAN.md](FOUNDATION_PLAN.md) Phase 1（一次資料の網羅的取得）の **生データ** を保管する。
Phase 2（機能カタログの構築 → `doc/GRAG_FOUNDATION.md`）では、本書を一次ソースとして参照する。

> **重要**：本書は加工していない調査結果である。各 Agent の自己申告した「未確認項目」もそのまま残してある。
> 整理 / 取捨選択 / 整合性チェック / spec-grag への適用判断は、Phase 2 以降で行う（[FOUNDATION_PLAN.md §6](FOUNDATION_PLAN.md#L165-L201) 参照）。

**実行日**：2026-04-27  
**実行方式**：4 Agent (Explore) + 1 Bash の並列発火

## 目次

- §A. Agent 1：graphrag-rs README に挙がる 10 論文の調査（元ファイル: `agent1_10papers.md`）
- §B. Agent 2：Entity Extractor / Summarization / Retrieval の実装読解（元ファイル: `agent2_extractors.md`）
- §C. Agent 3：Incremental / Storage / Embedding / LLM 統合の実装読解（元ファイル: `agent3_incremental.md`）
- §D. Agent 4：graphrag-rs 公式 docs の体系的読解（元ファイル: `agent4_docs.md`）
- §E. Bash：Cargo.toml workspace 構造・feature 一覧（元ファイル: `bash_cargo.md`）

---

# §A. Agent 1：graphrag-rs README に挙がる 10 論文の調査

**タスク**：3.1 の 10 件の research papers / advanced techniques を WebFetch / WebSearch で調査し、出典 URL・abstract 引用・spec-grag との関連性（直接 / 間接 / 基盤）を整理。

**実行**：2026-04-27、Agent (Explore)、tool_use_id=`toolu_015V9AB8hf184CC4y3denYQh`。

**未確認の自己申告**：CatRAG（#6）と Dynamic Edge Weighting（#7）は学術論文出典が特定不能で確認度 20-30%。

---

## graphrag-rs README に記載される 10 件の研究論文・手法の調査報告

graphrag-rs README から確認できた 10 件の手法について、以下のように整理しました。

---

## 1. LightRAG Dual-Level Retrieval

### 目的（why）
現在の RAG システムは「フラットなデータ表現と不十分なコンテキスト認識」に苦しんでおり、複雑な相互依存関係を見落とす。LightRAG は「低レベルと高レベルの両方からの包括的な情報検索」を実現する二段階検索システムで、この問題を解決する。

> "comprehensive information retrieval from both low-level and high-level knowledge discovery"
> （参考：[ACL Anthology - LightRAG](https://aclanthology.org/2025.findings-emnlp.568/)）

### 方法（how）
グラフ構造とベクトル表現を結合して、関連エンティティと関係を効率的に位置付ける。**低レベル検索**は特定のエンティティとその属性・関係に焦点。**高レベル検索**は複数の関連エンティティ間に集約された情報を抽出。インクリメンタル更新メカニズムで新情報を動的に統合。

### spec-grag 関連性（推測）
**直接関係**。仕様書の「Purpose / Concept / Source specs」は異なる粒度の情報であり、LightRAG の二段階検索（概要レベルと詳細レベル）は spec-grag の **Concept（上位設計思想）** と **Source specs（局所的仕様本文）** を段階的に検索・統合するモデルとして活用できる推測。

### 出典
- EMNLP 2025 Findings
- https://arxiv.org/abs/2410.05779
- https://aclanthology.org/2025.findings-emnlp.568/
- アクセス日：2026年4月27日

### 確認できなかった点
- 論文本文の詳細な実装メカニズム（PDF アクセス制限のため abstract 相当の情報のみ）

---

## 2. Leiden Community Detection

### 目的（why）
Louvain アルゴリズムは「任意に悪く接続されたコミュニティ、最悪の場合は切断されたコミュニティを生成」する（最大 25% が悪く接続、16% が完全に切断）。Leiden は「保証されたコミュニティ接続性」を実現する改善アルゴリズム。

> "yields communities that are guaranteed to be connected"
> （Traag et al., [Nature Scientific Reports 2019](https://www.nature.com/articles/s41598-019-41695-z) / [arXiv:1810.08473](https://arxiv.org/abs/1810.08473)）

### 方法（how）
3 段階プロセス：(1) ノードの局所的な移動（変更されたネイバーフッドを持つノードのみ訪問）、(2) 分割の洗練（各クラスタ内で singleton 分割から開始して段階的にマージ）、(3) 洗練済み分割に基づくネットワーク凝集。Louvain より高速で、より良い分割を発見。

### spec-grag 関連性（推測）
**間接関係**。spec-grag の Hierarchical Cluster（章・概念・関係の階層クラスタ）の構築において、Leiden による entity relationship graph の階層的コミュニティ検出は、仕様要素間の高度な「関係構造化」に貢献する推測。つまり Purpose / Concept / Source specs 間の関係を意味のあるクラスタへ自動分割する基盤技術。

### 出典
- Scientific Reports 2019, DOI: 10.1038/s41598-019-41695-z
- https://www.nature.com/articles/s41598-019-41695-z
- https://arxiv.org/abs/1810.08473
- アクセス日：2026年4月27日

### 確認できなかった点
- Nature Scientific Reports の full text（ペイウォール越しのため abstract から引用）

---

## 3. Cross-Encoder Reranking

### 目的（why）
従来のニューラルランキング手法を大幅に改善する。BERT の fine-tuned cross-encoder は「MS MARCO 上で古典的リランカーを劇的に上回る」（Nogueira & Cho, 2019）。

> "fine-tuned BERT models as cross-encoders dramatically outperformed classical rerankers on MS MARCO"
> （参考：[arXiv:1901.04085](https://arxiv.org/abs/1901.04085) "Passage Re-ranking with BERT"）

### 方法（how）
BERT を query-passage pair に適用し、passage の relevance score を直接出力。Bi-encoder（別々にエンコード）ではなく cross-encoder（query と passage を一度にエンコード）することで、query と passage 間の interaction を直接捕捉。TREC-CAR、MS MARCO で SOTA 達成。27% 相対改善（MRR@10）。

### spec-grag 関連性（推測）
**直接関係**。spec-grag の `/spec-inject` / `/spec-realign` で「課題プロンプトと候補 Source specs / ChapterAnchor の関連度を判定」する際、cross-encoder は purpose-aware reranking として機能する推測。単なる semantic similarity ではなく、「仕様課題と制約・修正対象候補の相互作用」を直接評価することで、局所的過度アンカーを回避。

### 出典
- arXiv:1901.04085 "Passage Re-ranking with BERT"
- https://arxiv.org/abs/1901.04085
- アクセス日：2026年4月27日

### 確認できなかった点
- 元の EMNLP 2019 正式投稿か Findings か（arXiv 記載）

---

## 4. HippoRAG Personalized PageRank

### 目的（why）
LLM が新知識を効率的に統合しつつ catastrophic forgetting を回避する課題を解決。哺乳類脳の hippocampus（海馬）と neocortex（新皮質）の長期記憶管理メカニズムを RAG に適用。

> "enables LLMs to continuously integrate knowledge across external documents" with "remarkable" up to 20% outperformance on multi-hop QA
> （[NeurIPS 2024](https://arxiv.org/abs/2405.14831)）

### 方法（how）
LLM + Knowledge Graph + Personalized PageRank を組み合わせ。新しい query に対して、query key concepts を seed にして KG 上で Personalized PageRank (PPR) を実行し、複数 passage 間の情報統合を実現。単一ステップ検索で iterative retrieval (IRCoT) と同等または優位な精度を **10-30 倍低コスト、6-13 倍高速** で達成。

### spec-grag 関連性（推測）
**間接関係**。spec-grag の ConversationContext から Purpose と関連 Concept・Source specs を「段階的に統合」する処理において、PPR による multi-hop 統合は、仕様要素間の遠距離関係（たとえば Purpose → 中間 Concept → 局所 Source specs）の traversal に適用される可能性推測。

### 出典
- NeurIPS 2024
- https://arxiv.org/abs/2405.14831
- https://proceedings.neurips.cc/paper_files/paper/2024/file/6ddc001d07ca4f319af96a3024f6dbd1-Paper-Conference.pdf
- https://github.com/osu-nlp-group/hipporag
- アクセス日：2026年4月27日

### 確認できなかった点
- NeurIPS 2024 full paper の詳細なアルゴリズム実装（PDF ダウンロード不可、arXiv HTML より情報取得）

---

## 5. Semantic Chunking

### 目的（why）
テキストの意味的完全性を保ちながら chunk を分割する。従来の固定長や構造ベース chunking では「関連アイデアの破断」「コンテキスト喪失」を招く。

> "splits text based on changes in meaning or topic, rather than fixed length or structural separators"
> （参考：[Weaviate](https://weaviate.io/blog/chunking-strategies-for-rag), [Medium](https://medium.com/the-ai-forum/semantic-chunking-for-rag-f4733025d5f5)）

### 方法（how）
全 sentence の embedding を計算し、similarity を比較して、意味的差異が閾値（百分位数、標準偏差、四分位数など）を超えた地点で chunk 分割。各 chunk は語意的に首尾一貫したコンセプトを代表。LangChain 2024 実装ではこれらの変動量に基づく複数の strategy 展開。

### spec-grag 関連性（推測）
**直接関係**。spec-grag は Source specs（現行章ファイル）から ChapterAnchor（章別キーコンセプト）を抽出する際、semantic chunking によって「局所仕様の意味的境界」を正確に認識する推測。固定幅では Purpose と無関係な「狭い仕様フレーズ」を避け、真に関連する「コンセプト単位」の chunk を得る。

### 出典
- LangChain 2024
- https://python.langchain.com/docs/how_to/semantic-chunker/ (redirect to https://docs.langchain.com/oss/python/langchain/overview)
- https://weaviate.io/blog/chunking-strategies-for-rag
- https://medium.com/the-ai-forum/semantic-chunking-for-rag-f4733025d5f5
- アクセス日：2026年4月27日

### 確認できなかった点
- LangChain official documentation の直接的な semantic chunking 専用セクション（リダイレクト先は overview のみ）

---

## 6. Symbolic Anchoring (CatRAG-style)

### 目的（why）
抽象的コンセプト（「愛」「正義」など）を具体的なエンティティ・事実へ grounding する。RAG 検索時に「シンボリックな query」を具体的エンティティへ自動変換し、conceptual query の精度向上。

※ **CatRAG の具体的論文は未確認**。graphrag-rs README では「Symbolic Anchoring (CatRAG-style)」と記載されるが、公開学術論文は検索範囲内で発見されず。

> "Automatically grounds abstract concepts (like 'love' or 'justice') to concrete entities for better conceptual query handling"
> （graphrag-rs README より）

### 方法（how）
未確認。推測として：抽象語の embedding を concrete entity の embedding に射影し、または LLM により abstract concept を exemplifying entity へ展開。

### spec-grag 関連性（推測）
**直接関係**の可能性高。仕様書の「Purpose」は高度に抽象的（たとえば「ユーザー XP の根幹」「システムの存在理由」）であり、これを「現実の Source specs・ChapterAnchor という具体エンティティ」へ自動 grounding することで、局所仕様の過度アンカーを防止する推測。

### 出典
- graphrag-rs README.md（https://github.com/automataIA/graphrag-rs）
- 学術論文での出典：**未確認**

### 確認できなかった点
- CatRAG 関連の学術論文（未発見）
- 実装の詳細なアルゴリズム
- 論文への DOI / arXiv リンク

---

## 7. Dynamic Edge Weighting

### 目的（why）
knowledge graph の edge weight を静的ではなく **query context に応じて動的に調整**する。同じ関係でも、query によって重要度が変わることを反映。

> "Adjusts relationship importance based on query context using semantic, temporal, and causal signals"
> （graphrag-rs README より）

### 方法（how）
graphrag-rs README では semantic boost、temporal boost、causal boost の 3 signal を言及。具体的実装は未確認だが、推測として：query embedding との cosine similarity（semantic）、時系列情報（temporal）、causal reasoning（causal）の各軸で edge weight を再計算。

### spec-grag 関連性（推測）
**直接関係**。spec-grag で Entity Relationship Graph を検索する際、同じ relationship edge でも「現在の課題コンテキスト」によって制約側か修正対象側かが変わる。Dynamic edge weighting により、Purpose-aware に重みづけされた relationship retrieval が実現推測。

### 出典
- graphrag-rs README.md（https://github.com/automataIA/graphrag-rs）
- 学術論文での出典：**未確認**（Microsoft GraphRAG 系と推察だが具体論文は特定困難）

### 確認できなかった点
- 学術論文化の有無
- 詳細なアルゴリズム（README のみ）
- semantic/temporal/causal boost の実装詳細

---

## 8. Causal Chain Analysis

### 目的（why）
RAG が因果関係を明示的にモデル化しない場合、「単純な事実検索」に陥り、「なぜ→何が起こったか」という multi-hop causal reasoning に失敗。Causal Chain Analysis は因果グラフを構築し、因果的整合性を検証。

> "Discovers multi-step causal chains with temporal consistency validation"
> （graphrag-rs README より）

複数の論文が存在：
- CausalRAG: "preserves contextual continuity and improves retrieval precision"
- CC-RAG: "constructs a Directed Acyclic Graph (DAG) of ⟨cause, relation, effect⟩ triples and applies forward/backward chaining"
> （[ACL Anthology](https://aclanthology.org/2025.findings-acl.1165/) / [arXiv:2503.19878](https://arxiv.org/abs/2503.19878)）

### 方法（how）
document から ⟨cause, relation, effect⟩ triple を抽出し DAG を構築。query に対して forward chaining（cause → effect）と backward chaining（effect → cause）で因果経路を検索。temporal consistency を検証（前の事象が後の事象を時系列的に先行）。LLM-based reasoning とグラフベース検索を統合。

### spec-grag 関連性（推測）
**間接関係**。仕様変更の波及分析（「この Purpose 変更が、どの Concept → どの Source specs に cascading 影響を与えるか」）に causal reasoning が活用される推測。通常の semantic similarity では捕捉できない「因果的影響関係」を明示化。

### 出典
- CausalRAG: https://arxiv.org/abs/2503.19878 (ACL Anthology: https://aclanthology.org/2025.findings-acl.1165/)
- CC-RAG: https://openreview.net/forum?id=daSiBuVRHH
- Causal-Counterfactual RAG: https://arxiv.org/abs/2509.14435
- MedCoT-RAG: https://openreview.net/pdf?id=kXzTSnaQrB
- アクセス日：2026年4月27日

### 確認できなかった点
- graphrag-rs での具体的実装（README のみ言及）
- 「temporal consistency validation」の詳細アルゴリズム

---

## 9. Hierarchical Relationship Clustering

### 目的（why）
平坦な entity relationship graph では、大規模グラフの検索が O(n) に堕ちる。階層的クラスタ化により、multi-resolution の semantic aggregation を実現し、高速かつ高品質な retrieval を両立。

> "Organizes relationships into multi-level hierarchies using Leiden algorithm with LLM-generated summaries"
> （graphrag-rs README より）

HiRAG 論文：
> "higher-layer entities acting as semantic hubs that abstract clusters of semantically related entities regardless of their distance"
> （[arXiv:2503.10150](https://arxiv.org/html/2503.10150v3)）

### 方法（how）
Leiden algorithm で entity/relationship を multi-level にクラスタ化。各レベルで LLM を用いてクラスタの semantic summary を生成。query に対して、高レベルから低レベルへ段階的に refinement。高レベルでは thematic 概念、低レベルでは granular な entity/relation 検索。

### spec-grag 関連性（推測）
**直接関係**。spec-grag の Hierarchical Cluster（章・概念・関係の階層クラスタ）の実装に直結。Purpose（最上位）→ Concept（中位）→ Source specs（最下位）という 3 層構造を、自動的かつ意味保持的に構築・検索するための技術推測。

### 出典
- HiRAG: https://arxiv.org/html/2503.10150v3 "Retrieval-Augmented Generation with Hierarchical Knowledge"
- graphrag-rs README.md（https://github.com/automataIA/graphrag-rs）
- アクセス日：2026年4月27日

### 確認できなかった点
- graphrag-rs での Leiden + LLM summary の具体実装
- HiRAG の full paper details

---

## 10. Graph Weight Optimization (DW-GRPO)

### 目的（why）
RAG の reinforcement learning fine-tuning で、複数の目的関数（relevance, faithfulness, conciseness）をバランス取ることが困難。固定重みでは「易しい目的への過最適化」（conciseness ばかり改善）を招く。DW-GRPO は動的重み調整で balanced optimization を実現。

> "monitors the rate of change for each reward component over time and dynamically adjusts weights using a softmax function with temperature parameter T"
> （[arXiv:2601.11144](https://arxiv.org/abs/2601.11144) "Deep GraphRAG"）

実例：Qwen2.5 1.5B モデルが DW-GRPO で 72B モデルの **94% 性能** (42.36% vs 45.02% EM-Total on NQ) を達成。

### 方法（how）
3 つの reward component (relevance, faithfulness, conciseness) の更新速度を監視。進捗が遅い目的に高い weight を付与（softmax + temperature）。Progressive balancing により、全目的の収束を同期。LLM fine-tuning 時に適用。

### spec-grag 関連性（推測）
**間接関係**の可能性。spec-grag が Concept / Source specs / ChapterAnchor を検索・統合する際、複数の検索戦略（semantic, graph-based, keyword）の重みを query context に応じて動的調整することで、Purpose bias と局所 spec の過度強調をバランス取る推測。

### 出典
- Deep GraphRAG: https://arxiv.org/abs/2601.11144
- https://arxiv.org/html/2601.11144v2
- https://www.alphaxiv.org/overview/2601.11144
- アクセス日：2026年4月27日

### 確認できなかった点
- 論文本文の詳細なアルゴリズム（HTML abstract から推測）

---

## 分類（spec-grag との関連性）

### 直接関係（3 件）
1. **LightRAG Dual-Level Retrieval** - 二段階検索で Concept と Source specs を段階的に統合
2. **Cross-Encoder Reranking** - purpose-aware reranking で局所過度アンカー回避
3. **Semantic Chunking** - 局所仕様の意味的境界認識で ChapterAnchor 抽出精度向上
4. **Symbolic Anchoring (CatRAG-style)** - 抽象 Purpose を具体エンティティへ自動 grounding
5. **Hierarchical Relationship Clustering** - 3 層階層化（Purpose → Concept → Source specs）

### 間接関係（3 件）
6. **Leiden Community Detection** - Entity Relationship Graph の関係構造化
7. **HippoRAG Personalized PageRank** - 仕様要素間の遠距離 multi-hop 統合
8. **Causal Chain Analysis** - 仕様変更の波及分析（因果的影響関係の明示化）
9. **Graph Weight Optimization (DW-GRPO)** - 複数検索戦略の動的重み調整

### 基盤技術（1 件）
10. **Dynamic Edge Weighting** - query context に応じた relationship weight の動的調整（手法カテゴリ、具体応用は上記に含まれる）

---

## 未確認だった項目の総まとめ

| # | 手法 | 未確認事項 | 確認度 |
|---|---|---|---|
| 1 | LightRAG | 論文本文の実装詳細（PDF 制限） | 70% |
| 2 | Leiden | Nature 論文 full text（ペイウォール） | 80% |
| 3 | Cross-Encoder | EMNLP 2019 正式投稿 vs Findings | 85% |
| 4 | HippoRAG | NeurIPS 2024 PDF full text | 75% |
| 5 | Semantic Chunking | LangChain 公式 dedicated セクション | 60% |
| 6 | Symbolic Anchoring | **CatRAG 学術論文・著者不明** | **30%** |
| 7 | Dynamic Edge Weighting | **学術論文化の有無不明** | **20%** |
| 8 | Causal Chain Analysis | graphrag-rs 実装の詳細 | 70% |
| 9 | Hierarchical Clustering | graphrag-rs + Leiden 統合実装 | 65% |
| 10 | DW-GRPO | 論文本文の詳細実装 | 65% |

### 特に低い確認度の項目（要注意）
- **#6 Symbolic Anchoring**: CatRAG 関連の学術論文が検索範囲内で発見されず。graphrag-rs README には記載されるが、論文は未確認。推測による記述を避けるため、「未確認」と明示。
- **#7 Dynamic Edge Weighting**: graphrag-rs README に実装があるが、学術論文化の有無が不明。Microsoft GraphRAG との関連推測だが、出典論文が特定困難。

---

**結論**：10 件中 8 件は確認可能な論文・ドキュメントが存在。2 件（Symbolic Anchoring, Dynamic Edge Weighting）は graphrag-rs の実装から逆推測であり、学術論文出典が未確認のため、spec-grag への活用時には追加調査が必要。

---

# §B. Agent 2：Entity Extractor / Summarization / Retrieval の実装読解

**タスク**：3.2（5 つの extractor）/ 3.3（Summarization・Clustering）/ 3.4（Retrieval・Reranking）を `vendor/graphrag-rs/graphrag-core/src/` 配下のファイル（entity/, summarization/, retrieval/, reranking/, lightrag/, query/）を Read して実装本体を読解。

**実行**：2026-04-27、Agent (Explore)、tool_use_id=`toolu_016198JmYjfPhvJrM1fGv6mV`。

**未確認の自己申告**：cluster generation の実装ロジック / Conflict detection メカニズム / BidirectionalIndex 内部 / GraphStatistics の計算ロジック / TemporalRelationType enum / LightRAG vs LazyGraphRAG の使い分け / Chunking strategy の overlap_sentences 詳細。

---

## 調査報告書：spec-grag Phase 1 基盤 - graphrag-rs vendor 実装分析

### 1. Entity Extractor 5つの使い分け本質

| 抽出器 | 入力 | 出力 | LLM呼び出し | 特徴 |
|--------|------|------|------------|------|
| **LLMEntityExtractor** | TextChunk | Vec<Entity>, Vec<Relationship> | ✅ 1回 / 初回抽出 | TRUE LLM推論。温度0.0。JSON修復対応（jsonfixer）。keep_alive で KV キャッシュ保持（line:22, 101-102） |
| **LLMRelationshipExtractor** | TextChunk | ExtractionResult (entities + rels) | ✅ 1回 / 抽出 + ✅ validate_triple 時追加 | 単一LLM呼び出しで E+R を同時抽出。fallback で pattern-based co-occurrence 可（line:193-263, 428-462） |
| **GleaningEntityExtractor** | TextChunk | Vec<Entity>, Vec<Relationship> | ✅ 4回 / gleaning ラウンド | ラウンド1：初期抽出。R2-N：継続抽出 + LLM完了判定（line:113-226）。length-based merge（line:228-275） |
| **AtomicFactExtractor** | TextChunk | Vec<AtomicFact> | ✅ 1回 / 抽出 | 5-tuple (S,P,O,Temporal,Conf) 形式。時間情報 + causal_strength 抽出（line:122-227, 287-316） |
| **GLiNERExtractor** | TextChunk | Vec<Entity>, Vec<Relationship> | ❌ 0 / ONNX推論のみ | NER+RE 単一フォワードパス（line:117-235）。CUDA可能（line:88-95）。span or token mode。hallucination なし |

**出典：** 各ファイルの line 番号で記載。

---

### 2. Entity Extractor の連携関係

```
[ LLMEntityExtractor ]                [ GleaningEntityExtractor ]
    ↓ (prompt_builder)                    ↓ (delegates to)
[ PromptBuilder ]  ────────────────────→ [ LLMEntityExtractor ]
    ↓                                         ↓
[ OllamaClient ]                        [ Round N loop ]
    ↓                                        ↓
[ LLM call ]                            [ completion check ]
    ↓                                        ↓
[ JSON repair (jsonfixer) ]             [ merge_entity_data ]
    ↓                                        ↓
[ ExtractionOutput ]                    [ final entities/rels ]

[ LLMRelationshipExtractor ]
    ├─ extract_with_llm() → ExtractionResult
    ├─ validate_triple() → TripleValidation (DEG-RAG)
    └─ fallback: infer_relationship_with_context()

[ AtomicFactExtractor ]
    ↓ extract_atomic_facts()
    ↓
    ├─ AtomicFact (temporal_marker + causal_strength)
    └─ atomics_to_graph_elements() → (Entity, Relationship)

[ GLiNERExtractor ] (feature-gated)
    ├─ SpanPipeline (NER)
    └─ RelationPipeline (RE)
    ↓
    ├─ Entity (with zero offsets - TODO: line 182-186)
    └─ Relationship
```

**出典：** entity/mod.rs:1-32, llm_extractor.rs:99-120, gleaning_extractor.rs:113-226, llm_relationship_extractor.rs:193-263

---

### 3. Summarization / Clustering の役割

**DocumentTree（hierarchical_query）:** TextChunk → Leaf nodes（抽出的要約）→ 階層的マージ（merge_size=5）→ Tree levels。LLM client があれば、Level ごとに abstractive/extractive を選択（Progressive strategy）。**出典：** summarization/mod.rs:202-260, 284-304, 421-454

**目的：** Knowledge graph の上流で Multi-level context を提供。Query ごとに適切な abstraction level を選択可能。Chunk 単位の局所的な要約から document 単位の全体概要まで段階的に構成。

**未確認詳細：** cluster generation の実装ロジック（branch を切ったか，その詳細コード）

---

### 4. Retrieval / Reranking のパイプライン

```
[ Query ]
    ↓
[ QueryIntelligence / QueryType 判定 ]
    ↓ (adaptive_routing, planner)
    ├─→ [ KeywordExtractor (LightRAG) ]
    │       ├─ high_level keywords (theme, concept)
    │       └─ low_level keywords (entity, detail)
    │       ↓
    │   [ DualLevelRetriever ]
    │       ├─ High-level: DocumentTree summary level 検索
    │       └─ Low-level: Entity/Chunk 検索
    │       ↓
    │   [ Semantic merge (MergeStrategy) ]
    │
    ├─→ [ BM25Retriever ] (keyword-based fallback)
    │
    ├─→ [ PageRankRetriever ] (graph traversal, feature-gated)
    │       └─ HippoRAG (personalized PPR)
    │
    └─→ [ EnrichedRetriever ] (metadata-aware)
            ├─ Entity weight: 0.4
            ├─ Chunk weight: 0.4
            └─ Graph weight: 0.2
                ↓
            [ HybridRetriever ]
                ├─ RRF (Reciprocal Rank Fusion)
                ├─ CombMNZ
                └─ Linear combination
                    ↓
                [ Top-K ranking ]
                    ↓
        [ CrossEncoderReranking ]
        (CandleCrossEncoder or ONNX)
            ├─ Query-document pair scoring
            ├─ Confidence normalization
            └─ Score delta calculation
                ↓
        [ Final Ranked Results ]
            └─ ExplainedAnswer
                ├─ answer text
                ├─ confidence (0.0-1.0)
                ├─ sources
                ├─ reasoning_steps
                └─ key_entities
```

**出典：**
- retrieval/mod.rs:1-111（RetrievalSystem, RetrievalConfig, SearchResult）
- lightrag/mod.rs:1-68（DualLevelRetriever, KeywordExtractor）
- lightrag/keyword_extraction.rs:44-129（high/low level extraction）
- lightrag/concept_graph.rs:1-150（concept-based filtering, no LLM required）
- reranking/mod.rs:1-14, cross_encoder.rs:1-150（CrossEncoder trait, CandleCrossEncoder）
- query/mod.rs:1-29（QueryIntelligence, adaptive routing）

---

### 5. LLMClient と OllamaClient の役割分離

| コンポーネント | 役割 | 出典 |
|---|---|---|
| **OllamaClient** | LLM推論の実装。生の text generation。Retry logic, keep_alive サポート | llm_extractor.rs:207-231 |
| **LLMClient trait** | summarization 用の高レベルインターフェース（generate_summary, batch）| summarization/mod.rs:14-43 |
| **AsyncLanguageModel trait** | LightRAG keyword extraction の抽象化 | lightrag/keyword_extraction.rs:46 |

**推測（未検証）：** OllamaClient は低レベル（raw response），LLMClient/AsyncLanguageModel は高レベル抽象化。実装を確認できたのは OllamaClient のみ。

---

### 6. 仕様分類への寄与マップ

spec-grag の目的「LLM に渡すコンテキストを **Constraint / Target / Exclusion / Conflict / Review** に事前分類」に対して：

```
Entity Extraction (5種)
├─ Constraint: entity type filtering (allowed_patterns)
├─ Target: high-confidence entities only（min_confidence threshold）
├─ Exclusion: excluded_patterns filtering（entity/mod.rs:79-89）
└─ Review: TripleValidation (DEG-RAG, llm_relationship_extractor.rs:281-409)

Summarization / Clustering
├─ Target: hierarchy levels で abstraction 段階的提供
└─ Review: merge_entity_data で duplicate detection

Retrieval / Reranking
├─ Target: top-k filtering, similarity_threshold
├─ Constraint: entity_weight, chunk_weight, graph_weight の3値分解
├─ Exclusion: below_threshold filtering
└─ Review: CrossEncoder で relevance re-scoring
```

**未確認：** Conflict detection の実装ファイル。relationship の矛盾検知機構。

---

### 7. Entity Linking と Merging

| 機能 | 入力 | 出力 | LLM呼び出し | 出典 |
|-----|------|------|------------|------|
| **StringSimilarityLinker** | KnowledgeGraph | HashMap<EntityId, EntityId> | ❌ 0 | Levenshtein, Jaro-Winkler, Jaccard, Soundex（line:186-405） |
| **SemanticEntityMerger** | Vec<Entity> | EntityMergeDecision | ✅ optional（fallback: heuristic） | similarity_threshold 0.7-0.9（line:57-111, 307-329） |
| **BidirectionalIndex** | (Entity ID ↔ Chunk ID mapping) | Fast lookups | ❌ 0 | Index statistics tracking（line:24） |

**出典：** string_similarity_linker.rs:54-123, semantic_merging.rs:57-111, bidirectional_index.rs（line数確認済み）

---

### 8. 未確認項目の総まとめ

| 項目 | 理由 | 影響範囲 |
|-----|------|---------|
| **cluster generation の実装詳細** | summarization/mod.rs で「cluster generation」言及（mod.rs:1）されるが、該当コード未読 | Summarization / Clustering の正確な手法 |
| **Conflict detection メカニズム** | spec-grag の「Conflict」分類に必要だが、ファイル検索で見つからず | Review フェーズの実装 |
| **BidirectionalIndex の内部構造** | bidirectional_index.rs の行数確認（613行）だが、Read 未実施 | Entity Extraction の効率化詳細 |
| **query/planner, query/optimizer** | query/mod.rs:1-29 のリスト表示のみ。advanced_pipeline, analysis 等の実装内容 | Query routing と cost estimation |
| **GraphStatistics 計算ロジック** | pagerank_retrieval と query/optimizer に登場するが定義確認なし | PageRank スコアリングの詳細 |
| **temporal_type（TemporalRelationType）** | atomic_fact_extractor.rs:305-314 で使用だが、enum 定義確認なし | Temporal reasoning の正確な型 |
| **LightRAG と LazyGraphRAG の区分** | lightrag/mod.rs に両モジュール混在（line:21-68）だが、使い分け未明確化 | 構成図の精密度 |
| **Chunking strategy（重複 overlap_sentences）** | summarization/mod.rs:84 で言及されるが、実装ロジック未確認 | Document fragmentation method |

**重要：** 上記 8 項目は**実装ファイルで確認できたが詳細読み込み未完了**。推測ではなく「未確認」と明記。

---

### 9. LLM 呼び出し総数の概算

1 chunk × 4 gleaning rounds で：
- **GleaningEntityExtractor:** round1 (1回) + R2-4 各round (3回) + 各round 完了判定 (3回) = **7回 / chunk**
- **AtomicFactExtractor:** 1回
- **LLMRelationshipExtractor:** 1回（validation なしの場合）+ validate_triple ×N entities
- **KeywordExtractor (query):** 1回 / query

**推測：** 1000ページ文書 + 4 gleaning rounds ≈ 2000 chunk で **14,000+ LLM calls** expected（未検証）。

---

### 10. 設計原則の確認

✅ **確認項目：**
- Entity Extractor は OllamaClient に統一（複数の LLM vendor 切り替え不可 → design choice）
- Relationship extraction と Entity extraction は分離（2-phase 構造）
- String similarity linker（LLM 不要）と SemanticMerger（LLM optional）の layering
- Hierarchical summarization の Progressive strategy（低 level は extractive）

❓ **推測項目（実装確認なし）：**
- Entity linking の bidirectional index 活用による高速化の実装
- Conflict detection の存在と algorithm

---

**報告書作成日時：** 2026-04-27  
**調査範囲縮小なし：** vendor/graphrag-rs/graphrag-core/src/ 配下 entity/, summarization/, retrieval/, reranking/, lightrag/, query/ ディレクトリすべて対象。ファイル名:行番号 で根拠明示。

---

# §C. Agent 3：Incremental / Storage / Embedding / LLM 統合の実装読解

**タスク**：3.5（Incremental Update）/ 3.6（Storage・Persistence）/ 3.7（Embedding）/ 3.8（LLM 統合）を `vendor/graphrag-rs/graphrag-core/src/` 配下（incremental/, persistence/, vector/, embeddings/, core/traits.rs, core/ollama_adapters.rs, generation/）を Read。

**実行**：2026-04-27、Agent (Explore)、tool_use_id=`toolu_015dtb4JX2Bx8xG6cAvg1fXp`。

**未確認の自己申告**：extract_from_content() がスケルトン / Lazy Propagation の apply_update が未実装 / ConflictResolution::HighestConfidence のスコア形式 / LanceDB・Qdrant 実装詳細 / JSON/JSONL バックエンド / Bloom filter の偽陽性率検証 / parallel processing 実測値 / StreamSupport / ClaudeCli の params 無視 / token estimation の近似式。

---

# graphrag-rs vendor 実装調査報告書

## 全体構成

spec-grag の graphrag-rs vendor 実装は、Incremental Update・Storage・Embedding・LLM 統合の4つの主要機能モジュールで構成。各機能は非同期 trait ベースで設計され、spec-grag が ClaudeCliLanguageModel を実装することで Claude CLI サブプロセス呼び出しを統合します。

---

## 3.5 Incremental Update メカニズム

### ファイル構成
- `/vendor/graphrag-rs/graphrag-core/src/incremental/mod.rs` (1,219行)
- `/vendor/graphrag-rs/graphrag-core/src/incremental/delta_computation.rs` (600+行)
- `/vendor/graphrag-rs/graphrag-core/src/incremental/lazy_propagation.rs` (600+行)
- `/vendor/graphrag-rs/graphrag-core/src/incremental/async_batch.rs` (500+行)

### 主要 struct / trait

**IncrementalGraphManager** (mod.rs:46-63)
- `graph: Arc<RwLock<DiGraph<GraphNode, GraphEdge>>>` - petgraph ベースのメイングラフ
- `node_index: Arc<RwLock<HashMap<String, NodeIndex>>>` - O(1) ノード検索用インデックス
- `change_detector: Arc<RwLock<ChangeDetector>>` - 変更検出
- `lazy_propagation: Arc<LazyPropagationEngine>` - Lazy Propagation エンジン
- `delta_computer: Arc<DeltaComputer>` - Delta 計算エンジン

**IncrementalConfig** (mod.rs:85-156)
- `auto_detect_changes: bool` - SHA-256 ハッシュベースの変更検出有効化（デフォルト true）
- `enable_lazy_propagation: bool` - Lazy Propagation 有効化（デフォルト true）
- `enable_delta_computation: bool` - Delta 計算有効化（デフォルト true）
- `lazy_propagation_threshold: usize` - 自動伝播トリガー数（デフォルト 100）
- `delta_use_bloom_filter: bool` - Bloom filter による高速化（デフォルト true）

**ChangeDetector** (mod.rs:431-438)
- `document_hashes: HashMap<String, String>` - SHA-256 ハッシュ保持

### Incremental Update パイプライン

#### 1. 変更検出フェーズ

**入力**: DocumentContent (mod.rs:996-1012)
- `id: String` - ドキュメント ID
- `text: String` - テキスト内容
- `metadata: HashMap<String, String>` - メタデータ

**処理** (mod.rs:497-507, mod.rs:841-860)
```
has_content_changed()
  → SHA-256(content.text) → ChangeDetector.document_hashes 比較
  → 変更がない場合は空の UpdateSummary を返却（処理スキップ）
```

出典: `mod.rs:841-852`（has_content_changed 実装）、`mod.rs:855-860`（hash_content 実装）

#### 2. 抽出・マッピング フェーズ

**処理** (mod.rs:510-514, mod.rs:862-920)
```
extract_from_content(content)
  → ExtractionResult {entities, relationships, concepts}
  
apply_incremental_update(extraction)
  ← 各 entity が既存ノードと合致したら update、そうでなければ add
  ← 各 relationship は add_edge で挿入
```

出典: `mod.rs:871-920`（apply_incremental_update 実装）

#### 3. Conflict Resolution

**戦略** (mod.rs:163-187)
- `LatestWins` - 新データで上書き（デフォルト）
- `HighestConfidence` - 信頼度スコアが高い方を採択
- `Merge` - 非競合属性をマージ
- `Manual` - エラーで止めて外部レビュー待ち

出典: `mod.rs:547-577`（update_node での適用）

#### 4. Lazy Propagation (80-90% 削減)

**メカニズム** (lazy_propagation.rs:1-43, 281-318)
```
Node/Edge 更新が発生
  → queue_node_update() / queue_edge_update() で PendingUpdate をキュー
  → DirtyTracker でノード/エッジを「dirty」マーク
  → should_propagate() で判定:
      - キュー サイズ >= propagation_threshold (デフォルト 100)
      - 最後の伝播から max_delay_seconds (デフォルト 300s) 経過
      → 自動 propagate_pending_updates() 実行
  → propagate_on_query=true なら、クエリ前に maybe_propagate_for_query()
```

出典: 
- `lazy_propagation.rs:281-318`（queue_node_update）
- `lazy_propagation.rs:356-376`（should_propagate）
- `lazy_propagation.rs:379-468`（propagate_pending_updates）
- `lazy_propagation.rs:504-510`（maybe_propagate_for_query）

**PendingUpdate の状態遷移**
- `Pending` → `InProgress` → `Applied` / `Failed` (→ リトライ最大 3回)

出典: `lazy_propagation.rs:401-443`

#### 5. Delta Computation

**Bloom Filter 最適化** (delta_computation.rs:222-279)
```
create_snapshot() 
  → 全ノード・エッジをキャプチャ (mod.rs:693-744)
  → NodeSnapshot {node_id, content_hash, properties, last_modified}
  → EdgeSnapshot {source, target, edge_type, content_hash, properties}

compute_delta(before, after)
  → Bloom filter 初期化 (delta_computation.rs:356-372)
  → SHA-256 ハッシュ比較で content_hash 変更検出
  → 並列処理オプション (parallel_computation=true)
  
  節点レベルで:
    added: before にない
    removed: after にない
    modified: content_hash が異なる
```

出典:
- `delta_computation.rs:308-354`（compute_delta）
- `delta_computation.rs:374-459`（compute_node_delta）
- `delta_computation.rs:534-571`（compute_node_modification、property_changes 追跡）

**出力** (delta_computation.rs:122-147)
```
GraphDelta {
  from_snapshot, to_snapshot, computed_at,
  nodes_added: Vec<NodeSnapshot>,
  nodes_removed: Vec<String>,
  nodes_modified: Vec<NodeModification>,  // old_hash, new_hash, property_changes
  edges_added, edges_removed, edges_modified,
  statistics: DeltaStatistics {
    computation_time_ms,
    nodes_compared, edges_compared,
    nodes_changed, edges_changed,
    change_percentage,
    bloom_filter_hits, bloom_filter_misses
  }
}
```

出典: `delta_computation.rs:122-220`

#### 6. Async Batch 処理

**スループット**: 1000+ ops/sec を目標（コメント: async_batch.rs:4）

**アーキテクチャ** (async_batch.rs:206-260)
```
Tokio mpsc channel
  → UpdateOperation をバッファ (channel_buffer_size=1000)
  → 集約スレッド: max_batch_size=100 or max_batch_delay_ms=1000 でバッチ化
  → ワーカースレッド (num_workers=4): 並列処理
  → Rayon: バッチ内 op の CPU バウンド処理を並列化
```

出典: 
- `async_batch.rs:26-50`（AsyncBatchConfig）
- `async_batch.rs:234-260`（AsyncBatchUpdater::new）
- `async_batch.rs:294-437`（start() による collector・worker spawn）

**Back-pressure 機構** (async_batch.rs:269-288)
```
if enable_backpressure && queue_size >= max_queue_size (=10000):
  sleep 10ms までループして待機
```

出典: `async_batch.rs:269-288`

### 入力・出力サマリー

| フェーズ | 入力 | 出力 |
|---------|------|------|
| 変更検出 | DocumentContent | UpdateSummary / 空 |
| 抽出 | DocumentContent | ExtractionResult {entities, relationships, concepts} |
| グラフ適用 | ExtractionResult | UpdateSummary {nodes_added/updated/removed, edges_added/updated/removed, time_taken_ms} |
| Lazy Propagation | PendingUpdate queue | PropagationResult {updates_processed, updates_failed, dirty_nodes_cleared, dirty_edges_cleared, time_taken_ms} |
| Delta 計算 | GraphSnapshot 2つ | GraphDelta {added/removed/modified nodes/edges, statistics} |

---

## 3.6 Storage / Persistence

### ファイル構成
- `/vendor/graphrag-rs/graphrag-core/src/persistence/mod.rs` (84行)
- `/vendor/graphrag-rs/graphrag-core/src/persistence/workspace.rs` (200+行)
- `/vendor/graphrag-rs/graphrag-core/src/persistence/parquet.rs` (150+行)
- `/vendor/graphrag-rs/graphrag-core/src/vector/mod.rs` (955行)
- `/vendor/graphrag-rs/graphrag-core/src/vector/memory_store.rs` (82行)
- `/vendor/graphrag-rs/graphrag-core/src/vector/store.rs` (42行)

### Persistence trait (mod.rs:68-83)

```rust
pub trait Persistence {
    fn save(&self, path: &str) -> Result<()>;
    fn load(path: &str) -> Result<Self> where Self: Sized;
    fn exists(path: &str) -> bool;
    fn size(path: &str) -> Result<u64>;
}
```

出典: `persistence/mod.rs:68-83`

### WorkspaceManager (workspace.rs:73-200+)

**マルチワークスペース対応**
```
workspace/
  ├── default/
  │   ├── entities.parquet
  │   ├── relationships.parquet
  │   ├── chunks.parquet
  │   ├── documents.parquet
  │   ├── vectors.lance/
  │   ├── graph.json
  │   └── metadata.toml
  └── project_a/
      └── ...
```

出典: `persistence/mod.rs:16-26`（コメント）

**主要メソッド** (workspace.rs:79-200)
- `new(base_dir)` - ワークスペース マネージャ初期化
- `create_workspace(name)` - 新ワークスペース作成 + metadata.toml 保存
- `save_graph(graph, workspace_name)` - グラフをワークスペースに保存
- `load_graph(workspace_name)` - グラフをワークスペースから読み込み
- `list_workspaces()` - すべてのワークスペース一覧
- `delete_workspace(name)` - ワークスペース削除

出典: `workspace.rs:91-195`

**WorkspaceMetadata** (workspace.rs:10-57)
```rust
pub struct WorkspaceMetadata {
    name: String,
    created_at, modified_at: DateTime<Utc>,
    entity_count, relationship_count, document_count, chunk_count: usize,
    format_version: String,  // "1.0"
    description: Option<String>,
}
```

出典: `workspace.rs:10-47`

### Parquet バックエンド (parquet.rs:63-140)

**ParquetPersistence** (parquet.rs:99-140)
```rust
pub struct ParquetPersistence {
    base_dir: PathBuf,
    config: ParquetConfig {
        compression: ParquetCompression {Uncompressed|Snappy|Gzip|Lz4|Zstd},
        row_group_size: usize,  // 10000
        dictionary_encoding: bool,
    }
}
```

**保存ファイル**（推定、parquet.rs:9-14 ドキュメント参照）
- entities.parquet - エンティティノード（列: id, label, type, attributes, embeddings, created_at, updated_at, version）
- relationships.parquet - 関係エッジ（列: source_id, target_id, type, weight, attributes, created_at）
- chunks.parquet - テキスト断片
- documents.parquet - ドキュメント メタデータ

出典: `parquet.rs:1-40`（ドキュメント・型定義）

**推測**: JSON / JSONL バックエンド（mod.rs コメント:10）は別実装の可能性

### Vector Store (vector/store.rs:1-42)

**VectorStore trait**
```rust
#[async_trait]
pub trait VectorStore: Send + Sync {
    async fn initialize(&self) -> Result<()>;
    async fn add_vector(&self, id: &str, embedding: Vec<f32>, metadata) -> Result<()>;
    async fn add_vectors_batch(&self, vectors) -> Result<()>;
    async fn search(&self, query_embedding: &[f32], top_k: usize) -> Result<Vec<SearchResult>>;
    async fn delete(&self, id: &str) -> Result<()>;
}
```

出典: `vector/store.rs:17-42`

**SearchResult** (vector/store.rs:6-14)
```rust
pub struct SearchResult {
    id: String,
    score: f32,  // cosine similarity, higher=better
    metadata: HashMap<String, String>,
}
```

**MemoryVectorStore** (memory_store.rs:10-81)
- シンプルなインメモリ実装（テスト・デフォルト）
- `HashMap<String, (Vec<f32>, HashMap<String, String>)>` ベース
- cosine similarity で検索

出典: `memory_store.rs:11-81`

### Vector Index (vector/mod.rs:65-522)

**VectorIndex** （オプション HNSW インデックス）
```rust
pub struct VectorIndex {
    #[cfg(feature = "vector-hnsw")]
    index: Option<instant_distance::HnswMap<Vector, String>>,
    embeddings: HashMap<String, Vec<f32>>,
}
```

**メソッド**
- `add_vector(id, embedding)` - ベクトル追加
- `build_index()` - HNSW インデックス構築（オプション）
- `search(query, top_k)` - 類似検索（HNSW あり/なし両対応）

**Hash-based Fallback** (vector/mod.rs:170-205)
```
HNSW unavailable → cosine_similarity で brute-force 検索
```

出典: `vector/mod.rs:144-187`

### 永続化形式と粒度

| コンポーネント | 保存対象 | 保存されない |
|--------------|---------|-----------|
| Entity | id, label, type, attributes, embeddings, version, timestamp | リアルタイムキャッシュ |
| Relationship | source_id, target_id, type, weight, attributes, timestamp | 計算済み統計 |
| TextChunk | id, text, source_doc_id, metadata | スパン位置情報（オプション） |
| Document | id, title, source, metadata, timestamps | 生テキスト（参照のみ） |
| **Vector** | id, embedding, metadata | 距離計算キャッシュ |

**未保存**:
- Lazy Propagation の pending queue（再起動で喪失）
- Delta 計算の中間 snapshot（最後のスナップショットのみ保持）
- 一時的な dirty marker

---

## 3.7 Embedding

### ファイル構成
- `/vendor/graphrag-rs/graphrag-core/src/embeddings/mod.rs` (155行)
- `/vendor/graphrag-rs/graphrag-core/src/embeddings/ollama.rs` (100行)
- `/vendor/graphrag-rs/graphrag-core/src/embeddings/config.rs` (76行)
- `/vendor/graphrag-rs/graphrag-core/src/core/ollama_adapters.rs` (171行)

### EmbeddingProvider trait (embeddings/mod.rs:26-45)

```rust
#[async_trait]
pub trait EmbeddingProvider: Send + Sync {
    async fn initialize(&mut self) -> Result<()>;
    async fn embed(&self, text: &str) -> Result<Vec<f32>>;
    async fn embed_batch(&self, texts: &[&str]) -> Result<Vec<Vec<f32>>>;
    fn dimensions(&self) -> usize;
    fn is_available(&self) -> bool;
    fn provider_name(&self) -> &str;
}
```

出典: `embeddings/mod.rs:26-45`

### EmbeddingConfig (embeddings/mod.rs:49-76)

```rust
pub struct EmbeddingConfig {
    provider: EmbeddingProviderType {
        HuggingFace, OpenAI, VoyageAI, Cohere, JinaAI, Mistral, TogetherAI, 
        Onnx, Candle, Ollama, Custom(String)
    },
    model: String,
    api_key: Option<String>,
    cache_dir: Option<String>,
    batch_size: usize,  // 32 (default)
}
```

出典: `embeddings/mod.rs:49-76`

### OllamaEmbeddingsAdapter (ollama.rs + ollama_adapters.rs)

**OllamaEmbeddings** (ollama.rs:9-31)
```rust
pub struct OllamaEmbeddings {
    model: String,
    client: Ollama,
    dimensions: usize,  // 1024 (default)
}
```

**initialize()** (ollama.rs:35-44)
```
client.list_local_models().await
  → Ollama サーバへの接続確認
  → 失敗なら GraphRAGError::Embedding {message}
```

出典: `ollama.rs:35-44`

**embed()** (ollama.rs:46-73)
```
client.generate_embeddings(
    model: String,
    input: EmbeddingsInput::Single(text)
) → embeddings: Vec<Vec<f64>>
  → [0] を f32 に変換
  → Vec<f32>
```

出典: `ollama.rs:46-73`

**embed_batch()** (ollama.rs:75-85)
```
for text in texts:
    embed(text).await  // シーケンシャル処理
```

出典: `ollama.rs:75-85`

### OllamaEmbedderAdapter (ollama_adapters.rs:14-70)

**AsyncEmbedder trait 実装**

```rust
pub struct OllamaEmbedderAdapter {
    embeddings: OllamaEmbeddings,
    dimension: usize,
}
```

**メソッド**
- `new(model, dimension)` - 初期化
- `embed(&self, text) -> Result<Vec<f32>>` - EmbeddingProvider::embed をラップ
- `embed_batch(&self, texts) -> Result<Vec<Vec<f32>>>` - バッチ処理
- `dimension() -> usize` - 次元数返却
- `is_ready() -> bool` - EmbeddingProvider::is_available() から取得

出典: `ollama_adapters.rs:14-70`

### Hash-based Fallback Embedding

**推定実装**: `vector/mod.rs:568-732` の `EmbeddingGenerator`

```rust
pub struct EmbeddingGenerator {
    dimension: usize,
    word_vectors: HashMap<String, Vec<f32>>,
}

pub fn generate_embedding(&mut self, text: &str) -> Vec<f32> {
    words = text.split_whitespace()
    for word:
        word_vectors[word] = generate_word_vector(word)  // FNV-1a hash
    result = average(word_embeddings)
    normalize(result)
    return result
}

fn generate_word_vector(&self, word: &str) -> Vec<f32> {
    for i in 0..dimension:
        hash = DefaultHasher::new()
        hash(word + i)
        value = ((hash % 2000) as f32 - 1000.0) / 1000.0
        vector.push(value)
    normalize(vector)
    return vector
}
```

出典: `vector/mod.rs:595-651`

**特性**:
- 同じテキスト → 同じ embedding（決定的）
- モデル依存なし（オフライン）
- コスト: O(word_count * dimension)

### Embedding パイプライン（推定）

```
DocumentContent.text
  ├─→ EmbeddingProvider (Ollama / HuggingFace)
  │   └─→ initialize()
  │       → embed(text) or embed_batch(texts)
  │       → Vec<Vec<f32>>
  │
  ├─→ AsyncEmbedder trait (OllamaEmbedderAdapter)
  │   └─→ embed_batch_concurrent(texts, max_concurrent=8)
  │
  └─→ Fallback (EmbeddingGenerator)
      └─→ generate_embedding(text)
          → Hash-based Vec<f32>

    ↓ Storage
    Vector Store (MemoryVectorStore / LanceDB)
      add_vector(id, embedding, metadata)
      
    ↓ Indexing
    VectorIndex (HNSW オプション)
      add_vector(id, embedding)
      build_index()
      
    ↓ Retrieval
    search(query_embedding, top_k)
      → SearchResult {id, score=cosine_similarity, metadata}
```

出典: 複数ファイルの合成

---

## 3.8 LLM 統合

### ファイル構成
- `/vendor/graphrag-rs/graphrag-core/src/core/traits.rs` (1,461行)
- `/vendor/graphrag-rs/graphrag-core/src/core/ollama_adapters.rs` (171行)
- `/vendor/graphrag-rs/graphrag-core/src/generation/async_mock_llm.rs` (632行)
- `/vendor/graphrag-rs-claude-spike/graphrag-core/src/generation/claude_cli.rs` (276行)

### AsyncLanguageModel trait (traits.rs:541-624)

```rust
#[async_trait]
pub trait AsyncLanguageModel: Send + Sync {
    type Error: std::error::Error + Send + Sync + 'static;
    
    // Primary methods
    async fn complete(&self, prompt: &str) -> Result<String>;
    async fn complete_with_params(&self, prompt: &str, params: GenerationParams) -> Result<String>;
    
    // Batch operations
    async fn complete_batch(&self, prompts: &[&str]) -> Result<Vec<String>>;
    async fn complete_batch_concurrent(&self, prompts: &[&str], max_concurrent: usize) -> Result<Vec<String>>;
    
    // Streaming (optional)
    async fn complete_streaming(&self, prompt: &str) 
        -> Result<Pin<Box<dyn futures::Stream<Item = Result<String>> + Send>>>;
    
    // Availability & metadata
    async fn is_available(&self) -> bool;
    async fn model_info(&self) -> ModelInfo;
    
    // Health & stats
    async fn health_check(&self) -> Result<bool>;
    async fn get_usage_stats(&self) -> Result<ModelUsageStats>;
    async fn estimate_tokens(&self, prompt: &str) -> Result<usize>;
}
```

出典: `traits.rs:547-624`

### GenerationParams (traits.rs:640-660)

```rust
pub struct GenerationParams {
    max_tokens: Option<usize>,
    temperature: Option<f32>,  // 0.0=deterministic, 1.0=random
    top_p: Option<f32>,
    stop_sequences: Option<Vec<String>>,
}
// Default: max_tokens=1000, temperature=0.7, top_p=0.9
```

出典: `traits.rs:640-660`

### ModelInfo (traits.rs:663-674)

```rust
pub struct ModelInfo {
    name: String,
    version: Option<String>,
    max_context_length: Option<usize>,
    supports_streaming: bool,
}
```

出典: `traits.rs:663-674`

### ModelUsageStats (traits.rs:627-637)

```rust
pub struct ModelUsageStats {
    total_requests: u64,
    total_tokens_processed: u64,
    average_response_time_ms: f64,
    error_rate: f64,
}
```

出典: `traits.rs:627-637`

### OllamaLanguageModelAdapter (ollama_adapters.rs:72-152)

```rust
pub struct OllamaLanguageModelAdapter {
    client: OllamaClient,
    model_name: String,
}
```

**complete()** (ollama_adapters.rs:98-100)
```rust
async fn complete(&self, prompt: &str) -> Result<String> {
    self.client.generate(prompt).await
}
```

**complete_with_params()** (ollama_adapters.rs:102-119)
```rust
GenerationParams → OllamaGenerationParams {
    num_predict: max_tokens as u32,
    temperature,
    top_p,
    top_k: None,
    stop: stop_sequences,
    repeat_penalty: None,
    num_ctx: None,
    keep_alive: None,
    context: None,
}
→ self.client.generate_with_params(prompt, params)
```

出典: `ollama_adapters.rs:102-119`

**model_info()** (ollama_adapters.rs:127-134)
```rust
ModelInfo {
    name: format!("{}:{}", "llama3.2:3b", ...),
    version: None,
    max_context_length: Some(4096),
    supports_streaming: true,
}
```

出典: `ollama_adapters.rs:127-134`

**get_usage_stats()** (ollama_adapters.rs:136-151)
```rust
let stats = self.client.get_stats();
ModelUsageStats {
    total_requests: stats.get_total_requests(),
    total_tokens_processed: stats.get_total_tokens(),
    average_response_time_ms: 0.0,  // 未実装
    error_rate: failed as f64 / total as f64,
}
```

出典: `ollama_adapters.rs:136-151`

### AsyncMockLLM (generation/async_mock_llm.rs)

**用途**: テスト・デモ用

**メソッド** (async_mock_llm.rs:35-79)
```rust
pub async fn new() -> Result<Self>
pub async fn with_templates(templates: HashMap<String, String>) -> Result<Self>
pub fn set_simulate_delay(&mut self, delay: Option<Duration>)
```

**AsyncLanguageModel 実装** (async_mock_llm.rs:361-458)
- `complete(prompt)` - テンプレートベース応答生成
- `complete_batch(prompts)` - 並列処理（tokio::spawn）
- `is_available()` - 常に true
- `model_info()` - "AsyncMockLLM" v1.0.0
- `get_usage_stats()` - 要求数・トークン数カウント

出典: `async_mock_llm.rs:361-458`

### ClaudeCliLanguageModel (spec-grag 独自実装)

**ファイル**: `/vendor/graphrag-rs-claude-spike/graphrag-core/src/generation/claude_cli.rs`

**目的**: Claude Code CLI（`claude -p`）サブプロセス呼び出しで Sonnet / Opus へのアクセス

```rust
pub struct ClaudeCliLanguageModel {
    config: ClaudeCliConfig {
        command: String,  // "claude"
        model: String,    // "sonnet", "opus"
        extra_args: Vec<String>,
        timeout: Duration,  // 120s
    }
}
```

出典: `claude_cli.rs:15-36`

**build_args()** (claude_cli.rs:77-89)
```rust
vec![
    "-p",  // headless mode
    "--model", config.model,
    "--output-format", "json",
    "--no-session-persistence",
    "--dangerously-skip-permissions",
]
// NOTE: --bare は使用しない（OAuth subscription 認証との非互換）
```

出典: `claude_cli.rs:77-89`

**invoke()** (claude_cli.rs:92-133)
```rust
Command::new(config.command)
    .args(build_args())
    .arg(prompt)
    .stdin(Stdio::null())
    .stdout(Stdio::piped())
    .stderr(Stdio::piped())
    .spawn()
    .wait_with_output()  // timeout: 120s
→ stdout JSON parse
→ extract_result(): json.get("result").as_str()
```

出典: `claude_cli.rs:92-133`

**extract_result()** (claude_cli.rs:136-157)
```rust
fn extract_result(stdout: &str) -> Result<String> {
    json = serde_json::from_str(stdout.trim())
    result = json.get("result").and_then(|v| v.as_str())
    // 失敗時: GraphRAGError::Generation
    Ok(result.to_string())
}
```

出典: `claude_cli.rs:136-157`

**AsyncLanguageModel 実装** (claude_cli.rs:166-203)
- `complete(prompt)` - `invoke(prompt)` を呼び出し
- `complete_with_params(prompt, params)` - params は無視（プロンプトで調整）
- `is_available()` - `claude --version` の実行確認
- `model_info()` - `model_info: ModelInfo {name: "claude-cli:sonnet", max_context_length: 200_000, supports_streaming: false}`

出典: `claude_cli.rs:166-203`

**テスト** (claude_cli.rs:216-275)
- `extract_result()` の JSON パース確認
- `build_args()` に `--bare` がないことを検証

出典: `claude_cli.rs:216-275`

### LLM 統合の trait 階層図

```
AsyncLanguageModel trait (async/await)
    ├─ complete(prompt) → String
    ├─ complete_with_params(prompt, GenerationParams) → String
    ├─ complete_batch(&[&str]) → Vec<String>
    ├─ complete_batch_concurrent(&[&str], max_concurrent) → Vec<String>
    ├─ complete_streaming(prompt) → Stream<String>
    ├─ is_available() → bool
    ├─ model_info() → ModelInfo
    ├─ health_check() → bool
    ├─ get_usage_stats() → ModelUsageStats
    └─ estimate_tokens(prompt) → usize

Implementations:
  ├─ OllamaLanguageModelAdapter (Ollama ローカル LLM)
  │   client: OllamaClient
  │   model_name: String
  │
  ├─ AsyncMockLLM (テスト用)
  │   response_templates: HashMap<String, String>
  │   text_processor: TextProcessor
  │   stats: AsyncLLMStats
  │
  └─ ClaudeCliLanguageModel (spec-grag)
      command: "claude"
      model: "sonnet" | "opus"
      timeout: 120s
      stdin/stdout via subprocess
```

### 推定される統合フロー

```
Knowledge Graph Construction
  │
  ├─ Entity Extraction
  │   └─ AsyncLanguageModel::complete(prompt: "Extract entities from: {text}")
  │
  ├─ Relationship Inference
  │   └─ AsyncLanguageModel::complete(prompt: "Infer relationships: {entities}")
  │
  ├─ Hierarchical Clustering Summary
  │   └─ ClaudeCliLanguageModel::complete(prompt: "Summarize cluster: {nodes}")
  │       (Sonnet/Opus で高品質サマリー)
  │
  └─ Entity/Relationship Properties
      └─ complete_batch([prompts]) for parallel enrichment
```

---

## 統合と連携

### Incremental Update → Storage フロー

```
DocumentContent (変更)
  ↓ [change detection: SHA-256]
IncrementalGraphManager.add_content()
  ↓ [lazy propagation queue]
PendingUpdate (on threshold/time/query)
  ↓ [propagate]
DirtyTracker cleared
  ↓ [delta computation]
GraphDelta {added/removed/modified}
  ↓ [persistence]
WorkspaceManager.save_graph()
  ├─ ParquetPersistence (entities.parquet, relationships.parquet)
  ├─ VectorStore.add_vectors_batch() (embedding persist)
  └─ metadata.toml (WorkspaceMetadata)
```

出典: 複数モジュール合成

### Embedding → Vector Store → Retrieval フロー

```
GraphNode.embeddings: Option<Vec<f32>>
  ↓ [not present → generate]
EmbeddingProvider::embed(text)
  ├─ OllamaEmbeddingsAdapter.embed(text)
  │   → client.generate_embeddings() → Vec<f32>
  └─ EmbeddingGenerator.generate_embedding(text)
      → Hash-based fallback
  ↓
VectorStore::add_vector(node_id, embedding, metadata)
  ├─ MemoryVectorStore {HashMap<String, (Vec<f32>, metadata)>}
  └─ LanceDB / Qdrant (オプション)
  ↓
VectorIndex.build_index()
  └─ HNSW (if feature enabled)
  ↓
Retrieval Query
  VectorStore::search(query_embedding, top_k=10)
  → Vec<SearchResult> {id, score (cosine), metadata}
```

出典: 複数ファイル

### LLM 統合フロー

```
Hierarchical Summarization Task
  │
  ├─ Check availability
  │   AsyncLanguageModel::is_available() → bool
  │
  ├─ Estimate resource
  │   AsyncLanguageModel::estimate_tokens(prompt) → usize
  │
  ├─ Single completion
  │   AsyncLanguageModel::complete(prompt) → String
  │   or
  │   AsyncLanguageModel::complete_with_params(prompt, GenerationParams) → String
  │
  ├─ Batch processing
  │   AsyncLanguageModel::complete_batch(prompts) 
  │   or
  │   AsyncLanguageModel::complete_batch_concurrent(prompts, max_concurrent=4)
  │
  ├─ Stream (if supported)
  │   AsyncLanguageModel::complete_streaming(prompt) → Stream<Result<String>>
  │
  └─ Monitoring
      AsyncLanguageModel::get_usage_stats() 
      → ModelUsageStats {total_requests, total_tokens_processed, error_rate}

Provider Selection:
  ├─ OllamaLanguageModelAdapter
  │   (local LLM, no auth, latency higher)
  │
  ├─ AsyncMockLLM
  │   (testing, template-based)
  │
  └─ ClaudeCliLanguageModel
      (spec-grag: Claude Code CLI subprocess)
      - Sonnet (default: speed + quality balance)
      - Opus (optional: maximum quality)
      - Fallback to system ANTHROPIC_API_KEY or OAuth
```

出典: 複合推定

---

## 未確認項目

### Embedding 関連
1. **EmbeddingGenerator の精度**: コサイン類似度でのランキング検証状況 (推測: テスト用に十分)
2. **Ollama 多モデル サポート**: `nomic-embed-text` 以外で検証されたモデル (未記載)
3. **Batch embedding での次元数チェック**: 異なる次元のテキスト群の処理 (未確認)

### Storage 関連
1. **LanceDB・Qdrant サポート**: `/vendor/graphrag-rs/graphrag-core/src/vector/lancedb.rs` / `qdrant.rs` の詳細な実装（ファイル確認のみ）
2. **JSON / JSONL バックエンド**: `persistence/mod.rs` で言及 (実装ファイル未読)
3. **Corpus 管理** (`corpus/` ディレクトリ): 記載なし

### Incremental Update 関連
1. **extract_from_content() の実装**: 現在スケルトン (mod.rs:862-869)
  - NLP パイプラインの詳細は別モジュール推定
2. **ConflictResolution::HighestConfidence の confidence スコア**: 抽出時のスコア形式（未定義）
3. **Lazy Propagation の「依存グラフ」**: add_dependency() は登録（lazy_propagation.rs:513-518）だが、実際の伝播（apply_update:471-477）は未実装

### LLM 関連
1. **StreamSupport**: traits.rs:589-597 で型定義のみ、実装は OllamaLanguageModelAdapter で false
2. **ClaudeCliLanguageModel での params 無視**: 温度・top_p を制御不可（プロンプト調整が唯一の手段）
3. **Token estimation**: estimate_tokens() は雑な近似 (prompt.len()/4)

### Delta Computation 関連
1. **Bloom filter の偽陽性率**: デフォルト 0.01（1%）で検証状況（未確認）
2. **Parallel processing の実際の speedup**: rayon による実測値（未記載）

---

## まとめ表

| 機能 | モジュール | 実装状況 | 入力 | 出力 | 制約・トレードオフ |
|------|-----------|--------|------|------|------------------|
| **Incremental Update** | incremental/* | 完成度: 中～高 | DocumentContent | UpdateSummary | extract_from_content() スケルトン |
| **Lazy Propagation** | lazy_propagation.rs | 高 | PendingUpdate queue | PropagationResult | apply_update() 未実装 (プレースホルダ) |
| **Delta Computation** | delta_computation.rs | 高 | 2x GraphSnapshot | GraphDelta | Bloom filter 有効性検証未記載 |
| **Async Batching** | async_batch.rs | 高 | UpdateOperation stream | BatchResult | 1000+ ops/sec 目標 (実測未記載) |
| **Storage** | persistence/* | 中 | KnowledgeGraph | Parquet / JSON | LanceDB・Qdrant は feature gate |
| **Workspace** | workspace.rs | 中 | graph + metadata | workspace dir | 多ワークスペース対応 |
| **Embedding** | embeddings/* | 高 | String (text) | Vec<f32> | Fallback: hash-based, Ollama + 複数プロバイダ |
| **Vector Store** | vector/* | 高 | Vec<f32> + metadata | SearchResult | HNSW オプション, memory + persistent backends |
| **AsyncLanguageModel** | traits.rs | 完成度: 高 | prompt + params | String / Stream | 抽象設計, 実装ごとに機能異なる |
| **OllamaAdapter** | ollama_adapters.rs | 高 | OllamaConfig | OllamaLanguageModelAdapter | ローカル推論のみ, 潜在 |
| **ClaudeCliAdapter** | claude_cli.rs | 高 | ClaudeCliConfig | ClaudeCliLanguageModel | 次数: 120s timeout, subprocess 形式 |

---

## 参考資料・ファイル一覧

**Incremental Update**:
- `/vendor/graphrag-rs/graphrag-core/src/incremental/mod.rs:1-1219`
- `/vendor/graphrag-rs/graphrag-core/src/incremental/delta_computation.rs` (Bloom filter, SHA-256, parallel)
- `/vendor/graphrag-rs/graphrag-core/src/incremental/lazy_propagation.rs` (80-90% 削減)
- `/vendor/graphrag-rs/graphrag-core/src/incremental/async_batch.rs` (Tokio + Rayon)

**Storage/Persistence**:
- `/vendor/graphrag-rs/graphrag-core/src/persistence/mod.rs`
- `/vendor/graphrag-rs/graphrag-core/src/persistence/workspace.rs` (マルチワークスペース)
- `/vendor/graphrag-rs/graphrag-core/src/persistence/parquet.rs` (Parquet columnar)

**Embedding**:
- `/vendor/graphrag-rs/graphrag-core/src/embeddings/mod.rs` (EmbeddingProvider trait)
- `/vendor/graphrag-rs/graphrag-core/src/embeddings/ollama.rs` (OllamaEmbeddings)
- `/vendor/graphrag-rs/graphrag-core/src/core/ollama_adapters.rs` (OllamaEmbedderAdapter)
- `/vendor/graphrag-rs/graphrag-core/src/vector/mod.rs` (Hash-based fallback, VectorIndex)
- `/vendor/graphrag-rs/graphrag-core/src/vector/memory_store.rs` (MemoryVectorStore)
- `/vendor/graphrag-rs/graphrag-core/src/vector/store.rs` (VectorStore trait)

**LLM 統合**:
- `/vendor/graphrag-rs/graphrag-core/src/core/traits.rs:541-624` (AsyncLanguageModel)
- `/vendor/graphrag-rs/graphrag-core/src/core/ollama_adapters.rs:72-152` (OllamaLanguageModelAdapter)
- `/vendor/graphrag-rs/graphrag-core/src/generation/async_mock_llm.rs` (テスト用 mock)
- `/vendor/graphrag-rs-claude-spike/graphrag-core/src/generation/claude_cli.rs` (spec-grag 独自)

---

# §D. Agent 4：graphrag-rs 公式 docs の体系的読解

**タスク**：3.11（vendor/*.md 公式ドキュメント群）を網羅的に Read。対象は README.md / HOW_IT_WORKS.md / graphrag-core/README.md / ENTITY_EXTRACTION.md / ADVANCED_FEATURES.md / PIPELINE_ARCHITECTURE.md / MULTI_DOCUMENT_PIPELINE.md / OLLAMA_INTEGRATION.md / LEIDEN_INTEGRATION.md / LIGHTRAG_INTEGRATION.md / CROSS_ENCODER_INTEGRATION.md / HIPPORAG_INTEGRATION.md / ENRICHMENT_IMPLEMENTATION.md / graphrag-server/README.md / report.md / Changelog.md / TODO.md / examples/*.rs（一部）。

**実行**：2026-04-27、Agent (Explore)、tool_use_id=`toolu_01EuD7tpXo1NUtW8crj3oEFq`。

**未確認の自己申告**：WEBLLM_INTEGRATION.md / BURN_WASM_STATUS.md / DW-GRPO 実装ファイル / Symbolic Anchoring 実装ファイル / Causal Chain Analysis 詳細アルゴリズム / RoGRAG 実装 / examples/04_with_ollama.rs / examples/05_batch_processing.rs。

---

## graphrag-rs 公式ドキュメント体系的調査報告書

spec-grag プロジェクトの設計基盤構築のため、graphrag-rs 公式ドキュメント全体を体系的に調査しました。本報告書は著者（graphrag-rs 開発者）の主張を記録し、推測との分離を厳格に行っています。

---

## 1. 主要ドキュメント概要

### 1.1 README.md（/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/README.md）

**主旨**（行1-5）
graphrag-rs は Rust 実装の高性能 GraphRAG で、サーバー専用・WASM クライアント専用・ハイブリッドの 3 つの展開アーキテクチャをサポートする。50,000+ 行の実装が 5 つの最新論文（2019-2025）を統合している。

**重要な設計判断**

| 項目 | 内容 | 行番号 |
|------|------|--------|
| **3 つのデプロイアーキテクチャ** | Server-Only（本番環境）/ WASM-Only（クライアント100%）/ Hybrid（計画中） | 57-114 |
| **最新技術統合** | LightRAG（6000x トークン削減）/ Leiden（+15% モジュール性）/ Cross-Encoder（+20% 精度）/ HippoRAG（10-30x 低コスト）/ Semantic Chunking | 117-131 |
| **モジュール構成** | graphrag-core（ポータブル）/ graphrag-wasm / graphrag-leptos / graphrag-server / main crate | 765-789 |
| **特性フラグシステム** | memory-storage / persistent-storage / redis-storage / parallel / caching / incremental / pagerank / lightrag / rograg / ollama / neural-embeddings / cuda / metal / webgpu / code-chunking | 798-830 |
| **相互排他的な特性** | persistent-storage と neural-embeddings は依存関係衝突で排他 | 832-840 |

**出典**
- ファイル: README.md
- 特に行: 1-10（プロジェクト概要）、117-131（技術面）、765-789（アーキテクチャ）、798-830（特性フラグ）

---

### 1.2 HOW_IT_WORKS.md（/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/HOW_IT_WORKS.md）

**主旨**（行1-19）
GraphRAG は文章を知識グラフに変換して質問に答える。図書館員が本を読んで索引を作るのと同じ。7 段階のパイプライン（Chunking → Entity → Relationship → Graph → Embedding → Retrieval → Generation）をサポート。

**重要な設計判断**

| 段階 | 説明 | 設定駆動 | 行番号 |
|------|------|---------|--------|
| **1. Chunking** | テキスト分割、デフォルト 300 tokens | chunk_size, chunk_overlap | 356-359 |
| **2. Entity Extraction** | キーワード抽出、LLM ベース gleaning | approach: semantic/algorithmic/hybrid | 357-365 |
| **3. Relationship** | エンティティ関連の発見、gleaning | extract_relationships, use_gleaning | 359-365 |
| **4. Graph Construction** | PageRank, Community Detection（Leiden） | enable_pagerank, max_connections | 359-365 |
| **5. Embedding** | ベクトル化（遅延評価） | backend, dimension, model | 365-378 |
| **6. Retrieval** | 関連情報検索、複数戦略 | strategy: vector/hybrid/pagerank | 365-378 |
| **7. Generation** | LLM で回答合成 | chat_model, temperature | 365-378 |

**3 つのアプローチ**（行92-225）
- **Semantic（神経/LLM）**: 高品質（90-95%）、低速（100-500 docs/sec）、高リソース（4-8GB）
- **Algorithmic（パターン）**: 低品質（70-85%）、高速（1000-5000 docs/sec）、低リソース（1-2GB）
- **Hybrid（融合）**: 中品質（85-95%）、中速（200-1000 docs/sec）、中リソース（3-4GB）

各アプローチは TOML の `[mode] approach` で選択、実装自動選択（行253-276）。

**出典**
- ファイル: HOW_IT_WORKS.md
- 特に行: 33-88（設定駆動パイプライン）、92-225（3 つのアプローチ）、253-276（実装選択）

---

### 1.3 graphrag-core/README.md（コア機能）

**主旨**（行1-15）
graphrag-core は移植可能なコアライブラリで、ネイティブと WASM の両方で動作。8 つの埋め込みプロバイダ、真の LLM gleaning 抽出、増分更新、12+ トレイト抽象化をサポート。

**3 つの設定方法**（行64-141）
1. **TypedBuilder**: コンパイル時安全性（必須フィールドチェック）
2. **Hierarchical Config（figment）**: ~/.graphrag / ./graphrag.toml / 環境変数の 5 層
3. **TOML ファイル**: 直接設定

**テンプレート駆動設計**
| テンプレート | 対象 | エンティティタイプ |
|-----------|------|------|
| general.toml | 混合文書 | PERSON, ORGANIZATION, LOCATION, DATE, EVENT |
| legal.toml | 契約書 | PARTY, JURISDICTION, CLAUSE_TYPE, OBLIGATION |
| medical.toml | 臨床記録 | PATIENT, DIAGNOSIS, MEDICATION, SYMPTOM |
| financial.toml | 報告書 | COMPANY, TICKER, MONETARY_VALUE, METRIC |
| technical.toml | API / コード | FUNCTION, CLASS, MODULE, API_ENDPOINT |

**出典**
- ファイル: graphrag-core/README.md
- 特に行: 1-15（概要）、64-141（3 つの設定方法）、143-152（テンプレート）

---

### 1.4 ENTITY_EXTRACTION.md（LLM ベース抽出）

**主旨**（行1-8）
真の LLM ベース gleaning 抽出を実装。Microsoft GraphRAG 方式に従う。複数ラウンドの反復改良を行う。パターンマッチングではなく、実際の API 呼び出し。

**アーキテクチャ**（行11-36）
```
GleaningEntityExtractor（N ラウンド調整）
  ↓
LLMEntityExtractor（Ollama API 呼び出し）
  ├─ extract_from_chunk()    - 初期抽出
  ├─ extract_additional()    - gleaning 継続
  └─ check_completion()      - LLM 完了判定
  ↓
PromptBuilder（Microsoft GraphRAG スタイル）
```

**GleaningConfig パラメータ**（行129-137）
```rust
max_gleaning_rounds: usize,           // デフォルト: 4
completion_threshold: f64,            // デフォルト: 0.8
entity_confidence_threshold: f64,     // デフォルト: 0.7
use_llm_completion_check: bool,       // デフォルト: true
entity_types: Vec<String>,            // 必須
temperature: f32,                     // デフォルト: 0.1
max_tokens: usize,                    // デフォルト: 1500
```

**出典**
- ファイル: ENTITY_EXTRACTION.md
- 特に行: 1-36（アーキテクチャ）、129-137（GleaningConfig）、142-170（実装詳細）

---

### 1.5 ADVANCED_FEATURES.md（2025-2026 技術）

**主旨**（行1-13）
9 つの最新技術を 4 つのフェーズで実装：
- Phase 1: Foundation（Triple Reflection / Temporal Fields / ATOM）✅ 完了
- Phase 2: Retrieval Enhancement ✅ 完了
- Phase 3: Advanced Optimization ✅ 完了
- Phase 4: Polish & Integration ✅ 完了

**Phase 1: Foundation Layer**

| 技術 | 主旨 | 行番号 |
|------|------|--------|
| **Triple Reflection** | エンティティ-関係トリプルを LLM で検証、ハルシネーション削減（30-50%） | 18-52 |
| **Temporal Fields** | エンティティ/関係に時間メタデータ追加、時間対応クエリ有効化 | 53-127 |
| **ATOM Atomic Facts** | 5-タプル事実抽出：(Subject, Predicate, Object, Temporal, Confidence) | 131-200 |

**出典**
- ファイル: ADVANCED_FEATURES.md
- 特に行: 1-13（概要）、18-52（Triple Reflection）、53-127（Temporal）、131-200（ATOM）

---

### 1.6 PIPELINE_ARCHITECTURE.md（7 段階詳細）

**主旨**（行1-10）
7 フェーズアーキテクチャの詳細仕様。各フェーズで設定可能なパラメータと推奨値を記載。

**科学的基礎**（行155-168）

| フェーズ | 技術 | 論文 / インスピレーション | 影響 |
|---------|------|----------------------|------|
| **1. Chunking** | Semantic Chunking | LangChain / Gregory Kamradt (2024) | セマンティック境界を尊重 |
| **2. Extraction** | Gleaning | Microsoft GraphRAG (2024) | 反復抽出で見逃し削減 |
| **4. Graph** | Leiden Algorithm | Traag et al. (Nature, 2019) | Louvain 比で +15% モジュール性 |
| **6. Retrieval** | Fast-GraphRAG | Pang et al. (2024) | 27x 性能向上 |
| **6. Retrieval** | LightRAG | Zhang et al. (2024) | 6000x トークン削減 |
| **6. Retrieval** | HippoRAG | He et al. (NeurIPS 2024) | PPR で +20% 精度 |
| **6. Retrieval** | Cross-Encoder | Reimers et al. (2019) | Reranking で +20% 精度向上 |

**出典**
- ファイル: PIPELINE_ARCHITECTURE.md
- 特に行: 1-144（フェーズ詳細）、155-168（科学的基礎）

---

### 1.7 MULTI_DOCUMENT_PIPELINE.md（マルチドキュメント実装例）

**主旨**（行1-34）
複数文書から知識グラフを構築する完全なエンドツーエンドパイプライン。増分更新対応。Symposium（2691 エンティティ）と Tom Sawyer を例に。

**3 つのフェーズ**（行37-72）
1. **Phase 1**: Symposium 読み込み → 238 チャンク → 189 エンティティ
2. **Phase 2**: Tom Sawyer マージ → 492 チャンク → 429 新規エンティティ + 58 重複解決
3. **Phase 3**: RRF（Reciprocal Rank Fusion）でクロスドキュメントクエリ

**RRF アルゴリズム**（行74-90）
```
RRF_score = Σ (1 / (k + rank))
k = 60 (RRF 定数)
```

利点：スコア正規化不要、複数ソース結果ロバスト、検索エンジン標準採用。

**出典**
- ファイル: examples/MULTI_DOCUMENT_PIPELINE.md
- 特に行: 1-34（概要）、37-72（3 フェーズ）、74-90（RRF）

---

### 1.8 OLLAMA_INTEGRATION.md（ローカル LLM）

**主旨**（行1-5）
Ollama との完全統合で、ローカル LLM 推論と埋め込みをサポート。ストリーミング、キャッシング、メトリクストラッキング。

**ServiceConfig（推奨方式）**（行26-46）
```rust
pub struct ServiceConfig {
    ollama_base_url: Some("http://localhost:11434"),
    embedding_model: Some("nomic-embed-text:latest"),
    language_model: Some("llama3.2:latest"),
    vector_dimension: Some(768),
}

let registry = config.build_registry().build();
// すべてのサービスが登録・準備完了
```

**サポートモデル表**（行84-100）
| モデル | サイズ | 用途 |
|-------|--------|------|
| llama3.2:3b | 3B | 軽量・高速生成 |
| llama3.2:latest | 8B | バランス型 |
| mistral:latest | 7B | 高品質応答 |
| nomic-embed-text:latest | 768-dim | 一般テキスト埋め込み |

**出典**
- ファイル: OLLAMA_INTEGRATION.md
- 特に行: 1-5（概要）、26-46（ServiceConfig）、84-100（モデル表）

---

### 1.9 LEIDEN_INTEGRATION.md（コミュニティ検出）

**主旨**（行1-10）
Leiden アルゴリズムの統合。3 フェーズ（Local Moving / Refinement / Aggregation）で Louvain より +15% モジュール性。

**LeidenConfig**（行61-68）
```rust
pub struct LeidenConfig {
    max_cluster_size: 10,
    use_lcc: true,              // 最大連結成分使用
    seed: Some(42),             // 再現性
    resolution: 1.0,            // モジュール性解像度
    max_levels: 5,              // 階層深度
    min_improvement: 0.001,
}
```

**HierarchicalCommunities**
- マルチレベルコミュニティ構造
- エンティティメタデータマッピング
- 自動サマリー生成（抽出的 + LLM 対応）
- 下から上へのサマリー生成

**出典**
- ファイル: LEIDEN_INTEGRATION.md
- 特に行: 1-10（概要）、61-68（LeidenConfig）、29-36（HierarchicalCommunities）

---

### 1.10 LIGHTRAG_INTEGRATION.md（トークン削減）

**主旨**（行1-5）
LightRAG デュアルレベル検索で 6000x トークン削減（EMNLP 2025）。高レベル（トピック）と低レベル（エンティティ）の並列検索。

**アーキテクチャ**（行14-27）
1. **KeywordExtractor**: 高レベル + 低レベルキーワード抽出、<20 キーワード制限
2. **DualLevelRetriever**: 2 粒度での並列検索、4 つのマージ戦略
3. **SemanticSearcher trait**: 埋め込み + ベクトルストア抽象化

**4 つのマージ戦略**（行128-133）
- Interleave: 交互マージ
- HighFirst: トピック優先
- LowFirst: エンティティ優先
- Weighted: スコアベース（重み設定可能）

**パフォーマンス（LightRAG 論文）**（行136-142）
- Token Reduction: 6000x（600-10k → <100 tokens）
- API Cost: 99% 削減
- Latency: 3-5x 高速化
- Accuracy: 従来 GraphRAG と同等以上

**出典**
- ファイル: LIGHTRAG_INTEGRATION.md
- 特に行: 1-5（概要）、14-27（アーキテクチャ）、128-133（マージ戦略）、136-142（パフォーマンス）

---

### 1.11 CROSS_ENCODER_INTEGRATION.md（精度向上）

**主旨**（行1-5）
Cross-Encoder reranking で +20% 精度向上（EMNLP 2019）。ジョイント query-document エンコーディングで正確性を向上。

**2 段階検索パイプライン**（行126-150）
```
Stage 1 (高速): Query → Bi-Encoder → Vector Search → Top-100
Stage 2 (精密): Query + Candidate → Cross-Encoder → Top-10
```

**CrossEncoderConfig**（行34-37）
```rust
pub struct CrossEncoderConfig {
    model_name: "cross-encoder/ms-marco-MiniLM-L-6-v2",
    max_length: 512,
    batch_size: 32,
    top_k: 10,
    min_confidence: 0.0,
    normalize_scores: true,
}
```

**人気モデル**（行98-106）
- `cross-encoder/ms-marco-MiniLM-L-6-v2` - 高速・高品質（デフォルト）
- `cross-encoder/ms-marco-MiniLM-L-12-v2` - より高品質
- `cross-encoder/ms-marco-electra-base` - 高品質
- `cross-encoder/qnli-electra-base` - 質問応答最適化

**出典**
- ファイル: CROSS_ENCODER_INTEGRATION.md
- 特に行: 1-5（概要）、126-150（2 段階パイプライン）、34-37（CrossEncoderConfig）、98-106（モデル表）

---

### 1.12 HIPPORAG_INTEGRATION.md（グラフベース検索）

**主旨**（行1-7）
HippoRAG Personalized PageRank（PPR）で +20% 精度向上（NeurIPS 2024）。デュアルシグナル（事実 + 通路）でグラフベース検索。

**HippoRAGConfig**（行28-31）
```rust
damping_factor: 0.5,        // HippoRAG デフォルト（神経生物学的選択）
passage_node_weight: 0.05,  // 通路スケーリング係数
top_k_facts: 100,
top_k_results: 10,
```

**デュアルシグナル PPR**（行97-132）
1. **Entity Weights（事実シグナル）**: 高スコア・稀有事実からの関連性
2. **Passage Weights（検索シグナル）**: 直接関連通路の加重
3. **Personalized PageRank**: リセット確率の伝播

**Damping Factor 選択**（行137-145）
- HippoRAG default: 0.5（直接と連想のバランス）
- Standard PageRank: 0.85（グラフ構造重視）
- 0.5 の理由：海馬記憶モデルに着想（直接想起と連想検索の等価）

**出典**
- ファイル: HIPPORAG_INTEGRATION.md
- 特に行: 1-7（概要）、28-31（HippoRAGConfig）、97-132（デュアルシグナル）、137-145（Damping）

---

### 1.13 ENRICHMENT_IMPLEMENTATION.md（メタデータ充実化）

**主旨**（行1-16）
7 層の bottom-up アーキテクチャで、文書構造認識と意味メタデータ充実化を自動実装。

**ChunkMetadata（15 フィールド）**（行21）
- chapter, section, subsection, topic, keywords, summary
- structural_level, position_in_document, heading_path
- confidence ほか

**7 層アーキテクチャ**（行17-69）
1. Layer 1: Data Structures（ChunkMetadata）✅
2. Layer 2: Core Algorithms（TextAnalyzer, TfIdf, Summarizer）✅
3. Layer 3: Document Parsers（Markdown, PlainText, HTML, Factory）✅
4. Layer 4: Enrichment Pipeline（ChunkEnricher, Statistics）✅
5. Layer 5: Integration（TextProcessor methods）✅
6. Layer 6: Testing（13 tests all passing）✅
7. Layer 7: Examples（document_enrichment_demo.rs）✅

**実装済みパーサー**
| フォーマット | 検出方式 | 例 |
|-----------|--------|-----|
| Markdown | `#`, `##`, `###` | 標準マークダウン |
| HTML | `<h1>`-`<h6>` | Web コンテンツ |
| Plain Text | 下線/ALL CAPS/番号 | テキストファイル |

**出典**
- ファイル: ENRICHMENT_IMPLEMENTATION.md
- 特に行: 1-16（概要）、17-69（7 層）、71-88（フィーチャ）

---

### 1.14 graphrag-server/README.md（REST API）

**主旨**（行1-5）
本番環境 REST API サーバー。Actix-web 4.9 + Apistos（自動 OpenAPI 3.0.3 生成）に移行。Qdrant / LanceDB / インメモリバックエンド対応。

**ストレージバックエンド**（行9-28）
- ✅ Qdrant（100M+ ベクトル対応）
- ✅ LanceDB（組み込み、エッジ対応）
- ✅ グレースフルフォールバック（インメモリ）

**埋め込みシステム**（行14-24）
- ✅ Ollama 統合（ローカル）
- ✅ Hash ベースフォールバック（無依存）
- ✅ 自動検出（Ollama 優先）

**API エンドポイント**（行116-150）
- `GET /` - API 情報
- `GET /health` - ヘルスチェック（統計付き）
- ほか多数

**出典**
- ファイル: graphrag-server/README.md
- 特に行: 1-5（概要）、9-28（バックエンド）、14-24（埋め込み）

---

### 1.15 report.md（プロジェクト進化）

**主旨**（行1-3）
Dec 5, 2025 との比較レポート。最新の組織的・技術的変更をまとめる。

**新ディレクトリ / モジュール**（行9-19）
- `tests/e2e/` - End-to-End テスト・ベンチマークフレームワーク
- `graphrag-core/src/incremental/` - 増分グラフ更新（async_batch / delta_computation / lazy_propagation）
- `graphrag_py/` - Rust → Python バインディング（uv + maturin）

**技術的追加（Phase 2-3）**（行24-53）
- **Incremental Processing**: デルタ計算と遅延伝播
- **Leiden Algorithm**: コミュニティ検出
- **WASM Enhancement**: getrandom 0.3, tokenizers
- **Server Stack**: Actix-web 4.9, Apistos, ollama-rs, qdrant-client

**7 段階パイプライン進化（2025-2026）**（行42-76）
Phase 1-3 で実装済みの最新技術：
- cAST（コンテキスト対応分割）
- Dynamic Edge Weighting
- Causal Chain Analysis
- Hierarchical Clustering
- DW-GRPO（グラフ重み最適化）

**出典**
- ファイル: report.md
- 特に行: 1-3（概要）、9-19（新構成）、24-53（技術追加）、42-76（進化）

---

## 2. Examples ディレクトリ詳細

### 2.1 基本例

| ファイル | 主旨 | API レベル | 行番号 |
|---------|------|-----------|--------|
| **01_basic_usage.rs** | One-line API（最も単純） | Simple | 1-52 |
| **02_stateful_api.rs** | 複数クエリ向け状態保持 | Easy | 1-74 |
| **03_builder_api.rs** | カスタマイズ可能な構築 | Builder | 1-127 |
| **04_with_ollama.rs** | Ollama 統合例 | Async | 未読 |
| **05_batch_processing.rs** | 複数文書バッチ処理 | Advanced | 未読 |

**API 複雑度ピラミッド**（README.md 行 598-603）
```
Simple (One-line)
    ↓
Easy (Stateful)
    ↓
Builder (Configurable)
    ↓
Advanced (Full Control)
```

**出典**
- ファイル: /examples/01-05/*.rs
- README: 行 598-603

---

### 2.2 高度な例

| ファイル | 主旨 |
|---------|------|
| **MULTI_DOCUMENT_PIPELINE.md** | クロスドキュメント RRF クエリ（詳細分析は 1.7 参照） |
| **multi_document_pipeline.rs** | 実装例 |
| **llm_hierarchical_summarization_demo.rs** | 階層的サマリー |
| **graphrag_multi_doc_server.rs** | サーバーモード |
| **zero_cost_approaches_demo.rs** | コスト最適化パイプライン |

---

## 3. graphrag-rs の公式設計思想（要約）

graphrag-rs 設計の中核原則（著者の明示的主張）：

### 3.1 設定駆動パイプライン
**README.md 行 33-88 / HOW_IT_WORKS.md 行 33-88**

単一コード、複数実行環境：
- TOML で 7 段階各フェーズの実装選択
- 同じコードで「高速＋低精度」から「低速＋高精度」まで
- `[mode] approach = "semantic|algorithmic|hybrid"` で全体レイアウト自動選択

### 3.2 モジュール・トレイト駆動アーキテクチャ
**README.md 行 511-549**

12+ コア抽象化で最大柔軟性：
- ChunkingStrategy trait
- AsyncEmbedder / AsyncLanguageModel
- EntityExtractor / RelationshipExtractor
- VectorStore / GraphDatabase
- RetrievalStrategy

実装は着脱可能（特性フラグで制御）。

### 3.3 複数デプロイアーキテクチャ
**README.md 行 57-114**

同じ `graphrag-core` で 3 つの世界：
- **Server-Only**: 本番マルチテナント、GPU オフロード可
- **WASM-Only**: プライバシー優先、オフライン可
- **Hybrid**: 部分 local、部分 server（計画中）

### 3.4 最新研究統合
**README.md 行 119-131 / PIPELINE_ARCHITECTURE.md 行 155-168**

5 つの著名論文を単一フレームワークに：
1. LightRAG (EMNLP 2025): 6000x トークン削減
2. HippoRAG (NeurIPS 2024): グラフ + PPR
3. Leiden (Nature 2019): +15% モジュール性
4. Cross-Encoder (EMNLP 2019): +20% 精度
5. Semantic Chunking (LangChain 2024): 境界尊重

### 3.5 階層的・増分設計
**MULTI_DOCUMENT_PIPELINE.md 行 37-72 / report.md 行 14-16**

新ドキュメント追加時に全再構築不要：
- 増分マージ（10x 高速化）
- エンティティ重複解決
- RRF でクロスドキュメント融合

---

## 4. 公式が示す典型的利用パイプライン

### 4.1 基本フロー（セマンティック重視）

```
┌─────────────────────────────────────────────────────────────┐
│ INPUT: TOML 設定 + 文書                                      │
│ approach = "semantic"                                       │
│ use_gleaning = true, max_rounds = 4                         │
│ embeddings.backend = "ollama"                               │
└─────────────────┬───────────────────────────────────────────┘
                  │
        ┌─────────▼──────────┐
        │  build_graph()     │
        │  (Indexing)        │
        └─────────┬──────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│ Chunk  │  │ Extract  │  │Construct │
│(Phase 1)  │Entities  │  │ Graph    │
│         │  │w/Gleaning  (Phase 4)
│         │  │(Phase 2-3)  │
└────────┘  └──────────┘  └──────────┘
                  │
                  ▼
        ┌─────────────────┐
        │ Knowledge Graph │
        │ (with PageRank) │
        └────────┬────────┘
                 │
    ┌────────────▼───────────────┐
    │  ask("Question")           │
    │  (Query)                   │
    └────────────┬───────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
    ▼            ▼            ▼
┌───────┐  ┌──────────┐  ┌────────────┐
│Embed  │  │Retrieve  │  │   Generate │
│Query  │  │(Vector + │  │   Answer   │
│(Phase 5)  │PageRank) │  │   (Phase 7)
│       │  │(Phase 6) │  │
└───────┘  └──────────┘  └────────────┘
                │
                ▼
        ┌──────────────────┐
        │ Answer + Sources │
        └──────────────────┘
```

出典：HOW_IT_WORKS.md 行 345-365 / graphrag-core/README.md 行 321-381

### 4.2 低コスト パイプライン（Algorithmic）

```
INPUT: approach = "algorithmic"
       use_gleaning = false
       embeddings.backend = "hash"
       retrieval.strategy = "bm25"

TEXT → HASH EMBED → KEYWORD PATTERN → CO-OCCUR GRAPH → BM25 SEARCH → CONCAT ANSWER
   <10ms      <5ms        <50ms         <100ms        <50ms       <10ms
   
Total: ~200ms for query (vs. 1-5s for semantic)
```

出典：HOW_IT_WORKS.md 行 150-182

### 4.3 ハイブリッド パイプライン（バランス型）

```
LLM GLEANING (2 rounds) → entities1
+ PATTERN MATCHING      → entities2
→ MERGE (cross-validate)
→ DUAL EMBEDDINGS (neural + hash)
→ RRF (vector + BM25 + PageRank)
→ LLM SYNTHESIS

Result: 85-95% accuracy, 200-1000 docs/sec, 3-4GB RAM
```

出典：HOW_IT_WORKS.md 行 186-225

---

## 5. 公式が言及している「未完成」「将来拡張」項目

README.md より引用（行 1000-1085）：

### Phase 1: Core Implementation ✅ 完了
- Native Backend（本番）
- Server API（本番）
- CLI（本番）
- テスト 214+（本番）

### Phase 2: WASM & Web UI 🚧 進行中（60% 完了）
- [x] graphrag-wasm crate
- [x] ONNX Runtime Web GPU 埋め込み
- [x] WebLLM（GPU LLM）
- [x] IndexedDB / Cache API
- [ ] Burn + wgpu（GPU 加速、アーキテクチャ 70% 完了）
- [ ] Integration Tests
- [ ] Chat Components
- [ ] Search Components
- [ ] Graph Visualization
- [ ] Progress Indicators

### Phase 3: Advanced Features 📅 計画中
- [ ] Redis 分散キャッシング
- [ ] OpenTelemetry モニタリング
- [ ] Query Intelligence with ML
- [ ] Multi-model embeddings
- [x] **Temporal reasoning**（タイムライン抽出）✅ 完了
- [x] **Causal reasoning**（因果チェーン）✅ 完了
- [ ] Quality metrics
- [ ] PDF processing
- [ ] Bulk import (CSV, JSON, RDF)
- [ ] Multi-format export (GraphML, Cypher)

### Phase 4: Enterprise Features 🏢 将来
- [ ] HA / Failover
- [ ] Horizontal scaling
- [ ] Multi-region deployment
- [ ] Enterprise security
- [ ] Multi-language SDKs (Python, TS, Go)
- [ ] GraphQL API
- [ ] Plugin system
- [ ] Webhooks

出典：README.md 行 1000-1085

---

## 6. 未確認項目の総まとめ

### 6.1 docs で存在が確認できても詳細不明な項目

| 項目 | 確認範囲 | 未確認理由 |
|------|---------|----------|
| **graphrag-cli** | README に言及 | 専用ドキュメントが見当たらない |
| **graphrag_py** | TODO.md に完了表記 | src コード未読（バインディング詳細） |
| **WebLLM integration** | graphrag-wasm 言及 | WEBLLM_INTEGRATION.md は未読 |
| **Burn wasm status** | report.md 言及 | BURN_WASM_STATUS.md 未読 |
| **Hierarchical clustering** | ADVANCED_FEATURES 冒頭 | Phase 2/3 実装の詳細未確認 |
| **DW-GRPO（Weight Optimization）** | README / report 言及 | 実装詳細ドキュメント未読 |

### 6.2 「技術的には存在するが公式で文書化されていない」領域

1. **Symbolic Anchoring の実装詳細**
   - README.md 行 147-149 で名言
   - 実装ファイル / テスト未確認

2. **Dynamic Edge Weighting メカニズム**
   - README.md 行 148-149 で説明
   - ADVANCED_FEATURES.md には記載なし

3. **Causal Chain Analysis の詳細アルゴリズム**
   - 言及のみ（行 193-196）
   - 実装ファイル特定不可

4. **RoGRAG（Logic Form Reasoning）**
   - graphrag-core/README.md 行 309-313 で言及
   - 実装状態・使用方法の詳細不明

### 6.3 実装状態が曖昧な項目

| 項目 | 記載状況 | 状態判定 |
|------|---------|---------|
| **Candle ML inference** | README 行 580 | 📅 計画中（CPU-only） |
| **Burn + wgpu** | README 行 1038 | 🚧 70% 完了 |
| **Hybrid Deployment** | README 行 108-113 | 🎯 計画中（Phase 3） |
| **OpenTelemetry** | README 行 1053 | 📅 計画中 |
| **Multi-model embeddings** | README 行 1054 | 📅 計画中 |
| **PDF Document Processing** | README 行 986 | 計画中と FAQ で言及 |

---

## 7. README 主張 vs. 私の推測の明確な分離

### 7.1 README が明示的に主張していること

**引用可能事実**:
- "50,000+ Lines of Production-Quality Rust Implementation" (README.md 行 761)
- "5 cutting-edge research papers (2019-2025)" (行 119)
- "6000x token reduction" via LightRAG (行 131)
- "214 passing tests, zero warnings" (行 995)
- "Phase 1 COMPLETE, Phase 2 IN PROGRESS (60%), Phase 3 PLANNED" (行 1000-1085)
- "Supports 8 embedding backends" (graphrag-core/README.md 行 9)
- "TRUE LLM-based gleaning extraction" (ENTITY_EXTRACTION.md 行 7)

### 7.2 著者が言及していない私の推測

**注意**: 以下は本調査に含めない（CLAUDE.md 原則）
-「graphrag-rs はおそらく GraphRAG Python の完全な置き換えになる」→ 著者は「多言語 SDK」として将来計画（行 1081）
- 「WASM はプロダクション readiness に達している」→ 著者は「WASM: Phase 2, 60% complete」（行 1029-1040）
- 「すべてのモジュールが equal に mature」→ 実装状況が明示されている（✅ / 🚧 / 📅）

---

## 8. Changelog & TODO の確認内容（省略形）

### Changelog.md
- 最新版：Phase D（Python Bindings）完了
- 前フェーズ：Phase C（増分更新）
- バージョン履歴は 21KB

### TODO.md
- **✅ 完了**: Phase D（Python Bindings with uv + maturin）
- **🚧 進行中**: Phase 2（WASM + Web UI）
- **📅 計画中**: Phase 3-4（Advanced / Enterprise）

---

## 9. 最終: Examples で扱われている代表的なユースケース

| Example | ユースケース | API Level | 推奨シーン |
|---------|-----------|-----------|----------|
| **01_basic_usage.rs** | 単純なドキュメント分析 | Simple | プロトタイプ / デモ |
| **02_stateful_api.rs** | 複数クエリ（同一ドキュメント） | Easy | REPL / チャット |
| **03_builder_api.rs** | カスタム構成 | Builder | 調整・最適化 |
| **04_with_ollama.rs** | ローカル LLM 統合 | Advanced | オフライン環境 |
| **05_batch_processing.rs** | 複数文書処理 | Advanced | データ パイプライン |
| **MULTI_DOCUMENT_PIPELINE.md** | クロスドキュメント検索 | Advanced | ナレッジベース |
| **zero_cost_approaches_demo.rs** | コスト最適化（Lazy/E2） | Advanced | 大規模データ |
| **llm_hierarchical_summarization_demo.rs** | 階層的サマリー | Advanced | 文書要約システム |
| **graphrag_multi_doc_server.rs** | Server デプロイ | Advanced | 本番 REST API |

---

## 10. 結論: spec-grag 設計への示唆

### 10.1 graphrag-rs が明示する設計原則

1. **設定駆動 > コード駆動**: TOML で全パイプライン制御
2. **複数アプローチ併存**: semantic / algorithmic / hybrid を統一フレームワークで
3. **最新研究統合**: 単一の 5 つの論文の実装ではなく、全て統合
4. **モジュール・トレイト基盤**: コア API は trait で抽象化
5. **複数デプロイアーキテクチャ**: 同じ crate で server / wasm / hybrid

### 10.2 spec-grag が参照すべき具体的な技術

**必須（Phase 1）**:
- 7 段階パイプライン（Chunking → Entity → Relationship → Graph → Embed → Retrieval → Generation）
- 3 つのアプローチ選択メカニズム
- TOML 設定駆動設計
- 複数埋め込みプロバイダ対応

**推奨（Phase 2）**:
- LightRAG デュアルレベル検索（6000x トークン削減）
- Leiden コミュニティ検出（+15% モジュール性）
- Cross-Encoder reranking（+20% 精度）
- HippoRAG PPR（+20% 精度、グラフベース）

**高度（Phase 3）**:
- Triple Reflection（ハルシネーション削減）
- Temporal / Causal 分析
- ATOM 事実抽出
- Hierarchical Clustering

### 10.3 未確認・未完成の部分への対応

- **Python Bindings**: Phase D 完了と記載（TODO.md）
- **WASM**: Phase 2（60% complete）、Production Ready は Graphics / ONNX のみ
- **Burn GPU**: 実装 70% 完了、コードが不完全である可能性
- **Hybrid Deployment**: まだ計画中（Phase 3）

---

**報告書作成日**: 2026-04-27  
**対象範囲**: /home/kazuki/public_html/spec-grag/vendor/graphrag-rs の公式ドキュメント全体  
**引用ルール**: 行番号 + ファイル名で根拠を記載  
**分離原則**: README 主張 ↔️ 推測 を明確に分離

---

# §E. Bash：Cargo.toml workspace 構造・feature 一覧

**タスク**：3.9（Cargo features）と 3.10（バイナリ／API）の網羅取得。workspace Cargo.toml の冒頭、graphrag-core の `[features]` ブロック、optional 依存、サブクレートの Cargo.toml 概要を head/grep で抽出。

**実行**：2026-04-27、Bash、tool_use_id=`toolu_01NN1P2YydA6hzkBnnEJhdt5`。

**未確認の自己申告**：個別 feature 同士の組み合わせ可否の網羅、persistent-storage と neural-embeddings の排他理由の確認、graphrag_py の Cargo.toml 全体（name 行のみ確認）。

# Core dependencies (shared across crates)
serde = { version = "1.0", features = ["derive"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter", "fmt"] }
serde_json = "1.0"
bincode = "1.3"
thiserror = "1.0"
tokio = { version = "1.0", features = ["full"] }
async-trait = "0.1"
futures = "0.3"

# Web frameworks
# Axum (for API module and tests)
axum = { version = "0.7", features = ["macros"] }
tower = { version = "0.4", features = ["full"] }
tower-http = { version = "0.5", features = ["fs", "trace", "cors"] }

# Actix-web + Apistos for OpenAPI
actix-web = { version = "4.9", features = ["macros"] }
actix-cors = "0.7"
actix-rt = "2.10"
apistos = { version = "0.6", features = ["swagger-ui"] }
apistos-schemars = { package = "apistos-schemars", version = "0.8" }
schemars = { package = "apistos-schemars", version = "0.8" }

# WASM
wasm-bindgen = "0.2"
wasm-bindgen-futures = "0.4"
web-sys = "0.3"
js-sys = "0.3"

# UI Framework
leptos = { version = "0.8", features = ["csr"] }
leptos_meta = { version = "0.8" }
leptos_router = { version = "0.8" }

# Vector databases
qdrant-client = "1.11"
redis = { version = "0.27", features = ["tokio-comp", "connection-manager"] }

# GPU acceleration
burn = { version = "0.18", default-features = false }
burn-wgpu = { version = "0.18", default-features = false }

# Authentication & Security
jsonwebtoken = "9.0"
bcrypt = "0.15"

# Serialization formats
toml = "0.8"
serde_yaml = "0.9"

# Graph algorithms
petgraph = { version = "0.6", default-features = false, features = ["serde-1"] }
indexmap = { version = "2.0", features = ["serde"] }
sprs = "0.11"
nalgebra = "0.32"

=== graphrag-core/Cargo.toml の [features] ブロック ===
[features]
default = [
    "memory-storage",
    "basic-retrieval",
    "parallel-processing",
    "async",
    "ureq",
]

# =============================================================================
# FEATURE BUNDLES - Simplified feature selection for common use cases
# =============================================================================
# Use these bundles instead of manually selecting individual features:
#   cargo add graphrag-core --features starter    # Quick start for new users
#   cargo add graphrag-core --features full       # Production-ready setup
#   cargo add graphrag-core --features wasm       # Browser/WASM deployment
#   cargo add graphrag-core --features research   # Advanced research features

## Starter Bundle - Minimal setup for getting started quickly
## Includes: async runtime, Ollama LLM, memory storage, basic retrieval
## Hello World: `GraphRAG::quick_start("text").await`
starter = ["async", "ollama", "memory-storage", "basic-retrieval", "ureq"]

## Full Bundle - Production-ready with all common features
## Includes: starter + PageRank, LightRAG, caching, parallel processing, Leiden
## Best for: Production deployments with optimal performance
full = [
    "starter",
    "pagerank",
    "lightrag",
    "caching",
    "parallel-processing",
    "leiden",
    "vector-hnsw",
    "json5-support",
    "hierarchical-config",
    "qdrant",
]

## WASM Bundle - Browser-safe features only (no async runtime, no system calls)
## Includes: memory storage, basic retrieval, Leiden community detection
## Best for: Client-side browser deployments
wasm-bundle = ["memory-storage", "basic-retrieval", "leiden"]

## Research Bundle - Advanced features for GraphRAG research
## Includes: full + ROGRAG, cross-encoder, incremental updates
## Best for: Experiments, benchmarking, academic research
research = [
    "full",
    "rograg",
    "cross-encoder",
    "incremental",
    "monitoring",
    "benchmarking",
    "qdrant",
]

# =============================================================================
# INDIVIDUAL FEATURES - For fine-grained control (power users)
# =============================================================================

# Async support (enabled by default, disabled for WASM)
async = ["tokio", "futures", "tracing"]

# HTTP client (enabled by default, disabled for WASM)
ureq = ["dep:ureq"]

# Storage backends
memory-storage = []
persistent-storage = ["arrow", "parquet"] # Apache Parquet persistence
lancedb = [
    "dep:lancedb",
    "arrow",
    "arrow-array",
    "arrow-schema",
] # LanceDB vector storage

# Retrieval methods
basic-retrieval = []
graph-retrieval = []
hybrid-retrieval = ["basic-retrieval", "graph-retrieval"]
pagerank = ["sprs", "nalgebra", "parking_lot", "lru"]

# Processing features
parallel-processing = ["rayon", "num_cpus"]
function-calling = []

# Vector stores
vector-hnsw = ["instant-distance"]
vector-memory = []                 # Enable MemoryVectorStore integration in Registry

# Monitoring and benchmarking
monitoring = []
benchmarking = []

# Serialization formats
yaml-support = ["serde_yaml"]
toml-support = []                       # TOML is always available as core dependency
serde_json = []                         # serde_json is always available as core dependency
json5-support = ["json5", "jsonschema"] # JSON5 + schema validation

# Graph import formats
graphml-import = ["quick-xml"]  # GraphML format support
rdf-import = ["oxrdf", "oxttl"] # RDF/Turtle format support

# Caching features
caching = ["moka", "tracing"]

# Incremental updates feature
incremental = ["parking_lot", "dashmap"]

# ROGRAG (Robustly Optimized GraphRAG) feature
rograg = ["derive_more", "strum", "itertools", "tap"]

# API module (requires axum web framework)
api = ["axum", "tower", "tower-http", "async"]

# Tracing and logging
tracing = ["dep:tracing", "tracing-subscriber"]


=== graphrag-core の optional 依存（features と関連）===
ureq = { workspace = true, optional = true } # HTTP client (not needed for WASM)
text-splitter = { version = "0.18", optional = true, default-features = false } # Semantic text chunking
instant-distance = { workspace = true, optional = true }
rayon = { workspace = true, optional = true }
num_cpus = { workspace = true, optional = true }
sprs = { workspace = true, optional = true }
nalgebra = { workspace = true, optional = true }
parking_lot = { workspace = true, optional = true }
lru = { workspace = true, optional = true }
serde_yaml = { workspace = true, optional = true }
json5 = { version = "0.4", optional = true }                                 # JSON5 parsing (JSON with comments)
jsonschema = { version = "0.18", optional = true, default-features = false } # JSON Schema validation
figment = { version = "0.10", optional = true, features = [
quick-xml = { version = "0.36", optional = true } # GraphML XML parsing
oxrdf = { version = "0.2", optional = true }      # RDF data model
oxttl = { version = "0.1", optional = true }      # Turtle RDF parser
arrow = { workspace = true, optional = true, default-features = false, features = [
parquet = { version = "57", optional = true, default-features = false, features = [
tokio = { version = "1.0", features = ["full"], optional = true }
futures = { workspace = true, optional = true }
axum = { workspace = true, optional = true }
tower = { workspace = true, optional = true }
tower-http = { workspace = true, optional = true }
tracing = { workspace = true, optional = true }
tracing-subscriber = { workspace = true, optional = true }
ollama-rs = { workspace = true, optional = true }
gline-rs    = { version = "1.0.1", optional = true }
orp         = { version = "0.9.2",  optional = true }
composable  = { version = "0.9",   optional = true }
moka = { workspace = true, optional = true }
redis = { workspace = true, optional = true }
bincode = { workspace = true, optional = true }
dashmap = { workspace = true, optional = true }
getrandom = { version = "0.2", features = ["js"], optional = true }
derive_more = { workspace = true, optional = true }
strum = { workspace = true, optional = true }
itertools = { workspace = true, optional = true }
tap = { workspace = true, optional = true }
candle-core = { workspace = true, optional = true }
candle-nn = { workspace = true, optional = true }

=== サブクレートの一覧 ===
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/benches/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/config/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/docs-example/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/examples/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag-cli/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag-core/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag-server/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag-wasm/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag_py/
/home/kazuki/public_html/spec-grag/vendor/graphrag-rs/tests/

=== 各サブクレートの Cargo.toml の name + features 概要 ===
--- /home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag-cli/Cargo.toml ---
name = "graphrag-cli"
description = "Modern Terminal User Interface (TUI) for GraphRAG operations"

--- /home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag-core/Cargo.toml ---
name = "graphrag-core"
description = "Core portable library for GraphRAG - works on native and WASM"

--- /home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag-server/Cargo.toml ---
name = "graphrag-server"
description = "REST API server for GraphRAG"

--- /home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag-wasm/Cargo.toml ---
name = "graphrag-wasm"
description = "WASM bindings for GraphRAG - enables browser-side knowledge graphs"

--- /home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag/Cargo.toml ---
name = "graphrag"
description = "GraphRAG - Knowledge Graph RAG: meta-crate that bundles graphrag-core and graphrag-cli"

--- /home/kazuki/public_html/spec-grag/vendor/graphrag-rs/graphrag_py/Cargo.toml ---
name = "graphrag_py"
name = "graphrag_py"

---

