# Step 3 業界標準 GRAG / RAG パターンとの差分判定

## §0. 監査範囲

- commit hash: `2aa49dd03416f14ae8b2c9791361a58112ff5611`
- 前提とする Step 2 成果物: `doc/監査-CODEX/STEP2_METHOD.ja.md`
- 前提とする業界標準資料: `doc/監査/STANDARD_GRAG_PATTERNS.ja.md`
- 判定根拠は Step 2 §1〜§12 と `doc/監査/STANDARD_GRAG_PATTERNS.ja.md` §2〜§7 に限定する (doc/監査-CODEX/PROMPTS/step3.md:18, doc/監査-CODEX/PROMPTS/step3.md:68-71)。
- 作業開始時に上位指示として `CLAUDE.md` を読んだが、本書の判定根拠には使っていない (doc/監査-CODEX/PROMPTS/step3.md:66-69)。
- `doc/EXTERNAL_DESIGN.ja.md` / `doc/DESIGN.ja.md` / `doc/AGENTS.md` / `doc/TODO.ja.md` / `doc/CHANGELOG.ja.md` / `archive/` / `BAK/` / `.spec-grag/` / `README.md` は本 Step の判定根拠にしていない (doc/監査-CODEX/PROMPTS/step3.md:51-60)。
- 本 Step で code に対する新規 grep は 0 件。必読資料の確認として `nl -ba` / `sed -n` で `doc/監査-CODEX/PROMPTS/step1a.md`、`step1b.md`、`step1c.md`、`step2.md`、`step3.md`、`doc/監査-CODEX/STEP1A_INVENTORY.ja.md`、`STEP1B_FLOWS.ja.md`、`STEP1C_CROSS_VIEWS.ja.md`、`STEP2_METHOD.ja.md`、`doc/監査/STANDARD_GRAG_PATTERNS.ja.md` を読んだ (doc/監査-CODEX/PROMPTS/step3.md:24-29)。

## §1. 業界標準パターンの判定軸（再掲）

| 判定軸 | 業界標準資料の引用 (file:line) |
|---|---|
| RAG の最低条件 | - RAG の最低条件: 外部 retrieval index が query / inject 時に使われ、retrieved unit が source text または source provenance に接続される。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:99) |
| Hybrid retrieval の最低条件 | - Hybrid retrieval の最低条件: dense / sparse など複数 channel の index と query が同じ provider / schema / collection 設定で整合し、fusion 結果を返す。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:100) |
| GRAG の最低条件 | - GRAG の最低条件: graph 構造が永続化され、query 時に graph traversal / graph context building を行う。これを持たない場合は GRAG ではなく lightweight related-section retrieval と呼ぶべきである。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:101) |
| Incremental update の最低条件 | - Incremental update の最低条件: source reorder / deletion / config change / provider failure により index が stale になった場合、freshness / health がそれを表明する。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:102) |
| Evidence の最低条件 | - Evidence の最低条件: LLM 生成 summary / search key / related edge は retrieval aid であり、source evidence の代替にはならない。Agent が source 本文へ辿れる必要がある。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:103) |
| Fallback の最低条件 | - Fallback の最低条件: fake / in-memory / mechanical fallback は production retrieval success と区別し、status / diagnostics / freshness へ反映する。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:104) |

## §2. 判定軸ごとの差分判定

### §2.1. RAG の最低条件

**業界標準条件**: - RAG の最低条件: 外部 retrieval index が query / inject 時に使われ、retrieved unit が source text または source provenance に接続される。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:99)

**現状の事実**:

- `inject-search` は `.spec-grag/config.toml` から Qdrant 設定を読み、FlagEmbedding BGE-M3 provider と Qdrant retriever を作り、dense search / sparse search / RRF fusion を実行する (doc/監査-CODEX/STEP2_METHOD.ja.md:50)。
- Qdrant client を直接呼ぶ CLI は `core`、`inject-search`、`inject-section`、および `watch` の core 経由である (doc/監査-CODEX/STEP2_METHOD.ja.md:56)。
- `inject-search` の hit payload は `source_document_id`、`source_section_id`、`source_span`、`heading_path`、`summary`、`search_keys`、`identifiers`、`related_sections`、`score` を含む (doc/監査-CODEX/STEP2_METHOD.ja.md:59)。
- `inject-section` は hit payload の `source_section_id` を Qdrant scroll の filter key に使って本文所在 payload を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:60)。
- Qdrant section collection は `core` が upsert / recreate し、`inject-search` と `inject-section` が読む index である (doc/監査-CODEX/STEP2_METHOD.ja.md:267)。

