# P2-F2: FlagEmbedding 不在状態のエラーハンドリング

## 実行日時
2026-05-23 JST

## 手順
1. `.venv` 内の FlagEmbedding 1.4.0 を `python -m pip uninstall FlagEmbedding -y` でアンインストール
2. `spec-anchor-setup-system` を実行
3. `python -m pip install "FlagEmbedding==1.4.0"` で再インストールして復旧

## 注意
最初の `pip uninstall` コマンド（pip バイナリ直接）が効かなかった（pip バイナリが not found）。  
`python -m pip uninstall` で成功した。

## 確認結果
```
production_readiness.status: blocked
blocking_reasons: ['flagembedding_missing']
FlagEmbedding provider: {available: False, version: null}
flagembedding check: {name: 'flagembedding_package', reason_code: 'flagembedding_missing', status: 'failed'}
exit: 0
```

## 復旧確認
```
from FlagEmbedding import BGEM3FlagModel → OK
```

## 判定
**PASS — 全2項目**

| 確認項目 | 結果 |
|---|---|
| `production_readiness.status="blocked"`, `blocking_reasons=["flagembedding_missing"]` | PASS |
| `providers[FlagEmbedding].available=false`, `version=null` | PASS |

## 対応する EXTERNAL_DESIGN の検証単位
§11.1.5 CLI エラー契約（FlagEmbedding 欠落状態の行）
