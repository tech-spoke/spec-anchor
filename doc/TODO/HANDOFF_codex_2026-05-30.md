# CODEX 引き継ぎ: 矛盾解決軽量化 TODO の残作業

**作成日**: 2026-05-30
**作成者**: Claude main (実装途中で引き継ぎ)
**正本 TODO**: `doc/TODO/TODO_conflict_resolution_simplification.ja.md`
**現 HEAD**: `678ec85`（working tree クリーン、全コミット済み）

---

## 0. まず読む（この順）

1. `doc/TODO/TODO_conflict_resolution_simplification.ja.md` — 実装スペック正本（sub task #1〜#8 + 検証条件 + 完了条件）
2. `CLAUDE.md` — 不変ルール。特に **ルール7（完了ガード）/ ルール8（失敗を計画へ反映）/ ルール15（廃止=根絶）/ ルール18（worktree 禁止）**
3. 本ファイル

## 1. 結論サマリー（何が終わって何が残っているか）

### コア実装（#1〜#7）: 実装は妥当。ただし **テストが 61 failed / 3 errors で赤**
`pytest --skip-external` = **631 passed / 61 failed / 22 skipped / 3 errors**。
失敗は「実装バグ」ではなく、ほぼ全て **テストファイル側の取りこぼし** が原因（真因 A / B、後述）。コア production コード（`spec_anchor/*.py`）は新契約で実装済み。

### ドキュメント（#6）: コミット済み・概ね反映。残 grep ヒットあり（後述 §4）

### E2E（#8）: **未着手**

---

## 2. 確定した新契約（これに整合させる。TODO 本文が正本だが要点を再掲）

- 矛盾（Conflict Review Item）の状態は **pending / dismissed の 2 値のみ**。`resolved` 廃止。
- decision 機構を全廃: `prefer_a` / `prefer_b` / `conditional` / `task_scope_resolution` / `needs_source_update` / `defer` / `--decision-json` / `--decision-file` / `unreflected_conflict_resolutions` / decision payload。残るのは **dismiss のみ**。
- 人間の却下インターフェースは **`spec-anchor core --dismiss-conflict <conflict_id> --reason "..."`** の 1 つだけ（`--reason` 必須）。
- 却下は永続化。却下根拠セクションのハッシュが変われば `/spec-core` 再生成で自動失効（**`stale_dismissal`**、旧 `stale_resolution` から改名済み）し、矛盾は再 pending に戻る。
- pending conflict は **freshness の停止理由ではない**（注入情報）。CLI（inject）は `pending_conflict_items` / `pending_conflict_count` を情報として返す。
- **`/spec-realign` に CLI 答案抑止ゲートを足さない**（最重要・誤実装しやすい）。止める/進むはテンプレ（`/spec-realign`）+ LLM の責務。CLI（realign）は渡された答案を構造化するだけ。
- Agentic Search は **4 path → 3 path**（path④ resolved Conflict Review Item からの evidence 抽出を廃止）。`inject-conflicts` CLI も廃止。
- `evidence_origin` の選択肢は **Purpose / Core Concept / Source Specs の 3 種**（「Conflict Review Item」を除外。ただし矛盾概念=pending/dismissed は残る）。
- freshness status は **4 値 → 3 値（fresh / blocked / failed）**。`degraded` 廃止。section_metadata 部分失敗も failed。停止理由は 7 値 → 5 値。
- CLAUDE.md ルール 4 / 5 は **完全削除・欠番維持**（`AGENTS.md` がルール 6〜12 を番号参照しているため繰り上げ厳禁。6〜19 は不変）。
- 既存 `status="resolved"` データの後方互換・migration は scope 外（リリース前の破壊的変更）。

---

## 3. テスト失敗の真因と修正手順（最優先）

### 真因 A（最大・37件）: `tests/test_spec_core.py` のヘルパー `_run_spec_core` が消えている

`26ef031`（#2）で使った機械的 strip ツールが、**ヘルパー関数 `def _run_spec_core` の本体に削除対象シンボル（`decision_payload` / `conflict_decision`）が含まれていたため、関数定義ごと削除**してしまった。呼び出し 59 箇所が残り全て `NameError: name '_run_spec_core' is not defined`。

