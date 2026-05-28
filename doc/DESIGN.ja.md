# SPEC-anchor 内部設計書

> 版: draft
> 対応する外部設計: `doc/EXTERNAL_DESIGN.ja.md`

本書は、軽量な仕様コンテキスト方式の内部設計を定義する。外部設計が「ユーザーから見える契約」を扱うのに対し、本書は保持物の形式、生成フロー、検索基盤、Related Sections 生成、freshness 判定を扱う。

## 0. 実装状況 (CLAUDE.md ルール 13 ダッシュボード)

内部設計の主要契約のうち、実装と検証の完了状況を記録する。`[x]` には evidence (file:line + test) を直下に併記する。詳細な refactor 計画は `doc/STORAGE_REDESIGN.ja.md` §7.4 (Phase R-0 〜 R-7) を参照。

- [x] §3.2 Section Search Keys は **自然言語のみ**、§3.3 Identifiers と非重複 (役割分離)
  - 実装: spec_anchor/section_metadata.py:105 (`_SEARCH_KEYS_INSTRUCTIONS`)、spec_anchor/section_metadata.py:120 (`_is_identifier_like_search_key`)、spec_anchor/section_metadata.py:1147 (`_search_keys`)
  - 検証: tests/test_section_metadata_generation.py::test_search_keys_and_identifiers_are_disjoint (per-key overlap 0% を assert、実 codex で 45.2% → 0.0% を計測済み)
- [x] §3.3 Identifiers は section 本文 + heading からの正規表現抽出 (LLM を経由しない決定論性)
  - 実装: spec_anchor/section_metadata.py:486-514 (`extract_identifiers`)
  - 検証: tests/test_section_metadata_generation.py::test_t_u21_generated_section_metadata_entries_have_required_fields
- [x] §3.4 LLM Generation Policy: section_metadata と related_sections は batch 化、`[limits].llm_batch_concurrency` で並列化可能
  - 実装: spec_anchor/section_metadata.py:329-334 (section_metadata 並列)、spec_anchor/related_sections.py の同様経路 (related_sections 並列)
  - 検証: tests/test_related_sections.py::test_llm_batch_concurrency_runs_batches_in_parallel、tests/test_related_sections.py::test_llm_batch_concurrency_default_is_sequential
- [x] §5 Related Sections: `relation_hint` enum = {depends_on, impacts, prerequisite, same_policy, see_also}、`conflicts_with` は除外し `possible_conflict` フラグだけ立てる
  - 実装: spec_anchor/related_sections.py:59-65 (`ALLOWED_RELATION_HINTS`)、spec_anchor/related_sections.py:858-863 (invalid 値を drop)、spec_anchor/related_sections.py:959 (`possible_conflict` flag 読み取り)
  - 検証: tests/test_related_sections.py::test_t_u10_related_sections_validation_filters_invalid_items_and_applies_limit、tests/test_conflict_review.py::test_t_u20_conflict_pair_selection_uses_conflicts_with_and_bounded_high_risk_pairs
- [x] §5.7 Related Sections の incremental re-evaluation は **pair-level cache** 方式
  - 実装: spec_anchor/related_typing_cache.py (pair key = `(source_id, target_id, source_hash, target_hash, prompt_version, model, effort)`)、spec_anchor/related_sections.py 経由で参照
  - 検証: tests/test_related_sections.py::test_pair_level_typing_cache_skips_unchanged_pairs
- [x] §5.8 Conflict 判定 stage は `possible_conflict=true` pair と高リスク pair を対象とし、`conflict_pair_max_per_section` 上限内に絞る (全 section pair の総当たり判定はしない)
  - 実装: spec_anchor/conflict_review.py の対象選定経路
  - 検証: tests/test_conflict_review.py::test_t_u20_conflict_pair_selection_uses_conflicts_with_and_bounded_high_risk_pairs
- [x] §9 Freshness: pending Conflict Review Item は `/spec-inject` / `/spec-realign` の通常進行を blocker にする
  - 実装: spec_anchor/freshness.py、spec_anchor/conflict_review.py
  - 検証: tests/test_spec_core.py::test_t_i04_conflicts_with_unresolved_blocks_freshness
- [x] §3 Section Metadata は Qdrant `[retrieval].section_collection` の payload に格納する
  - 実装: `build_section_payloads` (spec_anchor/retrieval_index.py) が related_sections を含めて payload を組み立てる。`update_section_collection_related_sections` が related_sections stage 後に `client.set_payload` で書き戻し (spec_anchor/core.py `_update_section_collection_related_sections_if_enabled` が wire)。読み取り API は spec_anchor/section_payload.py `fetch_section_payloads`
  - 検証: tests/test_retrieval_index.py、tests/test_section_payload.py
- [x] §4 Source Retrieval Index は section-level Qdrant collection のみ
  - 実装: spec_anchor/retrieval_index.py の `upsert_qdrant_section_collection` / `QdrantHybridRetriever` / `section_hybrid_candidates`。spec_anchor/core.py の `_upsert_section_collection_if_enabled` が wire し、戻り値で `CoreResult.retrieval_index_status` を埋める
- [x] §6 Chapter Key Anchor は LLM が章単位で生成する (input: 章 heading + 配下 summary / search_keys / identifiers / related_sections + 関連 Core Concept、output: chapter_id / summary / key_topics / important_sections / notes / source_section_ids / generated_at)
  - 実装: Phase R-7 で spec_anchor/chapter_anchors.py (`generate_chapter_anchors`、`ChapterAnchorsCache`、`CHAPTER_ANCHORS_PROMPT_VERSION = "chapter-anchors-v1"`)。spec_anchor/core.py `_chapter_anchors` を新 module 委譲に置換 (cache_dir = context_dir / "cache"、provider は section_metadata と同 active_provider、concept_text は `[core].concept_file` から読み込み)。stage は LlmRequest contract に合わせ `chapter_key_anchor`
  - 検証: tests/test_chapter_anchors.py の 9 件 (chapter ごとに LLM call、summary/key_topics/notes が LLM 出力に由来、important_sections が章内 section_ids に絞られる、unparseable response 時の mechanical fallback、cache reuse、section_hash 変更時の選択的 invalidation)
- [x] §8 `/spec-inject` CLI 拡張 (`inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts`)
  - 実装: Phase R-6 で spec_anchor/inject.py に `run_inject_search` / `run_inject_section` / `run_inject_chapters` / `run_inject_purpose` / `run_inject_conflicts` を追加、spec_anchor/cli.py に対応する subparser + dispatcher を追加。Qdrant / FlagEmbedding 不可時は structured warning fallback。F-C 採用後、各 inject-* の冒頭に freshness gate を組み込み、gate probe 専用 subcommand (`spec-anchor inject`) は撤去
  - 検証: tests/test_inject_cli_extension.py
