from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from spec_grag.concept_index import (
    ConceptDiffProposal,
    concept_proposal_to_terms,
    generate_concept_diff_proposal_with_llm,
)
from spec_grag.injection import (
    classify_context_item,
    conflict_notes_for,
)
from spec_grag.embedding import EmbeddingMetadata, embedding_for_text
from spec_grag.sidecars import ChapterAnchorsSidecar, load_chapter_anchors


class FakeLLM:
    def __init__(self, payload: dict[str, Any] | str) -> None:
        self.payload = payload
        self.output_schema: Any = None

    def complete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        self.output_schema = kwargs.get("output_schema")
        if isinstance(self.payload, str):
            return SimpleNamespace(text=self.payload)
        return SimpleNamespace(text=json.dumps(self.payload, ensure_ascii=False))


def test_classification_llm_output_is_applied() -> None:
    llm = FakeLLM(
        {
            "constraint_relevance": "high",
            "target_relevance": "medium",
            "semantic_conflict_candidate": False,
            "review_required": False,
            "reason_for_current_task": "LLM classified this as a policy constraint.",
        }
    )

    item = classify_context_item(
        {"summary": "OAuth is required."},
        item_type="concept",
        query="OAuth を見直す",
        llm=llm,
        llm_budget={"remaining": 1},
    )

    assert llm.output_schema is not None
    assert item["classification_source"] == "classification_llm"
    assert item["constraint_relevance"] == "high"
    assert item["reason_for_current_task"] == "LLM classified this as a policy constraint."


def test_classification_invalid_partial_output_falls_back_to_rule_based() -> None:
    item = classify_context_item(
        {"summary": "OAuth is required."},
        item_type="concept",
        query="OAuth を見直す",
        llm=FakeLLM("{not json"),
        llm_budget={"remaining": 1},
    )

    assert item["classification_source"] == "orchestrator_rule_based"
    assert item["classification_partial_output_recovered"] is True
    assert item["review_required"] is True


def test_concept_diff_llm_proposal_keeps_evidence_span() -> None:
    proposal = generate_concept_diff_proposal_with_llm(
        concept_text="# Concept\n",
        source_terms=[
            {
                "term": "OAuth 2.0",
                "source_section_id": "docs/spec/auth.md#auth-login",
                "evidence_excerpt": "OAuth 2.0 login.",
                "source_span": "L4-L6",
            }
        ],
        changed_source_section_ids=["docs/spec/auth.md#auth-login"],
        llm=FakeLLM(
            {
                "items": [
                    {
                        "term": "OAuth 2.0",
                        "source_section_id": "docs/spec/auth.md#auth-login",
                        "evidence_excerpt": "OAuth 2.0 login.",
                        "source_span": "L4-L6",
                        "proposed_text": "OAuth 2.0 login policy",
                    }
                ],
                "warnings": [],
            }
        ),
    )
    terms = concept_proposal_to_terms(
        proposal,
        changed_source_section_ids=["docs/spec/auth.md#auth-login"],
    )

    assert isinstance(proposal, ConceptDiffProposal)
    assert terms == [
        {
            "term": "OAuth 2.0",
            "source_section_id": "docs/spec/auth.md#auth-login",
            "evidence_excerpt": "OAuth 2.0 login.",
            "source_span": "L4-L6",
            "proposed_text": "OAuth 2.0 login policy",
        }
    ]


def test_conflict_validator_rule_pack_detects_bounds_and_permissions() -> None:
    conflicts = conflict_notes_for(
        [],
        [],
        classified_items=[
            {"excerpt": "minimum 5 approvals are required."},
            {"excerpt": "maximum 3 approvals are allowed."},
            {"excerpt": "admin only can export reports."},
            {"excerpt": "all users can export reports."},
        ],
    )

    rule_ids = {item.get("rule_id") for item in conflicts}
    assert "numeric_bounds" in rule_ids
    assert "permission_scope" in rule_ids


def test_corrupt_sidecar_is_quarantined_and_recovered_empty(tmp_path: Path) -> None:
    path = tmp_path / "chapter_anchors.json"
    path.write_text("{not json", encoding="utf-8")

    recovered = load_chapter_anchors(path)

    assert isinstance(recovered, ChapterAnchorsSidecar)
    assert recovered.anchors == []
    assert not path.exists()
    assert list(tmp_path.glob("chapter_anchors.json.corrupt-*"))


def test_ollama_embedding_provider_uses_configured_api(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"embedding":[0.1,0.2,0.3]}'

    captured: dict[str, Any] = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    embedding = embedding_for_text(
        "Auth",
        EmbeddingMetadata(provider="ollama", model="bge-m3", dimension=3),
        config={"timeout_sec": 7, "max_retries": 0},
    )

    assert embedding == [0.1, 0.2, 0.3]
    assert captured["body"] == {"model": "bge-m3", "prompt": "Auth"}
    assert captured["timeout"] == 7
