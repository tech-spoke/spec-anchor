# spec-grag 作業手順 / フェーズ管理

本書は spec-grag の **作業手順とフェーズ管理** を記録する。仕様書（DESIGN.ja.md）や外部契約（EXTERNAL_DESIGN.ja.md）とは別に、「次にやるべき作業」と「フェーズ進行」を一元管理する。

## 設計手順の原則

```
1. 調査
   - GraphRAG / LlamaIndex の機能・限界・典型利用シーケンスを実装レベルで把握
   - CLAUDE.md ルール 1（土台調査）, ルール 5（全項目列挙）に従う
   - 推論カットで埋めない（CLAUDE.md ルール 2, 3）

2. 仮分担と方式フローの策定
   - 調査結果を元に、役割分担（DESIGN.ja.md §1.1〜§1.9）と内部フローを仮策定
   - 「仮」「暫定」と書く（CLAUDE.md ルール 4）

3. 根幹処理のレビュー
   - ユーザーレビューを受ける
   - 矛盾・欠落・誤解を洗い出す

4. 設計書へ反映
   - レビュー承認後に DESIGN.ja.md §1 を更新（「仮」を「決定」に昇格、または再分配）
   - 一巡したら次のフェーズへ
```

**重要**: 調査前に役割分担を「決定」と書かない。CLAUDE.md ルール 7「実装より先に役割分担を考える」は **調査が完了した上での役割分担の確定** を意味する。役割分担「自体」を調査前に確定してはいけない（前回 graphrag-rs で犯した手戻りと同じ構造）。

---

## 現在のフェーズ

**Phase 0: §4.1 表面マップ調査前**

DESIGN.ja.md §1.1〜§1.3, §1.5〜§1.9 はすべて **仮分担**。§4.1 LlamaIndex 表面マップ調査完了後にレビュー → 確定する。

`§1.4 採用方針（決定済）`（Python + LlamaIndex 系エコシステム + ローカル・ファイルベース永続化 + Claude/Codex CLI + Ollama embedding）のみ pivot で確定済。

---

## 次のアクション（優先順）

### Phase 0：表面マップ調査（最優先、§4.1）

調査方法：WebFetch + GitHub の最新版コード確認（CLAUDE.md ルール 2 に従う、推論カットで埋めない）。

- [ ] `PropertyGraphIndex` の API 安定度調査
  - v0.10 系での変更頻度、Breaking change の頻度
  - コア API（add / build / query）の実体
- [ ] `SchemaLLMPathExtractor` の制約強度
  - プロンプトレベル止まりか、型システムレベルまで
  - スキーマ受理形式（dataclass / pydantic / dict / TypedDict）
- [ ] `SimplePropertyGraphStore` の永続化粒度
  - 章別 vs 全体一括の制御可否
  - pickle / JSON / parquet
  - in-memory vs disk persist の境界
- [ ] incremental update 方式
  - 章単位 SHA-256 変更検出 → 影響範囲のみ再構築できるか
  - stale edge 除去の挙動
- [ ] `HybridRetriever` の fusion 戦略（RRF / Weighted / CombSum / MaxScore のうち何が標準か、API レベルで切替可能か）
- [ ] `HippoRAG / LightRAG retrieval` との統合可否
- [ ] 4 軸評価メタデータ（constraint_relevance / target_relevance / conflict / review_required）を node / relation のプロパティとして保持できるか
- [ ] 章単位 incremental の実装可能性

### Phase 1：仮分担と方式フローの再評価（§4.1 完了後）

§4.1 調査結果を元に、DESIGN.ja.md §1 の各セクションが GraphRAG 側で実装可能か照合する。

- [ ] §1.1 仮分担マトリクスを調査結果と照合
  - GraphRAG が実際にできること / できないことに合わせて再分配
  - LLM (Extraction / Classification / Answer) の境界が成立するか
- [ ] §1.5 整合性チェック方針の再評価
  - Conflict 二段階（LLM 候補 → Validator/Human 確定）が GraphRAG API で成立するか
- [ ] §1.6 4 軸評価の再評価
  - LlamaIndex 側で 4 軸メタデータを保持・取り出せるか
- [ ] §1.7 Agent Read 制限の再評価
  - 実装上、Agent から spec-grag CLI への入出力で制限が成立するか
- [ ] §1.8 LlamaIndex 部品契約（candidate_only）の再評価
  - PropertyGraphIndex / SchemaLLMPathExtractor / SimplePropertyGraphStore / Retriever が candidate_only として制約可能か
- [ ] §1.9 内部処理フローの再評価
  - /spec-core / /spec-inject / /spec-realign の各ステップが GraphRAG API で実装可能か
  - ChapterAnchor の共同責務（CLI/Parser + LLM (Extraction) + GRAG Builder）が成立するか

成果：DESIGN.ja.md §1 の更新案を作成（「仮」→「決定」または再分配）。

### Phase 2：レビュー → 設計書反映（Phase 1 完了後）

- [ ] ユーザーレビュー（根幹処理に問題がないか）
- [ ] レビューフィードバックを DESIGN.ja.md §1 に反映
- [ ] §1 の「仮分担」マーカーを外して「決定」に昇格

### Phase 3：実装着手（Phase 2 完了後）

DESIGN.ja.md §4.2〜§4.9 の不確定項目を順次解消：

- [ ] §4.2 章別管理（ChapterAnchor JSON/dataclass 構造、章単位 incremental orchestration、chapter_index/concept_index スキーマ、階層 cluster）
- [ ] §4.3 LLM プロバイダー実装（Claude/Codex CLI 版 subprocess、concurrent batch、LLM 注入抽象化、用途別設定）
- [ ] §4.4 Cross-Encoder rerank（日本語モデル選定、LlamaIndex 統合）
- [ ] §4.5 spec-grag CLI 実装（フレームワーク、パッケージング、配布）
- [ ] §4.6 整合性チェック実装（グラフ構造ベースルール、ルールベース YAML/TOML、LLM prompt template、Conflict 昇格 Validator）
- [ ] §4.7 4 軸評価の実装（値域・閾値・default、prompt template、派生 irrelevant、重複表示制御）
- [ ] §4.8 Concept 更新案 unified diff（生成パイプライン、diff ライブラリ、出力規約）
- [ ] §4.9 Optional Extensions 発動判断（decision_process 拡張の有効化）

---

## 関連ドキュメント

- [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md): 外部契約（source of truth、不変）
- [doc/DESIGN.ja.md](DESIGN.ja.md): 詳細設計（§1 仮分担を含む）
- [CLAUDE.md](../CLAUDE.md): 不変ルール（ルール 1, 4, 5, 7 が設計手順の根拠）
- [doc/CLAUDE_NOTES.md](CLAUDE_NOTES.md): 過去の手戻り集
- memory `feedback_design_procedure.md`: 設計手順の原則
