# SPEC-grag 設計判断表

本書は、`doc/EXTERNAL_DESIGN.ja.md` を詳細設計へ落とす前に、外部要件、採用済み判断、未決定事項、詳細設計への反映先を整理するための台帳である。

`doc/DESIGN.ja.md` を再構成するときは、本書で `採用済み` または `暫定採用` になっている判断だけを詳細設計本文へ反映する。`未決定` の項目を、詳細設計で確定事項として書いてはいけない。

## 1. 本書の役割

### 1.1 Source of Truth

| 文書 | 役割 |
|---|---|
| `doc/EXTERNAL_DESIGN.ja.md` | 外部契約の source of truth。ユーザー向けコマンド、入力、出力、停止条件を定義する |
| `doc/DESIGN_DECISIONS.ja.md` | 外部契約を内部設計へ落とす前の設計判断台帳 |
| `doc/DESIGN.ja.md` | 本書で合意した判断を実装可能な内部設計へ展開する文書 |
| `doc/DESIGN_old.md` / `doc/DESIGN.md` | 参考資料。確定済み設計として扱わない |

### 1.2 判断ステータス

| Status | 意味 | 詳細設計への扱い |
|---|---|---|
| 採用済み | 外部設計または会話で合意済み | 詳細設計へ反映してよい |
| 暫定採用 | 現時点の推奨。後で差し替え可能 | 詳細設計には暫定であることを明記する |
| 未決定 | まだ議論が必要 | 詳細設計で確定事項として書かない |
| 却下 | 採用しないと判断済み | 詳細設計に残さない。必要なら却下理由だけ記録する |
| 調査必要 | 外部仕様や実装 API の確認が必要 | 調査結果が出るまで詳細設計へ断定しない |

### 1.3 詳細設計を書く前の規則

詳細設計は、次の順で作る。

```text
外部設計の要件
  -> 本書の Requirements Traceability
  -> 本書の Design Decisions
  -> 未決定事項の合意
  -> doc/DESIGN.ja.md への反映
```

次の書き方は禁止する。

```text
GraphRAG-rs ができそうだから詳細設計に書く
既存の DESIGN_old.md にあるから詳細設計に書く
LLM provider / embedding / storage を GRAG と一語でまとめる
未決定の provider や storage を標準構成として断定する
```

## 2. Requirements Traceability

| Req ID | 外部要件 | 根拠 | 内部設計で満たすべきこと | Status |
|---|---|---|---|---|
| R-001 | 目の前の資料への過剰アンカーを避ける | 外部設計 1章 | 生テキストを丸ごと最終コンテキストにせず、制約側 / 修正対象側 / 無関係 / 競合 / レビューに分類する | 採用済み |
| R-002 | Purpose は常に制約側 | 外部設計 1章, 5.4 | `Purpose` は `ConstraintContext` にのみ入れる。`TargetContext` には入れない | 採用済み |
| R-003 | Concept は制約側にも修正対象側にもなり得る | 外部設計 3.3, 5.4 | Query-time classification で `concept_constraints[]` と `related_concepts[]` のどちらか、または両方に分類する | 採用済み |
| R-004 | Source specs は制約側にも修正対象側にもなり得る | 外部設計 3.3, 5.4 | `source_spec_constraints[]` と `related_source_sections[]` の分類理由を別々に保持する | 採用済み |
| R-005 | `/spec-core` は GRAG 更新と Concept 保守を行う | 外部設計 4章 | incremental / full rebuild、Concept diff、CoreResult を独立した内部フローとして設計する | 採用済み |
| R-006 | `/spec-inject` は回答を生成しない | 外部設計 5章 | `InjectionContext` だけを出力し、Answer を作らない | 採用済み |
| R-007 | `/spec-realign` は `/spec-inject` 相当の後に Answer を作る | 外部設計 6章 | `RealignResult = task_prompt + injection_context + answer` とし、Context を再定義しない | 採用済み |
| R-008 | `/spec-inject` と `/spec-realign` は最初に incremental 更新を行う | 外部設計 3.2, 5.3, 6.3 | 両コマンドの先頭に `/spec-core` 相当の incremental 処理を置く | 採用済み |
| R-009 | Concept diff 未承認時は停止する | 外部設計 4.5, 5.3, 6.3, 9章 | `InjectionContext` / `Answer` を生成せず、accept / reject / 修正指示を要求する | 採用済み |
| R-010 | 設定ファイルは対象プロジェクト直下 `.spec-grag/config.toml` 固定 | 外部設計 3.1, 7章 | 親方向探索をしない。対象プロジェクトルートで実行する | 採用済み |
| R-011 | 章本文は読めるが、無分類で最終注入しない | 外部設計 3.5 | Agentic search と根拠確認では読む。最終出力は構造化された `InjectionContext` に限定する | 採用済み |
| R-012 | `InjectionContext` の形を外部契約に合わせる | 外部設計 5.4, 8.1 | 詳細設計のスキーマは 8.1 と一致させる | 採用済み |
| R-013 | `CoreResult` の形を外部契約に合わせる | 外部設計 8.3 | `mode`, `updated_sources[]`, `skipped_sources[]`, `failed_sources[]`, `graph_storage`, `freshness_report`, `concept_diff?`, `warnings[]` を返す | 採用済み |
| R-014 | LLM provider 実装詳細は外部設計では扱わない | 外部設計 10章 | 詳細設計で provider 境界を定義する。ただし本書で合意してから書く | 採用済み |
| R-015 | GRAG 内部、抽出器、永続化形式は詳細設計に委ねる | 外部設計 10章 | 本書で採用判断と未決定事項を分けた後、詳細設計に展開する | 採用済み |

