# 06: HippoRAG / LightRAG retrieval 統合

> 状態: WebFetch ✓ / GitHub ☐ / Spike ☐ — 判定 **not_present_in_lpg_guide**（spec-grag では当面不要）
> 最終更新: 2026-04-28

## 調査対象

- component: HippoRAG / LightRAG retrieval の LlamaIndex integration
- version / commit: llama-index-core **0.14.21**
- source:
  - official docs (lpg_index_guide): https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
  - GitHub source: _pending fetch_
  - 実行確認: _不要（spec-grag では当面採用しない）_

## 確認した API（WebFetch レベル）

- lpg_index_guide ページに **HippoRAG / LightRAG の言及なし**（WebFetch で確認済）
- 別 integration package（例: `llama-index-graph-rag` 系）が存在するかは要追加確認、ただし spec-grag の retrieval 設計には現時点で不要

## 実測・検証結果

- 最小コードで動いたこと: _不要_
- 期待と違った点:
  - 当初 TODO.md / DESIGN §4.1 では「HippoRAG / LightRAG 統合可否」を調査項目に挙げていたが、Property Graph Index guide ではこれらは取り上げられていない

## spec-grag への影響

- spec-grag の retrieval 設計は **PGRetriever + sub_retrievers + spec-grag Orchestrator 側 4 軸評価** で完結する見込み（項目 05 / 08 と整合）
- HippoRAG / LightRAG は研究色の強い retrieval 戦略で、spec-grag の必須要件ではない
- 必要が出てきたら別途調査する（pivot 後の優先度を考えると最低限の retrieval から始める）
- 未解決事項:
  - 別 integration package の有無
  - spec-grag の特定ユースケース（多段階 multi-hop reasoning）で必要になる時期

## 判定

**not_present_in_lpg_guide** — spec-grag MVP では採用候補から外す。retrieval は項目 05 (PGRetriever) で十分の見込み
