# P1-E1: spec-anchor-setup-system 正常系

## 実行日時
2026-05-23 JST

## 実行環境
- spec-anchor: 0.1.0
- Qdrant: 1.17.1 (http://localhost:6333)
- FlagEmbedding: 1.4.0
- codex: 0.125.0 / claude: 2.1.147

## 実行コマンドと結果

### (1) 正常系: production_readiness.status="ready"
```bash
$ .venv/bin/spec-anchor-setup-system --qdrant-url http://localhost:6333
```
- exit code: 0
- `production_readiness.status`: `"ready"`
- `production_readiness.blocking_reasons`: `[]`
- checks: qdrant_service / flagembedding_package / qdrant_client_package / agent_cli / 5 console_scripts すべて `"passed"`

### (2) --check-only は書き込まない
```bash
$ md5sum docs/spec/sample.md docs/core/purpose.md docs/core/concept.md  # before
6cbb02df7bb94a91a7a80a67d7886054  docs/spec/sample.md
65b23a6dfd1f402177912d45ce2066da  docs/core/purpose.md
268b7364c7cdb86137628ffc1e8a5fcf  docs/core/concept.md

$ .venv/bin/spec-anchor-setup-system --check-only --qdrant-url http://localhost:6333
# check_only: true が確認、actions に reason: "check_only" status: "skipped"

$ md5sum docs/spec/sample.md docs/core/purpose.md docs/core/concept.md  # after (同一)
6cbb02df7bb94a91a7a80a67d7886054  docs/spec/sample.md
65b23a6dfd1f402177912d45ce2066da  docs/core/purpose.md
268b7364c7cdb86137628ffc1e8a5fcf  docs/core/concept.md
```
- exit code: 0、md5sum 変化なし

### (3) --run-smoke で agent_cli_entries が出る
```bash
$ .venv/bin/spec-anchor-setup-system --run-smoke --qdrant-url http://localhost:6333
agent_cli_entries: ['claude', 'codex']
status: ready
```
- exit code: 0、`agent_cli_entries` に `claude` / `codex` が存在

## 判定
**PASS — 全5項目**

| 確認項目 | 結果 |
|---|---|
| production_readiness.status="ready" | PASS |
| exit code 0 | PASS |
| --check-only は書き込まない | PASS（md5sum 一致） |
| --run-smoke で agent_cli_entries が出る | PASS |
| Source Specs / Purpose / Core Concept を変更しない | PASS（md5sum 一致） |

## 対応する EXTERNAL_DESIGN の検証単位
§6.2.1 System Setup Script 内の [ ] 行（status=ready / exit_code / check_only / run_smoke / ファイル不変）
