#!/usr/bin/env python3
"""Install SPEC-grag project templates into a target repository."""

from __future__ import annotations

import argparse
import json
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from spec_grag.template_resources import project_template_root

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE_INCLUDE = ["docs/spec/**/*.md"]
DEFAULT_SOURCE_EXCLUDE: list[str] = []
DEFAULT_PURPOSE_FILE = "docs/core/purpose.md"
DEFAULT_CONCEPT_FILE = "docs/core/concept.md"
DEFAULT_GRAPH_STORAGE = ".spec-grag/graph/"

PURPOSE_TEMPLATE = """# Purpose

Describe the product goal, non-negotiable outcomes, and constraints that should
guide specification changes.
"""

CONCEPT_TEMPLATE = """# Concept

Capture stable architecture principles and recurring terms here. SPEC-grag may
propose guarded updates through pending Concept diffs.
"""

EXAMPLE_SPEC_TEMPLATE = """# Example Spec

This file gives SPEC-grag an initial source document for smoke tests.

## System Goal

The system should keep project purpose, concept, and detailed specifications in
sync before making implementation decisions.
"""


@dataclass(frozen=True)
class PlannedFile:
    relative_path: Path
    content: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="setup_project.py")
    parser.add_argument("--target", default=".", help="target project root")
    parser.add_argument("--template-root", help="override template directory")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "render a no-dependency CI/fresh-install smoke config; this is not "
            "a production-quality project profile"
        ),
    )
    parser.add_argument("--force", action="store_true", help="overwrite changed files")
    parser.add_argument(
        "--backup",
        action="store_true",
        help="backup changed files before replacing them",
    )
    parser.add_argument("--dry-run", action="store_true", help="show actions only")
    parser.add_argument("--json", action="store_true", help="emit machine-readable summary")
    parser.add_argument(
        "--source-include",
        action="append",
        dest="source_includes",
        help="source glob to add; may be repeated",
    )
    parser.add_argument(
        "--source-exclude",
        action="append",
        dest="source_excludes",
        help="source exclude glob to add; may be repeated",
    )
    parser.add_argument("--purpose-file", default=DEFAULT_PURPOSE_FILE)
    parser.add_argument("--concept-file", default=DEFAULT_CONCEPT_FILE)
    parser.add_argument("--graph-storage", default=DEFAULT_GRAPH_STORAGE)
    parser.add_argument(
        "--embedding-provider",
        choices=["stable_hash", "ollama"],
        default=None,
    )
    parser.add_argument("--embedding-model")
    parser.add_argument("--embedding-dimension", type=int)
    parser.add_argument(
        "--llm-provider",
        choices=["codex_cli", "claude_cli"],
        default=None,
        help="production LLM provider switch written to [llm].provider",
    )
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument("--codex-model", default="gpt-5.4")
    parser.add_argument(
        "--codex-effort",
        choices=["minimal", "low", "medium", "high", "xhigh"],
        default="low",
    )
    parser.add_argument("--claude-command", default="claude")
    parser.add_argument("--claude-model", default="claude-sonnet-4-6")
    parser.add_argument(
        "--claude-effort",
        choices=["low", "medium", "high", "xhigh", "max"],
        default="low",
    )
    parser.add_argument(
        "--extraction-mode",
        choices=["deterministic", "schema_llm", "schema", "llm"],
        default=None,
    )
    parser.add_argument(
        "--answer-provider",
        choices=["template", "deterministic", "none", "disabled", "codex", "claude"],
        default=None,
        help="smoke/fallback-only stage provider override; use --llm-provider in production",
    )
    parser.add_argument(
        "--answer-failure-fallback",
        choices=["failed", "template"],
        default=None,
    )
    parser.add_argument(
        "--classification-provider",
        choices=["orchestrator_rule_based", "rule_based", "codex", "claude"],
        default=None,
        help="smoke/fallback-only stage provider override; use --llm-provider in production",
    )
    parser.add_argument(
        "--concept-diff-provider",
        choices=["source_derived", "template", "none", "disabled", "codex", "claude"],
        default=None,
        help="smoke/fallback-only stage provider override; use --llm-provider in production",
    )
    parser.add_argument(
        "--query-planner-provider",
        choices=["template", "deterministic", "none", "disabled", "codex", "claude"],
        default=None,
        help="smoke/fallback-only stage provider override; use --llm-provider in production",
    )
    parser.add_argument(
        "--create-core-docs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="create missing Purpose and Concept files",
    )
    parser.add_argument(
        "--create-example-spec",
        action="store_true",
        help="create docs/spec/example.md when missing",
    )
    parser.add_argument(
        "--validate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="validate rendered config and installed files",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.force and args.backup:
        parser.error("--force and --backup are mutually exclusive")
    if not args.smoke and any(
        value is not None
        for value in (
            args.answer_provider,
            args.classification_provider,
            args.concept_diff_provider,
            args.query_planner_provider,
        )
    ):
        parser.error(
            "use --llm-provider for production LLM switching; stage provider "
            "flags are smoke/fallback-only"
        )

    target = Path(args.target).expanduser().resolve()
    if args.template_root:
        template_root = Path(args.template_root).expanduser().resolve()
        summary = install_project(args, target=target, template_root=template_root)
    else:
        with project_template_root(REPO_ROOT / "templates") as template_root:
            summary = install_project(args, target=target, template_root=template_root)
    emit_summary(summary, json_output=args.json)
    return 0 if summary["ok"] else 1


def install_project(
    args: argparse.Namespace,
    *,
    target: Path,
    template_root: Path,
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not template_root.exists():
        return {
            "ok": False,
            "target": str(target),
            "template_root": str(template_root),
            "smoke": bool(args.smoke),
            "dry_run": bool(args.dry_run),
            "actions": [],
            "conflicts": [],
            "warnings": [f"template_root_missing:{template_root}"],
            "checks": {},
        }

    planned_files = list(planned_template_files(args, template_root))
    if args.create_core_docs:
        planned_files.extend(core_doc_files(args))
    if args.create_example_spec:
        planned_files.append(PlannedFile(Path("docs/spec/example.md"), EXAMPLE_SPEC_TEMPLATE))

    if not args.dry_run:
        target.mkdir(parents=True, exist_ok=True)

    for planned in planned_files:
        install_one_file(
            target=target,
            planned=planned,
            force=bool(args.force),
            backup=bool(args.backup),
            dry_run=bool(args.dry_run),
            actions=actions,
            conflicts=conflicts,
        )

    checks: dict[str, Any] = {}
    if args.validate:
        checks = validate_install(
            target,
            planned_files,
            dry_run=bool(args.dry_run),
            smoke=bool(args.smoke),
        )
        if not checks.get("ok", False):
            warnings.extend(checks.get("warnings", []))

    ok = not conflicts and (not checks or checks.get("ok", False))
    return {
        "ok": ok,
        "target": str(target),
        "template_root": str(template_root),
        "smoke": bool(args.smoke),
        "dry_run": bool(args.dry_run),
        "actions": actions,
        "conflicts": conflicts,
        "warnings": warnings,
        "checks": checks,
    }


def planned_template_files(
    args: argparse.Namespace,
    template_root: Path,
) -> Iterable[PlannedFile]:
    for path in sorted(template_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(template_root)
        if relative == Path(".spec-grag/config.toml"):
            yield PlannedFile(relative, render_config(args))
        else:
            yield PlannedFile(relative, path.read_text(encoding="utf-8"))


def core_doc_files(args: argparse.Namespace) -> list[PlannedFile]:
    return [
        PlannedFile(Path(args.purpose_file), PURPOSE_TEMPLATE),
        PlannedFile(Path(args.concept_file), CONCEPT_TEMPLATE),
    ]


def render_config(args: argparse.Namespace) -> str:
    includes = args.source_includes or DEFAULT_SOURCE_INCLUDE
    excludes = args.source_excludes if args.source_excludes is not None else DEFAULT_SOURCE_EXCLUDE
    extraction_mode = choose_provider(
        args.extraction_mode,
        "deterministic",
        "schema_llm",
        args.smoke,
    )
    embedding_provider = choose_provider(
        args.embedding_provider,
        "stable_hash",
        "ollama",
        args.smoke,
    )
    answer_provider = choose_provider(
        args.answer_provider,
        "template",
        "codex",
        args.smoke,
    )
    answer_failure_fallback = choose_provider(
        args.answer_failure_fallback,
        "template",
        "failed",
        args.smoke,
    )
    classification_provider = choose_provider(
        args.classification_provider,
        "orchestrator_rule_based",
        "codex",
        args.smoke,
    )
    concept_diff_provider = choose_provider(
        args.concept_diff_provider,
        "source_derived",
        "codex",
        args.smoke,
    )
    query_planner_provider = choose_provider(
        args.query_planner_provider,
        "template",
        "codex",
        args.smoke,
    )
    llm_provider = args.llm_provider or "codex_cli"
    llm_block = render_llm_block(args, provider=llm_provider)
    if args.smoke:
        llm_block = ""
    extraction_provider_blocks = (
        ""
        if args.smoke
        else """
[extraction.codex]
model = "gpt-5.4-mini"
effort = "low"

[extraction.claude]
model = "claude-haiku-4-5"
effort = "low"
"""
    )
    extraction_provider_line = stage_provider_line("codex", smoke=args.smoke)
    answer_provider_line = stage_provider_line(answer_provider, smoke=args.smoke)
    classification_provider_line = stage_provider_line(
        classification_provider,
        smoke=args.smoke,
    )
    concept_diff_provider_line = stage_provider_line(
        concept_diff_provider,
        smoke=args.smoke,
    )
    community_report_provider_line = stage_provider_line(
        "deterministic",
        smoke=args.smoke,
    )
    query_planner_provider_line = stage_provider_line(
        query_planner_provider,
        smoke=args.smoke,
    )
    embedding_model = args.embedding_model
    embedding_dimension = args.embedding_dimension
    if embedding_provider == "stable_hash":
        embedding_model = embedding_model or "sha256-v1"
        embedding_dimension = embedding_dimension or 8
    else:
        embedding_model = embedding_model or "bge-m3"
        embedding_dimension = embedding_dimension or 1024

    return f"""[sources]
include = {toml_list(includes)}
exclude = {toml_list(excludes)}

[core]
purpose_file = {toml_string(args.purpose_file)}
concept_file = {toml_string(args.concept_file)}
extraction_mode = {toml_string(extraction_mode)}

[graph]
storage = {toml_string(args.graph_storage)}

{llm_block}
[extraction]
mode = {toml_string(extraction_mode)}
{extraction_provider_line}max_triplets_per_chunk = 20
num_workers = 1
batch_size = 6
batch_max_chars = 4000
section_max_heading_level = 4
grounding_score_threshold = 0.9
grounding_score_margin = 0.15
timeout_sec = 120
max_retries = 0
retry_backoff_sec = 0.0
repair_on_schema_failure = true
{extraction_provider_blocks}

[answer]
{answer_provider_line}failure_fallback = {toml_string(answer_failure_fallback)}
sandbox = "read-only"
tools = ""
timeout_sec = 120
max_retries = 0
retry_backoff_sec = 0.0
repair_on_schema_failure = true

[classification]
{classification_provider_line}sandbox = "read-only"
tools = ""
max_items = 8
fallback_on_error = {toml_bool(args.smoke)}
timeout_sec = 120
max_retries = 0
retry_backoff_sec = 0.0
repair_on_schema_failure = true

[concept_diff]
{concept_diff_provider_line}sandbox = "read-only"
tools = ""
fallback_on_error = {toml_bool(args.smoke)}
timeout_sec = 120
max_retries = 0
retry_backoff_sec = 0.0
repair_on_schema_failure = true

[community_report]
{community_report_provider_line}sandbox = "read-only"
tools = ""
fallback_on_error = {toml_bool(args.smoke)}
timeout_sec = 120
max_retries = 0
retry_backoff_sec = 0.0
repair_on_schema_failure = true

[retrieval]
chunk_size = 1600
chunk_overlap = 200
vector_top_k = 8
bm25_top_k = 12
graph_expansion_hops = 1
graph_relation_allowlist = ["DEPENDS_ON", "REFINES", "RELATED_TO", "CONTRASTS_WITH"]
graph_min_relation_confidence = "medium"
max_graph_entities = 12
rank_fusion = "rrf"
max_source_chunks = 12

[query_planner]
{query_planner_provider_line}fallback_on_error = {toml_bool(args.smoke)}
sandbox = "read-only"
tools = ""
timeout_sec = 120
max_retries = 0
retry_backoff_sec = 0.0
repair_on_schema_failure = true

[embedding]
provider = {toml_string(embedding_provider)}
model = {toml_string(embedding_model)}
dimension = {embedding_dimension}
timeout_sec = 120
max_retries = 0
retry_backoff_sec = 0.0

[run]
save_artifacts = false
artifact_dir = ".spec-grag/runs"
include_request = false
include_response = false
redact_payload = false

[watcher]
enabled = true
interval_ms = 2000
debounce_ms = 500
stale_lock_ms = 300000
state_file = ".spec-grag/state/watch_state.json"
queue_file = ".spec-grag/state/watch_queue.json"
"""


def render_llm_block(args: argparse.Namespace, *, provider: str) -> str:
    return f"""[llm]
provider = {toml_string(provider)}

[llm.codex_cli]
command = {toml_string(args.codex_command)}
model = {toml_string(args.codex_model)}
effort = {toml_string(args.codex_effort)}

[llm.claude_cli]
command = {toml_string(args.claude_command)}
model = {toml_string(args.claude_model)}
effort = {toml_string(args.claude_effort)}
"""


def stage_provider_line(provider: str, *, smoke: bool) -> str:
    if not smoke:
        return ""
    return f"provider = {toml_string(provider)}\n"


def choose_provider(
    value: str | None,
    smoke_default: str,
    production_default: str,
    smoke: bool,
) -> str:
    if value is not None:
        return value
    return smoke_default if smoke else production_default


def install_one_file(
    *,
    target: Path,
    planned: PlannedFile,
    force: bool,
    backup: bool,
    dry_run: bool,
    actions: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> None:
    destination = target / planned.relative_path
    action_path = str(planned.relative_path)
    exists = destination.exists()
    if exists and destination.read_text(encoding="utf-8") == planned.content:
        actions.append({"action": "skip-identical", "path": action_path})
        return

    if exists and not force and not backup:
        conflicts.append(
            {
                "path": action_path,
                "reason": "exists-with-different-content",
                "resolution": "rerun with --force or --backup",
            }
        )
        actions.append({"action": "conflict", "path": action_path})
        return

    if dry_run:
        action = "create" if not exists else "overwrite"
        if exists and backup:
            action = "backup-and-overwrite"
        actions.append({"action": f"would-{action}", "path": action_path})
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    if exists and backup:
        backup_destination = next_backup_path(destination)
        shutil.copy2(destination, backup_destination)
        actions.append(
            {
                "action": "backup",
                "path": action_path,
                "backup_path": str(backup_destination.relative_to(target)),
            }
        )
    destination.write_text(planned.content, encoding="utf-8")
    actions.append({"action": "create" if not exists else "overwrite", "path": action_path})


def next_backup_path(path: Path) -> Path:
    candidate = path.with_name(f"{path.name}.bak")
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = path.with_name(f"{path.name}.bak{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def validate_install(
    target: Path,
    planned_files: list[PlannedFile],
    *,
    dry_run: bool,
    smoke: bool,
) -> dict[str, Any]:
    warnings: list[str] = []
    config_path = target / ".spec-grag/config.toml"
    planned_paths = sorted(str(item.relative_path) for item in planned_files)
    required_paths = [
        ".spec-grag/config.toml",
        ".codex/commands/spec-core.md",
        ".codex/commands/spec-inject.md",
        ".codex/commands/spec-realign.md",
    ]
    if dry_run:
        config_valid = True
        try:
            config_valid = planned_config_valid(planned_files, smoke=smoke)
        except Exception as exc:
            config_valid = False
            warnings.append(f"config_validation_unavailable:{exc}")
        present = [path for path in required_paths if path in planned_paths]
        return {
            "ok": len(present) == len(required_paths) and config_valid,
            "config_valid": config_valid,
            "required_files": present,
            "warnings": warnings,
            "spec_grag_cli": shutil.which("spec-grag"),
            "python_module": True,
        }

    missing = [path for path in required_paths if not (target / path).exists()]
    config_valid = False
    try:
        with config_path.open("rb") as f:
            validate_config_data(tomllib.load(f), smoke=smoke)
        config_valid = True
    except Exception as exc:
        warnings.append(f"config_invalid:{exc}")

    module_ok = python_module_available()
    if not module_ok:
        warnings.append("python_module_unavailable:spec_grag.cli")
    cli_path = shutil.which("spec-grag")
    if cli_path is None:
        warnings.append("console_script_missing:spec-grag")

    return {
        "ok": not missing and config_valid and module_ok,
        "config_valid": config_valid,
        "required_files": required_paths,
        "missing_files": missing,
        "warnings": warnings,
        "spec_grag_cli": cli_path,
        "python_module": module_ok,
    }


def planned_config_valid(planned_files: list[PlannedFile], *, smoke: bool) -> bool:
    for item in planned_files:
        if item.relative_path == Path(".spec-grag/config.toml"):
            validate_config_data(tomllib.loads(item.content), smoke=smoke)
            return True
    return False


def validate_config_data(config: dict[str, Any], *, smoke: bool) -> dict[str, Any]:
    try:
        from spec_grag.config import validate_project_config
    except Exception as exc:
        raise RuntimeError("spec_grag validation dependencies are unavailable") from exc
    return validate_project_config(config, smoke=smoke)


def python_module_available() -> bool:
    try:
        import spec_grag.cli  # noqa: F401
    except Exception:
        return False
    return True


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def toml_list(values: Sequence[str]) -> str:
    return "[" + ", ".join(toml_string(value) for value in values) + "]"


def toml_bool(value: bool) -> str:
    return "true" if value else "false"


def emit_summary(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print(f"target: {summary['target']}")
    print(f"template_root: {summary['template_root']}")
    print(f"smoke: {summary['smoke']}")
    print(f"dry_run: {summary['dry_run']}")
    for action in summary["actions"]:
        print(f"{action['action']}: {action['path']}")
    for conflict in summary["conflicts"]:
        print(f"conflict: {conflict['path']} ({conflict['resolution']})")
    for warning in summary["warnings"]:
        print(f"warning: {warning}")
    print("ok" if summary["ok"] else "failed")


if __name__ == "__main__":
    raise SystemExit(main())
