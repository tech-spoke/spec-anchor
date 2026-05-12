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

## B-1: related_sections の Claude prompt cache 安定化

### 背景

2026-05-13 session で artifact 層 refactor (Phase 1-8) を完了させた後、real-env smoke (`docs/spec/sample.md`、1 chapter / 4 section の fixture) で 3 mode (`--rebuild` / `--all` / `incremental` no-change) を計測した。

`related_sections` stage が `--rebuild` / `--all` で毎回 ~30 秒、`cache_creation_input_tokens` が毎回 ~22,000 token 発生し、Claude prompt cache が runs を跨いで十分に再利用できていないことが分かった。

連続 `--rebuild` 2 回の比較で確認した値 (smoke fixture):

| field | rebuild #1 | rebuild #2 | 一致? |
|---|---|---|---|
| `prompt_full_sha256` | adeca414... | ebdad3f1... | 異なる |
| `prompt_len` | 6,559 | 6,623 | +64 char |
| `catalog_sha256` | ed064c70... | 6af75938... | 異なる |
| `evaluations_sha256` | 5b82e562... | 5b82e562... | 同一 |
| `catalog_summaries_sha256` | 3b691a85... | 9e79e105... | 異なる |
| `catalog_search_keys_sha256` | a6934177... | 38d2e975... | 異なる |

### 真因 (確定)

`spec_grag/related_sections.py:_build_batch_selection_request` (lines 1765-1921 付近) が組み立てる Claude へ送る prompt の `payload.catalog` に、`section_metadata` stage が LLM 生成した **summary** と **search_keys** が混入している。

`section_metadata` stage の LLM (`gpt-5.4-mini` / `codex`) は同一入力でも run 毎に文字列レベルで微変動する出力を返す。`evaluations` (`candidate_score`, `channels`, `evidence_terms` 由来) は完全に決定的で run 間で同一だが、`catalog.summaries` と `catalog.search_keys` だけが変動し、その結果 `catalog` 全体および `prompt` 全体の SHA-256 が一致しない。

Claude API 側は、変動した portion を「新規 content」と判定し `cache_creation_input_tokens` に計上する。`json.dumps(payload, sort_keys=True, separators=(",", ":"))` で順序不安定や timestamp / run_id 混入は防御済み (`evaluations_sha256` が同一であることで確認)。

### 目的

`section_metadata` stage の LLM 出力が run 毎に揺れても、`related_sections` の Claude prompt cache が破壊されないようにする。`--rebuild` 連続実行で `cache_creation_input_tokens` が **2 回目以降に大きく減少** することを目標にする。

### 実装方針

1. **`related_sections` の catalog 構築から LLM 生成 metadata を外す。**
   - 削除する field: `summary` (LLM 生成自然文)、`search_keys` (LLM 生成キーワード)、その他 run 毎に揺れる metadata
   - 残す field: `section_id`、`stable_section_uid`、`heading_path` (Markdown AST 由来)、`source_hash`、`semantic_hash`、`identifiers[]` (機械抽出)、`source_document_id`
   - 追加する field: **source 本文 excerpt** を deterministic に切り出す。例えば「section 本文の最初の N 文字」「最初の段落の本文」「heading 直後の N 文字」など。切り出し方は `spec_grag/section_parser.py` の section オブジェクトの `text` / `body` field から純機械処理。LLM 不介入。
2. **catalog を deterministic 情報だけで構成。**
   - 結果として `catalog_sha256` が run 間で完全一致するはず (semantic_hash 不変なら excerpt も不変、identifier も不変)。
3. **debug 用の hash 観測 hook を残す (optional)。**
   - 例えば `SPEC_GRAG_DEBUG_RELATED_PROMPT=1` のような env で `.spec-grag/state/_debug_related_prompts.jsonl` に prompt_full_sha256 / catalog_sha256 / evaluations_sha256 等を append する経路を恒久実装。運用時は無効、検証時に有効化。
   - 既存の `_record_llm_call_stats` 経由で `core_progress.json` の usage に hash 情報を埋める案も検討。
