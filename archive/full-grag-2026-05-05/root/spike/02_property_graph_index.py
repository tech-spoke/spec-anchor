"""
spike 02: PropertyGraphIndex 構築 + Settings.embed_model + 全再構築

実証する Phase 0 項目（doc/TODO.md Phase 0.5 spike 計画 #02）:
- 01: PropertyGraphIndex.from_existing の動作確認
- 09: /spec-core --all 相当の shutil.rmtree(persist_dir) + 全再構築
- 11-注入: Settings.embed_model = OllamaEmbedding 注入経路

シナリオ:
  STEP 1: Settings.embed_model = OllamaEmbedding 注入
  STEP 2: SimplePropertyGraphStore + SimpleVectorStore + 案 A 直接投入
  STEP 3: PropertyGraphIndex.from_existing で index 構築
  STEP 4: storage_context.persist
  STEP 5: reload (StorageContext.from_defaults + load_index_from_storage)
  STEP 6: /spec-core --all 相当 — shutil.rmtree + 全再構築

usage:
  spike/.venv/bin/python spike/02_property_graph_index.py
"""

from __future__ import annotations

import os
import shutil

from llama_index.core import (
    PropertyGraphIndex,
    Settings,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode, Relation
from llama_index.core.indices.property_graph import ImplicitPathExtractor
from llama_index.core.vector_stores.simple import SimpleVectorStore
from llama_index.embeddings.ollama import OllamaEmbedding


PERSIST_DIR = "./spike_storage/02"


def banner(msg: str) -> None:
    print()
    print("=" * 64)
    print(msg)
    print("=" * 64)


def build_initial_data() -> tuple[list[EntityNode], list[Relation]]:
    section_a = [
        EntityNode(
            name="user_authentication",
            label="Concept",
            properties={
                "section_id": "section_a",
                "heading_path": "1 / 認証",
                "source_hash": "hash_a_001",
                "approval_status": "approved",
            },
        ),
        EntityNode(
            name="oauth2_required",
            label="Constraint",
            properties={
                "section_id": "section_a",
                "heading_path": "1 / 認証",
                "source_hash": "hash_a_002",
                "approval_status": "approved",
            },
        ),
    ]
    section_b = [
        EntityNode(
            name="user_session",
            label="Concept",
            properties={
                "section_id": "section_b",
                "heading_path": "2 / セッション",
                "source_hash": "hash_b_001",
                "approval_status": "approved",
            },
        ),
    ]
    rels = [
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
    ]
    return section_a + section_b, rels


# =====================================================================
banner("spike 02: PropertyGraphIndex.from_existing + Settings.embed_model + 全再構築")

# クリーンアップ
if os.path.exists(PERSIST_DIR):
    shutil.rmtree(PERSIST_DIR)
os.makedirs(PERSIST_DIR, exist_ok=True)


# ---------------------------------------------------------------------
banner("STEP 1: Settings.embed_model = OllamaEmbedding 注入（項目 11-注入）")
emb = OllamaEmbedding(
    model_name="nomic-embed-text",
    base_url="http://localhost:11434",
)
Settings.embed_model = emb
print(f"  Settings.embed_model = {type(Settings.embed_model).__name__}")
print(f"  test embedding dim = {len(emb.get_text_embedding('hello'))}")


# ---------------------------------------------------------------------
banner("STEP 2: SimplePropertyGraphStore + SimpleVectorStore + 案 A 直接投入")
graph_store = SimplePropertyGraphStore()
vector_store = SimpleVectorStore()

nodes, rels = build_initial_data()
graph_store.upsert_nodes(nodes)
graph_store.upsert_relations(rels)
print(f"  graph_store: nodes = {len(graph_store.get())}")
print(f"  graph_store: triplets = {len(graph_store.graph.get_triplets())}")


# ---------------------------------------------------------------------
banner("STEP 3: PropertyGraphIndex.from_existing で index 構築（項目 01）")
try:
    index = PropertyGraphIndex.from_existing(
        property_graph_store=graph_store,
        vector_store=vector_store,
        embed_kg_nodes=False,  # 既存 entity への embedding 自動計算をしない
        # ★ 案 A: kg_extractors=[] では falsy 判定で default LLM extractor が呼ばれるため、
        #         LLM 不要の ImplicitPathExtractor() のみを渡して LLM 解決を回避する
        kg_extractors=[ImplicitPathExtractor()],
    )
    print(f"  [OK] PropertyGraphIndex constructed: {type(index).__name__}")
    print(f"  index.property_graph_store: {type(index.property_graph_store).__name__}")
except Exception as e:
    print(f"  [FAIL] PropertyGraphIndex.from_existing: {type(e).__name__}: {e}")
    raise


# ---------------------------------------------------------------------
banner("STEP 4: storage_context.persist（項目 01）")
try:
    index.storage_context.persist(persist_dir=PERSIST_DIR)
    print(f"  [OK] persisted to {PERSIST_DIR}")
    print(f"  files in {PERSIST_DIR}:")
    for f in sorted(os.listdir(PERSIST_DIR)):
        full = os.path.join(PERSIST_DIR, f)
        if os.path.isfile(full):
            print(f"    {f}: {os.path.getsize(full)} bytes")
        else:
            print(f"    {f}/ (dir)")
except Exception as e:
    print(f"  [FAIL] persist: {type(e).__name__}: {e}")
    raise


# ---------------------------------------------------------------------
banner("STEP 5: reload (StorageContext.from_defaults + load_index_from_storage)")

# まず graph_store だけ単独で reload してみる
loaded_store_only = SimplePropertyGraphStore.from_persist_dir(PERSIST_DIR)
print(f"  [OK] graph_store reload (alone): nodes = {len(loaded_store_only.get())}")

# 次に PropertyGraphIndex 全体を reload する
try:
    storage_ctx = StorageContext.from_defaults(
        persist_dir=PERSIST_DIR,
        property_graph_store=loaded_store_only,
    )
    loaded_index = load_index_from_storage(storage_ctx)
    print(f"  [OK] PropertyGraphIndex loaded: {type(loaded_index).__name__}")
    loaded_store = loaded_index.property_graph_store
    print(f"  loaded graph_store: nodes = {len(loaded_store.get())}")
    sample_a = loaded_store.get(properties={"section_id": "section_a"})
    if sample_a:
        print(f"    sample section_a node: {sample_a[0].name}")
        print(f"      properties = {sample_a[0].properties}")
except Exception as e:
    print(f"  [WARN] load_index_from_storage failed: {type(e).__name__}: {e}")
    print(f"  → graph_store の単独 reload は OK、index 全体は別途調査")


# ---------------------------------------------------------------------
banner("STEP 6: /spec-core --all 相当 — shutil.rmtree + 全再構築（項目 09）")
print(f"  before rmtree: PERSIST_DIR exists = {os.path.exists(PERSIST_DIR)}")
shutil.rmtree(PERSIST_DIR)
print(f"  after rmtree:  PERSIST_DIR exists = {os.path.exists(PERSIST_DIR)}")

# 新しい store + index で再構築（同じデータで再投入）
os.makedirs(PERSIST_DIR, exist_ok=True)
new_graph_store = SimplePropertyGraphStore()
new_vector_store = SimpleVectorStore()
nodes2, rels2 = build_initial_data()
new_graph_store.upsert_nodes(nodes2)
new_graph_store.upsert_relations(rels2)

new_index = PropertyGraphIndex.from_existing(
    property_graph_store=new_graph_store,
    vector_store=new_vector_store,
    embed_kg_nodes=False,
    kg_extractors=[ImplicitPathExtractor()],  # ★ 案 A、LLM 解決回避
)
new_index.storage_context.persist(persist_dir=PERSIST_DIR)
print(f"  [OK] rebuilt and persisted to {PERSIST_DIR}")
print(f"  files: {sorted(os.listdir(PERSIST_DIR))}")
print(f"  nodes after rebuild: {len(new_graph_store.get())}")
print(f"  triplets after rebuild: {len(new_graph_store.graph.get_triplets())}")

banner("DONE")
