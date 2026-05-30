"""Unit tests for the section_pair conflict candidate generator."""

from __future__ import annotations

from typing import Any

from spec_anchor.conflict_review import section_pair_id
from spec_anchor.section_pair_candidates import (
    SectionPairCandidateResult,
    generate_section_pair_candidates,
)


def _section(
    section_id: str,
    *,
    document_id: str = "doc.md",
    source_hash: str = "h",
    text: str = "",
    heading: str | None = None,
) -> dict[str, Any]:
    return {
        "source_section_id": section_id,
        "source_document_id": document_id,
        "source_hash": source_hash,
        "text": text or f"body for {section_id}",
        "heading_path": ["Spec", heading or section_id],
    }


def _origins(result: SectionPairCandidateResult) -> dict[str, str]:
    return {
        section_pair_id(c["left_section_id"], c["right_section_id"]): c["candidate_origin"]
        for c in result.candidates
    }


class _FakeHit:
    def __init__(self, sid: str, *, dense_score: float | None) -> None:
        self._sid = sid
        self.score = 0.03  # RRF-fused score is always small (rank-based)
        self.dense_score = dense_score

    @property
    def source_section_id(self) -> str:
        return self._sid


class _FakeResult:
    def __init__(self, hits: list[_FakeHit]) -> None:
        self.hits = hits


def test_retrieval_cap_min_dense_score_gates_on_dense_not_fused_score(monkeypatch) -> None:
    """min_dense_score must gate hit.dense_score (real cosine ~0.3-0.9), NOT the
    RRF-fused hit.score (~0.03). Otherwise a 0.55 threshold drops every candidate
    (confirmed on real Qdrant/BGE-M3: fused ~0.03, dense 0.30-0.59)."""

    from spec_anchor import section_pair_candidates as spc

    sections = [_section(f"doc.md#s{i}", source_hash=f"h{i}") for i in range(16)]

    # For every source, the fake retriever returns: one high-dense neighbour
    # (kept), one low-dense neighbour (dropped), one sparse-only/None (kept).
    def _fake_search(query, **kwargs):  # noqa: ANN001
        return _FakeResult(
            [
                _FakeHit("doc.md#s0", dense_score=0.60),
                _FakeHit("doc.md#s1", dense_score=0.40),
                _FakeHit("doc.md#s2", dense_score=None),
            ]
        )

    class _FakeRetriever:
        search = staticmethod(_fake_search)

    monkeypatch.setattr(spc, "_build_retriever", lambda *a, **k: _FakeRetriever())

    config = {
        "conflict_candidate_detection": {
            "min_dense_score": 0.55,
            "section_pair_top_k": 8,
            "global_pair_cap": 200,
            "allow_same_section_pair": False,
        }
    }
    result = generate_section_pair_candidates(sections, config=config)

    # Every section is a source; the fake returns the same 3 hits (s0/s1/s2) for
    # each. So s0/s1/s2 also pair via being a SOURCE. To check TARGET gating,
    # look at who each of s0/s1/s2 pairs with: a section sX (X not in 0,1,2) can
    # only be paired with s0/s1/s2 by appearing as sX's retrieval TARGET.
    def partners(sid: str) -> set[str]:
        out: set[str] = set()
        for c in result.candidates:
            if c["candidate_origin"] != "section_pair_retrieval":
                continue
            ids = {c["left_section_id"], c["right_section_id"]}
            if sid in ids:
                out |= ids - {sid}
        return out

    other_sources = {f"doc.md#s{i}" for i in range(3, 16)}
    # s0 (dense 0.60 >= 0.55): kept as a target -> paired with many other sources.
    assert partners("doc.md#s0") & other_sources, "high-dense target must be kept"
    # s2 (dense None -> not gated by dense threshold): also kept as a target.
    assert partners("doc.md#s2") & other_sources, "sparse-only (None dense) target must be kept"
    # s1 (dense 0.40 < 0.55): dropped as a target -> never paired with s3..s15.
    assert not (partners("doc.md#s1") & other_sources), (
        "low-dense target must be dropped (gated on dense_score, not fused score)"
    )


