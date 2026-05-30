# TODO: watcher_queue_pending 停止理由の根絶と dirty_or_stale_source への一本化

**起票日**: 2026-05-30
**起票者**: Claude main
**最終更新**: 2026-05-30
**ステータス**: 計画中
**関連設計書**: `doc/EXTERNAL_DESIGN.ja.md` (freshness 停止理由 enum / §11.1.5 / §11.2)、`doc/DESIGN.ja.md §watcher`

## 全体目的

freshness の停止理由 `watcher_queue_pending` を根絶し、「Source Specs が保持物より先行しているが core 未反映」という状態の停止理由を `dirty_or_stale_source` に一本化する。

利用者視点: 現状、実質同じ「source が保持物より先行している」状況に対して、watcher 経由かどうかで `watcher_queue_pending` と `dirty_or_stale_source` の 2 種類の停止理由・メッセージが出る。これを 1 本にし、`/spec-inject` `/spec-realign` 停止時に利用者が見る理由を単純化する。

設計判断の根拠 (裏取り済み, 2026-05-30 session):

- `/spec-inject` は freshness 保持物を読んだ後、`_live_source_dirty` (`spec_anchor/inject.py:166-213`) で**現在の Source Specs の section hash と `section_manifest` を直接突き合わせ**、ズレていれば `dirty_or_stale_source` を理由に挿入する (`spec_anchor/inject.py:157-161`)。これは watcher の状態を一切見ない。
- watcher が `watcher_queue_pending` を立てるのは「source が変わったが core 未消化」の状態 (`spec_anchor/watcher.py:264` 検知直後 / `spec_anchor/watcher.py:529` core 実行中に来た追加変更)。この瞬間は `section_manifest` がまだ更新されていない (core は保持物を実行末尾に atomic 一括書き込みするため。`spec_anchor/artifacts.py:108-127`, `spec_anchor/core.py:874`)。
- したがって `watcher_queue_pending` が立つ全状態で `_live_source_dirty` は独立に True を返し、`dirty_or_stale_source` で必ず停止する。`watcher_queue_pending` はゲート停止理由としては冗長。
- `/spec-realign` は `run_spec_inject` に委譲する (`spec_anchor/realign.py:149`) ため同じ live チェック経路を通る。

挙動方針 (2026-05-30, Human 判断): 「更新中は止めて理由を出す」を維持する。本課題は**挙動を変えない**。`watcher_running` (core 実行中の停止) は残す (Qdrant retrieval index を実行途中で in-place 更新する `spec_anchor/core.py:455` の唯一の整合ガードであり、source 無変更の強制 rebuild 中は live チェックで検出できないため)。本課題が触るのは `watcher_queue_pending` のみ。

完了とみなす条件: live code / test / template / doc から `watcher_queue_pending` / `WATCHER_QUEUE_PENDING` が消え (archive 除く)、watcher が当該状態で `dirty_or_stale_source` を書くようになり、「source 変更 → watcher queue 済 → core 未実行」状態で `/spec-inject` が `dirty_or_stale_source` で停止することを test で確認できた状態。

## 状況サマリー

| # | sub task ID | 概要 | 状態 | 残作業 | 最終更新 | 完了 commit |
|---|---|---|---|---|---|---|
| 1 | T-WQP-1 | コードの `watcher_queue_pending` 根絶 + watcher 書き込みを `dirty_or_stale_source` へ置換 + targeted pytest | 未着手 | 下記「残作業」参照 | 2026-05-30 | — |
| 2 | T-WQP-2 | doc / template / `.claude/commands` の enum 列挙更新 + forbidden_terms + 全 grep 0 確認 | 未着手 | 下記「残作業」参照 | 2026-05-30 | — |

本表の `状態` と `残作業` を見るだけで「次に何をすべきか」が分かるように維持する。

## sub task 詳細

### #1 T-WQP-1: コードの watcher_queue_pending 根絶 + dirty_or_stale_source 置換

**状態**: 未着手
**担当**: Claude main | CODEX
**最終更新**: 2026-05-30

#### 背景

`watcher_queue_pending` は freshness の停止理由 enum として定義・配線されているが、上記「全体目的」の通りゲート停止としては `dirty_or_stale_source` の live チェックに完全に内包される。stop-reason を 1 本化するため、enum とその配線を根絶する。

#### 真因 / 対応方針

**方針**: `watcher_queue_pending` を停止理由 enum から削除する。watcher が現在この理由を**書いている箇所** (`spec_anchor/watcher.py:264`, `:529`, `:1415`) は、何も書かない (= 保持物が "clean" と嘘をつく) のではなく **`dirty_or_stale_source=True` を書くよう置換する**。理由: freshness 保持物自体を正しい状態 (= source が保持物より先行 = dirty) に保ち、inject の live チェックに依存しない読者 (`/spec-core` 等) に対しても整合させるため。

