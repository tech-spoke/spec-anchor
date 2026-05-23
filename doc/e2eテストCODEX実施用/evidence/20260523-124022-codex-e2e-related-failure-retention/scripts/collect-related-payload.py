#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

from qdrant_client import QdrantClient


project = Path(sys.argv[1])
out = Path(sys.argv[2])
collection_override = sys.argv[3] if len(sys.argv) > 3 else None
if collection_override:
    collection = collection_override
else:
    state = json.loads(
        (project / ".spec-anchor/state/retrieval_index_state.json").read_text(
            encoding="utf-8"
        )
    )
    collection = state["collection_name"]

client = QdrantClient(url="http://localhost:6333")
records, _ = client.scroll(collection_name=collection, with_payload=True, limit=100)
payloads = [dict(point.payload or {}) for point in records]
out.write_text(
    json.dumps({"collection": collection, "payloads": payloads}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
