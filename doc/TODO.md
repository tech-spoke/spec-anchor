# spec-grag TODO / Phase 1 verification

本書は現時点の次アクションを管理する。旧フェーズ管理版は `BAK/doc/TODO.md.pre-phase1-verification-20260429` に退避済み。

## 現在地

- 外部契約: `doc/EXTERNAL_DESIGN.ja.md`
- 内部設計: `doc/DESIGN.ja.md`
- 現フェーズ: Phase 1 verification / 初期実装
- 方針: 縮小版ではなく、外部契約を満たす実装を前提に、未実証の実装方式を検証する

Phase 1 verification は「仕様を後で決める期間」ではない。`DESIGN.ja.md` の内部契約どおりに実装できるかを確認し、不成立の箇所だけ外部契約を維持した代替へ切り替えるためのゲートである。

## 作業原則

- `EXTERNAL_DESIGN.ja.md` の出力契約は崩さない
- `DESIGN.ja.md` にある JSON schema / sidecar schema / status enum を先に固定する
- Answer 生成 phase では tool / raw source read / 追加 Agentic search を許可しない
- LLM 抽出 artifact には provenance を必ず持たせる
- stale 削除は `source_section_id` / `source_chunk_id` / `extract_run_id` に基づく
- section 構造変更は `source_manifest` と `current_section_manifest` の差分で扱う
- 低信頼・未解決項目は graph を汚染せず、sidecar / ReviewNotes / warnings / `ResultEnvelope.status` に落とす
- 検証で使用した package version / CLI version / 実行日を記録する

## 推奨順

### 1. JSON protocol と CLI skeleton

- [x] `SlashCommandRequest`
- [x] `ResultEnvelope`
- [x] `NeedMoreContextResult`
- [x] `AgenticSearchCandidate`
- [x] `CoreResult`
- [x] `ConceptApprovalRequiredResult`
- [x] `InjectionContext`
- [x] `RealignResult`
- [x] stdin JSON -> CLI -> stdout JSON の roundtrip test
- [x] `/spec-core` / `/spec-inject` / `/spec-realign` の最小 CLI entrypoint

完了条件: Agent/CLI/Orchestrator 境界が JSON schema と test で固定される。

### 2. manifest / atomic write 基盤

- [x] Markdown heading 構造から `current_section_manifest` を生成
- [x] section 単位 `source_hash` を計算
- [x] `source_manifest.json` の load / tmp write / fsync / atomic replace
- [x] `status=ok` / `degraded` / `blocked` / `failed` 時の manifest 更新 test
- [x] removed / renamed / split / merged section の reconciliation test
- [ ] CommonMark parser 導入判断（Setext heading / HTML block / attribute 付き heading が必要になった場合）

完了条件: source 構造変更時に deterministic node / relation と LLM artifact の stale が残らない。

### 3. GRAG build 最小縦切り

- [x] `CodexCLIAdapter(CustomLLM)` 実装
- [x] `complete` / `stream_complete` / `metadata` の最小動作確認
- [x] CLI structured output の schema 違反時挙動を確認
  - 2026-04-29 実測: 矛盾プロンプトでは schema 側が優先される傾向。ただし満たせない schema では Codex / Claude とも exit 0 で schema 外出力を返し得るため、adapter 側で local JSON Schema validation を必須化
- [x] `SchemaLLMPathExtractor` 軽量 schema（4 entity / 6 relation）
- [x] 日本語 extraction prompt
- [x] LLM extraction artifact provenance 付与
- [x] `safe_delete_by_section` を provenance-based に実装

完了条件: toy source から graph node / relation / provenance 付き artifact を生成し、変更 section の stale を削除できる。

### 4. vector / retrieval 基盤

- [x] vector_store の `VECTOR_SOURCE_KEY` 連結正規パターンを確定
- [x] TextNode.metadata へ entity properties をコピー
- [x] `PGRetriever` / `VectorContextRetriever` の候補取得 smoke test
- [x] 0 件時の keyword + property filter fallback
- [x] retrieval result へ 4 軸 transient annotation を後付け

完了条件: graph traversal と vector retrieval の両方から evidence 付き候補を取得できる。

### 5. sidecar artifacts

- [ ] `unresolved_relations` sidecar
- [ ] `chapter_anchors.json`
- [ ] affected chapter 単位の ChapterAnchor dirty 化
- [ ] ChapterAnchor 再集約成功時の atomic replace
- [ ] ChapterAnchor 再集約失敗時に旧 artifact を stale のまま保持
- [ ] `cluster_snapshot.json`
- [ ] cluster dirty / stale 再算出
- [ ] `level=concept` が Core Concept index を参照することを test

完了条件: section 更新後も章単位 summary / key_entities / key_concepts / cluster が古いまま通常扱いされない。

### 6. Concept diff 承認フロー

- [ ] `pending_concept_diff_<id>.json`
- [ ] `diff_id` / `hunk_id`
- [ ] `base_concept_hash`
- [ ] `/spec-core --accept`
- [ ] `/spec-core --reject`
- [ ] `/spec-core --revise`
- [ ] `/spec-core --apply`
- [ ] apply 時の hash 衝突検出

完了条件: hunk 単位の承認・拒否・修正指示が CLI プロセス終了後も再開できる。

### 7. `/spec-core` E2E

- [ ] `/spec-core --all`
- [ ] `/spec-core` incremental 本文変更
- [ ] `/spec-core` incremental section 削除
- [ ] `/spec-core` incremental section rename
- [ ] `/spec-core` incremental split / merge
- [ ] ChapterAnchor 全再生成
- [ ] Concept diff pending 停止
- [ ] `CoreResult.status` と `ResultEnvelope.status`

完了条件: source 更新から graph/vector/sidecar/concept diff まで一通り流れる。

### 8. `/spec-inject`

- [ ] `/spec-inject` が内部で `/spec-core` incremental 相当を実行
- [ ] Concept diff 未承認時は `ConceptApprovalRequiredResult` で `blocked`
- [ ] Retrieval / Agentic search 候補分類
- [ ] `NeedMoreContextResult` loop
- [ ] `AgenticSearchCandidate` の `request_id` / `source_hash` / 出典解決 validation
- [ ] `InjectionContext` 構造化出力
- [ ] `constraint_context` / `target_context` / `conflict_notes` / `review_notes`

完了条件: Answer 生成なしで、外部設計どおりの InjectionContext を生成できる。

### 9. `/spec-realign`

- [ ] `/spec-realign` が `/spec-inject` 相当の context build を実行
- [ ] `context_ready == true` になるまで Answer 生成しない
- [ ] Answer 入力を `task_prompt + InjectionContext` のみに制限
- [ ] Answer phase の tool / raw source read 禁止を test
- [ ] `RealignResult` 構造化出力

完了条件: 追加 Agentic search を Answer phase に持ち込まず、制約付き回答を生成できる。

### 10. 外部契約 E2E

- [ ] 経路 1: `/spec-core` incremental
- [ ] 経路 2: `/spec-core --all`
- [ ] 経路 3: `/spec-inject`
- [ ] 経路 4: `/spec-realign`
- [ ] degraded / blocked / failed の代表ケース
- [ ] stale relation が残らないこと
- [ ] unresolved relation が graph に混入しないこと
- [ ] Concept diff 未承認時に InjectionContext / Answer を生成しないこと

完了条件: `EXTERNAL_DESIGN.ja.md` の主要フローとエラー契約を E2E で確認できる。

## Phase 1 verification 対応表

| spike | 位置づけ | 対応 TODO |
|---|---|---|
| spike 13 | JSON protocol / InjectionContext の入口契約。最初に固定する土台 | 1, 8, 9 |
| spike 05 | `CodexCLIAdapter(CustomLLM)` | 3 |
| spike 06 | SchemaLLMPathExtractor / Section grounding / provenance / reconciliation | 2, 3 |
| spike 07 | vector_store 連結 / retrieval metadata | 4 |
| spike 08 | ChapterAnchor artifact / affected chapter 再集約 | 5 |
| spike 09 | Concept diff 候補生成 / pending apply protocol | 6 |
| spike 10 | 4 軸 transient annotation prompt / metadata 後付け | 4, 8 |
| spike 11 | Conflict validator | 8 |
| spike 12 | cluster snapshot / dirty-stale 再算出 | 5 |

spike 番号は設計書上の検証 ID として維持する。実行順は `spike 13` 相当の JSON protocol を先頭に置く。

## 記録する成果物

- 実装コード
- unit test / integration test
- toy source fixtures
- CLI 入出力 JSON fixture
- 実行ログ
- 検証 version / commit / 実行日
- `DESIGN.ja.md` を修正した場合の根拠

## 関連ドキュメント

- `doc/EXTERNAL_DESIGN.ja.md`: 外部契約
- `doc/DESIGN.ja.md`: 内部設計
- `doc/HANDOFF.ja.md`: 現在の実装・検証結果・次作業の引き継ぎ
- `BAK/doc/TODO.md.pre-phase1-verification-20260429`: 旧フェーズ管理 TODO
- `doc/CLAUDE_NOTES.md`: 作業メモと過去の手戻り
