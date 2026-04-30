# SPEC-grag 詳細設計書

本書は、`doc/EXTERNAL_DESIGN.ja.md` で定義した外部契約を、`spec-grag` CLI、`graphrag-rs`、LLM、エージェントアダプターでどう実現するかを定義する内部設計書である。

外部契約の source of truth は `doc/EXTERNAL_DESIGN.ja.md` である。本書は実装方針、処理責務、データ構造、`graphrag-rs` の利用箇所、LLM の利用箇所を扱う。

## 1. 設計原則

SPEC-grag の目的は、仕様書をそのまま LLM に大量投入することではない。仕様書、Purpose、Concept、ChapterAnchor、関係グラフ、階層クラスタを使い、会話区間または課題プロンプトに対して、次を分類済み文脈として渡すことである。

```text
ConstraintContext
TargetContext
ExclusionNotes
ConflictNotes
ReviewNotes
GRAG Freshness Report
```

最重要の分類規則は次である。

```text
Purpose:
  常に ConstraintContext に属する
  TargetContext には入らない

Concept:
  課題に対して制約として働く場合は ConstraintContext
  課題に対して修正・見直し・検討対象になる場合は TargetContext
  同じ Concept が両方に出る場合もある

Source specs:
  守るべき既存仕様として働く場合は ConstraintContext
  修正対象の章・節として扱う場合は TargetContext
  同じ Source specs が両方に出る場合もある
```

未承認の Concept diff がある場合、`InjectionContext` と `Answer` を生成してはいけない。ユーザーの `accept / reject / 修正指示` を待つ。

## 2. 実行主体

| 主体 | 責務 |
|---|---|
| `spec-grag` | コマンド制御、設定読込、ソース同期、章節ID、状態管理、正規化、マージ、出力契約を持つ |
| `graphrag-rs` | 抽出器、TextChunk 形式、GraphRAG 系の graph / embedding / traversal / clustering 機能を部品として提供する |
| LLM | 原子的事実抽出、曖昧候補の分類、Triple Reflection、Concept 更新候補、Answer 生成を担う |
| 非生成型モデル | GLiNER など。低コストな entity / anchor 候補発見に使う |
| 人間 | Purpose 作成、Concept diff の承認、high risk / conflicting / deprecated 判断の最終承認を行う |
| エージェントアダプター | Codex skill、Claude command など。共通 CLI 出力を各エージェントへ渡す |

`graphrag-rs` は仕様判断の所有者ではない。仕様判断の source of truth は `spec-grag` の正規スキーマ、状態フィールド、根拠リンク、ユーザー承認状態である。

## 3. コマンド対応

外部コマンドは次の内部処理に対応する。

| 外部コマンド | 内部処理 |
|---|---|
| `/spec-core [--all|-a]` | `spec-grag core`。GRAG incremental / full rebuild と Concept 保守を行う |
| `/spec-inject [<課題プロンプト>]` | `spec-grag inject`。`/spec-core` 相当の incremental 後に `InjectionContext` を作る |
| `/spec-realign <課題プロンプト>` | `spec-grag realign`。`InjectionContext` を作り、Answer 生成契約に従って回答を作る |

すべてのコマンドは対象プロジェクトルートで実行され、実行ディレクトリ直下の `.spec-grag/config.toml` を読む。親方向への探索は行わない。

## 4. 設定

設定例:

```toml
[sources]
include = ["docs/spec/**/*.md"]
exclude = ["**/drafts/**"]

[core]
purpose_file = "docs/SPEC-grag/core/purpose.md"
concept_file = "docs/SPEC-grag/core/concept.md"

[graph]
storage = ".spec-grag/graph/"

[llm]
provider = "codex_cli"

[llm.codex_cli]
command = "codex"
model = "gpt-5.4"

[llm.claude_cli]
command = "claude"
model = "sonnet"
```

`Purpose` は読み取り専用である。`Concept` は更新候補を作れるが、ユーザー承認なしに書き換えない。

## 5. 内部データモデル

### 5.1 SourceSectionRecord

Source specs の章節単位の原文記録である。根拠へ戻るための台帳として使う。

