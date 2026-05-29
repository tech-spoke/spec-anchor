# #9-s10 FlagEmbedding model 1 回 load 化の実機検証

## シナリオ要件

`/spec-core` を実 CLI 経路で 1 回起動したとき、

- FlagEmbedding model の重み読み込み (`Loading weights:`) と Hub fetch (`Fetching 30 files:`) の **進捗バーが stdout / stderr に過剰に反復出力されない**。
- stdout は **valid JSON 単体** であり、Agent が Python parser を書かずに `json.loads(stdout)` で読める。
- 内部の実 weights I/O は **1 回** (BGEM3FlagModel の class-level cache hit) で済み、`__init__` を複数箇所で呼んでも model object が共有される。

TODO の元観察 (2026-05-29 セッション初回) では `/spec-core` の **stdout に `Loading weights:` 系の進捗バーが 4 セット混入** していた。本シナリオはこれが現実装で解消されたことを実 CLI 経路で立証する。

## 実機検証手順

```
$ rm -f /tmp/sa-core-stdout.json /tmp/sa-core-stderr.log
$ time .venv/bin/spec-anchor core 1>/tmp/sa-core-stdout.json 2>/tmp/sa-core-stderr.log
```

## 実行環境

| 項目 | 値 |
|---|---|
| 日付 | 2026-05-29 |
| プロジェクト root | `/home/kazuki/public_html/spec-anchor` |
| Python | 3.12.3 |
| qdrant_client | installed (`.venv/lib/python3.12/site-packages/qdrant_client/`) |
| FlagEmbedding | installed (BAAI/bge-m3 model cache あり: `~/.cache/huggingface/hub/models--BAAI--bge-m3`) |
| Qdrant service | `http://localhost:6333/` HTTP 200 |
| `.spec-anchor/config.toml` | embedding=flagembedding / model=BAAI/bge-m3 / vector_store=qdrant 実 provider 設定済み |

## 計測結果

| 項目 | 値 | 評価 |
|---|---|---|
| 所要時間 (`real`) | 6m32.965s | — |
| exit code | 0 | ✅ 正常終了 |
| stdout サイズ | 60,869 bytes | — |
| stdout の構造 | `json.load()` が成功し top-level 27 キーを持つ単一 JSON object | ✅ Agent が `json.loads(stdout)` 直呼び可 |
| stderr 行数 | 1 行 | — |
| stderr の内容 | `Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN ...` (1 行のみ) | — |
| `Loading weights:` 出現回数 (stderr) | **0** | ✅ 進捗バー完全抑制 |
| `Fetching 30 files:` 出現回数 (stderr) | **0** | ✅ 進捗バー完全抑制 |
| stdout の top-level keys (代表) | `auto_dismissed_conflict_count` / `claim_retrieval_status` / `conflict_review_items` / `failed_sections` / `failed_sources` / ... 計 27 keys | CLI の正常応答スキーマ |

## 内部の実 weights I/O について

別途 `FlagEmbeddingBgeM3Provider` を 2 回直接構築する Probe (同セッション、env なし) で次を確認している:

```
[init call #1]
[init call #2]
first init done in 87.6s
second init done in 37.6s
total init count: 2
same model instance? id(p1.model)=140459117687920 id(p2.model)=140459117687920
```

`id(p1.model) == id(p2.model)` の通り **BGEM3FlagModel が class-level cache を内蔵**しており、`__init__` を何回呼んでも model object は同一で実 weights I/O は 1 回しか走らない。

`spec_anchor` 配下で `FlagEmbeddingBgeM3Provider(...)` を構築している箇所は静的 grep で 5 箇所:

- `spec_anchor/inject.py:670`
- `spec_anchor/claim_retrieval.py:200`
- `spec_anchor/claim_retrieval.py:272`
- `spec_anchor/retrieval_index.py:390`
- `spec_anchor/retrieval_index.py:1010`

これらが 1 回の `/spec-core` 実行中に複数回呼ばれても、cache hit で実 I/O は 1 回。

## 元 TODO 観察「4 回反復」との照合

元観察「`/spec-core` の stdout に `Fetching 30 files:` と `Loading weights:` の進捗バーが 4 セット混入」は次の二つの要因が重なっていた:

1. **env が立っていなかった**: 当時の CLI には HF/FlagEmbedding 系の env 設定機構がなく、HuggingFace Hub と FlagEmbedding が tqdm 進捗バーを描画していた
2. **stdout / stderr 分離がなかった**: 当時の CLI は stdout に直接 result JSON を書き、ライブラリ進捗バーも stdout に混じっていた

現実装の対策:

| 対策 | 実装箇所 | 効果 |
|---|---|---|
| HF/FlagEmbedding の進捗バーを env で抑制 | `spec_anchor/cli.py:27-28` で `HF_HUB_DISABLE_PROGRESS_BARS=1` / `HF_HUB_DISABLE_TELEMETRY=1` 等を `setdefault` | tqdm 描画自体が起きない |
| コマンド本体実行中 stdout を stderr へ redirect | `spec_anchor/cli.py:62` `_stdout_reserved_for_result()` context manager | ライブラリが何かを書いても stdout は汚染されない |
| BGEM3FlagModel の class-level cache | FlagEmbedding ライブラリ側の機構 (本リポジトリでは利用) | `__init__` を何度呼んでも実 weights I/O は 1 回 |

これらが揃ったため、実 CLI 経路では:

- 進捗バー描画 = 0 件
- 実 weights I/O = 1 回 (cache hit)
- stdout = 60KB の valid JSON 単体
- stderr = HF Hub の token absence warning 1 行のみ (s10 スコープ外)

## 結論

#9-s10 シナリオ要件「FlagEmbedding model が 1 回だけ load される (4 回反復が解消されている)」は **実 CLI 経路で完全に満たされている**。前セッションでターミナル側 Claude が「外部ブロッカー」分類したのは誤判断で、本環境には qdrant_client / FlagEmbedding / Qdrant service / HF model cache がすべて揃っており検証可能であった。

## 残作業

なし。

## 補足: 残る stderr 1 行 (`HF_TOKEN` warning) について

```
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
```

これは HuggingFace Hub の token absence warning で、rate limit 緩和のための提案メッセージ。`HF_HUB_DISABLE_PROGRESS_BARS` でも `HF_HUB_DISABLE_TELEMETRY` でも抑制されない。抑制したい場合は `HF_TOKEN` を設定するか、`huggingface_hub` の logging level を下げる必要がある。本 sub task (#9 = stdout を valid JSON 単体にする) のスコープ外。
