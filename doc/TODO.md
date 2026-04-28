# spec-grag 作業手順 / フェーズ管理

本書は spec-grag の **作業手順とフェーズ管理** を記録する。仕様書（DESIGN.ja.md）や外部契約（EXTERNAL_DESIGN.ja.md）とは別に、「次にやるべき作業」と「フェーズ進行」を一元管理する。

## 設計手順の原則

```
1. 調査
   - GraphRAG / LlamaIndex の機能・限界・典型利用シーケンスを実装レベルで把握
   - 公式 docs / GitHub 確認だけでは不十分。最小実行スパイク（Phase 0.5）で挙動を実証
   - 調査成果物は固定フォーマットで記録(要約だけでは判定とみなさない)
   - 確認できなかった項目は unknown のまま残す（推測で埋めない）
   - CLAUDE.md ルール 1, 2, 3, 5 に従う

2. 仮分担と方式フローの策定
   - 調査結果を元に、役割分担と内部フローを仮策定
   - 「仮」「暫定」と書く（CLAUDE.md ルール 4）

3. 根幹処理のレビュー
   - ユーザーレビューを受ける、矛盾・欠落・誤解を洗い出す

4. 設計書へ反映
   - レビュー承認後に DESIGN.ja.md §1 を更新（「仮」を「決定」に昇格、または再分配）
   - 検証した version / commit を pin して記録（latest を根拠に設計確定しない）
   - 一巡したら次のフェーズへ
```

**重要**: 調査前に役割分担を「決定」と書かない。CLAUDE.md ルール 7「実装より先に役割分担を考える」は **調査が完了した上での役割分担の確定** を意味する。

---

## 調査成果物フォーマット（Phase 0 の各項目に必須）

各調査項目は必ず以下の形式で記録する。要約だけでは判定とみなさない。

```markdown
### 調査対象
- component:
- version / commit:
- source:
  - official docs:
  - GitHub source:
  - 実行確認: (Phase 0.5 のスパイクファイル名)

### 確認した API
- import path:
- constructor:
- main methods:
- input:
- output:
- persist / reload:
- delete / update:

### 実測・検証結果
- 最小コードで動いたこと:
- 動かなかったこと:
- エラー:
- 期待と違った点:

### spec-grag への影響
- DESIGN §1 の仮分担を維持できるか:
- 再分配が必要な責務:
- 未解決事項:

### 判定
usable / usable_with_wrapper / risky / unusable / unknown
```

「雰囲気として使えそう」「公式 docs にこう書いてある」だけで判定しない。最小実行で実測したか、実証できなかった場合は `unknown` のまま残す。

---

## version pin 方針

- Phase 0 調査では latest docs / latest GitHub を確認する
- Phase 1 以降の設計確定は、実際に検証した package version / commit に固定する
- DESIGN.ja.md には以下を記録する：
  - `llama-index-core` version
  - property graph 関連の import path
  - 検証 commit / release
  - 検証日
  - 破壊的変更が起きた場合の再調査範囲

「latest」を根拠に設計確定しない。設計の根拠は検証したバージョンに固定する。

---

## 恒久プロパティ vs transient annotation の境界

調査・設計・実装すべての段階で以下の境界を守る：

| 種別 | 例 | 保持先 |
|---|---|---|
| **恒久プロパティ**（graph node / relation のメタデータとして永続化） | document_id / section_id / heading_path / source_span / source_hash / concept_id / approval_status / evidence / created_at / updated_at | graph store（SimplePropertyGraphStore 等）|
| **transient annotation**（課題ごとに変動する評価） | constraint_relevance / target_relevance / semantic_conflict_candidate / review_required / ranking_score / reason_for_current_task | retrieval result / InjectionContext / RealignResult のみ（graph には永続化しない）|

理由：同一の Concept / Source spec が課題ごとに「制約 / 修正対象 / 無関係」と異なる評価を取る（EXTERNAL_DESIGN.ja.md §5.4）。4 軸評価を graph の恒久プロパティに書くと、別の課題で再利用したときに不正な評価が混入する。

---

## 現在のフェーズ

**Phase 0 + Phase 0.5 進行中**（2026-04-28）

DESIGN.ja.md §1.1〜§1.3, §1.5〜§1.9 はすべて **仮分担**。§4.1 LlamaIndex 表面マップ調査完了後にレビュー → 確定する。

