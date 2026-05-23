# P1-E6-Agent: /spec-realign Agent CLI 出力（4区分構造）

## 実行日時
2026-05-23 JST

## 実行コマンド
```bash
cd /tmp/sa-test-sonnet-e3-q2iKl
claude --print \
  --allowedTools "Bash(spec-anchor inject*),Bash(spec-anchor realign*),Read" \
  --no-session-persistence \
  "/spec-realign 認証エンドポイントでセッションタイムアウトを24時間に設定する実装案を提示して"
```
exit: 0

## 出力の4区分構造確認

### ✅ 今回守る制約（4件）
- セッションは非アクティブ24時間で失効
  - 根拠: `docs/spec/sample.md#0002-authentication`
- ログアウトは即時無効化
  - 根拠: `docs/spec/sample.md#0004-session-termination`
- 期限切れセッションは5分間隔で自動削除
  - 根拠: `docs/spec/sample.md#0004-session-termination`
- ログインエンドポイントはリモートIP単位1分5回レートリミット
  - 根拠: `docs/spec/sample.md#0002-authentication`

### ✅ 今回扱う修正候補または検討対象
- 認証エンドポイントのセッションタイムアウトを 86400秒（非アクティブ基準）に設定

### ✅ 競合 / 不確実性 / 人間レビューが必要な点
- フレームワーク選択（仕様書に記載なし）
- 非アクティブトラッキングの実装詳細（DB vs インメモリ）

### ✅ 課題プロンプトへの回答または修正案
- ログイン成功時のセッション生成、認証ミドルウェア、ログアウトエンドポイント、バックグラウンドスイープ、ログインレートリミットの擬似コードを提示

## 制約との矛盾確認
回答案は全制約と整合している。矛盾なし（「競合 / 不確実性」セクションに矛盾は隠されていない）。

## 判定
**PASS — 全4項目**

| 確認項目 | 結果 |
|---|---|
| 4区分（今回守る制約 / 今回扱う修正候補 / 競合・不確実性・人間レビュー / 課題への回答）が全て出力される | PASS |
| 制約は Source Specs に根拠を持ち `evidence_origin` が明示されている | PASS |
| 回答案が制約と矛盾する場合に「競合・不確実性」セクションに明示されている（今回は矛盾なし） | PASS |
| CLI が回答本文を独自生成せず Agent が整形した形で提示している | PASS |

## 対応する EXTERNAL_DESIGN の検証単位
§9.3 Answer 生成契約（4区分構造） / §9.2 動作
