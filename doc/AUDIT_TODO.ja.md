# spec-grag 監査 TODO

> 作成日: 2026-05-01
> 目的: Phase 9 後の設計充足、production 経路、E2E、GRAG 品質、障害系を通常開発 TODO から分離して追跡する。

本書は `doc/TODO.md` の肥大化を避けるための監査専用 TODO である。通常の実装作業順は `doc/TODO.md`、外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md` を正とする。

## 記録形式

- 状態: `[ ]` 未着手、`[x]` 完了、`[~]` 実行中、`[!]` 要修正、`[-]` 対象外
- 判定: `OK` / `MISSING` / `PARTIAL` / `DRIFT` / `RISK` / `BLOCKED`
- 証跡: test 名、command、artifact path、該当 file / line、run id を残す
- production 到達性: 単なる文字列存在ではなく、production config から到達可能かで判定する

## 推奨順

1. Preflight 監査: LLM 消費なし、または小さい probe で設定・契約の大穴を潰す
2. Real provider 小規模 probe: Codex / Claude / Ollama の実機 schema / latency / token を確認する
3. Full GRAG build: `spec-core --all` を production config で実行する
4. E2E / GRAG 品質監査: build 済み graph を使って injection / realign / retrieval 品質を見る
5. Failure / recovery 監査: 壊れた sidecar、metadata mismatch、pending state、provider failure を見る

## 現在の前提

- repo-local production config: `.spec-grag/config.toml`
- source specs: `テスト用ドキュメント/**/*.md`
- Purpose: `テスト用ドキュメント/01_システム目標.md`
- Purpose は `sources.exclude` で Source specs から除外する
- extraction: `gpt-5.4-mini` / `claude-haiku-4-5` の軽量 provider override
- embedding: Ollama `bge-m3` / dim `1024`
- section 化: `section_max_heading_level = 4`
- batch extraction: `batch_size = 6` / `batch_max_chars = 4000`
- runtime 方針: local daily は watcher required / 同期 core 更新なし、CI / watcherなしは foreground incremental 可、production は dirty / pending / stale を fail-fast
- Concept diff 方針: pending は単一。pending 中の追加変更は queued change と provisional concept cache に保存し、pending 解消後に再評価する

## 0. Preflight 監査

- [x] `.spec-grag/config.toml` が production policy を通る
  - 判定: OK
  - 証跡: `validate_project_config(..., smoke=False)` -> `_runtime_mode = production`
- [x] `purpose_file` が存在し、Source specs に混入していない
  - 判定: OK
  - 証跡: `purpose_file = テスト用ドキュメント/01_システム目標.md`、`purpose_exists = true`、`purpose_in_sources = false`
- [x] `sources.include` / `sources.exclude` が意図どおり効く
  - 判定: OK
  - 証跡: `source_count = 14`、`first_source = テスト用ドキュメント/10_問題点一覧.md`、`exclude = ["テスト用ドキュメント/01_システム目標.md"]`
- [x] `section_max_heading_level = 4` で manifest 粒度が期待どおり
  - 判定: OK
  - 証跡: `section_count = 418`、`H1 = 14`、`H2 = 101`、`H3 = 244`、`H4 = 59`、`H5 = 0`、`H6 = 0`
- [x] batch 分割数、平均 section 数、単独 batch 数を記録する
  - 判定: OK
  - 証跡: `batch_size = 6`、`batch_max_chars = 4000`、`batch_count = 84`、`avg_sections_per_batch = 4.98`、`single_section_batches = 8`
- [x] `uv run --with pytest pytest tests -q` が通る
  - 判定: OK
  - 証跡: `161 passed in 108.97s (0:01:48)`

## A. Contract Traceability Matrix

外部契約と実装 / test の対応を確認する。

| 契約 | 期待 | 実装 | test / 証跡 | 判定 | 備考 |
|---|---|---|---|---|---|
| GRAG Freshness | readiness gate で fresh / dirty / pending / stale を判定し、mode 別に扱う | `spec_grag/readiness.py` | `tests/test_phase10_readiness.py` | OK |  |
| Purpose read-only | Purpose を更新しない |  |  |  |  |
| Concept diff 承認 | 未承認 Concept を採用しない |  |  |  |  |
| Concept diff 単一 pending | pending 中は追加 diff を多重生成せず queue/cache に積む | `spec_grag/concept_index.py` / `watch_state.py` | `tests/test_phase10_readiness.py` | OK |  |
| provisional concept cache | 未承認 Concept 候補を差分検出効率化だけに使う | `spec_grag/watch_state.py` | `tests/test_phase10_readiness.py` | OK | accepted Concept と混ぜない |
| foreground approval | 人が呼ぶ spec-core / inject / realign は pending 承認フロー対象 | `options.approval` / approval_prompt | `tests/test_cli.py` | OK | 外部 slash command 追加なし |
| watcher background role | watcher は承認プロンプトを出さず pending / queue / cache 更新で停止 | `spec_grag/watcher.py` | `tests/test_phase10_readiness.py` | OK | polling 実装 |
| Conflict 候補 | 未承認 Conflict を確定扱いしない | `spec_grag/conflict_review.py` | `tests/test_cli.py` / `tests/test_injection_realign.py` | OK | `/spec-core` auto generation + approved_conflicts sidecar |
| Answer 入力境界 | task_prompt + InjectionContext のみ |  |  |  |  |
| Source evidence | source_section_id / source_span / source_hash を保持 |  |  |  |  |
| section 化規約 | `section_max_heading_level` 超過を親へ統合 |  |  |  |  |
| Concept apply hash | base hash mismatch で blocked |  |  |  |  |
| NeedMoreContext | 情報不足時は blocked |  |  |  |  |
| ReviewNotes | 不確実性・未承認候補を隠さない |  |  |  |  |

重点 TODO:

- [ ] `doc/EXTERNAL_DESIGN.ja.md` の各節に contract id を付与するか検討
- [ ] `doc/DESIGN.ja.md` の内部契約と実装 file / test の対応を埋める
- [ ] `MISSING` / `PARTIAL` / `DRIFT` を issue 化できる粒度に分割する

## B. Production Readiness Matrix

smoke / fallback / fake が production config から到達可能でないことを確認する。

| 対象 | production 到達性 | 許容条件 | test / 証跡 | 判定 | 備考 |
|---|---|---|---|---|---|
| `stable_hash` embedding | 到達不可 | smoke 明示時のみ | resolved `embedding_provider = ollama` | OK |  |
| `template` answer | 到達不可 | smoke 明示時のみ | resolved `answer_provider = codex`, `failure_fallback = failed` | OK |  |
| `orchestrator_rule_based` classification | 到達不可 | budget skip / smoke 明示時のみ | resolved `classification_provider = codex`, `fallback_on_error = false` | OK |  |
| `source_derived` concept diff | 到達不可 | smoke 明示時のみ | resolved `concept_diff_provider = codex`, `fallback_on_error = false` | OK |  |
| deterministic extraction | 到達不可 | smoke 明示時のみ | resolved `extraction_mode = schema_llm`, `extraction_provider = codex` | OK |  |
| `fallback_on_error = true` | 到達不可 | production では不可 | classification / concept_diff / query_planner / community_report all false | OK |  |
| `failure_fallback = "template"` | 到達不可 | production では不可 | resolved `answer_failure_fallback = failed` | OK |  |
| mock / fake provider | 未確認 | test 専用 |  |  | 後続の静的 trace で確認 |
| token-match 主導 retrieval | 未確認 | deterministic validator / debug 限定 |  |  | 後続の静的 trace で確認 |

重点 TODO:

- [ ] production config からの provider resolution を表にする
- [x] fallback event が provider config から出ないことを確認
  - 判定: OK
  - 証跡: `fallback_events = []`
- [ ] smoke config が production mode で拒否されることを確認

## C. E2E Scenario Matrix

full build 後に実行する。

| シナリオ | command | 期待 | artifact / 証跡 | 判定 | 備考 |
|---|---|---|---|---|---|
| production full core | `spec-core --all` | `ok`、fallback なし |  |  |  |
| no-change incremental | `spec-core` | no-change / ok |  |  |  |
| injection | `spec-inject` | InjectionContext |  |  |  |
| realign | `spec-realign` | RealignResult または NeedMoreContext |  |  |  |
| pending Concept block | pending diff 作成後 `spec-inject` | blocked |  |  |  |
| Concept accept/reject/revise/apply | `options.approval` | state 遷移 OK | `tests/test_cli.py` | OK | legacy wrapper flags は内部互換 |
| hash mismatch | stale pending diff apply | blocked |  |  |  |
| Answer NeedMoreContext | LLM が needs_more_context | blocked |  |  |  |
| ConflictNotes / ReviewNotes | conflict / review evidence | Answer で明示 |  |  |  |
| embedding metadata mismatch | provider / dim 変更後 incremental | rebuild 要求 |  |  |  |

### C-2. Watcher / Readiness Gate TODO

日常利用では watcher が Source specs 変更を検知し、background incremental を実行する。slash command は重い core 更新を毎回同期実行せず、readiness gate と承認フローだけを担う。

- [x] `watch_state` artifact を設計する
  - 期待: `fresh` / `dirty` / `pending` / `stale`、last processed semantic hash、running / failed 状態、last run id を保存する
- [x] `watch_queue` artifact を設計する
  - 期待: pending 中に変更された `source_section_id`、semantic hash、理由、発生時刻を保存する
- [x] provisional concept cache を設計する
  - 期待: label、normalized label、supporting sections、source semantic hashes、confidence、first_seen / last_seen、provider / model / prompt version を保存する
  - 期待: 非承認時は cache / pending を残し、次回コマンドで同じ承認を求める
  - 禁止: InjectionContext / Answer / Conflict 確定 / production readiness の authoritative input に使わない
- [x] Concept diff の単一 pending 制約を実装する
  - 期待: pending がある間は新しい diff を作らず queue/cache 更新だけ行う
  - 期待: pending 解消後、queued change を最新 Concept base hash で再評価する
- [x] foreground `/spec-core` の承認フローを実装 / 監査する
  - 期待: 人が呼んだ `/spec-core` は pending Concept diff / Conflict 候補を `/spec-inject` と同じく確認対象にする
  - 期待: background watcher の core 更新では承認プロンプトを出さない
- [x] `/spec-inject` / `/spec-realign` を readiness gate 経由へ変更する
  - local daily: dirty なら同期 core 更新せず blocked / watcher waiting
  - CI / watcherなし: foreground incremental 可
  - production: dirty / pending / stale は fail-fast
- [x] E2E を追加する
  - pending Concept diff 中に source 追加変更しても diff が多重生成されない
  - pending 解消後に queued section が再評価される
  - provisional cache が未承認 Concept として InjectionContext に混入しない
  - local daily dirty で inject / realign が同期 core を走らせない
  - CI mode では watcherなしでも foreground incremental が走る
  - production mode では dirty / pending / stale が fail-fast する

実装証跡（2026-05-02）:

- `spec_grag/config.py`: `[runtime]` schema と `resolve_runtime_policy()`、`[watcher]` schema を追加。production は dirty / pending / stale fail-fast を強制し、watcher は `enabled` / timing / state path / queue path を config から解決。
- `spec_grag/readiness.py`: source manifest / semantic hash / artifact / embedding metadata / extractor version / pending state を横断した readiness gate を追加。
- `spec_grag/watch_state.py`: `watch_state.json`、`watch_queue.json`、`provisional_concept_cache.json`、heartbeat lock を追加。
- `spec_grag/watcher.py`: `spec-grag-watch` 常駐 polling watcher を追加。single worker で開始時 snapshot を処理し、実行中追加変更は `watch_queue` に積んで次サイクルで drain する。
- `spec_grag/readiness.py`: watcher running / queued changes を readiness gate に統合。local daily は blocked、production は fail-fast、CI / watcherなしは foreground incremental を許可。
- `tests/test_phase10_readiness.py`: local daily blocked、CI foreground incremental、production fail-fast、単一 pending queue、queued 再評価、provisional cache 非混入、background watcher 非承認、watcher running / queue blocker、実行中変更 queue、次サイクル drain を regression 化。

## D. GRAG Quality / Retrieval Evaluation

「動く」ではなく「GRAGとして役に立つ」ことを見る。

| 観点 | 評価クエリ | 期待 | 証跡 | 判定 | 備考 |
|---|---|---|---|---|---|
| raw chunk retrieval |  | source excerpt が取れる |  |  |  |
| dense retrieval |  | 日本語 semantic hit |  |  |  |
| BM25 sparse retrieval |  | 固有名詞 / API 名 hit |  |  |  |
| RRF rank fusion |  | dense + sparse + graph が統合 |  |  |  |
| graph expansion |  | relation 経由候補が増える |  |  |  |
| QueryPlan |  | 検索語・章候補・曖昧性を出す |  |  |  |
| ChapterAnchor |  | InjectionContext に反映 |  |  |  |
| cluster / community |  | 関連 cluster が出る |  |  |  |
| evidence traceability |  | section/span/hash が追跡可能 |  |  |  |
| unresolved relation |  | graph に入らず ReviewNotes / sidecar |  |  |  |

評価クエリ候補:

- [ ] Core と Customize の境界を説明して
- [ ] ImageUploadField / FileUploadField / ImageGalleryField の違い
- [ ] Action signal と emit / 購読の関係
- [ ] section_max_heading_level で `#####` が親に統合される影響
- [ ] Concept にないが Source specs にある制約の扱い

