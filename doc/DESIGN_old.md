# SPEC-grag — 仕様策定アシスト用 GraphRAG 連携設計（設計ドキュメント）

> 本ドキュメントは SPEC-grag の **設計ドキュメント**（背景・設計判断・実装計画）。利用者向けの README はリポジトリルート [`README.md`](../README.md) を参照。

## 1. 解決する課題

LLM（GPT-5.3, Opus 4.7 等）は資料への忠実度が高い反面、直近のコンテキスト（部分資料）にアテンションが偏る。仕様策定では以下の問題が発生する。

- 上位概念（本来の目的、コアコンセプト）を無視した局所最適化
- 章間の波及検出が弱く、ある章の修正が他章の前提条件を壊す
- 修正案が KV にアンカーされた瞬間、後続の整合性チェックが正当化トークン化する

人間設計者は各章のキー情報を保持し、現在の問題から関連情報が励起してきて、上位概念から演繹的に整合性をチェックする。本設計は、この「アンカー＋励起＋照射」の認知プロセスを LLM 上で再現する。

## 2. アンカー要素

spec-grag が扱う情報を以下に分類する。

### 2.1 主要要素（コア文書 + 入力）

| # | 名前 | 内容 | 場所 | 更新方法 |
|---|---|---|---|---|
| #1 | **Purpose** | 本来の目的（ビジネスゴール、UX の根幹） | `core.purpose_dir`（例：`docs/SPEC-grag/core/purpose.md`） | 人が手書き、spec-grag では更新しない |
| #2 | **Concept** | コアコンセプト（不変のアーキテクチャ方針、設計思想） | `core.concept_dir`（例：`docs/SPEC-grag/core/concept.md`） | spec-grag が **取得 → 整形 → concept_dir のファイルへ unified diff 提示**（hunk 単位 accept/reject 後にスラッシュコマンド側で書き戻す） |
| - | **課題プロンプト** | 現在の課題（解決すべきボトルネック） | `/spec-realign` の引数 | プロンプトで都度渡す |
| - | **章ファイル群** | 部分資料・現行仕様（実装の詳細） | `sources.include` で指定 | 利用者が編集 |

### 2.2 中間生成物（graphrag-rs グラフ）

| # | 名前 | 内容 | 場所 | 更新方法 |
|---|---|---|---|---|
| #3 | **章別キーアンカー** | 各章の主要エンティティ・キー概念 | graphrag-rs グラフ内 | 3 コマンド共通の前処理でインクリメンタル更新（§7.0）、`/spec-core --all` で全再構築 |
| #4 | **依存グラフエンベディング** | エンティティ関係グラフ + Ollama 埋め込み | `.spec-grag/graph/` に persist | 同上 |
| #5 | **階層クラスタ** | Leiden + LLM 要約（num_levels=3） | graphrag-rs グラフ内 | 同上 |

主要要素は文書として整備し、コマンドで KV に再注入する。中間生成物は graphrag-rs が管理し、励起時に章別キーアンカー（#3）として呼び起こす。

## 3. 励起メカニズム

| 方向 | 内容 |
|---|---|
| 垂直励起 | 課題プロンプトから Purpose / Concept への波及を検査。上位概念のどの項目が揺らぐか列挙 |
| 水平励起 | 他章のデータモデル・インターフェース定義との競合を検査 |

励起の実行主体は graphrag-rs。Hierarchical Clustering（num_levels = 3）と Symbolic Anchoring によって、各章のキーアンカー（#3）と章間の関係アンカーをグラフとして保持し、課題プロンプトを起点に 2 ホップで関連情報を呼び起こす。

章別キーアンカー（#3）は graphrag-rs 内のグラフのみに保持し、各章ファイルの frontmatter には書き戻さない。運用で支障が出た場合（励起精度の劣化、手動補正の必要性、文書側からの手動編集要求等）に限り frontmatter 書き戻しを再検討する。

## 4. アーキテクチャ