進捗の状態凡例（各項目の sub-bullet で使用）:

| マーク | 意味 |
|---|---|
| `✓` | その手段で確認・実証済 |
| `☐` | その手段では未確認・未実証 |
| `—` | その手段は該当しない（例: Ollama embedding に GitHub source 直接読みは不要）|

判定は **spike まで含めて確認できたら usable** にする。WebFetch / GitHub source のみで「usable」と書かない（CLAUDE.md ルール 2）。spike が残っていれば判定は `usable_with_wrapper` か `partially usable` 止まり。

`§1.4 採用方針（決定済）`（Python + LlamaIndex 系エコシステム + ローカル・ファイルベース永続化 + Claude/Codex CLI + Ollama embedding）のみ pivot で確定済。

---

## 次のアクション（優先順）

### Phase 0：表面マップ調査（最優先、§4.1）

調査方法：WebFetch + GitHub の最新版コード確認 + 上記「調査成果物フォーマット」で記録（推論カットで埋めない、CLAUDE.md ルール 2 に従う）。

各項目について「調査対象 / 確認した API / 実測・検証結果 / spec-grag への影響 / 判定」を埋める。実測は Phase 0.5 と並行する。

**前提（決定、DESIGN.ja.md §1.4）**: 生成系 LLM は **サブスク認証 Claude/Codex CLI を subprocess external reasoning/extraction worker として扱う**。embedding は **Ollama nomic-embed-text** をローカル embedding model として採用。LlamaIndex `LLM` interface への直接組込は Phase 0 では前提にしない。Phase 0 では DESIGN.ja.md §4.1 の **案 A / B / C** のどの統合方式が現実的かの判断材料を取る。

判定は **spike まで含めて確認できたら usable**。spike が未済の項目は WebFetch / GitHub のみの判定にとどめる。

検証環境（version pin、2026-04-28 時点）: `llama-index-core==0.14.21`、`llama-index-embeddings-ollama==0.9.0`、Python 3.12.3、Ollama 0.21.2、Claude CLI 2.1.119、Codex CLI 0.93.0。詳細は [doc/SURVEY/index.md](SURVEY/index.md)。

#### 状態一覧

| # | 項目 | WebFetch | GitHub | Spike | 現判定 | spike 未済の残作業 |
|---|---|---|---|---|---|---|
| 01 | PropertyGraphIndex の API 安定度 | ✓ | ☐ | ☐ | usable_with_wrapper | PropertyGraphIndex 構築自体の動作確認（spike 02 予定） |
| 02 | SchemaLLMPathExtractor (2a-2f) | ✓ | ✓ | 部分 | partially usable（A/C 確定、B/2c 未済）| 2c の strict=True 違反時の LLM 挙動、2a の `LLM` subclass wrapper 動作（Phase 1 / 実装時に詰める）|
| 03 | SimplePropertyGraphStore 永続化粒度 | ✓ | ✓ | ✓ | **usable** | （実証済、`store.delete()` は使わず safe wrapper 経由）|
| 04 | incremental update 方式 | ✓ | ✓ | ✓ | usable_with_wrapper | safe_delete_by_section wrapper を spec-grag 側で実装する責務（spike 01 で動作確認済）|
| 05 | HybridRetriever / PGRetriever fusion | ✓ | ✓ | ☐ | usable_with_wrapper | PGRetriever / VectorContextRetriever の検索動作（spike 03 予定）|
| 06 | HippoRAG / LightRAG | ✓ | — | — | not_present_in_lpg_guide | spec-grag MVP 除外、spike 不要 |
| 07 | 恒久プロパティの metadata 保持 | ✓ | ✓ | ✓ | **usable** | retrieval result（NodeWithScore）に properties が乗るかは未確認（spike 03 予定）|
| 08 | transient annotation の実装パターン | ☐ | ☐ | ☐ | unknown | NodeWithScore.metadata に 4 軸後付けの動作確認（spike 03 予定）|
| 09 | /spec-core --all 全再構築 | ☐ | ☐ | ☐ | unknown | persist_dir 削除 + 再構築の動作確認（spike 02 予定）|
| 10 | /spec-core incremental stale 除去 | ✓ | ✓ | ✓ | usable_with_wrapper | safe_delete_by_section wrapper を spec-grag 側で実装する責務（spike 01 で動作確認済）|
| 11 | Ollama embedding 接続 | ✓ | — | ✓ | **usable** | （実証済、dim=768、JP/EN OK）|
| 12 | Claude/Codex CLI subprocess | ✓ (CLI help) | — | ☐ | partially usable | 実呼び出しでの JSON 出力 / 出力揺れ / 認証切れ動作（spike 04 予定）|

