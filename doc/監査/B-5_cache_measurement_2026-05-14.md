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

cache 経路の (a) 判定とは別に、5 シナリオ計測の実行時間から **incremental の利用者価値を損なう重大な副次問題** が判明した (§4.x 参照)。これらは B-5 task の主目的 (cache 経路の現状確認) の scope 外だが、B-5 計測で初めて測定されたものであり、新規 task として独立化する。

B-5 自体の処理:

- (a) 判定なので新規 task は cache 経路本体に対しては作らない
- `doc/DESIGN.ja.md` に「section_metadata / related_typing cache の entry 単位再構築」セクションを追加し、本計測結果に基づく現実装の説明を 1〜2 段落で残す (本書を引用する形)
- `doc/TODO.ja.md` の B-2 計画書本文 (完了確認済み配下) の「直交」表現を「既存実装で entry 単位再構築を達成済 (B-5 で確定)」に訂正
- B-5 task block を「## 完了確認済み」配下に **原文保持移動**、disposition 節を append

B-5 計測で発見した副次問題 (新規 task として起票):

- **B-5a (`doc/TODO.ja.md`)**: S2/S3 で `section_collection_upsert.action=upserted_partial` だが `embed_documents_input_size=50, sections_upserted_count=50` (51 section 中 50 件 embed) になる真因調査と修正。B-3b 完了確認時 (別 fixture `/tmp/spec_grag_b3b_measure/`、現在は揮発済) の `embed_documents_input_size=1` と矛盾
- **B-7 (`doc/TODO.ja.md`)**: partial change 時の related_sections 増分再生成。現状は incremental でも `action=fallback_regenerated, batch_count=7, elapsed=51.7s` で全 section 再 typing。changed section を source または target に持つ pair だけ再 typing する経路の追加

### 4.x 副次発見: 1 section 変更でも core 全体 wall が initial build とほぼ同等

`§2 集計表` の S2 / S3 wall time が 94.6s / 97.3s で、S0 initial 96.0s とほぼ同等であることが計測で観測された。section_metadata の cache 経路自体は entry 単位で機能している (cache_hits=50, llm_calls=1) のに、core 全体としては incremental の利用者価値を実現できていない。stage 単位の内訳を `s2_progress.json` から抽出すると次の通り。

**S2 (Section 01 本文 1 文字編集, wall 94.6s) の stage 内訳**:

```text
section_metadata.elapsed_sec        = 0.007s   (cache_hits=50, llm_calls=1, batch_sizes=[1])
section_collection_upsert.elapsed_sec = 40.795s
related_sections.elapsed_sec        = 51.725s
chapter_anchors.elapsed_sec         = 0.003s
verify_index.elapsed_sec            = (skipped)
```

**section_collection_upsert.diagnostics (S2)**:

```text
action                       = upserted_partial   ← partial 経路に乗っている
reason                       = source_hash
recreate                     = false
embed_documents_input_size   = 50                ← 51 section 中 50 件 embed
sections_upserted_count      = 50                ← 50 件 Qdrant upsert
sections_deleted_count       = 0
stale_points_deleted         = 0
total_section_input_count    = 51
partial_requested            = true              ← partial が呼ばれている
```

**section_collection_upsert.diagnostics (S3, heading 変更)**:

```text
action                       = upserted_partial
reason                       = section_added
embed_documents_input_size   = 50                ← S3 でも 50 件 embed
sections_upserted_count      = 50
sections_deleted_count       = 1                ← S3 では旧 Section 01 point を delete
stale_points_deleted         = 1
total_section_input_count    = 51
partial_requested            = true
```

**related_sections.action (S2/S3)**: `fallback_regenerated`、`batch_count=7, actual_call_count=7` = 全 section 再 typing。

### 4.x.1 問題 1: B-3b partial path で「partial = ほぼ全件」になっている

action は `upserted_partial`、partial_requested=true で partial 経路に乗っているにも関わらず、S2 で 50 section が embed されている。**B-3b 完了確認** (`doc/TODO.ja.md` B-3b 完了確認結果表) の同条件 (50 section fixture / 1 section 本文変更) では `embed_documents_input_size=1, sections_upserted_count=1, elapsed=8.465s` で合格していた。今回の B-5 計測との差分:

- B-3b 完了確認: fixture `/tmp/spec_grag_b3b_measure/` (現在は揮発済)、collection `spec_grag_b3b_measure`
- B-5 計測: fixture `/tmp/spec_grag_b5_measure/`、collection `spec_grag_b5_measure`
- B-3b 完了確認以降の commit: `bbb843e` (CDX follow-up), `e66eb1f` (B-3b + CDX-002), `400b409` (B-2 fast path), `202af3d` (B-3a)。B-3b 完了確認は commit `b42b309` (2026-05-14) で実施

