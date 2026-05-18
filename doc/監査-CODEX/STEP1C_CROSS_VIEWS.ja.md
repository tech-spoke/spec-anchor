# Step 1-C 横断観点表

## §0. 監査範囲

- commit hash: `2aa49dd03416f14ae8b2c9791361a58112ff5611`
- 前提とする Step 1-A 成果物: `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`
- 前提とする Step 1-B 成果物: `doc/監査-CODEX/STEP1B_FLOWS.ja.md`
- 観点 x CLI マトリクスで対象とする CLI 9 個: `core` / `inject` / `inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` / `realign` / `watch` (Step 1-B §0 行 9-19)

本 Step で新規 grep / line read した範囲:

```text
$ rg -n 'section_manifest\.json|conflict_review_items\.json|chapter_anchors\.json|freshness\.json|retrieval_index_state\.json|related_sections_state\.json|core_progress\.json|core_update\.lock\.json|watch_state\.json|watch_queue\.json|_debug_provider_invocations\.jsonl|_debug_related_prompts\.jsonl|related_typing_cache\.json' spec_grag tests pyproject.toml
$ rg -n 'build_empty_chapter_anchors|slash_main|watch_main|setup_project_main|setup_system_main|run_watcher_once|get_watcher_status' spec_grag tests pyproject.toml
$ rg -n 'ARTIFACT_FILENAMES|STATE_ARTIFACTS|CORE_ARTIFACT_ORDER|DEBUG_PROVIDER|RELATED_PROMPT|CACHE_FILE_NAME|PROGRESS_FILENAME|DEFAULT_CORE_LOCK_FILE|DEFAULT_STATE_FILE|DEFAULT_QUEUE_FILE|ContextArtifactStore|atomic_write_json|write_all|write\(' spec_grag/artifacts.py spec_grag/core.py spec_grag/core_lock.py spec_grag/core_progress.py spec_grag/llm_provider.py spec_grag/related_sections.py spec_grag/related_typing_cache.py spec_grag/watcher.py spec_grag/inject.py spec_grag/retrieval_index.py spec_grag/section_metadata.py spec_grag/chapter_anchors.py
$ rg -n 'section_collection|vector_store|state_file|queue_file|dense_top_k|sparse_top_k|section_dense_threshold|section_candidate_top_k|section_final_top_n|llm_batch|max_retries|timeout_sec|SPEC_GRAG_FAKE_LLM|SPEC_GRAG_FAKE_RETRIEVAL|SPEC_GRAG_DEBUG' spec_grag/core.py spec_grag/inject.py spec_grag/related_sections.py spec_grag/llm_provider.py spec_grag/retrieval_index.py spec_grag/watcher.py spec_grag/config.py
$ rg -n 'def _build_.*state|retrieval_index_state|related_sections_state|expected_state|schema_version' spec_grag/core.py spec_grag/freshness.py spec_grag/retrieval_index.py
$ rg -n 'task_prompt|conversation_context|agent_constraints|llm_provider|provider=|freshness_report|wait=|blocking=|env=' spec_grag tests pyproject.toml
$ rg -n 'run_spec_inject\(|run_spec_realign\(|select_llm_provider_config\(|run_watcher_cycle\(' spec_grag tests pyproject.toml
```

新規 grep が必要だった理由:

- §2 の保持ファイル artifact（生成・読込される保持ファイル）表で、Step 1-A §4 と Step 1-B §1-§9 だけでは schema 定義行、cache 書込行、debug JSONL 書込行、repo 全体の読込有無を同一表に転記できない行があった。
- §6.2 で、Step 1-B §B 行 465-474 の target 9 CLI 範囲 dead 候補が、tests / pyproject.toml / target 9 CLI 外の spec_grag 経路から参照されるかを repo 全体で確認する必要があった。
- 本 Step の新規調査コマンドは `spec_grag/`、`tests/`、`pyproject.toml` に限定した。
- 作業開始前の上位ルール確認として `CLAUDE.md` / `AGENTS.md` / `doc/EXTERNAL_DESIGN.ja.md` / `doc/TODO.ja.md` を読んだ。Step 1-C 成果物の根拠としては使用していない。

## §1. 外部接続点 x CLI のマトリクス