## E. Failure Mode / Recovery Tests

| 障害 | 期待 | test / command | 判定 | 備考 |
|---|---|---|---|---|
| Codex schema violation | local validation で retry / fail |  |  |  |
| Claude schema violation | local validation で retry / fail |  |  |  |
| LLM timeout | failed / degraded が明示 |  |  |  |
| Ollama unavailable | embedding_provider_failed |  |  |  |
| dimension mismatch | incremental failed / rebuild 要求 |  |  |  |
| corrupt sidecar | quarantine して再生成 |  |  |  |
| invalid source_span | ReviewNotes |  |  |  |
| ambiguous excerpt | ReviewNotes |  |  |  |
| changed section | stale artifact delete / regenerate |  |  |  |
| removed section | stale artifact delete |  |  |  |

## F. Sidecar & Artifact Lifecycle Tests

| artifact | 作成 | 更新 | stale / dirty | corruption recovery | 判定 |
|---|---|---|---|---|---|
| `source_manifest.json` |  |  |  |  |  |
| graph store |  |  |  |  |  |
| vector store |  |  |  |  |  |
| `document_chunks.json` |  |  |  |  |  |
| `chunk_vector_index.json` |  |  |  |  |  |
| `bm25_index.json` |  |  |  |  |  |
| `unresolved_relations.json` |  |  |  |  |  |
| `chapter_anchors.json` |  |  |  |  |  |
| `cluster_snapshot.json` |  |  |  |  |  |
| `concept_index.json` |  |  |  |  |  |
| run artifacts | run artifact / execution diagnostics に timing_summary / stage_timings を保存し、blocked / failed でも完了済み timings を残す | `spec_grag/timing.py`, `spec_grag/run_artifacts.py`, `spec_grag/cli.py` | `tests/test_phase11_timings.py` | OK | token usage は provider から安定取得できる場合に追加 |

