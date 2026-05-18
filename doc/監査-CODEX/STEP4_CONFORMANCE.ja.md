# Step 4 外部設計書との整合チェック

## §0. 監査範囲

- commit hash: `2aa49dd03416f14ae8b2c9791361a58112ff5611`
- 前提とした前段成果物:
  - `doc/監査-CODEX/STEP1A_INVENTORY.ja.md`
  - `doc/監査-CODEX/STEP1B_FLOWS.ja.md`
  - `doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md`
  - `doc/監査-CODEX/STEP2_METHOD.ja.md`
  - `doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md`
- 外部設計書のパス: `doc/EXTERNAL_DESIGN.ja.md`
- 本 Step で判定根拠として使った外部設計書は `doc/EXTERNAL_DESIGN.ja.md:1-1138` である。
- 本 Step で判定根拠として使った実装事実は、主に `doc/監査-CODEX/STEP2_METHOD.ja.md:1-306` と `doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:183-195` である。

本 Step で新規 grep / line read した範囲:

```text
$ nl -ba doc/監査-CODEX/PROMPTS/step1a.md
$ nl -ba doc/監査-CODEX/PROMPTS/step1b.md
$ nl -ba doc/監査-CODEX/PROMPTS/step1c.md
$ nl -ba doc/監査-CODEX/PROMPTS/step2.md
$ nl -ba doc/監査-CODEX/PROMPTS/step3.md
$ nl -ba doc/監査-CODEX/PROMPTS/step4.md
$ nl -ba doc/監査-CODEX/STEP1A_INVENTORY.ja.md
$ nl -ba doc/監査-CODEX/STEP1B_FLOWS.ja.md
$ nl -ba doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md
$ nl -ba doc/監査-CODEX/STEP2_METHOD.ja.md
$ nl -ba doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md
$ nl -ba doc/監査/STANDARD_GRAG_PATTERNS.ja.md
$ rg -n '^#{1,6} ' doc/EXTERNAL_DESIGN.ja.md
$ nl -ba doc/EXTERNAL_DESIGN.ja.md | sed -n '1,220p'
$ nl -ba doc/EXTERNAL_DESIGN.ja.md | sed -n '221,440p'
$ nl -ba doc/EXTERNAL_DESIGN.ja.md | sed -n '441,660p'
$ nl -ba doc/EXTERNAL_DESIGN.ja.md | sed -n '661,880p'
$ nl -ba doc/EXTERNAL_DESIGN.ja.md | sed -n '881,1138p'
$ rg -n 'GRAG|GraphRAG|lightweight|core_progress|progress|DEBUG|debug|SPEC_GRAG_DEBUG|SPEC_GRAG_FAKE|section_collection|vector_store\.section_collection|vector_store\.collection|--use-cache|use-cache' doc/EXTERNAL_DESIGN.ja.md
```

denylist について:

- `doc/DESIGN.ja.md` / `doc/AGENTS.md` / `doc/TODO.ja.md` / `doc/CHANGELOG.ja.md` / `archive/` / `BAK/` / `.spec-grag/` / `README.md` は本 Step の判定根拠として開いていない。
- 作業ルール確認として `CLAUDE.md` と `.codex/skills/spec-grag/SKILL.md` を読んだ。これはリポジトリ共通指示と skill 指示に従ったものであり、本書の照合判定根拠には使っていない。
- 「どちらが正しい」を判定しない制約は、各項目で外部設計書の記述と Step 2 の実装事実を並べ、人間判断項目を問いの形に限定することで守る。

本書で使う内部ラベルの範囲:

- `provider` は、`doc/EXTERNAL_DESIGN.ja.md:504` に出る LLM provider、embedding provider、vector store provider の総称として使う。対象は `.spec-grag/config.toml` で指定される LLM、埋め込み生成、vector store 接続先であり、本 Step では失敗時の報告契約と fake 指定の扱いを照合する。
- `smoke` は、短時間の疎通確認を指す内部ラベルとして使う。本書では Step 3 §5 の `fake provider / fallback / warning result` 引き継ぎ項目に含まれる test / smoke 例外指定の扱いだけを指し、通常実行経路の完了判定としては扱わない。
- `degraded` は、Step 3 §5 の `degraded warning` という引き継ぎ語として使う。本書では `/spec-core` または `/spec-inject` が完全な成功とは別に warning / diagnostics / freshness へ何を出すかを確認する対象名である。
- `stale` は、古い保持情報または古い検索点を表す状態名として、外部設計書と Step 2 の該当記述を引用する場合にだけ使う。本 Step では `stale_points_deleted` や freshness gate の扱いを照合する文脈に限定する。
- `<project_root>` は、対象プロジェクトのルートディレクトリを指す。`doc/EXTERNAL_DESIGN.ja.md:891-899` の設定ファイル配置を照合する箇所でだけ使う。

## §1. 外部設計書の構造

`doc/EXTERNAL_DESIGN.ja.md` の章・節構成は次のとおりである。`doc/EXTERNAL_DESIGN.ja.md:177-180` は code fence 内の Markdown 見出し例であり、本書の節として扱わない。

| 節番号 | 節タイトル | 行範囲 |
|---|---|---|
| 表題 | SPEC-grag 外部設計書 | `doc/EXTERNAL_DESIGN.ja.md:1-6` |
| 1 | 目的 | `doc/EXTERNAL_DESIGN.ja.md:7-25` |
| 2 | 用語と範囲 | `doc/EXTERNAL_DESIGN.ja.md:26-157` |
| 2.1 | Purpose | `doc/EXTERNAL_DESIGN.ja.md:30-47` |
| 2.2 | Source Specs | `doc/EXTERNAL_DESIGN.ja.md:48-53` |
| 2.3 | Core Concept | `doc/EXTERNAL_DESIGN.ja.md:54-71` |
| 2.4 | Section | `doc/EXTERNAL_DESIGN.ja.md:72-84` |
| 2.5 | Section Metadata | `doc/EXTERNAL_DESIGN.ja.md:85-88` |
| 2.6 | Section Search Keys | `doc/EXTERNAL_DESIGN.ja.md:89-94` |
| 2.6.1 | Section Identifiers | `doc/EXTERNAL_DESIGN.ja.md:95-105` |
| 2.7 | Related Sections | `doc/EXTERNAL_DESIGN.ja.md:106-115` |
| 2.8 | Conflict Review Item | `doc/EXTERNAL_DESIGN.ja.md:116-136` |
| 2.9 | Chapter Key Anchor | `doc/EXTERNAL_DESIGN.ja.md:137-151` |
| 2.10 | Agentic Search | `doc/EXTERNAL_DESIGN.ja.md:152-157` |
| 3 | SPEC-grag の動作モデル | `doc/EXTERNAL_DESIGN.ja.md:158-237` |
| 3.1 | Source Specs を Section に分割する | `doc/EXTERNAL_DESIGN.ja.md:170-182` |
| 3.2 | 保持物を生成する | `doc/EXTERNAL_DESIGN.ja.md:183-190` |
| 3.3 | 保持物の鮮度を保つ | `doc/EXTERNAL_DESIGN.ja.md:191-209` |
| 3.4 | 制約を生成する | `doc/EXTERNAL_DESIGN.ja.md:210-231` |
| 3.5 | 回答を生成する | `doc/EXTERNAL_DESIGN.ja.md:232-237` |
| 4 | 保持物 | `doc/EXTERNAL_DESIGN.ja.md:238-289` |
| 4.1 | 保持物の物理配置 | `doc/EXTERNAL_DESIGN.ja.md:258-289` |
| 5 | 責務境界 | `doc/EXTERNAL_DESIGN.ja.md:290-340` |
| 5.1 | Human | `doc/EXTERNAL_DESIGN.ja.md:292-301` |
| 5.2 | Agent / LLM | `doc/EXTERNAL_DESIGN.ja.md:302-317` |
| 5.3 | CLI / SPEC-grag | `doc/EXTERNAL_DESIGN.ja.md:318-340` |
| 6 | コマンド体系 | `doc/EXTERNAL_DESIGN.ja.md:341-476` |
| 6.1 | Agent 別 command / skill 入口 | `doc/EXTERNAL_DESIGN.ja.md:354-364` |
| 6.2 | Setup Script | `doc/EXTERNAL_DESIGN.ja.md:365-457` |
| 6.2.1 | System Setup Script | `doc/EXTERNAL_DESIGN.ja.md:369-399` |
| 6.2.2 | Project Setup Script | `doc/EXTERNAL_DESIGN.ja.md:400-457` |
| 6.3 | spec-grag-watch | `doc/EXTERNAL_DESIGN.ja.md:458-476` |
| 7 | `/spec-core [--all|-a]` | `doc/EXTERNAL_DESIGN.ja.md:477-686` |
| 7.1 | 目的 | `doc/EXTERNAL_DESIGN.ja.md:479-505` |
| 7.2 | 入力 | `doc/EXTERNAL_DESIGN.ja.md:506-526` |
| 7.3 | 動作 | `doc/EXTERNAL_DESIGN.ja.md:527-563` |
| 7.4 | 出力 | `doc/EXTERNAL_DESIGN.ja.md:564-686` |
| 8 | `/spec-inject [<課題プロンプト>]` | `doc/EXTERNAL_DESIGN.ja.md:687-847` |
| 8.1 | 目的 | `doc/EXTERNAL_DESIGN.ja.md:689-695` |
| 8.2 | 入力 | `doc/EXTERNAL_DESIGN.ja.md:697-709` |
| 8.3 | Agent / LLM が行う作業 | `doc/EXTERNAL_DESIGN.ja.md:710-756` |
| 8.4 | CLI が提供する操作 | `doc/EXTERNAL_DESIGN.ja.md:757-782` |
| 8.5 | 通常出力 | `doc/EXTERNAL_DESIGN.ja.md:783-827` |
| 8.6 | 停止時出力 | `doc/EXTERNAL_DESIGN.ja.md:828-847` |
| 9 | `/spec-realign [<課題プロンプト>]` | `doc/EXTERNAL_DESIGN.ja.md:848-888` |
| 9.1 | 目的 | `doc/EXTERNAL_DESIGN.ja.md:850-855` |
| 9.2 | 動作 | `doc/EXTERNAL_DESIGN.ja.md:856-865` |
| 9.3 | Answer 生成契約 | `doc/EXTERNAL_DESIGN.ja.md:866-878` |
| 9.4 | CLI フラグ | `doc/EXTERNAL_DESIGN.ja.md:879-888` |
| 10 | 設定ファイル | `doc/EXTERNAL_DESIGN.ja.md:889-1103` |
| 10.1 | 設定ファイル配置 | `doc/EXTERNAL_DESIGN.ja.md:891-899` |
| 10.2 | 設定項目 | `doc/EXTERNAL_DESIGN.ja.md:901-1070` |
| 10.3 | 環境変数 | `doc/EXTERNAL_DESIGN.ja.md:1072-1083` |
| 10.4 | `.gitignore` 推奨設定 | `doc/EXTERNAL_DESIGN.ja.md:1084-1103` |
| 11 | エラー契約 | `doc/EXTERNAL_DESIGN.ja.md:1104-1123` |
| 12 | 外部設計で扱わないこと | `doc/EXTERNAL_DESIGN.ja.md:1124-1138` |

