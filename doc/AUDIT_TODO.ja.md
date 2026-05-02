# spec-grag 監査 TODO

> 作成日: 2026-05-01
> 目的: Phase 9 後の設計充足、production 経路、E2E、GRAG 品質、障害系を通常開発 TODO から分離して追跡する。

本書は `doc/TODO.md` の肥大化を避けるための監査専用 TODO である。通常の実装作業順は `doc/TODO.md`、外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md` を正とする。

Phase 10〜13 で、watcher / readiness gate、stage timings、artifact transaction、production query path hardening、stable identity migration を実施した。これは監査で見えていた大きな既知リスクの一部を潰した状態であり、監査完了を意味しない。本書の主目的は引き続き、外部設計・内部設計・実装・test・artifact の対応を横断し、`MISSING` / `PARTIAL` / `DRIFT` / `RISK` を発見して本番運用前に潰すことである。

Ph10〜13 の実装は、今後の監査における現在のベースラインとして扱う。特に次は「実装済みだが監査対象」である。

- Phase 10: runtime mode、watcher、readiness gate、Concept diff 単一 pending、queued change、provisional concept cache、Conflict approval state
- Phase 11: `timing_summary` / `stage_timings` による stage 別性能診断
- Phase 12: query path read-only 化、artifact staging / commit、bounded graph traversal、retrieval index、BM25 postings、classification cache、run artifact privacy hardening
- Phase 13: `stable_section_uid` / `stable_chunk_uid` を内部参照軸にした stable identity migration

残る監査は、production self-run の latency / token / cost 実測だけではない。契約充足、設計 drift、GraphRAG 品質、障害復旧、security / privacy、実 provider schema / timeout、古い smoke / fallback 到達性を引き続き確認する。

## 記録形式

- 状態: `[ ]` 未着手、`[x]` 完了、`[~]` 実行中、`[!]` 要修正、`[-]` 対象外
- 判定: `OK` / `MISSING` / `PARTIAL` / `DRIFT` / `RISK` / `BLOCKED`
- 証跡: test 名、command、artifact path、該当 file / line、run id を残す
- production 到達性: 単なる文字列存在ではなく、production config から到達可能かで判定する
- 実装済み Phase の項目も、設計・test・artifact の証跡が揃うまでは `OK` としない

## 推奨順

1. Contract / design drift 監査: `EXTERNAL_DESIGN` / `DESIGN` / 実装 / test / artifact の対応表を埋め、未実装・ズレを先に洗う
2. Preflight 監査: LLM 消費なし、または小さい probe で設定・契約の大穴を潰す
3. Production readiness 静的監査: smoke / fallback / privacy / artifact transaction / stable identity の production 到達性を見る
4. Real provider 小規模 probe: Codex / Claude / Ollama の実機 schema / latency / token を確認する
5. Full GRAG build: `spec-core --all` を production config で実行する
6. E2E / GRAG 品質監査: build 済み graph を使って injection / realign / retrieval 品質を見る
7. Failure / recovery 監査: 壊れた sidecar、metadata mismatch、pending state、provider failure、staging failure を見る

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
- artifact 方針: heavy core path は staging / commit 方式。`artifact_revision.json` と `retrieval_index.json` を production artifact に含める
- retrieval 方針: BM25 postings、retrieval index、bounded graph traversal、graph path metadata を利用する
- identity 方針: 内部 retrieval / provenance は `stable_section_uid` / `stable_chunk_uid` を優先し、`section_id` / `chunk_id` は alias / citation / debug 互換として残す
- diagnostics 方針: run artifact は `timing_summary` / `stage_timings` を持ち、`include_request` / `include_response` は既定 false

## 直近監査メモ（2026-05-02）

- production config validation:
  - `.spec-grag/config.toml`、`templates/.spec-grag/config.toml`、`spec_grag/templates/.spec-grag/config.toml` は `validate_project_config(..., smoke=False)` を通過
  - `_runtime_mode = production`、`run.include_request = false`、`run.include_response = false`、`answer.failure_fallback = failed`、`classification.fallback_on_error = false`、`concept_diff.fallback_on_error = false`
  - repo-local extraction は `provider = codex`、`model = gpt-5.4-mini`、`effort = low`、`batch_size = 6`、`batch_max_chars = 4000`、`section_max_heading_level = 4`
- readiness gate:
  - `status = stale`
  - `dirty_count = 0`、`format_only_count = 0`、`queued_count = 0`、pending Concept / Conflict なし、watcher `idle`
  - stale reason は `artifact_missing`
- active `.spec-grag/graph` artifact:
  - `source_manifest.json`、`document_chunks.json`、`chunk_vector_index.json`、`bm25_index.json` は存在
  - `retrieval_index.json`、`artifact_revision.json` は未生成
  - 既存 `source_manifest.json` / chunk 系 artifact には `stable_section_uid` / `stable_chunk_uid` が含まれていない
  - 結論: Ph12 / Ph13 の実装は入っているが、このリポジトリ自身の active graph は production artifact としては stale。E2E / GRAG 品質監査の前に production full build または同等の再生成が必要
- selected regression:
  - `uv run --with pytest python -m pytest tests/test_phase10_readiness.py tests/test_phase11_timings.py tests/test_phase12_hardening.py tests/test_manifest.py tests/test_phase8_hybrid_retrieval.py tests/test_prompt_injection_robustness.py tests/test_embedding_reuse.py -q`
  - `58 passed in 53.10s`
- smoke / fallback reachability:
  - `.spec-grag/config.smoke.toml` は `validate_project_config(..., smoke=False)` で production policy violation として拒否
  - code search 上、`stable_hash` / `template` / `orchestrator_rule_based` / `source_derived` / `deterministic` は smoke config、project setup の `--smoke`、production policy rejection、または disabled provider 経路として残る
  - query text match は `allow_query_text_match = runtime_mode(config) == "smoke"` のときだけ有効
- design drift candidates:
  - 修正済み: `doc/EXTERNAL_DESIGN.ja.md` の output / citation contract に `stable_section_uid` / `stable_chunk_uid` の扱いを明示
  - 修正済み: `doc/DESIGN.ja.md` §4.6 の Qdrant 将来案を `stable_chunk_uid` point id / lookup 主軸に更新
- implementation fix:
  - 修正済み: `artifact_revision.json` を readiness / no-change fast path の必須 artifact に追加
  - 証跡: active graph の欠落理由は `retrieval_index.json` / `artifact_revision.json` の両方として検出される
- production full build / approval / E2E:
  - `env -u SPEC_GRAG_SMOKE -u SPEC_GRAG_RUNTIME_MODE uv run spec-grag-slash spec-core --all --pretty`
  - 結果: exit 0、`ResultEnvelope.status = degraded`。pending 承認があるため context は未ready
  - elapsed: `/usr/bin/time` wall `1:27:56`
  - stage timings: extraction `2,748,824ms` / 70 calls / 418 sections、embedding `2,647,947ms` / 1585 nodes + 407 chunks、community `92,314ms` / 1 call、concept_diff `46,092ms` / 1 call
  - Concept diff: `diff-6bdc6ac048ad6131:hunk-1` を Codex delegated approval として accept/apply。`docs/core/concept.md` に 16 件の source-derived concepts を追加
  - Conflict candidates: `candidate-8d4f4ead616b2393`、`candidate-8efe436a0f005952`、`candidate-e847557e3aed60a4` は直接矛盾として弱いため Codex delegated approval として reject/apply。`approved_conflicts.json` は approved 0、rejected fingerprints 3
  - readiness: pending 解消後 `fresh`。dirty / queued / pending / stale reason なし。active revision `graph:09676c8bff689811af2f5038`
  - artifact check: required artifact は全て存在。source sections 418、chunks 407、`stable_section_uid` / `stable_chunk_uid` 欠落 0、retrieval relations 1296、clusters 15
  - `spec-inject`: exit 0、elapsed `0:51.04`、`status=degraded`、`context_ready=true`、`llm_calls=9`、warning `classification_incomplete`（Phase 14 前の historical / stale）
  - `spec-realign`: exit 0、elapsed `99.899s`、`status=degraded`、`context_ready=true`、`llm_calls=10`、answer 生成まで完了、warning `classification_incomplete`（Phase 14 前の historical / stale）
  - finding: production E2E は動くが、classification budget 8 件を超えて degraded になっていた。Phase 14 後の再判定では high priority skip 0 / medium incomplete 残りへ更新済み
  - Phase 14 batch 初回 `spec-inject`: exit 0、total `72,489ms`、retrieval `19,104ms`、classification `53,085ms`、classification LLM calls 4、`high_priority_skipped_count=0`
  - Phase 14 persistent cache 再実行 `spec-inject`: exit 0、total `44,670ms`、retrieval `14,124ms`、classification `30,277ms`、classification LLM calls 3、cache hit 15、`high_priority_skipped_count=0`
  - Phase 14 batch/cache 後 `spec-realign`: exit 0、total `89,423ms`、retrieval `17,615ms`、classification `28,672ms`、answer `42,844ms`、classification LLM calls 2、cache hit 19、`high_priority_skipped_count=0`
  - finding: priority / type budget により Purpose / raw source / approved Concept は優先分類される。batch classification と persistent classification cache により classification latency は 90-100秒台から 28-53秒台まで改善
  - finding: `CodexCLIAdapter` の実呼び出しに旧 `--disable general_analytics` が残っていた。修正済み: `--config analytics.enabled=false` へ変更し、`tests/test_llm_adapters.py` 14 passed
  - finding: `.spec-grag/state/` が生成されたが ignore 対象外だった。修正済み: `.spec-grag/.gitignore` / `templates/.spec-grag/.gitignore` に `state/` を追加
  - finding: `run.include_request=false` でも response payload が run artifact に保存されていた。修正済み: `[run].include_response=false` を追加し、response payload は明示 opt-in のみに変更
  - 検証: 修正後 no-change `spec-core` は exit 0 / `status=ok` / elapsed `3.814s` / semantic no-op。run artifact `.spec-grag/runs/20260502T053753.043284Z-spec-core-1ad8db71a719.json` は `request` / `response` とも未保存
  - ccusage: `ccusage-codex session --since 2026-05-02 --timezone Asia/Tokyo --offline --json` は対話側 gpt-5.5 sessions を集計するが、`codex exec --ephemeral --json` の gpt-5.4 / gpt-5.4-mini subprocess 使用量は session 別に見えていない。full build の call 数 / duration は run artifact の `stage_timings` を一次証跡とする

### 次セッション向け残監査キュー（2026-05-02）

Phase 14 後、classification は high priority skipped 0 まで改善済み。残監査は「classification だけ」ではなく、設計 drift、retrieval 品質、latency、failure diagnostics、security / privacy の順に潰す。

- [x] Phase 14 後の E2E 判定を反映する
  - 対象: C / Full Build 実施メモの `spec-inject` / `spec-realign`
  - 判定: PARTIAL。`classification.max_items=8` 起因の古い `RISK` は stale。Phase 14 後は high priority skipped 0、`classification_medium_priority_incomplete` 残りとして扱う
  - 証跡: `.spec-grag/runs/20260502T081601.899646Z-spec-inject-7b71d453395a.json`、`.spec-grag/runs/20260502T081700.397111Z-spec-inject-925565b62f5d.json`、`.spec-grag/runs/20260502T082150.417804Z-spec-realign-fd72d9ad2316.json`
- [x] medium / low priority incomplete の production policy を決める
  - 決定: production では medium / low priority incomplete も `classification_incomplete` warning と `status=degraded` を維持する。warning-only は現時点では採用しない
  - 理由: 未分類 graph / chapter / cluster は `review_required=true` として Answer に見える可能性があり、正常 `ok` 扱いにすると人間レビューの必要性が薄れるため
  - 2026-05-03 実装追補: primary budget 後に medium / low の未分類候補を最大 6 件追加分類する deferred classification を追加。production では silent rule-based fallback せず、LLM classification / cache / incomplete warning の契約を維持する
  - 注意: production では silent rule-based fallback しない
- [~] Retrieval 品質 query set を artifact evidence で評価する
  - query: `Core と Customize の境界を説明して`
  - query: `ImageUploadField / FileUploadField / ImageGalleryField の違い`
  - query: `Action signal と emit / 購読の関係`
  - query: `section_max_heading_level で ##### が親に統合される影響`
  - query: `Concept にないが Source specs にある制約の扱い`
  - 2026-05-02 初回評価: 1〜3 は degraded だが source evidence は概ね妥当。4 は一度 Classification LLM failed になったが再実行で degraded。5 は type budget が tier 0 graph entity を落として failed になったため修正済み
  - 証跡: `.spec-grag/runs/20260502T083945.272932Z-spec-inject-fbf469c867d1.json`、`.spec-grag/runs/20260502T084048.110708Z-spec-inject-278390f73f4d.json`、`.spec-grag/runs/20260502T084152.977964Z-spec-inject-6eb850708393.json`、`.spec-grag/runs/20260502T084524.948365Z-spec-inject-35959229423e.json`、`.spec-grag/runs/20260502T084927.386804Z-spec-inject-2bf9dae9cfe6.json`
  - finding: approved Concept retrieval は `Concept / Source-derived concepts` の巨大 chunk と導入文 chunk が多くの query で混じる。Source specs 側は当たっているため、Concept index chunking / top-k / query-side filtering を別途見る
  - finding: broad query では BM25 query terms が 662〜989 と多く、BM25 candidate documents が 407/407 になりやすい。query planner の語過多が sparse retrieval の識別力を落としている可能性がある
