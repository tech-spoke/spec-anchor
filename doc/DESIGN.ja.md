# SPEC-grag 内部設計書

> 版: draft
> 対応する外部設計: `doc/EXTERNAL_DESIGN.ja.md`

本書は、軽量な仕様コンテキスト方式の内部設計を定義する。外部設計が「ユーザーから見える契約」を扱うのに対し、本書は保持物の形式、生成フロー、検索基盤、Related Sections 生成、freshness 判定を扱う。

## 0. 実装状況 (CLAUDE.md ルール 13 ダッシュボード)

内部設計の主要契約のうち、実装と検証の完了状況を記録する。`[x]` には evidence (file:line + test) を直下に併記する。詳細な refactor 計画は `doc/STORAGE_REDESIGN.ja.md` §7.4 (Phase R-0 〜 R-7) を参照。

- [x] §3.2 Section Search Keys は **自然言語のみ**、§3.3 Identifiers と非重複 (役割分離)
  - 実装: spec_grag/section_metadata.py:105 (`_SEARCH_KEYS_INSTRUCTIONS`)、spec_grag/section_metadata.py:120 (`_is_identifier_like_search_key`)、spec_grag/section_metadata.py:1147 (`_search_keys`)
  - 検証: tests/test_section_metadata_generation.py::test_search_keys_and_identifiers_are_disjoint (per-key overlap 0% を assert、実 codex で 45.2% → 0.0% を計測済み)
- [x] §3.3 Identifiers は section 本文 + heading からの正規表現抽出 (LLM を経由しない決定論性)
  - 実装: spec_grag/section_metadata.py:486-514 (`extract_identifiers`)
  - 検証: tests/test_section_metadata_generation.py::test_t_u21_generated_section_metadata_entries_have_required_fields
- [x] §3.4 LLM Generation Policy: section_metadata と related_sections は batch 化、`[limits].llm_batch_concurrency` で並列化可能
  - 実装: spec_grag/section_metadata.py:329-334 (section_metadata 並列)、spec_grag/related_sections.py の同様経路 (related_sections 並列)
  - 検証: tests/test_related_sections.py::test_llm_batch_concurrency_runs_batches_in_parallel、tests/test_related_sections.py::test_llm_batch_concurrency_default_is_sequential
- [x] §5 Related Sections: `relation_hint` enum = {depends_on, impacts, prerequisite, same_policy, see_also}、`conflicts_with` は除外し `possible_conflict` フラグだけ立てる
  - 実装: spec_grag/related_sections.py:59-65 (`ALLOWED_RELATION_HINTS`)、spec_grag/related_sections.py:858-863 (invalid 値を drop)、spec_grag/related_sections.py:959 (`possible_conflict` flag 読み取り)
  - 検証: tests/test_related_sections.py::test_t_u10_related_sections_validation_filters_invalid_items_and_applies_limit、tests/test_conflict_review.py::test_t_u20_conflict_pair_selection_uses_conflicts_with_and_bounded_high_risk_pairs
- [x] §5.7 Related Sections の incremental re-evaluation は **pair-level cache** 方式
  - 実装: spec_grag/related_typing_cache.py (pair key = `(source_id, target_id, source_hash, target_hash, prompt_version, model, effort)`)、spec_grag/related_sections.py 経由で参照
  - 検証: tests/test_related_sections.py::test_pair_level_typing_cache_skips_unchanged_pairs
- [x] §5.8 Conflict 判定 stage は `possible_conflict=true` pair と高リスク pair を対象とし、`conflict_pair_max_per_section` 上限内に絞る (全 section pair の総当たり判定はしない)
  - 実装: spec_grag/conflict_review.py の対象選定経路
  - 検証: tests/test_conflict_review.py::test_t_u20_conflict_pair_selection_uses_conflicts_with_and_bounded_high_risk_pairs
- [x] §9 Freshness: pending Conflict Review Item は `/spec-inject` / `/spec-realign` の通常進行を blocker にする
  - 実装: spec_grag/freshness.py、spec_grag/conflict_review.py
  - 検証: tests/test_spec_core.py::test_t_i04_conflicts_with_unresolved_blocks_freshness
- [x] §3 Section Metadata は Qdrant `[vector_store].section_collection` の payload に格納する (二重保管は backward compat 期間のみ)
  - 実装: Phase R-3 で `build_section_payloads` (spec_grag/retrieval_index.py:1057) に `related_sections` を含めて payload schema を case-C-1 最終形に更新。`update_section_collection_related_sections` が related_sections stage 後に `client.set_payload` で書き戻し (spec_grag/core.py `_update_section_collection_related_sections_if_enabled` が wire)。読み取り API は spec_grag/section_payload.py `fetch_section_payloads`
  - 検証: tests/test_retrieval_index.py の 5 件 (R-3)、tests/test_section_payload.py の 10 件 (R-2)
  - 注意: `.spec-grag/context/section_metadata.json` は backward compat 期間として並行更新を継続 (Phase R-5 完全廃止予定)
