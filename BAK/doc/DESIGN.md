# SPEC-grag Design

> This document replaces the old chapter-anchor-centered design. The previous
> design is kept at `doc/DESIGN_old.md` for reference. `HANDOFF.md` still
> describes the old implementation state and must be rewritten after this
> design is accepted.

## 1. Purpose

SPEC-grag is a specification authoring assistant that prevents an LLM from
overfitting to the most recently read specification text.

Modern LLMs are increasingly faithful to supplied documents. That is useful for
stable implementation work, but it is harmful during specification design where
the documents themselves may still be tentative, conflicting, or locally
optimized. The system must therefore distinguish:

- what the source document says
- whether that statement is stable, tentative, deprecated, or conflicting
- whether that statement is a requirement, constraint, exception, dependency,
  design principle, or open issue
- whether it should constrain the current change

The goal is not to build a stronger document search engine. The goal is to
build a control structure that brings a proposed specification change back to:

```text
Purpose -> Concept -> approved constraints -> candidate change targets
```

The graph must help the agent decide what must be protected, what may be
changed, and what needs human review.

## 2. Core Design Shift

The old design treated these as the main intermediate products:

```text
Chapter anchors
Dependency graph embeddings
Hierarchical clusters
```

Those are useful retrieval aids, but they are not the core model. The new
design is fact-first:

```text
Source text
  -> Atomic facts
  -> normalized constraints / dependencies / exceptions
  -> validated edges with evidence
  -> query-time decision classification
```

Chapter anchors and clusters remain useful, but they are secondary indexes.
They help locate relevant areas. They do not decide what is true, stable, or
binding.

## 3. Information Model

### 3.1 Core Documents

| Item | Role | Update Policy |
|---|---|---|
| Purpose | Business goal, UX root, reason the system exists | Human-authored only |
| Concept | Stable architecture principles and design philosophy | Human-approved only |
| Source specs | Current chapter files and working specifications | Edited by users |

Purpose and Concept are not ordinary extracted facts. They are higher-authority
anchors. The system may propose changes to Concept, but it must not silently
rewrite it. Purpose is never updated by SPEC-grag.

### 3.2 Canonical Node Types

SPEC-grag stores a canonical graph with explicit node types:

```text
Purpose
Concept
DesignPrinciple
ChapterAnchor
SpecSection
AtomicFact
Requirement
Constraint
ExceptionRule
Dependency
Conflict
OpenIssue
Screen
API
Component
DataModel
State
StateTransition
Role
Permission
Workflow
TestCase
ChangeRequest
```

Not every project needs every type, but the schema must support them without
collapsing everything into generic entities.

### 3.3 Canonical Edge Types

The relation vocabulary is domain-specific and must be normalized. Minimum edge
types:

```text
SUPPORTS
DERIVED_FROM
MENTIONED_IN
ANCHORS
IMPLEMENTS
REFINES
PART_OF
DEPENDS_ON
CONSTRAINS
REQUIRES
FORBIDS
ALLOWS
EXCEPTS
OVERRIDES
PROTECTS
AFFECTS
CONFLICTS_WITH
SAME_AS
OUT_OF_SCOPE_FOR
```

`related_to` is not acceptable as a primary relation type for specification
reasoning. It may exist only as a low-confidence fallback.

### 3.4 Required State Fields

Every fact, constraint, and edge must carry state. This is the main guard
against document over-anchoring.

```text
authority:
  human_approved | inferred | document_claim | candidate

stability:
  core | stable | tentative | deprecated | conflicting

scope:
  global | chapter | feature | component

validation:
  unvalidated | validated | rejected | needs_human_review

risk:
  low | medium | high | critical
```

The retrieval layer must prefer `human_approved` and `validated` items, but it
must still surface `tentative`, `conflicting`, and `needs_human_review` items as
risks instead of hiding them.

## 4. Evidence Model

An edge is not accepted because an extractor produced it. An edge is accepted
because it has evidence.

