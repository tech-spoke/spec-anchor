# P2-F4: watcher 実行中の freshness gate

## 実行日時
2026-05-23 JST

## 手順
1. Source Specs (`docs/spec/sample.md`) に1行追加して変更を作る
2. `spec-anchor-watch --debounce-sec 1 --interval-sec 1` を起動
3. `watch_state.json` の `is_running=true` を確認（2秒後）
4. `spec-anchor inject-search "認証"` を実行
5. watcher を停止

## 確認結果

```
inject-search exit: 0
status: blocked
should_stop: True
blocking_reasons: ['dirty_or_stale_source', 'watcher_running']
recommended_next_action: run /spec-core before /spec-inject
```

`watcher_running` と `dirty_or_stale_source` が同時に blocking_reasons に入った  
（Source Specs 変更 + watcher 実行中の複合状態）。

## 判定
**PASS — 全2項目**

| 確認項目 | 結果 |
|---|---|
| `blocking_reasons` に `watcher_running` が含まれ、inject-search が `should_stop=True` で停止 | PASS |
| exit code 0 | PASS |

## 対応する EXTERNAL_DESIGN の検証単位
§3.3 保持物の鮮度（watcher 実行中の停止）/ §6.3 spec-anchor-watch / §11.1.5 watcher_running 行