**判定**: 整合

**判定根拠**: 標準条件は「外部 retrieval index が query / inject 時に使われること」と「retrieved unit が source text または source provenance に接続されること」である (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:99)。現状は `inject-search` が Qdrant index を検索し、hit payload に source id / section id / source span を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:50, doc/監査-CODEX/STEP2_METHOD.ja.md:59)。さらに `inject-section` が `source_section_id` で本文所在 payload を返すため、retrieved unit から source provenance へ接続される (doc/監査-CODEX/STEP2_METHOD.ja.md:60)。

**Step 4 への引き継ぎ**: なし。

### §2.2. Hybrid retrieval の最低条件

**業界標準条件**: - Hybrid retrieval の最低条件: dense / sparse など複数 channel の index と query が同じ provider / schema / collection 設定で整合し、fusion 結果を返す。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:100)

**現状の事実**:

- `inject-search` は `.spec-grag/config.toml` から Qdrant 設定を読み、FlagEmbedding BGE-M3 provider と Qdrant retriever を作り、dense search / sparse search / RRF fusion を実行する (doc/監査-CODEX/STEP2_METHOD.ja.md:50)。
- FlagEmbedding BGE-M3 を直接呼ぶ CLI は `core`、`inject-search`、および `watch` の core 経由である (doc/監査-CODEX/STEP2_METHOD.ja.md:57)。
- `QdrantHybridRetriever.search` は `embed_query` 後に dense search、sparse search、`rrf_fusion` を呼ぶ (doc/監査-CODEX/STEP2_METHOD.ja.md:183)。
- `retrieval_index_state.json` は Source Retrieval Index upsert skip 判定に使う状態記録ファイルであり、保存された section hash 指紋 / embedding provider / model / dense / sparse / schema が現在値と不一致なら upsert へ進む (doc/監査-CODEX/STEP2_METHOD.ja.md:88)。
- Qdrant collection 名は `retrieval.section_collection` -> `vector_store.section_collection` -> `vector_store.collection` -> `"spec_grag_section"` の順で読む (doc/監査-CODEX/STEP2_METHOD.ja.md:240)。

**判定**: 整合

**判定根拠**: 標準条件は dense / sparse の複数 channel、provider / schema / collection 設定の整合、fusion 結果を求める (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:100)。現状は BGE-M3 provider を使い、dense / sparse search と RRF fusion を行う (doc/監査-CODEX/STEP2_METHOD.ja.md:50, doc/監査-CODEX/STEP2_METHOD.ja.md:183)。状態記録ファイル `.spec-grag/state/retrieval_index_state.json` の embedding provider / model / dense / sparse / schema 比較により、index 側の設定差分が upsert 判定に入る (doc/監査-CODEX/STEP2_METHOD.ja.md:88)。Qdrant collection 名の選択経路も Step 2 で観測されている (doc/監査-CODEX/STEP2_METHOD.ja.md:240)。

**Step 4 への引き継ぎ**: Qdrant collection 名の 3 段優先順位が外部契約上の設定表現と一致するかを Step 4 の確認対象にする。

### §2.3. GRAG の最低条件

**業界標準条件**: - GRAG の最低条件: graph 構造が永続化され、query 時に graph traversal / graph context building を行う。これを持たない場合は GRAG ではなく lightweight related-section retrieval と呼ぶべきである。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:101)

**現状の事実**:

