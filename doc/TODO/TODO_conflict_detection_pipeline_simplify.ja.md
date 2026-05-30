# TODO: 矛盾検出パイプラインを claim 多段から section_pair 単段へ切り直す

**起票日**: 2026-05-30
**起票者**: Human (設計判断) + GPT (レビュー) + Claude main (調査・記述)
**最終更新**: 2026-05-30
**ステータス**: 実装着手可能（CODEX 設計レビュー CR-001〜CR-011 反映済み・人間判断点は詳細仕様まで確定。#1 は実装/テスト済み・コミット待ち。末尾「設計レビュー指摘と disposition」「人間判断点」参照）
**関連設計書**: `doc/EXTERNAL_DESIGN.ja.md`（§4.1 保持物の物理配置 / decision payload 節 / freshness / Agentic Search path）、`doc/EXTERNAL_SPEC_DRAFT.ja.md`、`spec_anchor/core.py`（`_spec_claims_enabled` L2872-2876・stale artifact read L622-640・spec_claims 経路 L1919 付近）、`spec_anchor/conflict_review.py`（`select_conflict_judging_pairs` L336・`evaluate_conflicts`）、`spec_anchor/claim_retrieval.py` / `spec_anchor/spec_claims.py` / `spec_anchor/conflict_candidates.py`（廃止対象）、`doc/TODO/TODO_conflict_resolution_simplification.ja.md`（本課題が supersede するゲート）、`doc/性能測定/METRICS.md`（性能根拠）

## 全体目的

矛盾検出の実装経路を `spec_claims → claim_retrieval → triage → conflict_evaluation` の **claim 単位 4 段パイプライン**から、**section ペアを直接 judge する単段検出器（section_pair conflict judge）**へ切り直す。あわせて claim 単位の検出・抽出・dismiss/reopen 機構を **廃止**（opt-in mode としても残さない）し、矛盾検出を「責務分離された軽量な dedicated judge」へ再設計する。

### なぜこの課題が必要か（土台）

直前の課題 `TODO_conflict_resolution_simplification.ja.md`（矛盾解決を「ゲート」から「注入情報」へ軽量化）は、矛盾の **扱い**（解決ゲート → 注入情報）を軽量化した。しかし production E2E に着手したところ、矛盾の **検出経路そのもの** が逆に重くなっていたことが判明した。

- 旧 `possible_conflict` 経路は Phase 5 で完全削除済みで、現在の検出器は `spec_claims → claim_retrieval → triage → conflict_evaluation` の 1 本だけ（`core.py` の spec_claims 生成 L1919 付近 →`conflict_review.select_conflict_judging_pairs` L336 → `evaluate_conflicts`）。
- つまり `spec_claims` は「あれば嬉しい追加機能」ではなく **唯一の検出器の第 1 段**になっている。
- 実 provider 実測（`doc/性能測定/METRICS.md` 第9回・56 section）では `spec-anchor core --rebuild` 総 wall 353.4 秒。`related_sections` 218 秒（34 calls）、`conflict_evaluation` 53 秒（11 calls）と、claim 抽出と pair 単位 judge が wall を押し上げている。

「簡素化」を掲げた課題の中で、矛盾検出が構造的に **責務分離（正しい意図）と claim 単位の高精度監査機構（重いコスト）を同時に入れて** しまい、後者が前者の利益を潰した。本課題はこの混入を解き、検出器を section_pair 単段へ戻すことで「簡素化」を検出経路にも一貫させる。

### 設計方針（Human 確定 / GPT・Claude 合意）

```text
責務分離:        実施する（related_sections から conflict 判定を切り離し、dedicated judge にする）
default 検出器:  section_pair conflict judge（矛盾検出は default on のまま）
claim-based:     opt-in ではなく廃止（spec_claims / claim_retrieval / triage / claim_uid 単位 dismiss/reopen）
triage:          廃止
conflict_review_item: section_pair_id + conflict_points[] へ再設計
dismiss/reopen:  section_pair 単位で扱う
concurrency:     最後に入れる（過剰な並列構造を温存しないため）
```

#### 用語の確定（CLAUDE.md ルール 6）

- **section_pair conflict judge**: 2 つの section（A / B）の本文を直接 LLM に渡し、矛盾しているかと矛盾箇所を判定させる検出器。事前に claim を抽出・永続化しない。
  - 含む: section ペアを単位とした矛盾判定、judge 出力としての `conflict_points[]`（`left_excerpt` / `right_excerpt` / `why_conflicting` / `severity`）
  - 含まない: claim 抽出、claim_uid、claim 単位 evidence_span の永続 artifact、triage 段
- **conflict_points[]**: section が長い場合に「どの section ペアが矛盾か」だけでは粗いため、judge 出力で矛盾箇所を細かく列挙する構造。identity（dismiss/track 単位）は section_pair で持ち、表示の細かさは conflict_points で担保する。
- **claim-based detection（廃止対象）**: `spec_claims.jsonl` への claim 抽出 + `claim_retrieval` による候補 pair 生成 + `triage` 選抜 + claim_uid 単位の conflict_id / dismiss/reopen。本課題で根絶する。

#### 「単段」の意味（誤解防止）

「section_pair 単段」とは **LLM 判定が section_pair judge の 1 段のみ**という意味であり、stage が物理的に 1 個になるわけではない。候補 section ペアの生成は LLM を使わない retrieval / rank stage として許可する。経路は次のとおり。

```text
sections
  ↓ section_pair_candidate_generation（LLM 非使用: retrieval / rank / cap）
  ↓ section_pair_conflict_judge（唯一の LLM 判定段）
  ↓ conflict_review_items
```

`related_sections` の **成果物 artifact には依存しない**（責務分離）。ただし section collection / embeddings / retrieval primitive（Qdrant・index）は conflict 専用候補生成のために再利用してよい。

### 成功とみなす条件

