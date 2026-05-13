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

## 開放中

### AUD-003: Qdrant point id / stale point 削除の整合

#### 背景

`doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の AUD-003 で、Qdrant point id が ordinal index に依存し、incremental upsert 時に削除済み section の stale point が残る risk が指摘された。

#### 真因 / 仮説

確定。`upsert_qdrant_section_collection()` は current payloads の upsert を行うが、現 source から消えた section に対応する既存 point を削除しない。

#### 目的

Source Specs の section 削除・挿入・並べ替え後も、Qdrant collection が現在の source corpus と一致する状態を保つ。

#### 実装方針

- Qdrant point id を `source_section_id` / stable source identity 由来の deterministic id にする
- collection 内の既存 payload と現 section set を比較し、現 source に存在しない point を削除する
- 既存 collection の旧 ordinal point からの移行条件を定義する

#### 検証条件

- section 削除後の incremental run で、削除 section が `spec-grag inject-search` の hit に残らない
- section 並べ替え後の incremental run で、hit の `source_section_id` と payload が別 section に入れ替わらない
- 旧 ordinal point を含む collection でも migration または rebuild が明示的に行われる

#### 依存 / scope 外

既存 Qdrant collection の migration / rebuild 方針が必要。B-2 では collection 不存在時の fallback rebuild までを扱い、stale point deletion は未実装。

### AUD-006: Chapter Anchors fallback の freshness degraded 反映

#### 背景

`doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の AUD-006 で、Chapter Anchors の LLM fallback が artifact success として扱われ、freshness に degraded として反映されない risk が指摘された。

#### 真因 / 仮説

確定。mechanical fallback は可用性維持として妥当だが、LLM-generated anchor と品質差がある。

#### 目的

Chapter Anchors が mechanical fallback になった場合、Agent が品質差を見落とさないよう freshness warning / diagnostics に表出する。

#### 実装方針

- `fallback_chapter_ids` が存在する場合に degraded optional artifact として freshness に渡す
- CoreResult の warnings / diagnostics に対象 chapter id を残す
- fallback が発生しても source metadata generation の成功とは別に判定する

#### 検証条件

- Chapter Anchors provider failure 時に `freshness_report.status == "degraded"` または warning が出る
- fallback chapter id が CoreResult diagnostics から確認できる

#### 依存 / scope 外

外部契約上、fallback を failed にするか degraded にするかの表現は既存設計の文言と揃える必要がある。

### AUD-007: Related Sections の Qdrant fallback diagnostics

#### 背景

`doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の AUD-007 で、Related Sections が Qdrant retriever 初期化失敗時に InMemory fallback しても、diagnostics へ十分に表出しない risk が指摘された。

#### 真因 / 仮説

確定。fallback 自体は処理継続のために妥当だが、Qdrant hybrid retrieval を期待した設定との差分を Agent / operator が判別しにくい。

#### 目的

Related Sections candidate generation が実 Qdrant ではなく InMemory fallback を使った場合、CoreResult / artifact diagnostics から判定できるようにする。

#### 実装方針

- Qdrant retriever 初期化失敗を candidate generation diagnostics に残す
- core の `related_sections_status` または warnings に fallback 情報を反映する
- fallback path と real Qdrant path を test で分けて検証する

#### 検証条件

- Qdrant 接続失敗時に `related_sections` diagnostics に fallback reason が入る
- Qdrant 正常時には fallback diagnostics が出ない
- freshness の failed / degraded との関係を設計文書に合わせて固定する

#### 依存 / scope 外

Related Sections は evidence ではなく retrieval auxiliary のため、freshness を failed にするか degraded にするかは AUD-006 と同じく表現を揃える必要がある。

## 実装済み / 完了確認中

### B-2: incremental no-change の固定費削減

#### 状態

実装済み。実装差分はこの変更セットでコミット予定。

#### 背景

session 2026-05-13 計測で `spec-grag core` (no-change incremental) が `llm_calls: 0` ながら **24.45 秒** かかった。内訳:

- `section_collection_upsert` stage: 約 10 秒 (Qdrant 接続 + collection_exists 確認 + 場合により upsert)
- `related_sections` stage: 約 9 秒 (cache 経由整合 + previous_metadata 経由 reuse のオーバーヘッド)

#### 目的

`section_manifest` の hash 比較で「全 section unchanged」を確定した場合、embedding 初期化 / Qdrant upsert / Qdrant scroll を skip する経路を追加し、no-change incremental を **5 秒以下** に短縮する。

#### 実装方針

1. `section_manifest` を読んで `source_hash` / `semantic_hash` を集める
2. 現 source spec の section parse 結果と diff
3. 完全一致なら `_upsert_section_collection_if_enabled` を早期 return し、`retrieval_index_status` は `skipped_unchanged` にする
4. Related Sections も fingerprint が一致する場合は再生成を skip し、`related_sections_status` は `skipped_unchanged` にする
5. Qdrant collection が無い場合は skip せず、`recreate=True` で fallback rebuild する

#### 実装結果

- `retrieval_index_state.json` と `related_sections_state.json` を state artifact として追加した
- no-change incremental では Source Retrieval Index と Related Sections の重い処理を skip する
- `[retrieval].section_collection` を Source Retrieval Index の collection 名として優先する
- Source Retrieval Index 更新失敗時は freshness を failed にする
- retrieval result には Source Specs 本文確認へ進むための `source_document_id` / `source_span` を含める

#### 検証条件

- no-change incremental の 2 回目実行で `retrieval_index_status == "skipped_unchanged"` になる
- no-change incremental の 2 回目実行で `related_sections_status == "skipped_unchanged"` になる
- 2 回目実行で Qdrant upsert と Related Sections generation が呼ばれない
- Qdrant collection が存在しない場合は `recreate=True` で fallback rebuild する
- local-service 環境の実 Qdrant / BGE-M3 で 2 回目実行が 5 秒以下になる

#### scope 外

本文 chunking と本文 embedding は行わない。本文中の語や MUST / 禁止条件の recall は、Section Summary に加えて `search_keys` / `identifiers` と Agentic Search で補う。
