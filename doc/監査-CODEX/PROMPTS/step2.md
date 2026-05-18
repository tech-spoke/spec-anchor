# Step 2 用 Codex prompt: 方式仕様書の逆生成（C4 / arc42 / ADR 混合形式）

本 prompt は Step 1-A / 1-B / 1-C で構築した事実集をもとに、**コードから方式仕様書を逆生成**する。後段 Step 3 で業界標準との差分、Step 4 で外部設計書との整合チェックを行う。本 Step では妥当性判定や業界標準との比較は行わない。

成果物の置き先: `doc/監査-CODEX/STEP2_METHOD.ja.md`

---

## 1. 役割

あなたは Step 1-A / 1-B / 1-C の事実集を構造化し、第三者がコードを読まずに方式を理解できる**方式仕様書**を作成する作業者である。C4 / arc42 / ADR テンプレートの混合形式で、コードに書かれた事実だけから方式を逆生成する。

本 Step では:

- 妥当性判定（適切 / 不適切 / 妥当 / 過剰 / 不足）は書かない
- 業界標準（RAG / GraphRAG / LlamaIndex 等）との比較は書かない
- 外部設計書 / Purpose / Core Concept の中身を参照しない（コードがそれらをどう扱うかは事実として記述する）
- 推測で空白を埋めない。コードから読めない箇所は「コードから理由不明」と明記する

---

## 2. 着手前の必読

次のファイルを最初から最後まで全文読んでから着手する。

- `doc/監査-CODEX/PROMPTS/step1a.md`（Step 1-A 仕様）
- `doc/監査-CODEX/PROMPTS/step1b.md`（Step 1-B 仕様）
- `doc/監査-CODEX/PROMPTS/step1c.md`（Step 1-C 仕様）
- `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`（Step 1-A 成果物）
- `doc/監査-CODEX/STEP1B_FLOWS.ja.md`（Step 1-B 成果物）
- `doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md`（Step 1-C 成果物）

読んだら、作業を始める前に 5-10 行で次を提示する:

1. 1-A / 1-B / 1-C 成果物のうち、本 Step で必ず引用する節
2. 本 Step で新規 grep / line read が必要だと判断した範囲（あれば、その理由）
3. 自分が誤解しそうな点と、その回避方法

---

## 3. 読んでよいファイル（allowlist）

- `spec_grag/` 配下の全 Python ファイル
- `spec_grag/templates/` 配下の全ファイル
- `tests/` 配下の全 Python ファイル
- `pyproject.toml` / `setup.py` / `setup.cfg`
- `doc/監査-CODEX/PROMPTS/step1a.md` / `step1b.md` / `step1c.md` / `step2.md`
- `doc/監査-CODEX/STEP1A_INVENTORY.ja.md` / `STEP1B_FLOWS.ja.md` / `STEP1C_CROSS_VIEWS.ja.md`

---

## 4. 読まないファイル（denylist）

次は**いかなる目的でも**開かない、引用しない、内容を前提にしない。

- `doc/EXTERNAL_DESIGN.ja.md` / `doc/DESIGN.ja.md` / `doc/AGENTS.md` / `doc/TODO.ja.md` / `doc/CHANGELOG.ja.md`
- `doc/監査/` 配下の既存資料（前回成果物。`doc/監査/STANDARD_GRAG_PATTERNS.ja.md` も Step 3 で初めて使う）
- `archive/` / `BAK/` 配下
- `.spec-grag/` 配下
- `CLAUDE.md`
- リポジトリ root の `AGENTS.md` / `README.md`
- `.venv/` / `node_modules/` / `.git/`

---

## 5. 上位ルール確認の禁止（重要）

`CLAUDE.md` / `AGENTS.md` / `README.md` / `doc/EXTERNAL_DESIGN.ja.md` / `doc/TODO.ja.md` などの**上位ルール文書 / 設計書 / 作業ガイド**を「作業者としての上位ルール確認」目的で読むことを禁止する。本 Step の作業に必要な情報は §2 必読仕様書と前段成果物に全て含まれている。

仕様書に書かれていない方針が必要だと感じた場合、上位ルール文書を読まずに次の対応を取る:

