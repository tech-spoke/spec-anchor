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

判定: 採用。B-3a (commit `202af3d feat: B-3a deterministic Qdrant point id + stale delete + ordinal migration`) で修正済み。

理由: index / query / payload lookup は同一 point id 空間で安定して同じ Section に解決される必要がある。ordinal id は collection 再作成時のみ stable で、section の追加・削除・並べ替えで対応関係が崩れる。

対応:

- `spec_grag/retrieval_index.py` に `stable_section_point_id(source_section_id) -> str` を追加し、Qdrant section collection の point id を `source_section_id` の UUID5 に統一した。固定 namespace UUID は `_SECTION_POINT_ID_NAMESPACE = uuid.UUID("b1d5535d-3e52-5430-af3e-ddd879e6cb19")` で、`uuid.uuid5(uuid.NAMESPACE_URL, "spec-grag.section-collection.v1")` の結果値を literal として埋め込んだ。
- `upsert_qdrant_section_collection` の `recreate=False` 経路で、`client.scroll(...)` の既存 point id 集合と `stable_section_point_id` の期待集合の差分を `client.delete(..., points_selector=PointIdsList(...))` で削除する経路を追加した。
- `upsert_qdrant_section_collection` は `recreate=False` で `client.scroll(..., limit=1)` の sample point id が UUID として parse できない場合、ordinal id collection と判定して `recreate=True` に切り替える。`core_progress.json` の `stages.section_collection_upsert.diagnostics` に `reason = "migration_required_from_ordinal_point_id"` と `warnings = ["migration_required_from_ordinal_point_id"]` を記録する。
- `spec_grag/core.py` の `_retrieval_schema_pin_fingerprint()` 入力に `"point_id_scheme": "point_id_v1_uuid5_source_section_id"` を追加した。B-3a 以前に書かれた `.spec-grag/state/retrieval_index_state.json` は B-3a 後の初回実行で必ず fingerprint 不一致になり、通常経路に落ちて auto-migration が走る。
- `doc/EXTERNAL_DESIGN.ja.md` §2.4 で `source_section_id` の global unique 性 (`<file_path>#<heading_slug>` 形式、`[sources].include` 全体で一意) を明記した。
- `doc/EXTERNAL_DESIGN.ja.md` §4.1 で Qdrant point id の UUID5 規約と固定 namespace UUID 値を明記した。§7.4 に旧 ordinal collection 検出時の auto-migration の user 向け動作を追記した。
- `doc/DESIGN.ja.md` §4.7 で `retrieval_schema_pin_fingerprint` 計算式に `point_id_v1_uuid5_source_section_id` を追記し、§4.8 で auto-migration アルゴリズムと stale-delete アルゴリズムを内部実装の用語で記述した。

証跡:

- `tests/test_retrieval_index.py` に 6 軸の独立 unit test を追加した:
  - `test_stable_section_point_id_deterministic` (A 同一 `source_section_id` で同一 point id)
  - `test_stable_section_point_id_no_collision` (B 50 個の異なる `source_section_id` で衝突なし)
  - `test_upsert_stale_delete_recreate_false` (C `recreate=False` で削除 section の point が `client.delete` 経由で消える)
  - `test_stable_section_point_id_reorder_invariance` (D Section の並べ替えで point id と payload の対応が崩れない)
  - `test_upsert_migration_from_ordinal` (E 旧 ordinal point id 検出時の `recreate=True` 切り替えと diagnostics)
  - `test_fast_path_consistency_with_new_fingerprint` (F 新 fingerprint 形式で fast path が正常動作)
- `git grep "uuid.uuid5" spec_grag/` は `retrieval_index.py:64` の `stable_section_point_id` 関数本体 1 件のみで、他に直接呼出しは存在しない。
- 実 Qdrant (localhost:6333) と実 BGE-M3 を使った smoke 検証 (smoke fixture `docs/spec/sample.md` の 4 section):
  - B-3a commit 前の旧 ordinal collection (point id = 整数 `0`, `1`, `2`, `3`) に対して `spec-grag core` を実行 → auto-migration が発火し、`stages.section_collection_upsert.action = "fallback_rebuilt"`、`diagnostics.warnings = ["migration_required_from_ordinal_point_id"]`、wall time 17.860s。
  - migration 直後の Qdrant collection sample point id は `2f38b869-45ae-5a63-91cf-8163aaab637f` 等の UUID5 文字列。Python で `uuid.uuid5(b1d5535d-..., "docs/spec/sample.md#0003-authorization")` を計算した結果と一致を確認。
  - 2 回目 `spec-grag core` で wall time 1.254s、BGE-M3 model load 0 回、`stages.section_collection_upsert.action = "skipped_unchanged"`、`stages.related_sections.action = "skipped_unchanged"`。B-2 fast path が回帰なく動作することを確認した。
- `pytest -q --skip-external`: 359 passed, 16 skipped (B-3a 前の baseline 353 から +6、上記 6 軸 unit test 分が増加)。

