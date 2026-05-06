"""Embedding metadata and deterministic fallback embeddings."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from spec_grag.io import write_model_atomic as _write_model_atomic
from spec_grag.protocol import StrictModel


EMBEDDING_METADATA_VERSION = "1"
EMBEDDING_METADATA_FILENAME = "embedding_metadata.json"
STABLE_HASH_PROVIDER = "stable_hash"
STABLE_HASH_MODEL = "sha256-v1"
STABLE_HASH_DIMENSION = 8
OLLAMA_PROVIDER = "ollama"
OLLAMA_EMBEDDING_URL = "http://127.0.0.1:11434/api/embeddings"


class EmbeddingMetadata(StrictModel):
    version: str = EMBEDDING_METADATA_VERSION
    provider: str
    model: str
    dimension: int
    generated_at: str | None = None

    def identity(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "dimension": self.dimension,
        }


class EmbeddingProviderError(RuntimeError):
    """Raised when a configured embedding provider cannot return embeddings."""


def default_embedding_metadata(*, generated_at: str | None = None) -> EmbeddingMetadata:
    return EmbeddingMetadata(
        provider=STABLE_HASH_PROVIDER,
        model=STABLE_HASH_MODEL,
        dimension=STABLE_HASH_DIMENSION,
        generated_at=generated_at,
    )


def embedding_metadata_from_config(
    config: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> EmbeddingMetadata:
    embedding_config = config.get("embedding")
    if not isinstance(embedding_config, Mapping):
        return default_embedding_metadata(generated_at=generated_at)
    return EmbeddingMetadata(
        provider=str(embedding_config.get("provider", STABLE_HASH_PROVIDER)),
        model=str(embedding_config.get("model", STABLE_HASH_MODEL)),
        dimension=int(embedding_config.get("dimension", STABLE_HASH_DIMENSION)),
        generated_at=generated_at,
    )


def embedding_metadata_path(graph_storage: Path) -> Path:
    return graph_storage / EMBEDDING_METADATA_FILENAME


def load_embedding_metadata(path: Path) -> EmbeddingMetadata | None:
    if not path.exists():
        return None
    return EmbeddingMetadata.model_validate_json(path.read_text(encoding="utf-8"))


def write_embedding_metadata_atomic(path: Path, metadata: EmbeddingMetadata) -> None:
    _write_model_atomic(path, metadata)


def embedding_identity_matches(
    left: EmbeddingMetadata | None, right: EmbeddingMetadata
) -> bool:
    return left is not None and left.identity() == right.identity()


def embedding_mismatch_warning(
    previous: EmbeddingMetadata | None, current: EmbeddingMetadata
) -> str:
    if previous is None:
        return "embedding_metadata_missing:index_rebuild_required"
    return (
        "embedding_metadata_mismatch:index_rebuild_required:"
        f"previous={previous.identity()}:current={current.identity()}"
    )


def stable_embedding(text: str, *, dimensions: int = STABLE_HASH_DIMENSION) -> list[float]:
    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        payload = f"{counter}:{text}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        values.extend(round(byte / 255.0, 6) for byte in digest)
        counter += 1
    return values[:dimensions]


def embedding_for_text(
    text: str,
    metadata: EmbeddingMetadata,
    *,
    config: Mapping[str, Any] | None = None,
) -> list[float]:
    embedding_config = config if isinstance(config, Mapping) else {}
    if metadata.provider == OLLAMA_PROVIDER:
        return ollama_embedding(
            text,
            model=metadata.model,
            expected_dimension=metadata.dimension,
            timeout_sec=int(embedding_config.get("timeout_sec", 120)),
            max_retries=int(embedding_config.get("max_retries", 0)),
            retry_backoff_sec=float(embedding_config.get("retry_backoff_sec", 0.0)),
        )
    return stable_embedding(text, dimensions=metadata.dimension)


def ollama_embedding(
    text: str,
    *,
    model: str,
    expected_dimension: int,
    timeout_sec: int,
    max_retries: int,
    retry_backoff_sec: float,
) -> list[float]:
    attempts = max_retries + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            values = _ollama_embedding_once(
                text,
                model=model,
                timeout_sec=timeout_sec,
            )
            if len(values) != expected_dimension:
                raise EmbeddingProviderError(
                    "Ollama embedding dimension mismatch: "
                    f"expected {expected_dimension}, got {len(values)}"
                )
            return values
        except Exception as exc:
            last_error = exc
            if attempt >= attempts - 1:
                break
            if retry_backoff_sec > 0:
                time.sleep(retry_backoff_sec)
    raise EmbeddingProviderError(f"Ollama embedding failed: {last_error}") from last_error


def _ollama_embedding_once(
    text: str,
    *,
    model: str,
    timeout_sec: int,
) -> list[float]:
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_EMBEDDING_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise EmbeddingProviderError(str(exc)) from exc

    values = data.get("embedding")
    if not isinstance(values, list):
        raise EmbeddingProviderError("Ollama response did not contain embedding")
    try:
        return [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise EmbeddingProviderError("Ollama embedding contained non-numeric values") from exc
