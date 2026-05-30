"""Internal vocabulary that must never appear in user-facing slash output.

The slash commands return a human-facing reply built from the CLI's internal
JSON. Per課題 #2 / #8 (``doc/TODO/TODO_slash_command_user_facing_output.ja.md``)
and EXTERNAL_DESIGN.ja.md §8.5, the reply must not contain CLI-internal field
names, enum values, or pipeline stage names — a reader who has never seen the
source code cannot decode them.

``FORBIDDEN_TERMS`` is the single source of truth used by both the command
templates' "禁止用語リスト" and the E2E assertions. ``find_forbidden_terms``
returns every forbidden substring present in a candidate user-facing reply.
"""

from __future__ import annotations

from collections.abc import Iterable


# Internal control flags / freshness gate field names.
_CONTROL_FLAGS = (
    "should_stop",
    "stop_reason",
    "blocking_reasons",
    "can_continue",
    'status="blocked"',
    'status="failed"',
    'status="error"',
    'status="fresh"',
    "status=blocked",
    "status=failed",
    "status=error",
    "status=fresh",
)

# Freshness `blocking_reasons` enum values + the internal "needs answer" signal.
_ENUM_VALUES = (
    "dirty_or_stale_source",
    "stale_config_or_schema",
    "watcher_running",
    "watcher_queue_pending",
    "pending_conflict",
    "failed_required_artifact",
    "needs_agent_answer",
    "answer candidate",
)

# Pipeline stage names / per-stage status field names from `/spec-core`.
_PIPELINE_STAGE_NAMES = (
    "section_metadata_generation",
    "related_sections_status",
    "related_sections",
    "retrieval_index_status",
    "retrieval_index",
    "chapter_anchors",
    "chapter_key_anchor",
)

# Normal-completion metric / count field names from CoreResult.
_NORMAL_COMPLETION_FIELDS = (
    "updated_sources",
    "failed_sources",
    "failed_sections",
    "pending_conflict_count",
    "stale_dismissal_count",
    "auto_dismissed_conflict_count",
    "auto_dismissed_conflict_ids",
    "regenerated_chapter_anchors",
)

# Internal answer / constraint field names + internal result paths.
_RESULT_PATH_FIELDS = (
    "inject_result.",
    "freshness_report",
    "evidence_origin",
    "support_refs",
)

# Conflict Review Item raw field names (must be rendered as human headings, #3).
_CONFLICT_FIELD_NAMES = (
    "conflict_id",
    "why_conflicting",
    "why_llm_cannot_decide",
    "source_refs",
    "recommended_next_action",
    'status="dismissed"',
    "status=dismissed",
)

# Non-Japanese natural-language strings the CLI emits as defaults but the Agent
# must translate before rendering them in user-facing replies (課題 #13). The
# user-facing language is Japanese; English natural sentences that escape into
# the body indicate the Agent skipped its translation duty.
#
# CLI returns these as the raw value of fields such as
# ``conflict_review_item.recommended_next_action``; the Agent template's
# "pending conflict の必須出力フォーマット" section requires translating any
# non-Japanese natural sentence into Japanese before placing it under "次の操作:".
# Command names, URLs, file paths, and identifiers are exempt — they pass
# through verbatim and are not listed here.
_NON_JAPANESE_NATURAL_SENTENCES = (
    "Ask a human to decide this conflict.",
)

FORBIDDEN_TERMS: tuple[str, ...] = (
    _CONTROL_FLAGS
    + _ENUM_VALUES
    + _PIPELINE_STAGE_NAMES
    + _NORMAL_COMPLETION_FIELDS
    + _RESULT_PATH_FIELDS
    + _CONFLICT_FIELD_NAMES
    + _NON_JAPANESE_NATURAL_SENTENCES
)


def find_forbidden_terms(text: str, *, allow: Iterable[str] = ()) -> list[str]:
    """Return forbidden substrings present in ``text``.

    ``allow`` is a per-scenario escape hatch for the rare case where a forbidden
    substring legitimately appears (e.g. a Source Specs file path that contains
    ``related_sections``). Callers must justify every allow entry in the scenario
    registry; the default empty allowlist is the contract.
    """

    allowed = set(allow)
    hits: list[str] = []
    for term in FORBIDDEN_TERMS:
        if term in allowed:
            continue
        if term in text and term not in hits:
            hits.append(term)
    return hits
