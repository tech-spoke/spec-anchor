"""`/spec-core` orchestration contract tests for G-11.

These tests pin the public orchestration behavior while leaving the concrete
builder shape flexible.  They accept dictionaries or dataclasses and try common
dependency injection names so the implementation can choose a clean API without
rewriting the contract.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


CONFIG = """\
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[context]
storage = ".spec-grag/context"

[section]
max_heading_level = 4

[llm.providers.fake]
command = "fake-noop"
model = "fake-spec-core"
timeout_sec = 5
max_retries = 0

[embedding]
provider = "fake"
model = "fake-embedding"

    [vector_store]
    provider = "memory"
    """

@dataclass
class FakeSpecCoreProvider:
    conflict_outcome: str = "resolved"

    def __post_init__(self) -> None:
        self.calls: list[Any] = []

    @property
    def provider_id(self) -> str:
        return f"fake-spec-core-{self.conflict_outcome}"

    def generate(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
        self.calls.append(request)
        section_hashes = getattr(request, "section_hashes", None)
        if (
            str(getattr(request, "stage", "")) == "section_metadata"
            and isinstance(section_hashes, dict)
            and section_hashes
        ):
            return {
                "sections": [
                    {
                        "section_id": str(section_id),
                        "summary": f"summary:{section_id}",
                        "search_keys": [f"key:{section_id}"],
                        "related_sections": [],
                    }
                    for section_id in section_hashes
                ]
            }
        text = _request_text(request)
        section_id = _request_section_id(request)
        if "conflict" in text.lower() or "judge" in text.lower():
            return self._conflict_payload()
        return {
            "summary": f"summary:{section_id}:{_fingerprint(text)}",
            "search_keys": [f"key:{section_id}", f"hash:{_fingerprint(text)}"],
            "related_sections": [],
            "chapter_summary": f"chapter:{_fingerprint(text)}",
            "key_topics": [f"topic:{_fingerprint(text)}"],
            "important_sections": [section_id] if section_id else [],
        }

    def judge(self, pair: Any, **_: Any) -> dict[str, Any]:
        self.calls.append(pair)
        return self._conflict_payload()

    def judge_conflict(self, pair: Any, **_: Any) -> dict[str, Any]:
        self.calls.append(pair)
        return self._conflict_payload()

    def _conflict_payload(self) -> dict[str, Any]:
        if self.conflict_outcome == "unresolved":
            return {
                "outcome": "needs_human_review",
                "severity": "high",
                "claims": [
                    {"side": "a", "summary": "Alpha requires FEATURE_X."},
                    {"side": "b", "summary": "Beta forbids FEATURE_X."},
                ],
                "why_conflicting": "FEATURE_X cannot be both required and forbidden.",
                "why_llm_cannot_decide": "Purpose and Core Concept do not define priority.",
                "decision_options": [
                    {"id": "prefer_a", "label": "Prefer Alpha"},
                    {"id": "prefer_b", "label": "Prefer Beta"},
                    {"id": "conditional", "label": "Conditional rule"},
                    {"id": "dismiss", "label": "Not a conflict"},
                    {"id": "needs_source_update", "label": "Update Source Specs"},
                    {"id": "defer", "label": "Defer"},
                    {"id": "task_scope_resolution", "label": "Resolve for task only"},
                ],
                "recommended_next_action": "Ask a human to choose the applicable rule.",
            }
        return {
            "outcome": "resolved_by_existing_evidence",
            "severity": "medium",
            "warning": "Core Concept priority resolves this potential conflict.",
            "why_not_pending": "Existing evidence is enough.",
        }


def _core_module() -> Any:
    try:
        return importlib.import_module("spec_grag.core")
    except ModuleNotFoundError as exc:
        if exc.name == "spec_grag.core":
            pytest.fail("spec_grag.core module is required for G-11 `/spec-core`")
        raise


def _required_function(module: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail("`/spec-core` public API is required; expected one of: " + ", ".join(names))


def _run_function() -> Any:
    return _required_function(
        _core_module(),
        (
            "run_spec_core",
            "spec_core",
            "run_core",
            "core",
            "execute_spec_core",
        ),
    )


def _call(func: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    supported = {
        name: value for name, value in kwargs.items() if name in signature.parameters
    }
    try:
        return func(**supported)
    except TypeError:
        return func(*kwargs.get("_positional", ()), **supported)


def _run_spec_core(project_root: Path, **kwargs: Any) -> Any:
    func = _run_function()
    all_mode = bool(kwargs.pop("all_mode", False))
    decision_payload = kwargs.pop("decision_payload", None)
    provider = kwargs.pop("provider", None)
    return _call(
        func,
        _positional=(project_root,),
        project_root=project_root,
        root=project_root,
        cwd=project_root,
        all=all_mode,
        all_mode=all_mode,
        full=all_mode,
        force=all_mode,
        mode="full" if all_mode else "incremental",
        decision_payload=decision_payload,
        decision=decision_payload,
        conflict_decision=decision_payload,
        provider=provider,
        llm_provider=provider,
        conflict_judge=provider,
        judge=provider,
        generated_at="2026-05-06T00:00:00Z",
        **kwargs,
    )


def _write_project(project_root: Path) -> dict[str, Path]:
    (project_root / ".spec-grag").mkdir(parents=True)
    (project_root / ".spec-grag" / "config.toml").write_text(CONFIG)
    (project_root / "docs/core").mkdir(parents=True)
    (project_root / "docs/spec").mkdir(parents=True)
    purpose = project_root / "docs/core/purpose.md"
    concept = project_root / "docs/core/concept.md"
    main = project_root / "docs/spec/main.md"
    other = project_root / "docs/spec/other.md"
    purpose.write_text("# Purpose\nShip reliable behavior.\n")
    concept.write_text("# Core Concept\nSource Specs are the authority.\n")
    main.write_text(
        "# Main\n"
        "Intro.\n\n"
        "## Alpha\n"
        "Alpha requires FEATURE_X for standard requests.\n\n"
        "## Beta\n"
        "Beta allows FEATURE_X when enabled by config.\n\n"
        "## Gamma\n"
        "Gamma defines CACHE_MODE as optional.\n"
    )
    other.write_text(
        "# Other\n"
        "Intro.\n\n"
        "## Delta\n"
        "Delta references CACHE_MODE for search coverage.\n"
    )
    return {"purpose": purpose, "concept": concept, "main": main, "other": other}


def _write_real_provider_project(
    project_root: Path,
    *,
    collection: str,
    qdrant_url: str,
) -> None:
    command = os.environ.get(
        "SPEC_GRAG_REAL_PROVIDER_COMMAND",
        os.environ.get("SPEC_GRAG_REAL_PROVIDER_COMMAND", "codex"),
    )
    (project_root / ".spec-grag").mkdir(parents=True)
    (project_root / "docs/core").mkdir(parents=True)
    (project_root / "docs/spec").mkdir(parents=True)
    (project_root / ".spec-grag/config.toml").write_text(
        f"""\
