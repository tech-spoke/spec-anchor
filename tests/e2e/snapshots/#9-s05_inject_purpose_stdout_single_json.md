# #9-s05 CLI stdout = valid JSON single object

検証コマンド: `spec-anchor inject-purpose` を `.spec-anchor/config.toml` が無い空プロジェクトで実行。

意味: このシナリオは「stdout が JSON object 1 個だけで、外部ライブラリの進捗ログや
警告が混入しない」という #9 の契約を確認する。空プロジェクトでは config 不在の
構造化エラー JSON が返るが、検証対象は **stdout の形** (単一 JSON object) であって
コマンドの成否ではない。実モデルまで初期化する成功経路の no-noise 確認は、Qdrant /
FlagEmbedding BGE-M3 を起動した実機が必要 (外部ブロッカー) であり、stdout への
ライブラリ出力リダイレクト機構自体は `test_library_stdout_noise_is_redirected` で
別途確認している。

実 stdout (そのまま貼付、`json.loads` で 1 object としてパース可能):

```json
{
  "blocked": true,
  "can_continue": false,
  "command": "/spec-inject inject-purpose",
  "constraints": [],
  "error": {
    "code": "command_error",
    "message": ".spec-anchor/config.toml not found under /tmp/claude-1001/tmp0vb6zu5z",
    "type": "ConfigError"
  },
  "project_root": "/tmp/claude-1001/tmp0vb6zu5z",
  "should_stop": true,
  "status": "error",
  "stops": true
}
```
