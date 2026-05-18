# Step 1-C 用 Codex prompt: 横断観点表

本 prompt は Step 1-A の機械的インベントリと Step 1-B の主要 CLI フローを起点に、**観点ごとに 9 CLI を横断**する表を作成する。後段 Step 2 で C4 / arc42 / ADR 形式の方式仕様書を再構成するための統合素材となる。

成果物の置き先: `doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md`

---

## 1. 役割

あなたは Step 1-A と Step 1-B の事実を統合し、観点 × CLI のマトリクスで横断ビューを作る監査作業者である。1-A と 1-B で既に file:line 付きの事実が揃っているので、本 Step では**新規 grep を最小限に抑え**、既存事実の再構造化を中心に行う。新規 grep が必要な場合は、Step 1-A / 1-B でカバーされていない理由を明示する。

本 Step では **解釈・評価・推測・改善案・業界標準との比較**は書かない。

---

## 2. 着手前の必読

次の 4 ファイルを最初から最後まで全文読んでから着手する。

- `doc/監査-CODEX/PROMPTS/step1a.md`（Step 1-A 仕様）
- `doc/監査-CODEX/PROMPTS/step1b.md`（Step 1-B 仕様）
- `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`（Step 1-A 成果物）
- `doc/監査-CODEX/STEP1B_FLOWS.ja.md`（Step 1-B 成果物）

読んだら、作業を始める前に 5-10 行で次を提示する:

1. 1-A / 1-B 成果物のうち、本 Step で必ず引用する節
2. 1-A / 1-B の事実だけで埋まる節と、新規 grep が必要な節の見分け
3. 本 Step で新規 grep する範囲（あれば）
4. 自分が誤解しそうな点と、その回避方法

---

## 3. 読んでよいファイル（allowlist）

- `spec_grag/` 配下の全 Python ファイル
- `spec_grag/templates/` 配下の全ファイル
- `tests/` 配下の全 Python ファイル
- `pyproject.toml` / `setup.py` / `setup.cfg`
- `doc/監査-CODEX/PROMPTS/step1a.md`
- `doc/監査-CODEX/PROMPTS/step1b.md`
- `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`
- `doc/監査-CODEX/STEP1B_FLOWS.ja.md`

---

## 4. 読まないファイル（denylist）

- `doc/EXTERNAL_DESIGN.ja.md` / `doc/DESIGN.ja.md` / `doc/AGENTS.md`
- `doc/監査/` の既存資料（前回成果は無かったものとして扱う）
- `archive/` / `BAK/` 配下
- `.spec-grag/` 配下
- `CLAUDE.md` / `AGENTS.md` / `README.md`
- `.venv/` / `node_modules/` / `.git/`

---

## 5. 禁則（書いてはいけないこと）

Step 1-A / 1-B の禁則に加え、本 Step 固有の禁則:

- 推測表現（「と思われる」「おそらく」「意図は～」）
- 評価表現（「適切」「妥当」「過剰」「不足」「冗長」「正しく」「整理されていない」）
- 改善案 / リファクタ案
- 業界標準 / RAG / GraphRAG / LlamaIndex 等の外部方式との比較
- 「責務」「役割」「担当」「管理」「処理」だけで内容を説明する記述
- file:line を付けない事実記述
- 「dead」「不要」「冗長」と書く時、観測範囲（target 9 CLI 範囲か / リポジトリ全体か）を明示しない記述
- 「失敗時に止まる」「continue する」と書く時、止まるかどうかの判定箇所 file:line を書かない記述
- 既存 1-A / 1-B 事実を再掲する時、引用元の節番号と file:line を併記しない記述

---

## 6. 出力構成

成果物 `doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md` を次の節構成で書く。各節は省略不可。

### §0. 監査範囲

- commit hash（`git rev-parse HEAD`）
- 前提とする Step 1-A / 1-B 成果物のパス
- 本 Step で新規 grep した範囲（あれば、その理由と探索コマンド）
- 観点 × CLI マトリクスで対象とする CLI 9 個の確認（Step 1-B §0 と同じ）

