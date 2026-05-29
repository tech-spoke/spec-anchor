# SPEC-anchor 外部設計書

本書は SPEC-anchor の外部契約を定義する。ここでは、ユーザーが何を実行できるか、各コマンドが何を保証するか、どの情報を保持するか、Agent / LLM と CLI の責務をどこで分けるか、SPEC-anchor がどのように動作するかを扱う。

内部実装、embedding provider、LLM provider、保存形式、検索アルゴリズム、slash command の具体プロンプトは外部設計の対象外である (§12)。

## 凡例: 検証進捗マーク

本書では、外部から観測可能な振る舞いの一つ一つを検証の単位として扱う。各記述の行頭または表の `確認` 列に次のマークを付けて進捗を管理する。

- `[ ]` 未検証、または production E2E 未通過
- `✅` production E2E 検証済 (定義は下記の通り厳格化)

**`✅` を付与する条件** (2026-05-22 改定):

`✅` は、対応する pytest test が存在し、`evidence_map.jsonl` に `result: "passed"` と `verification_level: "production_e2e_verified"` の両方が記録されている場合に限り付与する。`production_e2e_verified` の定義は `doc/e2eテスト/test_plan.ja.md` §4.2.1 を参照 (要点: real Codex / Claude / Qdrant / BGE-M3 を使い、`SPEC_ANCHOR_FAKE_*` を一切付けず、`/spec-core` → `/spec-inject` → `/spec-realign` の代表経路で artifact が後続 command に正しく渡るところまで通したもの)。

`unit_verified` / `hybrid_verified` / `real_smoke_verified` / `local-service` のみ通過した項目は `✅` にせず `[ ]` のまま残し、進捗は `test_plan.ja.md` §4.2.2 の per-level 列で記録する。fake / hybrid を「検証実装かつ通過」と読み替えて `✅` を付ける運用は禁止する。

マークが付いている記述は、その行 (または段落) が単独で 1 件の検証ケースに対応する。マークが付いていない記述は、説明文 / 用語定義 / 背景情報であり検証の単位ではない。

検証方法は項目によって次のいずれか (テストケース実装時に選ぶ)。

- **入出力比較**: CLI コマンド実行で stdout JSON / exit code を期待値と比較
- **artifact 内容確認**: 生成された artifact ファイル (例: `.spec-anchor/state/core_progress.json`、`chapter_anchors.json`) の field 値を確認
- **Agent 出力文言確認**: Agent CLI が利用者に提示した文言が期待される構造 (§8.5 の 5 セクション等) を満たすか確認
- **tool call trace 監査**: Agent CLI が実行した tool call の連鎖 (例: `spec-anchor inject-search` → `inject-section`) を log から確認

Agent 側の手順 (§8.3 各 path のステップ等) は、ステップごとに個別 `[ ]` を付けつつ、path 全体に対する 1 件の trace 監査チェックも併設する。**ステップ個別 `[ ]` は LLM が手順を省略しないための可視化目的、path 単位 `[ ]` が実際の検証単位** である。

`[ ]` は GitHub Flavored Markdown の task-list 標準 syntax を採用する (別 session の Agent / LLM が legend を読まなくても「未完了タスク」として認識できるため)。`✅` は完了済を視覚的に区別するための絵文字として使用する。

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

- [ ] 標準経路に property graph / entity relation graph / hierarchical cluster を含めない (graph artifact が生成されず、graph traversal 用の CLI 経路が存在しない)。
- [ ] Concept 自動更新、広範な conflict 承認フロー、実行モード分岐を標準経路に含めない。
- [ ] LLM が解決できない conflict は Conflict Review Item として人間判断待ちになり、warning-only で `/spec-inject` / `/spec-realign` が進む経路を持たない。

Section 数が多いプロジェクトでは、`/spec-core --all` の LLM 呼び出しはなお重くなる。実装は、Section hash による incremental update、複数 Section の batch 生成、変更 chapter だけの再生成を基本にする。

主導権は Agent / LLM にある。slash command は Agent / LLM に対して探索手順を指示し、CLI は保持物と検索機能を提供する。CLI は最終判断主体ではない。

### 1.1 方式の分類

SPEC-anchor は、業界標準資料 (`doc/監査/STANDARD_GRAG_PATTERNS.ja.md`) の分類で言えば **Hybrid RAG + lightweight related-section retrieval** に位置づけられる。

| 確認 | 要素 | SPEC-anchor での実装 |
|---|---|---|
| [ ] | Hybrid RAG | Section を単位とした BGE-M3 の dense + sparse vector を Qdrant の `[retrieval].section_collection` で RRF 結合する。これが Source Specs 探索の主経路 (`spec-anchor inject-search`) |
| [ ] | lightweight related-section retrieval | 各 Section に LLM 生成の Section Metadata (Summary / Search Keys / Identifiers / Related Sections) を持たせ、Related Sections は単純な配列として payload に格納する。`spec-anchor inject-section` で id 指定の payload lookup を提供し、Agent が再帰的に辿る |

業界標準資料 §7 で言うところの「property graph」「entity relation graph」「hierarchical cluster」は本方式では**標準経路に含めない** (§1 軽量化方針)。Related Sections は単一の payload field として持ち、graph traversal の代替を Agent の再帰的 lookup に置く。これにより、永続化する構造を最小に抑え、graph 構築・保守のコストを Agent / LLM 側の探索コストに置き換える。

- [ ] Related Sections は単一の payload field として保持され、graph traversal ではなく Agent の再帰的 `inject-section` lookup で辿られる。

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

- [ ] `source_section_id` の形式は `<file_path>#<ordinal>-<heading_slug>` である (生成された全 Section ID をこの正規表現にマッチさせる)。
- [ ] `<ordinal>` は同一 file 内 Section 出現順を 1 始まり 4 桁 zero-padded (`0001` / `0002` / ...) で表す。
- [ ] `<heading_slug>` の正規化規則: 英数字 / アンダースコア / 日本語 (ひらがな・カタカナ・漢字) を保持、それ以外を `-` に置換、小文字化、前後 `-` を除去、空文字列は `section` で代替。
- [ ] `source_section_id` は `[sources].include` に一致する Source Specs 全体で一意である (同一 ID が複数 Section に割り当てられない)。

### 2.5 Section Metadata

Section Metadata は、Source Specs の各 Section に対して `/spec-core` が生成・更新する検索補助情報の総称である。単独で最終根拠にはしない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の根拠を確認する。

### 2.6 Section Search Keys

Section Search Keys は、検索 recall を上げるための **自然言語**の検索キーワードである。コードシンボル / API 名 / CLI コマンド / CLI option / ファイルパス / ALL_CAPS 定数 / PascalCase 型名は含まない。これらは Section Identifiers (§2.6.1) に分離する。

- [ ] Section Search Keys は自然言語の検索キーワードのみであり、コードシンボル / API 名 / CLI コマンド / CLI option / ファイルパス / ALL_CAPS 定数 / PascalCase 型名を含まない。
- [ ] コードシンボル / API 名 / CLI コマンド / CLI option / ファイルパス / ALL_CAPS 定数 / PascalCase 型名は Section Identifiers に分離される。

Section Search Keys は根拠ではない。検索に引っかけるための補助語であり、制約として扱ってはいけない。

- [ ] Section Search Keys は制約根拠として扱われない。

#### 2.6.1 Section Identifiers

Section Identifiers は、Section 本文 + heading に出現する **コードシンボル / 固有技術名**を、正規表現で機械抽出した list である。LLM 判断を経由しない。

- [ ] Section Identifiers は Section 本文 + heading に出現するコードシンボル / 固有技術名から機械抽出され、LLM 判断を経由しない。

含むもの:

- API 名、関数名、CLI コマンド、CLI option (例: `bindContext`, `removeBindContext`, `productStoreGroup.replace`, `--rebuild`)
- ファイルパス、ALL_CAPS 定数、PascalCase 型名、ドット区切り技術名

Section Identifiers は根拠ではない。検索の補助 / 関連候補生成の手がかりであり、制約として扱ってはいけない。

- [ ] Section Identifiers は制約根拠として扱われない。

### 2.7 Related Sections

Related Sections は、ある Section を見たときに一緒に見るべき Section の一覧である (依存先、影響先、同じ方針に属する Section、変更時に確認すべき Section)。full graph relation、無制限の多段 traversal、CLI による自律的な Agentic Search は含まない。

CLI は関連先を保持・返却するが、どこまで辿るかは Agent / LLM が判断する。

Related Sections は最終根拠ではないが単なる一時候補でもない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の該当箇所を根拠として確認する。

Related Sections は **conflict 判定を持たない**。relation_hint は `depends_on / impacts / prerequisite / same_policy / see_also` のみ。`conflicts_with` は本 stage では確定させない。仕様上の矛盾候補抽出は SpecClaim 経路 (§2.11 Conflict Candidate Detection) が独立して扱う。

- [ ] Related Sections の `relation_hint` は `depends_on` / `impacts` / `prerequisite` / `same_policy` / `see_also` のいずれかのみ (artifact 内に他の enum 値が現れない)。
- [ ] Related Sections の `relation_hint` に `conflicts_with` は出現しない (本 stage では確定させない契約)。
- [ ] Related Sections の出力 schema に conflict referral signal field が存在しない (Related Sections は conflict 候補抽出経路から完全に切り離されている)。
- [ ] LLM が矛盾兆候を見つけた場合、Related Sections の選定や schema は変わらない。仕様上の矛盾候補は §2.11 Conflict Candidate Detection が SpecClaim pair から抽出する。

### 2.8 Conflict Review Item

Conflict Review Item は、Purpose、Core Concept、または Source Specs の根拠同士が同時に満たせない疑いがあり、LLM が既存根拠だけでは解消できない場合に、人間へ判断を求める項目である。Conflict Review Item の作成対象は §2.11 Conflict Candidate Detection が `triage.send_to_review = true` と判定した SpecClaim pair に限定する。

含むもの:

- [ ] conflict の対象となる source refs
- [ ] それぞれの主張の要約
- [ ] 矛盾していると判断した理由
- [ ] LLM が解決できない理由
- [ ] 人間に選んでほしい判断肢
- [ ] status

含まないもの (Conflict Review Item の作成・処理が次の振る舞いを引き起こさないことを検証する):

- [ ] Core Concept の自動更新が発生しない
- [ ] Source Specs の自動修正が発生しない
- [ ] LLM による最終裁定 (status の自動 `resolved` 化等) が発生しない

- [ ] status が `pending` の Conflict Review Item が存在する状態で `/spec-inject` / `/spec-realign` を実行すると、制約生成 / 回答生成へ進まず停止する (詳細な停止挙動は §8.6 / §11.1.5 / §11.2 を参照)。

### 2.9 Chapter Key Anchor

Chapter Key Anchor は、章全体の重要テーマ、判断軸、主要 Section への入口を、LLM が章単位で抽象化して生成する artifact である。Agentic Search の章単位エントリポイントとして使う。

output (per chapter、生成された `chapter_anchors.json` の各 chapter entry に次のフィールドが存在することを検証する):

- [ ] `chapter_id`
- [ ] `summary`
  - 補足: 章全体の抽象化された要約
- [ ] `key_topics[]`
  - 補足: 章の重要テーマ
- [ ] `important_sections[]`
  - 補足: 章内で判断軸となる主要 Section の section_id 群
- [ ] `notes[]`
  - 補足: 章全体で守るべき読み方
- [ ] `source_section_ids[]`
  - 補足: 章配下の全 section_id

Chapter Key Anchor は最終根拠ではない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の該当箇所を根拠として確認する。

### 2.10 Agentic Search

Agentic Search は、Agent / LLM が検索結果を見ながら追加検索、関連先参照、根拠確認を繰り返す行動を指す。

Agentic Search は CLI の責務ではない。slash command の説明に探索手順を書き、Agent / LLM がそれに従って必要な検索を行う。

### 2.11 Conflict Candidate Detection

SpecClaim は Source Specs の section から抽出した、仕様上の主張である (例: 「Active sessions must be retained for 30 days.」のような根拠付き宣言)。Section 単位ではなく、section 内の仕様主張単位で矛盾候補を扱うために導入する。

SpecClaim は section_metadata の拡張項目ではない。`.spec-anchor/context/spec_claims.jsonl` を正本として保持し、cache key / freshness / diagnostics は section_metadata と分ける。

SpecClaim record は少なくとも `claim_uid`、`source_section_id`、`claim_text`、`evidence_span`、`target`、`target_aliases`、`claim_hash`、`retrieval` を持つ。`claim_uid` は同じ主張を再抽出しても安定する識別子、`evidence_span` は Source Specs 内の根拠位置、`retrieval` は claim-level retrieval に使う text / dense / sparse / conflict probe 用情報である。

Claim Retrieval は claim-level の専用 retrieval index で、矛盾候補になり得る少数の SpecClaim pair を選ぶ段階である。dense retrieval、sparse retrieval、conflict probe retrieval を融合し、全 SpecClaim pair の総当たりを LLM 判定へ送らない。

Conflict Candidate Detection は、SpecClaim pair を §2.8 Conflict Review Item へ送るべきかを判定する stage である。conflict を確定する stage ではない。Conflict Review Item の作成、人間判断、Source Specs の修正は §2.8 と人間の責務である。

LLM triage は Claim Retrieval で絞った少数の SpecClaim pair に対し、Conflict Review に送る価値があるかだけを判定する。出力は `triage.send_to_review` の bool、`reason`、`confidence` であり、conflict 確定、人間判断必須性、Source Specs 優先関係の決定は LLM triage の責務ではない。

Conflict Candidate Detection の出力名は `conflict_candidate_pairs` である。`triage.send_to_review = true` の SpecClaim pair だけを `.spec-anchor/context/conflict_candidate_pairs.jsonl` に保存し、§2.8 Conflict Review Item の作成対象にする。

- [ ] `/spec-core` は SpecClaim を section 内の仕様主張ごとに抽出し、`.spec-anchor/context/spec_claims.jsonl` に保存する。
- [ ] SpecClaim pair の retrieval (Claim Retrieval) は claim-level の専用 retrieval index を使う。全 claim pair を LLM 判定の対象にしない。
- [ ] LLM triage は Claim Retrieval で絞った少数 claim pair に対し、Conflict Review に送る価値があるかだけを判定する (`send_to_review` の bool、`reason`、`confidence`)。conflict 確定、人間判断必須性、Source Specs 優先関係の決定は LLM triage の責務ではない。
- [ ] `triage.send_to_review = true` の SpecClaim pair だけが §2.8 Conflict Review Item の作成対象になる。Related Sections の relation_hint や旧 Related Sections 由来 pair は対象にしない。
- [ ] Conflict Candidate Detection の出力は `.spec-anchor/context/conflict_candidate_pairs.jsonl` に保存される (Conflict Review に送る価値があると判定された claim pair の集合)。
- [ ] SpecClaim 抽出に失敗した section がある場合、Conflict Candidate Detection は完全成功として扱わない (`partial_success`)。失敗 section は CoreResult diagnostics に出力される。
- [ ] fake 用テストや最小起動確認だけでは、SpecClaim 抽出と Conflict Candidate Detection の実装完了とは扱わない。実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う経路で未確認の範囲は、未完了 TODO として報告する。

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

- [ ] Section 分割は `[section].max_heading_level` 以下の Markdown 見出しを境界として行う。
- [ ] `[section].max_heading_level` より深い見出しは独立 Section にならず、直近の親 Section 本文に統合される。
- [ ] `[section].max_heading_level` のデフォルト値は `4` である (設定省略時の挙動)。

例 (`max_heading_level = 4` の場合):

```text
## Feature                        -> Section
### Field group                   -> Section
#### Image upload                 -> Section
##### Internal helper             -> 親 Section の本文に統合
```

### 3.2 保持物を生成する

`/spec-core` は Source Specs を読み、Section Metadata、Related Sections、SpecClaims、Conflict Candidate Pairs、Chapter Key Anchor、Source Retrieval Index、Conflict Review Items を生成する (§4 保持物一覧、§7 詳細契約)。

`/spec-core` は Section hash に基づいて変更された Section だけを更新する incremental update を基本とする。`--all` flag で LLM 由来 cache をクリアして再評価できる。`--rebuild` flag で Source Retrieval Index の Qdrant collection を全再構築する。

Purpose と Core Concept は人間が更新する。SPEC-anchor はこれらを自動更新しない (§5.1 Human の責務)。

- [ ] `/spec-core` は Section Metadata / Related Sections / SpecClaims / Conflict Candidate Pairs / Chapter Key Anchor / Source Retrieval Index / Conflict Review Items を生成する (各 artifact の所在は §4.1)。
- [ ] `/spec-core` は Section hash を比較し、変更があった Section のみを更新する (incremental update がデフォルト動作)。
- [ ] `/spec-core --all` 実行時、LLM 由来 cache がクリアされて全 Section が再評価される。
- [ ] `/spec-core --rebuild` 実行時、Source Retrieval Index の Qdrant collection が削除・再作成される。
- [ ] `/spec-core` は Purpose / Core Concept ファイルを更新しない (人間管理対象)。