- 2026-05-03 再評価:
  - Concept index を v2 に更新し、Markdown list item を 1 concept chunk として扱うように変更。既存 v1 artifact は readiness で `concept_index_version_mismatch` stale として検出し、`spec-core` で再生成する
  - `spec-core` 再生成 artifact: `.spec-grag/runs/20260502T153505.476508Z-spec-core-f9f636203d11.json`。`concept_index` input chunks は 17、warning `concept_index_version_mismatch_rebuilt`
  - query set 初回実測: q1〜q4 は `status=degraded` だが `high_priority_skipped_count=0` / `medium_priority_skipped_count=0`、残りは `classification_low_priority_incomplete`。q5 は `status=ok`
  - artifacts: q1 `.spec-grag/runs/20260502T153643.956546Z-spec-inject-d0dc1af90348.json`、q2 `.spec-grag/runs/20260502T153802.915154Z-spec-inject-a136bb0283e4.json`、q3 `.spec-grag/runs/20260502T153926.308161Z-spec-inject-7e2c9c188bd6.json`、q4 `.spec-grag/runs/20260502T154045.389010Z-spec-inject-976fc5de966f.json`、q5 `.spec-grag/runs/20260502T154122.527438Z-spec-inject-c4b65b04c98d.json`
  - Concept 導入文 chunk は query-side filter で除外。確認 artifact: `.spec-grag/runs/20260502T154925.012827Z-spec-inject-d4ab5756ea82.json`
  - 残 finding: Source evidence は q1〜q3 は概ね妥当。q4 `section_max_heading_level` は該当語が Source specs に薄く、dense 側で周辺 section を拾う傾向が残る。BM25 candidate documents も 314〜404/407 とまだ広い