`watcher_queue_count` は停止理由ではなく診断値 (`spec_anchor/freshness.py:169`)。停止理由削除後も残すか落とすかは実装時に判定する (残す場合は「`watcher_queue_pending` 廃止後も診断目的で残す」と最終報告に明示)。

**キューファイル本体と run/idle 判断は scope 外** (下記「依存 / scope 外」)。`queue["queue"]` を使う watcher 内部ロジック (`spec_anchor/watcher.py:283` の idle/run 分岐等) には手を入れない。

#### 根絶対象 (grep 確定, 2026-05-30)

`spec_anchor/freshness.py`:
- `:25` `WATCHER_QUEUE_PENDING = "watcher_queue_pending"` 定数
- `:32` `REASON_PRIORITY` 内エントリ
- `:43` `BLOCKED_REASONS` 内エントリ
- `:49` `DIRTY_WATCHER_OR_STALE_REASONS` 内エントリ
- `:80` `watcher_queue_pending: bool = False` 引数
- `:83` `queue_pending: bool = False` 引数 (queue-pending 配線。要個別確認)
- `:171-180` reason 加算ロジック (`watcher_queue_pending` / `queue_pending` / `_watcher_value(watcher, "queue_pending")` → `_add_reason(reasons, WATCHER_QUEUE_PENDING)`)
- `:412` `if WATCHER_RUNNING in reasons or WATCHER_QUEUE_PENDING in reasons:` 分岐 (`WATCHER_RUNNING` 単独に縮約)
- `:822` `__all__` の `"WATCHER_QUEUE_PENDING"` export

`spec_anchor/watcher.py`:
- `:32` import
- `:47` `WATCHER_ACTIVITY_REASONS = {WATCHER_RUNNING, WATCHER_QUEUE_PENDING}` → `{WATCHER_RUNNING}` に縮約。**`WATCHER_ACTIVITY_REASONS` の全使用箇所を grep し、縮約で挙動が壊れないか確認**
- `:264` `build_freshness_report(watcher_queue_pending=True, watcher_queue_count=...)` → `dirty_or_stale_source=True` へ置換
- `:529` `watcher_queue_pending=True` → `dirty_or_stale_source=True` へ置換
- `:1415` `watcher_queue_pending=bool(queue["queue"])` → `dirty_or_stale_source=bool(queue["queue"])` へ置換
- `:620`, `:1368`, `:1385` の `queue_pending` フィールド: freshness の停止理由に流れる経路か (`freshness.py:175` `_watcher_value(watcher, "queue_pending")`)、純診断フィールドかを個別判定。停止理由に流れるなら断つ。純診断なら残してよい (キューファイルは scope 外で残るため)

#### 検証条件

- `python3 -m pytest tests/test_freshness.py tests/test_watcher.py tests/test_spec_inject.py -q` がパス
- 新規 or 既存の test で「source 変更 → watcher が queue に積んだ (core 未実行) 状態」で `/spec-inject` が `dirty_or_stale_source` を含む `blocking_reasons[]` で停止することを確認
- edge case 確認: `section_manifest` が存在しない新規プロジェクトでは `_live_source_dirty` が False を返す (`spec_anchor/inject.py:188-189`) が、その場合は `failed_required_artifact` で別途停止することを確認 (= queue-pending 廃止で「停止しない穴」が空かないこと)

#### 完了条件

- `git grep -nE "watcher_queue_pending|WATCHER_QUEUE_PENDING" -- 'spec_anchor/**'` が 0 件
- watcher が当該 3 箇所で `dirty_or_stale_source` を書く
- 上記 pytest パス

#### 残作業

- 根絶対象リストの全項目処理
- watcher 3 箇所の `dirty_or_stale_source` 置換
- `WATCHER_ACTIVITY_REASONS` 縮約の影響確認
- `queue_pending` 診断フィールドの個別判定
- targeted pytest + queue-pending 状態の停止 test

#### 依存 / scope 外

- キューファイル (`queue_file`) 本体の廃止、`queue["queue"]` による watcher run/idle 判断の snapshot-diff 一本化は **scope 外** (別課題 = 当初検討の「②大」)
- Qdrant retrieval index の atomic swap (新 collection + alias swap)、更新中に「古いが一貫した snapshot」を inject に出す方式は **scope 外** (2026-05-30 Human 判断で見送り)
- `watcher_running` 停止理由は**残す** (scope 外、削除しない)

