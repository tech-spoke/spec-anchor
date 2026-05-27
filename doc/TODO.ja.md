# 開放 TODO 一覧

このファイルは、次のセッション以降で実装する未解決 task だけを置く。

過去に完了済みの TODO block はこのファイルへ戻さない。完了済み履歴を参照する必要がある場合は、`doc/OLD/TODO.ja.md` または該当 commit を確認する。

各 task は次の構造で書く:

- 背景
- 真因 / 対応方針
- 目的
- 実装方針
- 検証条件
- 触れる主なファイル
- 完了条件
- 依存 / scope 外

## 開放中

優先順位:

1. **T-conflict-source-update-flow**: Source Specs 修正後に pending Conflict Review Item が残り続ける user-facing workflow 不整合の修正

### T-conflict-source-update-flow: Source Specs 修正後に pending Conflict Review Item が残り続ける user-facing workflow 不整合の修正

#### 背景

2026-05-27 の Claude / Codex 監査会話で、利用者視点の懸念が出た。

利用者が直接触るのは `/spec-core`、`/spec-inject`、`/spec-realign`、Codex skill の `spec-anchor` であり、内部 CLI の細部ではない。したがって、未解決 Conflict Review Item はチャット上に十分な情報として提示され、利用者が Source Specs / Purpose / Core Concept を修正してから `/spec-core` または `spec-anchor-watch` によって保持物を更新すれば、更新後も実際に残る conflict だけが blocker として残る必要がある。

監査結果:

| ID | 指摘 | disposition | 根拠 / 残作業 |
| --- | --- | --- | --- |
| C-1 | pending Conflict Review Item の表示項目がチャットに出るか | 既対応 / regression test は必要 | `.claude/commands/spec-inject.md`、`.claude/commands/spec-realign.md`、`.codex/skills/spec-anchor/SKILL.md` は `conflict_id` / `severity` / `claims` / `why_conflicting` / `why_llm_cannot_decide` / `decision_options` / `source_refs` / `recommended_next_action` の提示を要求している。今後の drift 防止 test は本 task に含める |
| C-2 | 利用者が Source Specs を修正して `/spec-core` または watch を走らせた後、解消済み pending conflict が消えるか | 採用 / 修正必要 | `evaluate_conflicts()` は LLM judge が「もう pending ではない」と返した結果を `potential_conflicts` warning に入れるだけで、既存 pending item を消す signal を返さない。`_merge_conflict_items()` は既存 pending item を無条件に残す |
| C-3 | 適切な制約が注入されるか | 部分採用 / guard 強化必要 | template は `evidence_origin` enum と Section Summary / Search Keys / Related Sections / Chapter Key Anchor の単独根拠禁止を要求している。ただし CLI は constraints JSON の構造・真偽を検証しないため、Agent / LLM の自己点検に依存している |
| C-4 | template は重要な source の一部なのに LLM が軽視しがち | 採用 / drift 防止必要 | Claude command template と Codex skill template は user-facing contract の実体である。`spec_anchor/templates/.claude/commands/*.md` と `.claude/commands/*.md`、`spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md` と `.codex/skills/spec-anchor/SKILL.md` の parity と必須文言を test する |
| C-5 | 既存 `dismiss` decision と source 修正後の自動 dismiss の意味が混ざる | 採用 / schema 明確化が必要 | `resolution.decision="dismiss"` は維持するが、`resolution.decision_origin` で `human` と `auto_source_update` を区別する。既存 item で field が無い場合は `human` 相当として扱う |
| C-6 | section_id 変更 / section 削除で既存 `conflict_id` が dangling になる | 採用 / 検証追加が必要 | `conflict_id` は section_id 由来なので、見出し slug 変更や section 削除では同一 id の non-pending signal が来ない。current source hash map に旧 source ref が無い場合の自動 dismiss 条件を追加する |
| C-7 | `spec-anchor-watch` が同じ更新経路か曖昧 | 採用 / 実装経路を明記 | `spec_anchor/watcher.py` は `run_spec_core_for_watcher` を直接 import して呼ぶ。subprocess ではないため、この直接呼び出し経路にも同じ pending 解除処理が適用されることを test する |
| C-8 | source 修正で何件自動解除されたか利用者が観測できない | 採用 / CoreResult field 追加 | `auto_dismissed_conflict_count` と `auto_dismissed_conflict_ids[]` を CoreResult に追加し、`/spec-core` 後に自動解除が見えるようにする |
| C-9 | 外部設計書の追記箇所と文言が task 内に未記載 | 採用 / ドラフトを TODO 内に固定 | `doc/EXTERNAL_DESIGN.ja.md` §3.3 と §7 decision 表直後に入れる文言ドラフトを本 task に持つ。`needs_source_update` は「人間が source 修正を選ぶ pending decision」、自動 dismiss は「修正後の再評価結果」として分ける |
| C-10 | 自動 dismiss 時の audit trail field が未定義 | 採用 / schema 明確化が必要 | `resolution.applied_at`、`resolution.previous_status`、`resolution.decision_origin`、`resolution.auto_dismiss_reason` を規約化する |