- [x] query planner latency を監査し、一次対策を入れる
  - 見るもの: no-change inject / realign の retrieval stage、query planner LLM call 数、cache 可能な QueryPlan
  - 初回 finding: query set 5本すべて retrieval stage で query planner LLM 1 call が残り、retrieval は約 10〜18 秒。no-change / warm cache でも QueryPlan cache がない
  - 2026-05-03 対応: QueryPlan persistent cache を追加。BM25 は raw query + identifiers/entities/expected areas の専用 query に分離し、dense は expanded QueryPlan query を使用。BM25 query terms は cap 80
  - 実測: q5 repeat `.spec-grag/runs/20260502T154138.492288Z-spec-inject-c57b13ce9e8a.json` は retrieval `4,722ms`、query planner LLM calls 0、`query_plan_cache_hit=true`
  - 初回 query set の BM25 terms は 378〜458 -> 80 に抑制。candidate documents はまだ 314〜404/407 のため、BM25 postings 側のさらなる絞り込みは継続監査
- [x] answer generation latency を監査し、cache / compaction を入れる
  - 見るもの: `spec-realign` の answer stage 40秒台、model / prompt / schema / NeedMoreContext policy
  - 初回 finding: `.spec-grag/runs/20260502T082150.417804Z-spec-realign-fd72d9ad2316.json` は `answer_generation` 42,843ms、answer LLM 1 call。classification cache 後は answer が最大 latency 成分
  - 2026-05-03 対応: Answer prompt 用 InjectionContext compaction と Answer persistent cache を追加。cache key は task prompt、compact context、provider/model/prompt policy で構成し、`classification_cache_hit` や freshness timestamp は除外する
  - 実測: cache miss `.spec-grag/runs/20260502T154645.565178Z-spec-realign-d0c0cfd9dbbf.json` は answer `38,386ms` / LLM 1 call / `answer_context_compacted=true`
  - 実測: cache hit `.spec-grag/runs/20260502T154702.759380Z-spec-realign-5aaef0f12cff.json` は answer `2.886ms` / LLM 0 call / `answer_cache_hit=true`、wall `7.99s`
  - 検証: `uv run --with pytest python -m pytest -q` -> `240 passed in 211.84s`
- [x] Claude architecture audit 指摘の current HEAD 突き合わせ（2026-05-03）
  - stale / 修正済み: Concept巨大chunk、BM25 query planner語過多、QueryPlan cache、Answer cache、deferred classification は `b4eebdb` で一次対応済み
  - 設計上維持: Concept reject は外部設計どおり未解決として残し、次回も確認要求する。accepted / rejected の pending Conflict も apply で approved sidecar / rejected fingerprint に反映されるまでは gate で止める
  - 追加対応: chunk / vector / BM25 lookup dict の repeated rebuild を cached lookup に変更。community report LLM prompt に untrusted data 境界を追加
  - 検証: `uv run --with pytest python -m pytest -q` -> `242 passed in 231.45s`
  - Phase 15 計画: 正当で現在も残る指摘は `doc/PHASE15_PLAN.ja.md` に実装順として整理済み
  - 継続課題: `injection.py` / `core.py` 分割、atomic write / LLM factory 共通化、logging 導入、tests/conftest.py 整理、dense search の短期高速化 / Qdrant 将来検討、safe_delete_by_sections batch 化、watcher / foreground lock 方針確認
