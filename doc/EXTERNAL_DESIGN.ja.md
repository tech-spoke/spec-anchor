# SPEC-grag 外部設計書

本書は SPEC-grag の外部契約を定義する。ここでは、ユーザーが何を実行できるか、各コマンドが何を保証するか、設定ファイルに何を書くか、どのような出力を返すかだけを扱う。

GRAG の内部構築、抽出器、エンティティ関係グラフ、階層クラスタ、検証処理、LLM プロバイダー実装の詳細は詳細設計書に委ねる。

## 1. 目的

近年の LLM は、与えられた資料に忠実に作業する傾向が強い。これは実装作業では有益だが、仕様が揺れている仕様策定段階では、直近に読んだ資料へ過剰にアンカーされ、上位目的や不変の設計思想から逸脱する原因になる。

SPEC-grag は、LLM が目の前の課題や局所資料に引っ張られすぎることを防ぐため、次の情報を明示的に再注入・照射する。

| 要素 | 意味 | 更新方針 |
|---|---|---|
| Purpose | 本来の目的。ビジネスゴール、UX の根幹、システムが存在する理由 | 人間が手書きする。SPEC-grag は更新しない |
| Concept | コアコンセプト。不変のアーキテクチャ方針、設計思想 | SPEC-grag が更新案を提示できる。確定は人間が行う |
| Source specs | 現行の章ファイル、作業中仕様。課題に対して制約側にも修正対象側にもなり得る仕様本文 | ユーザー・LLM が編集する。SPEC-grag は変更検出し、GRAG 更新の入力にする |
| ChapterAnchor | 章別キーアンカー。各章の主要エンティティ、キー概念、要約 | GRAG 更新時に生成・更新する |
| Entity Relationship Graph | 仕様要素間の関係グラフ | GRAG 更新時に生成・更新する |
| Hierarchical Cluster | 章・概念・関係の階層クラスタ | GRAG 更新時に生成・更新する |

SPEC-grag が実現したい判断の流れは次である。課題プロンプトと会話区間を入力にして、Purpose を常に制約側の上位根拠として取得し、Concept、Source specs、ChapterAnchor、関係グラフ、階層クラスタを検索して、制約側と修正対象側へ分類する。

```text
ConversationContext / 課題プロンプト
  -> Purpose を取得し、常に制約側へ置く
  -> Concept / Source specs / ChapterAnchor / 関係グラフ / 階層クラスタを検索

  制約側:
    -> Purpose から守るべき上位制約を抽出
    -> 課題に対して制約として働く Concept / Source specs を分類
    -> 制約として効く ChapterAnchor を抽出

  修正対象側:
    -> 課題に直接関係する Concept / Source specs を抽出
    -> 修正対象候補に関係する ChapterAnchor を抽出
    -> 修正対象候補に関係する章・節・エンティティを抽出

  -> 無関係な情報を除外
  -> 制約を修正対象候補に照射
  -> LLM が回答または修正案を作る
```

## 2. コマンド体系

SPEC-grag は、ユーザー向けに次の 3 コマンドを提供する。

| コマンド | オプション / 引数 | 目的 | 回答生成 |
|---|---|---|---|
| `/spec-core` | `--all` / `-a` | GRAG のインクリメント更新または全再構築を行い、Concept を保守する | しない |
| `/spec-inject` | `[<課題プロンプト>]` | 会話区間または課題プロンプトに対する InjectionContext を注入する | しない |
| `/spec-realign` | `<課題プロンプト>` | `/spec-inject` 相当の InjectionContext を反映し、課題プロンプトに対する制約照射済み回答を出す | する |

すべてのコマンドは、対象プロジェクトルートで実行する。実行時には、そのプロジェクトルート直下の `.spec-grag/config.toml` を読み込む。

## 3. 共通契約

### 3.1 設定ファイル配置

コマンドは、対象プロジェクトルートで実行することを前提にする。コマンドは、実行ディレクトリ直下の `.spec-grag/config.toml` を読み込む。設定ファイルの場所は固定であり、カレントディレクトリから親方向へ探索しない。

