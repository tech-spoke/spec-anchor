# SPEC-anchor 外部仕様書 (DRAFT)

本書は `agent_doc/外部設計書リライト.md` に従って作成した外部仕様書の **試作版** である。`doc/EXTERNAL_DESIGN.ja.md` を素材として書き直したものであり、現時点で正本ではない。Agent / 利用者の参照経路、CLAUDE.md / AGENTS.md / TODO 上での扱いは、本ドラフトの完成と正本切り替え合意の後に別途決定する。

## 0. ドラフト運用情報

### 情報源の優先順位

本ドラフトの記述は次の優先順位の情報源に基づく。

1. 現在の実装で外部から観測できる入出力
2. 既存 `doc/EXTERNAL_DESIGN.ja.md` に明記された外部契約
3. テストで固定されている外部挙動 (`tests/` 配下)
4. `doc/README素材.md` などの利用者ガイド素材、過去の議論

実装・既存設計書・テストの間で矛盾があるか、断定値を確認できなかった項目は、各章末尾の「未確定事項」節に分離する。本文の契約表には推測で値を埋めない。(2026-05-22: 17 件の未確定事項を実機確認で全件解消し、本文に反映済み)

### 互換性方針の所在

本書に定義された項目は原則すべて外部契約として扱う。互換性方針の総則は §14 を参照。診断用・debug 用・互換性保証対象外の項目は、各項目の説明欄でその旨を明記する。

## 1. 外部仕様の対象範囲

本書は SPEC-anchor の **外部から観測できる入出力契約** を定義する。

### 1.1 対象

- shell CLI (`spec-anchor` / `spec-anchor-watch` / `spec-anchor-setup-system` / `spec-anchor-setup-project`) の入力・出力・状態・エラー
- Agent CLI (Claude Code / Codex) の slash command / skill 経由で発火する `/spec-core` / `/spec-inject` / `/spec-realign` の入力・出力
- `.spec-anchor/config.toml` の全 table / 全 key
- 生成・更新される artifact (`.spec-anchor/state/`、`.spec-anchor/context/` 配下のうち外部から参照されるもの)
- Conflict Review Item の状態遷移
- freshness gate の停止条件と recommended_next_action
- Agent / 利用者が打鍵する識別子 (`source_section_id` 等) の形式

### 1.2 対象外

- 内部アルゴリズム (検索方式、ranking、embedding 入力 text 組み立て、point id 生成、cache key 生成、stage 実行順、retry / debounce の内部ロジック)
- 保存の内部データ構造 (Qdrant payload field 内訳、UUID5 namespace、fingerprint 組み立て、state file の内部 field のうち Agent / 利用者が読まないもの)
- provider routing の実装
- 方式分類 (Hybrid RAG / property graph / hierarchical cluster の実装方式説明)
- 検証管理情報 (`tests/` のテスト ID、検証進捗マーク)

## 2. 用語

### 2.1 Purpose (目的)

プロジェクトの存在理由、達成したい価値、上位の判断基準を示す人間管理文書。`.spec-anchor/config.toml` の `[core].purpose_file` が指すファイルが正本であり、SPEC-anchor は `.spec-anchor/` 配下にコピーや再生成 artifact を作らない。

### 2.2 Core Concept (中核コンセプト)

プロジェクト全体の判断軸、承認済みの設計原則、不変に近い方針を示す人間管理文書。`[core].concept_file` が指すファイルが正本であり、Purpose と同様に `.spec-anchor/` 配下に複製を作らない。

### 2.3 Source Specs (仕様本文)

`[sources].include` の glob に一致する Markdown 文書群。SPEC-anchor は本文を Markdown 見出しで分割して扱う。

### 2.4 Section (セクション)

Source Specs を Markdown 見出しを境界として分割した単位。分割の最大深さは `[section].max_heading_level` で指定 (既定 4)。設定値より深い見出しは独立セクションにならず、直近の親セクション本文に統合される。

### 2.5 source_section_id (セクション識別子)

形式: `<file_path>#<ordinal>-<heading_slug>`

- `<file_path>`: project-root 相対パス (`.spec-anchor/config.toml` の `[sources].include` で読み込まれた path)
- `<ordinal>`: 同一ファイル内の出現順、1 始まり 4 桁 zero-padded (`0001` / `0002` / ...)
- `<heading_slug>`: heading text の正規化結果。英数字 / `_` / 日本語 (ひらがな・カタカナ・漢字) は保持、それ以外は `-` に置換、小文字化、前後 `-` 除去。空文字列になる場合は `section` で代替

一意性: `[sources].include` に一致する Source Specs 全体で一意。

使用箇所:

- 入力: `spec-anchor inject-section "<id>" [<id>...]` の CLI 引数
- 出力: `spec-anchor inject-search` の戻り値の `source_section_id` field、`spec-anchor core` の `updated_sections[]` / `failed_sections[].section_id`、artifact 内の `source_section_id` field

見つからない場合の挙動: `spec-anchor inject-section` で未存在 ID を指定したときの reason code と表示内容は §13 を参照。

利用者が永続参照として使う場合の注意: heading 変更で `<heading_slug>` が変わると ID も変わる。Section の並び替えで `<ordinal>` が変わると ID も変わる。ファイル rename でも変わる。

### 2.6 保持物

`/spec-core` が生成・更新する次の集合を指す。

- セクションごとの要約 (各 Section に 1 件)
- セクション検索キー (各 Section に複数件)
- セクション識別子リスト (各 Section 本文から抽出)
- 関連セクション (各 Section に関連先一覧)
- Conflict Review Item (検出された矛盾候補)
- 章単位の要点 (Markdown 最上位見出しごと)
- Source 検索 Index (検索基盤の Section 索引)

各保持物の artifact path と更新条件は §4 / §5 / §11 / §12 を参照。

保持物のうち、セクション検索キーとセクション識別子は検索の補助情報であり、制約の根拠にしてはいけない。

- **セクション検索キー** (Section Search Keys): 検索 recall を上げるための自然言語のキーワード。コードシンボル / API 名 / CLI コマンド / CLI option / ファイルパス / 定数名 / 型名は含まない (これらはセクション識別子に分離される)
- **セクション識別子** (Section Identifiers): Section 本文に出現するコードシンボル / 固有技術名を正規表現で機械抽出したリスト。LLM 判断を経由しない

同様に、セクションごとの要約、関連セクション、章単位の要点も単独では根拠にならない。制約として採用する場合は、Purpose / Core Concept / Source Specs 本文 / stale でない resolved Conflict Review Item のいずれかを根拠として確認する。

### 2.7 Conflict Review Item (仕様矛盾の判断待ち)

`/spec-core` が、利用者プロジェクトの Source Specs / Purpose / Core Concept の中から検出した仕様矛盾のうち、LLM が自力で解決できないものを「人間判断待ち」として記録した項目。対象は次の 3 種類。

- 利用者の Source Specs 内の異なる Section 同士の矛盾 (同一トピックに対する記述の食い違いなど)
- 利用者の Source Specs と Core Concept (設計原則) の衝突
- 利用者の Source Specs と Purpose (上位目的) の衝突

本仕様書自体の記述は SPEC-anchor の検出対象ではない (SPEC-anchor は利用者プロジェクトの仕様情報を扱うツールであり、ツール自身の仕様書を解析対象にしない)。

詳細は §11 を参照。

### 2.8 Chapter Key Anchor (章単位の要点)

Source Specs の章 (Markdown 最上位見出しの範囲) ごとに、章全体の要約・重要テーマ・主要 Section への入口を LLM が生成する。LLM 生成のみで作成され、mechanical / placeholder 代替は提供しない。LLM 生成に失敗した章がある場合、`/spec-core` は canonical `chapter_anchors.json` を更新せず前回値を残し、freshness を failed に降格する。詳細は §5 を参照。

### 2.9 freshness gate (鮮度ゲート)

`/spec-inject` / `/spec-realign` の各サブコマンドが内部で実行する停止判定。保持物が古い、watcher 動作中、未判断 Conflict Review Item がある、保持物の一部生成に失敗、のいずれかで停止する。詳細は §12 を参照。

### 2.10 Agentic Search (Agent 主体の探索)

Agent / LLM が検索結果を見ながら追加検索・関連先参照・根拠確認を繰り返す行動。shell CLI は探索方針を自律的に決めず、Agent / LLM が判断する。

## 3. 共通実行規約

### 3.1 配置と作業ディレクトリ

shell CLI は対象プロジェクトの `<project_root>/.spec-anchor/config.toml` を設定の正本とする。親ディレクトリへの自動探索は行わない。

`spec-anchor` 系コマンドはカレントディレクトリを project root として解釈する。実行前に対象 project root に `cd` する。

### 3.2 出力形式

- shell CLI の主出力は stdout に JSON object 1 つ。CLI 自身に整形 mode (`--format human` 等) は持たない
- stderr は補助情報のみ。契約は stdout の JSON が正本
- slash command / skill から発火された場合、Agent CLI が stdout JSON を解釈して利用者向けに整形する (詳細は §6.2 / 各コマンド章の slash command 契約)

### 3.3 CLI exit code の方針

| コマンド | exit code 1 を返す条件 |
|---|---|
| `spec-anchor core` | `status` が `failed` / `error` |
| `spec-anchor realign` | `status` が `failed` / `error` |
| `spec-anchor-setup-system` | `status` が `error` / `failed` |
| `spec-anchor-setup-project` | `status` が `conflict` / `error` / `failed` |
| `spec-anchor inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` | 常に 0 (停止状態は stdout JSON の `should_stop` / `blocking_reasons` / `status` で表現) |
| `spec-anchor-watch` | 常に 0 |

`inject-*` と `spec-anchor-watch` の呼び出し元は CLI exit code を見ずに stdout JSON を parse する責務を持つ。

### 3.4 失敗時の共通契約

全コマンドで、`status="failed"` を返す失敗はすべて、stdout JSON 内の `freshness_report.blocking_reasons` に `failed_required_artifact` が積まれ、`freshness_report.status` も `failed` になる。これにより後続の `/spec-inject` / `/spec-realign` は §12 freshness gate で停止する。`/spec-core` 自身は新しい canonical artifact を上書きせず、前回値を残す (復旧時の比較基準になる)。

## 4. 設定ファイルの外部契約

### 4.1 配置

`<project_root>/.spec-anchor/config.toml` を設定の正本とする。親ディレクトリへの自動探索は行わない。

`<project_root>` 直下にのみ配置される。`../.spec-anchor/` 等を探索しない。project root から外れた cwd で `spec-anchor` 系コマンドを実行すると、`.spec-anchor/config.toml not found under {cwd}` で失敗する。

### 4.2 設定項目の全 key 列挙

`<id>` は `[llm.providers.<id>]` で命名するユーザー定義 provider id (例: `codex`、`claude_typing`、`claude_judge`)。

