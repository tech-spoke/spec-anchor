# #8-s04 /spec-core 正常完了 (pending conflict あり)

保持物の更新は完了したが、人間判断が必要な衝突が残っている。衝突は #3 の本文展開フォーマットで提示する。

---

■ 保持物の更新が完了しました

  更新があった仕様:
    - docs/spec/auth.md
        - セッション管理 (#0002-session-management)

  人間判断が必要な仕様の衝突:

  ■ 人間判断が必要な仕様の衝突があります (1 件)

    1. セッション失効時間を 24 時間とするか 30 分とするか

       主張 A: セッションは発行から 24 時間で失効する。
          出典: docs/spec/auth.md#0002-session-management
       主張 B: セッションは無操作 30 分で失効する。
          出典: docs/spec/security.md#0005-idle-timeout

       論点: 失効の基準が食い違っており両立しない。
       人間判断が必要な理由: セキュリティ方針の選択であり資料だけでは決められない。
       重要度: 高

       関係する仕様:
         - docs/spec/auth.md#0002-session-management
         - docs/spec/security.md#0005-idle-timeout

       選択肢:
         - 発行から 24 時間で失効に統一する
         - 無操作 30 分で失効に統一する

       次の操作: Ask a human to decide this conflict.

       (衝突 ID: CONF-0007  ← 再参照用)