```text
対象プロジェクト/
└── .spec-grag/
    └── config.toml
```

SPEC-grag 本体は共通ツールとして配置し、プロジェクトごとの差分は対象プロジェクト側の `.spec-grag/config.toml` に閉じ込める。

### 3.2 GRAG Freshness

`/spec-inject` と `/spec-realign` は、古い GRAG を元に判断してはいけない。そのため、どちらも本処理の前に `/spec-core` 相当のインクリメント更新を実行する。

```text
/spec-inject
  -> core incremental
  -> inject

/spec-realign <課題プロンプト>
  -> core incremental
  -> inject 相当
  -> realign
  -> answer
```

`/spec-core --all` または `/spec-core -a` だけが全再構築を行う。通常の `/spec-core`、`/spec-inject`、`/spec-realign` は変更分のみを更新する。

### 3.3 ConversationContext

`/spec-inject` と `/spec-realign` は、明示された課題プロンプトだけでなく、現在の会話区間も入力として扱う。

```text
ConversationContext
  - 現在のユーザー発話
  - 直近の会話区間
  - 明示された課題プロンプト
  - 進行中の作業対象
```

会話区間は検索・分類の入力であり、仕様上の根拠ではない。会話区間と課題プロンプトは、Concept、Source specs、ChapterAnchor、関係グラフ、階層クラスタを検索し、それらを今回の作業に対して次のどちらで扱うかを決めるために使う。

```text
制約側:
  今回の修正対象ではないが、守るべき目的・設計思想・境界条件として効くもの

修正対象側:
  今回の課題に直接関係し、変更候補または検討対象として扱うもの
```

Concept と Source specs は、常に制約とは限らず、常に修正対象とも限らない。会話区間・課題に対して分類される。章本文や Concept を読んだ瞬間にそれを正として固定するのではなく、まず「制約として守るもの」と「修正対象として扱うもの」に分けることが、SPEC-grag の主要な役割である。

完全に無関係な情報は、制約にも修正対象にもせず、LLM コンテキストへ注入しない。

`/spec-inject` に `<課題プロンプト>` が渡された場合は、それを ConversationContext の中心クエリとして使う。渡されない場合は、現在の会話区間から中心クエリを推定する。

### 3.4 Purpose と Concept の扱い

Purpose は人間が手書きする。SPEC-grag は Purpose を読み、出力に含めることはできるが、更新してはいけない。

Concept は SPEC-grag が更新案を提示できる。ただし、自動確定してはいけない。Concept に変更案がある場合は unified diff として提示し、人間が hunk 単位で accept / reject / 修正指示を行う。

### 3.5 生テキスト投入の制限

SPEC-grag は、章ファイル本文を無条件に LLM コンテキストへ丸ごと投入しない。LLM へ渡す文脈は、InjectionContext として、ConstraintContext、TargetContext、ExclusionNotes、ConflictNotes、ReviewNotes、GRAG Freshness Report に構造化する。

章本文は、Agentic search、GRAG 検索候補の抽出、根拠確認のために読むことを許可する。ただし、読んだ章本文を無分類のまま LLM コンテキストへ丸ごと注入してはいけない。

標準フローは次である。

```text
ConversationContext / 課題プロンプト
  -> Agentic search で関連しそうな章本文を読む
  -> キーワード / エンティティ / 章候補を抽出
  -> GRAG に投げる検索候補を作る
  -> GRAG 検索 / グラフ探索
     -> ChapterAnchor を取得
     -> 関係グラフを辿る
     -> 階層クラスタを取得
     -> 依存・波及候補を取得
  -> GRAG 結果から必要な根拠 snippet 候補を特定
  -> 必要なら根拠 snippet を読む
  -> Agentic search 結果 + GRAG 結果 + snippet を統合
  -> 制約側 / 修正対象側 / 無関係 / 競合 / 人間レビューに分類
```