|  | core | inject | inject-search | inject-section | inject-chapters | inject-purpose | inject-conflicts | realign | watch |
|---|---|---|---|---|---|---|---|---|---|
| LLM provider (subprocess) | 呼ぶ (`spec_grag/core.py:302-349`, `spec_grag/llm_provider.py:252-285`; Step 1-B §1 行 55-59, 90) | 呼ばない (`spec_grag/inject.py:91`; Step 1-B §2 行 111, 128) | 呼ばない (`spec_grag/inject.py:870-954`; Step 1-B §3 行 152-161, 174-180) | 呼ばない (`spec_grag/inject.py:688-749`; Step 1-B §4 行 213) | 呼ばない (`spec_grag/inject.py:752-776`; Step 1-B §5 行 251) | 呼ばない (`spec_grag/inject.py:779-818`; Step 1-B §6 行 287) | 呼ばない (`spec_grag/inject.py:821-867`; Step 1-B §7 行 324) | 呼ばない (`spec_grag/realign.py:59-185`; Step 1-B §8 行 365-366) | 条件付き (queue がある場合 `run_spec_core_for_watcher` 経由で core を呼ぶ: `spec_grag/watcher.py:454-464`, `spec_grag/core.py:812-822`; Step 1-B §9 行 402-403) |
| Qdrant client | 条件付き (`embedding.provider == "flagembedding"` かつ `vector_store.provider == "qdrant"`: `spec_grag/core.py:1997-2013`, `spec_grag/retrieval_index.py:963-967`; Step 1-B §1 行 60-62, 91) | 呼ばない (`spec_grag/inject.py:66-151`; Step 1-B §2 行 131-137) | 呼ぶ (`spec_grag/inject.py:920-936`, `spec_grag/retrieval_index.py:398-435`; Step 1-B §3 行 157-159, 180) | 呼ぶ (`spec_grag/inject.py:727-741`, `spec_grag/section_payload.py:60-90`; Step 1-B §4 行 200-201, 221) | 呼ばない (`spec_grag/inject.py:752-776`; Step 1-B §5 行 251) | 呼ばない (`spec_grag/inject.py:779-818`; Step 1-B §6 行 287) | 呼ばない (`spec_grag/inject.py:821-867`; Step 1-B §7 行 324) | 呼ばない (`spec_grag/realign.py:103-120` 経由の inject は Qdrant を呼ばない; Step 1-B §8 行 349, 368-374) | 条件付き (queue がある場合 core 経由: `spec_grag/watcher.py:454-464`; Step 1-B §9 行 402-403) |
| FlagEmbedding (BGE-M3) | 条件付き (`embedding.provider == "flagembedding"` かつ upsert input がある場合: `spec_grag/core.py:1997-2013`, `spec_grag/retrieval_index.py:1007-1014`; Step 1-B §1 行 60-62, 92) | 呼ばない (`spec_grag/inject.py:66-151`; Step 1-B §2 行 131-137) | 呼ぶ (`spec_grag/inject.py:916-924`; Step 1-B §3 行 156-158, 179) | 呼ばない (`spec_grag/section_payload.py:60-90`; Step 1-B §4 行 200-201, 216-221) | 呼ばない (`spec_grag/inject.py:752-776`; Step 1-B §5 行 251) | 呼ばない (`spec_grag/inject.py:779-818`; Step 1-B §6 行 287) | 呼ばない (`spec_grag/inject.py:821-867`; Step 1-B §7 行 324) | 呼ばない (`spec_grag/realign.py:59-185`; Step 1-B §8 行 365-374) | 条件付き (queue がある場合 core 経由: `spec_grag/watcher.py:454-464`; Step 1-B §9 行 402-403) |
| file I/O: `.spec-grag/config.toml` | 呼ぶ (`spec_grag/core.py:96-104`, `spec_grag/config.py:163-170`; Step 1-B §1 行 48, 86) | 呼ぶ (`spec_grag/inject.py:599-623`; Step 1-B §2 行 112, 135-137; 新規 line read) | 呼ぶ (`spec_grag/inject.py:957-969`; Step 1-B §3 行 154, 178) | 呼ぶ (`spec_grag/inject.py:711-713`, `spec_grag/inject.py:957-969`; Step 1-B §4 行 198, 220) | 呼ぶ (`spec_grag/inject.py:615-623`; Step 1-B §5 行 258) | 呼ぶ (`spec_grag/inject.py:792-804`; Step 1-B §6 行 274, 293) | 呼ぶ (`spec_grag/inject.py:615-623`; Step 1-B §7 行 331) | 呼ぶ (`spec_grag/realign.py:103-120` 経由の inject: Step 1-B §8 行 349, 373-374) | 呼ぶ (`spec_grag/watcher.py:645-650`, `spec_grag/config.py:163-170`; Step 1-B §9 行 391, 425) |
| file I/O: Source Specs (Markdown) | 呼ぶ (`spec_grag/core.py:2306-2319`; Step 1-B §1 行 57) | 呼ばない (`spec_grag/inject.py:66-151`; Step 1-B §2 行 131-137) | 呼ばない (`spec_grag/inject.py:870-954`; Step 1-B §3 行 174-180) | 呼ばない (`spec_grag/inject.py:688-749`; Step 1-B §4 行 216-221) | 呼ばない (`spec_grag/inject.py:752-776`; Step 1-B §5 行 253-258) | 呼ばない (`spec_grag/inject.py:779-818`; Step 1-B §6 行 289-294) | 呼ばない (`spec_grag/inject.py:821-867`; Step 1-B §7 行 326-331) | 呼ばない (`spec_grag/realign.py:59-185`; Step 1-B §8 行 368-374) | 呼ぶ (`spec_grag/watcher.py:702-732`; Step 1-B §9 行 394, 427) |
| file I/O: Purpose / Core Concept | 呼ぶ (`spec_grag/core.py:255-258`, `spec_grag/core.py:2220-2223`; Step 1-B §1 行 52, 87) | 呼ばない (`spec_grag/inject.py:66-151`; Step 1-B §2 行 131-137) | 呼ばない (`spec_grag/inject.py:870-954`; Step 1-B §3 行 174-180) | 呼ばない (`spec_grag/inject.py:688-749`; Step 1-B §4 行 216-221) | 呼ばない (`spec_grag/inject.py:752-776`; Step 1-B §5 行 253-258) | 呼ぶ (`spec_grag/inject.py:803-804`, `spec_grag/inject.py:1006-1020`; Step 1-B §6 行 274-275, 294) | 呼ばない (`spec_grag/inject.py:821-867`; Step 1-B §7 行 326-331) | 呼ばない (`spec_grag/realign.py:59-185`; Step 1-B §8 行 368-374) | 条件付き (queue がある場合 core 経由: `spec_grag/watcher.py:454-464`; Step 1-B §9 行 402-403) |
| file I/O: `.spec-grag/state/*.json` | 呼ぶ (`spec_grag/core.py:131-153`, `spec_grag/core.py:764-777`, `spec_grag/core.py:2103-2110`, `spec_grag/core.py:2553-2589`; Step 1-B §1 行 50, 68, 88-89) | 呼ぶ (`spec_grag/inject.py:599-612`; Step 1-B §2 行 112, 136) | 呼ばない (`spec_grag/inject.py:870-954`; Step 1-B §3 行 174-180) | 呼ばない (`spec_grag/inject.py:688-749`; Step 1-B §4 行 216-221) | 呼ばない (`spec_grag/inject.py:752-776`; Step 1-B §5 行 253-258) | 呼ばない (`spec_grag/inject.py:779-818`; Step 1-B §6 行 289-294) | 呼ばない (`spec_grag/inject.py:821-867`; Step 1-B §7 行 326-331) | 呼ぶ (`spec_grag/realign.py:103-120` 経由の freshness read; Step 1-B §8 行 373) | 呼ぶ (`spec_grag/watcher.py:246-255`, `spec_grag/watcher.py:967-1000`, `spec_grag/core_lock.py:63-81`; Step 1-B §9 行 393, 398, 425-428) |
| file I/O: `.spec-grag/context/*.json` | 呼ぶ (`spec_grag/core.py:265-270`, `spec_grag/core.py:764-777`; Step 1-B §1 行 53, 68) | 呼ぶ (`spec_grag/inject.py:123-126`, `spec_grag/inject.py:450-453`; Step 1-B §2 行 115, 137) | 呼ばない (`spec_grag/inject.py:870-954`; Step 1-B §3 行 174-180) | 呼ばない (`spec_grag/inject.py:688-749`; Step 1-B §4 行 216-221) | 呼ぶ (`spec_grag/inject.py:767`; Step 1-B §5 行 238-240, 257) | 呼ばない (`spec_grag/inject.py:779-818`; Step 1-B §6 行 289-294) | 呼ぶ (`spec_grag/inject.py:835-836`, `spec_grag/inject.py:450-453`; Step 1-B §7 行 310-311, 330) | 呼ぶ (`spec_grag/realign.py:103-120` 経由の conflict read; Step 1-B §8 行 374) | 条件付き (queue がある場合 core 経由: `spec_grag/watcher.py:454-464`; Step 1-B §9 行 402-403) |
| file I/O: `.spec-grag/cache/**` | 呼ぶ (`spec_grag/core.py:272-297`, `spec_grag/section_metadata.py:203-234`, `spec_grag/chapter_anchors.py:89-116`, `spec_grag/related_typing_cache.py:58-99`; Step 1-B §1 行 54) | 呼ばない (`spec_grag/inject.py:66-151`; Step 1-B §2 行 131-137) | 呼ばない (`spec_grag/inject.py:870-954`; Step 1-B §3 行 174-180) | 呼ばない (`spec_grag/inject.py:688-749`; Step 1-B §4 行 216-221) | 呼ばない (`spec_grag/inject.py:752-776`; Step 1-B §5 行 253-258) | 呼ばない (`spec_grag/inject.py:779-818`; Step 1-B §6 行 289-294) | 呼ばない (`spec_grag/inject.py:821-867`; Step 1-B §7 行 326-331) | 呼ばない (`spec_grag/realign.py:59-185`; Step 1-B §8 行 368-374) | 条件付き (queue がある場合 core 経由: `spec_grag/watcher.py:454-464`; Step 1-B §9 行 402-403) |
| file lock: `core_update.lock.json` | 呼ぶ (`spec_grag/core.py:131-153`, `spec_grag/core_lock.py:63-81`; Step 1-B §1 行 50, 89) | 呼ばない (`spec_grag/inject.py:66-151`; Step 1-B §2 行 131-137) | 呼ばない (`spec_grag/inject.py:870-954`; Step 1-B §3 行 174-180) | 呼ばない (`spec_grag/inject.py:688-749`; Step 1-B §4 行 216-221) | 呼ばない (`spec_grag/inject.py:752-776`; Step 1-B §5 行 253-258) | 呼ばない (`spec_grag/inject.py:779-818`; Step 1-B §6 行 289-294) | 呼ばない (`spec_grag/inject.py:821-867`; Step 1-B §7 行 326-331) | 呼ばない (`spec_grag/realign.py:59-185`; Step 1-B §8 行 368-374) | 呼ぶ (`spec_grag/watcher.py:321-328`, `spec_grag/core_lock.py:63-81`; Step 1-B §9 行 398, 428) |
| subprocess (LLM 以外) | 呼ばない (LLM provider subprocess は別行; Step 1-B §1 行 55-59, 90) | 呼ばない (Step 1-B §2 行 131-137) | 呼ばない (Step 1-B §3 行 174-180) | 呼ばない (Step 1-B §4 行 216-221) | 呼ばない (Step 1-B §5 行 253-258) | 呼ばない (Step 1-B §6 行 289-294) | 呼ばない (Step 1-B §7 行 326-331) | 呼ばない (Step 1-B §8 行 368-374) | 呼ばない (Step 1-B §9 行 421-429) |

