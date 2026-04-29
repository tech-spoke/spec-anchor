# SPEC-grag 詳細設計書（draft、2026-04-29）

> **位置付け**: これは現 [doc/DESIGN.ja.md](DESIGN.ja.md) の **書き直し draft**。
> [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md)（不変、source of truth）の全要件を **維持した上で**、それを **Native LlamaIndex GraphRAG Flow + 軽量 graph schema + Orchestrator 実装** で実現する設計方針を記述する。
>
> **大原則**:
>
> - EXTERNAL_DESIGN.ja.md の要件（Purpose / Concept / Source specs / ChapterAnchor / Entity Relationship Graph / Hierarchical Cluster / ConstraintContext / TargetContext / ConflictNotes / ReviewNotes / 4 軸評価 / Conflict 二段階 / Concept 承認制 / Answer 生成 4 区分）は **すべて実現する**
> - 軽量化されるのは **graph schema レベル**（5 entity / 6 relation）と **実装手段**のみ
> - graph 上に持たない概念は **Orchestrator 側で実装**して外部契約を満たす
>
> ユーザーレビュー承認後に DESIGN.ja.md と置換する。

本書は SPEC-grag の **現時点での実装方針** を記録する。外部契約は [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md)（source of truth、不変）で定義され、本書はその実装側の方針を扱う。

---

## 1. アーキテクチャ

### 1.1 責務マトリクス

SPEC-grag は判断契約を **GRAG / GraphRAG ライブラリに委譲しない**。GRAG は構造化された候補生成・検索基盤であり、最終判断は CLI / Orchestrator / LLM（用途別）/ Human が分担する。

| 領域 | 持ち主 | やること |
|---|---|---|
| Purpose 確定 | **Human** | 書く・確定する。LLM は更新しない |
| Concept 承認 | **Human** | accept / reject / 修正指示。LLM は自動承認しない |
| Concept 更新候補生成 | LLM (Extraction) + GRAG | 章本文と現 Concept から更新候補を unified diff として提示。最終確定はしない |
| 変更検出 | **CLI** | hash / section 差分（決定的、LLM 不要）|
| Document / Section 構造 | **CLI / Parser** | Markdown AST から決定的に取得 |
| ChapterAnchor の文書構造部分 | **CLI / Parser** | document_id / section_id / heading_path / source_hash |
| ChapterAnchor の意味要素部分 | LLM (Extraction) | ANCHOR / CONCEPT / 章間 relation を SchemaLLMPathExtractor で抽出 |
| Entity / Relation 抽出 | LLM (Extraction) | 軽量 schema（5 entity / 6 relation）で抽出 |
| Section grounding / normalization | **Orchestrator** | LLM が出した自由文字列の CHAPTER / SECTION 名を deterministic section_id に正規化（§2.4）|
| Graph store / 検索 / 探索 | **GRAG subsystem** | LlamaIndex Property Graph 標準フロー。判断はしない |
| 軽量 Graph Schema | **spec-grag Core** | 5 entity / 6 relation（§2.1）|
| EXTERNAL_DESIGN.ja.md 概念の実現 | **Orchestrator** | Concept / ChapterAnchor / Hierarchical Cluster / ConstraintContext / TargetContext / ConflictNotes / ReviewNotes を Orchestrator 側 wrapper で実現（§3 参照）|
| 4 軸評価の付与 | LLM (Classification) + **Orchestrator** | §1.6 の 4 軸を retrieval 候補に付与（graph 不汚染、transient annotation）|
| 未承認 Concept 遮断 | **Orchestrator** | 絶対に通さない（InjectionContext / Answer 生成を停止）|
| Conflict 候補 → 確定の昇格 | Validator + **Human** | LLM 単独では `conflict=true` 不可（§1.5 二段階）|
| Hierarchical Cluster | **Orchestrator** | graph に持たず、retrieval 時に章間 relation traversal で動的算出（§3.5）|
| InjectionContext 構築 | **Orchestrator** | ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes / ReviewNotes に構造化（§3.1）|
| Answer 生成 | LLM (Answer) | InjectionContext / RealignResult に拘束された 4 区分回答（§3.6）|

LLM は **用途別に分離**して扱う:

- **Extraction LLM**: SchemaLLMPathExtractor の LLM backend、Concept 更新候補生成
- **Classification LLM**: 4 軸付与（review_required / semantic_conflict_candidate）、Validator の deterministic 検査を経る
- **Answer LLM**: InjectionContext を前提に回答生成、ConstraintContext を守る、ConflictNotes / ReviewNotes を隠さない

### 1.2 GRAG / GraphRAG ライブラリがしてはいけないこと

- Purpose を更新する
- Concept diff を自動承認する
- 課題に対して何を最終制約にするかを確定する
- 何を修正対象にするかを最終確定する
- 未承認 Concept を勝手に検索対象に混ぜる
- Answer を生成する
- `conflict=true` を単独で確定する

GRAG / GraphRAG ライブラリ（LlamaIndex / Neo4j 等）は **GRAG subsystem の内部実装**に過ぎず、SPEC-grag の判断契約を代替しない。

### 1.3 三層分業（実装パッケージ）

