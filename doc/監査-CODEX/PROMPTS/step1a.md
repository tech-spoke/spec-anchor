# Step 1-A 用 Codex prompt: 機械的インベントリ

本 prompt は spec-grag リポジトリの**機械的事実だけ**を抽出するための指示書である。説明文・解釈・評価・推測は一切書かない。後段 Step 1-B でフロー深掘り、Step 1-C で横断観点表化を行う。本 Step は素材集めに限定する。

成果物の置き先: `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`

---

## 1. 役割

あなたは grep / find / AST を用いてコードから機械的事実だけを抽出する作業者である。本 Step では**表と grep / find / AST の実行結果のみ**を残す。文章による説明、関数の責務記述、データフロー記述は禁止する。それらは後段 Step 1-B / 1-C で扱う。

---

## 2. 読んでよいファイル（allowlist）

- `spec_grag/` 配下の全 Python ファイル
- `spec_grag/templates/` 配下の全ファイル
- `tests/` 配下の全 Python ファイル
- `pyproject.toml` / `setup.py` / `setup.cfg`

これ以外は開かない、引用しない、ファイル名で参照しない。

---

## 3. 読まないファイル（denylist）

- `doc/` 配下の全ファイル（`doc/監査/STANDARD_GRAG_PATTERNS.ja.md` も含む。Step 3 で初めて使う）
- `doc/監査/` の既存資料（前回成果は無かったものとして扱う）
- `archive/` / `BAK/` 配下
- `.spec-grag/` 配下（generated runtime state）
- `CLAUDE.md` / `AGENTS.md` / `README.md`（agent 向け / 利用者向けドキュメント）
- `.venv/` / `node_modules/` / `.git/`

---

## 4. 禁則（書いてはいけないこと）

次は本書に書かない。書いた場合は Step 1-A の成果物として無効。

- 説明文（「〜している」「〜する」「〜のために使われる」「〜を担当する」等）を表セル以外の本文に書かない。表セル内に書く場合も、コードからの直接引用（関数名・docstring の literal・コメント引用）でなければ書かない
- 推測表現（「と思われる」「おそらく」「意図は～」）
- 評価表現（「適切」「妥当」「過剰」「不足」「冗長」）
- 改善案 / リファクタ案
- 業界標準 / RAG / GraphRAG 等の外部方式との比較
- データフロー記述（「A の出力が B に渡る」型）。これは Step 1-B で扱う
- 責務記述（「core.py は X を担当する」型）。これは Step 1-C で扱う
- file:line のない事実記述。本文・表セル全てに file:line を必須とする（見出し、表の列名、§0 の探索コマンド記録は除く）
- `tests/` から得た事実を S5 以外の節に混入させる。テスト期待値が実装仕様として混ざるのを防ぐため、本体側 (§1–§4) と test 側 (§5) を分離する
- 「全件」「全部」「全件網羅」と書く時に**実行した探索コマンドを併記しない**

---

## 5. 出力構成

成果物 `doc/監査-CODEX/STEP1A_INVENTORY.ja.md` を次の節構成で書く。各節は省略不可。

### §0. 監査範囲と探索コマンド宣言

- commit hash（`git rev-parse HEAD` を実行した結果）
- 本 Step で実行した探索コマンドの全件リスト（grep / find / ast / python の正確な引数とオプションをそのまま記録）
- 各コマンドの出力件数（参考値、後続節の表の件数と一致するべき）
- 読んだファイルの absolute path 一覧（allowlist 外を開いていないことの証跡）

### §1. ファイル一覧と公開シンボル

`spec_grag/` 配下の全 `.py` ファイルについて、次の表で記録する。

| file | LOC | 公開関数 (file:line, 引数シグネチャ literal) | 公開クラス (file:line) | dataclass / TypedDict (file:line) |

定義:
- 公開 = モジュール先頭で `def` / `class` 定義、`_` で始まらないシンボル
- 引数シグネチャは `def foo(a: int, b: str = "x") -> None:` のように literal で引用

節末に **本節で実行した探索コマンド** を記録する。例:
```
$ find spec_grag -type f -name "*.py" | sort
$ python -c "import ast; ..."
```

### §2. CLI コマンド一覧

argparse の `add_parser` / `add_subparsers` / `add_argument` から抽出する。

| コマンド名 | 定義 file:line | エントリー関数 file:line | 引数定義（literal 引用） | デフォルト値 (file:line) |

