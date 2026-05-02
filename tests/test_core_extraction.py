from __future__ import annotations

import json
from pathlib import Path

from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode, Relation
from llama_index.core.schema import TextNode

from spec_grag.core import run_core_update
from spec_grag.core_extraction import (
    KG_NODES_KEY,
    KG_RELATIONS_KEY,
    extract_schema_llm_artifacts,
    make_schema_extractor_from_config,
)
from spec_grag.extraction import BatchExtractionResponse
from spec_grag.manifest import build_current_section_manifest, load_source_manifest
from spec_grag.concept_diff import (
    ConceptApplyStatus,
    accept_hunk,
    apply_pending_concept_diff,
    load_pending_concept_diff,
    pending_concept_diff_path,
)
from spec_grag.concept_index import refresh_concept_index
from spec_grag.llm_adapters import ClaudeCLIAdapter
from spec_grag.protocol import ResultStatus
from spec_grag.sidecars import load_unresolved_relations


class FakeSchemaExtractor:
    def __init__(
        self,
        payloads: dict[str, tuple[list[EntityNode], list[Relation]] | Exception],
    ) -> None:
        self.payloads = payloads
        self.calls: list[str] = []

    def __call__(
        self, nodes: list[TextNode], show_progress: bool = False, **kwargs
    ) -> list[TextNode]:
        extracted = []
        for node in nodes:
            section_id = node.metadata["current_section_id"]
            self.calls.append(section_id)
            payload = self.payloads.get(section_id, ([], []))
            if isinstance(payload, Exception):
                raise payload
            kg_nodes, kg_relations = payload
            node.metadata[KG_NODES_KEY] = kg_nodes
            node.metadata[KG_RELATIONS_KEY] = kg_relations
            extracted.append(node)
        return extracted


def schema_config() -> dict:
    return {
        "sources": {"include": ["docs/spec/**/*.md"]},
        "core": {
            "purpose_file": "docs/core/purpose.md",
            "concept_file": "docs/core/concept.md",
        },
        "graph": {"storage": ".spec-grag/graph/"},
        "extraction": {"mode": "schema_llm", "provider": "codex"},
    }


def write_concept(project_root: Path, text: str) -> Path:
    path = project_root / "docs/core/concept.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_source(project_root: Path, text: str) -> Path:
    path = project_root / "docs/spec/auth.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def load_graph(project_root: Path) -> dict:
    store = SimplePropertyGraphStore.from_persist_dir(
        str(project_root / ".spec-grag/graph")
    )
    return store.graph.model_dump()


