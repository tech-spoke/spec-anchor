# SPEC-grag 外部設計書

> 版: draft
> 位置づけ: 軽量な仕様コンテキスト方式の外部設計。既存 `doc/EXTERNAL_DESIGN.ja.md` のうち、目的、コマンド体系、freshness、section 化、承認境界など再利用できる契約を引き継ぎ、フル GRAG 前提の内部構築は前提にしない。

本書は SPEC-grag の外部契約を定義する。ここでは、ユーザーが何を実行できるか、各コマンドが何を保証するか、どの情報を保持するか、LLM と CLI の責務をどこで分けるかを扱う。

内部実装、embedding provider、LLM provider、保存形式、検索アルゴリズム、slash command の具体プロンプトは詳細設計に委ねる。対応する内部設計は `doc/DESIGN.ja.md` に置く。

## 1. 目的

LLM は、目の前にあるファイルや直近の会話に強く注意を向ける。その性質は実装作業では役に立つが、背景知識や上位目的の収集が足りないまま進むと、局所的な内容へ過剰に引っ張られ、設計意図からずれた回答や修正を出しやすい。

SPEC-grag の目的は、LLM が作業中に次を見失わないようにすることである。

- 本来の目的
- Core Concept
- 現在の課題に関係する Source Specs
- section ごとの概要と検索入口
- section 間の関連先
- 章単位の key anchor

この設計でいう軽量とは、LLM 呼び出しが常に少ないという意味ではない。旧 GRAG 版にあった property graph、entity relation graph、hierarchical cluster、Concept 自動更新、広範な conflict 承認フロー、実行モード分岐を標準経路から外し、永続化する構造と人間承認の待ち時間を減らすという意味である。ただし、LLM が解決できない conflict に限り、Conflict Review Item として人間判断待ちを作る。これは標準契約であり、warning-only の逃げ道ではない。

section 数が多いプロジェクトでは、`/spec-core --all` の LLM 呼び出しはなお重くなりうる。そのため実装は、section hash による incremental update、複数 section の batch 生成、変更 chapter だけの再生成を基本にする。

この設計では、CLI が最終判断の主体にはならない。主導権は Agent / LLM にある。slash command は Agent / LLM に対して探索手順を指示し、CLI はその探索に使う保持物と検索機能を提供する。

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

- 具体的な section 要約
- 検索キー
- 実装詳細
- LLM が一時的に推測した制約

### 2.2 Source Specs

Source Specs は、SPEC-grag の対象となる仕様本文ファイル群である。`.spec-grag/config.toml` の `[sources].include` に一致する Markdown 文書を指す。

Source Specs は、現在の仕様本文であり、今回の課題に対して「守るべき既存仕様」になる場合も、「修正対象」になる場合もある。

含むもの:

- 仕様章ファイル
- section 化された本文
- source span を持つ根拠 snippet

含まないもの:

- Purpose
- Core Concept
- Section Metadata
- Chapter Key Anchor
- 会話区間上の仮説

### 2.3 Core Concept

Core Concept は、プロジェクト全体の判断軸、承認済みの設計原則、不変に近い方針を指す。

既存設計書で `Concept` と呼んでいたものに相当する。本書では、単なる概念抽出結果ではなく、人間が読む中核方針であることを明確にするため `Core Concept` と呼ぶ。

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

Section Metadata は、本書での整理用の呼び名である。Source Specs の各 section に対して `/spec-core` が生成・更新する検索補助情報を指す。

含むもの:

- section summary
- section search keys
- related sections

含まないもの:

- Source Specs の本文そのもの
- Core Concept
- 章ごとの key anchor
- property graph
- 多段 graph traversal
- LLM が生成した今回限りの制約

Section Metadata は、LLM が必要な文脈へ到達するための入口であり、単独で最終根拠にはしない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の根拠を確認する。

### 2.5 Section Summary

Section Summary は、その section が何について書いているかを短く表す要約である。

目的は、LLM が検索結果を見たときに、その section を深掘りすべきか判断しやすくすることである。

### 2.6 Section Search Keys

Section Search Keys は、検索 recall を上げるための語句である。

含むもの:

- 日本語 / 英語の言い換え
- 同義語
- 機能名
- 実装名
- ファイル名
- API 名
- 設定名
- 状態名
- warning / error 名
- ユーザーが使いそうな自然語

Section Search Keys は根拠ではない。検索に引っかけるための補助語であり、制約として扱ってはいけない。

### 2.7 Related Sections

Related Sections は、ある section を見たときに一緒に見るべき section の一覧である。

含むもの:

- 依存先
- 影響先
- 同じ方針に属する section
- 変更時に確認すべき section
- 衝突しうる section

含まないもの:

- full graph relation
- 無制限の多段 traversal
- CLI による自律的な Agentic search