判定対象から除外する節:

- `doc/EXTERNAL_DESIGN.ja.md:30-47` の Purpose の中身は、人間管理文書の内容をどうあるべきか判断する対象から外す。ただし、Purpose を CLI が読むか、自動更新しないかは照合対象に含める。
- `doc/EXTERNAL_DESIGN.ja.md:54-71` の Core Concept の中身は、人間管理文書の内容をどうあるべきか判断する対象から外す。ただし、Core Concept を CLI が読むか、自動更新しないかは照合対象に含める。

## §2. Step 3 §5 引き継ぎ 9 件の照合

### §2.1. Qdrant collection 名の 3 段優先順位

**Step 3 §5 引き継ぎ内容**: `Qdrant collection 名の 3 段優先順位` は `retrieval.section_collection`、`vector_store.section_collection`、`vector_store.collection` の扱いが外部契約に出るかを確認する項目である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:187)。

**実装の事実**:

- Qdrant collection 名は `retrieval.section_collection` -> `vector_store.section_collection` -> `vector_store.collection` -> `"spec_grag_section"` の順で読む (doc/監査-CODEX/STEP2_METHOD.ja.md:240)。
- 同じ 3 段参照は、`core`、`inject-search`、`inject-section`、`watch` core 経由に影響する (doc/監査-CODEX/STEP2_METHOD.ja.md:251)。

**外部設計書の対応記述**: `doc/EXTERNAL_DESIGN.ja.md:262`: "検索管理 (Qdrant `[retrieval].section_collection`、default `spec_grag_section`)"。`doc/EXTERNAL_DESIGN.ja.md:929`: "`[retrieval]` | `section_collection` | 任意 | `\"spec_grag_section\"` | section-level retrieval 用 Qdrant collection 名。1 Section = 1 vector、payload に summary / search_keys / identifiers / related_sections / heading_path を含む"。

**判定**: 不整合

**判定根拠**: 外部設計書は collection 名の外部設定を `[retrieval].section_collection` として記述する (doc/EXTERNAL_DESIGN.ja.md:262, doc/EXTERNAL_DESIGN.ja.md:929)。Step 2 の実装事実は `vector_store.section_collection` と `vector_store.collection` も順に読む 3 段参照である (doc/監査-CODEX/STEP2_METHOD.ja.md:240, doc/監査-CODEX/STEP2_METHOD.ja.md:251)。同じ collection 名に対応する記述があり、参照する key の範囲が食い違う。

**人間判断項目としてのフラグ**: Qdrant collection 名の外部契約に互換 key `vector_store.section_collection` / `vector_store.collection` を含めるか、外部契約では `[retrieval].section_collection` だけを示し、互換 key は内部互換経路として扱うか。

### §2.2. GRAG / GraphRAG / lightweight related-section retrieval の呼称

**Step 3 §5 引き継ぎ内容**: `GRAG / GraphRAG / lightweight related-section retrieval の呼称` は、graph 構造の永続 store / traversal がない現状と、外部向け方式呼称の一致を確認する項目である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:188)。

**実装の事実**:

- graph 構造の永続 store / traversal は、allowlist 内 grep で観測されない (doc/監査-CODEX/STEP2_METHOD.ja.md:73)。
- Related Sections は target section、confidence、evidence terms、channels、possible conflict を返す配列であり、Qdrant payload に `related_sections` として入る (doc/監査-CODEX/STEP2_METHOD.ja.md:74)。
- Step 3 の方式分類は「業界標準と異なる方式（最も近い呼称: Hybrid RAG + lightweight related-section retrieval）」である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:152)。

**外部設計書の対応記述**: `doc/EXTERNAL_DESIGN.ja.md:20`: "軽量化の方針として、property graph、entity relation graph、hierarchical cluster、Concept 自動更新、広範な conflict 承認フロー、実行モード分岐は標準経路に含めない。" `doc/EXTERNAL_DESIGN.ja.md:1124-1136` は外部設計で扱わないものとして "property graph / entity relation graph / hierarchical cluster の構築" を列挙する。`rg -n 'GRAG|GraphRAG|lightweight' doc/EXTERNAL_DESIGN.ja.md` では、表題の `SPEC-grag` 以外に `GraphRAG` / `lightweight related-section retrieval` の方式呼称は出ない。

**判定**: 未確認

**判定根拠**: 外部設計書は property graph / entity relation graph / hierarchical cluster を標準経路に含めないと記述する (doc/EXTERNAL_DESIGN.ja.md:20, doc/EXTERNAL_DESIGN.ja.md:1135)。一方で、Step 3 が求める業界用語としての `Hybrid RAG + lightweight related-section retrieval` という外部呼称は外部設計書に出ない (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:152, doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:188)。表題の `SPEC-grag` が業界用語の GRAG を指すか、製品名を指すかは本 Step の材料だけでは判定しない。

**人間判断項目としてのフラグ**: `SPEC-grag` という名称を製品名として扱うか、業界用語の GRAG と対応させるか。外部向け方式呼称として `Hybrid RAG + lightweight related-section retrieval` を併記するか。

### §2.3. Related Sections / Summary / Search Keys の evidence 区分

**Step 3 §5 引き継ぎ内容**: `Related Sections / Summary / Search Keys の evidence 区分` は、retrieval aid と source evidence の区別が外部向け説明に出るかを確認する項目である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:189)。

**実装の事実**:

- `validate_constraints` は `SUPPORT_ONLY_ORIGINS` を final evidence_origin にすると `SpecInjectError` を raise する (doc/監査-CODEX/STEP2_METHOD.ja.md:186)。
- Related Sections 出力は `target_section_id` / `evidence_terms` / `channels` / `possible_conflict` を持つ補助 field として payload に入る (doc/監査-CODEX/STEP2_METHOD.ja.md:186)。
- `conflict_review_items.json` は `validate_constraints` が conflict review item evidence を検査する保持ファイルである (doc/監査-CODEX/STEP2_METHOD.ja.md:85)。

