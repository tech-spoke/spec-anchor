"""Registry of E2E user-facing-output scenarios.

Each scenario ties a ``scenario_id`` (``#<subtask>-s<NN>``) to the evidence
snapshot under ``snapshots/`` and the human-facing content that snapshot must
contain. The pytest module :mod:`tests.e2e.test_user_facing_output` is driven
entirely by this registry, so adding a scenario means adding one entry here plus
its snapshot file.

Fields per :class:`Scenario`:

* ``snapshot`` — filename under ``snapshots/`` (the Agent-formatted final reply).
* ``required`` — substrings that must be present (human-facing content the
  scenario is meant to prove is shown).
* ``allow`` — forbidden substrings tolerated for this scenario, each justified.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    subtask: str
    summary: str
    snapshot: str
    required: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()
    # "user_facing": Agent-formatted reply — forbidden-term + required-content
    #   checked. "cli_json": raw CLI stdout JSON evidence — validated as a single
    #   JSON object, NOT forbidden-term checked (internal field names are the
    #   CLI's by design; the Agent translates them in the user_facing snapshots).
    kind: str = "user_facing"


SCENARIOS: tuple[Scenario, ...] = (
    # Scenarios are registered per-Phase as their evidence snapshots are
    # authored. #1 / #5 / #7 / #10 scenarios join this tuple when those sub
    # tasks are implemented (keeps the suite green at every phase commit).

    # --- #2 stop-time output templates ---------------------------------------
    Scenario(
        "#2-s01", "#2", "① 初期設定未完了 (config.toml 不在) を /spec-core で表示",
        "#2-s01_stop_setup_missing_config_spec_core.md",
        required=("初期設定が完了していません", "spec-anchor-setup-project"),
    ),
    Scenario(
        "#2-s02", "#2", "② 外部サービス必要 (Qdrant 接続失敗) を /spec-inject で表示",
        "#2-s02_stop_qdrant_unavailable_spec_inject.md",
        required=("外部サービス", "Qdrant"),
    ),
    Scenario(
        "#2-s03", "#2", "③ 保持物更新必要 (dirty source) を /spec-inject で表示",
        "#2-s03_stop_dirty_source_spec_inject.md",
        required=("保持物の更新が必要", "/spec-core"),
    ),
    Scenario(
        "#2-s04", "#2", "④ 保持物の更新中・待機 を /spec-inject で表示",
        "#2-s04_stop_watcher_running_spec_inject.md",
        required=("更新中", "完了を待"),
    ),
    Scenario(
        "#2-s05", "#2", "⑥ ツール側のエラー を /spec-core で表示",
        "#2-s05_stop_tool_error_spec_core.md",
        required=("ツール側", "開発元"),
    ),
    Scenario(
        "#2-s06", "#2", "◇ 情報通知 (補助保持物のみ劣化) で続行可能",
        "#2-s06_info_degraded_optional_continue.md",
        required=("続行できます", "参考情報"),
    ),
    Scenario(
        "#2-s07", "#2", "3 コマンド一貫性: ③ で 3 コマンド同テンプレ",
        "#2-s07_stop_dirty_three_commands_consistency.md",
        required=("/spec-core", "/spec-inject", "/spec-realign", "保持物の更新が必要"),
    ),
    Scenario(
        "#2-s08", "#2", "禁止用語横断チェック (#2-s01〜07)",
        "#2-s08_forbidden_terms_cross_check.md", kind="note",
        required=("禁止用語",),
    ),

    # --- #3 pending conflict body expansion ----------------------------------
    Scenario(
        "#3-s01", "#3", "pending conflict 1 件 / 単一 claim pair",
        "#3-s01_pending_conflict_single_pair.md",
        required=("人間判断が必要な仕様の衝突", "主張 A", "主張 B", "論点", "選択肢", "次の操作"),
    ),
    Scenario(
        "#3-s02", "#3", "pending conflict 1 件 / 3 件以上の claims",
        "#3-s02_pending_conflict_three_claims.md",
        required=("主張 A", "主張 B", "主張 C"),
    ),
    Scenario(
        "#3-s03", "#3", "pending conflict 複数件 (連番 1./2.)",
        "#3-s03_pending_conflict_multiple.md",
        required=("人間判断が必要な仕様の衝突", "1.", "2."),
    ),
    Scenario(
        "#3-s04", "#3", "pending conflict + 保持物更新必要 の混在",
        "#3-s04_pending_conflict_with_dirty_source.md",
        required=("保持物の更新が必要", "人間判断が必要な仕様の衝突"),
    ),
    Scenario(
        "#3-s05", "#3", "3 コマンド一貫性: pending conflict 同フォーマット",
        "#3-s05_pending_conflict_three_commands.md",
        required=("/spec-core", "/spec-inject", "/spec-realign", "人間判断が必要な仕様の衝突"),
    ),

    # --- #4 needs-agent-answer hide (auto-rerun) ------------------------------
    Scenario(
        "#4-s01", "#4", "答案なし → 自動再実行 → 整形済み RealignResult (内部信号なし)",
        "#4-s01_realign_auto_rerun_clean.md",
        required=("今回守る制約", "課題プロンプトへの回答または修正案"),
    ),
    Scenario(
        "#4-s02", "#4", "自動再実行が利用者に見えない (メタ説明なし)",
        "#4-s02_realign_auto_rerun_no_meta.md",
        required=("今回守る制約",),
    ),

    # --- #6 retry policy (depends on #5) -------------------------------------
    Scenario(
        "#6-s01", "#6", "構造化失敗 → CLI error で修正 → 2 回目成功 → 整形済み RealignResult",
        "#6-s01_retry_success_after_fix.md",
        required=(
            "今回守る制約",
            "今回扱う修正候補または検討対象",
            "競合 / 不確実性 / 人間レビューが必要な点",
            "課題プロンプトへの回答または修正案",
        ),
    ),
    Scenario(
        "#6-s02", "#6", "構造化失敗 → リトライ → 再失敗 → ⑥ 表示 (最後の答案 + 差分併記)",
        "#6-s02_retry_exhausted_tool_error.md",
        required=("ツール側", "開発元", "期待された形式との差分", "最後に送った回答候補"),
    ),

    # --- #5 realign CLI error detail (raw CLI error block) -------------------
    Scenario(
        "#5-s01", "#5", "不正答案 (final 区分なし) → error.code=missing_final_section",
        "#5-s01_realign_error_missing_final_section.md", kind="cli_json",
        required=("missing_final_section", "課題プロンプトへの回答または修正案"),
    ),
    Scenario(
        "#5-s02", "#5", "不正答案 (evidence_origin 不正値) → invalid_evidence_origin",
        "#5-s02_realign_error_invalid_evidence_origin.md", kind="cli_json",
        required=("invalid_evidence_origin", "constraints[0].evidence_origin"),
    ),
    Scenario(
        "#5-s03", "#5", "不正答案 (support_refs 型違反) → invalid_support_refs_type",
        "#5-s03_realign_error_invalid_support_refs_type.md", kind="cli_json",
        required=("invalid_support_refs_type", "constraints[0].support_refs"),
    ),
    Scenario(
        "#5-s04", "#5", "正常答案 → error block なし RealignResult",
        "#5-s04_realign_valid_no_error_block.md", kind="cli_json",
        required=("今回守る制約",),
    ),

    # --- #9 CLI stdout = single JSON object (raw CLI evidence) ----------------
    Scenario(
        "#9-s01", "#9", "spec-anchor core stdout が valid JSON 単体",
        "#9-s01_core_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s02", "#9", "spec-anchor inject-search stdout が valid JSON 単体",
        "#9-s02_inject_search_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s03", "#9", "spec-anchor inject-section stdout が valid JSON 単体",
        "#9-s03_inject_section_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s04", "#9", "spec-anchor inject-chapters stdout が valid JSON 単体",
        "#9-s04_inject_chapters_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s05", "#9", "spec-anchor inject-purpose stdout が valid JSON 単体",
        "#9-s05_inject_purpose_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s06", "#9", "spec-anchor inject-conflicts stdout が valid JSON 単体",
        "#9-s06_inject_conflicts_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s07", "#9", "spec-anchor realign stdout が valid JSON 単体",
        "#9-s07_realign_stdout_single_json.md", kind="cli_json",
    ),
    Scenario(
        "#9-s08", "#9", "stdout に HF / FlagEmbedding / progress bar 由来文字列が含まれない",
        "#9-s08_stdout_no_progress_noise.md", kind="note",
        required=("test_library_stdout_noise_is_redirected", "stderr"),
    ),
    Scenario(
        "#9-s09", "#9", "stderr 側に warning / progress 等が出ている (副作用確認)",
        "#9-s09_stderr_carries_noise.md", kind="note",
        required=("stderr", "Fetching 30 files"),
    ),
)


SCENARIOS_BY_ID = {scenario.scenario_id: scenario for scenario in SCENARIOS}
