"""Setup helpers for SPEC-anchor project and system entrypoints."""

from __future__ import annotations

import difflib
import importlib.metadata
import importlib.resources
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


PROJECT_TEMPLATE_ROOT = "templates"
MANAGED_COMMANDS = ("spec-core.md", "spec-inject.md", "spec-realign.md")
MANAGED_CONSOLE_SCRIPTS = (
    "spec-anchor",
    "spec-anchor-slash",
    "spec-anchor-watch",
    "spec-anchor-setup-project",
    "spec-anchor-setup-system",
)
MANAGED_TEMPLATE_PATHS = (
    "templates/.codex/skills/spec-anchor/SKILL.md",
    "templates/.claude/commands/spec-core.md",
    "templates/.claude/commands/spec-inject.md",
    "templates/.claude/commands/spec-realign.md",
    "templates/.spec-anchor/config.toml",
    "templates/.spec-anchor/.gitignore",
)


def setup_project(
    target: str | Path = ".",
    *,
    agent: str = "both",
    dry_run: bool = False,
    force: bool = False,
    no_init_core_files: bool = False,
) -> dict[str, Any]:
    """Create or update SPEC-anchor project files under an existing project root."""

    target_path = Path(target).expanduser()
    result = _base_project_result(
        target_path,
        agent,
        dry_run,
        force,
        no_init_core_files,
    )

    if agent not in {"codex", "claude", "both"}:
        return _error_result(result, "invalid_agent", f"unsupported agent: {agent}")
    if not target_path.exists():
        return _error_result(
            result,
            "target_not_found",
            "target does not exist; create it explicitly before running setup",
        )
    if not target_path.is_dir():
        return _error_result(result, "target_not_directory", "target is not a directory")

    root = target_path.resolve()
    result["target"] = str(root)
    result["codex_skill_path"] = _path_label(
        root,
        _codex_skill_destination(root),
    )

    entries = _project_file_entries(
        agent,
        root=root,
        init_core_files=not no_init_core_files,
    )
    protected_core_paths = (
        _protected_core_paths(root)
        if not no_init_core_files
        else set()
    )
    operations: list[dict[str, str]] = []

    for rel_path, content in entries:
        destination = _project_destination(root, rel_path)
        rel_name = _path_label(root, destination)
        is_protected_core_path = (
            _resolve_project_path(root, destination) in protected_core_paths
        )

        if destination.exists() and not destination.is_file():
            result["conflicts"].append(
                {
                    "path": rel_name,
                    "reason": "destination_exists_and_is_not_file",
                }
            )
            continue

        if (destination.exists() or destination.is_symlink()) and is_protected_core_path:
            _add_protected_core_skip(result, rel_name, force)
            continue

        if not destination.exists():
            result["created"].append(rel_name)
            operations.append(
                {
                    "action": "create",
                    "path": rel_name,
                    "destination": destination.as_posix(),
                    "content": content,
                }
            )
            continue

        try:
            existing = destination.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            result["conflicts"].append(
                {"path": rel_name, "reason": "existing_file_is_not_utf8_text"}
            )
            continue

        if existing == content:
            result["skipped"].append(rel_name)
            continue

        if force:
            result["updated"].append(rel_name)
            operations.append(
                {
                    "action": "update",
                    "path": rel_name,
                    "destination": destination.as_posix(),
                    "content": content,
                }
            )
            continue

        result["conflicts"].append(
            {
                "path": rel_name,
                "reason": "would_overwrite_existing_file",
                "diff": _unified_diff(existing, content, rel_name),
            }
        )

    if no_init_core_files:
        _add_no_init_core_diagnostic(
            root,
            result,
            config_text=_config_text_after_planned_operations(root, operations),
        )

    if result["conflicts"]:
        result["status"] = "conflict"
        result["applied"] = False
        result["exit_code"] = 1
        return result

    if dry_run:
        result["status"] = "dry_run"
        result["applied"] = False
        result["exit_code"] = 0
        return result

    for operation in operations:
        destination = Path(operation["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(operation["content"], encoding="utf-8")

    result["status"] = "ok"
    result["applied"] = True
    result["exit_code"] = 0
    return result


def run_setup_project(
    target: str | Path = ".",
    *,
    agent: str = "both",
    dry_run: bool = False,
    force: bool = False,
    no_init_core_files: bool = False,
) -> dict[str, Any]:
    """Compatibility alias for callers that prefer an action-style name."""

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
    qdrant_url: str | None = None,
) -> dict[str, Any]:
    """Check or lightly prepare the SPEC-anchor installation."""

    result: dict[str, Any] = {
        "status": "ok",
        "mode": mode,
        "check_only": check_only,
        "prepared": [],
        "actions": [],
        "created": [],
        "updated": [],
        "skipped": [],
        "conflicts": [],
        "diagnostics": [],
        "console_scripts": _check_console_scripts(),
        "templates": _check_packaged_templates(),
        "providers": _check_providers(qdrant_url=qdrant_url),
        "agent_cli_entries": _agent_cli_entry_checks(),
        "smoke": {"executed": False, "skipped": True},
    }
    result["production_readiness"] = _production_readiness(
        providers=result["providers"],
        console_scripts=result["console_scripts"],
    )

    _add_availability_diagnostics(result)
    _add_agent_cli_entry_diagnostics(result)

    if mode not in {"editable", "archive", "install"}:
        result["status"] = "error"
        result["diagnostics"].append(
            {
                "reason_code": "invalid_mode",
                "severity": "error",
                "message": f"unsupported setup mode: {mode}",
            }
        )

    result["actions"] = _system_setup_actions(
        mode=mode,
        check_only=check_only,
        console_scripts=result["console_scripts"],
        templates=result["templates"],
        providers=result["providers"],
        run_smoke=run_smoke,
    )

    if run_smoke:
        smoke = run_smoke_checks()
        result["smoke"] = smoke
        _record_smoke_action(result["actions"], smoke)
        if not smoke["passed"]:
            result["status"] = "failed"

    result["prepared"] = [
        action for action in result["actions"] if action.get("status") == "prepared"
    ]
    result["skipped"] = [
        action for action in result["actions"] if action.get("status") == "skipped"
    ]

    if result["status"] == "ok" and any(
        item["severity"] == "warning" for item in result["diagnostics"]
    ):
        result["status"] = "degraded"

    result["exit_code"] = 1 if result["status"] in {"error", "failed"} else 0
    return result


def run_setup_system(
    *,
    check_only: bool = False,
    mode: str = "editable",
    run_smoke: bool = False,
) -> dict[str, Any]:
    """Compatibility alias for callers that prefer an action-style name."""

    return setup_system(check_only=check_only, mode=mode, run_smoke=run_smoke)


def run_smoke_checks() -> dict[str, Any]:
    """Run explicit, local smoke checks without touching the caller's project."""

    checks: list[dict[str, Any]] = []
    repo_root = Path(__file__).resolve().parents[1]

    help_result = subprocess.run(
        [sys.executable, "-m", "spec_anchor", "--help"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    checks.append(
        {
            "name": "python_module_help",
            "passed": help_result.returncode == 0 and "usage" in help_result.stdout.lower(),
            "returncode": help_result.returncode,
        }
    )

    with tempfile.TemporaryDirectory(prefix="spec-anchor-smoke-") as tmp:
        project_result = setup_project(
            tmp,
            agent="codex",
            dry_run=False,
            force=False,
            no_init_core_files=True,
        )
        checks.append(
            {
                "name": "project_setup_temp",
                "passed": project_result["status"] == "ok",
                "status": project_result["status"],
            }
        )

    return {
        "executed": True,
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }


def result_exit_code(result: dict[str, Any], *, system_setup: bool = False) -> int:
    """Map setup result status to a CLI exit code."""

    if result["status"] in {"error", "conflict", "failed"}:
        return int(result.get("exit_code", 1))
    if system_setup:
        return 0
    return 0


def _base_project_result(
    target: Path,
    agent: str,
    dry_run: bool,
    force: bool,
    no_init_core_files: bool,
) -> dict[str, Any]:
    return {
        "status": "pending",
        "target": str(target),
        "agent": agent,
        "dry_run": dry_run,
        "force": force,
        "no_init_core_files": no_init_core_files,
        "codex_skill_path": None,
        "applied": False,
        "exit_code": 0,
        "created": [],
        "updated": [],
        "skipped": [],
        "protected": [],
        "conflicts": [],
        "diagnostics": [],
        "missing_core_files": [],
    }


def _error_result(result: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    result["status"] = "error"
    result["applied"] = False
    result["exit_code"] = 1
    result["diagnostics"].append(
        {
            "reason_code": code,
            "severity": "error",
            "message": message,
        }
    )
    return result


def _project_file_entries(
    agent: str,
    *,
    root: Path,
    init_core_files: bool,
) -> list[tuple[Path, str]]:
    entries = [
        (Path(".spec-anchor/config.toml"), _template_text(".spec-anchor/config.toml")),
        (Path(".spec-anchor/.gitignore"), _template_text(".spec-anchor/.gitignore")),
    ]

    if agent in {"claude", "both"}:
        for command_name in MANAGED_COMMANDS:
            entries.append(
                (
                    Path(f".claude/commands/{command_name}"),
                    _template_text(f".claude/commands/{command_name}"),
                )
            )

    if agent in {"codex", "both"}:
        entries.append(
            (
                _codex_skill_destination(root),
                _template_text(".codex/skills/spec-anchor/SKILL.md"),
            )
        )

    if init_core_files:
        core_paths = _core_paths_from_config_template()
        entries.extend(
            [
                (core_paths["purpose_file"], _purpose_placeholder()),
                (core_paths["concept_file"], _concept_placeholder()),
            ]
        )

    return entries


def _selected_agents(agent: str) -> Iterable[str]:
    if agent == "both":
        return ("codex", "claude")
    return (agent,)


def _codex_skill_destination(root: Path) -> Path:
    return root / ".codex" / "skills" / "spec-anchor" / "SKILL.md"


def _path_label(root: Path, path: Path) -> str:
    destination = _project_destination(root, path)
    try:
        return destination.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return destination.as_posix()


def _template_text(relative_path: str) -> str:
    resource = importlib.resources.files("spec_anchor").joinpath(
        PROJECT_TEMPLATE_ROOT,
        *Path(relative_path).parts,
    )
    return resource.read_text(encoding="utf-8")


def _core_paths_from_config_template() -> dict[str, Path]:
    raw = tomllib.loads(_template_text(".spec-anchor/config.toml"))
    return _core_paths_from_config(raw)


def _core_paths_from_project_or_template(root: Path) -> dict[str, Path]:
    config_path = root / ".spec-anchor" / "config.toml"
    if config_path.is_file():
        try:
            raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
            return _core_paths_from_config(raw)
        except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
            pass
    return _core_paths_from_config_template()


def _core_paths_from_config(raw: dict[str, Any]) -> dict[str, Path]:
    core = raw["core"]
    return {
        "purpose_file": Path(core["purpose_file"]),
        "concept_file": Path(core["concept_file"]),
    }


def _protected_core_paths(root: Path) -> set[Path]:
    core_paths = list(_core_paths_from_project_or_template(root).values())
    core_paths.extend(_core_paths_from_config_template().values())
    return {
        _resolve_project_path(root, path)
        for path in core_paths
    }


def _project_destination(root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return root / path


def _resolve_project_path(root: Path, path: Path) -> Path:
    return _project_destination(root, path).resolve(strict=False)


def _config_text_after_planned_operations(
    root: Path,
    operations: list[dict[str, str]],
) -> str | None:
    for operation in operations:
        if operation["path"] == ".spec-anchor/config.toml":
            return operation["content"]

    config_path = root / ".spec-anchor" / "config.toml"
    if not config_path.is_file():
        return None
    try:
        return config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _add_protected_core_skip(
    result: dict[str, Any],
    rel_name: str,
    force: bool,
) -> None:
    result["skipped"].append(rel_name)
    result["protected"].append(rel_name)
    result["diagnostics"].append(
        {
            "reason_code": "human_owned_core_file_protected",
            "severity": "info",
            "message": "Human-owned Purpose / Core Concept file was left unchanged.",
            "path": rel_name,
            "force": force,
        }
    )


def _purpose_placeholder() -> str:
    return (
        "# Purpose\n"
        "\n"
        "Write the human-maintained purpose of this project here.\n"
        "\n"
        "SPEC-anchor never updates this file automatically.\n"
    )


def _concept_placeholder() -> str:
    return (
        "# Core Concept\n"
        "\n"
        "Write the human-maintained core concepts and invariants here.\n"
        "\n"
        "SPEC-anchor never updates this file automatically.\n"
    )


def _add_no_init_core_diagnostic(
    root: Path,
    result: dict[str, Any],
    *,
    config_text: str | None,
) -> None:
    core_paths = _core_paths_from_config_text_or_project_or_template(root, config_text)
    missing = [
        path.as_posix()
        for path in core_paths.values()
        if not _project_destination(root, path).is_file()
    ]
    result["missing_core_files"] = missing
    if not missing:
        return
    result["diagnostics"].append(
        {
            "reason_code": "core_files_not_initialized",
            "severity": "warning",
            "message": (
                "Purpose / Core Concept placeholders were not created; "
                "after setup, /spec-core fails until a human creates the "
                "configured core files."
            ),
            "missing_core_files": missing,
        }
    )


def _core_paths_from_config_text_or_project_or_template(
    root: Path,
    config_text: str | None,
) -> dict[str, Path]:
    if config_text is not None:
        try:
            return _core_paths_from_config(tomllib.loads(config_text))
        except (KeyError, TypeError, tomllib.TOMLDecodeError):
            pass
    return _core_paths_from_project_or_template(root)


def _unified_diff(existing: str, desired: str, rel_name: str) -> str:
    diff = difflib.unified_diff(
        existing.splitlines(),
        desired.splitlines(),
        fromfile=f"{rel_name} (existing)",
        tofile=f"{rel_name} (template)",
        lineterm="",
    )
    return "\n".join(diff)


def _check_console_scripts() -> list[dict[str, Any]]:
    return [
        {
            "name": command,
            "available": shutil.which(command) is not None,
            "path": shutil.which(command),
        }
        for command in MANAGED_CONSOLE_SCRIPTS
    ]


def _check_packaged_templates() -> list[dict[str, Any]]:
    package_root = importlib.resources.files("spec_anchor")
    return [
        {
            "path": template_path,
            "available": package_root.joinpath(*Path(template_path).parts).is_file(),
        }
        for template_path in MANAGED_TEMPLATE_PATHS
    ]


def _agent_cli_entry_checks() -> dict[str, Any]:
    return {
        "codex": {
            "cli": _command_check("codex", "agent_cli", required=False),
            "project_skill_path": "<project>/.codex/skills/spec-anchor/SKILL.md",
        },
        "claude": {
            "cli": _command_check("claude", "agent_cli", required=False),
            "project_command_path": "<project>/.claude/commands/spec-{core,inject,realign}.md",
        },
    }


def _check_providers(*, qdrant_url: str | None = None) -> list[dict[str, Any]]:
    providers = [
        _python_package_check("FlagEmbedding", "embedding_provider", required=False),
        _python_package_check("qdrant_client", "vector_store_client", required=False),
        _command_check("codex", "agent_cli", required=False),
        _command_check("claude", "agent_cli", required=False),
        _qdrant_service_check(qdrant_url=qdrant_url),
    ]
    return providers


def _python_package_check(name: str, kind: str, *, required: bool) -> dict[str, Any]:
    try:
        available = importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        available = False
    return {
        "name": name,
        "kind": kind,
        "available": available,
        "version": _package_version(name) if available else None,
        "required": required,
    }


def _command_check(name: str, kind: str, *, required: bool) -> dict[str, Any]:
    path = shutil.which(name)
    return {
        "name": name,
        "kind": kind,
        "available": path is not None,
        "path": path,
        "version": _command_version(path) if path else None,
        "required": required,
    }


def _qdrant_service_check(*, qdrant_url: str | None = None) -> dict[str, Any]:
    base_url = (qdrant_url or os.environ.get("SPEC_ANCHOR_QDRANT_URL") or "http://localhost:6333").rstrip("/")
    url = f"{base_url}/"
    version = None
    try:
        with urllib.request.urlopen(url, timeout=0.2) as response:
            available = 200 <= response.status < 500
            raw = response.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                version = payload.get("version")
            error = None
    except (OSError, urllib.error.URLError, ValueError) as exc:
        available = False
        error = exc.__class__.__name__

    return {
        "name": "qdrant",
        "kind": "vector_store_service",
        "available": available,
        "url": base_url,
        "version": str(version) if version else None,
        "required": False,
        "error": error,
    }


def _production_readiness(
    *,
    providers: list[dict[str, Any]],
    console_scripts: list[dict[str, Any]],
) -> dict[str, Any]:
    provider_by_name = {item["name"]: item for item in providers}
    script_by_name = {item["name"]: item for item in console_scripts}
    checks = [
        _readiness_check(
            "qdrant_service",
            bool(provider_by_name.get("qdrant", {}).get("available")),
            "qdrant_service_unavailable",
            provider_by_name.get("qdrant", {}),
        ),
        _readiness_check(
            "flagembedding_package",
            bool(provider_by_name.get("FlagEmbedding", {}).get("available")),
            "flagembedding_missing",
            provider_by_name.get("FlagEmbedding", {}),
        ),
        _readiness_check(
            "qdrant_client_package",
            bool(provider_by_name.get("qdrant_client", {}).get("available")),
            "qdrant_client_missing",
            provider_by_name.get("qdrant_client", {}),
        ),
        _readiness_check(
            "agent_cli",
            bool(provider_by_name.get("codex", {}).get("available"))
            or bool(provider_by_name.get("claude", {}).get("available")),
            "agent_cli_unavailable",
            {
                "codex": provider_by_name.get("codex", {}),
                "claude": provider_by_name.get("claude", {}),
            },
        ),
    ]
    script_checks = [
        _readiness_check(
            f"console_script:{name}",
            bool(script_by_name.get(name, {}).get("available")),
            "console_script_missing",
            script_by_name.get(name, {}),
        )
        for name in MANAGED_CONSOLE_SCRIPTS
    ]
    checks.extend(script_checks)
    blocking = [item for item in checks if item["status"] != "passed"]
    return {
        "status": "ready" if not blocking else "blocked",
        "checks": checks,
        "blocking_reasons": [item["reason_code"] for item in blocking],
        "qdrant_url": provider_by_name.get("qdrant", {}).get("url"),
        "qdrant_server_version": provider_by_name.get("qdrant", {}).get("version"),
        "flagembedding_version": provider_by_name.get("FlagEmbedding", {}).get("version"),
        "model_cache_dir": _model_cache_dir(),
    }


def _readiness_check(
    name: str,
    passed: bool,
    reason_code: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "reason_code": None if passed else reason_code,
        "details": dict(details or {}),
    }


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _command_version(path: str) -> str | None:
    try:
        completed = subprocess.run(
            [path, "--version"],
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else None


def _model_cache_dir() -> str:
    for name in ("HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE"):
        value = os.environ.get(name)
        if value:
            return value
    return str(Path.home() / ".cache" / "huggingface")


def _add_availability_diagnostics(result: dict[str, Any]) -> None:
    for script in result["console_scripts"]:
        if not script["available"]:
            result["diagnostics"].append(
                {
                    "reason_code": "console_script_missing",
                    "severity": "warning",
                    "message": f"console script is not on PATH: {script['name']}",
                    "name": script["name"],
                }
            )

    for template in result["templates"]:
        if not template["available"]:
            result["diagnostics"].append(
                {
                    "reason_code": "template_missing",
                    "severity": "error",
                    "message": f"packaged template is missing: {template['path']}",
                    "path": template["path"],
                }
            )
            result["status"] = "error"

    for provider in result["providers"]:
        if provider["available"]:
            continue
        severity = "error" if provider["required"] else "warning"
        result["diagnostics"].append(
            {
                "reason_code": "provider_unavailable",
                "severity": severity,
                "message": f"{provider['kind']} is unavailable: {provider['name']}",
                "name": provider["name"],
                "kind": provider["kind"],
            }
        )
        if severity == "error":
            result["status"] = "error"


def _add_agent_cli_entry_diagnostics(result: dict[str, Any]) -> None:
    entries = result.get("agent_cli_entries")
    if not isinstance(entries, Mapping):
        return
    codex = entries.get("codex")
    if isinstance(codex, Mapping):
        result["diagnostics"].append(
            {
                "reason_code": "codex_skill_entrypoint",
                "severity": "info",
                "message": (
                    "Codex uses skill entrypoints under <project>/.codex/skills/spec-anchor; "
                    "SPEC-anchor does not install .codex/commands for Codex."
                ),
                "project_skill_path": codex.get("project_skill_path"),
            }
        )
    claude = entries.get("claude")
    if isinstance(claude, Mapping):
        result["diagnostics"].append(
            {
                "reason_code": "claude_command_entrypoint",
                "severity": "info",
                "message": "Claude Code uses project command entrypoints under .claude/commands.",
                "project_command_path": claude.get("project_command_path"),
            }
        )


def _system_setup_actions(
    *,
    mode: str,
    check_only: bool,
    console_scripts: list[dict[str, Any]],
    templates: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    run_smoke: bool,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = [
        {
            "name": "console_scripts",
            "status": "checked",
            "available_count": sum(1 for item in console_scripts if item["available"]),
            "missing": [
                item["name"] for item in console_scripts if not item["available"]
            ],
        },
        {
            "name": "packaged_templates",
            "status": "checked",
            "available_count": sum(1 for item in templates if item["available"]),
            "missing": [
                item["path"] for item in templates if not item["available"]
            ],
        },
        {
            "name": "optional_providers",
            "status": "checked",
            "available": [item["name"] for item in providers if item["available"]],
            "unavailable": [
                item["name"] for item in providers if not item["available"]
            ],
        },
    ]

    if check_only:
        actions.append(
            {
                "name": "mode_preparation",
                "mode": mode,
                "status": "skipped",
                "reason": "check_only",
            }
        )
    else:
        actions.append(_mode_preparation_action(mode))
        actions.append(
            {
                "name": "heavy_install",
                "mode": mode,
                "status": "skipped",
                "reason": "no implicit pip install or external service bootstrap",
            }
        )

    if not run_smoke:
        actions.append(
            {
                "name": "smoke_checks",
                "status": "skipped",
                "reason": "run_smoke_not_requested",
            }
        )

    return actions


def _mode_preparation_action(mode: str) -> dict[str, Any]:
    if mode == "editable":
        return {
            "name": "editable_environment",
            "mode": mode,
            "status": "prepared",
            "prepared": [
                "source package import path checked",
                "console script definitions checked",
                "packaged templates checked",
            ],
        }
    if mode == "archive":
        return {
            "name": "archive_distribution",
            "mode": mode,
            "status": "prepared",
            "prepared": [
                "package data presence checked",
                "archive mode does not modify project files",
            ],
        }
    if mode == "install":
        return {
            "name": "installed_environment",
            "mode": mode,
            "status": "prepared",
            "prepared": [
                "package metadata checked",
                "console script availability checked",
            ],
        }
    return {
        "name": "mode_preparation",
        "mode": mode,
        "status": "skipped",
        "reason": "invalid_mode",
    }


def _record_smoke_action(
    actions: list[dict[str, Any]],
    smoke: dict[str, Any],
) -> None:
    actions.append(
        {
            "name": "smoke_checks",
            "status": "checked",
            "executed": True,
            "passed": smoke["passed"],
        }
    )


def dumps_result(result: dict[str, Any]) -> str:
    """Serialize setup results for console output."""

    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