[sources]
include = ["docs/spec/**/*.md"]
exclude = []

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[context]
storage = ".spec-grag/context"

[section]
max_heading_level = 4

[llm.providers.real]
command = "{command}"
model = "real-smoke"
effort = "low"
timeout_sec = 60
max_retries = 0

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"
dense_enabled = true
sparse_enabled = true

[vector_store]
provider = "qdrant"
url = "{qdrant_url}"
collection = "{collection}"
"""
    )
    (project_root / "docs/core/purpose.md").write_text("# Purpose\nVerify real /spec-core provider usage.\n")
    (project_root / "docs/core/concept.md").write_text("# Core Concept\nThe configured [llm] provider must generate metadata.\n")
    (project_root / "docs/spec/main.md").write_text(
        "# Main\n\n"
        "## Provider Path\n"
        "The normal spec-core path must call the configured CLI provider and build a real index.\n"
    )


def _write_multi_source_real_provider_project(
    project_root: Path,
    *,
    collection: str,
    qdrant_url: str,
) -> None:
    _write_real_provider_project(
        project_root,
        collection=collection,
        qdrant_url=qdrant_url,
    )
    (project_root / "docs/spec/auth.md").write_text(
        "# Auth\n\n"
        "## Session Validation\n"
        "Authentication must validate active sessions before privileged changes.\n\n"
        "## Pending Conflict Gate\n"
        "Pending Conflict Review Items block inject and realign until a human decides.\n"
    )
    (project_root / "docs/spec/search.md").write_text(
        "# Search\n\n"
        "## Hybrid Retrieval\n"
        "Qdrant dense and sparse retrieval must be fused with RRF for Source Specs.\n"
    )


def _write_large_project(project_root: Path, *, section_count: int = 52) -> None:
    (project_root / ".spec-grag").mkdir(parents=True)
    (project_root / ".spec-grag" / "config.toml").write_text(
        CONFIG
        + """\

