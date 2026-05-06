# SPEC-grag 実装計画

> 位置づけ: 軽量版 SPEC-grag を実装するための作業計画。外部契約の正本は `doc/EXTERNAL_DESIGN.ja.md`、内部設計の正本は `doc/DESIGN.ja.md` とする。本書は進行管理とサブエージェント運用のための文書であり、外部契約を上書きしない。

## 1. 進行原則

本書でいう「実装 slice」は、1 回の並列作業で完了条件と検証方法を持てる小さな実装単位を指す。

含むもの:

- module / command / artifact 単位の実装
- 対応する unit test / smoke test
  - `none` / `fake` smoke
  - `local-service` smoke
  - `real-smoke`
  は別の検証段階として扱う。`fake` smoke が通っても、実 Qdrant / BGE-M3 / real provider の実動作完了とは呼ばない。
- 実装に必要な最小 README / template 更新
- 設計正本に沿う範囲の内部構成判断

含まないもの:

- Purpose / Core Concept の内容変更
- 外部契約の変更
- 仕様 conflict の人間判断
- 大きな provider / dependency 方針変更

実装では、Human 判断が不要な範囲は止まらず進める。Agent は「確認した方が丁寧」という理由だけでは停止しない。

## 2. Human 判断が必要な停止条件

次の場合だけ Human 判断を求めて停止する。

- Purpose または Core Concept の内容変更が必要
- `doc/EXTERNAL_DESIGN.ja.md` の外部契約変更が必要
- Source Specs / Purpose / Core Concept 間の conflict を LLM だけで解けない
- 標準 retrieval stack である Qdrant + BGE-M3 dense/sparse + RRF の方針を変える必要がある
- 秘密情報、認証、課金、外部 service 作成が必要
- 合意済みの設計方針を反転する必要がある
- ユーザー作業物や archive を破壊的に削除する必要がある

次は Human 判断なしで進めてよい。

- `doc/` の現行設計に沿った source / test / fixture / template の新規作成
- package 構成、module 分割、CLI entrypoint、内部 API の最小実装
- format / lint / unit test / smoke test の実行と失敗修正
- 設計と矛盾しない軽微な内部仕様の補完
- 旧実装 archive を参照した実装上の移植。ただし旧設計を正本にはしない

### 2.1 継続判断ルール

Lead Agent は、停止条件に該当しない限り、確認質問をせず次の作業へ進む。

Builder / Test / Review / Docs の結果に失敗、未実装、設計との差分、テスト不足が見つかった場合でも、外部契約変更、人間判断、破壊的操作が不要なら停止しない。Lead Agent は修正 slice を切り、担当 Agent に再投入して継続する。

次の状況は Human 判断なしで継続する。

- test failure の原因が実装 bug、fixture 不足、test expectation の実装契約への追従不足である
- Review Agent が外部設計とのズレを指摘したが、現行 `doc/` の契約を変えずに実装を合わせられる
- Docs Agent が README / setup / command template の不足を指摘したが、実装済み仕様の反映だけで解ける
- provider 未導入などで real-smoke が default profile の実行対象外になったが、`none` / `fake` の必須 test は実行できる。ただし、その場合は「実動作検証」は未完了 TODO として残す。

次の状況だけ停止して Human 判断を求める。

- 修正に `doc/EXTERNAL_DESIGN.ja.md` の契約変更が必要
- Purpose / Core Concept の意味内容を変更する必要がある
- pending Conflict Review Item の判断が必要
- Qdrant 以外の vector store、BGE-M3 以外の標準 embedding、RRF 以外の標準 fusion へ変更する必要がある
- 認証、課金、外部 service 作成、秘密情報入力が必要
- ユーザー作業物や archive の破壊的削除が必要

## 3. サブエージェント運用

親 Agent は Lead Agent として振る舞う。サブエージェントは都度起動し、実装 slice ごとに閉じる。

| 役割 | 担当 | 主な責務 |
|---|---|---|
| Lead Agent | 親 Agent | `doc/` を正本として slice を切る。停止条件を判定する。他 Agent の成果を統合する |
| Builder Agent | worker | source 実装、CLI / config / storage / retrieval API などを作る |
| Test Agent | worker | unit test / smoke test / fixture を作る。失敗を再現し、修正対象を明確にする |
| Review Agent | explorer または worker | 外部設計とのズレを確認する。freshness / Conflict / Related Sections / LLM 呼び出し過多を重点チェックする |
| Docs Agent | worker | README / setup / command template を整える。実装で確定した仕様だけを文書へ反映する |

### 3.1 サブエージェントのモデル・推論強度

