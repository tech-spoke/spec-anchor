# Phase 12 実行報告: production query path / artifact consistency / Graph RAG retrieval hardening

## 実施範囲

- `build_injection()` を read-only default に変更し、低レベル API から暗黙に `run_core_update()` が走らないようにした。
- heavy core update path の artifact 書き込みを staging directory 経由にし、commit 前の失敗で active graph artifacts を維持するようにした。
- entity vector の embedding 入力を `name` だけではなく、label / name / heading / description / evidence を含む rich text に変更した。
- `retrieval.graph_expansion_hops` を retrieval path に接続し、bounded traversal と graph path metadata を返すようにした。
- classification cache を追加し、同一 context item の LLM classification を再利用するようにした。
- production で classification budget が尽きた場合、silent rule fallback ではなく `classification_incomplete` として degraded に出すようにした。
- `retrieval_index.json` を追加し、section/chunk/node/relation の逆引きを query-time traversal で使うようにした。
- graph traversal policy として relation allowlist、confidence threshold、max graph entities を config 化した。
- BM25 index に postings list を追加し、query term に関係する chunk だけを scoring するようにした。
- `stable_section_uid` / `stable_chunk_uid` / `entity_text_hash` を追加し、heading rename や entity text 変更の追跡をしやすくした。
- extraction / query planning / classification / answer prompt に untrusted input 境界を明記した。
- source / query / context に埋め込まれた命令を untrusted data として扱う prompt regression を追加した。
- run artifact の `include_request` default を false にし、任意の `redact_payload` と `trace_id` / revision diagnostics を追加した。

## 検証

- `uv run --with pytest python -m pytest -q`
- 結果: `216 passed in 180.65s (0:03:00)`。

追加した主な regression:

- 低レベル `build_injection()` が read-only default で graph artifact を作らない
- graph expansion が `max_hops=1/2` の差分を持つ
- classification cache が重複 LLM 呼び出しを抑止する
- concept diff 失敗時に active `source_manifest.json` が旧 hash のまま維持される
- entity rich text が変わると embedding が再計算される
- `retrieval_index.json` と BM25 postings が生成される
- graph traversal policy が relation type / confidence / max entities を適用し、`CONTRASTS_WITH` で矛盾候補を拾う
- extraction / query planner / classification / answer prompt が source 内 instruction を untrusted data として境界付ける
- heading rename しても本文が同じ section は `stable_section_uid` が維持される
- run artifact は既定で request を保存しない

## 残タスク

- external vector DB / ANN への実差し替え
- stable ID を primary key にする全面移行
- production self-run での latency / token / cost 実測
- readiness report への active / staging / failed revision diagnostics の露出

## 注意点

今回の artifact transaction は heavy core path の最小実装である。no-change / format-only fast path は既存の atomic file write を維持しており、full directory staging の対象外である。
