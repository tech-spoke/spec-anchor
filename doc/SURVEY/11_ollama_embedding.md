# 11: Ollama embedding 接続

> 状態: **WebFetch ✓ / Spike ✓** — API レベルで動作確認、判定 **usable**
> 最終更新: 2026-04-28

## 調査対象

- component: `llama_index.embeddings.ollama.OllamaEmbedding`
- model: `nomic-embed-text:latest` (Ollama daemon localhost:11434, installed)
- version / commit: `llama-index-embeddings-ollama==0.9.0` (with `llama-index-core==0.14.21`)
- source:
  - official docs: https://developers.llamaindex.ai/python/framework/integrations/embeddings/ollama_embedding/
  - GitHub source: _略（必要なら fetch）_
  - 実行確認: [`spike/00_smoke_ollama_embedding.py`](../../spike/00_smoke_ollama_embedding.py)

## 確認した API

- import path: `from llama_index.embeddings.ollama import OllamaEmbedding`
- constructor: `OllamaEmbedding(model_name="nomic-embed-text", base_url="http://localhost:11434", ollama_additional_kwargs=None)`
- single embedding: `emb.get_text_embedding("...")` / `emb.get_query_embedding("...")`
- batch embedding: `emb.get_text_embedding_batch([...], show_progress=True)`
- async: `aget_text_embedding` / `aget_query_embedding` / `aget_text_embedding_batch`
- PropertyGraphIndex / Retriever への注入: LlamaIndex の `Settings.embed_model` または各 index の `embed_model=...` 引数経由（要追加 spike で実証、項目 01 の追加 spike で兼ねる）

## 実測・検証結果（spike/00_smoke_ollama_embedding.py）

- import OK
- インスタンス化 OK
- 英語 `"hello world"` → dim=768
- 日本語 `"これは仕様書の章テキストです"` → dim=768、head 値も独立したベクトル
- 日本語クエリ `"認証フローはどう書かれているか"` → dim=768
- en / ja / query で dim 一致（768）

```
[OK] import: from llama_index.embeddings.ollama import OllamaEmbedding
[OK] instantiate: OllamaEmbedding
[OK] get_text_embedding('hello world') -> dim=768, head=[-0.006808166, -0.0013142417, -0.17139521]
[OK] get_text_embedding(JP) -> dim=768, head=[0.0483752, 0.011283044, -0.114529446]
[OK] get_query_embedding(JP) -> dim=768
[OK] dim consistent across en/ja/query: 768
```

## spec-grag への影響

- DESIGN §1.4「embedding は Ollama nomic-embed-text」が **API レベルで成立**
- dim=768
- 日本語入力で問題なく動作
- 未解決事項:
  - PropertyGraphIndex に `Settings.embed_model = OllamaEmbedding(...)` で注入できるか（→ spike で実証予定、項目 01 の追加 spike で兼ねる）
  - daemon 落ち / モデル未 pull 時のエラー型（spec-grag CLI の error handling 設計に必要）

## 判定

**usable**