```text
┌────────────────────────────────────────────────────────┐
│  Agent (Claude / Codex CLI) — slash command 実行層     │
│  - ConversationContext + 課題プロンプト解釈            │
│  - Agentic search で章本文を読む                        │
│  - 章アンカー欠損章を動的補完                           │
│  - Concept 更新候補の unified diff 生成                 │
│  - InjectionContext / RealignResult を読み Answer 生成 │
│  - raw source spec の Read は §1.7 で制限される        │
└──────────────────┬─────────────────────────────────────┘
                   │ Bash 呼び出し
                   ↓
┌────────────────────────────────────────────────────────┐
│  spec-grag CLI / Orchestrator（Python）                 │
│  - .spec-grag/config.toml 読み込み                      │
│  - 変更検出（章単位 SHA-256）                            │
│  - GRAG Builder / Retriever / Validator 呼び出し制御   │
│  - 未承認 Concept 遮断                                  │
│  - 2 系統 pipeline（制約探索 / 修正対象探索）            │
│  - 4 軸評価のオーケストレーション                       │
│  - Conflict 二段階の Validator + 昇格制御               │
│  - Hierarchical Cluster の動的算出                      │
│  - InjectionContext / RealignResult 構造化出力          │
│  - safe_delete_by_section wrapper（R1）                 │
│  - Section grounding / normalization                    │
└──────────────────┬─────────────────────────────────────┘
                   │ Python API（LlamaIndex 標準フロー）
                   ↓
┌────────────────────────────────────────────────────────┐
│  GRAG（LlamaIndex Property Graph、軽量 schema）          │
│  - PropertyGraphIndex.from_documents / from_existing    │
│  - SchemaLLMPathExtractor + ImplicitPathExtractor       │
│  - 軽量 schema: DOCUMENT / CHAPTER / SECTION /          │
│                ANCHOR / CONCEPT（§2.1）                 │
│  - SimplePropertyGraphStore（JSON 永続化）              │
│  - SimpleVectorStore + OllamaEmbedding（dim=768）       │
│  - PGRetriever / VectorContextRetriever                 │
│  - LLM backend = CodexCLIAdapter（spec-grag が実装）   │
│  → 候補を返すのみ。判断はしない                         │
└────────────────────────────────────────────────────────┘
```

### 1.4 採用方針（pivot 後 + Phase 0 結果）

**確定方針（pivot 後 commit b45d95f / 2026-04-27）**:

- 言語: **Python**
- GRAG エンジン: **LlamaIndex** Property Graph（標準フローに乗る、Native LlamaIndex GraphRAG Flow）
- graph store: ローカル・ファイルベース `.spec-grag/graph/`
- **生成系 LLM**（用途別: Extraction / Classification / Answer）: **Claude CLI / Codex CLI**
  - サブスク認証前提（API key 前提にしない）
  - subprocess 呼び出しで JSON 入出力契約（structured output: `--json-schema` / `--output-schema`）
  - 統合方式: **Native LlamaIndex GraphRAG Flow**
    - `CodexCLIAdapter(CustomLLM)` を LlamaIndex の LLM backend として実装
    - `SchemaLLMPathExtractor` に渡す
    - `PropertyGraphIndex` / `SimplePropertyGraphStore` / Retriever は LlamaIndex 標準フローに乗る
    - 旧調査資料上の「案 B」に相当する（[doc/SURVEY/SUMMARY.md §3.9](SURVEY/SUMMARY.md) / [13_path_b_design_options.md](SURVEY/13_path_b_design_options.md)）
- **ベクトル化 model（embedding）**: **Ollama nomic-embed-text**（ローカル、dim=768）

**Phase 0 で確定した運用ルール R1〜R5**:

| ルール | 内容 |
|---|---|
| R1 | `safe_delete_by_section` wrapper を spec-grag 側で実装する（LlamaIndex 標準 `delete()` は cascade で対岸 entity を消すため使えない、spike 01 で実証）|
| R2 | **`kg_extractors` は空配列 `[]` にしない**（falsy で default の `[SimpleLLMPathExtractor, ImplicitPathExtractor]` が呼ばれて `Settings.llm` 解決が走る）。Native LlamaIndex GraphRAG Flow では必ず `kg_extractors=[ImplicitPathExtractor(), schema_llm_path_extractor]` のように **ImplicitPathExtractor + SchemaLLMPathExtractor を明示**する。LLM 抽出を無効化する特殊ケースのみ `[ImplicitPathExtractor()]` 単独を許可する |
| R3 | `load_index_from_storage` を使わず、graph_store を `from_persist_dir` で reload + 毎セッション `from_existing` で再構築 |
| R4 | PGRetriever の rank fusion / 4 軸付与 / vector_store 連結はすべて spec-grag Orchestrator 側責務 |
| R5 | Claude / Codex CLI subprocess は `--bare` 不使用（OAuth/keychain を読まないため）。代わりに `--no-session-persistence` + `--disable-slash-commands` + `--allowedTools ""` 等の組合せ |

### 1.5 整合性チェック方針（3 段階パイプライン + Conflict 二段階）

LLM 抽出を完全信用しない。EXTERNAL_DESIGN.ja.md §5.4 の ConflictNotes（制約 vs 修正対象 / Source spec 同士 / Concept vs Source spec）の検出は 3 段階で行う:

1. **グラフ構造ベース**（決定論的、優先）
   - graph 上の章間 `SUPERSEDES` チェーンに循環がある（軽量 schema では `REFINES` の循環で代用）
   - 同一 CONCEPT に対し異なる定義 SECTION が存在する
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

