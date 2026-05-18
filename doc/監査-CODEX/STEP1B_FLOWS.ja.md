# Step 1-B 主要 CLI フロー深掘り

## §0. 監査範囲

- commit hash: `2aa49dd03416f14ae8b2c9791361a58112ff5611`
- 前提とした Step 1-A 成果物: `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`
- allowlist 確認: `doc/監査-CODEX/PROMPTS/step1b.md:34-43` の範囲で、`find spec_grag tests -type f -name "*.py" | sort` は 53 件を返した。

| CLI | entry | wrapper | first domain call |
|---|---|---|---|
| `core` | `spec_grag/cli.py:54-92` | `spec_grag/cli.py:344` | `spec_grag/core.py:51` |
| `inject` | `spec_grag/cli.py:94-115` | `spec_grag/cli.py:373` | `spec_grag/inject.py:66` |
| `inject-search` | `spec_grag/cli.py:117-127` | `spec_grag/cli.py:409` | `spec_grag/inject.py:870` |
| `inject-section` | `spec_grag/cli.py:129-138` | `spec_grag/cli.py:430` | `spec_grag/inject.py:688` |
| `inject-chapters` | `spec_grag/cli.py:140-146` | `spec_grag/cli.py:449` | `spec_grag/inject.py:752` |
| `inject-purpose` | `spec_grag/cli.py:148-154` | `spec_grag/cli.py:465` | `spec_grag/inject.py:779` |
| `inject-conflicts` | `spec_grag/cli.py:156-162` | `spec_grag/cli.py:481` | `spec_grag/inject.py:821` |
| `realign` | `spec_grag/cli.py:164-194` | `spec_grag/cli.py:497` | `spec_grag/realign.py:59` |
| `watch` | `spec_grag/cli.py:196-200` | `spec_grag/cli.py:329` | `spec_grag/watcher.py:85` |

| 対象外 CLI | entry | 理由 |
|---|---|---|
| `spec-grag` | `pyproject.toml:30`, `spec_grag/cli.py:283` | `spec_grag/cli.py:290-307` で 9 個の subcommand に分岐する入口である。 |
| `spec-grag-slash` | `pyproject.toml:31`, `spec_grag/cli.py:312` | `spec_grag/cli.py:318-320` で `core` / `inject` / `realign` の引数 parse 後に `0` を返す。 |
| `spec-grag-watch` | `pyproject.toml:32`, `spec_grag/cli.py:323` | `spec_grag/cli.py:325-326` で `_run_watch_from_args` を呼ぶ別入口である。 |
| `spec-grag-setup-project` | `pyproject.toml:33`, `spec_grag/cli.py:652` | `spec_grag/cli.py:656-664` で `setup_project` を呼ぶ初期化入口である。 |
| `spec-grag-setup-system` | `pyproject.toml:34`, `spec_grag/cli.py:667` | `spec_grag/cli.py:671-678` で `setup_system` を呼ぶ初期化入口である。 |

探索コマンド:
```text
$ git rev-parse HEAD
$ find spec_grag tests -type f -name "*.py" | sort
$ grep -nE "^def (_run_|run_spec_|run_inject_|run_spec_realign|run_spec_grag_watch|run_watcher_|load_watcher_settings|collect_source_snapshot|build_spec_core_llm_provider|select_llm_provider_config)" spec_grag/cli.py spec_grag/core.py spec_grag/inject.py spec_grag/realign.py spec_grag/watcher.py spec_grag/llm_provider.py
$ grep -nE "spec-grag|\\[project.scripts\\]" pyproject.toml
```

## §1. core

エントリー: `spec_grag/cli.py:54-92` で parser を作り、`spec_grag/cli.py:290-291` で `_run_core_from_args` を呼び、`spec_grag/cli.py:356-366` で `run_spec_core` を呼ぶ。

### フローチェーン

1. 入力: `--all` / `--rebuild` / `--verify-index` / `--use-cache` / `--project-root` / `--llm-provider` / `--decision-json` / `--decision-file` は `spec_grag/cli.py:58-92` で argparse に登録される。
2. 呼出: `spec_grag/cli.py:347` で project root を解決し、`spec_grag/cli.py:349-353` で decision JSON/file を読み、`spec_grag/cli.py:354-355` で `rebuild_embeddings` と `run_full_flag` を作る。
3. 呼出: `spec_grag/cli.py:356-366` は `run_spec_core(project_root, all=..., use_cache=..., rebuild_embeddings=..., verify_index=..., decision_payload=..., llm_provider_id=...)` を呼ぶ。
4. 分岐: `spec_grag/cli.py:367-370` は例外を `_exception_result` に変換し、`spec_grag/cli.py:369-370` で JSON を出して `_command_exit_code` に渡す。
5. 呼出: `spec_grag/core.py:89-94` は `root`、`generated_at`、`run_full`、`mode_name`、`run_id` を作る。
6. file I/O: `spec_grag/core.py:96-104` は `_load_project_config` を呼び、`spec_grag/core.py:1126-1134` と `spec_grag/config.py:163-170` は `.spec-grag/config.toml` を読む。
7. 分岐: `spec_grag/core.py:106-114` は lock bypass 条件を確認し、`spec_grag/core.py:116-130` は watcher state が実行中なら blocked result を返す。
8. file I/O: `spec_grag/core.py:131-153` は `acquire_core_update_lock` を呼び、`spec_grag/core_lock.py:63-81` は `.spec-grag/state/core_update.lock.json` を排他的作成する。
9. 呼出: `spec_grag/core.py:156-187` は `_run_spec_core_unlocked` に CLI 引数と lock bypass 後の値を渡し、`spec_grag/core.py:188-189` は finally で lock release を呼ぶ。
10. file I/O: `spec_grag/core.py:255-258` は Purpose / Core Concept を `Path.read_text()` で読み、`spec_grag/core.py:260-263` は hash を作る。
11. file I/O: `spec_grag/core.py:265-270` は `ContextArtifactStore` と既存 artifact 読み込みを作り、`spec_grag/artifacts.py:82-100` は artifact path と JSON read を実行する。
12. file I/O: `spec_grag/core.py:272-297` は full mode かつ `use_cache` false のとき cache JSON を削除する。
13. LLM provider: `spec_grag/core.py:302-321` は stage ごとの llm config を作り、`spec_grag/core.py:322-349` は provider 未指定の stage で `build_spec_core_llm_provider` を呼ぶ。
14. LLM provider: `spec_grag/llm_provider.py:308-328` は `SPEC_GRAG_FAKE_LLM` 判定、provider selection、command args 作成、`SubprocessLlmProvider` 作成を行う。
15. file I/O: `spec_grag/core.py:355-359` は snapshot があれば `_load_sections_from_snapshot`、なければ `_load_sections` を呼び、`spec_grag/core.py:2306-2319` は Source Specs markdown を parse する。
16. LLM provider: `spec_grag/core.py:380-388` は `section_metadata_api.generate_section_metadata_result` を呼び、`spec_grag/section_metadata.py:364-371` は `generate_with_retries` を呼ぶ。
17. subprocess: `spec_grag/llm_provider.py:826-949` は `provider.generate` を retry し、`spec_grag/llm_provider.py:252-285` は `subprocess.run(..., env=_subprocess_env(command))` を呼ぶ。
18. Qdrant / FlagEmbedding: `spec_grag/core.py:439-453` は `_upsert_section_collection_if_enabled` を呼び、`spec_grag/core.py:1997-2011` は provider が `flagembedding` / `qdrant` でない場合に skipped を返す。
19. Qdrant / FlagEmbedding: `spec_grag/core.py:2093-2102` は `retrieval_index_api.upsert_qdrant_section_collection` を呼び、`spec_grag/retrieval_index.py:963-967` は `QdrantClient(url)` を作る。
20. Qdrant / FlagEmbedding: `spec_grag/retrieval_index.py:1007-1014` は BGE-M3 embedding を作り、`spec_grag/retrieval_index.py:1018-1028` は collection recreate、`spec_grag/retrieval_index.py:1076-1077` は upsert を呼ぶ。
21. Qdrant verify: `spec_grag/core.py:466-474` は `_verify_section_collection_if_requested` を呼び、`spec_grag/core.py:1648-1750` は `verify_index` と provider 条件で skip / failed / clean を返す。
22. Related Sections: `spec_grag/core.py:482-496` は `_generate_related_sections` を呼び、`spec_grag/core.py:2511-2533` は state fingerprint 一致時に `skipped_unchanged` を返す。
23. Related Sections: `spec_grag/core.py:2535-2578` は partial または full の related generation を呼び、`spec_grag/related_sections.py:693-703` は LLM retry を呼ぶ。
24. Conflict Review: `spec_grag/core.py:557-620` は decision apply、candidate selection、`evaluate_conflicts`、staleness refresh、summary を呼ぶ。
25. Chapter Anchors: `spec_grag/core.py:718-735` は `_chapter_anchors` を呼び、`spec_grag/chapter_anchors.py:229-241` は chapter ごとの LLM retry を呼ぶ。
26. file I/O: `spec_grag/core.py:750-777` は freshness report と artifacts dict を作り、`spec_grag/artifacts.py:108-123` と `spec_grag/artifacts.py:202-220` は JSON を atomic write する。
27. 出力: `spec_grag/core.py:789-809` は CoreResult dict を返し、`spec_grag/cli.py:369-370` は JSON 出力と exit code を返す。

### 最終出力

- 戻り値: `status` / `mode` / `updated_sources` / `retrieval_index_status` / `related_sections_status` / `freshness_report` / `diagnostics` を含む dict は `spec_grag/core.py:789-809` にある。
- stdout: `_run_core_from_args` は `spec_grag/cli.py:369` で `_dumps_json(result)` を print する。
- exit code: `_run_core_from_args` は `spec_grag/cli.py:370` で `_command_exit_code(result)` を返し、`spec_grag/cli.py:640-645` は `status in {"failed","error"}` を `1`、`blocked` を `2`、その他を `0` にする。

### このフローの中で「呼ばれていない引数 / 経路」

- `select_llm_provider_config` の `env` 引数は `spec_grag/llm_provider.py:331-337` にあり、`spec_grag/llm_provider.py:348` で `del env` される。
- `_run_spec_core_unlocked` は `spec_grag/core.py:223` で `**_` を受けるが、`run_spec_core` から渡る CLI 由来の named args は `spec_grag/core.py:156-186` に明示される。

### このフローで観測される外部接続点

| 種別 | 接続先 / ファイル | 呼出条件 | 失敗時挙動 |
|---|---|---|---|
| file I/O | `.spec-grag/config.toml` | `spec_grag/core.py:96-104` で config load を呼ぶ | `spec_grag/core.py:98-104` で config error result を返す |
| file I/O | Purpose / Core Concept | `spec_grag/core.py:255-258` で `_read_required` を呼ぶ | `spec_grag/core.py:2220-2223` で missing は `FileNotFoundError` になる |
| file I/O | context/state artifacts | `spec_grag/core.py:764-777` で artifact dict を write する | `spec_grag/artifacts.py:202-220` で失敗時に tmp unlink 後 raise する |
| file lock | `.spec-grag/state/core_update.lock.json` | `spec_grag/core.py:131-153` で lock を取る | `spec_grag/core.py:139-152` で blocked result を返す |
| LLM provider subprocess | `[llm.providers.<id>].command` | `spec_grag/llm_provider.py:324-328` で subprocess provider を作る | `spec_grag/llm_provider.py:275-282` と `spec_grag/llm_provider.py:876-949` で diagnostics 付き failed result を返す |
| Qdrant | section collection | `spec_grag/core.py:1997-2013` で provider が `flagembedding` / `qdrant` の場合 | `spec_grag/core.py:2143-2162` で failed status と diagnostics を返す |
| FlagEmbedding | `BAAI/bge-m3` | `spec_grag/retrieval_index.py:1007-1014` で embedding inputs がある場合 | `spec_grag/core.py:2143-2162` で failed status と diagnostics を返す |

探索コマンド:
```text
$ nl -ba spec_grag/cli.py | sed -n '46,204p;283,370p'
$ nl -ba spec_grag/core.py | sed -n '51,230p;255,809p;1648,2217p;2220,2319p;2980,3240p'
$ nl -ba spec_grag/llm_provider.py | sed -n '252,370p;826,1060p'
$ nl -ba spec_grag/retrieval_index.py | sed -n '949,1099p'
```

## §2. inject

エントリー: `spec_grag/cli.py:94-115` で parser を作り、`spec_grag/cli.py:292-293` で `_run_inject_from_args` を呼び、`spec_grag/cli.py:388-394` で `run_spec_inject` を呼ぶ。

### フローチェーン

