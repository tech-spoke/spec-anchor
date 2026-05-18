# Step 3 用 Codex prompt: 業界標準 GRAG / RAG パターンとの差分判定

本 prompt は Step 2 で逆生成された方式仕様書を、業界標準 GRAG / RAG パターン（`doc/監査/STANDARD_GRAG_PATTERNS.ja.md`）に照らして差分判定する。後段 Step 4 で外部設計書 (`doc/EXTERNAL_DESIGN.ja.md`) との整合チェックを行う。本 Step では妥当性の最終判定は行わない（Purpose / 外部設計書を見ないと正当化判定ができないため、Step 4 で人間判断対象としてフラグする）。

成果物の置き先: `doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md`

---

## 1. 役割

あなたは Step 2 成果物（コード由来の方式仕様書）と業界標準資料 (`doc/監査/STANDARD_GRAG_PATTERNS.ja.md`) を比較し、判定軸ごとに**差分**を構造化する作業者である。

本 Step では:

- 業界標準の各最低条件に対して、現状が整合 / 部分整合 / 不整合 / 業界標準より strict / 業界標準より loose のいずれかを判定する
- 不整合が見つかった場合、「妥当性 / 正当化されるか」は判定しない（Step 4 で外部設計書と Purpose に照らして判断対象）
- 業界用語（RAG / Hybrid RAG / GraphRAG / LightRAG / lightweight related-section retrieval 等）の対応付けは行う（業界標準資料の §7 判定軸に基づく）
- 判定の根拠は Step 2 §1〜§12 と業界標準資料の §2-§7 のみを使う

---

## 2. 着手前の必読

次のファイルを最初から最後まで全文読んでから着手する。

- `doc/監査-CODEX/PROMPTS/step3.md`（本仕様書）
- `doc/監査-CODEX/PROMPTS/step1a.md` / `step1b.md` / `step1c.md` / `step2.md`（前段仕様書）
- `doc/監査-CODEX/STEP1A_INVENTORY.ja.md` / `STEP1B_FLOWS.ja.md` / `STEP1C_CROSS_VIEWS.ja.md` / `STEP2_METHOD.ja.md`（前段成果物）
- `doc/監査/STANDARD_GRAG_PATTERNS.ja.md`（業界標準資料）

読んだら、作業を始める前に 5-10 行で次を提示する:

1. Step 2 成果物のうち、判定の主要根拠とする節
2. STANDARD_GRAG_PATTERNS のうち、判定軸として採用する節（§7 が中心）
3. 業界用語の対応付けで自分が誤解しそうな点
4. Step 4 で判断対象として保留する候補（業界標準と不整合だが正当化される可能性のある事項）

---

## 3. 読んでよいファイル（allowlist）

- `spec_grag/` 配下の全 Python ファイル（必要な場合のみ、Step 2 の引用で代替できる場合は開かない）
- `spec_grag/templates/` 配下（必要な場合のみ）
- `pyproject.toml` / `setup.py` / `setup.cfg`（必要な場合のみ）
- `doc/監査-CODEX/PROMPTS/step1a.md` / `step1b.md` / `step1c.md` / `step2.md` / `step3.md`
- `doc/監査-CODEX/STEP1A_INVENTORY.ja.md` / `STEP1B_FLOWS.ja.md` / `STEP1C_CROSS_VIEWS.ja.md` / `STEP2_METHOD.ja.md`
- `doc/監査/STANDARD_GRAG_PATTERNS.ja.md`（**本 Step で初めて開く**）

---

## 4. 読まないファイル（denylist）

- `doc/EXTERNAL_DESIGN.ja.md` / `doc/DESIGN.ja.md` / `doc/AGENTS.md` / `doc/TODO.ja.md` / `doc/CHANGELOG.ja.md`
- `doc/監査/` の `STANDARD_GRAG_PATTERNS.ja.md` 以外のファイル（既存資料）
- `archive/` / `BAK/` 配下
- `.spec-grag/` 配下
- `CLAUDE.md` / `AGENTS.md` / `README.md`
- `.venv/` / `node_modules/` / `.git/`

`doc/EXTERNAL_DESIGN.ja.md` は **Step 4 で初めて開く設計書**である。本 Step では絶対に判定根拠にしない。

---

## 5. 上位ルール確認の禁止（Step 1-C / Step 2 と同じ）

