# Phase 0 + Phase 0.5 完了レポート（ユーザーレビュー材料）

> 作成日: 2026-04-28（**2026-04-28 改訂: 案 A 破棄、Phase 1 入り口を方向 1 / 方向 2 の 2 択に変更**）
> commit: e020524（spike 04 完了時点）
> 本書の位置付け: Phase 1 開始前にユーザーレビューを受けるための実証結果サマリ。
> 個別の調査詳細は `doc/SURVEY/01_*.md` 〜 `12_*.md` を参照。

## ユーザー決定（2026-04-28）

**案 A は破棄**。理由は §3.5（案 A が捨てる GRAG 機能）/ §3.6（推奨者バイアス開示）/ §3.7（6 項目自己問答）/ §3.8（波及先発見品質の評価軸）に詳述。

> 「案 A は LlamaIndex を採用しているのに GRAG の中核（concept/entity/relation 抽出 + graph construction + grounding + retrieval fusion）を全部 spec-grag 自前実装している。それなら LlamaIndex を core dependency にする合理性が薄い。波及先発見が pivot の本来目的なのに、その判断軸が私の評価から落ちていた。」

Phase 1 入り口の選択肢は **§3.9 方向 1（GRAG をちゃんと使う）/ 方向 2（自前 canonical graph + optional adapter）の 2 択**。

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

### 3.1 案 A【破棄、2026-04-28】: 外部抽出 → 直接投入

> **状態**: ユーザー決定により **破棄**（2026-04-28）
> **本質**: 「GRAG 活用案」ではなく「**controlled graph-store adapter 案 / 自前 GRAG 構築案**」だった
> **破棄理由**: §3.5 / §3.6 / §3.7 / §3.8 を参照

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

### 3.4 採用判断（spec-grag MVP）— **撤回・案 A 破棄**

**2026-04-28 改訂前の方針（撤回）**: 「案 A 主体 + `ImplicitPathExtractor` 補助」

**2026-04-28 改訂後の方針**: **案 A 破棄、Phase 1 入り口で方向 1 / 方向 2 の 2 択を評価する**（§3.9 参照）。

#### 撤回理由（推奨者の自己認識）

私（Claude）は次の 5 つのバイアスで案 A を押した：

1. **サブスク CLI 前提が LlamaIndex の `LLM` interface と相性悪い → adapter 工数を避けた**（adapter の工数は spike せず想像で評価）
2. **「制御性」を理由に LlamaIndex 機能を丸ごと迂回した**（本来は「LlamaIndex 内部に判断契約を委譲しない」だけが原則だったのに、抽出機能まで使わない方向に拡大解釈）
3. **動いた spike を過大評価した**（spike 01 は案 A だけ書いて動かし、案 B / 案 C を spike しなかった→比較不公平）
4. **目的関数のすり替え**（pivot 本来目的「波及先発見のためのグラフ構築」が「壊れにくく説明しやすい subprocess 連携」に変質）
5. **機能損失をデメリットとして重く見ない**（§3.5 でリストを書いた後ですら「だから LlamaIndex 入れる意味あるか？」に結びつけなかった）

特に 4 が致命的。比較表の評価観点が「実装容易性 / レビュー容易性 / 失敗確率 / 機能活用度 / 自前範囲 / community / ドメイン特化」だけで、**「波及先発見品質が成立するか」が一切入っていなかった**。pivot 本来の目的を判断軸から落としていた。

#### 案 A の本質

案 A は GRAG の中核（concept/entity/relation 抽出 + graph construction + grounding + retrieval fusion）を spec-grag 自前で書く案。LlamaIndex は graph store / retriever traversal / vector store の **薄皮 adapter** としてしか使われない。

→ **LlamaIndex を core dependency にする合理性が薄い**。SQLite / NetworkX / FAISS + 自前 retriever でほぼ同じことができる。

→ **GRAG 活用案として承認しない**（ユーザー判断、2026-04-28）。

3 案の比較は §3.7（6 項目自己問答）/ §3.8（波及先発見品質の評価軸）/ §3.9（Phase 1 入り口の 2 択）に再構成する。

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

→ 私が押した「案 A」は **左 3 行を強く重視した** 評価結果。**右 3 行（GraphRAG 機能活用 / 実装範囲縮小 / community ノウハウ）と「波及先発見品質」（§3.8）はユーザー決定で重視され、結果として案 A は破棄された**。

---

### 3.7 案 A の自己問答（GPT 提示の 6 項目、事実列挙）

ユーザー決定（2026-04-28）に至る根拠として、以下 6 項目を事実列挙する。判断的な部分は方向 1 / 方向 2 の評価で詰める。

#### 1. 案 A で **使う** LlamaIndex 機能