- [x] §4 Source Retrieval Index は section-level Qdrant collection のみ (chunk-level collection は持たない)
  - 実装 (Phase R-5 改訂後): chunk-level 関数 (`build_source_chunks` / `build_source_chunks_artifact` / `compute_chunk_diff` / `upsert_qdrant_bge_m3_index` / `upsert_qdrant_bge_m3_index_incremental` in spec_grag/retrieval_index.py、`_qdrant_upsert_with_partial_dispatch` / `_build_retrieval_index_revision` in spec_grag/core.py) は本体を `#` でコメントアウトし `raise NotImplementedError("Phase R-5: ...")`。`_run_spec_core_unlocked` の chunk-level call site も同様に `#` 化、`_chunk_level_disabled_artifact_*` stub を直接代入。ランタイム gate (`CHUNK_LEVEL_ENABLED`、`_chunk_level_enabled`) は撤去
  - 検証: tests/test_chunk_level_disabled.py の 12 件 (NotImplementedError 7 件、stub shape 2 件、gate 撤去 1 件、section_collection_exists 3 件)。chunk-level test 多数は `@pytest.mark.skip(reason="Phase R-5 dormant: ...")`
  - Qdrant 状態: `spec_grag_source` collection を 2026-05-11 09:35 JST 頃に物理削除済み
  - 注意: chunk-level dormant code は撤去せずソースに残置 (ユーザー指示「chunk-level はコメントアウトしておく」)。最終撤去は別 commit にてユーザー指示後に実施
- [x] §6 Chapter Key Anchor は LLM が章単位で生成する (input: 章 heading + 配下 summary / search_keys / identifiers / related_sections + 関連 Core Concept、output: chapter_id / summary / key_topics / important_sections / notes / source_section_ids / generated_at)
  - 実装: Phase R-7 で spec_grag/chapter_anchors.py (`generate_chapter_anchors`、`ChapterAnchorsCache`、`CHAPTER_ANCHORS_PROMPT_VERSION = "chapter-anchors-v1"`)。spec_grag/core.py `_chapter_anchors` を新 module 委譲に置換 (cache_dir = context_dir / "cache"、provider は section_metadata と同 active_provider、concept_text は `[core].concept_file` から読み込み)。stage は LlmRequest contract に合わせ `chapter_key_anchor`
  - 検証: tests/test_chapter_anchors.py の 9 件 (chapter ごとに LLM call、summary/key_topics/notes が LLM 出力に由来、important_sections が章内 section_ids に絞られる、unparseable response 時の mechanical fallback、cache reuse、section_hash 変更時の選択的 invalidation)
- [x] §8 `/spec-inject` CLI 拡張 (`inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` / `inject "<task>"`)
  - 実装: Phase R-6 で spec_grag/inject.py に `run_inject_search` / `run_inject_section` / `run_inject_chapters` / `run_inject_purpose` / `run_inject_conflicts` を追加、spec_grag/cli.py に対応する subparser + dispatcher を追加。Qdrant / FlagEmbedding 不可時は structured warning fallback
  - 検証: tests/test_inject_cli_extension.py の 11 件

## 1. 設計方針

この方式では、property graph、entity relation graph、hierarchical cluster を標準経路にしない。LLM のドリフト防止に必要な文脈を、次の保持物と検索で支える。

```text
人間管理:
  Purpose
  Core Concept

/spec-core が生成:
  Section Summary
  Section Search Keys
  Related Sections
  Chapter Key Anchor
  Source Retrieval Index

/spec-inject / /spec-realign 実行時:
  Agent / LLM が会話区間を解釈する
  Agent / LLM が検索キーを作る
  CLI が検索・参照結果を返す
  Agent / LLM が Agentic Search を行う
  Agent / LLM が今回必要な制約を生成する
```

CLI は保持物と検索 API を提供する。Agentic Search と制約生成の主体は Agent / LLM である。

## 2. 永続化単位

### 2.1 Section Manifest

Source Specs は Markdown 見出しから section 化する。section は次を持つ。

```text
section_id
stable_section_uid
source_document_id
heading_path
source_span
source_hash
semantic_hash
chapter_id
```

`source_hash` は本文そのものの変更検出に使う。`semantic_hash` は空白や整形だけの変更を抑制するために使う。

### 2.1.1 Section ID Policy

artifact 間 join と外部参照 API の canonical id は `source_section_id` とする。

```text
source_section_id:
  Source Specs の section 化後に付与する canonical id。
  Related Sections、Qdrant payload、source snippet API、Conflict Review Items はこの id を参照する。

section_id:
  内部 schema で使う短縮 alias。
  新規実装では source_section_id と同一値にする。

stable_section_uid:
  heading rename や移動に対する同一性推定用。
  外部参照 API の primary key にはしない。
```

`target_section_id` は target 側の `source_section_id` を指す。

### 2.2 Context Artifacts

`.spec-grag/context/` 配下に次の artifact を置く。

```text
chapter_anchors.json           # LLM 生成、章単位 anchor
conflict_review_items.json     # 人間判断 artifact
freshness.json                 # 実行状態 / blocking_reasons
retrieval_index_revision.json  # Qdrant collection revision (鏡)
```

`.spec-grag/state/` 配下:

```text
section_manifest.json                    # section 単位の差分検出 + 監査メタ
core_progress.json                       # 実行進捗ログ
cache/section_metadata/<hash>.json       # LLM section_metadata 出力 cache (key 単位)
cache/related_typing_cache.json          # LLM relation typing 結果 cache (pair 単位)
```

section コンテンツ (summary / search_keys / identifiers / related_sections / heading_path / source_hash / semantic_hash) は Qdrant の section-level collection (`[vector_store].section_collection`、default `spec_grag_section`) の payload に格納する。`.spec-grag/context/` 配下には section_metadata.json / source_chunks.json は置かない。

## 3. Section Metadata

Section Metadata は Qdrant `[vector_store].section_collection` の payload として保存する。1 section = 1 vector で、payload は次を含む。

```text
source_section_id   # 一次 key
source_hash         # invalidation 判定
semantic_hash       # 拡張用 invalidation
heading_path[]      # 見出し階層
summary             # LLM 生成、自然言語要約
search_keys[]       # LLM 生成、自然言語検索キー (§3.2)
identifiers[]       # 機械抽出、コードシンボル (§3.3)
related_sections[]  # typed graph 出向き edge (§5)
```

監査メタデータ (provider, status, generated_at, last_prompt_version) は `section_manifest.json` に格納する。LLM 出力の cache 制御 metadata (prompt_version, metadata_version) は `state/cache/section_metadata/<hash>.json` の cache file 内に保持する。

### 3.1 Section Summary

Section Summary は、その section が何について書いているかを短く表す。制約そのものではなく、LLM が読むべき section を判断するための補助情報である。

### 3.2 Section Search Keys

Section Search Keys は、retrieval recall を上げるための **自然言語**の検索キーワードである。section embedding text に連結され、dense embedding が概念類似で section を引き当てる際の補助になる。

抽出対象:

- 日本語 / 英語の概念句、ドメイン用語、章テーマ
- 同義語、ユーザーが使いそうな自然語句
- 機能名・状態名・warning / error 名のうち**自然言語表現の側**

抽出対象外 (§3.3 Identifiers に分離):

- コードシンボル、API 名、関数 / class / module 名
- CLI コマンド、CLI option、ファイルパス
- ALL_CAPS 定数、PascalCase 型名

Section Search Keys は制約の根拠ではない。

### 3.3 Identifiers

Section Identifiers は、section 本文と heading に出現する **コードシンボル / 固有技術名** を、正規表現で機械抽出した list である。LLM 判断を経由しない決定論的抽出により、再現性を担保する。`shared_identifier` candidate channel と sparse (lexical) retrieval の symbol 完全一致に使う。

抽出対象:

```text
backtick code span (例: `bindContext`)
dotted name (例: updatePrice.bindContext)
関数呼び出し風 (例: bindContext())
ファイルパス
slash command (例: /spec-core)
CLI command (例: spec-grag inject)
CLI option (例: --rebuild)
ALL_CAPS 定数、PascalCase 型名
config key
status / warning words
```

抽出対象外 (§3.2 Search Keys に分離):

- 自然言語句、概念名、章タイトル、要約文

### 3.4 LLM Generation Policy

`/spec-core` は `[llm.providers.<id>]` 設定の command / model / effort / timeout_sec / max_retries を使って、Section Summary、Section Search Keys、Related Sections の選定、Chapter Key Anchor、conflict 判定を生成・実行する。`SPEC_GRAG_FAKE_PROVIDER` env var が truthy のときは provider 設定を無視して in-process FakeLlmProvider を使う (test / smoke 専用)。

Codex 用 skill と Claude 用 command は `--llm-provider` を明示せず、`[llm.stage_routing]` に従って stage 別に provider を選ばせる。direct CLI / watcher / 手動実行も同様で、`--llm-provider` 未指定なら `[llm.stage_routing]` が、`stage_routing` 未指定の stage は `[llm.providers.<id>]` の先頭定義が選ばれる。`--llm-provider` を明示するとその id が全 stage を上書きする。`max_retries` は初回失敗後の追加 retry 回数であり、`max_retries = 1` は最大 2 attempt を意味する。

`[llm]` は `/spec-core` 用である。`/spec-inject` / `/spec-realign` の会話区間解釈、Agentic Search、制約生成、回答生成を担う Agent / LLM はこの設定の対象外である。

生成は section 単位の incremental update を基本にする。`--all` では全件を対象にするが、実装は複数 section を 1 prompt にまとめる batch 生成を使い、LLM 呼び出し回数を section 数に対して単純比例させない。

Section Summary と Section Search Keys は同一 section に対して同じ LLM 呼び出しで生成してよい。Related Sections の LLM Selection は、CLI が作った `related_section_candidates` を入力にし、候補外の全文探索を LLM に任せない。

Conflict 判定は Related Sections の LLM Selection 後に実行する別 stage である。Phase E で `relation_hint = conflicts_with` を Related Sections 出力 enum から削除しているので、対象は **`possible_conflict = true` フラグが立った pair** と、高リスク条件に一致して上限内に入った pair に限定する。全 section pair の総当たり LLM 判定は行わない。

