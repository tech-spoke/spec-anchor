"""Package resource helpers for project template installation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from importlib import resources
from pathlib import Path


@contextmanager
def project_template_root(
    preferred_root: Path | None = None,
) -> Iterator[Path]:
    """Yield a filesystem path for SPEC-grag project templates.

    Source checkouts keep editable templates at repo-root ``templates/``. Wheels
    cannot rely on that path, so the same files are also packaged under
    ``spec_grag/templates`` and exposed through ``importlib.resources``.
    """

    if preferred_root is not None and preferred_root.exists():
        with nullcontext(preferred_root) as path:
            yield path
            return

    resource_root = resources.files("spec_grag").joinpath("templates")
    with resources.as_file(resource_root) as path:
        yield Path(path)


def packaged_template_files() -> list[str]:
    """Return package-relative template paths for diagnostics and tests."""

    with project_template_root(None) as root:
        return sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        )
