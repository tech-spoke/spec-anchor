# spec-grag TODO / Phase 1 verification

本書は現時点の次アクションを管理する。旧フェーズ管理版は `BAK/doc/TODO.md.pre-phase1-verification-20260429` に退避済み。

## 現在地

- 外部契約: `doc/EXTERNAL_DESIGN.ja.md`
- 内部設計: `doc/DESIGN.ja.md`
- 現フェーズ: Phase 10 watcher / GRAG readiness gate / Concept diff queue 化 完了
- 次フェーズ: Phase 10 完了後、Phase 11 stage timings / performance observability を入れてから、契約監査 / production readiness / E2E / GRAG 品質 / 障害系を `doc/AUDIT_TODO.ja.md` に従って実施する
- 方針: 縮小版ではなく、外部契約を満たす実装を前提に、未実証の実装方式を検証する
- 監査 TODO: Phase 9 後の契約監査 / production readiness / E2E / GRAG 品質 / 障害系は `doc/AUDIT_TODO.ja.md` に分離する

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
- [x] Concept approval transport: accept / reject / revise / apply
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

Phase 8 の実装 checklist は完了。Phase 9 では smoke / fallback 実装を通常実行経路から外し、schema LLM extraction、実 embedding、LLM classification、LLM answer、LLM concept diff、LLM community report を production 主経路にした。self project の大規模 production full 評価は token 見積もり後の残件として分離する。

### 2026-05-01 現在の Phase 9 整理

- [x] production policy gate を追加し、通常 config から smoke fallback を締め出す
- [x] repo root / active template / package template の `.spec-grag/config.toml` を production 向けにする
- [x] `[llm].provider = "codex_cli" | "claude_cli"` を生成系 LLM の外部契約に戻す
- [x] `[llm]` から extraction / classification / answer / concept diff / query planner へ provider / command / model を継承させる
- [x] production では `[llm]` と選択 provider の `model` を必須にする
- [x] 外部設計書の Claude model 例を alias の `sonnet` ではなく `claude-sonnet-4-6` に変更する
- [x] Codex model は `codex debug models` の slug を指定する契約として外部設計書に明記する
- [x] full regression: `155 passed in 89.94s`
- [x] semantic conflict candidate の日本語 regression fixture を増やす
- [x] community detection / LLM community report / report evidence を導入する
- [x] fallback / degraded component の運用検査と CI guard を完成させる
- [ ] self project を production provider で token probe -> full run -> inject / realign まで通す

### Phase 7. 配布テンプレート / Codex command packaging

目的: Python CLI と JSON transport を、対象プロジェクトへ配布・導入し、Codex 上で `/spec-core` / `/spec-inject` / `/spec-realign` として自然に使える状態にする。

現状: `spec-grag` CLI と `scripts/spec-grag-slash.py` はあるが、active な `templates/` フォルダと Codex 用 command 定義は未実装。旧 `.claude/commands` と `.spec-grag/config.toml` は `BAK/templates/` にだけ残っている。

- [x] active な `templates/` フォルダを作成する
  - `templates/.spec-grag/config.toml`
  - `templates/.spec-grag/README.md` または設定コメント
  - `.codex/` は `.gitignore` 対象のため、実体は repo root 直下ではなく `templates/.codex/...` として管理する
- [x] Codex 用 slash command 定義を作成する
  - `templates/.codex/commands/spec-core.md`
  - `templates/.codex/commands/spec-inject.md`
  - `templates/.codex/commands/spec-realign.md`
  - 各 command は `spec-grag` または `scripts/spec-grag-slash.py` に stdin JSON を渡す形に統一する
  - Answer phase で raw source read / 追加 Agentic search に逃げない制約を command 文面にも明記する
- [x] Codex command の引数設計を固定する
  - `/spec-core [--all]`
  - `options.approval` による Concept approval transport
  - 互換用 wrapper flags は内部 transport として扱い、外部 slash command 契約にはしない
  - `/spec-inject "<task or current user message>"`
  - `/spec-realign "<task prompt>"`
- [x] テンプレート installer を実装する
  - 候補: `scripts/install_templates.py`
  - 候補: `spec-grag init --target <project_root>`
  - 既存ファイルがある場合は上書きせず `.bak` または `--force` 必須にする
  - install 後に `.spec-grag/config.toml` と `.codex/commands/spec-*.md` が揃うことを検証する
- [x] プロジェクト側セットアップスクリプトを実装する
  - 候補: `scripts/setup_project.py`
  - 対象プロジェクト root を指定して `.spec-grag/`、`.codex/commands/`、必要なら `docs/core/purpose.md` / `docs/core/concept.md` の雛形を作る
  - `--dry-run` / `--force` / `--backup` を持たせ、既存ファイルを暗黙に上書きしない
  - source include / graph storage / embedding provider / `[llm]` provider を対話なしの CLI option で指定できる
  - setup 後に `spec-grag` CLI が見つかること、config validation が通ること、必要ファイルが揃うことを確認する
  - 対象プロジェクト内の runtime artifact（`.spec-grag/graph/`、`.spec-grag/runs/`）と command template の git 管理方針を README に出す