可能性:

1. **B-3b 完了確認時の数値が partial path の正しい挙動を反映していなかった** (= 別の理由で 1 section embed になっていた、現実は 50 section embed が常態)
2. **B-3b 完了確認後のいずれかの commit (B-4 `345fff1` を含む) で partial path の判定が回帰した**
3. **fixture / config の差で `changed_section_ids` が 50 件になる経路がある** (例: `payload_fingerprint` 計算で何かが他 49 section も変化させた)

最優先で B-5a として真因調査する。

#### 4.x.1.1 真因確定 (2026-05-14, Claude main agent field-level diff)

S0 と S2 の `section_manifest.json` を 51 entry × 4 fingerprint field で diff した結果:

- Section 01 (`spec.md#0002-section-01-authentication-window`): `source_hash` / `semantic_hash` / `payload_fingerprint` / `source_span` が変化 (期待通り)
- **残り 50 section: `payload_fingerprint` のみ変化、`source_hash` / `semantic_hash` / `vector_input_fingerprint` は不変**
- 50 section すべてで `source_span.start_offset` / `source_span.end_offset` が **+3 文字シフト**:
  - Section 02: `start_offset 356 → 359`, `end_offset 530 → 533`
  - Section 10: `+3`, `+3`
  - Section 50: `start_offset 9935 → 9938`, `end_offset 10099 → 10102`
- `start_line` / `end_line` は不変 (Section 01 で行数は変わっていない)

Section 01 の本文 `ten minutes` → `eleven minutes` で +3 文字、後続 50 section の byte offset がそれぞれ +3 シフト。`_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS = frozenset({"related_sections"})` (commit `e66eb1f` の CDX-002 fix 時点) は `source_span` を除外しておらず、`_payload_fingerprint_input(payload)` の出力に `source_span` が含まれ、後続 50 section の `payload_fingerprint` が「他 section の本文長変更」だけで変動する。これが 5 候補のうち **(i) `payload_fingerprint` 計算で他 49 section に変化が波及** の具体経路。

修正 (commit ` (本セッションで実施)`、B-5a として CODEX 実装 + Claude main 監査):

```python
# spec_grag/retrieval_index.py:735
_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS = frozenset({"related_sections", "source_span"})
```

修正後 S2 実機再計測 (`/tmp/spec_grag_b5_measure/` clean state + Section 01 1 文字編集):

| metric | 修正前 (S2) | 修正後 (S2 postfix) |
|---|---|---|
| wall time | 94.6s | **63.9s** |
| `embed_documents_input_size` | 50 | **1** |
| `sections_upserted_count` | 50 | **1** |
| `section_collection_upsert.elapsed_sec` | 40.795s | **9.211s** (B-3b 完了確認時の 8.465s に近い値に復帰) |
| `cache_hits` / `llm_calls` | 50 / 1 | 50 / 1 (不変、期待通り) |
| `related_sections.elapsed_sec` | 51.725s | 52.626s (不変、B-7 scope) |

副作用 (受容): Section 01 だけ変更時、後続 50 section の Qdrant collection 上 `source_span` が古いまま残る。`source_section_id` で source 本文に直接アクセスできるため実用上問題なし。Qdrant payload 上の `source_span` を最新化したい場合は別 task (B-5b 候補、`set_payload` partial patch 経路) として将来切り出す。

### 4.x.2 問題 2: related_sections は incremental でも全体再生成

`related_sections.action=fallback_regenerated, batch_count=7` は「changed section だけでなく全 section の Related Sections を再生成」する経路。current 実装には Related Sections の partial 増分再生成経路が存在しない。`doc/DESIGN.ja.md` §5.7.1 の `incremental no-change fast path` は「全 section が unchanged」の no-change ケースだけ skipped_unchanged で抜ける設計で、1 section でも変化があれば fast path から fallback してフル再生成する。

これは S0 initial build の `related_sections.elapsed_sec=51.252s` と S2 の `51.725s` がほぼ同じことから明確に観測される (= 1 section 変更でも全体再生成、initial build と同コスト)。

B-7 として「partial change 時の related_sections 増分再生成」を新規 task で起票する。合格基準は:

- 50 section fixture / 1 section 本文変更で、`related_sections.elapsed_sec` が initial build の 1/10 以下 (例: 5s 未満) に収まる
- 変更 section を source または target に持つ pair だけ再 typing
- 新 stage action として `regenerated_partial` (仮称) を追加し、全 section 再生成 (`fallback_regenerated`) と区別する

### 4.x.3 incremental の利用者価値への影響

S2 / S3 で測定された stage 内訳は次の通り (1 section 変更 = ideal な 1 LLM call + 1 embed + 1 Qdrant upsert + 隣接 pair typing を想定):

| stage | 観測値 (S2) | 理想値の感覚 | 主因 |
|---|---|---|---|
| section_metadata | 0.007s | 同等 | cache 経路は機能 |
| section_collection_upsert | **40.795s** | ~1s 想定 (B-3b 完了確認時の数値) | B-5a 問題 (50 件 embed) |
| related_sections | **51.725s** | ~5s 想定 (changed pair のみ) | B-7 問題 (全体再生成) |
| chapter_anchors | 0.003s | 同等 | (LLM fallback は別問題、AUD-006) |

`section_collection_upsert + related_sections` で 92.5s = wall 94.6s のほぼ全て。incremental の利用者価値は事実上 `no-change ケース` (S1, wall 1.0s) でのみ実現されている。1 section 変更で initial build 並みの時間がかかるのは利用者体験として致命的。

### 4.x.2.1 B-7 Phase 1 実装後の S2 計測 (2026-05-14, source 中心 partial)

B-7 step 1 (CODEX rescue 実装 + Claude main 監査 + GPT 指摘の必須フラグ追加) を `/tmp/spec_grag_b5_measure/` で実機計測した結果 (50 section fixture + fake LLM + real BGE-M3 + real Qdrant、S0 clean → Section 01 を `ten` → `eleven` で 1 文字編集 → S2 incremental):

| metric | B-5 計測時 (S2) | B-5a 完了時 (S2 postfix) | **B-7 Phase 1 完了時 (S2 b7)** |
|---|---|---|---|
| wall | 94.6s | 63.9s | **61.7s** |
| `section_collection_upsert.elapsed` | 40.8s | 9.2s | 9.2s |
| `section_collection_upsert.action` | upserted_partial | upserted_partial | upserted_partial |
| `related_sections.action` | `fallback_regenerated` | `fallback_regenerated` | **`regenerated_partial`** ✓ |
| `related_sections.batch_count` | 7 | 7 | **1** ✓ |
| `related_sections.llm_calls` | 7 | 7 | **1** ✓ |
| `related_sections.elapsed` | 51.7s | 52.6s | **50.4s** |
| `section_metadata.cache_hits` / `llm_calls` | 50 / 1 | 50 / 1 | 50 / 1 (不変) |
| diagnostics: `partial_mode` | (n/a) | (n/a) | **`source_changed_only`** ✓ |
| diagnostics: `changed_target_relations_inherited` | (n/a) | (n/a) | **True** ✓ |
| diagnostics: `requires_full_regeneration_for_complete_target_recheck` | (n/a) | (n/a) | **True** ✓ |
| diagnostics: `changed_source_section_ids` | (n/a) | (n/a) | `['spec.md#0002-section-01-authentication-window']` ✓ |

**重要な観察**: `batch_count` は **7 → 1** に削減 (= 50 source → 1 source の LLM typing)、しかし `related_sections.elapsed_sec` は **52.6s → 50.4s で約 2.2s しか短縮されない**。

partial 経路の構築 (selection / typing の source 絞り込み) は仕様通り完了したが、**`related_sections.elapsed_sec` の主因は LLM typing batch ではなく candidate generation 段階** (= `generate_related_section_candidates_result(sections, ...)` を全 section から呼んでいる) であることが示唆される。

Codex の partial 実装は selection 段階のみを絞り込んでおり、candidate generation は全 section を入力として走る ([spec_grag/related_sections.py](../../spec_grag/related_sections.py) `generate_related_sections_partial_result` line 1131-1138)。selection 段階の batch_count = 1 達成は B-7 step 1 の検証条件 A (`actual_call_count <= 2`) を満たすが、検証条件 B (`elapsed_sec が initial build の 1/10 以下`) は **未達 (50.4s)**。

このため、B-7 task は **Phase 1 完了 (selection / typing partial 化)** として「完了確認済み」へ移動するが、`elapsed_sec` 目標達成のためには candidate generation の partial 化を **B-7a として独立 task 起票** する。stage 別 timing 内訳 (candidate_generation_elapsed_sec / selection_elapsed_sec) を B-7a の必須計測項目に含めることで、本 task で「主因確定」が間接推論に留まった点を補正する。