## §2. artifact x CLI のライフサイクル

| artifact | 物理位置 | 生成 CLI (file:line) | 読込 CLI (file:line) | 削除 / 上書き CLI (file:line) | スキーマ定義 (file:line) |
|---|---|---|---|---|---|
| `section_manifest.json` | `.spec-grag/state/section_manifest.json` (`spec_grag/artifacts.py:31-48`; Step 1-A §4 行 251) | `core` (`spec_grag/core.py:764-777`; Step 1-B §1 行 68) | `core` (`spec_grag/core.py:268`, `spec_grag/core.py:1218-1224`; Step 1-B §1 行 53) | `core` 上書き (`spec_grag/artifacts.py:108-130`, `spec_grag/artifacts.py:202-220`) | `spec_grag/core.py:3274-3327`; test helper schema は `spec_grag/artifacts.py:136-157` (Step 1-A §1 行 119) |
| `conflict_review_items.json` | `.spec-grag/context/conflict_review_items.json` (`spec_grag/artifacts.py:31-38`; Step 1-A §4 行 252) | `core` (`spec_grag/core.py:764-777`; Step 1-B §1 行 68) | `core` (`spec_grag/core.py:269`; Step 1-B §1 行 53) / `inject` (`spec_grag/inject.py:123-126`, `spec_grag/inject.py:450-453`; Step 1-B §2 行 115, 137) / `inject-conflicts` (`spec_grag/inject.py:835-836`; Step 1-B §7 行 310-311, 330) / `realign` (inject 経由; Step 1-B §8 行 374) | `core` 上書き (`spec_grag/artifacts.py:108-130`, `spec_grag/artifacts.py:202-220`) | `spec_grag/conflict_review.py:444-485`, `spec_grag/conflict_review.py:59-72` |
| `chapter_anchors.json` | `.spec-grag/context/chapter_anchors.json` (`spec_grag/artifacts.py:31-38`; Step 1-A §4 行 253) | `core` (`spec_grag/core.py:718-735`, `spec_grag/core.py:771-776`; Step 1-B §1 行 67-68) | `inject-chapters` (`spec_grag/inject.py:767`; Step 1-B §5 行 238-240, 257) | `core` 上書き (`spec_grag/artifacts.py:108-130`, `spec_grag/artifacts.py:202-220`) | `spec_grag/chapter_anchors.py:45-53`; empty helper は `spec_grag/artifacts.py:160-170` (Step 1-A §1 行 120) |
| `freshness.json` | `.spec-grag/state/freshness.json` (`spec_grag/artifacts.py:31-48`; Step 1-A §4 行 254) | `core` (`spec_grag/core.py:750-777`; Step 1-B §1 行 68) / `watch` (`spec_grag/watcher.py:262-265`, `spec_grag/watcher.py:398-399`, `spec_grag/watcher.py:1289-1290`; Step 1-B §9 行 395, 400, 404-406) | `inject` (`spec_grag/inject.py:94-100`, `spec_grag/inject.py:599-612`; Step 1-B §2 行 112, 136) / `realign` (inject 経由; Step 1-B §8 行 373) / `watch` (`spec_grag/watcher.py:1293-1298`) | `core` / `watch` 上書き (`spec_grag/artifacts.py:102-130`, `spec_grag/watcher.py:1289-1290`) | `spec_grag/freshness.py:63-272` |
| `retrieval_index_state.json` | `.spec-grag/state/retrieval_index_state.json` (`spec_grag/artifacts.py:31-48`; Step 1-A §4 行 255) | `core` (`spec_grag/core.py:2014-2038`, `spec_grag/core.py:2103-2110`) | `core` (`spec_grag/core.py:1412-1435`) | `core` 上書き (`spec_grag/core.py:2103-2110`, `spec_grag/artifacts.py:102-106`) | `spec_grag/core.py:1351-1370` |
| `related_sections_state.json` | `.spec-grag/state/related_sections_state.json` (`spec_grag/artifacts.py:31-48`; Step 1-A §4 行 256) | `core` (`spec_grag/core.py:2505-2517`, `spec_grag/core.py:2553-2554`, `spec_grag/core.py:2585-2587`) | `core` (`spec_grag/core.py:1452-1477`) | `core` 上書き (`spec_grag/core.py:2553-2554`, `spec_grag/core.py:2585-2587`, `spec_grag/artifacts.py:102-106`) | `spec_grag/core.py:1373-1395` |
| `core_progress.json` | `.spec-grag/state/core_progress.json` (`spec_grag/core_progress.py:20-24`; Step 1-A §4 行 284) | `core` (`spec_grag/core_progress.py:48-87`, `spec_grag/core_progress.py:196-210`) | 読込 CLI なし。読込 API は `read_progress` (`spec_grag/core_progress.py:213-220`); Step 1-B §1-§9 の CLI 表では読込なし | `core` 上書き (`spec_grag/core_progress.py:207-210`) | `spec_grag/core_progress.py:196-206` |
| `core_update.lock.json` | `.spec-grag/state/core_update.lock.json` (`spec_grag/core_lock.py:23`, `spec_grag/core_lock.py:48-49`; Step 1-A §4 行 282) | `core` (`spec_grag/core.py:131-153`, `spec_grag/core_lock.py:63-81`; Step 1-B §1 行 50, 89) / `watch` (`spec_grag/watcher.py:321-328`; Step 1-B §9 行 398, 428) | `core` / `watch` (`spec_grag/core_lock.py:225-243`) | `core` / `watch` release (`spec_grag/core.py:188-189`, `spec_grag/watcher.py:574-575`, `spec_grag/core_lock.py:144-155`) | `spec_grag/core_lock.py:28-45`, `spec_grag/core_lock.py:72-79` |
| `watch_state.json` | `.spec-grag/state/watch_state.json` (`spec_grag/watcher.py:44`, `spec_grag/watcher.py:681-697`; Step 1-A §4 行 331) | `watch` (`spec_grag/watcher.py:253`, `spec_grag/watcher.py:302`, `spec_grag/watcher.py:397`, `spec_grag/watcher.py:523`, `spec_grag/watcher.py:967-968`; Step 1-B §9 行 393, 397, 400, 404-406) | `core` (`spec_grag/core.py:106-130`, `spec_grag/core.py:1103`; Step 1-B §1 行 49) / `watch` (`spec_grag/watcher.py:246`, `spec_grag/watcher.py:586`; Step 1-B §9 行 393, 425-426) | `watch` 上書き (`spec_grag/watcher.py:967-968`, `spec_grag/watcher.py:1012-1024`) | `spec_grag/watcher.py:376-397`, `spec_grag/watcher.py:506-523`, `spec_grag/watcher.py:967-968` |
| `watch_queue.json` | `.spec-grag/state/watch_queue.json` (`spec_grag/watcher.py:45`, `spec_grag/watcher.py:681-697`; Step 1-A §4 行 332) | `watch` (`spec_grag/watcher.py:260-261`, `spec_grag/watcher.py:486`, `spec_grag/watcher.py:503`, `spec_grag/watcher.py:567`, `spec_grag/watcher.py:986-1000`; Step 1-B §9 行 393, 395, 404-406) | `watch` (`spec_grag/watcher.py:254`, `spec_grag/watcher.py:971-983`; Step 1-B §9 行 393, 425-426) | `watch` 上書き (`spec_grag/watcher.py:986-1000`, `spec_grag/watcher.py:1012-1024`) | `spec_grag/watcher.py:971-1000` |
| `_debug_provider_invocations.jsonl` | `.spec-grag/state/_debug_provider_invocations.jsonl` (`spec_grag/llm_provider.py:462-463`; Step 1-A §4 行 302-303) | `core` 条件付き (`SPEC_GRAG_DEBUG_PROVIDER_INVOCATION` truthy かつ related_section_selection: `spec_grag/llm_provider.py:252-265`, `spec_grag/llm_provider.py:478-482`) | 読込 CLI なし (`rg` artifact names command; §0) | append のみ (`spec_grag/llm_provider.py:478-482`) | JSONL record fields は `spec_grag/llm_provider.py:464-477` |
| `_debug_related_prompts.jsonl` | `.spec-grag/state/_debug_related_prompts.jsonl` (`spec_grag/related_sections.py:2820-2842`; Step 1-A §4 行 305-307) | `core` 条件付き (`SPEC_GRAG_DEBUG_RELATED_PROMPT` truthy: `spec_grag/related_sections.py:2825-2842`, `spec_grag/related_sections.py:2861-2916`) | 読込 CLI なし (`rg` artifact names command; §0) | append のみ (`spec_grag/related_sections.py:2912-2916`) | JSONL record fields は `spec_grag/related_sections.py:2873-2911` |
| `related_typing_cache.json` | `.spec-grag/cache/related_typing_cache.json` (`spec_grag/core.py:285`, `spec_grag/related_typing_cache.py:21`; Step 1-A §4 行 278, 311) | `core` (`spec_grag/related_sections.py:596-599`, `spec_grag/related_typing_cache.py:86-99`; Step 1-B §1 行 64-65) | `core` (`spec_grag/related_typing_cache.py:58-77`) | `core --all` 削除 (`spec_grag/core.py:272-289`; Step 1-B §1 行 54) / `core` 上書き (`spec_grag/related_typing_cache.py:86-99`) | `spec_grag/related_typing_cache.py:48-99` |
| Qdrant section collection | Qdrant URL + collection (`spec_grag/core.py:2012-2013`, `spec_grag/inject.py:957-969`; Step 1-B §1 行 60-62, §3 行 154) | `core` (`spec_grag/retrieval_index.py:1018-1028`, `spec_grag/retrieval_index.py:1060-1077`; Step 1-B §1 行 61-62) | `core` (`spec_grag/core.py:1146-1204`) / `inject-search` (`spec_grag/retrieval_index.py:398-435`; Step 1-B §3 行 158-159) / `inject-section` (`spec_grag/section_payload.py:60-90`; Step 1-B §4 行 200-201) | `core` recreate / delete / upsert (`spec_grag/retrieval_index.py:1018-1058`, `spec_grag/retrieval_index.py:1076-1077`) / related_sections payload patch (`spec_grag/retrieval_index.py:786-855`) | collection metadata は `spec_grag/retrieval_index.py:603-643`; payload build は `spec_grag/retrieval_index.py:692-762` (Step 1-A §1 行 135) |