```text
source_section_id
source_path
heading_path[]
start_offset
end_offset
content_hash
text
```

### 5.2 SpecChunk

抽出器へ渡す単位である。章節境界、表、箇条書き、仕様IDを壊さない。

```text
spec_chunk_id
source_section_id
source_path
heading_path[]
start_offset
end_offset
content_hash
text
```

### 5.3 graphrag-rs TextChunk Adapter

`SpecChunk` を `graphrag-rs` 抽出器に渡すための adapter である。

```text
SpecChunk
  -> graphrag-rs TextChunk
  -> metadata に source_section_id / content_hash / heading_path を保持
```

ここでは仕様判断を行わない。

### 5.4 AtomicFact

LLM 抽出された原子的事実である。

```text
fact_id
subject
predicate
object
temporal_marker?
confidence
source_section_id
spec_chunk_id
authority
stability
scope
```

AtomicFact は「本文にこう書いてある」という事実主張であり、今回守るべき制約かどうかはまだ決めない。

### 5.5 NormalizedFact

AtomicFact を仕様判断用の型へ正規化したもの。

```text
normalized_fact_id
kind: requirement | constraint | exception | dependency | design_principle | open_issue
subject
relation_type
object
source_fact_ids[]
authority
stability
scope
risk
```

### 5.6 EdgeCandidate

正規グラフへ入れる前の関係候補である。

```text
edge_candidate_id
source_node_id
target_node_id
relation_type
confidence
risk
evidence_fact_ids[]
source_section_ids[]
validation: unvalidated
```

### 5.7 ValidationEvent

Triple Reflection などの検証結果である。

```text
validation_event_id
edge_candidate_id
valid: true | false
confidence
reason
validated_by
validated_at
source_section_ids[]
```

検証は「本文に支持されるか」を見る。今回の課題で制約として採用すべきかはクエリ時に別途分類する。

### 5.8 CanonicalNode / CanonicalEdge / EvidenceLink

正規グラフの source of truth である。

```text
CanonicalNode:
  node_id
  node_type
  canonical_name
  aliases[]
  source_section_ids[]
  authority
  stability

CanonicalEdge:
  edge_id
  source_node_id
  target_node_id
  relation_type
  confidence
  validation
  authority
  stability
  scope
  risk
  evidence_fact_ids[]
  validation_event_ids[]

EvidenceLink:
  evidence_link_id
  target_type: node | edge | context_item
  target_id
  source_section_id
  fact_id?
  snippet_hash
```

### 5.9 InjectionContext

外部設計 5.4 / 8.1 と一致させる。

```text
InjectionContext
  conversation_context_summary
  constraint_context
    purpose_constraints[]
    concept_constraints[]
    source_spec_constraints[]
    chapter_anchor_constraints[]
    classification_notes[]
  target_context
    candidate_targets[]
    related_concepts[]
    related_source_sections[]
    related_chapter_anchors[]
    related_entities[]
    classification_notes[]
  excluded_as_irrelevant[]
  conflict_notes[]
  review_notes[]
  freshness_report
  approved_concept_update?
  warnings[]
```

`approved_concept_update?` は、承認済みの Concept 更新が今回の文脈に影響する場合だけ記録する。未承認 diff は `InjectionContext` に入らない。

### 5.10 RealignResult

外部設計 6.4 / 8.2 と一致させる。

```text
RealignResult
  task_prompt
  injection_context
  answer
```

`answer` は外部設計 6.5 の Answer 生成契約に従う。

### 5.11 CoreResult

```text
CoreResult
  mode: incremental | full
  updated_sources[]
  skipped_sources[]
  failed_sources[]
  graph_storage
  freshness_report
  concept_diff?
  warnings[]
```

`concept_diff?` は `/spec-core` の出力であり、未承認 diff を含み得る。未承認の場合、`/spec-inject` と `/spec-realign` は通常出力へ進まない。

## 6. `/spec-core` 内部フロー

### 6.1 通常実行

