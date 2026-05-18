# Step 1 用 Codex prompt: コードからの事実抽出

本 prompt は、spec-grag リポジトリのコードのみから「方式評価に必要な事実」を抽出するための指示書である。後段 Step 2 で C4 / arc42 / ADR 形式の方式仕様書を再構成するための素材を集めることが目的である。

成果物の置き先: `doc/監査-CODEX/STEP1_FACTS.ja.md`

---

## 1. 役割

あなたは既存コードベースから事実だけを抽出する監査者である。本 Step では推測・評価・改善案・方式判断・業界標準との比較は一切書かない。コードに書かれている事実だけを file:line 付きで記録する。

---

## 2. 読んでよいファイル（allowlist）

次のみを読む。これ以外は開かない、引用しない、内容を前提にしない。

- `spec_grag/` 配下の全 Python ファイル
- `spec_grag/templates/` 配下の全ファイル（テンプレート設定 / リソース）
- `tests/` 配下の全 Python ファイル
- `pyproject.toml` / `setup.py` / `setup.cfg`（package 構造確認のため）

許可されたファイルでも、import 経由で内部参照しているリポジトリ内ファイル以外は開かない。

---

## 3. 読まないファイル（denylist）

次は開かない、内容を引用しない、内容を前提にしない、ファイル名で参照しない。

- `doc/` 配下の全ファイル（`doc/監査/STANDARD_GRAG_PATTERNS.ja.md` を含む。Step 3 で初めて使う）
- `doc/監査/INTERNAL_SPEC_FROM_CODE.ja.md`（前回成果、無かったものとして扱う）
- `doc/監査/IMPLEMENTATION_*.md`（前回監査の disposition、修正中）
- `doc/EXTERNAL_DESIGN.ja.md` / `doc/DESIGN.ja.md`（Step 4 で初めて使う）
- `doc/AGENTS.md` / `CLAUDE.md` / `AGENTS.md` / `README.md`（agent 向け / 利用者向けドキュメント、外部契約や設計意図を述べている。Step 1 では引きずられないよう開かない）
- `archive/` 配下
- `BAK/` 配下（存在すれば）
- `.spec-grag/` 配下（generated runtime state）
- `node_modules/` / `.venv/` / `.git/`

---

## 4. 禁則（書いてはいけないこと）

次は本書に書かない。書いた場合は Step 1 の成果物として無効である。

- 推測表現: 「と思われる」「だろう」「と推測される」「おそらく」「意図は～と考えられる」
- 評価表現: 「適切」「不適切」「よく設計されている」「問題がある」「過剰」「不足」「冗長」「妥当」
- 改善案 / 修正案 / リファクタ案
- 方式判断の正当化: 「なぜこの方式か」「この採用理由は～」（コードに literal でコメントがあり、それを引用するだけならよい。その場合は引用と明記する）
- 業界標準 / RAG / GraphRAG / LlamaIndex 等の外部方式との比較
- 外部設計書 / Purpose / Core Concept の内容を前提とした記述（コードがそれを「読み込む I/O 事実」として扱う場合のみ可。内容の評価は禁止）
- `file:line` 付与のない事実記述（テーブルや図でも、根拠の file:line を必ず併記する）
- 「管理する」「処理する」「連携する」「制御する」だけで済ませる記述。何を入力に、何を出力する関数か、どの行で何をするかを書く

---

## 5. 出力構成

成果物 `doc/監査-CODEX/STEP1_FACTS.ja.md` を次の節構成で書く。各節は省略不可。書く事実が無い節は「該当なし」と明記する。

### S1. 監査範囲と読込宣言

- 対象 commit hash（`git rev-parse HEAD` を実行して記録）
- 実際に読んだファイルの absolute path 一覧（allowlist の外を開いていないことの証跡）
- 読まなかった対象ファイル（allowlist 内だが Step 1 では未読、と判断した場合は理由を明記）

### S2. パッケージ構成と CLI エントリーポイント