## §3. 失敗時挙動 x CLI

| 失敗対象 | CLI | カテゴリ | 判定箇所 (file:line) | 失敗時の挙動 (file:line) |
|---|---|---|---|---|
| `.spec-grag/config.toml` 読込失敗 | core | failed | `spec_grag/core.py:96-104` (Step 1-B §1 行 48, 86) | config error result を返す (`spec_grag/core.py:98-104`) |
| Purpose / Core Concept missing | core | raise | `spec_grag/core.py:255-258`, `spec_grag/core.py:2220-2223` (Step 1-B §1 行 52, 87) | `FileNotFoundError` を出す (`spec_grag/core.py:2220-2223`) |
| context/state 保持ファイル write 失敗 | core | raise | `spec_grag/core.py:764-777` (Step 1-B §1 行 68, 88) | tmp unlink 後 raise (`spec_grag/artifacts.py:202-220`) |
| core update lock 取得失敗 | core | blocked | `spec_grag/core.py:131-153` (Step 1-B §1 行 50, 89) | blocked result を返す (`spec_grag/core.py:139-152`) |
| LLM provider subprocess failure / timeout / validation failure | core | failed | `spec_grag/llm_provider.py:252-285`, `spec_grag/llm_provider.py:826-949` (Step 1-B §1 行 55-59, 90) | diagnostics 付き failed result を返す (`spec_grag/llm_provider.py:876-949`) |
| Qdrant section collection upsert 失敗 | core | failed | `spec_grag/core.py:1997-2013` (Step 1-B §1 行 60-62, 91) | failed status と diagnostics を返す (`spec_grag/core.py:2143-2162`) |
| FlagEmbedding embed 失敗 | core | failed | `spec_grag/retrieval_index.py:1007-1014` (Step 1-B §1 行 60-62, 92) | core 側で failed status と diagnostics を返す (`spec_grag/core.py:2143-2162`) |
| constraints / freshness override file 読込失敗 | inject | failed | `spec_grag/cli.py:378-387` (Step 1-B §2 行 108-110, 135) | input error または exception result を返す (`spec_grag/cli.py:395-406`) |
| `freshness.json` missing / unreadable | inject | failed | `spec_grag/inject.py:599-612` (Step 1-B §2 行 112, 136) | failed freshness report を返す (`spec_grag/inject.py:607-612`) |
| `conflict_review_items.json` missing / JSON error | inject | fallback | `spec_grag/inject.py:123-126`, `spec_grag/inject.py:637-644` (Step 1-B §2 行 115, 137) | `{}` を返し constraints 検査へ進む (`spec_grag/inject.py:637-644`) |
| agent constraints が無い | inject | raise | `spec_grag/inject.py:112-121` (Step 1-B §2 行 114) | `SpecInjectError` を raise し CLI が JSON result にする (`spec_grag/cli.py:395-406`) |
| `.spec-grag/config.toml` missing / decode error | inject-search | fallback | `spec_grag/inject.py:957-969` (Step 1-B §3 行 154, 178) | `{}` を返し default Qdrant config を使う (`spec_grag/inject.py:626-634`, `spec_grag/inject.py:957-969`) |
| blank query | inject-search | skipped | `spec_grag/inject.py:900-904` (Step 1-B §3 行 155) | warning 付き base result を返す (`spec_grag/inject.py:900-904`) |
| FlagEmbedding / Qdrant import failure | inject-search | degraded / warning | `spec_grag/inject.py:905-914` (Step 1-B §3 行 156) | `retriever_unavailable` warning を返す (`spec_grag/inject.py:910-914`) |
| retriever init failure | inject-search | degraded / warning | `spec_grag/inject.py:916-929` (Step 1-B §3 行 157, 179-180) | `retriever_init_failed` warning を返す (`spec_grag/inject.py:925-929`) |
| retriever search failure | inject-search | degraded / warning | `spec_grag/inject.py:930-936` (Step 1-B §3 行 158, 180) | `retrieval_failed` warning を返す (`spec_grag/inject.py:930-936`) |
| `.spec-grag/config.toml` missing / decode error | inject-section | fallback | `spec_grag/inject.py:711-713`, `spec_grag/inject.py:957-969` (Step 1-B §4 行 198, 220) | `{}` を返し default Qdrant config を使う (`spec_grag/inject.py:626-634`, `spec_grag/inject.py:957-969`) |
| requested ids empty | inject-section | skipped | `spec_grag/inject.py:724-725` (Step 1-B §4 行 199, 214) | base result を返す (`spec_grag/inject.py:714-725`) |
| Qdrant payload lookup failure | inject-section | degraded / warning | `spec_grag/inject.py:727-741` (Step 1-B §4 行 200-201, 221) | warning を result に追加する (`spec_grag/inject.py:728-741`) |
| `chapter_anchors.json` missing | inject-chapters | degraded / warning | `spec_grag/inject.py:767` (Step 1-B §5 行 238-240, 257) | `chapter_anchors_missing` warning を返す (`spec_grag/inject.py:768-776`) |
| `.spec-grag/config.toml` missing / decode error | inject-chapters | fallback | `spec_grag/inject.py:615-644` (Step 1-B §5 行 258) | `{}` を返して context dir default を使う (`spec_grag/inject.py:626-634`) |
| `.spec-grag/config.toml` missing / decode error | inject-purpose | fallback | `spec_grag/inject.py:792-804` (Step 1-B §6 行 274, 293) | `{}` を返して Purpose / Core Concept path を unset 扱いにする (`spec_grag/inject.py:626-634`, `spec_grag/inject.py:1006-1020`) |
| Purpose / Core Concept path unset / missing / read error | inject-purpose | degraded / warning | `spec_grag/inject.py:803-804`, `spec_grag/inject.py:1006-1020` (Step 1-B §6 行 274-275, 294) | warning dict を返す (`spec_grag/inject.py:1006-1020`) |
| `conflict_review_items.json` missing / JSON error | inject-conflicts | fallback | `spec_grag/inject.py:835-836`, `spec_grag/inject.py:637-644` (Step 1-B §7 行 310-311, 330) | `{}` を返し resolved / excluded count を作る (`spec_grag/inject.py:637-644`, `spec_grag/inject.py:861-867`) |
| `.spec-grag/config.toml` missing / decode error | inject-conflicts | fallback | `spec_grag/inject.py:615-644` (Step 1-B §7 行 331) | `{}` を返して context dir default を使う (`spec_grag/inject.py:626-634`) |
| constraints / freshness / answer file 読込失敗 | realign | failed | `spec_grag/cli.py:502-512` (Step 1-B §8 行 345-347, 372) | input error または exception result を返す (`spec_grag/cli.py:521-532`) |
| inject 側 `SpecInjectError` | realign | failed | `spec_grag/realign.py:103-128` (Step 1-B §8 行 349-350) | clarification result または `SpecRealignError` を返す (`spec_grag/realign.py:121-128`) |
| answer が無い | realign | blocked | `spec_grag/realign.py:145-153` (Step 1-B §8 行 352) | `_needs_answer_result` を返す (`spec_grag/realign.py:363-389`) |
| watcher settings config error | watch | raise | `spec_grag/watcher.py:645-652` (Step 1-B §9 行 391, 425) | `WatcherError` を raise する (`spec_grag/watcher.py:651-652`) |
| state / queue JSON read failure | watch | fallback | `spec_grag/watcher.py:246-255`, `spec_grag/watcher.py:1003-1009` (Step 1-B §9 行 393, 425-426) | read failure は `None` になる (`spec_grag/watcher.py:1003-1009`) |
| Source Specs UnicodeDecodeError | watch | fallback | `spec_grag/watcher.py:708-724` (Step 1-B §9 行 394, 427) | replace decode になる (`spec_grag/watcher.py:710-713`) |
| core update lock 取得失敗 | watch | blocked | `spec_grag/watcher.py:321-328` (Step 1-B §9 行 398, 428) | locked result を返す (`spec_grag/watcher.py:329-362`) |
| core internal call が failed result を返す | watch | failed | `spec_grag/watcher.py:454-499` (Step 1-B §9 行 402-404, 429) | failed state / queue / freshness を書き failed result を返す (`spec_grag/watcher.py:465-499`) |
| core internal call 中の exception | watch | raise | `spec_grag/watcher.py:547-573` (Step 1-B §9 行 406, 429) | failed state / queue / freshness を書いて raise する (`spec_grag/watcher.py:547-573`) |

