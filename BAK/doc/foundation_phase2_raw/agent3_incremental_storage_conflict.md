# Agent 3 — Incremental / Storage / Conflict 調査レポート

調査者: Agent 3 (Phase 2)
調査日: 2026-04-27
対象 vendor: `vendor/graphrag-rs/graphrag-core/`
担当 D 軸: D5 (Conflict 検出機構), D6 (章単位インクリメント), D7 (永続化粒度)

---

## 全体サマリ（先に読む）

| 観点 | 結論 |
|------|------|
| **Conflict detection の存在 (D5)** | **二値判定: 部分的に存在**。ただし「ノード属性の上書き戦略」レベルであり、spec-grag が求める「制約 vs 修正対象 / Source spec 同士 / Concept vs Source spec」という意味的矛盾検出は **存在しない**。 |
| **章単位インクリメント (D6)** | `IncrementalGraphManager` は **document-level の SHA-256 ハッシュ変更検出**を持つ。章単位は「document を章ファイル単位に分割して使う」ことで実現可能だが、graphrag-rs 自体は「章」概念を持たない。`auto_detect_changes` フラグ・`ChangeDetector::document_hashes` は機能する。Lazy Propagation の `apply_update` はプレースホルダで、Async Batch の `process_single_operation` も全部プレースホルダ。 |
| **永続化粒度 (D7)** | **全体一括が標準**。章別保存の仕組みは graphrag-rs に **存在しない**。Workspace 配下に `entities.parquet / relationships.parquet / chunks.parquet / documents.parquet / graph.json / metadata.toml` の 4-5 ファイル分割（**エンティティ別**であり**章別ではない**）。`save_state_async` は JSON 一括 + 文書別 tree.json。`load_state_async` は **存在しない**（save のみ）。VectorIndex (HNSW) は永続化メソッドを持たず、Lance を別途使う必要あり。 |

---

## M4. Conflict detection / Conflict resolution

### 入力

graphrag-rs には **2 つの異なる Conflict 概念**が並存する。

#### M4-A: `incremental/mod.rs::ConflictResolution` (シンプルな上書き戦略)

- 入力: 既存 `GraphNode` と新しい `NodeUpdate`
- 戦略 enum: `LatestWins` / `HighestConfidence` / `Merge` / `Manual`
- トリガ: `IncrementalGraphManager::update_node(node_id, NodeUpdate)`

#### M4-B: `graph/incremental.rs::ConflictResolver` (より構造化)

- 入力: `Conflict` struct
  - `conflict_id: UpdateId`
  - `conflict_type: ConflictType`
  - `existing_data: ChangeData`
  - `new_data: ChangeData`
  - `resolution: Option<ConflictResolution>`
- 戦略 enum (`ConflictStrategy`): `KeepExisting` / `KeepNew` / `Merge` / `LLMDecision` / `UserPrompt` / `Custom(String)`
- 矛盾種別 (`ConflictType`):
  - `EntityExists` — 同 ID のエンティティが既存
  - `RelationshipExists` — 同関係が既存
  - `VersionMismatch` — 期待 version と現状の不一致
  - `DataInconsistency` — グラフ状態と矛盾
  - `ConstraintViolation` — 制約違反

### 出力

#### M4-A
- `Result<()>`（更新成功/`GraphRAGError::IncrementalUpdate { Manual conflict resolution required }`）
- 副作用: ノードの label, attributes, embeddings が更新される

#### M4-B
- `Result<ConflictResolution>` { strategy, resolved_data, metadata }
- `ConflictResolution::resolved_data: ChangeData` が「採用された側のデータ」

### 内部処理（要点、実装行レベル）

#### M4-A: `incremental/mod.rs:538-598` (`update_node`)
```
LatestWins:        node.attributes.extend(attrs)  // 上書き
HighestConfidence: コメントのみ（実装空）
Merge:             node.attributes.entry(k).or_insert(v) // 既存を保持
Manual:            return Err(...)
```
**重要**: `HighestConfidence` の中身は空（line 559-562）。confidence 比較のロジック未実装。

