# 02: SchemaLLMPathExtractor 制約強度と統合方式 (2a–2f)

> 状態: WebFetch ✓ / GitHub ✓（schema_llm.py + transformations/utils.py + retriever.py 確認）/ Spike ☐
> 判定 **usable** — 案 A: usable / 案 B: usable_with_wrapper / 案 C: usable
> 最終更新: 2026-04-28

DESIGN.ja.md §4.1 の 2a〜2f を実証する。

## 調査対象

- component: `llama_index.core.indices.property_graph.SchemaLLMPathExtractor` ほか extractor 群
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source:
    - `llama-index-core/llama_index/core/indices/property_graph/transformations/schema_llm.py`
    - `llama-index-core/llama_index/core/indices/property_graph/transformations/utils.py`
    - `llama-index-core/llama_index/core/indices/property_graph/transformations/{simple_llm,dynamic_llm,implicit}.py`
  - 実行確認: _pending spike/_

## sub-items

### 2a. LlamaIndex `LLM` interface 要求 — 案 B の前提検証

**GitHub source 確認**（`schema_llm.py`）:

- `from llama_index.core.llms.llm import LLM` の `LLM` クラスを必須引数として受け取る
- constructor signature: `llm: LLM` (mandatory)
- subprocess 駆動の Claude/Codex CLI wrapper を `LLM` の **subclass として実装**すれば差し込み可能
- `_aextract` 等の内部メソッドで LLM の structured output API（推定 `apredict_and_call` / `astructured_predict` 系）を呼ぶ想定 → 要追加 source 確認 + spike

**実装パターン**（案 B、spec-grag 側で書く想定）:

```python
class CodexCLIAdapter(LLM):
    """Wrap codex exec --output-schema as a LlamaIndex LLM."""
    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        # subprocess.run([codex, exec, --output-schema, schema_path, prompt], capture_output=True)
        ...
    async def acomplete(self, prompt: str, **kwargs) -> CompletionResponse:
        ...
    # その他 LlamaIndex LLM が要求する method 群を実装
```

判定: **usable_with_wrapper**（subprocess wrapper を `LLM` subclass で実装する設計工数あり）

### 2b. スキーマ受理形式

**GitHub source 確認**（`schema_llm.py`, `transformations/utils.py`）:

- `possible_entities: Optional[Type[Any]]` ← **`Literal[...]` 型**で渡す（例: `Literal["Concept", "Requirement", "Constraint", ...]`）
- `possible_relations: Optional[Type[Any]]` ← Literal 型
- `possible_entity_props: Optional[Union[List[str], List[Tuple[str, str]]]]` ← list of str or list of (name, description) tuple
- `possible_relation_props`: 同上
- `kg_validation_schema: Optional[Union[Dict[str, str], List[Triple]]]` ← **`List[Tuple[str, str, str]]`**（subject_type, relation, object_type）
- `kg_schema_cls: Any = None` ← **pydantic モデルを直接指定可能**（完全に schema 制御したい場合）
- 内部で `create_model` + `field_validator` を使い動的 pydantic モデル構築

**注意点**:

- `DEFAULT_ENTITIES` は business/news 語彙（PRODUCT / MARKET / TECHNOLOGY / ORGANIZATION / PERSON / ...）→ spec-grag では必ず `possible_entities` を spec-grag Core schema 用 Literal で上書きする
- `DEFAULT_SCHEMA_PATH_EXTRACT_PROMPT` は英語ハードコード → spec-grag は日本語 `extract_prompt` で差し替え必須

**spec-grag への適用**:

```python
SpecGragEntities = Literal[
    "Document", "Section", "SourceSpan",
    "Concept", "Requirement", "Constraint",
    "Decision", "OpenQuestion", "Conflict", "Rationale", "Alternative",
]
SpecGragRelations = Literal[
    "CONTAINS", "MENTIONS", "DEFINES", "HAS_EVIDENCE",
    "DEPENDS_ON", "CONSTRAINS", "REFINES", "SUPERSEDES",
    "CONFLICTS_WITH", "SUPPORTS", "ALTERNATIVE_TO", "RELATED_TO",
]
spec_grag_schema = [
    ("Section", "CONTAINS", "Section"),
    ("Section", "MENTIONS", "Concept"),
    # ...
]
```

判定: **usable**

### 2c. `strict=True` で schema 外 triplet が拒否されるか

