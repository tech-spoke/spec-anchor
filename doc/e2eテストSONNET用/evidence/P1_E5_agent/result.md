# P1-E5-Agent: /spec-inject Agent CLI 出力（5セクション構造）

## 実行日時
2026-05-23 JST

## 実行コマンド
```bash
cd /tmp/sa-test-sonnet-e3-q2iKl
claude --print \
  --allowedTools "Bash(spec-anchor inject*),Read,Bash(spec-anchor realign*)" \
  --no-session-persistence \
  "/spec-inject 認証エンドポイントの実装について"
```
exit: 0

## 出力の5セクション構造確認

### ✅ 今回守る制約（6件）
- メールアドレス＋パスワード認証の実装
  - 根拠: Source Specs / `docs/spec/sample.md#0002-authentication`
- ログインエンドポイントのIP単位速度制限（5回/分）
  - 根拠: Source Specs / `docs/spec/sample.md#0002-authentication`
- セッションの24時間非活動失効
  - 根拠: Source Specs / `docs/spec/sample.md#0002-authentication`
- 管理者MFA必須・サービスアカウント免除
  - 根拠: Source Specs / `docs/spec/sample.md#0002-authentication`
- ログアウト時のセッション即時無効化
  - 根拠: Source Specs / `docs/spec/sample.md#0004-session-termination`
- サービスアカウントのAPIキー認証・ログインUI非接続
  - 根拠: Source Specs / `docs/spec/sample.md#0003-authorization`

### ✅ 今回見るべき対象（2件）
- `docs/spec/sample.md#0002-authentication`（Authentication） 理由付き
- `docs/spec/sample.md#0004-session-termination`（Session Termination） 理由付き

### ✅ 関連先として確認したもの（2件）
- `docs/spec/sample.md#0003-authorization`（depends_on）理由付き
- `docs/spec/sample.md#0001-sample-specification`（prerequisite）理由付き

### ✅ 採用しなかったもの（1件）
- `docs/spec/test_heading.md`系セクション → 「認証仕様と無関係」と明示して棄却

### ✅ 不確実性 / 人間確認（2件）
- Purpose・Core Concept の適用範囲（fixture vs 本番）
- セッション自動削除間隔の実装方式

## 制約の構造確認（constraints JSON）
各 constraint に `statement` / `evidence_origin` / `evidence_ref` / `support_refs` / `applicability` / `uncertainty` が存在。  
`evidence_origin` はすべて `"Source Specs"`（Search Keys / Section Summary を evidence_origin に置いていない）。

## 判定
**PASS — 全5項目**

| 確認項目 | 結果 |
|---|---|
| 5セクション（今回守る制約 / 今回見るべき対象 / 関連先として確認したもの / 採用しなかったもの / 不確実性）が全て出力される | PASS |
| 0件セクションも「採用しなかったもの」のように明示される（省略しない） | PASS |
| 制約に `statement` / `evidence_origin` / `evidence_ref` が存在する | PASS |
| `evidence_origin` が許可 4 種（Purpose/Core Concept/Source Specs/Conflict Review Item）内 | PASS |
| Section Summary / Search Keys / Chapter Key Anchor だけを `evidence_origin` にしていない | PASS |

## 対応する EXTERNAL_DESIGN の検証単位
§8.5 通常出力の 5 セクション構造 / 制約 constraint の最小構造 / §8.3 4 path Agentic Search