Codex 環境の上位指示で `CLAUDE.md` / `AGENTS.md` / `doc/EXTERNAL_DESIGN.ja.md` 等を作業開始時に読むことが Step 1-C / Step 2 で発生した。本 Step では:

- 上位ルール文書を読んだ場合、**判定の根拠としては絶対に使わない**
- 判定根拠は Step 2 成果物と `doc/監査/STANDARD_GRAG_PATTERNS.ja.md` のみとする
- 「Purpose に照らして」「外部設計書では」のような上位文書参照は禁止
- 業界標準と不整合な事項が正当化されるかは判定しない（Step 4 で人間判断対象）

---

## 6. 禁則（書いてはいけないこと）

- 推測表現（「と思われる」「おそらく」「意図は～」「設計者は～」）
- 評価表現（「適切」「不適切」「妥当」「過剰」「不足」「冗長」「正しく」「綺麗」）
- 改善案 / リファクタ案 / 修正方針
- 「Purpose に照らして」「外部設計書では」のような上位文書参照
- file:line または Step 2 §節番号引用が付かない事実記述（見出し、列名、§0 集計値は例外）
- 業界標準の最低条件に対する判定で、「整合」「不整合」だけ書いて根拠を示さない記述
- 業界標準資料の引用なしに「業界標準では～」と書く記述（必ず `STANDARD_GRAG_PATTERNS.ja.md` の §節番号と行番号を併記）
- 業界標準と不整合な事項について「これは正しい / 間違っている」と判断する記述（**判定は Step 4**）
- 業界標準資料に書かれていない判定軸を持ち込む記述（必要なら §最終報告で「追加判定軸の提案」として明示）

---

## 7. 出力構成

成果物 `doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md` を次の節構成で書く。

### §0. 監査範囲

- commit hash（`git rev-parse HEAD`）
- 前提とする Step 2 成果物のパス
- 前提とする業界標準資料のパス: `doc/監査/STANDARD_GRAG_PATTERNS.ja.md`
- 本 Step で新規 grep / line read した範囲（あれば、その理由と探索コマンド）
- denylist を開いていないことの確認方法（上位ルール文書を判定根拠にしていないことの確認）

### §1. 業界標準パターンの判定軸（再掲）

`doc/監査/STANDARD_GRAG_PATTERNS.ja.md` §7 から、判定軸 6 件を引用する。

| 判定軸 | 業界標準資料の引用 (file:line) |
|---|---|
| RAG の最低条件 |  |
| Hybrid retrieval の最低条件 |  |
| GRAG の最低条件 |  |
| Incremental update の最低条件 |  |
| Evidence の最低条件 |  |
| Fallback の最低条件 |  |

各引用は STANDARD_GRAG_PATTERNS.ja.md の §7 行 99-104 から逐語引用する。書き換えない。

### §2. 判定軸ごとの差分判定

各判定軸について次のフォーマットで書く:

```markdown
### §2.N. <判定軸名>

**業界標準条件**: <STANDARD_GRAG_PATTERNS の引用 + file:line>

**現状の事実**: <Step 2 §節番号引用 + file:line。3-5 項目>

**判定**: <整合 / 部分整合 / 不整合 / 業界標準より strict / 業界標準より loose>

**判定根拠**: <事実と業界標準条件の対応 3-5 行>

**Step 4 への引き継ぎ**: <Step 4 で外部設計書 / Purpose に照らして判断するべき事項があれば記録、なければ「なし」>
```

判定の選択肢:

- `整合`: 業界標準条件を全て満たす
- `部分整合`: 業界標準条件の一部を満たすが、他の部分は満たさない
- `不整合`: 業界標準条件を満たさない
- `業界標準より strict`: 業界標準より強い条件を実装している
- `業界標準より loose`: 業界標準より弱い条件で実装している
- `業界標準と異なる方式`: 業界標準と全く異なる方式で類似目的を達成している

判定対象は §1 の 6 判定軸 + 追加で次の軸も扱う:

### §2.7. 全体方式分類（業界用語）

業界標準資料 §2-§6 から、現状の実装に最も近い業界用語呼称を判定する。

- 候補: Baseline RAG / Hybrid RAG / GraphRAG / LightRAG / PropertyGraphIndex / lightweight related-section retrieval
- 判定: 「最も近い呼称: X」「ただし Y の点で異なる」の形で書く
- 根拠: Step 2 §2 方式分類 + 業界標準資料 §2-§6 の引用