- §12 不明事項に記録する
- 「仕様書に方針記述が無い」と明示する
- 自己判断で進めず保留する

理由: 本 Step は「コードから方式を逆生成する」作業であり、設計書バイアスや作業ガイドのバイアスが入ると、後段 Step 3 / Step 4 の独立性が失われる。特に `doc/EXTERNAL_DESIGN.ja.md` は Step 4 で初めて開く設計書である。Step 2 時点で見ると、Step 4 の整合チェックが意味を失う。

---

## 6. 禁則（書いてはいけないこと）

- 推測表現（「と思われる」「おそらく」「意図は～」「設計者は～」）
- 評価表現（「適切」「不適切」「妥当」「過剰」「不足」「冗長」「正しく動く」「整理されている」「綺麗」）
- 改善案 / リファクタ案 / 修正方針
- 業界標準（RAG / GraphRAG / LlamaIndex / Microsoft / LightRAG 等）との比較・対応付け
- 「Purpose に照らして」「外部設計書では」のような上位文書参照
- file:line を付けない事実記述（見出し、表の列名、§0 監査範囲集計値は例外）
- 1-A / 1-B / 1-C 事実を引用するとき、引用元の節番号と元 file:line を併記しない記述
- C4 / arc42 / ADR のテンプレートを埋めるためだけに、コードから読めない内容を記述（読めないなら「コードから理由不明」と書く）
- 「責務」「役割」「担当」「管理」「処理」だけで内容を説明する記述（**入力 / 何を呼ぶ / 出力 / 失敗時挙動**で書く）

---

## 7. 出力構成

成果物 `doc/監査-CODEX/STEP2_METHOD.ja.md` を次の節構成で書く。

### §0. 監査範囲

- commit hash（`git rev-parse HEAD`）
- 前提とする Step 1-A / 1-B / 1-C 成果物のパス
- 本 Step で新規 grep / line read した範囲（あれば、その理由と探索コマンド）
- denylist を開いていないことの確認方法

### §1. Executive Summary

第三者がコードを読まずに「この実装は何方式か」を把握できる 15-30 行の要約。**事実のみ**で書く。次の問いに answers を与える:

- このリポジトリは何を提供する CLI ツール群か（コードから観測される範囲のみ）
- 主要 CLI コマンドはいくつあり、どの CLI が外部接続を持つか
- LLM provider / Qdrant / FlagEmbedding を呼ぶのはどの CLI か
- 制約生成（constraints）はどの主体が行うか（CLI か Agent か、コードから観測される範囲）
- 検索結果から本文へ辿る経路は実装されているか
- 既知の不確実性（Step 1-A 〜 1-C で「コードから不明」と記録された箇所）

本節では妥当性判定を書かない。事実だけ書く。

### §2. 方式分類（事実ベース）

Step 1-C §1 マトリクスから読み取れる**方式構造**を記述する。次の問いに事実で答える:

- どの CLI が retrieval を呼ぶか
- どの CLI が LLM を呼ぶか
- どの CLI が読み取り専用 artifact lookup か
- 制約生成（constraints）の主体は誰か（Agent / CLI どちらに観測されるか）
- グラフ構造（Property Graph, Entity Graph 等）が実装されているか / されていないか

判定は「事実 + 観測根拠 file:line + Step 1-C §節番号」の形で書く。「これは GraphRAG だ」「これは Hybrid RAG だ」のような業界用語での分類は Step 3 で行う。本 Step では「graph 構造の永続 store / graph traversal の有無」のような**実装事実**で書く。

### §3. 正本データ・派生データ・キャッシュ・index の分類

Step 1-C §2 の 14 artifact を次のカテゴリに分類する。各 artifact に file:line + Step 1-C §節番号を付ける。

| カテゴリ | 意味 |
|---|---|
| `正本` | 人間または Source Specs が source of truth。CLI は読むだけ、または上書きしない |
| `派生` | 正本から生成される、再生成可能なもの |
| `cache` | 高速化目的の中間データ。再生成可能 |
| `index` | 検索用 index。物理 store または DB |
| `runtime state` | 実行制御 / lock / queue / progress |
| `debug` | デバッグ専用、運用経路では未使用 |

