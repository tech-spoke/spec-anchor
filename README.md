# SPEC-grag

SPEC-grag is a specification workflow helper built around a JSON transport for
`/spec-core`, `/spec-inject`, and `/spec-realign`.

The current implementation is Python-first. Normal project setup renders a
production-oriented config that expects real providers such as Codex, Claude,
and Ollama. A separate `--smoke` setup mode exists only for CI and
fresh-install wiring checks without external providers.

## System Setup

Inspect the local toolchain and required distribution files:

```bash
python3 scripts/setup_system.py --check-only
```

Install the package in editable mode:

```bash
python3 scripts/setup_system.py --mode editable
```

Build a local distribution archive that includes templates and setup scripts:

```bash
python3 scripts/setup_system.py --mode archive
```

## Project Setup

Install SPEC-grag templates into a target project:

```bash
python3 scripts/setup_project.py --target /path/to/project
```

After a wheel or pip install, use the packaged console entrypoint:

```bash
spec-grag-setup-project --target /path/to/project
```

The default config uses `schema_llm` extraction, the project-level `[llm]`
provider switch (`codex_cli` by default), and Ollama `bge-m3` embeddings.
Change `[llm].provider` or pass `--llm-provider claude_cli` to switch all
LLM-backed stages together.

Preview without writing files:

```bash
python3 scripts/setup_project.py --target /path/to/project --dry-run
```

Create a no-dependency smoke setup in a fresh project:

```bash
python3 scripts/setup_project.py --target /path/to/project --smoke --create-example-spec
```

`--smoke` is for command wiring and package checks only; it is not a
production-quality GraphRAG run mode.

Existing files are not overwritten by default. Use `--backup` to keep `.bak`
copies or `--force` to replace changed files.

Useful non-interactive options:

```bash
python3 scripts/setup_project.py \
  --target /path/to/project \
  --source-include "docs/spec/**/*.md" \
  --graph-storage ".spec-grag/graph/" \
  --embedding-provider ollama \
  --llm-provider codex_cli \
  --codex-model gpt-5.4
```

The Claude template uses the Claude Code full model name
`claude-sonnet-4-6`; short aliases such as `sonnet` are accepted by Claude
Code but are not pinned.

## Commands

After setup, use the console wrapper from the project root:

```bash
spec-grag-slash spec-core --all
spec-grag-slash spec-inject "task or current user message"
spec-grag-slash spec-realign "task prompt"
```

Concept diff operations:

```bash
spec-grag-slash spec-core --accept <diff_id>:<hunk_id>
spec-grag-slash spec-core --reject <diff_id>:<hunk_id>
spec-grag-slash spec-core --revise <diff_id>:<hunk_id> "instruction"
spec-grag-slash spec-core --apply <diff_id>
```

If the console script is not on `PATH`, use:

```bash
python3 -m spec_grag.slash spec-core --all
```

Runtime graph, run artifacts, and pending Concept diffs live under
`.spec-grag/`. The template installs `.spec-grag/.gitignore` so generated
`graph/`, `runs/`, and `pending/` state stays out of git while
`.spec-grag/config.toml` and `.codex/commands/*.md` remain commit candidates.