#### M4-B: `graph/incremental.rs:662-688` (`ConflictResolver::resolve_conflict`)
```
KeepExisting / KeepNew: 単純コピー
Merge:                  merge_conflict_data()
Custom:                 登録済 resolver を呼ぶ
LLMDecision/UserPrompt: "Conflict resolution strategy not implemented" エラー
```
- `merge_entities` (line 721-748): confidence 高い方を優先、mentions を重複排除して結合、embedding を上書き。
- `merge_relationships` (line 750-773): 同様に confidence 高い方優先、context を重複排除結合。
- **LLMDecision / UserPrompt は未実装**（line 684-686 でエラー返却）。

#### M4-B: `validate_consistency` (line 2494-2537)
- orphaned entities（関係なしエンティティ）と broken relationships（存在しないエンティティを参照）と missing_embeddings のみ検出
- **意味的矛盾（spec 同士の矛盾、Concept vs spec）は一切検出しない**

### 典型 use case

- M4-A: `auto_detect_changes` が true で、同 doc id を再アップロードした際、既存 node の attribute をどう上書きするか決める
- M4-B: 並行更新で同じ entity_id に違うデータを書こうとしたとき、merge/keep を選ぶ

### 他機能との連携

- M4-A は `IncrementalGraphManager` が単独で使う。`apply_incremental_update` (line 871-920) で `find_similar_entity` → `update_node` の流れで起動。
- M4-B は `IncrementalGraphStore` trait の batch_upsert_entities/relationships の引数に渡す（戦略のみ）。実際の検出は trait 実装側に委ねられる。

### 実装ファイル

- `vendor/graphrag-rs/graphrag-core/src/incremental/mod.rs` (M4-A)
  - line 162-187: `enum ConflictResolution`
  - line 547-577: `update_node` 内の戦略適用
- `vendor/graphrag-rs/graphrag-core/src/graph/incremental.rs` (M4-B)
  - line 240-296: `ConflictStrategy`, `Conflict`, `ConflictType`, `ConflictResolution`
  - line 634-774: `ConflictResolver` 実装
  - line 2494-2537: `validate_consistency`
- `vendor/graphrag-rs/graphrag-core/src/core/error.rs:182-185`: `GraphRAGError::ConflictResolution`

### ライセンス・出典
graphrag-rs (vendored, Apache-2.0/MIT 想定; LICENSE は別途確認要)

### 確認できなかった点

- `HighestConfidence` ブランチの「confidence 比較を実際に行う」コードはどこにあるのか。コメントだけで未実装の可能性が高い。
- `ConflictType::DataInconsistency` / `ConstraintViolation` の検出ロジックがどこに存在するか。`Conflict` struct を生成しているコードを `IncrementalGraphStore` trait の各実装が持つ必要があるが、**この trait の実装は graphrag-rs 内に確認できなかった**（`async_trait` の skeleton はあるが、具体的な検出処理が trait 利用者側に委ねられている）。

### D5/D6/D7 への寄与

- **D5 (分類・矛盾検出メカニズム)**:
  - graphrag-rs の Conflict は **構造的矛盾**（同 ID 衝突、broken refs）に限定。spec-grag の `ConflictNotes` が要求する 3 種は **すべて意味的矛盾**:
    1. 制約 spec vs 修正対象 spec (e.g.「サーバ側のみ」と「クライアント呼び出し」)
    2. Source specs 同士の矛盾
    3. Concept (集約定義) vs Source specs の矛盾
  - graphrag-rs の `ConflictResolver` をそのまま流用しても、これらは検出できない。
  - 検出ロジックは **spec-grag 独自実装が必須**（LLM ベース推論 or ルールベース or グラフトラバース）。
  - ただし `ConflictResolution::Manual` ブランチや `ConflictType::DataInconsistency` の構造は **検出後の "保留" レポートには再利用可能**。