1. 矛盾検出は default on のまま、検出器が section_pair conflict judge の単段になっている（claim 抽出 → triage の多段が無い）。
2. `spec_claims` / `claim_retrieval` / `triage` / claim_uid 単位の conflict_id・dismiss/reopen が **根絶**される（CLAUDE.md ルール 15。stub / disabled / opt-in / fallback を残さない）。
3. `conflict_review_item` が section_pair 単位（`conflict_id` = section_pair_id、`source_refs` = section A / B、`conflict_points[]`、`why_conflicting`）に再設計される。
4. dismiss / reopen が section_pair 単位で機能する（reopen トリガーは従来どおり section hash 変化ベース。変わるのは conflict_id の同一性が claim pair → section pair になる点）。
5. 矛盾検出の on/off が `conflict_candidate_detection.enabled` で正規に制御できる（GPT-02 バグの解消）。detection disabled / failed 時に古い artifact を評価しない（GPT-01 の解消）。
6. 実 provider の production E2E で `spec-anchor core` の wall time が claim 多段時より短縮され、recall（既知矛盾の検出）が維持される。
7. 外部設計書・外部仕様 draft・内部設計書・コマンドテンプレ・`§4.1 保持物の物理配置`表が新検出経路と整合する（実装監査後に反映。CLAUDE.md ルール 20）。
8. **性能ガード**: `docs/`（`docs/spec/{sample.md, 25_*, 27_*, 29_*, 30_*}.md` 等の簡易サンプル）での `spec-anchor core` 計測で、検出経路変更前より総 wall time が **大幅に悪化しない**（目標は短縮）。簡易サンプルは性能測定の主対象であり、ここが大幅に遅くなる変更は不可。検出ステージを変えるため、`doc/性能測定/METRICS.md` の per-stage 計測（section_metadata / section_pair_judge / chapter_anchors / related_sections / section_collection_upsert）を新ステージ構成に合わせて取り直す。

## 状況サマリー

| # | sub task ID | 概要 | 状態 | 残作業 | 最終更新 | 完了 commit |
|---|---|---|---|---|---|---|
| 1 | T-stale-artifact-guard | GPT-01: detection disabled/failed 時に stale な `conflict_candidate_pairs.jsonl` / `spec_claims.jsonl` を無条件 read して評価するバグを修正（status ガード追加） | 実装済み・テスト未検証 | test 観測点修正 + pytest + production E2E | 2026-05-30 | — |
| 2 | T-section-pair-judge | section ペアを直接 judge する dedicated 検出器を新設（責務分離）。候補生成は非LLM retrieval/rank・非永続(A案)。`conflict_points[]` を出力契約に含める | ST-1/ST-2 実装済(additive・未配線) | ST-3 配線 + no-change skip + diagnostics + test | 2026-05-31 | — |
| 3 | T-conflict-item-redesign | `conflict_review_item` を section_pair_id + conflict_points[] に再設計し、dismiss/reopen を section_pair 単位へ | 未着手 | 実装 + test（方針承認済み） | 2026-05-30 | — |
| 4 | T-claim-pipeline-eradicate | `spec_claims` / `claim_retrieval` / `triage` / claim_uid 単位 dismiss/reopen を根絶（GPT-02 enable バグも消滅） | 未着手 | 実装 + grep 検証 + test | 2026-05-30 | — |
| 5 | T-contract-realign | 外部設計書 / 仕様 draft / 内部設計書 / テンプレ / §4.1 配置表を新検出経路へ整合（実装監査後） | 未着手 | docs 反映 + 人間レビュー | 2026-05-30 | — |
| 6 | T-judge-concurrency | section_pair judge の並列化を最後に入れる | 未着手 | 実装 + test | 2026-05-30 | — |
| 7 | T-perf-measure | docs 簡易サンプルで per-stage 計測を新ステージ構成に合わせて取り直し、性能ガード（大幅悪化なし・目標短縮）を確認 | 未着手 | 計測 + METRICS.md 更新 | 2026-05-30 | — |

## sub task 詳細

### #1 T-stale-artifact-guard: GPT-01 stale artifact safety（先行可・設計判断不要）

**状態**: 実装済み・テスト未検証（Claude main、未コミット）
**担当**: Claude main
**最終更新**: 2026-05-30

#### 背景

当初 `core.py:622-640` は `conflict_candidate_pairs.jsonl` と `spec_claims.jsonl` を **status ガードなしで無条件に read** し、そのまま `evaluate_conflicts` へ渡していた。一度 detection を走らせた後に `conflict_candidate_detection` を disabled / failed にしても、前回生成された古い pair / claim が評価対象になりえた。

> CR-006 反映（2026-05-30）: 当セッションで `spec_anchor/core.py:622-650` に `conflict_detection_reliable`（= `_conflict_pair_absence_is_reliable(...)` の値）による read ガードを追加済み。reliable な時だけ read し、disabled/failed 時は空を渡す。GPT-01 の (2) auto-dismiss 防止は既存の `allow_pair_absent_auto_dismiss=_conflict_pair_absence_is_reliable(...)`（`core.py:683` 付近）で対応済みだった。残るは追加 unit test の観測点修正と pytest 検証のみ。

#### 真因 / 対応方針

detection が disabled または前回 failed の場合、次の両方を守る（GPT 補足）。

1. **stale artifact を評価へ渡さない**: read 前に status を確認するガードを入れ、古い `conflict_candidate_pairs.jsonl` / `spec_claims.jsonl` を読まない。
2. **pair absent を根拠に既存 pending/dismissed を auto-dismiss しない**: 候補 pair が（disabled/failed で）存在しないことを「矛盾が消えた」と解釈して既存 Conflict Review Item を勝手に dismiss/失効させない。disabled/failed は「今回評価していない」であって「矛盾が無くなった」ではない。

これは設計判断・契約変更を伴わない純粋な安全バグ修正なので、本課題内で先行して着手してよい（GPT・Human 合意）。

注: #4 で `spec_claims.jsonl` 自体を廃止するため、本 sub task のうち spec_claims 側ガードは #4 に吸収される。先行する価値は「再設計レビュー中も現コードを安全に保つ」点にある。

#### 検証条件

主眼は「stale artifact を evaluate_conflicts に渡さない」こと。テストは優先順位を分ける（GPT 補足）。

