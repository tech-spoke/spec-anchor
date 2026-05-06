# 08: transient annotation の実装パターン

> 状態: **Spike ✓**（spike/03_retriever_and_transient.py）— 判定 **usable**
> 最終更新: 2026-04-28

DESIGN.ja.md §1.6 / TODO.md「恒久プロパティ vs transient annotation の境界」に従い、**4 軸評価（transient annotation）を graph store に書かず、retrieval result / Orchestrator 側に持つ実装パターン**を実証した。

## 調査対象

- component: `NodeWithScore` の `node.metadata` 経由で 4 軸を後付け
- version / commit: llama-index-core **0.14.21**
- source:
  - 実行確認: [`spike/03_retriever_and_transient.py`](../../spike/03_retriever_and_transient.py) STEP 6-8

## 確認した実装パターン（spike 03 で実証）

```python
from llama_index.core.schema import NodeWithScore

def annotate_4axis(
    node_with_score: NodeWithScore,
    constraint_relevance: str,   # none | low | medium | high
    target_relevance: str,       # none | low | medium | high
    conflict: bool,              # LLM 単独では false まで（§1.5）
    review_required: bool,
) -> NodeWithScore:
    """spec-grag Orchestrator が retrieval result に 4 軸を後付け。
    NodeWithScore.node.metadata に追記。graph_store には書き込まない。"""
    if node_with_score.node.metadata is None:
        node_with_score.node.metadata = {}
    node_with_score.node.metadata["constraint_relevance"] = constraint_relevance
    node_with_score.node.metadata["target_relevance"] = target_relevance
    node_with_score.node.metadata["conflict"] = conflict
    node_with_score.node.metadata["review_required"] = review_required
    return node_with_score
```

## 実測・検証結果（spike 03）

### STEP 6: 4 軸 transient annotation を 3 件の NodeWithScore に後付け

```
[0] 4-axis: {'constraint_relevance': 'high', 'target_relevance': 'low', 'conflict': False, 'review_required': False}
[1] 4-axis: {'constraint_relevance': 'medium', 'target_relevance': 'high', 'conflict': False, 'review_required': True}
[2] 4-axis: {'constraint_relevance': 'none', 'target_relevance': 'none', 'conflict': False, 'review_required': False}
```

### STEP 7: graph_store に 4 軸が混入していないことを確認

```
graph_store dump keys: ['nodes', 'relations', 'triplets']
[OK] graph_store の properties に 4 軸が含まれていない（transient 隔離成功）
```

→ `graph_store.graph.model_dump()` の全 nodes / relations の properties を走査し、4 軸キーが含まれていないことを確認。

### STEP 8: persist → reload 後も 4 軸が出てこない

```
[OK] reload 後の properties に 4 軸が含まれていない（永続化分離成功）
```

→ NodeWithScore.metadata への後付けは graph_store / persist パスから完全に分離されている。

## spec-grag への影響

- DESIGN §1.6 の境界（恒久プロパティ vs transient annotation）が **API レベルで自然に成立**
- spec-grag Orchestrator が retrieval result（List[NodeWithScore]）に対して 4 軸を後付けする設計が動作
- enforcement: graph_store / persist の write path は EntityNode / Relation / Triplet のみを扱い、NodeWithScore.metadata は graph_store とは独立
- 設計上の含意:
  - **NodeWithScore.metadata は課題ごとに上書きされる作業空間**（4 軸 / ranking_score / reason_for_current_task 等を持てる）
  - graph_store の `EntityNode.properties` は恒久プロパティのみ（document_id / section_id / source_hash / approval_status 等）
  - 同じ entity が複数の課題で異なる 4 軸を取れる（EXTERNAL_DESIGN §5.4 の要求と整合）
- 未解決事項:
  - InjectionContext / RealignResult の serialization（4 軸を含めて出力する spec-grag 側 schema）→ DESIGN §4.7 で詰める

## 判定

**usable** — Orchestrator 側で 4 軸を NodeWithScore.metadata に後付けする実装パターンが動作、graph_store への書き戻しが起きないことを spike で実証
