# TODO: 矛盾解決を「ゲート」から「注入情報」へ軽量化する

**起票日**: 2026-05-30
**起票者**: Human (設計判断) + Claude main (調査・記述)
**最終更新**: 2026-05-30
**ステータス**: 計画中
**関連設計書**: `doc/EXTERNAL_DESIGN.ja.md`（decision payload 節 L801-826 / freshness の `pending_conflict` / §8.7 停止カテゴリ⑤）、`doc/EXTERNAL_SPEC_DRAFT.ja.md`（§2.7 / §4 core 出力 / §5・§6 停止出力 / §6.1.6 inject-conflicts / §11 全体）、`spec_anchor/conflict_review.py`、`spec_anchor/core.py`、`spec_anchor/freshness.py`、`spec_anchor/cli.py`、`.claude/commands/spec-inject.md` / `spec-realign.md` / `spec-core.md`、`CLAUDE.md` ルール 4 / ルール 5（完全削除）

## 全体目的

spec-anchor の Conflict Review Item まわりの状態機械と CLI 解決機構（decision payload）を、本システムの本来目的に合わせて根本的に軽量化する。

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

両コマンドは同じ freshness ゲートを共有する（`spec_anchor/realign.py:5`「validates the gate via `/spec-inject`」）。本課題の変更はこのゲート経由で両方に効く。矛盾時の到達点は次のとおり確定。

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

## 状況サマリー

| # | sub task ID | 概要 | 状態 | 残作業 | 最終更新 | 完了 commit |
|---|---|---|---|---|---|---|
| 1 | T-conflict-no-block | 矛盾の `/spec-inject` ハードブロックを廃止し、注入情報として提示する経路へ変更 | 未着手 | — | 2026-05-30 | — |
| 2 | T-decision-machinery-removal | `prefer_a`/`prefer_b`/`conditional`/`task_scope_resolution`/`needs_source_update`/`defer` + `unreflected_conflict_resolutions` + `--decision-json`/`--decision-file` を根絶。`resolved` 状態と path ④（resolved evidence 抽出）も廃止 | 未着手 | — | 2026-05-30 | — |
| 3 | T-dismiss-cli | `spec-anchor core --dismiss-conflict <id> --reason "..."` を実装（却下記録の唯一の口） | 未着手 | — | 2026-05-30 | — |
| 4 | T-dismiss-staleness-reopen | `base_source_hashes` + ハッシュ失効判定を「却下の失効」へ転用し、失効した dismiss を再オープンする処理を追加 | 未着手 | — | 2026-05-30 | — |
| 5 | T-template-dismiss-flow | コマンドテンプレに却下フロー（説明 vs 却下分離 / 証跡表示 / 実行前確認）を記述 | 未着手 | — | 2026-05-30 | — |
| 6 | T-contract-realign | 外部設計書 + 外部仕様 draft + 内部設計書（`doc/DESIGN.ja.md`）+ Codex skill（`.codex/skills/`）の矛盾解決契約を書き換え、CLAUDE.md ルール 4 / ルール 5 を完全削除（正本は外部設計書 + テンプレ）。Agentic Search を 4 path → 3 path（path ④ 廃止）へ全文書反映 | 未着手 | — | 2026-05-30 | — |

本表の `状態` と `残作業` を見るだけで「次に何をすべきか」が分かるように維持する。

## sub task 詳細

### #1 T-conflict-no-block: 矛盾のハードブロック廃止 → 注入情報として提示

**状態**: 未着手
**担当**: 未定（Claude main / CODEX）
**最終更新**: 2026-05-30

#### 背景

現在 `pending_conflict` は freshness の `BLOCKED_REASONS` に含まれ（`spec_anchor/freshness.py:50`）、`/spec-inject` は constraints を生成せず即停止する。これは「矛盾＝解決すべきゲート」という旧モデルの帰結。新モデルでは矛盾は注入情報であり、提示した時点で目的は達成される。多数の矛盾を抱えた実仕様書ではハードゲートが作業を止めてしまう。

