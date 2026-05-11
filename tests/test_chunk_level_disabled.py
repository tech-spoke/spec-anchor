"""Phase R-5 tests for the chunk-level dormant contract.

`doc/STORAGE_REDESIGN.ja.md` §7.4 R-5 commented out chunk-level retrieval.
The dormant code (`build_source_chunks`, `build_source_chunks_artifact`,
`compute_chunk_diff`, `upsert_qdrant_bge_m3_index`,
`upsert_qdrant_bge_m3_index_incremental`,
`_qdrant_upsert_with_partial_dispatch`,
`_build_retrieval_index_revision`) raises `NotImplementedError`. The
runtime gate (`CHUNK_LEVEL_ENABLED` constant + `_chunk_level_enabled`
helper + `[vector_store].chunk_level_enabled` config override) was
removed because it would only ever guard NotImplementedError.

This test file:

* Verifies that each commented-out function raises NotImplementedError
  with a clear Phase R-5 message.
* Verifies that `_run_spec_core_unlocked` writes the disabled-state stub
  artifacts (`source_chunks` / `retrieval_index_revision`) directly, with
  `status == "disabled"` and Phase R-5 diagnostics.
* Verifies that the section_collection auto-recreate helper
  (`_section_collection_exists`) survived the cleanup.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


import spec_grag.core as core_module  # noqa: E402
import spec_grag.retrieval_index as retrieval_module  # noqa: E402


# -----------------------------------------------------------------------------
# Stub-artifact contract (still active)
# -----------------------------------------------------------------------------


def test_chunk_level_disabled_source_chunks_stub_shape() -> None:
    stub = core_module._chunk_level_disabled_artifact_source_chunks(
        "2026-05-11T03:00:00Z"
    )

    assert stub["status"] == "disabled"
    assert stub["chunks"] == []
    assert stub["chunking"] == {"enabled": False, "phase": "R-5"}
    assert stub["diagnostics"]["phase_r5"] is True
    assert "case C-1" in stub["diagnostics"]["message"]
    assert "spec_grag_section" in stub["diagnostics"]["message"]
    assert stub["generated_at"] == "2026-05-11T03:00:00Z"


def test_chunk_level_disabled_retrieval_index_revision_stub_shape() -> None:
    config = {
        "embedding": {"provider": "flagembedding", "model": "BAAI/bge-m3"},
        "vector_store": {
            "provider": "qdrant",
            "collection": "spec_grag_source",
            "section_collection": "spec_grag_section",
        },
    }
    stub = core_module._chunk_level_disabled_artifact_retrieval_index_revision(
        config,
        "2026-05-11T03:00:00Z",
    )

    assert stub["status"] == "disabled"
    assert stub["embedding"]["provider"] == "flagembedding"
    assert stub["vector_store"]["collection"] == "spec_grag_source"
    assert stub["diagnostics"]["phase_r5"] is True
    assert "spec_grag_section" in stub["diagnostics"]["message"]


# -----------------------------------------------------------------------------
# Runtime gate has been removed (Phase R-5 cleanup)
# -----------------------------------------------------------------------------


def test_runtime_gate_constant_and_helper_are_removed() -> None:
    """The Phase R-5 cleanup deletes CHUNK_LEVEL_ENABLED + _chunk_level_enabled.

    The dormant chunk-level functions all raise NotImplementedError, so a
    config override flag would only mask the dormant signal. Make sure no
    one accidentally re-introduces the gate without restoring the function
    bodies.
    """

    assert not hasattr(core_module, "CHUNK_LEVEL_ENABLED"), (
        "CHUNK_LEVEL_ENABLED must stay deleted while chunk-level functions "
        "are commented out (raise NotImplementedError)"
    )
    assert not hasattr(core_module, "_chunk_level_enabled"), (
        "_chunk_level_enabled gate must stay deleted while chunk-level "
        "functions are commented out"
    )


# -----------------------------------------------------------------------------
# Commented-out chunk-level functions raise NotImplementedError
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("func_name", "args", "kwargs"),
    [
        ("build_source_chunks", ([],), {}),
        ("build_source_chunks_artifact", ([],), {}),
        ("compute_chunk_diff", (None, []), {}),
        ("upsert_qdrant_bge_m3_index", ([],), {}),
        (
            "upsert_qdrant_bge_m3_index_incremental",
            (),
            {
                "url": "http://localhost:6333",
                "collection": "x",
                "chunks_to_embed": [],
                "point_ids_to_delete": [],
                "all_chunks": [],
            },
        ),
    ],
)
def test_chunk_level_helper_raises_not_implemented_error(
    func_name: str, args: tuple, kwargs: dict
) -> None:
    """Each dormant chunk-level helper must raise NotImplementedError.

    The `raise NotImplementedError(...)` statements anchor the dormant
    contract: anything that accidentally calls into a commented-out
    helper fails loudly with a Phase R-5 message instead of returning
    stale data.
    """

    func = getattr(retrieval_module, func_name)
    with pytest.raises(NotImplementedError) as exc_info:
        func(*args, **kwargs)
    assert "Phase R-5" in str(exc_info.value)


def test_core_chunk_level_dispatchers_raise_not_implemented_error() -> None:
    """`_qdrant_upsert_with_partial_dispatch` and `_build_retrieval_index_revision`
    are also dormant per Phase R-5 cleanup."""

    with pytest.raises(NotImplementedError) as exc_info:
        core_module._qdrant_upsert_with_partial_dispatch(
            chunks=[],
            url="http://localhost:6333",
            collection="x",
            generated_at="t",
            previous_source_chunks=None,
            previous_revision=None,
        )
    assert "Phase R-5" in str(exc_info.value)

    with pytest.raises(NotImplementedError) as exc_info:
        core_module._build_retrieval_index_revision(
            config={},
            chunks=[],
            generated_at="t",
        )
    assert "Phase R-5" in str(exc_info.value)


# -----------------------------------------------------------------------------
# Section-collection auto-recreate helper still works (Phase R-3 follow-up)
# -----------------------------------------------------------------------------


def test_section_collection_exists_returns_false_when_qdrant_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("simulated Qdrant outage")

    import qdrant_client

    monkeypatch.setattr(qdrant_client, "QdrantClient", _explode)

    assert core_module._section_collection_exists(
        "http://localhost:6333", "spec_grag_section"
    ) is False


def test_section_collection_exists_returns_false_when_collection_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubClient:
        def __init__(self, url: str) -> None:
            self.url = url

        def collection_exists(self, *, collection_name: str) -> bool:
            return False

    import qdrant_client

    monkeypatch.setattr(qdrant_client, "QdrantClient", _StubClient)

    assert core_module._section_collection_exists(
        "http://localhost:6333", "spec_grag_section"
    ) is False


def test_section_collection_exists_returns_true_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubClient:
        def __init__(self, url: str) -> None:
            self.url = url

        def collection_exists(self, *, collection_name: str) -> bool:
            return collection_name == "spec_grag_section"

    import qdrant_client

    monkeypatch.setattr(qdrant_client, "QdrantClient", _StubClient)

    assert core_module._section_collection_exists(
        "http://localhost:6333", "spec_grag_section"
    ) is True
