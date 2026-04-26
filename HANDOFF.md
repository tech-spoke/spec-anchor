# SPEC-grag 引き継ぎメモ（実装フェーズ）

> 前セッションで設計フェーズが完了し、実装の MVP スケルトンが動作するところまで進んだ。本ファイルは新セッションで最小コストで実装を続けるための引き継ぎ。
> 設計の本体は [doc/DESIGN.md](doc/DESIGN.md) を参照。本ファイルは「進捗」「残り作業」「環境状態」「実装上の注意点」のみを扱う。

---

## 1. 完了済み

### 1.1 設計

- [doc/DESIGN.md](doc/DESIGN.md)：仕様策定アシスト用 GraphRAG 連携の設計ドキュメント
  - アーキテクチャ：spec-grag CLI（独立バイナリ）+ graphrag-rs vendor 同梱
  - LLM 構成：要約 = Claude CLI（subprocess）/ 埋め込み = Ollama (nomic-embed-text)
  - コマンド体系：`/spec-realign` `/spec-inject` `/spec-core`
  - 監査役 subagent：垂直整合性 + 波及検査の 2 観点
  - Try & Error 項目（§10）：実装時に詰める

### 1.2 graphrag-rs 拡張

- `vendor/graphrag-rs/graphrag-core/src/generation/claude_cli.rs`（240 行、新規）
  - `ClaudeCliLanguageModel`：`AsyncLanguageModel` trait 実装
  - subprocess: `claude -p --model {sonnet} --output-format json --bare --no-session-persistence --dangerously-skip-permissions`
  - 単体テスト 8 個全 pass
- `vendor/graphrag-rs/graphrag-core/src/generation/mod.rs`：`pub mod claude_cli;` 追加
- `vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs`：`with_async_claude_cli()` / `with_async_claude_cli_default()` 追加

### 1.3 spec-grag CLI スケルトン

- `Cargo.toml`：clap, serde, toml, tokio, anyhow, thiserror, serde_json, glob, graphrag-core (path 依存)
- `src/main.rs`：clap でサブコマンド分岐、`#[tokio::main] async fn main`
- `src/config.rs`：`.spec-grag/config.toml` ローダー、`Project::discover()`（git の `.git/` 解決同様、親方向探索）
- `src/commands/mod.rs`：サブコマンドモジュール宣言
- `src/commands/inject.rs`：`/spec-inject`（Purpose / Concept を stdout 出力）
- `src/commands/realign.rs`：`/spec-realign`（プロンプト + inject 呼び出し、③以降は TODO）
- `src/commands/core.rs`：`/spec-core`（章ファイル群一覧表示、差分計算は TODO）
- `templates/.spec-grag/config.toml`：利用者向け設定テンプレート
- `.gitignore`：target/, vendor/graphrag-rs/target/, エディタ系

### 1.4 環境構築

| 項目 | バージョン | 備考 |
|---|---|---|
| pkg-config | 1.8.1 | `sudo apt install pkg-config` |
| Rust toolchain | 1.95.0 | rustup |
| Ollama | 0.21.2 | systemd で active |
| nomic-embed-text | 274MB | `ollama pull` 済み |
| libssl-dev | 3.0.13 | openssl-sys ビルド用 |
| zstd | 1.5.5 | ollama インストーラ前提 |

### 1.5 ビルド・動作確認

- `cd vendor/graphrag-rs && cargo build --release` 成功（3m 16s、`graphrag`, `graphrag-cli`, `graphrag-server` 等のバイナリ生成）
- `cargo build --release`（spec-grag）成功（2m 38s + インクリメンタル 5.85s、`target/release/spec-grag` 1.35MB）
- `cargo test -p graphrag-core --lib generation::claude_cli` 全 8 テスト pass
- `/tmp/spec-grag-test/` で実機動作確認済み：
  - `spec-grag --version` / `--help` ✅
  - `spec-grag inject` ✅（Purpose / Concept 読み込み + stdout）
  - `spec-grag core` / `core --all` ✅（章ファイル群一覧）
  - `spec-grag realign <prompt>` ✅（課題プロンプト + inject 呼び出し）