### 3.3 保持物の鮮度を保つ

`/spec-inject` (各 `inject-*` サブコマンド: `inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts`) と `/spec-realign` は、保持物が最新でない場合は停止し、理由と対処方法を表示する (freshness gate)。各コマンドは内部で gate を通すので、Agent が事前に別の probe コマンドを呼ぶ必要はない。

| 確認 | 状態 | `/spec-inject` / `/spec-realign` の動作 | 対処 |
|---|---|---|---|
| [ ] | 保持物は最新 | 続行する | — |
| [ ] | Source Specs が変更されたが `/spec-core` で更新されていない | 停止する | `/spec-core` を実行する |
| [ ] | `spec-anchor-watch` が実行中、または未処理の変更が残っている | 停止する | watcher の完了を待つ |
| [ ] | 人間判断待ちの Conflict Review Item がある | 停止する | Conflict Review Item に判断を返す |
| [ ] | 一部の保持物の生成に失敗している | 停止する | `/spec-core --all` で再生成する |
| [ ] | 一部の保持物が欠けているが必須分は使える | warning を表示し続行できる | 必要なら `/spec-core` で補完する |

- [ ] Source Specs の変更と未解決 Conflict が同時にある場合、まず `/spec-core` で保持物を更新する経路に誘導される (更新後に残る Conflict のみが人間判断対象として `pending_conflict_items` に残る)。
- [ ] Source Specs / Purpose / Core Concept の変更後に `/spec-core` または `spec-anchor-watch` が保持物を更新した場合、SPEC-anchor は既存 pending Conflict Review Item を現在の source hash と conflict evaluation 結果で再評価する。根拠 source の hash が変化した、または根拠 source ref が削除された既存 pending item について、同じ conflict pair が non-pending 判定になるか、現在の conflict candidate から消えた場合、`/spec-core` はその item を `status="dismissed"`、`resolution.decision_origin="auto_source_update"` として blocker から外す。source hash が変わっていない pending item は、LLM judge の再判定だけでは自動解除しない。
- [ ] `/spec-inject` / `/spec-realign` は `/spec-core` を自動実行しない (保持物更新はユーザーの明示実行または `spec-anchor-watch` 経由)。
- [ ] `spec-anchor-watch` は 1 回の更新サイクルで処理する Source Specs の範囲を開始時点で固定し、更新中に追加された変更は次回サイクルへ回す。
- [ ] `spec-anchor-watch` 更新中および未処理変更が残っている間、`/spec-inject` / `/spec-realign` は停止する。

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

- [ ] `/spec-inject` は Source Specs 本文 / Core Concept / Chapter Key Anchor を無条件に LLM コンテキストへ丸ごと投入しない (snippet 単位 / 必要箇所のみ Read される)。
- [ ] `spec-anchor inject-chapters` の戻り値は `chapter_anchors.json` の path であり、Agent が `Read` で必要箇所を抽出する経路を取る (全文を CLI が直接返さない)。
- [ ] `spec-anchor inject-purpose` の戻り値は Purpose 全文 (`purpose` field) + Core Concept の path (`core_concept_path`) である (Purpose は短いため全文注入、Core Concept は path 経由)。

Search Keys は根拠にしない。Section Summary と Chapter Key Anchor は検索・理解の補助であり、制約として採用する場合は Purpose、Core Concept、Source Specs、または解決済み Conflict Review Item の根拠を確認する。

全文を最終コンテキストとして扱うのは、ユーザーが明示的に全文レビューを求めた場合に限る。

### 3.5 回答を生成する

`/spec-realign` は、`/spec-inject` と同じ手順で今回必要な制約を生成し、その制約に従って課題への回答または修正案を作るためのコマンドである (§9 詳細契約)。

`/spec-realign` も §3.4 と同じ Conversation Context および生テキスト投入の制限に従う。LLM は、生成した制約を守って回答する。制約と矛盾する案を出す場合は、その矛盾を隠さず明示し、人間レビューが必要な点として扱う。

- [ ] `/spec-realign` は §3.4 と同じ Conversation Context および生テキスト投入の制限 (Source Specs / Core Concept / Chapter Key Anchor を無条件に丸ごと注入しない) に従う。
- [ ] `/spec-realign` の回答案が生成された制約と矛盾する場合、Agent はその矛盾を「競合 / 不確実性 / 人間レビューが必要な点」セクションに明示する (矛盾を隠した回答を出さない)。

## 4. 保持物

SPEC-anchor は、次の情報を保持する。

| 確認 | 保持物 | 更新主体 | 役割 |
|---|---|---|---|
| [ ] | Purpose | 人間 | 本来の目的。ビジネスゴール、UX の根幹、システムが存在する理由 |
| [ ] | Core Concept | 人間 | 全体の判断軸、承認済みの設計原則 |
| [ ] | Section Summary | `/spec-core` | 各 Section が何について書かれているかを示す |
| [ ] | Section Search Keys | `/spec-core` | 自然言語で Section を検索するためのキーワード |
| [ ] | Section Identifiers | `/spec-core` | Section 本文に出現するコードシンボル / 固有技術名の機械抽出リスト |
| [ ] | Related Sections | `/spec-core` | 一緒に見るべき Section、依存・影響・関連先 (typed graph) |
| [ ] | SpecClaims | `/spec-core` | Source Specs から抽出した仕様上の主張 |
| [ ] | Conflict Candidate Pairs | `/spec-core` | Claim Retrieval と LLM triage で Conflict Review に送る価値があると判定した SpecClaim pair |
| [ ] | Conflict Review Items | `/spec-core` / 人間 | LLM が解決できない仕様 conflict の人間判断待ち項目 |
| [ ] | Chapter Key Anchor | `/spec-core` | 章全体の重要テーマ、判断軸、主要 Section への入口 |
| [ ] | Source Retrieval Index | `/spec-core` | Source Specs を Section 単位で hybrid retrieval するための index |

- [ ] Purpose / Core Concept は SPEC-anchor が自動更新しない (人間管理対象、`/spec-core` 実行で書き換えられない)。
- [ ] SPEC-anchor は Core Concept 乖離通知を提供しない (Source Specs 進化に伴う Core Concept 陳腐化は自動検出・通知の対象外)。

### 4.1 保持物の物理配置

保持物は責務ごとに 3 つの保存先に分離する。

**検索管理 (Qdrant `[retrieval].section_collection`、default `spec_anchor_section`)**:

- [ ] Qdrant section collection の payload には `source_document_id` / `source_span` / Section Summary / Section Search Keys / Section Identifiers / Related Sections / `heading_path` が格納されている。
- [ ] 1 Section が 1 Qdrant point (vector) に対応する (1 Section が複数 vector に分割されない、chunk 分割した別 collection を作らない)。
- [ ] Source Retrieval Index は section-level の Qdrant collection そのものである (Source Specs を chunk 分割した別 collection を持たない)。
- [ ] Qdrant の point id は `source_section_id` から生成した UUID5 文字列である。
- [ ] UUID5 生成の namespace は固定値 `b1d5535d-3e52-5430-af3e-ddd879e6cb19` である (一度採用したら変更しない、Section が並べ替えられても同じ `source_section_id` は同じ point id に対応し続ける)。
- [ ] 1 Section の embedding 入力 text は、`heading_path` (` / ` で結合)、Section Summary、Section Search Keys (上限 8 件、半角空白で結合)、Section Identifiers (上限 8 件、半角空白で結合) を ` | ` で並べた text である。
- [ ] Section Search Keys / Section Identifiers の embedding 入力への投入上限は各 8 件である (9 件目以降は embedding 入力に含まれない)。
- [ ] Source Specs 本文 (raw body) は embedding 入力に含まれない (raw body が embedding 計算対象から除外される)。
- [ ] Qdrant claim collection (`[retrieval].claim_collection`、default `spec_anchor_claim`) は claim-level retrieval 用であり、1 SpecClaim が 1 Qdrant point (vector) に対応する。

Qdrant を期待した設定で Related Sections 用の retrieval backend を初期化できなかった場合、`/spec-core` は次のように振る舞う:

- [ ] **データ保持**: payload 内の関連先と Section Metadata 側の関連先一覧を更新せず、前回値を残す。
- [ ] **status 報告**: `related_sections_status: "failed"` を返し、`failed_required_artifacts` に `related_sections` を追加する。`freshness_report.blocking_reasons` に `failed_required_artifact` が積まれ、`freshness_report.status` と `CoreResult.status` はともに `failed` になる。
- [ ] **下流の停止**: 後続の `/spec-inject` / `/spec-realign` は freshness gate (§3.3) で停止し、`spec-anchor core --rebuild` を実行する手順が利用者に提示される。

**外部契約として人間 / Agent が参照する artifact (`.spec-anchor/context/`)**:

- [ ] Conflict Review Items は `.spec-anchor/context/conflict_review_items.json` に格納される (git 追跡対象)。
- [ ] Chapter Key Anchor は `.spec-anchor/context/chapter_anchors.json` に格納される。
- [ ] Chapter anchor を生成できない chapter があった場合、`.spec-anchor/context/chapter_anchors.json` は更新されず前回の値が残る (canonical artifact の data 消失防止)。
- [ ] SpecClaim は `.spec-anchor/context/spec_claims.jsonl` に格納される (JSONL 形式、section 単位ではなく claim 単位の record)。
- [ ] Conflict Candidate Pair (Conflict Review に送るべきと判定された claim pair) は `.spec-anchor/context/conflict_candidate_pairs.jsonl` に格納される。
- [ ] Claim-level retrieval 用の materialized view は、初期実装では `spec_claims.jsonl` 内の `retrieval` field に保持する。将来分離する場合の置き場所は `.spec-anchor/context/spec_claim_retrieval_index.jsonl` とする (初期実装では生成されない)。

**状態管理 / 鮮度判定 / watcher 動作状態 (`.spec-anchor/state/`)**:

- [ ] Section の差分検出と監査用 metadata は `.spec-anchor/state/section_manifest.json` に格納される。
- [ ] `section_manifest.json` の各 Section エントリには、Source Specs 本文の hash、embedding 入力 text の fingerprint、Qdrant payload の fingerprint が記録される (本文が同じでも検索補助情報 / payload が変わった Section を次回 `/spec-core` が検出可能)。
- [ ] 保持物全体の鮮度状態は `.spec-anchor/state/freshness.json` に格納される (watcher の background update 結果を `/spec-inject` / `/spec-realign` が読む通信媒体)。
- [ ] watcher の polling state は `[watcher].state_file` で指定された path (既定 `.spec-anchor/state/watch_state.json`) に格納される。
- [ ] watcher の未処理キューは `[watcher].queue_file` で指定された path (既定 `.spec-anchor/state/watch_queue.json`) に格納される。
- [ ] Source Retrieval Index の冪等判定用状態は `.spec-anchor/state/retrieval_index_state.json` に格納される (前回 upsert 時の section 集合 hash 指紋 + embedding / retrieval 設定指紋を記録)。
- [ ] `retrieval_index_state.json` の前提が崩れた場合 (ファイル不在 / 指紋不一致 / Qdrant collection 不在) は通常の upsert 経路に fallback する。
- [ ] Related Sections 冪等判定用状態は `.spec-anchor/state/related_sections_state.json` に格納される (前回 Related Sections 生成時の section 集合 hash + candidate generation / LLM selection 設定指紋を記録)。
- [ ] `related_sections_state.json` の前提が崩れた場合は通常の生成経路に fallback する。
- [ ] SpecClaim 抽出の冪等判定用状態は `.spec-anchor/state/spec_claims_state.json` に格納される (前回 SpecClaim 抽出時の section 集合 hash 指紋 + 抽出設定指紋 + claim uid / hash / retrieval hash 集合を記録)。
- [ ] Conflict Candidate Detection (Claim Retrieval + LLM triage) の冪等判定用状態は `.spec-anchor/state/conflict_candidate_pairs_state.json` に格納される (前回 SpecClaim 集合指紋 + claim retrieval 設定指紋 + LLM triage 設定指紋 + candidate uid 集合 + truncation diagnostics を記録)。
- [ ] `spec_claims_state.json` または `conflict_candidate_pairs_state.json` の前提が崩れた場合は通常の生成経路に fallback する (該当 section の SpecClaim を再抽出するか、影響範囲の claim pair の retrieval / triage を再実行する)。

**LLM 応答 cache (`.spec-anchor/cache/`)**:

- [ ] section_metadata / related_sections / spec_claims / conflict_candidate_triage / chapter_anchors の LLM 応答が `.spec-anchor/cache/` 配下にキャッシュされる。

**正本ファイル (artifact 化しない)**:

- [ ] Purpose / Core Concept は `[core].purpose_file` / `[core].concept_file` で指定された file の本文をそのまま正本として扱い、SPEC-anchor は別 artifact 化しない (`.spec-anchor/` 配下に Purpose / Core Concept のコピーや再生成 artifact が作られない)。

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

- [ ] `.spec-anchor/config.toml` を読み込み、設定値で動作する。
- [ ] Source Specs の Section hash を管理し、差分検出に利用する (`section_manifest.json`)。
- [ ] Section Metadata を生成・保持する (`/spec-core`)。
- [ ] SpecClaims を生成・保持する (`spec_claims.jsonl`)。
- [ ] Conflict Candidate Pairs を生成・保持する (`conflict_candidate_pairs.jsonl`)。
- [ ] Conflict Review Item を生成・保持する (`conflict_review_items.json`)。
- [ ] Chapter Key Anchor を生成・保持する (`chapter_anchors.json`)。
- [ ] Source Retrieval Index を生成・保持する (Qdrant section collection)。
- [ ] freshness を判定する (`freshness.json` を生成)。
- [ ] Agent / LLM が渡した検索キーに対して検索結果を返す (`spec-anchor inject-search`)。
- [ ] 指定された Section payload を返す (`spec-anchor inject-section`)。

CLI / SPEC-anchor は次を担当しない (negative test):

- [ ] 会話区間を最終解釈しない (CLI が会話 transcript を引数として受理しないことで検証)。
- [ ] Agentic Search の探索方針を自律的に決めない (自動探索 / 多段 traversal の CLI コマンドが存在しない)。
- [ ] 今回の課題に必要な制約を最終生成しない (`spec-anchor inject-*` (`inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts`) は retrieval payload / 章 anchor path / Purpose 全文 / Conflict Review Item 一覧を返すのみで、constraint statement の最終生成は Agent / LLM の責務である。CLI 出力に fabricated な `constraints[]` / `statement` field が現れない)。
- [ ] conflict を人間抜きで最終裁定しない (`pending` Conflict Review Item の status を CLI が自動 `resolved` 化しない)。
- [ ] Answer を自由生成しない (CLI は `spec-anchor realign --answer-json '<json>'` で Agent から受け取った answer の整形のみ行い、独自に answer 本文を生成しない)。
- [ ] Purpose / Core Concept を自動更新しない (`/spec-core` 実行で `purpose_file` / `concept_file` が書き換えられない)。

## 6. コマンド体系

SPEC-anchor は、ユーザー向け slash command、Source Specs 変更を background で処理する watcher process、導入を支援する setup script を提供する。

| 確認 | コマンド | 目的 | 詳細 |
|---|---|---|---|
| [ ] | `/spec-core` | 保持物を生成・更新する | §7 |
| [ ] | `/spec-inject` | 課題に対する制約を生成する (回答は出さない) | §8 |
| [ ] | `/spec-realign` | 制約を生成し、課題に回答する | §9 |
| [ ] | `spec-anchor-watch` | Source Specs 変更を監視し background で更新する | §6.3 |
| [ ] | `spec-anchor-setup-system` | 外部依存の導入状態を確認する | §6.2.1 |
| [ ] | `spec-anchor-setup-project` | プロジェクトに設定と Agent 入口を配置する | §6.2.2 |

### 6.1 Agent 別 command / skill 入口

SPEC-anchor は、同じ CLI 契約を、各 Agent CLI が認識する入口形式で提供する。

| 確認 | Agent 環境 | 入口形式 | 配置先 |
|---|---|---|---|
| [ ] | Claude Code / Claude CLI | command template | `<project>/.claude/commands/` |
| [ ] | Codex CLI | skill (SKILL.md) | `<project>/.codex/skills/spec-anchor/` |

- [ ] 入口形式は Agent CLI ごとに固定であり、利用者が `--agent` 等で別形式を選んでも上記マッピングに従って配置される (Claude 環境に skill、Codex 環境に command template を配置する経路を持たない)。

### 6.2 Setup Script