**修正手順:**
1. 次の定義を `tests/test_spec_core.py` の `_call`（行 247 付近）の直後に復元する。ただし **削除済みシンボル（`decision_payload` / `decision` / `conflict_decision`）の行は除去**した新契約版を入れる（現行 `run_spec_core` はこれらを受け取らないが、`_call` が `inspect.signature` で未対応 kw をフィルタするため害はない。clean のため除く）:

```python
def _run_spec_core(project_root: Path, **kwargs: Any) -> Any:
    func = _run_function()
    all_mode = bool(kwargs.pop("all_mode", False))
    provider = kwargs.pop("provider", None)
    return _call(
        func,
        _positional=(project_root,),
        project_root=project_root,
        root=project_root,
        cwd=project_root,
        all=all_mode,
        all_mode=all_mode,
        full=all_mode,
        force=all_mode,
        mode="full" if all_mode else "incremental",
        provider=provider,
        llm_provider=provider,
        conflict_judge=provider,
        judge=provider,
        generated_at="2026-05-06T00:00:00Z",
        **kwargs,
    )
```

   元の定義は `git show 2ab6252:tests/test_spec_core.py` の 258〜285 行にある（`decision_payload=decision_payload` / `decision=decision_payload` / `conflict_decision=decision_payload` の 3 行を含むので、それを削った上記版を使う）。

2. 復元後、`test_spec_core.py` 単体を実行し 37 件が解消することを確認:
   ```
   .venv/bin/python -m pytest tests/test_spec_core.py -p no:cacheprovider -q
   ```
   - `decision_payload` を渡していた呼び出しが残っていれば、新契約では渡せないので呼び出し側も外す。
   - 削除済みテスト関数（`test_t_i14_decision_payload_resolves_pending_item_through_spec_core_api` 等、`#2` strip で正当に消えた4件）は**復活させない**。

### 真因 B（残テストの新契約未追従・約24件）

削除した機構をまだ assert している既存テスト。新契約へ更新 or 削除する。

| ファイル | 件数 | 内容 | 対応 |
|---|---|---|---|
| `tests/test_spec_core_acceptance.py` | 11 | `test_cli_flag_accepted[--decision-json/--decision-file]`、`test_core_result_field[unreflected_conflict_resolutions/stale_resolution_count]`、`test_decision_option_offered[prefer_a/conditional/needs_source_update/defer]` | これらは EXTERNAL_DESIGN の行番号パラメータ（L601 等）を読む契約テスト。削除した行を参照しているので、パラメータを新契約の行（`stale_dismissal_count` 等）へ更新 or 該当パラメータ削除。**EXTERNAL_DESIGN 側は既に新契約化済み**なので、テストのパラメータ表を現行行へ合わせる |
| `tests/test_setup_scripts.py` | 5 | テンプレが `inject-conflicts` / 「自動実行しない」キーワードを期待。`spec-inject.md` / `spec-realign.md` のテンプレ突合 | 新契約テンプレ（3 path / dismiss-conflict）に合わせて期待キーワードを更新 |
| `tests/test_spec_inject.py` | 3 | `test_t_i09_pending_conflict_stop_output_surfaces_items` 他。pending で stop する旧挙動を期待 | pending 非ブロック新挙動（fresh で継続 + items 提示）へ更新 |
| `tests/e2e/test_user_facing_output.py` | 3 | `[inject-conflicts]` scenario / `test_template_command_matches_project[spec-inject.md/spec-realign.md]` | #8 と併せて処理。inject-conflicts scenario 除去、template 突合更新 |
| `tests/test_responsibility_boundary.py` | 1 | `test_cli_does_not_accept_conversation_transcript_argument`（inject-conflicts 参照の可能性） | inject-conflicts 言及を除去 |
| `tests/test_release_readiness.py` | 1 | `test_t_r04_release_smoke_uses_temp_project_and_fake_inputs` | smoke が inject-conflicts を叩いていれば除去 |
| `tests/test_project_skeleton.py` | 1 | `test_t_p02_main_cli_dispatches_primary_commands_as_json[inject-conflicts-...run_inject_conflicts...]` | inject-conflicts パラメータ削除 |
| `tests/test_core_progress.py` | 1 | `test_run_spec_core_writes_progress_artifact` | 真因 A の `_run_spec_core` 復元で直る可能性。要再確認 |
| `tests/test_conflict_review.py` | 1 | `test_t_u14_pending_item_required_schema_fields` | `decision_options` 全廃で schema が変わった。pending item に decision_options を要求しないよう更新 |