### §1. 外部接続点 × CLI のマトリクス

9 CLI それぞれが、次の外部接続点を**呼ぶ / 呼ばない**を表にする。

|  | core | inject | inject-search | inject-section | inject-chapters | inject-purpose | inject-conflicts | realign | watch |
|---|---|---|---|---|---|---|---|---|---|
| LLM provider (subprocess) |  |  |  |  |  |  |  |  |  |
| Qdrant client |  |  |  |  |  |  |  |  |  |
| FlagEmbedding (BGE-M3) |  |  |  |  |  |  |  |  |  |
| file I/O: `.spec-grag/config.toml` |  |  |  |  |  |  |  |  |  |
| file I/O: Source Specs (Markdown) |  |  |  |  |  |  |  |  |  |
| file I/O: Purpose / Core Concept |  |  |  |  |  |  |  |  |  |
| file I/O: `.spec-grag/state/*.json` |  |  |  |  |  |  |  |  |  |
| file I/O: `.spec-grag/context/*.json` |  |  |  |  |  |  |  |  |  |
| file I/O: `.spec-grag/cache/**` |  |  |  |  |  |  |  |  |  |
| file lock: `core_update.lock.json` |  |  |  |  |  |  |  |  |  |
| subprocess（LLM 以外） |  |  |  |  |  |  |  |  |  |

各セルには次のいずれかを書く:

- `呼ぶ (file:line)` — 呼び出し箇所 file:line を引用（Step 1-B §1〜§9 の「外部接続点」表から）
- `呼ばない` — そのフロー中で呼ばれないことの根拠 (Step 1-B §N の「呼ばれない経路」または「外部接続点」表に該当なし)
- `条件付き (条件) (file:line)` — 設定値や引数で呼ぶか否かが決まる場合、条件と file:line

### §2. artifact × CLI のライフサイクル

Step 1-A §4 / §5 と Step 1-B の各 CLI フローで観測された artifact について、次を表にする。

| artifact | 物理位置 | 生成 CLI (file:line) | 読込 CLI (file:line) | 削除 / 上書き CLI (file:line) | スキーマ定義 (file:line) |

対象 artifact:
- `section_manifest.json`
- `conflict_review_items.json`
- `chapter_anchors.json`
- `freshness.json`
- `retrieval_index_state.json`
- `related_sections_state.json`
- `core_progress.json`
- `core_update.lock.json`
- `watch_state.json`
- `watch_queue.json`
- `_debug_provider_invocations.jsonl`
- `_debug_related_prompts.jsonl`
- `related_typing_cache.json`
- Qdrant section collection（物理位置 = qdrant URL の collection）

「生成 CLI」が複数ある場合は全件列挙する。読込 CLI が「無い」場合、その旨を明示する（artifact が書かれているが読まれていない可能性を可視化する）。

### §3. 失敗時挙動 × CLI

Step 1-B の各 CLI 「外部接続点」表の失敗時挙動を、次のカテゴリに分類して横断する。

| カテゴリ | 意味 |
|---|---|
| `blocked` | CLI 自体を止め、blocked status を返す |
| `failed` | CLI 自体を止め、failed status を返す |
| `degraded / warning` | CLI は続行し、warning または degraded status を結果に含める |
| `fallback` | 代替経路に切替えて続行する |
| `skipped` | 該当処理をスキップし、CLI は続行する |
| `raise` | exception を raise する（CLI 終了 exit code 非 0） |

横断表:

| 失敗対象 | CLI | カテゴリ | 判定箇所 (file:line) | 失敗時の挙動 (file:line) |

Step 1-B の §1〜§9「外部接続点」表に書かれた失敗時挙動を全件転記し、カテゴリを分類する。Step 1-B に無い失敗箇所を本節で新規追加する場合、新規 grep の探索コマンドを併記する。

### §4. 判断ロジック / fallback / 閾値の集約

Step 1-B の各 CLI 「分岐」記述を横断統合する。

| 判断対象 | 条件 | 通常時挙動 | 例外時 / fallback 時挙動 | 該当 CLI | 所在 (file:line) |