## §4. 判断ロジック / fallback / 閾値の集約

| 判断対象 | 条件 | 通常時挙動 | 例外時 / fallback 時挙動 | 該当 CLI | 所在 (file:line) |
|---|---|---|---|---|---|
| CLI exit code | `status in {"failed","error"}` / `status == "blocked"` | JSON を stdout に出し exit code を返す | failed/error は `1`、blocked は `2`、その他は `0` | core / inject / realign | `spec_grag/cli.py:640-645` (Step 1-B §1 行 73-75, §2 行 120-124, §8 行 357-361) |
| core config load | `.spec-grag/config.toml` 読込 | `_run_spec_core_unlocked` へ進む | config error result を返す | core | `spec_grag/core.py:96-104` (Step 1-B §1 行 48) |
| watcher running guard | watcher state が running | core main body を実行する | blocked result を返す | core | `spec_grag/core.py:106-130` (Step 1-B §1 行 49) |
| core update lock | lock acquire success | `_run_spec_core_unlocked` を呼ぶ | blocked result を返す | core | `spec_grag/core.py:131-187` (Step 1-B §1 行 50-51) |
| `--all` cache clear | `run_full and not use_cache` | cache を保持して stage 実行 | `related_typing_cache.json` と cache subdir JSON を削除 | core | `spec_grag/core.py:272-297` (Step 1-B §1 行 54) |
| LLM provider selection | stage routing / `--llm-provider` / explicit provider | stage ごとの provider を構築 | `SPEC_GRAG_FAKE_LLM` truthy で fake provider を返す | core | `spec_grag/core.py:302-349`, `spec_grag/llm_provider.py:308-328` (Step 1-B §1 行 55-56) |
| LLM retry | `max_retries` | `max_retries + 1` attempts | timeout / provider error / validation error を diagnostics に入れる | core | `spec_grag/llm_provider.py:826-949`; threshold source `spec_grag/config.py:402-403` (Step 1-A §3 行 190-201) |
| Source Retrieval Index upsert | `embedding.provider == "flagembedding"` and `vector_store.provider == "qdrant"` | Qdrant upsert へ進む | 条件不一致なら skipped を返す | core | `spec_grag/core.py:1997-2013` (Step 1-B §1 行 60) |
| retrieval_index_state 一致 | section hash / retrieval config / collection exists が一致 | `skipped_unchanged` を返す | mismatch / collection missing なら upsert へ進む | core | `spec_grag/core.py:2014-2038`, `spec_grag/core.py:1401-1435` (Step 1-B §1 行 60-62) |
| `--verify-index` | flag absent / provider 条件不一致 / rebuild 後 | skip または clean result を返す | mismatch は failed diagnostics を返す | core | `spec_grag/core.py:466-474`, `spec_grag/core.py:1648-1750` (Step 1-B §1 行 63) |
| Related Sections state 一致 | `related_sections_state.json` の fingerprint と config が一致 | skip または partial 判定へ進む | mismatch は full generation へ進む | core | `spec_grag/core.py:2505-2517`, `spec_grag/core.py:1452-1477` (Step 1-B §1 行 64-65) |
| Related Sections partial | section diff sets に changed source がある | partial generation を実行 | full rebuild / retrieval index failed では partial へ進まない | core | `spec_grag/core.py:2535-2578` (Step 1-B §1 行 64-65) |
| Chapter Anchors write | generation status success | `chapter_anchors` を artifacts に入れる | success 以外では canonical write 対象に入れない | core | `spec_grag/core.py:718-735`, `spec_grag/core.py:771-776` (Step 1-B §1 行 67-68) |
| freshness gate | `build_freshness_gate_decision` result | can_continue なら constraints 検査へ進む | stopped / blocked / failed result を返す | inject / realign | `spec_grag/inject.py:101-110`, `spec_grag/freshness.py:359-418` (Step 1-B §2 行 113, §8 行 349-351) |
| constraints required | agent constraints が non-empty | validate constraints へ進む | `SpecInjectError` を raise | inject / realign | `spec_grag/inject.py:112-121` (Step 1-B §2 行 114) |
| constraint evidence validation | required fields / string fields / conflict evidence | validated constraints を返す | invalid field で `SpecInjectError` | inject / realign | `spec_grag/inject.py:154-190` (Step 1-B §2 行 116) |
| inject-search query | non-blank query | retriever import / init / search へ進む | blank query は warning 付き base result | inject-search | `spec_grag/inject.py:900-904` (Step 1-B §3 行 155) |
| inject-search top-k | `--top-k` default `8` | `retriever.search(query, limit=int(top_k))` | search exception は warning result | inject-search | `spec_grag/cli.py:124-127`, `spec_grag/inject.py:930-936` (Step 1-B §3 行 152, 158) |
| Qdrant config priority | `retrieval.section_collection` -> `vector_store.section_collection` -> `vector_store.collection` -> default | selected collection を result に入れる | config missing / decode error は `{}` から default を使う | core / inject-search / inject-section / watch(core経由) | `spec_grag/core.py:1232-1237`, `spec_grag/inject.py:957-969`, `spec_grag/related_sections.py:387-398` (Step 1-B §C 行 492-493) |
| inject-section ids | requested ids non-empty | Qdrant payload lookup | empty ids は base result | inject-section | `spec_grag/inject.py:724-741` (Step 1-B §4 行 199-201) |
| inject-chapters artifact | `chapter_anchors.json` exists | artifact payload を返す | missing warning を返す | inject-chapters | `spec_grag/inject.py:767-776` (Step 1-B §5 行 238-240, 257) |
| Purpose / Core Concept text read | configured path exists and is readable | text を返す | unset / missing / read error warning を返す | inject-purpose | `spec_grag/inject.py:792-818`, `spec_grag/inject.py:1006-1020` (Step 1-B §6 行 274-276, 293-294) |
| conflict item filtering | status resolved and stale marker false | resolved list に入れる | status mismatch / stale marker は excluded list に入れる | inject-conflicts | `spec_grag/inject.py:839-860` (Step 1-B §7 行 312) |
| answer requirement | answer candidate exists | structured answer を返す | answer missing result を返す | realign | `spec_grag/realign.py:145-185`, `spec_grag/realign.py:363-389` (Step 1-B §8 行 352-354) |
| clarification result | task / conversation context / flag | continue result を作る | clarification result または `SpecRealignError` | realign | `spec_grag/realign.py:121-143`, `spec_grag/realign.py:631-690` (Step 1-B §8 行 350-351) |
| watch snapshot diff | current snapshot differs from previous | queue / freshness を書く | diff が無い場合 queue empty 判定へ進む | watch | `spec_grag/watcher.py:257-265` (Step 1-B §9 行 395) |
| watch running state | state running | locked result を返す | running でなければ queue 判定へ進む | watch | `spec_grag/watcher.py:267-281` (Step 1-B §9 行 396) |
| watch queue empty | `not queue["queue"]` | idle state を書いて idle result | queue があれば lock acquire へ進む | watch | `spec_grag/watcher.py:283-314` (Step 1-B §9 行 397) |
| watch lock acquisition | lock acquired | running state を書き core runner を呼ぶ | locked state / freshness を書き locked result | watch | `spec_grag/watcher.py:321-362` (Step 1-B §9 行 398-400) |
| watch core result | core report failed ではない | final state / freshness を書く | failed state / queue / freshness を書き failed result | watch | `spec_grag/watcher.py:465-545` (Step 1-B §9 行 404-405) |
| watch post snapshot diff | post-run source diff exists | queued result | diff が無ければ updated result | watch | `spec_grag/watcher.py:500-545` (Step 1-B §9 行 405) |
| watch polling count | `--once` / `--max-runs` | loop cycle を実行 | max_runs 到達で loop 結果を返す | watch | `spec_grag/cli.py:215-236`, `spec_grag/watcher.py:124-156` (Step 1-B §9 行 389-390, 408) |