- [x] システム配布 / 導入セットアップスクリプトを実装する
  - 候補: `scripts/setup_system.py`
  - Python >= 3.12、`uv`、`spec-grag` console script、依存 package の存在を検証する
  - 開発用 editable install、wheel build、ローカル配布 archive のいずれかを選べるようにする
  - Codex CLI / Claude CLI / Ollama は provider dependency として検出し、production では未導入時に fail-fast、`--smoke` 明示時だけ template / stable_hash fallback で動くことを明示する
  - PATH に `spec-grag` が見えるか、`python -m spec_grag.cli` fallback が使えるかを確認する
  - `scripts/ci-smoke.sh` または軽量 smoke を実行できる option を持たせる
  - 配布物に `templates/`、`scripts/spec-grag-slash.py`、README / quickstart が含まれることを検証する
- [x] 配布テンプレートの regression test を追加する
  - template path が git 管理対象であること
  - command markdown が存在し、`spec-core` / `spec-inject` / `spec-realign` を参照していること
  - installer が一時プロジェクトへ template を配置できること
  - 既存ファイルを誤って上書きしないこと
- [x] セットアップスクリプトの regression test を追加する
  - project setup が一時 project に必要ファイルを配置できること
  - project setup が既存ファイルをデフォルトで上書きしないこと
  - system setup の `--check-only` が依存状態を JSON または安定した stdout で返すこと
  - system setup の dry run がファイルを書かないこと
  - setup 後の fresh project で `spec-core --all` / `spec-inject` / `spec-realign` smoke が通ること
- [x] fresh project install smoke を追加する
  - 空の一時プロジェクトに template を install
  - `docs/core/purpose.md` / `docs/core/concept.md` / `docs/spec/*.md` の toy source を配置
  - install 済み config で `spec-core --all` / `spec-inject` / `spec-realign` が通ること
- [x] README / quickstart を整備する
  - 導入手順
  - Codex command の使い方
  - Ollama embedding を使う場合の前提
  - Codex / Claude provider を使う場合の認証前提
  - `.spec-grag/graph/`、`.spec-grag/runs/`、`.codex/commands/` の扱い
- [x] `doc/PHASE7_REPORT.ja.md` を作成する
  - 実装結果
  - 検証結果
  - テンプレート導入手順
  - 残リスク
  - 次作業

完了条件: fresh project に template を install すると、Codex 上で `/spec-core` / `/spec-inject` / `/spec-realign` が利用可能になり、同じ設定で `spec-grag` CLI smoke も通る。

### Phase 8. GraphRAG retrieval 再設計 / raw chunk hybrid search

目的: `/spec-inject` / `/spec-realign` の候補取得を、手書き token pattern matching から、raw document chunks + dense vector search + BM25 sparse lexical search + AI-extracted knowledge graph + rank fusion へ置き換える。

現状: `source_manifest.json` / `SECTION` node / vector store は主に `heading_path`、`section_id`、anchor metadata を保持しており、raw document chunk 本文を retrieval 対象にしていない。`query_tokens()` は空白 split に近く、日本語自然文では候補章が graph に存在しても `InjectionContext` に出ないことがある。GraphRAG としては、AI-extracted knowledge graph と raw document chunks の両方を検索対象にする必要がある。

方針:

- 手書き substring pattern matching を retrieval 主経路から排除する
- raw document chunks を検索対象の一次データにする
- dense vector search は raw chunk text を embedding する
- sparse lexical search は BM25 を正式な lexical leg として実装する
- BM25 analyzer は char n-gram + identifier/code/path token を基本にする
- LLM は query planning / query expansion / candidate assessment に使う
- graph は hit した chunk / entity / chapter / concept からの expansion に使う
- 最終的な `InjectionContext` には `excerpt` / `source_span` / `source_hash` 付き evidence を入れる

- [x] `DocumentChunk` / `TextUnit` sidecar schema を追加する
  - `chunk_id`
  - `document_id`
  - `chapter_id`
  - `section_id`
  - `heading_path`
  - `source_span`
  - `source_hash`
  - `text`
  - `chunk_hash`
  - `generated_at`
- [x] Markdown source から raw document chunks を生成する
  - section 単位だけでなく、長い section は overlap 付き chunk に分割する
  - chunk size / overlap は config 化する
  - `source_span` は 1-based line range で保持する
  - chunk text と source file の hash / span 検証を可能にする
- [x] raw chunk dense vector index を実装する
  - chunk本文を embedding する
  - `.spec-grag/graph/vector_store.json` または専用 sidecar に chunk vector を保存する
  - 既存の SECTION / ANCHOR metadata embedding は graph expansion 用に降格する
  - embedding metadata mismatch 時は chunk index も rebuild guard の対象にする