- `pyproject.toml` / `setup.py` の package 定義、エントリーポイント定義
- `spec_grag/__main__.py` から CLI 関数への dispatch チェーン
- argparse による全コマンド・サブコマンドの定義所在（file:line）。各コマンドの引数とデフォルトを表で書く

### S3. ファイル一覧と公開シンボル

`spec_grag/` 配下の全 `.py` ファイルについて表で書く。

| file | LOC | 公開関数 | 公開クラス | dataclass / TypedDict |

`公開` の定義: モジュール先頭で `def` / `class` で定義され、`_` で始まらないもの。各シンボルは file:line を付与する。

### S4. CLI コマンドごとのユースケース完走チェーン

各 CLI コマンド（`core`, `inject`, `inject-search`, `inject-section`, `inject-chapters`, `inject-purpose`, `inject-conflicts`, `realign`, `watch` 等、argparse から実際に観測された全コマンド）について、次の形式で完走チェーンを書く。

```
コマンド: <コマンド名>
エントリー関数: <file:line>

ステップ 1: <呼び出し関数 file:line>
  入力: <型・データソース・前段からの引き継ぎ。実際の引数名と型注釈を引用>
  処理: <何の API を呼ぶか / 何の計算をするか。LLM 呼出 / vector 検索 / grep / hash / file I/O のどれか>
  出力: <返り値の型と意味>
  外部接続: <Qdrant / FlagEmbedding / LLM provider / file I/O / subprocess のどれか、無ければ「無し」>

ステップ 2: ...
（出口に至るまで全ステップ）

最終出力: <stdout に何を JSON / text で書くか。exit code は何か>
```

ここはサボらない。各 CLI コマンドの入口から出口まで、実際の関数呼び出しを全部追う。1 関数 1 ステップに分解する必要は無いが、外部接続が発生する箇所、判断分岐が発生する箇所、artifact を書き出す箇所はステップとして必ず立てる。

### S5. 外部接続点の全件

下記の表で全件を列挙する。

| 種別 | 接続先 | 呼出箇所 file:line | 呼出条件 | 失敗時挙動 |

種別の例:
- LLM subprocess（codex / claude / その他 CLI）
- LLM fake provider
- 埋め込み計算（FlagEmbedding 等）
- Vector store クライアント（Qdrant 等）
- File I/O（read / write / atomic write / lock file）
- Subprocess（git / その他）

「呼出条件」は「embedding.provider が flagembedding のとき」「設定 X が true のとき」等、コード上で観測される条件を書く。「失敗時挙動」は raise / 空返却 / fallback / log のいずれか、その対象 file:line。

### S6. 設定キー消費箇所

`.spec-grag/config.toml` および `spec_grag/templates/` 内 config の各 key について、次の表で全件を列挙する。

| key | dataclass / 型 | 定義所在 file:line | 読込所在 file:line | 用途（コード観測のみ） |

「用途」は推測ではなく、その値が次に何の関数に渡され、何の引数になるかを書く。値の意味づけや方式上の役割の推測は書かない。

### S7. データ artifact のライフサイクル

`.spec-grag/state/` / `.spec-grag/context/` / `.spec-grag/cache/` 配下に生成されるファイル、Qdrant collection、その他永続データについて、次の表で全件を列挙する。

| artifact 名 | 物理位置（path or collection 名） | 生成箇所 file:line | 読込箇所 file:line | 削除 / 上書き箇所 file:line | スキーマ参照（dataclass / TypedDict file:line） |

artifact の例: `section_manifest.json`, `conflict_review_items.json`, `chapter_anchors.json`, `freshness.json`, `core_update.lock.json`, `core_progress.json`, `_debug_*.jsonl`, Qdrant Section collection 等。

### S8. 判断ロジック / fallback / 閾値の所在

コード中の重要な判断分岐、閾値、fallback 経路について、次の表で全件を列挙する。