- [ ] §5.10 SpecClaim 経路 (SpecClaim 抽出 + Claim Retrieval + LLM triage) を新規実装する (SCD-032)
  - 詳細: `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` の §1-§17 を参照
  - 実装範囲: spec_anchor/spec_claims.py (SpecClaim 抽出 stage)、spec_anchor/claim_retrieval.py (Claim Retrieval stage)、spec_anchor/conflict_candidates.py (LLM triage stage)、spec_anchor/core.py のフロー組み込み
  - 検証: 実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う `/spec-core` 実行で `.spec-anchor/context/spec_claims.jsonl` と `.spec-anchor/context/conflict_candidate_pairs.jsonl` が生成されることを確認
  - **Phase 1 (SpecClaim 抽出 stage 単独) 完了 (2026-05-28, commits `eb8c1cf` Part A + `cbe13c0` Part B + Part C 修正)**: `spec_anchor/spec_claims.py` を新設 (version 定数 / prompt / schema validation / `claim_uid` 生成 / evidence offset 4 段階補正 / cache key / state file / jsonl atomic write)、`spec_anchor/core.py` に `_generate_spec_claims_if_enabled` を結線し CoreResult に `spec_claims_status` と `spec_claims_diagnostics` を追加、`spec_anchor/llm_provider.py` に `spec_claims` stage の prompt / OpenAI structured output schema (strict mode 対応で全 properties を required 化) を追加、`spec_anchor/config.py` の `[llm.stage_routing]` 許可 stage に `spec_claims` を追加。fake テストは `tests/test_spec_claims.py` (8 件) と `tests/test_spec_core.py` の incremental (skipped_unchanged + 部分再抽出 + 削除 section 除外) で確認。実機検証: 実 Codex CLI (`gpt-5.4-mini`) を使う `/spec-core` で `.spec-anchor/context/spec_claims.jsonl` に 5 section から 14 claim が JSON Lines で生成され、設計書 §5 の必須 field をすべて含むこと、変更なし incremental で `stages.spec_claims.status = "skipped_unchanged"` + `llm_calls = 0` になることを確認。
  - **Phase 2 (Claim Retrieval stage) 完了 (2026-05-29, commits `dd3c674` Part A + `94c25c7` Part B + `1e0a7ec` Part C)**: `spec_anchor/claim_retrieval.py` を新設 (`ClaimRetrievalConfig` / `InMemoryClaimRetrievalBackend` / `QdrantClaimRetriever` / claim-level Qdrant upsert + delete + dense + sparse + conflict_probe 3 channel retrieval + sorted `claim_uid` tuple dedup + `retrieval_sources[]` 集約 + RRF 順位融合 + 上限 truncation + state file 読み書き + `conflict_candidate_pairs.jsonl` atomic write、`candidate_uid_for_claim_pair` は sorted claim_uid pair → sha256 で route 含まず)、`spec_anchor/core.py` に `_generate_claim_retrieval_if_enabled` を結線し CoreResult に `claim_retrieval_status` と `claim_retrieval_diagnostics` (`candidate_count` / `truncated_candidate_sources` / `truncated_pair_count` / `same_section_pair_count`) を追加、`spec_anchor/config.py` に `[conflict_candidate_detection]` block と `[retrieval].claim_collection` (default `spec_anchor_claim`) の解決を追加。fake テストは `tests/test_claim_retrieval.py` (8 件: Qdrant fake upsert/delete + dedup + 上限 truncation + 削除 claim 除外 + `retrieval_sources[]` 集約 + 同一 section pair 採用 + 変更 claim 起点の全集合探索 + 未変更 pair reuse) と `tests/test_spec_core.py` の incremental (skipped_unchanged + 部分 upsert + 削除 claim 除外) で確認。`tests/test_spec_core_acceptance.py::test_trace_audit_stage_order` の `expected_order` に `claim_retrieval` を追加 (`spec_claims` と `conflict_evaluation` の間)。実機検証: 実 Qdrant (`localhost:6333`、`spec_anchor_claim` collection) と FlagEmbedding BGE-M3 を使う `/spec-core` で `.spec-anchor/context/conflict_candidate_pairs.jsonl` に 14 SpecClaim → 45 candidate pairs (うち 10 件が同一 section 内、27 件が `per_claim_top_k` / `per_section_top_k` 上限で truncate) が `triage = null` の retrieval-only candidate として生成され、変更なし incremental で `stages.claim_retrieval.status = "skipped_unchanged"` + `qdrant_upsert_count = 0` + `qdrant_search_count = 0` になることを確認。
  - **Phase 3 (LLM triage stage) 完了 (2026-05-29, commits `5204323` Part A + `fa2def0` Part B + 本 commit Part C)**: `spec_anchor/conflict_candidates.py` を新設 (`ConflictTriageLlmRequest` / `ConflictTriageValidation` / `ConflictCandidateTriageResult` / `ConflictTriageCache` / `build_conflict_triage_prompt` / `validate_conflict_triage_response` / `compute_conflict_triage_cache_key` / `generate_conflict_candidate_triage_result` / `write_conflict_candidate_pairs_jsonl`)、LLM triage 出力は `send_to_review` (bool) / `reason` (str) / `confidence` (high/medium/low の enum) のみで他 field を含む応答は reject (Conflict Review との責務重複防止)、cache key は両 claim の `claim_uid` / `claim_hash` / `retrieval_hash` / 両 source の `source_hash` / `triage_prompt_version` / `triage_schema_version` / `triage_model` / `triage_effort`、`triage_max_pairs` 上限内の LLM triage 実行、`triage = null` のままの retrieval-only record は `.spec-anchor/context/conflict_candidate_pairs.jsonl` から除外 (Conflict Review に送る対象は `triage.send_to_review = true` のみ)。`spec_anchor/core.py` に `_generate_conflict_candidate_triage_if_enabled` を結線し CoreResult に `conflict_candidate_triage_status` と `conflict_candidate_triage_diagnostics` (`send_to_review_count` / `send_to_review_false_count` / `triage_truncated_pairs`) を追加、`spec_anchor/llm_provider.py` に `conflict_candidate_triage` stage の prompt / OpenAI structured output schema (`send_to_review` / `reason` / `confidence` の全 properties を required で strict mode 対応) を追加、`spec_anchor/config.py` の `[llm.stage_routing]` 許可 stage に `conflict_candidate_triage` を追加。fake テストは `tests/test_conflict_candidates.py` (10 件: `conflict_confirmed` / `human_review_required` / `resolution` / 未知 field / `confidence` enum 外 の各 reject + `triage=None` の record 除外 + cache 再利用 + `triage_prompt_version` 変化で再評価 + `triage_max_pairs` 上限 + `send_to_review=true` の受理) と `tests/test_spec_core.py` の incremental (skipped_unchanged + 変更 claim 含む pair の cache miss + 未変更 pair の cache hit) で確認。`tests/test_spec_core_acceptance.py::test_trace_audit_stage_order` の `expected_order` に `conflict_candidate_triage` を追加 (`claim_retrieval` と `conflict_evaluation` の間)。実機検証: 実 Codex CLI (`gpt-5.4-mini` / `low`) + Qdrant + FlagEmbedding BGE-M3 を使う `/spec-core` で 14 SpecClaim → 45 candidate pairs → `triage_max_pairs = 30` の上限内で LLM triage を 30 件実行 (15 件は上限超過で `triage_truncated_pairs` に計上)、30 件のうち `send_to_review_count = 7` / `send_to_review_false_count = 23` で `triage.send_to_review = true` の 7 件のみが `.spec-anchor/context/conflict_candidate_pairs.jsonl` に保存されることを確認。変更なし incremental では `stages.conflict_candidate_triage.status = "skipped_unchanged"` + `llm_calls = 0` を確認。Phase 5 (`possible_conflict` 経路完全削除 + Conflict Review 入力境界変更) は未着手 (`doc/TODO.ja.md` T-spec-claim-phase-5 で追跡)。
  - **Phase 4 (実機 recall 検証 = Phase 5 着手 gate) 完了 (2026-05-29, 本 commit)**: 実 Codex CLI + Qdrant + FlagEmbedding BGE-M3 を使う `/spec-core` で `docs/spec/sample.md` の意図的な conflict pair (§0004 Session Termination: 24h purge ↔ §0005 Session Retention Policy: 30 日保持必須) が SpecClaim 経路で **2 件の SpecClaim pair (CC-00013 + CC-00015) として `triage.send_to_review = true, confidence = "high"` で `.spec-anchor/context/conflict_candidate_pairs.jsonl` に保存**され、Conflict Review pipeline の入力候補に届くことを確認 (合格基準 B 達成)。production config に `legacy_possible_conflict_mode` 等の legacy key を **未追加**で実施。recall 比較 (合格基準 C、任意項目) の手順と結果記録 template は `doc/性能測定/spec_claim_migration_comparison.md` (新規) に整備。Phase 5 (`possible_conflict` 経路完全削除 + Conflict Review 入力境界変更) は未着手 (`doc/TODO.ja.md` T-spec-claim-phase-5 で追跡)。