- **D6 (章単位インクリメント)**:
  - 直接寄与せず（M4 は ConflictType の話、章単位は M7 の話）

- **D7 (永続化粒度)**:
  - 直接寄与せず

### 設計判断への含意

- **そのまま使えない**: 仕様の意味的矛盾検出は graphrag-rs に実装が無い。
- **構造を借用する価値はある**:
  - `Conflict { existing_data, new_data, resolution: Option<...> }` の構造体形状
  - `ConflictType` の分類列挙
  - `ConflictResolution { strategy, resolved_data, metadata }` の出力形状
  - これらを spec-grag の `ConflictNotes` schema として参考にできる
- **改造方針**: spec-grag は LLM/ルールで意味的矛盾を検出 → `Conflict`-like struct でレポート → `ConflictNotes` として `InjectionContext` に注入。

---

## M7. IncrementalGraphManager の章単位インクリメント挙動

### 入力

#### `IncrementalConfig` (incremental/mod.rs:85-140)
```rust
auto_detect_changes: bool,           // デフォルト true (SHA-256 でドキュメント変更を検出)
min_entity_confidence: f32,          // デフォルト 0.7
max_batch_size: usize,               // デフォルト 1000
parallel_updates: bool,              // デフォルト true
conflict_resolution: ConflictResolution,
enable_lazy_propagation: bool,       // デフォルト true
lazy_propagation_threshold: usize,   // デフォルト 100
enable_delta_computation: bool,      // デフォルト true
delta_use_bloom_filter: bool,        // デフォルト true
```

#### `add_content` (line 494-535) の入力
```rust
DocumentContent {
    id: String,        // 変更検出キー
    text: String,
    metadata: HashMap<String, String>,
}
```

### 出力

```rust
UpdateSummary {
    nodes_added/updated/removed: usize,
    edges_added/updated/removed: usize,
    time_taken_ms: u64,
}
```

### 内部処理（要点、実装行レベル）

#### 変更検出 (line 841-860)
```rust
fn has_content_changed(&self, content) -> bool {
    if !auto_detect_changes { return true; }
    let hash = SHA-256(content.text);
    self.change_detector.read().document_hashes.get(&content.id) != hash
}
```
- **キー = `content.id`、ハッシュ対象 = `content.text` 全体**
- 章単位にしたい場合、spec-grag 側で「章 = 1 DocumentContent」として登録すれば章単位ハッシュは効く。

#### Lazy Propagation の実態 (lazy_propagation.rs:470-477)
```rust
fn apply_update(&self, _update: &PendingUpdate) -> Result<()> {
    // This is a placeholder. In real implementation, this would:
    // 1. Modify the actual graph structure
    // 2. Update any dependent computations
    // 3. Propagate changes to dependent nodes (if enabled)
    Ok(())  // ★ 空実装
}
```
**Phase 1 の発見と完全に一致**。これに依存している `propagate_pending_updates` (line 379-468) は dirty tracker の clear と stats 更新のみ実行する状態。

#### Async Batch の実態 (async_batch.rs:536-564)
```rust
fn process_single_operation(operation) -> Result<(), String> {
    match operation_type {
        AddNode => Ok(()),  // ← graph.add_node(...) のコメントのみ
        UpdateNode => Ok(()),
        ...全部 Ok(()) を返すだけ
    }
}
```
**Async Batch も全プレースホルダ**。throughput stats は計算されるが実グラフは更新されない。

#### Delta Computation (delta_computation.rs)
- `compute_delta(before, after)` (line 308-354): 2 つの `GraphSnapshot` を比較
- node 比較: `NodeSnapshot.content_hash` が違えば `NodeModification`、なければ無変更
- bloom filter: snapshot.nodes/edges のキーを bloom に入れて、新 snapshot の各キーが旧 bloom に無ければ即「added」と判定（false positive rate 1%）
- parallel: rayon の `par_iter().partition_map`
- **これは実装されている**（プレースホルダではない）

