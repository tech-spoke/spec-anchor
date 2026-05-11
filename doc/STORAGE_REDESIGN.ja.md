# Storage Redesign Working Note

このドキュメントは、SPEC-grag のデータ保管場所（vector DB / JSON）を再設計するための検討メモである。最終的な決定は `doc/EXTERNAL_DESIGN.ja.md` および `doc/DESIGN.ja.md` に反映し、本ドキュメントは設計判断のたたき台として扱う。

## 0. 確定した方針 (案 C-1)

**Qdrant `spec_grag_section` (section-level) のみを正本にし、chunk-level collection は削除。JSON は人間判断 / 軽量 tracking / 状態のみ。**

設計意図:

- 1 section = 1 vector の section-level retrieval を唯一の経路にする
- section embedding text は短い (~700 文字: heading + summary + search_keys + identifiers の連結) ため、section 本文全体を直接 embed しない
- 本文を vector で代理表現する仕組みとして **search_keys (自然言語) + identifiers (コードシンボル)** を section 単位で持つ
  - search_keys → dense embedding で概念類似を補強 (本文には書かれているが summary にない概念句を救う)
  - identifiers → sparse (BGE-M3 lexical) で symbol 完全一致を補強 (本文に出てくる API 名 / CLI / 定数を symbol レベルで lookup できる)
- chunk-level collection は当初から不要。search_keys + identifiers がその代替

⚠️ **役割分離の対処状況 (Phase R-0)**

`search_keys` の役割分離 (§1.0、自然言語のみ、identifiers と非重複) は Phase R-0 で実装側を整備済み。具体的には:

- LLM プロンプトに `_SEARCH_KEYS_INSTRUCTIONS` を埋め込み、`search_keys` に code symbol / API 名 / CLI command / option / file path / ALL_CAPS / PascalCase / dotted name を入れない指示を明記 (spec_grag/section_metadata.py:105 と spec_grag/section_metadata.py:999 で `_batch_prompt_payload` の `instructions` フィールドに注入)
- post-process filter `_is_identifier_like_search_key` で LLM が出した identifier 風 token を drop し、`keys.extend(identifiers)` 由来の自動混入も撤去 (spec_grag/section_metadata.py:93 で regex 集合定義、spec_grag/section_metadata.py:120 で判定関数、spec_grag/section_metadata.py:1147 の `_search_keys` で適用)
- `SECTION_METADATA_PROMPT_VERSION` を `section-metadata-v2` に bump し、cache key 経由で旧 v1 cache を invalidate (spec_grag/section_metadata.py:37、cache key payload は spec_grag/section_metadata.py:579)
- unit test で disjoint 性を保証 (tests/test_section_metadata_generation.py::test_search_keys_and_identifiers_are_disjoint ほか)

実 codex / claude provider で `spec-grag core --all` を回した実測値での重複率低下確認は未実施。Phase R-2 以降に進む前に運用環境で 1 回実行して効果検証する必要がある。これを怠ると section-level 単独運用に切り替えた時点で検索品質劣化が残る可能性がある。

廃止対象:

- `section_metadata.json` ⛔ **完全廃止確定** (§1.3, §4)
- `source_chunks.json` ⛔ **完全廃止確定** (§1.4, §4)
- Qdrant `spec_grag_source` (chunk-level collection) ⛔ **完全廃止確定** (§1.1, §4)

集約先:

- section コンテンツ (summary / search_keys / identifiers / related_sections / heading_path) は Qdrant `spec_grag_section` payload に集約
- 監査ログは `section_manifest.json` 拡張側に移動

存続して改修対象とする artifact:

- `chapter_anchors.json`: 設計意図 (DESIGN.ja.md §6) の「章単位の judgment 軸 / key_topics / important_sections」を LLM 生成で実装する。現在の機械集約は機能不全のため改修。`/spec-inject` の §5 path ② で利用する

`/spec-inject` で Agent が制約を組み立てる際の探索パスは §5 (4 path: section retrieval + chapter anchor + Purpose/Core Concept + Conflict Review Items) で確定。CLAUDE.md ルール 4 の `evidence_origin` enum をすべてカバーする構造。

段階的 refactor は §7.4 の Phase R-0 〜 R-7 を参照。決定の詳細根拠は §4 / §5 を、未確定の細部は §7 TODO を参照。

## 1. 現状の保管場所と中身

### 1.0 役割が混同されやすい field の定義 (drift 防止)

`search_keys` と `identifiers` は実装が両方 `section` の payload / metadata に並ぶため、過去に LLM プロンプト不徹底で内容が大幅重複した経緯がある。本ドキュメントでは以下の役割分離を明示し、設計書 / プロンプト / test もこの定義に揃える。

| field | 役割 | 入力する内容 | 入れない内容 | 例 |
|---|---|---|---|---|
| `search_keys` | **自然言語**で検索したい時のキーワード。概念句、検索意図表現、章のテーマ語 | 概念名、ドメイン用語、章テーマ、自然言語句 | コードシンボル、API 名、CLI コマンド、ファイルパス | `"配置操作"`, `"context registration"`, `"再登録の挙動"`, `"freshness gate"` |
| `identifiers` | **コードシンボル / 固有技術名**。機械抽出で再現性を担保 | API 名、関数名、CLI コマンド、CLI option、ファイルパス、ALL_CAPS 定数、PascalCase 型名、ドット区切り技術名 | 自然言語句、概念名、章タイトル、要約文 | `"bindContext"`, `"removeBindContext"`, `"productStoreGroup.replace"`, `"--rebuild"` |

実装上の振り分け原則:

- `search_keys` は LLM が `section_metadata` 生成時に出力する。プロンプトで「コードシンボル / API 名 / CLI コマンドは search_keys に入れない (identifiers が拾うため)」を明記する
- `identifiers` は `extract_identifiers` が正規表現で section 本文から機械抽出する。LLM 判断は経由しない

