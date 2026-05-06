"""Shared exceptions and diagnostics for SPEC-grag."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Diagnostic:
    """Machine-readable diagnostic data for user-facing errors."""

    code: str
    message: str
    severity: str = "error"
    path: str | None = None
    key: str | None = None
    line: int | None = None
    column: int | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }
        for name in ("path", "key", "line", "column", "hint"):
            value = getattr(self, name)
            if value is not None:
                data[name] = value
        return data


class SpecGragError(Exception):
    """Base class for SPEC-grag exceptions."""

    def __init__(
        self,
        message: str,
        *,
        diagnostic: Diagnostic | None = None,
        diagnostics: tuple[Diagnostic, ...] | None = None,
    ) -> None:
        super().__init__(message)
        if diagnostics is None:
            diagnostics = () if diagnostic is None else (diagnostic,)
        self.message = message
        self.diagnostics = diagnostics
        self.diagnostic = diagnostics[0] if diagnostics else diagnostic


class ConfigError(SpecGragError):
    """Base class for configuration loading errors."""


class ConfigFileNotFoundError(ConfigError):
    """Raised when project-root .spec-grag/config.toml is missing."""


class ConfigParseError(ConfigError):
    """Raised when config.toml cannot be parsed as TOML."""


class ConfigValidationError(ConfigError):
    """Raised when config.toml is syntactically valid but invalid."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        count = len(diagnostics)
        message = (
            diagnostics[0].message
            if count == 1
            else f"config validation failed with {count} errors"
        )
        super().__init__(message, diagnostics=diagnostics)