- [ ] Phase 15 architecture audit hardening を進める
  - 計画: `doc/PHASE15_PLAN.ja.md`
  - 先行順: atomic write 共通化、LLM factory 共通化、priority constants、safe_delete_by_sections、logging diagnostics、`injection.py` concern 分割
  - 非対象: Concept reject を解決済みにする変更、apply 前 pending を gate から外す変更、protocol-breaking ContextItem model 化、Qdrant 移行
- [ ] Contract / design drift matrix を埋める
  - 対象: `EXTERNAL_DESIGN` / `DESIGN` / implementation / test / production artifact
  - まず `PARTIAL` を `OK` / `DRIFT` に確定する
- [ ] Failure / recovery と artifact lifecycle を確認する
  - 対象: failed staging diagnostics、old smoke artifact から production artifact への再生成、stable ID 導入後 incremental alias 混入
- [ ] Security / privacy / production reachability を再確認する
  - 対象: mock / fake provider 到達性、query path read-only 全 entrypoint、run artifact request/response opt-in、prompt untrusted boundary

## 0. Preflight 監査

- [x] `.spec-grag/config.toml` が production policy を通る
  - 判定: OK
  - 証跡: `validate_project_config(..., smoke=False)` -> `_runtime_mode = production`
  - 2026-05-02 再確認: repo-local / template / package template の 3 config すべて OK
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
- [x] Phase 13 後の full regression が通る
  - 判定: OK
  - 証跡: `uv run --with pytest python -m pytest` -> `222 passed in 194.04s (0:03:14)`

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
| Answer 入力境界 | task_prompt + InjectionContext のみ | `spec_grag/realign.py` | `tests/test_realign_answer.py` / `tests/test_prompt_injection_robustness.py` | PARTIAL | 実 provider E2E で追加確認 |
| Source evidence | stable/current section、source_span、source_hash、stable_chunk_uid を保持 | `spec_grag/chunk_index.py` / `spec_grag/injection.py` | `tests/test_phase8_hybrid_retrieval.py` / `tests/test_manifest.py` | PARTIAL | active graph は stable UID 未生成。production graph artifact で追跡確認が必要 |
| section 化規約 | `section_max_heading_level` 超過を親へ統合し、stable section を維持する | `spec_grag/manifest.py` | `tests/test_manifest.py` | PARTIAL | split / merge / duplicate の監査継続 |
| Concept apply hash | base hash mismatch で blocked |  |  |  |  |
| NeedMoreContext | 情報不足時は blocked |  |  |  |  |
| ReviewNotes | 不確実性・未承認候補を隠さない |  |  |  |  |
| query path read-only | production inject / realign は暗黙 core update をしない | `spec_grag/cli.py` / `spec_grag/injection.py` | `tests/test_phase12_hardening.py` | OK | local daily / production は readiness gate |
| artifact transaction | heavy core path は staging commit で active artifact を壊さない | `spec_grag/core.py` | `tests/test_phase12_hardening.py` | OK | fast path は atomic file write |
| graph expansion hops | `retrieval.graph_expansion_hops` に従う bounded traversal | `spec_grag/injection.py` | `tests/test_phase12_hardening.py` | OK | 実 retrieval 品質は D で評価 |
| classification budget | production budget 超過で silent rule fallback しない | `spec_grag/injection.py` | `tests/test_phase9_production_policy.py` / `tests/test_phase12_hardening.py` | OK | `classification_incomplete` |
| stable identity | rename / edit で stable section / chunk key を維持する | `spec_grag/manifest.py` / `spec_grag/chunk_index.py` | `tests/test_manifest.py` / `tests/test_phase8_hybrid_retrieval.py` | OK | split / merge は安全側 |
| run artifact privacy | request / response 保存は既定 off、redaction 可能 | `spec_grag/run_artifacts.py` / `spec_grag/config.py` | `tests/test_cli.py` | OK | `include_response=false` を追加 |

重点 TODO:

- [ ] `doc/EXTERNAL_DESIGN.ja.md` の各節に contract id を付与するか検討
- [ ] `doc/DESIGN.ja.md` の内部契約と実装 file / test の対応を埋める
- [ ] `MISSING` / `PARTIAL` / `DRIFT` を issue 化できる粒度に分割する
- [ ] Phase 10〜13 で追加した契約が `EXTERNAL_DESIGN` / `DESIGN` / config template / tests に全て同期されているか確認する
- [ ] 旧挙動の記述が README / HANDOFF / SURVEY / command template に残っていないか確認する
- [ ] `PARTIAL` の項目を production artifact 実測で `OK` / `DRIFT` に確定する

### A-2. Contract / Design Drift Audit TODO

設計ズレ洗い出しを監査の第一目的として扱う。Ph10〜13 の実装済み項目も、設計・実装・test・artifact の対応が取れるまで監査完了にしない。

- [ ] `doc/EXTERNAL_DESIGN.ja.md` の見出し単位で contract matrix を作る
  - 期待: 各契約に implementation file、test、run artifact evidence、判定を付ける
- [ ] `doc/DESIGN.ja.md` の schema / sidecar / state machine と実装 model を照合する
  - 対象: `SourceManifest`、`DocumentChunksSidecar`、`RetrievalIndex`、`watch_state`、`watch_queue`、`provisional_concept_cache`、`pending_conflict_review`、`artifact_revision`
- [ ] command surface と外部設計を照合する
  - 対象: `/spec-core`、`/spec-inject`、`/spec-realign`、`spec-grag-watch`、approval transport、legacy wrapper flags
- [ ] runtime mode ごとの契約を state transition と test で確認する
  - 対象: `local_daily`、`ci`、`production`、smoke 明示モード
