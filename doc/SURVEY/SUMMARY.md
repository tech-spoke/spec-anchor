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

## 3. 統合方式 — 3 案の中身と採用判断

DESIGN.ja.md §4.1 で立てた **案 A / 案 B / 案 C** は「LlamaIndex / Claude・Codex CLI / spec-grag CLI が抽出フローのどこで何を担うか」が違う 3 つの構成。各案の中身を以下に整理する。

### 3.1 案 A: 外部抽出 → 直接投入（spec-grag CLI が抽出責務を持つ）

**何が「外部」か**: LlamaIndex の SchemaLLMPathExtractor を経由せず、**spec-grag CLI が Claude/Codex CLI を直接 subprocess で呼んで JSON を取る**。LlamaIndex は graph store / retriever / traversal / embedding search の道具として使うだけ。

**データフロー**:

```
[章 markdown]
   ↓ spec-grag CLI が章ごとに切り出す
[spec-grag CLI: extraction]
   └→ subprocess: claude --output-format json --json-schema '{...}' < prompt
                  または codex exec --output-schema spec_grag_schema.json
   ↓
[Claude/Codex CLI が JSON を返す]
   {"entities": [{name, label, properties}, ...],
    "relations": [{label, source_id, target_id, properties}, ...]}
   ↓ spec-grag CLI: parse + Validator (schema 適合・section_id 採番・SHA-256)
[graph_store.upsert_nodes(...)]
[graph_store.upsert_relations(...)]
   ↓ spec-grag CLI: storage_context.persist
[LlamaIndex 側: PGRetriever / VectorContextRetriever / get_rel_map]
   ↓ spec-grag Orchestrator: fusion + 4 軸付与（NodeWithScore.metadata）
[InjectionContext / RealignResult]
```

**役割分担**:

| 担当 | やること |
|---|---|
| **spec-grag CLI** | 章切り出し / Claude・Codex subprocess 呼び出し / JSON parse / Validator / `upsert_nodes` / `upsert_relations` / safe_delete_by_section / Orchestrator |
| **Claude/Codex CLI**（subprocess）| structured output で entity/relation JSON を返す。LlamaIndex の `LLM` interface は経由しない |
| **LlamaIndex** | graph store（容器）/ retriever / traversal / embedding search の **道具として**使われる。判断契約は持たない |

**利点**:
- 責務分離が明瞭（LlamaIndex を道具に閉じ込める、判断は spec-grag）
- Claude/Codex CLI の `--json-schema` / `--output-schema` をそのまま活用、structured output のリトライ・検証を spec-grag が制御
- LlamaIndex の `LLM` subclass adapter（10+ method）を書かなくて良い

**欠点**:
- spec-grag CLI 側に抽出パイプライン（prompt 組み立て / 章切り出し / 並列実行 / エラーハンドリング）を実装する工数
- LlamaIndex 内蔵の SchemaLLMPathExtractor の prompt / schema 強制 / retry を活用しない（自前で書く）

---

### 3.2 案 B: LLM wrapper 方式（LlamaIndex の LLM interface に CLI を埋め込む）

**何が「wrapper」か**: spec-grag が **LlamaIndex の `LLM` クラスを継承した subclass adapter** を実装し、その内部で Claude/Codex CLI を subprocess で呼ぶ。LlamaIndex の SchemaLLMPathExtractor / from_documents はこの adapter を `Settings.llm` 経由で使う。

**データフロー**:

```
[章 markdown]
   ↓ spec-grag CLI: PropertyGraphIndex.from_documents(documents, ...)
[LlamaIndex: SchemaLLMPathExtractor]
   ↓ schema 強制 prompt を組み立て
[LlamaIndex の LLM interface: spec-grag が実装した CodexCLIAdapter]
   class CodexCLIAdapter(LLM):
       def complete(self, prompt: str, **kwargs) -> CompletionResponse:
           subprocess.run([codex, exec, --output-schema, schema, prompt], ...)
       def acomplete / chat / achat / stream_complete / metadata / ...
   ↓
[Claude/Codex CLI が JSON を返す]
   ↓ adapter: CompletionResponse 形式に変換
[LlamaIndex: SchemaLLMPathExtractor]
   ↓ pydantic validation（strict=True で Literal 型強制）
[graph_store に LlamaIndex が投入]
   ↓ ... 以降は案 A と同じ
```

**役割分担**:

| 担当 | やること |
|---|---|
| **spec-grag CLI** | `LLM` subclass adapter の実装 / Orchestrator（4 軸付与・fusion・InjectionContext）|
| **Claude/Codex CLI**（subprocess）| adapter の裏で呼ばれる |
| **LlamaIndex** | graph store + retriever + **加えて、SchemaLLMPathExtractor 内部の抽出オーケストレーション**（prompt / schema validation / retry / 並列実行） |

**利点**:
- LlamaIndex 内蔵の prompt / pydantic schema 強制 / retry を活用できる
- spec-grag CLI 側の抽出パイプラインが薄くなる
- 既存の LlamaIndex example / tutorial と互換性が高い

**欠点**:
- **`LLM` subclass adapter の実装工数が大きい**（LlamaIndex `LLM` interface は 10+ method、sync / async / streaming / structured output 全対応が要る）
- subprocess の挙動（timeout / 認証切れ / rate limit）を LlamaIndex の retry ロジックと整合させる必要
- pydantic ValidationError 時の挙動（リトライ / エラー伝播）が LlamaIndex 側に閉じ、制御が効きにくい
- spike 02 で確認したように `Settings.llm` 解決パスが多く、各 callsite で adapter を確実に差し込む配慮が要る

---

### 3.3 案 C: 混合（kg_extractors に複数 extractor を並べる）

**何が「混合」か**: `PropertyGraphIndex(kg_extractors=[ext1, ext2, ...])` のリストに **LLM 不要 extractor（`ImplicitPathExtractor`）** と **spec-grag が書いたカスタム extractor** を並べ、抽出フローを段階分割する。

**データフロー**:

```
[章 markdown]
   ↓ PropertyGraphIndex.from_documents(documents,
        kg_extractors=[ImplicitPathExtractor(), CustomPGExtractor()])
[LlamaIndex: kg_extractors orchestration（複数 extractor を順に / 並列で実行）]

   分岐 1: ImplicitPathExtractor（LLM 不要）
      ↓ node の relationship 属性から path を読む
      [graph_store に triplet を投入]

   分岐 2: CustomPGExtractor（spec-grag が TransformComponent を継承して実装）
      ↓ subprocess で Claude/Codex CLI を呼ぶ（案 A の中身を内側に持つ）
      [graph_store に entity/relation を投入]

   ↓ ... 以降は案 A と同じ
```

**役割分担**:

| 担当 | やること |
|---|---|
| **spec-grag CLI** | `CustomPGExtractor(TransformComponent)` の実装（内部は案 A 同様の subprocess 呼び出し）/ Orchestrator |
| **Claude/Codex CLI**（subprocess）| CustomPGExtractor の中で呼ばれる |
| **LlamaIndex** | graph store + retriever + **加えて kg_extractors の orchestration**（複数 extractor の順次/並列実行）。LlamaIndex 内蔵 SchemaLLMPathExtractor は使わない |

**利点**:
- LlamaIndex の kg_extractors の並列実行 / progress bar / 標準フロー を活用できる
- LLM 不要部分（document structure / 簡単な relation）は ImplicitPathExtractor に任せて高速化
- spec-grag MVP では `[ImplicitPathExtractor()]` だけを渡すミニマル形（空リスト回避策、R2）が **案 C の最小特殊形**

**欠点**:
- CustomPGExtractor を `TransformComponent` 継承で書く工数（案 A の subprocess 部分と同等 + extractor interface 適合）
- LlamaIndex の TransformComponent flow に従う必要（spec-grag 側からの細かい制御が下がる）

---

### 3.4 採用判断（spec-grag MVP）

**採用方針: 案 A 主体 + `ImplicitPathExtractor` 補助**（案 C の最小特殊形）

実証ベースの根拠:

| 観点 | 案 A | 案 B | 案 C |
|---|---|---|---|
| LLM 呼び出し位置 | spec-grag CLI が直接 | LlamaIndex 内部 | LlamaIndex 内部（CustomPGExtractor 内で spec-grag が呼ぶ）|
| spec-grag 主実装 | 抽出パイプライン + Validator | LLM subclass adapter（10+ method）| TransformComponent 継承 |
| LlamaIndex 内蔵プロンプト活用 | しない | する | しない |
| structured output 強制 | CLI `--json-schema` を直接使用 | LlamaIndex pydantic validation | extractor 側で実装 |
| spike 実証 | ✓ spike 01 で動作 | ☐ wrapper 未実装 | △ ImplicitPathExtractor のみ spike 02 |
| 責務境界の明瞭性 | **高**（LlamaIndex は道具）| 低（LlamaIndex が判断パスに入る）| 中 |
| 実装工数 | 中 | 大 | 中 |
| MVP 適合性 | **○** | △ | ○（最小特殊形 = 案 A + ImplicitPathExtractor のみ）|

