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
import shutil
import subprocess
import sys
import types
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
            "notes": [],
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


class RelatedSectionsSpecCoreProvider(FakeSpecCoreProvider):
    @property
    def provider_id(self) -> str:
        return "fake-spec-core-related-sections"

    def generate(self, request: Any, *, timeout_sec: int = 5) -> dict[str, Any]:
        self.calls.append(request)
        stage = str(getattr(request, "stage", ""))
        section_hashes = getattr(request, "section_hashes", None)
        if (
            stage == "section_metadata"
            and isinstance(section_hashes, dict)
            and section_hashes
        ):
            return {
                "sections": [
                    {
                        "section_id": str(section_id),
                        "summary": f"summary:{section_id}",
                        "search_keys": ["shared-related-key", f"key:{section_id}"],
                        "identifiers": [],
                        "related_sections": [],
                    }
                    for section_id in section_hashes
                ]
            }
        if stage == "related_section_selection":
            try:
                payload = json.loads(str(getattr(request, "prompt", "{}") or "{}"))
            except json.JSONDecodeError:
                payload = {}
            sections: list[dict[str, Any]] = []
            related_by_source: dict[str, list[dict[str, Any]]] = {}
            for evaluation in payload.get("evaluations", []):
                if not isinstance(evaluation, dict):
                    continue
                source_id = str(evaluation.get("source_section_id") or "")
                candidates = [
                    candidate
                    for candidate in evaluation.get("candidates", [])
                    if isinstance(candidate, dict)
                    and isinstance(candidate.get("target_section_id"), str)
                ]
                related: list[dict[str, Any]] = []
                if source_id and candidates:
                    candidate = candidates[0]
                    related.append(
                        {
                            "target_section_id": candidate["target_section_id"],
                            "relation_hint": "see_also",
                            "confidence": "high",
                            "reason": "shared-related-key links these fixture sections.",
                            "evidence_terms": [],
                            "channels": list(candidate.get("channels") or []),
                            "possible_conflict": False,
                        }
                    )
                if source_id:
                    related_by_source[source_id] = related
                    sections.append(
                        {
                            "source_section_id": source_id,
                            "related_sections": related,
                        }
                    )
            return {"sections": sections, "related_sections": related_by_source}
        return super().generate(request, timeout_sec=timeout_sec)


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
    command = "codex"
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


def _write_cdx006_project(project_root: Path, *, collection: str) -> None:
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

[llm.providers.fake]
command = "fake-noop"
model = "fake-spec-core"
timeout_sec = 5
max_retries = 0

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"
dense_enabled = true
sparse_enabled = true

[vector_store]
provider = "qdrant"
url = "http://fake-qdrant:6333"
collection = "{collection}"

[retrieval]
section_candidate_top_k = 0
section_final_top_n = 8