- **必須（stale read guard の観測）**: detection disabled の状態で `spec-anchor core` を実行し、古い `conflict_candidate_pairs.jsonl` があっても conflict judge が走らない（評価されない）ことを確認する unit test。
- **回帰確認（既存 auto-dismiss guard の挙動維持）**: detection disabled / failed 時に、既存 pending/dismissed の Conflict Review Item が pair absent を理由に auto-dismiss されないことを確認する unit test。これは既存実装（`allow_pair_absent_auto_dismiss=False`）の確認。

#### 完了条件

disabled / failed 時に (1) stale artifact を評価しない、(2) 既存 conflict を auto-dismiss しない、の両方が test で観測でき、`pytest --skip-external` が回帰なし。

#### 残作業

- 追加 unit test の観測点修正（conflict judge が走ったかの signal を取り直す）と pytest 検証。
- production E2E での確認（#2〜#4 後の検出経路で）。

#### 依存 / scope 外

#2〜#6 に先行可能。spec_claims 側の最終処理は #4 に依存。

### #2 T-section-pair-judge: section_pair conflict judge を新設（責務分離）

**状態**: 未着手
**担当**: Human（設計レビュー）+ Claude main / CODEX（実装）
**最終更新**: 2026-05-30

#### 背景

矛盾判定を related_sections から切り離した dedicated 検出器を作る。claim 抽出を介さず、section A / B 本文を直接 judge へ渡す。

#### 真因 / 対応方針

- judge 入力: section ペア（A / B の本文 + source ref）**+ Purpose / Core Concept の grounding**。
- judge 出力: 矛盾の有無 + `conflict_points[]`（`left_excerpt` / `right_excerpt` / `why_conflicting` / `severity`）+ `why_conflicting`（summary）。
- section が長い場合に粗くならないよう、conflict_points を必須化する。

> CR-004 反映（grounding 維持・必須）: 現 `_EvidenceGroundedConflictJudge.judge_conflict`（`core.py:4315` 付近）は judge 入力に Purpose（`source_ref`/`hash`/`text`）と Core Concept を必ず注入している。これは「Purpose / Core Concept が解決する矛盾を pending にしない」ための過剰検出防止機構である。section_pair judge でこの grounding を外すと過剰検出（Purpose/Concept で解決済みの差異まで pending 化）が起きる。**section_pair judge も Purpose / Core Concept grounding を必ず入力に含める**。外す選択肢は取らない。

#### 候補 section ペア選抜方式（GPT 推奨で確定）

LLM を使わない retrieval / rank stage で候補を作る。`related_sections` の成果物 artifact には依存しない（section collection / embeddings / retrieval primitive は再利用してよい）。

```text
1. 全 section を section collection に入れる
2. 各 section から dense/sparse retrieval で近い section を取得
3. section pair を重複排除
4. score / rank / top_k で候補を絞る
5. その候補だけ section_pair judge に渡す
```

小規模 fixture は recall 優先で all-pairs、大きい docs は retrieval + cap で爆発を防ぐ（56 section の all-pairs = 1540 pair を LLM judge に全部渡すと再び遅くなるため）。

```text
section 数 <= 12 → all-pairs
section 数 > 12  → retrieval 候補 + cap
```

設定 key と初期値（確定）:

```toml
[conflict_candidate_detection]
enabled = true
small_section_all_pairs_threshold = 12   # section 数 <= この値で all-pairs、超えたら retrieval + cap
section_pair_top_k = 8
global_pair_cap = 80
min_dense_score = 0.55
allow_same_source_file_pair = true
allow_same_section_pair = true
```

> 「section 数 <= 12 → all-pairs」の閾値は固定値をコードに埋めず `small_section_all_pairs_threshold` として config 化する（後で調整しやすくするため）。

> 【ST-2 実装監査で判明・要 real Qdrant キャリブレーション】`min_dense_score` の比較対象。retriever の `hit.score` は RRF fused score（定義上 rank ベースで ~0.03 程度）であり、`min_dense_score=0.55` を fused score に当てると retrieval_cap 経路（section 数 > 12）で全候補が閾値落ちし false negative になる。現実装（`spec_anchor/section_pair_candidates.py`）は既存 `related_sections.py` と同じく `hit.score`（fused）に閾値を当てている。**閾値の比較対象を `hit.dense_score`（dense channel 生 cosine、real BGE-M3 で ~0.5-0.9）に変えるか、default 値を fused スケールへ再調整するかは、実 Qdrant + BGE-M3 で実測してから ST-3 の real-smoke または #7 で確定する**（rule 11 の外部ブロッカー扱い）。docs 簡易サンプル（5 section）は all_pairs mode のためこの経路を通らず、影響を受けない。unit test は `min_dense_score=0.0` で retrieval 経路を通している（閾値挙動自体は未検証）。

> CR-002 反映（同一 section 内矛盾と recall）: 現 claim 経路は `allow_same_section_claim_pair`（`core.py:2512` 付近、**既定 True**）で同一 section 内 claim pair を候補にできる。GPT 当初案の `allow_same_section_pair = false` はこれを検出対象外にし、「recall 維持」と衝突する。**default を `true` に変更し、同一 section 内矛盾を scope に含める**。この場合 A/B が同一 section になる judge 入力と conflict_id の扱いを定義する（conflict_id は section_pair_id だが A==B の場合の安定 ID 規則を決める）。同一 section 内を scope 外にするなら、recall 劣化として完了条件に明記する（人間判断点）。
>
> CR-002 実装注意（self-pair 落ち防止・GPT 追加）: `allow_same_section_pair = true` の場合、self-pair（A==A）を候補に含める。通常の組み合わせ実装（i<j）も retrieval（自分自身は近傍に出ない）も self-pair を自然には含めないため、**all-pairs 経路・retrieval+cap 経路の両方で self-pair を明示的に候補生成へ注入する**。これを怠ると「設定は true だが同一 section 内矛盾を実際は見ない」事故になる。ただし同一 section pair は **1 件だけ生成し、重複 judge しない**。