[limits]
llm_batch_max_sections = 8
llm_batch_max_chars = 12000
section_summary_max_chars = 480
search_keys_max = 32
"""
    )
    (project_root / "docs/core").mkdir(parents=True)
    (project_root / "docs/spec").mkdir(parents=True)
    (project_root / "docs/core/purpose.md").write_text("# Purpose\nKeep large projects responsive.\n")
    (project_root / "docs/core/concept.md").write_text("# Core Concept\nBatch metadata generation is required.\n")
    sections = ["# Large Spec\nIntro.\n"]
    for index in range(1, section_count + 1):
        sections.append(
            f"## Feature {index:02d}\n"
            f"Feature {index:02d} defines a stable requirement for batch generation.\n"
        )
    (project_root / "docs/spec/large.md").write_text("\n".join(sections))


def _value(value: Any, *path: str, default: Any = None) -> Any:
    current = value
    for key in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            current = getattr(current, key, default)
    return current


def _result_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        result = result.to_dict()
    if hasattr(result, "__dict__") and not isinstance(result, dict):
        result = vars(result)
    assert isinstance(result, dict), "CoreResult must be dict-like or dataclass-like"
    return dict(result)


def _freshness(result: Any) -> dict[str, Any]:
    payload = _value(result, "freshness_report") or _value(result, "freshness") or result
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    if hasattr(payload, "__dict__") and not isinstance(payload, dict):
        payload = vars(payload)
    assert isinstance(payload, dict), "CoreResult must expose freshness_report"
    return dict(payload)


def _artifact(project_root: Path, name: str) -> dict[str, Any]:
    from spec_grag.artifacts import ARTIFACT_FILENAMES

    path = project_root / ".spec-grag/context" / ARTIFACT_FILENAMES[name]
    assert path.is_file(), f"{name} artifact must be written at {path}"
    return json.loads(path.read_text())


def _artifact_texts(project_root: Path) -> dict[str, str]:
    from spec_grag.artifacts import ARTIFACT_FILENAMES

    context_dir = project_root / ".spec-grag/context"
    return {
        name: (context_dir / filename).read_text()
        for name, filename in ARTIFACT_FILENAMES.items()
        if (context_dir / filename).is_file()
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _looks_exclusively_blocked(result: Any, *expected_terms: str) -> bool:
    try:
        freshness = _freshness(result)
    except AssertionError:
        freshness = {}
    status = (
        str(freshness.get("status") or _value(result, "status") or "").lower()
    )
    reasons = freshness.get("blocking_reasons") or _value(result, "blocking_reasons", default=[])
    text = _json_text({"status": status, "reasons": reasons, "result": result}).lower()
    return (
        status in {"blocked", "locked"}
        or "blocked" in text
        or "locked" in text
    ) and any(term in text for term in expected_terms)


def _sections(project_root: Path) -> list[dict[str, Any]]:
    metadata = _artifact(project_root, "section_metadata")
    sections = metadata.get("sections", [])
    assert isinstance(sections, list), "section_metadata.sections must be a list"
    return [dict(section) for section in sections]


def _section_by_id(project_root: Path, suffix: str) -> dict[str, Any]:
    for section in _sections(project_root):
        section_id = str(section.get("section_id") or section.get("source_section_id"))
        if section_id.endswith(suffix) or _legacy_section_id(section_id).endswith(suffix):
            return section
    pytest.fail(f"section ending with {suffix!r} was not generated")


def _ids(items: Any) -> set[str]:
    assert isinstance(items, list), "CoreResult field must be list-like"
    ids: set[str] = set()
    for item in items:
        if isinstance(item, str):
            ids.add(item)
        else:
            ids.add(str(_value(item, "section_id") or _value(item, "source_section_id") or item))
    return ids


def _has_id(ids: set[str], expected: str) -> bool:
    return any(
        value == expected
        or value.endswith(expected)
        or _legacy_section_id(value) == expected
        or _legacy_section_id(value).endswith(expected)
        for value in ids
    )


def _legacy_section_id(section_id: str) -> str:
    return re.sub(r"#\d{4}-", "#", section_id)


def _request_text(request: Any) -> str:
    if isinstance(request, dict):
        return " ".join(str(value) for value in request.values())
    return str(getattr(request, "input_text", None) or getattr(request, "prompt", None) or request)


def _request_section_id(request: Any) -> str:
    if isinstance(request, dict):
        return str(request.get("section_id") or request.get("source_section_id") or "unknown")
    return str(getattr(request, "section_id", None) or getattr(request, "source_section_id", None) or "unknown")


def _metadata_calls(provider: FakeSpecCoreProvider) -> list[Any]:
    return [
        call
        for call in provider.calls
        if str(getattr(call, "stage", "")) == "section_metadata"
    ]


def _request_section_ids(request: Any) -> list[str]:
    section_hashes = getattr(request, "section_hashes", None)
    if isinstance(section_hashes, dict):
        return [str(section_id) for section_id in section_hashes]
    section_id = _request_section_id(request)
    return [] if section_id == "unknown" else [section_id]


def _fingerprint(text: str) -> str:
    return str(abs(hash(text)) % 100_000)


class RelatedSectionsProvider(FakeSpecCoreProvider):
    def generate(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
        payload = super().generate(request, timeout_sec=timeout_sec)
        text = _request_text(request)
        section_ids = _request_section_ids(request)
        if "CACHE_MODE" not in text:
            return payload
        related_item = {
            "target_section_id": "docs/spec/other.md#0002-delta",
            "relation_hint": "depends_on",
            "confidence": "high",
            "reason": "Both sections define CACHE_MODE behavior.",
            "evidence_terms": ["CACHE_MODE"],
            "channels": ["shared_identifier"],
        }
        # Batch related-sections selection requests have section_ids drawn from
        # section_hashes; produce a dict keyed by source_section_id when the
        # request is a related-section batch. Fall back to a list for legacy
        # single-source callers.
        is_batch_related = (
            getattr(request, "stage", "") == "related_section_selection"
            and len(section_ids) > 1
        )
        gamma_id = next(
            (section_id for section_id in section_ids if section_id.endswith("gamma")),
            None,
        )
        if is_batch_related:
            related_map: dict[str, list[dict[str, Any]]] = {
                section_id: [] for section_id in section_ids
            }
            if gamma_id is not None:
                related_map[gamma_id] = [related_item]
            payload["related_sections"] = related_map
        elif gamma_id is not None or _request_section_id(request).endswith("gamma"):
            payload["related_sections"] = [related_item]
        return payload


class FailingSpecCoreProvider(FakeSpecCoreProvider):
    @property
    def provider_id(self) -> str:
        return "failing-spec-core"

    def generate(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
        self.calls.append(request)
        return {"unexpected": "simulated provider failure"}


class EvidenceGroundedConflictProvider(FakeSpecCoreProvider):
    def __init__(self) -> None:
        super().__init__("resolved")
        self.conflict_requests: list[Any] = []

    def judge_conflict(self, pair: Any, **_: Any) -> dict[str, Any]:
        self.conflict_requests.append(pair)
        request_text = _request_text(pair)
        has_grounding = (
            "Ship reliable behavior" in request_text
            or "docs/core/purpose.md" in request_text
        ) and (
            "Source Specs are the authority" in request_text
            or "docs/core/concept.md" in request_text
        )
        assert has_grounding, (
            "warning-only conflict resolution must be grounded in Purpose/Core "
            "Concept text or explicit refs"
        )
        return self._conflict_payload()


def test_t_i02_all_mode_regenerates_all_artifacts_and_returns_fresh(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    data = _result_dict(result)

    assert data["mode"] == "full"
    assert _freshness(result)["status"] == "fresh"
    assert not _freshness(result).get("blocking_reasons", [])
    updated_sources = _ids(data["updated_sources"])
    updated_sections = _ids(data["updated_sections"])
    assert _has_id(updated_sources, "docs/spec/main.md")
    assert _has_id(updated_sources, "docs/spec/other.md")
    for section_id in (
        "docs/spec/main.md#alpha",
        "docs/spec/main.md#beta",
        "docs/spec/main.md#gamma",
        "docs/spec/other.md#delta",
    ):
        assert _has_id(updated_sections, section_id)
    for artifact_name in (
        "section_manifest",
        "section_metadata",
        "chapter_anchors",
        "source_chunks",
        "retrieval_index_revision",
        "freshness",
    ):
        _artifact(project_root, artifact_name)


def test_g11_runtime_core_uses_section_parser_for_h1_only_source_specs(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    paths["other"].unlink()
    paths["main"].write_text("# Only Heading\nBody belongs to the H1 section.\n")

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )
    manifest_sections = _artifact(project_root, "section_manifest")["sections"]

    assert result["status"] == "updated"
    assert _freshness(result)["status"] == "fresh"
    assert len(manifest_sections) == 1
    assert manifest_sections[0]["source_document_id"] == "docs/spec/main.md"
    assert manifest_sections[0]["heading_path"] == ["Only Heading"]


def test_g11_runtime_core_uses_section_parser_for_no_heading_source_specs(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    paths["other"].unlink()
    paths["main"].write_text("A Source Spec without headings is still a required document.\n")

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )
    manifest_sections = _artifact(project_root, "section_manifest")["sections"]

    assert result["status"] == "updated"
    assert _freshness(result)["status"] == "fresh"
    assert len(manifest_sections) == 1
    assert manifest_sections[0]["heading_path"] == []
    assert manifest_sections[0]["section_id"] == "docs/spec/main.md#0001-document"


def test_g11_runtime_core_assigns_unique_ids_for_duplicate_headings(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    paths["other"].unlink()
    paths["main"].write_text(
        "# Main\n\n"
        "## API\n"
        "The first API section defines request validation.\n\n"
        "## API\n"
        "The second API section defines response validation.\n"
    )

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )
    ids = [
        str(section["section_id"])
        for section in _artifact(project_root, "section_manifest")["sections"]
    ]

    assert result["status"] == "updated"
    assert _freshness(result)["status"] == "fresh"
    assert len(ids) == len(set(ids))
    assert "docs/spec/main.md#0002-api" in ids
    assert "docs/spec/main.md#0003-api" in ids


def test_g11_runtime_core_ignores_fenced_code_headings_in_section_manifest(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    paths["other"].unlink()
    paths["main"].write_text(
        "# API\n"
        "before\n"
        "```markdown\n"
        "# Not a heading\n"
        "```\n"
        "## Details\n"
        "after\n"
    )

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )
    manifest_sections = _artifact(project_root, "section_manifest")["sections"]
    heading_paths = [section["heading_path"] for section in manifest_sections]

    assert result["status"] == "updated"
    assert _freshness(result)["status"] == "fresh"
    assert heading_paths == [["API"], ["API", "Details"]]
    assert all("Not a heading" not in section["heading_path"] for section in manifest_sections)


def test_g11_runtime_core_respects_sources_exclude_in_artifacts(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    config_path = project_root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text().replace(
            'include = ["docs/spec/**/*.md"]',
            'include = ["docs/spec/**/*.md"]\nexclude = ["docs/spec/drafts/**"]',
        )
    )
    draft = project_root / "docs/spec/drafts/ignored.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("# Draft\nThis draft must not enter runtime artifacts.\n")

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )
    manifest_sections = _artifact(project_root, "section_manifest")["sections"]
    source_docs = {str(section["source_document_id"]) for section in manifest_sections}

    assert result["status"] == "updated"
    assert "docs/spec/drafts/ignored.md" not in source_docs
    assert not any(source.startswith("docs/spec/drafts/") for source in source_docs)


def test_g11_runtime_core_fails_when_sources_include_matches_no_files(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    config_path = project_root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text().replace(
            'include = ["docs/spec/**/*.md"]',
            'include = ["docs/spec/missing/**/*.md"]',
        )
    )

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )
    freshness = _freshness(result)

    assert result["status"] == "failed"
    assert freshness["status"] == "failed"
    assert "failed_required_artifact" in freshness["blocking_reasons"]
    assert "sources.include" in _json_text(result)
    assert result["diagnostics"]["config_error"]["reason_code"] == "config_error"


def test_t_i01_incremental_updates_changed_section_and_skips_unchanged(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    unchanged_before = _section_by_id(project_root, "#beta")

    paths["main"].write_text(paths["main"].read_text().replace("standard requests", "enterprise requests"))
    result = _run_spec_core(project_root, provider=FakeSpecCoreProvider())
    data = _result_dict(result)
    changed_after = _section_by_id(project_root, "#alpha")
    unchanged_after = _section_by_id(project_root, "#beta")

    assert data["mode"] == "incremental"
    updated_sections = _ids(data["updated_sections"])
    assert _has_id(updated_sections, "docs/spec/main.md#alpha")
    assert not _has_id(updated_sections, "docs/spec/main.md#beta")
    assert changed_after["summary"]
    assert unchanged_after["summary"] == unchanged_before["summary"]
    assert unchanged_after["search_keys"] == unchanged_before["search_keys"]


@pytest.mark.skip(
    reason="Phase R-5 dormant: chunk-level retrieval_index_revision is "
    "always the disabled stub (no embedding_generation_skipped / "
    "skip_reason fields). See doc/STORAGE_REDESIGN.ja.md §7.4 R-5."
)
def test_t_e07_spec_core_batches_metadata_and_reuses_unchanged_sections(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "large-project"
    _write_large_project(project_root, section_count=52)
    provider = FakeSpecCoreProvider()

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=provider)
    )
    sections = _sections(project_root)
    metadata_calls = _metadata_calls(provider)
    generation = result["diagnostics"]["section_metadata_generation"]

    assert len(sections) >= 50
    assert 1 < len(metadata_calls) < len(sections)
    assert generation["llm_calls"] == len(metadata_calls)
    assert generation["batch_sizes"]
    assert max(generation["batch_sizes"]) <= 8
    assert all(1 <= len(_request_section_ids(call)) <= 8 for call in metadata_calls)

    full_provider = FakeSpecCoreProvider()
    full = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=full_provider)
    )
    full_generation = full["diagnostics"]["section_metadata_generation"]

    assert _metadata_calls(full_provider)
    assert full_generation["llm_calls"] == len(_metadata_calls(full_provider))
    assert full_generation["cache_hits"] == 0

    cached_provider = FakeSpecCoreProvider()
    cached = _result_dict(
        _run_spec_core(
            project_root,
            all_mode=True,
            provider=cached_provider,
            use_cache=True,
        )
    )
    cached_generation = cached["diagnostics"]["section_metadata_generation"]
    cached_revision = _artifact(project_root, "retrieval_index_revision")

    assert _metadata_calls(cached_provider) == []
    assert cached_generation["llm_calls"] == 0
    assert cached_generation["cache_hits"] >= len(sections)
    assert cached_revision["diagnostics"]["embedding_generation_skipped"] is True
    assert cached_revision["diagnostics"]["skip_reason"] == "source_hash_unchanged"


def test_t_i03_core_result_has_required_public_fields(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )

    assert {
        "mode",
        "updated_sources",
        "skipped_sources",
        "failed_sources",
        "failed_sections",
        "updated_sections",
        "regenerated_chapter_anchors",
        "retrieval_index_status",
        "potential_conflicts",
        "conflict_review_items",
        "pending_conflict_count",
        "unreflected_conflict_resolutions",
        "stale_resolution_count",
        "freshness_report",
        "warnings",
    }.issubset(result)
    assert result["mode"] in {"incremental", "full"}
    assert isinstance(result["pending_conflict_count"], int)
    assert isinstance(result["stale_resolution_count"], int)


def test_spec_core_does_not_modify_human_owned_purpose_or_concept(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    before = {name: path.read_text() for name, path in paths.items() if name in {"purpose", "concept"}}

    _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())

    assert paths["purpose"].read_text() == before["purpose"]
    assert paths["concept"].read_text() == before["concept"]


def test_t_i04_conflicts_with_unresolved_blocks_freshness(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    paths["main"].write_text(paths["main"].read_text().replace("allows FEATURE_X", "forbids FEATURE_X"))

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider("unresolved"))
    )

    assert result["conflict_review_items"]
    assert result["pending_conflict_count"] >= 1
    assert any(item.get("status") == "pending" for item in result["conflict_review_items"])
    assert _freshness(result)["status"] == "blocked"
    assert "pending_conflict" in _freshness(result).get("blocking_reasons", [])


def test_t_i04_resolved_conflicts_with_becomes_potential_conflict_warning(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    paths["main"].write_text(paths["main"].read_text().replace("allows FEATURE_X", "forbids FEATURE_X"))

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider("resolved"))
    )

    assert result["pending_conflict_count"] == 0
    assert result["conflict_review_items"] == []
    assert result["potential_conflicts"]
    assert _freshness(result)["status"] in {"fresh", "degraded"}


def test_t_i14_decision_payload_resolves_pending_item_through_spec_core_api(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    paths["main"].write_text(paths["main"].read_text().replace("allows FEATURE_X", "forbids FEATURE_X"))
    pending = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider("unresolved"))
    )
    pending_count_before = pending["pending_conflict_count"]
    conflict_id = pending["conflict_review_items"][0]["conflict_id"]

    result = _result_dict(
        _run_spec_core(
            project_root,
            provider=FakeSpecCoreProvider("resolved"),
            decision_payload={
                "conflict_id": conflict_id,
                "decision": "prefer_a",
                "selected_option": "prefer_a",
                "reason": "Human chose Alpha for this fixture.",
                "referenced_source_refs": ["docs/spec/main.md#alpha"],
                "human_acknowledgement": True,
            },
        )
    )

    item = next(item for item in result["conflict_review_items"] if item["conflict_id"] == conflict_id)
    assert item["status"] == "resolved"
    assert item["resolution"]["reason"]
    assert result["pending_conflict_count"] == pending_count_before - 1
    assert _freshness(result)["status"] == (
        "fresh" if result["pending_conflict_count"] == 0 else "blocked"
    )


def test_t_i15_spec_core_uses_atomic_context_update_and_writes_freshness_last(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_grag.artifacts import ContextArtifactStore

    project_root = tmp_path / "project"
    _write_project(project_root)
    calls: list[list[str]] = []
    original = ContextArtifactStore.write_context_update

    def spy(self: ContextArtifactStore, artifacts: dict[str, Any]) -> list[Path]:
        written = original(self, artifacts)
        calls.append([path.name for path in written])
        return written

    monkeypatch.setattr(ContextArtifactStore, "write_context_update", spy)
    _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())

    assert calls, "`/spec-core` must write artifacts through ContextArtifactStore.write_context_update"
    assert calls[-1][-1] == "freshness.json"


def test_g11_context_update_rolls_back_partial_artifact_set_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_grag.artifacts import ContextArtifactStore

    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    complete_before = _artifact_texts(project_root)
    original_write = ContextArtifactStore.write

    def fail_after_some_artifacts(
        self: ContextArtifactStore,
        artifact_name: str,
        payload: dict[str, Any],
    ) -> Path:
        if artifact_name == "source_chunks":
            raise OSError("simulated context update failure")
        return original_write(self, artifact_name, payload)

    paths["main"].write_text(
        paths["main"].read_text().replace(
            "Gamma defines CACHE_MODE as optional.",
            "Gamma defines CACHE_MODE as required for review failure coverage.",
        )
    )
    monkeypatch.setattr(ContextArtifactStore, "write", fail_after_some_artifacts)

    with pytest.raises(OSError, match="simulated context update failure"):
        _run_spec_core(project_root, provider=FakeSpecCoreProvider())

    assert _artifact_texts(project_root) == complete_before


def test_g14_manual_spec_core_does_not_update_artifacts_while_watcher_running(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    state_dir = project_root / ".spec-grag/state"
    state_dir.mkdir(parents=True)
    _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    artifacts_before = _artifact_texts(project_root)

    (state_dir / "watch_state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": True,
                "owner": "watcher",
                "run_id": "watcher-run-in-progress",
                "started_at_epoch_ms": 1_000_000,
                "updated_at_epoch_ms": 1_000_000,
            }
        )
    )
    paths["main"].write_text(
        paths["main"].read_text().replace(
            "standard requests",
            "manual core must not process this while watcher is running",
        )
    )

    try:
        result = _run_spec_core(project_root, provider=FakeSpecCoreProvider())
    except Exception as exc:
        message = str(exc).lower()
        assert any(term in message for term in ("watcher", "running", "lock", "locked", "blocked"))
    else:
        assert _looks_exclusively_blocked(
            result,
            "watcher_running",
            "watcher",
            "locked",
            "blocked",
        ), "manual `/spec-core` must report watcher-running lock contention"

    assert _artifact_texts(project_root) == artifacts_before, (
        "manual `/spec-core` must not update context artifacts while watcher owns the lock"
    )


def test_g14_manual_spec_core_ignores_stale_watcher_state_without_now_ms(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    state_dir = project_root / ".spec-grag/state"
    state_dir.mkdir(parents=True)
    provider = FakeSpecCoreProvider()

    (state_dir / "watch_state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "running": True,
                "owner": "watcher",
                "run_id": "stale-watcher-state",
                "started_at_epoch_ms": 1,
                "updated_at_epoch_ms": 1,
            }
        )
    )

    result = _result_dict(
        _run_spec_core(project_root, provider=provider, stale_lock_ms=100)
    )

    assert provider.calls, "manual `/spec-core` must not permanently block on stale watcher state"
    assert result["status"] != "blocked"
    assert _freshness(result)["status"] == "fresh"


def test_g11_spec_core_populates_related_sections_through_core_path(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    _run_spec_core(project_root, all_mode=True, provider=RelatedSectionsProvider())

    related_entries = [
        related
        for section in _sections(project_root)
        for related in section.get("related_sections", [])
    ]
    assert related_entries, "`/spec-core` must orchestrate and persist Related Sections"
    assert any(
        _has_id({str(related.get("target_section_id", ""))}, "docs/spec/other.md#delta")
        and related.get("relation_hint") != "conflicts_with"
        for related in related_entries
    )


def test_g11_core_builds_configured_llm_provider_when_not_injected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    provider = FakeSpecCoreProvider()
    build_calls: list[Any] = []
    core_module = _core_module()

    def fake_build(llm_config: Any, **kwargs: Any) -> Any:
        build_calls.append((llm_config, kwargs))
        return provider

    monkeypatch.setattr(
        core_module.llm_provider_api,
        "build_spec_core_llm_provider",
        fake_build,
    )

    result = _result_dict(core_module.run_spec_core(project_root, all_mode=True))

    assert result["status"] == "updated"
    assert build_calls, "normal `/spec-core` must build provider from [llm]"
    assert provider.calls, "configured provider must be called without explicit injection"
    stages = {str(getattr(call, "stage", "")) for call in provider.calls}
    assert "section_metadata" in stages
    sections = _sections(project_root)
    assert any(section["summary"].startswith("summary:") for section in sections)


def test_g11_core_can_select_codex_or_claude_from_shared_llm_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    config_path = project_root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text().replace(
            '[llm.providers.fake]\ncommand = "fake-noop"\nmodel = "fake-spec-core"\ntimeout_sec = 5\nmax_retries = 0\n',
            """\