LLM (Classification) は **候補**を出してよいが、**確定**は Validator または Human approval を経る。実装は Orchestrator 側（§3.3）。

### 1.6 4 軸評価（transient annotation、graph 不汚染）

EXTERNAL_DESIGN.ja.md §5.4 で「同じ Concept / Source spec が制約側と修正対象側の両方に現れる場合もある」と定義されているとおり、課題に対する評価は**排他的 5 分類ではなく、4 軸の独立評価**として実装する。

**4 軸は課題依存の transient annotation**。同一概念が課題ごとに違う評価を持つため、graph store の **恒久プロパティとしては保持しない**（spike 03 で実証）。retrieval result / InjectionContext / RealignResult 上にのみ保持する。

| 種別 | 例 | 保持先 |
|---|---|---|
| 恒久プロパティ | document_id / section_id / heading_path / source_hash / created_at / updated_at（任意）/ source_span（任意）/ evidence_excerpt（任意） | graph store（LlamaIndex SimplePropertyGraphStore の properties）|
| transient annotation | constraint_relevance / target_relevance / semantic_conflict_candidate / review_required / ranking_score | retrieval result の NodeWithScore.metadata / InjectionContext / RealignResult |

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

**InjectionContext のフィールド対応**（EXTERNAL_DESIGN §5.4 の構造、Orchestrator が振り分ける）:

| 4 軸の状態 | InjectionContext の所属フィールド |
|---|---|
| `constraint_relevance ≠ none` | `constraint_context.{purpose,concept,source_spec,chapter_anchor}_constraints` |
| `target_relevance ≠ none` | `target_context.{candidate_targets,related_concepts,related_source_sections,related_chapter_anchors,related_entities}` |
| `conflict == true` | `conflict_notes` |
| `review_required == true` | `review_notes` |
| すべて none/false（派生 irrelevant） | `excluded_as_irrelevant` |

同一項目が複数フィールドに同時所属しうる。実装は Orchestrator 側（§3.1 / §3.2）。

### 1.7 Agent の Read tool 使用制限

Agent (Claude / Codex CLI) は spec-grag CLI の外側で動く実行制御層であり、raw source spec の直接読み取りは **用途を限定**する。Orchestrator の **未承認 Concept 遮断**を Agent が迂回しないための制約。

**許可される Agent の Read**:

- Agentic search（GRAG 候補補正、章アンカー欠損章の動的補完、§2.5）
- evidence inspection（debug / 人間レビュー用）
- 章ファイルの軽量サンプリング（章数の確認等）

**禁止される Agent の Read**:

- Answer 生成時に raw source spec を **直接 Answer の根拠として組み込む**
- InjectionContext を経由せず source spec の内容を Answer に引用する
- 未承認 Concept を含む章ファイルを Answer の根拠として使う
- ConstraintContext / TargetContext / ConflictNotes / ReviewNotes に **存在しない情報**を Answer 制約として持ち込む

Answer 生成時の制約・修正対象・競合候補は **InjectionContext / RealignResult 経由のみ**使用する。raw source の Read は補助的な確認手段に限定する。

### 1.8 LlamaIndex 部品契約（candidate_only）

LlamaIndex 部品はすべて **candidate_only** として扱う。承認状態、制約確定、Concept 更新、Conflict 確定の権限は持たせない。

| 部品 | role | authority | 許可される用途 | 禁止される用途 |
|---|---|---|---|---|
| `PropertyGraphIndex` | graph_index_builder_and_query_surface | candidate_store_only | graph_build / retrieval / relation_candidate_storage | concept_approval / conflict_resolution / answer_generation / 制約確定 |
| `SchemaLLMPathExtractor` | schema_constrained_path_candidate_extraction | candidate_only | entity_candidate_extraction / relation_candidate_extraction | concept 承認 / 最終 relation 決定 / Purpose 更新 / Conflict 確定 |
| `SimplePropertyGraphStore` | local_graph_persistence_candidate | storage_only | local_persist / local_reload | source_of_truth_for_approval / Concept レジストリ代替 |
| `Retriever` | evidence_backed_candidate_retrieval | retrieval_only | candidate_search / evidence_collection | final_classification / Orchestrator なしの answer_generation |
| `CodexCLIAdapter` (spec-grag 実装) | llm_backend_for_extraction | structured_output_only | SchemaLLMPathExtractor の LLM、subprocess経由 JSON | 判断 / 承認 / 制約確定 |

### 1.9 内部処理フロー（3 コマンド × 4 経路）

EXTERNAL_DESIGN.ja.md §4 / §5 / §6 の 3 コマンドを、§1.1 の責務境界と §1.5〜§1.8 の制約に従って実行する。`/spec-core` は incremental / --all の 2 経路、計 4 経路すべてが一気通貫で動作する。

