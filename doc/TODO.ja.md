# 開放 TODO 一覧

次のセッション以降で実装する task をここに集める。`doc/EXTERNAL_DESIGN.ja.md` の外部契約を **変えない** task を中心に置く。契約変更を伴う task は EXTERNAL_DESIGN.ja.md 本体に書く。

各 task は次の構造で書く:

- 背景 (どの session でどの観測から派生したか)
- 真因 / 仮説 (確定 / 未確定の別を明示)
- 目的
- 実装方針
- 検証条件 (合格基準を数値化)
- 触れる主なファイル
- 完了条件
- 依存 / scope 外

---

## B-2: incremental no-change の固定費削減 (placeholder)

### 背景

session 2026-05-13 計測で `spec-grag core` (no-change incremental) が `llm_calls: 0` ながら **24.45 秒** かかった。内訳:

- `section_collection_upsert` stage: ~10 秒 (Qdrant 接続 + collection_exists 確認 + 場合により upsert)
- `related_sections` stage: ~9 秒 (cache 経由整合 + previous_metadata 経由 reuse のオーバーヘッド)

### 目的

`section_manifest` の hash 比較で「全 section unchanged」を確定した場合、embedding 初期化 / Qdrant upsert / Qdrant scroll を skip する経路を追加し、no-change incremental を **5 秒以下** に短縮する。

### 実装方針 (未確定、別 session で具体化)

1. `section_manifest` を読んで `source_hash` / `semantic_hash` を集める
2. 現 source spec の section parse 結果と diff
3. 完全一致なら `_upsert_section_collection_if_enabled` を早期 return (status は前回値継承)
4. `_read_previous_section_metadata` の Qdrant scroll を不要にする経路を追加 (section_manifest だけで reuse 判定)

### scope

B-1 完了後に着手。B-1 と独立だが、関連する Qdrant scroll の挙動を触るため順序付けが望ましい。
