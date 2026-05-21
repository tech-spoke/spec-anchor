# SPEC-anchor 外部設計書

本書は SPEC-anchor の外部契約を定義する。ここでは、ユーザーが何を実行できるか、各コマンドが何を保証するか、どの情報を保持するか、Agent / LLM と CLI の責務をどこで分けるか、SPEC-anchor がどのように動作するかを扱う。

内部実装、embedding provider、LLM provider、保存形式、検索アルゴリズム、slash command の具体プロンプトは外部設計の対象外である (§12)。

## 1. 目的

LLM は、目の前にあるファイルや直近の会話に強く注意を向ける。その性質は実装作業では役に立つが、背景知識や上位目的の収集が足りないまま進むと、局所的な内容へ過剰に引っ張られ、設計意図からずれた回答や修正を出しやすい。

SPEC-anchor の目的は、LLM が作業中に次を見失わないようにすることである。

- 本来の目的
- Core Concept
- 現在の課題に関係する Source Specs
- Section ごとの概要と検索入口
- Section 間の関連先
- 章単位の key anchor

軽量化の方針として、property graph、entity relation graph、hierarchical cluster、Concept 自動更新、広範な conflict 承認フロー、実行モード分岐は標準経路に含めない。永続化する構造と人間承認の待ち時間を減らす。LLM が解決できない conflict のみ、Conflict Review Item として人間判断待ちを作る。これは標準契約であり、warning-only の逃げ道ではない。

Section 数が多いプロジェクトでは、`/spec-core --all` の LLM 呼び出しはなお重くなる。実装は、Section hash による incremental update、複数 Section の batch 生成、変更 chapter だけの再生成を基本にする。

主導権は Agent / LLM にある。slash command は Agent / LLM に対して探索手順を指示し、CLI は保持物と検索機能を提供する。CLI は最終判断主体ではない。

### 1.1 方式の分類

SPEC-anchor は、業界標準資料 (`doc/監査/STANDARD_GRAG_PATTERNS.ja.md`) の分類で言えば **Hybrid RAG + lightweight related-section retrieval** に位置づけられる。

| 要素 | SPEC-anchor での実装 |
|---|---|
| Hybrid RAG | Section を単位とした BGE-M3 の dense + sparse vector を Qdrant の `[retrieval].section_collection` で RRF 結合する。これが Source Specs 探索の主経路 (`spec-anchor inject-search`) |
| lightweight related-section retrieval | 各 Section に LLM 生成の Section Metadata (Summary / Search Keys / Identifiers / Related Sections) を持たせ、Related Sections は単純な配列として payload に格納する。`spec-anchor inject-section` で id 指定の payload lookup を提供し、Agent が再帰的に辿る |

業界標準資料 §7 で言うところの「property graph」「entity relation graph」「hierarchical cluster」は本方式では**標準経路に含めない** (§1 軽量化方針)。Related Sections は単一の payload field として持ち、graph traversal の代替を Agent の再帰的 lookup に置く。これにより、永続化する構造を最小に抑え、graph 構築・保守のコストを Agent / LLM 側の探索コストに置き換える。

「SPEC-anchor」は本方式に与えた固有の製品名であり、業界用語の「GraphRAG」とは別カテゴリ (graph 構造を持たないため) であることに注意する。

## 2. 用語と範囲

本書では新しい整理語を使うため、先に範囲を定義する。

### 2.1 Purpose

Purpose は、このプロジェクトが何のためにあるかを示す人間管理文書である。

含むもの:

- プロジェクトの存在理由
- 達成したい価値
- ユーザー体験や業務上の目的
- 個別仕様より上位にある判断基準

含まないもの:

- 具体的な Section 要約
- 検索キー
- 実装詳細
- LLM が一時的に推測した制約

### 2.2 Source Specs

Source Specs は、SPEC-anchor の対象となる仕様本文ファイル群である。`.spec-anchor/config.toml` の `[sources].include` に一致する Markdown 文書を指す。

Source Specs は、現在の仕様本文であり、今回の課題に対して「守るべき既存仕様」になる場合も、「修正対象」になる場合もある。

### 2.3 Core Concept

Core Concept は、プロジェクト全体の判断軸、承認済みの設計原則、不変に近い方針を指す。

含むもの:

- 設計原則
- 守るべき境界
- 判断時に優先する考え方
- 人間が承認済みの方針

含まないもの:

- Source Specs から自動抽出された未承認候補
- Section summary
- 検索キー
- LLM が一時的に推測した制約

### 2.4 Section

Section は、Source Specs を Markdown 見出しで分割した単位である。SPEC-anchor は次の処理を Section 単位で行う。

- Section Summary、Section Search Keys、Section Identifiers の生成
- Related Sections の関連付け
- Source Retrieval Index への登録
- `/spec-inject` / `/spec-realign` の検索結果として返す単位

Section の分割規則は §3.1 に定義する。

各 Section の `source_section_id` は、`<file_path>#<ordinal>-<heading_slug>` 形式の識別子である。`<ordinal>` は同一 file 内での Section 出現順序を 4 桁 zero-padded で表したもの (1 始まり、例: `0001` / `0002` / ...)。`<heading_slug>` は heading text を正規化したもので、英数字 / アンダースコア / 日本語 (ひらがな・カタカナ・漢字) は保持し、それ以外の文字は `-` に置換、小文字化、前後の `-` を除去する (空文字列になる場合は `section` を使う)。例: `docs/spec/sample.md#0002-authentication`、`docs/spec/auth.md#0003-認証設計`。

ordinal を含める目的は、同一 file 内で同名 heading が複数ある場合でも一意性を保つことである (`<file_path>#<heading_slug>` だけだと衝突する可能性があるため)。`source_section_id` は、`.spec-anchor/config.toml` の `[sources].include` に一致する Source Specs 全体で一意でなければならない。SPEC-anchor はこの一意性を、Source Retrieval Index と Related Sections が同じ Section を参照し続けるための契約として扱う。

### 2.5 Section Metadata

Section Metadata は、Source Specs の各 Section に対して `/spec-core` が生成・更新する検索補助情報の総称である。単独で最終根拠にはしない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の根拠を確認する。

### 2.6 Section Search Keys

Section Search Keys は、検索 recall を上げるための **自然言語**の検索キーワードである。コードシンボル / API 名 / CLI コマンド / CLI option / ファイルパス / ALL_CAPS 定数 / PascalCase 型名は含まない。これらは Section Identifiers (§2.6.1) に分離する。

Section Search Keys は根拠ではない。検索に引っかけるための補助語であり、制約として扱ってはいけない。

#### 2.6.1 Section Identifiers

Section Identifiers は、Section 本文 + heading に出現する **コードシンボル / 固有技術名**を、正規表現で機械抽出した list である。LLM 判断を経由しない。

含むもの:

- API 名、関数名、CLI コマンド、CLI option (例: `bindContext`, `removeBindContext`, `productStoreGroup.replace`, `--rebuild`)
- ファイルパス、ALL_CAPS 定数、PascalCase 型名、ドット区切り技術名

Section Identifiers は根拠ではない。検索の補助 / 関連候補生成の手がかりであり、制約として扱ってはいけない。

### 2.7 Related Sections

Related Sections は、ある Section を見たときに一緒に見るべき Section の一覧である (依存先、影響先、同じ方針に属する Section、変更時に確認すべき Section、衝突しうる Section)。full graph relation、無制限の多段 traversal、CLI による自律的な Agentic Search は含まない。

CLI は関連先を保持・返却するが、どこまで辿るかは Agent / LLM が判断する。

Related Sections は最終根拠ではないが単なる一時候補でもない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の該当箇所を根拠として確認する。

relation_hint は `depends_on / impacts / prerequisite / same_policy / see_also` のみ。**`conflicts_with` は本 stage では確定させない**。LLM が矛盾の兆候を見つけた場合は `possible_conflict: true` フラグだけ立て、最終判定は §2.8 Conflict Review Item へ委ねる。

### 2.8 Conflict Review Item

Conflict Review Item は、Purpose、Core Concept、または Source Specs の根拠同士が同時に満たせない疑いがあり、LLM が既存根拠だけでは解消できない場合に、人間へ判断を求める項目である。

含むもの:

- conflict の対象となる source refs
- それぞれの主張の要約
- 矛盾していると判断した理由
- LLM が解決できない理由
- 人間に選んでほしい判断肢
- status

含まないもの:

- Core Concept の自動更新
- Source Specs の自動修正
- LLM による最終裁定

Conflict Review Item は単なる warning ではない。status が `pending` の項目は人間判断待ちであり、`/spec-inject` と `/spec-realign` はその状態を無視して制約生成や回答生成へ進んではいけない。

### 2.9 Chapter Key Anchor

Chapter Key Anchor は、章全体の重要テーマ、判断軸、主要 Section への入口を、LLM が章単位で抽象化して生成する artifact である。Agentic Search の章単位エントリポイントとして使う。

output (per chapter):

- `chapter_id`
- `summary`: 章全体の抽象化された要約
- `key_topics[]`: 章の重要テーマ
- `important_sections[]`: 章内で判断軸となる主要 Section の section_id 群
- `notes[]`: 章全体で守るべき読み方
- `source_section_ids[]`: 章配下の全 section_id

Chapter Key Anchor は最終根拠ではない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の該当箇所を根拠として確認する。

### 2.10 Agentic Search

Agentic Search は、Agent / LLM が検索結果を見ながら追加検索、関連先参照、根拠確認を繰り返す行動を指す。

Agentic Search は CLI の責務ではない。slash command の説明に探索手順を書き、Agent / LLM がそれに従って必要な検索を行う。

## 3. SPEC-anchor の動作モデル