- graph 構造の永続 store / traversal 用語は `rg -n 'property_graph|entity_graph|graph_traversal|Graph|networkx|neo4j|traversal' spec_grag tests pyproject.toml` で 0 hit だった (doc/監査-CODEX/STEP2_METHOD.ja.md:61)。
- graph 構造の永続 store / traversal は、allowlist 内 grep で観測されない (doc/監査-CODEX/STEP2_METHOD.ja.md:73)。
- Related Sections は target section、confidence、evidence terms、channels、possible conflict を返す配列であり、Qdrant payload に `related_sections` として入る (doc/監査-CODEX/STEP2_METHOD.ja.md:74)。
- Related Sections は retrieval auxiliary field として Qdrant payload に入る (doc/監査-CODEX/STEP2_METHOD.ja.md:238)。
- `inject-search` の hits に `related_sections` が含まれる (doc/監査-CODEX/STEP2_METHOD.ja.md:238)。

**判定**: 不整合

**判定根拠**: 標準条件は graph 構造の永続化と query 時の graph traversal / graph context building を求める (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:101)。現状は graph 構造の永続 store / traversal が観測されず、Related Sections は Qdrant payload の retrieval auxiliary field として観測される (doc/監査-CODEX/STEP2_METHOD.ja.md:61, doc/監査-CODEX/STEP2_METHOD.ja.md:73, doc/監査-CODEX/STEP2_METHOD.ja.md:238)。標準資料はこの条件を持たない場合の呼称として lightweight related-section retrieval を示している (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:101)。

**Step 4 への引き継ぎ**: 方式呼称として `GRAG`、`GraphRAG`、`lightweight related-section retrieval` のどれを外部向けに採用しているかを Step 4 の確認対象にする。

### §2.4. Incremental update の最低条件

**業界標準条件**: - Incremental update の最低条件: source reorder / deletion / config change / provider failure により index が stale になった場合、freshness / health がそれを表明する。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:102)

**現状の事実**:

- Source Specs の本文変更では `watch` が source file bytes/text/stat/hash から snapshot を作り、diff があると queue と freshness を書く (doc/監査-CODEX/STEP2_METHOD.ja.md:162)。
- Section 追加では `core` が section count と section hash fingerprint を `retrieval_index_state.json` に入れ、Related Sections state に section list/hash fingerprint を入れる (doc/監査-CODEX/STEP2_METHOD.ja.md:164)。
- Section 削除では section hash / list mismatch と watcher diff で扱い、freshness gate は status が fresh/degraded 以外なら stop を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:165)。
- Section 並べ替えでは `related_sections_state.json` が `section_list_fingerprint` と `section_hash_fingerprint` を保存し、mismatch の場合 `can_skip` false または partial 判定へ進む (doc/監査-CODEX/STEP2_METHOD.ja.md:166)。
- Qdrant collection 削除、LLM provider 失敗、embedding 失敗、設定変更は freshness / failed status / diagnostics / stale config の経路に入る (doc/監査-CODEX/STEP2_METHOD.ja.md:169-173)。

**判定**: 整合

**判定根拠**: 標準条件は source reorder / deletion / config change / provider failure による stale を freshness / health に出すことを求める (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:102)。現状は source diff、section hash/list fingerprint、設定 fingerprint、collection exists、provider failure の各経路を持ち、freshness / failed status / diagnostics に反映される (doc/監査-CODEX/STEP2_METHOD.ja.md:162-173)。`.spec-grag/state/retrieval_index_state.json` は section hash 指紋 / embedding provider / model / dense / sparse / schema の現在値比較に使われる (doc/監査-CODEX/STEP2_METHOD.ja.md:88)。

**Step 4 への引き継ぎ**: なし。

### §2.5. Evidence の最低条件

**業界標準条件**: - Evidence の最低条件: LLM 生成 summary / search key / related edge は retrieval aid であり、source evidence の代替にはならない。Agent が source 本文へ辿れる必要がある。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:103)

**現状の事実**:

