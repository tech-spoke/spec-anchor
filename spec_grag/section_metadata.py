"""Generate Section Metadata retrieval aids.

Section Summary and Section Search Keys produced here are navigation helpers
for retrieval recall. They are deliberately not evidence and must not be used
as final constraint provenance without checking Purpose, Core Concept, or the
Source Specs text.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spec_grag.config import (
    LimitsConfig,
    SectionMetadataConfig,
)
from spec_grag.llm_provider import (
    DEFAULT_METADATA_VERSION,
    FakeLlmProvider,
    LlmGenerationResult,
    LlmProvider,
    LlmRequest,
    build_spec_core_llm_provider,
    generate_with_retries,
    select_llm_provider_config,
)


SECTION_METADATA_PROMPT_VERSION = "section-metadata-v2"
SECTION_METADATA_ROLE = "retrieval_aid_not_evidence"
IDENTIFIER_EXTRACTOR_VERSION = "identifier-extractor-v1"

_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_TABLE_RE = re.compile(r"(?<!\w)\[([A-Za-z_][A-Za-z0-9_.-]*)\]")
_CONFIG_ASSIGN_RE = re.compile(
    r"(?m)^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*=",
)
_DOTTED_NAME_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b",
)
_CALLABLE_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\(\)")
_PASCAL_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b")
_SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_FILE_RE = re.compile(
    r"\b[A-Za-z0-9_.-]+\.(?:json|toml|ya?ml|md|py|txt|lock)\b",
)
_SLASH_COMMAND_RE = re.compile(r"(?<!\w)/[A-Za-z][A-Za-z0-9_-]*\b")
_CLI_COMMAND_RE = re.compile(
    r"\b(?:spec-grag(?:-[A-Za-z0-9_-]+)?|codex|claude)"
    r"(?:\s+[A-Za-z][A-Za-z0-9_-]*)?(?:\s+--[A-Za-z0-9_-]+)?\b",
)
_OPTION_RE = re.compile(r"(?<!\w)--[A-Za-z0-9][A-Za-z0-9_-]*\b")
_UPPER_CODE_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_STATUS_WORDS = {
    "blocked",
    "degraded",
    "dirty",
    "failed",
    "fresh",
    "optional",
    "pending",
    "required",
    "resolved",
    "stale",
    "success",
    "timeout",
}
_WARNING_MARKERS = (
    "blocking",
    "conflict",
    "degraded",
    "diagnostic",
    "error",
    "failed",
    "freshness",
    "invalid",
    "missing",
    "pending",
    "required",
    "stale",
    "timeout",
    "warning",
)
_CAMEL_CASE_RE = re.compile(r"[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*")
_SEARCH_KEY_IDENTIFIER_REGEXES = (
    _DOTTED_NAME_RE,
    _CALLABLE_RE,
    _SLASH_COMMAND_RE,
    _CLI_COMMAND_RE,
    _OPTION_RE,
    _UPPER_CODE_RE,
    _PASCAL_RE,
    _CAMEL_CASE_RE,
    _SNAKE_RE,
    _FILE_RE,
)
_SEARCH_KEYS_INSTRUCTIONS = (
    "search_keys must be NATURAL LANGUAGE keywords for retrieval recall."
    " Output domain concept phrases, chapter themes, synonyms, and the"
    " natural-language side of feature/state/warning names."
    " Do NOT output code symbols, API names, function names, class names,"
    " CLI commands, CLI options (e.g. --rebuild), file paths, ALL_CAPS"
    " constants, PascalCase type names, or dotted technical names."
    " Code symbols are tracked separately under `identifiers` and must not"
    " appear in `search_keys` (the two lists are disjoint by contract)."
    " If a phrase contains an identifier-shaped token, prefer the"
    " natural-language paraphrase (e.g. use 'config replace' instead of"
    " 'productStoreGroup.replace')."
)


def _is_identifier_like_search_key(value: str, identifiers: set[str]) -> bool:
    """Return True when the search_key candidate is a code-shaped token.

    Used to enforce the search_keys (natural language) vs identifiers
    (code symbols) role separation declared in `doc/EXTERNAL_DESIGN.ja.md`
    §2.6 / §2.6.1.
    """

    text = value.strip()
    if not text:
        return True
    if text in identifiers:
        return True
    for regex in _SEARCH_KEY_IDENTIFIER_REGEXES:
        match = regex.fullmatch(text)
        if match is not None:
            return True
    return False


@dataclass(frozen=True)
class SectionMetadataGeneration:
    artifact: dict[str, Any]
    entries: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    llm_results: list[LlmGenerationResult]
    llm_calls: int
    cache_hits: int
    reused_section_ids: list[str]
    generated_section_ids: list[str]
    batch_sizes: list[int]


@dataclass(frozen=True)
class _NormalizedSection:
    section_id: str
    stable_section_uid: str
    source_document_id: str
    heading_path: list[str]
    source_hash: str
    semantic_hash: str
    text: str


@dataclass(frozen=True)
class _WorkItem:
    section: _NormalizedSection
    identifiers: list[str]
    cache_key: str


class SectionMetadataCache:
    """Section-level cache for retrieval-aid metadata.

    The cache key is scoped to the section source hash, prompt version, model,
    provider, metadata version, limits, and generator versions. This lets an
    unchanged section reuse its Summary/Search Keys even when another section
    in the same LLM batch changed.
    """

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)

    def key_for(
        self,
        section: Any,
        *,
        prompt_version: str = SECTION_METADATA_PROMPT_VERSION,
        model: str = "fake",
        provider_id: str = "fake",
        metadata_version: int = DEFAULT_METADATA_VERSION,
        section_metadata_config: Any | None = None,
        limits: Any | None = None,
    ) -> str:
        return section_metadata_cache_key(
            section,
            prompt_version=prompt_version,
            model=model,
            provider_id=provider_id,
            metadata_version=metadata_version,
            section_metadata_config=section_metadata_config,
            limits=limits,
        )

    def load(self, section: Any, cache_key: str) -> dict[str, Any] | None:
        path = self.path_for_key(cache_key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, Mapping):
            return None
        entry = payload.get("entry")
        if not isinstance(entry, Mapping):
            return None
        normalized = _normalize_section(section)
        if not _entry_matches_section(entry, normalized):
            return None
        return dict(entry)

    def store(self, entry: Mapping[str, Any], cache_key: str) -> Path:
        path = self.path_for_key(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_key": cache_key,
            "artifact_role": SECTION_METADATA_ROLE,
            "identifier_extractor_version": IDENTIFIER_EXTRACTOR_VERSION,
            "entry": dict(entry),
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def path_for_key(self, cache_key: str) -> Path:
        return self.cache_dir / "section_metadata" / f"{cache_key}.json"


def generate_section_metadata_result(
    sections: Sequence[Any],
    *,
    config: Any | None = None,
    project_config: Any | None = None,
    provider: LlmProvider | None = None,
    llm_provider: LlmProvider | None = None,
    llm_config: Any | None = None,
    section_metadata_config: Any | None = None,
    limits: Any | None = None,
    previous_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    existing_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    current_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    rebuild_all: bool = False,
    all_sections: bool | None = None,
    force_all: bool | None = None,
    run_all: bool | None = None,
    cache_dir: str | Path | None = None,
    generated_at: str | None = None,
    prompt_version: str = SECTION_METADATA_PROMPT_VERSION,
    metadata_version: int = DEFAULT_METADATA_VERSION,
) -> SectionMetadataGeneration:
    """Generate section metadata payload entries (summary/search_keys/identifiers/related_sections).

    The generated Summary/Search Keys are retrieval aids only, not evidence.
    Unchanged sections are reused by section-level cache key; changed sections
    are grouped into LLM batches bounded by `[limits]`.
    """

    normalized_sections = [_normalize_section(section) for section in sections]
    config = config if config is not None else project_config
    provider = provider if provider is not None else llm_provider
    existing_metadata = _first_not_none(
        existing_metadata,
        previous_metadata,
        current_metadata,
    )
    rebuild = _rebuild_all(
        rebuild_all=rebuild_all,
        all_sections=all_sections,
        force_all=force_all,
        run_all=run_all,
    )
    llm_config = _selected_llm_config(
        llm_config if llm_config is not None else _config_value(config, "llm", None)
    )
    limits = limits if limits is not None else _config_value(config, "limits", None)
    section_metadata_config = (
        section_metadata_config
        if section_metadata_config is not None
        else _config_value(config, "section_metadata", None)
    )
    limits_config = _limits(limits)
    metadata_config = _metadata_config(section_metadata_config)
    provider = _resolve_metadata_provider(provider, llm_config)
    provider_id = str(getattr(provider, "provider_id", provider.__class__.__name__))
    model = _model_name(llm_config, provider_id)
    effort = _config_value(llm_config, "effort", None)
    timeout_sec = int(_config_value(llm_config, "timeout_sec", 120))
    max_retries = int(_config_value(llm_config, "max_retries", 1))
    cache = SectionMetadataCache(cache_dir) if cache_dir is not None else None
    existing_by_section = {} if rebuild else _existing_entries(existing_metadata)

    entries_by_id: dict[str, dict[str, Any]] = {}
    pending: list[_WorkItem] = []
    diagnostics: list[dict[str, Any]] = []
    reused_section_ids: list[str] = []
    generated_section_ids: list[str] = []
    cache_hits = 0

    for section in normalized_sections:
        cache_key = section_metadata_cache_key(
            section,
            prompt_version=prompt_version,
            model=model,
            provider_id=provider_id,
            metadata_version=metadata_version,
            section_metadata_config=metadata_config,
            limits=limits_config,
        )
        cached = cache.load(section, cache_key) if cache is not None and not rebuild else None
        existing = existing_by_section.get(section.section_id)
        reusable = cached or _reusable_existing_entry(
            existing,
            section,
            prompt_version=prompt_version,
            model=model,
            provider_id=provider_id,
            metadata_version=metadata_version,
            metadata_config=metadata_config,
            limits_config=limits_config,
        )
        if reusable is not None:
            entries_by_id[section.section_id] = dict(reusable)
            reused_section_ids.append(section.section_id)
            cache_hits += 1
            continue
        pending.append(
            _WorkItem(
                section=section,
                identifiers=extract_identifiers(section),
                cache_key=cache_key,
            )
        )

    llm_results: list[LlmGenerationResult] = []
    batch_sizes: list[int] = []
    should_call_llm = metadata_config.summary_enabled or metadata_config.search_keys_enabled

    if should_call_llm:
        batches = list(_batch_work_items(pending, limits_config))
        for batch in batches:
            batch_sizes.append(len(batch))

        def _run_metadata_batch(batch: Sequence[Any]) -> Any:
            request = _build_batch_request(
                batch,
                prompt_version=prompt_version,
                model=model,
                effort=effort,
                metadata_version=metadata_version,
                limits=limits_config,
                metadata_config=metadata_config,
            )
            result = generate_with_retries(
                provider,
                request,
                required_fields=(),
                field_schema={"sections": "list[object]"},
                timeout_sec=timeout_sec,
                max_retries=max_retries,
            )
            return batch, request, result

        concurrency = max(1, int(getattr(limits_config, "llm_batch_concurrency", 4) or 4))
        if concurrency > 1 and len(batches) > 1:
            with ThreadPoolExecutor(max_workers=concurrency) as ex:
                batch_outputs = list(ex.map(_run_metadata_batch, batches))
        else:
            batch_outputs = [_run_metadata_batch(batch) for batch in batches]

        for batch, request, result in batch_outputs:
            llm_results.append(result)
            output = result.artifact.output if result.artifact is not None else {}
            output_by_section = _output_by_section(output, batch)
            if not output_by_section:
                diagnostics.append(
                    _diagnostic(
                        "validation_error",
                        "section_metadata LLM output did not contain sections, summary, or search_keys",
                        batch,
                        request,
                    )
                )
            for item in batch:
                generated_section_ids.append(item.section.section_id)
                entry = _entry_from_llm_output(
                    item,
                    output_by_section.get(item.section.section_id, {}),
                    metadata_version=metadata_version,
                    generated_at=generated_at,
                    metadata_config=metadata_config,
                    limits=limits_config,
                    provider_succeeded=result.status == "success" and bool(output_by_section),
                )
                entries_by_id[item.section.section_id] = entry
                if cache is not None and result.status == "success" and bool(output_by_section):
                    cache.store(entry, item.cache_key)
            for diagnostic in result.diagnostic_items or []:
                diagnostics.append(dict(diagnostic))
    else:
        for item in pending:
            generated_section_ids.append(item.section.section_id)
            entry = _entry_from_llm_output(
                item,
                {},
                metadata_version=metadata_version,
                generated_at=generated_at,
                metadata_config=metadata_config,
                limits=limits_config,
                provider_succeeded=True,
            )
            entries_by_id[item.section.section_id] = entry
            if cache is not None:
                cache.store(entry, item.cache_key)

    entries = [entries_by_id[section.section_id] for section in normalized_sections]
    artifact = {
        "artifact_role": SECTION_METADATA_ROLE,
        "summary_search_keys_are_evidence": False,
        "generation": {
            "stage": "section_metadata",
            "prompt_version": prompt_version,
            "model": model,
            "provider": provider_id,
            "metadata_version": metadata_version,
            "identifier_extractor_version": IDENTIFIER_EXTRACTOR_VERSION,
            "enabled_fields": {
                "summary": metadata_config.summary_enabled,
                "search_keys": metadata_config.search_keys_enabled,
                "related_sections": metadata_config.related_sections_enabled,
            },
            "limits": {
                "section_summary_max_chars": limits_config.section_summary_max_chars,
                "search_keys_max": limits_config.search_keys_max,
                "llm_batch_max_sections": limits_config.llm_batch_max_sections,
                "llm_batch_max_chars": limits_config.llm_batch_max_chars,
            },
            "cache_key_inputs": [
                "stable_section_uid",
                "source_hash",
                "prompt_version",
                "model",
                "provider",
                "metadata_version",
                "limits",
                "enabled_fields",
            ],
        },
        "diagnostics": diagnostics,
        "sections": entries,
    }
    return SectionMetadataGeneration(
        artifact=artifact,
        entries=entries,
        diagnostics=diagnostics,
        llm_results=llm_results,
        llm_calls=len(llm_results),
        cache_hits=cache_hits,
        reused_section_ids=reused_section_ids,
        generated_section_ids=generated_section_ids,
        batch_sizes=batch_sizes,
    )


def generate_section_metadata(
    sections: Sequence[Any],
    *,
    config: Any | None = None,
    project_config: Any | None = None,
    provider: LlmProvider | None = None,
    llm_provider: LlmProvider | None = None,
    llm_config: Any | None = None,
    section_metadata_config: Any | None = None,
    limits: Any | None = None,
    previous_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    existing_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    current_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    rebuild_all: bool = False,
    all_sections: bool | None = None,
    force_all: bool | None = None,
    run_all: bool | None = None,
    cache_dir: str | Path | None = None,
    generated_at: str | None = None,
    prompt_version: str = SECTION_METADATA_PROMPT_VERSION,
    metadata_version: int = DEFAULT_METADATA_VERSION,
) -> dict[str, Any]:
    """Return a section metadata payload (summary/search_keys/identifiers/related_sections) for retrieval aids, not evidence."""

    return generate_section_metadata_result(
        sections,
        config=config,
        project_config=project_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_config=llm_config,
        section_metadata_config=section_metadata_config,
        limits=limits,
        previous_metadata=previous_metadata,
        existing_metadata=existing_metadata,
        current_metadata=current_metadata,
        rebuild_all=rebuild_all,
        all_sections=all_sections,
        force_all=force_all,
        run_all=run_all,
        cache_dir=cache_dir,
        generated_at=generated_at,
        prompt_version=prompt_version,
        metadata_version=metadata_version,
    ).artifact


def build_section_metadata(
    sections: Sequence[Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Return a section metadata payload (summary/search_keys/identifiers/related_sections) of retrieval aids, not evidence."""

    return generate_section_metadata(sections, **kwargs)