### 1.6 ClaudeCliLanguageModel 実機検証（優先 1 完了）

- `vendor/graphrag-rs/graphrag-core/examples/claude_cli_smoke.rs` 新規作成
- `cargo run --example claude_cli_smoke --release` 全 5 項目 pass
- 検証結果：
  - `is_available()` ✅ 134ms で `true`（claude 2.1.119 検出）
  - `model_info()` ✅ `claude-cli:sonnet`（max_ctx 200k）
  - `complete("...")` ✅ 単発 3.4s で正常な応答
  - シーケンシャル x5 ✅ avg 3.96s/call
  - 並列 x5 via `complete_batch_concurrent` 🟡 動くが直列と同等（20.6s vs 19.8s）→ §4.7 参照
- **重要な発見・修正**：`--bare` フラグは OAuth サブスク認証と非互換（`Not logged in · Please run /login` で fail）
  - `claude_cli.rs::build_args` から `--bare` を削除
  - 単体テストも追従（`--bare` が含まれないことを assert）
  - 削除理由を doc コメントで明記
- `--dangerously-skip-permissions` の挙動：subprocess から permission prompt は出ず正常動作。`--no-session-persistence` と組み合わせで session 汚染なし

### 1.7 励起取得ロジック実装（優先 2、骨格まで完了）

**vendor 拡張**（[vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs](vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs)）:
- `AsyncGraphRAG::load_state_async(state_dir)` — `save_state_async` の対称。`async_knowledge_graph.json` と `*_async_tree.json` をディレクトリから読み込み、内部状態を置き換える
- `AsyncGraphRAG::hierarchical_query_grouped(query, max_per_doc)` — `Vec<(DocumentId, QueryResult)>` を返す。各結果がどの document（章）由来かを追跡
- `AsyncGraphRAG::document_id_for_chunk(chunk_id)` — chunk → document の逆引き
- `AsyncGraphRAG::document_tree_count()` — ロード済み tree 数の確認用

**spec-grag 側**:
- [src/excitation.rs](src/excitation.rs) 新規（180 行）。グラフロード → キーワードごとに `hierarchical_query_grouped` → `(document_id, level)` で BTreeMap 整形 → stdout に Markdown 出力
- [src/main.rs](src/main.rs) Realign に `--high <kw,...>` `--low <kw,...>` `--max-per-doc <N>` を追加（LightRAG dual-level retrieval のキーワードを CLI 引数で受領）
- [src/commands/realign.rs](src/commands/realign.rs) ② の inject 後に `excitation::run` を呼ぶ wire up

**動作確認 3 分岐**（`/tmp/spec-grag-test/`）:
- グラフディレクトリ無し → ⚠ warning + skip
- グラフディレクトリ空 → ⚠ warning + skip
- キーワード未指定 → 「励起をスキップします」+ skip
- いずれも exit 0 で realign の④以降を継続できる

**残課題**：グラフ自体が無い状態（優先 4 で `core --all` 実装後に解消）。励起モジュール本体は完成しているので、グラフが構築されれば自動的に end-to-end 動作する。

**単体テスト**：5 件全 pass（excitation 4 件 + config 1 件）。release ビルドも成功。

### 1.8 スラッシュコマンド実装（優先 3）⚠️ 破綻状態に降格

**ステータス変更（2026-04-26）**：当初「完了」と記録したが、**CLI 出力フォーマットを設計する前にプロンプトを書いたため、CLI が出さない出力を前提にした破綻プロンプト**になっていることが判明。`spec-core.md` が代表例（CLI は unified diff を出さないのに、プロンプトは diff 提示・accept/reject 判定を前提）。**§2.5(a)(b) の CLI 実装後に §2.5(c) で書き直しが必要**。

