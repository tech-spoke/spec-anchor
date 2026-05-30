# 矛盾解決簡素化 production E2E — 調査結果 (2026-05-30, GPT レビュー用)

本ディレクトリは `doc/TODO/TODO_conflict_resolution_simplification.ja.md` の残ゲート
「production E2E(実 provider 一巡)」を実行した際の証跡と、その過程で判明した
性能・設計上の論点をまとめたもの。**production E2E はまだ PASS していない**(理由は下記)。

検証スクリプト: `scripts/run-conflict-e2e.py`(実 Codex / Claude CLI、起動済み Qdrant、
FlagEmbedding BGE-M3 を使用)。

## 1. production E2E の進捗

同一 target に直接矛盾する 2 つの Source Spec(`docs/spec/checkout.md` の
「>1000 USD は manager 承認必須」 vs `docs/spec/automation.md` の「全注文を自動承認」など)を
seed し、4 phase を検証する。

| phase | 内容 | 結果 |
|---|---|---|
| 1 | `/spec-core` で保持物生成 + 実 provider が pending conflict を生成 | **PASS**(pending 多数生成) |
| 2 | `/spec-inject` が pending で停止せず `pending_conflict_items` 返却・`inject-search` 実行可 | **PASS** |
| 3 | `spec-anchor core --dismiss-conflict` で却下永続化・注入対象から除外 | **PASS** |
| 4 | 却下根拠セクション編集 → hash 失効 → `/spec-core` 再実行で dismissed→pending 再浮上 | **1 回目 FAIL → テスト修正済み・再実行は未完了** |

証跡(1 回目 run、`stdout/` と `artifacts/phase*.json`、いずれも 21:25-21:30 生成):

- `artifacts/phase1-conflict_review_items.json` … pending conflict 生成
- `artifacts/phase2-inject.json` … `should_stop=false` / `pending_conflict_items` 返却
- `artifacts/phase3-conflict_review_items.json` / `phase3-inject-after-dismiss.json` … dismiss 永続化
- `artifacts/phase4-conflict_review_items.json` … phase4 の結果(下記 root cause の根拠)

注意: `commands.log` / `evidence_map.jsonl` / `config.toml` / `project-path.txt` /
`provider-invocations.jsonl` は 2 回目 run の開始時に上書き・truncate されたため、
phase1-4 の権威ある証跡は `stdout/*.stdout` と `artifacts/phase*.json`(1 回目)を見ること。

## 2. phase4 失敗の root cause(製品バグではなくテスト設計のミス)

1 回目の phase4 編集は矛盾文そのもの(`high-value orders is forbidden.` の行)に追記した。
`compute_claim_uid`(`spec_anchor/spec_claims.py:430`)は `claim_text` と `evidence_start`
(オフセット)を含むため、claim 文を変えると claim_uid → candidate_uid → conflict_id が変化する。

その結果、再 `/spec-core` 時に旧 conflict_id のペアは「消えた(pair absent)」と判定され、
**設計通り** `source_update_recheck_pair_absent` / `decision_origin=auto_source_update` で
自動 dismiss された(`artifacts/phase4-conflict_review_items.json` で確認、6 件)。
一方、編集後の claim には**新しい conflict_id の pending が 11 件**立った。
つまり矛盾は pending として再浮上しており、製品挙動は正しい。

テスト側は「同一 conflict_id が dismissed→pending に戻る」ことを assert していたため fail した。
修正済み: phase4 編集を **claim-preserving**(既存 claim 文とオフセットを変えず、セクション末尾に
無関係な段落を追記)に変更し、同一 conflict_id が reopen することを検証する形にした
(`scripts/run-conflict-e2e.py` の Phase 4)。**再実行は性能上の理由でまだ完走していない**。

## 3. 性能の問題(本セッションの主要論点)

実 provider の `/spec-core` が大幅に遅い。phase1 の実測ステージ:

```
section_metadata           34.5s
section_collection_upsert  19.7s
related_sections           27.7s
spec_claims               100.3s   ← 新規
claim_retrieval            15.5s   ← 新規
conflict_candidate_triage 176.6s   ← 新規 (partial_success = 上限到達)
conflict_evaluation       (実行中)
```
provider 呼び出し合計 254 回(codex 195 + claude 59)。

