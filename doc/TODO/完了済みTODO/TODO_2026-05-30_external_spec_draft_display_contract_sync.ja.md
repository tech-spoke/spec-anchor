# TODO: slash command 利用者向け出力契約を EXTERNAL_SPEC_DRAFT.ja.md へ反映する

**起票日**: 2026-05-30
**起票者**: Human (反映漏れ指摘) + Claude main (調査・記述)
**最終更新**: 2026-05-30
**ステータス**: 完了 (人間レビュー待ち)
**関連設計書**: `doc/EXTERNAL_DESIGN.ja.md`（§8.7 人間向け表示契約 / §8.3・§8.3.1 能動的 Agentic Search）、`doc/EXTERNAL_SPEC_DRAFT.ja.md`（§2.10 / §5.2 / §6.2 / §7.2）
**元 TODO（来歴）**: `doc/TODO/完了済みTODO/TODO_2026-05-30_slash_command_user_facing_output.ja.md`（commit b71f620 で完了クローズ）

## 全体目的

完了済み TODO「スラッシュコマンド利用者向け出力整理」は、利用者向け出力契約を `doc/EXTERNAL_DESIGN.ja.md` に反映して完了した。しかし関連設計書として **`doc/EXTERNAL_SPEC_DRAFT.ja.md` を対象に挙げ忘れた** ため、同じ契約が draft 側へ未反映で残っている。`EXTERNAL_SPEC_DRAFT.ja.md` は `EXTERNAL_DESIGN.ja.md` と同じ外部契約を別粒度で記述する並行文書なので、この乖離を解消する。

### 反映漏れの実態（2026-05-30 調査）

| 完了済み TODO が `EXTERNAL_DESIGN.ja.md` に入れた内容 | DESIGN 側 | DRAFT 側 |
|---|---|---|
| 停止時の表示カテゴリ（6 + ◇ + ✕） | §8.7.1 | **なし** |
| 利用者向け本文に貼ってはいけない内部用語の列挙 | §8.7 本文 + `tests/e2e/forbidden_terms.py` | **なし** |
| 正常完了時の表示 / 回答候補の形式不備とリトライ | §8.7.3 / §8.7.4 | 部分的（§5.2/§6.2/§7.2 に断片） |
| 4 path「起点であり上限ではない」能動的 Agentic Search | §8.3 / §8.3.1 | **なし**（§6.2 の 4 path は固定リストのみ、§2.10 も簡素） |
| 利用者向け本文の日本語統一 | （#13 で対応済み） | 要確認（draft の停止出力例に英語自然文が残っていないか） |

draft はこの作業期間中に独立して触られていない（最後のコミットは CODEX review fix と E2E phase。slash command 出力作業の commit には含まれない）。

### 根本原因

完了済み TODO の関連設計書欄が `EXTERNAL_DESIGN.ja.md` のみで、並行文書 `EXTERNAL_SPEC_DRAFT.ja.md` を含めなかった。今後の契約変更はすべて両文書へ反映する必要がある（矛盾解決 TODO `TODO_conflict_resolution_simplification.ja.md` の #6 では既にこれを織り込み済み）。

### 成功とみなす条件

1. `EXTERNAL_DESIGN.ja.md` §8.7 相当の「人間向け表示契約」（停止カテゴリ枠組み・禁止内部用語・正常完了・リトライ）が draft の該当箇所へ反映される
2. `EXTERNAL_DESIGN.ja.md` §8.3 / §8.3.1 相当の「4 path は起点であり上限ではない」能動的 Agentic Search の文言が draft §2.10 / §6.2 へ反映される
3. draft の利用者向け出力例が日本語で統一されている
4. 両外部文書が同じ契約を矛盾なく記述している（粒度差はあってよいが内容の食い違いがない）

## 状況サマリー

| # | sub task ID | 概要 | 状態 | 残作業 | 最終更新 | 完了 commit |
|---|---|---|---|---|---|---|
| 1 | T-draft-display-contract | §8.7 人間向け表示契約（停止カテゴリ枠組み・禁止内部用語・正常完了・リトライ）を draft へ反映 | 完了 | なし | 2026-05-30 | 579546e |
| 2 | T-draft-active-search | §8.3 / §8.3.1 の能動的 Agentic Search 文言を draft §2.10 / §6.2 へ反映 | 完了 | なし | 2026-05-30 | fccc6d2 |
| 3 | T-draft-japanese-check | draft の利用者向け出力例に英語自然文が残っていないか確認・是正 | 完了（検証のみ・変更なし） | なし | 2026-05-30 | — |

本表の `状態` と `残作業` を見るだけで「次に何をすべきか」が分かるように維持する。

## sub task 詳細

### #1 T-draft-display-contract: 人間向け表示契約を draft へ反映

**状態**: 完了（commit 579546e）
**担当**: Claude main
**最終更新**: 2026-05-30

#### 背景