> CR-008 反映（self-pair 注入の徹底・CODEX 追加）: 上記の self-pair 注入は all-pairs だけでなく **retrieval + cap 経路でも必須**。各 section について `allow_same_section_pair = true` なら self-pair を 1 件、候補集合へ無条件で加える（retrieval 近傍に出ないため、cap とは独立に注入する）。

> CR-001 反映（cap 外 false negative の防止）: large docs で retrieval + cap により候補 section pair を絞ると、**既存 Conflict Review Item が参照する section_pair が cap 外に落ちただけ**で候補に現れない場合がある。これを「矛盾が消えた」と扱い auto-dismiss すると false negative になる。section_pair 経路に「absence が信頼できる条件」を定義する（claim 経路の `_conflict_pair_absence_is_reliable` 相当）。最低限:
> - 既存 Conflict Review Item が参照する section_pair は、いずれかの source hash が変化した run で **候補 rank / cap と無関係に必ず再評価対象へ強制投入する**。
> - auto-dismiss を許可するのは、(a) 当該 section_pair を実際に judge して非矛盾と判定した場合、または (b) all-pairs 実行で当該 pair の absence が信頼できる場合のみ。cap truncation による absence では auto-dismiss しない。
> - 候補 truncation の diagnostics（cap で落とした pair 数）と「absence reliable」判定を section_pair 経路で emit する。
>
> CR-001 実装注意（candidate 集合の定義・GPT 追加）: judge にかける対象集合を次で明確に分ける。union 後にまとめて cap をかけると既存 conflict pair が落ちるので禁止。
> ```text
> judge_targets =
>   ranked_new_candidate_pairs_limited_by_cap   # global_pair_cap / section_pair_top_k 対象
>   ∪ existing_conflict_pairs_requiring_recheck  # cap / top_k の対象外（exempt）
> ```
> `existing_conflict_pairs_requiring_recheck` は `global_pair_cap` / `section_pair_top_k` の **対象外**として扱い、cap 適用後に union する（cap を union 後にかけ直さない）。
>
> absence reliable predicate（確定）:
> ```text
> absence を信頼してよい（auto-dismiss 許可）:
>   all-pairs 実行 かつ
>   candidate generation / judge が success かつ
>   truncation なし かつ
>   当該 section pair が評価対象に含まれていなかった
>
> absence を信頼しない（auto-dismiss しない）:
>   retrieval + cap 実行 / truncation あり / backend failed /
>   partial_success / disabled / timeout
> ```
> ただし absence 判定に頼るより、**既存 conflict の section_pair は source hash 変化時に cap 対象外で必ず再評価する**方が安全。これを第一手段とする。

> CR-009 反映（section 削除 / rename の扱い・CODEX 追加）: absence reliable（cap 外 false negative 防止）とは別に、**section が消えるケース**の方針を section_pair 化後も定義する。既存テストに dangling ref の auto-dismiss 系がある（`tests/test_spec_core.py` の `test_t_conflict_source_update_auto_dismisses_heading_slug_change_dangling_ref` / `..._deleted_section_dangling_ref`）。section_pair 経路では次を区別する。
> - **section 削除**: 当該 section が source から消えた場合、その section を含む既存 conflict pair は auto-dismiss 可能（dangling ref）。
> - **heading slug の rename**: 旧 section id が消えても内容は残っているので「pair 不在 → 矛盾解消」ではなく、**source ref / section id の変化（再マップ対象）**として扱い、新 section id で再評価する。rename を削除と同一視して auto-dismiss しない。

#### candidate は永続化しない（A 案・確定 / 旧 artifact 名は撤回）

section_pair candidate は **永続化せず、full / changed run で毎回 in-memory 再計算**する（GPT・Human 合意 A 案）。旧 `conflict_candidate_pairs.jsonl` は #4 で根絶し、**新 artifact は作らない**。以前確定した `section_conflict_candidate_pairs.jsonl` は撤回（外部設計書反映前なので実装前の設計修正で済む）。

理由: section_pair candidate は LLM 非使用の retrieval/rank で軽量に再生成でき、再評価に必要な状態は既存 artifact から復元できる（現在の sections = section_manifest、既存 conflict と recheck 対象 = `conflict_review_items.json` の `section_pair` + `base_source_hashes`）。candidate を永続化すると schema / state file / fingerprint / stale 判定 / disabled-failed read guard / §4.1 契約 / E2E が再び必要になり、今回消したい複雑性に逆行する。**GPT-01 の stale-read 問題は「artifact が存在するから起きる」ので、永続化しない方が構造的に安全**。

ただし次の 2 条件を必須とする。

1. **no-change incremental では candidate generation も section_pair judge も skip する**（毎回再計算しない）。skip 判定材料: section_manifest の section hash / `conflict_review_items` の `base_source_hashes` / config fingerprint / Purpose・Core Concept hash。これらが不変なら前回の `conflict_review_items.json` を維持し、candidate 再生成も judge もしない。source hash が変わった run だけ candidate を再生成し、existing_conflict recheck pair を cap 対象外で union して judge する。
2. candidate を永続化しない代わりに、**candidate generation の diagnostics を `CoreResult` / `core_progress` に出す**: `status` / `mode`(all_pairs|retrieval_cap) / `section_count` / `candidate_count_before_cap` / `candidate_count_after_cap` / `self_pair_count` / `recheck_pair_count` / `truncated_pair_count` / `absence_reliable` / `origin_counts`(all_pairs/section_pair_retrieval/existing_conflict_recheck)。これで永続ログが無くても性能・安全性・cap 外 false negative を監査できる。

#### 検証条件

- 既知矛盾（METRICS で安定検出されている session-termination ↔ session-retention-policy 等）を section_pair judge が検出することを確認。
- recall 維持の比較（claim 多段時の検出件数と一致 or 上回る）。

#### 完了条件

section_pair judge が既知矛盾を検出し、conflict_points を返す。recall が claim 多段時から劣化しない。

#### 残作業

