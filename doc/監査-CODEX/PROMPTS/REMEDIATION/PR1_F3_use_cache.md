# PR 1: F-3 `--use-cache` 完全削除 (Codex 作業仕様)

監査 Step 5 §3.3 / §8.1 F-3 で確定した修正方針 **C（完全削除）** を実装する PR。

worktree 作業:

- path: `/home/kazuki/public_html/spec-grag.wt-fix-use-cache`
- branch: `fix-use-cache`
- base: `main` の `5a66eb9` (監査成果物確定済み)

---

## 1. 修正の本質

外部設計書 §7.1 [行 502](doc/EXTERNAL_DESIGN.ja.md#L502) で「`--use-cache` は deprecated (挙動は無指定と同等)」と明記、§7.2 CLI フラグ表 [行 517-525](doc/EXTERNAL_DESIGN.ja.md#L517-L525) には未掲載。実装は `--use-cache` が cache 削除をスキップする機能を保持しており、**仕様と矛盾**。template / test / 利用実態すべて 0 件で完全な dead 機能。

選択肢 C: argparse / 引数 / 関連ロジック / 設計書記述すべて完全削除。

---

## 2. 削除対象（コード）

### `spec_grag/cli.py`

| 行 | 削除内容 |
|---|---|
| 75-78 | `core.add_argument("--use-cache", action="store_true", help="(deprecated) keep reusable section metadata cache even with --all")` を削除 |
| 361 | `_run_core_from_args` 内の `use_cache=args.use_cache,` 引き渡しを削除 |

### `spec_grag/core.py`

| 行 | 削除内容 |
|---|---|
| 59 | `run_spec_core` のシグネチャから `use_cache: bool = False,` を削除 |
| 164 | `_run_spec_core_unlocked` 呼出から `use_cache=use_cache,` を削除 |
| 201 | `_run_spec_core_unlocked` のシグネチャから `use_cache: bool = False,` を削除 |
| 275 周辺 | コメント `# `--all` (use_cache=False) clears the LLM-derived caches BEFORE the` を整理（`--all` 単独で cache clear する旨に書き換え、もしくは削除） |
| 284 | `if run_full and not use_cache:` を `if run_full:` に簡素化 |
| 385 | `rebuild_all=run_full and not use_cache,` を `rebuild_all=run_full,` に簡素化 |
| 727 | 同様の `rebuild_all=run_full and not use_cache,` を `rebuild_all=run_full,` に簡素化 |

---

## 3. 削除対象（外部設計書）

### `doc/EXTERNAL_DESIGN.ja.md`

| 行 | 削除内容 |
|---|---|
| 502 | `--rebuild` は `--all` を含意する。`--use-cache` は deprecated (挙動は無指定と同等)。 → 「`--rebuild` は `--all` を含意する。」のみ残す（後半の `--use-cache` 文を削除） |

---

## 4. test / template への影響

- **test 削除対象**: なし（`grep -rn "use_cache\|use-cache" tests/` で hit 0 件、監査時確認済み）
- **Agent CLI template への影響**: なし（`spec_grag/templates/.claude/commands/`, `.codex/skills/spec-grag/SKILL.md` で `--use-cache` 言及 0 件、監査時確認済み）

---

## 5. 完了条件

次を全て満たすこと:

1. **コード削除完了**: §2 の 9 箇所全てを削除
2. **外部設計書削除完了**: §3 の 1 箇所を削除
3. **残骸ゼロ確認**:
   ```bash
   git grep -n 'use_cache\|use-cache' spec_grag doc tests
   ```
   が 0 件であること（`.git/` や `doc/監査-CODEX/STEP5_FINDINGS_AND_REMEDIATION.ja.md` の F-3 記述は除外して 0 件、もし残るなら明示）
4. **pytest 通過**: `pytest -q` で全 test pass（none / fake profile、real-smoke / local-service は skip 許容）
5. **smoke check**: `python -m spec_grag --version` で正常起動

---

## 6. 3 種類のバイアス警戒（Step 5 §6.4 参照）

本作業中に次のバイアスを発動しないこと:

| バイアス | 注意点 |
|---|---|
| **残す引力** | 「念のため」「test 便利性」「後方互換性」を口実に `--use-cache` 関連経路を残さない。完全削除する |
| **消す引力** | 削除対象 (§2 / §3) の範囲外には触らない。他の dead code っぽいものを見つけても本 PR では削らない |
| **機能集約への引力** | CLI コードに「`--use-cache` は廃止された」のような deprecation warning メッセージをハードコードしない。CLI から完全に消す |

---

## 7. 作業ディレクトリ

**worktree path**: `/home/kazuki/public_html/spec-grag.wt-fix-use-cache`

作業前に必ず:

```bash
cd /home/kazuki/public_html/spec-grag.wt-fix-use-cache
pwd  # 確認
git branch --show-current  # fix-use-cache であること確認
```

main repo (`/home/kazuki/public_html/spec-grag`) では作業しないこと。

`.venv` symlink 問題に注意: worktree 内で test 実行する前に、`.venv/bin/python` が worktree のコードを指すか確認。必要なら `pip install -e .` を worktree で再実行する。

---

## 8. 完了報告フォーマット

作業完了時に次を提示:

1. **作業ディレクトリの確認**: `pwd` 出力と `git branch --show-current` 出力
2. **削除箇所の確認**: §2 / §3 の各項目について「削除完了」or「該当なし」を明示
3. **残骸ゼロの確認**: `git grep -n 'use_cache\|use-cache' spec_grag doc tests` の出力（0 件のはず、もし残る場合は理由）
4. **pytest 結果**: `pytest -q` の最後 20 行
5. **smoke check**: `python -m spec_grag --version` の出力
6. **diff 要約**: `git diff main --stat` の出力
7. **commit message 案**: 1-2 sentence で「なぜ」を書く
8. **3 種類のバイアス自己点検**: 「残す引力」「消す引力」「機能集約への引力」のいずれも発動していないことを 1 行ずつ確認

---

## 9. 中断時のルール

途中で中断する場合:

- 現状を worktree に commit せず stash か WIP commit で保存
- ファイル先頭に「⚠ 未完了: 中断箇所と理由」セクションを追加（成果物が文書の場合）
- 完了報告の代わりに「中断報告」として、どこまで完了したか / 何が残っているかを提示
- 事実水増し、削除省略、テスト省略は禁止

---

## 10. 監査者 Claude による完了確認後の処理

Codex の完了報告 → Claude 監査通過 → ユーザー最終確認 後:

1. worktree で `git commit -m "..."` (commit message は Codex 提案 + Claude 調整)
2. main に戻る: `cd /home/kazuki/public_html/spec-grag`
3. merge: `git merge fix-use-cache` (fast-forward or merge commit)
4. worktree 削除: `git worktree remove ../spec-grag.wt-fix-use-cache`
5. branch 削除: `git branch -D fix-use-cache`
6. Step 5 §4.1 短期ロードマップ表の F-3 行に「✅ 完了 YYYY-MM-DD, commit `<hash>`」を追加

---

## Codex に投げる起動 prompt (この下の triple-backtick の中身をそのままコピペ)

```
あなたは spec-grag リポジトリの修正作業者です。本タスクは PR 1: F-3 (`--use-cache` 完全削除) の実装です。

# 着手前の必読

次のファイルを最初から最後まで全文読んでから着手してください:

仕様書: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/PROMPTS/REMEDIATION/PR1_F3_use_cache.md
監査根拠: /home/kazuki/public_html/spec-grag/doc/監査-CODEX/STEP5_FINDINGS_AND_REMEDIATION.ja.md (§3.3, §8.1 F-3, §6.4)
外部設計書 (改訂対象): /home/kazuki/public_html/spec-grag/doc/EXTERNAL_DESIGN.ja.md (§7.1, §7.2)

# 作業ディレクトリ

cd /home/kazuki/public_html/spec-grag.wt-fix-use-cache

pwd で確認 (期待: /home/kazuki/public_html/spec-grag.wt-fix-use-cache)
git branch --show-current で確認 (期待: fix-use-cache)

# 作業

仕様書 §2 (削除対象コード 9 箇所) + §3 (削除対象設計書 1 箇所) を削除します。仕様書 §4 (test / template 影響なし) を踏まえ、test や template には触りません。

# 完了条件 (仕様書 §5)

- §2 / §3 全削除完了
- git grep -n 'use_cache\|use-cache' spec_grag doc tests が 0 件 (doc/監査-CODEX/STEP5_FINDINGS_AND_REMEDIATION.ja.md の F-3 記述は除外)
- pytest -q 通過
- python -m spec_grag --version 起動確認

# 3 種類のバイアス警戒 (仕様書 §6)

- 残す引力: `--use-cache` を「念のため」残さない
- 消す引力: 削除対象範囲外には触らない
- 機能集約への引力: CLI に deprecation メッセージをハードコードしない

# 完了報告 (仕様書 §8 フォーマット遵守)

作業完了時に仕様書 §8 の 8 項目を提示してください。

# 絶対に守ること

- 作業ディレクトリは /home/kazuki/public_html/spec-grag.wt-fix-use-cache のみ。main repo (/home/kazuki/public_html/spec-grag) では作業しない
- 上位ルール文書 (CLAUDE.md / AGENTS.md など) を作業判断根拠にしない (監査で確立した原則)
- pytest / smoke check が通らない場合、原因を仕様書 §9 に従って中断報告する。事実水増しせず正直に報告

# 中断時 (仕様書 §9)

途中で中断する場合は中断報告。事実水増し / 省略禁止。
```

---

## 補足（Codex に投げる文には含めない、ユーザー向けメモ）

- 本 PR は **PR 1** で、運用フロー確認の最小単位として選んだ
- 完了後、Phase 1 残り PR 2 (F-1) / PR 3 (F-7 + F-B) / PR 4 (F-A) を**並列展開**する判断材料になる
- 各 PR で同じ Codex prompt パターンを使う想定（範囲だけ差し替え）
- 完了報告 → Claude 監査（Step 5 §8.1 / §6.4 と照合） → ユーザー最終確認 → merge → worktree 削除 → Step 5 完了マーク