#### ChangeDetector (mod.rs:430-438)
```rust
struct ChangeDetector {
    document_hashes: HashMap<String, String>,  // 機能する
    entity_versions: HashMap<String, u32>,     // dead code (#[allow(dead_code)])
}
```

### 典型 use case

```rust
let mut mgr = IncrementalGraphManager::new(IncrementalConfig::default());
mgr.add_content(&DocumentContent { id: "ch01.md", text: "...", metadata: ... })?;
// ch01.md を編集
mgr.add_content(&DocumentContent { id: "ch01.md", text: "新内容", metadata: ... })?;
// → has_content_changed: true → extract_from_content → apply_incremental_update
// ただし extract_from_content も中身は空 (line 862-869: 常に entities=[] を返す)
```

### 章別 ChapterAnchor / ERG / Hierarchical Cluster の自動更新

- **graphrag-rs に ChapterAnchor は存在しない**（grep 0 件）
- **HierarchicalCluster の自動再構築は incremental には組み込まれていない**:
  - `IncrementalGraphManager` は `KnowledgeGraph` を持たず、独自の `DiGraph<GraphNode, GraphEdge>` を持つ（line 47-48）
  - つまり incremental 側で動かしても hierarchical clustering モジュールは触らない（別系統）
- **章ファイル変更時に何が自動更新されるか**:
  - `ChangeDetector::document_hashes` の該当エントリ
  - `IncrementalGraphManager` 内部の `DiGraph` ノード/エッジ（ただし実装空のため実質無更新）
  - **HierarchicalCluster / Concept / ERG の再構築は別途 spec-grag 側で叩く必要がある**

### 他機能との連携

- `IncrementalGraphManager` は `KnowledgeGraph` (graphrag-core の中心型) と **別の独自グラフ**を持つ。両者の同期方法は提供されていない。
- `validate_consistency` は `graph/incremental.rs::IncrementalGraphStore` trait のもので、`IncrementalGraphManager` には存在しない。

### 実装ファイル

- `vendor/graphrag-rs/graphrag-core/src/incremental/mod.rs` 全 1219 行
- `vendor/graphrag-rs/graphrag-core/src/incremental/lazy_propagation.rs` 全 655 行
- `vendor/graphrag-rs/graphrag-core/src/incremental/delta_computation.rs` 全 700+ 行
- `vendor/graphrag-rs/graphrag-core/src/incremental/async_batch.rs` 全 593 行+
- `vendor/graphrag-rs/graphrag-core/src/graph/incremental.rs` (別系統、IncrementalGraphStore trait 中心、~3000 行)

### ライセンス・出典
graphrag-rs (vendored)

### 確認できなかった点

- `extract_from_content` (mod.rs:862-869) が常に空を返すため、production で実際に entity 抽出するためには別の経路が必要。どの経路から呼ぶのが正しいか未確認。
- `IncrementalGraphManager` の独自 `DiGraph` と `KnowledgeGraph` の bridge コードがあるかどうか。grep 範囲を広げる必要あり。
- `graph/incremental.rs::IncrementalGraphStore` trait の **具体的実装** (impl) が存在するか。trait 定義のみで impl が見当たらなかった。

### D5/D6/D7 への寄与

- **D5**: validate_consistency が orphan/broken のみで不十分なことを示す（M4 と同じ結論）
- **D6 (章単位インクリメント) — 中核データ**:
  1. **章単位の変更検出は SHA-256 ベースで実用可能**: `DocumentContent::id` を `chapter_path` (e.g. `"specs/01-overview.md"`) にすればよい
  2. **Lazy Propagation は使えない**: `apply_update` がプレースホルダ → 章別 ChapterAnchor 更新を Lazy 経由で行うのは不可。`enable_lazy_propagation: false` 推奨。
  3. **Async Batch も実装空**: 章ファイル一括処理は Async Batch ではなく rayon 直接 or spec-grag 自前のループが必要
  4. **Delta Computation は使える**: snapshot 比較は実装済。章別 GraphSnapshot を取って差分計算する方式は機能する
  5. **ChapterAnchor / ERG / Hierarchical Cluster の自動更新ナシ**: これらの再構築は spec-grag 側で章単位にトリガする必要がある
