"""
spike 01: 案 A（外部抽出 → 直接投入）+ 章単位 stale 除去シナリオ

最重要シナリオ（DESIGN §1.9 経路 1 の核心）:

1. spec-grag schema に従う entity / relation を Python コードで手書き（案 A の外部抽出を模擬）
2. SimplePropertyGraphStore に upsert_nodes / upsert_relations で直接投入
3. persist / reload
4. 章 B 削除シナリオを 2 つの方式で比較:
   - **raw delete**: store.delete(properties={"section_id": "section_b"})  ← 破綻する
   - **safe delete**: to_dict → spec-grag 側で section_id filter → from_dict ← spec-grag 推奨
5. JSON 永続化ファイルの構造観察

確認したい項目:
- 案 A: kg_extractors / SchemaLLMPathExtractor を使わず、直接 store 操作のみで graph 構築可（項目 02-2d）
- properties dict に恒久プロパティを保持できる（項目 07）
- persist / reload で properties 保持（項目 03 / 07）
- raw delete の挙動（項目 04 / 10、cascade 過剰）
- safe delete wrapper の動作（項目 04 / 10、spec-grag 推奨パターン）
- get_rel_map で graph traversal（項目 05）

usage:
  spike/.venv/bin/python spike/01_property_graph_basic.py
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import (
    DEFAULT_PG_PERSIST_FNAME,
    EntityNode,
    Relation,
)

PERSIST_DIR = "./spike_storage/01"


def banner(msg: str) -> None:
    print()
    print("=" * 64)
    print(msg)
    print("=" * 64)


def show_summary(store: SimplePropertyGraphStore, label: str, *, allow_keyerror: bool = False) -> None:
    a_nodes = store.get(properties={"section_id": "section_a"})
    b_nodes = store.get(properties={"section_id": "section_b"})
    all_nodes = store.get()
    print(f"  [{label}]")
    print(f"    nodes total      = {len(all_nodes)}")
    print(f"    nodes section_a  = {len(a_nodes)}")
    print(f"    nodes section_b  = {len(b_nodes)}")
    try:
        all_triplets = store.graph.get_triplets()
        print(f"    triplets total   = {len(all_triplets)}")
    except KeyError as e:
        if allow_keyerror:
            print(f"    triplets total   = ERROR (KeyError: {e}) ← dangling reference")
        else:
            raise


def build_initial_data() -> tuple[list[EntityNode], list[Relation]]:
    section_a_nodes = [
        EntityNode(
            name="user_authentication",
            label="Concept",
            properties={
                "section_id": "section_a",
                "heading_path": "1 / 認証",
                "source_hash": "hash_a_001",
                "source_span": "[1:1-50]",
                "approval_status": "approved",
                "concept_id": "concept-uauth-001",
            },
        ),
        EntityNode(
            name="oauth2_required",
            label="Constraint",
            properties={
                "section_id": "section_a",
                "heading_path": "1 / 認証",
                "source_hash": "hash_a_002",
                "source_span": "[1:25-40]",
                "approval_status": "approved",
            },
        ),
    ]
    section_a_rels = [
        Relation(
            label="CONSTRAINS",
            source_id="oauth2_required",
            target_id="user_authentication",
            properties={"section_id": "section_a"},
        ),
    ]
    section_b_nodes = [
        EntityNode(
            name="user_session",
            label="Concept",
            properties={
                "section_id": "section_b",
                "heading_path": "2 / セッション",
                "source_hash": "hash_b_001",
                "source_span": "[2:1-30]",
                "approval_status": "approved",
                "concept_id": "concept-usess-001",
            },
        ),
        EntityNode(
            name="session_timeout_30min",
            label="Constraint",
            properties={
                "section_id": "section_b",
                "heading_path": "2 / セッション",
                "source_hash": "hash_b_002",
                "source_span": "[2:15-25]",
                "approval_status": "approved",
            },
        ),
    ]
    section_b_rels = [
        # 章 B の relation だが target は 章 A の entity（章をまたぐ DEPENDS_ON）
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
    return section_a_nodes + section_b_nodes, section_a_rels + section_b_rels


def safe_delete_by_section(
    store: SimplePropertyGraphStore, section_id: str
) -> SimplePropertyGraphStore:
    """
    spec-grag 推奨: to_dict → filter → from_dict で章単位削除

    LlamaIndex の delete API は subj/obj を巻き込んで消すため、章をまたぐ
    relation で対岸の章の entity を巻き添えにしてしまう。spec-grag は
    to_dict 経由で graph 全体を取り出し、section_id を持つ node / relation /
    triplet を一貫して filter してから from_dict で再構築する。
    """
    data = store.graph.model_dump()  # pydantic v2: dict 化
    raw_nodes: dict[str, Any] = data.get("nodes", {})
    raw_relations: dict[str, Any] = data.get("relations", {})
    raw_triplets = data.get("triplets", set())

    # 1. section_id 一致の node を除外
    kept_nodes = {
        nid: ndict
        for nid, ndict in raw_nodes.items()
        if (ndict.get("properties") or {}).get("section_id") != section_id
    }
    kept_node_ids = set(kept_nodes.keys())

    # 2. section_id 一致の relation を除外
    kept_relations = {
        rkey: rdict
        for rkey, rdict in raw_relations.items()
        if (rdict.get("properties") or {}).get("section_id") != section_id
    }

    # 3. triplet で「source / target が消えた」もの、または relation 自体が
    #    消えたものを除外
    if isinstance(raw_triplets, set):
        triplets_iter = raw_triplets
    else:
        triplets_iter = set(tuple(t) for t in raw_triplets)
    kept_triplets = set()
    for t in triplets_iter:
        subj_id, rel_id, obj_id = t
        if subj_id not in kept_node_ids:
            continue
        if obj_id not in kept_node_ids:
            continue
        # relation key の reconstruction: source_id_label_target_id
        rel_key = f"{subj_id}_{rel_id}_{obj_id}"
        if rel_key not in kept_relations:
            continue
        kept_triplets.add(t)

    new_data = {
        "nodes": kept_nodes,
        "relations": kept_relations,
        "triplets": kept_triplets,
    }

    return SimplePropertyGraphStore.from_dict(new_data)


# =====================================================================
banner("spike 01: SimplePropertyGraphStore + 案 A 直接投入 + safe vs raw delete")

# 0. クリーンアップ
if os.path.exists(PERSIST_DIR):
    shutil.rmtree(PERSIST_DIR)
os.makedirs(PERSIST_DIR, exist_ok=True)

# ---------------------------------------------------------------------
banner("STEP 1: 案 A 模擬（手書き entity / relation を投入、kg_extractors 不使用）")
all_nodes, all_rels = build_initial_data()
store = SimplePropertyGraphStore()
store.upsert_nodes(all_nodes)
store.upsert_relations(all_rels)
show_summary(store, "after upsert")

# ---------------------------------------------------------------------
banner("STEP 2: persist / reload")
persist_path = os.path.join(PERSIST_DIR, DEFAULT_PG_PERSIST_FNAME)
store.persist(persist_path=persist_path)
print(f"  persisted to {persist_path}")
print(f"  file size = {os.path.getsize(persist_path)} bytes")

reloaded = SimplePropertyGraphStore.from_persist_path(persist_path)
show_summary(reloaded, "after reload")
print(f"  reload OK: properties が保たれているか")
sample_a = reloaded.get(properties={"section_id": "section_a"})
if sample_a:
    n = sample_a[0]
    print(f"    sample {n.id}: properties = {n.properties}")

# ---------------------------------------------------------------------
banner("STEP 3a: 【NG パターン】 raw delete(properties={section_id: section_b})")
import copy

raw_store = SimplePropertyGraphStore.from_persist_path(persist_path)
raw_store.delete(properties={"section_id": "section_b"})
show_summary(raw_store, "after RAW delete", allow_keyerror=True)

print(f"  → 章 A の user_authentication が DEPENDS_ON triplet で巻き込まれて消えていないか:")
remaining_nodes = raw_store.get()
print(f"    remaining nodes = {[n.id for n in remaining_nodes]}")
ua = raw_store.get(ids=["user_authentication"])
if ua:
    print(f"    user_authentication: still present (good)")
else:
    print(f"    ★ user_authentication: DELETED (BAD — section_a の entity が巻き込まれた)")

print(f"  triplets set 内の dangling reference:")
internal_triplets = list(raw_store.graph.triplets)
print(f"    triplets set size = {len(internal_triplets)}")
print(f"    nodes dict size  = {len(raw_store.graph.nodes)}")
print(f"    relations dict size = {len(raw_store.graph.relations)}")

# ---------------------------------------------------------------------
banner("STEP 3b: 【OK パターン】 safe_delete_by_section(section_b) — spec-grag 推奨")
safe_store = safe_delete_by_section(reloaded, section_id="section_b")
show_summary(safe_store, "after SAFE delete")

print(f"  → 章 A は完全保存:")
ua = safe_store.get(ids=["user_authentication"])
if ua:
    print(f"    user_authentication: present (GOOD)")
    print(f"      properties = {ua[0].properties}")
oa = safe_store.get(ids=["oauth2_required"])
if oa:
    print(f"    oauth2_required: present (GOOD)")

print(f"  → 章 B は完全消去:")
us = safe_store.get(ids=["user_session"])
print(f"    user_session: {'absent (GOOD)' if not us else 'still present (BAD)'}")
sto = safe_store.get(ids=["session_timeout_30min"])
print(f"    session_timeout_30min: {'absent (GOOD)' if not sto else 'still present (BAD)'}")

# 章 A の relation だけ残っているか
remaining_triplets = list(safe_store.graph.get_triplets())
print(f"  remaining triplets (count={len(remaining_triplets)}):")
for t in remaining_triplets:
    print(f"    {t[0].id} -[{t[1].label}, props={t[1].properties}]-> {t[2].id}")

# ---------------------------------------------------------------------
banner("STEP 4: 章 B 修正版を upsert (user_session_v2)")
new_b_nodes = [
    EntityNode(
        name="user_session_v2",
        label="Concept",
        properties={
            "section_id": "section_b",
            "heading_path": "2 / セッション",
            "source_hash": "hash_b_001_v2",
            "source_span": "[2:1-35]",
            "approval_status": "approved",
            "concept_id": "concept-usess-002",
        },
    ),
]
new_b_rels = [
    Relation(
        label="DEPENDS_ON",
        source_id="user_session_v2",
        target_id="user_authentication",
        properties={"section_id": "section_b"},
    ),
]
safe_store.upsert_nodes(new_b_nodes)
safe_store.upsert_relations(new_b_rels)
show_summary(safe_store, "after upsert v2")

# ---------------------------------------------------------------------
banner("STEP 5: get_rel_map (depth=2 from user_authentication)")
seed = safe_store.get(ids=["user_authentication"])
print(f"  seed: {[n.id for n in seed]}")
rel_map = safe_store.get_rel_map(seed, depth=2, limit=30)
print(f"  rel_map size = {len(rel_map)}")
for t in rel_map:
    print(f"    {t[0].id} -[{t[1].label}]-> {t[2].id}")

# ---------------------------------------------------------------------
banner("STEP 6: JSON ファイル構造を peek")
v2_path = os.path.join(PERSIST_DIR, "property_graph_store_v2.json")
safe_store.persist(persist_path=v2_path)

with open(v2_path, encoding="utf-8") as f:
    data = json.load(f)

print(f"  top-level keys: {list(data.keys())}")
for k, v in data.items():
    if isinstance(v, dict):
        print(f"  data[{k}] dict size = {len(v)}")
    elif isinstance(v, list):
        print(f"  data[{k}] list size = {len(v)}")
    else:
        print(f"  data[{k}] = {type(v).__name__}")

# 1 node 1 relation を抜粋
if "nodes" in data and data["nodes"]:
    first_id = next(iter(data["nodes"]))
    print(f"  sample node[{first_id}] =")
    print(f"    {json.dumps(data['nodes'][first_id], ensure_ascii=False, indent=2)}")
if "relations" in data and data["relations"]:
    first_id = next(iter(data["relations"]))
    print(f"  sample relation[{first_id}] =")
    print(f"    {json.dumps(data['relations'][first_id], ensure_ascii=False, indent=2)}")
if "triplets" in data:
    print(f"  triplets sample (up to 3): {data['triplets'][:3] if isinstance(data['triplets'], list) else list(data['triplets'])[:3]}")

banner("DONE")