- [ ] §5 / §5.5 / §5.8 / §3.4 から `possible_conflict` field / `conflict_pair_max_per_section` / Related Sections 由来 conflict routing を完全削除する (SCD-032, Phase 5)
  - 実装範囲: spec_anchor/related_sections.py の schema / prompt / output から `possible_conflict` 削除、spec_anchor/llm_provider.py の `possible_conflict` schema 定義削除、spec_anchor/core.py の `possible_conflict=true` routing 削除、spec_anchor/conflict_review.py の relation_hint 整合 filter 削除、`[limits].conflict_pair_max_per_section` 設定 key 削除
  - 検証: `git grep -nE "possible_conflict|conflict_pair_max_per_section" spec_anchor tests` の hit が 0 件 (`doc/性能測定/spec_claim_migration_comparison.md` の比較記録以外)、Related Sections output に `possible_conflict` field が存在しない test を追加
- [ ] §5.8 Conflict Review の入力境界を SpecClaim pair / evidence / triage result に固定する (SCD-033)
  - 実装範囲: spec_anchor/conflict_review.py の `evaluate_conflicts` を SpecClaim pair 入力に変更、Related Sections の `relation_hint` を Conflict Review の入力にしない
  - 検証: Conflict Review に Related Sections 由来 pair が渡らない test を追加

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

Qdrant section collection の point id は、`stable_section_point_id(source_section_id)` で生成する。実装は `_SECTION_POINT_ID_NAMESPACE = UUID("b1d5535d-3e52-5430-af3e-ddd879e6cb19")` と `source_section_id` から UUID5 文字列を返す。`uuid.uuid5(...)` を直接呼ぶ場所はこの関数だけにし、Qdrant upsert や test はこの関数を経由する。

### 2.2 Context Artifacts

`.spec-anchor/context/` 配下に次の artifact を置く。

```text
chapter_anchors.json           # LLM 生成、章単位 anchor
conflict_review_items.json     # 人間判断 artifact
```

`.spec-anchor/state/` 配下:

```text
section_manifest.json                    # section 単位の差分検出 + 監査メタ
freshness.json                           # 実行状態 / blocking_reasons
core_progress.json                       # 実行進捗ログ
```

`.spec-anchor/cache/` 配下:

```text
section_metadata/<hash>.json             # LLM section_metadata 出力 cache (key 単位)
related_typing_cache.json                # LLM relation typing 結果 cache (pair 単位)
chapter_anchors/<hash>.json              # chapter_key_anchor LLM 出力 cache
```

section コンテンツ (source_document_id / source_span / summary / search_keys / identifiers / related_sections / heading_path / source_hash / semantic_hash) は Qdrant の section-level collection (`[retrieval].section_collection`、default `spec_anchor_section`) の payload に格納する。ローカルディスクには同等の JSON artifact を持たない。

## 3. Section Metadata

Section Metadata は Qdrant `[retrieval].section_collection` の payload として保存する。1 section = 1 vector で、payload は次を含む。

```text
source_section_id   # 一次 key
source_document_id  # Source Specs file path
source_span         # Source Specs 本文を Read で確認するための line / offset
source_hash         # invalidation 判定
semantic_hash       # 拡張用 invalidation
heading_path[]      # 見出し階層
summary             # LLM 生成、自然言語要約
search_keys[]       # LLM 生成、自然言語検索キー (§3.2)
identifiers[]       # 機械抽出、コードシンボル (§3.3)
related_sections[]  # typed graph 出向き edge (§5)
```

監査メタデータ (provider, status, generated_at, last_prompt_version) は `section_manifest.json` に格納する。LLM 出力の cache 制御 metadata (prompt_version, metadata_version) は `.spec-anchor/cache/section_metadata/<hash>.json` の cache file 内に保持する。

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
CLI command (例: spec-anchor core, spec-anchor inject-search)
CLI option (例: --rebuild)
ALL_CAPS 定数、PascalCase 型名
config key
status / warning words
```

抽出対象外 (§3.2 Search Keys に分離):

- 自然言語句、概念名、章タイトル、要約文

### 3.4 LLM Generation Policy

`/spec-core` は `[llm.providers.<id>]` 設定の command / model / effort / timeout_sec / max_retries を使って、Section Summary、Section Search Keys、Related Sections の選定、SpecClaim 抽出、Conflict Candidate Triage (SpecClaim pair に対する LLM triage)、Conflict Review (LLM が既存根拠で解消できない conflict の判定)、Chapter Key Anchor を生成・実行する。`SPEC_ANCHOR_FAKE_LLM` env var が truthy のときは provider 設定を無視して in-process FakeLlmProvider を使う (test / smoke 専用)。`SPEC_ANCHOR_FAKE_RETRIEVAL` が truthy のときは Qdrant + FlagEmbedding の実構築を block する (`allow_real_provider=True` 経路を除く)。

Codex 用 skill と Claude 用 command は `--llm-provider` を明示せず、`[llm.stage_routing]` に従って stage 別に provider を選ばせる。direct CLI / watcher / 手動実行も同様で、`--llm-provider` 未指定なら `[llm.stage_routing]` が、`stage_routing` 未指定の stage は `[llm.providers.<id>]` の先頭定義が選ばれる。`--llm-provider` を明示するとその id が全 stage を上書きする。`max_retries` は CLI subprocess 1 stage 呼び出しが失敗したときの追加 retry 回数で、`max_retries = 1` は最大 attempt 数 2 (初回 + retry) を意味する。

`[llm]` は `/spec-core` 用である。`/spec-inject` / `/spec-realign` の会話区間解釈、Agentic Search、制約生成、回答生成を担う Agent / LLM はこの設定の対象外である。

生成は section 単位の incremental update を基本にする。`--all` では全件を対象にするが、実装は複数 section を 1 prompt にまとめる batch 生成を使い、LLM 呼び出し回数を section 数に対して単純比例させない。

Section Summary と Section Search Keys は同一 section に対して同じ LLM 呼び出しで生成してよい。Related Sections の LLM Selection は、CLI が作った `related_section_candidates` を入力にし、候補外の全文探索を LLM に任せない。

SpecClaim 抽出は Source Specs の section から仕様主張を抽出する LLM stage であり、Related Sections の生成と独立に実行される。Claim Retrieval は claim-level の dense / sparse / conflict probe retrieval で候補 SpecClaim pair を絞る LLM を呼ばない stage、Conflict Candidate Triage は絞った少数 pair に対する LLM triage stage、Conflict Review は LLM が既存根拠で解消できない conflict を Conflict Review Item として記録する LLM stage である。全 SpecClaim pair の総当たり LLM 判定は行わない。詳細は `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` を参照。

stage 単位での model / effort 切替は `[llm.stage_routing]` で指定する。許可される stage key は `section_metadata` / `related_sections` / `spec_claims` / `conflict_candidate_triage` / `conflict_review` / `chapter_key_anchor` の 6 つ。`claim_retrieval` stage は LLM を呼ばないため stage_routing 対象外。stage_routing で指定された provider が `[llm.providers.<id>]` に存在しない場合、または stage key が許可外の場合は `ConfigError` で reject する。stage_routing 未指定の stage は `[llm.providers.<id>]` の先頭定義へフォールバックする。`select_llm_provider_config(stage=...)` の解決優先順は `provider_id (CLI 引数 / env)` → `stage_routing[stage]` → `[llm.providers.<id>]` の先頭定義の順である。

Claim Retrieval の処理量制御は `[conflict_candidate_detection]` の `per_claim_top_k`、`per_section_top_k`、`per_target_top_k`、`global_candidate_top_k`、`triage_max_pairs` の各上限で行う。上限により候補が切られた場合は CoreResult の diagnostics に `truncated_candidate_sources` / `truncated_pair_count` が残る。Related Sections 由来 pair や Related Sections として採用されなかった「高リスク候補」を Conflict Review に送る経路は持たない (SCD-033)。

Conflict Candidate Triage stage は、複数 SpecClaim pair を target / source document 単位で batch 化してよい。cache key は、対象 pair の `claim_uid`、`claim_hash`、`retrieval_hash`、両 claim の `source_hash`、Purpose / Core Concept hash、triage prompt version、LLM model を含める。Conflict Review stage の cache key は §5.8 を参照。

LLM generation artifact は、prompt version、model、source_hash、semantic_hash、metadata_version を持つ。同じ入力と同じ prompt version の生成結果は再利用してよい。

### 3.5 Limits

初期上限は次の値を標準とする。実装は `.spec-anchor/config.toml` の `[limits]` で上書きできる。

```text
section_summary_max_chars = 480
search_keys_max = 32
related_candidate_max_per_section = 32
related_selected_max_per_section = 8
llm_batch_max_sections = 8
llm_batch_max_chars = 12000
```

Conflict Candidate Detection 専用の上限は `[conflict_candidate_detection]` で管理する (`per_claim_top_k = 10` / `per_section_top_k = 20` / `per_target_top_k = 20` / `global_candidate_top_k = 100` / `triage_max_pairs = 30` 等)。詳細は `doc/EXTERNAL_DESIGN.ja.md` §10.2 と `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` §16 を参照。

### 3.6 Section Metadata Cache の entry 単位再構築

`SectionMetadataCache` ([spec_anchor/section_metadata.py:170](../spec_anchor/section_metadata.py#L170)) は section_metadata の生成結果を **entry 単位** で永続化し、incremental 経路で変更されていない section の LLM call を省く。cache key は `section_metadata_cache_key(source_section_id, source_hash, semantic_hash, metadata_version, prompt_version, enabled_fields, limits)` ([spec_anchor/section_metadata.py:562](../spec_anchor/section_metadata.py#L562)) で、key の SHA-256 が `.spec-anchor/cache/section_metadata/<hash>.json` の file 名になる。1 entry = 1 JSON file 構成のため、changed section だけ書き替えれば残り section の cache は file system 上で触らない。

incremental 経路で `cache.get(cache_key)` が hit すれば `generate_section_metadata_result` ([spec_anchor/section_metadata.py:300](../spec_anchor/section_metadata.py#L300) 周辺) は LLM call を skip し、`reused_section_ids` に section_id を加え `cache_hits` を increment する。miss すれば section を `llm_batch_max_sections` ごとの batch にまとめて 1 LLM call で生成し、`generated_section_ids` と `llm_calls` を更新する。`CoreResult.diagnostics.section_metadata_generation` は `cache_hits` / `llm_calls` / `batch_sizes` / `reused_section_ids` / `generated_section_ids` を公開しており、operator は cache 経路の現実を CoreResult から直接確認できる。

key 構成要素のいずれかが変わると entry が invalidate される。具体例: source 本文を 1 文字変えると `source_hash` と `semantic_hash` が変わり、その section の cache だけ miss する。section の `## ` heading 名を変えると `source_section_id` (= `<doc>#<ordinal>-<slug>` 形式、[spec_anchor/section_parser.py](../spec_anchor/section_parser.py)) が変わるので、heading を変えた section の cache だけ miss する。`prompt_version` を bump すると全 section の key が変わり cache 全 miss + 全 section LLM 再生成になる。これは B-5 計測 (`doc/監査/B-5_cache_measurement_2026-05-14.md`) の S0〜S5 で実機確認済。