## §5. 設定 key 重複の CLI 横断影響

| key | 重複 / 乖離の内容 | 影響を受ける CLI 全件 | 読込所在 (file:line) |
|---|---|---|---|
| `section_collection` | `retrieval.section_collection`、`vector_store.section_collection`、`vector_store.collection` の 3 段参照がある (Step 1-B §C 行 492) | `core` (`spec_grag/core.py:2012-2013`), `inject-search` (`spec_grag/inject.py:890-896`), `inject-section` (`spec_grag/inject.py:711-718`), `watch` (core 経由: `spec_grag/watcher.py:454-464`, `spec_grag/core.py:2012-2013`) | `spec_grag/core.py:1232-1237`, `spec_grag/inject.py:957-969`, `spec_grag/related_sections.py:387-398`; dataclass は `spec_grag/config.py:105-112`, `spec_grag/config.py:124-127` |
| `vector_store.section_collection` / `vector_store.collection` | raw config から読まれるが、`VectorStoreConfig` field は `provider` と `url` である (Step 1-B §C 行 493) | `core` (`spec_grag/core.py:2012-2013`), `inject-search` (`spec_grag/inject.py:890-896`), `inject-section` (`spec_grag/inject.py:711-718`), `watch` (core 経由: `spec_grag/watcher.py:454-464`, `spec_grag/core.py:2012-2013`) | raw read は `spec_grag/core.py:1235-1236`, `spec_grag/inject.py:965-966`, `spec_grag/related_sections.py:392-394`; dataclass は `spec_grag/config.py:124-127` |
| `watcher.state_file` | config loader の `WatcherConfig.state_file` と core / watcher の raw read がある (Step 1-B §C 行 494) | `core` (`spec_grag/core.py:116-130`), `watch` (`spec_grag/watcher.py:246-255`, `spec_grag/watcher.py:586-587`) | dataclass は `spec_grag/config.py:130-136`; config load は `spec_grag/config.py:530-545`; core raw read は `spec_grag/core.py:1103`; watcher raw read は `spec_grag/watcher.py:681-697` |
| `watcher.queue_file` | config loader の `WatcherConfig.queue_file` と watcher の raw read がある (Step 1-B §C 行 495) | `watch` (`spec_grag/watcher.py:254-265`, `spec_grag/watcher.py:500-504`, `spec_grag/watcher.py:1411-1412`) | dataclass は `spec_grag/config.py:130-136`; config load は `spec_grag/config.py:530-545`; watcher raw read は `spec_grag/watcher.py:681-697` |

