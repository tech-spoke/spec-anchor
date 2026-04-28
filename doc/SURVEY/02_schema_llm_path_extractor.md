# 02: SchemaLLMPathExtractor 制約強度と統合方式 (2a–2f)

> 状態: WebFetch 部分確認済（2d / 2e / 2f は確定、2a / 2b / 2c は未確認）
> 判定 **partially usable** — 案 A / 案 C の前提が API 上で成立、案 B は要追加調査
> 最終更新: 2026-04-28

DESIGN.ja.md §4.1 の 2a〜2f を実証する。各 sub-item の結果が **案 A / B / C**（doc/SURVEY/index.md）の判定に直結する。

## 調査対象

- component: `llama_index.core.indices.property_graph.SchemaLLMPathExtractor` ほか extractor 群
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: _pending fetch_
  - 実行確認: _pending spike/_

## sub-items

### 2a. LlamaIndex `LLM` interface 要求 — 案 B の前提検証

- 同期 completion で済むか / async / streaming / structured output 必須か: **未確認**
- subprocess 駆動の Claude/Codex CLI wrapper を `LLM` interface に直接差せるか: **未確認**
- 実測: pending

判定: **unknown**（案 B の前提は未検証）

### 2b. スキーマ受理形式

- dataclass / pydantic / dict / TypedDict / その他: **未確認**（pydantic 想定だが要 GitHub source 確認）
- 実測: pending

判定: **unknown**

### 2c. `strict=True` で schema 外 triplet が拒否されるか

- 拒否される / 警告のみ / 通過してしまう: **未確認**
- 拒否のレベル（プロンプト誘導 / parser / runtime validation / 型システム）: **未確認**
- 実測: pending

判定: **unknown**

### 2d. 事前抽出済み triplet の直接投入 API — 案 A の前提検証

- `graph_store.upsert_nodes(entities)` / `graph_store.upsert_relations(relations)` で **直接投入可能**（WebFetch で確認）
- `index.insert_nodes(nodes)` も使える可能性（要 spike 実証）
- spike で実証する余地: 直接投入 + persist / reload で entity / relation が保持されるか

判定: **usable**（案 A の前提成立）

### 2e. `kg_extractors` の独自 extractor 受理 — 案 C の前提検証

- **list 受理確定**（WebFetch、複数 extractor 組み合わせ可能）
- カスタム extractor は **`TransformComponent` をサブクラス化**
- default は `SimpleLLMPathExtractor` + `ImplicitPathExtractor`

判定: **usable**（案 C の前提成立）

### 2f. LLM 不要 extractor の存在

- **`ImplicitPathExtractor` 存在確認**（`from llama_index.core.indices.property_graph import ImplicitPathExtractor`、default の一部）
- 用途範囲は要 GitHub source 確認（node の relationship 属性から path を読む程度と推定、要実証）

判定: **usable**（存在確認、用途範囲は要追加調査）

## 確認した API

- import path: `from llama_index.core.indices.property_graph import SchemaLLMPathExtractor`
- 関連 extractors（同 import path）:
  - `SimpleLLMPathExtractor`
  - `ImplicitPathExtractor`（LLM 不要）
  - `DynamicLLMPathExtractor`

## 実測・検証結果

- 最小コードで動いたこと: _pending spike/_
- 動かなかったこと: _pending_

## spec-grag への影響

- 案 A / 案 C は API 上の前提が成立 → 採用候補に残せる
- 案 B は SchemaLLMPathExtractor の内部 LLM interface 要求次第（2a 未確認）
- DESIGN §1.8（candidate_only）を維持できる: SchemaLLMPathExtractor の中身に判断契約を委譲しない、外側で抽出した結果を投入する設計が成立
- 未解決事項:
  - SchemaLLMPathExtractor 自体の内部実装（プロンプト / structured output 要求）→ 案 B 成否判定
  - スキーマ受理形式（pydantic dataclass か）→ 2b
  - strict=True の挙動 → 2c
  - ImplicitPathExtractor の用途範囲（どんな relation を読めるか）→ 2f の精度

## 判定

**partially usable** — 案 A / 案 C は usable、案 B は unknown