incremental 経路の cache file garbage collection は部分的にのみ動作する (B-5 計測 §2 副次観察)。`--all` flag を渡した実行では `.spec-anchor/cache/` 配下の section_metadata cache が wipe され、その後の generation で全 section の entry が新規書き込みされる。これが「外部設計書 §7 で `--all` が `LLM 由来 cache (section_metadata / pair typing / chapter_anchors) をクリアして再評価` と表現される動作」の内部実装である。

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

Qdrant collection は **section-level の `[retrieval].section_collection` のみ** を持つ。1 section = 1 vector で、payload は次を含む。

```text
source_section_id   # 一次 key
source_document_id
source_span
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

section embedding text は短い (~700 文字程度)。本文の searchable surface は search_keys (自然言語、dense embedding 補強) と identifiers (コードシンボル、sparse / lexical 補強) が section 単位で代理表現する。

Source Specs 本文を直接読みたい場合は、Agent が `sources.include` で指定された Markdown ファイルを Read tool で開く。

Qdrant point id は payload の `source_section_id` から `stable_section_point_id(...)` で生成した UUID5 文字列とする。`upsert_qdrant_section_collection` は `PointStruct(id=stable_section_point_id(payload["source_section_id"]), ...)` を使う。これにより、Section の並び替えがあっても point id と payload の対応が崩れない。

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

point_id_scheme:
  point_id_v1_uuid5_source_section_id

tie_break:
  source_section_id
  source_hash
```

Qdrant / FlagEmbedding の最小 version は、実装パッケージ側で pin する。artifact には、Qdrant collection schema version、Qdrant server version、FlagEmbedding package version、embedding model revision、dense size、distance、sparse vector kind、fusion method を保存する。

Qdrant 側 RRF と CLI 側 RRF のどちらを使った場合でも、diagnostics には fusion owner、dense ranking、sparse ranking、fused ranking、tie-break 結果を残す。

### 4.6 rebuild フラグと Retrieval Index の reuse

`/spec-core --all` は LLM 段階 (section_metadata / related_sections / chapter_key_anchor) を強制再生成する。section-level Qdrant collection は section fingerprint が一致する場合に再利用する (BGE-M3 embedding は決定論的なので再計算する利得がないため)。

`/spec-core --rebuild` は条件に関わらず Qdrant collection を `delete_collection` して全 section を re-embed + upsert する。

設計理由:

- BGE-M3 embedding は決定論的 (同 section embedding text + 同 model = 同 vector)
- Source Specs に変更がない限り、再 embed は計算資源だけ消費して情報利得がゼロ
- `--all` の本来の意図は「LLM 段階の非決定性を排除して再生成する」ことであり、決定論的な後段処理まで強制再計算する必要はない
- Vector 破損 / collection schema 移行などの異常系は `--rebuild` で対応する

retrieval index を意図的に再構築したい場合 (例: BGE-M3 model revision 変更、Qdrant collection schema 変更) の手段は `/spec-core --rebuild` とする。`--rebuild` は Qdrant `spec_anchor_section` collection を drop + recreate し、全 section を再 embed + upsert する。

`--rebuild-retrieval` のような専用 flag は現状提供しない。`--rebuild` が `--all` (LLM cache クリア) を含意するため、1 command で LLM 再生成 + retrieval 再構築が完結する。

### 4.7 incremental no-change fast path

incremental 実行 (`--all` / `--rebuild` なし) で「Source Specs に追加・削除・内容変更がなく、設定指紋も前回と一致する」場合、`_upsert_section_collection_if_enabled` は次の処理を **すべて省略する**。

- `FlagEmbeddingBgeM3Provider` のインスタンス化
- `provider.embed_documents([...])` の呼び出し
- Qdrant への `upsert` 呼び出し

この経路を fast path と呼ぶ。fast path に入った場合 `retrieval_index_status = "skipped_unchanged"`、`core_progress.json` の `stages.section_collection_upsert` には `action = "skipped_unchanged"`、`reason = "input_and_config_fingerprint_match_and_collection_exists"` を記録する。

fast path に入る条件 (すべて満たす場合のみ):

1. 入力フラグが incremental (`--all` / `--rebuild` 未指定、`run_full == False`)
2. 現 `section_manifest` の section 集合と、現 source parse 結果の section 集合が完全一致する。具体的には次のすべてが成立:
   - 追加された section_id がない
   - 削除された section_id がない
   - 各 section について `source_hash` と `semantic_hash` の両方が前回 manifest 値と一致 (`semantic_hash` だけの一致では fast path に入らない。`source_hash` 変化は section_metadata cache miss を引き起こし LLM 非決定性で metadata が揺れる可能性があるため)
3. Source Retrieval Index の冪等判定用の状態記録ファイル `.spec-anchor/state/retrieval_index_state.json` が存在し、次の指紋がすべて現在値と一致する:
   - `section_hash_fingerprint` (sorted(source_hash|semantic_hash) の集約 SHA-256)
   - `embedding_provider`, `embedding_model` (config の `[embedding]`)
   - `dense_enabled`, `sparse_enabled` (BGE-M3 dense/sparse の有効化フラグ)
   - `retrieval_schema_pin_fingerprint` (Qdrant collection schema 版 + BGE-M3 dense サイズ + sparse ベクトル設定 + `point_id_v1_uuid5_source_section_id`)
   - `artifact_schema_version`
4. Qdrant collection が実在する (`QdrantClient(url).collection_exists(collection_name=...)` が True)。`collection_exists` のみで足り、scroll で全 payload を読む必要はない (`collection_exists` は Qdrant の軽量 RPC)。

