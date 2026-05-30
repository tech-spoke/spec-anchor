"""section_pair conflict candidate generator.

This module produces the ``section_pairs`` list consumed by
``conflict_review.evaluate_section_pair_conflicts``. Each candidate is a dict
``{"left_section_id", "right_section_id", "candidate_origin"}`` in canonical
sorted order, deduped by ``conflict_review.section_pair_id``.

Responsibility split (CLAUDE.md rule 3): this generator is the candidate
*supplier*. It does not call the LLM judge, does not persist artifacts, and is
not wired into ``core.py`` (a later task does both). It only decides which
section pairs are worth judging, using:

* an exhaustive ``all_pairs`` enumeration for small section sets, or
* a retrieval-capped ``section_pair_retrieval`` enumeration (top-k nearest
  sections per source via the in-memory or Qdrant hybrid retriever) for large
  sets, plus
* self-pairs (cap-exempt) and existing-conflict rechecks (cap-exempt).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from spec_anchor.conflict_review import section_pair_id
from spec_anchor.retrieval_index import (
    BgeM3EmbeddingProvider,
    InMemoryHybridRetriever,
    QdrantHybridRetriever,
    build_section_payloads,
)


# Defaults for the [conflict_candidate_detection] config table. Read with
# `_config_get(config, ("conflict_candidate_detection", <key>), <default>)`.
DEFAULT_SMALL_SECTION_ALL_PAIRS_THRESHOLD = 12
DEFAULT_SECTION_PAIR_TOP_K = 8
DEFAULT_GLOBAL_PAIR_CAP = 80
DEFAULT_MIN_DENSE_SCORE = 0.55
DEFAULT_ALLOW_SAME_SOURCE_FILE_PAIR = True
DEFAULT_ALLOW_SAME_SECTION_PAIR = True

# candidate_origin precedence: a recheck pair must never be dropped in favour
# of a cap-eligible origin, so existing_conflict_recheck wins over retrieval,
# which wins over all_pairs. Higher number = higher precedence.
_ORIGIN_PRECEDENCE = {
    "all_pairs": 0,
    "section_pair_retrieval": 1,
    "existing_conflict_recheck": 2,
}


@dataclass
class SectionPairCandidateResult:
    """Result of the section_pair candidate generator.

    ``candidates`` is the deduped, canonical-order list handed to
    ``evaluate_section_pair_conflicts``. ``diagnostics`` records how the set
    was built so callers can audit mode selection and cap truncation.
    """

    candidates: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _config_get(config: Any, path: tuple[str, ...], default: Any = None) -> Any:
    """Read a nested config value supporting dict configs and attr configs.

    Mirrors the access shape used in ``core.py`` (nested ``Mapping`` lookup)
    but also walks attribute access for object-shaped configs, so a typed
    settings object and a plain dict both work.
    """

    current: Any = config
    for key in path:
        if current is None:
            return default
        if isinstance(current, Mapping):
            if key not in current:
                return default
            current = current[key]
        else:
            if not hasattr(current, key):
                return default
            current = getattr(current, key)
    if current is None:
        return default
    return current


def _config_bool(config: Any, path: tuple[str, ...], default: bool) -> bool:
    value = _config_get(config, path, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _config_int(config: Any, path: tuple[str, ...], default: int) -> int:
    value = _config_get(config, path, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _config_float(config: Any, path: tuple[str, ...], default: float) -> float:
    value = _config_get(config, path, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _section_id(section: Mapping[str, Any]) -> str:
    """Resolve the canonical section id (same order as conflict_review)."""

    return str(
        section.get("source_section_id")
        or section.get("section_id")
        or section.get("id")
        or ""
    )


def _canonical_pair(left: str, right: str) -> tuple[str, str]:
    """Return the (left, right) sorted canonical order; self-pair = (a, a)."""

    if left == right:
        return left, left
    return tuple(sorted((left, right)))  # type: ignore[return-value]


def _select_real_qdrant(config: Any) -> bool:
    """Choose Qdrant vs in-memory the same way related_sections.py does."""

    qdrant_provider = str(_config_get(config, ("vector_store", "provider"), "") or "")
    qdrant_url = str(_config_get(config, ("vector_store", "url"), "") or "")
    embedding_provider = str(_config_get(config, ("embedding", "provider"), "") or "")
    return (
        qdrant_provider == "qdrant"
        and bool(qdrant_url)
        and embedding_provider == "flagembedding"
    )


def _build_retriever(
    sections: Sequence[Mapping[str, Any]],
    section_metadata: Mapping[str, Mapping[str, Any]] | None,
    config: Any,
    embedding_provider: BgeM3EmbeddingProvider | None = None,
) -> Any:
    """Build the hybrid retriever, reusing retrieval_index primitives only.

    Uses ``QdrantHybridRetriever`` when the config selects the standard
    Qdrant + BGE-M3 stack, otherwise ``InMemoryHybridRetriever`` over
    ``build_section_payloads`` output (unit-test / dev path). This does not
    touch the related_sections artifact; it only reuses the retriever class
    and ``build_section_payloads``.
    """

    payloads = build_section_payloads(sections, section_metadata or {})
    if _select_real_qdrant(config):
        url = str(_config_get(config, ("vector_store", "url"), "http://localhost:6333"))
        collection = str(
            _config_get(config, ("retrieval", "section_collection"), "spec_anchor_section")
            or "spec_anchor_section"
        )
        return QdrantHybridRetriever(
            url=url,
            collection=collection,
            embedding_provider=embedding_provider,
        )
    return InMemoryHybridRetriever(payloads)


def _section_query_text(
    section: Mapping[str, Any],
    metadata: Mapping[str, Any] | None,
) -> str:
    """Build the query text used to find a section's nearest neighbours.

    Prefers the same dense signal the section payload embeds (heading +
    summary + search keys), falling back to the raw text when no metadata
    is supplied.
    """

    metadata = metadata or {}
    heading_path = section.get("heading_path") or []
    heading = " / ".join(str(part) for part in heading_path if part)
    summary = str(metadata.get("summary") or "")
    search_keys = list(metadata.get("search_keys") or [])
    parts: list[str] = []
    if heading:
        parts.append(heading)
    if summary:
        parts.append(summary)
    if search_keys:
        parts.append(" ".join(str(key) for key in search_keys))
    if not parts:
        parts.append(str(section.get("text") or ""))
    return " | ".join(part for part in parts if part)


def generate_section_pair_candidates(
    sections: list[dict[str, Any]],
    *,
    existing_conflict_items: list[dict[str, Any]] | None = None,
    current_source_hashes: dict[str, str] | None = None,
    config: Any = None,
    section_metadata: dict[str, Any] | None = None,
    embedding_provider: BgeM3EmbeddingProvider | None = None,
) -> SectionPairCandidateResult:
    """Generate deduped section_pair candidates for the conflict judge.

    See module docstring for the responsibility split. ``existing_conflict_items``
    carry prior ``section_pair`` + ``base_source_hashes`` so changed conflicts
    can be force-rechecked (cap-exempt). ``current_source_hashes`` maps
    ``section_id -> source_hash`` for the current run.
    """

    sections = list(sections or [])
    section_metadata = section_metadata or {}
    existing_conflict_items = existing_conflict_items or []
    current_source_hashes = current_source_hashes or {}

    # Algorithm step 1: build the section id list (skip unidentifiable rows).
    section_ids: list[str] = []
    section_by_id: dict[str, Mapping[str, Any]] = {}
    for section in sections:
        sid = _section_id(section)
        if not sid:
            continue
        if sid not in section_by_id:
            section_ids.append(sid)
        section_by_id[sid] = section

    threshold = _config_int(
        config,
        ("conflict_candidate_detection", "small_section_all_pairs_threshold"),
        DEFAULT_SMALL_SECTION_ALL_PAIRS_THRESHOLD,
    )
    section_pair_top_k = _config_int(
        config,
        ("conflict_candidate_detection", "section_pair_top_k"),
        DEFAULT_SECTION_PAIR_TOP_K,
    )
    global_pair_cap = _config_int(
        config,
        ("conflict_candidate_detection", "global_pair_cap"),
        DEFAULT_GLOBAL_PAIR_CAP,
    )
    min_dense_score = _config_float(
        config,
        ("conflict_candidate_detection", "min_dense_score"),
        DEFAULT_MIN_DENSE_SCORE,
    )
    allow_same_source_file_pair = _config_bool(
        config,
        ("conflict_candidate_detection", "allow_same_source_file_pair"),
        DEFAULT_ALLOW_SAME_SOURCE_FILE_PAIR,
    )
    allow_same_section_pair = _config_bool(
        config,
        ("conflict_candidate_detection", "allow_same_section_pair"),
        DEFAULT_ALLOW_SAME_SECTION_PAIR,
    )

    # Algorithm step 2: mode selection.
    mode = "all_pairs" if len(sections) <= threshold else "retrieval_cap"

    truncated_count = 0
    # capped_pairs maps pair_id -> {left, right, origin}; these are subject to
    # the global cap. cap_exempt_pairs are unioned AFTER cap (self-pairs and
    # existing-conflict rechecks).
    capped_pairs: dict[str, dict[str, Any]] = {}
    cap_exempt_pairs: dict[str, dict[str, Any]] = {}

    def _same_file(a_id: str, b_id: str) -> bool:
        a_doc = str(section_by_id.get(a_id, {}).get("source_document_id") or "")
        b_doc = str(section_by_id.get(b_id, {}).get("source_document_id") or "")
        return a_doc == b_doc

    def _record(target: dict[str, dict[str, Any]], left: str, right: str, origin: str) -> None:
        cleft, cright = _canonical_pair(left, right)
        pid = section_pair_id(cleft, cright)
        existing = target.get(pid)
        if existing is None or _ORIGIN_PRECEDENCE.get(origin, -1) > _ORIGIN_PRECEDENCE.get(
            existing["candidate_origin"], -1
        ):
            target[pid] = {
                "left_section_id": cleft,
                "right_section_id": cright,
                "candidate_origin": origin,
            }

    if mode == "all_pairs":
        # Algorithm step 3: all i<j combinations.
        for a_id, b_id in combinations(section_ids, 2):
            if not allow_same_source_file_pair and _same_file(a_id, b_id):
                continue
            _record(capped_pairs, a_id, b_id, "all_pairs")
    else:
        # Algorithm step 4: retrieval_cap.
        retriever = _build_retriever(
            sections,
            section_metadata,
            config,
            embedding_provider=embedding_provider,
        )
        per_source_pairs: dict[str, dict[str, Any]] = {}
        for source_id in section_ids:
            source_section = section_by_id[source_id]
            query = _section_query_text(
                source_section, section_metadata.get(source_id)
            )
            if not query.strip():
                continue
            result = retriever.search(
                query,
                dense_top_k=max(section_pair_top_k * 2, section_pair_top_k),
                sparse_top_k=max(section_pair_top_k * 2, section_pair_top_k),
                limit=section_pair_top_k + 1,
                fusion_owner="section_pair_candidates",
            )
            kept = 0
            for hit in result.hits:
                hit_id = hit.source_section_id
                if not hit_id or hit_id == source_id:
                    continue
                if hit_id not in section_by_id:
                    continue
                # min_dense_score gates the DENSE channel cosine (hit.dense_score),
                # NOT the RRF-fused hit.score. Real BGE-M3 dense cosine is ~0.3-0.9
                # while the RRF-fused score is rank-based (~0.03), so comparing the
                # threshold against hit.score would drop every candidate. A hit with
                # no dense_score (sparse-only match) is not gated by the dense
                # threshold (kept, to preserve recall).
                dense_score = hit.dense_score
                if dense_score is not None and float(dense_score) < min_dense_score:
                    continue
                if not allow_same_source_file_pair and _same_file(source_id, hit_id):
                    continue
                _record(per_source_pairs, source_id, hit_id, "section_pair_retrieval")
                kept += 1
                if kept >= section_pair_top_k:
                    break

        # Algorithm step 4 (cont.): apply global_pair_cap to the new set.
        ordered = sorted(per_source_pairs.items())
        if global_pair_cap >= 0 and len(ordered) > global_pair_cap:
            truncated_count = len(ordered) - global_pair_cap
            ordered = ordered[:global_pair_cap]
        for pid, payload in ordered:
            capped_pairs[pid] = payload

    # Algorithm step 5: self-pairs (cap-exempt) for every section in both modes.
    if allow_same_section_pair:
        for sid in section_ids:
            _record(cap_exempt_pairs, sid, sid, "all_pairs")

    # Algorithm step 6: existing-conflict recheck (cap-exempt).
    recheck_count = 0
    for item in existing_conflict_items:
        if not isinstance(item, Mapping):
            continue
        section_pair = item.get("section_pair")
        if not isinstance(section_pair, Mapping):
            continue
        left = str(section_pair.get("left_section_id") or "")
        right = str(section_pair.get("right_section_id") or "")
        if not left or not right:
            continue
        # A referenced section that no longer exists is handled elsewhere as
        # auto-dismiss (deletion / heading-slug rename). Do not force-recheck.
        if left not in section_by_id or right not in section_by_id:
            continue
        if _changed(item, current_source_hashes):
            _record(cap_exempt_pairs, left, right, "existing_conflict_recheck")
            recheck_count += 1

    # Algorithm step 7: dedupe the union, recheck/retrieval precedence wins.
    merged: dict[str, dict[str, Any]] = dict(capped_pairs)
    for pid, payload in cap_exempt_pairs.items():
        existing = merged.get(pid)
        if existing is None or _ORIGIN_PRECEDENCE.get(
            payload["candidate_origin"], -1
        ) > _ORIGIN_PRECEDENCE.get(existing["candidate_origin"], -1):
            merged[pid] = payload

    candidates = [merged[pid] for pid in sorted(merged)]
    diagnostics = {
        "section_count": len(sections),
        "mode": mode,
        "generated_count": len(candidates),
        "truncated_count": truncated_count,
        "recheck_count": recheck_count,
    }
    return SectionPairCandidateResult(candidates=candidates, diagnostics=diagnostics)


def _changed(item: Mapping[str, Any], current_source_hashes: Mapping[str, str]) -> bool:
    """Return True when any referenced section's source_hash differs.

    Uses the item's ``base_source_hashes`` (``[{"source_ref", "hash"}, ...]``)
    against ``current_source_hashes`` (``section_id -> source_hash``). When the
    base hash record is empty / unparseable, the pair is treated as changed so
    a still-existing conflict is rechecked rather than silently skipped.
    """

    base_hashes = item.get("base_source_hashes") or []
    if not base_hashes:
        return True
    saw_comparable = False
    for base in base_hashes:
        if not isinstance(base, Mapping):
            continue
        source_ref = (
            base.get("source_ref")
            or base.get("source_section_id")
            or base.get("ref")
        )
        expected = base.get("hash") or base.get("source_hash")
        if not source_ref or expected is None:
            continue
        if str(source_ref) not in current_source_hashes:
            # Cannot determine for this section; conservatively recheck.
            return True
        saw_comparable = True
        if str(current_source_hashes[str(source_ref)]) != str(expected):
            return True
    if not saw_comparable:
        return True
    return False
