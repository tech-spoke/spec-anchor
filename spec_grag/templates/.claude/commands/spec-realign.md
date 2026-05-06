---
description: Prepare SPEC-grag constraints and answer the task
argument-hint: "[task]"
allowed-tools: Bash(spec-grag realign:*), Bash(spec-grag inject:*)
---

# /spec-realign

The source of truth is the SPEC-grag external command contract and the SPEC-grag CLI input/output. This Claude template only binds that contract to the Claude command environment.

Run the SPEC-grag CLI reference operation for `/spec-realign` from the project root, then perform the same Agent / LLM owned Agentic Search and constraint preparation as `/spec-inject`.

Check freshness first. If the report is not fresh, stop according to `blocking_reasons`; do not run `/spec-core` automatically. If pending conflict is the remaining blocker, present the Conflict Review Items and decision choices to the human before normal constraint generation.

Use Purpose, Core Concept, Source Specs snippets, Section Summary, Section Search Keys, Related Sections, Chapter Key Anchors, and Conflict Review Items as reference operations for exploration. Treat Related Sections as `support_refs` / reference helpers only; they help decide what to inspect and are not final evidence.

For every constraint, cite final evidence from at least one of: Purpose, Core Concept, Source Specs, or a resolved Conflict Review Item whose resolution is not stale. Do not use Section Summary, Section Search Keys, Related Sections, Chapter Key Anchor, or stale Conflict Review Items as the sole evidence for a constraint.

Purpose and Core Concept are human-owned read-only inputs for this command. After the constraint set is prepared, answer the task using only constraints grounded in those final evidence sources.
