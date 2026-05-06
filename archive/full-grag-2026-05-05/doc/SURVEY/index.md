# Phase 0 表面マップ調査 — 状態一覧

最終更新: 2026-04-28

> **Phase 0 + Phase 0.5 完了レポート（ユーザーレビュー材料）**: [SUMMARY.md](SUMMARY.md) を参照
> 個別調査詳細は本書の各項目リンクから 01_*.md 〜 12_*.md へ


## 検証環境（version pin）

| 項目 | 値 |
|---|---|
| Python | 3.12.3 (`/usr/bin/python3`) |
| venv | `spike/.venv` (pip 26.1) |
| Ollama | 0.21.2 (daemon localhost:11434) |
| Ollama embedding model | nomic-embed-text:latest (id: 0a109f422b47, 274 MB) |
| Claude CLI | 2.1.119 (Claude Code) |
| Codex CLI | 0.93.0 (codex-cli) |
| `llama-index-core` | **0.14.21** |
| `llama-index-embeddings-ollama` | **0.9.0** |
| `llama-index-instrumentation` | 0.5.0 |
| `llama-index-workflows` | 2.20.0 |
| `pydantic` | 2.13.3 |
| `ollama` (Python client) | 0.6.1 |
| 検証日 | _pending Phase 0 完了時に確定_ |
| 検証 commit | _pending_ |

## 統合方式（Phase 0 で評価、DESIGN.ja.md §4.1）

| 案 | 概要 | 前提検証項目 |
|---|---|---|
| **A: 外部抽出 → 投入方式** | Claude/Codex CLI で entity / relation を抽出 → JSON → LlamaIndex graph store に直接投入。LlamaIndex は graph store / retriever / traversal / embedding search に専念 | 02-2d（事前抽出済 triplet 投入 API） |
| **B: LLM wrapper 方式** | Claude/Codex CLI を LlamaIndex `LLM` interface でラップ → SchemaLLMPathExtractor 等に渡す | 02-2a（LLM interface 要求）、12（subprocess 最小確認） |
| **C: 混合** | 一部 LLM 不要 extractor + 一部外部抽出 + retriever は LlamaIndex 側 | 02-2e（独自 extractor 受理）、02-2f（LLM 不要 extractor 存在） |

## 調査項目状態（12 項目）

| # | 項目 | WebFetch | GitHub | Spike | 判定 |
|---|---|---|---|---|---|
| [01](01_property_graph_index.md) | PropertyGraphIndex API 安定度 | ✓ | ✓ | ✓ | **usable_with_caveat**（kg_extractors=[ImplicitPathExtractor()] 必須 / load_index_from_storage 不使用）|
| [02](02_schema_llm_path_extractor.md) | SchemaLLMPathExtractor 制約強度と統合方式 (2a-2f) | ✓ | ✓ | 部分 | partially usable（A: usable / B: 未実証 / C: usable）|
| [03](03_simple_property_graph_store.md) | SimplePropertyGraphStore 永続化粒度 | ✓ | ✓ | ✓ | **usable**（store.delete は使わず safe_delete_by_section 経由）|
| [04](04_incremental_update.md) | incremental update 方式 | ✓ | ✓ | ✓ | usable_with_wrapper（safe_delete_by_section wrapper 必須、設計確定）|
| [05](05_hybrid_retriever.md) | HybridRetriever / PGRetriever fusion 戦略 | ✓ | ✓ | ✓ | usable_with_wrapper（API 動作 ✓、vector_store 連結詳細は実装時詰め）|
| [06](06_hipporag_lightrag.md) | HippoRAG / LightRAG retrieval 統合 | ✓ | — | — | not_present_in_lpg_guide（spec-grag MVP では除外）|
| [07](07_persistent_property.md) | 恒久プロパティの node/relation metadata | ✓ | ✓ | ✓ | **usable**（永続化保持 ✓、retrieval 経由 metadata は実装時詰め）|
| [08](08_transient_annotation.md) | transient annotation の実装パターン | — | — | ✓ | **usable**（NodeWithScore.metadata 後付け、graph 不汚染、永続化分離を spike 03 で実証）|
| [09](09_spec_core_all.md) | /spec-core --all 全再構築の API 挙動 | — | — | ✓ | **usable**（spike 02 で動作実証）|
| [10](10_spec_core_incremental.md) | /spec-core incremental stale 除去整合 | ✓ | ✓ | ✓ | usable_with_wrapper（safe_delete_by_section wrapper 必須、設計確定）|
| [11](11_ollama_embedding.md) | Ollama embedding 接続 | ✓ | — | ✓ | **usable**（注入経路 spike 02 で実証済）|
| [12](12_claude_codex_subprocess.md) | Claude/Codex CLI subprocess 最小確認 | ✓ (CLI help) | — | ✓ | partially usable（API 構造把握 ✓、実認証下の動作は Phase 1 で詰め）|
| [13](13_path_b_design_options.md) | 案 B 設計オプション探索（Phase 1 ステップ 0a）| ✓ | — | — | 3 サブパターン提示（B-1 Ollama / B-2 Custom LLM / B-3 LiteLLM proxy）+ ハイブリッド可能性、ユーザー判断待ち |

判定値: `usable` / `usable_with_wrapper` / `risky` / `unusable` / `unknown`

## 起点 URL（Phase 0 で順次追記）

| カテゴリ | URL / 場所 |
|---|---|
| LlamaIndex 公式 docs (top) | https://developers.llamaindex.ai/python/framework/ (旧 https://docs.llamaindex.ai/ から 301 redirect) |
| LlamaIndex Python GitHub | https://github.com/run-llama/llama_index |
| Property Graph Index guide | https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/ |
| OllamaEmbedding integration | https://developers.llamaindex.ai/python/framework/integrations/embeddings/ollama_embedding/ |
| Ollama LLM integration | https://developers.llamaindex.ai/python/framework/integrations/llm/ollama/ |
| SchemaLLMPathExtractor docs | _PG guide page から sub-link 探索が必要、または GitHub source 直接読み_ |
| SimplePropertyGraphStore source | _GitHub `llama_index/core/graph_stores/simple_lpg.py` を後で確認_ |
| Codex CLI docs (`codex exec` 等) | _pending fetch_ |
| Claude Code CLI docs | _pending fetch_ |

## 関連

- [doc/DESIGN.ja.md](../DESIGN.ja.md) §1.4 / §4.1
- [doc/TODO.md](../TODO.md) Phase 0 / 0.5
- [doc/EXTERNAL_DESIGN.ja.md](../EXTERNAL_DESIGN.ja.md) (不変)
- [CLAUDE.md](../../CLAUDE.md) ルール 1〜8
- [spike/](../../spike/) — Phase 0.5 の最小実行スパイク（pending）