対象とする判断:
- 設定値による経路切替（例: `embedding.provider == "flagembedding"` で Qdrant upsert を呼ぶか）
- 数値閾値（top-k, threshold, batch size, retry count, timeout）
- env var による経路切替（`SPEC_GRAG_FAKE_LLM`, `SPEC_GRAG_FAKE_RETRIEVAL`, `SPEC_GRAG_DEBUG_*` 等）
- 例外からの fallback（mechanical fallback, fake provider fallback 等）
- early return（empty input, missing artifact 等）

Step 1-B のフロー記述から引用する箇所は、Step 1-B §N の節番号と元の file:line を併記する。

### §5. 設定 key 重複の CLI 横断影響

Step 1-B §C で観測された設定 key 重複 4 件を、本 Step で**全 CLI 影響範囲に展開**する。

| key | 重複 / 乖離の内容 | 影響を受ける CLI 全件 | 読込所在 (file:line) |

影響を受ける CLI は Step 1-B §1〜§9 で観測された範囲を全件書く（§C では「core, inject-search, inject-section」と書かれていたが、Step 1-B のフロー追跡で参照される全 CLI を列挙）。

### §6. dead 経路の二重区分

Step 1-B §B で observed の「dead」を 2 つのカテゴリに分けて再整理する。

#### §6.1 対象 9 CLI 範囲の dead

target 9 CLI（core / inject / inject-search / inject-section / inject-chapters / inject-purpose / inject-conflicts / realign / watch）のフロー中で参照されない、または呼ばれないもの。

| 対象 file:line | 種別 | target 9 CLI 範囲で参照されない理由 | 該当 Step 1-B §B 行 |

#### §6.2 リポジトリ全体の dead

target 9 CLI 以外の経路（`spec-grag-slash`, `spec-grag-watch`, `spec-grag-setup-project`, `spec-grag-setup-system` などの別 entry point、test ファイル）からも参照されないもの。

| 対象 file:line | 種別 | repo 全体で参照されない理由 | 探索した grep / AST コマンド |

注意: Step 1-B §B の「`slash_main`, `watch_main`, `setup_project_main`, `setup_system_main`」は **target 9 CLI 範囲では呼ばれない**が、`pyproject.toml` の別 entry である。これらは §6.2 ではなく §6.1 に分類し、別 entry として実在することを明示する。

### §7. 不明 / 解釈不能事項

本 Step で機械的に判定できなかった項目を記録する。

- 空でもよい。空の場合は探索範囲・検討した候補・空にした理由を記録
- Step 1-B §D の 2 件（`os.environ.copy()` と `_env_enabled(name)`）は本 Step で解消対象外として明示する
- 本 Step 固有の解消不能のみを記録する

| 箇所 file:line | 機械的に判定できなかった事象 | 試した探索コマンド |

---

## 7. 良い例 / 悪い例

### 良い例 (1) — §1 外部接続点マトリクス

```
| LLM provider (subprocess) | 呼ぶ (spec_grag/core.py:302-349, spec_grag/llm_provider.py:308-328) | 呼ばない (Step 1-B §2 行 128: spec_grag/inject.py:91 で `provider` / `llm_provider` を del) | 呼ばない (Step 1-B §3 行 169-172 「LLM provider を呼ばない」明示) | 呼ばない | 呼ばない | 呼ばない | 呼ばない | 条件付き (run_spec_inject 経由のみ。Step 1-B §8 行 365-366) | 呼ぶ (spec_grag/watcher.py:454-464 経由 spec_grag/core.py:812-822、Step 1-B §9 行 402-403) |
```

理由: 各セルに「呼ぶ / 呼ばない / 条件付き」が file:line と Step 1-B §節番号で根拠付けされている。

### 悪い例 (1) — §1 外部接続点マトリクス

```
| LLM provider | core: yes / inject: no / inject-search: no / ... |
```

理由: 「yes/no」のみで file:line と根拠なし。後段で追跡できない。

### 良い例 (2) — §2 artifact ライフサイクル