**配置先**：`templates/.claude/commands/`（利用者プロジェクトにコピーする想定）

| ファイル | 状態 | 概要 |
|---|---|---|
| [spec-inject.md](templates/.claude/commands/spec-inject.md) | ⚠️ 要 CLI 整合確認 | `!spec-grag inject` をインライン実行 |
| [spec-core.md](templates/.claude/commands/spec-core.md) | ❌ 破綻 | CLI が unified diff を出さないため、accept/reject 判定が空転する |
| [spec-realign.md](templates/.claude/commands/spec-realign.md) | ⚠️ 要 CLI 整合確認 | 9 ステップワークフロー。励起取得（§1.7）の出力と整合しているか未検証 |

**書いたプロンプト方針（再書き直し時も保持）**：
- 抽象的な Level 表記ではなく **Purpose / Concept / 課題プロンプト / 章ファイル** の具体表現
- spec-realign.md 冒頭に「用語の定義」テーブル
- パスは `.spec-grag/config.toml` 由来として記述（`core.purpose_dir` / `core.concept_dir` / `sources.include` / `graph.storage`）。プロジェクトごとに異なるので、`spec-grag inject` の出力 or `.spec-grag/config.toml` を `Read` して取得するよう LLM に指示

**実機検証**：CLI 実装完了 + プロンプト改訂後に、外側の Claude Code セッションで `/spec-realign "test"` を打って発火確認（§4.13 参照）。

---

## 2. 残り作業（DESIGN.md §10 Try & Error 項目）

優先順序は依存関係を考慮して以下を推奨。

### 2.1 ClaudeCliLanguageModel の実機検証（優先 1）✅ 完了

§1.6 に結果を集約。スキップして §2.2 へ。

### 2.2 励起取得ロジック実装（優先 2）✅ 骨格完了

§1.7 に結果を集約。グラフ構築（優先 4）完了後に end-to-end 検証。

### 2.3 スラッシュコマンド実装（優先 3）⚠️ 破綻状態に降格

§1.8 に結果を集約。CLI 出力フォーマット未確定のままプロンプトを書いたため破綻。§2.5(c) で再書き直しが必要。

### 2.4 ClaudeCliLanguageModel の concurrent batch override（優先 3.5、優先 4 の前提）

**目的**：`AsyncLanguageModel::complete_batch_concurrent` のデフォルト実装が並列化されておらず（§4.7）、優先 4 のクラスタ要約で大量 LLM call が発生したときに直列実行で詰まる。優先 4 着手前に必ず潰す。

**やること**（[vendor/graphrag-rs/graphrag-core/src/generation/claude_cli.rs](vendor/graphrag-rs/graphrag-core/src/generation/claude_cli.rs)）：

- `ClaudeCliLanguageModel` で `complete_batch_concurrent` を override
- 実装パターン：[async_graphrag.rs:429-444](vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs) の `answer_questions_batch` と同じく `futures::stream::FuturesUnordered` または `tokio::task::JoinSet`
- `max_concurrent` パラメータを尊重（subscription レート / システム負荷の両方を考慮し、デフォルトは 5〜10 程度）
- 順序保証：戻り値は入力 `prompts` と同順になるように index を持って戻す
- エラー時の挙動：1 件失敗で全体 abort するか、残りを継続するかを決める（推奨：fail-fast、最初のエラーで abort）

**動作確認**：

- `examples/claude_cli_smoke.rs` の concurrent x5 を再測定
- 期待値：直列 ~20s → 並列 ~4s（5 倍速）
- 単体テストはモックに置き換えて並列性検証（subprocess を起動せず`AsyncLanguageModel` の override パスだけテスト）

**参考**：

- [HANDOFF.md §4.7](HANDOFF.md) — 直列実行になっている事実と実測値
- [DESIGN.md §10](doc/DESIGN.md) — Try & Error 項目の「concurrent pool 化」

### 2.5 graphrag-rs feed 共通前処理 + Concept 差分提示実装（優先 4）

