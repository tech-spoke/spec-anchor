# SPEC-grag 外部設計書

> 版: draft
> 内部設計: `doc/DESIGN.ja.md`
> 記述ルール: `agent_doc/EXTERNAL_DESIGN_RULES.ja.md`

本書は SPEC-grag の外部契約を定義する。ユーザーが何を実行できるか、各コマンドが何を保証するか、どの情報を保持するか、LLM と CLI の責務をどこで分けるかを扱う。

## 1. 目的

LLM は、目の前にあるファイルや直近の会話に強く注意を向ける。その性質は実装作業では役に立つが、背景知識や上位目的の収集が足りないまま進むと、局所的な内容へ過剰に引っ張られ、設計意図からずれた回答や修正を出しやすい。

SPEC-grag の目的は、LLM が作業中に次を見失わないようにすることである。

- 本来の目的
- Core Concept
- 現在の課題に関係する Source Specs
- section ごとの概要と検索入口
- section 間の関連先
- 章単位の key anchor

この設計では、CLI が最終判断の主体にはならない。主導権は Agent / LLM にある。slash command は Agent / LLM に対して探索手順を指示し、CLI はその探索に使う保持物と検索機能を提供する。

## 2. 用語と範囲

### 2.1 Purpose

Purpose は、このプロジェクトが何のためにあるかを示す人間管理文書である。

含むもの:

- プロジェクトの存在理由
- 達成したい価値
- ユーザー体験や業務上の目的
- 個別仕様より上位にある判断基準

含まないもの:

- 具体的な section 要約
- 検索キー
- 実装詳細
- LLM が一時的に推測した制約

### 2.2 Source Specs

Source Specs は、SPEC-grag の対象となる仕様本文ファイル群である。`.spec-grag/config.toml` の `[sources].include` に一致する Markdown 文書を指す。

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
- section summary
- 検索キー
- LLM が一時的に推測した制約

### 2.4 Section Metadata

Section Metadata は、Source Specs の各 section に対して `/spec-core` が生成・更新する検索補助情報の総称である。単独で最終根拠にはしない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の根拠を確認する。

### 2.5 Section Search Keys

Section Search Keys は、検索 recall を上げるための **自然言語**の検索キーワードである。コードシンボル / API 名 / CLI コマンド / CLI option / ファイルパス / ALL_CAPS 定数 / PascalCase 型名は含まない。これらは Section Identifiers (§2.5.1) に分離する。

Section Search Keys は根拠ではない。検索に引っかけるための補助語であり、制約として扱ってはいけない。

### 2.5.1 Section Identifiers

Section Identifiers は、section 本文 + heading に出現する **コードシンボル / 固有技術名**を、正規表現で機械抽出した list である。LLM 判断を経由しない。

含むもの:

- API 名、関数名、CLI コマンド、CLI option (例: `bindContext`, `removeBindContext`, `productStoreGroup.replace`, `--rebuild`)
- ファイルパス、ALL_CAPS 定数、PascalCase 型名、ドット区切り技術名

Section Identifiers は根拠ではない。検索の補助 / 関連候補生成の手がかりであり、制約として扱ってはいけない。

### 2.6 Related Sections

Related Sections は、ある section を見たときに一緒に見るべき section の一覧である (依存先、影響先、同じ方針に属する section、変更時に確認すべき section、衝突しうる section)。

CLI は関連先を保持・返却するが、どこまで辿るかは Agent / LLM が判断する。

Related Sections は最終根拠ではないが単なる一時候補でもない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の該当箇所を根拠として確認する。

Related Sections が示す関係種別は `depends_on / impacts / prerequisite / same_policy / see_also` のいずれかである。矛盾の疑いがある pair は、Related Sections 段階では確定させず、Conflict Review (§2.7) で判定する。

### 2.7 Conflict Review Item

Conflict Review Item は、Purpose、Core Concept、または Source Specs の根拠同士が同時に満たせない疑いがあり、LLM が既存根拠だけでは解消できない場合に、人間へ判断を求める項目である。

含むもの:

- conflict の対象となる根拠
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

### 2.8 Chapter Key Anchor

Chapter Key Anchor は、章全体の重要テーマ、判断軸、主要 section への入口を、LLM が章単位で生成する。Agentic Search の章単位エントリポイントとして使う。

各章について以下が生成される:

- 章全体の抽象化された要約
- 章の重要テーマ (key_topics)
- 章内で判断軸となる主要 section
- 章全体で守るべき読み方 (notes)

Chapter Key Anchor は最終根拠ではない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の該当箇所を根拠として確認する。

### 2.9 Agentic Search

Agentic Search は、Agent / LLM が検索結果を見ながら追加検索、関連先参照、根拠確認を繰り返す行動を指す。

この設計では、Agentic Search は CLI の責務ではない。slash command の説明に探索手順を書き、Agent / LLM がそれに従って必要な検索を行う。

## 3. 保持物

SPEC-grag は、次の情報を保持する。

| 保持物 | 更新主体 | 役割 |
|---|---|---|
| Purpose | 人間 | 本来の目的。ビジネスゴール、UX の根幹、システムが存在する理由 |
| Core Concept | 人間 | 全体の判断軸、承認済みの設計原則 |
| Section Summary | `/spec-core` | 各 section が何について書かれているかを示す |
| Section Search Keys | `/spec-core` | 自然言語で section を検索するためのキーワード |
| Section Identifiers | `/spec-core` | section 本文に出現するコードシンボル / 固有技術名の機械抽出リスト |
| Related Sections | `/spec-core` | 一緒に見るべき section、依存・影響・関連先 |
| Conflict Review Items | `/spec-core` / 人間 | LLM が解決できない仕様 conflict の人間判断待ち項目 |
| Chapter Key Anchor | `/spec-core` | 章全体の重要テーマ、判断軸、主要 section への入口 |

Purpose と Core Concept は人間が更新する。SPEC-grag はこれらを自動更新しない。

SPEC-grag は Core Concept 乖離通知を保証しない。Source Specs の進化により Core Concept が陳腐化した場合でも、自動更新や自動通知は行わず、人間が必要に応じて Core Concept を更新する。

## 4. 責務境界

### 4.1 Human

- Purpose の作成・更新
- Core Concept の作成・更新
- 最終的な仕様判断
- Conflict Review Item の判断

### 4.2 Agent / LLM

- 会話区間と課題を解釈する
- 検索キーを作り、保持物を検索する
- 検索結果を見ながら Agentic Search を行う
- 今回の課題に必要な制約を生成する
- LLM だけでは解決できない conflict を人間判断待ちとして提示する
- `/spec-realign` では、制約に従って回答または修正案を作る

### 4.3 CLI / SPEC-grag

- 設定ファイルを読み、保持物を生成・更新する
- Agent / LLM が渡した検索キーに対して検索結果を返す
- 保持物が最新かどうかを判定する

CLI / SPEC-grag は次を担当しない。

- Agentic Search の探索方針を自律的に決める
- 今回の課題に必要な制約を最終生成する
- conflict を人間抜きで最終裁定する
- Purpose / Core Concept を自動更新する

## 5. コマンド体系

| コマンド | 目的 | 詳細 |
|---|---|---|
| `/spec-core` | 保持物を生成・更新する | §7 |
| `/spec-inject` | 課題に対する制約を生成する (回答は出さない) | §8 |
| `/spec-realign` | 制約を生成し、課題に回答する | §9 |
| `spec-grag-watch` | Source Specs 変更を監視し background で更新する | 下記 |
| `spec-grag-setup-project` | プロジェクトに設定と Agent 入口を配置する | §5.2.1 |
| `spec-grag-setup-system` | 外部依存の導入状態を確認する | §5.2.2 |

#### spec-grag-watch

Source Specs の変更を検知し、background で保持物を更新する。

```
spec-grag-watch [project_root]
```

| オプション | 既定 | 内容 |
|---|---|---|
| `project_root` (位置引数) | `.` | プロジェクトルート |
| `--once` | — | 1 回だけ scan して終了する (poll ループに入らない) |
| `--interval-sec <秒>` | 2.0 | 変更がないときの poll 間隔 |
| `--debounce-sec <秒>` | 1.0 | 変更検知後、update を開始するまでの待ち時間 (連続変更をまとめる) |
| `--stale-lock-sec <秒>` | 300 | lock file がこの秒数を超えたら stale とみなして回収する |
| `--max-runs <回数>` | 無制限 | 指定回数だけ update したら終了する |

