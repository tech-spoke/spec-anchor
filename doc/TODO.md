# spec-grag TODO / Phase 1 verification

本書は現時点の次アクションを管理する。旧フェーズ管理版は `BAK/doc/TODO.md.pre-phase1-verification-20260429` に退避済み。

## 現在地

- 外部契約: `doc/EXTERNAL_DESIGN.ja.md`
- 内部設計: `doc/DESIGN.ja.md`
- 現フェーズ: Phase 6 設定・運用・品質基盤 完了
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
- 各 Phase の完了時には、実装結果・検証結果・気づき・問題点・簡易実装・残リスク・次 Phase への申し送りを `doc/PHASE<N>_REPORT.ja.md` として記録する

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
- [x] CommonMark parser 導入（`markdown-it-py` commonmark preset、Setext heading / HTML block 対応、parser metadata 記録）

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

- [x] `unresolved_relations` sidecar
- [x] `chapter_anchors.json`
- [x] affected chapter 単位の ChapterAnchor dirty 化
- [x] ChapterAnchor 再集約成功時の atomic replace
- [x] ChapterAnchor 再集約失敗時に旧 artifact を stale のまま保持
- [x] `cluster_snapshot.json`
- [x] cluster dirty / stale 再算出
- [x] `level=concept` が Core Concept index を参照することを test

完了条件: section 更新後も章単位 summary / key_entities / key_concepts / cluster が古いまま通常扱いされない。

### 6. Concept diff 承認フロー

- [x] `pending_concept_diff_<id>.json`
- [x] `diff_id` / `hunk_id`
- [x] `base_concept_hash`
- [x] `/spec-core --accept`
- [x] `/spec-core --reject`
- [x] `/spec-core --revise`
- [x] `/spec-core --apply`
- [x] apply 時の hash 衝突検出

完了条件: hunk 単位の承認・拒否・修正指示が CLI プロセス終了後も再開できる。

### 7. `/spec-core` E2E

- [x] `/spec-core --all`
- [x] `/spec-core` incremental 本文変更
- [x] `/spec-core` incremental section 削除
- [x] `/spec-core` incremental section rename
- [x] `/spec-core` incremental split / merge
- [x] ChapterAnchor 全再生成
- [x] Concept diff pending 停止
- [x] `CoreResult.status` と `ResultEnvelope.status`

完了条件: source 更新から graph/vector/sidecar/concept diff まで一通り流れる。

### 8. `/spec-inject`

- [x] `/spec-inject` が内部で `/spec-core` incremental 相当を実行
- [x] Concept diff 未承認時は `ConceptApprovalRequiredResult` で `blocked`
- [x] Retrieval / Agentic search 候補分類
- [x] `NeedMoreContextResult` loop
- [x] `AgenticSearchCandidate` の `request_id` / `source_hash` / 出典解決 validation
- [x] `InjectionContext` 構造化出力
- [x] `constraint_context` / `target_context` / `conflict_notes` / `review_notes`

完了条件: Answer 生成なしで、外部設計どおりの InjectionContext を生成できる。

### 9. `/spec-realign`

- [x] `/spec-realign` が `/spec-inject` 相当の context build を実行
- [x] `context_ready == true` になるまで Answer 生成しない
- [x] Answer 入力を `task_prompt + InjectionContext` のみに制限
- [x] Answer phase の tool / raw source read 禁止を test
- [x] `RealignResult` 構造化出力

完了条件: 追加 Agentic search を Answer phase に持ち込まず、制約付き回答を生成できる。

### 10. 外部契約 E2E

- [x] 経路 1: `/spec-core` incremental
- [x] 経路 2: `/spec-core --all`
- [x] 経路 3: `/spec-inject`
- [x] 経路 4: `/spec-realign`
- [x] degraded / blocked / failed の代表ケース
- [x] stale relation が残らないこと
- [x] unresolved relation が graph に混入しないこと
- [x] Concept diff 未承認時に InjectionContext / Answer を生成しないこと

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

## Phase 2 以降の計画