```text
経路 1: /spec-core incremental（変更分のみ）
  1. CLI: .spec-grag/config.toml 読み込み
  2. CLI: Source specs の変更検出（章単位 SHA-256、決定的）
  3. CLI: 変更 Section 特定
  4. spec-grag が safe_delete_by_section(graph_store, section_id) で
     変更章の旧 node / relation を整合的に除去（R1）
  5. CLI / Parser: 変更章の Markdown heading から
     DOCUMENT / CHAPTER / SECTION 構造（CONTAINS）を deterministic に生成
     - heading_path / source_hash 等の恒久プロパティを付与
  6. ChapterAnchor 生成（共同責務、変更 Section のみ）
     - SchemaLLMPathExtractor が変更章から ANCHOR / CONCEPT / 章間 relation を抽出
     - LLM backend = CodexCLIAdapter（Native LlamaIndex GraphRAG Flow）
     - schema = §2.1 軽量 schema（5 entity / 6 relation）
     - Orchestrator が Section grounding / normalization で正規化（§2.4）
  7. graph_store.upsert_nodes / upsert_relations で投入
  8. Concept 更新候補生成（§3.4）
     - GRAG が relation 駆動で「Core 書き換え候補」を抽出
     - LLM (Extraction) が Agentic search で章本文確認 + unified diff 生成
  9. CLI: Concept diff を Human に hunk 単位提示
 10. Human: accept / reject / 修正指示
 11. CLI: 未承認の場合は Concept を更新せず停止

経路 2: /spec-core --all（全再構築）
  1. CLI: .spec-grag/config.toml 読み込み
  2. shutil.rmtree(persist_dir) で既存 graph store / vector store を破棄
     （別パスへバックアップしてから削除する選択肢も）
  3. CLI: sources.include の全章を対象として SchemaLLMPathExtractor で再抽出
  4. PropertyGraphIndex.from_existing で再構築 + persist
  5. Concept 再生成候補（経路 1 の Step 8 と同じプロセス）
  6. CLI: Concept diff を Human に提示（全章再生成での diff）
  7. Human: accept / reject / 修正指示
  8. CLI: 未承認の場合は Concept を更新せず停止

経路 3: /spec-inject（GRAG を信じすぎず、Agentic search 併用）
  1. CLI: 経路 1（/spec-core incremental）を内部実行
  2. Orchestrator: Concept diff が未承認なら停止（InjectionContext 生成しない）
  3. CLI: ConversationContext + 課題プロンプト + Purpose + 承認済 Concept を取得
  4. Orchestrator: Purpose を必ず ConstraintContext 候補に追加（自動）
  5. CLI → GRAG Retriever: 関連候補を 2 系統 pipeline で取得
     a. 制約探索: PGRetriever + Concept / Source specs 制約候補
     b. 修正対象探索: VectorContextRetriever + 章間 relation 探索
     - 各候補は (node, relation, source span, evidence, confidence, score) を持つ
     - graph の relation は「読むべき場所のヒント」、確定事実ではない
  6. GRAG: 該当章 / 関連章の chapter_anchors（ANCHOR）を取得
  7. LLM: Agentic search を併用して以下を行う:
     a. GRAG 候補を章本文ベースで補正（関連が薄い候補は除外、見落とし候補を追加）
     b. 章アンカー欠損章を Agentic search で動的補完（§2.5）
     c. graph の relation type を章本文確認後に確信度付きで context に反映
  8. LLM (Classification) + Orchestrator: 4 軸評価を付与（transient annotation）
     - constraint_relevance / target_relevance / conflict / review_required
     - LLM が出すのは候補（review_required, semantic_conflict_candidate）まで
  9. Validator: schema / source / Concept approval / Conflict 昇格を deterministic に検査（§1.5）
 10. Orchestrator: InjectionContext を構造化出力（§3.1 のフィールド対応）
     - ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes / ReviewNotes
     - chapter_anchors（GRAG / Agentic search 由来を明示）
     - cascade_candidates（source_origin: GRAG / Agentic search / 両方）
     - GRAG Freshness Report

経路 4: /spec-realign（context 構築後の Agentic search 追補も許容）
  1. 経路 3（/spec-inject 相当）で InjectionContext を作成
  2. LLM (Answer): InjectionContext / RealignResult に拘束された 4 区分回答を生成（§3.6）
     - 守る制約（ConstraintContext）
     - 修正候補（TargetContext）
     - 競合 / 不確実性 / 人間レビュー（ConflictNotes / ReviewNotes）
     - 課題への回答または修正案
     - 経路 3 で確認できなかった章があれば追加 Agentic search で補完してよい
     - graph の relation を「確定事実」として引用しない、章本文を根拠に明示する
     - raw source spec を直接根拠に使わない（§1.7、InjectionContext 経由のみ）
  3. Orchestrator: RealignResult を構造化出力（task_prompt + InjectionContext + answer）
```

**経路間の依存関係**:

- 経路 3 / 4 は経路 1（incremental）を内部で呼ぶ → Concept diff 未承認時は停止
- 経路 2（--all）は単独実行のみ
- 経路 1 / 2 で生成された ANCHOR / 関連 relation が経路 3 の Retriever で取得できることを保証する

ChapterAnchor は **retrieval artifact** であり、判断主体ではない。`/spec-core`（経路 1 / 2 両方）で生成・更新するが、「課題に対して制約か修正対象か」は確定しない。その評価は `/spec-inject` または `/spec-realign` で課題に応じて 4 軸評価（transient annotation）を付与する。

---

## 2. スキーマ

### 2.1 軽量 Graph Schema（5 entity / 6 relation）

