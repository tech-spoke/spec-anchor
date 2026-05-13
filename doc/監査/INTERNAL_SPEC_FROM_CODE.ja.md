# 内部仕様書再生成（コード由来）

作成日: 2026-05-13

本書は `spec_grag/` 配下のコードのみから再生成した監査用の内部仕様である。既存の `doc/` 配下の設計書は ground truth として使わない。Purpose / Core Concept のファイルを読む処理がコード中に存在する箇所は「入出力事実」として記録するが、その内容は本 Phase の判断材料にしない。

## 1. 対象

対象ファイルは `spec_grag/` 配下の Python モジュール全 24 ファイル。

- `spec_grag/__init__.py`
- `spec_grag/__main__.py`
- `spec_grag/artifacts.py`
- `spec_grag/chapter_anchors.py`
- `spec_grag/cli.py`
- `spec_grag/config.py`
- `spec_grag/conflict_review.py`
- `spec_grag/core.py`
- `spec_grag/core_lock.py`
- `spec_grag/core_progress.py`
- `spec_grag/errors.py`
- `spec_grag/freshness.py`
- `spec_grag/inject.py`
- `spec_grag/llm_provider.py`
- `spec_grag/project_setup.py`
- `spec_grag/realign.py`
- `spec_grag/related_sections.py`
- `spec_grag/related_typing_cache.py`
- `spec_grag/retrieval_index.py`
- `spec_grag/section_metadata.py`
- `spec_grag/section_parser.py`
- `spec_grag/section_payload.py`
- `spec_grag/setup.py`
- `spec_grag/watcher.py`

未読扱いのモジュールはない。

## 2. 全体責務

`spec_grag` は、Markdown の Source Specs を Section 単位に分割し、LLM で Section metadata / Related Sections / Conflict Review / Chapter Anchors を生成し、Qdrant + BGE-M3 dense/sparse ベクトルによる Section Retrieval Index を作成する。Agent 側へは freshness gate、制約検証、検索、Section payload、Purpose / Core Concept、Conflict Review Item を CLI で返す。

主要な実行入口は `spec_grag/cli.py` の `main()` / `slash_main()` / `watch_main()` である。`build_main_parser()` は `core`、`inject`、`inject-search`、`inject-section`、`inject-chapters`、`inject-purpose`、`inject-conflicts`、`realign`、`watch` を構成する（`spec_grag/cli.py:46`, `spec_grag/cli.py:278`, `spec_grag/cli.py:307`, `spec_grag/cli.py:318`）。

## 3. `/spec-core` データフロー

`run_spec_core()` はロック取得、watcher 競合判定、設定読込、進捗ファイル初期化を行い、実処理を `_run_spec_core_unlocked()` に委譲する（`spec_grag/core.py:47`, `spec_grag/core.py:186`）。共有ロックは `.spec-grag/state/core_update.lock.json` を使い、atomic な `O_EXCL` 作成と heartbeat で多重更新を防ぐ（`spec_grag/core_lock.py:48`, `spec_grag/core_lock.py:52`, `spec_grag/core_lock.py:183`）。

`_run_spec_core_unlocked()` の処理順序は次の通り。

