"""
spike 03: VectorContextRetriever / PGRetriever + 4 軸 transient annotation

実証する Phase 0 項目（doc/TODO.md Phase 0.5 spike 計画 #03）:
- 05: VectorContextRetriever / PGRetriever の検索動作
- 07-retrieval: NodeWithScore.node.metadata / properties が retrieval result に乗るか
- 08: 4 軸 transient annotation（constraint_relevance / target_relevance /
       conflict / review_required）を Orchestrator 側で後付けし、
       graph_store に書き込まないことを確認

シナリオ:
  STEP 1: Settings.embed_model 注入
  STEP 2: 各 entity に embedding をセット（spec-grag CLI 側の責務）
  STEP 3: SimplePropertyGraphStore に upsert
  STEP 4: VectorContextRetriever 単独で検索
  STEP 5: PGRetriever でラップして検索（複数 sub_retrievers の挙動確認）
  STEP 6: NodeWithScore に 4 軸 transient annotation を後付け
  STEP 7: graph_store.to_dict() に 4 軸が混入していないことを確認

usage:
  spike/.venv/bin/python spike/03_retriever_and_transient.py
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from llama_index.core import PropertyGraphIndex, Settings
from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import (
    EntityNode,
    Relation,
    VECTOR_SOURCE_KEY,  # = "vector_source_id"、TextNode.metadata に必須
)
from llama_index.core.indices.property_graph import (
    ImplicitPathExtractor,
    PGRetriever,
    VectorContextRetriever,
)
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.vector_stores.simple import SimpleVectorStore
from llama_index.embeddings.ollama import OllamaEmbedding


PERSIST_DIR = "./spike_storage/03"


def banner(msg: str) -> None:
    print()
    print("=" * 64)
    print(msg)
    print("=" * 64)


# =====================================================================
banner("spike 03: VectorContextRetriever + PGRetriever + transient annotation")

if os.path.exists(PERSIST_DIR):
    shutil.rmtree(PERSIST_DIR)
os.makedirs(PERSIST_DIR, exist_ok=True)


# ---------------------------------------------------------------------
banner("STEP 1: Settings.embed_model = OllamaEmbedding")
emb = OllamaEmbedding(
    model_name="nomic-embed-text",
    base_url="http://localhost:11434",
)
Settings.embed_model = emb
print(f"  embed dim = {len(emb.get_text_embedding('hello'))}")


# ---------------------------------------------------------------------
banner("STEP 2: 各 entity に embedding を計算してセット（spec-grag CLI の責務）")
def make_entity(name: str, label: str, descriptive_text: str, props: dict) -> EntityNode:
    """
    spec-grag が外部抽出後に entity を構築する想定。
    descriptive_text を embedding 計算に使い、entity.embedding にセットする。
    """
    return EntityNode(
        name=name,
        label=label,
        properties=props,
        embedding=emb.get_text_embedding(descriptive_text),
    )


nodes = [
    make_entity(
        "user_authentication",
        "Concept",
        "ユーザー認証の概念。ログインや本人確認に関わる仕組み。",
        {
            "section_id": "section_a",
            "heading_path": "1 / 認証",
            "source_hash": "hash_a_001",
            "approval_status": "approved",
        },
    ),
    make_entity(
        "oauth2_required",
        "Constraint",
        "OAuth 2.0 を必須とする制約。外部 ID プロバイダ連携のため。",
        {
            "section_id": "section_a",
            "heading_path": "1 / 認証",
            "source_hash": "hash_a_002",
            "approval_status": "approved",
        },
    ),
    make_entity(
        "user_session",
        "Concept",
        "ユーザーセッション管理。ログイン後の状態保持と有効期限。",
        {
            "section_id": "section_b",
            "heading_path": "2 / セッション",
            "source_hash": "hash_b_001",
            "approval_status": "approved",
        },
    ),
    make_entity(
        "session_timeout_30min",
        "Constraint",
        "セッションは 30 分でタイムアウトする制約。",
        {
            "section_id": "section_b",
            "heading_path": "2 / セッション",
            "source_hash": "hash_b_002",
            "approval_status": "approved",
        },
    ),
    make_entity(
        "payment_processing",
        "Concept",
        "決済処理の概念。クレジットカード等の支払い処理。",
        {
            "section_id": "section_c",
            "heading_path": "3 / 決済",
            "source_hash": "hash_c_001",
            "approval_status": "approved",
        },
    ),
]
print(f"  built {len(nodes)} entities, each with 768-dim embedding")
print(f"  sample embedding head: {nodes[0].embedding[:3]}")


# ---------------------------------------------------------------------
banner("STEP 3: SimplePropertyGraphStore に upsert + PropertyGraphIndex 構築")
graph_store = SimplePropertyGraphStore()
vector_store = SimpleVectorStore()

graph_store.upsert_nodes(nodes)
graph_store.upsert_relations(
    [
        Relation(
            label="CONSTRAINS",
            source_id="oauth2_required",
            target_id="user_authentication",
            properties={"section_id": "section_a"},
        ),
        Relation(
            label="DEPENDS_ON",
            source_id="user_session",
            target_id="user_authentication",
            properties={"section_id": "section_b"},
        ),
        Relation(
            label="CONSTRAINS",
            source_id="session_timeout_30min",
            target_id="user_session",
            properties={"section_id": "section_b"},
        ),
    ]
)

index = PropertyGraphIndex.from_existing(
    property_graph_store=graph_store,
    vector_store=vector_store,
    embed_kg_nodes=True,  # ★ 自動投入を期待（既に embedding 済の entity を vector_store にも入れる）
    kg_extractors=[ImplicitPathExtractor()],
)
print(f"  graph_store: nodes = {len(graph_store.get())}")
# vector_store の中身を peek
try:
    vs_data = vector_store.to_dict()
    print(f"  vector_store: keys = {list(vs_data.keys())}")
    if "embedding_dict" in vs_data:
        print(f"    embedding_dict size = {len(vs_data['embedding_dict'])}")
    if "metadata_dict" in vs_data:
        print(f"    metadata_dict size = {len(vs_data['metadata_dict'])}")
except Exception as e:
    print(f"  vector_store inspection failed: {e}")


# ---------------------------------------------------------------------
banner("STEP 4: VectorContextRetriever 単独で検索（項目 05 / 07-retrieval）")
vec_ret = VectorContextRetriever(
    graph_store=graph_store,
    vector_store=vector_store,  # ★ vector_store を明示的に渡す
    embed_model=emb,
    similarity_top_k=3,
    include_text=True,
)
print(f"  VectorContextRetriever instance: {type(vec_ret).__name__}")

query = "ユーザー認証に関する制約は？"
print(f"  query: {query!r}")
try:
    results = vec_ret.retrieve(QueryBundle(query_str=query))
    print(f"  [OK] retrieved {len(results)} NodeWithScore")
    for i, r in enumerate(results):
        print(f"    [{i}] type={type(r.node).__name__} score={r.score:.3f}")
        print(f"        text head: {r.node.get_content()[:80]!r}")
        # metadata / properties が retrieval result に乗っているか
        print(f"        node.metadata = {dict(r.node.metadata) if r.node.metadata else '{}'}")
except Exception as e:
    print(f"  [FAIL] VectorContextRetriever: {type(e).__name__}: {e}")
    raise


# ---------------------------------------------------------------------
banner("STEP 5: PGRetriever で複数 sub_retrievers をラップ（項目 05）")
pg_ret = PGRetriever(sub_retrievers=[vec_ret], use_async=False)
print(f"  PGRetriever instance: {type(pg_ret).__name__}")

try:
    pg_results = pg_ret.retrieve(QueryBundle(query_str=query))
    print(f"  [OK] PGRetriever returned {len(pg_results)} NodeWithScore")
    for i, r in enumerate(pg_results):
        print(f"    [{i}] score={r.score:.3f} text head: {r.node.get_content()[:60]!r}")
except Exception as e:
    print(f"  [FAIL] PGRetriever: {type(e).__name__}: {e}")
    raise


# ---------------------------------------------------------------------
banner("STEP 6: 4 軸 transient annotation を NodeWithScore に後付け（項目 08）")

def annotate_4axis(
    node_with_score: NodeWithScore,
    constraint_relevance: str,
    target_relevance: str,
    conflict: bool,
    review_required: bool,
) -> NodeWithScore:
    """
    spec-grag Orchestrator が retrieval result に 4 軸を後付けする想定。
    NodeWithScore.node.metadata に追記。graph_store に書き込まない。
    """
    if node_with_score.node.metadata is None:
        node_with_score.node.metadata = {}
    node_with_score.node.metadata["constraint_relevance"] = constraint_relevance
    node_with_score.node.metadata["target_relevance"] = target_relevance
    node_with_score.node.metadata["conflict"] = conflict
    node_with_score.node.metadata["review_required"] = review_required
    return node_with_score


# 仮の 4 軸評価をハードコード（実際は LLM Classification + Validator で付与）
annotated = []
for i, r in enumerate(pg_results):
    if i == 0:
        ann = annotate_4axis(r, "high", "low", False, False)
    elif i == 1:
        ann = annotate_4axis(r, "medium", "high", False, True)
    else:
        ann = annotate_4axis(r, "none", "none", False, False)
    annotated.append(ann)

print(f"  annotated {len(annotated)} NodeWithScore with 4-axis transient annotation")
for i, r in enumerate(annotated):
    print(f"    [{i}] score={r.score:.3f}")
    print(f"        4-axis: {{'constraint_relevance': {r.node.metadata.get('constraint_relevance')!r}, "
          f"'target_relevance': {r.node.metadata.get('target_relevance')!r}, "
          f"'conflict': {r.node.metadata.get('conflict')}, "
          f"'review_required': {r.node.metadata.get('review_required')}}}")


# ---------------------------------------------------------------------
banner("STEP 7: graph_store に 4 軸が書き込まれていないことを確認（重要）")
data = graph_store.graph.model_dump()
print(f"  graph_store dump keys: {list(data.keys())}")
contamination = []
for nid, ndict in data.get("nodes", {}).items():
    props = ndict.get("properties") or {}
    for axis in ["constraint_relevance", "target_relevance", "conflict", "review_required"]:
        if axis in props:
            contamination.append((nid, axis, props[axis]))
for rkey, rdict in data.get("relations", {}).items():
    props = rdict.get("properties") or {}
    for axis in ["constraint_relevance", "target_relevance", "conflict", "review_required"]:
        if axis in props:
            contamination.append((rkey, axis, props[axis]))

if not contamination:
    print(f"  [OK] graph_store の properties に 4 軸が含まれていない（transient 隔離成功）")
else:
    print(f"  [FAIL] graph_store に 4 軸が漏れている:")
    for c in contamination:
        print(f"    {c}")


# ---------------------------------------------------------------------
banner("STEP 8: graph_store を persist して reload しても 4 軸が出てこないことを確認")
graph_store.persist(persist_path=os.path.join(PERSIST_DIR, "property_graph_store.json"))
reloaded = SimplePropertyGraphStore.from_persist_dir(PERSIST_DIR)
reloaded_props = [
    n.properties for n in reloaded.get()
]
contamination_after = []
for p in reloaded_props:
    for axis in ["constraint_relevance", "target_relevance", "conflict", "review_required"]:
        if axis in p:
            contamination_after.append((p, axis))
if not contamination_after:
    print(f"  [OK] reload 後の properties に 4 軸が含まれていない（永続化分離成功）")
else:
    print(f"  [FAIL] reload で 4 軸が出てきた: {contamination_after}")


# ---------------------------------------------------------------------
banner("STEP 9: vector_store に TextNode（embedding + metadata）を手動投入")
# spec-grag CLI が graph_store に entity を upsert する際、対応する TextNode を
# vector_store.add で投入する想定。TextNode.metadata に entity の properties を
# コピーすることで retrieval 結果に properties が乗るようにする。
from llama_index.core.schema import TextNode

text_nodes_for_vector = []
for n in nodes:
    text_for_query = f"{n.label}: {n.name}"
    if n.properties.get("heading_path"):
        text_for_query += f" ({n.properties['heading_path']})"
    text_nodes_for_vector.append(
        TextNode(
            text=text_for_query,
            embedding=n.embedding,  # spec-grag が事前計算した embedding を再利用
            metadata={
                VECTOR_SOURCE_KEY: n.id,  # ★ VectorContextRetriever が graph_store と紐付ける必須キー
                "kg_node_label": n.label,
                **n.properties,  # entity properties を metadata にコピー
            },
        )
    )

# 新 vector_store に投入してみる（既存は空なので別 vector_store でも可）
vector_store_v2 = SimpleVectorStore()
vector_store_v2.add(text_nodes_for_vector)
print(f"  vector_store_v2 に {len(text_nodes_for_vector)} 件の TextNode を投入")
vs2_data = vector_store_v2.to_dict()
print(f"  embedding_dict size = {len(vs2_data.get('embedding_dict', {}))}")
print(f"  metadata_dict size = {len(vs2_data.get('metadata_dict', {}))}")


# ---------------------------------------------------------------------
banner("STEP 10: vector_store_v2 を渡した VectorContextRetriever で再検索")
vec_ret_v2 = VectorContextRetriever(
    graph_store=graph_store,
    vector_store=vector_store_v2,
    embed_model=emb,
    similarity_top_k=3,
    include_text=True,
)

results_v2 = vec_ret_v2.retrieve(QueryBundle(query_str=query))
print(f"  retrieved {len(results_v2)} NodeWithScore")
for i, r in enumerate(results_v2):
    print(f"  [{i}] type={type(r.node).__name__} score={r.score:.4f}")
    print(f"      text: {r.node.get_content()[:80]!r}")
    if r.node.metadata:
        keys = list(r.node.metadata.keys())
        print(f"      metadata keys: {keys}")
        section_id = r.node.metadata.get("section_id")
        approval_status = r.node.metadata.get("approval_status")
        kg_node_id = r.node.metadata.get("kg_node_id")
        print(f"      section_id = {section_id!r}, approval_status = {approval_status!r}, kg_node_id = {kg_node_id!r}")
    else:
        print(f"      metadata = empty")


banner("DONE")