[llm.providers.codex]
command = "codex"
model = "codex-test"
effort = "low"
timeout_sec = 5
max_retries = 0

[llm.providers.claude]
command = "claude"
model = "claude-test"
effort = "low"
timeout_sec = 5
max_retries = 0
""",
        )
    )
    provider = FakeSpecCoreProvider()
    build_calls: list[tuple[Any, dict[str, Any]]] = []
    core_module = _core_module()

    def fake_build(llm_config: Any, **kwargs: Any) -> Any:
        build_calls.append((llm_config, kwargs))
        return provider

    monkeypatch.setattr(
        core_module.llm_provider_api,
        "build_spec_core_llm_provider",
        fake_build,
    )

    result = _result_dict(
        core_module.run_spec_core(
            project_root,
            all_mode=True,
            llm_provider_id="claude",
        )
    )

    assert result["status"] == "updated"
    selected_config, kwargs = build_calls[0]
    assert selected_config["command"] == "claude"
    assert selected_config["model"] == "claude-test"
    assert kwargs["provider_id"] == "claude"


def test_g11_configured_real_cli_provider_runs_without_env_gate_and_no_fake_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    config_path = project_root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text().replace(
            '[llm.providers.fake]\ncommand = "fake-noop"\nmodel = "fake-spec-core"\ntimeout_sec = 5\nmax_retries = 0\n',
            '[llm.providers.codex]\ncommand = "codex"\nmodel = "real-smoke"\neffort = "low"\ntimeout_sec = 5\nmax_retries = 0\n',
        )
    )
    core_module = _core_module()
    monkeypatch.delenv("SPEC_GRAG_REAL_PROVIDER", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_SMOKE", raising=False)
    monkeypatch.delenv("SPEC_GRAG_FAKE_PROVIDER", raising=False)
    calls: list[Any] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"args": args, "kwargs": kwargs})
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="provider failed")

    monkeypatch.setattr(core_module.llm_provider_api.subprocess, "run", fake_run)

    result = _result_dict(core_module.run_spec_core(project_root, all_mode=True))
    freshness = _freshness(result)

    assert result["status"] == "failed"
    assert freshness["status"] == "failed"
    assert "failed_required_artifact" in freshness["blocking_reasons"]
    assert result["failed_sections"]
    sections = _sections(project_root)
    assert all(section["llm_provider"] == "codex" for section in sections)
    assert all(section["llm_generation_status"] == "failed" for section in sections)
    text = _json_text(result).lower()
    assert calls, "configured real provider must be called without env opt-in"
    assert "provider failed" in text
    assert "summary:" not in text


def test_t_r12_configured_real_provider_is_default_without_smoke_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_grag.llm_provider import build_spec_core_llm_provider

    monkeypatch.delenv("SPEC_GRAG_REAL_PROVIDER", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_SMOKE", raising=False)
    monkeypatch.delenv("SPEC_GRAG_FAKE_PROVIDER", raising=False)

    provider = build_spec_core_llm_provider(
        {
            "providers": {
                "codex": {
                    "command": "codex",
                    "model": "real-smoke",
                    "effort": "low",
                },
            },
        }
    )

    assert getattr(provider, "provider_id") == "codex"
    assert getattr(provider, "real_provider_enabled") is True


def test_g11_provider_failure_does_not_use_fixed_metadata_fallback(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    provider = FailingSpecCoreProvider()

    result = _result_dict(_run_spec_core(project_root, all_mode=True, provider=provider))
    freshness = _freshness(result)

    assert result["status"] == "failed"
    assert freshness["status"] == "failed"
    assert "failed_required_artifact" in freshness["blocking_reasons"]
    assert result["failed_sections"]
    sections = _sections(project_root)
    assert all(section["summary"] == "" for section in sections)
    assert all(section["search_keys"] == [] for section in sections)


@pytest.mark.skip(
    reason="Phase R-5 dormant: chunk-level upsert_qdrant_bge_m3_index is "
    "commented out. See doc/STORAGE_REDESIGN.ja.md §7.4 R-5."
)
def test_g11_standard_retrieval_service_failure_is_failed_not_fake_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    config_path = project_root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text()
        .replace(
            '[embedding]\nprovider = "fake"\nmodel = "fake-embedding"\n',
            '[embedding]\nprovider = "flagembedding"\nmodel = "BAAI/bge-m3"\ndense_enabled = true\nsparse_enabled = true\n',
        )
        .replace(
            '    [vector_store]\n    provider = "memory"\n    ',
            '[vector_store]\nprovider = "qdrant"\nurl = "http://localhost:6333"\ncollection = "spec_grag_source"\n',
        )
    )
    core_module = _core_module()

    def fake_upsert(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "upsert_qdrant_bge_m3_index",
        fake_upsert,
    )

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )
    freshness = _freshness(result)
    revision = _artifact(project_root, "retrieval_index_revision")

    assert result["status"] == "failed"
    assert result["retrieval_index_status"] == "failed"
    assert freshness["status"] == "failed"
    assert "failed_required_artifact" in freshness["blocking_reasons"]
    assert revision["status"] == "failed"
    assert revision["diagnostics"]["real_retrieval_index"] is False
    assert "qdrant unavailable" in _json_text(revision)


@pytest.mark.skip(
    reason="Phase R-5 dormant: chunk-level upsert_qdrant_bge_m3_index is "
    "commented out. See doc/STORAGE_REDESIGN.ja.md §7.4 R-5."
)
def test_t_r12_standard_qdrant_retrieval_is_default_without_smoke_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)
    config_path = project_root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text()
        .replace(
            '[embedding]\nprovider = "fake"\nmodel = "fake-embedding"\n',
            '[embedding]\nprovider = "flagembedding"\nmodel = "BAAI/bge-m3"\ndense_enabled = true\nsparse_enabled = true\n',
        )
        .replace(
            '    [vector_store]\n    provider = "memory"\n    ',
            '[vector_store]\nprovider = "qdrant"\nurl = "http://localhost:6333"\ncollection = "spec_grag_source"\n',
        )
    )
    calls: list[dict[str, Any]] = []

    def fake_upsert(chunks: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"chunks": list(chunks), **kwargs})
        return {
            "status": "success",
            "artifact_revision": "fake-real-retrieval",
            "diagnostics": {
                "real_retrieval_index": True,
                "qdrant_url": kwargs["url"],
                "collection": kwargs["collection"],
                "embedding_model": "BAAI/bge-m3",
                "fusion_method": "rrf",
            },
        }

    monkeypatch.delenv("SPEC_GRAG_REAL_RETRIEVAL", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_SMOKE", raising=False)
    monkeypatch.delenv("SPEC_GRAG_LOCAL_SERVICE", raising=False)
    core_module = _core_module()
    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "upsert_qdrant_bge_m3_index",
        fake_upsert,
    )

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )

    assert result["status"] != "failed"
    assert result["retrieval_index_status"] == "success"
    assert calls, "standard Qdrant/BGE-M3 config must run real retrieval without env opt-in"


@pytest.mark.skip(
    reason="Phase R-5 dormant: chunk-level upsert_qdrant_bge_m3_index is "
    "commented out. See doc/STORAGE_REDESIGN.ja.md §7.4 R-5."
)
@pytest.mark.parametrize(
    ("exc", "reason_code"),
    [
        (RuntimeError("401 Unauthorized: Not logged in"), "agent_cli_unauthenticated"),
        (ConnectionError("Qdrant connection refused"), "qdrant_service_unavailable"),
        (ValueError("Qdrant schema mismatch: dense vector size differs"), "qdrant_schema_mismatch"),
        (RuntimeError("FlagEmbedding BGE-M3 model load failure"), "embedding_model_load_failure"),
        (TimeoutError("provider timeout while generating vectors"), "provider_timeout"),
    ],
)
def test_t_r15_retrieval_failure_diagnostics_distinguish_required_categories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc: Exception,
    reason_code: str,
) -> None:
    project_root = tmp_path / f"project-{reason_code}"
    _write_project(project_root)
    config_path = project_root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text()
        .replace(
            '[embedding]\nprovider = "fake"\nmodel = "fake-embedding"\n',
            '[embedding]\nprovider = "flagembedding"\nmodel = "BAAI/bge-m3"\ndense_enabled = true\nsparse_enabled = true\n',
        )
        .replace(
            '    [vector_store]\n    provider = "memory"\n    ',
            '[vector_store]\nprovider = "qdrant"\nurl = "http://127.0.0.1:65535"\ncollection = "spec_grag_failure"\n',
        )
    )
    monkeypatch.delenv("SPEC_GRAG_REAL_RETRIEVAL", raising=False)

    core_module = _core_module()

    def failing_upsert(*_: Any, **__: Any) -> dict[str, Any]:
        raise exc

    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "upsert_qdrant_bge_m3_index",
        failing_upsert,
    )

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider())
    )
    revision = _artifact(project_root, "retrieval_index_revision")

    assert result["status"] == "failed"
    assert result["retrieval_index_status"] == "failed"
    assert revision["status"] == "failed"
    assert revision["diagnostics"]["reason_code"] == reason_code
    assert "failed_required_artifact" in result["freshness_report"]["blocking_reasons"]


@pytest.mark.external
@pytest.mark.skip(
    reason="Phase R-5 dormant: assertion targets the chunk-level "
    "spec_grag_source collection / qdrant_hybrid_retrieve which is "
    "commented out. Rewrite for spec_grag_section to reactivate. See "
    "doc/STORAGE_REDESIGN.ja.md §7.4 R-5."
)
def test_t_r07_real_core_uses_configured_llm_provider_and_real_index(
    tmp_path: Path,
) -> None:
    pytest.importorskip("FlagEmbedding")
    qdrant_client = pytest.importorskip("qdrant_client")

    from spec_grag.core import run_spec_core

    project_root = tmp_path / "real-core-provider"
    collection = f"spec_grag_t_r07_{uuid.uuid4().hex}"
    qdrant_url = os.environ.get("SPEC_GRAG_QDRANT_URL", "http://localhost:6333")
    _write_real_provider_project(
        project_root,
        collection=collection,
        qdrant_url=qdrant_url,
    )
    client = qdrant_client.QdrantClient(qdrant_url)
    try:
        result = run_spec_core(project_root, all=True)

        assert result["status"] == "updated"
        assert result["freshness_report"]["status"] == "fresh"
        metadata = _artifact(project_root, "section_metadata")
        sections = metadata["sections"]
        assert sections
        assert {section["llm_provider"] for section in sections} <= {
            "codex_cli",
            "claude_cli",
        }
        assert all(section["llm_generation_status"] == "success" for section in sections)
        assert all(not section["summary"].startswith("summary:") for section in sections)
        revision = _artifact(project_root, "retrieval_index_revision")
        assert revision["status"] == "success"
        assert revision["diagnostics"]["real_retrieval_index"] is True
        assert client.count(collection).count >= 1
    finally:
        try:
            client.delete_collection(collection)
        except Exception:
            pass


@pytest.mark.skip(
    reason="Phase R-5 dormant: assertion targets the chunk-level "
    "spec_grag_source collection / qdrant_hybrid_retrieve which is "
    "commented out. Rewrite for spec_grag_section to reactivate. See "
    "doc/STORAGE_REDESIGN.ja.md §7.4 R-5."
)
@pytest.mark.external
def test_t_r12_production_core_uses_real_provider_and_retrieval_without_smoke_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("FlagEmbedding")
    qdrant_client = pytest.importorskip("qdrant_client")

    from spec_grag.core import run_spec_core
    from spec_grag.inject import run_spec_inject
    from spec_grag.realign import run_spec_realign
    from spec_grag.retrieval_index import qdrant_hybrid_retrieve

    monkeypatch.delenv("SPEC_GRAG_REAL_PROVIDER", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_RETRIEVAL", raising=False)
    monkeypatch.delenv("SPEC_GRAG_REAL_SMOKE", raising=False)
    monkeypatch.delenv("SPEC_GRAG_LOCAL_SERVICE", raising=False)

    project_root = tmp_path / "production-core-provider"
    collection = f"spec_grag_t_r12_{uuid.uuid4().hex}"
    qdrant_url = os.environ.get("SPEC_GRAG_QDRANT_URL", "http://localhost:6333")
    _write_multi_source_real_provider_project(
        project_root,
        collection=collection,
        qdrant_url=qdrant_url,
    )
    client = qdrant_client.QdrantClient(qdrant_url)
    try:
        result = run_spec_core(project_root, all=True)

        assert result["status"] == "updated"
        assert result["freshness_report"]["status"] == "fresh"
        metadata = _artifact(project_root, "section_metadata")
        sections = metadata["sections"]
        assert len(sections) >= 4
        assert {section["llm_provider"] for section in sections} <= {
            "codex_cli",
            "claude_cli",
        }
        assert all(section["llm_generation_status"] == "success" for section in sections)
        revision = _artifact(project_root, "retrieval_index_revision")
        diagnostics = revision["diagnostics"]
        assert revision["status"] == "success"
        assert diagnostics["real_retrieval_index"] is True
        assert diagnostics["qdrant_url"] == qdrant_url
        assert diagnostics["collection"] == collection
        assert diagnostics["embedding_model"] == "BAAI/bge-m3"
        assert diagnostics["flagembedding_package_version"]
        assert diagnostics["embedding_model_cache_dir"]
        assert "embedding_device" in diagnostics
        assert diagnostics["fusion_method"] == "rrf"
        assert client.count(collection).count >= 1
        retrieval = qdrant_hybrid_retrieve(
            "Qdrant dense sparse retrieval RRF Source Specs",
            url=qdrant_url,
            collection=collection,
            dense_top_k=5,
            sparse_top_k=5,
            limit=5,
        )
        retrieved_sections = {hit.source_section_id for hit in retrieval.hits}
        assert _has_id(retrieved_sections, "docs/spec/search.md#hybrid-retrieval")
        dense_sections = {
            item["source_section_id"]
            for item in retrieval.diagnostics["dense_ranking"]
        }
        sparse_sections = {
            item["source_section_id"]
            for item in retrieval.diagnostics["sparse_ranking"]
        }
        assert _has_id(dense_sections, "docs/spec/search.md#hybrid-retrieval")
        assert _has_id(sparse_sections, "docs/spec/search.md#hybrid-retrieval")

        constraints = [
            {
                "statement": "Authentication must validate active sessions first.",
                "evidence_origin": "Source Specs",
                "evidence_ref": "docs/spec/auth.md#session-validation",
                "support_refs": [
                    {
                        "origin": "Related Sections",
                        "ref": "docs/spec/auth.md#pending-conflict-gate",
                    }
                ],
                "applicability": "Authentication updates.",
                "uncertainty": [],
            }
        ]
        inject_result = run_spec_inject(
            project_root=project_root,
            task_prompt="Update authentication behavior.",
            agent_constraints=constraints,
        )
        assert inject_result["status"] in {"fresh", "ok", "success", "ready"}
        assert inject_result["constraints"]

        realign_result = run_spec_realign(
            project_root=project_root,
            task_prompt="Update authentication behavior.",
            agent_constraints=constraints,
            agent_answer={
                "今回守る制約": ["Authentication must validate active sessions first."],
                "今回扱う修正候補または検討対象": [
                    "Add an active-session validation guard before privileged changes."
                ],
                "競合 / 不確実性 / 人間レビューが必要な点": [],
                "課題プロンプトへの回答または修正案": (
                    "認証処理の前段で active session を検証する。"
                ),
            },
        )
        assert realign_result["status"] in {"fresh", "ok", "success", "ready"}
        realign_text = _json_text(realign_result)
        assert "今回守る制約" in realign_text
        assert "課題プロンプトへの回答または修正案" in realign_text

        pending = {
            "conflict_id": "conflict-production-auth",
            "status": "pending",
            "severity": "high",
            "source_refs": ["docs/spec/auth.md#pending-conflict-gate"],
            "claims": [
                {"side": "a", "summary": "The gate blocks until human decision."},
                {"side": "b", "summary": "The task asks to continue immediately."},
            ],
            "why_conflicting": "Pending human decision is required.",
            "why_llm_cannot_decide": "Only a human can decide the pending conflict.",
            "decision_options": [{"id": "defer", "label": "Defer"}],
            "recommended_next_action": "Ask a human to resolve the conflict.",
        }
        context_dir = project_root / ".spec-grag/context"
        (context_dir / "conflict_review_items.json").write_text(
            json.dumps(
                {"conflict_review_items": [pending]},
                ensure_ascii=False,
                indent=2,
            )
        )
        (context_dir / "freshness.json").write_text(
            json.dumps(
                {
                    "status": "blocked",
                    "blocking_reasons": ["pending_conflict"],
                    "warnings": [],
                    "pending_conflict_count": 1,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        inject_cli = subprocess.run(
            [
                sys.executable,
                "-m",
                "spec_grag",
                "inject",
                "--project-root",
                project_root.as_posix(),
                "--constraints",
                json.dumps(constraints, ensure_ascii=False),
                "Update authentication behavior.",
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        realign_cli = subprocess.run(
            [
                sys.executable,
                "-m",
                "spec_grag",
                "realign",
                "--project-root",
                project_root.as_posix(),
                "--constraints",
                json.dumps(constraints, ensure_ascii=False),
                "--answer-json",
                json.dumps(
                    {
                        "今回守る制約": ["Authentication must validate active sessions first."],
                        "今回扱う修正候補または検討対象": ["Do not continue through pending conflicts."],
                        "競合 / 不確実性 / 人間レビューが必要な点": [],
                        "課題プロンプトへの回答または修正案": "Pending conflict blocks this run.",
                    },
                    ensure_ascii=False,
                ),
                "Update authentication behavior.",
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        assert inject_cli.returncode == 0, inject_cli.stderr or inject_cli.stdout
        assert realign_cli.returncode == 0, realign_cli.stderr or realign_cli.stdout
        for completed in (inject_cli, realign_cli):
            payload = json.loads(completed.stdout)
            assert payload["status"] == "blocked"
            assert payload["should_stop"] is True
            assert payload["can_continue"] is False
            assert payload["constraints"] == []
            assert payload["freshness_report"]["blocking_reasons"] == ["pending_conflict"]
            text = _json_text(payload)
            assert "conflict-production-auth" in text
            assert "why_llm_cannot_decide" in text
            assert "decision_options" in text
    finally:
        try:
            client.delete_collection(collection)
        except Exception:
            pass


def test_g11_warning_only_conflict_resolution_receives_purpose_and_concept_evidence(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    paths["main"].write_text(
        paths["main"].read_text().replace("allows FEATURE_X", "forbids FEATURE_X")
    )
    provider = EvidenceGroundedConflictProvider()

    result = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=provider)
    )

    assert provider.conflict_requests
    assert result["potential_conflicts"]
    assert result["pending_conflict_count"] == 0


def test_g11_resolved_conflict_becomes_stale_when_purpose_or_concept_changes(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    paths = _write_project(project_root)
    paths["main"].write_text(
        paths["main"].read_text().replace("allows FEATURE_X", "forbids FEATURE_X")
    )
    pending = _result_dict(
        _run_spec_core(project_root, all_mode=True, provider=FakeSpecCoreProvider("unresolved"))
    )
    conflict_id = pending["conflict_review_items"][0]["conflict_id"]
    _run_spec_core(
        project_root,
        provider=FakeSpecCoreProvider("resolved"),
        decision_payload={
            "conflict_id": conflict_id,
            "decision": "prefer_a",
            "selected_option": "prefer_a",
            "reason": "Human chose Alpha because the current Core Concept prioritizes sources.",
            "referenced_source_refs": [
                "docs/core/concept.md",
                "docs/spec/main.md#alpha",
            ],
            "human_acknowledgement": True,
        },
    )

    paths["concept"].write_text(
        "# Core Concept\nHuman decisions must be rechecked after principle changes.\n"
    )
    result = _result_dict(
        _run_spec_core(project_root, provider=FakeSpecCoreProvider("resolved"))
    )

    assert result["stale_resolution_count"] >= 1
    assert any(
        item.get("conflict_id") == conflict_id and item.get("stale_resolution") is True
        for item in result["conflict_review_items"]
    )


def test_t_i17_watcher_internal_update_api_is_distinct_from_external_command() -> None:
    module = _core_module()
    external = _required_function(
        module,
        ("run_spec_core", "spec_core", "run_core", "core", "execute_spec_core"),
    )
    internal = _required_function(
        module,
        (
            "run_spec_core_for_watcher",
            "update_spec_core_from_watcher",
            "run_watcher_core_update",
            "apply_watcher_update",
        ),
    )

    assert internal is not external
    assert callable(internal)