```
| `freshness.json` | `.spec-grag/context/freshness.json` (spec_grag/artifacts.py:35) | `core` (spec_grag/core.py:750-777, Step 1-B §1 行 68) / `watch` (spec_grag/watcher.py:283-314, Step 1-B §9 行 397) | `inject` (spec_grag/inject.py:599-612, Step 1-B §2 行 112) / `realign` (Step 1-B §8 行 373 経由 inject) | 上書きのみ (atomic write による rename、削除は別経路なし) | dataclass 定義なし (`build_freshness_report` の戻り値 dict が spec_grag/freshness.py:63-272 で構造を返す) |
```

理由: 生成・読込・削除の各 CLI が file:line + Step 1-B 節番号で記録、スキーマ定義の所在も明示。

### 悪い例 (2) — §2 artifact ライフサイクル

```
| freshness.json | core で生成、inject で読込 | freshness の情報を保持 |
```

理由: file:line なし、Step 1-B 引用なし、「freshness の情報を保持」は内容説明（責務記述）で禁則違反。

### 良い例 (3) — §3 失敗時挙動

```
| Qdrant 接続失敗 (section collection upsert) | core | failed | spec_grag/core.py:2143-2162 (Step 1-B §1 行 91 引用) | failed status と diagnostics を返し core 自体は止めない (spec_grag/core.py:2143-2162) |
```

理由: 失敗対象、CLI、カテゴリ、判定箇所、挙動箇所が全て file:line + Step 1-B 引用付き。

### 悪い例 (3) — §3 失敗時挙動

```
| Qdrant 失敗 | core / inject | エラー処理あり | 適切に処理 |
```

理由: カテゴリなし、file:line なし、「適切に処理」は評価表現で禁則違反。

### 良い例 (4) — §6.1 と §6.2 の区別

```
§6.1 (target 9 CLI 範囲の dead):
| spec_grag/cli.py:312 `slash_main` | 関数 1 件 | target 9 CLI の dispatch は spec_grag/cli.py:290-307 で、`slash_main` は pyproject.toml:31 の別 entry として実在する (Step 1-B §B 行 469) | Step 1-B §B 行 469 |

§6.2 (リポジトリ全体の dead):
| <該当箇所 file:line> | 関数 | tests/ / pyproject.toml / 全 spec_grag/ で参照なし | grep -RIn '<symbol_name>' spec_grag tests pyproject.toml |
```

理由: §6.1 は「target 9 CLI 範囲では呼ばれないが別 entry として実在」を明示、§6.2 は repo 全体での参照を grep で確認した結果のみ。

---

## 8. 「全件」と書く時のルール

Step 1-A / 1-B と同じ: 「全件」「全部」「全リスト」と書く時は、同じ節内で探索コマンドを併記する。

本 Step では Step 1-A / 1-B 既存事実を引用する場合、引用元の節番号と file:line で代替できる。新規 grep が必要な場合のみ探索コマンドを書く。

---

## 9. Codex 実行環境の注意

Step 1-B 実行時に観測された落とし穴:

- `grep` pattern に backtick を含めて double quote で囲むと、shell が backtick 内を command として展開する。`core` / `inject` / `watch` のような symbol を pattern に入れる時は、**single quote で囲む** か、`-F` (fixed string) フラグを使う
- 例: `grep -n "\`watch\`"` → 危険（backtick 展開）
- 安全: `grep -nF "watch"` または `grep -n 'watch'`
- escape の `\\` を double quote 内で使う時は `\$` などへの誤展開に注意

本 Step では新規 grep を最小限に抑えるが、必要な場合は上記に注意する。

---

## 10. 作業手順