Related Sections は、LLM が Agentic search を行うときの足場である。CLI は関連先を保持・返却するが、どこまで辿るかは Agent / LLM が判断する。

Related Sections は最終根拠ではないが、単なる一時候補でもない。`/spec-core` が生成・保持する「一緒に確認すべき section の参照補助リンク」として扱う。制約として採用する場合は、Purpose、Core Concept、または Source Specs の該当箇所を根拠として確認する。

`/spec-core` は、LLM に全文から関連先を自由発見させるのではなく、heading、Section Summary、Section Search Keys、明示リンク、shared identifier、同一 chapter、hybrid retrieval などから広めの関連候補を作り、LLM が候補内から理由付きで Related Sections を選ぶ。Related Sections には、少なくとも関連理由、関係の種類を示す hint、根拠語を保持する。

### 2.8 Conflict Review Item

Conflict Review Item は、Purpose、Core Concept、または Source Specs の根拠同士が同時に満たせない疑いがあり、LLM が既存根拠だけでは解消できない場合に、人間へ判断を求める項目である。

含むもの:

- conflict の対象となる source refs
- それぞれの主張の要約
- 矛盾していると判断した理由
- 関連する Related Sections / search evidence
- LLM が解決できない理由
- 人間に選んでほしい判断肢
- status

含まないもの:

- Core Concept の自動更新
- Source Specs の自動修正
- LLM による最終裁定

Conflict Review Item は単なる warning ではない。status が `pending` の項目は人間判断待ちであり、`/spec-inject` と `/spec-realign` はその状態を無視して制約生成や回答生成へ進んではいけない。

### 2.9 Chapter Key Anchor

Chapter Key Anchor は、章全体の重要テーマ、判断軸、主要 section への入口を短くまとめた情報である。

Section Summary だけでは、章全体の意図や優先順位が薄くなる場合がある。Chapter Key Anchor は、その章を読むときのミニ目次と注意点として使う。

含むもの:

- 章の主要テーマ
- 章内の主要 section
- 重要語
- 章全体で守るべき読み方
- 関連しやすい領域

含まないもの:

- 人間承認済み Core Concept の代替
- Source Specs 本文の代替
- graph cluster

### 2.10 Agentic Search

Agentic Search は、Agent / LLM が検索結果を見ながら追加検索、関連先参照、根拠確認を繰り返す行動を指す。

この設計では、Agentic Search は CLI の責務ではない。slash command の説明に探索手順を書き、Agent / LLM がそれに従って必要な検索を行う。

## 3. 保持物

SPEC-grag は、次の情報を保持する。

| 保持物 | 更新主体 | 役割 |
|---|---|---|
| Purpose | 人間 | 本来の目的。ビジネスゴール、UX の根幹、システムが存在する理由 |
| Core Concept | 人間 | 全体の判断軸、承認済みの設計原則 |
| Section Summary | `/spec-core` | 各 section が何について書かれているかを示す |
| Section Search Keys | `/spec-core` | retrieval に引っかけるための検索語 |
| Related Sections | `/spec-core` | 一緒に見るべき section、依存・影響・関連先 |
| Conflict Review Items | `/spec-core` / 人間 | LLM が解決できない仕様 conflict の人間判断待ち項目 |
| Chapter Key Anchor | `/spec-core` | 章全体の重要テーマ、判断軸、主要 section への入口 |
| Source Retrieval Index | `/spec-core` | Source Specs 本文を hybrid retrieval するための index |

Purpose と Core Concept は人間が更新する。SPEC-grag はこれらを自動更新しない。

SPEC-grag は Core Concept 乖離通知を保証しない。Source Specs の進化により Core Concept が陳腐化した場合でも、自動更新や自動通知は行わず、人間が必要に応じて Core Concept を更新する。

`/spec-core` は、Purpose と Core Concept 以外の保持物を生成・更新する。`--all` なしでは section hash に基づいて変更 section を中心に更新し、`--all` または `-a` ではコマンド更新対象を再生成する。

## 4. 責務境界

### 4.1 Human

Human は次を担当する。

- Purpose の作成・更新
- Core Concept の作成・更新
- 最終的な仕様判断
- Conflict Review Item の判断
- LLM が生成した制約や回答の採否判断

### 4.2 Agent / LLM

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

### 4.3 CLI / SPEC-grag

CLI / SPEC-grag は次を担当する。

- 設定ファイルを読む
- Source Specs の section hash を管理する
- Section Metadata を生成・保持する
- Conflict Review Item を生成・保持する
- Chapter Key Anchor を生成・保持する
- Source Retrieval Index を生成・保持する
- freshness を判定する
- Agent / LLM が渡した検索キーに対して検索結果を返す
- 指定された section summary、related sections、chapter anchor を返す

CLI / SPEC-grag は次を担当しない。

