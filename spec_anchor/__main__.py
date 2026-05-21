"""Module execution entrypoint for ``python -m spec_anchor``."""

from __future__ import annotations

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
