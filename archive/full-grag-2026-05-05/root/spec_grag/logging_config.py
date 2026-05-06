"""Logging setup for CLI and watcher entrypoints."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


LOGGING_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
    "OFF": logging.CRITICAL + 1,
}


def configure_logging_from_config(
    config: Mapping[str, Any],
    *,
    project_root: Path | None = None,
) -> None:
    logging_config = _mapping(config.get("logging"))
    level_name = str(logging_config.get("level", "WARNING")).strip().upper()
    level = LOGGING_LEVELS.get(level_name, logging.WARNING)
    logger = logging.getLogger("spec_grag")
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, "_spec_grag_configured", False):
            logger.removeHandler(handler)
            handler.close()

    if level_name == "OFF":
        logger.disabled = True
        return
    logger.disabled = False

    file_path = logging_config.get("file_path")
    if isinstance(file_path, str) and file_path.strip():
        path = Path(file_path)
        if not path.is_absolute() and project_root is not None:
            path = project_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=int(logging_config.get("max_bytes", 1_048_576)),
            backupCount=int(logging_config.get("backup_count", 3)),
            encoding="utf-8",
        )
    else:
        handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    setattr(handler, "_spec_grag_configured", True)
    logger.addHandler(handler)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
