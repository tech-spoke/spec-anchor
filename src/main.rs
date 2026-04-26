//! spec-grag CLI entry point
//!
//! Three subcommands map to the slash commands defined in DESIGN.md §7:
//!
//! - `spec-grag realign <prompt>` ↔ `/spec-realign <課題プロンプト>`
//! - `spec-grag inject`           ↔ `/spec-inject`
//! - `spec-grag core [--all]`     ↔ `/spec-core [--all]`
//!
//! The CLI is driven by Claude Code slash commands (`.claude/commands/*.md`)
//! that invoke this binary via Bash. Stdout is captured by Claude Code as the
//! tool result and merged into the conversation context (the KV-injection path
//! described in DESIGN.md §4).

use clap::{Parser, Subcommand};

mod commands;
mod config;
mod excitation;

#[derive(Parser, Debug)]
#[command(name = "spec-grag")]
#[command(version)]
#[command(about = "Specification authoring assistant powered by GraphRAG", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Run the specification realignment workflow (`/spec-realign <課題プロンプト>`)
    ///
    /// Implements DESIGN.md §7.1 steps ④〜⑨ on the CLI side. Steps ① (prompt
    /// reception), ② (core sync + injection) and ③ (chapter key-anchor
    /// excitation) involve Claude Code agentic search and are partly handled by
    /// the slash command prompt that drives this CLI.
    Realign {
        /// The challenge prompt describing the issue to address
        prompt: String,

        /// Comma-separated abstract concept keywords (LightRAG high_level).
        /// Repeat the flag or comma-separate to pass multiple keywords.
        #[arg(long, value_delimiter = ',')]
        high: Vec<String>,

        /// Comma-separated concrete entity keywords (LightRAG low_level).
        /// Repeat the flag or comma-separate to pass multiple keywords.
        #[arg(long, value_delimiter = ',')]
        low: Vec<String>,

        /// Per-document max QueryResult count for each keyword (default 3)
        #[arg(long, default_value_t = 3)]
        max_per_doc: usize,
    },

    /// Sync + inject Core documents into the LLM context (`/spec-inject`)
    ///
    /// Reads Purpose and Concept documents and writes them to stdout in a
    /// structured form so Claude Code can absorb them into KV. Concept
    /// differences against the latest chapter files are also surfaced
    /// (or skipped when there is no diff).
    Inject,

    /// Maintain the Concept document
    ///
    /// Without `--all`, performs an incremental update against chapter files
    /// changed since `sources_scanned_through`. With `--all`, runs a full
    /// re-clustering. Purpose is hand-authored and is never updated by this
    /// command.
    Core {
        /// Re-cluster all chapter files from scratch
        #[arg(long, short = 'a')]
        all: bool,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Realign {
            prompt,
            high,
            low,
            max_per_doc,
        } => {
            let inputs = excitation::ExcitationInputs {
                high_level: high,
                low_level: low,
                max_per_doc,
            };
            commands::realign::run(&prompt, inputs).await
        }
        Commands::Inject => commands::inject::run().await,
        Commands::Core { all } => commands::core::run(all).await,
    }
}
