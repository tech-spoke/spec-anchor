# TODO: conflict judge を budget-first + batch 化し LLM brute-force を解消する

**起票日**: 2026-05-31
**起票者**: GPT (設計指摘) + Human (同意) + Claude main (記述)
**最終更新**: 2026-05-31
**ステータス**: Phase 1/2/3 完了・Phase 4 据え置き（実質完了）。実機 rebuild で llm_call 21→5・総 wall 127s→91s・recall 5 conflict 維持を確認。残: 4シナリオ再計測 + 人間レビュー。コミット e6bc616(P1)/aba7d52(P2)/86fb655+237f7cd(P3)
**関連設計書**: `doc/TODO/TODO_conflict_detection_pipeline_simplify.ja.md`（本体課題・機能は完了、本 TODO はその性能/設計 follow-up）、`doc/性能測定/METRICS.md` 第12回

**起票時点のソース pin（commit `db39a0d`、行番号 drift 防止用 permalink）**:
- `spec_anchor/section_pair_candidates.py`: https://github.com/tech-spoke/spec-anchor/blob/db39a0d/spec_anchor/section_pair_candidates.py
- `spec_anchor/conflict_review.py`（`evaluate_section_pair_conflicts`）: https://github.com/tech-spoke/spec-anchor/blob/db39a0d/spec_anchor/conflict_review.py
- `spec_anchor/llm_provider.py`（conflict_review schema/prompt）: https://github.com/tech-spoke/spec-anchor/blob/db39a0d/spec_anchor/llm_provider.py

## 全体目的

section_pair conflict judge が **1 pair = 1 LLM call の brute-force** になっており、小規模でも LLM call 数が多い。実測 6 section = 21 calls / 62〜68s、threshold 上限 12 section では C(12,2)+12 = **78 calls**(self-pair 込み)。suite / CI / 実運用で重すぎる。次の 2 軸で解消する。

1. **section 数による all_pairs / retrieval_cap の分岐を廃止し、常に budget-first の単一 pipeline に統一する**。
2. **judge を batch 化**(複数 pair を 1 LLM call で判定、parse failure / 欠落時のみ該当 batch を per-pair fallback)し、recall を落とさず call 数を削る。

機能 correctness(検出・conflict_points・dismiss/reopen)は本体課題で緑。本課題は **性能/設計の follow-up** であり、これが終わるまで本体課題を「性能面で完了」とは扱わない。

### 実装順序（段階実施・一括禁止）

**本 TODO は一括実装してよい課題ではない。** 各 phase ごとに 設計 → 実装 → 実機 recall/metrics 確認 を分け、前後で call 数 metrics を比較して「どの変更が何に効いたか」を追跡可能にする。recall に影響しうる変更(budget-first / self-pair)を batch 化と同時にやらない。

```text
Phase 1: diagnostics 追加 (#4)
  - judge_pair_count / batch_count / fallback_count / capped_out_count /
    self_pair_count / llm_call_count を CoreResult・core_progress に出す
  - これを先に入れ、以降の phase の before/after を数値で比較できるようにする

Phase 2: batch judge (#2) ★最優先の本丸
  - batch size 小さめ (3〜5)、missing pair / parse failure は per-pair fallback
  - recall を落とさず call 数を減らせる見込みが高い (recall 安全)
  - before/after metrics 比較 + 実機 recall 確認

Phase 3: budget-first 統一 (#1)
  - all_pairs / retrieval_cap 分岐 (small_section_all_pairs_threshold) 廃止
  - exhaustive は検証用 config に残す
  - recall 影響しうる → Phase 2 後に metrics を見て段階実施

Phase 4: self-pair 見直し (#3)
  - allow_same_section_pair=false へ即変更しない
  - lightweight internal check 化 or config 明示化
  - recall 影響しうる → 最後
```

理由: batch judge は recall 安全に call 削減できる一方、budget-first / prefilter / self-pair lightweight 化は recall に影響し得るため、同時実施は性能改善の原因追跡を困難にする(GPT 指摘・Human 同意)。

### なぜ分岐廃止か（GPT 指摘 + Human 同意）

- 「小規模だから全網羅しても安い」は **1 pair 1 LLM judge では成立しない**(6 section=21、12 section=78 calls)。
- `≤12 all_pairs / >12 retrieval_cap` は section が 1 個増えただけで探索戦略が急変する **12/13 の段差**を生み、性能も recall も境界で不自然に変わる。
- all_pairs は「候補生成」としては妥当だが、生成した pair を全部 LLM judge する必要は別問題。候補生成 → ランク付け → cap → cap 内なら結果的に全件 judge、とすれば小規模は従来同等(全件 judge)で段差が消える。