## 3. Command-Level Decisions

### 3.1 `/spec-core`

| Decision ID | 判断 | Status | 理由 | 詳細設計への反映 |
|---|---|---|---|---|
| C-CORE-001 | `/spec-core` は GRAG 更新と Concept diff 生成だけを行い、InjectionContext や Answer を作らない | 採用済み | 外部設計 4章の責務に合わせる | `/spec-core` 内部フロー |
| C-CORE-002 | 通常実行は changed Source specs のみを対象にする | 採用済み | 外部設計 3.2, 4.3 | SourceSectionRecord と content hash 比較 |
| C-CORE-003 | `--all` / `-a` のみ全再構築を行う | 採用済み | 外部設計 3.2, 4.3 | full rebuild フロー |
| C-CORE-004 | Concept diff は hunk 単位で accept / reject / 修正指示を受ける | 採用済み | 外部設計 4.5 | Concept approval state |
| C-CORE-005 | Concept 更新候補の生成にどの LLM provider を使うか | 未決定 | Codex CLI / Claude CLI / API / Ollama の境界が未合意 | LLM provider 章 |

### 3.2 `/spec-inject`

| Decision ID | 判断 | Status | 理由 | 詳細設計への反映 |
|---|---|---|---|---|
| C-INJ-001 | `/spec-inject` は `InjectionContext` のみを返す | 採用済み | 外部設計 5.1, 5.4 | output schema |
| C-INJ-002 | 明示プロンプトがない場合も ConversationContext から中心クエリを推定する | 採用済み | 外部設計 3.3, 5.2 | ConversationContext parser |
| C-INJ-003 | Agentic search は検索候補を作るために使い、最終コンテキストへ生本文を入れない | 採用済み | 外部設計 3.5 | query candidate extraction |
| C-INJ-004 | ConstraintContext と TargetContext は同じ候補集合から分類する | 採用済み | Concept / Source specs が両側になり得るため | query-time classifier |
| C-INJ-005 | 分類器を LLM で行うか、ルール + LLM にするか | 未決定 | 品質、速度、再現性の議論が必要 | classifier design |

### 3.3 `/spec-realign`