Phase 1 verification では、外部契約の主要経路と失敗契約を E2E で通し、JSON protocol / manifest / sidecar / pending Concept diff / `/spec-core` / `/spec-inject` / `/spec-realign` の縦切りを固定した。

ただし現時点の `/spec-core` は、E2E 契約を先に固定するために deterministic な DOCUMENT / CHAPTER / SECTION / ANCHOR 生成で実装している。Phase 2 以降は、この土台を崩さず、内部実装を本来設計の LLM extraction / GraphRAG retrieval / classification / answer generation へ置き換えていく。

継続原則:

- `EXTERNAL_DESIGN.ja.md` の外部契約は縮小しない
- `DESIGN.ja.md` は設計判断だけを記録し、作業ログを混ぜない
- Answer 生成 phase では raw source read / 追加 Agentic search / tool 利用を許可しない
- Concept diff 未承認時は `/spec-inject` / `/spec-realign` を `blocked` で止める
- 低信頼 relation / unresolved relation は graph に入れず sidecar / ReviewNotes に落とす
- deterministic 縦切りで通した E2E は、実装差し替え後も regression test として維持する

### Phase 2. 実抽出 core 化

目的: deterministic core update を、本来設計の `SchemaLLMPathExtractor + Codex/Claude adapter + section grounding` に置き換える。

- [x] `/spec-core` に `SchemaLLMPathExtractor` 実行パスを接続
- [x] `CodexCLIAdapter` / Claude adapter の provider 選択を config 化
  - [x] Codex provider を `[extraction] mode = "schema_llm"` / `provider = "codex"` で選択可能にする
  - [x] Claude provider adapter を追加し、同じ config 境界で選択可能にする
- [x] LLM 抽出 node / relation に `ExtractionProvenance` を必ず付与
- [x] LLM 抽出 ANCHOR を graph / vector store に投入
- [x] deterministic DOCUMENT / CHAPTER / SECTION / CONTAINS と LLM artifact を分離して永続化
- [x] target grounding / normalization を実装
- [x] 解決不能 target を `unresolved_relations.json` へ保存し、graph に混入しないことを E2E で確認
- [x] confidence が低い relation を traversal / cluster 入力から除外
- [x] `safe_delete_by_section` を実抽出 artifact に対して E2E 確認
- [x] `/spec-core --all` / incremental の既存 E2E を実抽出パスで通す
- [x] `doc/PHASE2_REPORT.ja.md` に実装結果・検証結果・気づき・問題点・残リスク・次 Phase への申し送りを記録する

完了条件: 実仕様 Markdown から LLM 抽出された ANCHOR / relation / unresolved relation / vector embedding / sidecar が provenance 付きで生成され、section 更新時に stale artifact が残らない。

### Phase 3. Core Concept index と Concept diff 候補生成

目的: 承認済み Concept を graph 外 index として検索可能にし、Source spec の変化から Concept 更新候補を生成する。

- [x] `concept_index.json` schema を実装
- [x] concept_file を heading / paragraph chunk に分割
- [x] `concept_chunk_id` / heading_path / text_hash / embedding を保存
- [x] concept_file hash 変更時に index を再生成
- [x] 未承認 Concept diff を index に混ぜないことを test
- [x] ANCHOR / relation と Core Concept index の差分検出を実装
- [x] Concept 更新候補を unified diff + hunk に変換
- [x] `pending_concept_diff_<diff_id>.json` 作成を `/spec-core` へ接続
- [x] accept / reject / revise / apply の既存 protocol E2E を実 diff 生成で通す
- [x] `doc/PHASE3_REPORT.ja.md` に実装結果・検証結果・気づき・問題点・残リスク・次 Phase への申し送りを記録する

完了条件: Source spec の意味変化から Concept diff 候補を生成し、未承認状態では downstream context / answer に入らない。

### Phase 4. Retrieval / Injection 品質化

目的: `/spec-inject` の rule-based 縦切りを、GraphRAG retrieval + 4 軸 classification + Validator に置き換える。