## 状況サマリー

| Phase | # | sub task ID | 概要 | 状態 | 残作業 | 最終更新 | 完了 commit |
|---|---|---|---|---|---|---|---|
| **1** | 4 | T-judge-budget-diagnostics | call budget を diagnostics に可視化(judge_pair_count / batch_count / fallback_count / self_pair_count / llm_call_count)。capped_out は truncated_count に流用 | **完了** | — | 2026-05-31 | e6bc616 |
| **2** | 2 | T-batch-judge | section_pair judge を batch 化(judge_batch_size 既定5)+ parse failure/欠落時の per-pair fallback + grounding 維持 | **完了** | — | 2026-05-31 | aba7d52 |
| **3** | 1 | T-budget-first-unify | section 数分岐(small_section_all_pairs_threshold)を廃止し budget-first(global_pair_cap ベース)へ統一。conflict_candidate_mode (budget/exhaustive) | **完了** | — | 2026-05-31 | 86fb655 / 237f7cd(docs) |
| **4** | 3 | T-self-pair-lightweight | self-pair を lightweight internal check 化 or config 明示。`allow_same_section_pair` は維持(=false へ即変更しない) | **据え置き(2026-05-31 Human 判断)** | — | 2026-05-31 | — |

## sub task 詳細

### #1 T-budget-first-unify: section 数分岐を廃止し budget-first へ

#### 背景 / 対応方針

現 `generate_section_pair_candidates` は `len(sections) <= small_section_all_pairs_threshold(12)` で all_pairs、超で retrieval_cap に分岐する。これを廃止し、section 数に依らず同一経路にする:

```text
1. candidate pair を生成 (self-pair を含めるかは #3)
2. score / lightweight filter / retrieval signal で順位付け
3. max_judge_pairs / global_pair_cap で上限を切る
4. cap 内に収まるなら結果的に全件 judge / 超えるなら上位だけ judge
```

小規模で候補数が cap 以下なら全件 judge され recall 同等。`exhaustive` は通常 default にせず、検証用 config (`conflict_candidate_mode = "exhaustive"` 等) として明示有効化する。

> CR-B01 反映(rule 15 根絶・High): 「分岐廃止」を実装する場合、`small_section_all_pairs_threshold` を **コードだけでなく config.py(`ConflictCandidateDetectionConfig`)/ `doc/EXTERNAL_DESIGN.ja.md`(§4.1・config table・L261/L1119 付近)/ `doc/DESIGN.ja.md`(L926 付近)/ 初期 config template / test** から全て根絶する。コードだけ変えて設計書・設定 key が残るのは根絶漏れ。廃止せず残す判断なら、その理由を本 TODO に明記する。

> CR-B07 反映(grep 0 の scope・Medium): 根絶検証 `git grep small_section_all_pairs_threshold` の対象は **live code(`spec_anchor/`)+ active contract docs(`doc/EXTERNAL_DESIGN.ja.md` / `doc/DESIGN.ja.md` / `doc/EXTERNAL_SPEC_DRAFT.ja.md`)+ config template + tests(`tests/`)** に限定し、**`doc/TODO/**` と `archive/**` は除外**する(本 TODO 自身が同語を含むため、文字通りの全体 grep 0 は完了不能)。本 TODO は完了時に `doc/TODO/完了済みTODO/` へ git mv する(本体課題 CR-007 と同パターン)。

> CR-B02 反映(既存 conflict の cap-exempt 再評価・High・最重要): budget-first の cap は **新規候補 pair にのみ適用**する。本体課題 CR-001(`TODO_conflict_detection_pipeline_simplify.ja.md` の absence reliable)で確定済みの通り、**既存 Conflict Review Item が参照する section_pair は cap/top_k 対象外で必ず再評価対象へ union する(cap 後)**。現コード `section_pair_candidates.py` の `existing_conflict_recheck`(cap-exempt union)を壊さない。cap 外に落ちただけで auto-dismiss しない。judge_targets = `capped_new_candidates ∪ existing_conflict_pairs_requiring_recheck(cap 免除)`。

> CR-B04 反映(新 key/用語の定義・Medium・rule 6/16): `max_judge_pairs` と既存 `global_pair_cap` の関係を実装前に確定する — **置換 / 併存 / 別軸**のどれか。現状 `global_pair_cap`(=retrieval_cap の上限)が既にあるので、budget-first では `global_pair_cap` を「judge に送る最終上限」として**流用(rename ではなく意味拡張)**するのが既存との整合上有力(新 key を増やさない)。`conflict_candidate_mode = "exhaustive"` は **新規 config key**であり、含むもの(全 pair を cap 無視で judge)/含まないもの(通常 budget 経路)/既定値(budget)/検証用途を明記してから追加する。