1. `.spec-grag/config.toml` をロードし、Purpose / Core Concept の参照ファイルを読み、`ContextArtifactStore` を作る（`spec_grag/core.py:1003`, `spec_grag/core.py:1280`, `spec_grag/artifacts.py:54`）。
2. Source Specs を Markdown 見出しで Section に分割する。Section は `section_id` / `source_section_id` / `stable_section_uid` / `source_document_id` / `source_span` / `source_hash` / `semantic_hash` / `chapter_id` / `text` を持つ（`spec_grag/section_parser.py:24`, `spec_grag/section_parser.py:38`）。
3. 既存 Section metadata は `section_manifest.json` と Qdrant payload から読める場合に再利用する。Qdrant から読む経路は embedding provider が `flagembedding`、vector store が `qdrant` のときだけ動く（`spec_grag/core.py:1023`, `spec_grag/core.py:1058`）。
4. `generate_section_metadata_result()` が Section Summary / Search Keys / Identifiers を生成する。LLM 結果はキャッシュ可能で、provider 成功時に summary が欠けると fallback summary を補う（`spec_grag/section_metadata.py:240`, `spec_grag/section_metadata.py:562`, `spec_grag/section_metadata.py:1170`）。
5. `_upsert_section_collection_if_enabled()` が Qdrant Section collection へ BGE-M3 dense/sparse embedding を upsert する。provider が標準でない場合は `skipped`、例外時は `failed` を返し、core 自体は止めない（`spec_grag/core.py:423`, `spec_grag/core.py:1154`, `spec_grag/core.py:1216`）。
6. `_generate_related_sections()` が candidate 生成、LLM による relation typing、validation をまとめる（`spec_grag/core.py:432`, `spec_grag/core.py:1549`, `spec_grag/related_sections.py:1010`）。
7. Related Sections は Qdrant payload に `set_payload` で反映されるが、この失敗も core は止めない（`spec_grag/core.py:456`, `spec_grag/core.py:1223`, `spec_grag/core.py:1263`）。
8. Related Sections のうち `possible_conflict=true`、または legacy pattern signal に合う pair が Conflict Review 候補になる（`spec_grag/core.py:1703`）。
9. `evaluate_conflicts()` が Conflict Review Item を生成する。最終 decision は `human_acknowledgement` がないと適用できない（`spec_grag/conflict_review.py:377`, `spec_grag/conflict_review.py:488`）。
10. `generate_chapter_anchors()` が chapter ごとの anchor を作る。LLM 失敗・未設定・不正出力時は mechanical anchor に fallback し、`fallback_chapter_ids` に記録する（`spec_grag/chapter_anchors.py:125`, `spec_grag/chapter_anchors.py:247`, `spec_grag/chapter_anchors.py:260`）。
11. `build_freshness_report()` で freshness を作り、`section_manifest`、`conflict_review_items`、`chapter_anchors`、必要なら `freshness` を atomic write する（`spec_grag/core.py:631`, `spec_grag/artifacts.py:193`）。
12. 戻り値は `status`、updated/skipped/failed sources、`retrieval_index_status`、potential conflicts、freshness などを含む（`spec_grag/core.py:669`）。

## 4. `/spec-inject` 系データフロー

`run_spec_inject()` は LLM provider を使わない。freshness gate を通し、Agent から渡された constraints を検証するだけで、fallback constraints は生成しない（`spec_grag/inject.py:66`, `spec_grag/inject.py:84`, `spec_grag/inject.py:117`）。

`run_inject_search()` は Qdrant Section collection に対して live hybrid retrieval を実行する。FlagEmbedding BGE-M3 provider と `QdrantHybridRetriever` を初期化できない場合は例外を投げず、structured warning を返す（`spec_grag/inject.py:870`, `spec_grag/inject.py:904`, `spec_grag/inject.py:924`）。

`run_inject_section()` は Qdrant の `source_section_id` filter で payload を取得する。欠落 ID は missing として返す（`spec_grag/inject.py:688`, `spec_grag/section_payload.py:30`）。

`run_inject_chapters()` は `.spec-grag/context/chapter_anchors.json` を返す（`spec_grag/inject.py:752`）。`run_inject_purpose()` は設定された Purpose / Core Concept ファイルの内容を返す（`spec_grag/inject.py:779`）。`run_inject_conflicts()` は resolved かつ stale でない Conflict Review Item だけを返す（`spec_grag/inject.py:821`）。

## 5. `/spec-realign` データフロー

`run_spec_realign()` は freshness / inject gate を使い、Agent が提示した answer を構造化する。`/spec-core` の LLM provider は使わない（`spec_grag/realign.py:59`, `spec_grag/realign.py:189`）。

## 6. Watcher データフロー

`run_spec_grag_watch()` / `run_watcher_cycle()` は設定から watch 対象を読み、Source Specs と Purpose / Core Concept の snapshot を作り、差分がある場合は queue と freshness を更新して core runner を呼ぶ（`spec_grag/watcher.py:85`, `spec_grag/watcher.py:209`, `spec_grag/watcher.py:633`, `spec_grag/watcher.py:702`）。watcher は stale lock cleanup、state / queue / freshness の atomic write、idle freshness の生成も担当する（`spec_grag/watcher.py:1118`, `spec_grag/watcher.py:1287`, `spec_grag/watcher.py:1301`）。