```
[Claude Code]
    ↓ スラッシュコマンド（.claude/commands/*.md → Bash 経由）
[spec-grag CLI（独立バイナリ）]
    ↓ Rust crate 依存
[graphrag-core ライブラリ（vendor/graphrag-rs/）]
    ├─ Hierarchical Clustering（Leiden + LLM 要約）
    ├─ Symbolic Anchoring（CatRAG）
    ├─ IncrementalGraphManager（差分更新）
    │   ├─ Delta Computation（Bloom filter）
    │   ├─ Lazy Propagation（80-90% 操作削減）
    │   └─ Async Batching（1000+ ops/sec）
    ├─ ChangeDetector（auto_detect_changes）
    │
    ├─ 要約 LLM: ClaudeCliLanguageModel（拡張、AsyncLanguageModel trait 実装）
    │   └─ subprocess: claude -p --model sonnet --output-format json --no-session-persistence --dangerously-skip-permissions
    └─ 埋め込み: OllamaEmbedderAdapter（既存）
        └─ http://localhost:11434/api/embed (nomic-embed-text)
    ↓
[knowledge graph storage（.spec-grag/graph/）]
    ↑ 入力
[章ファイル群（sources.include で指定された Markdown）]
```

コア文書（Purpose / Concept）の配置先は `.spec-grag/config.toml` の `core.purpose_dir` / `core.concept_dir` で指定する。Concept は `/spec-core` で更新、Purpose は人が手書きで spec-grag では更新しない。

Claude Code のスラッシュコマンドは Bash 経由で `spec-grag` CLI を呼び出し、stdout が Claude Code のコンテキスト（KV）に取り込まれる。これにより `/spec-inject` のコア注入も Bash 経由で実現する。

## 5. LLM 構成

graphrag-rs は **埋め込み生成 + 要約生成 + エンティティ抽出** の 3 種で LLM を使う。本プロジェクトは graphrag-rs の `AsyncLanguageModel` trait（`graphrag-core/src/core/traits.rs:547`）に **ClaudeCliLanguageModel を新規実装**し、要約とエンティティ抽出を Claude Code CLI に流す。埋め込みのみローカル Ollama で生成する。要約・エンティティ抽出は Claude（および将来的に Codex）の CLI subprocess 経由のみとし、ローカル LLM への切り替え（フォールバック）は設けない。

graphrag-rs の標準実装では `LLMEntityExtractor`（`entity/llm_extractor.rs`）が `OllamaClient` を直接保持する設計だが、本プロジェクトでは vendor 拡張により `AsyncLanguageModel` trait 経由に改造し、`ClaudeCliLanguageModel` を注入する（§10 Try & Error 項目）。これにより Ollama は埋め込み専用に純化される。

### 5.1 構成詳細

| 項目 | 内容 |
|---|---|
| 埋め込み | Ollama: nomic-embed-text (274MB) |
| 要約 + エンティティ抽出 | Claude Code CLI（subprocess、Sonnet 4.6） |
| ピーク RAM | 0.5-1GB（埋め込みモデル load 時のみ） |
| 平均 RAM | ~100MB（自動アンロード後） |
| 要約品質 | 高（Claude Sonnet 4.6） |
| 追加課金 | Claude Code サブスク（Sonnet 専用枠を活用） |
| 実装手段 | `ClaudeCliLanguageModel` 新規実装（180-300行） |
| HTTP 層 | なし（trait 経由で直接 subprocess 呼び出し） |

### 5.2 主構成（B-2 派生）の経路

graphrag-rs に対して、`AsyncLanguageModel` trait の新規実装を 1 つ追加する。HTTP プロキシは介さない。

```
[graphrag-rs ライブラリ]
    └─ AsyncGraphRAGBuilder.language_model(Box::new(ClaudeCliLanguageModel::new(...)))
        ↓ trait object
    DocumentTree::generate_llm_summary()  (summarization/mod.rs:421)
        ↓ AsyncLanguageModelAdapter (async_graphrag.rs:21-61)
    AsyncLanguageModel::complete(prompt)
        ↓ ClaudeCliLanguageModel 実装内
    subprocess: claude -p "..." --model sonnet --output-format json --no-session-persistence --dangerously-skip-permissions
```

実装で触るファイル：