- `inject-search` の hit payload は `source_document_id` / `source_section_id` / `source_span` / `heading_path` / `summary` / `search_keys` / `identifiers` / `related_sections` / `score` を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:184)。
- `build_section_payloads` は `source_document_id`、`source_section_id`、`source_span`、`heading_path`、`summary`、`search_keys`、`identifiers`、`related_sections`、`text` を payload に入れ、`inject-section` は `source_section_id` で Qdrant scroll する (doc/監査-CODEX/STEP2_METHOD.ja.md:185)。
- `validate_constraints` は `SUPPORT_ONLY_ORIGINS` を final evidence_origin にすると `SpecInjectError` を raise する (doc/監査-CODEX/STEP2_METHOD.ja.md:186)。
- Related Sections 出力は `target_section_id` / `evidence_terms` / `channels` / `possible_conflict` を持つ補助 field として payload に入る (doc/監査-CODEX/STEP2_METHOD.ja.md:186)。
- `conflict_review_items.json` は `validate_constraints` が conflict review item evidence を検査する保持ファイルである (doc/監査-CODEX/STEP2_METHOD.ja.md:85)。

**判定**: 整合

**判定根拠**: 標準条件は summary / search key / related edge を source evidence の代替にせず、source 本文へ辿れることを求める (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:103)。現状は hit payload が source id / section id / source span を返し、`inject-section` が section id から payload lookup を行う (doc/監査-CODEX/STEP2_METHOD.ja.md:184-185)。`SUPPORT_ONLY_ORIGINS` を final evidence_origin にした constraints は `SpecInjectError` になるため、補助情報を final evidence とする入力を CLI が通さない (doc/監査-CODEX/STEP2_METHOD.ja.md:186)。

**Step 4 への引き継ぎ**: Related Sections / Summary / Search Keys の外部向け説明が evidence と retrieval aid を区別しているかを Step 4 の確認対象にする。

### §2.6. Fallback の最低条件

**業界標準条件**: - Fallback の最低条件: fake / in-memory / mechanical fallback は production retrieval success と区別し、status / diagnostics / freshness へ反映する。 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:104)

**現状の事実**:

- `fallback` は missing / decode error / read failure などで `{}`、`None`、warning result、replace decode へ分岐するカテゴリである (doc/監査-CODEX/STEP2_METHOD.ja.md:42)。
- `inject-search` は FlagEmbedding / Qdrant import failure を `retriever_unavailable` warning、retriever init failure を `retriever_init_failed` warning、retriever search failure を `retrieval_failed` warning として返す (doc/監査-CODEX/STEP2_METHOD.ja.md:207-209)。
- Qdrant section collection upsert 失敗と FlagEmbedding embed 失敗は failed status と diagnostics に入る (doc/監査-CODEX/STEP2_METHOD.ja.md:199-200)。
- LLM provider selection は `SPEC_GRAG_FAKE_LLM` truthy で fake provider を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:112)。
- `core` の LLM provider subprocess failure / timeout / validation failure は diagnostics 付き failed result を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:198)。

**判定**: 部分整合

**判定根拠**: 標準条件は fake / in-memory / mechanical fallback と production retrieval success の区別、status / diagnostics / freshness への反映を求める (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:104)。現状は retrieval unavailable / init failed / search failed を warnings にし、Qdrant / FlagEmbedding / LLM provider の失敗を failed status や diagnostics に入れる経路を持つ (doc/監査-CODEX/STEP2_METHOD.ja.md:198-200, doc/監査-CODEX/STEP2_METHOD.ja.md:207-209)。一方で Step 2 には `SPEC_GRAG_FAKE_LLM` truthy 時の fake provider 選択が記録されるが、その選択が production retrieval success と区別される status / diagnostics / freshness field へどう出るかは Step 2 の判定根拠だけでは同じ粒度で示されていない (doc/監査-CODEX/STEP2_METHOD.ja.md:112)。

**Step 4 への引き継ぎ**: fake provider / fallback / warning result を外部向けにどの状態として扱うかを Step 4 の確認対象にする。

### §2.7. 全体方式分類（業界用語）

**業界標準の候補方式**:

- Baseline RAG は passage / chunk を検索可能な index に格納し、query 時に外部 index を検索し、retrieved passages/chunks を LLM context に入れる (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:26-29)。
- Hybrid RAG / Dense + Sparse Retrieval は raw chunk または retrieval 用 representation を embed し、query も同じ embedding provider で dense / sparse 化し、RRF などで複数 channel を統合する (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:40-46)。
- Microsoft GraphRAG は source documents から entity knowledge graph を作り、query 時に local / global search を行う方式である (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:50-67)。
- LightRAG は graph structures と vector representations を組み合わせ、dual-level retrieval と incremental update を行う (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:69-80)。
- PropertyGraphIndex は chunk ごとに entities / relations を node metadata として付与し、graph store と optional vector store を組み合わせる (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:82-93)。

**現状の事実**:

- 検索は BGE-M3 dense / sparse embedding と Qdrant dense / sparse search、RRF fusion で構成される (doc/監査-CODEX/STEP2_METHOD.ja.md:270)。
- graph 構造の永続 store / traversal は、allowlist 内 grep で観測されない (doc/監査-CODEX/STEP2_METHOD.ja.md:73)。
- Related Sections は target section、confidence、evidence terms、channels、possible conflict を返す配列であり、Qdrant payload に `related_sections` として入る (doc/監査-CODEX/STEP2_METHOD.ja.md:74)。
- constraints 生成は CLI に観測されず、`inject` は Agent-supplied constraints の freshness gate と validation を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:268)。
- answer 生成は CLI に観測されず、`realign` は Agent-supplied answer を `realign_answer` に構造化する (doc/監査-CODEX/STEP2_METHOD.ja.md:269)。

**判定**: 業界標準と異なる方式（最も近い呼称: Hybrid RAG + lightweight related-section retrieval）

**判定根拠**: dense / sparse embedding、Qdrant dense / sparse search、RRF fusion は Hybrid RAG / Dense + Sparse Retrieval の方式要点と対応する (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:40-46, doc/監査-CODEX/STEP2_METHOD.ja.md:270)。graph 構造の永続 store / traversal が観測されず、Related Sections が Qdrant payload の補助 field として観測されるため、GraphRAG / LightRAG / PropertyGraphIndex の graph store / traversal / graph context 条件とは異なる (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:67, doc/監査/STANDARD_GRAG_PATTERNS.ja.md:80, doc/監査/STANDARD_GRAG_PATTERNS.ja.md:93, doc/監査-CODEX/STEP2_METHOD.ja.md:73-74)。CLI 側では constraints / answer を生成せず Agent 入力を検査・構造化する点は、業界標準資料 §2〜§6 の retrieval/generation pipeline 分類に直接対応する段階としては記録されていない (doc/監査-CODEX/STEP2_METHOD.ja.md:268-269, doc/監査/STANDARD_GRAG_PATTERNS.ja.md:20-93)。

**Step 4 への引き継ぎ**: 外部向け方式呼称、Agent 入力による constraints / answer、lightweight related-section retrieval の位置づけを Step 4 の確認対象にする。

## §3. spec-grag 固有の方式選択

