"""Claim Retrieval stage helpers for SpecClaim conflict candidates.

This module owns the claim-level retrieval step between SpecClaim extraction
and LLM triage. It indexes one SpecClaim per vector point, gathers
dense/sparse/probe hits, fuses pair ranks with RRF, and writes retrieval-only
conflict candidate pairs.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from spec_anchor.retrieval_index import (
    BGE_M3_DENSE_SIZE,
    DEFAULT_RRF_K,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    BgeM3EmbeddingProvider,
    FakeBgeM3EmbeddingProvider,
    FlagEmbeddingBgeM3Provider,
    SparseVector,
)


CLAIM_RETRIEVAL_SCHEMA_VERSION = "claim-retrieval-v1"
CONFLICT_CANDIDATE_SCHEMA_VERSION = "conflict-candidate-v1"
CONFLICT_CANDIDATE_PAIRS_JSONL_FILENAME = "conflict_candidate_pairs.jsonl"
CONFLICT_CANDIDATE_PAIRS_STATE_FILENAME = "conflict_candidate_pairs_state.json"
DEFAULT_CLAIM_COLLECTION = "spec_anchor_claim"

DENSE_CLAIM_RETRIEVAL = "dense_claim_retrieval"
SPARSE_KEY_CLAIM_RETRIEVAL = "sparse_key_claim_retrieval"
CONFLICT_PROBE_CLAIM_RETRIEVAL = "conflict_probe_claim_retrieval"
CLAIM_RETRIEVAL_ROUTE = "claim_retrieval"
RETRIEVAL_SOURCES = (
    DENSE_CLAIM_RETRIEVAL,
    SPARSE_KEY_CLAIM_RETRIEVAL,
    CONFLICT_PROBE_CLAIM_RETRIEVAL,
)

_CLAIM_POINT_ID_NAMESPACE = uuid.UUID("70f11e44-bf77-59e7-aec7-1e19302f4a0b")
_EMPTY_FINGERPRINT = "sha256:" + ("0" * 64)


@dataclass(frozen=True)
class ClaimRetrievalConfig:
    claim_collection: str = DEFAULT_CLAIM_COLLECTION
    dense_top_k: int = 12
    sparse_top_k: int = 20
    per_claim_top_k: int = 10
    per_section_top_k: int = 20
    per_target_top_k: int = 20
    global_candidate_top_k: int = 100
    min_dense_score: float = 0.55
    min_sparse_score: float = 0.0
    rank_fusion: str = "rrf"
    rrf_k: int = DEFAULT_RRF_K
    allow_same_section_claim_pair: bool = True
    allow_same_source_file_claim_pair: bool = True
    source_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            DENSE_CLAIM_RETRIEVAL: 1.0,
            SPARSE_KEY_CLAIM_RETRIEVAL: 1.0,
            CONFLICT_PROBE_CLAIM_RETRIEVAL: 1.0,
        }
    )

    def fingerprint(self) -> str:
        return _sha256_json(
            {
                "schema_version": CLAIM_RETRIEVAL_SCHEMA_VERSION,
                "claim_collection": self.claim_collection,
                "dense_top_k": self.dense_top_k,
                "sparse_top_k": self.sparse_top_k,
                "per_claim_top_k": self.per_claim_top_k,
                "per_section_top_k": self.per_section_top_k,
                "per_target_top_k": self.per_target_top_k,
                "global_candidate_top_k": self.global_candidate_top_k,
                "min_dense_score": self.min_dense_score,
                "min_sparse_score": self.min_sparse_score,
                "rank_fusion": self.rank_fusion,
                "rrf_k": self.rrf_k,
                "allow_same_section_claim_pair": self.allow_same_section_claim_pair,
                "allow_same_source_file_claim_pair": self.allow_same_source_file_claim_pair,
                "source_weights": dict(sorted(self.source_weights.items())),
            }
        )


@dataclass(frozen=True)
class ClaimRetrievalHit:
    claim_uid: str
    score: float
    payload: dict[str, Any]
    point_id: str | int | None = None


class ClaimRetrievalBackend(Protocol):
    def dense_search(self, query: str, top_k: int) -> Sequence[Any]:
        """Return dense hits for one claim query."""

    def sparse_search(self, query: str, top_k: int) -> Sequence[Any]:
        """Return sparse hits for one claim query."""


@dataclass(frozen=True)
class ClaimRetrievalResult:
    candidates: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONFLICT_CANDIDATE_SCHEMA_VERSION,
            "claim_retrieval_schema_version": CLAIM_RETRIEVAL_SCHEMA_VERSION,
            "candidates": self.candidates,
            "diagnostics": self.diagnostics,
            "state": self.state,
        }


class InMemoryClaimRetrievalBackend:
    """Deterministic in-process claim retriever for tests and local runs."""

    def __init__(
        self,
        claims: Sequence[Mapping[str, Any]],
        *,
        embedding_provider: BgeM3EmbeddingProvider | None = None,
        dense_enabled: bool = True,
        sparse_enabled: bool = True,
    ) -> None:
        self.payloads = build_claim_payloads(claims)
        self.provider = embedding_provider or FakeBgeM3EmbeddingProvider(
            dense_enabled=dense_enabled,
            sparse_enabled=sparse_enabled,
        )
        self.dense_enabled = dense_enabled
        self.sparse_enabled = sparse_enabled
        self._embeddings = self.provider.embed_documents(
            [str(payload.get("text") or "") for payload in self.payloads]
        ).embeddings

    def dense_search(self, query: str, top_k: int) -> list[ClaimRetrievalHit]:
        if not self.dense_enabled or not query.strip() or top_k <= 0:
            return []
        query_embedding = self.provider.embed_query(query)
        if query_embedding.dense is None:
            return []
        hits: list[ClaimRetrievalHit] = []
        for payload, embedding in zip(self.payloads, self._embeddings, strict=False):
            if embedding.dense is None:
                continue
            score = _cosine_similarity(query_embedding.dense, embedding.dense)
            if score > 0:
                hits.append(_hit_from_payload(payload, score=score))
        return _top_claim_hits(hits, top_k)

    def sparse_search(self, query: str, top_k: int) -> list[ClaimRetrievalHit]:
        if not self.sparse_enabled or not query.strip() or top_k <= 0:
            return []
        query_embedding = self.provider.embed_query(query)
        if query_embedding.sparse is None:
            return []
        hits: list[ClaimRetrievalHit] = []
        for payload, embedding in zip(self.payloads, self._embeddings, strict=False):
            if embedding.sparse is None:
                continue
            score = _sparse_dot(query_embedding.sparse, embedding.sparse)
            if score > 0:
                hits.append(_hit_from_payload(payload, score=score))
        return _top_claim_hits(hits, top_k)


class QdrantClaimRetriever:
    """Qdrant-backed claim retriever for the claim-level collection."""

    def __init__(
        self,
        *,
        url: str = "http://localhost:6333",
        collection: str = DEFAULT_CLAIM_COLLECTION,
        embedding_provider: BgeM3EmbeddingProvider | None = None,
    ) -> None:
        from qdrant_client import QdrantClient  # type: ignore[import-not-found]

        self.url = url
        self.collection = collection
        self.client = QdrantClient(url)
        self.provider = embedding_provider or FlagEmbeddingBgeM3Provider(
            allow_real_provider=True,
            use_fp16=False,
        )

    def dense_search(self, query: str, top_k: int) -> list[ClaimRetrievalHit]:
        if not query.strip() or top_k <= 0:
            return []
        query_embedding = self.provider.embed_query(query)
        if query_embedding.dense is None:
            return []
        points = self.client.query_points(
            collection_name=self.collection,
            query=[float(value) for value in query_embedding.dense],
            using=DENSE_VECTOR_NAME,
            limit=top_k,
        ).points
        return [_hit_from_qdrant_point(point) for point in points]

    def sparse_search(self, query: str, top_k: int) -> list[ClaimRetrievalHit]:
        if not query.strip() or top_k <= 0:
            return []
        query_embedding = self.provider.embed_query(query)
        sparse = query_embedding.sparse
        if sparse is None or not sparse.indices:
            return []
        from qdrant_client import models as qdrant_models  # type: ignore[import-not-found]

        points = self.client.query_points(
            collection_name=self.collection,
            query=qdrant_models.SparseVector(
                indices=list(sparse.indices),
                values=[float(value) for value in sparse.values],
            ),
            using=SPARSE_VECTOR_NAME,
            limit=top_k,
        ).points
        return [_hit_from_qdrant_point(point) for point in points]


def stable_claim_point_id(claim_uid: str) -> str:
    return str(uuid.uuid5(_CLAIM_POINT_ID_NAMESPACE, claim_uid))


def build_claim_payloads(claims: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    payloads = [_build_claim_payload(claim) for claim in claims]
    return sorted(payloads, key=lambda payload: str(payload.get("claim_uid") or ""))


def upsert_qdrant_claim_collection(
    claims: Sequence[Mapping[str, Any]],
    *,
    url: str = "http://localhost:6333",
    collection: str = DEFAULT_CLAIM_COLLECTION,
    embedding_provider: BgeM3EmbeddingProvider | None = None,
    recreate: bool = True,
    claims_to_upsert: Sequence[Mapping[str, Any]] | None = None,
    claims_to_delete: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Upsert one BGE-M3 dense+sparse vector per SpecClaim into Qdrant."""

    from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    from qdrant_client import models as qdrant_models  # type: ignore[import-not-found]

    client = QdrantClient(url)
    payloads_to_upsert = build_claim_payloads(
        claims if claims_to_upsert is None or recreate else claims_to_upsert
    )
    deleted_claim_uids = sorted({str(uid) for uid in (claims_to_delete or []) if str(uid)})
    embedding_inputs = [str(payload.get("text") or "") for payload in payloads_to_upsert]
    provider = embedding_provider
    if embedding_inputs:
        provider = provider or FlagEmbeddingBgeM3Provider(
            allow_real_provider=True,
            use_fp16=False,
        )
        embeddings = provider.embed_documents(embedding_inputs).embeddings
    else:
        embeddings = []

    if recreate:
        client.recreate_collection(
            collection_name=collection,
            vectors_config={
                DENSE_VECTOR_NAME: qdrant_models.VectorParams(
                    size=BGE_M3_DENSE_SIZE,
                    distance=qdrant_models.Distance.COSINE,
                )
            },
            sparse_vectors_config={SPARSE_VECTOR_NAME: qdrant_models.SparseVectorParams()},
        )
    elif deleted_claim_uids:
        client.delete(
            collection_name=collection,
            points_selector=qdrant_models.PointIdsList(
                points=[stable_claim_point_id(uid) for uid in deleted_claim_uids]
            ),
        )

    points = []
    for payload, embedding in zip(payloads_to_upsert, embeddings, strict=True):
        sparse = embedding.sparse or SparseVector()
        points.append(
            qdrant_models.PointStruct(
                id=stable_claim_point_id(str(payload["claim_uid"])),
                vector={
                    DENSE_VECTOR_NAME: [float(value) for value in (embedding.dense or [])],
                    SPARSE_VECTOR_NAME: qdrant_models.SparseVector(
                        indices=list(sparse.indices),
                        values=[float(value) for value in sparse.values],
                    ),
                },
                payload=payload,
            )
        )
    if points:
        client.upsert(collection_name=collection, points=points)

    return {
        "status": "success",
        "collection": collection,
        "claim_count": len(claims),
        "claims_upserted_count": len(payloads_to_upsert),
        "claims_deleted_count": len(deleted_claim_uids),
        "embed_documents_input_size": len(embedding_inputs),
        "recreate": recreate,
        "partial_requested": claims_to_upsert is not None or claims_to_delete is not None,
        "embedding_provider": getattr(provider, "provider_id", None),
        "embedding_model": getattr(provider, "model", None),
    }