- [ ] Concept / Conflict approval の人間確認 UX と内部 state transition が一致しているか確認する
  - 対象: accept / reject / defer / revise / apply、base hash mismatch、queued change 再評価
- [ ] stable identity の契約と実装のズレを確認する
  - 対象: rename、move、body edit、split、merge、duplicate body、old artifact regeneration
  - 2026-05-02 fixed: `doc/EXTERNAL_DESIGN.ja.md` の output / citation contract に `stable_section_uid` / `stable_chunk_uid` を明示
  - 2026-05-02 fixed: `doc/DESIGN.ja.md` §4.6 の Qdrant 将来案を `stable_chunk_uid` 主軸へ修正
- [ ] query path read-only 契約を全 entrypoint で確認する
  - 対象: CLI、low-level API、watcher、tests/helper 経路
- [ ] production privacy 契約を確認する
  - 対象: prompt untrusted boundary、run artifact redaction、`include_request=false`、source本文 / prompt本文 / LLM応答本文の保存有無

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
| token-match 主導 retrieval | 到達不可 | smoke / deterministic helper 限定 | code search: `allow_query_text_match = runtime_mode(config) == "smoke"` | OK | GRAG 品質は実 query set で別評価 |
| query-time core update | 到達不可 | watcher / foreground core のみ | `tests/test_phase12_hardening.py` | OK | low-level `build_injection()` も read-only default |
| request/response artifact 保存 | production default では保存しない | 明示 opt-in + redaction | `tests/test_cli.py` | OK | `.spec-grag/config.toml` は `include_request=false` / `include_response=false` |
| artifact partial commit | 到達不可 | staging commit 成功時のみ active 更新 | `tests/test_phase12_hardening.py` | OK | no-change fast path は atomic write |
| classification silent fallback | 到達不可 | `classification_incomplete` と degraded | `tests/test_phase9_production_policy.py` | OK | budget 超過時 |

重点 TODO:

- [x] production config からの provider resolution を表にする
  - 判定: OK
  - 証跡: repo-local / template / package template とも `extraction=codex:gpt-5.4-mini`、`embedding=ollama:bge-m3`、`answer=codex:gpt-5.4`、`classification=codex:gpt-5.4`、`concept_diff=codex:gpt-5.4`
- [x] fallback event が provider config から出ないことを確認
  - 判定: OK
  - 証跡: `fallback_events = []`
- [x] smoke config が production mode で拒否されることを確認
  - 判定: OK
  - 証跡: `.spec-grag/config.smoke.toml` -> `ConfigPolicyError`
- [x] production config の `run.include_request=false` / `run.include_response=false` と redaction 方針を実 config / template / artifact で確認する
  - 判定: OK
  - 証跡: repo-local / template / package template は `include_request=false`、`include_response=false`
  - finding: 2026-05-02 production self-run artifact は修正前のため response payload を含んでいた
  - 修正: `include_response=false` を追加し、response payload は明示 opt-in のみ。redaction test 追加
- [x] static trace で `stable_hash` / `template` / rule fallback が production command から到達不可であることを再確認する
  - 判定: PARTIAL
  - 証跡: `rg "stable_hash|template|orchestrator_rule_based|source_derived|deterministic|fallback_on_error|failure_fallback|query_tokens|token_match_score|mock|fake|smoke" spec_grag .spec-grag templates spec_grag/templates`
  - 確認: smoke-only provider は production policy で拒否、または `--smoke` / disabled provider / explicit smoke runtime に閉じている
  - 残課題: `mock` provider の production 到達性は別項目として継続確認

## C. E2E Scenario Matrix

full build 後に実行する。

| シナリオ | command | 期待 | artifact / 証跡 | 判定 | 備考 |
|---|---|---|---|---|---|
| production full core | `spec-core --all` | `ok`、fallback なし | `2026-05-02T052250Z` run / wall `1:27:56` | PARTIAL | pending Concept / Conflict により `degraded`。承認後 readiness fresh |
| no-change incremental | `spec-core` | no-change / ok |  |  |  |
| injection | `spec-inject` | InjectionContext | `2026-05-02T081700Z` run / wall `44.670s` | PARTIAL | Phase 14 後は high priority skipped 0。`classification_medium_priority_incomplete` で degraded |
| realign | `spec-realign` | RealignResult または NeedMoreContext | `2026-05-02T082150Z` run / wall `89.423s` | PARTIAL | answer 生成完了。high priority skipped 0、`classification_medium_priority_incomplete` で degraded |
| pending Concept block | pending diff 作成後 `spec-inject` | blocked |  |  |  |
| Concept accept/reject/revise/apply | `options.approval` | state 遷移 OK | `tests/test_cli.py` | OK | legacy wrapper flags は内部互換 |
| hash mismatch | stale pending diff apply | blocked |  |  |  |
| Answer NeedMoreContext | LLM が needs_more_context | blocked |  |  |  |
| ConflictNotes / ReviewNotes | conflict / review evidence | Answer で明示 | `spec-realign` answer / InjectionContext | PARTIAL | Validator conflict / unresolved relation review は出る。品質妥当性は継続監査 |
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
| raw chunk retrieval | Scoped Store / Action runtime | source excerpt が取れる | `spec-inject` evidence | OK | `stable_chunk_uid` / span / hash 付き excerpt を確認 |
| dense retrieval | Scoped Store / Action runtime | 日本語 semantic hit | `spec-inject` evidence | PARTIAL | dense hits 8。品質評価セットは未整備 |
| BM25 sparse retrieval | Scoped Store / Action runtime | postings list 経由で固有名詞 / API 名 hit | `tests/test_phase8_hybrid_retrieval.py` / `spec-inject` | PARTIAL | BM25 candidate documents 405/407。query planner の語過多を継続確認 |
| RRF rank fusion | Scoped Store / Action runtime | dense + sparse + graph が統合 | `spec-inject` evidence | PARTIAL | retrieval_methods に `rank_fusion` を確認 |
| graph expansion |  | bounded traversal で relation path / hop / evidence が出る | `tests/test_phase12_hardening.py` | PARTIAL | 実 query set で品質評価 |
| QueryPlan |  | 検索語・章候補・曖昧性を出す |  |  |  |
| ChapterAnchor |  | InjectionContext に反映 |  |  |  |
| cluster / community |  | 関連 cluster が出る |  |  |  |
| evidence traceability | Scoped Store / Action runtime | stable_chunk_uid / current section / source_span / source_hash が追跡可能 | `tests/test_phase8_hybrid_retrieval.py` / `tests/test_manifest.py` / production artifact | OK | manifest/chunks stable UID 欠落 0 |
| unresolved relation |  | graph に入らず ReviewNotes / sidecar |  |  |  |
| retrieval index | Scoped Store / Action runtime | section/chunk/node/relation の逆引きを query path が使う | `tests/test_phase12_hardening.py` / production artifact | OK | `retrieval_index.json` generated、relations 1296 |
| stable identity retrieval |  | heading rename / body edit 後も stable key で検索単位を維持 | `tests/test_manifest.py` / `tests/test_phase8_hybrid_retrieval.py` | PARTIAL | full rebuild artifact で確認 |

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
| core update failure before commit | active artifact を維持し failed revision を記録 | `tests/test_phase12_hardening.py` | OK | staging commit |
| watcher running / queued change | local daily は blocked、production は fail-fast | `tests/test_phase10_readiness.py` | OK | single worker + queue drain |
| stable ID duplicate / split / merge | 誤継承せず安全側で added / removed / changed | `tests/test_manifest.py` | OK | Phase 13 |

