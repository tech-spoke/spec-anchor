# 03: SimplePropertyGraphStore 永続化粒度

> 状態: WebFetch ✓ / GitHub ✓（simple_labelled.py 確認）/ Spike ☐ — 判定 **usable**
> 最終更新: 2026-04-28

## 調査対象

- component: `llama_index.core.graph_stores.SimplePropertyGraphStore`（実体は `simple_labelled.py`）
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: `llama-index-core/llama_index/core/graph_stores/simple_labelled.py`
  - 実行確認: _pending spike/_

## 確認した API（GitHub source レベル）

```python
class SimplePropertyGraphStore(PropertyGraphStore):
    """Simple in-memory labelled property graph store."""

    supports_structured_queries: bool = False  # Cypher 非対応
    supports_vector_queries: bool = False      # vector query は別 store で

    def __init__(self, graph: Optional[LabelledPropertyGraph] = None): ...

    # 取得
    def get(self, properties=None, ids=None) -> List[LabelledNode]: ...
    def get_triplets(self, entity_names=None, relation_names=None,
                     properties=None, ids=None) -> List[Triplet]: ...
    def get_rel_map(self, graph_nodes, depth=2, limit=30, ignore_rels=None) -> List[Triplet]: ...

    # 投入
    def upsert_nodes(self, nodes: Sequence[LabelledNode]) -> None: ...
    def upsert_relations(self, relations: List[Relation]) -> None: ...

    # 削除（多軸 filter）
    def delete(self, entity_names=None, relation_names=None,
               properties=None, ids=None) -> None: ...

    # 永続化（JSON）
    def persist(self, ...) -> None: ...
    @classmethod
    def from_persist_path(cls, ...) -> "SimplePropertyGraphStore": ...
    @classmethod
    def from_persist_dir(cls, ...) -> "SimplePropertyGraphStore": ...
    @classmethod
    def from_dict(cls, ...) -> "SimplePropertyGraphStore": ...
    def to_dict(self) -> dict: ...

    # その他
    def get_schema(self, refresh=False) -> str: ...
    def save_networkx_graph(self, name="kg.html") -> None: ...
    def show_jupyter_graph(self) -> None: ...
```

- import: `from llama_index.core.graph_stores import SimplePropertyGraphStore`
- 型: `from llama_index.core.graph_stores.types import LabelledNode, EntityNode, Relation, Triplet, LabelledPropertyGraph, DEFAULT_PERSIST_DIR, DEFAULT_PG_PERSIST_FNAME`
- 永続化形式: **JSON**（`to_dict()` / `from_dict()` 経由、`import json` を使う）
- in-memory: `self.graph = graph or LabelledPropertyGraph()` ← デフォルトで in-memory、persist で disk 書き出し
- 全文章ベース store（章別 store 分割は LlamaIndex 側ではない）

## 実測・検証結果

- 最小コードで動いたこと: _pending spike/_
- 動かなかったこと: _pending_

## spec-grag への影響

- DESIGN §1.4 採用候補スタックの `SimplePropertyGraphStore` は **JSON 永続化で human-readable** → review / debug に最適（CLAUDE.md ルール 1 と整合: 何が起きたか分かる）
- 章別 vs 全体一括: **全体一括 in-memory + JSON persist** が標準。章別 incremental は spec-grag 側で `delete(properties={"section_id": ...})` + `upsert_nodes(...)` の組合せで実現する
- `get_rel_map(depth=2, limit=30)` はデフォルトで depth=2 traversal、ignore_rels で関係型を除外可能 → spec-grag の制約探索 / 修正対象探索 / SUPERSEDES 追跡に直接使える
- `supports_vector_queries=False` → vector index は PropertyGraphIndex 構築時に **別途 `vector_store` を渡す**（DEFAULT は SimpleVectorStore か、要 spike 確認）
- `save_networkx_graph` で graph を HTML 可視化できる → debug 用途で価値あり
- 未解決事項:
  - persist 時のファイル名 / パス命名（`DEFAULT_PG_PERSIST_FNAME` の中身）→ types.py 確認
  - `delete(properties=...)` で **node 削除時に紐付 edge も連動して削除されるか** → spike で確認必須（項目 04 / 10）
  - `to_dict()` の JSON 構造（spec-grag 側で sidecar として読みたい場合）

## 判定

**usable**（永続化 JSON / API 全部揃う、edge 連動削除の挙動だけ spike で実証）