各 artifact について次の表:

| artifact | カテゴリ | 最終根拠として使えるか（コードから観測される使用箇所がある場合のみ Yes） | 古くなった場合の検知方法（コードから観測される範囲） | 失敗時にどう扱うか（Step 1-C §3 引用） |

### §4. C4 ビュー（Container / Component）

#### §4.1 Container

外部 actor（人間 / Agent / Qdrant 等）と CLI の関係を、Step 1-C §1 マトリクスから抽出して図表で書く。Mermaid 等は使わなくて良い、表形式で構造化する:

| Container 名 | 種類（CLI / 外部 service / file store） | 入力 | 出力 | 接続先 |

#### §4.2 Component（spec_grag 内）

`spec_grag/` 内のモジュール責務を、Step 1-A §1 公開シンボル一覧から抽出する:

| Component（モジュール名）| 入力 | 何を呼ぶか（外部接続 / 他モジュール）| 出力 | 関連 artifact |

ここで「責務」と書きそうになったら、**入力 / 何を呼ぶ / 出力**で書き直す。

### §5. 主要データフロー

Step 1-B の各 CLI フローを、§4 の Container / Component 視点で再構造化する:

| CLI | エントリー | 主要ステップ（概要、3-7 ステップに圧縮）| Container 間移動 | 出力 |

Step 1-B の詳細フロー（27 ステップ等）を再掲する必要はない。**§5 では Container 間移動が見える粒度**に圧縮する。詳細は Step 1-B §1〜§9 への引用で代替する。

### §6. 更新時の整合性

次の case 別に、システムがどう振る舞うかをコード観測事実で記述する:

| case | 振る舞い（file:line + Step 1-C §節番号引用） | freshness / stale 通知の有無 |
|---|---|---|
| Source Specs の本文変更 |  |  |
| Section heading 変更 |  |  |
| Section 追加 |  |  |
| Section 削除 |  |  |
| Section 並べ替え |  |  |
| Source Specs ファイル名変更 |  |  |
| Purpose / Core Concept ファイル変更 |  |  |
| Qdrant collection 削除 |  |  |
| LLM provider 失敗 |  |  |
| embedding 失敗 |  |  |
| watcher 異常停止 |  |  |
| 設定 (`.spec-grag/config.toml`) 変更 |  |  |

書けない case は「コードから観測される更新ロジックなし」と書く。憶測で埋めない。

### §7. 検索結果から本文へ戻る経路

Step 1-B §3 (`inject-search`) を中心に、次の経路を 1 ステップずつ追う:

1. query が CLI 引数からどう受け取られるか
2. query が何で embedding されるか
3. embedding が何で検索されるか（dense / sparse / fusion）
4. hit payload に何が含まれるか（field 一覧、所在 file:line）
5. hit payload から source 本文へ戻れるか（`source_span` / `source_document_id` / `source_section_id` 等のフィールドの有無、`inject-section` 経路の存在）
6. Summary / Search Keys / Related Sections は evidence として使えるか / 補助材料か（[`spec_grag/related_sections.py:1053-1060`](../../spec_grag/related_sections.py) など、コードに観測される範囲のみ）

各ステップに file:line + Step 1-B §節番号を付ける。

### §8. 失敗時ポリシー（横断表）

Step 1-C §3 の 34 件を、CLI ごとに次のカテゴリで再構造化する:

| CLI | 失敗対象 | カテゴリ | 通知方法（exit code / status / warning / diagnostics の field 名）| Step 1-C §3 行番号 |

categories: `blocked` / `failed` / `degraded / warning` / `fallback` / `skipped` / `raise`

ここで「外部契約に適合するか」は書かない（Step 4 で扱う）。事実のみ。

### §9. ADR 候補（コードから読み取れる方式判断）

コード上で observed の設計判断を、ADR テンプレート（決定 / 文脈 / 採用理由 / 代替案 / 結果 / リスク）で記録する。**ただし、コードから読み取れない要素は「コードから不明」と書く**。

