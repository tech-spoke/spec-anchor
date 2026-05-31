# #9-s10 FlagEmbedding model の per-run load 回数 実機計測

## シナリオ要件

`/spec-core` を実 CLI 経路で 1 回起動したとき、

- FlagEmbedding model の重み読み込み (`Loading weights:`) と Hub fetch (`Fetching 30 files:`) の **進捗バーが stdout / stderr に過剰に反復出力されない**。
- stdout は **valid JSON 単体** であり、Agent が Python parser を書かずに `json.loads(stdout)` で読める。
- 1 回の `/spec-core` 実行中に BGE-M3 model weights を **実際に何回 load するか** を instrument で計測する。

> **重要な訂正 (2026-05-31)**: 旧版の本シナリオは「BGEM3FlagModel が class-level cache を持ち、`__init__` を何回呼んでも model object は共有され実 weights I/O は 1 回」と結論していた。これは **誤り**である。旧版 probe は `id(p1.model) == id(p2.model)` で「同一 instance」と判定していたが、`FlagEmbeddingBgeM3Provider.model` は **モデル名の文字列** (`"BAAI/bge-m3"`) であり、Python の文字列 interning により異なる instance でも `id` が一致する (偽の一致)。実モデルオブジェクト `FlagEmbeddingBgeM3Provider._model = BGEM3FlagModel(...)` を比較すると別物であり、class-level cache は効いていない。2026-05-31 の実機計測で **1 回の `/spec-core` で BGE-M3 を 2 回 load している**ことが判明した。

## 実機計測手順

`FlagEmbedding.BGEM3FlagModel` と `FlagEmbeddingBgeM3Provider.__init__` を wrap して構築回数と call site を記録し、`spec-anchor core --rebuild` を in-process 実行した (`spec_anchor.cli.main(["core","--rebuild"])`)。stdout の CoreResult JSON は別バッファへ退避し、構築カウントのみ stderr へ出力した。

## 実行環境

| 項目 | 値 |
|---|---|
| 日付 | 2026-05-31 |
| プロジェクト root | `/home/kazuki/public_html/spec-anchor` |
| Source Specs | `docs/spec/sample.md` (6 section) |
| Python | 3.12 (`.venv`) |
| FlagEmbedding | installed (BAAI/bge-m3 model cache あり: `~/.cache/huggingface/hub/models--BAAI--bge-m3`) |
| Qdrant service | `http://localhost:6333/` healthz OK |
| `.spec-anchor/config.toml` | embedding=flagembedding / model=BAAI/bge-m3 / vector_store=qdrant 実 provider 設定済み |

## 計測結果

| 項目 | 値 | 評価 |
|---|---|---|
| `spec-anchor core --rebuild` 総 wall | 修正前 123 s / 修正後 118 s | — |
| exit code | 0 | ✅ 正常終了 |
| **`FlagEmbeddingBgeM3Provider.__init__` 呼び出し回数** | **修正前 2 → 修正後 1** | ✅ provider 共有で 1 回に |
| **`BGEM3FlagModel(...)` 構築 (実 weights load) 回数** | **修正前 2 → 修正後 1** | ✅ **1 回の core 実行で 1 回 load (修正済み)** |
| stdout の構造 | `json.load()` が成功し top-level **21 keys** を持つ単一 JSON object | ✅ Agent が `json.loads(stdout)` 直呼び可 |
| stdout の top-level keys (代表) | `auto_resolved_conflict_count` / `conflict_review_items` / `pending_conflict_count` / `section_pair_candidate_generation_status` / `related_sections_status` / `retrieval_index_status` / `status` / ... 計 21 keys (claim 系 status は廃止済み) | CLI の正常応答スキーマ |
| `Loading weights:` 進捗バー出現 (stdout) | 0 | ✅ 進捗バー抑制は有効 |

## 【修正前】BGE-M3 が 2 回 load されていた call site

修正前の instrument で記録した `BGEM3FlagModel(...)` 構築の 2 箇所 (現在は provider 共有で 1 回に統合済み):