SPEC-anchor は、Source Specs を読み取り、Agent / LLM が後で参照できる保持物を生成し、保持物の鮮度を保ち、課題提示時に制約を生成し、必要に応じて回答を生成する。本章はこの全体の動作モデルを 5 ステップで示す。

| ステップ | 役割 | 主担当 | 詳細 |
|---|---|---|---|
| §3.1 | Source Specs を Section に分割する | CLI | 本節 |
| §3.2 | 保持物を生成する | CLI + Agent / LLM (`/spec-core`) | 本節 + §7 |
| §3.3 | 保持物の鮮度を保つ | CLI (`spec-anchor-watch` / freshness gate) | 本節 |
| §3.4 | 制約を生成する | Agent / LLM (`/spec-inject`) | 本節 + §8 |
| §3.5 | 回答を生成する | Agent / LLM (`/spec-realign`) | 本節 + §9 |

### 3.1 Source Specs を Section に分割する

Source Specs (§2.2) は、Markdown 見出しを境界として Section (§2.4) に分割される。境界となる Markdown 見出しの最大深さは `[section].max_heading_level` で指定する (§10.2)。標準は `4`。設定値以下の見出しは Section 境界となり、それより深い見出しは独立 Section にならず、直近の親 Section の本文に統合される。

例 (`max_heading_level = 4` の場合):

```text
## Feature                        -> Section
### Field group                   -> Section
#### Image upload                 -> Section
##### Internal helper             -> 親 Section の本文に統合
```

### 3.2 保持物を生成する

`/spec-core` は Source Specs を読み、Section Metadata、Related Sections、Chapter Key Anchor、Source Retrieval Index、Conflict Review Items を生成する (§4 保持物一覧、§7 詳細契約)。

`/spec-core` は Section hash に基づいて変更された Section だけを更新する incremental update を基本とする。`--all` flag で LLM 由来 cache をクリアして再評価できる。`--rebuild` flag で Source Retrieval Index の Qdrant collection を全再構築する。

Purpose と Core Concept は人間が更新する。SPEC-anchor はこれらを自動更新しない (§5.1 Human の責務)。

### 3.3 保持物の鮮度を保つ

`/spec-inject` (各 `inject-*` サブコマンド: `inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts`) と `/spec-realign` は、保持物が最新でない場合は停止し、理由と対処方法を表示する (freshness gate)。各コマンドは内部で gate を通すので、Agent が事前に別の probe コマンドを呼ぶ必要はない。

| 状態 | `/spec-inject` / `/spec-realign` の動作 | 対処 |
|---|---|---|
| 保持物は最新 | 続行する | — |
| Source Specs が変更されたが `/spec-core` で更新されていない | 停止する | `/spec-core` を実行する |
| `spec-anchor-watch` が実行中、または未処理の変更が残っている | 停止する | watcher の完了を待つ |
| 人間判断待ちの Conflict Review Item がある | 停止する | Conflict Review Item に判断を返す |
| 一部の保持物の生成に失敗している | 停止する | `/spec-core --all` で再生成する |
| 一部の保持物が欠けているが必須分は使える | warning を表示し続行できる | 必要なら `/spec-core` で補完する |

Source Specs の変更と未解決 Conflict が同時にある場合は、まず `/spec-core` で保持物を更新する。更新後も残る Conflict だけが人間判断の対象になる。

`/spec-inject` と `/spec-realign` は `/spec-core` を自動実行しない。保持物の更新はユーザーが `/spec-core` を明示実行するか、`spec-anchor-watch` に任せる。

`spec-anchor-watch` (§6.3) は、1 回の更新で処理する Source Specs の範囲を開始時点で固定する。更新中に追加の変更が入った場合、その変更は次回に回す。更新中および未処理の変更が残っている間、`/spec-inject` と `/spec-realign` は停止する。

### 3.4 制約を生成する

`/spec-inject` は、Agent / LLM が現在の会話区間と課題を解釈し、SPEC-anchor の保持物を使って今回必要な制約を生成し、会話区間へ注入するためのコマンドである (§8 詳細契約)。

`/spec-inject` の入力は、明示された課題プロンプトだけでなく、現在の会話区間も含む。会話区間を解釈する主体は Agent / LLM である。

```text
Conversation Context
  - 現在のユーザー発話
  - 直近の会話区間
  - 明示された課題プロンプト
  - 進行中の作業対象
```

会話区間は検索キー生成と制約生成の入力であり、仕様上の根拠ではない。最終根拠は Purpose、Core Concept、Source Specs のどれに由来するかを区別する。Section Summary と Chapter Key Anchor を使った場合は、参照補助として区別する。

SPEC-anchor は、Source Specs 本文および大きく成長する保持物 (Core Concept、Chapter Key Anchor) を無条件に LLM コンテキストへ丸ごと投入しない。Agent / LLM は Agentic Search、検索キー生成、根拠確認のために必要な Source Specs snippet および保持物の必要箇所を読むことができる。`spec-anchor inject-chapters` / `inject-purpose` は対応する保持物の path を返すので、Agent は path を `Read` で読み、課題に関連する部分だけを抽出する。Purpose は目的そのもので短いため `inject-purpose` の戻り値に全文を含める。読んだ本文を無整理のまま最終回答の前提へ混ぜてはいけない。最終的に使う制約は、今回の課題に必要なものとして生成し、根拠を示す。

Search Keys は根拠にしない。Section Summary と Chapter Key Anchor は検索・理解の補助であり、制約として採用する場合は Purpose、Core Concept、Source Specs、または解決済み Conflict Review Item の根拠を確認する。

全文を最終コンテキストとして扱うのは、ユーザーが明示的に全文レビューを求めた場合に限る。

### 3.5 回答を生成する

`/spec-realign` は、`/spec-inject` と同じ手順で今回必要な制約を生成し、その制約に従って課題への回答または修正案を作るためのコマンドである (§9 詳細契約)。

`/spec-realign` も §3.4 と同じ Conversation Context および生テキスト投入の制限に従う。LLM は、生成した制約を守って回答する。制約と矛盾する案を出す場合は、その矛盾を隠さず明示し、人間レビューが必要な点として扱う。

## 4. 保持物

SPEC-anchor は、次の情報を保持する。

| 保持物 | 更新主体 | 役割 |
|---|---|---|
| Purpose | 人間 | 本来の目的。ビジネスゴール、UX の根幹、システムが存在する理由 |
| Core Concept | 人間 | 全体の判断軸、承認済みの設計原則 |
| Section Summary | `/spec-core` | 各 Section が何について書かれているかを示す |
| Section Search Keys | `/spec-core` | 自然言語で Section を検索するためのキーワード |
| Section Identifiers | `/spec-core` | Section 本文に出現するコードシンボル / 固有技術名の機械抽出リスト |
| Related Sections | `/spec-core` | 一緒に見るべき Section、依存・影響・関連先 (typed graph) |
| Conflict Review Items | `/spec-core` / 人間 | LLM が解決できない仕様 conflict の人間判断待ち項目 |
| Chapter Key Anchor | `/spec-core` | 章全体の重要テーマ、判断軸、主要 Section への入口 |
| Source Retrieval Index | `/spec-core` | Source Specs を Section 単位で hybrid retrieval するための index |

Purpose と Core Concept は人間が更新する。SPEC-anchor はこれらを自動更新しない。

SPEC-anchor は Core Concept 乖離通知を保証しない。Source Specs の進化により Core Concept が陳腐化した場合でも、自動更新や自動通知は行わず、人間が必要に応じて Core Concept を更新する。

### 4.1 保持物の物理配置

保持物は責務ごとに 3 つの保存先に分離する。

**検索管理 (Qdrant `[retrieval].section_collection`、default `spec_anchor_section`)**:

- source_document_id / source_span / Section Summary / Section Search Keys / Section Identifiers / Related Sections / heading_path を payload に格納する。1 Section = 1 vector。
- Source Retrieval Index は section-level の Qdrant collection そのものである。Source Specs を chunk 分割して別 collection に持つことはしない。
- Qdrant の point id は、`source_section_id` から生成した UUID5 文字列である。固定 namespace UUID は `b1d5535d-3e52-5430-af3e-ddd879e6cb19` であり、この値は一度採用した後に変更しない。これにより、Source Specs の Section が並べ替えられても、同じ `source_section_id` は同じ point id に対応し続ける。
- 1 Section の embedding 入力 text は、`heading_path` を ` / ` で結合した見出し列、Section Summary、Section Search Keys (上限 8 件、半角空白で結合)、Section Identifiers (上限 8 件、半角空白で結合) を ` | ` で並べた短い text である。Source Specs 本文 (raw body) は embedding 入力に含めない。これにより、長い Section でも 1 Section = 1 BGE-M3 vector に収まり、検索キーと embedding 入力の語彙が一致して retrieval 精度が安定する。Source Specs 本文を確認したい場合、Agent は `spec-anchor inject-search` の hit で得た `source_section_id` と `source_span` から Source Specs の file を `Read` する経路を取る。
- Qdrant を期待した設定で Related Sections 用の retrieval backend を初期化できなかった場合、`/spec-core` は次のように振る舞う:
  - **データ保持**: payload 内の関連先と Section Metadata 側の関連先一覧は更新せず、前回値を残す。これは復旧後の `/spec-core --rebuild` で上書き再構築する基準として使う (data 消失防止)。
  - **status 報告**: `related_sections_status: "failed"` を返し、`failed_required_artifacts` に `related_sections` を追加する (AUD-007 で確定)。`freshness_report.blocking_reasons` に `failed_required_artifact` が積まれ、`freshness_report.status` と `CoreResult.status` はともに `failed` になる。
  - **下流の停止**: `/spec-inject` と `/spec-realign` は freshness gate (§3.3) で停止し、利用者は Qdrant を復旧して `spec-anchor core --rebuild` を実行する必要がある。前回値の保持は data 消失防止のためであり、業務継続を意図したものではない。

