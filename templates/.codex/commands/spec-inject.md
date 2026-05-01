---
description: Retrieve grounded Purpose, Concept, source, conflict, and review context.
argument-hint: "\"task or current user message\""
allowed-tools: Bash(spec-grag-slash:*), Bash(python:*)
---

# /spec-inject

Build the SPEC-grag injection context for the current task without drafting a
final answer.

Use the installed command when available:

```bash
spec-grag-slash spec-inject $ARGUMENTS
```

Fallback when the console script is not on `PATH`:

```bash
python3 -m spec_grag.slash spec-inject $ARGUMENTS
```

Treat the returned `InjectionContext` as the only injected context for this
turn. Keep Purpose, Concept, source constraints, conflicts, review notes, and
freshness warnings visible in the next response. If the envelope is blocked by
a pending Concept diff, resolve that diff with `/spec-core` first.

Do not use this command as permission to bypass grounding. If the returned
context is insufficient, report the gap instead of silently reading unrelated
raw source files.