全文を最終コンテキストとして扱うのは、ユーザーが明示的に全文レビューを求めた場合に限る。

## 4. `/spec-core [--all|-a]`

### 4.1 目的

`/spec-core` は、GRAG の鮮度を保ち、Concept を保守するためのコマンドである。

```text
/spec-core
  = GRAG インクリメント
  + Concept 更新案の提示

/spec-core --all
  = GRAG 全再構築
  + Concept 再生成案の提示
```

### 4.2 入力

| 入力 | 内容 |
|---|---|
| `.spec-grag/config.toml` | 対象ソース、Purpose、Concept、GRAG 保存先、LLM 設定 |
| Source specs | `sources.include` で指定された仕様章ファイル |
| Purpose | `core.purpose_file` で指定されたファイル。読み取り専用 |
| Concept | `core.concept_file` で指定されたファイル。更新案の対象 |
| `--all` / `-a` | 全再構築を行う |

### 4.3 動作

通常実行では、変更された Source specs だけを対象に GRAG をインクリメント更新する。Concept に更新候補がある場合は diff を提示する。

```text
/spec-core
  -> Source specs の変更検出
  -> GRAG incremental update
  -> Concept 更新候補の生成
  -> Concept diff 判定
  -> CoreResult を出力

/spec-core --all
  -> Source specs を全件読み込み
  -> GRAG full rebuild
  -> Concept 再生成候補の生成
  -> Concept diff 判定
  -> CoreResult を出力
```

`--all` または `-a` が指定された場合は、すべての Source specs を対象に GRAG を再構築し、Concept の再生成案を提示する。

Purpose は常に読み取り専用である。

### 4.4 出力

`/spec-core` は次を出力する。

```text
GRAG 更新結果
  - incremental / full rebuild
  - 更新対象ファイル
  - スキップされたファイル
  - 失敗したファイル

Concept 更新案
  - diff あり / なし
  - diff がある場合は unified diff

Freshness Report
  - 最終更新時刻
  - GRAG 保存先
  - 警告
```

### 4.5 人間確認

Concept diff が出力された場合、エージェントはユーザーに hunk 単位で accept / reject / 修正指示を確認する。確認なしに Concept を書き換えてはいけない。reject する場合は、ユーザーから修正指示を受け取り、必要に応じて Concept 更新候補を再生成する。

## 5. `/spec-inject [<課題プロンプト>]`

### 5.1 目的

`/spec-inject` は、LLM が議論中に Purpose / Concept からドリフトしたとき、現在の会話区間または課題プロンプトに対する InjectionContext をコンテキストへ再注入するためのコマンドである。

このコマンドは課題に対する最終回答を作ることを目的にしない。LLM のアテンションを本来の目的、コアコンセプト、関連章アンカー、守るべき制約へ戻すことを目的にする。

`/spec-inject` と `/spec-realign` は、InjectionContext を作るところまでは本質的に同じである。違いは、`/spec-realign` がその InjectionContext を前提に、回答または修正案まで生成する点である。

### 5.2 入力

| 入力 | 内容 |
|---|---|
| ConversationContext | 現在のユーザー発話、直近の会話区間、進行中の作業対象 |
| `<課題プロンプト>` | 任意。指定された場合は中心クエリとして扱う |
| `.spec-grag/config.toml` | 対象プロジェクト設定 |
| Purpose | 読み取り専用の上位目的 |
| Concept | 人間承認済みのコアコンセプト |
| Source specs | 現行の章ファイル、作業中仕様。Agentic search の読解対象であり、制約側 / 修正対象側への分類対象であり、ChapterAnchor と GRAG 更新の入力でもある |

### 5.3 動作

`/spec-inject` は、最初に `/spec-core` 相当のインクリメント更新を行う。その後、最新 GRAG から注入用文脈を作る。