**実装方針**: EXTERNAL_DESIGN.ja.md §1 の概念（Purpose / Concept / Source specs / ChapterAnchor / Entity Relationship Graph / Hierarchical Cluster）と §5.4 の構造化 context（ConstraintContext / TargetContext / ConflictNotes / ReviewNotes）を実現するため、graph schema は **5 entity / 6 relation の軽量版**を採用する。Orchestrator 側（§3）でこれらの概念を構造化して提供する。

**Entity（5 種）**:

| Entity | 抽出方式 | 説明 |
|---|---|---|
| `DOCUMENT` | deterministic（CLI / Parser）| ファイル単位（`docs/spec/foo.md`）|
| `CHAPTER` | deterministic（Markdown heading から）| 上位章（H1 / H2）|
| `SECTION` | deterministic（Markdown heading から）| 下位節（H2 / H3）|
| `ANCHOR` | LLM 抽出（SchemaLLMPathExtractor）| 章のキーアンカー（主要キーワード / 概念 / トピック、3〜7 個）|
| `CONCEPT` | LLM 抽出（SchemaLLMPathExtractor）| EXTERNAL_DESIGN.ja.md §1 の `Concept`（コアコンセプト）に対応する graph entity。Core 文書（user-managed、graph 外）との紐付け候補として graph に乗る |

**Relation（6 種）**:

| Relation | 抽出方式 | 説明 |
|---|---|---|
| `CONTAINS` | deterministic | DOCUMENT → CHAPTER、CHAPTER → SECTION |
| `MENTIONS` | LLM 抽出 | CHAPTER / SECTION → ANCHOR / CONCEPT（弱参照、grounding）|
| `RELATED_TO` | LLM 抽出 | 弱関連（章同士 / 概念同士、SUPPORTS / ALTERNATIVE_TO の抽象化）|
| `DEPENDS_ON` | LLM 抽出 | 依存関係（章 / 概念、CONSTRAINS の抽象化を含む）|
| `REFINES` | LLM 抽出 | 精緻化 / 詳細化（SUPERSEDES の抽象化を含む）|
| `CONTRASTS_WITH` | LLM 抽出 | 対比 / 異なる視点（CONFLICTS_WITH より緩い、graph 上の Conflict 確定は §1.5 二段階を経る）|

**deterministic 部分（DOCUMENT / CHAPTER / SECTION / CONTAINS）は spec-grag CLI が Markdown AST から直接生成し、graph_store.upsert_nodes / upsert_relations で投入する**。LLM 抽出に任せない（精度・速度・冪等性の都合）。

### 2.2 EXTERNAL_DESIGN.ja.md 概念と graph schema の対応表

EXTERNAL_DESIGN.ja.md の各概念を、軽量 graph schema + Orchestrator 実装でどう実現するかの対応:

| EXTERNAL_DESIGN.ja.md 概念 | graph schema での表現 | 実装場所 |
|---|---|---|
| Purpose（人手書き、不変）| graph に持たない | spec-grag CLI が常に ConstraintContext に追加（経路 3 Step 4）|
| Concept（コアコンセプト、人承認） | Core 文書（user-managed、graph 外）+ CONCEPT entity（紐付け候補）| spec-grag CLI が Core 文書管理、graph は更新候補 hint |
| Source specs | DOCUMENT / CHAPTER / SECTION（heading から deterministic）| spec-grag CLI が Markdown AST 解析 |
| ChapterAnchor | ANCHOR entity + 章本文 + Agentic search（§2.5 フォールバック）| graph に乗る、欠損章は LLM が動的補完 |
| Entity Relationship Graph | 5 entity / 6 relation の graph 全体 | LlamaIndex Property Graph 標準フロー |
| Hierarchical Cluster | graph に持たない、retrieval 時に動的算出 | Orchestrator が章間 relation traversal で動的算出（§3.5）|
| ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes / ReviewNotes | graph に持たない | Orchestrator が InjectionContext のフィールドに振り分け（§3.1）|
| 4 軸評価 | graph に持たない（transient annotation）| Orchestrator が NodeWithScore.metadata に後付け（§3.2、spike 03 で実証）|
| Conflict 二段階確定 | graph 上の CONFLICTS_WITH ではなく、Orchestrator 側 Validator | グラフ構造ベース + ルールベース + LLM Classification 候補（§1.5 / §3.3）|
| Concept 承認制 | graph と無関係 | spec-grag CLI が unified diff を hunk 単位で人承認 UX 提供（§3.4）|
| Answer 生成 4 区分 | graph と無関係 | LLM (Answer) への prompt 制約として実装（§3.6）|

### 2.3 SchemaLLMPathExtractor へのスキーマ受理形式（Phase 0 確認済）