## G. Real Provider Optional Smoke

実 provider が利用可能な環境だけで実施する。mock だけでは CLI 実機の schema / timeout / token / auth 問題を拾えない。

| provider | probe | 期待 | token / latency | 判定 | 備考 |
|---|---|---|---|---|---|
| Codex extraction | `gpt-5.4-mini` batch 3 件 | schema valid | 81.9s / 67,715 total tokens | OK | JSON valid 3 of 3、source_section_id 逸脱 0 |
| Codex judgment | `gpt-5.4` classification / answer | schema valid |  |  |  |
| Claude extraction | `claude-haiku-4-5` batch 1 件 | schema valid |  |  |  |
| Claude judgment | `claude-sonnet-4-6` answer | schema valid |  |  |  |
| Ollama embedding | `bge-m3` probe | dim 1024 | probe returned `embedding_dim = 1024` | OK | `ollama list` includes `bge-m3:latest` |

直近の参考値:

- `gpt-5.4-mini` batch extraction 3 件: 81.9s / 67,715 total tokens / JSON valid 3 of 3
- 現 self project: 418 sections / 84 batches 見込み

## Full Build 実施メモ

実行前:

- [x] Preflight 監査で `BLOCKED` がない
- [~] Plus / provider 使用枠に余裕がある
  - 判定: RISK
  - 証跡: full build 見込みは 84 Codex local messages。ユーザー確認のうえ production full build を実施する