- [x] BM25 sparse lexical index を実装する
  - raw chunk text を document とする
  - char 2-gram / 3-gram analyzer を実装する
  - `StoreGroup` / `ActionContext` / `defineStoreGroup` / `flattenRefs` / `doc26.5` / `@core/ui` など identifier/code/path token を壊さず index する
  - BM25 の term frequency / document frequency / length normalization を持つ
  - 手書き `if token in haystack` を BM25 leg へ置き換える
- [x] `QueryPlan` schema を追加する
  - `intent`
  - `high_level_concepts`
  - `low_level_entities`
  - `expected_source_areas`
  - `disambiguation_hints`
  - `must_include_identifiers`
  - `question_type`
- [x] LLM query planner を実装する
  - provider: `template` / `codex` / `claude`
  - Codex / Claude provider では structured output schema を使う
  - LLM failure 時は template planner に degrade する
  - planner output は retrieval query expansion にだけ使い、source truth にはしない
- [x] hybrid retriever を実装する
  - dense vector search over raw chunks
  - BM25 search over raw chunks
  - concept index search
  - graph entity / relation expansion
  - chapter / cluster expansion
  - community report 本体は Phase 9 の production 実行経路化で扱う
  - explicit file / working target hints
- [x] rank fusion を実装する
  - RRF などで vector / BM25 / graph proximity / explicit hint を統合する
  - source freshness / source_hash / stale state を score に反映する
  - 取得上限と diversity by document / chapter を持たせる
- [x] `InjectionContext` の source evidence を raw chunk 根拠に変更する
  - `source_spec_constraints` / `related_source_sections` に `excerpt` と `source_span` を含める
  - heading だけの evidence を避ける
  - graph / anchor hit は対応 chunk へ戻して本文 evidence を添える
- [x] Agentic search candidate validation と raw chunk retrieval を統合する
  - 既存の `source_span` / `excerpt` validation を通常 retrieval path にも適用する
  - ambiguous excerpt / missing span は ReviewNotes に落とす
  - Answer phase は raw source read に逃げず、retrieved evidence の不足を `NeedMoreContextResult` として返す
- [x] `query_tokens()` / `token_match_score()` 依存を撤去または低優先 fallback 化する
  - retrieval 主経路から `token in haystack` を消す
  - retrieval 主経路からは撤去済み
  - remaining use は Classification fallback / Concept index の既存実装に残るため、Phase 9 で通常実行経路から降格する
- [x] config を追加する
  - `[retrieval] chunk_size`
  - `[retrieval] chunk_overlap`
  - `[retrieval] vector_top_k`
  - `[retrieval] bm25_top_k`
  - `[retrieval] graph_expansion_hops`
  - `[retrieval] rank_fusion`
  - `[query_planner] provider`
  - `[query_planner] timeout / retry / fallback`
- [x] regression test を追加する
  - 日本語自然文 query `StoreGroup設計原則を確認して、管理画面仕様で守るべき制約を教えて` で doc20 / doc27 / doc31 由来の evidence が出ること
  - 空白を入れない日本語 query でも BM25 n-gram と vector で拾えること
  - API / 型名 query `defineStoreGroup flattenRefs ActionContext` で exact identifier を拾えること
  - heading にないが本文にある語句を raw chunk retrieval が拾うこと
  - `source_span` / `excerpt` が source file 上で検証できること
  - BM25 index rebuild / chunk hash change / embedding metadata mismatch を検出できること
- [x] self project smoke を更新する
  - `テスト用ドキュメント/**/*.md` を source にする
  - `spec-core --all`
  - `spec-inject "StoreGroup設計原則を確認して、管理画面仕様で守るべき制約を教えて"`
  - `spec-realign "StoreGroup設計原則を確認して、管理画面仕様で守るべき制約を教えて"`
  - raw chunk evidence / graph expansion / BM25 hit / vector hit の内訳を artifact に残す
- [x] `doc/PHASE8_REPORT.ja.md` を作成する
  - 実装結果
  - 検証結果
  - retrieval architecture
  - パターンマッチ撤去範囲
  - 残リスク

完了条件: raw document chunks と AI-extracted knowledge graph の両方を使った hybrid retrieval が動作し、日本語自然文 query でも `excerpt` / `source_span` 付きの根拠が `InjectionContext` に入り、手書き substring pattern matching が retrieval 主経路から外れている。

### Phase 9. production 実行経路化 / smoke fallback 主経路からの撤去

目的: Phase 8 で整備した retrieval の上に、現在 smoke / fallback として残っている deterministic / template / rule_based / source_derived / stable_hash の主経路利用をやめ、一般的な GraphRAG 運用で使える production 実行経路を成立させる。

現状: smoke 互換の config では、fresh project smoke を優先して `extraction.mode = "deterministic"`、`answer.provider = "template"`、`classification.provider = "orchestrator_rule_based"`、`concept_diff.provider = "source_derived"`、`embedding.provider = "stable_hash"` を使える。これは配布確認には有効だが、実運用品質の GraphRAG ではない。Phase 9 では通常 project config を production 品質として扱い、smoke は config profile ではなく CI / fresh install 確認用の明示モードに限定する。