**目的**：DESIGN.md §7.0（3 コマンド共通の feed 前処理）+ §7.3（Concept 更新案 unified diff 提示）の本格実装。グラフ構築（クラスタ要約 = 大量 LLM call）を含むので、優先 3.5 の並列化を先に済ませること。

本作業は **DESIGN.md §7.0 / §7.1.2 / §7.2.2 / §7.3.2 の CLI 契約** に従って実装する。CLI 契約は仕様（規定）、本作業はその実装（タスク）の関係。

**(a) 3 コマンド共通の feed 前処理（DESIGN.md §7.0）**

**前提：LLMEntityExtractor の AsyncLanguageModel 対応化（vendor 拡張）**

graphrag-rs 標準の `LLMEntityExtractor`（`entity/llm_extractor.rs`）は `OllamaClient` を直接保持する設計のため、現状では章別キーアンカー（#3）作成が Ollama 専用。さらに `AsyncGraphRAG::extract_entities_async` は Mark Twain 登場人物名がハードコードされたダミー実装。spec-grag の方針（要約・エンティティ抽出は Claude CLI、Ollama は埋め込み専用）と整合させるため、以下の vendor 拡張が必要（§4.x 参照）：

- `entity/llm_extractor.rs`：`OllamaClient` フィールドを `Arc<dyn AsyncLanguageModel<Error = GraphRAGError>>` に置換、JSON 抽出プロンプト経路を `AsyncLanguageModel::complete` 経由に書き直し（100-200 行）
- `lib.rs:839 付近`：`LLMEntityExtractor::new(client, ...)` を `AsyncLanguageModel` 注入パターンに変更（20-50 行）
- `async_graphrag.rs::extract_entities_async`：現状のダミー実装を改造版 `LLMEntityExtractor` 呼び出しに置換（30-50 行）

これで章別キーアンカー作成も `ClaudeCliLanguageModel` 経由（Claude Sonnet 4.6）になる。

**spec-grag CLI 側の実装**

- `src/sync.rs` 新規（または `src/commands/feed.rs`）：
  - 変更ファイル検出（`sources_scanned_through` 比較）
  - graphrag-rs に feed（`AsyncGraphRAG::add_document` を変更分のみ）
  - #3 章別キーアンカー / #4 依存グラフエンベディング / #5 階層クラスタを `auto_detect_changes = true` でインクリメンタル更新
  - `save_state_async` でグラフ永続化
- `--all` 時は feed 範囲を全章ファイルに拡大、#3/#4/#5 を全再構築
- `commands/{realign,inject,core}.rs` の冒頭で sync を呼ぶ

**(b) Concept 差分提示（DESIGN.md §7.3 / §7.3.2 CLI 契約）**