## 7. モジュール別仕様

| モジュール | 責務 | 主な入出力 / 外部接続 | 証跡 |
|---|---|---|---|
| `__init__.py` | package version を返す。 | `importlib.metadata.version("spec-grag")`。 | `spec_grag/__init__.py:8` |
| `__main__.py` | package 実行時に CLI へ委譲する。 | CLI argv。 | `spec_grag/__main__.py` |
| `artifacts.py` | `.spec-grag/state` と `.spec-grag/context` の成果物保存。 | JSON / bytes atomic write。 | `spec_grag/artifacts.py:31`, `spec_grag/artifacts.py:54`, `spec_grag/artifacts.py:193` |
| `chapter_anchors.py` | chapter 単位の anchor 生成、cache、mechanical fallback。 | LLM provider、`.spec-grag/cache/chapter_anchors`。 | `spec_grag/chapter_anchors.py:58`, `spec_grag/chapter_anchors.py:125`, `spec_grag/chapter_anchors.py:459` |
| `cli.py` | argparse と command dispatch。 | stdout JSON、exit code。 | `spec_grag/cli.py:46`, `spec_grag/cli.py:278`, `spec_grag/cli.py:634` |
| `config.py` | `.spec-grag/config.toml` の検証と dataclass 化。 | TOML、dotenv、glob。 | `spec_grag/config.py:158`, `spec_grag/config.py:281`, `spec_grag/config.py:480` |
| `conflict_review.py` | conflict 候補選別、judge 呼び出し、human decision 適用、stale 判定。 | LLM judge、Conflict Review Item JSON。 | `spec_grag/conflict_review.py:239`, `spec_grag/conflict_review.py:377`, `spec_grag/conflict_review.py:488`, `spec_grag/conflict_review.py:612` |
| `core.py` | `/spec-core` の統合 pipeline。 | Source Specs、LLM、Qdrant、artifacts、freshness。 | `spec_grag/core.py:47`, `spec_grag/core.py:186`, `spec_grag/core.py:669` |
| `core_lock.py` | core / watcher 更新ロック。 | `.spec-grag/state/core_update.lock.json`。 | `spec_grag/core_lock.py:48`, `spec_grag/core_lock.py:52`, `spec_grag/core_lock.py:183` |
| `core_progress.py` | 長時間 core 実行の進捗永続化。 | `.spec-grag/state/core_progress.json`。 | `spec_grag/core_progress.py:23`, `spec_grag/core_progress.py:48`, `spec_grag/core_progress.py:193` |
| `errors.py` | diagnostic と共通例外型。 | 例外オブジェクト。 | `spec_grag/errors.py:10`, `spec_grag/errors.py:35` |
| `freshness.py` | freshness report と gate decision。 | blocking reasons、warnings、diagnostics。 | `spec_grag/freshness.py:63`, `spec_grag/freshness.py:207`, `spec_grag/freshness.py:359` |
| `inject.py` | Agent 注入用 context / search / payload lookup。 | freshness artifact、Qdrant、config、constraints。 | `spec_grag/inject.py:66`, `spec_grag/inject.py:688`, `spec_grag/inject.py:870` |
| `llm_provider.py` | Fake/Subprocess LLM provider、schema、retry、cache。 | `codex` / `claude` subprocess、JSON schema、env debug。 | `spec_grag/llm_provider.py:252`, `spec_grag/llm_provider.py:288`, `spec_grag/llm_provider.py:383`, `spec_grag/llm_provider.py:454` |
| `project_setup.py` | project/system setup と readiness checks。 | config files、Qdrant service check、provider availability。 | `spec_grag/project_setup.py:42`, `spec_grag/project_setup.py:204`, `spec_grag/project_setup.py:291` |
| `realign.py` | freshness gate 後、Agent answer を制約別に構造化。 | inject result、answer JSON/text。 | `spec_grag/realign.py:59`, `spec_grag/realign.py:189` |
| `related_sections.py` | Related Section 候補生成、LLM relation typing、validation。 | Markdown links、identifiers、search keys、Qdrant/InMemory hybrid retrieval、LLM cache。 | `spec_grag/related_sections.py:304`, `spec_grag/related_sections.py:441`, `spec_grag/related_sections.py:756`, `spec_grag/related_sections.py:1010` |
| `related_typing_cache.py` | Related Sections の pair/batch cache。 | JSON cache。 | `spec_grag/related_typing_cache.py:24`, `spec_grag/related_typing_cache.py:48` |
| `retrieval_index.py` | Qdrant + BGE-M3 dense/sparse + RRF の Section Retrieval Index。 | FlagEmbedding、Qdrant、in-memory fake retrieval。 | `spec_grag/retrieval_index.py:1`, `spec_grag/retrieval_index.py:167`, `spec_grag/retrieval_index.py:364`, `spec_grag/retrieval_index.py:832` |
| `section_metadata.py` | Section summary/search keys/identifiers 生成。 | LLM provider、cache、fallback summary。 | `spec_grag/section_metadata.py:240`, `spec_grag/section_metadata.py:531`, `spec_grag/section_metadata.py:562` |
| `section_parser.py` | Markdown 見出し単位の Section 分割。 | Markdown file/text。 | `spec_grag/section_parser.py:24`, `spec_grag/section_parser.py:38`, `spec_grag/section_parser.py:140` |
| `section_payload.py` | Qdrant payload lookup と metadata shape 変換。 | Qdrant scroll API。 | `spec_grag/section_payload.py:30`, `spec_grag/section_payload.py:93` |
| `setup.py` | setup API の薄い wrapper。 | `project_setup.py` への委譲。 | `spec_grag/setup.py:15`, `spec_grag/setup.py:49` |
| `watcher.py` | polling watcher、snapshot diff、queue、core runner 呼び出し。 | Source files、state/queue/freshness JSON、lock。 | `spec_grag/watcher.py:85`, `spec_grag/watcher.py:209`, `spec_grag/watcher.py:633` |