方針:

- deterministic DOCUMENT / CHAPTER / SECTION / CONTAINS は構造同期として維持する
- AI-extracted knowledge graph は `schema_llm` extraction を production 主経路にする
- `stable_hash` embedding は smoke / unit test 専用にし、通常実行経路では実 embedding provider を必須にする
- `template` answer、rule-based classification、source-derived concept diff は production 主経路にしない
- fallback が発動した場合は `warnings` / `degraded_components` / run artifact に必ず記録する
- 通常実行経路では必要 provider が未設定または未導入なら fail-fast する
- smoke は CI と fresh install 確認用に残すが、README で品質評価対象外と明示する
- `local` profile は作らない。開発者PCで本番品質経路を動かす場合も production とし、Ollama / Codex / Claude などの provider 設定で実行場所を表現する

- [x] production policy schema を追加する
  - 通常 `.spec-grag/config.toml` は production 品質の config として扱い、local / smoke 用の config profile は導入しない
  - smoke は `scripts/setup_project.py --smoke`、`SPEC_GRAG_SMOKE=1`、専用 test fixture など、通常 config と別の明示経路だけで許可する
  - production では `stable_hash` / `template` / `orchestrator_rule_based` / `source_derived` / deterministic-only extraction を禁止する
  - production では `[llm]` と選択 provider の `model` を必須にする
  - production では silent fallback を禁止し、必要 provider が未設定・未導入・失敗した場合は fail-fast する
- [x] setup / template を production / smoke 明示モードに対応させる
  - `scripts/setup_project.py --smoke` と production 向け `templates/.spec-grag/config.toml` を分離する
  - 通常の `scripts/setup_project.py` は production 向け config を生成する
  - 通常 config は `[llm].provider = "codex_cli" | "claude_cli"` を生成系 LLM の外部契約とし、stage 個別 provider を書かずに全 LLM stage へ継承させる
  - default model は Codex CLI catalog の `gpt-5.4` と Claude Code full model name `claude-sonnet-4-6` を使う
  - `scripts/setup_project.py --smoke` は no-deps の CI / fresh install 確認用 config を生成する
  - `scripts/setup_system.py --run-smoke` は smoke script 実行に限定し、project config profile は作らない
  - `templates/.spec-grag/config.toml` は production 向け例にする
  - README / `.spec-grag/README.md` に production 経路と smoke 経路の違い、必要 dependency を明記する
- [x] wheel / pip install 後の template resource 導線を追加する
  - `templates/` と `.codex/commands/*.md` を package data / resource API から確実に取り出せる導線を作る
  - 実装済み: `spec_grag/template_resources.py` と package data `spec_grag/templates/**`
  - 実装済み: wheel / pip install 後に使える `spec-grag-setup-project` console script
  - 実装済み: active `templates/` と packaged resource の一致 regression
  - Codex custom command の実環境読み込み仕様を確認し、frontmatter / command body / fallback CLI 案内を必要に応じて調整する
- [x] schema LLM extraction を production 主経路にする
  - 通常実行経路では `extraction.mode = "schema_llm"` を必須にする
  - heading anchor は structural / debug artifact として扱い、AI-extracted ANCHOR / relation と区別する
  - extraction failure 時は stale graph を混ぜず `failed` または `degraded` にする
  - 残件: 大きな実仕様群で過抽出、未抽出、relation 種別の揺れ、重複 relation を評価し、fixture / report に残す
  - 残件: target grounding の `grounding_score_threshold` / `grounding_score_margin` を実 embedding と実 LLM 抽出結果で再評価し、曖昧候補が graph に混入しないことを regression test にする
  - 残件: Codex / Claude provider の structured output fixture と integration test を追加する
- [x] embedding provider を production 品質にする
  - 通常実行経路では実 embedding provider と dimension を必須検証する
  - `stable_hash` は unit test / smoke 明示モードのみ許可する
  - embedding metadata mismatch 時の rebuild guard を raw chunk index / concept index / graph entity vector に横断適用する
  - provider unavailable / dimension mismatch / retry exhaustion の error handling を通常実行経路 / smoke 明示モードで分けて定義する
- [x] classification を LLM 主経路にする
  - 通常実行経路では `[llm].provider` から解決された `classification.provider = "codex" | "claude"` を必須にする
  - rule-based classifier は fallback / debug annotation に限定する
  - `classify_context_item_rule_based()`、`is_target_query()`、`query_tokens()`、`token_match_score()` による target intent / relevance 判定を通常実行経路から外す
  - `("見直", "修正", "変更", "target", "update")` のような固定語彙による intent 判定は smoke / debug 専用に降格し、通常実行経路では LLM classification の structured output を使う
  - LLM fallback 発動時は `review_required=true`、`classification_fallback_reason`、`degraded_components` を必ず出す
  - 4 軸分類の golden fixture を増やす
