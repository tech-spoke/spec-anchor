# #8-s03 /spec-inject と /spec-realign が pending 時に同一提示

検証対象: /spec-inject と /spec-realign は、課題関連の pending がある場合に同じ本文展開で利用者へ提示する。

---

/spec-inject

人間判断が必要な仕様の衝突
  1. セッション保持期間の扱い
     主張 A: セッションは 24 時間で失効する。
        出典: docs/spec/auth.md#0002-session-management
     主張 B: セッションは 7 日間保持する。
        出典: docs/spec/session.md#0004-retention
     論点: 同じ保持期間の値が一致していない。
     人間判断が必要な理由: どちらの節を優先するかを機械判断できない。
     重要度: 高
     次の操作: 人間判断で衝突を解消してください。
     (衝突 ID: CONF-0001)

/spec-realign

人間判断が必要な仕様の衝突
  1. セッション保持期間の扱い
     主張 A: セッションは 24 時間で失効する。
        出典: docs/spec/auth.md#0002-session-management
     主張 B: セッションは 7 日間保持する。
        出典: docs/spec/session.md#0004-retention
     論点: 同じ保持期間の値が一致していない。
     人間判断が必要な理由: どちらの節を優先するかを機械判断できない。
     重要度: 高
     次の操作: 人間判断で衝突を解消してください。
     (衝突 ID: CONF-0001)

同じ本文展開で提示し、回答へ進む前に人間判断を求めます。
