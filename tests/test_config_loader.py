"""Config Loader contract tests.

These tests pin the lightweight SPEC-grag config contract before the builder
implementation exists.  The loader may return dataclasses or dictionaries; the
assertion helpers below intentionally accept both shapes.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


STANDARD_CONFIG = """\
[sources]
include = ["docs/spec/**/*.md"]
exclude = ["docs/spec/drafts/**"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[context]
storage = ".spec-grag/context"

[section]
max_heading_level = 4

[section_metadata]
summary_enabled = true
search_keys_enabled = true
related_sections_enabled = true

[chapter_anchor]
enabled = true

[llm.providers.codex]
provider = "codex_cli"
command = "codex"
model = "gpt-5.4-mini"
effort = "low"
timeout_sec = 120
max_retries = 1

[llm.providers.claude]
provider = "claude_cli"
command = "claude"
effort = "low"
timeout_sec = 120
max_retries = 1

[limits]
section_summary_max_chars = 480
search_keys_max = 32
related_candidate_max_per_section = 32
related_selected_max_per_section = 8
conflict_pair_max_per_section = 8
llm_batch_max_sections = 8
llm_batch_max_chars = 12000

[retrieval]
chunk_size = 1200
chunk_overlap = 160
dense_top_k = 12
sparse_top_k = 20
rank_fusion = "rrf"

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"
dense_enabled = true
sparse_enabled = true

[vector_store]
provider = "qdrant"
url = "http://localhost:6333"
collection = "spec_grag_source"

[watcher]
enabled = true
interval_ms = 2000
debounce_ms = 1000
stale_lock_ms = 300000
state_file = ".spec-grag/state/watch_state.json"
queue_file = ".spec-grag/state/watch_queue.json"
"""


MINIMAL_CONFIG = """\
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[llm]
provider = "codex_cli"

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"

[vector_store]
provider = "qdrant"
"""


REQUIRED_KEY_CASES = (
    ("sources.include", "[sources]\ninclude = [\"docs/spec/**/*.md\"]\n", "[sources]\n"),
    ("embedding.provider", 'provider = "flagembedding"\nmodel = "BAAI/bge-m3"\n', 'model = "BAAI/bge-m3"\n'),
    ("embedding.model", 'provider = "flagembedding"\nmodel = "BAAI/bge-m3"\n', 'provider = "flagembedding"\n'),
    ("vector_store.provider", '[vector_store]\nprovider = "qdrant"\n', "[vector_store]\n"),
    ("llm.provider", '[llm]\nprovider = "codex_cli"\n', "[llm]\n"),
    ("core.purpose_file", 'purpose_file = "docs/core/purpose.md"\n', ""),
    ("core.concept_file", 'concept_file = "docs/core/concept.md"\n', ""),
)


def _load_config(project_root: Path) -> Any:
    module = importlib.import_module("spec_grag.config")
    load_config = getattr(module, "load_config", None)
    assert callable(load_config), "spec_grag.config.load_config(project_root) is required"
    return load_config(project_root)


def _get(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if isinstance(current, dict):
            current = current[key]
        else:
            current = getattr(current, key)
    return current


def _path(value: Any) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _source_files(config: Any) -> list[Path]:
    sources = _get(config, "sources")
    for name in (
        "files",
        "source_files",
        "resolved_files",
        "resolved_source_files",
        "documents",
    ):
        if isinstance(sources, dict) and name in sources:
            return [_path(path) for path in sources[name]]
        if not isinstance(sources, dict) and hasattr(sources, name):
            return [_path(path) for path in getattr(sources, name)]
    pytest.fail(
        "config.sources must expose matched source files as one of: "
        "files, source_files, resolved_files, resolved_source_files, documents"
    )


def _write_project(project_root: Path, config_text: str = STANDARD_CONFIG) -> None:
    (project_root / ".spec-grag").mkdir(parents=True)
    (project_root / ".spec-grag" / "config.toml").write_text(config_text)
    (project_root / "docs" / "core").mkdir(parents=True)
    (project_root / "docs" / "core" / "purpose.md").write_text("# Purpose\n")
    (project_root / "docs" / "core" / "concept.md").write_text("# Concept\n")
    (project_root / "docs" / "spec").mkdir(parents=True)
    (project_root / "docs" / "spec" / "main.md").write_text("# Main spec\n")


def _assert_config_error(project_root: Path, expected_text: str) -> None:
    with pytest.raises(Exception) as exc_info:
        _load_config(project_root)
    assert expected_text.lower() in str(exc_info.value).lower()


def test_t_u05_standard_config_parses_and_resolves_project_relative_paths(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root)

    config = _load_config(project_root)

    assert _get(config, "sources", "include") == ["docs/spec/**/*.md"]
    assert _get(config, "embedding", "provider") == "flagembedding"
    assert _get(config, "embedding", "model") == "BAAI/bge-m3"
    assert _get(config, "vector_store", "provider") == "qdrant"
    assert _get(config, "llm", "provider") == "codex_cli"
    assert _get(config, "llm", "providers", "codex", "provider") == "codex_cli"
    assert _get(config, "llm", "providers", "claude", "provider") == "claude_cli"

    assert _path(_get(config, "core", "purpose_file")) == project_root / "docs/core/purpose.md"
    assert _path(_get(config, "core", "concept_file")) == project_root / "docs/core/concept.md"
    assert _path(_get(config, "context", "storage")) == project_root / ".spec-grag/context"
    assert project_root / "docs/spec/main.md" in _source_files(config)


@pytest.mark.parametrize(("missing_key", "old", "new"), REQUIRED_KEY_CASES)
def test_t_u05_missing_required_keys_fail(
    tmp_path: Path,
    missing_key: str,
    old: str,
    new: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root, MINIMAL_CONFIG.replace(old, new))

    _assert_config_error(project_root, missing_key)


def test_t_u05_defaults_are_applied_when_optional_tables_are_omitted(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root, MINIMAL_CONFIG)

    config = _load_config(project_root)

    assert _get(config, "section", "max_heading_level") == 4
    assert _path(_get(config, "context", "storage")) == project_root / ".spec-grag/context"
    assert _get(config, "section_metadata", "summary_enabled") is True
    assert _get(config, "section_metadata", "search_keys_enabled") is True
    assert _get(config, "section_metadata", "related_sections_enabled") is True
    assert _get(config, "chapter_anchor", "enabled") is True
    assert _get(config, "watcher", "enabled") is False

    assert _get(config, "limits", "section_summary_max_chars") == 480
    assert _get(config, "limits", "search_keys_max") == 32
    assert _get(config, "limits", "related_candidate_max_per_section") == 32
    assert _get(config, "limits", "related_selected_max_per_section") == 8
    assert _get(config, "limits", "conflict_pair_max_per_section") == 8
    assert _get(config, "limits", "llm_batch_max_sections") == 8
    assert _get(config, "limits", "llm_batch_max_chars") == 12000


def test_t_u05_legacy_single_llm_provider_config_still_parses(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root, MINIMAL_CONFIG)

    config = _load_config(project_root)

    assert _get(config, "llm", "provider") == "codex_cli"
    assert _get(config, "llm", "providers") == {}


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    (
        ('provider = "codex_cli"\ncommand = "codex"\n', 'command = "codex"\n', "llm.providers.codex.provider"),
    ),
)
def test_t_u05_multi_llm_provider_config_rejects_invalid_provider_references(
    tmp_path: Path,
    old: str,
    new: str,
    expected: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root, STANDARD_CONFIG.replace(old, new))

    _assert_config_error(project_root, expected)


def test_t_u06_missing_config_file_fails_without_parent_directory_search(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    _write_project(parent)
    child.mkdir()

    _assert_config_error(child, ".spec-grag/config.toml")


@pytest.mark.parametrize(
    ("mutate", "expected_text"),
    (
        (lambda root: (root / "docs/core/purpose.md").unlink(), "purpose_file"),
        (lambda root: (root / "docs/core/concept.md").unlink(), "concept_file"),
        (lambda root: (root / "docs/spec/main.md").unlink(), "sources.include"),
    ),
)
def test_t_u06_missing_referenced_files_fail(
    tmp_path: Path,
    mutate: Any,
    expected_text: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root, MINIMAL_CONFIG)
    mutate(project_root)

    _assert_config_error(project_root, expected_text)


def test_t_u06_toml_syntax_error_reports_parse_location(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root, "[sources\ninclude = [\n")

    with pytest.raises(Exception) as exc_info:
        _load_config(project_root)

    message = str(exc_info.value).lower()
    assert "toml" in message
    assert "line" in message or "column" in message or ":" in message


@pytest.mark.parametrize(
    ("config_text", "expected_text"),
    (
        (MINIMAL_CONFIG.replace('include = ["docs/spec/**/*.md"]', 'include = "docs/spec/**/*.md"'), "sources.include"),
        (MINIMAL_CONFIG.replace('model = "BAAI/bge-m3"', "model = 123"), "embedding.model"),
        (MINIMAL_CONFIG + "\n[section]\nmax_heading_level = \"4\"\n", "section.max_heading_level"),
    ),
)
def test_t_u06_type_mismatches_fail(
    tmp_path: Path,
    config_text: str,
    expected_text: str,
) -> None:
    project_root = tmp_path / "project"
    _write_project(project_root, config_text)

    _assert_config_error(project_root, expected_text)


def test_t_r01_root_source_does_not_import_archive_old_implementation() -> None:
    source_root = REPO_ROOT / "spec_grag"
    forbidden_fragments = (
        "archive.",
        "archive/",
        "full-grag-2026-05-05",
        "full_grag_2026_05_05",
    )

    for path in source_root.rglob("*.py"):
        source = path.read_text()
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.lstrip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert not any(fragment in line for fragment in forbidden_fragments), (
                f"{path.relative_to(REPO_ROOT)} imports archive implementation: {line}"
            )