### §3. spec-grag 固有の方式選択

業界標準の判定軸では捉えきれない、spec-grag 固有の観察事実を列挙する。これらは Step 4 で外部設計書 / Purpose に照らして判断するべき候補となる。

| 固有事項 | 業界標準との関係 | 観察根拠 (Step 2 §節番号引用) | Step 4 への引き継ぎ |
|---|---|---|---|

最低限扱う事項:

- constraints / answer 生成が CLI 側ではなく Agent 側で行われる方式（Step 2 §9 ADR 行 235-236）
- `inject-search` が retrieval を呼ぶ唯一の inject 系経路で、他 4 個の inject 系経路（inject / inject-section / inject-chapters / inject-purpose / inject-conflicts）は LLM を呼ばない（Step 2 §1 / §2）
- Related Sections が retrieval auxiliary であり、evidence ではない（Step 2 §9 ADR 行 238）
- Section embedding text に raw body を含めず Summary / Search Keys / Identifiers から作る（Step 2 §9 ADR 行 239）
- `core_progress.json` が生成されるが target 9 CLI の読込表に出ない（Step 2 §9 ADR 行 241）
- target 9 CLI 範囲の dead 引数 5 件（`task_prompt` / `prompt` / `conversation_context` / `provider` / `llm_provider`）が `run_spec_inject` のシグネチャに残る（Step 2 §10 リスク行 254）
- Qdrant collection 名の 3 段優先順位（`retrieval.section_collection` → `vector_store.section_collection` → `vector_store.collection`）（Step 2 §9 ADR 行 240）

これら以外に Step 2 で観察された固有事項があれば追記する。

### §4. 判定サマリ

判定軸 7 件（§2.1-§2.7）の判定結果を表にする:

| 判定軸 | 判定 | Step 4 引き継ぎの有無 |
|---|---|---|
| RAG の最低条件 |  |  |
| Hybrid retrieval の最低条件 |  |  |
| GRAG の最低条件 |  |  |
| Incremental update の最低条件 |  |  |
| Evidence の最低条件 |  |  |
| Fallback の最低条件 |  |  |
| 全体方式分類（業界用語） |  |  |

### §5. Step 4 への引き継ぎ

§2.1〜§2.7 と §3 の中で、Step 4 で外部設計書 / Purpose に照らして判断するべき候補を集約する。

| 候補 | 判定根拠（§2 または §3 引用） | Step 4 で判断するべき内容 |
|---|---|---|

ここでは「現状の妥当性を判断する」ではなく、「Step 4 で人間判断対象として何を扱うべきか」を列挙する。

### §6. 不明 / 解釈不能事項

本 Step で機械的に判定できなかった項目を記録する。

- 空でもよい。空の場合は探索範囲・検討した候補・空にした理由を記録
- Step 1-B §D / Step 1-C §7 / Step 2 §12 を再掲する必要はない（参照引用のみで可）
- 本 Step 固有の不明のみ記録

| 箇所 file:line または §節番号 | 判定できなかった事象 | 試した探索方法 |

---

## 8. 良い例 / 悪い例

### 良い例 (1) — §2 判定軸

```
### §2.3. GRAG の最低条件

**業界標準条件**: graph 構造が永続化され、query 時に graph traversal / graph context building を行う。これを持たない場合は GRAG ではなく lightweight related-section retrieval と呼ぶべきである (STANDARD_GRAG_PATTERNS.ja.md §7 行 101)。

**現状の事実**:
- graph 構造の永続 store / traversal は allowlist 内 grep で観測されない (Step 2 §2 行 73)
- Related Sections は retrieval auxiliary field として Qdrant payload に入る (Step 2 §9 ADR 行 238)
- Related Sections は target section、confidence、evidence terms、channels、possible conflict を返す配列 (Step 2 §2 行 74)
- 業界用語の graph traversal は実装に存在しない (Step 2 §11 行 274)

**判定**: 不整合

**判定根拠**: 業界標準 GRAG の最低条件「graph 構造永続化 + query 時 graph traversal」に対して、現状は graph 構造の永続 store / traversal が観測されない。業界標準資料の §7 行 101 自身が「これを持たない場合は GRAG ではなく lightweight related-section retrieval と呼ぶべきである」と明示している。よって現状は GRAG ではなく lightweight related-section retrieval に分類される。

**Step 4 への引き継ぎ**: GRAG を名乗っているか / lightweight retrieval を名乗っているかは外部設計書 / Purpose の記述に依存する。Step 4 で外部設計書の方式呼称を確認し、コードと一致するかを判断する。
```