両者の内容が重複しないよう、`section_metadata` 生成時に post-process で `search_keys` 中の identifier 風トークンを drop する保険も入れる。詳細は本ドキュメント §6 の TODO で追跡。

### 1.1 Qdrant `spec_grag_source` (chunk-level collection) ⛔ 廃止

案 C-1 で完全廃止 (§0 / §4 参照)。引継ぎ先: chunk 本文の閲覧は Source Specs ファイル直読み (Agent の Read tool)、または `inject-section <id>` 経由で section 単位コンテンツを取得する。schema 詳細は本ドキュメントで管理しない。

### 1.2 Qdrant `spec_grag_section` (section-level collection)

1 section = 1 vector。section 単位の事前計算メタデータと、その連結テキストを embed したもの。**本表は現状 (As-Is) の payload。案 C-1 採用後の最終形は §4.3 を参照。**

| field | 型 | 内容 | 用途 | 状態 |
|---|---|---|---|---|
| `source_document_id` | str | ファイルパス | section が属する file | 現状有 |
| `source_section_id` | str | section ID | 一次 key | 現状有 |
| `stable_section_uid` | str | section 安定 UID | Qdrant point id 計算の入力 | 現状有 |
| `stable_chunk_uid` | str | section UID と同じ値 | 互換用 | 現状有 |
| `heading_path` | list[str] | 見出し階層 | 表示補助 | 現状有 |
| `source_hash` | str | section 全体の hash | invalidation 判定 | 現状有 |
| `semantic_hash` | str | semantic hash | 拡張用 | 現状有 |
| `summary` | str | LLM 生成の section 1 段落要約 (~480 文字) | retrieval 結果に含めて Agent が読み下す | 現状有 |
| `search_keys` | list[str] | **自然言語**の検索キーワード (LLM 生成、§1.0 参照) | 概念句での dense 検索の補助、Related Sections の `search_key_match` channel | 現状有 ⚠️ **品質劣化**: LLM プロンプトに role 制約がなく、コードシンボル / API 名が大量に混入 (実測で identifiers と 90% 重複)。§1.0 の自然言語限定が守られていない。修正は §6.2 TODO で追跡 |
| `identifiers` | list[str] | **コードシンボル / 固有技術名** (正規表現で機械抽出、§1.0 参照) | sparse 検索の identifier 完全一致、Related Sections の `shared_identifier` channel | 現状有 ⚠️ **search_keys 側との重複**: identifiers の内容自体は機械抽出で意図通りだが、search_keys 側にコードシンボルが混入しているため独立した役割を果たせていない (両方に同 symbol が出る)。前提となる search_keys 側の修正が完了するまで、本 field の検索貢献は縮退中 |
| `text` | str | `heading + summary + search_keys + identifiers` の連結 (~700 文字) | embedding 入力テキスト | 現状有 (廃止候補、§6.3) |
| `related_sections` | list[obj] | typed graph 出向き edge (target_section_id, relation_hint, confidence, reason, evidence_terms, channels, possible_conflict) | `inject-search` の戻り値に同梱して graph traversal を 1 call で完結 | **未実装 (案 C-1 Phase R-3 で追加)** |
| (vector) | dense + sparse | BGE-M3 で `text` を embed | section 単位の類似度検索 | 現状有 |

### 1.3 JSON: `.spec-grag/context/section_metadata.json` ⛔ 廃止

**ステータス: 案 C-1 で完全廃止確定 (本ドキュメント §4.3 参照)**

中身の field 一覧は本ドキュメントでは管理しない。引継ぎ先は次の通り:

- section コンテンツ (`summary`, `search_keys`, `identifiers`, `related_sections`, `heading_path` 等) → Qdrant `spec_grag_section` payload (§4.3)
- 監査ログ (`llm_provider`, `llm_generation_status`, `generated_at`, `last_prompt_version`) → `section_manifest.json` 拡張 (§4.3)
- LLM cache (`prompt_version`, `metadata_version` を含む key) → `state/cache/section_metadata/*.json` (既存、変更なし)

廃止前の schema 詳細は git history (`git show HEAD~ -- doc/STORAGE_REDESIGN.ja.md`) で参照可能。新規参照禁止。

### 1.4 JSON: `.spec-grag/context/source_chunks.json` ⛔ 廃止

**ステータス: 案 C-1 で完全廃止確定 (本ドキュメント §4.3 参照)**

引継ぎ先: chunk 本文 + メタデータは Qdrant `spec_grag_source` payload (§1.1) に集約。本ドキュメントでは schema を管理しない。

### 1.5 JSON: その他

| ファイル | 内容 | Qdrant 関連性 |
|---|---|---|
| `chapter_anchors.json` | chapter 単位の anchor section_id 群 | 無関連 (純粋な状態 artifact) |
| `conflict_review_items.json` | Conflict Review Items (人間判断) | 無関連 (人間判断 artifact、git で追う必要あり) |
| `freshness.json` | blocking_reasons / counts / status | 無関連 (実行状態) |
| `retrieval_index_revision.json` | Qdrant index 状態 + 設定 | Qdrant 状態の鏡 |
| `section_manifest.json` | section_id / source_hash の軽量 tracking | 無関連 (差分検出用) |
| `state/core_progress.json` | 実行進捗ログ | 無関連 |
| `state/cache/related_typing_cache.json` | LLM pair typing 結果 cache | 無関連 (LLM 判定の re-roll 抑止) |
| `state/cache/section_metadata/*.json` | section 単位 LLM 出力 cache | 無関連 (同上) |

## 2. 重複の整理

### 2.1 二重保管されているデータ

