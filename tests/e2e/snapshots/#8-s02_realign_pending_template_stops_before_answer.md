# #8-s02 /spec-realign テンプレートが pending 時に提示停止

検証対象: 課題関連の pending がある場合、テンプレートは答案つきの spec-anchor realign を呼ばない。CLI ではなく Agent / LLM 側の停止責務を確認する。

---

今回守る制約
  - セッション失効処理は Source Specs の該当節を根拠にする。
    根拠の種類: Source Specs
    参照: docs/spec/auth.md#0002-session-management
    適用範囲: セッション失効処理の実装方針

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

回答は生成していません。上記の衝突について、人間が仕様判断を示してから回答へ進みます。