節末に探索コマンド記録（例: `grep -nE "add_(parser|argument|subparsers)" spec_grag/cli.py`）。

### §3. 設定キー一覧

config 関連 dataclass / TOML 読込から抽出する。

| section.key | dataclass / 型 (file:line) | 読込所在 (file:line) | デフォルト値 / 必須かどうか (file:line) |

`spec_grag/templates/.spec-grag/config.toml` のキーも全件含める（template リテラルとして引用）。

節末に探索コマンド記録。

### §4. リテラル候補一覧

artifact ファイル名、Qdrant collection 名、env var 名、状態ファイル名などの**文字列リテラル**を grep で抽出する。

| リテラル | 出現 file:line | 文脈（その行のコード literal 引用、解釈・説明なし） |

対象とする grep パターン（最低限、追加可）:
- `.json` を含む文字列リテラル（artifact / state file）
- `.lock` を含む文字列リテラル
- `.jsonl` を含む文字列リテラル
- `SPEC_GRAG_` を含む文字列リテラル（env var）
- `os.environ` 経由で参照されている key
- `collection` / `Collection` を含む文字列リテラル

節末に探索コマンド記録（全 grep パターンを書く）。

### §5. 外部接続キーワード grep 結果

次のキーワードについて、`spec_grag/` 配下の出現を全件記録する（`tests/` は §6 で別途）。

対象キーワード:
- `subprocess`
- `qdrant`
- `FlagEmbedding`
- `BGEM3`
- `open(`
- `write_text`
- `read_text`
- `Path(`
- `os.environ`
- `except`
- `fallback`
- `timeout`
- `retry`
- `lazy import` 候補: `importlib`
- LLM provider 名候補: `codex`, `claude`

| キーワード | 出現件数 | 出現 file:line 全リスト |

「出現件数」と「全リスト」の件数が一致することを自己点検する。一致しない場合はその理由を末尾に記録する。

節末に探索コマンド記録（各キーワードの grep コマンドをそのまま）。

### §6. tests/ 章（本体と分離）

`tests/` 配下のテストファイルについて次を記録する。**ここに書いた事実は §1–§5 に混入させない**。

| test file | import している spec_grag モジュール (file:line) | test 関数一覧 (file:line) |

節末に探索コマンド記録。

### §7. 不明 / 解釈不能事項

本 Step の grep / find / AST で**機械的に判定できなかった**項目を記録する。

ルール:
- 空でもよい
- 空の場合は次を記録する:
  - 探索範囲（実行した全 grep / find / AST コマンド）
  - 不明候補として検討したが不明扱いにしなかった箇所と、その理由
  - 空にした理由（例「機械的抽出範囲では全項目が件数一致した」）
- 水増し禁止。本物の不明点がない場合に無理に書かない

| 箇所 file:line | 機械的に判定できなかった事象 | 試した探索コマンド |

---

## 6. 良い例 / 悪い例

### 良い例 (1) — §1 ファイル一覧

```
| file | LOC | 公開関数 (file:line, sig) | 公開クラス | dataclass |
|---|---|---|---|---|
| spec_grag/core.py | 1920 | `run_spec_core(config_path: Path, ...) -> dict` (spec_grag/core.py:47) | `CoreContext` (spec_grag/core.py:120) | `SectionResult` (spec_grag/core.py:200) |
```

理由: file:line と引数シグネチャ literal が併記されている。説明文を含まない。

### 悪い例 (1) — §1

```
| file | 説明 |
|---|---|
| spec_grag/core.py | core パイプラインを担当する。LLM を呼んで section metadata を作る |
```

理由: 「担当する」「LLM を呼んで」は説明文・データフロー記述。本 Step では禁則。

### 良い例 (2) — §4 リテラル

```
| `"section_manifest.json"` | spec_grag/artifacts.py:193 | `path = self._state_dir / "section_manifest.json"` |
```

理由: リテラル、所在、文脈の literal 引用が揃っている。

### 悪い例 (2) — §4 リテラル

```
| section_manifest.json | artifacts.py | section の manifest を保存する重要なファイル |
```

理由: file:line が無く、「重要な」は評価。文脈が literal 引用ではなく説明文。

### 良い例 (3) — §5 外部接続キーワード

