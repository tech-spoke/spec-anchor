from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path
from typing import Any

from spec_anchor import claim_retrieval


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _claim(
    suffix: str,
    *,
    section: str = "docs/spec/main.md#0001-alpha",
    source_document_id: str = "docs/spec/main.md",
    target: str = "active session retention",
    aliases: list[str] | None = None,
    text: str | None = None,
    embedding_text: str | None = None,
    sparse_keys: list[str] | None = None,
    conflict_probes: list[str] | None = None,
    claim_hash_extra: str = "",
    retrieval_hash_extra: str = "",
) -> dict[str, Any]:
    claim_uid = f"claim:sha256:{suffix}"
    evidence = text or f"{target} must match {suffix}."
    retrieval = {
        "embedding_text": embedding_text or f"{target} {suffix}",
        "sparse_keys": sparse_keys or [target, suffix],
        "conflict_probes": conflict_probes or [f"{target} conflicts {suffix}"],
    }
    return {
        "claim_uid": claim_uid,
        "display_id": f"{section}:C{suffix}",
        "claim_hash": _hash(f"claim:{suffix}:{claim_hash_extra}"),
        "section_uid": section,
        "source_section_id": section,
        "source_document_id": source_document_id,
        "source_hash": _hash(f"source:{section}"),
        "semantic_hash": _hash(f"semantic:{section}"),
        "claim_text": evidence,
        "target": target,
        "target_aliases": aliases or [target],
        "scope": "normal operation",
        "condition": "active session",
        "value": suffix,
        "claim_kind": "requirement",
        "claim_kind_confidence": "high",
        "evidence_span": evidence,
        "evidence_start": 0,
        "evidence_end": len(evidence),
        "evidence_hash": _hash(evidence),
        "confidence": "high",
        "retrieval": retrieval,
        "retrieval_hash": _hash(f"retrieval:{suffix}:{retrieval_hash_extra}"),
        "schema_version": "spec-claim-v1",
        "claim_identity_version": "claim-identity-v1",
        "retrieval_schema_version": "spec-claim-retrieval-v1",
        "generated_at": "2026-05-28T00:00:00Z",
    }


def _config(**overrides: Any) -> claim_retrieval.ClaimRetrievalConfig:
    values: dict[str, Any] = {
        "min_dense_score": 0.0,
        "min_sparse_score": 0.0,
        "per_claim_top_k": 10,
        "per_section_top_k": 20,
        "per_target_top_k": 20,
        "global_candidate_top_k": 100,
    }
    values.update(overrides)
    return claim_retrieval.ClaimRetrievalConfig(**values)


def _candidate(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    retrieval_sources: list[str] | None = None,
) -> dict[str, Any]:
    left_uid, right_uid = sorted([left["claim_uid"], right["claim_uid"]])
    claims = {left["claim_uid"]: left, right["claim_uid"]: right}
    left_claim = claims[left_uid]
    right_claim = claims[right_uid]
    return {
        "candidate_uid": claim_retrieval.candidate_uid_for_claim_pair(left_uid, right_uid),
        "display_id": "CC-00001",
        "left_claim_uid": left_uid,
        "right_claim_uid": right_uid,
        "left_claim_hash": left_claim["claim_hash"],
        "right_claim_hash": right_claim["claim_hash"],
        "left_retrieval_hash": left_claim["retrieval_hash"],
        "right_retrieval_hash": right_claim["retrieval_hash"],
        "left_section_uid": left_claim["source_section_id"],
        "right_section_uid": right_claim["source_section_id"],
        "shared_target": left_claim["target"],
        "primary_route": claim_retrieval.CLAIM_RETRIEVAL_ROUTE,
        "routes": [
            {
                "route": claim_retrieval.CLAIM_RETRIEVAL_ROUTE,
                "is_primary_route": True,
            }
        ],
        "retrieval_sources": retrieval_sources
        or [claim_retrieval.DENSE_CLAIM_RETRIEVAL],
        "signals": ["semantic_same_target"],
        "triage": None,
        "evidence": [],
    }


