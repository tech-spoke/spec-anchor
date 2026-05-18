# Step 2 方式仕様書

## §0. 監査範囲

- commit hash: `2aa49dd03416f14ae8b2c9791361a58112ff5611`
- 前提成果物: `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`、`doc/監査-CODEX/STEP1B_FLOWS.ja.md`、`doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md` (Step 2 prompt §2 行 24-31)。
- 本書の保持ファイル表では、Step 2 prompt の `artifact` を「保持ファイル」として扱う (Step 2 prompt §7 行 130-146)。
- 対象 CLI は `core` / `inject` / `inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` / `realign` / `watch` の 9 個である (Step 1-B §0 行 9-19; Step 1-C §0 行 8)。
- 上位指示により、作業開始時に `CLAUDE.md` / `AGENTS.md` / `doc/EXTERNAL_DESIGN.ja.md` / `doc/TODO.ja.md` を読んだ。本書の根拠には使わない。Step 2 prompt §13 行 381 の「allowlist 外を開いていない」は厳密には満たしていない。

本 Step で新規 grep / line read した範囲:

```text
$ git rev-parse HEAD
$ ls -l doc/監査-CODEX/STEP2_METHOD.ja.md
$ nl -ba spec_grag/related_sections.py | sed -n '1048,1065p'
$ nl -ba spec_grag/retrieval_index.py | sed -n '661,762p'
$ nl -ba spec_grag/retrieval_index.py | sed -n '373,460p'
$ nl -ba spec_grag/inject.py | sed -n '870,954p'
$ nl -ba spec_grag/inject.py | sed -n '154,190p'
$ nl -ba spec_grag/inject.py | sed -n '430,453p'
$ nl -ba spec_grag/freshness.py | sed -n '359,418p'
$ nl -ba spec_grag/core.py | sed -n '1218,1239p;1351,1435p;1452,1477p;1997,2038p;2505,2517p'
$ nl -ba spec_grag/section_payload.py | sed -n '48,90p'
$ nl -ba spec_grag/cli.py | sed -n '54,204p;283,307p;344,532p;640,645p'
$ rg -n 'property_graph|entity_graph|graph_traversal|Graph|networkx|neo4j|traversal' spec_grag tests pyproject.toml
```

追加確認の理由:

- `spec_grag/retrieval_index.py:661-762` は §7 と §9 で、検索用 text と hit payload に含まれる field を書くために確認した。
- `spec_grag/related_sections.py:1048-1060` は §7 と §9 で、Related Sections の出力 field を書くために確認した。
- `spec_grag/freshness.py:359-418` と `spec_grag/inject.py:154-190` は §2 / §7 / §9 で、CLI が constraints を生成せず、freshness gate と validation を返す経路を書くために確認した。
- `rg -n 'property_graph|entity_graph|graph_traversal|Graph|networkx|neo4j|traversal' spec_grag tests pyproject.toml` は exit code 1 / 0 hit だった。§2 の graph 構造の永続 store / traversal の観測なしの根拠として記録した。

本書で使う内部語:

- `project root`: CLI 引数 `--project-root` / `--root` で渡される対象 project directory (`spec_grag/cli.py:79`, `spec_grag/cli.py:98`, `spec_grag/cli.py:168`; Step 1-B §1 行 43, §2 行 108, §8 行 345)。
- `provider`: code 上の LLM command provider または embedding provider を指す。LLM は `spec_grag/llm_provider.py:288-328`、embedding は `spec_grag/retrieval_index.py:390-393` と `spec_grag/inject.py:916-924` にある。
- `degraded`: CLI が停止せず warning または degraded status を result に含めるカテゴリである (Step 1-C §3 行 80-90)。
- `stale`: 保存済み hash / config / schema が現在値と一致しない状態を指す。state mismatch は `spec_grag/core.py:1415-1435` と `spec_grag/core.py:1452-1477` にある。
- `fallback`: missing / decode error / read failure などで `{}`、`None`、warning result、replace decode へ分岐するカテゴリである (Step 1-C §3 行 74, 80, 84, 88, 91, 97, 98)。
- `runtime state`: 実行制御状態を表す保持ファイルの分類であり、`freshness.json`、lock、watch state / queue、progress を含む (Step 1-C §2 行 52, 55-58)。

## §1. Executive Summary

1. `spec-grag` の top-level parser は 9 subcommand へ分岐する (`spec_grag/cli.py:54-204`, `spec_grag/cli.py:283-307`; Step 1-B §0 行 9-19)。
2. `core` は config、Source Specs、Purpose / Core Concept、LLM provider subprocess、Qdrant、FlagEmbedding、保持ファイル write、lock を呼ぶ (`spec_grag/core.py:96-104`, `spec_grag/core.py:255-258`, `spec_grag/core.py:302-349`, `spec_grag/core.py:1997-2013`; Step 1-C §1 行 33-42)。
3. `watch` は Source Specs snapshot、state / queue JSON、lock を呼び、queue がある場合に `run_spec_core_for_watcher` 経由で `core` を呼ぶ (`spec_grag/watcher.py:244-265`, `spec_grag/watcher.py:454-464`, `spec_grag/core.py:812-822`; Step 1-B §9 行 393-403)。
4. `inject-search` は `.spec-grag/config.toml` から Qdrant 設定を読み、FlagEmbedding BGE-M3 provider と Qdrant retriever を作り、dense search / sparse search / RRF fusion を実行する (`spec_grag/inject.py:889-936`, `spec_grag/retrieval_index.py:398-435`; Step 1-B §3 行 152-160)。
5. `inject-section` は section id を受け取り、Qdrant client と `client.scroll` で payload を返す (`spec_grag/inject.py:727-741`, `spec_grag/section_payload.py:60-90`; Step 1-B §4 行 195-201)。
6. `inject-chapters` は `chapter_anchors.json` を読み、`inject-purpose` は Purpose / Core Concept text を読み、`inject-conflicts` は `conflict_review_items.json` を読む (`spec_grag/inject.py:767`, `spec_grag/inject.py:803-804`, `spec_grag/inject.py:835-836`; Step 1-B §5 行 238-240, §6 行 274-276, §7 行 310-312)。
7. `inject` は Agent-supplied constraints を受け取り、freshness gate と constraints validation を実行して dict を返す (`spec_grag/inject.py:91`, `spec_grag/inject.py:101-121`, `spec_grag/inject.py:154-190`; Step 1-B §2 行 108-118)。
8. `realign` は `run_spec_inject` を呼び、Agent-supplied answer を 4 section dict に構造化して返す (`spec_grag/realign.py:103-120`, `spec_grag/realign.py:155-185`, `spec_grag/realign.py:189-302`; Step 1-B §8 行 345-355)。
9. LLM provider subprocess を直接作る経路は `core` と `watch` の core 経由である (`spec_grag/core.py:302-349`, `spec_grag/llm_provider.py:252-285`, `spec_grag/watcher.py:454-464`; Step 1-C §1 行 33)。
10. Qdrant client を直接呼ぶ CLI は `core`、`inject-search`、`inject-section`、および `watch` の core 経由である (`spec_grag/retrieval_index.py:963-967`, `spec_grag/inject.py:920-936`, `spec_grag/inject.py:727-741`; Step 1-C §1 行 34)。
11. FlagEmbedding BGE-M3 を直接呼ぶ CLI は `core`、`inject-search`、および `watch` の core 経由である (`spec_grag/retrieval_index.py:1007-1014`, `spec_grag/inject.py:916-924`; Step 1-C §1 行 35)。
12. constraints 生成の主体は CLI 側には観測されず、CLI は `agent_constraints` / `agent_answer` を入力として validation と answer structure を返す (`spec_grag/cli.py:388-394`, `spec_grag/cli.py:513-520`, `spec_grag/inject.py:154-190`; Step 1-C §6.1 行 155)。
13. `inject-search` の hit payload は `source_document_id`、`source_section_id`、`source_span`、`heading_path`、`summary`、`search_keys`、`identifiers`、`related_sections`、`score` を含む (`spec_grag/inject.py:937-954`)。
14. `inject-section` は hit payload の `source_section_id` を Qdrant scroll の filter key に使って本文所在 payload を返す (`spec_grag/section_payload.py:62-90`; Step 1-B §4 行 200-201)。
15. graph 構造の永続 store / traversal 用語は `rg -n 'property_graph|entity_graph|graph_traversal|Graph|networkx|neo4j|traversal' spec_grag tests pyproject.toml` で 0 hit だった。
16. Step 1-B §D 行 511-512 には `os.environ.copy()` と `_env_enabled(name)` の解消不能 2 件が残り、Step 1-C §7 行 176-181 は Step 1-C 固有不明 0 件として扱う。

