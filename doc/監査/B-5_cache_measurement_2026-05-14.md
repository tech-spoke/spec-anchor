# B-5: section_metadata / related_typing cache の現状計測

作成日: 2026-05-14
担当: Claude main agent (Codex rescue subagent は sandbox の network 制約で localhost:6333 へ届かず、本計測は Claude main agent が直接実行した)
fixture: `/tmp/spec_grag_b5_measure/` (50 section spec + fake LLM + real BGE-M3 + real Qdrant collection `spec_grag_b5_measure`)
target: `SectionMetadataCache` ([spec_grag/section_metadata.py:170](../../spec_grag/section_metadata.py#L170)) と `RelatedTypingCache` ([spec_grag/related_typing_cache.py:48](../../spec_grag/related_typing_cache.py#L48)) が **entry 単位再構築** を実現しているかを 5 シナリオで計測する。

## 1. 計測手段

`spec-grag core` を `SPEC_GRAG_FAKE_LLM=1` 環境で実行し、各シナリオで次を観測。

- `CoreResult.diagnostics.section_metadata_generation.cache_hits` (`section_metadata.py` の `cache_hits` 計数、既存露出)
- `CoreResult.diagnostics.section_metadata_generation.llm_calls` (batch 単位)
- `CoreResult.diagnostics.section_metadata_generation.batch_sizes` (各 batch の section 数)
- `CoreResult.diagnostics.section_metadata_generation.reused_section_ids` / `generated_section_ids` (section 単位)
- `.spec-grag/state/core_progress.json` の各 stage `elapsed_sec` / `action`
- `.spec-grag/cache/section_metadata/*.json` の file 数 (実行前後で snapshot)
- `.spec-grag/cache/related_typing_cache.json` の `entries` 数 (実行前後で snapshot)
- 全体 wall time (shell の `date +%s.%N` 差分)

RelatedTypingCache の hit/miss は `CoreResult.diagnostics` に直接露出していないため、`related_typing_cache.json` の entry 数の差分と file mtime で間接観測した。`spec_grag/related_sections.py:520` 周辺の typing cache 利用箇所は計測のために変更していない。

LLM は fake (`SPEC_GRAG_FAKE_LLM=1`) で実行。cache key は `source_section_id` / `source_hash` / `semantic_hash` / `metadata_version` / `prompt_version` / `enabled_fields` / `limits` で構成されており LLM 出力に依存しないため、fake LLM と real LLM で hit/miss 挙動は変わらない (CDX-002 修正後の B-3b と同じ前提)。

## 2. 5 シナリオ計測結果

| Scenario | 操作 | wall | retrieval_index_status | related_sections_status | cache_hits | llm_calls | batch_sizes | reused | generated | sm cache files (before→after) | related_typing entries (before→after) | section_collection_upsert action | related_sections action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | initial build (cache/state/collection 空) | 96.0s | success | success | 0 | 7 | [8,8,8,8,8,8,3] | 0 | 51 | 0→51 | 0→1632 | upserted_full | fallback_regenerated |
| S1 | no-change incremental (S0 直後に再実行) | 1.0s | skipped_unchanged | skipped_unchanged | 51 | 0 | [] | 51 | 0 | 51→51 | 1632→1632 | skipped_unchanged | skipped_unchanged |
| S2 | Section 01 本文を 1 文字編集 (`ten minutes` → `eleven minutes`) | 94.6s | success | success | 50 | 1 | [1] | 50 | 1 | 51→52 (+1 orphan) | 1632→1714 (+82) | upserted_partial | fallback_regenerated |
| S3 | Section 01 heading 変更 (`## Section 01 Authentication Window` → `## Section 01A Auth Renamed`、`source_section_id` 変化) | 97.3s | success | success | 50 | 1 | [1] | 50 | 1 | 52→52 (S2 orphan replaced) | 1714→1796 (+82) | upserted_partial | fallback_regenerated |
| S4 | `SECTION_METADATA_PROMPT_VERSION = "section-metadata-v2"` を `"section-metadata-v2-b5probe"` に一時変更して再実行 | 1.2s | skipped_unchanged | skipped_unchanged | 0 | 7 | [8,8,8,8,8,8,3] | 0 | 51 | 52→103 (+51, old entries 残る) | 1796→1796 | skipped_unchanged | skipped_unchanged |
| S5 | `prompt_version` を `section-metadata-v2` に restore してから `spec-grag core --all` | 94.1s | success | success | 0 | 7 | [8,8,8,8,8,8,3] | 0 | 51 | 103→51 (全 wipe + 新 51) | 1796→1632 (-164) | upserted_full | generated |

各シナリオの raw output と core_progress.json は `/tmp/spec_grag_b5_measure/results/s{0,1,2,3,4,5}_*.json` に保存。

### 数値が示す挙動

**SectionMetadataCache の entry 単位再構築**: ✓ 動作している。

- S2 / S3 で `cache_hits=50, llm_calls=1, reused=50, generated=1` = 変更された 1 section だけ LLM 再生成、他 50 section は cache 経由で再利用
- S2 の `batch_sizes=[1]` は LLM call 数 (= changed section 数) に一致
- S4 (`prompt_version` 変化) で `cache_hits=0, generated=51` = 全 section invalidate (cache key の一部が変わったため、想定通り)
- S3 で heading 変更 (`source_section_id` 変化) しても `cache_hits=50` を維持。つまり「他 section の `source_section_id` は変わっていないため、それらの cache key は変化せず hit する」= entry 単位 cache が壊れない

**RelatedTypingCache の挙動**: ✓ 動作している (entry は (source, target) pair 単位)。

- S0 で 1632 entry 生成 (50 section の pair = 50 × N、N は candidate selection で決まる平均値で ~32.6)
- S1 (no-change) で 1632→1632 (変化なし、cache hit 経由で reuse されている)
- S2 (1 section source 変更) で 1632→1714 (+82)。Section 01 が source または target になる pair の typing が再計算 (50 × 2 - 1 = 99 が最大値、実際は candidate selection で 82 まで絞られている)
- S3 (heading 変更) で 1714→1796 (+82)。Section 01A (旧 Section 01) の pair entry が新たに追加 (古い Section 01 entry は残る)
- S4 (`prompt_version` 変化) は section_metadata_version への影響だけ。related_typing は影響を受けず 1796→1796
- S5 (`--all`) で 1796→1632。`--all` は LLM cache 全 wipe + 新規生成、entry 数は S0 と同じになる

**B-2 fast path との関係**: cache 経路と fast path は重ね合わせ動作する。

- S1 (no-change) で `cache_hits=51, llm_calls=0` を経由してから `section_collection_upsert action: skipped_unchanged` / `related_sections action: skipped_unchanged` に乗る。section_metadata stage は cache hit を観測するために実行され、その結果が retrieval_index_state の指紋一致判定に渡される
- B-2 計画書本文の「LLM cache (section_metadata, related_typing) のエントリ単位再構築は本 task と直交」は実態と合っていない。**entry 単位 cache と B-2 fast path は二段構えで動作している** が正確な記述

### 副次観察 (B-5 scope 外、ただし記録)

**cache file の永続化 GC が `--all` でのみ走る**:

- S2 で section_metadata cache files が 51 → 52 と 1 つ増えた (新 cache key の entry が追加されたが、旧 cache key の entry も file として残る)
- S3 では 52 → 52 (S2 で追加された旧 Section 01 entry が削除、新 Section 01A entry が追加)。これは「現 section に対応しない cache file の一部 cleanup」が incremental 経路で部分的に動いていることを示す
- S4 (`prompt_version` 変化) では 52 → 103 (旧 prompt_version の 52 entry はそのまま、新 prompt_version の 51 entry が追加)。incremental 経路では削除されない
- S5 (`--all`) で 103 → 51 (全 wipe + 新規生成)

**cache GC の挙動は厳密には documented されていない**。incremental 経路で削除される entry とされない entry の区分は実装で確認すれば追跡できるが、本 task scope では現象観察に留め、`--all` で確実に reset できることを以て (a) 判定の足し / 引きにしない。

**section_metadata 永続化 schema**:

- 1 entry = 1 JSON file (`section_metadata/<sha256>.json`)
- key の hash 化 ([spec_grag/section_metadata.py:562](../../spec_grag/section_metadata.py#L562) `section_metadata_cache_key`) で file 名を決定
- 永続化レイヤは `cache_dir` 配下の file-per-entry で、JSON parse のオーバーヘッドはあるが entry 単位の partial 更新が可能

**related_typing 永続化 schema**:

- 1 file = 全 entry を持つ JSON map (`related_typing_cache.json`)
- key は `(source_section_id, target_section_id)` の組み合わせ ([spec_grag/related_typing_cache.py:48](../../spec_grag/related_typing_cache.py#L48))
- 全 file rewrite で更新するため、entry 数が増えるほど I/O コストが上昇する potential

## 3. 結論

**(a) 既存実装で satisfied**。

SectionMetadataCache / RelatedTypingCache はいずれも entry 単位再構築を実現しており、B-2 計画書本文の「直交」表現は実態と合わない。正しくは「entry 単位 cache と B-2 fast path は重ね合わせ動作する」。

5 シナリオ全てで cache key 構成要素が期待通り cache hit/miss を決めており、entry が不要に invalidate される経路や cache miss 時の LLM call が想定外に発生する経路は観測されなかった。

## 4. 後続アクション

- (a) 判定なので新規 task (B-5a / B-5b) は作らない
- `doc/DESIGN.ja.md` に「section_metadata / related_typing cache の entry 単位再構築」セクションを追加し、本計測結果に基づく現実装の説明を 1〜2 段落で残す (本書を引用する形)
- `doc/TODO.ja.md` の B-2 計画書本文 (完了確認済み配下) の「直交」表現を「既存実装で entry 単位再構築を達成済 (B-5 で確定)」に訂正
- B-5 task block を「## 完了確認済み」配下に **原文保持移動**、disposition 節を append

## 5. 残範囲 / 未検証 / scope 外

- cache GC の incremental 経路における削除条件 (S2→S3 で旧 Section 01 entry が削除された一方、S4 では旧 prompt_version entry が削除されない違い) の真因は本書では追跡していない。B-5 task scope は「entry 単位再構築の達成確認」のみ。GC 挙動の文書化が必要なら別 task として切り出す候補
- `related_typing_cache.json` の I/O コストは entry 数 1796 までは観測した範囲で問題なし (S1 で wall 1.0s)。さらに大規模 (例: 500 section, 50000 entry 規模) でのコスト測定は **B-6** の scope (大規模 spec での Qdrant scroll + cache I/O の組み合わせ計測) に含めるか検討
- real LLM (Codex / Claude CLI) 経由での typing cache 計測は fake LLM 計測と挙動が一致することを CDX-002 修正時の B-3b real LLM 環境で実証済。本書では再実証していない
- `/tmp/spec_grag_b5_measure/.spec-grag/cache_codex_backup` / `state_codex_s0_backup` / `state_claude_s0_with_cache` / `context_codex_backup` は計測過程の退避 snapshot。session 終了時に削除可能

## 6. 計測 reproducer

```bash
# 1. fixture 準備 (本書 §1 参照)。tests/fixtures/spec_50sections/spec.md を /tmp/spec_grag_b5_measure/spec.md にコピー、config.toml を section_collection="spec_grag_b5_measure" で書く
# 2. Qdrant 起動済を確認 (curl http://localhost:6333/collections)
# 3. clean 状態にする
rm -rf /tmp/spec_grag_b5_measure/.spec-grag/{cache,state,context}
curl -s -X DELETE http://localhost:6333/collections/spec_grag_b5_measure

# 4. S0
source /home/kazuki/public_html/spec-grag/.venv/bin/activate
SPEC_GRAG_FAKE_LLM=1 spec-grag core --project-root /tmp/spec_grag_b5_measure > /tmp/s0.json

# 5. S1 (S0 直後)
SPEC_GRAG_FAKE_LLM=1 spec-grag core --project-root /tmp/spec_grag_b5_measure > /tmp/s1.json

# 6. S2 (Section 01 本文編集後)
sed -i 's/ten minutes/eleven minutes/' /tmp/spec_grag_b5_measure/spec.md
SPEC_GRAG_FAKE_LLM=1 spec-grag core --project-root /tmp/spec_grag_b5_measure > /tmp/s2.json

# 7. S3 (heading 変更)
sed -i 's/## Section 01 Authentication Window/## Section 01A Auth Renamed/' /tmp/spec_grag_b5_measure/spec.md
SPEC_GRAG_FAKE_LLM=1 spec-grag core --project-root /tmp/spec_grag_b5_measure > /tmp/s3.json

# 8. S4 (prompt_version bump、一時変更)
sed -i 's/SECTION_METADATA_PROMPT_VERSION = "section-metadata-v2"/SECTION_METADATA_PROMPT_VERSION = "section-metadata-v2-b5probe"/' /home/kazuki/public_html/spec-grag/spec_grag/section_metadata.py
SPEC_GRAG_FAKE_LLM=1 spec-grag core --project-root /tmp/spec_grag_b5_measure > /tmp/s4.json
sed -i 's/SECTION_METADATA_PROMPT_VERSION = "section-metadata-v2-b5probe"/SECTION_METADATA_PROMPT_VERSION = "section-metadata-v2"/' /home/kazuki/public_html/spec-grag/spec_grag/section_metadata.py

# 9. S5 (--all)
SPEC_GRAG_FAKE_LLM=1 spec-grag core --project-root /tmp/spec_grag_b5_measure --all > /tmp/s5.json
```
