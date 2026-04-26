//! `/spec-inject` — Sync + inject Core documents into the LLM context
//!
//! Reads Purpose and Concept and writes them to stdout in a structured form.
//! Claude Code captures this output and merges it into the conversation KV
//! (DESIGN.md §4 — Bash stdout → KV injection path).
//!
//! NOTE: The Concept-diff phase (DESIGN.md §7.1.1 ② "diff 提示・accept/reject")
//! is not yet implemented; for now `inject` only emits the current Core docs.
//! The diff workflow will be added when the chapter-files → graphrag-rs sync
//! logic is wired up alongside `core::run`.

use crate::config::{Project};
use anyhow::{Context, Result};
use std::path::Path;

pub async fn run() -> Result<()> {
    let project = Project::discover()?;

    let purpose_path = project.resolve(&project.config.core.purpose_dir);
    let concept_path = project.resolve(&project.config.core.concept_dir);

    let purpose = read_or_placeholder(&purpose_path, "Purpose")?;
    let concept = read_or_placeholder(&concept_path, "Concept")?;

    println!("# Core ドキュメント注入 (`/spec-inject`)");
    println!();
    println!("対象プロジェクト: `{}`", project.root.display());
    println!();
    println!("## Purpose — `{}`", purpose_path.display());
    println!();
    println!("{}", purpose.trim_end());
    println!();
    println!("## Concept — `{}`", concept_path.display());
    println!();
    println!("{}", concept.trim_end());
    println!();

    Ok(())
}

/// Read the file if present; otherwise return a placeholder so `inject` still
/// emits useful context during initial setup before Core docs exist.
fn read_or_placeholder(path: &Path, label: &str) -> Result<String> {
    if !path.exists() {
        return Ok(format!(
            "*({} 文書が未作成: `{}` を編集してください)*",
            label,
            path.display()
        ));
    }
    std::fs::read_to_string(path)
        .with_context(|| format!("failed to read {}", path.display()))
}