1. 入力: `--project-root` / `--conversation-context` / `--constraints-json` / `--constraints-file` / `--freshness-json` / `--freshness-file` / `task` は `spec_grag/cli.py:98-115` で argparse に登録される。
2. file I/O: `spec_grag/cli.py:378-387` は constraints と freshness を JSON 文字列または file から読み、`spec_grag/cli.py:544-558` は JSON decode を実行する。
3. 呼出: `spec_grag/cli.py:388-394` は project root、task prompt、conversation_context、constraints、freshness を `run_spec_inject` に渡す。
4. 呼出: `spec_grag/inject.py:91` は `task_prompt` / `prompt` / `conversation_context` / `provider` / `llm_provider` を削除する。
5. file I/O: `spec_grag/inject.py:94-100` は freshness 引数が無い場合 `_read_freshness_artifact` を呼び、`spec_grag/inject.py:599-612` は `freshness.json` を読む。
6. 分岐: `spec_grag/inject.py:101-110` は `build_freshness_gate_decision` を呼び、`spec_grag/freshness.py:359-418` は stop / continue の dict を返す。
7. 分岐: `spec_grag/inject.py:112-121` は constraints 候補が無い場合 `SpecInjectError` を raise する。
8. file I/O: `spec_grag/inject.py:123-126` は `_read_conflict_review_items` を呼び、`spec_grag/inject.py:450-453` は `conflict_review_items.json` を読む。
9. 呼出: `spec_grag/inject.py:154-190` は constraints の required fields と string fields を検査する。
10. 出力: `spec_grag/inject.py:127-151` は validated constraints、injectable_context、labels、warnings を含む dict を返す。
11. 出力: `spec_grag/cli.py:395-406` は `SpecInjectError` と generic exception を JSON result にし、`spec_grag/cli.py:405-406` は JSON と exit code を返す。

### 最終出力

- 戻り値: `command` / `project_root` / `status` / `freshness_report` は `spec_grag/inject.py:493-508` にあり、continue 時の `constraints` / `injectable_context` / `labels` は `spec_grag/inject.py:131-144` にある。
- stdout: `_run_inject_from_args` は `spec_grag/cli.py:405` で `_dumps_json(result)` を print する。
- exit code: `_run_inject_from_args` は `spec_grag/cli.py:406` で `_command_exit_code(result)` を返す。

### このフローの中で「呼ばれていない引数 / 経路」

- `run_spec_inject` の `task_prompt` / `prompt` / `conversation_context` / `provider` / `llm_provider` は `spec_grag/inject.py:71-80` にあり、`spec_grag/inject.py:91` で削除される。
- `run_spec_inject` は `spec_grag/inject.py:66-151` の範囲で `run_spec_core` を呼ばない。

### このフローで観測される外部接続点

| 種別 | 接続先 / ファイル | 呼出条件 | 失敗時挙動 |
|---|---|---|---|
| file I/O | constraints / freshness override file | `spec_grag/cli.py:378-387` で file 引数が渡された場合 | `spec_grag/cli.py:395-406` で input error または exception result を返す |
| file I/O | `freshness.json` | `spec_grag/inject.py:94-100` で freshness 引数が無い場合 | `spec_grag/inject.py:607-612` で failed freshness report を返す |
| file I/O | `conflict_review_items.json` | `spec_grag/inject.py:123-126` で constraints 検査前に読む | `spec_grag/inject.py:637-644` で missing / JSON error は `{}` になる |

探索コマンド:
```text
$ nl -ba spec_grag/cli.py | sed -n '94,115p;373,406p;544,558p'
$ nl -ba spec_grag/inject.py | sed -n '66,190p;430,612p'
$ grep -n "def build_freshness_gate_decision" -A60 spec_grag/freshness.py
```

## §3. inject-search

エントリー: `spec_grag/cli.py:117-127` で parser を作り、`spec_grag/cli.py:294-295` で `_run_inject_search_from_args` を呼び、`spec_grag/cli.py:417-421` で `run_inject_search` を呼ぶ。

### フローチェーン

1. 入力: `--project-root` / `--top-k` / `query` は `spec_grag/cli.py:121-127` で argparse に登録される。
2. 呼出: `spec_grag/cli.py:415-421` は query tokens を join し、`run_inject_search(project_root, query, top_k)` を呼ぶ。
3. file I/O: `spec_grag/inject.py:889-890` は project root と `_qdrant_section_config` を作り、`spec_grag/inject.py:957-969` は `.spec-grag/config.toml` の raw dict から url と section_collection を読む。
4. 分岐: `spec_grag/inject.py:900-904` は blank query の場合 warning 付き base result を返す。
5. import: `spec_grag/inject.py:905-914` は `FlagEmbeddingBgeM3Provider` と `QdrantHybridRetriever` import 失敗を `retriever_unavailable` warning にする。
6. FlagEmbedding / Qdrant: `spec_grag/inject.py:916-924` は BGE-M3 provider と hybrid retriever を作る。
7. Qdrant / FlagEmbedding: `spec_grag/inject.py:930-936` は `retriever.search(query, limit=int(top_k))` を呼び、失敗時に `retrieval_failed` warning を返す。
8. Qdrant: `spec_grag/retrieval_index.py:398-435` は embed、dense search、sparse search、RRF fusion を実行する。
9. 出力: `spec_grag/inject.py:937-954` は hits を sections 配列に変換して result を返す。
10. 出力: `spec_grag/cli.py:422-427` は exception を JSON result にし、`spec_grag/cli.py:426-427` は JSON と `0` を返す。

### 最終出力

- 戻り値: `command` / `project_root` / `query` / `top_k` / `collection` / `sections` / `warnings` は `spec_grag/inject.py:891-899` と `spec_grag/inject.py:937-954` にある。
- stdout: `_run_inject_search_from_args` は `spec_grag/cli.py:426` で `_dumps_json(result)` を print する。
- exit code: `_run_inject_search_from_args` は `spec_grag/cli.py:427` で `0` を返す。

### このフローの中で「呼ばれていない引数 / 経路」

- `run_inject_search` は `spec_grag/inject.py:870-954` の範囲で freshness artifact を読まない。
- `_build_hybrid_retriever` の optional `provider` は `spec_grag/inject.py:980-993` にあり、`spec_grag/inject.py:920-924` では `embedding_provider` が渡される。

### このフローで観測される外部接続点

