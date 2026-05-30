"""Project config loader for lightweight SPEC-anchor."""

from __future__ import annotations

import glob
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


STANDARD_EMBEDDING_PROVIDER = "flagembedding"
STANDARD_EMBEDDING_MODEL = "BAAI/bge-m3"
STANDARD_VECTOR_STORE_PROVIDER = "qdrant"
STANDARD_RANK_FUSION = "rrf"


class ConfigError(Exception):
    """Raised when `.spec-anchor/config.toml` is missing or invalid."""


def _load_project_dotenv(project_root: Path) -> None:
    """Load `<project_root>/.env` into os.environ without overriding existing vars.

    Existing shell / CI env values win (override=False), so `.env` only
    supplies fallbacks for unset variables. Silently no-op if no `.env`
    file exists.
    """

    dotenv_path = project_root / ".env"
    if not dotenv_path.is_file():
        return
    from dotenv import load_dotenv  # imported lazily so tests not touching config skip the cost

    load_dotenv(dotenv_path, override=False)


@dataclass(frozen=True)
class SourcesConfig:
    include: list[str]
    exclude: list[str]
    files: list[Path]


@dataclass(frozen=True)
class CoreConfig:
    purpose_file: Path
    concept_file: Path


@dataclass(frozen=True)
class ContextConfig:
    storage: Path


@dataclass(frozen=True)
class SectionConfig:
    max_heading_level: int = 4


@dataclass(frozen=True)
class SectionMetadataConfig:
    summary_enabled: bool = True
    search_keys_enabled: bool = True
    related_sections_enabled: bool = True


@dataclass(frozen=True)
class ChapterAnchorConfig:
    enabled: bool = True


@dataclass(frozen=True)
class LlmProviderConfig:
    name: str
    command: str
    model: str | None = None
    effort: str | None = None
    timeout_sec: int = 120
    max_retries: int = 1


@dataclass(frozen=True)
class LlmConfig:
    providers: dict[str, LlmProviderConfig]
    # Per-stage provider routing. Maps SPEC-anchor pipeline stages to provider
    # names (keys of `providers`).
    stage_routing: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LimitsConfig:
    section_summary_max_chars: int = 480
    search_keys_max: int = 32
    related_candidate_max_per_section: int = 32
    related_selected_max_per_section: int = 8
    llm_batch_max_sections: int = 8
    llm_batch_max_chars: int = 12000
    llm_batch_concurrency: int = 4


@dataclass(frozen=True)
class RetrievalConfig:
    dense_top_k: int = 12
    sparse_top_k: int = 20
    rank_fusion: str = "rrf"
    section_collection: str = "spec_anchor_section"
    claim_collection: str = "spec_anchor_claim"
    section_dense_threshold: float = 0.55
    section_candidate_top_k: int = 16
    section_final_top_n: int = 8


@dataclass(frozen=True)
class ConflictCandidateDetectionConfig:
    enabled: bool = True
    small_section_all_pairs_threshold: int = 12
    section_pair_top_k: int = 8
    global_pair_cap: int = 80
    min_dense_score: float = 0.55
    allow_same_source_file_pair: bool = True
    allow_same_section_pair: bool = True


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    dense_enabled: bool = True
    sparse_enabled: bool = True


@dataclass(frozen=True)
class VectorStoreConfig:
    provider: str
    url: str | None = None


@dataclass(frozen=True)
class WatcherConfig:
    enabled: bool = False
    interval_ms: int = 2000
    debounce_ms: int = 1000
    stale_lock_ms: int = 300000
    state_file: Path | None = None
    queue_file: Path | None = None


@dataclass(frozen=True)
class ProjectConfig:
    project_root: Path
    config_file: Path
    sources: SourcesConfig
    core: CoreConfig
    context: ContextConfig
    section: SectionConfig
    section_metadata: SectionMetadataConfig
    chapter_anchor: ChapterAnchorConfig
    llm: LlmConfig
    limits: LimitsConfig
    retrieval: RetrievalConfig
    conflict_candidate_detection: ConflictCandidateDetectionConfig
    embedding: EmbeddingConfig
    vector_store: VectorStoreConfig
    watcher: WatcherConfig
    raw: dict[str, Any] = field(repr=False)