```text
/spec-inject [<課題プロンプト>]
  -> /spec-core incremental を実行
  -> CoreResult を取得
  -> Concept diff があればユーザーに accept / reject / 修正指示を要求
  -> Concept diff が解決した場合のみ承認済み Concept を確定
  -> ConversationContext を取得
  -> Purpose を取得
  -> 承認済み Concept を取得

  共通候補抽出:
    -> Agentic search で関連しそうな章本文を読む
    -> キーワード / エンティティ / 章候補を抽出
    -> GRAG に投げる検索候補を作る

  制約側:
    -> 検索候補から制約探索クエリを作る
    -> GRAG 検索 / グラフ探索
    -> Purpose / Concept から守るべき制約を取得
    -> 課題に対して制約として働く Concept / Source specs を分類
    -> 制約として効く ChapterAnchor を取得

  修正対象側:
    -> 検索候補から修正対象探索クエリを作る
    -> GRAG 検索 / グラフ探索
    -> 関連する Concept / Source specs を取得
    -> 修正対象候補に関係する ChapterAnchor を取得
    -> 修正対象候補に関係する章・節・エンティティを取得

  -> 必要なら根拠 snippet を読む
  -> Agentic search 結果 + GRAG 結果 + snippet を統合
  -> 制約側 / 修正対象側 / 無関係 / 競合 / 人間レビューに分類
  -> InjectionContext を出力
```

Concept 更新案は `/spec-core` 相当の incremental 処理中に発生する。未承認の Concept 更新案を InjectionContext に採用してはいけない。

```text
Concept diff が発生:
  ユーザーが accept
    -> 承認済み Concept として InjectionContext に使う

  ユーザーが reject
    -> Concept 更新案を採用しない
    -> ユーザーから修正指示を受け取る
    -> 必要に応じて Concept 更新候補を再生成する
    -> 再度ユーザー確認を行う

  ユーザーが未確認
    -> InjectionContext を作らない
    -> Concept を書き換えず、確認待ちとして停止する
```

Concept diff が未承認のまま `/spec-inject` の注入用文脈生成へ進んではいけない。

### 5.4 出力

`/spec-inject` は InjectionContext を出力する。

```text
InjectionContext
  - ConversationContext の要約
  - ConstraintContext
    - Purpose 由来の制約
    - Concept 由来の制約
    - Source specs 由来の制約
    - ChapterAnchor 由来の制約または制約探索入口
    - ClassificationNotes
      - 制約側に分類した理由
  - TargetContext
    - 修正対象候補
    - 関連 Concept / Source specs
    - 関連 ChapterAnchor
    - 修正対象候補に関係する章・節・エンティティ
    - ClassificationNotes
      - 修正対象側に分類した理由
  - ExclusionNotes
    - 無関係として除外したもの
  - ConflictNotes
    - 制約側と修正対象側の衝突
    - Source specs 同士の矛盾
    - Concept と Source specs の矛盾
  - ReviewNotes
    - 人間の判断が必要な項目
    - 根拠不足または分類不能な項目
  - GRAG Freshness Report
```

`Purpose` は常に `ConstraintContext` に属し、`TargetContext` には入らない。

`Concept` は、課題に対して制約として働く場合は `ConstraintContext` に入り、修正・見直し・検討対象として扱う場合は `TargetContext` に入る。同じ Concept が制約側と修正対象側の両方に現れる場合もある。

`Source specs` も同様に、守るべき既存仕様として働く場合は `ConstraintContext` に入り、修正対象の章・節として扱う場合は `TargetContext` に入る。同じ Source specs が制約側と修正対象側の両方に現れる場合もある。

Concept diff が未解決の場合、`/spec-inject` は InjectionContext を出力しない。その場合は、Concept を書き換えず、ユーザーに accept / reject / 修正指示を求める確認要求だけを出力する。

### 5.5 LLM への要求

エージェントは `/spec-inject` の出力を読んだ後、`ConstraintContext` を守るべき制約として扱い、`TargetContext` を変更候補または検討対象として扱う。章本文、Concept、会話上の仮説が `ConstraintContext` と衝突する場合は、その衝突を隠さずユーザーに提示する。

