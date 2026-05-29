# SpecClaim 経路移行 — 実機検証と recall 比較記録

## 目的

`doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` で確定した SpecClaim 経路 (SpecClaim 抽出 + Claim Retrieval + LLM triage) が、旧 `possible_conflict` 経路で検出されていた conflict を **欠落なく拾えることを実機で確認**し、Phase 5 (`possible_conflict` 経路の完全削除) 着手判断の根拠データを残す。

本ファイルは `doc/TODO.ja.md` T-spec-claim-phase-4 (検証条件 B / C) の成果物。

## Phase 4 完了時点 (2026-05-29) の実機検証

### 環境

- 実行 revision: HEAD = `9529e07 docs(internal): record LLM triage Phase 3 完了 evidence (Part C)`
- LLM provider: 実 Codex CLI (`gpt-5.4-mini`, `effort = low`, `[llm.stage_routing].section_metadata = "codex"`, 他は `[llm.providers]` 先頭 default)
- LLM triage provider: 実 Codex CLI (`gpt-5.4-mini`, `low`、`[llm.stage_routing].conflict_candidate_triage` 未指定 → providers 先頭 default)
- Qdrant: `localhost:6333`, `spec_anchor_section` + `spec_anchor_claim` collection
- Embedding: FlagEmbedding BGE-M3 (dense + sparse)
- Source Specs: `docs/spec/sample.md` (5 sections + intro = 6 section)
- Purpose / Core Concept: `docs/core/purpose.md` / `docs/core/concept.md`
- 設定: 既定の `[conflict_candidate_detection]` (`triage_max_pairs = 30`, `per_claim_top_k = 10`, etc)
- production config に `legacy_possible_conflict_mode` 等の legacy key は **未追加**

### 既知 conflict (intent)

`docs/spec/sample.md` に意図的に埋め込まれた conflict pair:

- §0004 Session Termination: `Sessions that exceed the 24-hour inactivity window are automatically purged by a background sweep that runs every five minutes.`
- §0005 Session Retention Policy: `For compliance and audit purposes, all session records must be retained and kept active for a minimum of 30 days regardless of inactivity. Sessions must not be terminated before the 30-day retention window has elapsed.`

矛盾: 24 時間で session purge vs 30 日間保持必須。

### 実機実行結果

`python3 -m spec_anchor core` を state クリア後に実行:

| stage | status | LLM calls | 詳細 |
|---|---|---|---|
| `spec_claims` | `skipped_unchanged` | 0 | 前回 (Phase 3 Part C) state を再利用、14 SpecClaim 保持 |
| `claim_retrieval` | `success` | 0 (LLM 非使用) | Qdrant に 14 claim upsert、search 42、45 candidate pairs 生成 (27 件 truncate) |
| `conflict_candidate_triage` | `partial_success` | 30 | `triage_max_pairs = 30` の上限内で 30 件 triage、15 件 truncate |

triage 結果:
- `send_to_review_count = 7`
- `send_to_review_false_count = 23`
- `triage_truncated_pairs = 15`

`.spec-anchor/context/conflict_candidate_pairs.jsonl` に `triage.send_to_review = true` の 7 件のみが保存された。

### 既知 conflict の SpecClaim 経路での検出 (合格基準 B)

7 件の `send_to_review = true` candidate のうち、**§0004 (Session Termination) ↔ §0005 (Session Retention Policy)** の pair が **2 件** (異なる SpecClaim pair として):

| display_id | left_section | right_section | confidence | triage reason (要約) |
|---|---|---|---|---|
| CC-00013 | `0004-session-termination` | `0005-session-retention-policy` | high | logout immediately invalidates the current ... |
| CC-00015 | `0004-session-termination` | `0005-session-retention-policy` | high | one allows automatic purging after 24h ... |

両方とも `confidence = high`、`send_to_review = true` で Conflict Review pipeline の入力候補として保持された。

判定: **合格基準 B 達成**。既知 conflict が SpecClaim 経路で `triage.send_to_review = true` として Conflict Review pipeline に届くことを実機で確認した。

### 2 回目 incremental (skipped 確認)

state を保持したまま `python3 -m spec_anchor core` を再実行:

| stage | status | LLM calls | reason |
|---|---|---|---|
| `spec_claims` | `skipped_unchanged` | 0 | `input_and_config_fingerprint_match` |
| `claim_retrieval` | `skipped_unchanged` | 0 | `input_and_config_fingerprint_match` |
| `conflict_candidate_triage` | `skipped_unchanged` | 0 | `input_and_config_fingerprint_match` |

