# SPEC-grag 設計

本ドキュメントは、SPEC-grag の設計仕様です。SPEC-grag は、仕様書を原子的事実、正規化された制約、根拠付きエッジ、クエリ時判断へ分解し、LLM が仕様変更作業で守るべき制約と変更してよい対象を取り違えないようにするためのシステムです。

## 1. 目的

SPEC-grag は、LLM が直近に読んだ仕様書本文へ過剰に引き寄せられることを防ぐための仕様策定支援ツールです。

近年の LLM は、与えられた文書への忠実度が高くなっています。これは安定した実装作業では有益ですが、仕様そのものがまだ揺れている仕様設計段階では有害になり得ます。文書内の記述が暫定、衝突中、局所最適、または古い前提である可能性があるためです。

そのため、システムは次を区別しなければなりません。

- 元文書に何が書かれているか
- その記述が安定済み / 暫定 / 廃止予定 / 衝突中のどれか
- その記述が要件 / 制約 / 例外 / 依存関係 / 設計原則 / 未解決課題のどれか
- その記述が今回の変更を制約すべきか

目的は、より強い文書検索エンジンを作ることではありません。目的は、仕様変更案を次の軸へ引き戻す制御構造を作ることです。

```text
目的 -> コンセプト -> 承認済み制約 -> 変更対象候補
```

グラフは、何を守るべきか、何を変更してよいか、何を人間レビューへ回すべきかをエージェントが判断するために使います。

## 2. End-to-End Data Contract

SPEC-grag の中核は、ソース仕様書をそのまま LLM に渡すことではありません。ソース仕様書を、仕様判断に使える成果物へ段階的に変換し、最後にエージェントへ渡す文脈を制御することです。

この章は、Source Markdown から AgentContext までの全体変換列を定義します。後続の構築時パイプラインとクエリ時パイプラインは、この契約の詳細実装です。

### 2.1 全体変換列

```text
Source Markdown
  ↓ spec-grag CLI
SourceSectionRecord
  ↓ spec-grag CLI
SpecChunk
  ↓ spec-grag CLI adapter
graphrag-rs TextChunk
  ↓ graphrag-rs GLiNERExtractor
EntityCandidate / AnchorCandidate
  ↓ graphrag-rs AtomicFactExtractor + LLM
AtomicFact
  ↓ spec-grag normalizer
Requirement / Constraint / Exception / Dependency
  ↓ spec-grag edge builder
EdgeCandidate
  ↓ graphrag-rs LLMRelationshipExtractor.validate_triple + LLM
ValidationEvent
  ↓ spec-grag canonical merge
CanonicalNode / CanonicalEdge / EvidenceLink
  ↓ graphrag-rs + spec-grag indexes
SearchIndex / ClusterIndex / RiskIndex
  ↓ spec-grag query-time decision retrieval + LLM classifier
DecisionSet
  ↓ agent adapter
AgentContext
```

### 2.2 Source Markdown

概要:
ユーザーまたは LLM が編集する仕様書本文です。この段階では、「書いてあること」「守るべきこと」「変更してよいこと」「競合していること」はまだ区別されていません。

実行主体:
なし。これは入力成果物です。

作成者:
ユーザー、またはユーザーの指示を受けた LLM。

LLM:
編集者として関与することはあります。ただし、この段階では抽出、検証、制約採用判断は行いません。

graphrag-rs:
使用しません。

spec-grag CLI:
この段階では読み取り対象として扱います。source of truth はファイル本文です。

出力:
Source Markdown。

次:
spec-grag CLI が SourceSectionRecord を作ります。

### 2.3 Source Markdown -> SourceSectionRecord

概要:
Markdown 仕様書を読み、章、節、見出しパス、原文範囲、content hash を持つ原文記録へ変換します。これは後で「この制約はどの原文に支えられているか」へ戻るための根拠台帳です。

実行主体:
spec-grag CLI。

LLM:
使用しません。

graphrag-rs:
使用しません。

spec-grag CLI:

```text
source glob 展開
Markdown 読み込み
Markdown AST 解析
heading path 生成
source_section_id 採番
start_offset / end_offset 計算
content_hash 計算
```

出力:
SourceSectionRecord[]。

次:
spec-grag CLI が SpecChunk を作ります。SourceSectionRecord は AtomicFact、ValidationEvent、EvidenceLink から原文へ戻るためにも使います。

### 2.4 SourceSectionRecord -> SpecChunk

概要:
SourceSectionRecord を抽出器に渡しやすい単位へ分割します。ただし、章節境界、表、箇条書き、仕様ID、見出しパスを壊してはいけません。

実行主体:
spec-grag CLI。

LLM:
使用しません。

graphrag-rs:
使用しません。graphrag-rs の汎用 chunking にこの処理を委譲しません。

spec-grag CLI:

```text
section を抽出単位へ分割
長すぎる section を安全に分割
source_section_id を維持
heading_path を維持
content_hash を維持
原文 offset を維持
```

出力:
SpecChunk[]。

次:
spec-grag CLI adapter が graphrag-rs TextChunk を作ります。

### 2.5 SpecChunk -> graphrag-rs TextChunk

概要:
graphrag-rs の抽出器に渡すため、SPEC-grag 独自の SpecChunk を graphrag-rs の TextChunk へ変換します。これは adapter only の処理です。ここで仕様判断は行いません。

実行主体:
spec-grag CLI。

LLM:
使用しません。