### errors（3件）: `tests/test_spec_core_acceptance.py`
`test_retrieval_index_partial_upsert_on_incremental` / `test_related_sections_partial_regeneration_diagnostics` / `test_related_sections_partial_mode_flags` が collection error。真因 A（同ファイル内の他テストが `_run_spec_core` 参照）の巻き添えの可能性。A 修正後に再確認。

---

## 4. #6 ドキュメント残 grep（未処理・未検証）

EXTERNAL_DESIGN は禁止語 0 で完了。残りは以下。`doc/TODO/**` と `archive/` を除いて 0 件にする（TODO 検証条件）:

- `doc/EXTERNAL_SPEC_DRAFT.ja.md`: 残 4（`inject-conflicts` ×1 / `decision-json` ×1 / `decision-file` ×1 / `stale_resolution` ×1）
- `doc/DESIGN.ja.md`: 残 13（`inject-conflicts` ×2 / `prefer_a` / `prefer_b` / `task_scope_resolution` / `needs_source_update` / `unreflected_conflict_resolution` / `decision_payload` / `4 path` ×2 / `path ④` ×2 / `stale_resolution` ×1）

各箇所を新契約（pending/dismissed・3 path・stale_dismissal・dismiss-conflict）へ書き換える。DESIGN は内部設計書なので内部用語可。SPEC_DRAFT は外部仕様 draft なので CLAUDE.md ルール14（ソース未読の読者に通じる言葉）に従う。

検証コマンド:
```bash
git grep -nE "decision-json|decision-file|decision_json|decision_file|decision payload|decision_payload|prefer_a|prefer_b|task_scope_resolution|needs_source_update|unreflected_conflict_resolution|inject-conflicts|inject_conflicts|stale_resolution" -- doc/EXTERNAL_DESIGN.ja.md doc/EXTERNAL_SPEC_DRAFT.ja.md doc/DESIGN.ja.md .codex spec_anchor/templates/.codex CLAUDE.md
# → 0 件であること（doc/TODO/** と archive/ は対象外）
git grep -nE "4 path|path ④|path④" -- doc/EXTERNAL_DESIGN.ja.md doc/EXTERNAL_SPEC_DRAFT.ja.md doc/DESIGN.ja.md .codex spec_anchor/templates/.codex .claude
# → 0 件（3 path へ）
```

---

## 5. #8 E2E（未着手・TODO #8 参照）

- 既存 `tests/e2e/` 基盤を再利用（再構築しない）。
- `#2-s06`（degraded 続行 snapshot）を `scenarios.py` と live snapshot から除去。`git grep "#2-s06"` が `tests/e2e/` の live で 0 件。
- `#3`/`#4` 系 snapshot を新挙動で再生成。
- 新シナリオ #8-s01〜s07（TODO #8 の表）を追加。`tests/e2e/forbidden_terms.py` の `degraded_optional_artifact` / `unreflected_conflict_resolution` 等の扱いも新契約へ。
- 3 段ゲート（pytest pass + LLM 自己確認 + 人間レビュー）。人間レビューは外出中のオーナー判断待ちなので、pytest + LLM 自己確認まで進め、人間レビューを残 TODO にする。

---

## 6. 完了済みコミット（参考・触らない）

