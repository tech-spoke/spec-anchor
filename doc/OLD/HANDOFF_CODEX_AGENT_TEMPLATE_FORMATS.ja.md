# Codex への作業申し送り: Agent 別 入口形式（command / skill）の不整合修正

> 位置づけ: 一時的な作業指示書。受領した修正が完了し、G-19 / T-A01 / T-A02 が `[x]` になり、`doc/IMPLEMENTATION_PLAN.ja.md §6.1 CA-16` が「対応済み」になった時点で、本書は archive へ退避する。

## 1. 目的

`spec-grag-setup-project` が Codex 環境向けに出力している `<project>/.codex/commands/spec-*.md` は、Codex CLI の公式仕様で認識されないパスである。Codex CLI の入口は `<install_path>/skills/<name>/SKILL.md` 形式の skill である。本書は、Codex 用 入口を skill 形式に切り替え、Claude Code 用は command 形式のまま、Agent CLI ごとに非対称配置する修正を Codex に申し送る。

修正後は、`spec-grag-setup-project` の出力が以下のとおりになる。

| Agent 環境 | 入口形式 | 配置先 |
|---|---|---|
| Claude Code / Claude CLI | command 形式 | `<project>/.claude/commands/spec-{core,inject,realign}.md` |
| Codex CLI（user 既定） | skill 形式 | `~/.codex/skills/spec-grag/SKILL.md` |
| Codex CLI（project ローカル） | skill 形式 | `<project>/.codex/skills/spec-grag/SKILL.md`（`--codex-install project` 指定時のみ） |

`<project>/.codex/commands/` は **どの組合せでも生成しない**。

## 2. 背景（なぜ修正が必要か）

- Claude Code の slash command は `.claude/commands/<name>.md` を公式仕様として認識する（既存仕様、変更不要）
- Codex CLI 0.125.0 は `~/.codex/skills/<name>/SKILL.md` を skill として認識する。`~/.codex/commands/` は標準パスに存在しない（実環境で確認済み）
- 既存実装は Codex 用 template を `templates/.codex/commands/` に配置し、`spec-grag-setup-project --agent codex` で `<project>/.codex/commands/spec-*.md` を出力していた。これは Codex CLI から認識されない
- 既存テスト T-S01 / T-C01 は「ファイルが置かれたか」だけを spec-grag 自身で verify しており、Agent CLI からの実認識を確認していなかったため、不整合が CI で検出されなかった

## 3. 守るべき外部契約と運用ルール

**`doc/CLAUDE.md` ルール**:

- ルール 1: 土台がない状態で設計を議論しない。Codex skill 仕様は `~/.codex/skills/.system/skill-creator/SKILL.md` を一次資料として参照し、推測で frontmatter フィールドを増やさない
- ルール 2: 仕様書には決定内容と TODO のみを書く。実装メモは外部設計書に混入させない
- ルール 7: 実装完了ガード。fake provider 通過だけで完了報告しない。G-19 / T-A01 / T-A02 の Agent CLI 実認識を確認するまで「実装完了」と報告しない

**`doc/EXTERNAL_DESIGN.ja.md` の改訂後の決定事項**:

- §5.1: Agent 環境ごとに入口形式を固定（Claude Code = command、Codex = skill）。「環境が選ぶ」の解釈は撤回済み
- §5.2.2: `spec-grag-setup-project` のオプションに `--codex-install user|project` を追加し、user (`~/.codex/`) を既定とする
- §5.2.2: 配置例は Agent 別非対称（旧 §10.2 を §5.2.2 Project Setup Script に統合）
- §11 エラー契約: `--codex-install user` で既存 `~/.codex/skills/spec-grag/` を上書きする場合は `--force` 必須

**`doc/TEST_SPEC.ja.md` の改訂後の決定事項**:

- 新規 Gate **G-19 Agent CLI 認識検証** と必須テスト **T-A01 / T-A02**
- 新規 provider mode **`agent-cli-smoke`**（`SPEC_GRAG_AGENT_CLI_SMOKE=1` で opt-in）
- T-S01 / T-S02 / T-C01 を Agent 別非対称配置の検証に書き換え

