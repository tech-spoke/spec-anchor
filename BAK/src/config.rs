//! Project configuration (`.spec-grag/config.toml`) loader
//!
//! The config layout is defined in DESIGN.md §6.1. The CLI walks up from the
//! current working directory looking for `.spec-grag/config.toml` (analogous to
//! how git locates `.git/`).

use anyhow::{anyhow, Context, Result};
use serde::Deserialize;
use std::path::{Path, PathBuf};

/// Top-level configuration loaded from `.spec-grag/config.toml`
#[derive(Debug, Clone, Deserialize)]
pub struct Config {
    pub sources: Sources,
    pub core: CoreDocs,
    pub graph: Graph,
    pub llm: Llm,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Sources {
    /// Chapter file glob patterns (relative to project root)
    pub include: Vec<String>,
    /// Glob patterns to exclude from chapter files
    #[serde(default)]
    pub exclude: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CoreDocs {
    /// Path to Purpose document. Hand-authored; spec-grag never updates it
    pub purpose_dir: PathBuf,
    /// Path to Concept document. spec-grag updates this with diffs
    pub concept_dir: PathBuf,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Graph {
    /// GraphRAG-rs graph persistence directory (recommended `.gitignore`)
    pub storage: PathBuf,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Llm {
    /// `"claude_cli"` (only currently implemented) | `"codex_cli"` (placeholder)
    pub summary_provider: String,
    pub claude_cli: Option<ClaudeCliSection>,
    pub codex_cli: Option<CodexCliSection>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ClaudeCliSection {
    /// Path to the `claude` binary (defaults to "claude" on PATH)
    pub command: String,
    /// Model alias or full model name (e.g. "sonnet", "opus")
    pub model: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CodexCliSection {
    pub command: String,
    pub model: String,
}

/// Resolved project context: the loaded config plus the project root that
/// contained `.spec-grag/config.toml`
#[derive(Debug, Clone)]
pub struct Project {
    pub root: PathBuf,
    pub config: Config,
}

impl Project {
    /// Walk up from the current working directory looking for
    /// `.spec-grag/config.toml`. Returns the first match.
    pub fn discover() -> Result<Self> {
        let cwd = std::env::current_dir().context("failed to get current directory")?;
        Self::discover_from(&cwd)
    }

    /// Walk up from `start` looking for `.spec-grag/config.toml`
    pub fn discover_from(start: &Path) -> Result<Self> {
        let mut current = start.canonicalize().with_context(|| {
            format!("failed to canonicalize start path: {}", start.display())
        })?;

        loop {
            let candidate = current.join(".spec-grag").join("config.toml");
            if candidate.is_file() {
                let raw = std::fs::read_to_string(&candidate)
                    .with_context(|| format!("failed to read {}", candidate.display()))?;
                let config: Config = toml::from_str(&raw)
                    .with_context(|| format!("failed to parse {}", candidate.display()))?;
                return Ok(Project {
                    root: current,
                    config,
                });
            }

            if !current.pop() {
                break;
            }
        }

        Err(anyhow!(
            "could not locate `.spec-grag/config.toml` from {} or any parent directory",
            start.display()
        ))
    }

    /// Resolve a path stored in the config relative to the project root
    pub fn resolve(&self, p: &Path) -> PathBuf {
        if p.is_absolute() {
            p.to_path_buf()
        } else {
            self.root.join(p)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_minimal_config() {
        let raw = r#"
[sources]
include = ["docs/**/*.md"]

[core]
purpose_dir = "docs/SPEC-grag/core/purpose.md"
concept_dir = "docs/SPEC-grag/core/concept.md"

[graph]
storage = ".spec-grag/graph/"

[llm]
summary_provider = "claude_cli"

[llm.claude_cli]
command = "claude"
model = "sonnet"
"#;
        let cfg: Config = toml::from_str(raw).unwrap();
        assert_eq!(cfg.sources.include, vec!["docs/**/*.md".to_string()]);
        assert_eq!(cfg.llm.summary_provider, "claude_cli");
        assert_eq!(cfg.llm.claude_cli.as_ref().unwrap().model, "sonnet");
    }
}