ここでいう推論強度は、Codex サブエージェント起動時に指定する `reasoning_effort` を指す。実装とレビューは品質リスクが高いため、原則として `xhigh` を指定する。

| 役割 | model 指定 | reasoning_effort | 方針 |
|---|---|---|---|
| Builder Agent | GPT-5.5 を第一候補。利用不可の場合は利用可能な最上位の coding 向け model | `xhigh` | 実装判断、既存設計との整合、失敗修正を重視する |
| Review Agent | GPT-5.5 を第一候補。利用不可の場合は利用可能な最上位 model | `xhigh` | 外部契約、freshness、Conflict、Related Sections、LLM 呼び出し過多の見落としを避ける |
| Test Agent | Lead Agent が slice の難度に応じて選ぶ | `medium` 以上を既定。複雑な fixture / E2E は `high` | deterministic test と再現性を優先する |
| Docs Agent | Lead Agent が文書量と仕様確定度に応じて選ぶ | `medium` 以上を既定 | 実装で確定した仕様だけを反映する |
| Lead Agent | 親 Agent の現在 model を使う | 親 Agent の現在設定を使う | slice 分割、人間判断要否、統合を担当する |

サブエージェント起動時に model を明示できない環境では、少なくとも Builder Agent と Review Agent に `reasoning_effort = xhigh` を指定する。Test Agent と Docs Agent は、Lead Agent が速度と品質のバランスを見て選ぶ。

サブエージェントに渡す共通指示:

```text
あなたは単独で作業していない。
他 Agent の変更を戻さず、担当範囲だけを編集する。
doc/EXTERNAL_DESIGN.ja.md と doc/DESIGN.ja.md を正本とする。
Human 判断が必要な停止条件に該当しない限り、実装・テスト・修正を進める。
最終報告では変更ファイル、検証結果、残リスクだけを簡潔に示す。
```

## 4. 標準 workflow

- [x] 旧 full GRAG 版の `doc/` を archive へ退避する
- [x] root の旧実装・生成物を archive へ退避する
- [x] 軽量版 `doc/` を正本にする
- [x] Agent 共通ルールを軽量版前提へ更新する
- [x] Lead Agent が次の実装 slice を選ぶ
- [x] Lead Agent が Builder / Test / Review / Docs の担当範囲を分ける
- [x] Builder Agent が担当 slice を実装する
- [x] Test Agent が対応 test / smoke を追加して実行する
- [x] Review Agent が `doc/` 契約とのズレを確認する
- [x] Docs Agent が必要な README / setup / template を更新する
- [x] 失敗や不足がある場合、Lead Agent が停止条件を判定し、Human 判断不要なら修正 slice を切って継続する
- [x] Lead Agent が成果を統合し、全体 test / smoke を実行する
- [x] Lead Agent が次 slice へ進むか、Human 判断が必要な停止条件を報告する

## 5. 実装 slice 一覧

### 5.1 Project Skeleton

- [x] `pyproject.toml` を新設する
- [x] `spec_grag/` package を新設する
- [x] CLI entrypoint を定義する
- [x] 最小 README を新設する
- [x] import smoke test を追加する

完了条件:

- package が install 可能
- `spec-grag --help` 相当が起動する
- test runner が動く

### 5.2 Config

- [x] `.spec-grag/config.toml` schema を実装する
- [x] `[sources]` / `[core]` / `[context]` / `[section]` を読む
- [x] `[llm]` / `[embedding]` / `[vector_store]` / `[limits]` を読む
- [x] config validation error を実装する
- [x] config fixture と unit test を追加する

完了条件:

- 必須項目欠落を error にできる
- 標準 config を parse できる
- path は project root 相対で解決される

### 5.3 Section Parser

- [x] Markdown 見出しから Source Specs を section 化する
- [x] `source_section_id` / `stable_section_uid` / `source_span` を生成する
- [x] `source_hash` / `semantic_hash` を生成する
- [x] `[section].max_heading_level` を反映する
- [x] 日本語 Source Specs fixture で unit test を追加する

完了条件:

- `#####` 以下を親 section に統合できる
- section id policy が `doc/DESIGN.ja.md` と一致する
- semantic change と format-only change を区別できる

### 5.4 Context Artifacts

- [x] `.spec-grag/context/` の artifact writer / reader を実装する
- [x] `section_manifest.json` を保存する
- [x] `section_metadata.json` を保存する
- [x] `chapter_anchors.json` を保存する
- [x] `conflict_review_items.json` を保存する
- [x] atomic write と schema version を実装する

完了条件:

- artifact を壊さず書き換えられる
- stale / missing artifact を診断できる
- test で round-trip を確認する

### 5.5 LLM Provider For `/spec-core`

- [x] `[llm]` 設定を `/spec-core` 用 provider として扱う
- [x] subprocess provider の最小 interface を定義する
- [x] timeout / retry / structured output validation を実装する
- [x] prompt version / model / source hash を generation artifact に残す
- [x] fake provider で unit test を追加する

完了条件:

- 実 LLM なしで tests が通る
- 実 provider は smoke test でだけ使う
- `/spec-inject` / `/spec-realign` の Agent 側 LLM と混同しない

### 5.6 Section Metadata Generation

- [x] Section Summary 生成を実装する
- [x] Section Search Keys 生成を実装する
- [x] identifiers 抽出を実装する
- [x] `[limits]` を反映する
- [x] incremental cache key を実装する

完了条件:

- Summary / Search Keys は根拠扱いされない
- LLM 呼び出し回数が section 数に単純比例しない batch 境界を持つ
- changed section だけを再生成できる

### 5.7 Retrieval Index

標準 retrieval stack は Qdrant + BGE-M3 dense/sparse + RRF とする。Builder Agent / Review Agent は、Chroma / FAISS / Weaviate / pgvector など別 vector store を標準経路として採用しない。別 stack が必要に見える場合は実装を止め、Human 判断を求める。

- [x] Source chunking を実装する
- [x] BGE-M3 dense embedding provider interface を実装する
- [x] BGE-M3 sparse lexical weights の正規化を実装する
- [x] Qdrant dense / sparse named vector schema を実装する
- [x] RRF fusion diagnostics を実装する
- [x] provider なしでも走る fake retrieval test を追加する

完了条件:

- Qdrant / FlagEmbedding version と schema metadata を保存する
- dense / sparse ranking と fused ranking を diagnostics に残す
- retrieval result から source snippet を取得できる

### 5.8 Related Sections

- [x] `related_section_candidates` の high recall 生成を実装する
- [x] same chapter / neighbor / markdown link / shared identifier を実装する
- [x] search key / summary search を実装する
- [x] LLM selection を実装する
- [x] relation_hint / confidence validation を実装する
- [x] incremental re-evaluation を実装する

完了条件:

- LLM は候補外の全文探索をしない
- `related_sections` は参照補助リンクとして保存される
- 上限で落とした候補は diagnostics に残る

### 5.9 Conflict Review Items

- [x] `conflicts_with` pair の判定 stage を実装する
- [x] high-risk pair の上限付き必須投入を実装する
- [x] Conflict Review Item schema を実装する
- [x] decision enum と状態遷移を実装する
- [x] `base_source_hashes` / `valid_scope` / `stale_resolution` を実装する
- [x] pending conflict が inject / realign を止める test を追加する

完了条件:

- pending は Conflict Review Item だけから発生する
- stale resolution は制約根拠にできない
- decision payload は人間が JSON を直接編集しない前提で扱える

### 5.10 Freshness Gate

- [x] freshness report schema を確定する
- [x] `blocking_reasons[]` を実装する
- [x] dirty / stale / pending / degraded の優先順位を実装する
- [x] watcher running / queued changes を dirty 扱いにする
- [x] `/spec-inject` / `/spec-realign` の停止時出力を実装する

完了条件:

- 古い保持物で制約生成へ進まない
- dirty / stale と pending が同時にある場合は先に更新を促す
- 必須 artifact 欠落時は制約生成へ進まない

### 5.11 `/spec-core`

- [x] incremental flow を実装する
- [x] `--all` flow を実装する
- [x] CoreResult を実装する
- [x] watcher から呼ぶ internal core update を分離する
- [x] smoke test を追加する

完了条件:

- Source Retrieval Index 更新後に related candidates を生成する
- Purpose / Core Concept は読み取り専用
- CoreResult に diagnostics が出る

### 5.12 `/spec-inject`

- [x] freshness gate を実行する
- [x] CLI reference operations を実装する
- [x] Agent / LLM 用 command template を実装する
- [x] 通常出力の制約セット最小構造を実装する
- [x] 停止時出力を実装する
- [x] smoke test を追加する

完了条件:

- `statement` / `evidence_origin` / `evidence_ref` を欠く制約を出さない
- Search Keys / Summary / Related Sections だけを根拠にしない
- pending / dirty / stale では通常制約セットを生成しない

### 5.13 `/spec-realign`

- [x] `/spec-inject` 相当の制約生成を再利用する
- [x] Answer 生成契約を実装する
- [x] 制約 / 修正候補 / 不確実性 / 回答を分ける
- [x] Answer 用 smoke test を追加する

完了条件:

- freshness が fresh でない場合は Answer 生成しない
- 制約と矛盾する案は隠さず人間レビュー扱いにする
- raw Source Specs を未整理のまま回答前提にしない

### 5.14 Watcher

- [x] polling watcher を実装する
- [x] debounce を実装する
- [x] snapshot isolation を実装する
- [x] queue file / state file を実装する
- [x] stale lock を実装する
- [x] watcher smoke test を追加する

完了条件:

- 実行中の追加変更を同じ run に混ぜない
- watcher running / queue non-empty の間は dirty になる
- `--once` / interval / debounce / stale lock option が動く

### 5.15 Setup Scripts And Templates

- [x] `spec-grag-setup-project` を実装する
- [x] `spec-grag-setup-system` を実装する
- [x] CODEX command template を実装する
- [x] CLAUDE command template を実装する
- [x] Purpose / Core Concept 雛形の作成規則を実装する
- [x] setup smoke test を追加する

完了条件:

- 既存ファイルを黙って上書きしない
- `--no-init-core-files` の場合は `/spec-core` が失敗することを明示する
- setup は runtime command 中に自動起動しない

### 5.16 Documentation And Release Readiness

- [x] README を作成する
- [x] command usage を記載する
- [x] local dev / smoke 手順を記載する
- [x] archive から旧設計が混ざっていないか確認する
- [x] `none` / `fake` profile の tests / lightweight smoke を実行する

完了条件:

- 初回利用者が setup から smoke まで進める
- `doc/` と README の用語が揃っている
- 旧 full GRAG 前提の説明が root 文書に残らない
- 実 Qdrant / BGE-M3 / real provider を使う実動作検証は本 slice の完了条件に含めない。これは §5.17 の未完了 TODO として扱う。

### 5.17 Real Operation Verification

- [x] local Qdrant service を起動または接続確認する
- [x] FlagEmbedding BGE-M3 を実環境で読み込み、dense / sparse embedding roundtrip を確認する
- [x] Qdrant collection schema が dense / sparse named vectors と RRF retrieval 方針に合うことを実接続で確認する
- [x] temp project に `spec-grag-setup-project` を実行し、生成 config を使って `/spec-core --all` 相当を実行する
- [x] 実 retrieval index 作成後に `/spec-inject` 相当を CLI 経由で実行する
- [x] 実 retrieval index 作成後に `/spec-realign` 相当を CLI 経由で実行する
- [x] `spec-grag-watch --once` を Source Specs 変更後に実行し、freshness が `fresh` に戻ることを確認する
- [x] real provider smoke が必要な環境変数、依存、service URL を README と diagnostics に明示する
- [x] `local-service` / `real-smoke` の skip が残る場合、理由を残リスクとして記録し、「実動作完了」とは報告しない

実行証跡:

- native Qdrant `1.17.1` を `/home/kazuki/.local/bin/qdrant` で起動し、`http://localhost:6333` の server version `1.17.1` を確認した。
- `.venv` に `qdrant-client==1.17.1` / `FlagEmbedding==1.4.0` を導入した。
- `SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_LOCAL_SERVICE=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333` で `tests/test_retrieval_index.py::test_t_i05_embedding_to_qdrant_roundtrip_is_explicit_opt_in` が passing。
- temp project `/tmp/spec-grag-real-iwmHHB` で `setup -> core -> inject -> realign -> watch` を実行し、Qdrant collection `spec_grag_source` に dense named vector `dense` / sparse named vector `sparse` と point count `1` を確認した。
- `retrieval_index_revision.json` に Qdrant URL / collection / BGE-M3 / RRF diagnostics が残ることを確認した。
- 通常 `/spec-core` は `[llm]` から provider を構築する。`SPEC_GRAG_REAL_SMOKE` なしで `codex_cli` / `claude_cli` を呼ばず、fixed summary fallback にも落とさず `failed_required_artifact` と diagnostics を残すことを `tests/test_spec_core.py` / `tests/test_section_metadata_generation.py` / `tests/test_related_sections.py` で確認した。
- 標準 Qdrant / BGE-M3 retrieval は `SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_LOCAL_SERVICE=1` なしでは `retrieval_index_status=skipped` かつ freshness `failed` になる。fake / memory profile の release smoke は明示的に fake config へ切り替えて実行する。
- T-R09 #3/#5 追加確認として、`PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_LOCAL_SERVICE=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q tests/test_watcher.py::test_t_r09_real_watcher_reports_running_queue_lock_heartbeat_and_stale_recovery -q` が passing。watcher 実行中 freshness の `watcher_queue_pending` / `watcher_running` と、watcher 完了後の `last_lock` / `last_heartbeat_at_epoch_ms`、stale recovery 後の `stale_lock_discarded` / `stale_locks[]` を確認した。
- Agent CLI real provider smoke は、archive の非対話実行方式（Codex: `codex --ask-for-approval never exec ... --json --output-schema ... -`、Claude: `claude --print --output-format json --json-schema ...`）に寄せた。repo-local `CODEX_HOME` は `Not logged in`、global `~/.codex` は `Logged in using ChatGPT` だったため、subprocess では repo-local `CODEX_HOME` を継承しない。Codex は structured output schema の strict 条件で一度失敗したため、batch `sections[]` schema と Related Sections schema を strict JSON schema に修正した。
- `SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_REAL_SMOKE_TIMEOUT_SEC=60 SPEC_GRAG_REAL_SMOKE_COMMAND=codex .venv/bin/python -m pytest -q tests/test_llm_provider.py::test_t_u26_real_provider_smoke_is_opt_in -q` が passing。
- `SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_REAL_SMOKE_TIMEOUT_SEC=60 SPEC_GRAG_REAL_SMOKE_COMMAND=claude .venv/bin/python -m pytest -q tests/test_llm_provider.py::test_t_u26_real_provider_smoke_is_opt_in -q` が passing。
- `SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_LOCAL_SERVICE=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 SPEC_GRAG_REAL_SMOKE_TIMEOUT_SEC=60 SPEC_GRAG_REAL_SMOKE_COMMAND=codex .venv/bin/python -m pytest -q tests/test_spec_core.py::test_t_r07_real_core_uses_configured_llm_provider_and_real_index -q` が passing。
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q` が `261 passed, 7 skipped`。skip は default profile では実行対象外にしている real provider / local-service / production-readiness 検証行。
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_LOCAL_SERVICE=1 SPEC_GRAG_REAL_PROVIDER=1 SPEC_GRAG_REAL_RETRIEVAL=1 SPEC_GRAG_PRODUCTION_READINESS=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q` が `267 passed, 1 skipped`。残 skip は real/local-service 有効時には実行対象外になる default CI skip 検証 `tests/test_release_readiness.py`。

完了条件:

- `SPEC_GRAG_REAL_SMOKE=1` と必要な provider 設定を入れた smoke が通る
- `SPEC_GRAG_LOCAL_SERVICE=1` と起動済み Qdrant を使う smoke が通る
- Qdrant / BGE-M3 / RRF の diagnostics が実行結果に残る
- setup した新規 project で `core -> inject -> realign -> watch` の一巡が実サービス込みで確認できる
- 予期しない skipped test がない。skip がある場合は未完了 TODO として明示されている

### 5.18 本運用 Readiness Verification

本 slice は、G-17 の実サービス一巡 smoke とは別に、通常利用者が本運用を開始できる状態かを確認する。ここでいう本運用 readiness は、通常 CLI 設定、永続 Qdrant、BGE-M3、認証済み real CLI provider、watcher、diagnostics、runbook を組み合わせた受入条件を指す。

G-18 が `[ ]` の間は、G-17 が `[x]` でも「本運用可能」と報告しない。

- [x] native Qdrant service の restart 後も collection / point / schema が保持されることを確認する
- [x] FlagEmbedding BGE-M3 の model cache / device / version を diagnostics に記録する
- [x] Codex / Claude CLI が subscription 認証済みの通常 CLI を使い、repo-local `CODEX_HOME` や API key 前提に依存しないことを確認する
- [x] 通常 CLI の `spec-grag core --all` が provider injection なしで `[llm]` から real provider を構築することを、本運用用 config で確認する
- [x] 本運用 CLI 経路が `fake` / `memory` profile に落ちず、real retrieval index を必須 artifact として扱うことを確認する
- [x] real provider failure 時に fake fallback で成功扱いにせず、actionable diagnostics を返すことを確認する
- [x] 本運用 provider gate が `smoke` という名前の環境変数を通常運用前提にしないよう整理する
- [x] watcher 継続運用で複数回の Source Specs 変更、manual core との排他、stale lock recovery、restart 後 diagnostics を確認する
- [x] 複数章・複数ファイルの Source Specs で retrieval / inject / realign / conflict gate / watcher 更新を一巡する
- [x] default 設定では prompt 本文、response 本文、Source Specs 本文全体、secret が run artifact に保存されないことを確認する
- [x] README または runbook に install / start / verify / restart / troubleshoot 手順を記録する

実行証跡:

- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_PRODUCTION_READINESS=1 .venv/bin/python -m pytest -q tests/test_production_readiness.py::test_t_r11_native_qdrant_persists_collection_across_restart` が passing。native Qdrant subprocess を同一 storage path で restart し、collection / point / dense-sparse schema が保持されることを確認した。
- `PATH="$PWD/.venv/bin:$PATH" SPEC_GRAG_REAL_PROVIDER=1 SPEC_GRAG_REAL_RETRIEVAL=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 spec-grag-setup-system --check-only` の `production_readiness.status=ready` と `blocking_reasons=[]` を確認した。
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_PRODUCTION_READINESS=1 SPEC_GRAG_REAL_PROVIDER=1 SPEC_GRAG_REAL_RETRIEVAL=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q tests/test_spec_core.py::test_t_r12_production_core_uses_real_provider_and_retrieval_without_smoke_env` が passing。`SPEC_GRAG_REAL_SMOKE` / `SPEC_GRAG_LOCAL_SERVICE` なしで Codex CLI、Qdrant、BGE-M3 を使う core、real index 後の inject / realign を確認した。
- 同 test で `qdrant_hybrid_retrieve()` による real dense / sparse query が期待 section `docs/spec/search.md#hybrid-retrieval` を返すこと、pending Conflict Review Item が本運用 CLI subprocess の `inject` / `realign` を停止することも確認した。
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_LOCAL_SERVICE=1 SPEC_GRAG_REAL_RETRIEVAL=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q tests/test_watcher.py::test_t_r09_real_watcher_reports_running_queue_lock_heartbeat_and_stale_recovery` が passing。real watcher の Source Specs 更新で `source_update_diff.old_revision/new_revision/changed_sections` と `watch_state.last_success_result.source_update_diff` が残ることを確認した。
- `tests/test_watcher.py::test_t_r13_continuous_mode_processes_multiple_source_changes`、`tests/test_watcher.py::test_t_r13_status_survives_restart_with_freshness_and_diagnostics`、`tests/test_watcher.py::test_t_r13_failed_core_result_keeps_last_success_and_failure_reason` で、継続 watcher、restart diagnostics、failed core result 時の last success / failure reason 分離を確認した。
- `tests/test_spec_core.py::test_t_r15_retrieval_failure_diagnostics_distinguish_required_categories` で、未認証 / service down / schema mismatch / model load failure / provider timeout の diagnostics reason_code を確認した。
- `tests/test_production_readiness.py::test_t_r15_readme_fixes_production_readiness_report_sections` で、本運用報告の区分テンプレートを README に固定した。
- `tests/test_spec_core.py::test_t_r12_real_provider_gate_uses_normal_operation_env_without_smoke` と `tests/test_spec_core.py::test_t_r12_real_retrieval_gate_uses_normal_operation_env_without_smoke` で、本運用 gate が `SPEC_GRAG_REAL_PROVIDER` / `SPEC_GRAG_REAL_RETRIEVAL` であり、`smoke` 名の env を通常運用前提にしないことを確認した。
- `tests/test_setup_scripts.py::test_t_r12_setup_project_config_is_production_stack_ready` で、setup 後 config が codex_cli / FlagEmbedding BGE-M3 / Qdrant の本運用 stack であることを確認した。
- Test Agent が `tests/test_spec_inject.py::test_review_pending_conflict_items_are_loaded_from_real_context_artifact` を 10 連続、default full suite を 10 連続で実行し、いずれも passing。pending conflict flaky は今回再現しなかった。
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q` が `261 passed, 7 skipped`。skip は real-smoke / local-service / production-readiness の opt-in 対象。
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_LOCAL_SERVICE=1 SPEC_GRAG_REAL_PROVIDER=1 SPEC_GRAG_REAL_RETRIEVAL=1 SPEC_GRAG_PRODUCTION_READINESS=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q` が `267 passed, 1 skipped`。残 skip は real/local-service profile 有効時には対象外になる default CI skip 検証。

完了条件:

- `doc/TEST_SPEC.ja.md` の G-18 / T-R11〜T-R15 がすべて `[x]` になる
- default passing、local-service / real-smoke passing、本運用 readiness passing を分けて報告できる
- 未実行または失敗が残る場合は残 TODO として報告し、「本運用可能」とは報告しない

## 6. Cross-cutting Review Checklist

各 slice の統合時に、Review Agent または Lead Agent が確認する。

- [x] Agent / LLM と CLI の責務境界が崩れていない
- [x] Related Sections が候補に弱まりすぎていない
- [x] Related Sections が full graph に戻っていない
- [x] Conflict Review Item が warning-only になっていない
- [x] pending conflict を無視して進まない
- [x] resolved だが未反映の判断を恒久 source of truth にしていない
- [x] `[llm]` を `/spec-core` 以外に混同していない
- [x] LLM 呼び出し上限が守られている
- [x] Source Specs の生テキストを未整理で回答に混ぜていない
- [x] Qdrant / BGE-M3 / RRF の diagnostics が残る
- [x] watcher snapshot isolation が守られている

証跡:

- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q` が `261 passed, 7 skipped`。
- `tests/test_spec_inject.py` / `tests/test_spec_realign.py` で Agent supplied constraints / answer を検証し、`[llm]` provider を inject / realign の自動生成に使わないことを確認した。
- `tests/test_related_sections.py` / `spec_grag/related_sections.py` は候補生成と選定補助に閉じ、property graph / full graph traversal へ戻っていない。
- `tests/test_conflict_review.py` / `tests/test_freshness.py` で pending conflict 停止、resolved stale 判定、warning-only 回避を確認した。
- `tests/test_watcher.py` で snapshot / queue / lock を確認した。real watcher は `watcher_queue_pending` / `watcher_running` / heartbeat / stale recovery diagnostics まで確認した。
- real retrieval run の `retrieval_index_revision.json` に Qdrant URL、collection、BGE-M3、dense/sparse named vectors、RRF diagnostics が保存された。
- provider 実行境界として、通常 `/spec-core` が `[llm]` provider を config から解決し、real provider 実行指定なしでは CLI provider を呼ばず失敗 diagnostics を残すことを確認した。
- `/spec-core` production 経路を `section_metadata.generate_section_metadata_result` に接続し、`tests/test_spec_core.py::test_t_e07_spec_core_batches_metadata_and_reuses_unchanged_sections` で 50+ section の batch 呼び出し、source_hash unchanged の LLM skip、retrieval index reuse による embedding skip diagnostics を確認した。
- `stable_section_uid` は heading 文字列ではなく文書内 ordinal を seed にし、`tests/test_section_parser.py::test_t_u02_stable_section_uid_survives_heading_rename` で heading rename 後の UID 一致を確認した。
- `/spec-realign` の clarification は CLI 側の文面 heuristic をやめ、空入力または Agent supplied `clarification_required` だけで停止することを `tests/test_spec_realign.py` で確認した。
- `/spec-core` runtime 経路を `config.load_config(..., allow_non_standard_providers=True)` と `section_parser.parse_markdown_sections` に統一し、H1-only、heading なし、duplicate heading、`sources.exclude`、include no-match を `tests/test_spec_core.py` で確認した。
- watcher snapshot も config loader の resolved source files を使い、`tests/test_watcher.py::test_watcher_snapshot_respects_config_loader_sources_exclude` と `test_watcher_settings_fail_when_sources_include_matches_no_files` で確認した。