| データ | 場所 1 | 場所 2 | drift リスク |
|---|---|---|---|
| `summary` | section_metadata.json | spec_grag_section payload | 中: LLM 再生成時に片方更新失敗で乖離 |
| `search_keys` | section_metadata.json | spec_grag_section payload | 同上 |
| `identifiers` | section_metadata.json | spec_grag_section payload | 同上 |
| chunk text | source_chunks.json | spec_grag_source payload | 低: 機械生成なので drift しにくいが double write |
| `heading_path` | section_metadata.json + section_manifest.json | spec_grag_section + spec_grag_source payload | 低 |
| `source_hash` | 複数 JSON | 両 Qdrant payload | 低 |

### 2.2 ベクター DB にしか無いデータ

無し。すべての payload field は JSON にも存在する（heading_level を除く）。

### 2.3 JSON にしか無いデータ

| データ | ファイル | Qdrant に持つべきか |
|---|---|---|
| `related_sections` (typed graph) | section_metadata.json | **持つべき**: section vector の payload として持てば 1 call で graph 取得可能。vector の検索対象ではなく payload data として扱う |
| `heading_level` | section_metadata.json | 不要: `heading_path` の長さから推定可能、UI 用なら派生で済む。**注**: `heading_path` (list[str]) は既に両 Qdrant collection の payload に有るので別物 |
| LLM 生成メタ (`prompt_version`, `metadata_version`, `llm_generation_status`, `llm_provider`, `generated_at`) | section_metadata.json | **基本的に不要**: cache key 計算と監査用。検索結果に同梱する必要なし。`section_manifest.json` 等の軽量 tracking に分離するのが筋 |
| `chapter_anchors` | chapter_anchors.json | section_id 参照のみ、vector DB 化不要 |
| `conflict_review_items` | conflict_review_items.json | 人間判断 artifact、git 必須 |
| 実行状態 / cache | state/ 配下 | vector DB 化不要 |

## 3. 「ベクター DB に格納すべきもの」の判断基準

### 3.1 vector DB の本来の役割

- **embedding 検索 (dense + sparse) の入力**になる
- **検索結果として返される際に必要な最小情報**を payload で運ぶ
- spec-grag では **section-level retrieval を唯一の経路**とする (chunk-level は削除)。section embedding text は短いので、本文の searchable surface は search_keys + identifiers が section 単位で代理表現する

### 3.2 vector DB に置くべきもの

- 検索の query にも結果にもなるテキスト（chunk 本文、または section の連結テキスト）
- 検索結果から「どの section / chunk か」を一意に特定する key (`source_section_id`, `stable_chunk_uid`)
- 検索結果を Agent が「読み下せる」最小ペイロード (summary 程度。本文全文は別 lookup でも可)

### 3.3 vector DB に置くべきでないもの

- 人間判断 artifact（git diff で追跡したい、削除に承認が必要）
- 実行状態 / cache（rebuild すれば作り直せる）
- cache 制御 metadata (`prompt_version`, `metadata_version`)：cache key 計算時に動的に作る。永続化は cache file 内のみで十分
- 監査メタデータ (`llm_provider`, `llm_generation_status`, `generated_at`)：検索結果に同梱しない。`section_manifest.json` 等の tracking artifact に分離

**注**: typed graph (`related_sections`) は §2.3 で「Qdrant に持つべき」と確定した。vector の検索対象 (`vector` field) にするのではなく、section vector に紐づく **payload data** として持つ。この区別を混同しない。

## 4. 再設計の最終形 (案 C-1)

データの種類で保管先を決める。Qdrant `spec_grag_section` を唯一の vector DB として、コンテンツの正本にする。chunk-level collection は廃止。JSON は人間判断 artifact と軽量 tracking のみに残す。

| データ種別 | 保管先 | 理由 |
|---|---|---|
| section の embedding | Qdrant `spec_grag_section` (vector) | vector DB 本来の役割 |
| section コンテンツ (summary / search_keys / identifiers / heading_path) | Qdrant `spec_grag_section` payload | 検索 1 回で同梱して読み下し可 |
| typed graph (related_sections) | Qdrant `spec_grag_section` payload | section vector と同じ key で同梱 → graph traversal の lookup を 1 step 削減 |
| 検索漏れ対策 (本文 vs section embedding text の語彙ギャップ) | search_keys + identifiers (上記 payload に含む) | 本文を chunk として別 collection に分けるのではなく、本文の概念句 / symbol を section 単位で代理表現することで section-level だけで覆う |
| Source Specs 本文 | ファイル直 (`sources.include` で指定された Markdown) | Agent が Read / Grep tool で必要 snippet を都度取得。Qdrant に格納しない |
| 人間判断 artifact | `conflict_review_items.json` | git 必須、削除に承認が必要 |
| 実行状態 | `freshness.json`, `state/core_progress.json` | rebuild 可能、運用観測用 |
| LLM 判定の re-roll 抑止 | `state/cache/related_typing_cache.json`, `state/cache/section_metadata/*.json` | cache、rebuild 可能 |
| section 単位の軽量 tracking と監査メタ | `section_manifest.json` (拡張) | 差分検出 + 監査 |
| chapter anchor (section_id 参照のみ) | `chapter_anchors.json` | 軽量、Qdrant 化の必要なし |

**Qdrant `spec_grag_section` payload の最終形**

```
source_section_id     ← 一次 key
source_hash           ← invalidation
semantic_hash         ← 拡張用 (現状ほぼ source_hash と同じ、§6 TODO で確認)
heading_path          ← list[str]
summary               ← LLM 生成、自然言語要約
search_keys           ← LLM 生成、自然言語検索キー (§1.0)
identifiers           ← 機械抽出、コードシンボル (§1.0)
related_sections      ← typed graph 出向き edge (target_section_id, relation_hint, confidence, reason, evidence_terms, channels, possible_conflict)
(text)                ← embedding 入力 (デバッグ用、保存しない案も可)
vector                ← BGE-M3 dense + sparse
```

**Qdrant `spec_grag_source` payload の最終形**