- [x] `ccusage-codex` の開始前 usage を記録
  - 証跡: `ccusage-codex session --since 2026-05-01 --timezone Asia/Tokyo --offline --json`
  - baseline total: input `231,766,221`、cached input `224,926,592`、output `653,769`、reasoning output `235,469`、total `232,419,990`、cost `$43.20305025`
  - 注意: baseline は現在の Codex 対話 session を含むため、full build 後は差分と新規 session を確認する
- [x] `.spec-grag/graph` の既存 metadata を確認
  - 証跡: `embedding_metadata.json` は旧 smoke 生成物。provider `stable_hash`、model `sha256-v1`、dimension `8`
  - 判定: production full build で `ollama` / `bge-m3` / dim `1024` へ再生成が必要

実行:

```bash
uv run spec-grag-slash spec-core --all --pretty
```

実行後:

- [x] `ResultEnvelope.status`
  - 1回目 `spec-core --all`: `failed`
  - 原因: `community_report_provider_failed:Community report LLM failed: [Errno 7] Argument list too long: 'codex'`
- [x] elapsed
  - 1回目 `spec-core --all`: 約 75 分
  - 内訳目安: Codex batch extraction 約 46 分、Ollama `bge-m3` CPU embedding 約 29 分
- [!] token / call 数
  - 判定: PARTIAL
  - 証跡: `ccusage-codex` は現在の対話 session の増分は見えるが、`codex exec --ephemeral --json` subprocess は session 集計に出ていない
  - 対応: Phase 11 で run artifact に `timing_summary` / `stage_timings` と stage 別 `llm_calls` を保存
  - 残課題: CLI token usage は provider から安定取得できる場合に追加する
