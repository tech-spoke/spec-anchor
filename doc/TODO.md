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

**Phase 0: §4.1 表面マップ調査前**

DESIGN.ja.md §1.1〜§1.3, §1.5〜§1.9 はすべて **仮分担**。§4.1 LlamaIndex 表面マップ調査完了後にレビュー → 確定する。

`§1.4 採用方針（決定済）`（Python + LlamaIndex 系エコシステム + ローカル・ファイルベース永続化 + Claude/Codex CLI + Ollama embedding）のみ pivot で確定済。

---

## 次のアクション（優先順）

### Phase 0：表面マップ調査（最優先、§4.1）

調査方法：WebFetch + GitHub の最新版コード確認 + 上記「調査成果物フォーマット」で記録（推論カットで埋めない、CLAUDE.md ルール 2 に従う）。

各項目について「調査対象 / 確認した API / 実測・検証結果 / spec-grag への影響 / 判定」を埋める。実測は Phase 0.5 と並行する。

- [ ] `PropertyGraphIndex` の API 安定度
  - v0.10 系での変更頻度、Breaking change の頻度
  - コア API（add / build / query / persist / reload）の実体
- [ ] `SchemaLLMPathExtractor` の制約強度
  - プロンプトレベル止まりか、型システムレベルまで
  - スキーマ受理形式（dataclass / pydantic / dict / TypedDict）
  - `strict=True` で schema 外 triplet が拒否されるか
- [ ] `SimplePropertyGraphStore` の永続化粒度
  - 章別 vs 全体一括の制御可否
  - pickle / JSON / parquet
  - in-memory vs disk persist の境界
- [ ] incremental update 方式
  - 章単位 SHA-256 変更検出 → 影響範囲のみ再構築できるか
  - stale edge 除去の挙動（変更章の旧 entity / relation がどう処理されるか）
- [ ] `HybridRetriever` の fusion 戦略（RRF / Weighted / CombSum / MaxScore のうち何が標準か、API レベルで切替可能か）
- [ ] `HippoRAG / LightRAG retrieval` との統合可否
- [ ] **恒久プロパティ**として保持できる項目（document_id / section_id / source_span / source_hash / concept_id / approval_status / evidence / created_at / updated_at）が node / relation の metadata に乗るか
- [ ] **transient annotation**（4 軸評価）を retrieval result / Orchestrator 側に持つ実装パターン
- [ ] `/spec-core --all`（全再構築）の API 上の挙動（既存 graph store の破棄 / バックアップ / 上書き、persist の冪等性）
- [ ] `/spec-core incremental` の stale 除去と新規追加の整合性（変更章の旧 entity/relation がどう除去されるか、新 entity/relation との整合）

### Phase 0.5：最小実行スパイク（Phase 0 の各項目を実コードで確認）

Phase 0 は WebFetch / GitHub 確認だけでは「素材を触った」と言えない。toy documents で実行確認する。スパイクコードは `spike/` 配下に保存し、調査成果物の `source.実行確認` に記録する。

**部品レベルのスパイク**:

- [ ] 2〜3 個の Markdown Section を読み込む（spec-grag 想定の章ファイル相当）
- [ ] `PropertyGraphIndex` を構築する
- [ ] `SchemaLLMPathExtractor` に schema を渡し、entity / relation が期待形式で取れるか確認
- [ ] node / relation に **恒久プロパティ**（section_id / source_span / source_hash 等）を保持できるか確認
- [ ] persist / reload できるか確認
- [ ] 1 章だけ変更した場合に stale node / stale edge を除去できるか確認
- [ ] `Retriever` で evidence 付き候補を取り出せるか確認
- [ ] 4 軸評価は LlamaIndex 内ではなく Orchestrator 側の **transient annotation** として扱えるか確認（graph に書かない）

**3 コマンド × 4 経路の一気通貫スパイク**（DESIGN.ja.md §1.9 の 4 経路、toy 構成で）:

- [ ] **経路 1: /spec-core incremental** — 章を 1 つ追加 → ChapterAnchor / Entity / Relation 生成 → Concept diff 提示 → accept → persist
- [ ] **経路 1（continued）**: 既存章を 1 つ修正 → 変更検出 → stale 除去 + 新規追加 → Concept diff 提示 → accept → persist
- [ ] **経路 2: /spec-core --all** — 既存 store を破棄 → 全章再構築 → Concept 再生成 diff → accept → persist
- [ ] **経路 3: /spec-inject** — 課題プロンプトを与える → 内部で経路 1 実行 → Retriever で候補取得 → LLM (Classification) で 4 軸付与 → Validator → InjectionContext 出力
- [ ] **経路 3（unapproved 停止）**: Concept diff が未承認な状態で /spec-inject を呼ぶ → 停止し InjectionContext を生成しないことを確認
- [ ] **経路 4: /spec-realign** — 課題プロンプトを与える → 経路 3 + LLM (Answer) で RealignResult を生成 → ConstraintContext / TargetContext / ConflictNotes / ReviewNotes / Answer の構造を確認
- [ ] **経路間の依存**: 経路 3 / 4 が経路 1 を正しく呼び、経路 2 が単独実行のみであることを確認

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