出力: 各 update の結果を JSON で標準出力に出す。watcher 実行中は `/spec-inject` と `/spec-realign` は停止する。

### 5.1 Agent 別 command / skill 入口

SPEC-grag は、同じ CLI 契約を、各 Agent CLI が認識する入口形式で提供する。

| Agent 環境 | 入口形式 | 配置先 |
|---|---|---|
| Claude Code / Claude CLI | command template | `<project>/.claude/commands/` |
| Codex CLI | skill (SKILL.md) | `<codex_install_path>/skills/spec-grag/` |

入口形式は Agent CLI ごとに固定であり、利用者が選ぶ対象ではない。配置は Project Setup Script (§5.2.1) が行う。

### 5.2 Setup Script

#### 5.2.1 Project Setup Script

対象プロジェクトに SPEC-grag の設定ファイルと Agent 入口を配置する。

```
spec-grag-setup-project --target <project-root>
```

入力:

| オプション | 既定 | 内容 |
|---|---|---|
| `--target <path>` | `.` (カレントディレクトリ) | プロジェクトルート |
| `--agent <codex\|claude\|both>` | `both` | Agent 入口の配置先。`claude` は `.claude/commands/` に command template、`codex` は Codex skill を配置 |
| `--codex-install <user\|project>` | `user` | Codex skill の配置先。`user` は `~/.codex/skills/`、`project` は `<target>/.codex/skills/` |
| `--dry-run` | — | 作成・更新予定を表示するだけで変更しない |
| `--force` | — | 既存ファイルの上書きを許可する |
| `--no-init-core-files` | — | Purpose / Core Concept の雛形を作成しない |

処理:

- `.spec-grag/config.toml` と `.spec-grag/.gitignore` を作成する
- Purpose / Core Concept の雛形を作成する (未存在の場合。`--no-init-core-files` で抑止可)
- `--agent` に応じて Claude command template / Codex skill を配置する

出力: 結果を JSON で標準出力に出す。exit code は成功なら 0、失敗なら非 0。

安全性:

- 既存ファイルがある場合は差分を示して停止する。`--force` を指定した場合のみ上書きする
- `/spec-core` は自動実行しない。setup 後にユーザーが `/spec-core` を明示実行する

#### 5.2.2 System Setup Script

SPEC-grag の動作に必要な外部依存が揃っているかを確認する。

```
spec-grag-setup-system
```

入力: なし (インストール済み環境を対象とする)

確認対象:

- SPEC-grag CLI が実行可能か
- embedding provider が読み込めるか
- vector store に接続できるか
- Agent CLI (Codex / Claude) が利用可能か

出力: 結果を JSON で標準出力に出す。

- 全て揃っている場合: status = ready
- 不足がある場合: status = blocked、不足理由を出力

exit code: ready なら 0、blocked なら非 0。

オプション:

- `--check-only`: 確認のみ行い何も変更しない

System Setup Script は対象プロジェクトの Source Specs、Purpose、Core Concept、生成済み保持物を変更しない。

## 6. 共通契約

### 6.1 設定ファイル配置

プロジェクトごとの設定は `<project_root>/.spec-grag/config.toml` に置く。親ディレクトリへの自動探索はしない。

```text
<project_root>/
└── .spec-grag/
    └── config.toml
```

### 6.2 保持物の鮮度確認

`/spec-inject` と `/spec-realign` は、保持物が最新でない場合は停止し、理由と対処方法を表示する。

| 状態 | `/spec-inject` / `/spec-realign` の動作 | 対処 |
|---|---|---|
| 保持物は最新 | 続行する | — |
| Source Specs が変更されたが `/spec-core` で更新されていない | 停止する | `/spec-core` を実行する |
| `spec-grag-watch` が実行中または未処理の変更が残っている | 停止する | watcher の完了を待つ |
| 人間判断待ちの Conflict Review Item がある | 停止する | Conflict Review Item に判断を返す |
| 一部の保持物の生成に失敗している | 停止する | `/spec-core --all` で再生成する |
| 一部の保持物が欠けているが必須分は使える | warning を表示し続行できる | 必要なら `/spec-core` で補完する |

Source Specs の変更と未解決 Conflict が同時にある場合は、まず `/spec-core` で保持物を更新する。更新後も残る Conflict だけが人間判断の対象になる。