3 stage 全てが skipped、LLM call は 0。

## recall 比較 (検証条件 C、Phase 5 着手判断データ)

### 比較方針

`doc/TODO.ja.md` T-spec-claim-phase-4 検証条件 C は **任意**。本 Phase では production config に legacy mode key を追加しない方針を維持する (SCD-024 確定通り)。比較は revision 切替と artifact 退避で行う。

Phase 5 着手前に旧 `possible_conflict` 経路と新 SpecClaim 経路の recall 比較を行う場合、次の手順を取る。

### 手順 (実施時にチェックして埋める)

1. **Phase 4 完了時点の artifact 退避**:
   - `cp -a .spec-anchor/context/conflict_candidate_pairs.jsonl /tmp/spec_claim_phase4_send_to_review.jsonl`
   - `cp -a .spec-anchor/state/core_progress.json /tmp/spec_claim_phase4_core_progress.json`
2. **Phase 5 着手前 revision (= 旧 `possible_conflict` 経路が動く revision、本 commit の親 commit) で実行**:
   - `git stash` (working tree クリーン)
   - `git checkout <Phase 4 完了時点の commit、本 commit の親>`
   - `mv .spec-anchor .spec-anchor.phase4.bak`
   - `mkdir -p .spec-anchor && cp -a .spec-anchor.phase4.bak/config.toml .spec-anchor/`
   - `python3 -m spec_anchor core` を実行
   - artifact (`conflict_review_items.json`, `potential_conflicts` warning) と diagnostics (`core_progress.json`) を取得
3. **diff 観点**:
   - 旧 `possible_conflict` 経路で `potential_conflicts` / `conflict_review_items.json` に出ていた pair が、新 SpecClaim 経路の `conflict_candidate_pairs.jsonl` (`send_to_review = true`) に含まれるか
   - 含まれない pair があれば、recall 低下として Phase 5 着手を保留する
   - 数値: 旧経路の conflict pair 数 / 新経路の send_to_review 数 / 共通 pair 数

### 比較結果 (実施時に追記)

実施日: (未実施)

| 観点 | 旧 `possible_conflict` 経路 | 新 SpecClaim 経路 | 差分 |
|---|---|---|---|
| conflict pair 検出数 | TBD | 7 | TBD |
| §0004 ↔ §0005 検出 | TBD | YES (CC-00013 / CC-00015) | TBD |
| recall 判定 | — | — | TBD |

## Phase 5 着手判断

実機検証 (検証条件 B) で **合格基準を達成**。新 SpecClaim 経路で既知 conflict が `triage.send_to_review = true` として Conflict Review pipeline に届くことを確認した。

recall 比較 (検証条件 C) は任意項目で、上記手順に従って実施できる。本記録時点で recall 比較は未実施だが、合格基準 B は単独で Phase 5 着手の必要条件を満たす (TODO.ja.md T-spec-claim-phase-4 完了条件)。

Phase 5 (T-spec-claim-phase-5) に進む。Phase 5 完了後、recall 比較を実施する場合は本ファイルの「比較結果」セクションに追記する。

## Phase 5 完了後の recall 維持確認 (2026-05-29)

### 環境

- 実行 revision: HEAD = `c8f3a48 chore(spec-claims): remove stale conflict_detection / conflict_judgement stages and project config conflict_pair_max_per_section (Phase 5 cleanup)` (Phase 5 削除 + cleanup 完了状態)
- LLM provider: Phase 4 と同じ (Codex CLI `gpt-5.4-mini` / `low` for spec_claims / claim_triage、Claude `claude-sonnet-4-6` / `low` for conflict_review)
- Qdrant + FlagEmbedding BGE-M3: 同上
- Source Specs: `docs/spec/sample.md` (Phase 4 と同じ、§0004 と §0005 の意図的 conflict を含む)
- state は fresh (Phase 4 後の state file を削除して再生成)

### Phase 4 (commit 285a6db) vs Phase 5 (commit c8f3a48) の比較

| 観点 | Phase 4 | Phase 5 | 判定 |
|---|---|---|---|
| `spec_claims` SpecClaim 件数 | 14 | 14 | recall 維持 |
| `claim_retrieval` candidate pair 件数 | 45 | 45 | recall 維持 |
| `triage.send_to_review = true` 件数 | 7 | 7 | recall 維持 |
| §0004 (Session Termination) ↔ §0005 (Session Retention Policy) の SpecClaim pair 検出 | CC-00013 + CC-00015 (両方 confidence = "high") | CC-00013 + CC-00012 (両方 confidence = "high") | **検出維持** (display_id 採番は cache key ではないため SCD-013 通り許容) |
| `conflict_review_items.json` (Conflict Review pipeline 到達) | — (Phase 4 時点では Phase 5 前経路で別 fixture / 別件数) | **3 件 (status = "pending")** | **新方式で end-to-end 動作** |

