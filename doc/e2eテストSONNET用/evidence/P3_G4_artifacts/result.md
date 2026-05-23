# P3-G4: §4 保持物の物理配置詳細確認

## 実行日時
2026-05-23 JST

---

## L313-L321: 保持物テーブル 9 種の存在確認
全 PASS（Purpose/Core Concept/section_manifest/Qdrant collection/conflict_review_items/chapter_anchors/freshness/Source Retrieval Index）

## L323: Purpose/Core Concept は自動更新しない
E3/E8/G5 で確認済み。PASS

## L324: Core Concept 乖離通知を提供しない
CoreResult に `concept_drift` / `core_concept` 系フィールドが存在しない。PASS

## L335: Qdrant point id は UUID5 文字列
4 points 全て `uuid.uuid5(b1d5535d-3e52-5430-af3e-ddd879e6cb19, section_id)` と一致。PASS

## L336: UUID5 namespace は固定値
L335 の検証で同 namespace で全点一致を確認。PASS

## L337: embedding 入力 text = `heading_path | summary | search_keys | identifiers`
```
Sample Specification / Authorization | Administrators can manage... | access control ... | API UI
```
形式を確認。PASS

## L338: search_keys / identifiers は各 8 件上限
全 4 points で search_keys ≤ 8、identifiers ≤ 8。PASS

## L339: Source Specs 本文（raw body）は payload に含まれない
payload fields に `raw_body` / `body` なし。PASS

## L343-L345: Related Sections 失敗時の振る舞い
**SKIP** — Qdrant 停止が必要。P2-F1（未着手）と同時に確認する。

## L349-L371: artifact 格納先全量確認（10 項目）
```
conflict_review_items.json @ context/  PASS
chapter_anchors.json @ context/         PASS
section_manifest.json @ state/          PASS
freshness.json @ state/                 PASS
watch_state.json @ state/               PASS
watch_queue.json @ state/               PASS
retrieval_index_state.json @ state/     PASS
related_sections_state.json @ state/    PASS
.spec-anchor/cache/ 存在               PASS
purpose/concept が .spec-anchor/ 配下にない  PASS
```

## L356: section_manifest.json に source_hash / fingerprint が記録
フィールド確認: `source_hash`, `payload_fingerprint`, `semantic_hash`, `vector_input_fingerprint`。PASS

## L361: retrieval_index_state.json の fingerprint 記録
フィールド確認: `section_hash_fingerprint`, `retrieval_schema_pin_fingerprint` 等。PASS

## L363: related_sections_state.json の fingerprint 記録
フィールド確認: `section_hash_fingerprint`, `section_list_fingerprint`, `candidate_generation_config_fingerprint` 等。PASS

## L351: Chapter anchor 失敗時は前回値を残す
正常系のみ確認（`chapter_anchors status: success`）。LLM 失敗パスは意図的失敗環境が必要なため SKIP。

## 判定
**PASS 27件 / SKIP 4件（L343-L345 の 3件 + L351 の 1件）**

SKIP 理由: Qdrant 停止 / LLM 意図的失敗が必要。P2-F1 実施時に追加確認する。

対応 EXTERNAL_DESIGN: §4 保持物 L313〜L371