| 種別 | 接続先 / ファイル | 呼出条件 | 失敗時挙動 |
|---|---|---|---|
| file I/O | `.spec-grag/config.toml` | `spec_grag/inject.py:957-969` で `_qdrant_section_config` が呼ばれる | `spec_grag/inject.py:626-634` で missing / decode error は `{}` になる |
| FlagEmbedding | `BAAI/bge-m3` | `spec_grag/inject.py:916-919` で provider を作る | `spec_grag/inject.py:925-929` で `retriever_init_failed` warning を返す |
| Qdrant | section collection | `spec_grag/inject.py:920-924` で retriever を作る | `spec_grag/inject.py:925-936` で init/search failure warning を返す |

探索コマンド:
```text
$ nl -ba spec_grag/cli.py | sed -n '117,127p;409,427p'
$ nl -ba spec_grag/inject.py | sed -n '870,993p'
$ nl -ba spec_grag/retrieval_index.py | sed -n '373,460p'
```

## §4. inject-section

エントリー: `spec_grag/cli.py:129-138` で parser を作り、`spec_grag/cli.py:296-297` で `_run_inject_section_from_args` を呼び、`spec_grag/cli.py:437-440` で `run_inject_section` を呼ぶ。

### フローチェーン

1. 入力: `--project-root` と `section_ids` は `spec_grag/cli.py:133-138` で argparse に登録される。
2. 呼出: `spec_grag/cli.py:437-440` は `run_inject_section(project_root, section_ids)` を呼ぶ。
3. import: `spec_grag/inject.py:706-709` は `fetch_section_payloads` と `SectionPayloadLookupError` を import する。
4. file I/O: `spec_grag/inject.py:711-713` は `_qdrant_section_config` を呼び、`spec_grag/inject.py:957-969` は `.spec-grag/config.toml` の raw dict から url と section_collection を読む。
5. 分岐: `spec_grag/inject.py:724-725` は requested ids が空なら base result を返す。
6. Qdrant: `spec_grag/inject.py:727-730` は `_build_qdrant_client` を呼び、`spec_grag/inject.py:972-977` は `QdrantClient(url)` を作る。
7. Qdrant: `spec_grag/inject.py:732-741` は `fetch_section_payloads` を呼び、`spec_grag/section_payload.py:60-90` は `client.scroll` を batch ごとに呼ぶ。
8. 出力: `spec_grag/inject.py:742-749` は found ids、missing ids、sections dict を result に入れる。
9. 出力: `spec_grag/cli.py:441-446` は exception を JSON result にし、`spec_grag/cli.py:445-446` は JSON と `0` を返す。

### 最終出力

- 戻り値: `command` / `project_root` / `requested_section_ids` / `collection` / `sections` / `missing_section_ids` は `spec_grag/inject.py:714-723` と `spec_grag/inject.py:742-749` にある。
- stdout: `_run_inject_section_from_args` は `spec_grag/cli.py:445` で `_dumps_json(result)` を print する。
- exit code: `_run_inject_section_from_args` は `spec_grag/cli.py:446` で `0` を返す。

### このフローの中で「呼ばれていない引数 / 経路」

- `run_inject_section` は `spec_grag/inject.py:688-749` の範囲で LLM provider を呼ばない。
- `fetch_section_payloads` は `spec_grag/section_payload.py:48-50` で empty ids の場合に Qdrant scroll へ進まない。

### このフローで観測される外部接続点

| 種別 | 接続先 / ファイル | 呼出条件 | 失敗時挙動 |
|---|---|---|---|
| file I/O | `.spec-grag/config.toml` | `spec_grag/inject.py:711-713` で qdrant config を作る | `spec_grag/inject.py:626-634` で missing / decode error は `{}` になる |
| Qdrant | section collection | `spec_grag/inject.py:727-736` で client と scroll を呼ぶ | `spec_grag/inject.py:728-741` で warning を result に追加する |

探索コマンド:
```text
$ nl -ba spec_grag/cli.py | sed -n '129,138p;430,446p'
$ nl -ba spec_grag/inject.py | sed -n '688,749p;957,977p'
$ nl -ba spec_grag/section_payload.py | sed -n '30,90p'
```

## §5. inject-chapters

エントリー: `spec_grag/cli.py:140-146` で parser を作り、`spec_grag/cli.py:298-299` で `_run_inject_chapters_from_args` を呼び、`spec_grag/cli.py:456` で `run_inject_chapters` を呼ぶ。

### フローチェーン

1. 入力: `--project-root` は `spec_grag/cli.py:144-146` で argparse に登録される。
2. 呼出: `spec_grag/cli.py:456` は `run_inject_chapters(project_root=args.project_root)` を呼ぶ。
3. file I/O: `spec_grag/inject.py:766-767` は project root と `_context_dir(project) / "chapter_anchors.json"` を作る。
4. file I/O: `spec_grag/inject.py:637-644` は JSON file missing で `{}`、JSON decode error で `{}` を返す。
5. 出力: `spec_grag/inject.py:768-776` は `chapter_anchors` と missing warning を含む dict を返す。
6. 出力: `spec_grag/cli.py:457-462` は exception を JSON result にし、`spec_grag/cli.py:461-462` は JSON と `0` を返す。

### 最終出力

- 戻り値: `command` / `project_root` / `status` / `chapter_anchors` / `warnings` は `spec_grag/inject.py:768-776` にある。
- stdout: `_run_inject_chapters_from_args` は `spec_grag/cli.py:461` で `_dumps_json(result)` を print する。
- exit code: `_run_inject_chapters_from_args` は `spec_grag/cli.py:462` で `0` を返す。

### このフローの中で「呼ばれていない引数 / 経路」

- `run_inject_chapters` は `spec_grag/inject.py:752-776` の範囲で Qdrant と LLM provider を呼ばない。

### このフローで観測される外部接続点

| 種別 | 接続先 / ファイル | 呼出条件 | 失敗時挙動 |
|---|---|---|---|
| file I/O | `chapter_anchors.json` | `spec_grag/inject.py:767` で context dir 配下を読む | `spec_grag/inject.py:774` で `chapter_anchors_missing` warning を返す |
| file I/O | `.spec-grag/config.toml` | `spec_grag/inject.py:615-623` で context dir を解決する | `spec_grag/inject.py:626-634` で missing / decode error は `{}` になる |

探索コマンド:
```text
$ nl -ba spec_grag/cli.py | sed -n '140,146p;449,462p'
$ nl -ba spec_grag/inject.py | sed -n '752,776p;615,644p'
```

## §6. inject-purpose