def load_config(
    project_root: str | Path,
    *,
    allow_non_standard_providers: bool = False,
) -> ProjectConfig:
    root = Path(project_root).expanduser().resolve()
    _load_project_dotenv(root)
    config_file = root / ".spec-anchor" / "config.toml"
    if not config_file.is_file():
        raise ConfigError(f".spec-anchor/config.toml not found under {root}")

    try:
        raw = tomllib.loads(config_file.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML parse error in .spec-anchor/config.toml: {exc}") from exc

    sources = _load_sources(root, _table(raw, "sources"))
    core = _load_core(root, _table(raw, "core"))
    context = _load_context(root, raw.get("context", {}))
    section = _load_section(raw.get("section", {}))
    section_metadata = _load_section_metadata(raw.get("section_metadata", {}))
    chapter_anchor = _load_chapter_anchor(raw.get("chapter_anchor", {}))
    llm = _load_llm(_table(raw, "llm"))
    limits = _load_limits(raw.get("limits", {}))
    retrieval = _load_retrieval(raw.get("retrieval", {}))
    conflict_candidate_detection = _load_conflict_candidate_detection(
        raw.get("conflict_candidate_detection", {})
    )
    embedding = _load_embedding(
        _table(raw, "embedding"),
        allow_non_standard_providers=allow_non_standard_providers,
    )
    vector_store = _load_vector_store(
        _table(raw, "vector_store"),
        allow_non_standard_providers=allow_non_standard_providers,
    )
    watcher = _load_watcher(root, raw.get("watcher", {}))

    return ProjectConfig(
        project_root=root,
        config_file=config_file,
        sources=sources,
        core=core,
        context=context,
        section=section,
        section_metadata=section_metadata,
        chapter_anchor=chapter_anchor,
        llm=llm,
        limits=limits,
        retrieval=retrieval,
        conflict_candidate_detection=conflict_candidate_detection,
        embedding=embedding,
        vector_store=vector_store,
        watcher=watcher,
        raw=raw,
    )


def _table(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] table is required")
    return value


def _optional_table(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a table")
    return value


def _required_str(table: dict[str, Any], table_name: str, key: str) -> str:
    if key not in table:
        raise ConfigError(f"{table_name}.{key} is required")
    value = table[key]
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{table_name}.{key} must be a non-empty string")
    return value


def _optional_str(table: dict[str, Any], table_name: str, key: str) -> str | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{table_name}.{key} must be a non-empty string")
    return value


def _bool(table: dict[str, Any], table_name: str, key: str, default: bool) -> bool:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{table_name}.{key} must be a boolean")
    return value


def _int(table: dict[str, Any], table_name: str, key: str, default: int) -> int:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{table_name}.{key} must be an integer")
    return value


def _float(table: dict[str, Any], table_name: str, key: str, default: float) -> float:
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{table_name}.{key} must be a number")
    return float(value)


def _relative_path(root: Path, table_name: str, key: str, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    if ".." in path.parts:
        raise ConfigError(f"{table_name}.{key} must not escape project root")
    return root / path


def _load_sources(root: Path, table: dict[str, Any]) -> SourcesConfig:
    include = table.get("include")
    if not isinstance(include, list) or not include:
        raise ConfigError("sources.include must be a non-empty list")
    if not all(isinstance(item, str) and item for item in include):
        raise ConfigError("sources.include must contain non-empty strings")

    exclude = table.get("exclude", [])
    if not isinstance(exclude, list):
        raise ConfigError("sources.exclude must be a list")
    if not all(isinstance(item, str) and item for item in exclude):
        raise ConfigError("sources.exclude must contain non-empty strings")

    matched = _match_sources(root, include, exclude)
    if not matched:
        raise ConfigError("sources.include did not match any Source Specs")
    return SourcesConfig(include=include, exclude=exclude, files=matched)


def _match_sources(root: Path, include: list[str], exclude: list[str]) -> list[Path]:
    included: set[Path] = set()
    for pattern in include:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ConfigError("sources.include must be project-root relative")
        for item in glob.glob(str(root / pattern), recursive=True):
            path = Path(item).resolve()
            if path.is_file() and _inside(root, path):
                included.add(path)

    excluded: set[Path] = set()
    for pattern in exclude:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ConfigError("sources.exclude must be project-root relative")
        for item in glob.glob(str(root / pattern), recursive=True):
            path = Path(item).resolve()
            if path.is_file() and _inside(root, path):
                excluded.add(path)
    return sorted(included - excluded)


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _load_core(root: Path, table: dict[str, Any]) -> CoreConfig:
    purpose_file = _relative_path(
        root,
        "core",
        "purpose_file",
        _required_str(table, "core", "purpose_file"),
    )
    concept_file = _relative_path(
        root,
        "core",
        "concept_file",
        _required_str(table, "core", "concept_file"),
    )
    if not purpose_file.is_file():
        raise ConfigError(f"core.purpose_file not found: {purpose_file}")
    if not concept_file.is_file():
        raise ConfigError(f"core.concept_file not found: {concept_file}")
    return CoreConfig(purpose_file=purpose_file, concept_file=concept_file)


def _load_context(root: Path, raw_value: Any) -> ContextConfig:
    table = _optional_table(raw_value, "context")
    storage = _optional_str(table, "context", "storage") or ".spec-anchor/context"
    return ContextConfig(storage=_relative_path(root, "context", "storage", storage))


def _load_section(raw_value: Any) -> SectionConfig:
    table = _optional_table(raw_value, "section")
    return SectionConfig(max_heading_level=_int(table, "section", "max_heading_level", 4))


def _load_section_metadata(raw_value: Any) -> SectionMetadataConfig:
    table = _optional_table(raw_value, "section_metadata")
    return SectionMetadataConfig(
        summary_enabled=_bool(table, "section_metadata", "summary_enabled", True),
        search_keys_enabled=_bool(table, "section_metadata", "search_keys_enabled", True),
        related_sections_enabled=_bool(
            table,
            "section_metadata",
            "related_sections_enabled",
            True,
        ),
    )


def _load_chapter_anchor(raw_value: Any) -> ChapterAnchorConfig:
    table = _optional_table(raw_value, "chapter_anchor")
    return ChapterAnchorConfig(enabled=_bool(table, "chapter_anchor", "enabled", True))


def _load_llm(table: dict[str, Any]) -> LlmConfig:
    providers_table = table.get("providers")
    if not isinstance(providers_table, dict) or not providers_table:
        raise ConfigError("llm.providers must be a non-empty table")
    providers: dict[str, LlmProviderConfig] = {}
    for name, value in providers_table.items():
        if not isinstance(name, str) or not name:
            raise ConfigError("llm.providers keys must be non-empty strings")
        provider_table = _optional_table(value, f"llm.providers.{name}")
        providers[name] = _load_llm_provider(name, provider_table)
    stage_routing = _load_stage_routing(table.get("stage_routing"), providers)
    return LlmConfig(
        providers=providers,
        stage_routing=stage_routing,
    )


def _load_llm_provider(name: str, table: dict[str, Any]) -> LlmProviderConfig:
    return LlmProviderConfig(
        name=name,
        command=_required_str(table, f"llm.providers.{name}", "command"),
        model=_optional_str(table, f"llm.providers.{name}", "model"),
        effort=_optional_str(table, f"llm.providers.{name}", "effort"),
        timeout_sec=_int(table, f"llm.providers.{name}", "timeout_sec", 120),
        max_retries=_int(table, f"llm.providers.{name}", "max_retries", 1),
    )


_STAGE_ROUTING_ALLOWED_STAGES = frozenset(
    {
        "section_metadata",
        "related_sections",
        "conflict_review",
        "chapter_key_anchor",
    }
)


def _load_stage_routing(
    raw: Any,
    providers: dict[str, LlmProviderConfig],
) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("llm.stage_routing must be a table mapping stage names to provider names")
    routing: dict[str, str] = {}
    for stage, provider_name in raw.items():
        if not isinstance(stage, str) or not stage:
            raise ConfigError("llm.stage_routing keys must be non-empty strings")
        if stage not in _STAGE_ROUTING_ALLOWED_STAGES:
            allowed = ", ".join(sorted(_STAGE_ROUTING_ALLOWED_STAGES))
            raise ConfigError(
                f"llm.stage_routing.{stage} is not an allowed stage. Allowed: {allowed}"
            )
        if not isinstance(provider_name, str) or not provider_name:
            raise ConfigError(
                f"llm.stage_routing.{stage} must be a non-empty provider name string"
            )
        _require_known_llm_provider(provider_name, providers, f"llm.stage_routing.{stage}")
        routing[stage] = provider_name
    return routing


def _require_known_llm_provider(
    provider_name: str,
    providers: dict[str, LlmProviderConfig],
    key: str,
) -> None:
    if provider_name not in providers:
        known = ", ".join(sorted(providers))
        raise ConfigError(f"{key} must reference a configured provider: {known}")


def _load_limits(raw_value: Any) -> LimitsConfig:
    table = _optional_table(raw_value, "limits")
    return LimitsConfig(
        section_summary_max_chars=_int(table, "limits", "section_summary_max_chars", 480),
        search_keys_max=_int(table, "limits", "search_keys_max", 32),
        related_candidate_max_per_section=_int(
            table,
            "limits",
            "related_candidate_max_per_section",
            32,
        ),
        related_selected_max_per_section=_int(
            table,
            "limits",
            "related_selected_max_per_section",
            8,
        ),
        llm_batch_max_sections=_int(table, "limits", "llm_batch_max_sections", 8),
        llm_batch_max_chars=_int(table, "limits", "llm_batch_max_chars", 12000),
        llm_batch_concurrency=max(
            1,
            _int(table, "limits", "llm_batch_concurrency", 4),
        ),
    )


def _load_retrieval(raw_value: Any) -> RetrievalConfig:
    table = _optional_table(raw_value, "retrieval")
    rank_fusion = _optional_str(table, "retrieval", "rank_fusion") or STANDARD_RANK_FUSION
    if rank_fusion != STANDARD_RANK_FUSION:
        raise ConfigError("retrieval.rank_fusion must be rrf")
    return RetrievalConfig(
        dense_top_k=_int(table, "retrieval", "dense_top_k", 12),
        sparse_top_k=_int(table, "retrieval", "sparse_top_k", 20),
        rank_fusion=rank_fusion,
        section_collection=_optional_str(table, "retrieval", "section_collection")
        or "spec_anchor_section",
        claim_collection=_optional_str(table, "retrieval", "claim_collection")
        or "spec_anchor_claim",
        section_dense_threshold=_float(table, "retrieval", "section_dense_threshold", 0.55),
        section_candidate_top_k=_int(table, "retrieval", "section_candidate_top_k", 16),
        section_final_top_n=_int(table, "retrieval", "section_final_top_n", 8),
    )


def _load_conflict_candidate_detection(
    raw_value: Any,
) -> ConflictCandidateDetectionConfig:
    table = _optional_table(raw_value, "conflict_candidate_detection")
    return ConflictCandidateDetectionConfig(
        enabled=_bool(table, "conflict_candidate_detection", "enabled", True),
        small_section_all_pairs_threshold=_int(
            table, "conflict_candidate_detection", "small_section_all_pairs_threshold", 12
        ),
        section_pair_top_k=_int(table, "conflict_candidate_detection", "section_pair_top_k", 8),
        global_pair_cap=_int(table, "conflict_candidate_detection", "global_pair_cap", 80),
        min_dense_score=_float(table, "conflict_candidate_detection", "min_dense_score", 0.55),
        allow_same_source_file_pair=_bool(
            table, "conflict_candidate_detection", "allow_same_source_file_pair", True
        ),
        allow_same_section_pair=_bool(
            table, "conflict_candidate_detection", "allow_same_section_pair", True
        ),
    )


def _load_embedding(
    table: dict[str, Any],
    *,
    allow_non_standard_providers: bool = False,
) -> EmbeddingConfig:
    provider = _required_str(table, "embedding", "provider")
    model = _required_str(table, "embedding", "model")
    if not allow_non_standard_providers and provider != STANDARD_EMBEDDING_PROVIDER:
        raise ConfigError("embedding.provider must be flagembedding")
    if not allow_non_standard_providers and model != STANDARD_EMBEDDING_MODEL:
        raise ConfigError("embedding.model must be BAAI/bge-m3")
    return EmbeddingConfig(
        provider=provider,
        model=model,
        dense_enabled=_bool(table, "embedding", "dense_enabled", True),
        sparse_enabled=_bool(table, "embedding", "sparse_enabled", True),
    )


def _load_vector_store(
    table: dict[str, Any],
    *,
    allow_non_standard_providers: bool = False,
) -> VectorStoreConfig:
    provider = _required_str(table, "vector_store", "provider")
    if not allow_non_standard_providers and provider != STANDARD_VECTOR_STORE_PROVIDER:
        raise ConfigError("vector_store.provider must be qdrant")
    return VectorStoreConfig(
        provider=provider,
        url=_optional_str(table, "vector_store", "url"),
    )


def _load_watcher(root: Path, raw_value: Any) -> WatcherConfig:
    table = _optional_table(raw_value, "watcher")
    state_file = _optional_str(table, "watcher", "state_file")
    queue_file = _optional_str(table, "watcher", "queue_file")
    return WatcherConfig(
        enabled=_bool(table, "watcher", "enabled", False),
        interval_ms=_int(table, "watcher", "interval_ms", 2000),
        debounce_ms=_int(table, "watcher", "debounce_ms", 1000),
        stale_lock_ms=_int(table, "watcher", "stale_lock_ms", 300000),
        state_file=_relative_path(root, "watcher", "state_file", state_file)
        if state_file
        else None,
        queue_file=_relative_path(root, "watcher", "queue_file", queue_file)
        if queue_file
        else None,
    )