Recommended edge record:

```text
edge_id
source_node_id
target_node_id
relation_type
confidence
validation
authority
stability
scope
risk
evidence_fact_ids
source_chunk_ids
source_section_ids
validated_by
validated_at
validation_reason
```

Atomic facts are stored separately and linked to edges:

```text
fact_id
subject
predicate
object
temporal_marker
confidence
source_chunk_id
source_section_id
authority
stability
scope
```

This creates two layers:

```text
Entity / Constraint Graph
  stable normalized nodes and edges

Fact / Evidence Layer
  exact source-grounded factual claims
```

## 5. Extractor Roles

The extractor roles are:

| Role | Extractor | Position |
|---|---|---|
| Primary fact extraction | `AtomicFactExtractor` | Build-time |
| Edge validation | `LLMRelationshipExtractor` + Triple Reflection | Build-time, and query-time only for a few risky candidates |
| Core anchor candidates | `GleaningEntityExtractor` | Build-time, limited to Purpose / Concept / glossary / key chapters |
| Wide scan | `GLiNERExtractor` | Build-time, cheap candidate discovery |
| Baseline comparison | `LLMEntityExtractor` | PoC and regression comparison only |

The old design over-centered `LLMEntityExtractor` and hierarchical clustering.
The new design uses entity extraction to find candidates, but uses atomic facts
and validated edges to reason.

## 6. Build-Time Pipeline

### 6.1 Source Sync

For every configured source file:

```text
source markdown
  -> section-aware chunking
  -> source section records
  -> content hash comparison
  -> changed chunks only
```

Change detection should be hash-based. Timestamps may be kept for reporting, but
they should not be the source of truth.

### 6.2 Wide Candidate Scan

Use GLiNER or equivalent non-generative extraction for broad, cheap discovery:

```text
Screen / API / Component / Role / Permission / State / DataModel / ChapterAnchor
```

These candidates are not authoritative. They are indexing hints.

### 6.3 Atomic Fact Extraction

Run atomic fact extraction on changed chunks:

```text
TextChunk
  -> AtomicFactExtractor
  -> AtomicFact[]
```

For specification text, prompts must ask for:

```text
requirements
constraints
exceptions
preconditions
postconditions
state transitions
permissions
prohibitions
dependencies
open questions
```

The output must not be treated as final truth. It starts as
`authority=document_claim` or `authority=candidate`.

### 6.4 Relation Candidate Generation

Convert atomic facts into candidate edges:

```text
AtomicFact
  -> candidate relation
  -> normalized relation type
  -> candidate edge
```

Relation normalization is mandatory. Free-form predicates must be mapped into
the canonical relation vocabulary.

### 6.5 Triple Reflection Validation

Run validation for important candidate edges:

```text
candidate edge + source text
  -> Triple Reflection
  -> validated | rejected | needs_human_review
```

Validation asks whether the source text explicitly supports the relation. It
does not decide whether the relation should constrain a future change. That
second decision is query-specific.

### 6.6 Canonical Merge

Merge all outputs into the canonical graph:

```text
deduplicate nodes
merge equivalent facts
merge equivalent edges
attach evidence facts
update authority/stability/validation state
persist graph
update indexes
```

The system must avoid storing duplicate semantic edges such as:

```text
requires
depends on
needs
is based on
```

as separate relation types unless they truly mean different things in the
domain.

### 6.7 Secondary Indexes

After the canonical graph is updated, build secondary indexes:

```text
chapter anchors
vector embeddings
hierarchical clusters
relation neighborhood indexes
risk indexes
```

These indexes accelerate retrieval. They do not replace the canonical graph.

## 7. Query-Time Pipeline

### 7.1 Query Understanding

Given a change request, first classify:

```text
requested change target
likely affected features
risk class
explicit non-goals
possible permissions / privacy / billing / data loss concerns
```

The query must not immediately pull large source text into the main LLM
context. It should first retrieve structured graph candidates.