- [x] warnings / degraded_components
  - warnings: `concept_index_embedding_metadata_mismatch_rebuilt`、`community_report_provider_failed:*Argument list too long*`
  - degraded_components: `[]`
- [x] fallback_events
  - 判定: OK
  - 証跡: fallback ではなく provider fail-fast として `failed`
- [!] generated artifacts
  - 判定: PARTIAL / RISK
  - 証跡: `failed` だが `property_graph_store.json`、`vector_store.json`、`document_chunks.json`、`chunk_vector_index.json`、`bm25_index.json`、`embedding_metadata.json`、`chapter_anchors.json`、`concept_index.json` は production artifact に更新済み
  - 未完了: `cluster_snapshot.json` と `source_manifest.json` は旧 artifact のまま
  - 要修正: `/spec-core` failed 時の artifact transaction / rollback / staging 方針を監査する
- [x] unresolved relation 件数
  - 証跡: `unresolved_relations.json` 更新済み、size `32776` bytes
- [x] Concept diff pending 有無
  - 1回目 `spec-core --all`: `pending_concept_diff_id = null`

実装修正:

- [x] Codex CLI prompt を argv ではなく stdin で渡す
  - 修正: `CodexCLIAdapter` は `codex exec -` + `stdin_text=prompt` を使う
  - 検証: `uv run --with pytest pytest tests/test_llm_adapters.py -q` -> `14 passed`
