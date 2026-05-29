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
