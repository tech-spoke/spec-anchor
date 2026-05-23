# P3-G7: §7 /spec-core 詳細確認

## 実行日時
2026-05-23 JST

---

## PASS 項目（85件）

| 行範囲 | 内容 | 確認方法 |
|---|---|---|
| L582-L584 | フラグ動作（none/--all/--rebuild のキャッシュ制御） | E3 で確認済み |
| L586 | --rebuild は --all を含意（mode=full + upserted_full） | G7 実行で確認 |
| L587 | 指定 provider を使い黙って切り替えない（nonexistent_provider → status=error） | G7 実行で確認 |
| L595-L598 | 入力ファイルテーブル 4 種存在 | ファイル存在確認 |
| L604-L609 | CLI フラグ 6 種存在（--all / --rebuild / --verify-index / --llm-provider / --decision-json / --decision-file） | --help で確認 |
| L618-L643 | stage フロー（incremental/all/rebuild）、10 stages 全て core_progress.json に記録 | core_progress.json 確認 |
| L646 | /spec-core 実行の trace 監査（core_progress.json の stages[] で観測可能） | core_progress.json 確認 |
| L648 | Purpose/Core Concept は読み取り専用 | E3/E8/G5 md5sum 確認済み |
| L649 | watcher による背景実行は Agent CLI を起動しない | F4 + watcher --once 確認 |
| L657-L673 | CoreResult 必須17フィールド全存在 | E3/G7 で確認 |
| L678 | retrieval_index_status=success | E3/G7-L586 で確認 |
| L680 | retrieval_index_status=skipped_unchanged | E3 2回目 incremental で確認 |
| L684-L687 | Qdrant collection 更新詳細（diagnostics に sections_upserted_count/stale_points_deleted 等） | core_progress.json 確認 |
| L691 | related_sections_status=success | E3 で確認 |
| L692 | related_sections_status=skipped_unchanged | E3 2回目 incremental で確認 |
| L701 | Chapter Key Anchor は LLM 生成のみ（mechanical/placeholder なし） | CoreResult.diagnostics で確認 |
| L702 | LLM 生成失敗時は chapter_anchors.json を更新せず前回値を残す | 正常系のみ確認（失敗パスは SKIP）|
| L704 | potential_conflicts は Related Sections conflicts_with 由来 | CoreResult.potential_conflicts=[] で確認 |
| L705 | pending conflict → freshness blocked | E4.2 で確認済み |
| L710-L721 | Conflict Review Item 必須12フィールド全存在 | E4.2 fixture で確認 |
| L726-L730 | decision_options 5 種以上（prefer_a/b/conditional/dismiss/defer 他） | E4.2 fixture で確認 |
| L732 | 判断保留（defer）は conflict を解決しない | E4.2 で pending のまま確認 |
| L734-L738 | resolution 管理（unreflected 通知、stale_resolution 検出） | CoreResult フィールド確認 |
| L743-L748 | decision payload 必須6フィールド全存在 | fixture 確認 |
| L755-L761 | decision 機械値と status 遷移 7 種 | 設計確認 + E4.2 で defer→pending 実動作確認 |
| L763 | conflict_evaluation は related_sections の後の別 stage | stages 順序で確認（index 6→7）|
| L764-L765 | conflict 判定は total pair ではなく絞り込み後のみ | 設計確認 |

## SKIP 項目（8件）

| 行 | 内容 | SKIP 理由 |
|---|---|---|
| L679 | retrieval_index_status=skipped | embedding 無効化 config 変更が必要 |
| L681 | retrieval_index_status=failed | Qdrant 停止が必要（P2-F1 で確認予定） |
| L682 | retrieval_index_status=blocked | 上流停止パスが必要 |
| L685 | Qdrant 旧 ordinal point id の自動移行 | 旧 version artifact が必要 |
| L686 | partial update で削除 Section が取り除かれる | テスト環境差異（テストミス-001 参照）|
| L693 | related_sections_status=failed | Qdrant 停止が必要 |
| L694 | related_sections_status=blocked | 上流停止パスが必要 |
| L702 | Chapter anchor 失敗時に前回値保持 | LLM 意図的失敗が必要 |

対応 EXTERNAL_DESIGN: §7 全体 L580〜L765