**外部契約として人間 / Agent が参照する artifact (`.spec-anchor/context/`)**:

- Conflict Review Items は `.spec-anchor/context/conflict_review_items.json` に格納する (人間判断 artifact、git 追跡対象)。
- Chapter Key Anchor は `.spec-anchor/context/chapter_anchors.json` に格納する。Chapter anchor を生成できない chapter があった場合、`/spec-core` はこの canonical artifact を更新せず、前回の値を残す。

**状態管理 / 鮮度判定 / watcher 動作状態 (`.spec-anchor/state/`)**:

- Section の差分検出と監査用 metadata を `.spec-anchor/state/section_manifest.json` に格納する。各 Section には、Source Specs 本文の hash、検索用 embedding に渡す入力 text の fingerprint、Qdrant に保存する payload の fingerprint を記録する。これにより、本文が同じでも検索補助情報や payload が変わった Section を次回 `/spec-core` が検出できる。
- 保持物全体の鮮度状態を `.spec-anchor/state/freshness.json` に格納する。watcher の background update 結果を `/spec-inject` / `/spec-realign` が読む通信媒体として機能する。
- watcher の polling state と未処理キューは `[watcher].state_file` / `[watcher].queue_file` で指定された path (既定 `.spec-anchor/state/watch_state.json` / `.spec-anchor/state/watch_queue.json`) に格納する。
- Source Retrieval Index の冪等判定用の状態記録ファイルを `.spec-anchor/state/retrieval_index_state.json` に格納する。前回 `/spec-core` が retrieval index に upsert を実行した時の Source Specs section 集合の hash 指紋と、その時の embedding / retrieval 設定の指紋を記録する。incremental 実行で「入力 section 集合と設定が前回と完全一致」と判定できる場合に、Qdrant への upsert と embedding 計算を省略するための判定材料として使う。前提が崩れた場合 (状態記録ファイルが無い / 指紋不一致 / Qdrant collection が存在しない) は通常の upsert 経路に fallback する。
- Related Sections の候補生成入力の冪等判定用の状態記録ファイルを `.spec-anchor/state/related_sections_state.json` に格納する。前回 `/spec-core` が Related Sections を生成した時の section 集合 hash と、candidate generation / LLM selection の設定指紋を記録する。incremental 実行で同一入力なら候補生成と LLM selection を省略し、前回の選択結果を継承するための判定材料として使う。前提が崩れた場合は通常の生成経路に fallback する。

**LLM 応答 cache (`.spec-anchor/cache/`)**:

- section_metadata / related_sections / chapter_anchors の LLM 応答キャッシュ。

**正本ファイル (artifact 化しない)**:

- Purpose / Core Concept は `[core].purpose_file` / `[core].concept_file` で指定された file の本文をそのまま正本として扱う。SPEC-anchor は別 artifact 化しない。

## 5. 責務境界

### 5.1 Human

Human は次を担当する。

- Purpose の作成・更新
- Core Concept の作成・更新
- 最終的な仕様判断
- Conflict Review Item の判断
- LLM が生成した制約や回答の採否判断

### 5.2 Agent / LLM

Agent / LLM は次を担当する。

- 会話区間を読む
- 課題を解釈する
- 必要な検索キーを作る
- hybrid retrieval を実行する
- Section Summary を参照する
- Related Sections を参照する
- Chapter Key Anchor を参照する
- 検索結果を見ながら Agentic Search を行う
- 集めた情報から今回の課題に必要な制約を生成する
- LLM だけでは解決できない conflict を人間判断待ちとして提示する
- `/spec-realign` では、その制約に従って回答または修正案を作る

### 5.3 CLI / SPEC-anchor

CLI / SPEC-anchor は次を担当する。

- 設定ファイルを読む
- Source Specs の Section hash を管理する
- Section Metadata を生成・保持する
- Conflict Review Item を生成・保持する
- Chapter Key Anchor を生成・保持する
- Source Retrieval Index を生成・保持する
- freshness を判定する
- Agent / LLM が渡した検索キーに対して検索結果を返す
- 指定された Section Summary、Related Sections、Chapter Key Anchor を返す

CLI / SPEC-anchor は次を担当しない。

- 会話区間を最終解釈する
- Agentic Search の探索方針を自律的に決める
- 今回の課題に必要な制約を最終生成する
- conflict を人間抜きで最終裁定する
- Answer を自由生成する
- Purpose / Core Concept を自動更新する

## 6. コマンド体系

SPEC-anchor は、ユーザー向け slash command、Source Specs 変更を background で処理する watcher process、導入を支援する setup script を提供する。

| コマンド | 目的 | 詳細 |
|---|---|---|
| `/spec-core` | 保持物を生成・更新する | §7 |
| `/spec-inject` | 課題に対する制約を生成する (回答は出さない) | §8 |
| `/spec-realign` | 制約を生成し、課題に回答する | §9 |
| `spec-anchor-watch` | Source Specs 変更を監視し background で更新する | §6.3 |
| `spec-anchor-setup-system` | 外部依存の導入状態を確認する | §6.2.1 |
| `spec-anchor-setup-project` | プロジェクトに設定と Agent 入口を配置する | §6.2.2 |

### 6.1 Agent 別 command / skill 入口

SPEC-anchor は、同じ CLI 契約を、各 Agent CLI が認識する入口形式で提供する。

| Agent 環境 | 入口形式 | 配置先 |
|---|---|---|
| Claude Code / Claude CLI | command template | `<project>/.claude/commands/` |
| Codex CLI | skill (SKILL.md) | `<project>/.codex/skills/spec-anchor/` |

入口形式は Agent CLI ごとに固定であり、利用者が選ぶ対象ではない。配置は Project Setup Script (§6.2.2) が行う。

### 6.2 Setup Script

本書でいう setup script は、実行時の検索・制約生成ではなく、SPEC-anchor を使い始めるための配置と検証を行う補助コマンドである。

#### 6.2.1 System Setup Script

SPEC-anchor の動作に必要な外部依存が揃っているかを確認する。

```
spec-anchor-setup-system
```

入力: なし (インストール済み環境を対象とする)

確認対象:

- SPEC-anchor CLI が実行可能か
- embedding provider (FlagEmbedding BGE-M3) が読み込めるか
- vector store (Qdrant) に接続できるか
- Agent CLI (Codex / Claude) が利用可能か

出力: 結果を JSON で標準出力に出す。

- 全て揃っている場合: `production_readiness.status` = `"ready"`
- 不足がある場合: `production_readiness.status` = `"blocked"`、不足理由が `diagnostics` に含まれる

exit code: ready なら 0、blocked なら非 0。

オプション:

- `--check-only`: 確認のみ行い何も変更しない
- `--qdrant-url <url>`: Qdrant 接続先を指定 (default `http://localhost:6333`)

System Setup Script は対象プロジェクトの Source Specs、Purpose、Core Concept、生成済み保持物を変更しない。プロジェクトへのファイル配置は Project Setup Script (§6.2.2) の責務である。

#### 6.2.2 Project Setup Script

対象プロジェクトに SPEC-anchor の設定ファイルと Agent 入口を配置する。

```
spec-anchor-setup-project --target <project-root>
```

入力:

| オプション | 既定 | 内容 |
|---|---|---|
| `--target <path>` | `.` (カレントディレクトリ) | プロジェクトルート |
| `--agent <codex\|claude\|both>` | `both` | Agent 入口の配置先。`claude` は `<target>/.claude/commands/` に command template、`codex` は `<target>/.codex/skills/spec-anchor/` に skill を配置 |
| `--dry-run` | — | 作成・更新予定を表示するだけで変更しない |
| `--force` | — | 既存ファイルの上書きを許可する |
| `--no-init-core-files` | — | Purpose / Core Concept の雛形を作成しない |

処理:

- `.spec-anchor/config.toml` と `.spec-anchor/.gitignore` を作成する
- Purpose / Core Concept の雛形を作成する (未存在の場合。`--no-init-core-files` で抑止可)
- `--agent` に応じて Claude command template と Codex skill を `<target>` 配下に配置する

出力: 結果を JSON で標準出力に出す。exit code は成功なら 0、失敗なら非 0。

安全性:

- 既存ファイルがある場合は差分を示して停止する。`--force` を指定した場合のみ上書きする
- `/spec-core` は自動実行しない。setup 後にユーザーが `/spec-core` を明示実行する

配置例:

Claude Code 用 command と Codex 用 skill は、いずれも対象プロジェクト配下に配置する。

```text
your-project/
├── .spec-anchor/
│   ├── config.toml
│   └── context/                  # 生成済み保持物。gitignore 推奨
├── .claude/
│   └── commands/                 # Claude Code 用 command template
│       ├── spec-core.md
│       ├── spec-inject.md
│       └── spec-realign.md
├── .codex/
│   └── skills/
│       └── spec-anchor/
│           └── SKILL.md          # Codex 用 skill 入口
├── docs/
│   ├── SPEC-anchor/
│   │   └── core/
│   │       ├── purpose.md
│   │       └── concept.md
│   └── spec/                     # Source Specs
│       └── ...
```

### 6.3 spec-anchor-watch

Source Specs の変更を検知し、background で `/spec-core` 相当の incremental update を繰り返す。対象プロジェクトはカレントディレクトリ固定なので、対象プロジェクトに `cd` してから実行する。

```
spec-anchor-watch
```