Phase 5 で `evaluate_conflicts` の入力境界を SpecClaim pair + evidence + `triage.send_to_review = true` に固定 (SCD-033) した結果、`conflict_evaluation` stage が `llm_calls = 7` (= send_to_review pair 7 件) を消化し、うち 3 件が pending Conflict Review Item として `.spec-anchor/context/conflict_review_items.json` に保存された。残り 4 件は LLM judge が non-pending (false_positive / not_a_conflict) と判定した結果として `potential_conflicts` warning へ振り分けられた経路。

### 判定

**recall regression なし**。さらに Phase 5 で初めて新方式の Conflict Review pipeline 全体 (SpecClaim 抽出 → Claim Retrieval → LLM triage → Conflict Review) の end-to-end 実機動作を確認できた。`display_id` の採番が変動するのは Phase 5 後の Claim Retrieval candidate 順序の整理 (`conflict_pair_max_per_section` 削除等) によるもので、`candidate_uid` (sorted claim_uid pair の sha256) と claim pair 自体は維持されている (SCD-013 通り `display_id` を primary key にしない設計のため許容)。

Phase 5 移行は完全に成功した。本セクションをもって T-spec-claim-phase-5 の合格基準 D (実機経路 recall 維持) を達成 (`doc/TODO.ja.md` T-spec-claim-phase-5 完了条件 D)。

## T-conflict-source-update-flow 実機 auto-dismiss 検証 (2026-05-29)

### 環境

- HEAD: `5f4bb1e test(conflict-review): add C-6 / C-3 / C-11 regression tests (T-conflict-source-update-flow 完全完了)` (T-conflict コア実装 + regression test 完了状態)
- LLM provider: Phase 4 / Phase 5 と同じ (Codex CLI `gpt-5.4-mini` / `low`、Claude `claude-sonnet-4-6` / `low` for conflict_review)
- Qdrant + FlagEmbedding BGE-M3: 同上
- Source Specs: `docs/spec/sample.md` (Phase 4 と同じ、§0004 Session Termination と §0005 Session Retention Policy の意図的 conflict を含む状態から開始)

### 手順

1. `.spec-anchor/state/spec_claims_state.json` / `conflict_candidate_pairs_state.json` および `.spec-anchor/context/spec_claims.jsonl` / `conflict_candidate_pairs.jsonl` / `conflict_review_items.json` を削除して fresh 状態にする (`/tmp/spec-anchor.bak.real-verify` にバックアップ)
2. 初回 `python3 -m spec_anchor core` 実行 (= 「人間が初めて Source Specs を /spec-core に通した状況」を再現)
3. `docs/spec/sample.md` の §Session Retention Policy を、§Session Termination と整合する内容に書き換える (active session 終了は §Session Termination に従い、本 section は post-termination の log retention のみを規定する形に変更)
4. 2 回目 `python3 -m spec_anchor core` 実行 (= 「人間が source 修正後に再度 /spec-core を走らせた状況」を再現)
5. `conflict_review_items.json` で前回 pending だった item が `status="dismissed"` + `resolution.decision_origin="auto_source_update"` に遷移していることを確認

### 結果

| 観点 | 初回 (修正前) | 2 回目 (§0005 修正後) | 判定 |
|---|---|---|---|
| `spec_claims` | success, llm_calls=6 (全 6 section) | success, llm_calls=1, action=`regenerated_partial` (§0005 のみ再抽出) | incremental 経路で意図通り |
| `claim_retrieval` | success, candidate_count=45 | success, action=`regenerated_partial` (変更 claim 起点で再候補) | incremental 経路で意図通り |
| `conflict_candidate_triage` | partial_success, llm_calls=30 (上限) | success, llm_calls=19 (cache hit + 新規評価) | cache 再利用 + 新規 triage 動作 |
| `conflict_evaluation` | llm_calls=6 | llm_calls=4 | pending item 再評価 |
| `conflict_review_items.json` 件数 | 3 件 (`status=pending`) | 3 件 (**`status=dismissed`**) | 全件 auto-dismiss |
| 自動 dismiss の `resolution.decision_origin` | — | **`auto_source_update`** (`human` ではない) | C-5 / C-12 達成 |
| 自動 dismiss の `resolution.auto_dismiss_reason` | — | **`source_update_recheck_pair_absent`** | C-6 / C-13 達成 |

