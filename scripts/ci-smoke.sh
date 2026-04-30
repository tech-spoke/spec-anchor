#!/usr/bin/env bash
set -euo pipefail

uv run --isolated --with pytest pytest -q
uv run --isolated --with pytest --with pydantic --with llama-index-core --with markdown-it-py python scripts/performance_smoke.py
uv run --isolated --with pytest --with pydantic --with llama-index-core --with markdown-it-py python scripts/real_docs_smoke.py