def test_all_pairs_mode_small_set_produces_all_ij_pairs_plus_self_pairs() -> None:
    sections = [_section(f"doc.md#s{i}") for i in range(4)]

    result = generate_section_pair_candidates(sections)

    assert result.diagnostics["mode"] == "all_pairs"
    assert result.diagnostics["section_count"] == 4
    # 4 choose 2 = 6 cross pairs + 4 self-pairs = 10
    assert len(result.candidates) == 10
    cross = [
        c for c in result.candidates if c["left_section_id"] != c["right_section_id"]
    ]
    self_pairs = [
        c for c in result.candidates if c["left_section_id"] == c["right_section_id"]
    ]
    assert len(cross) == 6
    assert len(self_pairs) == 4
    assert all(c["candidate_origin"] == "all_pairs" for c in result.candidates)
    # canonical order: left <= right for every cross pair.
    for c in cross:
        assert c["left_section_id"] <= c["right_section_id"]


def test_all_pairs_mode_drops_same_file_pairs_when_disallowed() -> None:
    # allow_same_source_file_pair=false honours the config key name: pairs
    # whose two sections share a source_document_id are dropped (only
    # cross-file pairs survive).
    sections = [
        _section("a.md#s0", document_id="a.md"),
        _section("a.md#s1", document_id="a.md"),
        _section("b.md#s0", document_id="b.md"),
    ]
    config = {"conflict_candidate_detection": {"allow_same_source_file_pair": False}}

    result = generate_section_pair_candidates(sections, config=config)

    cross = [
        c for c in result.candidates if c["left_section_id"] != c["right_section_id"]
    ]
    # The within-a.md pair (a.md#s0, a.md#s1) is dropped; the two cross-file
    # pairs to b.md survive.
    assert len(cross) == 2
    cross_keys = {
        frozenset((c["left_section_id"], c["right_section_id"])) for c in cross
    }
    assert frozenset(("a.md#s0", "a.md#s1")) not in cross_keys
    assert frozenset(("a.md#s0", "b.md#s0")) in cross_keys
    assert frozenset(("a.md#s1", "b.md#s0")) in cross_keys
    # self-pairs still present for all 3 (cap/file-filter exempt).
    self_pairs = [
        c for c in result.candidates if c["left_section_id"] == c["right_section_id"]
    ]
    assert len(self_pairs) == 3


def test_retrieval_cap_mode_produces_retrieval_pairs_respects_cap_and_self_pairs() -> None:
    # > threshold(12) sections -> retrieval_cap mode. Give each a meaningful
    # metadata summary so build_section_payloads produces dense embedding text.
    sections = []
    metadata: dict[str, Any] = {}
    for i in range(16):
        sid = f"doc.md#s{i}"
        sections.append(_section(sid, source_hash=f"h{i}"))
        metadata[sid] = {
            "summary": "authentication token session expiry retry rule",
            "search_keys": ["auth", "token", "session", f"rule{i % 3}"],
        }
    config = {
        "conflict_candidate_detection": {
            # RRF fused scores are small (~0.03); use a low threshold so the
            # in-memory retriever surfaces neighbours in the unit test.
            "min_dense_score": 0.0,
            "section_pair_top_k": 4,
            "global_pair_cap": 5,
        }
    }

    result = generate_section_pair_candidates(
        sections, config=config, section_metadata=metadata
    )

    assert result.diagnostics["mode"] == "retrieval_cap"
    assert result.diagnostics["section_count"] == 16
    retrieval = [
        c for c in result.candidates if c["candidate_origin"] == "section_pair_retrieval"
    ]
    # cap is 5; retrieval candidates must not exceed it.
    assert len(retrieval) <= 5
    assert result.diagnostics["truncated_count"] > 0
    # self-pairs are cap-exempt: one per section, all 16 present.
    self_pairs = [
        c for c in result.candidates if c["left_section_id"] == c["right_section_id"]
    ]
    assert len(self_pairs) == 16


def test_existing_conflict_recheck_force_included_when_hash_changed_even_over_cap() -> None:
    sections = []
    metadata: dict[str, Any] = {}
    for i in range(16):
        sid = f"doc.md#s{i}"
        sections.append(_section(sid, source_hash=f"current-{i}"))
        metadata[sid] = {"summary": "alpha beta", "search_keys": ["k"]}

    # A prior conflict between two sections; one section's hash changed.
    existing = [
        {
            "section_pair": {
                "left_section_id": "doc.md#s14",
                "right_section_id": "doc.md#s15",
            },
            "base_source_hashes": [
                {"source_ref": "doc.md#s14", "hash": "current-14"},
                {"source_ref": "doc.md#s15", "hash": "OLD-15"},
            ],
        }
    ]
    current_hashes = {f"doc.md#s{i}": f"current-{i}" for i in range(16)}
    config = {
        "conflict_candidate_detection": {
            "min_dense_score": 0.0,
            "section_pair_top_k": 2,
            # cap of 0 means no retrieval pairs survive the cap at all.
            "global_pair_cap": 0,
        }
    }

    result = generate_section_pair_candidates(
        sections,
        existing_conflict_items=existing,
        current_source_hashes=current_hashes,
        config=config,
        section_metadata=metadata,
    )

    origins = _origins(result)
    pid = section_pair_id("doc.md#s14", "doc.md#s15")
    assert origins.get(pid) == "existing_conflict_recheck"
    assert result.diagnostics["recheck_count"] == 1
    # cap was 0, so no retrieval pair survived, proving recheck is cap-exempt.
    assert all(
        c["candidate_origin"] != "section_pair_retrieval" for c in result.candidates
    )