## F. Sidecar & Artifact Lifecycle Tests

| artifact | 作成 | 更新 | stale / dirty | corruption recovery | 判定 |
|---|---|---|---|---|---|
| `source_manifest.json` | 作成済み | raw / semantic hash と stable section 更新 | readiness dirty / stale 判定 | 再生成 | OK |
| graph store | 作成済み | staging commit | revision mismatch で stale | active維持 | PARTIAL |
| vector store | 作成済み | stable entity text hash で再利用 | embedding metadata mismatch で stale | 再生成 | PARTIAL |
| `document_chunks.json` | 作成済み | stable chunk lookup を更新 | stale chunk を削除 | 再生成 | OK |
| `chunk_vector_index.json` | 作成済み | stable_chunk_uid 主軸で再利用 | embedding metadata mismatch で stale | 再生成 | OK |
| `bm25_index.json` | 作成済み | postings を更新 | graph revision mismatch を検出 | 再生成 | OK |
| `retrieval_index.json` | 逆引き index を作成 | stable section / chunk lookup を更新 | readiness missing / stale を検出 | 再生成 | OK |
| `artifact_revision.json` | commit marker を作成 | active revision を更新 | readiness missing / diagnostics に出す | failed revision を記録 | OK |
| `unresolved_relations.json` | 作成済み | unresolved のみ sidecar | ReviewNotes へ反映 | 再生成 | PARTIAL |
| `chapter_anchors.json` | 作成済み | chapter 単位更新 | graph revision mismatch | 再生成 | PARTIAL |
| `cluster_snapshot.json` | 作成済み | community report 更新 | graph revision mismatch | 再生成 | PARTIAL |
| `concept_index.json` | 作成済み | Concept apply 時に更新 | concept hash mismatch | 再生成 | PARTIAL |
| run artifacts | run artifact / execution diagnostics に timing_summary / stage_timings を保存し、blocked / failed でも完了済み timings を残す | `spec_grag/timing.py`, `spec_grag/run_artifacts.py`, `spec_grag/cli.py` | `tests/test_phase11_timings.py` | OK | token usage は provider から安定取得できる場合に追加 |

重点 TODO:

- [x] `artifact_revision.json`、`retrieval_index.json`、stable UID fields が production full build artifact に実在することを確認する
  - 2026-05-02 finding: active `.spec-grag/graph` では `retrieval_index.json` / `artifact_revision.json` が missing。既存 manifest / chunk artifacts も stable UID fields なし
  - 2026-05-02 fixed: readiness の missing artifact 判定と no-change fast path の必須 artifact 判定に `artifact_revision.json` を追加
  - 2026-05-02 verified: production full build 後、required artifact は全て存在。manifest 418 entries / chunks 407 / stable UID 欠落 0 / retrieval relations 1296 / clusters 15
- [ ] failed staging の残骸と failed revision diagnostics が運用上読める形になっているか確認する
- [ ] old smoke artifact から production artifact への再生成手順を確認する
- [ ] stable ID 導入後の incremental rebuild で古い alias が混入しないことを確認する

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
- [x] generated artifacts
  - 判定: OK
  - 証跡: Phase 12 で heavy core path は `.spec-grag/.staging/<graph>/<revision>/` への書き込み後に active graph directory へ commit する方式へ変更
  - 証跡: `artifact_revision.json` と `retrieval_index.json` を必須 artifact に追加
  - 検証: `tests/test_phase12_hardening.py::test_core_update_failure_keeps_active_artifacts`
  - 残課題: production self-run artifact で active / staging / failed revision diagnostics を再確認する
- [x] unresolved relation 件数
  - 証跡: `unresolved_relations.json` 更新済み、size `32776` bytes
- [x] Concept diff pending 有無
  - 1回目 `spec-core --all`: `pending_concept_diff_id = null`

### 2026-05-02 production full build 再実行

- [x] `spec-core --all` を Ph13 後の production config で実行
  - command: `/usr/bin/time -v env -u SPEC_GRAG_SMOKE -u SPEC_GRAG_RUNTIME_MODE uv run spec-grag-slash spec-core --all --pretty`
  - result: exit 0、`ResultEnvelope.status = degraded`
  - degraded reason: Concept diff / Conflict candidate の pending 承認。fallback ではない
  - `/usr/bin/time`: wall `1:27:56`、max RSS `479344KB`
  - `timing_summary`: total `5,547,441ms`、llm calls `72`、LLM total `2,887,231ms`、embedding total `2,647,948ms`、community total `92,314ms`
  - `schema_llm_extraction`: provider `codex`、model `gpt-5.4-mini`、70 calls、418 sections、failed 0
  - `embedding_update`: provider `ollama`、model `bge-m3`、dim 1024、1585 nodes、407 chunks
  - `community_report`: provider `codex`、model `gpt-5.4`、1 call、cluster_count 15
  - `concept_diff`: provider `codex`、model `gpt-5.4`、1 call、pending_created true
  - run artifact: `.spec-grag/runs/20260502T052250.886165Z-spec-core-064eee23ecc9.json`
