# P3 セッション引継ぎ書: §7 /spec-core E2E 検証

最終更新: 2026-05-22 (P2 完了時点)
作成セッション: P0 / P1 / P2 担当

> **追記 (2026-05-22 P3 セッション完了後)**:
> 本書は P3 着手前の状態を記述している。P3 は **hybrid_verified (real Qdrant + real BGE-M3 + fake LLM)** までを完了させたが、**real_smoke_verified / production_e2e_verified には到達していない**。本書 §4 / §10 で言及している "real-smoke 必須" は **未実施** である。
> 検証レベルの正本は `test_plan.ja.md` §4.2.1 / §4.2.2 / §4.2.3 を参照。real Codex / Claude 経由の `/spec-core` 経路は **P7 (横串 real production E2E phase)** で踏む計画に再定義した (`test_plan.ja.md` §4.2.4)。

このセッションでは **§7 (`/spec-core`) の 118 件の検証単位** を E2E テストで `[ ]` → `✅` 化することが目標です。前セッション (P0 / P1 / P2) の成果と前提を本書で引き継ぐ。

## 1. 最初に読むもの

順番厳守。

1. **`doc/EXTERNAL_DESIGN.ja.md` 凡例 + §7** (本セッションの主役)
2. **`doc/e2eテスト/test_plan.ja.md`** (全体方針、特に §1.1.1 real-smoke 優先 / §1.1.2 テスト環境 / §1.1.3 破壊操作の許容範囲 / §4.2 進捗表 / §7 エビデンス設計)
3. **`CLAUDE.md`** (プロジェクト共通ルール、特に ルール 8 / 10 / 11 / 12)
4. **本書 (handoff-P3.md)**

## 2. 現状サマリ

- ✅ 累計 165 / [ ] 残 ~288
- 完了 Phase: P0 (harness), P1 §5 (15), P1 §10 (69), P2 §6 (37)
- ✅ 化済の §11 既存: 44 (前セッション)
- 直近 commit: `b66a3e1` (進捗表追加)

git log で `7397617..b66a3e1` を確認すれば本セッション以前の流れが見える。

## 3. P3 のスコープ: §7 内 118 件の構成

`doc/EXTERNAL_DESIGN.ja.md` §7 (line 553 付近〜940 付近) の `[ ]` 全てが対象。内訳:

| 部分 | spec doc 位置 | 件数概算 | 性質 |
|---|---|---:|---|
| §7.1 目的 / mode 説明 + flag 相互作用表 + provider 失敗 | L560-625 周辺 | 5 | structural / fake |
| §7.2 入力表 + CLI フラグ表 | L640-700 周辺 | 10 | structural / fake |
| §7.3 動作 step (3 mode 分の手順) | L740-790 周辺 | 23 step + 1 trace 監査 | **real-smoke 必須** (実 /spec-core 実行) |
| §7.4 CoreResult フィールド (17) | L820-840 周辺 | 17 | real-smoke 推奨 (fake でも構造は確認可) |
| §7.4 retrieval_index_status enum (5) + 動作 4 詳細 | L850-880 周辺 | 9 | real-smoke (各 status を実際に発生させて確認) |
| §7.4 related_sections_status enum (4) + 動作詳細 | L890-910 周辺 | 5+ | real-smoke |
| §7.4 Chapter Key Anchor / potential_conflicts | L920-930 周辺 | 数件 | real-smoke |
| §7.4 Conflict Review Item / decision payload / decision enum (7) | L930+ | 約 20 | fake 中心 (構造検証) |

正確な件数は P3 着手時に `awk '/^## 7\./,/^## 8\./' doc/EXTERNAL_DESIGN.ja.md | grep -c "\[ \]"` で確認。

## 4. real-smoke fixture 設計 (P3 の核心)

### 4.1 設計方針

118 件の多くは 1 回の `/spec-core` 実行結果を様々な観点から検証する。よって **session-scoped fixture で `/spec-core` を 1 度だけ実行し、複数 test が結果を参照する** 構造にする。