#### 残作業 / 人間判断点

- budget-first の ranking 信号(dense score / 制約密度 / 見出し類似など)と judge 上限の既定値の確定（recall トレードオフ）。`global_pair_cap` 流用 vs 新 `max_judge_pairs`(CR-B04)。
- `small_section_all_pairs_threshold` の廃止可否(GPT・Human は廃止寄り)。廃止なら CR-B01 の全 surface 根絶。exhaustive モードを残すか。
- 既存 conflict の cap-exempt 再評価を必ず維持(CR-B02)。

### #2 T-batch-judge: judge を batch 化

#### 背景 / 対応方針

現 `evaluate_section_pair_conflicts` は 1 pair = 1 `_call_judge`。複数 pair を 1 LLM call で判定する batch judge を基本にする。例: 21 pair を 5 pair ずつ → ~5 calls。

- batch judge の出力契約(各 pair の outcome / conflict_points を pair 識別子付きで返す)を `llm_provider.py` の conflict_review schema/prompt に定義。
- **parse failure / 出力欠落(後半 pair の見落とし)時は、該当 batch だけ per-pair fallback** に落とす(recall を守る)。
- 既存の並列化(#6 commit feba231)と整合(batch 単位で ThreadPoolExecutor)。

> CR-B06 反映(grounding 維持・High): batch 化で `llm_provider.py` を直呼びして `_EvidenceGroundedConflictJudge`(`core.py` 付近、Purpose/Core Concept を judge 入力へ注入)を迂回すると、本体課題 CR-004 で確定した grounding が外れ過剰検出になる。**batch call も per-pair fallback も既存の `_EvidenceGroundedConflictJudge` wrapper を必ず通し、Purpose / Core Concept grounding を維持する**。batch では複数 pair を 1 prompt にまとめても、各 pair の section A/B + 共通 grounding(Purpose/Core Concept)を含める。grounding を外す実装は不採用。

#### 残作業 / 人間判断点

- batch size 既定値(JSON 崩れリスクと call 削減のバランス)。
- 実機 recall 確認: batch 化前後で既知矛盾の検出件数が落ちないこと(real provider)。

### #3 T-self-pair-lightweight: self-pair の扱い見直し（据え置き）

> **据え置き判断(2026-05-31 Human)**: Phase 2 の batch 化で self-pair も cross-pair も同一 batch に吸収されたため、self-pair 軽量化の削減効果は ~2 batch call まで縮小(batch 化前は 6 call 削減見込みだった)。recall リスクを冒して lightweight 化する費用対効果が低いと判断し、本 sub task は据え置く。将来 self-pair を別扱いする必要が出たら再開する。`allow_same_section_pair=true`(生成して judge する)は維持。

self-pair は今回 21 calls 中 6 件(~29%)を占めるが価値が低い。`allow_same_section_pair = true` は維持しつつ、default では self-pair を LLM judge 全投入せず lightweight internal check に回す、または config で明示有効化する。即 `allow_same_section_pair=false` は recall 影響があるため避ける。

> CR-B03 反映(同一 section 内矛盾 scope との整合・High): 本体課題は `allow_same_section_pair = true` で self-pair を必ず**生成**すると確定済み(`TODO_conflict_detection_pipeline_simplify.ja.md` CR-002、現コード `section_pair_candidates.py` の self-pair cap-exempt 追加)。本 sub task は「生成は維持、LLM judge への投入だけ見直す」もの。実装前に次を定義する:
> - lightweight internal check が **何を検出するか**(例: 同一 section 内の単純な相反語/数値矛盾の構文的検知)と **何を LLM judge に回すか**(検出できない深い矛盾)。
> - **recall 維持条件**: lightweight 化で既知の同一 section 内矛盾(あれば)を取りこぼさないこと。現 sample(6 section)に self 矛盾が無いなら、recall 影響は「なし(実測)」と記録する。判断できる材料が無いまま lightweight 化しない。
> - 候補: (a) self-pair を config で明示有効化(`allow_same_section_pair` の意味を「生成して judge する」に保ち、別 flag で self だけ off)、(b) self-pair は構文 prefilter で明らかな矛盾兆候がある時だけ LLM judge。どちらも `allow_same_section_pair=true` の生成契約は壊さない。

### #4 T-judge-budget-diagnostics: call budget の可視化

`CoreResult` / `core_progress` の section_pair_candidate_generation / conflict_evaluation diagnostics に call budget を出し、各 phase の before/after を数値比較可能にする。

> CR-B05 反映(field 定義・既存命名との整合・Medium): 既存 diagnostics は `generated_count`(生成候補数)/ `truncated_count`(cap で落とした数)/ `recheck_count`(既存 conflict 強制再評価数)(`section_pair_candidate_generation`)。新規 field は意味を明記し既存と整合させる:
> - `judge_pair_count`: 実際に LLM judge に渡した pair 数(= cap 後 union 後の judge_targets 数)。
> - `batch_count`: batch judge で発行した batch 数(Phase 2)。
> - `fallback_count`: parse failure / 欠落で per-pair fallback に落ちた pair 数(Phase 2)。
> - `capped_out_count`: budget cap で judge から外した新規候補数(= 既存 `truncated_count` と重複するなら統合し新設しない。新設する場合は差分を明記)。
> - `self_pair_count`: self-pair の数(うち lightweight 処理 / LLM judge の内訳)。
> - `llm_call_count`: 実 LLM 呼び出し回数(batch + fallback の合計。batch 化前は judge_pair_count と一致、batch 化後は減る)。
> 既存 field と意味が重なるものは**新設せず流用**する(rule 16)。新設するものだけ追加し、命名は snake_case で既存に揃える。

## 課題全体の完了条件

- section 数分岐が廃止され、budget-first 単一 pipeline + batch judge で動く。
- 実機 recall が batch 化・budget 化前(本体課題 第12回)から落ちない。
- docs サンプル(6 section)の conflict_evaluation call 数 / wall が削減される(METRICS で before/after)。
- `pytest --skip-external` 回帰なし + 実 provider で recall 維持確認。

## 設計レビュー指摘と disposition（2026-05-31 CODEX 監査）

実装着手前の TODO に対する CODEX 監査。全件採用し対象 sub task へ反映済み(CLAUDE.md ルール 9)。

| ID | 重要度 | 対象 | 指摘要約 | 判定 | 反映 |
|---|---|---|---|---|---|
| CR-B01 | High | #1 | 「分岐廃止」が config.py / 外部・内部設計 / template / test の根絶対象を挙げておらず、コードだけ変えて key/docs が残る事故(rule 15) | 採用 | #1 に CR-B01: `small_section_all_pairs_threshold` を全 surface で根絶(grep 0)。残すなら理由明記。 |
| CR-B02 | High | #1 | budget-first 手順に既存 conflict の cap-exempt 再評価 / absence reliable(本体 CR-001)が欠落。実装者が既存 pending を落とす恐れ | 採用 | #1 に CR-B02: cap は新規候補のみ。既存 conflict pair は cap 免除で union(cap 後)。cap 外≠auto-dismiss。 |
| CR-B03 | High | #3 | self-pair lightweight 化が「同一 section 内矛盾を含める」確定(本体 CR-002)と未整合。検出範囲・recall 維持条件が未定義 | 採用 | #3 に CR-B03: 生成は維持、judge 投入のみ見直し。検出範囲と recall 維持条件を実装前に定義。 |
| CR-B04 | Medium | #1 | `max_judge_pairs` / `conflict_candidate_mode="exhaustive"` が既存 `global_pair_cap` との関係未定義(rule 6/16) | 採用 | #1 に CR-B04: `global_pair_cap` 流用(意味拡張)を有力、`exhaustive` は新 key として含む/含まない/既定を定義。 |
| CR-B05 | Medium | #4 | diagnostics field の意味が曖昧、既存 `generated_count`/`truncated_count`/`recheck_count` と命名不整合 | 採用 | #4 に CR-B05: 各 field の意味を定義、既存と重複は流用、新設のみ追加。 |
| CR-B06 | High | #2 | batch judge に Purpose/Core Concept grounding 維持が未記載。llm_provider 直呼びで wrapper 迂回すると過剰検出(本体 CR-004) | 採用 | #2 に CR-B06: batch / fallback とも `_EvidenceGroundedConflictJudge` を通し grounding 維持。外す実装は不採用。 |
| CR-B07 | Medium | #1 | `small_section_all_pairs_threshold` の grep 0 が本 TODO 自身に hit し完了不能 | 採用 | #1 に CR-B07: grep 0 対象を live code + active contract docs + template + tests に限定、`doc/TODO/**`・`archive/**` 除外。完了時に本 TODO を 完了済みTODO へ移す。 |

## 依存 / scope 外

- 本体課題 `TODO_conflict_detection_pipeline_simplify.ja.md`(機能完了)の性能 follow-up。機能契約(section_pair / conflict_points / dismiss-reopen)は変えない。
- recall に影響する判断(judge 上限値 / batch size / self-pair 方針)は実装着手前に人間と確定する。
- **本体課題の確定決定を覆さない**: `allow_same_section_pair=true`(生成は維持)、既存 conflict の cap-exempt 再評価、conflict_points schema は本 TODO で変更しない。