| Table | Key | 型 | 必須 | 既定値 | 許可値 / 範囲 | 不正値時のエラー | 観測できる効果 |
|---|---|---|---|---|---|---|---|
| `[sources]` | `include` | list[string] | 必須 | — | 非空 list、各要素は非空 string (glob) | `sources.include must be a non-empty list` / `sources.include must contain non-empty strings` | Source Specs として読み込むファイル集合が決まる |
| `[sources]` | `exclude` | list[string] | 任意 | `[]` | string list | `sources.exclude must be a list` / `sources.exclude must contain non-empty strings` / `sources.exclude must be project-root relative` | `include` から除外するファイル集合が決まる |
| `[core]` | `purpose_file` | string | 必須 | — | 既存ファイルへの project-root 相対 path | `core.purpose_file not found: {path}` | Purpose の正本ファイルが決まる |
| `[core]` | `concept_file` | string | 必須 | — | 既存ファイルへの project-root 相対 path | `core.concept_file not found: {path}` | Core Concept の正本ファイルが決まる |
| `[context]` | `storage` | string | 任意 | `.spec-anchor/context` | project-root 相対 path | `context.storage must be a non-empty string` / `context.storage must not escape project root` | 生成済み保持物 (Conflict Review Item / Chapter Key Anchor) の保存先 directory |
| `[section]` | `max_heading_level` | int | 任意 | `4` | 1〜6 | `section.max_heading_level must be an integer` | Source Specs を Section に分割する境界となる最大 Markdown heading level |
| `[section_metadata]` | `summary_enabled` | bool | 任意 | `true` | `true` / `false` | `section_metadata.summary_enabled must be a boolean` | `false` で「セクションごとの要約」生成を抑止 |
| `[section_metadata]` | `search_keys_enabled` | bool | 任意 | `true` | `true` / `false` | `section_metadata.search_keys_enabled must be a boolean` | `false` で「セクション検索キー」生成を抑止 |
| `[section_metadata]` | `related_sections_enabled` | bool | 任意 | `true` | `true` / `false` | `section_metadata.related_sections_enabled must be a boolean` | `false` で「関連セクション」生成を抑止 |
| `[chapter_anchor]` | `enabled` | bool | 任意 | `true` | `true` / `false` | `chapter_anchor.enabled must be a boolean` | `false` で「章単位の要点」生成を抑止 |
| `[llm.providers.<id>]` | `command` | string | 必須 | — | 実行可能 CLI コマンド名または絶対 path | `llm.providers.<id>.command is required` / `llm.providers.<id>.command must be a non-empty string` | `/spec-core` の各 stage が呼び出す LLM 子プロセス。`SPEC_ANCHOR_FAKE_LLM` truthy 時は呼ばれない。PATH 上に存在しない command を指定した場合、当該 stage は `reason_code="provider_exception"`、`message="[Errno 2] No such file or directory: '<command>'"` として失敗する (retry 回数分繰り返す) |
| `[llm.providers.<id>]` | `model` | string | 任意 | — | provider 依存 | `llm.providers.<id>.model must be a non-empty string` | provider に渡される model 名 |
| `[llm.providers.<id>]` | `effort` | string | 任意 | — | provider 依存 (例: `low` / `medium`) | `llm.providers.<id>.effort must be a non-empty string` | provider に渡される reasoning effort |
| `[llm.providers.<id>]` | `timeout_sec` | int | 任意 | `120` | 正の整数 | `llm.providers.<id>.timeout_sec must be an integer` | 1 attempt の wall clock 上限。超過時は attempt 失敗 |
| `[llm.providers.<id>]` | `max_retries` | int | 任意 | `1` | 非負整数 | `llm.providers.<id>.max_retries must be an integer` | 失敗時の追加 retry 回数。すべて失敗で当該 stage を failed として diagnostics に出す |
| `[llm.stage_routing]` | `section_metadata` | string | 任意 | `[llm.providers]` 先頭定義 | `[llm.providers]` で定義済みの id | `[llm.providers]` 未定義の id を指定すると config error として reject | section_metadata stage で使う provider |
| `[llm.stage_routing]` | `related_sections` | string | 任意 | `[llm.providers]` 先頭定義 | 同上 | 同上 | related_sections stage で使う provider |
| `[llm.stage_routing]` | `conflict_review` | string | 任意 | `[llm.providers]` 先頭定義 | 同上 | 同上 | conflict_review stage で使う provider |
| `[llm.stage_routing]` | `chapter_key_anchor` | string | 任意 | `[llm.providers]` 先頭定義 | 同上 | 同上 | chapter_key_anchor stage で使う provider |

`[llm.providers]` が 1 件も定義されていない場合、`/spec-core` は config error で停止する (`SPEC_ANCHOR_FAKE_LLM` truthy 時を除く)。`[llm.stage_routing]` に上記 4 key 以外の key を指定した場合は config error として reject される (`"llm.stage_routing.{key} is not an allowed stage"`)。

| `[retrieval]` | `dense_top_k` | int | 任意 | `12` | 正の整数 | `retrieval.dense_top_k must be an integer` | dense retrieval の取得 top-K |
| `[retrieval]` | `sparse_top_k` | int | 任意 | `20` | 正の整数 | `retrieval.sparse_top_k must be an integer` | sparse retrieval の取得 top-K |
| `[retrieval]` | `rank_fusion` | string | 任意 | `"rrf"` | `"rrf"` | `retrieval.rank_fusion must be rrf` | dense / sparse の融合方式 |
| `[retrieval]` | `section_collection` | string | 任意 | `"spec_anchor_section"` | 非空 string | `retrieval.section_collection must be a non-empty string` | section-level 検索基盤の collection 名 |
| `[retrieval]` | `section_dense_threshold` | float | 任意 | `0.55` | 0.0〜1.0 | `retrieval.section_dense_threshold must be a number` | section-level dense 候補の採用最低 score |
| `[retrieval]` | `section_candidate_top_k` | int | 任意 | `16` | 正の整数 | `retrieval.section_candidate_top_k must be an integer` | section-level 候補絞り込み 1 段目 top-K |
| `[retrieval]` | `section_final_top_n` | int | 任意 | `8` | 正の整数 | `retrieval.section_final_top_n must be an integer` | section-level 候補絞り込み最終 top-N |
| `[embedding]` | `provider` | string | 必須 | — | `"flagembedding"` (現時点で 1 値) | `embedding.provider must be flagembedding` | embedding provider 種別 |
| `[embedding]` | `model` | string | 必須 | — | provider 依存 (標準は `"BAAI/bge-m3"`) | `embedding.model must be BAAI/bge-m3` | embedding model 名 |
| `[embedding]` | `dense_enabled` | bool | 任意 | `true` | `true` / `false` | `embedding.dense_enabled must be a boolean` | `false` で dense embedding 算出を抑止 |
| `[embedding]` | `sparse_enabled` | bool | 任意 | `true` | `true` / `false` | `embedding.sparse_enabled must be a boolean` | `false` で sparse embedding 算出を抑止 |
| `[vector_store]` | `provider` | string | 必須 | — | `"qdrant"` (現時点で 1 値) | `vector_store.provider must be qdrant` | vector store 種別 |
| `[vector_store]` | `url` | string | 任意 | — | URL 文字列 (例: `http://localhost:6333`) | 接続失敗時 `production_readiness.blocking_reasons=["qdrant_service_unavailable"]` (setup-system 経由) | vector store サービスの接続先 |
| `[limits]` | `section_summary_max_chars` | int | 任意 | `480` | 正の整数 | `limits.section_summary_max_chars must be an integer` | セクションごとの要約の最大文字数 |
| `[limits]` | `search_keys_max` | int | 任意 | `32` | 正の整数 | `limits.search_keys_max must be an integer` | セクション検索キーの 1 Section あたり最大件数 |
| `[limits]` | `related_candidate_max_per_section` | int | 任意 | `32` | 正の整数 | `limits.related_candidate_max_per_section must be an integer` | 関連セクション候補生成の 1 Section あたり最大件数 |
| `[limits]` | `related_selected_max_per_section` | int | 任意 | `8` | 正の整数 | `limits.related_selected_max_per_section must be an integer` | 関連セクション最終採用の 1 Section あたり最大件数 |
| `[limits]` | `conflict_pair_max_per_section` | int | 任意 | `8` | 正の整数 | `limits.conflict_pair_max_per_section must be an integer` | conflict 判定 stage に送る pair の 1 Section あたり最大件数 |
| `[limits]` | `llm_batch_max_sections` | int | 任意 | `8` | 正の整数 | `limits.llm_batch_max_sections must be an integer` | 1 LLM 呼び出しでまとめる Section 数の上限 |
| `[limits]` | `llm_batch_max_chars` | int | 任意 | `12000` | 正の整数 | `limits.llm_batch_max_chars must be an integer` | 1 LLM 呼び出しでまとめる総文字数の上限 |
| `[limits]` | `llm_batch_concurrency` | int | 任意 | `4` | 正の整数 | `limits.llm_batch_concurrency must be an integer` | section_metadata / related_sections の batch 並列実行数 |
| `[watcher]` | `enabled` | bool | 任意 | `false` | `true` / `false` | `watcher.enabled must be a boolean` | watcher の有効化フラグ。標準テンプレは `true` で配布 |
| `[watcher]` | `interval_ms` | int | 任意 | `2000` | 正の整数 | `watcher.interval_ms must be an integer` | watcher の polling 間隔 (ms) |
| `[watcher]` | `debounce_ms` | int | 任意 | `1000` | 非負整数 | `watcher.debounce_ms must be an integer` | 連続変更を 1 回の更新にまとめる debounce 時間 (ms) |
| `[watcher]` | `stale_lock_ms` | int | 任意 | `300000` | 正の整数 | `watcher.stale_lock_ms must be an integer` | 古い lock を回収する閾値 (ms) |
| `[watcher]` | `state_file` | string | 任意 | `.spec-anchor/state/watch_state.json` | project-root 相対 path | `watcher.state_file must be a non-empty string` | watcher の polling 状態保存先 (内部状態。利用者が直接参照する必要はない) |
| `[watcher]` | `queue_file` | string | 任意 | `.spec-anchor/state/watch_queue.json` | project-root 相対 path | `watcher.queue_file must be a non-empty string` | watcher の未処理キュー保存先 (内部状態。利用者が直接参照する必要はない) |

### 4.3 設定キーの追加・改名・削除

すべての key の追加・改名・削除は §14 互換性方針に従う。利用者が直接参照しない内部状態 (`[watcher].state_file` / `queue_file` など) も外部から path 指定できる以上、設定キーとしては外部契約に含まれる。

### 4.4 環境変数による設定の上書き

project root に `.env` ファイル (`KEY=VALUE` 行) を置くと、`spec-anchor` 起動時に `os.environ` に投入される。既に shell で export されている変数は上書きしない (.env より shell 優先)。

| 環境変数 | 用途 |
|---|---|
| `SPEC_ANCHOR_FAKE_LLM` | truthy (`1` / `true` / `yes` / `on`) で `/spec-core` が `[llm.providers.<id>].command` を起動せず in-process fake を使う |
| `SPEC_ANCHOR_FAKE_RETRIEVAL` | truthy で Qdrant + FlagEmbedding BGE-M3 の実構築を伴う test / smoke コード経路を block する |
| `SPEC_ANCHOR_QDRANT_URL` | `spec-anchor-setup-project` / `spec-anchor-setup-system` の probe が config 確定前に検索基盤接続先を解決するために読む。config が存在する場合は `[vector_store].url` が正本 |
| `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION` | debug 用。truthy で LLM 子プロセスの解決済み command / stdin の SHA-256 を JSONL append で記録 (本運用経路の挙動は変えず、追加 append 出力のみ増える)。出力内容と path は互換性保証対象外 (将来変更されうる) |
| `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION_PATH` | debug 用。上記 debug log の出力先 file path を上書き。空 / 未設定で `.spec-anchor/state/_debug_provider_invocations.jsonl`。互換性保証対象外 |
| `SPEC_ANCHOR_DEBUG_RELATED_PROMPT` | debug 用。truthy で関連セクション stage の prompt hash と入力 section 集合を JSONL append で記録。互換性保証対象外 |
| `SPEC_ANCHOR_DEBUG_RELATED_PROMPT_PATH` | debug 用。上記 debug log の出力先 file path を上書き。空 / 未設定で `.spec-anchor/state/_debug_related_prompts.jsonl`。互換性保証対象外 |

### 4.5 初期 `.spec-anchor/config.toml` 全文

`spec-anchor-setup-project` が初期化時に project root へ展開する `.spec-anchor/config.toml` の全文を次に示す。本文の §4.2 設定項目仕様表と同期する (key の取捨選択は本文・初期 TOML のどちらでも行わない)。

```toml
[sources]
include = ["docs/spec/**/*.md"]
exclude = ["**/drafts/**"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[context]
storage = ".spec-anchor/context"

[section]
max_heading_level = 4

[section_metadata]
summary_enabled = true
search_keys_enabled = true
related_sections_enabled = true

[chapter_anchor]
enabled = true

# LLM provider 定義。/spec-core が保持物の生成に使う。
# /spec-inject と /spec-realign の会話解釈・制約生成は Agent 環境が担うため対象外。

[llm.providers.codex]
command = "codex"
model = "gpt-5.4-mini"
effort = "low"
timeout_sec = 120
max_retries = 1

[llm.providers.claude_typing]
command = "claude"
model = "claude-sonnet-4-6"
effort = "low"
timeout_sec = 360
max_retries = 1

[llm.providers.claude_judge]
command = "claude"
model = "claude-sonnet-4-6"
effort = "low"
timeout_sec = 360
max_retries = 1

# 各 stage がどの provider を使うかを指定する。
[llm.stage_routing]
section_metadata   = "codex"
related_sections   = "claude_typing"
conflict_review    = "claude_judge"
chapter_key_anchor = "codex"

[retrieval]
dense_top_k = 12
sparse_top_k = 20
rank_fusion = "rrf"
section_collection = "spec_anchor_section"
section_dense_threshold = 0.55
section_candidate_top_k = 16
section_final_top_n = 8

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"
dense_enabled = true
sparse_enabled = true

[vector_store]
provider = "qdrant"
url = "http://localhost:6333"

[limits]
section_summary_max_chars = 480
search_keys_max = 32
related_candidate_max_per_section = 32
related_selected_max_per_section = 8
conflict_pair_max_per_section = 8
llm_batch_max_sections = 8
llm_batch_max_chars = 12000
llm_batch_concurrency = 4

[watcher]
enabled = true
interval_ms = 2000
debounce_ms = 1000
stale_lock_ms = 300000
state_file = ".spec-anchor/state/watch_state.json"
queue_file = ".spec-anchor/state/watch_queue.json"
```