## §2. 方式分類（事実ベース）

| 事実 | 観測根拠 |
|---|---|
| retrieval を呼ぶ CLI は `core`、`inject-search`、`inject-section`、`watch` core 経由である。 | `spec_grag/core.py:1997-2013`, `spec_grag/inject.py:920-936`, `spec_grag/inject.py:727-741`, `spec_grag/watcher.py:454-464`; Step 1-C §1 行 34-35 |
| LLM provider subprocess を呼ぶ CLI は `core` と `watch` core 経由である。 | `spec_grag/core.py:302-349`, `spec_grag/llm_provider.py:252-285`, `spec_grag/watcher.py:454-464`; Step 1-C §1 行 33 |
| 読み取り専用 lookup CLI は `inject-chapters`、`inject-purpose`、`inject-conflicts` である。 | `spec_grag/inject.py:752-818`, `spec_grag/inject.py:821-867`; Step 1-B §5 行 238-258, §6 行 274-294, §7 行 310-331 |
| constraints は CLI が生成せず、Agent-supplied constraints を CLI が検査する。 | `spec_grag/cli.py:388-394`, `spec_grag/inject.py:91`, `spec_grag/inject.py:154-190`; Step 1-B §2 行 108-118, Step 1-C §6.1 行 155 |
| answer は CLI が LLM provider に依頼せず、Agent-supplied answer を `realign_answer` dict に構造化する。 | `spec_grag/cli.py:513-520`, `spec_grag/realign.py:145-185`, `spec_grag/realign.py:189-302`; Step 1-B §8 行 345-355 |
| graph 構造の永続 store / traversal は、allowlist 内 grep で観測されない。 | §0 の graph 用語 grep command は 0 hit |
| Related Sections は target section、confidence、evidence terms、channels、possible conflict を返す配列であり、Qdrant payload に `related_sections` として入る。 | `spec_grag/related_sections.py:1048-1060`, `spec_grag/retrieval_index.py:725-729`; Step 1-C §2 行 61 |

§2 方式分類の事実件数: 7 件。

## §3. 正本データ・派生データ・cache・index の分類

カテゴリ定義は Step 2 prompt §7 行 134-142 に従う。`runtime state` は本節では実行制御状態を指す。

| artifact（保持ファイル名） | カテゴリ | 最終根拠として使えるか | 古くなった場合の検知方法 | 失敗時にどう扱うか |
|---|---|---|---|---|
| `section_manifest.json` | 派生 | No。`core` が freshness / section diff の入力として読む (`spec_grag/core.py:268`, `spec_grag/core.py:1218-1224`; Step 1-C §2 行 49)。 | `core --all` または section hash 差分で再生成される (`spec_grag/core.py:272-297`; Step 1-B §1 行 54)。 | write 失敗は tmp unlink 後 raise (`spec_grag/artifacts.py:202-220`; Step 1-C §3 行 65)。 |
| `conflict_review_items.json` | 派生 | Yes。`validate_constraints` が conflict review item evidence を検査する (`spec_grag/inject.py:154-190`, `spec_grag/inject.py:450-453`; Step 1-C §2 行 50)。 | `core` が current source hashes で staleness refresh を呼ぶ (`spec_grag/core.py:557-620`; Step 1-B §1 行 66)。 | missing / JSON error は `{}` になり constraints 検査へ進む (`spec_grag/inject.py:637-644`; Step 1-C §3 行 74)。 |
| `chapter_anchors.json` | 派生 | No。`inject-chapters` が lookup output として返す (`spec_grag/inject.py:767-776`; Step 1-C §2 行 51)。 | `core` が Chapter Anchors stage で生成し、success 時だけ canonical write 対象に入れる (`spec_grag/core.py:718-735`, `spec_grag/core.py:771-776`; Step 1-C §4 行 119)。 | missing は `chapter_anchors_missing` warning (`spec_grag/inject.py:768-776`; Step 1-C §3 行 87)。 |
| `freshness.json` | runtime state | Yes。`inject` / `realign` の freshness gate が読む (`spec_grag/inject.py:94-110`, `spec_grag/realign.py:103-120`; Step 1-C §2 行 52)。 | `core` / `watch` が freshness report を上書きする (`spec_grag/core.py:750-777`, `spec_grag/watcher.py:262-265`; Step 1-C §2 行 52)。 | missing / unreadable は failed freshness report (`spec_grag/inject.py:607-612`; Step 1-C §3 行 73)。 |
| `retrieval_index_state.json` | cache | No。Source Retrieval Index upsert skip 判定に使う状態記録ファイルである (`spec_grag/core.py:1351-1370`, `spec_grag/core.py:1412-1435`; Step 1-C §2 行 53)。 | 保存された section hash 指紋 / embedding provider / model / dense / sparse / schema が現在値と不一致なら upsert へ進む (`spec_grag/core.py:1358-1369`, `spec_grag/core.py:1415-1435`)。 | Qdrant upsert 失敗は failed status と diagnostics (`spec_grag/core.py:2143-2162`; Step 1-C §3 行 67)。 |
| `related_sections_state.json` | cache | No。Related Sections skip / partial 判定に使う状態記録ファイルである (`spec_grag/core.py:1373-1395`, `spec_grag/core.py:1452-1477`; Step 1-C §2 行 54)。 | 保存された section list/hash 指紋、candidate generation config、selection prompt/model/provider/effort が不一致なら full または partial へ進む (`spec_grag/core.py:1384-1395`, `spec_grag/core.py:1452-1477`)。 | LLM / Qdrant backend failure は stage status に failed / degraded を返す (`spec_grag/core.py:2535-2578`; Step 1-C §3 行 68-69)。 |
| `core_progress.json` | runtime state | No。Step 1-B §1-§9 の CLI 読込表では読込なしである (Step 1-C §2 行 55)。 | `CoreProgressTracker` が stage transition / stats emit 時に上書きする (`spec_grag/core_progress.py:48-87`, `spec_grag/core_progress.py:196-210`; Step 1-C §2 行 55)。 | write 失敗は tracker 内の file write 例外経路に従う (`spec_grag/core_progress.py:207-210`; Step 1-C §2 行 55)。 |
| `core_update.lock.json` | runtime state | No。core / watch の排他制御に使われる (`spec_grag/core_lock.py:63-81`, `spec_grag/watcher.py:321-328`; Step 1-C §2 行 56)。 | stale lock 判定は payload / pid / hostname / age を読む (`spec_grag/core_lock.py:225-243`, `spec_grag/core_lock.py:267-271`; Step 1-C §2 行 56)。 | lock 取得失敗は core / watch で blocked result (`spec_grag/core.py:139-152`, `spec_grag/watcher.py:329-362`; Step 1-C §3 行 66, 99)。 |
| `watch_state.json` | runtime state | No。watch の cycle state と core の watcher running guard が読む (`spec_grag/watcher.py:246-255`, `spec_grag/core.py:106-130`; Step 1-C §2 行 57)。 | watch が running / idle / failed state を上書きする (`spec_grag/watcher.py:376-397`, `spec_grag/watcher.py:506-523`, `spec_grag/watcher.py:967-968`; Step 1-C §2 行 57)。 | read failure は `None` になる (`spec_grag/watcher.py:1003-1009`; Step 1-C §3 行 97)。 |
| `watch_queue.json` | runtime state | No。watch が source diff queue として読む (`spec_grag/watcher.py:254`, `spec_grag/watcher.py:971-983`; Step 1-C §2 行 58)。 | watch が source diff / post-run diff / failed core result で上書きする (`spec_grag/watcher.py:260-261`, `spec_grag/watcher.py:500-504`, `spec_grag/watcher.py:986-1000`; Step 1-C §2 行 58)。 | read failure は `None` になる (`spec_grag/watcher.py:1003-1009`; Step 1-C §3 行 97)。 |
| `_debug_provider_invocations.jsonl` | debug | No。読込 CLI なし (`spec_grag/llm_provider.py:478-482`; Step 1-C §2 行 59)。 | `SPEC_GRAG_DEBUG_PROVIDER_INVOCATION` truthy 時だけ append される (`spec_grag/llm_provider.py:252-265`, `spec_grag/llm_provider.py:478-482`; Step 1-C §2 行 59)。 | debug append 経路で例外を捕捉する (`spec_grag/llm_provider.py:478-483`; Step 1-C §2 行 59)。 |
| `_debug_related_prompts.jsonl` | debug | No。読込 CLI なし (`spec_grag/related_sections.py:2912-2916`; Step 1-C §2 行 60)。 | `SPEC_GRAG_DEBUG_RELATED_PROMPT` truthy 時だけ append される (`spec_grag/related_sections.py:2825-2842`, `spec_grag/related_sections.py:2861-2916`; Step 1-C §2 行 60)。 | debug append 経路で例外を捕捉する (`spec_grag/related_sections.py:2912-2917`; Step 1-C §2 行 60)。 |
| `related_typing_cache.json` | cache | No。Related Sections candidate typing の再利用に使う (`spec_grag/related_typing_cache.py:58-99`; Step 1-C §2 行 61)。 | `core --all` で削除され、通常実行で上書きされる (`spec_grag/core.py:272-289`, `spec_grag/related_typing_cache.py:86-99`; Step 1-C §2 行 61)。 | cache read / write の失敗は cache miss / write failure の経路になる (`spec_grag/related_typing_cache.py:58-99`; Step 1-C §2 行 61)。 |
| Qdrant section collection | index | Yes。`inject-search` と `inject-section` が payload を返す (`spec_grag/retrieval_index.py:398-435`, `spec_grag/section_payload.py:60-90`; Step 1-C §2 行 62)。 | `retrieval_index_state.json` の現在値比較と `_section_collection_exists` で collection missing を検知する (`spec_grag/core.py:1412-1435`; Step 1-C §4 行 115)。 | upsert / lookup / search failure は failed または warning result になる (`spec_grag/core.py:2143-2162`, `spec_grag/inject.py:930-936`, `spec_grag/inject.py:728-741`; Step 1-C §3 行 67, 82, 86)。 |