class StaticBackend:
    def __init__(
        self,
        claims: list[dict[str, Any]],
        *,
        dense: dict[str, list[tuple[str, float]]] | None = None,
        sparse: dict[str, list[tuple[str, float]]] | None = None,
    ) -> None:
        self.payloads = {
            payload["claim_uid"]: payload
            for payload in claim_retrieval.build_claim_payloads(claims)
        }
        self.dense = dense or {}
        self.sparse = sparse or {}

    def dense_search(self, query: str, top_k: int) -> list[claim_retrieval.ClaimRetrievalHit]:
        return self._hits(self.dense.get(query, []), top_k)

    def sparse_search(self, query: str, top_k: int) -> list[claim_retrieval.ClaimRetrievalHit]:
        return self._hits(self.sparse.get(query, []), top_k)

    def _hits(
        self,
        values: list[tuple[str, float]],
        top_k: int,
    ) -> list[claim_retrieval.ClaimRetrievalHit]:
        return [
            claim_retrieval.ClaimRetrievalHit(
                claim_uid=uid,
                score=score,
                payload=self.payloads[uid],
            )
            for uid, score in values[:top_k]
        ]


def test_qdrant_upsert_delete_uses_uuid5_and_required_payload(
    monkeypatch: Any,
) -> None:
    installed_clients: list[Any] = []

    class FakePointStruct:
        def __init__(self, *, id: Any, vector: Any, payload: Any) -> None:
            self.id = id
            self.vector = vector
            self.payload = payload

    class FakeSparseVector:
        def __init__(self, *, indices: list[int], values: list[float]) -> None:
            self.indices = indices
            self.values = values

    class FakePointIdsList:
        def __init__(self, *, points: list[Any]) -> None:
            self.points = points

    class FakeClient:
        def __init__(self, url: str) -> None:
            self.url = url
            self.recreated: list[dict[str, Any]] = []
            self.deleted: list[Any] = []
            self.upserted: list[Any] = []
            installed_clients.append(self)

        def recreate_collection(self, **kwargs: Any) -> None:
            self.recreated.append(kwargs)

        def delete(self, *, collection_name: str, points_selector: Any) -> None:
            self.deleted.append((collection_name, points_selector))

        def upsert(self, *, collection_name: str, points: list[Any]) -> None:
            self.upserted.append((collection_name, list(points)))

    fake_models = types.SimpleNamespace(
        PointStruct=FakePointStruct,
        SparseVector=FakeSparseVector,
        PointIdsList=FakePointIdsList,
        VectorParams=lambda **kwargs: kwargs,
        SparseVectorParams=lambda **kwargs: kwargs,
        Distance=types.SimpleNamespace(COSINE="cosine"),
    )
    fake_qdrant = types.SimpleNamespace(QdrantClient=FakeClient, models=fake_models)
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_qdrant)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", fake_models)

    current = _claim("a")
    stale_uid = "claim:sha256:stale"
    diagnostics = claim_retrieval.upsert_qdrant_claim_collection(
        [current],
        url="memory",
        collection="spec_anchor_claim_test",
        recreate=False,
        claims_to_upsert=[current],
        claims_to_delete=[stale_uid],
        embedding_provider=claim_retrieval.FakeBgeM3EmbeddingProvider(),
    )

    client = installed_clients[0]
    assert diagnostics["claims_upserted_count"] == 1
    assert diagnostics["claims_deleted_count"] == 1
    assert client.deleted[0][1].points == [
        claim_retrieval.stable_claim_point_id(stale_uid)
    ]
    point = client.upserted[0][1][0]
    assert point.id == claim_retrieval.stable_claim_point_id(current["claim_uid"])
    assert {
        "target",
        "target_aliases",
        "claim_text",
        "claim_hash",
        "source_section_id",
        "evidence_span",
        "retrieval_hash",
    } <= set(point.payload)