### 4.6 `.gitignore` 推奨設定

`spec-anchor-setup-project` は `.gitignore` 推奨雛形を作る。

```gitignore
.spec-anchor/context/
.spec-anchor/cache/
.spec-anchor/state/
.env
```


## 5. `/spec-core` の外部仕様

### 5.1 shell CLI 契約

#### 実行形式

```text
spec-anchor core [--all | -a] [--rebuild] [--verify-index] [--llm-provider <id>] [--decision-json '<json>'] [--decision-file <path>]
```

#### 入力

| 入力 | 必須 | 説明 | 不備がある場合の挙動 |
|---|---|---|---|
| `<project_root>/.spec-anchor/config.toml` | 必須 | 設定ファイル (§4) | `status="failed"`、`diagnostics.config_error.message=".spec-anchor/config.toml not found under {root}"`、CLI exit code 1 |
| Purpose ファイル (`[core].purpose_file`) | 必須 | 人間管理の Purpose 本文 | `status="failed"`、`diagnostics.config_error.message="core.purpose_file not found: {path}"`、CLI exit code 1 |
| Core Concept ファイル (`[core].concept_file`) | 必須 | 人間管理の Core Concept 本文 | `status="failed"`、`diagnostics.config_error.message="core.concept_file not found: {path}"`、CLI exit code 1 |
| Source Specs (`[sources].include` で一致するファイル) | 必須 (1 件以上) | 仕様本文 | `status="failed"`、`diagnostics.config_error.message="sources.include did not match any Source Specs"`、CLI exit code 1 |

#### オプション

| オプション | 必須 | 既定値 | 意味 | 観測効果 |
|---|---|---|---|---|
| `--all` / `-a` | 任意 | (未指定) | LLM 由来 cache (section_metadata / pair typing / chapter_anchors) をクリアして再評価 | 全 Section の LLM 出力を再生成。embedding は hash 一致時に再利用 |
| `--rebuild` | 任意 | (未指定) | `--all` を含意し、さらに検索基盤 (`[retrieval].section_collection`) を drop + recreate | `core_progress.json` の `stages.section_collection_upsert.action="upserted_full"` |
| `--verify-index` | 任意 | (未指定) | 検索基盤の内容と現在の Section hash の一致を能動検証。不整合検出時は `retrieval_index_status="failed"` で停止 | 不整合時に `/spec-core --rebuild` を促す stop output |
| `--llm-provider <id>` | 任意 | `[llm.stage_routing]` の指定 | 指定 id で `[llm.stage_routing]` の全 stage を上書き | 指定 provider を全 stage で使う。Codex skill / Claude command は通常指定しない |
| `--decision-json '<json>'` | 任意 | (未指定) | 未判断 Conflict Review Item に対する判断結果を JSON で渡す | §11 の遷移に従って status を更新 |
| `--decision-file <path>` | 任意 | (未指定) | 同上、JSON ファイルから読み込み | 同上 |

#### 出力

stdout JSON 1 つ。top-level および Agent / 利用者 / 後続コマンドが参照する nested field を網羅する。

| field | 型 | 必須 | 意味 |
|---|---|---|---|
| `status` | string | 必須 | `updated` / `degraded` / `failed` / `error` |
| `mode` | string | 必須 | `incremental` / `full` |
| `project_root` | string | 必須 | 解決済 project root の絶対 path (posix 形式) |
| `updated_sources[]` | list | 必須 | 今回更新された Source Specs ファイルの相対 path |
| `skipped_sources[]` | list | 必須 | 変更なしで skip された Source Specs |
| `failed_sources[]` | list | 必須 | 読み込み / 処理で失敗した Source Specs |
| `failed_sections[]` | list[object] | 必須 | 失敗 Section のリスト。各 object に `section_id` / `reason_code` / 追加情報 |
| `updated_sections[]` | list | 必須 | 今回更新された Section の `section_id` |
| `regenerated_chapter_anchors[]` | list | 必須 | 再生成された章 id のリスト |
| `retrieval_index_status` | string | 必須 | `success` / `skipped` / `skipped_unchanged` / `failed` / `blocked` (詳細は §5.1.1) |
| `related_sections_status` | string | 必須 | `success` / `skipped_unchanged` / `failed` / `blocked` (詳細は §5.1.2) |
| `potential_conflicts[]` | list | 必須 | 関連セクション由来の conflict 候補のうち、warning として残ったもの |
| `conflict_review_items[]` | list[object] | 必須 | Conflict Review Item のリスト (§11) |
| `pending_conflict_count` | int | 必須 | `status="pending"` の Conflict Review Item 件数 |
| `unreflected_conflict_resolutions[]` | list | 必須 | resolved だが Purpose / Core Concept / Source Specs に未反映の項目。未反映自体は blocker ではなく、後続 `/spec-inject` / `/spec-realign` の実行を止めない |
| `stale_resolution_count` | int | 必須 | base source の hash 変化により `stale_resolution` になった項目数 |
| `freshness_report` | object | 必須 | `freshness_report.status`、`freshness_report.blocking_reasons[]`、`freshness_report.warnings[]`、`freshness_report.diagnostics` を含む (§12) |
| `warnings[]` | list | 必須 | warning 文字列または object のリスト |
| `diagnostics` | object | 必須 | 診断用。各 context (`config_error` / `section_metadata_generation` / `chapter_anchors` / `related_sections` / `retrieval_index` ほか) ごとの reason / message。内部 field の追加・改名は本書中で影響範囲を明示する |

#### 5.1.1 `retrieval_index_status` の値

| 値 | 意味 |
|---|---|
| `success` | 検索基盤への upsert を実行し、最新の Section 集合と設定を反映済。索引は Section 単位 (1 Section = 1 検索結果)。Section 内部の chunk 分割は行わない |
| `skipped` | `[embedding]` / `[vector_store]` で機能が無効化されている (例: `embedding.provider != "flagembedding"`)。Agent は in-memory retrieval に fallback |
| `skipped_unchanged` | 入力 (Section 集合の hash と embedding / retrieval 設定指紋) が前回実行と完全一致。前回 index を引き続き有効として扱う。指紋が不一致、state file が欠損、または検索基盤の collection が不在の場合は通常 upsert に戻る |
| `failed` | 検索基盤の upsert / 接続で例外、または `--verify-index` で不整合検出。`/spec-core --rebuild` を促す |
| `blocked` | 上流の理由 (pending conflict / freshness 停止 / 入力読込失敗) で本 stage に到達せず |

#### 5.1.2 `related_sections_status` の値

| 値 | 意味 |
|---|---|
| `success` | 候補生成と LLM selection を実行し、関連セクションを最新化 |
| `skipped_unchanged` | 入力指紋 (Section 集合の hash と候補生成 / LLM selection 設定指紋) 一致で候補生成・LLM selection を skip。前回値を継承。指紋不一致または state file 欠損時は通常生成に戻る |
| `failed` | 関連セクション生成のいずれかの段階で失敗、または期待設定で検索基盤を初期化できなかった。canonical な関連セクションは更新されず前回値が残り、freshness は failed に降格 |
| `blocked` | 上流の理由で本 stage に到達せず |

#### 作成・更新される artifact

| artifact path | 作成条件 | 更新条件 | 更新しない条件 |
|---|---|---|---|
| `.spec-anchor/context/conflict_review_items.json` | 初回 `/spec-core` 実行時 (現状) | `/spec-core` 実行で Conflict Review Item の追加・status 遷移があった場合 | 例外発生 / 上流停止 |
| `.spec-anchor/context/chapter_anchors.json` | 初回 `/spec-core` 実行時 | 章単位の要点生成が成功した場合のみ | LLM 生成失敗 chapter があれば全体更新せず前回値を残す |
| `.spec-anchor/state/section_manifest.json` | 初回 `/spec-core` 実行時 | Section の差分検出メタデータが変わったとき | 常に更新される (incremental 判定用)。内部状態。利用者が直接参照する必要はない |
| `.spec-anchor/state/freshness.json` | 初回 `/spec-core` 実行時 | freshness 状態が変化したとき | 常に更新される (`/spec-inject` / `/spec-realign` が読む通信媒体)。利用者が直接参照する必要はないが、内容は §12 で外部契約として定義される |
| `.spec-anchor/state/retrieval_index_state.json` | 検索基盤への upsert 成功時 | upsert 成功時 | 例外発生 / `skipped_unchanged` のときは更新しない。内部状態 |
| `.spec-anchor/state/related_sections_state.json` | 関連セクション生成成功時 | 同上 | 同上。内部状態 |

`.spec-anchor/cache/` 配下と Qdrant collection の物理配置は外部仕様の対象外 (内部設計)。

incremental 更新時、CoreResult の `diagnostics` に以下の診断用 field が含まれる (互換性保証対象外)。

- `section_collection_upsert`: `action` (`upserted_full` / `upserted_partial` / `skipped_unchanged`)、`sections_upserted_count`、`sections_deleted_count`、`embed_documents_input_size`、`stale_points_deleted`、`partial_requested` (bool)、`migration_required_from_ordinal_point_id` (bool、point id 移行が発生した場合)
- `related_sections`: `candidate_generation_partial_mode` (`"full"` / `"source_changed_only"`)、`candidate_generation_source_count`、`candidate_generation_elapsed_sec`、`selection_elapsed_sec`、`requires_full_regeneration_for_complete_target_recheck` (bool)

`core_progress.json` は診断用で、stage 名は `start` / `inputs_loaded` / `sections_loaded` / `section_metadata` / `section_collection_upsert` / `verify_index` / `related_sections` / `conflict_evaluation` / `chapter_anchors` / `artifact_write`。`stages.section_collection_upsert.action` に出る値 (`upserted_full` / `upserted_partial` / `skipped_unchanged`) は外部観測可能 (診断用)。

#### 正常終了

- CLI exit code: 0 (`status="updated"` または `status="degraded"`)
- stdout JSON: 上記 field がすべて出力される
- 後続コマンド: `/spec-inject` / `/spec-realign` が実行可能 (freshness が `fresh` または `degraded`)

#### 警告付き続行

- 発火条件: Section Metadata の LLM 生成が一部 Section で失敗、ただし必須 artifact は揃う
- CLI exit code: 0
- 追加 warning: `warnings[]` に Section ごとの失敗説明、`status="degraded"`、`freshness_report.status="degraded"`、`freshness_report.blocking_reasons=["degraded_optional_artifact"]`、`freshness_report.diagnostics.degraded_optional_artifacts=["section_metadata"]`
- 後続コマンド: 実行可能。必要に応じて `/spec-core --all` で再生成

#### 停止 / 失敗