§3 artifact（保持ファイル）分類の件数: 14 件。

## §4. C4 ビュー（Container / Component）

### §4.1 Container

| Container 名 | 種類 | 入力 | 出力 | 接続先 |
|---|---|---|---|---|
| `spec-grag` CLI process | CLI | argv / argparse subcommand (`spec_grag/cli.py:54-204`, `spec_grag/cli.py:283-307`; Step 1-B §0 行 9-19) | JSON stdout と exit code (`spec_grag/cli.py:369-370`, `spec_grag/cli.py:405-406`, `spec_grag/cli.py:640-645`; Step 1-B §1 行 71-75) | `spec_grag.core`, `spec_grag.inject`, `spec_grag.realign`, `spec_grag.watcher` (`spec_grag/cli.py:344-532`) |
| `.spec-grag` file store | file store | config / state / context / cache JSON (`spec_grag/config.py:163-170`, `spec_grag/artifacts.py:82-100`; Step 1-C §1 行 36-42) | state / context / cache JSON (`spec_grag/artifacts.py:108-130`, `spec_grag/artifacts.py:202-220`; Step 1-C §2 行 49-61) | core / inject / realign / watch (Step 1-C §1 行 36-42) |
| Source Specs file set | file store | Markdown files matched from config (`spec_grag/core.py:2306-2319`, `spec_grag/watcher.py:702-732`; Step 1-C §1 行 37) | parsed sections / watcher snapshot (`spec_grag/core.py:2306-2319`, `spec_grag/watcher.py:708-724`; Step 1-B §1 行 57, §9 行 394) | core / watch |
| LLM provider command | 外部 subprocess | `LlmRequest` and schema (`spec_grag/llm_provider.py:252-285`, `spec_grag/llm_provider.py:826-949`; Step 1-B §1 行 55-59) | generation result / diagnostics (`spec_grag/llm_provider.py:876-949`; Step 1-C §3 行 68) | core / watch core 経由 |
| Qdrant service | 外部 service | dense / sparse vectors and payload lookup (`spec_grag/retrieval_index.py:963-1077`, `spec_grag/section_payload.py:60-90`; Step 1-C §1 行 34) | collection hits / payloads (`spec_grag/retrieval_index.py:398-435`, `spec_grag/inject.py:937-954`; Step 1-B §3 行 158-160) | core / inject-search / inject-section / watch core 経由 |
| FlagEmbedding BGE-M3 provider | 外部 library | query text / section embedding text (`spec_grag/retrieval_index.py:415`, `spec_grag/retrieval_index.py:661-689`, `spec_grag/inject.py:916-924`; Step 1-C §1 行 35) | dense / sparse embedding (`spec_grag/retrieval_index.py:415-421`; Step 1-B §3 行 158-159) | core / inject-search / watch core 経由 |

§4.1 Container 件数: 6 件。

### §4.2 Component（spec_grag 内）