```text
/spec-core
  -> .spec-grag/config.toml を読む
  -> Purpose を読む
  -> Concept を読む
  -> Source specs の glob を展開
  -> SourceSectionRecord を作る
  -> content_hash で変更検出
  -> changed SpecChunk だけ処理
  -> GRAG incremental update
  -> Concept 更新候補を生成
  -> Concept diff 判定
  -> CoreResult を出力
```

### 6.2 全再構築

```text
/spec-core --all
  -> Source specs を全件読み込み
  -> 既存 index を rebuild 対象にする
  -> 全 SpecChunk を再処理
  -> GRAG full rebuild
  -> Concept 再生成候補を生成
  -> Concept diff 判定
  -> CoreResult を出力
```

### 6.3 Concept diff

Concept diff がある場合:

```text
accept:
  承認済み Concept として保存する

reject:
  Concept 更新案を採用しない
  ユーザーから修正指示を受け取る
  必要に応じて候補を再生成する

未確認:
  Concept を書き換えない
  /spec-inject と /spec-realign は InjectionContext / Answer 生成へ進まない
```

### 6.4 Source specs 取り込み

`spec-grag` が担当する。

```text
source glob 展開
exclude 適用
Markdown AST 解析
heading_path 生成
source_section_id 採番
content_hash 計算
SpecChunk 生成
graphrag-rs TextChunk へ adapter 変換
```

`graphrag-rs` の汎用 chunking に章節境界の決定を委譲しない。

### 6.5 Build-Time GRAG 構築

```text
SpecChunk
  -> TextChunk adapter
  -> GLiNERExtractor で EntityCandidate / AnchorCandidate
  -> AtomicFactExtractor で AtomicFact
  -> spec-grag normalizer で NormalizedFact
  -> spec-grag edge builder で EdgeCandidate
  -> LLMRelationshipExtractor.validate_triple で ValidationEvent
  -> canonical merge
  -> indexes
```

## 7. 抽出器の使い分け

| 目的 | 使用対象 | 実行時点 | 備考 |
|---|---|---|---|
| 広域候補発見 | `GLiNERExtractor` | 構築時 | 画面、API、Role、Permission、State、DataModel、ChapterAnchor 候補を安く拾う |
| 主事実抽出 | `AtomicFactExtractor` | 構築時 | Source specs を原子的事実へ分解する |
| 取り漏れ対策 | `GleaningEntityExtractor` | 構築時限定 | Concept、用語集、重要章、ChapterAnchor 生成候補に限定して使う |
| 関係検証 | `LLMRelationshipExtractor.validate_triple` | 構築時中心 | edge が原文に支持されるか検証する |
| ベースライン比較 | `LLMEntityExtractor` | PoC / 回帰確認 | 本線の graph source にはしない |

LLM へ委譲してよいこと:

```text
AtomicFact 抽出
曖昧な relation_type の少数分類
Triple Reflection
Concept 更新候補
query-time の少数候補分類
Answer 生成
```

LLM へ委譲してはいけないこと:

```text
Purpose の自動更新
Concept の自動確定
Source specs の無分類投入
validated でない edge の確定扱い
ConstraintContext / TargetContext の出力構造の勝手な変更
```

## 8. 正規化と状態管理

### 8.1 ノード型

| 型ID | 日本語名 |
|---|---|
| Purpose | 目的 |
| Concept | コンセプト / 基本構想 |
| DesignPrinciple | 設計原則 |
| ChapterAnchor | 章別アンカー / 章の主要概念 |
| SpecSection | 仕様セクション / 仕様章節 |
| AtomicFact | 原子的事実 / 最小事実単位 |
| Requirement | 要件 |
| Constraint | 制約 |
| ExceptionRule | 例外ルール |
| Dependency | 依存関係 |
| Conflict | 競合 / 矛盾 |
| OpenIssue | 未解決課題 |
| Screen | 画面 |
| API | API |
| Component | コンポーネント |
| DataModel | データモデル |
| State | 状態 |
| StateTransition | 状態遷移 |
| Role | ロール / 役割 |
| Permission | 権限 |
| Workflow | ワークフロー |
| TestCase | テストケース |
| ChangeRequest | 変更要求 |

### 8.2 エッジ型