| 決定 | 文脈（コード観測事実）| 採用理由（コード上のコメント / docstring / 命名にあれば引用、無ければ「コードから不明」）| 代替案（コード上に削除済み / 別経路として残るものがあれば引用）| 結果（コード観測事実）| リスク（Step 1-C §6 dead / §5 設定 key 重複から観測されるもの）| 証跡 file:line |

ADR 候補として最低限扱う方式判断:

- LLM provider 呼び出しが core / watch (core 経由) のみで、inject 系は呼ばないこと
- 制約生成（constraints）が CLI 側ではなく Agent 側で行われていること
- `inject-search` が Qdrant hybrid retrieval を直接呼ぶ唯一の経路であること
- Related Sections が retrieval auxiliary とマークされていること（[`spec_grag/related_sections.py:1053-1060`](../../spec_grag/related_sections.py) など）
- Section Embedding text に Section raw body を含めず Summary / Search Keys / Identifiers から作ること（[`spec_grag/retrieval_index.py:661-689`](../../spec_grag/retrieval_index.py) 周辺）
- Qdrant collection 名の 3 段優先順位（Step 1-C §5）
- `core_progress.json` が生成されるが運用経路で読み込まれないこと（Step 1-C §2）
- `_debug_*.jsonl` が conditional に append されること

これら以外にコードから観測される判断があれば追記する。

### §10. アーキテクチャリスク一覧

Step 1-C §6.1（target 9 CLI 範囲の dead）と §5（設定 key 重複）と §2 artifact ライフサイクル不整合（読込 CLI なし等）から、**コード観測事実**として記録する。

| リスク名 | 何が起きうるか（コード観測事実から導けるシナリオ）| なぜ起きるか（コード観測事実）| 再現条件（コード観測事実）| ユーザーから見える症状（exit code / warning / artifact 状態のいずれか）| 証跡 file:line |

「優先度」「必要なテスト」は本 Step では書かない（評価表現になるため）。事実観測のみ。

### §11. 方式の構造的要約（最終）

§1-§10 を踏まえ、第三者が「この実装の方式構造」を 10-15 行で把握できる要約を書く。判定は書かない。

含めるべき要素:

- データプロダクトの正本 / 派生 / index / runtime state 分類の全体像
- 制約生成 / answer 生成の主体（Agent / CLI のどちらに観測されるか）
- 検索経路（dense / sparse / fusion）と本文戻り経路の実装有無
- 失敗時ポリシーの全体傾向（block の多寡、fallback の多寡）
- コード観測事実として残った主要なリスクと不確実性

### §12. 不明 / 解釈不能事項

本 Step で「コードから読み取れなかった」項目を記録する:

| 箇所 file:line | コードから不明な事象 | 試した探索方法（Step 1-A 〜 1-C 引用 + 新規 grep） |

空でもよい。空の場合は探索範囲と空にした理由を記録する。Step 1-B §D / Step 1-C §7 を再掲する必要はない（参照引用のみで可）。

---

## 8. 良い例 / 悪い例

### 良い例 (1) — §2 方式分類

```
- LLM provider を subprocess で呼び出す CLI: `core` (`spec_grag/core.py:302-349`; Step 1-C §1 行 33), `watch` (queue がある場合 `run_spec_core_for_watcher` 経由で `core` を呼ぶ: `spec_grag/watcher.py:454-464`; Step 1-C §1 行 33)
- Qdrant client を呼ぶ CLI: `core` (条件: embedding.provider == "flagembedding" かつ vector_store.provider == "qdrant"; Step 1-C §1 行 34), `inject-search` (Step 1-C §1 行 34), `inject-section` (Step 1-C §1 行 34), `watch` (core 経由; Step 1-C §1 行 34)
- graph 構造の永続 store / graph traversal: コード観測なし。Related Sections は `spec_grag/related_sections.py:1053-1060` で retrieval auxiliary とマーク。永続化は `retrieval_index_state.json` (Step 1-C §2 行 53) と Qdrant section collection (Step 1-C §2 行 62) のみ
```

理由: 事実、観測根拠 file:line、Step 1-C §節番号引用、業界用語比較なし、評価表現なし。