### 6.1 CLAUDE 監査指摘 disposition

| ID | 判定 | 対応 / 証跡 | 残 TODO |
|---|---|---|---|
| CA-01 `/spec-core` batch production 統合 / T-E07 | 既対応 | `tests/test_spec_core.py::test_t_e07_spec_core_batches_metadata_and_reuses_unchanged_sections` | real provider batch 実測は本運用性能検証の別課題 |
| CA-02 `stable_section_uid` heading rename | 既対応 | `tests/test_section_parser.py::test_t_u02_stable_section_uid_survives_heading_rename` | section 挿入 / split / merge の高度な同一性推定は別課題 |
| CA-03 `retrieval_index_status=skipped` freshness 伝播 | 既対応 | `tests/test_spec_core.py::test_g11_standard_retrieval_without_local_service_is_failed_not_fresh`, `test_t_r15_retrieval_failure_diagnostics_distinguish_required_categories` | なし |
| CA-04 `/spec-realign` clarification heuristic | 既対応 | `tests/test_spec_realign.py::test_t_e05_non_empty_ambiguous_words_do_not_trigger_cli_heuristic` | なし |
| CA-05 pending conflict flaky 疑惑 | 既対応 / 今回再現なし | Test Agent が target test 10 連続、default full suite 10 連続で passing | xdist / seed 固定 stress は未実行 |
| CA-06 T-I17 watcher/core 排他証跡 | 既対応 | `test_g14_manual_spec_core_does_not_update_artifacts_while_watcher_running`, `test_watcher_heartbeat_keeps_long_internal_core_from_looking_stale`, `test_t_r13_continuous_mode_processes_multiple_source_changes` | なし |
| CA-07 T-R11 本運用 service bootstrap / persistence | 採用 / 対応済み | `tests/test_production_readiness.py::test_t_r11_native_qdrant_persists_collection_across_restart` | なし |
| CA-08 T-R12 本運用 CLI 経路 | 採用 / 対応済み | `tests/test_setup_scripts.py::test_t_r12_setup_project_config_is_production_stack_ready`, `tests/test_spec_core.py::test_t_r12_production_core_uses_real_provider_and_retrieval_without_smoke_env` | なし |
| CA-09 T-R13 本運用 watcher / recovery | 採用 / 対応済み | `test_t_r13_continuous_mode_processes_multiple_source_changes`, `test_t_r13_status_survives_restart_with_freshness_and_diagnostics`, `test_t_r13_failed_core_result_keeps_last_success_and_failure_reason`, `test_t_r09_real_watcher_reports_running_queue_lock_heartbeat_and_stale_recovery` | なし |
| CA-10 T-R14 本運用 project data roundtrip | 採用 / 対応済み | `test_t_r12_production_core_uses_real_provider_and_retrieval_without_smoke_env`, `test_t_r09_real_watcher_reports_running_queue_lock_heartbeat_and_stale_recovery` | なし |
| CA-11 T-R15 本運用 reporting / privacy / runbook | 採用 / 対応済み | `test_t_r15_readme_fixes_production_readiness_report_sections`, `test_t_r15_retrieval_failure_diagnostics_distinguish_required_categories`, README Production Readiness | なし |
| CA-12 `/spec-core` source no-match / empty artifact freshness | 採用 / 対応済み | `tests/test_spec_core.py::test_g11_runtime_core_fails_when_sources_include_matches_no_files` | なし |
| CA-13 `/spec-core` sources.exclude 無視 | 採用 / 対応済み | `tests/test_spec_core.py::test_g11_runtime_core_respects_sources_exclude_in_artifacts`, `tests/test_watcher.py::test_watcher_snapshot_respects_config_loader_sources_exclude` | なし |
| CA-14 `/spec-core` duplicate heading section_id 衝突 | 採用 / 対応済み | `tests/test_spec_core.py::test_g11_runtime_core_assigns_unique_ids_for_duplicate_headings` | なし |
| CA-15 TEST_SPEC [x] の runtime 経路不足 | 採用 / 対応済み | `tests/test_spec_core.py::test_g11_runtime_core_uses_section_parser_for_h1_only_source_specs`, `test_g11_runtime_core_uses_section_parser_for_no_heading_source_specs`, `test_g11_runtime_core_assigns_unique_ids_for_duplicate_headings`, `test_g11_runtime_core_respects_sources_exclude_in_artifacts`, `test_g11_runtime_core_fails_when_sources_include_matches_no_files` | なし |