理由: 業界標準条件の逐語引用 + Step 2 事実引用 + 判定 + 判定根拠 + Step 4 引き継ぎが揃っている。判定は「不整合」だが「正しい / 間違っている」とは書かず、Step 4 へ判断を委ねている。

### 悪い例 (1) — §2 判定軸

```
### §2.3. GRAG の最低条件

これは GRAG ではないため不整合。lightweight retrieval として名乗るべきである。GRAG と書いているなら直すべき。
```

理由: 業界標準条件引用なし、Step 2 引用なし、「直すべき」は改善案で禁則違反、Step 4 引き継ぎなし。

### 良い例 (2) — §3 固有事項

```
| constraints 生成が Agent 側 | 業界標準資料 §2 (Baseline RAG) / §3 (Hybrid RAG) / §4 (GraphRAG) のいずれにも「制約生成」段階は明示的に分類されていない (STANDARD_GRAG_PATTERNS.ja.md §2-§6)。業界標準は LLM が retrieved context に基づき回答するパイプラインを示すが、CLI が constraints 検証のみを行い Agent が constraints 生成する分業は業界標準パターンと対応する明示的位置づけがない。 | Step 2 §9 ADR 行 235-236, Step 2 §11 行 6 | Step 4 で外部設計書 / Purpose が CLI / Agent の責務分担をどう規定しているかを確認する。 |
```

理由: 業界標準資料の該当節を引用、現状の事実を Step 2 引用、Step 4 引き継ぎ内容が具体的。

### 悪い例 (2) — §3 固有事項

```
| Agent が制約を生成する | これは責務分離のため業界標準に近い | コード | Step 4 で判断 |
```

理由: 業界標準資料の引用なし、「責務分離のため」は推測、Step 2 引用なし、Step 4 引き継ぎが具体的でない。

### 良い例 (3) — §2.7 方式分類

```
### §2.7. 全体方式分類（業界用語）

**業界標準の候補方式**:
- Baseline RAG (STANDARD_GRAG_PATTERNS.ja.md §2 行 20-32): 単一 retrieval パイプラインで passage を embed/index/retrieve/augment/generate
- Hybrid RAG (§3 行 34-46): dense + sparse の named vectors を持つ point を fusion 検索
- GraphRAG (§4 行 48-67): entity knowledge graph + community detection + local/global search
- LightRAG (§5 行 69-80): graph + vector の dual-level retrieval + incremental update
- PropertyGraphIndex (§6 行 82-93): chunk ごとの graph extraction + graph store + vector retrieval

**現状の事実**:
- BGE-M3 dense / sparse + RRF fusion (Step 2 §7 ステップ 3, Step 2 §11 行 270)
- graph 構造の永続 store / traversal なし (Step 2 §2 行 73)
- Related Sections は retrieval auxiliary、graph traversal 用ではない (Step 2 §9 ADR 行 238)
- hit payload に source_section_id を含み inject-section で本文 lookup (Step 2 §7 ステップ 5)

**判定**: 最も近い呼称: Hybrid RAG (§3) + lightweight related-section retrieval (§4 で示唆される代替呼称)

ただし、業界標準 Hybrid RAG が dense + sparse の vector channel fusion に焦点を当てるのに対し、現状は Section embedding text を heading / summary / search keys / identifiers から作り raw body を含めない点で異なる (Step 2 §9 ADR 行 239)。

**Step 4 への引き継ぎ**: 外部設計書 / Purpose で「GRAG」「Hybrid RAG」「lightweight retrieval」のいずれの呼称が採用されているかを確認する。
```

理由: 業界標準の候補方式を 5 件全て列挙、現状の事実を Step 2 引用、判定が「Hybrid RAG + lightweight related-section retrieval」のように複合的、Step 4 引き継ぎが具体的。

---

## 9. 「全件」と書く時のルール

Step 1-A〜Step 2 と同じ: 「全件」「全部」と書く時は探索コマンドまたは Step 1-A〜Step 2 / STANDARD_GRAG_PATTERNS への引用を併記する。本 Step では Step 2 / STANDARD_GRAG_PATTERNS への引用で代替できる。