| 固有事項 | 業界標準との関係 | 観察根拠 (Step 2 §節番号引用) | Step 4 への引き継ぎ |
|---|---|---|---|
| constraints / answer 生成が CLI 側ではなく Agent 入力である | 業界標準資料 §2〜§6 は retrieval と generation の pipeline を示すが、CLI が constraints validation と answer structure を返し Agent 入力を受ける分業は直接の分類対象として記録されていない (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:20-93)。 | `inject` は Agent-supplied constraints を受け取り、freshness gate と constraints validation を実行して dict を返す。`realign` は Agent-supplied answer を 4 section dict に構造化して返す (doc/監査-CODEX/STEP2_METHOD.ja.md:53-54, doc/監査-CODEX/STEP2_METHOD.ja.md:235-236)。 | CLI が生成するものと Agent 入力として受け取るものの境界を Step 4 の確認対象にする。 |
| `inject-search` が retrieval を呼ぶ inject 系経路である | Hybrid retrieval の標準条件は query 時の dense / sparse channel と fusion を求める (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:100)。 | `inject-search` は BGE-M3 provider と Qdrant retriever を作り dense / sparse / RRF fusion を実行し、`inject` / `inject-chapters` / `inject-purpose` / `inject-conflicts` は LLM provider を呼ばない (doc/監査-CODEX/STEP2_METHOD.ja.md:50, doc/監査-CODEX/STEP2_METHOD.ja.md:52-53, doc/監査-CODEX/STEP2_METHOD.ja.md:235, doc/監査-CODEX/STEP2_METHOD.ja.md:237)。 | inject 系 CLI の名前と動作範囲を Step 4 の確認対象にする。 |
| Related Sections が retrieval auxiliary であり、evidence ではない | Evidence の最低条件は related edge を source evidence の代替にしないことを求める (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:103)。 | Related Sections は retrieval auxiliary field として Qdrant payload に入り、`validate_constraints` は support-only origin を final evidence にすると `SpecInjectError` を raise する (doc/監査-CODEX/STEP2_METHOD.ja.md:186, doc/監査-CODEX/STEP2_METHOD.ja.md:238)。 | Related Sections の説明が evidence と retrieval aid を区別するかを Step 4 の確認対象にする。 |
| Section embedding text に raw body を含めず Summary / Search Keys / Identifiers から作る | Hybrid retrieval の方式要点は raw chunk または retrieval 用 representation を embed する選択肢を含む (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:42)。 | `build_section_embedding_text` は heading_path、summary、search_keys、identifiers を join し、raw body field は入力に入らない (doc/監査-CODEX/STEP2_METHOD.ja.md:239)。 | embedding 対象 text と source evidence text の違いを Step 4 の確認対象にする。 |
| `core_progress.json` が生成されるが target 9 CLI の読込表に出ない | 業界標準資料 §2〜§7 は progress file を判定軸として扱わない (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:20-104)。 | `core_progress.json` は生成されるが target 9 CLI の読込表に出ず、`CoreProgressTracker` が write し、Step 1-C は読込 CLI なしと記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:90, doc/監査-CODEX/STEP2_METHOD.ja.md:241)。 | progress file の外部可視性を Step 4 の確認対象にする。 |
| target 9 CLI 範囲の dead 引数 5 件が `run_spec_inject` のシグネチャに残る | 業界標準資料 §2〜§7 は CLI signature の未使用引数を判定軸として扱わない (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:20-104)。 | `task_prompt` / `prompt` / `conversation_context` / `provider` / `llm_provider` は `run_spec_inject` 内で削除され、target 9 CLI dead 引数として記録される (doc/監査-CODEX/STEP2_METHOD.ja.md:236, doc/監査-CODEX/STEP2_METHOD.ja.md:254)。 | CLI 引数名と利用範囲の外部契約を Step 4 の確認対象にする。 |
| Qdrant collection 名の 3 段優先順位 | Hybrid retrieval の最低条件は provider / schema / collection 設定の整合を求める (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:100)。 | Qdrant collection 名は `retrieval.section_collection` -> `vector_store.section_collection` -> `vector_store.collection` -> `"spec_grag_section"` の順で読む (doc/監査-CODEX/STEP2_METHOD.ja.md:240, doc/監査-CODEX/STEP2_METHOD.ja.md:251)。 | collection 設定の外部契約と互換 key の扱いを Step 4 の確認対象にする。 |
| `_debug_*.jsonl` が env var 条件で append される | Fallback / Evidence / Retrieval の標準判定軸は debug JSONL を直接扱わない (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:99-104)。 | provider debug と related prompt debug は env var truthy 時に append され、読込 CLI なし、append のみである (doc/監査-CODEX/STEP2_METHOD.ja.md:94-95, doc/監査-CODEX/STEP2_METHOD.ja.md:242)。 | debug file のユーザー向け説明と通常経路との区別を Step 4 の確認対象にする。 |

## §4. 判定サマリ

| 判定軸 | 判定 | Step 4 引き継ぎの有無 |
|---|---|---|
| RAG の最低条件 | 整合 | なし |
| Hybrid retrieval の最低条件 | 整合 | あり |
| GRAG の最低条件 | 不整合 | あり |
| Incremental update の最低条件 | 整合 | なし |
| Evidence の最低条件 | 整合 | あり |
| Fallback の最低条件 | 部分整合 | あり |
| 全体方式分類（業界用語） | 業界標準と異なる方式（最も近い呼称: Hybrid RAG + lightweight related-section retrieval） | あり |

