# SPEC-grag 設計

> 本ドキュメントは、旧来の章アンカー中心設計を置き換える新設計です。
> 旧設計は参照用として `doc/DESIGN_old.md` に保持します。
> `HANDOFF.md` はまだ旧実装状態を記述しているため、この設計が合意された後に書き換える必要があります。

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

## 2. 中核設計の変更

旧設計では、主な中間生成物を次のように扱っていました。

```text
章別キーアンカー
依存グラフエンベディング
階層クラスタ
```

これらは検索補助として有用です。しかし中核モデルではありません。新設計は事実優先（fact-first）です。

```text
原文
  -> 原子的事実
  -> 正規化された制約 / 依存関係 / 例外
  -> 根拠付きの検証済みエッジ
  -> クエリ時の判断分類
```

章アンカーとクラスタは残しますが、二次インデックスに降格します。関連領域を見つけるためには使いますが、何が正しいか、何が安定しているか、何が今回の変更を拘束するかは、それらでは判断しません。

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
| 比較基準 | `LLMEntityExtractor` | PoC と回帰比較のみ |

旧設計は `LLMEntityExtractor` と階層クラスタを中心に置きすぎていました。新設計ではエンティティ抽出を候補発見に使いますが、推論は原子的事実と検証済みエッジで行います。

## 6. 構築時パイプライン（Build-Time Pipeline）

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

### 6.2 広域候補スキャン

GLiNER または同等の非生成型抽出で、広く安く候補を拾います。

```text
Screen / API / Component / Role / Permission / State / DataModel / ChapterAnchor
```

これらの候補は authoritative ではありません。indexing hints です。

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

### 6.4 関係候補生成

原子的事実をエッジ候補に変換します。

```text
AtomicFact
  -> 関係候補
  -> 正規化された関係型
  -> エッジ候補
```

関係正規化は必須です。自由文の述語は正規関係語彙に写像します。

### 6.5 Triple Reflection 検証

重要なエッジ候補に検証を実行します。

```text
エッジ候補 + 原文
  -> Triple Reflection
  -> validated | rejected | needs_human_review
```

検証が問うのは、原文がその関係を明示的に支持しているかです。将来の変更に対してその関係が制約になるかは決めません。その判断はクエリ固有です。

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
ClaudeCliLanguageModel   互換プロバイダー / 既存実装
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

正確な headless コマンド形式は実装前に検証します。設計上の仮定は、次のような subprocess プロバイダーです。

```text
codex exec ...
```

実際のコマンド、JSON 出力スキーマ、モデルフラグは実装詳細であり、設計段階で固定しません。

### 8.3 Claude Compatibility

`ClaudeCliLanguageModel` は既に存在し、今後も価値があります。ただし architecture の所有者にはしません。

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

旧 `summary_provider` という名前は狭すぎます。プロバイダーは要約以外も担当します。

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

状態:

```text
templates/.claude/commands/spec-inject.md
templates/.claude/commands/spec-core.md
templates/.claude/commands/spec-realign.md
```

これらは CLI 出力契約が安定した後に書き換えます。

### 9.3 Codex Adapter

Codex において Claude スラッシュコマンドに相当するものは skill / workflow instruction set です。

これは `.claude/commands` files をそのまま skill にコピーするという意味ではありません。

```text
Claude スラッシュコマンド -> Claude 専用アダプター
Codex skill          -> Codex 専用アダプター
spec-grag CLI        -> 共通実行契約
```

将来の Codex skill は `templates/.claude/commands` の外に置くべきです。例:

```text
skills/spec-grag/SKILL.md
```

または同等の Codex ワークフロー配置場所です。そこでは Codex に次を指示します。

```text
spec-grag sync/index を実行する
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

旧設計の「すべてのコマンドの裏で重い前処理を隠れて実行する」方式は置き換える可能性があります。隠れた重い処理はレイテンシを予測不能にします。

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

優先度 0: 旧設計を凍結する

```text
doc/DESIGN_old.md は参照専用として残す
HANDOFF.md は書き換え完了まで旧情報として扱う
```

優先度 1: プロバイダー抽象化

```text
ClaudeCliLanguageModel を維持する
CodexCliLanguageModel を実装する
summary_provider を provider に改名する
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

## 13. 移行メモ

既存の有用な成果:

```text
ClaudeCliLanguageModel 実装
Project 設定ローダー
基本 CLI コマンド骨格
ソース glob 展開
励起出力プロトタイプ
GraphRAG-rs vendor 同梱
```

旧設計由来として扱うべき成果:

```text
章アンカー中心の DESIGN_old.md
階層クラスタ要約から Concept を生成する主経路
templates/.claude/commands を唯一の workflow 定義とする設計
AsyncGraphRAG のデモ用エンティティ抽出経路
すべてのコマンド前に隠れて走る重い同期処理
```

この文書の次に更新すべき文書は `HANDOFF.md` です。新設計に合わせて、旧優先順位を削除する必要があります。