| 判断対象 | 条件 | 通常時挙動 | 例外時 / fallback 時挙動 | 所在 file:line |

対象とすべき箇所:
- `if` による経路切替で外部接続の有無が変わる箇所
- `except` から fallback 経路に入る箇所
- 数値閾値（top-k, threshold, batch size, retry count, timeout）の所在と値
- env var による経路切替（`SPEC_GRAG_*` 等）

### S9. データ間の参照関係（依存グラフ）

S7 の artifact、S8 の判断対象、S6 の設定キーがどう繋がっているかを、コードから観測できる範囲で列挙する。例:

- `section_manifest.json` を更新する関数: <file:line>
- `section_manifest.json` を読む関数: <file:line>
- その読み手は freshness 判定に使う: <file:line> （事実引用、評価は書かない）

ここは「事実の連鎖」だけを書き、設計判断や方式の正当性には踏み込まない。

### S10. テストカバレッジの所在

`tests/` 配下のテストファイル一覧と、それぞれが `spec_grag/` のどのモジュール / どの関数を import しているかを表で書く。テストの内容（どんなシナリオを検証しているか）は概要を 1 行で書く。テストの妥当性評価は書かない。

| test file | import している spec_grag モジュール | 検証対象（概要 1 行） |

### S11. 未確認 / 解釈不能事項

コードを読んだが意味が分からなかった箇所、推測なしには内容を書けない箇所、コードのコメントが古い / 矛盾している箇所を列挙する。

| 箇所 file:line | 何が分からないか | コメントの有無 / 食い違いの有無 |

ここに書いた項目は、後段 Step 2 / Step 3 / Step 4 で人間判断が必要な候補になる。隠さず全部書く。

---

## 6. 良い例 / 悪い例

### 良い例 (1) — S4 ユースケース完走

```
コマンド: inject-search
エントリー関数: spec_grag/cli.py:307 -> spec_grag/inject.py:870 (`run_inject_search`)

ステップ 1: spec_grag/inject.py:870 (`run_inject_search`)
  入力: query: str（CLI 引数 --query から）、top_k: int（CLI 引数 --top-k、デフォルト spec_grag/cli.py:XXX）
  処理: 設定読込、Qdrant provider 名と embedding provider 名を取得（spec_grag/inject.py:XXX-XXX）
  出力: 後続に config, query, top_k を渡す
  外部接続: file I/O（.spec-grag/config.toml 読込）

ステップ 2: spec_grag/inject.py:904 (`_initialize_retriever`)
  入力: config
  処理: embedding.provider == "flagembedding" かつ vector_store.provider == "qdrant" のとき QdrantHybridRetriever を作る (spec_grag/retrieval_index.py:XXX)。それ以外は structured warning を返す (spec_grag/inject.py:924)
  出力: retriever instance または warning dict
  外部接続: FlagEmbedding (lazy import, spec_grag/retrieval_index.py:167), Qdrant client (lazy import, spec_grag/retrieval_index.py:364)
...
```

理由: 入力・処理・出力・外部接続が各ステップで完結している。「retriever を作る」だけでなく、どの条件で何を作るかが書かれている。

### 悪い例 (1) — S4 ユースケース完走

```
コマンド: inject-search
処理: Qdrant に対して live hybrid retrieval を実行する。失敗時は warning を返す。
```

理由: 「live hybrid retrieval を実行する」は責務一行記述。どの関数で、どの条件で、どの入力に対して、何を返すかが書かれていない。これでは Step 2 で方式を再構成できない。

### 良い例 (2) — S5 外部接続点

```
| LLM subprocess | codex CLI | spec_grag/llm_provider.py:383 | provider 設定が codex かつ SPEC_GRAG_FAKE_LLM が unset/0 のとき | spec_grag/llm_provider.py:454 で retry 3 回、最終失敗時は LlmInvocationError を raise |
```

理由: 接続条件（provider 設定 + env）、失敗時挙動（retry 回数と最終挙動）が具体的に書かれている。