- [x] Core Concept retrieval を `/spec-inject` に接続
- [x] graph traversal retrieval と vector retrieval を統合
- [x] keyword fallback を retrieval pipeline に組み込む
- [x] ChapterAnchor / cluster snapshot を retrieval 候補に統合
- [x] Classification LLM による 4 軸 annotation を実装
  - Phase 4 では外部 LLM 呼び出しではなく Orchestrator rule-based classifier として実装。Classification LLM provider 接続は Phase 6 の provider config 整備で扱う。
- [x] 4 軸 annotation を graph に永続化しない regression test を維持
- [x] Conflict validator の段階 1 / 2 deterministic checks を実装
- [x] LLM 単独で `conflict=true` に昇格しないことを test
- [x] Agentic search request を複数候補・複数 round に拡張
- [x] Agentic search candidate の excerpt / source_span 解決 validation を強化
- [x] NeedMoreContext loop の retry / merge / timeout 方針を実装
- [x] InjectionContext の `constraint_context` / `target_context` / `conflict_notes` / `review_notes` golden E2E を追加
- [x] `doc/PHASE4_REPORT.ja.md` に実装結果・検証結果・気づき・問題点・残リスク・次 Phase への申し送りを記録する

完了条件: 課題プロンプトに対して、Purpose / Concept / Source specs / ChapterAnchor / graph / cluster / Agentic search 候補を 4 軸で分類した InjectionContext を安定生成できる。

### Phase 5. Answer LLM と `/spec-realign` 品質化

目的: `/spec-realign` のテンプレート回答を、Answer phase isolation を維持した Answer LLM に置き換える。

- [x] Answer LLM provider を config 化
- [x] Answer prompt template を固定
- [x] Answer 入力を `task_prompt + InjectionContext` のみに制限する境界 test を維持
- [x] context_ready でない場合に Answer 生成しない E2E を維持
- [x] 不足情報がある場合に blocked / NeedMoreContext へ戻す判定を実装
- [x] 4 区分回答（制約 / 修正対象 / 競合・レビュー / 回答案）の schema / golden test を追加
- [x] ConflictNotes / ReviewNotes を回答で隠さないことを test
- [x] raw source read / tool 利用禁止を subprocess / adapter 境界でも確認
- [x] `doc/PHASE5_REPORT.ja.md` に実装結果・検証結果・気づき・問題点・残リスク・次 Phase への申し送りを記録する

完了条件: `/spec-realign` が InjectionContext に拘束された回答を生成し、Answer phase で追加検索や raw source read を行わない。

### Phase 6. 設定・運用・品質基盤

目的: 実プロジェクトで継続利用できる CLI / slash command / storage 運用へ仕上げ、Graph / InjectionContext / Answer の根拠性を運用可能な水準まで固める。

- [x] `.spec-grag/config.toml` strict schema validation
- [x] provider / model / timeout / retry / storage path / source include の config 化
- [x] Codex / Claude CLI adapter の retry / backoff / timeout / schema failure handling を実装
  - 通常 retry、repair prompt、phase-specific fallback の順で扱う
  - Answer phase では失敗時も raw source read / 追加 Agentic search に逃げない
- [x] Classification LLM provider の実呼び出し mode を config 化
  - Phase 4 の `orchestrator_rule_based` classifier を fallback として維持する
- [x] Answer / Classification LLM の partial output recovery 方針を実装
  - 壊れた JSON はそのまま採用しない
  - Classification は該当候補を `review_required=true` または rule-based fallback に落とす
  - Answer は template fallback / `NeedMoreContextResult` / failed のいずれかに落とす
- [x] AgenticSearchCandidate の `source_span` strict validation を実装
  - `source_document_id` / `source_section_id` / `source_hash` / 行番号範囲 / section 範囲 / excerpt containment を検証する
  - 明示 `source_span` が有効で excerpt を含む場合、同一 excerpt が別箇所に存在しても invalid にしない
  - excerpt から `source_span` を逆引きする場合に複数候補があるときは ambiguous として `ReviewNotes` に落とす
