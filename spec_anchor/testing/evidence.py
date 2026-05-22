"""Evidence collector for the SPEC-anchor E2E test plan.

Each pytest test that contributes to an external-design checkbox carries a
``SPEC_REF: §<chapter> L<line>`` line in its docstring (see
``doc/e2eテスト/test_plan.ja.md`` §7.3). During a pytest session, the
collector:

1. Parses each test's docstring to extract ``SPEC_REF`` / ``PROFILE`` /
   ``METHOD`` headers.
2. Resolves each ``SPEC_REF`` to the exact ``[ ]`` line in
   ``doc/EXTERNAL_DESIGN.ja.md`` and captures its text.
3. Records the test outcome (``passed`` / ``failed`` / ``skipped`` /
   ``xfailed``) with duration and timestamp.
4. Writes one JSONL row per ``SPEC_REF`` to
   ``doc/e2eテスト/evidence/<date>/evidence_map.jsonl`` at session end.

The collector never raises into the test session: parse errors and IO
failures are reported via warnings so a malformed docstring does not
break the suite.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DOC_PATH = REPO_ROOT / "doc" / "EXTERNAL_DESIGN.ja.md"
EVIDENCE_ROOT = REPO_ROOT / "doc" / "e2eテスト" / "evidence"


_SPEC_REF_RE = re.compile(r"^\s*SPEC_REF:\s*(?P<section>§[^\s]+)\s+L(?P<line>\d+)\s*$")
_PROFILE_RE = re.compile(r"^\s*PROFILE:\s*(?P<profile>\S+)\s*$")
_METHOD_RE = re.compile(r"^\s*METHOD:\s*(?P<method>.+?)\s*$")

_ALLOWED_PROFILES = {"none", "fake", "local-service", "real-smoke"}
_ALLOWED_METHODS = {
    "入出力比較",
    "artifact 内容確認",
    "Agent 出力文言確認",
    "tool call trace 監査",
}


@dataclass(frozen=True)
class SpecRef:
    """One ``SPEC_REF: §X.Y L<n>`` reference parsed from a test docstring."""

    section: str
    line: int


@dataclass
class _TestRecord:
    test_id: str
    refs: list[SpecRef]
    profile: str | None
    method: str | None
    result: str = "pending"
    duration_sec: float = 0.0
    executed_at: str = ""
    failure_message: str | None = None


def _parse_docstring(doc: str | None) -> tuple[list[SpecRef], str | None, str | None]:
    """Extract ``SPEC_REF`` / ``PROFILE`` / ``METHOD`` from a test docstring.

    Returns ``([], None, None)`` if the docstring is absent or contains no
    ``SPEC_REF`` line. This is not an error: many tests pre-date the
    evidence schema and will be backfilled gradually.
    """

    if not doc:
        return [], None, None

    refs: list[SpecRef] = []
    profile: str | None = None
    method: str | None = None

    for raw_line in doc.splitlines():
        if (m := _SPEC_REF_RE.match(raw_line)) is not None:
            try:
                refs.append(SpecRef(section=m.group("section"), line=int(m.group("line"))))
            except ValueError:
                warnings.warn(
                    f"evidence: cannot parse SPEC_REF line: {raw_line!r}",
                    stacklevel=2,
                )
        elif (m := _PROFILE_RE.match(raw_line)) is not None:
            profile = m.group("profile")
        elif (m := _METHOD_RE.match(raw_line)) is not None:
            method = m.group("method")

    return refs, profile, method


def _load_checkbox_text(line_no: int) -> str:
    """Read the spec doc line at ``line_no`` (1-based) and return its text.

    Returns ``"<line out of range>"`` when ``line_no`` is past the file end.
    Never raises; callers should not get a partial evidence_map.jsonl due to
    a docstring typo.
    """

    try:
        with SPEC_DOC_PATH.open("r", encoding="utf-8") as fp:
            for i, line in enumerate(fp, start=1):
                if i == line_no:
                    return line.rstrip("\n")
        return "<line out of range>"
    except OSError as exc:
        warnings.warn(f"evidence: cannot read spec doc: {exc}", stacklevel=2)
        return "<spec doc unreadable>"


class EvidenceCollector:
    """Singleton collector consumed by pytest hooks in ``tests/conftest.py``."""

    _instance: "EvidenceCollector | None" = None

    def __init__(self) -> None:
        self._records: dict[str, _TestRecord] = {}
        self._malformed_count = 0

    @classmethod
    def instance(cls) -> "EvidenceCollector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def record(self, item: pytest.Item, report: pytest.TestReport) -> None:
        """Record one test outcome. Idempotent for the same ``test_id``."""

        if report.when != "call":
            return

        # Pull docstring from the underlying function. ``item.obj`` is the
        # bound function for pytest function-style tests.
        obj = getattr(item, "obj", None)
        doc = getattr(obj, "__doc__", None) if obj is not None else None
        refs, profile, method = _parse_docstring(doc)

        # Per-param SPEC_REF markers override docstring refs. This lets a
        # ``@pytest.mark.parametrize`` test attach a row-specific
        # SPEC_REF / PROFILE / METHOD via
        # ``pytest.param(..., marks=[pytest.mark.spec_ref(section, line,
        # profile=..., method=...)])``. When a marker is present, the
        # docstring-derived refs are replaced entirely so each parametrize
        # row maps to its own checkbox.
        marker = item.get_closest_marker("spec_ref")
        if marker is not None:
            try:
                section, line = marker.args[0], int(marker.args[1])
            except (IndexError, ValueError, TypeError):
                warnings.warn(
                    f"evidence: {item.nodeid}: malformed @spec_ref marker "
                    f"args={marker.args!r}; expected (section, line, ...)",
                    stacklevel=2,
                )
            else:
                refs = [SpecRef(section=section, line=line)]
                profile = marker.kwargs.get("profile", profile)
                method = marker.kwargs.get("method", method)

        if not refs:
            # Test has no SPEC_REF. Not an error: legacy tests not yet
            # backfilled. Skip recording.
            return

        if profile is not None and profile not in _ALLOWED_PROFILES:
            warnings.warn(
                f"evidence: {item.nodeid}: PROFILE {profile!r} is not in "
                f"{sorted(_ALLOWED_PROFILES)}",
                stacklevel=2,
            )
            self._malformed_count += 1

        if method is not None and method not in _ALLOWED_METHODS:
            warnings.warn(
                f"evidence: {item.nodeid}: METHOD {method!r} is not in "
                f"{sorted(_ALLOWED_METHODS)}",
                stacklevel=2,
            )
            self._malformed_count += 1

        record = _TestRecord(
            test_id=item.nodeid,
            refs=refs,
            profile=profile,
            method=method,
            result=report.outcome,
            duration_sec=report.duration,
            executed_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            failure_message=str(report.longrepr) if report.failed else None,
        )
        self._records[item.nodeid] = record

    def flush(self, target_dir: Path | None = None) -> Path | None:
        """Write ``evidence_map.jsonl`` to ``target_dir`` (default: date folder).

        Returns the JSONL path written, or ``None`` if no SPEC_REF-bearing
        test ran during the session.
        """

        if not self._records:
            return None

        if target_dir is None:
            target_dir = _resolve_default_target_dir()

        target_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = target_dir / "evidence_map.jsonl"

        # Append mode: same date folder can collect evidence from multiple
        # pytest runs (e.g., `none` then `fake` then `real-smoke`). Caller
        # selects target_dir to control segmentation.
        with jsonl_path.open("a", encoding="utf-8") as fp:
            for record in self._records.values():
                for ref in record.refs:
                    row = {
                        "spec_section": ref.section,
                        "spec_line": ref.line,
                        "checkbox_text": _load_checkbox_text(ref.line),
                        "test_id": record.test_id,
                        "profile": record.profile,
                        "method": record.method,
                        "result": record.result,
                        "duration_sec": round(record.duration_sec, 4),
                        "executed_at": record.executed_at,
                    }
                    if record.failure_message:
                        row["failure_message"] = record.failure_message
                    fp.write(json.dumps(row, ensure_ascii=False) + "\n")

        return jsonl_path

    def records(self) -> Iterable[_TestRecord]:
        return self._records.values()


def _resolve_default_target_dir() -> Path:
    """Resolve evidence target folder honoring ``SPEC_ANCHOR_E2E_EVIDENCE_DATE``.

    Default is today's date in ``YYYY-MM-DD`` local-time form. Override with
    ``SPEC_ANCHOR_E2E_EVIDENCE_DATE=<arbitrary-tag>`` to pin a Phase-named
    folder (e.g., ``SPEC_ANCHOR_E2E_EVIDENCE_DATE=P0-baseline``).
    """

    tag = os.environ.get("SPEC_ANCHOR_E2E_EVIDENCE_DATE")
    if not tag:
        tag = datetime.now().strftime("%Y-%m-%d")
    return EVIDENCE_ROOT / tag