- 会話区間を最終解釈する
- Agentic Search の探索方針を自律的に決める
- 今回の課題に必要な制約を最終生成する
- conflict を人間抜きで最終裁定する
- Answer を自由生成する
- Purpose / Core Concept を自動更新する

## 5. コマンド体系

SPEC-grag は、ユーザー向け slash command、Source Specs 変更を background で処理する watcher process、導入を支援する setup script を提供する。

| コマンド | オプション / 引数 | 目的 | 回答生成 |
|---|---|---|---|
| `/spec-core` | `--all` / `-a` / conflict decision | Purpose / Core Concept 以外の保持物を生成・更新し、Conflict Review Item への人間判断を記録する | しない |
| `/spec-inject` | `[<課題プロンプト>]` | Agent / LLM が会話区間と課題から検索・参照・Agentic Search を行い、今回必要な制約を生成して注入する | しない |
| `/spec-realign` | `[<課題プロンプト>]` | `/spec-inject` 相当の制約生成を行った上で、課題を解決する | する |
| `spec-grag-watch` | `[project_root]` / `--once` / `--interval-sec` / `--debounce-sec` / `--stale-lock-sec` / `--max-runs` | Source Specs 変更を監視し、background で `/spec-core` 相当の incremental update を行う | しない |
| `spec-grag-setup-project` | `--target <project_root>` / `--agent codex\|claude\|both` / `--dry-run` / `--force` / `--no-init-core-files` | 対象プロジェクトに `.spec-grag/config.toml`、Agent 別 command template、Purpose / Core Concept 雛形、ignore 設定を配置する | しない |
| `spec-grag-setup-system` | `--check-only` / `--mode editable\|archive\|install` / `--run-smoke` | SPEC-grag 本体の導入、実行ファイル、package data、依存ツール、smoke を確認・準備する | しない |

slash command と watcher process は、対象プロジェクトルートで実行する。実行時には、そのプロジェクトルート直下の `.spec-grag/config.toml` を読み込む。

setup script は runtime command ではない。`/spec-inject` や `/spec-realign` の実行中に自動起動してはいけない。

### 5.1 Agent 別 command template

SPEC-grag は、同じ外部コマンド契約に対して Agent / LLM 別の command template を提供する。

ここでいう command template は、各 Agent 環境に配置する `/spec-core`、`/spec-inject`、`/spec-realign` 用の prompt / metadata ファイルである。Agent 環境が skill 形式を使う場合も、役割は同じである。

提供予定の版:

| 版 | 対象 | 役割 |
|---|---|---|
| CODEX 版 | Codex / Codex CLI | Codex の command / skill 形式に合わせて、SPEC-grag CLI を呼び出し、Agent / LLM 主導の探索手順を指示する |
| CLAUDE 版 | Claude Code / Claude CLI | Claude の command / skill 形式に合わせて、SPEC-grag CLI を呼び出し、Agent / LLM 主導の探索手順を指示する |

CODEX 版と CLAUDE 版は、同じ SPEC-grag CLI 契約を使う。違いは、各 Agent 環境の command metadata、tool permission、prompt 表現、引数展開方式だけである。

source of truth は、外部コマンド契約と SPEC-grag CLI の入出力である。CODEX 版または CLAUDE 版の command template を、仕様の唯一の根拠にしてはいけない。

### 5.2 Setup Script

本書でいう setup script は、実行時の検索・制約生成ではなく、SPEC-grag を使い始めるための配置と検証を行う補助コマンドである。

#### 5.2.1 Project Setup Script

Project Setup Script は、対象プロジェクトごとに実行する。

責務:

- `.spec-grag/config.toml` を作成または更新する
- `.spec-grag/.gitignore` を配置する
- CODEX 版 command template を `.codex/commands/` に配置する
- CLAUDE 版 command template を `.claude/commands/` に配置する
- skill 形式を選ぶ場合は `.codex/skills/spec-grag/` または `.claude/skills/spec-grag/` を配置する
- Purpose / Core Concept の雛形を、未存在の場合は既定で作成する
- Source Specs の配置例ディレクトリを、明示オプションがある場合だけ作成する
- `--dry-run` で作成・更新予定を表示する

Project Setup Script は既存ファイルを黙って上書きしない。既存ファイルがある場合は差分を示して停止するか、`--force` が明示された場合だけ更新する。

`--no-init-core-files` が指定された場合、Project Setup Script は Purpose / Core Concept の雛形を作らない。この場合、setup 後に人間が `core.purpose_file` と `core.concept_file` の実体を作成するまで `/spec-core` は失敗する。

Project Setup Script は `/spec-core` を自動実行しない。初期生成まで行う場合は、ユーザーが setup 後に `/spec-core` または `/spec-core --all` を明示実行する。

#### 5.2.2 System Setup Script

System Setup Script は、SPEC-grag 本体を利用可能にするために実行する。

責務:

- Python package と console script を利用可能にする
- `spec-grag`、`spec-grag-slash`、`spec-grag-watch`、`spec-grag-setup-project`、`spec-grag-setup-system` が呼べることを確認する
- CODEX 版 / CLAUDE 版 command template が配布物に含まれることを確認する
- Qdrant、embedding provider、Agent CLI など外部依存の有無を確認し、欠けているものを diagnostics として出す
- `--check-only` では変更せず、導入状態だけを確認する
- `--run-smoke` が明示された場合だけ smoke を実行する

System Setup Script は対象プロジェクトの Source Specs、Purpose、Core Concept、生成済み保持物を変更しない。対象プロジェクトへのファイル配置は Project Setup Script の責務である。

### 5.3 本運用 readiness と実 provider 実行 gate

本運用 readiness は、smoke test の opt-in とは別の運用前確認である。

smoke test は「実 provider を使う検証を明示的に走らせる」ための test profile であり、本運用で実 provider を使わなくてよいという意味ではない。本運用では、通常 CLI 経路が fake provider や memory retrieval に落ちず、認証済み Agent CLI、BGE-M3、Qdrant を使える状態であることを確認する。

本運用で real provider / real retrieval を実行する場合、次の環境変数を明示する。

| 環境変数 | 意味 |
|---|---|
| `SPEC_GRAG_REAL_PROVIDER=1` | `/spec-core` が `[llm]` の real Agent CLI provider を呼び出してよいことを示す |
| `SPEC_GRAG_REAL_RETRIEVAL=1` | `/spec-core` が FlagEmbedding BGE-M3 と Qdrant による real retrieval index を作成・更新してよいことを示す |
| `SPEC_GRAG_QDRANT_URL=<url>` | 接続する Qdrant service の URL |

これらは仕様上の機能切替ではなく、誤って外部 provider や永続 vector store を叩かないための実行安全 gate である。未設定の場合、通常経路は fake fallback で成功扱いにしてはいけない。real provider / real retrieval が必要な設定で gate が閉じている場合は、diagnostics と freshness failure として扱う。

`spec-grag-setup-system --check-only` は、console script、配布 template、FlagEmbedding、qdrant-client、Qdrant service、Agent CLI、上記 gate の状態を確認し、本運用可能な場合は `production_readiness.status = ready` と `blocking_reasons = []` を返す。欠損がある場合は `production_readiness.status = blocked` とし、欠損理由を diagnostics に出す。

`SPEC_GRAG_REAL_SMOKE` と `SPEC_GRAG_LOCAL_SERVICE` は smoke / test profile 用の互換的な実行指定であり、本運用 readiness の通常 gate ではない。

## 6. 共通契約

### 6.1 設定ファイル配置

コマンドは、対象プロジェクトルートで実行することを前提にする。コマンドは、実行ディレクトリ直下の `.spec-grag/config.toml` を読み込む。設定ファイルの場所は固定であり、カレントディレクトリから親方向へ探索しない。

```text
対象プロジェクト/
└── .spec-grag/
    └── config.toml
```

SPEC-grag 本体は共通ツールとして配置し、プロジェクトごとの差分は対象プロジェクト側の `.spec-grag/config.toml` に閉じ込める。

### 6.2 Context Freshness

`/spec-inject` と `/spec-realign` は、古い保持物を元に判断してはいけない。まず freshness gate を通し、freshness report の `status` が `fresh` の場合だけ続行する。

freshness report は `status` と `blocking_reasons[]` を持つ。

```text
status:
  fresh
  blocked
  degraded
  failed
```

`status = blocked` は、制約生成や回答生成へ進めない状態である。`status = degraded` は任意 artifact の一部が欠けているが、必須 artifact は使える状態である。`status = failed` は必須 artifact や retrieval index が使えない状態である。

`blocking_reasons[]` は、少なくとも次を持つ。

```text
dirty_or_stale_source
watcher_running
watcher_queue_pending
stale_config_or_schema
failed_required_artifact
pending_conflict
degraded_optional_artifact
```

複数理由が同時に成立する場合は、表示優先を次の順にする。

```text
dirty_or_stale_source
watcher_running
watcher_queue_pending
stale_config_or_schema
failed_required_artifact
pending_conflict
degraded_optional_artifact
```

dirty / stale / watcher queue がある場合、同時に存在する pending conflict は古い Source Specs に基づく可能性があるため、まず `/spec-core` による更新または再生成を促す。更新後も残る pending conflict だけを人間判断対象として提示する。

`degraded` は、一部 section / chapter の生成失敗など、保持物が完全ではないことを示す。retrieval index や必須 artifact が使えない場合は `failed` として扱い、制約生成へ進まない。

`/spec-core` は保持物を更新するための明示コマンドである。`/spec-inject` と `/spec-realign` は、前処理として `/spec-core` 相当の更新を自動起動しない。会話中の注入コマンドが予期せず長時間ブロックすることを避け、どの保持物を根拠にしたかを明確にするためである。