```python
from typing import Literal

Entities = Literal["DOCUMENT", "CHAPTER", "SECTION", "ANCHOR", "CONCEPT"]
Relations = Literal["CONTAINS", "MENTIONS", "RELATED_TO", "DEPENDS_ON", "REFINES", "CONTRASTS_WITH"]

# 関係型整合 schema（接続可能な triple）
kg_validation_schema = [
    ("DOCUMENT", "CONTAINS", "CHAPTER"),
    ("CHAPTER", "CONTAINS", "SECTION"),
    ("CHAPTER", "MENTIONS", "ANCHOR"),
    ("CHAPTER", "MENTIONS", "CONCEPT"),
    ("SECTION", "MENTIONS", "ANCHOR"),
    ("SECTION", "MENTIONS", "CONCEPT"),
    ("CHAPTER", "RELATED_TO", "CHAPTER"),
    ("CHAPTER", "DEPENDS_ON", "CHAPTER"),
    ("CHAPTER", "REFINES", "CHAPTER"),
    ("CHAPTER", "CONTRASTS_WITH", "CHAPTER"),
    ("CONCEPT", "RELATED_TO", "CONCEPT"),
    ("CONCEPT", "DEPENDS_ON", "CONCEPT"),
    ("CONCEPT", "REFINES", "CONCEPT"),
    ("CONCEPT", "CONTRASTS_WITH", "CONCEPT"),
    ("ANCHOR", "RELATED_TO", "ANCHOR"),
]

extractor = SchemaLLMPathExtractor(
    llm=codex_cli_adapter,                  # CodexCLIAdapter (CustomLLM)
    possible_entities=Entities,
    possible_relations=Relations,
    kg_validation_schema=kg_validation_schema,
    strict=True,
    extract_prompt="<日本語プロンプト>",  # spec-grag が用意
    max_triplets_per_chunk=20,
)

# R2: kg_extractors=[ImplicitPathExtractor(), schema_extractor] と明示
```

### 2.4 Section grounding / normalization（LLM 出力の正規化）

SchemaLLMPathExtractor の出力をそのまま graph に確定投入してはいけない。LLM が章名 / 節名から派生して生成した CHAPTER / SECTION ノードと、deterministic に作った CHAPTER / SECTION ノードの **ID を正規化して接続**する責務は spec-grag CLI が持つ。

理由: SchemaLLMPathExtractor は LLM に「この章 X が章 Y に DEPENDS_ON している」と推論させると、LLM が `"章 Y"` 等の自由文字列で新規 CHAPTER / SECTION ノードを生成する。一方で spec-grag は heading から `docs/foo.md#section-y` のような deterministic な section_id を持つ CHAPTER / SECTION ノードを既に作っている。両者を結ばないと、graph 上で **同名・別 ID の孤立ノード** が増える。

**正規化ルール**:

| ルール | 内容 |
|---|---|
| 入力 chunk metadata | LlamaIndex の `Document` / `TextNode` に `current_section_id` / `heading_path` / `doc_path` を metadata として渡す |
| 抽出範囲の限定 | LLM には原則として **current section を source とする relation のみ抽出**させる（自由文字列の CHAPTER / SECTION ノードを大量生成しないよう prompt で制約） |
| target の解決 | LLM が relation の target として出した CHAPTER / SECTION の自由文字列は、`target_hint` として一旦保持し、spec-grag CLI が **既存 deterministic section_id に解決**する（heading text / heading_path の文字列マッチ + embedding 類似で）|
| 解決できない target の扱い | `unresolved_relation` として保持、または `RELATED_TO` の低信頼候補として graph に入れる |
| 重複ノード生成の禁止 | deterministic node と同名でない CHAPTER / SECTION ノードを LLM が新規作成することは **graph 投入時に拒否**する |
| ANCHOR / CONCEPT は対象外 | この正規化は CHAPTER / SECTION のみに適用。ANCHOR / CONCEPT は LLM が自由に生成して良い |

実装は Phase 1 spike 06（軽量 schema + 章アンカー抽出）の中で詰める。

### 2.5 章アンカー欠損時の Agentic search フォールバック

GRAG が章アンカーを持っていない章（抽出失敗 / 質が低い / 新規追加章で未抽出）は、`/spec-inject` / `/spec-realign` 実行時に LLM が章本文を Agentic search で読んで動的に章アンカーを作成する。spec-grag CLI は両者をマージして InjectionContext.chapter_anchors に乗せる。実装は Phase 1 spike 08。

### 2.6 ノード / リレーションのプロパティ

**必須プロパティ**:

| プロパティ | 対象 | 用途 |
|---|---|---|
| `section_id` | ANCHOR / CONCEPT / 章間 relation 全部 | 章単位 stale 除去（safe_delete_by_section、R1）|
| `heading_path` | CHAPTER / SECTION | 「1 / 認証」のような可読 path |
| `source_hash` | CHAPTER / SECTION | 章単位 SHA-256（変更検出）|
| `document_id` | 全 entity | 所属 document の id |

**任意プロパティ**（debug / evidence / 拡張用、取得できたら graph に乗せる）:

| プロパティ | 対象 | 用途 |
|---|---|---|
| `embedding` | ANCHOR / CONCEPT | vector retrieval 用（spec-grag CLI が事前計算してセット）|
| `description` | ANCHOR / CONCEPT | LLM 抽出時の付加情報 |
| `source_span` | 章間 relation / ANCHOR / CONCEPT | 行範囲（[26:1263-1289] 等）。debug / 根拠提示用 |
| `evidence_excerpt` | 章間 relation / ANCHOR / CONCEPT | LLM 抽出 relation の短い根拠テキスト |
| `heading_start_line` | CHAPTER / SECTION | section の Markdown 内開始行番号 |
| `created_at` / `updated_at` | 全 entity | ISO8601 timestamp |

**transient annotation**（4 軸評価）は graph には書かない（§1.6 / §3.2）。

---

## 3. Orchestrator 側で EXTERNAL_DESIGN.ja.md 概念を実現する

軽量 graph schema には乗せず、Orchestrator が EXTERNAL_DESIGN.ja.md の概念を実現する責務:

