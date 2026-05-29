# #3-s03 pending conflict 複数件 (/spec-inject)

衝突が 2 件以上。見出しを 1. 2. と連番にする。

---

■ 人間判断が必要な仕様の衝突があります (2 件)

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

  2. パスワード最小長を 8 文字とするか 12 文字とするか

     主張 A: パスワードは 8 文字以上とする。
        出典: docs/spec/auth.md#0004-password-policy
     主張 B: パスワードは 12 文字以上とする。
        出典: docs/spec/security.md#0009-credential-strength

     論点: 最小長の要件が異なり、どちらを採るかで実装が変わる。
     人間判断が必要な理由: コンプライアンス要件の選択であり資料だけでは決められない。
     重要度: 中

     関係する仕様:
       - docs/spec/auth.md#0004-password-policy
       - docs/spec/security.md#0009-credential-strength

     選択肢:
       - 8 文字以上に統一する
       - 12 文字以上に統一する

     次の操作: Ask a human to decide this conflict.

     (衝突 ID: CONF-0009  ← 再参照用)