**GitHub source 確認**（`transformations/utils.py` の `get_entity_class` / `get_relation_class`）:

- `strict=True`（default）: pydantic field の `type` を `possible_entities`（Literal）に固定 → 範囲外の値は **pydantic ValidationError**
- `strict=False`: pydantic field の `type` を `str` に → 任意の文字列 OK
- `clean_additional_properties=True`: `additionalProperties: false` を JSON schema に設定（OpenAI structured outputs / Google Gemini 互換）

```python
# from utils.py
def get_entity_class(possible_entities, possible_entity_props, strict, clean_additional_properties=False):
    return create_model(
        "Entity",
        type=(possible_entities if strict else str, Field(...)),
        name=(str, ...),
        ...
    )
```

LLM が schema 違反 JSON を返した場合のリトライ挙動は要 spike（pydantic ValidationError → LlamaIndex の `_aextract` 内で吸収か、そのまま伝播か）。

判定: **usable**（schema 外 triplet は pydantic Literal で deterministic に拒否、リトライ挙動は要 spike）

### 2d. 事前抽出済み triplet の直接投入 API — 案 A の前提検証

- `graph_store.upsert_nodes(entities)` / `graph_store.upsert_relations(relations)` で **直接投入可能**（WebFetch + 推定）
- `index.insert_nodes(nodes)` も使える可能性
- `EntityNode` / `Relation` / `Triplet` は `from llama_index.core.graph_stores.types import EntityNode, Relation, Triplet`（schema_llm.py の import から確認）

判定: **usable**（案 A の前提成立）

### 2e. `kg_extractors` の独自 extractor 受理 — 案 C の前提検証

- カスタム extractor は `TransformComponent` をサブクラス化（`from llama_index.core.schema import TransformComponent`、schema_llm.py の import から確認）
- **list 受理確定**（複数 extractor 組み合わせ可能）
- default は `SimpleLLMPathExtractor` + `ImplicitPathExtractor`

判定: **usable**（案 C の前提成立）

### 2f. LLM 不要 extractor の存在

- `ImplicitPathExtractor`: `transformations/implicit.py` に存在
- 用途範囲: node の relationship 属性から path を読む（推定、要 implicit.py 確認）
- spec-grag では section structure（`CONTAINS`, `MENTIONS`）の機械的抽出に補助的に使える可能性

判定: **usable**

## 確認した API

- import path: `from llama_index.core.indices.property_graph import SchemaLLMPathExtractor, SimpleLLMPathExtractor, ImplicitPathExtractor, DynamicLLMPathExtractor`
- 関連型 import: `from llama_index.core.graph_stores.types import EntityNode, Relation, Triplet, KG_NODES_KEY, KG_RELATIONS_KEY`
- LLM interface: `from llama_index.core.llms.llm import LLM`
- TransformComponent base: `from llama_index.core.schema import TransformComponent`

## 実測・検証結果

- 最小コードで動いたこと: _pending spike/_（pydantic schema 違反時の挙動を実証）
- LLM が schema 違反 JSON を返した場合のリトライ挙動: _pending spike/_

## spec-grag への影響

- 案 A / 案 B / 案 C **すべて API レベルで成立**
- spec-grag 設計判断:
  - 案 A: `graph_store.upsert_nodes/relations` で外部抽出 JSON を直接投入 → spec-grag CLI が抽出責務を持つ → **責務分離が綺麗**
  - 案 B: `LLM` subclass を作って SchemaLLMPathExtractor に差す → LlamaIndex の prompt / pydantic validation を活用できる → **wrapper 工数が必要**
  - 案 C: `ImplicitPathExtractor`（document structure 抽出、LLM 不要）+ 外部抽出（意味要素、Claude/Codex CLI）+ kg_extractors にカスタム extractor を差す混合 → **柔軟性最大**
- DESIGN §1.8（candidate_only）を維持: SchemaLLMPathExtractor を **使う / 使わない** の自由度は spec-grag 側にある（candidate_only 契約と整合）
- 未解決事項:
  - LLM が pydantic ValidationError を起こした場合の retry 挙動 → spike
  - DEFAULT_ENTITIES / DEFAULT_RELATIONS を完全に上書きできるか（partial override の落とし穴）

## 判定

**usable** — 全サブアイテム usable / usable_with_wrapper、案 A / B / C すべて成立