本書でいう setup script は、実行時の検索・制約生成ではなく、SPEC-anchor を使い始めるための配置と検証を行う補助コマンドである。

#### 6.2.1 System Setup Script

SPEC-anchor の動作に必要な外部依存が揃っているかを確認する。

```
spec-anchor-setup-system
```

入力: なし (インストール済み環境を対象とする)

確認対象:

- [ ] SPEC-anchor CLI が実行可能か (`spec-anchor` console script が PATH 上に存在し起動する)。
- [ ] embedding provider (FlagEmbedding BGE-M3) が読み込めるか (`FlagEmbedding` package を import 可能で BGE-M3 model を初期化できる)。
- [ ] vector store (Qdrant) に接続できるか (`--qdrant-url` で指定された endpoint に HTTP 接続可能)。
- [ ] Agent CLI (Codex / Claude) が利用可能か (`codex` / `claude` console script が PATH 上に存在し version を返す)。

出力: 結果を JSON で標準出力に出す。

- [ ] 全て揃っている場合: stdout JSON の `production_readiness.status` が `"ready"` になる。
- [ ] 不足がある場合: `production_readiness.status` が `"blocked"`、不足理由が `diagnostics[]` に含まれる。

- [ ] exit code: 常に 0 (warning level)。`status` が `"error"` / `"failed"` の場合のみ非 0。`production_readiness.status="blocked"` は exit code 0 で返す。

オプション:

- [ ] `--check-only`: 確認のみ行い、ファイル / 設定への変更を一切しない (`.spec-anchor/` や config への書き込みが発生しない)。
- [ ] `--qdrant-url <url>`: Qdrant 接続先を指定。省略時の default は `http://localhost:6333`。
- [ ] `--run-smoke`: Agent CLI 認識性の smoke probe を実行する。`agent_cli_entries` に `project_skill_path` / `project_command_path` が追加される。認識失敗は `production_readiness.blocking_reasons` に含めず warning 扱い。

- [ ] System Setup Script は対象プロジェクトの Source Specs / Purpose / Core Concept / 生成済み保持物を変更しない (実行前後で `docs/spec/`、`docs/SPEC-anchor/core/`、`.spec-anchor/context/` の内容が一致する)。

#### 6.2.2 Project Setup Script

対象プロジェクトに SPEC-anchor の設定ファイルと Agent 入口を配置する。

```
spec-anchor-setup-project --target <project-root>
```

入力:

| 確認 | オプション | 既定 | 内容 |
|---|---|---|---|
| [ ] | `--target <path>` | `.` (カレントディレクトリ) | プロジェクトルート |
| [ ] | `--agent <codex\|claude\|both>` | `both` | Agent 入口の配置先。`claude` は `<target>/.claude/commands/` に command template、`codex` は `<target>/.codex/skills/spec-anchor/` に skill を配置 |
| [ ] | `--dry-run` | — | 作成・更新予定を表示するだけで変更しない |
| [ ] | `--force` | — | 既存ファイルの上書きを許可する |
| [ ] | `--no-init-core-files` | — | Purpose / Core Concept の雛形を作成しない |

処理:

- [ ] `.spec-anchor/config.toml` と `.spec-anchor/.gitignore` を作成する (未存在時)。
- [ ] Purpose / Core Concept の雛形を作成する (未存在時、`--no-init-core-files` 指定時は抑止)。
- [ ] `--agent` 値に応じて Claude command template と Codex skill を `<target>` 配下に配置する (`claude` のみ / `codex` のみ / `both`)。

- [ ] 出力: 結果を JSON で標準出力に出す。exit code は成功なら 0、失敗なら非 0。

安全性:

- [ ] 既存ファイルがある場合は差分を示して停止する (`--force` 指定時のみ上書き)。
- [ ] `/spec-core` を自動実行しない (setup 完了後、`.spec-anchor/state/` や `.spec-anchor/context/` 配下に保持物が生成されていない)。

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

| 確認 | オプション | 既定 | 内容 |
|---|---|---|---|
| [ ] | `--once` | — | 1 回だけ scan して終了する (poll ループに入らない) |
| [ ] | `--interval-sec <秒>` | 2.0 | 変更がないときの poll 間隔 |
| [ ] | `--debounce-sec <秒>` | 1.0 | 変更検知後、update を開始するまでの待ち時間 (連続変更をまとめる) |
| [ ] | `--stale-lock-sec <秒>` | 300 | lock file がこの秒数を超えたら stale とみなして回収する |
| [ ] | `--max-runs <回数>` | 無制限 | 指定回数だけ update したら終了する |

- [ ] 出力: 1 つの JSON object を標準出力に出す。object 内に `cycles[]` 配列を持ち、各要素が 1 update サイクルの CoreResult 相当の結果を含む。`--once` の場合は `cycle_count=1`。top-level に集計情報 (`cycle_count` / `run_count` / `freshness_report` / `settings` ほか) が付く。
- [ ] watcher 実行中は freshness gate が `status = blocked` (`watcher_running`) になり、`/spec-inject` と `/spec-realign` は停止する (§3.3)。

## 7. `/spec-core [--all|-a]`

### 7.1 目的

`/spec-core` は、Purpose / Core Concept 以外の保持物を生成・更新するためのコマンドである。

```text
/spec-core
  = Section hash に基づく incremental update。LLM cache と embedding を hash 一致時に再利用

/spec-core --all
  = LLM 由来 cache (section_metadata / related_sections / spec_claims / conflict_candidate_triage / chapter_anchors) をクリアして再評価
    embedding は決定論的なので hash 一致時に再利用 (時間と計算資源を節約)

/spec-core --rebuild
  = 上記に加え、Qdrant spec_anchor_section collection を drop + recreate
    embedding 破損や schema 移行など vector store 再構築が必要な場合に使う
```

| 確認 | flag | LLM 由来 cache (section_metadata / related_sections / spec_claims / conflict_candidate_triage / chapter_anchors) | embedding (Qdrant section collection) |
|---|---|---|---|
| [ ] | (none) | reuse (hash 一致時) | reuse (hash 一致時) |
| [ ] | `--all` | clear → 再生成 | reuse (hash 一致時) |
| [ ] | `--rebuild` | clear → 再生成 | full recreate (collection 再作成) |

- [ ] `--rebuild` は `--all` を含意する (両方の効果が同時に発火し、`--all` を別途指定する必要がない)。
- [ ] `/spec-core` は `.spec-anchor/config.toml` で指定された LLM provider / embedding provider / vector store provider をそのまま使い、別 provider に黙って切り替えない (指定 provider 失敗時は失敗として報告)。

### 7.2 入力

`/spec-core` は次の artifact / 設定を入力として消費する。各行は「artifact の内容を変更すると CLI 出力 / 生成物が対応して変化する」または「CLI の tool call / file Read trace に該当 artifact への参照が観測される」ことで検証する。

| 確認 | 入力 | 内容 |
|---|---|---|
| [ ] | `.spec-anchor/config.toml` | 対象ソース、Purpose、Core Concept、保持物の保存先、LLM / embedding 設定 |
| [ ] | Source Specs | `sources.include` で指定された仕様ファイル |
| [ ] | Purpose | `core.purpose_file` で指定されたファイル。読み取り専用 |
| [ ] | Core Concept | `core.concept_file` で指定されたファイル。人間更新対象 |

`spec-anchor core` の CLI フラグ:

| 確認 | フラグ | 内容 |
|---|---|---|
| [ ] | `--all` / `-a` | LLM 由来 cache (section_metadata / related_sections / spec_claims / conflict_candidate_triage / chapter_anchors) をクリアして再評価する。embedding は hash 一致時に再利用 |
| [ ] | `--rebuild` | `--all` を含意し、さらに Qdrant `spec_anchor_section` collection を drop + recreate する。embedding 破損や schema 移行時に使う |
| [ ] | `--verify-index` | Source Retrieval Index の Qdrant collection に保持されている内容が、現在の Section の hash と一致するかを能動検証する。不整合を見つけた場合、retrieval_index_status を failed にして停止指示を表示する。自動修復はしない。 |
| [ ] | `--llm-provider <id>` | `[llm.stage_routing]` を上書きし、指定した provider id を全 stage に適用する。Codex skill / Claude command は通常指定しない |
| [ ] | `--decision-json <json>` | pending Conflict Review Item に対する判断結果を JSON で渡す |
| [ ] | `--decision-file <path>` | pending Conflict Review Item に対する判断結果を JSON ファイルから読み込む |

### 7.3 動作

通常実行では、Section hash に基づいて変更された Source Specs だけを中心に保持物を更新する。

ステップ個別チェック (CLI 手順遵守の可視化):

```text
[ ] /spec-core
      [ ] Source Specs の Section manifest を作る
      [ ] Section hash を比較する
      [ ] 変更 Section の Section Summary を更新する
      [ ] 変更 Section の Section Search Keys を更新する
      [ ] Source Retrieval Index を更新する
      [ ] 関連候補を広く集め、LLM が Related Sections を理由付きで選ぶ
      [ ] 変更 Section の SpecClaim を抽出する
      [ ] Claim Retrieval で候補 SpecClaim pair を絞る
      [ ] LLM triage で Conflict Review に送る pair を判定する
      [ ] LLM triage が送付対象にした pair から、LLM が解決できない conflict を Conflict Review Item として記録する
      [ ] 影響する Chapter Key Anchor を更新する
      [ ] CoreResult を出力する

[ ] /spec-core --all
      [ ] Source Specs を全件読み込む
      [ ] Section Summary を LLM 再生成する (cache 無視)
      [ ] Section Search Keys を LLM 再生成する (cache 無視)
      [ ] Source Retrieval Index は hash 一致時に reuse (embedding は決定論的)
      [ ] Related Sections を LLM 再 typing する (pair cache 無視)
      [ ] SpecClaim を LLM 再抽出する (cache 無視)
      [ ] Claim Retrieval と LLM triage を再実行する
      [ ] LLM triage が送付対象にした pair から、LLM が解決できない conflict を Conflict Review Item として記録する
      [ ] Chapter Key Anchor を再生成する
      [ ] CoreResult を出力する

[ ] /spec-core --rebuild
      [ ] --all と同じ手順で LLM 由来 cache を再評価する
      [ ] Source Retrieval Index を Qdrant collection ごと full recreate する
```

- [ ] **`/spec-core` 実行の trace 監査** (検証単位): `.spec-anchor/state/core_progress.json` の `stages[]` に上記ステップが順に記録され、各 stage の `status` / `elapsed_sec` / `action` / `diagnostics` で観測できる。

- [ ] `/spec-core` 実行中 Purpose / Core Concept ファイルは読み取り専用として扱われ、書き換えられない (実行前後で `purpose_file` / `concept_file` の内容が一致する)。
- [ ] `spec-anchor-watch` が呼び出す core 更新は `/spec-core` slash command の外部実行ではなく、watcher process 内部の background execution として `spec-core` 相当の incremental update が実行される (Agent CLI を起動しない)。

### 7.4 出力

`/spec-core` は次を出力する。CoreResult の stdout JSON に次のフィールドが存在することを検証する。

```text
CoreResult
  [ ] status: updated | degraded | failed | error
  [ ] mode: incremental | full
  [ ] updated_sources
  [ ] skipped_sources
  [ ] failed_sources
  [ ] failed_sections
  [ ] updated_sections
  [ ] regenerated_chapter_anchors
  [ ] retrieval_index_status
  [ ] related_sections_status
  [ ] potential_conflicts
  [ ] spec_claims_status
  [ ] conflict_candidate_pairs_status
  [ ] conflict_review_items
  [ ] pending_conflict_count
  [ ] auto_dismissed_conflict_count
  [ ] auto_dismissed_conflict_ids
  [ ] unreflected_conflict_resolutions
  [ ] stale_resolution_count
  [ ] freshness_report
  [ ] warnings
```

`retrieval_index_status` は Source Retrieval Index の最終状態を示す。次のいずれかの値を取る。

- [ ] `success`: 今回 `/spec-core` が retrieval index に upsert を実行し、index は最新の section 集合と設定を反映している。
- [ ] `skipped`: retrieval index 機能が `[embedding]` / `[vector_store]` の設定で無効化されている (例: `embedding.provider != "flagembedding"`)。Agent / LLM 側は in-memory retrieval にフォールバックする。
- [ ] `skipped_unchanged`: 入力 (Source Specs の section 集合と内容、embedding / retrieval 設定の指紋) が前回 `/spec-core` 実行時と完全に一致した場合、retrieval index への upsert は実行されず、前回実行時点の index が引き続き有効として扱われる。
- [ ] `failed`: retrieval index の upsert / 接続で例外が発生した、または `--verify-index` が不整合を検出した場合。`/spec-core --rebuild` で復旧する旨を出力する。
- [ ] `blocked`: 上流の理由 (pending conflict、freshness 停止、入力読み込み失敗) で `/spec-core` 自体が処理を中断し、retrieval index 経路に到達しなかった場合。

- [ ] Qdrant collection が手動削除等で `skipped_unchanged` の前提条件 (`retrieval_index_state.json` の指紋一致 + collection 存在) が崩れている場合、`/spec-core` は upsert を自動実行し、最終 status は `success` または `failed`、`core_progress.json` の `stages.section_collection_upsert.action` は `"upserted_full"` で記録される (更新が必要になった理由は同 stage の `reason` / `diagnostics` で確認可能)。
- [ ] 古い version の SPEC-anchor が作成した数値 point id の Qdrant collection を検出した場合、`/spec-core` は実行内で collection を再作成し UUID5 形式の point id で登録し直す (ユーザーの `--rebuild` 指定なしに自動移行、`core_progress.json` の `stages.section_collection_upsert.action` は `"upserted_full"`、同 stage に `migration_required_from_ordinal_point_id` warning が記録される)。
- [ ] Source Specs の一部 Section だけが変わった incremental 実行では、Source Retrieval Index の更新対象が変更・追加 Section に絞られ、削除 Section が Qdrant collection から取り除かれる。この場合 `core_progress.json` の `stages.section_collection_upsert.action` は `"upserted_partial"` になり、同 stage の `diagnostics` で `sections_upserted_count` / `sections_deleted_count` / `embed_documents_input_size` / `stale_points_deleted` を確認できる。
- [ ] `spec-anchor core --verify-index` は不整合を検出した場合、Source Retrieval Index を自動修復せず、結果を `retrieval_index_status = "failed"` として `/spec-core --rebuild` の実行を促す。

`related_sections_status` は Related Sections 生成の最終状態を示す。次のいずれかの値を取る。

- [ ] `success`: 今回 `/spec-core` が Related Sections の候補生成と LLM selection を実行し、selected_related_sections を最新化した。
- [ ] `skipped_unchanged`: 入力 (section 集合と内容、candidate generation / LLM selection の設定指紋) が前回 `/spec-core` 実行時と完全に一致した場合、候補生成と LLM selection は実行されず、前回の selected_related_sections が継承される。
- [ ] `failed`: Related Sections 生成のいずれかの段階で例外が発生した場合、または Qdrant 期待設定で retrieval backend を初期化できなかった場合。canonical な related_sections は更新されず前回値が残り、freshness は failed に降格する。
- [ ] `blocked`: 上流の理由で `/spec-core` が中断され、Related Sections 経路に到達しなかった場合。

- [ ] Qdrant 期待設定 (`vector_store.provider = "qdrant"` + `url` 設定済み + `embedding.provider = "flagembedding"`) で Qdrant retrieval backend を初期化できなかった場合、`/spec-core` は InMemory への自動切り替えを行わず、Related Sections を failed として扱う (期待した backend と実際の状態 / 失敗理由は CoreResult の diagnostics で確認可能)。
- [ ] Qdrant 未設定 (純 InMemory 構成) では Related Sections は InMemory で生成され、`related_sections_status = "success"` を返す。
- [ ] Source Specs の一部 Section だけが変わった incremental 実行では、Related Sections の更新対象が変更・追加 Section に絞られ、削除 Section への関連先が取り除かれる。`related_sections_status = "success"`、`core_progress.json` の `stages.related_sections.action` は `"regenerated_partial"`、同 stage の `diagnostics` で `candidate_generation_elapsed_sec` / `selection_elapsed_sec` / `candidate_generation_source_count` / `candidate_generation_partial_mode` を確認できる。
- [ ] 部分更新時、`/spec-core` は変更された Section から見た関連先のみ更新し、変更された Section が他 Section の関連先として現れる場合の判定は前回結果を引き継ぐ (`.spec-anchor/context/related_sections` の各エントリに `partial_mode` と `requires_full_regeneration_for_complete_target_recheck` フラグが添えられる)。