## 4. 修正範囲

### 4.1 Codex 用 skill template の新設

**新規作成**: `spec_grag/templates/.codex/skills/spec-grag/SKILL.md`

仕様（Codex skill 公式仕様 `~/.codex/skills/.system/skill-creator/SKILL.md` に従う）:

- frontmatter（必須）
  - `name: spec-grag`
  - `description: ...`（Codex CLI が skill 起動を判断する説明文。SPEC-grag が何をするか、いつ起動すべきかを明示）
- frontmatter（任意）
  - `metadata.short-description: ...`（UI / list 表示用の短い説明）
- 本文（Markdown）
  - SPEC-grag CLI の呼び出し手順（`spec-grag core` / `spec-grag inject` / `spec-grag realign`）
  - freshness gate を最初に確認、status が `fresh` でなければ停止
  - pending conflict が残っているときは通常制約生成へ進まない
  - Section Summary / Search Keys / Related Sections / Chapter Key Anchor を最終根拠にしない
  - Purpose / Core Concept は人間更新対象、自動更新しない
  - 既存の `spec_grag/templates/.claude/commands/spec-{core,inject,realign}.md` の本文を統合・要約して 1 ファイルにまとめる

参考: `~/.codex/skills/code/SKILL.md`、`~/.codex/skills/.system/skill-creator/SKILL.md`

### 4.2 旧 Codex command template の撤去

**削除**:

- `spec_grag/templates/.codex/commands/spec-core.md`
- `spec_grag/templates/.codex/commands/spec-inject.md`
- `spec_grag/templates/.codex/commands/spec-realign.md`
- `spec_grag/templates/.codex/commands/`（空になったディレクトリも削除）

### 4.3 `spec-grag-setup-project` の経路書き換え

対象: [spec_grag/cli.py](spec_grag/cli.py) と [spec_grag/project_setup.py](spec_grag/project_setup.py)

- `--codex-install user|project` を `build_setup_project_parser` に追加。既定: `user`
- `setup_project(...)` のシグネチャに `codex_install: str = "user"` を追加
- `_project_file_entries(agent, *, init_core_files, codex_install)` を以下のように非対称化
  - `agent in ("claude", "both")` → `<project>/.claude/commands/spec-{core,inject,realign}.md`
  - `agent in ("codex", "both")` and `codex_install == "user"` → `~/.codex/skills/spec-grag/SKILL.md`
  - `agent in ("codex", "both")` and `codex_install == "project"` → `<project>/.codex/skills/spec-grag/SKILL.md`
  - **どの組合せでも `<project>/.codex/commands/` には書かない**
- `--codex-install user` で既存 `~/.codex/skills/spec-grag/` がある場合、`--force` なしでは status=`conflict`、`--force` 指定時のみ更新
- `--dry-run` の出力には `<install_path>` を明示
- `--no-init-core-files`、`--target` 不在、既存ファイル検出、`--force` 等の従来挙動は維持

### 4.4 `pyproject.toml` package-data の更新

```toml
[tool.setuptools.package-data]
spec_grag = [
  "templates/.claude/commands/*.md",
  "templates/.codex/skills/spec-grag/*.md",
  "templates/.spec-grag/config.toml",
  "templates/.spec-grag/.gitignore",
]
```

`templates/.codex/commands/*.md` の行は撤去する。

### 4.5 `spec-grag-setup-system` の templates 確認に skill 追加

対象: [spec_grag/project_setup.py](spec_grag/project_setup.py) の `_check_packaged_templates` 等

- 確認対象に `templates/.codex/skills/spec-grag/SKILL.md` を追加
- `templates/.codex/commands/*.md` の確認は撤去
- Agent CLI 認識性 diagnostics を追加
  - `which codex` で Codex CLI の存在確認、見つかれば `codex --version` を取得
  - `which claude` で Claude Code CLI の存在確認、見つかれば `claude --version` を取得
  - 認識性の補足情報（user install 想定 path の存在、対応 version 範囲の note）を `diagnostics` に出す
  - 実認識自体の verify は test (T-A01) で行うため、setup-system は warning レベルに留める