| 発火条件 | reason / status | 利用者に表示される内容 | CLI exit code | 利用者の次アクション |
|---|---|---|---|---|
| 設定ファイル不在 | `status="failed"`、`diagnostics.config_error.reason_code="config_error"`、message=`.spec-anchor/config.toml not found under {root}` | 不在 path とともに reason | 1 | `spec-anchor-setup-project --target <root>` |
| Purpose ファイル不在 | `status="failed"`、message=`core.purpose_file not found: {path}` | 不在 path | 1 | Purpose ファイルを作成 |
| Core Concept ファイル不在 | `status="failed"`、message=`core.concept_file not found: {path}` | 不在 path | 1 | Core Concept ファイルを作成 |
| `[sources].include` が 0 件マッチ | `status="failed"`、message=`sources.include did not match any Source Specs` | message と include 値 | 1 | Source Specs を配置 / `[sources].include` を実在 path に修正 |
| 章単位の要点生成失敗 | `status="failed"`、`diagnostics.chapter_anchors={status:"failed", failed_chapter_ids:[...], failure_reasons_by_chapter:{...}}`、`warnings[]` に `Chapter Anchors LLM generation failed for {N} chapter(s); canonical chapter_anchors.json is not updated. Run /spec-core --all to retry.`、`freshness_report.diagnostics.failed_required_artifacts=["chapter_anchors"]` | 失敗章数と warning | 1 | `/spec-core --all` で再試行 |
| 検索基盤に到達できない (`[vector_store].provider="qdrant"` 設定済み) | `status="failed"`、`retrieval_index_status="failed"`、`related_sections_status="failed"`、`diagnostics.related_sections.qdrant_backend_failure={"exception_type":"ResponseHandlingException","failure_reason":"[Errno 111] Connection refused","provider":"qdrant","url":"..."}`、`warnings[]` に `Source Retrieval Index update failed` と `Related Sections retrieval backend failure: {reason}; canonical related_sections artifact is not updated. Restore Qdrant connectivity and run /spec-core --rebuild.` | 接続失敗理由 | 1 | サービス起動後 `/spec-core --rebuild` |
| 検索基盤の upsert 失敗 | `status="failed"`、`retrieval_index_status="failed"`、`warnings[]` に `Source Retrieval Index update failed`、`freshness_report.diagnostics.failed_required_artifacts=["retrieval_index"]` | 失敗理由 | 1 | `/spec-core --rebuild` |
| `--verify-index` で不整合検出 | `status="failed"`、`retrieval_index_status="failed"`、`warnings[]` に `Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild`、`freshness_report.diagnostics.failed_required_artifacts=["retrieval_index"]`、`diagnostics.verify_index.stale_point_count=<件数>`、`diagnostics.verify_index.issues[].reason_code="stale_point"` | 不整合 point 数と stale point 一覧 | 1 | `/spec-core --rebuild` |

#### 副作用として行わないこと

- Purpose ファイルと Core Concept ファイルを書き換えない (実行前後で内容一致)
- Source Specs ファイルを書き換えない
- Conflict Review Item の status を人間判断なしに `resolved` に変えない (`--decision-json` / `--decision-file` を経由しない)
- `.spec-anchor/config.toml` を書き換えない
- 章単位の要点生成失敗時に canonical `chapter_anchors.json` を上書きしない (前回値を残す)
- 関連セクション生成失敗時に canonical な関連セクション情報を上書きしない (前回値を残す)
- Qdrant 期待設定で検索基盤が初期化できないとき、別 backend (InMemory) に黙って fallback しない (期待 backend での失敗として報告)

### 5.2 Agent slash command / skill 契約

#### 発火形式

利用者が Agent CLI で `/spec-core [--all|--rebuild]` を発火する (Claude Code の slash command、Codex の SPEC-anchor skill のいずれか)。

#### Agent が内部で呼び出す shell CLI

`spec-anchor core [<flags>]` を 1 回実行する。

#### Agent が利用者へ提示する正常時の出力

- 実行モード (`incremental` / `full`) と `--all` / `--rebuild` の有無
- 更新された Source Specs と Section の件数
- 検出された Conflict Review Item の件数 (あれば)
- warning の有無と内容 (あれば)
- 後続コマンドが実行可能かの判定

shell CLI の raw JSON を貼らず、構造化して伝える。

#### Agent が停止時に利用者へ提示する内容

| 停止理由 (CLI `status="failed"` または `diagnostics`) | Agent 出力に必ず含める情報 | Agent が提案する次アクション |
|---|---|---|
| config 不在 | 不在 path、`diagnostics.config_error.message` | `spec-anchor-setup-project --target <path>` |
| Purpose / Core Concept 不在 | 不在 path、人間が中身を書く必要 | 該当ファイルを作成 |
| Source Specs 0 件 | `[sources].include` 値、対象 glob | Source Specs 配置 or `[sources].include` 修正 |
| 章単位の要点生成失敗 | 失敗章数、前回値が保持される旨 | `/spec-core --all` |
| 検索基盤接続失敗 | 接続先 url、復旧手順 (サービス起動) | サービス起動後 `/spec-core --rebuild` |
| 検索基盤 upsert / verify 失敗 | 失敗理由 | `/spec-core --rebuild` |

#### Agent が追加確認を求める条件

なし (`/spec-core` は会話文脈の解釈を必要としない)。

#### shell CLI exit code / status の Agent 出力への写し方

- `status="updated"` → 正常終了として上記正常時の出力を提示
- `status="degraded"` → warning を必ず提示し、後続コマンドが実行可能である旨を明示
- `status="failed"` / `status="error"` → 停止時の出力テーブルに従う。`recommended_next_action` 相当の Agent 提案を必ず添える

#### Agent slash command 層で行わないこと

- shell CLI を呼ばずに会話だけで「実行した」と装わない
- shell CLI の `status` / reason を要約で書き換えて利用者へ伝達しない (`failed` を `degraded` に弱めない)
- shell CLI 失敗時に `/spec-core --all` / `--rebuild` 等を Agent が自動実行しない (人間判断を要する)

### 5.3 `core_progress.json` の構造 (診断用)

`/spec-core` 実行中、`.spec-anchor/state/core_progress.json` に stage 進捗が逐次書き込まれる。プロセスが途中で kill されても最後の状態が残る。

top-level field: `run_id` / `mode` / `generated_at` / `started_at` (ISO 8601 UTC) / `updated_at` / `current_stage` / `finalized_at` / `final_status` / `stage_order[]` / `stages` (dict)

各 stage entry の field: `stage` / `raw` / `started_at` / `started_at_epoch` / `llm_calls` / `token_count` / `retry_count` / `failed_batch_ids[]` / `finished_at` / `elapsed_sec` / `checkpoints[]`

本 file の内部 field 構造は診断用であり、互換性保証対象外である (§14.1)。

## 6. `/spec-inject` の外部仕様

### 6.1 shell CLI 契約

`/spec-inject` は内部で次のサブコマンドを呼び分ける。

```text
spec-anchor inject-search "<query>"
spec-anchor inject-section "<section_id>" [<section_id>...]
spec-anchor inject-chapters
spec-anchor inject-purpose
spec-anchor inject-conflicts
```

各サブコマンドは内部で §12 freshness gate を通す。Agent は別途 probe を呼ぶ必要はない。

#### 6.1.1 共通契約

##### CLI exit code

常に 0。停止状態は stdout JSON の `should_stop` / `blocking_reasons` / `status` で表現する。

成功時の出力 field は各サブコマンド節 (§6.1.2〜§6.1.6) の出力テーブルに従う。freshness gate で停止した場合は、サブコマンド固有の field の代わりに下記共通 field が返る。

##### 共通停止 / 失敗 (freshness gate)

| 発火条件 (freshness gate) | reason / status | stdout JSON | 利用者の次アクション |
|---|---|---|---|
| Source Specs 変更が `/spec-core` で未反映 | `status="blocked"`、`should_stop=true`、`blocking_reasons=["dirty_or_stale_source"]`、`recommended_next_action="run /spec-core before /spec-inject"` | 左記 field を含む JSON | `/spec-core` |
| 設定 / schema が古い | `blocking_reasons=["stale_config_or_schema"]`、`recommended_next_action="run /spec-core --all before /spec-inject"` | 同上 | `/spec-core --all` |
| watcher 動作中 / 未処理キュー残 | `blocking_reasons=["watcher_running"]` または `["watcher_queue_pending"]`、`recommended_next_action="wait for watcher completion before /spec-inject"` | 同上 | watcher 完了待ち |
| 未判断 Conflict Review Item あり | `status="blocked"`、`blocking_reasons=["pending_conflict"]`、`pending_conflict_count=<件数>`、`recommended_next_action="resolve pending Conflict Review Items"` | 左記 + `pending_conflict_items[]` | §11 の手順で判断を返す |
| 必須 artifact が `failed` (直前 `/spec-core` で `failed_required_artifact`) | `status="failed"`、`blocking_reasons=["failed_required_artifact"]`、`recommended_next_action="run /spec-core or /spec-core --all before /spec-inject"` | 同上 | `/spec-core` または `/spec-core --all` |
| 例外発生 (config 不在等) | `status="error"`、`error={"code":"command_error","type":"ConfigError","message":"..."}` | 左記 + `error` object | error message に従う |

##### 共通入力

`<project_root>/.spec-anchor/config.toml` が必須。不在時は `error={"code":"command_error","type":"ConfigError","message":".spec-anchor/config.toml not found under {root}"}` を返す (CLI exit code は 0)。

#### 6.1.2 `spec-anchor inject-search "<query>"`

##### 実行形式

```text
spec-anchor inject-search "<query>"
```

##### 入力

| 入力 | 必須 | 説明 | 不備がある場合 |
|---|---|---|---|
| `<query>` (位置引数) | 必須 | 自然言語または Section Identifiers の検索クエリ | 空文字列時: exit 0、`hits=[]`、`warnings=[{"message":"query must be a non-empty string","reason_code":"empty_query"}]` |

##### オプション

該当なし (CLI 固有フラグはない)。

##### 出力

| field | 型 | 必須 | 意味 |
|---|---|---|---|
| `command` | string | 必須 | `"/spec-inject inject-search"` |
| `project_root` | string | 必須 | project root の絶対 path |
| `query` | string | 必須 | 実行された検索クエリ |
| `collection` | string | 必須 | 検索対象の collection 名 |
| `top_k` | int | 必須 | 適用された top-K 値 |
| `hits[]` | list[object] | 正常時必須 | 検索結果。各 object に下記 field |
| `hits[].source_section_id` | string | 必須 | `source_section_id` (§2.5) |
| `hits[].source_document_id` | string | 必須 | Source Specs ファイルの相対 path |
| `hits[].source_span` | object | 必須 | Section の本文範囲。`start_line` (int) / `end_line` (int) / `start_offset` (int) / `end_offset` (int) |
| `hits[].heading_path[]` | list[string] | 必須 | Section の Markdown heading path (親見出しからの連鎖) |
| `hits[].summary` | string | 必須 | セクションごとの要約 |
| `hits[].search_keys[]` | list[string] | 必須 | セクション検索キー |
| `hits[].identifiers[]` | list[string] | 必須 | セクション識別子 (コードシンボル / 固有技術名) |
| `hits[].related_sections[]` | list[object] | 必須 | 関連先一覧。各 object に `target_section_id` / `relation_hint` (`depends_on` / `impacts` / `prerequisite` / `same_policy` / `see_also`) / 必要に応じて `possible_conflict: true`。`relation_hint` に `conflicts_with` は出現しない。矛盾の兆候は `possible_conflict: true` に留め、最終判定は Conflict Review Item (§11) へ委ねる |
| `hits[].score` | float | 必須 | retrieval score (融合後) |
| `warnings[]` | list[object] | 必須 | 空文字列時は `[{"message":"query must be a non-empty string","reason_code":"empty_query"}]` |

#### 6.1.3 `spec-anchor inject-section "<id>" [<id>...]`

##### 実行形式

```text
spec-anchor inject-section "<id>" [<id>...]
```

##### 入力

| 入力 | 必須 | 説明 | 不備がある場合 |
|---|---|---|---|
| `<id>` (位置引数、1 つ以上) | 必須 | `source_section_id` (§2.5) | 未存在 ID: exit 0、`missing_section_ids` で通知、`sections` には含まれない。部分成功 (一部 found + 一部 missing) は正常動作 |

##### 出力

| field | 型 | 必須 | 意味 |
|---|---|---|---|
| `command` | string | 必須 | `"/spec-inject inject-section"` |
| `project_root` | string | 必須 | project root の絶対 path |
| `collection` | string | 必須 | 検索対象の collection 名 |
| `requested_section_ids[]` | list[string] | 必須 | 利用者が指定した id のリスト (入力順) |
| `found_section_ids[]` | list[string] | 必須 | 実際に見つかった id のリスト |
| `missing_section_ids[]` | list[string] | 必須 | 見つからなかった id のリスト |
| `sections` | object (dict) | 必須 | id をキー、Section payload を値とする dict。payload の構造は `inject-search` の `hits[]` の各 object と同じ |
| `warnings[]` | list | 必須 | warning があれば |