`/spec-inject` と `/spec-realign` は `/spec-core` を自動実行しない。保持物の更新はユーザーが `/spec-core` を明示実行するか、`spec-grag-watch` に任せる。

### 6.3 Watcher の snapshot 分離

`spec-grag-watch` は、1 回の更新で処理する Source Specs の範囲を開始時点で固定する。更新中に追加の変更が入った場合、その変更は次回に回す。更新中および未処理の変更が残っている間、`/spec-inject` と `/spec-realign` は停止する。

### 6.4 Conversation Context

`/spec-inject` と `/spec-realign` は、明示された課題プロンプトだけでなく、現在の会話区間も入力として扱う。ただし、会話区間を解釈する主体は Agent / LLM である。

会話区間は検索キー生成と制約生成の入力であり、仕様上の根拠ではない。最終根拠は Purpose、Core Concept、Source Specs のどれに由来するかを区別する。

### 6.5 生テキスト投入の制限

SPEC-grag は、Source Specs 本文を無条件に LLM コンテキストへ丸ごと投入しない。

Agent / LLM は Agentic Search で必要な Source Specs snippet を読むことができる。ただし、読んだ本文を無整理のまま最終回答の前提へ混ぜてはいけない。最終的に使う制約は、今回の課題に必要なものとして生成し、根拠を示す。

全文を投入するのは、ユーザーが明示的に全文レビューを求めた場合に限る。

### 6.6 Source Specs の section 化規約

SPEC-grag は、Source Specs の Markdown 見出しを section 境界として扱う。

section 化する最大見出し深さは `.spec-grag/config.toml` の `[section].max_heading_level` で指定する。設定値より深い見出しは独立 section にせず、直近の親 section の本文に統合する。

標準設定は `max_heading_level = 4` とする。

```text
## Feature                        -> section
### Field group                   -> section
#### Image upload                 -> section
##### Internal helper             -> parent section body
```

## 7. `/spec-core`

### 7.1 目的

`/spec-core` は、Purpose / Core Concept 以外の保持物を生成・更新するためのコマンドである。

通常実行では、Source Specs の変更分だけを更新する。

| フラグ | 動作 |
|---|---|
| (なし) | 変更された section だけを更新する |
| `--all` / `-a` | 全ての保持物を再生成する。ただし検索 index は変更がなければ再利用する |
| `--rebuild` | `--all` に加え、検索 index も完全に作り直す |

`/spec-core` は設定ファイルで指定された provider をそのまま使う。指定された provider が失敗した場合は、別の provider に黙って切り替えず、失敗として報告する。

### 7.2 入力

| 入力 | 内容 |
|---|---|
| `.spec-grag/config.toml` | 対象ソース、Purpose、Core Concept、LLM / 検索設定 |
| Source Specs | `sources.include` で指定された仕様ファイル |
| Purpose | 読み取り専用の上位目的 |
| Core Concept | 人間更新対象 |
| `--all` / `-a` | 全ての保持物を再生成する |
| `--rebuild` | `--all` に加え、検索 index を完全に作り直す |

### 7.3 動作

```text
/spec-core
  -> Source Specs を読み、変更された section を特定する
  -> 変更 section の Summary / Search Keys を更新する
  -> 検索 index を更新する
  -> Related Sections を更新する
  -> 矛盾の疑いがある pair を検査する
  -> LLM が解決できない矛盾を Conflict Review Item として記録する
  -> Chapter Key Anchor を更新する
  -> 結果を出力する
```

Purpose と Core Concept は常に読み取り専用である。`/spec-core` はこれらを自動更新しない。

### 7.4 出力

`/spec-core` は結果を JSON で標準出力に出す。主な出力項目:

- 更新された section / source の一覧
- 失敗した section / source の一覧
- 検出された Conflict Review Item
- 未解決の Conflict の数
- 保持物の鮮度状態
- warning

### 7.5 Conflict Review

LLM が Source Specs 間の矛盾を検出したが、既存根拠だけでは解決できない場合、Conflict Review Item を作成する。未解決の Conflict Review Item がある間、`/spec-inject` と `/spec-realign` は停止する。

人間の判断肢:

- 片方の仕様を優先する
- 両方を満たす条件分岐を指示する
- 矛盾ではないとして退ける
- Source Specs の修正が必要として差し戻す
- 今回は判断保留にする
- 今回の課題内だけの一時判断にする