B-7 Phase 1 で固定した不変条件 (regression test `test_b7_related_sections_partial_regenerate_source_centric` で常時検証):

- changed/added source の selection / typing のみ再実行 (`batch_count == 1`)
- unchanged source は前回 selected_related_sections を継承 (Section 02 の `target_section_id` / `relation_hint` 集合が initial build と一致)
- removed source は artifact から除外、removed target を含む inherited relation は除外
- diagnostics に partial の制限を明示 (`partial_mode=source_changed_only`、`changed_target_relations_inherited=True`、`requires_full_regeneration_for_complete_target_recheck=True`)

### 4.x.2.2 B-7a 実装後の S2 計測 (2026-05-14, candidate generation の source partial 化)

B-7a (CODEX rescue 実装 + Claude main 監査 + 真の partial 化検証用 assertion 追加) を `/tmp/spec_grag_b5_measure/` で実機計測:

| metric | B-7 Phase 1 (S2) | **B-7a 完了 (S2)** | 改善 |
|---|---|---|---|
| wall | 61.7s | **16.3s** | -45.4s (-74%) |
| `section_collection_upsert.elapsed` | 9.2s | 9.2s | 不変 |
| `related_sections.action` | regenerated_partial | regenerated_partial | 不変 |
| `related_sections.batch_count` | 1 | 1 | 不変 |
| **`related_sections.elapsed_sec`** | **50.4s** | **4.666s** ✓ | -45.7s (1/10 以下達成) |
| `candidate_generation_elapsed_sec` | (計測なし) | **4.52s** | (新計測) |
| `selection_elapsed_sec` | (計測なし) | **0.017s** | (新計測) |
| `candidate_generation_partial_mode` | (n/a) | **`source_changed_only`** ✓ | |
| `candidate_generation_source_count` | (n/a) | **1** ✓ | |

**検証条件 B (`elapsed_sec が initial build の 1/10 以下、5s 未満`) を達成** ✓

stage 別 timing の内訳明示により、Phase 1 で間接推論した「主因は candidate generation」が厳密確定:

- candidate generation: 4.52s (= related_sections elapsed の 97%)
- selection (LLM batch typing): 0.017s (= fake LLM 1 batch、極小)

Phase 1 の 50.4s から 4.7s への削減 (~46s 短縮) の **ほぼ全部** が candidate generation の partial 化に起因。Phase 1 推定 (`generate_related_section_candidates_result(sections=all_sections)` が dominant) は完全に裏付けられた。

実装本物性の検証 (Claude main 監査による逆方向検証):

- `_CoreFakeEmbeddingProvider.embed_query` の呼び出し回数 (`query_calls`) は `InMemoryHybridRetriever` が内部に持つ default `FakeBgeM3EmbeddingProvider` を使うため install fake には流れず検証指標として無効
- 代わりに `generate_related_section_candidates_result` 内部で生成される `related_section_candidate_generation_scope` diagnostic を assertion 対象に追加。これは core.py や `partial_diagnostic` の固定値ではなく、`source_records` の絞り込みを直接反映する
- `if source_section_id_set is None or True:` (= partial 強制無効) で test を再実行 → `assert 'full' == 'source_changed_only'` で fail することを確認 (= test が真に内部 partial 化を検証している決定的証拠)

S2 wall 16.3s の段階別内訳概算:

| stage | elapsed |
|---|---|
| start (config load + manifest 読込) | ~0.7s |
| section_metadata (cache hit 50/51) | ~0.01s |
| section_collection_upsert (B-3b/B-5a partial) | 9.2s |
| related_sections (B-7a partial) | **4.666s** |
| chapter_anchors | ~0.003s |
| その他 (verify_index disabled, etc.) | ~2.4s |

S0 initial 99s に対し S2 16.3s = **83.5% 削減**。incremental の利用者価値が実現された。

B-7a で固定した不変条件 (regression test `test_b7a_related_sections_candidate_generation_source_partial` で常時検証):

- `generate_related_section_candidates_result` の `source_section_ids` 引数が None でない場合、`source_records` を絞り込んで `_add_*_candidates` に渡す
- `candidate_generation_partial_mode == "source_changed_only"`、`candidate_generation_source_count == 1` の表明が `related_section_candidate_generation_scope` diagnostic に出る (core.py / partial_diagnostic の固定値経由ではなく、`generate_related_section_candidates_result` 内部の真値)
- `RelatedSectionCandidateGeneration` と `RelatedSectionSelection` の `elapsed_sec` field に stage 別計測値を持つ

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