```
678ec85 fix(#1,#3,#4,#7): 直前コミットで欠落していたコア処理とテストを補完
fe6764b docs(codex-skill): 矛盾解決軽量化を Codex skill へ反映 (#6)
13bc941 docs(design): 矛盾解決軽量化を内部設計書へ反映 (#6)
3edc8dd docs(spec-draft): 矛盾解決軽量化を外部仕様 draft へ反映 (#6)
cde196c docs(external-design): 矛盾解決軽量化を外部設計書へ反映 (#6)
394709d docs(#5,#6): .claude コマンドテンプレを新契約へ整合
16f97cd docs(#6): CLAUDE.md ルール 4 / ルール 5 を完全削除(欠番維持)
e71dea1 feat(#1,#7): pending を非ブロック化し degraded status を failed に畳む
26ef031 feat(#2): decision 機構と resolved 状態・path④ を根絶
7ae4be6 feat(#4): dismiss 失効と再オープン + stale_resolution→stale_dismissal 改名
6aa9c62 feat(#3): spec-anchor core --dismiss-conflict で却下を永続化
```

**重要な既知の不整合**: 上記コミットのうち `26ef031`（#2）・`7ae4be6`（#4）はコミットメッセージの主張と実体が一部ズレていた（reopen 呼び出し欠落・テストヘルパー削除）。`678ec85` で一部補完済みだが、本ファイル §3 の修正が残っている。コミットメッセージを鵜呑みにせず、必ず production コードと test の実体を確認すること。

---

## 7. CODEX 作業手順（推奨順）

1. **真因 A 修正**: `_run_spec_core` 復元（§3）→ `pytest tests/test_spec_core.py -q` で確認 → コミット
2. **真因 B 修正**: ファイル単位で新契約へ更新（§3 表）→ 各ファイル単位で `pytest tests/<file> -q` → コミット（sub task 監査がファイル単位のため小さく分ける）
3. **#6 残 grep 解消**（§4）→ grep 0 件確認 → コミット
4. **フル pytest**: `.venv/bin/python -m pytest --skip-external -q`（約 6.5 分）で **0 failed / 0 errors** を確認。これが通るまで「完了」と報告しない（CLAUDE.md ルール7）
5. **#8 E2E**（§5）→ pytest + LLM 自己確認まで。人間レビューは残 TODO
6. 完了時、TODO ファイルの状況サマリ表を更新し、`doc/TODO/完了済みTODO/TODO_2026-05-30_conflict_resolution_simplification.ja.md` へ `git mv`

## 8. 守ること（CLAUDE.md 不変ルール）

- **ルール7**: smoke/skip 通過を完了扱いしない。`pytest --skip-external` 全緑を確認してから完了報告。
- **ルール8**: 失敗を見つけたら loop（失敗検出→修正→再テスト→報告）を止めない。
- **ルール15**: 廃止=根絶。stub/コメントアウトで名前を残さない。grep 0 件を実行。
- **ルール18**: git worktree を作らない。main ブランチ上で直接コミット。
- **(b) 確定事項**: `run_spec_realign` に `pending_conflict_count > 0` の答案抑止ゲートを足さない。
- **Python は `python3` / `.venv/bin/python`**。`python` 直呼び禁止。
- pytest は `.venv/bin/python -m pytest` で呼ぶ。`PYTHONDONTWRITEBYTECODE=1` を付けるとキャッシュ汚染を避けられる。

## 9. 検証用ワンライナー集

```bash
# フルテスト（最終確認・6.5分）
.venv/bin/python -m pytest --skip-external -q

# 失敗をファイル別集計
.venv/bin/python -m pytest --skip-external -q -p no:cacheprovider 2>&1 | grep -aE "^(FAILED|ERROR) " | sed -E 's/^(FAILED|ERROR) //; s/::.*//' | sort | uniq -c | sort -rn

# #2 根絶 grep（コード+テスト、0 件にする語）
git grep -nE "prefer_a|prefer_b|task_scope_resolution|needs_source_update|unreflected_conflict_resolution|decision-json|decision-file|decision_json|decision_file|decision_payload|conflict_decision|resolved_conflict|usable_conflict_resolution_evidence|filter_usable_conflict_evidence|RESOLVED_DECISIONS|PENDING_DECISIONS|run_inject_conflicts|inject-conflicts|inject_conflicts" -- 'spec_anchor/*.py' tests

# stale_resolution 改名漏れ（0 件）
git grep -nE "stale_resolution" -- 'spec_anchor/*.py' tests

# git worktree を作っていないこと
git worktree list
```