- [ ] Chapter Key Anchor は LLM 生成のみで作成され、mechanical / placeholder 代替 anchor は提供されない。
- [ ] LLM 生成に失敗した chapter があった場合、`/spec-core` は chapter_anchors artifact 全体を failed として扱い、canonical `chapter_anchors.json` は更新せず前回値を残し、freshness を failed に降格する (失敗した chapter 一覧は CoreResult の diagnostics で確認可能、`/spec-core --all` で再試行)。

- [ ] `potential_conflicts` は SpecClaim pair の LLM triage で `send_to_review = true` と判定された候補のうち、Conflict Review で「矛盾ではない」または「優先関係が明確」と判断できた pair を warning として保持する。
- [ ] `conflict_candidate_pairs_status` は Conflict Candidate Detection (Claim Retrieval + LLM triage) の最終状態を示す。`success` / `partial_success` / `skipped_unchanged` / `failed` / `blocked` のいずれかの値を取る。
- [ ] `spec_claims_status` は SpecClaim 抽出 stage の最終状態を示す。`success` / `partial_success` / `skipped_unchanged` / `failed` / `blocked` のいずれかの値を取る。SpecClaim 抽出に失敗した section が 1 件以上ある場合、status は `partial_success` または `failed` になり、Conflict Candidate Detection の recall は完全ではないとして diagnostics に記録される。
- [ ] LLM が既存根拠だけでは解決できない場合、`conflict_review_items` に `status = "pending"` の項目が作成され、freshness report は `status = "blocked"`、`blocking_reasons[] = ["pending_conflict"]` を返す。

Conflict Review Item は、少なくとも次を人間に提示する。

```text
[ ] conflict_id
[ ] status: pending
[ ] severity
[ ] source_refs[]
[ ] claims[]
[ ] why_conflicting
[ ] why_llm_cannot_decide
[ ] related_sections[]
[ ] decision_options[]
[ ] recommended_next_action
[ ] base_source_hashes[]
[ ] valid_scope
```

人間の判断肢は、少なくとも次を含む (`decision_options[]` に各オプションが提示される)。

- [ ] 片方の仕様を優先する
- [ ] 両方を満たす条件分岐を指示する
- [ ] 矛盾ではないとして dismiss する
- [ ] Source Specs の修正が必要として差し戻す
- [ ] 今回は判断保留にする

- [ ] 判断保留は conflict を解決しない。status は `pending` のまま残り、`/spec-inject` / `/spec-realign` はその conflict を無視して進まず停止する。

- [ ] 人間判断後の Conflict Review Item には、決定内容 / 理由 / 判断者が参照した source refs が `resolution` として保持される。
- [ ] SPEC-anchor は resolution を Purpose / Core Concept / Source Specs へ自動反映しない (反映は人間作業)。
- [ ] resolved Conflict Review Item が Purpose / Core Concept / Source Specs に未反映の場合、`/spec-core` は CoreResult の `unreflected_conflict_resolutions` として通知する (未反映自体は blocker ではない)。
- [ ] resolution は `base_source_hashes[]` と `valid_scope` を持つ。対象 Source Specs / Purpose / Core Concept の hash が変わった場合、resolution は `stale_resolution` になり、`/spec-inject` / `/spec-realign` で制約根拠として使われない。
- [ ] `valid_scope = "task_scope"` の resolution は、その課題内の一時判断として扱われ、後続セッションの恒久根拠として使われない。

decision payload は少なくとも次を持つ (`spec-anchor core --decision-json` / `--decision-file` で渡す JSON 構造)。

```text
[ ] conflict_id
[ ] decision
[ ] reason
[ ] selected_option
[ ] valid_scope
[ ] referenced_source_refs[]
```

`decision` の機械値と状態遷移は次のとおりである。

| 確認 | decision | 意味 | 遷移 |
|---|---|---|---|
| [ ] | `prefer_a` | conflict の片方 A を優先する | `resolved` |
| [ ] | `prefer_b` | conflict の片方 B を優先する | `resolved` |
| [ ] | `conditional` | 条件分岐により両方を扱う | `resolved` |
| [ ] | `dismiss` | 矛盾ではないとして退ける | `dismissed` |
| [ ] | `needs_source_update` | Source Specs / Purpose / Core Concept の修正が必要 | `pending` |
| [ ] | `defer` | 今回は判断保留にする | `pending` |
| [ ] | `task_scope_resolution` | 今回の課題内だけの一時判断にする | `resolved` + `valid_scope = task_scope` |

- [ ] `needs_source_update` は、人間が Source Specs / Purpose / Core Concept の修正を必要と判断したことを記録する pending decision である。修正後の `/spec-core` 再評価により conflict が解消された場合、SPEC-anchor は該当 pending item を `dismissed` に遷移できる。この自動遷移は人間 decision の `dismiss` とは区別し、`resolution.decision_origin="auto_source_update"`、`resolution.previous_status="pending"`、`resolution.applied_at=<timestamp>`、`resolution.auto_dismiss_reason=<reason>` を持つ。自動遷移前に pending decision の `resolution` が存在する場合、SPEC-anchor は置き換え前の値を `resolution.previous_resolution` に保持する。`auto_dismiss_reason` は将来拡張可能な enum であり、現在定義する値は `source_update_recheck_non_pending` と `source_update_recheck_pair_absent` である。
- [ ] 人間が `--decision-json` / `--decision-file` で渡した decision には、保存時に `resolution.decision_origin="human"` が入る。これにより、人間の `dismiss` と Source Specs / Purpose / Core Concept 修正後の自動 dismiss を区別できる。
- [ ] `/spec-core` の CoreResult は、Source Specs / Purpose / Core Concept 修正後の再評価で自動 dismiss された Conflict Review Item の件数を `auto_dismissed_conflict_count`、id 一覧を `auto_dismissed_conflict_ids[]` として返す。

- [ ] Conflict Candidate Detection は SpecClaim 抽出 (`.spec-anchor/context/spec_claims.jsonl` の生成) の後に実行される別 stage であり、Claim Retrieval と LLM triage を含む。対象は Claim Retrieval が絞り込んだ少数の SpecClaim pair に限定される (全 SpecClaim pair の総当たり LLM 判定は行わない)。
- [ ] Claim Retrieval は claim-level の dense retrieval、sparse retrieval、conflict probe retrieval を融合して候補 SpecClaim pair を生成する。Related Sections の出力は Claim Retrieval の必須前提ではない (Related Sections が未生成、stale、failed の場合も Claim Retrieval は実行可能)。
- [ ] Claim Retrieval の処理量制御は `[conflict_candidate_detection]` の `per_claim_top_k`、`per_section_top_k`、`per_target_top_k`、`global_candidate_top_k`、`triage_max_pairs` の各上限で行う。上限により候補が切られた場合は CoreResult の diagnostics に `truncated_candidate_sources` と `truncated_pair_count` が残る。
- [ ] LLM triage が `send_to_review = true` と判定した SpecClaim pair だけが §2.8 Conflict Review Item の作成対象となる。Related Sections 由来 pair は Conflict Review に送らない。

## 8. `/spec-inject`

### 8.1 目的

`/spec-inject` は、Agent / LLM が現在の会話区間と課題を解釈し、SPEC-anchor の保持物を使って今回必要な制約を生成し、会話区間へ注入するためのコマンドである。

このコマンドは課題に対する最終回答を作ることを目的にしない。LLM の注意を、本来の目的、Core Concept、関連 Source Specs、Section Summary、Related Sections、Chapter Key Anchor へ戻すことを目的にする。

会話区間の解釈と中心課題の特定は Agent / LLM の責務である (§5.3)。CLI は会話区間も課題プロンプトも消費しない。Agent / LLM が解釈した課題に基づいて、§8.3 の 4 path から必要な保持物を CLI に問い合わせ、制約を生成する。入力に含まれる会話区間の扱い、生テキスト投入の制限、根拠の区別は §3.4 を参照。

- [ ] `/spec-inject` の出力は「制約セット」である (Agent / LLM が現在の会話区間と課題を解釈し、SPEC-anchor の保持物を根拠とした制約を生成し、会話区間へ注入したものであることを §8.5 の 5 セクション構造および §8.2 の入力消費で確認する)。
- [ ] `/spec-inject` の通常出力は、課題に対する最終回答 / 実装コード / 結論文を含まない (Agent の出力は §8.5 の 5 セクション構造に限る)。
- [ ] `spec-anchor inject-*` / `realign` CLI は、会話区間 / 課題プロンプト全体を引数として受け取らない (各コマンドは §8.4 に列挙された限定引数のみ受理)。

### 8.2 入力

`/spec-inject` は次の artifact / 設定を入力として消費する。各行は「artifact の内容を変更すると CLI 出力 / Agent 提示が対応して変化する」または「Agent CLI の tool call trace に該当 artifact への Read / API 呼び出しが観測される」ことで検証する。

| 確認 | 入力 | 内容 |
|---|---|---|
| [ ] | `.spec-anchor/config.toml` | 対象プロジェクト設定 |
| [ ] | Purpose | 読み取り専用の上位目的 |
| [ ] | Core Concept | 人間更新対象のコアコンセプト |
| [ ] | Qdrant `[retrieval].section_collection` | Section 単位 hybrid retrieval index と payload (source_document_id / source_span / summary / search_keys / identifiers / related_sections / heading_path) |
| [ ] | `chapter_anchors.json` | LLM 生成の章単位 anchor |
| [ ] | `conflict_review_items.json` | resolved / dismissed / pending Conflict Review Items |

### 8.3 Agent / LLM が行う作業 (4 path)

Agent / LLM は、課題の性質に応じて次の 4 path を組み合わせて使う。`evidence_origin` の enum (`Purpose` / `Core Concept` / `Source Specs` / `Conflict Review Item`) を 4 path がそれぞれカバーする。各 path は必須ではなく許可で、Agent が選んで使い分ける。

#### path ① Qdrant section-level retrieval

ステップ個別チェック (LLM 手順遵守の可視化):

- [ ] 1. 会話区間 / 課題プロンプトから検索キーを選定し、hybrid retrieval を呼ぶ
- [ ] 2. CLI は section_id ranking を返す (top-K、K は config、少し大きめ)
- [ ] 3. 各 hit の payload (heading / summary / search_keys / identifiers) を読み、関連候補を見つける
- [ ] 4. 候補 Section の `related_sections` 配列を辿り、target_section_id を payload lookup で取得 (id 指定の point retrieve、vector 検索ではない)
- [ ] 5. 必要なら Source Specs ファイル本文を Read で確認し、制約根拠を抽出
- [ ] 6. 4 を再帰的に適用 (最大 N hop、N は config)。制約に関係しないと判断できた時点で打ち切り

evidence_origin: `Source Specs`

- [ ] **path ① 採用時の trace 監査** (検証単位): Agent CLI の tool call trace に `spec-anchor inject-search` の呼び出しが含まれ、その後に 1 回以上の `spec-anchor inject-section` (related 辿りによる id 指定 lookup) が観測される。必要に応じて `Read` による Source Specs ファイル読み込みも含まれる。最終 constraints の `evidence_origin` に `Source Specs` を含む item が存在する。

#### path ② chapter_anchors.json による章単位エントリ

ステップ個別チェック (LLM 手順遵守の可視化):

- [ ] 1. 会話区間 / 課題プロンプトから、`chapter_anchors.json` の summary / key_topics / important_sections に基づき関係しそうな章を特定
- [ ] 2. 特定された章配下の Section を path ① と同様に Agentic Search で読み、制約を抽出

evidence_origin: `Source Specs` (章単位の入口、最終 evidence は章配下の Source Specs)

- [ ] **path ② 採用時の trace 監査** (検証単位): Agent CLI の tool call trace に `spec-anchor inject-chapters` の呼び出しが含まれ、その後に該当章配下 Section に対する `spec-anchor inject-search` / `inject-section` の連鎖が観測される。最終 constraints の `evidence_ref` に当該章配下の section_id が含まれる。

#### path ③ Purpose / Core Concept からの制約抽出

ステップ個別チェック (LLM 手順遵守の可視化):

- [ ] 1. `purpose_file` / `concept_file` を Read で全文読み、課題に該当する制約根拠を抽出

evidence_origin: `Purpose` または `Core Concept`

- [ ] **path ③ 採用時の trace 監査** (検証単位): Agent CLI の tool call trace に `spec-anchor inject-purpose` の呼び出しと、続く `Read(purpose_file)` または `Read(concept_file)` が観測される。最終 constraints の `evidence_origin` に `Purpose` または `Core Concept` を含む item が存在する。

#### path ④ resolved Conflict Review Items の確認

ステップ個別チェック (LLM 手順遵守の可視化):

- [ ] 1. `conflict_review_items.json` から `status = resolved` かつ stale でない items を抽出
- [ ] 2. `valid_scope` (global / task_scope) と `resolution.referenced_source_refs` を確認
- [ ] 3. 制約に関係する場合、`evidence_origin = "Conflict Review Item"` として制約に組み込む

evidence_origin: `Conflict Review Item`

- [ ] **path ④ 採用時の trace 監査** (検証単位): Agent CLI の tool call trace に `spec-anchor inject-conflicts` の呼び出しが含まれ、最終 constraints の `evidence_origin = "Conflict Review Item"` の item の `evidence_ref` が `inject-conflicts` の戻り値範囲 (`status = resolved` かつ stale でない) に収まる。

#### 8.3.1 path 選択の指針

| 確認 | 課題タイプ | 主 path | 補強 |
|---|---|---|---|
| [ ] | 具体的 API / 識別子 | ① | ③、④ |
| [ ] | 全体方針 / 抽象的 | ② | ①、③、④ |
| [ ] | Purpose / Core Concept 直接質問 | ③ | ①、② |
| [ ] | 過去判断の継続 | ④ | ①、③ |

Agentic Search は Agent / LLM の責務である。CLI は検索結果、payload、章 anchor、Purpose / Core Concept、Conflict Review Items を返すだけであり、探索方針を自律的に決めない。

- [ ] `spec-anchor inject-*` には自動探索 / 多段 traversal を実行する CLI コマンドは含まれない (CLI は単発の retrieval / payload lookup / 章 anchor 取得 / Purpose 取得 / Conflict Review Item 取得のみ提供し、Section 間の再帰的 lookup は Agent 側が行う)。

### 8.4 CLI が提供する操作

CLI は外部契約として次の参照操作を提供する。

- [ ] 各 `inject-*` コマンドは内部で freshness gate / pending conflict gate / watcher gate を通す (§3.3 / §2.8 / §6.3)。gate が blocked / failed の場合、各コマンドは Agentic Search を実行せず、停止指示と理由 (`should_stop=true`、`blocking_reasons`、`recommended_next_action`) を返す。Agent は別途事前 probe を実行する必要はない。

| 確認 | 操作 | コマンド | 戻り値 |
|---|---|---|---|
| [ ] | section-level hybrid retrieval | `spec-anchor inject-search "<query>"` | `hits[]` 配列として top-K の Section payload を返す (各 hit に source_document_id / source_section_id / source_span / heading / summary / search_keys / identifiers / related_sections / score)。top-level に `query` / `collection` / `top_k` も含む |
| [ ] | Section payload lookup (related 辿り) | `spec-anchor inject-section "<id>" [<id>...]` | `sections` (dict、id をキー) + `found_section_ids[]` + `missing_section_ids[]` + `requested_section_ids[]` として返す。未存在 ID はエラーにならず `missing_section_ids` で通知 |
| [ ] | 章 anchor 取得 | `spec-anchor inject-chapters` | `chapter_anchors.json` の path。Agent は path を `Read` で読み、課題に関連しそうな章を特定する |
| [ ] | Purpose / Core Concept 取得 | `spec-anchor inject-purpose` | `purpose` (Purpose 全文、短いので注入) + `core_concept_path` (Core Concept の path、Agent が `Read` で必要箇所を抽出) |
| [ ] | Conflict Review Items 取得 | `spec-anchor inject-conflicts` | `status = resolved` かつ stale でない items |

- [ ] `spec-anchor inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` には CLI 固有フラグはない。`/spec-realign` の CLI フラグは §9.4 を参照。

### 8.5 通常出力

freshness report の `status = fresh` の場合、`/spec-inject` は Agent / LLM が生成した今回用の制約セットと、その根拠・探索経路の要約を会話へ注入する。

- [ ] `spec-anchor inject-*` および `spec-anchor realign` の **CLI 出力は内部 JSON** であり、stdout に JSON object を 1 つ出す。
- [ ] CLI 自身に整形 mode (`--format human` 等) は持たない。

人間に見える出力は、Agent CLI 側 (`.claude/commands/spec-inject.md` / `spec-realign.md` および `.codex/skills/spec-anchor/SKILL.md` の template) が CLI の JSON 戻り値を解釈し、ユーザー宛の会話に対して次のような読みやすい構造として整形する。

- [ ] 各セクションは、該当 0 件のときも「該当なし」を明示する (セクション自体の省略 / 空欄出力を許可しない)。