エントリー: `spec_grag/cli.py:148-154` で parser を作り、`spec_grag/cli.py:300-301` で `_run_inject_purpose_from_args` を呼び、`spec_grag/cli.py:472` で `run_inject_purpose` を呼ぶ。

### フローチェーン

1. 入力: `--project-root` は `spec_grag/cli.py:152-154` で argparse に登録される。
2. 呼出: `spec_grag/cli.py:472` は `run_inject_purpose(project_root=args.project_root)` を呼ぶ。
3. file I/O: `spec_grag/inject.py:792-804` は raw config から `core.purpose_file` と `core.concept_file` を解決して text を読む。
4. file I/O: `spec_grag/inject.py:1006-1020` は path unset、missing、read error を warning dict にする。
5. 出力: `spec_grag/inject.py:805-818` は purpose/core concept の path と text と warnings を含む dict を返す。
6. 出力: `spec_grag/cli.py:473-478` は exception を JSON result にし、`spec_grag/cli.py:477-478` は JSON と `0` を返す。

### 最終出力

- 戻り値: `command` / `project_root` / `status` / `purpose` / `core_concept` / `warnings` は `spec_grag/inject.py:810-818` にある。
- stdout: `_run_inject_purpose_from_args` は `spec_grag/cli.py:477` で `_dumps_json(result)` を print する。
- exit code: `_run_inject_purpose_from_args` は `spec_grag/cli.py:478` で `0` を返す。

### このフローの中で「呼ばれていない引数 / 経路」

- `run_inject_purpose` は `spec_grag/inject.py:779-818` の範囲で Qdrant と LLM provider を呼ばない。

### このフローで観測される外部接続点

| 種別 | 接続先 / ファイル | 呼出条件 | 失敗時挙動 |
|---|---|---|---|
| file I/O | `.spec-grag/config.toml` | `spec_grag/inject.py:793` で raw config を読む | `spec_grag/inject.py:626-634` で missing / decode error は `{}` になる |
| file I/O | Purpose / Core Concept | `spec_grag/inject.py:803-804` で `_read_text_or_warning` を呼ぶ | `spec_grag/inject.py:1006-1020` で unset / missing / read error warning を返す |

探索コマンド:
```text
$ nl -ba spec_grag/cli.py | sed -n '148,154p;465,478p'
$ nl -ba spec_grag/inject.py | sed -n '779,818p;1006,1020p'
```

## §7. inject-conflicts

エントリー: `spec_grag/cli.py:156-162` で parser を作り、`spec_grag/cli.py:302-303` で `_run_inject_conflicts_from_args` を呼び、`spec_grag/cli.py:488` で `run_inject_conflicts` を呼ぶ。

### フローチェーン

1. 入力: `--project-root` は `spec_grag/cli.py:160-162` で argparse に登録される。
2. 呼出: `spec_grag/cli.py:488` は `run_inject_conflicts(project_root=args.project_root)` を呼ぶ。
3. file I/O: `spec_grag/inject.py:835-836` は project root を解決し、`_read_conflict_review_items` を呼ぶ。
4. file I/O: `spec_grag/inject.py:450-453` は context dir の `conflict_review_items.json` を読む。
5. 分岐: `spec_grag/inject.py:839-860` は each item の `status` と stale flag に応じて `resolved` または `excluded` に分ける。
6. 出力: `spec_grag/inject.py:861-867` は resolved/excluded/count を含む dict を返す。
7. 出力: `spec_grag/cli.py:489-494` は exception を JSON result にし、`spec_grag/cli.py:493-494` は JSON と `0` を返す。

### 最終出力

- 戻り値: `command` / `project_root` / `status` / `resolved_conflict_items` / `excluded_conflict_items` / `count` は `spec_grag/inject.py:861-867` にある。
- stdout: `_run_inject_conflicts_from_args` は `spec_grag/cli.py:493` で `_dumps_json(result)` を print する。
- exit code: `_run_inject_conflicts_from_args` は `spec_grag/cli.py:494` で `0` を返す。

### このフローの中で「呼ばれていない引数 / 経路」

- `run_inject_conflicts` は `spec_grag/inject.py:821-867` の範囲で Qdrant と LLM provider を呼ばない。

### このフローで観測される外部接続点

| 種別 | 接続先 / ファイル | 呼出条件 | 失敗時挙動 |
|---|---|---|---|
| file I/O | `conflict_review_items.json` | `spec_grag/inject.py:835-836` で artifact を読む | `spec_grag/inject.py:637-644` で missing / JSON error は `{}` になる |
| file I/O | `.spec-grag/config.toml` | `spec_grag/inject.py:615-623` で context dir を解決する | `spec_grag/inject.py:626-634` で missing / decode error は `{}` になる |

探索コマンド:
```text
$ nl -ba spec_grag/cli.py | sed -n '156,162p;481,494p'
$ nl -ba spec_grag/inject.py | sed -n '821,867p;450,453p;615,644p'
```

## §8. realign

エントリー: `spec_grag/cli.py:164-194` で parser を作り、`spec_grag/cli.py:304-305` で `_run_realign_from_args` を呼び、`spec_grag/cli.py:513-520` で `run_spec_realign` を呼ぶ。

### フローチェーン

1. 入力: `--project-root` / `--conversation-context` / constraints JSON/file / answer text/json/file / freshness JSON/file / `task` は `spec_grag/cli.py:168-194` で argparse に登録される。
2. file I/O: `spec_grag/cli.py:502-512` は constraints、freshness、answer を JSON/file/text から読む。
3. 呼出: `spec_grag/cli.py:513-520` は project root、task prompt、conversation_context、constraints、answer、freshness を `run_spec_realign` に渡す。
4. 呼出: `spec_grag/realign.py:91-101` は project root、task text、conversation context、clarification flag を作る。
5. 呼出: `spec_grag/realign.py:103-120` は `run_spec_inject` を呼び、`spec_grag/inject.py:91` により provider / llm_provider は inject 側で削除される。
6. 分岐: `spec_grag/realign.py:121-128` は `SpecInjectError` と clarification 条件で clarification result または `SpecRealignError` を返す。
7. 分岐: `spec_grag/realign.py:130-143` は inject result shape、stopped result、clarification result を判定する。
8. 分岐: `spec_grag/realign.py:145-153` は constraints と selected answer を作り、answer が無い場合 `_needs_answer_result` を返す。
9. 呼出: `spec_grag/realign.py:155-161` は `structure_realign_answer` を呼び、`spec_grag/realign.py:189-302` は constraints/targets/review/answer の 4 section dict を返す。
10. 出力: `spec_grag/realign.py:163-185` は constraints、answer、realign_answer、inject_result、labels を含む dict を返す。
11. 出力: `spec_grag/cli.py:521-532` は `SpecRealignError` と generic exception を JSON result にし、`spec_grag/cli.py:531-532` は JSON と exit code を返す。

