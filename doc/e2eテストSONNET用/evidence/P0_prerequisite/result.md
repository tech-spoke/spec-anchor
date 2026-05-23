# P0: 前提確認

## 実行日時
2026-05-23 JST

## 実行環境
- spec-anchor バージョン: 0.1.0
- Qdrant: healthz check passed (http://localhost:6333)
- codex バージョン: codex-cli 0.125.0
- claude バージョン: 2.1.147 (Claude Code)
- FlagEmbedding: BGEM3FlagModel import OK
- Python: .venv/bin/python

## 実行コマンドと結果

```bash
$ .venv/bin/spec-anchor --version
spec-anchor 0.1.0
exit: 0

$ curl -s http://localhost:6333/healthz
healthz check passed
exit: 0

$ codex --version
codex-cli 0.125.0
exit: 0

$ claude --version
2.1.147 (Claude Code)
exit: 0

$ .venv/bin/python -c "from FlagEmbedding import BGEM3FlagModel; print('ok')"
ok
exit: 0

$ ls docs/spec/sample.md docs/core/purpose.md docs/core/concept.md
docs/core/concept.md
docs/core/purpose.md
docs/spec/sample.md
exit: 0
```

## 判定
**PASS — 全6項目**

| 項目 | 結果 |
|---|---|
| spec-anchor CLI が PATH 上にある | PASS (0.1.0) |
| Qdrant が起動している | PASS (healthz check passed) |
| codex CLI が PATH 上にある | PASS (0.125.0) |
| claude CLI が PATH 上にある | PASS (2.1.147) |
| FlagEmbedding が import できる | PASS |
| テスト用 Source Specs が存在する | PASS (3ファイル確認) |
