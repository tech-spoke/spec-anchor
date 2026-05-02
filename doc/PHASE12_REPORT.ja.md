# Phase 12 実行報告: production query path / artifact consistency / Graph RAG retrieval hardening

## 実施範囲

- `build_injection()` を read-only default に変更し、低レベル API から暗黙に `run_core_update()` が走らないようにした。
- heavy core update path の artifact 書き込みを staging directory 経由にし、commit 前の失敗で active graph artifacts を維持するようにした。
- entity vector の embedding 入力を `name` だけではなく、label / name / heading / description / evidence を含む rich text に変更した。
- `retrieval.graph_expansion_hops` を retrieval path に接続し、bounded traversal と graph path metadata を返すようにした。
- classification cache を追加し、同一 context item の LLM classification を再利用するようにした。
- production で classification budget が尽きた場合、silent rule fallback ではなく `classification_incomplete` として degraded に出すようにした。

## 検証

- `uv run --with pytest python -m pytest -q`
- 結果: `209 passed`

追加した主な regression:

- 低レベル `build_injection()` が read-only default で graph artifact を作らない
- graph expansion が `max_hops=1/2` の差分を持つ
- classification cache が重複 LLM 呼び出しを抑止する
- concept diff 失敗時に active `source_manifest.json` が旧 hash のまま維持される
- entity rich text が変わると embedding が再計算される

## 残タスク

- retrieval sidecar index: `section_id -> chunk_ids`、`section_id -> graph_node_ids`、`node_id -> relation_ids`
- BM25 postings list と dense search 差し替え境界
- stable section / chunk / anchor ID の移行設計
- prompt injection / artifact privacy hardening
- Phase 11 timing metrics の scanned_count / cache_hit / retry_count 拡張
- `DESIGN.ja.md` / `EXTERNAL_DESIGN.ja.md` / `AUDIT_TODO.ja.md` への詳細同期

## 注意点

今回の artifact transaction は heavy core path の最小実装である。no-change / format-only fast path は既存の atomic file write を維持しており、full directory staging の対象外である。