| オプション | 既定 | 内容 |
|---|---|---|
| `--once` | — | 1 回だけ scan して終了する (poll ループに入らない) |
| `--interval-sec <秒>` | 2.0 | 変更がないときの poll 間隔 |
| `--debounce-sec <秒>` | 1.0 | 変更検知後、update を開始するまでの待ち時間 (連続変更をまとめる) |
| `--stale-lock-sec <秒>` | 300 | lock file がこの秒数を超えたら stale とみなして回収する |
| `--max-runs <回数>` | 無制限 | 指定回数だけ update したら終了する |

出力: 各 update の結果を JSON で標準出力に出す。watcher 実行中は freshness gate が `status = blocked` (`watcher_running`) になり、`/spec-inject` と `/spec-realign` は停止する (§3.3)。

## 7. `/spec-core [--all|-a]`

### 7.1 目的

`/spec-core` は、Purpose / Core Concept 以外の保持物を生成・更新するためのコマンドである。

```text
/spec-core
  = Section hash に基づく incremental update。LLM cache と embedding を hash 一致時に再利用

/spec-core --all
  = LLM 由来 cache (section_metadata / pair typing / chapter_anchors) をクリアして再評価
    embedding は決定論的なので hash 一致時に再利用 (時間と計算資源を節約)

/spec-core --rebuild
  = 上記に加え、Qdrant spec_anchor_section collection を drop + recreate
    embedding 破損や schema 移行など vector store 再構築が必要な場合に使う
```

| flag | LLM 由来 cache (section_metadata / pair typing / chapter_anchors) | embedding (Qdrant section collection) |
|---|---|---|
| (none) | reuse (hash 一致時) | reuse (hash 一致時) |
| `--all` | clear → 再生成 | reuse (hash 一致時) |
| `--rebuild` | clear → 再生成 | full recreate (collection 再作成) |

`--rebuild` は `--all` を含意する。

`/spec-core` は `.spec-anchor/config.toml` で指定された LLM provider、embedding provider、vector store provider をそのまま使う。指定された provider が失敗した場合は、別の provider に黙って切り替えず、失敗として報告する。

### 7.2 入力

| 入力 | 内容 |
|---|---|
| `.spec-anchor/config.toml` | 対象ソース、Purpose、Core Concept、保持物の保存先、LLM / embedding 設定 |
| Source Specs | `sources.include` で指定された仕様ファイル |
| Purpose | `core.purpose_file` で指定されたファイル。読み取り専用 |
| Core Concept | `core.concept_file` で指定されたファイル。人間更新対象 |

`spec-anchor core` の CLI フラグ:

| フラグ | 内容 |
|---|---|
| `--all` / `-a` | LLM 由来 cache (section_metadata / pair typing / chapter_anchors) をクリアして再評価する。embedding は hash 一致時に再利用 |
| `--rebuild` | `--all` を含意し、さらに Qdrant `spec_anchor_section` collection を drop + recreate する。embedding 破損や schema 移行時に使う |
| `--verify-index` | Source Retrieval Index の Qdrant collection に保持されている内容が、現在の Section の hash と一致するかを能動検証する。不整合を見つけた場合、retrieval_index_status を failed にして停止指示を表示する。自動修復はしない。 |
| `--llm-provider <id>` | `[llm.stage_routing]` を上書きし、指定した provider id を全 stage に適用する。Codex skill / Claude command は通常指定しない |
| `--decision-json <json>` | pending Conflict Review Item に対する判断結果を JSON で渡す |
| `--decision-file <path>` | pending Conflict Review Item に対する判断結果を JSON ファイルから読み込む |

### 7.3 動作

通常実行では、Section hash に基づいて変更された Source Specs だけを中心に保持物を更新する。

```text
/spec-core
  -> Source Specs の Section manifest を作る
  -> Section hash を比較する
  -> 変更 Section の Section Summary を更新する
  -> 変更 Section の Section Search Keys を更新する
  -> Source Retrieval Index を更新する
  -> 関連候補を広く集め、LLM が Related Sections を理由付きで選ぶ
  -> conflicts_with が疑われる pair を検査する
  -> LLM が解決できない conflict を Conflict Review Item として記録する
  -> 影響する Chapter Key Anchor を更新する
  -> CoreResult を出力する

/spec-core --all
  -> Source Specs を全件読み込む
  -> Section Summary を LLM 再生成する (cache 無視)
  -> Section Search Keys を LLM 再生成する (cache 無視)
  -> Source Retrieval Index は hash 一致時に reuse (embedding は決定論的)
  -> Related Sections を LLM 再 typing する (pair cache 無視)
  -> conflicts_with が疑われる pair を検査する
  -> LLM が解決できない conflict を Conflict Review Item として記録する
  -> Chapter Key Anchor を再生成する
  -> CoreResult を出力する

/spec-core --rebuild
  -> --all と同じ手順で LLM 由来 cache を再評価する
  -> Source Retrieval Index を Qdrant collection ごと full recreate する
```

Purpose と Core Concept は常に読み取り専用である。`/spec-core` はこれらを自動更新しない。

`spec-anchor-watch` が呼び出す core 更新は `/spec-core` の外部 slash command 実行ではない。watcher は background execution role として `spec-core` 相当の incremental update を実行する。

### 7.4 出力

`/spec-core` は次を出力する。

```text
CoreResult
  - mode: incremental | full
  - updated_sources
  - skipped_sources
  - failed_sources
  - failed_sections
  - updated_sections
  - regenerated_chapter_anchors
  - retrieval_index_status
  - related_sections_status
  - potential_conflicts
  - conflict_review_items
  - pending_conflict_count
  - unreflected_conflict_resolutions
  - stale_resolution_count
  - freshness_report
  - warnings
```

`retrieval_index_status` は Source Retrieval Index の最終状態を示す。次のいずれかの値を取る。

- `success` — 今回 `/spec-core` が retrieval index に upsert を実行し、index は最新の section 集合と設定を反映している。
- `skipped` — retrieval index 機能が `[embedding]` / `[vector_store]` の設定で無効化されている (例: `embedding.provider != "flagembedding"`)。Agent / LLM 側は in-memory retrieval にフォールバックする。
- `skipped_unchanged` — 入力 (Source Specs の section 集合と内容、embedding / retrieval 設定の指紋) が前回 `/spec-core` 実行時と完全に一致したため、`/spec-core` は retrieval index への upsert を **実行しなかった**。index は前回実行時点の状態のまま正常で、Agent / LLM 側は前回 index に対して検索を行う。`skipped` とは違い、retrieval index 機能自体は有効である。
- `failed` — retrieval index の upsert / 接続で例外が発生した、または `--verify-index` が不整合を検出した。index が古い、もしくは壊れている可能性がある。`/spec-core --rebuild` で復旧する。
- `blocked` — 上流の理由 (pending conflict、freshness 停止、入力読み込み失敗) で `/spec-core` 自体が処理を中断したため、retrieval index 経路に到達しなかった。

Qdrant collection が手動で削除されている等の理由で `skipped_unchanged` の前提条件 (`.spec-anchor/state/retrieval_index_state.json` の指紋一致 + collection 存在) が崩れている場合、`/spec-core` は Source Retrieval Index の upsert を自動的に実行する。この場合の最終 status は `success` または `failed` であり、全 Section を登録し直した実行は `core_progress.json` の `stages.section_collection_upsert.action = "upserted_full"` として記録する。更新が必要になった理由は、同じ stage の `reason` と `diagnostics` で確認できる。

古い version の SPEC-anchor が作成した Qdrant collection では、Section の並び順に基づく数値の point id が残っている場合がある。`/spec-core` はこの形式を検出すると、その実行内で Source Retrieval Index の Qdrant collection を再作成し、現在の Source Specs から UUID5 形式の point id で登録し直す。ユーザーが `--rebuild` を指定する必要はない。この自動移行が起きた場合、`.spec-anchor/state/core_progress.json` の `stages.section_collection_upsert.action` は `upserted_full` になり、同じ stage に `migration_required_from_ordinal_point_id` という warning が記録される。

Source Specs の一部 Section だけが変わった incremental 実行では、`/spec-core` は Source Retrieval Index の更新対象を変更・追加された Section に絞り、削除された Section は Qdrant collection から取り除く。この差分更新が使われた場合、`.spec-anchor/state/core_progress.json` の `stages.section_collection_upsert.action` は `upserted_partial` になる。ユーザーは同じ stage の `diagnostics` で、`sections_upserted_count`、`sections_deleted_count`、`embed_documents_input_size`、`stale_points_deleted` を確認できる。1 Section だけを変更した場合、この stage の時間は、全 Section を再登録する時間ではなく、変更された Section 数に近い時間として観測される。

`spec-anchor core --verify-index` は、Source Retrieval Index の Qdrant collection に残っている Section 情報と現在の Source Specs から作られる Section 情報を照合する。通常の差分更新や変更なしの再実行で index 本体を読み直さない場合でも、利用者が明示したときだけ実体との乖離を検出できる。不整合が見つかった場合、`/spec-core` は Source Retrieval Index を自動修復せず、結果を failed として `/spec-core --rebuild` の実行を促す。

`related_sections_status` は Related Sections 生成の最終状態を示す。次のいずれかの値を取る。