def test_schema_llm_core_path_persists_provenance_and_unresolved_sidecar(
    tmp_path: Path,
) -> None:
    write_source(
        tmp_path,
        "# Auth\n\nOAuth login.\n\n# Billing\n\nPayment state.\n",
    )
    extractor = FakeSchemaExtractor(
        {
            "docs/spec/auth.md#auth": (
                [
                    EntityNode(label="CHAPTER", name="Auth"),
                    EntityNode(label="CHAPTER", name="Billing"),
                    EntityNode(
                        label="ANCHOR",
                        name="OAuth",
                        properties={
                            "description": "OAuth login",
                            "confidence": "high",
                            "evidence_excerpt": "OAuth login.",
                        },
                    ),
                    EntityNode(label="CHAPTER", name="Missing chapter"),
                ],
                [
                    Relation(label="MENTIONS", source_id="Auth", target_id="OAuth"),
                    Relation(
                        label="DEPENDS_ON",
                        source_id="Auth",
                        target_id="Billing",
                        properties={"confidence": "medium"},
                    ),
                    Relation(
                        label="DEPENDS_ON",
                        source_id="Auth",
                        target_id="Missing chapter",
                        properties={
                            "confidence": "medium",
                            "evidence_excerpt": "Depends on future work.",
                        },
                    ),
                    Relation(
                        label="CONTRASTS_WITH",
                        source_id="Auth",
                        target_id="Billing",
                        properties={"confidence": "low"},
                    ),
                ],
            )
        }
    )

    update = run_core_update(
        tmp_path,
        schema_config(),
        all_sources=True,
        schema_extractor=extractor,
    )

    graph = load_graph(tmp_path)
    unresolved = load_unresolved_relations(
        tmp_path / ".spec-grag/graph/unresolved_relations.json"
    )
    manifest = load_source_manifest(tmp_path / ".spec-grag/graph/source_manifest.json")

    anchor_id = "anchor:docs/spec/auth.md#auth:oauth"
    relation_key = "docs/spec/auth.md#auth_DEPENDS_ON_docs/spec/auth.md#billing"
    low_relation_key = "docs/spec/auth.md#auth_CONTRASTS_WITH_docs/spec/auth.md#billing"
    assert update.status == ResultStatus.OK
    assert graph["nodes"][anchor_id]["properties"]["extractor_name"] == "SchemaLLMPathExtractor"
    assert graph["nodes"][anchor_id]["properties"]["source_section_id"] == "docs/spec/auth.md#auth"
    assert (
        graph["nodes"][anchor_id]["properties"]["stable_source_section_uid"]
        == manifest.by_section_id()["docs/spec/auth.md#auth"].stable_section_uid
    )
    assert graph["relations"][relation_key]["properties"]["source_hash"]
    assert graph["relations"][relation_key]["properties"]["stable_source_section_uid"]
    assert graph["relations"][relation_key]["properties"]["stable_source_chunk_uid"]
    assert low_relation_key not in graph["relations"]
    assert any(entry.target_hint == "Missing chapter" for entry in unresolved.entries)
    assert any(entry.reason == "low_confidence" for entry in unresolved.entries)
    assert {entry.source_section_id for entry in unresolved.entries} == {"docs/spec/auth.md#auth"}
    assert "schema_llm_path_extractor" in manifest.entries[0].extractor_versions
    assert "anchor:docs/spec/auth.md#billing:billing" not in graph["nodes"]


def test_schema_llm_incremental_carries_unchanged_artifacts_and_extracts_changed_only(
    tmp_path: Path,
) -> None:
    source = write_source(
        tmp_path,
        "# Auth\n\nOAuth login.\n\n# Billing\n\nPayment state.\n",
    )
    first_extractor = FakeSchemaExtractor(
        {
            "docs/spec/auth.md#auth": (
                [EntityNode(label="ANCHOR", name="OAuth")],
                [Relation(label="MENTIONS", source_id="Auth", target_id="OAuth")],
            ),
            "docs/spec/auth.md#billing": (
                [EntityNode(label="ANCHOR", name="Payment")],
                [Relation(label="MENTIONS", source_id="Billing", target_id="Payment")],
            ),
        }
    )
    run_core_update(
        tmp_path,
        schema_config(),
        all_sources=True,
        schema_extractor=first_extractor,
    )

    source.write_text(
        "# Auth\n\nOAuth login.\n\n# Billing\n\nPayment state is audited.\n",
        encoding="utf-8",
    )
    second_extractor = FakeSchemaExtractor(
        {
            "docs/spec/auth.md#billing": (
                [EntityNode(label="ANCHOR", name="Audit")],
                [Relation(label="MENTIONS", source_id="Billing", target_id="Audit")],
            )
        }
    )
    update = run_core_update(
        tmp_path,
        schema_config(),
        all_sources=False,
        schema_extractor=second_extractor,
    )

    graph = load_graph(tmp_path)

    assert update.status == ResultStatus.OK
    assert second_extractor.calls == ["docs/spec/auth.md#billing"]
    assert "anchor:docs/spec/auth.md#auth:oauth" in graph["nodes"]
    assert "anchor:docs/spec/auth.md#billing:audit" in graph["nodes"]
    assert "anchor:docs/spec/auth.md#billing:payment" not in graph["nodes"]