graphrag-rs:
TextChunk 型だけを入力形式として使います。

graphrag-rs の使用機能:

```text
TextChunk::new
ChunkId
DocumentId
ChunkMetadata
```

graphrag-rs の不使用機能:

```text
DocumentManager
DocumentIndex
ChunkingStrategy
LateChunkingStrategy
```

spec-grag CLI:

```text
SpecChunk の ID と source_section_id を TextChunk metadata へ保持
content / offset を TextChunk に写像
後続 extractor の入力形式を揃える
```

出力:
graphrag-rs TextChunk[]。

次:
GLiNERExtractor と AtomicFactExtractor に渡します。

### 2.6 TextChunk -> EntityCandidate / AnchorCandidate

概要:
画面名、API、Component、Role、Permission、State、DataModel、ChapterAnchor などの候補を広く拾います。これは候補発見であり、仕様判断ではありません。

実行主体:
graphrag-rs + 非生成型モデル。

LLM:
使用しません。

graphrag-rs:
GLiNERExtractor を使用します。

graphrag-rs の使用機能:

```text
GLiNERExtractor::new
GLiNERExtractor::extract_from_chunk
entity_labels
relation_labels は必要な場合のみ
```

spec-grag CLI:

```text
仕様書向けラベルセットを渡す
confidence threshold を適用する
SpecChunk / SourceSectionRecord へ戻れる参照IDを保持する
候補を EntityCandidate / AnchorCandidate として保存する
```

出力:
EntityCandidate[]、AnchorCandidate[]。

次:
canonical merge、章別アンカー index、クエリ時の候補探索で使います。

### 2.7 TextChunk -> AtomicFact

概要:
仕様文を、単独で検証可能な原子的事実へ分解します。ここで初めて LLM が抽出作業を行います。

実行主体:
graphrag-rs extractor + LLM provider。

LLM:
使用します。CodexCliLanguageModel を primary とする AsyncLanguageModel を通します。

LLM が行うこと:

```text
仕様文を self-contained fact に分解する
subject / predicate / object / temporal_marker / confidence を出す
```

LLM にさせないこと:

```text
fact が最終仕様として正しいか決める
今回の変更で守るべき制約か決める
Purpose / Concept を書き換える
```

graphrag-rs:
AtomicFactExtractor を使用します。

graphrag-rs の使用機能:

```text
AtomicFactExtractor
extract_atomic_facts 相当
AtomicFact
```

spec-grag CLI:

```text
TextChunk を渡す
仕様書向けプロンプトを管理する
source_section_id / source_hash を付与する
authority 初期値を付ける
stability 初期値を付ける
```

出力:
AtomicFact[]。

次:
spec-grag normalizer が Requirement / Constraint / Exception / Dependency に分類します。

### 2.8 AtomicFact -> Requirement / Constraint / Exception / Dependency

概要:
AtomicFact を仕様判断用の正規 fact へ分類し、predicate の揺れを抑えます。ここで「文書に書いてある事実」を「仕様判断で使う型」へ変換します。

実行主体:
spec-grag CLI。必要に応じて LLM classifier を補助的に使います。

LLM:
原則は使用しません。述語が曖昧でルールだけでは分類できない場合のみ、少数候補を分類させます。

LLM にさせないこと:

```text
human_approved 扱いにする
stable / core 扱いにする
今回の変更で必ず守る制約だと決める
```

graphrag-rs:
この分類処理には使用しません。

spec-grag CLI:

```text
relation vocabulary への写像
requirement / constraint / exception / dependency / open issue の分類
同等 fact の重複抑制
authority / stability / scope の初期化
```

出力:
Requirement[]、Constraint[]、ExceptionRule[]、Dependency[]、OpenIssue[]。

次:
spec-grag edge builder が EdgeCandidate を作ります。

### 2.9 Normalized Fact -> EdgeCandidate

概要:
正規 fact から、source-target-relation の関係候補を作ります。EdgeCandidate はまだ確定エッジではありません。

実行主体:
spec-grag CLI。

LLM:
原則は使用しません。source / target / relation_type が曖昧な場合のみ、少数候補の分類に使います。

graphrag-rs:
Relationship 相当の graph element 形式を参考にします。ただし、authority、stability、validation、risk、evidence は spec-grag の正規スキーマで保持します。

spec-grag CLI:

```text
source node 候補を決める
target node 候補を決める
relation_type を正規語彙へ写像する
evidence_fact_ids を付与する
confidence / risk 初期値を付与する
```

出力:
EdgeCandidate[]。

次:
Triple Reflection 検証へ渡します。

### 2.10 EdgeCandidate -> ValidationEvent

概要:
EdgeCandidate が原文に明示的に支えられているかを検証します。ここで問うのは「本文に支持されるか」であり、「今回の変更で制約として採用すべきか」ではありません。

実行主体:
graphrag-rs relationship validator + LLM provider。

LLM:
使用します。source、relation、target、原文根拠を入力し、validity、confidence、reason を返します。

LLM にさせないこと:

```text
今回の変更で守るべき制約か決める
validated edge を human_approved に昇格する
conflicting を黙って解消する
```

graphrag-rs:
LLMRelationshipExtractor の Triple Reflection 検証を限定利用します。

graphrag-rs の使用機能:

```text
LLMRelationshipExtractor.validate_triple 相当
```

spec-grag CLI:

```text
検証対象 edge を選別する
high risk / low confidence / Purpose 近傍 edge を優先する
validation event を保存する
needs_human_review を保持する
```