- `success` — 今回 `/spec-core` が Related Sections の候補生成と LLM selection を実行し、selected_related_sections を最新化した。
- `skipped_unchanged` — 入力 (section 集合と内容、candidate generation / LLM selection の設定指紋) が前回 `/spec-core` 実行時と完全に一致したため、`/spec-core` は候補生成と LLM selection を **実行しなかった**。前回の selected_related_sections がそのまま継承される。
- `failed` — Related Sections 生成のいずれかの段階で例外が発生した、または Qdrant を期待した設定で Qdrant retrieval backend を初期化できなかった。`/spec-core` は canonical な related_sections (Section Metadata 内の関連先一覧と、検索 backend 側の関連先 payload) を更新せず、前回の値を残す。freshness は failed に降格する。Agent / LLM は前回値の利用継続を選ぶか、Qdrant 接続性を復旧してから `/spec-core --rebuild` で再生成する。
- `blocked` — 上流の理由で `/spec-core` が中断され、Related Sections 経路に到達しなかった。

Qdrant を期待した設定 (`vector_store.provider = "qdrant"` / `url` が設定済み / `embedding.provider = "flagembedding"`) で Qdrant retrieval backend を初期化できなかった場合、`/spec-core` は InMemory への自動切り替えを行わず、Related Sections を failed として扱う。利用者は CoreResult の diagnostics で「期待した retrieval backend と実際の状態、失敗理由」を確認できる。Qdrant 未設定 (開発・テスト用の純 InMemory 構成) では Related Sections は引き続き InMemory で生成され、status は `success` を返す。

Source Specs の一部 Section だけが変わった incremental 実行では、`/spec-core` は Related Sections の更新対象を変更・追加された Section だけに絞る。変更されていない Section の Related Sections は前回値をそのまま使い、削除された Section に向いていた関連先は取り除く。この部分更新が使われた場合、`related_sections_status` は引き続き `success` を返し、`.spec-anchor/state/core_progress.json` の `stages.related_sections.action` は `regenerated_partial` になる。利用者は同じ stage の `candidate_generation_elapsed_sec`、`selection_elapsed_sec`、`candidate_generation_source_count`、`candidate_generation_partial_mode` で内訳を確認できる。1 Section だけを変更した場合、この stage の時間は、全 Section の Related Sections を作り直す時間ではなく、変更された Section 数に比例した時間として観測される。

部分更新の前提として、`/spec-core` は **変更された Section から見た関連先** を更新するが、**変更された Section が他の Section の関連先として現れる場合の判定はそのまま前回結果を引き継ぐ**。これは軽微な編集 (1 文字修正、typo) で関連性判定が壊れないよう保守的に振る舞う設計選択である。Section の意味が大きく変わった場合、または conflict 判定を完全に洗い直したい場合は、`/spec-core --all` を実行する。`.spec-anchor/context/related_sections` の各エントリの `partial_mode` と `requires_full_regeneration_for_complete_target_recheck` フラグは、この前提を Agent / 利用者に明示するために添えられる。

Chapter Key Anchor は LLM 生成によってのみ作る。LLM 生成に失敗した chapter があった場合、`/spec-core` は対象 chapter の anchor を作らず、chapter_anchors artifact 全体を failed として扱う。canonical `chapter_anchors.json` は更新せず前回値を残し、freshness は failed に降格する。利用者は失敗した chapter 一覧を CoreResult の diagnostics で確認し、`/spec-core --all` で再試行する。SPEC-anchor は mechanical / placeholder 経由の代替 anchor を提供しない。

`potential_conflicts` は、Related Sections の `conflicts_with` に由来する conflict 候補である。CLI / LLM が Source Specs、Purpose、Core Concept の根拠から「矛盾ではない」または「優先関係が明確」と判断できる場合は warning として残すだけでよい。

一方、LLM が既存根拠だけでは解決できない場合は、`conflict_review_items` に status `pending` の項目を作る。pending conflict は人間判断待ちであり、freshness report は `status = blocked` と `blocking_reasons[] = ["pending_conflict"]` を返す。

Conflict Review Item は、少なくとも次を人間に提示する。

```text
conflict_id
status: pending
severity
source_refs[]
claims[]
why_conflicting
why_llm_cannot_decide
related_sections[]
decision_options[]
recommended_next_action
base_source_hashes[]
valid_scope
```

人間の判断肢は、少なくとも次を含む。

```text
片方の仕様を優先する
両方を満たす条件分岐を指示する
矛盾ではないとして dismiss する
Source Specs の修正が必要として差し戻す
今回は判断保留にする
```

判断保留は conflict を解決しない。status は `pending` のままとし、`/spec-inject` と `/spec-realign` はその conflict を無視して進んではいけない。

人間が判断した Conflict Review Item は、決定内容、理由、判断者が参照した source refs を resolution として保持する。resolution は人間の明示判断であり、`/spec-inject` と `/spec-realign` は一時的な根拠として参照してよい。長期的には Purpose、Core Concept、または Source Specs のどれかへ反映することを推奨する。

SPEC-anchor は resolution を Purpose、Core Concept、Source Specs へ自動反映しない。反映は人間の作業である。resolved Conflict Review Item がまだ Purpose、Core Concept、Source Specs のどれにも反映されていない場合、`/spec-core` は `unreflected_conflict_resolutions` として通知する。`/spec-inject` と `/spec-realign` がその resolution を根拠として使う場合は、「解決済みだが Source Specs 等へ未反映の人間判断」であることを明示する。未反映であること自体は blocker ではない。

resolution は、判断時に参照した `base_source_hashes[]` と有効範囲 `valid_scope` を持つ。対象 Source Specs、Purpose、Core Concept の hash が変わった場合、その resolution は `stale_resolution` になり、制約の根拠として使ってはいけない。`valid_scope = task_scope` の resolution は、その課題内の一時判断であり、後続セッションの恒久根拠にはしない。

人間判断の戻し方は、外部 slash command を増やさず `/spec-core` の conflict decision として扱う。Agent / LLM は Conflict Review Item の要約と判断肢を人間に提示し、人間の回答を構造化した decision payload として CLI に戻す。人間に JSON を直接編集させることは外部契約にしない。

decision payload は少なくとも次を持つ。

```text
conflict_id
decision
reason
selected_option
valid_scope
referenced_source_refs[]
```

`decision` の機械値と状態遷移は次のとおりである。

| decision | 意味 | 遷移 |
|---|---|---|
| `prefer_a` | conflict の片方 A を優先する | `resolved` |
| `prefer_b` | conflict の片方 B を優先する | `resolved` |
| `conditional` | 条件分岐により両方を扱う | `resolved` |
| `dismiss` | 矛盾ではないとして退ける | `dismissed` |
| `needs_source_update` | Source Specs / Purpose / Core Concept の修正が必要 | `pending` |
| `defer` | 今回は判断保留にする | `pending` |
| `task_scope_resolution` | 今回の課題内だけの一時判断にする | `resolved` + `valid_scope = task_scope` |

Conflict 判定は Related Sections 選定後の別 stage とする。対象は `relation_hint = conflicts_with` またはそれに準じる高リスク候補だけであり、全 Section pair を総当たりで LLM 判定しない。実装は複数 conflict pair を chapter や source document 単位で batch 化してよい。

Related Sections に選ばれなかった候補でも、同一 identifier、同一 config / status 名、must / must not / 禁止 / 例外 / required / optional などの衝突しやすい語を共有する pair は、`conflict_pair_max_per_section` の範囲で high-risk pair として conflict 判定 stage に送る。上限により送らなかった pair は diagnostics に残す。

## 8. `/spec-inject`

### 8.1 目的

`/spec-inject` は、Agent / LLM が現在の会話区間と課題を解釈し、SPEC-anchor の保持物を使って今回必要な制約を生成し、会話区間へ注入するためのコマンドである。

このコマンドは課題に対する最終回答を作ることを目的にしない。LLM の注意を、本来の目的、Core Concept、関連 Source Specs、Section Summary、Related Sections、Chapter Key Anchor へ戻すことを目的にする。

会話区間の解釈と中心課題の特定は Agent / LLM の責務である (§5.3)。CLI は会話区間も課題プロンプトも消費しない。Agent / LLM が解釈した課題に基づいて、§8.3 の 4 path から必要な保持物を CLI に問い合わせ、制約を生成する。入力に含まれる会話区間の扱い、生テキスト投入の制限、根拠の区別は §3.4 を参照。

### 8.2 入力

| 入力 | 内容 |
|---|---|
| `.spec-anchor/config.toml` | 対象プロジェクト設定 |
| Purpose | 読み取り専用の上位目的 |
| Core Concept | 人間更新対象のコアコンセプト |
| Qdrant `[retrieval].section_collection` | Section 単位 hybrid retrieval index と payload (source_document_id / source_span / summary / search_keys / identifiers / related_sections / heading_path) |
| `chapter_anchors.json` | LLM 生成の章単位 anchor |
| `conflict_review_items.json` | resolved / dismissed / pending Conflict Review Items |

### 8.3 Agent / LLM が行う作業 (4 path)

Agent / LLM は、課題の性質に応じて次の 4 path を組み合わせて使う。`evidence_origin` の enum (`Purpose` / `Core Concept` / `Source Specs` / `Conflict Review Item`) を 4 path がそれぞれカバーする。各 path は必須ではなく許可で、Agent が選んで使い分ける。

#### path ① Qdrant section-level retrieval

1. 会話区間 / 課題プロンプトから検索キーを選定し、hybrid retrieval を呼ぶ
2. CLI は section_id ranking を返す (top-K、K は config、少し大きめ)
3. 各 hit の payload (heading / summary / search_keys / identifiers) を読み、関連候補を見つける
4. 候補 Section の `related_sections` 配列を辿り、target_section_id を payload lookup で取得 (id 指定の point retrieve、vector 検索ではない)
5. 必要なら Source Specs ファイル本文を Read で確認し、制約根拠を抽出
6. 4 を再帰的に適用 (最大 N hop、N は config)。制約に関係しないと判断できた時点で打ち切り

evidence_origin: `Source Specs`