**外部設計書の対応記述**: `doc/EXTERNAL_DESIGN.ja.md:87`: "Section Metadata は、Source Specs の各 Section に対して `/spec-core` が生成・更新する検索補助情報の総称である。単独で最終根拠にはしない。" `doc/EXTERNAL_DESIGN.ja.md:93`: "Section Search Keys は根拠ではない。" `doc/EXTERNAL_DESIGN.ja.md:112`: "Related Sections は最終根拠ではないが単なる一時候補でもない。" `doc/EXTERNAL_DESIGN.ja.md:826`: "`/spec-inject` は、検索キー、Section Summary、Related Sections だけを根拠として制約を確定してはいけない。"

**判定**: 整合

**判定根拠**: 外部設計書は Section Metadata、Section Search Keys、Related Sections を最終根拠にしないと記述する (doc/EXTERNAL_DESIGN.ja.md:87, doc/EXTERNAL_DESIGN.ja.md:93, doc/EXTERNAL_DESIGN.ja.md:112, doc/EXTERNAL_DESIGN.ja.md:826)。Step 2 の実装事実は support-only origin を final evidence_origin にすると検査で止める (doc/監査-CODEX/STEP2_METHOD.ja.md:186)。両者は、補助情報と evidence を区別する点で一致する。

**人間判断項目としてのフラグ**: なし。

### §2.4. fake provider / fallback / warning result の状態表現

**Step 3 §5 引き継ぎ内容**: `fake provider / fallback / warning result の状態表現` は、fake provider、degraded warning、failed diagnostics、freshness の区別が外部向け説明に出るかを確認する項目である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:190)。

**実装の事実**:

- `inject-search` は FlagEmbedding / Qdrant import failure を `retriever_unavailable` warning、retriever init failure を `retriever_init_failed` warning、retriever search failure を `retrieval_failed` warning として返す (doc/監査-CODEX/STEP2_METHOD.ja.md:207-209)。
- Qdrant section collection upsert 失敗と FlagEmbedding embed 失敗は failed status と diagnostics に入る (doc/監査-CODEX/STEP2_METHOD.ja.md:199-200)。
- LLM provider selection は `SPEC_GRAG_FAKE_LLM` truthy で fake provider を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:112)。

**外部設計書の対応記述**: `doc/EXTERNAL_DESIGN.ja.md:504`: "`/spec-core` は `.spec-grag/config.toml` で指定された LLM provider、embedding provider、vector store provider をそのまま使う。指定された provider が失敗した場合は、別の provider に黙って切り替えず、失敗として報告する。" `doc/EXTERNAL_DESIGN.ja.md:1074-1081` は `SPEC_GRAG_FAKE_LLM` と `SPEC_GRAG_FAKE_RETRIEVAL` を in-process fake へ切り替える例外指定として記述する。`doc/EXTERNAL_DESIGN.ja.md:1114-1116` は retrieval backend / embedding / dirty stale 系の停止を記述する。

**判定**: 未確認

**判定根拠**: 外部設計書は fake 用環境変数と、provider 失敗時に黙って切り替えない契約を記述する (doc/EXTERNAL_DESIGN.ja.md:504, doc/EXTERNAL_DESIGN.ja.md:1074-1081)。Step 2 は warning / failed diagnostics の実装事実を示すが、`SPEC_GRAG_FAKE_LLM` truthy 時の fake provider 選択が CoreResult / freshness / diagnostics にどの粒度で表れるかは Step 3 自身が未判定事項として残している (doc/監査-CODEX/STEP2_METHOD.ja.md:112, doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:203)。この項目は fake provider の状態表現について判定材料が不足する。

**人間判断項目としてのフラグ**: fake provider を test / smoke 専用の例外指定としてだけ外部設計に残すか、CoreResult / freshness / diagnostics にどう表れるかまで外部契約に含めるか。

### §2.5. Agent 入力による constraints / answer

**Step 3 §5 引き継ぎ内容**: `Agent 入力による constraints / answer` は、CLI が constraints / answer を生成せず、Agent 入力を検査・構造化する境界を確認する項目である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:191)。

**実装の事実**:

- `inject` は Agent-supplied constraints を受け取り、freshness gate と constraints validation を実行して dict を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:53)。
- `realign` は Agent-supplied answer を 4 section dict に構造化して返す (doc/監査-CODEX/STEP2_METHOD.ja.md:54)。
- constraints 生成は CLI に観測されず、`inject` は Agent-supplied constraints の freshness gate と validation を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:268)。

**外部設計書の対応記述**: `doc/EXTERNAL_DESIGN.ja.md:24`: "主導権は Agent / LLM にある。slash command は Agent / LLM に対して探索手順を指示し、CLI は保持物と検索機能を提供する。CLI は最終判断主体ではない。" `doc/EXTERNAL_DESIGN.ja.md:332-338` は CLI が会話区間の最終解釈、制約の最終生成、Answer の自由生成を担当しないと記述する。`doc/EXTERNAL_DESIGN.ja.md:954`: "`/spec-inject` / `/spec-realign` の会話区間解釈、Agentic Search、制約生成、回答生成を行う Agent / LLM は Agent CLI 側で動くため、これらの設定の対象外である。"

**判定**: 整合

**判定根拠**: 外部設計書は Agent / LLM が探索と制約生成、回答生成を行い、CLI は保持物と検索機能を提供する境界を記述する (doc/EXTERNAL_DESIGN.ja.md:24, doc/EXTERNAL_DESIGN.ja.md:332-338, doc/EXTERNAL_DESIGN.ja.md:954)。Step 2 は CLI 側に constraints / answer 生成が観測されず、Agent 入力を検査・構造化する事実を記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:53-54, doc/監査-CODEX/STEP2_METHOD.ja.md:268)。両者は一致する。

**人間判断項目としてのフラグ**: なし。

### §2.6. Section embedding text と source evidence text の違い

**Step 3 §5 引き継ぎ内容**: `Section embedding text と source evidence text の違い` は、embedding 用 representation と本文 evidence の違いが外部向け説明に出るかを確認する項目である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:192)。

**実装の事実**:

- `build_section_embedding_text` は heading_path、summary、search_keys、identifiers を join し、raw body field は入力に入らない (doc/監査-CODEX/STEP2_METHOD.ja.md:239)。
- `build_section_payloads` は `source_document_id`、`source_section_id`、`source_span`、`heading_path`、`summary`、`search_keys`、`identifiers`、`related_sections`、`text` を payload に入れる (doc/監査-CODEX/STEP2_METHOD.ja.md:185)。

**外部設計書の対応記述**: `doc/EXTERNAL_DESIGN.ja.md:264`: "source_document_id / source_span / Section Summary / Section Search Keys / Section Identifiers / Related Sections / heading_path を payload に格納する。1 Section = 1 vector。" `doc/EXTERNAL_DESIGN.ja.md:764` は `inject-search` の戻り値に "source_document_id / source_section_id / source_span / heading / summary / search_keys / identifiers / related_sections / score" を含むと記述する。`doc/EXTERNAL_DESIGN.ja.md:1128-1133` は "embedding provider の実装" と "hybrid retrieval の内部 scoring" を外部設計で扱わないと記述する。

**判定**: 過剰

**判定根拠**: 外部設計書は Qdrant payload と検索結果の source provenance を記述するが、embedding 入力 text が raw body を含まないことまでは契約として記述していない (doc/EXTERNAL_DESIGN.ja.md:264, doc/EXTERNAL_DESIGN.ja.md:764)。Step 2 は embedding 用 text の構成を実装事実として記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:239)。実装に事実があり、外部設計書に対応する契約がない。

**人間判断項目としてのフラグ**: embedding 用 representation と Source Specs 本文 evidence の違いを外部契約に含めるか、外部設計書 §12 の対象外に含まれる内部方式として扱うか。

### §2.7. `core_progress.json` の外部可視性

**Step 3 §5 引き継ぎ内容**: ``core_progress.json` の外部可視性` は、progress file が生成されるが target 9 CLI の読込表に出ない点を外部仕様に出すかを確認する項目である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:193)。

**実装の事実**:

- `core_progress.json` は生成されるが target 9 CLI の読込表に出ず、`CoreProgressTracker` が write し、Step 1-C は読込 CLI なしと記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:90, doc/監査-CODEX/STEP2_METHOD.ja.md:241)。
- `core_progress.json` は progress write 対象になる (doc/監査-CODEX/STEP2_METHOD.ja.md:241)。

