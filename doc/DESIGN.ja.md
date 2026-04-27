# SPEC-grag 詳細設計書

本書は SPEC-grag の **現時点での方針** を記録する。外部契約は [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md)（source of truth、不変）で定義され、本書はその実装側の方針を扱う。

> **警告**: 本書のうち §1.2「採用候補スタック」と §2「スキーマ」の運用詳細は、表面マップ調査前の **暫定方針**である。§4「不確定項目」が解消するまで実装に着手しない。「最終方針」「採用」「確定」と読み替えない。
>
> 本書の編集ルールは [CLAUDE.md](../CLAUDE.md) の不変ルール 1〜5 に従う。

---

## 1. アーキテクチャ

### 1.1 三層分業

```text
┌────────────────────────────────────────────────────────┐
│  Agent (Claude / Codex CLI) — slash command 実行層     │
│  - ConversationContext + 課題プロンプト解釈            │
│  - Agentic search（章ファイルを Read tool で読む）     │
│  - 動的キーワード／エンティティ／章候補抽出            │
│  - synonym 展開・意図解釈                              │
│  - InjectionContext を読み 5 分類                      │
│    （制約／修正対象／無関係／競合／要レビュー）         │
│  - Answer 生成（spec-realign）                          │
└──────────────────┬─────────────────────────────────────┘
                   │ Bash 呼び出し（CLI 引数で動的キーワード渡し）
                   ↓
┌────────────────────────────────────────────────────────┐
│  spec-grag CLI（Python、独立スクリプト）               │
│  - .spec-grag/config.toml + schema.toml 読み込み       │
│  - GRAG オーケストレーション                           │
│  - 2 系統 pipeline（制約探索 / 修正対象探索）           │
│  - 階層 ranking（Purpose > Concept > Source spec）     │
│  - 章別永続化（chapter_index、concept_index）          │
│  - InjectionContext を Markdown / JSON で出力          │
└──────────────────┬─────────────────────────────────────┘
                   │ Python API（暫定、§4.1 で確認）
                   ↓
┌────────────────────────────────────────────────────────┐
│  GRAG エンジン（採用候補：LlamaIndex 系、§1.2 暫定）   │
│  - PropertyGraphIndex / SimplePropertyGraphStore        │
│  - SchemaLLMPathExtractor                               │
│  - HybridRetriever / Cross-Encoder（要日本語モデル）   │
└────────────────────────────────────────────────────────┘
```

責務の境界：

- **クエリ生成は Agent (LLM) の責務**（Agentic search で動的抽出）
- **2 系統 pipeline は CLI の責務**（受け取った動的キーワードでオーケストレーション）
- **GRAG エンジンは「プリミティブ」のみ**（ファサード API を信用しすぎない）

### 1.2 採用候補スタック（暫定、§4 完了まで未確定）

```text
language     : Python
GRAG エンジン : LlamaIndex PropertyGraphIndex（候補）
graph store  : SimplePropertyGraphStore（候補、ローカル・ファイルベース）
extractor    : SchemaLLMPathExtractor（候補、ノード型・関係型を制約）
embedding    : Ollama nomic-embed-text（または OpenAI 互換、設定で切替）
LLM 要約・生成: Claude CLI / Codex CLI（spec-grag が直接保持、subprocess 呼び出し）
storage      : .spec-grag/graph/ にローカル永続化
optional 拡張 : Neo4jPropertyGraphStore adapter（将来追加可）
```

**未確認**: 上記の各候補の API 詳細・組み合わせ動作・version 安定度・永続化粒度・incremental update 方式は §4.1 で表面マップ調査が必要。

### 1.3 整合性チェック方針（3 段階パイプライン）

LLM 抽出を完全信用しない。EXTERNAL_DESIGN.ja.md §5.4 ConflictNotes（制約 vs 修正対象 / Source spec 同士 / Concept vs Source spec）の検出を 3 段階で実装する：

1. **グラフ構造ベース**（決定論的、優先）
   - `CONFLICTS_WITH` エッジが既に存在する
   - 同一概念に対し異なる Definition が存在する
   - `SUPERSEDES` チェーンに循環がある
   - 同一 ID への異なる属性が並存する
