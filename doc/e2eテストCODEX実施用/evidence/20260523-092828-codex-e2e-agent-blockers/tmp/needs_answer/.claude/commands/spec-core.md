---
description: SPEC-anchor の保持コンテキスト artifact を更新する
argument-hint: "[--all]"
allowed-tools: Bash(spec-anchor core:*)
---

# /spec-core

正本は SPEC-anchor の外部 command contract と SPEC-anchor CLI の入出力である。この Claude command template は、Agent がその契約をどう呼び出すかだけを示す。

すべての `spec-anchor` CLI 呼び出しは現在の作業ディレクトリ (cwd) を project root として実行する。親ディレクトリ、別プロジェクト、記憶にある他のパスを探索してはならない。`.spec-anchor/config.toml` の有無を事前確認して CLI 実行を省略してはならない。CLI を実行し、CLI が返すエラー JSON を利用者に伝達する。

project root で `spec-anchor core` を実行する。`--all` または `-a` は、ユーザーが full rebuild を明示した場合だけ追加する。`.spec-anchor/config.toml` の `[llm.stage_routing]` が H-4 calibration で確定した stage 別最適 model / effort (`section_metadata` / `related_sections` / `conflict_review` / `chapter_key_anchor`) を適用する。`--llm-provider` を明示すると stage_routing が上書きされるので、特別な事情がない限り指定しない。

`/spec-core` は SPEC-anchor の保持 artifact を生成または更新する: Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor、Source Retrieval Index、Conflict Review Items。

実行後は、後続作業に必要な CoreResult field を確認して報告する: `updated_sources`, `failed_sources`, `failed_sections`, `retrieval_index_status`, `freshness_report`, `pending_conflict_count`, `conflict_review_items`, `unreflected_conflict_resolutions`, `stale_resolution_count`。

pending Conflict Review Items が残る場合、`conflict_id`, `severity`, `source_refs`, `claims`, `why_conflicting`, `why_llm_cannot_decide`, `decision_options`, `recommended_next_action` を人間判断用に提示する。pending conflict を Agent が決めない。

Purpose と Core Concept は人間が維持する read-only input である。この command から `/spec-inject` や `/spec-realign` を自動実行しない。CLI result と、人間判断が必要な pending Conflict Review Items を返す。

## エラー時の復旧手順を明示する規約

CLI が失敗を返した場合、ユーザー向けの復旧手順は具体的な command 名で提示する。略称や類似 command を提案しない。

- `.spec-anchor/config.toml not found under {root}` のとき → `spec-anchor-setup-project --target <project_root>` を提案する (例: `spec-anchor-setup-project --target /path/to/project`)。`spec-anchor init` のような存在しない command を提案しない。
- `core.purpose_file not found: ...` / `core.concept_file not found: ...` のとき → 該当ファイル (`docs/core/purpose.md` 等) を人間が作成して再実行することを提案する。Agent は Purpose / Core Concept を書かない。
- `sources.include did not match any Source Specs` のとき → `.spec-anchor/config.toml` の `[sources].include` glob を修正するか、Source Specs を該当 path に配置することを提案する。
- `Chapter Anchors LLM generation failed for {N} chapter(s); ...` のとき → `spec-anchor core --all` (または `/spec-core --all`) で再試行を提案する。
- `Related Sections retrieval backend failure: ...` のとき → Qdrant service の起動状態を確認し、`spec-anchor core --rebuild` (または `/spec-core --rebuild`) で再構築を提案する。
- `Source Retrieval Index update failed` / `Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild` のとき → `spec-anchor core --rebuild` (または `/spec-core --rebuild`) を提案する。