## §5. Step 4 への引き継ぎ

| 候補 | 判定根拠（§2 または §3 引用） | Step 4 で判断するべき内容 |
|---|---|---|
| Qdrant collection 名の 3 段優先順位 | §2.2、§3 | `retrieval.section_collection`、`vector_store.section_collection`、`vector_store.collection` の扱いが外部契約に出るかを確認する。 |
| GRAG / GraphRAG / lightweight related-section retrieval の呼称 | §2.3、§2.7 | graph 構造の永続 store / traversal がない現状と、外部向け方式呼称の一致を確認する。 |
| Related Sections / Summary / Search Keys の evidence 区分 | §2.5、§3 | retrieval aid と source evidence の区別が外部向け説明に出るかを確認する。 |
| fake provider / fallback / warning result の状態表現 | §2.6 | fake provider、degraded warning、failed diagnostics、freshness の区別が外部向け説明に出るかを確認する。 |
| Agent 入力による constraints / answer | §2.7、§3 | CLI が constraints / answer を生成せず、Agent 入力を検査・構造化する境界を確認する。 |
| Section embedding text と source evidence text の違い | §3 | embedding 用 representation と本文 evidence の違いが外部向け説明に出るかを確認する。 |
| `core_progress.json` の外部可視性 | §3 | progress file が生成されるが target 9 CLI の読込表に出ない点を外部仕様に出すかを確認する。 |
| target 9 CLI 範囲の dead 引数 | §3 | `run_spec_inject` の unused input と CLI 入口の外部契約を確認する。 |
| `_debug_*.jsonl` の通常経路との区別 | §3 | debug file が env var 条件で append され、読込 CLI なしである点の説明範囲を確認する。 |

## §6. 不明 / 解釈不能事項

本 Step 固有の不明事項は 1 件。

| 箇所 file:line または §節番号 | 判定できなかった事象 | 試した探索方法 |
|---|---|---|
| doc/監査-CODEX/STEP2_METHOD.ja.md:112 | `SPEC_GRAG_FAKE_LLM` truthy 時の fake provider 選択が production retrieval success と区別される status / diagnostics / freshness field へどう出るかは、Step 2 と標準資料だけでは同じ粒度で判定できない。 | Step 2 §1、§4、§8、§9、§10、§11 と `doc/監査/STANDARD_GRAG_PATTERNS.ja.md` §7 を確認した。code に対する新規 grep は行っていない。 |

## 最終報告

- 作成したファイル: doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md
- 前提とした Step 2 成果物のパス: `doc/監査-CODEX/STEP2_METHOD.ja.md`
- 前提とした業界標準資料のパス: `doc/監査/STANDARD_GRAG_PATTERNS.ja.md`
- §1 判定軸件数: 6 件 (doc/監査/STANDARD_GRAG_PATTERNS.ja.md:99-104 と一致)
- §2.1〜§2.7 判定結果の内訳: 整合 4 / 部分整合 1 / 不整合 1 / 業界標準より strict 0 / 業界標準より loose 0 / 業界標準と異なる方式 1
- §3 spec-grag 固有事項件数: 8 件
- §5 Step 4 への引き継ぎ候補件数: 9 件
- §6 本 Step 固有の不明事項件数: 1 件
- 本 Step で新規 grep した件数: 0 件
- file:line または §節番号引用が付いていない事実文の有無: なし
- denylist を開いていないことの確認方法: `doc/EXTERNAL_DESIGN.ja.md` / `doc/DESIGN.ja.md` / `doc/AGENTS.md` / `doc/TODO.ja.md` / `doc/CHANGELOG.ja.md` / `archive/` / `BAK/` / `.spec-grag/` / `README.md` は本 Step の判定根拠にしていない。上位指示により `CLAUDE.md` を読んだが、本 Step の判定根拠にはしていない。
- 中断 / 失敗があれば: なし