2. **ルールベース**（決定論的、補助）
   - Purpose の制約条項と Source spec の対立量化詞（「必ず」⇔「任意」、「全て」⇔「一部」）
   - sources_scanned_through より新しい修正と古い章の食い違い
   - Required と Optional の同時指定
3. **LLM 推論**（補助、最後）
   - 上記 1, 2 で疑わしい候補のみ LLM で意味的妥当性確認
   - LLM 単独では発火しない、必ず構造的根拠とセット

LLM は最後の検証段階で、構造的に検出済みの候補に対する補助としてのみ使う。

---

## 2. スキーマ

### 2.1 Core Schema（spec-grag 標準、ドメイン非依存、増やさない）

```toml
[schema.core.entities]
document_structure = [
  "Document",
  "Section",
  "SourceSpan",     # 行範囲（[26:1263-1289] 等）の根拠粒度
]
semantic = [
  "Concept",
  "Requirement",
  "Constraint",
  "Decision",
  "OpenQuestion",
  "Conflict",
  "Rationale",      # 独立ノード型、複数 Decision で共有可
  "Alternative",    # 独立ノード型、ALTERNATIVE_TO で Decision に紐付け
]

[schema.core.relations]
structure = [
  "CONTAINS",       # Document → Section、Section → Section
]
grounding = [
  "MENTIONS",       # Section → 意味要素（弱参照）
  "DEFINES",        # Section → 意味要素（その節が定義主体）
  "HAS_EVIDENCE",   # 意味要素 → SourceSpan（行参照付き根拠）
]
semantic = [
  "DEPENDS_ON",
  "CONSTRAINS",
  "REFINES",
  "SUPERSEDES",
  "CONFLICTS_WITH",
  "SUPPORTS",       # 意味要素 → 意味要素（弱依存、根拠としての支持）
  "ALTERNATIVE_TO", # Alternative → Decision
  "RELATED_TO",     # 弱関連（型が定まらない参照）
]
```

**未確認**: 上記スキーマを SchemaLLMPathExtractor に渡す具体的な API 形式（dataclass / pydantic / dict / TypedDict のいずれか）は §4.1 で確認が必要。

### 2.2 Optional Extensions（spec-grag 標準で提供、`.spec-grag/config.toml` で有効化）

```toml
[schema.extensions]
enabled = ["decision_process"]

[schema.extensions.decision_process.entities]
items = [
  "Phase",          # 議論段階
  "RejectedItem",   # 採用しなかった案（Alternative より明確に「却下された」もの）
  "SupersededItem", # 旧版（_old.md など、SUPERSEDES の対象）
]
```

議論プロセスを記録する文書（技術選定経緯、ADR、設計判断記録）でのみ有効化する。一般的な業務要件定義書では不要。

### 2.3 Project Custom Schema（spec-grag 標準には含めない、各プロジェクトが定義）

各プロジェクトが自分のドメイン語彙を `.spec-grag/schema.toml` で定義する。**spec-grag 本体には含めない**。spec-grag 本体は **ドメイン非依存**を保つ。

### 2.4 Section の意味要素参照ポリシー

「Section は 0 個以上の意味要素を参照する。ただし主要節は最低 1 つの Anchor または Summary を持つ」。前置き / 目次的節 / 補足節は意味要素を持たないことが正常。

---

## 3. 設計判断の境界（spec-grag 標準に含めない範囲）

汎用性を保つため、以下は spec-grag 標準スキーマに**含めない**。

### 3.1 プロジェクト固有のドメイン語彙

技術スタック語彙（Layer / Component / API / DataStructure / Action / Hook / Pattern / TechStack 等）、業務語彙（BusinessRule / Account / Transaction 等）、研究語彙（Hypothesis / Experiment / Result 等）、契約語彙（Party / Obligation / Term 等）はすべて Project Custom Schema として各プロジェクト側で定義する。

**理由**: 一つのドメイン語彙を spec-grag 標準に含めると、別ドメインで使えなくなる。「最初のユースケース」に引きずられて汎用性を損なわない。