#### 各項目の確認状況詳細

- [ ] **項目 01**: `PropertyGraphIndex` の API 安定度
  - WebFetch ✓: `from_documents` / `from_existing` / `insert` / `insert_nodes` / `storage_context.persist` / `load_index_from_storage` の API シグネチャ
  - GitHub ☐: v0.14 系の breaking change 頻度（release notes 未確認）
  - Spike ☐: PropertyGraphIndex を実際に構築・動作させていない（spike 01 では SimplePropertyGraphStore のみ）→ **spike 02 で実証予定**

- [ ] **項目 02**: `SchemaLLMPathExtractor` の制約強度と統合方式（DESIGN §4.1 の 2a〜2f）
  - **2a** LlamaIndex `LLM` interface 要求 — 案 B の前提
    - GitHub ✓: `llm: LLM` 必須引数、subprocess wrapper を `LLM` subclass で実装する設計が必要
    - Spike ☐: 実装と動作確認は Phase 1 / 実装着手時
  - **2b** スキーマ受理形式
    - GitHub ✓: `Literal[...]` + `List[Triple]` + `kg_schema_cls`、内部で `create_model` + `field_validator`
    - Spike ☐: 実投入動作は Phase 1
  - **2c** `strict=True` 違反時の挙動
    - GitHub ✓: `strict=True` で pydantic Literal 型強制 → 範囲外は ValidationError
    - Spike ☐: **LLM が違反 JSON を返した場合のリトライ / エラー伝播**は未実証 → Phase 1
  - **2d** 事前抽出済み triplet 投入 — 案 A の前提
    - WebFetch ✓ + Spike ✓: `graph_store.upsert_nodes` / `upsert_relations` で動作確認済（spike 01）
  - **2e** `kg_extractors` 独自 extractor 受理 — 案 C の前提
    - WebFetch ✓: list 受理、`TransformComponent` 継承
    - Spike ☐: 独自 extractor の動作確認は実装着手時
  - **2f** LLM 不要 extractor の存在
    - GitHub ✓: `ImplicitPathExtractor` 存在
    - Spike ☐: 用途範囲（どんな relation を読めるか）は未実証

- [ ] **項目 03**: `SimplePropertyGraphStore` の永続化粒度
  - WebFetch ✓ + GitHub ✓ + Spike ✓: JSON 永続化、`to_dict` / `from_dict`、in-memory + persist、delete は多軸 filter
  - 注意: **`store.delete()` は破綻するため使わない**（spike 01 で確認）

- [ ] **項目 04**: incremental update 方式
  - WebFetch ✓ + GitHub ✓ + Spike ✓: `delete(properties=...)` の cascade で section_a の entity を巻き込む問題を spike で確認
  - 対処: **safe_delete_by_section** wrapper を spec-grag 側で実装する責務（spike 01 で動作実証）

- [ ] **項目 05**: PGRetriever fusion 戦略
  - WebFetch ✓ + GitHub ✓: `PGRetriever._retrieve` は単純結合 + テキスト dedup、RRF / Weighted / CombSum / MaxScore は LlamaIndex 標準にない
  - Spike ☐: 実際の検索動作（VectorContextRetriever / PGRetriever）→ **spike 03 で実証予定**

- [ ] **項目 06**: HippoRAG / LightRAG retrieval 統合可否
  - WebFetch ✓: lpg_index_guide ページに記載なし
  - 結論: spec-grag MVP では除外（spike 不要）

- [ ] **項目 07**: 恒久プロパティ metadata
  - WebFetch ✓ + GitHub ✓ + Spike ✓: `properties: Dict[str, Any]` free-form、persist 後 reload で完全保持（日本語 OK、spike 01）
  - Spike ☐: **retrieval result に properties が乗るか**は未確認 → spike 03 で実証