#### path ② chapter_anchors.json による章単位エントリ

1. 会話区間 / 課題プロンプトから、`chapter_anchors.json` の summary / key_topics / important_sections に基づき関係しそうな章を特定
2. 特定された章配下の Section を path ① と同様に Agentic Search で読み、制約を抽出

evidence_origin: `Source Specs` (章単位の入口、最終 evidence は章配下の Source Specs)

#### path ③ Purpose / Core Concept からの制約抽出

1. `purpose_file` / `concept_file` を Read で全文読み、課題に該当する制約根拠を抽出

evidence_origin: `Purpose` または `Core Concept`

#### path ④ resolved Conflict Review Items の確認

1. `conflict_review_items.json` から `status = resolved` かつ stale でない items を抽出
2. `valid_scope` (global / task_scope) と `resolution.referenced_source_refs` を確認
3. 制約に関係する場合、`evidence_origin = "Conflict Review Item"` として制約に組み込む

evidence_origin: `Conflict Review Item`

#### 8.3.1 path 選択の指針

| 課題タイプ | 主 path | 補強 |
|---|---|---|
| 具体的 API / 識別子 | ① | ③、④ |
| 全体方針 / 抽象的 | ② | ①、③、④ |
| Purpose / Core Concept 直接質問 | ③ | ①、② |
| 過去判断の継続 | ④ | ①、③ |

Agentic Search は Agent / LLM の責務である。CLI は検索結果、payload、章 anchor、Purpose / Core Concept、Conflict Review Items を返すだけであり、探索方針を自律的に決めない。

### 8.4 CLI が提供する操作

CLI は外部契約として次の参照操作を提供する。各 `inject-*` コマンドは内部で freshness gate / pending conflict gate / watcher gate を通す (§3.3 / §2.8 / §6.3)。gate が blocked / failed の場合、各コマンドは Agentic Search を実行せず、停止指示と理由 (`should_stop=true`、`blocking_reasons`、`recommended_next_action`) を返す。Agent は別途事前 probe を実行する必要はない。

| 操作 | コマンド | 戻り値 |
|---|---|---|
| section-level hybrid retrieval | `spec-anchor inject-search "<query>"` | top-K の Section payload (source_document_id / source_section_id / source_span / heading / summary / search_keys / identifiers / related_sections / score) |
| Section payload lookup (related 辿り) | `spec-anchor inject-section "<id>" [<id>...]` | 指定 section_id の payload 一括取得 |
| 章 anchor 取得 | `spec-anchor inject-chapters` | `chapter_anchors.json` の path。Agent は path を `Read` で読み、課題に関連しそうな章を特定する |
| Purpose / Core Concept 取得 | `spec-anchor inject-purpose` | `purpose` (Purpose 全文、短いので注入) + `core_concept_path` (Core Concept の path、Agent が `Read` で必要箇所を抽出) |
| Conflict Review Items 取得 | `spec-anchor inject-conflicts` | `status = resolved` かつ stale でない items |

`spec-anchor inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` には CLI 固有フラグはない。`/spec-realign` の CLI フラグは §9.4 を参照。

### 8.5 通常出力

freshness report の `status = fresh` の場合、`/spec-inject` は Agent / LLM が生成した今回用の制約セットと、その根拠・探索経路の要約を会話へ注入する。

`spec-anchor inject-*` および `spec-anchor realign` の **CLI 出力は内部 JSON** であり、stdout に JSON object を 1 つ出す。人間に見える出力は、Agent CLI 側 (`.claude/commands/spec-inject.md` / `spec-realign.md` および `.codex/skills/spec-anchor/SKILL.md` の template) が CLI の JSON 戻り値を解釈し、ユーザー宛の会話に対して次のような読みやすい構造として整形する。CLI 自身に整形 mode (`--format human` 等) は持たない。

```text
今回守る制約
  - <制約>
    根拠: Purpose / Core Concept / Source Specs
    参照補助: Section Summary / Chapter Key Anchor / Related Sections
    source: <source_document_id / source_section_id / source_span>

今回見るべき対象
  - <Section または topic>
    理由: <なぜ今回関係するか>

関連先として確認したもの
  - <related Section>
    理由: <depends / impacts / related / conflicts など>

採用しなかったもの
  - <候補>
    理由: <今回の課題には遠い / 根拠不足 / 別論点>

不確実性 / 人間確認
  - <確認すべき点>
```

制約セットは、少なくとも次の最小構造を満たす。

```text
constraint
  - statement: 今回守る制約
  - evidence_origin: Purpose | Core Concept | Source Specs | Conflict Review Item
  - evidence_ref: 文書 path、source_section_id、source span、Core Concept の項目、または stale でない resolved conflict_id
  - support_refs: Section Summary / Related Sections / Chapter Key Anchor などの参照補助
  - applicability: 今回の課題でどこに効く制約か
  - uncertainty: 根拠不足、衝突、または人間確認が必要な点
```

Agent / LLM は自由な説明文を出してよいが、制約を提示する場合は `statement`、`evidence_origin`、`evidence_ref` を欠かしてはいけない。

`/spec-inject` は、検索キー、Section Summary、Related Sections だけを根拠として制約を確定してはいけない。制約として使う場合は、Purpose、Core Concept、Source Specs、または解決済み Conflict Review Item の該当箇所を根拠として示す。

制約構造の検証 (`statement` / `evidence_origin` / `evidence_ref` / `support_refs` / `applicability` / `uncertainty` の存在と整合) は **Agent / LLM が自己点検する責務** である。CLI は制約構造を検証しない。Conflict Review Item を根拠にする場合の status / stale_resolution / valid_scope の確認も Agent 側で行う (`spec-anchor inject-conflicts` が resolved + stale でない items に絞って返すので、その範囲だけを採用する)。

### 8.6 停止時出力

freshness report が `status = blocked` かつ `blocking_reasons[] = ["pending_conflict"]` の場合、`/spec-inject` は通常の制約セットを生成しない。人間判断が必要な conflict だけを停止時出力として提示する。

```text
停止理由: pending conflict

人間判断が必要な conflict
  - conflict_id
    severity
    source_refs[]
    claims[]
    why_conflicting
    why_llm_cannot_decide
    decision_options[]
    recommended_next_action
```

freshness report が `status = blocked` で、`blocking_reasons[]` に dirty / stale / watcher 系理由を含む場合、`/spec-inject` は制約生成を行わず、`blocking_reasons[]` と推奨される次アクションを提示する。

## 9. `/spec-realign`

### 9.1 目的

`/spec-realign` は、`/spec-inject` と同じ手順で今回必要な制約を生成し、その制約に従って課題への回答または修正案を作るためのコマンドである。

会話区間の解釈と中心課題の特定は Agent / LLM の責務である (§5.3 / §8.1)。Agent / LLM は会話区間から中心課題を解釈し、特定できない場合は回答生成を進めずに人間に確認を求める。CLI は会話区間も課題プロンプトも消費しない。

### 9.2 動作

```text
/spec-realign
  -> freshness gate
  -> 8.3 と同じ手順で制約を生成する
  -> 生成した制約に従って回答または修正案を作る
  -> RealignResult を出力する
```

### 9.3 Answer 生成契約

LLM は、生成した制約を守って回答する。制約と矛盾する案を出す場合は、その矛盾を隠さず明示し、人間レビューが必要な点として扱う。

`Answer` は、少なくとも次を区別して記述する。

```text
今回守る制約
今回扱う修正候補または検討対象
競合 / 不確実性 / 人間レビューが必要な点
課題プロンプトへの回答または修正案
```

### 9.4 CLI フラグ

`spec-anchor realign` は次の回答候補入力フラグを持つ。回答候補は Agent が §9.3 の 4 区分 (`今回守る制約` / `今回扱う修正候補または検討対象` / `競合 / 不確実性 / 人間レビューが必要な点` / `課題プロンプトへの回答または修正案`) を含むように作成する。制約構造の検証は Agent / LLM の責務 (§8.5 末尾) で、CLI は回答を 4 区分の RealignResult に整形するだけである。

| フラグ | 内容 |
|---|---|
| `--answer <text>` / `--answer-text <text>` / `--agent-answer <text>` | Agent が生成した回答候補の plain text。alias は同義 |
| `--answer-json <json>` / `--agent-answer-json <json>` | Agent が生成した回答候補の JSON object |
| `--answer-file <path>` / `--agent-answer-file <path>` | 回答候補の JSON または plain text のファイル入力 |

## 10. 設定ファイル

### 10.1 設定ファイル配置

プロジェクトごとの設定は `<project_root>/.spec-anchor/config.toml` に置く。親ディレクトリへの自動探索はしない。

```text
<project_root>/
└── .spec-anchor/
    └── config.toml
```

### 10.2 設定項目

`<id>` は `[llm.providers.<id>]` で命名するユーザー定義 provider id (例: `codex`、`claude_typing`、`claude_judge`)。