def extract_identifiers(section: Any) -> list[str]:
    normalized = _normalize_section(section)
    text = "\n".join([*normalized.heading_path, normalized.text])
    identifiers: list[str] = []
    for regex in (
        _CODE_SPAN_RE,
        _TABLE_RE,
        _CONFIG_ASSIGN_RE,
        _DOTTED_NAME_RE,
        _CALLABLE_RE,
        _FILE_RE,
        _SLASH_COMMAND_RE,
        _CLI_COMMAND_RE,
        _OPTION_RE,
        _UPPER_CODE_RE,
        _PASCAL_RE,
    ):
        for match in regex.finditer(text):
            _append_identifier(identifiers, match.group(1) if regex.groups else match.group(0))

    for match in _SNAKE_RE.finditer(text):
        token = match.group(0)
        if token in _STATUS_WORDS or any(marker in token for marker in _WARNING_MARKERS):
            _append_identifier(identifiers, token)

    for word in _STATUS_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", text):
            _append_identifier(identifiers, word)
    return identifiers[:64]


def section_metadata_cache_key(
    section: Any,
    *,
    prompt_version: str = SECTION_METADATA_PROMPT_VERSION,
    model: str = "fake",
    provider_id: str = "fake",
    metadata_version: int = DEFAULT_METADATA_VERSION,
    section_metadata_config: Any | None = None,
    limits: Any | None = None,
) -> str:
    normalized = _normalize_section(section)
    metadata_config = _metadata_config(section_metadata_config)
    limits_config = _limits(limits)
    payload = {
        "stable_section_uid": normalized.stable_section_uid,
        "semantic_hash": normalized.semantic_hash,
        "prompt_version": prompt_version,
        "model": model,
        "provider": provider_id,
        "metadata_version": metadata_version,
        "identifier_extractor_version": IDENTIFIER_EXTRACTOR_VERSION,
        "summary_enabled": metadata_config.summary_enabled,
        "search_keys_enabled": metadata_config.search_keys_enabled,
        "related_sections_enabled": metadata_config.related_sections_enabled,
        "section_summary_max_chars": limits_config.section_summary_max_chars,
        "search_keys_max": limits_config.search_keys_max,
        "llm_batch_max_sections": limits_config.llm_batch_max_sections,
        "llm_batch_max_chars": limits_config.llm_batch_max_chars,
    }
    return _sha256_text(_stable_json(payload))