| Component（モジュール名） | 入力 | 何を呼ぶか | 出力 | 関連保持ファイル |
|---|---|---|---|---|
| `spec_grag/cli.py` | argv (`spec_grag/cli.py:54-204`, `spec_grag/cli.py:283-307`; Step 1-A §1 行 121) | target function (`spec_grag/cli.py:344-532`; Step 1-B §0 行 9-19) | stdout JSON / exit code (`spec_grag/cli.py:369-370`, `spec_grag/cli.py:640-645`) | CLI ごとに Step 1-C §1 行 33-43 の接続先 |
| `spec_grag/config.py` | `.spec-grag/config.toml` (`spec_grag/config.py:158`, `spec_grag/config.py:163-170`; Step 1-A §1 行 122) | TOML loader / dataclass builders (`spec_grag/config.py:282-545`; Step 1-A §3 行 133-220) | `ProjectConfig` (`spec_grag/config.py:140`, `spec_grag/config.py:158`) | config file |
| `spec_grag/core.py` | project root / config / Source Specs / Purpose / Core Concept (`spec_grag/core.py:51`, `spec_grag/core.py:96-104`, `spec_grag/core.py:255-258`; Step 1-B §1 行 43-57) | LLM provider, retrieval index, related sections, conflict review, chapter anchors, `ContextArtifactStore` (`spec_grag/core.py:302-349`, `spec_grag/core.py:1997-2013`, `spec_grag/core.py:2505-2517`; Step 1-B §1 行 55-68) | CoreResult dict (`spec_grag/core.py:789-809`; Step 1-B §1 行 71-75) | Step 1-C §2 行 49-62 の 14 件のうち core 生成 / 上書き対象 |
| `spec_grag/inject.py` | constraints / freshness / query / section ids / project root (`spec_grag/inject.py:66`, `spec_grag/inject.py:688`, `spec_grag/inject.py:870`; Step 1-A §1 行 127) | freshness gate, Qdrant retriever, payload lookup, file JSON read (`spec_grag/inject.py:101-110`, `spec_grag/inject.py:920-936`, `spec_grag/inject.py:727-741`; Step 1-B §2-§7) | inject / lookup result dict (`spec_grag/inject.py:127-151`, `spec_grag/inject.py:937-954`; Step 1-B §2 行 117-118, §3 行 160-167) | `freshness.json`, `conflict_review_items.json`, `chapter_anchors.json`, Qdrant section collection |
| `spec_grag/realign.py` | constraints / answer / freshness / task (`spec_grag/realign.py:59`; Step 1-B §8 行 345-347) | `run_spec_inject`, `structure_realign_answer` (`spec_grag/realign.py:103-120`, `spec_grag/realign.py:155-185`; Step 1-B §8 行 349-354) | realign result dict (`spec_grag/realign.py:163-185`; Step 1-B §8 行 357-361) | `freshness.json`, `conflict_review_items.json` inject 経由 |
| `spec_grag/watcher.py` | project root / watch args / config (`spec_grag/watcher.py:85`, `spec_grag/watcher.py:645-650`; Step 1-B §9 行 389-392) | source snapshot, state / queue read-write, core runner, lock (`spec_grag/watcher.py:244-265`, `spec_grag/watcher.py:321-328`, `spec_grag/watcher.py:454-464`; Step 1-B §9 行 393-403) | watch result dict (`spec_grag/watcher.py:148-156`; Step 1-B §9 行 410-414) | `watch_state.json`, `watch_queue.json`, `freshness.json`, `core_update.lock.json` |
| `spec_grag/artifacts.py` | sections / 保持ファイル name / payload (`spec_grag/artifacts.py:63`, `spec_grag/artifacts.py:136`, `spec_grag/artifacts.py:160`; Step 1-A §1 行 119) | JSON read / atomic write (`spec_grag/artifacts.py:82-100`, `spec_grag/artifacts.py:202-220`; Step 1-C §2 行 49-52) | manifest / context payload / write result | `section_manifest.json`, `conflict_review_items.json`, `chapter_anchors.json`, `freshness.json` |
| `spec_grag/freshness.py` | freshness inputs / conflict review items (`spec_grag/freshness.py:63`, `spec_grag/freshness.py:359`; Step 1-A §1 行 126) | freshness normalization and gate decision (`spec_grag/freshness.py:273-418`; Step 1-B §2 行 113) | freshness report / gate decision | `freshness.json`, `conflict_review_items.json` |
| `spec_grag/llm_provider.py` | llm config / request (`spec_grag/llm_provider.py:288`, `spec_grag/llm_provider.py:826-949`; Step 1-A §1 行 128) | subprocess command (`spec_grag/llm_provider.py:252-285`; Step 1-B §1 行 55-59) | generation result / diagnostics | `_debug_provider_invocations.jsonl` conditional |
| `spec_grag/retrieval_index.py` | sections / metadata / query (`spec_grag/retrieval_index.py:373-460`, `spec_grag/retrieval_index.py:661-762`; Step 1-A §5 行 361-438) | FlagEmbedding, Qdrant client, RRF fusion (`spec_grag/retrieval_index.py:385-435`, `spec_grag/retrieval_index.py:963-1077`; Step 1-B §1 行 60-62, §3 行 158-159) | Qdrant payloads / hits | Qdrant section collection |
| `spec_grag/section_payload.py` | section ids / Qdrant client (`spec_grag/section_payload.py:48-90`; Step 1-B §4 行 200-201) | Qdrant scroll (`spec_grag/section_payload.py:72-79`) | section id indexed payload dict | Qdrant section collection |
| `spec_grag/related_sections.py` | sections / metadata / provider (`spec_grag/related_sections.py:693-703`, `spec_grag/related_sections.py:1048-1060`; Step 1-B §1 行 64-65) | LLM retry / optional Qdrant candidates (`spec_grag/related_sections.py:693-703`, `spec_grag/related_sections.py:387-398`) | related section entries | `related_sections_state.json`, `_debug_related_prompts.jsonl`, Qdrant payload patch |
| `spec_grag/related_typing_cache.py` | pair typing payload (`spec_grag/related_typing_cache.py:58-99`; Step 1-C §2 行 61) | cache file read / write | cached pair typing entries | `related_typing_cache.json` |
| `spec_grag/conflict_review.py` | sections / related sections / conflict items (`spec_grag/conflict_review.py:239`, `spec_grag/conflict_review.py:377`; Step 1-A §1 行 123) | conflict selection / evaluation / staleness refresh (`spec_grag/conflict_review.py:239-638`; Step 1-B §1 行 66) | conflict review item list / summary | `conflict_review_items.json` |
| `spec_grag/chapter_anchors.py` | sections / metadata / provider (`spec_grag/chapter_anchors.py:122`; Step 1-A §1 行 120) | LLM retry and cache (`spec_grag/chapter_anchors.py:229-241`; Step 1-B §1 行 67) | chapter anchors generation | `chapter_anchors.json` |
| `spec_grag/core_lock.py` | project root / owner / run id (`spec_grag/core_lock.py:48-52`; Step 1-A §1 行 125) | atomic lock file create/read/release (`spec_grag/core_lock.py:63-81`, `spec_grag/core_lock.py:144-155`; Step 1-C §2 行 56) | lock attempt / diagnostics | `core_update.lock.json` |
| `spec_grag/core_progress.py` | root / stage events (`spec_grag/core_progress.py:23`, `spec_grag/core_progress.py:48`; Step 1-A §1 行 125) | JSON write / read (`spec_grag/core_progress.py:196-220`; Step 1-C §2 行 55) | progress payload / read result | `core_progress.json` |
| `spec_grag/section_parser.py` | Markdown text / path (`spec_grag/section_parser.py:108-110`; Step 1-A §5 行 361-438) | heading parse / hash calculation (`spec_grag/section_parser.py:108-196`; Step 1-A §6 行 438) | parsed section list | `section_manifest.json` core 経由 |
| `spec_grag/section_metadata.py` | sections / provider / cache (`spec_grag/section_metadata.py:364-371`; Step 1-B §1 行 58) | LLM retry / cache read-write (`spec_grag/section_metadata.py:203-234`, `spec_grag/section_metadata.py:364-371`) | metadata result | `section_manifest.json`, Qdrant payload metadata core 経由 |

§4.2 Component 件数: 19 件。

## §5. 主要データフロー