- `SimplePropertyGraphStore` の `to_dict` / `from_dict` / `upsert_nodes` / `upsert_relations` / `delete` / `get_rel_map(depth=2)`
- `PropertyGraphIndex.from_existing` の薄いラッパ（`storage_context.persist`）
- `OllamaEmbedding` 注入（実体は ollama-python client、LlamaIndex なしでも呼べる）
- `kg_extractors=[ImplicitPathExtractor()]`（空リスト回避策、本来の用途では使わない）
- `PGRetriever` の単純結合 + dedup（fusion / rerank は spec-grag 側）

#### 2. 案 A で **使わない** LlamaIndex / GraphRAG 機能

§3.5 で列挙済（11 項目）。要点:

- `SchemaLLMPathExtractor` 内蔵プロンプト・pydantic strict・retry
- `kg_extractors` 並列 merge / orchestration
- `from_documents` の document → entity/relation 自動変換
- `embed_kg_nodes=True` の自動 vector_store 投入
- `insert(document)` incremental flow
- `DEFAULT_VALIDATION_SCHEMA` 関係型整合チェック
- `TransformComponent` 標準フロー（chunk / metadata / progress）
- LlamaIndex 内蔵プロンプト・extractor 進化への追従

#### 3. **使わない機能を spec-grag が自前実装する範囲**

以下すべて:

- Section 分割 / SourceSpan 管理 / Entity 抽出 / Relation 抽出 / Concept 候補抽出
- relation type 設計
- JSON schema validation（CLI `--json-schema` 任せでも、CLI 実装依存性が残る）
- 重複 entity 統合
- stale edge 削除（`safe_delete_by_section` wrapper）
- source grounding（source_span の付与・伝播）
- graph traversal policy（depth / relation filter）
- retrieval fusion（RRF / Weighted / cross-encoder rerank）
- vector_store 連結（VECTOR_SOURCE_KEY / TextNode metadata）
- 4 軸 transient annotation の付与・隔離
- 並列実行（asyncio.gather + Semaphore）
- prompt 工学（日本語 + Literal 型表現 + 例示 + retry prompt）
- 章単位 SHA-256 変更検出 / incremental update orchestration

#### 4. それでも LlamaIndex を core dependency にする合理性（事実のみ、判断保留）

- 借りているのは「JSON ベース graph store + 薄い traversal + 薄い retriever interface」
- これらは SQLite / NetworkX / FAISS で代替可能（§3.9 方向 2 参照）
- LlamaIndex 採用の唯一の固有利点は「将来 LlamaIndex Property Graph が改善した場合に取り込める可能性」
- ただし、案 A の使い方では SchemaLLMPathExtractor / kg_extractors / from_documents の改善には乗れない（使っていないので）
- → **判断**: Phase 1 で方向 1 / 方向 2 のいずれを取るかで合理性が決まる

#### 5. 自前 canonical graph + optional LlamaIndex adapter と比較した場合の差分

| 項目 | 案 A | 自前 canonical + adapter |
|---|---|---|
| graph store | LlamaIndex SimplePropertyGraphStore | SQLite / JSONL / NetworkX |
| 永続化 JSON 構造 | LlamaIndex 内部仕様（`{nodes, relations, triplets}`）| spec-grag 自前定義 |
| traversal | `get_rel_map(depth=2)` | NetworkX `bfs_edges` / 自前 BFS |
| vector store | LlamaIndex `SimpleVectorStore` + 連結問題 | FAISS / Chroma 直接 |
| retriever | `PGRetriever` の薄皮 | 自前統合（embedding + property + traversal） |
| spec-grag 自前範囲 | 上記 §3 と同じ（多い）| 同じ + graph store I/O のみ追加（差分は graph store I/O だけ） |
| 落とし穴 | `kg_extractors` falsy / `load_index_from_storage` LLM 解決 / `delete` cascade / VECTOR_SOURCE_KEY 連結 | これらは存在しない |
| LlamaIndex 進化への追従 | 上述のとおり SchemaLLMPathExtractor 系には乗れない | optional adapter 越しに後付けできる |

→ **判断**: 機能損失と落とし穴の数で見ると、案 A は「自前 canonical + adapter」より明確に劣位

#### 6. 案 C で LlamaIndex の `kg_extractors` flow に乗せる場合の追加工数と得られる機能

- **追加工数**:
  - `CustomPGExtractor(TransformComponent)` の実装（subprocess 呼び出しを TransformComponent interface に適合）
  - LlamaIndex の `Settings.llm` 解決を avoid する設計（spike 02 の落とし穴対策）
  - SchemaLLMPathExtractor を併用する場合は `LLM` subclass adapter（10+ method）も必要
- **得られる機能**:
  - kg_extractors の並列実行（`num_workers`）
  - LlamaIndex の chunk 化 / progress bar / metadata 注入
  - SchemaLLMPathExtractor を併用すれば prompt / pydantic / retry も活用可
  - `from_documents` flow に乗ることで future 改善の恩恵を受けやすい
