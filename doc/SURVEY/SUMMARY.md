# Phase 0 + Phase 0.5 完了レポート（ユーザーレビュー材料）

> 作成日: 2026-04-28
> commit: e020524（spike 04 完了時点）
> 本書の位置付け: Phase 1 開始前にユーザーレビューを受けるための実証結果サマリ。
> 個別の調査詳細は `doc/SURVEY/01_*.md` 〜 `12_*.md` を参照。

## 1. Phase 0 / 0.5 のスコープ

- **目的**: LlamaIndex 系の API・限界を実装レベルで把握し、DESIGN.ja.md §1 の仮分担を再評価する根拠を取る
- **検証環境（version pin）**:
  - Python 3.12.3
  - llama-index-core==**0.14.21**
  - llama-index-embeddings-ollama==**0.9.0**
  - Ollama 0.21.2（nomic-embed-text:latest、dim=768）
  - Claude CLI 2.1.119 / Codex CLI 0.93.0
- **手段**: WebFetch（公式 docs）/ GitHub source / spike 0-4 の三層実証

## 2. 12 項目最終判定（一覧）

| # | 項目 | 判定 | 実証根拠 |
|---|---|---|---|
| 01 | PropertyGraphIndex API 安定度 | **usable_with_caveat** | spike 02。落とし穴 2 つあり（後述）|
| 02 | SchemaLLMPathExtractor 制約強度 (2a-2f) | **partially usable** | 2d/2f は spike 実証、2a/2b/2c/2e は GitHub source 確認止まり（**案 A 採用なら必須でない**）|
| 03 | SimplePropertyGraphStore 永続化粒度 | **usable** | spike 01。JSON 永続化、`to_dict`/`from_dict`、`get_rel_map(depth=2)`|
| 04 | incremental update 方式 | **usable_with_wrapper** | spike 01。`safe_delete_by_section` wrapper 必須（spec-grag 側責務）|
| 05 | PGRetriever fusion 戦略 | **usable_with_wrapper** | spike 03。fusion / rerank / 4 軸 / vector_store 連結はすべて spec-grag Orchestrator 側 |
| 06 | HippoRAG / LightRAG | **not_present_in_lpg_guide** | spec-grag MVP では除外 |
| 07 | 恒久プロパティ metadata | **usable** | spike 01/03。永続化保持 ✓、retrieval 経由 metadata 伝播は wrapper 設計（Phase 1）|
| 08 | transient annotation 実装パターン | **usable** | spike 03。`NodeWithScore.metadata` 後付け、graph 不汚染、永続化分離を実証 |
| 09 | /spec-core --all 全再構築 | **usable** | spike 02。`shutil.rmtree(persist_dir)` + 新 store + persist で動作 |
| 10 | /spec-core incremental stale 除去 | **usable_with_wrapper** | spike 01。項目 04 と同根拠 |
| 11 | Ollama embedding 接続 | **usable** | spike 00/02。dim=768、JP/EN OK、`Settings.embed_model` 注入確認 |
| 12 | Claude/Codex CLI subprocess | **partially usable** | spike 04。API 構造把握、実認証下の動作（出力揺れ等）は Phase 1 で詰め |

unknown はゼロ。

## 3. 採用統合方式の根拠

DESIGN.ja.md §4.1 で立てた **案 A / 案 B / 案 C** の評価が Phase 0 で確定。

### 案 A: 外部抽出 → 直接投入（採用）

**実証根拠**:

- spike 01: `graph_store.upsert_nodes(...)` / `upsert_relations(...)` で外部抽出済データを直接投入できる（4 nodes / 3 triplets を投入、persist 後 reload で完全保持）
- spike 02: `PropertyGraphIndex.from_existing(kg_extractors=[ImplicitPathExtractor()])` で LLM extractor を経由しない構築が動作
- spec-grag CLI が抽出責務を持つ → 責務分離が綺麗（Orchestrator がライブラリの判断契約を委譲しない）

**不採用とした案**:

