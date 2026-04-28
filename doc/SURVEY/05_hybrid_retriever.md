# 05: HybridRetriever / PGRetriever fusion 戦略

> 状態: WebFetch ✓ / GitHub ✓（retriever.py + sub_retrievers/base.py 確認）/ Spike ☐
> 判定 **usable_with_wrapper**（fusion は spec-grag 側で実装する前提なら usable）
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

## 実測・検証結果

- 最小コードで動いたこと: _pending spike/_
- 動かなかったこと: _pending_

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

**usable_with_wrapper**（fusion / rerank / 4 軸付与は spec-grag Orchestrator で実装、各 sub_retriever は usable）