### 3.2 議論メタデータの標準昇格

Phase / Alternative / Rationale / TakeDown 等の議論プロセスメタデータは、Optional Extensions（`decision_process`）として標準で提供するが、**Core Schema には昇格させない**。標準スキーマだけで EXTERNAL_DESIGN.ja.md §1 の 6 要素と §5.4 の 5 分類は表現可能。

**理由**: 「将来必要かも」で予防的に Core Schema を太らせない。議論記録を含まない仕様書（業務要件定義書等）で標準が肥大化しない設計を保つ。

---

## 4. 不確定項目（土台作り Phase 完了まで方針確定しない）

[CLAUDE.md](../CLAUDE.md) のルール 1（土台がない状態で設計を議論しない）に従い、以下はすべて確認まで実装に着手しない。「次セッションで調査」「MVP では省略」「最小コストで」は逃げ口にしない（ルール 4）。

### 4.1 LlamaIndex 系の表面マップ調査

- **PropertyGraphIndex** の API 安定度（v0.10 系での変更頻度、Breaking change の頻度）、コア API（add / build / query）の実体
- **SchemaLLMPathExtractor** の制約強度（プロンプトレベル止まりか、型システムレベルまで）、スキーマ受理形式（dataclass / pydantic / dict / TypedDict のいずれか）
- **SimplePropertyGraphStore** の永続化粒度（章別 vs 全体一括の制御可否、pickle / JSON / parquet どれか）、再ロードの粒度
- **incremental update 方式**（章単位 SHA-256 変更検出 → 影響範囲のみ再構築できるか、それとも全体再構築のみか）
- **HybridRetriever** の fusion 戦略（RRF / Weighted / CombSum / MaxScore のうち何が標準か、API レベルで切替可能か）
- **HippoRAG / LightRAG retrieval** との統合可否

### 4.2 章別管理の実装方針

- ChapterAnchor 集約の具体実装（章のキーアンカーをどう抽出・集約するか）
- 章別 chapter_index.json / concept_index.json のスキーマ
- 章単位 incremental の orchestration（変更章のみ再抽出 → ERG 再構築 → cluster 再計算）
- 階層 cluster の実装（LlamaIndex に hierarchical clustering があるか、自前実装か）

### 4.3 LLM プロバイダー実装

- Claude CLI / Codex CLI の Python 版 subprocess 設計
- 並列実行（concurrent batch）の実装（`asyncio.gather` + `asyncio.Semaphore`）
- LLM 注入の抽象化（LlamaIndex の `LLM` interface を実装するか独自 protocol か）

### 4.4 Cross-Encoder rerank

- 日本語向けモデル選定
- LlamaIndex への統合方法

### 4.5 spec-grag CLI 実装

- フレームワーク選定（Click / Typer / Fire 等）
- パッケージング（`pyproject.toml`、`uv` / `pdm` / `poetry` 等）
- 配布方式

### 4.6 整合性チェックの実装

- グラフ構造ベース検出ルールの具体（Cypher 風クエリで書くか、Python 直書きか）
- ルールベース検出の YAML / TOML スキーマ
- LLM 推論の prompt template（日本語）

### 4.7 Concept 更新案 unified diff

- cluster summary → Concept 文書の生成パイプライン
- diff ライブラリ選定（`difflib` 標準 vs サードパーティ）
- diff の context_radius / unified format の出力規約

### 4.8 Optional Extensions の発動判断

- decision_process 拡張をいつ有効化するか
- `.spec-grag/config.toml` の `[schema.extensions]` で `enabled` を制御

---

## 5. 関連ドキュメント

### リポジトリ内（現行）

- [doc/EXTERNAL_DESIGN.ja.md](EXTERNAL_DESIGN.ja.md): 外部契約（source of truth、不変）
- [CLAUDE.md](../CLAUDE.md): リポジトリレベルの不変ルール

### BAK/（pre-pivot のアーカイブ、参考のみ）

`BAK/` 配下に Rust + graphrag-rs 前提の旧実装と関連調査資料が保管されている。pivot 後の設計には戻らないが、過去の機能調査結果は参考になる場合がある。
