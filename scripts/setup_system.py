#!/usr/bin/env python3
"""Prepare or inspect a local SPEC-grag system installation."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = REPO_ROOT / "dist" / "spec-grag-distribution.tar.gz"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="setup_system.py")
    parser.add_argument(
        "--mode",
        choices=["none", "editable", "wheel", "archive"],
        default="none",
        help="setup action to run",
    )
    parser.add_argument("--check-only", action="store_true", help="only inspect prerequisites")
    parser.add_argument("--dry-run", action="store_true", help="show planned commands only")
    parser.add_argument("--json", action="store_true", help="emit machine-readable summary")
    parser.add_argument("--archive-path", default=str(DEFAULT_ARCHIVE))
    parser.add_argument("--wheel-dir", default=str(REPO_ROOT / "dist" / "wheelhouse"))
    parser.add_argument("--run-smoke", action="store_true", help="run scripts/ci-smoke.sh")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = setup_system(args)
    emit_summary(summary, json_output=args.json)
    return 0 if summary["ok"] else 1


def setup_system(args: argparse.Namespace) -> dict[str, Any]:
    checks = collect_checks()
    actions: list[dict[str, Any]] = []
    warnings = list(checks["warnings"])
    errors = initial_errors_for_mode(checks["errors"], args)

    if not args.check_only:
        if args.mode == "editable":
            actions.append(run_or_plan(install_command(), dry_run=args.dry_run, cwd=REPO_ROOT))
        elif args.mode == "wheel":
            wheel_dir = Path(args.wheel_dir).expanduser().resolve()
            command = [sys.executable, "-m", "pip", "wheel", str(REPO_ROOT), "-w", str(wheel_dir)]
            actions.append(run_or_plan(command, dry_run=args.dry_run, cwd=REPO_ROOT))
        elif args.mode == "archive":
            archive_path = Path(args.archive_path).expanduser().resolve()
            actions.append(create_or_plan_archive(archive_path, dry_run=args.dry_run))

        if args.run_smoke:
            smoke_script = REPO_ROOT / "scripts" / "ci-smoke.sh"
            actions.append(run_or_plan([str(smoke_script)], dry_run=args.dry_run, cwd=REPO_ROOT))

    editable_installed = (
        not args.check_only
        and args.mode == "editable"
        and not args.dry_run
        and actions
        and actions[0].get("returncode") == 0
    )
    if editable_installed:
        checks = collect_checks()
        warnings = list(checks["warnings"])
        errors = list(checks["errors"])

    for action in actions:
        if action.get("returncode", 0) != 0:
            errors.append(f"action_failed:{action.get('label', action.get('command'))}")

    ok = not errors
    return {
        "ok": ok,
        "repo_root": str(REPO_ROOT),
        "dry_run": bool(args.dry_run),
        "check_only": bool(args.check_only),
        "mode": args.mode,
        "checks": checks,
        "actions": actions,
        "warnings": warnings,
        "errors": errors,
    }


def collect_checks() -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    python_ok = sys.version_info >= (3, 12)
    if not python_ok:
        errors.append("python_version_lt_3_12")

    uv_path = shutil.which("uv")
    if uv_path is None:
        warnings.append("uv_missing")

    spec_grag_path = shutil.which("spec-grag")
    if spec_grag_path is None:
        warnings.append("console_script_missing:spec-grag")

    slash_path = shutil.which("spec-grag-slash")
    if slash_path is None:
        warnings.append("console_script_missing:spec-grag-slash")

    module_cli_ok = module_help_ok("spec_grag.cli")
    module_slash_ok = module_help_ok("spec_grag.slash")
    if not module_cli_ok:
        errors.append("python_module_unavailable:spec_grag.cli")
    if not module_slash_ok:
        errors.append("python_module_unavailable:spec_grag.slash")

    required_files = [
        "templates/.spec-grag/config.toml",
        "templates/.codex/commands/spec-core.md",
        "templates/.codex/commands/spec-inject.md",
        "templates/.codex/commands/spec-realign.md",
        "scripts/spec-grag-slash.py",
        "scripts/setup_project.py",
        "README.md",
    ]
    missing_files = [path for path in required_files if not (REPO_ROOT / path).exists()]
    if missing_files:
        errors.append("required_distribution_files_missing")

    return {
        "python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
            "ok": python_ok,
        },
        "uv": uv_path,
        "spec_grag": spec_grag_path,
        "spec_grag_slash": slash_path,
        "codex": shutil.which("codex"),
        "claude": shutil.which("claude"),
        "ollama": shutil.which("ollama"),
        "python_module_cli": module_cli_ok,
        "python_module_slash": module_slash_ok,
        "required_files": required_files,
        "missing_files": missing_files,
        "warnings": warnings,
        "errors": errors,
    }


def initial_errors_for_mode(errors: list[str], args: argparse.Namespace) -> list[str]:
    if args.check_only or args.mode == "none":
        return list(errors)
    return [
        error
        for error in errors
        if not error.startswith("python_module_unavailable:")
    ]


def module_help_ok(module: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def install_command() -> list[str]:
    return [sys.executable, "-m", "pip", "install", "-e", str(REPO_ROOT)]


def run_or_plan(command: list[str], *, dry_run: bool, cwd: Path) -> dict[str, Any]:
    if dry_run:
        return {
            "label": Path(command[0]).name,
            "command": command,
            "cwd": str(cwd),
            "dry_run": True,
            "returncode": 0,
        }
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "label": Path(command[0]).name,
        "command": command,
        "cwd": str(cwd),
        "dry_run": False,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def create_or_plan_archive(archive_path: Path, *, dry_run: bool) -> dict[str, Any]:
    include_roots = [
        "README.md",
        "pyproject.toml",
        "spec_grag",
        "scripts",
        "templates",
        "doc",
    ]
    if dry_run:
        return {
            "label": "archive",
            "archive_path": str(archive_path),
            "include": include_roots,
            "dry_run": True,
            "returncode": 0,
        }

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as tar:
        for relative in include_roots:
            path = REPO_ROOT / relative
            if path.exists():
                tar.add(path, arcname=f"spec-grag/{relative}")
    return {
        "label": "archive",
        "archive_path": str(archive_path),
        "include": include_roots,
        "dry_run": False,
        "returncode": 0,
    }


def emit_summary(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print(f"repo_root: {summary['repo_root']}")
    print(f"mode: {summary['mode']}")
    print(f"dry_run: {summary['dry_run']}")
    for warning in summary["warnings"]:
        print(f"warning: {warning}")
    for error in summary["errors"]:
        print(f"error: {error}")
    for action in summary["actions"]:
        label = action.get("label", "action")
        print(f"{label}: returncode={action.get('returncode')}")
    print("ok" if summary["ok"] else "failed")


if __name__ == "__main__":
    raise SystemExit(main())