- **D7**: 直接寄与せず

### 設計判断への含意

- **章単位の変更検出は graphrag-rs の `ChangeDetector` をそのまま使える**（document_id を chapter_path にマッピング）
- **Lazy Propagation / Async Batch は使えない（プレースホルダ）**: これに依存する設計をすると Phase 3 で詰む。spec-grag 側で同期 or 自前 async で実装する必要あり
- **章別 ChapterAnchor / ERG / Hierarchical Cluster の自動更新は graphrag-rs に存在しない**: spec-grag が自前で「変更された章 → 該当 chapter anchor 再生成 → 当該 anchor を含む cluster 再計算」のオーケストレーションを書く必要がある
- **Delta Computation は活用できる**: 「章 ch01 のスナップショット」を保存しておき、新版との diff から impacted entities を絞り込む用途で使える

---

## M8. save_state_async / load_state_async / 永続化粒度

### 入力

#### Workspace 経路 (`persistence/workspace.rs`)
```rust
WorkspaceManager::new(base_dir)?
  .save_graph(&graph: &KnowledgeGraph, workspace_name: &str) -> Result<()>
  .load_graph(workspace_name: &str) -> Result<KnowledgeGraph>
```

#### Async 経路 (`async_graphrag.rs:481-503`)
```rust
async fn save_state_async(&self, output_dir: &str) -> Result<()>
```
- **`load_state_async` は存在しない**（grep 0 件）

#### Parquet 経路 (`persistence/parquet.rs`)
```rust
ParquetPersistence::new(base_dir)?
  .save_graph(&graph) -> Result<()>
  .load_graph() -> Result<KnowledgeGraph>
```

#### Lance 経路 (`persistence/lance.rs`)
```rust
LanceVectorStore::new(path, config).await?
  .store_embedding(id, embedding).await?
  .search_similar(query, k).await?
```

### 出力（ファイル構成）

#### WorkspaceManager (`workspace.rs`) — `.spec-grag/graph/` の素直な対応先
```
<base_dir>/
└── <workspace_name>/
    ├── graph.json           # 常に作成（fallback）— entities/relationships/chunks/documents 全部入り 1 ファイル
    ├── entities.parquet     # feature = "persistent-storage" 時
    ├── relationships.parquet
    ├── chunks.parquet
    ├── documents.parquet
    └── metadata.toml        # WorkspaceMetadata (counts, format_version, timestamps)
```

#### Lance (`lance.rs`)
```
<path>/                       # LanceVectorStore のパス
└── (lance columnar files)   # 内部はテーブルとして管理
```

#### `save_state_async` 出力
```
<output_dir>/
├── async_knowledge_graph.json    # KnowledgeGraph 全体 1 ファイル (line 490)
└── <doc_id>_async_tree.json      # ドキュメントごとのツリー (line 495-499)
```

### 内部処理（要点、実装行レベル）

#### `WorkspaceManager::save_graph` (workspace.rs:198-229)
1. `workspace_path/graph.json` に `KnowledgeGraph::save_to_json` で **JSON 一括保存**
2. feature = "persistent-storage" なら `ParquetPersistence::save_graph` で 4 ファイル別保存
3. metadata.toml を更新

#### `WorkspaceManager::load_graph` (workspace.rs:232-264)
1. **Parquet を最初に試す**（feature ON 時）
2. 失敗時は graph.json fallback
3. **章別ロードはサポートされていない**（workspace 単位のみ）