### 4.2 fixture スケッチ

`tests/conftest.py` または `tests/test_spec_core_acceptance.py` 冒頭に追加 (新規 fixture):

```python
@pytest.fixture(scope="session")
def real_spec_core_project(tmp_path_factory):
    """Session-scoped real-smoke /spec-core run against a fresh project.

    Drops a couple of small Source Specs into a fresh project_root,
    invokes `spec-anchor core` with real Codex/Claude/Qdrant/BGE-M3,
    and returns a dict with paths + parsed JSON + artifact contents.
    Subsequent tests inspect this snapshot without re-invoking
    /spec-core, keeping total LLM cost bounded.
    """
    project = tmp_path_factory.mktemp("real_core")
    # setup-project skeleton
    subprocess.run(
        [".venv/bin/spec-anchor-setup-project", "--target", str(project), "--agent", "both"],
        check=True, capture_output=True,
    )
    # Add minimal Source Specs (multi-section for chapter anchor coverage)
    (project / "docs" / "spec").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "spec" / "alpha.md").write_text(
        "# Alpha Spec\n\n## Overview\n\nA brief.\n\n## Authentication\n\nUse Bearer.\n",
        encoding="utf-8",
    )
    (project / "docs" / "spec" / "beta.md").write_text(
        "# Beta Spec\n\n## Background\n\nb.\n\n## Conflict candidate\n\nA conflicts with B.\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.pop("SPEC_ANCHOR_FAKE_LLM", None)
    env.pop("SPEC_ANCHOR_FAKE_RETRIEVAL", None)
    proc = subprocess.run(
        [".venv/bin/spec-anchor", "core"],
        cwd=project, env=env, capture_output=True, text=True, timeout=900,
    )
    core_result = json.loads(proc.stdout)

    snapshot = {
        "project": project,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "core_result": core_result,
        "core_progress": json.loads(
            (project / ".spec-anchor/state/core_progress.json").read_text()
        ) if (project / ".spec-anchor/state/core_progress.json").is_file() else None,
        "freshness": json.loads(
            (project / ".spec-anchor/state/freshness.json").read_text()
        ),
        "chapter_anchors": json.loads(
            (project / ".spec-anchor/context/chapter_anchors.json").read_text()
        ) if (project / ".spec-anchor/context/chapter_anchors.json").is_file() else None,
        "section_manifest": json.loads(
            (project / ".spec-anchor/state/section_manifest.json").read_text()
        ),
        # ... add other artifacts as needed
    }
    yield snapshot
```

Variants needed:
- `real_spec_core_project` (no flag, incremental)
- `real_spec_core_all` (--all)
- `real_spec_core_rebuild` (--rebuild)
- `real_spec_core_verify_index` (--verify-index)
- `real_spec_core_pending_conflict` (with seeded pending conflict)
- `real_spec_core_failure_*` (Qdrant down / LLM failure scenarios via env override)

各 fixture は session-scoped で `/spec-core` 1 回呼ぶだけ。tests はその結果を参照。

### 4.3 LLM 実行コスト見積り

- 小さな Source Specs (2 ファイル、4 section) で /spec-core 1 回 ≈ 1-3 分 (section_metadata × 4 + related_sections + conflict_review + chapter_key_anchor)
- 必要な fixture variant が 5-7 個 → 計 10-20 分の LLM 時間
- LLM コスト: ~ small (test 用は短い prompt)

### 4.4 fixture 失敗時の挙動

- Codex / Claude / Qdrant がダウンしている場合は `@pytest.mark.external` + `pytest.skip()`
- timeout は generous に (900s 上限)
- 失敗 fixture から派生する全 test は automatically xfail にする (`pytest.fail` ではなく `pytest.skip`)

## 5. fake-mode で完結する部分

§7 全 118 件のうち、real-smoke を必要としない約 30-40 件:

- §7.1 mode 説明 (3 mode × 1 表) — fake で実行可
- §7.2 入力 + CLI フラグ表 — fake (引数 parsing 確認)
- §7.4 Conflict Review Item 構造 + decision payload + decision enum (7) — fake で artifact 構造確認

これらは先に fake で倒すと P3 進捗が見えやすくなる。

## 6. test ファイル設計案

新規 1 ファイル: `tests/test_spec_core_acceptance.py`

```text
tests/test_spec_core_acceptance.py
  - 冒頭: real_spec_core_* fixtures (session-scoped, 5-7 variants)
  - §7.1 / §7.2 / §7.4 構造 / decision 関連: fake-mode tests (~40 件)
  - §7.3 動作 step / §7.4 enum / §7.4 status 詳細: real_spec_core_* fixture
    を消費する parametrized tests (~70 件)
  - 末尾: trace 監査 1 件 (Agent CLI ではなく CLI 自身の core_progress.json
    stages を辿る方式)
```

または、§7.x ごとに分割しても可。1 ファイルで管理する方が evidence_map.jsonl と
spec_line の対応が追跡しやすい。

## 7. SPEC_REF marker の使い方

§10 config keys / §6 setup commands と同じく、parametrized test で per-row marker を使う:

```python
@pytest.mark.parametrize(
    "spec_line, field_name, expected_type",
    [
        pytest.param(
            830, "mode", str,
            marks=[pytest.mark.spec_ref("§7.4", 830, profile="real-smoke", method="入出力比較")],
            id=f"L830-mode",
        ),
        # ... 17 CoreResult fields
    ],
)
def test_core_result_field_exists(real_spec_core_project, spec_line, field_name, expected_type):
    """SPEC_REF はマーカー側、PROFILE/METHOD もマーカー側 (per-row)."""
    assert field_name in real_spec_core_project["core_result"]
```

evidence_map.jsonl にはマーカー値が記録される (P1 §10 と同じ仕組み)。

## 8. 進捗管理

P3 着手時:
1. `doc/e2eテスト/test_plan.ja.md` §4.2 の P3 行を `STATUS: todo → in-progress` に更新
2. test_spec_core_acceptance.py を実装
3. 各 [ ] → ✅ flip 時に test_plan §4.2 P3 行の件数を更新
4. P3 完了時に `STATUS: in-progress → done` + commit hash を記入

evidence folder: `doc/e2eテスト/evidence/P3-section-7-<分割名>/` (例: `P3-section-7-structural`, `P3-section-7-real`)

## 9. 既知の落とし穴 / 注意

### 9.1 spec ↔ 実装の乖離チェック (lesson from L413)

[ ] を ✅ にする前に、spec doc の文言が **実装と一致しているか** を必ず確認:
- spec doc に書かれた CLI flag / subcommand / artifact field 名が実装に存在するか
- 不一致を見つけたら、spec doc を実態に合わせて修正してから ✅ 化

P1 §5.3 L413 で `spec-anchor inject` / `--constraints` 不在の問題があり、commit `9e939f6` で修正済。

### 9.2 conftest.py の autouse fake_providers fixture

`tests/conftest.py` に次の autouse fixture がある:

```python
monkeypatch.setenv("SPEC_ANCHOR_FAKE_LLM", "1")
monkeypatch.setenv("SPEC_ANCHOR_FAKE_RETRIEVAL", "1")
```

real-smoke fixture では **これを delete** してから subprocess を起動する。本セッションでは
`env.pop("SPEC_ANCHOR_FAKE_LLM", None)` で対処している (例: `test_setup_commands_acceptance.py::_setup_system_real`).

### 9.3 `.venv/bin/pytest` の shebang が壊れている

`.venv/bin/pytest` は `/home/kazuki/public_html/spec-grag/.venv/bin/python` を指していて
動かない。**`.venv/bin/python -m pytest` を使う**。

### 9.4 `.spec-anchor/` stash 機構

`tests/conftest.py` は session 開始時に `<repo>/.spec-anchor/` を stash 退避し、session 終了時に
復元する。real-smoke fixture が tmp_path で完結する限り影響なし。

