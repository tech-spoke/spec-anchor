# spec-grag 開発ガイド（Claude Code 用）

このファイルは spec-grag リポジトリで作業する Claude Code セッションが最初に読むべき**不変ルール**を記録する。memory（`~/.claude/projects/-home-kazuki-public-html-spec-grag/memory/`）は揮発するため、リポジトリ管理下にも同じ内容を残す。

## 必読ドキュメント（新セッション開始時、この順序で）

1. **`doc/EXTERNAL_DESIGN.ja.md`** — 外部契約（source of truth、不変）
2. **`doc/DESIGN.ja.md`** — 現時点での方針、設計判断の境界、不確定項目
3. **本ファイル `CLAUDE.md`** — 不変ルール（本書）
4. memory `~/.claude/projects/-home-kazuki-public-html-spec-grag/memory/MEMORY.md` 経由で `project_engine_pivot.md`, `project_first_use_case.md`, `feedback_*.md` 8 件
5. 必要に応じて `BAK/` 配下を参考（過去の議論・調査の参照のみ、戻らない）

## 不変ルール（pivot を超えて生きる、ユーザーから明示された原則）

### ルール 1: 土台がない状態で設計を議論しない

**採用方針として「Python + LlamaIndex 系のエコシステム」で行くことは決定済**（pivot 後、commit b45d95f, 2026-04-27）。ただし、**具体 API**（PropertyGraphIndex / SimplePropertyGraphStore / SchemaLLMPathExtractor 等）の API 詳細・組み合わせ動作・永続化粒度・incremental update 方式は **未確認**。

「どういう機能があり、どう利用できるのか」が不明なままでは、設計は土台不足のまま破綻する。これは graphrag-rs 時代の Phase 0 原則だが、**pivot を超えて生きている**。LlamaIndex でも同じく：

- 機能カタログを把握する（何ができるか、何ができないか、何がプレースホルダか）
- 典型利用シーケンスをコード断片レベルで確認する
- 限界・既知の罠を実装レベルで把握する

これが揃うまで具体 API の **利用方法** を「最終方針」「採用」と確定しない。「LlamaIndex 系で行く」という採用方針自体は確定済（DESIGN.ja.md §1.4）。

関連 memory: `feedback_no_design_without_foundation.md`

### ルール 2: 推論カットの都合で不明な事をもっともらしく提示しない

私の学習データはカットオフがある（2026-01）。それ以降の LlamaIndex / 依存ライブラリの API 変更・破壊的変更・新機能・deprecated 化は知らない。

過去の知識ベースで「LlamaIndex はこう使う」「PropertyGraphIndex の API はこう」と書くのは「もっともらしい」が誤り得る。代わりに：

- WebFetch で公式 docs を確認した内容のみを書く
- 実コード（GitHub の最新版）を確認した内容のみを書く
- 確認していないことは**「未確認」と最初から明示する**

### ルール 3: 推論カットの都合で不明なものを隠して整合性を取ろうとしない

文書に書いた他の部分との整合性を取るために、未確認の API や挙動を「こうなっているはず」で埋めない。整合しなくても「未確認」と明示する。**整合性のために推測で穴埋めする方が、後から手戻りリスクが大きい**。

### ルール 4: 必要な調査は不明な点を無くすまで行う

「次セッションで調査」「MVP では省略」「最小コストで」「後で追加」を判断回避の逃げ口にしない。

設計に影響する不確定項目は、その項目を確定するまで設計判断を「最終」「採用」と書かない。「現時点での方針」「採用候補」「暫定」と書き分ける。

関連 memory: `feedback_no_minimum_cost_escape.md`

### ルール 5: 全項目列挙の原則

調査範囲は最初に網羅的に列挙し、各項目の現状把握度（確認済 / 中 / 浅い / 表面的 / 未確認）を一覧で明示する。未確認項目を見せないように範囲を縮小しない。

関連 memory: `feedback_full_scope_enumeration.md`

### ルール 6: 資料には決定内容と TODO のみを書く、作業メモとしない

仕様書・設計書・契約書（`doc/EXTERNAL_DESIGN.ja.md`, `doc/DESIGN.ja.md` 等）には以下のみを書く：

- **決定された内容**（現時点での方針、確定スキーマ、確定アーキテクチャ）
- **未確定の TODO**（不確定項目セクションで明示、解消されるまで実装に着手しない）

書かないもの：

- 議論プロセスの時系列（Phase 1, 2, 3, 4 のような作業段階）
- 過去の選定経緯（採用しなかった候補の評価、検討した代替案の議論）
- 作業メモ（途中経過、議論の振り返り、自分用の覚書）
- 「最初のユースケース」固有の詳細（汎用設計を引きずる原因）