| ファイル | 操作 | 規模 |
|---|---|---|
| `vendor/graphrag-rs/graphrag-core/src/generation/claude_cli.rs` | 新規（要約用 ClaudeCliLanguageModel） | 150-250 行 |
| `vendor/graphrag-rs/graphrag-core/src/generation/mod.rs` | `pub mod claude_cli;` 追記 | +2 行 |
| `vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs` | `with_async_claude_cli()` を Builder に追加 + `extract_entities_async` ダミー実装を改造版 LLMEntityExtractor 呼び出しに置換 | +50-80 行 |
| `vendor/graphrag-rs/graphrag-core/src/entity/llm_extractor.rs` | `OllamaClient` 直接依存 → `AsyncLanguageModel` trait 経由に改造 | +100-200 行（仕様変更） |
| `vendor/graphrag-rs/graphrag-core/src/lib.rs` | LLMEntityExtractor 起動箇所（line 839 付近）を `AsyncLanguageModel` 注入パターンに変更 | +20-50 行 |

合計 320-580 行。LLMClient trait の実装は不要（`AsyncLanguageModelAdapter` が `AsyncLanguageModel` から自動変換するため）。

注：`--bare` フラグは OAuth サブスク認証と非互換のため使用しない（`Not logged in · Please run /login` で fail する）。

## 6. プロジェクト設定ファイル

SPEC-grag は対象プロジェクトのルートに `.spec-grag/config.toml` を置いて動作する。コマンドは CWD から親方向に config.toml を探索する（git の `.git/` 解決と同様）。プロジェクト追加時に SPEC-grag 本体を編集しない設計。

`.spec-grag/config.toml` は **プロジェクトの git コミット対象**（チームのデフォルト設定 = テンプレート）。個人差（claude/codex の好み等）が出た場合は手元で編集する。`.spec-grag/graph/` は実行時の永続化データなので **`.gitignore` 対象**。

### 6.1 設定項目

```toml
[sources]
# 章ファイル群の glob パターン。複数指定可
include = [
  "docs/spec/**/*.md",
]
# 除外パターン
exclude = ["**/drafts/**"]

[core]
# Purpose（本来の目的）。人が手書き。spec-grag は更新しない
purpose_dir = "docs/SPEC-grag/core/purpose.md"
# Concept（コアコンセプト）。spec-grag が作成・差分提示する
concept_dir = "docs/SPEC-grag/core/concept.md"

[graph]
# graphrag-rs のグラフ永続化先。`.gitignore` 推奨
storage = ".spec-grag/graph/"

[llm]
# 要約 LLM プロバイダー
# "claude_cli" → 主構成（ClaudeCliLanguageModel を graphrag-rs に注入）
# "codex_cli"  → 将来拡張（CodexCliLanguageModel、未実装。指定しても起動時エラー）
summary_provider = "claude_cli"

[llm.claude_cli]
# 起動コマンド（PATH 上の claude バイナリ）
command = "claude"
# モデル指定（Sonnet 推奨：要約品質 + Sonnet 専用枠活用）
model = "sonnet"

[llm.codex_cli]
# 将来拡張用ブロック。Codex CLI 実装後に有効化される
# 現時点で summary_provider = "codex_cli" を指定すると起動時に「未実装」エラー
command = "codex"
model = "gpt-5.4"  # 暫定値。Codex CLI の実機検証で確定
```

注：subprocess の timeout、retry 戦略、stdin/stdout バッファサイズ等の詳細パラメータは、ClaudeCliLanguageModel 実装中に確定する。

### 6.2 配置例

```
your-project/
├── .spec-grag/
│   ├── config.toml
│   └── graph/                    # 永続化（.gitignore）
├── docs/
│   ├── SPEC-grag/
│   │   └── core/
│   │       ├── purpose.md
│   │       └── concept.md
│   └── spec/                     # 章ファイル群
│       └── ...
```

別プロジェクトでは `include` を該当する Markdown 配置パス（例：`docs/architecture/**/*.md`）に変えるだけで動く。SPEC-grag 本体（`/home/kazuki/public_html/spec-grag/`）は変更不要。

### 6.3 初期セットアップ

SPEC-grag 本体に同梱されているテンプレートをコピーして使う：

```bash
# 対象プロジェクトに移動
cd /path/to/your-project

# テンプレートをコピー
cp -r /home/kazuki/public_html/spec-grag/templates/.spec-grag .

# 自分の環境に合わせて include / core.dir を編集
$EDITOR .spec-grag/config.toml

# graph/ ディレクトリは git ignore に追加
echo ".spec-grag/graph/" >> .gitignore
```