出力:
ValidationEvent[]。

次:
spec-grag canonical merge が CanonicalNode / CanonicalEdge / EvidenceLink を作ります。

### 2.11 Candidate / Fact / ValidationEvent -> Canonical Graph

概要:
EntityCandidate、AnchorCandidate、AtomicFact、Normalized Fact、EdgeCandidate、ValidationEvent を正規グラフへ統合します。ここで重複をまとめ、根拠リンクと状態を保存します。

実行主体:
spec-grag CLI。

LLM:
原則使用しません。

graphrag-rs:
graph storage、graph traversal、Entity / Relationship 相当の graph element 基盤を利用できます。ただし、正規スキーマと状態管理の source of truth は spec-grag 側です。

spec-grag CLI:

```text
canonical node を作る
canonical edge を作る
atomic fact を保存する
evidence link を張る
validation 状態を反映する
authority / stability / risk を保持する
rejected edge を採用しない
needs_human_review を OpenIssue / Conflict として保持する
```

出力:
CanonicalNode[]、CanonicalEdge[]、EvidenceLink[]、AtomicFact[]、ValidationEvent[]。

次:
二次インデックス構築とクエリ時検索で使います。

### 2.12 Canonical Graph -> SearchIndex / ClusterIndex / RiskIndex

概要:
正規グラフへ速く戻るための二次インデックスを作ります。インデックスは正規グラフの代替ではありません。

実行主体:
graphrag-rs + spec-grag CLI。

LLM:
原則使用しません。クラスタ要約を作る場合だけ使用します。

graphrag-rs:

```text
embedding
graph traversal
hierarchical relationship clustering
neighborhood search
```

spec-grag CLI:

```text
anchor index を作る
risk index を作る
query-time ranking key を作る
正規グラフの node_id / edge_id へ戻れる参照を保持する
```

出力:
SearchIndex、ClusterIndex、RiskIndex。

次:
クエリ時に DecisionSet を作るための候補探索に使います。

### 2.13 Change Request -> DecisionSet

概要:
ユーザーの変更要求に対して、事前構築済みの正規グラフとインデックスを検索し、今回の変更で必要な文脈を分類します。この段階では原則として全文書からの抽出をやり直しません。

実行主体:
spec-grag CLI + LLM classifier。

LLM:
少数候補の分類に使います。

LLM が行うこと:

```text
変更対象候補を分類する
守るべき制約を分類する
対象外のコアを分類する
補助文脈 / 無関係 / 競合 / 人間レビュー項目を分ける
```

LLM にさせないこと:

```text
生文書全体から新規関係を大量抽出する
validated ではない edge を確定扱いにする
Purpose / Concept を黙って変更する
```

graphrag-rs:
検索、近傍探索、階層クラスタ、graph traversal を候補取得に使います。

spec-grag CLI:

```text
QueryIntent を作る
Purpose / Concept / DesignPrinciple を先に取得する
validated edge を優先する
Fast / Balanced / Strict path を選ぶ
query decision cache を管理する
```

出力:
DecisionSet。

次:
agent adapter が AgentContext を作ります。

### 2.14 DecisionSet -> AgentContext

概要:
Codex / Claude などの作業エージェントへ渡す最終コンテキストを作ります。生の章本文を丸ごと渡さず、分類済みの文脈だけを渡します。

実行主体:
agent adapter。実体は spec-grag CLI の出力契約と、エージェント固有の adapter です。

LLM:
AgentContext を消費して、仕様変更案または実装変更案を作ります。AgentContext の組み立て自体は LLM に委譲しません。

graphrag-rs:
使用しません。必要な検索結果は DecisionSet 作成時点で取得済みです。

spec-grag CLI:

```text
DecisionSet を構造化 Markdown / JSON に変換する
Purpose / Concept を先頭に置く
守るべき制約と変更対象候補を分離する
根拠 fact と source_section_id を付ける
conflict / needs_human_review を隠さない
```

出力:
AgentContext。

次:
Codex / Claude が AgentContext を読み、仕様変更または実装変更を行います。

### 2.15 設計上の判断基準

このフローでは、graphrag-rs は中心ではなく部品です。仕様判断の source of truth は、spec-grag の SourceSectionRecord、CanonicalGraph、EvidenceLink、ValidationEvent です。

```text
graphrag-rs を使う:
  extractor
  TextChunk などの入力型
  Entity / Relationship 相当の graph element
  graph traversal
  embedding
  hierarchical clustering

graphrag-rs に委譲しない:
  source section 管理
  Markdown 章節境界の決定
  authority / stability / validation の状態管理
  relation type 正規化の最終決定
  query-time の制約採用判断
  AgentContext の組み立て
```

章アンカー、依存グラフ、階層クラスタは検索補助として使います。ただし、それらを中核判断モデルにはしません。何が正しいか、何が安定しているか、何が今回の変更を拘束するかは、根拠付きの fact / edge / state で判断します。

## 3. 情報モデル

### 3.1 コア文書

| 項目 | 役割 | 更新方針 |
|---|---|---|
| Purpose | ビジネスゴール、UX の根、システムが存在する理由 | 人間が手書きする |
| Concept | 安定したアーキテクチャ原則、設計思想 | 人間承認済みのみ |
| Source specs | 現行の章ファイル / 作業中仕様 | ユーザー・LLMが編集する |