### 悪い例 (2) — S5 外部接続点

```
| LLM subprocess | codex / claude | spec_grag/llm_provider.py | 必要に応じて呼ぶ | エラー時は適切に処理 |
```

理由: 「必要に応じて」「適切に処理」が抽象表現で、コードに書かれている条件と挙動が分からない。

### 良い例 (3) — S8 判断ロジック

```
| Qdrant への upsert 実行 | embedding.provider == "flagembedding" かつ vector_store.provider == "qdrant" | upsert を実行し、戻り値で `retrieval_index_status=updated` | 上記条件を満たさないとき `skipped`、例外時 `failed` を返し core 自体は止めない | spec_grag/core.py:423, spec_grag/core.py:1154, spec_grag/core.py:1216 |
```

理由: 条件、通常時挙動、例外時挙動、所在が揃っている。

### 悪い例 (3) — S8 判断ロジック

```
| embedding 関連 | provider が標準でないとき | skip する | エラー時は log を出す | spec_grag/core.py 周辺 |
```

理由: 条件が曖昧、所在が「周辺」、log の宛先と内容が書かれていない。

### 良い例 (4) — S11 未確認

```
| spec_grag/related_sections.py:1850-1856 | LLM への prompt で `conflicts_with` を出さないよう指示しているが、`conflicts_with` という field を読む側コードを spec_grag/ 内で発見できなかった | コードコメント無し |
```

理由: 何が分からないか、調査範囲、コメントの有無が書かれている。隠さず正直に書いている。

### 悪い例 (4) — S11 未確認

```
| 全体的に複雑な箇所がいくつかあった | コードコメントが足りない |
```

理由: 箇所が特定されておらず、後段で追跡できない。

---

## 7. 作業手順

1. `git rev-parse HEAD` を実行し commit hash を記録する
2. allowlist の対象ファイルを一通り `ls` / `find` で列挙し、読む対象を確定する
3. `spec_grag/__main__.py` と `spec_grag/cli.py` から CLI コマンド一覧を確定し、S4 で追跡する対象を決める
4. S2 → S3 → S4 → S5 → S6 → S7 → S8 → S9 → S10 → S11 の順で書く（S4 が最も重い。S2-S3 で全体地図を作ってから S4 を埋める）
5. 書き終わったら、各節の事実記述に file:line が付いているか自己点検する
6. 「推測」「評価」「改善案」を再 grep で自己点検する（章ごとに `と思われる` `だろう` `適切` `不適切` `問題` `改善` 等を検索）

---

## 8. 完了条件

次を全て満たすとき完了とする。

- allowlist 外のファイルを開いていない
- 禁則表現（推測、評価、改善案、業界標準比較）を含んでいない
- 全ての事実記述に file:line が付いている
- S11（未確認事項）が空でない（コードベース規模から、解釈不能な箇所が 0 件であることはほぼあり得ない。0 件なら確認不足を疑う）
- S4 で全 CLI コマンドのチェーンが入口から出口まで揃っている
- S5, S6, S7, S8 の表が「該当なし」を除き全件網羅されている

完了したら、次の 2 文を本文末に書く。

> 本書は spec-grag リポジトリのコードのみから抽出した事実集である。Step 2 以降でこれを素材として方式仕様書を再構成する。
> 本書では推測・評価・改善案・業界標準比較・外部設計書との照合を行っていない。これらは Step 2 / Step 3 / Step 4 で行う。

---

## 9. 注意

- 既存の `doc/監査/INTERNAL_SPEC_FROM_CODE.ja.md` は無かったものとして扱う。参照しない、引用しない
- 既存の `doc/監査/IMPLEMENTATION_*.md` は修正中のため参照しない
- 過去の commit log / git diff は事実として参照してよいが、コミットメッセージの主張をそのまま事実として書かない（コードに現在書かれていることが事実）
- 不明点を埋めるために `doc/` を開くのは禁則違反である。不明点は S11 に書いて残す
