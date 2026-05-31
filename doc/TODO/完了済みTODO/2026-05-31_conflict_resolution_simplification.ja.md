# TODO: 矛盾解決を「ゲート」から「注入情報」へ軽量化する

**起票日**: 2026-05-30
**起票者**: Human (設計判断) + Claude main (調査・記述)
**最終更新**: 2026-05-30
**ステータス**: 実装・pytest 検証済み / **production E2E ゲート充足（2026-05-31）**。superseded 先 `TODO_conflict_detection_pipeline_simplify.ja.md` の production E2E 取り直し（現コード = batch+budget-first+#8 後）で、人間 dismiss → reopen / auto 解消 → 削除 / 修正失敗 → pending 維持 を実 provider で確認（証跡 `doc/e2eテスト/evidence/2026-05-31-conflict-auto-resolve-delete/`、計測 `doc/性能測定/METRICS.md` 第13回）。#8 により dismiss=human-only（成功条件 #4）が実装上も真。**CLOSE（2026-05-31 オーナー承認）**: production E2E 取り直し証跡（FINDINGS）と #8 実装差分をレビューし close 判断。成功条件 #1〜#8 を満たす。

> **2026-05-30 supersede メモ**: 本 TODO の残ゲート（production E2E + 人間レビュー）に着手したところ、矛盾の **検出経路**（`spec_claims → claim_retrieval → triage → conflict_evaluation` の claim 多段）が「簡素化」課題内で逆に重くなっていたことが判明した（実 provider 56 section で総 wall 353 秒、`doc/性能測定/METRICS.md` 第9回）。検出経路を section_pair 単段へ切り直すまで production E2E を回しても作り直し前のコードを検証することになるため、**production E2E は後続課題 `doc/TODO/TODO_conflict_detection_pipeline_simplify.ja.md` の完了後に実施する**（このゲートは後続課題へ superseded）。本 TODO で確定済みの方針（矛盾 = 注入情報、pending/dismissed の 2 値、dismiss CLI が唯一の却下口、freshness 簡素化）は維持され、後続課題は検出 **経路** のみを作り直す。

> **2026-05-31 cross-ref メモ（dismiss=human-only の確定）**: 後続課題 `TODO_conflict_detection_pipeline_simplify.ja.md` #8（T-auto-resolve-delete）で、source 更新により自動解消した矛盾を **dismissed 化せず item 削除** へ変更する（auto 解消 2 reason `source_update_recheck_non_pending` / `pair_absent` 対象、human dismiss は現状維持）。これにより本 TODO 成功条件 #4「却下口は `--dismiss-conflict` の 1 つだけ」が**実装上も真**になる（`dismissed` 箱に入るのは人間判断だけ）。本 TODO の close は #8 完了 + production E2E 取り直し（現コードで人間 dismiss→reopen / auto 解消→削除 / 修正失敗→pending 維持 を実 LLM で確認）+ 人間レビューの後。
**関連設計書**: `doc/EXTERNAL_DESIGN.ja.md`（decision payload 節 L801-826 / freshness の `pending_conflict` / §8.7 停止カテゴリ⑤）、`doc/EXTERNAL_SPEC_DRAFT.ja.md`（§2.7 / §4 core 出力 / §5・§6 停止出力 / §6.1.6 inject-conflicts / §11 全体）、`spec_anchor/conflict_review.py`、`spec_anchor/core.py`、`spec_anchor/freshness.py`、`spec_anchor/section_metadata.py`（#7 degraded 源）、`spec_anchor/cli.py`、`tests/e2e/`（#8）、`.claude/commands/spec-inject.md` / `spec-realign.md` / `spec-core.md`、`CLAUDE.md` ルール 4 / ルール 5（完全削除）

## 全体目的

spec-anchor の Conflict Review Item まわりの状態機械と CLI 解決機構（decision payload）を、本システムの本来目的に合わせて根本的に軽量化する。あわせて、この軽量化に伴う freshness status の簡素化（停止理由から `pending_conflict` を外す・`degraded` status を `failed` に畳む = status 4 値→3 値、停止理由 7 値→5 値）も本課題に含める（経緯は末尾「依存 / scope 外」参照）。

### 再フレーミング（本課題の土台）

本システムは **仕様書を修正するシステムではない**。spec-anchor の目的は、LLM が仕様を読まずに作業すること（仕様未読）と、仕様理解のドリフトを防ぐことである。したがって `/spec-inject` は **LLM に正しい仕様コンテキストを注入する手段でしかない**。

この軸に立つと、矛盾の扱いが変わる。

- 現状: 矛盾（pending conflict）は **解決すべきゲート** であり、`/spec-inject` をハードブロックし、CLI で `resolved` にマークするまで先へ進めない。
- 本課題で目指す姿: 矛盾は **注入すべき情報の一種**。課題に関連した矛盾を LLM が抽出・提示した時点で、目的（ドリフト防止・仕様未読防止）は達成されている。spec-anchor のデータモデル上で矛盾を「解決済み」にマークする必要はない。人間が会話で意味を伝えれば議論は進む。

現実の仕様書は矛盾を多数抱えたまま運用され、放置しながら作業が進む。「全矛盾を resolved にしないと inject できない」ハードゲートは、この実務と正面衝突しているため廃止する。

### 想定する新フロー

```text
/spec-inject + 課題 を実行
  ↓
課題に関連した矛盾を含む情報を LLM が抽出・提示し、停止する
  （この時点で矛盾情報は LLM に注入済み = 目的達成）
  ↓
人間が矛盾の意味を伝える
  - 「これはこういう意味だ」= 説明 → 状態は変えず議論継続
  - 「これは矛盾ではない」= 却下 → LLM が CLI で dismiss を永続化
  ↓
議論が進む
```

ここで言う「停止」は、旧ハードブロック（constraints を一切出さず即停止）とは異なる。新方針の停止は **constraints + 矛盾情報を提示してから停止** する。提示そのものが成果物（= 注入完了 = 目的達成）であり、CLI 解決を強制して先へ進ませない旧ゲートとは別物。

#### `/spec-inject` と `/spec-realign` の矛盾時挙動（人間確定）

両コマンドは同じ freshness ゲートを共有する（`spec_anchor/realign.py:5`「validates the gate via `/spec-inject`」）が、**pending conflict は freshness ゲートで止めない**（#1 (b) 確定）。CLI（`inject`）は `pending_conflict_items` / `pending_conflict_count` を情報として返すだけで、`/spec-realign` テンプレートが課題関連 pending を見て答案生成を止める。freshness ゲートが両コマンドに効くのは dirty / watcher / stale / failed 等の保持物起因の停止理由であり、pending はその対象外。矛盾時の到達点は次のとおり確定。

- **`/spec-inject`**: 矛盾の有無に関わらず、制約情報 + 矛盾情報の提示が一旦のゴール（元々答案を出さない）。追加で人間が矛盾を却下することがある程度。
- **`/spec-realign`**:
  - 矛盾なし → 答案生成まで進んでゴール
  - 矛盾あり → `/spec-inject` と同様に制約情報 + 矛盾情報を提示して停止する。答案生成はコマンドでは行わず、人間が会話を継続して進める
  - つまり **矛盾ありの `/spec-realign` は結果的に `/spec-inject` と同じ動き** になる

理由: `/spec-realign` が矛盾未解決のまま答案を生成すると、LLM がどちらの主張に沿うかを暗黙に選んでしまう。提示で一旦留め、人間が矛盾の意味を伝えてから会話で答案へ進む分担にする。

### 成功とみなす条件

