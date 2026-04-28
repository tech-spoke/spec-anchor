# 08: transient annotation の実装パターン

> 状態: 未確認
> 最終更新: 2026-04-28

## 調査対象

DESIGN.ja.md §1.6 / TODO.md の境界に従い、**4 軸評価（transient annotation）を graph store に書かず、retrieval result / Orchestrator 側に持つ実装パターン**を確認する。

transient annotation:

- `constraint_relevance: none | low | medium | high`
- `target_relevance: none | low | medium | high`
- `conflict: true | false`（LLM 単独では false まで、§1.5）
- `review_required: true | false`
- 派生: `irrelevant`

- component: retrieval result の data structure（NodeWithScore 等）
- version / commit: _pending_
- source:
  - official docs: _pending fetch_
  - GitHub source: _pending fetch_
  - 実行確認: _pending spike/_

## 確認した API

- retrieval result の構造（NodeWithScore など）: _pending_
- annotation を retrieval result に付与する公式パターン（postprocessor / metadata layering 等）: _pending_
- annotation を graph store に書き戻さない隔離手段: _pending_

## 実測・検証結果

- 4 軸を retrieval result に乗せて返せるか: _pending_
- LlamaIndex の標準 postprocessor / response_synthesizer がこのパターンに合うか: _pending_
- Orchestrator 側で 4 軸を保持する場合の data flow: _pending_

## spec-grag への影響

- DESIGN §1.6 / §1.9 経路 3 の 4 軸付与（LLM Classification + Orchestrator）が成立するか:
- graph store への書き込み防止の enforcement 方法:
- 未解決事項:
  - retrieval result が複数 query で再利用される場合の隔離
  - InjectionContext / RealignResult まで透過させる serialization 方式

## 判定

unknown
