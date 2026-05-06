# SPEC-grag Phase 9 実行報告

> 作成日: 2026-05-01
> 対象: Phase 9 production 実行経路化 / smoke fallback 主経路からの撤去

## 1. 結論

Phase 9 の実装側は完了。production policy gate、repo-local production config 切替、実 provider 小型 production probe まで確認済み。

通常 `.spec-grag/config.toml` は production 品質として扱い、`stable_hash`、`template` answer、`orchestrator_rule_based` classification、`source_derived` Concept diff、deterministic-only extraction、silent fallback を通常実行経路から禁止した。

smoke は config profile ではなく、`SPEC_GRAG_SMOKE=1`、`SPEC_GRAG_RUNTIME_MODE=smoke`、`scripts/setup_project.py --smoke`、`scripts/ci-smoke.sh` のような明示経路に限定した。

ただし、`テスト用ドキュメント/**/*.md` 全体を対象にした repo-local 大規模 production full 評価は token 消費が大きいため残件である。

## 2. 実装結果

### production policy

- `spec_grag/config.py` に `ConfigPolicyError` と `smoke_mode_enabled()` を追加した
- `validate_project_config()` は通常時に production policy を強制し、smoke 明示時だけ fallback config を許可する
- production では次を禁止する
  - `[llm]` が未設定
  - `[llm].provider` が `codex_cli` / `claude_cli` 以外
  - 選択した `[llm.<provider>]` table または `model` が未設定
  - `extraction.mode != "schema_llm"`
  - `core.extraction_mode = "deterministic"`
  - `embedding.provider = "stable_hash"`
  - `answer.provider` が `codex` / `claude` 以外
  - `answer.failure_fallback = "template"`
  - `classification.provider` が `codex` / `claude` 以外
  - `classification.fallback_on_error = true`
  - `concept_diff.provider` が `codex` / `claude` 以外
  - `concept_diff.fallback_on_error = true`
  - `query_planner.provider` が `codex` / `claude` 以外
  - `query_planner.fallback_on_error = true`

### fail-fast

- Classification LLM failure は `fallback_on_error=false` では `ClassificationError` として fail-fast する
- Classification LLM path では、fallback 無効時に `is_target_query()` / `query_tokens()` / `token_match_score()` の固定語彙判定を先に混ぜない
- Query planner は `fallback_on_error=false` で template planner に戻らず例外を上げる既存実装を production policy と接続した
- Concept diff LLM proposal failure は `ConceptDiffProposalError` として fail-fast する
- embedding provider unavailable / dimension mismatch は `/spec-core` の `failed` として返し、`embedding_provider_failed:*` warning に残す
- `/spec-inject` / `/spec-realign` の context build 中に production provider が失敗した場合、CLI は `context_build_failed` の `ErrorResult` を返す

### retrieval / Concept index の production 寄せ

- Concept index retrieval は production 経路で `stable_embedding(query)` と token substring scoring に依存せず、index metadata に従って query embedding を作る
- cluster の query text fallback は smoke mode だけで許可し、production は raw chunk hit / graph proximity / concept / anchor 接続に限定した

### setup / tests / self project config

- `templates/.spec-grag/config.toml` は production 向け設定として validation される
- `scripts/setup_project.py --smoke` は smoke config として validation される
- `scripts/ci-smoke.sh` は `SPEC_GRAG_SMOKE=1` を明示する
- `[llm].provider = "codex_cli" | "claude_cli"` を project-level の生成系 LLM 切替契約にし、extraction / classification / answer / concept diff / query planner は選択 provider の `command` / `model` / `effort` を継承する
- 既存 E2E smoke tests は `SPEC_GRAG_SMOKE=1` を明示し、production policy test と分離した
- run artifact に `runtime_mode` と provider summary を残す
- run artifact に `fallback_events`、`degraded_components`、`retrieval_summary` を残す
- repo root の `.spec-grag/config.toml` を production policy を通る self project 設定へ切り替えた
- 旧 smoke 設定は `.spec-grag/config.smoke.toml` に退避した
- repo root / active template / wheel package template の config は stage 個別の LLM provider 指定を持たず、`[llm]` の変更だけで Codex / Claude を切り替える
- Codex model は Codex CLI catalog の `gpt-5.4`、Claude model は full Claude Code model name `claude-sonnet-4-6` を default とする
- 現環境へ Ollama `bge-m3` を導入し、repo-local production config は `bge-m3` / `dimension = 1024` を使う

### package resource

- active `templates/` を `spec_grag/templates/**` package data として同梱した
- `spec_grag/template_resources.py` から wheel / pip install 後も template root を取り出せる
- `spec-grag-setup-project` console script を追加し、wheel install 後の project setup 導線を作った

### semantic conflict candidate

- LLM classification が `semantic_conflict_candidate=true` を返しても、それだけでは `conflict=true` に昇格しない
- Validator の hard rule が成立しない候補は ReviewNotes / human approval 待ちに落とす regression を追加した
- 日本語仕様文の権限範囲、状態遷移、数量条件、数量詞 conflict の regression fixture を追加した