1. 矛盾は旧ハードブロック（constraints を出さず即停止）をやめ、constraints + 矛盾情報を提示してから停止する（CLI 解決を強制しない）。`/spec-realign` も矛盾時は同じく提示で停止し、答案生成へ進まない
2. Conflict Review Item の状態は **pending（提示対象）/ dismissed（却下・抑制中）の 2 つだけ**に縮約される
3. `resolved` 系の decision 機構（`prefer_a` / `prefer_b` / `conditional` / `task_scope_resolution`）と pending 系（`needs_source_update` / `defer`）、`unreflected_conflict_resolutions`、重い `--decision-json` / `--decision-file`、`resolved` 状態、Agentic Search の path ④（resolved evidence 抽出）が **根絶**される（CLAUDE.md ルール 15）。Agentic Search は 4 path → 3 path になる
4. 人間の却下インターフェースは **`spec-anchor core --dismiss-conflict <conflict_id> --reason "..."`** の 1 つだけ
5. 却下は永続化され、却下根拠セクションのハッシュが変われば `/spec-core` 再生成で自動失効し、矛盾が再 triage 対象に戻る（再浮上は許容: 「矛盾が解決できない修正をしただけ」と解釈する）
6. コマンドテンプレに「説明 vs 却下の境界」「却下時の CLI 実行＋証跡表示」「実行前確認」が明文化され、LLM が誤って却下を永続化したり、口だけで CLI を叩かなかったりしない
7. 外部設計書・内部設計書・Codex skill・コマンドテンプレが新方針と整合し、CLAUDE.md からルール 4 / ルール 5 が完全削除される（参照していた `doc/DESIGN.ja.md` のルール 4/5 言及も新契約へ修正）
8. （軽量化に伴う freshness 簡素化）freshness status が `degraded` 廃止で 3 値（fresh / blocked / failed）になり、`pending_conflict` が停止理由（`blocking_reasons`）から外れる。`section_metadata` の部分失敗は `failed` として停止する

## 状況サマリー

> 2026-05-30 Codex 更新: 本 TODO は完了扱いしない。#1〜#7 は実装と pytest 検証まで通過、#8 は E2E snapshot の pytest と Codex 自己確認まで通過。未完了範囲は production E2E（実運用経路での `/spec-core` → `/spec-inject` → dismiss → source hash 変更 → 再浮上の一巡）と人間レビューである。
>
> 2026-05-30 Codex 追加修正: CLAUDE 監査後に残っていた同種の grep 回避 / 旧契約残存を修正した。`spec_anchor/conflict_review.py` の旧 field 黙殺 shim を削除し、Conflict Review Item validation は未知 field をエラーにする。tests 内の廃止語 split literal を削除し、README / `doc/EXTERNAL_SPEC_DRAFT.ja.md` / `doc/DESIGN.ja.md` / `agent_doc/外部設計書リライト.md` の旧契約記述を現行契約へ更新した。`tests/test_release_readiness.py::test_t_r05_no_retired_term_split_literal_evasion` を追加し、split literal で廃止語を隠す逃げを pytest で検出する。`doc/TODO/**` と `archive/` を除く live コード・test・active docs で、今回確認した廃止語 grep と split literal grep は 0 件。targeted pytest は 55 passed、`pytest --skip-external` は 686 passed, 22 skipped。production E2E と人間レビューは引き続き未完了。

### Completion Ledger（2026-05-30 Codex）

| scope | 判定 | profile | command / evidence | skip / 未実行理由 | 次アクション |
|---|---|---|---|---|---|
| #1〜#7 実装 + unit / integration pytest | PASS | none / fake / default | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --skip-external -q -p no:cacheprovider` → 686 passed, 22 skipped | 22 skipped は、このコマンドで意図的に除外した外部サービス検証など。skip 件数だけで今回 TODO の残作業を増やさない | production E2E と人間レビューへ進む |
| #8 E2E snapshots | PASS | fake / static E2E | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/e2e/test_user_facing_output.py -q -p no:cacheprovider` → 95 passed | 人間レビューは未実施 | snapshot を人間レビューに出す |
| grep 回避 / 旧契約残存の追加修正 | PASS | none / fake / default + docs grep | `rg -n "decision_options\|inject-conflicts\|inject_conflicts\|resolved_conflict\|usable_conflict_resolution_evidence\|filter_usable_conflict_evidence\|decision-json\|decision-file\|decision_json\|decision_file\|prefer_a\|prefer_b\|conditional\|task_scope_resolution\|needs_source_update\|\\bdefer\\b\|unreflected_conflict_resolutions\|stale_resolution\|possible_conflict\|conflict_pair_max_per_section\|legacy_possible_conflict_mode\|legacy_related_possible_conflict" ...` → 0 件、split literal grep → 0 件、targeted pytest → 55 passed、`tests/test_release_readiness.py::test_t_r05_no_retired_term_split_literal_evasion` → 1 passed、`pytest --skip-external` → 686 passed, 22 skipped | 22 skipped は `--skip-external` による外部依存 test の除外。production E2E はこの行では未実行 | production 経路の一巡を実行する |
| real Qdrant / BGE-M3 外部検証 | PASS | local-service / external | `PATH="$PWD/.venv/bin:$PATH" spec-anchor-setup-system --check-only --qdrant-url http://localhost:6333` → ready、`pytest -m external` → 13 passed, 9 skipped | 9 skipped は今回 TODO の実環境検証不足を埋めるものではない。今回 TODO に記載のない既存外部テストが skip されただけで、production E2E は別 scope として未実行のまま | production 経路の一巡を実行する |
| full pytest | PASS | mixed | `PATH="$PWD/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider` → 698 passed, 9 skipped | 9 skipped の分類とは別に、full pytest の PASS だけでは実運用経路の一巡は未保証 | 本 TODO の残作業は production E2E と人間レビュー |
| #7 `degraded` 残存確認 | PASS | grep 結果の分類 | `rg -n "degraded\|DEGRADED_OPTIONAL_ARTIFACT" spec_anchor tests .claude/commands .codex/skills spec_anchor/templates doc/EXTERNAL_DESIGN.ja.md doc/EXTERNAL_SPEC_DRAFT.ja.md doc/DESIGN.ja.md ...` | freshness の状態値としての `degraded` は残っていない。残存 hit は、別機能の内部状態、旧入力の互換テスト、またはテスト内の確認文言として分類済み | 残作業なし |
| production E2E | NOT-RUN（後続課題へ superseded） | production E2E | 未実行 | 検出経路が claim 多段で重く、section_pair 単段へ切り直す後続課題 `TODO_conflict_detection_pipeline_simplify.ja.md` が先決と判明 | 後続課題の完了後に `/spec-core` → `/spec-inject` → dismiss → source hash 変更 → 再浮上を real provider で通す |
| 人間レビュー | NOT-RUN | human review | 未実施 | オーナーレビュー未実施 | #8-s01〜#8-s07 snapshot と実装差分をレビューする |

| # | sub task ID | 概要 | 状態 | 残作業 | 最終更新 | 完了 commit |
|---|---|---|---|---|---|---|
| 1 | T-conflict-no-block | 矛盾の `/spec-inject` ハードブロックを廃止し、注入情報として提示する経路へ変更 | 実装・pytest済み | production E2E / 人間レビュー | 2026-05-30 | — |
| 2 | T-decision-machinery-removal | `prefer_a`/`prefer_b`/`conditional`/`task_scope_resolution`/`needs_source_update`/`defer` + `unreflected_conflict_resolutions` + `--decision-json`/`--decision-file` を根絶。`resolved` 状態と path ④（resolved evidence 抽出）も廃止 | 実装・grep確認・pytest済み | production E2E / 人間レビュー | 2026-05-30 | — |
| 3 | T-dismiss-cli | `spec-anchor core --dismiss-conflict <id> --reason "..."` を実装（却下記録の唯一の口） | 実装・pytest済み | production E2E / 人間レビュー | 2026-05-30 | — |
| 4 | T-dismiss-staleness-reopen | `base_source_hashes` + ハッシュ失効判定を「却下の失効」へ転用し、失効した dismiss を再オープンする処理を追加 | 実装・pytest済み | production E2E / 人間レビュー | 2026-05-30 | — |
| 5 | T-template-dismiss-flow | コマンドテンプレに却下フロー（説明 vs 却下分離 / 証跡表示 / 実行前確認）と、realign の pending 時答案抑止（#1 (b) で CLI ゲートを置かずテンプレが担う）を記述 | 実装・E2E snapshot pytest済み | 人間レビュー / production E2E | 2026-05-30 | — |
| 6 | T-contract-realign | 外部設計書 + 外部仕様 draft + 内部設計書（`doc/DESIGN.ja.md`）+ Codex skill（`.codex/skills/`）の矛盾解決契約を書き換え、CLAUDE.md ルール 4 / ルール 5 を完全削除（正本は外部設計書 + テンプレ）。Agentic Search を 4 path → 3 path（path ④ 廃止）へ全文書反映 | 実装・grep確認・pytest済み | 人間レビュー / production E2E | 2026-05-30 | — |
| 7 | T-freshness-degraded-fold | `degraded_optional_artifact` を `failed_required_artifact` に畳み `degraded` status を廃止（軸1: 4→3、軸2: degraded 理由除去）。section_metadata 部分失敗も failed 扱い。中間 status 不採用で pending 変更と独立化したため独立 sub task へ昇格（2026-05-30、(い)） | 実装・grep分類・pytest済み | production E2E / 人間レビュー | 2026-05-30 | — |
| 8 | T-e2e-conflict-simplification | 既存 `tests/e2e/` 基盤を再利用し、本 TODO の挙動変更（pending 非ブロック・realign 提示停止・dismiss 一巡・degraded→failed）を E2E シナリオで検証。挙動変更で無効化される既存 snapshot（`#2-s06` 等）の除去・再生成も担う。3 段ゲート（pytest + LLM 自己確認 + 人間レビュー） | pytest + Codex自己確認済み / 未完了 | 人間レビュー / production E2E | 2026-05-30 | — |