Purpose と Concept は、通常の抽出済み事実ではありません。より高い権威を持つアンカーです。システムは Concept の変更案を提示できますが、黙って書き換えてはいけません。Purpose は SPEC-grag が更新しません。

### 3.2 正規ノード型

SPEC-grag は、明示的なノード型を持つ正規グラフ（canonical graph）を保持します。実装上の型IDは英語で固定し、表示・説明では日本語を併記します。

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

全プロジェクトがすべての型を必要とするわけではありません。ただし、すべてを汎用エンティティに潰さず扱えるスキーマが必要です。

### 3.3 正規エッジ型

関係語彙はドメイン固有に正規化します。実装上のエッジ型（edge type）は英語IDで固定し、表示・説明では日本語を併記します。最低限のエッジ型は次です。

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
| OUT_OF_SCOPE_FOR | 対象外である |

仕様推論において、`related_to` を主要な関係型として使ってはいけません。低信頼の予備扱いとしてのみ許容します。

### 3.4 必須状態フィールド

すべての事実、制約、エッジは状態を持ちます。これは文書への過剰アンカーを防ぐ主な仕組みです。

```text
authority:
  human_approved（人間承認済み）
  inferred（推論されたもの）
  document_claim（文書上の主張）
  candidate（候補）

stability:
  core（コア）
  stable（安定済み）
  tentative（暫定）
  deprecated（廃止予定）
  conflicting（衝突中）

scope:
  global（全体）
  chapter（章）
  feature（機能）
  component（コンポーネント）

validation:
  unvalidated（未検証）
  validated（検証済み）
  rejected（却下）
  needs_human_review（人間レビューが必要）

risk:
  low（低）
  medium（中）
  high（高）
  critical（重大）
```

検索層は `human_approved` と `validated` を優先します。ただし、`tentative`、`conflicting`、`needs_human_review` を隠してはいけません。これらはリスクとして提示します。

## 4. 根拠モデル（Evidence モデル）

エッジは、抽出器が出したから採用されるのではありません。根拠があるから採用されます。

推奨エッジ記録:

```text
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
evidence_fact_ids
source_chunk_ids
source_section_ids
validated_by
validated_at
validation_reason
```

原子的事実（Atomic facts）は別レイヤーに保存し、エッジにリンクします。

```text
fact_id
subject
predicate
object
temporal_marker
confidence
source_chunk_id
source_section_id
authority
stability
scope
```

これにより、2 層構造を作ります。

```text
エンティティ / 制約グラフ
  安定した正規化済みノードとエッジ

事実 / 根拠レイヤー
  原文に根拠づけられた事実主張
```

## 5. 抽出器の役割

抽出器の役割は次です。

| 役割 | 抽出器 | 位置づけ |
|---|---|---|
| 主事実抽出 | `AtomicFactExtractor` | 構築時 |
| エッジ検証 | `LLMRelationshipExtractor` + Triple Reflection | 構築時。クエリ時ではリスク候補だけ |
| コアアンカー候補 | `GleaningEntityExtractor` | 構築時。Purpose / Concept / 用語集 / 重要章に限定 |
| 広域スキャン | `GLiNERExtractor` | 構築時。低コスト候補発見 |
| ベースライン検証 | `LLMEntityExtractor` | 抽出品質の比較、回帰確認、初期検証に限定 |

### 5.1 実行主体の凡例

この設計では、`graphrag-rs` はグラフ構築・抽出・検索のエンジンとして使います。ただし、仕様判断の最終責任を `graphrag-rs` に置きません。仕様書GRAG固有の分類、状態管理、権威づけ、制約照射は `spec-grag` 側で持ちます。

| 主体 | 役割 |
|---|---|
| `spec-grag` | 仕様書GRAGの制御層。ソース同期、章節ID、状態管理、正規スキーマ、正規化、マージ方針、CLI契約を持つ |
| `graphrag-rs` | 抽出器、graph elements、グラフ保存、埋め込み、階層クラスタ、検索などの基盤機能を使う対象 |
| LLM | 原子的事実抽出、関係候補の意味づけ、Triple Reflection、クエリ意図分類、修正案生成を担当する |
| 非生成型モデル | GLiNER など。候補発見に使い、仕様判断の根拠にはしない |
| 人間 | Purpose / Concept / DesignPrinciple / deprecated / conflicting / high risk の最終承認者 |

LLM 呼び出しは `CodexCliLanguageModel` を primary とします。`ClaudeCliLanguageModel` は任意プロバイダーとして扱い、同じ `AsyncLanguageModel` 契約の下で差し替えられるようにします。

### 5.2 構築時処理の責務分担