def generate_claim_retrieval_result(
    claims: Sequence[Mapping[str, Any]],
    *,
    seed_claim_uids: Sequence[str] | None = None,
    backend: ClaimRetrievalBackend | None = None,
    config: ClaimRetrievalConfig | None = None,
    previous_candidates: Sequence[Mapping[str, Any]] | None = None,
    previous_state: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
    state_path: str | Path | None = None,
    generated_at: str | None = None,
) -> ClaimRetrievalResult:
    config = config or ClaimRetrievalConfig()
    if config.rank_fusion != "rrf":
        raise ValueError("Claim Retrieval supports rank_fusion='rrf' only")
    if config.rrf_k <= 0:
        raise ValueError("rrf_k must be positive")

    claims_by_uid = _claims_by_uid(claims)
    current_claim_uids = set(claims_by_uid)
    if seed_claim_uids is None:
        seeds = sorted(current_claim_uids)
    else:
        seeds = sorted({str(uid) for uid in seed_claim_uids if str(uid) in claims_by_uid})
    backend = backend or InMemoryClaimRetrievalBackend(list(claims_by_uid.values()))

    loaded_previous_candidates = list(previous_candidates or [])
    if previous_candidates is None and output_path is not None:
        candidate_file = _jsonl_path(output_path)
        if candidate_file.exists():
            loaded_previous_candidates = read_conflict_candidate_pairs_jsonl(candidate_file)
    loaded_previous_state = dict(previous_state or {})
    if previous_state is None and state_path is not None:
        loaded_previous_state = read_conflict_candidate_pairs_state(state_path)

    previous_retrieval_state = _retrieval_state(loaded_previous_state)
    reusable_candidates, reuse_diagnostics = _reusable_previous_candidates(
        loaded_previous_candidates,
        claims_by_uid=claims_by_uid,
        seed_claim_uids=set(seeds),
        previous_retrieval_state=previous_retrieval_state,
        config_fingerprint=config.fingerprint(),
    )

    pair_records = {
        _pair_key_from_candidate(candidate): _pair_record_from_candidate(candidate)
        for candidate in reusable_candidates
        if _pair_key_from_candidate(candidate) is not None
    }
    generated_pair_records, generation_diagnostics = _collect_pair_records(
        claims_by_uid,
        seeds=seeds,
        backend=backend,
        config=config,
    )
    for key, record in generated_pair_records.items():
        pair_records[key] = _merge_pair_records(pair_records.get(key), record)

    ranked_records = _rank_pair_records(pair_records, config=config)
    limited_records, limit_diagnostics = _apply_candidate_limits(
        ranked_records,
        claims_by_uid=claims_by_uid,
        config=config,
    )
    candidates = [
        _build_candidate(record, claims_by_uid=claims_by_uid, display_index=index)
        for index, record in enumerate(limited_records, start=1)
    ]

    diagnostics = {
        "status": "success",
        "schema_version": CLAIM_RETRIEVAL_SCHEMA_VERSION,
        "candidate_schema_version": CONFLICT_CANDIDATE_SCHEMA_VERSION,
        "claim_count": len(claims_by_uid),
        "seed_claim_count": len(seeds),
        "generated_pair_count": len(generated_pair_records),
        "reused_candidate_count": len(reusable_candidates),
        "candidate_count": len(candidates),
        "rank_fusion": "rrf",
        "rrf_k": config.rrf_k,
        "claim_retrieval_config_fingerprint": config.fingerprint(),
        **generation_diagnostics,
        **reuse_diagnostics,
        **limit_diagnostics,
    }
    state = build_conflict_candidate_pairs_state(
        list(claims_by_uid.values()),
        candidates,
        config=config,
        diagnostics=diagnostics,
        generated_at=generated_at,
    )
    if loaded_previous_state:
        merged_state = dict(loaded_previous_state)
        merged_state["schema_version"] = CONFLICT_CANDIDATE_SCHEMA_VERSION
        merged_state["generated_at"] = generated_at
        merged_state["retrieval"] = state["retrieval"]
        state = merged_state

    if output_path is not None:
        write_conflict_candidate_pairs_jsonl(
            output_path,
            candidates,
            active_claim_uids=sorted(current_claim_uids),
        )
    if state_path is not None:
        write_conflict_candidate_pairs_state(state_path, state)

    return ClaimRetrievalResult(
        candidates=candidates,
        diagnostics=diagnostics,
        state=state,
    )