#### `KnowledgeGraph::save_to_json` (core/mod.rs:649-)
- 1 つの JSON に entities/relationships/chunks/documents 全部入れる
- **embedding は保存されない**（load 時 `embedding: None` で復元、line 539, 572, 611）

#### `ParquetPersistence::save_graph` (parquet.rs:143-163)
- 4 ファイル分割: entities / relationships / chunks / documents
- **章別ではなくエンティティ種別での分割**
- Snappy 圧縮（デフォルト、line 92）
- row_group_size: 10000

#### `save_state_async` (async_graphrag.rs:481-503)
```rust
graph.save_to_json("{output_dir}/async_knowledge_graph.json")?;  // 全体 1 ファイル
for (doc_id, tree) in document_trees {
    fs::write("{output_dir}/{doc_id}_async_tree.json", tree.to_json()?)?;
}
```
- **document tree は doc_id ごとに別ファイル** ← 章別保存に近い唯一の場所
- ただし graph 本体は 1 ファイル

#### `LanceVectorStore` (lance.rs)
- 永続化のみ（ディスクパスを最初から渡す）
- `store_embedding(id, embedding)` で個別 upsert 可能
- HNSW / IVF / Flat の各 index タイプ対応

#### `VectorIndex` (vector/mod.rs)
- `instant_distance::HnswMap` を内部に持つ（line 67）
- **save / load メソッドは存在しない**: メモリ上でのみ動作。プログラム再起動時は embedding を再投入して `build_index()` 必要
- VectorStore trait (store.rs) も `initialize / add_vector / search / delete` のみ。永続化メソッドなし

### 典型 use case

#### Pattern A: シンプル (JSON のみ)
```rust
let workspace = WorkspaceManager::new("./.spec-grag/graph")?;
workspace.save_graph(&kg, "main")?;       // graph.json + metadata.toml
let kg = workspace.load_graph("main")?;   // graph.json から復元（embedding 失われる）
```

#### Pattern B: Parquet + Lance（推奨）
```rust
// 構造データ
let parquet = ParquetPersistence::new(PathBuf::from("./.spec-grag/graph"))?;
parquet.save_graph(&kg)?;

// embedding
let lance = LanceVectorStore::new(PathBuf::from("./.spec-grag/graph/vectors.lance"), config).await?;
for entity in kg.entities() {
    if let Some(emb) = &entity.embedding {
        lance.store_embedding(entity.id.as_str(), emb.clone()).await?;
    }
}
```

### 他機能との連携

- `IncrementalGraphManager` 内部のグラフは `KnowledgeGraph` ではないため、`WorkspaceManager` でそのまま保存できない。bridge コードが必要。
- `HierarchicalCluster` の永続化は `KnowledgeGraph` のフィールドに含まれていれば JSON/Parquet に乗るが、別途 hierarchical_clustering モジュールに保存パスがあるか未確認。

### 実装ファイル

- `vendor/graphrag-rs/graphrag-core/src/persistence/mod.rs` 全 84 行（trait + 再エクスポート）
- `vendor/graphrag-rs/graphrag-core/src/persistence/workspace.rs` 全 369 行
- `vendor/graphrag-rs/graphrag-core/src/persistence/parquet.rs` 全 1100+ 行（schema 定義含む）
- `vendor/graphrag-rs/graphrag-core/src/persistence/lance.rs` 全 530+ 行
- `vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs:481-503` (`save_state_async`)
- `vendor/graphrag-rs/graphrag-core/src/core/mod.rs:498-646` (`save_to_json` / `load_from_json`)
- `vendor/graphrag-rs/graphrag-core/src/vector/mod.rs:65-200` (`VectorIndex`、永続化なし)

### ライセンス・出典
graphrag-rs (vendored)

### 確認できなかった点

- `HierarchicalCluster` がどこに保存されるか（KnowledgeGraph フィールドに含まれるなら parquet で保存される、別なら未保存）。`hierarchical_clustering` モジュールの永続化を未調査。
- `save_state_async` に対応する `load_state_async` が無い理由（実装漏れか、設計上の意図か）。
- `VectorIndex` の HNSW を再ビルドせず persistent にする方法（instant_distance crate 自体に save/load があるか未調査）。