| CLI | エントリー | 主要ステップ | Container 間移動 | 出力 |
|---|---|---|---|---|
| `core` | `spec_grag/cli.py:54-92`, `spec_grag/cli.py:344-370` (Step 1-B §1 行 39-46) | config read -> lock acquire -> Purpose / Core Concept read -> Source Specs parse -> LLM generation -> Qdrant upsert -> related/conflict/chapter generation -> JSON write (`spec_grag/core.py:96-104`, `spec_grag/core.py:131-153`, `spec_grag/core.py:255-258`, `spec_grag/core.py:302-777`; Step 1-B §1 行 47-69) | CLI -> file store -> LLM subprocess -> Qdrant / FlagEmbedding -> file store | CoreResult dict / stdout JSON / exit code (`spec_grag/core.py:789-809`, `spec_grag/cli.py:369-370`; Step 1-B §1 行 71-75) |
| `inject` | `spec_grag/cli.py:94-115`, `spec_grag/cli.py:373-406` (Step 1-B §2 行 104-118) | JSON args read -> freshness read -> freshness gate -> conflict items read -> constraints validation -> result dict (`spec_grag/inject.py:94-151`, `spec_grag/inject.py:154-190`; Step 1-B §2 行 108-118) | CLI -> file store -> CLI result | constraints / injectable_context / warnings dict (`spec_grag/inject.py:127-151`; Step 1-B §2 行 120-124) |
| `inject-search` | `spec_grag/cli.py:117-127`, `spec_grag/cli.py:409-427` (Step 1-B §3 行 148-161) | query join -> config read -> blank query branch -> retriever import -> BGE-M3 provider -> Qdrant dense/sparse search -> hit payload conversion (`spec_grag/inject.py:889-954`; Step 1-B §3 行 152-160) | CLI -> config file -> FlagEmbedding -> Qdrant -> CLI result | hits / warnings dict (`spec_grag/inject.py:891-899`, `spec_grag/inject.py:937-954`; Step 1-B §3 行 163-167) |
| `inject-section` | `spec_grag/cli.py:129-138`, `spec_grag/cli.py:430-446` (Step 1-B §4 行 191-201) | section ids -> config read -> Qdrant client -> `client.scroll` -> missing ids calculation (`spec_grag/inject.py:711-749`, `spec_grag/section_payload.py:60-90`; Step 1-B §4 行 195-201) | CLI -> config file -> Qdrant -> CLI result | sections / missing ids dict (`spec_grag/inject.py:714-749`; Step 1-B §4 行 203-207) |
| `inject-chapters` | `spec_grag/cli.py:140-146`, `spec_grag/cli.py:449-462` (Step 1-B §5 行 228-240) | project root -> context dir -> `chapter_anchors.json` read -> warning branch (`spec_grag/inject.py:766-776`; Step 1-B §5 行 232-240) | CLI -> file store -> CLI result | chapter_anchors / warnings dict (`spec_grag/inject.py:768-776`; Step 1-B §5 行 242-246) |
| `inject-purpose` | `spec_grag/cli.py:148-154`, `spec_grag/cli.py:465-478` (Step 1-B §6 行 266-276) | project root -> raw config read -> Purpose / Core Concept path resolve -> text read / warning branch (`spec_grag/inject.py:792-818`, `spec_grag/inject.py:1006-1020`; Step 1-B §6 行 270-276) | CLI -> config file -> Purpose / Core Concept files -> CLI result | purpose / core_concept text and warnings (`spec_grag/inject.py:810-818`; Step 1-B §6 行 278-282) |
| `inject-conflicts` | `spec_grag/cli.py:156-162`, `spec_grag/cli.py:481-494` (Step 1-B §7 行 302-312) | project root -> `conflict_review_items.json` read -> resolved/excluded split -> count (`spec_grag/inject.py:835-867`; Step 1-B §7 行 306-312) | CLI -> file store -> CLI result | resolved_conflict_items / excluded_conflict_items / count (`spec_grag/inject.py:861-867`; Step 1-B §7 行 314-318) |
| `realign` | `spec_grag/cli.py:164-194`, `spec_grag/cli.py:497-532` (Step 1-B §8 行 341-355) | constraints/freshness/answer args read -> `run_spec_inject` -> stopped / clarification branch -> answer structure (`spec_grag/realign.py:103-185`, `spec_grag/realign.py:189-302`; Step 1-B §8 行 345-355) | CLI -> file store via inject -> CLI result | constraints / answer / realign_answer dict (`spec_grag/realign.py:163-185`; Step 1-B §8 行 357-361) |
| `watch` | `spec_grag/cli.py:196-236`, `spec_grag/cli.py:329-341` (Step 1-B §9 行 385-390) | config read -> state / queue / snapshot read -> diff queue write -> lock acquire -> core internal call -> final state / freshness write (`spec_grag/watcher.py:107-156`, `spec_grag/watcher.py:244-575`; Step 1-B §9 行 391-408) | CLI -> file store -> Source Specs file set -> lock file -> core -> file store | cycles / run_count / settings dict (`spec_grag/watcher.py:148-156`, `spec_grag/cli.py:340-341`; Step 1-B §9 行 410-414) |

§5 主要データフローの CLI 件数: 9 件。

## §6. 更新時の整合性

| case | 振る舞い | freshness / stale 通知の有無 |
|---|---|---|
| Source Specs の本文変更 | `watch` は source file bytes/text/stat/hash から snapshot を作り、diff があると queue と freshness を書く (`spec_grag/watcher.py:702-732`, `spec_grag/watcher.py:257-265`; Step 1-B §9 行 394-395)。 | あり。watch が freshness を書き、inject は freshness gate を読む (`spec_grag/watcher.py:262-265`, `spec_grag/inject.py:101-110`; Step 1-C §4 行 120)。 |
| Section heading 変更 | `core` は Source Specs Markdown を parse し、section manifest と section hash 系の入力を作る (`spec_grag/core.py:2306-2319`, `spec_grag/core.py:1351-1370`; Step 1-B §1 行 57)。heading 専用 branch は Step 1-B §1 / Step 1-C §4 に記録なし。 | section hash / list 指紋の比較に入る (`spec_grag/core.py:1358-1369`, `spec_grag/core.py:1387-1389`; Step 1-C §4 行 115, 117)。 |
| Section 追加 | `core` は section count と section hash fingerprint を `retrieval_index_state.json` に入れ、Related Sections state に section list/hash fingerprint を入れる (`spec_grag/core.py:1358-1369`, `spec_grag/core.py:1384-1395`)。 | state mismatch なら skip せず upsert / related generation へ進む (`spec_grag/core.py:1415-1435`, `spec_grag/core.py:1452-1477`; Step 1-C §4 行 115, 117)。 |
| Section 削除 | `freshness` tests には deleted stored section blocking があるが、本書は code path と Step 1-C に基づき、section hash / list mismatch と watcher diff で扱う (`spec_grag/core.py:1415-1435`, `spec_grag/watcher.py:257-265`; Step 1-A §6 行 438, Step 1-C §4 行 115, 117)。 | あり。freshness gate は status が fresh/degraded 以外なら stop を返す (`spec_grag/freshness.py:377-418`; Step 1-B §2 行 113)。 |
| Section 並べ替え | Related Sections state は `section_list_fingerprint` と `section_hash_fingerprint` を保存する (`spec_grag/core.py:1384-1389`)。 | mismatch の場合 `can_skip` false または partial 判定へ進む (`spec_grag/core.py:1452-1477`; Step 1-C §4 行 117-118)。 |
| Source Specs ファイル名変更 | `watch` は matched source files の bytes/text/stat/sha256 を snapshot に入れる (`spec_grag/watcher.py:702-732`; Step 1-B §9 行 394)。filename 専用 branch は Step 1-B §9 / Step 1-C §4 に記録なし。 | snapshot diff があれば queue / freshness write (`spec_grag/watcher.py:257-265`; Step 1-C §4 行 132)。 |
| Purpose / Core Concept ファイル変更 | `core` は Purpose / Core Concept を読み、hash を作る (`spec_grag/core.py:255-263`; Step 1-B §1 行 52)。`inject-purpose` は text read error を warning にする (`spec_grag/inject.py:1006-1020`; Step 1-C §3 行 90)。 | freshness report / conflict staleness 入力に入る (`spec_grag/core.py:557-620`, `spec_grag/freshness.py:359-418`; Step 1-B §1 行 66, §2 行 113)。 |
| Qdrant collection 削除 | Source Retrieval Index の状態記録ファイルが一致しても `_section_collection_exists` が false なら `can_skip` false になる (`spec_grag/core.py:1412-1435`; Step 1-C §4 行 115)。 | あり。upsert 失敗時は failed status と diagnostics (`spec_grag/core.py:2143-2162`; Step 1-C §3 行 67)。 |
| LLM provider 失敗 | `generate_with_retries` は provider error / timeout / validation error を diagnostics に入れる (`spec_grag/llm_provider.py:826-949`; Step 1-C §3 行 68)。 | あり。core の stage result に failed / diagnostics が入る (`spec_grag/llm_provider.py:876-949`; Step 1-C §3 行 68)。 |
| embedding 失敗 | `core` の retrieval index upsert は provider 条件一致時に Qdrant / FlagEmbedding を呼び、例外時は failed status と diagnostics を返す (`spec_grag/core.py:1997-2013`, `spec_grag/core.py:2143-2162`; Step 1-C §3 行 69)。 | あり。retrieval index failure は core result の failed status / diagnostics になる (`spec_grag/core.py:2143-2162`; Step 1-C §3 行 69)。 |
| watcher 異常停止 | `watch` は core internal call 中の exception で failed state / queue / freshness を書いて raise する (`spec_grag/watcher.py:547-573`; Step 1-C §3 行 101)。 | あり。failed freshness write がある (`spec_grag/watcher.py:547-573`; Step 1-B §9 行 406)。 |
| 設定 (`.spec-grag/config.toml`) 変更 | retrieval state は embedding provider/model/dense/sparse/schema を保存し、Related Sections state は candidate generation config と selection provider/model/effort を保存する (`spec_grag/core.py:1358-1369`, `spec_grag/core.py:1384-1395`; Step 1-C §4 行 115, 117)。 | stale config / schema は freshness gate の blocking reason に入る (`spec_grag/freshness.py:359-418`; Step 1-A §6 行 438)。 |

§6 更新時整合性の case 件数: 12 件。コードから観測される専用 branch なしとして書いた case: 2 件。

## §7. 検索結果から本文へ戻る経路

| step | 観測事実 |
|---|---|
| 1. query 受け取り | `inject-search` の argparse は `query` を `nargs="+"` で受け、wrapper が tokens を join する (`spec_grag/cli.py:121-127`, `spec_grag/cli.py:414-420`; Step 1-B §3 行 152-153)。 |
| 2. query embedding | `run_inject_search` は `FlagEmbeddingBgeM3Provider(allow_real_provider=True, use_fp16=False)` を作る (`spec_grag/inject.py:916-924`; Step 1-B §3 行 156-158)。 |
| 3. dense / sparse / fusion | `QdrantHybridRetriever.search` は `embed_query` 後に dense search、sparse search、`rrf_fusion` を呼ぶ (`spec_grag/retrieval_index.py:415-435`; Step 1-B §3 行 158-159)。 |
| 4. hit payload field | `run_inject_search` は `source_document_id` / `source_section_id` / `source_span` / `heading_path` / `summary` / `search_keys` / `identifiers` / `related_sections` / `score` を返す (`spec_grag/inject.py:937-954`)。 |
| 5. 本文所在 payload lookup | `build_section_payloads` は `source_document_id`、`source_section_id`、`source_span`、`heading_path`、`summary`、`search_keys`、`identifiers`、`related_sections`、`text` を payload に入れ、`inject-section` は `source_section_id` で Qdrant scroll する (`spec_grag/retrieval_index.py:692-732`, `spec_grag/section_payload.py:62-90`; Step 1-B §4 行 200-201)。 |
| 6. Summary / Search Keys / Related Sections の扱い | `validate_constraints` は `SUPPORT_ONLY_ORIGINS` を final evidence_origin にすると `SpecInjectError` を raise し、Related Sections 出力は `target_section_id` / `evidence_terms` / `channels` / `possible_conflict` を持つ補助 field として payload に入る (`spec_grag/inject.py:186-190`, `spec_grag/related_sections.py:1048-1060`, `spec_grag/retrieval_index.py:725-729`)。 |

§7 検索結果から本文へ戻る経路のステップ件数: 6 件。

## §8. 失敗時ポリシー（横断表）

| CLI | 失敗対象 | カテゴリ | 通知方法 | Step 1-C §3 行番号 |
|---|---|---|---|---|
| core | `.spec-grag/config.toml` 読込失敗 | failed | config error result (`spec_grag/core.py:98-104`) | Step 1-C §3 行 65 |
| core | Purpose / Core Concept missing | raise | `FileNotFoundError` (`spec_grag/core.py:2220-2223`) | Step 1-C §3 行 66 |
| core | context/state 保持ファイル write 失敗 | raise | tmp unlink 後 raise (`spec_grag/artifacts.py:202-220`) | Step 1-C §3 行 65 |
| core | core update lock 取得失敗 | blocked | blocked result (`spec_grag/core.py:139-152`) | Step 1-C §3 行 66 |
| core | LLM provider subprocess failure / timeout / validation failure | failed | diagnostics 付き failed result (`spec_grag/llm_provider.py:876-949`) | Step 1-C §3 行 68 |
| core | Qdrant section collection upsert 失敗 | failed | failed status と diagnostics (`spec_grag/core.py:2143-2162`) | Step 1-C §3 行 67 |
| core | FlagEmbedding embed 失敗 | failed | failed status と diagnostics (`spec_grag/core.py:2143-2162`) | Step 1-C §3 行 69 |
| inject | constraints / freshness override file 読込失敗 | failed | input error または exception result (`spec_grag/cli.py:395-406`) | Step 1-C §3 行 72 |
| inject | `freshness.json` missing / unreadable | failed | failed freshness report (`spec_grag/inject.py:607-612`) | Step 1-C §3 行 73 |
| inject | `conflict_review_items.json` missing / JSON error | fallback | `{}` で constraints 検査へ進む (`spec_grag/inject.py:637-644`) | Step 1-C §3 行 74 |
| inject | agent constraints が無い | raise | `SpecInjectError` を CLI が JSON result 化 (`spec_grag/inject.py:112-121`, `spec_grag/cli.py:395-406`) | Step 1-C §3 行 75 |
| inject-search | `.spec-grag/config.toml` missing / decode error | fallback | `{}` から default Qdrant config (`spec_grag/inject.py:626-634`, `spec_grag/inject.py:957-969`) | Step 1-C §3 行 80 |
| inject-search | blank query | skipped | warning 付き base result (`spec_grag/inject.py:900-904`) | Step 1-C §3 行 81 |
| inject-search | FlagEmbedding / Qdrant import failure | degraded / warning | `retriever_unavailable` warning (`spec_grag/inject.py:910-914`) | Step 1-C §3 行 82 |
| inject-search | retriever init failure | degraded / warning | `retriever_init_failed` warning (`spec_grag/inject.py:925-929`) | Step 1-C §3 行 82 |
| inject-search | retriever search failure | degraded / warning | `retrieval_failed` warning (`spec_grag/inject.py:930-936`) | Step 1-C §3 行 83 |
| inject-section | `.spec-grag/config.toml` missing / decode error | fallback | `{}` から default Qdrant config (`spec_grag/inject.py:626-634`, `spec_grag/inject.py:957-969`) | Step 1-C §3 行 84 |
| inject-section | requested ids empty | skipped | base result (`spec_grag/inject.py:714-725`) | Step 1-C §3 行 85 |
| inject-section | Qdrant payload lookup failure | degraded / warning | warning result (`spec_grag/inject.py:728-741`) | Step 1-C §3 行 86 |
| inject-chapters | `chapter_anchors.json` missing | degraded / warning | `chapter_anchors_missing` warning (`spec_grag/inject.py:768-776`) | Step 1-C §3 行 87 |
| inject-chapters | `.spec-grag/config.toml` missing / decode error | fallback | `{}` から context dir default (`spec_grag/inject.py:626-634`) | Step 1-C §3 行 88 |
| inject-purpose | `.spec-grag/config.toml` missing / decode error | fallback | `{}` で Purpose / Core Concept path unset (`spec_grag/inject.py:626-634`, `spec_grag/inject.py:1006-1020`) | Step 1-C §3 行 89 |
| inject-purpose | Purpose / Core Concept path unset / missing / read error | degraded / warning | warning dict (`spec_grag/inject.py:1006-1020`) | Step 1-C §3 行 90 |
| inject-conflicts | `conflict_review_items.json` missing / JSON error | fallback | `{}` で resolved / excluded count (`spec_grag/inject.py:637-644`, `spec_grag/inject.py:861-867`) | Step 1-C §3 行 91 |
| inject-conflicts | `.spec-grag/config.toml` missing / decode error | fallback | `{}` から context dir default (`spec_grag/inject.py:626-634`) | Step 1-C §3 行 92 |
| realign | constraints / freshness / answer file 読込失敗 | failed | input error または exception result (`spec_grag/cli.py:521-532`) | Step 1-C §3 行 93 |
| realign | inject 側 `SpecInjectError` | failed | clarification result または `SpecRealignError` (`spec_grag/realign.py:121-128`) | Step 1-C §3 行 94 |
| realign | answer が無い | blocked | `_needs_answer_result` (`spec_grag/realign.py:363-389`) | Step 1-C §3 行 95 |
| watch | watcher settings config error | raise | `WatcherError` (`spec_grag/watcher.py:651-652`) | Step 1-C §3 行 96 |
| watch | state / queue JSON read failure | fallback | read failure は `None` (`spec_grag/watcher.py:1003-1009`) | Step 1-C §3 行 97 |
| watch | Source Specs UnicodeDecodeError | fallback | replace decode (`spec_grag/watcher.py:710-713`) | Step 1-C §3 行 98 |
| watch | core update lock 取得失敗 | blocked | locked result (`spec_grag/watcher.py:329-362`) | Step 1-C §3 行 99 |
| watch | core internal call が failed result を返す | failed | failed state / queue / freshness write (`spec_grag/watcher.py:465-499`) | Step 1-C §3 行 100 |
| watch | core internal call 中の exception | raise | failed state / queue / freshness write 後 raise (`spec_grag/watcher.py:547-573`) | Step 1-C §3 行 101 |