def test_schema_llm_batch_extraction_groups_sections_and_keeps_source_section_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = write_source(
        tmp_path,
        "# Auth\n\nOverview.\n\n## Login\n\nOAuth login.\n\n## Logout\n\nSession logout.\n",
    )
    manifest = build_current_section_manifest(tmp_path, [source])
    section_ids = [
        "docs/spec/auth.md#auth-login",
        "docs/spec/auth.md#auth-logout",
    ]

    class FakeBatchLLM:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def complete(self, prompt: str, **kwargs):
            self.calls.append(prompt)
            assert kwargs["output_schema"] is BatchExtractionResponse
            return type(
                "Response",
                (),
                {
                    "text": json.dumps(
                        {
                            "triplets": [
                                {
                                    "source_section_id": section_ids[0],
                                    "subject": {
                                        "name": "Login",
                                        "type": "SECTION",
                                        "properties": {
                                            "display_name": "Login",
                                            "description": "Login",
                                            "confidence": "high",
                                            "evidence_excerpt": "OAuth login.",
                                        },
                                    },
                                    "relation": {
                                        "type": "MENTIONS",
                                        "properties": {
                                            "confidence": "high",
                                            "evidence_excerpt": "OAuth login.",
                                            "source_span": "",
                                            "target_hint": "",
                                        },
                                    },
                                    "object": {
                                        "name": "OAuth",
                                        "type": "ANCHOR",
                                        "properties": {
                                            "display_name": "OAuth",
                                            "description": "OAuth login",
                                            "confidence": "high",
                                            "evidence_excerpt": "OAuth login.",
                                        },
                                    },
                                },
                                {
                                    "source_section_id": section_ids[1],
                                    "subject": {
                                        "name": "Logout",
                                        "type": "SECTION",
                                        "properties": {
                                            "display_name": "Logout",
                                            "description": "Logout",
                                            "confidence": "high",
                                            "evidence_excerpt": "Session logout.",
                                        },
                                    },
                                    "relation": {
                                        "type": "MENTIONS",
                                        "properties": {
                                            "confidence": "high",
                                            "evidence_excerpt": "Session logout.",
                                            "source_span": "",
                                            "target_hint": "",
                                        },
                                    },
                                    "object": {
                                        "name": "Session",
                                        "type": "ANCHOR",
                                        "properties": {
                                            "display_name": "Session",
                                            "description": "Session logout",
                                            "confidence": "high",
                                            "evidence_excerpt": "Session logout.",
                                        },
                                    },
                                },
                            ]
                        }
                    )
                },
            )()

    llm = FakeBatchLLM()
    monkeypatch.setattr(
        "spec_grag.core_extraction.make_extraction_llm_from_config",
        lambda config: llm,
    )

    result = extract_schema_llm_artifacts(
        project_root=tmp_path,
        manifest=manifest,
        graph_store=SimplePropertyGraphStore(),
        config={
            "extraction": {
                "mode": "schema_llm",
                "provider": "codex",
                "batch_size": 2,
                "batch_max_chars": 4000,
                "max_triplets_per_chunk": 20,
                "num_workers": 1,
            }
        },
        extract_run_id="run-1",
        extracted_at="2026-05-01T00:00:00+00:00",
        section_ids_to_extract=section_ids,
    )

    graph = result.graph_store.graph.model_dump()
    assert result.failed_section_ids == []
    assert len(llm.calls) == 1
    assert "source_section_id" in llm.calls[0]
    assert graph["nodes"]["anchor:docs/spec/auth.md#auth-login:oauth"]["properties"][
        "source_section_id"
    ] == section_ids[0]
    assert graph["nodes"]["anchor:docs/spec/auth.md#auth-logout:session"]["properties"][
        "source_section_id"
    ] == section_ids[1]


def test_schema_llm_extraction_failure_degrades_and_preserves_retry_manifest(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "# Auth\n\nOAuth login.\n")
    extractor = FakeSchemaExtractor(
        {"docs/spec/auth.md#auth": RuntimeError("adapter unavailable")}
    )

    update = run_core_update(
        tmp_path,
        schema_config(),
        all_sources=True,
        schema_extractor=extractor,
    )
    manifest = load_source_manifest(tmp_path / ".spec-grag/graph/source_manifest.json")

    assert update.status == ResultStatus.DEGRADED
    assert update.failed_sources == ["docs/spec/auth.md#auth"]
    assert "schema_llm_extraction_failed:docs/spec/auth.md#auth" in update.warnings[0]
    assert "docs/spec/auth.md#auth" not in manifest.by_section_id()


def test_schema_llm_unsupported_provider_returns_failed_core_update(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "# Auth\n\nOAuth login.\n")
    config = schema_config()
    config["extraction"]["provider"] = "unknown"

    update = run_core_update(tmp_path, config, all_sources=True)

    assert update.status == ResultStatus.FAILED
    assert update.failed_sources == ["config"]
    assert "unsupported extraction.provider" in update.warnings[0]


def test_schema_llm_claude_provider_uses_same_config_boundary() -> None:
    config = schema_config()
    config["extraction"].update(
        {
            "provider": "claude",
            "command": "claude-dev",
            "model": "sonnet",
            "timeout_sec": 33,
            "max_retries": 2,
            "retry_backoff_sec": 0,
            "max_triplets_per_chunk": 3,
            "num_workers": 1,
        }
    )

    extractor = make_schema_extractor_from_config(config)

    assert isinstance(extractor.llm, ClaudeCLIAdapter)
    assert extractor.llm.command == "claude-dev"
    assert extractor.llm.model == "sonnet"
    assert extractor.llm.timeout_sec == 33
    assert extractor.llm.max_retries == 2
    assert extractor.max_triplets_per_chunk == 3
    assert extractor.num_workers == 1


def test_schema_llm_grounding_scores_compact_and_same_chapter_hints(
    tmp_path: Path,
) -> None:
    write_source(
        tmp_path,
        (
            "# 認証\n\nAuth overview.\n\n"
            "## ログイン\n\nLogin details.\n\n"
            "# 決済\n\nBilling overview.\n\n"
            "## ログイン\n\nBilling login.\n"
        ),
    )
    extractor = FakeSchemaExtractor(
        {
            "docs/spec/auth.md#認証": (
                [
                    EntityNode(label="CHAPTER", name="認証"),
                    EntityNode(label="SECTION", name="認証ログイン"),
                    EntityNode(label="SECTION", name="ログイン"),
                ],
                [
                    Relation(
                        label="DEPENDS_ON",
                        source_id="認証",
                        target_id="認証ログイン",
                        properties={"confidence": "medium"},
                    ),
                    Relation(
                        label="REFINES",
                        source_id="認証",
                        target_id="ログイン",
                        properties={"confidence": "medium"},
                    ),
                ],
            )
        }
    )

    update = run_core_update(
        tmp_path,
        schema_config(),
        all_sources=True,
        schema_extractor=extractor,
    )

    graph = load_graph(tmp_path)
    unresolved = load_unresolved_relations(
        tmp_path / ".spec-grag/graph/unresolved_relations.json"
    )

    compact_relation_key = (
        "docs/spec/auth.md#認証_DEPENDS_ON_section:docs/spec/auth.md#認証-ログイン"
    )
    ambiguous_relation_key = (
        "docs/spec/auth.md#認証_REFINES_section:docs/spec/auth.md#認証-ログイン"
    )
    assert update.status == ResultStatus.OK
    assert compact_relation_key in graph["relations"]
    assert ambiguous_relation_key in graph["relations"]
    relation_props = graph["relations"][ambiguous_relation_key]["properties"]
    assert "same_chapter" in relation_props["target_grounding_methods"]
    assert relation_props["target_grounding_score"] > relation_props[
        "target_grounding_second_score"
    ]
    assert not any(entry.target_hint == "ログイン" for entry in unresolved.entries)


