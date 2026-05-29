# TODO: 矛盾解決を「ゲート」から「注入情報」へ軽量化する

**起票日**: 2026-05-30
**起票者**: Human (設計判断) + Claude main (調査・記述)
**最終更新**: 2026-05-30
**ステータス**: 計画中
**関連設計書**: `doc/EXTERNAL_DESIGN.ja.md`（decision payload 節 L801-826 / freshness の `pending_conflict` / §8.7 停止カテゴリ⑤）、`doc/EXTERNAL_SPEC_DRAFT.ja.md`（§2.7 / §4 core 出力 / §5・§6 停止出力 / §6.1.6 inject-conflicts / §11 全体）、`spec_anchor/conflict_review.py`、`spec_anchor/core.py`、`spec_anchor/freshness.py`、`spec_anchor/cli.py`、`.claude/commands/spec-inject.md` / `spec-realign.md` / `spec-core.md`、`CLAUDE.md` ルール 5

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
3. `resolved` 系の decision 機構（`prefer_a` / `prefer_b` / `conditional` / `task_scope_resolution`）と pending 系（`needs_source_update` / `defer`）、`unreflected_conflict_resolutions`、重い `--decision-json` / `--decision-file` が **根絶**される（CLAUDE.md ルール 15）
4. 人間の却下インターフェースは **`spec-anchor core --dismiss-conflict <conflict_id> --reason "..."`** の 1 つだけ
5. 却下は永続化され、却下根拠セクションのハッシュが変われば `/spec-core` 再生成で自動失効し、矛盾が再 triage 対象に戻る（再浮上は許容: 「矛盾が解決できない修正をしただけ」と解釈する）
6. コマンドテンプレに「説明 vs 却下の境界」「却下時の CLI 実行＋証跡表示」「実行前確認」が明文化され、LLM が誤って却下を永続化したり、口だけで CLI を叩かなかったりしない
7. 外部設計書と CLAUDE.md ルール 5（pending conflict を無視して進まない）が新方針と整合する

## 状況サマリー

| # | sub task ID | 概要 | 状態 | 残作業 | 最終更新 | 完了 commit |
|---|---|---|---|---|---|---|
| 1 | T-conflict-no-block | 矛盾の `/spec-inject` ハードブロックを廃止し、注入情報として提示する経路へ変更 | 未着手 | — | 2026-05-30 | — |
| 2 | T-decision-machinery-removal | `prefer_a`/`prefer_b`/`conditional`/`task_scope_resolution`/`needs_source_update`/`defer` + `unreflected_conflict_resolutions` + `--decision-json`/`--decision-file` を根絶 | 未着手 | — | 2026-05-30 | — |
| 3 | T-dismiss-cli | `spec-anchor core --dismiss-conflict <id> --reason "..."` を実装（却下記録の唯一の口） | 未着手 | — | 2026-05-30 | — |
| 4 | T-dismiss-staleness-reopen | `base_source_hashes` + ハッシュ失効判定を「却下の失効」へ転用し、失効した dismiss を再オープンする処理を追加 | 未着手 | — | 2026-05-30 | — |
| 5 | T-template-dismiss-flow | コマンドテンプレに却下フロー（説明 vs 却下分離 / 証跡表示 / 実行前確認）を記述 | 未着手 | — | 2026-05-30 | — |
| 6 | T-contract-realign | 外部設計書 + 外部仕様 draft の矛盾解決契約を書き換え、CLAUDE.md ルール 5 を新方針へ整合 | 未着手 | — | 2026-05-30 | — |

本表の `状態` と `残作業` を見るだけで「次に何をすべきか」が分かるように維持する。

## sub task 詳細

### #1 T-conflict-no-block: 矛盾のハードブロック廃止 → 注入情報として提示

**状態**: 未着手
**担当**: 未定（Claude main / CODEX）
**最終更新**: 2026-05-30

#### 背景

現在 `pending_conflict` は freshness の `BLOCKED_REASONS` に含まれ（`spec_anchor/freshness.py:50`）、`/spec-inject` は constraints を生成せず即停止する。これは「矛盾＝解決すべきゲート」という旧モデルの帰結。新モデルでは矛盾は注入情報であり、提示した時点で目的は達成される。多数の矛盾を抱えた実仕様書ではハードゲートが作業を止めてしまう。