### #2 T-WQP-2: doc / template / .claude/commands の enum 列挙更新 + 全 grep 0 確認

**状態**: 未着手
**担当**: Claude main | CODEX
**最終更新**: 2026-05-30

#### 背景

`watcher_queue_pending` は停止理由 enum として複数の doc / コマンドテンプレートに列挙されている。コード削除と同時に列挙からも除去しないと「廃止された名前がドキュメントに残る」状態 (CLAUDE.md ルール 15 違反) になる。

#### 根絶対象 (grep 確定, 2026-05-30)

設計書:
- `doc/EXTERNAL_DESIGN.ja.md:966` (停止理由列挙), `:1390` (`blocking_reasons` JSON 例)。**他にも §11.1.5 / §11.2 / 物理配置表周辺に記述があれば併せて確認**
- `doc/DESIGN.ja.md:1093`, `:1100` (watcher 説明)
- `doc/EXTERNAL_SPEC_DRAFT.ja.md` (grep で該当行特定)

コマンドテンプレート (本体):
- `spec_anchor/templates/.claude/commands/spec-core.md:142`
- `spec_anchor/templates/.claude/commands/spec-inject.md:247`
- `spec_anchor/templates/.claude/commands/spec-realign.md:202`

リポジトリ直下の `.claude/commands/` (`spec-core.md:142` / `spec-inject.md:259` / `spec-realign.md:214`): **`spec_anchor/templates/` から生成されるコピーか、手管理かを先に確認**。生成物なら再生成、手管理なら直接編集。

test:
- `tests/e2e/forbidden_terms.py` (1 件。`watcher_queue_pending` が許可語 enum リストに入っている等の用途を確認して更新)
- `tests/test_freshness.py` (1 件)
- `tests/test_spec_inject.py` (1 件)
- `tests/test_watcher.py` (2 件)

#### 検証条件 / 完了条件

- `git grep -nE "watcher_queue_pending|WATCHER_QUEUE_PENDING"` が **archive 除き 0 件**:
  ```bash
  git grep -nE "watcher_queue_pending|WATCHER_QUEUE_PENDING" | grep -vE "doc/OLD|完了済みTODO|e2eテスト/evidence|archive/full-grag"
  ```
  → 0 件
- `git grep -nE "stub|dormant|legacy|disabled|deprecated|fallback"` の新規 hit が出ていない (置換で中途半端な残骸を作っていない)
- T-WQP-1 と T-WQP-2 は **同一 commit 群で landing** させる (片方だけ landing すると enum とコードが乖離する)

#### 残作業

- 設計書 3 ファイルの enum 列挙・JSON 例から除去
- テンプレート 3 ファイル + `.claude/commands` 3 ファイルの enum 列挙から除去 (生成/手管理を先に判定)
- test 5 ファイルの参照除去・更新
- 全 grep 0 確認

#### 依存 / scope 外

- T-WQP-1 に依存 (コード側の enum 定義が消えてから / と同時に doc を更新)

## 課題全体の完了条件

- `git grep -nE "watcher_queue_pending|WATCHER_QUEUE_PENDING"` が archive 除き 0 件
- watcher が「source 先行・core 未実行」状態で `dirty_or_stale_source` を書く
- 「source 変更 → watcher queue 済 → core 未実行」で `/spec-inject` が `dirty_or_stale_source` で停止する test がパス
- `python3 -m pytest tests/test_freshness.py tests/test_watcher.py tests/test_spec_inject.py -q` および forbidden_terms e2e がパス
- 利用者向け挙動 (停止する / しない) が本課題前後で不変であることを確認

## 依存 / scope 外

- **scope 外 (別課題候補)**: キューファイル本体の廃止と watcher run/idle 判断の snapshot-diff 一本化 (「②大」)、Qdrant retrieval index の atomic swap、更新中の stale-consistent snapshot 提示
- **触らない**: `watcher_running` 停止理由、`pending_conflict` 経路 (別 TODO `TODO_conflict_resolution_simplification.ja.md` の管轄)
- freshness.py は矛盾解決軽量化 TODO も触っている領域。landing 時に該当 TODO の作業と衝突しないか確認する

## sub task / 課題完了時の更新手順

(テンプレート `doc/TODO/TODO_template.ja.md` の手順に従う。完了時は状況サマリー表と sub task 詳細をセットで更新し、章タイトル末尾に `[完了 YYYY-MM-DD, commit xxxx]` を付ける)

## archive 手順

1. すべての sub task と「課題全体の完了条件」が達成されていることを確認する
2. 本ファイル全体を `doc/TODO/完了済みTODO/TODO_<完了日>_watcher_queue_pending_eradication.ja.md` に `git mv` する
