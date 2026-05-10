# SPEC-grag 運用・開発ガイド

> 位置づけ: SPEC-grag の運用手順、テスト手順、本運用 Readiness、トラブルシュート、プライバシー設定をまとめた参照文書。README から分離した内容を含む。

## 1. Retrieval Stack

標準 retrieval stack は次のとおり。

- Qdrant vector store
- FlagEmbedding BGE-M3 (`BAAI/bge-m3`) の dense / sparse vector
- dense search + sparse search + RRF fusion

Ollama は標準の sparse-vector 経路ではない。本運用では `.spec-grag/config.toml` が指定する Qdrant、FlagEmbedding、Codex / Claude CLI を通常経路で使う。本運用前には Readiness check（§4）で依存関係の導入状態を確認する。

## 2. Freshness と Conflict

`/spec-inject` と `/spec-realign` は、通常の制約生成・回答生成へ進む前に freshness gate を通す必要がある。以下のいずれかの場合は黙って続行せず停止する。

- Source Specs が dirty / stale
- watcher が実行中または queue 待ちにある
- config / schema が stale
- 必須 artifact が failed
- pending conflict が残っている

dirty / stale 状態と pending conflict が同時にあるときは、まず `/spec-core` または watcher で更新する。更新後にも残った pending conflict だけを人間判断対象とする。resolved だが未反映の Conflict Review Item は、記録された source hash と valid scope が依然有効である間に限り、一時的な人間判断として参照できる。

freshness status の詳細は `doc/EXTERNAL_DESIGN.ja.md` §6.2 を参照。

## 3. Agent 入口の詳細

プロジェクトセットアップは、次の Agent 別入口を配置する。

- `~/.codex/skills/spec-grag/SKILL.md` — Codex の user install。既定 `--codex-install user` で選択
- `<project>/.codex/skills/spec-grag/SKILL.md` — Codex の project ローカル install。`--codex-install project` で選択
- `<project>/.claude/commands/spec-core.md`
- `<project>/.claude/commands/spec-inject.md`
- `<project>/.claude/commands/spec-realign.md`

Codex CLI は `<project>/.codex/commands/` を公式に認識しないため、このパスへの command 形式は配置しない。

これらの入口は、同じ SPEC-grag CLI 契約を Agent 環境ごとの形式に合わせて適用するものである。仕様の唯一の根拠ではない。外部設計と CLI I/O 契約が正本である。

`spec-grag inject` と `spec-grag realign` は、Agent / LLM が今回の課題に必要な制約（および realign では回答候補）を渡すことを前提にする。通常運用では、配置された Codex skill または Claude command template が、その手順を Agent に指示する。

## 4. テストと smoke

### 4.1 ローカル開発

ローカル開発の test を実行する:

```bash
python3 -m pytest
```

組み込みのローカル smoke を明示的に実行する:

```bash
spec-grag-setup-system --check-only --run-smoke
```

### 4.2 外部依存を含む pytest

通常の pytest は、実 Agent CLI、FlagEmbedding BGE-M3、Qdrant service など外部依存を使う test も実行対象にする。外部依存が無い環境では該当 test は失敗する。

```bash
python3 -m pytest
```

Qdrant の接続先を test / probe 用に差し替える場合だけ、`SPEC_GRAG_QDRANT_URL` を使う。

### 4.3 外部依存 test を除外する軽量確認

Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 が無い環境で、外部依存なしの範囲だけ確認する場合は次を使う。

```bash
python3 -m pytest --skip-external
```

この実行で skip された test は未実行であり、実 Qdrant / BGE-M3 / real provider / Agent CLI の実動作完了の根拠にしない。

### 4.4 pytest 実行範囲

| 実行方法 | 意味 | 報告での扱い |
|---|---|---|
| `python3 -m pytest` | 外部依存 test も実行対象にする | 外部依存 test が passing した場合だけ実動作検証の証跡にできる |
| `python3 -m pytest --skip-external` | 外部依存 test を skip する | skip された test は未実行として報告する |

`pytest --skip-external` は pytest の実行範囲を狭めるための指定であり、本運用の通常 CLI が fake provider や memory retrieval を使うという意味ではない。

## 5. 本運用 Readiness

本運用 Readiness は smoke testing とは別の概念である。smoke test は選ばれた real 経路が動くことを示す。本運用 Readiness は、通常の利用者が永続 Qdrant service、BGE-M3、認証済み Agent CLI で SPEC-grag を継続稼働できることを示す。