| Table | Key | 必須性 | 既定値 | 内容 |
|---|---|---|---|---|
| `[sources]` | `include` | 必須 | — | Source Specs として読み込む Markdown ファイルの glob。複数指定可。project-root 相対 |
| `[sources]` | `exclude` | 任意 | `[]` | `include` から除外する glob。複数指定可 |
| `[core]` | `purpose_file` | 必須 | — | Purpose ファイルのパス。SPEC-anchor は自動更新しない |
| `[core]` | `concept_file` | 必須 | — | Core Concept ファイルのパス。人間更新対象 |
| `[context]` | `storage` | 任意 | `.spec-anchor/context` | 生成済み保持物の保存先ディレクトリ |
| `[section]` | `max_heading_level` | 任意 | `4` | Section 化する最大 Markdown heading level。`4` の場合 `#` から `####` までが Section 境界、それ以下は親 Section 本文に含まれる |
| `[section_metadata]` | `summary_enabled` | 任意 | `true` | Section Summary 生成を有効にするか |
| `[section_metadata]` | `search_keys_enabled` | 任意 | `true` | Section Search Keys 生成を有効にするか |
| `[section_metadata]` | `related_sections_enabled` | 任意 | `true` | Related Sections 生成を有効にするか |
| `[chapter_anchor]` | `enabled` | 任意 | `true` | Chapter Key Anchor 生成を有効にするか |
| `[llm.providers.<id>]` | `command` | 必須 | — | 実行する CLI コマンド名または絶対パス (例: `codex`、`claude`)。`SPEC_ANCHOR_FAKE_LLM` が truthy のときは無視される |
| `[llm.providers.<id>]` | `model` | 任意 | — | provider に渡す model 名 (例: `gpt-5.4-mini`、`claude-sonnet-4-6`) |
| `[llm.providers.<id>]` | `effort` | 任意 | — | provider に渡す reasoning effort (例: `low`、`medium`) |
| `[llm.providers.<id>]` | `timeout_sec` | 任意 | `120` | `command` で起動した CLI subprocess 1 attempt あたりの待ち時間 (秒)。この時間を超えると attempt は timeout として失敗扱いになる |
| `[llm.providers.<id>]` | `max_retries` | 任意 | `1` | `command` で起動した CLI subprocess が失敗 (non-zero exit / timeout / schema 違反) した場合の追加 retry 回数。`max_retries = 1` の場合、1 stage 呼び出しあたり最大 attempt 数は初回 1 回 + retry 1 回の計 2 回。すべて失敗するとその stage が `failed` として diagnostics に出力される |
| `[llm.stage_routing]` | `section_metadata` | 任意 | `[llm.providers]` の先頭定義 | section_metadata stage で使う provider id |
| `[llm.stage_routing]` | `related_sections` | 任意 | `[llm.providers]` の先頭定義 | related_sections stage で使う provider id |
| `[llm.stage_routing]` | `conflict_review` | 任意 | `[llm.providers]` の先頭定義 | conflict_review stage で使う provider id |
| `[llm.stage_routing]` | `chapter_key_anchor` | 任意 | `[llm.providers]` の先頭定義 | chapter_key_anchor stage で使う provider id |
| `[retrieval]` | `dense_top_k` | 任意 | `12` | dense retrieval の取得 top-K |
| `[retrieval]` | `sparse_top_k` | 任意 | `20` | sparse retrieval の取得 top-K |
| `[retrieval]` | `rank_fusion` | 任意 | `"rrf"` | dense / sparse の融合方式。現時点では `rrf` (Reciprocal Rank Fusion) のみ受容 |
| `[retrieval]` | `section_collection` | 任意 | `"spec_anchor_section"` | section-level retrieval 用 Qdrant collection 名。1 Section = 1 vector、payload に summary / search_keys / identifiers / related_sections / heading_path を含む |
| `[retrieval]` | `section_dense_threshold` | 任意 | `0.55` | section-level dense 候補の採用最低スコア |
| `[retrieval]` | `section_candidate_top_k` | 任意 | `16` | section-level 候補絞り込み 1 段目の top-K |
| `[retrieval]` | `section_final_top_n` | 任意 | `8` | section-level 候補絞り込み最終 top-N |
| `[embedding]` | `provider` | 必須 | — | embedding provider 種別。標準は `flagembedding` |
| `[embedding]` | `model` | 必須 | — | embedding model 名。標準は `BAAI/bge-m3` |
| `[embedding]` | `dense_enabled` | 任意 | `true` | dense embedding を有効にするか |
| `[embedding]` | `sparse_enabled` | 任意 | `true` | sparse embedding を有効にするか |
| `[vector_store]` | `provider` | 必須 | — | vector store 種別。標準は `qdrant` |
| `[vector_store]` | `url` | 任意 | — | vector store の接続先 URL (例: `http://localhost:6333`) |
| `[limits]` | `section_summary_max_chars` | 任意 | `480` | Section Summary の最大文字数 |
| `[limits]` | `search_keys_max` | 任意 | `32` | Section Search Keys の 1 Section あたり最大個数 |
| `[limits]` | `related_candidate_max_per_section` | 任意 | `32` | Related Sections 候補生成の 1 Section あたり最大個数 |
| `[limits]` | `related_selected_max_per_section` | 任意 | `8` | Related Sections 最終採用の 1 Section あたり最大個数 |
| `[limits]` | `conflict_pair_max_per_section` | 任意 | `8` | conflict 判定 stage に送る pair の 1 Section あたり最大個数 |
| `[limits]` | `llm_batch_max_sections` | 任意 | `8` | 1 LLM 呼び出しでまとめる Section 数の上限 |
| `[limits]` | `llm_batch_max_chars` | 任意 | `12000` | 1 LLM 呼び出しでまとめる総文字数の上限 |
| `[limits]` | `llm_batch_concurrency` | 任意 | `4` | section_metadata / related_sections の batch 並列実行数 (1 = 逐次。Codex Pro 5x / Claude Max 5x 環境は 4-8 推奨) |
| `[watcher]` | `enabled` | 任意 | `false` | watcher を有効にするか。標準テンプレは `true` で配布 |
| `[watcher]` | `interval_ms` | 任意 | `2000` | watcher の polling 間隔 (ミリ秒) |
| `[watcher]` | `debounce_ms` | 任意 | `1000` | 連続変更を 1 回の更新にまとめる debounce 時間 (ミリ秒) |
| `[watcher]` | `stale_lock_ms` | 任意 | `300000` | 古い lock を回収する閾値 (ミリ秒) |
| `[watcher]` | `state_file` | 任意 | — | watcher 状態ファイルのパス。project-root 相対 |
| `[watcher]` | `queue_file` | 任意 | — | watcher キューファイルのパス。project-root 相対 |

`[llm.providers.<id>]` と `[llm.stage_routing]` は `/spec-core` が保持物生成 (section_metadata / related_sections / conflict_review / chapter_key_anchor) で直接 spawn する LLM の設定である。`/spec-inject` / `/spec-realign` の会話区間解釈、Agentic Search、制約生成、回答生成を行う Agent / LLM は Agent CLI 側で動くため、これらの設定の対象外である。

Codex 用 skill と Claude 用 command は `spec-anchor core` を `--llm-provider` 引数なしで実行し、`[llm.stage_routing]` に従って stage 別に provider を選ばせる。`--llm-provider` を明示すると `[llm.stage_routing]` が上書きされ、その provider id が全 stage に適用されるため、provider 障害時の手動 fallback など特別な事情がない限り指定しない。

#### Stage 別 provider routing (`[llm.stage_routing]`)

`/spec-core` の各 stage は認知負荷が異なるため、stage 別に LLM provider を切り替える仕組みを持つ。許可される stage key は次の 4 つに固定する。

| stage | 役割 |
|---|---|
| `section_metadata` | summary / search_keys / identifiers の機械抽出 |
| `related_sections` | candidate 集合からの relation_hint 分類 |
| `conflict_review` | Purpose / Core Concept grounding を伴う矛盾判定 |
| `chapter_key_anchor` | 章単位 summary / key_topics / important_sections の合成 |

stage_routing は明示指定方式であり、次の契約に従う。

- `[llm.providers.<id>]` は少なくとも 1 つ必須。0 個の場合は設定エラーとして reject する。
- `[llm.stage_routing]` の各 stage は任意。未指定の stage は `[llm.providers.<id>]` の先頭定義 (TOML 上の出現順) を使う。`[llm.stage_routing]` 自体が無い、または全 stage 未指定の場合、すべての stage が先頭定義を使う。
- `spec-anchor core --llm-provider <id>` を CLI で明示すると、その provider id が `[llm.stage_routing]` の指定を上書きし、全 stage に適用される。
- 指定された provider が実行失敗 (non-zero exit / timeout / schema 違反) した場合、別 provider に黙って切り替えず、失敗として報告する (silent fallback 禁止)。

stage_routing で参照する provider id は `[llm.providers.<id>]` で定義済みでなければ設定エラーとして reject する。許可外の stage key (例: 誤記の `conflict_reveiw`) も同様に reject する。

初期設定:

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
llm_batch_concurrency = 4   # 1 = 逐次。Pro 5x / Max 5x なら 4-8 推奨