本表の `状態` と `残作業` を見るだけで「次に何をすべきか」が分かるように維持する。

## sub task 詳細

### #1 T-conflict-no-block: 矛盾のハードブロック廃止 → 注入情報として提示

**状態**: 実装・pytest済み（production E2E / 人間レビュー未実施）
**担当**: 未定（Claude main / CODEX）
**最終更新**: 2026-05-30

#### 背景

現在 `pending_conflict` は freshness の `BLOCKED_REASONS` に含まれ（`spec_anchor/freshness.py:50`）、`/spec-inject` は constraints を生成せず即停止する。これは「矛盾＝解決すべきゲート」という旧モデルの帰結。新モデルでは矛盾は注入情報であり、提示した時点で目的は達成される。多数の矛盾を抱えた実仕様書ではハードゲートが作業を止めてしまう。

#### 対応方針

**重要（CODEX レビュー #1 採用）**: `pending_conflict` を `BLOCKED_REASONS` から外すだけでは新挙動にならない。理由を 3 つ確認済み:

1. `classify_freshness_status`（`freshness.py:298-311`）は末尾が `return BLOCKED`。既知の非 degraded 理由は `BLOCKED_REASONS` に無くても最終 fallthrough で blocked になる。**→ 確定（中間 status 不採用）**: `pending_conflict` を `REASON_PRIORITY` / `KNOWN_REASONS` 自体から外す（停止理由でなくす）ことで、pending は reason 集合に入らず fallthrough に到達しない。専用 status や明示分岐は新設しない
2. `build_freshness_report`（`freshness.py:242-250`）が pending を理由として `reasons` に追加する。pending を「停止理由」から外して「注入すべき情報」として別フィールドへ載せる経路が要る
3. `_hydrate_pending_conflict_items`（`inject.py:64`）は `should_stop` 時のみ pending 本文を hydrate する。新方針では「検索は実行し constraints の根拠も集めるが、矛盾も併せて提示して停止」なので、hydrate を should_stop 以外の提示経路でも行う必要がある

新方針の到達点を整理:

- pending conflict があっても **Agentic Search（inject-search 等）は実行できる**（旧ゲートは search を一切させずに止めていた）。Agent は constraints の根拠を集めつつ、関連 pending conflict も hydrate して提示し、その後停止する
- 「提示して停止」＝ search は走るが、`/spec-realign` の答案生成へは進まない。提示＝注入＝目的達成
- CLI 解決を強制しない

**`/spec-realign` の answer shaping 抑止条件（CODEX レビュー #2 採用、最重要）**: 現 `run_spec_realign`（`realign.py:169-172`）は `run_spec_inject` の結果が stopped（`_is_stopped`）でなければ `_first_answer` 以降の answer shaping へ進む。pending conflict を「blocked にしない／search を実行可能にする」だけにすると、**矛盾ありでも realign が answer shaping へ進み答案を返してしまう**。これは「矛盾あり realign は inject と同じく提示で停止し答案を出さない」という確定方針に反する。

したがって、pending conflict を「search は通すが answer shaping は止める」という **2 段階の意味**で扱う必要がある:

- `inject-search` 等の検索 API: pending があっても実行可能（constraints 根拠収集のため）
- `/spec-realign` の answer shaping: pending があれば進まず、inject 同様に提示で停止する

実装方式は **(b) = 止める/進むの判断を LLM / テンプレート側に倒すで確定（2026-05-30、責務境界 = CLAUDE.md ルール 3）**: pending 時に答案を止めるか進めるかの判断は CLI ではなく Agent / テンプレートが行う。CLI `realign` には pending 専用の答案抑止ゲートを **足さない**（`realign.py` は渡された答案を構造化するだけ。`realign.py:118`「never synthesizes an answer」）。Agent が「止める」と判断した場合はそもそも答案を渡さないので realign は構造化対象を受け取らない。テンプレート `/spec-realign`（#5）が「課題関連の pending conflict があれば提示して停止し答案を生成しない」を LLM へ指示する。CLI 側は `inject` が `pending_conflict_items` / `pending_conflict_count` を情報として返すまで（判断しない）。freshness status は触らない（中間 status は新設しない）。

旧 **(a) 案**（`run_spec_realign` が `pending_conflict_count > 0` で answer shaping をスキップする CLI ゲート）は **撤回**。理由: 「ゲート→注入情報」の本旨と責務境界に照らすと CLI を判断主体にするのは逆行。CLI は課題関連性を判定できず、関連性も止める/進むも LLM の責務（これにより CDX-B の「global pending か課題関連か」という CLI レベルの曖昧さも消える）。

トレードオフ（明示）: 答案抑止は **テンプレ遵守頼み**（#5 の dismiss フローと同じ信頼モデル）になり、CLI ハードゲートは持たない。ただし再フレーミング（L20）で「矛盾を提示した時点で目的＝ドリフト防止は達成」と定義済みで核心は提示。提示されれば暗黙の片側化リスクは大きく下がるため、LLM 側判断で核心目的は守れる。

**freshness に中間 status を新設しない理由**: pending conflict は保持物の鮮度ではなく人間判断待ち情報であり、freshness status に乗せるべき情報ではない。また pending は「確定した矛盾」ではなく「LLM が決着不能としてエスカレーションした矛盾候補」（`evaluate_conflicts` で judge outcome が `needs_human_review` / `unresolved` / `pending` のもの）。答案を抑止する目的は、決着不能な候補を答案生成が暗黙に片側へ倒すのを防ぐこと（その抑止は上記のとおりテンプレ / LLM が担う）。矛盾情報自体（`pending_conflict_items` / `pending_conflict_count`）と検出経路（`/spec-core` → `conflict_review_items.json` → `pending_conflict_items()`）は不変で、inject が情報として返し、Agent が判断に使う。

**CLI JSON と Agent 提示の分離（CODEX レビュー #2 採用）**: 「constraints + 矛盾情報を提示」は **Agent（コマンドテンプレを実行する LLM）の利用者向け出力**であって、CLI が返す JSON ではない。`/spec-inject` CLI は constraints を生成しない契約（`inject.py:37`、`test_spec_inject.py:405` が constraints 不在を確認）。本 sub task の記述は次を分けて書く:

- **CLI 側**: pending conflict を blocked にせず、search API を実行可能にし、pending conflict 本文を JSON で返す（`pending_conflict_items` 等）
- **Agent 側**: CLI の JSON を読み、constraints（自前生成）+ 矛盾情報を利用者向けに整形提示してから停止する（答案は出さない）

#### 検証条件

