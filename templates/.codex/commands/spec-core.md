---
description: Refresh SPEC-grag graph state and manage guarded Concept diffs.
argument-hint: "[--all] [--accept diff:hunk | --reject diff:hunk | --revise diff:hunk \"instruction\" | --apply diff]"
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
- `/spec-core --accept <diff_id>:<hunk_id>`
- `/spec-core --reject <diff_id>:<hunk_id>`
- `/spec-core --revise <diff_id>:<hunk_id> "<instruction>"`
- `/spec-core --apply <diff_id>`

Read the JSON envelope before acting. If the result is
`ConceptApprovalRequiredResult`, ask the user for hunk-level approval before
running accept, reject, revise, or apply. Do not edit `docs/core/concept.md`
directly to bypass the pending diff protocol.