### 悪い例 (1) — §2

```
- これは Hybrid RAG / lightweight related-section retrieval 型である
- GraphRAG ではない
- 制約生成を Agent に委譲する設計は適切である
```

理由: 業界用語比較が混入、評価表現が混入、file:line なし、Step 1-C 引用なし。

### 良い例 (2) — §3 artifact 分類

```
| `section_manifest.json` | 派生 | No（最終根拠としてではなく、core が生成し core が freshness 判定に使う: Step 1-C §2 行 49） | core が `--all` または各 section の semantic_hash 変化で再生成（`spec_grag/core.py:272-297`; Step 1-B §1 行 54）| atomic write の失敗時は tmp unlink 後 raise（`spec_grag/artifacts.py:202-220`; Step 1-C §3 行 70） |
```

理由: カテゴリ判定の根拠を Step 1-C 引用付きで明示、各セルに file:line または §節番号。

### 悪い例 (2) — §3

```
| section_manifest.json | 重要なデータ | 最終的な根拠として使える可能性がある | 古くなったら core が再生成する | エラー処理あり |
```

理由: 評価表現「重要な」、推測「可能性がある」、file:line なし。

### 良い例 (3) — §9 ADR

```
| 制約生成は Agent 側 | コード観測: `spec_grag/inject.py:91` で `provider` / `llm_provider` 引数を `del` する（Step 1-B §2 行 128, Step 1-C §6.1 行 155）。`run_spec_inject` は constraints を validate のみ（`spec_grag/inject.py:154-190`; Step 1-B §2 行 116）| コードから不明 | コード観測: dead 引数として `task_prompt` / `prompt` / `conversation_context` / `provider` / `llm_provider` が `run_spec_inject` シグネチャに残る（Step 1-C §6.1 行 155）| 結果: Agent が constraints を準備し CLI が freshness gate と検証のみ行う構造 | リスク: dead 引数が将来の契約変更で混乱を招く可能性（Step 1-C §6.1 行 155 と Step 1-B §B 行 465）| `spec_grag/inject.py:66-151`, `spec_grag/inject.py:91`, Step 1-B §2 行 128 |
```

理由: 「採用理由」が観測不能な場合「コードから不明」と明記、各要素に file:line + Step 1-B / Step 1-C §節番号引用。

### 悪い例 (3) — §9

```
| Agent が制約を生成する | これは責務分離のため | LLM を inject で呼ぶ案もあった | より良い設計になっている | LLM 呼び出しコスト削減 | 特になし |
```

理由: 「責務分離のため」は推測、「より良い設計」は評価、「LLM を inject で呼ぶ案もあった」はコード非観測、file:line なし。

---

## 9. 「全件」と書く時のルール

Step 1-A 〜 1-C と同じ: 「全件」「全部」「すべての」と書く時は、同じ節内で探索コマンドまたは Step 1-A〜1-C 引用を併記する。本 Step では Step 1-A〜1-C への引用で代替できる。新規 grep が必要な場合のみ探索コマンドを書く。

---

## 10. Codex 実行環境の注意（再掲）

grep pattern に backtick を含めて double quote で囲まない。single quote または `-F` を使う。詳細は `step1c.md:179-188` 参照。

---

## 11. 作業手順

1. Step 1-A / 1-B / 1-C 成果物を全文読む（denylist 確認: `CLAUDE.md` / `AGENTS.md` / `doc/EXTERNAL_DESIGN.ja.md` 等を**読まない**）
2. `git rev-parse HEAD` で commit hash を取得し §0 に記録
3. §1 Executive Summary を書く
4. §2 方式分類を Step 1-C §1 マトリクスから構造化
5. §3 artifact 分類を Step 1-C §2 ライフサイクルから構造化
6. §4 C4 ビューを Step 1-A / 1-C / 1-B から構造化
7. §5 主要データフローを Step 1-B から圧縮構造化
8. §6 更新時整合性を case 別に書く（書けない case は「コードから観測なし」と明示）
9. §7 検索結果から本文戻り経路を Step 1-B §3 中心に追跡
10. §8 失敗時ポリシーを Step 1-C §3 から CLI ごとに再構造化
11. §9 ADR 候補を所定の方式判断 + 追加観測について書く（「コードから不明」を恐れない）
12. §10 アーキテクチャリスクを Step 1-C §5 / §6 / §2 から構造化
13. §11 方式の構造的要約を §1-§10 を踏まえて 10-15 行で書く
14. §12 不明事項を本 Step 固有の項目で書く
15. §最終報告（§12 参照）を本文末に書く