通常経路への fallback 条件 (いずれか 1 つでも該当する場合):

- 入力フラグが `--all` / `--rebuild`
- Source Retrieval Index の冪等判定用の状態記録ファイル `.spec-anchor/state/retrieval_index_state.json` が存在しない / JSON parse 失敗 / 指紋不一致
- Qdrant collection が存在しない
- 上流の `section_metadata` stage で再生成が走り、section_metadata の指紋 (`manifest.generation`) が変わった

fast path に入れず Source Retrieval Index の更新を実行した場合は、`retrieval_index_status = "success"` または `"failed"` を返す。`core_progress.json` の `stages.section_collection_upsert.action` には、全 Section を embed / upsert した場合は `upserted_full`、`recreate=False` で差分 Section だけを embed / upsert した場合は `upserted_partial` を記録する。`reason` には更新が必要になった具体的根拠 (`sidecar_missing` は `.spec-anchor/state/retrieval_index_state.json` がない場合、`fingerprint_mismatch` は指紋不一致、`collection_missing` は Qdrant collection 不在) を記録する。

Qdrant payload と manifest の section 単位 hash 整合性チェック (= 全件 scroll) は通常 fast path では行わない。large spec で持続不能になるため。明示的な検証は `spec-anchor core --verify-index` を指定した場合だけ §4.10 の経路で実行する。

### 4.8 ordinal point id collection の自動 migration

`upsert_qdrant_section_collection` は `recreate=False` で既存 Qdrant collection を更新する前に、`client.scroll(..., with_payload=False, with_vectors=False, limit=1)` で sample point id を 1 件読む。`uuid.UUID(str(sample.id))` が `ValueError` になる場合、その collection は旧 ordinal point id 形式と判定する。

旧 ordinal point id 形式を検出した実行では、`upsert_qdrant_section_collection` はその場で `recreate=True` に切り替え、collection を再作成して全 Section を UUID5 point id で upsert する。戻り値の diagnostics には `reason = "migration_required_from_ordinal_point_id"`、`migration_required_from_ordinal_point_id = true`、`recreate = true` を入れる。`_upsert_section_collection_if_enabled` はこの diagnostics を `.spec-anchor/state/core_progress.json` の `stages.section_collection_upsert.diagnostics` に記録し、`stages.section_collection_upsert.action` は `upserted_full` にする。

`recreate=False` で既存 collection が UUID point id 形式の場合、`upsert_qdrant_section_collection` は upsert 前に `client.scroll(..., with_payload=False, with_vectors=False, limit=1024)` を offset 付きで最後まで実行し、既存 point id 集合を取得する。現在の Section 集合から `stable_section_point_id(source_section_id)` で期待 point id 集合を作り、差分を `client.delete(collection_name=..., points_selector=PointIdsList(points=[...]))` で削除する。削除数は diagnostics の `stale_points_deleted` に記録する。

### 4.9 partial-change section collection upsert

`_upsert_section_collection_if_enabled` は、`section_collection_upsert` stage に入る時点で current Section 集合と前回の `.spec-anchor/state/section_manifest.json` を比較し、次の 3 集合を作る。

- `added_section_ids`: current input に存在し、前回 manifest に存在しない `source_section_id`
- `changed_section_ids`: 両方に存在するが、比較対象 fingerprint のいずれかが変わった `source_section_id`
- `removed_section_ids`: 前回 manifest に存在し、current input に存在しない `source_section_id`

`changed_section_ids` の比較対象は次の 4 つである。

- `source_hash`: Source Specs の Section 本文 hash
- `semantic_hash`: whitespace 正規化後の Section hash
- `vector_input_fingerprint`: `build_section_payloads` が作る `payload["text"]` の SHA-256
- `payload_fingerprint`: Qdrant に保存する payload dict から `related_sections` field を除外したサブセットを `_stable_json(...)` で canonical JSON 化した文字列の SHA-256

`vector_input_fingerprint` は、Source Specs 本文が同じでも `summary` / `search_keys` / `identifiers` の変化で BGE-M3 入力 text が変わる場合を検出する。`payload_fingerprint` は、BGE-M3 入力 text には入らない payload field、たとえば `heading_path` / `chapter_id` / `source_document_id` の変化を検出する。

`related_sections` field を `payload_fingerprint` の対象から **除外する** のは、`update_section_collection_related_sections` ([spec_anchor/retrieval_index.py](spec_anchor/retrieval_index.py)) が `related_sections` を Qdrant `set_payload` で別経路で patch し、BGE-M3 embedding を変えない責務分割になっているためである。`section_collection_upsert` stage の diff 計算は、Section が変わったとき **embedding / upsert を再実行する必要があるか** を判定するためのものなので、embedding を変えない `related_sections` の変化は対象に含めない。これを含めると、`_upsert_section_collection_if_enabled` が diff 計算する apply-before タイミングの payload (`related_sections=[]`) と、Section Manifest に最終記録される apply-after タイミングの payload (`related_sections=[...]`) で `payload_fingerprint` が乖離し、次回 incremental 実行で全 Section が `changed` と誤判定される。

partial upsert 分岐:

- `--rebuild` または `recreate=True`: partial diff は使わず、全 Section を embed + upsert し、Qdrant collection を recreate する。
- B-3a migration: 既存 collection に旧 ordinal point id が見つかった場合、`upsert_qdrant_section_collection` は `recreate=True` に切り替え、partial diff は使わず全 Section を UUID5 point id で再登録する。
- incremental で collection が存在し、migration も不要: `sections_to_upsert = added_section_ids + changed_section_ids` に対応する Section だけを `provider.embed_documents([...])` に渡し、同じ `stable_section_point_id(source_section_id)` の point を上書きする。`removed_section_ids` は `stable_section_point_id(...)` に変換して `PointIdsList(points=[...])` で delete する。他の point は触らない。
- caller が `sections_to_delete` を渡さない場合: B-3a の stale delete 経路を維持し、既存 point id 全体を scroll して current Section 集合に無い point を削除する。caller が空 list を含めて `sections_to_delete` を渡した場合は、明示された削除集合だけを扱う。

インクリメンタル部分実行では sections_to_delete が明示集合として渡るため、B-3a の collection-wide stale delete (collection 全 scroll → current にない point を削除) は走らない。manifest が信頼できる前提で stale 検出は manifest diff だけに依存する。manifest が壊れた場合は --rebuild で復旧する。`--verify-index` (B-4) を指定した実行では §4.10 の独立検証経路で Qdrant payload と manifest の乖離を検出できる。

`upsert_qdrant_section_collection` の optional keyword は additive contract とする。`sections_to_upsert=None`, `sections_to_delete=None` の場合は、従来と同じ full-batch upsert と stale delete 判定を行う。incremental 実行で partial diff を使い、`recreate=False` のまま差分 Section だけを登録した場合、`core_progress.json` の `stages.section_collection_upsert.action` は `upserted_partial` になる。

`.spec-anchor/state/section_manifest.json` には、最終的に Qdrant payload として観測される Section ごとの `vector_input_fingerprint` と `payload_fingerprint` を保存する。次回 incremental 実行では、この manifest entry と current payload fingerprint を比較して partial diff を作る。`.spec-anchor/state/retrieval_index_state.json` は collection 全体の冪等判定用に、section hash 集約指紋と embedding / retrieval 設定指紋を保存し続ける。fingerprint が一致し、Qdrant collection も存在し、3 つの diff 集合がすべて空の場合だけ、`section_collection_upsert` stage は `skipped_unchanged` で終了する。

### 4.10 明示検証 (`--verify-index`)

`spec-anchor core --verify-index` は `_upsert_section_collection_if_enabled` の戻り値が確定した直後、`_generate_related_sections` に `retrieval_index_status` を渡す前に `_verify_section_collection_if_requested` で実行する。目的は、`.spec-anchor/state/retrieval_index_state.json` に保存された Source Retrieval Index の前回状態 (section hash 指紋 + 設定指紋) と現在値が一致し、`section_collection_upsert` stage が `skipped_unchanged` になった場合でも、Qdrant collection の実 payload が現在の Section manifest と乖離していないかを operator が明示的に確認できるようにすることである。