§8 失敗時ポリシー件数: 34 件。

## §9. ADR 候補（コードから読み取れる方式判断）

| 決定 | 文脈（コード観測事実） | 採用理由 | 代替案 | 結果 | リスク | 証跡 file:line |
|---|---|---|---|---|---|---|
| LLM provider 呼び出しは `core` / `watch` core 経由 | `core` は provider を作り、`watch` は queue がある場合に core runner を呼ぶ。`inject` 系は LLM provider を呼ばない (Step 1-C §1 行 33)。 | コードから不明 | コードから不明 | LLM subprocess 接続は `core` と `watch` core 経由に集まる。 | `run_spec_inject` の `provider` / `llm_provider` は削除される (Step 1-C §6.1 行 155)。 | `spec_grag/core.py:302-349`, `spec_grag/watcher.py:454-464`, `spec_grag/inject.py:91` |
| constraints 生成は CLI 側ではなく Agent 入力 | CLI は `agent_constraints` を受け取り、`validate_constraints` で field と evidence_origin を検査する (Step 1-B §2 行 108-118)。 | コードから不明 | `task_prompt` / `conversation_context` / `provider` / `llm_provider` はシグネチャに残るが削除される (Step 1-C §6.1 行 155)。 | CLI result は constraints / injectable_context / warnings を返す。 | dead 引数 5 件が target 9 CLI 範囲に残る (Step 1-C §6.1 行 155)。 | `spec_grag/cli.py:388-394`, `spec_grag/inject.py:91`, `spec_grag/inject.py:154-190` |
| `inject-search` は Qdrant hybrid retrieval を直接呼ぶ | `run_inject_search` は BGE-M3 provider と `QdrantHybridRetriever` を作り、retriever.search を呼ぶ (Step 1-B §3 行 156-160)。 | コードから不明 | blank query / import failure / init failure / search failure は warning result になる (Step 1-C §3 行 81-83)。 | hit payload は source ids / source span / summary / search keys / identifiers / related sections / score を返す。 | `.spec-grag/config.toml` missing / decode error は `{}` から default Qdrant config を使う (Step 1-C §3 行 80)。 | `spec_grag/inject.py:916-954`, `spec_grag/retrieval_index.py:398-435` |
| Related Sections は retrieval auxiliary field として Qdrant payload に入る | Related Sections entry は `target_section_id` / `evidence_terms` / `channels` / `possible_conflict` を持ち、payload の `related_sections` に入る。 | コードから不明 | コードから不明 | `inject-search` の hits に `related_sections` が含まれる。 | `related_sections_state.json` の mismatch 時は skip せず full / partial 経路へ進む (Step 1-C §4 行 117-118)。 | `spec_grag/related_sections.py:1048-1060`, `spec_grag/retrieval_index.py:725-729`, `spec_grag/inject.py:949` |
| Section embedding text は raw body ではなく heading / summary / search keys / identifiers から作る | `build_section_embedding_text` は heading_path、summary、search_keys、identifiers を join する。raw body field は入力に入らない。 | `spec_grag/retrieval_index.py:668-671` の docstring に短く意味が書かれている。 | コードから不明 | 1 section payload の `text` は `build_section_embedding_text` の出力になる。 | `source_span` と `related_sections` は payload fingerprint から除外される。 | `spec_grag/retrieval_index.py:661-689`, `spec_grag/retrieval_index.py:692-735`, `spec_grag/retrieval_index.py:738-759` |
| Qdrant collection 名は 3 段優先順位で読む | `retrieval.section_collection` -> `vector_store.section_collection` -> `vector_store.collection` -> `"spec_grag_section"` の順で読む (Step 1-C §5 行 144-145)。 | コードから不明 | コードから不明 | `core` / `inject-search` / `inject-section` / `watch` core 経由に影響する (Step 1-C §5 行 144-145)。 | raw config で dataclass field 外の `vector_store.section_collection` / `vector_store.collection` も読む (Step 1-C §5 行 145)。 | `spec_grag/core.py:1232-1239`, `spec_grag/inject.py:957-969`, `spec_grag/related_sections.py:387-398` |
| `core_progress.json` は生成されるが target 9 CLI の読込表に出ない | `CoreProgressTracker` が write し、Step 1-C は読込 CLI なしと記録する。 | コードから不明 | コードから不明 | `core_progress.json` は progress write 対象になる。 | target 9 CLI の user-facing result から read path が観測されない。 | `spec_grag/core_progress.py:48-87`, `spec_grag/core_progress.py:196-220`, Step 1-C §2 行 55 |
| `_debug_*.jsonl` は env var 条件で append される | provider debug と related prompt debug は env var truthy 時に append される (Step 1-C §2 行 59-60)。 | コードから不明 | コードから不明 | 読込 CLI なし、append のみ。 | debug file が root relative default path に書かれる。 | `spec_grag/llm_provider.py:252-265`, `spec_grag/llm_provider.py:478-482`, `spec_grag/related_sections.py:2825-2842`, `spec_grag/related_sections.py:2912-2916` |

§9 ADR 候補の件数: 8 件。

## §10. アーキテクチャリスク一覧

