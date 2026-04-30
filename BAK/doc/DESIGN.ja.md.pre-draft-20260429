# SPEC-grag 詳細設計書

本書は SPEC-grag の **現時点での方針** を記録する。外部契約は [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md)（source of truth、不変）で定義され、本書はその実装側の方針を扱う。

> **警告**: 本書のうち以下はすべて [§4.1 表面マップ調査](#41-llamaindex-系の表面マップ調査) 完了前の **仮**である：
>
> - §1.1〜§1.3, §1.5〜§1.9（責務境界・整合性チェック・4 軸評価・Read 制限・部品契約・内部フロー）→ **§4.1 調査前の仮分担**。調査結果次第で再分配する
> - §1.4「採用候補スタック」と §2 スキーマの運用詳細 → **暫定方針**
>
> 「最終方針」「採用」「確定」と読み替えない。`§1.4 採用方針（決定済）`（Python + LlamaIndex 系エコシステム）のみ pivot で確定済。
>
> 設計手順とフェーズ進行は [doc/TODO.md](TODO.md) を参照（**調査 → 仮分担 → レビュー → 設計書反映**）。本書の編集ルールは [CLAUDE.md](../CLAUDE.md) の不変ルール 1〜8 に従う。

---

## 1. アーキテクチャ

### 1.1 責務の仮分担マトリクス（§4.1 調査前の仮）

> **仮分担**: §4.1 LlamaIndex 表面マップ調査が完了するまで、本マトリクスは仮の役割分担である。調査結果次第で再分配される（[doc/TODO.md](TODO.md) Phase 1 で再評価）。

SPEC-grag は判断契約を **GRAG / GraphRAG ライブラリに委譲しない**。GRAG は構造化された候補生成・検索基盤であり、最終判断は CLI / Orchestrator / LLM（用途別）/ Human が分担する（仮）。

| 領域 | 持ち主 | やること |
|---|---|---|
| Purpose 確定 | **Human** | 書く・確定する。LLM は更新しない |
| Concept 承認 | **Human** | accept / reject / 修正指示。LLM は自動承認しない |
| Concept diff 提示 | LLM (Extraction) | 更新候補を生成。最終確定はしない |
| Custom schema 承認 | **Human** | ドメイン語彙の採否を決める |
| 変更検出 | **CLI** | hash / section 差分（決定的、LLM 不要）|
| Document / Section 構造 | **CLI / Parser** | Markdown AST から決定的に取得（LLM 不要）|
| ChapterAnchor の文書構造部分 | **CLI / Parser** | document_id / section_id / heading_path / source_hash / source_span |
| ChapterAnchor の意味要素部分 | LLM (Extraction) | summary / key_concepts / candidate_constraints / mentions |
| Entity / Relation 抽出 | LLM (Extraction) | 意味要素候補・relation 候補を生成 |
| Graph store / 検索 / 探索 | **GRAG subsystem** | 保存・検索・探索。判断はしない |
| 標準スキーマ | **spec-grag Core** | 汎用語彙のみ |
| Custom schema | **Project** | ドメイン固有語彙（spec-grag 本体には含めない）|
| 4 軸評価の付与 | LLM (Classification) + **Orchestrator** | §1.7 の 4 軸（constraint_relevance / target_relevance / conflict / review_required）を候補に付与 |
| 未承認 Concept 遮断 | **Orchestrator** | 絶対に通さない（InjectionContext / Answer 生成を停止）|
| Conflict 候補 → 確定の昇格 | Validator + **Human** | LLM 単独では `conflict=true` 不可（§1.5）|
| InjectionContext 構築 | **Orchestrator** | 構造化出力（自由生成しない）|
| Answer 生成 | LLM (Answer) | InjectionContext / RealignResult に拘束された回答 |

LLM は **用途別に分離**して扱う（同一 LLM インスタンスでも、プロンプトと役割で分離する）：

- **Extraction LLM**: Section から意味要素・relation 候補を抽出、ChapterAnchor の summary / key_concepts を生成、Concept 更新候補を生成
- **Classification LLM**: GRAG 検索結果に対して 4 軸評価を付与、`semantic_conflict_candidate` / `review_required` を出す（必ず Validator の deterministic 検査を経る）
- **Answer LLM**: InjectionContext を前提に回答生成、ConstraintContext を守る、ConflictNotes / ReviewNotes を隠さない

### 1.2 GRAG / GraphRAG ライブラリがしてはいけないこと

- Purpose を更新する
- Concept diff を自動承認する
- 課題に対して何を最終制約にするかを確定する
- 何を修正対象にするかを最終確定する
- 未承認 Concept を勝手に検索対象に混ぜる
- Answer を生成する
- ドメイン固有語彙を標準スキーマに固定する
- `conflict=true` を単独で確定する

GRAG / GraphRAG ライブラリ（LlamaIndex / Neo4j / Microsoft GraphRAG 等）は **GRAG subsystem の内部実装候補**に過ぎず、SPEC-grag の判断契約を代替しない。

### 1.3 三層分業（実装パッケージ）

```text
┌────────────────────────────────────────────────────────┐
│  Agent (Claude / Codex CLI) — slash command 実行層     │
│  - ConversationContext + 課題プロンプト解釈            │
│  - Agentic search（検索クエリ生成のためのキーワード抽出)│
│  - InjectionContext / RealignResult を読み Answer 生成 │
│  - raw source spec の Read は §1.7 で制限される        │
└──────────────────┬─────────────────────────────────────┘
                   │ Bash 呼び出し（CLI 引数で動的キーワード渡し）
                   ↓
┌────────────────────────────────────────────────────────┐
│  spec-grag CLI / Orchestrator（Python）                 │
│  - .spec-grag/config.toml + schema.toml 読み込み       │
│  - 変更検出（決定的）                                  │
│  - GRAG Builder / Retriever / Validator 呼び出し制御   │
│  - 未承認 Concept 遮断                                 │
│  - 2 系統 pipeline（制約探索 / 修正対象探索）           │
│  - 4 軸評価のオーケストレーション                       │
│  - InjectionContext / RealignResult 構築・出力         │
└──────────────────┬─────────────────────────────────────┘
                   │ Python API（暫定、§4.1 で確認）
                   ↓
┌────────────────────────────────────────────────────────┐
│  GRAG subsystem (内部実装候補：LlamaIndex 系、§1.4 暫定)│
│  - Builder / Store / Retriever / Traversal             │
│  - 全部品 candidate_only（§1.8 部品契約）              │
│  → 候補を返すのみ。判断はしない                         │
└────────────────────────────────────────────────────────┘
```

### 1.4 採用方針と候補スタック

**採用方針（決定済、pivot 後 commit b45d95f, 2026-04-27）**:

- 言語: **Python**
- GRAG エンジンのエコシステム: **LlamaIndex 系**
- graph store: ローカル・ファイルベース（プロジェクトごとの `.spec-grag/graph/`、Neo4j 等のサーバ常駐型は default 採用しない）
- **生成系 LLM**（用途別 3 種: Extraction / Classification / Answer）: **Claude CLI / Codex CLI**
  - **サブスク認証前提**（Claude Pro/Max / ChatGPT Plus/Pro 等の subscription-authenticated CLI agent）。**API key 前提にしない**
  - subprocess 呼び出しで **JSON 入出力契約**を取る **external reasoning/extraction worker** として扱う
  - LlamaIndex の `LLM` interface に直接組み込むことは **Phase 0 では前提にしない**（統合方式は §4.1 で調査して Phase 1 で確定。案 A / B / C は §4.1 参照）
- **ベクトル化 model（embedding）**: **Ollama nomic-embed-text**（ローカル embedding model、生成 LLM ではない、`ollama serve` で常駐）
  - 「Ollama」は当面 embedding 用ホストとして採用。generative LLM ホストとしては default では採用しない（生成系は Claude/Codex CLI に集約）
  - spike 段階で Ollama generative LLM を SchemaLLMPathExtractor 等の **一時** LLM として使う場合は spike 限定の代替として明記する

**採用候補スタック（暫定、§4.1 表面マップ調査で確定）**:

```text
GRAG index      : LlamaIndex PropertyGraphIndex（候補）
graph store     : SimplePropertyGraphStore（候補）
extractor       : SchemaLLMPathExtractor（候補、ノード型・関係型を制約）
storage path    : .spec-grag/graph/
optional 拡張   : Neo4jPropertyGraphStore adapter（将来追加可、現在は不要）
```

**未確認**: 上記候補の API 詳細・組み合わせ動作・version 安定度・永続化粒度・incremental update 方式は §4.1 で表面マップ調査が必要。「LlamaIndex 系で行く」という採用方針自体は確定。

**Phase 0 暫定結果（2026-04-28、llama-index-core==0.14.21）**:

- ✅ 採用候補スタックは API レベルで成立（doc/SURVEY/ 参照）
- ⚠️ **`SimplePropertyGraphStore.delete()` は使えない**（spec-grag の章単位 incremental では破綻、cascade で対岸 entity を消す）。spec-grag 側で **safe_delete_by_section** wrapper を実装する責務がある（§1.9 経路 1 / doc/SURVEY/04 参照）
- ⚠️ **PGRetriever の rank fusion は単純結合 + dedup のみ**（RRF / Weighted は LlamaIndex 標準にない）。spec-grag Orchestrator 側で fusion / rerank / 4 軸付与を実装する
- ⚠️ **`PropertyGraphIndex` 構築の落とし穴 2 つ**（spike 02 で実証、doc/SURVEY/01 参照）:
  - `kg_extractors=[]` は falsy 判定で **default の `SimpleLLMPathExtractor` が呼ばれて LLM 解決**が走る → **spec-grag は `kg_extractors=[ImplicitPathExtractor()]` を必須引数として渡す**（案 A の運用前提）
  - `load_index_from_storage(storage_ctx)` は内部で `Settings.llm` を解決するため使えない → **spec-grag は graph_store を `from_persist_dir` で単独 reload し、毎セッションで `PropertyGraphIndex.from_existing(...)` を再構築する**（PropertyGraphIndex は薄いラッパで永続化対象ではない）

**【2026-04-28 改訂】案 A 破棄、Phase 1 入り口は案 B 第一選択 + fallback ladder**:

- ユーザー決定により **案 A は破棄**（doc/SURVEY/SUMMARY.md §3.4 / §3.5 / §3.6 / §3.9 参照）
- 理由: 案 A は GRAG の中核（concept/entity/relation 抽出 + graph construction + grounding + retrieval fusion）を spec-grag 自前で書く案であり、LlamaIndex を core dependency にする合理性が薄い。pivot 本来目的「波及先発見のためのグラフ構築」が Claude の判断軸から落ちていた
- **Phase 1 入り口の優先順序（pivot 決定を尊重した fallback ladder、SURVEY/SUMMARY.md §3.9 参照）**:
  1. **案 B（第一選択）**: GRAG 本来の使い方。SchemaLLMPathExtractor / kg_extractors / PropertyGraphIndex の標準フローに乗り、Extractor で使う LLM backend を `CodexCLIAdapter(LLM)` 経由で Claude/Codex CLI subprocess に差し替えるだけ。本 §1.4「Python + LlamaIndex 系エコシステム採用」を維持
  2. **案 C（fallback 1）**: 案 B が spike で成立しないと実証された場合のみ。`kg_extractors` に CustomPGExtractor を入れて spec-grag 側に抽出を寄せる
  3. **GRAG 撤回（最終手段）**: 案 B / 案 C 両方が成立しなかった場合のみ。pivot 撤回し、本 §1.4 を「Python + 自前 canonical graph」に書き換え
- 上記の落とし穴対応（`safe_delete_by_section` / `kg_extractors=[ImplicitPathExtractor()]` / `load_index_from_storage` 不使用）は **案 B / 案 C 採用時に適用**。GRAG 撤回まで降りた場合のみ撤回
- PGRetriever fusion / 4 軸付与を Orchestrator 側でやる原則、Claude `--bare` 不使用は全段階共通
- Phase 1 ステップ 0 = 案 B の spike 05 (CodexCLIAdapter) / spike 06 (日本語 schema prompt) / spike 07 (vector_store 連結正規化) を実証してから §1.1〜§1.9 / §2 / §3 / §4 を再記述する

各部品の **候補契約**は §1.8 で定義（candidate_only）。

### 1.5 整合性チェック方針（3 段階パイプライン + Conflict 二段階）

LLM 抽出を完全信用しない。EXTERNAL_DESIGN.ja.md §5.4 ConflictNotes（制約 vs 修正対象 / Source spec 同士 / Concept vs Source spec）の検出は 3 段階で行う：

1. **グラフ構造ベース**（決定論的、優先）
   - `CONFLICTS_WITH` エッジが既に存在する
   - 同一概念に対し異なる Definition が存在する
   - `SUPERSEDES` チェーンに循環がある
   - 同一 ID への異なる属性が並存する
2. **ルールベース**（決定論的、補助）
   - Purpose の制約条項と Source spec の対立量化詞（「必ず」⇔「任意」、「全て」⇔「一部」）
   - sources_scanned_through より新しい修正と古い章の食い違い
   - Required と Optional の同時指定
3. **LLM 推論**（補助、最後）
   - 上記 1, 2 で疑わしい候補のみ LLM (Classification) で意味的妥当性確認
   - LLM 単独では `conflict=true` を発火させない、必ず構造的根拠とセット

**Conflict の確定権限（二段階）**:

| 状態 | LLM 単独で出してよいか | 説明 |
|---|---|---|
| `review_required = true` | ✅ 可 | 怪しい・確認が必要 |
| `semantic_conflict_candidate = true` | ✅ 可 | 意味的に衝突の疑い |
| `conflict = true` | ❌ 不可 | 構造的根拠（段階 1 or 2）または Human approval を必須とする |

LLM (Classification) は **候補**を出してよいが、**確定**は Validator または Human approval を経る。

### 1.6 4 軸評価（5 分類ではなく軸評価、transient annotation）

EXTERNAL_DESIGN.ja.md §5.4 で「同じ Concept / Source spec が制約側と修正対象側の両方に現れる場合もある」と定義されているとおり、課題に対する評価は**排他的 5 分類ではなく、4 軸の独立評価**として実装する。

**4 軸は課題依存の transient annotation**。同一概念が課題ごとに違う評価を持つため、graph store の **恒久プロパティとしては保持しない**。retrieval result / InjectionContext / RealignResult 上にのみ保持する。

| 種別 | 例 | 保持先 |
|---|---|---|
| 恒久プロパティ | document_id / section_id / heading_path / source_span / source_hash / concept_id / approval_status / evidence / created_at / updated_at | graph store |
| transient annotation | constraint_relevance / target_relevance / semantic_conflict_candidate / review_required / ranking_score | retrieval result / InjectionContext / RealignResult |

**4 軸評価（transient）**:

```text
constraint_relevance: none | low | medium | high
target_relevance:     none | low | medium | high
conflict:             true | false  ← LLM 単独では false まで（候補は §1.5 参照）
review_required:      true | false
```

**派生状態**:

```text
irrelevant = (constraint_relevance == none)
          && (target_relevance == none)
          && (conflict == false)
          && (review_required == false)
```

`irrelevant` は一次分類ではなく、4 軸すべてが無関係な場合の **派生状態**。

**InjectionContext のフィールド対応**（EXTERNAL_DESIGN §5.4 の構造に従う）:

| 4 軸の状態 | InjectionContext の所属フィールド |
|---|---|
| `constraint_relevance ≠ none` | `constraint_context.{purpose,concept,source_spec,chapter_anchor}_constraints` |
| `target_relevance ≠ none` | `target_context.{candidate_targets,related_concepts,related_source_sections,related_chapter_anchors,related_entities}` |
| `conflict == true` | `conflict_notes` |
| `review_required == true` | `review_notes` |
| すべて none/false（派生 irrelevant） | `excluded_as_irrelevant` |

同一項目が複数フィールドに同時所属しうる（例：Constraint としても Target としても関連、かつ Conflict 候補で review 必要）。

### 1.7 Agent の Read tool 使用制限

Agent (Claude / Codex CLI) は spec-grag CLI の外側で動く実行制御層であり、raw source spec の直接読み取りは **用途を限定**する。これは Orchestrator の **未承認 Concept 遮断**を Agent が迂回しないための制約。

**許可される Agent の Read**:

- Agentic search の事前調査（GRAG 検索クエリ生成のためのキーワード・エンティティ抽出）
- evidence inspection（debug / 人間レビュー用、Answer の根拠としては InjectionContext を経由する）
- 章ファイルの軽量サンプリング（章数の確認等）

**禁止される Agent の Read**:

- Answer 生成時に raw source spec を **直接 Answer の根拠として組み込む**
- InjectionContext を経由せず source spec の内容を Answer に引用する
- 未承認 Concept を含む章ファイルを Answer の根拠として使う
- ConstraintContext / TargetContext / ConflictNotes / ReviewNotes に **存在しない情報**を Answer 制約として持ち込む

Answer 生成時の制約・修正対象・競合候補は **InjectionContext / RealignResult 経由のみ**使用する。raw source の Read は補助的な確認手段に限定する。

### 1.8 LlamaIndex 部品契約（採用候補、candidate_only）

§1.4 採用候補スタックの各部品はすべて **candidate_only** として扱う。承認状態、制約確定、Concept 更新、Conflict 確定の権限は持たせない。

| 部品 | role | authority | 許可される用途 | 禁止される用途 |
|---|---|---|---|---|
| `PropertyGraphIndex` | graph_index_builder_and_query_surface | candidate_store_only | graph_build / retrieval / relation_candidate_storage | concept_approval / conflict_resolution / answer_generation / 制約確定 |
| `SchemaLLMPathExtractor` | schema_constrained_path_candidate_extraction | candidate_only | entity_candidate_extraction / relation_candidate_extraction | concept 承認 / 最終 relation 決定 / Purpose 更新 / Conflict 確定 |
| `SimplePropertyGraphStore` | local_graph_persistence_candidate | storage_only | local_persist / local_reload / prototype_storage | source_of_truth_for_approval / Concept レジストリ代替 |
| `Retriever` | evidence_backed_candidate_retrieval | retrieval_only | candidate_search / evidence_collection / source_span_lookup | final_classification / Orchestrator なしの answer_generation |

未定義の extractor / store は **unavailable** として扱う。採用候補の追加は §4.1 の表面マップ調査結果に基づいてのみ行う。

### 1.9 内部処理フロー（責務分担、3 コマンド × 4 経路）

3 コマンドの内部処理を、§1.1 の責務境界と §1.5〜§1.8 の制約に従って実行する。`/spec-core` は incremental / --all の 2 経路、計 4 経路すべてが一気通貫で動作する必要がある。

```text
経路 1: /spec-core incremental（変更分のみ）
  1. CLI: .spec-grag/config.toml 読み込み
  2. CLI: Source specs の変更検出（hash / section 差分、決定的）
  3. CLI: 変更 Section 特定
  4. CLI → GRAG Builder: 変更 Section の ChapterAnchor / Entity / Relation / Cluster を更新依頼
  5. ChapterAnchor 生成（共同責務、変更 Section のみ）
     - CLI / Parser: 文書構造（document_id, section_id, heading_path,
                                   source_hash, source_span）を決定的に生成
     - LLM (Extraction): 意味要素（summary, key_concepts,
                                       candidate_constraints, mentions）を抽出
     - GRAG Builder: schema validation + stale node/edge 除去 + 新 node/edge 追加
       (※ stale 除去は safe_delete_by_section wrapper 経由、後述)
  6. LLM (Extraction) + GRAG: 影響を受ける Concept の更新候補を生成
  7. CLI: Concept diff を Human に提示
  8. Human: accept / reject / 修正指示
  9. CLI: 未承認の場合は Concept を更新せず停止

  ※ Step 5 の stale 除去: LlamaIndex `SimplePropertyGraphStore.delete()` は
     triplet の subject/object 両方を巻き込んで削除する仕様（章をまたぐ
     relation で対岸の章の entity が消える）。spec-grag は **safe_delete_by_section**
     wrapper を持ち、graph.model_dump() → section_id で node/relation/triplet
     をフィルタ → from_dict() で再構築するパターンで stale 除去する。
     詳細は doc/SURVEY/04_incremental_update.md 参照（spike 01 で実証済）。

  **【2026-04-28 改訂】**: 上記 stale 除去の wrapper は **方向 1（LlamaIndex
  採用）時のみ適用**。方向 2（自前 canonical graph）採用時は stale 除去ロジック
  自体を spec-grag 自前で再設計する（Phase 1 で詰める）。

経路 2: /spec-core --all（全再構築）
  1. CLI: .spec-grag/config.toml 読み込み
  2. CLI: 既存 graph store / chapter_index / concept_index を破棄
         （または別パスへバックアップ）
  3. CLI: sources.include の全 Section を対象として再生成
  4. CLI → GRAG Builder: 全 Section の ChapterAnchor / Entity / Relation / Cluster を生成
  5. ChapterAnchor 生成（共同責務、全 Section）
     - 経路 1 の Step 5 と同じ（CLI/Parser + LLM Extraction + GRAG Builder の協働）
  6. LLM (Extraction) + GRAG: 全 Concept の再生成候補を作成
  7. CLI: Concept diff を Human に提示（全章再生成での diff）
  8. Human: accept / reject / 修正指示
  9. CLI: 未承認の場合は Concept を更新せず停止

経路 3: /spec-inject
  1. CLI: 経路 1（/spec-core incremental）を内部実行
  2. Orchestrator: Concept diff が未承認なら停止
                   （InjectionContext を生成しない）
  3. CLI: ConversationContext + 課題プロンプト取得
  4. Orchestrator: Purpose を必ず ConstraintContext 候補に追加（自動）
  5. CLI → GRAG Retriever: 関連候補（node, relation, source span,
                                       evidence, confidence, score）を取得
  6. LLM (Classification) + Orchestrator: 4 軸評価を付与（transient annotation）
     - constraint_relevance / target_relevance / conflict / review_required
     - LLM が出すのは候補（review_required, semantic_conflict_candidate）まで
  7. Validator: schema / source / concept approval / Conflict 昇格を deterministic に検査
  8. Orchestrator: InjectionContext を構造化出力（§1.6 のフィールド対応に従う）

経路 4: /spec-realign
  1. 経路 3（/spec-inject 相当）で InjectionContext を作成
  2. LLM (Answer): InjectionContext / RealignResult に拘束された回答を生成
     - 守る制約（ConstraintContext）
     - 修正候補（TargetContext）
     - 競合 / 不確実性 / 人間レビュー（ConflictNotes / ReviewNotes）
     - 課題への回答または修正案
     - raw source spec を直接根拠に使わない（§1.7）
  3. Orchestrator: RealignResult を構造化出力
```

**経路間の依存関係（一気通貫の前提）**:

- 経路 3 / 4 は経路 1（incremental）を内部で呼ぶ → Concept diff 未承認時は停止する
- 経路 2（--all）は単独実行のみ。経路 3 / 4 から呼ばれない
- 4 経路すべてが Phase 1 のレビュー基準（§4.1 → Phase 1 で再評価）

ChapterAnchor は **retrieval artifact** であり、判断主体ではない。`/spec-core`（経路 1 / 2 両方）で生成・更新するが、「課題に対して制約か修正対象か」は確定しない。その評価は `/spec-inject` または `/spec-realign` で課題に応じて 4 軸評価（transient annotation）を付与する。

---

## 2. スキーマ

### 2.1 Core Schema（spec-grag 標準、ドメイン非依存、増やさない）

```toml
[schema.core.entities]
document_structure = [
  "Document",
  "Section",
  "SourceSpan",     # 行範囲（[26:1263-1289] 等）の根拠粒度
]
semantic = [
  "Concept",
  "Requirement",
  "Constraint",
  "Decision",
  "OpenQuestion",
  "Conflict",
  "Rationale",      # 独立ノード型、複数 Decision で共有可
  "Alternative",    # 独立ノード型、ALTERNATIVE_TO で Decision に紐付け
]

[schema.core.relations]
structure = [
  "CONTAINS",       # Document → Section、Section → Section
]
grounding = [
  "MENTIONS",       # Section → 意味要素（弱参照）
  "DEFINES",        # Section → 意味要素（その節が定義主体）
  "HAS_EVIDENCE",   # 意味要素 → SourceSpan（行参照付き根拠）
]
semantic = [
  "DEPENDS_ON",
  "CONSTRAINS",
  "REFINES",
  "SUPERSEDES",
  "CONFLICTS_WITH",
  "SUPPORTS",       # 意味要素 → 意味要素（弱依存、根拠としての支持）
  "ALTERNATIVE_TO", # Alternative → Decision
  "RELATED_TO",     # 弱関連（型が定まらない参照）
]
```

**未確認**: 上記スキーマを SchemaLLMPathExtractor に渡す具体的な API 形式（dataclass / pydantic / dict / TypedDict のいずれか）は §4.1 で確認が必要。

### 2.2 Optional Extensions（spec-grag 標準で提供、`.spec-grag/config.toml` で有効化）

```toml
[schema.extensions]
enabled = ["decision_process"]

[schema.extensions.decision_process.entities]
items = [
  "Phase",          # 議論段階
  "RejectedItem",   # 採用しなかった案（Alternative より明確に「却下された」もの）
  "SupersededItem", # 旧版（_old.md など、SUPERSEDES の対象）
]
```

議論プロセスを記録する文書（技術選定経緯、ADR、設計判断記録）でのみ有効化する。一般的な業務要件定義書では不要。

### 2.3 Project Custom Schema（spec-grag 標準には含めない、各プロジェクトが定義）

各プロジェクトが自分のドメイン語彙を `.spec-grag/schema.toml` で定義する。**spec-grag 本体には含めない**。spec-grag 本体は **ドメイン非依存**を保つ。

### 2.4 Section の意味要素参照ポリシー

「Section は 0 個以上の意味要素を参照する。ただし主要節は最低 1 つの Anchor または Summary を持つ」。前置き / 目次的節 / 補足節は意味要素を持たないことが正常。

---

## 3. 設計判断の境界（spec-grag 標準に含めない範囲）

汎用性を保つため、以下は spec-grag 標準スキーマに**含めない**。

### 3.1 プロジェクト固有のドメイン語彙

技術スタック語彙（Layer / Component / API / DataStructure / Action / Hook / Pattern / TechStack 等）、業務語彙（BusinessRule / Account / Transaction 等）、研究語彙（Hypothesis / Experiment / Result 等）、契約語彙（Party / Obligation / Term 等）はすべて Project Custom Schema として各プロジェクト側で定義する。

**理由**: 一つのドメイン語彙を spec-grag 標準に含めると、別ドメインで使えなくなる。「最初のユースケース」に引きずられて汎用性を損なわない。

### 3.2 議論メタデータの標準昇格

Phase / Alternative / Rationale / TakeDown 等の議論プロセスメタデータは、Optional Extensions（`decision_process`）として標準で提供するが、**Core Schema には昇格させない**。標準スキーマだけで EXTERNAL_DESIGN.ja.md §1 の 6 要素と §5.4 の 5 フィールド構造は表現可能。

**理由**: 「将来必要かも」で予防的に Core Schema を太らせない。

---

## 4. 不確定項目（土台作り Phase 完了まで方針確定しない）

[CLAUDE.md](../CLAUDE.md) のルール 1（土台がない状態で設計を議論しない）に従い、以下はすべて確認まで実装に着手しない。「次セッションで調査」「MVP では省略」「最小コストで」は逃げ口にしない（ルール 4）。

**§4.1 が最優先**: §1 仮分担マトリクスは §4.1 調査結果を入力として再評価される。§4.2 以降の作業は §4.1 完了後 → §1 確定 → ユーザーレビュー承認後に開始する。詳細なフェーズ進行は [doc/TODO.md](TODO.md) を参照。

### 4.1 LlamaIndex 系の表面マップ調査

**前提（決定）**: §1.4 のとおり、生成系 LLM は **サブスク認証 Claude/Codex CLI を subprocess external worker として扱う**。LlamaIndex の `LLM` interface に直接組み込むことは Phase 0 では前提にしない。本節 §4.1 は LlamaIndex 部品が以下のどの統合方式を許容するかを実証して Phase 1 で確定する。

- **案 A: 外部抽出 → 投入方式**（Claude/Codex CLI で entity / relation を抽出 → JSON → LlamaIndex graph store に直接投入。LlamaIndex は graph store / retriever / traversal / embedding search に専念）
- **案 B: LLM wrapper 方式**（Claude/Codex CLI を LlamaIndex `LLM` interface でラップ → SchemaLLMPathExtractor 等に渡す）
- **案 C: 混合**（一部 LLM 不要 extractor + 一部外部抽出 + retriever は LlamaIndex 側）

調査項目:

- **PropertyGraphIndex** の API 安定度（v0.10 系での変更頻度、Breaking change の頻度）、コア API（add / build / query / persist / reload）の実体
- **SchemaLLMPathExtractor** の制約強度と統合方式
  - 2a: LlamaIndex `LLM` interface 要求（同期 completion で済むか、async / streaming / structured output 必須か）→ Claude/Codex CLI subprocess wrapper を直接差し込めるか判定（案 B の前提検証）
  - 2b: スキーマ受理形式（dataclass / pydantic / dict / TypedDict のいずれか）
  - 2c: `strict=True` で schema 外 triplet が拒否されるか
  - 2d: **事前抽出済み triplet / nodes / relations を `PropertyGraphIndex` に直接投入する API の有無**（案 A の前提検証）
  - 2e: `kg_extractors` に独自 extractor を差せるか、複数 extractor を組み合わせられるか（案 C の前提検証）
  - 2f: `ImplicitPathExtractor` 等の **LLM 不要 extractor** の存在と用途範囲
- **SimplePropertyGraphStore** の永続化粒度（章別 vs 全体一括の制御可否、pickle / JSON / parquet どれか）、再ロードの粒度、in-memory vs disk persist の境界
- **incremental update 方式**（章単位 SHA-256 変更検出 → 影響範囲のみ再構築できるか、それとも全体再構築のみか、stale edge 除去の挙動）
- **HybridRetriever** の fusion 戦略（RRF / Weighted / CombSum / MaxScore のうち何が標準か、API レベルで切替可能か）
- **HippoRAG / LightRAG retrieval** との統合可否
- **Ollama embedding 接続**: `llama-index-embeddings-ollama` の API 形式、PropertyGraphIndex / Retriever への注入経路、batch / async 対応
- **Claude/Codex CLI subprocess の最小確認**: non-interactive mode（`codex exec` 等）の入出力契約、JSON 整形可否、timeout / 認証切れ / 出力揺れの扱い、サブスク利用上限の挙動

### 4.2 章別管理の実装方針

ChapterAnchor の責務分担は §1.1 / §1.9 で確定済み（CLI/Parser + LLM (Extraction) + GRAG Builder の共同生成物）。残る未確定：

- ChapterAnchor の JSON / dataclass 構造の確定（フィールド名、confidence の値域、relation 候補の表現）
- 章単位 incremental の orchestration（変更章のみ再抽出 → ERG 再構築 → cluster 再計算の境界条件）
- 章別 chapter_index.json / concept_index.json のスキーマ
- 階層 cluster の実装（LlamaIndex に hierarchical clustering があるか、自前実装か）

### 4.3 LLM プロバイダー実装

- Claude CLI / Codex CLI の Python 版 subprocess 設計
- 並列実行（concurrent batch）の実装（`asyncio.gather` + `asyncio.Semaphore`）
- LLM 注入の抽象化（LlamaIndex の `LLM` interface を実装するか独自 protocol か）
- LLM 用途別（Extraction / Classification / Answer）の設定切替

### 4.4 Cross-Encoder rerank

- 日本語向けモデル選定
- LlamaIndex への統合方法

### 4.5 spec-grag CLI 実装

- フレームワーク選定（Click / Typer / Fire 等）
- パッケージング（`pyproject.toml`、`uv` / `pdm` / `poetry` 等）
- 配布方式

### 4.6 整合性チェックの実装

- グラフ構造ベース検出ルールの具体（Cypher 風クエリで書くか、Python 直書きか）
- ルールベース検出の YAML / TOML スキーマ
- LLM (Classification) 推論の prompt template（日本語）
- `conflict=true` 昇格の Validator ルール（§1.5 二段階の deterministic 検査）

### 4.7 4 軸評価の実装（transient annotation）

4 軸は graph の **恒久プロパティではなく**、課題依存の transient annotation として retrieval result / InjectionContext / RealignResult 上に持つ（§1.6）。残る未確定：

- 4 軸の値域・閾値・default
- LLM (Classification) の prompt template（4 軸を独立に評価）
- 派生状態 `irrelevant` の自動算出ロジック
- 同一項目が複数 InjectionContext フィールドに所属する場合の重複表示制御
- transient と恒久プロパティ（§1.6 表）の永続化境界の実装上の保証（graph に 4 軸を書き込まないことの enforcement）

### 4.8 Concept 更新案 unified diff

- cluster summary → Concept 文書の生成パイプライン
- diff ライブラリ選定（`difflib` 標準 vs サードパーティ）
- diff の context_radius / unified format の出力規約

### 4.9 Optional Extensions の発動判断

- decision_process 拡張をいつ有効化するか
- `.spec-grag/config.toml` の `[schema.extensions]` で `enabled` を制御

---

## 5. 関連ドキュメント

### リポジトリ内（現行）

- [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md): 外部契約（source of truth、不変）
- [CLAUDE.md](../CLAUDE.md): リポジトリレベルの不変ルール

### BAK/（pre-pivot のアーカイブ、参考のみ）

`BAK/` 配下に Rust + graphrag-rs 前提の旧実装と関連調査資料が保管されている。pivot 後の設計には戻らないが、過去の機能調査結果は参考になる場合がある。
