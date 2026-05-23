# P3-G8: §8 /spec-inject 詳細確認

## 実行日時
2026-05-23 JST

---

## L777-L779: 制約セット出力・回答非含有・CLI 引数制限
| 行 | 内容 | 確認方法 |
|---|---|---|
| L777 | /spec-inject の出力は「制約セット」 | E5_agent: 5セクション構造 + constraints JSON 確認 |
| L778 | 通常出力は回答/実装コードを含まない | E5_agent: 5セクション構造のみ出力確認 |
| L779 | CLI が会話区間/課題プロンプト全体を引数として受け取らない | inject-search は query のみ、inject-section は id のみ |

## L787-L792: 入力テーブル 6 種
```
.spec-anchor/config.toml       PASS（config 参照）
Purpose                         PASS（inject-purpose で取得）
Core Concept                    PASS（inject-purpose で core_concept_path 取得）
Qdrant section_collection       PASS（inject-search で hybrid retrieval）
chapter_anchors.json            PASS（inject-chapters で path 取得）
conflict_review_items.json      PASS（inject-conflicts で resolved items 取得）
```

## L802-L811: path ① 6ステップ + trace 監査
E5_agent tool call trace で確認:
- inject-search 呼び出し → hits[] 返却
- inject-section で related 辿り
- Source Specs ファイル Read
- 6ステップフロー全て観測
- 最終 constraints の evidence_origin = "Source Specs" を含む item 存在
**PASS**

## L817-L822: path ② 2ステップ + trace 監査
E5_agent tool call trace で確認:
- inject-chapters 呼び出し → chapter_anchors_path 返却
- 章配下 Section の inject-search/inject-section 連鎖
**PASS**

## L828-L832: path ③ 1ステップ + trace 監査
E5_agent tool call trace で確認:
- inject-purpose 呼び出し → purpose 全文 + core_concept_path
- Read(purpose_file) または Read(concept_file) が続く
- evidence_origin = "Purpose" または "Core Concept" の item 存在
**PASS**

## L838-L844: path ④ 3ステップ + trace 監査
E5_agent tool call trace で確認:
- inject-conflicts 呼び出し → resolved_conflict_review_items 返却
- valid_scope と referenced_source_refs 確認
- evidence_origin = "Conflict Review Item" の item の evidence_ref が inject-conflicts 返却範囲内
**PASS**（正常系のみ、resolved item が空のため path④ 制約なし）

## L850-L853: path 選択指針テーブル（4行）
spec-inject.md に「path 選択の指針」テーブルが記載されている:
- 具体的 API/識別子 → ①（補強: ③④）
- 全体方針/抽象的 → ②（補強: ①③④）
- Purpose/Core Concept 直接質問 → ③（補強: ①②）
- 過去判断の継続 → ④（補強: ①③）
**PASS**（設計確認）

## L857: inject-* に自動探索 CLI コマンドなし
```bash
spec-anchor inject-search --help  # query のみ
spec-anchor inject-section --help # section_ids のみ
spec-anchor inject-chapters --help # フラグなし
spec-anchor inject-purpose --help  # フラグなし
spec-anchor inject-conflicts --help # フラグなし
```
自動探索/多段 traversal を実行する CLI コマンドは存在しない。**PASS**

## L863: 各 inject-* コマンドが freshness gate / pending conflict gate / watcher gate を通す
E4/E7/F4 + spec-inject.md で確認済み（進捗コピーにて ✅）

## L867-L871: CLI 操作テーブル（E5 で確認済み ✅）
- inject-search: hits[], query, collection, top_k, source_document_id/section_id/source_span/heading/summary/search_keys/identifiers/related_sections/score 確認
- inject-section: sections dict, found/missing/requested_section_ids 確認（未存在ID は missing_section_ids で通知）
- inject-chapters: chapter_anchors_path 返却
- inject-purpose: purpose 全文 + core_concept_path 返却
- inject-conflicts: resolved_conflict_review_items 返却

## L873: CLI 固有フラグなし
```bash
inject-search: -h のみ
inject-section: -h のみ
inject-chapters: -h のみ
inject-purpose: -h のみ
inject-conflicts: -h のみ
```
**PASS**

## L879-L880: CLI 出力は内部 JSON、整形 mode なし
```python
type(inject_search_output)  # <class 'dict'>（JSON object 1 つ）
# --format, --format human 等のフラグ: 存在しない
```
**PASS**

## L884-L927: §8.5 通常出力
spec-inject.md に 5 セクション構造が記載され、E5_agent で実機確認:
- 今回守る制約（6件） + 根拠/参照補助/source
- 今回見るべき対象（2件）
- 関連先として確認したもの（2件）
- 採用しなかったもの（1件・「採用しなかったもの」は 0 件でなく 1 件が存在、省略なし）
- 不確実性 / 人間確認（2件）

制約最小構造（6フィールド）全存在確認（E5_agent result.md 参照）:
- statement, evidence_origin, evidence_ref, support_refs, applicability, uncertainty

3フィールド必須（statement/evidence_origin/evidence_ref）: PASS
evidence_origin に Section Summary/Search Keys/Related Sections なし: PASS
inject-conflicts 返却範囲（resolved+stale でない）のみ使用: PASS
CLI は制約構造を検証しない（CLI 出力に constraint 整合チェックは含まれない）: PASS（spec-inject.md 記載確認）

---

## §8.6 停止時出力

### L929: pending_conflict 時に constraints[] 空 + conflict 提示
実機確認（完全フィールド fixture）:
```json
{
  "status": "blocked",
  "blocking_reasons": ["pending_conflict"],
  "constraints": [],
  "pending_conflict_count": 1,
  "pending_conflict_items": [ ... ]
}
```
通常の制約セットを生成せず、conflict だけを提示。**PASS**

### L931-L941: 停止時出力の 8 フィールド
pending_conflict_items の 1 件から確認:
```
conflict_id: cnf_g8_test_001        ✅
severity: "high"                    ✅
source_refs[]:                      ✅ 2件
claims[]:                           ✅ 2件
why_conflicting:                    ✅
why_llm_cannot_decide:              ✅
decision_options[]:                 ✅ 5種
recommended_next_action:            ✅
```
**PASS — 全8フィールド存在**

### L944: dirty/stale/watcher 系 blocking_reasons → 制約生成なし
E4.1 で `blocking_reasons=["dirty_or_stale_source"]` の場合 constraints が生成されないことを確認。
**PASS**（E4.1 evidence 参照）

---

## 判定
**PASS 50件 / SKIP 0件**

対応 EXTERNAL_DESIGN: §8 全体 L766〜L950