テンプレート本体は [`templates/.spec-grag/config.toml`](../templates/.spec-grag/config.toml)。SPEC-grag 本体を更新したらテンプレートも更新されるので、必要に応じて手動で再コピー（自動同期はしない）。

## 7. コマンド体系

### 7.0 graphrag-rs グラフ更新（3 コマンド共通の前処理）

graphrag-rs グラフは以下 3 種の中間生成物で構成される（詳細は §2.2 参照）：

| # | 名前 | 場所 |
|---|---|---|
| #3 | 章別キーアンカー | graphrag-rs グラフ内 |
| #4 | 依存グラフエンベディング | `.spec-grag/graph/` に persist |
| #5 | 階層クラスタ | graphrag-rs グラフ内 |

すべてのコマンド（`/spec-realign`, `/spec-inject`, `/spec-core`）は本処理の前に以下を機械的に実行する：

| 処理 | 内容 | 更新対象 |
|---|---|---|
| 変更ファイル検出 | `sources_scanned_through` 以降に更新された章ファイル（`sources.include`）を抽出 | - |
| graphrag-rs feed | 変更ファイルを `DocumentContent` として graphrag-rs に渡す | - |
| 章別キーアンカー更新 | LLMEntityExtractor（vendor 改造版）が ClaudeCliLanguageModel 経由で Claude Sonnet にエンティティ抽出を依頼（Symbolic Anchoring / CatRAG-style） | #3 |
| 依存グラフエンベディング更新 | Ollama (nomic-embed-text) で章別エンティティの埋め込み生成 + 関係グラフ構築 | #4 |
| 階層クラスタ更新 | Leiden + LLM 要約で num_levels=3 の階層クラスタを delta_computation で更新 | #5 |

これらは graphrag-rs の `auto_detect_changes = true` により、変更分のみ更新（**インクリメンタル**）される。

**例外**：`/spec-core --all` のみ、#3 / #4 / #5 を **全再構築**する（章ファイル群を全 feed → 階層クラスタを再生成）。

### 7.1 `/spec-realign <課題プロンプト>`

仕様編集時の本流ワークフロー。修正案を出す前に励起・照射を強制し、KV バイアスを抑える。

#### 7.1.1 ワークフロー

```
① 課題プロンプト受領
② コア同期 + 注入（§7.0 の前処理 → Concept 更新があれば diff 提示・accept/reject → Purpose / Concept を KV に再充填）
③ 章別キーアンカーの励起取得
   メイン LLM 側：
   (a) Agentic サーチ：grep / Read / Glob ツールで課題プロンプト関連情報を収集
   (b) KeywordExtractor：(a) と課題プロンプトから high_level（抽象概念）/ low_level（具体エンティティ）を分離抽出（LightRAG Dual-Level Retrieval）
   spec-grag CLI 側（橋渡し専用、Bash 経由で呼ばれる）：
   (c) graphrag-rs::hierarchical_query() を抽出キーワードで呼び出し → QueryResult[]
   (d) QueryResult.chunk_ids → TextChunk.document_id への逆引き
   (e) document_id（= 章ファイル）でグルーピング → stdout 出力
   メイン LLM はこの stdout を tool_result として KV に取り込み、章別キーアンカーを得る（章本文は KV に流入させない）
④ 守るべき制約の導出
   課題プロンプト + Purpose / Concept + 章別キーアンカー → 絞り込まれた守るべき制約
   この書き起こしが KV に制約をアンカーする
⑤ 解決案の構想
   課題プロンプト + 守るべき制約 → 解決案
⑥ 波及先の導出
   解決案を入力に、graphrag-rs::hierarchical_query() で波及先を抽出（外部処理、メイン LLM の KV を直接汚染しない）
⑦ 修正解決案の策定
   波及先への解決案の適用 → 修正解決案
⑧ 守るべき制約のチェック
   監査役 subagent が独立 KV で「修正解決案 vs 守るべき制約」を検証
   違反があれば⑤に戻る
⑨ 最終案の提示
```