### 7.2 Retrieve Binding Anchors First

Query-time retrieval starts from stable anchors:

```text
Purpose
Concept
DesignPrinciple
human_approved constraints
validated critical edges
```

Then it expands toward:

```text
related ChapterAnchor
candidate change target
dependency edges
exception rules
conflicts
source evidence
```

### 7.3 Candidate Classification

The main query-time LLM task is not extraction. It is classification over a
small candidate set.

For each candidate edge/fact:

```text
protect_constraint
change_target
out_of_scope_core
supporting_context
conflict
irrelevant
needs_human_review
```

This is where the system answers:

```text
Should this edge constrain this change?
```

That cannot be fully decided at build time.

### 7.4 Fast / Balanced / Strict Paths

Fast path:

```text
validated edges only
no query-time Triple Reflection
no new relation extraction
```

Balanced path:

```text
top-k candidates
low-confidence or high-risk edges classified by LLM
query-decision cache enabled
```

Strict path:

```text
permissions
privacy
billing
inventory
ordering
legal
data deletion
compatibility

-> re-run Triple Reflection on a few critical edges
-> require human review for conflicts
```

### 7.5 LLM Context Shape

The final LLM context should be structured:

```text
A. User change request
B. Binding Purpose / Concept
C. Protected constraints
D. Candidate change targets
E. Out-of-scope core items
F. Evidence atomic facts
G. Conflicts and human-review items
```

Do not dump whole chapters unless the user explicitly asks for broad review.

## 8. LLM Provider Architecture

### 8.1 Provider Rule

All generative extraction, summarization, normalization, validation, and
query-time classification must go through a common provider trait.

The implementation target is:

```text
AsyncLanguageModel
```

Provider implementations:

```text
CodexCliLanguageModel    primary for this project
ClaudeCliLanguageModel   compatible provider / existing implementation
AsyncMockLanguageModel   tests
Ollama generation        not used for specification reasoning by default
```

Codex and Claude providers do the same job. They differ only in subprocess
command format, output parsing, model configuration, timeout, and rate limits.

### 8.2 Codex as Primary

Because Codex is the primary implementation agent for this project,
`CodexCliLanguageModel` should become the primary provider.

Expected responsibilities:

```text
complete(prompt)
complete_with_params(prompt, params)
complete_batch_concurrent(prompts, max_concurrent)
is_available()
model_info()
```

The exact headless command format must be verified before implementation. The
design assumption is a subprocess provider similar to:

```text
codex exec ...
```

The actual command, JSON output schema, and model flags are implementation
details, not design assumptions.

### 8.3 Claude Compatibility

`ClaudeCliLanguageModel` already exists and can remain valuable. It should not
own the architecture.

The provider selection should be:

```toml
[llm]
provider = "codex_cli" # codex_cli | claude_cli | mock

[llm.codex_cli]
command = "codex"
model = "gpt-5.4"

[llm.claude_cli]
command = "claude"
model = "sonnet"
```

The old `summary_provider` name is too narrow. The provider now handles more
than summaries.

### 8.4 Embeddings

Embeddings remain separate from generative LLMs.

Default:

```text
Ollama nomic-embed-text
```

Embedding models support retrieval and clustering only. They do not perform
specification judgment.

## 9. Agent Adapters

### 9.1 Shared CLI Contract

SPEC-grag must expose an agent-neutral CLI. Claude Code and Codex should both
drive the same commands and parse the same structured output.

The CLI is the contract. Agent-specific prompts are adapters.

### 9.2 Claude Code Adapter

`templates/.claude/commands` are Claude Code slash-command adapters.

They are useful when the user runs SPEC-grag from Claude Code. They should be
kept, but they must not contain the only copy of the workflow logic.

Status:

```text
templates/.claude/commands/spec-inject.md
templates/.claude/commands/spec-core.md
templates/.claude/commands/spec-realign.md
```

These should be rewritten after the CLI output contract is stable.