| Decision ID | 判断 | Status | 理由 | 詳細設計への反映 |
|---|---|---|---|---|
| C-REAL-001 | `/spec-realign` は `/spec-inject` と同じ手順で `InjectionContext` を作る | 採用済み | 外部設計 6.3 | `/spec-realign` flow |
| C-REAL-002 | `RealignResult` は `InjectionContext` を再利用し、ConstraintContext / TargetContext を再定義しない | 採用済み | 外部設計 6.4 | output schema |
| C-REAL-003 | Answer は `task_prompt` と `InjectionContext` だけを入力にする | 採用済み | 外部設計 6.5 | Answer generator |
| C-REAL-004 | Answer で競合や人間レビュー項目を隠さない | 採用済み | 外部設計 6.5 | Answer contract |

## 4. System Boundary Decisions

| Decision ID | 領域 | 判断 | Status | 理由 |
|---|---|---|---|---|
| S-001 | 所有者 | 仕様判断、分類、承認状態、出力契約は `spec-grag` が所有する | 採用済み | GraphRAG-rs は仕様判断の source of truth ではない |
| S-002 | GraphRAG-rs | `graphrag-rs` は部品として使う。外部コマンドの振る舞いを所有させない | 採用済み | 外部設計のコマンド契約を守るため |
| S-003 | LLM | LLM は抽出、分類、検証、回答生成に使えるが、Purpose 更新や Concept 自動確定はできない | 採用済み | 外部設計 3.4 |
| S-004 | Human | Concept diff の最終確定、レビュー必要項目の判断は人間が行う | 採用済み | 外部設計 4.5, 9章 |
| S-005 | Adapter | Codex skill / Claude command は共通 CLI 契約の adapter に留める | 暫定採用 | agent 固有プロンプトを source of truth にしないため |

## 5. LLM Generation Decisions

LLM 生成は、次を分けて扱う。

```text
Build-time LLM:
  AtomicFact 抽出
  ChapterAnchor / Concept 更新候補
  edge validation

Query-time LLM:
  ConversationContext 要約
  制約側 / 修正対象側 / 無関係 / 競合 / レビュー分類
  Answer 生成
```

| Decision ID | 判断 | Status | 理由 | 未決定事項 |
|---|---|---|---|---|
| LLM-001 | `CodexCliLanguageModel` を主担当候補にする | 暫定採用 | ユーザーは Codex 主担当で進めたい意向。外部設計の例も `provider = "codex_cli"` | CLI 入出力形式、timeout、再試行、JSON 抽出方法 |
| LLM-002 | `ClaudeCliLanguageModel` は同じ抽象 interface の別 provider とする | 暫定採用 | Claude command と Codex skill の違いを adapter に閉じ込めるため | 同じ prompt contract で安定するか |
| LLM-003 | Ollama は local backend 候補に留める | 暫定採用 | GraphRAG-rs の主要 LLM 抽出器と互換する可能性はあるが、ユーザーはサブスクモデル利用を望む | Ollama を標準にするか、fallback にするか |
| LLM-004 | API 型 LLM provider を初期実装に入れるか | 未決定 | サブスク CLI と API 課金モデルは運用が異なる | OpenAI / Anthropic API を対象にするか |
| LLM-005 | LLM 抽出器は provider-agnostic service として設計する | 暫定採用 | GraphRAG-rs の特定 client に詳細設計を縛らないため | 既存 GraphRAG-rs extractor を直接使う範囲 |

詳細設計に書くときは、次を混ぜない。

```text
生成 LLM provider
埋め込み provider
GraphRAG-rs の extractor 実装
Codex / Claude の agent adapter
```

## 6. Embedding Decisions

埋め込みは、生成 LLM とは別 provider として扱う。

| Decision ID | 判断 | Status | 理由 | 未決定事項 |
|---|---|---|---|---|
| EMB-001 | 埋め込み provider は `[llm]` ではなく `[embeddings]` として分離する | 採用済み | 生成 LLM と embedding は運用、コスト、API が違う | 設定スキーマ詳細 |
| EMB-002 | 初期標準 provider は未決定とする | 未決定 | OpenAI / Voyage / Cohere / Jina / HuggingFace / Ollama など候補があり、用途と費用で変わる | 日本語仕様書での品質、費用、プライバシー |
| EMB-003 | provider を変えた場合は index rebuild が必要になる可能性を明記する | 暫定採用 | dimension と embedding 空間が変わるため | 既存 index の移行方法 |
| EMB-004 | サブスク CLI モデルを embedding provider として扱わない | 採用済み | Codex CLI / Claude CLI は通常の embedding API ではない | なし |

候補を詳細設計で比較するときは、少なくとも次を比較する。

```text
日本語仕様書での検索品質
API key / subscription / local 実行の運用
dimension
batch size
再構築コスト
データ持ち出し可否
```

## 7. Storage Decisions

外部設計の `[graph].storage = ".spec-grag/graph/"` は保存先ルートであり、物理ストア種別までは決めていない。

### 7.1 論理ストア

| Store | 保存するもの | Status |
|---|---|---|
| Source Registry | SourceSectionRecord, SpecChunk, content hash, freshness | 採用済み |
| Canonical Graph Store | CanonicalNode, CanonicalEdge, EvidenceLink, validation state | 採用済み |
| Vector Store | chunk / node / edge / anchor embedding | 採用済み |
| Cluster Store | ChapterAnchor, hierarchical cluster, community / group metadata | 採用済み |
| Cache Store | query classification cache, LLM response cache, validation cache | 採用済み |
| Audit Log | Concept diff, validation event, user approval event | 採用済み |

### 7.2 物理ストア

| Decision ID | 判断 | Status | 理由 | 未決定事項 |
|---|---|---|---|---|
| STO-001 | 論理ストアを一つの `graph/` ディレクトリ配下に置く | 採用済み | 外部設計の `graph.storage` と整合する | ディレクトリ構造 |
| STO-002 | MVP の metadata / graph store を SQLite にするか | 未決定 | JSONL より query / migration / consistency が扱いやすい可能性がある | SQLite 採用可否 |
| STO-003 | MVP の vector store を LanceDB / Qdrant / SQLite拡張 / GraphRAG-rs内蔵のどれにするか | 未決定 | 運用負荷と検索品質の比較が必要 | 初期標準 |
| STO-004 | Neo4j は初期標準にしない | 暫定採用 | 最初から導入すると運用が重い。複雑な多段探索が必要になった段階で再検討 | 大規模化時の移行 |
| STO-005 | `.spec-grag/graph/` は通常 `.gitignore` 推奨 | 採用済み | 外部設計 7.2 と整合 | 共有したい成果物の扱い |

## 8. GraphRAG-rs Usage Decisions

GraphRAG-rs は、外部契約を満たすための部品として扱う。詳細設計では、直接使う部分、adapter を挟む部分、使わない部分を分ける。

| Decision ID | 対象 | 判断 | Status | 理由 / 注意 |
|---|---|---|---|---|
| GRAG-001 | TextChunk | `SpecChunk` から GraphRAG-rs `TextChunk` へ adapter 変換する | 暫定採用 | chunk 境界の所有者は spec-grag にする |
| GRAG-002 | Chunking | Source specs の章節分割を GraphRAG-rs 汎用 chunking に委譲しない | 採用済み | 章、節、表、仕様IDを壊すと根拠管理が壊れる |
| GRAG-003 | GLiNER | 広域 entity / anchor 候補発見の optional 部品にする | 暫定採用 | LLM 生成ではないため大量処理向き。ただし feature / model 設定確認が必要 |
| GRAG-004 | AtomicFactExtractor | GraphRAG-rs 直接利用か spec-grag 実装かを未決定にする | 未決定 | GraphRAG-rs 側が特定 backend 前提の場合、Codex/Claude と直結できない |
| GRAG-005 | LLMRelationshipExtractor.validate_triple | GraphRAG-rs 直接利用か spec-grag 実装かを未決定にする | 未決定 | fallback が SPEC-grag の検証契約に合うか確認が必要 |
| GRAG-006 | Embeddings | GraphRAG-rs の embedding provider は候補として扱う | 調査必要 | provider 実 API と feature flag を確認してから採用判断する |
| GRAG-007 | Vector / Graph traits | 利用候補にするが、外部出力契約は spec-grag が所有する | 暫定採用 | traits に合わせすぎて `InjectionContext` が歪むことを避ける |
| GRAG-008 | Fork / vendor customization | 初期方針として避ける | 暫定採用 | upstream 追随コストが高い。必要性が証明されてから検討する |

