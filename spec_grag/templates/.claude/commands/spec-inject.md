---
description: Prepare SPEC-grag constraints without answering the task
argument-hint: "[task]"
allowed-tools: Bash(spec-grag inject:*)
---

# /spec-inject

The source of truth is the SPEC-grag external command contract and the SPEC-grag CLI input/output. This Claude template is not a separate specification.

Run the SPEC-grag CLI reference operation for `/spec-inject` from the project root, then perform Agentic Search as the Agent / LLM. The CLI provides retained artifacts, freshness reports, retrieval, and source snippets; it does not choose the exploration strategy or generate the final constraint set by itself.

Check freshness first. If the report is not fresh, stop according to `blocking_reasons`; do not run `/spec-core` automatically. If pending conflict is the remaining blocker, present the Conflict Review Items and decision choices to the human before normal constraint generation.

Use Purpose, Core Concept, Source Specs snippets, Section Summary, Section Search Keys, Related Sections, Chapter Key Anchors, and Conflict Review Items as reference operations for exploration. Treat Related Sections as `support_refs` / reference helpers only; they help decide what to inspect and are not final evidence.

For every injected constraint, cite final evidence from at least one of: Purpose, Core Concept, Source Specs, or a resolved Conflict Review Item whose resolution is not stale. Do not use Section Summary, Section Search Keys, Related Sections, Chapter Key Anchor, or stale Conflict Review Items as the sole evidence for a constraint.

Purpose and Core Concept are human-owned read-only inputs for this command. Output the constraint set, evidence list, and search summary only. Do not answer the task or propose the final solution in `/spec-inject`.