- 多数の pending conflict があるプロジェクトで、CLI の inject-search 等が **実行でき**、`pending_conflict_items` を JSON で返すこと（旧ゲートのように search を止めないこと）を pytest で確認
- `pending_conflict` が `blocking_reasons` / `REASON_PRIORITY` に含まれず、pending のみ存在する状態で freshness status が blocked にならないことを pytest で確認
- `/spec-inject` / `inject-search` の出力 JSON が、pending 時に freshness を blocking にせず（`status` が blocked でない）、`pending_conflict_items` と `pending_conflict_count` を保持することを **JSON 形状込み**で pytest 確認（両 CLI とも答案抑止はしない）
- `/spec-realign` CLI は pending の有無に関わらず、渡された答案を構造化する（pending 専用の答案抑止ゲートを持たない）ことを pytest 確認。pending 時に「答案を出さない」挙動はテンプレート / LLM 側の責務として E2E（#8-s02 / #8-s03）で確認する
- Agent が constraints + 矛盾情報を提示して停止し、`/spec-realign` では答案を出さないことを E2E で確認（E2E シナリオは #8 に集約: #8-s02 / #8-s03）
- `freshness.py` の理由分類変更（`pending_conflict` を `REASON_PRIORITY` / `KNOWN_REASONS` から除去 + `build_freshness_report`）の影響範囲を pytest で確認。pending を reason 集合から外すため末尾 fallthrough（`return BLOCKED`）の特別対応は不要だが、除去によって他の停止理由の分類が変わらないことを確認する

#### 完了条件

CLI が pending conflict で search を止めず JSON で矛盾本文を返し、Agent が constraints + 矛盾情報を提示してから停止する。`/spec-realign` は矛盾なしで答案まで、矛盾ありで提示停止。

#### 残作業

- ~~pending conflict の status 形状の確定~~ → **確定（2026-05-30）**: 中間 status を新設しない。`pending_conflict` を `blocking_reasons` から外すため、`classify_freshness_status` 末尾 fallthrough の特別対応は不要
- ~~`/spec-realign` の答案抑止の実装方式~~ → **確定（2026-05-30、(b)）**: CLI realign に答案抑止ゲートを足さない。止める/進むの判断はテンプレート / LLM 側（#5）が担い、realign は構造化のみ

#### 依存 / scope 外

- #6（契約・CLAUDE.md ルール 4/5 削除）と密結合。ルール 5「pending conflict を無視して進まない」は本 sub task で前提が変わる。

### #2 T-decision-machinery-removal: decision 機構の根絶

**状態**: 実装・grep確認・pytest済み（production E2E / 人間レビュー未実施）
**担当**: 未定
**最終更新**: 2026-05-30

#### 背景

decision payload（`prefer_a` / `prefer_b` / `conditional` / `dismiss` / `needs_source_update` / `defer` / `task_scope_resolution`）は旧 full GRAG 版の「広範な conflict 承認フロー」由来で、`doc/OLD/EXTERNAL_DESIGN.ja..OLD.md:568` 以降に既存。新モデルでは `dismiss` 以外は不要:

- `prefer_a` / `prefer_b` / `conditional` / `task_scope_resolution`: 会話で意味を伝えれば済む。CLI で resolved にマークする独立価値がない。特に `conditional` は条件の中身が構造化されず（`reason` 自由文のみ）、機械的には `resolved` の別名（`conflict_review.py:27,36`）。
- `needs_source_update` / `defer`: 「直す予定」「保留」を追跡するが、本システムは仕様修正システムではないので追跡しない。人間が外で直し、次の `/spec-core` が再検出する。
- `unreflected_conflict_resolutions`: resolved-but-unreflected 専用通知。resolved を廃止すれば不要。

**`resolved` 状態と path ④ も廃止（人間確定 2026-05-30）**。理由:「SPEC を直さずコンフリクト解決が積み上がると手に負えなくなる」。spec-anchor は仕様修正システムではなく、矛盾の「解決済み」を蓄積する仕組みを持たない。これにより次が連鎖して廃止対象になる:

- `resolved` を `STATUSES` から外す（残る状態は `pending` / `dismissed`）。`conflict_review.py:719` の `updated["status"] = "resolved"` への唯一の到達経路（削除する decision 群）が消えるため、`resolved` は dead になる
- Agentic Search の **path ④（resolved Conflict Review Item からの制約抽出）を廃止**。これにより 4 path → 3 path の契約変更になる（#6 で外部文書反映）
- path ④ の evidence 供給コード `usable_conflict_resolution_evidence` / `resolved_conflict_evidence` / `filter_usable_conflict_evidence`（`conflict_review.py:810-849`）を削除
- `inject.py:602` の `resolved_conflict_review_items` 返却と `inject.py:578` の `status == "resolved"` 分岐を削除
- `evidence_origin` の選択肢から「Conflict Review Item」を外す（残る根拠種別は Purpose / Core Concept / Source Specs）

#### 対応方針（CLAUDE.md ルール 15: 廃止 = 根絶）

`dismiss` を除く decision 値、`--decision-json` / `--decision-file`、`unreflected_conflict_resolutions`、関連する生成・読込・テスト・ドキュメント・設定 template を grep で網羅して削除。

根絶確認:

```text
git grep -nE "prefer_a|prefer_b|conditional|task_scope_resolution|needs_source_update|defer|unreflected_conflict_resolutions|decision-json|decision-file|decision_json"
git grep -nE "resolved_conflict|usable_conflict_resolution_evidence|filter_usable_conflict_evidence|RESOLVED_DECISIONS|resolved_conflict_review_items"
git grep -nE "stub|dormant|legacy|disabled|deprecated|fallback"
```

本 #2 の廃止対象は上記 `resolved_conflict*` 系シンボルと `resolved` という **状態値**。なお dismiss 失効の `stale_resolution` 系シンボルは #4 で `stale_dismissal` へ改名する（resolved 廃止後の誤解防止）。`resolved` 単独 grep の 0 件強制は #4 の改名完了に依存するため、本 #2 単独では強制しない。

**grep 対象をリポジトリ全体へ拡大（CODEX レビュー #5 採用）**: docs / テンプレだけでなく、コードと test にも path ④ / Conflict Review Item evidence 契約が残っている。最低限次を確認し、新契約へ修正する:

- `spec_anchor/realign.py:47-52` の `VALID_EVIDENCE_ORIGINS` から `"Conflict Review Item"` を削除し、`realign.py:345-350` の検証と整合
- `tests/test_conflict_review.py` / `tests/test_responsibility_boundary.py` / `tests/test_release_readiness.py` / `tests/test_setup_scripts.py` / `tests/test_spec_inject.py` / `tests/test_inject_cli_extension.py` / `tests/e2e/test_user_facing_output.py` / `tests/e2e/scenarios.py` 等の Conflict Review Item evidence・`inject-conflicts`・decision 関連 test を新契約へ更新または削除
- `git grep -rn "Conflict Review Item\|inject-conflicts\|inject_conflicts\|VALID_EVIDENCE_ORIGINS"` をリポジトリ全体で実行し、残存を全件処理

#### 検証条件

- **0 件にする語**（`prefer_a` / `prefer_b` / `conditional` / `task_scope_resolution` / `needs_source_update` / `defer` / `unreflected_conflict_resolutions` / `decision-json` / `decision-file` / `resolved_conflict*` / `usable_conflict_resolution_evidence` / `filter_usable_conflict_evidence` / `inject-conflicts` / `inject_conflicts` / `RESOLVED_DECISIONS` / `PENDING_DECISIONS`）が、`doc/TODO/**` と `archive/` を除いた live コード・契約・test で 0 件
- **hit ごとに disposition する語**（全廃ではない）: `Conflict Review Item`（pending / dismissed として概念は残る）、`VALID_EVIDENCE_ORIGINS`（enum 定数は残し "Conflict Review Item" entry のみ除去）。これらを 0 件条件に含めない
- pytest で decision 関連テストを削除後も全体が pass

#### 完了条件

`dismiss` 以外の decision 機構が根絶され、grep 0 件。

#### 残作業

- 実装上の残作業なし。課題全体の残作業は production E2E と人間レビュー（#8）に集約。

#### 依存 / scope 外

- #3（dismiss CLI）と #4（dismiss 失効）が `dismiss` 経路を引き継ぐので、それらと整合させてから削除する。

### #3 T-dismiss-cli: `--dismiss-conflict` フラグ実装

**状態**: 実装・pytest済み（production E2E / 人間レビュー未実施）
**担当**: 未定
**最終更新**: 2026-05-30

#### 背景

却下の永続化には書き込みが必要なため、人間（実際は LLM が代行実行）が却下を伝える口が 1 つ要る。重い `--decision-json` は廃止し、dismiss 専用の軽い口だけ残す。

#### 対応方針

`spec_anchor/cli.py` に追加:

```text
spec-anchor core --dismiss-conflict <conflict_id> --reason "..."
```