[limits]
related_selected_max_per_section = 4
"""
    )
    (project_root / "docs/core/purpose.md").write_text("# Purpose\nVerify partial retrieval updates.\n")
    (project_root / "docs/core/concept.md").write_text("# Core Concept\nRelated Sections are retrieval aids.\n")
    (project_root / "docs/spec/sample.md").write_text(
        (REPO_ROOT / "docs/spec/sample.md").read_text()
    )


class _CoreFakePoint:
    def __init__(self, point_id: Any, payload: dict[str, Any] | None = None) -> None:
        self.id = point_id
        self.payload = dict(payload or {})


class _CoreFakePointStruct:
    def __init__(self, *, id: Any, vector: dict[str, Any], payload: dict[str, Any]) -> None:
        self.id = id
        self.vector = dict(vector)
        self.payload = dict(payload)


class _CoreFakePointIdsList:
    def __init__(self, *, points: Any) -> None:
        self.points = list(points)


class _CoreFakeVectorParams:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = dict(kwargs)


class _CoreFakeSparseVectorParams:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = dict(kwargs)


class _CoreFakeSparseVector:
    def __init__(self, *, indices: Any, values: Any) -> None:
        self.indices = list(indices)
        self.values = list(values)


class _CoreFakeMatchValue:
    def __init__(self, *, value: Any) -> None:
        self.value = value


class _CoreFakeFieldCondition:
    def __init__(self, *, key: str, match: Any) -> None:
        self.key = key
        self.match = match


class _CoreFakeFilter:
    def __init__(self, *, must: Any) -> None:
        self.must = list(must)


class _CoreFakeQdrantModels(types.SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(
            PointStruct=_CoreFakePointStruct,
            PointIdsList=_CoreFakePointIdsList,
            VectorParams=_CoreFakeVectorParams,
            SparseVectorParams=_CoreFakeSparseVectorParams,
            SparseVector=_CoreFakeSparseVector,
            Filter=_CoreFakeFilter,
            FieldCondition=_CoreFakeFieldCondition,
            MatchValue=_CoreFakeMatchValue,
            Distance=types.SimpleNamespace(COSINE="cosine"),
        )


class _CoreFakeQdrantClient:
    def __init__(self) -> None:
        self.collection_created = False
        self.point_ids: list[Any] = []
        self.payload_by_point_id: dict[str, dict[str, Any]] = {}
        self.upserted_points: list[Any] = []
        self.deleted_point_ids: list[Any] = []
        self.payload_patches: list[dict[str, Any]] = []

    def info(self) -> dict[str, str]:
        return {"version": "fake-qdrant"}

    def collection_exists(self, *, collection_name: str) -> bool:
        return self.collection_created

    def scroll(
        self,
        *,
        collection_name: str,
        with_payload: bool,
        with_vectors: bool,
        limit: int,
        offset: int | None = None,
    ) -> tuple[list[_CoreFakePoint], int | None]:
        start = int(offset or 0)
        end = start + int(limit)
        points = [
            _CoreFakePoint(
                point_id,
                self.payload_by_point_id.get(str(point_id), {}),
            )
            for point_id in self.point_ids[start:end]
        ]
        next_offset = end if end < len(self.point_ids) else None
        return points, next_offset

    def recreate_collection(self, **kwargs: Any) -> None:
        self.collection_created = True
        self.point_ids = []
        self.payload_by_point_id = {}

    def delete(self, *, collection_name: str, points_selector: Any) -> None:
        points = list(points_selector.points)
        self.deleted_point_ids.extend(points)
        self.point_ids = [point_id for point_id in self.point_ids if point_id not in points]
        for point_id in points:
            self.payload_by_point_id.pop(str(point_id), None)

    def upsert(self, *, collection_name: str, points: Any) -> None:
        self.collection_created = True
        self.upserted_points = list(points)
        by_id = {str(point_id): point_id for point_id in self.point_ids}
        for point in self.upserted_points:
            by_id[str(point.id)] = point.id
            self.payload_by_point_id[str(point.id)] = dict(point.payload)
        self.point_ids = list(by_id.values())

    def set_payload(
        self,
        *,
        collection_name: str,
        payload: dict[str, Any],
        points: Any,
    ) -> None:
        self.payload_patches.append(
            {
                "collection_name": collection_name,
                "payload": dict(payload),
                "points": points,
            }
        )
        source_section_ids: set[str] = set()
        for condition in getattr(points, "must", []):
            if getattr(condition, "key", "") == "source_section_id":
                source_section_ids.add(str(getattr(condition.match, "value", "")))
        if source_section_ids:
            for point_payload in self.payload_by_point_id.values():
                if str(point_payload.get("source_section_id") or "") in source_section_ids:
                    point_payload.update(dict(payload))
            return
        point_ids = points if isinstance(points, list) else []
        for point_id in point_ids:
            existing = self.payload_by_point_id.setdefault(str(point_id), {})
            existing.update(dict(payload))


class _CoreFakeEmbeddingProvider:
    provider_id = "fake-embedding"
    model = "fake-model"
    dense_enabled = True
    sparse_enabled = True

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: Any) -> Any:
        texts = list(texts)
        self.calls.append(texts)
        module = importlib.import_module("spec_grag.retrieval_index")
        return module.BgeM3EmbeddingBatch(
            embeddings=[
                module.BgeM3Embedding(
                    dense=[float(index + 1)],
                    sparse=module.SparseVector(indices=[index + 1], values=[1.0]),
                )
                for index, _text in enumerate(texts)
            ]
        )

    def embed_query(self, text: str) -> Any:
        self.query_calls.append(text)
        module = importlib.import_module("spec_grag.retrieval_index")
        return module.BgeM3Embedding(dense=[1.0], sparse=module.SparseVector())


def _install_core_fake_qdrant(
    monkeypatch: pytest.MonkeyPatch,
    client: _CoreFakeQdrantClient,
) -> None:
    fake_models = _CoreFakeQdrantModels()
    fake_qdrant_client = types.SimpleNamespace(
        QdrantClient=lambda _url: client,
        models=fake_models,
    )
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_qdrant_client)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", fake_models)


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


def _artifact_path(project_root: Path, name: str) -> Path:
    from spec_grag.artifacts import ARTIFACT_FILENAMES, STATE_ARTIFACTS

    filename = ARTIFACT_FILENAMES[name]
    base = ".spec-grag/state" if name in STATE_ARTIFACTS else ".spec-grag/context"
    return project_root / base / filename


def _artifact(project_root: Path, name: str) -> dict[str, Any]:
    path = _artifact_path(project_root, name)
    assert path.is_file(), f"{name} artifact must be written at {path}"
    return json.loads(path.read_text())


def _artifact_texts(project_root: Path) -> dict[str, str]:
    from spec_grag.artifacts import ARTIFACT_FILENAMES

    return {
        name: _artifact_path(project_root, name).read_text()
        for name in ARTIFACT_FILENAMES
        if _artifact_path(project_root, name).is_file()
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


def _sections(result: Any) -> list[dict[str, Any]]:
    data = _result_dict(result)
    diagnostics = data.get("diagnostics") or {}
    metadata = diagnostics.get("section_metadata") or {}
    sections = metadata.get("sections", [])
    assert isinstance(sections, list), "diagnostics.section_metadata.sections must be a list"
    return [dict(section) for section in sections]


def _section_by_id(result: Any, suffix: str) -> dict[str, Any]:
    for section in _sections(result):
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
        "chapter_anchors",
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
    # The first run is incremental on an empty project so it generates every
    # section's LLM cache without later wiping it. The second run is the
    # actual subject of this test: incremental reuse of unchanged sections.
    # Note: using `all_mode=True` here would wipe the section_metadata cache
    # files after generation (the documented `--all` semantic), so the
    # second run would have no reuse source and would re-run every section.
    initial_result = _run_spec_core(project_root, provider=FakeSpecCoreProvider())
    unchanged_before = _section_by_id(initial_result, "#beta")

    paths["main"].write_text(paths["main"].read_text().replace("standard requests", "enterprise requests"))
    result = _run_spec_core(project_root, provider=FakeSpecCoreProvider())
    data = _result_dict(result)
    changed_after = _section_by_id(result, "#alpha")
    unchanged_after = _section_by_id(result, "#beta")

    assert data["mode"] == "incremental"
    updated_sections = _ids(data["updated_sections"])
    assert _has_id(updated_sections, "docs/spec/main.md#alpha")
    assert not _has_id(updated_sections, "docs/spec/main.md#beta")
    assert changed_after["summary"]
    assert unchanged_after["summary"] == unchanged_before["summary"]
    assert unchanged_after["search_keys"] == unchanged_before["search_keys"]


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
        "related_sections_status",
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


def test_b2_incremental_no_change_skips_retrieval_and_related_heavy_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_grag.core_progress import read_progress

    project_root = tmp_path / "project"
    _write_real_provider_project(
        project_root,
        collection="wrong_vector_store_collection",
        qdrant_url="http://localhost:6333",
    )
    config_path = project_root / ".spec-grag/config.toml"
    config_path.write_text(
        config_path.read_text()
        + """\