def build_conflict_candidate_pairs_state(
    claims: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    *,
    config: ClaimRetrievalConfig | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    config = config or ClaimRetrievalConfig()
    diagnostics = dict(diagnostics or {})
    claim_hash_by_uid = {
        str(claim.get("claim_uid") or ""): str(claim.get("claim_hash") or "")
        for claim in claims
        if str(claim.get("claim_uid") or "")
    }
    retrieval_hash_by_uid = {
        str(claim.get("claim_uid") or ""): str(claim.get("retrieval_hash") or "")
        for claim in claims
        if str(claim.get("claim_uid") or "")
    }
    candidate_uids = sorted(
        {
            str(candidate.get("candidate_uid") or "")
            for candidate in candidates
            if str(candidate.get("candidate_uid") or "")
        }
    )
    retrieval_state = {
        "schema_version": CLAIM_RETRIEVAL_SCHEMA_VERSION,
        "spec_claims_fingerprint": spec_claims_fingerprint(claims),
        "claim_uids": sorted(claim_hash_by_uid),
        "claim_hashes": sorted(set(claim_hash_by_uid.values())),
        "claim_hash_by_uid": dict(sorted(claim_hash_by_uid.items())),
        "retrieval_hashes": sorted(set(retrieval_hash_by_uid.values())),
        "retrieval_hash_by_uid": dict(sorted(retrieval_hash_by_uid.items())),
        "candidate_uids": candidate_uids,
        "claim_retrieval_config_fingerprint": config.fingerprint(),
        "truncated_candidate_sources": list(
            diagnostics.get("truncated_candidate_sources") or []
        ),
        "truncated_pair_count": int(diagnostics.get("truncated_pair_count") or 0),
    }
    return {
        "schema_version": CONFLICT_CANDIDATE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "retrieval": retrieval_state,
    }


def spec_claims_fingerprint(claims: Sequence[Mapping[str, Any]]) -> str:
    entries = [
        {
            "claim_uid": str(claim.get("claim_uid") or ""),
            "claim_hash": str(claim.get("claim_hash") or ""),
            "retrieval_hash": str(claim.get("retrieval_hash") or ""),
        }
        for claim in claims
        if str(claim.get("claim_uid") or "")
    ]
    entries.sort(key=lambda item: item["claim_uid"])
    if not entries:
        return _EMPTY_FINGERPRINT
    return _sha256_json(entries)


def read_conflict_candidate_pairs_state(path: str | Path) -> dict[str, Any]:
    state_path = _state_path(path)
    if not state_path.exists():
        return {}
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def write_conflict_candidate_pairs_state(
    path: str | Path,
    state: Mapping[str, Any],
) -> Path:
    state_path = _state_path(path)
    _atomic_write_json(state_path, dict(state))
    return state_path


def read_conflict_candidate_pairs_jsonl(path: str | Path) -> list[dict[str, Any]]:
    jsonl_path = _jsonl_path(path)
    if not jsonl_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def write_conflict_candidate_pairs_jsonl(
    path: str | Path,
    candidates: Sequence[Mapping[str, Any]],
    *,
    active_claim_uids: Sequence[str] | None = None,
) -> Path:
    jsonl_path = _jsonl_path(path)
    active = set(active_claim_uids or [])
    records = [
        dict(candidate)
        for candidate in candidates
        if active_claim_uids is None
        or (
            str(candidate.get("left_claim_uid") or "") in active
            and str(candidate.get("right_claim_uid") or "") in active
        )
    ]
    records.sort(key=lambda item: str(item.get("candidate_uid") or ""))
    _atomic_write_jsonl(jsonl_path, records)
    return jsonl_path


def candidate_uid_for_claim_pair(left_claim_uid: str, right_claim_uid: str) -> str:
    left, right = sorted([str(left_claim_uid), str(right_claim_uid)])
    return "candidate:sha256:" + hashlib.sha256(
        _stable_json([left, right]).encode("utf-8")
    ).hexdigest()


def _build_claim_payload(claim: Mapping[str, Any]) -> dict[str, Any]:
    claim_uid = _required_text(claim, "claim_uid")
    retrieval = _required_mapping(claim, "retrieval")
    embedding_text = str(retrieval.get("embedding_text") or "").strip()
    sparse_keys = [str(value) for value in (retrieval.get("sparse_keys") or [])]
    conflict_probes = [str(value) for value in (retrieval.get("conflict_probes") or [])]
    if not embedding_text:
        raise ValueError("SpecClaim retrieval.embedding_text is required")
    return {
        "claim_uid": claim_uid,
        "stable_chunk_uid": claim_uid,
        "target": _required_text(claim, "target"),
        "target_aliases": [str(value) for value in (claim.get("target_aliases") or [])],
        "claim_text": _required_text(claim, "claim_text"),
        "claim_hash": _required_text(claim, "claim_hash"),
        "source_section_id": _required_text(claim, "source_section_id"),
        "section_uid": str(claim.get("section_uid") or claim.get("source_section_id") or ""),
        "source_document_id": _source_document_id(claim),
        "source_hash": str(claim.get("source_hash") or ""),
        "evidence_span": _required_text(claim, "evidence_span"),
        "evidence_start": _int_or_none(claim.get("evidence_start")),
        "evidence_end": _int_or_none(claim.get("evidence_end")),
        "evidence_hash": str(claim.get("evidence_hash") or ""),
        "retrieval_hash": _required_text(claim, "retrieval_hash"),
        "retrieval": {
            "embedding_text": embedding_text,
            "sparse_keys": sparse_keys,
            "conflict_probes": conflict_probes,
        },
        "text": embedding_text,
    }


def _collect_pair_records(
    claims_by_uid: Mapping[str, Mapping[str, Any]],
    *,
    seeds: Sequence[str],
    backend: ClaimRetrievalBackend,
    config: ClaimRetrievalConfig,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    pair_records: dict[tuple[str, str], dict[str, Any]] = {}
    channel_counts: Counter[str] = Counter()
    same_section_skipped = 0
    same_file_skipped = 0
    missing_claim_hit_count = 0

    for seed_uid in seeds:
        seed_claim = claims_by_uid[seed_uid]
        retrieval = dict(seed_claim.get("retrieval") or {})
        channel_queries = (
            (
                DENSE_CLAIM_RETRIEVAL,
                str(retrieval.get("embedding_text") or ""),
                config.dense_top_k,
                config.min_dense_score,
                backend.dense_search,
            ),
            (
                SPARSE_KEY_CLAIM_RETRIEVAL,
                " ".join(str(value) for value in retrieval.get("sparse_keys") or []),
                config.sparse_top_k,
                config.min_sparse_score,
                backend.sparse_search,
            ),
            (
                CONFLICT_PROBE_CLAIM_RETRIEVAL,
                " ".join(str(value) for value in retrieval.get("conflict_probes") or []),
                config.sparse_top_k,
                config.min_sparse_score,
                backend.sparse_search,
            ),
        )
        for source, query, top_k, min_score, search in channel_queries:
            hits = [_coerce_hit(hit) for hit in search(query, top_k)]
            accepted_rank = 0
            for hit in _top_claim_hits(hits, top_k):
                if hit.claim_uid == seed_uid:
                    continue
                if hit.score < min_score:
                    continue
                target_claim = claims_by_uid.get(hit.claim_uid)
                if target_claim is None:
                    missing_claim_hit_count += 1
                    continue
                if (
                    not config.allow_same_section_claim_pair
                    and _section_uid(seed_claim) == _section_uid(target_claim)
                ):
                    same_section_skipped += 1
                    continue
                if (
                    not config.allow_same_source_file_claim_pair
                    and _source_document_id(seed_claim) == _source_document_id(target_claim)
                ):
                    same_file_skipped += 1
                    continue
                accepted_rank += 1
                key = _pair_key(seed_uid, hit.claim_uid)
                record = pair_records.setdefault(
                    key,
                    {
                        "left_claim_uid": key[0],
                        "right_claim_uid": key[1],
                        "source_ranks": {},
                        "source_scores": {},
                    },
                )
                current_rank = record["source_ranks"].get(source)
                if current_rank is None or accepted_rank < current_rank:
                    record["source_ranks"][source] = accepted_rank
                    record["source_scores"][source] = hit.score
                channel_counts[source] += 1

    return pair_records, {
        "retrieval_channel_counts": dict(sorted(channel_counts.items())),
        "same_section_claim_pairs_skipped": same_section_skipped,
        "same_source_file_claim_pairs_skipped": same_file_skipped,
        "missing_claim_hit_count": missing_claim_hit_count,
    }


def _rank_pair_records(
    pair_records: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    config: ClaimRetrievalConfig,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for key, record in pair_records.items():
        source_ranks = dict(record.get("source_ranks") or {})
        score = 0.0
        for source, rank in source_ranks.items():
            weight = float(config.source_weights.get(source, 1.0))
            score += weight / float(config.rrf_k + int(rank))
        if not source_ranks:
            score = float(record.get("rrf_score") or 0.0)
        payload = dict(record)
        payload["left_claim_uid"] = key[0]
        payload["right_claim_uid"] = key[1]
        payload["rrf_score"] = score
        payload["retrieval_sources"] = [
            source for source in RETRIEVAL_SOURCES if source in source_ranks
        ] or list(record.get("retrieval_sources") or [])
        ranked.append(payload)
    return sorted(
        ranked,
        key=lambda item: (
            -float(item.get("rrf_score") or 0.0),
            str(item.get("left_claim_uid") or ""),
            str(item.get("right_claim_uid") or ""),
        ),
    )


def _apply_candidate_limits(
    ranked_records: Sequence[Mapping[str, Any]],
    *,
    claims_by_uid: Mapping[str, Mapping[str, Any]],
    config: ClaimRetrievalConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    per_claim: Counter[str] = Counter()
    per_section: Counter[str] = Counter()
    per_target: Counter[str] = Counter()
    truncated_sources: set[str] = set()
    truncated_pair_count = 0

    for record in ranked_records:
        if len(accepted) >= config.global_candidate_top_k:
            truncated_sources.add("global_candidate_top_k")
            truncated_pair_count += 1
            continue
        left_uid = str(record.get("left_claim_uid") or "")
        right_uid = str(record.get("right_claim_uid") or "")
        left = claims_by_uid[left_uid]
        right = claims_by_uid[right_uid]
        claim_limit_hit = (
            per_claim[left_uid] >= config.per_claim_top_k
            or per_claim[right_uid] >= config.per_claim_top_k
        )
        section_keys = {_section_uid(left), _section_uid(right)}
        section_limit_hit = any(
            per_section[key] >= config.per_section_top_k for key in section_keys if key
        )
        target_key = _target_bucket(left, right)
        target_limit_hit = per_target[target_key] >= config.per_target_top_k
        if claim_limit_hit:
            truncated_sources.add("per_claim_top_k")
        if section_limit_hit:
            truncated_sources.add("per_section_top_k")
        if target_limit_hit:
            truncated_sources.add("per_target_top_k")
        if claim_limit_hit or section_limit_hit or target_limit_hit:
            truncated_pair_count += 1
            continue
        payload = dict(record)
        accepted.append(payload)
        per_claim[left_uid] += 1
        per_claim[right_uid] += 1
        for key in section_keys:
            if key:
                per_section[key] += 1
        per_target[target_key] += 1

    return accepted, {
        "truncated_candidate_sources": sorted(truncated_sources),
        "truncated_pair_count": truncated_pair_count,
    }


def _build_candidate(
    record: Mapping[str, Any],
    *,
    claims_by_uid: Mapping[str, Mapping[str, Any]],
    display_index: int,
) -> dict[str, Any]:
    left_uid = str(record.get("left_claim_uid") or "")
    right_uid = str(record.get("right_claim_uid") or "")
    left = claims_by_uid[left_uid]
    right = claims_by_uid[right_uid]
    retrieval_sources = [
        source
        for source in RETRIEVAL_SOURCES
        if source in set(record.get("retrieval_sources") or [])
    ]
    if not retrieval_sources:
        retrieval_sources = [
            source
            for source in RETRIEVAL_SOURCES
            if source in dict(record.get("source_ranks") or {})
        ]
    return {
        "candidate_uid": candidate_uid_for_claim_pair(left_uid, right_uid),
        "display_id": f"CC-{display_index:05d}",
        "left_claim_uid": left_uid,
        "right_claim_uid": right_uid,
        "left_claim_hash": str(left.get("claim_hash") or ""),
        "right_claim_hash": str(right.get("claim_hash") or ""),
        "left_retrieval_hash": str(left.get("retrieval_hash") or ""),
        "right_retrieval_hash": str(right.get("retrieval_hash") or ""),
        "left_section_uid": _section_uid(left),
        "right_section_uid": _section_uid(right),
        "shared_target": _shared_target(left, right),
        "primary_route": CLAIM_RETRIEVAL_ROUTE,
        "routes": [{"route": CLAIM_RETRIEVAL_ROUTE, "is_primary_route": True}],
        "retrieval_sources": retrieval_sources,
        "signals": _signals(left, right),
        "triage": None,
        "evidence": [_evidence_entry(left), _evidence_entry(right)],
    }


def _reusable_previous_candidates(
    previous_candidates: Sequence[Mapping[str, Any]],
    *,
    claims_by_uid: Mapping[str, Mapping[str, Any]],
    seed_claim_uids: set[str],
    previous_retrieval_state: Mapping[str, Any],
    config_fingerprint: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not previous_candidates or not previous_retrieval_state:
        return [], {"deleted_claim_pairs_excluded": 0, "reuse_skipped_candidate_count": 0}
    if (
        str(previous_retrieval_state.get("schema_version") or "")
        != CLAIM_RETRIEVAL_SCHEMA_VERSION
        or str(previous_retrieval_state.get("claim_retrieval_config_fingerprint") or "")
        != config_fingerprint
    ):
        return [], {
            "deleted_claim_pairs_excluded": 0,
            "reuse_skipped_candidate_count": len(previous_candidates),
        }
    claim_hash_by_uid = dict(previous_retrieval_state.get("claim_hash_by_uid") or {})
    retrieval_hash_by_uid = dict(previous_retrieval_state.get("retrieval_hash_by_uid") or {})
    reusable: list[dict[str, Any]] = []
    deleted = 0
    skipped = 0
    for candidate in previous_candidates:
        left_uid = str(candidate.get("left_claim_uid") or "")
        right_uid = str(candidate.get("right_claim_uid") or "")
        if left_uid not in claims_by_uid or right_uid not in claims_by_uid:
            deleted += 1
            continue
        if left_uid in seed_claim_uids or right_uid in seed_claim_uids:
            skipped += 1
            continue
        left = claims_by_uid[left_uid]
        right = claims_by_uid[right_uid]
        if claim_hash_by_uid.get(left_uid) != str(left.get("claim_hash") or ""):
            skipped += 1
            continue
        if claim_hash_by_uid.get(right_uid) != str(right.get("claim_hash") or ""):
            skipped += 1
            continue
        if retrieval_hash_by_uid.get(left_uid) != str(left.get("retrieval_hash") or ""):
            skipped += 1
            continue
        if retrieval_hash_by_uid.get(right_uid) != str(right.get("retrieval_hash") or ""):
            skipped += 1
            continue
        reusable.append(dict(candidate))
    return reusable, {
        "deleted_claim_pairs_excluded": deleted,
        "reuse_skipped_candidate_count": skipped,
    }


def _pair_record_from_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    key = _pair_key_from_candidate(candidate)
    if key is None:
        return {}
    return {
        "left_claim_uid": key[0],
        "right_claim_uid": key[1],
        "source_ranks": {},
        "source_scores": {},
        "retrieval_sources": list(candidate.get("retrieval_sources") or []),
        "rrf_score": float(candidate.get("rrf_score") or 0.0),
    }


def _merge_pair_records(
    current: Mapping[str, Any] | None,
    incoming: Mapping[str, Any],
) -> dict[str, Any]:
    if current is None:
        return dict(incoming)
    merged = dict(current)
    source_ranks = dict(current.get("source_ranks") or {})
    source_scores = dict(current.get("source_scores") or {})
    for source, rank in dict(incoming.get("source_ranks") or {}).items():
        current_rank = source_ranks.get(source)
        if current_rank is None or int(rank) < int(current_rank):
            source_ranks[source] = int(rank)
            source_scores[source] = dict(incoming.get("source_scores") or {}).get(source)
    merged["source_ranks"] = source_ranks
    merged["source_scores"] = source_scores
    merged["retrieval_sources"] = sorted(
        set(merged.get("retrieval_sources") or [])
        | set(incoming.get("retrieval_sources") or [])
        | set(source_ranks)
    )
    return merged


def _claims_by_uid(claims: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_uid: dict[str, Mapping[str, Any]] = {}
    for claim in claims:
        uid = str(claim.get("claim_uid") or "")
        if not uid:
            continue
        by_uid[uid] = dict(claim)
    return dict(sorted(by_uid.items()))


def _pair_key(left_uid: str, right_uid: str) -> tuple[str, str]:
    left, right = sorted([str(left_uid), str(right_uid)])
    return left, right


def _pair_key_from_candidate(candidate: Mapping[str, Any]) -> tuple[str, str] | None:
    left_uid = str(candidate.get("left_claim_uid") or "")
    right_uid = str(candidate.get("right_claim_uid") or "")
    if not left_uid or not right_uid or left_uid == right_uid:
        return None
    return _pair_key(left_uid, right_uid)


def _coerce_hit(hit: Any) -> ClaimRetrievalHit:
    if isinstance(hit, ClaimRetrievalHit):
        return hit
    payload = dict(getattr(hit, "payload", None) or {})
    if isinstance(hit, Mapping):
        payload = dict(hit.get("payload") or hit)
        score = float(hit.get("score") or payload.get("score") or 0.0)
        claim_uid = str(hit.get("claim_uid") or payload.get("claim_uid") or "")
        point_id = hit.get("point_id") or payload.get("id")
    else:
        score = float(getattr(hit, "score", 0.0) or 0.0)
        claim_uid = str(getattr(hit, "claim_uid", "") or payload.get("claim_uid") or "")
        point_id = getattr(hit, "point_id", None)
    return ClaimRetrievalHit(
        claim_uid=claim_uid,
        score=score,
        payload=payload,
        point_id=point_id,
    )


def _hit_from_payload(payload: Mapping[str, Any], *, score: float) -> ClaimRetrievalHit:
    return ClaimRetrievalHit(
        claim_uid=str(payload.get("claim_uid") or ""),
        score=float(score),
        payload=dict(payload),
        point_id=payload.get("id"),
    )


def _hit_from_qdrant_point(point: Any) -> ClaimRetrievalHit:
    payload = dict(getattr(point, "payload", None) or {})
    return ClaimRetrievalHit(
        claim_uid=str(payload.get("claim_uid") or ""),
        score=float(getattr(point, "score", 0.0) or 0.0),
        payload=payload,
        point_id=getattr(point, "id", None),
    )


def _top_claim_hits(hits: Sequence[ClaimRetrievalHit], limit: int) -> list[ClaimRetrievalHit]:
    if limit <= 0:
        return []
    return sorted(
        hits,
        key=lambda hit: (-float(hit.score), str(hit.claim_uid), str(hit.point_id or "")),
    )[:limit]


def _evidence_entry(claim: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "claim_uid": str(claim.get("claim_uid") or ""),
        "section_uid": _section_uid(claim),
        "evidence_span": str(claim.get("evidence_span") or ""),
        "evidence_start": _int_or_none(claim.get("evidence_start")),
        "evidence_end": _int_or_none(claim.get("evidence_end")),
        "evidence_hash": str(claim.get("evidence_hash") or ""),
    }


def _signals(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    signals: list[str] = []
    if _shared_target(left, right):
        signals.append("semantic_same_target")
    return signals


def _shared_target(left: Mapping[str, Any], right: Mapping[str, Any]) -> str:
    left_terms = _target_terms(left)
    right_terms = _target_terms(right)
    overlap = sorted(left_terms & right_terms)
    if overlap:
        return overlap[0]
    if _normalize_term(str(left.get("target") or "")) == _normalize_term(
        str(right.get("target") or "")
    ):
        return str(left.get("target") or "")
    return ""


def _target_bucket(left: Mapping[str, Any], right: Mapping[str, Any]) -> str:
    return _shared_target(left, right) or _normalize_term(str(left.get("target") or ""))


def _target_terms(claim: Mapping[str, Any]) -> set[str]:
    values = [str(claim.get("target") or "")]
    values.extend(str(value) for value in (claim.get("target_aliases") or []))
    return {_normalize_term(value) for value in values if _normalize_term(value)}


def _normalize_term(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _section_uid(claim: Mapping[str, Any]) -> str:
    return str(claim.get("section_uid") or claim.get("source_section_id") or "")


def _source_document_id(claim: Mapping[str, Any]) -> str:
    source_document_id = str(claim.get("source_document_id") or "")
    if source_document_id:
        return source_document_id
    source_section_id = str(claim.get("source_section_id") or "")
    return source_section_id.split("#", 1)[0]


def _retrieval_state(state: Mapping[str, Any]) -> dict[str, Any]:
    retrieval = state.get("retrieval") if isinstance(state, Mapping) else None
    return dict(retrieval or {})


def _required_text(mapping: Mapping[str, Any], key: str) -> str:
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise ValueError(f"SpecClaim {key} is required")
    return value


def _required_mapping(mapping: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"SpecClaim {key} is required")
    return value


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left, right, strict=False):
        dot += float(left_value) * float(right_value)
        left_norm += float(left_value) * float(left_value)
        right_norm += float(right_value) * float(right_value)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / math.sqrt(left_norm * right_norm)


def _sparse_dot(left: SparseVector, right: SparseVector) -> float:
    right_by_index = dict(zip(right.indices, right.values, strict=False))
    return sum(
        float(value) * float(right_by_index.get(index, 0.0))
        for index, value in zip(left.indices, left.values, strict=False)
    )


def _state_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.name == CONFLICT_CANDIDATE_PAIRS_STATE_FILENAME:
        return candidate
    return candidate / CONFLICT_CANDIDATE_PAIRS_STATE_FILENAME


def _jsonl_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.name == CONFLICT_CANDIDATE_PAIRS_JSONL_FILENAME:
        return candidate
    return candidate / CONFLICT_CANDIDATE_PAIRS_JSONL_FILENAME


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