- [x] answer generation を LLM 主経路にする
  - 通常実行経路では `[llm].provider` から解決された `answer.provider = "codex" | "claude"` を必須にする
  - `template` answer は smoke / test 専用にする
  - 通常実行経路では `failure_fallback = "template"` を禁止する
  - 残件: Answer LLM 実機 smoke と schema violation recovery test を追加する
  - 残件: 実運用ログを使って Answer prompt が ConstraintContext / TargetContext / ConflictNotes / ReviewNotes を落とさないことを評価する
- [x] Concept diff を LLM proposal 主経路にする
  - 通常実行経路では `[llm].provider` から解決された `concept_diff.provider = "codex" | "claude"` を必須にする
  - `source_derived` append は fallback / seed candidate に降格する
  - 残件: 既存 Concept との重複、言い換え、矛盾、削除提案を LLM proposal schema に含める
  - 残件: pending diff validation / accept / reject / revise / apply の E2E を通常実行経路で通す
- [x] semantic conflict candidate を強化する
  - deterministic rule pack は hard validator として維持する
  - LLM は semantic conflict candidate / uncertainty candidate を生成する
  - LLM 候補だけでは `conflict=true` に昇格せず、ReviewNotes または人間承認待ちにする
  - 実装済み: LLM semantic candidate 単体では hard conflict に昇格せず ReviewNotes に落ちる regression
  - 実装済み: 日本語仕様文の矛盾、権限範囲、状態遷移、数量条件の regression fixture
- [x] community / cluster artifact を一般的な GraphRAG 寄りにする
  - 実装済み: `label_propagation_v1` community cluster
  - 実装済み: community report / chapter report の LLM 生成
  - 実装済み: report に source evidence、covered chunks、staleness、confidence を保持
  - 実装済み: retrieval で raw chunk hit + graph expansion + community report を扱う
  - 実装済み: `cluster_matches()` の `query_tokens()` / `token_match_score()` 補助判定は smoke のみ許可
- [x] Concept index retrieval を production 品質にする
  - `retrieve_concept_chunks()` の `stable_embedding()` + `token_match_score()` scoring を通常実行経路から外す
  - Concept chunk も実 embedding provider metadata に従って dense retrieval し、必要なら BM25 sparse leg / LLM query planning と rank fusion する
  - `stable_hash` / stable embedding は smoke / unit test 専用にする
- [x] fallback 可視化を追加する
  - `ResultEnvelope.warnings` に fallback 種別を安定コードで出す
  - `degraded_components` に extraction / embedding / retrieval / classification / answer / concept_diff を分けて入れる
  - 実装済み: run artifact に provider、model、runtime_mode を保存する
  - 実装済み: run artifact に `fallback_events`、`degraded_components`、`retrieval_summary` を保存する
  - 実装済み: smoke/fallback provider と warning fallback が artifact に残る regression
- [x] fallback 運用検査を追加する
  - 実装済み: `degraded_components` を extraction / embedding / retrieval / classification / answer / concept_diff の安定 component 名へ統一する regression
  - 実装済み: 通常実行経路の smoke/fallback 混入を検出する CI guard
- [x] 既存 smoke tests と production tests を分離する
  - smoke tests は fresh install と契約維持だけを確認し、品質評価に使わない
  - production tests は mock LLM / mock embedding で実 provider path を通す
  - 残件: optional real-provider smoke は Codex / Claude / Ollama がある場合だけ実行する
  - `uv run --isolated ...` を標準 test runner として維持しつつ、editable install 後の素の `pytest` が通るか、または非サポートとして README / setup output に明記する
  - `tests/test_phase9_production_policy.py` を追加する
- [ ] self project を production 実行経路で通す
  - `テスト用ドキュメント/**/*.md` を source にする
  - 実装済み: repo root の `.spec-grag/config.toml` を production policy を通る設定に切り替える
  - 実装済み: 旧 smoke 設定を `.spec-grag/config.smoke.toml` に退避する
  - 実装済み: 現環境へ Ollama `bge-m3` を導入し、repo-local production config を `bge-m3` / `dimension = 1024` に切り替える
  - 検証済み: production config validation と `bge-m3` embedding probe（1024 次元）は通過する
  - 確認済み: 既存 `.spec-grag/graph/` 生成物は過去 smoke の `stable_hash` metadata のため、production full run では `--all` rebuild が必要
  - 実施済み: 小さい source subset の一時 project で LLM token 消費を見積もる
    - `spec-core --all`: 4 turns / total 56,425 tokens / `degraded`（pending Concept diff 作成）
    - no-change incremental: 1 turn / total 12,330 tokens / `ok`
    - `spec-inject`（classification max_items=8）: 10 turns / total 116,520 tokens / `ok`
    - `spec-realign`（classification max_items=8）: 11 turns / total 137,724 tokens / `blocked` NeedMoreContext
  - 残件: repo-local `テスト用ドキュメント/**/*.md` production config で `spec-core --all`
  - 残件: repo-local production config で `spec-inject` / `spec-realign`
  - fallback が発動していないか、発動した場合は理由が artifact に出ることを確認する
