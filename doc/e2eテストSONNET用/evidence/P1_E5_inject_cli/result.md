# P1-E5: /spec-inject CLI 部分（inject-search/section/chapters/purpose/conflicts）

## 実行日時
2026-05-23 JST

## 注記
E5 の「Agent CLI が 5 セクション構造を提示するか」は Agent CLI 出力の確認が必要なため別途実施。  
本証跡は CLI コマンドの戻り値構造を確認する部分のみ。

---

## inject-section

```bash
spec-anchor inject-section "docs/spec/sample.md#0002-authentication"
```

```
found_section_ids: ['docs/spec/sample.md#0002-authentication']
missing_section_ids: []
sections keys: ['docs/spec/sample.md#0002-authentication']
```

指定 ID の payload が `sections` dict として返される。未存在 ID は `missing_section_ids` で通知。

---

## inject-chapters

```bash
spec-anchor inject-chapters
```

```
章 anchor path: /tmp/sa-test-sonnet-e3-q2iKl/.spec-anchor/context/chapter_anchors.json
ファイル存在: True
```

`chapter_anchors.json` の path を返す。Agent が `Read` で必要箇所を抽出する経路。

---

## inject-purpose

```bash
spec-anchor inject-purpose
```

```
purpose フィールド存在: True
purpose 長さ: 248
core_concept_path: /tmp/sa-test-sonnet-e3-q2iKl/docs/core/concept.md
core_concept_path ファイル存在: True
```

Purpose 全文（248文字）+ Core Concept の path が返る。

---

## inject-conflicts

```bash
spec-anchor inject-conflicts
```

```
top-level keys: ['command', 'count', 'excluded_conflict_review_items', 'project_root', 'resolved_conflict_review_items']
items count: 0
（pending は含まれない）: OK
```

`status=resolved` かつ stale でない items のみ返す（現在 pending なし = 0 件）。

---

## inject-search（E3.2 で確認済み）

`spec-anchor inject-search "認証"` → hits 8件、必須フィールド全存在（evidence/P1_E3_2_qdrant_payload/ 参照）

---

## 判定
**PASS（CLI 部分 5 項目）**

| 確認項目 | 結果 |
|---|---|
| inject-search が hits[] を返す（必須フィールド全存在） | PASS（E3.2参照） |
| inject-section が found/missing を区別して payload を返す | PASS |
| inject-chapters が chapter_anchors.json の path を返す | PASS |
| inject-purpose が purpose 全文 + core_concept_path を返す | PASS |
| inject-conflicts が resolved かつ stale でない items を返す | PASS |

Agent CLI 側の 5 セクション構造確認: 未実施（E5-Agent として別途実施予定）

## 対応する EXTERNAL_DESIGN の検証単位
§8.4 CLI が提供する操作の [ ] 行（inject-search/section/chapters/purpose/conflicts）