**外部設計書の対応記述**: `doc/EXTERNAL_DESIGN.ja.md:596`: "全 Section を登録し直した実行は `core_progress.json` の `stages.section_collection_upsert.action = \"upserted_full\"` として記録する。" `doc/EXTERNAL_DESIGN.ja.md:600`: "ユーザーは同じ stage の `diagnostics` で、`sections_upserted_count`、`sections_deleted_count`、`embed_documents_input_size`、`stale_points_deleted` を確認できる。" `doc/EXTERNAL_DESIGN.ja.md:613`: "`.spec-grag/state/core_progress.json` の `stages.related_sections.action` は `regenerated_partial` になる。"

**判定**: 整合

**判定根拠**: 外部設計書は `core_progress.json` に stage action / diagnostics が記録されると記述する (doc/EXTERNAL_DESIGN.ja.md:596, doc/EXTERNAL_DESIGN.ja.md:600, doc/EXTERNAL_DESIGN.ja.md:613)。Step 2 は `core_progress.json` が生成され、target 9 CLI の読込表には出ないと記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:90, doc/監査-CODEX/STEP2_METHOD.ja.md:241)。外部設計書は CLI read API ではなくファイル上の確認を記述しており、生成されるという点は一致する。

**人間判断項目としてのフラグ**: なし。

### §2.8. target 9 CLI 範囲の dead 引数

**Step 3 §5 引き継ぎ内容**: `target 9 CLI 範囲の dead 引数` は、`run_spec_inject` の unused input と CLI 入口の外部契約を確認する項目である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:194)。

**実装の事実**:

- `task_prompt` / `prompt` / `conversation_context` / `provider` / `llm_provider` は `run_spec_inject` 内で削除され、target 9 CLI dead 引数として記録される (doc/監査-CODEX/STEP2_METHOD.ja.md:236, doc/監査-CODEX/STEP2_METHOD.ja.md:254)。
- `inject` は Agent-supplied constraints を受け取り、freshness gate と constraints validation を実行して dict を返す (doc/監査-CODEX/STEP2_METHOD.ja.md:53)。

**外部設計書の対応記述**: `doc/EXTERNAL_DESIGN.ja.md:697-703` は `/spec-inject` 入力として Conversation Context と `<課題プロンプト>` を記述する。`doc/EXTERNAL_DESIGN.ja.md:775-780` は `inject` / `realign` 共通フラグとして `--conversation-context`、`--constraints*`、`--freshness*` を記述する。`doc/EXTERNAL_DESIGN.ja.md:854` は `<課題プロンプト>` 省略時に Agent / LLM が会話区間から中心課題を解釈すると記述する。

**判定**: 不整合

**判定根拠**: 外部設計書は `/spec-inject` の入力として Conversation Context と `<課題プロンプト>` を記述する (doc/EXTERNAL_DESIGN.ja.md:697-703, doc/EXTERNAL_DESIGN.ja.md:775-780)。Step 2 は `run_spec_inject` の `task_prompt` / `prompt` / `conversation_context` が関数内で削除される実装事実を記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:236, doc/監査-CODEX/STEP2_METHOD.ja.md:254)。対応する入力項目があり、CLI 関数内の利用範囲が食い違う。

**人間判断項目としてのフラグ**: `<課題プロンプト>` と `--conversation-context` を CLI が freshness gate / constraints validation に使う外部契約として扱うか、Agent / LLM 専用の上位入力として扱い CLI 実装では消費しない契約として扱うか。

### §2.9. `_debug_*.jsonl` の通常経路との区別

**Step 3 §5 引き継ぎ内容**: ``_debug_*.jsonl` の通常経路との区別` は、debug file が env var 条件で append され、読込 CLI なしである点の説明範囲を確認する項目である (doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:195)。

**実装の事実**:

- provider debug と related prompt debug は env var truthy 時に append され、読込 CLI なし、append のみである (doc/監査-CODEX/STEP2_METHOD.ja.md:94-95, doc/監査-CODEX/STEP2_METHOD.ja.md:242)。

**外部設計書の対応記述**: `doc/EXTERNAL_DESIGN.ja.md:1078-1082` の環境変数表は `SPEC_GRAG_FAKE_LLM`、`SPEC_GRAG_FAKE_RETRIEVAL`、`SPEC_GRAG_QDRANT_URL` を列挙する。`rg -n 'DEBUG|debug|SPEC_GRAG_DEBUG' doc/EXTERNAL_DESIGN.ja.md` では debug JSONL に対応する記述はない。`doc/EXTERNAL_DESIGN.ja.md:1128-1134` は Section Metadata / Chapter Key Anchor の内部生成プロンプト、LLM provider の subprocess 実装、slash command の完全なプロンプト本文を外部設計で扱わないと記述する。

**判定**: 過剰

**判定根拠**: Step 2 は `_debug_provider_invocations.jsonl` と `_debug_related_prompts.jsonl` の conditional append を実装事実として記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:94-95, doc/監査-CODEX/STEP2_METHOD.ja.md:242)。外部設計書の環境変数表には debug 用環境変数がなく、外部設計の対象外節にも debug JSONL の保持ファイル契約はない (doc/EXTERNAL_DESIGN.ja.md:1078-1082, doc/EXTERNAL_DESIGN.ja.md:1128-1134)。実装に事実があり、外部設計書に対応する契約がない。

**人間判断項目としてのフラグ**: debug JSONL を外部設計書の環境変数 / 保持ファイル契約に含めるか、内部調査用の実装詳細として外部設計の対象外に置くか。

## §3. 外部設計書の他の契約項目の照合