- [x] `doc/PHASE9_REPORT.ja.md` を作成する
  - 実装結果
  - 検証結果
  - smoke 明示モードと production 実行経路の差分
  - fallback 撤去 / 降格範囲
  - 残リスク

完了条件: 通常 project config で `spec-core` / `spec-inject` / `spec-realign` を実行したとき、raw chunk hybrid retrieval、schema LLM extraction、実 embedding、LLM classification、LLM answer、LLM concept diff が主経路として動作し、smoke/fallback 実装は test-only または明示的な smoke mode としてのみ使われる。

### Phase 10. watcher / GRAG readiness gate / Concept diff queue 化

目的: 日常利用で `/spec-inject` / `/spec-realign` のたびに重い core incremental を同期実行しない。Source specs の変更は watcher が background incremental で反映し、foreground command は GRAG readiness gate と承認フローを担う。未承認 Concept / Conflict を downstream に混ぜず、production では dirty / pending / stale を fail-fast する。

現状: Phase 9 で production 主経路と provider policy は整備済み。no-change / format-only は semantic hash で数秒に短縮済み。ただし、日常運用では意味変更時の extraction / embedding / community refresh に時間がかかるため、watcher による background incremental が必要である。Phase 10 で readiness gate、watch state / queue schema、provisional cache、単一 pending、承認 transport、watcher 実行中変更の queue 化、queue drain、running / queued state の readiness gate 統合を実装済みである。

方針:

- execution role を分ける
  - foreground human: 人が実行した `/spec-core` / `/spec-inject` / `/spec-realign`
  - background watcher: file watch から起動する core incremental
  - CI / watcherなし: 非常駐環境での foreground incremental
  - production: 自動更新・自動承認を行わない fail-fast 環境
- GRAG readiness gate で `fresh` / `dirty` / `pending` / `stale` を判定する
- local daily mode では watcher required とし、`/spec-inject` / `/spec-realign` は同期 core 更新を行わない
- CI / watcherなし mode では foreground incremental を許可する
- production mode では dirty / pending / stale があれば自動修復せず fail-fast する
- Concept diff は単一 pending とする
- pending Concept diff がある間の追加変更は queued change と provisional concept cache に保存する
- pending 解消後、queued change を最新 Concept base hash と最新 Source specs で再評価する
- provisional concept cache は差分検出・重複抑制・再評価効率化専用とし、未承認 Concept として InjectionContext / Answer / Conflict 確定に使わない
- foreground `/spec-core` は `/spec-inject` / `/spec-realign` と同じく pending 承認フローを出す
- background watcher は承認プロンプトを出さず、pending / queue / cache を保存して停止する

- [x] runtime config / policy resolver を追加する
  - `[runtime].mode = "local_daily" | "ci" | "production"` を扱う
  - `watcher_required` / `foreground_incremental` / `fail_fast_on_dirty` の mode 既定値と明示上書きを解決する
  - `[watcher]` の `enabled` / `interval_ms` / `debounce_ms` / `stale_lock_ms` / `state_file` / `queue_file` を strict schema で検証し、watcher 実行時設定として使う
  - production では dirty / pending / stale を自動修復できないよう guard する
  - `ResultEnvelope` / run artifact に resolved runtime policy を残す
- [x] GRAG readiness gate を実装する
  - source manifest、semantic hash、graph artifact、embedding metadata、schema / prompt / provider version、pending state を横断して `fresh` / `dirty` / `pending` / `stale` を判定する
  - `readiness_report` を CoreResult / InjectionContext / RealignResult の artifact に残す
  - stale reason を machine-readable code で出す
- [x] watch state / queue schema を追加する
  - `.spec-grag/state/watch_state.json` に `fresh` / `dirty` / `pending` / `stale`、running / failed、last run id、last processed semantic hash を保存する
  - `.spec-grag/state/watch_queue.json` に pending 中の changed `source_section_id`、semantic hash、reason、detected_at を保存する
  - lock / heartbeat / stale lock の扱いを決め、二重 watcher 起動で artifact を壊さない
- [x] watcher entrypoint の基礎を追加する
  - polling cycle と `--once` で debounce 後に background core incremental を実行する
  - background execution role では承認プロンプトを出さない
  - pending がある場合は新規 Concept diff を作らず queue / provisional cache を更新する
  - provider failure / embedding failure / schema violation は watch_state と run artifact に残す
- [x] core execution role を分離する
  - `run_core_update` 相当 API に foreground / background / CI / production の role を渡せるようにする
  - human foreground `/spec-core` は pending Concept diff / Conflict 候補を確認要求として返す
  - background watcher は pending を作成・更新できるが、承認・適用はしない
  - no-change / format-only fast path は維持する
- [x] `/spec-inject` / `/spec-realign` を readiness gate 経由へ変更する
  - local daily では dirty 時に同期 core 更新せず blocked / watcher waiting を返す
  - CI / watcherなしでは foreground incremental を許可する
  - production では dirty / pending / stale で fail-fast する
  - pending Concept diff が未解決なら InjectionContext / Answer を生成しない