- [ ] **項目 08**: transient annotation の実装パターン
  - WebFetch ☐ / GitHub ☐ / Spike ☐
  - 設計仮説: `NodeWithScore.metadata` に 4 軸（constraint_relevance 等）を後付け
  - **spike 03 で動作確認予定**

- [ ] **項目 09**: `/spec-core --all` 全再構築の API 挙動
  - WebFetch ☐ / GitHub ☐ / Spike ☐
  - 設計仮説: `shutil.rmtree(persist_dir)` + `os.makedirs` + 再構築 + `persist`
  - **spike 02 で動作確認予定**

- [ ] **項目 10**: `/spec-core incremental` stale 除去整合
  - WebFetch ✓ + GitHub ✓ + Spike ✓: spike 01 で safe_delete_by_section wrapper の動作を確認、章 A 完全保存 / 章 B 完全消去 / triplets 整合
  - 判定根拠は項目 04 と同一

- [ ] **項目 11**: Ollama embedding 接続
  - WebFetch ✓ + Spike ✓: import / instantiate / get_text_embedding / dim=768 / 日本語 OK（spike 00）
  - Spike ☐: PropertyGraphIndex / VectorContextRetriever への注入経路は未確認 → spike 02/03 で実証

- [ ] **項目 12**: Claude/Codex CLI subprocess 最小確認
  - CLI help ✓: 両 CLI で structured output 対応（Claude `--json-schema`、Codex `--output-schema`）
  - Spike ☐: 実呼び出し / JSON 出力 / 出力揺れ / 認証切れ / レート制限の挙動 → **spike 04 で実証予定**

### Phase 0.5：最小実行スパイク（Phase 0 の各項目を実コードで確認）

Phase 0 は WebFetch / GitHub 確認だけでは「素材を触った」と言えない。toy documents で実行確認する。スパイクコードは `spike/` 配下に保存し、調査成果物の `source.実行確認` に記録する。

#### Phase 0.5 spike 計画（spike file 単位の進捗管理）

Phase 0 の各項目を実証するための spike file 計画を以下に固定する。**Phase 0.5 完了の判定はこの spike 計画の完了で決める**（部品スパイクのチェックリスト項目ではなく spike file 単位で進捗管理）。

| # | spike file | ステータス | 実証する Phase 0 項目 | 内容 | 優先順 |
|---|---|---|---|---|---|
| 00 | `spike/00_smoke_ollama_embedding.py` | ✓ 完了 | 11 | `OllamaEmbedding` import / instantiate / `get_text_embedding` / dim=768 / JP・EN | — |
| 01 | `spike/01_property_graph_basic.py` | ✓ 完了 | 02-2d / 03 / 04 / 07 / 10 | 案 A 直接投入（`upsert_nodes`/`upsert_relations`）/ persist-reload / 章単位 stale 除去（raw delete vs safe wrapper の比較）/ `safe_delete_by_section` wrapper 動作 | — |
| 02 | `spike/02_property_graph_index.py` | ☐ 未着手 | 01 / 09 / 11-注入経路 | `PropertyGraphIndex.from_existing(graph_store, vector_store, embed_model)` 構築 / `Settings.embed_model = OllamaEmbedding(...)` 注入 / persist + reload / `shutil.rmtree(persist_dir)` + 全再構築（経路 2 相当）| 1 |
| 03 | `spike/03_retriever_and_transient.py` | ☐ 未着手 | 05 / 07-retrieval / 08 | 各 entity に embedding をセット → `VectorContextRetriever` + `PGRetriever` で検索 / `NodeWithScore.node.metadata` に properties が乗るか確認 / 4 軸 transient annotation（`constraint_relevance` / `target_relevance` / `conflict` / `review_required`）を Orchestrator 側で後付け、graph には書き込まないことを確認 | 2 |
| 04 | `spike/04_cli_subprocess.py` | ☐ 未着手 | 12 | `claude --print --bare --no-session-persistence --output-format json --json-schema '{...}' < prompt` で JSON 取得 / `codex exec --output-schema schema.json --skip-git-repo-check` で同等動作 / 出力揺れ（同一 prompt × 複数回） / 認証切れ・rate limit エラー型を観察 | 3 |

**優先順序の根拠**:

- 02 が最優先: `PropertyGraphIndex` の構築が動かないと 03 の `Retriever` 系が組めない（依存）
- 03 は 02 の後: retrieval は graph 構築 + embedding 注入後でしか走らない
- 04 は独立: subprocess のみなので 02/03 と並行可。ただし 02/03 が終わってからまとめて取り組むのが効率的

**Phase 0.5 完了条件**:

1. spike 02 / 03 / 04 が**動作確認まで完了**している（実行ログが取れている）
2. 各 spike の結果を [doc/SURVEY/](SURVEY/) 各項目の「実測・検証結果」に反映
3. Phase 0 状態一覧表（上記）の `Spike` 列が全項目 ✓ または該当ナシ（—）になる
4. 残った `usable_with_wrapper` / `partially usable` の項目が、wrapper 設計確定 + spike 実証で **`usable` または明確な不採用判定** に確定している

#### 部品レベルのチェックリスト（Phase 0.5 内訳、参考）

上の spike 計画と対応する形で、当初の TODO 項目を整理する。

- [✓] 2〜3 個の Markdown Section を読み込む（spike 01 で section_a / section_b をハードコード模擬）
- [☐] `PropertyGraphIndex` を構築する → spike 02
- [☐] `SchemaLLMPathExtractor` に schema を渡し、entity / relation が期待形式で取れるか確認 → Phase 1 / 実装着手時（spike 計画には含めない、案 A で進める想定なので必須でない）
- [✓] node / relation に **恒久プロパティ**（section_id / source_span / source_hash 等）を保持できる（spike 01）
- [✓] persist / reload できる（spike 01、JSON 1741 bytes、日本語 OK）
- [✓] 1 章だけ変更した場合に stale node / stale edge を除去できる（spike 01、ただし `store.delete()` は破綻、`safe_delete_by_section` wrapper 経由のみ可）
- [☐] `Retriever` で evidence 付き候補を取り出せる → spike 03
- [☐] 4 軸評価を LlamaIndex 内ではなく Orchestrator 側の **transient annotation** として扱える → spike 03
- [☐] PropertyGraphIndex に Ollama embedding を `Settings.embed_model` 経由で注入（追加項目） → spike 02
- [☐] `/spec-core --all` 相当の persist_dir 削除 + 全再構築（追加項目） → spike 02
- [☐] Claude/Codex CLI subprocess 実呼び出し（追加項目、structured output） → spike 04

#### 3 コマンド × 4 経路の一気通貫スパイク（DESIGN.ja.md §1.9 の 4 経路、toy 構成で）

すべて未着手（部品スパイクが完了してから組み立てる）。

- [☐] **経路 1: /spec-core incremental** — 章を 1 つ追加 → ChapterAnchor / Entity / Relation 生成 → Concept diff 提示 → accept → persist
- [☐] **経路 1（continued）**: 既存章を 1 つ修正 → 変更検出 → stale 除去 + 新規追加 → Concept diff 提示 → accept → persist
- [☐] **経路 2: /spec-core --all** — 既存 store を破棄 → 全章再構築 → Concept 再生成 diff → accept → persist
- [☐] **経路 3: /spec-inject** — 課題プロンプトを与える → 内部で経路 1 実行 → Retriever で候補取得 → LLM (Classification) で 4 軸付与 → Validator → InjectionContext 出力
- [☐] **経路 3（unapproved 停止）**: Concept diff が未承認な状態で /spec-inject を呼ぶ → 停止し InjectionContext を生成しないことを確認
- [☐] **経路 4: /spec-realign** — 課題プロンプトを与える → 経路 3 + LLM (Answer) で RealignResult を生成 → ConstraintContext / TargetContext / ConflictNotes / ReviewNotes / Answer の構造を確認
- [☐] **経路間の依存**: 経路 3 / 4 が経路 1 を正しく呼び、経路 2 が単独実行のみであることを確認

### Phase 1：仮分担と方式フローの再評価（Phase 0 + 0.5 完了後）

Phase 0 / 0.5 の結果を元に、DESIGN.ja.md §1 の各セクションが GraphRAG 側で実装可能か照合する。

**§1 各セクションの再評価**:

- [ ] §1.1 仮分担マトリクスを調査結果と照合
  - GraphRAG が実際にできること / できないことに合わせて再分配
  - LLM (Extraction / Classification / Answer) の境界が成立するか