未存在 ID はエラーにならない。`missing_section_ids` で通知され、`sections` には含まれない (exit code 0)。部分成功 (一部 found + 一部 missing) が正常動作。

#### 6.1.4 `spec-anchor inject-chapters`

##### 出力

| field | 型 | 必須 | 意味 |
|---|---|---|---|
| `command` | string | 必須 | `"/spec-inject inject-chapters"` |
| `status` | string | 必須 | `success` / `blocked` / `failed` / `error` |
| `chapter_anchors_path` | string | 正常時必須 | `.spec-anchor/context/chapter_anchors.json` の絶対 path。Agent は path を `Read` で読み、必要箇所を抽出する |

`chapter_anchors.json` の構造 (各 chapter entry に `chapter_id` / `summary` / `key_topics[]` / `important_sections[]` / `notes[]` / `source_section_ids[]` が含まれる) は §13.2 を参照。

#### 6.1.5 `spec-anchor inject-purpose`

##### 出力

| field | 型 | 必須 | 意味 |
|---|---|---|---|
| `command` | string | 必須 | `"/spec-inject inject-purpose"` |
| `purpose` | string | 正常時必須 | Purpose ファイルの全文 (短いため全文を CLI が直接返す) |
| `core_concept_path` | string | 正常時必須 | Core Concept ファイルの絶対 path。Agent は `Read` で必要箇所を抽出 |

`core_concept_path` が指す file が存在しない場合 (削除された場合): exit 0 で `purpose` (Purpose 全文) は返す。`core_concept_path` は不在 path のまま返す。`warnings=[{"message":"concept_file not found: {path}","reason_code":"concept_file_missing"}]`。

#### 6.1.6 `spec-anchor inject-conflicts`

##### 出力

| field | 型 | 必須 | 意味 |
|---|---|---|---|
| `command` | string | 必須 | `"/spec-inject inject-conflicts"` |
| `resolved_conflict_review_items[]` | list[object] | 正常時必須 | `status="resolved"` かつ `stale_resolution: false` の Conflict Review Item の一覧 (§11.5 の object 構造) |
| `excluded_conflict_review_items[]` | list[object] | 正常時必須 | 除外された item の一覧。各 object に `conflict_id` / `reason_code` (`stale_resolution` / `status_pending` / `status_dismissed` 等) |
| `count` | int | 正常時必須 | `resolved_conflict_review_items` の件数 |

#### 6.1.7 共通副作用として行わないこと

- Source Specs / Purpose / Core Concept を書き換えない
- 自動で `/spec-core` を実行しない (保持物が古い場合は停止のみ。Agent / 利用者が `/spec-core` を明示実行する)
- 自動探索 / 多段 traversal を実行しない (各サブコマンドは単発の retrieval / payload lookup / 章 anchor 取得 / Purpose 取得 / Conflict Review Item 取得のみ提供)
- Conflict Review Item の status を変更しない (status 変更は `/spec-core --decision-*` 経由)
- 制約セット (`statement` / `evidence_origin` 等) を CLI 出力に fabricate しない (constraint statement の最終生成は Agent / LLM の責務)

### 6.2 Agent slash command / skill 契約

#### 発火形式

利用者が Agent CLI で `/spec-inject "<task>"` を発火する。または会話文脈から課題を Agent が解釈する形でも発火可能。

#### Agent が内部で呼び出す shell CLI

§6.2 末尾の 4 path に従い、課題の性質に応じて次の組み合わせで `spec-anchor inject-*` を呼ぶ (Agentic Search)。

- **path ①** (具体的 API / 識別子): `inject-search` → `inject-section` (related 辿りで複数回)
- **path ②** (全体方針 / 抽象的): `inject-chapters` → 該当章配下に対して `inject-search` / `inject-section`
- **path ③** (Purpose / Core Concept 直接質問): `inject-purpose` (Purpose 全文は `purpose` field で直接返る。Core Concept は `core_concept_path` を `Read` で参照)
- **path ④** (過去判断の継続): `inject-conflicts`。利用時は各 item の `valid_scope` (`global` / `task_scope`) と `resolution.referenced_source_refs` を確認する

Agent は path を組み合わせて使い分ける。CLI は探索方針を自律的に決めない。

#### 根拠と入力の区別

会話区間 (現在のユーザー発話、直近の会話、明示された課題プロンプト、進行中の作業対象) は検索キー生成と制約生成の入力であり、仕様上の根拠ではない。最終根拠は Purpose / Core Concept / Source Specs / stale でない resolved Conflict Review Item のいずれかに由来し、どれに由来するかを `evidence_origin` で区別する。

#### 生テキスト投入の制限

Source Specs 本文、Core Concept、Chapter Key Anchor を無条件に LLM コンテキストへ丸ごと投入しない。Agent は Agentic Search で必要な箇所だけを `Read` で読み、課題に関連する部分を抽出する。読んだ本文を未整理のまま最終回答の前提へ混ぜない。全文を最終コンテキストとして扱うのは、ユーザーが明示的に全文レビューを求めた場合に限る。

#### Agent が利用者へ提示する正常時の出力

freshness が `fresh` または `degraded` の場合、次の 5 セクション構造で利用者へ提示する。

```text
今回守る制約
  - <制約>
    根拠: Purpose / Core Concept / Source Specs / Conflict Review Item のいずれか
    source: <source_document_id / source_section_id / source span / 該当 path>
    参照補助: <セクションごとの要約 / 章単位の要点 / 関連セクション>

今回見るべき対象
  - <Section または topic>
    理由: <なぜ今回関係するか>

関連セクションとして確認したもの
  - <related Section>
    理由: <depends / impacts / related など>

採用しなかったもの
  - <候補>
    理由: <今回の課題には遠い / 根拠不足 / 別論点>

不確実性 / 人間確認
  - <確認すべき点>
```

各セクションは該当 0 件でも「該当なし」を明示し、省略しない。

制約セット (上記「今回守る制約」の各 item) は、最小構造として次を満たす。

| field | 必須 | 意味 |
|---|---|---|
| `statement` | 必須 | 今回守る制約 |
| `evidence_origin` | 必須 | `Purpose` / `Core Concept` / `Source Specs` / `Conflict Review Item` のいずれか |
| `evidence_ref` | 必須 | 文書 path、`source_section_id`、source span、Core Concept の項目、または stale でない `conflict_id` |
| `support_refs` | 任意 | セクションごとの要約 / 関連セクション / 章単位の要点 などの参照補助 |
| `applicability` | 任意 | 今回の課題でどこに効く制約か |
| `uncertainty` | 任意 | 根拠不足 / 衝突 / 人間確認が必要な点 |

`statement` / `evidence_origin` / `evidence_ref` の 3 field は欠かさない。検索キー / セクションごとの要約 / 関連セクション・章単位の要点だけを根拠に制約を確定しない (根拠は常に Purpose / Core Concept / 仕様本文 / stale でない resolved Conflict Review Item のいずれか)。

#### Agent が停止時に利用者へ提示する内容

| 停止理由 (`blocking_reasons`) | Agent 出力に必ず含める情報 | Agent が提案する次アクション |
|---|---|---|
| `dirty_or_stale_source` | Source Specs が変更されたが保持物が古いこと、Agentic Search を実行していない旨 | `/spec-core` を実行してから `/spec-inject` 再実行 |
| `stale_config_or_schema` | 設定 / schema 変更で全章再評価が必要なこと | `/spec-core --all` 後に `/spec-inject` 再実行 |
| `watcher_running` / `watcher_queue_pending` | 自動更新動作中 / 未処理キュー残のこと | 完了待ち後に `/spec-inject` 再実行 |
| `pending_conflict` | `pending_conflict_items[]` の各項目を §11.4 の構造で提示 (`conflict_id` / `severity` / `claims` / `why_conflicting` / `why_llm_cannot_decide` / `decision_options` / `source_refs` / `recommended_next_action`) | 人間判断で各 conflict を resolved にして `/spec-inject` 再実行 |
| `failed_required_artifact` | 直前 `/spec-core` の `warnings[]` 内容 (失敗 artifact 名と理由) | `/spec-core --all` で再構築後に `/spec-inject` 再実行 |
| config 不在 / 例外 | `error.message` の内容 | `spec-anchor-setup-project --target <path>` などの復旧手順 |

#### Agent が追加確認を求める条件

Agent が課題の中心を特定できなかった場合 (会話文脈から target task が判別できない場合)、回答生成を進めず、利用者へ追加情報を要求する。

#### shell CLI exit code / status の Agent 出力への写し方

- CLI exit code は常に 0 だが、`status="blocked"` / `"failed"` / `"error"` のいずれでも Agent は **Agentic Search を実行せず** 停止状態を利用者へ伝達する
- `recommended_next_action` を必ず転写する
- raw JSON は貼らず、上記 5 セクション (正常時) または §6.2 停止時テーブルの構造で整形する

#### Agent slash command 層で行わないこと

- 課題に対する最終回答 / 実装コード / 結論文を提示しない (`/spec-inject` の出力は制約セットに限る)
- 検索キーやセクションごとの要約だけを根拠に制約を確定しない (3 field 必須を Agent 側で自己点検する)
- 制約構造の検証を CLI に委ねない (`spec-anchor inject-*` は制約構造を検証しない)
- shell CLI を呼ばずに会話だけで制約を出さない
- Conflict Review Item を根拠にする場合、`inject-conflicts` の返却範囲 (resolved かつ stale でない) を超えて採用しない


## 7. `/spec-realign` の外部仕様

### 7.1 shell CLI 契約

#### 実行形式

```text
spec-anchor realign [--answer <text> | --answer-text <text> | --agent-answer <text>]
                    [--answer-json <json> | --agent-answer-json <json>]
                    [--answer-file <path> | --agent-answer-file <path>]
```

#### 入力

| 入力 | 必須 | 説明 | 不備がある場合 |
|---|---|---|---|
| `<project_root>/.spec-anchor/config.toml` | 必須 | 設定ファイル | `error={"code":"command_error","type":"ConfigError"...}`、CLI exit code 1 |
| Agent が構成した answer candidate | 必須 | Agent が §6.2 の 4 path で抽出した制約と回答案を 4 区分構造で構成したもの。CLI option 経由で渡す | 不在時は `status="fresh"`、`stop_reason="needs_agent_answer"`、`should_stop=true`、`recommended_next_action="provide an Agent-generated answer candidate for /spec-realign"`、CLI exit code 0 |

#### オプション

| オプション | 必須 | 既定値 | 意味 | 観測効果 |
|---|---|---|---|---|
| `--answer <text>` / `--answer-text <text>` / `--agent-answer <text>` | 排他必須 (3 形式のいずれか) | — | answer candidate を plain text で渡す。3 形式は alias | RealignResult の `answer` field 構築 |
| `--answer-json <json>` / `--agent-answer-json <json>` | 排他必須 | — | answer candidate を JSON object で渡す | 同上 |
| `--answer-file <path>` / `--agent-answer-file <path>` | 排他必須 | — | answer candidate を JSON または plain text のファイルから読み込む | 同上 |

#### 出力

| field | 型 | 必須 | 意味 |
|---|---|---|---|
| `command` | string | 必須 | `"/spec-realign"` |
| `status` | string | 必須 | `fresh` / `blocked` / `failed` / `error` |
| `project_root` | string | 必須 | project root の絶対 path |
| `should_stop` | bool | 必須 | gate 停止または needs-answer 時 true |
| `answer` | object | 正常時必須 | RealignResult。下記の 4 区分構造を含む |
| `answer["今回守る制約"]` | list | 必須 | 制約 |
| `answer["今回扱う修正候補または検討対象"]` | list | 必須 | 修正候補 (該当なしの場合は空 list) |
| `answer["競合 / 不確実性 / 人間レビューが必要な点"]` | list | 必須 | 矛盾・判断保留・人間確認が必要な点 |
| `answer["課題プロンプトへの回答または修正案"]` | list | 必須 | 回答または修正案 |
| `freshness_report` | object | 必須 | §12 |
| `blocking_reasons[]` | list | gate 停止時必須 | §12 |
| `recommended_next_action` | string | gate 停止 / needs-answer 時必須 | 利用者の次アクション |
| `pending_conflict_items[]` | list | `blocking_reasons` に `pending_conflict` 含む時必須 | §11 |
| `error` | object | 例外発生時必須 | `code` / `type` / `message` |