## 6. `/spec-realign <課題プロンプト>`

### 6.1 目的

`/spec-realign` は、`/spec-inject` の発展形である。ConversationContext と課題プロンプトから `/spec-inject` 相当の InjectionContext を作り、それを前提に課題プロンプトに対する回答を LLM が出力する。

このコマンドは、次の 2 系統を分離して扱う。

```text
制約探索:
  課題プロンプト
    -> Purpose / Concept
    -> 課題に対して制約として働く Concept / Source specs
    -> 関連 ChapterAnchor
    -> 守るべき制約

修正対象探索:
  課題プロンプト
    -> Agentic search
    -> Entity Relationship Graph
    -> Hierarchical Cluster
    -> 修正対象候補
```

最終的に、守るべき制約を修正対象候補へ照射し、回答または修正案を作る。

### 6.2 入力

| 入力 | 内容 |
|---|---|
| `<課題プロンプト>` | ユーザーが今回解くべき問い |
| ConversationContext | 現在のユーザー発話、直近の会話区間、進行中の作業対象 |
| `.spec-grag/config.toml` | 対象プロジェクト設定 |
| Purpose | 上位目的 |
| Concept | コアコンセプト |
| Source specs | 現行の章ファイル、作業中仕様。Agentic search の読解対象であり、制約側 / 修正対象側への分類対象であり、ChapterAnchor と GRAG 更新の入力でもある |
| 最新 GRAG | ChapterAnchor、関係グラフ、階層クラスタ |

### 6.3 動作

`/spec-realign` は、最初に `/spec-core` 相当のインクリメント更新を行う。その後、5.3 と同じ手順で InjectionContext を生成し、6.5 の Answer 生成契約に従って課題プロンプトへの回答を生成する。

```text
/spec-realign <課題プロンプト>
  -> /spec-core incremental を実行
  -> CoreResult を取得
  -> Concept diff があればユーザーに accept / reject / 修正指示を要求
  -> Concept diff が解決した場合のみ承認済み Concept を確定
  -> ConversationContext を取得
  -> 5.3 と同じ手順で InjectionContext を生成
  -> 6.5 の Answer 生成契約に従って Answer を生成
  -> RealignResult を出力
```

Concept diff が未承認のまま `/spec-realign` の文脈生成や `Answer` 生成へ進んではいけない。

### 6.4 出力

`/spec-realign` は RealignResult を出力する。

RealignResult は、`/spec-inject` が返す InjectionContext を再利用し、それを前提に課題プロンプトへ回答した結果である。`ConstraintContext` や `TargetContext` を RealignResult 側で別項目として再定義してはいけない。

Concept diff が未解決の場合、`/spec-realign` は RealignResult を出力しない。その場合は、Concept を書き換えず、ユーザーに accept / reject / 修正指示を求める確認要求だけを出力する。

```text
RealignResult
  - 課題プロンプト
  - InjectionContext
    - 5.4 と同じ構造
  - Answer
    - 6.5 の生成契約に従った LLM の回答または修正案
```

### 6.5 Answer 生成契約

本節は、6.4 の `RealignResult.Answer` をどのように生成するかを定義する。

LLM は、`RealignResult.task_prompt` と `RealignResult.InjectionContext` を入力として、次の規則で `Answer` を生成する。

```text
InjectionContext.ConstraintContext:
  今回守るべき制約として扱う

InjectionContext.TargetContext:
  今回の修正候補または検討対象として扱う

InjectionContext.ExclusionNotes:
  回答の前提情報として採用しない

InjectionContext.ConflictNotes:
  競合として Answer 内で明示する

InjectionContext.ReviewNotes:
  人間レビューが必要な点として Answer 内で明示する

InjectionContext.approved_concept_update / warnings:
  回答に影響する場合は、不確実性または人間レビュー項目として Answer 内で明示する
```

`Answer` は、少なくとも次を区別して記述する。