| 外部設計書の節 / 行 | 契約内容 | 対応する実装事実 (Step 2 §節番号引用) | 判定 | 判定根拠 | 人間判断項目フラグ |
|---|---|---|---|---|---|
| `doc/EXTERNAL_DESIGN.ja.md:20-24` | property graph / entity relation graph / hierarchical cluster を標準経路に含めず、CLI は保持物と検索機能を提供する。 | graph 構造の永続 store / traversal は観測されず、constraints 生成は CLI に観測されない (doc/監査-CODEX/STEP2_METHOD.ja.md:73, doc/監査-CODEX/STEP2_METHOD.ja.md:268)。 | 整合 | 外部設計書は graph 構造を標準経路に含めないと記述し、Step 2 も graph 永続 store / traversal を観測していない。CLI が最終判断主体でない点も Agent 入力 validation と対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:48-53` | Source Specs は `[sources].include` に一致する Markdown 文書で、今回の課題に対する既存仕様または修正対象になる。 | `core` は Source Specs markdown を parse し、watch は Source Specs snapshot を読む (doc/監査-CODEX/STEP2_METHOD.ja.md:48-52, doc/監査-CODEX/STEP2_METHOD.ja.md:162)。 | 整合 | 外部設計書は Source Specs を config 由来の Markdown 文書群とし、Step 2 は core / watch がその文書群を読む事実を記録する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:72-83` | Section は Source Specs を Markdown 見出しで分割した単位で、Source Retrieval Index と inject / realign の検索結果単位である。 | Source Specs Markdown parse、section manifest、Qdrant section collection、`inject-search` payload が記録される (doc/監査-CODEX/STEP2_METHOD.ja.md:48-60, doc/監査-CODEX/STEP2_METHOD.ja.md:267-271)。 | 整合 | 外部設計書の Section 単位処理と、Step 2 の section manifest / Qdrant section collection / inject-search payload は対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:83` | `source_section_id` は `<file_path>#<heading_slug>` 形式で、Source Specs 全体で一意でなければならない。 | Step 2 は payload に `source_section_id` が入ることを記録するが、`<file_path>#<heading_slug>` 形式と一意性の検査事実は同じ粒度で記録していない (doc/監査-CODEX/STEP2_METHOD.ja.md:59-60, doc/監査-CODEX/STEP2_METHOD.ja.md:184-185)。 | 未確認 | 外部設計書に id 形式と一意性の契約がある。Step 2 は `source_section_id` の使用は示すが、形式と一意性契約の実装事実が不足する。 | `source_section_id` の形式・一意性を外部契約として維持する場合、Step 2 由来の方式仕様書に対応する実装事実を追加で確認するか。 |
| `doc/EXTERNAL_DESIGN.ja.md:85-115` | Section Metadata / Search Keys / Identifiers / Related Sections / Chapter Key Anchor は検索補助であり、最終根拠にしない。 | support-only origin は final evidence_origin にできず、Related Sections は補助 field として payload に入る (doc/監査-CODEX/STEP2_METHOD.ja.md:186, doc/監査-CODEX/STEP2_METHOD.ja.md:238)。 | 整合 | 外部設計書の根拠区分と Step 2 の constraints validation が対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:116-136` | pending Conflict Review Item がある場合、`/spec-inject` と `/spec-realign` は制約生成や回答生成へ進んではいけない。 | `conflict_review_items.json` は constraints 検査に使われ、freshness gate は pending conflict を止める経路を持つ (doc/監査-CODEX/STEP2_METHOD.ja.md:85, doc/監査-CODEX/STEP2_METHOD.ja.md:201-204)。 | 整合 | 外部設計書の pending conflict stop と、Step 2 の freshness gate / conflict review evidence 検査は対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:137-151` | Chapter Key Anchor は章単位入口であり、最終根拠ではない。 | `inject-chapters` は `chapter_anchors.json` を lookup output として返し、missing は warning になる (doc/監査-CODEX/STEP2_METHOD.ja.md:86, doc/監査-CODEX/STEP2_METHOD.ja.md:150, doc/監査-CODEX/STEP2_METHOD.ja.md:213)。 | 整合 | 外部設計書は chapter anchor を入口とし、Step 2 は lookup output と warning 経路を記録する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:152-157` | Agentic Search は Agent / LLM の行動であり、CLI は探索方針を自律的に決めない。 | constraints 生成は CLI に観測されず、Agent-supplied constraints を CLI が検査する (doc/監査-CODEX/STEP2_METHOD.ja.md:71, doc/監査-CODEX/STEP2_METHOD.ja.md:268)。 | 整合 | 外部設計書の Agentic Search 境界と、Step 2 の Agent 入力 validation は対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:170-187` | Section 分割の最大見出し深さは `[section].max_heading_level` で指定し、`/spec-core` は incremental update を基本にする。 | Section heading 変更 / 追加 / 削除 / 並べ替えは section hash / list 指紋、watcher diff、state mismatch で扱う (doc/監査-CODEX/STEP2_METHOD.ja.md:162-167)。 | 整合 | 外部設計書は Section hash に基づく incremental update を記述し、Step 2 は section hash / list 指紋による更新判定を記録する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:193-206` | `/spec-inject` と `/spec-realign` は保持物が最新でない場合は停止し、`/spec-core` を自動実行しない。 | `inject` は freshness gate を読み、blocked / failed 状態で止まる。`run_spec_inject` は `run_spec_core` を呼ばない (doc/監査-CODEX/STEP2_METHOD.ja.md:87, doc/監査-CODEX/STEP2_METHOD.ja.md:120-122, doc/監査-CODEX/STEP2_METHOD.ja.md:250)。 | 整合 | 外部設計書の freshness gate と自動 core 非実行は、Step 2 の inject flow と一致する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:224-230` | 会話区間は根拠ではなく、全文を最終コンテキストとして扱うのは明示的な全文レビュー時だけである。 | constraints は Agent-supplied input として渡され、CLI は evidence_origin を検査する (doc/監査-CODEX/STEP2_METHOD.ja.md:53, doc/監査-CODEX/STEP2_METHOD.ja.md:186, doc/監査-CODEX/STEP2_METHOD.ja.md:268)。 | 整合 | 外部設計書は会話区間と evidence を分け、Step 2 は evidence_origin validation を記録する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:238-256` | Purpose / Core Concept は人間が更新し、Core Concept 乖離通知は保証しない。 | Purpose / Core Concept は core が読み、`/spec-core` はこれらを自動更新しない (doc/監査-CODEX/STEP2_METHOD.ja.md:52, doc/監査-CODEX/STEP2_METHOD.ja.md:264)。 | 整合 | 外部設計書の人間更新対象と、Step 2 の read-only 実装事実は対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:269-280` | `.spec-grag/context/` には `conflict_review_items.json` / `chapter_anchors.json`、`.spec-grag/state/` には `section_manifest.json` / `freshness.json` / watcher state / queue / retrieval と related の状態記録ファイルを置く。 | Step 2 は 14 件の保持ファイル分類を記録し、`section_manifest.json`、`conflict_review_items.json`、`chapter_anchors.json`、`freshness.json`、`retrieval_index_state.json`、`related_sections_state.json` を分類する (doc/監査-CODEX/STEP2_METHOD.ja.md:82-99)。 | 整合 | 外部設計書の主要保持ファイル配置と、Step 2 の保持ファイル分類は対応する。`core_progress.json` と debug JSONL は §2.7 / §2.9 で別途扱った。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:279-280` | `.spec-grag/state/retrieval_index_state.json` は section hash 指紋 + embedding / retrieval 設定指紋を保存し、一致時は upsert / embedding 計算を省略し、不一致等では通常 upsert 経路に fallback する。`.spec-grag/state/related_sections_state.json` は section 集合 hash + candidate generation / LLM selection 設定指紋を保存し、一致時は前回結果を継承する。 | Step 2 は `.spec-grag/state/retrieval_index_state.json` と `.spec-grag/state/related_sections_state.json` を skip / partial 判定に使う状態記録ファイルとして記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:88-89, doc/監査-CODEX/STEP2_METHOD.ja.md:266)。 | 整合 | 外部設計書の状態記録ファイルの保存内容、参照する `/spec-core` stage、一致時 / 不一致時の挙動は、Step 2 の skip / partial 判定記録と対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:369-429` | `spec-grag-setup-system` と `spec-grag-setup-project` は外部依存確認と project への設定・Agent 入口配置を行う。 | Step 2 の対象 CLI は target 9 CLI であり、setup script は方式仕様書の主要データフロー対象に含まれていない (doc/監査-CODEX/STEP2_METHOD.ja.md:8, doc/監査-CODEX/STEP2_METHOD.ja.md:293-295)。 | 未確認 | 外部設計書に setup script の契約があるが、Step 2 の方式仕様書は target 9 CLI 中心で setup script の実装事実を同じ粒度で扱っていない。 | setup script の契約を Step 4 の照合対象に含め続ける場合、Step 2 相当のコード由来事実を追加で用意するか。 |
| `doc/EXTERNAL_DESIGN.ja.md:458-476` | `spec-grag-watch` は Source Specs の変更を検知し、background で incremental update を繰り返し、実行中は freshness gate が `blocked` になる。 | `watch` は Source Specs snapshot、state / queue JSON、lock を呼び、queue がある場合に `run_spec_core_for_watcher` 経由で core を呼ぶ (doc/監査-CODEX/STEP2_METHOD.ja.md:49, doc/監査-CODEX/STEP2_METHOD.ja.md:154, doc/監査-CODEX/STEP2_METHOD.ja.md:172)。 | 整合 | 外部設計書の watcher 動作と、Step 2 の watch データフロー / freshness write は対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:496-502` | `/spec-core --all` は LLM 由来 cache を再生成し、`--rebuild` は Qdrant collection を full recreate する。`--use-cache` は deprecated で無指定と同等である。 | Step 2 は `--all` / `--rebuild` / `--use-cache` を入力として記録し、`run_full and not use_cache` のとき cache JSON を削除すると記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:43, doc/監査-CODEX/STEP2_METHOD.ja.md:54)。 | 不整合 | `--all` と `--rebuild` の大枠は対応するが、外部設計書は `--use-cache` を無指定と同等と記述し、Step 2 は `use_cache` が cache clear 条件に入る実装事実を記録する。 | `--use-cache` を外部契約上の no-op とするか、cache clear に影響する互換 flag として記述するか。 |
| `doc/EXTERNAL_DESIGN.ja.md:504` | 指定された LLM / embedding / vector store が失敗した場合、別の接続先設定に黙って切り替えず、失敗として報告する。 | Qdrant / FlagEmbedding / LLM provider の失敗は failed status / diagnostics / warnings に記録される (doc/監査-CODEX/STEP2_METHOD.ja.md:198-209)。 | 整合 | 外部設計書の silent fallback 禁止と、Step 2 の failed / warning result は対応する。fake provider の詳細は §2.4 で未確認にした。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:564-686` | CoreResult は retrieval / related / conflict / freshness / warning を出力し、retrieval / related の status と conflict decision payload を扱う。 | CoreResult dict、retrieval / related status、conflict review staleness、freshness report は Step 2 に記録される (doc/監査-CODEX/STEP2_METHOD.ja.md:73-75, doc/監査-CODEX/STEP2_METHOD.ja.md:88-91, doc/監査-CODEX/STEP2_METHOD.ja.md:168-173, doc/監査-CODEX/STEP2_METHOD.ja.md:197-229)。 | 整合 | 外部設計書の CoreResult と status 群は、Step 2 の core output / failure policy と対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:671-685` | Conflict Review Item の decision 値と状態遷移、high-risk pair の判定対象を記述する。 | Step 2 は conflict review item evidence と pending conflict gate を記録するが、decision 値 `prefer_a` などの状態遷移一覧は同じ粒度で記録していない (doc/監査-CODEX/STEP2_METHOD.ja.md:85, doc/監査-CODEX/STEP2_METHOD.ja.md:168, doc/監査-CODEX/STEP2_METHOD.ja.md:203)。 | 未確認 | 外部設計書に decision 値と遷移の契約がある。Step 2 は conflict review の存在と staleness / gate は示すが、decision enum の全件対応は不足する。 | Conflict Review Item の decision enum を外部契約として維持する場合、Step 2 相当のコード由来事実で全 enum を照合するか。 |
| `doc/EXTERNAL_DESIGN.ja.md:757-769` | CLI は gate probe、hybrid retrieval、Section payload lookup、chapter anchor、Purpose / Core Concept、Conflict Review Items、制約検証を提供する。 | `inject` / `inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` のデータフローは Step 2 に記録される (doc/監査-CODEX/STEP2_METHOD.ja.md:50-54, doc/監査-CODEX/STEP2_METHOD.ja.md:147-152, doc/監査-CODEX/STEP2_METHOD.ja.md:181-186)。 | 整合 | 外部設計書が列挙する参照操作は、Step 2 の 6 経路の実装事実と対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:783-810` | `/spec-inject` の人間に見える通常出力は、内部 JSON ではなく読みやすい構造を基本とする。 | `_run_inject_from_args` は JSON を stdout に出し、exit code を返す。`inject` の戻り値は constraints / injectable_context / warnings dict である (doc/監査-CODEX/STEP2_METHOD.ja.md:53, doc/監査-CODEX/STEP2_METHOD.ja.md:122-124)。 | 不整合 | 外部設計書は人間に見える出力を読みやすい構造と記述するが、Step 2 は CLI stdout が JSON であると記録する。slash command / skill 側の表示変換は Step 2 の実装事実には出ていない。 | `/spec-inject` の外部契約を CLI JSON と slash command / skill 表示に分けるか、現在の人間向け出力記述を維持するか。 |
| `doc/EXTERNAL_DESIGN.ja.md:812-827` | 制約セットは `statement` / `evidence_origin` / `evidence_ref` を必須とし、補助情報だけで確定してはいけない。 | constraints validation は required fields と support-only origins を検査する (doc/監査-CODEX/STEP2_METHOD.ja.md:116, doc/監査-CODEX/STEP2_METHOD.ja.md:186)。 | 整合 | 外部設計書の制約 JSON 形状と evidence_origin 制限は、Step 2 の validation 実装事実と対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:848-888` | `/spec-realign` は `/spec-inject` と同じ手順で制約を生成し、回答候補を区分して出力する。 | `realign` は `run_spec_inject` を呼び、Agent-supplied answer を `constraints` / `answer` / `realign_answer` dict に構造化する (doc/監査-CODEX/STEP2_METHOD.ja.md:54, doc/監査-CODEX/STEP2_METHOD.ja.md:153, doc/監査-CODEX/STEP2_METHOD.ja.md:269)。 | 整合 | 外部設計書の realign 構造と、Step 2 の inject 経由 / answer structure 実装事実は対応する。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:891-899` | 設定ファイルは `<project_root>/.spec-grag/config.toml` に置き、親ディレクトリへの自動探索はしない。 | Step 2 は `.spec-grag/config.toml` を読むことを記録するが、親ディレクトリへの自動探索なしの実装事実は同じ粒度では記録していない (doc/監査-CODEX/STEP2_METHOD.ja.md:48, doc/監査-CODEX/STEP2_METHOD.ja.md:107)。 | 未確認 | 外部設計書には配置と探索範囲の契約がある。Step 2 は config read の存在は記録するが、親探索なしの確認材料が不足する。 | 親ディレクトリ探索なしを外部契約として維持する場合、実装事実を Step 2 相当の方式仕様書へ追加するか。 |
| `doc/EXTERNAL_DESIGN.ja.md:901-1070` | 設定項目表は sources/core/context/section/section_metadata/chapter_anchor/llm/retrieval/embedding/vector_store/limits/watcher を列挙する。 | Step 2 は config / provider / retrieval / watcher の主要接続と、Qdrant collection 名の 3 段参照を記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:38-43, doc/監査-CODEX/STEP2_METHOD.ja.md:240-251)。 | 不整合 | 外部設計書の設定表は `vector_store.section_collection` / `vector_store.collection` を列挙しないが、Step 2 は raw config からその 2 key も読むと記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:240-251)。この不整合は §2.1 と同じ対象である。 | §2.1 と同じ。 |
| `doc/EXTERNAL_DESIGN.ja.md:1072-1083` | 環境変数表は `SPEC_GRAG_FAKE_LLM`、`SPEC_GRAG_FAKE_RETRIEVAL`、`SPEC_GRAG_QDRANT_URL` を列挙する。 | Step 2 は `SPEC_GRAG_FAKE_LLM` と fake provider 選択、debug env var append を記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:112, doc/監査-CODEX/STEP2_METHOD.ja.md:242)。 | 不整合 | 外部設計書の環境変数表は debug env var を列挙しない一方、Step 2 は debug JSONL append の env var 条件を記録する。この不整合は §2.9 と同じ対象である。 | §2.9 と同じ。 |
| `doc/EXTERNAL_DESIGN.ja.md:1084-1103` | `.spec-grag/context/`、`.spec-grag/cache/`、`.spec-grag/state/`、`.env` の gitignore 推奨を記述する。 | Step 2 は state / context / cache / debug / Qdrant collection の保持ファイル分類を記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:82-99)。 | 整合 | 外部設計書の gitignore 推奨カテゴリと、Step 2 の保持ファイル分類は大枠で対応する。debug JSONL と core_progress の外部可視性は §2.7 / §2.9 で別途扱った。 | なし |
| `doc/EXTERNAL_DESIGN.ja.md:1104-1123` | config / Purpose / Core Concept / Source Specs missing、provider failure、pending conflict、watcher running、setup script failure のエラー契約を記述する。 | Step 2 は config error、Purpose / Core Concept missing、retrieval failure、pending conflict、watcher exception / lock を記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:194-227)。setup script は Step 2 target 9 CLI 外である (doc/監査-CODEX/STEP2_METHOD.ja.md:8)。 | 未確認 | target 9 CLI のエラー契約は対応するが、setup script 系のエラー契約は Step 2 に同じ粒度で出ていない。 | setup script のエラー契約を同一監査範囲に含めるか、別監査範囲として扱うか。 |
| `doc/EXTERNAL_DESIGN.ja.md:1124-1138` | Section Metadata 内部生成プロンプト、embedding provider 実装、hybrid retrieval 内部 scoring、LLM provider subprocess 実装、property graph 構築は外部設計で扱わない。 | Step 2 は embedding text 構成、LLM subprocess、hybrid retrieval、debug JSONL を実装事実として記録する (doc/監査-CODEX/STEP2_METHOD.ja.md:50, doc/監査-CODEX/STEP2_METHOD.ja.md:55-59, doc/監査-CODEX/STEP2_METHOD.ja.md:239, doc/監査-CODEX/STEP2_METHOD.ja.md:242)。 | 未確認 | 外部設計書は一部内部方式を対象外に置く。Step 2 はコード由来の方式仕様書としてそれらを記録する。外部契約として対象外にする範囲と、実装事実として記録する範囲の境界は本 Step だけでは確定しない。 | 外部設計書 §12 に、debug JSONL と embedding input text を含めるかを §2.6 / §2.9 と合わせて判断するか。 |