def _normalize_section(section: Any) -> _NormalizedSection:
    text = str(_section_value(section, "text", ""))
    section_id = str(_section_value(section, "section_id", ""))
    if not section_id:
        section_id = _sha256_text(text)[:16]
    stable_section_uid = str(
        _section_value(section, "stable_section_uid", section_id),
    )
    source_document_id = str(
        _section_value(section, "source_document_id", ""),
    )
    heading_path = _list_of_strings(_section_value(section, "heading_path", []))
    source_hash = str(_section_value(section, "source_hash", _sha256_text(text)))
    semantic_hash = str(_section_value(section, "semantic_hash", source_hash))
    return _NormalizedSection(
        section_id=section_id,
        stable_section_uid=stable_section_uid,
        source_document_id=source_document_id,
        heading_path=heading_path,
        source_hash=source_hash,
        semantic_hash=semantic_hash,
        text=text,
    )


def _section_value(section: Any, key: str, default: Any) -> Any:
    if isinstance(section, Mapping):
        return section.get(key, default)
    return getattr(section, key, default)


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value]


def _limits(value: Any | None) -> LimitsConfig:
    if isinstance(value, LimitsConfig):
        return value
    if value is None:
        return LimitsConfig()
    return LimitsConfig(
        section_summary_max_chars=max(
            0,
            int(_config_value(value, "section_summary_max_chars", 480)),
        ),
        search_keys_max=max(0, int(_config_value(value, "search_keys_max", 32))),
        related_candidate_max_per_section=max(
            0,
            int(_config_value(value, "related_candidate_max_per_section", 32)),
        ),
        related_selected_max_per_section=max(
            0,
            int(_config_value(value, "related_selected_max_per_section", 8)),
        ),
        conflict_pair_max_per_section=max(
            0,
            int(_config_value(value, "conflict_pair_max_per_section", 8)),
        ),
        llm_batch_max_sections=max(
            1,
            int(_config_value(value, "llm_batch_max_sections", 8)),
        ),
        llm_batch_max_chars=max(1, int(_config_value(value, "llm_batch_max_chars", 12000))),
        llm_batch_concurrency=max(
            1,
            int(_config_value(value, "llm_batch_concurrency", 4)),
        ),
    )


