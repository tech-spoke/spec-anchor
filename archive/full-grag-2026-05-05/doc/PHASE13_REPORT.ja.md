# Phase 13 実行報告: stable identity migration

## 実施範囲

- `stable_section_uid` を本文 hash 由来ではなく、初回観測後に manifest から引き継ぐ永続 ID として扱うようにした。
- `SourceManifest.by_stable_section_uid()` と `ManifestReconciliation.renamed_sections` を追加し、`reconcile_manifests()` を stable ID 主体に変更した。
- heading rename は added / removed ではなく rename として扱い、本文変更は同一 stable ID の changed として扱うようにした。
- 重複 stable ID や曖昧な body match は primary key として扱わず、安全側で added / removed に倒すようにした。
- `stable_chunk_uid` を stable section ID + chunk ordinal 主体に変更し、本文変更時も同じ chunk ordinal の retrieval unit ID を維持するようにした。
- `DocumentChunksSidecar` / BM25 / chunk vector index / retrieval index に stable chunk / stable section lookup を追加し、retrieval 内部 key は `stable_chunk_uid` を優先するようにした。
- `chunk_id` / `section_id` は alias、citation、debug、後方互換用として維持した。
- SECTION / ANCHOR node と relation provenance に `stable_section_uid` / `stable_source_section_uid` / `stable_source_chunk_uid` を追加した。
- stale cleanup は stable provenance を優先し、旧 `source_section_id` を fallback alias として使えるようにした。
- AgenticSearchCandidate の `source_section_id` は current ID / stable ID / alias から current manifest entry へ解決できるようにした。
- InjectionContext の raw chunk citation に `stable_chunk_uid`、旧 `chunk_id`、current `section_id`、`source_span` を併記するようにした。

## 検証

- `uv run --with pytest python -m pytest`
- 結果: `222 passed in 194.04s (0:03:14)`。

追加・更新した主な regression:

- heading rename で stable section ID を維持し、added / removed ではなく rename として扱う
- body edit で stable section ID を維持し、semantic/source hash 差分で changed と判定する
- duplicate body で stable ID が衝突しない
- `stable_chunk_uid` が同じ chunk ordinal の body edit で維持される
- chunk vector index が旧 `chunk_id` 変更後も `stable_chunk_uid` で embedding を再利用できる
- BM25 postings / retrieval index が stable chunk / stable section key を持つ
- schema extraction artifact に stable provenance が付く
- graph cleanup が stable provenance だけでも削除できる

## 残タスク

Phase 13 の実装残としては扱わない。

- 古い artifact の厚い migration は範囲外。新規 core run で stable key 主体の artifact を再生成する。
- Qdrant / ANN 導入は将来対応。導入時は今回の `stable_chunk_uid` を point ID / payload 主キーにする。
- watcher queue や Concept diff の外部表示は引き続き `source_section_id` 互換を維持する。完全な stable ID 表示切替は必要が出た時点で別管理とする。

## 注意点

`stable_chunk_uid` は content hash ではなく stable section ID + chunk ordinal を主軸にした。本文変更時の embedding 再利用可否は `chunk_hash` で判定し、ID は retrieval unit の継続性を表す。

section split / merge や duplicate stable ID のような曖昧ケースは、誤った primary key 継承を避けるため added / removed または changed 側に倒す。