## §4. 不整合の人間判断対象一覧

| 項目 | 外部設計書の記述 (節・行・逐語引用) | 実装の事実 (Step 2 §節番号引用) | 人間判断するべき問い |
|---|---|---|---|
| Qdrant collection 名の 3 段優先順位 | `doc/EXTERNAL_DESIGN.ja.md:929`: "`[retrieval]` | `section_collection` | 任意 | `\"spec_grag_section\"` | section-level retrieval 用 Qdrant collection 名。" | Qdrant collection 名は `retrieval.section_collection` -> `vector_store.section_collection` -> `vector_store.collection` -> `"spec_grag_section"` の順で読む (doc/監査-CODEX/STEP2_METHOD.ja.md:240, doc/監査-CODEX/STEP2_METHOD.ja.md:251)。 | 外部契約に互換 key 2 件を含めるか、`[retrieval].section_collection` だけを外部契約として示すか。 |
| `/spec-inject` の `<課題プロンプト>` / `--conversation-context` 入力 | `doc/EXTERNAL_DESIGN.ja.md:697-703`: Conversation Context と `<課題プロンプト>` を入力に含む。 | `task_prompt` / `prompt` / `conversation_context` は `run_spec_inject` 内で削除される (doc/監査-CODEX/STEP2_METHOD.ja.md:236, doc/監査-CODEX/STEP2_METHOD.ja.md:254)。 | 課題プロンプトと conversation context を CLI 実装が消費する外部契約にするか、Agent / LLM 側の入力として扱うか。 |
| `--use-cache` の挙動 | `doc/EXTERNAL_DESIGN.ja.md:502`: "`--use-cache` は deprecated (挙動は無指定と同等)。" | `run_full and not use_cache` のとき cache JSON を削除する (doc/監査-CODEX/STEP2_METHOD.ja.md:54)。 | `--use-cache` を無指定と同等の deprecated flag とするか、cache clear に影響する互換 flag とするか。 |
| `/spec-inject` の人間向け通常出力 | `doc/EXTERNAL_DESIGN.ja.md:787`: "人間に見える出力は、内部 JSON ではなく、次のような読みやすい構造を基本とする。" | `_run_inject_from_args` は JSON を stdout に出し、`inject` の戻り値は dict である (doc/監査-CODEX/STEP2_METHOD.ja.md:53, doc/監査-CODEX/STEP2_METHOD.ja.md:122-124)。 | 外部契約を CLI JSON と Agent command / skill の表示に分けるか、現在の人間向け出力記述を維持するか。 |
| 設定項目表と raw config key | `doc/EXTERNAL_DESIGN.ja.md:901-1070` は設定項目表を列挙し、`vector_store.section_collection` / `vector_store.collection` を含まない。 | raw config から `vector_store.section_collection` / `vector_store.collection` も読む (doc/監査-CODEX/STEP2_METHOD.ja.md:240-251)。 | §2.1 と同じ。 |
| 環境変数表と debug env var | `doc/EXTERNAL_DESIGN.ja.md:1078-1082` は `SPEC_GRAG_FAKE_LLM` / `SPEC_GRAG_FAKE_RETRIEVAL` / `SPEC_GRAG_QDRANT_URL` だけを列挙する。 | provider debug と related prompt debug は env var truthy 時に append される (doc/監査-CODEX/STEP2_METHOD.ja.md:94-95, doc/監査-CODEX/STEP2_METHOD.ja.md:242)。 | debug env var を外部契約に含めるか、内部調査用の実装詳細として扱うか。 |