### community report / cluster

- `label_propagation_v1` による community cluster を追加した
- community report を LLM 生成できるようにし、source evidence、covered chunks、staleness、confidence を保持する
- retrieval では raw chunk hit / graph expansion / community report を扱い、production では cluster text fallback を使わない

### Codex CLI production guard

- Codex CLI subprocess では `plugins` と `general_analytics` を無効化し、featured plugin / analytics の 403 で provider call が落ちないようにした
- user global config の `model_reasoning_effort = "xhigh"` を引きずらないよう、structured phase の既定を `[llm.codex_cli].effort = "low"` にした。Codex は `codex exec --config model_reasoning_effort="<effort>"`、Claude は `claude --effort <effort>` に渡す
- Codex/OpenAI structured output 互換のため、LLM output schema は object properties を required に揃える regression を追加した
- production token guard として `classification.max_items` の既定を 8 にし、budget exhaustion は provider failure ではなく policy skip として rule-based に戻す

## 3. 検証結果

Phase 9 related regression:

```text
uv run --isolated --with pytest --with pydantic --with llama-index-core --with markdown-it-py pytest tests/test_phase7_packaging.py tests/test_cli.py tests/test_phase9_production_policy.py tests/test_injection_realign.py -q
50 passed in 70.70s (0:01:10)
```

Full regression after real-provider hardening:

```text
uv run --isolated --with pytest --with pydantic --with llama-index-core --with llama-index-readers-file --with llama-index-embeddings-ollama --with markdown-it-py --with jsonschema pytest tests -q
155 passed in 89.94s (0:01:29)
```

実 provider 小型 production probe:

```text
spec-core --all: 4 turns / total 56,425 tokens / degraded（pending Concept diff 作成）
spec-core incremental no-change: 1 turn / total 12,330 tokens / ok
spec-inject max_items=8: 10 turns / total 116,520 tokens / ok
spec-realign max_items=8: 11 turns / total 137,724 tokens / blocked NeedMoreContext
```

CI smoke:

```text
scripts/ci-smoke.sh
142 passed in 119.87s (0:01:59)
{"status": "ok", "updated_sources": 12}
{"command": "spec-core", "status": "ok"}
{"command": "spec-inject", "status": "ok"}
{"command": "spec-realign", "status": "ok"}
```

wheel package data probe:

```text
uv build --wheel --out-dir /tmp/spec-grag-wheel-check
spec_grag/templates/.codex/commands/spec-core.md
spec_grag/templates/.codex/commands/spec-inject.md
spec_grag/templates/.codex/commands/spec-realign.md
spec_grag/templates/.spec-grag/.gitignore
spec_grag/templates/.spec-grag/README.md
spec_grag/templates/.spec-grag/config.toml
```

ローカル provider 状態:

```text
codex-cli 0.125.0
codex login status: Logged in using ChatGPT
ollama list: bge-m3:latest, nomic-embed-text:latest
```

repo-local production config / smoke config / `bge-m3` probe:

```text
prod_runtime production
prod_embedding ollama bge-m3 1024
smoke_runtime smoke
smoke_embedding stable_hash sha256-v1 8
ollama_probe_dimension 1024
```

## 4. smoke 明示モードと production 実行経路

production は通常の config validation で強制される。開発者 PC で動かす場合も production とし、実行場所の違いは provider 設定で表現する。

smoke は以下の明示経路だけで許可する。

- `SPEC_GRAG_SMOKE=1`
- `SPEC_GRAG_RUNTIME_MODE=smoke`
- `scripts/setup_project.py --smoke`
- `scripts/ci-smoke.sh`
- smoke 専用 test fixture

smoke は command wiring / fresh install / no-deps CI の確認用であり、GraphRAG 品質評価には使わない。

## 5. 残リスク

### 実 provider 大規模評価は未実施

policy と fail-fast は入り、repo root の `.spec-grag/config.toml` も production policy を通る `bge-m3` / `dimension = 1024` 設定に切り替えた。小型一時 project の実 provider probe は通過した。ただし、`テスト用ドキュメント/**/*.md` 全体を production config、Codex extraction / classification / answer / concept diff、Ollama embedding で通す評価は未実施である。

既存 `.spec-grag/graph/` 生成物は過去 smoke の `stable_hash` metadata を持つ。これは source config ではなく generated artifact の状態であり、production self project 評価では `spec-core --all` rebuild が必要である。

### plain pytest は標準 runner ではない

依存が入っていない素の Python 環境では `pytest` が import 依存で失敗し得る。現時点の標準 runner は `uv run --isolated --with pytest --with pydantic --with llama-index-core --with markdown-it-py pytest -q` とする。

## 6. 次作業

- repo-local `テスト用ドキュメント/**/*.md` の production full run を、token 予算を確認してから実施する
- production provider を使った self project 評価で fallback が発動しないことを artifact で確認する
- `spec-inject` の LLM classification は現在 max_items cap で抑制しているため、必要なら batch classification 化して token をさらに削減する
