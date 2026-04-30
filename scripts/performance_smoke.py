"""Generate a larger temporary source set and run deterministic SPEC-core."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="spec-grag-perf-") as tmp:
        root = Path(tmp)
        write_project(root, doc_count=12, sections_per_doc=8)
        payload = request_payload(root, "spec-core", all_sources=True)
        result = subprocess.run(
            [sys.executable, "-m", "spec_grag.cli"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return result.returncode
        envelope = json.loads(result.stdout)
        print(
            json.dumps(
                {
                    "status": envelope["status"],
                    "updated_sources": len(envelope["payload"]["updated_sources"]),
                },
                ensure_ascii=False,
            )
        )
    return 0


def write_project(root: Path, *, doc_count: int, sections_per_doc: int) -> None:
    spec_dir = root / "docs/spec"
    core_dir = root / "docs/core"
    spec_dir.mkdir(parents=True)
    core_dir.mkdir(parents=True)
    (core_dir / "purpose.md").write_text("# Purpose\nKeep specs consistent.\n", encoding="utf-8")
    (core_dir / "concept.md").write_text("# Concept\nSpec sections describe constraints.\n", encoding="utf-8")
    for doc_index in range(doc_count):
        lines = [f"# Module {doc_index}\n\nOverview.\n"]
        for section_index in range(sections_per_doc):
            lines.append(
                f"## Feature {section_index}\n\n"
                f"Feature {section_index} requires audit trail {doc_index}-{section_index}.\n"
            )
        (spec_dir / f"module_{doc_index}.md").write_text("".join(lines), encoding="utf-8")
    config_dir = root / ".spec-grag"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[graph]
storage = ".spec-grag/graph/"
""".strip(),
        encoding="utf-8",
    )


def request_payload(root: Path, command: str, *, all_sources: bool = False) -> dict:
    return {
        "command": command,
        "project_root": str(root),
        "conversation_context": {
            "current_user_message": "Feature audit trail を確認する",
            "recent_messages": [],
            "working_target": None,
            "explicit_files": [],
        },
        "agent_capabilities": {"can_read_source": True, "can_answer": False},
        "options": {"output_format": "json", "all": all_sources},
    }


if __name__ == "__main__":
    raise SystemExit(main())