freshness gate の扱いは次のとおりである。

| freshness | `/spec-inject` / `/spec-realign` の扱い |
|---|---|
| `status = fresh` | その保持物を使って続行する |
| `status = blocked` かつ `blocking_reasons[]` に dirty / stale / watcher 系がある | 停止し、watcher の完了を待つか `/spec-core` を実行するよう促す |
| `status = blocked` かつ `blocking_reasons[]` に `pending_conflict` だけが残る | 停止し、人間判断が必要な Conflict Review Item を提示する |
| `status = degraded` | degraded warning を表示し、必須 artifact が揃っている場合だけ続行できる |
| `status = failed` | 停止し、`/spec-core` または `/spec-core --all` による再生成を促す |

watcher は任意である。watcher を使う場合は Source Specs の変更を background で `/spec-core` 相当の incremental update として処理する。watcher が実行中である、または queue file に未処理変更が残っている場合、freshness gate は `status = blocked` とし、`watcher_running` または `watcher_queue_pending` を `blocking_reasons[]` に入れる。watcher を使わない場合は、人間または CI が `/spec-core` を明示実行してから `/spec-inject` / `/spec-realign` を実行する。

`/spec-core --all` または `/spec-core -a` だけが全再生成を行う。通常の `/spec-core` は変更分のみを更新する。

### 6.3 Watcher Snapshot Isolation

watcher は、1 回の background update で処理する Source Specs の snapshot を開始時点で固定する。実行中に追加変更が入った場合、その変更を同じ run に混ぜず、次の queue として扱う。

この不変条件により、生成済み保持物が「一部は古い Source Specs、一部は新しい Source Specs」に由来する状態を避ける。snapshot 処理中、または queue が残っている間、`/spec-inject` と `/spec-realign` は `status = blocked` として停止する。

### 6.4 Conversation Context

`/spec-inject` と `/spec-realign` は、明示された課題プロンプトだけでなく、現在の会話区間も入力として扱う。ただし、会話区間を解釈する主体は Agent / LLM である。

```text
Conversation Context
  - 現在のユーザー発話
  - 直近の会話区間
  - 明示された課題プロンプト
  - 進行中の作業対象
```

会話区間は検索キー生成と制約生成の入力であり、仕様上の根拠ではない。最終根拠は Purpose、Core Concept、Source Specs のどれに由来するかを区別する。Section Metadata と Chapter Key Anchor を使った場合は、参照補助として区別する。

### 6.5 生テキスト投入の制限

SPEC-grag は、Source Specs 本文を無条件に LLM コンテキストへ丸ごと投入しない。

Agent / LLM は、Agentic Search、検索キー生成、根拠確認のために必要な Source Specs snippet を読むことができる。ただし、読んだ本文を無整理のまま最終回答の前提へ混ぜてはいけない。最終的に使う制約は、今回の課題に必要なものとして生成し、根拠を示す。

Search Keys は根拠ではない。Section Summary と Chapter Key Anchor は検索・理解の補助であり、制約として採用する場合は Purpose、Core Concept、Source Specs、または解決済み Conflict Review Item の根拠を確認する。

全文を最終コンテキストとして扱うのは、ユーザーが明示的に全文レビューを求めた場合に限る。

### 6.6 Source Specs の section 化規約

SPEC-grag は、Source Specs の Markdown 見出しを section 境界として扱う。section は変更検出、Section Metadata 生成、retrieval provenance、incremental 更新の基本単位である。

section 化する最大見出し深さは `.spec-grag/config.toml` の `[section].max_heading_level` で指定する。設定値より深い見出しは独立 section にせず、直近の親 section 本文に統合する。

標準設定は `max_heading_level = 4` とする。この場合、`#` / `##` / `###` / `####` は section 境界になり、`#####` / `######` は親 section に含まれる。

```text
# Chapter                         -> section
## Feature                        -> section
### Field group                   -> section
#### Image upload                 -> section
##### Internal helper             -> parent section body
```

`source_section_id` は section 化後の単位に対して付与する。

外部参照 API と artifact 間 join の canonical id は `source_section_id` とする。内部 schema で `section_id` と書く場合は `source_section_id` の alias とし、新規実装では同一値にする。`stable_section_uid` は heading rename や移動に対する同一性推定用であり、外部参照 API の primary key にはしない。

## 7. `/spec-core [--all|-a]`

### 7.1 目的

`/spec-core` は、Purpose / Core Concept 以外の保持物を生成・更新するためのコマンドである。

```text
/spec-core
  = section hash に基づく incremental update

/spec-core --all
  = コマンド更新対象の再生成
```

### 7.2 入力

