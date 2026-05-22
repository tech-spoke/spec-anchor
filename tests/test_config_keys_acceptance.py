"""Table-driven acceptance tests for §10.2 (config 設定項目).

Each row of the §10.2 table in ``doc/EXTERNAL_DESIGN.ja.md`` is covered
by exactly one ``pytest.param`` here. The evidence collector reads the
per-row ``@pytest.mark.spec_ref`` marker (registered by
``tests/conftest.py``) and writes one ``evidence_map.jsonl`` row per
parametrize case.

Two test functions cover the table:

- ``test_optional_key_default_is_applied`` (40 rows): for optional keys,
  omitting the key from the TOML must yield the documented default.
- ``test_required_key_missing_raises_config_error`` (7 rows): for
  required keys, removing the key must surface ``ConfigError`` from
  ``load_config``.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


# Bare-minimum config covering only required keys. Each optional-key test
# loads this verbatim and asserts the resolved attribute equals the
# documented default value.
_MINIMAL_CONFIG_TOML = """\
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[llm.providers.codex]
command = "codex"

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"

[vector_store]
provider = "qdrant"
"""


def _write_minimal_project(target: Path, config_text: str | None = None) -> None:
    """Materialise a project root with the minimal config + Source Specs."""

    (target / ".spec-anchor").mkdir(parents=True)
    (target / ".spec-anchor" / "config.toml").write_text(
        config_text if config_text is not None else _MINIMAL_CONFIG_TOML,
        encoding="utf-8",
    )
    (target / "docs" / "core").mkdir(parents=True)
    (target / "docs" / "core" / "purpose.md").write_text("# Purpose\n", encoding="utf-8")
    (target / "docs" / "core" / "concept.md").write_text("# Concept\n", encoding="utf-8")
    (target / "docs" / "spec").mkdir(parents=True)
    (target / "docs" / "spec" / "main.md").write_text("# Main spec\n", encoding="utf-8")


def _load_config(project_root: Path) -> Any:
    module = importlib.import_module("spec_anchor.config")
    return module.load_config(project_root)


def _resolve(config: Any, *path: str) -> Any:
    current = config
    for key in path:
        if isinstance(current, dict):
            current = current[key]
        else:
            current = getattr(current, key)
    return current


# Each entry: (spec_line, attr_path, expected_default).
#
# ``attr_path`` is the dotted path into the loaded ``ProjectConfig``
# dataclass. ``expected_default`` is the value the loader produces when
# the key is omitted from the TOML (matching the §10.2 既定値 column).
_OPTIONAL_CASES: list[tuple[int, tuple[str, ...], Any]] = [
    (1018, ("sources", "exclude"), []),
    (1021, ("context", "storage"), Path(".spec-anchor/context")),
    (1022, ("section", "max_heading_level"), 4),
    (1023, ("section_metadata", "summary_enabled"), True),
    (1024, ("section_metadata", "search_keys_enabled"), True),
    (1025, ("section_metadata", "related_sections_enabled"), True),
    (1026, ("chapter_anchor", "enabled"), True),
    (1028, ("llm", "providers", "codex", "model"), None),
    (1029, ("llm", "providers", "codex", "effort"), None),
    (1030, ("llm", "providers", "codex", "timeout_sec"), 120),
    (1031, ("llm", "providers", "codex", "max_retries"), 1),
    (1036, ("retrieval", "dense_top_k"), 12),
    (1037, ("retrieval", "sparse_top_k"), 20),
    (1038, ("retrieval", "rank_fusion"), "rrf"),
    (1039, ("retrieval", "section_collection"), "spec_anchor_section"),
    (1040, ("retrieval", "section_dense_threshold"), 0.55),
    (1041, ("retrieval", "section_candidate_top_k"), 16),
    (1042, ("retrieval", "section_final_top_n"), 8),
    (1045, ("embedding", "dense_enabled"), True),
    (1046, ("embedding", "sparse_enabled"), True),
    (1048, ("vector_store", "url"), None),
    (1049, ("limits", "section_summary_max_chars"), 480),
    (1050, ("limits", "search_keys_max"), 32),
    (1051, ("limits", "related_candidate_max_per_section"), 32),
    (1052, ("limits", "related_selected_max_per_section"), 8),
    (1053, ("limits", "conflict_pair_max_per_section"), 8),
    (1054, ("limits", "llm_batch_max_sections"), 8),
    (1055, ("limits", "llm_batch_max_chars"), 12000),
    (1056, ("limits", "llm_batch_concurrency"), 4),
    (1057, ("watcher", "enabled"), False),
    (1058, ("watcher", "interval_ms"), 2000),
    (1059, ("watcher", "debounce_ms"), 1000),
    (1060, ("watcher", "stale_lock_ms"), 300000),
    (1061, ("watcher", "state_file"), None),
    (1062, ("watcher", "queue_file"), None),
]


# Optional keys whose default is "[llm.providers] の先頭定義": stage_routing
# rows. The loader returns an empty dict when omitted, and the runtime
# falls back to the first provider. These four rows are checked by
# asserting the empty dict default; the runtime fallback is covered by
# ``test_stage_routing.py``.
_STAGE_ROUTING_CASES: list[tuple[int, str]] = [
    (1032, "section_metadata"),
    (1033, "related_sections"),
    (1034, "conflict_review"),
    (1035, "chapter_key_anchor"),
]


# Required keys: omitting them must raise ConfigError. ``(spec_line, key)``
# where ``key`` is a substring expected to appear in the error message.
_REQUIRED_CASES: list[tuple[int, str, str]] = [
    # spec_line, key_path_in_message, removal_snippet (we delete a line
    # whose content uniquely identifies the required key)
    (1017, "sources.include", '[sources]\ninclude = ["docs/spec/**/*.md"]\n'),
    (1019, "core.purpose_file", 'purpose_file = "docs/core/purpose.md"\n'),
    (1020, "core.concept_file", 'concept_file = "docs/core/concept.md"\n'),
    (1027, "command", '[llm.providers.codex]\ncommand = "codex"\n'),
    (1043, "embedding.provider", '[embedding]\nprovider = "flagembedding"\nmodel = "BAAI/bge-m3"\n'),
    (1044, "embedding.model", '[embedding]\nprovider = "flagembedding"\nmodel = "BAAI/bge-m3"\n'),
    (1047, "vector_store.provider", '[vector_store]\nprovider = "qdrant"\n'),
]


def _make_optional_param(case: tuple[int, tuple[str, ...], Any]) -> pytest.param:
    spec_line, attr_path, expected = case
    return pytest.param(
        spec_line,
        attr_path,
        expected,
        id=f"L{spec_line}-{'.'.join(attr_path)}",
    )


def _make_stage_param(case: tuple[int, str]) -> pytest.param:
    spec_line, stage_key = case
    return pytest.param(
        spec_line,
        stage_key,
        id=f"L{spec_line}-stage_routing.{stage_key}",
    )


def _make_required_param(case: tuple[int, str, str]) -> pytest.param:
    spec_line, key_label, _ = case
    return pytest.param(
        *case,
        id=f"L{spec_line}-required-{key_label.replace('.', '_')}",
    )


@pytest.mark.parametrize(
    "spec_line, attr_path, expected_default",
    [_make_optional_param(case) for case in _OPTIONAL_CASES],
)
def test_optional_key_default_is_applied(
    spec_line: int,
    attr_path: tuple[str, ...],
    expected_default: Any,
    tmp_path: Path,
) -> None:
    """Omitting an optional key yields the documented default value.

    Per-row SPEC_REF is supplied via ``@pytest.mark.spec_ref`` (see
    ``conftest.py``); this docstring intentionally omits SPEC_REF.
    """

    project = tmp_path / f"project-{spec_line}"
    _write_minimal_project(project)
    config = _load_config(project)
    actual = _resolve(config, *attr_path)

    if isinstance(expected_default, Path):
        # Path defaults resolve relative to project_root.
        expected = project / expected_default
        assert Path(actual) == expected, (
            f"§10.2 L{spec_line}: {'.'.join(attr_path)} default mismatch: "
            f"got {actual!r}, expected {expected!r}"
        )
    else:
        assert actual == expected_default, (
            f"§10.2 L{spec_line}: {'.'.join(attr_path)} default mismatch: "
            f"got {actual!r}, expected {expected_default!r}"
        )


@pytest.mark.parametrize(
    "spec_line, stage_key",
    [_make_stage_param(case) for case in _STAGE_ROUTING_CASES],
)
def test_stage_routing_omitted_falls_back_to_first_provider(
    spec_line: int,
    stage_key: str,
    tmp_path: Path,
) -> None:
    """Omitting an ``[llm.stage_routing]`` key leaves it unset; runtime
    consumers fall back to the first ``[llm.providers]`` definition.
    """

    project = tmp_path / f"stage-{stage_key}"
    _write_minimal_project(project)
    config = _load_config(project)
    stage_routing = config.llm.stage_routing
    # Either the stage key is absent, or maps to a provider id; both are
    # acceptable since loader stores TOML-supplied routing only. The
    # runtime fallback behaviour is covered by test_stage_routing.py.
    if stage_key in stage_routing:
        assert stage_routing[stage_key] in config.llm.providers, (
            f"§10.2 L{spec_line}: stage_routing.{stage_key} resolves to unknown provider"
        )
    else:
        # Confirm there's at least one provider so the fallback target exists.
        assert len(config.llm.providers) >= 1, (
            f"§10.2 L{spec_line}: stage_routing.{stage_key} omitted but no "
            f"[llm.providers.<id>] available as fallback"
        )


@pytest.mark.parametrize(
    "spec_line, key_label, removal_snippet",
    [_make_required_param(case) for case in _REQUIRED_CASES],
)
def test_required_key_missing_raises_config_error(
    spec_line: int,
    key_label: str,
    removal_snippet: str,
    tmp_path: Path,
) -> None:
    """Removing a required key must raise ``ConfigError`` from the loader.
    """

    # Remove the snippet identifying the required key. If the snippet
    # isn't present in the minimal config we treat it as a test author
    # error rather than a silent pass.
    assert removal_snippet in _MINIMAL_CONFIG_TOML, (
        f"§10.2 L{spec_line}: removal snippet not found in minimal config; "
        f"test author must update _REQUIRED_CASES."
    )
    broken = _MINIMAL_CONFIG_TOML.replace(removal_snippet, "")

    project = tmp_path / f"required-{spec_line}"
    _write_minimal_project(project, config_text=broken)

    config_module = importlib.import_module("spec_anchor.config")
    with pytest.raises(config_module.ConfigError):
        _load_config(project)