```text
今回の回答で守る制約
今回の回答で扱う修正候補または検討対象
競合 / 不確実性 / 人間レビューが必要な点
課題プロンプトへの回答または修正案
```

制約と矛盾する案を出す場合は、その矛盾を `Answer` 内で明示し、人間レビューが必要な点として扱う。競合や人間レビュー項目は RealignResult のトップレベル項目として別定義せず、`Answer` の中で表現する。

## 7. 設定ファイル

### 7.1 設定項目

対象プロジェクトのルートに `.spec-grag/config.toml` を置く。

```toml
[sources]
# 仕様章ファイル群の glob パターン。複数指定可
include = [
  "docs/spec/**/*.md",
]
# 除外パターン
exclude = ["**/drafts/**"]

[core]
# Purpose（本来の目的）。人が手書き。SPEC-grag は更新しない
purpose_file = "docs/SPEC-grag/core/purpose.md"
# Concept（コアコンセプト）。SPEC-grag が更新案を作り、人間が承認する
concept_file = "docs/SPEC-grag/core/concept.md"

[graph]
# GRAG 永続化先。`.gitignore` 推奨
storage = ".spec-grag/graph/"

[llm]
# LLM プロバイダー。詳細な呼び出し方式は詳細設計書で定義する
provider = "codex_cli"

[llm.codex_cli]
command = "codex"
model = "gpt-5.4"

[llm.claude_cli]
command = "claude"
model = "sonnet"
```

### 7.2 配置例

```text
your-project/
├── .spec-grag/
│   ├── config.toml
│   └── graph/                    # 実行時データ。gitignore 推奨
├── docs/
│   ├── SPEC-grag/
│   │   └── core/
│   │       ├── purpose.md
│   │       └── concept.md
│   └── spec/                     # Source specs
│       └── ...
```

別プロジェクトでは、`sources.include` と `core.*_file` を対象プロジェクトの配置に合わせて変更する。SPEC-grag 本体をプロジェクトごとに編集してはいけない。

## 8. 出力契約

### 8.1 InjectionContext

`/spec-inject` は次の構造を返す。

```text
InjectionContext
  conversation_context_summary
  constraint_context
    purpose_constraints[]
    concept_constraints[]
    source_spec_constraints[]
    chapter_anchor_constraints[]
    classification_notes[]
  target_context
    candidate_targets[]
    related_concepts[]
    related_source_sections[]
    related_chapter_anchors[]
    related_entities[]
    classification_notes[]
  excluded_as_irrelevant[]
  conflict_notes[]
  review_notes[]
  freshness_report
  approved_concept_update?
  warnings[]
```

### 8.2 RealignResult

`/spec-realign` は次の構造を返す。

```text
RealignResult
  task_prompt
  injection_context
  answer
```

`answer` は、6.5 の Answer 生成契約に従って生成する。

### 8.3 CoreResult

`/spec-core` は次の構造を返す。

```text
CoreResult
  mode: incremental | full
  updated_sources[]
  skipped_sources[]
  failed_sources[]
  graph_storage
  freshness_report
  concept_diff?
  warnings[]
```

## 9. エラー契約

| 状態 | 期待動作 |
|---|---|
| `.spec-grag/config.toml` が見つからない | エラー終了し、設定ファイル作成を促す |
| Purpose が見つからない | エラー終了する |
| Concept が見つからない | 警告し、初期作成候補を提示する |
| Source specs が見つからない | エラー終了する |
| GRAG 更新に一部失敗 | 失敗ファイルを出力し、結果を degraded として扱う |
| Concept diff が未承認 | Concept を書き換えず、InjectionContext / Answer を生成せず、承認または修正指示待ちとして停止する |

## 10. 外部設計で扱わないこと

本書では次を扱わない。

```text
GRAG 内部の抽出器選定
AtomicFact / Triple Reflection の詳細
グラフ永続化形式
階層クラスタ生成方法
LLM プロバイダーの subprocess 実装
Codex skill / Claude command の内部プロンプト
```

これらは詳細設計書で定義する。
