# TODO: conflict judge を budget-first + batch 化し LLM brute-force を解消する

**起票日**: 2026-05-31
**起票者**: GPT (設計指摘) + Human (同意) + Claude main (記述)
**最終更新**: 2026-05-31
**ステータス**: 計画中（設計方針は概ね合意・実装着手前に recall トレードオフを確定）
**関連設計書**: `doc/TODO/TODO_conflict_detection_pipeline_simplify.ja.md`（本体課題・機能は完了、本 TODO はその性能/設計 follow-up）、`doc/性能測定/METRICS.md` 第12回、`spec_anchor/section_pair_candidates.py`、`spec_anchor/conflict_review.py`（`evaluate_section_pair_conflicts`）

## 全体目的

section_pair conflict judge が **1 pair = 1 LLM call の brute-force** になっており、小規模でも LLM call 数が多い。実測 6 section = 21 calls / 62〜68s、threshold 上限 12 section では C(12,2)+12 = **78 calls**(self-pair 込み)。suite / CI / 実運用で重すぎる。次の 2 軸で解消する。

1. **section 数による all_pairs / retrieval_cap の分岐を廃止し、常に budget-first の単一 pipeline に統一する**。
2. **judge を batch 化**(複数 pair を 1 LLM call で判定、parse failure / 欠落時のみ該当 batch を per-pair fallback)し、recall を落とさず call 数を削る。

機能 correctness(検出・conflict_points・dismiss/reopen)は本体課題で緑。本課題は **性能/設計の follow-up** であり、これが終わるまで本体課題を「性能面で完了」とは扱わない。

### なぜ分岐廃止か（GPT 指摘 + Human 同意）

- 「小規模だから全網羅しても安い」は **1 pair 1 LLM judge では成立しない**(6 section=21、12 section=78 calls)。
- `≤12 all_pairs / >12 retrieval_cap` は section が 1 個増えただけで探索戦略が急変する **12/13 の段差**を生み、性能も recall も境界で不自然に変わる。
- all_pairs は「候補生成」としては妥当だが、生成した pair を全部 LLM judge する必要は別問題。候補生成 → ランク付け → cap → cap 内なら結果的に全件 judge、とすれば小規模は従来同等(全件 judge)で段差が消える。

## 状況サマリー

| # | sub task ID | 概要 | 状態 | 残作業 | 最終更新 | 完了 commit |
|---|---|---|---|---|---|---|
| 1 | T-budget-first-unify | section 数分岐(small_section_all_pairs_threshold)を廃止し budget-first 単一 pipeline へ。exhaustive は検証用 config モードに退避 | 計画中 | recall トレードオフ確定 + 実装 + test | 2026-05-31 | — |
| 2 | T-batch-judge | section_pair judge を batch 化(N pair/1 call)+ parse failure/欠落時の per-pair fallback | 計画中 | batch size 確定 + 実装 + test + 実機 recall 確認 | 2026-05-31 | — |
| 3 | T-self-pair-lightweight | self-pair を LLM judge 全投入でなく lightweight internal check 化 or config 明示。`allow_same_section_pair` は維持 | 計画中 | 方針確定 + 実装 + test | 2026-05-31 | — |
| 4 | T-judge-budget-diagnostics | candidate / judge の call budget を diagnostics に可視化(judge_pair_count / batch_count / fallback_count / capped_out_count) | 計画中 | 実装 + test | 2026-05-31 | — |

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

#### 残作業 / 人間判断点

- budget-first の ranking 信号(dense score / 制約密度 / 見出し類似など)と `max_judge_pairs` 既定値の確定（recall トレードオフ）。
- `small_section_all_pairs_threshold` の廃止可否(GPT・Human は廃止寄り)。exhaustive モードを残すか。

### #2 T-batch-judge: judge を batch 化

#### 背景 / 対応方針

現 `evaluate_section_pair_conflicts` は 1 pair = 1 `_call_judge`。複数 pair を 1 LLM call で判定する batch judge を基本にする。例: 21 pair を 5 pair ずつ → ~5 calls。

- batch judge の出力契約(各 pair の outcome / conflict_points を pair 識別子付きで返す)を `llm_provider.py` の conflict_review schema/prompt に定義。
- **parse failure / 出力欠落(後半 pair の見落とし)時は、該当 batch だけ per-pair fallback** に落とす(recall を守る)。
- 既存の並列化(#6 commit feba231)と整合(batch 単位で ThreadPoolExecutor)。

#### 残作業 / 人間判断点

- batch size 既定値(JSON 崩れリスクと call 削減のバランス)。
- 実機 recall 確認: batch 化前後で既知矛盾の検出件数が落ちないこと(real provider)。

### #3 T-self-pair-lightweight: self-pair の扱い見直し

self-pair は今回 21 calls 中 6 件(~29%)を占めるが価値が低い。`allow_same_section_pair = true` は維持しつつ、default では self-pair を LLM judge 全投入せず lightweight internal check に回す、または config で明示有効化する。即 `allow_same_section_pair=false` は recall 影響があるため避ける。

### #4 T-judge-budget-diagnostics: call budget の可視化

`CoreResult` / `core_progress` の section_pair_candidate_generation / conflict_evaluation diagnostics に judge_pair_count / batch_count / fallback_count / capped_out_count を出し、call budget を監査可能にする。

## 課題全体の完了条件

- section 数分岐が廃止され、budget-first 単一 pipeline + batch judge で動く。
- 実機 recall が batch 化・budget 化前(本体課題 第12回)から落ちない。
- docs サンプル(6 section)の conflict_evaluation call 数 / wall が削減される(METRICS で before/after)。
- `pytest --skip-external` 回帰なし + 実 provider で recall 維持確認。

## 依存 / scope 外

- 本体課題 `TODO_conflict_detection_pipeline_simplify.ja.md`(機能完了)の性能 follow-up。機能契約(section_pair / conflict_points / dismiss-reopen)は変えない。
- recall に影響する判断(max_judge_pairs / batch size / self-pair 方針)は実装着手前に人間と確定する。