順序の根拠：④で守るべき制約を KV にアンカーすることで、⑤の解決案生成が制約に縛られる。⑥は graphrag-rs に外注するためメイン LLM の KV を直接汚染しない。⑧は独立 subagent で正当化バイアスを排除する。

#### 7.1.2 CLI 契約

**コマンド**：`spec-grag realign <prompt> [--high <kw,...>] [--low <kw,...>] [--max-per-doc <N>]`

**引数**：

| 引数 | 必須 | 説明 |
|---|---|---|
| `<prompt>` | Y | 課題プロンプト（位置引数） |
| `--high <kw,...>` | N | 抽象概念キーワード（カンマ区切り、複数指定可）。LightRAG high_level |
| `--low <kw,...>` | N | 具体エンティティキーワード（カンマ区切り、複数指定可）。LightRAG low_level |
| `--max-per-doc <N>` | N | 章あたりキーアンカー上限（デフォルト 3） |

**読み取り対象**：
- `.spec-grag/config.toml`（CWD から親方向探索）
- `core.purpose_dir` / `core.concept_dir`
- 章ファイル群（`sources.include`）
- `.spec-grag/graph/` 配下のグラフ永続化データ

**前処理**：§7.0 共通（章別キーアンカー / 依存グラフエンベディング / 階層クラスタのインクリメンタル更新）

**処理ステップ**：上記ワークフローの (c) / (d) / (e) を CLI が担当。メイン LLM 側の (a) / (b) は事前に行ってキーワードを引数で受け渡す。

**出力（stdout）**：
- 形式：Markdown
- 構造：
  - `# /spec-realign — 仕様編集ワークフロー`
  - `## ① 課題プロンプト`：渡されたプロンプト
  - `## Purpose` / `## Concept`：`/spec-inject` 同様
  - `## ③ 章別キーアンカー`：document_id ごとに keyword リスト
- 章本文は流入させない

**副作用**：`.spec-grag/graph/` への書き込み（前処理経由）

**終了コード**：
- 0：正常
- 1：設定不在 / 設定パースエラー
- 2：graphrag-rs エラー / Claude CLI エラー

### 7.2 `/spec-inject`

#### 7.2.1 動作

コア同期 + 注入を実行する軽量コマンド。§7.0 の前処理 → Concept 更新があれば diff 提示・accept/reject → Purpose / Concept を KV に再充填する。ユーザーが議論のドリフトを感知した時に発火する。`/spec-realign` の②と機能的に等価だが、独立コマンドとして切り出すことでドリフト時の再注入 UX を最小コストにする。

#### 7.2.2 CLI 契約

**コマンド**：`spec-grag inject`

**引数**：なし

**読み取り対象**：
- `.spec-grag/config.toml`
- `core.purpose_dir` / `core.concept_dir`
- 章ファイル群（前処理用）

**前処理**：§7.0 共通（インクリメンタル更新）

**処理ステップ**：
- Purpose / Concept ファイルを読み込む
- Markdown に整形して stdout に出力

**出力（stdout）**：
- 形式：Markdown
- 構造：
  - `# Core ドキュメント注入 (/spec-inject)`
  - `## Purpose — <path>`：Purpose 全文
  - `## Concept — <path>`：Concept 全文

**副作用**：`.spec-grag/graph/` への書き込み（前処理経由）

**終了コード**：
- 0：正常
- 1：設定不在 / 設定パースエラー
- 2：graphrag-rs エラー

### 7.3 `/spec-core`

#### 7.3.1 動作

Concept 文書（#2）の自動メンテナンスコマンド。**人間が明示的に発火する**（diff の accept/reject を含むため）。インクリメンタル更新（引数なし）が基本で、`--all` は手動再構築用。

`/spec-realign` `/spec-inject` の前処理（§7.0）でグラフは常に最新化されるため、`/spec-core` 単独実行は「Concept 更新案のみを確認したい」場合に使う。

| 引数 | 動作 |
|---|---|
| なし（incremental） | §7.0 のインクリメンタル更新 → 階層クラスタ要約から Concept 更新案を **取得 → 整形** → 既存 `concept_dir` のファイルとの **unified diff** 提示 |
| `--all` (`-a`) | §7.0 を全再構築モードで実行（章ファイル群を全 feed → 階層クラスタ再生成）→ 上記と同様に Concept 更新案 unified diff を提示（差分は大きくなる傾向） |