| 入力 | 内容 |
|---|---|
| `.spec-grag/config.toml` | 対象ソース、Purpose、Core Concept、保持物の保存先、LLM / embedding 設定 |
| Source Specs | `sources.include` で指定された仕様ファイル |
| Purpose | `core.purpose_file` で指定されたファイル。読み取り専用 |
| Core Concept | `core.concept_file` で指定されたファイル。人間更新対象 |
| `--all` / `-a` | コマンド更新対象を再生成する |

### 7.3 動作

通常実行では、section hash に基づいて変更された Source Specs だけを中心に保持物を更新する。

```text
/spec-core
  -> Source Specs の section manifest を作る
  -> section hash を比較する
  -> 変更 section の Section Summary を更新する
  -> 変更 section の Section Search Keys を更新する
  -> Source Retrieval Index を更新する
  -> 関連候補を広く集め、LLM が Related Sections を理由付きで選ぶ
  -> conflicts_with が疑われる pair を検査する
  -> LLM が解決できない conflict を Conflict Review Item として記録する
  -> 影響する Chapter Key Anchor を更新する
  -> CoreResult を出力する

/spec-core --all
  -> Source Specs を全件読み込む
  -> Section Summary を再生成する
  -> Section Search Keys を再生成する
  -> Source Retrieval Index を再生成する
  -> Related Sections を再生成する
  -> conflicts_with が疑われる pair を検査する
  -> LLM が解決できない conflict を Conflict Review Item として記録する
  -> Chapter Key Anchor を再生成する
  -> CoreResult を出力する
```

Purpose と Core Concept は常に読み取り専用である。`/spec-core` はこれらを自動更新しない。

`spec-grag-watch` が呼び出す core 更新は `/spec-core` の外部 slash command 実行ではない。watcher は background execution role として `spec-core` 相当の incremental update を実行する。

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
  - potential_conflicts
  - conflict_review_items
  - pending_conflict_count
  - unreflected_conflict_resolutions
  - stale_resolution_count
  - freshness_report
  - warnings
```

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

人間が判断した Conflict Review Item は、決定内容、理由、判断者が参照した source refs を resolution として保持する。resolution は人間の明示判断であり、`/spec-inject` と `/spec-realign` は一時的な根拠として参照してよい。ただし、長期的には Purpose、Core Concept、または Source Specs のどれかへ反映することを推奨する。

SPEC-grag は resolution を Purpose、Core Concept、Source Specs へ自動反映しない。反映は人間の作業である。resolved Conflict Review Item がまだ Purpose、Core Concept、Source Specs のどれにも反映されていない場合、`/spec-core` は `unreflected_conflict_resolutions` として通知する。`/spec-inject` と `/spec-realign` がその resolution を根拠として使う場合は、「解決済みだが Source Specs 等へ未反映の人間判断」であることを明示する。未反映であること自体は blocker ではない。

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

Conflict 判定は Related Sections 選定後の別 stage とする。対象は `relation_hint = conflicts_with` またはそれに準じる高リスク候補だけであり、全 section pair を総当たりで LLM 判定しない。実装は複数 conflict pair を chapter や source document 単位で batch 化してよい。

Related Sections に選ばれなかった候補でも、同一 identifier、同一 config / status 名、must / must not / 禁止 / 例外 / required / optional などの衝突しやすい語を共有する pair は、`conflict_pair_max_per_section` の範囲で high-risk pair として conflict 判定 stage に送る。上限により送らなかった pair は diagnostics に残す。

## 8. `/spec-inject [<課題プロンプト>]`

### 8.1 目的

`/spec-inject` は、Agent / LLM が現在の会話区間と課題を解釈し、SPEC-grag の保持物を使って今回必要な制約を生成し、会話区間へ注入するためのコマンドである。

このコマンドは課題に対する最終回答を作ることを目的にしない。LLM の注意を、本来の目的、Core Concept、関連 Source Specs、section summary、related sections、chapter key anchor へ戻すことを目的にする。

### 8.2 入力

| 入力 | 内容 |
|---|---|
| Conversation Context | 現在のユーザー発話、直近の会話区間、進行中の作業対象 |
| `<課題プロンプト>` | 任意。指定された場合は中心課題として扱う |
| `.spec-grag/config.toml` | 対象プロジェクト設定 |
| Purpose | 読み取り専用の上位目的 |
| Core Concept | 人間更新対象のコアコンセプト |
| Generated Context Artifacts | Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor、Source Retrieval Index |

### 8.3 Agent / LLM が行う作業

`/spec-inject` の slash command は、Agent / LLM に次の手順を指示する。

```text
1. 会話区間、課題を解釈する
2. 必要な検索キーを作る
3. Purpose と Core Concept を参照する
4. その検索キーで hybrid retrieval を実行し、検索結果を見て Agentic Search を行う
5. その検索キーで Section Summary を参照し、Agentic Search を行う
6. Related Sections を参照し、Agentic Search を行う
7. 必要に応じて Chapter Key Anchor を参照する
8. 集めた情報から、今回の課題に必要な制約を生成する
9. 生成した制約を会話区間に注入する
```

Agentic Search は Agent / LLM の責務である。CLI は、検索結果、summary、related sections、chapter anchor、source snippet を返すだけであり、探索方針を自律的に決めない。

### 8.4 CLI が提供する操作

実装は詳細設計に委ねるが、外部契約として CLI は少なくとも次の参照を提供する。

```text
検索キーによる hybrid retrieval
Purpose 取得
Core Concept 取得
Core Concept が大きい場合の検索キーによる Core Concept retrieval
source_section_id による Section Summary 取得
source_section_id による Section Search Keys 取得
source_section_id による Related Sections 取得
chapter id による Chapter Key Anchor 取得
source span / chunk id による根拠 snippet 取得
freshness report 取得
```

### 8.5 通常出力

freshness report の `status = fresh` の場合、`/spec-inject` は Agent / LLM が生成した今回用の制約セットと、その根拠・探索経路の要約を会話へ注入する。

人間に見える出力は、内部 JSON ではなく、次のような読みやすい構造を基本とする。

```text
今回守る制約
  - <制約>
    根拠: Purpose / Core Concept / Source Specs
    参照補助: Section Summary / Chapter Key Anchor / Related Sections
    source: <source_document_id / source_section_id / source_span>

