# P3-G2: §2 用語と範囲 残11件

## 実行日時
2026-05-23 JST

| 行 | 内容 | 判定 | 確認方法 |
|---|---|---|---|
| L127 | source_section_id は Sources 全体で一意 | PASS | section_manifest.json で 9件全て一意 |
| L162 | possible_conflict:true フラグのみ立つ（conflicts_with を確定させない） | PASS | Related Sections に possible_conflict=True なし（正常系）|
| L170 | conflict.source_refs[] 存在 | PASS | E4.2 fixture で確認 |
| L171 | conflict.claims[] 存在 | PASS | E4.2 fixture で確認 |
| L172 | conflict.why_conflicting 存在 | PASS | E4.2 fixture で確認 |
| L173 | conflict.why_llm_cannot_decide 存在 | PASS | E4.2 fixture で確認 |
| L174 | conflict.decision_options[] 存在 | PASS | E4.2 fixture で確認 |
| L175 | conflict.status 存在 | PASS | E4.2 fixture で確認 |
| L179 | Core Concept の自動更新が発生しない | PASS | G5/E3 で md5 一致確認 |
| L180 | Source Specs の自動修正が発生しない | PASS | spec-core は Source Specs を書き込まない |
| L181 | LLM による自動 resolved 化が発生しない | PASS | G5 L420 で pending が pending のまま確認 |