#### 対応方針

- `pending_conflict` を旧ハードブロック（constraints を出さず即停止）から外す。代わりに constraints + 矛盾情報を提示してから停止する経路へ変更する
- 課題に関連する矛盾は「提示して停止」までは行うが、CLI 解決を強制しない（提示＝注入＝目的達成）
- `/spec-inject` と `/spec-realign` は同じゲートを共有（`realign.py:5`）。`/spec-realign` は矛盾なしなら答案生成まで進み、矛盾ありなら inject と同じく提示で停止し答案生成へ進まない（人間確定）

#### 検証条件

- 多数の pending conflict があるプロジェクトで `/spec-inject` が constraints + 矛盾情報を提示してから停止すること（旧ハードブロックのように constraints を出さず即停止しないこと）を E2E で確認
- `/spec-realign` が、矛盾なしなら答案まで生成し、矛盾ありなら inject と同じく提示で停止し答案を出さないことを E2E で確認
- `freshness.py` の `BLOCKED_REASONS` から `pending_conflict` を外した影響範囲を pytest で確認

#### 完了条件

矛盾時に旧ハードブロック（constraints を出さず即停止）が廃止され、constraints + 矛盾情報を提示してから停止する。`/spec-realign` は矛盾なしで答案まで、矛盾ありで提示停止。

#### 残作業

- なし（矛盾提示時は「停止して提示」で人間確定済み。`/spec-realign` も矛盾時は提示で停止し答案を出さない）

#### 依存 / scope 外

- #6（契約・CLAUDE.md ルール 5 整合）と密結合。ルール 5「pending conflict を無視して進まない」は本 sub task で前提が変わる。

### #2 T-decision-machinery-removal: decision 機構の根絶

**状態**: 未着手
**担当**: 未定
**最終更新**: 2026-05-30

#### 背景

decision payload（`prefer_a` / `prefer_b` / `conditional` / `dismiss` / `needs_source_update` / `defer` / `task_scope_resolution`）は旧 full GRAG 版の「広範な conflict 承認フロー」由来で、`doc/OLD/EXTERNAL_DESIGN.ja..OLD.md:568` 以降に既存。新モデルでは `dismiss` 以外は不要:

- `prefer_a` / `prefer_b` / `conditional` / `task_scope_resolution`: 会話で意味を伝えれば済む。CLI で resolved にマークする独立価値がない。特に `conditional` は条件の中身が構造化されず（`reason` 自由文のみ）、機械的には `resolved` の別名（`conflict_review.py:27,36`）。
- `needs_source_update` / `defer`: 「直す予定」「保留」を追跡するが、本システムは仕様修正システムではないので追跡しない。人間が外で直し、次の `/spec-core` が再検出する。
- `unreflected_conflict_resolutions`: resolved-but-unreflected 専用通知。resolved を廃止すれば不要。

#### 対応方針（CLAUDE.md ルール 15: 廃止 = 根絶）

`dismiss` を除く decision 値、`--decision-json` / `--decision-file`、`unreflected_conflict_resolutions`、関連する生成・読込・テスト・ドキュメント・設定 template を grep で網羅して削除。

根絶確認:

```text
git grep -nE "prefer_a|prefer_b|conditional|task_scope_resolution|needs_source_update|defer|unreflected_conflict_resolutions|decision-json|decision-file|decision_json"
git grep -nE "stub|dormant|legacy|disabled|deprecated|fallback"
```

#### 検証条件

- 上記 grep が（`dismiss` 関連を除き）0 件
- pytest で decision 関連テストを削除後も全体が pass

#### 完了条件

`dismiss` 以外の decision 機構が根絶され、grep 0 件。

#### 残作業

- `RESOLVED_DECISIONS` / `PENDING_DECISIONS` / `DECISIONS` 定数（`conflict_review.py:18-28`）の整理
- `STATUSES`（`pending` / `resolved` / `dismissed`）から `resolved` を外すか要検討（dismissed と pending の 2 状態に縮約）

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

#### 検証条件

- `--dismiss-conflict` 実行で対象 item が `dismissed` になり `base_source_hashes` が記録される pytest
- 存在しない conflict_id 指定時のエラー挙動

#### 完了条件

`--dismiss-conflict` で却下が永続化される。

#### 残作業