---

## 12. 最終報告（本文末に必須）

```markdown
## 最終報告

- 作成したファイル: doc/監査-CODEX/STEP2_METHOD.ja.md
- 前提とした Step 1-A / 1-B / 1-C 成果物のパス
- §1 Executive Summary の行数
- §2 方式分類の事実件数
- §3 artifact 分類の件数（14 件 = Step 1-C §2 と一致するか）
- §4.1 Container / §4.2 Component の件数
- §5 主要データフローの CLI 件数（9 件 = 対象 CLI と一致するか）
- §6 更新時整合性の case 件数と「コードから観測なし」件数
- §7 検索結果から本文戻り経路のステップ件数
- §8 失敗時ポリシーの件数（34 件 = Step 1-C §3 と一致するか）
- §9 ADR 候補の件数（所定の方式判断 8 件 + 追加観測 N 件）
- §10 アーキテクチャリスク件数
- §11 方式構造的要約の行数（10-15 行に収まったか）
- §12 不明事項件数
- 本 Step で新規 grep した件数（0 件であることが望ましい、新規 grep があった理由）
- file:line または Step 1-A 〜 1-C §節番号引用が付いていない事実文の有無: なし（または箇所列挙）
- denylist を開いていないことの確認方法: 上位ルール文書（CLAUDE.md / AGENTS.md / doc/EXTERNAL_DESIGN.ja.md 等）を一切開いていない（または何件開いた、理由）
- 中断 / 失敗があれば: <隠さずに記録、または「なし」>
```

---

## 13. 完了条件

- allowlist 外を開いていない（特に CLAUDE.md / AGENTS.md / doc/EXTERNAL_DESIGN.ja.md 等の上位ルール文書）
- 禁則表現（推測 / 評価 / 改善案 / 業界標準比較 / 上位文書参照 / 「責務」だけの記述 / file:line 無し）を含まない
- 全ての事実記述に file:line または Step 1-A 〜 1-C §節番号引用が付いている
- §0〜§12 が全て埋まっている
- §3 artifact 件数が 14 件で Step 1-C §2 と一致
- §8 失敗時ポリシー件数が 34 件で Step 1-C §3 と一致
- §6 / §9 で「コードから観測なし / 不明」を恐れずに明記している
- §11 方式構造的要約が 10-15 行に収まっている
- §最終報告が記入されている

---

## 14. 中断時のルール

途中で中断する場合:

- 現状を `doc/監査-CODEX/STEP2_METHOD.ja.md` に保存
- ファイル先頭に「⚠ 未完了: 中断箇所と理由」セクションを追加
- 完了報告の代わりに「中断報告」として、どこまで完了したか / 何が残っているかを提示
- 事実水増し、file:line 省略、推測の混入は禁止
- 節単位で中断する場合、§N の途中で止めるよりも §N を「未完了」マークして §N+1 を着手しない

---

## 15. 注意

- 本 Step は Step 1-A〜1-C の事実を**方式仕様書として再構造化する**作業である。新規 grep を最小限に抑える
- Step 4 で `doc/EXTERNAL_DESIGN.ja.md` を初めて開く設計になっている。Step 2 時点で見ると Step 4 の整合チェックが意味を失う
- 「責務」「役割」を書きそうになったら、**入力 / 何を呼ぶ / 出力 / 失敗時挙動**で書き直す
- C4 / arc42 / ADR は「テンプレートの欄を埋める」ことが目的ではない。コードから読めない欄は「コードから不明」と書いて空白にする
- 既存 1-A / 1-B / 1-C 事実を再掲する時は、必ず元の節番号と file:line を併記する