| 案 | 不採用理由 |
|---|---|
| 案 B（CLI を `LLM` interface でラップ）| spike 02 の落とし穴で `Settings.llm` 解決が必要なケースが多く、wrapper 工数が大きい。サブスク認証 CLI を LlamaIndex `LLM` subclass で正しくラップするコストは Phase 3 実装時に評価する選択肢に留める |
| 案 C（混合）| `kg_extractors=[ImplicitPathExtractor()]` 自体は採用するが、LLM 抽出の本流を spec-grag CLI 側に置く（案 A 主体）。`ImplicitPathExtractor` は補助 |

→ **採用方針: 案 A 主体 + `ImplicitPathExtractor` 補助**（案 C の最小組合せ）。

## 4. spec-grag への確定設計含意

Phase 0 で実証された **動かすために必要な運用ルール 5 項目**：

### R1. `safe_delete_by_section` wrapper を spec-grag 側で実装する

- 出典: spike 01、SURVEY/04, 10
- LlamaIndex の `SimplePropertyGraphStore.delete()` は `delete_triplet` 内部で **subject と object 両方を nodes から削除する**ため、章をまたぐ relation で対岸の章の entity を巻き込んで消す。triplets set に dangling reference も残る
- 対処パターン:
  ```python
  def safe_delete_by_section(store, section_id):
      data = store.graph.model_dump()
      kept_nodes = {nid: nd for nid, nd in data["nodes"].items()
                    if (nd.get("properties") or {}).get("section_id") != section_id}
      kept_relations = {rk: rd for rk, rd in data["relations"].items()
                        if (rd.get("properties") or {}).get("section_id") != section_id}
      kept_node_ids = set(kept_nodes.keys())
      kept_triplets = {t for t in data["triplets"]
                       if t[0] in kept_node_ids and t[2] in kept_node_ids
                       and f"{t[0]}_{t[1]}_{t[2]}" in kept_relations}
      return SimplePropertyGraphStore.from_dict({
          "nodes": kept_nodes, "relations": kept_relations, "triplets": kept_triplets,
      })
  ```

### R2. `PropertyGraphIndex` 構築は `kg_extractors=[ImplicitPathExtractor()]` 必須

- 出典: spike 02、SURVEY/01
- 落とし穴: `kg_extractors=[]` は falsy 判定で **default の `[SimpleLLMPathExtractor, ImplicitPathExtractor]` が代入**され、`Settings.llm` 解決で OpenAI ImportError
- `[ImplicitPathExtractor()]` は truthy で default 代入を回避、LLM 不要

### R3. `load_index_from_storage` を使わず、graph_store 単独 reload + 毎セッション `from_existing` で再構築

- 出典: spike 02、SURVEY/01
- `load_index_from_storage(storage_ctx)` は内部で `Settings.llm` 解決を要求、未インストール環境で ImportError
- spec-grag 運用:
  ```python
  graph_store = SimplePropertyGraphStore.from_persist_dir(persist_dir)
  index = PropertyGraphIndex.from_existing(
      property_graph_store=graph_store,
      vector_store=vector_store,
      kg_extractors=[ImplicitPathExtractor()],
      embed_kg_nodes=False,
  )
  ```
- PropertyGraphIndex は薄いラッパで永続化対象ではない（永続化される本体は graph_store / vector_store / docstore）

### R4. PGRetriever の fusion / rerank / 4 軸付与 / vector_store 連結はすべて spec-grag Orchestrator 側責務

- 出典: spike 03、SURVEY/05, 07, 08
- LlamaIndex 標準: `PGRetriever._retrieve` は単純結合 + テキスト dedup のみ。RRF / Weighted / CombSum / MaxScore は無い
- `NodeWithScore.node.metadata` はデフォルトで空、entity properties は乗らない → spec-grag が **vector_store 投入時に TextNode.metadata に properties をコピーする責務**
- 4 軸 transient annotation の後付けは graph_store / persist パスから完全に分離（spike 03 で実証）

### R5. Claude / Codex CLI subprocess は `--bare` 不使用、サブスク認証 keychain を活かす

- 出典: spike 04、SURVEY/12
- `claude --bare` は OAuth/keychain を読まない仕様（CLI help 明記）→ "Not logged in" エラー
- spec-grag 運用パターン（推奨）:
  ```bash
  claude --print --no-session-persistence \
    --disable-slash-commands \
    --allowedTools "" \
    --exclude-dynamic-system-prompt-sections \
    --output-format json --json-schema '{...}' \
    --system-prompt 'spec-grag 固有の system prompt' \
    --model haiku <prompt>
  ```
