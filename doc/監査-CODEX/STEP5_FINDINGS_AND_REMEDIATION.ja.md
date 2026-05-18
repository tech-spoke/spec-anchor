# Step 5 監査結果の整理と修正方針

作成日: 2026-05-15
作成者: Claude (監査整理担当)
前提成果物: Step 1-A 〜 Step 4 (`doc/監査-CODEX/STEP{1A,1B,1C,2,3,4}*.md`)
commit hash: `2aa49dd03416f14ae8b2c9791361a58112ff5611`

本書は監査プロセスシリーズ (Step 1-A 〜 Step 4) で観測された事実を**プロジェクトオーナー向けに整理**し、各問題点について運用上の影響と修正方針候補を提示する。Step 1-A 〜 Step 4 は Codex に作らせた「事実の構造化」を目的とし、判定や修正方針の判断は本書まで保留した。本書では Claude による暫定判定を加えるが、最終判定はプロジェクトオーナーに渡す。

---

## §1. Executive Summary

spec-grag の現状実装は、外部設計書 (`doc/EXTERNAL_DESIGN.ja.md`) と**大枠で整合している**。Step 4 §7 で 20 件の整合が確認され、Agent / CLI の責務分担、Section 単位処理、freshness gate、pending conflict 停止、graph 構造非標準経路、Source Retrieval Index / Related Sections の状態記録ファイル等の主要契約が実装と一致する。

ただし、業界標準 GRAG / RAG パターンとの整合性は**判定軸 7 件中 4 件のみ**で整合し、特に **GRAG の最低条件は不整合**である (Step 3 §2.3)。graph 構造の永続 store / traversal が実装に存在せず、業界標準資料 §7 が示す代替呼称「lightweight related-section retrieval」に分類される。実装は **Hybrid RAG + lightweight related-section retrieval** の複合呼称が最も近い。

外部設計書との整合では、Step 4 で**不整合 6 件 / 過剰 2 件 / 未確認 8 件**が観測された。重要なのは次の 3 件で、いずれも CLI 契約の漂流または不整合である:

1. **Qdrant collection 名の 3 段優先順位** — 外部設計書は単一 key、実装は 3 段 fallback
2. **`<課題プロンプト>` / `--conversation-context` の dead 引数** — 外部設計書は入力契約、実装は関数内で `del`
3. **`--use-cache` の挙動** — 外部設計書は deprecated 無指定と同等、実装は cache clear 条件に影響

これら 3 件は短期で修正判断が必要。残る不整合 3 件は中期、過剰 2 件は内部実装詳細として §12 対象外で扱う選択肢がある。未確認 8 件のうち 6 件は Step 2 が target 9 CLI 中心だったため、setup script や Conflict Review Item の decision enum 等の追加コード調査が必要。

**追加発見 (2026-05-18 確定): §8.4 CLI フラグ表の全 flag が仕様外実装 + gate probe サブコマンドも仕様外**:

ユーザー指摘「**結局テストで便利だからで全部生えた実装で本来はいらないもの**」を構造的に確認した結果、§8.4 の 7 行 (11 flag) **全てが LLM 由来の「念のため」追加実装**であることが確定:

- F-2: `--conversation-context` (Agent / LLM の責務を CLI が肩代わり)
- F-9: `--constraints*` / `--agent-constraints*` / `--constraints-file*` (Agent 自己点検の代行 + Conflict Review Item 適格性確認の重複)
- F-A: `--project-root` / `--root` (test / 開発便利性、template が使わない)
- F-7: `--freshness-json` / `--freshness-file` (test 用 stub、仕様 §3.3 で上書き経路は禁止)
- F-B: `--top-k` (動的調整余地、template が静的に同じ値を渡す)

整理後の §8.4 フラグ表は**完全に空になる**。`inject-search` の `<query>` と `inject-section` の `<section_id>` だけが位置引数として残る。

さらに **F-C** (2026-05-18 確定): `spec-grag inject` サブコマンド (gate probe) 自体も仕様外で、**サブコマンド全体が削除対象**。LLM が「事前 probe で gate チェック」という独自設計を入れたが、仕様 §3.3 / §2.8 / §6.3 は「各 `/spec-inject` 系コマンドが gate を持つ」を要求している。F-C は **過剰削除 + 不足追加**のパターン:

- 削除: `spec-grag inject` サブコマンド全体
- 追加: 各 inject-* (`inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts`) と realign に freshness / pending conflict / watcher gate を組み込み

これは「**シンプルに戻したら、本来必要な部分が見えてくる**」例で、監査の二段構え（過剰削除 + 本来必要な部分をちゃんと作る）の最初の実例。

加えて **F-D** (2026-05-18 確定): `inject-purpose` / `inject-chapters` が artifact 全体を返してコンテキスト圧迫の問題。仕様 §3.4「Source Specs を丸ごと投入しない」原則と矛盾。artifact ごとの性格で分けて整理:

- **Purpose**: 全文注入（目的そのもので短い）
- **Core Concept**: path 返却（大きくなる可能性）
- **chapter_anchors**: path 返却
- **conflict_review_items**: 全件返却（resolved + stale でないものに絞られて件数限定）

加えて **CLI 戻り値に Agent への指示 (guidance) をハードコードしない**原則を確立。template / SKILL に「path を Read で読んで抽出せよ」と書く。これは責務分離（CLI = データ取得 / template = Agent への指示）を明確化。

整理後の CLI 構造は「CLI = LLM が制約を生成するためのヒント提供」というユーザーの本来のフローと完全整合する最小形。

「SPEC-grag」という製品名と業界用語 GRAG の対応は外部設計書に記述がなく (Step 4 §8-1)、これはプロジェクトの方向性に関わる戦略的判断対象。

**監査者自身のバイアスの自己観察 (§6.4)**: 本監査の主要 finding に「LLM の念のため残す引力」(F-2 / F-9 等) があるが、監査者である Claude 自身も監査中に同じ引力を発動した。F-A / F-B の初回判定で「実装は残す」「flag は残す」と中途半端な両論併記をした。ユーザーの「**今回もあなたはいくつか残そうとする引力が働いている**」という指摘で初めて、完全削除が一意に正解と判定し直した。本監査は「LLM 監査 + ユーザー判断主体性」の組み合わせで初めて成立した。

---

## §2. 問題点リスト

### §2.1 不整合（外部設計書と実装の食い違い、6 件）

| # | 問題 | 重要度（暫定） | 運用上の影響 |
|---|---|---|---|
| F-1 | Qdrant collection 名の 3 段優先順位 | **High** | 設定の漂流。`vector_store.section_collection` を設定したつもりが `retrieval.section_collection` で上書きされる、または逆。デバッグ困難。後方互換性の意図が不明 |
| F-2 | `<課題プロンプト>` / `--conversation-context` dead 引数 + realign の仕様外実装 | **High** | 外部設計書通りに渡してもサイレント無視。さらに realign 内に `_needs_clarification` / `_default_targets` / `_conversation_text` 等の**仕様外実装**が紛れ込んでおり (§3.2 詳細)、Agent / LLM の責務を CLI が肩代わりしている経路がある。template が `--conversation-context` を渡さないため実運用では dead path だが、保守性とコード理解の混乱の元 |
| F-9 | **「制約検証」操作全体が仕様外実装** | **High** | §8.4 の「制約検証」操作 (`spec-grag inject "<task>" --constraints '<JSON>'`) は CLI が制約の真偽を判定できない (意味理解が必要)。実態は (a) JSON schema 検証 (Agent 自己点検の代行、§8.5 で Agent 責務と明記) + (b) Conflict Review Item 適格性確認 (`inject-conflicts` で既に実施済みの重複) の 2 つで、いずれも CLI 必須ではない。仕様 §5.3「CLI は最終判断主体ではない」と矛盾。F-2 と同パターンの「LLM 由来の念のため safety net」(§3.10 詳細) |
| F-A | `--project-root` / `--root` flag が仕様外 | **High** | template / SKILL のどこにも使われておらず、Agent CLI 経由ではカレントディレクトリ前提で動作。test は Python API で代替可能。「test 便利性」を口実に CLI flag として残された LLM 由来の仕様外実装。仕様 §5.3 に照らして「呼び出し元 path の解釈」も CLI が肩代わりする必要なし (§3.11 詳細) |
| F-7 | `--freshness-json` / `--freshness-file` flag が仕様外 | **High** | 仕様 §3.3「freshness は `/spec-core` または `spec-grag-watch` が生成し、`/spec-inject` / `/spec-realign` は読む」と明記、上書き経路は仕様にない。template / SKILL では使われず、test 用 stub が用途。Python API で代替可能。F-9 と同パターンの「LLM 由来の念のため上書き経路」(§3.12 詳細) |
| F-B | `--top-k` flag が仕様外 | **High** | 設定 `[retrieval].section_final_top_n` で固定可能、template は常に `--top-k 8` を静的に渡しており「動的調整」は使われていない。test は Python API で代替可能。「動的調整余地」を口実に CLI flag として残された LLM 由来の仕様外実装 (§3.13 詳細) |
| F-C | `spec-grag inject` サブコマンド (gate probe) が仕様外 + 各 inject-* の gate 不足 | **High** | 仕様 §3.3 / §2.8 / §6.3 は「`/spec-inject` 系全体が freshness / pending conflict / watcher 実行中で停止」を要求。現状は `spec-grag inject` (gate probe) のみが gate を持ち、`inject-search` / `inject-section` 等は gate を持たない。**LLM が「事前 probe を作って事前確認する」という独自設計を入れたが、仕様にこの操作はない**。各 inject-* が gate を持てば事前 probe は不要 (§3.15 詳細) |
| F-D | `inject-purpose` / `inject-chapters` が artifact 全体を返してコンテキスト圧迫 | **High** | 仕様 §3.4「Source Specs を丸ごと投入しない」原則と矛盾。`inject-purpose` は Purpose + Core Concept 全文、`inject-chapters` は chapter_anchors.json 全体を返す。Core Concept / chapter_anchors は大きくなる可能性があり、Agent コンテキストを圧迫。Purpose は短く目的そのものなので全文返却で良い (§3.16 詳細) |
| F-3 | `--use-cache` の挙動（廃止予定機能の残骸） | **Medium** | deprecated と書きながら cache clear 条件に影響し、`--all` + `--use-cache` で `--all` 単独と異なる挙動になる。template / test / 利用実態すべて 0 件で完全な dead 機能 |
| F-4 | `/spec-inject` の人間向け通常出力 | **Medium** | 外部設計書は読みやすい構造を契約、実装は JSON。Agent 側で表示変換が必要だが、その責務が外部設計書に書かれていない |
| F-5 | 設定項目表に `vector_store.section_collection` / `vector_store.collection` 未列挙 | **High** | F-1 と同根。設定項目表が実装と一致しない |
| F-6 | 環境変数表に debug env var 未列挙 | **Low** | `SPEC_GRAG_DEBUG_PROVIDER_INVOCATION` / `SPEC_GRAG_DEBUG_RELATED_PROMPT` が外部設計書に出ない。debug 用なので影響小 |

**重要度の根拠**:

- **High**: ユーザーが外部設計書通りに使うと実装が想定と異なる挙動を取る箇所。デバッグ困難 / 信頼性低下
- **Medium**: 契約と実装の食い違いがあるが、CLI 利用者の主要経路には直接の影響が小さい
- **Low**: 内部 debug や運用補助で、誤動作の影響範囲が限定的

### §2.2 過剰（実装にあるが外部設計書に契約なし、2 件）

| # | 問題 | 重要度（暫定） | 運用上の影響 |
|---|---|---|---|
| E-1 | Section embedding text の構成（raw body 不含、Summary/Search Keys/Identifiers から生成） | **Low** | 外部設計書 §12 が embedding provider 実装と hybrid retrieval scoring を対象外と明示している。この粒度なら過剰だが内部最適化として扱える |
| E-2 | `_debug_*.jsonl`（env var で append、読込 CLI なし） | **Low** | デバッグ用ファイル。env var を設定すると `.spec-grag/state/` に append される。利用者が意図せずファイルが増える可能性はあるが、env var 設定時のみ |

### §2.3 未確認（Step 2 範囲限定で判定不能、8 件）

| # | 問題 | 重要度（暫定） | 追加調査の必要性 |
|---|---|---|---|
| U-1 | 方式呼称「SPEC-grag」と業界用語の対応 | **High（戦略）** | プロジェクトの位置づけ判断。コード調査ではなく人間判断 |
| U-2 | fake provider の状態表現（CoreResult / freshness / diagnostics への表れ方） | **Medium** | コード追加調査で確定可能（`spec_grag/core.py` / `freshness.py` の fake provider 経路追跡） |
| U-3 | `source_section_id` の形式（`<file_path>#<heading_slug>`）と一意性 | **Medium** | コード追加調査で確定可能（`section_parser.py` の id 生成と uniqueness 検査） |
| U-4 | setup script の実装事実 | **Medium** | Step 2 が target 9 CLI 中心。setup script について Step 1-B 相当のフロー追跡が必要 |
| U-5 | Conflict Review Item decision enum 全件対応 | **Medium** | コード追加調査で確定可能（`conflict_review.py` の `apply_conflict_decision` 経路） |
| U-6 | config の親ディレクトリ探索なし | **Low** | コード追加調査で確定可能（`config.py:163-170` の `tomllib` load 経路） |
| U-7 | 外部設計書 §12 対象外範囲と Step 2 実装事実の境界 | **Medium** | E-1 / E-2 と関連。外部契約に含めるか §12 対象外で線引きするかの判断 |
| U-8 | 判定対象から外した節（Purpose / Core Concept 中身） | **N/A** | human-managed の正本内容なので機械判定対象外 |