今回見るべき対象
  - <section または topic>
    理由: <なぜ今回関係するか>

関連先として確認したもの
  - <related section>
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

## 9. `/spec-realign [<課題プロンプト>]`

### 9.1 目的

`/spec-realign` は、`/spec-inject` と同じ手順で今回必要な制約を生成し、その制約に従って課題への回答または修正案を作るためのコマンドである。

`<課題プロンプト>` が省略された場合、Agent / LLM は現在のユーザー発話と直近の会話区間から中心課題を解釈する。中心課題を特定できない場合は、回答生成を進めずに確認を求める。

### 9.2 動作

```text
/spec-realign [<課題プロンプト>]
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

## 10. 設定ファイル

### 10.1 主な設定項目

対象プロジェクトのルートに `.spec-grag/config.toml` を置く。

| table | key | 必須性 | 内容 |
|---|---|---|---|
| `[sources]` | `include` | 必須 | Source Specs として読む Markdown glob。複数指定可 |
| `[sources]` | `exclude` | 任意 | `include` から除外する glob |
| `[core]` | `purpose_file` | 必須 | Purpose ファイル。SPEC-grag は更新しない |
| `[core]` | `concept_file` | 必須 | Core Concept ファイル。人間更新対象 |
| `[context]` | `storage` | 任意 | 生成済み保持物の保存先 |
| `[section]` | `max_heading_level` | 任意 | section 化する最大 Markdown heading level。標準は `4` |
| `[section_metadata]` | `summary_enabled` / `search_keys_enabled` / `related_sections_enabled` | 任意 | Section Metadata 生成の有効化 |
| `[chapter_anchor]` | `enabled` | 任意 | Chapter Key Anchor 生成の有効化 |
| `[llm]` | `provider` / `command` / `model` / `effort` / `timeout_sec` / `max_retries` | 必須 | `/spec-core` が Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor、conflict 判定を実行するための LLM |
| `[retrieval]` | `chunk_size` / `chunk_overlap` / `dense_top_k` / `sparse_top_k` / `rank_fusion` | 任意 | hybrid retrieval の取得幅 |
| `[embedding]` | `provider` / `model` / `dense_enabled` / `sparse_enabled` | 必須 | embedding provider。標準は `flagembedding` + `BAAI/bge-m3` |
| `[vector_store]` | `provider` / `url` / `collection` | 必須 | vector store。標準は Qdrant |
| `[limits]` | `section_summary_max_chars` / `search_keys_max` / `related_candidate_max_per_section` / `related_selected_max_per_section` / `conflict_pair_max_per_section` / `llm_batch_max_sections` / `llm_batch_max_chars` | 任意 | LLM 呼び出しと候補生成の上限 |
| `[watcher]` | `enabled` / `interval_ms` / `debounce_ms` / `stale_lock_ms` / `state_file` / `queue_file` | 任意 | Source Specs 変更検知と background incremental の設定 |
| `[run]` | `save_artifacts` / `artifact_dir` / `include_request` / `include_response` / `redact_payload` | 任意 | run artifact 保存設定 |

最小構成例:

```toml
[sources]
include = ["docs/spec/**/*.md"]
exclude = ["**/drafts/**"]

[core]
purpose_file = "docs/SPEC-grag/core/purpose.md"
concept_file = "docs/SPEC-grag/core/concept.md"

[context]
storage = ".spec-grag/context/"

[section]
max_heading_level = 4

