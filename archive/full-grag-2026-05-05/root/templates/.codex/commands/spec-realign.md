---
description: Produce a grounded answer after SPEC-grag injection and answer validation.
argument-hint: "\"task prompt\""
allowed-tools: Bash(spec-grag-slash:*), Bash(python:*)
---

# /spec-realign

Use SPEC-grag to answer the supplied task prompt with grounded context.

Use the installed command when available:

```bash
spec-grag-slash spec-realign $ARGUMENTS
```

Fallback when the console script is not on `PATH`:

```bash
python3 -m spec_grag.slash spec-realign $ARGUMENTS
```

The argument is required:

```bash
spec-grag-slash spec-realign "task prompt"
```

Use the returned `RealignResult.answer` as the answer basis. Respect
`NeedMoreContextResult`, `ConceptApprovalRequiredResult`, and
`ConflictApprovalRequiredResult` as blockers.

Answer phase constraint: do not escape into raw source reads, broad grep, or
additional agentic search after this command unless the JSON envelope explicitly
asks for more context. If the answer is degraded, surface the warnings instead
of hiding them.