⛔ **collection ごと廃止。** chunk-level retrieval は section-level の search_keys + identifiers で代替。本 collection は §6.4 Phase R-5 で `delete_collection` する。

**`section_manifest.json` の最終形 (拡張)**

```
per section:
  source_section_id
  source_hash
  semantic_hash
  heading_path
  heading_level                  ← UI で必要な場合のみ、原則 heading_path から派生
  llm_generation_status          ← success / failed / skipped (失敗 section は Qdrant に index しない)
  llm_provider                   ← 監査用
  generated_at                   ← 監査用
  last_prompt_version            ← cache 整合確認用
```

**廃止する artifact (案 C-1 で確定)**

- Qdrant `spec_grag_source` (chunk-level collection) を **完全廃止**
  - chunk-level retrieval 自体が不要 (search_keys + identifiers が代替)
  - core 経路から chunk 関連の upsert / build を全て撤去 (Phase R-5)
- `section_metadata.json` を **完全廃止**
  - section コンテンツ (summary, search_keys, identifiers, related_sections) は Qdrant `spec_grag_section` payload へ
  - LLM cache は既存の `state/cache/section_metadata/*.json` (hash key 付き個別 file) で完結 (section_metadata.json は cache に関与していない)
  - 監査ログ (provider, status, generated_at, prompt_version) は `section_manifest.json` 拡張で吸収
- `source_chunks.json` を **完全廃止**
  - chunk-level collection を廃止するので chunk artifact 自体が不要
  - Source Specs 本文の閲覧は Agent が Markdown ファイルを直読み

**保留する JSON (現状維持)**

- `chapter_anchors.json`（section_id 参照のみ、vector DB 化不要）
- `conflict_review_items.json`（git 必須）
- `freshness.json`（実行状態）
- `retrieval_index_revision.json`（Qdrant 状態の鏡、現状維持）
- `state/` 配下（cache と進捗ログ）

**update タイミングの整合**

- `section_metadata` 生成 stage 完了時: Qdrant `spec_grag_section` の vector + summary / search_keys / identifiers / heading_path を upsert
- `related_sections` LLM typing stage 完了時: Qdrant payload に `related_sections` 配列を **`set_payload` API で追加更新** (vector 再計算不要)
- chunk-level upsert 経路は廃止 (Phase R-5 で `_qdrant_upsert_with_partial_dispatch` 関連を撤去、collection も削除)

**利点**

- 単一 source of truth (コンテンツは Qdrant、人間判断と運用状態は JSON)
- typed graph も section vector と同じ key で同梱されるため `inject-search` 1 call で graph 取得可
- drift 構造的に発生しない (data の二重保管なし)
- LLM 監査メタは tracking 専用 manifest に局所化、検索戻り値を肥大化させない

**欠点**

- refactor 規模は中〜大 (Read 経路 / 書き込み経路 / test fixture)
- Qdrant 障害時はコンテンツ取得不可 (`--rebuild` で LLM 再生成、現状の `--rebuild` と同じセマンティクス)
- git diff で LLM 生成 summary を直接追えない (必要なら audit log を別途出力する仕組みを後付け可能)

## 5. `/spec-inject` の Agent フロー (確定)

`/spec-inject` で Agent が制約を組み立てる際の探索パスは次の 4 経路を組み合わせる。これは案 C-1 で確定した保管場所と直接対応する。

CLAUDE.md ルール 4 が定める `evidence_origin` enum (Purpose / Core Concept / Source Specs / Conflict Review Item) を 4 path がそれぞれカバーする構造。各 path は **必須ではなく許可**で、Agent が課題の性質に応じて使い分ける。

### 5.1 path 一覧

#### ① Qdrant section-level collection 検索

- [a] Agent が会話区間 / 課題プロンプトから検索キーを選定し、hybrid retrieval を呼ぶ (query → Qdrant)
- [b] Qdrant が section_id ranking を返す (top-K、K は config、少し大きめにとる)
- [c] Agent が top-K の payload (heading / summary / search_keys / identifiers) を読み、制約に関連しそうな候補を見つけ、Agentic サーチで本文を確認、制約を抽出
- [d] Agent が related_sections の target_section_id を Qdrant payload lookup (id 指定の point retrieve、vector 検索ではない)、heading / summary / search_keys / identifiers を読む。制約に関係しそうであれば Agentic サーチで本文を確認
  - [d] を再帰的に適用 (最大 N hop、N は config)
  - 制約に関係しないと判断できた時点で打ち切り

evidence_origin: `Source Specs`

#### ② chapter_anchors.json による章単位 Agentic サーチ

- [a] Agent が会話区間 / 課題プロンプトから、`chapter_anchors.json` を Read または Grep し、関係しそうな章を特定 (章単位の judgment 軸 / key_topics で絞り込み)
- [b] 特定された章配下の section を Agentic サーチで読み、制約を抽出

evidence_origin: `Source Specs` (章単位の入口として機能、最終 evidence は章配下の Source Specs)

`chapter_anchors.json` は LLM が章単位で生成した judgment 軸を含む (実装計画は §6.4 Phase R-7)。

#### ③ Purpose / Core Concept からの制約抽出

- [a] Agent が `purpose_file` / `concept_file` を Read で全文読み、会話区間 / 課題プロンプトに照らして該当する制約根拠を抽出

evidence_origin: `Purpose` または `Core Concept`

これらは通常短い文書のため、Grep より全文 Read のほうが安全 (部分マッチで重要文を見逃すリスク回避)。

#### ④ resolved Conflict Review Items の確認

- [a] Agent が `conflict_review_items.json` を読み、`status == "resolved"` かつ stale でない items を抽出
- [b] `valid_scope` (global / task_scope) と `resolution.referenced_source_refs` を確認
- [c] 制約に関係する場合、`evidence_origin = "Conflict Review Item"` として制約に組み込む

evidence_origin: `Conflict Review Item`