| 処理 | 主担当 | LLM 作業 | `graphrag-rs` 利用 | `spec-grag` 側の責務 |
|---|---|---|---|---|
| ソース同期 / 変更検出 | `spec-grag` | なし | 使用しない | Markdown の章節解析、source section record、content hash、差分処理 |
| 章節チャンク化 | `spec-grag` | なし | 使用しない | 見出し、表、箇条書き、仕様IDを壊さない `SpecChunk` boundary を決める |
| TextChunk adapter | `spec-grag` | なし | `TextChunk::new` / `ChunkId` / `DocumentId` / `ChunkMetadata` を adapter only で使用 | `SpecChunk` の source_section_id と metadata を失わず extractor 入力へ変換する |
| 広域候補スキャン | `graphrag-rs` + 非生成型モデル | なし | `GLiNERExtractor` | 候補ラベル、信頼度閾値、章別アンカーへの紐づけを管理する |
| 原子的事実抽出 | LLM + `graphrag-rs` | 仕様文を `AtomicFact` に分解する | `AtomicFactExtractor` | 仕様書向けプロンプト、出力スキーマ、authority / stability 初期値を付与する |
| 関係候補生成 | `spec-grag` + LLM | 必要に応じて述語の意味を正規関係型へ分類する | `Relationship` 相当の構造は参考にするが、正規 `EdgeCandidate` は `spec-grag` が持つ | relation type 正規化、重複抑制、候補 edge の risk / confidence を付与する |
| Triple Reflection | LLM + `graphrag-rs` | edge が原文に明示的に支持されるか検証する | `LLMRelationshipExtractor.validate_triple` 相当 | 検証対象の絞り込み、validation 状態、根拠 fact とのリンクを保存する |
| 正規グラフへのマージ | `spec-grag` | 原則なし | graph traversal / storage は利用可能。ただし正規スキーマの source of truth にはしない | ノード正規化、edge 統合、evidence linking、状態更新、永続化方針を決める |
| 二次インデックス | `graphrag-rs` + `spec-grag` | 要約が必要な場合のみ | 埋め込み、階層クラスタ、近傍検索 | anchor index、risk index、query-time 用の検索キーを構築する |

### 5.3 クエリ時処理の責務分担

| 処理 | 主担当 | LLM 作業 | `graphrag-rs` 利用 | `spec-grag` 側の責務 |
|---|---|---|---|---|
| クエリ理解 | LLM | 変更対象、守るべき制約、リスク領域を抽出する | 原則なし | 出力を固定スキーマに落とし、検索クエリへ変換する |
| アンカー取得 | `spec-grag` + `graphrag-rs` | 原則なし | graph traversal / vector search / hierarchical query | Purpose / Concept / DesignPrinciple を先に取得し、後続検索の上位制約にする |
| 修正対象候補探索 | `graphrag-rs` | 原則なし | graph traversal、ベクトル検索、章別クラスタ | candidate nodes / edges / facts を取り、authority と validation で順位づけする |
| 制約候補探索 | `graphrag-rs` + `spec-grag` | 原則なし | validated edge、近傍検索 | `CONSTRAINS` / `DEPENDS_ON` / `PROTECTS` / `FORBIDS` / `EXCEPTS` を優先して辿る |
| 候補分類 | LLM | 少数候補を修正対象、守るべき制約、対象外、未確定に分類する | 検索済み候補を入力として使う | Fast / Balanced / Strict の判定、分類結果のキャッシュを管理する |
| Fast path | `spec-grag` | 最終回答生成のみ | 事前検証済み edge と index を使う | 低リスク変更では追加検証なしで文脈を組み立てる |
| Balanced path | LLM + `spec-grag` | 曖昧な top-k 候補だけ再判定する | 候補取得に使う | low confidence / high impact edge を選別する |
| Strict path | LLM + `graphrag-rs` | 高リスク edge に Triple Reflection と採用判定を行う | `LLMRelationshipExtractor` の検証機構を限定利用 | 権限、課金、個人情報、破壊的変更などを強制的に厳格扱いにする |
| LLM コンテキスト組み立て | `spec-grag` | LLM は組み立て済み文脈を消費する | 検索結果を入力に使う | Purpose、修正対象、対象外コア、制約、根拠 fact、不確実候補を分離して渡す |

重要なのは、クエリ時の LLM を「生文書から関係を再抽出する主体」にしないことです。クエリ時 LLM は、事前構築済みの graph / fact / edge を少数候補に絞ったうえで、今回の変更に対する採用可否を判定する分類器として使います。

エンティティ抽出は候補発見に使います。仕様判断の推論は、原子的事実、正規化された関係、検証済みエッジ、状態フィールドを使って行います。

## 6. 構築時パイプライン（Build-Time Pipeline）

構築時パイプラインは、ソース文書からクエリ時に使える正規グラフと検索インデックスを作る処理です。各ステップの位置づけは次です。

| 節 | 処理 | 主に使うもの | 生成物 | 主な利用先 |
|---|---|---|---|---|
| 6.1 | ソース同期 | `spec-grag` のソース設定、Markdown 章節解析、content hash | source section record、changed chunk | 6.2、6.3、6.5、6.6 |
| 6.2 | 広域候補スキャン | `GLiNERExtractor` または同等の非生成型抽出 | entity / anchor 候補 | 6.6、6.7、7.2、7.3 |
| 6.3 | Atomic Fact Extraction | `AtomicFactExtractor` + `AsyncLanguageModel` | `AtomicFact[]` | 6.4、6.5、6.6、7.5 |
| 6.4 | 関係候補生成 | `spec-grag` relation normalizer、必要に応じて LLM 分類 | edge candidate | 6.5、6.6 |
| 6.5 | Triple Reflection 検証 | `LLMRelationshipExtractor.validate_triple` 相当 | validation event、validated / rejected edge | 6.6、7.2、7.4 |
| 6.6 | 正規グラフへのマージ | `spec-grag` canonical schema、graphrag-rs graph 基盤 | canonical nodes / edges / evidence links | 6.7、7章全体 |
| 6.7 | 二次インデックス | embeddings、hierarchical clustering、近傍 index | anchor / vector / cluster / risk index | 7.2、7.3、7.4 |

### 6.1 ソース同期

設定されたソースファイルごとに次を行います。

```text
Markdown原文
  -> 章節を意識したチャンク分割
  -> 原文セクション記録
  -> 内容ハッシュ比較
  -> 変更されたチャンクのみ処理
```

変更検出はハッシュベースにします。タイムスタンプは報告用に保持してよいですが、真実の根拠にしてはいけません。

使用する機能:

```text
spec-grag:
  source glob 展開
  Markdown 章節解析
  section id 採番
  content hash 比較

graphrag-rs:
  使用しない
  TextChunk への変換は 2.5 / adapter 処理で行う

LLM:
  使用しない
```

生成物と利用先:

```text
source section record
  -> 6.3 AtomicFact の source_section_id
  -> 6.5 Triple Reflection の原文根拠
  -> 6.6 evidence link

changed chunk
  -> 6.2 広域候補スキャン
  -> 6.3 Atomic Fact Extraction
```

### 6.2 広域候補スキャン

GLiNER または同等の非生成型抽出で、広く安く候補を拾います。

```text
Screen / API / Component / Role / Permission / State / DataModel / ChapterAnchor
```

これらの候補は authoritative ではありません。indexing hints です。

使用する機能:

```text
graphrag-rs:
  GLiNERExtractor
  entity_labels
  relation_labels がある場合のみ relation extraction

spec-grag:
  仕様書向けラベル定義
  confidence threshold
  ChapterAnchor への紐づけ

LLM:
  使用しない
```

生成物と利用先:

```text
entity / anchor 候補
  -> 6.6 canonical node 候補
  -> 6.7 章別アンカー index
  -> 7.2 Purpose / Concept 近傍探索の補助
  -> 7.3 修正対象候補探索の入口
```

### 6.3 Atomic Fact Extraction

変更されたチャンクに原子的事実抽出を実行します。

```text
TextChunk
  -> AtomicFactExtractor
  -> AtomicFact[]
```

仕様書向けプロンプトでは、次の抽出を要求します。

```text
要件
制約
例外
事前条件
事後条件
状態遷移
権限
禁止事項
依存関係
未解決の問い
```

出力は最終真実として扱いません。初期状態は `authority=document_claim` または `authority=candidate` です。

使用する機能:

```text
graphrag-rs:
  AtomicFactExtractor

LLM:
  CodexCliLanguageModel を primary とする AsyncLanguageModel
  要件 / 制約 / 例外 / 依存 / 未解決課題の抽出

spec-grag:
  仕様書向け抽出プロンプト
  AtomicFact schema
  authority / stability 初期値
  source_section_id / source_hash の付与
```

生成物と利用先:

```text
AtomicFact[]
  -> 6.4 関係候補生成
  -> 6.5 edge 検証時の根拠
  -> 6.6 atomic_facts.jsonl
  -> 7.5 LLM へ渡す根拠事実
```

### 6.4 関係候補生成

原子的事実をエッジ候補に変換します。

```text
AtomicFact
  -> 関係候補
  -> 正規化された関係型
  -> エッジ候補
```

関係正規化は必須です。自由文の述語は正規関係語彙に写像します。

使用する機能:

```text
spec-grag:
  relation type 正規化
  entity canonicalization
  duplicate candidate 抑制
  risk / confidence 初期値の付与

graphrag-rs:
  Relationship 相当の構造は参考にする
  正規 EdgeCandidate schema は spec-grag が持つ

LLM:
  述語が曖昧な場合だけ正規関係型への分類に使う
```

生成物と利用先:

```text
edge candidate
  -> 6.5 Triple Reflection 検証
  -> 6.6 canonical edge 候補

relation normalization event
  -> 6.6 validation / merge の判断材料
```

### 6.5 Triple Reflection 検証

重要なエッジ候補に検証を実行します。

```text
エッジ候補 + 原文
  -> Triple Reflection
  -> validated | rejected | needs_human_review
```

検証が問うのは、原文がその関係を明示的に支持しているかです。将来の変更に対してその関係が制約になるかは決めません。その判断はクエリ固有です。

使用する機能:

```text
graphrag-rs:
  LLMRelationshipExtractor.validate_triple 相当

LLM:
  source - relation - target が原文に支持されるかを判定する

spec-grag:
  検証対象 edge の選別
  high risk / low confidence / Purpose 近傍 edge の優先
  validation event の保存
```

生成物と利用先:

```text
validated edge
  -> 6.6 canonical edge として採用
  -> 7.2 / 7.4 で優先使用

rejected edge
  -> 6.6 では採用しない
  -> 必要なら監査ログに残す

needs_human_review
  -> 6.6 conflicting / open issue として扱う
  -> 7.5 人間レビュー項目として提示
```

### 6.6 正規グラフへのマージ

すべての出力を正規グラフにマージします。

```text
ノード重複排除
同等事実の統合
同等エッジの統合
根拠事実の紐づけ
authority / stability / validation 状態の更新
グラフ永続化
インデックス更新
```

次のような意味的に重複するエッジを別々の関係型として保存しないようにします。

```text
必要とする
依存する
求める
基づく
```

ドメイン上本当に意味が異なる場合だけ分けます。

使用する機能:

```text
spec-grag:
  canonical node schema
  canonical edge schema
  evidence link schema
  authority / stability / validation 状態更新
  merge policy

graphrag-rs:
  graph storage / graph traversal は利用可能
  ただし canonical schema の source of truth にはしない

LLM:
  原則使用しない
```