#### 正常終了

- CLI exit code: 0 (`status="fresh"` で `answer` が構築できた場合)
- stdout JSON: `answer` を含む
- 後続コマンド: 該当なし (`/spec-realign` は対話の終端)

#### 警告付き続行

- 発火条件: freshness が `degraded` だが必須 artifact は揃う
- CLI exit code: 0
- 追加 warning: `freshness_report.warnings[]` に degraded 内容

#### 停止 / 失敗

`/spec-inject` と同じ freshness gate を共有 (§6.1.1 / §12)。加えて次の固有停止がある。

| 発火条件 | reason / status | stdout JSON | CLI exit code | 利用者の次アクション |
|---|---|---|---|---|
| Agent が answer candidate を渡さない、または内容が空 | `status="fresh"`、`stop_reason="needs_agent_answer"`、`should_stop=true`、`answer` field なし、`error` field なし、`recommended_next_action="provide an Agent-generated answer candidate to spec-anchor realign"` | 上記 | 0 | Agent が answer candidate を 4 区分で構成して再実行 |
| `--answer-text` + `--answer-json` (または他の answer option) を複数同時指定 | `status="error"`、`error={"code":"command_error","type":"ValueError","message":"answer must be supplied by only one answer option"}` | エラー内容 | 1 | answer option を 1 つだけ指定して再実行 |
| `--answer-file` に存在しない path を指定 | `status="error"`、`error={"code":"command_error","type":"FileNotFoundError","message":"..."}` | 不在 path | 1 | 正しい file path を指定して再実行 |
| 設定不在等の例外 | `status="error"`、`error.code="command_error"`、CLI exit code 1 | 同上 | 1 | error message に従う |

#### 副作用として行わないこと

- 回答本文を独自生成しない (CLI は受け取った answer を 4 区分構造で整形するのみ。新規 LLM 呼び出しを行わない)
- Purpose / Core Concept / Source Specs を書き換えない
- gate 停止時に answer の整形を行わない

### 7.2 Agent slash command / skill 契約

#### 発火形式

利用者が `/spec-realign "<task>"` を発火する。

#### Agent が内部で呼び出す shell CLI

`/spec-inject` と同じ §6.2 の 4 path で制約を抽出した後、`spec-anchor realign --answer-json '<json>'` (または `--answer-text` / `--answer-file`) を呼ぶ。

#### Agent が利用者へ提示する正常時の出力

次の 4 区分構造で提示する。

```text
今回守る制約
  (/spec-inject と同じ構造)

今回扱う修正候補または検討対象
  (今回の課題で対象とする変更箇所、検討対象、影響範囲など)

競合 / 不確実性 / 人間レビューが必要な点
  (生成した制約と回答案の矛盾、判断保留事項、人間判断が必要な箇所)

課題への回答または修正案
  (具体的な回答、コード案、修正案)
```

各区分は該当 0 件でも「該当なし」を明示する。

回答案が制約と矛盾する場合、矛盾を隠さず必ず「競合 / 不確実性 / 人間レビューが必要な点」区分に明示する。

#### Agent が停止時に利用者へ提示する内容

`/spec-inject` の停止時テーブル (§6.2) と同じ理由群。加えて:

| 停止理由 | Agent 出力に必ず含める情報 | Agent が提案する次アクション |
|---|---|---|
| Agent が課題の中心を特定できなかった (`/spec-realign` 固有) | 課題が抽象的すぎる旨、`/spec-inject` で制約だけ先に確認できる旨 | 課題を具体化して再依頼、または `/spec-inject` で制約を先に確認 |
| `needs_agent_answer` (CLI が answer candidate を要求) | `/spec-inject` で制約を取得済みでない場合の手順 | `/spec-inject` で制約取得 → answer candidate を 4 区分で構成 → `/spec-realign` 再実行 |

#### Agent が追加確認を求める条件

Agent が課題の中心を特定できなかった場合は、利用者へ追加情報を要求する。

#### shell CLI exit code / status の Agent 出力への写し方

- `status="fresh"` で `answer` が構築できた → 4 区分の利用者向け出力に展開
- `status="fresh"` で `stop_reason="needs_agent_answer"` → answer candidate が必要である旨を伝達
- `status="blocked"` / `"failed"` / `"error"` → answer の整形は行わず、停止理由を伝達

#### Agent slash command 層で行わないこと

- 制約と矛盾する回答案を、矛盾を隠した形で提示しない
- shell CLI を呼ばずに回答を組み立てない
- gate 停止時に回答だけを進めない
- 課題の中心が特定できないまま自由生成で回答しない


## 8. `spec-anchor-watch` の外部仕様

### 8.1 shell CLI 契約

#### 実行形式

```text
spec-anchor-watch [--once] [--interval-sec <秒>] [--debounce-sec <秒>] [--stale-lock-sec <秒>] [--max-runs <回数>]
```

#### 入力

| 入力 | 必須 | 説明 | 不備がある場合 |
|---|---|---|---|
| `<project_root>/.spec-anchor/config.toml` | 必須 | 設定ファイル | `error={"code":"command_error","type":"ConfigError"...}`、watcher loop に入らず早期 return |

#### オプション

| オプション | 必須 | 既定値 | 意味 | 観測効果 |
|---|---|---|---|---|
| `--once` | 任意 | (未指定) | 1 回だけ scan して終了する | poll loop に入らない |
| `--interval-sec <秒>` | 任意 | `2.0` | 変更がないときの poll 間隔 | poll 頻度 |
| `--debounce-sec <秒>` | 任意 | `1.0` | 変更検知後、update を開始するまでの待ち時間 | 連続変更を 1 サイクルに統合 |
| `--stale-lock-sec <秒>` | 任意 | `300` | lock file がこの秒数を超えたら stale とみなして回収 | 古い lock を強制回収 |
| `--max-runs <回数>` | 任意 | (未指定、無制限) | 指定回数 update したら終了 | 終了条件 |

#### 出力

1 つの JSON object を stdout に出力する。object 内に `cycles[]` 配列を持ち、各要素が 1 update サイクルの CoreResult 相当の結果を含む。`--once` の場合は `cycle_count=1`。top-level に集計情報 (`cycle_count` / `run_count` / `freshness_report` / `settings` ほか) が付く。

#### 作成・更新される artifact

| artifact path | 作成条件 | 更新条件 | 更新しない条件 |
|---|---|---|---|
| `[watcher].state_file` (既定 `.spec-anchor/state/watch_state.json`) | 初回起動時 | poll 状態が変化したとき | 例外発生。内部状態 |
| `[watcher].queue_file` (既定 `.spec-anchor/state/watch_queue.json`) | 初回起動時 | 未処理キューが変化したとき | 例外発生。内部状態 |
| `.spec-anchor/state/freshness.json` | 更新サイクル開始・完了時 | 更新サイクルごと | 常に更新される |

加えて、`/spec-core` 相当の background execution として §5.1 の artifact を更新する。Agent CLI は起動しない (watcher process 内部で実行)。

#### 正常終了

- CLI exit code: 常に 0
- `--once` または `--max-runs` で指定回数達成後に終了
- watcher 動作中、`/spec-inject` / `/spec-realign` は freshness gate で停止する (§12)

#### 停止 / 失敗

| 発火条件 | 表示内容 | CLI exit code | 利用者の次アクション |
|---|---|---|---|
| 設定ファイル不在 | `error={"code":"command_error","type":"ConfigError","message":".spec-anchor/config.toml not found under {root}"}` | 0 | `spec-anchor-setup-project` で初期化 |
| 古い lock が残存 (stale-lock-sec 超過前) | watcher は待機せず即座に `status="locked"` を返す。freshness artifact を `watcher_running=true` に設定し、`last_lock_contention` (lock owner / lock diagnostics / queue count) を state に記録する | 0 | `--stale-lock-sec` を調整、または watcher 再起動 |

#### 副作用として行わないこと

- LLM への課題対応 (制約注入や回答生成) を行わない (`/spec-inject` / `/spec-realign` 経路を実行しない)
- Purpose と Core Concept を書き換えない
- 1 サイクル中に追加された変更を当該サイクルに含めない (次回スキャンで検知され、queue に FIFO 順で追加される)

`[watcher].enabled=false` の状態で `spec-anchor-watch --once` を実行した場合: 1 cycle を実行して正常終了する (`enabled` flag は `--once` を抑止しない)。

### 8.2 Agent slash command / skill 契約

該当なし。`spec-anchor-watch` は slash command / skill 経由で発火しない。


## 9. `spec-anchor-setup-system` の外部仕様

### 9.1 shell CLI 契約

#### 実行形式

```text
spec-anchor-setup-system [--check-only] [--qdrant-url <url>] [--run-smoke]
```

#### 入力

なし (既存環境を対象に動作)。

#### オプション

| オプション | 必須 | 既定値 | 意味 | 観測効果 |
|---|---|---|---|---|
| `--check-only` | 任意 | (規定動作) | 確認のみを行う | 設定ファイルや保持物に書き込まない (現状の既定動作と同じ) |
| `--qdrant-url <url>` | 任意 | `http://localhost:6333` | 検索基盤の接続先を明示指定 | probe 対象 url |
| `--run-smoke` | 任意 | (未指定) | 検査用。Agent CLI 認識性の smoke probe を実行 | `agent_cli_entries` に `project_skill_path` / `project_command_path` などが追加される。出力内容は診断目的 |

#### 出力

| field | 型 | 必須 | 意味 |
|---|---|---|---|
| `status` | string | 必須 | `ok` / `degraded` / `error` / `failed` |
| `production_readiness` | object | 必須 | 利用環境の readiness 集計 |
| `production_readiness.status` | string | 必須 | `ready` / `blocked` |
| `production_readiness.blocking_reasons[]` | list[string] | 必須 | `qdrant_service_unavailable` / `flagembedding_package_unavailable` / `qdrant_client_package_unavailable` / `agent_cli_codex_unavailable` / `agent_cli_claude_unavailable` / `console_script_<name>_unavailable` 等 |
| `production_readiness.checks[]` | list[object] | 必須 | 各 check の結果。`name` / `status="passed"\|"failed"` / `reason_code` |
| `providers[]` | list[object] | 必須 | 検査した provider のリスト (`qdrant` / `FlagEmbedding` / `codex` / `claude` ほか)。各 object に `name` / `kind` / `available` / `version` / `error` |
| `console_scripts[]` | list[object] | 必須 | console script の検査結果 (`spec-anchor` / `spec-anchor-watch` / `spec-anchor-setup-project` / `spec-anchor-setup-system` / `spec-anchor-slash`)。各 object に `name` / `available` / `path` |
| `templates[]` | list[object] | 必須 | 診断用。template の検査結果。各 object に `available` (bool) / `path` (string、`templates/` prefix 付き template 相対 path)。6 項目: `.codex/skills/spec-anchor/SKILL.md` / `.claude/commands/spec-core.md` / `.claude/commands/spec-inject.md` / `.claude/commands/spec-realign.md` / `.spec-anchor/config.toml` / `.spec-anchor/.gitignore` |
| `diagnostics[]` | list[object] | 必須 | 個別 diagnostic |
| `agent_cli_entries` | object | `--run-smoke` 時必須 | 診断用。各 Agent CLI (`codex` / `claude`) の認識性。`cli.path` / `cli.version` / `project_skill_path` / `project_command_path` ほか |

#### 正常終了

- CLI exit code: 0 (status が `ok` or `degraded`)
- `production_readiness.status="ready"` で全前提が揃っている

#### 停止 / 失敗

| 発火条件 | reason / status | 表示内容 | CLI exit code | 利用者の次アクション |
|---|---|---|---|---|
| 検索基盤サービス未起動 | `production_readiness.status="blocked"`、`blocking_reasons=["qdrant_service_unavailable"]`、`providers[*].error="URLError"` (network error) または `"ValueError"` (URL syntax error) | 接続先 url と理由 | 0 (warning) | サービス起動 / URL を修正 |
| `FlagEmbedding` / `qdrant_client` package import 不可 | `blocking_reasons=["flagembedding_package_unavailable"]` / `["qdrant_client_package_unavailable"]` | 不在 package 名 | 0 (warning) | package 導入 |
| Agent CLI (`codex` / `claude`) が PATH 上に無い | `blocking_reasons=["agent_cli_codex_unavailable"]` / `["agent_cli_claude_unavailable"]` | 不在 CLI 名 | 0 (warning) | Agent CLI 導入 |
| console script が PATH 上に無い | `blocking_reasons=["console_script_<name>_unavailable"]` (不在 script 1 件につき 1 reason) | 不在 script 名 | 0 (warning) | SPEC-anchor 再インストール |