def test_existing_conflict_recheck_not_forced_when_section_deleted() -> None:
    sections = [_section(f"doc.md#s{i}") for i in range(3)]
    existing = [
        {
            "section_pair": {
                "left_section_id": "doc.md#s0",
                "right_section_id": "doc.md#DELETED",
            },
            "base_source_hashes": [
                {"source_ref": "doc.md#s0", "hash": "stale"},
                {"source_ref": "doc.md#DELETED", "hash": "stale"},
            ],
        }
    ]
    current_hashes = {f"doc.md#s{i}": "current" for i in range(3)}

    result = generate_section_pair_candidates(
        sections,
        existing_conflict_items=existing,
        current_source_hashes=current_hashes,
    )

    pid = section_pair_id("doc.md#s0", "doc.md#DELETED")
    assert pid not in _origins(result)
    assert result.diagnostics["recheck_count"] == 0


def test_existing_conflict_recheck_skipped_when_hash_unchanged() -> None:
    sections = [_section(f"doc.md#s{i}", source_hash="current") for i in range(3)]
    existing = [
        {
            "section_pair": {
                "left_section_id": "doc.md#s0",
                "right_section_id": "doc.md#s1",
            },
            "base_source_hashes": [
                {"source_ref": "doc.md#s0", "hash": "current"},
                {"source_ref": "doc.md#s1", "hash": "current"},
            ],
        }
    ]
    current_hashes = {f"doc.md#s{i}": "current" for i in range(3)}

    result = generate_section_pair_candidates(
        sections,
        existing_conflict_items=existing,
        current_source_hashes=current_hashes,
    )

    # The pair still appears via all_pairs (small set) but NOT as a recheck.
    origins = _origins(result)
    pid = section_pair_id("doc.md#s0", "doc.md#s1")
    assert origins.get(pid) == "all_pairs"
    assert result.diagnostics["recheck_count"] == 0


def test_dedupe_canonical_order_and_origin_precedence() -> None:
    # Small set -> all_pairs. The (s0, s1) pair also appears as a changed
    # recheck; recheck precedence must win over all_pairs for that pair.
    sections = [_section(f"doc.md#s{i}", source_hash="current") for i in range(3)]
    existing = [
        {
            "section_pair": {
                # deliberately reversed order to prove canonicalization.
                "left_section_id": "doc.md#s1",
                "right_section_id": "doc.md#s0",
            },
            "base_source_hashes": [
                {"source_ref": "doc.md#s0", "hash": "OLD"},
                {"source_ref": "doc.md#s1", "hash": "current"},
            ],
        }
    ]
    current_hashes = {f"doc.md#s{i}": "current" for i in range(3)}

    result = generate_section_pair_candidates(
        sections,
        existing_conflict_items=existing,
        current_source_hashes=current_hashes,
    )

    pid = section_pair_id("doc.md#s0", "doc.md#s1")
    # exactly one entry for the (s0,s1) pair (deduped).
    matching = [
        c
        for c in result.candidates
        if section_pair_id(c["left_section_id"], c["right_section_id"]) == pid
    ]
    assert len(matching) == 1
    # canonical sorted order regardless of the reversed input.
    assert matching[0]["left_section_id"] == "doc.md#s0"
    assert matching[0]["right_section_id"] == "doc.md#s1"
    # origin precedence: recheck wins over all_pairs.
    assert matching[0]["candidate_origin"] == "existing_conflict_recheck"


def test_empty_sections_returns_empty_candidates() -> None:
    result = generate_section_pair_candidates([])
    assert result.candidates == []
    assert result.diagnostics["section_count"] == 0
    assert result.diagnostics["mode"] == "all_pairs"
