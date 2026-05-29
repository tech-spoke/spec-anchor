# TODO 一覧

このファイルは spec-anchor の **現在開放中の task** を管理する。完了済み task の本文と履歴は `doc/OLD/TODO_archive_*.ja.md` を参照する。

## 状況サマリー

| # | task | 状態 | 優先度 | 残作業 | 最終更新 |
|---|---|---|---|---|---|
| — | (現在、開放中の task はありません) | — | — | — | 2026-05-29 |

## 直近の archive

- [`doc/OLD/TODO_2026-05-29_specclaim_complete.ja.md`](OLD/TODO_2026-05-29_specclaim_complete.ja.md) (2026-05-29): SpecClaim 経路移行 (Phase 1-5: SCD-032 / SCD-033) + T-conflict-source-update-flow (スラッシュコマンド user-facing workflow auto-dismiss) + 追従 task (T-flaky-spec-core-responsibility-boundary, T-spec-inject-pending-conflict-fixture-update) を完全完了。設計書 [`doc/OLD/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md`](OLD/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md) 由来の実装はすべて CLOSE。

## 新規 task 追加時のテンプレート

新規 task を起こす際は次の手順:

1. 「## 状況サマリー」表に 1 行追加し、`task` / `状態` / `優先度` / `残作業` / `最終更新` を埋める
2. 本ファイル末尾に章本体 `### T-task-name: 1 行概要` を追加
3. 章本体は次の構造で書く:

```markdown
### T-task-name: 1 行概要

**状態**: 未着手 | 着手中 | コア実装完了 | regression test 待ち | 完了
**担当**: Claude main | CODEX | Human
**最終更新**: YYYY-MM-DD
**直近 commit**: (該当ある場合)

#### 背景
何が問題で、なぜこの task が必要か。利用者視点で書く。

#### 真因 / 対応方針
真因が確定している場合は記述。確定していない場合は仮説と確認手順を書く。

#### 検証条件
完了確認に必要な test や実機実行条件を列挙。

#### 完了条件
何が達成されたら完了扱いにするか。

#### 残作業
- ...
- ...

#### 依存 / scope 外
依存 task / 本 task の scope 外として明示すべき事項。
```

4. task が完了したら:
   - 「## 状況サマリー」表から該当行を削除
   - 章タイトルに `[完了 YYYY-MM-DD, commit XXXXXXX]` マークを付ける
   - 章本体は残す (または archive 移行時にまとめて doc/OLD/ へ)
5. ファイルが肥大化したら、完了 task の章本体だけを `doc/OLD/TODO_YYYY-MM-DD_<topic>.ja.md` に切り出し、本ファイル冒頭の「直近の archive」リストに 1 行追加する