1. Step 1-A / 1-B 成果物を全文読む
2. `git rev-parse HEAD` で commit hash を取得し §0 に記録
3. §1 外部接続点マトリクスを Step 1-B §1〜§9 の「外部接続点」表から転記し横断統合する
4. §2 artifact ライフサイクルを Step 1-A §4 (リテラル) と §5 (file I/O grep) と Step 1-B 各 CLI フローから構築する
5. §3 失敗時挙動を Step 1-B §1〜§9 から転記し、カテゴリ分類する
6. §4 判断ロジックを Step 1-B 「分岐」記述から横断統合する
7. §5 設定 key 重複を Step 1-B §C から全 CLI 影響範囲に展開する
8. §6.1 / §6.2 で dead を二重区分する
9. §7 で本 Step 固有の不明事項を記録（Step 1-B §D の 2 件は対象外として明示）
10. §最終報告（§12 参照）を本文末に書く

---

## 11. 最終報告（本文末に必須）

本文の最後に次の節を作る。

```markdown
## 最終報告

- 作成したファイル: doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md
- 前提とした Step 1-A 成果物: doc/監査-CODEX/STEP1A_INVENTORY.ja.md
- 前提とした Step 1-B 成果物: doc/監査-CODEX/STEP1B_FLOWS.ja.md
- §1 マトリクスのセル件数: 11 行 × 9 CLI = 99 セル（または実件数）
- §2 artifact 件数: <件数>
- §3 失敗時挙動件数: <件数>
- §4 判断ロジック件数: <件数>
- §5 設定 key 重複件数: 4 件（Step 1-B §C 全件、新規発見があれば追記）
- §6.1 target 9 CLI 範囲の dead 件数: <件数>
- §6.2 リポジトリ全体の dead 件数: <件数>
- §7 本 Step 固有の不明事項件数: <件数>
- 本 Step で新規 grep した件数: <件数 / 0 件>
- file:line なしで残っている事実文の有無: なし（または箇所列挙）
- denylist を開いていないことの確認方法: <例: 全 grep / AST 引数を §0 に記録、doc/ 配下は step1a.md, step1b.md, STEP1A, STEP1B のみ参照>
- 中断 / 失敗があれば: <隠さずに記録、または「なし」>
```

---

## 12. 完了条件

次を全て満たしたら完了とする。

- allowlist 外を開いていない
- 禁則表現を含まない
- 全ての事実記述（表セル含む）に file:line または Step 1-B 節番号引用が付いている
- §0 に commit hash と前提成果物が明示されている
- §1 外部接続点マトリクスが 9 CLI 全列で埋まっている（空セルなし、各セルに file:line または「呼ばない」根拠）
- §2 artifact ライフサイクルが対象 artifact 全件で埋まっている
- §3 失敗時挙動が Step 1-B §1〜§9 の全外部接続点失敗を網羅している
- §4 判断ロジックが Step 1-B 「分岐」記述を網羅している
- §5 設定 key 重複が Step 1-B §C を全 CLI 影響範囲に展開している
- §6.1 / §6.2 が分けて記録されている
- §7 が空の場合、空である根拠が記録されている
- §最終報告が記入されている

---

## 13. 中断時のルール

タスクの途中で中断する場合:

- 現状を `doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md` に保存する
- ファイル先頭に「⚠ 未完了: 中断箇所と理由」セクションを追加する
- 完了報告の代わりに「中断報告」として、どこまで完了したか / 何が残っているかを提示する
- 「完了したように見せる」ための事実水増し、file:line 省略、推測の混入は禁止

節単位で中断する場合、§N の途中で止めるよりも §N を「未完了」マークして §N+1 を着手しないでください。横断観点ごとの完走性を優先する。

---

## 14. 注意

- 本 Step は Step 1-A / 1-B の事実を**再構造化**する作業である。新規 grep を最小限に抑える
- Step 1-B §D の 2 件（動的 env var の解消不能）は本 Step 対象外。§7 には書かない
- §6 の二重区分で、Step 1-B §B の `slash_main` / `watch_main` / `setup_project_main` / `setup_system_main` は §6.1 に分類する（target 9 CLI 範囲では呼ばれないが、pyproject.toml の別 entry として実在）
- 「責務」「役割」を書きそうになったら、**入力 / 何を呼ぶ / 出力 / 失敗時挙動**で書き直す
- 既存 1-A / 1-B 事実を再掲する時は、必ず元の節番号と file:line を併記する
- grep pattern の quoting に注意（§9 参照）