実行しない条件:

- `--verify-index` が指定されていない: `stages.verify_index.action = "disabled"`, `reason = "not_requested"`。
- `[embedding].provider != "flagembedding"` または `[vector_store].provider != "qdrant"`: `stages.verify_index.action = "disabled"`, `reason = "disabled"`。
- `_upsert_section_collection_if_enabled` が `failed` / `blocked` / `skipped` を返した: `stages.verify_index.action = "skipped"`。上流の status を上書きしない。
- `_upsert_section_collection_if_enabled` が `upserted_full` を記録した、または `--rebuild` により `force_full_recreate=True` になった: `stages.verify_index.action = "skipped"`, `reason = "already_recreated"`。直前に全 Section payload を書いた経路なので、追加 scroll は冗長である。

実行する場合、`_verify_section_collection_if_requested` は現在書き込む予定の `section_manifest` entry から次の expected map を作る。

```text
source_section_id ->
  source_hash
  semantic_hash
  vector_input_fingerprint
  payload_fingerprint
```

Qdrant collection の実 payload は `_scroll_section_payloads_from_qdrant` が `client.scroll(collection_name=..., with_payload=True, with_vectors=False, limit=256, offset=...)` で全件取得する。各 payload の `vector_input_fingerprint` と `payload_fingerprint` は `retrieval_index.py:756 section_payload_fingerprints` を使って計算する。同じ計算式を使うため、`payload_fingerprint` は `related_sections` field を除外した `_payload_fingerprint_input` に基づく。

差分分類:

- `stale_point`: Qdrant payload の `source_section_id` が expected map に存在しない。payload に `source_section_id` が無い場合は `section_id = "<missing>"` として記録する。
- `missing_point`: expected map に存在する `source_section_id` が Qdrant payload に存在しない。
- `hash_mismatch`: `source_section_id` が両方に存在するが、`source_hash` / `semantic_hash` / `vector_input_fingerprint` / `payload_fingerprint` のいずれかが一致しない。`source_hash` 等の直接 field が不一致の場合、`payload_fingerprint` の不一致は派生差分として `fields` へ重複記録しない。

`stages.verify_index` の schema:

```text
action: verified_clean | verified_inconsistent | skipped | disabled
reason:
  verified_clean の場合: clean
  verified_inconsistent の場合: hash_mismatch | stale_point | missing_point | mixed
  skipped / disabled の場合: not_requested | disabled | already_recreated | retrieval_index_<status>
diagnostics:
  executed: boolean
  checked_count: int
  stale_point_count: int
  missing_point_count: int
  hash_mismatch_count: int
  issues:
    - section_id: string
      reason_code: stale_point | missing_point | hash_mismatch
      fields: list[string]
```

不整合 0 件の場合、`retrieval_index_status` は変更しない。不整合が 1 件以上ある場合、`_verify_section_collection_if_requested` は `retrieval_index_status = "failed"` に降格する。この状態で `freshness_report` は `failed_required_artifacts` に `retrieval_index` を含み、`warnings` には `Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild` を追加する。自動修復はしない。復旧手段は既存契約どおり `/spec-core --rebuild` である。

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

LLM は候補 section の `heading_path`、`identifiers`、`source_document_id`、本文先頭 480 文字の `short_snippet`、`channels` を読んで、採用する `related_sections` を選ぶ。

`catalog` の field は意図的に **Source Specs から決定論的に導ける情報だけ** に絞っている。section_metadata stage が LLM 生成した `summary` / `search_keys` は同一入力でも run 毎に文字列レベルで揺れ、Claude prompt cache の prefix 一致を毎回破壊するため、related_sections の prompt 構築に持ち込まない。`spec-anchor core --rebuild` の 2 回目で 90% 以上が `cache_read_input_tokens` に流れる前提は、この catalog 決定論性に依存する。

LLM 呼び出しは batch 化されており、1 batch に最大 `[limits].llm_batch_max_sections` 件の source section を含める。section_metadata stage と同様、batch payload は `catalog` (重複排除された section descriptor 集合) と `evaluations` (source_section_id + 候補 list の配列) で構成される。`evaluations` の候補 score / channel / evidence_terms はすべて mechanical (候補生成側の signal) で、LLM 介入なしに stable。

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

`conflicts_with` は本 stage の出力 enum から **削除** されている。Related Sections は conflict 判定を持たない。仕様上の矛盾候補抽出は SpecClaim 経路 (SpecClaim 抽出 + Claim Retrieval + LLM triage、詳細は §5.10 と `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md`) が独立して扱う。これにより Related Sections の軽量な分類タスクと厳密な矛盾判定の evidence 厳密度を分離し、Related Sections のモデル選択が conflict recall を左右しない構造にする。

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

### 5.7.1 incremental no-change fast path

incremental 実行で「Source Specs に追加・削除・内容変更がなく、Related Sections の生成設定指紋も前回と一致する」場合、`_generate_related_sections` 経路は次の処理を **すべて省略する**。

- `QdrantHybridRetriever` のインスタンス化 (これは内部で `FlagEmbeddingBgeM3Provider` を作る重い処理)
- `provider.embed_query(...)` の呼び出し
- Qdrant への `query_points` (dense / sparse) 呼び出し
- `_add_qdrant_section_hybrid_candidates` 全体 (および他 channel の candidate generation は実行されない、後述の reuse 経路に置き換わる)
- `select_related_sections_result` 内の LLM provider 呼び出し

fast path に入った場合、`related_sections_status = "skipped_unchanged"`、`core_progress.json` の `stages.related_sections` には `action = "skipped_unchanged"`、`reason = "input_and_config_fingerprint_match"` を記録する。selected_related_sections は前回 artifact (Qdrant section payload の `related_sections` field) からそのまま継承する。

fast path に入る条件 (すべて満たす場合):

1. 入力フラグが incremental (`run_full == False`)
2. §4.7 と同じ section 集合 unchanged 条件 (source_hash + semantic_hash 両方一致、追加・削除なし)
3. Related Sections の冪等判定用の状態記録ファイル `.spec-anchor/state/related_sections_state.json` が存在し、次の指紋が現在値と一致:
   - `section_list_fingerprint` (sorted(source_section_id) の集約 SHA-256)
   - `section_hash_fingerprint` (sorted(source_hash|semantic_hash) の集約 SHA-256)
   - `candidate_generation_config_fingerprint` (`MVP_CANDIDATE_CHANNELS`、`[retrieval]` の `section_candidate_top_k` / `section_final_top_n` / `section_dense_threshold`、`[limits]` の関連 fields の集約)
   - `selection_prompt_version` (`RELATED_SECTIONS_PROMPT_VERSION`)
   - `selection_model`, `selection_provider`, `selection_effort` (`[llm.stage_routing].related_sections` で解決された provider 設定)
   - `artifact_schema_version`
4. retrieval index 側も `retrieval_index_status == "skipped_unchanged"` または `success` であること (= Qdrant section payload が読める前提)。retrieval index が `failed` / `skipped` の場合は related_sections fast path に入らず通常経路に fallback。

通常経路への fallback 条件 (いずれか 1 つでも該当):

- §4.7 fast path から外れる原因がある (section 集合変更、設定指紋不一致、`--all` / `--rebuild` 指定)
- Related Sections の冪等判定用の状態記録ファイル `.spec-anchor/state/related_sections_state.json` が存在しない / JSON parse 失敗 / 指紋不一致
- 上流 `section_metadata` の指紋変化 (LLM 再生成が起きて identifiers / heading_path 派生 fingerprint が変わった等)
- retrieval index 側が `failed` または `skipped` (in-memory retrieval 経路になる場合は決定論性が落ちるので safety 寄りに通常経路で再生成する)

通常経路に fallback した場合は `related_sections_status = "success"` または `"failed"`、`core_progress.json` の `stages.related_sections.action = "fallback_regenerated"`、`reason` に fallback 根拠を記録する。

### 5.7.2 partial change regeneration (source 中心 partial)