#### 真因 / 対応方針

真因 (確定):

- `spec_anchor/conflict_review.py` の `evaluate_conflicts()` は、judge の `outcome` が `needs_human_review` / `unresolved` / `pending` の場合だけ `conflict_review_items` に pending item を返す。それ以外の outcome は `potential_conflicts` warning になり、同じ `conflict_id` の pending item を解除する情報として扱われない。
- `spec_anchor/core.py` の `_merge_conflict_items(existing, new)` は既存 item を先に `merged[conflict_id] = current` で保持する。`new` に同じ `conflict_id` の pending item が無い場合でも、既存 pending item は残る。
- `refresh_conflict_resolution_staleness()` は `resolved` / `dismissed` の stale 判定を扱うが、`pending` の「根拠 source が変わったので再評価済みで解除できるか」を扱わない。
- `doc/EXTERNAL_DESIGN.ja.md` §3.3 は「Source Specs の変更と未解決 Conflict が同時にある場合、まず `/spec-core` で保持物を更新する。更新後に残る Conflict のみが人間判断対象」と読めるが、現在の実装はこの user-facing contract を満たさない。

対応方針 (確定):

- `evaluate_conflicts()` は non-pending outcome について、同じ `conflict_id` の既存 pending item を解除するための machine-readable signal を返す。この signal は `conflict_id`、source pair、judge outcome、解除理由、現在の source hash を含む。
- 既存 pending item は、Source Specs / Purpose / Core Concept の source hash が変わった場合だけ自動解除対象にする。source hash が変わっていない場合、provider の再判定結果だけでは自動解除しない。これにより LLM judge の揺れで人間判断待ち blocker が消えることを防ぐ。
- 同じ `conflict_id` の non-pending signal がある既存 pending item は、`status="dismissed"`、`resolution.decision="dismiss"`、`resolution.decision_origin="auto_source_update"`、`resolution.auto_dismiss_reason="source_update_recheck_non_pending"` として blocker から外す。item は `conflict_review_items.json` に残し、監査履歴を削除しない。
- Related Sections の再生成結果から pair 自体が消えた場合も、既存 pending item の `base_source_hashes` に含まれる Source Specs / Purpose / Core Concept の少なくとも 1 つが変わっている場合だけ、同じく `status="dismissed"`、`resolution.decision="dismiss"`、`resolution.decision_origin="auto_source_update"` として blocker から外す。この場合の `resolution.auto_dismiss_reason` は `source_update_recheck_pair_absent` とする。source hash が変わっていない場合は pending のまま残す。
- 既存 pending item の `base_source_hashes` に含まれる source ref が現在の source hash map に存在しない場合は、source hash 変化と同じ扱いにする。これにより heading slug 変更による section_id 変更、または section 削除で dangling になった既存 pending item を、現在の conflict candidate に残っていない場合だけ自動 dismiss できる。
- blocker から外した item の `base_source_hashes` は、解除判断に使った現在の source hash に更新する。これにより解除直後に `stale_resolution=true` になることを避ける。
- 新しい `status` は追加しない。既存の `pending` / `resolved` / `dismissed` だけを使う。ただし `doc/EXTERNAL_DESIGN.ja.md` には、Source Specs / Purpose / Core Concept 修正後の `/spec-core` が既存 pending item を `dismissed` にできる条件を明記する。
- 人間が `--decision-json` / `--decision-file` で渡した `dismiss` と自動 dismiss は、`resolution.decision_origin` で区別する。人間 decision 由来は `decision_origin="human"` とし、既存 JSON に field が無い resolved / dismissed item は backward compatible に `human` 相当として扱う。
- 自動 dismiss の `resolution` には、`applied_at`、`previous_status="pending"`、`decision_origin="auto_source_update"`、`auto_dismiss_reason`、`referenced_source_refs`、`valid_scope="global"` を入れる。
- `/spec-core` の CoreResult には `auto_dismissed_conflict_count` と `auto_dismissed_conflict_ids[]` を追加し、Source Specs / Purpose / Core Concept 修正後に何件の pending Conflict Review Item が blocker から外れたかを利用者が確認できるようにする。
- constraints JSON の意味論的真偽を CLI が完全検証する機能は今回追加しない。今回の guard 強化は、template parity、pending conflict 必須 label、`evidence_origin` enum、support-only evidence 禁止を static test で検出する範囲に固定する。