## §5. 過剰実装一覧

| 実装事実 (Step 2 §節番号引用) | 外部設計書の該当節（無いことの確認方法） | 人間判断するべき問い |
|---|---|---|
| `build_section_embedding_text` は heading_path、summary、search_keys、identifiers を join し、raw body field は入力に入らない (doc/監査-CODEX/STEP2_METHOD.ja.md:239)。 | `doc/EXTERNAL_DESIGN.ja.md:264` と `doc/EXTERNAL_DESIGN.ja.md:764` は payload / hit field を記述するが、embedding 入力 text の構成は記述しない。`doc/EXTERNAL_DESIGN.ja.md:1128-1133` は embedding provider 実装と scoring を外部設計対象外に置く。 | embedding 用 representation と source evidence text の差を外部契約に含めるか、内部方式として扱うか。 |
| `_debug_provider_invocations.jsonl` と `_debug_related_prompts.jsonl` は env var truthy 時に append され、読込 CLI なしである (doc/監査-CODEX/STEP2_METHOD.ja.md:94-95, doc/監査-CODEX/STEP2_METHOD.ja.md:242)。 | `rg -n 'DEBUG|debug|SPEC_GRAG_DEBUG' doc/EXTERNAL_DESIGN.ja.md` で debug JSONL に対応する記述なし。`doc/EXTERNAL_DESIGN.ja.md:1078-1082` の環境変数表にもない。 | debug JSONL を外部設計書の環境変数 / 保持ファイル契約に含めるか、内部調査用の実装詳細として扱うか。 |

## §6. 不足実装一覧

| 外部設計書の記述 (節・行・逐語引用) | 実装の該当事実（無いことの確認方法） | 人間判断するべき問い |
|---|---|---|
| なし | §2 / §3 で `不足` と判定した項目は 0 件。外部設計書に契約があり Step 2 に材料が不足したものは、実装事実の欠落とは判定せず `未確認` に分類した。 | なし |

## §7. 整合確認済み一覧

| 項目 | 外部設計書の記述 (節・行) | 実装の事実 (Step 2 §節番号引用) |
|---|---|---|
| Related Sections / Summary / Search Keys の evidence 区分 | `doc/EXTERNAL_DESIGN.ja.md:87`, `doc/EXTERNAL_DESIGN.ja.md:93`, `doc/EXTERNAL_DESIGN.ja.md:112`, `doc/EXTERNAL_DESIGN.ja.md:826` | doc/監査-CODEX/STEP2_METHOD.ja.md:186, doc/監査-CODEX/STEP2_METHOD.ja.md:238 |
| Agent 入力による constraints / answer | `doc/EXTERNAL_DESIGN.ja.md:24`, `doc/EXTERNAL_DESIGN.ja.md:332-338`, `doc/EXTERNAL_DESIGN.ja.md:954` | doc/監査-CODEX/STEP2_METHOD.ja.md:53-54, doc/監査-CODEX/STEP2_METHOD.ja.md:268 |
| `core_progress.json` の生成 | `doc/EXTERNAL_DESIGN.ja.md:596`, `doc/EXTERNAL_DESIGN.ja.md:600`, `doc/EXTERNAL_DESIGN.ja.md:613` | doc/監査-CODEX/STEP2_METHOD.ja.md:90, doc/監査-CODEX/STEP2_METHOD.ja.md:241 |
| graph 構造を標準経路に含めない | `doc/EXTERNAL_DESIGN.ja.md:20-24` | doc/監査-CODEX/STEP2_METHOD.ja.md:73, doc/監査-CODEX/STEP2_METHOD.ja.md:268 |
| Source Specs 読み取り | `doc/EXTERNAL_DESIGN.ja.md:48-53` | doc/監査-CODEX/STEP2_METHOD.ja.md:48-52, doc/監査-CODEX/STEP2_METHOD.ja.md:162 |
| Section 単位処理 | `doc/EXTERNAL_DESIGN.ja.md:72-83` | doc/監査-CODEX/STEP2_METHOD.ja.md:48-60, doc/監査-CODEX/STEP2_METHOD.ja.md:267-271 |
| pending Conflict Review Item の停止 | `doc/EXTERNAL_DESIGN.ja.md:116-136` | doc/監査-CODEX/STEP2_METHOD.ja.md:85, doc/監査-CODEX/STEP2_METHOD.ja.md:201-204 |
| Chapter Key Anchor lookup | `doc/EXTERNAL_DESIGN.ja.md:137-151` | doc/監査-CODEX/STEP2_METHOD.ja.md:86, doc/監査-CODEX/STEP2_METHOD.ja.md:150, doc/監査-CODEX/STEP2_METHOD.ja.md:213 |
| Agentic Search の主体 | `doc/EXTERNAL_DESIGN.ja.md:152-157` | doc/監査-CODEX/STEP2_METHOD.ja.md:71, doc/監査-CODEX/STEP2_METHOD.ja.md:268 |
| freshness gate と `/spec-core` 非自動実行 | `doc/EXTERNAL_DESIGN.ja.md:193-206` | doc/監査-CODEX/STEP2_METHOD.ja.md:87, doc/監査-CODEX/STEP2_METHOD.ja.md:120-122, doc/監査-CODEX/STEP2_METHOD.ja.md:250 |
| Purpose / Core Concept の read-only | `doc/EXTERNAL_DESIGN.ja.md:238-256` | doc/監査-CODEX/STEP2_METHOD.ja.md:52, doc/監査-CODEX/STEP2_METHOD.ja.md:264 |
| 主要保持ファイル配置 | `doc/EXTERNAL_DESIGN.ja.md:269-280` | doc/監査-CODEX/STEP2_METHOD.ja.md:82-99 |
| Source Retrieval Index / Related Sections の状態記録ファイル | `doc/EXTERNAL_DESIGN.ja.md:279-280` | doc/監査-CODEX/STEP2_METHOD.ja.md:88-89, doc/監査-CODEX/STEP2_METHOD.ja.md:266 |
| watcher 動作 | `doc/EXTERNAL_DESIGN.ja.md:458-476` | doc/監査-CODEX/STEP2_METHOD.ja.md:49, doc/監査-CODEX/STEP2_METHOD.ja.md:154, doc/監査-CODEX/STEP2_METHOD.ja.md:172 |
| provider 失敗時の silent fallback 禁止 | `doc/EXTERNAL_DESIGN.ja.md:504` | doc/監査-CODEX/STEP2_METHOD.ja.md:198-209 |
| CoreResult と status 群 | `doc/EXTERNAL_DESIGN.ja.md:564-686` | doc/監査-CODEX/STEP2_METHOD.ja.md:73-75, doc/監査-CODEX/STEP2_METHOD.ja.md:88-91, doc/監査-CODEX/STEP2_METHOD.ja.md:168-173, doc/監査-CODEX/STEP2_METHOD.ja.md:197-229 |
| inject 系 CLI の参照操作 | `doc/EXTERNAL_DESIGN.ja.md:757-769` | doc/監査-CODEX/STEP2_METHOD.ja.md:50-54, doc/監査-CODEX/STEP2_METHOD.ja.md:147-152, doc/監査-CODEX/STEP2_METHOD.ja.md:181-186 |
| constraints 最小構造と evidence validation | `doc/EXTERNAL_DESIGN.ja.md:812-827` | doc/監査-CODEX/STEP2_METHOD.ja.md:116, doc/監査-CODEX/STEP2_METHOD.ja.md:186 |
| realign の answer structure | `doc/EXTERNAL_DESIGN.ja.md:848-888` | doc/監査-CODEX/STEP2_METHOD.ja.md:54, doc/監査-CODEX/STEP2_METHOD.ja.md:153, doc/監査-CODEX/STEP2_METHOD.ja.md:269 |
| `.gitignore` 推奨カテゴリ | `doc/EXTERNAL_DESIGN.ja.md:1084-1103` | doc/監査-CODEX/STEP2_METHOD.ja.md:82-99 |