### 3.1 InjectionContext の構造化（ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes / ReviewNotes）

EXTERNAL_DESIGN.ja.md §5.4 / §8.1 の構造を Orchestrator が組み立てる。

```text
Orchestrator が経路 3 で行う:
  retrieval 候補（NodeWithScore のリスト、graph + Agentic search 由来）
    ↓
  4 軸評価付与（§3.2）
    ↓
  各候補を 4 軸の値で振り分け（§1.6 のフィールド対応表）:
    constraint_relevance ≠ none → constraint_context.{...}_constraints
    target_relevance ≠ none     → target_context.{...}
    conflict == true            → conflict_notes（Validator 確定後のみ）
    review_required == true     → review_notes
    すべて none/false (派生 irrelevant) → excluded_as_irrelevant
    ↓
  InjectionContext として構造化出力（EXTERNAL_DESIGN.ja.md §8.1）
```

同一項目が複数フィールドに同時所属しうる（例: Constraint としても Target としても関連、かつ Conflict 候補で review 必要）。

### 3.2 4 軸 transient annotation（graph 不汚染、spike 03 で実証）

- LLM (Classification) が retrieval 候補 each に 4 軸の **候補値**を出す
  - `review_required = true / false`
  - `semantic_conflict_candidate = true / false`
  - `constraint_relevance = none | low | medium | high`
  - `target_relevance = none | low | medium | high`
- Orchestrator が NodeWithScore.metadata に後付け（spike 03 で実証）
- graph_store / persist パスには 4 軸を書き込まない（spike 03 で graph 不汚染を確認）
- LLM 単独では `conflict = true` を発火させない（§1.5 二段階）

### 3.3 Conflict 二段階確定（Orchestrator 側 Validator）

§1.5 の 3 段階パイプラインを Orchestrator が実装する。

```text
段階 1（グラフ構造ベース、決定論的）:
  - 章間 REFINES / SUPERSEDES の循環検出
  - 同一 CONCEPT に対し異なる定義 SECTION の存在検出
  - 同一 ID への異なる属性並存検出
  → これらに該当した候補を「conflict 候補」として retrieval result に印を付ける

段階 2（ルールベース、決定論的）:
  - Purpose の制約条項と Source spec の対立量化詞検出
  - sources_scanned_through より新しい修正と古い章の食い違い検出
  - Required と Optional の同時指定検出
  → 段階 1 と合わせて「conflict 候補」を絞り込む

段階 3（LLM 推論、補助）:
  - 段階 1 / 2 で疑わしい候補のみ LLM (Classification) で意味的妥当性を確認
  - LLM が `semantic_conflict_candidate = true` / `review_required = true` を出してよい
  - LLM 単独で `conflict = true` は不可

確定:
  conflict = true は構造的根拠（段階 1 or 2）または Human approval を必須とする
```

実装は Phase 1 spike 11。

### 3.4 Concept (Core) 承認制

EXTERNAL_DESIGN.ja.md §3.4 / §4.5 の Concept 更新候補生成プロセス:

```text
1. GRAG が relation 駆動で「Core 書き換え候補」を抽出
   - SchemaLLMPathExtractor が章から CONCEPT entity を抽出
   - 現 Core 文書の概念と比較
   - relation（REFINES / CONTRASTS_WITH 等）で関連付く章 / 概念を候補とする
2. LLM が Agentic search で章本文・現 Core を確認、unified diff を生成
3. SPEC-grag CLI がユーザーに hunk 単位で提示
4. ユーザーが accept / reject / 修正指示
5. SPEC-grag CLI が accept された hunk を Core 文書に反映
```

候補生成方式 (P) GRAG 経由 vs (Q) LLM 直接 の比較は Phase 1 spike 09 で行う。

### 3.5 Hierarchical Cluster（動的算出）

EXTERNAL_DESIGN.ja.md §1 の Hierarchical Cluster は graph schema には乗せず、retrieval 時に動的算出する:

```text
- spec-grag Orchestrator が retrieval 時に章間 relation traversal を行う
  - get_rel_map(seed_chapters, depth=2-3) で関連章群を取得
  - DEPENDS_ON / REFINES / RELATED_TO の path を辿る
- 取得した章群を「クラスタ」として InjectionContext に渡す
- 必要に応じて spec-grag が章別 cluster_index を sidecar として持つ（実装容易性次第）
```

実装は Phase 1 spike 12。

### 3.6 Answer 生成 4 区分（LLM への prompt 制約）

EXTERNAL_DESIGN.ja.md §6.5 の Answer 生成契約。LLM (Answer) への prompt 制約として実装:

```text
LLM へ渡す prompt template（spec-grag が固定）:
  - InjectionContext.ConstraintContext を「今回の回答で守る制約」として扱う
  - InjectionContext.TargetContext を「今回の修正候補または検討対象」として扱う
  - InjectionContext.ExclusionNotes は「回答の前提情報として採用しない」
  - InjectionContext.ConflictNotes は Answer 内で明示する
  - InjectionContext.ReviewNotes は Answer 内で「人間レビューが必要な点」として明示する
  - InjectionContext.approved_concept_update / warnings は「不確実性または人間レビュー項目」として Answer 内で明示する

Answer は次を区別して記述:
  1. 今回の回答で守る制約
  2. 今回の回答で扱う修正候補または検討対象
  3. 競合 / 不確実性 / 人間レビューが必要な点
  4. 課題プロンプトへの回答または修正案

制約と矛盾する案を出す場合は、その矛盾を Answer 内で明示し、人間レビューが必要な点として扱う。
```

