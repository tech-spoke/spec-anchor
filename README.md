# SPEC-grag

SPEC-grag is a lightweight specification context tool for Agent / LLM workflows.
It helps an Agent keep the project purpose, Core Concept, relevant Source Specs,
section summaries, related sections, chapter anchors, and conflict review state
in view while working. SPEC-grag does not update Core Concept automatically; it
is maintained by humans.

The current source of truth is:

- `doc/EXTERNAL_DESIGN.ja.md`
- `doc/DESIGN.ja.md`
- `doc/IMPLEMENTATION_PLAN.ja.md`
- `doc/TEST_SPEC.ja.md`

The standard path is the lightweight SPEC-grag design. It does not use property
graph, entity relation graph, hierarchical cluster, unrestricted graph traversal,
Core Concept auto-update, or CLI-driven Agentic Search as the standard path.

## Responsibility Boundary

- Human: maintains Purpose and Core Concept, decides pending Conflict Review
  Items, and makes final specification judgments.
- Agent / LLM: interprets the task and conversation, creates search keys, runs
  Agentic Search using CLI results, generates task-specific constraints, and
  produces answers when `/spec-realign` is used.
- CLI / SPEC-grag: reads config, tracks section hashes and freshness, generates
  context artifacts, stores Conflict Review Items, and exposes search/reference
  APIs. It does not decide the exploration strategy or final answer.

## Retrieval Stack

The standard retrieval stack is:

- Qdrant vector store
- FlagEmbedding BGE-M3 (`BAAI/bge-m3`) dense and sparse vectors
- Dense search + sparse search + RRF fusion

Ollama is not the standard sparse-vector path. Real Qdrant, FlagEmbedding, and
Agent CLI calls are guarded explicitly: smoke tests use smoke/local-service
opt-ins, while normal production operation uses the production readiness gates
described below.

## Install

From this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

If you use `uv`, `uv run ...` can be used instead of activating the venv.

Check the installed entrypoints:

```bash
spec-grag --help
spec-grag core --help
spec-grag inject --help
spec-grag realign --help
spec-grag-watch --help
spec-grag-setup-project --help
spec-grag-setup-system --help
```

## Setup

Check the local tool installation without changing a target project:

```bash
spec-grag-setup-system --check-only
```

Create SPEC-grag files in a project:

```bash
spec-grag-setup-project --target /path/to/project --agent both
```

This creates `.spec-grag/config.toml`, `.spec-grag/.gitignore`, CODEX and/or
CLAUDE command templates, and Purpose / Core Concept placeholders unless
`--no-init-core-files` is used. Existing managed files are not silently
overwritten; use `--dry-run` to preview or `--force` to replace managed files.

The generated config excludes `archive/**` from Source Specs by default.

## Usage

Run commands from the target project root, or pass `--project-root` where
available. The config path is fixed at `.spec-grag/config.toml`.

Generate or update context artifacts:

```bash
spec-grag core
spec-grag core --all
```

Record a human decision for a Conflict Review Item:

```bash
spec-grag core --decision-file decision.json
```

Prepare constraints for Agent-driven work:

```bash
spec-grag inject "task prompt" --constraints-file constraints.json
```

Prepare constraints and return an Agent-supplied answer candidate:

```bash
spec-grag realign "task prompt" \
  --constraints-file constraints.json \
  --answer-file answer.json
```

Watch Source Specs and run incremental updates in the background:

```bash
spec-grag-watch /path/to/project --once
spec-grag-watch /path/to/project --interval-sec 2 --debounce-sec 1
```

`spec-grag inject` and `spec-grag realign` expect the Agent / LLM to provide the
task-specific constraints (and, for realign, the answer candidate). In normal use
the installed CODEX / CLAUDE command templates guide the Agent through that
workflow.

## Freshness And Conflicts

`/spec-inject` and `/spec-realign` must pass the freshness gate before normal
constraint or answer generation. If Source Specs are dirty/stale, watcher work is
running or queued, config/schema is stale, required artifacts failed, or pending
conflicts exist, the command stops instead of silently continuing.

If dirty/stale state and pending conflicts exist together, update first with
`/spec-core` or the watcher. Only pending conflicts that remain after the update
need human judgment. Resolved but unreflected Conflict Review Items can be used
as temporary human decisions only while their recorded source hashes and valid
scope still apply.

## Command Templates

Project setup installs Agent-specific templates under:

- `.codex/commands/spec-core.md`
- `.codex/commands/spec-inject.md`
- `.codex/commands/spec-realign.md`
- `.claude/commands/spec-core.md`
- `.claude/commands/spec-inject.md`
- `.claude/commands/spec-realign.md`

These templates adapt the same SPEC-grag CLI contract to each Agent environment.
They are not the sole source of truth; the external design and CLI I/O contract
are authoritative.

## Tests And Smoke

Run local development tests:

```bash
python3 -m pytest
```

Run the built-in local smoke checks explicitly:

```bash
spec-grag-setup-system --check-only --run-smoke
```

Real-provider smoke is opt-in:

```bash
SPEC_GRAG_REAL_SMOKE=1 python3 -m pytest
```

Local-service smoke that needs Qdrant is also opt-in:

```bash
SPEC_GRAG_REAL_SMOKE=1 \
SPEC_GRAG_LOCAL_SERVICE=1 \
SPEC_GRAG_QDRANT_URL=http://localhost:6333 \
python3 -m pytest
```

Without those environment variables, real Agent CLI, FlagEmbedding BGE-M3, and
Qdrant service tests are skipped.

## Production Readiness

Production readiness is separate from smoke testing. Smoke tests prove selected
real paths can run; production readiness proves a normal user can start and keep
SPEC-grag running with a persistent Qdrant service, BGE-M3, and an authenticated
Agent CLI.

Install the tool and retrieval dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[retrieval,test]'
```

Start Qdrant as a native service or managed process, not Docker. One local
example:

```bash
export QDRANT__SERVICE__HTTP_PORT=6333
export QDRANT__SERVICE__GRPC_PORT=6334
export QDRANT__STORAGE__STORAGE_PATH=/var/lib/spec-grag/qdrant
qdrant --disable-telemetry
```

Enable normal real-provider and real-retrieval execution. These are the normal
operation gates; `SPEC_GRAG_REAL_SMOKE` remains only for explicit smoke tests.

```bash
export SPEC_GRAG_REAL_PROVIDER=1
export SPEC_GRAG_REAL_RETRIEVAL=1
export SPEC_GRAG_QDRANT_URL=http://localhost:6333
```

Verify the local installation and production-readiness diagnostics:

```bash
spec-grag-setup-system --check-only
```

The JSON result includes `production_readiness`. A ready environment has Qdrant,
FlagEmbedding, qdrant-client, at least one Agent CLI, console scripts, and both
normal operation gates enabled. Missing pieces appear as blocking reason codes
such as `qdrant_service_unavailable`, `flagembedding_missing`,
`agent_cli_unavailable`, `real_provider_gate_disabled`, or
`real_retrieval_gate_disabled`.

Create or update a project, then run the normal CLI path:

```bash
spec-grag-setup-project --target /path/to/project --agent both
cd /path/to/project
spec-grag core --all
spec-grag inject "task prompt" --constraints-file constraints.json
spec-grag realign "task prompt" --constraints-file constraints.json --answer-file answer.json
spec-grag-watch . --interval-sec 2 --debounce-sec 1
```

Restart Qdrant by stopping the native service or process and starting it again
with the same `QDRANT__STORAGE__STORAGE_PATH`. Verify persistence by rerunning
`spec-grag core` and checking `.spec-grag/context/retrieval_index_revision.json`
for the same Qdrant URL, collection, schema version, server version, BGE-M3
model, dense/sparse named vectors, and RRF diagnostics.

Troubleshoot by checking the diagnostics first:

- `real_provider_required`: set `SPEC_GRAG_REAL_PROVIDER=1` and confirm `codex`
  or `claude` is available and authenticated.
- `agent_cli_unauthenticated`: authenticate the subscription CLI outside the
  project-local environment and rerun the command.
- `real_retrieval_index=false` or `real_retrieval_gate_disabled`: set
  `SPEC_GRAG_REAL_RETRIEVAL=1` and confirm Qdrant is reachable.
- `qdrant_service_unavailable`: start or restart the native Qdrant service and
  confirm `SPEC_GRAG_QDRANT_URL`.
- `qdrant_schema_mismatch`: recreate or migrate the Qdrant collection so it has
  the `dense` and `sparse` named vectors expected by SPEC-grag.
- `flagembedding_missing` or `embedding_model_load_failure`: install the
  retrieval extra and confirm the BGE-M3 model cache under `HF_HOME`,
  `HF_HUB_CACHE`, or `~/.cache/huggingface`.
- `provider_timeout` or `timeout`: increase the configured timeout or fix the
  blocked Agent CLI / model process before retrying.
- `failed_required_artifact`: inspect `.spec-grag/context/freshness.json` and
  rerun `spec-grag core --all` after the missing provider or service is fixed.

### Production Readiness Report Template

When reporting production-readiness work, use these exact sections and keep
smoke/default passing separate from real-service passing:

- 実装済み
- `none` / `fake` profile で passing
- `local-service` / `real-smoke` で passing
- skipped / 未実行
- 残 TODO
- 証跡

Do not report "本運用可能" while G-18 or any required T-R11 through T-R15 row
is still unchecked.

## Diagnostics Privacy

By default, run artifacts do not save LLM request prompt text, LLM response text,
or Source Specs full text. Diagnostics may store provider identity, timing, counts,
reason codes, retrieval ranking summaries, fusion method, embedding model, and
Qdrant collection metadata. The default template keeps:

```toml
[run]
save_artifacts = false
include_request = false
include_response = false
redact_payload = true
```

## Archive

`archive/full-grag-2026-05-05/` is historical reference material for the old full
GRAG version. It is not the current source of truth and should not be read as the
standard implementation path.
