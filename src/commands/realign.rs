//! `/spec-realign <prompt>` — Specification realignment workflow
//!
//! Implements DESIGN.md §7.1. Most of the heavy work happens in the slash
//! command prompt that drives this CLI (Agentic search, KeywordExtractor,
//! result drafting). This binary handles the deterministic plumbing:
//!
//! - Project resolution
//! - Forwarding the challenge prompt to graphrag-rs for excitation (TODO)
//! - Surfacing Core docs alongside the challenge prompt for the LLM
//!
//! Full implementation of steps ⑥〜⑨ (waveform derivation, audit subagent,
//! final answer) lives in the slash command prompt and the audit subagent.

use crate::commands::inject;
use crate::config::Project;
use crate::excitation::{self, ExcitationInputs};
use anyhow::Result;

pub async fn run(prompt: &str, excitation_inputs: ExcitationInputs) -> Result<()> {
    println!("# `/spec-realign` — 仕様編集ワークフロー");
    println!();
    println!("## ① 課題プロンプト");
    println!();
    println!("{}", prompt);
    println!();

    // ② コア同期 + 注入: 当面は inject を直接呼ぶ。Concept 差分提示は未実装
    inject::run().await?;

    // ③ 章別キーアンカーの励起。グラフ未構築 or キーワード未指定なら excitation::run 内で
    // warning + skip。後段（④〜⑨）はスラッシュコマンドのプロンプトと監査役 subagent で組む。
    let project = Project::discover()?;
    excitation::run(&project, &excitation_inputs).await?;

    println!("## TODO: ④〜⑨ 守るべき制約導出 / 解決案 / 波及検査 / 監査役");
    println!();
    println!(
        "③ で得られた章別キーアンカーを踏まえて、メイン LLM が ④ 以降を駆動する。\
         監査役 subagent と最終案提示はスラッシュコマンド側で実装予定。"
    );
    println!();

    Ok(())
}