---

## 10. Codex 実行環境の注意（再掲）

grep pattern の shell quoting に注意。詳細は `step1c.md:179-188` 参照。本 Step は引用中心で新規 grep を最小限にする。

---

## 11. 作業手順

1. Step 1-A 〜 Step 2 成果物と業界標準資料を全文読む
2. `git rev-parse HEAD` で commit hash を取得し §0 に記録
3. §1 で業界標準資料 §7 の判定軸 6 件を逐語引用
4. §2.1 〜 §2.6 で 6 判定軸ごとに判定する
5. §2.7 で全体方式分類を判定する
6. §3 で spec-grag 固有事項を列挙する
7. §4 で判定サマリを集約する
8. §5 で Step 4 への引き継ぎ候補を集約する
9. §6 で本 Step 固有の不明事項を記録する
10. §最終報告（§12 参照）を本文末に書く

---

## 12. 最終報告（本文末に必須）

```markdown
## 最終報告

- 作成したファイル: doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md
- 前提とした Step 2 成果物のパス
- 前提とした業界標準資料のパス: doc/監査/STANDARD_GRAG_PATTERNS.ja.md
- §1 判定軸件数: 6 件 (STANDARD_GRAG_PATTERNS.ja.md §7 と一致)
- §2.1〜§2.7 判定結果の内訳: 整合 N / 部分整合 N / 不整合 N / business strict N / business loose N / 業界標準と異なる方式 N
- §3 spec-grag 固有事項件数
- §5 Step 4 への引き継ぎ候補件数
- §6 本 Step 固有の不明事項件数
- 本 Step で新規 grep した件数（0 件が望ましい）
- file:line または §節番号引用が付いていない事実文の有無: なし（または箇所列挙）
- denylist を開いていないことの確認方法: doc/EXTERNAL_DESIGN.ja.md を判定根拠にしていない、上位ルール文書を判定根拠にしていない（または何件開いた、判定根拠にしていないことの確認方法）
- 中断 / 失敗があれば: <隠さずに記録、または「なし」>
```

---

## 13. 完了条件

- allowlist 外を開いていない、または開いたが判定根拠にしていない
- 禁則表現を含まない
- 全ての事実記述に file:line または §節番号引用が付いている
- §1 で業界標準資料 §7 の判定軸 6 件が逐語引用されている
- §2.1〜§2.6 で 6 判定軸の判定が「整合 / 部分整合 / 不整合 / business strict / business loose / 業界標準と異なる方式」のいずれかで明示されている
- §2.7 で全体方式分類が業界用語 5 候補から選ばれて判定されている
- §3 で spec-grag 固有事項が最低 7 件（指示の所定事項）+ 追加観察があれば列挙されている
- §4 で判定サマリが §2.1〜§2.7 と一致する形で集約されている
- §5 で Step 4 への引き継ぎ候補が集約されている
- §6 が空の場合、空である根拠が記録されている
- §最終報告が記入されている

---

## 14. 中断時のルール

途中で中断する場合:

- 現状を `doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md` に保存
- ファイル先頭に「⚠ 未完了: 中断箇所と理由」セクションを追加
- 完了報告の代わりに「中断報告」として、どこまで完了したか / 何が残っているかを提示
- 事実水増し、file:line / §節番号引用省略、推測の混入は禁止
- 判定軸単位で中断する場合、§2.N の途中で止めるよりも §2.N を「未完了」マークして §2.N+1 を着手しない

---

## 15. 注意

- 本 Step は「業界標準との差分判定」であり、**妥当性 / 正当化の判定は Step 4 に委ねる**
- 不整合と判定された事項は「不整合」と書き、「これは間違っている」「これは正しい」とは書かない
- 判定根拠は Step 2 成果物と STANDARD_GRAG_PATTERNS.ja.md のみ。外部設計書 / Purpose / 上位ルール文書は判定根拠にしない
- 業界標準資料に書かれていない判定軸を持ち込む場合、§最終報告で「追加判定軸の提案」として明示する
- 業界用語の対応付けで複数候補がある場合は複数併記する（例: 「Hybrid RAG + lightweight related-section retrieval」）
- 「責務」「役割」を書きそうになったら、**入力 / 何を呼ぶ / 出力 / 失敗時挙動**で書き直す