#### 副作用として行わないこと

- 対象プロジェクトの Source Specs / Purpose / Core Concept / 生成済み保持物を変更しない (`--check-only` 既定で確認専用)
- `.spec-anchor/` 配下に書き込まない
- 不足している前提を自動でインストールしない
- Agent CLI 認識性 (`--run-smoke`) の失敗を `production_readiness.blocking_reasons` に含めない (warning 扱い)

### 9.2 Agent slash command / skill 契約

該当なし。

### 9.3 `--run-smoke` の結果構造

`--run-smoke` 実行時、`smoke` field が出力に追加される。

| field | 型 | 意味 |
|---|---|---|
| `smoke.executed` | bool | smoke が実行されたか |
| `smoke.passed` | bool | 全 check が pass したか |
| `smoke.checks[]` | list[object] | 各 check の結果。`name` / `passed` / `returncode` (help check) / `status` (project check) |

smoke の pass/fail は `production_readiness.blocking_reasons` に含まれない (§9.1 副作用)。action に `{"name":"smoke_checks", "status":"checked", "executed":true, "passed":false}` として記録される。

## 10. `spec-anchor-setup-project` の外部仕様

### 10.1 shell CLI 契約

#### 実行形式

```text
spec-anchor-setup-project --target <path> [--agent <codex|claude|both>] [--dry-run] [--force] [--no-init-core-files]
```

#### 入力

| 入力 | 必須 | 説明 | 不備がある場合 |
|---|---|---|---|
| `--target <path>` の指す directory | 必須 | 配置先 project root | `status="error"`、`diagnostics=[{reason_code:"target_not_found", ...}]` (不在) / `[{reason_code:"target_not_directory", ...}]` (file)、CLI exit code 1 |

#### オプション

| オプション | 必須 | 既定値 | 意味 | 観測効果 |
|---|---|---|---|---|
| `--target <path>` | 必須 | `.` (カレントディレクトリ) | 配置先 project root | 配置対象 path |
| `--agent <codex\|claude\|both>` | 任意 | `both` | Agent 入口の配置先。`claude` で `.claude/commands/` に command template、`codex` で `.codex/skills/spec-anchor/` に skill | 配置形式 |
| `--dry-run` | 任意 | (未指定) | 配置せず変更予定だけ表示 | `applied=false` / `created` / `updated` / `conflicts` のみ算出 |
| `--force` | 任意 | (未指定) | 既存ファイルの上書きを許可 | conflicts でなく `updated` として処理 |
| `--no-init-core-files` | 任意 | (未指定) | Purpose / Core Concept の雛形を作成しない | `protected[]` に雛形が入らない |

#### 出力

| field | 型 | 必須 | 意味 |
|---|---|---|---|
| `status` | string | 必須 | `ok` / `conflict` / `error` / `failed` |
| `exit_code` | int | 必須 | 0 / 1 |
| `target` | string | 必須 | 配置先 path |
| `applied` | bool | 必須 | 実際に変更を適用したか |
| `created[]` | list[string] | 必須 | 新規作成された path |
| `updated[]` | list[string] | 必須 | 既存と内容が異なり、`--force` で上書きした path |
| `skipped[]` | list[string] | 必須 | 既存ファイルと内容が一致したため変更しなかった path のリスト |
| `protected[]` | list[string] | 必須 | `--force` の有無に関わらず保護される path (Purpose / Core Concept ファイルなど) |
| `conflicts[]` | list[object] | 必須 | 衝突した path のリスト。各 object に `path` / `reason` (`would_overwrite_existing_file` / `destination_exists_and_is_not_file` / `existing_file_is_not_utf8_text`) / `diff` (reason が `would_overwrite_existing_file` のときのみ unified diff) |
| `diagnostics[]` | list[object] | 必須 | reason_code / message / severity |

#### 作成・更新される artifact

| path | 作成条件 | 更新条件 | 更新しない条件 |
|---|---|---|---|
| `<target>/.spec-anchor/config.toml` | 不在時に常時 | `--force` 指定時のみ更新 | 既存で `--force` なしの場合 conflict として扱う |
| `<target>/.spec-anchor/.gitignore` | 不在時に常時 | `--force` 指定時のみ更新 | 同上 |
| `<target>/<purpose_file 既定>` (例: `docs/core/purpose.md`) | `--no-init-core-files` なしで不在時 | (上書きしない) | 既存ファイルは `--force` 指定時も保護される (`protected[]`) |
| `<target>/<concept_file 既定>` (例: `docs/core/concept.md`) | 同上 | 同上 | 同上 |
| `<target>/.claude/commands/spec-core.md` / `spec-inject.md` / `spec-realign.md` | `--agent` が `claude` または `both` のときに不在時 | `--force` 指定時のみ更新 | 既存で `--force` なしの場合 conflict |
| `<target>/.codex/skills/spec-anchor/SKILL.md` | `--agent` が `codex` または `both` のときに不在時 | 同上 | 同上 |

#### 正常終了

- CLI exit code: 0 (`status="ok"`)
- `applied=true`、`created[]` / `updated[]` / `protected[]` に作業結果

#### 停止 / 失敗

| 発火条件 | reason / status | 表示内容 | CLI exit code | 利用者の次アクション |
|---|---|---|---|---|
| `--target` 不在 | `status="error"`、`diagnostics=[{reason_code:"target_not_found", message:"target does not exist; create it explicitly before running setup", severity:"error"}]` | 不在 path | 1 | directory を作る |
| `--target` が directory でない | `status="error"`、`diagnostics=[{reason_code:"target_not_directory", message:"target is not a directory", severity:"error"}]` | path | 1 | 別 path を指定 |
| 既存ファイル衝突 (`--force` なし) | `status="conflict"`、`applied=false`、`conflicts[]` に各 path | 衝突 path と差分 | 1 | 内容確認後 `--force` で再実行 or `--dry-run` で事前確認 |

#### 副作用として行わないこと

- Purpose / Core Concept ファイルの中身を書かない (雛形のみ作成、`--force` でも保護)
- `/spec-core` を自動実行しない (配置後の状態で `.spec-anchor/state/` / `.spec-anchor/context/` に保持物が生成されていない)
- 親ディレクトリを自動作成しない (`--target` は既存である必要がある)
- Agent CLI の認証情報やセッション状態を変更しない

`--agent` に `codex` / `claude` / `both` 以外の値を指定した場合: argparse が stderr に usage を出力して exit code 2 で終了する (stdout JSON は出ない)。

2 回目の実行 (既に全 artifact が配置済み): `status="ok"` / `created=[]` / `updated=[]` / `skipped=[全既存 path]` / `conflicts=[]`。冪等である。

### 10.2 Agent slash command / skill 契約

該当なし。

### 10.3 `--dry-run` の挙動

`--dry-run` の `conflicts[]` 構造は通常実行と同一である。`conflicts` がある場合は `status="conflict"` で返し (dry-run 判定に到達しない)、`conflicts` がない場合のみ `status="dry_run"` / `applied=false` で返す。

## 11. Conflict Review Item の外部仕様

### 11.1 配置と更新主体

`.spec-anchor/context/conflict_review_items.json` に格納される (git 追跡対象)。

- 候補生成: `/spec-core` (LLM が利用者プロジェクトの Source Specs / Purpose / Core Concept から検出)
- 最終判断: 人間 (`spec-anchor core --decision-json '<json>'` または `--decision-file <path>` 経由)

Conflict 判定は全 Section pair の総当たりではない。`relation_hint = conflicts_with` 相当の高リスク候補、および同一識別子・衝突しやすい語 (`must` / `must not` / `禁止` / `必須` / `任意` 等) を共有する pair が、`conflict_pair_max_per_section` (§4) の範囲で判定 stage に送られる。上限により送られなかった pair は CoreResult の `diagnostics` に残る。

### 11.2 status 値とその遷移

| status | 意味 | 遷移元 | 遷移先 |
|---|---|---|---|
| `pending` | LLM が解決できず人間判断待ち | (新規) | `resolved` / `dismissed` (`--decision-*` 経由)、`pending` のまま (`defer` / `needs_source_update`) |
| `resolved` | 人間判断で解決済み | `pending` | (なし。status は `resolved` のまま。base source の hash 変化時は `stale_resolution` flag が true になる。§11.6 参照) |
| `dismissed` | 矛盾ではないとして取り下げ | `pending` | (なし、最終状態) |

未判断 (`pending`) の Conflict Review Item があると、§12 freshness gate で `/spec-inject` / `/spec-realign` が停止する。`stale_resolution: true` の item は blocking しない (制約根拠として使わないだけで、後続コマンドの実行を止めない)。

### 11.3 decision payload の構造

`spec-anchor core --decision-json '<json>'` または `--decision-file <path>` で渡す JSON object。

| field | 必須 | 意味 |
|---|---|---|
| `conflict_id` | 必須 | 対象 Conflict Review Item の id |
| `decision` | 必須 | 下記 enum 値のいずれか |
| `reason` | 必須 | 人間の判断理由 |
| `selected_option` | 任意 | `decision_options[]` の中で選んだ option id |
| `valid_scope` | 任意 | `"global"` (既定) または `"task_scope"` |
| `referenced_source_refs[]` | 任意 | 判断時に参照した source ref のリスト |

### 11.4 decision 値の意味と結果

| decision | 意味 | 結果の status |
|---|---|---|
| `prefer_a` | conflict 片方 A を優先 | `resolved` |
| `prefer_b` | conflict 片方 B を優先 | `resolved` |
| `conditional` | 条件分岐により両方を扱う | `resolved` |
| `dismiss` | 矛盾ではないとして取り下げ | `dismissed` |
| `needs_source_update` | Source Specs / Purpose / Core Concept の修正が必要 | `pending` のまま |
| `defer` | 今回は判断保留 | `pending` のまま |
| `task_scope_resolution` | 今回の課題内だけの一時判断 | `resolved` + `valid_scope="task_scope"` |

### 11.5 Conflict Review Item の object 構造

各 item は次の field を持つ。

| field | 必須 | 意味 |
|---|---|---|
| `conflict_id` | 必須 | 一意な id |
| `status` | 必須 | §11.2 の enum |
| `severity` | 必須 | LLM 生成の severity ラベル (自由文字列、既定 `"medium"`)。バリデーションなし |
| `source_refs[]` | 必須 | 矛盾している箇所の出典 (source_document_id / source_section_id / source span) |
| `claims[]` | 必須 | それぞれの主張の要約 |
| `why_conflicting` | 必須 | 矛盾していると判断した理由 |
| `why_llm_cannot_decide` | 必須 | LLM が自力で解決できない理由 |
| `related_sections[]` | 必須 | 関連する Section の id リスト |
| `decision_options[]` | 必須 | 利用者が選べる判断肢の list。各 option に `id` / `label`。常に全 7 decision enum 値 (`prefer_a` / `prefer_b` / `conditional` / `dismiss` / `needs_source_update` / `defer` / `task_scope_resolution`) を含む。LLM が label をカスタマイズする場合がある |
| `recommended_next_action` | 必須 | 次に取るべき行動の推奨 (既定 `"Ask a human to decide this conflict."`) |
| `base_source_hashes[]` | 必須 | resolution の基準となる source の hash 配列 |
| `valid_scope` | 必須 | `"global"` / `"task_scope"` |
| `stale_resolution` | 必須 | boolean。resolved item の base source hash が変化した場合 `true` (§11.6) |
| `created_at` | 必須 | ISO 8601 UTC 形式 (例: `2026-05-22T03:00:00Z`)。item 作成時刻 |
| `updated_at` | 必須 | ISO 8601 UTC 形式。decision 適用時を含む最終更新時刻 |
| `resolution` | resolved / dismissed 時必須 | `decision` / `reason` / `selected_option` / `valid_scope` / `referenced_source_refs[]` |