- 対象 conflict_id を `dismissed` にし、`base_source_hashes` を却下時点のソースハッシュで記録
- `resolution.decision_origin="human"` 相当の記録（人間却下と将来の自動失効を区別）

**既存 decision 適用条件との整合（CODEX レビュー #4 採用）**: `apply_conflict_decision` を再利用する場合、`_resolution_from_payload`（`conflict_review.py:735`）が `referenced_source_refs` 必須（空だと `raise ValueError`）で、pending→final 遷移には human 認証フィールド（`conflict_review.py:671-680` 付近の final_decisions チェック）も要る。`--dismiss-conflict` CLI は次を満たす:

- 対象 item の `source_refs`（claims の出典）から `referenced_source_refs` を組み立てて payload に渡す
- `--reason` は **必須**（証跡として。空 reason を弾く）
- 対象 conflict_id が `pending` でない（既に dismissed 等）場合はエラーにする
- human 認証フィールドを CLI 側で付与（人間が代行 LLM 経由で却下を指示した、という attestation）

#### 検証条件

- `--dismiss-conflict` 実行で対象 item が `dismissed` になり `base_source_hashes` と `referenced_source_refs` が記録される pytest
- 存在しない conflict_id・非 pending conflict_id・空 reason 指定時のエラー挙動 pytest

#### 完了条件

`--dismiss-conflict` で却下が永続化され、referenced_source_refs / human 認証 / reason 必須の条件を満たす。

#### 残作業

- なし（`--reason` 必須・referenced_source_refs 生成・非 pending エラーは CODEX #4 採用で確定）

#### 依存 / scope 外

- #2 で `--decision-json` を削除する前に、`dismiss` 経路を本フラグへ移行しておく。

### #4 T-dismiss-staleness-reopen: 却下の失効と再オープン

**状態**: 実装・pytest済み（production E2E / 人間レビュー未実施）
**担当**: 未定
**最終更新**: 2026-05-30

#### 背景

却下は永続化するが、却下根拠セクションが修正されたら自動失効し、矛盾を再 triage 対象に戻したい。これは現 `resolved` 用の `stale_resolution` 機構と対称で、既存部品を再利用できる:

- `base_source_hashes`: 既に全 item に保存（`conflict_review.py:482`）
- ハッシュ比較失効判定 `refresh_stale_resolution`（`conflict_review.py:791-806`）は **既に `dismissed` も対象**にしている
- ソース変更で pending を自動 dismiss する `_auto_dismiss_pending_conflict`（`core.py:4467`）の鏡像（自動 un-dismiss）

#### 対応方針

- **概念名とシンボルを改名（確定 2026-05-30、pre-release）**: `stale_resolution` 系 →「却下の失効 = `stale_dismissal`」へ改名する（ルール 15 = 概念名と一致。resolved 廃止後は「resolution」が誤解を招くため）。対象: `stale_resolution` flag / `refresh_stale_resolution`（関数）/ `stale_resolution_count` 等のシンボルと JSON field 名
- `/spec-core` 再生成時、`dismissed` item の base ハッシュが変化していたら却下を破棄して pending に戻し、再 triage 対象に戻す処理を追加（`_auto_dismiss_pending_conflict` の鏡像 1 つ）

**merge 順序の明示（CODEX レビュー #3 採用、最重要）**: 現 `_merge_conflict_items`（`core.py:4380-4392`）は次の順で動く:

1. 既存 item を走査し、`status in {resolved, dismissed}` の pair_key を `resolved_pair_keys`（抑制集合）へ追加
2. 新規 item を走査し、pair_key が抑制集合にあれば `continue` で破棄

この順序のままだと、**古くなった dismissed item が pending へ戻る前に、同一 pair の新規 conflict が抑制集合で破棄される**。再オープンが成立しない。

したがって再オープン処理は **抑制集合を構築する前**（上記ステップ 1 の前、または抑制集合へ追加する条件判定の中）に挿入し、「base ハッシュが変化した dismissed は失効＝抑制集合に入れない（= pending に戻して新規 conflict を通す）」順序にする。`refresh_conflict_resolution_staleness`（`core.py:715`）の呼び出しが現状 merge より後なら、失効判定を merge の抑制集合構築より前へ移すか、merge 内で base ハッシュ変化を直接判定する。実装時にこのデータフロー（staleness 判定 → 抑制集合構築 → 新規破棄）の順序を確定する。

失効粒度の注意（人間了解済み）: 失効はハッシュベース（粗い）。却下根拠セクションへの**矛盾と無関係な軽微な編集でも一旦失効・再 triage が走る**。再 triage がまだ矛盾と判定すれば再浮上（人間が再却下）、矛盾でなければ浮上しない。「意味的に矛盾が残るか」ではなく「セクションが変わったか」で失効する。

#### 検証条件

- 却下後にソース変更 → `/spec-core` 再生成で dismiss が失効し pending に戻る pytest
- ソース無変更なら dismiss が維持される pytest
- 却下後にソース変更し、再 triage が「もう矛盾でない」（既存根拠で解決 = `non_pending_signal`）と判定したケースで、pending に戻らず利用者へ提示されないことを pytest または E2E（#8）で確認
- 改名検証: `git grep -nE "stale_resolution|stale_resolution_count|refresh_stale_resolution"` が `doc/TODO/**`・`archive/` を除く live コード・契約・test で 0 件（`stale_dismissal` 系へ改名済み）

#### 完了条件

却下根拠のハッシュ変化で dismiss が自動失効し、矛盾が再浮上できる。

#### 残作業

- 実装上の残作業なし。失効した dismissed が抑制集合に入る前に pending へ戻ることは pytest で確認済み。課題全体の残作業は production E2E と人間レビュー（#8）に集約。

#### 依存 / scope 外

- triage 自体の精度向上は本課題の scope 外（別途）。

### #5 T-template-dismiss-flow: コマンドテンプレに却下フロー記述

**状態**: 実装・E2E snapshot pytest済み（人間レビュー / production E2E 未実施）
**担当**: 未定
**最終更新**: 2026-05-30

#### 背景

却下永続化の CLI は LLM が代行実行する。テンプレに書けば LLM は実行できるが、テンプレだけでは信頼性が保証されない既知の失敗モードがある。

#### 対応方針（却下フロー 3 失敗モード + realign 答案抑止）

1. **説明 vs 却下の取り違え（最重要）**: 「却下は、人間が明示的に『矛盾ではない / 却下する』意図を示したときのみ。意味の説明・議論継続は却下しない（状態を変えない）」とテンプレで境界を切る
2. **言うだけで実行しない（silent omission）**: 却下時は実行した CLI コマンドと終了結果を会話に出させる（証跡表示を義務化）。例:「却下を永続化しました（`spec-anchor core --dismiss-conflict cnf_001` 実行、結果: dismissed）」
3. **確認なしの即実行**: 却下前に「この矛盾を却下として永続化します。よいですか?」と一度確認してから実行する
4. **`/spec-realign` の pending 時答案抑止（#1 の (b) 確定で本テンプレが担う）**: spec-realign テンプレに「課題関連の pending conflict があれば、矛盾を提示して停止し、答案を生成しない（`spec-anchor realign` を答案つきで呼ばない）」を明記。CLI に答案抑止のハードゲートが無いため、この停止はテンプレ指示で保証する。課題と無関係な pending の提示は Agent が関連性で絞ってよい

`.claude/commands/` 配下と `spec_anchor/templates/.claude/commands/` 配下の両方に反映。

#### 検証条件

- E2E で「人間が説明しただけ」のケースで却下が永続化されないこと、「人間が却下を明示」したケースで CLI が実行され証跡が表示されることを確認（E2E シナリオは #8 に集約: #8-s06）
- spec-realign テンプレに「課題関連 pending では答案を生成しない」指示があり、pending 時に答案が出ないことを E2E（#8-s02 / #8-s03）で確認

#### 完了条件

却下フローがテンプレに明文化され、誤却下・silent omission が起きない。さらに `/spec-realign` テンプレートが、課題関連 pending conflict があるとき答案を生成せず、答案付きの `spec-anchor realign` 呼び出しも行わない（提示で停止する）ことが明文化されている。

#### 残作業

- 実装上の残作業なし。課題全体の残作業は production E2E と人間レビュー（#8）に集約。

#### 依存 / scope 外

- #3（CLI）実装後に記述を確定する。