### 5.2 path 選択の指針

| 課題タイプ | 主 path | 補強 |
|---|---|---|
| 具体的 API / 識別子 | ① | ③、④ |
| 全体方針 / 抽象的 | ② | ①、③、④ |
| Purpose / Core Concept 直接質問 | ③ | ①、② |
| 過去判断の継続 | ④ | ①、③ |

### 5.3 inject CLI API との対応

| path | CLI API |
|---|---|
| ① hybrid retrieval | `spec-grag inject-search "<query>"` (top-K の section payload を返す) |
| ① related lookup | `spec-grag inject-section "<id>" [<id>...]` (id 指定で section payload を一括 lookup) |
| ② chapter anchor | `spec-grag inject-chapters` (chapter_anchors.json 取得、Agent が Read tool で代替も可) |
| ③ purpose / core concept | `spec-grag inject-purpose` (purpose_file + concept_file 全文) |
| ④ conflict items | `spec-grag inject-conflicts` (resolved + stale でない items) |
| 制約検証 | `spec-grag inject "<task>" --constraints '<JSON>'` |
| gate probe | `spec-grag inject "<task>"` (freshness gate, pending conflict 確認) |

実装は §6.4 Phase R-6 で案 C-1 前提に組む。

## 6. 次のステップ

1. `doc/EXTERNAL_DESIGN.ja.md` と `doc/DESIGN.ja.md` の関連節を案 C-1 + §5 inject フローで改訂（checkbox 化と同時に）
2. §7.2 の役割分離 (search_keys / identifiers) を先行実施 (Phase R-0)
3. 段階的 refactor の Phase 分けを `doc/IMPLEMENTATION_PLAN.ja.md` に追記
4. 各 Phase で test を維持しつつ実施

## 7. TODO

### 7.1 設計判断 (確定)

- [x] 案 C-1 を採用 (Qdrant をコンテンツ正本、`section_metadata.json` 完全廃止、JSON は人間判断 / 軽量 tracking / 状態のみ)
- [ ] `doc/EXTERNAL_DESIGN.ja.md` と `doc/DESIGN.ja.md` の関連節を案 C-1 で改訂
- [ ] 改訂と同時に CLAUDE.md ルール 13 の checkbox 化を実施

### 7.2 役割分離 (search_keys vs identifiers, §1.0)

- [x] §1.0 の役割分離を `spec_grag/section_metadata.py` の LLM プロンプトに反映 (search_keys にコードシンボルを入れさせない、identifiers との重複禁止を明記)
  - 実装: spec_grag/section_metadata.py:105 (`_SEARCH_KEYS_INSTRUCTIONS`)、spec_grag/section_metadata.py:999 (`_batch_prompt_payload` の `instructions` フィールドに注入)
  - 検証: tests/test_section_metadata_generation.py::test_section_metadata_prompt_includes_role_constraint_instructions
- [x] 上記プロンプト改訂後、`section_metadata` cache invalidation のため `prompt_version` を bump
  - 実装: spec_grag/section_metadata.py:37 (`SECTION_METADATA_PROMPT_VERSION = "section-metadata-v2"`)。spec_grag/core.py:378 と spec_grag/core.py:1623 の直書き `"section-metadata-v1"` も `section_metadata_api.SECTION_METADATA_PROMPT_VERSION` 参照に置換
  - 検証: tests/test_section_metadata_generation.py::test_section_metadata_prompt_version_is_v2、`section_metadata_cache_key` (spec_grag/section_metadata.py:563、payload は spec_grag/section_metadata.py:579) の payload に `prompt_version` を含めることで既存 cache を invalidate
- [x] §1.0 の役割分離を `doc/EXTERNAL_DESIGN.ja.md` (Section Search Keys / Identifiers の章) に反映
  - 反映済み: doc/EXTERNAL_DESIGN.ja.md §2.6 (Section Search Keys 含むもの / 含まないもの、line 118-133)、doc/EXTERNAL_DESIGN.ja.md §2.6.1 (Section Identifiers 含むもの / 含まないもの、line 135-151) で「役割重複を防ぐため Section Search Keys には入れない」を明記済み
- [x] post-process フィルタ (`search_keys` から identifier 風トークンを drop) を `section_metadata.py` に追加し、test で重複ゼロを保証 (例: `assert set(search_keys).isdisjoint(set(identifiers))`)
  - 実装: spec_grag/section_metadata.py:93 (`_SEARCH_KEY_IDENTIFIER_REGEXES`)、spec_grag/section_metadata.py:120 (`_is_identifier_like_search_key`)、spec_grag/section_metadata.py:1147 (`_search_keys` で deduped 後に filter 適用、また `keys.extend(identifiers)` の重複混入を撤去)
  - 検証: tests/test_section_metadata_generation.py::test_search_keys_and_identifiers_are_disjoint (`bindContext` / `productStoreGroup.replace` / `--rebuild` / `/spec-core` / `BINDING_KEY` / `PascalName` / `config.toml` を drop し、`context registration` / `freshness gate` を保持することを assert)

### 7.2.2 Phase R-7 実 codex 検証で発見した問題と対処

`spec-grag core --all` を実 codex provider (gpt-5.4-mini, low effort) で再実行 (2026-05-11 04:35 JST 頃) し、生成された `.spec-grag/context/chapter_anchors.json` を確認したところ、`generation.fallback_chapter_ids` に全 4 chapter が含まれ、機械集約 fallback 経路を踏んでいた。

原因: `spec_grag/llm_provider.py:_spec_core_output_schema` が `chapter_key_anchor` stage を未認識で、section_metadata 用の `{summary, search_keys}` 形 schema を codex に渡していた。codex は schema に従い section 形式で出力するため、`spec_grag.chapter_anchors._anchor_from_llm_output` が `summary` を見つけられず (出力に `key_topics` / `important_sections` / `notes` が欠落)、毎 chapter で mechanical fallback に降格していた。

