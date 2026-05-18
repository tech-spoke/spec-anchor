# Step 1-B 用 Codex prompt: 主要 CLI フローの深掘り

本 prompt は spec-grag の主要 CLI コマンドについて、入口から出口までの**ユースケース完走チェーン**を追跡する。Step 1-A の機械的インベントリを起点に、各 CLI が「何を入力に、何の API を呼び、何を出力するか」を行レベルで明示する。後段 Step 1-C で横断観点表化、Step 2 で方式仕様書再構成、Step 3 で業界標準差分、Step 4 で外部設計書整合チェックを行う。

成果物の置き先: `doc/監査-CODEX/STEP1B_FLOWS.ja.md`

---

## 1. 役割

あなたは Step 1-A の機械的インベントリを起点に、主要 CLI のフローを深掘りする監査作業者である。各 CLI のエントリーポイントから出口まで、関数呼び出し連鎖を行レベルで追跡し、外部接続点・分岐・fallback・dead code を file:line で明示する。

本 Step では **解釈・評価・推測・改善案・業界標準との比較**は書かない。コードに書かれた事実だけを構造化する。

---

## 2. 着手前の必読

次のファイルを最初から最後まで全文読んでから着手する。

- `doc/監査-CODEX/PROMPTS/step1a.md`（Step 1-A の仕様、本 Step の前提）
- `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`（Step 1-A 成果物、本 Step の入力。特に §1 公開関数シグネチャ、§2 CLI コマンド定義、§3 設定キー、§7 不明事項を参照する）

読んだら、作業を始める前に 5-10 行で次を提示する:

1. Step 1-A 成果物のうち、本 Step で必ず引用する節（§1 / §2 / §3 / §7 のいずれか）
2. 本 Step で深掘りする CLI 一覧
3. 本 Step で**深掘りしない** CLI 一覧と、その理由
4. Step 1-A の §7（動的 env var resolution）のうち本 Step で解消する候補
5. 自分が誤解しそうな点と、その回避方法

---

## 3. 読んでよいファイル（allowlist）

Step 1-A と同じ範囲に Step 1-A 成果物を加える。

- `spec_grag/` 配下の全 Python ファイル
- `spec_grag/templates/` 配下の全ファイル
- `tests/` 配下の全 Python ファイル
- `pyproject.toml` / `setup.py` / `setup.cfg`
- `doc/監査-CODEX/PROMPTS/step1a.md`
- `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`

---

## 4. 読まないファイル（denylist）

- `doc/` 配下のその他全ファイル（`doc/EXTERNAL_DESIGN.ja.md` / `doc/DESIGN.ja.md` / `doc/AGENTS.md` / `doc/監査/` の既存資料 等）
- `archive/` / `BAK/` 配下
- `.spec-grag/` 配下
- `CLAUDE.md` / `AGENTS.md` / `README.md`
- `.venv/` / `node_modules/` / `.git/`

`doc/監査-CODEX/PROMPTS/step1a.md` と `doc/監査-CODEX/STEP1A_INVENTORY.ja.md` 以外の `doc/` 配下は開かない。

---

## 5. 禁則（書いてはいけないこと）

- 推測表現（「と思われる」「おそらく」「意図は～」「設計者は～」）
- 評価表現（「適切」「妥当」「過剰」「不足」「冗長」「正しく動く」「適切に処理する」）
- 改善案 / リファクタ案
- 業界標準 / RAG / GraphRAG / LlamaIndex 等の外部方式との比較
- 「責務」「役割」「担当」「管理」「処理」だけで内容を説明する記述。**入力 / 何を呼ぶ / 出力**で書く
- 各ステップに file:line を付けない記述
- フロー追跡で「省略した」「以下同様」と書く（同じパターンが連続する場合は、その旨を明示してパターンを 1 つ書き、残りは「同一パターンを N 回繰り返す: file:line, file:line, ...」と書く）
- 「呼ばれている」とだけ書いて、**どの条件で呼ばれるか**を書かない記述
- 外部接続点を「ある」とだけ書いて、接続先・接続条件・失敗時挙動を書かない記述

---

## 6. 対象 CLI と対象外 CLI

### 深掘り対象（9 個）

Step 1-A §2 で観測された CLI のうち、次を深掘りする:

1. `core`
2. `inject`
3. `inject-search`
4. `inject-section`
5. `inject-chapters`
6. `inject-purpose`
7. `inject-conflicts`
8. `realign`
9. `watch`

### 対象外（理由を明示）

