//! `/spec-core [--all]` — Concept document maintenance
//!
//! DESIGN.md §7.3:
//! - Without `--all`: incremental update against chapter files changed since
//!   `sources_scanned_through`. Diff against the Concept document is presented
//!   for hunk-level accept/reject.
//! - With `--all`: full re-clustering of all chapter files from scratch.
//!
//! Purpose is hand-authored and is never updated by this command.
//!
//! Implementation status: stub — the chapter-files → graphrag-rs feed and the
//! Concept-diff workflow are not yet wired up. The current run only surfaces
//! the resolved project state and the chapter files that would be processed.

use crate::config::Project;
use anyhow::Result;
use std::path::Path;

pub async fn run(all: bool) -> Result<()> {
    let project = Project::discover()?;

    println!("# `/spec-core` — Core 文書メンテナンス");
    println!();
    println!("対象プロジェクト: `{}`", project.root.display());
    println!(
        "モード: **{}**",
        if all {
            "--all (再クラスタリング)"
        } else {
            "incremental (差分更新)"
        }
    );
    println!();

    println!("## 章ファイル群");
    println!();
    println!("`include` パターン:");
    for p in &project.config.sources.include {
        println!("- `{}`", p);
    }
    if !project.config.sources.exclude.is_empty() {
        println!();
        println!("`exclude` パターン:");
        for p in &project.config.sources.exclude {
            println!("- `{}`", p);
        }
    }

    let matches = collect_sources(&project)?;
    println!();
    println!(
        "マッチしたファイル: **{} 件**",
        matches.len()
    );
    if !matches.is_empty() {
        for path in matches.iter().take(10) {
            println!("- `{}`", path.display());
        }
        if matches.len() > 10 {
            println!("- ... (他 {} 件)", matches.len() - 10);
        }
    }
    println!();

    println!("## TODO");
    println!();
    println!(
        "- 変更ファイル抽出 (sources_scanned_through 比較)\n\
         - graphrag-rs への feed と差分計算 (delta_computation)\n\
         - Concept 更新案の diff 提示 + accept/reject\n\
         - `--all` 時の再クラスタリングと Concept 文書の再生成"
    );
    println!();

    Ok(())
}

/// Walk include patterns and return matching files (minus exclude)
fn collect_sources(project: &Project) -> Result<Vec<std::path::PathBuf>> {
    use anyhow::Context;
    let mut results = Vec::new();
    let mut seen = std::collections::HashSet::new();

    // glob で include 展開済みなので、include の二重チェックは不要。exclude のみ判定する
    let exclude_globs: Vec<glob::Pattern> = project
        .config
        .sources
        .exclude
        .iter()
        .map(|p| glob::Pattern::new(p))
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to compile exclude pattern")?;

    for pattern in &project.config.sources.include {
        let absolute = project.root.join(pattern);
        let pattern_str = absolute
            .to_str()
            .context("non-UTF-8 path in include pattern")?;

        for entry in glob::glob(pattern_str).with_context(|| {
            format!("failed to expand glob pattern: {}", pattern_str)
        })? {
            let path = match entry {
                Ok(p) => p,
                Err(_) => continue,
            };
            if !path.is_file() {
                continue;
            }
            let rel = path
                .strip_prefix(&project.root)
                .unwrap_or(&path)
                .to_path_buf();
            if exclude_globs.iter().any(|g| matches_against(g, &rel)) {
                continue;
            }
            if seen.insert(path.clone()) {
                results.push(path);
            }
        }
    }

    results.sort();
    Ok(results)
}

fn matches_against(pattern: &glob::Pattern, rel: &Path) -> bool {
    rel.to_str()
        .map(|s| pattern.matches(s))
        .unwrap_or(false)
}
