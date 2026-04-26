//! Chapter key-anchor excitation via graphrag-rs hierarchical_query.
//!
//! Implements DESIGN.md §7.1.1 step ③:
//! - The main LLM (driver of `/spec-realign`) extracts high_level (abstract
//!   concept) and low_level (concrete entity) keywords from the challenge
//!   prompt + agentic search results, following LightRAG dual-level retrieval.
//! - This module receives those keywords, queries the persisted GraphRAG
//!   document trees through `AsyncGraphRAG::hierarchical_query_grouped`,
//!   and groups results by document (= chapter file) before printing to stdout.
//!
//! The graph itself is built and persisted by `/spec-core` (currently a stub —
//! see HANDOFF.md §2.4). When the graph directory is missing or empty, this
//! module emits a warning to stdout and exits successfully so the realign
//! workflow can still proceed (the LLM falls back to the constraints derived
//! from Core docs alone).

use crate::config::Project;
use anyhow::{Context, Result};
use graphrag_core::async_graphrag::AsyncGraphRAGBuilder;
use graphrag_core::core::DocumentId;
use graphrag_core::generation::claude_cli::ClaudeCliConfig;
use graphrag_core::summarization::QueryResult;
use std::collections::BTreeMap;
use std::path::Path;
use std::time::Duration;

/// Inputs collected from the slash command (or CLI flags).
///
/// Both keyword lists may be empty; in that case excitation is skipped.
#[derive(Debug, Clone, Default)]
pub struct ExcitationInputs {
    pub high_level: Vec<String>,
    pub low_level: Vec<String>,
    /// Per-document max QueryResult count for each keyword. Defaults to 3.
    pub max_per_doc: usize,
}

impl ExcitationInputs {
    pub fn is_empty(&self) -> bool {
        self.high_level.is_empty() && self.low_level.is_empty()
    }
}