## 9. Classification Decisions

| Decision ID | 判断 | Status | 理由 |
|---|---|---|---|
| CLS-001 | `Purpose` は常に constraint side | 採用済み | 外部設計 5.4 |
| CLS-002 | `Concept` は constraint / target / both / irrelevant のいずれにもなり得る | 採用済み | 外部設計 3.3, 5.4 |
| CLS-003 | `Source specs` は constraint / target / both / irrelevant のいずれにもなり得る | 採用済み | 外部設計 3.3, 5.4 |
| CLS-004 | `ChapterAnchor` は制約探索入口にも修正対象探索入口にもなり得る | 採用済み | 外部設計 1章, 5.4 |
| CLS-005 | `ConflictNotes` と `ReviewNotes` は `InjectionContext` に持つ | 採用済み | `/spec-inject` 単体でも必要 |
| CLS-006 | 分類理由は ConstraintContext / TargetContext の双方に残す | 採用済み | 後から分類妥当性を人間がレビューするため |
| CLS-007 | 分類器の実装方式 | 未決定 | rule-first / LLM-first / hybrid の比較が必要 |

## 10. Open Questions

詳細設計へ進む前に、少なくとも次を決める。

| ID | 未決定事項 | 選択肢 | 決めない場合のリスク |
|---|---|---|---|
| OQ-001 | 初期 LLM provider | Codex CLI / Claude CLI / API / Ollama | 抽出器と回答生成の設計が分岐する |
| OQ-002 | LLM subprocess の出力契約 | JSON strict / markdown + JSON block / tool specific parser | 自動処理が不安定になる |
| OQ-003 | 初期 embedding provider | OpenAI / Voyage / Cohere / Jina / HuggingFace / Ollama | index dimension と rebuild 方針が決まらない |
| OQ-004 | 初期 vector store | Qdrant / LanceDB / SQLite拡張 / GraphRAG-rs内蔵 | `.spec-grag/graph/` の構造が決まらない |
| OQ-005 | 初期 metadata / graph store | SQLite / JSONL / Postgres / Neo4j | canonical graph と approval state の整合性設計が決まらない |
| OQ-006 | GraphRAG-rs を fork するか | fork しない / vendor patch / upstream PR | 保守コストと provider 対応範囲が変わる |
| OQ-007 | AtomicFact / TripleValidation の実装場所 | spec-grag 実装 / GraphRAG-rs 直接 / backend 別 adapter | Codex/Claude 利用可否に直結する |
| OQ-008 | Query-time classifier の方式 | rule-first / LLM-first / hybrid | ドリフト抑制と再現性に影響する |

## 11. 詳細設計への反映手順

`doc/DESIGN.ja.md` を修正するときは、次の順に行う。

```text
1. 本書の `未決定` を議論し、必要なものを `採用済み` または `暫定採用` にする
2. `/spec-core` の内部設計を書く
3. `/spec-inject` の内部設計を書く
4. `/spec-realign` の内部設計を書く
5. LLM generation provider を書く
6. embedding provider を書く
7. storage を logical / physical に分けて書く
8. GraphRAG-rs 直接利用 / adapter / 未使用 / 調査必要を明記する
9. Requirements Traceability の Req ID を詳細設計の該当章に紐づける
```

詳細設計の各章には、最低限次を置く。

```text
対応する Req ID
対応する Decision ID
入力
処理主体
GraphRAG-rs 利用有無
LLM 利用有無
embedding 利用有無
storage 更新有無
出力
停止条件
未決定事項
```

## 12. 次に議論する順番

次の順に決めると、詳細設計のズレが少ない。

1. 初期 LLM provider を決める
2. 初期 embedding provider を決める
3. 初期 metadata / graph / vector store を決める
4. GraphRAG-rs を fork せず使う範囲を決める
5. AtomicFact / TripleValidation を spec-grag 側で実装するか決める
6. Query-time classifier の方式を決める
7. その後に `doc/DESIGN.ja.md` を再構成する