---

## 4. 不確定項目（Phase 1 で詰める）

### 4.1 Phase 1 spike 計画

| spike | 実証内容 |
|---|---|
| **spike 05** | `CodexCLIAdapter(CustomLLM)` 実装（`complete` / `stream_complete` / `metadata` の最小実装、subprocess `claude --print --output-format json --json-schema ...` 経由）|
| **spike 06** | SchemaLLMPathExtractor 軽量 schema（5 entity / 6 relation）+ 日本語 prompt + 章アンカー抽出 + Section grounding / normalization（§2.4）|
| **spike 07** | vector_store の VECTOR_SOURCE_KEY 連結正規パターン（spike 03 の 0 件問題を解消）|
| **spike 08** | 章アンカー欠損章の LLM Agentic search フォールバック実装（§2.5）|
| **spike 09** | Concept (Core) 更新提案の (P) GRAG 経由 vs (Q) LLM 直接 の比較（§3.4）|
| **spike 10** | Classification LLM の 4 軸付与 prompt template + Orchestrator 側 NodeWithScore.metadata 後付けパイプライン（§3.2）|
| **spike 11** | Conflict 二段階 Validator 実装（段階 1 グラフ構造 + 段階 2 ルール + 段階 3 LLM 候補、§3.3）|
| **spike 12** | Hierarchical Cluster の retrieval 時動的算出（§3.5、`get_rel_map` traversal + spec-grag 側 clustering）|
| **spike 13** | InjectionContext 構造化出力（§3.1、ConstraintContext / TargetContext / ExclusionNotes / ConflictNotes / ReviewNotes へのフィールド振り分け）|

spike 05-09 は経路 1 / 2 を成立させる前提。spike 10-13 は経路 3 / 4 を成立させる前提。

### 4.2 LLM プロバイダー実装

- `CodexCLIAdapter(CustomLLM)` の実装（spike 05 で確定）
- 並列実行（`asyncio.gather` + `asyncio.Semaphore`）の設計
- timeout / 認証切れ / rate limit / 出力揺れの error handling
- LLM 用途別（Extraction / Classification / Answer）の設定切替
- Ollama generative LLM（B-1）と CodexCLIAdapter（B-2）のハイブリッド可能性（[SURVEY/13](SURVEY/13_path_b_design_options.md) §4 参照）

### 4.3 Concept (Core) 更新承認制 unified diff 生成

EXTERNAL_DESIGN.ja.md §3.4 の Core 更新候補生成プロセスを実装する。

- 候補生成方式: (P) GRAG 経由 vs (Q) LLM 直接（spike 09 で比較）
- diff ライブラリ選定（`difflib` 標準 / サードパーティ）
- diff の context_radius / unified format の出力規約
- ユーザー hunk 単位 accept / reject UX

### 4.4 spec-grag CLI 実装

- フレームワーク選定（Click / Typer / Fire 等）
- パッケージング（`pyproject.toml`、`uv` / `pdm` / `poetry` 等）
- 配布方式（PyPI / git clone / Docker）
- 設定ファイル schema（`.spec-grag/config.toml`）の strict validation

### 4.5 Cross-Encoder rerank（内部設計、必要時に追加）

retriever（PGRetriever / VectorContextRetriever）のスコアで cascade_candidates の関連度が正しく序列化できるかを spike 06 / 07 / 08 の retrieval 動作で評価する。不足が顕在化したら、日本語対応の cross-encoder reranker（例: BAAI/bge-reranker-v2-m3）を spike 14 として PGRetriever の後段に組み込む（R4「fusion / rerank は Orchestrator 側責務」と整合）。

### 4.6 vector retrieval の fallback

PGRetriever / VectorContextRetriever が機能しない / 0 件返す場合の fallback として、graph store の `get` / `get_rel_map` で keyword + property filter を組み合わせた retrieval を spec-grag Orchestrator 側で実装する。spike 07 で実証する。

---

## 5. 関連ドキュメント

### リポジトリ内（現行）

- [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md): 外部契約（**source of truth、不変**）
- [doc/SURVEY/SUMMARY.md](SURVEY/SUMMARY.md): Phase 0 / 0.5 完了レポート、案 A 破棄根拠、Native LlamaIndex GraphRAG Flow（旧名 案 B）採用
- [doc/SURVEY/13_path_b_design_options.md](SURVEY/13_path_b_design_options.md): 案 B サブパターン（B-1 / B-2 / B-3）+ ハイブリッド可能性
- [doc/SURVEY/01_*.md](SURVEY/) 〜 [12_*.md](SURVEY/): Phase 0 個別調査結果
- [doc/TODO.md](TODO.md): Phase 1 入り口の spike 計画（spike 05-13）
- [CLAUDE.md](../CLAUDE.md): リポジトリレベルの不変ルール（EXTERNAL_DESIGN.ja.md は不変、明示の改訂指示なしに変更しない）

### BAK/（pre-pivot のアーカイブ、参考のみ）

`BAK/` 配下に Rust + graphrag-rs 前提の旧実装。pivot 後は使わない。