```text
[ ] 今回守る制約
      - <制約>
        根拠: Purpose / Core Concept / Source Specs
        参照補助: Section Summary / Chapter Key Anchor / Related Sections
        source: <source_document_id / source_section_id / source_span>

[ ] 今回見るべき対象
      - <Section または topic>
        理由: <なぜ今回関係するか>

[ ] 関連先として確認したもの
      - <related Section>
        理由: <depends / impacts / related / conflicts など>

[ ] 採用しなかったもの
      - <候補>
        理由: <今回の課題には遠い / 根拠不足 / 別論点>

[ ] 不確実性 / 人間確認
      - <確認すべき点>
```

制約セット (上記「今回守る制約」セクションの各 item) は、少なくとも次の最小構造を満たす。

```text
constraint
  [ ] statement: 今回守る制約
  [ ] evidence_origin: Purpose | Core Concept | Source Specs | Conflict Review Item
  [ ] evidence_ref: 文書 path、source_section_id、source span、Core Concept の項目、または stale でない resolved conflict_id
  [ ] support_refs: Section Summary / Related Sections / Chapter Key Anchor などの参照補助
  [ ] applicability: 今回の課題でどこに効く制約か
  [ ] uncertainty: 根拠不足、衝突、または人間確認が必要な点
```

- [ ] Agent / LLM は自由な説明文を出してよいが、制約を提示する場合は `statement` / `evidence_origin` / `evidence_ref` のいずれかを欠かさない (3 フィールド必須)。
- [ ] `/spec-inject` は、検索キー、Section Summary、Related Sections だけを根拠として制約を確定しない。制約として使う場合は、Purpose、Core Concept、Source Specs、または解決済み Conflict Review Item の該当箇所を根拠として示す。

制約構造の検証 (`statement` / `evidence_origin` / `evidence_ref` / `support_refs` / `applicability` / `uncertainty` の存在と整合) は **Agent / LLM が自己点検する責務** である。

- [ ] Conflict Review Item を根拠にする制約は、`status = resolved` かつ stale でない item に限る (`spec-anchor inject-conflicts` がこの範囲に絞って返すので、その範囲だけを採用する)。
- [ ] CLI (`spec-anchor inject-*`) は制約構造を検証しない (constraint の `statement` / `evidence_origin` 等の整合チェックは CLI 出力に含まれない)。

### 8.6 停止時出力

- [ ] freshness report が `status = blocked` かつ `blocking_reasons[] = ["pending_conflict"]` の場合、`/spec-inject` は通常の制約セット (`constraints[]`) を生成せず、人間判断が必要な conflict だけを停止時出力として提示する (詳細な CLI / Agent 出力契約は §11.1.5 / §11.2 を参照)。

Agent CLI が停止時に提示する出力は、次を必ず含む。各 conflict item は §2.8 の構造に従う。`recommended_next_action` の default は `Ask a human to decide this conflict.`。

```text
[ ] 停止理由: pending conflict

人間判断が必要な conflict
  [ ] conflict_id
  [ ] severity
  [ ] source_refs[]
  [ ] claims[]
  [ ] why_conflicting
  [ ] why_llm_cannot_decide
  [ ] decision_options[]
  [ ] recommended_next_action
```

- [ ] freshness report が `status = blocked` で、`blocking_reasons[]` に dirty / stale / watcher 系理由 (`dirty_or_stale_source` / `stale_config_or_schema` / `watcher_running` / `watcher_queue_pending`) を含む場合、`/spec-inject` は制約生成を行わず、`blocking_reasons[]` と推奨される次アクションを提示する (詳細は §11.1.5 / §11.2)。

## 9. `/spec-realign`

### 9.1 目的

`/spec-realign` は、`/spec-inject` と同じ手順で今回必要な制約を生成し、その制約に従って課題への回答または修正案を作るためのコマンドである。

会話区間の解釈と中心課題の特定は Agent / LLM の責務である (§5.3 / §8.1)。Agent / LLM は会話区間から中心課題を解釈し、特定できない場合は回答生成を進めずに人間に確認を求める。CLI は会話区間も課題プロンプトも消費しない。

- [ ] `/spec-realign` の出力は「制約セット + 制約に従った回答 / 修正案」である (制約生成手順は §8.3 と同じ、回答整形は §9.3 の 4 区分構造に従う)。
- [ ] Agent / LLM が中心課題を特定できない場合、`/spec-realign` は回答生成へ進まず、人間への確認を促す (回答が出ない / `agent_answer` 構成不能で停止)。
- [ ] `spec-anchor realign` CLI は会話区間 / 課題プロンプト全体を引数として受け取らず、Agent が構成した `agent_answer` を `--answer-*` フラグで受理する。

### 9.2 動作

ステップ個別チェック (CLI 手順遵守の可視化):

```text
[ ] /spec-realign
      [ ] freshness gate (§3.3 と同じ判定で blocked / failed なら停止)
      [ ] 8.3 と同じ手順で制約を生成する
      [ ] 生成した制約に従って回答または修正案を作る
      [ ] RealignResult を出力する
```

- [ ] **`/spec-realign` 実行の trace 監査** (検証単位): Agent CLI の tool call trace に §8.3 の 4 path のいずれかの呼び出し連鎖 + `spec-anchor realign --answer-json '<json>'` が観測され、最終出力に §9.3 の 4 区分が含まれる。

### 9.3 Answer 生成契約

LLM は、生成した制約を守って回答する。制約と矛盾する案を出す場合は、その矛盾を隠さず明示し、人間レビューが必要な点として扱う。

`Answer` は、少なくとも次を区別して記述する (RealignResult / Agent 提示文の 4 区分構造)。

```text
[ ] 今回守る制約
[ ] 今回扱う修正候補または検討対象
[ ] 競合 / 不確実性 / 人間レビューが必要な点
[ ] 課題プロンプトへの回答または修正案
```

- [ ] LLM の回答案が生成された制約と矛盾する場合、その矛盾は「競合 / 不確実性 / 人間レビューが必要な点」セクションに明示される (矛盾を隠した回答が出力されない)。

### 9.4 CLI フラグ

`spec-anchor realign` は次の回答候補入力フラグを持つ。回答候補は Agent が §9.3 の 4 区分 (`今回守る制約` / `今回扱う修正候補または検討対象` / `競合 / 不確実性 / 人間レビューが必要な点` / `課題プロンプトへの回答または修正案`) を含むように作成する。制約構造の検証は Agent / LLM の責務 (§8.5 末尾) で、CLI は回答を 4 区分の RealignResult に整形するだけである。

| 確認 | フラグ | 内容 |
|---|---|---|
| [ ] | `--answer <text>` / `--answer-text <text>` / `--agent-answer <text>` | Agent が生成した回答候補の plain text。alias は同義 |
| [ ] | `--answer-json <json>` / `--agent-answer-json <json>` | Agent が生成した回答候補の JSON object |
| [ ] | `--answer-file <path>` / `--agent-answer-file <path>` | 回答候補の JSON または plain text のファイル入力 |

- [ ] `spec-anchor realign` CLI は回答を 4 区分の RealignResult に整形するのみで、回答本文を独自生成しない (CLI の出力 `answer` field は Agent から渡された text の構造化のみ、新規 LLM 呼び出しを行わない)。

## 10. 設定ファイル

### 10.1 設定ファイル配置

プロジェクトごとの設定は `<project_root>/.spec-anchor/config.toml` に置く。親ディレクトリへの自動探索はしない。

```text
<project_root>/
└── .spec-anchor/
    └── config.toml
```

- [ ] `spec-anchor` 系コマンド (`spec-anchor` / `spec-anchor-watch` / `spec-anchor-setup-project` / `spec-anchor-setup-system`) は、設定ファイルを `<project_root>/.spec-anchor/config.toml` から読み込む (`spec-anchor-setup-project` がここに生成し、他コマンドはここを読む)。
- [ ] `.spec-anchor/config.toml` は `<project_root>` 直下にのみ配置される。親ディレクトリ (`../.spec-anchor/`) への自動探索は行われない (project root から外れた cwd でコマンドを実行すると `.spec-anchor/config.toml not found under {cwd}` で失敗)。

### 10.2 設定項目

`<id>` は `[llm.providers.<id>]` で命名するユーザー定義 provider id (例: `codex`、`claude_typing`、`claude_judge`)。

| 確認 | Table | Key | 必須性 | 既定値 | 内容 |
|---|---|---|---|---|---|
| [ ] | `[sources]` | `include` | 必須 | — | Source Specs として読み込む Markdown ファイルの glob。複数指定可。project-root 相対 |
| [ ] | `[sources]` | `exclude` | 任意 | `[]` | `include` から除外する glob。複数指定可 |
| [ ] | `[core]` | `purpose_file` | 必須 | — | Purpose ファイルのパス。SPEC-anchor は自動更新しない |
| [ ] | `[core]` | `concept_file` | 必須 | — | Core Concept ファイルのパス。人間更新対象 |
| [ ] | `[context]` | `storage` | 任意 | `.spec-anchor/context` | 生成済み保持物の保存先ディレクトリ |
| [ ] | `[section]` | `max_heading_level` | 任意 | `4` | Section 化する最大 Markdown heading level。`4` の場合 `#` から `####` までが Section 境界、それ以下は親 Section 本文に含まれる |
| [ ] | `[section_metadata]` | `summary_enabled` | 任意 | `true` | Section Summary 生成を有効にするか |
| [ ] | `[section_metadata]` | `search_keys_enabled` | 任意 | `true` | Section Search Keys 生成を有効にするか |
| [ ] | `[section_metadata]` | `related_sections_enabled` | 任意 | `true` | Related Sections 生成を有効にするか |
| [ ] | `[chapter_anchor]` | `enabled` | 任意 | `true` | Chapter Key Anchor 生成を有効にするか |
| [ ] | `[llm.providers.<id>]` | `command` | 必須 | — | 実行する CLI コマンド名または絶対パス (例: `codex`、`claude`)。`SPEC_ANCHOR_FAKE_LLM` が truthy のときは無視される |
| [ ] | `[llm.providers.<id>]` | `model` | 任意 | — | provider に渡す model 名 (例: `gpt-5.4-mini`、`claude-sonnet-4-6`) |
| [ ] | `[llm.providers.<id>]` | `effort` | 任意 | — | provider に渡す reasoning effort (例: `low`、`medium`) |
| [ ] | `[llm.providers.<id>]` | `timeout_sec` | 任意 | `120` | `command` で起動した CLI subprocess 1 attempt あたりの待ち時間 (秒)。この時間を超えると attempt は timeout として失敗扱いになる |
| [ ] | `[llm.providers.<id>]` | `max_retries` | 任意 | `1` | `command` で起動した CLI subprocess が失敗 (non-zero exit / timeout / schema 違反) した場合の追加 retry 回数。`max_retries = 1` の場合、1 stage 呼び出しあたり最大 attempt 数は初回 1 回 + retry 1 回の計 2 回。すべて失敗するとその stage が `failed` として diagnostics に出力される |
| [ ] | `[llm.stage_routing]` | `section_metadata` | 任意 | `[llm.providers]` の先頭定義 | section_metadata stage で使う provider id |
| [ ] | `[llm.stage_routing]` | `related_sections` | 任意 | `[llm.providers]` の先頭定義 | related_sections stage で使う provider id |
| [ ] | `[llm.stage_routing]` | `conflict_review` | 任意 | `[llm.providers]` の先頭定義 | conflict_review stage で使う provider id |
| [ ] | `[llm.stage_routing]` | `chapter_key_anchor` | 任意 | `[llm.providers]` の先頭定義 | chapter_key_anchor stage で使う provider id |
| [ ] | `[llm.stage_routing]` | `spec_claims` | 任意 | `[llm.providers]` の先頭定義 | spec_claims stage (SpecClaim 抽出) で使う provider id |
| [ ] | `[llm.stage_routing]` | `claim_retrieval` | 任意 | (LLM 呼ばない) | claim_retrieval stage は LLM を呼ばないため provider routing 対象外。設定 key として記述しても無視される |
| [ ] | `[llm.stage_routing]` | `conflict_candidate_triage` | 任意 | `[llm.providers]` の先頭定義 | conflict_candidate_triage stage (SpecClaim pair の LLM triage) で使う provider id |
| [ ] | `[retrieval]` | `dense_top_k` | 任意 | `12` | dense retrieval の取得 top-K |
| [ ] | `[retrieval]` | `sparse_top_k` | 任意 | `20` | sparse retrieval の取得 top-K |
| [ ] | `[retrieval]` | `rank_fusion` | 任意 | `"rrf"` | dense / sparse の融合方式。現時点では `rrf` (Reciprocal Rank Fusion) のみ受容 |
| [ ] | `[retrieval]` | `section_collection` | 任意 | `"spec_anchor_section"` | section-level retrieval 用 Qdrant collection 名。1 Section = 1 vector、payload に summary / search_keys / identifiers / related_sections / heading_path を含む |
| [ ] | `[retrieval]` | `section_dense_threshold` | 任意 | `0.55` | section-level dense 候補の採用最低スコア |
| [ ] | `[retrieval]` | `section_candidate_top_k` | 任意 | `16` | section-level 候補絞り込み 1 段目の top-K |
| [ ] | `[retrieval]` | `section_final_top_n` | 任意 | `8` | section-level 候補絞り込み最終 top-N |
| [ ] | `[retrieval]` | `claim_collection` | 任意 | `"spec_anchor_claim"` | claim-level retrieval 用 Qdrant collection 名。1 SpecClaim = 1 vector、payload に target / target_aliases / claim_text / claim_hash / source_section_id / evidence_span / retrieval hash を含む |
| [ ] | `[embedding]` | `provider` | 必須 | — | embedding provider 種別。標準は `flagembedding` |
| [ ] | `[embedding]` | `model` | 必須 | — | embedding model 名。標準は `BAAI/bge-m3` |
| [ ] | `[embedding]` | `dense_enabled` | 任意 | `true` | dense embedding を有効にするか |
| [ ] | `[embedding]` | `sparse_enabled` | 任意 | `true` | sparse embedding を有効にするか |
| [ ] | `[vector_store]` | `provider` | 必須 | — | vector store 種別。標準は `qdrant` |
| [ ] | `[vector_store]` | `url` | 任意 | — | vector store の接続先 URL (例: `http://localhost:6333`) |
| [ ] | `[limits]` | `section_summary_max_chars` | 任意 | `480` | Section Summary の最大文字数 |
| [ ] | `[limits]` | `search_keys_max` | 任意 | `32` | Section Search Keys の 1 Section あたり最大個数 |
| [ ] | `[limits]` | `related_candidate_max_per_section` | 任意 | `32` | Related Sections 候補生成の 1 Section あたり最大個数 |
| [ ] | `[limits]` | `related_selected_max_per_section` | 任意 | `8` | Related Sections 最終採用の 1 Section あたり最大個数 |
| [ ] | `[limits]` | `llm_batch_max_sections` | 任意 | `8` | 1 LLM 呼び出しでまとめる Section 数の上限 |
| [ ] | `[limits]` | `llm_batch_max_chars` | 任意 | `12000` | 1 LLM 呼び出しでまとめる総文字数の上限 |
| [ ] | `[limits]` | `llm_batch_concurrency` | 任意 | `4` | section_metadata / related_sections の batch 並列実行数 (1 = 逐次。Codex Pro 5x / Claude Max 5x 環境は 4-8 推奨) |
| [ ] | `[conflict_candidate_detection]` | `enabled` | 任意 | `true` | Conflict Candidate Detection (SpecClaim 抽出 + Claim Retrieval + LLM triage) を有効にするか |
| [ ] | `[conflict_candidate_detection]` | `per_claim_top_k` | 任意 | `10` | 1 claim あたりの Claim Retrieval 候補 top-K |
| [ ] | `[conflict_candidate_detection]` | `per_section_top_k` | 任意 | `20` | 1 section 配下の SpecClaim 候補 pair 上限 |
| [ ] | `[conflict_candidate_detection]` | `per_target_top_k` | 任意 | `20` | 同一 target を共有する候補 pair 上限 |
| [ ] | `[conflict_candidate_detection]` | `global_candidate_top_k` | 任意 | `100` | Claim Retrieval 全体の最終候補 pair 上限 |
| [ ] | `[conflict_candidate_detection]` | `triage_max_pairs` | 任意 | `30` | LLM triage に送る最大 pair 数 (global_candidate_top_k より少なくしてよい) |
| [ ] | `[conflict_candidate_detection]` | `min_dense_score` | 任意 | `0.55` | dense retrieval 採用最低スコア |
| [ ] | `[conflict_candidate_detection]` | `min_sparse_score` | 任意 | `0.0` | sparse retrieval 採用最低スコア |
| [ ] | `[conflict_candidate_detection]` | `rank_fusion` | 任意 | `"rrf"` | dense / sparse / conflict_probe channel の融合方式。現時点では `rrf` のみ受容 |
| [ ] | `[conflict_candidate_detection]` | `allow_same_section_claim_pair` | 任意 | `true` | 同一 section 内 SpecClaim pair を候補対象にするか |
| [ ] | `[conflict_candidate_detection]` | `allow_same_source_file_claim_pair` | 任意 | `true` | 同一 Source Specs file 内 SpecClaim pair を候補対象にするか |
| [ ] | `[watcher]` | `enabled` | 任意 | `false` | watcher を有効にするか。標準テンプレは `true` で配布 |
| [ ] | `[watcher]` | `interval_ms` | 任意 | `2000` | watcher の polling 間隔 (ミリ秒) |
| [ ] | `[watcher]` | `debounce_ms` | 任意 | `1000` | 連続変更を 1 回の更新にまとめる debounce 時間 (ミリ秒) |
| [ ] | `[watcher]` | `stale_lock_ms` | 任意 | `300000` | 古い lock を回収する閾値 (ミリ秒) |
| [ ] | `[watcher]` | `state_file` | 任意 | — | watcher 状態ファイルのパス。project-root 相対 |
| [ ] | `[watcher]` | `queue_file` | 任意 | — | watcher キューファイルのパス。project-root 相対 |