| リスク名 | 何が起きうるか | なぜ起きるか | 再現条件 | ユーザーから見える症状 | 証跡 file:line |
|---|---|---|---|---|---|
| constraints 入力が無い `inject` は停止する | Agent constraints が空の場合に `SpecInjectError` が出る。 | `run_spec_inject` は constraints 候補が無い場合 raise する。 | `spec-grag inject` に constraints JSON/file を渡さない。 | CLI JSON result が input error / `needs_agent_constraints` を返す。 | `spec_grag/inject.py:112-121`, `spec_grag/cli.py:395-406`; Step 1-C §3 行 75 |
| Qdrant config 3 段参照 | `retrieval.section_collection` と raw `vector_store.*collection` で選ばれる collection 名が変わる。 | `_section_collection_name` と `_qdrant_section_config` が複数 key を読む。 | config に複数の collection key を置く。 | result の `collection` field または Qdrant target collection が変わる。 | `spec_grag/core.py:1232-1239`, `spec_grag/inject.py:957-969`; Step 1-C §5 行 144-145 |
| `core_progress.json` の CLI 読込なし | progress file が生成されても target 9 CLI の lookup output に出ない。 | Step 1-C §2 は読込 CLI なしと記録する。 | `core` が progress tracker を使う。 | `core_progress.json` は state dir に残るが target 9 CLI result から読む経路がない。 | `spec_grag/core_progress.py:48-87`, `spec_grag/core_progress.py:196-220`; Step 1-C §2 行 55 |
| debug JSONL append | debug env var が truthy だと `_debug_*.jsonl` が append される。 | debug path は env var または default path で決まる。 | `SPEC_GRAG_DEBUG_PROVIDER_INVOCATION` または `SPEC_GRAG_DEBUG_RELATED_PROMPT` を truthy にする。 | `.spec-grag/state/_debug_provider_invocations.jsonl` または `_debug_related_prompts.jsonl` が増える。 | `spec_grag/llm_provider.py:478-482`, `spec_grag/related_sections.py:2912-2916`; Step 1-C §2 行 59-60 |
| target 9 CLI dead 引数 | `task_prompt` 等の入力が渡っても `run_spec_inject` 内で削除される。 | `del task_prompt, prompt, conversation_context, provider, llm_provider` がある。 | `inject` / `realign` で task prompt や conversation context を渡す。 | CLI result は constraints validation 経路に進み、task prompt 由来の constraints 生成は出ない。 | `spec_grag/inject.py:91`; Step 1-C §6.1 行 155 |
| Qdrant / FlagEmbedding unavailable warning | `inject-search` は retriever import / init / search failure を warnings にして hits 空で返す。 | `run_inject_search` が exception を warning result に変換する。 | qdrant_client / FlagEmbedding import failure、Qdrant connection failure、search exception。 | `warnings` に `retriever_unavailable` / `retriever_init_failed` / `retrieval_failed` が入る。 | `spec_grag/inject.py:905-936`; Step 1-C §3 行 82-83 |
| watcher exception path | core internal call 中の exception で failed state / queue / freshness が書かれ、exception が再送出される。 | `watch` の exception branch が state/queue/freshness write 後に raise する。 | `run_spec_core_for_watcher` 中に exception が出る。 | watch CLI が non-JSON exception path になる場合がある。 | `spec_grag/watcher.py:547-573`; Step 1-C §3 行 101 |
| Source Retrieval Index の状態記録ファイル不一致 | section hash / embedding config / schema が違うと skip されない。 | `_retrieval_index_fast_path_decision` が state keys と collection exists を比較する。 | section change、embedding provider/model change、Qdrant collection deletion。 | `section_collection_upsert` が実行されるか、失敗時に failed diagnostics が返る。 | `spec_grag/core.py:1351-1370`, `spec_grag/core.py:1412-1435`, `spec_grag/core.py:2143-2162`; Step 1-C §4 行 115 |

§10 アーキテクチャリスク件数: 8 件。

## §11. 方式の構造的要約（最終）

1. 9 CLI は `spec_grag/cli.py` の argparse subcommand から各 module function へ分岐する (`spec_grag/cli.py:54-204`, `spec_grag/cli.py:283-307`; Step 1-B §0 行 9-19)。
2. Source Specs / Purpose / Core Concept は `core` が読み、`watch` は Source Specs snapshot を読む (`spec_grag/core.py:255-258`, `spec_grag/core.py:2306-2319`, `spec_grag/watcher.py:702-732`; Step 1-C §1 行 37-38)。
3. `section_manifest.json`、`conflict_review_items.json`、`chapter_anchors.json` は core が生成 / 上書きする派生保持ファイルである (Step 1-C §2 行 49-52)。
4. `retrieval_index_state.json` と `related_sections_state.json` は skip / partial 判定に使う状態記録ファイルである (`spec_grag/core.py:1351-1395`, `spec_grag/core.py:1412-1477`; Step 1-C §2 行 53-54)。
5. Qdrant section collection は `core` が upsert / recreate し、`inject-search` と `inject-section` が読む index である (`spec_grag/retrieval_index.py:1018-1077`, `spec_grag/inject.py:930-954`, `spec_grag/section_payload.py:60-90`; Step 1-C §2 行 62)。
6. constraints 生成は CLI に観測されず、`inject` は Agent-supplied constraints の freshness gate と validation を返す (`spec_grag/inject.py:91`, `spec_grag/inject.py:101-190`; Step 1-B §2 行 108-118)。
7. answer 生成は CLI に観測されず、`realign` は Agent-supplied answer を `realign_answer` に構造化する (`spec_grag/realign.py:145-185`, `spec_grag/realign.py:189-302`; Step 1-B §8 行 352-355)。
8. 検索は BGE-M3 dense / sparse embedding と Qdrant dense / sparse search、RRF fusion で構成される (`spec_grag/retrieval_index.py:415-435`; Step 1-B §3 行 158-159)。
9. hit payload には `source_document_id` / `source_section_id` / `source_span` が入り、`inject-section` が `source_section_id` で Qdrant payload lookup を行う (`spec_grag/inject.py:937-954`, `spec_grag/section_payload.py:62-90`; Step 1-B §4 行 200-201)。
10. 失敗時カテゴリは blocked / failed / degraded-warning / fallback / skipped / raise に分かれ、Step 1-C §3 で 34 件が記録されている (Step 1-C §3 行 65-101)。
11. target 9 CLI 範囲 dead は 10 行、repo 全体 dead は 0 件である (Step 1-C §6.1 行 155-164, §6.2 行 168-172)。
12. Step 1-B §D の `os.environ.copy()` と `_env_enabled(name)` は Step 2 固有 unknown に再掲せず、既知の前段不明として参照する (Step 1-B §D 行 511-512; Step 1-C §7 行 176-181)。

§11 方式構造的要約の行数: 12 行。

## §12. 不明 / 解釈不能事項

| 箇所 file:line | コードから不明な事象 | 試した探索方法 |
|---|---|---|
| なし | Step 2 固有で追加した不明事項は 0 件。Step 1-B §D 行 511-512 の 2 件と Step 1-C §7 行 176-181 の扱いを参照した。 | Step 1-A §7 行 446-455、Step 1-B §D 行 507-512、Step 1-C §7 行 174-185、§0 の新規 line read / grep |

§12 不明事項件数: 0 件。

## 最終報告

- 作成したファイル: doc/監査-CODEX/STEP2_METHOD.ja.md
- 前提とした Step 1-A / 1-B / 1-C 成果物のパス: `doc/監査-CODEX/STEP1A_INVENTORY.ja.md` / `doc/監査-CODEX/STEP1B_FLOWS.ja.md` / `doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md`
- §1 Executive Summary の行数: 16 行
- §2 方式分類の事実件数: 7 件
- §3 artifact（保持ファイル）分類の件数: 14 件
- §4.1 Container / §4.2 Component の件数: 6 件 / 19 件
- §5 主要データフローの CLI 件数: 9 件
- §6 更新時整合性の case 件数と「コードから観測される専用 branch なし」件数: 12 件 / 2 件
- §7 検索結果から本文へ戻る経路のステップ件数: 6 件
- §8 失敗時ポリシーの件数: 34 件
- §9 ADR 候補の件数: 所定の方式判断 8 件 + 追加観測 0 件
- §10 アーキテクチャリスク件数: 8 件
- §11 方式構造的要約の行数: 12 行
- §12 不明事項件数: 0 件
- 本 Step で新規 grep した件数: 1 件。graph 構造の永続 store / traversal 用語の有無を観測するために実行した。
- 本 Step で新規 line read した件数: 10 件。検索 payload、constraints validation、freshness gate、状態記録ファイル比較、CLI wrapper を確認するために実行した。
- file:line または Step 1-A 〜 1-C §節番号引用が付いていない事実文の有無: なし
- denylist を開いていないことの確認方法: 上位指示により作業開始時に `CLAUDE.md` / `AGENTS.md` / `doc/EXTERNAL_DESIGN.ja.md` / `doc/TODO.ja.md` を開いたため、「一切開いていない」とは記録しない。本書の根拠にはそれらの内容を使っていない。
- 中断 / 失敗があれば: Step 2 prompt §13 行 381 の allowlist 外未読条件は厳密には未充足。成果物作成は完了。