## 7. 現在の次アクション

- [x] §6 Cross-cutting Review Checklist を証跡ベースで実施し、チェック状態を更新する
- [x] G-17 Real Operation Verification を開始する
- [x] local Qdrant / FlagEmbedding BGE-M3 / real provider の実行環境を確認する
- [x] `local-service` / `real-smoke` の skipped test を実行対象に切り替える
- [x] 実サービス込みの `core -> inject -> realign -> watch` 一巡後にのみ「実動作完了」と報告する
- [x] 大量の git 差分を実装差分 / 旧版 archive 退避差分 / generated 差分に分けて確認する
- [x] G-18 本運用 Readiness Verification を完了する
- [x] 本運用 provider gate が `smoke` という名前の環境変数を通常運用前提にしないよう整理する
- [x] Codex / Claude CLI subscription 認証を本運用条件として確認する
- [x] native Qdrant service restart / persistence を本運用条件として確認する
- [x] 長時間 watcher / restart / stale recovery を本運用条件として確認する
- [x] README または runbook に本運用の install / start / verify / restart / troubleshoot 手順を記録する

差分分類メモ:

- 実装差分: `AGENTS.md`, `CLAUDE.md`, `README.md`, `doc/DESIGN.ja.md`, `doc/EXTERNAL_DESIGN.ja.md`, `doc/IMPLEMENTATION_PLAN.ja.md`, `doc/TEST_SPEC.ja.md`, `pyproject.toml`, `uv.lock`, 現行 `spec_grag/*.py`, `spec_grag/templates/`, 現行 `tests/test_*.py`。
- 旧版 archive 退避差分: root から削除された `BAK/`, 旧 `doc/PHASE*`, `doc/SURVEY/`, 旧 Rust / full GRAG 系 `spec_grag/*`, `scripts/`, `spike/`, `templates/` は `archive/full-grag-2026-05-05/` 配下へ退避済み。
- generated / runtime 差分: root `.spec-grag/` の旧生成物削除、`.gitignore` 更新、dependency lock 更新。Qdrant は git 管理外の user systemd service と `/tmp/spec-grag-qdrant-*` を使う。