### 最終出力

- 戻り値: continue result は `spec_grag/realign.py:163-185` にあり、answer missing result は `spec_grag/realign.py:363-389` にある。
- stdout: `_run_realign_from_args` は `spec_grag/cli.py:531` で `_dumps_json(result)` を print する。
- exit code: `_run_realign_from_args` は `spec_grag/cli.py:532` で `_command_exit_code(result)` を返す。

### このフローの中で「呼ばれていない引数 / 経路」

- `run_spec_realign` の `provider` / `llm_provider` は `spec_grag/realign.py:76-77` にあり、`spec_grag/realign.py:116-117` で inject に渡り、`spec_grag/inject.py:91` で削除される。
- `run_spec_realign` は `spec_grag/realign.py:59-185` の範囲で `[llm]` provider を直接呼ばない。

### このフローで観測される外部接続点

| 種別 | 接続先 / ファイル | 呼出条件 | 失敗時挙動 |
|---|---|---|---|
| file I/O | constraints / freshness / answer file | `spec_grag/cli.py:502-512` で file 引数が渡された場合 | `spec_grag/cli.py:521-532` で input error または exception result を返す |
| file I/O | `freshness.json` | `spec_grag/realign.py:103-120` 経由の `run_spec_inject` で freshness 引数が無い場合 | `spec_grag/inject.py:607-612` で failed freshness report を返す |
| file I/O | `conflict_review_items.json` | `spec_grag/realign.py:103-120` 経由の `run_spec_inject` で constraints 検査時に読む | `spec_grag/inject.py:637-644` で missing / JSON error は `{}` になる |

探索コマンド:
```text
$ nl -ba spec_grag/cli.py | sed -n '164,194p;497,532p'
$ nl -ba spec_grag/realign.py | sed -n '59,185p;189,389p'
$ nl -ba spec_grag/inject.py | sed -n '66,151p'
```

## §9. watch

エントリー: `spec_grag/cli.py:196-200` で parser を作り、`spec_grag/cli.py:306-307` で `_run_watch_from_args` を呼び、`spec_grag/cli.py:332-339` で `run_spec_grag_watch` を呼ぶ。

### フローチェーン

1. 入力: `project_root` / `--once` / `--interval-sec` / `--debounce-sec` / `--stale-lock-sec` / `--max-runs` は `spec_grag/cli.py:215-236` で argparse に登録される。
2. 呼出: `spec_grag/cli.py:332-339` は watch arguments を `run_spec_grag_watch` に渡す。
3. file I/O: `spec_grag/watcher.py:107-116` は `load_watcher_settings` を呼び、`spec_grag/watcher.py:645-650` と `spec_grag/config.py:163-170` は `.spec-grag/config.toml` を読む。
4. 呼出: `spec_grag/watcher.py:124-146` は loop を作り、`spec_grag/watcher.py:128-136` で `run_watcher_cycle` を呼ぶ。
5. file I/O: `spec_grag/watcher.py:244-255` は state file、queue file、source snapshot を読む。
6. hash / file I/O: `spec_grag/watcher.py:702-732` は matched source files の bytes、text、stat、sha256 を作る。
7. 分岐: `spec_grag/watcher.py:257-265` は snapshot diff がある場合 queue と freshness artifact を書く。
8. 分岐: `spec_grag/watcher.py:267-281` は state running の場合 locked result を返す。
9. 分岐: `spec_grag/watcher.py:283-314` は queue empty の場合 stale lock cleanup、state write、idle result を返す。
10. file lock: `spec_grag/watcher.py:321-328` は `acquire_core_update_lock` を呼び、`spec_grag/core_lock.py:63-81` は lock file を排他的作成する。
11. 分岐: `spec_grag/watcher.py:329-362` は lock acquisition 失敗時に locked state と freshness を書いて locked result を返す。
12. file I/O: `spec_grag/watcher.py:376-399` は running state と running freshness を書く。
13. file lock: `spec_grag/watcher.py:403-452` は heartbeat callback を作り、`spec_grag/core_lock.py:183-220` は lock heartbeat を更新する。
14. 呼出: `spec_grag/watcher.py:454-464` は `_call_core_runner` を呼び、`spec_grag/watcher.py:739-787` は `run_spec_core_for_watcher` に watcher snapshot と lock bypass args を渡す。
15. 呼出: `spec_grag/core.py:812-822` は watcher 用 kwargs を設定して `run_spec_core` を呼ぶ。
16. 分岐: `spec_grag/watcher.py:465-499` は core result failed の場合 failed state、queue、freshness を書き failed result を返す。
17. 分岐: `spec_grag/watcher.py:500-545` は post snapshot diff を queue に書き、updated または queued result を返す。
18. 分岐: `spec_grag/watcher.py:547-573` は exception 時に failed state、queue、failed freshness を書いて raise する。
19. file lock: `spec_grag/watcher.py:574-575` は finally で `release_core_update_lock` を呼ぶ。
20. 出力: `spec_grag/watcher.py:148-156` は last cycle、cycles、cycle_count、runs、settings を含む dict を返し、`spec_grag/cli.py:340-341` は JSON と `0` を返す。

### 最終出力

- 戻り値: `cycles` / `cycle_count` / `runs` / `run_count` / `settings` は `spec_grag/watcher.py:148-156` にある。
- stdout: `_run_watch_from_args` は `spec_grag/cli.py:340` で `json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)` を print する。
- exit code: `_run_watch_from_args` は `spec_grag/cli.py:341` で `0` を返す。

### このフローの中で「呼ばれていない引数 / 経路」

- `run_watcher_cycle` の `wait` / `blocking` は `spec_grag/watcher.py:226-228` にあり、`spec_grag/watcher.py:232` で削除される。
- `run_watcher_once` は `spec_grag/watcher.py:159` にあるが、target `watch` flow は `spec_grag/watcher.py:128-136` で `run_watcher_cycle` を呼ぶ。

### このフローで観測される外部接続点

