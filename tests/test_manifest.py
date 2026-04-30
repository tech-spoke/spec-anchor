from __future__ import annotations

from pathlib import Path

from spec_grag.manifest import (
    MARKDOWN_PARSER_NAME,
    SourceManifest,
    ManifestUpdateStatus,
    build_current_section_manifest,
    load_source_manifest,
    next_source_manifest,
    reconcile_manifests,
    write_source_manifest_atomic,
)


def write_markdown(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def section_ids_for(path: Path, root: Path) -> list[str]:
    manifest = build_current_section_manifest(root, [path])
    return [entry.section_id for entry in manifest.entries]


def test_build_current_section_manifest_ignores_fenced_headings(tmp_path: Path) -> None:
    source = write_markdown(
        tmp_path / "docs/spec/auth.md",
        """# Auth

Intro.

```text
# Not a heading
```

## Login

OAuth is required.
""",
    )

    manifest = build_current_section_manifest(tmp_path, [source])

    assert [entry.heading_path for entry in manifest.entries] == [
        "Auth",
        "Auth / Login",
    ]
    assert manifest.entries[0].document_id == "docs/spec/auth.md"
    assert manifest.entries[1].chapter_id == "docs/spec/auth.md#auth"
    assert len(manifest.entries[1].source_hash) == 64
    assert manifest.parser_name == MARKDOWN_PARSER_NAME
    assert manifest.parser_version


def test_build_current_section_manifest_supports_setext_headings(
    tmp_path: Path,
) -> None:
    source = write_markdown(
        tmp_path / "docs/spec/auth.md",
        """Auth
====

Intro.

Login
-----

OAuth is required.
""",
    )

    manifest = build_current_section_manifest(tmp_path, [source])

    assert [entry.heading_path for entry in manifest.entries] == [
        "Auth",
        "Auth / Login",
    ]
    assert [entry.section_id for entry in manifest.entries] == [
        "docs/spec/auth.md#auth",
        "docs/spec/auth.md#auth-login",
    ]
    assert manifest.entries[0].heading_start_line == 1
    assert manifest.entries[1].heading_start_line == 6


def test_build_current_section_manifest_ignores_nested_and_html_headings(
    tmp_path: Path,
) -> None:
    source = write_markdown(
        tmp_path / "docs/spec/auth.md",
        """<div>
# Not a heading
</div>

> # Quoted heading

- # List item heading

# Real
""",
    )

    manifest = build_current_section_manifest(tmp_path, [source])

    assert [entry.heading_path for entry in manifest.entries] == [
        "auth / preamble",
        "Real",
    ]
    assert manifest.entries[1].section_id == "docs/spec/auth.md#real"


def test_source_hash_changes_only_when_section_content_changes(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "docs/spec/auth.md", "# Auth\n\nOAuth is required.\n")
    first = build_current_section_manifest(tmp_path, [source])

    source.write_text("# Auth\n\nOAuth is optional.\n", encoding="utf-8")
    second = build_current_section_manifest(tmp_path, [source])

    assert first.entries[0].section_id == second.entries[0].section_id
    assert first.entries[0].source_hash != second.entries[0].source_hash


def test_build_current_section_manifest_preserves_unicode_heading_ids(
    tmp_path: Path,
) -> None:
    source = write_markdown(
        tmp_path / "docs/spec/auth.md",
        "# 認証\n\nIntro.\n\n## ログイン\n\nOAuth.\n",
    )

    assert section_ids_for(source, tmp_path) == [
        "docs/spec/auth.md#認証",
        "docs/spec/auth.md#認証-ログイン",
    ]


def test_reconcile_detects_changed_removed_added_and_rename_as_removed_added(
    tmp_path: Path,
) -> None:
    source = write_markdown(
        tmp_path / "docs/spec/auth.md",
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth is required.\n",
    )
    previous = build_current_section_manifest(tmp_path, [source])

    source.write_text(
        "# Auth\n\nIntro changed.\n\n## Authentication\n\nOAuth is required.\n\n## Tokens\n\nJWT.\n",
        encoding="utf-8",
    )
    current = build_current_section_manifest(tmp_path, [source])
    plan = reconcile_manifests(previous, current)

    assert "docs/spec/auth.md#auth" in plan.changed_section_ids
    assert "docs/spec/auth.md#auth-login" in plan.removed_section_ids
    assert "docs/spec/auth.md#auth-authentication" in plan.added_section_ids
    assert "docs/spec/auth.md#auth-tokens" in plan.added_section_ids
    assert plan.structure_changed_chapter_ids == ["docs/spec/auth.md#auth"]


def test_reconcile_detects_split_and_merge_as_added_removed(tmp_path: Path) -> None:
    source = write_markdown(
        tmp_path / "docs/spec/auth.md",
        "# Auth\n\n## Login\n\nOAuth.\n\n## Logout\n\nClear session.\n",
    )
    split = build_current_section_manifest(tmp_path, [source])

    source.write_text(
        "# Auth\n\n## Session\n\nOAuth and session cleanup.\n",
        encoding="utf-8",
    )
    merged = build_current_section_manifest(tmp_path, [source])
    plan = reconcile_manifests(split, merged)

    assert "docs/spec/auth.md#auth-login" in plan.removed_section_ids
    assert "docs/spec/auth.md#auth-logout" in plan.removed_section_ids
    assert "docs/spec/auth.md#auth-session" in plan.added_section_ids


def test_reconcile_treats_parser_change_as_changed_sections(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "docs/spec/auth.md", "# Auth\n\nOAuth.\n")
    current = build_current_section_manifest(tmp_path, [source])
    previous = SourceManifest(
        parser_name="legacy-atx",
        parser_version="0",
        generated_at=current.generated_at,
        entries=current.entries,
    )

    plan = reconcile_manifests(previous, current)

    assert plan.unchanged_section_ids == []
    assert plan.changed_section_ids == ["docs/spec/auth.md#auth"]


def test_write_and_load_source_manifest_atomic(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "docs/spec/auth.md", "# Auth\n\nOAuth.\n")
    manifest = build_current_section_manifest(tmp_path, [source], generated_at="t0")
    manifest_path = tmp_path / ".spec-grag/graph/source_manifest.json"

    write_source_manifest_atomic(manifest_path, manifest)
    loaded = load_source_manifest(manifest_path)

    assert loaded == manifest
    assert not list(manifest_path.parent.glob("*.tmp"))


def test_next_source_manifest_ok_updates_all_current_entries(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "docs/spec/auth.md", "# Auth\n\nOAuth.\n")
    previous = build_current_section_manifest(tmp_path, [source])
    source.write_text("# Auth\n\nOAuth 2.0.\n", encoding="utf-8")
    current = build_current_section_manifest(tmp_path, [source])

    updated = next_source_manifest(
        previous,
        current,
        status=ManifestUpdateStatus.OK,
        scanned_at="2026-04-29T00:00:00+00:00",
        extract_run_id="run-1",
        extractor_versions={"schema_llm_path_extractor": "0.1"},
    )

    assert updated.entries[0].source_hash == current.entries[0].source_hash
    assert updated.entries[0].scanned_at == "2026-04-29T00:00:00+00:00"
    assert updated.entries[0].extract_run_id == "run-1"


def test_next_source_manifest_degraded_keeps_failed_section_and_updates_success(
    tmp_path: Path,
) -> None:
    source = write_markdown(
        tmp_path / "docs/spec/auth.md",
        "# Auth\n\nIntro.\n\n## Login\n\nOAuth.\n",
    )
    previous_current = build_current_section_manifest(tmp_path, [source])
    previous = next_source_manifest(
        previous_current,
        previous_current,
        status=ManifestUpdateStatus.OK,
        scanned_at="old",
        extract_run_id="run-old",
    )

    source.write_text(
        "# Auth\n\nIntro changed.\n\n## Login\n\nOAuth changed.\n",
        encoding="utf-8",
    )
    current = build_current_section_manifest(tmp_path, [source])
    failed_section = "docs/spec/auth.md#auth-login"
    updated = next_source_manifest(
        previous,
        current,
        status=ManifestUpdateStatus.DEGRADED,
        scanned_at="new",
        extract_run_id="run-new",
        failed_section_ids={failed_section},
    )
    by_id = updated.by_section_id()

    assert by_id["docs/spec/auth.md#auth"].scanned_at == "new"
    assert by_id[failed_section].scanned_at == "old"
    assert by_id[failed_section].source_hash == previous.by_section_id()[failed_section].source_hash


def test_next_source_manifest_failed_or_blocked_keeps_previous(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "docs/spec/auth.md", "# Auth\n\nOAuth.\n")
    previous = build_current_section_manifest(tmp_path, [source], generated_at="old")
    source.write_text("# Auth\n\nChanged.\n", encoding="utf-8")
    current = build_current_section_manifest(tmp_path, [source], generated_at="new")

    failed = next_source_manifest(
        previous,
        current,
        status=ManifestUpdateStatus.FAILED,
        scanned_at="new",
        extract_run_id="run-new",
    )
    blocked = next_source_manifest(
        previous,
        current,
        status=ManifestUpdateStatus.BLOCKED,
        scanned_at="new",
        extract_run_id="run-new",
    )

    assert failed == previous
    assert blocked == previous