def test_dedup_sorted_claim_uid_and_retrieval_sources_aggregate() -> None:
    first = _claim(
        "a",
        embedding_text="dense seed a",
        sparse_keys=["sparse seed a"],
    )
    second = _claim(
        "b",
        section="docs/spec/main.md#0002-beta",
        embedding_text="dense seed b",
        sparse_keys=["sparse seed b"],
    )
    backend = StaticBackend(
        [first, second],
        dense={"dense seed a": [(second["claim_uid"], 0.91)]},
        sparse={"sparse seed b": [(first["claim_uid"], 0.82)]},
    )

    result = claim_retrieval.generate_claim_retrieval_result(
        [first, second],
        seed_claim_uids=[first["claim_uid"], second["claim_uid"]],
        backend=backend,
        config=_config(),
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert (candidate["left_claim_uid"], candidate["right_claim_uid"]) == tuple(
        sorted([first["claim_uid"], second["claim_uid"]])
    )
    assert candidate["retrieval_sources"] == [
        claim_retrieval.DENSE_CLAIM_RETRIEVAL,
        claim_retrieval.SPARSE_KEY_CLAIM_RETRIEVAL,
    ]


def test_truncation_reports_sources_and_pair_count() -> None:
    seed = _claim("a", embedding_text="dense seed")
    hits = [
        _claim("b", section="docs/spec/main.md#0002-beta"),
        _claim("c", section="docs/spec/main.md#0003-gamma"),
        _claim("d", section="docs/spec/main.md#0004-delta"),
    ]
    backend = StaticBackend(
        [seed, *hits],
        dense={
            "dense seed": [
                (hits[0]["claim_uid"], 0.93),
                (hits[1]["claim_uid"], 0.92),
                (hits[2]["claim_uid"], 0.91),
            ]
        },
    )

    result = claim_retrieval.generate_claim_retrieval_result(
        [seed, *hits],
        seed_claim_uids=[seed["claim_uid"]],
        backend=backend,
        config=_config(per_claim_top_k=1),
    )

    assert len(result.candidates) == 1
    assert result.diagnostics["truncated_pair_count"] == 2
    assert result.diagnostics["truncated_candidate_sources"] == ["per_claim_top_k"]


def test_deleted_claim_pairs_are_excluded_from_reuse_and_jsonl(
    tmp_path: Path,
) -> None:
    left = _claim("a")
    kept = _claim("b", section="docs/spec/main.md#0002-beta")
    deleted = _claim("deleted", section="docs/spec/main.md#0003-deleted")
    config = _config()
    previous_candidates = [
        _candidate(left, kept),
        _candidate(left, deleted),
    ]
    previous_state = claim_retrieval.build_conflict_candidate_pairs_state(
        [left, kept, deleted],
        previous_candidates,
        config=config,
    )
    previous_state["triage"] = {"preserved": True}

    result = claim_retrieval.generate_claim_retrieval_result(
        [left, kept],
        seed_claim_uids=[],
        backend=StaticBackend([left, kept]),
        config=config,
        previous_candidates=previous_candidates,
        previous_state=previous_state,
        output_path=tmp_path / ".spec-anchor" / "context",
        state_path=tmp_path / ".spec-anchor" / "state",
    )

    assert result.diagnostics["deleted_claim_pairs_excluded"] == 1
    assert [candidate["candidate_uid"] for candidate in result.candidates] == [
        previous_candidates[0]["candidate_uid"]
    ]
    written = claim_retrieval.read_conflict_candidate_pairs_jsonl(
        tmp_path / ".spec-anchor" / "context"
    )
    assert [item["candidate_uid"] for item in written] == [
        previous_candidates[0]["candidate_uid"]
    ]
    state = claim_retrieval.read_conflict_candidate_pairs_state(
        tmp_path / ".spec-anchor" / "state"
    )
    assert state["triage"] == {"preserved": True}
    assert state["retrieval"]["claim_uids"] == [left["claim_uid"], kept["claim_uid"]]
    assert state["retrieval"]["candidate_uids"] == [
        previous_candidates[0]["candidate_uid"]
    ]


def test_same_section_claim_pair_is_allowed_by_default() -> None:
    first = _claim("a", embedding_text="dense same section")
    second = _claim("b")
    backend = StaticBackend(
        [first, second],
        dense={"dense same section": [(second["claim_uid"], 0.9)]},
    )

    result = claim_retrieval.generate_claim_retrieval_result(
        [first, second],
        seed_claim_uids=[first["claim_uid"]],
        backend=backend,
        config=_config(),
    )

    assert len(result.candidates) == 1
    assert result.candidates[0]["left_section_uid"] == result.candidates[0][
        "right_section_uid"
    ]


def test_changed_seed_claim_searches_all_current_claims_with_in_memory_backend() -> None:
    changed = _claim(
        "changed",
        embedding_text="changed session retention policy",
        sparse_keys=["session", "retention", "policy"],
    )
    unchanged = _claim(
        "unchanged",
        section="docs/spec/main.md#0002-beta",
        embedding_text="unchanged session retention policy",
        sparse_keys=["session", "retention", "policy"],
    )
    unrelated = _claim(
        "unrelated",
        section="docs/spec/main.md#0003-gamma",
        target="invoice export",
        aliases=["invoice export"],
        embedding_text="invoice export csv",
        sparse_keys=["invoice", "export"],
    )
    backend = claim_retrieval.InMemoryClaimRetrievalBackend(
        [changed, unchanged, unrelated],
        dense_enabled=False,
        sparse_enabled=True,
    )

    result = claim_retrieval.generate_claim_retrieval_result(
        [changed, unchanged, unrelated],
        seed_claim_uids=[changed["claim_uid"]],
        backend=backend,
        config=_config(dense_top_k=0, sparse_top_k=5),
    )

    pairs = {
        (candidate["left_claim_uid"], candidate["right_claim_uid"])
        for candidate in result.candidates
    }
    assert tuple(sorted([changed["claim_uid"], unchanged["claim_uid"]])) in pairs
    assert all(unrelated["claim_uid"] not in pair for pair in pairs)


def test_unchanged_pair_is_reused_when_retrieval_fingerprint_matches() -> None:
    changed_old = _claim("a", claim_hash_extra="old", retrieval_hash_extra="old")
    changed_new = _claim("a", claim_hash_extra="new", retrieval_hash_extra="new")
    left = _claim("b", section="docs/spec/main.md#0002-beta")
    right = _claim("c", section="docs/spec/main.md#0003-gamma")
    config = _config()
    previous_candidates = [_candidate(left, right)]
    previous_state = claim_retrieval.build_conflict_candidate_pairs_state(
        [changed_old, left, right],
        previous_candidates,
        config=config,
    )

    result = claim_retrieval.generate_claim_retrieval_result(
        [changed_new, left, right],
        seed_claim_uids=[changed_new["claim_uid"]],
        backend=StaticBackend([changed_new, left, right]),
        config=config,
        previous_candidates=previous_candidates,
        previous_state=previous_state,
    )

    assert result.diagnostics["reused_candidate_count"] == 1
    assert [candidate["candidate_uid"] for candidate in result.candidates] == [
        previous_candidates[0]["candidate_uid"]
    ]
    assert result.candidates[0]["triage"] is None


def test_candidate_schema_has_retrieval_only_route_and_null_triage() -> None:
    first = _claim("a", embedding_text="dense schema a")
    second = _claim("b", section="docs/spec/main.md#0002-beta")
    backend = StaticBackend(
        [first, second],
        dense={"dense schema a": [(second["claim_uid"], 0.9)]},
    )

    result = claim_retrieval.generate_claim_retrieval_result(
        [first, second],
        seed_claim_uids=[first["claim_uid"]],
        backend=backend,
        config=_config(),
    )

    candidate = result.candidates[0]
    assert candidate["primary_route"] == claim_retrieval.CLAIM_RETRIEVAL_ROUTE
    assert candidate["routes"] == [
        {
            "route": claim_retrieval.CLAIM_RETRIEVAL_ROUTE,
            "is_primary_route": True,
        }
    ]
    assert candidate["triage"] is None
    assert set(candidate) == {
        "candidate_uid",
        "display_id",
        "left_claim_uid",
        "right_claim_uid",
        "left_claim_hash",
        "right_claim_hash",
        "left_retrieval_hash",
        "right_retrieval_hash",
        "left_section_uid",
        "right_section_uid",
        "shared_target",
        "primary_route",
        "routes",
        "retrieval_sources",
        "signals",
        "triage",
        "evidence",
    }