/// Run the excitation step: load the persisted graph, query each keyword,
/// group results by document, and write a Markdown report to stdout.
///
/// Returns `Ok(())` even when the graph is missing — emits a warning and lets
/// the realign workflow continue without excitation results.
pub async fn run(project: &Project, inputs: &ExcitationInputs) -> Result<()> {
    println!("## ③ 章別キーアンカーの励起（hierarchical_query）");
    println!();

    if inputs.is_empty() {
        println!("> キーワード未指定。励起をスキップします。");
        println!();
        return Ok(());
    }

    let storage = project.resolve(&project.config.graph.storage);
    if !storage.is_dir() {
        println!(
            "> ⚠ グラフディレクトリ `{}` が存在しません。`spec-grag core --all` でグラフを構築してください。",
            storage.display()
        );
        println!("> 励起なしで以降のフローを継続します。");
        println!();
        return Ok(());
    }

    if is_empty_dir(&storage)? {
        println!(
            "> ⚠ グラフディレクトリ `{}` が空です。`spec-grag core --all` でグラフを構築してください。",
            storage.display()
        );
        println!();
        return Ok(());
    }

    // Build a GraphRAG instance with Claude CLI as the summary LLM.
    // hierarchical_query itself does not invoke the LLM, but `set_language_model`
    // on the builder is the canonical way to instantiate AsyncGraphRAG.
    let claude_config = ClaudeCliConfig {
        command: project
            .config
            .llm
            .claude_cli
            .as_ref()
            .map(|c| c.command.clone())
            .unwrap_or_else(|| "claude".to_string()),
        model: project
            .config
            .llm
            .claude_cli
            .as_ref()
            .map(|c| c.model.clone())
            .unwrap_or_else(|| "sonnet".to_string()),
        extra_args: Vec::new(),
        timeout: Duration::from_secs(120),
    };

    let graphrag = AsyncGraphRAGBuilder::new()
        .with_async_claude_cli(claude_config)
        .build()
        .await
        .context("failed to initialize AsyncGraphRAG with Claude CLI")?;

    let storage_str = storage
        .to_str()
        .context("graph.storage path contains invalid UTF-8")?;
    graphrag
        .load_state_async(storage_str)
        .await
        .with_context(|| format!("failed to load graph state from {storage_str}"))?;

    let tree_count = graphrag.document_tree_count().await;
    if tree_count == 0 {
        println!(
            "> ⚠ ロード済み document tree がありません（`{}`）。",
            storage.display()
        );
        println!();
        return Ok(());
    }

    let max_per_doc = if inputs.max_per_doc == 0 { 3 } else { inputs.max_per_doc };

    // (DocumentId, level) -> Vec<(keyword, QueryResult)>
    let mut grouped: BTreeMap<(String, usize), Vec<(String, QueryResult)>> = BTreeMap::new();
    let mut keyword_hit_counts: BTreeMap<String, usize> = BTreeMap::new();

    let mut all_keywords: Vec<(&str, &str)> = Vec::new();
    for kw in &inputs.high_level {
        all_keywords.push(("high", kw.as_str()));
    }
    for kw in &inputs.low_level {
        all_keywords.push(("low", kw.as_str()));
    }

    for (kind, kw) in &all_keywords {
        let results = graphrag
            .hierarchical_query_grouped(kw, max_per_doc)
            .await
            .with_context(|| format!("hierarchical_query failed for keyword `{kw}`"))?;
        keyword_hit_counts.insert(format!("[{}] {}", kind, kw), results.len());
        for (doc_id, qr) in results {
            grouped
                .entry((doc_id_to_string(&doc_id), qr.level))
                .or_default()
                .push((format!("[{}] {}", kind, kw), qr));
        }
    }

    // Header summary
    println!("**入力キーワード**");
    println!();
    for (kw, count) in &keyword_hit_counts {
        println!("- `{}` → {} hit", kw, count);
    }
    println!();

    if grouped.is_empty() {
        println!("> どのキーワードも document tree とマッチしませんでした。");
        println!();
        return Ok(());
    }

    println!("**章別キーアンカー**");
    println!();

    // We grouped by (doc_id, level). Sort each section by score desc.
    let mut current_doc: Option<String> = None;
    for ((doc, level), mut entries) in grouped {
        entries.sort_by(|a, b| b.1.score.partial_cmp(&a.1.score).unwrap());
        if Some(&doc) != current_doc.as_ref() {
            println!("### `{}`", doc);
            println!();
            current_doc = Some(doc.clone());
        }
        println!("- L{} ({} hit)", level, entries.len());
        for (kw, qr) in entries.iter().take(max_per_doc) {
            let summary = oneline_truncate(&qr.summary, 120);
            let kws = if qr.keywords.is_empty() {
                String::new()
            } else {
                format!(" — keywords: {}", qr.keywords.join(", "))
            };
            println!(
                "  - `{}` (score {:.3}, node `{}`{}): {}",
                kw, qr.score, qr.node_id, kws, summary
            );
        }
    }
    println!();

    Ok(())
}

fn doc_id_to_string(d: &DocumentId) -> String {
    // DocumentId implements Display; format!("{}") is the canonical string form.
    format!("{}", d)
}

fn is_empty_dir(p: &Path) -> Result<bool> {
    let mut iter = std::fs::read_dir(p)
        .with_context(|| format!("failed to read graph storage directory: {}", p.display()))?;
    Ok(iter.next().is_none())
}

fn oneline_truncate(s: &str, max_chars: usize) -> String {
    let one = s.replace('\n', " ").replace('\r', " ");
    let trimmed = one.trim();
    if trimmed.chars().count() <= max_chars {
        trimmed.to_string()
    } else {
        let mut out: String = trimmed.chars().take(max_chars).collect();
        out.push('…');
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn excitation_inputs_empty_detects() {
        let empty = ExcitationInputs::default();
        assert!(empty.is_empty());

        let nonempty = ExcitationInputs {
            high_level: vec!["abstract".into()],
            ..Default::default()
        };
        assert!(!nonempty.is_empty());
    }

    #[test]
    fn oneline_truncate_keeps_short() {
        assert_eq!(oneline_truncate("hello", 10), "hello");
    }

    #[test]
    fn oneline_truncate_collapses_newlines() {
        assert_eq!(oneline_truncate("a\nb\nc", 10), "a b c");
    }

    #[test]
    fn oneline_truncate_handles_multibyte() {
        // Should not panic at byte boundaries
        let _ = oneline_truncate("日本語のテキストです", 3);
    }
}