| Edge type | 日本語名 |
|---|---|
| SUPPORTS | 支持する / 根拠になる |
| DERIVED_FROM | 派生元である / 由来する |
| MENTIONED_IN | 言及されている |
| ANCHORS | アンカーする / 紐づける |
| IMPLEMENTS | 実装する / 実現する |
| REFINES | 詳細化する / 洗練する |
| PART_OF | 一部である |
| DEPENDS_ON | 依存する |
| CONSTRAINS | 制約する |
| REQUIRES | 必要とする |
| FORBIDS | 禁止する |
| ALLOWS | 許可する |
| EXCEPTS | 例外とする |
| OVERRIDES | 上書きする / 優先する |
| PROTECTS | 保護する |
| AFFECTS | 影響する |
| CONFLICTS_WITH | 競合する / 矛盾する |
| SAME_AS | 同一である |

`related_to` を主要 edge type として使ってはいけない。低信頼の予備候補に限る。

### 8.3 状態フィールド

```text
authority:
  human_approved
  inferred
  document_claim
  candidate

stability:
  stable
  tentative
  deprecated
  conflicting

validation:
  unvalidated
  validated
  rejected
  needs_human_review

risk:
  low
  medium
  high
  critical
```

状態は検索順位、Answer 生成、ReviewNotes 生成に使う。`tentative`、`conflicting`、`needs_human_review` を隠してはいけない。

## 9. `/spec-inject` 内部フロー

`/spec-inject` は `InjectionContext` を作る。回答は作らない。

```text
/spec-inject [<課題プロンプト>]
  -> /spec-core incremental 相当を実行
  -> Concept diff があれば accept / reject / 修正指示を要求
  -> diff 解決済みの場合だけ続行
  -> ConversationContext を取得
  -> Purpose を取得し ConstraintContext の上位制約候補に置く
  -> 承認済み Concept を取得

  共通候補抽出:
    -> Agentic search で関連しそうな章本文を読む
    -> キーワード / エンティティ / 章候補を抽出
    -> GRAG に投げる検索候補を作る

  制約側:
    -> 検索候補から制約探索クエリを作る
    -> GRAG 検索 / グラフ探索
    -> Purpose 由来の上位制約を取得
    -> 課題に対して制約として働く Concept / Source specs を分類
    -> 制約として効く ChapterAnchor を取得

  修正対象側:
    -> 検索候補から修正対象探索クエリを作る
    -> GRAG 検索 / グラフ探索
    -> 関連する Concept / Source specs を取得
    -> 修正対象候補に関係する ChapterAnchor を取得
    -> 修正対象候補に関係する章・節・エンティティを取得

  -> 必要なら根拠 snippet を読む
  -> Agentic search 結果 + GRAG 結果 + snippet を統合
  -> 制約側 / 修正対象側 / 無関係 / 競合 / 人間レビューに分類
  -> InjectionContext を出力
```

### 9.1 Agentic search の位置づけ

Agentic search は Source specs から検索候補を作るために使う。読んだ章本文を無分類のまま LLM コンテキストへ入れてはいけない。

```text
許可:
  関連章の発見
  キーワード抽出
  entity / chapter candidate 抽出
  snippet 候補抽出

禁止:
  章本文の丸ごと注入
  読んだ内容を即制約として固定
  GRAG 検索を飛ばして Answer を作る
```

### 9.2 Query-Time GRAG 検索

`spec-grag` は、Agentic search の候補を使って GRAG 検索を行う。

```text
constraint query:
  Purpose 近傍
  Concept 近傍
  CONSTRAINS / DEPENDS_ON / PROTECTS / FORBIDS / EXCEPTS
  ChapterAnchor
  validated edge

target query:
  Source specs section
  Concept
  Screen / API / Component / DataModel / Role / Permission
  AFFECTS / IMPLEMENTS / PART_OF / MENTIONED_IN
  ChapterAnchor / Cluster
```

### 9.3 LLM classifier

LLM classifier は少数候補だけを分類する。