判断保留は conflict を解決しない。`/spec-inject` と `/spec-realign` はその conflict を無視して進んではいけない。

人間が判断した Conflict Review Item は resolution として保持される。ただし、判断時の根拠となった Source Specs が変更された場合、その resolution は無効になる。一時判断 (task_scope) は後続セッションの恒久根拠にはしない。

SPEC-grag は resolution を Source Specs / Purpose / Core Concept へ自動反映しない。反映は人間の作業である。

## 8. `/spec-inject`

### 8.1 目的

`/spec-inject` は、Agent / LLM が現在の課題に必要な制約を生成して会話に注入するためのコマンドである。課題に対する最終回答は作らない。

### 8.2 入力

| 入力 | 内容 |
|---|---|
| 会話区間 | 現在のユーザー発話、直近の会話区間、進行中の作業対象 |
| `<課題プロンプト>` | 任意。指定された場合は中心課題として扱う |
| 設定ファイル | 対象プロジェクト設定 |
| 保持物 | Purpose / Core Concept / Section Metadata / Chapter Key Anchor / Conflict Review Items |

### 8.3 Agent / LLM が行う作業 (4 path)

Agent / LLM は、課題の性質に応じて次の 4 path を組み合わせて使う。各 path は必須ではなく許可で、Agent が選んで使い分ける。

#### path ① section 検索

1. 会話区間 / 課題プロンプトから検索キーを選定し、検索を実行する
2. 検索結果の section 概要 (heading / summary / search keys / identifiers) を読み、関連候補を選ぶ
3. 関連候補の Related Sections を辿り、さらに関係する section を探す
4. 必要なら Source Specs ファイル本文を Read で確認し、制約根拠を抽出する
5. 3-4 を繰り返す。制約に関係しないと判断できた時点で打ち切る

#### path ② 章単位エントリ

1. Chapter Key Anchor を読み、関係しそうな章を key_topics / important_sections で特定する
2. 特定された章配下の section を path ① と同様に探索する

#### path ③ Purpose / Core Concept からの制約抽出

1. Purpose / Core Concept の全文を読み、課題に該当する制約根拠を抽出する

#### path ④ resolved Conflict Review Items の確認

1. 解決済みかつ有効な Conflict Review Items を取得する
2. 制約に関係する場合、制約に組み込む

### 8.3.1 path 選択の指針

| 課題タイプ | 主 path | 補強 |
|---|---|---|
| 具体的 API / 識別子 | ① | ③、④ |
| 全体方針 / 抽象的 | ② | ①、③、④ |
| Purpose / Core Concept 直接質問 | ③ | ①、② |
| 過去判断の継続 | ④ | ①、③ |

Agentic Search は Agent / LLM の責務である。CLI は検索結果を返すだけであり、探索方針を自律的に決めない。

### 8.4 CLI が提供する操作

| 操作 | コマンド | 戻り値 |
|---|---|---|
| 鮮度確認 | `spec-grag inject "<task>"` | 保持物の鮮度状態と停止理由 |
| section 検索 | `spec-grag inject-search "<query>"` | 検索にヒットした section の一覧 (概要 / 関連先を含む) |
| section 詳細取得 | `spec-grag inject-section "<id>" [<id>...]` | 指定した section の詳細情報 |
| 章 anchor 取得 | `spec-grag inject-chapters` | 章単位の要約 / key_topics / important_sections |
| Purpose / Core Concept 取得 | `spec-grag inject-purpose` | Purpose + Core Concept の全文 |
| Conflict Review Items 取得 | `spec-grag inject-conflicts` | 解決済みかつ有効な Conflict Review Items |
| 制約検証 | `spec-grag inject "<task>" --constraints '<JSON>'` | 検証済み制約セット |

### 8.5 通常出力

保持物が最新の場合、`/spec-inject` は Agent / LLM が生成した制約セットを出力する。

出力は次を区別する:

```text
今回守る制約
  - <制約>
    根拠: Purpose / Core Concept / Source Specs / Conflict Review Item
    参照補助: Section Summary / Chapter Key Anchor / Related Sections

今回見るべき対象
  - <section または topic>

採用しなかったもの
  - <候補> と理由

不確実性 / 人間確認
  - <確認すべき点>
```