- [x] chunk / graph vector embedding を incremental で再利用する
  - 修正: `chunk_id + chunk_hash + embedding metadata` 一致時に `chunk_vector_index.json` の embedding を再利用する
  - 修正: `node_id + source_hash + embedding metadata` 一致時に `vector_store.json` の embedding を再利用する
  - 検証: `uv run --with pytest pytest tests/test_embedding_reuse.py tests/test_llm_adapters.py -q` -> `16 passed`
  - 検証: `uv run --with pytest pytest tests/test_embedding_reuse.py tests/test_core_e2e.py tests/test_phase9_production_policy.py -q` -> `28 passed`
  - 検証: `uv run --with pytest pytest tests -q` -> `163 passed in 102.84s`
- [x] 修正後に incremental `spec-core` を実行し、community report 以降が完了するか確認する
  - 結果: `degraded`
  - elapsed: 約 1 分 30 秒
  - run artifact: `.spec-grag/runs/20260501T120824.598916Z-spec-core-5ce6c4e8b3be.json`
  - `pending_concept_diff_id = diff-76f8e35d58b55cb2`
  - `updated_sources`: Uppy / upload field 周辺 5 sections
  - warnings: Concept diff proposal の注意 3 件
  - 判定: `community_report` の `Argument list too long` は解消。degraded は pending Concept diff による通常状態
- [x] pending Concept diff を解消して no-change incremental を実測する
  - 判定: OK
  - 処理（Phase 10 前の旧挙動）: `diff-76f8e35d58b55cb2:hunk-1` は Core Concept へ入れるには粒度が細かいため reject し、`--apply diff-76f8e35d58b55cb2` で pending を除去
  - 証跡: `applied_hunk_ids = []`、`pending_concept_diff_id = null`
  - Phase 10 後の方針: reject / 非承認は pending を除去せず、同じ承認を次回も求める。pending 解消は承認 apply または修正後の承認 apply で行う
- [x] no-change incremental の性能確認
  - 判定: OK
  - 1回目: pending 解消後の no-change `spec-core` は `updated_sources = []` / `status = ok` だが `real 74.13s`
  - 原因: source 差分なしでも `community_report` の Codex CLI が呼ばれていた
  - 修正: source 差分なし、`graph_revision` 同一、Concept index chunk 構成同一なら `cluster_snapshot.json` を再利用し、community report LLM を呼ばない
  - 2回目修正: no-change では manifest 比較直後に fast return し、graph / vector / chunk / sidecar 再構築に入らない
  - 修正後: `updated_sources = []` / `status = ok` / `real 2.99s`
  - run artifact: `.spec-grag/runs/20260501T194714.123556Z-spec-core-8b105075d8b6.json`
  - run artifact: `.spec-grag/runs/20260501T195502.960205Z-spec-core-0880c93596d6.json`
  - 検証: `uv run --with pytest pytest tests/test_core_e2e.py tests/test_embedding_reuse.py tests/test_llm_adapters.py tests/test_phase9_production_policy.py -q` -> `44 passed in 19.40s`
  - 検証: `uv run --with pytest pytest tests -q` -> `165 passed in 110.79s`
