# TODO 一覧

このファイルは、次のセッション以降で実装する **開放中 task** と、完了した task の本文 (履歴) を同じファイル内に並べる。

- 「## 開放中」配下の優先順位リストには **開放中の task のみ** を載せる
- 完了した task は章タイトルに `[完了 YYYY-MM-DD, commit(s) ...]` マークを付けて本文をそのまま残す (章本体の構造は変えない)
- 完了 task は優先順位リストから外し、開放中リスト直後の「完了済み task」一覧で見出しと完了日のみ参照する

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
2. **T-flaky-spec-core-responsibility-boundary**: `tests/test_responsibility_boundary.py::test_spec_core_does_not_modify_purpose_or_concept_files` の偶発的失敗 (真因特定・test 修正済み、長時間検証待ち)

依存関係:

- T-conflict-source-update-flow は SpecClaim 移行と独立。Phase 5 (commit da692ba) で Conflict Review 入力境界が SpecClaim pair に変更されたが、T-conflict の auto-dismiss ロジックは `conflict_review_items.json` 側で完結するため SpecClaim pair 入力でも直交する。Phase 5 で Related Sections 由来 pair 依存の test fixture (T-conflict B 区分) は SpecClaim retrieval 由来 fixture に更新する必要がある。
- T-flaky-spec-core-responsibility-boundary は独立。2026-05-29 に真因特定と test 修正は実施済み。残作業は full pytest 100 回相当の長時間安定性確認。

完了済み task (履歴は本ファイル各章と git log を参照):

- T-spec-claim-phase-1 (Phase 1: SpecClaim 抽出 stage) — 完了 2026-05-28
- T-spec-claim-phase-2 (Phase 2: Claim Retrieval stage) — 完了 2026-05-29
- T-spec-claim-phase-3 (Phase 3: LLM triage stage) — 完了 2026-05-29
- T-spec-claim-phase-4 (Phase 4: 実機 recall 検証 = Phase 5 着手 gate) — 完了 2026-05-29
- T-spec-claim-phase-5 (Phase 5: `possible_conflict` 完全削除 + Conflict Review 入力境界変更) — 完了 2026-05-29
- T-spec-inject-pending-conflict-fixture-update (PendingConflictSpecCoreProvider を SpecClaim 経路に追従) — 完了 2026-05-29

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
| C-11 | `needs_source_update` の人間 decision が自動 dismiss で上書きされる | 採用 / audit trail 保持が必要 | `needs_source_update` 済み item も source 修正後に自動 dismiss できる。ただし上書き前の `resolution` は `resolution.previous_resolution` に保持し、人間が「source 修正が必要」と判断したログを消さない |
| C-12 | 人間 decision の `decision_origin="human"` を設定する実装箇所が曖昧 | 採用 / 実装方針へ追加 | `spec_anchor/conflict_review.py::apply_conflict_decision()` で、decision payload に `decision_origin` が無い場合は `resolution.decision_origin="human"` を補完する |
| C-13 | `auto_dismiss_reason` の値集合が固定か拡張可能か曖昧 | 採用 / schema 方針を明記 | 現在の値は `source_update_recheck_non_pending` と `source_update_recheck_pair_absent` の 2 種に固定するが、外部契約上は将来拡張可能な enum として扱う |

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
- `apply_conflict_decision()` は、人間が `--decision-json` / `--decision-file` で渡した decision payload に `decision_origin` が無い場合、保存する `resolution.decision_origin` を `human` で補完する。
- 自動 dismiss の `resolution` には、`applied_at`、`previous_status="pending"`、`decision_origin="auto_source_update"`、`auto_dismiss_reason`、`referenced_source_refs`、`valid_scope="global"` を入れる。
- 自動 dismiss が `needs_source_update` など既存 pending decision の `resolution` を置き換える場合、置き換え前の `resolution` を `resolution.previous_resolution` に保存する。これにより、人間が source 修正を必要と判断した audit trail を保持する。`resolution.history[]` は今回の scope では導入しない。
- `auto_dismiss_reason` は将来拡張可能な enum とする。今回の実装で使う値は `source_update_recheck_non_pending` と `source_update_recheck_pair_absent` の 2 種に限定する。
- `/spec-core` の CoreResult には `auto_dismissed_conflict_count` と `auto_dismissed_conflict_ids[]` を追加し、Source Specs / Purpose / Core Concept 修正後に何件の pending Conflict Review Item が blocker から外れたかを利用者が確認できるようにする。
- constraints JSON の意味論的真偽を CLI が完全検証する機能は今回追加しない。今回の guard 強化は、template parity、pending conflict 必須 label、`evidence_origin` enum、support-only evidence 禁止を static test で検出する範囲に固定する。

外部設計書追記ドラフト:

```text
§3.3 追記:
Source Specs / Purpose / Core Concept の変更後に `/spec-core` または `spec-anchor-watch` が保持物を更新した場合、SPEC-anchor は既存 pending Conflict Review Item を現在の source hash と conflict evaluation 結果で再評価する。根拠 source の hash が変化した、または根拠 source ref が削除された既存 pending item について、同じ conflict pair が non-pending 判定になるか、現在の conflict candidate から消えた場合、`/spec-core` はその item を `status="dismissed"`、`resolution.decision_origin="auto_source_update"` として blocker から外す。source hash が変わっていない pending item は、LLM judge の再判定だけでは自動解除しない。

§7 decision 表直後に追記:
`needs_source_update` は、人間が Source Specs / Purpose / Core Concept の修正を必要と判断したことを記録する pending decision である。修正後の `/spec-core` 再評価により conflict が解消された場合、SPEC-anchor は該当 pending item を `dismissed` に遷移できる。この自動遷移は人間 decision の `dismiss` とは区別し、`resolution.decision_origin="auto_source_update"`、`resolution.previous_status="pending"`、`resolution.applied_at=<timestamp>`、`resolution.auto_dismiss_reason=<reason>` を持つ。自動遷移前に pending decision の `resolution` が存在する場合、SPEC-anchor は置き換え前の値を `resolution.previous_resolution` に保持する。`auto_dismiss_reason` は将来拡張可能な enum であり、現在定義する値は `source_update_recheck_non_pending` と `source_update_recheck_pair_absent` である。
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
5. 自動 dismiss では `resolution.decision="dismiss"`、`resolution.decision_origin="auto_source_update"`、`resolution.previous_status="pending"`、`resolution.applied_at=<timestamp>`、`resolution.auto_dismiss_reason`、`resolution.reason`、`resolution.referenced_source_refs` を記録する。既存 pending decision の `resolution` がある場合は `resolution.previous_resolution` に退避する。`base_source_hashes` は現在の source hash に更新する。
6. source hash が変わっていない既存 pending item は、non-pending signal があっても pending のまま残す。
7. `spec_anchor/conflict_review.py::apply_conflict_decision()` で、人間 decision payload に `decision_origin` が無い場合は `resolution.decision_origin="human"` を補完する。
8. `auto_dismiss_reason` の validator / document は、現在値を `source_update_recheck_non_pending` / `source_update_recheck_pair_absent` の 2 種とし、将来の理由追加に備えて unknown value を破壊的に落とさない方針にする。
9. `spec_anchor/core.py` の CoreResult に `auto_dismissed_conflict_count` と `auto_dismissed_conflict_ids[]` を追加する。
10. `doc/EXTERNAL_DESIGN.ja.md` に、上記「外部設計書追記ドラフト」の内容を反映する。
11. `spec-anchor-watch` は `spec_anchor/watcher.py` で `run_spec_core_for_watcher` を直接 import して呼ぶため、この直接呼び出し経路にも同じ pending 解除処理と CoreResult field が適用されることを test する。watch の長時間実行が必要な場合は unit / integration を分ける。
12. template / skill drift 防止として、Claude command / Codex skill の installed copy と packaged template の parity、pending conflict の必須 label、constraints 根拠ルールの必須文言を static assertion で確認する test を追加する。

#### 検証条件

A. **既存 pending item の解除**

- `tests/test_spec_core.py` に、1 回目 `FakeSpecCoreProvider("unresolved")` で pending item を作り、Source Specs を修正し、2 回目 `FakeSpecCoreProvider("resolved")` または non-pending outcome provider で `spec-anchor core` を実行したとき、該当 `conflict_id` が `pending_conflict_count` に含まれないことを確認する test を追加する。
- 同じ source hash のまま provider だけが non-pending を返す場合は、既存 pending item が残ることを確認する。
- 自動 dismiss された item の `resolution.decision_origin`、`resolution.previous_status`、`resolution.applied_at`、`resolution.auto_dismiss_reason`、`resolution.referenced_source_refs`、`base_source_hashes` が期待どおりであることを確認する。
- `needs_source_update` など既存 pending decision の `resolution` がある item を自動 dismiss した場合、置き換え前の `resolution` が `resolution.previous_resolution` に保持されることを確認する。
- `apply_conflict_decision()` で人間 decision payload に `decision_origin` が無い場合、保存後の `resolution.decision_origin` が `human` になることを確認する。
- 自動 dismiss の `resolution.auto_dismiss_reason` が現在定義済みの 2 値を返すこと、将来の reason 値を読むだけの経路が破壊的に失敗しないことを確認する。
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

### [完了 2026-05-28, commits eb8c1cf / cbe13c0 / 3ca9536] T-spec-claim-phase-1: SpecClaim 抽出 stage の新規実装 (SCD-032 Phase 1)

#### 背景

`doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` (commit 4a68f54) で、Related Sections の `possible_conflict` を完全廃止し、section 内の仕様主張単位で矛盾候補を抽出する SpecClaim 経路に置き換える方針が確定した。本 Phase は SpecClaim 経路の最初のステップ (SpecClaim 抽出 stage の新規実装) を扱う。

`doc/EXTERNAL_DESIGN.ja.md` §2.11 / §4.1 / §7.4 / §10.2 (commit aa83f63) と `doc/DESIGN.ja.md` §0 implementation tracker / §3.4 / §5.10 (commit 8272ab9) には、SpecClaim を section_metadata と別 stage / 別 cache / 別 schema で扱う外部契約と内部設計指針がすでに反映済み。`.spec-anchor/context/spec_claims.jsonl` を正本にする / `[retrieval].claim_collection` を別 Qdrant collection にする / `[llm.stage_routing].spec_claims` を許可 stage に追加する、などの契約はこの commit 群で固定されている。

#### 真因 / 対応方針

真因 (確定):

- 現在 `/spec-core` は section 単位の summary / search_keys / identifiers / related_sections しか抽出していない。section 内の「仕様主張」を独立した record として持たないため、Conflict Review に送るべき候補を section pair ではなく claim pair で扱う仕組みがない。
- Related Sections の `possible_conflict` flag は Phase 5 で削除予定だが、それまでの間に Conflict Review に届く別経路 (SpecClaim 経路) を立ち上げる必要がある。

対応方針 (確定):

- 新規 module `spec_anchor/spec_claims.py` を作る。SpecClaim 抽出 stage 用の prompt / schema validation / cache key / state file (`spec_claims_state.json`) / version 定数 (`SPEC_CLAIM_SCHEMA_VERSION` / `SPEC_CLAIM_PROMPT_VERSION` / `SPEC_CLAIM_IDENTITY_VERSION` / `SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION`) をすべてこの module に集約する。詳細は `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` §5 / §9 を参照。
- `spec_anchor/core.py` のフローに spec_claims stage を組み込む。section_metadata stage の後 (または並列) に実行する。Related Sections stage との順序依存は持たない (SpecClaim 抽出は Related Sections を必須前提にしない)。
- `spec_anchor/llm_provider.py` に SpecClaim 抽出 prompt / response schema を追加する。`[llm.stage_routing].spec_claims` の provider 解決を core.py の stage routing に組み込む。
- 保持物 `.spec-anchor/context/spec_claims.jsonl` を JSONL 形式で永続化する。1 SpecClaim record = 1 行。schema は `claim_uid` / `display_id` / `claim_hash` / `claim_text` / `target` / `target_aliases` / `scope` / `condition` / `value` / `claim_kind` / `evidence_span` / `evidence_start` / `evidence_end` / `evidence_hash` / `source_hash` / `semantic_hash` / `retrieval` / `source_section_id` / `generated_at` を持つ (詳細は SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md §5)。
- state file `.spec-anchor/state/spec_claims_state.json` を新設し、section 集合指紋 / 各 section の `source_hash` / `semantic_hash` / 抽出設定指紋 / claim uid / hash / retrieval hash 集合を保存する。incremental 経路では state file の指紋一致時に LLM を呼ばず skip する。
- diagnostics field `success_with_claims` / `success_no_claims` / `failed_spec_claim_sections` / `claim_limit_reached_sections` を CoreResult / `core_progress.json` に追加する。SpecClaim 抽出に失敗した section が 1 件以上ある場合、stage status は `partial_success` または `failed` とする (`claims=[]` で成功扱いしない)。
- LLM 出力には `claim_uid`、`claim_hash`、`evidence_span`、`evidence_start`、`evidence_end`、`evidence_hash`、`target_aliases`、`source_hash` を必須化し、schema validation で reject する。`evidence_start` / `evidence_end` が Source Specs の section text と一致することを検証し、不一致時は補正または validation failure とする。
- Phase 1 では Claim Retrieval (Qdrant claim_collection への upsert を含む) と LLM triage は実装しない。SpecClaim 抽出と保持物生成だけを完成させる。後続 Phase で claim retrieval / triage を実装する。

#### 目的

`/spec-core` 実行時に section 内の仕様主張 (SpecClaim) を抽出し、`.spec-anchor/context/spec_claims.jsonl` に保存する経路を確立する。Phase 2 以降の Claim Retrieval / LLM triage / Conflict Review への入力源として使える状態を作る。

合格基準:

- 実 Codex / Claude CLI を使う `/spec-core` 実行で `.spec-anchor/context/spec_claims.jsonl` が生成され、含まれる record が schema validation を通る。
- 変更なし incremental で `spec_claims: skipped_unchanged` が出て、SpecClaim 抽出の LLM call が 0 になる。
- 変更あり incremental で、変更・追加 section だけ SpecClaim が再抽出され、削除 section の SpecClaim が `.spec-anchor/context/spec_claims.jsonl` から除外される。
- `evidence_start` / `evidence_end` が Source Specs の section text と一致することが検証され、不一致時は補正または validation failure として diagnostics に出る。
- SpecClaim 抽出に失敗した section が 1 件以上あれば、stage status は `partial_success` または `failed` となり、`failed_spec_claim_sections` が CoreResult / `core_progress.json` に記録される。
- `claims=[]` を失敗 section の代替値として保存していない。
- `[llm.stage_routing].spec_claims` で provider を切り替えられる。

#### 実装方針

1. `spec_anchor/spec_claims.py` を新規作成し、次を実装する:
   - version 定数 (`SPEC_CLAIM_SCHEMA_VERSION` / `SPEC_CLAIM_PROMPT_VERSION` / `SPEC_CLAIM_IDENTITY_VERSION` / `SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION`)
   - SpecClaim 抽出 prompt template
   - LLM response schema validation
   - `claim_uid` 生成 (LLM 出力順、schema version、offset に依存しない安定 ID)
   - `evidence_span` / `evidence_start` / `evidence_end` の Source Specs 照合
   - schema validation failure / LLM call failure の diagnostics
   - cache key (`source_section_id`, `source_hash`, `semantic_hash`, `spec_claim_prompt_version`, `model`, `effort`, `schema_version`)
   - state file (`spec_claims_state.json`) の読み書き
   - `.spec-anchor/context/spec_claims.jsonl` の atomic write (削除 section の record 除外を含む)
2. `spec_anchor/core.py` に `_generate_spec_claims_if_enabled` 相当の wire を追加し、stage routing で SpecClaim 抽出を起動する。
3. `spec_anchor/llm_provider.py` に SpecClaim 抽出 stage の LLM provider 呼び出し経路を追加する。
4. `spec_anchor/cli.py` / config loader に `[llm.stage_routing].spec_claims` の解決を追加する。
5. fake 用テスト fixture (`tests/test_spec_claims.py` 新規) で schema validation / cache reuse / failed section diagnostics を確認する。
6. 実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う `/spec-core` 実行で `.spec-anchor/context/spec_claims.jsonl` が生成されることを確認する。

#### 検証条件

A. **fake 用テスト** (`tests/test_spec_claims.py` 新規):

- schema validation、cache key、失敗 diagnostics、`evidence_start` / `evidence_end` の検証、offset 補正、`ambiguous_evidence_span` / `invalid_evidence_span` の判定、`success_with_claims` / `success_no_claims` / `failed_spec_claim_sections` の区別、`max_claims_per_section` 到達時の `claim_limit_reached_sections`、`claim_uid` の LLM 出力順 / schema version / offset 非依存性。

B. **incremental 経路** (`tests/test_spec_core.py` 拡張):

- 変更なし incremental で `spec_claims: skipped_unchanged` となり SpecClaim 抽出の LLM call が 0 になる。
- 変更あり incremental で変更・追加 section だけ SpecClaim が再抽出され、削除 section の SpecClaim が `.spec-anchor/context/spec_claims.jsonl` から除外される。

C. **実機経路** (real provider 経路、未実行時は残 TODO):

- 実 Codex / Claude CLI を使う `/spec-core` 実行で `.spec-anchor/context/spec_claims.jsonl` が生成され、含まれる record が schema validation を通る。
- `[llm.stage_routing].spec_claims` で provider を切り替えると、stage が指定 provider を使う。

D. **既存 pytest**: `pytest --skip-external` が pass する。

#### 触れる主なファイル

- `spec_anchor/spec_claims.py` (新規): SpecClaim 抽出 stage 本体
- `spec_anchor/core.py`: stage 組み込み、CoreResult への `spec_claims_status` 追加
- `spec_anchor/llm_provider.py`: SpecClaim 抽出 prompt / response schema
- `spec_anchor/cli.py` / config loader: `[llm.stage_routing].spec_claims` 解決
- `tests/test_spec_claims.py` (新規): SpecClaim 抽出の fake 用テスト
- `tests/test_spec_core.py`: incremental 経路 test 拡張

#### 完了条件

- A / B の fake 用テストが pass する。
- C の実機経路を実行できた範囲で確認結果を記録する。実 provider / Qdrant / BGE-M3 が未実行の場合は未完了 TODO として残す。
- D の `pytest --skip-external` が pass する。
- `doc/DESIGN.ja.md` §0 implementation tracker の T-spec-claim-phase-1 関連 `[ ]` task を `[x]` に変えて evidence link (file:line + test) を併記する。
- 本 task entry を「完了確認済み」へ移動する場合は、完了内容と未実行検証を保持する。

#### 依存 / scope 外

- **依存**: なし (新規追加)。
- **scope 外**:
  - Claim Retrieval (Qdrant claim_collection への upsert と retrieval 処理) は T-spec-claim-phase-2 で実装する。本 Phase では retrieval 派生表現を `spec_claims.jsonl` 内の `retrieval` field に保持するまでで止める。
  - LLM triage は T-spec-claim-phase-3 で実装する。
  - `possible_conflict` 経路の削除は T-spec-claim-phase-5 で実装する。本 Phase では既存 `possible_conflict` 経路を変更しない。

### [完了 2026-05-29, commits dd3c674 / 94c25c7 / 1e0a7ec] T-spec-claim-phase-2: Claim Retrieval stage の新規実装 (SCD-032 Phase 2)

#### 背景

T-spec-claim-phase-1 で SpecClaim 抽出と `.spec-anchor/context/spec_claims.jsonl` 保持物が確立されたら、本 Phase は SpecClaim pair を絞り込む Claim Retrieval stage を実装する。

`doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` §7.3 と `doc/EXTERNAL_DESIGN.ja.md` §10.2 に従い、Claim Retrieval は LLM を呼ばない。Qdrant の専用 collection (`[retrieval].claim_collection`、default `spec_anchor_claim`) に SpecClaim を upsert し、dense retrieval / sparse retrieval / conflict probe retrieval の 3 channel を RRF (Reciprocal Rank Fusion) で融合して候補 SpecClaim pair を作る。

#### 真因 / 対応方針

真因 (確定):

- T-spec-claim-phase-1 完了後でも、SpecClaim pair の絞り込み機構が無いと、Phase 3 の LLM triage は全 SpecClaim pair の総当たりを送らざるを得ない。これは大規模 spec で O(N^2) になり、運用不能。
- claim-level retrieval は section-level retrieval (`section_collection`) と別 collection にする必要がある (粒度、metadata、削除単位、検索目的が異なるため)。

対応方針 (確定):

- 新規 module `spec_anchor/claim_retrieval.py` を作る。Qdrant claim_collection への upsert / dense+sparse retrieval / conflict probe retrieval / RRF / 上限による truncation / state file (`conflict_candidate_pairs_state.json` の retrieval 部分) を実装する。
- claim-level Qdrant collection の point id は `claim_uid` から生成した UUID5 とする (section-level collection と同じ namespace を使うか別 namespace を使うかは実装時に決定し、決定理由を doc に追記)。
- `[retrieval].claim_collection` の payload には `target` / `target_aliases` / `claim_text` / `claim_hash` / `source_section_id` / `evidence_span` / `retrieval_hash` を含む。
- retrieval pipeline (`spec_anchor/claim_retrieval.py` 内):
  - 起点 claim ごとに dense_hits / sparse_key_hits / conflict_probe_hits を取る
  - pair を作る (`route = "dense_claim_retrieval"` / `"sparse_key_claim_retrieval"` / `"conflict_probe_claim_retrieval"`)
  - sorted `claim_uid` tuple で dedup する (= 順序非依存)
  - 同一 pair が複数 channel から来た場合は `retrieval_sources[]` に集約する
  - RRF で順位融合する (`rrf_score = Σ source_weight[source] / (rrf_k + rank_source(pair))`)
  - `per_claim_top_k` / `per_section_top_k` / `per_target_top_k` / `global_candidate_top_k` の上限で truncate する
  - truncate 発生時は `truncated_candidate_sources` / `truncated_pair_count` を diagnostics に出す
- 初期 default では同一 section 内 SpecClaim pair も候補対象にする (`allow_same_section_claim_pair = true`)。
- 出力は `.spec-anchor/context/conflict_candidate_pairs.jsonl` の **retrieval-only candidate** として保存する (`triage = null`、`route = "claim_retrieval"`)。LLM triage は次 Phase で `triage` を埋める。
- 実装時は `[conflict_candidate_detection]` の default config (`per_claim_top_k = 10` / `per_section_top_k = 20` / `per_target_top_k = 20` / `global_candidate_top_k = 100` / `triage_max_pairs = 30` / `min_dense_score = 0.55` / `min_sparse_score = 0.0` / `rank_fusion = "rrf"` / `allow_same_section_claim_pair = true` / `allow_same_source_file_claim_pair = true`) を `spec_anchor/config.py` の loader が受理することを確認する。

#### 目的

`/spec-core` 実行時に SpecClaim retrieval で候補 SpecClaim pair を作り、`.spec-anchor/context/conflict_candidate_pairs.jsonl` に retrieval-only candidate として保存する経路を確立する。

合格基準:

- 実 Qdrant / FlagEmbedding BGE-M3 を使う構成で `.spec-anchor/context/conflict_candidate_pairs.jsonl` が生成され、各候補が `claim_retrieval_llm_triage` route の前段 retrieval として `retrieval_sources[]` を持つ。
- 上限により候補が切られた場合、`truncated_candidate_sources` と `truncated_pair_count` が diagnostics に出る。
- 同一 section 内 SpecClaim pair が初期 default で候補対象になる。
- 変更あり incremental で、変更 claim を起点に全 SpecClaim 集合から候補 pair を取り直す (変更 claim 同士の探索だけに絞らない)。
- 未変更 claim 同士の candidate pair は、claim retrieval 設定指紋一致時に再利用される。

#### 実装方針

1. `spec_anchor/claim_retrieval.py` を新規作成し、次を実装する:
   - Qdrant claim_collection の作成・upsert・delete (incremental 経路の変更・追加・削除 claim 対応)
   - dense / sparse / conflict_probe retrieval の 3 channel
   - sorted `claim_uid` tuple での dedup
   - `retrieval_sources[]` の集約
   - RRF 順位融合
   - 上限 truncation と diagnostics
   - retrieval-only candidate の `.spec-anchor/context/conflict_candidate_pairs.jsonl` 書き込み (`triage = null`)
   - state file (`conflict_candidate_pairs_state.json`) の retrieval 部分の読み書き
2. `spec_anchor/core.py` に `_generate_claim_retrieval_if_enabled` 相当を追加し、Phase 1 の SpecClaim 抽出後に起動する。
3. `spec_anchor/config.py` / config loader に `[conflict_candidate_detection]` block と `[retrieval].claim_collection` の解決を追加する。
4. fake 用テスト (`tests/test_claim_retrieval.py` 新規) で dedup / 上限 truncation / 削除 claim を含む pair の除外 / 同一 section pair 採用を確認する。
5. 実 Qdrant + FlagEmbedding BGE-M3 を使う統合 test で claim_collection の upsert / retrieval を確認する。

#### 検証条件

A. **fake 用テスト** (`tests/test_claim_retrieval.py` 新規):

- dedup (sorted `claim_uid` tuple)、上限 truncation (`truncated_candidate_sources` / `truncated_pair_count`)、削除 claim を含む pair の除外、`retrieval_sources[]` 集約、同一 section pair 採用、変更 claim 起点の全 SpecClaim 集合探索、未変更 pair の reuse。

B. **incremental 経路** (`tests/test_spec_core.py` 拡張):

- 変更なし incremental で `claim_retrieval: skipped_unchanged` となり Qdrant upsert / retrieval call が 0 になる。
- 変更あり incremental で変更・追加 claim だけ upsert され、削除 claim が claim_collection から除外される。

C. **実機経路** (real Qdrant + FlagEmbedding BGE-M3、未実行時は残 TODO):

- 実 Qdrant + FlagEmbedding BGE-M3 を使う構成で claim_collection の upsert と retrieval が動く。
- `.spec-anchor/context/conflict_candidate_pairs.jsonl` に retrieval-only candidate (`triage = null`、`route = "claim_retrieval"`) が保存される。

D. **既存 pytest**: `pytest --skip-external` が pass する。

#### 触れる主なファイル

- `spec_anchor/claim_retrieval.py` (新規): Claim Retrieval stage 本体
- `spec_anchor/core.py`: stage 組み込み、CoreResult / state file の retrieval 部分の wire
- `spec_anchor/config.py` / config loader: `[conflict_candidate_detection]` / `[retrieval].claim_collection` の解決
- `tests/test_claim_retrieval.py` (新規): Claim Retrieval の fake 用テスト
- `tests/test_spec_core.py`: incremental 経路 test 拡張

#### 完了条件

- A / B の fake 用テストが pass する。
- C の実機経路を実行できた範囲で確認結果を記録する。実 Qdrant / BGE-M3 が未実行の場合は未完了 TODO として残す。
- D の `pytest --skip-external` が pass する。
- `doc/DESIGN.ja.md` §0 implementation tracker の Claim Retrieval 関連 evidence を記録する。

#### 依存 / scope 外

- **依存**: T-spec-claim-phase-1 (SpecClaim 抽出 stage と `.spec-anchor/context/spec_claims.jsonl` 保持物)。
- **scope 外**:
  - LLM triage は T-spec-claim-phase-3 で実装する。本 Phase では `triage = null` の retrieval-only candidate までで止める。
  - `possible_conflict` 経路の削除は T-spec-claim-phase-5 で実装する。

### [完了 2026-05-29, commits 5204323 / fa2def0 / 9529e07] T-spec-claim-phase-3: LLM triage stage の新規実装 (SCD-032 Phase 3)

#### 背景

T-spec-claim-phase-2 で Claim Retrieval が候補 SpecClaim pair を作るようになったら、本 Phase は少数 pair に対して LLM triage を実行し、Conflict Review に送るべきかを判定する stage を実装する。

`doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` §2.3 / §7.4 に従い、LLM triage は `send_to_review` の bool と `reason` / `confidence` だけを返す。conflict 確定や人間判断必須性、Source Specs 優先関係の決定はしない。

#### 真因 / 対応方針

真因 (確定):

- T-spec-claim-phase-2 完了後でも、retrieval だけでは Conflict Review に送る価値があるかの判定がない。Conflict Review pipeline は Purpose / Core Concept grounding を伴う厳密な judge call なので、retrieval が拾った候補すべてを送ると Conflict Review の cost が肥大化する。
- LLM triage は軽量な judgement (送るべき / 送らない) に絞り、Conflict Review に責務を寄せる構造にする。

対応方針 (確定):

- 新規 module `spec_anchor/conflict_candidates.py` を作る。LLM triage prompt / response schema / cache key / version 定数 (`CONFLICT_CANDIDATE_SCHEMA_VERSION` / `CONFLICT_TRIAGE_PROMPT_VERSION`) / state file (`conflict_candidate_pairs_state.json` の triage 部分) をこの module に集約する。
- LLM triage 入力は section 全文ではなく、SpecClaim pair と `evidence_span` 中心。Purpose / Core Concept は本 stage の grounding に含めない (Conflict Review が grounding を持つ責務)。
- LLM triage 出力は `send_to_review` (bool)、`reason` (str)、`confidence` (`high` / `medium` / `low`) のみ。`conflict_confirmed` / `human_review_required` / `resolution` を出力してはいけない (schema validation で reject する)。
- T-spec-claim-phase-2 が書いた retrieval-only candidate を読み、`triage_max_pairs` の上限内で LLM triage を実行する。`triage.send_to_review = true` になった pair の `triage` field を埋め、`.spec-anchor/context/conflict_candidate_pairs.jsonl` を atomic に更新する。
- `triage = null` のままの retrieval-only record は `.spec-anchor/context/conflict_candidate_pairs.jsonl` から除外する (Conflict Review に送る対象は `triage.send_to_review = true` のみ)。
- cache key は両 claim の `claim_uid` / `claim_hash` / `retrieval_hash` / 両 source の `source_hash` / `triage_prompt_version` / `triage_schema_version` / `triage_model` / `triage_effort` を含める。これらが一致する pair の triage cache は再利用する。
- diagnostics field `send_to_review_count` / `send_to_review_false_count` / `triage_truncated_pairs` を CoreResult / `core_progress.json` に追加する。

#### 目的

`/spec-core` 実行時に Claim Retrieval が拾った少数の SpecClaim pair に対して LLM triage を実行し、`triage.send_to_review = true` の pair だけを `.spec-anchor/context/conflict_candidate_pairs.jsonl` に保存する経路を確立する。Conflict Review pipeline の入力源として使える状態を作る。

合格基準:

- LLM triage の出力 schema が `send_to_review` / `reason` / `confidence` のみで、それ以外の field を含む応答は reject される。
- 実 Codex / Claude CLI を使う `/spec-core` で少数 claim pair だけが LLM triage に送られる (全 retrieval candidate ではなく `triage_max_pairs` 上限内)。
- 両 claim の `claim_hash` / `retrieval_hash` と triage 設定が一致する pair の triage cache が再利用される。
- `triage = null` の record は `.spec-anchor/context/conflict_candidate_pairs.jsonl` に保存されない (diagnostics 用途も含めて Conflict Review に送らない)。
- `[llm.stage_routing].conflict_candidate_triage` で provider を切り替えられる。

#### 実装方針

1. `spec_anchor/conflict_candidates.py` を新規作成し、次を実装する:
   - version 定数 (`CONFLICT_CANDIDATE_SCHEMA_VERSION` / `CONFLICT_TRIAGE_PROMPT_VERSION`)
   - LLM triage prompt template
   - response schema validation (`send_to_review` / `reason` / `confidence` のみ受理、それ以外は reject)
   - cache key の生成と triage cache 読み書き
   - `triage_max_pairs` 上限内の LLM triage 実行
   - `triage.send_to_review = true` の pair だけ `.spec-anchor/context/conflict_candidate_pairs.jsonl` に保存
   - `triage = null` の record の除外
   - state file (`conflict_candidate_pairs_state.json`) の triage 部分の読み書き
2. `spec_anchor/core.py` に `_generate_conflict_candidate_triage_if_enabled` 相当を追加し、Phase 2 の Claim Retrieval 後に起動する。
3. `spec_anchor/llm_provider.py` に LLM triage stage の provider 呼び出し経路を追加する。
4. `spec_anchor/cli.py` / config loader に `[llm.stage_routing].conflict_candidate_triage` の解決を追加する。
5. fake 用テスト (`tests/test_conflict_candidates.py` 新規) で schema validation / cache reuse / `triage = null` の record 除外 / `[llm.stage_routing].conflict_candidate_triage` の provider 切り替えを確認する。
6. 実 Codex / Claude CLI を使う統合 test で少数 claim pair だけが LLM triage に送られることを確認する。

#### 検証条件

A. **fake 用テスト** (`tests/test_conflict_candidates.py` 新規):

- `send_to_review` / `reason` / `confidence` 以外の field を含む応答が reject される。
- `triage = null` の record が `.spec-anchor/context/conflict_candidate_pairs.jsonl` に保存されない。
- `triage = null` の record が Conflict Review に送られない (diagnostics 用途も含む)。
- 両 claim の `claim_hash` / `retrieval_hash` と triage 設定が一致する pair で triage cache が再利用される。
- `triage_max_pairs` 上限が機能する。

B. **incremental 経路** (`tests/test_spec_core.py` 拡張):

- 変更なし incremental で `conflict_candidate_triage: skipped_unchanged` となり LLM triage call が 0 になる。
- 変更あり incremental で変更 claim を含む pair だけ triage cache miss となり、LLM call が走る。

C. **実機経路** (real provider 経路、未実行時は残 TODO):

- 実 Codex / Claude CLI を使い、少数 claim pair だけが LLM triage に送られる (全 retrieval candidate ではなく上限内)。
- `triage.send_to_review = true` の pair だけが Conflict Review pipeline の入力候補として保存される。
- `[llm.stage_routing].conflict_candidate_triage` で provider を切り替えると、stage が指定 provider を使う。

D. **既存 pytest**: `pytest --skip-external` が pass する。

#### 触れる主なファイル

- `spec_anchor/conflict_candidates.py` (新規): LLM triage stage 本体
- `spec_anchor/core.py`: stage 組み込み、CoreResult / state file の triage 部分の wire
- `spec_anchor/llm_provider.py`: LLM triage prompt / response schema
- `spec_anchor/cli.py` / config loader: `[llm.stage_routing].conflict_candidate_triage` 解決
- `tests/test_conflict_candidates.py` (新規): LLM triage の fake 用テスト
- `tests/test_spec_core.py`: incremental 経路 test 拡張

#### 完了条件

- A / B の fake 用テストが pass する。
- C の実機経路を実行できた範囲で確認結果を記録する。実 provider が未実行の場合は未完了 TODO として残す。
- D の `pytest --skip-external` が pass する。
- `doc/DESIGN.ja.md` §0 implementation tracker の LLM triage 関連 evidence を記録する。

#### 依存 / scope 外

- **依存**: T-spec-claim-phase-1、T-spec-claim-phase-2。
- **scope 外**:
  - Conflict Review pipeline 自体 (Purpose / Core Concept grounding 付き judge) の責務変更は T-spec-claim-phase-5 で行う。本 Phase では既存 Conflict Review pipeline をそのまま使う (入力経路に SpecClaim pair が増えるだけ)。
  - `possible_conflict` 経路の削除は T-spec-claim-phase-5 で実装する。

### [完了 2026-05-29, commit 285a6db] T-spec-claim-phase-4: 既知 conflict fixture が SpecClaim 経路で Conflict Review に届くことの検証 + 任意 recall 比較 (SCD-032 Phase 4)

#### 背景

T-spec-claim-phase-1 〜 phase-3 で SpecClaim 経路 (SpecClaim 抽出 + Claim Retrieval + LLM triage) の実装が完了したら、本 Phase は既知 conflict fixture が SpecClaim 経路で Conflict Review に届くことを実機経路で確認する。これは Phase 5 (`possible_conflict` 完全削除) に進むための gate。

`doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` §12 Phase 4 / §14.2 Phase 4 完了条件 に従い、recall 比較を任意のサブステップとして実施できる。

#### 真因 / 対応方針

真因 (確定):

- Phase 1-3 の fake 用テストだけでは「既存 `possible_conflict` 経路で拾えていた conflict が SpecClaim 経路でも拾える」ことを保証できない。fake 用テストは fixed response でのみ動く。
- Phase 5 で `possible_conflict` 経路を削除すると、recall regression が発生しても回復経路がない (削除後の revision では `possible_conflict` 経路は無い)。したがって Phase 5 着手前に recall を実機で確認する必要がある。

対応方針 (確定):

- 既知 conflict fixture (現在の `tests/test_conflict_review.py::test_phase_e_possible_conflict_flag_routes_to_conflict_review` で使われている fixture と等価、または独自定義) を SpecClaim 経路で再実行し、`triage.send_to_review = true` として Conflict Review pipeline に届くことを確認する。
- 実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う `/spec-core` 実行で確認する。fake 用テストの passing は完了証跡として認めない。
- 任意のサブステップとして、Phase 5 着手前の revision (`possible_conflict` 経路が動いている revision) で `/spec-core` 実行し、artifact (`conflict_review_items.json` / `core_progress.json`) を退避する。新 SpecClaim 経路の結果と diff して recall 比較する。比較が必要な場合、production config を変更しない (legacy mode を増やさない)。比較は revision 切替と artifact 退避で行う。
- recall 比較の手順と結果は新規ファイル `doc/性能測定/spec_claim_migration_comparison.md` に記録する (作成タイミングは本 task 着手時)。

#### 目的

Phase 5 着手前に、SpecClaim 経路で既知 conflict fixture が Conflict Review に届くことを実機経路で保証する。recall 比較を実施した場合はその結果を記録し、Phase 5 削除判断の根拠データにする。

合格基準:

- 既知 conflict fixture を含む Source Specs で実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う `/spec-core` を実行し、当該 conflict pair が SpecClaim 経路で `triage.send_to_review = true` として Conflict Review pipeline に届く。
- 当該 conflict が `conflict_review_items.json` に `status="pending"` として記録される (LLM judge が pending と判定した場合) または `potential_conflicts` warning として diagnostics に出る (LLM judge が non-pending と判定した場合) のいずれか。
- production config に legacy mode key を追加していない。
- 任意で recall 比較を実施した場合、`doc/性能測定/spec_claim_migration_comparison.md` に手順と結果を記録する。

#### 実装方針

1. 既知 conflict fixture を `tests/fixtures/spec_claim_recall/` 配下に整備する (Source Specs / Purpose / Core Concept / 想定 conflict pair の expected outcome を含む)。
2. integration test `tests/test_spec_claim_e2e.py` (新規) を追加し、fake 用 fixture で SpecClaim 抽出 → Claim Retrieval → LLM triage → Conflict Review pipeline 着信までを E2E で確認する。
3. 実機検証ガイド `doc/性能測定/spec_claim_migration_comparison.md` を新規作成し、次を記述する:
   - Phase 5 着手前 revision の checkout 手順
   - `/spec-core` 実行と artifact 退避手順
   - Phase 4 完了時点 revision での `/spec-core` 実行手順
   - artifact diff の比較観点 (recall / wall time / token / candidate 数 / Conflict Review 到達数 / Conflict Review Item 作成数)
   - 結果記録テンプレート (実施日 / fixture / 旧経路 / 新経路 / diff)
4. 実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う `/spec-core` 実行を実施し、結果を `doc/性能測定/spec_claim_migration_comparison.md` に記録する (実機 1 回で十分。複数 fixture を使う場合は entry を追加)。

#### 検証条件

A. **fake 用 E2E テスト** (`tests/test_spec_claim_e2e.py` 新規):

- 既知 conflict fixture (fake 版) で SpecClaim 抽出 → Claim Retrieval → LLM triage → Conflict Review pipeline まで一貫して動き、当該 pair が `triage.send_to_review = true` として Conflict Review に届く。

B. **実機経路** (real Codex / Claude CLI + Qdrant + FlagEmbedding BGE-M3、未実行時は残 TODO):

- 既知 conflict fixture を含む Source Specs で実機 `/spec-core` を実行し、当該 conflict が SpecClaim 経路で `triage.send_to_review = true` として Conflict Review に届く。
- 結果を `doc/性能測定/spec_claim_migration_comparison.md` に記録する。
- production config に `legacy_*` key を追加していないことを `grep -nE "legacy_possible_conflict_mode|legacy_related_possible_conflict" .spec-anchor/config.toml` で確認する。

C. **任意 recall 比較** (Phase 5 着手判断の根拠データとして):

- Phase 5 着手前 revision で `/spec-core` 実行 → artifact 退避 → Phase 4 完了時点 revision で `/spec-core` 実行 → artifact diff の手順を `doc/性能測定/spec_claim_migration_comparison.md` に従って実施する。
- 結果 (recall 維持 / 低下 / 増加) を記録する。recall 低下が検出された場合は Phase 5 着手を保留し、SpecClaim 経路の retrieval / triage の改善を別 task として切り出す。

D. **既存 pytest**: `pytest --skip-external` が pass する。

#### 触れる主なファイル

- `tests/fixtures/spec_claim_recall/` (新規): 既知 conflict fixture
- `tests/test_spec_claim_e2e.py` (新規): fake 用 E2E テスト
- `doc/性能測定/spec_claim_migration_comparison.md` (新規): 実機検証ガイド + 結果記録
- 実機検証実施時は対象プロジェクトの `.spec-anchor/config.toml` / `.spec-anchor/context/` / `.spec-anchor/state/` を読み取り対象とする (本 task では編集対象としない)

#### 完了条件

- A の fake 用 E2E テストが pass する。
- B の実機検証を 1 回以上実施し、結果を `doc/性能測定/spec_claim_migration_comparison.md` に記録する。実機検証が未実施の場合、Phase 5 (T-spec-claim-phase-5) 着手を保留する。
- C の recall 比較を任意で実施した場合、結果を `doc/性能測定/spec_claim_migration_comparison.md` に追記する。
- D の `pytest --skip-external` が pass する。

#### 依存 / scope 外

- **依存**: T-spec-claim-phase-1、T-spec-claim-phase-2、T-spec-claim-phase-3。
- **scope 外**:
  - `possible_conflict` 経路の削除は T-spec-claim-phase-5 で実装する。本 Phase では既存 `possible_conflict` 経路を変更しない (recall 比較で旧経路を実行する必要があるため)。
  - Conflict Review 入力境界の SpecClaim pair 固定 (SCD-033) は T-spec-claim-phase-5 で実装する。

### [完了 2026-05-29, commit da692ba] T-spec-claim-phase-5: `possible_conflict` 経路の完全削除 + Conflict Review 入力境界変更 (SCD-032 / SCD-033 Phase 5)

#### 背景

T-spec-claim-phase-4 で SpecClaim 経路の recall が許容範囲であることが実機で確認できたら、本 Phase は `possible_conflict` 経路を production code / docs / tests から完全削除し、Conflict Review 入力境界を SpecClaim pair に固定する (SCD-033)。

これは契約と実装の divergence を解消する commit。`doc/EXTERNAL_DESIGN.ja.md` (commit aa83f63) と `doc/DESIGN.ja.md` (commit 8272ab9) はすでに最終状態 (`possible_conflict` 言及なし) を記述しているので、本 Phase の実装変更で doc と code の整合が回復する。

#### 真因 / 対応方針

真因 (確定):

- 現在 `spec_anchor/related_sections.py` / `spec_anchor/llm_provider.py` / `spec_anchor/core.py` / `spec_anchor/conflict_review.py` / 関連 tests / `[limits].conflict_pair_max_per_section` 設定が `possible_conflict` 経路を生かしている。これらを Phase 5 で完全削除する。
- Conflict Review pipeline は現在 Related Sections の `relation_hint` と `possible_conflict` flag を入力にしているが、Phase 5 では SpecClaim pair / evidence / triage result のみを入力にする (SCD-033)。

対応方針 (確定):

- `spec_anchor/related_sections.py` の schema / prompt / output から `possible_conflict` field を削除する。LLM prompt が `possible_conflict` 判定を要求する箇所、schema validation で `possible_conflict` field を期待する箇所、`possible_conflict` flag を読み取り output へ書き込む箇所をすべて削除する。
- `spec_anchor/llm_provider.py` の `possible_conflict` schema 定義を削除する。
- `spec_anchor/core.py` の `possible_conflict=true` 由来 Conflict Review routing (`conflict_route: "possible_conflict_flag"` 等) を削除する。Conflict Review への入力は SpecClaim pair の `triage.send_to_review = true` 由来のみとする。
- `spec_anchor/conflict_review.py` の relation_hint 整合 filter (現状 L367-421 周辺、`possible_conflict` flag 前提で relation_hint を再 filter する処理) を削除する。`evaluate_conflicts` の入力 schema を SpecClaim pair / evidence / triage result に変更する。`select_conflict_judging_pairs` の legacy backward compat 経路も削除する。
- `[limits].conflict_pair_max_per_section` 設定 key と関連処理を削除する。`spec_anchor/config.py` / config loader の該当 field validation を削除する。
- `tests/test_conflict_review.py::test_phase_e_possible_conflict_flag_routes_to_conflict_review` および関連 `possible_conflict` 経路 routing test を削除する。代わりに次の test を追加する (`tests/test_related_sections.py` / `tests/test_conflict_review.py`):
  - Related Sections output に `possible_conflict` field が存在しない
  - Related Sections prompt が conflict 判定を要求しない
  - `spec_anchor/core.py` が Related Sections output から `possible_conflict` を読まない
  - SpecClaim candidate pair の `triage.send_to_review = true` だけが Conflict Review に渡る
- `doc/DESIGN.ja.md` §0 implementation tracker の T-spec-claim-phase-5 関連 `[ ]` task を `[x]` に変える。evidence link (file:line + test) を併記する。
- T-conflict-source-update-flow の test fixture (B 区分「pair が消えた場合の解除」内の Related Sections candidate fixture) を SpecClaim retrieval candidate fixture に更新する (Phase 5 後は Related Sections は conflict pair を出さないため)。

#### 目的

`possible_conflict` 経路を production code / docs / tests から完全削除し、Conflict Review pipeline の入力境界を SpecClaim pair に固定する。doc と code の divergence を解消する。

合格基準:

- `git grep -nE "possible_conflict|legacy_related_possible_conflict|legacy_possible_conflict_mode|conflict_pair_max_per_section" spec_anchor tests` の hit が 0 件 (`doc/性能測定/spec_claim_migration_comparison.md` 内の比較記録、および `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` §18 retired SCDs の歴史記録、`doc/DESIGN.ja.md` §0 implementation tracker の歴史記録は許容例外)。
- Related Sections output に `possible_conflict` field が存在しないことを test で検出できる。
- Related Sections prompt が conflict 判定を要求しないことを test で検出できる。
- `spec_anchor/core.py` が Related Sections output から `possible_conflict` を読まないことを test で検出できる。
- SpecClaim candidate pair の `triage.send_to_review = true` だけが Conflict Review に渡ることを test で検出できる。
- Conflict Review pipeline の入力が SpecClaim pair / evidence / triage result に変わっており、Related Sections の `relation_hint` や旧 `possible_conflict` 由来 pair が渡らない。
- 実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う `/spec-core` で T-spec-claim-phase-4 の既知 conflict fixture が引き続き Conflict Review に届く (recall 維持)。

#### 実装方針

1. `spec_anchor/related_sections.py` の `possible_conflict` 関連処理を削除する (schema、prompt 文言、output 書き込み、validation の各箇所)。
2. `spec_anchor/llm_provider.py` の `possible_conflict` schema 定義を削除する。
3. `spec_anchor/core.py` の `possible_conflict=true` Conflict Review routing を削除する (`_generate_related_sections` 後の routing block、`conflict_route: "possible_conflict_flag"` 関連)。
4. `spec_anchor/conflict_review.py` の relation_hint 整合 filter (L367-421 周辺) を削除し、`evaluate_conflicts` の入力 schema を SpecClaim pair / evidence / triage result に変更する。`select_conflict_judging_pairs` の legacy 経路を削除する。
5. `spec_anchor/config.py` / config loader から `[limits].conflict_pair_max_per_section` を削除する。
6. `tests/test_conflict_review.py::test_phase_e_possible_conflict_flag_routes_to_conflict_review` を削除する。
7. 新規 test を `tests/test_related_sections.py` / `tests/test_conflict_review.py` に追加する:
   - `test_related_sections_output_has_no_possible_conflict_field`
   - `test_related_sections_prompt_does_not_request_conflict_judgment`
   - `test_core_does_not_route_related_sections_to_conflict_review`
   - `test_conflict_review_accepts_only_spec_claim_pair_input`
8. T-conflict-source-update-flow の test fixture (Related Sections candidate fixture 由来部分) を SpecClaim retrieval candidate fixture に更新する。
9. `git grep -nE "possible_conflict|legacy_related_possible_conflict|legacy_possible_conflict_mode|conflict_pair_max_per_section" spec_anchor tests` を実行し、hit が 0 件であることを確認する (許容例外を除く)。
10. 実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う `/spec-core` を T-spec-claim-phase-4 の既知 conflict fixture で実行し、当該 conflict が引き続き Conflict Review に届くことを確認する。
11. `doc/DESIGN.ja.md` §0 implementation tracker の SCD-032 / SCD-033 関連 `[ ]` task を `[x]` に変えて evidence link を記録する。

#### 検証条件

A. **削除の grep 検証**:

- `git grep -nE "possible_conflict|legacy_related_possible_conflict|legacy_possible_conflict_mode|conflict_pair_max_per_section" spec_anchor tests` の hit が 0 件 (`doc/` 配下の歴史記録、`doc/性能測定/spec_claim_migration_comparison.md` の比較記録、`doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` §18 retired section、`doc/DESIGN.ja.md` §0 implementation tracker の歴史記録は許容)。

B. **新規 test**:

- `test_related_sections_output_has_no_possible_conflict_field` / `test_related_sections_prompt_does_not_request_conflict_judgment` / `test_core_does_not_route_related_sections_to_conflict_review` / `test_conflict_review_accepts_only_spec_claim_pair_input` が pass する。

C. **既存 test**:

- T-conflict-source-update-flow の B 区分 (pair が消えた場合の解除) の fixture を SpecClaim retrieval candidate fixture に更新したうえで pass する。
- `tests/test_conflict_review.py::test_phase_e_possible_conflict_flag_routes_to_conflict_review` が削除されている (= 該当 test が collection に存在しない)。

D. **実機経路** (real provider 経路、未実行時は残 TODO):

- 実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う `/spec-core` で T-spec-claim-phase-4 の既知 conflict fixture が引き続き `triage.send_to_review = true` として Conflict Review に届く (recall 維持)。

E. **既存 pytest**: `pytest --skip-external` が pass する。

#### 触れる主なファイル

- `spec_anchor/related_sections.py`: `possible_conflict` 関連処理の削除
- `spec_anchor/llm_provider.py`: `possible_conflict` schema 定義の削除
- `spec_anchor/core.py`: `possible_conflict=true` Conflict Review routing の削除
- `spec_anchor/conflict_review.py`: relation_hint 整合 filter の削除、`evaluate_conflicts` 入力 schema の SpecClaim pair 化、`select_conflict_judging_pairs` legacy 経路の削除
- `spec_anchor/config.py` / config loader: `[limits].conflict_pair_max_per_section` の削除
- `tests/test_conflict_review.py`: `test_phase_e_possible_conflict_flag_routes_to_conflict_review` の削除、新規 test の追加
- `tests/test_related_sections.py`: 新規 test の追加 (`possible_conflict` field 不在の検証)
- `tests/test_spec_core.py`: T-conflict-source-update-flow B 区分 fixture の SpecClaim retrieval candidate fixture への更新
- `doc/DESIGN.ja.md` §0 implementation tracker: SCD-032 / SCD-033 関連 task を `[x]` に変更

#### 完了条件

- A の grep 検証で許容例外以外の hit が 0 件。
- B / C の test が pass する。
- D の実機経路を実行できた範囲で確認結果を記録する。実 provider / Qdrant / BGE-M3 が未実行の場合は未完了 TODO として残す。recall regression が検出された場合、Phase 5 commit を revert して SpecClaim 経路の改善を別 task として切り出す。
- E の `pytest --skip-external` が pass する。
- `doc/DESIGN.ja.md` §0 implementation tracker の SCD-032 / SCD-033 関連 task が `[x]` に更新され、evidence link (file:line + test) が併記されている。

#### 依存 / scope 外

- **依存**: T-spec-claim-phase-1、T-spec-claim-phase-2、T-spec-claim-phase-3、T-spec-claim-phase-4 (特に Phase 4 の実機 recall 確認が完了していること)。T-conflict-source-update-flow (Phase 5 で T-conflict の B 区分 fixture を SpecClaim retrieval candidate fixture に更新するため)。
- **scope 外**:
  - SpecClaim 経路の retrieval / triage の改善 (recall regression が Phase 4 で検出された場合の改善は別 task)。
  - Conflict Review pipeline の prompt 改善や judge ロジック変更は今回の scope 外 (本 Phase は入力境界変更のみ)。
  - `doc/SPEC_CLAIM_CONFLICT_CANDIDATE_DESIGN.ja.md` 自体を archive へ移す判断は別 task (本 Phase 完了後の整理 task として切り出してよい)。

### T-flaky-spec-core-responsibility-boundary: `test_spec_core_does_not_modify_purpose_or_concept_files` の偶発的失敗 (真因特定・test 修正済み、長時間検証待ち)

#### 背景

2026-05-29 の Phase 2 Part A commit `dd3c674` 直後の `python3 -m pytest -q --skip-external` で `tests/test_responsibility_boundary.py::test_spec_core_does_not_modify_purpose_or_concept_files` が 1 件 fail を観測。その後、Claude main が次を実施して再現を試みた:

- 同 test 単独実行 10 回連続: 全 pass
- full pytest 4 回連続実行: 全 pass (合計 597 passed × 4)
- 新規 file (`tests/test_claim_retrieval.py`) を退避した状態の full pytest: 589 passed, 0 failed

つまり全 15 回追加実行で 0 failed。**1/16 = 約 6% の偶発的失敗率**で、真因を特定できる再現サンプルが得られなかった。

#### 真因 / 対応方針

真因 (2026-05-29 Codex 調査で確定):

- 偶発失敗の主因は production code が `docs/core/purpose.md` / `docs/core/concept.md` を atomic write したことではなく、test infrastructure 側の subprocess 実行条件だった。
- `tests/test_responsibility_boundary.py` の `_run_spec_anchor("core", cwd=project)` は `subprocess.run([sys.executable, "-m", "spec_anchor", "core"], timeout=30)` を使うが、以前は subprocess の `env` を明示していなかった。
- subprocess が一時 project の cwd から local repo の `spec_anchor` を import できない環境では、`python -m spec_anchor` が即時 import error で終了しても、test は returncode を確認していなかったため pass していた。
- 逆に subprocess が local repo / installed package を import でき、`SPEC_ANCHOR_FAKE_LLM=1` が入っていない環境では、setup project の標準 config が real Codex / Claude provider を起動する。手元の再現では `PYTHONPATH=$PWD` かつ fake env なしの一時 project で `spec-anchor core` が `elapsed=29.844s`、`returncode=1` となった。`core_progress.json` では real LLM stage が `section_metadata=5.117s`、`related_sections=8.119s`、`spec_claims=9.073s`、`chapter_anchors=7.318s` を消費しており、outer timeout 30 秒の直前で完了していた。このため Codex / Claude CLI 起動 latency の揺れだけで `TimeoutExpired` になり得る。
- 既存 `_diag()` は Purpose / Core Concept byte mismatch の assertion message にしか入っておらず、`TimeoutExpired` では `_diag()` が出ない。したがって「再発時に `_diag()` から timeout / atomic write / 状態漏れを切り分ける」という準備は timeout 仮説に対して不十分だった。
- `spec_anchor/core.py` の確認では、Purpose / Core Concept は `_read_required()` で読み込まれ、`ContextArtifactStore.write_context_update()` が書く対象は `.spec-anchor/state/section_manifest.json`、`.spec-anchor/context/conflict_review_items.json`、`.spec-anchor/context/chapter_anchors.json`、`.spec-anchor/state/freshness.json` である。Purpose / Core Concept file path は write target に含まれない。

対応済み:

- `tests/test_responsibility_boundary.py` の subprocess helper で `PYTHONPATH` に repo root を明示し、`SPEC_ANCHOR_FAKE_LLM=1` / `SPEC_ANCHOR_FAKE_RETRIEVAL=1` を明示するよう修正した。
- timeout は `CompletedProcess(returncode=124)` として返し、既存 `_diag()` に `returncode` / stdout / stderr が載るよう修正した。
- 該当 test の一時 project では `.spec-anchor/config.toml` の `[embedding].provider` / `[vector_store].provider` を `none` に変更し、Qdrant / BGE-M3 がない環境でも `/spec-core` が正常終了する deterministic path にした。
- `result.returncode == 0` を read-only assertion の前に確認するよう修正した。これにより import error や provider failure で `/spec-core` が実際には走っていない pass を防ぐ。

#### 目的

- 再発時に真因を特定し、production-critical な「`/spec-core` は purpose / concept を変更しない」契約 (`doc/EXTERNAL_DESIGN.ja.md` §5.3 L416) を信頼できる test で守る。
- `_diag()` 改善は本 task の準備として既に commit 済み (本 commit)。

#### 実装方針

実装済み:

1. `tests/test_responsibility_boundary.py` の subprocess helper を、local repo import / fake LLM / timeout 診断を明示する形に変更する。
2. `test_spec_core_does_not_modify_purpose_or_concept_files` の一時 project config で external retrieval を無効化し、Qdrant / BGE-M3 に依存しない正常系 `/spec-core` を実行する。
3. `/spec-core` subprocess の returncode が 0 であることを確認してから、Purpose / Core Concept の byte 一致を確認する。

残作業:

4. 長時間検証として full pytest 100 回相当で偶発 timeout / import error / file mutation が再発しないことを確認する。

#### 検証条件

- 真因は test infrastructure 側の subprocess 実行条件 + 30 秒 timeout 境界として確定済み。
- 修正後の targeted test は pass 済み:
  - `python3 -m pytest -q tests/test_responsibility_boundary.py::test_spec_core_does_not_modify_purpose_or_concept_files --tb=short` → `1 passed in 0.23s`
  - `python3 -m pytest -q tests/test_responsibility_boundary.py --tb=short` → `6 passed in 0.76s`
  - `python3 -m pytest -q tests/test_responsibility_boundary.py tests/test_spec_core.py::test_spec_core_does_not_modify_human_owned_purpose_or_concept --tb=short` → `7 passed in 0.92s`
  - `python3 -m py_compile tests/test_responsibility_boundary.py` → pass
  - `.venv/bin/python -m pytest -q tests/test_responsibility_boundary.py::test_spec_core_does_not_modify_purpose_or_concept_files --tb=short` を 100 回連続実行 → `100/100 pass`
- 全体確認:
  - `python3 -m pytest -q --skip-external` → system python に `python-dotenv` / `qdrant_client` がなく、別 test 群で `12 failed, 592 passed, 23 skipped`
  - `.venv/bin/python -m pytest -q --skip-external` → `tests/test_spec_core_acceptance.py::test_verify_index_does_not_self_repair` の session fixture で 1 error、`604 passed, 22 skipped`
  - `.venv/bin/python -m pytest -q --skip-external tests/test_spec_core_acceptance.py::test_verify_index_does_not_self_repair --tb=short` → 単独再実行で `1 passed in 23.05s`
- 未実行: 連続 100 回 full pytest。これは長時間安定性確認として残す。

#### 触れる主なファイル

- `tests/test_responsibility_boundary.py`: subprocess env / timeout 診断 / deterministic `/spec-core` config / returncode assertion を修正済み。
- `spec_anchor/core.py`: 調査のみ。Purpose / Core Concept への write target は確認されず、修正不要。
- 原因 test (二分探索で特定): 状態漏れ仮説は採用しない。現時点で追加 teardown は不要。

#### 完了条件

- 真因が確定し、修正が入る。`tests/test_responsibility_boundary.py` 修正済み。
- 本 task entry に確定真因と修正経路を記録する。記録済み。
- 未完了: 連続 100 回 full pytest で 100/100 pass する。

#### 依存 / scope 外

- **依存**: なし (独立 task)。
- **scope 外**:
  - 他の flaky test の追跡 (本 task は本 1 件に限定)。
  - 予防的な subprocess timeout 一律延長 (真因確定前の予防修正は scope 外)。

### [完了 2026-05-29, commit 2ff711b] T-spec-inject-pending-conflict-fixture-update: PendingConflictSpecCoreProvider を SpecClaim 経路に追従させる

#### 背景

Phase 5 (T-spec-claim-phase-5, commit シリーズ) で Related Sections の `relation_hint = "conflicts_with"` 経路と `possible_conflict` field 由来の Conflict Review routing を完全廃止した (SCD-032 / SCD-033)。

これにより `tests/test_spec_inject.py::PendingConflictSpecCoreProvider` (line 112-155) が依存する経路が消えた:

```python
return {
    "related_sections": [{
        "target_section_id": target,
        "relation_hint": "conflicts_with",  # ← Phase 5 で出力 enum から削除
        ...
    }],
}
```

結果として `tests/test_spec_inject.py::test_review_pending_conflict_items_are_loaded_from_real_context_artifact` が `pending_conflict_count == 0` で失敗し、`@pytest.mark.skip` で一時 skip した (commit 後の HEAD で確認できる)。

#### 真因 / 対応方針

真因 (確定):

- `PendingConflictSpecCoreProvider.generate(request)` は `request.stage == "related_section_selection"` のときに `relation_hint = "conflicts_with"` を含む応答を返している。これが旧 Conflict Review pipeline の入力源だった。
- Phase 5 で `evaluate_conflicts` の入力境界が SpecClaim pair + evidence + triage result に変更されたので、Related Sections 由来の応答では Conflict Review に届かなくなった。

対応方針 (確定):

- `PendingConflictSpecCoreProvider` を SpecClaim 経路に追従させる。次の stage に fake 応答を追加する:
  - `request.stage == "spec_claims"`: 2 つの section から conflict する SpecClaim を抽出する応答 (各 section 1 件以上、矛盾する `claim_text` + `evidence_span`)
  - `request.stage == "conflict_candidate_triage"`: 2 つの SpecClaim pair について `send_to_review = true`, `confidence = "high"` を返す応答
  - `judge_conflict()` は現状維持 (`needs_human_review` を返す既存実装で OK)
- `_write_conflicting_project` の Source Specs (`docs/spec/security.md` の Authentication / Session 2 section) はそのまま使う。`PendingConflictSpecCoreProvider` だけを書き換えれば test は SpecClaim 経路で pending item を作れる。
- 書き換え後、`@pytest.mark.skip` を外して test pass を確認する。
- 必要なら `spec_claims_state.json` / `conflict_candidate_pairs_state.json` の atomic write 経路に fake fixture が触れるかも確認 (Phase 1/2/3 の test_spec_core.py の incremental test を参考にする)。

#### 目的

`/spec-inject` の pending conflict 表示経路が、Phase 5 後の SpecClaim 経路でも end-to-end で動くことを fake fixture で保証する。

合格基準:

- `tests/test_spec_inject.py::test_review_pending_conflict_items_are_loaded_from_real_context_artifact` が `@pytest.mark.skip` を外した状態で pass する。
- `pending_conflict_count >= 1`、`freshness.status == "blocked"`、`blocking_reasons == ["pending_conflict"]`、`pending_items` に Phase 5 後の Conflict Review pipeline が生成した item が含まれる。
- `/spec-inject` の出力に Phase 5 後の test 構造で `conflict-from-spec-core-artifact` (または書き換え後の対応する conflict_id) と `why_llm_cannot_decide` が含まれる。

#### 実装方針

1. `tests/test_spec_inject.py::PendingConflictSpecCoreProvider` の `generate(request)` で `request.stage` 分岐を追加:
   - `"spec_claims"`: 各 section から conflicting claim を返す
   - `"conflict_candidate_triage"`: pair を `send_to_review=true` で返す
2. `@pytest.mark.skip` を外す
3. `python3 -m pytest -q tests/test_spec_inject.py::test_review_pending_conflict_items_are_loaded_from_real_context_artifact` が pass することを確認

#### 検証条件

- 上記 test が pass する。
- `python3 -m pytest -q --skip-external` の合計 passed が +1 (skip 解除分)。

#### 触れる主なファイル

- `tests/test_spec_inject.py`: `PendingConflictSpecCoreProvider` の書き換え + skip 解除

#### 完了条件

- 該当 test が pass する。
- `@pytest.mark.skip` が消えている。
- `pytest --skip-external` が pass する。

#### 依存 / scope 外

- **依存**: T-spec-claim-phase-5 完了 (Phase 5 後の Conflict Review 入力境界が SpecClaim pair に固定されていることが前提)。
- **scope 外**:
  - `PendingConflictSpecCoreProvider` 以外の fake fixture (本 task は本 fixture 1 件の追従に限定)。
  - 実 Codex / Claude CLI 経路は別 task (本 task は fake fixture の追従のみ)。
