# P3-G5: §5 責務境界 negative check

## 実行日時
2026-05-23 JST

---

## L417: CLI は会話区間を最終解釈しない（引数として受理しない）
```
spec-anchor inject-search [-h] query [query ...]
```
positional 引数は `query` のみ。会話区間全体を受け取るフラグが存在しない。PASS

## L418: CLI は Agentic Search の探索方針を自律的に決めない
```
inject-search --help / inject-section --help: 探索/自動探索/traverse/agentic フラグなし
```
PASS

## L419: CLI は制約を最終生成しない
正常系（freshness=fresh）の inject-search 出力 top-level keys:
```
['collection', 'command', 'hits', 'project_root', 'query', 'top_k', 'warnings']
```
`constraints[]` / `statement` フィールドが CLI 独自生成されていない。PASS  
※ blocked 時の出力には `constraints: []`（空配列）が含まれるが、これは CLI が独自生成した制約ではなく空値を返すだけ。

## L420: CLI は conflict を人間抜きで自動 resolved にしない
pending conflict を設定した状態で `spec-anchor core` を実行:
```
CoreResult.status: updated
pending_conflict_count: 1
freshness_report.status: blocked
conflict_review_items[0].status: pending（変更なし）
```
CLI が `pending` → `resolved` に自動変更しない。PASS

## L421: CLI は Answer を自由生成しない
`spec-anchor realign`（--answer-json なし）:
```
stop_reason: needs_agent_answer
answer フィールド: なし
```
CLI が独自に answer を生成しない。PASS

## L422: CLI は Purpose / Core Concept を自動更新しない
`spec-anchor core` 実行前後の md5sum が一致:
```
65b23a6dfd1f402177912d45ce2066da  purpose.md（変化なし）
268b7364c7cdb86137628ffc1e8a5fcf  concept.md（変化なし）
```
PASS

## L405-L413: CLI が担当する責務（正 check）
以下はフェーズ①の他のテストで確認済み:
- config.toml を読み込み設定値で動作: E7で確認
- Section hash 管理・差分検出: E3で確認（section_manifest.json）
- Section Metadata 生成・保持: E3で確認
- Conflict Review Item 生成・保持: E3で確認
- Chapter Key Anchor 生成・保持: E10で確認
- Source Retrieval Index 生成・保持: E3.2で確認
- freshness 判定: E4で確認（freshness.json）
- inject-search で検索結果返却: E5で確認
- inject-section で Section payload 返却: E5で確認

## 判定
**PASS — 全15項目**

対応 EXTERNAL_DESIGN: §5.3 L405〜L422