次は本 Step の深掘り対象から外す。**理由を §0 に明示する**:

- `spec-grag` (top-level main parser): 上記 9 個に dispatch するだけのエントリー
- `spec-grag-slash`: 上記 9 個の一部を呼ぶ薄い wrapper（Step 1-A §1 で確認）
- `spec-grag-watch`: `watch` のエントリーポイントの別名
- `spec-grag-setup-project` / `spec-grag-setup-system`: 設定の初期化系。retrieval / artifact 生成・読込経路ではないため、方式評価の対象外

対象外と判断したものでも、Step 1-A §1 のエントリー関数 file:line を本書 §0 に引用する。

---

## 7. 出力構成

成果物 `doc/監査-CODEX/STEP1B_FLOWS.ja.md` を次の節構成で書く。各節は省略不可。

### §0. 監査範囲

- commit hash（`git rev-parse HEAD`）
- 前提とする Step 1-A 成果物のパス
- 深掘り対象 CLI（9 個）の一覧と、それぞれのエントリー関数 file:line
- 対象外 CLI の一覧と理由

### §1〜§9. CLI ごとのユースケース完走チェーン

各 CLI について 1 節を立てる。順序は §6 に従う（§1 = core, §2 = inject, ..., §9 = watch）。

各節の形式:

```markdown
## §N. <CLI 名>

エントリー: <file:line> 経由で <関数名> (<file:line>) を呼ぶ

### フローチェーン

ステップ 1: <呼び出し関数 file:line>
  入力: <型・データソース・前段からの引き継ぎ>
  処理: <何の API を呼ぶか — 「LLM 呼出 / vector 検索 / grep / hash 計算 / file I/O / subprocess」のいずれか、その対象 file:line>
  出力: <型・次段への引き渡し>
  外部接続: <Qdrant / FlagEmbedding / LLM provider / file I/O / subprocess / なし、接続条件と失敗時挙動>
  分岐 (該当時): <if 条件、threshold、except → fallback、file:line>

ステップ 2: ...
（CLI の出口に至るまで）

### 最終出力

- 戻り値の型（dataclass / dict 構造）file:line
- stdout に書かれる JSON / text の構造
- exit code 分岐 file:line

### このフローの中で「呼ばれていない引数 / 経路」

- 関数シグネチャに存在するが、本フロー中で参照されない引数: <引数名 (file:line) — 参照所在なし>
- import されているが、本フロー中で使われていないモジュール: <モジュール名 (file:line)>

### このフローで観測される外部接続点

- <種別> <接続先> <呼出箇所 file:line> <呼出条件> <失敗時挙動 file:line>
（このフロー固有の外部接続を全件列挙）
```

ステップ数の目安: 浅い経路（`inject-chapters` 等の artifact lookup）は 3-5 ステップ。深い経路（`core`）は 20-50 ステップ。**浅ければ短く、深ければ深く**。

### §A. 動的 env var resolution の解消

Step 1-A §7 で残った「`os.environ.get(name)` のように name が変数で grep に乗らなかった」項目を、フロー追跡時に確定した範囲で解消する。

| Step 1-A §7 該当 file:line | name 変数に入る具体的な値（コード上で確定可能なもの） | 値の根拠 file:line |

解消できないものは「解消不能」として残し、Step 1-C で扱う旨を明記する。

### §B. 出現するが呼ばれない経路（dead-on-arrival）

各 CLI のフロー追跡で観測された次を全件列挙する:

- 関数シグネチャに存在するが、どの CLI フローからも参照されない引数（dead 引数）
- import されているが、どの CLI フローからも使われていないモジュール
- 関数として定義されているが、どの CLI フローからも呼ばれていない関数

| 対象 file:line | 種別（引数 / import / 関数）| 観測範囲（追跡した CLI 全てで参照なし） | 探索した grep / AST コマンド |

### §C. 設定 key の重複 / 乖離

Step 1-A §3 で観測された設定 key について、フロー追跡時に確認された重複・乖離を列挙する:

- 同じ意味の値を 2 箇所以上から読んでいる key（例: `retrieval.section_collection` と `vector_store.section_collection`）
- dataclass に定義されていないが、コード中で `config.get("...")` 経由で読まれている key
- template config (`spec_grag/templates/.spec-grag/config.toml`) に書かれているが、dataclass の読込所在が無い key
- dataclass の読込所在があるが、フロー中で参照されない key

| key | 観測された重複 / 乖離 | 該当 file:line（複数） | 影響を受ける CLI |