[retrieval]
dense_top_k = 12
sparse_top_k = 20
rank_fusion = "rrf"
section_collection = "right_retrieval_collection"
section_dense_threshold = 0.55
section_candidate_top_k = 16
section_final_top_n = 8
"""
    )
    core_module = _core_module()
    collection_state = {"exists": True}
    monkeypatch.setattr(
        core_module,
        "_section_collection_exists",
        lambda *_args, **_kwargs: collection_state["exists"],
    )

    upsert_calls: list[dict[str, Any]] = []
    related_calls: list[dict[str, Any]] = []

    def fake_upsert(*args: Any, **kwargs: Any) -> dict[str, Any]:
        upsert_calls.append({"args": args, "kwargs": kwargs})
        return {"status": "success"}

    def fake_related(*args: Any, **kwargs: Any) -> dict[str, Any]:
        related_calls.append({"args": args, "kwargs": kwargs})
        return {
            "related_section_candidates": [],
            "related_sections": {},
            "sections": [],
            "diagnostics": [],
            "generated_at": kwargs.get("generated_at"),
        }

    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "upsert_qdrant_section_collection",
        fake_upsert,
    )
    monkeypatch.setattr(
        core_module.related_sections_api,
        "generate_related_sections_result",
        fake_related,
    )

    first = _result_dict(_run_spec_core(project_root, provider=FakeSpecCoreProvider()))
    second = _result_dict(_run_spec_core(project_root, provider=FakeSpecCoreProvider()))
    collection_state["exists"] = False
    third = _result_dict(_run_spec_core(project_root, provider=FakeSpecCoreProvider()))

    assert first["retrieval_index_status"] == "success"
    assert first["related_sections_status"] == "success"
    assert second["retrieval_index_status"] == "skipped_unchanged"
    assert second["related_sections_status"] == "skipped_unchanged"
    assert third["retrieval_index_status"] == "success"
    assert len(upsert_calls) == 2
    assert upsert_calls[0]["kwargs"]["collection"] == "right_retrieval_collection"
    assert upsert_calls[1]["kwargs"]["recreate"] is True
    assert len(related_calls) == 1
    assert _artifact(project_root, "retrieval_index_state")["collection_name"] == "right_retrieval_collection"
    assert _artifact(project_root, "related_sections_state")["selection_provider"].startswith("fake-spec-core")

    progress = read_progress(project_root)
    assert progress is not None
    assert progress["stages"]["section_collection_upsert"]["action"] == "upserted_full"
    assert progress["stages"]["section_collection_upsert"]["reason"] == "collection_missing"
    assert progress["stages"]["related_sections"]["action"] == "skipped_unchanged"


def test_b3b_core_passes_partial_diff_sets_and_records_stage_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_grag.core_progress import read_progress

    project_root = tmp_path / "project"
    _write_real_provider_project(
        project_root,
        collection="b3b_partial_collection",
        qdrant_url="http://localhost:6333",
    )
    core_module = _core_module()
    monkeypatch.setattr(
        core_module,
        "_section_collection_exists",
        lambda *_args, **_kwargs: True,
    )

    upsert_calls: list[dict[str, Any]] = []

    def fake_upsert(*args: Any, **kwargs: Any) -> dict[str, Any]:
        sections_to_upsert = kwargs.get("sections_to_upsert")
        sections_to_delete = kwargs.get("sections_to_delete")
        upsert_calls.append({"args": args, "kwargs": kwargs})
        return {
            "status": "success",
            "diagnostics": {
                "recreate": bool(kwargs.get("recreate")),
                "sections_upserted_count": len(sections_to_upsert or []),
                "sections_deleted_count": len(sections_to_delete or []),
                "embed_documents_input_size": len(sections_to_upsert or []),
                "stale_points_deleted": len(sections_to_delete or []),
            },
        }

    def fake_related(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "related_section_candidates": [],
            "related_sections": {},
            "sections": [],
            "diagnostics": [],
            "generated_at": kwargs.get("generated_at"),
        }

    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "upsert_qdrant_section_collection",
        fake_upsert,
    )
    monkeypatch.setattr(
        core_module.related_sections_api,
        "generate_related_sections_result",
        fake_related,
    )
    monkeypatch.setattr(
        core_module.related_sections_api,
        "generate_related_sections_partial_result",
        fake_related,
    )

    _run_spec_core(project_root, provider=FakeSpecCoreProvider())
    _run_spec_core(project_root, provider=FakeSpecCoreProvider())
    spec_path = project_root / "docs/spec/main.md"
    spec_path.write_text(
        spec_path.read_text().replace("build a real index.", "build a real index!")
    )
    result = _result_dict(_run_spec_core(project_root, provider=FakeSpecCoreProvider()))

    assert result["retrieval_index_status"] == "success"
    assert len(upsert_calls) == 2
    partial_kwargs = upsert_calls[-1]["kwargs"]
    partial_upsert_ids = {
        section["source_section_id"]
        for section in partial_kwargs["sections_to_upsert"]
    }
    assert partial_upsert_ids == {"docs/spec/main.md#0002-provider-path"}
    assert partial_kwargs["sections_to_delete"] == []
    progress = read_progress(project_root)
    assert progress is not None
    assert progress["stages"]["section_collection_upsert"]["action"] == "upserted_partial"
    diagnostics = progress["stages"]["section_collection_upsert"]["diagnostics"]
    assert diagnostics["sections_upserted_count"] == 1
    assert diagnostics["sections_deleted_count"] == 0
    assert diagnostics["embed_documents_input_size"] == 1
    assert diagnostics["stale_points_deleted"] == 0


def test_cdx006_related_sections_fingerprint_timing_keeps_partial_upsert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """without non-empty related_sections this test cannot detect CDX-002-style timing divergence (FakeLLM hid the bug originally)."""

    from spec_grag.core_progress import read_progress

    project_root = tmp_path / "project"
    _write_cdx006_project(project_root, collection="cdx006_collection")
    core_module = _core_module()
    fake_qdrant = _CoreFakeQdrantClient()
    fake_embedding = _CoreFakeEmbeddingProvider()
    _install_core_fake_qdrant(monkeypatch, fake_qdrant)
    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "FlagEmbeddingBgeM3Provider",
        lambda **_kwargs: fake_embedding,
    )

    _run_spec_core(project_root, provider=RelatedSectionsSpecCoreProvider())
    assert any(
        call["payload"].get("related_sections")
        for call in fake_qdrant.payload_patches
    )

    spec_path = project_root / "docs/spec/sample.md"
    spec_path.write_text(
        spec_path.read_text().replace(
            "Regular users may read and update only resources they own.",
            "Regular users may read and update only resources they own!",
        )
    )
    _run_spec_core(project_root, provider=RelatedSectionsSpecCoreProvider())

    progress = read_progress(project_root)
    assert progress is not None
    diagnostics = progress["stages"]["section_collection_upsert"]["diagnostics"]
    assert diagnostics["sections_upserted_count"] == 1
    assert diagnostics["embed_documents_input_size"] == 1


def test_b7_related_sections_partial_regenerate_source_centric(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_grag.core_progress import read_progress

    project_root = tmp_path / "project"
    _write_cdx006_project(project_root, collection="b7_related_sections_partial_collection")
    spec_path = project_root / "docs/spec/spec.md"
    sample_path = project_root / "docs/spec/sample.md"
    sample_path.unlink()
    shutil.copyfile(REPO_ROOT / "tests/fixtures/spec_50sections/spec.md", spec_path)

    core_module = _core_module()
    fake_qdrant = _CoreFakeQdrantClient()
    fake_embedding = _CoreFakeEmbeddingProvider()
    _install_core_fake_qdrant(monkeypatch, fake_qdrant)
    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "FlagEmbeddingBgeM3Provider",
        lambda **_kwargs: fake_embedding,
    )

    first = _result_dict(
        _run_spec_core(project_root, provider=RelatedSectionsSpecCoreProvider())
    )
    section_02_first = _section_by_id(first, "section-02-billing-ledger")
    first_related = section_02_first.get("related_sections") or []
    assert first_related
    first_targets = {
        str(item.get("target_section_id") or "") for item in first_related
    }
    first_hints = {str(item.get("relation_hint") or "") for item in first_related}

    spec_path.write_text(
        spec_path.read_text().replace("ten minutes", "eleven minutes")
    )
    second = _result_dict(
        _run_spec_core(project_root, provider=RelatedSectionsSpecCoreProvider())
    )

    progress = read_progress(project_root)
    assert progress is not None
    related_stage = progress["stages"]["related_sections"]
    assert related_stage["action"] == "regenerated_partial"
    assert related_stage["batch_count"] == 1
    assert related_stage["llm_calls"] == 1
    assert any(
        str(section_id).endswith("section-01-authentication-window")
        for section_id in related_stage["changed_source_section_ids"]
    )

    related_diagnostics = second["diagnostics"]["related_sections"]["diagnostics"]
    partial_diagnostic = next(
        item
        for item in related_diagnostics
        if item.get("reason_code") == "related_sections_partial_regenerated"
    )
    assert partial_diagnostic["partial_regeneration"] is True
    assert partial_diagnostic["source_centric_partial"] is True
    assert partial_diagnostic["unchanged_source_inheritance"] is True
    assert partial_diagnostic["removed_source_exclusion"] is True
    assert partial_diagnostic["partial_mode"] == "source_changed_only"
    assert partial_diagnostic["changed_target_relations_inherited"] is True
    assert partial_diagnostic["requires_full_regeneration_for_complete_target_recheck"] is True
    assert any(
        str(section_id).endswith("section-01-authentication-window")
        for section_id in partial_diagnostic["changed_source_section_ids"]
    )
    assert any(
        str(section_id).endswith("section-01-authentication-window")
        for section_id in partial_diagnostic["changed_target_section_ids"]
    )

    section_02_second = _section_by_id(second, "section-02-billing-ledger")
    second_related = section_02_second.get("related_sections") or []
    second_targets = {
        str(item.get("target_section_id") or "") for item in second_related
    }
    second_hints = {str(item.get("relation_hint") or "") for item in second_related}
    assert second_targets == first_targets
    assert second_hints == first_hints


def test_b7a_related_sections_candidate_generation_source_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_grag.core_progress import read_progress

    project_root = tmp_path / "project"
    _write_cdx006_project(project_root, collection="b7a_related_sections_partial_collection")
    spec_path = project_root / "docs/spec/spec.md"
    sample_path = project_root / "docs/spec/sample.md"
    sample_path.unlink()
    shutil.copyfile(REPO_ROOT / "tests/fixtures/spec_50sections/spec.md", spec_path)

    core_module = _core_module()
    fake_qdrant = _CoreFakeQdrantClient()
    fake_embedding = _CoreFakeEmbeddingProvider()
    _install_core_fake_qdrant(monkeypatch, fake_qdrant)
    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "FlagEmbeddingBgeM3Provider",
        lambda **_kwargs: fake_embedding,
    )

    first = _result_dict(
        _run_spec_core(project_root, provider=RelatedSectionsSpecCoreProvider())
    )
    section_02_first = _section_by_id(first, "section-02-billing-ledger")
    first_related = section_02_first.get("related_sections") or []
    assert first_related
    first_targets = {
        str(item.get("target_section_id") or "") for item in first_related
    }
    first_hints = {str(item.get("relation_hint") or "") for item in first_related}

    spec_path.write_text(
        spec_path.read_text().replace("ten minutes", "eleven minutes")
    )
    fake_embedding.query_calls.clear()
    second = _result_dict(
        _run_spec_core(project_root, provider=RelatedSectionsSpecCoreProvider())
    )

    progress = read_progress(project_root)
    assert progress is not None
    related_stage = progress["stages"]["related_sections"]
    assert related_stage["action"] == "regenerated_partial"
    assert related_stage["batch_count"] == 1
    assert related_stage["llm_calls"] == 1
    assert related_stage["candidate_generation_partial_mode"] == "source_changed_only"
    assert related_stage["candidate_generation_source_count"] == 1
    assert isinstance(related_stage["candidate_generation_elapsed_sec"], float)
    assert related_stage["candidate_generation_elapsed_sec"] > 0.0
    assert isinstance(related_stage["selection_elapsed_sec"], float)
    assert related_stage["selection_elapsed_sec"] > 0.0
    assert any(
        str(section_id).endswith("section-01-authentication-window")
        for section_id in related_stage["changed_source_section_ids"]
    )
    # 真の partial 化検証: candidate generation の Qdrant hybrid retrieval query
    # (= embed_query 呼び出し) は changed source 1 件分のみ実行されるべき。
    # core.py の固定値ではなく、generate_related_section_candidates_result の
    # 内部 partial 化を実証する assertion。
    assert len(fake_embedding.query_calls) <= 1

    related_diagnostics = second["diagnostics"]["related_sections"]["diagnostics"]
    partial_diagnostic = next(
        item
        for item in related_diagnostics
        if item.get("reason_code") == "related_sections_partial_regenerated"
    )
    assert partial_diagnostic["partial_regeneration"] is True
    assert partial_diagnostic["source_centric_partial"] is True
    assert partial_diagnostic["unchanged_source_inheritance"] is True
    assert partial_diagnostic["removed_source_exclusion"] is True
    assert partial_diagnostic["partial_mode"] == "source_changed_only"
    assert partial_diagnostic["changed_target_relations_inherited"] is True
    assert partial_diagnostic["requires_full_regeneration_for_complete_target_recheck"] is True
    assert partial_diagnostic["candidate_generation_partial_mode"] == "source_changed_only"
    assert partial_diagnostic["candidate_generation_source_count"] == 1
    # 真の partial 化検証: generate_related_section_candidates_result の内部で
    # 生成される `related_section_candidate_generation_scope` diagnostic は
    # core.py や partial_diagnostic の固定値ではなく、`source_records` の絞り
    # 込みを直接反映する。partial mode と source_count=1 がここに出ていれば、
    # candidate generation 内部が source_section_ids を尊重していることの実証。
    candidate_scope_diagnostic = next(
        item
        for item in related_diagnostics
        if item.get("reason_code") == "related_section_candidate_generation_scope"
    )
    assert candidate_scope_diagnostic["candidate_generation_partial_mode"] == "source_changed_only"
    assert candidate_scope_diagnostic["candidate_generation_source_count"] == 1
    assert any(
        str(section_id).endswith("section-01-authentication-window")
        for section_id in partial_diagnostic["changed_source_section_ids"]
    )
    assert any(
        str(section_id).endswith("section-01-authentication-window")
        for section_id in partial_diagnostic["changed_target_section_ids"]
    )

    section_02_second = _section_by_id(second, "section-02-billing-ledger")
    second_related = section_02_second.get("related_sections") or []
    second_targets = {
        str(item.get("target_section_id") or "") for item in second_related
    }
    second_hints = {str(item.get("relation_hint") or "") for item in second_related}
    assert second_targets == first_targets
    assert second_hints == first_hints


def test_b5a_partial_upsert_ignores_source_span_shift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_grag.core_progress import read_progress

    project_root = tmp_path / "project"
    (project_root / ".spec-grag").mkdir(parents=True)
    (project_root / "docs/core").mkdir(parents=True)
    (project_root / "docs/spec").mkdir(parents=True)
    (project_root / ".spec-grag/config.toml").write_text(
        """\
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