- ST-1（judge コア）/ ST-2（候補生成）実装済（additive・未配線）。残りは ST-3 の core.py 配線。
- ST-3 で: candidate 非永続(A案)・no-change incremental skip・candidate diagnostics を CoreResult/core_progress に出す。
- Purpose / Core Concept grounding を judge 入力に含める実装（CR-004。ST-3 配線で wrapper を通す）。
- cap truncation 時の「absence reliable」判定と既存 pair 強制再評価の実装（CR-001。ST-2 で recheck union 実装済、ST-3 で absence_reliable を core 側に配線）。

#### 依存 / scope 外

#3（conflict_review_item 再設計）と密結合。並列化（#6）は本 sub task の後。候補生成方式・config 値・CR-001/002/004 はすべて確定済（残るのは ST-3 配線のみ）。

### #3 T-conflict-item-redesign: conflict_review_item を section_pair 単位へ再設計

**状態**: 未着手
**担当**: Human（契約判断）+ 実装担当
**最終更新**: 2026-05-30

#### 背景

現 `conflict_review_item` は claim-pair 前提（`conflict_id` = claim pair 由来、`claims` = claim_text + evidence_span、`spec_claim_pair`）。section_pair judge に合わせて再設計する。

#### 真因 / 対応方針

- `conflict_id` = section_pair_id（section A / B の安定 ID から導出）。
- `source_refs` = section A / B。
- `conflict_points[]` を保持（表示の細かさを担保）。
- dismiss / reopen は section_pair 単位。reopen トリガーは従来どおり section hash 変化ベース（変わるのは「何を 1 単位として dismiss/track するか」= conflict_id の同一性が claim pair → section pair になる点。reopen 検知の仕組み自体は不変）。

#### section_pair_id の canonical hash 規則（確定）

順序揺れと self-pair の両方に対応するため、canonical 化してから hash する。

```text
section_pair_id = "section_pair:sha256:v1:" + hash(
  identity_version,
  canonical_pair,
)

canonical_pair:
  A != B → [left_section_id, right_section_id] を辞書順 sort
  A == B → [A, A]
```

例:
```text
section_pair_id("checkout#approval", "automation#approval")
  = section_pair:sha256:v1:<hash(["automation#approval","checkout#approval"])>
section_pair_id("session-policy", "session-policy")
  = section_pair:sha256:v1:<hash(["session-policy","session-policy"])>
```

> CR-003 反映（既存表示契約の置き換えを完全定義）: 現 conflict_review_item は `why_llm_cannot_decide`、人間向け `claims[]` 要約、`recommended_next_action` を持ち、`/spec-inject` / `/spec-realign` の pending conflict 展開がこれらを使って人間へ説明している。`conflict_points[]` を足すだけでは既存の説明契約とずれる。**section_pair 版 conflict_review_item の完全 schema を実装前に確定する**。少なくとも次を定義する。
> - `conflict_id`（= section_pair_id）
> - `source_refs[]`（section A / B、各 source_ref + hash）
> - `conflict_points[]`（`left_excerpt` / `right_excerpt` / `why_conflicting` / `severity`）
> - item-level `why_conflicting`（summary）
> - item-level `why_llm_cannot_decide`
> - 人間向け summary（旧 `claims[]` 要約の代替。section_pair でどう出すか）
> - `recommended_next_action`
> - `base_source_hashes[]`（reopen 失効判定用）
> - `status`（pending / dismissed）と `resolution`（dismiss 時）
>
> あわせて `/spec-inject` / `/spec-realign` の pending conflict 展開（テンプレと CLI 出力）を新 schema に合わせて更新対象に含める（#5 で docs、本 sub task で CLI 出力構造）。

確定 schema（旧 `claims[]` は残さない。代替は `conflict_points[]` + `why_conflicting`）:

```json
{
  "conflict_id": "section_pair:sha256:v1:...",
  "status": "pending",
  "severity": "medium",
  "source_refs": [
    {
      "source_section_id": "...",
      "source_ref": "...",
      "source_hash": "sha256:...",
      "heading_path": ["..."]
    }
  ],
  "section_pair": {
    "section_pair_id": "section_pair:sha256:v1:...",
    "left_section_id": "...",
    "right_section_id": "...",
    "candidate_origin": "all_pairs|section_pair_retrieval|existing_conflict_recheck"
  },
  "conflict_points": [
    {
      "left_excerpt": "...",
      "right_excerpt": "...",
      "why_conflicting": "...",
      "severity": "medium"
    }
  ],
  "why_conflicting": "item-level summary",
  "why_llm_cannot_decide": "Existing evidence does not establish a safe priority.",
  "recommended_next_action": "Ask a human to decide this conflict.",
  "base_source_hashes": [
    { "source_ref": "...", "hash": "sha256:..." }
  ],
  "valid_scope": "section_pair",
  "stale_dismissal": false,
  "created_at": "...",
  "updated_at": "..."
}
```

#### 外部契約への影響（**section_pair 化で承認済み**）

次の 3 つが外部から見て変わる。方針は section_pair 化で承認済み（GPT・Human）。すべて確定済。

1. candidate artifact: 旧 `conflict_candidate_pairs.jsonl` は #4 で根絶し、**新 candidate artifact は作らない（A案・非永続）**。candidate は毎回 in-memory 再計算。
2. Agent に出す conflict の根拠粒度: section pair + `conflict_points[]` で提示。
3. dismiss / reopen の単位: claim pair → section pair。同じ section ペア内に複数矛盾があっても個別 dismiss は section pair 単位に粗くなる（conflict_points で表示は細かく維持）。

人間への矛盾「提示」品質への影響は限定的（judge が conflict_points を返せば section_pair でも十分詳しく出せる）。影響が大きいのは「管理単位（dismiss/reopen の粒度）」。今回用途（LLM agent に矛盾を見落とさせない / 人間に判断材料を出す）では section_pair で十分という判断（GPT・Claude 合意）。

#### 検証条件

- section_pair 単位の dismiss → 永続化 → 該当 section の hash 変化 → section_pair judge で再判定 → reopen、の一巡を test と production E2E で確認。（CR-010 反映: triage 根絶 TODO のため「再 triage」表現を使わない。reopen の再判定は section_pair judge が担う）