### 11.6 stale_resolution flag の発火条件

resolved Conflict Review Item は `base_source_hashes[]` を持つ。対象 source (Source Specs / Purpose / Core Concept) の hash が変化すると `stale_resolution` flag が `true` になる (status は `"resolved"` のまま変わらない)。`stale_resolution: true` の Conflict Review Item は `/spec-inject` / `/spec-realign` で制約根拠として使われない。

### 11.7 副作用として行わないこと

- 人間判断を経由せず status を `resolved` に変えない
- 判断結果を Purpose / Core Concept / Source Specs に自動反映しない (反映は人間が直接編集する)
- `task_scope_resolution` の resolved を後続セッションの恒久根拠として使わない
- `stale_resolution: true` の item を `resolved` 扱いして根拠に使わない


## 12. freshness gate の外部仕様

### 12.1 配置

`.spec-anchor/state/freshness.json` に格納される。`/spec-inject` / `/spec-realign` の各サブコマンドが内部で本 file を読み、停止判定を行う。利用者は通常 file を直接編集せず、`/spec-core` または `spec-anchor-watch` 経由で更新される。

### 12.2 status 値

| status | 意味 | `/spec-inject` / `/spec-realign` の挙動 |
|---|---|---|
| `fresh` | すべての必須 artifact が最新で利用可能 | 続行 |
| `degraded` | 任意 artifact が欠けるが必須は揃う | warning 付きで続行 |
| `blocked` | 何らかの理由で停止すべき (下記 blocking_reasons を伴う) | 停止 (`should_stop=true`) |
| `failed` | 直前 `/spec-core` で必須 artifact が `failed_required_artifact` | 停止 (`should_stop=true`) |

### 12.3 blocking_reasons の enum 値

複数同時に積まれることがある。

| reason | 意味 | recommended_next_action |
|---|---|---|
| `dirty_or_stale_source` | Source Specs が変更されたが `/spec-core` で未反映 | `run /spec-core before /spec-inject` / `before /spec-realign` |
| `stale_config_or_schema` | 設定 / schema が変更されて全章再評価が必要 | `run /spec-core --all before /spec-inject` / `before /spec-realign` |
| `watcher_running` | `spec-anchor-watch` が更新サイクル中 | `wait for watcher completion before /spec-inject` / `before /spec-realign` |
| `watcher_queue_pending` | watcher の未処理キューに変更が残存 | 同上 |
| `pending_conflict` | 未判断の Conflict Review Item あり | `resolve pending Conflict Review Items` |
| `failed_required_artifact` | 直前 `/spec-core` で必須 artifact 生成失敗 | `run /spec-core or /spec-core --all before /spec-inject` / `before /spec-realign` |
| `degraded_optional_artifact` | 任意 artifact の一部が失敗 (`status="degraded"` 時)。**blocking しない** — gate は `can_continue=true` / `continues_with_warnings=true` で続行を許可する | `continue /spec-inject with warnings` / `continue /spec-realign with warnings` |

### 12.4 freshness_report オブジェクト構造

`/spec-core` / `/spec-inject` / `/spec-realign` の stdout JSON に含まれる。

| field | 必須 | 意味 |
|---|---|---|
| `freshness_report.status` | 必須 | §12.2 の enum |
| `freshness_report.blocking_reasons[]` | 必須 | §12.3 の enum (複数可) |
| `freshness_report.warnings[]` | 必須 | warning 文字列または object |
| `freshness_report.counts` | 任意 | 診断用。reason ごとの件数 (`required_artifact_problem_count` / `degraded_optional_artifact_count` / `pending_conflict_count` / `watcher_queue_count`) |
| `freshness_report.diagnostics` | 任意 | 診断用。reason ごとの詳細。`failed_required_artifacts[]` / `missing_required_artifacts[]` / `degraded_optional_artifacts[]`。内部 field の追加・改名は本書中で影響範囲を明示する |

#### `recommended_next_action` の決定規則

複数の blocking_reasons が同時に積まれた場合、`recommended_next_action` は以下の priority 順で最初に一致した reason に対応する文言を返す (複数の reason の文言を結合しない)。

1. `dirty_or_stale_source` → `"run /spec-core before {command}"`
2. `watcher_running` / `watcher_queue_pending` → `"wait for watcher completion before {command}"`
3. `stale_config_or_schema` → `"run /spec-core --all before {command}"`
4. `failed_required_artifact` → `"run /spec-core or /spec-core --all before {command}"`
5. `pending_conflict` → `"resolve pending Conflict Review Items"`
6. (それ以外) → `"stop before {command}"`

### 12.5 副作用として行わないこと

- `/spec-inject` / `/spec-realign` の各サブコマンドは、停止状態でも `/spec-core` を自動実行しない (人間または `spec-anchor-watch` が制御)
- freshness gate は Conflict Review Item の status を変更しない
- Source Specs / Purpose / Core Concept を書き換えない


## 13. エラー仕様

### 13.1 レイヤー分離

SPEC-anchor は 2 レイヤー構造を持つ (§3 / §6.2 / §7.2)。エラー仕様もレイヤーごとに分かれる。

- **shell CLI レイヤー**: 利用者または Agent CLI が `spec-anchor` 系コマンドを子プロセスとして実行したときの stdout JSON / CLI exit code
- **Agent slash command / skill レイヤー**: 利用者が Claude Code / Codex で slash command / skill を発火し、Agent CLI が内部で shell CLI を呼び、その JSON を解釈して利用者へ整形伝達するときの最終文言と構造

各コマンド章 (§5〜§10) の「停止 / 失敗」表が shell CLI 層、「Agent が停止時に利用者へ提示する内容」表が slash command 層の契約を定義する。

### 13.2 主要 artifact JSON の参照可能 field

#### `.spec-anchor/context/chapter_anchors.json`

配置は §5.1。Agent / 利用者が `Read` で参照する。

各 chapter entry の構造:

| field | 必須 | 意味 |
|---|---|---|
| `chapter_id` | 必須 | 章 id (Markdown 最上位見出し由来) |
| `summary` | 必須 | 章全体の抽象化された要約 |
| `key_topics[]` | 必須 | 章の重要テーマ |
| `important_sections[]` | 必須 | 章内で判断軸となる主要 Section の `section_id` 群 |
| `notes[]` | 必須 | 章全体で守るべき読み方 |
| `source_section_ids[]` | 必須 | 章配下の全 `section_id` |

#### `.spec-anchor/context/conflict_review_items.json`

§11.5 の object 構造に従う。

### 13.3 全コマンド共通の失敗時挙動

`status="failed"` を返す失敗はすべて、stdout JSON 内の `freshness_report.blocking_reasons` に `failed_required_artifact` が積まれ、`freshness_report.status="failed"` になる。これにより後続 `/spec-inject` / `/spec-realign` が §12 freshness gate で停止する。`/spec-core` 自身は新しい canonical artifact を上書きせず、前回値を残す。

### 13.4 reason_code の一覧

本書中の各章で出現する reason_code 値を集約する。

| reason_code | 出現コマンド | 意味 |
|---|---|---|
| `config_error` | `core` / `inject-*` / `realign` / `watch` | 設定 / 必須ファイル不在等 |
| `chapter_anchors_llm_failure` | `core` | 章単位の要点生成失敗 |
| `retrieval_index_failed` | `core` | 検索基盤 upsert / verify 失敗 |
| `retrieval_backend_init_failed` | `core` | Qdrant 期待設定で初期化失敗 |
| `target_not_found` | `setup-project` | `--target` 不在 |
| `target_not_directory` | `setup-project` | `--target` が directory でない |
| `would_overwrite_existing_file` | `setup-project` | 既存ファイル衝突 |
| `destination_exists_and_is_not_file` | `setup-project` | 配置先が file 以外 |
| `existing_file_is_not_utf8_text` | `setup-project` | 既存ファイルが UTF-8 でない |
| `qdrant_service_unavailable` | `setup-system` | 検索基盤サービス未到達 |
| `flagembedding_package_unavailable` | `setup-system` | FlagEmbedding 未導入 |
| `qdrant_client_package_unavailable` | `setup-system` | qdrant-client 未導入 |
| `agent_cli_codex_unavailable` | `setup-system` | codex CLI 未導入 |
| `agent_cli_claude_unavailable` | `setup-system` | claude CLI 未導入 |
| `console_script_<name>_unavailable` | `setup-system` | console script 未導入 (`<name>` は script 名) |
| `empty_query` | `inject-search` | 検索クエリが空 |
| `retriever_unavailable` | `inject-search` | retriever (FlagEmbedding / qdrant) の import 失敗 |
| `retriever_init_failed` | `inject-search` | retriever 初期化失敗 |
| `retrieval_failed` | `inject-search` | 検索実行時のエラー |
| `qdrant_unavailable` | `inject-*` | Qdrant サービスに接続できない |
| `qdrant_lookup_failed` | `inject-*` | Qdrant lookup 実行時のエラー |
| `chapter_anchors_missing` | `inject-chapters` | chapter_anchors.json が未生成 |
| `concept_file_unset` / `concept_file_missing` | `inject-purpose` | Core Concept file の設定漏れ / ファイル不在 |
| `stale_resolution` | `inject-conflicts` | resolved Conflict Review Item の base source hash が変化 |
| `provider_exception` | `core` (LLM 呼び出し) | LLM 子プロセスの起動失敗 (command 不在等)。診断用 |
| `provider_error` | `core` (LLM 呼び出し) | LLM 子プロセスが非 0 exit code で終了。診断用 |
| `timeout` | `core` (LLM 呼び出し) | LLM 子プロセスが timeout_sec 超過。診断用 |
| `validation_error` | `core` (LLM 呼び出し) | LLM 出力が期待構造に合致しない。診断用 |
| `human_owned_core_file_protected` | `setup-project` | 人間管理ファイル (Purpose / Core Concept) が既存で保護された |
| `core_files_not_initialized` | `setup-project` | `--no-init-core-files` で初期化を省略した |
| `invalid_mode` | `setup-system` | 不正な mode 値 |
| `set_payload_failed` | `core` (retrieval) | 検索基盤の payload 更新失敗。診断用 |

### 13.5 `error.code` の enum

`error.code` は `"command_error"` の 1 値のみ。全コマンド共通で、設定不在・例外発生・入力バリデーション失敗時に使われる。

### 13.6 diagnostics の `severity` enum

diagnostics 内の `severity` は次の 3 値:

| severity | 意味 |
|---|---|
| `"error"` | 当該項目が失敗した (blocking) |
| `"warning"` | 問題があるが続行可能 |
| `"info"` | 情報提供のみ (問題なし) |

## 14. 互換性方針と非保証事項

### 14.1 互換性方針

本書に定義されたコマンド、オプション、設定キー、出力 field、status 値、reason code、artifact path、識別子形式は外部契約である。これらを削除、改名、型変更、意味変更する場合は breaking change として扱う。変更時は移行手順を提供する。

ただし、各項目の説明欄で次のいずれかが明記されたものはこの限りではない。

- 「診断用」: 失敗原因の特定や運用状態の把握のために提供する情報。内部 field 構造の追加・改名は本書中で影響範囲を明示するが、互換性保証の対象外とする
- 「debug 用」: 開発・問題切り分けのために提供する debug 出力。内容・出力先・存在自体が将来変更されうる
- 「互換性保証対象外」: 現時点で外部観測できるが、互換性を維持しない明示宣言を本書中に持つ項目
- 「内部状態」: ファイル位置を設定キーで指定できるが、内部 field 構造は利用者の参照対象ではない (利用者が読まない artifact)

### 14.2 SPEC-anchor が保証しないこと

- LLM が提示する制約と回答案が常に正しいこと (利用者の確認が必要)
- 仕様変更後に Purpose と Core Concept が陳腐化していないかの自動検出 (人間判断による)
- 自動検出される仕様矛盾の網羅性 (検出されない矛盾が残る可能性がある)
- 検索キーと要約だけで関係する Section を全件発見すること (補助情報であり、根拠ではない)
- 同じ仕様情報に対する Claude Code と Codex の解釈・回答内容の完全一致 (保持物と CLI 契約は同じだが、LLM ごとの解釈差は保証しない)
- `[watcher].enabled=true` でも、長時間運用時の watcher の永続稼働 (停止からの自動復旧などは外部仕様の対象外)
