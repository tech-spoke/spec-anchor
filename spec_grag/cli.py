"""Command line entrypoints for the lightweight SPEC-grag skeleton."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from spec_grag import __version__


def _install_termination_handler() -> None:
    """Convert SIGTERM into SystemExit so ``try/finally`` blocks always run.

    Python's default SIGTERM handler terminates the process immediately
    without unwinding the stack. That left ``.spec-grag/state/core_update.lock.json``
    behind whenever a `/spec-core` run was killed (e.g. via ``kill PID``),
    blocking the next run for the full ``stale_lock_ms`` (5 minutes).
    Translating SIGTERM into ``SystemExit`` lets ``release_core_update_lock``
    (and other resource cleanups) execute cleanly.
    """

    def _terminate(signum: int, frame: object | None) -> None:
        sys.exit(128 + signum)

    try:
        signal.signal(signal.SIGTERM, _terminate)
    except (ValueError, OSError):
        # Not running in main thread (e.g. embedded usage) — caller can
        # install their own signal handling.
        pass


def _add_version(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )


def build_main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec-grag",
        description="Lightweight SPEC-grag CLI.",
    )
    _add_version(parser)
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    core = subparsers.add_parser(
        "core",
        help="update section metadata, retrieval index, and conflict review items",
    )
    core.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="clear LLM-derived caches (section metadata + pair typing + chapter anchors) and re-evaluate",
    )
    core.add_argument(
        "--rebuild",
        action="store_true",
        help="drop and recreate the Qdrant spec_grag_section collection (implies --all). Use when embeddings are suspected corrupt or the collection has stale residue.",
    )
    core.add_argument(
        "--verify-index",
        action="store_true",
        help="verify that the Qdrant Source Retrieval Index payloads match the current section hashes",
    )
    core.add_argument(
        "--llm-provider",
        dest="llm_provider_id",
        help="configured [llm.providers.<id>] to use for this /spec-core run",
    )
    core.add_argument(
        "--decision-json",
        help="JSON conflict decision payload to pass to /spec-core",
    )
    core.add_argument(
        "--decision-file",
        help="path to a JSON conflict decision payload to pass to /spec-core",
    )

    inject_search = subparsers.add_parser(
        "inject-search",
        help="Phase R-6: section-level Qdrant hybrid retrieval (top-K section payload)",
    )
    inject_search.add_argument("query", nargs="+", help="natural-language search query")

    inject_section = subparsers.add_parser(
        "inject-section",
        help="Phase R-6: id-indexed section payload lookup against Qdrant",
    )
    inject_section.add_argument(
        "section_ids", nargs="+", help="one or more source_section_id values"
    )

    subparsers.add_parser(
        "inject-chapters",
        help="Phase R-6: return chapter_anchors.json for the project",
    )

    subparsers.add_parser(
        "inject-purpose",
        help="Phase R-6: return Purpose + Core Concept file contents",
    )

    subparsers.add_parser(
        "inject-conflicts",
        help="Phase R-6: return resolved (non-stale) Conflict Review Items",
    )

    realign = subparsers.add_parser(
        "realign",
        help="structure the Agent-supplied answer into the RealignResult layout",
    )
    realign.add_argument(
        "--answer",
        "--answer-text",
        "--agent-answer",
        dest="answer_text",
        help="Agent-supplied answer candidate as plain text",
    )
    realign.add_argument("--answer-json", "--agent-answer-json", dest="answer_json", help="Agent-supplied answer candidate JSON")
    realign.add_argument("--answer-file", "--agent-answer-file", dest="answer_file", help="path to Agent-supplied answer JSON or text")

    watch = subparsers.add_parser(
        "watch",
        help="watch Source Specs and run incremental updates",
    )
    _add_watch_arguments(watch)

    return parser


def build_watch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec-grag-watch",
        description="Watch Source Specs and run incremental SPEC-grag updates.",
    )
    _add_version(parser)
    _add_watch_arguments(parser)
    return parser


def _add_watch_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--once", action="store_true", help="run one scan and exit")
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=None,
        help="poll interval override",
    )
    parser.add_argument(
        "--debounce-sec",
        type=float,
        default=None,
        help="change debounce override",
    )
    parser.add_argument(
        "--stale-lock-sec",
        type=float,
        default=None,
        help="stale lock age override",
    )
    parser.add_argument("--max-runs", type=int, default=None, help="maximum update runs")


def build_setup_project_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec-grag-setup-project",
        description="Create or update SPEC-grag project files.",
    )
    _add_version(parser)
    parser.add_argument("--target", default=".", help="target project root")
    parser.add_argument(
        "--agent",
        choices=("codex", "claude", "both"),
        default="both",
        help="Agent entrypoint target",
    )
    parser.add_argument("--dry-run", action="store_true", help="show changes only")
    parser.add_argument("--force", action="store_true", help="overwrite managed files")
    parser.add_argument(
        "--no-init-core-files",
        action="store_true",
        help="do not create Purpose / Core Concept placeholders",
    )
    return parser


def build_setup_system_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec-grag-setup-system",
        description="Check or prepare the SPEC-grag tool installation.",
    )
    _add_version(parser)
    parser.add_argument("--check-only", action="store_true", help="only report status")
    parser.add_argument(
        "--mode",
        choices=("editable", "archive", "install"),
        default="editable",
        help="installation mode to check or prepare",
    )
    parser.add_argument("--run-smoke", action="store_true", help="run opt-in smoke checks")
    parser.add_argument(
        "--qdrant-url",
        help="Qdrant URL to probe for system readiness; project runs use [vector_store].url",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _install_termination_handler()
    parser = build_main_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) is None:
        parser.print_help()
        return 0
    if args.command == "core":
        return _run_core_from_args(args)
    if args.command == "inject-search":
        return _run_inject_search_from_args(args)
    if args.command == "inject-section":
        return _run_inject_section_from_args(args)
    if args.command == "inject-chapters":
        return _run_inject_chapters_from_args(args)
    if args.command == "inject-purpose":
        return _run_inject_purpose_from_args(args)
    if args.command == "inject-conflicts":
        return _run_inject_conflicts_from_args(args)
    if args.command == "realign":
        return _run_realign_from_args(args)
    if args.command == "watch":
        return _run_watch_from_args(args)
    parser.error(f"unknown command: {args.command}")
    return 2


def slash_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spec-grag-slash",
        description="Render or dispatch SPEC-grag slash command helpers.",
    )
    _add_version(parser)
    parser.add_argument("command", nargs="?", choices=("core", "realign"))
    parser.parse_args(argv)
    return 0


def watch_main(argv: Sequence[str] | None = None) -> int:
    _install_termination_handler()
    args = build_watch_parser().parse_args(argv)
    return _run_watch_from_args(args)


def _run_watch_from_args(args: argparse.Namespace) -> int:
    import spec_grag.watcher as watcher

    result = watcher.run_spec_grag_watch(
        project_root=str(Path.cwd()),
        once=args.once,
        interval_sec=args.interval_sec,
        debounce_sec=args.debounce_sec,
        stale_lock_sec=args.stale_lock_sec,
        max_runs=args.max_runs,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_core_from_args(args: argparse.Namespace) -> int:
    from spec_grag.core import run_spec_core

    project_root = _resolved_project_root()
    try:
        decision_payload = _load_json_argument(
            value=args.decision_json,
            file_path=args.decision_file,
            label="decision payload",
        )
        rebuild_embeddings = bool(args.rebuild)
        run_full_flag = bool(args.all or rebuild_embeddings)
        result = run_spec_core(
            project_root=project_root,
            all=run_full_flag,
            all_mode=run_full_flag,
            mode="full" if run_full_flag else None,
            rebuild_embeddings=rebuild_embeddings,
            verify_index=args.verify_index,
            decision_payload=decision_payload,
            llm_provider_id=args.llm_provider_id,
        )
    except Exception as exc:
        result = _exception_result("/spec-core", project_root=project_root, exc=exc)
    print(_dumps_json(result))
    return _command_exit_code(result)


def _run_inject_search_from_args(args: argparse.Namespace) -> int:
    """Phase R-6: dispatch `spec-grag inject-search`."""

    from spec_grag.inject import run_inject_search

    project_root = _resolved_project_root()
    query = " ".join(getattr(args, "query", []) or ()).strip()
    try:
        result = run_inject_search(
            project_root=project_root,
            query=query,
        )
    except Exception as exc:
        result = _exception_result(
            "/spec-inject inject-search", project_root=project_root, exc=exc
        )
    print(_dumps_json(result))
    return 0


def _run_inject_section_from_args(args: argparse.Namespace) -> int:
    """Phase R-6: dispatch `spec-grag inject-section`."""

    from spec_grag.inject import run_inject_section

    project_root = _resolved_project_root()
    try:
        result = run_inject_section(
            project_root=project_root,
            section_ids=list(getattr(args, "section_ids", []) or ()),
        )
    except Exception as exc:
        result = _exception_result(
            "/spec-inject inject-section", project_root=project_root, exc=exc
        )
    print(_dumps_json(result))
    return 0


def _run_inject_chapters_from_args(args: argparse.Namespace) -> int:
    """Phase R-6: dispatch `spec-grag inject-chapters`."""

    from spec_grag.inject import run_inject_chapters

    project_root = _resolved_project_root()
    try:
        result = run_inject_chapters(project_root=project_root)
    except Exception as exc:
        result = _exception_result(
            "/spec-inject inject-chapters", project_root=project_root, exc=exc
        )
    print(_dumps_json(result))
    return 0


def _run_inject_purpose_from_args(args: argparse.Namespace) -> int:
    """Phase R-6: dispatch `spec-grag inject-purpose`."""

    from spec_grag.inject import run_inject_purpose

    project_root = _resolved_project_root()
    try:
        result = run_inject_purpose(project_root=project_root)
    except Exception as exc:
        result = _exception_result(
            "/spec-inject inject-purpose", project_root=project_root, exc=exc
        )
    print(_dumps_json(result))
    return 0


def _run_inject_conflicts_from_args(args: argparse.Namespace) -> int:
    """Phase R-6: dispatch `spec-grag inject-conflicts`."""

    from spec_grag.inject import run_inject_conflicts

    project_root = _resolved_project_root()
    try:
        result = run_inject_conflicts(project_root=project_root)
    except Exception as exc:
        result = _exception_result(
            "/spec-inject inject-conflicts", project_root=project_root, exc=exc
        )
    print(_dumps_json(result))
    return 0


def _run_realign_from_args(args: argparse.Namespace) -> int:
    from spec_grag.realign import SpecRealignError, run_spec_realign

    project_root = _resolved_project_root()
    try:
        answer = _load_answer_argument(args)
        result = run_spec_realign(
            project_root=project_root,
            agent_answer=answer,
        )
    except SpecRealignError as exc:
        result = _agent_input_error_result(
            "/spec-realign",
            project_root=project_root,
            exc=exc,
            stop_reason=_realign_stop_reason(str(exc)),
            recommended_next_action=_realign_recommended_next_action(str(exc)),
        )
    except Exception as exc:
        result = _exception_result("/spec-realign", project_root=project_root, exc=exc)
    print(_dumps_json(result))
    return _command_exit_code(result)


def _resolved_project_root() -> Path:
    return Path.cwd().resolve()


def _load_json_argument(
    *,
    value: str | None,
    file_path: str | None,
    label: str,
) -> Any | None:
    if value is None and file_path is None:
        return None
    if value is not None and file_path is not None:
        raise ValueError(f"{label} must be supplied either as JSON or as a file, not both")
    raw = Path(file_path).expanduser().read_text(encoding="utf-8") if file_path else value
    try:
        return json.loads(raw or "")
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} JSON: {exc.msg}") from exc


def _load_answer_argument(args: argparse.Namespace) -> Any | None:
    if args.answer_json is not None:
        if args.answer_text is not None or args.answer_file is not None:
            raise ValueError("answer must be supplied by only one answer option")
        return _load_json_argument(value=args.answer_json, file_path=None, label="answer")
    if args.answer_file is not None:
        if args.answer_text is not None:
            raise ValueError("answer must be supplied by only one answer option")
        raw = Path(args.answer_file).expanduser().read_text(encoding="utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return args.answer_text


def _agent_input_error_result(
    command: str,
    *,
    project_root: Path,
    exc: Exception,
    stop_reason: str,
    recommended_next_action: str,
) -> dict[str, Any]:
    return {
        "command": command,
        "project_root": project_root.as_posix(),
        "status": "error",
        "should_stop": True,
        "stops": True,
        "blocked": True,
        "can_continue": False,
        "constraints": [],
        "stop_reason": stop_reason,
        "reasons": [stop_reason],
        "recommended_next_action": recommended_next_action,
        "error": {
            "code": stop_reason,
            "type": exc.__class__.__name__,
            "message": str(exc),
        },
    }


def _exception_result(command: str, *, project_root: Path, exc: Exception) -> dict[str, Any]:
    return {
        "command": command,
        "project_root": project_root.as_posix(),
        "status": "error",
        "should_stop": True,
        "stops": True,
        "blocked": True,
        "can_continue": False,
        "constraints": [],
        "error": {
            "code": "command_error",
            "type": exc.__class__.__name__,
            "message": str(exc),
        },
    }


def _realign_stop_reason(message: str) -> str:
    if "answer" in message or "agent_answer" in message:
        return "needs_agent_answer"
    return "needs_agent_input"


def _realign_recommended_next_action(message: str) -> str:
    reason = _realign_stop_reason(message)
    if reason == "needs_agent_answer":
        return "provide an Agent-generated answer candidate to spec-grag realign"
    return "provide the missing Agent-generated input to spec-grag realign"


def _command_exit_code(result: Mapping[str, Any]) -> int:
    if "exit_code" in result:
        return int(result.get("exit_code") or 0)
    if result.get("error") or result.get("status") in {"error", "failed"}:
        return 1
    return 0


def _dumps_json(result: Mapping[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)


def setup_project_main(argv: Sequence[str] | None = None) -> int:
    args = build_setup_project_parser().parse_args(argv)
    from spec_grag.project_setup import dumps_result, result_exit_code, setup_project

    result = setup_project(
        target=args.target,
        agent=args.agent,
        dry_run=args.dry_run,
        force=args.force,
        no_init_core_files=args.no_init_core_files,
    )
    print(dumps_result(result))
    return result_exit_code(result)


def setup_system_main(argv: Sequence[str] | None = None) -> int:
    args = build_setup_system_parser().parse_args(argv)
    from spec_grag.project_setup import dumps_result, result_exit_code, setup_system

    result = setup_system(
        check_only=args.check_only,
        mode=args.mode,
        run_smoke=args.run_smoke,
        qdrant_url=args.qdrant_url,
    )
    print(dumps_result(result))
    return result_exit_code(result, system_setup=True)
