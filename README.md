# SPEC-grag

LLM は、目の前のファイルや直近の会話に強く注意を向ける。背景知識や上位目的の収集が足りないまま進むと、局所的な内容に引っ張られ、設計意図からずれた回答や修正を出しやすい。

SPEC-grag is a lightweight specification context tool. SPEC-grag は、LLM が作業中に次を見失わないよう支援する軽量な仕様コンテキストツールである。

- 本来の目的（Purpose）
- 承認済みの設計原則（Core Concept）
- 現在の課題に関係する仕様本文（Source Specs）
- section ごとの要約・検索入口・関連先
- 仕様間の矛盾（Conflict Review Item）

Purpose と Core Concept は人間が維持する。SPEC-grag does not update them automatically.

標準経路は軽量版の設計であり、property graph、entity relation graph、hierarchical cluster、無制限 graph traversal は使わない。These are not part of the standard path; the lightweight path does not use them as the standard retrieval stack.

## 前提となる技術スタック

| 要素 | 標準構成 |
|---|---|
| Vector Store | Qdrant |
| Embedding | FlagEmbedding BGE-M3 (`BAAI/bge-m3`) — dense + sparse |
| Fusion | dense search + sparse search + RRF |
| LLM (Agent 側) | Codex CLI / Claude Code CLI（外部の Agent 環境が担当） |
| LLM (`/spec-core` 用) | `.spec-grag/config.toml` の `[llm]` で設定。Agent 側 LLM とは別 |

Ollama は標準の sparse-vector 経路ではない。

## 環境構築

### 1. SPEC-grag 本体と retrieval 依存のインストール

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -e '.[retrieval]'
```

`.[retrieval]` で FlagEmbedding (BGE-M3) と qdrant-client が導入される。テスト用依存も入れる場合は `.[retrieval,test]`。

### 2. Qdrant のインストールと起動

Qdrant は Python パッケージではなく、別途 native binary が必要。

```bash
# Linux: GitHub releases から取得して $PATH に配置
curl -L https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-gnu.tar.gz | tar xz
mv qdrant ~/.local/bin/
```

macOS の場合は `brew install qdrant/tap/qdrant` または GitHub releases から対応 binary を取得する。

#### 2.1 systemd ユーザーサービスとして常駐させる (Linux 推奨)

`spec-grag core` / `/spec-inject` / `/spec-realign` が Qdrant に依存するため、log-in セッションで自動起動・自動再起動するように systemd ユーザーサービス化するのが扱いやすい。手動 `qdrant --disable-telemetry` を毎回起動するより事故が少ない。

```bash
# 永続化される storage / runtime ディレクトリを先に作る
mkdir -p ~/.local/share/spec-grag/qdrant/storage ~/.local/share/spec-grag/qdrant/runtime

# ユーザーサービス unit を作成
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/qdrant.service <<'UNIT'
[Unit]
Description=Qdrant Vector Database (for spec-grag)
Documentation=https://qdrant.tech/documentation/
After=default.target

[Service]
Type=simple
Environment=QDRANT__SERVICE__HTTP_PORT=6333
Environment=QDRANT__SERVICE__GRPC_PORT=6334
Environment=QDRANT__STORAGE__STORAGE_PATH=%h/.local/share/spec-grag/qdrant/storage
ExecStartPre=/bin/mkdir -p %h/.local/share/spec-grag/qdrant/storage %h/.local/share/spec-grag/qdrant/runtime
WorkingDirectory=%h/.local/share/spec-grag/qdrant/runtime
ExecStart=%h/.local/bin/qdrant --disable-telemetry
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT

# 反映 + 自動起動有効化 + 起動
systemctl --user daemon-reload
systemctl --user enable --now qdrant.service

# ログイン無しでも起動するようにする (任意、サーバー / 常時起動の WSL 等)
loginctl enable-linger "$USER"
```

確認:

```bash
systemctl --user status qdrant       # active (running)
curl -s http://localhost:6333/readyz  # all shards are ready
curl -s http://localhost:6333/collections  # {"result":{"collections":[...]}, "status":"ok", ...}
```

注意: `WorkingDirectory` は systemd が ExecStartPre より前にチェックするため、初回だけ手動 `mkdir -p` が必須 (上記 1 行目)。スクリプト化する際は `loginctl enable-linger` を必須ステップに含めると、再起動後の auto start が確実になる (lingering 無効だと WSL の cold-start などで service が立ち上がらない)。

WSL の場合: `/etc/wsl.conf` に `[boot]\nsystemd=true` が無いとユーザーサービスが使えない。先に `wsl --shutdown` してから設定を反映する。

#### 2.2 手動起動でとりあえず動かす場合

systemd を使えない環境では、ターミナルで直接起動する。

```bash
mkdir -p ~/.local/share/spec-grag/qdrant/storage
QDRANT__SERVICE__HTTP_PORT=6333 \
QDRANT__STORAGE__STORAGE_PATH=~/.local/share/spec-grag/qdrant/storage \
qdrant --disable-telemetry
```

シェルを閉じると停止するので、開発作業の最初に立ち上げて維持する運用になる。systemd を使える環境では §2.1 の常駐化を推奨する。

### 3. 導入状態の確認

```bash
spec-grag --help
spec-grag-setup-system --check-only
```

`spec-grag-setup-system --check-only` の出力で、Qdrant / FlagEmbedding / Agent CLI の導入状態と不足要素を確認できる。

## プロジェクトへの導入

```bash
# 対象プロジェクトにセットアップ（Claude Code + Codex 両対応）
spec-grag-setup-project --target /path/to/project --agent both