### 5.1 インストール（retrieval 依存を含む）

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[retrieval,test]'
```

### 5.2 Qdrant の起動

Qdrant を Docker ではなく native service / managed process として起動する。ローカル例:

```bash
export QDRANT__SERVICE__HTTP_PORT=6333
export QDRANT__SERVICE__GRPC_PORT=6334
export QDRANT__STORAGE__STORAGE_PATH=/var/lib/spec-grag/qdrant
qdrant --disable-telemetry
```

### 5.3 本運用実行条件

本運用では、生成 config の `codex_cli` / `claude_cli`、FlagEmbedding BGE-M3、Qdrant を既定で使う。`SPEC_GRAG_REAL_PROVIDER` / `SPEC_GRAG_REAL_RETRIEVAL` は不要である。

Qdrant 接続先は project 設定である。通常運用では `.spec-grag/config.toml` の `[vector_store].url` を正とし、環境変数ではなく設定ファイルで管理する。`SPEC_GRAG_QDRANT_URL` は smoke / test / system readiness probe の接続先差し替え用に限る。

### 5.4 導入状態と Readiness の確認

```bash
spec-grag-setup-system --check-only --qdrant-url http://localhost:6333
```

JSON 結果には `production_readiness` が含まれる。ready 状態では、指定した Qdrant probe 先、FlagEmbedding、qdrant-client、いずれかの Agent CLI、console script が利用可能である。不足要素は `qdrant_service_unavailable`、`flagembedding_missing`、`agent_cli_unavailable` などの blocking reason code として返る。

### 5.5 通常 CLI 経路の実行

プロジェクトを作成または更新し、通常 CLI 経路を実行する:

```bash
spec-grag-setup-project --target /path/to/project --agent both --codex-install project
cd /path/to/project
spec-grag core --all
spec-grag inject "task prompt" --constraints-file constraints.json
spec-grag realign "task prompt" --constraints-file constraints.json --answer-file answer.json
spec-grag-watch . --interval-sec 2 --debounce-sec 1
```

### 5.6 Qdrant の再起動と永続性検証

Qdrant の再起動は、native service / process を停止し、同じ `QDRANT__STORAGE__STORAGE_PATH` で再開する。`spec-grag core` を再実行し、`.spec-grag/context/retrieval_index_revision.json` で同じ Qdrant URL、collection、schema version、server version、BGE-M3 model、dense / sparse named vector、RRF diagnostics が保持されているか確認することで永続性を検証する。

### 5.7 トラブルシュート

diagnostics から確認する:

- `real_provider_disabled`: test が明示的に real provider を無効化した場合の診断である。本運用では `codex` または `claude` が利用可能で認証済みであることを確認する。
- `agent_cli_unauthenticated`: project ローカル環境の外で subscription CLI を認証し、コマンドを再実行する。
- `real_retrieval_index=false`: `.spec-grag/config.toml` が Qdrant / FlagEmbedding BGE-M3 ではなく fake / memory profile を指していないか、Qdrant が到達可能かを確認する。
- `qdrant_service_unavailable`: native Qdrant service を起動または再起動し、`.spec-grag/config.toml` の `[vector_store].url` または `spec-grag-setup-system --qdrant-url` の probe 先を確認する。
- `qdrant_schema_mismatch`: SPEC-grag が要求する `dense` / `sparse` named vector を持つよう Qdrant collection を再作成または migrate する。
- `flagembedding_missing` または `embedding_model_load_failure`: retrieval extra をインストールし、`HF_HOME`、`HF_HUB_CACHE`、`~/.cache/huggingface` のいずれかで BGE-M3 model cache を確認する。
- `provider_timeout` または `timeout`: 設定済みの timeout を増やす、または ブロックされた Agent CLI / model process を解消してから再試行する。
- `failed_required_artifact`: `.spec-grag/context/freshness.json` を確認し、不足する provider / service を解消した上で `spec-grag core --all` を再実行する。

### 5.8 本運用 Readiness 報告テンプレート

本運用 Readiness の作業を報告するときは、次のセクション名をそのまま使い、smoke / default passing と real-service passing を分けて記載する。

- 実装済み
- `none` / `fake` profile で passing
- `local-service` / `real-smoke` で passing
- skipped / 未実行
- 残 TODO
- 証跡

G-18 または T-R11〜T-R15 のいずれかの行が `[ ]` の間は「本運用可能」と報告しない。

## 6. Diagnostics プライバシー

既定では、run artifact に LLM request prompt 本文、LLM response 本文、Source Specs 全文は保存しない。diagnostics には provider identity、timing、count、reason code、retrieval ranking 概要、fusion method、embedding model、Qdrant collection metadata を保存しうる。既定 template は次の値を保つ。

```toml
[run]
save_artifacts = false
include_request = false
include_response = false
redact_payload = true
```