- [ ] §1.5 整合性チェック方針の再評価
  - Conflict 二段階（LLM 候補 → Validator/Human 確定）が GraphRAG API で成立するか
- [ ] §1.6 4 軸評価の再評価
  - **graph 恒久プロパティではなく transient annotation として保持**できるか
  - retrieval result / InjectionContext / RealignResult のどこに持つか
- [ ] §1.7 Agent Read 制限の再評価
- [ ] §1.8 LlamaIndex 部品契約（candidate_only）の再評価
- [ ] §1.9 内部処理フローの再評価
  - ChapterAnchor の共同責務（CLI/Parser + LLM (Extraction) + GRAG Builder）が成立するか

**3 コマンド × 4 経路の一気通貫動作確認（最重要レビュー基準）**:

DESIGN.ja.md §1.9 の 4 経路すべてが、Phase 0.5 のスパイクから上位の orchestrator まで一気通貫で動作することを確認する。**1 経路でも破綻していたら Phase 2 に進めない**。

- [ ] 経路 1（/spec-core incremental）: 変更検出 → 該当章のみ再抽出 → stale 除去 → Concept diff → 承認後 persist
- [ ] 経路 2（/spec-core --all）: 全章再構築 → Concept 再生成 → 承認後 persist
- [ ] 経路 3（/spec-inject）: 経路 1 を内部実行 → Concept 未承認時の停止確認 → Retriever → 4 軸付与 → Validator → InjectionContext
- [ ] 経路 4（/spec-realign）: 経路 3 + Answer 生成 → RealignResult
- [ ] 経路間のデータ受け渡し（経路 3 → 4 で InjectionContext が一貫している、経路 1 で永続化された ChapterAnchor が経路 3 の Retriever で取れる、等）

成果：DESIGN.ja.md §1 の更新案を作成（「仮」→「決定」または再分配）+ **検証 version / commit / 検証日を pin して記録** + 4 経路の動作証跡（spike コードと出力ログ）。

### Phase 2：レビュー → 設計書反映（Phase 1 完了後）

- [ ] ユーザーレビュー（根幹処理に問題がないか）
- [ ] **3 コマンド × 4 経路の一気通貫動作証跡**をユーザーに提示（Phase 1 で取得した spike コードと出力ログ）
- [ ] レビューフィードバックを DESIGN.ja.md §1 に反映
- [ ] §1 の「仮分担」マーカーを外して「決定」に昇格
- [ ] DESIGN.ja.md に検証 version / commit / 検証日を記録

### Phase 3：実装着手（Phase 2 完了後）

DESIGN.ja.md §4.2〜§4.9 の不確定項目を順次解消：

- [ ] §4.2 章別管理（ChapterAnchor JSON/dataclass 構造、章単位 incremental orchestration、chapter_index/concept_index スキーマ、階層 cluster）
- [ ] §4.3 LLM プロバイダー実装（Claude/Codex CLI 版 subprocess、concurrent batch、LLM 注入抽象化、用途別設定）
- [ ] §4.4 Cross-Encoder rerank（日本語モデル選定、LlamaIndex 統合）
- [ ] §4.5 spec-grag CLI 実装（フレームワーク、パッケージング、配布）
- [ ] §4.6 整合性チェック実装（グラフ構造ベースルール、ルールベース YAML/TOML、LLM prompt template、Conflict 昇格 Validator）
- [ ] §4.7 4 軸評価の実装（transient annotation、値域・閾値・default、prompt template、派生 irrelevant、重複表示制御）
- [ ] §4.8 Concept 更新案 unified diff（生成パイプライン、diff ライブラリ、出力規約）
- [ ] §4.9 Optional Extensions 発動判断（decision_process 拡張の有効化）

---

## 関連ドキュメント

- [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md): 外部契約（source of truth、不変）
- [doc/DESIGN.ja.md](DESIGN.ja.md): 詳細設計（§1 仮分担を含む）
- [CLAUDE.md](../CLAUDE.md): 不変ルール（ルール 1, 4, 5, 7 が設計手順の根拠）
- [doc/CLAUDE_NOTES.md](CLAUDE_NOTES.md): 過去の手戻り集
- memory `feedback_design_procedure.md`: 設計手順の原則