#### 対応方針

**重要（CODEX レビュー #1 採用）**: `pending_conflict` を `BLOCKED_REASONS` から外すだけでは新挙動にならない。理由を 3 つ確認済み:

1. `classify_freshness_status`（`freshness.py:298-311`）は末尾が `return BLOCKED`。既知の非 degraded 理由は `BLOCKED_REASONS` に無くても最終 fallthrough で blocked になる。`pending_conflict` を別扱い（fresh 継続 or 専用 status）にする明示分岐が要る
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

実装方式の選択肢: (a) `run_spec_realign` が pending conflict の有無を見て answer shaping をスキップし stopped 相当を返す、(b) freshness の status を「search は許すが answer は止める」中間状態として表現する。どちらにするかは pending status 形状の確定（未確定事項参照）と併せて決める。

**CLI JSON と Agent 提示の分離（CODEX レビュー #2 採用）**: 「constraints + 矛盾情報を提示」は **Agent（コマンドテンプレを実行する LLM）の利用者向け出力**であって、CLI が返す JSON ではない。`/spec-inject` CLI は constraints を生成しない契約（`inject.py:37`、`test_spec_inject.py:405` が constraints 不在を確認）。本 sub task の記述は次を分けて書く:

- **CLI 側**: pending conflict を blocked にせず、search API を実行可能にし、pending conflict 本文を JSON で返す（`pending_conflict_items` 等）
- **Agent 側**: CLI の JSON を読み、constraints（自前生成）+ 矛盾情報を利用者向けに整形提示してから停止する（答案は出さない）

#### 検証条件

- 多数の pending conflict があるプロジェクトで、CLI の inject-search 等が **実行でき**、`pending_conflict_items` を JSON で返すこと（旧ゲートのように search を止めないこと）を pytest で確認
- `classify_freshness_status` が pending のみの場合に blocked へ落ちない（新分岐が効く）ことを pytest で確認
- Agent が constraints + 矛盾情報を提示して停止し、`/spec-realign` では答案を出さないことを E2E で確認
- `freshness.py` の理由分類変更（`BLOCKED_REASONS` + 末尾 fallthrough + build_freshness_report）の影響範囲を pytest で確認

#### 完了条件

CLI が pending conflict で search を止めず JSON で矛盾本文を返し、Agent が constraints + 矛盾情報を提示してから停止する。`/spec-realign` は矛盾なしで答案まで、矛盾ありで提示停止。

#### 残作業

- pending conflict の status 形状（fresh 継続 / 「search は許すが answer は止める」中間 status）の確定 → **未確定事項 #5 へ**。`classify_freshness_status` の末尾 fallthrough（`return BLOCKED`）を pending について通さない実装はここに依存する
- `/spec-realign` の answer shaping 抑止（#2）の実装方式確定 → 未確定事項 #5 と連動

#### 依存 / scope 外

- #6（契約・CLAUDE.md ルール 4/5 削除）と密結合。ルール 5「pending conflict を無視して進まない」は本 sub task で前提が変わる。

### #2 T-decision-machinery-removal: decision 機構の根絶

**状態**: 未着手
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

`resolved` 文字列は dismiss 失効（#4）の文脈で `stale_resolution` 等に残る可能性があるため、`resolved` 単独 grep は 0 件を強制しない。廃止対象は上記 `resolved_conflict*` 系シンボルと `resolved` という **状態値**。

**grep 対象をリポジトリ全体へ拡大（CODEX レビュー #5 採用）**: docs / テンプレだけでなく、コードと test にも path ④ / Conflict Review Item evidence 契約が残っている。最低限次を確認し、新契約へ修正する:

- `spec_anchor/realign.py:47-52` の `VALID_EVIDENCE_ORIGINS` から `"Conflict Review Item"` を削除し、`realign.py:345-350` の検証と整合
- `tests/test_conflict_review.py` / `tests/test_responsibility_boundary.py` / `tests/test_release_readiness.py` / `tests/test_setup_scripts.py` / `tests/test_spec_inject.py` / `tests/test_inject_cli_extension.py` / `tests/e2e/test_user_facing_output.py` / `tests/e2e/scenarios.py` 等の Conflict Review Item evidence・`inject-conflicts`・decision 関連 test を新契約へ更新または削除
- `git grep -rn "Conflict Review Item\|inject-conflicts\|inject_conflicts\|VALID_EVIDENCE_ORIGINS"` をリポジトリ全体で実行し、残存を全件処理

#### 検証条件

- 上記 grep が（`dismiss` 関連を除き）0 件
- pytest で decision 関連テストを削除後も全体が pass

#### 完了条件

`dismiss` 以外の decision 機構が根絶され、grep 0 件。

#### 残作業

- `RESOLVED_DECISIONS` / `PENDING_DECISIONS` / `DECISIONS` 定数（`conflict_review.py:18-28`）の整理
- `STATUSES` から `resolved` を外す（`pending` / `dismissed` の 2 状態へ縮約）— **確定済み（2026-05-30）**
- path ④ evidence 供給コード（`conflict_review.py:810-849` / `inject.py:578,602`）の削除
- `inject-conflicts` CLI の完全削除（`cli.py:165,297-298,461-471` / `inject.py:552-606,784`）— **確定済み（2026-05-30、未確定事項 #4）**

#### 依存 / scope 外

- #3（dismiss CLI）と #4（dismiss 失効）が `dismiss` 経路を引き継ぐので、それらと整合させてから削除する。

### #3 T-dismiss-cli: `--dismiss-conflict` フラグ実装

**状態**: 未着手
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

**状態**: 未着手
**担当**: 未定
**最終更新**: 2026-05-30

#### 背景

却下は永続化するが、却下根拠セクションが修正されたら自動失効し、矛盾を再 triage 対象に戻したい。これは現 `resolved` 用の `stale_resolution` 機構と対称で、既存部品を再利用できる:

- `base_source_hashes`: 既に全 item に保存（`conflict_review.py:482`）
- ハッシュ比較失効判定 `refresh_stale_resolution`（`conflict_review.py:791-806`）は **既に `dismissed` も対象**にしている
- ソース変更で pending を自動 dismiss する `_auto_dismiss_pending_conflict`（`core.py:4467`）の鏡像（自動 un-dismiss）

#### 対応方針

- 概念名を `stale_resolution` →「却下の失効（dismiss 失効）」に整理し直す
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

#### 完了条件

却下根拠のハッシュ変化で dismiss が自動失効し、矛盾が再浮上できる。

#### 残作業

- 再 triage が「もう矛盾でない」と判定した場合は浮上しないことの確認（triage 精度は本課題と別関心事）
- staleness 判定 → 抑制集合構築 → 新規破棄の順序を実装時に確定（CODEX #3）。失効した dismissed が抑制集合に入る前に pending へ戻ることを pytest で確認

#### 依存 / scope 外

- triage 自体の精度向上は本課題の scope 外（別途）。

### #5 T-template-dismiss-flow: コマンドテンプレに却下フロー記述

**状態**: 未着手
**担当**: 未定
**最終更新**: 2026-05-30

#### 背景

却下永続化の CLI は LLM が代行実行する。テンプレに書けば LLM は実行できるが、テンプレだけでは信頼性が保証されない既知の失敗モードがある。

#### 対応方針（3 つの失敗モードを潰す記述）

1. **説明 vs 却下の取り違え（最重要）**: 「却下は、人間が明示的に『矛盾ではない / 却下する』意図を示したときのみ。意味の説明・議論継続は却下しない（状態を変えない）」とテンプレで境界を切る
2. **言うだけで実行しない（silent omission）**: 却下時は実行した CLI コマンドと終了結果を会話に出させる（証跡表示を義務化）。例:「却下を永続化しました（`spec-anchor core --dismiss-conflict cnf_001` 実行、結果: dismissed）」
3. **確認なしの即実行**: 却下前に「この矛盾を却下として永続化します。よいですか?」と一度確認してから実行する

`.claude/commands/` 配下と `spec_anchor/templates/.claude/commands/` 配下の両方に反映。

#### 検証条件

- E2E で「人間が説明しただけ」のケースで却下が永続化されないこと、「人間が却下を明示」したケースで CLI が実行され証跡が表示されることを確認

#### 完了条件

却下フローがテンプレに明文化され、誤却下・silent omission が起きない。

#### 残作業

- conflict_id を利用者向け本文に出さず内部保持する現テンプレの扱いを維持しつつ、却下時の証跡には conflict_id を出してよいか（再参照用として現状も末尾に出している）

#### 依存 / scope 外

- #3（CLI）実装後に記述を確定する。

### #6 T-contract-realign: 外部設計書・外部仕様 draft の整合 + CLAUDE.md ルール 4 / 5 完全削除

**状態**: 未着手
**担当**: 未定
**最終更新**: 2026-05-30

#### 背景

本課題は外部契約（矛盾解決の仕様）を大きく変える。次の 3 文書が新方針と矛盾しており、すべて書き換える。一方だけ直すと文書間の乖離が残る。

**(a) `doc/EXTERNAL_DESIGN.ja.md`**

- decision payload 節（L801-826）
- freshness の `pending_conflict`
- §8.7 停止カテゴリ⑤（人間判断が必要な仕様の衝突）

**(b) `doc/EXTERNAL_SPEC_DRAFT.ja.md`**（IDE で開かれている外部仕様 draft。`doc/EXTERNAL_DESIGN.ja.md` と同じ契約を別粒度で記述しており、こちらも反映必須）

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

CLAUDE.md にあるのはドリフトしうる 3 つ目のコピー。**ポインタも残さず完全削除**し、正本（外部設計書 + コマンドテンプレ）に一本化する。なおルール 4 の「stale でない resolved Conflict Review Item の根拠」（L83）とルール 5 の resolved / stale_resolution 記述（L93）は、本課題の resolved / path ④ 廃止と直接矛盾するため、いずれにせよ書き換えが必要だった。削除後、ルール 6 以降の番号は繰り上げず、欠番にするか全体を詰めるかは削除時に判断（他文書からの「ルール N」参照が無いか grep 確認してから決める）。

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
- 両外部文書の記述がソース未読の読者に通じるか（ルール 14 のチェック）
- (a) と (b) が同じ契約を矛盾なく記述しているか（粒度差はあってよいが内容の食い違いがないこと）

#### 完了条件

`doc/EXTERNAL_DESIGN.ja.md`・`doc/EXTERNAL_SPEC_DRAFT.ja.md` が新方針と整合し、CLAUDE.md からルール 4 / ルール 5 が削除され、文書間で矛盾しない。

#### 残作業

- ルール 4 / ルール 5 削除はオーナー承認済み（2026-05-30）。削除時のルール番号繰り上げ要否（欠番にするか全体を詰めるか）だけ削除実施時に判断

#### 依存 / scope 外

- #1〜#5 の設計確定後に契約反映する（実装と契約の乖離を残さない）。

## 課題全体の完了条件

- すべての sub task（#1〜#6）が完了
- `dismiss` 以外の decision 機構が grep 0 件で根絶（ルール 15 検証）
- 多数 pending conflict のプロジェクトで `/spec-inject` がブロックされず、却下 → ハッシュ失効 → 再浮上の一巡が E2E で確認できる
- 外部設計書・外部仕様 draft（`EXTERNAL_DESIGN.ja.md` + `EXTERNAL_SPEC_DRAFT.ja.md`）・CLAUDE.md・コマンドテンプレ（プロジェクト直下 + `spec_anchor/templates/`）が新方針で一貫
- `pytest -q --skip-external` が pass