- [x] delegated approval を記録
  - Concept: `diff-6bdc6ac048ad6131:hunk-1` を accept/apply。理由: source span 付きで、安定語彙・原則として採用可能
  - Conflict: 3 candidates を reject/apply。理由: 直接矛盾としては弱く、問題一覧や optional props に対する rule string false positive
  - approved conflicts: 0、rejected fingerprints: 3
- [x] full build 後 readiness
  - result: `fresh`
  - dirty / format-only / queued / pending Concept / pending Conflict / stale reasons: all empty
  - active revision: `graph:09676c8bff689811af2f5038`
- [x] production artifact inspection
  - required artifact: all present
  - source manifest: 418 entries、`stable_section_uid` 欠落 0
  - document chunks: 407 chunks、`stable_chunk_uid` 欠落 0
  - retrieval index: relations 1296
  - cluster snapshot: clusters 15
- [x] historical production E2E `spec-inject`（Phase 14 前 / stale RISK）
  - command: `spec-inject --message 'Scoped Store と Action runtime の設計上の制約を確認したい'`
  - result: exit 0、`status=degraded`、`context_ready=true`
  - elapsed: `0:51.04`
  - timing: total `51,227ms`、llm calls 9、retrieval `50,706ms`、classification `291ms`
  - finding: `classification_budget = 8`、skipped 17、warning `classification_incomplete`。Phase 14 後の priority / budget policy により stale
  - run artifact: `.spec-grag/runs/20260502T052715.932938Z-spec-inject-856ed762e012.json`
- [~] Phase 14 production E2E `spec-inject`
  - command: `spec-inject --message 'Scoped Store と Action runtime の設計上の制約を確認したい'`
  - result: exit 0、`status=degraded`、`context_ready=true`
  - timing: total `108,385ms`、llm calls 21、retrieval `15,664ms`、classification `92,464ms`
  - finding: `classification_budget = 20`、candidate 38、classified 20、skipped 18、`high_priority_skipped_count = 0`
  - skipped distribution: graph entity 8、chapter anchor 4、cluster 6。raw source 12、Purpose 1、Concept 2 は classified
  - warning: `classification_incomplete` / `classification_medium_priority_incomplete`
  - run artifact: `.spec-grag/runs/20260502T075818.783343Z-spec-inject-7e81989e392a.json`
- [~] Phase 14 batch/cache production E2E `spec-inject`
  - command: `spec-inject --message 'Scoped Store と Action runtime の設計上の制約を確認したい'`
  - first batch result: total `72,489ms`、llm calls 5、retrieval `19,104ms`、classification `53,085ms`、classification LLM calls 4、cache hit 0
  - persistent cache rerun: total `44,670ms`、llm calls 4、retrieval `14,124ms`、classification `30,277ms`、classification LLM calls 3、cache hit 15
  - finding: `high_priority_skipped_count = 0`、warning `classification_medium_priority_incomplete`
  - run artifacts: `.spec-grag/runs/20260502T081601.899646Z-spec-inject-7b71d453395a.json` / `.spec-grag/runs/20260502T081700.397111Z-spec-inject-925565b62f5d.json`
- [x] historical production E2E `spec-realign`（Phase 14 前 / stale RISK）
  - command: `spec-realign --task-prompt 'Scoped Store と Action runtime の設計上の制約を、根拠付きで簡潔に整理して'`
  - result: exit 0、`status=degraded`、`context_ready=true`、answer 生成完了
  - elapsed: `99.899s`
  - timing: total `96,519ms`、llm calls 10、retrieval `49,685ms`、classification `367ms`、answer `46,203ms`
  - finding: `classification_budget = 8`、skipped 19、warning `classification_incomplete`。Phase 14 後の priority / budget policy により stale
  - run artifact: `.spec-grag/runs/20260502T052918.646928Z-spec-realign-3612623ba40e.json`
- [~] Phase 14 production E2E `spec-realign`
  - command: `spec-realign --task-prompt 'Scoped Store と Action runtime の設計上の制約を、根拠付きで簡潔に整理して'`
  - result: exit 0、`status=degraded`、`context_ready=true`、answer 生成完了
  - timing: total `160,713ms`、llm calls 22、retrieval `19,290ms`、classification `99,452ms`、answer `41,728ms`
  - finding: `classification_budget = 20`、candidate 40、classified 20、skipped 20、`high_priority_skipped_count = 0`
  - skipped distribution: graph entity 8、chapter anchor 5、cluster 7。raw source 12、Purpose 1、Concept 2 は classified
  - warning: `classification_incomplete` / `classification_medium_priority_incomplete`
  - run artifact: `.spec-grag/runs/20260502T080058.085853Z-spec-realign-32aa47a12a59.json`
- [~] Phase 14 batch/cache production E2E `spec-realign`
  - command: `spec-realign --task-prompt 'Scoped Store と Action runtime の設計上の制約を、根拠付きで簡潔に整理して'`
  - result: exit 0、`status=degraded`、`context_ready=true`、answer 生成完了
  - timing: total `89,423ms`、llm calls 4、retrieval `17,615ms`、classification `28,672ms`、answer `42,844ms`
  - finding: classification LLM calls 2、cache hit 19、`high_priority_skipped_count = 0`
  - warning: `classification_incomplete` / `classification_medium_priority_incomplete`
  - run artifact: `.spec-grag/runs/20260502T082150.417804Z-spec-realign-fd72d9ad2316.json`
