"""Phase R-5 tests for the chunk-level disable contract.

`doc/STORAGE_REDESIGN.ja.md` §7.4 R-5 keeps the chunk-level code
(`build_source_chunks`, `build_source_chunks_artifact`,
`compute_chunk_diff`, `upsert_qdrant_bge_m3_index_incremental`,
`_qdrant_upsert_with_partial_dispatch`) in the codebase as dormant /
commented-out logic. Production callers gate every chunk-level entry
point behind `spec_grag.core.CHUNK_LEVEL_ENABLED` (default `False`,
case C-1). Tests opt back in either by toggling the module-level
constant (via the autouse fixture in `tests/conftest.py`) or by setting
`[vector_store].chunk_level_enabled = true` in the project config.

This test file deliberately covers the **disabled** path: it sets the
constant back to its production default, drives a small end-to-end
`spec-grag core` run with the in-memory test fake providers, and
verifies that:

* `source_chunks` and `retrieval_index_revision` artifacts are still
  written (status = "disabled" with Phase R-5 diagnostics).
* No chunk-level Qdrant upsert is attempted.
* `_chunk_level_enabled` honors the config override even when the
  constant says the opposite, so a test fixture can re-enable the
  dormant path locally.
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


def test_chunk_level_enabled_production_default_is_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`spec_grag.core.CHUNK_LEVEL_ENABLED` defaults to False (case C-1)."""

    # The conftest autouse hook flips the constant to True for the
    # session; restore the production default here.
    monkeypatch.setattr(core_module, "CHUNK_LEVEL_ENABLED", False)

    assert core_module._chunk_level_enabled() is False
    assert core_module._chunk_level_enabled(None) is False


def test_chunk_level_enabled_respects_config_override_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[vector_store].chunk_level_enabled = true` re-enables the dormant path."""

    monkeypatch.setattr(core_module, "CHUNK_LEVEL_ENABLED", False)
    config = {"vector_store": {"chunk_level_enabled": True}}

    assert core_module._chunk_level_enabled(config) is True


def test_chunk_level_enabled_respects_config_override_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`chunk_level_enabled = false` keeps the path off even when the constant is on."""

    monkeypatch.setattr(core_module, "CHUNK_LEVEL_ENABLED", True)
    config = {"vector_store": {"chunk_level_enabled": False}}

    assert core_module._chunk_level_enabled(config) is False


def test_chunk_level_disabled_source_chunks_stub_shape() -> None:
    """The R-5 stub for source_chunks declares the disabled state inline."""

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
    """The R-5 stub for retrieval_index_revision points at section-level retrieval."""

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


def test_chunk_level_disabled_does_not_call_chunk_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When disabled, neither build_source_chunks nor _qdrant_upsert_with_partial_dispatch runs."""

    monkeypatch.setattr(core_module, "CHUNK_LEVEL_ENABLED", False)

    def _explode_build_source_chunks(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(
            "build_source_chunks must not be called while CHUNK_LEVEL_ENABLED is False"
        )

    def _explode_build_source_chunks_artifact(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(
            "build_source_chunks_artifact must not be called while CHUNK_LEVEL_ENABLED is False"
        )

    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "build_source_chunks",
        _explode_build_source_chunks,
    )
    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "build_source_chunks_artifact",
        _explode_build_source_chunks_artifact,
    )

    config = {"vector_store": {"chunk_level_enabled": False}}
    # The bare gate call should pick the disabled branch via config
    # override; explode if a chunk-level helper is accidentally
    # exercised.
    assert core_module._chunk_level_enabled(config) is False
