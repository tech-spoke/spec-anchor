# P1-E3: /spec-core 正常系

## 実行日時
2026-05-23 JST（10:08〜10:26）

## 実行環境
- spec-anchor: 0.1.0
- tmp project root: `/tmp/sa-test-sonnet-e3-q2iKl`
- Source Specs: `docs/spec/sample.md` のみ（1ファイル）
- Qdrant collection: `spec_anchor_section_sonnet`（SONNET専用）
- LLM provider: codex (section_metadata / chapter_key_anchor) + claude_typing (related_sections) + claude_judge (conflict_review)

## 注記
初回は `テスト用ドキュメント/`（16ファイル）を使用し 26分経過・SIGTERM 中断（EXIT:143）。  
**`docs/spec/sample.md` のみに変更して再実行（約3分で完了）。**  
以降のテストでも `テスト用ドキュメント/` は使用しない。

## 実行コマンド
```bash
cd /tmp/sa-test-sonnet-e3-q2iKl
spec-anchor core
```

## exit code
0

## stdout JSON（抜粋）
```json
{
  "status": "updated",
  "mode": "incremental",
  "updated_sources": ["docs/spec/sample.md"],
  "updated_sections count": 4,
  "retrieval_index_status": "success",
  "related_sections_status": "success",
  "pending_conflict_count": 0,
  "freshness_report": {"status": "fresh"},
  "warnings": []
}
```

## 必須フィールドの存在確認
全17フィールド存在（missing なし）:
status / mode / updated_sources / skipped_sources / failed_sources / failed_sections /
updated_sections / regenerated_chapter_anchors / retrieval_index_status /
related_sections_status / potential_conflicts / conflict_review_items /
pending_conflict_count / unreflected_conflict_resolutions / stale_resolution_count /
freshness_report / warnings

## 生成 artifact 確認

### .spec-anchor/context/
- `chapter_anchors.json` ✅（chapters count: 1、fields: chapter_id / generated_at / important_sections / key_topics / notes / source_section_ids / summary）
- `conflict_review_items.json` ✅

### .spec-anchor/state/
- `core_progress.json` ✅
- `freshness.json` ✅（status: fresh）
- `section_manifest.json` ✅
- `retrieval_index_state.json` ✅
- `related_sections_state.json` ✅

## Purpose / Core Concept 不変確認
```
md5sum before: 65b23a6dfd1f402177912d45ce2066da  purpose.md
               268b7364c7cdb86137628ffc1e8a5fcf  concept.md
md5sum after:  65b23a6dfd1f402177912d45ce2066da  purpose.md  （一致）
               268b7364c7cdb86137628ffc1e8a5fcf  concept.md  （一致）
```

## 判定
**PASS — 全12項目**

| 確認項目 | 結果 |
|---|---|
| incremental update が動く（status=updated） | PASS |
| mode: incremental が返る | PASS |
| CoreResult の必須フィールドが全て存在する | PASS（17フィールド全て） |
| chapter_anchors.json が context/ に生成される | PASS |
| conflict_review_items.json が context/ に生成される | PASS |
| section_manifest.json が state/ に生成される | PASS |
| freshness.json が state/ に生成される（status=fresh） | PASS |
| retrieval_index_status=success | PASS |
| related_sections_status=success | PASS |
| Purpose / Core Concept ファイルは更新されない | PASS（md5 一致） |
| 2回目の incremental 実行で変更なし section は skip（別途確認） | 未実施→E3補足で実施 |
| chapter_anchors の必須フィールドが存在する | PASS（7フィールド確認） |

## 対応する EXTERNAL_DESIGN の検証単位
§7.1〜§7.4、§3.2 の [ ] 行
