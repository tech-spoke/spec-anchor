# 05: HybridRetriever / PGRetriever fusion 戦略

> 状態: WebFetch ✓ / GitHub ✓ / **Spike ✓**（spike/03_retriever_and_transient.py）— 判定 **usable_with_wrapper**
> 最終更新: 2026-04-28

LlamaIndex Property Graph の retrieval API 名は **`PGRetriever`**（`HybridRetriever` ではない）。fusion 戦略は **単純結合 + テキスト dedup** のみ、RRF / Weighted は LlamaIndex 標準にはない。

## 調査対象

- component:
  - `llama_index.core.indices.property_graph.PGRetriever`（複数 sub_retrievers を統合）
  - `BasePGRetriever`（sub_retriever の基底）
  - `LLMSynonymRetriever` / `VectorContextRetriever` / `TextToCypherRetriever` / `CypherTemplateRetriever` / `CustomPGRetriever`
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source:
    - `llama-index-core/llama_index/core/indices/property_graph/retriever.py` (PGRetriever)
    - `llama-index-core/llama_index/core/indices/property_graph/sub_retrievers/base.py` (BasePGRetriever)
    - `sub_retrievers/{custom,cypher_template,llm_synonym,text_to_cypher,vector}.py`
  - 実行確認: _pending spike/_

## 確認した API（GitHub source レベル）

### PGRetriever（retriever.py）

```python
class PGRetriever(BaseRetriever):
    def __init__(
        self,
        sub_retrievers: List[BasePGRetriever],
        num_workers: int = 4,
        use_async: bool = True,
        show_progress: bool = False,
        **kwargs,
    ):
        ...

    def _retrieve(self, query_bundle):
        if self.use_async:
            return asyncio_run(self._aretrieve(query_bundle))
        for sub_retriever in self.sub_retrievers:
            results.extend(sub_retriever.retrieve(query_bundle))
        return self._deduplicate(results)

    def _deduplicate(self, nodes):
        seen = set()
        deduped = []
        for node in nodes:
            if node.text not in seen:
                deduped.append(node)
                seen.add(node.text)
        return deduped
```

**fusion 戦略**: **単純結合（extend）+ テキストベース dedup（`node.text` で set）**
- async: `_aretrieve` で `run_jobs` 並列実行
- **RRF / Weighted / CombSum / MaxScore は実装されていない**
- score 集約も無し（各 sub_retriever の score がそのまま残る、`include_text=True` で source text 付加）

### BasePGRetriever（sub_retrievers/base.py）

```python
class BasePGRetriever(BaseRetriever):
    def __init__(
        self,
        graph_store: PropertyGraphStore,
        include_text: bool = True,
        include_text_preamble: Optional[str] = DEFAULT_PREAMBLE,
        include_properties: bool = False,
        **kwargs,
    ):
        ...

    def _get_nodes_with_score(self, triplets, scores=None) -> List[NodeWithScore]:
        # triplet -> NodeWithScore 変換
        ...
```

- `triplet` を `NodeWithScore` に変換
- `TRIPLET_SOURCE_KEY` を `triplet[0].properties` から拾い、`NodeRelationship.SOURCE` で source 関連付け
- `include_properties=True` で `triplet[0]!s -> triplet[1]!s -> triplet[2]!s`、False で id のみ

### 各 retriever の import

```python
from llama_index.core.indices.property_graph import (
    LLMSynonymRetriever,
    VectorContextRetriever,
    TextToCypherRetriever,
    CypherTemplateRetriever,
    CustomPGRetriever,
)
```

- default: `LLMSynonymRetriever` + `VectorContextRetriever`
- 返り値: `List[NodeWithScore]`（`TextNode` ベース）

## 実測・検証結果（spike 03）

- ✅ `VectorContextRetriever(graph_store, vector_store, embed_model, similarity_top_k=3)` 構築 OK
- ✅ `PGRetriever(sub_retrievers=[vec_ret], use_async=False)` 構築 OK
- ✅ `pg_ret.retrieve(QueryBundle(query_str="..."))` で 3 件の `NodeWithScore` が返る（fallback path）
- ⚠️ vector_store が空のとき 3 件返るが score = 0.000（本来の vector 類似ではなく fallback で triplets を返す挙動）
- ⚠️ vector_store に手動で TextNode 投入しても 0 件返る（VECTOR_SOURCE_KEY を metadata に入れたが正しく連結されない、要追加調査）
- ✅ NodeWithScore.node は TextNode で、`text` 属性に triplet 文字列（`"oauth2_required -> CONSTRAINS -> user_authentication"`）

### vector_store への正しい投入パターン（要追加調査・実装時詰める）

spec-grag 側で:

```python
from llama_index.core.schema import TextNode
from llama_index.core.graph_stores.types import VECTOR_SOURCE_KEY  # "vector_source_id"

text_nodes = [
    TextNode(
        text=f"{n.label}: {n.name} ({n.properties['heading_path']})",
        embedding=n.embedding,
        metadata={
            VECTOR_SOURCE_KEY: n.id,  # ★ graph_store の entity id と連結
            **n.properties,           # entity properties をコピー
        },
    )
    for n in entities
]
vector_store.add(text_nodes)
```

ただし spike 03 ではこの投入で 0 件が返るため、**vector_store と graph_store の entity 連結ロジックの詳細は Phase 1 / 実装時に追加調査が必要**。MVP では graph_store 直接アクセス（`get_rel_map`）+ keyword retrieval から始める選択肢もある。

## spec-grag への影響

- DESIGN §1.9 経路 3（/spec-inject）の 2 系統 retrieval（制約探索 / 修正対象探索）に応用可能
  - 制約探索用: `LLMSynonymRetriever`（synonym 展開で Purpose / Concept 関連を広く拾う）
  - 修正対象探索用: `VectorContextRetriever`（embedding 類似で課題プロンプト関連を拾う）
- **rank fusion は LlamaIndex 標準にない** → spec-grag Orchestrator 側で実装する必要あり
  - spec-grag が rank fusion / 4 軸付与 / cross-encoder rerank（DESIGN §4.4）を一気に処理する設計が綺麗
  - `BasePGRetriever._get_nodes_with_score` の score をそのまま 4 軸評価の入力に使える
- 4 軸評価（transient annotation）は retrieval result の `NodeWithScore` に対して spec-grag Orchestrator 側で付与（項目 08 と連携、`NodeWithScore.metadata` か wrapper クラスで保持）
- 未解決事項:
  - `LLMSynonymRetriever` の synonym 展開 prompt（日本語適合性）
  - cross-encoder rerank（DESIGN §4.4）との接続点
  - `include_properties=True` で triplet 全体を text として渡したときの 4 軸評価への影響

## 判定

**usable_with_wrapper** — API レベル動作 ✓、ただし以下を spec-grag が実装する責務:

1. fusion / rerank / 4 軸付与（LlamaIndex 標準にない）
2. vector_store への TextNode 投入（VECTOR_SOURCE_KEY 連結含む、Phase 1 で詳細詰め）
3. NodeWithScore から graph_store の EntityNode への参照解決（必要に応じて）

MVP では graph_store ベース retrieval（`get` / `get_rel_map`）+ keyword 検索から始め、vector retrieval は段階的に投入する選択肢も視野に入れる。