`EXTERNAL_DESIGN.ja.md` §8.7（人間向け表示契約）は次を定める。draft にはこの枠組みが無く、§5.2 / §6.2 / §7.2 の各「停止時の出力形式」に旧式の断片があるだけ。

- §8.7.1 停止時の表示カテゴリ（① 初期設定 / ② 外部サービス / ③ 保持物更新が必要 / ④ 更新中 / ⑤ 人間判断が必要な衝突 / ⑥ ツール側エラー / ◇ 情報通知 / ✕ 非表示）
- §8.7 本文の「利用者向け本文に貼ってはいけない内部用語」列挙（`tests/e2e/forbidden_terms.py` が単一の真実）
- §8.7.3 正常完了時の表示
- §8.7.4 回答候補の形式不備とリトライ

#### 対応方針

- draft §5.2 / §6.2 / §7.2 の停止出力記述を §8.7 の停止カテゴリ枠組みへ揃える。または draft に §8.7 相当の統合節を新設して各コマンド節から参照させる（draft の構成方針に合わせて判断）
- 「貼ってはいけない内部用語」の列挙を draft へ追加する（`forbidden_terms.py` を単一の真実として参照）
- draft 内で内部 field 名（`conflict_id` / `why_conflicting` / `decision_options` 等）を利用者向け出力例として直書きしている箇所を、人間向け見出しへ写像した記述へ直す

#### 検証条件

- DESIGN §8.7 の停止カテゴリ・禁止用語が draft でも参照できること
- `tests/e2e/forbidden_terms.py` の禁止語が draft の利用者向け出力例に出ていないこと（grep）

#### 完了条件

draft が DESIGN §8.7 と同じ人間向け表示契約を矛盾なく記述する。

#### 残作業

- なし

#### 完了時の対応（2026-05-30, commit 579546e）

- draft §3.5「人間向け表示契約 (停止時・正常完了時・リトライ)」を新設（§3.4 の後、§4 の前）。DESIGN §8.7 相当の統合節として、停止カテゴリ ①②③④⑥◇✕・禁止内部用語・正常完了の見せ方・リトライを記述。draft の構成方針に合わせ、共通実行規約 §3 配下の統合節とし、各コマンド章 §5.2 / §6.2 / §7.2 から参照させる方式を採用。
- 「貼ってはいけない内部用語」は `tests/e2e/forbidden_terms.py` の `FORBIDDEN_TERMS` を単一の真実として参照し、一覧の再掲はしない（二重管理回避）。
- §5.2 / §6.2 / §7.2 の冒頭に §3.5 への参照行を追加。
- DESIGN §8.7.1 ✕（回答候補待ち = `needs_agent_answer` は非表示・Agent 自動再実行）へ §7.2 を整合。利用者向け「回答案が未提示」停止 blockquote を除去し、✕ の自動再構成挙動へ置換。停止テーブルの `needs_agent_answer` 行も ✕ 注記へ置換、status 写し方も更新。
- 衝突 category ⑤ は本文展開せず §11 / §6.2 / §7.2 の pending conflict 出力へ委譲（別 TODO `TODO_conflict_resolution_simplification.ja.md` #6 の領域。二重編集回避）。
- 検証: `forbidden_terms.py` の禁止語が draft 利用者向け blockquote 37 行に 0 件（grep, python3 で `FORBIDDEN_TERMS` 突合）。

#### 依存 / scope 外

- **category ⑤（人間判断が必要な衝突）と §11 Conflict Review Item は、矛盾解決 TODO（`TODO_conflict_resolution_simplification.ja.md` の #6）が draft を書き換える対象と重複する**。二重編集・相互上書きを避けるため、衝突関連の停止出力（DESIGN §8.7.2 / draft §6.2・§7.2 の pending conflict 部分・§11）は本 TODO では触れず、矛盾解決 TODO #6 に委ねる。本 TODO は衝突以外の表示契約（①②③④⑥◇✕・禁止用語・正常完了・リトライ）に絞る。

### #2 T-draft-active-search: 能動的 Agentic Search 文言を draft へ反映

**状態**: 完了（commit fccc6d2）
**担当**: Claude main
**最終更新**: 2026-05-30

#### 背景

`EXTERNAL_DESIGN.ja.md` §8.3（L864）/ §8.3.1（L925）は「4 path は探索の起点であり上限ではない。Agent は根拠不足と判断すれば能動的に追加探索する。探索の十分性は Agent が判断する」を明文化している。draft 側は §6.2（L723-）の 4 path が固定リストのままで、§2.10 Agentic Search も「追加検索を繰り返す」程度の簡素な記述に留まり、この能動性・上限非強制の契約が無い。

#### 対応方針

- draft §6.2 の 4 path 記述に「起点であり上限ではない」「Agent が探索十分性を判断」「CLI は path 数・hop 数の上限を強制しない」「ただし根拠は `evidence_origin` に縛られ、CLI 道具を介さない Source Specs 直接 grep は禁止」を反映
- draft §2.10 Agentic Search の定義にも能動性を補う