## §8. 未確認 / 解釈不能事項

| 項目 | 外部設計書の記述または実装の事実 | 判定不能な理由 | 試した探索方法 |
|---|---|---|---|
| 方式呼称 `SPEC-grag` と業界用語の対応 | 外部設計書は `SPEC-grag` と記述し、property graph / entity relation graph / hierarchical cluster を標準経路に含めない (doc/EXTERNAL_DESIGN.ja.md:1, doc/EXTERNAL_DESIGN.ja.md:20)。 | `SPEC-grag` が製品名か、業界用語 GRAG と対応する呼称かは本 Step の材料だけでは判定しない。 | `rg -n 'GRAG|GraphRAG|lightweight' doc/EXTERNAL_DESIGN.ja.md` |
| fake provider の状態表現 | `SPEC_GRAG_FAKE_LLM` は in-process FakeLlmProvider を使うと外部設計書が記述する (doc/EXTERNAL_DESIGN.ja.md:1080)。 | Step 2 は fake provider 選択を記録するが、CoreResult / freshness / diagnostics への表れ方は同じ粒度で示していない (doc/監査-CODEX/STEP2_METHOD.ja.md:112, doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md:203)。 | Step 2 §1、§8、§9、Step 3 §6、外部設計書 §10.3 / §11 を確認した。 |
| `source_section_id` の形式と一意性 | 外部設計書は `<file_path>#<heading_slug>` 形式と一意性を契約とする (doc/EXTERNAL_DESIGN.ja.md:83)。 | Step 2 は `source_section_id` の payload 利用を示すが、形式と一意性の検査までは記録していない (doc/監査-CODEX/STEP2_METHOD.ja.md:59-60)。 | Step 2 §1、§2、§7、§11 を確認した。 |
| setup script の実装事実 | 外部設計書は system / project setup script の契約を持つ (doc/EXTERNAL_DESIGN.ja.md:369-429)。 | Step 2 は target 9 CLI 中心で、setup script を主要方式フローに含めていない (doc/監査-CODEX/STEP2_METHOD.ja.md:8)。 | Step 2 §0、§4、§5、§8 を確認した。 |
| Conflict Review Item decision enum | 外部設計書は `prefer_a` / `prefer_b` / `conditional` / `dismiss` / `needs_source_update` / `defer` / `task_scope_resolution` を記述する (doc/EXTERNAL_DESIGN.ja.md:671-681)。 | Step 2 は Conflict Review Item の存在と gate は記録するが、decision enum の全対応は示していない (doc/監査-CODEX/STEP2_METHOD.ja.md:85, doc/監査-CODEX/STEP2_METHOD.ja.md:168)。 | Step 2 §3、§6、§8、§9 を確認した。 |
| config の親ディレクトリ探索なし | 外部設計書は親ディレクトリへの自動探索をしないと記述する (doc/EXTERNAL_DESIGN.ja.md:893)。 | Step 2 は `.spec-grag/config.toml` を読む事実を記録するが、親探索なしの確認材料は不足する (doc/監査-CODEX/STEP2_METHOD.ja.md:48)。 | Step 2 §1、§4、§5 を確認した。 |
| 外部設計書 §12 の対象外範囲 | 外部設計書は embedding provider 実装や LLM provider subprocess 実装などを扱わない (doc/EXTERNAL_DESIGN.ja.md:1128-1134)。 | Step 2 は実装事実として embedding text、LLM subprocess、debug JSONL を記録するため、外部契約から外す範囲と実装事実として記録する範囲の対応は人間判断が必要である (doc/監査-CODEX/STEP2_METHOD.ja.md:55-59, doc/監査-CODEX/STEP2_METHOD.ja.md:239, doc/監査-CODEX/STEP2_METHOD.ja.md:242)。 | 外部設計書 §12 と Step 2 §1、§7、§9 を確認した。 |
| 判定対象から外した節 | Purpose / Core Concept の中身そのもの (doc/EXTERNAL_DESIGN.ja.md:30-47, doc/EXTERNAL_DESIGN.ja.md:54-71)。 | human-managed の正本内容であり、その内容がどうあるべきかは本 Step の判定対象から外す。Purpose / Core Concept を CLI が読むか、自動更新しないかは §3 で照合済み。 | 外部設計書 §2.1 / §2.3 / §4 / §5 と Step 2 §1 / §11 を確認した。 |

## 最終報告

- 作成したファイル: `doc/監査-CODEX/STEP4_CONFORMANCE.ja.md`
- 前提とした前段成果物のパス: `doc/監査-CODEX/STEP1A_INVENTORY.ja.md` / `doc/監査-CODEX/STEP1B_FLOWS.ja.md` / `doc/監査-CODEX/STEP1C_CROSS_VIEWS.ja.md` / `doc/監査-CODEX/STEP2_METHOD.ja.md` / `doc/監査-CODEX/STEP3_STANDARD_DIFF.ja.md`
- 外部設計書のパス: `doc/EXTERNAL_DESIGN.ja.md`
- §1 外部設計書の節件数: 表題 1 + 章 / 節 53 件。`doc/EXTERNAL_DESIGN.ja.md:177-180` の code fence 内見出し例は節件数から除外した。
- §2.1〜§2.9 Step 3 §5 引き継ぎ 9 件の判定内訳: 整合 3 / 不足 0 / 過剰 2 / 不整合 2 / 未確認 2
- §3 §2 以外の契約項目の照合件数: 30 件
- §4 不整合人間判断対象件数: 6 件
- §5 過剰実装件数: 2 件
- §6 不足実装件数: 0 件
- §7 整合確認済み件数: 20 件
- §8 未確認 / 解釈不能件数: 8 件
- 外部設計書の全節をスキャンしたことの確認方法: `rg -n '^#{1,6} ' doc/EXTERNAL_DESIGN.ja.md` で見出しを抽出し、`nl -ba doc/EXTERNAL_DESIGN.ja.md | sed -n '1,220p'`、`221,440p`、`441,660p`、`661,880p`、`881,1138p` で全文を読んだ。
- 「どちらが正しい」を判定しなかったことの確認方法: §4 / §5 / §8 は実装変更または設計書変更の方向を決めず、人間が判断する問いだけを記録した。
- file:line または §節番号引用が付いていない事実文の有無: なし
- denylist を開いていないことの確認方法: `doc/DESIGN.ja.md` / `doc/AGENTS.md` / `doc/TODO.ja.md` / `doc/CHANGELOG.ja.md` / `archive/` / `BAK/` / `.spec-grag/` / `README.md` は本 Step の判定根拠として開いていない。作業ルール確認として `CLAUDE.md` と `.codex/skills/spec-grag/SKILL.md` を読んだが、本 Step の判定根拠にはしていない。
- 中断 / 失敗があれば: なし