[section_metadata]
summary_enabled = true
search_keys_enabled = true
related_sections_enabled = true

[chapter_anchor]
enabled = true

[llm]
provider = "codex_cli"
command = "codex"
model = "gpt-5.4-mini"
effort = "low"
timeout_sec = 120
max_retries = 1

[limits]
section_summary_max_chars = 480
search_keys_max = 32
related_candidate_max_per_section = 32
related_selected_max_per_section = 8
conflict_pair_max_per_section = 8
llm_batch_max_sections = 8
llm_batch_max_chars = 12000

[retrieval]
chunk_size = 1200
chunk_overlap = 160
dense_top_k = 12
sparse_top_k = 20
rank_fusion = "rrf"

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"
dense_enabled = true
sparse_enabled = true

[vector_store]
provider = "qdrant"
url = "http://localhost:6333"
collection = "spec_grag_source"

[watcher]
enabled = true
interval_ms = 2000
debounce_ms = 1000
stale_lock_ms = 300000
state_file = ".spec-grag/state/watch_state.json"
queue_file = ".spec-grag/state/watch_queue.json"
```

`[llm]` は `/spec-core` の生成・選定・conflict 判定用である。`/spec-inject` / `/spec-realign` の会話区間解釈、Agentic Search、制約生成、回答生成を行う Agent / LLM は、外部の Agent 環境が担うため、この `[llm]` の対象外である。

### 10.2 配置例

```text
your-project/
├── .spec-grag/
│   ├── config.toml
│   └── context/                  # 生成済み保持物。gitignore 推奨
├── .codex/
│   └── commands/                 # CODEX 版 command template の配置例
│       ├── spec-core.md
│       ├── spec-inject.md
│       └── spec-realign.md
├── .claude/
│   └── commands/                 # CLAUDE 版 command template の配置例
│       ├── spec-core.md
│       ├── spec-inject.md
│       └── spec-realign.md
├── docs/
│   ├── SPEC-grag/
│   │   └── core/
│   │       ├── purpose.md
│   │       └── concept.md
│   └── spec/                     # Source Specs
│       └── ...
```

上記は command 形式の配置例である。Agent 環境が skill 形式を使う場合は、同等の手順を `.codex/skills/spec-grag/SKILL.md` または `.claude/skills/spec-grag/SKILL.md` に置き、`/spec-core`、`/spec-inject`、`/spec-realign` の command template はその skill を呼び出す薄い入口にしてよい。

### 10.3 `.gitignore` 推奨設定

`.spec-grag/config.toml` は対象プロジェクトの設定として管理してよい。一方、生成済み保持物、pending state、cache、tmp、watcher state には Source Specs 由来の抽出中間データや LLM 出力が含まれる可能性があるため、通常は Git 管理しない。

CODEX 版 / CLAUDE 版の command template は、対象プロジェクトの操作入口であるため Git 管理してよい。ただし、Agent 環境の認証情報、ログ、セッション state が同じディレクトリに作られる場合は、それらだけを ignore する。

```gitignore
.spec-grag/context/
.spec-grag/pending/
.spec-grag/cache/
.spec-grag/state/
.spec-grag/tmp/
.spec-grag/runs/
```

## 11. エラー契約

| 状態 | 期待動作 |
|---|---|
| `.spec-grag/config.toml` が見つからない | エラー終了し、設定ファイル作成を促す |
| Purpose が見つからない | エラー終了する |
| Core Concept が見つからない | エラー終了する |
| Source Specs が見つからない | エラー終了する |
| Section Metadata 更新に一部失敗 | 失敗 section を出力し、必須 artifact が揃う場合は `status = degraded` として扱う |
| Chapter Key Anchor 更新に一部失敗 | 失敗 chapter を出力し、必須 artifact が揃う場合は `status = degraded` として扱う |
| embedding / retrieval index 更新に失敗 | `status = failed` として扱い、古い index を新しいものとして採用しない |
| dirty / stale / watcher 系 blocking reason がある | `/spec-inject` / `/spec-realign` は自動更新せず、watcher の完了、`/spec-core`、または `/spec-core --all` を促して停止する |
| `pending_conflict` だけが blocking reason として残っている | `/spec-inject` / `/spec-realign` は制約生成 / Answer 生成を行わず、Conflict Review Item と判断肢を提示する |
| watcher running / queued changes が残っている | `/spec-inject` / `/spec-realign` は制約生成 / Answer 生成を行わず、watcher の完了を待つ |
| Project Setup Script の target が存在しない | 明示オプションなしでは作成せず、作成するかどうかを人間に委ねる |
| Project Setup Script の配置先に既存ファイルがある | 黙って上書きせず、差分または衝突ファイル一覧を出して停止する。`--force` がある場合だけ更新する |
| System Setup Script の依存ツールが見つからない | 失敗または warning として diagnostics に出し、足りない command / package / service を示す |

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
