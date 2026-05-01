#!/usr/bin/env python3
"""Repository-local entry point for the SPEC-grag slash wrapper."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spec_grag.slash import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