- Codex `--model` 指定は環境ごとに利用可能なモデルを確認

## 5. Phase 1 / 実装時に詰める残課題

実装着手前に解決が必要な未解決事項：

| 項目 | 残課題 | 緊急度 |
|---|---|---|
| 05 / 07 retrieval | `vector_store` の `VECTOR_SOURCE_KEY` 連結で正規の vector 類似検索を動かす方法（spike 03 では 0 件返却） | **高**（経路 3 / 4 の retrieval が成立するか） |
| 12 Claude/Codex CLI | 実認証下での出力揺れ / rate limit / 認証切れの挙動 | 中（spec-grag CLI の error handling 設計に必要） |
| 02-2c | LLM が schema 違反 JSON を返した場合のリトライ / エラー伝播（案 B 採用時のみ） | 低（案 A 採用なら不要）|
| 01 | llama-index-core v0.14 系の breaking change 頻度 | 低（リリース管理時に追跡）|

## 6. レビュー観点（ユーザーに判断してほしいこと）

### 観点 A: 採用統合方式（案 A 主体 + ImplicitPathExtractor 補助）の承認

- `graph_store.upsert_nodes/upsert_relations` で spec-grag CLI が抽出結果を直接投入する責務を負う設計でよいか
- 案 B（CLI を `LLM` subclass でラップ）に切り戻す可能性を残すか、Phase 1 で完全に案 A に固定するか

### 観点 B: 5 つの確定設計含意（R1-R5）の承認

各ルールが spec-grag 仕様（DESIGN.ja.md §1.4 / §1.9）に正しく取り込まれているか確認:

- R1 (safe_delete_by_section) → §1.9 経路 1 注記、SURVEY/04 に記録済
- R2 (kg_extractors 必須) → §1.4 注記、SURVEY/01 に記録済
- R3 (毎回再構築) → §1.4 注記、SURVEY/01 に記録済
- R4 (Orchestrator 責務) → §1.4 注記
- R5 (Claude `--bare` 不使用) → SURVEY/12 に記録済（DESIGN.ja.md にはまだ反映していない、レビュー後に反映）

### 観点 C: vector_store 連結問題（高緊急）の対処方針

- 選択肢 1: Phase 1 で追加調査して spike を更新、検索精度を確保してから本実装に進む
- 選択肢 2: spec-grag MVP では graph_store 直接アクセス（`get` / `get_rel_map` / property filter）+ keyword 検索から始め、vector retrieval は段階的に追加する
- 選択肢 3: HybridRetriever 風の自前 fusion を spec-grag が実装し、graph + keyword + （後期） vector を統合

### 観点 D: Phase 1 への移行条件

Phase 0.5 完了条件 4 つ（TODO.md 参照）のうち：

1. spike 02/03/04 動作確認 ✓ 完了
2. SURVEY/ 各項目に反映 ✓ 完了
3. Phase 0 状態表の Spike 列が全項目 ✓ または — ✓ 完了
4. usable_with_wrapper / partially usable が `usable` または明確な不採用判定に確定 → **partially usable が 02 / 12 に残る、usable_with_wrapper が 04/05/10 に残る**

→ 4 番目は厳密には完全条件を満たしていない（02/12 partially / 04/05/10 wrapper）。これらが Phase 1 のレビュー対象になるか、それとも追加 spike が必要か、ユーザー判断が必要。

## 7. 関連ファイル

- 個別調査結果: [doc/SURVEY/01_*.md](.) 〜 [12_*.md](.)
- spike コード: [spike/00_*.py](../../spike/) 〜 [04_*.py](../../spike/)
- フェーズ管理: [doc/TODO.md](../TODO.md)
- 設計書: [doc/DESIGN.ja.md](../DESIGN.ja.md) §1.4 / §1.9
- 外部契約: [doc/EXTERNAL_DESIGN.ja.md](../EXTERNAL_DESIGN.ja.md)（不変）
