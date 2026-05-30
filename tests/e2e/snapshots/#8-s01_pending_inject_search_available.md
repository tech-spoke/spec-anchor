# #8-s01 pending が blocker にならず /spec-inject が検索可能

検証対象: pending_conflict_items が返る状態でも、freshness は blocked ではない。CLI は検索結果と pending conflict の両方を返し、Agent が利用者向けに整形する。

---

今回守る制約
  - セッション失効は仕様書の「セッション管理」に書かれた期限を基準にする。
    根拠の種類: Source Specs
    参照: docs/spec/auth.md#0002-session-management
    適用範囲: セッション失効処理を変更する作業

今回見るべき対象
  - セッション失効のバッチ処理

関連先として確認したもの
  - トークン再発行フロー
    理由: セッション失効と連動するため

人間判断が必要な仕様の衝突
  1. セッション保持期間の扱い
     主張 A: セッションは 24 時間で失効する。
        出典: docs/spec/auth.md#0002-session-management
     主張 B: セッションは 7 日間保持する。
        出典: docs/spec/session.md#0004-retention
     論点: 同じセッション保持期間に異なる値が書かれている。
     人間判断が必要な理由: どちらを優先するかを仕様から決められない。
     重要度: 高
     次の操作: 人間判断で衝突を解消してください。
     (衝突 ID: CONF-0001)

不確実性 / 人間確認
  - 上記の衝突が今回の変更対象に関係するため、回答へ進む前に人間判断が必要です。