## §6. dead 経路の二重区分

### §6.1 対象 9 CLI 範囲の dead

| 対象 file:line | 種別 | target 9 CLI 範囲で参照されない理由 | 該当 Step 1-B §B 行 |
|---|---|---|---|
| `spec_grag/inject.py:71-80` `task_prompt` / `prompt` / `conversation_context` / `provider` / `llm_provider` | 引数 5 件 | `spec_grag/inject.py:91` で削除され、target `inject` と `realign` は `spec_grag/cli.py:388-394` と `spec_grag/realign.py:103-120` からこの関数を呼ぶ。 | Step 1-B §B 行 465 |
| `spec_grag/llm_provider.py:331-337` `env` | 引数 1 件 | `spec_grag/llm_provider.py:348` で削除され、core flow は `spec_grag/llm_provider.py:313-318` からこの関数を呼ぶ。 | Step 1-B §B 行 466 |
| `spec_grag/watcher.py:226-228` `wait` / `blocking` | 引数 2 件 | `spec_grag/watcher.py:232` で削除され、target `watch` は `spec_grag/watcher.py:128-136` から `run_watcher_cycle` を呼ぶ。 | Step 1-B §B 行 467 |
| `spec_grag/core.py:21` `build_empty_chapter_anchors` | import 1 件 | production 側参照は import と定義のみである。 | Step 1-B §B 行 468 |
| `spec_grag/cli.py:312` `slash_main` | 関数 1 件 | target 9 CLI の dispatch は `spec_grag/cli.py:290-307` で、`slash_main` は `pyproject.toml:31` の別 entry である。 | Step 1-B §B 行 469 |
| `spec_grag/cli.py:323` `watch_main` | 関数 1 件 | target `watch` は `spec_grag/cli.py:306-307` から `_run_watch_from_args` を呼び、`watch_main` は `pyproject.toml:32` の別 entry である。 | Step 1-B §B 行 470 |
| `spec_grag/cli.py:652` `setup_project_main` | 関数 1 件 | target 9 CLI の dispatch は `spec_grag/cli.py:290-307` で、`setup_project_main` は `pyproject.toml:33` の別 entry である。 | Step 1-B §B 行 471 |
| `spec_grag/cli.py:667` `setup_system_main` | 関数 1 件 | target 9 CLI の dispatch は `spec_grag/cli.py:290-307` で、`setup_system_main` は `pyproject.toml:34` の別 entry である。 | Step 1-B §B 行 472 |
| `spec_grag/watcher.py:159` `run_watcher_once` | 関数 1 件 | target `watch` は `spec_grag/watcher.py:128-136` から `run_watcher_cycle` を呼び、`run_watcher_once` は `spec_grag/watcher.py:188-206` で `run_spec_grag_watch(..., once=True)` を返す。 | Step 1-B §B 行 473 |
| `spec_grag/watcher.py:578` `get_watcher_status` | 関数 1 件 | target `watch` の return path は `spec_grag/watcher.py:148-156` で、`get_watcher_status` は `spec_grag/watcher.py:578-630` に別 dict shape を返す。 | Step 1-B §B 行 474 |