### 判定

実機経路で T-conflict-source-update-flow の主要合格基準 (`doc/TODO.ja.md` T-conflict 完了条件) が動作確認できた:

- 合格基準 A (既存 pending item の解除): **達成**。3 件すべてが pending → dismissed に遷移。
- 合格基準 B (pair が消えた場合の解除): **達成**。`auto_dismiss_reason = source_update_recheck_pair_absent` で全件解除。
- 合格基準 D (人間 decision と auto dismiss の区別): **達成**。`decision_origin = auto_source_update` で自動 dismiss であることが明示される。
- 合格基準 E (`pytest --skip-external`): 別経路で達成済み (commit `5f4bb1e` 時 614 passed, 0 failed)。

本セクションをもって T-conflict-source-update-flow の実機経路合格基準を達成した。残範囲は `spec-anchor-watch` の長時間 process + filesystem event integration のみ。

## T-conflict-source-update-flow 実機 watcher / filesystem event 検証 (2026-05-29)

### 環境

- HEAD: `706de59 docs(perf): record T-conflict-source-update-flow 実機 auto-dismiss 検証 (合格基準 A / B / D 達成)` (上記 auto-dismiss 検証完了状態)
- watcher コマンド: `python3 -m spec_anchor watch --max-runs 1 --interval-sec 3 --debounce-sec 3`
- LLM provider / Qdrant / FlagEmbedding BGE-M3: 上記 auto-dismiss 検証と同じ実機環境

### 手順

1. `spec-anchor watch` を background で起動 (`--max-runs 1` で 1 回 update したら exit、`--interval-sec 3` で 3 秒 poll、`--debounce-sec 3` で 3 秒 debounce)
2. 8 秒待機してから `docs/spec/sample.md` の §Session Retention Policy を `sed` で log retention 限定版に書き換え (上記 auto-dismiss 検証と同じ修正)
3. watcher が filesystem event を検知して `run_spec_core_for_watcher` 経由で `/spec-core` を起動することを観測
4. `.spec-anchor/state/watch_state.json` の `last_lock` / `last_result` で watcher 経路の動作を確認

### 結果

| 観点 | 値 |
|---|---|
| sed 編集時刻 | `2026-05-29T04:11:41Z` (Monitor タイムスタンプ) |
| watcher が core lock 取得した時刻 | `2026-05-29T04:11:42.952Z` (`watch_state.json.last_lock.acquired_at`) |
| 検知遅延 (sed → lock) | **約 1 秒** (filesystem event ベースで即時) |
| watcher core 実行終了時刻 | `2026-05-29T04:13:43.205Z` (`watch_state.json.finished_at`) |
| 実行時間 | 約 2 分 (incremental 経路、`spec_claims` 1 section 再抽出 + `conflict_candidate_triage` 19 LLM call) |
| `last_owner` | `watcher` |
| `last_queue_count_at_start` | 1 |
| `last_result.mode` | `incremental` |
| `last_result.pending_conflict_count` | 0 (修正後の §0005 で conflict 解消、既存 dismissed が維持) |
| `last_result.related_sections_status` | `success` |
| watcher exit 状態 | `--max-runs 1` 通り 1 回 update 後 clean exit |

### 判定

`spec-anchor watch` の filesystem event 検知 → `run_spec_core_for_watcher` 経由の `/spec-core` 起動 → `last_result` への結果保存 → `--max-runs 1` 通り exit、を実機で約 1 秒の検知遅延で動作確認した。

これにより T-conflict-source-update-flow の合格基準 F (watcher 経路、`doc/TODO.ja.md` T-conflict 検証条件 F) が達成された。直接 import 経路 (`run_spec_core_for_watcher`) は `tests/test_spec_core.py::test_t_conflict_source_update_auto_dismisses_through_watcher_internal_api` で fake 経路でも確認済みであり、本セクションは長時間 process + filesystem event のレイヤーを実機で補強する。

本セクションをもって T-conflict-source-update-flow の合格基準 A / B / D / F すべてが実機で達成された。残範囲は real Qdrant / BGE-M3 / real provider / `local-service` / `real-smoke` の各 profile での pytest 実行のみ (本ファイル時点では実機 spec-anchor core / watch は実 provider 経路で動いており、pytest profile はカバーしていない別軸の検証)。
