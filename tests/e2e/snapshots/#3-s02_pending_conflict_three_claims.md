# #3-s02 pending conflict 1 件 / 3 件以上の claims (/spec-realign)

主張が 3 件以上ある衝突。主張 A / B / C と連続させる。

---

■ 人間判断が必要な仕様の衝突があります (1 件)

  1. 価格表示の通貨をどう扱うか

     主張 A: 価格は常に税込で表示する。
        出典: docs/spec/pricing.md#0003-tax-included
     主張 B: 価格は税抜で表示し、税は明細で別建てにする。
        出典: docs/spec/pricing.md#0008-tax-breakdown
     主張 C: 表示通貨は利用者のロケールに従って切り替える。
        出典: docs/spec/i18n.md#0011-locale-currency

     論点: 税込・税抜・ロケール依存の 3 方針が同時には成立せず、表示仕様が一意に定まらない。
     人間判断が必要な理由: 法令要件と UX 方針のどちらを優先するかは事業判断であり、資料だけでは決められない。
     重要度: 中

     関係する仕様:
       - docs/spec/pricing.md#0003-tax-included
       - docs/spec/pricing.md#0008-tax-breakdown
       - docs/spec/i18n.md#0011-locale-currency

     選択肢:
       - 税込表示に統一する
       - 税抜表示 + 税明細別建てにする
       - ロケール依存で表示を切り替える

     次の操作: 人間判断で衝突を解消してください。

     (衝突 ID: CONF-0012  ← 再参照用)
