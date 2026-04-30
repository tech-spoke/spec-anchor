"""Optional run artifact persistence for CLI diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_grag.protocol import ResultEnvelope, SlashCommandRequest


def maybe_write_run_artifact(
    *,
    project_root: Path,
    config: dict[str, Any],
    request: SlashCommandRequest,
    envelope: ResultEnvelope,
) -> str | None:
    run_config = config.get("run", {})
    if not bool(run_config.get("save_artifacts", False)):
        return None
    artifact_dir = Path(str(run_config.get("artifact_dir", ".spec-grag/runs")))
    if not artifact_dir.is_absolute():
        artifact_dir = project_root / artifact_dir
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    digest = hashlib.sha256(envelope.to_json().encode("utf-8")).hexdigest()[:12]
    path = artifact_dir / f"{timestamp}-{request.command.value}-{digest}.json"
    payload: dict[str, Any] = {
        "version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "command": request.command.value,
        "status": envelope.status.value,
        "result_type": envelope.result_type.value,
        "warnings": envelope.warnings,
        "execution": envelope.execution.model_dump(mode="json"),
        "response": json.loads(envelope.to_json()),
    }
    if bool(run_config.get("include_request", True)):
        payload["request"] = request.model_dump(mode="json")
    _write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return str(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