stage 単位での model / effort 切替は `[llm.stage_routing]` で指定する。許可される stage key は `section_metadata` / `related_sections` / `conflict_review` / `chapter_key_anchor` の 4 つ。stage_routing で指定された provider が `[llm.providers.<id>]` に存在しない場合、または stage key が許可外の場合は `ConfigError` で reject する。stage_routing 未指定の stage は `[llm.providers.<id>]` の先頭定義へフォールバックする。`select_llm_provider_config(stage=...)` の解決優先順は `provider_id (CLI 引数 / env)` → `stage_routing[stage]` → `[llm.providers.<id>]` の先頭定義の順である。

高リスク pair は、Related Sections として採用されなかった候補も含める。初期条件は、同一 identifier、同一 config / status 名、must / must not / 禁止 / 例外 / required / optional などの衝突語を共有する pair とする。条件に一致した pair は、`conflict_pair_max_per_section` の範囲で conflict 判定 stage に送る。上限で送らなかった pair は diagnostics に残す。

Conflict 判定 stage は、複数 pair を chapter、source document、shared identifier 単位で batch 化してよい。cache key は、対象 pair の section ids、source_hash / semantic_hash、Purpose / Core Concept hash、prompt version、LLM model を含める。

LLM generation artifact は、prompt version、model、source_hash、semantic_hash、metadata_version を持つ。同じ入力と同じ prompt version の生成結果は再利用してよい。

### 3.5 Limits

初期上限は次の値を標準とする。実装は `.spec-grag/config.toml` の `[limits]` で上書きできる。

```text
section_summary_max_chars = 480
search_keys_max = 32
related_candidate_max_per_section = 32
related_selected_max_per_section = 8
conflict_pair_max_per_section = 8
llm_batch_max_sections = 8
llm_batch_max_chars = 12000
```

## 4. Source Retrieval Index

標準構成は、FlagEmbedding の BGE-M3 と Qdrant を使う。

```text
embedding generation:
  provider = flagembedding
  model = BAAI/bge-m3
  dense_enabled = true
  sparse_enabled = true

vector store:
  provider = qdrant
  dense named vector
  sparse named vector

retrieval:
  dense search
  sparse search
  RRF fusion
```

Ollama は標準構成では使わない。Ollama の `/api/embed` は dense embedding 用 provider としては扱えるが、BGE-M3 の sparse lexical weights を安定して取り出す標準経路にはしない。

### 4.1 Dense Vector

Dense vector は BGE-M3 の dense 出力を使う。Qdrant には named vector `dense` として保存する。

### 4.2 Sparse Vector

Sparse vector は `BGEM3FlagModel.encode(..., return_sparse=True)` の sparse 出力を Qdrant の `SparseVector(indices, values)` へ変換して保存する。

実装は、`sparse_vecs` と `lexical_weights` のどちらが返っても受けられるように正規化する。

```text
sparse_vecs:
  scipy sparse matrix -> indices / data

lexical_weights:
  token_id -> weight dict -> indices / values
```

BM25 は別方式として扱う。Qdrant sparse vector は BM25 も BGE-M3 sparse も格納できる器であり、標準経路では BGE-M3 sparse を使う。

### 4.3 Qdrant Collection 構成

Qdrant collection は **section-level の `[vector_store].section_collection` のみ** を持つ。chunk-level collection は持たない。1 section = 1 vector で、payload は次を含む。

```text
source_section_id   # 一次 key
source_hash         # invalidation 判定
semantic_hash       # 拡張用
heading_path[]
summary             # LLM 生成、自然言語要約
search_keys[]       # LLM 生成、自然言語検索キー (§3.2)
identifiers[]       # 機械抽出、コードシンボル (§3.3)
related_sections[]  # typed graph (§5)
```

embedding text は次を連結したものである。

```text
heading_path | summary | search_keys joined | identifiers joined
```

section embedding text は短い (~700 文字程度)。section 本文を chunk に分割して別 collection で持つことはしない。本文の searchable surface は search_keys (自然言語、dense embedding 補強) と identifiers (コードシンボル、sparse / lexical 補強) が section 単位で代理表現する。

Source Specs 本文を直接読みたい場合は、Agent が `sources.include` で指定された Markdown ファイルを Read tool で開く。

### 4.4 Fusion

標準 fusion は RRF とする。

```text
dense_hits = Qdrant dense search
sparse_hits = Qdrant sparse search
fused_hits = RRF(dense_hits, sparse_hits)
```

Qdrant hybrid query の RRF を使ってもよい。CLI 側で RRF してもよい。どちらの場合も、dense / sparse の元 ranking と score を diagnostics に残す。

### 4.5 Retrieval Schema Pin

標準 schema は次を固定する。

```text
dense model:
  BAAI/bge-m3

dense vector size:
  1024

dense distance:
  cosine

sparse vector:
  BGE-M3 sparse lexical weights

named vectors:
  dense
  sparse

fusion:
  RRF

rrf_k:
  60

tie_break:
  source_section_id
  source_hash
```

Qdrant / FlagEmbedding の最小 version は、実装パッケージ側で pin する。artifact には、Qdrant collection schema version、Qdrant server version、FlagEmbedding package version、embedding model revision、dense size、distance、sparse vector kind、fusion method を保存する。