- `--reason` を必須にするか任意にするか（証跡として必須が望ましい）

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

失効粒度の注意（人間了解済み）: 失効はハッシュベース（粗い）。却下根拠セクションへの**矛盾と無関係な軽微な編集でも一旦失効・再 triage が走る**。再 triage がまだ矛盾と判定すれば再浮上（人間が再却下）、矛盾でなければ浮上しない。「意味的に矛盾が残るか」ではなく「セクションが変わったか」で失効する。

#### 検証条件

- 却下後にソース変更 → `/spec-core` 再生成で dismiss が失効し pending に戻る pytest
- ソース無変更なら dismiss が維持される pytest

#### 完了条件

却下根拠のハッシュ変化で dismiss が自動失効し、矛盾が再浮上できる。

#### 残作業

- 再 triage が「もう矛盾でない」と判定した場合は浮上しないことの確認（過剰生成バグ履歴あり: triage 精度は別関心事）

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

### #6 T-contract-realign: 外部設計書・外部仕様 draft・CLAUDE.md ルール 5 の整合

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
- §6.1.6 `inject-conflicts`（resolved/excluded の reason_code 等、L696-712）
- §11 Conflict Review Item の外部仕様（§11.1〜11.7 全体: status 遷移 / decision payload 構造 / decision 値の意味 / object 構造 / stale_resolution flag）

**(c) `CLAUDE.md` ルール 5**（pending conflict を無視して進まない）

#### 対応方針

- (a)(b) から decision payload 機構（`prefer_a`/`prefer_b`/`conditional`/`task_scope_resolution`/`needs_source_update`/`defer`/`--decision-json`/`--decision-file`/`unreflected_conflict_resolutions`）の記述を削除し、「矛盾は constraints と共に提示してから停止（旧ハードブロック廃止）」「却下のみ永続化・ハッシュ失効で再浮上」「`/spec-realign` は矛盾時 inject 同様に提示停止し答案を出さない」の新契約へ書き換え
- status を `pending` / `dismissed` の 2 値へ縮約した記述に統一（§11.2 / §11.3 / §11.4 / §11.6）
- 停止カテゴリ⑤と停止時出力（(a)§8.7 / (b)§5・§6）を「解決を強制する」表現から「提示して停止、却下は任意」へ再定義
- CLAUDE.md ルール 5 を新方針へ改訂（「pending conflict でハードブロックしない」へ）
- いずれもソース未読の読者に通じる言葉で書く（CLAUDE.md ルール 14）

#### 検証条件

- `git grep -nE "decision-json|decision-file|prefer_a|prefer_b|task_scope_resolution|needs_source_update|defer|unreflected_conflict_resolutions"` が `doc/EXTERNAL_DESIGN.ja.md` / `doc/EXTERNAL_SPEC_DRAFT.ja.md` / `CLAUDE.md` で 0 件
- 両外部文書の記述がソース未読の読者に通じるか（ルール 14 のチェック）
- (a) と (b) が同じ契約を矛盾なく記述しているか（粒度差はあってよいが内容の食い違いがないこと）

#### 完了条件

`doc/EXTERNAL_DESIGN.ja.md`・`doc/EXTERNAL_SPEC_DRAFT.ja.md`・CLAUDE.md が新方針と整合し、3 文書間で矛盾しない。

#### 残作業

- CLAUDE.md ルール 5 の改訂は人間（プロジェクトオーナー）承認が必要

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
- conflict triage 自体の精度（過剰生成バグ: 記憶 #204 / #205）は本課題の scope 外。

## 未確定事項（実装着手前に人間判断が要る点）

1. ~~矛盾提示時に「停止する」か「停止せず続行する」か~~ → **確定（2026-05-30）**: 停止して提示。`/spec-realign` も矛盾時は提示で停止し答案を出さない
2. `STATUSES` から `resolved` を完全に外すか（#2 残作業）
3. CLAUDE.md ルール 5 の改訂文面（#6、人間承認）

## sub task / 課題完了時の更新手順

`doc/TODO/TODO_template.ja.md` の「sub task / 課題完了時の更新手順」「archive 手順」に従う。完了時は本ファイルを `doc/TODO/完了済みTODO/TODO_<YYYY-MM-DD>_conflict_resolution_simplification.ja.md` に `git mv` する。