採用方針:

- **抽出の本流 = 案 A**（spec-grag CLI が章ごとに Claude/Codex CLI を呼んで JSON を取り、`upsert_nodes` / `upsert_relations` で graph_store に直接投入）
- **`kg_extractors=[ImplicitPathExtractor()]`** は R2（空リスト回避）として渡す。これは案 C の最小特殊形にあたる
- **案 B は MVP では不採用**。Phase 3（実装着手後）で「LlamaIndex 内蔵 SchemaLLMPathExtractor の prompt / pydantic 強制を活用したい」となれば再評価する選択肢として残す

**ただし、案 A は LlamaIndex（GraphRAG エコシステム）の本体機能の大半を捨てる選択であり、その代償は §3.5 にすべて列挙する**。§3.6 では推奨者（Claude）の選好バイアスを開示する。**ユーザーが §3.5 / §3.6 を読んだ上で案 A を承認するかどうかが採用判断の本体**。

**この採用方針で動かすために確定した運用ルール（R1-R5）は §4 に記載**。

---

### 3.5 案 A が捨てる GRAG（LlamaIndex Property Graph）の機能

LlamaIndex Property Graph が標準で提供する機能のうち、案 A は以下をすべて捨てる。**spec-grag が自前実装する必要がある**。

| 機能カテゴリ | LlamaIndex 標準で提供されるもの | 案 A での扱い（spec-grag 自前実装が必要）|
|---|---|---|
| **schema 強制プロンプト設計** | `DEFAULT_SCHEMA_PATH_EXTRACT_PROMPT` + Literal 型 / List[Triple] から自動生成。LLM への prompt 工学を LlamaIndex に任せられる | spec-grag が日本語 prompt を自前で組み立てる（schema 表現・例示・instruction tuning すべて）|
| **pydantic strict validation（schema 外 triplet 拒否）** | `kg_schema_cls` + `create_model` + `Literal` 型で **schema 違反は ValidationError で即拒否**（spike 02 で確認の落とし穴メカニズム）| spec-grag が JSON parse 後に自前で validate。CLI 側 `--json-schema` / `--output-schema` に任せても、その厳密性は CLI 実装依存（LlamaIndex の pydantic ほど強くない可能性）|
| **schema 違反時の retry ロジック** | LlamaIndex 内蔵の retry（プロンプトを修正して再試行、最大回数制御）| spec-grag が retry ループを自前実装。「違反検出 → 修正 prompt → 再試行 → 失敗時のフォールバック」を独自設計 |
| **chunk 単位の抽出量制御** | `max_triplets_per_chunk` 引数で 1 chunk から抽出する triplet 上限を制御 | spec-grag が章 / セクション / chunk 境界を自前で判断、抽出量を独自にチューニング |
| **並列実行（concurrent batch）** | `num_workers` 引数で自動並列化。async pipeline で章単位 non-blocking 実行 | spec-grag が `asyncio.gather` + `asyncio.Semaphore` で subprocess 並列化を自前実装 |
| **`embed_kg_nodes=True` の自動 vector_store 投入** | `from_documents(embed_kg_nodes=True)` で entity の embedding を自動計算 + `vector_store` に add → vector retrieval が即動く | spec-grag が `EntityNode.embedding` 計算 + 別途 `TextNode` 構築 + `vector_store.add(...)` を自前で（spike 03 で必要性を確認、spike 03 では VECTOR_SOURCE_KEY 連結が動かず Phase 1 で追加調査）|
| **`insert(document)` incremental flow** | 1 メソッド呼び出しで chunk → 抽出 → 投入 → vector_store 連動が完結 | spec-grag が章切り出し + 変更検出 + safe_delete_by_section + 抽出 + Validator + upsert を自前パイプラインで |
| **kg_extractors の並列 merge** | 複数 extractor を `kg_extractors=[ext1, ext2, ...]` で並列実行し結果を merge（案 C が活用するもの）| spec-grag は単一抽出 + ImplicitPathExtractor のみ（複数 extractor の結果統合は使わない）|
| **`DEFAULT_VALIDATION_SCHEMA`（関係型妥当性チェック）** | `(subject_type, relation, object_type)` triple の整合（PERSON-BORN_IN-LOCATION のような）を pydantic レベルで自動検査 | spec-grag が Validator で同等のロジックを自前実装 |
| **`TransformComponent` 標準フロー** | chunk 化 / metadata 注入 / progress bar / async などの定型処理 | spec-grag が独自の章処理パイプラインを持つ |
| **LlamaIndex 内蔵プロンプト進化への追従** | LlamaIndex がプロンプト改善・モデル切替・新機能追加した場合に upgrade で恩恵を受ける | spec-grag 自前 prompt の改善は spec-grag 側で実装する責任。community のノウハウに乗らない |