生成物と利用先:

```text
canonical_nodes.jsonl
canonical_edges.jsonl
atomic_facts.jsonl
evidence_links.jsonl
validation_events.jsonl
  -> 6.7 二次インデックス
  -> 7.2 アンカー取得
  -> 7.3 候補探索
  -> 7.4 Fast / Balanced / Strict 判定
  -> 7.5 LLM コンテキスト組み立て
```

### 6.7 二次インデックス

正規グラフ更新後に二次インデックスを作ります。

```text
章別アンカー
ベクトル埋め込み
階層クラスタ
関係近傍インデックス
リスクインデックス
```

これらは検索を高速化します。正規グラフの代替ではありません。

使用する機能:

```text
graphrag-rs:
  embeddings
  hierarchical clustering
  graph traversal / neighborhood index

spec-grag:
  anchor index
  risk index
  query-time ranking key

LLM:
  原則使用しない
  要約インデックスを作る場合だけ使用する
```

生成物と利用先:

```text
chapter_anchors.json
vector index
clusters
risk index
  -> 7.2 拘束力のあるアンカー取得
  -> 7.3 修正対象候補探索
  -> 7.4 Balanced / Strict path の候補絞り込み
```

## 7. クエリ時パイプライン（Query-Time Pipeline）

### 7.1 クエリ理解

変更要求を受けたら、まず分類します。

```text
要求された変更対象
影響しそうな機能
リスク分類
明示された非目標
権限 / プライバシー / 課金 / データ損失の懸念
```

クエリでは、いきなり大きな原文をメイン LLM コンテキストに入れてはいけません。まず構造化されたグラフ候補を取得します。

### 7.2 拘束力のあるアンカーを先に取得する

クエリ時検索は安定アンカーから始めます。

```text
Purpose
Concept
DesignPrinciple
人間承認済み制約
検証済み重要エッジ
```

その後、次へ展開します。

```text
関連する ChapterAnchor
変更対象候補
依存エッジ
例外ルール
競合
原文根拠
```

### 7.3 候補分類

クエリ時における LLM の主タスクは抽出ではありません。少数候補に対する分類です。

各エッジ候補 / 事実候補を次に分類します。

```text
守るべき制約
変更対象
対象外のコア
補助文脈
競合
無関係
人間レビューが必要
```

ここでシステムは次に答えます。

```text
このエッジは今回の変更を制約すべきか？
```

これは構築時だけでは完全には決められません。

### 7.4 Fast / Balanced / Strict パス

Fast path（高速経路）:

```text
検証済みエッジのみ
クエリ時 Triple Reflection は実行しない
新規の関係抽出は行わない
```

Balanced path（バランス経路）:

```text
上位 k 件の候補
低信頼または高リスクのエッジを LLM で分類
クエリ判断キャッシュを有効化
```

Strict path（厳格経路）:

```text
権限
プライバシー
課金
在庫
注文
法務
データ削除
互換性

-> 少数の重要エッジに Triple Reflection を再実行
-> 競合には人間レビューを要求
```

### 7.5 LLM コンテキストの形

最終的に LLM へ渡すコンテキストは構造化します。

```text
A. ユーザーの変更要求
B. 拘束力のある Purpose / Concept
C. 守るべき制約
D. 変更対象候補
E. 対象外のコア項目
F. 根拠となる原子的事実
G. 競合と人間レビュー項目
```

ユーザーが明示的に広範レビューを求めない限り、章全体を丸ごと投入してはいけません。

## 8. LLM プロバイダー構成

### 8.1 プロバイダー規則

生成型の抽出、要約、正規化、検証、クエリ時分類は、すべて共通プロバイダー trait を通します。

実装対象は次です。

```text
AsyncLanguageModel
```

プロバイダー実装:

```text
CodexCliLanguageModel    本プロジェクトの主経路
ClaudeCliLanguageModel   任意プロバイダー
AsyncMockLanguageModel   テスト用
Ollama generation        仕様推論ではデフォルト不使用
```

Codex プロバイダーと Claude プロバイダーは同じ役割を担います。違いは subprocess コマンド形式、出力パース、モデル設定、timeout、rate limit だけです。

### 8.2 Codex を Primary にする

このプロジェクトでは Codex が主実装エージェントなので、`CodexCliLanguageModel` を主プロバイダーにします。

想定責務:

```text
complete(prompt)
complete_with_params(prompt, params)
complete_batch_concurrent(prompts, max_concurrent)
is_available()
model_info()
```

ヘッドレス実行のコマンド形式はプロバイダー設定で指定します。実装は標準出力、標準エラー、終了コード、構造化出力スキーマを正規化して扱います。

```text
codex exec ...
```

実際のコマンド、JSON 出力スキーマ、モデルフラグは実装詳細であり、設計段階で固定しません。

### 8.3 任意の Claude CLI プロバイダー

`ClaudeCliLanguageModel` は任意の LLM プロバイダーとして扱います。architecture の所有者にはしません。

プロバイダー選択は次の形にします。

```toml
[llm]
provider = "codex_cli" # codex_cli | claude_cli | mock

[llm.codex_cli]
command = "codex"
model = "gpt-5.4"

[llm.claude_cli]
command = "claude"
model = "sonnet"
```

設定名は `provider` とします。プロバイダーは要約だけでなく、抽出、正規化、検証、クエリ時分類も担当します。

### 8.4 Embeddings

埋め込みは生成型 LLM から分離します。