# コンテキスト artifact を初回生成
cd /path/to/project
# 必要に応じて .spec-grag/config.toml の [vector_store].url を実 Qdrant URL にする
spec-grag core --all
```

`--agent both` は次の入口を配置する:

- Claude Code 用: `<project>/.claude/commands/spec-{core,inject,realign}.md`
- Codex 用: `~/.codex/skills/spec-grag/SKILL.md`（user install、既定）

Codex skill を project に閉じたい場合は `--codex-install project` を追加する（Codex CLI の version によって project local skill を認識しない場合がある）。Claude Code のみ / Codex のみ使う場合は `--agent claude` / `--agent codex` で絞れる。

セットアップ後、Agent 環境に配置された入口（Claude Code の `/spec-core`、Codex の spec-grag skill）から利用できる。

`--no-init-core-files` を指定すると Purpose / Core Concept 雛形を作らない（後で人間が作成するまで `/spec-core` は失敗する）。`--dry-run` で作成予定の確認、`--force` で既存管理ファイルの上書きができる。Codex user install の既存 skill を更新する場合も `--force` が必要である。

### LLM 並列度のチューニング

`/spec-core --all` の section_metadata / related_sections 生成は batch ごとに LLM を呼ぶ。`.spec-grag/config.toml` の `[limits].llm_batch_concurrency` で同時実行数を指定できる:

```toml
[limits]
llm_batch_concurrency = 1   # default、逐次
# llm_batch_concurrency = 4   # Codex Pro 5x / Claude Max 5x 推奨
# llm_batch_concurrency = 8   # 上記サブスクで wall time をさらに短縮
```

サブスクごとの目安:

| サブスク | 5h window あたり message budget | 推奨 `llm_batch_concurrency` | 備考 |
|---|---|---|---|
| Codex Plus ($20) | 15-80 | 1 | quota 超過で実質回せない、Pro 以上を推奨 |
| Codex Pro 5x ($100) | 80-400 | 4 | 418 section 規模 (~106 messages/run) で 1 日 3-4 回程度 |
| Codex Pro 20x ($200) | 320-1600 | 8 | 上限近くまで余裕 |
| Claude Pro ($20) | 非公開 (TPM/RPM 単位制限) | 1-2 | TPM が支配的 |
| Claude Max 5x ($100) | 非公開 (5x スケール) | 4 | Pro 5x と同等扱い |
| Claude Max 20x ($200) | 非公開 (20x スケール) | 8 | 上限近くまで余裕 |

実測上、claude / codex の両 CLI は 16 並列まで API 側で reject されないが、5h window quota を考慮すると上記が安全側の運用値になる。並列度を上げるとサブスク budget の消費速度が直線的に増える点に注意。

## コマンド一覧

| コマンド | 目的 |
|---|---|
| `spec-grag core [--all] [--use-cache]` | Section Summary、Search Keys、Related Sections、Chapter Key Anchor、Retrieval Index、Conflict Review Item を生成・更新する。`--all` は完全再生成で、section metadata cache を読まない。`--all --use-cache` を指定した場合だけ同一 cache key の section metadata cache を再利用してよい。Conflict Review Item の人間判断は Agent が構造化して `/spec-core` に渡す（人間が JSON を直接編集する運用ではない） |
| `spec-grag inject "<課題>"` | Agent が生成した制約を検証し、注入用のコンテキストを返す。回答は生成しない |
| `spec-grag realign "<課題>"` | 制約を検証した上で、Agent が生成した回答候補を構造化して返す |
| `spec-grag-watch [project_root] [--once]` | Source Specs の変更を監視し、background で incremental update を行う |
| `spec-grag-setup-project --target <path>` | 対象プロジェクトに `.spec-grag/config.toml`、Agent 入口、Purpose / Core Concept 雛形を配置する |
| `spec-grag-setup-system --check-only` | SPEC-grag 本体の導入状態と外部依存を確認する |

各コマンドの詳細は `--help` で確認できる。

## 責務境界

| 役割 | 担当 |
|---|---|
| Human | Purpose と Core Concept の維持、Conflict Review Item の判断、最終仕様判断 |
| Agent / LLM | 課題と会話の解釈、検索キー生成、Agentic Search、制約生成、回答生成 |
| CLI / SPEC-grag | 設定読込、section hash / freshness 管理、保持物生成、検索 API、参照 API。探索方針や最終回答は決めない |

CLI は探索や回答の主体にならない。Agent / LLM が CLI の提供する検索結果と保持物を使って判断する。

## Agent 入口

`spec-grag-setup-project` は Agent 環境ごとに対応する形式の入口を配置する。

| Agent 環境 | 形式 | 配置先 |
|---|---|---|
| Claude Code | command | `<project>/.claude/commands/spec-{core,inject,realign}.md` |
| Codex CLI | skill | `<project>/.codex/skills/spec-grag/SKILL.md` |

Codex CLI は `.codex/commands/` を認識しないため、command 形式は Claude Code 専用である。

## 設計文書

| 文書 | 内容 |
|---|---|
| `doc/EXTERNAL_DESIGN.ja.md` | 外部契約の正本。コマンド体系、freshness、section 化、承認境界 |

## Archive

`archive/full-grag-2026-05-05/` は旧 full GRAG 版の歴史的参照資料である。現在の正本ではない。