[llm.providers.fake]
command = "fake-noop"
model = "fake-spec-core"
timeout_sec = 5
max_retries = 0

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"
dense_enabled = true
sparse_enabled = true

[vector_store]
provider = "qdrant"
url = "http://fake-qdrant:6333"
collection = "b5a_source_span_collection"

[retrieval]
section_candidate_top_k = 0
section_final_top_n = 8
"""
    )
    (project_root / "docs/core/purpose.md").write_text(
        "# Purpose\nVerify source-span-stable partial retrieval updates.\n"
    )
    (project_root / "docs/core/concept.md").write_text(
        "# Core Concept\nSource hashes detect content changes.\n"
    )
    spec_path = project_root / "docs/spec/spec.md"
    shutil.copyfile(REPO_ROOT / "tests/fixtures/spec_50sections/spec.md", spec_path)

    core_module = _core_module()
    fake_qdrant = _CoreFakeQdrantClient()
    fake_embedding = _CoreFakeEmbeddingProvider()
    _install_core_fake_qdrant(monkeypatch, fake_qdrant)
    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "FlagEmbeddingBgeM3Provider",
        lambda **_kwargs: fake_embedding,
    )

    _run_spec_core(project_root, provider=FakeSpecCoreProvider())
    spec_path.write_text(
        spec_path.read_text().replace("ten minutes", "eleven minutes")
    )
    result = _result_dict(_run_spec_core(project_root, provider=FakeSpecCoreProvider()))

    metadata_generation = result["diagnostics"]["section_metadata_generation"]
    generated_section_ids = metadata_generation["generated_section_ids"]
    assert metadata_generation["cache_hits"] == 50
    assert metadata_generation["llm_calls"] == 1
    assert generated_section_ids == [
        "docs/spec/spec.md#0002-section-01-authentication-window"
    ]

    progress = read_progress(project_root)
    assert progress is not None
    assert progress["stages"]["section_collection_upsert"]["action"] == "upserted_partial"
    diagnostics = progress["stages"]["section_collection_upsert"]["diagnostics"]
    assert diagnostics["embed_documents_input_size"] == 1
    assert diagnostics["sections_upserted_count"] == 1
    assert diagnostics["total_section_input_count"] == 51


def test_aud002_retrieval_index_failure_marks_freshness_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    _write_real_provider_project(
        project_root,
        collection="aud002_collection",
        qdrant_url="http://localhost:6333",
    )
    core_module = _core_module()
    monkeypatch.setattr(
        core_module,
        "_section_collection_exists",
        lambda *_args, **_kwargs: True,
    )

    def failing_upsert(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("qdrant upsert failed")

    def fake_related(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "related_section_candidates": [],
            "related_sections": {},
            "sections": [],
            "diagnostics": [],
            "generated_at": kwargs.get("generated_at"),
        }

    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "upsert_qdrant_section_collection",
        failing_upsert,
    )
    monkeypatch.setattr(
        core_module.related_sections_api,
        "generate_related_sections_result",
        fake_related,
    )

    result = _result_dict(_run_spec_core(project_root, provider=FakeSpecCoreProvider()))
    freshness = _freshness(result)

    assert result["retrieval_index_status"] == "failed"
    assert result["related_sections_status"] == "success"
    assert result["status"] == "failed"
    assert freshness["status"] == "failed"
    assert "failed_required_artifact" in freshness.get("blocking_reasons", [])
    assert "retrieval_index" in freshness["diagnostics"]["failed_required_artifacts"]
    assert "Source Retrieval Index update failed" in result["warnings"]


def test_aud007_qdrant_backend_failure_marks_related_sections_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUD-007: Qdrant 設定済みで `QdrantHybridRetriever` 初期化失敗時、
    Related Sections は `status = failed` となり、core の status / freshness が
    failed に降格し、`failed_required_artifacts` に `related_sections` を含む。
    canonical Related Sections (section_metadata の関連先 + Qdrant payload patch)
    は更新されない。
    """
    project_root = tmp_path / "project"
    _write_real_provider_project(
        project_root,
        collection="aud007_collection",
        qdrant_url="http://localhost:6333",
    )

    core_module = _core_module()
    fake_qdrant = _CoreFakeQdrantClient()
    fake_embedding = _CoreFakeEmbeddingProvider()
    _install_core_fake_qdrant(monkeypatch, fake_qdrant)
    monkeypatch.setattr(
        core_module.retrieval_index_api,
        "FlagEmbeddingBgeM3Provider",
        lambda **_kwargs: fake_embedding,
    )

    retrieval_module = importlib.import_module("spec_grag.retrieval_index")
    related_module = importlib.import_module("spec_grag.related_sections")

    class _BrokenQdrantRetriever:
        def __init__(self, *, url: str, collection: str) -> None:
            raise RuntimeError("simulated qdrant connection refused for AUD-007")

    monkeypatch.setattr(
        retrieval_module, "QdrantHybridRetriever", _BrokenQdrantRetriever
    )
    # related_sections.py は import で取り込み済みなので、その module 側も上書きする
    if hasattr(related_module, "QdrantHybridRetriever"):
        monkeypatch.setattr(
            related_module, "QdrantHybridRetriever", _BrokenQdrantRetriever
        )

    patches_before = list(fake_qdrant.payload_patches)

    result = _result_dict(_run_spec_core(project_root, provider=FakeSpecCoreProvider()))
    freshness = _freshness(result)

    assert result["related_sections_status"] == "failed"
    assert result["status"] == "failed"
    assert freshness["status"] == "failed"
    assert "failed_required_artifact" in freshness.get("blocking_reasons", [])
    failed_artifacts = freshness["diagnostics"]["failed_required_artifacts"]
    assert "related_sections" in failed_artifacts

    # diagnostics に Qdrant backend failure descriptor が乗っている
    related_diagnostic = result["diagnostics"]["related_sections"]
    failure = related_diagnostic.get("qdrant_backend_failure")
    assert isinstance(failure, dict), failure
    assert failure["expected_retrieval_backend"] == "qdrant"
    assert failure["actual_retrieval_backend"] == "unavailable"
    assert failure["fallback_attempted"] is False
    assert failure["qdrant_url_configured"] is True
    assert "simulated qdrant connection refused" in failure["failure_reason"]

    # warnings に failure_reason を引用した文字列が含まれる
    assert any(
        "Related Sections retrieval backend failure" in warning
        and "simulated qdrant connection refused" in warning
        for warning in result["warnings"]
    ), result["warnings"]

    # canonical Qdrant payload patch (related_sections field の上書き) が走らない
    new_patches = fake_qdrant.payload_patches[len(patches_before) :]
    related_patches = [
        patch
        for patch in new_patches
        if "related_sections" in patch.get("payload", {})
    ]
    assert related_patches == [], related_patches


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
        if artifact_name == "chapter_anchors":
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

    result = _run_spec_core(project_root, all_mode=True, provider=RelatedSectionsProvider())

    related_entries = [
        related
        for section in _sections(result)
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
    sections = _sections(result)
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
    monkeypatch.delenv("SPEC_GRAG_FAKE_LLM", raising=False)
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
    sections = _sections(result)
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

    monkeypatch.delenv("SPEC_GRAG_FAKE_LLM", raising=False)

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
    sections = _sections(result)
    assert all(section["summary"] == "" for section in sections)
    assert all(section["search_keys"] == [] for section in sections)




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
