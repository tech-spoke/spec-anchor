# CLAUDE サブエージェント委譲・監査ガイド

このファイルは、CLAUDE main agent が `Agent` tool で **CLAUDE サブエージェント**に実装を委譲し、main が監査する場合の実務ガイドである。`CODEX_DELEGATION_GUIDE.ja.md` の対であり、多くを共有する。

## このファイルの位置づけ

- 共通の失敗パターンと監査チェックリストは `CODEX_DELEGATION_GUIDE.ja.md` を参照する。本ファイルは **Claude 特有の失敗傾向と差分**に絞る。
- 重要: **サブエージェントの最終サマリーは「やろうとしたこと」であって「実際にやったこと」とは限らない。** main は必ず実 diff・実コードを確認してから完了判定する (`Agent` tool の "trust but verify" 原則)。
- CODEX 固有の失敗 (forwarder completed 誤認、grep 回避 string-concat hack 等) も Claude が起こさない保証は無い。本ファイルで省いた項目も CODEX guide の監査を一通り当てる。

---

## 1. Claude (サブエージェント / 自分自身) がよく起こす失敗

### A. TODO / placeholder で「実装完了」にする
production 経路に `TODO` / `NotImplementedError` / `pass` / `...` / 固定値 / 空の戻り値を残したまま「実装した」と報告する。**CODEX 固有ではなく Claude も頻発させる。**
- 対策: `CLAUDE.md` ルール 7 (実装完了ガード)。main は production 経路に placeholder が無いか grep + 目視。

### B. 推論カットによる調査の甘い実装 ★Claude 特有・最重要
学習データのカットオフ後に変わりうる API / library version / CLI 挙動 / package 仕様を、**確認せず過去知識の前提で実装する**。整合性のために不明点を推測で埋める。動いた spike を過大評価する。
- 対策: `CLAUDE.md` ルール 1 (土台がない状態で設計しない)。memory `feedback_no_speculative_filling` / `feedback_verify_before_recommend` / `feedback_no_design_without_foundation`。委譲時に「API / version / 挙動は一次資料か実行で確認し、未確認は明示せよ」と制約する。main は「この実装が依存する外部 API / version / 挙動は確認済みか、推測か」を監査する。

### C. サマリー ≠ 実変更 ★サブエージェント特有
main はサブエージェントの tool 呼び出しを直接見ず、最終サマリーだけを受け取る。サマリーは「意図」であり、実際の編集と食い違うことがある (やったと書いて未編集、別ファイルを触った、検証を省いた)。
- 対策: main は完了判定前に必ず `git diff` / 実コードを読み、サマリーの各主張と実変更を突合する。

### D. 「最小コスト / MVP / 後で追加」で判断回避
本質を理解しないまま「最小案」を出して判断を先送りする。スコープを勝手に狭める。
- 対策: memory `feedback_no_minimum_cost_escape` / `feedback_no_unilateral_scope_narrowing`。

### E. 調査・列挙の取りこぼし
未確認項目を見せないように調査範囲を縮小する。全項目を列挙せず「主なものは確認」で済ます。
- 対策: memory `feedback_full_scope_enumeration`。「確認済 / 表面的 / 未確認」を一覧で出させる。

### F. CODEX と共通の失敗 (本ファイルでは詳説しない)
根絶漏れ / 早期リターン dead code / phantom 仕様 (実装と仕様反映を同時にやると発生) / smoke・fake の production 混入 / 根絶残骸。これらは CODEX 固有ではなく Claude サブエージェントにも起きる。
- 対策: `CODEX_DELEGATION_GUIDE.ja.md` §1 と §3 の監査チェックリストをそのまま適用する。

---

## 2. CLAUDE サブエージェントへ依頼する時の注意点

`CODEX_DELEGATION_GUIDE.ja.md` §2 と多くを共有する。Claude 特有・差分のみ記す。

### 2.1 外部仕様書の反映と実装を同じ task でやらせない
CODEX guide §2.1 と同じ。Claude サブエージェントも実装 + 仕様反映を同時にやると phantom 仕様を書く。外部仕様反映は実装監査後。仕様発明禁止の制約を prompt に入れる (詳細は CODEX guide §2.1)。

### 2.2 外部依存は「確認してから実装」を明示する ★Claude 特有
prompt に「依存する API / library version / CLI 挙動 / package 仕様は、過去知識で仮定せず、一次資料か最小実行で確認してから実装せよ。確認できない点は推測で埋めず未確認として報告せよ」を入れる。

### 2.3 最終 pytest と検収は main が握る
CODEX guide §2.3 と同じ。サブエージェントには実装 + 関連 unit test まで。full pytest と逸脱確認は main。

### 2.4 サブエージェントに「実 diff を残せ」と要求する
完了報告に、変更した file / 追加した test / 実行した検証 command と結果を file:line 付きで含めるよう要求する。main がサマリーと実 diff を突合できる形にする。

---

## 3. 受け取り後の監査ポイント

**共通チェックリストは `CODEX_DELEGATION_GUIDE.ja.md` §3 を適用**する (ただし §3.1 完了の実在確認の forwarder / output file 部分は Claude サブエージェントでは不要)。Claude 特有の追加監査:

- **サマリー突合**: サブエージェントのサマリーの各主張を `git diff` / 実コードで裏取りする。「やった」と書いて未編集、検証省略、別ファイル混入が無いか。
- **推測実装の検出**: 実装が依存する外部 API / version / 挙動が、確認済みか推測か。サブエージェントが「確認した」と書いていても、確認 command の証跡が無ければ未確認扱い。
- **placeholder 検出**: production 経路に `TODO` / `pass` / `...` / 固定値が無いか (ルール 7)。
- **スコープ突合**: 依頼スコープの全項目が処理されたか。「別 task」「スコープ外」で勝手に縮小していないか。

---

## 4. 関連ドキュメント

- `agent_doc/CODEX_DELEGATION_GUIDE.ja.md` — 共通の失敗パターンと監査チェックリスト (本ファイルはその Claude 版差分)
- `CLAUDE.md` ルール 1 (土台がない状態で設計しない) / ルール 7 (実装完了ガード) / ルール 15 (廃止 = 根絶) / ルール 20 (CODEX 委譲時のガイド参照)
- memory: `feedback_no_speculative_filling` / `feedback_verify_before_recommend` / `feedback_no_design_without_foundation` / `feedback_no_minimum_cost_escape` / `feedback_full_scope_enumeration` / `feedback_no_unilateral_scope_narrowing`