def test_schema_llm_grounding_keeps_same_score_targets_unresolved(
    tmp_path: Path,
) -> None:
    write_source(
        tmp_path,
        (
            "# 認証\n\nAuth overview.\n\n"
            "## ログイン\n\nPrimary login.\n\n"
            "## ログイン\n\nSecondary login.\n"
        ),
    )
    extractor = FakeSchemaExtractor(
        {
            "docs/spec/auth.md#認証": (
                [
                    EntityNode(label="CHAPTER", name="認証"),
                    EntityNode(label="SECTION", name="ログイン"),
                ],
                [
                    Relation(
                        label="DEPENDS_ON",
                        source_id="認証",
                        target_id="ログイン",
                        properties={"confidence": "medium"},
                    ),
                ],
            )
        }
    )

    update = run_core_update(
        tmp_path,
        schema_config(),
        all_sources=True,
        schema_extractor=extractor,
    )

    graph = load_graph(tmp_path)
    unresolved = load_unresolved_relations(
        tmp_path / ".spec-grag/graph/unresolved_relations.json"
    )

    first_relation_key = (
        "docs/spec/auth.md#認証_DEPENDS_ON_section:docs/spec/auth.md#認証-ログイン"
    )
    second_relation_key = (
        "docs/spec/auth.md#認証_DEPENDS_ON_section:docs/spec/auth.md#認証-ログイン-2"
    )
    assert update.status == ResultStatus.OK
    assert first_relation_key not in graph["relations"]
    assert second_relation_key not in graph["relations"]
    assert any(
        entry.target_hint == "ログイン" and entry.reason == "ambiguous_target"
        for entry in unresolved.entries
    )


def test_schema_llm_core_generates_pending_concept_diff_from_new_anchor(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "# Auth\n\n## Login\n\nOAuth 2.0 login.\n")
    concept = write_concept(tmp_path, "# Concept\n\nAuth protects sessions.\n")
    extractor = FakeSchemaExtractor(
        {
            "docs/spec/auth.md#auth-login": (
                [
                    EntityNode(
                        label="ANCHOR",
                        name="OAuth 2.0",
                        properties={
                            "display_name": "OAuth 2.0",
                            "confidence": "high",
                        },
                    )
                ],
                [
                    Relation(
                        label="MENTIONS",
                        source_id="Login",
                        target_id="OAuth 2.0",
                    )
                ],
            )
        }
    )

    update = run_core_update(
        tmp_path,
        schema_config(),
        all_sources=True,
        schema_extractor=extractor,
    )

    assert update.status == ResultStatus.OK
    assert update.pending_concept_diff_id is not None
    assert update.concept_diff is not None
    assert "OAuth 2.0" in update.concept_diff["hunks"][0]["diff_text"]
    assert (
        pending_concept_diff_path(
            tmp_path / ".spec-grag/pending",
            update.pending_concept_diff_id,
        )
        .exists()
    )

    pending = load_pending_concept_diff(
        pending_concept_diff_path(
            tmp_path / ".spec-grag/pending",
            update.pending_concept_diff_id,
        )
    )
    accepted = accept_hunk(pending, "hunk-1")
    result = apply_pending_concept_diff(accepted, concept)
    refreshed, warnings = refresh_concept_index(
        tmp_path,
        schema_config(),
        tmp_path / ".spec-grag/graph",
    )

    assert result.status == ConceptApplyStatus.APPLIED
    assert "OAuth 2.0" in concept.read_text(encoding="utf-8")
    assert warnings == []
    assert refreshed is not None
    assert "OAuth 2.0" in refreshed.chunk_text()