## 依存 / scope 外

- **鮮度（freshness）側の議論は本課題の scope 外**。別 TODO として後続で起票・議論する（本セッションでユーザーと合意済み）。ただし `pending_conflict` を `BLOCKED_REASONS` から外す変更（#1）は freshness モジュールに触れるため、鮮度側 TODO と影響範囲が重なる点に注意。
- conflict triage 自体の精度は本課題の scope 外。なお過去に possible_conflict の過剰生成事象があったが既に修正・経路廃止済み（現存バグではない）。
- **既存 `status="resolved"` データの後方互換・migration は本課題の scope 外**。`status="resolved"` を含む既存 `.spec-anchor/context/conflict_review_items.json` は考慮しない（リリース前のため）。本課題はリリース前の破壊的契約変更として扱い、実装・テスト・文書は新契約（pending / dismissed の 2 状態）のみを対象にする。

## 未確定事項（実装着手前に人間判断が要る点）

1. ~~矛盾提示時に「停止する」か「停止せず続行する」か~~ → **確定（2026-05-30）**: 停止して提示。`/spec-realign` も矛盾時は提示で停止し答案を出さない
2. ~~`STATUSES` から `resolved` を完全に外すか（#2 残作業）~~ → **確定（2026-05-30）**: `resolved` 状態も path ④（resolved Conflict Review Item からの制約抽出）も廃止する。理由（人間）: 「SPEC を直さずコンフリクト解決が積み上がると手に負えなくなる」。spec-anchor は仕様修正システムではないので、矛盾の「解決済み」を蓄積する仕組みを持たない。矛盾は提示（注入）して目的達成、SPEC 側の修正は人間が外で行い次の `/spec-core` が再検出する。残る状態は pending / dismissed の 2 つ
3. ~~CLAUDE.md ルール 5 の改訂文面（#6、人間承認）~~ → **確定（2026-05-30）**: ルール 5 を改訂せず、ルール 4 とともに **完全削除**（オーナー承認済み）。理由: 両ルールは `/spec-inject` / `/spec-realign` の製品ランタイム挙動契約であり、開発規律を集めた CLAUDE.md の対象外。内容は外部設計書 + コマンドテンプレが正本（重複 3 箇所目を解消）。詳細は #6 (c)
4. ~~`inject-conflicts` CLI コマンドの去就~~ → **確定（2026-05-30）**: 完全削除する。調査で判明: pending conflict の本文提示は freshness gate 経由（`inject.py:65` `_hydrate_pending_conflict_items` / `freshness.py:320` `pending_conflict_items`）で既に行われており、`inject-conflicts`（`inject.py:552-606`）は `status == "resolved"` のみを返す path ④ 専用関数。path ④ 廃止で唯一の用途が消えるため、pending 提示へ転用する余地はなく完全削除でよい。削除対象: `cli.py:165,297-298,461-471`（subcommand 定義と dispatch）、`inject.py:552-606`（`run_inject_conflicts`）、`inject.py:784` の export、外部設計書 §8.4 / draft §6.1.6 の記述
5. **未確定（CODEX レビュー #3 採用で実装前判断へ復帰）**: pending conflict の status 形状をどう表現するか。候補: (a) pending を fresh 継続にして停止しない、(b) 「search は許すが answer shaping は止める」中間 status を新設する。これは CLI が返す JSON 構造と外部契約（freshness の見え方）に影響するため、#1 の実装着手前に確定する。#2（realign の answer shaping 抑止）の実装方式とも連動する

## sub task / 課題完了時の更新手順

`doc/TODO/TODO_template.ja.md` の「sub task / 課題完了時の更新手順」「archive 手順」に従う。完了時は本ファイルを `doc/TODO/完了済みTODO/TODO_<YYYY-MM-DD>_conflict_resolution_simplification.ja.md` に `git mv` する。