「影響を受ける CLI」は本 Step §1〜§9 で観測された範囲のみ書く。

### §D. 不明 / 解釈不能事項

本 Step のフロー追跡で**機械的に判定できなかった**項目を記録する。

- 空でもよい
- 空の場合: 追跡範囲、不明候補として検討したが不明扱いにしなかった箇所、空にした理由を記録
- 水増し禁止

| 箇所 file:line | フロー追跡で判定できなかった事象 | 追跡で試したこと |

---

## 8. 良い例 / 悪い例

### 良い例 (1) — フローチェーン

```
ステップ 3: spec_grag/inject.py:96 (`run_spec_inject` 内)
  入力: project_root (str | Path), agent_constraints (Sequence[Mapping[str, Any]] | None)
  処理: spec_grag/inject.py:117 で agent_constraints が None または empty の場合、戻り値 dict に `constraints=[]` を入れて return する。LLM provider を呼び出さない、retrieval も呼び出さない
  出力: dict (constraints, freshness_report, blocking_reasons, warnings の構造)
  外部接続: なし
  分岐: spec_grag/inject.py:115 で agent_constraints が空のときの early return
```

理由: 入力・処理・出力・外部接続・分岐が file:line と共に明示されている。「LLM を呼ばない」「retrieval を呼ばない」を**事実として**書いている（評価表現ではなく観測事実）。

### 悪い例 (1) — フローチェーン

```
ステップ 3: inject の制約検証部分
  処理: Agent から渡された constraints を validate して返す
  外部接続: 適宜あり
```

理由: file:line なし、関数名なし、入力・出力なし、「適宜あり」が曖昧。

### 良い例 (2) — 呼ばれない引数

```
| spec_grag/inject.py:66 `run_spec_inject` の `freshness_report` 引数 | 引数 | step1b §2 (inject) フロー中、spec_grag/inject.py:66 から出口まで `freshness_report` を直接参照する箇所なし。spec_grag/inject.py:96 で別名 `freshness` の代入があるが、これは関数内ローカル変数 `_freshness_input` の構築用で、`freshness_report` 引数とは別経路 | grep -n "freshness_report" spec_grag/inject.py |
```

理由: どの CLI のフロー中で参照されないかを明示、別名や類似引数との混同を区別、検証 grep を併記。

### 悪い例 (2) — 呼ばれない引数

```
| inject の引数 | 関数 | 使われていない |
```

理由: file:line なし、どの引数か特定されていない、観測範囲なし。

### 良い例 (3) — 設定 key の重複

```
| `section_collection` | `retrieval.section_collection` (config.py:109, dataclass) と `vector_store.section_collection` (dataclass 未定義、config.get 経由) の 2 経路 | spec_grag/core.py:1234 で `retrieval.section_collection` を読み、それが None なら spec_grag/core.py:1235 で `vector_store.section_collection` を読み、それも None なら spec_grag/core.py:1236 で `vector_store.collection` を読む。コード上に 3 段の優先順位がある | core, inject-search, related_sections（spec_grag/related_sections.py:390-394 でも同じ 3 段優先） |
```

理由: 観測された 3 段優先順位を file:line で明示、影響する CLI / モジュールを明示。評価せず事実だけ書いている。

### 悪い例 (3) — 設定 key の重複

```
| section_collection が複数箇所から読まれている | これは設定の冗長性で、整理すべきである | core, inject など |
```

理由: file:line なし、「整理すべき」は改善案で禁則違反、影響する CLI が具体的でない。

### 良い例 (4) — 動的 env var resolution

```
| spec_grag/llm_provider.py:488 `value = os.environ.get(name)` | name は spec_grag/llm_provider.py:485 の for loop で `for name in env_vars:` から得る。env_vars は spec_grag/llm_provider.py:480 で `("HOME", "PATH", "PYTHONPATH")` のリテラルから初期化される | spec_grag/llm_provider.py:480 |
```

理由: name 変数の値が確定する位置と、その値の具体的なリテラルを引用している。

---

## 9. 「全件」と書く時のルール

Step 1-A の §7 と同じルール: 「全件」「全部」「すべての」と書く時は、**同じ節内で実行した探索コマンドを併記する**。

例:
```
本 §B（呼ばれない経路）で観測された dead 引数は全件 N 件である。

探索コマンド:
$ grep -nE "def run_spec_inject" spec_grag/inject.py
$ python3 -c "import ast; ..."  # AST: function argument extraction
$ grep -nE "freshness_report" spec_grag/inject.py
```