| 種別 | 接続先 / ファイル | 呼出条件 | 失敗時挙動 |
|---|---|---|---|
| file I/O | `.spec-grag/config.toml` | `spec_grag/watcher.py:645-650` で settings を読む | `spec_grag/watcher.py:651-652` で `WatcherError` を raise する |
| file I/O | state / queue JSON | `spec_grag/watcher.py:246-255` と `spec_grag/watcher.py:967-1000` で read/write する | `spec_grag/watcher.py:1003-1009` で read failure は `None` になる |
| file I/O | Source Specs bytes | `spec_grag/watcher.py:708-724` で source files を読む | `spec_grag/watcher.py:710-713` で UnicodeDecodeError は replace decode になる |
| file lock | `.spec-grag/state/core_update.lock.json` | `spec_grag/watcher.py:321-328` で lock を取る | `spec_grag/watcher.py:329-362` で locked result を返す |
| core internal call | `run_spec_core_for_watcher` | `spec_grag/watcher.py:454-464` で queue がある場合 | `spec_grag/watcher.py:547-573` で failed state と failed freshness を書いて raise する |

探索コマンド:
```text
$ nl -ba spec_grag/cli.py | sed -n '196,236p;329,341p'
$ nl -ba spec_grag/watcher.py | sed -n '85,575p;633,820p;960,1030p'
$ nl -ba spec_grag/core.py | sed -n '812,822p'
$ nl -ba spec_grag/core_lock.py | sed -n '52,155p;183,243p'
```

## §A. 動的 env var resolution の解消

| Step 1-A §7 該当 file:line | name 変数に入る具体的な値 | 値の根拠 file:line |
|---|---|---|
| `spec_grag/llm_provider.py:488` | 解消不能。`os.environ.copy()` は process env 全体をコピーし、`codex` command の場合だけ `CODEX_HOME` / `CODEX_THREAD_ID` / `CODEX_INTERNAL_ORIGINATOR_OVERRIDE` を削除する。 | `spec_grag/llm_provider.py:487-493` |
| `spec_grag/project_setup.py:805` | `HF_HOME` / `HF_HUB_CACHE` / `TRANSFORMERS_CACHE` | `spec_grag/project_setup.py:803-808` |
| `spec_grag/project_setup.py:778` | 解消不能。`_env_enabled(name)` は `name` 引数を読むが、allowlist 内 grep では call site が検出されない。 | `spec_grag/project_setup.py:777-778`; 探索: `grep -RIn "_env_enabled(" spec_grag` |
| `spec_grag/related_sections.py:2839` | `SPEC_GRAG_DEBUG_RELATED_PROMPT_PATH` | `spec_grag/related_sections.py:2821`, `spec_grag/related_sections.py:2839-2841` |
| `spec_grag/related_sections.py:2836` | `SPEC_GRAG_DEBUG_RELATED_PROMPT` | `spec_grag/related_sections.py:2820`, `spec_grag/related_sections.py:2836-2838` |
| `spec_grag/retrieval_index.py:1708` | `HF_HOME` / `HF_HUB_CACHE` / `TRANSFORMERS_CACHE` | `spec_grag/retrieval_index.py:1706-1711` |

探索コマンド:
```text
$ grep -RIn "os.environ.copy\\|os.environ.get(name)\\|_RELATED_PROMPT_DEBUG\\|_env_enabled(" spec_grag | sort
$ nl -ba spec_grag/llm_provider.py | sed -n '457,493p'
$ nl -ba spec_grag/project_setup.py | sed -n '777,808p'
$ nl -ba spec_grag/related_sections.py | sed -n '2820,2842p'
$ nl -ba spec_grag/retrieval_index.py | sed -n '1706,1711p'
```

## §B. 出現するが呼ばれない経路

本節で観測した dead 引数は 8 件、dead import は 1 件、dead 関数は 6 件である。

| 対象 file:line | 種別 | 観測範囲 | 探索した grep / AST コマンド |
|---|---|---|---|
| `spec_grag/inject.py:71-80` `task_prompt` / `prompt` / `conversation_context` / `provider` / `llm_provider` | 引数 5 件 | `spec_grag/inject.py:91` で削除され、target `inject` と `realign` は `spec_grag/cli.py:388-394` と `spec_grag/realign.py:103-120` からこの関数を呼ぶ。 | `python3 - <<'PY' # AST: Delete nodes in target flow files` |
| `spec_grag/llm_provider.py:331-337` `env` | 引数 1 件 | `spec_grag/llm_provider.py:348` で削除され、core flow は `spec_grag/llm_provider.py:313-318` からこの関数を呼ぶ。 | `python3 - <<'PY' # AST: Delete nodes in target flow files` |
| `spec_grag/watcher.py:226-228` `wait` / `blocking` | 引数 2 件 | `spec_grag/watcher.py:232` で削除され、target `watch` は `spec_grag/watcher.py:128-136` から `run_watcher_cycle` を呼ぶ。 | `python3 - <<'PY' # AST: Delete nodes in target flow files` |
| `spec_grag/core.py:21` `build_empty_chapter_anchors` | import 1 件 | `grep -RIn "build_empty_chapter_anchors" spec_grag tests` では production 側の参照は `spec_grag/core.py:21` と定義 `spec_grag/artifacts.py:160` のみである。 | `python3 - <<'PY' # AST: import name usage in traced files`; `grep -RIn "build_empty_chapter_anchors" spec_grag tests` |
| `spec_grag/cli.py:312` `slash_main` | 関数 1 件 | target 9 CLI の dispatch は `spec_grag/cli.py:290-307` で、`slash_main` は `pyproject.toml:31` の別 entry である。 | `grep -nE "def (slash_main|watch_main|setup_project_main|setup_system_main)" spec_grag/cli.py`; `grep -nE "spec-grag" pyproject.toml` |
| `spec_grag/cli.py:323` `watch_main` | 関数 1 件 | target `watch` は `spec_grag/cli.py:306-307` から `_run_watch_from_args` を呼び、`watch_main` は `pyproject.toml:32` の別 entry である。 | `grep -nE "def (slash_main|watch_main|setup_project_main|setup_system_main)" spec_grag/cli.py`; `grep -nE "spec-grag" pyproject.toml` |
| `spec_grag/cli.py:652` `setup_project_main` | 関数 1 件 | target 9 CLI の dispatch は `spec_grag/cli.py:290-307` で、`setup_project_main` は `pyproject.toml:33` の別 entry である。 | `grep -nE "def (slash_main|watch_main|setup_project_main|setup_system_main)" spec_grag/cli.py`; `grep -nE "spec-grag" pyproject.toml` |
| `spec_grag/cli.py:667` `setup_system_main` | 関数 1 件 | target 9 CLI の dispatch は `spec_grag/cli.py:290-307` で、`setup_system_main` は `pyproject.toml:34` の別 entry である。 | `grep -nE "def (slash_main|watch_main|setup_project_main|setup_system_main)" spec_grag/cli.py`; `grep -nE "spec-grag" pyproject.toml` |
| `spec_grag/watcher.py:159` `run_watcher_once` | 関数 1 件 | target `watch` は `spec_grag/watcher.py:128-136` から `run_watcher_cycle` を呼び、`run_watcher_once` は `spec_grag/watcher.py:188-206` で `run_spec_grag_watch(..., once=True)` を返す。 | `grep -nE "def run_watcher_once|def get_watcher_status|run_watcher_once\\(" spec_grag/watcher.py` |
| `spec_grag/watcher.py:578` `get_watcher_status` | 関数 1 件 | target `watch` の return path は `spec_grag/watcher.py:148-156` で、`get_watcher_status` は `spec_grag/watcher.py:578-630` に別 dict shape を返す。 | `grep -nE "def run_watcher_once|def get_watcher_status|get_watcher_status\\(" spec_grag/watcher.py` |