```
| `subprocess` | 4 件 | spec_grag/llm_provider.py:383, spec_grag/llm_provider.py:454, spec_grag/project_setup.py:204, spec_grag/project_setup.py:291 |

探索コマンド:
$ grep -nE "subprocess" spec_grag/**/*.py
```

理由: 件数と全 file:line が一致し、探索コマンドが記録されている。

### 悪い例 (3) — §5

```
| subprocess | 多数 | spec_grag 各所 |
```

理由: 「多数」「各所」は件数と所在の不明示。後段で追跡できない。

### 良い例 (4) — §7 不明事項

```
本節は空である。
探索範囲: 上記 §0 の探索コマンド全件。
不明候補として検討したが不明扱いにしなかった箇所: 
- `spec_grag/related_sections.py:1850` 付近の prompt template リテラル → §4 のリテラル表に literal 引用済みのため不明扱いにしない
空にした理由: 機械的抽出範囲では全項目が件数一致した。
```

理由: 空であることの根拠が示されている。

### 悪い例 (4) — §7

```
特に不明点なし
```

理由: 探索範囲、検討した候補が記録されていない。または

```
| 全体的に複雑な箇所が多い | コードコメント不足 |
```

理由: 箇所が file:line で特定されておらず、機械的判定できなかった事象が書かれていない（「複雑」は評価表現）。

---

## 7. 「全件」と書く時のルール

次のいずれかを書く時は、**同じ節内に実行した探索コマンドを併記する**。併記が無い場合は禁則違反。

- 「全件」「全部」「全件網羅」「全リスト」「すべての」「全ての」

例:
```
spec_grag/ 配下の全 .py ファイルを §1 に記録した。

探索コマンド:
$ find spec_grag -type f -name "*.py" | sort
```

---

## 8. 作業手順

1. `git rev-parse HEAD` で commit hash を取得し §0 に記録
2. `find spec_grag tests -type f -name "*.py" | sort` で allowlist 対象を確定
3. §1 → §2 → §3 → §4 → §5 → §6 の順で表を埋める。各節の最後に探索コマンドを記録する
4. §5 で件数と所在リストの件数が一致することを自己点検する
5. §7 を書く。本物の不明点があればそれを、無ければ空である根拠を書く
6. 最終報告（§9 参照）を本文末に書く

---

## 9. 最終報告（本文末に必須）

本文の最後に次の節を作る。

```markdown
## 最終報告

- 作成したファイル: doc/監査-CODEX/STEP1A_INVENTORY.ja.md
- 実行したコマンド全件: <§0 と各節末の探索コマンドが本セクションでも追跡可能なよう、合計件数と一覧の所在を記す>
- 読んだファイル数: spec_grag/ 配下 N ファイル、tests/ 配下 M ファイル、設定 K ファイル
- 読まなかった allowlist 内ファイル数: 0 件（または N 件と理由）
- 未完了の章: なし（または列挙）
- file:line なしで残っている事実文の有無: なし（または箇所列挙）
- denylist を開いていないことの確認方法: <例: grep のターゲット glob を allowlist のみに限定した。全コマンド引数を §0 に記録した>
- §7（不明事項）の状態: 空 / N 件
```

---

## 10. 完了条件

次を全て満たしたら完了とする。

- allowlist 外のファイルを開いていない
- 禁則表現（説明文、推測、評価、改善案、データフロー記述、責務記述）を含まない
- 全ての事実記述（表セル含む）に file:line が付いている。例外は見出し、表の列名、§0 の探索コマンド記録、§9 最終報告内の集計値のみ
- §1 〜 §6 の各節末に探索コマンドが記録されている
- §5 で件数と所在リストの件数が一致する（または不一致理由が記録されている）
- §7 が空の場合、空である根拠（探索範囲・検討した候補・空にした理由）が記録されている
- §9 最終報告が記入されている

---

## 11. 注意

- 既存 `doc/監査/INTERNAL_SPEC_FROM_CODE.ja.md` は無かったものとして扱う
- 既存 `doc/監査/IMPLEMENTATION_*.md` は修正中のため参照しない
- 不明点を埋めるために `doc/` を開くのは禁則違反。不明点は §7 に書いて残す
- 本 Step は機械的事実のみ。フロー深掘り（CLI コマンドが何を入力に何を出力するか）は Step 1-B、横断観点表（外部接続点の条件・fallback の発動条件）は Step 1-C で扱う。本 Step で先取りして書かない
