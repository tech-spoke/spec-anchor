---
description: SPEC-grag の保持コンテキスト artifact を更新する
argument-hint: "[--all]"
allowed-tools: Bash(spec-grag core:*)
---

# /spec-core

正本は SPEC-grag の外部 command contract と SPEC-grag CLI の入出力である。この Claude command template は、Agent がその契約をどう呼び出すかだけを示す。

project root で `spec-grag core` を実行する。`--all` または `-a` は、ユーザーが full rebuild を明示した場合だけ追加する。`.spec-grag/config.toml` の `[llm.stage_routing]` が H-4 calibration で確定した stage 別最適 model / effort (`section_metadata` / `related_sections` / `conflict_review`) を適用する。`--llm-provider` を明示すると stage_routing が上書きされるので、特別な事情がない限り指定しない。

`/spec-core` は SPEC-grag の保持 artifact を生成または更新する: Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor、Source Retrieval Index、Conflict Review Items。

実行後は、後続作業に必要な CoreResult field を確認して報告する: `updated_sources`, `failed_sources`, `failed_sections`, `retrieval_index_status`, `freshness_report`, `pending_conflict_count`, `conflict_review_items`, `unreflected_conflict_resolutions`, `stale_resolution_count`。

pending Conflict Review Items が残る場合、`conflict_id`, `severity`, `source_refs`, `claims`, `why_conflicting`, `why_llm_cannot_decide`, `decision_options`, `recommended_next_action` を人間判断用に提示する。pending conflict を Agent が決めない。

Purpose と Core Concept は人間が維持する read-only input である。この command から `/spec-inject` や `/spec-realign` を自動実行しない。CLI result と、人間判断が必要な pending Conflict Review Items を返す。