```
# 構築 #1: section collection の embedding upsert 経路
spec_anchor/core.py:428  (_run_spec_core_unlocked → section_collection_upsert)
  -> spec_anchor/retrieval_index.py:211  self._model = BGEM3FlagModel(model, **model_kwargs)

# 構築 #2: related_sections 候補生成の retrieval 経路
spec_anchor/core.py:471  (_run_spec_core_unlocked → _generate_related_sections)
  -> spec_anchor/related_sections.py:1128  generate_related_sections_result
  -> spec_anchor/related_sections.py:427   generate_related_section_candidates_result
  -> spec_anchor/retrieval_index.py:211    self._model = BGEM3FlagModel(model, **model_kwargs)
```

`FlagEmbeddingBgeM3Provider(...)` の構築点は現状 3 箇所 (`spec_anchor/inject.py:586` は `/spec-inject` 用、`spec_anchor/retrieval_index.py:390` / `:1010` が retrieval 用)。1 回の `/spec-core` では section_collection_upsert と related_sections がそれぞれ独自に retriever を構築するため **2 回 load** になる。

> 補足 (2026-05-31 再計測で訂正): この「retrieval_cap mode では 3 回 load」懸念は **shared provider 化で解消済み**。`core.py` は `_build_shared_embedding_provider_for_core` で 1 回だけ provider を構築し、section_collection_upsert / related_sections / section_pair candidate generation の全 retriever へ注入する (`generate_section_pair_candidates(..., embedding_provider=shared)`)。下記「2026-05-31 再計測 (現コード)」のとおり retrieval_cap mode でも load = 1。

## per-stage 所要時間 (どこで load が起きるか)

詳細な per-stage 計測は `doc/性能測定/METRICS.md` 第12回を参照。BGE-M3 の 1 回目 load は `section_collection_upsert` (10.2 s) に、2 回目 load は `related_sections` (29.4 s、大半は LLM typing) に含まれる。warm cache 時の 1 回 load は実測 ~4.5 s、cold 時は数十秒。

## 進捗バー抑制 (旧版から有効な対策、訂正なし)

| 対策 | 実装箇所 | 効果 |
|---|---|---|
| HF/FlagEmbedding の進捗バーを env で抑制 | `spec_anchor/cli.py` で `HF_HUB_DISABLE_PROGRESS_BARS=1` / `HF_HUB_DISABLE_TELEMETRY=1` を `setdefault` | tqdm 描画自体が起きない |
| コマンド本体実行中 stdout を stderr へ redirect | `spec_anchor/cli.py` `_stdout_reserved_for_result()` context manager | ライブラリが何かを書いても stdout は汚染されない |

これらにより stdout は valid JSON 単体に保たれる (#9 = stdout を valid JSON 単体にする契約は満たされている)。

## 2026-05-31 再計測 (現コード = section_pair + batch + budget-first + #8 後)

`FlagEmbedding.BGEM3FlagModel.__init__` を wrap して構築回数を数え、`spec-anchor core --rebuild` を in-process 実行する probe を 2 構成で再実施した。

| 構成 | section 数 | candidate mode | BGEM3FlagModel 構築回数 | 構築 call site |
|---|---|---|---|---|
| `docs/spec/sample.md` | 6 | all_pairs | **1** | `core.py:_build_shared_embedding_provider_for_core` → `retrieval_index.py:211` |
| temp(29_api + 30_矛盾例 + 23_fields) | 21 | **retrieval_cap** | **1** | 同上 (候補生成も shared provider を注入され独自 load しない) |

両構成とも 1 回の `/spec-core` で BGE-M3 load = 1。retrieval_cap mode でも candidate generation は shared provider を使うため、旧版が懸念した「3 回 load」は発生しない。stdout は 21 keys の valid JSON 単体、`Loading weights:` の stdout 混入 0。

## 結論

- **stdout cleanliness (#9 本体)**: 満たされている。stdout は 21 keys の valid JSON 単体、進捗バー混入なし。
- **load 回数 (修正済み)**: 旧版の「1 回 load (class-level cache)」主張は誤りで、実測では **1 回の `/spec-core` につき 2 回** load していた (section_collection_upsert + related_sections がそれぞれ provider を構築)。**provider 共有 (commit `dee9550`、`_build_shared_embedding_provider_for_core` で 1 回構築し各 retriever へ注入) で 1 回に修正済み**。修正後の実機 instrument で `BGEM3FlagModel` 構築 = 1 を確認。total wall 123→118 s。
- **改善 TODO**: `doc/TODO/TODO_bge_m3_provider_sharing.ja.md` (完了済み)。
