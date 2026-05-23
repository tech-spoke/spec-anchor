# P2-F3: Agent CLI 不在状態のエラーハンドリング

## 実行日時
2026-05-23 JST

## 手順
NVM 配下（`/home/kazuki/.nvm/versions/node/v24.11.1/bin`）を PATH から除外し、
codex / claude コマンドが見つからない状態で `spec-anchor-setup-system` を実行。

## 実行コマンド
```bash
PATH="<nvm除外済みPATH>" spec-anchor-setup-system
```

## 結果
```
production_readiness.status: blocked
blocking_reasons: ['agent_cli_unavailable']
  claude.cli.path: None
  claude.cli.version: None
  codex.cli.path: None
  codex.cli.version: None
exit: 0
```

## 判定
**PASS — 全2項目**

| 確認項目 | 結果 |
|---|---|
| `production_readiness.status="blocked"`, `blocking_reasons=["agent_cli_unavailable"]` | PASS |
| `agent_cli_entries.<agent>.cli.path=null`, `.cli.version=null` | PASS（claude / codex 両方） |

## 対応する EXTERNAL_DESIGN の検証単位
§11.1.5 CLI エラー契約（codex / claude が PATH 上に無い状態の行）