### #6 T-contract-realign: 外部設計書・外部仕様 draft の整合 + CLAUDE.md ルール 4 / 5 完全削除

**状態**: 実装・grep確認・pytest済み（人間レビュー / production E2E 未実施）
**担当**: 未定
**最終更新**: 2026-05-30

#### 背景

本課題は外部契約（矛盾解決の仕様）を大きく変える。次の 3 文書が新方針と矛盾しており、すべて書き換える。一方だけ直すと文書間の乖離が残る。

**(a) `doc/EXTERNAL_DESIGN.ja.md`**

- decision payload 節（L801-826）
- freshness の `pending_conflict`
- §8.7 停止カテゴリ⑤（人間判断が必要な仕様の衝突）

**(b) `doc/EXTERNAL_SPEC_DRAFT.ja.md`**（外部仕様 draft。`doc/EXTERNAL_DESIGN.ja.md` と同じ契約を別粒度で記述しており、こちらも反映必須）

- §2.7 Conflict Review Item（対象 3 種の定義）
- §4 core 出力: `unreflected_conflict_resolutions[]`（L399）、`--decision-json` / `--decision-file`（L356, L376-377）、「`resolved` に変えない」副作用記述（L474）
- §5 / §6 停止時出力: `pending_conflict` で停止し「各矛盾を解決してから再実行」と促す現記述（L789, L806-817, L967-968）
- §6.1.6 `inject-conflicts`（コマンド完全削除に伴い節ごと削除。L696-712）
- §6.2 4 path 記述（path ④ 廃止で 3 path へ。L723-727）
- §11 Conflict Review Item の外部仕様（§11.1〜11.7 全体: status 遷移 / decision payload 構造 / decision 値の意味 / object 構造 / stale_resolution flag）

**(c) `CLAUDE.md` ルール 4 / ルール 5 → 完全削除（人間確定 2026-05-30）**

ルール 4（Source Specs の生テキストを無制限に混ぜない）とルール 5（pending conflict を無視して進まない）は、`/spec-inject` / `/spec-realign` という **製品のランタイム挙動契約** であり、「spec-anchor を開発する Agent の不変ルール（開発規律）」を集めた CLAUDE.md の対象ではない。両ルールの内容は既に正本 2 箇所に存在する:

- ルール 4 相当: 外部設計書 §3.4（L327/335/343/345）・§8.3、コマンドテンプレ `spec-inject.md:68,135` / `spec-realign.md:62`（+ `spec_anchor/templates/` 側）
- ルール 5 相当: 外部設計書 §3（L307）・§8.7・§11・freshness（L766/1001）、コマンドテンプレの停止カテゴリ⑤

CLAUDE.md にあるのはドリフトしうる 3 つ目のコピー。**ポインタも残さず完全削除**し、正本（外部設計書 + コマンドテンプレ）に一本化する。なおルール 4 の「stale でない resolved Conflict Review Item の根拠」（L83）とルール 5 の resolved / stale_resolution 記述（L93）は、本課題の resolved / path ④ 廃止と直接矛盾するため、いずれにせよ書き換えが必要だった。削除後、**ルール番号は欠番維持で確定（2026-05-30）**: `AGENTS.md`（L7〜L66）が CLAUDE.md のルール 6〜12 を番号で参照しているため、繰り上げると AGENTS.md が壊れる。よってルール 4 / 5 は欠番にし、ルール 6 以降（6〜19）の番号は不変にする。

**(d) path ④ 廃止に伴う Agentic Search 4 path → 3 path の文書反映**

- `doc/EXTERNAL_DESIGN.ja.md` §8.3（L864）/ §8.3.1（L925）: 4 path 記述から path ④（resolved Conflict Review Item）を削除し 3 path へ。`evidence_origin` 選択肢から「Conflict Review Item」を外す。§8.4 `inject-conflicts` 節も削除
- `.claude/commands/spec-inject.md` / `spec-realign.md` および `spec_anchor/templates/.claude/commands/` 配下: 「path ④ resolved Conflict Review Items の確認」節と path 選択指針の表、根拠ルールの「Conflict Review Item は resolved かつ stale でない場合だけ final evidence にできる」記述、`spec-anchor inject-conflicts` 言及を削除
- **Codex skill（CODEX レビュー #1 採用）**: `.codex/skills/spec-anchor/SKILL.md`（L30,35,38,39,66,85）と配布用 `spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md` にも「4 path」「pending conflict で停止」「inject-conflicts」「Conflict Review Item を根拠にできる」が残っている。Codex が実際に読むファイルなので `.claude/commands` 系と同じ内容で新契約へ更新する
- **内部設計書 `doc/DESIGN.ja.md`（CODEX レビュー #4 採用）**: L869（ルール 4 参照）、L871（ルール 5 参照 + `apply_conflict_decision` の resolved/dismissed 遷移）、L1046（ルール 4 の evidence_origin enum を 4 path がカバー）を新契約へ修正。ルール 4/5 を CLAUDE.md から削除するので、これら内部設計書からの「CLAUDE.md ルール 4/5」参照も書き換える（参照先消滅を残さない）
- **コードコメント**: `git grep -nE "CLAUDE.md ルール 4|CLAUDE.md ルール 5|ルール 4|ルール 5"` をリポジトリ全体で実行し、コメント内の参照も処理（参照先消滅を残さない）

#### 対応方針

- (a)(b) から decision payload 機構（`prefer_a`/`prefer_b`/`conditional`/`task_scope_resolution`/`needs_source_update`/`defer`/`--decision-json`/`--decision-file`/`unreflected_conflict_resolutions`）の記述を削除し、「矛盾は constraints と共に提示してから停止（旧ハードブロック廃止）」「却下のみ永続化・ハッシュ失効で再浮上」「`/spec-realign` は矛盾時 inject 同様に提示停止し答案を出さない」の新契約へ書き換え
- status を `pending` / `dismissed` の 2 値へ縮約した記述に統一（§11.2 / §11.3 / §11.4 / §11.6）
- 停止カテゴリ⑤と停止時出力（(a)§8.7 / (b)§5・§6）を「解決を強制する」表現から「提示して停止、却下は任意」へ再定義
- (d) Agentic Search を 4 path → 3 path に書き換え、path ④（resolved Conflict Review Item）と `evidence_origin` の「Conflict Review Item」を全文書（外部設計書 §8.3/§8.3.1 + コマンドテンプレ両所）から削除
- (c) CLAUDE.md ルール 4 / ルール 5 をブロックごと完全削除（ポインタも残さない）。削除前に `git grep -nE "ルール 4|ルール 5"` で他文書からの参照が無いか確認
- いずれもソース未読の読者に通じる言葉で書く（CLAUDE.md ルール 14）

#### 検証条件

- `git grep -nE "decision-json|decision-file|prefer_a|prefer_b|task_scope_resolution|needs_source_update|defer|unreflected_conflict_resolutions"` が `doc/EXTERNAL_DESIGN.ja.md` / `doc/EXTERNAL_SPEC_DRAFT.ja.md` / `CLAUDE.md` で 0 件
- 両外部文書・コマンドテンプレで「4 path」「path ④」「Conflict Review Item を evidence_origin にできる」相当の記述が残っていない（3 path へ更新済み）
- `git grep -nE "ルール 4|ルール 5"` が CLAUDE.md で 0 件（ブロック削除済み）かつ他文書からの「ルール 4/5」参照が無い
- 内部設計書 `doc/DESIGN.ja.md`・Codex skill（`.codex/skills/spec-anchor/SKILL.md` 本体 + `spec_anchor/templates/.codex/skills/` 配布版）・コマンドテンプレ（`.claude/commands/spec-inject.md` / `spec-realign.md` / `spec-core.md` + `spec_anchor/templates/.claude/commands/` 配布版）に旧契約（4 path / decision 機構 / inject-conflicts / 「pending で停止して解決を強制」）が残っていないことを grep 確認（完了条件と同一スコープ）
- `AGENTS.md` が参照する CLAUDE.md ルール番号（6〜12）がルール 4/5 削除後も壊れていないこと（欠番維持を確認。下記「残作業」参照）
- 両外部文書の記述がソース未読の読者に通じるか（ルール 14 のチェック）
- (a) と (b) が同じ契約を矛盾なく記述しているか（粒度差はあってよいが内容の食い違いがないこと）