残 TODO: なし。

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

判定: 保留 / 方針再検討済み (2026-05-14)。

理由: 今回は Source Retrieval Index と Related Sections の no-change fast path、および retrieval provenance を対象にした。Chapter Anchors fallback の扱いは別変更で固定する。

方針切替 (2026-05-14): 当初の「degraded 反映」案は破棄し、**通常モードでは mechanical fallback を failed 扱い・canonical 保存しない** 方針に切り替えた。degraded で先に進める設計は「動いているように見えるが品質保証されていない」状態を許容してしまい、Purpose (章単位 key anchor を見失わない) を満たさないため。詳細は `doc/TODO.ja.md` の AUD-006 残 TODO を参照。

対応:

- 今回は未修正。
- `doc/TODO.ja.md` に AUD-006 の残 TODO を追加 (2026-05-13)、方針切替を反映して更新 (2026-05-14)。

証跡:

- 未検証。

残 TODO:

- 通常モードで `fallback_chapter_ids` が 1 件以上発生した場合、`chapter_anchors` artifact を `status: failed` (または `partial_failed`) にし、canonical file として書き込まない。core 最終結果は `failed_required_artifacts` に `chapter_anchors` を含めて `status: failed` にする。
- mechanical fallback の preview は CoreResult diagnostics に残す (Agent / human review 用)。
- explicit best-effort mode (`--allow-mechanical-anchors` 仮称) の導入是非を人間判断で確定する。
- `doc/EXTERNAL_DESIGN.ja.md` の Chapter Anchors / freshness 仕様にこの扱いを明記する。
- `tests/test_chapter_anchors.py` 等で provider missing / provider failure / unparseable response の 3 ケースを通常モードで分けて検証する。

## AUD-007: Related Sections の Qdrant fallback が diagnostics へ十分に表出しない

判定: 保留 / 方針再検討済み (2026-05-14)。

理由: 今回の Related Sections 変更は no-change fast path と status 公開であり、Qdrant retriever 初期化失敗時の扱いはまだ実装していない。

方針切替 (2026-05-14): 当初の「diagnostics 表出 + warnings 反映」案は弱いと判定し、**Qdrant を期待した設定 (`vector_store.provider = qdrant`、`url` 設定済み) で初期化失敗 → InMemory fallback した場合は、通常モードで Related Sections を failed として扱い、canonical artifact として success 保存しない** 方針に切り替えた。

ただし Qdrant 未設定で最初から InMemory を使う dev / test 構成は対象外 (`success` のまま)。問題は「Qdrant を期待した設定なのに黙って InMemory に変わること」のみ。詳細は `doc/TODO.ja.md` の AUD-007 残 TODO を参照。

対応:

- 今回は未修正。
- `doc/TODO.ja.md` に AUD-007 の残 TODO を追加 (2026-05-13)、方針切替を反映して更新 (2026-05-14)。

証跡:

- 未検証。

残 TODO:

- 通常モードで Qdrant 設定済み + 初期化失敗の場合、`related_sections` artifact を `status: failed` にし、canonical file として success 保存しない。core 最終結果は `failed_required_artifacts` に `related_sections` を含めて `status: failed` にする。
- CoreResult diagnostics に `expected_retrieval_backend = "qdrant"` / `actual_retrieval_backend = "in_memory"` / `fallback_used` / `fallback_reason` / `qdrant_url_configured` / `embedding_provider` を記録する。
- `_add_qdrant_section_hybrid_candidates()` ([spec_grag/related_sections.py:1304](spec_grag/related_sections.py#L1304)) の現状 (例外を握って `retriever = None` で InMemory に落ちる) を、fallback 情報を上位へ伝搬する戻り値経路に変える。
- explicit best-effort mode (`--best-effort` 仮称、AUD-006 と共通) の導入是非を人間判断で確定する。
- `doc/EXTERNAL_DESIGN.ja.md` の Related Sections / freshness 仕様にこの扱いを明記する。
- Qdrant 設定済み + 初期化失敗 / Qdrant 正常 / Qdrant 未設定 (純 InMemory) の 3 経路を test で分けて検証する。

## 検証

- `PYTHONPATH="$PWD" .venv/bin/python -m py_compile spec_grag/core.py spec_grag/artifacts.py spec_grag/inject.py spec_grag/related_sections.py spec_grag/retrieval_index.py spec_grag/section_payload.py spec_grag/watcher.py`: passed
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q tests/test_spec_core.py::test_b2_incremental_no_change_skips_retrieval_and_related_heavy_paths tests/test_spec_core.py::test_aud002_retrieval_index_failure_marks_freshness_failed tests/test_spec_core.py::test_t_i03_core_result_has_required_public_fields tests/test_retrieval_index.py::test_section_payloads_one_per_section tests/test_section_payload.py::test_section_payload_to_metadata_entry_matches_legacy_shape tests/test_section_payload.py::test_section_payload_to_metadata_entry_fills_empty_defaults tests/test_inject_cli_extension.py::test_inject_search_returns_source_provenance_for_agentic_search`: 7 passed
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external`: 350 passed, 16 skipped
- `SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q tests/test_retrieval_index.py::test_t_i05_embedding_to_qdrant_roundtrip_uses_real_local_service`: 1 passed
- 実 Qdrant / BGE-M3 と fake LLM provider の一時 project smoke: first run 17.754 秒、second run 0.072 秒、2 回目は `retrieval_index_status == "skipped_unchanged"` / `related_sections_status == "skipped_unchanged"`

## R-001: Related Sections の collection fallback が core / inject と一致していない

指摘 ID: R-001

指摘要約: `spec_grag/related_sections.py` の collection 名解決が `[retrieval].section_collection` → `[vector_store].section_collection` → `spec_grag_section` の 2-step fallback になっており、`spec_grag/core.py` と `spec_grag/inject.py` が使う `[vector_store].collection` fallback と一致していなかった。

判定: 採用。

理由: Source Retrieval Index、inject-search、Related Sections の Qdrant section collection は同じ設定優先順で解決される必要がある。Related Sections だけ `[vector_store].collection` を無視すると、既存 project 設定で core / inject と異なる collection を参照する可能性がある。

対応:

- `spec_grag/related_sections.py:361` で collection 名解決を `[retrieval].section_collection` → `[vector_store].section_collection` → `[vector_store].collection` → `spec_grag_section` に変更した。
- `tests/test_related_sections.py:655` に `test_qdrant_section_hybrid_uses_vector_store_collection_fallback` を追加し、`[vector_store].collection` が Related Sections の Qdrant retriever へ渡ることを確認した。

証跡:

- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external tests/test_related_sections.py::test_qdrant_section_hybrid_uses_vector_store_collection_fallback`: 1 passed
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external`: 353 passed, 16 skipped
- 確認箇所: `spec_grag/related_sections.py:361`、`tests/test_related_sections.py:655`

残 TODO: なし。

## R-002: inject-search path で `[retrieval].section_collection` 優先を確認する test がない

指摘 ID: R-002

指摘要約: inject-search の collection 名解決について、`[vector_store].collection` と `[retrieval].section_collection` が同時に存在する場合に `[retrieval].section_collection` を優先する regression test がなかった。

判定: 採用。

理由: inject-search は Agentic Search の主経路であり、core が upsert した collection と同じ collection を検索する必要がある。設定優先順の regression test がないと、将来の refactor で `[vector_store].collection` が誤って使われても検出できない。

対応:

- `tests/test_inject_cli_extension.py:310` に `test_inject_search_prefers_retrieval_section_collection_over_vector_store_collection` を追加した。
- test 内で `_build_hybrid_retriever` を monkeypatch し、`run_inject_search()` が渡す collection 引数が `right_collection` であり、`wrong_collection` ではないことを確認した。
- production code の `spec_grag/inject.py:963` は既に `[retrieval].section_collection` → `[vector_store].section_collection` → `[vector_store].collection` → `spec_grag_section` の優先順になっているため、R-002 では test を追加した。

証跡:

- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external tests/test_inject_cli_extension.py::test_inject_search_prefers_retrieval_section_collection_over_vector_store_collection`: 1 passed
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external`: 353 passed, 16 skipped
- 確認箇所: `tests/test_inject_cli_extension.py:310`、`spec_grag/inject.py:963`

残 TODO: なし。

## R-004: `_source_span_payload()` が欠落・不正 field を 0 埋めしている

指摘 ID: R-004

指摘要約: `spec_grag/retrieval_index.py` の `_source_span_payload()` が `start_line` / `end_line` / `start_offset` / `end_offset` の欠落または不正値を 0 に置き換え、実在しない source span を payload に入れる可能性があった。

判定: 採用。

理由: `source_span` は Agent が Source Specs 本文へ戻るための provenance であり、欠落・不正 field を 0 埋めすると誤った本文範囲を示す。`spec_grag/section_payload.py` の metadata entry と同様に、source span が有効でない場合は空 dict として扱う。

対応:

- `spec_grag/retrieval_index.py:1176` の `_source_span_payload()` を変更し、4 field のいずれかが欠落または整数化不可の場合は `{}` を返すようにした。
- `tests/test_retrieval_index.py:442` に `test_section_payloads_use_empty_source_span_for_incomplete_or_invalid_fields` を追加した。

証跡:

- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external tests/test_retrieval_index.py::test_section_payloads_one_per_section tests/test_retrieval_index.py::test_section_payloads_use_empty_source_span_for_incomplete_or_invalid_fields`: 2 passed
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external`: 353 passed, 16 skipped
- 確認箇所: `spec_grag/retrieval_index.py:1176`、`tests/test_retrieval_index.py:442`

残 TODO: なし。