- [x] watcher の最終監視モデルを実装する
  - Source specs の実変更を継続監視し、debounce 後に background incremental を起動する
  - watcher は single worker とし、同時に複数の core incremental を走らせない
  - 1回の incremental は開始時点の snapshot を処理対象とし、実行中の追加変更を同じ run に混ぜない
  - 実行中に検知した追加変更は `.spec-grag/state/watch_queue.json` に `running_change` として保存する
  - run 完了直後に queue / 最新 manifest を再確認し、残変更があれば次サイクルの background incremental を起動する
  - heartbeat を long run 中も更新し、stale lock 誤判定を避ける
- [x] watcher running / queued state を readiness gate に統合する
  - `watch_state.run_state == running` を foreground context generation の blocker として扱う
  - `watch_queue` 非空を foreground context generation の blocker として扱う
  - local daily の `/spec-inject` / `/spec-realign` は watcher running / queued changes 中に InjectionContext / Answer を生成しない
  - production は dirty / pending / stale に加え、watcher running / queued changes でも fail-fast する
  - CI / watcherなしでは watcher state に依存せず foreground incremental を許可する
- [x] Concept diff 単一 pending / queued change を実装する
  - pending Concept diff がある間は新しい diff を多重生成しない
  - queued change は古い diff として保存せず、再評価対象として保存する
  - 承認 apply または修正後の承認 apply 後に queued change を最新 Concept base hash で再評価する
  - 非承認は pending / cache を残し、次回も同じ承認を求める
  - base hash mismatch では apply を blocked にする
- [x] provisional concept cache を実装する
  - label、normalized label、aliases、supporting sections、semantic hashes、confidence、provider / model / prompt version、first_seen / last_seen を保存する
  - 非承認時は cache / pending を残し、次回コマンドで同じ承認を求める
  - approved Concept / provisional を novelty gate で区別する
  - provisional cache が InjectionContext / Answer / ConflictNotes に混入しない regression を追加する
- [x] Conflict candidate state を readiness gate に統合する
  - `/spec-core` が Source specs 全体から source-level Conflict candidate を検出し、`pending_conflict_review` を自動生成する
  - 未承認 Conflict 候補は pending / ReviewNotes として扱う
  - accept / reject / defer の永続化状態を readiness report に出す
  - `pending_conflict_review` の chat approval transport と `approved_conflicts` sidecar 適用を実装する
  - LLM 候補だけでは確定 Conflict に昇格しない regression を維持する
- [x] Phase 10 readiness / approval E2E / regression test を追加する
  - pending Concept diff 中に source 追加変更しても diff が多重生成されない
  - pending 解消後に queued section が再評価される
  - provisional cache が未承認 Concept として downstream context に入らない
  - local daily dirty で `/spec-inject` / `/spec-realign` が同期 core を走らせない
  - CI mode では watcherなしでも foreground incremental が走る
  - production mode では dirty / pending / stale が fail-fast する
  - foreground `/spec-core` が pending 承認フローを返す
  - background watcher が承認プロンプトを出さない
- [x] watcher 最終監視 E2E / regression test を追加する
  - watcher 常駐実行が Source specs 変更を検知して background incremental を起動する
  - watcher 実行中の追加変更が現 run に割り込まず `watch_queue` に保存される
  - run 完了後に queued change が次サイクルで処理される
  - watcher running / queued changes 中の local daily `/spec-inject` / `/spec-realign` が blocked になる
  - watcher running / queued changes 中の production command が fail-fast する
  - pending Concept diff がある間は watcher が新規 diff を多重生成せず queue / provisional cache に積む
- [x] documentation / report を最終 watcher 仕様で更新する
  - `doc/EXTERNAL_DESIGN.ja.md` との差分があれば同期する
  - `doc/DESIGN.ja.md` に watch_state / queue / provisional cache / readiness gate の内部設計を追加する
  - `doc/AUDIT_TODO.ja.md` の Phase 10 関連 TODO に実装証跡を追記する
  - `doc/PHASE10_REPORT.ja.md` を作成する

完了条件: local daily mode では watcher が Source specs の変更を継続監視し、background incremental で処理する。watcher 実行中の追加変更は現 run に割り込まず queue に積まれ、run 完了後の次サイクルで処理される。`/spec-inject` / `/spec-realign` は同期 core 更新を行わず、dirty / watcher running / queued / pending / stale では InjectionContext / Answer を生成しない。Concept diff は単一 pending に制限され、pending 中の変更は queue / provisional cache で再評価される。CI / watcherなしでは foreground incremental が可能で、production では dirty / watcher running / queued / pending / stale が fail-fast する。

### Phase 11. stage timings / performance observability

目的: `spec-core` / `spec-inject` / `spec-realign` の実行時間を stage 別に可視化し、performance tuning、watcher 効果測定、監査前のボトルネック特定を推測ではなく artifact ベースで行えるようにする。