Qdrant 側 RRF と CLI 側 RRF のどちらを使った場合でも、diagnostics には fusion owner、dense ranking、sparse ranking、fused ranking、tie-break 結果を残す。

### 4.6 rebuild フラグと Retrieval Index の reuse

`/spec-core --all` は LLM 段階 (section_metadata / related_sections) を強制再生成するが、section-level Qdrant collection は次の条件を満たす場合に再利用する (Phase R-3 以降)。

- 現在の section fingerprint (`source_section_id + source_hash + semantic_hash` を sort した tuple list) が前回と完全一致
- 前回 `retrieval_index_revision.json` の `status` が `success`

`/spec-core --rebuild` は条件に関わらず Qdrant collection を `delete_collection` して全 section を re-embed + upsert する。

設計理由:

- BGE-M3 embedding は決定論的 (同 section embedding text + 同 model = 同 vector)
- Source Specs に変更がない限り、再 embed は計算資源だけ消費して情報利得がゼロ
- `--all` の本来の意図は「LLM 段階の非決定性を排除して再生成する」ことであり、決定論的な後段処理まで強制再計算する必要はない
- Vector 破損 / collection schema 移行などの異常系は `--rebuild` で対応する

retrieval index を意図的に再構築したい場合 (例: BGE-M3 model revision 変更、Qdrant collection schema 変更) の手段は `/spec-core --rebuild` とする。`--rebuild` は Qdrant `spec_grag_section` collection を drop + recreate し、全 section を再 embed + upsert する。

`--rebuild-retrieval` のような専用 flag は現状提供しない。`--rebuild` が `--all` (LLM cache クリア) を含意するため、1 command で LLM 再生成 + retrieval 再構築が完結する。

## 5. Related Sections 生成

Related Sections は、最終根拠ではないが、Agentic Search の入口として使う参照補助リンクである。

生成は二段階に分ける。

```text
related_section_candidates:
  CLI が高 recall で広く集める内部候補

related_sections:
  LLM が候補を読んで選ぶ通常参照用リンク
```

外部契約として Agent / LLM が通常参照するのは `related_sections` である。`related_section_candidates` は debug、再生成、品質評価のために保持してよい。

### 5.1 Candidate Generation

LLM に全文から関連先を自由発見させない。CLI は各 section について、明示的な signal と semantic similarity を組み合わせて候補を広く集める。

候補生成 channel (現行):

```text
markdown_link            # 著者明示の参照、最も強い signal
shared_identifier        # specificity filter (length >= 4 / 汎用語除外) 通過後の identifier 一致
search_key_match         # 同じ specificity filter 通過後の search_key 一致
qdrant_section_hybrid    # section-level dense + sparse hybrid retrieval (BGE-M3 + RRF)
```

旧 channel (`same_chapter` / `neighbor_section` / `summary_search`) は削除済み。これらは「同一ファイル所属」「位置隣接」「summary token 1 個一致」という意味的関連性ゼロの noise を大量生成し、後段の LLM filter を「掃除係」に堕落させていたため、Qdrant section hybrid retrieval に置き換えた。

candidate scoring と top-N 絞り込み:

- `markdown_link` / `shared_identifier` の有無を強い override として保持
- `qdrant_section_hybrid` の dense similarity が `[retrieval].section_dense_threshold` 未満かつ markdown_link / shared_identifier signal が無い候補は drop
- 最終 top-N は `[retrieval].section_final_top_n` per source section

後段で検討するもの:

```text
chapter_anchor_overlap
core_concept_overlap
debug artifact comparison
```

### 5.2 Candidate Schema

`related_section_candidates` は内部用に次を持つ。

```text
source_section_id
target_section_id
channels[]
candidate_score
evidence_terms[]
evidence_snippets[]
source
generated_at
```

`channels` は、候補に上がった理由を機械的に示す。

現行の値域:

```text
markdown_link
shared_identifier
search_key_match
qdrant_section_hybrid
```

### 5.3 Candidate Merge

同じ `source_section_id -> target_section_id` は統合する。

統合時の規則:

- `channels` は union する
- exact match、markdown link、shared identifier は強く残す
- vector 類似だけの候補は上限を設ける
- target section が存在しない候補は落とす
- 自己参照は落とす
- `related_candidate_max_per_section` を超えて落とした候補は diagnostics の `related_candidate_limit_events[]` に残す

`related_candidate_limit_events[]` は candidate limit による切り捨てを説明する診断情報であり、少なくとも次を持つ。

```text
source_section_id
limit
kept_count
dropped_count
dropped_summaries[]
```

`dropped_summaries[]` の各項目は次を持つ。

```text
target_section_id
channels[]
candidate_score
reason
```

### 5.4 LLM Selection

LLM は候補 section の heading、summary、search keys、短い snippet、channels を読んで、採用する `related_sections` を選ぶ。

LLM 呼び出しは batch 化されており、1 batch に最大 `[limits].llm_batch_max_sections` 件の source section を含める。section_metadata stage と同様、batch payload は `catalog` (重複排除された section descriptor 集合) と `evaluations` (source_section_id + 候補 list の配列) で構成される。

batch の同時実行は `[limits].llm_batch_concurrency` で制御する:

- `1` (default): 逐次実行。互換性デフォルト、サブスク quota が厳しい環境向け
- `4-8`: Codex Pro 5x / Claude Max 5x など上位サブスクで wall time を 4-8 倍速化
- 実装は `concurrent.futures.ThreadPoolExecutor(max_workers=N)`
- batch 間の結果は `executor.map` で順序保持。`llm_results` のインデックスと batch の対応関係は崩れない

並列度を上げるとサブスクの 5h window quota を早く消費する点に注意。1 batch あたり 1-2 LLM call (max_retries=1)、418 sections 規模で計 100+ call/run になるため、Codex Plus (15-80/5h) では超過する。Codex Pro 5x (80-400/5h) / Claude Max 5x が最低水準。

LLM 出力:

```text
target_section_id
relation_hint
confidence
reason
evidence_terms[]
channels[]
```

`relation_hint` の許可値:

```text
depends_on
impacts
same_policy
prerequisite
see_also
```

`conflicts_with` は本 stage の出力 enum から **削除** されている。LLM が矛盾の兆候を見つけた場合は `possible_conflict: true` フラグだけ立て、Conflict Review pipeline (§5.8) が Purpose / Core Concept / Source Specs grounding 付きで独立に判定する。これにより軽量な分類タスクと厳密な矛盾判定の evidence 厳密度を分離する。

最初に重視する relation:

```text
depends_on
impacts
prerequisite
```

`confidence` の許可値:

```text
high
medium
low
```

`confidence` は Related Sections をどの程度強く参照すべきかを示す補助値であり、制約の確からしさそのものではない。

### 5.5 Related Sections Schema

通常参照用の `related_sections` は次を持つ。

```text
target_section_id
relation_hint
confidence
reason
evidence_terms[]
channels[]
possible_conflict     # bool、Conflict Review pipeline への referral signal
generated_at
```

例:

```yaml
related_sections:
  - target_section_id: docs/spec/core.md#freshness-gate
    relation_hint: depends_on
    confidence: high
    reason: この section の inject 実行条件は freshness gate の結果に依存するため。
    evidence_terms:
      - freshness gate
      - dirty
      - stale
    channels:
      - shared_identifier
      - search_key_match
      - qdrant_section_hybrid
    possible_conflict: false
```

### 5.6 Validation

LLM 出力は採用前に検証する。

検証項目:

- `target_section_id` が存在する
- LLM Selection の実行元 `source_section_id` の `related_section_candidates` に、同じ `target_section_id` の候補が存在する
- 自己参照ではない
- `relation_hint` が許可値である
- `confidence` が許可値である
- `evidence_terms` が候補情報または本文 snippet に存在する
- 最大件数を超えていない

`target_section_id` が存在するだけでは採用条件として不十分である。LLM 出力の `target_section_id` は、必ずその `source_section_id` の `related_section_candidates` 内にある target だけを採用する。候補外の target は hallucinated target として drop し、diagnostics に source / target / reason を残す。

検証に失敗した item は落とし、必要に応じて debug warning として残す。

### 5.7 Incremental Re-evaluation

ある section A が変わった場合、A だけを再評価すると古い関連が残る可能性がある。incremental update では、少なくとも次を Related Sections 再評価対象にする。

```text
変更 section
変更 section が related target になっている section (前回 metadata の reverse index)
specificity filter 通過後の shared identifier を持つ section
specificity filter 通過後の search_key 一致を持つ section
明示 markdown link でつながる section
前回 `related_section_candidates` の reverse index で変更 section が target になっていた section
```

旧設計の「同じ chapter の近傍 section」「summary token overlap」のヒューリスティックは Phase F で削除した。これらは旧 `same_chapter` / `neighbor_section` / `summary_search` channel の補完であり、現行の Qdrant section hybrid retrieval が semantic な近傍を担うため不要になった。

この範囲は correctness のための下限である。section embedding の変更が `qdrant_section_hybrid` の top-K ランキングを揺らす可能性は理論上残るので、実装が軽い場合は変更 section を含む batch で全 source を再評価してもよい。

実装は **pair 単位 cache 方式** を採用する。`compute_related_sections_reevaluation_targets` は外部 API として上の再評価対象集合を返す関数だが、core 経路では narrowing による「新規候補入りこぼし」を避けるため、毎回全 source の candidate 生成を行い、`(source_id, target_id, source_hash, target_hash, prompt_version, model, effort)` を key とする pair cache `related_typing_cache.json` で unchanged pair の LLM 再評価をスキップする。これにより candidate set shift（X 不変だが S が新規に X の top-K に enter）も pair cache miss として正しく LLM 評価されるため、narrowing 経路が抱える correctness loss を回避する。

### 5.8 Conflict Review Items

`related_sections` の `possible_conflict: true` フラグが立った section pair について、CLI は該当 section pair の Source Specs snippet、関連する Purpose / Core Concept、候補生成 channel を LLM に渡して conflict 判定を行う。Related Sections の relation_hint には `conflicts_with` は含まれない (§5.4 参照)。Conflict Review pipeline は Related Sections の分類とは独立した judge call で、Purpose / Core Concept / Source Specs grounding を必須とする。