- → **判断**: 工数は中、得られる機能は GRAG 中核に直結。Phase 1 で方向 1 として詳細評価する

---

### 3.8 波及先発見品質の評価軸（共通基準）

GRAG を採用する pivot 本来の目的は **「変更対象から波及先（dependent section / related concept / superseded item / conflict candidate）を辿れる」**こと。これを Phase 1 で各方向（方向 1 / 方向 2）の評価に使う共通基準として明示する。

| 領域 | 評価観点 | 案 A の場合（参考、破棄済）|
|---|---|---|
| 波及先の保存管理 | node / relation / section_id / source_span / source_hash を正しく保存できるか | ○ spike 01 で実証 |
| 明示 edge の探索 | `DEPENDS_ON` / `CONSTRAINS` / `REFINES` / `SUPERSEDES` / `CONFLICTS_WITH` を辿れるか | ○ `get_rel_map` で動作 |
| stale edge 除去 | 変更章削除で対岸 entity を巻き込まないか | △ `safe_delete_by_section` wrapper 必須 |
| 暗黙的な波及先発見 | 明示 edge にないが意味的に関連する章を vector / keyword で拾えるか | △〜× vector_store 連結が未解決、案 A は明示 edge 依存 |
| GRAG ライブラリの構築支援 | LlamaIndex の SchemaLLMPathExtractor / kg_extractors orchestration を活用できるか | × 案 A は活用しない |

→ Phase 1 で方向 1 / 方向 2 をこの軸で **対称的に評価**する。

---

### 3.9 Phase 1 入り口の 2 択（方向 1 / 方向 2）

案 A 破棄に伴い、Phase 1 入り口の選択肢は以下 2 つ。**私（Claude）は片方を推さない**。ユーザーが §3.5 / §3.6 / §3.7 / §3.8 を踏まえて判断する。

#### 方向 1: GRAG をちゃんと使う

LlamaIndex Property Graph を **抽出パイプラインも含めて活用**する方向。

```
- PropertyGraphIndex.from_documents flow に乗る
- kg_extractors = [SchemaLLMPathExtractor + ImplicitPathExtractor + CustomPGExtractor]
- LLM 接続: CodexCLIAdapter(LLM) を実装（案 B の wrapper、または HTTP 経由 LLM provider）
- TextNode / metadata / source grounding を LlamaIndex 標準流に近づける
- vector_store 連結を LlamaIndex 慣習で解決（spike 03 の 0 件問題は連結ロジックの正しい実装で解決可能）
- spec-grag 責務: Concept 承認・未承認遮断・safe delete・4 軸付与・InjectionContext / RealignResult 構造化
```

**Phase 1 で詰める**:
- adapter 実装方針（CLI subprocess wrapper の最小 method 一覧）
- SchemaLLMPathExtractor のプロンプト日本語化と Literal 型 schema 定義
- vector_store 連結の正規パターン（追加 spike）

#### 方向 2: 制御性最優先（自前 canonical graph + optional LlamaIndex adapter）

**canonical graph を spec-grag 自前管理**にして、LlamaIndex は optional adapter として位置付ける。

```
- canonical graph: spec-grag 自前（SQLite / JSONL / NetworkX 等を Phase 1 で評価）
- entity / relation / source_span のスキーマ・I/O は spec-grag が完全制御
- vector store: FAISS / Chroma / SQLite-vec（直接利用）
- LlamaIndex: optional な「adapter ファサード」として残す（互換性が必要になったら使う）
- LightRAG / HippoRAG: optional な波及先 retriever として将来評価
- 抽出: Claude/Codex CLI subprocess（案 A の subprocess 部分は流用）
```

**Phase 1 で詰める**:
- 自前 graph store の永続化形式と粒度（SQLite vs JSONL vs NetworkX in-memory + JSON dump）
- 自前 retriever の fusion 設計（embedding + property + traversal）
- LlamaIndex を optional adapter にする境界 API の設計

#### 共通評価基準（§3.8 を使う）

両方向を §3.8 の 5 観点（保存管理 / 明示 edge 探索 / stale edge 除去 / 暗黙的波及先発見 / GRAG 構築支援）で対称的に評価する。Phase 1 の出口で方向 1 / 方向 2 のどちらを採るかを確定する。

---

## 4. spec-grag への確定設計含意（方向によって適用範囲が変わる）