### D5/D6/D7 への寄与

- **D5**: 直接寄与せず
- **D6**: parquet/lance はディスク永続化対応のため章単位ファイルを書ける可能性はあるが、現行 schema は entity/relationship/chunk/document 軸の **column 分割**で、**章 axis は無い**。spec-grag が章別ファイルを作りたいなら自前で章 ID を column に追加するか、章別 workspace を作る必要がある。
- **D7 (永続化 / ロード粒度) — 中核データ**:
  1. **graphrag-rs の標準は「全体一括」**: workspace 単位、graph 単位、document tree 単位での保存は可能だが「章単位」は標準サポートされない
  2. **章別ファイル構成にしたい場合の方法**:
     - (a) workspace を章ごとに切る（`./.spec-grag/graph/<chapter_id>/`）— overhead 大、cluster の global view が崩れる
     - (b) 単一 workspace で章別 sub-Parquet を独自に書く（spec-grag が schema 拡張）
     - (c) graphrag-rs の標準 workspace + spec-grag が章別 anchor index を別ファイルで管理
  3. **embedding は別管理必須**: JSON は embedding を保存しない。Parquet 標準 schema も embedding を含まない（要確認）。Lance を使うのが正解
  4. **`load_state_async` 不存在**: async での復元は spec-grag が自前で `WorkspaceManager::load_graph` を呼ぶ必要あり

### 設計判断への含意

- **`.spec-grag/graph/` の素直な構成**:
  ```
  .spec-grag/graph/
  ├── workspace/main/
  │   ├── graph.json or entities.parquet ...
  │   └── metadata.toml
  ├── vectors.lance/         # Lance for embeddings
  ├── chapter_index.json     # spec-grag 独自: chapter_id → entity_ids
  └── concept_index.json     # spec-grag 独自: concept_name → source spec ids
  ```
- **章単位ロードは graphrag-rs に頼れない**: spec-grag 側で章別 anchor index を別管理し、必要な章のみメモリにロードするオーケストレーションが必要
- **Lazy Propagation / Async Batch がプレースホルダのため**、章単位の inkremental 更新で「章 N 個変更 → N 回 add_content → graph 再保存」というシンプルな fullsync が、現実的には最も安全
- **embedding 永続化は Lance 推奨**（HNSW VectorIndex は再ビルド必須のため起動コスト大）
- **`save_state_async` と `WorkspaceManager` を併用すると同じデータが二重保存になる** ため、どちらか一方を採用する設計判断が必要

---

## 全体の Phase 1 発見との関係

| Phase 1 の発見 | M4/M7/M8 での確認 |
|---|---|
| `Lazy Propagation::apply_update` がプレースホルダ | **再確認**（lazy_propagation.rs:470-477）。章別 ChapterAnchor 更新には使用不可 |
| Async Batch がプレースホルダ | **新発見**（async_batch.rs:536-564 で全 OperationType が `Ok(())` のみ） |
| Conflict Resolution がドキュメントに記載 | **存在は事実だが「ノード上書き戦略」レベル**で意味的矛盾検出ではない |

---

## 親への報告用要点（参考）

- M4/M7/M8 すべて完了
- Conflict detection: **graphrag-rs に「構造的衝突」は存在するが、spec-grag の意味的矛盾（spec 同士、Concept vs spec）は存在せず → 独自実装必須**
- 永続化: **全体一括が標準。章別保存は graphrag-rs に存在せず。`.spec-grag/graph/` は workspace 経由で全体保存 + 章別 index を spec-grag が自前管理する設計が現実的**
- 章単位 SHA-256 変更検出は機能する（`DocumentContent::id` に章パスを使えばよい）
- Lazy Propagation / Async Batch はプレースホルダのため依存禁止