`conflict_review.evaluate_conflicts` は `judge` callable を引数として受け取る薄い orchestration である。Purpose / Core Concept / Source Specs を実際に grounding として LLM に渡す責務は呼び出し側が用意する `judge` 実装が担う。core.py の通常経路では `_EvidenceGroundedConflictJudge` ラッパーが Purpose と Core Concept のテキストとハッシュを毎 request に付与する。`evaluate_conflicts` を単体で呼ぶ caller (テストや外部ツール) も同等の grounding を持つ judge を渡す責任を負う。

Source Specs grounding は section_a / section_b の本文を judge prompt に含める形で行う。周辺 section や全 corpus を judge に渡すことはしない。judge が追加 context を必要とする場合は、`evidence_terms` を経由した snippet 抽出のみを使い、Source Specs 全文の盲目的注入は CLAUDE.md ルール 4 に反するため行わない。

旧 `relation_hint == "conflicts_with"` 経路は backward compatibility のため `conflict_review.select_conflict_judging_pairs` で受理されるが、新規 LLM 出力ではこの hint を使わない。

`apply_conflict_decision` は status を `resolved` または `dismissed` に変更する場合、`decision_payload.human_acknowledgement = true` を必須とする。CLAUDE.md ルール 5 / EXTERNAL_DESIGN §2.8 に従い、最終裁定は人間の判断であることを caller が明示的に attest する。Agent / LLM が独断で resolve / dismiss を実行する経路はサポートしない。

LLM が「矛盾ではない」または「既存根拠から優先関係が明確」と判断できる場合は、`potential_conflicts` warning として diagnostics に残すだけでよい。

LLM が判断できない場合は、`conflict_review_items.json` に次の項目を保存する。

```text
conflict_id
status: pending | resolved | dismissed
severity
source_refs[]
claims[]
why_conflicting
why_llm_cannot_decide
related_sections[]
decision_options[]
resolution
reflection_status
reflected_refs[]
base_source_hashes[]
valid_scope
stale_resolution
created_at
updated_at
```

Conflict Review Item の `status = pending` は、freshness report の `blocking_reasons[]` に `pending_conflict` を作る。`/spec-inject` と `/spec-realign` は pending conflict を無視して進まない。

人間判断により `resolved` または `dismissed` になった item は、resolution に判断内容、理由、参照 source refs を保持する。resolution は一時的な人間判断として参照できるが、長期的には Purpose、Core Concept、Source Specs のいずれかへ反映することを推奨する。

`reflection_status` は `unreflected | reflected | not_required` とする。resolved item が `unreflected` の場合、`/spec-core` は diagnostics に `unreflected_conflict_resolutions` を出す。これは blocker ではないが、`/spec-inject` と `/spec-realign` がその resolution を根拠に使う場合は、未反映の人間判断であることを出力に含める。

`base_source_hashes` は resolution の判断時に参照した Purpose、Core Concept、Source Specs の hash を保持する。対象 source が変わった場合、resolution は `stale_resolution = true` になり、制約根拠として使わない。Agent / LLM は再判断または Source Specs への反映を促す。

`valid_scope` は resolution が効く範囲である。値は `global | source_pair | section_pair | task_scope` とする。`task_scope` の resolution は、その課題内の一時判断として扱い、後続セッションの恒久根拠にはしない。

decision payload は `/spec-core` の内部 transport として受ける。外部 slash command は増やさず、Agent / LLM が人間回答を構造化して CLI に戻す。

decision payload の `decision` は次の enum に限定する。

```text
prefer_a -> resolved
prefer_b -> resolved
conditional -> resolved
dismiss -> dismissed
needs_source_update -> pending
defer -> pending
task_scope_resolution -> resolved + valid_scope=task_scope
```

## 6. Chapter Key Anchor

Chapter Key Anchor は、章全体の重要テーマ、判断軸、主要 section への入口を、LLM が章単位で抽象化して生成する。`/spec-inject` の path ② が章単位エントリポイントとして利用する。

artifact: `.spec-grag/context/chapter_anchors.json`

LLM 生成 input:

```text
chapter heading
chapter 配下の section summaries
chapter 配下の search keys / identifiers
chapter 配下の related sections
Core Concept のうち関連する項目
```

LLM 生成 output (per chapter):

```text
chapter_id
summary             # 章全体の抽象化された要約
key_topics[]        # 章の重要テーマ
important_sections[] # 判断軸となる主要 section の section_id 群
notes[]             # 章全体で守るべき読み方
source_section_ids[] # 章配下の全 section_id
generated_at
```

Chapter Key Anchor の cache key は次を含む。

```text
chapter_id
章配下の section_hash 集合
prompt_version
model
effort
```

cache key が前回と一致する場合は LLM 再呼出をしない。`--all` 時は cache を clear して再生成する。`--rebuild` は本 artifact の挙動には影響しない (LLM 生成範囲は `--all` と同じ扱い)。

Chapter Key Anchor は制約の最終根拠ではない。Agentic Search の入口として使う。

## 7. `/spec-core` フロー

通常実行:

```text
load config
load Purpose / Core Concept
build current section manifest
compare section hashes
update changed Section Summary
update changed Section Search Keys
update Source Retrieval Index
generate related_section_candidates
run LLM selection for Related Sections
validate Related Sections
evaluate conflicts_with pairs
update Conflict Review Items
update impacted Chapter Key Anchors
write context artifacts atomically
write freshness
return CoreResult
```

`--all` 実行:

```text
load config
load Purpose / Core Concept
build current section manifest
regenerate all Section Summary
regenerate all Section Search Keys
rebuild Source Retrieval Index
generate all related_section_candidates
run LLM selection for all Related Sections
validate Related Sections
evaluate all conflicts_with pairs
update Conflict Review Items
regenerate Chapter Key Anchors
write context artifacts atomically
write freshness
return CoreResult
```

## 8. `/spec-inject` と `/spec-realign`

slash command は Agent / LLM に探索手順を指示する。CLI は次の参照操作を提供する。CLAUDE.md ルール 4 の `evidence_origin` enum (Purpose / Core Concept / Source Specs / Conflict Review Item) を 4 path がカバーする。

| 操作 | コマンド | 戻り値 | 対応 path |
|---|---|---|---|
| gate probe | `spec-grag inject "<task>"` | freshness report、pending conflict、`needs_agent_constraints` フラグ | 全 path 共通 |
| section-level hybrid retrieval | `spec-grag inject-search "<query>"` | top-K の section payload (heading / summary / search_keys / identifiers / related_sections / source_section_id / score) | path ① |
| section payload lookup | `spec-grag inject-section "<id>" [<id>...]` | 指定 section_id の payload 一括取得。`related_sections` 辿り用 | path ① の hop traversal |
| 章 anchor 取得 | `spec-grag inject-chapters` | `chapter_anchors.json` 全体 | path ② |
| Purpose / Core Concept 取得 | `spec-grag inject-purpose` | `purpose_file` + `concept_file` の全文 | path ③ |
| Conflict Review Items 取得 | `spec-grag inject-conflicts` | `status = resolved` かつ stale でない items | path ④ |
| 制約検証 | `spec-grag inject "<task>" --constraints '<JSON>'` | validated constraints + injectable_context | constraint 確定時 |

Agent / LLM はこれらを使い、課題の性質に応じて 4 path を組み合わせる。

| 課題タイプ | 主 path | 補強 |
|---|---|---|
| 具体的 API / 識別子 | ① | ③、④ |
| 全体方針 / 抽象的 | ② | ①、③、④ |
| Purpose / Core Concept 直接質問 | ③ | ①、② |
| 過去判断の継続 | ④ | ①、③ |

CLI は探索方針を自律的に決めない。Agent / LLM は inject-search の戻り値の `related_sections` 配列を辿る再帰探索を、`[limits].max_traversal_hops` (default 2-3) の範囲で行う。

## 9. Freshness

freshness は次の入力で判定する。

```text
Source Specs section manifest
Purpose file hash
Core Concept file hash
Section Metadata version
Chapter Anchor version
Conflict Review Items version / pending status
LLM provider / model / prompt version
embedding provider / model
vector store collection revision
retrieval config
```

freshness report は次を持つ。

```text
status: fresh | blocked | degraded | failed
blocking_reasons[]
warnings[]
```

`blocking_reasons[]` の表示優先は次の順にする。

```text
dirty_or_stale_source
watcher_running
watcher_queue_pending
stale_config_or_schema
failed_required_artifact
pending_conflict
degraded_optional_artifact
```

dirty / stale / watcher queue と pending conflict が同時に存在する場合、pending conflict は古い source hash に基づく可能性がある。先に `/spec-core` または watcher で更新し、更新後に残った pending conflict だけを人間判断対象にする。

`/spec-inject` と `/spec-realign` は、`status != fresh` の場合に自動更新しない。`blocking_reasons[]` に dirty / stale / watcher 系理由がある場合は `/spec-core` または watcher が先に保持物を更新する。`blocking_reasons[] = ["pending_conflict"]` だけが残る場合は Conflict Review Item の人間判断を先に行う。

watcher は run 開始時の Source Specs snapshot を固定し、実行中に入った追加変更は次回 queue として扱う。watcher running または queue non-empty の間、freshness report は `status = blocked` になり、`watcher_running` または `watcher_queue_pending` を `blocking_reasons[]` に入れる。

## 10. 診断

run artifact には、少なくとも次を保存できるようにする。

```text
updated_sections
skipped_sections
failed_sections
related_section_candidate_count
related_section_selected_count
related_candidate_limit_events[]
candidate_channels_summary
potential_conflicts
conflict_review_item_count
pending_conflict_count
unreflected_conflict_resolution_count
stale_resolution_count
dense_hit_count
sparse_hit_count
fusion_method
qdrant_collection
embedding_provider
embedding_model
stage_timings
warnings
```

Source Specs 本文、LLM prompt 本文、LLM response 本文は、明示設定なしに run artifact へ保存しない。

## 11. 非対象

本設計では次を標準経路にしない。

```text
property graph
entity relation graph
hierarchical cluster
無制限 graph traversal
CLI 主導の Agentic Search
Ollama bge-m3 による sparse vector 生成
```