### 4.6 tests の更新

対象: [tests/test_setup_scripts.py](tests/test_setup_scripts.py)、新規 `tests/test_agent_cli_smoke.py`

- T-S01 を改訂版（17 行）に書き換え（既存の 13 行 → Agent 別非対称配置 17 行）
- T-S02 #8 / #9 を改訂版に書き換え
- T-C01 を改訂版に書き換え（Claude Code command frontmatter / Codex skill frontmatter / 共通ルール の 3 ブロック構成、計 11 行）
- Codex 用 command 形式 (`<project>/.codex/commands/`) がどの組合せでも作られないことを assert する test を追加
- T-A01 / T-A02 を `tests/test_agent_cli_smoke.py` に新規実装。`SPEC_GRAG_AGENT_CLI_SMOKE` 未設定なら skip、Codex CLI / Claude Code CLI 未 install なら個別 skip
- T-A02 では `テスト用ドキュメント/` を temp project にコピーして Source Specs として使う

### 4.7 README の更新

- Codex 環境のセットアップ手順に skill 形式と `--codex-install user|project` を明記
- 既存の `.codex/commands/` 言及があれば skill 形式に置き換える
- 「user install で `~/.codex/skills/spec-grag/` を更新するときは `--force` 必須」を runbook に追記

## 5. 実装ステップ（推奨順）

1. **テスト用ドキュメントの fixture 化準備**: `テスト用ドキュメント/` を Source Specs として temp project にコピーする helper を `tests/conftest.py` または `tests/test_agent_cli_smoke.py` に書く
2. **新 SKILL.md の作成**: §4.1 の skill template を Claude Code template の本文をベースに統合
3. **旧 command template の撤去**: §4.2
4. **`pyproject.toml` の package-data 更新**: §4.4。これを先に行うと、開発中の install で skill が package data に含まれる
5. **`project_setup.py` / `cli.py` の経路書き換え**: §4.3
6. **`spec-grag-setup-system` の改訂**: §4.5
7. **既存 tests の改訂**: §4.6 の T-S01 / T-S02 / T-C01
8. **新規 tests の追加**: §4.6 の T-A01 / T-A02
9. **README 更新**: §4.7
10. **default profile (`none/fake`) のフルスイート確認**: 254 → 新規 test 数増 で全 passing
11. **agent-cli-smoke profile での実認識確認**: §6 検証手順
12. **`doc/IMPLEMENTATION_PLAN.ja.md` §5.15 / §5.19 / §6.1 CA-16 の `[ ]` を `[x]` に更新**
13. **`doc/TEST_SPEC.ja.md` G-19 / T-A01 / T-A02 / T-S01 / T-S02 / T-C01 の `[ ]` を `[x]` に更新**

## 6. 検証手順

### 6.1 default profile (`none/fake`)

```
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q
```

期待: T-S01 / T-S02 / T-C01 を含む既存 + 新規 test がすべて passing。`agent-cli-smoke` 系の新規 test は `SPEC_GRAG_AGENT_CLI_SMOKE` 未設定で skip。

### 6.2 agent-cli-smoke profile（実 Codex CLI / 実 Claude Code CLI）

前提:

- Codex CLI が install 済みかつ subscription 認証済み（`codex --version` / `~/.codex/auth.json` で確認）
- Claude Code CLI が install 済みかつ認証済み
- local Qdrant が起動済み（T-A02 が retrieval 一巡を含むため）。project config の `[vector_store].url` が実 Qdrant URL を指すこと。`SPEC_GRAG_QDRANT_URL=http://localhost:6333` は test 差し替え用にだけ使う
- FlagEmbedding BGE-M3 が利用可能

実行:

```
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" \
  SPEC_GRAG_AGENT_CLI_SMOKE=1 \
  SPEC_GRAG_LOCAL_SERVICE=1 \
  .venv/bin/python -m pytest -q tests/test_agent_cli_smoke.py
```

期待:

- T-A01: `~/.codex/skills/spec-grag/SKILL.md` が Codex CLI で認識される。`<project>/.claude/commands/spec-*.md` が Claude Code CLI で認識される
- T-A02: `テスト用ドキュメント/` を Source Specs として、Claude Code / Codex 両 CLI で `setup -> core -> inject -> realign -> watch` 一巡が完走

### 6.3 実運用 setup の手動確認（推奨）

`テスト用ドキュメント/` を実 setup target に使う手順を実機で確認:

```
TMP_PROJECT=$(mktemp -d -t spec-grag-real-handoff-XXXX)
echo "TARGET=$TMP_PROJECT"

# Source Specs としてテスト用ドキュメントをコピー
mkdir -p "$TMP_PROJECT/docs/spec"
cp テスト用ドキュメント/*.md "$TMP_PROJECT/docs/spec/"

# Project setup（Claude command + Codex skill project local）
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" \
  .venv/bin/spec-grag-setup-project \
    --target "$TMP_PROJECT" \
    --agent both \
    --codex-install project

# 配置確認
find "$TMP_PROJECT/.claude" "$TMP_PROJECT/.codex" -type f

# /spec-core --all を CLI 経由で実行
cd "$TMP_PROJECT"
PATH=".../venv/bin:$PATH" \
  spec-grag core --all

# 実 Codex CLI を起動して、skill 認識を確認
codex
# プロンプトで: 「spec-grag skill を呼び出して /spec-core を実行」相当を試す

# 実 Claude Code CLI を起動して、command 認識を確認
claude
# プロンプトで: /spec-core
```

確認結果は T-A02 の実行証跡として `doc/IMPLEMENTATION_PLAN.ja.md §5.19` に記録する。

## 7. 完了条件

- 上記 §4 の修正がすべてマージされている
- `default profile` で全 test passing（pending_conflict 系の決定論性は維持）
- `agent-cli-smoke` opt-in 環境で T-A01 / T-A02 passing、または skip 理由が明確
- `doc/IMPLEMENTATION_PLAN.ja.md` §5.15 / §5.19 / §6 cross-cutting / §6.1 CA-16 / §7 が `[x]` に更新済み
- `doc/TEST_SPEC.ja.md` G-19 / T-A01 / T-A02 / T-S01 / T-S02 / T-C01 が `[x]` に更新済み
- `~/.codex/skills/spec-grag/SKILL.md`（user install 経路）と `<project>/.codex/skills/spec-grag/SKILL.md`（project local 経路）の両方が、`spec-grag-setup-project` の出力として確認できる
- `<project>/.codex/commands/` が出力されないことを test と実走の両方で確認できる

## 8. Human 判断要否

- 外部契約の改訂（Agent 別形式の固定、`--codex-install` 追加）は本書の作成時点でユーザー承認済み。Codex は外部契約をさらに変える場合のみ Human 判断を求めて停止する
- `<project>/.codex/skills/<name>/SKILL.md` を Codex CLI が認識する version 範囲が確定しない場合の挙動（user フォールバック / warning / 失敗）は、`--codex-install project` 採用時の実検証結果を踏まえて確定する。確定方針が外部契約の意味を変える場合は Human 判断を求める
- skill SKILL.md 本文の責務記述が、外部設計の責務境界（人間 / Agent / CLI）からズレた場合は Human 判断を求める
- pending Conflict Review Item / Purpose / Core Concept 関連の実装変更は本書の対象外

## 9. 参考資料

- `doc/EXTERNAL_DESIGN.ja.md` §5.1 / §5.2.1 / §5.2.2 / §11
- `doc/TEST_SPEC.ja.md` §0.2 / §0.3 / T-S01 / T-S02 / T-C01 / T-A01 / T-A02 / §9 / §10
- `doc/IMPLEMENTATION_PLAN.ja.md` §5.15 / §5.19 / §6 / §6.1 (CA-16) / §7
- `~/.codex/skills/.system/skill-creator/SKILL.md`（Codex skill 公式仕様の一次資料）
- `~/.codex/skills/code/SKILL.md`（既存 user-installed skill の実例）
- `テスト用ドキュメント/`（Source Specs として使う fixture）