探索コマンド:
```text
$ python3 - <<'PY'  # AST: Delete nodes in target flow files
$ python3 - <<'PY'  # AST: import name usage in traced files
$ grep -RIn "build_empty_chapter_anchors" spec_grag tests | sort
$ grep -nE "def (slash_main|watch_main|setup_project_main|setup_system_main)" spec_grag/cli.py
$ grep -nE "spec-grag" pyproject.toml
$ grep -nE "def run_watcher_once|def get_watcher_status|run_watcher_once\\(|get_watcher_status\\(" spec_grag/watcher.py
```

## §C. 設定 key の重複 / 乖離

本節で観測した設定 key の重複 / 乖離は 4 件である。

| key | 観測された重複 / 乖離 | 該当 file:line | 影響を受ける CLI |
|---|---|---|---|
| `section_collection` | `retrieval.section_collection`、`vector_store.section_collection`、`vector_store.collection` の 3 段参照がある。 | `spec_grag/core.py:1232-1237`, `spec_grag/inject.py:957-969`, `spec_grag/related_sections.py:387-398`; dataclass は `spec_grag/config.py:105-112` と `spec_grag/config.py:124-127` | `core` (`spec_grag/core.py:2012-2013`), `inject-search` (`spec_grag/inject.py:890-896`), `inject-section` (`spec_grag/inject.py:711-718`) |
| `vector_store.section_collection` / `vector_store.collection` | raw config から読まれるが、`VectorStoreConfig` の field は `provider` と `url` である。 | raw read は `spec_grag/core.py:1235-1236`, `spec_grag/inject.py:965-966`, `spec_grag/related_sections.py:392-394`; dataclass は `spec_grag/config.py:124-127` | `core` (`spec_grag/core.py:2012-2013`), `inject-search` (`spec_grag/inject.py:890-896`), `inject-section` (`spec_grag/inject.py:711-718`) |
| `watcher.state_file` | config loader の `WatcherConfig.state_file` と core / watcher の raw read がある。 | dataclass は `spec_grag/config.py:130-136`; config load は `spec_grag/config.py:530-545`; core raw read は `spec_grag/core.py:1103`; watcher raw read は `spec_grag/watcher.py:681-697` | `core` (`spec_grag/core.py:116-130`), `watch` (`spec_grag/watcher.py:246-255`) |
| `watcher.queue_file` | config loader の `WatcherConfig.queue_file` と watcher の raw read がある。 | dataclass は `spec_grag/config.py:130-136`; config load は `spec_grag/config.py:530-545`; watcher raw read は `spec_grag/watcher.py:681-697` | `watch` (`spec_grag/watcher.py:254-265`, `spec_grag/watcher.py:500-504`) |

探索コマンド:
```text
$ grep -RIn "section_collection\\|vector_store.*collection\\|watcher.*state_file\\|watcher.*queue_file" spec_grag | sort
$ nl -ba spec_grag/config.py | sed -n '103,136p;480,545p'
$ nl -ba spec_grag/core.py | sed -n '1089,1104p;1232,1239p'
$ nl -ba spec_grag/inject.py | sed -n '957,969p'
$ nl -ba spec_grag/related_sections.py | sed -n '387,398p'
$ nl -ba spec_grag/watcher.py | sed -n '681,697p'
```

## §D. 不明 / 解釈不能事項

| 箇所 file:line | フロー追跡で判定できなかった事象 | 追跡で試したこと |
|---|---|---|
| `spec_grag/llm_provider.py:488` | `os.environ.copy()` の key 集合は code 上に finite list として出ない。`codex` command 時に削除される 3 key は `spec_grag/llm_provider.py:489-493` で判定できる。 | `grep -RIn "os.environ.copy\\|_subprocess_env" spec_grag`; `nl -ba spec_grag/llm_provider.py | sed -n '487,493p'` |
| `spec_grag/project_setup.py:778` | `_env_enabled(name)` の `name` 値は allowlist 内 call site が検出されない。 | `grep -RIn "_env_enabled(" spec_grag` |

## 最終報告

- 作成したファイル: doc/監査-CODEX/STEP1B_FLOWS.ja.md
- 前提とした Step 1-A 成果物: doc/監査-CODEX/STEP1A_INVENTORY.ja.md
- 深掘りした CLI 数: 9 個
- 対象外として除外した CLI 数: 5 件、理由の所在は §0
- 解消した動的 env var 件数: 4 / 6
- 観測された dead 引数の件数: 8 件
- 観測された dead import の件数: 1 件
- 観測された dead 関数の件数: 6 件
- 観測された設定 key の重複 / 乖離: 4 件
- §D（不明事項）の状態: 2 件
- file:line なしで残っている事実文の有無: なし
- denylist を開いていないことの確認方法: §0 の探索コマンド、§1〜§D の探索コマンド、allowlist 内 path のみを引数にした `grep` / `nl` / `find` / AST コマンドを記録
- 中断 / 失敗があれば: `grep` pattern に backtick を含めた shell command で shell 展開が発生し、`core` / `inject` / `watch` などの command name が実行対象として解釈された。成果物の根拠には使わず、以後は single quote または pattern 簡略化で再実行した。