Purpose（#1）は spec-grag では一切扱わない（人が手書き保守）。

タイムスタンプは Concept 文書の frontmatter に保持する：

```yaml
---
last_updated: 2026-04-25T10:30:00Z
sources_scanned_through: 2026-04-25T10:00:00Z
---
```

#### 7.3.2 CLI 契約

**コマンド**：`spec-grag core [--all|-a]`

**引数**：

| 引数 | 必須 | 説明 |
|---|---|---|
| `--all` / `-a` | N | 全再構築モード（デフォルトはインクリメンタル） |

**読み取り対象**：
- `.spec-grag/config.toml`
- `core.concept_dir`（既存 Concept ファイル）
- 章ファイル群

**前処理**：
- `--all` なし：§7.0 共通インクリメンタル更新
- `--all` あり：§7.0 全再構築（章ファイル群を全 feed → 階層クラスタ再生成）

**処理ステップ**：
- 階層クラスタ要約を取得 → Concept 更新案として整形
- 既存 `concept_dir` のファイルとの unified diff を生成（context_radius 10 程度）

**出力（stdout）**：
- 形式：Markdown + unified diff
- 構造：

  ````markdown
  # /spec-core — Concept 更新メンテナンス

  対象: <project_root>
  モード: incremental / --all

  ## 変更検出（incremental のみ）

  最終 sync: <timestamp>
  変更ファイル: N 件
  - <path>

  ## Concept 更新案

  ```diff
  --- <concept_dir> (現行)
  +++ <concept_dir> (提案)
  @@ -10,5 +10,7 @@
   既存内容
  +追加行
  ```
  ````

- 差分なしの場合：「Concept に変更なし」のみ出力（diff ブロックは省略）

**副作用**：
- `.spec-grag/graph/` への書き込み（前処理経由）
- **`core.concept_dir` への書き戻しはこの CLI では行わない**（hunk 単位の accept/reject 後にスラッシュコマンド側 / LLM が書き戻す）

**終了コード**：
- 0：正常（差分あり / なし問わず）
- 1：設定不在 / 設定パースエラー / `concept_dir` が存在しない場合は新規作成扱い
- 2：graphrag-rs / Claude CLI エラー

## 8. GraphRAG-rs の機能根拠

| 機能 | 用途 |
|---|---|
| Symbolic Anchoring (CatRAG-style) | 抽象概念を具体エンティティに自動 grounding。章別キーアンカー（#3）抽出。実装は `LLMEntityExtractor`（下記）が担当 |
| LLMEntityExtractor | LLM ベースのエンティティ抽出（`entity/llm_extractor.rs`）。graphrag-rs 標準は `OllamaClient` を直接保持する設計だが、本プロジェクトでは vendor 拡張で `AsyncLanguageModel` trait 経由に改造（§10 Try & Error 項目）。改造後は ClaudeCliLanguageModel が呼ばれ、章別キーアンカー作成も Claude Sonnet 4.6 で行う |
| Hierarchical Relationship Clustering | Leiden アルゴリズム + LLM 要約で多階層化（num_levels = 3）。Concept 候補（クラスタ要約）を自動抽出 |
| LLM-generated cluster summaries | クラスタの代表テキスト生成。Concept 候補 |
| Leiden Community Detection | +15% modularity（Sci Reports 2019）。関連章のグルーピング |
| IncrementalGraphManager | フル再構築なしのグラフ更新 |
| Delta Computation | Bloom filter による最小 diff 計算 |
| Lazy Propagation | 関係更新の遅延（80-90% 操作削減） |
| Async Batching | 1000+ ops/sec の非同期更新 |
| ChangeDetector | API 経由で渡された `DocumentContent` の差分を自動検知（`auto_detect_changes = true`）。graphrag-rs 自体には FS 監視機能はない（`notify` 等の依存無し）ので、章ファイル群 → graphrag-rs への反映は spec-grag CLI が §7.0 で実行する |
| AsyncLanguageModel trait | LLM プロバイダー抽象化。本プロジェクトはこの trait に ClaudeCliLanguageModel を実装して要約 LLM を差し替える |
| LightRAG Dual-Level Retrieval | high_level（抽象概念）/ low_level（具体エンティティ）の 2 階層キーワード分離。本プロジェクトではメイン LLM が抽出役を担い、抽出キーワードを graphrag-rs::hierarchical_query() に渡す |
| hierarchical_query | クエリと階層クラスタの一致度で QueryResult（keywords, chunk_ids, summary, level）を返す。本プロジェクトでは章別キーアンカー取得（§7.1.1 ③）に使う |