#### 完了条件

section_pair 単位の dismiss/reopen が一巡し、conflict_points が表示できる。

#### 残作業

- section_pair 版 conflict_review_item の完全 schema 確定（CR-003 必須 8 項目）。
- `/spec-inject` / `/spec-realign` の pending conflict 展開（CLI 出力構造）を新 schema へ更新。
- 外部契約変更の人間承認、test。

#### 依存 / scope 外

#2 と密結合。外部設計書（docs）反映は #5。CLI 出力構造の更新は本 sub task。

### #4 T-claim-pipeline-eradicate: claim-based pipeline を根絶（opt-in でも残さない）

**状態**: 未着手
**担当**: 実装担当（CODEX 委譲時はルール 15 / ルール 20 厳守）
**最終更新**: 2026-05-30

#### 背景

claim 単位を opt-in mode として残すと、`spec_claims` スキーマ / claim_uid identity / claim_retrieval / triage / claim-based conflict_id / claim 単位 dismiss/reopen E2E / artifact 互換 / config 分岐 / 外部仕様の二重契約をすべて維持する必要があり、設計・test・契約が二重化する。今回用途では不要（GPT・Claude 合意で完全削除寄り）。

#### 真因 / 対応方針

CLAUDE.md ルール 15（廃止 = 根絶）に従い、次を grep で網羅して削除する。stub / disabled / コメントアウト / opt-in / fallback を残さない。

- artifact: `spec_claims.jsonl` / `conflict_candidate_pairs.jsonl` / それらの state file を根絶（A案で candidate は非永続のため代替 artifact は作らない）
- 処理: `spec_claims` 生成（`core.py` L1919 付近）、`claim_retrieval`、`conflict_review.select_conflict_judging_pairs`（L336、triage 選抜）
- 設定 key: `[section_metadata].enabled` 参照を含む `_spec_claims_enabled`（L2872-2876）。GPT-02 バグ（`section_metadata.enabled`（既定 True）`or` `conflict_candidate_detection.enabled` で常時 True、`or` のため off にできない）はこの関数の削除で消滅。矛盾検出の on/off は `conflict_candidate_detection.enabled` を唯一の gate にする。
- 参照: import / call / 型注釈
- test / fixture: claim_uid 単位 dismiss/reopen の test
- docs: 外部設計 / 内部設計 / README / 設定 template / コメント（#5 で実施）

grep 回避の文字列連結 hack を仕込まない（過去 CODEX 事故。memory `feedback_codex_grep_evasion_hack`）。

#### 検証条件

```text
git grep spec_claims
git grep claim_retrieval
git grep select_conflict_judging_pairs
git grep -nE "stub|dormant|legacy|disabled|deprecated|fallback"
```

廃止名 grep が 0 件（**live コード + test に限定**。`doc/**` / `archive/` は除く）。残 hit は目的のある記述か削除漏れかを分類。

> CR-005 反映（#4 と #5 の循環解消）: 当初は #4 の grep 0 対象に「active docs」を含めていたが、docs は #5（#2〜#4 後に実施）で書き換わるまで claim 用語を残すため、#4 完了時点で active docs の grep 0 は満たせず順序矛盾になる。**#4 の grep 0 は live コード（`spec_anchor/`）+ test（`tests/`）に限定する**。`doc/EXTERNAL_DESIGN.ja.md` 等の active docs からの claim 用語根絶は **#5 の完了条件**に移す。#5 完了時に docs を含めた全体 grep 0 を確認する。

#### 完了条件

claim-based pipeline が live コード（`spec_anchor/`）・test（`tests/`）から根絶され、矛盾検出は section_pair judge 単段のみ。`pytest --skip-external` 回帰なし。active docs の claim 用語根絶は #5 の完了条件（本 sub task の完了判定には docs を含めない）。

#### 残作業

- 根絶実装、grep 検証、test。

#### 依存 / scope 外

#2 / #3 で section_pair 検出器が機能してから着手（受け皿が無い状態で claim 経路を消すと検出が消える）。

### #5 T-contract-realign: 外部契約 / 内部設計 / テンプレ / 配置表を整合

**状態**: 未着手
**担当**: Human レビュー + 実装担当
**最終更新**: 2026-05-30

#### 背景

検出経路の作り直しに伴い、外部設計書・外部仕様 draft・内部設計書・コマンドテンプレ・`§4.1 保持物の物理配置`表を新契約へ整合する。

#### 対応方針（CLAUDE.md ルール 20）

- **実装の監査が完了してから** docs に反映する（実装と仕様反映を同じ task でやらせない。phantom 仕様の混入を防ぐ）。
- docs に追加してよいのは実装済みかつ test で観測可能な挙動だけ。code / test / TODO に根拠の無い field・status・reason・route・config key を docs に書かない。
- 外部設計書はソースコード未読の読者に通じる言葉で書く（ルール 14）。

#### 検証条件

doc 記載の field / status / config key が実 emit / 実コードと突合して一致（phantom フィールドが無い）。

#### 完了条件

全 docs が新検出経路と整合し、§4.1 配置表に新 artifact が反映され、廃止 artifact が表から消えている。**active contract docs の claim 用語 grep が 0 件**（CR-005 で #4 から移管した docs 根絶をここで確認）。

> CR-007 反映（grep scope の明確化）: grep 0 件の対象は **active contract docs に限定**する = `doc/EXTERNAL_DESIGN.ja.md` / `doc/EXTERNAL_SPEC_DRAFT.ja.md` / `doc/DESIGN.ja.md` / `README*` / `.claude/commands/**` / `spec_anchor/templates/**`。**`doc/TODO/**`（本 TODO 自身・完了済み TODO 含む）と `archive/**` と履歴系 docs は除外**する（これらには経緯記録として claim 用語が残るため、文字通りの全体 0 件は完了不能になる）。

人間レビュー OK。

#### 残作業

- docs 反映、§4.1 表更新、人間レビュー。

#### 依存 / scope 外

#2〜#4 の実装監査完了が前提。

