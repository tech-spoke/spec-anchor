# production E2E 取り直し: section_pair + batch + budget-first + #8(auto 解消=削除)

**実施日**: 2026-05-31
**対象コード**: `TODO_conflict_detection_pipeline_simplify.ja.md` #2(section_pair 単段) + budget/batch follow-up + #8(T-auto-resolve-delete) 反映後の現コード（commit `d14bdaf` 時点）
**目的**: batch + budget-first + #8 でコードが変わったため、`TODO_conflict_resolution_simplification.ja.md`(#1) と #2 の production E2E ゲートを **現コードで取り直す**。特に #8 の新挙動（auto 解消 = dismissed 化せず削除 / 修正失敗 = pending 維持）を実 provider で確認する。

**環境（実 provider・fake 不使用）**: codex `gpt-5.4-mini` / claude `claude-sonnet-4-6`(typing + judge) / Qdrant `:6333` / FlagEmbedding `BAAI/bge-m3`。ソース `docs/spec/sample.md`(6 section)。各 step の `spec-anchor core` は incremental で 80〜100s。state は開始前に既存 `conflict_review_items.json` を退避して clean 化。

## 結果サマリー（5 ステップ全 PASS）

| # | ステップ | 操作 | 期待 | 実結果 | 証跡 |
|---|---|---|---|---|---|
| 1 | 検出 | clean `core --rebuild` | 矛盾検出 + conflict_points populated | **3 pending**(retention-policy ↔ {auth 24h / termination 24h / lockout})、全件 conflict_points あり | `artifacts/phase1-rebuild-coreresult.json` |
| 2 | 人間 dismiss | `core --dismiss-conflict <auth↔retention> --reason ...` | dismissed / origin=human で永続 | `status=dismissed` / `resolution.decision_origin=human` | `artifacts/phase2-dismiss-coreresult.json` |
| 3 | reopen | authentication を 24h→48h 編集 → `core` | 却下が pending へ reopen | auth↔retention が **pending へ reopen**(resolution 消去)。再 judge も矛盾と判定し pending 維持。48h 化で auth↔termination の新矛盾も検出(計 4 pending) | `artifacts/phase3-reopen-coreresult.json` |
| 4 | **auto 解消 → 削除 (#8)** | retention-policy を矛盾しない文へ編集 → `core` | 解消した矛盾は **削除**(dismissed で残らない)、`auto_resolved_conflict_count` で件数報告 | retention 絡み **3 件削除**(`conflict_review_items` から消失)、`auto_resolved_conflict_count=3`。retention 非依存の auth↔termination は pending 維持(計 1 pending) | `artifacts/phase4-auto-resolve-delete-coreresult.json` |
| 5 | **修正失敗 → pending 維持 (#8)** | session-termination の sweep 間隔のみ編集(24h purge 維持=まだ不整合) → `core` | source 変更でもまだ不整合なら **削除されず pending 維持** | auth↔termination は **pending 維持**、`auto_resolved_conflict_count=0` | `artifacts/phase5-still-conflict-coreresult.json` |
| 6 | baseline 復元 | `git checkout docs/spec/sample.md` → clean `core --rebuild` | clean baseline 再生成 | **3 pending**(conflict_points populated)。step5 の auth↔termination(48h 時の残骸)は sample.md 復元で 24h↔24h となり矛盾消失 → `auto_resolved=1` で自動削除され、retention 3 件が fresh 検出 | `artifacts/phase6-restore-baseline-coreresult.json` |

## #8 の確認ポイント（オーナー判断対象）

- **ステップ4**: 矛盾が「ソース修正で解消した」場合、項目は `dismissed` として残らず **削除**される。`dismissed` は人間の `--dismiss-conflict` 専用の箱になった(dismiss=human-only / `TODO_conflict_resolution_simplification.ja.md` 成功条件 #4 が実装上も真)。
- **ステップ5**: ソースを変更しても **まだ不整合なら削除されず pending 維持**。人間が解消し損ねた矛盾を黙って消さない(ユーザー懸念の核心)。
- これらは fake provider の unit test(`tests/test_spec_core.py` の `test_t_conflict_source_update_removes_*` / `..._still_conflicting_keeps_pending`)でも決定的に担保。本 E2E は実 provider 出力で同じ挙動を確認したもの。

## 生証跡

- `stdout/phase{1-6}-*.raw.out`: 各 step の `spec-anchor core` 生標準出力(stderr 込みキャプチャ)。
- `artifacts/phase{1-6}-*-coreresult.json`: 各 step の CoreResult を JSON 整形したもの(`conflict_review_items` / `pending_conflict_count` / `auto_resolved_conflict_count` / `auto_resolved_conflict_ids` を含む)。

## 性能注記

各 incremental run は 80〜100s。詳細な per-stage 計測は `doc/性能測定/METRICS.md` 第13回(per-scenario 4 表 + 「production E2E 取り直し」節)を参照。

## このゲートが満たすもの

本一巡で `#2`(detection_pipeline_simplify) と `#1`(resolution_simplification) の **production E2E ゲートを現コードで充足**。両 TODO の最終 close に残る gate は **人間(オーナー)レビューのみ**。レビュー観点は両 TODO の「成功とみなす条件」+ 下記:

1. 検出の質(recall / precision)。特に 矛盾2(retention ↔ lockout, severity=medium)を提示すべき矛盾とみなすか。
2. conflict_points(left/right excerpt + why)の注入有用性。
3. ユーザー向け表示用語。`tests/e2e/snapshots/#3-s02` が多点矛盾を「主張(claims)」と表示しており、section_pair + conflict_points モデルでこの語が適切か。
4. 設計判断(section_pair 単段 / dismiss=human-only / auto 解消=削除)の承認。