- `src/commands/core.rs` の TODO を実装
- graphrag-rs の階層クラスタ要約から **Concept 更新案** を導出
- 既存 `concept.md` との **unified diff** を生成（[`similar` クレート](https://crates.io/crates/similar) で `context_radius` 10 程度）
- 「変更なし」の場合は diff を出さず、その旨だけ表示

CLI 出力フォーマット（ユーザー合意済）：

````markdown
# `/spec-core` — Concept 更新メンテナンス

対象: /path/to/project
モード: incremental / --all

## 変更検出（incremental のみ）

最終 sync: 2026-04-25T10:00:00Z
変更ファイル: 2 件
- docs/spec/chapter1.md

## Concept 更新案

```diff
--- docs/SPEC-grag/core/concept.md (現行)
+++ docs/SPEC-grag/core/concept.md (提案)
@@ -10,5 +10,7 @@
 既存内容
+追加行
```
````

**(c) スラッシュコマンドの改訂（DESIGN.md §7.1.2 / §7.2.2 / §7.3.2 CLI 契約）**

- 現状の `templates/.claude/commands/spec-core.md` は CLI 未実装の機能を前提（§1.8 末尾参照）
- (b) の CLI 出力フォーマットに合わせて 3 ファイル全部書き直す（spec-core.md / spec-realign.md / spec-inject.md）
- LLM の役割：CLI 契約に従う stdout を解釈、ユーザーに accept/reject を尋ねる（spec-core）、章別キーアンカーを KV に取り込む（spec-realign）、Purpose / Concept を KV に取り込む（spec-inject）
- spec-core では accept された hunk を `core.concept_dir` のファイルに書き戻すのは LLM 側（CLI は diff 提示のみ、§7.3.2 副作用節）

**順序**：(a) → (b) → (c)。(a) 完成で励起（優先 2、§1.7）も end-to-end で動くようになる（副作用としてグラフ無し問題が解消）。

### 2.6 監査役 subagent プロンプト実装（優先 5）

**やること**：`.claude/agents/` 配下（または別配置）に subagent 定義を作成。

- 入力：Purpose / Concept 文書、④の守るべき制約、⑦の修正解決案
- 検証観点：垂直整合性 + 波及検査（DESIGN.md §9.1）
- 出力：違反項目 + 総合判定

`/spec-realign` のフロー⑧で起動される設計。

---

## 3. 環境状態

### 3.1 WSL2 メモリ

- 設定：20GB（`.wslconfig` で設定済み、増強後）
- swap：4GB
- 過去の OOM 履歴：12GB 時に graphrag-core release ビルドで OOM kill。20GB に増強後は通る

### 3.2 ディレクトリ構造

```
/home/kazuki/public_html/spec-grag/
├── Cargo.toml                              # spec-grag CLI
├── HANDOFF.md                              # 本ファイル
├── .gitignore
├── doc/
│   └── DESIGN.md                           # 設計ドキュメント
├── src/
│   ├── main.rs
│   ├── config.rs
│   └── commands/
│       ├── mod.rs
│       ├── inject.rs
│       ├── realign.rs
│       └── core.rs
├── templates/
│   └── .spec-grag/
│       └── config.toml                     # 利用者向けテンプレート
├── target/                                 # spec-grag ビルド成果物（.gitignore）
└── vendor/
    └── graphrag-rs/                        # --depth 1 clone、claude_cli 拡張済
        ├── graphrag-core/src/generation/claude_cli.rs   # 新規
        ├── graphrag-core/src/generation/mod.rs          # 編集
        ├── graphrag-core/src/async_graphrag.rs          # 編集
        └── target/                                       # graphrag-rs ビルド成果物（.gitignore）
```

### 3.3 テスト環境

- `/tmp/spec-grag-test/` に簡易テストプロジェクト（前セッションで作成）
- 構造：`.spec-grag/config.toml` + `docs/SPEC-grag/core/{purpose,concept}.md` + `docs/spec/chapter{1,2}.md`
- 削除可（必要なら再作成すれば良い）

---

## 4. 実装上の注意点

### 4.1 `--dangerously-skip-permissions` の実機検証必要

`claude_cli.rs::build_args` で常に追加している。subprocess から permission prompt を回避するため必要と判断したが、実機検証で：

- 実際に subprocess から permission prompt が出ないか
- セキュリティ上の影響（権限の影響範囲）
- `--bare` モードと組み合わせた挙動

を確認する必要がある。問題があれば外す or 別の対処（`--permission-mode auto` 等）。

### 4.2 設定ファイルテンプレートの include パターン

`templates/.spec-grag/config.toml` の `include = ["docs/**/*.md"]` は汎用的すぎて `docs/SPEC-grag/core/` 配下（Purpose / Concept）も章ファイル群として拾う。利用者は `include = ["docs/spec/**/*.md"]` のように個別に絞る必要がある。

将来的に spec-grag CLI 側で `core_dir` 配下を自動 exclude する仕組みを入れる検討余地あり（ただし利用者の責任で OK という判断もアリ）。

### 4.3 graphrag-core の dead_code 警告 7 個

`graphrag-core/src/rograg/validator.rs` 等で `value never read` の警告。既存コードの問題で、本プロジェクトとは無関係。upstream への PR 提出は動作確認後に検討（DESIGN.md §8）。

### 4.4 spec-grag バイナリの dead_code 警告 5 個

config.rs の `ClaudeCliSection`、`CodexCliSection`、`Sources::exclude` 等のフィールドが現状未使用。実装が進めば（励起取得ロジック・Concept 差分提示の実装で）解消される。

### 4.5 cwd 維持

セッション中に `cd vendor/graphrag-rs/...` を実行すると、その後の Bash も同じ cwd で動く。`Shell cwd was reset to /home/kazuki/public_html/spec-grag` のメッセージが出るので、cd の影響範囲に注意。原則として絶対パスを使う。

### 4.6 ccusage 観測（参考）

前セッションで `npx ccusage@latest blocks` で Max (5x) プランの 5h ウィンドウ消費率を観測。設計議論メイン回でも 14% 程度だったので、subprocess 経由 `claude -p` 50-100 回 batch も枠内に収まる見込み。Sonnet 専用枠は今週ゼロ消費だったので、`--model sonnet` 指定なら Opus 対話と競合しない。

### 4.7 `complete_batch_concurrent` のデフォルト実装は並列化されていない

`AsyncLanguageModel::complete_batch_concurrent` の trait デフォルト実装は名前に反して直列実行（`for chunk in chunks { complete_batch(chunk).await }` で chunk ごとに sequential、`complete_batch` 内も sequential）。

smoke test 実測：sequential x5 = 19.8s、concurrent x5 = 20.6s（ほぼ同じ）。

優先 4（Concept 差分提示）のクラスタ要約で実用上必須になる。**§2.4（優先 3.5）として独立タスク化済み**。優先 4 着手前に潰すこと。

### 4.8 `claude -p` の cache creation トークン量

smoke test の応答 JSON で `cache_creation_input_tokens: 17592` を観測（CLAUDE.md auto-discovery + デフォルトシステムプロンプト含む）。5min TTL なので連続バッチでは 1 回目以降は cache hit になるが、5min 跨ぐと再 creation。

最適化案（必要になったら）：
- `--system-prompt ""` でシステムプロンプトを空にする
- `--add-dir /tmp/empty` 等で CLAUDE.md auto-discovery を抑制
- `--exclude-dynamic-system-prompt-sections` でクロスマシン cache reuse を改善

ただし subscription 利用なら tokens 課金されないので、レイテンシだけが問題。優先度は低い。

### 4.9 `AsyncGraphRAG::extract_entities_async` がダミー実装（優先 4 の地雷）

[vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs:222-245](vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs) はハードコードされた人名（`["tom", "huck", "polly", "sid", "mary", "jim"]`）に対する文字列マッチで Entity を作る Tom Sawyer デモコード。`build_graph()` がこれを呼ぶ。

優先 4 で `spec-grag core --all` から `build_graph()` を呼ぶと、章のエンティティが Tom Sawyer 化する。**差し替え必須**。

**方針決定（2026-04-26）**：

graphrag-rs には本物の `LLMEntityExtractor`（`entity/llm_extractor.rs`）が存在するが、`OllamaClient` を直接フィールドに保持する設計のため、そのままでは Ollama 専用。spec-grag では vendor 拡張で `AsyncLanguageModel` trait 経由に改造し、`ClaudeCliLanguageModel` を注入する（DESIGN.md §5 / §10 / §2.5(a) の前提条件）。

改造内容：
- `entity/llm_extractor.rs`：`OllamaClient` フィールド → `Arc<dyn AsyncLanguageModel<Error = GraphRAGError>>`
- `lib.rs:839 付近`：起動箇所を `AsyncLanguageModel` 注入パターンに変更
- `async_graphrag.rs::extract_entities_async`：本ダミーを改造版 LLMEntityExtractor 呼び出しに置換

これで章別キーアンカー作成も Claude Sonnet 経由（サブスク）になり、Ollama は埋め込み専用に純化される。

### 4.10 `AsyncGraphRAG::add_documents_batch` も sequential

[vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs:459](vendor/graphrag-rs/graphrag-core/src/async_graphrag.rs) のコメント：

```rust
// Process documents sequentially for now to avoid borrowing issues
// In a production implementation, you'd use channels or other concurrency patterns
for document in documents {
    self.add_document(document).await?;
}
```

upstream 自身が「sequential for now」と認めている。優先 4 で 100 件以上のドキュメントを feed する時に効く。§2.4（concurrent batch override）と並行して並列化する候補。

ただし `add_document` は内部で `&mut self` を要求し、`document_trees` と `knowledge_graph` の両方に書き込むので、単純な `join_all` では borrow checker が通らない。channel パターンか、`document_trees` を `Arc<RwLock>` のまま fine-grained lock で並列書き込みする工夫が必要。

### 4.11 Ollama 埋め込み統合が未実装（優先 4 必須）

DESIGN.md §5 では「埋め込み = Ollama nomic-embed-text、要約 = Claude CLI」と決まっているが、現状の `AsyncGraphRAGBuilder` は `language_model`（要約）の wiring しか実装されておらず、埋め込み経路が未着手。

graphrag-core 側の `embeddings/` モジュール（`OllamaEmbedder` 等）をどう注入するか調査が必要。[vendor/graphrag-rs/graphrag-core/src/ollama/](vendor/graphrag-rs/graphrag-core/src/ollama/) に `AsyncOllamaGenerator` はあるが、これは **生成 LLM** であって embedder ではない。embedder の trait と Ollama 実装の場所を `embeddings/` 配下で確認する必要あり。

優先 4 着手時の最初の調査項目。

### 4.12 ChangeDetector の手段が未確定（優先 4 サブタスク）

DESIGN.md §8 の表で

> 章ファイル群 → graphrag-rs への反映は spec-grag 側で別途仕組みを用意する（具体手段は未確定）

と既に明記されている。手段の候補：

| 手段 | メリット | デメリット |
|---|---|---|
| mtime 比較 | 実装最簡単 | 手動 touch で偽陽性、エディタの保存挙動に依存 |
| blob hash（SHA-256） | 確実 | 全文読み込み必要、計算コスト |
| git diff | 既にコミットがある前提なら最強 | 未 commit の変更を取り逃す、git 必須 |
| `Concept` の `sources_scanned_through` タイムスタンプ + mtime | DESIGN.md §7.3 と整合 | mtime と同様の弱点 |

DESIGN.md §7.3 では Concept frontmatter に `sources_scanned_through` を持たせる前提なので、**mtime + sources_scanned_through** が筋。優先 4 で確定。

### 4.13 スラッシュコマンドの実機発火検証が未実施（優先 3 残課題）

優先 3 で作成した 3 ファイルは frontmatter (YAML) のパース妥当性と CLI 単体動作までしか確認していない。**実機での発火検証は subprocess 環境からは不可能**なので、外側の Claude Code セッションで以下を確認する必要がある：

- `/spec-inject` 単独発火 → Purpose / Concept が KV に注入される
- `/spec-core` および `/spec-core --all` → 引数 `$ARGUMENTS` が `!`bash`` 内で展開されるか
- `/spec-realign "test"` → ① 〜 ⑨ のフローを LLM が踏むか、③ で `spec-grag realign --high --low` を Bash ツールで起動するか
- `/spec-realign` の ⑥ で `Task` ツール経由 subagent が起動するか

**特に未確認の挙動**：`!`bash`` インライン実行内での `$ARGUMENTS` 展開挙動。展開されない場合は `spec-core.md` を「LLM が Bash ツールで `spec-grag core $ARGUMENTS` を実行する」形式に書き換える必要がある。

### 4.14 ⑥ 波及検査の「メイン LLM の KV を汚染しない」運用は subagent 経由必須

DESIGN.md §7.1 ⑥ では「graphrag-rs に外注、メイン LLM の KV を直接汚染しない」が設計要件。しかし spec-grag CLI 単独では実現不可能（Bash 出力は必ずメイン LLM の stdout を経由するので KV に流入する）。

`spec-realign.md` ではプロンプトで「`Task` ツール経由 subagent に投げて要約だけ受け取る」よう誘導しているが、ユーザー判断で直接 Bash を呼ぶケースが起こり得る。これは利便性 vs 設計純度の trade-off。

将来的な対応案：
- spec-grag に「励起のみ実行、結果を一時ファイルに書く」モードを追加（`spec-grag excite --output /tmp/excitation.json`）
- subagent から一時ファイルを読み、サマリだけメインに返す形にすれば、KV 汚染を確実に避けられる
- 優先 5 の監査役 subagent 実装と合わせて検討

### 4.15 監査役 subagent の `subagent_type` 名が未確定

[spec-realign.md](templates/.claude/commands/spec-realign.md) の ⑧ で `Task` ツール起動時の `subagent_type` 名は **placeholder** になっている。優先 5 で `.claude/agents/` に監査役 subagent を実装した時点で、確定した名前で書き換える必要がある。

優先 5 完了時のチェックリスト：
- [ ] `subagent_type` 名を spec-realign.md ⑧ に反映
- [ ] 暫定の「`general-purpose` で代替」記述を削除
- [ ] 監査役 subagent の入出力フォーマットがプロンプトの記述と一致しているか確認

### 4.16 ⑥ で `spec-grag realign` を 2 回呼ぶと冗長

DESIGN.md §7.1 ③ と ⑥ の両方で `spec-grag realign --high --low` が呼ばれる設計。現状の `spec-grag realign` は内部で `inject` を自動的に呼ぶため、⑥ で再実行すると Purpose / Concept がもう一度 stdout に出る。

対策案：
- `spec-grag realign --no-inject` フラグを追加して、励起だけ実行する
- もしくは励起だけの専用サブコマンド `spec-grag excite` を新設する
- 後者の方が責務分離として明快（§4.14 と組み合わせて `--output` も付与する）

優先 4 着手時に検討。

### 4.17 smoke test に並列性アサーション無し

[examples/claude_cli_smoke.rs](vendor/graphrag-rs/graphrag-core/examples/claude_cli_smoke.rs) は `println!` で実行時間を出すだけで、「並列化が効いているか」を機械的に検証していない。優先 3.5 で `complete_batch_concurrent` を override した時、回帰検出のために以下のような assertion が欲しい：

```rust
assert!(
    elapsed_par < elapsed_seq * Duration::from_millis(600).as_secs_f32() / 1000.0,
    "concurrent x5 should be at least 40% faster than sequential x5"
);
```

優先 3.5 のサブタスク（並列化と同時に実装）。

---

## 5. 次セッション開始時の最初の手順

1. 本 HANDOFF.md を読む（`Read /home/kazuki/public_html/spec-grag/HANDOFF.md`）
2. [doc/DESIGN.md](doc/DESIGN.md) を読む（必要なセクションのみ）
3. 残り作業（§2）から次の項目を選んで開始
   - **優先 3（スラッシュコマンド）**：プロンプト書きで小〜中規模、LLM call なしで完結
   - **優先 3.5（concurrent batch override）**：優先 4 の前提。30 分〜1 時間程度
   - **優先 4（Concept 差分提示／グラフ構築）**：優先 3.5 を先に済ませてから着手。Ollama 埋め込み統合 + クラスタ要約の wiring が必要。完了時に優先 2 の励起が end-to-end で動くようになる
4. 完了したら次の優先項目へ。各項目の完了時に HANDOFF.md を更新（または完了済みを §1 に移動）

新セッションでこの引き継ぎ + DESIGN.md があれば、設計議論を再現する必要なく実装に集中できる。