外部設計書追記ドラフト:

```text
§3.3 追記:
Source Specs / Purpose / Core Concept の変更後に `/spec-core` または `spec-anchor-watch` が保持物を更新した場合、SPEC-anchor は既存 pending Conflict Review Item を現在の source hash と conflict evaluation 結果で再評価する。根拠 source の hash が変化した、または根拠 source ref が削除された既存 pending item について、同じ conflict pair が non-pending 判定になるか、現在の conflict candidate から消えた場合、`/spec-core` はその item を `status="dismissed"`、`resolution.decision_origin="auto_source_update"` として blocker から外す。source hash が変わっていない pending item は、LLM judge の再判定だけでは自動解除しない。

§7 decision 表直後に追記:
`needs_source_update` は、人間が Source Specs / Purpose / Core Concept の修正を必要と判断したことを記録する pending decision である。修正後の `/spec-core` 再評価により conflict が解消された場合、SPEC-anchor は該当 pending item を `dismissed` に遷移できる。この自動遷移は人間 decision の `dismiss` とは区別し、`resolution.decision_origin="auto_source_update"`、`resolution.previous_status="pending"`、`resolution.applied_at=<timestamp>`、`resolution.auto_dismiss_reason=<reason>` を持つ。
```

#### 目的

利用者が pending conflict を提示された後に Source Specs / Purpose / Core Concept を修正し、`/spec-core` または `spec-anchor-watch` で保持物を更新した場合、更新後も実際に未解決の conflict だけが `/spec-inject` / `/spec-realign` を停止させる状態にする。

合格基準:

- Source Specs 修正により LLM judge が non-pending outcome を返す同一 pair の既存 pending Conflict Review Item は、次回 `spec-anchor core` 後に `pending_conflict_count` へ含まれない。
- Source Specs 修正により Related Sections pair が候補から消えた既存 pending Conflict Review Item は、source hash 変化を条件に `status="dismissed"` となり、`pending_conflict_count` へ含まれない。source hash が変わっていない場合は解除しない。
- section_id 変更または section 削除で既存 pending item の source refs が現在の source hash map から消え、かつ現在の conflict candidate に同じ pair が残らない場合、その item は `status="dismissed"`、`resolution.decision_origin="auto_source_update"` となり、`pending_conflict_count` へ含まれない。
- `spec-anchor inject-*` / `spec-anchor realign` の freshness gate は、解除済み item を `pending_conflict_items` に出さない。
- `spec-anchor core` の CoreResult は、自動 dismiss の件数と id を `auto_dismissed_conflict_count` / `auto_dismissed_conflict_ids[]` で返す。
- Claude command template と Codex skill template に、pending conflict の必須 label と constraints 根拠ルールが残っていることを test で検出できる。

#### 実装方針

1. `evaluate_conflicts()` の戻り値に、judge が non-pending outcome を返した pair の `conflict_id` / source pair / outcome / reason を machine-readable な diagnostics として追加する。
2. `_merge_conflict_items()` またはその前段に、既存 pending item を現在の conflict evaluation 結果で再評価する処理を追加する。
3. 同じ `conflict_id` の non-pending signal があり、かつ既存 item の `base_source_hashes` に含まれる Source Specs / Purpose / Core Concept の少なくとも 1 つが変わっている場合、既存 pending item を `status="dismissed"` にする。
4. 同じ pair が今回の candidate から消え、かつ既存 item の `base_source_hashes` に含まれる Source Specs / Purpose / Core Concept の少なくとも 1 つが変わっている場合、既存 pending item を `status="dismissed"` にする。
5. 自動 dismiss では `resolution.decision="dismiss"`、`resolution.decision_origin="auto_source_update"`、`resolution.previous_status="pending"`、`resolution.applied_at=<timestamp>`、`resolution.auto_dismiss_reason`、`resolution.reason`、`resolution.referenced_source_refs` を記録する。`base_source_hashes` は現在の source hash に更新する。
6. source hash が変わっていない既存 pending item は、non-pending signal があっても pending のまま残す。
7. `spec_anchor/core.py` の CoreResult に `auto_dismissed_conflict_count` と `auto_dismissed_conflict_ids[]` を追加する。
8. `doc/EXTERNAL_DESIGN.ja.md` に、上記「外部設計書追記ドラフト」の内容を反映する。
9. `spec-anchor-watch` は `spec_anchor/watcher.py` で `run_spec_core_for_watcher` を直接 import して呼ぶため、この直接呼び出し経路にも同じ pending 解除処理と CoreResult field が適用されることを test する。watch の長時間実行が必要な場合は unit / integration を分ける。
10. template / skill drift 防止として、Claude command / Codex skill の installed copy と packaged template の parity、pending conflict の必須 label、constraints 根拠ルールの必須文言を static assertion で確認する test を追加する。

#### 検証条件

A. **既存 pending item の解除**

- `tests/test_spec_core.py` に、1 回目 `FakeSpecCoreProvider("unresolved")` で pending item を作り、Source Specs を修正し、2 回目 `FakeSpecCoreProvider("resolved")` または non-pending outcome provider で `spec-anchor core` を実行したとき、該当 `conflict_id` が `pending_conflict_count` に含まれないことを確認する test を追加する。
- 同じ source hash のまま provider だけが non-pending を返す場合は、既存 pending item が残ることを確認する。
- 自動 dismiss された item の `resolution.decision_origin`、`resolution.previous_status`、`resolution.applied_at`、`resolution.auto_dismiss_reason`、`resolution.referenced_source_refs`、`base_source_hashes` が期待どおりであることを確認する。
- CoreResult の `auto_dismissed_conflict_count` と `auto_dismissed_conflict_ids[]` が自動 dismiss 件数と id を返すことを確認する。

B. **pair が消えた場合の解除**

- Related Sections candidate から該当 pair が消えた fixture を作り、Source Specs の source hash が変わった場合だけ既存 pending item が `status="dismissed"` になり blocker から外れることを確認する。
- source hash が変わらない場合は、既存 pending item が残ることを確認する。
- heading slug 変更で section_id が変わり、既存 pending item の `source_refs` が現在の source hash map で見つからない場合に、現在の conflict candidate に同じ pair が無ければ `status="dismissed"` になることを確認する。
- section 削除で既存 pending item の `source_refs` が dangling になった場合に、現在の conflict candidate に同じ pair が無ければ `status="dismissed"` になることを確認する。

C. **freshness gate**

- `tests/test_freshness.py` または `tests/test_spec_inject.py` で、解除済み item が `pending_conflict_items` に含まれないことを確認する。
- dirty / stale と pending conflict が同時にある場合は、従来どおり先に `/spec-core` 実行を促し、古い pending item details を出さないことを維持する。

D. **template / skill regression**

- `.claude/commands/spec-inject.md` と `spec_anchor/templates/.claude/commands/spec-inject.md` が一致することを確認する。
- `.claude/commands/spec-realign.md` と `spec_anchor/templates/.claude/commands/spec-realign.md` が一致することを確認する。
- `.codex/skills/spec-anchor/SKILL.md` と `spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md` が一致することを確認する。
- pending conflict の 8 label、item 側 `recommended_next_action` の literal 出力要求、constraints 根拠ルールの必須文言を static assertion で確認する。

E. **既存 pytest**

- `pytest --skip-external` を実行し、既存 unit / integration test が pass すること。
- 実 Qdrant / BGE-M3 / real provider が必要な検証は、未実行なら未完了 TODO として報告し、fake provider の passing だけで実動作完了扱いにしない。

F. **watch 経路**

- `spec_anchor/watcher.py` の `run_spec_core_for_watcher` 直接呼び出し経路で、Source Specs 修正後の自動 dismiss と CoreResult の `auto_dismissed_conflict_count` / `auto_dismissed_conflict_ids[]` が同じように得られることを確認する。

#### 触れる主なファイル

- `spec_anchor/conflict_review.py`: non-pending outcome の machine-readable diagnostics / 既存 pending item 再評価用 metadata
- `spec_anchor/core.py`: `_merge_conflict_items()` またはその前後の pending 解除処理、CoreResult の `auto_dismissed_conflict_count` / `auto_dismissed_conflict_ids[]`
- `spec_anchor/freshness.py`: `pending_conflict_items()` / gate 出力の確認。必要な場合のみ修正
- `spec_anchor/watcher.py`: `run_spec_core_for_watcher` 直接呼び出し経路で同じ core 更新結果になることの確認。必要な場合のみ修正
- `.claude/commands/spec-inject.md` / `.claude/commands/spec-realign.md` / `.codex/skills/spec-anchor/SKILL.md`: template 文言の drift 防止対象
- `spec_anchor/templates/.claude/commands/spec-inject.md` / `spec_anchor/templates/.claude/commands/spec-realign.md` / `spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md`: setup 時に配布される template
- `tests/test_spec_core.py` / `tests/test_conflict_review.py` / `tests/test_spec_inject.py` / watcher 関連 test: regression test
- `doc/EXTERNAL_DESIGN.ja.md`: Source Specs / Purpose / Core Concept 修正後の自動 dismiss 条件、`needs_source_update` との関係、`resolution.decision_origin` / audit trail field、CoreResult 観測 field の契約を追記

#### 完了条件

- Source Specs 修正後の `/spec-core` で、解消済み pending Conflict Review Item が `pending_conflict_count` から外れる。
- Related Sections pair が消えた場合の扱いが設計・実装・test で一致している。
- section_id 変更 / section 削除で dangling になった既存 pending item の扱いが設計・実装・test で一致している。
- 人間 decision の `dismiss` と source 修正後の自動 dismiss が `resolution.decision_origin` で区別され、audit trail field が保存される。
- CoreResult で自動 dismiss 件数と id が観測できる。
- `/spec-inject` / `/spec-realign` の pending conflict 停止出力が、更新後も残る conflict だけを提示する。
- Claude command template / Codex skill template の parity と必須文言を test で検査できる。
- `pytest --skip-external` が pass する。
- 実 Qdrant / BGE-M3 / real provider / `spec-anchor-watch` 実機検証を実行した場合は結果を記録する。未実行なら、未完了範囲として完了報告に残す。
- 本項を「完了確認済み」へ移動する場合は、完了した内容・実行した test・未実行の real provider / watch 検証を保持する。block の削除は禁止。

#### 依存 / scope 外

- **依存**: `/spec-core` conflict evaluation の現在契約、`/spec-inject` / `/spec-realign` freshness gate の pending conflict 停止契約。
- **scope 外**:
  - Agent / LLM が人間の代わりに conflict を裁定する機能。Human が Source Specs / Purpose / Core Concept を修正するか、明示的に `--decision-json` / `--decision-file` 相当の判断を渡す責務は維持する。
  - Purpose / Core Concept の自動更新。両ファイルは引き続き人間管理対象。
  - constraints の意味論的真偽を CLI が完全検証する機能。今回の scope は template / skill の必須文言と、機械的に検査できる根拠ルールの regression 防止まで。