- [x] embedding provider / model / dimension の config 化
  - default: Ollama `bge-m3`（日本語 / 多言語仕様文書向け、dim=1024）
  - dim=768 互換が必要な場合のみ `nomic-embed-text-v2-moe` を選択候補にする
  - `nomic-embed-text` / `nomic-embed-text:v1.5` は legacy / English-oriented と扱い、日本語仕様書 RAG の標準にしない
- [x] graph / vector / concept index に embedding provider / model / dimension metadata を保存
- [x] embedding metadata と config が不一致の場合、混在させず index rebuild を要求
- [x] conservative grounding scoring を実装
  - exact heading / heading_path / same document / same chapter / anchor proximity / embedding similarity / evidence excerpt containment / span proximity を候補スコアに使う
  - `best_score >= threshold` かつ `best_score - second_score >= margin` を満たす場合のみ resolve する
  - 曖昧な候補は graph に入れず `unresolved_relations` / `ReviewNotes` に落とす
- [x] LLM Concept diff proposal を実装
  - LLM は Concept を直接更新せず、evidence span 付き structured proposal を返す
  - CLI が proposal を検証し unified diff / pending Concept diff hunk に変換する
  - pending diff JSON / hunk accept / reject / revise / apply / 未承認遮断は既存実装を維持する
- [x] Conflict validator の deterministic rule pack を段階的に拡張
  - MUST vs MUST NOT、禁止 vs 必須、上限値 / 下限値、状態遷移、権限条件、Concept vs Source spec の矛盾を候補にする
  - LLM は `semantic_conflict_candidate` と evidence を出し、`conflict=true` 昇格は Validator rule または human approval を経る
- [x] slash command wrapper 実装
- [x] CLI 入出力 fixture を整備
- [x] run artifact / debug report / execution log を保存
- [x] graph / sidecar 破損時の recovery 方針を実装
- [x] storage migration / version check を追加
- [x] large source set の performance smoke
- [x] 実 `テスト用ドキュメント/` を使った end-to-end smoke
- [x] CI 用 smoke command を定義
- [x] `doc/PHASE6_REPORT.ja.md` を Phase 6 完了報告として最終化し、実装結果・検証結果・気づき・問題点・残リスク・次 Phase への申し送りを記録する

完了条件: 対象プロジェクトに `.spec-grag/config.toml` を置くだけで、継続的な `/spec-core` / `/spec-inject` / `/spec-realign` 運用ができ、根拠 span / LLM failure / grounding ambiguity が Graph を汚さない形で処理される。

### 直近推奨順

Phase 6 の実装 checklist は完了。次に進む場合は、実運用で得たログをもとに retrieval / grounding threshold / LLM prompt を調整する。

## 記録する成果物

- 実装コード
- unit test / integration test
- toy source fixtures
- CLI 入出力 JSON fixture
- 実行ログ
- 検証 version / commit / 実行日
- 各 Phase の結果報告 `doc/PHASE<N>_REPORT.ja.md`
- `DESIGN.ja.md` を修正した場合の根拠

## 関連ドキュメント

- `doc/EXTERNAL_DESIGN.ja.md`: 外部契約
- `doc/DESIGN.ja.md`: 内部設計
- `doc/HANDOFF.ja.md`: 現在の実装・検証結果・次作業の引き継ぎ
- `doc/PHASE1_REPORT.ja.md`: Phase 1 の結果報告。以後の Phase も同形式で作成する
- `doc/PHASE2_REPORT.ja.md`: Phase 2 の結果報告
- `doc/PHASE3_REPORT.ja.md`: Phase 3 の結果報告
- `doc/PHASE4_REPORT.ja.md`: Phase 4 の結果報告
- `doc/PHASE5_REPORT.ja.md`: Phase 5 の結果報告
- `doc/PHASE6_REPORT.ja.md`: Phase 6 の完了報告
- `BAK/doc/TODO.md.pre-phase1-verification-20260429`: 旧フェーズ管理 TODO
- `doc/CLAUDE_NOTES.md`: 作業メモと過去の手戻り