比較: 2026-05-26 の full run(6 section、`doc/性能測定/core_progress_all.json` 他)は
合計 ~70-114s で、矛盾検出は `conflict_evaluation` 1 ステージ(14-43s)のみ。
`spec_claims` / `claim_retrieval` / `conflict_candidate_triage` は**存在しなかった**。

遅さの構造的原因:

- `spec_claims`(`spec_anchor/spec_claims.py:584` `for section in records`)は section ごとに
  LLM を**逐次**呼ぶ。並列化なし。
- `conflict_candidate_triage`(`spec_anchor/conflict_candidates.py:292` `for candidate in candidates`)は
  候補ペアごとに LLM を**逐次**呼ぶ。`triage_max_pairs=30` 上限。並列化なし。
- `llm_batch_concurrency` を尊重するのは `conflict_evaluation`(`spec_anchor/conflict_review.py:518`)
  **のみ**。新ステージはこの設定に関係なく常に逐次。

## 4. 設計上の論点(GPT に見てほしい点)

### 4-1. 経緯(事実)

- 4 ステージ化は **SpecClaim 経路移行**(`T-spec-claim-phase-1〜5`、完了 2026-05-29、
  `doc/TODO/完了済みTODO/TODO_2026-05-29_specclaim_complete.ja.md`、設計は
  `doc/OLD/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md`)で導入された。
- 本来の動機は **責務分離**(設計書 §3 問題 1/2):矛盾検出が `related_sections` の
  `possible_conflict` フラグに相乗りしていたため、related_sections のモデルを速くすると
  矛盾検出が消える結合があった。recall は Phase 4 gate で**維持(regression なし)**を確認する条件。
  (= 「recall 向上 / 拾い漏れを無くす」が目的という整理は不正確。)
- 性能(wall time / 実用速度)の受け入れ基準は移行 TODO の合格基準に**無かった**。

### 4-2. 論点: 責務分離に 4 ステージは必要か

責務分離(検出を related_sections から切り離し、専用 model routing を持たせる)に必要なのは
「専用 conflict stage + 専用 model + 1 段の judge」だけで、claim 抽出も二段 LLM も不要、という見立て。

| 要素 | 責務分離に必要か | 備考 |
|---|---|---|
| 専用 conflict stage + 専用 model | 必要 | これが責務分離の本体 |
| stage 2 claim_retrieval(LLM 不使用) | あると良い | O(n²) 候補枝刈り、安い |
| stage 1 spec_claims(LLM、section ごと) | 責務分離には不要 | claim 単位 `evidence_span` と claim_uid ベース dismiss/reopen のための別機能 |
| stage 3 conflict_candidate_triage(LLM、ペアごと) | 不要の疑い | 下記 |

stage 3 が過剰の根拠(移行記録の実数): candidate 45 → triage 30 件(上限)→ 7 件通過 → judge 7 件。
triage 30 + judge 7 = 37 回。triage 無しで judge 全 45 件なら 45 回。差は 8 回のみで、上限を外せば
逆に増える。しかも wall time では triage が最遅。「安いフィルタ」の役割を果たせていない。
→ triage を畳み、retrieval スコア閾値で候補を絞って judge に直接渡す案。

stage 1(claim 抽出)は責務分離と独立した機能判断:claim 単位の精密根拠と claim_uid ベースの
dismiss/reopen 失効追跡(本 E2E phase4 が依存)を維持する価値が、per-section LLM のコストに
見合うか。見合わないなら section ペア直接 judge に縮約できる(責務分離は専用 model routing で達成)。
トレードオフ: section 化すると dismiss/reopen が section hash 粒度になり、根拠も section 粒度に落ちる。

## 5. 残作業 / 提案

- production E2E(phase4 claim-preserving 版)の完走 — 現状は実 provider の遅さで実用的に回しづらい。
- 性能: 検出パイプラインの並列化(spec_claims / triage / judge に concurrency)+ 実用速度の受け入れ基準定義。
- 設計: 責務分離は実施前提。その上で (a) triage 畳み(低リスク・純改善)、(b) claim 抽出の要否、を判断。

人間判断が要る点(GPT レビュー後):
- 4 ステージを責務分離 + 軽量 judge に縮約するか、現行を保ったまま並列化のみで実用速度に乗せるか。
- claim 単位 dismiss/reopen を維持するか、section 粒度に戻すか。