### #6 T-judge-concurrency: section_pair judge の並列化（最後）

**状態**: 未着手
**担当**: 実装担当
**最終更新**: 2026-05-30

#### 背景

並列化は他ステージでも必要だが、検出器の構造を確定させてから入れる（過剰な並列構造を温存しないため、最後に回す）。

#### 対応方針

**#2 の section_pair judge は最初は逐次で実装する**（構造と recall を先に確定するため）。並列化は本 sub task で最後に入れる。

> CR-011 反映（並列化の意図明確化・CODEX 追加）: 既存 `conflict_review.py:522` 付近は既に `ThreadPoolExecutor(max_workers=concurrency)` を使っている。#6 は新インフラの追加ではなく、**新 section_pair judge のペア単位呼び出しに、この既存 ThreadPoolExecutor パターンを再利用して並列化を入れる**こと。順序は「#2 で逐次実装 → #6 で並列化を後付け」。最初から並列で作らないのは、過剰な並列構造を温存せず構造確定を優先するため。

#### 完了条件

並列化後も recall 維持、wall time 短縮、`pytest --skip-external` 回帰なし。

#### 残作業

- 並列化実装、性能再測定、test。

#### 依存 / scope 外

#2〜#4 完了後。

### #7 T-perf-measure: docs 簡易サンプルで per-stage 計測を取り直す

**状態**: 未着手
**担当**: 計測担当
**最終更新**: 2026-05-30

#### 背景

検出経路を claim 多段（spec_claims / claim_retrieval / triage / conflict_evaluation）から section_pair 単段へ変えるため、`doc/性能測定/METRICS.md` の per-stage 計測がステージ構成と乖離する。簡易サンプル（`docs/spec/{sample.md, 25_*, 27_*, 29_*, 30_*}.md`）は性能測定の主対象であり、ここが大幅に遅くなる変更は不可。

#### 対応方針

- 新ステージ構成（section_metadata / section_pair_candidate_generation / section_pair_judge / chapter_anchors / related_sections / section_collection_upsert）の per-stage wall / calls / token を計測し METRICS.md に記録。
- claim 多段時の baseline（METRICS.md 既存回。例: 第11回 5 section / 第9回 56 section）と比較し、簡易サンプルの総 wall が大幅悪化しないことを確認。目標は短縮。
- **full / rebuild と no-change incremental の両方を測る**（A案の前提条件確認）: (1) full/rebuild = candidate generation + section_pair judge の wall、(2) no-change incremental = candidate generation も judge も走らず ほぼ skip されること。
- 並列化（#6）前後で 2 点測る。

#### 検証条件

簡易サンプルでの `spec-anchor core` 総 wall と per-stage wall を記録し、claim 多段 baseline と並べた比較表を METRICS.md に追加。

#### 完了条件

簡易サンプル総 wall が claim 多段時より悪化していない（目標短縮）ことが METRICS.md の比較で示される。

#### 残作業

- 実 provider での計測、METRICS.md 比較表追加。

#### 依存 / scope 外

#2〜#6 の検出経路が確定してから測る。#6 並列化の前後で測る。

## 課題全体の完了条件

- 矛盾検出が section_pair conflict judge の単段で動き、claim-based pipeline が根絶されている（grep 0 件。対象 = live コード `spec_anchor/` + test `tests/` + active contract docs。`doc/TODO/**` / `archive/**` / 履歴 docs は除外。CR-005 / CR-007）。
- `conflict_review_item` が section_pair 単位で、dismiss/reopen の一巡が production E2E で確認できる。
- GPT-01（stale artifact）/ GPT-02（enable バグ）が解消されている。
- 実 provider の production E2E で wall time が claim 多段時より短縮され、recall が維持される。
- docs 簡易サンプルの per-stage 計測を取り直し、総 wall が claim 多段時より大幅悪化していない（目標短縮）ことを METRICS.md の比較表で示している。
- 全 docs / §4.1 配置表が新契約と整合し、人間レビュー OK。
- production E2E PASS + 人間レビュー OK までは完了扱いにしない（AGENTS.md Completion Ledger ガード / fake・skip-external の pass で代替しない）。

## 依存 / scope 外

- 本課題は `TODO_conflict_resolution_simplification.ja.md` の production E2E ゲートを **supersede** する（検出パイプライン作り直しが先決と判明したため。旧 TODO 側に supersede メモあり）。
- 旧 TODO で確定済みの「矛盾 = 注入情報（解決ゲート廃止）」「pending/dismissed の 2 値」「dismiss CLI が唯一の却下口」「freshness 簡素化」は維持する。本課題は検出 **経路** の作り直しであり、矛盾の **扱い** の方針は変えない。
- 候補 section ペア選抜方式（#2）と外部契約 3 点（#3）は section_pair 化で承認済み。candidate 非永続(A案)・no-change skip・config 初期値・section_pair_id 規則・absence reliable predicate・完全 schema はすべて本 TODO 内に確定記載済み（末尾「人間判断点」参照）。実装は本 TODO の確定値を正として進められる状態。

## 設計レビュー指摘と disposition（2026-05-30 CODEX 監査）

CODEX が本 TODO（実装着手前の設計）を監査して挙げた 6 指摘。全件採用し、対象 sub task の本文へ反映済み（CLAUDE.md ルール 9）。