## 8. 設定キーの実消費箇所

`[sources]` は include/exclude glob と source root を読み、対象ファイルを project root 内に制限する（`spec_grag/config.py:281`, `spec_grag/config.py:300`, `spec_grag/config.py:321`）。

`[core]` は Purpose / Core Concept file path と artifact 更新先の root を解決する（`spec_grag/config.py:329`）。core はこの path から text/hash を読み、Conflict Review judge request に context として渡す（`spec_grag/core.py:1852`, `spec_grag/core.py:1946`）。

`[context]` は context directory を決める（`spec_grag/config.py:349`, `spec_grag/artifacts.py:31`）。

`[section]` は Markdown heading の最大 level を決める（`spec_grag/config.py:355`, `spec_grag/section_parser.py:38`）。

`[section_metadata]` は summary/search key/identifier の enabled state と version を決める（`spec_grag/config.py:360`, `spec_grag/section_metadata.py:666`）。

`[chapter_anchor]` は chapter anchor version をロードする（`spec_grag/config.py:374`）。

`[llm]` と `[llm.providers]` は stage routing、model、effort、timeout、retry、provider command を決める。provider 選択は明示 `--llm-provider`、stage routing、先頭 provider の順である（`spec_grag/config.py:379`, `spec_grag/config.py:396`, `spec_grag/llm_provider.py:331`）。

`[limits]` は summary/search keys/related/conflict/LLM batch の上限で使われる（`spec_grag/config.py:448`, `spec_grag/related_sections.py:2369`, `spec_grag/section_metadata.py:631`）。

`[retrieval]` は dense/sparse top-k、RRF、section collection、threshold、candidate top-k、final top-n をロードする（`spec_grag/config.py:105`, `spec_grag/config.py:480`）。一方で、Qdrant collection 名を実際に読む core / inject / related_sections の経路は `[vector_store].section_collection` を参照している（`spec_grag/core.py:1071`, `spec_grag/core.py:1178`, `spec_grag/core.py:1243`, `spec_grag/inject.py:954`, `spec_grag/related_sections.py:361`）。

`[embedding]` は標準では `provider=flagembedding`、`model=BAAI/bge-m3` を要求する（`spec_grag/config.py:497`）。

`[vector_store]` は標準では `provider=qdrant` と `url` だけを dataclass に持つ（`spec_grag/config.py:123`, `spec_grag/config.py:516`）。

