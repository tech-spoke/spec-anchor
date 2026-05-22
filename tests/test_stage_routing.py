"""Phase H-2/H-3: per-stage LLM provider routing.

These tests pin the contract that `[llm.stage_routing]` selects a provider
per pipeline stage so section_metadata, related_sections, conflict_review,
and chapter_key_anchor can target different model / effort tuples without
code changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spec_anchor.config import ConfigError, LlmConfig, LlmProviderConfig, load_config
from spec_anchor.llm_provider import select_llm_provider_config


CONFIG_WITH_ROUTING = """\
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[context]
storage = ".spec-anchor/context"

[section]
max_heading_level = 4

[llm.providers.claude]
command = "claude"
model = "claude-haiku-4-5"
effort = "low"

[llm.providers.claude_judge]
command = "claude"
model = "claude-sonnet-4-6"
effort = "medium"

[llm.providers.claude_typing]
command = "claude"
model = "claude-haiku-4-5"
effort = "medium"

[llm.stage_routing]
section_metadata = "claude"
related_sections = "claude_typing"
conflict_review = "claude_judge"
chapter_key_anchor = "claude"

[retrieval]
dense_top_k = 12
sparse_top_k = 20
rank_fusion = "rrf"

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"

[vector_store]
provider = "qdrant"
url = "http://localhost:6333"
"""


def _write_minimal_project(root: Path) -> None:
    (root / ".spec-anchor").mkdir(parents=True)
    (root / "docs/core").mkdir(parents=True)
    (root / "docs/spec").mkdir(parents=True)
    (root / "docs/core/purpose.md").write_text("# Purpose\n")
    (root / "docs/core/concept.md").write_text("# Concept\n")
    (root / "docs/spec/main.md").write_text("# Spec\nBody.\n")
    (root / ".spec-anchor/config.toml").write_text(CONFIG_WITH_ROUTING)


def test_stage_routing_loaded_into_llm_config(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    project_config = load_config(tmp_path)
    routing = project_config.llm.stage_routing
    assert routing == {
        "section_metadata": "claude",
        "related_sections": "claude_typing",
        "conflict_review": "claude_judge",
        "chapter_key_anchor": "claude",
    }


def test_stage_routing_resolves_to_correct_provider() -> None:
    providers = {
        "claude": LlmProviderConfig(
            name="claude",
            command="claude",
            model="claude-haiku-4-5",
            effort="low",
        ),
        "claude_judge": LlmProviderConfig(
            name="claude_judge",
            command="claude",
            model="claude-sonnet-4-6",
            effort="medium",
        ),
        "claude_typing": LlmProviderConfig(
            name="claude_typing",
            command="claude",
            model="claude-haiku-4-5",
            effort="medium",
        ),
    }
    config = LlmConfig(
        providers=providers,
        stage_routing={
            "section_metadata": "claude",
            "related_sections": "claude_typing",
            "conflict_review": "claude_judge",
            "chapter_key_anchor": "claude",
        },
    )
    metadata_provider = select_llm_provider_config(config, stage="section_metadata")
    related_provider = select_llm_provider_config(config, stage="related_sections")
    conflict_provider = select_llm_provider_config(config, stage="conflict_review")
    chapter_anchor_provider = select_llm_provider_config(config, stage="chapter_key_anchor")
    assert metadata_provider.model == "claude-haiku-4-5"
    assert metadata_provider.effort == "low"
    assert related_provider.model == "claude-haiku-4-5"
    assert related_provider.effort == "medium"
    assert conflict_provider.model == "claude-sonnet-4-6"
    assert conflict_provider.effort == "medium"
    assert chapter_anchor_provider.model == "claude-haiku-4-5"
    assert chapter_anchor_provider.effort == "low"


def test_stage_routing_falls_back_to_first_provider() -> None:
    """Omitted stage_routing falls back to first `[llm.providers]` definition.

    SPEC_REF: §10.2 L1086
    SPEC_REF: §10.2 L1087
    PROFILE: fake
    METHOD: 入出力比較
    """

    providers = {
        "claude": LlmProviderConfig(
            name="claude",
            command="claude",
            model="claude-haiku-4-5",
            effort="low",
        ),
    }
    config = LlmConfig(
        providers=providers,
        stage_routing={},
    )
    selected = select_llm_provider_config(config, stage="section_metadata")
    assert selected.model == "claude-haiku-4-5"


def test_stage_routing_rejects_unknown_stage(tmp_path: Path) -> None:
    """Unrecognised stage keys (e.g., misspelled) raise ConfigError.

    SPEC_REF: §10.2 L1091
    PROFILE: fake
    METHOD: 入出力比較
    """

    bad = CONFIG_WITH_ROUTING.replace(
        "section_metadata = \"claude\"", "unknown_stage = \"claude\"", 1
    )
    _write_minimal_project(tmp_path)
    (tmp_path / ".spec-anchor/config.toml").write_text(bad)
    with pytest.raises(ConfigError, match="not an allowed stage"):
        load_config(tmp_path)


def test_stage_routing_rejects_unknown_provider(tmp_path: Path) -> None:
    """stage_routing referencing an undefined provider id is rejected.

    SPEC_REF: §10.2 L1090
    PROFILE: fake
    METHOD: 入出力比較
    """

    bad = CONFIG_WITH_ROUTING.replace(
        "section_metadata = \"claude\"",
        "section_metadata = \"missing_provider\"",
        1,
    )
    _write_minimal_project(tmp_path)
    (tmp_path / ".spec-anchor/config.toml").write_text(bad)
    with pytest.raises(ConfigError, match="must reference a configured provider"):
        load_config(tmp_path)