`[llm.providers.<id>]` と `[llm.stage_routing]` は `/spec-core` が保持物生成 (section_metadata / related_sections / spec_claims / conflict_candidate_triage / conflict_review / chapter_key_anchor) で直接 spawn する LLM の設定である。`claim_retrieval` stage は LLM を呼ばず Qdrant / FlagEmbedding の retrieval だけを実行するため、provider routing 対象外である。`/spec-inject` / `/spec-realign` の会話区間解釈、Agentic Search、制約生成、回答生成を行う Agent / LLM は Agent CLI 側で動くため、これらの設定の対象外である。

- [ ] `[llm.providers.<id>]` と `[llm.stage_routing]` は `/spec-core` の保持物生成 stage (section_metadata / related_sections / spec_claims / conflict_candidate_triage / conflict_review / chapter_key_anchor) でのみ参照される (`/spec-inject` / `/spec-realign` の Agent / LLM 動作には影響しない、tool call trace に `[llm.providers]` 由来の subprocess 起動が現れない)。
- [ ] `claim_retrieval` stage は LLM を呼ばないため `[llm.stage_routing]` の対象外であり、provider routing 解決もされない (tool call trace に claim_retrieval stage 由来の `[llm.providers]` subprocess 起動が現れない)。

Codex 用 skill と Claude 用 command は `spec-anchor core` を `--llm-provider` 引数なしで実行し、`[llm.stage_routing]` に従って stage 別に provider を選ばせる。`--llm-provider` を明示すると `[llm.stage_routing]` が上書きされ、その provider id が全 stage に適用されるため、provider 障害時の手動 fallback など特別な事情がない限り指定しない。

- [ ] Codex skill (`.codex/skills/spec-anchor/SKILL.md`) と Claude command (`.claude/commands/spec-core.md`) の template は `spec-anchor core` を `--llm-provider` 引数なしで呼ぶ (template 本文に `spec-anchor core --llm-provider` の文字列が含まれない、または明示的に「特別な事情がない限り指定しない」旨が記載されている)。

#### Stage 別 provider routing (`[llm.stage_routing]`)

`/spec-core` の各 stage は認知負荷が異なるため、stage 別に LLM provider を切り替える仕組みを持つ。許可される stage key は次の 6 つに固定する。`claim_retrieval` stage は LLM を呼ばないため stage_routing の対象外である。

| stage | 役割 |
|---|---|
| `section_metadata` | summary / search_keys / identifiers の機械抽出 |
| `related_sections` | candidate 集合からの relation_hint 分類 |
| `spec_claims` | section 単位の SpecClaim (仕様主張) の抽出 |
| `conflict_candidate_triage` | Claim Retrieval が絞った少数 SpecClaim pair の Conflict Review 送付要否判定 (`send_to_review` の bool 判定のみ) |
| `conflict_review` | Purpose / Core Concept grounding を伴う矛盾判定 |
| `chapter_key_anchor` | 章単位 summary / key_topics / important_sections の合成 |

stage_routing は明示指定方式であり、次の契約に従う。

- [ ] `[llm.providers.<id>]` は少なくとも 1 つ必須 (0 個の場合は設定エラーとして reject する)。
- [ ] `[llm.stage_routing]` の各 stage は任意。未指定 stage は `[llm.providers.<id>]` の先頭定義 (TOML 上の出現順) を使う。
- [ ] `[llm.stage_routing]` 自体が無い、または全 stage 未指定の場合、すべての stage が `[llm.providers.<id>]` 先頭定義を使う。
- [ ] `spec-anchor core --llm-provider <id>` を CLI で明示すると、その provider id が `[llm.stage_routing]` の指定を上書きし、全 stage に適用される。
- [ ] 指定された provider が実行失敗 (non-zero exit / timeout / schema 違反) した場合、別 provider に黙って切り替えず、失敗として報告する (silent fallback 禁止)。
- [ ] stage_routing で参照する provider id は `[llm.providers.<id>]` で定義済みでなければ設定エラーとして reject する。
- [ ] 許可外の stage key (例: 誤記の `conflict_reveiw`) は設定エラーとして reject する (許可される stage key は `section_metadata` / `related_sections` / `spec_claims` / `conflict_candidate_triage` / `conflict_review` / `chapter_key_anchor` の 6 つ固定)。

- [ ] `spec-anchor-setup-project` が新規プロジェクトで実行された場合、`.spec-anchor/config.toml` に次の初期設定 (下記 TOML 内容) が展開される (既存ファイルがある場合は §6.2.2 の安全性ルールに従い、`--force` 無しでは上書きしない)。

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
# claim_retrieval は LLM を呼ばないため routing 対象外 (記述してもよいが無視される)。
[llm.stage_routing]
section_metadata           = "codex"
related_sections           = "claude_typing"
spec_claims                = "codex"
conflict_candidate_triage  = "claude_judge"
conflict_review            = "claude_judge"
chapter_key_anchor         = "codex"

[retrieval]
dense_top_k = 12
sparse_top_k = 20
rank_fusion = "rrf"
section_collection = "spec_anchor_section"
claim_collection = "spec_anchor_claim"
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
llm_batch_max_sections = 8
llm_batch_max_chars = 12000
llm_batch_concurrency = 4   # 1 = 逐次。Pro 5x / Max 5x なら 4-8 推奨

[conflict_candidate_detection]
enabled = true
per_claim_top_k = 10
per_section_top_k = 20
per_target_top_k = 20
global_candidate_top_k = 100
triage_max_pairs = 30
min_dense_score = 0.55
min_sparse_score = 0.0
rank_fusion = "rrf"
allow_same_section_claim_pair = true
allow_same_source_file_claim_pair = true

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

- [ ] `SPEC_ANCHOR_DEBUG_*` 系 env var は本運用経路の挙動を変えず、set 時のみ追加の append 出力が増える観察専用である (未 set 時と挙動 / 出力 artifact が一致する)。

project root に `.env` ファイル (dotenv 形式の `KEY=VALUE` 行) を置くと、`spec-anchor` 起動時に `load_config` が読み込んで `os.environ` に投入する (既存 shell 変数は上書きしない)。shell から直接 export しても、CI が pipeline 設定で export しても、`.env` 経由でも、同じ env として扱われる。雛形は project root の `.env.example` を参照。

- [ ] project root に `.env` ファイル (`KEY=VALUE` 行) を置くと、`spec-anchor` 起動時に `load_config` が読み込んで `os.environ` に投入する。
- [ ] `.env` の KEY と同名の shell 変数が既に export されている場合、`.env` の値は採用されず、既存 shell 変数の値が維持される (上書きしない契約)。
- [ ] shell export / `.env` / CI pipeline export のいずれの経路で投入された env も、`spec-anchor` 内では同じ env として扱われる (経路による挙動差が無い)。

| 確認 | 環境変数 | 役割 |
|---|---|---|
| [ ] | `SPEC_ANCHOR_FAKE_LLM` | truthy (`1` / `true` / `yes` / `on`) のとき、`spec-anchor core` は `[llm.providers.<id>]` の `command` を子プロセスとして起動せず in-process FakeLlmProvider を使う。test / smoke で実 codex / claude CLI を呼ばないために使う |
| [ ] | `SPEC_ANCHOR_FAKE_RETRIEVAL` | truthy のとき、Qdrant + FlagEmbedding BGE-M3 の実構築を伴う test / smoke コード経路を block する。本運用の `/spec-core` 経路 (Qdrant への Section payload 書き込みと hybrid retrieval) は本変数の影響を受けず、`[vector_store].url` の Qdrant と `[embedding].model` の BGE-M3 をそのまま使う。test / smoke で BGE-M3 weight download や Qdrant 接続を避けるために使う |
| [ ] | `SPEC_ANCHOR_QDRANT_URL` | `spec-anchor-setup-project` / `setup-system` の probe が `.spec-anchor/config.toml` 確定前に Qdrant 接続先を解決するために読む。config が存在する場合は `[vector_store].url` が正本 |
| [ ] | `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION` | truthy のとき、`spec-anchor core` が起動する LLM 子プロセスの解決済み command と stdin、それぞれの SHA-256 を JSONL append で記録する (1 行 1 invocation)。consecutive run で codex / claude へ渡るバイト列の安定性を観測する用途。本運用経路の挙動は変えず、書き込み失敗は黙って no-op。default 出力先は project root 直下の `.spec-anchor/state/_debug_provider_invocations.jsonl` |
| [ ] | `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION_PATH` | 上記 debug log の出力先 file path を上書きする。空 / 未設定なら default の `.spec-anchor/state/_debug_provider_invocations.jsonl` を使う。`SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION` が falsy / 未設定のときは本変数を読まない |
| [ ] | `SPEC_ANCHOR_DEBUG_RELATED_PROMPT` | truthy (`1` / `true` / `yes` / `on`) のとき、`/spec-core` の Related Sections stage が組み立てた prompt の hash と入力 section 集合を JSONL append で記録する (1 行 1 prompt)。prompt 構成が consecutive run で安定しているか観測する用途。本運用経路の挙動は変えず、書き込み失敗は黙って no-op。default 出力先は project root 直下の `.spec-anchor/state/_debug_related_prompts.jsonl` |
| [ ] | `SPEC_ANCHOR_DEBUG_RELATED_PROMPT_PATH` | 上記 debug log の出力先 file path を上書きする。空 / 未設定なら default の `.spec-anchor/state/_debug_related_prompts.jsonl` を使う。`SPEC_ANCHOR_DEBUG_RELATED_PROMPT` が falsy / 未設定のときは本変数を読まない |

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

- `.spec-anchor/context/`: `/spec-core` が生成する人間 / Agent 参照の保持物 (`chapter_anchors.json`、`conflict_review_items.json`、`spec_claims.jsonl`、`conflict_candidate_pairs.jsonl`)
- `.spec-anchor/cache/`: section_metadata / related_sections / chapter_anchors の LLM 応答キャッシュ
- `.spec-anchor/state/`: 状態管理・鮮度・watcher (`section_manifest.json`、`freshness.json`、`watch_state.json`、`watch_queue.json`)
- `.env`: user 個別の subsystem 切替 (`SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` で fake モードへ、`SPEC_ANCHOR_QDRANT_URL` で setup probe の Qdrant 接続先差し替え)。共有用の雛形は `.env.example` を repo に commit する

## 11. エラー契約

本章は外部仕様として **入力** と **出力** を記述する。エラー時に利用者が観測すべき情報 (JSON のフィールド名、文字列、exit code) はすべて出力列に書く。

本システムは 2 レイヤー構造である。利用者は通常 slash command / skill 経由で操作し、CLI を直接実行することもできる。各レイヤーで入力と出力が異なるため、§11.1 と §11.2 で別々に契約を記述する。

- **CLI レイヤー** (§11.1): 利用者または slash command / skill が `spec-anchor` CLI を子プロセスとして起動する。出力は stdout の JSON と CLI exit code。
- **slash command / skill レイヤー** (§11.2): 利用者が Agent CLI (Claude Code / Codex) に slash command (`/spec-core` / `/spec-inject` / `/spec-realign`) または skill (SPEC-anchor skill) を発火する。Agent CLI は内部で `spec-anchor` CLI を実行し、その JSON を読み取って利用者に整形して伝達する。出力は Agent が利用者に提示する情報構造。

外部契約コマンドは次の 6 種類:

- `/spec-core` (内部実行: `spec-anchor core`)
- `/spec-inject` (内部実行: `spec-anchor inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts`、§8)
- `/spec-realign` (内部実行: `spec-anchor realign`、§9)
- `spec-anchor-watch` (§6.3)
- `spec-anchor-setup-system` (§6.2)
- `spec-anchor-setup-project` (§6.2)

総則: `status = "failed"` を返す失敗はすべて、`freshness_report.blocking_reasons` に `failed_required_artifact` が積まれ、`freshness_report.status` も `failed` になる。これにより下流の `/spec-inject` / `/spec-realign` は freshness gate (§3.3) で停止する。`/spec-core` 自身は新しい canonical artifact を上書きせず、前回値を残すため、復旧 (例: `spec-anchor core --rebuild`、Qdrant 再起動、Source Specs / Purpose / Core Concept の修正) 時の比較基準として使える。

CLI exit code の方針は対応コマンドで非対称である。`spec-anchor core` / `spec-anchor realign` / `spec-anchor-setup-project` / `spec-anchor-setup-system` は `status` が `"failed"` / `"error"` / `"conflict"` のときに CLI exit code 1 を返す。`spec-anchor inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` と `spec-anchor-watch` は CLI exit code 0 固定であり、停止状態は stdout JSON (`should_stop` / `blocking_reasons` / `status`) で表現する (呼び出し元は CLI exit code を見ずに JSON を parse する責務を持つ)。

### 11.1 失敗時の JSON 戻り値の構造

利用者 (shell / CI / Agent CLI / slash command / skill) は次の構造を `spec-anchor` CLI の stdout JSON から parse して観測する。stderr は補助情報のみで、契約としては stdout の JSON が正本である。コマンド分類で構造が異なる。

#### 11.1.1 `spec-anchor core` の失敗

```json
{
  "status": "failed" | "error",
  "freshness_report": {
    "status": "failed",
    "blocking_reasons": ["failed_required_artifact", ...],
    "warnings": [<string or object>],
    "diagnostics": {"failed_required_artifacts": [<artifact name>, ...]}
  },
  "warnings": [<string or object>],
  "diagnostics": {
    "<context>": {
      "reason_code": "<具体 code>",
      "message": "<エラー詳細>",
      "exception_type": "<例外型名、省略可>"
    }
  },
  "retrieval_index_status": "success" | "failed" | "blocked" | "skipped_unchanged",
  "related_sections_status": "success" | "failed" | "blocked" | "skipped_unchanged"
}
```

`diagnostics.<context>.reason_code` の代表値:

- `config_error`: `.spec-anchor/config.toml` / Purpose / Core Concept / Source Specs 不在 (`ConfigError` 経由)
- `retrieval_backend_init_failed`: Qdrant 設定済みで Related Sections 用 retrieval backend の初期化失敗
- `chapter_anchors_llm_failure`: Chapter Key Anchor 生成失敗 (`chapter_anchors.failure_reasons_by_chapter` に chapter ごとの理由)
- `retrieval_index_failed`: embedding / retrieval index 更新失敗

#### 11.1.2 `spec-anchor inject-*` / `spec-anchor realign` の失敗

A) **freshness gate stop** (通常の停止経路):

```json
{
  "command": "/spec-inject inject-search",
  "status": "blocked" | "failed",
  "should_stop": true,
  "blocked": true,
  "can_continue": false,
  "blocking_reasons": ["dirty_or_stale_source" | "pending_conflict" | "watcher_running" | "watcher_queue_pending" | "failed_required_artifact" | ...],
  "warnings": [<string or object>],
  "recommended_next_action": "<具体的に何をすべきか>",
  "pending_conflict_items": [<Conflict Review Item>, ...]
}
```

`pending_conflict_items` は `pending_conflict` が blocking reason に含まれる場合のみ。

B) **例外経由** (内部エラー):

```json
{
  "command": "/spec-inject inject-search",
  "status": "error",
  "should_stop": true,
  "blocked": true,
  "can_continue": false,
  "error": {
    "code": "command_error",
    "type": "<例外型名>",
    "message": "<エラー詳細>"
  }
}
```

#### 11.1.3 `spec-anchor-setup-project` の失敗

