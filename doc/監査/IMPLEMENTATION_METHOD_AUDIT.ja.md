# 方式妥当性監査

作成日: 2026-05-13

本書は Phase 1 のコード由来内部仕様、Phase 2 の外部標準、Phase 3 の Purpose / Core Concept 抽出に基づく Phase 4 監査結果である。コード修正は行っていない。

## 1. Phase 3 抽出

抽出元は `doc/EXTERNAL_DESIGN.ja.md` の Purpose / Core Concept 範囲のみ。

Purpose の要点:

- LLM が作業中に、本来の目的、Core Concept、関連 Source Specs、Section ごとの概要と検索入口、Section 間関連、章単位 key anchor を見失わないようにする（`doc/EXTERNAL_DESIGN.ja.md:7`）。
- 軽量化方針として、property graph、entity relation graph、hierarchical cluster、Concept 自動更新、広範な conflict 承認フロー、実行モード分岐は標準経路に含めない（`doc/EXTERNAL_DESIGN.ja.md:20`）。
- 主導権は Agent / LLM にあり、CLI は保持物と検索機能を提供する（`doc/EXTERNAL_DESIGN.ja.md:24`）。

Core Concept の要点:

- Purpose は存在理由、達成価値、ユーザー体験や業務上の目的、個別仕様より上位の判断基準を含む（`doc/EXTERNAL_DESIGN.ja.md:30`）。
- Core Concept は判断軸、承認済み設計原則、不変に近い方針を指す（`doc/EXTERNAL_DESIGN.ja.md:54`）。
- LLM が一時的に推測した制約や自動抽出候補は Purpose / Core Concept に含まない（`doc/EXTERNAL_DESIGN.ja.md:41`, `doc/EXTERNAL_DESIGN.ja.md:65`）。

Purpose は監査に使える程度に明確であるため、停止確認は不要と判断した。

## 2. 総合判定

現実装は、Qdrant + BGE-M3 dense/sparse + RRF の Section Retrieval Index、LLM による Section metadata、Related Sections、Conflict Review、Chapter Anchors を持っており、「ベクター DB を使っていない」状態ではない。

一方で、方式設計としては Source Retrieval Index 周辺に重大な不整合が残っている。特に、collection 設定の実消費不一致、Qdrant failure が freshness に反映されないこと、point id / incremental upsert の stale risk、retrieval result から source 本文へ辿る情報不足は、RAG の基礎契約に関わる。

GraphRAG については、Purpose が property graph / entity relation graph / hierarchical cluster を標準経路から外すと明示しているため、GraphRAG 標準と違うこと自体は不具合ではない。ただし、その場合は実態を「lightweight related-section retrieval」として扱い、GraphRAG 相当の graph retrieval をしているかのように報告してはならない。

## 3. 妥当な点

### OK-001: Property graph / entity graph を作っていないこと自体は Purpose で正当化される

判定: 逸脱だが正当化あり。

標準 GraphRAG は entity graph、relationships、community summaries、graph query を持つ。一方、Purpose は標準経路から property graph、entity relation graph、hierarchical cluster を外すと明示している。

実装も Related Sections を retrieval auxiliary / evidence ではないものとして扱う（`spec_grag/related_sections.py:1053`, `spec_grag/related_sections.py:1057`, `spec_grag/related_sections.py:1060`）。そのため、graph DB がないことは単独では指摘対象にしない。

### OK-002: `/spec-inject` が自律 LLM 生成をしない境界は明確

判定: 妥当。

`run_spec_inject()` は provider / llm_provider を API 互換のため受け取るが、意図的に使わず、Agent supplied constraints の検証だけを行う（`spec_grag/inject.py:84`, `spec_grag/inject.py:117`）。Purpose の「主導権は Agent / LLM、CLI は保持物と検索機能を提供」に合う。

### OK-003: Conflict Review の final decision は人間承認が必須

判定: 妥当。

`apply_conflict_decision()` は final decision 適用時に `human_acknowledgement` を要求する（`spec_grag/conflict_review.py:488`）。Related Sections 側も `possible_conflict` の flag だけを出し、`conflicts_with` を直接出さないよう制限されている（`spec_grag/related_sections.py:1856`）。

## 4. 指摘

### AUD-001: `[retrieval].section_collection` が実行時 Qdrant 経路で消費されない

判定: 不整合 / 不足。

根拠:

- 設定 loader は `RetrievalConfig.section_collection` を定義し、`[retrieval].section_collection` をロードする（`spec_grag/config.py:105`, `spec_grag/config.py:480`）。
- `VectorStoreConfig` は `provider` と `url` だけを持つ（`spec_grag/config.py:123`）。
- しかし core の Qdrant read/upsert/payload patch は `vector_store.section_collection` を読む（`spec_grag/core.py:1071`, `spec_grag/core.py:1178`, `spec_grag/core.py:1243`）。
- related candidate generation も `vector_store.section_collection` を読む（`spec_grag/related_sections.py:361`）。
- inject search / section lookup も `_qdrant_section_config()` で `vector_store.section_collection` を読む（`spec_grag/inject.py:954`）。

評価:

標準 hybrid RAG では index / query / payload lookup が同じ collection 設定を共有する必要がある。現実装では外部的に自然な `[retrieval].section_collection` を変えても、実行時の Qdrant 経路は既定値または `[vector_store].section_collection` を使う。これは設定契約と実消費の不一致であり、custom collection を使う環境で index と検索がずれる。

### AUD-002: Qdrant Retrieval Index failure が freshness gate に反映されない

判定: 不整合 / 名乗りと実態の乖離。

根拠:

- `_upsert_section_collection_if_enabled()` は Qdrant 例外時に `"failed"` を返すが core を止めない（`spec_grag/core.py:1154`, `spec_grag/core.py:1216`）。
- `build_freshness_report()` へ渡す failed/degraded artifact は section metadata generation status だけから作られる（`spec_grag/core.py:561`, `spec_grag/core.py:631`）。
- core result の `status` は freshness が failed の場合だけ `"failed"` になり、`retrieval_index_status` は別 field として返る（`spec_grag/core.py:669`, `spec_grag/core.py:679`）。
- freshness 側は `retrieval_index_failed` を required artifact failure として扱える実装を持つが、core はこの input を渡していない（`spec_grag/freshness.py:222`）。
- Related Sections の Qdrant retriever 初期化失敗は InMemoryHybridRetriever へ fallback する（`spec_grag/related_sections.py:1355`, `spec_grag/related_sections.py:1365`）。

評価:

Purpose は CLI が検索機能を提供するとしており、Phase 2 の RAG 基準では retrieval index の可用性は中核である。現実装は `retrieval_index_status=failed` を返すだけで freshness を failed/degraded にしないため、Agent は fresh と判断しても実 Qdrant retrieval が成立していない可能性がある。これは production retrieval success と fallback/in-memory behavior の区別が弱い。

### AUD-003: Qdrant point id が ordinal index で、incremental upsert 時に stale point が残る設計

判定: 不整合。

根拠:

- Section ID と `stable_section_uid` は ordinal に依存する（`spec_grag/section_parser.py:157`, `spec_grag/section_parser.py:158`）。
- Qdrant schema version 名は `qdrant-bge-m3-hybrid-v2-stable-ids` だが、実際の point id は payload list の enumerate index である（`spec_grag/retrieval_index.py:45`, `spec_grag/retrieval_index.py:868`, `spec_grag/retrieval_index.py:873`）。
- core は明示 rebuild または collection 不存在時だけ recreate し、通常は既存 collection に upsert する（`spec_grag/core.py:1203`）。
- `upsert_qdrant_section_collection()` は current payloads の upsert を行うが、削除済み section に対応する既存 point を delete する処理はない（`spec_grag/retrieval_index.py:884`）。

評価:

Source Specs の section 削除・挿入・並べ替えが起きた場合、incremental upsert では古い point が collection に残る、または ordinal index の payload が別 section に差し替わる。RAG index は source corpus と一致していることが前提なので、これは更新頻度のある仕様書に対して重大な index consistency risk である。

### AUD-004: retrieval result が Source Specs 本文 / span に直接接続されていない

判定: 不足。

根拠:

- parser の Section は `source_span` と raw `text` を保持する（`spec_grag/section_parser.py:24`, `spec_grag/section_parser.py:31`, `spec_grag/section_parser.py:35`）。
- Qdrant payload は `source_document_id`、`source_section_id`、hash、summary、search_keys、identifiers、related_sections、`text` を持つが、`source_span` と raw body は保存しない（`spec_grag/retrieval_index.py:707`, `spec_grag/retrieval_index.py:720`）。
- payload の `text` は raw body ではなく、heading / summary / search_keys / identifiers から作る embedding text である（`spec_grag/retrieval_index.py:653`, `spec_grag/retrieval_index.py:666`）。
- `section_payload_to_metadata_entry()` も `source_span` や raw text を復元しない（`spec_grag/section_payload.py:93`, `spec_grag/section_payload.py:106`）。
- `run_inject_search()` の hit は `source_section_id`、heading、summary、search_keys、identifiers、related_sections、score だけを返す（`spec_grag/inject.py:936`）。

評価:

標準 RAG は retrieved passage/chunk を generation context に入れるか、少なくとも source text へ確実に辿れる provenance を返す。現実装の検索結果は summary/search keys 中心で、Agent が CLI だけで source span / raw body を取得できない。Purpose は Source Specs と Section 検索入口を見失わないことを目的にしているため、検索入口から本文確認までの接続が弱い。

### AUD-005: Section Retrieval Index が raw Section body ではなく LLM metadata を embedding 対象にしている

判定: 逸脱 / 不足寄り。

根拠:

- `build_section_embedding_text()` は heading、summary、search_keys、identifiers だけで embedding text を作る（`spec_grag/retrieval_index.py:653`, `spec_grag/retrieval_index.py:666`）。
- Qdrant upsert はこの `payload["text"]` を BGE-M3 へ渡す（`spec_grag/retrieval_index.py:847`, `spec_grag/retrieval_index.py:854`）。
- Section metadata は LLM 生成であり、失敗時には fallback summary / 空 search keys になる経路がある（`spec_grag/section_metadata.py:240`, `spec_grag/section_metadata.py:1170`）。

評価:

Purpose には Section Summary / Search Keys が検索入口として必要という方向性があるため、この設計は一部正当化できる。しかし標準 RAG の基準では source chunk 本文自体、または本文に忠実な chunk representation を index するのが基本である。現在は LLM metadata の抽出漏れが retrieval recall の漏れに直結する。特に仕様書の SHOULD/MUST/禁止条件など、summary に落ちない語が検索できない可能性がある。

### AUD-006: Chapter Anchors の LLM fallback が artifact success として扱われ、freshness に degrade 反映されない

判定: 不整合 / 過大申告 risk。

根拠:

- `generate_chapter_anchors()` は provider missing / failure / unparseable response 時に mechanical anchor へ fallback し、`fallback_chapter_ids` に記録する（`spec_grag/chapter_anchors.py:140`, `spec_grag/chapter_anchors.py:247`, `spec_grag/chapter_anchors.py:253`）。
- artifact は fallback があっても `"status": "success"` になる（`spec_grag/chapter_anchors.py:260`）。
- core の freshness report は metadata generation の failed/degraded だけを反映し、chapter anchor fallback を degraded optional artifact として渡していない（`spec_grag/core.py:631`）。

評価:

Purpose は章単位 key anchor を見失わないことを要求している。mechanical anchor は可用性維持としては妥当だが、LLM-generated anchor と同じ success として扱うと Agent が品質差を見落とす。fallback は diagnostics / freshness warning に反映すべきである。

### AUD-007: Related Sections の Qdrant fallback が diagnostics へ十分に表出しない

判定: 不足。

根拠:

- real Qdrant を使う条件は vector store が qdrant、url がある、embedding provider が flagembedding の場合である（`spec_grag/related_sections.py:371`）。
- Qdrant retriever 初期化に失敗すると例外を握って `retriever=None` にし、その後 InMemoryHybridRetriever を使う（`spec_grag/related_sections.py:1355`, `spec_grag/related_sections.py:1363`, `spec_grag/related_sections.py:1365`）。
- `_add_qdrant_section_hybrid_candidates()` は fallback を呼び出し元へ diagnostics として返す戻り値を持たない（`spec_grag/related_sections.py:1304`）。
- core の `_generate_related_sections()` は generate 全体の例外だけ diagnostics 化する（`spec_grag/core.py:1549`, `spec_grag/core.py:1567`）。

評価:

Related Sections は evidence ではないが、Conflict Review 候補や Agentic Search の入口になる。Qdrant hybrid retrieval を期待する設定で InMemory fallback が起きても明示的に表出しないため、production path と fallback path の区別が監査・運用上不十分である。

## 5. 方式妥当性まとめ

妥当:

- 軽量方針として property graph / entity graph を標準経路に含めない判断。
- `/spec-inject` が LLM を呼ばず Agent supplied constraints を検証する境界。
- Conflict Review final decision に人間承認を要求する設計。

不整合 / 不足:

- Retrieval collection 設定の読み先が `[retrieval]` と `[vector_store]` で割れている。
- Qdrant index failure が freshness gate に反映されない。
- Qdrant point id / incremental upsert が source deletion/reorder に弱い。
- 検索結果が raw Source Specs 本文 / span へ直接接続されていない。
- Embedding 対象が raw source ではなく LLM metadata に寄っている。
- Chapter Anchors / Related Sections の fallback が degraded として十分に表出しない。

結論:

現在の実装は「軽量 SPEC-grag」としての方向性は Purpose と整合するが、RAG の基礎である retrieval index の整合性・可用性・provenance がまだ弱い。特に AUD-001 から AUD-004 は方式設計上の中核問題であり、実装後の smoke / fake passing だけでは完了扱いにできない。