私用の作業メモが必要なら、リポジトリ内別ファイル（例：[doc/CLAUDE_NOTES.md](doc/CLAUDE_NOTES.md)）または memory に書く。仕様書本体には混ぜない。

**資料の構成**:

- 決定内容（本体）→ 資料の上部
- 不確定項目 / TODO → **資料末尾にそれぞれまとめる**（各セクションに散らさない、本文に紛らせない）

関連 memory: `feedback_spec_not_worklog.md`

### ルール 7: 実装より先に役割分担を考える

設計判断・実装に入る前に、まず **「誰が何を持つか」（責務境界）** を整理する。フレームワーク選定（LlamaIndex 採用 / Neo4j 採用 等）や実装手段の議論はその後。

順序：

1. プロジェクトの判断契約・実行契約を **役割別に分解**する
2. 各役割を **誰が持つか**（Human / CLI / Orchestrator / LLM 用途別 / GRAG / Library）を決める
3. その後で、各役割を実装する **手段**（フレームワーク・ライブラリ・API）を選ぶ

順序を逆にしない。「LlamaIndex を採用する → そこに何を任せるか考える」ではなく、「役割分担を決める → 各役割を実装する手段を選ぶ」。

役割分担を最初に決めないと起きること：

- GRAG / GraphRAG ライブラリに **判断契約**まで委譲してしまう（GRAG は候補生成・検索基盤、判断主体ではない）
- LLM に「全部やらせよう」となる（用途別に分離すべき：**Extraction / Classification / Answer**）
- 「最初のユースケース」のドメイン語彙が標準スキーマに紛れ込む（汎用性が損なわれる）

SPEC-grag の役割分担（決定済）：

- **Human**: Purpose 確定、Concept 承認、Custom schema 承認、最終仕様判断
- **CLI / Orchestrator**: 変更検出、未承認 Concept 遮断、5 分類オーケストレーション、InjectionContext 構築
- **LLM (Extraction)**: ChapterAnchor の意味要素抽出、Concept 更新候補生成、Entity/Relation 候補抽出
- **LLM (Classification)**: GRAG 検索結果を課題に対して 5 分類（Validator の deterministic 検査を経る）
- **LLM (Answer)**: InjectionContext に拘束された回答生成（自由回答ではない）
- **GRAG subsystem**: 候補生成・検索・探索（判断はしない）
- **GraphRAG library**（LlamaIndex / Neo4j / Microsoft GraphRAG 等）: GRAG subsystem の内部実装候補に過ぎない

ChapterAnchor のような **共同責務** は、各役割を最初に分けてから組み立てる（CLI/Parser が文書構造、LLM (Extraction) が意味要素、GRAG Builder が保存）。

詳細な責務マトリクスは [doc/DESIGN.ja.md §1.1〜§1.6](doc/DESIGN.ja.md) を参照。

関連 memory: `feedback_role_separation_first.md`

## 過去の手戻り（同じ轍を踏まない）

過去セッションで犯した手戻りの教訓集は [doc/CLAUDE_NOTES.md](doc/CLAUDE_NOTES.md) に分離した。新セッション開始時に併せて参照する。

## 関連 memory（~/.claude/projects/-home-kazuki-public-html-spec-grag/memory/）

| ファイル | 内容 |
|---|---|
| `feedback_no_design_without_foundation.md` | 土台がない状態で設計を議論しない |
| `feedback_no_speculative_filling.md` | 推論カットの都合で推測で埋めない、整合性のため隠さない |
| `feedback_full_scope_enumeration.md` | 全項目列挙、未確認は最初から明示 |
| `feedback_verify_before_recommend.md` | 推奨を出す前に一次資料確認 |
| `feedback_no_minimum_cost_escape.md` | 「最小コスト」「MVP」を判断回避の逃げ口にしない |
| `feedback_structural_analysis.md` | 比較するなら最初に「軸」を立てる |
| `feedback_capture_findings.md` | 実装中の気付きを即座にメモする |
| `feedback_spec_not_worklog.md` | 資料には決定内容と TODO のみ、作業メモとしない |
| `feedback_role_separation_first.md` | 実装より先に役割分担を考える、責務境界を最初に整理する |
| `project_engine_pivot.md` | pivot 経緯と暫定採用スキーマ |
| `project_first_use_case.md` | ec-spoke.local 事例 |

memory はリポジトリ外（`~/.claude/` 配下）で揮発しうるため、本書（CLAUDE.md）と `doc/DESIGN.ja.md` を二重保険として運用する。
