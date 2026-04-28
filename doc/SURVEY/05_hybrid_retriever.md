# 05: HybridRetriever fusion 戦略

> 状態: 未確認
> 最終更新: 2026-04-28

## 調査対象

- component: `llama_index.core.retrievers.HybridRetriever` 等（property graph 系の hybrid retrieval）
- version / commit: _pending_
- source:
  - official docs: _pending fetch_
  - GitHub source: _pending fetch_
  - 実行確認: _pending spike/_

## 確認した API

- import path: _pending_
- constructor: _pending_
- fusion 戦略の指定方式（RRF / Weighted / CombSum / MaxScore のうち何が標準か）: _pending_
- API レベルでの切替可否: _pending_

## 実測・検証結果

- 最小コードで動いたこと: _pending_
- 動かなかったこと: _pending_
- エラー: _pending_
- 期待と違った点: _pending_

## spec-grag への影響

- 制約探索 / 修正対象探索（DESIGN §1.9 経路 3）の 2 系統 retrieval にどう活かせるか:
- vector retriever と graph retriever の合成方式:
- 未解決事項:
  - 日本語 embedding (nomic-embed-text) との相性
  - cross-encoder rerank（DESIGN §4.4）との接続方式

## 判定

unknown