現状: no-change / format-only / semantic change の実測値はあるが、run artifact には stage 別 wall time がない。そのため、`schema_llm_extraction`、embedding、Concept diff、community report、artifact write のどこが何割を占めたかを後から正確に比較できない。Phase 11 では外部契約を大きく変えず、診断情報として `stage_timings` と `timing_summary` を追加する。

方針:

- 計測には `time.perf_counter_ns()` の monotonic clock を使う
- 初期実装は run artifact / execution diagnostics に限定し、source本文、prompt本文、LLM応答本文は保存しない
- duration と count を優先し、cache hit / affected graph metrics は意味が固まったものから段階的に追加する
- `stage_timings` は詳細配列、`timing_summary` は比較しやすい集計値とする
- stage 名は machine-readable な snake_case に固定する
- no-change / format-only fast path の計測オーバーヘッドを小さく保つ
- Phase 10 の readiness gate / watcher / queue / provisional cache と衝突しない診断層として実装する

- [ ] timing data model を追加する
  - `stage_timings[]` に `stage`、`duration_ms`、`status`、任意 metrics を持たせる
  - `timing_summary` に `total_duration_ms`、`heavy_path`、`semantic_noop`、`llm_call_count`、`llm_total_duration_ms`、`embedding_total_duration_ms`、`community_total_duration_ms` を持たせる
  - stage 名の候補: `config_load`、`manifest_reconcile`、`semantic_noop_filter`、`readiness_gate`、`stale_carry_forward`、`schema_llm_extraction`、`embedding_update`、`chunk_index_update`、`graph_sidecar_update`、`concept_diff`、`conflict_review`、`community_report`、`retrieval`、`classification`、`answer_generation`、`artifact_write`
- [ ] lightweight timer utility を実装する
  - context manager で stage duration を記録する
  - nested stage を許容するか、初期実装では flat stage に限定するか決める
  - exception / blocked / degraded 時も終了済み stage を artifact に残す
  - retry がある stage は attempt count を記録できるようにする
- [ ] LLM / embedding call metrics を集計する
  - LLM stage に `llm_calls`、`provider`、`model`、`input_sections`、必要なら `candidate_count` を残す
  - embedding stage に `input_chunks`、`input_nodes`、`provider`、`model`、`dimension` を残す
  - token usage は provider / CLI から取得できる場合だけ `token_usage` として保存し、取得できない場合は未設定にする
- [ ] core path へ stage timings を入れる
  - no-change / format-only: manifest / semantic noop / artifact write が見えること
  - semantic change: extraction / embedding / graph / concept diff / community report が見えること
  - pending Concept diff / queued change / provisional cache の処理時間が見えること
- [ ] inject / realign path へ stage timings を入れる
  - readiness gate
  - retrieval / query planner
  - classification
  - answer generation
  - NeedMoreContext / blocked 時も timings を保存する
- [ ] run artifact に保存する
  - top-level に `timing_summary` と `stage_timings` を追加する
  - `execution` 側にも同等情報を持たせるか、run artifact 専用にするかを決める
  - pretty output へ出す場合は要約だけにする
- [ ] regression test を追加する
  - no-change `spec-core` artifact に `manifest_reconcile` と `artifact_write` が出る
  - format-only `spec-core` artifact で `schema_llm_extraction` が 0 call / absent になる
  - semantic change `spec-core` artifact に `schema_llm_extraction` と `embedding_update` が出る
  - blocked / failed でも完了済み stage timings が残る
  - artifact に source本文 / prompt本文 / LLM応答本文が混入しない
- [ ] 実測プロトコルを残す
  - no-change
  - format-only change
  - 1 section semantic change
  - 10 section semantic change
  - pending Concept diff 中の queued change
  - `spec-inject`
  - `spec-realign`
- [ ] documentation / report を更新する
  - `doc/AUDIT_TODO.ja.md` に timing artifact を監査証跡として使う方針を追記する
  - `doc/PHASE11_REPORT.ja.md` を作成し、各ケースの stage 比率を記録する

完了条件: run artifact から `spec-core` / `spec-inject` / `spec-realign` の stage 別 duration、LLM call 数、embedding 入力数、heavy path / semantic noop の有無を確認できる。no-change / format-only / semantic change / blocked / failed の各ケースで timings が残り、Phase 10 の watcher や後続監査で性能改善効果を比較できる。

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
- `doc/PHASE7_REPORT.ja.md`: Phase 7 の完了報告
- `doc/PHASE8_REPORT.ja.md`: Phase 8 の完了報告
- `doc/PHASE9_REPORT.ja.md`: Phase 9 production policy gate の実行報告
- `doc/PHASE10_REPORT.ja.md`: Phase 10 watcher / readiness gate の実行報告
- `doc/PHASE11_REPORT.ja.md`: Phase 11 stage timings / performance observability の実行報告
- `BAK/doc/TODO.md.pre-phase1-verification-20260429`: 旧フェーズ管理 TODO
- `doc/CLAUDE_NOTES.md`: 作業メモと過去の手戻り