**この決断が意味するもの**:

- LlamaIndex を **「Knowledge Graph 抽出ライブラリ」としては使わない**。graph store / retriever / traversal / embedding storage の **容器・道具**として閉じ込める
- spec-grag CLI 側に「日本語仕様書ドメインに特化した抽出パイプライン」を実装する工数と品質責任を全部抱える
- LlamaIndex の example / tutorial / community ノウハウから外れる（独自実装ゆえ参照できる先例が少ない）

**この決断が成立する前提**:

- spec-grag CLI が日本語仕様書ドメインに特化した prompt / Validator / retry を **自前で持つ価値がある**（汎用 prompt より高品質を実現できる）
- LlamaIndex の prompt 改善・extractor 進化に乗らないことを許容できる
- 工数として「自前抽出パイプライン」を Phase 3 実装で書ききれる

**前提が崩れる兆候**:

- 自前 prompt の品質が LlamaIndex 内蔵 SchemaLLMPathExtractor を下回る
- retry / 並列実行 / chunk 制御の自前実装が安定せず時間を取られる
- spec-grag CLI が「LLM 抽出ライブラリ」自体を抱える肥大化を起こす

→ そうなった場合は **案 B に切り戻す**（`LLM` subclass adapter を実装して LlamaIndex 内蔵機能を活用）。Phase 3 で再評価する選択肢として残す。

---

### 3.6 推奨者（Claude）の選好バイアス開示

ユーザーから指摘されたとおり、私（Claude）の推奨は **「推論カットできる（コードが見える）案を推奨する」傾向**が反映されている（memory `feedback_no_minimum_cost_escape.md` / `feedback_verify_before_recommend.md` 参照）。今回も同じ：

- 案 A は spec-grag CLI の挙動がコードレベルで全部見える → 私がレビューしやすい / 失敗箇所を特定しやすい
- 案 B は LlamaIndex 内部の retry / prompt / pydantic 動作が私から見えにくい → 「不透明」と感じる
- spike 01 で案 A の中核（upsert_nodes / 直接投入）が動作実証済 → 私の中で「確実に動く案」と評価が上がる

これらは **実装容易性 / レビュー容易性 / 失敗確率** の観点であって、**機能損失 / 自前実装の品質負担 / community ノウハウ活用** の観点ではない。

中立的な評価は次のとおり：

| 観点 | 案 A 有利 | 案 B 有利 |
|---|---|---|
| 実装容易性（spec-grag 視点）| ○（直接呼び出しのみ）| ×（adapter 10+ method 実装）|
| レビュー容易性（コードが見える）| ○（subprocess 呼び出し直視）| ×（LlamaIndex 内部に閉じる）|
| 失敗確率（spike 01 で実証済）| ○ | ×（adapter が未実装、subprocess 整合の不確実性）|
| **機能活用度（LlamaIndex 機能を活かす）** | × | **○**（schema 強制 / retry / 並列 / vector workflow）|
| **自前実装範囲の小ささ** | × | **○**（LlamaIndex に任せる）|
| **community ノウハウ活用** | × | **○**（example / tutorial に近い）|
| **ドメイン特化の柔軟性** | **○**（日本語 prompt 完全制御）| ×（LlamaIndex prompt に縛られる）|

→ 私が押した「案 A」は **左 3 行を強く重視した** 評価結果。**右 3 行（GraphRAG 機能活用 / 実装範囲縮小 / community ノウハウ）はユーザーが重視するなら案 B / C 寄りの判断もある**。

ユーザーは §3.5（案 A が捨てる機能の具体リスト）と §3.6（私のバイアス）を踏まえて、案 A / 案 B / 案 C のどれを採るかを最終判断する。Phase 1 への移行はその判断の後。

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