```json
{
  "status": "conflict" | "error" | "failed",
  "exit_code": 1,
  "applied": false,
  "conflicts": [
    {
      "path": "<相対 path>",
      "reason": "would_overwrite_existing_file" | "destination_exists_and_is_not_file" | "existing_file_is_not_utf8_text",
      "diff": "<unified diff、reason が overwrite の場合のみ>"
    }
  ],
  "diagnostics": [{"reason_code": "<code>", "message": "<詳細>"}, ...]
}
```

#### 11.1.4 `spec-anchor-setup-system` の失敗

```json
{
  "status": "ok" | "degraded" | "error" | "failed",
  "production_readiness": {
    "status": "ready" | "blocked",
    "blocking_reasons": ["qdrant_service_unavailable" | "flagembedding_missing" | "qdrant_client_missing" | "agent_cli_unavailable" | "console_script_missing" | ...],
    "checks": [{"name": "<subsystem>", "status": "passed" | "failed", "reason_code": "<code or null>"}]
  },
  "providers": [<provider entry>],
  "console_scripts": [<entry>],
  "templates": [<entry>],
  "diagnostics": [<entry>]
}
```

### 11.1.5 CLI レイヤーのエラー契約 (入力 / 出力)

各行の「入力」は発火条件 (実行する CLI コマンド + 引数 + 環境状態) を、「出力」は CLI が返すすべての観測可能な内容 (stdout JSON のフィールド + 文字列 template + CLI exit code) を記述する。文字列 template の `{var}` は実行時に置換される値を示す。共通の JSON 構造は §11.1.1 〜 §11.1.4 を参照。