- [x] 2026-05-02 retrieval query set 初回監査
  - result: `Core と Customize の境界`、`ImageUploadField / FileUploadField / ImageGalleryField`、`Action signal と emit / 購読` は degraded / context_ready true。Source evidence は概ね妥当
  - result: `section_max_heading_level で ##### が親に統合される影響` は一度 Classification LLM failed、再実行では degraded / context_ready true。provider transient として継続監視
  - finding: `Concept にないが Source specs にある制約の扱い` で type budget が tier 0 graph entity を落とし、`classification_high_priority_incomplete` / failed になった
  - 修正: tier 0 candidate は type budget を迂回し、global `max_items` のみで制限する。再実行 `.spec-grag/runs/20260502T084927.386804Z-spec-inject-2bf9dae9cfe6.json` は `status=degraded`、`high_priority_skipped_count=0`、`medium_priority_skipped_count=4`
  - 修正: classification warning だけの場合に `degraded_components` が `retrieval` を含まないように attribution を修正。再実行 artifact では `degraded_components=['classification']`

実装修正:

- [x] classification type budget が high priority candidate を落とさないようにする
  - 修正: `select_classification_candidates()` で type budget は tier > 0 にのみ適用
  - 検証: `tests/test_phase12_hardening.py::test_high_priority_classification_candidates_bypass_type_budget` 追加
  - 検証: `uv run --with pytest python -m pytest -q` -> `229 passed in 187.76s`
- [x] Codex CLI prompt を argv ではなく stdin で渡す
  - 修正: `CodexCLIAdapter` は `codex exec -` + `stdin_text=prompt` を使う
  - 検証: `uv run --with pytest pytest tests/test_llm_adapters.py -q` -> `14 passed`
- [x] chunk / graph vector embedding を incremental で再利用する
  - 修正: Phase 13 前は `chunk_id + chunk_hash + embedding metadata` 一致時に `chunk_vector_index.json` の embedding を再利用していた
  - 修正: Phase 13 後は `stable_chunk_uid + chunk_hash + embedding metadata` を主軸にし、`chunk_id` は互換 alias として扱う
  - 修正: `node_id + source_hash / entity_text_hash + embedding metadata` 一致時に `vector_store.json` の embedding を再利用する
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
| 2026-05-02 | Phase 10 watcher / readiness gate | OK。local daily / CI / production の runtime mode、watcher queue、単一 pending、provisional cache、Conflict approval state を regression 化 | OS native watcher / daemon 管理は範囲外 | contract drift audit で外部設計との対応を確認 |
| 2026-05-02 | Phase 11 stage timings | OK。run artifact に `timing_summary` / `stage_timings` を保存し、blocked / failed でも完了済み stage を残す | token usage は provider 依存 | production self-run で latency 比率を記録 |
| 2026-05-02 | Phase 12 hardening | OK。query path read-only、artifact staging commit、bounded graph traversal、retrieval index、BM25 postings、classification cache、privacy default を実装 | external ANN / vector DB は将来対応 | production full build artifact で実確認 |
| 2026-05-02 | Phase 13 stable identity | OK。stable section / chunk UID を内部参照軸にし、rename / edit / chunk ordinal 継続を regression 化 | 古い artifact の厚い migration は範囲外 | stable ID が production artifact と retrieval result に出ることを監査 |
| 2026-05-02 | 監査再開: config / readiness / active artifact / selected regression | PARTIAL。production config は repo-local / template / package template 全て valid、readiness は dirty/pending なしだが `artifact_missing` で stale、selected regression 58 passed | active graph に `retrieval_index.json` / `artifact_revision.json` / stable UID fields がない | production full build を実施するか、先に stable identity の設計 drift を修正してから full build |
| 2026-05-02 | 監査 finding 修正 | OK/PARTIAL。EXTERNAL_DESIGN の stable UID output contract、DESIGN の Qdrant stable key 方針、artifact_revision 必須判定を修正。targeted regression 47 passed | active graph artifact 自体は未再生成 | production full build で active graph を更新し、E2E / GRAG 品質監査へ進む |
| 2026-05-02 | production full build 再実行 | PARTIAL。`spec-core --all` は exit 0 / wall 1:27:56。Concept diff は delegated accept/apply、Conflict 3件は delegated reject/apply。readiness は fresh、required artifact と stable UID は確認済み | build 自体は完了。E2E が `classification_incomplete` で degraded | classification budget / query planner latency / retrieval quality を重点監査 |
| 2026-05-02 | production inject / realign E2E | HISTORICAL/RISK。`spec-inject` 51.04s、`spec-realign` 99.899s。どちらも `context_ready=true` だが `classification_incomplete` で degraded | classification budget 8 件で source / concept / chapter / cluster の一部が未分類。Phase 14 後は stale | budget設定、優先順位、分類cache粒度、degraded時のanswer policyを確認 |
| 2026-05-02 | Phase 14 classification priority / budget policy | OK/PARTIAL。候補収集、classification key dedup、priority sort、type budget、batch classification、persistent cache、priority-aware warning/fail、stage metrics を実装。self E2E は high priority skipped 0 | `classification_medium_priority_incomplete` は残る。retrieval query planner / answer latency も残課題 | query planner cache、answer latency、medium/low deferred policy を次に検討 |
| 2026-05-02 | 監査 finding 修正 2 | OK。Codex CLI analytics抑止を `--config analytics.enabled=false` に修正、`.spec-grag/state/` を ignore 化、run artifact response payload を `include_response=false` 既定に変更。`tests/test_llm_adapters.py` 14 passed | なし | full targeted regression と diff check |
| 2026-05-02 | 修正後 no-change / privacy 確認 | OK。`spec-core` no-change は 3.814s、`status=ok`、semantic no-op。run artifact は request / response payload を保存しない | なし | 残りは classification degraded と retrieval品質監査 |
| 2026-05-02 | retrieval query set / type budget 監査 | OK/PARTIAL。5 query の初回評価で Source evidence は概ね妥当。`Concept にないが Source specs にある制約` で tier 0 graph entity が type budget で落ちる不具合を修正し、再実行で high priority skipped 0 | medium incomplete は degraded 維持。Concept 巨大 chunk 混入、query planner 語過多、answer 40秒台は残る | 当時は QueryPlan cache / Concept chunking / deferred classification を検討。2026-05-03 追補で一次対策済み |