### 9.5 既存 .spec-anchor / Qdrant collection の扱い

`doc/e2eテスト/test_plan.ja.md` §1.1.3 により、テスト中は repo root の `.spec-anchor/` 削除や
Qdrant collection `spec_anchor_section` の drop / recreate を許容する。tmp_path test では
基本不要だが、--rebuild 系 test は本物の Qdrant collection を触ることになる。

### 9.6 既存 pre-existing 変更ファイル

git status に出る以下は **このセッションの担当外**:
- `spec_anchor/cli.py`
- `spec_anchor/core.py`
- `spec_anchor/inject.py`
- `spec_anchor/project_setup.py`
- `spec_anchor/realign.py`
- `spec_anchor/templates/.claude/commands/spec-*.md`
- `tests/test_setup_scripts.py`
- `uv.lock`
- 未追跡: `doc/監査-CODEX/e2e-evidence-2026-05-21/`、`メモ`

P3 commit 時は **自分の変更だけを `git add` で staging** する。これら pre-existing 変更を
誤って取り込まないように注意。

### 9.7 evidence_map.jsonl は append-only

同じ `SPEC_ANCHOR_E2E_EVIDENCE_DATE` 配下で複数回 pytest を回すと entries が累積する。
最新 entry が authoritative (cf. P1-dev folder の例)。P3 では:
- 開発中: `SPEC_ANCHOR_E2E_EVIDENCE_DATE=P3-dev` で気軽に試す
- 最終確定: `SPEC_ANCHOR_E2E_EVIDENCE_DATE=P3-section-7-final` で clean run

## 10. 着手手順 (推奨)

1. test_plan §4.2 を更新: `P3` 行を `STATUS: in-progress` に
2. real-smoke fixture を `test_spec_core_acceptance.py` 冒頭に実装
3. 簡単な動作確認: `real_spec_core_project` fixture を使う 1 test を書いて `pytest -m external` で実行 → 結果確認
4. fake-mode test (§7.1 / §7.2 / Conflict 構造 / decision enum) を先に倒す (~40 件)
5. real-smoke fixture を多数 test で消費 (~70 件)
6. §7 ✅ 集計を spec doc で確認、test_plan §4.2 P3 行を更新
7. commit: `test+docs: P3 §7 (/spec-core) verified — N checkboxes → ✅`

## 11. ヘルパー: P3 着手時のサニティ確認コマンド

```bash
# 1. 現在の §7 [ ] 件数
awk '/^## 7\./,/^## 8\./' doc/EXTERNAL_DESIGN.ja.md | grep -c "\[ \]"

# 2. 環境確認
.venv/bin/python -m pytest --version
.venv/bin/spec-anchor-setup-system --check-only | grep '"status"'
which codex claude
curl -s http://localhost:6333/collections | python3 -m json.tool

# 3. 既存 test が壊れていないこと
.venv/bin/python -m pytest --skip-external -q | tail -3

# 4. evidence folder の状態
ls doc/e2eテスト/evidence/
```

## 12. 終わったあと

P3 完了時:
1. test_plan §4.2 P3 行: `STATUS: done`, 件数 / commit hash 入力
2. 累計 ✅ 件数を更新 (`P3 完了時点で ✅ XXX / [ ] YYY`)
3. P3a / P4 着手のための引継ぎがあれば `handoff-P3a.md` を作成

P3 完走目安: 1-2 時間。fixture 設計を最初に固めれば 118 件は数珠つなぎで倒せる。

---

**次セッション開始時に何をすべきか**

```
1. doc/EXTERNAL_DESIGN.ja.md §7 を読む
2. doc/e2eテスト/test_plan.ja.md を読む (特に §4.2 進捗表)
3. doc/e2eテスト/handoff-P3.md (本書) を読む
4. §11「ヘルパー」のサニティ確認コマンドを順に実行
5. real-smoke fixture を実装して試走
6. P3 着手
```