def _metadata_config(value: Any | None) -> SectionMetadataConfig:
    if isinstance(value, SectionMetadataConfig):
        return value
    if value is None:
        return SectionMetadataConfig()
    return SectionMetadataConfig(
        summary_enabled=bool(_config_value(value, "summary_enabled", True)),
        search_keys_enabled=bool(_config_value(value, "search_keys_enabled", True)),
        related_sections_enabled=bool(
            _config_value(value, "related_sections_enabled", True),
        ),
    )


def _config_value(config: Any, key: str, default: Any) -> Any:
    if config is None:
        return default
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _resolve_metadata_provider(
    provider: LlmProvider | None,
    llm_config: Any | None,
) -> LlmProvider:
    if provider is not None:
        return provider
    if llm_config is None:
        return FakeLlmProvider()
    return build_spec_core_llm_provider(llm_config)


def _selected_llm_config(llm_config: Any | None) -> Any | None:
    if _config_value(llm_config, "providers", None):
        return select_llm_provider_config(llm_config)
    return llm_config


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _rebuild_all(
    *,
    rebuild_all: bool,
    all_sections: bool | None,
    force_all: bool | None,
    run_all: bool | None,
) -> bool:
    for value in (all_sections, force_all, run_all):
        if value is not None:
            return bool(value)
    return bool(rebuild_all)