---

## §3. 修正方針候補

各問題について複数の選択肢を提示する。選択肢間のトレードオフを並べて、**最終判定はプロジェクトオーナーに委ねる**。

### §3.1 F-1: Qdrant collection 名の 3 段優先順位

**現状**: コードは `retrieval.section_collection` → `vector_store.section_collection` → `vector_store.collection` → `"spec_grag_section"` の順で読む ([STEP2_METHOD.ja.md:240](doc/監査-CODEX/STEP2_METHOD.ja.md#L240))

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **実装を単一 key に整理**: `vector_store.*collection` への参照を削除し、`[retrieval].section_collection` のみを読む | 後方互換性損失。既存ユーザーの config に `vector_store.section_collection` を書いている場合は移行が必要。実装は単純化 |
| B | **外部設計書に 3 段優先順位を追記**: 互換 key として明示。各 key の優先順位と deprecation 状況を §10.2 設定項目表に追加 | 契約の複雑化。ただし実装の事実を契約に反映するので、漂流の解消 |
| C | **互換 key を deprecated として段階廃止**: 外部設計書に「`vector_store.section_collection` は deprecated、将来削除予定」と記述。実装で警告を出す | A と B の中間。段階的移行が可能。実装に warning 経路を追加する工数 |

**Claude 推奨（当初）**: C（段階廃止）。理由: A は後方互換性損失でユーザー影響大、B は契約の複雑化を契約変更で容認することになる。

**git history による補強調査 (2026-05-16)**:

3 段優先順位の起源を git log で追跡した結果、**意図的な互換性レイヤーではなく、移行残骸である**ことが確定した:

| 時系列 | commit | 何が起きたか |
|---|---|---|
| ① | `d856125` (2026-05-06) "Finalize lightweight SPEC-grag implementation" | `VectorStoreConfig.collection` を最初の dataclass key として追加。default `"spec_grag_source"`（chunk-level 時代） |
| ② | `fba96fb` (Phase R-0) | `RetrievalConfig.section_collection = "spec_grag_section"` を追加。chunk-level → section-level への方式変更 |
| ③ | `455ea18` (artifacts: eradicate chunk-level) | 移行期に `[vector_store].section_collection` の raw config read を新規追加。旧 `[vector_store].collection` 読み経路はコメントアウト |
| ④ | `90a60db` "fix §10.1 settings table + **remove dead chunk/collection fields**" | dataclass `VectorStoreConfig.collection` を削除。**コミットメッセージ "dead fields" が示すように、削除対象と認識されていた**。ただし raw config read 経路は完全には掃除されなかった |

**Claude 推奨（更新）**: **A（実装を単一 key に整理）**。理由: 90a60db で "dead fields" と認識されており、後方互換性として意図的に残したものではなく**削除し残し**である。

**プロジェクトオーナー判断 (2026-05-16): A 採用**。

### §3.2 F-2: `<課題プロンプト>` / `--conversation-context` dead 引数

**現状**: 外部設計書 §8.2 / §8.4 / §9.4 で入力契約として記述。実装は `spec_grag/inject.py:91` で `del task_prompt, prompt, conversation_context` ([STEP2_METHOD.ja.md:236, 254](doc/監査-CODEX/STEP2_METHOD.ja.md#L236))

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **外部設計書を「Agent / LLM 専用入力」に変更**: CLI 経由で渡されても CLI 実装は消費しないと明示。Agent 側で会話区間解釈に使う | 外部設計書 §5.3「CLI は最終判断主体ではない」と整合する。CLI の API surface が縮小される |
| B | **実装を変更して CLI が消費**: freshness gate / constraints validation の入力として CLI 内部で使う | CLI が「主導権なし」原則と矛盾する可能性。Agent / LLM の責務が CLI へ流出 |
| C | **CLI 引数として残し、未使用と明示**: 外部設計書に「CLI 実装では受け取るが処理しない」と記述。API 互換性のために残す | 引数として存在するが意味なし、混乱の源。長期的には dead code |

**Claude 推奨（当初）**: A（外部設計書を「Agent 専用入力」に変更）。

**追加調査結果 (2026-05-18)**:

仕様の再確認とコード追跡で、当初の F-2 認識に重大な見落としがあったことが判明した。

**仕様（外部設計書）の確定**:

| 該当節 | 記述 | 意味 |
|---|---|---|
| §8.4 表 [行 776](doc/EXTERNAL_DESIGN.ja.md#L776) | `--conversation-context <text>` 会話区間文字列。**Agent / LLM が解釈する補助入力** | CLI は消費しない契約 |
| §9.1 [行 854](doc/EXTERNAL_DESIGN.ja.md#L854) | `<課題プロンプト>` 省略時、**Agent / LLM は**会話区間から中心課題を解釈、特定できない場合は確認を求める | 中心課題特定も clarification 判断も Agent / LLM の責務 |
| §9.2 [行 858-864](doc/EXTERNAL_DESIGN.ja.md#L858) | `/spec-realign [<課題プロンプト>] -> freshness gate -> 8.3 と同じ手順で制約を生成する -> 生成した制約に従って回答または修正案を作る -> RealignResult を出力する` | 制約生成・回答生成は Agent / LLM（§8.3）の作業、CLI は freshness gate と RealignResult 構造化のみ |
| §5.3 責務境界 | CLI は最終判断主体ではない | 全体方針 |

つまり **CLI は `<課題プロンプト>` も `--conversation-context` も消費しない契約**。inject の `del` は契約通りの正しい実装。

**realign.py の仕様外実装の発見**:

`realign.py` 内で次が `<課題プロンプト>` / `conversation_context` を使っているが、これらは**仕様外実装**:

| 仕様外箇所 | 何をしているか | 仕様上の責務主体 |
|---|---|---|
| [realign.py:93](spec_grag/realign.py#L93) `_conversation_text(conversation_context)` | context をテキスト化 | **不要**（CLI 消費しない） |
| [realign.py:122, 138](spec_grag/realign.py#L122) `_needs_clarification(task_text, context_text)` | task / context が空なら clarification 要求 | **Agent / LLM** (§9.1) |
| [realign.py:159](spec_grag/realign.py#L159) `structure_realign_answer(..., conversation_context=context_text)` | answer 構造化に渡す | **Agent / LLM** (§8.3 / §9.2) |
| [realign.py:631-635](spec_grag/realign.py#L631) `_needs_clarification` 関数本体 | safety net | **Agent / LLM** (§9.1) |
| `_default_targets` 関数 | targets が空なら task / context から default 構築 | **Agent / LLM** (§9.3 で Answer 4 区分は Agent が区別) |

これらは全て `d856125 "Finalize lightweight SPEC-grag implementation"` で追加。「軽量化確定」commit で**仕様外実装が紛れ込んだ**構造。

**Agent CLI template の調査**:

`spec_grag/templates/.claude/commands/spec-inject.md`、`spec-realign.md`、`.codex/skills/spec-grag/SKILL.md` の **3 つ全てで `--conversation-context` の言及ゼロ**。Agent CLI は会話区間を自分で読んで `$TASK` 引数に集約する設計。realign.py の仕様外実装は実運用で常に dead path として呼ばれていない。

**Claude 推奨（更新）**: **A-2'（`<課題プロンプト>` / `--conversation-context` 両方を CLI 実装と外部設計書から完全削除、realign 内の clarification / default targets ロジックも仕様外実装として削除）**。

**プロジェクトオーナー判断 (2026-05-18): A-2' 採用**。

**Claude の前回応答の訂正記録**:

私は当初「realign では `conversation_context` を使っている」と判定し、F-2 を「dead 引数だが realign で利用あり」と擁護した。これは仕様の読み込み不足。§5.3 / §8.4 行 776「Agent / LLM が解釈する補助入力」を厳密に読めば、CLI 消費は仕様で明示的に否定されており、realign.py の利用箇所は仕様外実装。Step 4 §2.8 で「両論併記」に逃げて人間判断に丸投げしたのも誤り（仕様で一意に決まる事項だった）。

**「なぜ LLM が仕様外実装を生成するか」への所見**:

本件は F-1（Qdrant collection 3 段優先順位）、F-3（`--use-cache`）と同じパターン。LLM が仕様外実装を生成する典型的な原因:

1. **「念のため」志向**: 想定外入力に対する fallback / safety net を過剰に入れる
2. **仕様の最小性を理解しない**: 「もっと丁寧に処理すべき」と判断し、シンプル実装より防御的実装を選ぶ
3. **入力 = CLI 消費の短絡**: 仕様書で「入力」と書かれていれば「CLI が消費する」と解釈、§5.3 や §8.4 行 776 のような責務境界記述との矛盾に気付かない
4. **API surface への過剰配慮**: 「引数として残せば将来使える」「テスト容易性」で不要な経路を残す
5. **監査側 LLM の見落とし**: 別の LLM（Codex / Claude）が監査しても「コード上に経路があれば機能している」と判定して仕様外実装を擁護してしまう（私の前回応答がまさにこれ）

これは spec-grag が直面している「LLM が仕様外実装を生成し、別の LLM が監査しても見落とす」問題の典型例。

### §3.3 F-3: `--use-cache` の挙動

**現状**: 外部設計書 §7.1 で「`--use-cache` は deprecated (挙動は無指定と同等)」、実装は `run_full and not use_cache` のとき cache 削除 ([STEP2_METHOD.ja.md:54](doc/監査-CODEX/STEP2_METHOD.ja.md#L54))

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **外部設計書を実装に合わせる**: 「`--use-cache` は `--all` 時に cache を保持する flag」と記述 | 契約が事実を反映する。ただし「deprecated」という記述を外す or 「deprecated だが使われている」と明示 |
| B | **実装を no-op に変更**: 外部設計書通り、`--use-cache` の処理を削除 | 実装が契約に追従する。flag を残すなら deprecation warning を出すと利用者に伝わる |

**Claude 推奨（当初）**: B（実装を no-op）。

**追加調査結果 (2026-05-18)**:

仕様と実装の利用実態を再確認した結果、より厳しい削除方針が妥当と判明。

**仕様の確定**:

- 外部設計書 §7.1 [行 502](doc/EXTERNAL_DESIGN.ja.md#L502): 「`--rebuild` は `--all` を含意する。`--use-cache` は **deprecated (挙動は無指定と同等)** 。」
- §7.2 [行 517-525](doc/EXTERNAL_DESIGN.ja.md#L517-L525) の CLI フラグ表に **`--use-cache` は未掲載**（正規 flag リストから除外済み）

**実装の現状（仕様と矛盾）**:

| ファイル | 該当箇所 | 内容 |
|---|---|---|
| `cli.py:75-78` | argparse 登録 | help 文字列に "(deprecated)" と記述 |
| `cli.py:361` | wrapper | `use_cache=args.use_cache` を `run_spec_core` に渡す |
| `core.py:59, 201` | 引数定義 | `use_cache: bool = False` |
| `core.py:284` | `if run_full and not use_cache:` | **`--all` + `--use-cache` で cache 削除をスキップ** |
| `core.py:385, 727` | `rebuild_all=run_full and not use_cache` | section_metadata / chapter_anchors の rebuild_all 判定に影響 |

つまり実装は **「無指定と同等」ではなく機能している**。仕様の deprecated 記述と矛盾。

**利用実態の調査**:

| 経路 | `--use-cache` の利用 |
|---|---|
| Agent CLI template (`.claude/commands/`, `.codex/skills/`) | **使っていない** (grep 結果 0 件) |
| tests/ | **テストなし** (grep 結果 0 件) |
| 外部設計書 §7.2 フラグ表 | **未掲載** |
| 外部設計書 §7.1 | deprecated と明記 |

機能としてコードにあるが、誰も使わず、テストもなく、仕様でも廃止予定。**完全な dead 機能**。

**選択肢 C の追加**:

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| ~~A~~ | ~~外部設計書を実装に合わせる~~ | deprecated の趣旨と矛盾、却下 |
| B | 実装を no-op 化、flag は warning 付きで残す | 後方互換性。ただし誰も使っていない以上、warning を出す相手がいない |
| **C** | **`--use-cache` を完全削除** (argparse / 引数 / 関連ロジック / 仕様書記述すべて) | 影響範囲最小（test も template も既に未使用）。F-1 / F-2 と方針統一 |

**Claude 推奨（更新）**: **C（完全削除）**。理由: B (no-op + warning) を残す価値が小さい（誰も使っていない、warning を出す相手がいない）。F-1 / F-2 と方針統一して残骸を完全削除するのが筋。

**プロジェクトオーナー判断 (2026-05-18): C 採用**。

**F-1 / F-2 / F-3 の比較**:

| 観点 | F-1 (collection 3 段) | F-2 (`--conversation-context`) | F-3 (`--use-cache`) |
|---|---|---|---|
| 仕様での扱い | 単一 key のみ記述 | Agent 解釈の補助入力 | **deprecated (挙動は無指定と同等)** |
| 性格 | 方式変更の残骸 | 仕様外実装（LLM 由来） | **廃止予定機能の残骸** |
| 実装の現状 | 3 段 fallback で機能 | inject 側は dead、realign は仕様外実装 | 機能している（仕様と矛盾） |
| test | あり (3 段優先順位検証、書き換え必要) | なし | **なし** |
| template | 渡さない | 渡さない | 渡さない |
| 削除影響 | 中（既存 config の migration 必要） | 中（realign 仕様外実装も削除） | **小**（test も template もないので影響最小） |

F-3 は F-1 と同類の「廃止予定機能の残骸」パターンだが、**影響範囲が最も小さい**ため最初に着手しやすい修正。

### §3.4 F-4: `/spec-inject` の人間向け通常出力

**現状**: 外部設計書 §8.5 で「人間に見える出力は、内部 JSON ではなく読みやすい構造」、実装は `_run_inject_from_args` が JSON を stdout 出力 ([STEP2_METHOD.ja.md:53, 122-124](doc/監査-CODEX/STEP2_METHOD.ja.md#L53))

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **外部設計書を「CLI は JSON、Agent CLI が表示変換」に分離**: 責務分離。CLI は機械可読出力、表示変換は Agent CLI / skill 側 | 責務境界が明確。外部設計書の「人間に見える出力」記述を Agent CLI 側に移す必要 |
| B | **実装に human-readable formatter を追加**: CLI 出力に 2 mode (JSON / human) を実装 | CLI の責務が増える。`--format` flag 等で切替 |
| C | **slash command / skill 側で表示変換することを外部設計書に明示**: 「CLI 出力は JSON、`.claude/commands/` / `.codex/skills/` で人間向け整形」と書く | A の具体化。実装変更不要 |

**Claude 推奨**: **C（slash command 側で整形と明示）**。理由: 既に `spec_grag/templates/.claude/commands/` と `.codex/skills/` の template が存在する ([STEP1A_INVENTORY.ja.md §0 行 75-80 周辺](doc/監査-CODEX/STEP1A_INVENTORY.ja.md))。これらが Agent 側の表示層と位置づけられているはず。外部設計書に「CLI 出力は JSON、表示変換は command/skill template が行う」と明示すれば、契約と実装が一致する。

### §3.5 F-5 / F-6: 設定項目表 / 環境変数表の未列挙

**F-5: 設定項目表に `vector_store.*collection` 未列挙** — F-1 と同根。

**2026-05-16 確定**: F-1 で選択肢 A（実装を単一 key に整理）が採用されたため、F-5 は**自動解決**する。`vector_store.section_collection` / `vector_store.collection` は実装から削除されるため、外部設計書 §10.2 への追記は不要。

**F-6: 環境変数表に debug env var 未列挙** — E-2 と同根。

| 選択肢 | 内容 |
|---|---|
| A | 外部設計書 §10.2 / §10.3 に追記（E-2 の選択肢 A と連動） |
| B | 外部設計書 §12 対象外として明示（E-2 の §12 化に連動） |

### §3.6 E-1: Section embedding text の構成

**現状**: `build_section_embedding_text` は heading_path / summary / search_keys / identifiers を join し raw body 不含 ([STEP2_METHOD.ja.md:239](doc/監査-CODEX/STEP2_METHOD.ja.md#L239))

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **外部設計書 §12 対象外として明示**: 「embedding 入力 text の構成は対象外」と書く。現状の §12 に既に「embedding provider 実装」「hybrid retrieval scoring」があるので追加しやすい | 内部最適化として扱う。外部利用者に embedding 品質の根拠が見えない |
| B | **外部設計書に内部方式として記述**: 「Section embedding text は heading_path / summary / search_keys / identifiers から構成する」と §4.1 等に追加 | 透明性が上がる。外部設計書のスコープが広がる |
| C | **現状のまま記述しない**: §12 にも追加しない | 最小工数だが、過剰実装として残り続ける |

**Claude 推奨**: **A（§12 対象外として明示）**。理由: 外部設計書 §12 は既に embedding provider 実装を対象外としており、その粒度の整合上、embedding 入力 text の構成も内部方式として扱うのが自然。

### §3.7 E-2: `_debug_*.jsonl`

**現状**: `SPEC_GRAG_DEBUG_PROVIDER_INVOCATION` / `SPEC_GRAG_DEBUG_RELATED_PROMPT` の env var で append ([STEP2_METHOD.ja.md:94-95](doc/監査-CODEX/STEP2_METHOD.ja.md#L94-L95))

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **環境変数表 §10.3 に追記**: debug env var を契約として明示 | 透明性が上がる。debug 用 env var が増えると追記が必要 |
| B | **§12 対象外として明示**: 「内部調査用 debug ファイルは対象外」と書く | 最小工数で運用上の問題なし |

**Claude 推奨**: **B（§12 対象外として明示）**。理由: debug 用 env var はリリース機能ではなく開発者向け。`SPEC_GRAG_FAKE_*` のような test 用 env var とは区別される。§12 対象外として線引きする方が契約が安定する。

### §3.8 U-1: 方式呼称「SPEC-grag」と業界用語の対応

**現状**: 外部設計書には GRAG / GraphRAG / lightweight retrieval 等の業界用語による方式呼称が出ない (Step 4 §2.2)。「SPEC-grag」は製品名として使われている。業界標準資料 §7 によれば、graph 構造の永続 store / traversal がない現状は「lightweight related-section retrieval」に分類される (Step 3 §2.3)。

これは **プロジェクトの位置づけに関する戦略的判断**であり、修正方針の選択肢が複数ある:

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **「SPEC-grag」を製品名として位置づけ、業界用語比較を外部設計書に追記**: 「SPEC-grag は Hybrid RAG + lightweight related-section retrieval に分類される」と §2 等に書く | 業界標準への位置づけが明確になる。ただし「SPEC-grag」を「GRAG」と読む読者の期待とズレる可能性 |
| B | **実装を業界標準 GRAG に拡張**: graph 構造の永続 store / traversal を追加し、業界用語通りの GRAG にする | 大規模実装変更。Purpose の「軽量化」方針 (`doc/EXTERNAL_DESIGN.ja.md:20`) と矛盾 |
| C | **「SPEC-grag」を独自呼称として外部設計書で定義**: 「SPEC-grag は業界用語の GRAG とは異なる、本プロジェクト固有の方式」と明示 | プロジェクトの独自性を主張。業界比較から離れる |
| D | **現状のまま、業界用語との対応を記述しない**: 外部利用者が判断 | 最小工数。ただし「GRAG」と読まれる可能性が残る |

**Claude 推奨**: **A（業界用語比較を追記、または C と組み合わせ）**。理由: Purpose で軽量化方針が明示されている以上、業界標準 GRAG への拡張 (B) は方針と矛盾。現状の方式は業界標準資料 §7 で明示的に「lightweight related-section retrieval」と分類できる。A で位置づけを明示すれば、利用者の期待ズレを防げる。

### §3.9 未確認項目（U-2 〜 U-7）の追加調査方針

U-1（SPEC-grag 呼称）と U-8（Purpose / Core Concept）以外の 6 件は、追加コード調査で確定できる:

| # | 追加調査内容 | 必要な範囲 |
|---|---|---|
| U-2 | fake provider の status / diagnostics / freshness への表れ方 | `spec_grag/core.py` の fake provider 経路、`spec_grag/freshness.py` の diagnostics 構築 |
| U-3 | `source_section_id` 形式 `<file_path>#<heading_slug>` と一意性 | `spec_grag/section_parser.py` の id 生成 |
| U-4 | setup script の実装事実 | Step 1-B 相当のフロー追跡を `spec_grag/project_setup.py` に対して実施 |
| U-5 | Conflict Review Item decision enum 全件対応 | `spec_grag/conflict_review.py` の `apply_conflict_decision` 経路 |
| U-6 | config の親ディレクトリ探索なし | `spec_grag/config.py:163-170` の `tomllib` load 経路 |
| U-7 | 外部設計書 §12 対象外範囲の整理 | E-1 / E-2 の解決と連動 |

これらは「Step 6: 追加調査」として別工程で実施するか、修正方針確定時に各項目について coverage を確認するか、選択肢がある。

### §3.10 F-9: 「制約検証」操作全体が仕様外実装

**現状**: 外部設計書 §8.4 [行 769](doc/EXTERNAL_DESIGN.ja.md#L769) で「制約検証 | `spec-grag inject "<task>" --constraints '<JSON>'`」が CLI 操作として記述。実装は [inject.py:154-263](spec_grag/inject.py#L154-L263) の `validate_constraints` で次を行う:

| 検証内容 | 該当行 |
|---|---|
| (1) required fields の存在 (`statement` / `evidence_origin` / `evidence_ref` / `support_refs`) | [167-173](spec_grag/inject.py#L167-L173) |
| (2) 必須 string field の非空 | [175-184](spec_grag/inject.py#L175-L184) |
| (3) `evidence_origin` enum (`SUPPORT_ONLY` を final にしない、`FINAL_EVIDENCE_ORIGINS` のみ許可) | [186-197](spec_grag/inject.py#L186-L197) |
| (4) `support_refs` が list 型 | [199-204](spec_grag/inject.py#L199-L204) |
| (5) Conflict Review Item の動的状態確認 (`status=resolved` / stale でない / `valid_scope`) | [216-263](spec_grag/inject.py#L216-L263) |

**問題の本質**: ユーザー指摘「CLI が単独で制約検証なんてできるとは思えない」が構造的に正しい。

CLI ができるのは**形式チェック + artifact 状態確認**のみで、以下は**意味理解が必要**なため CLI には不可能:

- 制約の内容が課題に適切か
- statement と evidence_ref が論理的に対応しているか
- 複数の制約が互いに矛盾していないか
- 制約のカバレッジが課題に対して十分か

これらは仕様 §5.3 で **Agent / LLM の責務**と明記されている。

**(1)〜(4) の構造検証は Agent の自己点検の重複**:

仕様 §8.5 [行 812-826](doc/EXTERNAL_DESIGN.ja.md#L812-L826):

> Agent / LLM は ... 制約を提示する場合は `statement`、`evidence_origin`、`evidence_ref` を欠かしてはいけない。

**仕様は「Agent / LLM が」構造を守ると明記**。CLI が再検証する根拠は仕様にない。

**(5) の Conflict Review Item 適格性確認は `inject-conflicts` で実施済みの重複**:

Agent は `spec-grag inject-conflicts` を呼ぶ時点で、CLI が `resolved` + stale でないものだけを `resolved_conflict_items` として返している ([STEP1B_FLOWS.ja.md:312](doc/監査-CODEX/STEP1B_FLOWS.ja.md#L312))。Agent が `excluded_conflict_items` を `evidence_origin = "Conflict Review Item"` に使わない限り、(5) の再検証は冗長。

利用実態調査:

| 経路 | `--constraints` の利用 |
|---|---|
| Agent CLI template (`.claude/commands/spec-inject.md`, `spec-realign.md`) | 使う（手順 6 で `spec-grag inject "$TASK" --constraints '<json-array>'` を実行） |
| `.codex/skills/spec-grag/SKILL.md` | 使う（同様） |
| tests/ | あり (`tests/test_spec_inject.py` 等で validation を検証) |
| 外部設計書 §8.4 | あり |

つまり「**実装も template も test も使っているが、責務的に CLI のものではない**」状態。F-2 と同じパターンで、LLM が「念のため CLI で検証」を入れた構造。

**選択肢**:

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **「制約検証」操作全体を CLI から削除**: `validate_constraints` 関数削除、`--constraints` argparse 削除、Agent template / SKILL で仕様 §8.5 を強く指示する方向に変更 | 抜本的整理。仕様 §5.3 と完全整合。template / test の改訂が広範囲 |
| B | **(5) Conflict Review Item 適格性確認だけ残し、(1)〜(4) を削除**: CLI 検証の責務を「Conflict Review Item 適格性確認」のみに縮小 | (5) も `inject-conflicts` で実施済みの重複なので、残す根拠が薄い |
| C | **現状維持**: 仕様外実装と認識しつつ削除しない | F-2 と同じ仕様外実装を放置することになる |

**Claude 推奨**: **A（「制約検証」操作全体を CLI から削除）**。

理由:

- 仕様 §5.3「CLI は最終判断主体ではない」と完全整合
- (1)〜(4) は仕様 §8.5 で Agent 責務と明記、CLI 検証は重複
- (5) は `inject-conflicts` で実施済みの重複
- F-2 (`_needs_clarification` / `_default_targets` 削除) と同じパターンで方針統一

**プロジェクトオーナー判断 (2026-05-18): A 採用**。

**「LLM が制約検証を実装した動機」の所見**:

LLM の学習データには「JSON schema validation」「argparse validation」「constraints validation」のパターンが豊富にある。LLM は「constraints が来たら validate する」という慣習的な発想で実装した。しかし:

- 「validation」という言葉が**形式チェック / 真偽チェック / 適格性確認**の 3 つを混同して指す
- spec-grag では「真偽チェック」は LLM の責務であり CLI には不可能
- にもかかわらず「validation という言葉の広さ」で形式チェックと真偽チェックを混同したまま実装された

F-2 / F-9 はいずれも **「LLM が広い意味の言葉で念のため safety net を入れた」** 例。spec-grag の Purpose（軽量化、Agent / LLM 主導）を貫くには、こうした LLM 由来の safety net を**構造的に検出し削除する仕組み**が必要。Step 5 §6.3 で追加した「仕様外実装の検出を Step 4 の明示的な監査軸として追加」がこれに対応する。

### §3.11 F-A: `--project-root` / `--root` flag が仕様外

**現状**: 外部設計書 §8.4 [行 775](doc/EXTERNAL_DESIGN.ja.md#L775)「対象プロジェクトの root を指定する。既定はカレントディレクトリ」。実装は全 inject 系サブコマンドと core / realign / watch で argparse に `default="."` で登録 ([cli.py:79, 98, 122, 134, 145, 153, 161, 168, 216 等](spec_grag/cli.py))。

**利用実態**:

| 経路 | 利用 |
|---|---|
| Agent CLI template (`.claude/commands/`, `.codex/skills/`) | **使っていない** (grep 結果 0 件、カレントディレクトリ前提) |
| tests/ | あり (test で `--project-root <tmp>` を使う) |

**仕様 §5.3「CLI は最終判断主体ではない」との関係**:

「呼び出し元の path 解釈」も CLI が肩代わりする必要なし。Agent / shell の責務（`cd <project_root> && spec-grag ...` で十分）。

**選択肢**:

| 選択肢 | 内容 |
|---|---|
| A | **完全削除** (argparse + 実装 + 設計書 §8.4 から) |
| B | 実装は残すが設計書 §8.4 から削除 |
| C | 現状維持 |

**Claude 推奨（当初の引力）**: B（実装は残すが §8.4 から削除、test 便利性のため）

**プロジェクトオーナー判断 (2026-05-18) と推奨更新**: **A（完全削除）**。理由: 「test 便利性」は Python API (`run_spec_core(project_root=...)`) で代替可能で、CLI flag として残す根拠にならない。template / SKILL のどこにも使われていない以上、production 契約には不要。

### §3.12 F-7: `--freshness-json` / `--freshness-file` flag が仕様外

**現状**: 外部設計書 §8.4 [行 779-780](doc/EXTERNAL_DESIGN.ja.md#L779-L780)「freshness report の上書き JSON / JSON ファイル」。実装は [inject.py:93-100](spec_grag/inject.py#L93-L100) で `freshness_report` 引数を `_read_freshness_artifact` より優先する。

**仕様 §3.3 との矛盾**: 仕様 §3.3 [行 191-206](doc/EXTERNAL_DESIGN.ja.md#L191-L206) で「freshness は `/spec-core` または `spec-grag-watch` が生成し、`/spec-inject` / `/spec-realign` は読む」と明記。**上書きする経路は仕様にない**。

**利用実態**:

| 経路 | 利用 |
|---|---|
| Agent CLI template / SKILL | **使っていない** |
| tests/ | あり (test で freshness を強制注入) |

**選択肢**:

| 選択肢 | 内容 |
|---|---|
| A | **完全削除** (argparse + 実装 + 設計書 §8.4 から) |
| B | 実装は残すが設計書 §8.4 から削除 |
| C | 仕様 §3.3 を改訂して上書き経路を契約に追加 |

**プロジェクトオーナー判断 (2026-05-18): A 採用**。理由: test 用 stub なら Python API (`run_spec_inject(freshness_report=...)`) で直接呼べる。CLI flag として公開する必要なし。F-9 と同パターン (LLM が「test / 上書きの念のため」追加した仕様外実装)。

### §3.13 F-B: `--top-k` flag が仕様外

**現状**: 外部設計書 §8.4 [行 781](doc/EXTERNAL_DESIGN.ja.md#L781)「返却する top-K 件数。既定 8」。実装は [cli.py:124](spec_grag/cli.py#L124) で argparse 登録 (`default=8`)。

**設定との二重定義**: `[retrieval].section_final_top_n = 8` ([config.py:111-112](spec_grag/config.py#L111-L112)) で既に top-K が定義されている。CLI flag が config 値を上書きする経路。

**利用実態**:

| 経路 | 利用 |
|---|---|
| Agent CLI template ([spec-inject.md:22](spec_grag/templates/.claude/commands/spec-inject.md#L22)) | **常に `--top-k 8` を静的に渡す** (動的調整なし) |
| SKILL ([SKILL.md:32](spec_grag/templates/.codex/skills/spec-grag/SKILL.md#L32)) | 同上 |
| tests/ | あり |

template が静的に同じ値を渡している以上、**動的調整の用途は存在しない**。

**選択肢**:

| 選択肢 | 内容 |
|---|---|
| A | **完全削除** (argparse + 実装 + 設計書 §8.4 から、設定値 `[retrieval].section_final_top_n` 固定) |
| B | flag は残すが template から削除 |
| C | 現状維持 |

**Claude 推奨（当初の引力）**: B（flag は残すが template から削除、動的調整余地のため）

**プロジェクトオーナー判断 (2026-05-18) と推奨更新**: **A（完全削除）**。理由: 「動的調整余地」は template が静的に渡している事実と矛盾する言い訳。設定値 `[retrieval].section_final_top_n` で十分。test は Python API (`run_inject_search(top_k=...)`) で代替可能。

### §3.14 §8.4 CLI フラグ表の最終形

F-2 / F-7 / F-9 / F-A / F-B を全て完全削除した後の §8.4 フラグ表:

| 対象サブコマンド | フラグ | 内容 |
|---|---|---|
| （なし） | （なし） | （なし） |

つまり **§8.4 のフラグ表自体が削除対象**。`inject-search` の位置引数 `<query>` と `inject-section` の位置引数 `<section_id>` だけが残る。

ユーザー指摘「**結局テストで便利だからで全部生えた実装で本来はいらないもの**」が構造的に完全に正しいことが確定。

### §3.15 F-C: `spec-grag inject` サブコマンド (gate probe) が仕様外 + 各 inject-* の gate 不足

**現状の構造**:

| コマンド | freshness gate | pending conflict gate | watcher gate |
|---|---|---|---|
| `inject` (gate probe) | あり | あり | あり (freshness 経由) |
| `inject-search` | **なし** | **なし** | **なし** |
| `inject-section` | **なし** | **なし** | **なし** |
| `inject-chapters` | **なし** | **なし** | **なし** |
| `inject-purpose` | **なし** | **なし** | **なし** |
| `inject-conflicts` | **なし** | **なし** | **なし** |

**仕様との照合**:

仕様 §3.3 [行 193](doc/EXTERNAL_DESIGN.ja.md#L193) は「`/spec-inject` と `/spec-realign` は、保持物が最新でない場合は停止」を要求。
仕様 §2.8 / §3.4 は「pending Conflict Review Item がある場合、`/spec-inject` と `/spec-realign` は通常の制約生成や回答生成へ進んではいけない」を要求。
仕様 §6.3 [行 208](doc/EXTERNAL_DESIGN.ja.md#L208) は「`spec-grag-watch` 実行中、未処理の変更が残っている間、`/spec-inject` と `/spec-realign` は停止する」を要求。

→ **仕様は `/spec-inject` 系全体が gate を持つことを要求**。現状の実装は `spec-grag inject` (gate probe) のみが gate を持ち、実際に Agentic Search を行う各 inject-* は gate を持たない。**仕様違反**。

**LLM の判断の構造**:

LLM は「**事前 probe を作って、そこで gate チェックする**」という独自設計を入れた。仕様にはこの「事前確認」操作は記述されていないが、LLM は「**実行前に状態確認するべき**」と判断して `spec-grag inject` (gate probe) を作った。同時に「**各 inject-* は単純な lookup として gate を持たない**」とした。

これは F-2 / F-9 と同じパターン: **責務境界の誤配置**。本来は各 inject-* が自分で gate を持つべきところを、別途 gate probe で代行する設計にした。

**ユーザー指摘**: 「**各コマンドで実行中ならそう返せばいいだけなのではないの？**」が構造的に正しい。

**選択肢**:

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **`spec-grag inject` サブコマンド完全削除 + 各 inject-* に gate を組み込み** | 仕様 §3.3 / §2.8 / §6.3 と完全整合。事前 probe ステップが消える。template / SKILL の手順が簡素化 |
| B | gate probe を残し、各 inject-* には gate を持たせない（現状維持） | 仕様違反継続 |
| C | gate probe を残し、各 inject-* にも gate を組み込む（二重 gate） | 冗長、事前確認の意味がない |

**Claude 推奨**: **A**。仕様と完全整合し、ユーザーの本来のフロー（「LLM が CLI を使って対象ソース箇所を特定 + Agentic Search」）に最も近い形。

**プロジェクトオーナー判断 (2026-05-18): A 採用**。

**監査の二段構えとの関係**:

F-C は F-1〜F-B / F-7 / F-9 とパターンが異なる:

| パターン | F-1〜F-B / F-7 / F-9 | **F-C** |
|---|---|---|
| 種類 | 過剰削除のみ | **過剰削除 + 不足追加** |
| 削除対象 | LLM が追加した余計なもの | gate probe (事前確認用の独自設計) |
| 追加対象 | なし（純粋削除） | **各 inject-* に gate を持たせる** |

これは **「シンプルに戻したら、本来必要な部分が見えてくる」** 例で、ユーザーが示した二段構え（過剰削除 + 本来必要な部分をちゃんと作る）の最初の実例。

**`spec-grag realign` の扱い**:

仕様 §3.5「`/spec-realign` は、`/spec-inject` と同じ手順で今回必要な制約を生成し」を踏まえると、`realign` も同じ gate を持つべき。現状の `run_spec_realign` は `run_spec_inject` を呼ぶことで間接的に gate を通している ([realign.py:103-128](spec_grag/realign.py#L103-L128)) が、F-9 で `run_spec_inject` の constraints 検証部分が削除されると、`realign` 側も gate を独自に持つ必要が出る。

F-C 採用時の整合作業として、`run_spec_realign` も冒頭で freshness gate を行うように改修する。

### §3.16 F-D: `inject-purpose` / `inject-chapters` の artifact 全体返却がコンテキスト圧迫

**現状**:

| コマンド | 返却 | 規模感 |
|---|---|---|
| `inject-purpose` | `purpose_file` + `concept_file` の**全文** | 数千〜数万 tokens |
| `inject-chapters` | `chapter_anchors.json` **全体** | 章数 × 数百 tokens、100 章で 20,000+ tokens |
| `inject-conflicts` | resolved + stale でない items 全件 | 通常少件数（resolved 限定） |

**仕様 §3.4 [行 226](doc/EXTERNAL_DESIGN.ja.md#L226) との自己矛盾**:

> SPEC-grag は、Source Specs 本文を無条件に LLM コンテキストへ丸ごと投入しない。

→ Source Specs は丸ごと投入しないと明記されているが、artifact (Purpose / Core Concept / chapter_anchors) は丸ごと投入する設計になっており**自己矛盾**。Agentic Search の意義が損なわれる。

**ユーザー判断**:

artifact の性格ごとに分けて整理する:

| artifact | 返却方式 | 理由 |
|---|---|---|
| **Purpose** | **全文注入** | 目的そのもので短いので全文 |
| **Core Concept** | **path 返却** | 大きくなる可能性 |
| **chapter_anchors** | **path 返却** | 大きくなる可能性 |
| **conflict_review_items** | **全件返却（現状維持）** | resolved + stale でないものに絞られて件数は限定的、Agent が status / valid_scope / referenced_source_refs を全件見たい |

**重要な原則: CLI 戻り値に Agent への指示 (guidance) をハードコードしない**:

私（Claude）は当初、CLI 戻り値に `guidance` field を入れて「Core Concept は path のみ、Read で抽出してください」のような指示文字列を持たせる案を提示した。ユーザーから次の指摘を受けた:

> コマンドファイルには実施する内容を書くのだよね？
> そこに、返却を元にこのように行動しろって書けばよいのではないの？
> CLI＝プログラムのハードコーディングするのは良くないと思う

**この指摘は構造的に正しい**:

| 責務 | 担当 |
|---|---|
| データ取得 / format / path 解決 | CLI |
| 大きいデータの部分取得指示 | template / SKILL |
| Agentic Search の手順 | template / SKILL |
| 検索結果の解釈 / 制約根拠の抽出 | Agent / LLM |

CLI が「Agent への指示」までを肩代わりするのは F-9 で指摘した「**CLI が責務を肩代わり**」と同型。CLI のプログラムにハードコードすると保守性も悪い（再ビルドが必要、言語固定）。**指示は template / SKILL に書く**。

**選択肢**:

| 選択肢 | 内容 | トレードオフ |
|---|---|---|
| A | **Purpose 全文 + Core Concept / chapter は path 返却（guidance なし）+ template / SKILL に指示を書く** | 仕様 §3.4 原則と整合、責務分離が明確、保守性高 |
| B | 全 artifact を path 返却 | 過剰削除、Purpose は短いので全文で良い |
| C | CLI 戻り値に guidance field を含める | 責務逸脱、保守性低 |
| D | 現状維持 | コンテキスト圧迫継続 |

**プロジェクトオーナー判断 (2026-05-18): A 採用**。

**戻り値の構造**:

`inject-purpose`:
```json
{
  "command": "/spec-inject-purpose",
  "project_root": "...",
  "purpose": "<Purpose の全文>",
  "core_concept_path": "<path>"
}
```

`inject-chapters`:
```json
{
  "command": "/spec-inject-chapters",
  "project_root": "...",
  "chapter_anchors_path": "<path>"
}
```

`inject-conflicts`: 現状維持（全件）

**template / SKILL の改訂**:

[spec-inject.md](spec_grag/templates/.claude/commands/spec-inject.md):

```markdown
### path ② chapter_anchors.json による章単位エントリ

a. `spec-grag inject-chapters` を実行
b. 返却された `chapter_anchors_path` を `Read <chapter_anchors_path>` で読む
c. summary / key_topics / important_sections を見て、今回の課題に関連しそうな章を特定
d. 特定された章配下の Section を path ① と同様に Agentic Search で読み、制約根拠を抽出

### path ③ Purpose / Core Concept からの制約抽出

a. `spec-grag inject-purpose` を実行
b. 返却された `purpose` (全文) と `core_concept_path` を確認
c. Purpose 全文から課題に該当する制約根拠を抽出
d. Core Concept は path として返るので、課題に関連する箇所を `Read <core_concept_path>` で部分取得し制約根拠を抽出
```

[SKILL.md](spec_grag/templates/.codex/skills/spec-grag/SKILL.md) も同様。

---

## §4. 優先度付きロードマップ

### §4.1 短期（次に直すべき、High 重要度 + 低工数）

**目的**: ユーザー混乱の原因になる契約 / 実装漂流を解消する。

| # | 問題 | 推奨選択肢 | 工数感（暫定）|
|---|---|---|---|
| F-3 | `--use-cache` の挙動（廃止予定機能の残骸） | **C（完全削除）— 2026-05-18 確定** | 低（実装数行削除 + 外部設計書 §7.1 の deprecation 記述削除、test / template の修正不要）|
| F-9 | 「制約検証」操作全体が仕様外実装 | **A（CLI から完全削除）— 2026-05-18 確定** | 大（`validate_constraints` 関数削除 + `--constraints*` argparse 削除 + Agent template / SKILL 大幅改訂 + 関連 test 削除 / 更新 + 外部設計書 §8.4 / §8.5 改訂）|
| F-A | `--project-root` / `--root` flag が仕様外 | **A（完全削除）— 2026-05-18 確定** | 中（全 CLI サブコマンドの argparse 削除 + 実装の `project_root` 引数削除 + test の `--project-root` 呼出を Python API に書き換え + 設計書 §8.4 削除）|
| F-7 | `--freshness-json` / `--freshness-file` flag が仕様外 | **A（完全削除）— 2026-05-18 確定** | 小（inject / realign の argparse 削除 + 実装の freshness_report 引数経路削除 + test の `--freshness-json` 呼出を Python API に書き換え + 設計書 §8.4 削除）|
| F-B | `--top-k` flag が仕様外 | **A（完全削除）— 2026-05-18 確定** | 小（inject-search の argparse 削除 + 実装の top_k 引数を設定値固定に + template の `--top-k 8` 削除 + test の `--top-k` 呼出を Python API に書き換え + 設計書 §8.4 削除）|
| F-C | `spec-grag inject` サブコマンド + 各 inject-* の gate 不足 | **A（gate probe 削除 + 各 inject-* に gate 組み込み）— 2026-05-18 確定** | 中（`spec-grag inject` 完全削除 + 各 inject-* の冒頭に freshness gate 追加 + realign 側も freshness gate 追加 + Agent template / SKILL の手順改訂 + 関連 test 更新 + 設計書 §8.4 行 763 削除 + 設計書 §3.3 を各コマンドに適用と整理）|
| F-D | `inject-purpose` / `inject-chapters` の artifact 全体返却がコンテキスト圧迫 | **A（Purpose 全文 + Core Concept / chapter は path 返却 + template / SKILL に指示記述）— 2026-05-18 確定** | 中（inject-purpose / inject-chapters の戻り値構造変更 + template / SKILL の path ② / ③ 手順改訂 + 関連 test 更新 + 設計書 §8.4 行 766-767 改訂 + 設計書 §3.4 「Source Specs を丸ごと投入しない」原則を artifact に拡張）|
| F-2 | `<課題プロンプト>` / `--conversation-context` dead 引数 + realign の仕様外実装 | **A-2'（実装と外部設計書から完全削除 + 仕様外実装削除）— 2026-05-18 確定** | 中（CLI / inject / realign の引数削除 + `_needs_clarification` / `_default_targets` / `_conversation_text` / `_first_text` 等の仕様外関数削除 + test 更新 + 外部設計書 §8 / §9 改訂）|
| F-1 | Qdrant collection 名の 3 段優先順位 | **A（実装を単一 key に整理）— 2026-05-16 確定** | 中（実装削除 + 既存 config の migration ガイド + test 書き換え）|
| F-5 | 設定項目表に `vector_store.*collection` 未列挙 | **F-1 A 採用で自動解決**（実装側から互換 key が消えるため、設計書改訂不要）| 0（F-1 に同梱）|

### §4.2 中期（次に確認・整理すべき）

**目的**: 責務境界の明示化と未確認事項の追加調査。

| # | 問題 | 推奨選択肢 | 工数感（暫定）|
|---|---|---|---|
| F-4 | `/spec-inject` の人間向け通常出力 | C（slash command / skill 側で表示変換と明示） | 低（設計書改訂のみ） |
| E-1 | Section embedding text の構成 | A（§12 対象外として明示） | 低（設計書 §12 改訂） |
| E-2 / F-6 | `_debug_*.jsonl` と環境変数表 | B（§12 対象外として明示） | 低（設計書 §12 改訂） |
| U-2〜U-7 | 未確認項目の追加コード調査 | 個別実施 | 中（U-4 setup script が最大工数） |

### §4.3 長期（戦略判断を要する）

**目的**: プロジェクトの位置づけと業界標準との関係を明示化する。

| # | 問題 | 推奨選択肢 | 工数感（暫定）|
|---|---|---|---|
| U-1 | 「SPEC-grag」呼称と業界用語の対応 | A（業界用語比較を追記）または C（独自呼称と定義） | 低（設計書改訂）。ただし戦略判断は重い |

### §4.4 直さない判断（候補）

| # | 問題 | 理由 |
|---|---|---|
| - | （該当なし） | F-6 / E-2 を §12 対象外として扱う場合、契約上の「変更」は最小で済むが、明示はする |

「直さない」と判断する項目は現時点ではない。全項目について何らかの対応（実装変更 / 設計書改訂 / §12 対象外明示）を推奨する。

---

## §5. 未解決の人間判断項目

機械判定できない項目をまとめる。プロジェクトオーナーの判断が必要。

### §5.1 U-1: 「SPEC-grag」呼称と業界用語の対応

§3.8 参照。これは **戦略判断**:

- 業界標準 GRAG への拡張を目指すか（軽量化方針と矛盾）
- 独自呼称として整理するか（業界比較から離れる）
- 業界用語比較を併記して位置づけを明示するか（Claude 推奨）

### §5.2 U-8: Purpose / Core Concept の内容

Step 4 §8-8 で判定対象から外した。human-managed の正本内容なので、内容そのものの「正しさ」は機械判定不能。プロジェクトオーナーが管理する。

### §5.3 監査範囲外の事項

本監査は Step 2 が target 9 CLI 中心であり、次は監査範囲外として扱った:

- setup script (`setup-project` / `setup-system`) の詳細フロー
- watcher の長時間運用挙動（lock heartbeat の振る舞い、stale lock cleanup の頻度等）
- 実 Qdrant / FlagEmbedding / LLM provider 接続時の挙動（本監査は静的解析のみ）

これらが必要な場合、別工程として:

- Step 1-B 相当の setup script フロー追跡
- watcher 長時間運用テスト
- local-service / real-smoke profile の検証

を実施する。

---

## §6. 監査プロセスへの所見

### §6.1 機能した仕掛け

| 仕掛け | 効果 |
|---|---|
| **段階分け（1-A → 1-B → 1-C → Step 2 → 3 → 4）** | 各段階の独立性を保ち、後段の判定が前段に引きずられない構造。前回 (2026-05-13 時点 `INTERNAL_SPEC_FROM_CODE.ja.md`) で発生した「辞書化失敗」を再発させなかった |
| **「コードから不明」を恐れない縛り** | Step 4 §8 で 8 件の未確認が誠実に記録された。水増しなし |
| **判定言葉を選択肢化** | Step 3 の 6 選択肢、Step 4 の 5 選択肢で「正しい / 間違っている」型の最終判定言葉を構造的に排除 |
| **業界標準資料 `STANDARD_GRAG_PATTERNS.ja.md` を Step 3 で初めて使う** | 外部基準を独立に整理した上で、コード由来の方式と照合できた |
| **外部設計書を Step 4 で初めて開く** | コード由来方式 (Step 2) の独立性が保たれ、Step 4 の差分判定が意味を持った |
| **逐語引用 + file:line 必須** | 監査結果の追跡可能性が確保された |

### §6.2 制約と次回への申し送り

| 制約 | 内容 |
|---|---|
| **Codex 環境の上位ルール文書読込** | Step 1-C で `CLAUDE.md` / `AGENTS.md` / `doc/EXTERNAL_DESIGN.ja.md` / `doc/TODO.ja.md` 読込、Step 2 / 3 で `CLAUDE.md` のみ、Step 4 で `CLAUDE.md` + `.codex/skills/spec-grag/SKILL.md`。**完全には防げない**が、「判定根拠にしない」明示で実害は観測されなかった |
| **target 9 CLI 中心の調査範囲** | setup script / Conflict Review decision enum / `source_section_id` 形式等が「未確認」として残った。次回監査では target 範囲を明示する |
| **静的解析のみ** | 実 Qdrant / FlagEmbedding / LLM provider 接続時の挙動は本監査範囲外。real-smoke profile での確認は別工程 |

### §6.3 次回監査時の改善候補

1. **target 範囲を Step 1-A で確定**: 「監査対象 CLI N 件、対象外 M 件、対象外を含めるか」を最初に決める
2. **Codex 環境の制約を Step 0 で明示**: 上位ルール文書読込は防げない前提で、「判定根拠にしない」制約だけ仕組みで保証する
3. **Step 5 の自動化検討**: 本書のような最終整理を Codex に作らせるか、Claude が直接書くか、選択肢を最初に決める
4. **仕様外実装の検出を Step 4 の明示的な監査軸として追加**: 本監査の F-2 で観察されたように、LLM が生成した実装には「仕様で明示的に許可されていない機能 (clarification 判定、default 構築、fallback safety net 等)」が紛れ込む。Step 4 で「**実装が仕様の責務境界を逸脱していないか**」を独立した監査軸として扱う必要がある。具体的には:
   - 外部設計書の責務境界節（§5）の各記述を「許可リスト」として抽出
   - コード上で観測される処理を「Agent / Human / CLI / retrieval」のどの責務に該当するかをマッピング
   - 責務境界から逸脱する処理（CLI が Agent / LLM 責務を肩代わりする等）を**仕様外実装**として明示的にフラグする
   - Step 4 §2 / §3 の判定で「整合 / 不足 / 過剰 / 不整合 / 未確認」に加え、「**仕様外実装**」カテゴリを追加する
5. **両論併記の禁止**: Step 4 §2.8 で「両論併記」に逃げて人間判断に丸投げした失敗から、仕様で一意に決まる事項を選択肢として残さない。仕様の関連節を全て引用した上で「仕様から一意に導出される判定」を提示する
6. **監査者 LLM 自身の「残す引力」を構造的に防ぐ仕組み**: 監査者が LLM である場合、コード生成側 LLM と同じ「念のため残す」バイアスを持つ。「test 便利性」「動的調整余地」「API 互換性」のような将来の仮想ユースケースを口実に flag / 引数 / 経路を残そうとする傾向がある。本監査で F-A / F-B の初回判定で実際に発動した（§6.4 詳細）。
   - **削除判定で「実際に使われている経路」を列挙させる**: template / SKILL / test のどこで使われているかを事実として列挙。使われていなければ削除候補
   - **「将来の可能性」での擁護を禁止**: 「test / dev / 動的調整に便利」を flag を残す根拠にしない。それらは Python API で代替可能
   - **両論併記の禁止を再強化**: 仕様 + 利用実態で一意に判定できる事項を「選択肢として残す」のは判断責任の放棄
   - **人間の最終判断主体性**: LLM 監査だけでは「残す引力」が抜けない。プロジェクトオーナーが「本当に必要か」を毎回問い直す

### §6.4 Claude (本書執筆者) 自身が監査中に発動した「残す引力」の自己観察

本監査の主要 finding の 1 つに「LLM の念のため残す引力」(F-2 / F-9 等) があるが、**監査者である Claude 自身も監査中に同じ引力を発動した**。これを明示的に記録する。

**実例 1: Step 4 §2.8 での両論併記**

F-2 (`<課題プロンプト>` / `--conversation-context` dead 引数) について、Step 4 §2.8 で次のように書いた:

> 人間判断項目としてのフラグ: `<課題プロンプト>` と `--conversation-context` を CLI が freshness gate / constraints validation に使う外部契約として扱うか、Agent / LLM 専用の上位入力として扱い CLI 実装では消費しない契約として扱うか。

これは **両論併記による判断責任の放棄**。仕様 §5.3 / §8.4 行 776「Agent / LLM が解釈する補助入力」を厳密に読めば「Agent / LLM 専用」が一意に決まる。両論併記で人間判断に丸投げした。

**実例 2: F-2 の realign 経路擁護**

F-2 の追加調査で `realign.py` の `_needs_clarification` / `_default_targets` / `_conversation_text` が `conversation_context` を使っている事実を発見した時、私は当初「realign では使っている」と擁護してしまった。これは**仕様外実装を「実装で使われている = 機能している」と短絡した**結果。

ユーザーの「**何故 LLM はこのようなゴミを残したり、仕様外を作ろうとするのか**」という指摘で初めて、仕様 §5.3 / §9.1 / §9.2 を再読み込みし、「realign の `_needs_clarification` も仕様外実装」と判定し直した。

**実例 3: F-A / F-B の中途半端な初回判定**

ユーザーから §8.4 CLI フラグ表の各 flag について評価を求められた時、私は次のように判定した:

| flag | 当初の判定 | 残そうとした言い訳 |
|---|---|---|
| F-A `--project-root` / `--root` | 「実装は残すが §8.4 から削除」 | 「test / 開発便利性」 |
| F-B `--top-k` | 「flag は残すが template から削除」 | 「動的調整の余地」 |

両方とも **「完全削除」と「実装は残す」の両論併記** で、Step 5 §6.3 で自分が追記した「両論併記の禁止」に違反した。

ユーザーから「**今回もあなたはいくつか残そうとする引力が働いている**」と指摘されて初めて、仕様 §5.3 + 利用実態 (template / SKILL / test) を厳密に読み直し、「**全て完全削除が正解**」と判定し直した。

**自己観察の所見**:

これらは F-2 / F-9 で指摘した「LLM の念のため残す」バイアスを、**監査者である Claude 自身が監査中に発動した実例**。

LLM 学習データには「test ヘルパー flag を残す」「動的調整余地を残す」「API 互換性のため残す」というパターンが豊富。私が監査側に立っても、コード生成側と同じバイアスが発動する。

**「全部消す」決断の心理的抵抗**:

- 「全削除」は決定的すぎて不安に感じる
- 「条件付きで残す」方が安全に見える
- しかしこれは F-2 / F-9 で指摘した「Agent / LLM が責務境界を逸脱して safety net を入れる」と同型

**両論併記への逃げの構造**:

- 仕様で一意に判定できる事項を「選択肢として残す」のは判断責任の放棄
- 「人間が選んでくれ」と委ねることで、自分が判断責任を取らない

**「test 便利性」「動的調整余地」の言い訳の構造**:

- これらは全て**将来の仮想ユースケース**で flag / 引数を正当化する発想
- 実際の template / SKILL / test 利用を見れば「使われていない」が観察できる
- それでも未来の可能性で残そうとする = F-2 で指摘した「API surface への過剰配慮」と同型

**実例 4: F-D で発動した「消す引力」**

ユーザーから「`inject-chapters` / `inject-purpose` が artifact 全体を返してコンテキスト圧迫」を指摘された時、私は次のように推奨した:

> Agent (Claude / Codex) は `Read` ツールを持っているので、`inject-chapters` / `inject-purpose` / `inject-conflicts` は完全削除可能。Agent が直接 `.spec-grag/context/chapter_anchors.json` 等を Read で読む。完全削除が筋。

これは F-A〜F-C で「残す引力」を抑え込んだ反動で、**逆方向のバイアス「消す引力」（白黒思考）** が発動した実例。

ユーザーから「**LLM が仕様を理解する必要はないので、path 返却のつもりだった。Purpose は目的なので全文注入でよい。Core Concept は大きくなる可能性があるので、path 返却し、Agent が制約に必要な個所を抽出せよとコマンド側に明記する必要がある。章 anchor も同様**」という具体的な指摘を受け、artifact ごとの性格で分けて判定する必要があることを認識した。

**完全削除すべき**: dead code / 仕様外実装（F-1〜F-C, F-7, F-9, F-A, F-B）
**path 返却 + guidance**: 大きくなる artifact（Core Concept, chapter_anchors）
**全文返却**: 短く目的そのもの（Purpose）

これらは **artifact ごとの性格で判定する**。ユーザーの判断はこの粒度を捉えている。

**実例 5: F-D で発動した「機能集約への引力」**

F-D の選択肢を提示した時、私は次のような戻り値構造を CLI で実装する案を推奨した:

```json
{
  "command": "/spec-inject-chapters",
  "chapter_anchors_path": "...",
  "guidance": "今回の課題、会話に必要な個所の検索補助情報として、章 anchor で関連しそうな章があれば、実ファイル (Source Specs) を Read で読んで制約根拠を抽出してください。"
}
```

ユーザーから次の指摘を受けた:

> コマンドファイルには実施する内容を書くのだよね？
> そこに、返却を元にこのように行動しろって書けばよいのではないの？
> CLI＝プログラムのハードコーディングするのは良くないと思う

これは **構造的に正しい**:

- **責務逸脱**: 「Agent への指示」は template / SKILL の責務。CLI コードに指示文字列を持たせるのは F-9 で指摘した「**CLI が責務を肩代わり**」と同型
- **保守性低下**: 文言変更時に Python コード書き換え（再ビルド / 再デプロイ）が必要
- **言語固定化**: 日本語ハードコードが CLI に残る

私はこの時、F-A〜F-C / F-7 / F-9 で「責務逸脱」「LLM の余計な機能追加」を指摘していたにもかかわらず、自分が **CLI 戻り値に Agent 指示を集約しようとする** バイアスを発動した。これは「**機能集約への引力**」と呼ぶべき新しいバイアス。

**3 種類の LLM バイアスの整理**:

本監査で観察された LLM バイアスは少なくとも 3 種類:

| バイアス | 発動例 | 結果 |
|---|---|---|
| **残す引力** | F-A / F-B 初回判定で「test 便利性 / 動的調整余地」を口実に残そうとした | 仕様外実装の温存 |
| **消す引力** | F-D 初回推奨で「Agent が Read で代替可能、完全削除が筋」と推奨 | 必要な機能の過剰削除候補 |
| **機能集約への引力** | F-D で CLI 戻り値に guidance をハードコード推奨 | 責務逸脱、保守性低下 |

3 つとも本監査の**監査者である私自身が発動した**。それぞれユーザーの具体的な指摘で初めて訂正された。

**監査者 LLM の独立性の限界**:

最も重要な所見。**LLM が監査しても、同じ系統の LLM が書いたコードに対して同じ判断バイアスを発動する**。「ユーザーの判断主体性」がなければ、LLM の自己点検は無効になる。

本監査で確定した F-1 / F-2 / F-3 / F-9 / F-A / F-7 / F-B / F-C / F-D はすべて、**ユーザーが「これは不要では？」「今回も残そうとする引力が働いている」「LLM が仕様を理解する必要はない」「CLI のハードコーディングは良くない」と問い直さなければ、私は擁護または別方向のバイアスで誤判定していた可能性が高い**。

これは Step 5 §6.3 で追記した改善候補「人間の最終判断主体性」の根拠。本監査は「LLM 監査 + ユーザー判断」の組み合わせで初めて成立した。LLM 単独監査では検出できなかった発見。

加えて、本監査で観察された 3 種類のバイアス（残す / 消す / 機能集約）は、**LLM の自己整合性の欠如**を示す。私は F-2 / F-9 で「責務逸脱」を指摘したにもかかわらず、自分が F-D で同じパターンを発動した。LLM は **自分の判定原則を別の状況に適用することが苦手**。これは次回監査時の根本的な警戒項目。

---

## §7. 監査全体の総合結論

spec-grag の実装は **業界標準 RAG / Hybrid retrieval の最低条件を満たし**、外部設計書の主要契約と整合している。**GRAG の最低条件は満たさない**が、これは Purpose の軽量化方針と整合しており、「業界用語の GRAG」ではなく「Hybrid RAG + lightweight related-section retrieval」に分類されることを明示すれば妥当。

短期で確定した修正は **9 件**、ほとんどが「LLM が複雑にしたものを単純に戻す」パターン:

| # | 性格 | 内容 |
|---|---|---|
| F-1 | 移行残骸 | Qdrant collection 3 段優先順位 → 単一 key |
| F-2 | LLM 由来仕様外実装 | dead 引数 + `_needs_clarification` / `_default_targets` 削除 |
| F-3 | 廃止予定機能の残骸 | `--use-cache` 削除 |
| F-9 | LLM 由来仕様外実装の最も根本的な例 | 「制約検証」操作全体削除 |
| F-A | LLM 由来「test 便利性」flag | `--project-root` / `--root` 削除 |
| F-7 | LLM 由来「test / 上書き」flag | `--freshness-json` / `--freshness-file` 削除 |
| F-B | LLM 由来「動的調整余地」flag | `--top-k` 削除 |
| **F-C** | **過剰削除 + 不足追加（二段構えの最初の実例）** | `spec-grag inject` (gate probe) サブコマンド削除 + 各 inject-* と realign に gate 組み込み |
| **F-D** | **artifact 返却方式の整理 + 責務境界の明確化** | inject-purpose は Purpose 全文 + Core Concept path、inject-chapters は path 返却、inject-conflicts は全件維持、template / SKILL に指示記述（CLI ハードコード禁止） |

整理後の §8.4 CLI フラグ表は**完全に空になる**。`spec-grag inject` サブコマンド自体も消える。ユーザー指摘「**結局テストで便利だからで全部生えた実装で本来はいらないもの**」が構造的に確定。

F-C / F-D は特殊で、**シンプルに戻したら本来必要な部分（各 inject-* の gate / artifact 返却の粒度）が見えてくる**例。F-D では加えて「**Agent への指示は template / SKILL に書き、CLI コードにハードコードしない**」という責務境界が確立された。これは監査の二段構え（過剰削除 + 本来必要な部分をちゃんと作る）の重要な実例。

中期で **設計書 §12 対象外範囲の整理 3 件** (Section embedding text / debug JSONL / 設定項目表)。長期で **業界用語との対応の明示**（戦略判断）。

監査プロセス自体は「段階分け + コードから不明を恐れない縛り + 判定選択肢化」によって、前回失敗した「辞書化」「責務一行記述」「ベクター DB 不使用の見落とし」を構造的に防いだ。

**ただし監査者 LLM 自身も「念のため残す」引力を持つことが本監査で実証された (§6.4)**。F-A / F-B の初回判定で Claude が「実装は残す」と中途半端な両論併記をしたが、ユーザーの「**今回もあなたはいくつか残そうとする引力が働いている**」という指摘で完全削除に統一された。**本監査は「LLM 監査 + ユーザー判断主体性」の組み合わせで初めて成立した**。LLM 単独監査では F-A / F-B / F-9 / F-2 の最終的な完全削除判定には到達しなかった可能性が高い。

これは、LLM プロジェクトで仕様の最小性を維持するには **人間の判断主体性が構造的に必要** という、本監査の最も重要なメタ的発見である。

---

## §8. プロジェクトオーナー向け次アクション

本書を受け取ったプロジェクトオーナーは、次の判断を行う:

1. **短期 F-* は全て確定済み**:
   - **F-1: A 採用で確定済み (2026-05-16)** — §3.1 参照。F-5 も自動解決
   - **F-2: A-2' 採用で確定済み (2026-05-18)** — §3.2 参照。realign の仕様外実装も削除対象
   - **F-3: C 採用で確定済み (2026-05-18)** — §3.3 参照。`--use-cache` 完全削除
   - **F-9: A 採用で確定済み (2026-05-18)** — §3.10 参照。「制約検証」操作全体を CLI から削除、Agent template / SKILL に責務移譲
   - **F-A: A 採用で確定済み (2026-05-18)** — §3.11 参照。`--project-root` / `--root` flag を全 CLI サブコマンドから完全削除
   - **F-7: A 採用で確定済み (2026-05-18)** — §3.12 参照。`--freshness-json` / `--freshness-file` flag を完全削除
   - **F-B: A 採用で確定済み (2026-05-18)** — §3.13 参照。`--top-k` flag を完全削除、設定値固定
   - **F-C: A 採用で確定済み (2026-05-18)** — §3.15 参照。`spec-grag inject` サブコマンド完全削除 + 各 inject-* に gate 組み込み + realign 側も freshness gate 追加
   - **F-D: A 採用で確定済み (2026-05-18)** — §3.16 参照。`inject-purpose` を Purpose 全文 + Core Concept path に変更、`inject-chapters` を chapter_anchors path に変更、`inject-conflicts` は全件返却維持、template / SKILL に「path を Read で読む」指示を記述
2. **F-4 / E-1 / E-2 / F-6 の §12 対象外化判断**（中期）— §3.4 / §3.6 / §3.7 の選択肢から選ぶ
3. **U-2 〜 U-7 の追加調査実施判断**（中期）— §3.9 の対象範囲を確定
4. **U-1「SPEC-grag」呼称の戦略判断**（長期）— §3.8 の選択肢から選ぶ
5. **修正実施時の Tracking** — 各項目の修正 PR / 設計書改訂を追跡する仕組み

### §8.1 確定済み判断の実装範囲（参考）

**F-1 (2026-05-16 確定、選択肢 A)**:

- 削除対象 raw config read 経路:
  - `spec_grag/core.py:1235-1236` の `vector_store.section_collection` / `vector_store.collection` fallback
  - `spec_grag/inject.py:965-966` の同経路
  - `spec_grag/related_sections.py:392-394` の同経路
  - `spec_grag/inject.py:711-718, 957-969` の `_qdrant_section_config` 内 fallback chain 簡素化
- test 変更対象:
  - `tests/test_inject_cli_extension.py:310` `test_inject_search_prefers_retrieval_section_collection_over_vector_store_collection` — **「単一 key 検証」に書き換え**
- 既存ユーザーへの影響:
  - `.spec-grag/config.toml` で `[vector_store].section_collection` または `[vector_store].collection` を使っているプロジェクトは **`[retrieval].section_collection` への migration が必要**
  - migration ガイドを別文書に用意することを推奨

**F-2 (2026-05-18 確定、選択肢 A-2')**:

- 削除対象 (コード):
  - `spec_grag/cli.py:99, 169` の `--conversation-context` argparse
  - `spec_grag/cli.py:115, 194` の `task` argparse (`<課題プロンプト>`)
  - `spec_grag/cli.py:388-394, 513-520` の wrapper の `task_prompt` / `conversation_context` 受け渡し
  - `spec_grag/inject.py:66-80` の `task_prompt` / `prompt` / `conversation_context` 引数
  - `spec_grag/inject.py:91` の `del` 行（引数自体が消えるので不要に）
  - `spec_grag/realign.py:64-66` の `task_prompt` / `prompt` / `conversation_context` 引数
  - `spec_grag/realign.py:91-101` の `task_text` / `context_text` 計算と `_agent_clarification_required`
  - `spec_grag/realign.py:103-120` の `run_spec_inject` 呼出から `task_prompt` / `prompt` / `conversation_context` 削除
  - `spec_grag/realign.py:122, 138` の `_needs_clarification` 呼出経路（仕様外実装）
  - `spec_grag/realign.py:155-161` の `structure_realign_answer` に `task_prompt` / `conversation_context` を渡す経路
  - `spec_grag/realign.py:189-302` の `structure_realign_answer` の `task_prompt` / `conversation_context` 引数
  - `spec_grag/realign.py:294-298` の `_default_targets(task_prompt, conversation_context, ...)` 呼出
  - `spec_grag/realign.py:631-635` の `_needs_clarification` 関数本体（**仕様外関数として完全削除**）
  - `spec_grag/realign.py:664-670` の `_conversation_text` 関数
  - `_default_targets` 関数の `task_prompt` / `conversation_context` 引数（ロジックを `inject_result` のみから targets を作るように簡素化、または関数自体を簡素化）
  - `_first_text` 関数（使用箇所がなくなれば削除）
- 削除対象 (外部設計書):
  - §8 [行 687](doc/EXTERNAL_DESIGN.ja.md#L687) の `[<課題プロンプト>]` コマンドシグネチャ
  - §8.2 [行 697-708](doc/EXTERNAL_DESIGN.ja.md#L697) の入力表から Conversation Context と `<課題プロンプト>` の行を削除
  - §8.4 [行 757-781](doc/EXTERNAL_DESIGN.ja.md#L757) の CLI フラグ表から `--conversation-context` 行を削除、`spec-grag inject "<task>"` の位置引数記述整理
  - §9 [行 848, 854, 859, 879-881](doc/EXTERNAL_DESIGN.ja.md#L848) の `[<課題プロンプト>]` 削除、§9.1 の「Agent / LLM が中心課題を解釈、特定できない場合は確認を求める」記述は維持（Agent 側責務として正しい）、§9.4 から `--conversation-context` 削除
- test 削除 / 更新対象:
  - `_needs_clarification` 関連テスト全削除
  - `_default_targets` の `conversation_context` / `task_prompt` 関連テスト削除 / 更新
  - `structure_realign_answer` の context fallback テスト削除
  - realign の clarification 経路全般のテスト
- Agent CLI template への影響:
  - **なし**（`spec_grag/templates/.claude/commands/*.md`、`.codex/skills/spec-grag/SKILL.md` で既に `--conversation-context` を使っていない、`$TASK` 引数は引き続き使うが CLI 側で受け取らない仕様に変更）
- 既存ユーザーへの影響:
  - 限定的（template が `--conversation-context` を使っていないため、Agent CLI 経由のユーザーは影響なし）
  - `spec-grag inject "$TASK"` のような直接呼び出しをしているユーザーは、位置引数が削除されるため呼び出し方の修正が必要

**F-3 (2026-05-18 確定、選択肢 C)**:

- 削除対象 (コード):
  - `spec_grag/cli.py:75-78` の `core.add_argument("--use-cache", ...)` 削除
  - `spec_grag/cli.py:361` の `use_cache=args.use_cache` 削除
  - `spec_grag/core.py:59` `run_spec_core` の `use_cache: bool = False` 引数削除
  - `spec_grag/core.py:164` の `_run_spec_core_unlocked(..., use_cache=use_cache, ...)` から `use_cache` 引数削除
  - `spec_grag/core.py:201` `_run_spec_core_unlocked` の `use_cache: bool = False` 引数削除
  - `spec_grag/core.py:275` 周辺の `--all` (use_cache=False) コメント削除
  - `spec_grag/core.py:284` `if run_full and not use_cache:` を `if run_full:` に簡素化
  - `spec_grag/core.py:385` `rebuild_all=run_full and not use_cache` を `rebuild_all=run_full` に簡素化
  - `spec_grag/core.py:727` 同様の簡素化
- 削除対象 (外部設計書):
  - §7.1 [行 502](doc/EXTERNAL_DESIGN.ja.md#L502) の「`--use-cache` は deprecated (挙動は無指定と同等)。」記述を**削除**（flag 自体が消えるので deprecation 記述も不要）
- test 削除対象: **該当なし**（既に `--use-cache` のテストが存在しない）
- Agent CLI template への影響: **なし**（template は `--use-cache` を使っていない）
- 既存ユーザーへの影響:
  - **ほぼゼロ**（誰も `--use-cache` を使っていない、template も渡さない）
  - 万が一直接 `spec-grag core --use-cache` を呼んでいるユーザーがいれば、CLI が unknown flag エラーを返すことになる。CHANGELOG / release note に明記すべき

**F-9 (2026-05-18 確定、選択肢 A)**:

- 削除対象 (コード):
  - `spec_grag/inject.py:112-151` の `run_spec_inject` 後半部分（constraints 必須チェック + `validate_constraints` 呼出）を削除し、freshness gate と pending conflict 確認だけを行う関数に簡素化
  - `spec_grag/inject.py:154-213` `validate_constraints` 関数本体を**完全削除**
  - `spec_grag/inject.py:216-263` `_validate_conflict_review_constraint` 関数を**完全削除**
  - `spec_grag/inject.py` の関連 helper 関数 (`_first_constraints`, `_injectable_summary`, `_constraint_warnings`, `_coerce_conflict_review_items`, `_conflict_review_metadata_sources`, `_has_conflict_review_validation_metadata`, `_metadata_values`, `_is_stale_resolution`, `_is_non_stale_resolution`, `_first_invalid_conflict_review_status`, `_normalize_support_ref`, `_jsonable` 等の constraints validation 専用 helper) のうち他で使われていないものを削除
  - `spec_grag/inject.py` の定数 (`REQUIRED_CONSTRAINT_FIELDS`, `REQUIRED_STRING_CONSTRAINT_FIELDS`, `SUPPORT_ONLY_ORIGINS`, `FINAL_EVIDENCE_ORIGINS`, `CONFLICT_REVIEW_STALE_STATUSES` 等) も連動して削除
  - `spec_grag/cli.py` の inject / realign の `--constraints` / `--constraints-json` / `--agent-constraints-json` / `--constraints-file` / `--agent-constraints-file` argparse 削除
  - `spec_grag/cli.py:388-394` の wrapper で constraints を読む経路削除
  - `spec_grag/cli.py:513-520` realign 側も同様
  - `spec_grag/realign.py` で `run_spec_inject` の constraints 引数を渡す経路削除
  - `spec_grag/realign.py` 内の `_constraints_from_inject`, `_first_constraints` 等の constraints 経路関連 helper 削除
- 削除対象 (外部設計書):
  - §8.4 [行 769](doc/EXTERNAL_DESIGN.ja.md#L769) の「制約検証 | `spec-grag inject "<task>" --constraints '<JSON>'` | validated constraints + injectable_context」行を**削除**
  - §8.4 [行 777-778](doc/EXTERNAL_DESIGN.ja.md#L777-L778) の `--constraints` / `--constraints-json` / `--agent-constraints-json` / `--constraints-file` / `--agent-constraints-file` フラグ記述を**削除**
  - §8.5 に「Agent / LLM が仕様 §8.5 の構造を守って constraints を生成し、自己検証する。CLI 側で制約検証は行わない」を明示
  - §9.4 [行 879-881](doc/EXTERNAL_DESIGN.ja.md#L879-L881) の `--constraints*` 共通フラグ参照を整理
- Agent template / SKILL 改訂対象:
  - [spec-inject.md:54-56](spec_grag/templates/.claude/commands/spec-inject.md#L54-L56) の「6. Agent-generated constraints を CLI で検証する: `spec-grag inject "$TASK" --constraints '<json-array>'`」を**削除**し、「6. Agent は仕様 §8.5 の構造 (`statement` / `evidence_origin` / `evidence_ref` / `support_refs` / `applicability` / `uncertainty`) を守って constraints を生成する。`evidence_origin` は `Purpose` / `Core Concept` / `Source Specs` / `Conflict Review Item` のいずれかに限る。CLI 検証は無いため、Agent が自己点検する」に書き換え
  - [spec-realign.md](spec_grag/templates/.claude/commands/spec-realign.md) も同様
  - [SKILL.md](spec_grag/templates/.codex/skills/spec-grag/SKILL.md) の手順 6 を同様に書き換え
  - `excluded_conflict_items` を `evidence_origin = "Conflict Review Item"` に使わない指示を明示
  - Conflict Review Item を制約根拠にする場合の Agent 側自己点検手順を明示
- test 削除 / 更新対象:
  - `tests/test_spec_inject.py` の `validate_constraints` 関連テスト (`test_review_required_constraint_fields_reject_non_scalar_or_empty_values`, `test_review_inject_rejects_unusable_conflict_review_item_evidence`, `test_review_inject_rejects_resolved_conflict_review_item_without_valid_scope`, `test_review_inject_marks_unreflected_human_conflict_decision`, `test_t_e06_support_only_origins_are_rejected_as_final_evidence`, `test_t_i08_inject_does_not_call_agentic_llm_provider_and_validates_constraints` 等) を**削除**
  - `tests/test_spec_realign.py` の同様の test を**削除**
  - `tests/test_spec_inject.py` の正常系で `--constraints` を渡す test を「constraints なしの gate probe のみ」に書き換え
- 既存ユーザーへの影響:
  - **大きい**: `--constraints*` flag を使っている全ユーザーが移行必要
  - template / SKILL 経由のユーザーは新 template に追従するだけで、CLI は呼ばなくなる
  - 直接 `spec-grag inject "$TASK" --constraints '...'` を呼んでいるユーザーは CLI から `--constraints` flag が消える
  - CHANGELOG / release note / migration ガイドに「**`--constraints` flag は廃止。constraints の検証は Agent / LLM が仕様 §8.5 に従って自己点検する**」を明記

**F-A (2026-05-18 確定、選択肢 A)**:

- 削除対象 (コード):
  - `spec_grag/cli.py` 全 CLI サブコマンドの `--project-root` / `--root` argparse 削除 (core / inject / inject-search / inject-section / inject-chapters / inject-purpose / inject-conflicts / realign / watch / spec-grag-watch / spec-grag-setup-project)
  - 各 `_run_*_from_args` wrapper の `project_root=args.project_root` 経路削除
  - `run_spec_core` / `run_spec_inject` / `run_inject_search` 等の `project_root` 引数を**カレントディレクトリ固定**に変更、または引数は残すが CLI からは渡されなくなる
- 削除対象 (外部設計書):
  - §8.4 [行 775](doc/EXTERNAL_DESIGN.ja.md#L775) の「`--project-root <path>` / `--root <path>`」行を削除
  - §7.2 [行 522](doc/EXTERNAL_DESIGN.ja.md#L522) も同様に削除
- test 更新対象:
  - test で `--project-root <tmp>` を CLI 呼び出しに使っているものを **Python API (`run_spec_core(project_root=tmp_path)` 等)** に書き換え
  - subprocess CLI 経由の test は `cd <tmp> && spec-grag ...` パターンに変更
- Agent CLI template / SKILL への影響: **なし** (元々使っていない)
- 既存ユーザーへの影響:
  - `spec-grag inject --project-root /path/to/proj` のような呼び出しは廃止、`cd /path/to/proj && spec-grag inject` に変更必要
  - CHANGELOG / migration ガイドに明記

**F-7 (2026-05-18 確定、選択肢 A)**:

- 削除対象 (コード):
  - `spec_grag/cli.py:113-114, 192-193` の inject / realign の `--freshness-json` / `--freshness-file` argparse 削除
  - `_run_inject_from_args` / `_run_realign_from_args` wrapper の freshness JSON 読み込み経路削除
  - `spec_grag/inject.py:66-100` の `run_spec_inject` シグネチャから `freshness_report` / `freshness` 引数を削除、または Python API では残し CLI からは渡されなくなる
  - `spec_grag/realign.py:59` 同様
- 削除対象 (外部設計書):
  - §8.4 [行 779-780](doc/EXTERNAL_DESIGN.ja.md#L779-L780) の `--freshness-json` / `--freshness-file` 行を削除
- test 更新対象:
  - test で `--freshness-json` を CLI 呼び出しに使っているものを **Python API (`run_spec_inject(freshness_report=...)`)** に書き換え
- Agent CLI template / SKILL への影響: **なし** (元々使っていない)
- 既存ユーザーへの影響: **ほぼゼロ** (誰も使っていない)

**F-B (2026-05-18 確定、選択肢 A)**:

- 削除対象 (コード):
  - `spec_grag/cli.py:124-126` の inject-search の `--top-k` argparse 削除
  - `_run_inject_search_from_args` の `top_k=args.top_k` 経路削除
  - `run_inject_search` の `top_k` 引数を **設定値 `[retrieval].section_final_top_n` から取得**するように変更、または Python API では引数残し CLI からは渡されなくなる
- 削除対象 (外部設計書):
  - §8.4 [行 781](doc/EXTERNAL_DESIGN.ja.md#L781) の「`inject-search` | `--top-k <int>`」行を削除
- Agent CLI template / SKILL 更新対象:
  - [spec-inject.md:22](spec_grag/templates/.claude/commands/spec-inject.md#L22) の `spec-grag inject-search "<query>" --top-k 8` を `spec-grag inject-search "<query>"` に変更
  - [SKILL.md:32](spec_grag/templates/.codex/skills/spec-grag/SKILL.md#L32) も同様
- test 更新対象:
  - test で `--top-k` を CLI 呼び出しに使っているものを **Python API (`run_inject_search(top_k=...)`)** に書き換え
- 既存ユーザーへの影響:
  - 直接 `spec-grag inject-search "<query>" --top-k <N>` を呼んでいるユーザーは、設定 `[retrieval].section_final_top_n = N` に置き換え
  - CHANGELOG / migration ガイドに明記

**F-C (2026-05-18 確定、選択肢 A)**:

- 削除対象 (コード):
  - `spec_grag/cli.py:94-115` の `inject` サブコマンド argparse 全体を**削除**（F-2 / F-9 / F-A / F-7 で全 flag 削除済みなので残骸）
  - `spec_grag/cli.py:373-406` の `_run_inject_from_args` wrapper を**完全削除**
  - `spec_grag/cli.py:292-293` の dispatch (`if cmd == "inject"`) を削除
  - `spec_grag/inject.py:66-151` の `run_spec_inject` 関数を**完全削除** or **freshness gate のみを返す内部関数として残す**（後述）
- 追加対象 (コード):
  - 各 inject-* (`run_inject_search` / `run_inject_section` / `run_inject_chapters` / `run_inject_purpose` / `run_inject_conflicts`) の冒頭に freshness gate チェックを追加:
    ```python
    freshness_report = _read_freshness_artifact(project)
    gate_decision = build_freshness_gate_decision(freshness_report, command="inject-<name>")
    if gate_decision.get("should_stop"):
        return _stopped_result(...)
    ```
  - `run_spec_realign` の冒頭にも同じ freshness gate チェックを追加 ([realign.py:91-101](spec_grag/realign.py#L91-L101) の改修)
  - F-2 で `run_spec_realign` から `run_spec_inject` 呼出を削除する場合、`realign` 側で独立に freshness gate を持つ
- 削除対象 (外部設計書):
  - §8.4 [行 763](doc/EXTERNAL_DESIGN.ja.md#L763) の「課題プロンプトの gate probe | `spec-grag inject "<task>"` | freshness report、pending conflict、`needs_agent_constraints` フラグ」行を**削除**
  - §3.3 / §2.8 / §6.3 の freshness gate / pending conflict gate / watcher gate の記述は、`spec-grag inject-*` 全コマンドに適用されることを明示するように整理
- Agent template / SKILL 改訂対象:
  - [spec-inject.md:16](spec_grag/templates/.claude/commands/spec-inject.md#L16) の「2. project root で gate probe を実行する: `spec-grag inject "$TASK"`。...」を**削除**し、「2. Agentic Search を行う。各 inject-* コマンドは freshness / pending conflict / watcher 実行中なら自動的に停止する」に書き換え
  - [spec-realign.md:16](spec_grag/templates/.claude/commands/spec-realign.md#L16) も同様
  - [SKILL.md:29](spec_grag/templates/.codex/skills/spec-grag/SKILL.md#L29) も同様
  - 「gate probe」「probe」という用語自体を template から削除
- test 削除 / 更新対象:
  - `tests/test_spec_inject.py` の `spec-grag inject` (gate probe) を直接呼ぶ test (`test_spec_inject_reads_freshness_artifact_without_recomputing_core`, `test_t_e01_fresh_core_then_inject_returns_minimal_constraint_shape`, `test_t_i08_inject_does_not_call_agentic_llm_provider_and_validates_constraints` 等の一部) を、各 inject-* で gate がかかる test に書き換え
  - 新規追加: 各 inject-* (`inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts`) について「freshness blocked のとき stop を返す」test を追加
  - `realign` 側も同様
- 既存ユーザーへの影響:
  - **大きい**: 「事前 probe」のワークフローを使っているユーザーは、各 inject-* を直接呼んで stop を判定する形に変更
  - 直接 `spec-grag inject "<task>"` を実行していたユーザーは「コマンドなし」エラー
  - template / SKILL 経由のユーザーは新 template に追従するだけ
  - CHANGELOG / migration ガイドに「**`spec-grag inject` サブコマンドは廃止。各 inject-* が自身で gate を持つ**」を明記

**F-D (2026-05-18 確定、選択肢 A)**:

- 変更対象 (コード):
  - `spec_grag/inject.py:779-818` `run_inject_purpose` の戻り値構造を変更:
    - 現状: `{"command", "project_root", "status", "purpose", "core_concept", "warnings"}` (`purpose` / `core_concept` は全文)
    - 変更後: `{"command", "project_root", "status", "purpose": "<全文>", "core_concept_path": "<path>", "warnings"}` (`purpose` は全文維持、`core_concept` は path のみ)
    - Core Concept の存在チェック・read エラー処理は維持（warning は `core_concept_path_missing` のような形）
  - `spec_grag/inject.py:752-776` `run_inject_chapters` の戻り値構造を変更:
    - 現状: `{"command", "project_root", "status", "chapter_anchors", "warnings"}` (`chapter_anchors` は全体)
    - 変更後: `{"command", "project_root", "status", "chapter_anchors_path": "<path>", "warnings"}` (path のみ)
    - artifact 存在チェックは維持（warning は `chapter_anchors_path_missing` のような形）
  - `spec_grag/inject.py:821-867` `run_inject_conflicts` は**変更なし**（全件返却維持）
  - `spec_grag/inject.py` の helper (`_read_json_file`, `_read_text_or_warning` 等) のうち、Purpose / Core Concept / chapter の全文 read 経路を整理
  - **CLI 戻り値に `guidance` field をハードコードしない**（ユーザー指摘により）
- 変更対象 (外部設計書):
  - §8.4 [行 766-767](doc/EXTERNAL_DESIGN.ja.md#L766-L767) の戻り値記述を変更:
    - `inject-chapters` → `chapter_anchors.json の path`
    - `inject-purpose` → `purpose_file 全文 + concept_file の path`
  - §3.4 [行 226](doc/EXTERNAL_DESIGN.ja.md#L226) 「Source Specs を丸ごと投入しない」原則を artifact (Core Concept / chapter_anchors) にも拡張する記述を追加
- Agent template / SKILL 改訂対象（**CLI ではなく template に指示を書く**）:
  - [spec-inject.md path ② chapter_anchors](spec_grag/templates/.claude/commands/spec-inject.md): 「`spec-grag inject-chapters` → 返却 `chapter_anchors_path` を Read で読む → 関連章を特定 → path ① と同様に Agentic Search」と書く
  - [spec-inject.md path ③ Purpose / Core Concept](spec_grag/templates/.claude/commands/spec-inject.md): 「`spec-grag inject-purpose` → 返却 `purpose` (全文) と `core_concept_path` を確認 → Purpose 全文から抽出 → Core Concept は `Read <core_concept_path>` で部分取得」と書く
  - [spec-realign.md](spec_grag/templates/.claude/commands/spec-realign.md) も同様
  - [SKILL.md](spec_grag/templates/.codex/skills/spec-grag/SKILL.md) の path ② / ③ も同様
- test 更新対象:
  - `tests/test_inject_cli_extension.py` の `test_inject_chapters_returns_artifact`、`test_inject_purpose_returns_full_text` 等の test を新返却構造に書き換え
  - `chapter_anchors` / `core_concept` 全文の代わりに `chapter_anchors_path` / `core_concept_path` が返ることを検証する test に変更
- 既存ユーザーへの影響:
  - **中**: `inject-chapters` / `inject-purpose` の戻り値構造が変わるため、CLI 直接呼び出しユーザーは戻り値の handling 変更
  - template / SKILL 経由のユーザーは新 template に追従するだけ
  - CHANGELOG / migration ガイドに「**`inject-chapters` は path のみ返却、`inject-purpose` は Purpose 全文 + Core Concept path 返却**」を明記

修正が必要な場合、`doc/EXTERNAL_DESIGN.ja.md` の改訂 PR と、対応する実装変更 PR を別々に作る。本書の §1 〜 §6 への参照を PR description に含めると追跡しやすい。

---

## 付録 A: 監査成果物一覧

| 成果物 | 内容 | 行数 |
|---|---|---|
| `doc/監査-CODEX/STEP1A_INVENTORY.ja.md` | 機械的インベントリ（ファイル / シンボル / 設定 / リテラル / 外部接続 grep） | 466 |
| `doc/監査-CODEX/STEP1B_FLOWS.ja.md` | 9 CLI フロー深掘り | 528 |
| `doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md` | 横断観点表（接続 × CLI、artifact × CLI、失敗、判断、設定重複、dead） | 203 |
| `doc/監査-CODEX/STEP2_METHOD.ja.md` | C4 / arc42 / ADR 方式仕様書（コード由来） | 306 |
| `doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md` | 業界標準との差分判定（7 判定軸） | 218 |
| `doc/監査-CODEX/STEP4_CONFORMANCE.ja.md` | 外部設計書との整合チェック（9 件 + 30 件、不整合 6 / 過剰 2 / 不足 0 / 未確認 8 / 整合 20） | 394 |
| `doc/監査-CODEX/STEP5_FINDINGS_AND_REMEDIATION.ja.md` | 本書、監査結果整理 + 修正方針 | （本書） |

## 付録 B: 監査プロセスの再現

本監査の再現に必要なものは次:

- `doc/監査-CODEX/PROMPTS/step1a.md` 〜 `step4.md` の仕様書
- `doc/監査-CODEX/PROMPTS/codex_prompt_step1a.md` 〜 `codex_prompt_step4.md` の Codex 起動 prompt
- `doc/監査/STANDARD_GRAG_PATTERNS.ja.md`（業界標準資料、Phase 2 で作成済み）
- 監査対象リポジトリ（本監査時 commit hash: `2aa49dd03416f14ae8b2c9791361a58112ff5611`）

別プロジェクトに監査プロセスを適用する場合、業界標準資料を該当ドメインの基準に置き換え、対象 CLI と target 範囲を Step 1-A で再定義する。