`[watcher]` は enabled、interval、state/queue path、stale lock、include Purpose/Core Concept snapshot 等をロードする（`spec_grag/config.py:530`, `spec_grag/watcher.py:633`）。

## 9. 外部接続点

- File I/O: Source Specs 読込、`.spec-grag/config.toml`、`.env`、`.spec-grag/state/*.json`、`.spec-grag/context/*.json`、`.spec-grag/cache/**/*.json`（`spec_grag/config.py:22`, `spec_grag/artifacts.py:193`, `spec_grag/core_progress.py:193`）。
- LLM subprocess: `codex` / `claude` 単体 command を専用引数で展開し、JSON schema を強制する（`spec_grag/llm_provider.py:383`）。
- LLM fake: `SPEC_GRAG_FAKE_LLM` が truthy の場合は `FakeLlmProvider` を返す（`spec_grag/llm_provider.py:303`, `spec_grag/llm_provider.py:310`）。
- Debug logs: related prompt と provider invocation は env が有効な場合だけ `.spec-grag/state/_debug_*.jsonl` に追記され、失敗しても本処理を止めない（`spec_grag/related_sections.py:2498`, `spec_grag/related_sections.py:2523`, `spec_grag/llm_provider.py:454`）。
- Embedding: `FlagEmbedding.BGEM3FlagModel` を lazy import し、dense/sparse を返す（`spec_grag/retrieval_index.py:167`）。
- Vector store: Qdrant client を lazy import し、named dense/sparse vectors を collection に作成・検索・payload patch する（`spec_grag/retrieval_index.py:364`, `spec_grag/retrieval_index.py:726`, `spec_grag/retrieval_index.py:832`）。
- OS lock: core update lock は lock file、PID、hostname、heartbeat timestamp を使う（`spec_grag/core_lock.py:52`, `spec_grag/core_lock.py:280`）。

## 10. 内部不変条件

- Section ID は `source_document_id#ordinal-slug`、`stable_section_uid` は `source_document_id + ordinal` の hash 先頭 16 文字である（`spec_grag/section_parser.py:157`, `spec_grag/section_parser.py:158`）。
- `source_hash` は Section body の sha256、`semantic_hash` は whitespace normalize 後の sha256 である（`spec_grag/section_parser.py:153`, `spec_grag/section_parser.py:154`, `spec_grag/section_parser.py:155`）。
- Section source span は line/offset を保持するが、Qdrant payload にはそのまま保存されない（`spec_grag/section_parser.py:31`, `spec_grag/retrieval_index.py:707`）。
- Section embedding text は heading、summary、search_keys、identifiers から作られ、Section raw body は直接含めない（`spec_grag/retrieval_index.py:653`）。
- Qdrant schema は dense vector 名 `dense`、sparse vector 名 `sparse`、BGE-M3 dense size 1024、cosine、RRF を標準とする（`spec_grag/retrieval_index.py:35`, `spec_grag/retrieval_index.py:38`, `spec_grag/retrieval_index.py:40`, `spec_grag/retrieval_index.py:43`）。
- Qdrant upsert は payload list の enumerate index を point id とする（`spec_grag/retrieval_index.py:868`, `spec_grag/retrieval_index.py:873`）。
- Related Sections は evidence ではなく retrieval auxiliary としてマークされる（`spec_grag/related_sections.py:1053`, `spec_grag/related_sections.py:1057`, `spec_grag/related_sections.py:1060`）。
- Related Section LLM は supplied candidates 以外を探さないよう指示され、`possible_conflict` だけを flag し、`conflicts_with` は出さないよう指示される（`spec_grag/related_sections.py:1850`, `spec_grag/related_sections.py:1855`, `spec_grag/related_sections.py:1856`）。
- Conflict decision の final status は human acknowledgement 必須である（`spec_grag/conflict_review.py:488`）。
- Freshness gate は status が `fresh` / `degraded` のときだけ continue とする（`spec_grag/freshness.py:377`, `spec_grag/freshness.py:380`）。
- `/spec-inject` は constraints を生成せず、Agent 入力を検証するだけである（`spec_grag/inject.py:117`）。

