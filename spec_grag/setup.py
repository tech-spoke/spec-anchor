"""Public setup helper aliases for SPEC-grag."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_grag.project_setup import (
    run_smoke_checks,
    setup_project as _setup_project,
    setup_system as _setup_system,
)


def setup_project(
    target: str | Path = ".",
    *,
    agent: str = "both",
    dry_run: bool = False,
    force: bool = False,
    no_init_core_files: bool = False,
) -> dict[str, Any]:
    return _setup_project(
        target,
        agent=agent,
        dry_run=dry_run,
        force=force,
        no_init_core_files=no_init_core_files,
    )


def run_setup_project(
    target: str | Path = ".",
    *,
    agent: str = "both",
    dry_run: bool = False,
    force: bool = False,
    no_init_core_files: bool = False,
) -> dict[str, Any]:
    return setup_project(
        target,
        agent=agent,
        dry_run=dry_run,
        force=force,
        no_init_core_files=no_init_core_files,
    )


def setup_system(
    *,
    check_only: bool = False,
    mode: str = "editable",
    run_smoke: bool = False,
) -> dict[str, Any]:
    return _setup_system(check_only=check_only, mode=mode, run_smoke=run_smoke)


def run_setup_system(
    *,
    check_only: bool = False,
    mode: str = "editable",
    run_smoke: bool = False,
) -> dict[str, Any]:
    return setup_system(check_only=check_only, mode=mode, run_smoke=run_smoke)


__all__ = [
    "run_smoke_checks",
    "run_setup_project",
    "run_setup_system",
    "setup_project",
    "setup_system",
]