#### 完了条件

次の全てが新方針と整合し、文書・テンプレ間で矛盾しない: `doc/EXTERNAL_DESIGN.ja.md`、`doc/EXTERNAL_SPEC_DRAFT.ja.md`、内部設計書 `doc/DESIGN.ja.md`、Codex skill 本体 `.codex/skills/spec-anchor/SKILL.md` と配布版 `spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md`、コマンドテンプレ `.claude/commands/spec-inject.md` / `spec-realign.md` と配布版 `spec_anchor/templates/.claude/commands/`。あわせて CLAUDE.md からルール 4 / ルール 5 が削除されている。

#### 残作業

- 実装上の残作業なし。課題全体の残作業は production E2E と人間レビュー（#8）に集約。

#### 依存 / scope 外

- #1〜#5 の設計確定後に契約反映する（実装と契約の乖離を残さない）。

### #7 T-freshness-degraded-fold: degraded status 廃止（freshness status 4値→3値）

**状態**: 実装・grep分類・pytest済み（production E2E / 人間レビュー未実施）
**担当**: 未定（Claude main / CODEX）
**最終更新**: 2026-05-30

#### 背景

本課題は矛盾解決を「停止ゲート」から「注入情報」へ軽量化する過程で freshness status を単純化する（#1: `pending_conflict` を停止理由から除外）。同じ「freshness status を単純化する一連の処理」として `degraded` status も畳む。

`degraded_optional_artifact` の唯一の発生源は `core.py:749` の `section_metadata` のみ。中身は「複数バッチ実行で一部バッチだけ LLM 生成が散発失敗した部分劣化」で transient（再 run で回復）、小規模 spec（単一バッチ）では構造的に発生しない。`classify_freshness_status` が `DEGRADED` を返すのは `reasons == {DEGRADED_OPTIONAL_ARTIFACT}` の 1 分岐のみ。発生が稀で「続行＋警告」と「停止」の差に利用者から見た意味が薄いため `failed_required_artifact` に畳む（人間決定 2026-05-30:「通常は発生しないので failed に纏める」）。

#### 対応方針（ルール 15 根絶）

- `core.py:747-749, 3765-3770`: `section_metadata` の部分失敗を `degraded_optional_artifacts` ではなく `failed_required_artifacts` へ。全失敗・部分失敗を問わず `failed`
- `freshness.py`: `DEGRADED` 定数 / `STATUSES` 集合 / `classify_freshness_status` の degraded 分岐（`reasons == {DEGRADED_OPTIONAL_ARTIFACT}`）/ `can_continue = status in {FRESH, DEGRADED}` → `{FRESH}` / L255・L416・L446・L727 の degraded 分岐 / `DEGRADED_OPTIONAL_ARTIFACT` 定数・`REASON_PRIORITY`・`KNOWN_REASONS` / `build_freshness_report` の `degraded_optional_*` 引数・diagnostics・export を全削除
- freshness status の `degraded` / 4 値記述を 3 値（fresh / blocked / failed）へ更新する文書を全て処理: 外部設計書 `doc/EXTERNAL_DESIGN.ja.md` / 外部仕様 draft `doc/EXTERNAL_SPEC_DRAFT.ja.md` / 内部設計書 `doc/DESIGN.ja.md` / コマンドテンプレ `.claude/commands/`・`spec_anchor/templates/.claude/commands/` / Codex skill `.codex/skills/`・`spec_anchor/templates/.codex/skills/`（degraded 言及があるもの）

#### 検証条件

- `section_metadata` の全失敗・部分失敗いずれでも freshness status が `failed`（停止）になることを pytest で確認
- `git grep "degraded"` / `git grep "DEGRADED_OPTIONAL_ARTIFACT"` をリポジトリ全体（`spec_anchor/` + `doc/` + `.claude/commands/` + `.codex/skills/` + `spec_anchor/templates/` + `tests/`（`tests/e2e/` 含む））で実行。`DEGRADED_OPTIONAL_ARTIFACT` は **`doc/TODO/**` と `archive/` を除いた live コード・契約・test で 0 件**。`degraded` の hit は意図ある記述か削除漏れかをルール 15 に従い個別判定。`doc/TODO/**`（本 TODO 自身を含む計画記述）と `archive/`（履歴）は hit してよく 0 件条件の対象外
- 外部設計書の status 値記述が 3 値で一貫

#### 2026-05-30 `degraded` hit disposition（Codex）

- 既対応: `spec_anchor/freshness.py` と `tests/test_spec_inject.py` / `tests/test_freshness.py` / `tests/test_degraded_fold.py` の `degraded` は、旧 freshness payload / 旧 `degraded_optional_artifact` を `failed_required_artifact` へ畳む互換入力テストと実装。freshness status としての `degraded` は `STATUSES` から除去済み。
- 対象外: `spec_anchor/project_setup.py` と `doc/EXTERNAL_SPEC_DRAFT.ja.md` §setup-system の `degraded` は setup readiness の status。freshness status ではなく、`/spec-inject` / `/spec-realign` の継続判定にも使わない。
- 対象外: `spec_anchor/retrieval_index.py` と `tests/test_retrieval_index.py` の `degraded` は、Qdrant payload の補正処理が一部失敗したことを表す retrieval index 内部の状態。freshness 側では非 success の保持物状態として `failed_required_artifact` に畳まれるため、freshness status `degraded` の残存ではない。
- 対象外: `spec_anchor/section_metadata.py` の `degraded` は検索語抽出フィルタ用の warning/status word。section_metadata の部分失敗を freshness status `degraded` にする経路ではない。
- 対象外: 旧 E2E evidence / session log / archive / TODO 内の `degraded` は履歴記録。live 契約として扱わない。
- 残 TODO: なし。production E2E と人間レビューは #8 / 課題全体の残作業として扱う。

#### 完了条件

`degraded` status が根絶され、`section_metadata` 生成失敗は全て `failed` として停止。freshness status は fresh / blocked / failed の 3 値。外部設計書も 3 値で整合。

#### 依存 / scope 外

- **#1 と同じ `freshness.py` を触る**ため、#1 と協調して実施し freshness.py の二重編集・衝突を避ける（軸1=status の 3 値化と軸2=停止理由の削減を 1 回の整合変更にまとめる）。
- freshness の本格的再設計（status モデル全体の見直し等）は引き続き本課題 scope 外。本 sub task は「degraded を failed に畳む」1 点に限定する。

### #8 T-e2e-conflict-simplification: E2E 検証（既存基盤の再利用）

**状態**: pytest + Codex自己確認済み / 未完了（人間レビュー / production E2E 未実施）
**担当**: 未定（Claude main / CODEX）
**最終更新**: 2026-05-30

#### 背景

本 TODO は freshness ゲートと矛盾処理の**挙動**を変える（#1: pending 非ブロック・提示停止、#7: degraded→failed）。これにより、前回 TODO（`doc/TODO/完了済みTODO/TODO_2026-05-30_slash_command_user_facing_output.ja.md`）で検証済みの既存 snapshot の一部が**嘘になる**:

- `tests/e2e/snapshots/#2-s06_info_degraded_optional_continue.md`: 「degraded は続行」を assert。#7 で degraded status 廃止のため、このシナリオ自体が消滅する（除去対象）
- `tests/e2e/snapshots/#3-s01〜s05_pending_conflict_*.md`: 旧ゲート（pending がブロック）前提で検証済み。#1 で「pending はブロックせず search 実行・提示停止」に変わるため再生成・再検証が要る
- `tests/e2e/snapshots/#4-s01/s02_realign_auto_rerun_*.md`: realign の答案抑止条件が変わるため影響確認が要る

E2E 基盤（`tests/e2e/scenarios.py` / `test_user_facing_output.py` / `forbidden_terms.py` / `snapshots/`）は前回 #11 で構築済みで**現存**するため、本 sub task は基盤を**再利用**し、基盤構築はしない。E2E 検証フロー protocol（CLI → Agent 整形 → snapshot 保存 → 3 段ゲート）は archive 済み前回 TODO の「E2E 検証フロー」章を参照する。

#### 対応方針

