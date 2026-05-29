# #9-s01 CLI stdout = valid JSON single object

検証コマンド: `spec-anchor core` を `.spec-anchor/config.toml` が無い空プロジェクトで実行。

意味: このシナリオは「stdout が JSON object 1 個だけで、外部ライブラリの進捗ログや
警告が混入しない」という #9 の契約を確認する。空プロジェクトでは config 不在の
構造化エラー JSON が返るが、検証対象は **stdout の形** (単一 JSON object) であって
コマンドの成否ではない。実モデルまで初期化する成功経路の no-noise 確認は、Qdrant /
FlagEmbedding BGE-M3 を起動した実機が必要 (外部ブロッカー) であり、stdout への
ライブラリ出力リダイレクト機構自体は `test_library_stdout_noise_is_redirected` で
別途確認している。

実 stdout (そのまま貼付、`json.loads` で 1 object としてパース可能):

```json
{
  "auto_dismissed_conflict_count": 0,
  "auto_dismissed_conflict_ids": [],
  "claim_retrieval_diagnostics": {
    "candidate_count": 0,
    "same_section_pair_count": 0,
    "truncated_candidate_sources": [],
    "truncated_pair_count": 0
  },
  "claim_retrieval_status": "failed",
  "conflict_candidate_triage_diagnostics": {
    "send_to_review_count": 0,
    "send_to_review_false_count": 0,
    "triage_truncated_pairs": 0
  },
  "conflict_candidate_triage_status": "failed",
  "conflict_review_items": [],
  "diagnostics": {
    "config_error": {
      "exception_type": "ConfigError",
      "message": ".spec-anchor/config.toml not found under /tmp/claude-1001/tmph8_6mwao",
      "reason_code": "config_error"
    }
  },
  "failed_sections": [],
  "failed_sources": [],
  "freshness_report": {
    "blocking_reasons": [
      "failed_required_artifact"
    ],
    "counts": {
      "required_artifact_problem_count": 1
    },
    "diagnostics": {
      "config_error": {
        "exception_type": "ConfigError",
        "message": ".spec-anchor/config.toml not found under /tmp/claude-1001/tmph8_6mwao",
        "reason_code": "config_error"
      },
      "failed_required_artifacts": [
        "source_specs"
      ],
      "missing_required_artifacts": []
    },
    "required_artifact_problem_count": 1,
    "status": "failed",
    "warnings": [
      ".spec-anchor/config.toml not found under /tmp/claude-1001/tmph8_6mwao"
    ]
  },
  "generated_at": "1970-01-01T00:00:00Z",
  "mode": "incremental",
  "pending_conflict_count": 0,
  "potential_conflicts": [],
  "project_root": "/tmp/claude-1001/tmph8_6mwao",
  "regenerated_chapter_anchors": [],
  "related_sections_status": "blocked",
  "retrieval_index_status": "failed",
  "skipped_sections": [],
  "skipped_sources": [],
  "spec_claims_diagnostics": {
    "claim_limit_reached_sections": [],
    "failed_spec_claim_sections": [],
    "success_no_claims_count": 0,
    "success_with_claims_count": 0
  },
  "spec_claims_status": "failed",
  "stale_resolution_count": 0,
  "status": "failed",
  "unreflected_conflict_resolutions": [],
  "updated_sections": [],
  "updated_sources": [],
  "warnings": [
    ".spec-anchor/config.toml not found under /tmp/claude-1001/tmph8_6mwao"
  ]
}
```