> **注記（2026-04-28、案 A 破棄に伴う）**: 以下の R1-R5 は案 A 採用時の運用ルールとして整理されたもの。**方向 1 / 方向 2 のどちらを採るかで適用範囲が変わる**:
>
> - R1 / R2 / R3: **方向 1 採用時のみ該当**（LlamaIndex `SimplePropertyGraphStore` / `PropertyGraphIndex` を使う前提）。方向 2 では graph store / index を自前管理するため、これらの落とし穴自体が存在しない
> - R4: **方向 1 / 方向 2 共通**（spec-grag Orchestrator が判断契約を持つ原則は両方向で維持される）
> - R5: **方向 1 / 方向 2 共通**（Claude/Codex CLI subprocess の運用ルールは両方向で維持される）

Phase 0 で実証された **動かすために必要な運用ルール 5 項目**（参考）：

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

## 5. Phase 1 / 実装時に詰める残課題（方向 1 / 方向 2 で適用が変わる）

| 項目 | 残課題 | 方向 1（GRAG 活用）| 方向 2（自前 canonical + adapter）|
|---|---|---|---|
| vector retrieval | embedding + entity の正規連結で類似検索を動かす | LlamaIndex `VECTOR_SOURCE_KEY` 連結を正規パターンで実装（spike 03 の 0 件問題を解消）| FAISS / Chroma / SQLite-vec を直接利用、自前 fusion 設計 |
| LLM 抽出統合 | Claude/Codex CLI と pipeline の接続 | `LLM` subclass adapter（CodexCLIAdapter）の最小 method 実装、SchemaLLMPathExtractor 日本語化 | subprocess 直接呼び出し（案 A の抽出部分を流用）+ 自前 retry / Validator |
| 12 Claude/Codex CLI 実認証下動作 | 出力揺れ / rate limit / 認証切れの挙動 | 共通課題（中緊急、spec-grag CLI の error handling 設計に必要）| 共通課題 |
| 02-2c strict 違反挙動 | LlamaIndex 内蔵 retry / pydantic ValidationError のフォールバック | 必要（SchemaLLMPathExtractor 採用時）| 不要（自前 Validator のみ）|
| 01 LlamaIndex breaking change | llama-index-core v0.14 系の release 追跡 | 必要（core dependency）| 低（adapter で隔離）|

## 6. レビュー観点（ユーザーに判断してほしいこと）

### 観点 A: 統合方式の決定 — **済（2026-04-28、案 A 破棄）**

ユーザー決定により案 A は破棄。Phase 1 入り口の選択肢は **方向 1 / 方向 2 の 2 択**（§3.9）。

### 観点 B: 方向 1 / 方向 2 のどちらに進むか — **未決**

§3.5 / §3.6 / §3.7 / §3.8 を踏まえて、Phase 1 で以下のどちらに進むかを確定する：

- **方向 1: GRAG をちゃんと使う** — LlamaIndex Property Graph の抽出 pipeline ・SchemaLLMPathExtractor の prompt / pydantic / retry を活用する方向
- **方向 2: 制御性最優先** — canonical graph を spec-grag 自前管理にし、LlamaIndex を optional adapter に格下げ

判断軸は §3.8（波及先発見品質の 5 観点）+ §3.7-5（自前 canonical との差分）+ §3.7-6（案 C 追加工数）。

### 観点 C: 確定設計含意（R1-R5）の方向別適用 — 方向確定後

- 方向 1 採用なら R1 / R2 / R3 / R4 / R5 すべて適用、DESIGN.ja.md §1.4 / §1.9 に正式反映
- 方向 2 採用なら R1 / R2 / R3 は不要（自前 graph store には別ルールが要る）、R4 / R5 のみ適用、DESIGN.ja.md §1.4 を「Python + 自前 canonical graph + optional LlamaIndex adapter」に書き換え

### 観点 D: Phase 1 への移行条件 — 一部条件未達だが移行可

Phase 0.5 完了条件 4 つ（TODO.md 参照）のうち：

1. spike 02/03/04 動作確認 ✓ 完了
2. SURVEY/ 各項目に反映 ✓ 完了
3. Phase 0 状態表の Spike 列が全項目 ✓ または — ✓ 完了
4. usable_with_wrapper / partially usable が `usable` または明確な不採用判定に確定 → **案 A 破棄により、これらの判定は方向 1 / 方向 2 で再評価が必要**

→ Phase 1 では §3.9 の方向 1 / 方向 2 をまず比較評価し、確定後に §1.1〜§1.9 仮分担マトリクスを再評価する流れに変更。

## 7. 関連ファイル

- 個別調査結果: [doc/SURVEY/01_*.md](.) 〜 [12_*.md](.)
- spike コード: [spike/00_*.py](../../spike/) 〜 [04_*.py](../../spike/)
- フェーズ管理: [doc/TODO.md](../TODO.md)
- 設計書: [doc/DESIGN.ja.md](../DESIGN.ja.md) §1.4 / §1.9
- 外部契約: [doc/EXTERNAL_DESIGN.ja.md](../EXTERNAL_DESIGN.ja.md)（不変）
