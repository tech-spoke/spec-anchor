---
description: Update SPEC-grag retained context artifacts
argument-hint: "[--all]"
allowed-tools: Bash(spec-grag core:*)
---

# /spec-core

The source of truth is the SPEC-grag external command contract and the SPEC-grag CLI input/output. This Claude template only describes how the Agent invokes that contract.

Run `spec-grag core` from the project root. Pass `--all` or `-a` only when the user explicitly asks for a full rebuild.

`/spec-core` generates or updates retained SPEC-grag artifacts: Section Summary, Section Search Keys, Related Sections, Chapter Key Anchor, Source Retrieval Index, and Conflict Review Items.

Purpose and Core Concept are human-owned read-only inputs for this command. Do not run `/spec-inject` or `/spec-realign` from this command. Return the CLI result and any pending Conflict Review Items for human decision.