```text
inputs:
  ConversationContext summary
  task prompt if any
  candidate facts / edges / sections
  evidence snippets
  authority / stability / validation / risk

outputs:
  constraint_context additions
  target_context additions
  excluded_as_irrelevant
  conflict_notes
  review_notes
  classification_notes
```

## 10. `/spec-realign` 内部フロー

`/spec-realign` は 9章の `/spec-inject` 内部フローと同じ手順で `InjectionContext` を生成し、その後 Answer を作る。

```text
/spec-realign <課題プロンプト>
  -> /spec-core incremental 相当を実行
  -> Concept diff があれば accept / reject / 修正指示を要求
  -> diff 解決済みの場合だけ続行
  -> 9章と同じ手順で InjectionContext を生成
  -> Answer 生成契約に従って Answer を生成
  -> RealignResult を出力
```

Answer 生成時の入力は `task_prompt` と `InjectionContext` だけである。`RealignResult` 側で `ConstraintContext` や `TargetContext` を再定義しない。

Answer は少なくとも次を区別する。

```text
今回の回答で守る制約
今回の回答で扱う修正候補または検討対象
競合 / 不確実性 / 人間レビューが必要な点
課題プロンプトへの回答または修正案
```

## 11. Freshness とキャッシュ

`/spec-inject` と `/spec-realign` は、必ず `/spec-core` 相当の incremental 処理を先に行う。

```text
freshness_report:
  graph_storage
  last_core_update
  updated_sources[]
  skipped_sources[]
  failed_sources[]
  degraded: true | false
  warnings[]
```

クエリ時分類はキャッシュできる。ただし、次が変わった場合は無効化する。

```text
task_prompt hash
conversation_context hash
concept hash
source section hash
canonical edge version
classification prompt version
```

## 12. LLM プロバイダー

生成型 LLM 呼び出しは `AsyncLanguageModel` 相当の共通インターフェースを通す。

```text
CodexCliLanguageModel:
  primary provider

ClaudeCliLanguageModel:
  optional provider

AsyncMockLanguageModel:
  tests
```

Codex と Claude は同じ役割を担う。違いは subprocess コマンド、出力パース、モデル設定、timeout、rate limit だけである。

`templates/.claude/commands` は Claude Code 専用アダプターである。Codex では skill / workflow instruction set を別に持つ。共通契約は CLI 出力であり、Claude command や Codex skill を source of truth にしてはいけない。

## 13. ストレージ

推奨配置:

```text
.spec-grag/
  config.toml
  graph/
    source_sections.jsonl
    spec_chunks.jsonl
    atomic_facts.jsonl
    normalized_facts.jsonl
    canonical_nodes.jsonl
    canonical_edges.jsonl
    evidence_links.jsonl
    validation_events.jsonl
    indexes/
      anchors.json
      clusters.json
      risk_index.json
      vector/
    cache/
      query_decisions.jsonl
      answer_inputs.jsonl
```

`.spec-grag/graph/` は実行時データであり、通常は `.gitignore` 推奨である。

## 14. エラー処理

| 状態 | 内部動作 |
|---|---|
| `.spec-grag/config.toml` がない | エラー終了 |
| Purpose がない | エラー終了 |
| Concept がない | 初期作成候補を提示し、ユーザー確認へ進む |
| Source specs がない | エラー終了 |
| GRAG 更新に一部失敗 | `degraded` として報告し、失敗ファイルを `failed_sources[]` に入れる |
| Concept diff が未承認 | Concept を書き換えず、`InjectionContext` / `Answer` を生成しない |
| Triple Reflection が失敗 | edge を `unvalidated` または `needs_human_review` に落とし、確定扱いにしない |

## 15. 実装優先順位

1. 設定読込、SourceSectionRecord、SpecChunk、content hash
2. `/spec-core` incremental / full rebuild の骨格
3. `InjectionContext` / `RealignResult` / `CoreResult` の出力スキーマ
4. GLiNER / AtomicFactExtractor / Triple Reflection の adapter
5. 正規グラフ、EvidenceLink、状態フィールド
6. `/spec-inject` の GRAG 検索と分類
7. `/spec-realign` の Answer 生成
8. Codex skill / Claude command アダプター