対処:

1. `spec_grag/llm_provider.py` に `_chapter_key_anchor_output_schema` を追加し、`_spec_core_output_schema` の dispatch で `chapter_key_anchor` stage を分岐 (`summary` / `key_topics[]` / `important_sections[]` / `notes[]` を required にした schema を返す)
2. `spec_grag/chapter_anchors.py` の `generate_with_retries` 呼び出しで `required_fields=("summary", "key_topics", "important_sections", "notes")` を明示し、検証エラー時に diagnostic を残すよう変更
3. tests/test_chapter_anchors.py::test_chapter_key_anchor_output_schema_includes_required_fields で schema 内容を assert

修正後 (実 LLM 検証完了): 2026-05-11 04:40 UTC+9 頃に spec-grag リポジトリで `spec-grag core --all` を再実行。`chapter_anchors.json.generation.fallback_chapter_ids` が `[]` になり (4/4 → 0/4)、各 chapter に LLM 生成の自然言語 `summary` (例: 25 章 "This chapter defines the component placement layer for editing slot composition, ..."), 6 件の `key_topics` (例: "component placement editing", "slot-based arrangement changes"), 3 件の substantive `notes` (例: "Treat missing component ids as errors, including remove operations") が入ることを確認。`provider: codex_cli` / `model: gpt-5.4-mini`

### 7.2.3 Phase R-3 follow-up: section collection 初期化の silent failure

同じ実 codex 検証で、`spec_grag_section` Qdrant collection が **そもそも存在していない** (Qdrant /collections に `spec_grag_source` だけがある) ことを発見。`_upsert_section_collection_if_enabled` は `force_full_recreate=False`(`--all` 経路の default) で `client.upsert(spec_grag_section, ...)` を試み、collection 不在で 404 → `except Exception: return` で silent fail していた。`--rebuild` を使った時だけ `recreate=True` で collection が作られていた。

原因: Phase R-3 で `build_section_payloads` に `related_sections` を含める変更を入れたが、上流の「collection の初回生成」 path が `--rebuild` 限定だったため、`--all` だけを回している環境では section collection そのものが空のままだった。R-3 / R-6 の inject CLI は section collection 前提のため、これは末端機能の動作不能を招く。

対処:

1. `spec_grag/core.py` に `_section_collection_exists(url, collection)` helper を追加 (`qdrant_client.QdrantClient.collection_exists`)
2. `_upsert_section_collection_if_enabled` 内で `recreate = bool(force_full_recreate) or not _section_collection_exists(url, section_collection)` に変更し、未存在時は自動 recreate
3. 同 helper の metadata_by_id 構築に `related_sections` を追加 (R-3 と整合)
4. tests/test_chunk_level_disabled.py に `_section_collection_exists` の 3 tests (unreachable / missing / present) を追加

修正後 (実 LLM 検証完了): 2026-05-11 04:40 UTC+9 頃の再 run で `spec_grag_section` collection が `--all` のみで作成 (`curl http://localhost:6333/collections` で確認、collection が事前削除されていた状態から自動 recreate)、50 sections 全てに `related_sections` が payload に書き込まれた (`spec_grag_section` 内 50/50 points が related_sections を保持、合計 328 edges)。section_metadata.json 側も同 50 sections が related_sections を持つ。sample edge: `25_コンポーネント層（配置操作）.md#0001` → `#0002` (`depends_on` / `high` confidence)

### 7.2.1 Phase R-5 実施で発見した問題と対処

実 codex / claude subprocess を立ち上げる smoke test (`tests/test_agent_cli_smoke.py::test_t_a02_real_setup_core_inject_realign_watch_roundtrip_with_agent_entrypoints`) で、tests/conftest.py の `_enable_chunk_level_for_tests` autouse hook が **subprocess に届かない**ため、`spec-grag core --all` 実行後の `client.count(collection)` assertion が `Collection ... doesn't exist` で失敗した。

最初の対処 (Phase R-5 初版): tests/test_agent_cli_smoke.py の `_patch_collection` で生成する config に `[vector_store].chunk_level_enabled = true` を inject する形で test 個別に opt-in。

#### 7.2.1.a Phase R-5 改訂: ランタイムゲート → リテラルコメントアウト

Phase R-5 初版は「`CHUNK_LEVEL_ENABLED: bool = False` 定数 + `_chunk_level_enabled(config)` ゲート + 関数本体は active」というランタイム gate 方式だったが、ユーザーから「**コメントアウトしておく**」(指示時の意図はリテラルコメント化) との指示を再度受けて改訂した。

改訂内容:

- `spec_grag/retrieval_index.py` の chunk-level 5 関数 (`build_source_chunks`, `build_source_chunks_artifact`, `compute_chunk_diff`, `upsert_qdrant_bge_m3_index`, `upsert_qdrant_bge_m3_index_incremental`) を、関数本体を `#` プレフィックスのコメントブロックに置換し、各関数冒頭に `raise NotImplementedError("Phase R-5: ...")` を追加
- `spec_grag/core.py` の `_qdrant_upsert_with_partial_dispatch` / `_build_retrieval_index_revision` を同様にコメントアウト + `raise NotImplementedError`
- `_run_spec_core_unlocked` の chunk-level call site (`if _chunk_level_enabled(config):` 以下) をコメントアウトし、stub artifact (`_chunk_level_disabled_artifact_*`) を直接代入する分岐に置換
- `CHUNK_LEVEL_ENABLED` 定数と `_chunk_level_enabled()` helper を撤去 (gate が NotImplementedError しか守らないため、残すと誤読を招く)
- `tests/conftest.py` の `_enable_chunk_level_for_tests` autouse hook を削除
- `tests/test_agent_cli_smoke.py` の `chunk_level_enabled = true` injection を削除し、test 自体を `@pytest.mark.skip` (`Phase R-5 dormant: assertion targets the chunk-level spec_grag_source collection`) に変更
- `tests/test_retrieval_index.py::test_compute_chunk_diff_*` を `@pytest.mark.skip`
- `tests/test_spec_core.py::test_g11_standard_retrieval_service_failure_is_failed_not_fake_success` / `test_t_r12_standard_qdrant_retrieval_is_default_without_smoke_env` / `test_t_r15_retrieval_failure_diagnostics_distinguish_required_categories` を `@pytest.mark.skip`
- `tests/test_chunk_level_disabled.py` を整理: gate test を削除し、`raise NotImplementedError` を 5 dormant function + 2 core helper で assert する 7 件、stub artifact shape 2 件、section_collection_exists 3 件の合計 12 件に再編
- `spec_grag/retrieval_index.py` 冒頭に「DORMANT FUNCTIONS」WARNING ブロックを追加し、live (case C-1) / dormant (R-5) の関数リストを明示

