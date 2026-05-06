from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: subprocess or end-to-end tests that may take several seconds",
    )


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT
