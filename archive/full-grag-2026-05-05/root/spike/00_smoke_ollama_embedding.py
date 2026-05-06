"""
spike 00: OllamaEmbedding 動作確認 (項目 11 の前哨)

目的:
  - llama-index-embeddings-ollama の OllamaEmbedding が import でき、
    daemon localhost:11434 + nomic-embed-text モデルで実際に embedding を返すことを確認
  - 日本語入力での embedding 取得を確認
  - dimensionality を実測

usage:
  spike/.venv/bin/python spike/00_smoke_ollama_embedding.py
"""

from __future__ import annotations

import sys

print("=" * 60)
print("spike 00: OllamaEmbedding smoke")
print("=" * 60)

# 1. import 確認
try:
    from llama_index.embeddings.ollama import OllamaEmbedding

    print(f"[OK] import: from llama_index.embeddings.ollama import OllamaEmbedding")
except Exception as e:
    print(f"[FAIL] import: {e}")
    sys.exit(1)

# 2. インスタンス化
try:
    emb = OllamaEmbedding(
        model_name="nomic-embed-text",
        base_url="http://localhost:11434",
    )
    print(f"[OK] instantiate: {type(emb).__name__}")
except Exception as e:
    print(f"[FAIL] instantiate: {e}")
    sys.exit(1)

# 3. 英語 embedding
try:
    v_en = emb.get_text_embedding("hello world")
    print(f"[OK] get_text_embedding('hello world') -> dim={len(v_en)}, head={v_en[:3]}")
except Exception as e:
    print(f"[FAIL] english embedding: {e}")
    sys.exit(1)

# 4. 日本語 embedding
try:
    v_ja = emb.get_text_embedding("これは仕様書の章テキストです")
    print(
        f"[OK] get_text_embedding(JP) -> dim={len(v_ja)}, head={v_ja[:3]}"
    )
except Exception as e:
    print(f"[FAIL] japanese embedding: {e}")
    sys.exit(1)

# 5. クエリ用 embedding
try:
    v_q = emb.get_query_embedding("認証フローはどう書かれているか")
    print(f"[OK] get_query_embedding(JP) -> dim={len(v_q)}")
except Exception as e:
    print(f"[FAIL] query embedding: {e}")
    sys.exit(1)

# 6. dimensionality 一致確認
if len(v_en) == len(v_ja) == len(v_q):
    print(f"[OK] dim consistent across en/ja/query: {len(v_en)}")
else:
    print(f"[WARN] dim mismatch: en={len(v_en)} ja={len(v_ja)} q={len(v_q)}")

print("=" * 60)
print("DONE")
print("=" * 60)