制約を提示する場合は、根拠の種類 (Purpose / Core Concept / Source Specs / Conflict Review Item)、参照先、この課題でどこに効くかを欠かしてはいけない。

Section Summary、Search Keys、Related Sections、Chapter Key Anchor だけを根拠として制約を確定してはいけない。

### 8.6 停止時出力

保持物が最新でない場合、`/spec-inject` は制約生成を行わず、停止理由と対処方法を表示する (§6.2 参照)。

## 9. `/spec-realign`

### 9.1 目的

`/spec-realign` は、`/spec-inject` と同じ手順で制約を生成し、その制約に従って課題への回答または修正案を作るためのコマンドである。

### 9.2 動作

1. §8 と同じ手順で制約を生成する
2. 制約に従って回答または修正案を作る
3. 結果を出力する

### 9.3 Answer 生成契約

LLM は、生成した制約を守って回答する。制約と矛盾する案を出す場合は、その矛盾を隠さず明示し、人間レビューが必要な点として扱う。

出力は次を区別する:

```text
今回守る制約
今回扱う修正候補または検討対象
競合 / 不確実性 / 人間レビューが必要な点
課題プロンプトへの回答または修正案
```

## 10. 設定ファイル

### 10.1 設定項目

対象プロジェクトのルートに `.spec-grag/config.toml` を置く。

| table | key | 必須性 | 内容 |
|---|---|---|---|
| `[sources]` | `include` | 必須 | Source Specs として読む Markdown glob。複数指定可 |
| `[sources]` | `exclude` | 任意 | `include` から除外する glob |
| `[core]` | `purpose_file` | 必須 | Purpose ファイルのパス |
| `[core]` | `concept_file` | 必須 | Core Concept ファイルのパス |
| `[section]` | `max_heading_level` | 任意 | section 化する最大 Markdown heading level。標準は `4` |
| `[llm]` | `default_provider` / `fallback_order` | 任意 | `/spec-core` が使う LLM provider |
| `[llm.providers.<id>]` | `provider` / `command` / `model` / `effort` / `timeout_sec` / `max_retries` | 必須 | LLM provider 定義。少なくとも 1 つ必要 |

その他の設定 (`[embedding]`、`[vector_store]`、`[retrieval]`、`[limits]`、`[watcher]`、`[llm.stage_routing]` 等) は内部設計 (`doc/DESIGN.ja.md`) を参照。

### 10.2 最小構成例

```toml
[sources]
include = ["docs/spec/**/*.md"]

[core]
purpose_file = "docs/core/purpose.md"
concept_file = "docs/core/concept.md"

[section]
max_heading_level = 4

[llm]
default_provider = "codex"

[llm.providers.codex]
provider = "codex_cli"
command = "codex"
model = "gpt-5.4-mini"
effort = "low"
timeout_sec = 120
max_retries = 1
```

### 10.3 配置例

```text
your-project/
├── .spec-grag/
│   └── config.toml
├── .claude/
│   └── commands/                 # Claude Code 用
│       ├── spec-core.md
│       ├── spec-inject.md
│       └── spec-realign.md
├── docs/
│   ├── core/
│   │   ├── purpose.md
│   │   └── concept.md
│   └── spec/                     # Source Specs
│       └── ...
```

### 10.4 `.gitignore` 推奨設定

`.spec-grag/config.toml` と Agent 入口 (`.claude/commands/spec-*.md` 等) は Git 管理してよい。生成済み保持物は Git 管理しない。

```gitignore
.spec-grag/context/
.spec-grag/state/
.spec-grag/cache/
.spec-grag/tmp/
```

## 11. エラー契約

| 状態 | 動作 |
|---|---|
| 設定ファイルが見つからない | エラー終了し、設定ファイル作成を促す |
| Purpose / Core Concept / Source Specs が見つからない | エラー終了する |
| 保持物の一部生成に失敗 | 失敗した section を出力し、必須分が揃う場合は warning 付きで続行可能 |
| 検索 index の更新に失敗 | 失敗として報告する |
| Source Specs が変更されたが未更新 | `/spec-inject` / `/spec-realign` は停止し、`/spec-core` を促す |
| 未解決の Conflict Review Item がある | `/spec-inject` / `/spec-realign` は停止し、判断肢を提示する |
| watcher が実行中 | `/spec-inject` / `/spec-realign` は停止し、完了を待つ |