### §6.2 リポジトリ全体の dead

repo 全体で dead と分類する項目は 0 件。

| 対象 file:line | 種別 | repo 全体で参照されない理由 | 探索した grep / AST コマンド |
|---|---|---|---|
| なし | なし | Step 1-B §B 行 465-474 の target 9 CLI 範囲 dead 候補は、tests / pyproject.toml / target 9 CLI 外の spec_grag 経路で参照があった。 | `rg -n 'build_empty_chapter_anchors&#124;slash_main&#124;watch_main&#124;setup_project_main&#124;setup_system_main&#124;run_watcher_once&#124;get_watcher_status' spec_grag tests pyproject.toml`; `rg -n 'task_prompt&#124;conversation_context&#124;agent_constraints&#124;llm_provider&#124;provider=&#124;freshness_report&#124;wait=&#124;blocking=&#124;env=' spec_grag tests pyproject.toml`; `rg -n 'run_spec_inject\\(&#124;run_spec_realign\\(&#124;select_llm_provider_config\\(&#124;run_watcher_cycle\\(' spec_grag tests pyproject.toml` |

## §7. 不明 / 解釈不能事項

本 Step 固有の不明事項は 0 件。

Step 1-B §D 行 511-512 の 2 件は本 Step で解消対象外として扱った:

- `spec_grag/llm_provider.py:488` の `os.environ.copy()` は Step 1-B §D 行 511 で code 上に finite list として出ないと記録済み。
- `spec_grag/project_setup.py:778` の `_env_enabled(name)` は Step 1-B §D 行 512 で allowlist 内 call site が検出されないと記録済み。

| 箇所 file:line | 機械的に判定できなかった事象 | 試した探索コマンド |
|---|---|---|
| なし | Step 1-B §D 行 511-512 以外に、本 Step 固有の未分類項目なし。 | §0 の新規 grep / line read command |

## 最終報告

- 作成したファイル: doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md
- 前提とした Step 1-A 成果物: doc/監査-CODEX/STEP1A_INVENTORY.ja.md
- 前提とした Step 1-B 成果物: doc/監査-CODEX/STEP1B_FLOWS.ja.md
- §1 マトリクスのセル件数: 11 行 x 9 CLI = 99 セル
- §2 artifact 件数: 14 件
- §3 失敗時挙動件数: 34 件
- §4 判断ロジック件数: 32 件
- §5 設定 key 重複件数: 4 件 (Step 1-B §C 全件、新規発見なし)
- §6.1 target 9 CLI 範囲の dead 件数: 10 行 (内訳: 引数 8 件、import 1 件、関数 6 件)
- §6.2 リポジトリ全体の dead 件数: 0 件
- §7 本 Step 固有の不明事項件数: 0 件
- 本 Step で新規 grep した件数: 7 件
- file:line なしで残っている事実文の有無: なし
- denylist を開いていないことの確認方法: 本 Step の新規 grep / line read は §0 に記録した allowlist 内 path のみを対象にした。作業開始前の上位ルール確認として `CLAUDE.md` / `AGENTS.md` / `doc/EXTERNAL_DESIGN.ja.md` / `doc/TODO.ja.md` を読んだが、本 Step 成果物の根拠としては使用していない。
- 中断 / 失敗があれば: なし