4. **temperature=0 / effort 制御は補助策にとどめる。**
   - LLM provider 設定で `temperature=0` を明示しても完全決定性は保証されない。根本対策は (1)〜(2)。

### 検証条件 (合格基準)

A. **cache_creation の削減 (定量)**
- 同一 source / 同一 config で `spec-grag core --rebuild` を **連続 2 回** 実行する
- 2 回目の `related_sections` stage の `cache_creation_input_tokens` が **1 回目の 10% 以下** (= 90% 以上 cache_read 化) であること
- 計測: `.spec-grag/state/core_progress.json` の `stages.related_sections.usage.cache_creation_input_tokens` / `.cache_read_input_tokens`

B. **catalog の決定性 (hash 一致)**
- 連続 2 回の `--rebuild` で `_build_batch_selection_request` 内の `catalog_sha256` が **完全一致**
- debug log で確認

C. **精度低下なし (品質)**
- 改修前後で `related_sections` の `selected_related_sections` の section_id 集合 (target_section_id) が **同等の section を選んでいる** こと
- `relation_hint` の分布 (`see_also` / `depends_on` / `impacts` / `prerequisite` / `same_policy` の割合) を改修前後で diff し、極端な偏りが出ないこと
- `possible_conflict=true` の発火率を改修前後で比較
- small fixture (`docs/spec/sample.md`) で目視確認、可能なら large spec (100+ section) でも比較

D. **incremental no-change の挙動維持**
- `spec-grag core` (no-change incremental) で `related_sections.usage.llm_calls = 0` のまま維持
- cache reuse 経路 (cache.load / previous_metadata) が壊れていないこと

E. **既存 pytest の合格**
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external` で全 pass 維持
- `tests/test_related_sections.py` 内の既存テスト本体を読み、catalog schema 変更で再書き直しが必要なものは追従

### 触れる主なファイル

- `spec_grag/related_sections.py`
  - `_build_batch_selection_request` (line 1765 付近)
  - `_build_selection_request` (line 1613 付近、single-source path だが catalog 構築構造は共通)
  - `_catalog_entry` (catalog entry の field 構成、line を grep)
  - `_MetadataRecord` 周辺の data class 定義
- `tests/test_related_sections.py` (catalog schema 変更に伴う test 更新)
- `doc/DESIGN.ja.md` (related_sections catalog の field 構成を内部設計として記載するなら)
- `spec_grag/section_parser.py` (deterministic excerpt 切り出しに使う section text / body field の参照)

### 完了条件

- (A)〜(E) の検証条件を全て満たす
- 改修前後の cache_creation_input_tokens の数値を commit message または PR description に記載
- `doc/TODO.ja.md` 本 task の項を削除

### 依存 / scope 外

- **依存**: なし (Phase 1-8 artifact 層 refactor は完了済み、independent に着手可能)
- **scope 外**:
  - `chapter_anchors` stage の cache 戦略 (別の独立 task が必要なら別 entry にする)
  - `section_metadata` の LLM 出力 deterministic 化 (provider 側の制御課題、本 task の範囲外)
  - Claude provider に temperature=0 を強制する config 改修 (補助策、本 task と並行で別途検討)
  - `incremental` no-change の 24 秒固定費削減 (`_upsert_section_collection_if_enabled` 早期 return、Qdrant scroll → fetch_section_payloads 切替) は B-2 として独立 task 化する

### 参考

- session 2026-05-13 の調査ログ抜粋:
  - `evaluations_sha256` が完全一致 → 候補評価ロジック側は deterministic
  - `catalog.summaries / search_keys` が変動 → `section_metadata` LLM 出力が直接 prompt に流入
  - 連続 `--rebuild` 2 回で `cache_creation` 22,130 → 22,050 (LLM 非決定性のため毎回 ~22k token が新規 cache 扱い)
- Claude prompt caching の token accounting:
  - 総 input = `input_tokens` + `cache_creation_input_tokens` + `cache_read_input_tokens`
  - `input_tokens` は最後の cache breakpoint 後の非キャッシュ部分のみ
  - 引用: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- 改善方針の出典: 本 session で GPT (`feedback_capture_findings.md` 参照) との 3 回往復で確定

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
