---
description: Refresh SPEC-grag graph state and manage guarded Concept diffs.
argument-hint: "[--all] [--approval-json '<approval transport JSON>']"
allowed-tools: Bash(spec-grag-slash:*), Bash(python:*)
---

# /spec-core

Run SPEC-grag core maintenance for the current project root.

Use the installed command when available:

```bash
spec-grag-slash spec-core $ARGUMENTS
```

Fallback when the console script is not on `PATH`:

```bash
python3 -m spec_grag.slash spec-core $ARGUMENTS
```

Argument contract:

- `/spec-core`
- `/spec-core --all`
- internal approval transport through `--approval-json`

Read the JSON envelope before acting. If the result is
`ConceptApprovalRequiredResult` or `ConflictApprovalRequiredResult`, summarize
`approval_prompt.items` in chat and ask the user for approval, revision
instructions, non-approval, or defer where available. Then pass the selected
`transport.approval` object back through `--approval-json`. Do not edit
`docs/core/concept.md` directly to bypass the pending diff protocol.