- [x] source specs 変更時の incremental 実測
  - 判定: RISK
  - 前提: `docs/core/concept.md` がほぼ空のため、意味変更なしの空行変更でも Source-derived Concept 候補が出やすい
  - `20_管理画面の基本設計.md` の空行変更: `updated_sources = 1`、`pending_concept_diff_id = diff-001c8055efc5512d`、`real 77.08s`
  - `10_問題点一覧.md` の空行変更: `updated_sources = 1`、`pending_concept_diff_id = diff-1b28c01ddea0259d`、`real 38.91s`
  - 測定用変更の復元: `updated_sources = 2`、`pending_concept_diff_id = diff-8e0665d9be88c021`、`real 71.76s`
  - 復元後 no-change 確認: `updated_sources = []`、`concept_diff = null`、`real 2.93s`
  - 対応（Phase 10 前の旧挙動）: 測定で生成された Concept diff はすべて reject/apply 済み。`テスト用ドキュメント/10_問題点一覧.md` と `テスト用ドキュメント/20_管理画面の基本設計.md` は差分なしへ復元済み
- [x] format-only change の heavy path を抑制する
  - 判定: OK
  - 修正: source manifest に `raw_hash` / `semantic_hash` を分離して保存し、空行・末尾空白・通常 prose の空白差分は `format_only_section_ids` として扱う
  - 期待: `raw_hash` は audit / 表示 / source_span 確認用、`semantic_hash` は extraction / embedding / graph update 判定用
  - 実測: `10_問題点一覧.md` の空行追加は `updated_sources = 1` だが `concept_diff = null`、`real 2.04s`
  - 実測: 空行復元も `concept_diff = null`、`real 3.08s`
  - 実測: 復元後 no-change は `updated_sources = []`、`concept_diff = null`、`real 3.62s`
  - 検証: `uv run --with pytest pytest tests/test_manifest.py tests/test_core_e2e.py::test_spec_core_incremental_format_only_change_updates_manifest_without_rebuild tests/test_core_e2e.py::test_spec_core_incremental_no_change_reuses_cluster_snapshot_without_llm tests/test_core_e2e.py::test_spec_core_incremental_concept_change_bypasses_no_change_fast_path -q` -> `18 passed in 1.47s`
  - 検証: `uv run --with pytest pytest tests -q` -> `168 passed in 116.50s (0:01:56)`

## 監査結果サマリ

| 日付 | 範囲 | 結果 | blocker | 次アクション |
|---|---|---|---|---|
| 2026-05-01 | Preflight / provider前提一部 | OK。production config valid、Purpose除外OK、418 sections / 84 batches、pytest 161 passed、Ollama bge-m3 dim 1024 | なし | full build 前に ccusage baseline と既存 graph metadata を記録 |
| 2026-05-01 | production `spec-core --all` 1回目 | FAILED。Codex extraction と embedding artifact は生成されたが、community_report が argv 長すぎで失敗 | Codex prompt argv 渡し、failed 時 artifact 部分更新 | Codex prompt stdin 化、embedding差分再利用、artifact transaction監査 |
| 2026-05-01 | 修正後 incremental `spec-core` | DEGRADED。約1分30秒で完了、pending Concept diff 作成、community_report ARG_MAX 解消 | pending Concept diff | Concept diff を処理して no-change incremental / inject / realign へ進む |
| 2026-05-01 | no-change incremental 実測 | OK。Phase 10 前の旧 reject/apply 後、`updated_sources = []`。不要な community_report LLM と artifact 再構築を抑制し 74.13s -> 17.77s -> 2.99s | source manifest 読み取りと hash 比較の数秒は残る | inject / realign E2E、artifact transaction監査 |
| 2026-05-01 | source specs 変更時 incremental 実測 | RISK。1 section の空行変更でも Concept が空に近いため pending Concept diff が発生。38.91s〜77.08s | Concept baseline 未整備により Concept diff が過敏 | Concept 初期採用方針、Concept diff 粒度、changed section 後段コスト削減を検討 |
| 2026-05-01 | format-only semantic hash 対応 | OK。空行変更は heavy path に入らず `concept_diff = null`、約2〜3秒。full pytest 168 passed | 意味変更時の Concept diff 過敏さは別課題 | watcher / readiness gate、provisional concept cache、単一 pending を実装する |