---

## 10. 作業手順

1. Step 1-A の `STEP1A_INVENTORY.ja.md` を全文読む
2. `git rev-parse HEAD` で commit hash を取得し §0 に記録
3. §0 で対象 CLI と対象外 CLI を確定
4. §1 (core) → §2 (inject) → §3 (inject-search) → §4 (inject-section) → §5 (inject-chapters) → §6 (inject-purpose) → §7 (inject-conflicts) → §8 (realign) → §9 (watch) の順で各 CLI のフローを書く
5. §A で Step 1-A §7 の動的 env var を、フロー追跡で確定した範囲で解消する
6. §B で呼ばれない経路（dead 引数 / dead import / dead 関数）を全件列挙する
7. §C で設定 key の重複 / 乖離を全件列挙する
8. §D で本 Step の不明事項を書く
9. §最終報告（§11 参照）を本文末に書く

---

## 11. 最終報告（本文末に必須）

本文の最後に次の節を作る。

```markdown
## 最終報告

- 作成したファイル: doc/監査-CODEX/STEP1B_FLOWS.ja.md
- 前提とした Step 1-A 成果物: doc/監査-CODEX/STEP1A_INVENTORY.ja.md
- 深掘りした CLI 数: 9 個
- 対象外として除外した CLI 数: <件数と理由の所在>
- 解消した動的 env var 件数: <Step 1-A §7 の 6 件のうち、本 Step §A で解消した件数> / 6
- 観測された dead 引数の件数: <§B>
- 観測された dead import の件数: <§B>
- 観測された dead 関数の件数: <§B>
- 観測された設定 key の重複 / 乖離: <§C 件数>
- §D（不明事項）の状態: <空 / N 件>
- file:line なしで残っている事実文の有無: なし（または箇所列挙）
- denylist を開いていないことの確認方法: <例: 全 grep / AST の引数を §0 に記録、doc/ 配下は step1a.md と STEP1A_INVENTORY.ja.md のみ参照>
- 中断 / 失敗があれば: <隠さずに記録、または「なし」>
```

---

## 12. 完了条件

次を全て満たしたら完了とする。

- allowlist 外を開いていない
- 禁則表現を含まない
- 全ての事実記述（表セル・フロー記述含む）に file:line が付いている
- §0 に対象 CLI と対象外 CLI が明示されている
- §1〜§9 の各 CLI フローがエントリーから出口まで揃っている
- 各 CLI フローの末尾に「呼ばれない引数 / 経路」と「観測される外部接続点」の節がある
- §A で Step 1-A §7 の動的 env var が、解消可能な範囲で解消されている
- §B で dead 引数 / dead import / dead 関数が全件列挙されている（探索コマンドを併記）
- §C で設定 key の重複 / 乖離が全件列挙されている
- §D が空の場合、空である根拠が記録されている
- §最終報告が記入されている

---

## 13. 中断時のルール

タスクの途中で中断する場合（タイムアウト / ユーザー指示 / 自己判断停止のいずれでも）:

- 現状を `doc/監査-CODEX/STEP1B_FLOWS.ja.md` に保存する
- ファイル先頭に「⚠ 未完了: 中断箇所と理由」セクションを追加する
- 完了報告の代わりに「中断報告」として、どこまで完了したか / 何が残っているかを提示する
- 完了したように見せる事実水増し、file:line 省略、推測の混入は禁止

CLI 単位で中断する場合、§N の途中で止めるよりも、§N を「未完了」マークして §N+1 を着手しないでください。CLI ごとの完走性を優先する。

---

## 14. 注意

- Step 1-A の §7（動的 env var）は本 Step §A で解消対象。フロー追跡時に name 変数の値が確定したら §A に記録する
- Step 1-A の §4（リテラル候補）に docstring / help 文字列が混入しているのは Step 1-A 時点で許容済み。本 Step では artifact 名 / env var 名のうち実フロー中で使われるものだけを §1〜§9 で引用する
- Step 1-A の §5（外部接続キーワード件数）は包括的件数。本 Step では各 CLI フロー中で実際に呼ばれる箇所だけを「外部接続点」として §1〜§9 末尾の表に記録する
- 既存 `doc/監査/INTERNAL_SPEC_FROM_CODE.ja.md` / `doc/監査/IMPLEMENTATION_*.md` は無かったものとして扱う
- 「責務」「役割」を書きそうになったら、**入力 / 何を呼ぶ / 出力**に書き直す
