# 業界標準 GRAG / RAG 方式整理

作成日: 2026-05-13

本書は Phase 2 の外部基準である。既存設計書・memory は使わず、一次資料（論文、公式 docs、主要 OSS 公式 repo）から整理した。

## 1. 参照一次資料

- Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", arXiv:2005.11401. https://arxiv.org/abs/2005.11401
- Microsoft GraphRAG docs: Indexing / Query Engine / Local Search / Global Search. https://microsoft.github.io/graphrag/
- Edge et al., "From Local to Global: A Graph RAG Approach to Query-Focused Summarization", arXiv:2404.16130. https://arxiv.org/abs/2404.16130
- Microsoft Research publication page for GraphRAG. https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/
- Guo et al., "LightRAG: Simple and Fast Retrieval-Augmented Generation", arXiv:2410.05779. https://arxiv.org/abs/2410.05779
- HKUDS LightRAG official repository. https://github.com/HKUDS/LightRAG
- LlamaIndex PropertyGraphIndex official docs. https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
- Qdrant Hybrid Queries official docs. https://qdrant.tech/documentation/search/hybrid-queries/
- BGE / FlagEmbedding BGE-M3 official docs. https://bge-model.com/tutorial/1_Embedding/1.2.1.html
- BGE-M3 paper, arXiv:2402.03216. https://arxiv.org/abs/2402.03216

## 2. Baseline RAG

標準的な RAG は、LLM の parametric memory だけに依存せず、外部の non-parametric memory を検索して generation に渡す方式である。Lewis et al. は dense vector index に格納した Wikipedia passages を neural retriever で取得し、取得 passage を条件に生成する方式として RAG を定義している。

方式上の要点:

- indexing: 文書を passage / chunk に分割し、検索可能な index に格納する。
- retrieval: query 時に外部 index を検索する。
- augmentation: retrieved passages/chunks を LLM context に入れる。
- generation: LLM は retrieved context に基づいて回答する。
- provenance/update: 外部 memory を更新でき、回答根拠の出所を扱えることが RAG の重要な効用である。

監査基準としては、RAG を名乗る経路では「検索 index を作る」だけでなく「query / inject 時に検索結果を使う」「検索結果が source text へ辿れる」ことが必要である。

## 3. Hybrid RAG / Dense + Sparse Retrieval

Qdrant の Hybrid Queries は、同一 point に複数 named vectors を持たせ、dense と sparse のような複数表現の検索結果を fusion する方式を標準機能として扱う。公式 docs は、text search では dense vector の semantic understanding と sparse vector の precise word matching を組み合わせるのが有用で、fusion 方式として RRF / DBSF を示している。

BGE-M3 は dense retrieval、sparse retrieval、multi-vector retrieval を同一モデルで扱える。公式 docs と論文は multilingual、multi-functionality、multi-granularity を特徴とし、最大 8192 tokens の入力粒度まで扱えるとしている。

方式上の要点:

- ingestion: raw chunk または retrieval 用 representation を embed し、dense / sparse vectors を保存する。
- query: query も同じ embedding provider で dense / sparse 化する。
- fusion: RRF などで複数 channel を統合する。
- payload: source id、chunk id、source text または source text へ辿れる provenance を保持する。
- health: vector DB / embedding provider が失敗した場合は retrieval capability が degraded / unavailable であることを上位へ伝える。

## 4. Microsoft GraphRAG

GraphRAG は、単純な semantic vector search が不得手な「dataset 全体を俯瞰する global questions」を扱うための graph-based RAG である。論文と公式 docs は、source documents から LLM で entity knowledge graph を作り、entity community の summaries/reports を事前生成し、query 時に local / global search を行う方式を示している。

indexing pipeline の標準要素:

- raw text から entities、relationships、claims を抽出する。
- entity graph に community detection を適用する。
- community summaries / reports を複数粒度で生成する。
- text を vector space に embed する。
- 出力は Parquet tables と vector store に保存される。

query pipeline の主要型:

- Local Search: query から関連 entity を見つけ、knowledge graph の構造データ、関係、community reports、raw document text chunks を組み合わせて context を作る。
- Global Search: community reports を map-reduce で処理し、dataset 全体の themes / global sensemaking question に答える。
- DRIFT Search: local search に community information を取り込み、query の出発点を広げる。
- Basic Search: 比較用の通常 vector RAG。

監査基準としては、GraphRAG を名乗るなら永続的・検索可能な graph index、entity / relation / community などの graph-side artifact、query 時の graph traversal / graph context building が必要である。ただし、Purpose が軽量化のため property graph / entity relation graph / hierarchical cluster を標準外と明示するなら、「GraphRAG ではなく lightweight related-section retrieval」として正当化され得る。

## 5. LightRAG

LightRAG は graph structures を text indexing / retrieval に統合し、low-level / high-level knowledge discovery の dual-level retrieval を行う方式である。論文は、graph structures と vector representations を組み合わせ、related entities and relationships を効率的に検索し、incremental update algorithm で新データを取り込むと説明している。公式 repo はこの実装の主要 OSS 参照で、2026-05-13 時点でも継続更新されている。

方式上の要点:

- graph-based indexing と vector retrieval を併用する。
- low-level retrieval は entity / local relation など細粒度情報に向く。
- high-level retrieval は relation / global context など広域情報に向く。
- incremental update は方式の中心機能であり、更新後の index 整合性が重要である。

監査基準としては、LightRAG 系を名乗る場合、graph context と vector context の両方を query 時に使い、更新時に graph/vector 両方の整合性を保つ必要がある。

## 6. LlamaIndex PropertyGraphIndex 系

LlamaIndex の PropertyGraphIndex は、chunk ごとに `kg_extractors` を適用し、entities / relations を node metadata として付与する。retriever は `include_text=True` により matching paths と source chunk text を返せる。公式 docs は graph store と optional vector store を組み合わせる構成、`LLMSynonymRetriever`、`VectorContextRetriever`、`TextToCypherRetriever` などの sub-retrievers を示している。

方式上の要点:

- graph construction は chunk 単位で path / entity / relation を抽出する。
- graph store は永続 store として扱われる。
- vector retrieval は graph node を取って connected paths を辿る。
- query result は source chunk text を含められる。

監査基準としては、property graph 方式を採るなら graph schema / graph store / graph retriever が必要であり、source chunk text を include できることが重要である。

## 7. 監査用判定軸

Phase 4 では、次を外部基準として扱う。

- RAG の最低条件: 外部 retrieval index が query / inject 時に使われ、retrieved unit が source text または source provenance に接続される。
- Hybrid retrieval の最低条件: dense / sparse など複数 channel の index と query が同じ provider / schema / collection 設定で整合し、fusion 結果を返す。
- GRAG の最低条件: graph 構造が永続化され、query 時に graph traversal / graph context building を行う。これを持たない場合は GRAG ではなく lightweight related-section retrieval と呼ぶべきである。
- Incremental update の最低条件: source reorder / deletion / config change / provider failure により index が stale になった場合、freshness / health がそれを表明する。
- Evidence の最低条件: LLM 生成 summary / search key / related edge は retrieval aid であり、source evidence の代替にはならない。Agent が source 本文へ辿れる必要がある。
- Fallback の最低条件: fake / in-memory / mechanical fallback は production retrieval success と区別し、status / diagnostics / freshness へ反映する。

