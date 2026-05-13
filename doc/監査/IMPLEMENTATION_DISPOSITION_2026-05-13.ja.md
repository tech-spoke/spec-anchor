# 監査指摘対応 disposition

作成日: 2026-05-13

対象: `doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の指摘に対する、2026-05-13 実装差分の disposition。

## 前提

今回の主な実装対象は `doc/TODO.ja.md` の B-2「incremental no-change の固定費削減」である。あわせて、方式監査で retrieval の通常利用に影響する AUD-001 / AUD-002 / AUD-004 を採用した。

本文 chunking と本文 embedding は実装しない。Section-level retrieval で候補 section に到達し、`search_keys` / `identifiers` と Agentic Search で本文確認へ進む方針を維持する。

## AUD-001: `[retrieval].section_collection` が実行時 Qdrant 経路で消費されない

判定: 採用。

理由: index / query / payload lookup は同じ Qdrant collection 設定を共有する必要がある。

対応:

- `spec_grag/core.py` で Source Retrieval Index の collection 名を `[retrieval].section_collection` 優先にした。
- `spec_grag/inject.py` で inject search / section lookup の collection 名を同じ優先順にした。
- `spec_grag/related_sections.py` で Related Sections candidate generation の Qdrant collection 名を同じ優先順にした。
- `doc/EXTERNAL_DESIGN.ja.md` と `doc/DESIGN.ja.md` の collection 設定記述を更新した。

証跡:

- `tests/test_spec_core.py::test_b2_incremental_no_change_skips_retrieval_and_related_heavy_paths` は `[vector_store].collection` と `[retrieval].section_collection` が異なる条件で、Qdrant upsert が `[retrieval].section_collection` を使うことを確認する。

残 TODO: なし。

## AUD-002: Qdrant Retrieval Index failure が freshness gate に反映されない

判定: 採用。

理由: Source Retrieval Index は検索 API の基盤であり、更新失敗を fresh と扱うと Agent が実 retrieval 成立を誤認する。

対応:

- `spec_grag/core.py` で `retrieval_index_status == "failed"` を `failed_required_artifacts` に入れ、freshness failed に反映する。
- CoreResult warnings に `Source Retrieval Index update failed` を出す。

証跡:

- `tests/test_spec_core.py::test_aud002_retrieval_index_failure_marks_freshness_failed` は Qdrant upsert 例外時に `retrieval_index_status == "failed"`、`freshness_report.status == "failed"`、`failed_required_artifacts` に `retrieval_index` が入ることを確認する。

残 TODO: なし。

## AUD-003: Qdrant point id が ordinal index で、incremental upsert 時に stale point が残る設計

判定: 保留。

理由: 今回の B-2 実装は no-change incremental の skip と collection missing 時の fallback rebuild を対象にした。point id の deterministic 化と stale point deletion は、既存 Qdrant collection の migration / rebuild 方針を伴うため、独立した変更として扱う。

対応:

- 今回は未修正。
- `doc/TODO.ja.md` に AUD-003 の残 TODO を追加した。

証跡:

- B-2 の collection missing fallback は `tests/test_spec_core.py::test_b2_incremental_no_change_skips_retrieval_and_related_heavy_paths` で確認済み。
- stale point deletion は未検証。

残 TODO:

- Qdrant point id を source identity 由来の deterministic id にする。
- 現 source set に存在しない point を削除する。
- 旧 ordinal point を含む collection の migration / rebuild 条件を固定する。

## AUD-004: retrieval result が Source Specs 本文 / span に直接接続されていない

判定: 採用。

理由: Section-level retrieval は summary / search key を入口にしてよいが、Agentic Search が Source Specs 本文を確認するための provenance は必要である。

対応:

- `spec_grag/retrieval_index.py` の Qdrant payload に `source_span` を追加した。
- `spec_grag/section_payload.py` の metadata entry に `source_span` を保持する。
- `spec_grag/inject.py` の `run_inject_search()` hit に `source_document_id` / `source_span` を含める。
- `doc/EXTERNAL_DESIGN.ja.md` と `doc/DESIGN.ja.md` に inject search payload の provenance を記載した。

証跡:

- `tests/test_retrieval_index.py::test_section_payloads_one_per_section` は payload の `source_span` を確認する。
- `tests/test_section_payload.py::test_section_payload_to_metadata_entry_matches_legacy_shape` は metadata entry の `source_span` を確認する。
- `tests/test_inject_cli_extension.py::test_inject_search_returns_source_provenance_for_agentic_search` は inject search hit の `source_document_id` / `source_span` を確認する。

残 TODO: なし。

## AUD-005: Section Retrieval Index が raw Section body ではなく LLM metadata を embedding 対象にしている

判定: 既対応。

理由: 本文 chunking と本文 embedding は今回の設計方針では行わない。Section-level retrieval で候補 section に到達し、本文中の語や MUST / 禁止条件などの recall は `search_keys` / `identifiers` と Agentic Search で補う。

対応:

- embedding text は heading / summary / search_keys / identifiers のまま維持した。
- 本文確認へ進むための `source_document_id` / `source_span` は AUD-004 で追加した。
- `doc/TODO.ja.md` の B-2 scope 外に、本文 chunking と本文 embedding を行わない方針を明記した。

証跡:

- `spec_grag/retrieval_index.py` の `build_section_embedding_text()` は heading / summary / search_keys / identifiers から embedding text を作る。
- `tests/test_inject_cli_extension.py::test_inject_search_returns_source_provenance_for_agentic_search` は retrieval hit から Source Specs 本文確認へ進むための provenance を確認する。

残 TODO: なし。

## AUD-006: Chapter Anchors の LLM fallback が freshness に degrade 反映されない

判定: 保留。

理由: 今回は Source Retrieval Index と Related Sections の no-change fast path、および retrieval provenance を対象にした。Chapter Anchors fallback の freshness 表現は別変更で固定する。

対応:

- 今回は未修正。
- `doc/TODO.ja.md` に AUD-006 の残 TODO を追加した。

証跡:

- 未検証。

残 TODO:

- `fallback_chapter_ids` を freshness warning / diagnostics に反映する。
- fallback 時の freshness status を設計文書と test で固定する。

## AUD-007: Related Sections の Qdrant fallback が diagnostics へ十分に表出しない

判定: 保留。

理由: 今回の Related Sections 変更は no-change fast path と status 公開であり、Qdrant retriever 初期化失敗時の fallback diagnostics はまだ実装していない。

対応:

- 今回は未修正。
- `doc/TODO.ja.md` に AUD-007 の残 TODO を追加した。

証跡:

- 未検証。

残 TODO:

- Qdrant retriever 初期化失敗を Related Sections diagnostics に残す。
- Qdrant 正常時と fallback 時を分ける test を追加する。

## 検証

- `PYTHONPATH="$PWD" .venv/bin/python -m py_compile spec_grag/core.py spec_grag/artifacts.py spec_grag/inject.py spec_grag/related_sections.py spec_grag/retrieval_index.py spec_grag/section_payload.py spec_grag/watcher.py`: passed
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q tests/test_spec_core.py::test_b2_incremental_no_change_skips_retrieval_and_related_heavy_paths tests/test_spec_core.py::test_aud002_retrieval_index_failure_marks_freshness_failed tests/test_spec_core.py::test_t_i03_core_result_has_required_public_fields tests/test_retrieval_index.py::test_section_payloads_one_per_section tests/test_section_payload.py::test_section_payload_to_metadata_entry_matches_legacy_shape tests/test_section_payload.py::test_section_payload_to_metadata_entry_fills_empty_defaults tests/test_inject_cli_extension.py::test_inject_search_returns_source_provenance_for_agentic_search`: 7 passed
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external`: 350 passed, 16 skipped
- `SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q tests/test_retrieval_index.py::test_t_i05_embedding_to_qdrant_roundtrip_uses_real_local_service`: 1 passed
- 実 Qdrant / BGE-M3 と fake LLM provider の一時 project smoke: first run 17.754 秒、second run 0.072 秒、2 回目は `retrieval_index_status == "skipped_unchanged"` / `related_sections_status == "skipped_unchanged"`