運用環境への影響:

- Qdrant `spec_grag_source` collection を `curl -X DELETE http://localhost:6333/collections/spec_grag_source` で物理削除済み (このセッション 2026-05-11 09:35 JST 頃)
- 運用 template `spec_grag/templates/.spec-grag/config.toml` の `chunk_level_enabled` 行は不要になったため追加しない (gate 自体が消えたので config override も無効)

残:

- 全 unit suite を再実行し、skip-marked test 以外が全て pass することを確認 (本 commit 後に実施)
- chunk-level dormant code を最終的にソースから撤去するかは、ユーザー判断後に別 commit で実施

### 7.3 案 C-1 確定時の確認事項

- [ ] `heading_level` の用途確認 (現状どこで使われているか調査)。利用箇所が無ければ `section_manifest.json` からも除外
- [ ] `semantic_hash` と `source_hash` の使い分け確認 (現状ほぼ同じ値が入っている可能性)。同一なら 1 つに統合
- [ ] `text` (embedding 入力テキスト) を Qdrant payload から除外可能か検討 (節約。再生成は他 field から決定論的に可能)
- [ ] `section_manifest.json` の最終 schema 確定 (本ドキュメント §4.3 案を本実装の docstring に転記)

### 7.4 段階的 refactor (案 C-1)

⚠️ **前提**: Phase R-2 以降に進む前に、§7.2 (search_keys / identifiers 役割分離) の対処を完了すること。chunk-level を廃止して section-level 単独運用にした時、search_keys が役割定義通りでないと検索品質が劣化する。

- [x] Phase R-0 (前提): §7.2 を完了 (LLM プロンプト改訂 + post-process フィルタ + `prompt_version` bump + 重複ゼロ test)
  - 実装: §7.2 の各 evidence 行を参照 (LLM prompt instructions, `_is_identifier_like_search_key` filter, `SECTION_METADATA_PROMPT_VERSION = "section-metadata-v2"`)
  - 検証 (unit): tests/test_section_metadata_generation.py の 3 件 (`test_search_keys_and_identifiers_are_disjoint` / `test_section_metadata_prompt_includes_role_constraint_instructions` / `test_section_metadata_prompt_version_is_v2`)。unit suite 全体 342 passed, 9 skipped (calibration matrix のみ skip)
  - 検証 (実 LLM): 2026-05-11 03:00 UTC+9 に spec-grag リポジトリ (`.spec-grag/config.toml` の default_provider = codex, model = gpt-5.4-mini, effort = low) で `spec-grag core --all` を実行。50 sections の section_metadata.json を v1 → v2 で再生成し、search_keys ∩ identifiers の重複が **92.0% → 0.0%** (sections-with-overlap 46/50 → 0/50)、per-key overlap rate **45.2% → 0.0%** (218/482 → 0/486) に低下。AFTER の sample section `25_コンポーネント層（配置操作）.md#0003-スコープ` は search_keys に "扱う範囲と扱わない範囲" / "文書のスコープ" / "型を選ぶ理由" 等の自然言語句を持ち、identifiers に `replaceComponent` / `registerComponents` / `addComponent` 等の code symbol が分離されている (役割分離が機能していることを確認)
- [x] Phase R-1: 設計書改訂 (案 C-1 + §5 inject フローを `doc/DESIGN.ja.md` / `doc/EXTERNAL_DESIGN.ja.md` に明記、checkbox 化)
  - 実装: doc/EXTERNAL_DESIGN.ja.md §2.6 / §2.6.1 / §2.7 / §2.8 / §2.9 / §3.1 / §8.4 に「外部契約 assertion (CLAUDE.md ルール 13)」ブロックを追加 (file:line + 検証 test 関数名を併記)。doc/DESIGN.ja.md §0「実装状況」ダッシュボードに 10 行のチェックボックスを追加
  - 検証: `git grep -c "^- \\[x\\]" doc/EXTERNAL_DESIGN.ja.md` で実装済み assertion 数を機械的に追跡できる
- [x] Phase R-2: 読み取り経路を `spec_grag_section` Qdrant payload に統一 (`section_metadata.json` / `source_chunks.json` を読む箇所を payload lookup に置換)
  - 実装: spec_grag/section_payload.py (`fetch_section_payloads`、`section_payload_to_metadata_entry`、`metadata_entries_from_payloads`)。`client.scroll` + `MatchAny(source_section_id)` filter で id-indexed lookup、256 件単位の batch
  - 検証: tests/test_section_payload.py (10 件 passed): 戻り値の dict shape、batch サイズ、legacy-shape conversion、SectionPayloadLookupError 型
  - 残: Phase R-6 (inject CLI) で実消費。spec_grag/core.py の `_read_artifact(store, "section_metadata")` 経路は依然存在 (Phase R-5 で廃止予定)
