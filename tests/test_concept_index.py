from __future__ import annotations

from pathlib import Path

from spec_grag.concept_diff import (
    ConceptDiffTaskContext,
    PendingConceptDiff,
    PendingConceptHunk,
    concept_file_hash,
    create_pending_concept_diff,
)
from spec_grag.concept_index import (
    build_concept_index,
    concept_index_path,
    refresh_concept_index,
    split_concept_paragraphs,
)
from spec_grag.protocol import Command


def write_concept(project_root: Path, text: str) -> Path:
    path = project_root / "docs/core/concept.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def config() -> dict:
    return {
        "core": {"concept_file": "docs/core/concept.md"},
        "graph": {"storage": ".spec-grag/graph/"},
    }


def test_split_concept_paragraphs_by_heading_and_paragraph() -> None:
    paragraphs = split_concept_paragraphs(
        "# Concept\n\nAuth protects sessions.\n\nKeep tokens short.\n\n## Login\n\nOAuth is required.\n"
    )

    assert [(p.heading_path, p.paragraph_index, p.text) for p in paragraphs] == [
        ("Concept", 0, "Auth protects sessions."),
        ("Concept", 1, "Keep tokens short."),
        ("Concept / Login", 0, "OAuth is required."),
    ]


def test_build_concept_index_records_hash_chunks_and_embeddings(tmp_path: Path) -> None:
    concept = write_concept(
        tmp_path,
        "# Concept\n\nAuth protects sessions.\n\n## Login\n\nOAuth is required.\n",
    )

    index = build_concept_index(tmp_path, concept, generated_at="t1")

    assert index.concept_file == "docs/core/concept.md"
    assert index.concept_file_hash == concept_file_hash(concept)
    assert [chunk.heading_path for chunk in index.chunks] == [
        "Concept",
        "Concept / Login",
    ]
    assert index.chunks[0].concept_chunk_id.startswith("concept:")
    assert len(index.chunks[0].text_hash) == 64
    assert len(index.chunks[0].embedding) == 8


def test_refresh_concept_index_is_idempotent_until_concept_hash_changes(
    tmp_path: Path,
) -> None:
    concept = write_concept(tmp_path, "# Concept\n\nAuth protects sessions.\n")
    graph_dir = tmp_path / ".spec-grag/graph"

    first, warnings = refresh_concept_index(
        tmp_path,
        config(),
        graph_dir,
        generated_at="t1",
    )
    second, _ = refresh_concept_index(
        tmp_path,
        config(),
        graph_dir,
        generated_at="t2",
    )
    concept.write_text("# Concept\n\nAuth protects all sessions.\n", encoding="utf-8")
    third, _ = refresh_concept_index(
        tmp_path,
        config(),
        graph_dir,
        generated_at="t3",
    )

    assert warnings == []
    assert first is not None
    assert second is not None
    assert third is not None
    assert concept_index_path(graph_dir).exists()
    assert second.generated_at == "t1"
    assert third.generated_at == "t3"
    assert third.concept_file_hash != first.concept_file_hash


def test_unapproved_pending_concept_diff_is_not_mixed_into_index(
    tmp_path: Path,
) -> None:
    concept = write_concept(tmp_path, "# Concept\n\nAuth protects sessions.\n")
    pending = PendingConceptDiff(
        diff_id="diff-1",
        base_concept_hash=concept_file_hash(concept),
        task_context=ConceptDiffTaskContext(
            command=Command.SPEC_CORE,
            changed_source_section_ids=["docs/spec/auth.md#auth-login"],
            extract_run_id="run-1",
        ),
        hunks=[
            PendingConceptHunk(
                hunk_id="hunk-1",
                file="docs/core/concept.md",
                old_range="-3,0",
                new_range="+3,1",
                diff_text=(
                    "--- a/docs/core/concept.md\n"
                    "+++ b/docs/core/concept.md\n"
                    "@@ -3,0 +3,1 @@\n"
                    "+- Passwordless login (source: docs/spec/auth.md#auth-login)\n"
                ),
            )
        ],
    )
    create_pending_concept_diff(tmp_path / ".spec-grag/pending", pending)

    index, _ = refresh_concept_index(tmp_path, config(), tmp_path / ".spec-grag/graph")

    assert index is not None
    assert "Passwordless" not in index.chunk_text()