[watcher]
enabled = true
interval_ms = 2000
debounce_ms = 1000
stale_lock_ms = 300000
state_file = ".spec-anchor/state/watch_state.json"
queue_file = ".spec-anchor/state/watch_queue.json"
```

### 10.3 環境変数

既定 (production / 本運用) では、`.spec-anchor/config.toml` の `[llm.providers.<id>]` で指定された実 CLI を子プロセスとして起動し、`[vector_store].url` の Qdrant + FlagEmbedding を使う。`SPEC_ANCHOR_FAKE_*` 系の env var は subsystem を **in-process fake へ切り替える** ための例外指定であり、本運用では設定不要。`SPEC_ANCHOR_DEBUG_*` 系は本運用経路の挙動を変えない観察専用 (set 時のみ追加の append 出力が増える)。

project root に `.env` ファイル (dotenv 形式の `KEY=VALUE` 行) を置くと、`spec-anchor` 起動時に `load_config` が読み込んで `os.environ` に投入する (既存 shell 変数は上書きしない)。shell から直接 export しても、CI が pipeline 設定で export しても、`.env` 経由でも、同じ env として扱われる。雛形は project root の `.env.example` を参照。

| 環境変数 | 役割 |
|---|---|
| `SPEC_ANCHOR_FAKE_LLM` | truthy (`1` / `true` / `yes` / `on`) のとき、`spec-anchor core` は `[llm.providers.<id>]` の `command` を子プロセスとして起動せず in-process FakeLlmProvider を使う。test / smoke で実 codex / claude CLI を呼ばないために使う |
| `SPEC_ANCHOR_FAKE_RETRIEVAL` | truthy のとき、Qdrant + FlagEmbedding BGE-M3 の実構築を伴う test / smoke コード経路を block する。本運用の `/spec-core` 経路 (Qdrant への Section payload 書き込みと hybrid retrieval) は本変数の影響を受けず、`[vector_store].url` の Qdrant と `[embedding].model` の BGE-M3 をそのまま使う。test / smoke で BGE-M3 weight download や Qdrant 接続を避けるために使う |
| `SPEC_ANCHOR_QDRANT_URL` | `spec-anchor-setup-project` / `setup-system` の probe が `.spec-anchor/config.toml` 確定前に Qdrant 接続先を解決するために読む。config が存在する場合は `[vector_store].url` が正本 |
| `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION` | truthy のとき、`spec-anchor core` が起動する LLM 子プロセスの解決済み command と stdin、それぞれの SHA-256 を JSONL append で記録する (1 行 1 invocation)。consecutive run で codex / claude へ渡るバイト列の安定性を観測する用途。本運用経路の挙動は変えず、書き込み失敗は黙って no-op。default 出力先は project root 直下の `.spec-anchor/state/_debug_provider_invocations.jsonl` |
| `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION_PATH` | 上記 debug log の出力先 file path を上書きする。空 / 未設定なら default の `.spec-anchor/state/_debug_provider_invocations.jsonl` を使う。`SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION` が falsy / 未設定のときは本変数を読まない |
| `SPEC_ANCHOR_DEBUG_RELATED_PROMPT` | truthy (`1` / `true` / `yes` / `on`) のとき、`/spec-core` の Related Sections stage が組み立てた prompt の hash と入力 section 集合を JSONL append で記録する (1 行 1 prompt)。prompt 構成が consecutive run で安定しているか観測する用途。本運用経路の挙動は変えず、書き込み失敗は黙って no-op。default 出力先は project root 直下の `.spec-anchor/state/_debug_related_prompts.jsonl` |
| `SPEC_ANCHOR_DEBUG_RELATED_PROMPT_PATH` | 上記 debug log の出力先 file path を上書きする。空 / 未設定なら default の `.spec-anchor/state/_debug_related_prompts.jsonl` を使う。`SPEC_ANCHOR_DEBUG_RELATED_PROMPT` が falsy / 未設定のときは本変数を読まない |

### 10.4 `.gitignore` 推奨設定

`.spec-anchor/config.toml` は対象プロジェクトの設定として管理してよい。一方、生成済み保持物、pending state、cache、tmp、watcher state には Source Specs 由来の抽出中間データや LLM 出力が含まれる可能性があるため、通常は Git 管理しない。

Claude Code 用 command template (`<project>/.claude/commands/spec-*.md`) と Codex 用 skill (`<project>/.codex/skills/spec-anchor/SKILL.md`) は、対象プロジェクトの操作入口であるため Git 管理してよい。Agent 環境の認証情報、ログ、セッション state が同じディレクトリに作られる場合は、それらだけを ignore する。

```gitignore
.spec-anchor/context/
.spec-anchor/cache/
.spec-anchor/state/
.env
```

各 entry の意味:

- `.spec-anchor/context/`: `/spec-core` が生成する人間 / Agent 参照の保持物 (`chapter_anchors.json`、`conflict_review_items.json`)
- `.spec-anchor/cache/`: section_metadata / related_sections / chapter_anchors の LLM 応答キャッシュ
- `.spec-anchor/state/`: 状態管理・鮮度・watcher (`section_manifest.json`、`freshness.json`、`watch_state.json`、`watch_queue.json`)
- `.env`: user 個別の subsystem 切替 (`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` で fake モードへ、`SPEC_ANCHOR_QDRANT_URL` で setup probe の Qdrant 接続先差し替え)。共有用の雛形は `.env.example` を repo に commit する

## 11. エラー契約

本表で `status = failed` と扱う失敗はすべて、`freshness_report.blocking_reasons` に `failed_required_artifact` が積まれ、`freshness_report.status` も `failed` になる。結果として `/spec-inject` と `/spec-realign` は freshness gate (§3.3) で停止し、利用者は復旧 (例: `spec-anchor core --rebuild`、Qdrant 再起動、Source Specs / Purpose / Core Concept の修正など) を行ったうえで `/spec-core` を再実行する必要がある。`/spec-core` 自身は新しい canonical artifact を上書きせず、前回値を残すため、復旧時の比較基準として使える。

外部契約コマンドは次の 6 種類で、本表の各エラー行が「どのコマンドで起きるか」を「対応コマンド」列に明示する。

- `/spec-core` (= `spec-anchor core`)
- `/spec-inject` (= `spec-anchor inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` の総称、§8)
- `/spec-realign` (= `spec-anchor realign`、§9)
- `spec-anchor-watch` (§6.3)
- `spec-anchor-setup-system` (§6.2)
- `spec-anchor-setup-project` (§6.2)

exit code の方針は対応コマンドで非対称である。`/spec-core` / `/spec-realign` / `spec-anchor-setup-project` / `spec-anchor-setup-system` は `status = failed` / `error` / `conflict` のときに exit code 1 を返し、shell スクリプトや CI から失敗を検知できる。`/spec-inject inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` と `spec-anchor-watch` は **exit code 0 固定**であり、停止状態は JSON 戻り値 (`should_stop` / `blocking_reasons` / `status`) で表現する (Agent CLI が exit code を見ずに JSON を parse する責務を持つ)。

| 状態 | 対応コマンド | exit code | 期待動作 |
|---|---|---|---|
| `.spec-anchor/config.toml` が見つからない | `/spec-core` / `/spec-inject` / `/spec-realign` / `spec-anchor-watch` | `/spec-core`: 1、`/spec-realign`: 1、`/spec-inject`: 0 (JSON で報告)、`spec-anchor-watch`: 0 (JSON で報告) | エラー終了し、設定ファイル作成 (`spec-anchor-setup-project`) を促す |
| Purpose が見つからない | `/spec-core` | 1 | エラー終了する |
| Core Concept が見つからない | `/spec-core` | 1 | エラー終了する |
| Source Specs が見つからない | `/spec-core` | 1 | エラー終了する |
| Section Metadata 更新に一部失敗 | `/spec-core` | 0 (`status = degraded` は failed ではない) | 失敗 Section を出力し、必須 artifact が揃う場合は `status = degraded` として扱う |
| Chapter Key Anchor 更新に一部失敗 | `/spec-core` | 1 | 失敗 chapter を出力し、`status = failed` として扱う。canonical `chapter_anchors.json` は更新せず、前回の値を残す |
| Related Sections の retrieval backend に到達できない (Qdrant を期待した設定で初期化失敗) | `/spec-core` | 1 | `status = failed` として扱い、Section Metadata 内の関連先一覧と検索 backend 側の関連先 payload を更新しない。前回の値を残す。Qdrant 未設定の InMemory 構成は対象外 |
| embedding / retrieval index 更新に失敗 | `/spec-core` | 1 | `status = failed` として扱い、古い index を新しいものとして採用しない |
| dirty / stale / watcher 系 blocking reason がある | `/spec-inject` / `/spec-realign` | `/spec-inject`: 0 (JSON で報告)、`/spec-realign`: 0 (`status = blocked` は failed ではない、JSON で報告) | 自動更新せず、watcher の完了、`/spec-core`、または `/spec-core --all` を促して停止する |
| `pending_conflict` だけが blocking reason として残っている | `/spec-inject` / `/spec-realign` | `/spec-inject`: 0 (JSON で報告)、`/spec-realign`: 0 (JSON で報告) | 制約生成 / Answer 生成を行わず、Conflict Review Item と判断肢を提示する |
| watcher running / queued changes が残っている | `/spec-inject` / `/spec-realign` | `/spec-inject`: 0 (JSON で報告)、`/spec-realign`: 0 (JSON で報告) | 制約生成 / Answer 生成を行わず、watcher の完了を待つ |
| Project Setup Script の target が存在しない | `spec-anchor-setup-project` | 1 (status = `error` / `failed`) | 明示オプションなしでは作成せず、作成するかどうかを人間に委ねる |
| Project Setup Script の配置先に既存ファイルがある | `spec-anchor-setup-project` | 1 (status = `conflict`、`--force` で 0 に戻る) | 黙って上書きせず、差分または衝突ファイル一覧を出して停止する。`--force` がある場合だけ更新する |
| System Setup Script の依存ツールが見つからない | `spec-anchor-setup-system` | warning レベル: 0、failed / error レベル: 1 | 失敗または warning として diagnostics に出し、足りない command / package / service を示す |
| System Setup Script の Agent CLI 認識性チェックで Codex skill / Claude command が認識されない | `spec-anchor-setup-system` | 0 (warning のみ、status は `ok` or `degraded`) | warning として diagnostics に出す。setup-project の出力先と Agent CLI version を提示し、手作業対応手順を案内する |

## 12. 外部設計で扱わないこと

本書では次を扱わない。

```text
Section Metadata の内部生成プロンプト
Chapter Key Anchor の内部生成プロンプト
embedding provider の実装
hybrid retrieval の内部 scoring
LLM provider の subprocess 実装
slash command の完全なプロンプト本文
property graph / entity relation graph / hierarchical cluster の構築
```

これらは詳細設計書で定義する。