| ID | 重要度 | 対象 | 指摘要約 | 判定 | 対応（反映先） |
|---|---|---|---|---|---|
| CR-001 | High | #2 / #3 | large docs で retrieval + cap により候補を切る設計で、cap 外に落ちた既存 conflict を「矛盾が消えた」と auto-dismiss すると false negative。absence を信頼してよい条件が未定義。 | 採用 | #2「候補 section ペア選抜方式」に CR-001 反映ブロックを追加。既存 item の section_pair は source hash 変化時に cap 無関係で強制再評価、auto-dismiss は judge 済み非矛盾 or all-pairs absence のみ許可、truncation diagnostics を emit。 |
| CR-002 | High | #2 | `allow_same_section_pair = false` は同一 section 内矛盾を検出対象外にし、claim 経路（`allow_same_section_claim_pair` 既定 True）と比べ recall 劣化。 | 採用 | #2 config 既定を `allow_same_section_pair = true` に変更。A==B の judge 入力と conflict_id 規則を定義。scope 外にするなら recall 劣化として完了条件に明記（人間判断点）。 |
| CR-003 | High | #3 / inject / realign | 新 item に `conflict_points[]` はあるが、既存表示契約の `why_llm_cannot_decide` / 人間向け `claims[]` 要約 / `recommended_next_action` の置き換えが未定義。 | 採用 | #3「真因 / 対応方針」に section_pair 版 conflict_review_item の完全 schema（必須 8 項目）を追加。inject / realign の pending 展開も更新対象に明記。 |
| CR-004 | High | #2 | judge 入力が section A/B 本文中心で、Purpose / Core Concept grounding を含めるか未定義。現コードは渡しており、外すと過剰検出。 | 採用 | #2「真因 / 対応方針」に CR-004 反映を追加。`_EvidenceGroundedConflictJudge`（`core.py:4315`）同様に Purpose / Core Concept grounding を必須入力にする（外す選択肢は不採用）。 |
| CR-005 | Medium | #4 / #5 | #4 が active docs まで grep 0 を要求する一方 #5 が #2〜#4 後に docs 反映で、完了条件と依存が循環。 | 採用 | #4 の grep 0 を live コード + test に限定。docs の claim 用語根絶を #5 完了条件へ移管し、#5 で docs 含む全体 grep 0 を確認。 |
| CR-006 | Low | #1 | #1 が「status ガードなし」と書くが、現 `core.py` には既に `conflict_detection_reliable` read ガードがある（当セッションで追加）。TODO が現コードとずれ。 | 採用（既対応） | #1 背景に CR-006 反映を追加し、状態を「実装済み・テスト未検証」へ更新。read ガードは当セッションで追加済み、auto-dismiss ガードは既存。残は test 観測点修正 + pytest。 |
| CR-007 | High | #5 / 課題完了条件 | 「docs を含めた全体 grep 0 件」が曖昧。`doc/TODO/**`・完了済み TODO・履歴 docs には claim 用語が残るので文字通りだと完了不能。 | 採用 | #5 完了条件と課題全体完了条件の grep 0 対象を **active contract docs（EXTERNAL_DESIGN / EXTERNAL_SPEC_DRAFT / DESIGN / README / .claude/commands / templates）に限定**し、`doc/TODO/**` と `archive/**` と履歴 docs を除外と明記。 |
| CR-008 | High | #2 | `allow_same_section_pair = true` にしたが、all-pairs も retrieval も self-pair を自然に含めない。同一 section 内矛盾を scope に含めるなら self-pair を明示的に候補生成へ注入する必要。 | 採用 | #2 CR-002 注意を強化（CR-008）。all-pairs 経路・retrieval+cap 経路の両方で self-pair（A==A）を cap 独立で 1 件注入する。 |
| CR-009 | Medium | #2 / #3 | absence reliable は cap 外には対応するが、section 削除 / heading slug rename で old section id が消える場合の扱いが未定義。既存に dangling ref auto-dismiss テストあり。 | 採用 | #2 CR-001 領域に CR-009 を追加。section 削除 = auto-dismiss 可、rename = source ref 変化（再マップ・再評価）で auto-dismiss しない、と区別。 |
| CR-010 | Medium | #3 | triage 根絶 TODO なのに #3 検証条件に「再 triage で reopen」が残る。 | 採用 | #3 検証条件の「再 triage」を「section_pair judge で再判定」へ置換。 |
| CR-011 | Low | #6 | #6 が「既存 conflict_review.py の並列化を踏襲」と書くが、現コードは既に ThreadPoolExecutor 使用（`conflict_review.py:522`）。逐次→後付け並列化か再利用かが曖昧。 | 採用 | #6 対応方針を明確化。#2 は逐次実装、#6 で既存 ThreadPoolExecutor パターンを再利用して並列化を後付け、と順序を明記。 |

### 人間判断点（大方針は承認済み。残るは実装前に固定する詳細仕様）

確定済み（人間判断済み・これ以上迷わない）:

- section_pair judge を default にする / claim-based pipeline は opt-in でも残さず廃止 / triage 廃止 / related_sections artifact 非依存 / `conflict_candidate_detection` は default on / dismiss・reopen は section_pair 単位 / Purpose・Core Concept grounding 維持。
- 同一 section 内矛盾は **scope に含める**（`allow_same_section_pair = true`。all-pairs・retrieval 両経路で self-pair A==A を 1 件生成）。
- candidate は **永続化しない（A案）**。毎回 in-memory 再計算。新 candidate artifact は作らない（旧確定の `section_conflict_candidate_pairs.jsonl` は撤回）。ただし no-change incremental では candidate generation / judge を skip し、candidate diagnostics を CoreResult/core_progress に出す。
- `existing_conflict_pairs_requiring_recheck` は cap / top_k の **対象外**で union する。
- conflict_review_item から旧 `claims[]` は廃止し、`conflict_points[]` + `why_conflicting` で代替する。

実装前に最終固定する詳細（本 TODO 内に確定値を記載済み。実装時はこれを正とする）:

1. `section_pair_id` の canonical hash 規則（#3 に確定記載）。
2. absence reliable predicate の exact 条件（#2 CR-001 に確定記載）。
3. section_pair 版 conflict_review_item の完全 schema（#3 に確定 JSON 記載）。
4. `[conflict_candidate_detection]` の初期 config 値（#2 に確定記載: threshold 12 / top_k 8 / cap 80 / min_dense_score 0.55 / same_section true / same_source_file true）。

## sub task / 課題完了時の更新手順

`doc/TODO/TODO_template.ja.md` の「sub task / 課題完了時の更新手順」「archive 手順」に従う。完了時は本ファイルを `doc/TODO/完了済みTODO/TODO_<YYYY-MM-DD>_conflict_detection_pipeline_simplify.ja.md` に `git mv` する。