- 既存 `tests/e2e/` 基盤を再利用（再構築しない）
- 本 TODO の挙動変更を次のシナリオで検証。3 段ゲート（pytest pass + LLM 自己確認 + 人間レビュー OK）を適用
- 無効化 snapshot の処理: `#2-s06` を `scenarios.py` と live snapshot から除去（degraded 廃止）。新挙動の検証は新規 `#8-s01`〜`#8-s07` で行う。既存 `#3`/`#4` 系 snapshot は旧ゲート挙動（pending がブロックして停止）を assert しておらず新挙動と矛盾しないため再生成は不要（2026-05-30 監査で確認）
- 散在していた E2E 検証条件（#1 の検証条件「realign は答案を出さない」/ #5 の検証条件「却下フロー」/ 課題完了条件の「却下→失効→再浮上の一巡」）を本 sub task に集約する

#### E2E シナリオ（既存 `tests/e2e/` 基盤へ追記）

| シナリオ ID | 概要 | エビデンス | pytest | LLM 自己確認 | 完了 | 人間レビュー |
|---|---|---|---|---|---|---|
| #8-s01 | 多数 pending のプロジェクトで `/spec-inject` が blocked にならず inject-search 実行可・`pending_conflict_items` 返却 | `tests/e2e/snapshots/#8-s01_pending_inject_search_available.md` | `[x]` | `[x]` | `[ ]` | 未実施 |
| #8-s02 | `/spec-realign` テンプレートが pending 時に提示停止し、答案を生成せず答案付き `spec-anchor realign` を呼ばない（CLI ゲートではなくテンプレ/LLM が抑止） | `tests/e2e/snapshots/#8-s02_realign_pending_template_stops_before_answer.md` | `[x]` | `[x]` | `[ ]` | 未実施 |
| #8-s03 | `/spec-inject` と `/spec-realign` が pending 時に同一提示で停止 | `tests/e2e/snapshots/#8-s03_pending_same_presentation.md` | `[x]` | `[x]` | `[ ]` | 未実施 |
| #8-s04 | dismiss CLI 実行 → dismissed → 以後提示されない | `tests/e2e/snapshots/#8-s04_dismiss_cli_suppresses_conflict.md` | `[x]` | `[x]` | `[ ]` | 未実施 |
| #8-s05 | dismissed が source 変更（ハッシュ失効）で再 pending として再浮上（一巡） | `tests/e2e/snapshots/#8-s05_dismissal_reopens_after_source_change.md` | `[x]` | `[x]` | `[ ]` | 未実施 |
| #8-s06 | 「説明だけ」で却下が永続化されない / 「却下明示」で CLI 実行+証跡表示（#5 連動） | `tests/e2e/snapshots/#8-s06_dismiss_requires_explicit_confirmation.md` | `[x]` | `[x]` | `[ ]` | 未実施 |
| #8-s07 | section_metadata 部分失敗で freshness status=failed 停止（#7、旧 `#2-s06` の置換） | `tests/e2e/snapshots/#8-s07_section_metadata_partial_failure_stops.md` | `[x]` | `[x]` | `[ ]` | 未実施 |
| — | production E2E（real provider 経路の一巡） | 未作成 | `[ ]` | `[ ]` | `[ ]` | 未実施 |

`完了` は人間レビュー OK と production E2E 通過後にだけ `[x]` にする。snapshot ファイル名は上表の実ファイル名を正とする。

#### 検証条件

- 上記 #8-s01〜s07 が `pytest tests/e2e/test_user_facing_output.py` で pass
- `#2-s06` が `scenarios.py` / live snapshot から除去され、`git grep "#2-s06"` が `tests/e2e/` の live コードで 0 件（archive 済み前回 TODO の記述は不変）
- `#3-s01〜s05` / `#4-s01/s02` が旧ゲート挙動を assert しておらず新挙動と矛盾しない（再生成不要、2026-05-30 監査で確認）。禁止用語横断チェックも pass

#### 完了条件

本 TODO の挙動変更シナリオ（#8-s01〜s07）が 3 段ゲート（pytest + LLM 自己確認 + 人間レビュー OK）を通過し、エビデンス snapshot が `tests/e2e/snapshots/` に残る。無効化された既存 snapshot が除去・再生成済み。

#### 依存 / scope 外

- #1〜#7 の実装完了に依存（挙動が固まらないと snapshot を取れない）。各 sub task 実装と並行してシナリオ追記してよいが、最終 snapshot は実装確定後に保存する
- 既存基盤（`tests/e2e/`）の構造変更は scope 外。本 sub task はシナリオ追記・snapshot 除去/再生成・3 段ゲート運用に限定する

## 課題全体の完了条件

2026-05-30 現在の判定: 未完了。pytest / decision 機構根絶 grep / `degraded` hit disposition / E2E snapshot 自己確認は通過しているが、production E2E と人間レビューが未実施のため、本 TODO を完了済みへ移動してはいけない。

- すべての sub task（#1〜#8）が完了
- 本 TODO の挙動変更が E2E（#8）の 3 段ゲート（pytest + LLM 自己確認 + 人間レビュー OK）で承認済み
- `dismiss` 以外の decision 機構が grep 0 件で根絶（ルール 15 検証）
- 多数 pending conflict のプロジェクトで `/spec-inject` がブロックされず、却下 → ハッシュ失効 → 再浮上の一巡が E2E で確認できる
- 外部設計書・外部仕様 draft（`EXTERNAL_DESIGN.ja.md` + `EXTERNAL_SPEC_DRAFT.ja.md`）・内部設計書（`doc/DESIGN.ja.md`）・Codex skill（`.codex/skills/spec-anchor/SKILL.md` 本体 + `spec_anchor/templates/.codex/skills/` 配布版）・コマンドテンプレ（`.claude/commands/` + `spec_anchor/templates/.claude/commands/`）・CLAUDE.md が新方針で一貫
- `pytest -q --skip-external` が pass
- production E2E（real provider 経路で `/spec-core` → `/spec-inject` → `spec-anchor core --dismiss-conflict` → source hash 変更 → 再浮上）を実行し、結果を本ファイルの Completion Ledger に追記済み

## 依存 / scope 外

- **freshness status の「単純化」は本課題に含める**（2026-05-30 にスコープへ取り込み、(い)）。本課題は矛盾解決を停止ゲートから注入情報へ軽量化する過程で freshness status を簡素化するため、同じ「freshness status を単純化する一連の処理」を分離しない: (1) `pending_conflict` を `blocking_reasons` から外す（#1）、(2) `degraded_optional_artifact` を `failed_required_artifact` に畳み `degraded` status を廃止（#7）。結果として status は 4 値 → 3 値、停止理由は 7 値 → 5 値になる。
- ただし **freshness の本格的な再設計**（status モデル全体の再構成、freshness 判定アルゴリズムの変更等）は本課題 scope 外。別 TODO として後続で起票・議論する。
- conflict triage 自体の精度は本課題の scope 外。なお過去に possible_conflict の過剰生成事象があったが既に修正・経路廃止済み（現存バグではない）。
- **既存 `status="resolved"` データの後方互換・migration は本課題の scope 外**。`status="resolved"` を含む既存 `.spec-anchor/context/conflict_review_items.json` は考慮しない（リリース前のため）。本課題はリリース前の破壊的契約変更として扱い、実装・テスト・文書は新契約（pending / dismissed の 2 状態）のみを対象にする。

## 未確定事項（実装着手前に人間判断が要る点）

現時点で未解決の未確定事項なし。実装着手前に人間判断が必要だった論点は全て確定し、各 sub task へ反映済み（理由・詳細はそちらを正とする）:

- 矛盾提示時の停止/続行、pending の扱い → #1
- `resolved` 状態・decision 機構・`inject-conflicts` の廃止（人間理由「SPEC を直さず解決が積み上がると手に負えなくなる」含む） → #2
- CLAUDE.md ルール 4 / 5 の完全削除 → #6 (c)
- `degraded` 畳み（4 値→3 値） → #7
- pending 時の止める/進む判断の所在（中間 status 不採用・realign CLI ゲートなし・テンプレ/LLM 側 = (b)） → #1 / #5

## sub task / 課題完了時の更新手順

`doc/TODO/TODO_template.ja.md` の「sub task / 課題完了時の更新手順」「archive 手順」に従う。完了時は本ファイルを `doc/TODO/完了済みTODO/TODO_<YYYY-MM-DD>_conflict_resolution_simplification.ja.md` に `git mv` する。