デフォルト:

```text
Ollama nomic-embed-text
```

埋め込みモデルは検索とクラスタリングのためだけに使います。仕様判断は行いません。

## 9. エージェントアダプター

### 9.1 共通 CLI 契約

SPEC-grag はエージェント非依存の CLI を公開します。Claude Code と Codex は同じコマンドを実行し、同じ構造化出力をパースします。

CLI が契約です。エージェント固有プロンプトはアダプターです。

### 9.2 Claude Code Adapter

`templates/.claude/commands` は Claude Code 用のスラッシュコマンドアダプターです。

ユーザーが Claude Code から SPEC-grag を実行する場合には有用です。ただしワークフロー本体の唯一のコピーにしてはいけません。

テンプレート配置:

```text
templates/.claude/commands/spec-inject.md
templates/.claude/commands/spec-core.md
templates/.claude/commands/spec-realign.md
```

これらは CLI 出力契約に従い、Claude Code 固有の呼び出し手順だけを記述します。

### 9.3 Codex Adapter

Codex において Claude スラッシュコマンドに相当するものは skill / workflow instruction set です。

これは `.claude/commands` files をそのまま skill にコピーするという意味ではありません。

```text
Claude スラッシュコマンド -> Claude 専用アダプター
Codex skill          -> Codex 専用アダプター
spec-grag CLI        -> 共通実行契約
```

Codex skill は `templates/.claude/commands` の外に置きます。例:

```text
skills/spec-grag/SKILL.md
```

または同等の Codex ワークフロー配置場所です。そこでは Codex に次を指示します。

```text
spec-grag index を実行する
spec-grag inject を実行する
spec-grag realign を実行する
制約候補を分類する
提案された変更を適用または却下する
```

## 10. CLI コマンド

コマンド体系は新モデルに合わせて見直します。

### 10.1 `spec-grag index`

正規グラフを構築または更新します。

```text
spec-grag index [--all]
```

責務:

```text
ソース同期
原子的事実抽出
広域スキャン
関係正規化
Triple Reflection 検証
正規グラフへのマージ
二次インデックス更新
グラフ永続化
```

重い前処理は `index` に集約します。他のコマンドの裏で暗黙に重い同期処理を走らせてはいけません。隠れた処理はレイテンシを予測不能にします。

### 10.2 `spec-grag inject`

承認済みコア文脈を注入します。

```text
Purpose
Concept
承認済み高リスク制約
現在のグラフ / インデックス状態
```

章本文の生テキストを丸ごと出力してはいけません。

### 10.3 `spec-grag realign`

変更要求に対してクエリ時検索を実行します。

```text
spec-grag realign "<change request>"
```

出力は構造化 Markdown または JSON とし、次を含めます。

```text
拘束力のあるアンカー
守るべき制約
変更対象候補
対象外のコア項目
根拠事実
競合
人間レビュー項目
```

エージェントはこの出力を使って仕様変更を作成または修正します。

### 10.4 `spec-grag core`

コア文書を保守します。

`Purpose` は人間が手書きします。`Concept` には変更提案を出せますが、人間が承認した hunk だけを書き込みます。

このコマンドは主グラフ構築器ではありません。

## 11. ストレージ

推奨ストレージ構成:

```text
.spec-grag/
  config.toml
  graph/
    canonical_nodes.jsonl
    canonical_edges.jsonl
    atomic_facts.jsonl
    evidence_links.jsonl
    validation_events.jsonl
    indexes/
      chapter_anchors.json
      vector/
      clusters/
  cache/
    query_decisions.jsonl
```

トランザクション性が重要になった場合は SQLite に置き換えてもよいです。論理スキーマは同じままにします。

## 12. 実装優先順位

優先度 1: プロバイダー抽象化

```text
CodexCliLanguageModel を主プロバイダーとして提供する
ClaudeCliLanguageModel を任意プロバイダーとして提供する
設定名は provider に統一する
バッチ並列実行と timeout をプロバイダー単位で扱う
```

優先度 2: 正規スキーマと永続化

```text
ノード
エッジ
原子的事実
根拠リンク
検証イベント
クエリ判断キャッシュ
```

優先度 3: 事実優先インデックス化

```text
章節を意識したチャンク分割
AsyncLanguageModel 経由の AtomicFactExtractor
関係正規化
エッジ候補生成
AsyncLanguageModel 経由の Triple Reflection
正規グラフへのマージ
```

優先度 4: クエリ時判断エンジン

```text
アンカー取得
対象候補取得
制約と変更対象の分類
Fast / Balanced / Strict モード
判断キャッシュ
```

優先度 5: アダプター

```text
Codex skill / workflow アダプター
Claude スラッシュコマンドアダプター
エージェント非依存の CLI 出力契約
```

## 13. 実装対象コンポーネント

SPEC-grag の実装対象は次です。

```text
CodexCliLanguageModel
ClaudeCliLanguageModel
Project 設定ローダー
CLI コマンド
ソース glob 展開
正規グラフストア
AtomicFact / Edge / Evidence 永続化
GraphRAG-rs adapter
Codex skill / workflow アダプター
Claude スラッシュコマンドアダプター
```

graphrag-rs は vendor または外部 crate として利用します。SPEC-grag 固有の正規スキーマ、状態管理、クエリ時判断、エージェント向け出力契約はこのリポジトリ側に置きます。

この文書は、実装時の判断基準と公開 CLI 契約の基準文書として扱います。