| 確認 | 入力 | 出力 |
|---|---|---|
| [ ] | `<project_root>/.spec-anchor/config.toml` 不在で `spec-anchor core [--all] [--rebuild]` を実行 | CLI exit code 1。stdout JSON (§11.1.1): `status="failed"`、`mode=<full|incremental>`、`project_root=<root>.as_posix()`、`freshness_report.status="failed"`、`freshness_report.blocking_reasons=["failed_required_artifact"]`、`freshness_report.diagnostics.failed_required_artifacts=["source_specs"]`、`freshness_report.warnings=[<exception message>]`、`warnings=[<exception message>]`、`diagnostics.config_error={"reason_code":"config_error", "message":".spec-anchor/config.toml not found under {root}", "exception_type":"ConfigError"}`、`retrieval_index_status="failed"`、`related_sections_status="blocked"`、`updated_sources=[]`、`updated_sections=[]`、`pending_conflict_count=0` |
| [ ] | `<project_root>/.spec-anchor/config.toml` 不在で `spec-anchor inject-search "<query>"` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` のいずれかを実行 | CLI exit code 0。stdout JSON (§11.1.2 B): `command="/spec-inject <subcommand>"`、`project_root=<root>.as_posix()`、`status="error"`、`should_stop=true`、`stops=true`、`blocked=true`、`can_continue=false`、`constraints=[]`、`error={"code":"command_error", "type":"ConfigError", "message":".spec-anchor/config.toml not found under {root}"}` |
| [ ] | `<project_root>/.spec-anchor/config.toml` 不在で `spec-anchor realign --answer-json '<json>'` を実行 | CLI exit code 1。stdout JSON (§11.1.2 B、`command="/spec-realign"` を除き同 shape) |
| [ ] | `<project_root>/.spec-anchor/config.toml` 不在で `spec-anchor-watch [--once]` を実行 | CLI exit code 0。stdout JSON (watch 固有 shape): `error={"code":"command_error", "type":"ConfigError", "message":".spec-anchor/config.toml not found under {root}"}`、watcher loop には入らずに早期 return |
| [ ] | `<project_root>/docs/core/purpose.md` (or `[core].purpose_file` で指定された file) 不在で `spec-anchor core` を実行 | CLI exit code 1。stdout JSON (§11.1.1): `status="failed"`、`diagnostics.config_error={"reason_code":"config_error", "message":"core.purpose_file not found: {purpose_path}", "exception_type":"ConfigError"}`、`warnings=[<same message>]`、`freshness_report.status="failed"`、`freshness_report.blocking_reasons=["failed_required_artifact"]`、`freshness_report.diagnostics.failed_required_artifacts=["source_specs"]`。例: `message="core.purpose_file not found: /path/to/project/docs/core/purpose.md"` |
| [ ] | `<project_root>/docs/core/concept.md` (or `[core].concept_file` で指定された file) 不在で `spec-anchor core` を実行 | CLI exit code 1。stdout JSON: 上記 Purpose 不在と同じ shape、`message="core.concept_file not found: {concept_path}"` (例: `"core.concept_file not found: /path/to/project/docs/core/concept.md"`) |
| [ ] | `[sources].include` の glob にマッチする Source Specs が 0 件で `spec-anchor core` を実行 | CLI exit code 1。stdout JSON: `status="failed"`、`diagnostics.config_error={"reason_code":"config_error", "message":"sources.include did not match any Source Specs", "exception_type":"ConfigError"}`、`updated_sources=[]`、`freshness_report.diagnostics.failed_required_artifacts=["source_specs"]`。`[sources].include` 自体が空 list / 非 list の場合は `message="sources.include must be a non-empty list"` または `"sources.include must contain non-empty strings"` |
| [ ] | Section Metadata の LLM 生成が一部の section で失敗 (必須 artifact 自体は揃う) `spec-anchor core` を実行 | CLI exit code 0。stdout JSON: `status="degraded"`、`failed_sections=[{section_id, reason_code, ...}, ...]`、`updated_sections=[<成功 section>]`、`diagnostics.section_metadata_generation={..., "failed_sections":[...], "freshness_status":"degraded"}`、`freshness_report.status="degraded"`、`freshness_report.blocking_reasons=["degraded_optional_artifact"]`、`freshness_report.diagnostics.degraded_optional_artifacts=["section_metadata"]`、`warnings=[<section ごとの失敗説明>]` |
| [ ] | Chapter Key Anchor の LLM 生成が失敗で `spec-anchor core` を実行 | CLI exit code 1。stdout JSON: `status="failed"`、`diagnostics.chapter_anchors={"status":"failed", "failed_chapter_ids":[...], "failure_reasons_by_chapter":{...}}`、`warnings=["Chapter Anchors LLM generation failed for {N} chapter(s); canonical chapter_anchors.json is not updated. Run /spec-core --all to retry."]`、`freshness_report.diagnostics.failed_required_artifacts=["chapter_anchors"]`、`regenerated_chapter_anchors=[]`。`chapter_anchors.json` 自体は前回値のまま書き換えない |
| [ ] | `[vector_store].provider="qdrant"` で Qdrant に到達できない (例: localhost:6333 down) 状態で `spec-anchor core` を実行 | CLI exit code 1。stdout JSON: `status="failed"`、`related_sections_status="failed"`、`diagnostics.related_sections.qdrant_backend_failure={"failure_reason":<具体>, ...}`、`warnings=["Related Sections retrieval backend failure: {failure_reason}; canonical related_sections artifact is not updated. Restore Qdrant connectivity and run /spec-core --rebuild."]`、`freshness_report.diagnostics.failed_required_artifacts=["related_sections"]`。`[vector_store].provider != "qdrant"` (InMemory 構成) では本パスは発火しない |
| [ ] | Qdrant の section collection への upsert / verify が失敗で `spec-anchor core` を実行 | CLI exit code 1。stdout JSON: `status="failed"`、`retrieval_index_status="failed"`、`diagnostics.retrieval_index={...}`、`warnings=["Source Retrieval Index update failed"]` (upsert 失敗時) または `["Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild"]` (`--verify-index` で不整合検出時)、`freshness_report.diagnostics.failed_required_artifacts=["retrieval_index"]`。前回の Qdrant collection は drop せず保持 (`--rebuild` 時のみ recreate) |
| [ ] | `freshness.json` が `status="blocked"` で `blocking_reasons` に `"dirty_or_stale_source"` / `"stale_config_or_schema"` / `"watcher_running"` / `"watcher_queue_pending"` のいずれかを含む状態で `spec-anchor inject-search` / `inject-section` / `inject-chapters` / `inject-purpose` / `inject-conflicts` のいずれかを実行 | CLI exit code 0。stdout JSON (§11.1.2 A): `command="/spec-inject <subcommand>"`、`status="blocked"`、`should_stop=true`、`stops=true`、`blocked=true`、`can_continue=false`、`blocking_reasons=<freshness.json と同じ>`、`recommended_next_action=` `"run /spec-core before /spec-inject"` (`dirty_or_stale_source`) / `"run /spec-core --all before /spec-inject"` (`stale_config_or_schema`) / `"wait for watcher completion before /spec-inject"` (`watcher_running` / `watcher_queue_pending`)。`pending_conflict_items` は本 path では output に含まれない (null / 省略) |
| [ ] | 同上の `freshness.json` 状態で `spec-anchor realign --answer-json '<json>'` を実行 | CLI exit code 0。stdout JSON: 上記と同 shape (`command="/spec-realign"`、`recommended_next_action` の `before /spec-inject` → `before /spec-realign` に置換) |
| [ ] | `freshness.json` が `status="blocked"` で `blocking_reasons=["pending_conflict"]` の状態で `spec-anchor inject-*` / `realign` を実行 | CLI exit code 0。stdout JSON (§11.1.2 A): `status="blocked"`、`should_stop=true`、`blocking_reasons=["pending_conflict"]`、`pending_conflict_items=[{conflict_id, status:"pending", severity, claims, why_conflicting, why_llm_cannot_decide, decision_options, source_refs, recommended_next_action:"Ask a human to decide this conflict."}, ...]`、`recommended_next_action="resolve pending Conflict Review Items"`、`pending_conflict_count=<件数>` |
| [ ] | `freshness.json` が `status="failed"` (= 直前 `/spec-core` で `failed_required_artifact`) の状態で `spec-anchor inject-*` / `realign` を実行 | CLI exit code 0 (`inject-*`) または 0 (`realign` は exit 1 を返さず 0、JSON で `status="failed"` を表現)。stdout JSON (§11.1.2 A): `status="failed"`、`blocking_reasons=["failed_required_artifact"]`、`recommended_next_action="run /spec-core or /spec-core --all before /spec-inject"` (`realign` は `before /spec-realign`) |
| [ ] | 配置先 path が存在しない / directory でない状態で `spec-anchor-setup-project --target <path>` を実行 | CLI exit code 1。stdout JSON (§11.1.3): `status="error"`、`exit_code=1`、`target=<path>`、`applied=false`、`created=[]`、`updated=[]`、`skipped=[]`、`conflicts=[]`、`diagnostics=[{"reason_code":"target_not_found", "message":"target does not exist; create it explicitly before running setup", "severity":"error"}]` または `[{"reason_code":"target_not_directory", "message":"target is not a directory", "severity":"error"}]` |
| [ ] | 配置対象 path に既存ファイルがあり内容が異なる状態で `spec-anchor-setup-project --target <path>` を実行 (`--force` 無し) | CLI exit code 1。stdout JSON (§11.1.3): `status="conflict"`、`exit_code=1`、`applied=false`、`conflicts=[{"path":<rel>, "reason":"would_overwrite_existing_file", "diff":<unified diff>}, ...]` (UTF-8 でない場合は `"reason":"existing_file_is_not_utf8_text"`、配置先が directory / symlink で file でない場合は `"reason":"destination_exists_and_is_not_file"`、最後 2 つの reason では `diff` field なし)。`docs/core/purpose.md` / `docs/core/concept.md` は `--force` の有無に関わらず常に `protected` として `skipped` に入り、`conflicts` には載らない |
| [ ] | 同上の状態で `spec-anchor-setup-project --target <path> --force` を実行 | CLI exit code 0。stdout JSON: `status="ok"`、`applied=true`、`created=[<新規 path>]`、`updated=[<既存 path で内容差し替えた>]`、`protected=[<Purpose / Core Concept など --force でも上書きされない path>]`、`conflicts=[]` |
| [ ] | Qdrant service が `localhost:6333` で起動していない状態で `spec-anchor-setup-system [--check-only]` を実行 | CLI exit code 0 (warning level、`status` は `"ok"` or `"degraded"`)。stdout JSON (§11.1.4): `production_readiness.status="blocked"`、`production_readiness.blocking_reasons=["qdrant_service_unavailable"]`、`production_readiness.checks=[{"name":"qdrant_service", "status":"failed", "reason_code":"qdrant_service_unavailable"}, ...]`、`providers=[{"name":"qdrant", "kind":"vector_store_service", "available":false, "url":<probed URL>, "error":"URLError" (or "OSError" 等の exception class 名のみ)}, ...]` |
| [ ] | `FlagEmbedding` / `qdrant_client` の Python package が import 不可で `spec-anchor-setup-system` を実行 | CLI exit code 0。stdout JSON: `production_readiness.status="blocked"`、`production_readiness.blocking_reasons=["flagembedding_missing"]` / `["qdrant_client_missing"]` (両方欠落時は両 reason を含む)、`providers=[{"name":"FlagEmbedding", "kind":"embedding_provider", "available":false, "version":null, "required":false}, ...]` |
| [ ] | `codex` / `claude` CLI が `PATH` 上に無い状態で `spec-anchor-setup-system` を実行 | CLI exit code 0。stdout JSON: `production_readiness.blocking_reasons=["agent_cli_unavailable"]` (codex / claude いずれも不在の場合に 1 件発火)、`agent_cli_entries.codex.cli.path=null` / `agent_cli_entries.claude.cli.path=null`、`agent_cli_entries.<agent>.cli.version=null` |
| [ ] | `spec-anchor` / `spec-anchor-watch` / `spec-anchor-setup-project` / `spec-anchor-setup-system` / `spec-anchor-slash` の console script のいずれかが `PATH` 上に無い状態で `spec-anchor-setup-system` を実行 | CLI exit code 0 (warning)。stdout JSON: `production_readiness.blocking_reasons=["console_script_missing", ...]` (不在 script 1 件につき 1 reason)、`console_scripts=[{"name":<name>, "available":false, "path":null}, ...]` (不在 script の名前は `console_scripts[]` 配列から識別) |
| [ ] | Setup-project 適用後で Agent CLI が skill / command を認識しない状態で `spec-anchor-setup-system --run-smoke` を実行 (Codex skill path mismatch / Claude command file 不在等) | CLI exit code 0 (warning のみ)。stdout JSON: `status="ok"` or `"degraded"`、`production_readiness.status="ready"` (Agent CLI 認識性は readiness check に含めず warning 扱い)、`diagnostics=[{"reason_code":<具体>, "message":<warning 文>, "agent_cli_entries":{...}}, ...]`、`agent_cli_entries.codex.project_skill_path=<期待 path>` / `agent_cli_entries.claude.project_command_path=<期待 path>`、`providers[<codex/claude>].version=<取得した CLI version>` |

### 11.2 slash command / skill レイヤーのエラー契約 (入力 / 出力)

slash command (`/spec-core` / `/spec-inject` / `/spec-realign`) と Codex skill (SPEC-anchor skill) は、Agent CLI (Claude Code / Codex) が利用者の発火を受けて内部で `spec-anchor` CLI を子プロセスとして実行し、その JSON 戻り値 (§11.1.1〜§11.1.4) を読み取って template (`spec_anchor/templates/.claude/commands/*.md` / `.codex/skills/spec-anchor/SKILL.md`) の手順に従って Agent が利用者に伝達する構成である。

「入力」は利用者が Agent CLI に与える発火条件 (cwd の状態 + 環境 + 利用者 prompt) を、「出力」は Agent CLI が内部で実行する `spec-anchor` CLI コマンドと、その JSON を受けて Agent が利用者に提示する情報を記述する。CLI JSON のフィールド名 / 文字列 template は §11.1.5 (CLI レイヤー表) を参照する。Agent CLI (Claude Code / Codex) が自然言語生成で構成する最終文言は LLM 出力に依存するため、本契約では「Agent が伝達すべき情報内容」を template の責務範囲として固定する。`spec-anchor-watch` / `spec-anchor-setup-system` / `spec-anchor-setup-project` は本レイヤー対象外 (slash command / skill 経由で発火しない、CLI 表 §11.1.5 を参照)。

| 確認 | 入力 | 出力 |
|---|---|---|
| [ ] | `<project_root>/.spec-anchor/config.toml` 不在で利用者が `/spec-core` (引数なし / `--all` / `--rebuild` 等) を発火 | Agent は `spec-anchor core [<flags>]` を実行。CLI 出力 (§11.1.5 該当行) の `diagnostics.config_error.message=".spec-anchor/config.toml not found under {root}"` を利用者に伝達し、復旧手順として `spec-anchor-setup-project --target <project_root>` の実行を提案<br><br>出力文言例:<br>`/spec-core` を実行しましたが、`.spec-anchor/config.toml not found under /path/to/project` のため失敗しました。先に `spec-anchor-setup-project --target /path/to/project` で project skeleton を初期化してから `/spec-core` を再実行してください。 |
| [ ] | `<project_root>/docs/core/purpose.md` (or `[core].purpose_file`) 不在で利用者が `/spec-core` を発火 | Agent は `spec-anchor core` を実行。CLI 出力の `diagnostics.config_error.message="core.purpose_file not found: {purpose_path}"` を利用者に伝達し、Purpose ファイル (`docs/core/purpose.md` 等) を作成して再実行する手順を提案<br><br>出力文言例:<br>`/spec-core` は失敗しました: `core.purpose_file not found: /path/to/project/docs/core/purpose.md`。`.spec-anchor/config.toml` の `[core].purpose_file` で指定された Purpose ファイルが見つかりません。ファイルを作成してから `/spec-core` を再実行してください。Purpose の内容は人間判断で記述します。 |
| [ ] | `<project_root>/docs/core/concept.md` (or `[core].concept_file`) 不在で利用者が `/spec-core` を発火 | Agent は `spec-anchor core` を実行。CLI 出力の `diagnostics.config_error.message="core.concept_file not found: {concept_path}"` を利用者に伝達し、Core Concept ファイル (`docs/core/concept.md` 等) を作成して再実行する手順を提案<br><br>出力文言例:<br>`/spec-core` は失敗しました: `core.concept_file not found: /path/to/project/docs/core/concept.md`。`.spec-anchor/config.toml` の `[core].concept_file` で指定された Core Concept ファイルが見つかりません。ファイルを作成してから `/spec-core` を再実行してください。Core Concept の内容は人間判断で記述します。 |
| [ ] | `[sources].include` の glob にマッチする Source Specs が 0 件で利用者が `/spec-core` を発火 | Agent は `spec-anchor core` を実行。CLI 出力の `diagnostics.config_error.message="sources.include did not match any Source Specs"` (or `"sources.include must be a non-empty list"`) を利用者に伝達し、`.spec-anchor/config.toml` の `[sources].include` 修正 or Source Specs の作成を促す<br><br>出力文言例:<br>`/spec-core` は失敗しました: `sources.include did not match any Source Specs`。`.spec-anchor/config.toml` の `[sources].include` (例: `docs/spec/**/*.md`) にマッチする Source Specs が 1 件もありません。Source Specs を該当 path 配下に作成するか、glob を実在 path に修正してから `/spec-core` を再実行してください。 |
| [ ] | Section Metadata の LLM 生成が一部 section で失敗 (必須 artifact 自体は揃う) 状態で利用者が `/spec-core` を発火 | Agent は `spec-anchor core` を実行。CLI 出力の `status="degraded"`、`failed_sections` 件数と `diagnostics.section_metadata_generation.failed_sections[i].reason_code` / `warnings` を利用者に伝達。利用者には「`status=degraded` だが必須 artifact は揃ったので継続可能、失敗 section の再生成は `/spec-core --all` で行える」と提示<br><br>出力文言例:<br>`/spec-core` は完了しましたが、12 section 中 2 section の Section Metadata 生成に失敗しました (`status=degraded`)。失敗 section: `docs/spec/api.md#0003-payments` (reason: llm_timeout), `docs/spec/auth.md#0001-session` (reason: schema_validation_error)。必須 artifact は揃っているため `/spec-inject` / `/spec-realign` は継続可能です。失敗 section を再生成する場合は `/spec-core --all` を実行してください。 |
| [ ] | Chapter Key Anchor 生成が失敗で利用者が `/spec-core` を発火 | Agent は `spec-anchor core` を実行。CLI 出力の `warnings=["Chapter Anchors LLM generation failed for {N} chapter(s); ..."]` を利用者に伝達。`canonical chapter_anchors.json` は前回値のまま保持される旨と、`spec-anchor core --all` での再試行を提案<br><br>出力文言例:<br>`/spec-core` は失敗しました: Chapter Anchors LLM generation failed for 3 chapter(s); canonical `chapter_anchors.json` is not updated。前回値が保持されているため既存の Chapter Key Anchor は引き続き参照可能ですが、最新 Source Specs の変更は未反映です。`/spec-core --all` で再試行してください。 |
| [ ] | Qdrant 設定済みで Qdrant に到達できない状態で利用者が `/spec-core` を発火 | Agent は `spec-anchor core` を実行。CLI 出力の `warnings=["Related Sections retrieval backend failure: {failure_reason}; ..."]` を利用者に伝達し、Qdrant 接続復旧 (例: `systemctl --user start qdrant`) + `spec-anchor core --rebuild` の実行手順を提案<br><br>出力文言例:<br>`/spec-core` は失敗しました: Related Sections retrieval backend failure: Qdrant connection refused at http://localhost:6333; canonical `related_sections` artifact is not updated。Qdrant service を起動 (`systemctl --user start qdrant`) してから `/spec-core --rebuild` を実行して retrieval index を作り直してください。 |
| [ ] | Qdrant section collection の upsert / verify が失敗状態で利用者が `/spec-core` を発火 | Agent は `spec-anchor core` を実行。CLI 出力の `warnings=["Source Retrieval Index update failed"]` または `["Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild"]` を利用者に伝達し、`spec-anchor core --rebuild` の実行を提案<br><br>出力文言例:<br>`/spec-core` は失敗しました: Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild。`/spec-core --rebuild` で section collection を作り直してください。前回 collection は drop されていないため、rebuild 完了まで既存 index は維持されます。 |
| [ ] | `<project_root>/.spec-anchor/config.toml` 不在で利用者が `/spec-inject "<task>"` (or 引数なしで会話区間から task 推論) を発火 | Agent は §8.3 の 4 path で最初の `spec-anchor inject-*` (通常 `inject-search` か `inject-conflicts`) を実行。CLI 出力 (§11.1.2 B) の `error.message=".spec-anchor/config.toml not found under {root}"` を利用者に伝達し、`spec-anchor-setup-project` での初期化を提案。Agentic Search は進めない<br><br>出力文言例:<br>`/spec-inject` は実行できません: `.spec-anchor/config.toml not found under /path/to/project`。先に `spec-anchor-setup-project --target /path/to/project` で project skeleton を初期化し、`/spec-core` を実行してから `/spec-inject` を再実行してください。Agentic Search は実行していません。 |
| [ ] | `freshness.json` が `status="blocked"` で `blocking_reasons` に dirty/stale/watcher 系 (`dirty_or_stale_source` / `stale_config_or_schema` / `watcher_running` / `watcher_queue_pending`) を含む状態で利用者が `/spec-inject` を発火 | Agent は最初の `spec-anchor inject-*` を実行。CLI 出力 (§11.1.2 A) の `recommended_next_action` (`"run /spec-core before /spec-inject"` / `"run /spec-core --all before /spec-inject"` / `"wait for watcher completion before /spec-inject"` のいずれか) と `blocking_reasons` を利用者に伝達。`/spec-core` 実行 or watcher 完了待ちを提案。`/spec-core` は Agent が自動実行しない (人間判断)<br><br>出力文言例:<br>`/spec-inject` は停止しました: `blocking_reasons=["dirty_or_stale_source"]`。Source Specs が変更されていますが保持物が更新されていません。`/spec-core` を実行して保持物を更新してから `/spec-inject` を再実行してください。Agentic Search は実行していません。 |
| [ ] | `freshness.json` が `status="blocked"` で `blocking_reasons=["pending_conflict"]` の状態で利用者が `/spec-inject` を発火 | Agent は最初の `spec-anchor inject-*` を実行。CLI 出力 (§11.1.2 A) の `pending_conflict_items` の各 item を §2.8 の構造 (conflict_id / severity / claims / why_conflicting / why_llm_cannot_decide / decision_options / source_refs / recommended_next_action) で利用者に提示し、人間判断を促す。各 item の `recommended_next_action` は default `"Ask a human to decide this conflict."`<br><br>出力文言例:<br>`/spec-inject` は停止しました: 未解決の Conflict Review Item が 2 件あります。<br>1. `conflict_id=cnf_001` (severity=high): claims=「A は同期処理」vs「A は非同期処理」、why_conflicting=「§3.2 と §5.1 が矛盾」、why_llm_cannot_decide=「両方の根拠が同等で LLM が判断できない」、decision_options=`option_a` / `option_b` / `defer`、source_refs=`docs/spec/api.md#0003`, `docs/spec/queue.md#0001`、recommended_next_action=`Ask a human to decide this conflict.`<br>2. `conflict_id=cnf_002` (severity=medium): ...<br>人間判断で各 conflict を `resolved` に決定してから `/spec-inject` を再実行してください。 |
| [ ] | `freshness.json` が `status="failed"` (`failed_required_artifact`) の状態で利用者が `/spec-inject` を発火 | Agent は最初の `spec-anchor inject-*` を実行。CLI 出力 (§11.1.2 A) の `recommended_next_action="run /spec-core or /spec-core --all before /spec-inject"` と `blocking_reasons=["failed_required_artifact"]`、`warnings` の失敗詳細を利用者に伝達し、`/spec-core --all` 実行を提案<br><br>出力文言例:<br>`/spec-inject` は停止しました: `blocking_reasons=["failed_required_artifact"]`。直前の `/spec-core` で必須 artifact (例: `chapter_anchors` / `related_sections` / `retrieval_index`) が失敗状態です。warnings: `Chapter Anchors LLM generation failed for 1 chapter(s)`。`/spec-core --all` で保持物を再構築してから `/spec-inject` を再実行してください。 |
| [ ] | `freshness.json` が `status="fresh"` (or `status="degraded"`) で利用者が `/spec-inject "<task>"` を発火 (正常経路) | Agent は §8.3 の 4 path Agentic Search を実行し、§8.5 の 4 区分 (今回守る制約 / 今回見るべき対象 / 関連先として確認したもの / 不確実性・人間確認) で制約セットを利用者に提示。CLI の raw JSON は貼らない。template (`spec-inject.md`) §6 の constraint 自己点検手順で `evidence_origin` enum / `support_refs` list / Conflict Review Item 由来の場合は `inject-conflicts` 返却範囲内 を Agent が確認<br><br>出力文言例:<br>## 今回守る制約<br>- API request body は `application/json` のみ受理 (出典: `docs/spec/api.md#0002-request-format`)<br>- 認証は session token を `Authorization: Bearer` header で送る (出典: `docs/spec/auth.md#0001-session`)<br><br>## 今回見るべき対象<br>- `src/api/handlers/payments.ts`<br>- `src/middleware/auth.ts`<br><br>## 関連先として確認したもの<br>- `docs/spec/queue.md#0001-async-jobs` (Related Section 上位 3 件のうち payments と非同期処理の関係を確認)<br><br>## 不確実性 / 人間確認が必要な点<br>- 失敗時 retry 回数が複数 section で矛盾。人間判断が必要。 |
| [ ] | `<project_root>/.spec-anchor/config.toml` 不在で利用者が `/spec-realign "<task>"` + answer candidate を発火 | Agent は `spec-anchor realign --answer-json '<json>'` を実行。CLI 出力 (§11.1.2 B) の `error.message=".spec-anchor/config.toml not found under {root}"` を利用者に伝達し、`spec-anchor-setup-project` での初期化を提案<br><br>出力文言例:<br>`/spec-realign` は実行できません: `.spec-anchor/config.toml not found under /path/to/project`。先に `spec-anchor-setup-project --target /path/to/project` で project skeleton を初期化し、`/spec-core` を実行してから `/spec-realign` を再実行してください。answer の整形は実行していません。 |
| [ ] | `freshness.json` が `status="blocked"` で `blocking_reasons` に dirty/stale/watcher 系 (`dirty_or_stale_source` / `stale_config_or_schema` / `watcher_running` / `watcher_queue_pending`) を含む状態で利用者が `/spec-realign` + answer candidate を発火 | Agent は `spec-anchor realign --answer-json '<json>'` を実行。CLI 出力 (§11.1.2 A) の `recommended_next_action` (`"run /spec-core before /spec-realign"` / `"run /spec-core --all before /spec-realign"` / `"wait for watcher completion before /spec-realign"` のいずれか) と `blocking_reasons` を利用者に伝達。`/spec-core` 実行 or watcher 完了待ちを提案。answer の整形は行わない (gate stop なので)<br><br>出力文言例:<br>`/spec-realign` は停止しました: `blocking_reasons=["dirty_or_stale_source"]`。Source Specs が変更されていますが保持物が更新されていません。`/spec-core` を実行してから `/spec-realign` を再実行してください。answer の整形は実行していません。 |
| [ ] | `freshness.json` が `status="blocked"` で `blocking_reasons=["pending_conflict"]` の状態で利用者が `/spec-realign` + answer candidate を発火 | Agent は `spec-anchor realign --answer-json '<json>'` を実行。CLI 出力 (§11.1.2 A) の `pending_conflict_items` の各 item を §2.8 の構造 (conflict_id / severity / claims / why_conflicting / why_llm_cannot_decide / decision_options / source_refs / recommended_next_action) で利用者に提示し、人間判断を促す。answer の整形は行わない (gate stop なので)<br><br>出力文言例:<br>`/spec-realign` は停止しました: 未解決の Conflict Review Item が 1 件あります。<br>1. `conflict_id=cnf_001` (severity=high): claims=「retry は 3 回」vs「retry は 5 回」、why_conflicting=「§4.1 と §6.2 が矛盾」、why_llm_cannot_decide=「両方が現行 Source Specs に存在」、decision_options=`option_a` / `option_b` / `merge` / `defer`、source_refs=`docs/spec/policy.md#0004`, `docs/spec/retry.md#0001`、recommended_next_action=`Ask a human to decide this conflict.`<br>人間判断で conflict を `resolved` に決定してから `/spec-realign` を再実行してください。answer の整形は実行していません。 |
| [ ] | `freshness.json` が `failed_required_artifact` の状態で利用者が `/spec-realign` + answer candidate を発火 | Agent は `spec-anchor realign --answer-json '<json>'` を実行。CLI 出力 (§11.1.2 A) の `status="failed"`、`recommended_next_action="run /spec-core or /spec-core --all before /spec-realign"` を利用者に伝達し、復旧手順を提案<br><br>出力文言例:<br>`/spec-realign` は停止しました: `status="failed"`、`blocking_reasons=["failed_required_artifact"]`。直前の `/spec-core` で必須 artifact が失敗状態です。`/spec-core --all` で保持物を再構築してから `/spec-realign` を再実行してください。answer の整形は実行していません。 |
| [ ] | 利用者が `/spec-realign "<task>"` を発火するが answer candidate を提示しない (Agent が `agent_answer` を構成できなかった) | Agent は `spec-anchor realign` を `--answer-json` 等無しで実行する。CLI は freshness gate を通過後、`agent_answer` が欠けることを検出して needs-answer 結果を返す (exit code 0): `status="fresh"`、`stop_reason="needs_agent_answer"`、`recommended_next_action="provide an Agent-generated answer candidate for /spec-realign"`、`should_stop=true`、`answer` field なし、`error` field なし (例外として raise しない経路)。Agent は「answer candidate が必要」と利用者に伝達し、追加情報を要求 or template (`spec-realign.md`) §7-§8 の手順で answer candidate を構成する<br><br>出力文言例:<br>`/spec-realign` には answer candidate (4 区分: 今回の回答案 / 根拠 / 関連先 / 不確実性) が必要ですが、提示されていません。先に `/spec-inject` で制約セットを取得し、それを踏まえた回答案を 4 区分構造で提示してから `/spec-realign` を再実行してください。 |
| [ ] | `freshness.json` が `status="fresh"` (or `status="degraded"`) で利用者が `/spec-realign "<task>"` + 4 区分 answer を発火 (正常経路) | Agent は `spec-anchor realign --answer-json '<json>'` を実行 (or `--answer-file` / `--answer-text`)。CLI JSON の `answer` field (RealignResult、§9.3 の 4 区分) を利用者に提示。constraint と answer 案が衝突する場合は `competing_conflicts` 相当 (Agent の自己判断) を「競合 / 不確実性 / 人間レビューが必要な点」セクションに必ず含める。raw JSON は貼らない<br><br>出力文言例:<br>## 今回の回答<br>payments handler では request body を `application/json` で受け、認証 token を `Authorization: Bearer` header から読み取る。失敗時は 3 回まで retry する。<br><br>## 根拠<br>- `docs/spec/api.md#0002-request-format` (今回守る制約に含まれる)<br>- `docs/spec/auth.md#0001-session` (今回守る制約に含まれる)<br><br>## 関連先<br>- `docs/spec/queue.md#0001-async-jobs` (Related Section 経由で確認)<br><br>## 競合 / 不確実性 / 人間レビューが必要な点<br>- retry 回数は §4.1 (3 回) と §6.2 (5 回) で矛盾あり。本回答は §4.1 を採用したが、人間判断が必要。 |

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