### 9.3 Codex Adapter

For Codex, the equivalent of Claude slash commands is a skill/workflow
instruction set.

That does not mean the `.claude/commands` files are copied directly into a
skill. Instead:

```text
Claude slash command -> Claude-specific adapter
Codex skill          -> Codex-specific adapter
spec-grag CLI        -> shared execution contract
```

A future Codex skill should live outside `templates/.claude/commands`, for
example:

```text
skills/spec-grag/SKILL.md
```

or an equivalent Codex workflow location. It should instruct Codex how to:

```text
run spec-grag sync/index
run spec-grag inject
run spec-grag realign
classify candidate constraints
apply or reject proposed changes
```

## 10. CLI Commands

The command set should be revised around the new model.

### 10.1 `spec-grag index`

Build or update the canonical graph.

```text
spec-grag index [--all]
```

Responsibilities:

```text
source sync
atomic fact extraction
wide scan
relation normalization
Triple Reflection validation
canonical merge
secondary index update
persist graph
```

This may replace the old "common pre-processing hidden inside every command"
model. Hidden heavy work makes latency unpredictable.

### 10.2 `spec-grag inject`

Inject approved core context:

```text
Purpose
Concept
approved high-risk constraints
current graph/index status
```

It must not dump raw chapter text.

### 10.3 `spec-grag realign`

Run query-time retrieval for a change request:

```text
spec-grag realign "<change request>"
```

Output should be structured Markdown or JSON containing:

```text
binding anchors
protected constraints
candidate change targets
out-of-scope core items
evidence facts
conflicts
human review items
```

The agent then uses this output to produce or revise a specification change.

### 10.4 `spec-grag core`

Maintain core documents.

`Purpose` remains human-authored. `Concept` may receive proposals, but only
human-approved hunks are written.

This command should not be the primary graph builder.

## 11. Storage

Recommended storage layout:

```text
.spec-grag/
  config.toml
  graph/
    canonical_nodes.jsonl
    canonical_edges.jsonl
    atomic_facts.jsonl
    evidence_links.jsonl
    validation_events.jsonl
    indexes/
      chapter_anchors.json
      vector/
      clusters/
  cache/
    query_decisions.jsonl
```

SQLite may replace JSONL if transactionality becomes important. The logical
schema should remain the same.

## 12. Implementation Priorities

Priority 0: freeze the old design

```text
doc/DESIGN_old.md remains reference only
HANDOFF.md is considered legacy until rewritten
```

Priority 1: provider abstraction

```text
keep ClaudeCliLanguageModel
implement CodexCliLanguageModel
rename summary_provider -> provider
ensure batch concurrency and timeouts are provider-level
```

Priority 2: canonical schema and persistence

```text
nodes
edges
atomic facts
evidence links
validation events
query decision cache
```

Priority 3: fact-first indexing

```text
section-aware chunking
AtomicFactExtractor through AsyncLanguageModel
relation normalization
candidate edge generation
Triple Reflection through AsyncLanguageModel
canonical merge
```

Priority 4: query-time decision engine

```text
retrieve anchors
retrieve candidate targets
classify constraints vs change targets
Fast/Balanced/Strict modes
cache decisions
```

Priority 5: adapters

```text
Codex skill/workflow adapter
Claude slash-command adapter
agent-neutral CLI output contract
```

## 13. Migration Notes

Existing useful work:

```text
ClaudeCliLanguageModel implementation
Project config loader
basic CLI command skeleton
source glob expansion
excitation output prototype
GraphRAG-rs vendor availability
```

Existing work that should be treated as legacy:

```text
chapter-anchor-centered DESIGN_old.md
Concept generation from hierarchical cluster summaries as a main path
templates/.claude/commands as the only workflow definition
AsyncGraphRAG demo entity extraction path
hidden heavy sync before every command
```

The immediate next document after this one should be `HANDOFF.md`, rewritten to
match this design and to remove the old priority order.