実装ソース: [`graphrag-core/src/incremental/`](https://github.com/automataIA/graphrag-rs/tree/main/graphrag-core/src/incremental)

本プロジェクトでは graphrag-rs を `vendor/graphrag-rs/` に同梱し、ClaudeCliLanguageModel 拡張を加えた状態でビルドする。upstream への PR 提出は動作確認後に検討。

## 9. 監査役 subagent

`/spec-realign` の⑧で起動する独立 subagent。同一エージェント内のセルフチェックは、自分が出した修正案を KV にアンカーしたまま検証するため正当化方向に流れる。subagent は元の修正案の生成プロセスを知らない状態で起動し、独立した KV から検証する。

spec-grag は LLM のアテンション矯正ツールであり、用語の一貫性や制約遵守の網羅検証は LLM 本体（メインエージェントまたは別の書き直しコマンド）の役割。監査役は **アテンション崩壊（上位概念の破壊）の検出** に特化する。

### 9.1 検証観点

1. **垂直整合性**：修正解決案を Purpose / Concept と直接比較し、上位概念から逸脱していないかを検証
2. **波及検査（水平整合性）**：修正解決案を graphrag-rs に入力 → 励起された波及先（他章の関連箇所）を抽出 → 波及先が Purpose / Concept を破壊していないかを検証

### 9.2 入出力

入力：
- Purpose / Concept 文書
- ④の守るべき制約
- ⑦の修正解決案

出力：
- 各観点の違反列挙（なければ「違反なし」）
- 違反ごと：違反 ID、修正解決案の該当箇所、是正方向
- 総合判定：適合 / 修正必要

## 10. 実装時の Try & Error 項目

- **`/spec-realign` のプロンプト実装**：`.claude/commands/spec-realign.md` の本文。§7.1.1 のフローを LLM が実行するためのプロンプト。CLI 契約（§7.1.2）と整合
- **`/spec-inject` のプロンプト実装**：`.claude/commands/spec-inject.md` の本文。CLI 契約（§7.2.2）と整合
- **`/spec-core` のプロンプト実装**：`.claude/commands/spec-core.md` の本文。CLI 契約（§7.3.2、unified diff）と整合
- **監査役 subagent の具体プロンプト**：垂直整合性 + 波及検査の 2 観点を実装
- **ClaudeCliLanguageModel 実装詳細**：subprocess の timeout 設定、stdout JSON パース、レート制限到達時の retry 戦略、concurrent 呼び出しの pool 化
- **LLMEntityExtractor の AsyncLanguageModel 対応化**：graphrag-rs vendor の `entity/llm_extractor.rs` を `OllamaClient` 直接依存から `AsyncLanguageModel` trait 経由に改造し、`ClaudeCliLanguageModel` を注入できるようにする。`AsyncGraphRAG::extract_entities_async`（現状ダミー）も改造版 `LLMEntityExtractor` 呼び出しに置換。エンティティ抽出も Claude Sonnet 経由になる（§7.0 §8 参照）
- **励起取得ロジック詳細**：spec-grag CLI 内の hierarchical_query() 呼び出し、QueryResult.chunk_ids → TextChunk.document_id 逆引き、章別グルーピングの実装
- **§7.0 共通前処理の実装**：3 コマンドの冒頭で graphrag-rs グラフを章ファイル群と同期する処理（変更ファイル検出 → feed → #3/#4/#5 更新）
- **CodexCliLanguageModel の実装可否**：Codex CLI の headless mode コマンド形式（`codex exec` 等）、JSON 出力スキーマ、モデル指定方法、ChatGPT Plus サブスクのレート制限挙動を実機検証してから実装。設定スキーマ上は枠を確保済み（`summary_provider = "codex_cli"`）