`incremental no-change fast path` (§5.7.1) は「全 section が unchanged」の場合のみ動作する。1 section でも変更があると従来は `fallback_regenerated` 経路で全 section を再生成していたが (`generate_related_sections_result` が `generate_related_section_candidates_result(sections)` を全 section 入力で呼び、`select_related_sections_result` が 全 source の typing batch を走らせる)、B-7 Phase 1 + B-7a で **changed/added section を source とする pair だけ再生成し、unchanged source は前回値を継承する** 部分再生成経路を追加した (`stages.related_sections.action = "regenerated_partial"`)。

#### 判定順序

`_related_sections_fast_path_decision` ([spec_anchor/core.py:1395](spec_anchor/core.py#L1395) 周辺) の戻り値に `can_partial: bool` を追加し、`_generate_related_sections` ([spec_anchor/core.py:2392](spec_anchor/core.py#L2392) 周辺) は次の優先順位で経路を選ぶ。

1. `run_full=True` → `fallback_regenerated` (`--all` / `--rebuild` 経路)
2. `retrieval_index_status` が `success` / `skipped_unchanged` 以外 → `fallback_regenerated` (retrieval が壊れていれば related_sections 経路も諦める)
3. `related_sections_state.json` が無い → `fallback_regenerated` (= 初回扱い)
4. 非 section 指紋 (`schema_version` / `candidate_generation_config_fingerprint` / `selection_prompt_version` / `selection_model` / `selection_provider` / `selection_effort` / `artifact_schema_version`) のいずれかが不一致 → `fallback_regenerated` (= 設定変更時の意図的全件再評価)
5. `section_list_fingerprint` と `section_hash_fingerprint` が両方一致 → `skipped_unchanged` (§5.7.1 fast path)
6. section 指紋が不一致だが `section_diff_sets` (B-3b で計算済) に `added_section_ids` / `changed_section_ids` / `removed_section_ids` の少なくとも 1 件がある → **`regenerated_partial`** (本節)
7. それ以外 → `fallback_regenerated`

#### 部分再生成の動作

`generate_related_sections_partial_result` ([spec_anchor/related_sections.py:1100](spec_anchor/related_sections.py#L1100) 周辺) は次のように動く。

1. `generate_related_section_candidates_result(sections, source_section_ids=changed_or_added_source_ids, ...)` を呼ぶ。`source_section_ids` が指定された場合、内部で `source_records` を絞り込んで 4 channel (`_add_markdown_link_candidates` / `_add_shared_identifier_candidates` / `_add_search_key_candidates` / `_add_qdrant_section_hybrid_candidates`) に渡す。`records_by_id` (target lookup) と inverted index は **全 records から構築** するため、target 側全 section へのリンクは保たれる
2. `select_related_sections_result(..., candidates=filtered_candidates, source_section_ids=changed_or_added_source_ids)` で LLM typing batch を実行。changed/added source を含む pair の cache miss だけ LLM call が走る (= 1 source × 1 batch、`actual_call_count == 1`)
3. `previous_related_sections` (= `_read_previous_section_metadata` 経由で取得した前回 selected_related_sections) と merge:
   - **changed/added source**: 新 selection 結果を使う
   - **unchanged source**: 前回値を継承。ただし target が `removed_source_ids` に含まれる relation は除外
   - **removed source**: 最終 artifact から除外
4. `_progress_action(action="regenerated_partial", ..., candidate_generation_elapsed_sec=<float>, selection_elapsed_sec=<float>, candidate_generation_source_count=<int>, candidate_generation_partial_mode="source_changed_only")` で stage 別 timing を記録

`RelatedSectionCandidateGeneration` / `RelatedSectionSelection` の dataclass に `elapsed_sec: float` field を持たせ、それぞれの API 内部で `time.perf_counter()` で計測する。

#### diagnostics の制限フラグ

`generate_related_sections_partial_result` の `partial_diagnostic` (reason_code = `related_sections_partial_regenerated`) は次フィールドで partial 経路の trade-off を明示する。

| field | 値 | 意味 |
|---|---|---|
| `partial_regeneration` | `true` | 部分再生成経路に乗ったこと |
| `partial_mode` | `"source_changed_only"` | source 中心 partial であることの表明 |
| `source_centric_partial` / `source_centric_partial_regeneration` | `true` | 同上 (人間向け表現の冗長性) |
| `unchanged_source_inheritance` | `true` | unchanged source は前回値継承 |
| `removed_source_exclusion` | `true` | removed source は artifact から除外 |
| `changed_target_relations_inherited` | `true` | **target 変化分の relation は前回継承される (= 完全な意味更新ではない)** |
| `requires_full_regeneration_for_complete_target_recheck` | `true` | **完全な target recheck には `--all` が必要** |
| `changed_source_section_ids` / `changed_target_section_ids` | `list[str]` | 再 typing した source / target id |
| `inherited_source_section_ids` / `removed_source_section_ids` | `list[str]` | 継承 / 除外した source id |
| `candidate_count` / `candidate_count_for_selection` / `selection_source_count` / `inherited_source_count` / `removed_source_count` / `batch_count` / `llm_calls` | `int` | 各種カウンタ |

加えて `generate_related_section_candidates_result` の **内部生成** diagnostic (reason_code = `related_section_candidate_generation_scope`) が `candidate_generation_partial_mode` / `candidate_generation_source_count` / `candidate_generation_elapsed_sec` を表明する。この diagnostic は core.py や `partial_diagnostic` の固定値経由ではなく `source_records` の絞り込みを直接反映するため、partial 化の本物性を検証する unit test (`test_b7a_related_sections_candidate_generation_source_partial`) はこの diagnostic を assertion 対象にする。

`requires_full_regeneration_for_complete_target_recheck` と `changed_target_relations_inherited` の 2 フラグは **partial 経路の安全性を後続 Agent / 人間に伝える safety flag** であり、`source_centric_partial` だけでは「source 中心 partial」の意味は伝わるが「target 変化分の関連性 / conflict 判定が前回継承される」の含意までは明示されないため必須とする (B-7 Phase 1 で GPT 指摘により追加された設計)。

#### trade-off と運用指針

- partial 経路は **日常編集向けの高速経路**: 1 文字編集、typo 修正、軽微な内容変更で `related_sections.elapsed_sec` を ~5s 以下に圧縮する。50 section fixture / Section 01 1 文字編集の S2 で wall 99s → 16.3s、`related_sections.elapsed_sec` 50.4s → 4.666s を実測 (`doc/監査/B-5_cache_measurement_2026-05-14.md` §4.x.2.2 参照)
- partial 経路は **完全監査向けの経路ではない**: changed section が他 section の関連先として現れる場合、`unchanged source` 側の関連性 / conflict 判定は前回継承される。Section の意味が semantic 的に変わった場合、または release 前 / audit 前は `/spec-core --all` で完全再評価する
- target 側 candidate の partial 化 (target が changed の pair の再 typing) は本実装の scope 外。将来 task として切り出す候補

#### 既存契約への影響

- `related_sections_status` の取り得る値は不変 (`success` / `skipped_unchanged` / `failed` / `blocked`)。partial 経路は `success` の一種
- `stages.related_sections.action` の取り得る値: `skipped_unchanged` / **`regenerated_partial`** (新規) / `generated` (`--all`) / `fallback_regenerated` / `failed`
- `fallback_regenerated` の挙動は不変 (`prompt_version` / `metadata_version` / schema bump 時に全体再生成)
- `--all` 経路 (`generated`) の挙動は不変
- `skipped_unchanged` 経路の挙動は不変

### 5.8 Conflict Review Items

Conflict Candidate Triage stage で `triage.send_to_review = true` と判定された SpecClaim pair について、CLI は該当 SpecClaim pair の `evidence_span` (Source Specs 内の根拠範囲)、両 claim の `source_section_id` の本文、関連する Purpose / Core Concept、`triage.reason` / `triage.confidence` を LLM に渡して Conflict Review judge を実行する。Related Sections の `relation_hint` や旧 Related Sections conflict referral 由来 pair は本 stage の入力にしない (SCD-033)。Conflict Review pipeline は Conflict Candidate Detection の分類とは独立した judge call で、Purpose / Core Concept / Source Specs grounding を必須とする。

`conflict_review.evaluate_conflicts` は `judge` callable を引数として受け取る薄い orchestration である。Purpose / Core Concept / Source Specs を実際に grounding として LLM に渡す責務は呼び出し側が用意する `judge` 実装が担う。core.py の通常経路では `_EvidenceGroundedConflictJudge` ラッパーが Purpose と Core Concept のテキストとハッシュを毎 request に付与する。`evaluate_conflicts` を単体で呼ぶ caller (テストや外部ツール) も同等の grounding を持つ judge を渡す責任を負う。

Source Specs grounding は section_a / section_b の本文を judge prompt に含める形で行う。周辺 section や全 corpus を judge に渡すことはしない。judge が追加 context を必要とする場合は、`evidence_terms` を経由した snippet 抽出のみを使い、Source Specs 全文の盲目的注入は CLAUDE.md ルール 4 に反するため行わない。

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

### 5.9 Related Typing Cache の entry 単位再構築

`RelatedTypingCache` ([spec_anchor/related_typing_cache.py:48](../spec_anchor/related_typing_cache.py#L48)) は Related Sections の typing LLM 出力 (= candidate pair に対する relation type / why 判定) を **(source_section_id, target_section_id) pair 単位** で永続化する。cache key は `make_related_typing_cache_key(source_section_id, target_section_id, source_hash, target_hash, prompt_version, ...)` で構成され、永続化形式は `.spec-anchor/cache/related_typing_cache.json` 内の `entries` map (1 file = 全 entry の dict)。

[`spec_anchor/related_sections.py:520`](../spec_anchor/related_sections.py#L520) 周辺の typing 利用箇所で `cache.get(key)` が hit すれば LLM typing call を skip し、miss すれば LLM call で type 判定を行う。changed section が source または target になる pair の cache 経路は miss、それ以外の pair は hit する設計。

B-5 計測 (`doc/監査/B-5_cache_measurement_2026-05-14.md`) で 50 section fixture に対し:

- 初期 build で 1632 entry (50 section × 平均 candidate per section)
- 1 section の本文変更で entry +82 (旧 entry は残る、新 cache key で +82 entry 追加 = changed section が source/target になる pair の再 typing 分)
- 1 section の heading 変更で entry +82 (新 source_section_id の pair が cache に追加、古い entry は残る)
- `--all` で entry 1796 → 1632 (= initial build 同等まで wipe + 再生成)

`RelatedTypingCache` の永続化レイヤは 1 file = 全 entry の構成で、entry 追加時に file 全体を rewrite する。50 section / 1632〜1796 entry の規模では I/O コストは観測されない (wall time 1.0s = 全 stage skipped_unchanged のケース)。大規模 spec (500 section, ~50000 entry) でのコストは未確認 (B-6 検討範囲)。

### 5.10 SpecClaim と Conflict Candidate Detection (内部設計参照)

SpecClaim、Claim Retrieval、LLM triage、conflict_candidate_pairs の内部設計詳細は `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` に集約する。実装はその文書の §1-§17 を一次資料として参照する。

DESIGN.ja.md と SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md の整合:

- §0 implementation tracker (本ファイル): SpecClaim 経路の実装 task と Phase 5 削除 task を `[ ]` で記録する。
- §3.4 LLM Generation Policy: `[llm.stage_routing]` 許可 stage に `spec_claims` / `conflict_candidate_triage` / `conflict_review` を含める。`claim_retrieval` は LLM を呼ばないため stage_routing 対象外。
- §3.5 Limits: Conflict Candidate Detection の処理量上限は `[conflict_candidate_detection]` で管理する。
- §5.4 LLM Selection: Related Sections は conflict 判定を持たない (SCD-003)。
- §5.5 Related Sections Schema: 旧 Related Sections conflict referral field を持たない。
- §5.8 Conflict Review Items: 入力境界は SpecClaim pair / evidence / triage result (SCD-033)。Related Sections 由来 pair を受け取らない。
- §7 `/spec-core` フロー: SpecClaim 抽出 → Claim Retrieval → LLM triage → Conflict Review の 4 stage で構成する。
- §5.10 (本節): SpecClaim / Claim Retrieval / LLM triage の詳細 schema と prompt contract は参照先文書を正本にし、本ファイルでは他節との境界だけを固定する。

SpecClaim 経路の version 定数 (`SPEC_CLAIM_SCHEMA_VERSION` / `SPEC_CLAIM_PROMPT_VERSION` / `SPEC_CLAIM_IDENTITY_VERSION` / `SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION` / `CONFLICT_CANDIDATE_SCHEMA_VERSION` / `CONFLICT_TRIAGE_PROMPT_VERSION`) は、実装 module (`spec_anchor/spec_claims.py` / `spec_anchor/conflict_candidates.py`) に置く。bump 条件は `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` §9.1 を参照。

保持ファイルと cache の物理配置 (`.spec-anchor/context/spec_claims.jsonl` / `.spec-anchor/context/conflict_candidate_pairs.jsonl` / `.spec-anchor/state/spec_claims_state.json` / `.spec-anchor/state/conflict_candidate_pairs_state.json`、claim-level Qdrant collection `[retrieval].claim_collection`) は `doc/EXTERNAL_DESIGN.ja.md` §4.1 と `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` §4 を参照する。

## 6. Chapter Key Anchor

Chapter Key Anchor は、章全体の重要テーマ、判断軸、主要 section への入口を、LLM が章単位で抽象化して生成する。`/spec-inject` の path ② が章単位エントリポイントとして利用する。

artifact: `.spec-anchor/context/chapter_anchors.json`

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
extract SpecClaims for changed sections
run Claim Retrieval for changed claims
run LLM triage on candidate SpecClaim pairs
update Conflict Review Items from triage.send_to_review = true pairs
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
regenerate all SpecClaims
run Claim Retrieval for all claims
run LLM triage on all candidate SpecClaim pairs
update Conflict Review Items from triage.send_to_review = true pairs
regenerate Chapter Key Anchors
write context artifacts atomically
write freshness
return CoreResult
```

## 8. `/spec-inject` と `/spec-realign`

slash command は Agent / LLM に探索手順を指示する。CLI は次の参照操作を提供する。CLAUDE.md ルール 4 の `evidence_origin` enum (Purpose / Core Concept / Source Specs / Conflict Review Item) を 4 path がカバーする。各 `inject-*` および `realign` は内部で freshness gate / pending conflict gate / watcher gate を通すので、Agent が事前 probe を呼ぶ必要はない (F-C 採用後の構造)。

| 操作 | コマンド | 戻り値 | 対応 path |
|---|---|---|---|
| section-level hybrid retrieval | `spec-anchor inject-search "<query>"` | top-K の section payload (source_document_id / source_section_id / source_span / heading / summary / search_keys / identifiers / related_sections / score) | path ① |
| section payload lookup | `spec-anchor inject-section "<id>" [<id>...]` | 指定 section_id の payload 一括取得。`related_sections` 辿り用 | path ① の hop traversal |
| 章 anchor 取得 | `spec-anchor inject-chapters` | `chapter_anchors.json` の path (Agent が `Read` で読み、関連章を特定する) | path ② |
| Purpose / Core Concept 取得 | `spec-anchor inject-purpose` | `purpose` (全文) + `core_concept_path` (Agent が `Read` で必要箇所を部分取得) | path ③ |
| Conflict Review Items 取得 | `spec-anchor inject-conflicts` | `status = resolved` かつ stale でない items | path ④ |

Agent / LLM はこれらを使い、課題の性質に応じて 4 path を組み合わせる。

| 課題タイプ | 主 path | 補強 |
|---|---|---|
| 具体的 API / 識別子 | ① | ③、④ |
| 全体方針 / 抽象的 | ② | ①、③、④ |
| Purpose / Core Concept 直接質問 | ③ | ①、② |
| 過去判断の継続 | ④ | ①、③ |

CLI は探索方針を自律的に決めない。Agent / LLM は `inject-search` の戻り値の `related_sections` 配列を辿る再帰探索を、課題への寄与が無くなったと判断した時点で打ち切る。再帰深さの上限は CLI 設定では持たず、Agent / LLM 側の判断に委ねる。

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