- [x] Phase R-3: 書き込み経路を Qdrant 直結
  - LLM 出力 → `spec_grag_section` payload upsert (`related_sections` を含む)
  - related_sections LLM typing 完了時 → `set_payload` で payload に追加
  - `section_metadata.json` / `source_chunks.json` への書き込みは backward compat 期間のみ
  - 実装: spec_grag/retrieval_index.py `build_section_payloads` に `related_sections` を含める変更、spec_grag/retrieval_index.py `update_section_collection_related_sections`、spec_grag/core.py `_update_section_collection_related_sections_if_enabled` を `apply_related_sections_to_metadata` 直後に wire
  - 検証: tests/test_retrieval_index.py の 5 件追加 (`test_section_payloads_include_related_sections_when_metadata_has_it` / `test_section_payloads_default_related_sections_to_empty_list` / `test_update_section_collection_related_sections_issues_set_payload_per_section` / `test_update_section_collection_related_sections_empty_input_skips_client` / `test_update_section_collection_related_sections_records_per_section_error`)。adjacent suite 92 passed
- [x] Phase R-4: 監査ログを `section_manifest.json` 拡張側に移植 (provider, status, generated_at, last_prompt_version)
  - 実装: spec_grag/core.py `_section_manifest_audit_by_id` と `_section_manifest_entry(..., audit=...)` で、metadata_entries から `llm_provider` / `llm_generation_status` / `last_prompt_version` / `generated_at` を section_manifest entry に注入。section_metadata.json 側の同フィールドは backward compat で残置 (Phase R-5 で削除予定)
  - 検証: tests/test_section_manifest_audit.py (6 件 passed): audit_by_id 収集、source_section_id fallback、部分 audit、no-audit 動作。adjacent suite (test_spec_core + test_freshness + test_context_artifacts + test_section_manifest_audit) 74 passed
- [x] Phase R-5: chunk-level 完全撤去 (本コミットではコメントアウト + stub artifact 方式で disable。Qdrant `spec_grag_source` collection 自体の削除は別 migration tool として残置)
  - 実装: spec_grag/core.py:51 に `CHUNK_LEVEL_ENABLED: bool = False` を導入。`_chunk_level_enabled(config)` で `[vector_store].chunk_level_enabled` config override 可。`_run_spec_core_unlocked` の chunk-level call sites を `if _chunk_level_enabled(config):` でガード。`_chunk_level_disabled_artifact_source_chunks` / `_chunk_level_disabled_artifact_retrieval_index_revision` で status="disabled" + phase_r5 diagnostics の stub artifact を書き出し
  - chunk-level コード (`build_source_chunks` / `build_source_chunks_artifact` / `compute_chunk_diff` / `upsert_qdrant_bge_m3_index_incremental` / `_qdrant_upsert_with_partial_dispatch`) は撤去せず、コメントアウト相当の dormant code として残置 (ユーザー指示「chunk-level はコメントアウトしておく」に準拠)
  - テスト互換: tests/conftest.py の `_enable_chunk_level_for_tests` hook で `CHUNK_LEVEL_ENABLED = True` を session 越しに set し、既存 chunk-level test を温存
  - 検証: tests/test_chunk_level_disabled.py (6 件 passed) で production default / config override / stub shape / chunk helper 非呼出を assert。adjacent suite 88 passed
  - 残: 運用環境 (.spec-grag/config.toml) で `[vector_store].chunk_level_enabled = false` を採用 (現状 template 未更新)。Qdrant `spec_grag_source` collection の `delete_collection` migration script 未実装 (運用者判断で `curl -X DELETE http://localhost:6333/collections/spec_grag_source` 推奨)
- [x] Phase R-6: F-06 (inject CLI 拡張) を §5.3 の API 設計通りに実装
  - `inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` / `inject "<task>"` (gate probe + constraints 検証)
  - 実装: spec_grag/inject.py に `run_inject_search` / `run_inject_section` / `run_inject_chapters` / `run_inject_purpose` / `run_inject_conflicts` を追加。Qdrant 利用は `_build_qdrant_client` / `_build_hybrid_retriever` helper 経由で structured warning fallback 付き。spec_grag/cli.py に 5 つの subparser + dispatch (`_run_inject_search_from_args` 等) を追加
  - 検証: tests/test_inject_cli_extension.py (11 件 passed) で各 CLI の正常系 / fallback / 空入力 / Qdrant 不可 / 埋め込み不可を assert。adjacent suite 66 passed。`spec-grag --help` に 5 つの新 subcommand が表示されることを確認
- [x] Phase R-7: chapter_anchors.json を本来の設計意図 (DESIGN.ja.md §6) 通りに LLM 生成で実装
  - 章単位で LLM call、input は heading + 章配下の section summaries + 関連 Core Concept
  - output: summary / key_topics / important_sections / notes / source_section_ids
  - prompt_version 管理、cache 化 (key = chapter_id + 章配下 section_hash 集合 + prompt_version)
  - 実装: spec_grag/chapter_anchors.py (`CHAPTER_ANCHORS_PROMPT_VERSION = "chapter-anchors-v1"`、`ChapterAnchorsCache`、`generate_chapter_anchors`)。stage は LlmRequest contract に合わせ `chapter_key_anchor`。spec_grag/core.py `_chapter_anchors` を新 module 委譲に置換 (旧機械集約は fallback path として残置)
  - 検証: tests/test_chapter_anchors.py (9 件 passed) で LLM call 数、summary/key_topics/notes が LLM 出力に由来すること、important_sections が章内 section_ids に絞られること、unparseable response 時の mechanical fallback、cache reuse、section_hash 変更時の選択的 invalidation を assert
  - output: summary / key_topics / important_sections / notes / source_section_ids
  - prompt_version 管理、cache 化 (key = chapter_id + 章配下 section_hash 集合 + prompt_version)
  - 現在の機械集約 ([core.py:2216 `_chapter_anchors`](spec_grag/core.py#L2216)) を置換