def _model_name(llm_config: Any, provider_id: str) -> str:
    model = _config_value(llm_config, "model", None)
    if isinstance(model, str) and model:
        return model
    return provider_id or "fake"


def _existing_entries(
    existing_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if existing_metadata is None:
        return {}
    generation: Any = None
    sections = (
        existing_metadata.get("sections", [])
        if isinstance(existing_metadata, Mapping)
        else existing_metadata
    )
    if isinstance(existing_metadata, Mapping):
        generation = existing_metadata.get("generation")
    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for item in sections:
        if not isinstance(item, Mapping):
            continue
        section_id = item.get("section_id")
        if isinstance(section_id, str) and section_id:
            entry = dict(item)
            if isinstance(generation, Mapping):
                entry["_artifact_generation"] = dict(generation)
            entries[section_id] = entry
    return entries


def _reusable_existing_entry(
    entry: Mapping[str, Any] | None,
    section: _NormalizedSection,
    *,
    prompt_version: str,
    model: str,
    provider_id: str,
    metadata_version: int,
    metadata_config: SectionMetadataConfig,
    limits_config: LimitsConfig,
) -> dict[str, Any] | None:
    if entry is None or not _entry_matches_section(entry, section):
        return None
    if entry.get("metadata_version") != metadata_version:
        return None
    if not isinstance(entry.get("summary"), str):
        return None
    if not isinstance(entry.get("search_keys"), list):
        return None
    if not isinstance(entry.get("identifiers"), list):
        return None
    if (
        metadata_config.summary_enabled
        and limits_config.section_summary_max_chars > 0
        and entry.get("summary") == ""
    ):
        return None
    if (
        metadata_config.search_keys_enabled
        and limits_config.search_keys_max > 0
        and not entry.get("search_keys")
    ):
        return None
    generation = entry.get("_artifact_generation")
    if not isinstance(generation, Mapping):
        return None
    expected = {
        "prompt_version": prompt_version,
        "model": model,
        "provider": provider_id,
        "metadata_version": metadata_version,
        "identifier_extractor_version": IDENTIFIER_EXTRACTOR_VERSION,
    }
    if any(generation.get(key) != value for key, value in expected.items()):
        return None
    enabled_fields = generation.get("enabled_fields")
    if not isinstance(enabled_fields, Mapping):
        return None
    if enabled_fields.get("summary") != metadata_config.summary_enabled:
        return None
    if enabled_fields.get("search_keys") != metadata_config.search_keys_enabled:
        return None
    if enabled_fields.get("related_sections") != metadata_config.related_sections_enabled:
        return None
    limit_values = generation.get("limits")
    if not isinstance(limit_values, Mapping):
        return None
    if limit_values.get("section_summary_max_chars") != limits_config.section_summary_max_chars:
        return None
    if limit_values.get("search_keys_max") != limits_config.search_keys_max:
        return None
    if limit_values.get("llm_batch_max_sections") != limits_config.llm_batch_max_sections:
        return None
    if limit_values.get("llm_batch_max_chars") != limits_config.llm_batch_max_chars:
        return None
    return _public_entry(dict(entry))


def _entry_matches_section(entry: Mapping[str, Any], section: _NormalizedSection) -> bool:
    return (
        entry.get("section_id") == section.section_id
        and entry.get("stable_section_uid") == section.stable_section_uid
        and entry.get("semantic_hash") == section.semantic_hash
    )


def _batch_work_items(
    pending: Sequence[_WorkItem],
    limits: LimitsConfig,
) -> list[list[_WorkItem]]:
    batches: list[list[_WorkItem]] = []
    current: list[_WorkItem] = []
    current_chars = 0
    max_sections = max(1, limits.llm_batch_max_sections)
    max_chars = max(1, limits.llm_batch_max_chars)
    for item in pending:
        item_chars = _work_item_char_cost(item)
        if current and (
            len(current) >= max_sections or current_chars + item_chars > max_chars
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item_chars
    if current:
        batches.append(current)
    return batches


def _work_item_char_cost(item: _WorkItem) -> int:
    return (
        len(item.section.text)
        + len("\n".join(item.section.heading_path))
        + len(item.section.section_id)
        + 160
    )


def _build_batch_request(
    batch: Sequence[_WorkItem],
    *,
    prompt_version: str,
    model: str,
    effort: str | None,
    metadata_version: int,
    limits: LimitsConfig,
    metadata_config: SectionMetadataConfig,
) -> LlmRequest:
    prompt = _build_batch_prompt(batch, limits=limits, metadata_config=metadata_config)
    source_hash = _sha256_text(
        _stable_json(
            {
                "role": SECTION_METADATA_ROLE,
                "prompt_version": prompt_version,
                "sections": [
                    [item.section.section_id, item.section.source_hash]
                    for item in batch
                ],
            },
        ),
    )
    semantic_hash = _sha256_text(
        _stable_json(
            {
                "sections": [
                    [item.section.section_id, item.section.semantic_hash]
                    for item in batch
                ],
            },
        ),
    )
    return LlmRequest(
        task="section_metadata",
        stage="section_metadata",
        prompt=prompt,
        prompt_version=prompt_version,
        model=model,
        source_hash=source_hash,
        semantic_hash=semantic_hash,
        metadata_version=metadata_version,
        effort=effort,
        section_hashes={
            item.section.section_id: item.section.source_hash for item in batch
        },
        input_hashes={
            item.section.section_id: item.cache_key for item in batch
        },
        context_hashes={
            "artifact_role": _sha256_text(SECTION_METADATA_ROLE),
            "identifier_extractor_version": _sha256_text(
                IDENTIFIER_EXTRACTOR_VERSION,
            ),
        },
    )


def _build_batch_prompt(
    batch: Sequence[_WorkItem],
    *,
    limits: LimitsConfig,
    metadata_config: SectionMetadataConfig,
) -> str:
    max_chars = max(1, limits.llm_batch_max_chars)
    text_limit = _initial_text_limit(batch, limits, metadata_config)
    while True:
        payload = _batch_prompt_payload(
            batch,
            limits=limits,
            metadata_config=metadata_config,
            text_limit=text_limit,
        )
        prompt = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(prompt) <= max_chars:
            return prompt
        if text_limit <= 0:
            minimal = _minimal_batch_prompt(batch, max_chars)
            if len(minimal) <= max_chars:
                return minimal
            return minimal[:max_chars]
        overflow = len(prompt) - max_chars
        text_limit = max(0, text_limit - (overflow // max(1, len(batch)) + 1))


def _initial_text_limit(
    batch: Sequence[_WorkItem],
    limits: LimitsConfig,
    metadata_config: SectionMetadataConfig,
) -> int:
    empty_payload = _batch_prompt_payload(
        batch,
        limits=limits,
        metadata_config=metadata_config,
        text_limit=0,
    )
    base_len = len(
        json.dumps(
            empty_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    available = max(0, limits.llm_batch_max_chars - base_len)
    if not batch:
        return 0
    return max(0, available // len(batch))


def _batch_prompt_payload(
    batch: Sequence[_WorkItem],
    *,
    limits: LimitsConfig,
    metadata_config: SectionMetadataConfig,
    text_limit: int,
) -> dict[str, Any]:
    return {
        "task": "section_metadata",
        "artifact_role": SECTION_METADATA_ROLE,
        "summary_search_keys_are_evidence": False,
        "instructions": _SEARCH_KEYS_INSTRUCTIONS,
        "return_shape": {
            "sections": [
                {
                    "section_id": "string",
                    "summary": "string",
                    "search_keys": ["string"],
                },
            ],
        },
        "limits": {
            "summary_enabled": metadata_config.summary_enabled,
            "search_keys_enabled": metadata_config.search_keys_enabled,
            "section_summary_max_chars": limits.section_summary_max_chars,
            "search_keys_max": limits.search_keys_max,
        },
        "sections": [
            {
                "section_id": item.section.section_id,
                "stable_section_uid": item.section.stable_section_uid,
                "heading_path": item.section.heading_path,
                "identifiers": item.identifiers,
                "text": item.section.text[:text_limit] if text_limit else "",
            }
            for item in batch
        ],
    }


def _minimal_batch_prompt(batch: Sequence[_WorkItem], max_chars: int) -> str:
    prompt = json.dumps(
        {
            "task": "section_metadata",
            "artifact_role": SECTION_METADATA_ROLE,
            "summary_search_keys_are_evidence": False,
            "sections": [
                {"section_id": item.section.section_id}
                for item in batch
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(prompt) <= max_chars or len(batch) <= 1:
        return prompt
    prompt = json.dumps(
        {
            "task": "section_metadata",
            "sections": [
                {"section_id": item.section.section_id}
                for item in batch
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return prompt


def _output_by_section(
    output: Mapping[str, Any],
    batch: Sequence[_WorkItem],
) -> dict[str, dict[str, Any]]:
    raw_sections = output.get("sections")
    if isinstance(raw_sections, Sequence) and not isinstance(raw_sections, (str, bytes)):
        by_id: dict[str, dict[str, Any]] = {}
        for raw_item in raw_sections:
            if not isinstance(raw_item, Mapping):
                continue
            section_id = raw_item.get("section_id")
            if isinstance(section_id, str) and section_id:
                by_id[section_id] = dict(raw_item)
        if by_id:
            return by_id

    if "summary" in output or "search_keys" in output:
        return {item.section.section_id: dict(output) for item in batch}
    return {}


def _entry_from_llm_output(
    item: _WorkItem,
    raw_output: Mapping[str, Any],
    *,
    metadata_version: int,
    generated_at: str | None,
    metadata_config: SectionMetadataConfig,
    limits: LimitsConfig,
    provider_succeeded: bool,
) -> dict[str, Any]:
    section = item.section
    summary = ""
    if metadata_config.summary_enabled:
        summary = _summary(raw_output, section, limits, provider_succeeded)

    search_keys: list[str] = []
    if metadata_config.search_keys_enabled:
        search_keys = _search_keys(
            raw_output,
            section,
            item.identifiers,
            limits,
            provider_succeeded=provider_succeeded,
        )

    entry = {
        "section_id": section.section_id,
        "stable_section_uid": section.stable_section_uid,
        "source_document_id": section.source_document_id,
        "heading_path": section.heading_path,
        "summary": summary,
        "search_keys": search_keys,
        "identifiers": item.identifiers,
        "related_sections": [],
        "metadata_version": metadata_version,
        "source_hash": section.source_hash,
        "semantic_hash": section.semantic_hash,
        "generated_at": generated_at,
    }
    entry["_generation"] = {
        "artifact_role": SECTION_METADATA_ROLE,
        "summary_search_keys_are_evidence": False,
        "prompt_version": SECTION_METADATA_PROMPT_VERSION,
        "model": str(raw_output.get("model", "")),
        "provider": str(raw_output.get("provider", "")),
        "metadata_version": metadata_version,
        "identifier_extractor_version": IDENTIFIER_EXTRACTOR_VERSION,
        "section_summary_max_chars": limits.section_summary_max_chars,
        "search_keys_max": limits.search_keys_max,
    }
    return _public_entry(entry)


def _summary(
    raw_output: Mapping[str, Any],
    section: _NormalizedSection,
    limits: LimitsConfig,
    provider_succeeded: bool,
) -> str:
    value = raw_output.get("summary")
    summary = value if isinstance(value, str) else ""
    if not summary and provider_succeeded:
        summary = _fallback_summary(section)
    return _limit_text(summary, limits.section_summary_max_chars)


def _search_keys(
    raw_output: Mapping[str, Any],
    section: _NormalizedSection,
    identifiers: Sequence[str],
    limits: LimitsConfig,
    *,
    provider_succeeded: bool,
) -> list[str]:
    if not provider_succeeded:
        return []
    keys: list[str] = []
    raw_keys = raw_output.get("search_keys")
    if isinstance(raw_keys, Sequence) and not isinstance(raw_keys, (str, bytes)):
        keys.extend(str(key) for key in raw_keys)
    keys.extend(section.heading_path)
    deduped = _dedupe_nonempty(keys)
    identifier_set = {
        " ".join(str(value).strip().split()) for value in identifiers
    }
    identifier_set.discard("")
    filtered = [
        key for key in deduped
        if not _is_identifier_like_search_key(key, identifier_set)
    ]
    return filtered[: limits.search_keys_max]


def _fallback_summary(section: _NormalizedSection) -> str:
    heading = " / ".join(section.heading_path).strip()
    first_line = next(
        (line.strip() for line in section.text.splitlines() if line.strip()),
        "",
    )
    if heading and first_line:
        return f"{heading}: {first_line}"
    return heading or first_line


def _limit_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    return value[:max_chars]


def _dedupe_nonempty(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = " ".join(str(value).strip().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _append_identifier(identifiers: list[str], value: str) -> None:
    normalized = " ".join(value.strip().split())
    if not normalized:
        return
    if normalized not in identifiers:
        identifiers.append(normalized)


def _diagnostic(
    reason_code: str,
    message: str,
    batch: Sequence[_WorkItem],
    request: LlmRequest,
) -> dict[str, Any]:
    return {
        "reason_code": reason_code,
        "message": message,
        "stage": "section_metadata",
        "model": request.model,
        "provider": "",
        "prompt_version": request.prompt_version,
        "source_hash": request.source_hash,
        "section_ids": [item.section.section_id for item in batch],
        "severity": "error",
    }


def _public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    entry.pop("_generation", None)
    entry.pop("_artifact_generation", None)
    return entry


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_related_section_candidates(
    sections: Sequence[Any],
    *args: Any,
    section_metadata: Any | None = None,
    metadata: Any | None = None,
    config: Any | None = None,
    project_config: Any | None = None,
    limits: Any | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Re-export Related Sections candidate generation with an explicit API."""

    from spec_grag.related_sections import build_related_section_candidates as _build

    if args:
        if section_metadata is None:
            section_metadata = args[0]
        if len(args) > 1 and config is None:
            config = args[1]
        if len(args) > 2 and limits is None:
            limits = args[2]
    return _build(
        sections,
        section_metadata=section_metadata,
        metadata=metadata,
        config=config,
        project_config=project_config,
        limits=limits,
        generated_at=generated_at,
    )


def validate_related_sections(
    source_section_id: str,
    llm_output: Any | None = None,
    *args: Any,
    output: Any | None = None,
    items: Any | None = None,
    candidates: Any | None = None,
    related_section_candidates: Any | None = None,
    sections: Sequence[Any] = (),
    section_by_id: Mapping[str, Any] | None = None,
    section_metadata: Any | None = None,
    metadata: Any | None = None,
    config: Any | None = None,
    project_config: Any | None = None,
    limits: Any | None = None,
    related_selected_max_per_section: int | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Re-export Related Sections validation with a section_metadata entry point."""

    from spec_grag.related_sections import validate_related_sections_result as _validate

    if args:
        if candidates is None:
            candidates = args[0]
        if len(args) > 1 and not sections:
            sections = args[1]
        if len(args) > 2 and section_metadata is None:
            section_metadata = args[2]
        if len(args) > 3 and limits is None:
            limits = args[3]
    section_items: Sequence[Any] = sections
    if not section_items and section_by_id is not None:
        section_items = list(section_by_id.values())
    effective_limits = limits
    if effective_limits is None and related_selected_max_per_section is not None:
        effective_limits = LimitsConfig(
            related_selected_max_per_section=related_selected_max_per_section,
        )
    return _validate(
        source_section_id,
        _first_not_none(llm_output, output, items, []),
        candidates=_first_not_none(candidates, related_section_candidates, []),
        sections=section_items,
        section_metadata=section_metadata,
        metadata=metadata,
        config=config,
        project_config=project_config,
        limits=effective_limits,
        generated_at=generated_at,
    ).to_dict()


def select_related_sections(
    sections: Sequence[Any] | str | None = None,
    *args: Any,
    source_section_id: str | None = None,
    source_section: Any | None = None,
    candidates: Any | None = None,
    related_section_candidates: Any | None = None,
    section_metadata: Any | None = None,
    metadata: Any | None = None,
    section_by_id: Mapping[str, Any] | None = None,
    config: Any | None = None,
    project_config: Any | None = None,
    provider: LlmProvider | None = None,
    llm_provider: LlmProvider | None = None,
    llm_config: Any | None = None,
    limits: Any | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Re-export Related Sections selection with a section_metadata entry point."""

    from spec_grag.related_sections import select_related_sections_result as _select

    section_sequence: Sequence[Any] | None
    if isinstance(sections, str):
        if source_section_id is None:
            source_section_id = sections
        section_sequence = None
    else:
        section_sequence = sections
    if args:
        if candidates is None and related_section_candidates is None:
            candidates = args[0]
        if len(args) > 1 and provider is None and llm_provider is None:
            provider = args[1]
        if len(args) > 2 and config is None:
            config = args[2]
    if section_sequence is not None:
        section_items = list(section_sequence)
    elif section_by_id is not None:
        section_items = list(section_by_id.values())
    elif source_section is not None:
        section_items = [source_section]
    else:
        section_items = []
    return _select(
        section_items,
        candidates=_first_not_none(candidates, related_section_candidates),
        section_metadata=section_metadata,
        metadata=metadata,
        config=config,
        project_config=project_config,
        provider=provider,
        llm_provider=llm_provider,
        llm_config=llm_config,
        limits=limits,
        source_section_ids=[source_section_id] if source_section_id else None,
        generated_at=generated_at,
    ).to_dict()


def related_section_reevaluation_targets(
    changed_section_ids: Sequence[str] | None = None,
    *args: Any,
    changed_sections: Sequence[str] | None = None,
    sections: Sequence[Any] = (),
    section_metadata: Any | None = None,
    previous_metadata: Any | None = None,
    metadata: Any | None = None,
    candidates: Any | None = None,
    related_section_candidates: Any | None = None,
) -> list[str]:
    """Re-export incremental Related Sections re-evaluation target calculation."""

    from spec_grag.related_sections import (
        related_section_reevaluation_targets as _targets,
    )

    if args:
        if not sections:
            sections = args[0]
        if len(args) > 1 and section_metadata is None:
            section_metadata = args[1]
        if len(args) > 2 and candidates is None:
            candidates = args[2]
    return _targets(
        _first_not_none(changed_section_ids, changed_sections, []),
        sections=sections,
        section_metadata=_first_not_none(
            section_metadata,
            previous_metadata,
            metadata,
        ),
        candidates=_first_not_none(candidates, related_section_candidates),
    )


__all__ = [
    "IDENTIFIER_EXTRACTOR_VERSION",
    "SECTION_METADATA_PROMPT_VERSION",
    "SECTION_METADATA_ROLE",
    "SectionMetadataCache",
    "SectionMetadataGeneration",
    "build_section_metadata",
    "build_related_section_candidates",
    "extract_identifiers",
    "generate_section_metadata",
    "generate_section_metadata_result",
    "related_section_reevaluation_targets",
    "section_metadata_cache_key",
    "select_related_sections",
    "validate_related_sections",
]