#### 検証条件

- draft §6.2 / §2.10 に「起点であり上限ではない」相当・「Agent が判断」相当の文言が grep でヒット

#### 完了条件

draft が DESIGN §8.3 / §8.3.1 と同じ能動的 Agentic Search 契約を記述する。

#### 残作業

- なし

#### 完了時の対応（2026-05-30, commit fccc6d2）

- draft §6.2 の 4 path 記述末尾に「4 path は探索の起点であり上限ではない」「探索十分性は Agent が判断」「CLI は path 数・hop 数の上限を強制せず自動探索コマンドを持たない」「根拠は Purpose / Core Concept / Source Specs / stale でない resolved Conflict Review Item に縛られ、CLI 道具を介さない Source Specs 直接 grep は禁止」を追記。
- draft §2.10 Agentic Search の定義に能動性・上限非強制・grep 禁止・`Read` は section_id 特定後の補助確認のみ、を補強。
- 検証: §2.10（L126）/ §6.2（L771）に「起点であり上限ではない」「Agent が判断」相当が grep ヒット。

#### 依存 / scope 外

- なし

### #3 T-draft-japanese-check: 利用者向け出力例の日本語統一確認

**状態**: 完了（検証のみ・是正不要）
**担当**: Claude main
**最終更新**: 2026-05-30

#### 背景

完了済み TODO #13 は「利用者向け本文を日本語に統一」を扱ったが、対象は主にコマンドテンプレだった。draft の利用者向け出力例（停止時の出力形式の例文）に英語自然文が残っていないか確認する。LLM の自己確認では bilingual 混在を検出しづらいため、grep ベースで確認する（記憶: bilingual blind spot）。

#### 対応方針

- draft の「停止時の出力形式（利用者が観測できる内容）」「Agent が利用者へ提示する正常時の出力」の例文を grep し、英語自然文（`Ask a human` 等の CLI default 文字列や英語説明文）が利用者向け出力例として残っていれば日本語へ是正
- 翻訳対象外（コマンド名・URL・file path・識別子）は除外

#### 検証条件

- draft の利用者向け出力例に CLI default 英語文字列・英語説明文が残っていない（grep）

#### 完了条件

draft の利用者向け出力例が日本語で統一されている。

#### 残作業

- なし

#### 完了時の対応（2026-05-30, 検証のみ・draft 変更なし）

- draft の利用者向け出力例（blockquote 37 行 + 正常時出力コードブロック）を python3 で抽出し、CLI default 英語自然文 / 英語命令文の有無を機械検査。
- `forbidden_terms.py` の唯一の英語自然文 `Ask a human to decide this conflict.` は blockquote に 0 件。英語命令文パターン（大文字始まり英単語 2 連続）も該当なし。
- 機械検査が拾った英語トークンは次のいずれかで、いずれも是正不要:
  - 定義済みドメイン用語: `Purpose` / `Core Concept` / `Source Specs` / `Conflict Review Item` / `Section`（§2.x で定義され DESIGN §8.5 正本テンプレートと同一表記）
  - 識別子プレースホルダ: `<source_document_id / source_section_id / source span / 該当 path>`（翻訳対象外）
  - relation_hint enum 例: `<depends / impacts / related など>`（DESIGN §8.5 正本と一致）
  - 衝突例の `retry`（§7.2 pending conflict blockquote。conflict TODO #6 の領域・本 TODO scope 外）
- 結論: 利用者向け出力例は既に日本語統一済み。draft への変更なし。

#### 依存 / scope 外

- なし

## 課題全体の完了条件

- すべての sub task（#1〜#3）が完了
- `EXTERNAL_DESIGN.ja.md` と `EXTERNAL_SPEC_DRAFT.ja.md` が、人間向け表示契約・能動的 Agentic Search・日本語統一について矛盾なく一致（衝突関連は矛盾解決 TODO #6 に委譲）
- `tests/e2e/forbidden_terms.py` の禁止語が draft の利用者向け出力例に出ていない（grep 0 件）

## 依存 / scope 外

- **衝突（Conflict Review Item）関連の表示契約・§11 は本 TODO の scope 外**。矛盾解決 TODO（`TODO_conflict_resolution_simplification.ja.md` の #6）が両外部文書の衝突部分を書き換えるため、そちらに委ねる。本 TODO と #6 は draft の異なる箇所を扱うが、停止カテゴリ ⑤ のみ境界が接するので、両 TODO 着手時に編集順序を調整する。
- コマンドテンプレ（`.claude/commands/` / `spec_anchor/templates/`）は完了済み TODO で対応済み。本 TODO は draft 文書への反映に絞る。

## sub task / 課題完了時の更新手順

`doc/TODO/TODO_template.ja.md` の「sub task / 課題完了時の更新手順」「archive 手順」に従う。完了時は本ファイルを `doc/TODO/完了済みTODO/TODO_<YYYY-MM-DD>_external_spec_draft_display_contract_sync.ja.md` に `git mv` する。
